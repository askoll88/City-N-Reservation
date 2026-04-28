"""
База данных для игры "Город N: Запретная Зона"
"""
from __future__ import annotations

import logging
import math
import os
import random
import threading
import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from typing import Any

import psycopg2
from psycopg2 import pool, OperationalError, InterfaceError
from psycopg2.extras import RealDictCursor

from infra import config
from game.item_pool import ITEMS_POOL
from game.constants import ITEM_CATEGORY_DROP_CHANCES_BY_LOCATION
from game.weapon_progression import (
    calc_weapon_attack,
    clamp_weapon_level,
    get_weapon_required_level,
    is_weapon,
    normalize_weapon_rank,
    roll_weapon_rank,
    roll_shop_weapon_level,
    weapon_upgrade_cost,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Пул соединений
# ---------------------------------------------------------------------------

_connection_pool = None
_pool_lock = threading.Lock()


def get_connection_pool():
    global _connection_pool
    if _connection_pool is None:
        with _pool_lock:
            if _connection_pool is None:
                _connection_pool = pool.ThreadedConnectionPool(
                    minconn=config.DB_POOL_MIN,
                    maxconn=config.DB_POOL_MAX,
                    host=config.DB_HOST,
                    port=config.DB_PORT,
                    dbname=config.DB_NAME,
                    user=config.DB_USER,
                    password=config.DB_PASSWORD,
                    cursor_factory=RealDictCursor,
                )
                logger.info("Пул соединений с БД создан")
    return _connection_pool


def get_connection():
    """
    Получить живое соединение из пула.
    Иногда пул может вернуть уже закрытое соединение (например после сетевого разрыва),
    в таком случае выкидываем его и пробуем взять следующее.
    """
    conn_pool = get_connection_pool()
    attempts = max(2, int(getattr(config, "DB_MAX_RETRIES", 3) or 3))
    last_exc = None
    for _ in range(attempts):
        conn = conn_pool.getconn()
        try:
            if getattr(conn, "closed", 1):
                conn_pool.putconn(conn, close=True)
                continue
            return conn
        except Exception as e:
            last_exc = e
            try:
                conn_pool.putconn(conn, close=True)
            except Exception:
                pass
    if last_exc:
        raise last_exc
    raise OperationalError("Не удалось получить живое соединение из пула")


def release_connection(conn, close: bool = False):
    """
    Вернуть соединение в пул.
    Если соединение закрыто/битое — удаляем из пула (close=True).
    """
    try:
        if conn is None:
            return
        if getattr(conn, "closed", 1):
            close = True
        get_connection_pool().putconn(conn, close=close)
    except Exception:
        # Не мешаем бизнес-логике, если пул уже в неконсистентном состоянии.
        logger.exception("Не удалось вернуть соединение в пул (close=%s)", close)


# ---------------------------------------------------------------------------
# Контекстный менеджер — основа всей работы с БД
# Гарантирует что соединение вернётся в пул даже при исключении.
# ---------------------------------------------------------------------------

@contextmanager
def db_cursor():
    conn = get_connection()
    close_conn = False
    try:
        with conn.cursor() as cursor:
            # Ensure DB session uses UTC so NOW() returns UTC.
            # This prevents timezone mismatches when server TZ != UTC.
            cursor.execute("SET timezone = 'UTC'")
            yield cursor, conn
            conn.commit()
    except Exception as e:
        if isinstance(e, (OperationalError, InterfaceError)):
            close_conn = True
        # Важно: rollback на уже закрытом conn вызывает InterfaceError и маскирует исходную ошибку.
        if conn is not None and not getattr(conn, "closed", 1):
            try:
                conn.rollback()
            except Exception:
                close_conn = True
        else:
            close_conn = True
        raise
    finally:
        release_connection(conn, close=close_conn)


# ---------------------------------------------------------------------------
# Инициализация схемы
# ---------------------------------------------------------------------------

def init_db():
    """Создать таблицы и заполнить справочник предметов."""

    # Сбрасываем кэш предметов перед инициализацией
    _reset_items_cache()

    with db_cursor() as (cursor, conn):

        # -- users ----------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id          SERIAL PRIMARY KEY,
                vk_id       BIGINT UNIQUE NOT NULL,
                name        VARCHAR(100) NOT NULL,
                location    VARCHAR(50)  DEFAULT 'город',
                health      INTEGER      DEFAULT 100,
                energy      INTEGER      DEFAULT 100,
                radiation   INTEGER      DEFAULT 0,
                money       INTEGER      DEFAULT 100,
                level       INTEGER      DEFAULT 1,
                experience  INTEGER      DEFAULT 0,
                strength    INTEGER      DEFAULT 4,
                stamina     INTEGER      DEFAULT 4,
                perception  INTEGER      DEFAULT 4,
                luck        INTEGER      DEFAULT 4,
                armor_defense     INTEGER DEFAULT 0,
                max_weight        INTEGER DEFAULT 20,
                max_health_bonus  INTEGER DEFAULT 0,
                hp_upgrade_level  INTEGER DEFAULT 0,
                artifact_slots    INTEGER DEFAULT 3,
                shells            INTEGER DEFAULT 0,
                player_class      VARCHAR(50),
                previous_location VARCHAR(50),
                hospital_treatments INTEGER DEFAULT 0,
                newbie_kit_received INTEGER DEFAULT 0,
                rank_tier       INTEGER DEFAULT 1,
                is_admin        INTEGER DEFAULT 0,
                is_banned       INTEGER DEFAULT 0,
                ban_reason      TEXT
            )
        """)

        # -- user_equipment -------------------------------------------------
        # Один слот = одна строка. Добавить новый слот = просто новая строка,
        # не нужен ALTER TABLE.
        # Известные слоты: weapon, head, body, legs, hands, feet,
        #                  backpack, device, shells_bag,
        #                  artifact_1, artifact_2, artifact_3
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_equipment (
                user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                slot      VARCHAR(30)  NOT NULL,
                item_name VARCHAR(100) NOT NULL,
                PRIMARY KEY (user_id, slot)
            )
        """)

        # -- user_flags -----------------------------------------------------
        # Бинарные/числовые флаги прогресса. Добавить новый флаг = новая строка.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_flags (
                user_id    INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                flag_name  VARCHAR(50) NOT NULL,
                value      INTEGER     DEFAULT 0,
                PRIMARY KEY (user_id, flag_name)
            )
        """)

        # -- user_runtime_state --------------------------------------------
        # JSON-состояния, которые должны переживать рестарты процесса бота.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_runtime_state (
                user_id      INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                state_key    VARCHAR(50)  NOT NULL,
                payload_json TEXT         NOT NULL,
                updated_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
                PRIMARY KEY (user_id, state_key)
            )
        """)

        # -- items ----------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id            SERIAL PRIMARY KEY,
                name          VARCHAR(100) UNIQUE NOT NULL,
                category      VARCHAR(50)  NOT NULL,
                description   TEXT,
                price         INTEGER      DEFAULT 0,
                attack        INTEGER      DEFAULT 0,
                defense       INTEGER      DEFAULT 0,
                weight        REAL         DEFAULT 1.0,
                backpack_bonus INTEGER     DEFAULT 0,
                rarity        VARCHAR(20)  DEFAULT 'common',
                anomaly_type  VARCHAR(30),
                bonus_type    VARCHAR(30),
                bonus_value   INTEGER      DEFAULT 0,
                drop_chance   INTEGER      DEFAULT 0,
                location_drop_chances JSONB DEFAULT '{}'::jsonb
            )
        """)

        # -- user_inventory -------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_inventory (
                id       SERIAL PRIMARY KEY,
                user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                item_id  INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                quantity INTEGER DEFAULT 1,
                item_level INTEGER DEFAULT 1,
                item_rank VARCHAR(20) DEFAULT 'common',
                UNIQUE(user_id, item_id)
            )
        """)

        # -- user_storage ---------------------------------------------------
        # Шкаф в убежище: хранение предметов вне инвентаря.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_storage (
                id       SERIAL PRIMARY KEY,
                user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                item_id  INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                quantity INTEGER DEFAULT 1,
                UNIQUE(user_id, item_id)
            )
        """)

        # -- game_settings --------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS game_settings (
                key         VARCHAR(100) PRIMARY KEY,
                value       VARCHAR(255) NOT NULL,
                updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)

        # -- market_listings ------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_listings (
                id              SERIAL PRIMARY KEY,
                seller_vk_id    BIGINT      NOT NULL,
                buyer_vk_id     BIGINT,
                item_id         INTEGER     NOT NULL REFERENCES items(id) ON DELETE RESTRICT,
                item_name       VARCHAR(100) NOT NULL,
                quantity        INTEGER     NOT NULL CHECK (quantity > 0),
                item_level      INTEGER     NOT NULL DEFAULT 1,
                item_rank       VARCHAR(20) NOT NULL DEFAULT 'common',
                price_per_item  INTEGER     NOT NULL CHECK (price_per_item > 0),
                listing_fee     INTEGER     NOT NULL DEFAULT 0,
                sale_fee        INTEGER     NOT NULL DEFAULT 0,
                status          VARCHAR(20) NOT NULL DEFAULT 'active',
                created_at      TIMESTAMP   NOT NULL DEFAULT NOW(),
                expires_at      TIMESTAMP   NOT NULL,
                completed_at    TIMESTAMP,
                cancelled_at    TIMESTAMP,
                expired_at      TIMESTAMP,
                expired_notified BOOLEAN    NOT NULL DEFAULT FALSE
            )
        """)
        cursor.execute("""
            ALTER TABLE market_listings
            ADD COLUMN IF NOT EXISTS expired_notified BOOLEAN NOT NULL DEFAULT FALSE
        """)
        cursor.execute("""
            ALTER TABLE market_listings
            ADD COLUMN IF NOT EXISTS item_level INTEGER NOT NULL DEFAULT 1
        """)
        cursor.execute("""
            ALTER TABLE market_listings
            ADD COLUMN IF NOT EXISTS item_rank VARCHAR(20) NOT NULL DEFAULT 'common'
        """)

        # -- market_transactions -------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_transactions (
                id              SERIAL PRIMARY KEY,
                listing_id      INTEGER     NOT NULL REFERENCES market_listings(id) ON DELETE RESTRICT,
                seller_vk_id    BIGINT      NOT NULL,
                buyer_vk_id     BIGINT      NOT NULL,
                item_id         INTEGER     NOT NULL REFERENCES items(id) ON DELETE RESTRICT,
                item_name       VARCHAR(100) NOT NULL,
                quantity        INTEGER     NOT NULL,
                item_level      INTEGER     NOT NULL DEFAULT 1,
                item_rank       VARCHAR(20) NOT NULL DEFAULT 'common',
                price_per_item  INTEGER     NOT NULL,
                total_price     INTEGER     NOT NULL,
                sale_fee        INTEGER     NOT NULL,
                created_at      TIMESTAMP   NOT NULL DEFAULT NOW()
            )
        """)
        cursor.execute("""
            ALTER TABLE market_transactions
            ADD COLUMN IF NOT EXISTS item_level INTEGER NOT NULL DEFAULT 1
        """)
        cursor.execute("""
            ALTER TABLE market_transactions
            ADD COLUMN IF NOT EXISTS item_rank VARCHAR(20) NOT NULL DEFAULT 'common'
        """)

        # -- npc_shop_stock -----------------------------------------------
        # Сток витрин NPC по периодам ротации.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS npc_shop_stock (
                period_key    VARCHAR(32)  NOT NULL,
                merchant_id   VARCHAR(30)  NOT NULL,
                item_id       INTEGER      NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                stock_total   INTEGER      NOT NULL DEFAULT 0,
                stock_left    INTEGER      NOT NULL DEFAULT 0,
                is_featured   BOOLEAN      NOT NULL DEFAULT FALSE,
                updated_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
                PRIMARY KEY (period_key, merchant_id, item_id)
            )
        """)

        # -- Индексы --------------------------------------------------------
        for ddl in [
            "CREATE INDEX IF NOT EXISTS idx_users_vk_id          ON users(vk_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_inventory_user   ON user_inventory(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_inventory_item   ON user_inventory(item_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_storage_user     ON user_storage(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_storage_item     ON user_storage(item_id)",
            "CREATE INDEX IF NOT EXISTS idx_items_category        ON items(category)",
            "CREATE INDEX IF NOT EXISTS idx_user_equipment_user   ON user_equipment(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_market_listings_status ON market_listings(status)",
            "CREATE INDEX IF NOT EXISTS idx_market_listings_exp    ON market_listings(expires_at)",
            "CREATE INDEX IF NOT EXISTS idx_market_listings_seller ON market_listings(seller_vk_id)",
            "CREATE INDEX IF NOT EXISTS idx_market_listings_exp_notified ON market_listings(status, expired_notified, expired_at)",
            "CREATE INDEX IF NOT EXISTS idx_market_trx_buyer       ON market_transactions(buyer_vk_id)",
            "CREATE INDEX IF NOT EXISTS idx_market_trx_seller      ON market_transactions(seller_vk_id)",
            "CREATE INDEX IF NOT EXISTS idx_npc_shop_stock_merchant_period ON npc_shop_stock(merchant_id, period_key)",
            "CREATE INDEX IF NOT EXISTS idx_user_runtime_state_key  ON user_runtime_state(state_key)",
        ]:
            cursor.execute(ddl)

        # Дефолтные настройки игры
        cursor.execute("""
            INSERT INTO game_settings (key, value)
            VALUES ('p2p_market_enabled', '1')
            ON CONFLICT (key) DO NOTHING
        """)

    # Миграция: перенести данные из старых колонок users в новые таблицы
    _migrate_legacy_schema()

    # Заполнить справочник предметов
    _seed_items()

    # Инициализировать таблицу ежедневных заданий
    init_daily_quests_table()

    # Инициализировать таблицу выбросов
    init_emission_table()

    logger.info("База данных инициализирована")


# ---------------------------------------------------------------------------
# Миграция старой схемы (на случай если таблица users уже существует
# со старыми колонками equipped_* и menu_state)
# ---------------------------------------------------------------------------

def _migrate_legacy_schema():
    """
    Переносит данные из legacy-колонок users в user_equipment/user_flags
    и затем удаляет эти колонки.
    Безопасно запускать многократно — проверяет наличие колонок перед работой.
    """
    # Список старых колонок экипировки и соответствующие им слоты
    slot_columns = {
        "equipped_weapon":       "weapon",
        "equipped_armor":        "body",   # старый единый слот брони
        "equipped_armor_head":   "head",
        "equipped_armor_body":   "body",
        "equipped_armor_legs":   "legs",
        "equipped_armor_hands":  "hands",
        "equipped_armor_feet":   "feet",
        "equipped_backpack":     "backpack",
        "equipped_device":       "device",
        "equipped_shells_bag":   "shells_bag",
        "equipped_artifact_1":   "artifact_1",
        "equipped_artifact_2":   "artifact_2",
        "equipped_artifact_3":   "artifact_3",
    }

    # Колонки сессии которые нужно просто удалить
    session_columns_remove = ["menu_state"]
    session_columns_keep = ["inventory_section"]  # Нужно для сохранения раздела инвентаря

    with db_cursor() as (cursor, conn):
        # Получаем список реально существующих колонок
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'users'
        """)
        existing = {row["column_name"] for row in cursor.fetchall()}

        # Переносим экипировку
        for col, slot in slot_columns.items():
            if col not in existing:
                continue
            cursor.execute(f"""
                INSERT INTO user_equipment (user_id, slot, item_name)
                SELECT id, %s, {col}
                FROM users
                WHERE {col} IS NOT NULL AND {col} != ''
                ON CONFLICT (user_id, slot) DO NOTHING
            """, (slot,))
            cursor.execute(f"ALTER TABLE users DROP COLUMN IF EXISTS {col}")
            logger.info("Мигрирована колонка users.%s → user_equipment.%s", col, slot)

        # Переносим newbie_kit_received в user_flags если он ещё в users
        if "newbie_kit_received" in existing:
            cursor.execute("""
                INSERT INTO user_flags (user_id, flag_name, value)
                SELECT id, 'newbie_kit_received', COALESCE(newbie_kit_received, 0)
                FROM users
                ON CONFLICT (user_id, flag_name) DO NOTHING
            """)
            # Не удаляем колонку — она нужна для обратной совместимости
            # с get_user_by_vk() который собирает плоский dict

        # Удаляем только menu_state, inventory_section оставляем
        for col in session_columns_remove:
            if col in existing:
                cursor.execute(f"ALTER TABLE users DROP COLUMN IF EXISTS {col}")
                logger.info("Удалена колонка сессии users.%s", col)

        # Добавляем новые колонки если их нет (для чистых инсталляций
        # которые уже имеют таблицу users но без новых полей)
        new_columns = [
            ("player_class",          "VARCHAR(50)"),
            ("previous_location",     "VARCHAR(50)"),
            ("hospital_treatments",   "INTEGER DEFAULT 0"),
            ("max_health_bonus",      "INTEGER DEFAULT 0"),
            ("hp_upgrade_level",      "INTEGER DEFAULT 0"),
            ("artifact_slots",        "INTEGER DEFAULT 3"),
            ("shells",                "INTEGER DEFAULT 0"),
            ("rank_tier",             "INTEGER DEFAULT 1"),
            ("is_admin",              "INTEGER DEFAULT 0"),
            ("is_banned",             "INTEGER DEFAULT 0"),
            ("ban_reason",            "TEXT"),
            ("inventory_section",     "VARCHAR(50)"),  # Текущий раздел инвентаря
        ]
        for col, definition in new_columns:
            if col not in existing:
                cursor.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {definition}")
                logger.info("Добавлена колонка users.%s", col)

        # Перенос ранга из user_flags в users.rank_tier (если ранее хранили во флагах).
        cursor.execute("""
            UPDATE users u
            SET rank_tier = GREATEST(1, COALESCE(uf.value, 1))
            FROM user_flags uf
            WHERE uf.user_id = u.id
              AND uf.flag_name = 'rank_tier'
              AND (
                  u.rank_tier IS NULL
                  OR u.rank_tier <> GREATEST(1, COALESCE(uf.value, 1))
              )
        """)

        # Нормализация: ранг не может быть < 1 или NULL.
        cursor.execute("""
            UPDATE users
            SET rank_tier = 1
            WHERE rank_tier IS NULL OR rank_tier < 1
        """)
        cursor.execute("ALTER TABLE users ALTER COLUMN rank_tier SET DEFAULT 1")
        cursor.execute("ALTER TABLE users ALTER COLUMN rank_tier SET NOT NULL")

        cursor.execute("ALTER TABLE user_inventory ADD COLUMN IF NOT EXISTS item_level INTEGER DEFAULT 1")
        cursor.execute("ALTER TABLE user_inventory ADD COLUMN IF NOT EXISTS item_rank VARCHAR(20) DEFAULT 'common'")
        cursor.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS drop_chance INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS location_drop_chances JSONB DEFAULT '{}'::jsonb")


# ---------------------------------------------------------------------------
# Справочник предметов
# ---------------------------------------------------------------------------

def _seed_items():
    """Заполнить таблицу items начальными данными."""
    items = ITEMS_POOL

    with db_cursor() as (cursor, conn):
        for item in items:
            _insert_item(cursor, item)

    logger.info("Справочник предметов заполнен")


def _balanced_item_price(category: str, price: int, attack: int = 0, defense: int = 0, rarity: str = "common") -> int:
    """Нормализовать цены боевого снаряжения, чтобы стартовые деньги не покупали mid-game комплект."""
    category = (category or "").lower()
    rarity = (rarity or "common").lower()
    price = int(price or 0)
    attack = int(attack or 0)
    defense = int(defense or 0)

    rarity_mult = {
        "common": 1.0,
        "rare": 1.25,
        "unique": 1.6,
        "legendary": 2.2,
    }.get(rarity, 1.0)

    if category in {"weapons", "rare_weapons"} and attack > 0:
        base = attack * (55 if category == "weapons" else 65)
        return max(price, int(base * rarity_mult))

    if category in {"armor", "rare_armor"} and defense > 0:
        base = defense * (45 if category == "armor" else 55)
        return max(price, int(base * rarity_mult))

    return price


def _coerce_percent(value: Any) -> int:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, int(round(num))))


def _default_location_drop_chances(category: str) -> dict[str, int]:
    category = (category or "").strip().lower()
    result: dict[str, int] = {}
    for location_id, category_map in ITEM_CATEGORY_DROP_CHANCES_BY_LOCATION.items():
        pct = _coerce_percent((category_map or {}).get(category, 0))
        if pct > 0:
            result[str(location_id)] = pct
    return result


def _normalize_location_drop_chances(location_drop_chances: Any, category: str) -> dict[str, int]:
    raw = location_drop_chances
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else {}
        except Exception:
            raw = {}
    if not isinstance(raw, dict):
        raw = {}

    result: dict[str, int] = {}
    for location_id, pct_raw in raw.items():
        key = str(location_id or "").strip()
        if not key:
            continue
        pct = _coerce_percent(pct_raw)
        if pct > 0:
            result[key] = pct

    if result:
        return result
    return _default_location_drop_chances(category)


def _resolve_drop_profile(category: str, drop_chance: Any = None, location_drop_chances: Any = None) -> tuple[int, dict[str, int]]:
    normalized_location = _normalize_location_drop_chances(location_drop_chances, category)
    if drop_chance is None:
        resolved_drop_chance = max(normalized_location.values(), default=0)
    else:
        resolved_drop_chance = _coerce_percent(drop_chance)
    return resolved_drop_chance, normalized_location


def _with_lore_description(name: str, category: str, description: str) -> str:
    """Привести описание предмета к лорному стилю Зоны."""
    base = str(description or "").strip()
    if not base:
        base = f"{name}."

    overrides = {
        "Суп с опилками": "Консерва без этикетки, от которой пахнет костром и железом. В Зоне такие банки не выбрасывают даже самые сытые.",
        "Гильза": "Тёплая латунная гильза, подобранная у свежего следа. В аномальных местах такая мелочь решает, вернёшься ли с добычей.",
        "Гильзы": "Стянутая резинкой связка гильз. Сталкеры берегут их как валюту риска у самой кромки аномалий.",
        "Душа": "Пульсирующий артефакт, от которого воздух становится плотнее. Про такие находки говорят шёпотом и прячут под тремя замками.",
        "Экзоскелет": "Тяжёлая силовая рама, скрипящая на каждом шаге. Даёт право идти туда, где без неё живут считанные секунды.",
        "Т-5000": "Собранная под дальний бой винтовка с холодным, ровным спуском. В руках терпеливого стрелка превращает открытую местность в тир.",
        "М249": "Лёгкий пулемёт с жадным аппетитом к ленте. В тесных коридорах его голос быстро глушит любые споры.",
        "ПМ": "Старый пистолет, знакомый каждому новичку у Периметра. Невелик в силе, но в Зоне надёжность ценят выше понтов.",
        "Антирад": "Горький раствор в потёртом флаконе. Не делает бессмертным, но даёт шанс дожить до безопасной койки.",
    }
    if name in overrides:
        return overrides[name]

    category = (category or "").lower().strip()
    tails = {
        "weapons": "После каждого рейда его чистят до блеска: в Зоне осечка часто звучит как приговор.",
        "rare_weapons": "Такие экземпляры ходят по рукам редко и обычно с историей, в которой кто-то не вернулся.",
        "armor": "Носится тяжело, зато даёт лишний вдох там, где воздух пахнет порохом и ржавчиной.",
        "rare_armor": "Редкая защита, собранная по кускам после чужих вылазок. Слабых мест почти не осталось.",
        "artifacts": "Тёплый на ладони артефакт с неровным фоном. Полезен, но за каждую его милость Зона обычно берёт плату.",
        "legendary_artifacts": "Легендарный артефакт из старых сталкерских баек, который вживую видели единицы.",
        "backpacks": "Лишние карманы здесь важнее красоты: путь назад почти всегда длиннее, чем казался на карте.",
        "shells_bag": "Простой с виду мешочек, без которого добыча артефактов превращается в пустой риск.",
        "meds": "Полевой расходник, который держат под рукой даже в мирных зонах. Иногда это единственная пауза между боем и тьмой.",
        "food": "Сухой паёк сталкера: без изысков, но помогает держать голову ясной и руки твёрдыми.",
        "consumables": "Одноразовая мелочь из сталкерского набора, которой часто не хватает именно в нужную минуту.",
        "other": "Обычная на вид вещь, полезность которой в Зоне понимаешь только после первой серьёзной ночи.",
        "resources": "Рабочий ресурс из сталкерского оборота. Дёшево стоит на бумаге, но на маршруте ценится иначе.",
        "trash": "Хлам с дороги, который пахнет сыростью и гарью. Иногда именно из такого мусора собирают комплект на выживание.",
    }

    tail = tails.get(category)
    if not tail:
        return base
    if base.endswith("."):
        return f"{base} {tail}"
    return f"{base}. {tail}"


def _insert_item(cursor, item: tuple):
    """Вставить один предмет. ON CONFLICT DO UPDATE обновляет всё кроме id."""
    if len(item) == 7:
        name, category, description, price, attack, defense, weight = item
        description = _with_lore_description(name, category, description)
        price = _balanced_item_price(category, price, attack, defense)
        drop_chance, location_drop_chances = _resolve_drop_profile(category)
        cursor.execute("""
            INSERT INTO items (name, category, description, price, attack, defense, weight,
                               rarity, anomaly_type, bonus_type, bonus_value,
                               drop_chance, location_drop_chances)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'common',NULL,NULL,0,%s,%s::jsonb)
            ON CONFLICT (name) DO UPDATE SET
                category=EXCLUDED.category, description=EXCLUDED.description,
                price=EXCLUDED.price, attack=EXCLUDED.attack,
                defense=EXCLUDED.defense, weight=EXCLUDED.weight,
                drop_chance=EXCLUDED.drop_chance,
                location_drop_chances=EXCLUDED.location_drop_chances
        """, (name, category, description, price, attack, defense, weight, drop_chance, json.dumps(location_drop_chances, ensure_ascii=False)))

    elif len(item) == 8:
        name, category, description, price, attack, defense, weight, backpack_bonus = item
        description = _with_lore_description(name, category, description)
        price = _balanced_item_price(category, price, attack, defense)
        drop_chance, location_drop_chances = _resolve_drop_profile(category)
        cursor.execute("""
            INSERT INTO items (name, category, description, price, attack, defense, weight,
                               backpack_bonus, rarity, anomaly_type, bonus_type, bonus_value,
                               drop_chance, location_drop_chances)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'common',NULL,NULL,0,%s,%s::jsonb)
            ON CONFLICT (name) DO UPDATE SET
                category=EXCLUDED.category, description=EXCLUDED.description,
                price=EXCLUDED.price, attack=EXCLUDED.attack,
                defense=EXCLUDED.defense, weight=EXCLUDED.weight,
                backpack_bonus=EXCLUDED.backpack_bonus,
                drop_chance=EXCLUDED.drop_chance,
                location_drop_chances=EXCLUDED.location_drop_chances
        """, (name, category, description, price, attack, defense, weight, backpack_bonus, drop_chance, json.dumps(location_drop_chances, ensure_ascii=False)))

    elif len(item) in {12, 13, 14}:
        name, category, description, price, attack, defense, weight, \
            backpack_bonus, rarity, anomaly_type, bonus_type, bonus_value = item[:12]
        drop_chance = item[12] if len(item) >= 13 else None
        location_drop_chances = item[13] if len(item) >= 14 else None
        description = _with_lore_description(name, category, description)
        price = _balanced_item_price(category, price, attack, defense, rarity)
        resolved_drop_chance, resolved_location_drop_chances = _resolve_drop_profile(
            category,
            drop_chance=drop_chance,
            location_drop_chances=location_drop_chances,
        )
        cursor.execute("""
            INSERT INTO items (name, category, description, price, attack, defense, weight,
                               backpack_bonus, rarity, anomaly_type, bonus_type, bonus_value,
                               drop_chance, location_drop_chances)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (name) DO UPDATE SET
                category=EXCLUDED.category, description=EXCLUDED.description,
                price=EXCLUDED.price, attack=EXCLUDED.attack,
                defense=EXCLUDED.defense, weight=EXCLUDED.weight,
                backpack_bonus=EXCLUDED.backpack_bonus,
                rarity=EXCLUDED.rarity, anomaly_type=EXCLUDED.anomaly_type,
                bonus_type=EXCLUDED.bonus_type, bonus_value=EXCLUDED.bonus_value,
                drop_chance=EXCLUDED.drop_chance,
                location_drop_chances=EXCLUDED.location_drop_chances
        """, (name, category, description, price, attack, defense, weight,
              backpack_bonus, rarity, anomaly_type, bonus_type, bonus_value,
              resolved_drop_chance, json.dumps(resolved_location_drop_chances, ensure_ascii=False)))
    else:
        raise ValueError(f"Unsupported item tuple format for {item[0] if item else '<empty>'}: {len(item)} fields")


# ---------------------------------------------------------------------------
# Кэш предметов (читается один раз при старте)
# ---------------------------------------------------------------------------

_items_cache: dict = {}
_items_by_category_cache: dict = {}
_shop_items_cache = None
_cache_lock = threading.Lock()


def _reset_items_cache():
    global _items_cache, _items_by_category_cache, _shop_items_cache
    with _cache_lock:
        _items_cache = {}
        _items_by_category_cache = {}
        _shop_items_cache = None


def _get_cached_items():
    global _items_cache, _items_by_category_cache, _shop_items_cache
    with _cache_lock:
        if _items_cache:
            return _items_cache, _items_by_category_cache, _shop_items_cache

        with db_cursor() as (cursor, _):
            cursor.execute("SELECT * FROM items")
            rows = cursor.fetchall()

        for row in rows:
            item = dict(row)
            _items_cache[item["name"]] = item
            cat = item["category"]
            _items_by_category_cache.setdefault(cat, []).append(item)

        _shop_items_cache = {
            None:      list(_items_cache.values()),
            "weapons": _items_by_category_cache.get("weapons", []),
            "armor":   _items_by_category_cache.get("armor", []),
            "resources": _items_by_category_cache.get("resources", []),
            "shells_bag": _items_by_category_cache.get("shells_bag", []),
        }

        logger.info("Кэш предметов загружен: %d предметов", len(_items_cache))
        return _items_cache, _items_by_category_cache, _shop_items_cache


# ---------------------------------------------------------------------------
# Вспомогательная функция — собрать плоский dict пользователя
# Совместим со старым кодом: все поля экипировки доступны как
# user["equipped_weapon"], user["equipped_armor_head"] и т.д.
# ---------------------------------------------------------------------------

def _build_user_dict(user_row: dict, equipment_rows: list, flags_rows: list) -> dict:
    """
    Собирает плоский словарь пользователя из нормализованных таблиц.
    Обратная совместимость: player.py и хендлеры видят те же ключи что раньше.
    """
    result = dict(user_row)

    # Экипировка: slot → item_name
    slot_to_field = {
        "weapon":     "equipped_weapon",
        "head":       "equipped_armor_head",
        "body":       "equipped_armor_body",
        "legs":       "equipped_armor_legs",
        "hands":      "equipped_armor_hands",
        "feet":       "equipped_armor_feet",
        "backpack":   "equipped_backpack",
        "device":     "equipped_device",
        "shells_bag": "equipped_shells_bag",
        # legacy поле — оставляем для совместимости
        "armor":      "equipped_armor",
    }
    for idx in range(1, config.MAX_ARTIFACT_SLOTS + 1):
        slot_to_field[f"artifact_{idx}"] = f"equipped_artifact_{idx}"
    # Дефолты
    for field in slot_to_field.values():
        result.setdefault(field, None)

    for row in equipment_rows:
        field = slot_to_field.get(row["slot"])
        if field:
            result[field] = row["item_name"]

    # Флаги
    for row in flags_rows:
        flag_name = row["flag_name"]
        # rank_tier хранится в users, не даём устаревшему флагу переопределять значение.
        if flag_name == "rank_tier":
            continue
        result[flag_name] = row["value"]

    result.setdefault("newbie_kit_received", 0)
    # inventory_section хранится в основной таблице users
    result.setdefault("inventory_section", None)
    return result


# ---------------------------------------------------------------------------
# Пользователи — CRUD
# ---------------------------------------------------------------------------

def get_user_by_vk(vk_id: int) -> dict | None:
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT * FROM users WHERE vk_id = %s", (vk_id,))
        user_row = cursor.fetchone()
        if not user_row:
            return None

        cursor.execute(
            "SELECT slot, item_name FROM user_equipment WHERE user_id = %s",
            (user_row["id"],),
        )
        equipment = cursor.fetchall()

        cursor.execute(
            "SELECT flag_name, value FROM user_flags WHERE user_id = %s",
            (user_row["id"],),
        )
        flags = cursor.fetchall()

    return _build_user_dict(dict(user_row), list(equipment), list(flags))


def create_user(vk_id: int, name: str) -> dict:
    with db_cursor() as (cursor, _):
        cursor.execute("""
            INSERT INTO users (vk_id, name, location, health, energy, radiation,
                               money, level, experience, strength, stamina,
                               perception, luck, armor_defense, max_weight)
            VALUES (%s,%s,'город',100,100,0,%s,1,0,4,4,4,4,0,20)
            ON CONFLICT (vk_id) DO NOTHING
        """, (vk_id, name, config.START_MONEY))
    return get_user_by_vk(vk_id)


def update_user_location(vk_id: int, location: str):
    with db_cursor() as (cursor, _):
        cursor.execute(
            "UPDATE users SET location = %s WHERE vk_id = %s",
            (location, vk_id),
        )


# Поля которые разрешено обновлять через update_user_stats()
_ALLOWED_USER_FIELDS = frozenset({
    "health", "energy", "radiation", "money",
    "level", "experience",
    "strength", "stamina", "perception", "luck",
    "armor_defense", "max_weight", "max_health_bonus",
    "artifact_slots", "shells",
    "player_class", "location", "previous_location",
    "hospital_treatments", "newbie_kit_received",
    "is_admin", "is_banned", "ban_reason",
    "inventory_section",  # Текущий раздел инвентаря
})

# Поля экипировки — обновляются через user_equipment
_EQUIPMENT_FIELDS = {
    "equipped_weapon":       "weapon",
    "equipped_armor":        "armor",
    "equipped_armor_head":   "head",
    "equipped_armor_body":   "body",
    "equipped_armor_legs":   "legs",
    "equipped_armor_hands":  "hands",
    "equipped_armor_feet":   "feet",
    "equipped_backpack":     "backpack",
    "equipped_device":       "device",
    "equipped_shells_bag":   "shells_bag",
}
for _idx in range(1, config.MAX_ARTIFACT_SLOTS + 1):
    _EQUIPMENT_FIELDS[f"equipped_artifact_{_idx}"] = f"artifact_{_idx}"


def update_user_stats(vk_id: int, **fields):
    """
    Обновить любые поля пользователя.
    Принимает именованные аргументы — добавление нового поля
    не требует трогать сигнатуру функции.

    Поля экипировки (equipped_*) автоматически роутятся в user_equipment.
    Пустая строка "" или None снимает предмет.

    Пример:
        update_user_stats(vk_id, health=80, money=500)
        update_user_stats(vk_id, equipped_weapon="АК-74")
        update_user_stats(vk_id, equipped_weapon="")  # снять оружие
    """
    if not fields:
        return

    user_fields = {}
    equipment_updates = {}  # {slot: item_name or None}

    for key, value in fields.items():
        if key in _EQUIPMENT_FIELDS:
            slot = _EQUIPMENT_FIELDS[key]
            # Пустая строка = снять предмет
            equipment_updates[slot] = None if value == "" else value
        elif key in _ALLOWED_USER_FIELDS:
            user_fields[key] = value
        else:
            logger.warning("update_user_stats: неизвестное поле '%s' — пропущено", key)

    with db_cursor() as (cursor, _):
        # Получаем internal id
        cursor.execute("SELECT id FROM users WHERE vk_id = %s", (vk_id,))
        row = cursor.fetchone()
        if not row:
            logger.error("update_user_stats: пользователь vk_id=%s не найден", vk_id)
            return
        user_id = row["id"]

        # Обновляем основную таблицу
        if user_fields:
            sets = ", ".join(f"{k} = %s" for k in user_fields)
            params = list(user_fields.values()) + [vk_id]
            cursor.execute(f"UPDATE users SET {sets} WHERE vk_id = %s", params)

        # Обновляем экипировку
        for slot, item_name in equipment_updates.items():
            if item_name is None:
                cursor.execute(
                    "DELETE FROM user_equipment WHERE user_id = %s AND slot = %s",
                    (user_id, slot),
                )
            else:
                cursor.execute("""
                    INSERT INTO user_equipment (user_id, slot, item_name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, slot) DO UPDATE SET item_name = EXCLUDED.item_name
                """, (user_id, slot, item_name))


# ---------------------------------------------------------------------------
# Инвентарь
# ---------------------------------------------------------------------------

def get_user_inventory(vk_id: int) -> list[dict]:
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT id, level FROM users WHERE vk_id = %s", (vk_id,))
        row = cursor.fetchone()
        if not row:
            return []
        cursor.execute("""
            SELECT i.name, i.category, i.description, i.price,
                   i.attack, i.defense, i.weight, i.backpack_bonus,
                   i.rarity, i.anomaly_type, i.bonus_type, i.bonus_value,
                   ui.quantity, ui.item_level, ui.item_rank
            FROM user_inventory ui
            JOIN items i ON ui.item_id = i.id
            WHERE ui.user_id = %s
        """, (row["id"],))
        result = []
        player_level = int(row.get("level", 1) or 1)
        for r in cursor.fetchall():
            item = dict(r)
            if is_weapon(item):
                stored_level = int(item.get("item_level") or get_weapon_required_level(item) or 1)
                min_level = max(1, int(get_weapon_required_level(item) or 1))
                max_level = max(min_level, player_level + 3)
                item_level = max(min_level, min(max_level, stored_level))
                item_rank = normalize_weapon_rank(item.get("item_rank"), item)
                item["item_level"] = item_level
                item["item_rank"] = item_rank
                item["required_level"] = get_weapon_required_level(item)
                item["base_attack"] = int(item.get("attack", 0) or 0)
                item["attack"] = calc_weapon_attack(item, item_level, item_rank)
            result.append(item)
        return result


def get_user_storage(vk_id: int) -> list[dict]:
    """Получить содержимое шкафа в убежище."""
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT id FROM users WHERE vk_id = %s", (vk_id,))
        row = cursor.fetchone()
        if not row:
            return []
        cursor.execute(
            """
            SELECT i.name, i.category, i.description, i.price,
                   i.attack, i.defense, i.weight, i.backpack_bonus,
                   i.rarity, i.anomaly_type, i.bonus_type, i.bonus_value,
                   us.quantity
            FROM user_storage us
            JOIN items i ON us.item_id = i.id
            WHERE us.user_id = %s
            ORDER BY i.category, i.name
            """,
            (row["id"],),
        )
        return [dict(r) for r in cursor.fetchall()]


def get_user_storage_load(vk_id: int) -> dict:
    """Текущее заполнение шкафа (по сумме quantity)."""
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT id FROM users WHERE vk_id = %s", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return {"current": 0, "capacity": int(config.SHELTER_STORAGE_CAPACITY)}
        cursor.execute(
            """
            SELECT COALESCE(SUM(quantity), 0) AS qty
            FROM user_storage
            WHERE user_id = %s
            """,
            (user["id"],),
        )
        row = cursor.fetchone() or {}
        current = int(row.get("qty", 0) or 0)
        return {"current": current, "capacity": int(config.SHELTER_STORAGE_CAPACITY)}


def move_item_to_storage_transaction(vk_id: int, item_name: str, quantity: int = 1) -> dict:
    """Переложить предмет из инвентаря в шкаф (атомарно)."""
    safe_qty = max(1, int(quantity or 1))
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT id FROM users WHERE vk_id = %s FOR UPDATE", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return {"success": False, "message": "Пользователь не найден."}
        user_id = int(user["id"])

        cursor.execute("SELECT id FROM items WHERE name = %s", (item_name,))
        item = cursor.fetchone()
        if not item:
            return {"success": False, "message": f"Предмет '{item_name}' не найден."}
        item_id = int(item["id"])

        cursor.execute(
            """
            SELECT quantity
            FROM user_inventory
            WHERE user_id = %s AND item_id = %s
            FOR UPDATE
            """,
            (user_id, item_id),
        )
        inv_row = cursor.fetchone()
        have_qty = int((inv_row or {}).get("quantity", 0) or 0)
        if have_qty < safe_qty:
            return {"success": False, "message": f"Не хватает '{item_name}': нужно {safe_qty}, у тебя {have_qty}."}

        cursor.execute(
            """
            SELECT quantity
            FROM user_storage
            WHERE user_id = %s
            FOR UPDATE
            """,
            (user_id,),
        )
        storage_qty = sum(int(r.get("quantity", 0) or 0) for r in cursor.fetchall())
        capacity = int(config.SHELTER_STORAGE_CAPACITY)
        if storage_qty + safe_qty > capacity:
            return {
                "success": False,
                "message": f"Шкаф переполнен: {storage_qty}/{capacity}. Освободи место.",
            }

        cursor.execute(
            """
            UPDATE user_inventory
            SET quantity = quantity - %s
            WHERE user_id = %s AND item_id = %s AND quantity >= %s
            """,
            (safe_qty, user_id, item_id, safe_qty),
        )
        cursor.execute(
            """
            DELETE FROM user_inventory
            WHERE user_id = %s AND item_id = %s AND quantity <= 0
            """,
            (user_id, item_id),
        )
        cursor.execute(
            """
            INSERT INTO user_storage (user_id, item_id, quantity)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, item_id)
            DO UPDATE SET quantity = user_storage.quantity + EXCLUDED.quantity
            """,
            (user_id, item_id, safe_qty),
        )

    return {"success": True, "message": f"Переложено в шкаф: {item_name} x{safe_qty}"}


def move_item_from_storage_transaction(vk_id: int, item_name: str, quantity: int = 1) -> dict:
    """Забрать предмет из шкафа в инвентарь (атомарно)."""
    safe_qty = max(1, int(quantity or 1))
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT id, level FROM users WHERE vk_id = %s FOR UPDATE", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return {"success": False, "message": "Пользователь не найден."}
        user_id = int(user["id"])
        player_level = int(user.get("level", 1) or 1)

        cursor.execute("SELECT * FROM items WHERE name = %s", (item_name,))
        item = cursor.fetchone()
        if not item:
            return {"success": False, "message": f"Предмет '{item_name}' не найден."}
        item_data = dict(item)
        item_id = int(item["id"])

        cursor.execute(
            """
            SELECT quantity
            FROM user_storage
            WHERE user_id = %s AND item_id = %s
            FOR UPDATE
            """,
            (user_id, item_id),
        )
        st_row = cursor.fetchone()
        have_qty = int((st_row or {}).get("quantity", 0) or 0)
        if have_qty < safe_qty:
            return {"success": False, "message": f"В шкафу недостаточно '{item_name}': {have_qty}."}

        item_level = 1
        item_rank = normalize_weapon_rank(None, item_data)
        if is_weapon(item_data):
            item_level = clamp_weapon_level(player_level, player_level, item_data)
            item_rank = normalize_weapon_rank(roll_weapon_rank(player_level, item_data), item_data)

        cursor.execute(
            """
            UPDATE user_storage
            SET quantity = quantity - %s
            WHERE user_id = %s AND item_id = %s AND quantity >= %s
            """,
            (safe_qty, user_id, item_id, safe_qty),
        )
        cursor.execute(
            """
            DELETE FROM user_storage
            WHERE user_id = %s AND item_id = %s AND quantity <= 0
            """,
            (user_id, item_id),
        )
        cursor.execute(
            """
            INSERT INTO user_inventory (user_id, item_id, quantity, item_level, item_rank)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, item_id)
            DO UPDATE SET
                quantity = user_inventory.quantity + EXCLUDED.quantity,
                item_level = GREATEST(user_inventory.item_level, EXCLUDED.item_level),
                item_rank = CASE
                    WHEN array_position(ARRAY['common','uncommon','rare','epic','legendary'], EXCLUDED.item_rank)
                       > array_position(ARRAY['common','uncommon','rare','epic','legendary'], COALESCE(user_inventory.item_rank, 'common'))
                    THEN EXCLUDED.item_rank
                    ELSE user_inventory.item_rank
                END
            """,
            (user_id, item_id, safe_qty, item_level, item_rank),
        )

    return {"success": True, "message": f"Забрано из шкафа: {item_name} x{safe_qty}"}


def add_item_to_inventory(
    vk_id: int,
    item_name: str,
    quantity: int = 1,
    item_level: int | None = None,
    item_rank: str | None = None,
) -> bool:
    try:
        safe_qty = int(quantity)
    except (TypeError, ValueError):
        return False
    if safe_qty <= 0:
        return False

    with db_cursor() as (cursor, _):
        cursor.execute("SELECT id, level FROM users WHERE vk_id = %s", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return False

        cursor.execute("SELECT * FROM items WHERE name = %s", (item_name,))
        item = cursor.fetchone()
        if not item:
            return False

        item_data = dict(item)
        player_level = int(user.get("level", 1) or 1)
        if is_weapon(item_data):
            item_level = clamp_weapon_level(item_level or player_level, player_level, item_data)
            item_rank = normalize_weapon_rank(item_rank or roll_weapon_rank(player_level, item_data), item_data)
        else:
            item_level = 1
            item_rank = normalize_weapon_rank(item_rank, item_data)

        cursor.execute("""
            INSERT INTO user_inventory (user_id, item_id, quantity, item_level, item_rank)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, item_id)
            DO UPDATE SET
                quantity = user_inventory.quantity + EXCLUDED.quantity,
                item_level = GREATEST(user_inventory.item_level, EXCLUDED.item_level),
                item_rank = CASE
                    WHEN array_position(ARRAY['common','uncommon','rare','epic','legendary'], EXCLUDED.item_rank)
                       > array_position(ARRAY['common','uncommon','rare','epic','legendary'], COALESCE(user_inventory.item_rank, 'common'))
                    THEN EXCLUDED.item_rank
                    ELSE user_inventory.item_rank
                END
        """, (user["id"], item["id"], safe_qty, item_level, item_rank))
    return True


def remove_item_from_inventory(vk_id: int, item_name: str, quantity: int = 1) -> bool:
    try:
        safe_qty = int(quantity)
    except (TypeError, ValueError):
        return False
    if safe_qty <= 0:
        return False

    with db_cursor() as (cursor, _):
        cursor.execute("SELECT id FROM users WHERE vk_id = %s", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return False

        cursor.execute("SELECT id FROM items WHERE name = %s", (item_name,))
        item = cursor.fetchone()
        if not item:
            return False

        cursor.execute("""
            UPDATE user_inventory
            SET quantity = quantity - %s
            WHERE user_id = %s AND item_id = %s AND quantity >= %s
        """, (safe_qty, user["id"], item["id"], safe_qty))
        if cursor.rowcount <= 0:
            return False

        cursor.execute("""
            DELETE FROM user_inventory
            WHERE user_id = %s AND item_id = %s AND quantity <= 0
        """, (user["id"], item["id"]))
    return True


def craft_item_transaction(
    vk_id: int,
    ingredients: list[tuple[str, int]],
    result_item_name: str,
    result_quantity: int = 1,
) -> dict:
    """
    Крафт предмета атомарно:
    - проверка наличия ингредиентов
    - списание ингредиентов
    - добавление результата
    """
    if not ingredients:
        return {"success": False, "message": "Рецепт пустой."}
    if not result_item_name:
        return {"success": False, "message": "Не указан результат крафта."}

    safe_ingredients = [(str(name), max(1, int(qty or 1))) for name, qty in ingredients]
    safe_result_qty = max(1, int(result_quantity or 1))

    with db_cursor() as (cursor, _):
        cursor.execute("SELECT id, level FROM users WHERE vk_id = %s FOR UPDATE", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return {"success": False, "message": "Пользователь не найден."}
        user_id = int(user["id"])
        player_level = int(user.get("level", 1) or 1)

        ingredient_rows: list[dict[str, int | str]] = []
        for item_name, required_qty in safe_ingredients:
            cursor.execute("SELECT id FROM items WHERE name = %s", (item_name,))
            item_row = cursor.fetchone()
            if not item_row:
                return {"success": False, "message": f"Ингредиент '{item_name}' не найден в базе."}

            item_id = int(item_row["id"])
            cursor.execute(
                """
                SELECT quantity
                FROM user_inventory
                WHERE user_id = %s AND item_id = %s
                FOR UPDATE
                """,
                (user_id, item_id),
            )
            inv = cursor.fetchone()
            have_qty = int((inv or {}).get("quantity", 0) or 0)
            if have_qty < required_qty:
                return {
                    "success": False,
                    "message": f"Не хватает '{item_name}': нужно {required_qty}, у тебя {have_qty}.",
                }

            ingredient_rows.append({
                "name": item_name,
                "item_id": item_id,
                "required_qty": required_qty,
            })

        cursor.execute("SELECT * FROM items WHERE name = %s", (result_item_name,))
        result_item_row = cursor.fetchone()
        if not result_item_row:
            return {"success": False, "message": f"Результат '{result_item_name}' не найден в базе."}

        result_item = dict(result_item_row)
        result_item_level = 1
        result_item_rank = normalize_weapon_rank(None, result_item)
        if is_weapon(result_item):
            result_item_level = clamp_weapon_level(player_level, player_level, result_item)
            result_item_rank = normalize_weapon_rank(roll_weapon_rank(player_level, result_item), result_item)

        for row in ingredient_rows:
            cursor.execute(
                """
                UPDATE user_inventory
                SET quantity = quantity - %s
                WHERE user_id = %s AND item_id = %s AND quantity >= %s
                """,
                (row["required_qty"], user_id, row["item_id"], row["required_qty"]),
            )

        cursor.execute(
            """
            DELETE FROM user_inventory
            WHERE user_id = %s AND item_id = ANY(%s) AND quantity <= 0
            """,
            (user_id, [int(r["item_id"]) for r in ingredient_rows]),
        )

        cursor.execute(
            """
            INSERT INTO user_inventory (user_id, item_id, quantity, item_level, item_rank)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, item_id)
            DO UPDATE SET
                quantity = user_inventory.quantity + EXCLUDED.quantity,
                item_level = GREATEST(user_inventory.item_level, EXCLUDED.item_level),
                item_rank = CASE
                    WHEN array_position(ARRAY['common','uncommon','rare','epic','legendary'], EXCLUDED.item_rank)
                       > array_position(ARRAY['common','uncommon','rare','epic','legendary'], COALESCE(user_inventory.item_rank, 'common'))
                    THEN EXCLUDED.item_rank
                    ELSE user_inventory.item_rank
                END
            """,
            (user_id, int(result_item["id"]), safe_result_qty, result_item_level, result_item_rank),
        )

    return {
        "success": True,
        "message": f"Скрафчено: {result_item_name} x{safe_result_qty}",
    }


def drop_item_from_inventory(vk_id: int, item_name: str, quantity: int = 1) -> dict:
    try:
        safe_qty = int(quantity)
    except (TypeError, ValueError):
        return {"success": False, "message": "Количество должно быть числом"}
    if safe_qty <= 0:
        return {"success": False, "message": "Количество должно быть больше нуля"}

    with db_cursor() as (cursor, _):
        cursor.execute("SELECT id FROM users WHERE vk_id = %s", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return {"success": False, "message": "Пользователь не найден"}

        cursor.execute("SELECT id FROM items WHERE name = %s", (item_name,))
        item = cursor.fetchone()
        if not item:
            return {"success": False, "message": f"Предмет '{item_name}' не найден"}

        cursor.execute("""
            SELECT quantity FROM user_inventory
            WHERE user_id = %s AND item_id = %s
        """, (user["id"], item["id"]))
        inv = cursor.fetchone()
        if not inv:
            return {"success": False, "message": f"У тебя нет '{item_name}'"}
        if inv["quantity"] < safe_qty:
            return {"success": False, "message": f"У тебя только {inv['quantity']} шт."}

        if inv["quantity"] == safe_qty:
            cursor.execute(
                "DELETE FROM user_inventory WHERE user_id = %s AND item_id = %s",
                (user["id"], item["id"]),
            )
        else:
            cursor.execute("""
                UPDATE user_inventory SET quantity = quantity - %s
                WHERE user_id = %s AND item_id = %s
            """, (safe_qty, user["id"], item["id"]))

    return {"success": True, "message": f"✅ Ты выбросил {safe_qty} шт. '{item_name}'"}


# ---------------------------------------------------------------------------
# NPC магазины (не P2P): ротация, редкий товар, сток, ивенты скупки
# ---------------------------------------------------------------------------

NPC_MERCHANT_SOLDIER = "soldier"
NPC_MERCHANT_SCIENTIST = "scientist"
NPC_MERCHANT_TRADER = "trader"

_NPC_SHOPS = {
    NPC_MERCHANT_SOLDIER: {"categories": ("weapons", "armor")},
    NPC_MERCHANT_SCIENTIST: {"categories": ("meds", "food")},
    # Барыга продаёт снаряжение и припасы, но артефакты только выкупает.
    NPC_MERCHANT_TRADER: {"categories": ("weapons", "rare_weapons", "armor", "backpacks", "meds", "food")},
}
_TRADER_BLOCKED_RARITIES = frozenset({"legendary"})
_TRADER_BUY_BLOCKED_CATEGORIES = frozenset({"artifacts", "rare_artifacts", "legendary_artifacts"})

_SHOP_EVENT_POOL = [
    {
        "id": "soldier_artifacts",
        "merchant_id": NPC_MERCHANT_SOLDIER,
        "categories": ("artifacts",),
        "sell_bonus_pct": 10,
        "title": "Сегодня военный принимает артефакты дороже (+10%).",
    },
    {
        "id": "scientist_meds",
        "merchant_id": NPC_MERCHANT_SCIENTIST,
        "categories": ("meds",),
        "sell_bonus_pct": 10,
        "title": "Сегодня учёный скупает медикаменты по повышенной цене (+10%).",
    },
    {
        "id": "trader_artifacts",
        "merchant_id": NPC_MERCHANT_TRADER,
        "categories": ("artifacts",),
        "sell_bonus_pct": 10,
        "title": "Сегодня барыга берёт артефакты по повышенной цене (+10%).",
    },
]


def _clamp(value: float, floor_value: float, ceil_value: float) -> float:
    return max(floor_value, min(ceil_value, value))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _get_shop_period_start(now_utc: datetime | None = None) -> datetime:
    now_utc = now_utc or _utc_now()
    rotation = max(1, int(config.SHOP_ROTATION_HOURS))
    slot_hour = (now_utc.hour // rotation) * rotation
    return now_utc.replace(hour=slot_hour, minute=0, second=0, microsecond=0)


def _get_shop_period_key(now_utc: datetime | None = None) -> str:
    return _get_shop_period_start(now_utc).strftime("%Y%m%d%H")


def _seed_int(seed: str) -> int:
    return int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16], 16)


def _get_active_shop_event(now_utc: datetime | None = None) -> dict:
    now_utc = now_utc or _utc_now()
    day_key = now_utc.strftime("%Y-%m-%d")
    idx = _seed_int(f"shop_event:{day_key}") % len(_SHOP_EVENT_POOL)
    return _SHOP_EVENT_POOL[idx]


def get_shop_event_text(merchant_id: str | None = None) -> str:
    event = _get_active_shop_event()
    if merchant_id and event["merchant_id"] != merchant_id:
        return ""
    return event["title"]


def _get_sell_event_bonus_pct(merchant_id: str | None, item_category: str | None) -> int:
    if not merchant_id or not item_category:
        return 0
    event = _get_active_shop_event()
    if event["merchant_id"] != merchant_id:
        return 0
    if item_category not in event["categories"]:
        return 0
    return int(event["sell_bonus_pct"])


def _get_shop_candidates(merchant_id: str, category: str | None = None, rarity: str | None = None) -> list[dict]:
    shop_info = _NPC_SHOPS.get(merchant_id, {})
    allowed_categories = set(shop_info.get("categories", ()))
    if category and category not in allowed_categories:
        return []

    _, by_cat, _ = _get_cached_items()

    categories = [category] if category else list(allowed_categories)
    result: list[dict] = []
    seen_names: set[str] = set()

    for cat in categories:
        for row in by_cat.get(cat, []):
            name = row.get("name")
            if not name or name in seen_names:
                continue
            item_rarity = (row.get("rarity") or "common").lower()
            # Барыга пока не продаёт легендарные предметы.
            if merchant_id == NPC_MERCHANT_TRADER and item_rarity in _TRADER_BLOCKED_RARITIES:
                continue
            if rarity and (row.get("rarity") or "common").lower() != rarity.lower():
                continue
            result.append(dict(row))
            seen_names.add(name)
    return result


def _pick_featured_item(merchant_id: str, candidates: list[dict], now_utc: datetime | None = None) -> dict | None:
    if not candidates:
        return None
    now_utc = now_utc or _utc_now()
    day_key = now_utc.strftime("%Y-%m-%d")
    eligible = [c for c in candidates if (c.get("rarity") or "common").lower() in {"rare", "unique", "legendary"}]
    if not eligible:
        eligible = sorted(candidates, key=lambda x: int(x.get("price") or 0), reverse=True)[:max(1, len(candidates) // 3)]
    eligible = sorted(eligible, key=lambda x: (x.get("name") or ""))
    idx = _seed_int(f"shop_featured:{merchant_id}:{day_key}") % len(eligible)
    return eligible[idx]


def _initial_shop_stock(item: dict, is_featured: bool = False) -> int:
    rarity = (item.get("rarity") or "common").lower()
    if rarity == "legendary":
        stock = config.SHOP_STOCK_LEGENDARY
    elif rarity == "unique":
        stock = config.SHOP_STOCK_UNIQUE
    elif rarity == "rare":
        stock = config.SHOP_STOCK_RARE
    else:
        stock = config.SHOP_STOCK_DEFAULT
    if is_featured:
        stock += 1
    return max(1, int(stock))


def _ensure_shop_stock_rows_tx(cursor, period_key: str, merchant_id: str, items: list[dict], featured_item_id: int | None):
    for item in items:
        item_id = int(item["id"])
        is_featured = (featured_item_id is not None and item_id == featured_item_id)
        stock_total = _initial_shop_stock(item, is_featured=is_featured)
        cursor.execute(
            """
            INSERT INTO npc_shop_stock (period_key, merchant_id, item_id, stock_total, stock_left, is_featured, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (period_key, merchant_id, item_id) DO NOTHING
            """,
            (period_key, merchant_id, item_id, stock_total, stock_total, is_featured),
        )


def _calc_shop_buy_price(base_price: int, is_featured: bool = False) -> tuple[int, int]:
    mult = 1.0
    if is_featured:
        mult -= max(0, int(config.SHOP_FEATURED_DISCOUNT_PCT)) / 100.0
    mult = _clamp(mult, config.SHOP_BUY_MULT_FLOOR, config.SHOP_BUY_MULT_CEIL)
    return max(1, int(base_price * mult)), int(round((1.0 - mult) * 100))


def get_npc_shop_assortment(
    merchant_id: str,
    category: str | None = None,
    limit: int = 10,
    rarity: str | None = None,
    player_level: int | None = None,
    viewer_vk_id: int | None = None,
) -> dict:
    """
    Получить текущую витрину NPC магазина:
    ротация по часу, редкий товар дня и ограниченный сток.
    """
    candidates = _get_shop_candidates(merchant_id, category=category, rarity=rarity)
    if not candidates:
        return {"items": [], "period_key": _get_shop_period_key(), "event_text": get_shop_event_text(merchant_id)}

    now_utc = _utc_now()
    period_key = _get_shop_period_key(now_utc)
    featured_item = _pick_featured_item(merchant_id, _get_shop_candidates(merchant_id), now_utc=now_utc)
    featured_item_id = int(featured_item["id"]) if featured_item else None

    rng = random.Random(_seed_int(f"shop_rotate:{merchant_id}:{category or 'all'}:{rarity or 'all'}:{period_key}"))
    ordered = list(candidates)
    rng.shuffle(ordered)

    picked = ordered[: max(1, int(limit))]
    if featured_item_id is not None and all(int(i["id"]) != featured_item_id for i in picked):
        featured_in_scope = next((i for i in candidates if int(i["id"]) == featured_item_id), None)
        if featured_in_scope:
            if len(picked) >= limit:
                picked[-1] = featured_in_scope
            else:
                picked.append(featured_in_scope)

    with db_cursor() as (cursor, _):
        _ensure_shop_stock_rows_tx(cursor, period_key, merchant_id, picked, featured_item_id)
        item_ids = [int(i["id"]) for i in picked]
        cursor.execute(
            """
            SELECT item_id, stock_left, is_featured
            FROM npc_shop_stock
            WHERE period_key = %s AND merchant_id = %s AND item_id = ANY(%s)
            """,
            (period_key, merchant_id, item_ids),
        )
        stock_rows = {int(r["item_id"]): dict(r) for r in cursor.fetchall()}

    result_items = []
    for item in picked:
        item_id = int(item["id"])
        stock = stock_rows.get(item_id, {})
        stock_left = int(stock.get("stock_left", 0))
        is_featured = bool(stock.get("is_featured", False))
        dynamic_price, discount_pct = _calc_shop_buy_price(int(item.get("price") or 0), is_featured=is_featured)
        row = dict(item)
        row["base_price"] = int(item.get("price") or 0)
        row["price"] = dynamic_price
        row["stock_left"] = stock_left
        row["is_featured"] = is_featured
        row["discount_pct"] = max(0, discount_pct)
        if is_weapon(row):
            seed = f"shop_weapon_level:{period_key}:{merchant_id}:{item_id}:{int(viewer_vk_id or 0)}"
            effective_player_level = max(1, int(player_level or get_weapon_required_level(row)))
            item_level = roll_shop_weapon_level(
                effective_player_level,
                row,
                spread=2,
                seed_key=seed,
            )
            row["item_level"] = item_level
            row["required_level"] = get_weapon_required_level(row)
            row["base_attack"] = int(row.get("attack", 0) or 0)
            row["attack"] = calc_weapon_attack(row, item_level, normalize_weapon_rank(None, row))
        result_items.append(row)

    return {
        "items": result_items,
        "period_key": period_key,
        "event_text": get_shop_event_text(merchant_id),
    }


def get_npc_sell_price_preview(item_name: str, merchant_id: str | None, sell_bonus_pct: int = 0) -> dict | None:
    item = get_item_by_name(item_name)
    if not item:
        return None
    base_price = int(item.get("price") or 0) // 2
    event_bonus = _get_sell_event_bonus_pct(merchant_id, (item.get("category") or "").lower())
    total_mult = 1.0 + (sell_bonus_pct + event_bonus) / 100.0
    total_mult = _clamp(total_mult, config.SHOP_SELL_MULT_FLOOR, config.SHOP_SELL_MULT_CEIL)
    return {
        "base_price": base_price,
        "sell_price": max(1, int(base_price * total_mult)),
        "event_bonus_pct": event_bonus,
        "total_mult": total_mult,
    }


# ---------------------------------------------------------------------------
# Атомарные операции покупки / продажи
# ---------------------------------------------------------------------------

def buy_item_transaction(vk_id: int, item_name: str, merchant_id: str | None = None) -> dict:
    """
    Купить предмет. Атомарно: деньги списываются и предмет добавляется
    в одной транзакции — нельзя потерять деньги без предмета.
    Возвращает {"success": bool, "message": str, "price": int}
    """
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT * FROM items WHERE name = %s", (item_name,))
        item_row = cursor.fetchone()
        if not item_row:
            return {"success": False, "message": f"Предмет '{item_name}' не найден"}
        item_data = dict(item_row)

        cursor.execute("SELECT id, money, level FROM users WHERE vk_id = %s FOR UPDATE", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return {"success": False, "message": "Пользователь не найден"}
        player_level = int(user.get("level", 1) or 1)

        if is_weapon(item_data):
            required_level = get_weapon_required_level(item_data)
            if required_level > player_level + 3:
                return {
                    "success": False,
                    "message": (
                        f"{item_name} требует минимум {required_level} уровень владения оружием.\n"
                        f"Твой уровень: {player_level}. Ищи оружие своего эшелона или прокачайся."
                    ),
                }

        is_featured = False
        stock_left_after = None
        period_key = None

        if merchant_id:
            item_category = (item_data.get("category") or "").lower()
            if merchant_id == NPC_MERCHANT_TRADER and item_category in _TRADER_BUY_BLOCKED_CATEGORIES:
                return {"success": False, "message": "Барыга артефакты не продаёт. Только выкупает найденное."}
            item_rarity = (item_data.get("rarity") or "common").lower()
            if merchant_id == NPC_MERCHANT_TRADER and item_rarity in _TRADER_BLOCKED_RARITIES:
                return {"success": False, "message": "Легендарные предметы у Барыги пока не продаются."}
            period_key = _get_shop_period_key()
            cursor.execute(
                """
                SELECT stock_left, is_featured
                FROM npc_shop_stock
                WHERE period_key = %s AND merchant_id = %s AND item_id = %s
                FOR UPDATE
                """,
                (period_key, merchant_id, item_data["id"]),
            )
            stock_row = cursor.fetchone()
            if not stock_row:
                return {
                    "success": False,
                    "message": "Ассортимент обновился. Сначала открой витрину магазина заново.",
                }
            if int(stock_row["stock_left"]) <= 0:
                return {"success": False, "message": "Товар закончился. Жди следующую ротацию витрины."}
            is_featured = bool(stock_row["is_featured"])

        price, _ = _calc_shop_buy_price(int(item_data.get("price") or 0), is_featured=is_featured)
        have = int(user.get("money") or 0)
        if have < price:
            return {
                "success": False,
                "message": f"Не хватает денег. Нужно {price} руб., у тебя {have} руб.",
            }

        cursor.execute(
            """
            UPDATE users
            SET money = money - %s
            WHERE id = %s
            RETURNING money
            """,
            (price, user["id"]),
        )
        new_balance = int(cursor.fetchone()["money"])

        inv_level = 1
        inv_rank = normalize_weapon_rank(None, item_data)
        if is_weapon(item_data):
            if merchant_id:
                seed = f"shop_weapon_level:{period_key}:{merchant_id}:{item_data['id']}:{vk_id}"
                inv_level = roll_shop_weapon_level(
                    player_level,
                    item_data,
                    spread=2,
                    seed_key=seed,
                )
            else:
                inv_level = clamp_weapon_level(player_level, player_level, item_data)
            inv_rank = roll_weapon_rank(player_level, item_data)

        cursor.execute(
            """
            INSERT INTO user_inventory (user_id, item_id, quantity, item_level, item_rank)
            VALUES (%s, %s, 1, %s, %s)
            ON CONFLICT (user_id, item_id)
            DO UPDATE SET
                quantity = user_inventory.quantity + 1,
                item_level = GREATEST(user_inventory.item_level, EXCLUDED.item_level),
                item_rank = CASE
                    WHEN array_position(ARRAY['common','uncommon','rare','epic','legendary'], EXCLUDED.item_rank)
                       > array_position(ARRAY['common','uncommon','rare','epic','legendary'], COALESCE(user_inventory.item_rank, 'common'))
                    THEN EXCLUDED.item_rank
                    ELSE user_inventory.item_rank
                END
            """,
            (user["id"], item_data["id"], inv_level, inv_rank),
        )

        if merchant_id:
            cursor.execute(
                """
                UPDATE npc_shop_stock
                SET stock_left = stock_left - 1, updated_at = NOW()
                WHERE period_key = %s AND merchant_id = %s AND item_id = %s AND stock_left > 0
                RETURNING stock_left
                """,
                (period_key, merchant_id, item_data["id"]),
            )
            row = cursor.fetchone()
            if not row:
                return {"success": False, "message": "Товар только что закончился. Попробуй другой предмет."}
            stock_left_after = int(row["stock_left"])

    msg = f"Ты купил {item_name} за {price} руб."
    if is_weapon(item_data):
        msg += f"\nУровень оружия: {inv_level}. Ранг: {inv_rank}."
    if stock_left_after is not None:
        msg += f"\nОстаток на витрине: {stock_left_after} шт."
    return {"success": True, "message": msg, "price": price, "remaining_money": new_balance}


def sell_item_transaction(vk_id: int, item_name: str, sell_bonus_pct: int = 0, merchant_id: str | None = None) -> dict:
    """
    Продать предмет. Атомарно: предмет убирается и деньги зачисляются
    в одной транзакции.
    sell_bonus_pct — бонус к цене от пассивных навыков класса (в процентах).
    """
    with db_cursor() as (cursor, _):
        cursor.execute(
            """
            SELECT i.id, i.price, i.category
            FROM items i
            WHERE i.name = %s
            """,
            (item_name,),
        )
        item = cursor.fetchone()
        if not item:
            return {"success": False, "message": f"Предмет '{item_name}' не найден"}

        cursor.execute("SELECT id FROM users WHERE vk_id = %s FOR UPDATE", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return {"success": False, "message": "Пользователь не найден"}

        cursor.execute(
            """
            SELECT quantity
            FROM user_inventory
            WHERE user_id = %s AND item_id = %s
            FOR UPDATE
            """,
            (user["id"], item["id"]),
        )
        inv_row = cursor.fetchone()
        if not inv_row or int(inv_row["quantity"]) < 1:
            return {"success": False, "message": f"У тебя нет '{item_name}'"}

        cursor.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM user_equipment
            WHERE user_id = %s AND item_name = %s
            """,
            (user["id"], item_name),
        )
        equipped_cnt = int((cursor.fetchone() or {}).get("cnt", 0))
        if equipped_cnt > 0 and int(inv_row["quantity"]) <= equipped_cnt:
            return {
                "success": False,
                "message": f"Нельзя продать надетый предмет '{item_name}'. Сначала сними его.",
            }

        base_price = int(item["price"]) // 2
        event_bonus_pct = _get_sell_event_bonus_pct(merchant_id, (item.get("category") or "").lower())
        total_mult = 1.0 + (sell_bonus_pct + event_bonus_pct) / 100.0
        total_mult = _clamp(total_mult, config.SHOP_SELL_MULT_FLOOR, config.SHOP_SELL_MULT_CEIL)
        sell_price = max(1, int(base_price * total_mult))

        cursor.execute(
            """
            UPDATE user_inventory
            SET quantity = quantity - 1
            WHERE user_id = %s AND item_id = %s AND quantity >= 1
            RETURNING quantity
            """,
            (user["id"], item["id"]),
        )
        if not cursor.fetchone():
            return {"success": False, "message": f"У тебя нет '{item_name}'"}

        cursor.execute(
            """
            DELETE FROM user_inventory
            WHERE user_id = %s AND item_id = %s AND quantity <= 0
            """,
            (user["id"], item["id"]),
        )

        cursor.execute(
            """
            UPDATE users
            SET money = money + %s
            WHERE vk_id = %s
            RETURNING money
            """,
            (sell_price, vk_id),
        )
        new_balance = int(cursor.fetchone()["money"])

    bonuses = []
    if sell_bonus_pct:
        bonuses.append(f"+{sell_bonus_pct}% класс")
    if event_bonus_pct:
        bonuses.append(f"+{event_bonus_pct}% ивент")
    bonus_msg = f" ({', '.join(bonuses)})" if bonuses else ""
    return {
        "success": True,
        "message": f"Ты продал {item_name} за {sell_price} руб.{bonus_msg}",
        "sell_price": sell_price,
        "remaining_money": new_balance,
    }


def upgrade_weapon_to_player_level(vk_id: int, item_name: str) -> dict:
    """Прокачать оружие в инвентаре до текущего уровня игрока."""
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT id, level, money FROM users WHERE vk_id = %s FOR UPDATE", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return {"success": False, "message": "Пользователь не найден"}

        cursor.execute(
            """
            SELECT ui.item_level, ui.item_rank, i.*
            FROM user_inventory ui
            JOIN items i ON i.id = ui.item_id
            WHERE ui.user_id = %s AND LOWER(i.name) = LOWER(%s)
            FOR UPDATE
            """,
            (user["id"], item_name),
        )
        row = cursor.fetchone()
        if not row:
            return {"success": False, "message": f"У тебя нет оружия '{item_name}'."}

        item = dict(row)
        if not is_weapon(item):
            return {"success": False, "message": "Прокачивать можно только оружие."}

        target_level = int(user.get("level", 1) or 1)
        current_level = clamp_weapon_level(item.get("item_level"), target_level, item)
        if current_level >= target_level:
            return {
                "success": False,
                "message": f"{item['name']} уже актуального уровня: {current_level}/{target_level}.",
            }

        rank = normalize_weapon_rank(item.get("item_rank"), item)
        cost = weapon_upgrade_cost(item, current_level, target_level, rank)
        money = int(user.get("money", 0) or 0)
        if money < cost:
            return {"success": False, "message": f"Прокачка стоит {cost} руб., у тебя {money} руб."}

        cursor.execute(
            "UPDATE users SET money = money - %s WHERE id = %s RETURNING money",
            (cost, user["id"]),
        )
        new_money = int(cursor.fetchone()["money"])
        cursor.execute(
            "UPDATE user_inventory SET item_level = %s WHERE user_id = %s AND item_id = %s",
            (target_level, user["id"], item["id"]),
        )

    old_attack = calc_weapon_attack(item, current_level, rank)
    new_attack = calc_weapon_attack(item, target_level, rank)
    return {
        "success": True,
        "message": (
            f"Оружие улучшено: {item['name']}\n"
            f"Уровень: {current_level} -> {target_level}\n"
            f"Ранг: {rank}\n"
            f"Урон: {old_attack} -> {new_attack}\n"
            f"Цена: {cost} руб.\n"
            f"Осталось денег: {new_money} руб."
        ),
    }


# ---------------------------------------------------------------------------
# Админ-функции и настройки игры
# ---------------------------------------------------------------------------

def get_game_setting(key: str, default: str | None = None) -> str | None:
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT value FROM game_settings WHERE key = %s", (key,))
        row = cursor.fetchone()
        if not row:
            return default
        return str(row["value"])


def set_game_setting(key: str, value: str):
    with db_cursor() as (cursor, _):
        cursor.execute("""
            INSERT INTO game_settings (key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key)
            DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """, (key, value))


def is_market_enabled() -> bool:
    value = get_game_setting("p2p_market_enabled", default="1")
    return str(value).strip() in {"1", "true", "on", "yes"}


def is_user_admin(vk_id: int) -> bool:
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT is_admin FROM users WHERE vk_id = %s", (vk_id,))
        row = cursor.fetchone()
        return bool(row and int(row.get("is_admin") or 0) == 1)


def set_user_admin(vk_id: int, is_admin: bool = True) -> dict:
    with db_cursor() as (cursor, _):
        cursor.execute("""
            UPDATE users
            SET is_admin = %s
            WHERE vk_id = %s
            RETURNING vk_id, name, is_admin
        """, (1 if is_admin else 0, vk_id))
        row = cursor.fetchone()
        if not row:
            return {"success": False, "message": "Пользователь не найден."}
    return {
        "success": True,
        "message": f"Права админа для {row['name']} ({row['vk_id']}) -> {row['is_admin']}.",
    }


def set_user_ban(vk_id: int, banned: bool, reason: str | None = None) -> dict:
    with db_cursor() as (cursor, _):
        cursor.execute("""
            UPDATE users
            SET is_banned = %s,
                ban_reason = %s
            WHERE vk_id = %s
            RETURNING vk_id, name, is_banned, ban_reason
        """, (1 if banned else 0, reason if banned else None, vk_id))
        row = cursor.fetchone()
        if not row:
            return {"success": False, "message": "Пользователь не найден."}
    if banned:
        return {
            "success": True,
            "message": f"Пользователь {row['name']} ({row['vk_id']}) забанен. Причина: {row['ban_reason'] or 'не указана'}",
        }
    return {
        "success": True,
        "message": f"Пользователь {row['name']} ({row['vk_id']}) разбанен.",
    }


def get_admin_user(vk_id: int) -> dict | None:
    with db_cursor() as (cursor, _):
        cursor.execute("""
            SELECT vk_id, name, level, money, is_admin, is_banned, ban_reason, location
            FROM users
            WHERE vk_id = %s
        """, (vk_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def admin_search_users(query: str | None = None, limit: int = 20) -> list[dict]:
    with db_cursor() as (cursor, _):
        if query:
            q = f"%{query}%"
            cursor.execute("""
                SELECT vk_id, name, level, money, is_admin, is_banned
                FROM users
                WHERE CAST(vk_id AS TEXT) ILIKE %s OR name ILIKE %s
                ORDER BY id DESC
                LIMIT %s
            """, (q, q, limit))
        else:
            cursor.execute("""
                SELECT vk_id, name, level, money, is_admin, is_banned
                FROM users
                ORDER BY id DESC
                LIMIT %s
            """, (limit,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def admin_list_banned_users(limit: int = 50) -> list[dict]:
    with db_cursor() as (cursor, _):
        cursor.execute("""
            SELECT vk_id, name, ban_reason
            FROM users
            WHERE is_banned = 1
            ORDER BY id DESC
            LIMIT %s
        """, (limit,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def admin_give_item(vk_id: int, item_name: str, quantity: int = 1) -> dict:
    if quantity <= 0:
        return {"success": False, "message": "Количество должно быть > 0."}
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT id FROM users WHERE vk_id = %s", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return {"success": False, "message": "Пользователь не найден."}

        cursor.execute("SELECT name FROM items WHERE LOWER(name) = LOWER(%s)", (item_name,))
        item = cursor.fetchone()
        if not item:
            return {"success": False, "message": f"Предмет '{item_name}' не найден."}

    if not add_item_to_inventory(vk_id, item["name"], quantity):
        return {"success": False, "message": f"Не удалось выдать '{item['name']}'."}

    return {
        "success": True,
        "message": f"Выдано: {item['name']} x{quantity} пользователю {vk_id}.",
    }


def admin_remove_item(vk_id: int, item_name: str, quantity: int = 1) -> bool:
    """Удалить предмет из инвентаря игрока"""
    if quantity <= 0:
        return False
    with db_cursor() as (cursor, conn):
        cursor.execute("SELECT id FROM users WHERE vk_id = %s", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return False

        cursor.execute("SELECT id, name FROM items WHERE LOWER(name) = LOWER(%s)", (item_name,))
        item = cursor.fetchone()
        if not item:
            return False

        cursor.execute("""
            SELECT quantity FROM user_inventory
            WHERE user_id = %s AND item_id = %s
        """, (user["id"], item["id"]))
        row = cursor.fetchone()
        if not row or row["quantity"] < quantity:
            return False

        new_qty = row["quantity"] - quantity
        if new_qty <= 0:
            cursor.execute("""
                DELETE FROM user_inventory
                WHERE user_id = %s AND item_id = %s
            """, (user["id"], item["id"]))
        else:
            cursor.execute("""
                UPDATE user_inventory SET quantity = %s
                WHERE user_id = %s AND item_id = %s
            """, (new_qty, user["id"], item["id"]))
    return True


_ADMIN_EDITABLE_FIELDS = frozenset({
    "money", "level", "experience",
    "health", "energy", "radiation",
    "strength", "stamina", "perception", "luck",
    "shells", "artifact_slots", "max_weight",
})


def admin_set_user_field(vk_id: int, field: str, value: int) -> dict:
    field = field.strip().lower()
    if field not in _ADMIN_EDITABLE_FIELDS:
        return {
            "success": False,
            "message": f"Поле '{field}' нельзя редактировать через админку.",
        }
    with db_cursor() as (cursor, _):
        cursor.execute(f"""
            UPDATE users
            SET {field} = %s
            WHERE vk_id = %s
            RETURNING vk_id, name, {field}
        """, (value, vk_id))
        row = cursor.fetchone()
        if not row:
            return {"success": False, "message": "Пользователь не найден."}
    return {
        "success": True,
        "message": f"{row['name']} ({row['vk_id']}): {field} = {row[field]}",
    }


def _resolve_rank_tier_by_level(level: int, rank_tiers: list[dict]) -> int:
    """
    Определить тир ранга по уровню.
    Ожидается, что rank_tiers отсортированы по возрастанию min_level.
    """
    if not rank_tiers:
        return 1
    safe_level = max(1, int(level or 1))
    tier = 1
    for idx, row in enumerate(rank_tiers, start=1):
        min_level = int(row.get("min_level", 1) or 1)
        if safe_level >= min_level:
            tier = idx
        else:
            break
    return max(1, min(len(rank_tiers), tier))


def admin_sync_ranks_by_level(rank_tiers: list[dict], overwrite_existing: bool = True) -> dict:
    """
    Синхронизировать rank_tier всем игрокам по текущему уровню.

    overwrite_existing=True:
        Перезаписывать существующий rank_tier по таблице рангов.
    overwrite_existing=False:
        Выдавать ранг только тем, у кого rank_tier не задан/некорректен.
    """
    if not rank_tiers:
        return {"success": False, "message": "Список рангов пуст."}

    with db_cursor() as (cursor, _):
        cursor.execute(
            """
            SELECT
                u.id AS user_id,
                u.vk_id,
                u.level,
                u.rank_tier AS current_rank_tier
            FROM users u
            ORDER BY u.id
            """
        )
        users = cursor.fetchall()

        if not users:
            return {
                "success": True,
                "total_players": 0,
                "updated": 0,
                "new_assignments": 0,
                "reassigned": 0,
                "unchanged": 0,
                "skipped_existing": 0,
                "overwrite_existing": overwrite_existing,
            }

        updates: list[tuple[int, int]] = []
        unchanged = 0
        skipped_existing = 0
        new_assignments = 0
        reassigned = 0

        for row in users:
            user_id = int(row["user_id"])
            level = int(row.get("level") or 1)
            target_tier = _resolve_rank_tier_by_level(level, rank_tiers)

            current_raw = row.get("current_rank_tier")
            current_tier = int(current_raw) if current_raw is not None else None
            has_rank = current_tier is not None and current_tier > 0

            if (not overwrite_existing) and has_rank:
                skipped_existing += 1
                continue

            if current_tier == target_tier:
                unchanged += 1
                continue

            if not has_rank:
                new_assignments += 1
            else:
                reassigned += 1

            updates.append((user_id, target_tier))

        if updates:
            cursor.executemany(
                """
                UPDATE users
                SET rank_tier = %s
                WHERE id = %s
                """,
                [(tier, uid) for uid, tier in updates],
            )

    return {
        "success": True,
        "total_players": len(users),
        "updated": len(updates),
        "new_assignments": new_assignments,
        "reassigned": reassigned,
        "unchanged": unchanged,
        "skipped_existing": skipped_existing,
        "overwrite_existing": overwrite_existing,
    }


# ---------------------------------------------------------------------------
# P2P Рынок игроков
# ---------------------------------------------------------------------------

_MARKET_TRADABLE_CATEGORIES = frozenset({
    "weapons",
    "rare_weapons",
    "armor",
    "backpacks",
    "artifacts",
    "meds",
    "food",
})


def _calc_fee(total: int, percent: float) -> int:
    if total <= 0 or percent <= 0:
        return 0
    return max(1, math.ceil(total * (percent / 100)))


def _get_market_price_bounds(item: dict) -> tuple[int, int]:
    rarity = (item.get("rarity") or "common").lower()
    base_price = int(item.get("price") or 0)
    if base_price <= 0:
        return 1, 10**9

    if rarity == "rare":
        min_mult = config.MARKET_PRICE_MIN_MULT_RARE
        max_mult = config.MARKET_PRICE_MAX_MULT_RARE
    elif rarity == "unique":
        min_mult = config.MARKET_PRICE_MIN_MULT_UNIQUE
        max_mult = config.MARKET_PRICE_MAX_MULT_UNIQUE
    elif rarity == "legendary":
        min_mult = config.MARKET_PRICE_MIN_MULT_LEGENDARY
        max_mult = config.MARKET_PRICE_MAX_MULT_LEGENDARY
    else:
        min_mult = config.MARKET_PRICE_MIN_MULT_COMMON
        max_mult = config.MARKET_PRICE_MAX_MULT_COMMON

    min_price = max(1, int(base_price * min_mult))
    max_price = max(min_price, int(base_price * max_mult))
    return min_price, max_price


def _is_market_item_tradable(item: dict) -> bool:
    category = (item.get("category") or "").lower()
    return category in _MARKET_TRADABLE_CATEGORIES


def _expire_market_listings_tx(cursor, limit: int = 200) -> int:
    """
    Закрыть просроченные лоты и вернуть предметы продавцам.
    Вызывать внутри уже открытой транзакции.
    """
    cursor.execute("""
        SELECT id, seller_vk_id, item_id, quantity
        FROM market_listings
        WHERE status = 'active' AND expires_at <= NOW()
        ORDER BY expires_at ASC
        LIMIT %s
        FOR UPDATE SKIP LOCKED
    """, (limit,))
    expired_rows = cursor.fetchall()
    if not expired_rows:
        return 0

    for row in expired_rows:
        cursor.execute("SELECT id FROM users WHERE vk_id = %s", (row["seller_vk_id"],))
        seller = cursor.fetchone()
        if seller:
            cursor.execute("""
                INSERT INTO user_inventory (user_id, item_id, quantity)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, item_id)
                DO UPDATE SET quantity = user_inventory.quantity + EXCLUDED.quantity
            """, (seller["id"], row["item_id"], row["quantity"]))

    listing_ids = [row["id"] for row in expired_rows]
    cursor.execute("""
        UPDATE market_listings
        SET status = 'expired', expired_at = NOW(), expired_notified = FALSE
        WHERE id = ANY(%s)
    """, (listing_ids,))
    return len(expired_rows)


def expire_market_listings(limit: int = 200) -> int:
    with db_cursor() as (cursor, _):
        return _expire_market_listings_tx(cursor, limit=limit)


def claim_expired_market_notifications(limit: int = 100) -> list[dict]:
    """
    Забрать пачку истёкших лотов, по которым ещё не отправлено уведомление,
    и сразу пометить их как отправленные (без дублей).
    """
    with db_cursor() as (cursor, _):
        cursor.execute("""
            SELECT id, seller_vk_id, item_name, quantity, expired_at
            FROM market_listings
            WHERE status = 'expired'
              AND COALESCE(expired_notified, FALSE) = FALSE
            ORDER BY expired_at ASC NULLS LAST, id ASC
            LIMIT %s
            FOR UPDATE SKIP LOCKED
        """, (limit,))
        rows = cursor.fetchall() or []
        if not rows:
            return []

        listing_ids = [int(r["id"]) for r in rows]
        cursor.execute("""
            UPDATE market_listings
            SET expired_notified = TRUE
            WHERE id = ANY(%s)
        """, (listing_ids,))
        return [dict(r) for r in rows]


def create_market_listing(vk_id: int, item_name: str, price_per_item: int, quantity: int = 1) -> dict:
    if not is_market_enabled():
        return {"success": False, "message": "P2P рынок временно отключён администратором."}
    if quantity <= 0:
        return {"success": False, "message": "Количество должно быть больше нуля."}
    if price_per_item <= 0:
        return {"success": False, "message": "Цена должна быть больше нуля."}

    with db_cursor() as (cursor, _):
        _expire_market_listings_tx(cursor)

        cursor.execute("SELECT id, level, money FROM users WHERE vk_id = %s FOR UPDATE", (vk_id,))
        seller = cursor.fetchone()
        if not seller:
            return {"success": False, "message": "Пользователь не найден."}
        if seller["level"] < config.MARKET_MIN_LEVEL:
            return {
                "success": False,
                "message": f"Рынок доступен с {config.MARKET_MIN_LEVEL} уровня.",
            }

        cursor.execute("""
            SELECT COUNT(*) AS cnt
            FROM market_listings
            WHERE seller_vk_id = %s AND status = 'active' AND expires_at > NOW()
        """, (vk_id,))
        active_lots = int(cursor.fetchone()["cnt"])
        if active_lots >= config.MARKET_MAX_LISTINGS_PER_USER:
            return {
                "success": False,
                "message": f"Достигнут лимит активных лотов ({config.MARKET_MAX_LISTINGS_PER_USER}).",
            }

        cursor.execute("SELECT * FROM items WHERE LOWER(name) = LOWER(%s)", (item_name,))
        item = cursor.fetchone()
        if not item:
            return {"success": False, "message": f"Предмет '{item_name}' не найден."}
        item = dict(item)
        if not _is_market_item_tradable(item):
            return {"success": False, "message": "Этот предмет нельзя выставить на рынок."}

        min_price, max_price = _get_market_price_bounds(item)
        if price_per_item < min_price or price_per_item > max_price:
            return {
                "success": False,
                "message": f"Цена вне диапазона: {min_price}..{max_price} руб. за шт.",
            }

        cursor.execute("""
            SELECT quantity, item_level, item_rank
            FROM user_inventory
            WHERE user_id = %s AND item_id = %s
            FOR UPDATE
        """, (seller["id"], item["id"]))
        inv = cursor.fetchone()
        if not inv or inv["quantity"] < quantity:
            have = inv["quantity"] if inv else 0
            return {
                "success": False,
                "message": f"Недостаточно предметов. У тебя: {have}, нужно: {quantity}.",
            }

        cursor.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM user_equipment
            WHERE user_id = %s AND item_name = %s
            """,
            (seller["id"], item["name"]),
        )
        equipped_cnt = int((cursor.fetchone() or {}).get("cnt", 0))
        if equipped_cnt > 0 and int(inv["quantity"]) - int(quantity) < equipped_cnt:
            return {
                "success": False,
                "message": f"Нельзя выставить надетый предмет '{item['name']}'. Сначала сними его.",
            }

        total_price = price_per_item * quantity
        listing_fee = _calc_fee(total_price, config.MARKET_LISTING_FEE_PCT)
        if seller["money"] < listing_fee:
            return {
                "success": False,
                "message": f"Не хватает денег на комиссию выставления ({listing_fee} руб.).",
            }

        cursor.execute("UPDATE users SET money = money - %s WHERE vk_id = %s", (listing_fee, vk_id))
        cursor.execute("""
            UPDATE user_inventory
            SET quantity = quantity - %s
            WHERE user_id = %s AND item_id = %s
        """, (quantity, seller["id"], item["id"]))
        cursor.execute("""
            DELETE FROM user_inventory
            WHERE user_id = %s AND item_id = %s AND quantity <= 0
        """, (seller["id"], item["id"]))

        cursor.execute("""
            INSERT INTO market_listings (
                seller_vk_id, item_id, item_name, quantity, item_level, item_rank, price_per_item,
                listing_fee, expires_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                NOW() + (%s * INTERVAL '1 hour')
            )
            RETURNING id, expires_at
        """, (
            vk_id,
            item["id"],
            item["name"],
            quantity,
            int(inv.get("item_level", 1) or 1),
            normalize_weapon_rank(inv.get("item_rank"), item),
            price_per_item,
            listing_fee, config.MARKET_LISTING_TTL_HOURS
        ))
        new_lot = cursor.fetchone()

    return {
        "success": True,
        "listing_id": new_lot["id"],
        "listing_fee": listing_fee,
        "expires_at": new_lot["expires_at"],
        "message": (
            f"Лот #{new_lot['id']} выставлен: {item['name']} x{quantity} "
            f"по {price_per_item} руб. Комиссия: {listing_fee} руб."
        ),
    }


def get_market_listing_info(listing_id: int) -> dict | None:
    """Получить информацию о лоте для превью покупки (без блокировки)"""
    with db_cursor() as (cursor, _):
        _expire_market_listings_tx(cursor)
        cursor.execute("""
            SELECT ml.*, i.category, i.rarity
            FROM market_listings ml
            JOIN items i ON i.id = ml.item_id
            WHERE ml.id = %s
        """, (listing_id,))
        row = cursor.fetchone()
        if not row:
            return None
        if row["status"] != "active" or row["expires_at"] <= datetime.now():
            return None
        return dict(row)


def count_market_listings(category: str | None = None, search: str | None = None) -> int:
    """Посчитать количество активных лотов для пагинации."""
    with db_cursor() as (cursor, _):
        _expire_market_listings_tx(cursor)
        if category and search:
            cursor.execute("""
                SELECT COUNT(*) as cnt
                FROM market_listings l
                JOIN items i ON i.id = l.item_id
                WHERE l.status = 'active'
                  AND l.expires_at > NOW()
                  AND i.category = %s
                  AND LOWER(l.item_name) LIKE LOWER(%s)
            """, (category, f"%{search}%"))
        elif category:
            cursor.execute("""
                SELECT COUNT(*) as cnt
                FROM market_listings l
                JOIN items i ON i.id = l.item_id
                WHERE l.status = 'active'
                  AND l.expires_at > NOW()
                  AND i.category = %s
            """, (category,))
        elif search:
            cursor.execute("""
                SELECT COUNT(*) as cnt
                FROM market_listings l
                WHERE l.status = 'active'
                  AND l.expires_at > NOW()
                  AND LOWER(l.item_name) LIKE LOWER(%s)
            """, (f"%{search}%",))
        else:
            cursor.execute("""
                SELECT COUNT(*) as cnt
                FROM market_listings l
                WHERE l.status = 'active'
                  AND l.expires_at > NOW()
            """)
        row = cursor.fetchone()
        return row["cnt"] if row else 0


def get_market_listings(page: int = 1, per_page: int = 8, category: str | None = None,
                        sort: str = "newest", search: str | None = None) -> dict:
    """
    Получить страницу лотов рынка.
    Возвращает dict: {listings, total, page, pages, per_page}
    sort: newest|oldest|cheap|expensive
    """
    if not is_market_enabled():
        return {"listings": [], "total": 0, "page": 1, "pages": 1, "per_page": per_page}

    offset = (page - 1) * per_page
    total = count_market_listings(category, search)
    pages = max(1, (total + per_page - 1) // per_page)

    # Определяем сортировку
    order_clause = "l.created_at DESC"
    if sort == "oldest":
        order_clause = "l.created_at ASC"
    elif sort == "cheap":
        order_clause = "l.price_per_item ASC"
    elif sort == "expensive":
        order_clause = "l.price_per_item DESC"

    with db_cursor() as (cursor, _):
        _expire_market_listings_tx(cursor)

        conditions = ["l.status = 'active'", "l.expires_at > NOW()"]
        params: list = []

        if category:
            conditions.append("i.category = %s")
            params.append(category)
        if search:
            conditions.append("LOWER(l.item_name) LIKE LOWER(%s)")
            params.append(f"%{search}%")

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT l.id, l.seller_vk_id, l.item_name, l.quantity, l.price_per_item,
                   (l.quantity * l.price_per_item) AS total_price,
                   l.expires_at, l.created_at, i.category, i.rarity
            FROM market_listings l
            JOIN items i ON i.id = l.item_id
            WHERE {where_clause}
            ORDER BY {order_clause}
            LIMIT %s OFFSET %s
        """
        params.extend([per_page, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return {
            "listings": [dict(row) for row in rows],
            "total": total,
            "page": page,
            "pages": pages,
            "per_page": per_page,
        }


def get_market_user_listings(vk_id: int, status: str = "active", page: int = 1, per_page: int = 8) -> dict:
    """Получить лоты пользователя с пагинацией."""
    offset = (page - 1) * per_page

    with db_cursor() as (cursor, _):
        _expire_market_listings_tx(cursor)

        if status == "all":
            cursor.execute("""
                SELECT id, item_name, quantity, price_per_item,
                       (quantity * price_per_item) AS total_price,
                       status, created_at, expires_at, completed_at, cancelled_at
                FROM market_listings
                WHERE seller_vk_id = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (vk_id, per_page, offset))
            rows = cursor.fetchall()

            cursor.execute("""
                SELECT COUNT(*) as cnt
                FROM market_listings
                WHERE seller_vk_id = %s
            """, (vk_id,))
        else:
            cursor.execute("""
                SELECT id, item_name, quantity, price_per_item,
                       (quantity * price_per_item) AS total_price,
                       status, created_at, expires_at, completed_at, cancelled_at
                FROM market_listings
                WHERE seller_vk_id = %s
                  AND status = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (vk_id, status, per_page, offset))
            rows = cursor.fetchall()

            cursor.execute("""
                SELECT COUNT(*) as cnt
                FROM market_listings
                WHERE seller_vk_id = %s AND status = %s
            """, (vk_id, status))
        total_row = cursor.fetchone() or {}
        total = int(total_row.get("cnt", 0))

        pages = max(1, (total + per_page - 1) // per_page)

        return {
            "listings": [dict(row) for row in rows],
            "total": total,
            "page": page,
            "pages": pages,
            "per_page": per_page,
        }


def buy_market_listing(vk_id: int, listing_id: int) -> dict:
    if not is_market_enabled():
        return {"success": False, "message": "P2P рынок временно отключён администратором."}
    with db_cursor() as (cursor, _):
        _expire_market_listings_tx(cursor)

        cursor.execute("SELECT id, level FROM users WHERE vk_id = %s FOR UPDATE", (vk_id,))
        buyer = cursor.fetchone()
        if not buyer:
            return {"success": False, "message": "Покупатель не найден."}
        if buyer["level"] < config.MARKET_MIN_LEVEL:
            return {
                "success": False,
                "message": f"Рынок доступен с {config.MARKET_MIN_LEVEL} уровня.",
            }

        cursor.execute("""
            SELECT *
            FROM market_listings
            WHERE id = %s
            FOR UPDATE
        """, (listing_id,))
        lot = cursor.fetchone()
        if not lot:
            return {"success": False, "message": "Лот не найден."}
        if lot["status"] != "active" or lot["expires_at"] <= datetime.now():
            return {"success": False, "message": "Лот уже недоступен."}
        if lot["seller_vk_id"] == vk_id:
            return {"success": False, "message": "Нельзя купить свой лот."}

        total_price = lot["price_per_item"] * lot["quantity"]
        sale_fee = _calc_fee(total_price, config.MARKET_SALE_FEE_PCT)
        seller_payout = max(0, total_price - sale_fee)

        cursor.execute("SELECT id FROM users WHERE vk_id = %s", (lot["seller_vk_id"],))
        seller = cursor.fetchone()
        if not seller:
            return {"success": False, "message": "Продавец не найден."}

        cursor.execute("""
            UPDATE users
            SET money = money - %s
            WHERE vk_id = %s AND money >= %s
            RETURNING money
        """, (total_price, vk_id, total_price))
        buyer_balance = cursor.fetchone()
        if not buyer_balance:
            return {"success": False, "message": f"Не хватает денег. Нужно {total_price} руб."}

        cursor.execute("""
            UPDATE users
            SET money = money + %s
            WHERE vk_id = %s
        """, (seller_payout, lot["seller_vk_id"]))

        cursor.execute("""
            INSERT INTO user_inventory (user_id, item_id, quantity, item_level, item_rank)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, item_id)
            DO UPDATE SET
                quantity = user_inventory.quantity + EXCLUDED.quantity,
                item_level = GREATEST(user_inventory.item_level, EXCLUDED.item_level),
                item_rank = CASE
                    WHEN array_position(ARRAY['common','uncommon','rare','epic','legendary'], EXCLUDED.item_rank)
                       > array_position(ARRAY['common','uncommon','rare','epic','legendary'], COALESCE(user_inventory.item_rank, 'common'))
                    THEN EXCLUDED.item_rank
                    ELSE user_inventory.item_rank
                END
        """, (
            buyer["id"],
            lot["item_id"],
            lot["quantity"],
            int(lot.get("item_level", 1) or 1),
            normalize_weapon_rank(lot.get("item_rank"), {"category": "weapons"} if lot.get("item_rank") else None),
        ))

        cursor.execute("""
            UPDATE market_listings
            SET status = 'sold',
                buyer_vk_id = %s,
                sale_fee = %s,
                completed_at = NOW()
            WHERE id = %s
        """, (vk_id, sale_fee, listing_id))

        cursor.execute("""
            INSERT INTO market_transactions (
                listing_id, seller_vk_id, buyer_vk_id, item_id, item_name,
                quantity, item_level, item_rank, price_per_item, total_price, sale_fee
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            listing_id, lot["seller_vk_id"], vk_id, lot["item_id"], lot["item_name"],
            lot["quantity"], int(lot.get("item_level", 1) or 1), lot.get("item_rank", "common"),
            lot["price_per_item"], total_price, sale_fee
        ))

    return {
        "success": True,
        "listing_id": listing_id,
        "seller_vk_id": lot["seller_vk_id"],
        "buyer_vk_id": vk_id,
        "item_name": lot["item_name"],
        "quantity": lot["quantity"],
        "total_price": total_price,
        "sale_fee": sale_fee,
        "seller_payout": seller_payout,
        "message": (
            f"Куплено: {lot['item_name']} x{lot['quantity']} за {total_price} руб.\n"
            f"Комиссия рынка (с продавца): {sale_fee} руб."
        ),
    }


def cancel_market_listing(vk_id: int, listing_id: int) -> dict:
    if not is_market_enabled():
        return {"success": False, "message": "P2P рынок временно отключён администратором."}
    with db_cursor() as (cursor, _):
        _expire_market_listings_tx(cursor)

        cursor.execute("""
            SELECT *
            FROM market_listings
            WHERE id = %s AND seller_vk_id = %s
            FOR UPDATE
        """, (listing_id, vk_id))
        lot = cursor.fetchone()
        if not lot:
            return {"success": False, "message": "Лот не найден."}
        if lot["status"] != "active":
            return {"success": False, "message": "Лот уже неактивен."}

        cursor.execute("SELECT id FROM users WHERE vk_id = %s", (vk_id,))
        seller = cursor.fetchone()
        if not seller:
            return {"success": False, "message": "Продавец не найден."}

        cursor.execute("""
            INSERT INTO user_inventory (user_id, item_id, quantity, item_level, item_rank)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, item_id)
            DO UPDATE SET
                quantity = user_inventory.quantity + EXCLUDED.quantity,
                item_level = GREATEST(user_inventory.item_level, EXCLUDED.item_level),
                item_rank = CASE
                    WHEN array_position(ARRAY['common','uncommon','rare','epic','legendary'], EXCLUDED.item_rank)
                       > array_position(ARRAY['common','uncommon','rare','epic','legendary'], COALESCE(user_inventory.item_rank, 'common'))
                    THEN EXCLUDED.item_rank
                    ELSE user_inventory.item_rank
                END
        """, (
            seller["id"],
            lot["item_id"],
            lot["quantity"],
            int(lot.get("item_level", 1) or 1),
            normalize_weapon_rank(lot.get("item_rank"), {"category": "weapons"} if lot.get("item_rank") else None),
        ))

        cursor.execute("""
            UPDATE market_listings
            SET status = 'cancelled', cancelled_at = NOW()
            WHERE id = %s
        """, (listing_id,))

    return {
        "success": True,
        "listing_id": listing_id,
        "seller_vk_id": vk_id,
        "item_name": lot["item_name"],
        "quantity": lot["quantity"],
        "message": f"Лот #{listing_id} снят. Предмет возвращён в инвентарь.",
    }


def get_market_user_transactions(vk_id: int, limit: int = 20) -> list[dict]:
    with db_cursor() as (cursor, _):
        cursor.execute("""
            SELECT id, listing_id, seller_vk_id, buyer_vk_id, item_name,
                   quantity, price_per_item, total_price, sale_fee, created_at
            FROM market_transactions
            WHERE seller_vk_id = %s OR buyer_vk_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (vk_id, vk_id, limit))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def admin_get_market_listings(status: str = "active", limit: int = 50) -> list[dict]:
    with db_cursor() as (cursor, _):
        _expire_market_listings_tx(cursor)
        cursor.execute("""
            SELECT id, seller_vk_id, buyer_vk_id, item_name, quantity, price_per_item,
                   (quantity * price_per_item) AS total_price,
                   status, created_at, expires_at, completed_at
            FROM market_listings
            WHERE (%s = 'all' OR status = %s)
            ORDER BY created_at DESC
            LIMIT %s
        """, (status, status, limit))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def admin_cancel_market_listing(listing_id: int) -> dict:
    with db_cursor() as (cursor, _):
        cursor.execute("""
            SELECT *
            FROM market_listings
            WHERE id = %s
            FOR UPDATE
        """, (listing_id,))
        lot = cursor.fetchone()
        if not lot:
            return {"success": False, "message": "Лот не найден."}
        if lot["status"] != "active":
            return {"success": False, "message": f"Лот не активен (status={lot['status']})."}

        cursor.execute("SELECT id FROM users WHERE vk_id = %s", (lot["seller_vk_id"],))
        seller = cursor.fetchone()
        if seller:
            cursor.execute("""
                INSERT INTO user_inventory (user_id, item_id, quantity)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, item_id)
                DO UPDATE SET quantity = user_inventory.quantity + EXCLUDED.quantity
            """, (seller["id"], lot["item_id"], lot["quantity"]))

        cursor.execute("""
            UPDATE market_listings
            SET status = 'cancelled',
                cancelled_at = NOW()
            WHERE id = %s
        """, (listing_id,))

    return {
        "success": True,
        "listing_id": listing_id,
        "seller_vk_id": lot["seller_vk_id"],
        "item_name": lot["item_name"],
        "quantity": lot["quantity"],
        "message": f"Лот #{listing_id} принудительно снят администратором.",
    }


# ---------------------------------------------------------------------------
# Предметы — справочные функции
# ---------------------------------------------------------------------------

def get_item_by_name(item_name: str) -> dict | None:
    items, _, _ = _get_cached_items()
    return items.get(item_name)


def get_item_location_drop_chance(item: dict | None, location_id: str | None) -> int:
    """Вернуть шанс выпадения предмета в конкретной локации (0..100)."""
    if not item or not location_id:
        return 0
    raw = item.get("location_drop_chances") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else {}
        except Exception:
            raw = {}
    if not isinstance(raw, dict):
        return 0
    return _coerce_percent(raw.get(location_id, 0))


def get_items_by_category(category: str) -> list[dict]:
    _, by_category, _ = _get_cached_items()
    return by_category.get(category, [])


def get_all_items() -> list[dict]:
    all_items, _, _ = _get_cached_items()
    return list(all_items.values())


def get_shop_items(category: str = None) -> list[dict]:
    _, _, shop = _get_cached_items()
    return shop.get(category, [])


def get_armor_type(item_name: str) -> str | None:
    """Определить слот брони по названию предмета."""
    name = item_name.lower()
    if any(k in name for k in ["кепка", "шлем", "каска", "шапка", "берет", "маска"]):
        return "head"
    if any(k in name for k in ["куртка", "броня", "жилет", "костюм", "плащ", "комбинезон", "скафандр", "экзоскелет"]):
        return "body"
    if any(k in name for k in ["джинсы", "штаны", "брюки"]):
        return "legs"
    if any(k in name for k in ["перчатк", "рукавич"]):
        return "hands"
    if any(k in name for k in ["ботинк", "кед", "туфл", "сапог", "берц"]):
        return "feet"
    return None


def get_shells_info(vk_id: int) -> dict:
    """Получить информацию о гильзах игрока"""
    user_data = get_user_by_vk(vk_id)
    if not user_data:
        return {'current': 0, 'capacity': 0, 'equipped_bag': None}

    shells = user_data.get('shells', 0)
    equipped_bag = user_data.get('equipped_shells_bag')

    capacity = 0
    if equipped_bag:
        bag_item = get_item_by_name(equipped_bag)
        if bag_item:
            capacity = bag_item.get('backpack_bonus', 0)

    return {
        'current': shells,
        'capacity': capacity,
        'equipped_bag': equipped_bag
    }


def get_user_shells(vk_id: int) -> int:
    """Получить текущее количество гильз"""
    info = get_shells_info(vk_id)
    return info['current']


def remove_shells(vk_id: int, quantity: int) -> bool:
    """Удалить гильзы у игрока"""
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT id FROM users WHERE vk_id = %s", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return False

        cursor.execute("""
            UPDATE users SET shells = GREATEST(0, shells - %s)
            WHERE id = %s AND shells >= %s
        """, (quantity, user['id'], quantity))

        return cursor.rowcount > 0


def add_shells(vk_id: int, quantity: int) -> tuple[bool, str]:
    """Добавить гильзы игроку с учётом вместимости мешочка.
    Возвращает (успех, сообщение)."""
    shells_info = get_shells_info(vk_id)
    current = shells_info['current']
    capacity = shells_info['capacity']

    available_space = capacity - current
    if available_space <= 0:
        return False, f"Мешочек полон! ({current}/{capacity})"

    actual_add = min(quantity, available_space)
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT id FROM users WHERE vk_id = %s", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return False, "Пользователь не найден."

        cursor.execute("""
            UPDATE users SET shells = shells + %s
            WHERE id = %s
        """, (actual_add, user['id']))

    if actual_add < quantity:
        return True, f"Добавлено {actual_add} гильз (мешочек полон: {current + actual_add}/{capacity})"
    return True, f"Добавлено {actual_add} гильз"


# ---------------------------------------------------------------------------
# Артефакты
# ---------------------------------------------------------------------------

ARTIFACT_BONUSES = {
    "Слизь":            {"health": 10, "dodge": 5},
    "Пружина":          {"defense": 8, "dodge": 3},
    "Пустышка":         {"luck": 5},
    "Капля":            {"health": 8, "radiation": -5},
    "Слюда":            {"damage_resist": 5},
    "Вспышка":          {"find_chance": 10, "perception": 3},
    "Бенгальский огонь":{"damage_boost": 12},
    "Батарейка":        {"energy": 15, "crit": 3},
    "Плёнка":           {"dodge": 6, "radiation": -3},
    "Ломоть мяса":      {"health": 12, "radiation": 8},
    "Грави":            {"defense": 20},
    "Выверт":           {"dodge": 15},
    "Слизняк":          {"health": 15, "dodge": 8},
    "Огненный шар":     {"damage_boost": 15, "defense_fire": 10},
    "Золотая рыбка":    {"luck": 15},
    "Ночная звезда":    {"max_weight": 10},
    "Колобок":          {"health": 10, "luck": 5, "find_chance": 5},
    "Морской ёж":       {"damage_boost": 18, "defense": 8},
    "Колючка":          {"defense": 10, "crit": 5},
    "Кровь камня":      {"defense": 20, "damage_resist": 5},
    "Каменный цветок":  {"damage_resist": 12},
    "Мамины бусы":      {"luck": 20, "radiation": -10},
    "Лунный свет":      {"max_energy": 20},
    "Кристальная колючка": {"defense": 25, "crit": 10, "dodge": 15},
    "Кристалл":         {"crit": 20, "defense": 15},
    "Медуза":           {"damage_resist": 15},
    "Душа":             {"all_stats": 30, "radiation": -30},
}


def equip_artifact(vk_id: int, artifact_name: str) -> dict:
    user = get_user_by_vk(vk_id)
    if not user:
        return {"success": False, "message": "Пользователь не найден"}

    inventory = get_user_inventory(vk_id)
    artifact_categories = {"artifacts", "rare_artifacts", "legendary_artifacts"}
    in_inv = [i for i in inventory if i["category"] in artifact_categories and i["name"] == artifact_name]
    if not in_inv:
        return {"success": False, "message": "Артефакт не найден в инвентаре"}

    max_slots = max(1, min(config.MAX_ARTIFACT_SLOTS, int(user.get("artifact_slots", 3) or 3)))
    equipped = [user.get(f"equipped_artifact_{i}") for i in range(1, max_slots + 1)]
    if artifact_name in equipped:
        return {"success": False, "message": "Этот артефакт уже экипирован"}

    used_slots = sum(1 for s in equipped if s)
    if used_slots >= max_slots:
        return {"success": False, "message": f"Недостаточно слотов! Занято: {used_slots}/{max_slots}"}

    for i in range(1, max_slots + 1):
        if not user.get(f"equipped_artifact_{i}"):
            update_user_stats(vk_id, **{f"equipped_artifact_{i}": artifact_name})
            return {"success": True, "message": f"✅ Артефакт {artifact_name} экипирован!"}

    return {"success": False, "message": "Нет свободных слотов"}


def unequip_artifact(vk_id: int, artifact_name: str) -> dict:
    user = get_user_by_vk(vk_id)
    if not user:
        return {"success": False, "message": "Пользователь не найден"}

    for i in range(1, config.MAX_ARTIFACT_SLOTS + 1):
        if user.get(f"equipped_artifact_{i}") == artifact_name:
            update_user_stats(vk_id, **{f"equipped_artifact_{i}": ""})
            return {"success": True, "message": f"✅ Артефакт {artifact_name} снят!"}

    return {"success": False, "message": "Этот артефакт не экипирован"}


def get_equipped_artifacts(vk_id: int) -> list:
    user = get_user_by_vk(vk_id)
    if not user:
        return []
    return [
        user[f"equipped_artifact_{i}"]
        for i in range(1, config.MAX_ARTIFACT_SLOTS + 1)
        if user.get(f"equipped_artifact_{i}")
    ]


def get_artifact_bonuses(vk_id: int) -> dict:
    equipped = get_equipped_artifacts(vk_id)
    bonuses = {
        "defense": 0,
        "defense_fire": 0,
        "energy": 0,
        "radiation": 0,
        "crit": 0,
        "find_chance": 0,
        "dodge": 0,
        "max_health_bonus": 0,
        "fire_immune": False,
        "rare_find_chance": 0,
        "damage_boost": 0,
        "max_weight": 0,
        "max_energy": 0,
        "strength": 0,
        "stamina": 0,
        "perception": 0,
        "luck": 0,
        "all_stats": 0,
    }

    for artifact_name in equipped:
        bonus_data = ARTIFACT_BONUSES.get(artifact_name, {})
        for key, value in bonus_data.items():
            # Исторически часть артефактов использовала ключ "health" для бонуса к макс. HP.
            # Сводим его к единому полю max_health_bonus.
            normalized_key = "max_health_bonus" if key == "health" else key
            if normalized_key == "all_stats":
                stat_delta = int(value or 0)
                bonuses["all_stats"] += stat_delta
                bonuses["strength"] += stat_delta
                bonuses["stamina"] += stat_delta
                bonuses["perception"] += stat_delta
                bonuses["luck"] += stat_delta
                continue
            if normalized_key in bonuses:
                if isinstance(value, bool):
                    bonuses[normalized_key] = bonuses[normalized_key] or value
                else:
                    bonuses[normalized_key] += value

    return bonuses


def roll_artifact_from_anomaly(anomaly_type: str, luck: int, detector_bonus: int, chance_multiplier: float = 1.0) -> dict | None:
    """Попытаться получить артефакт из аномалии с броском гильзы"""
    import random
    from game.anomalies import ANOMALIES

    if anomaly_type not in ANOMALIES:
        return None

    anomaly = ANOMALIES[anomaly_type]
    artifacts_list = anomaly.get("artifacts", [])

    if not artifacts_list:
        return None

    base_chance = anomaly.get("success_chance_with_detector", 50)
    total_chance = (base_chance + (luck * 2) + detector_bonus) * max(0.0, chance_multiplier)
    total_chance = min(95, total_chance)

    if random.randint(1, 100) > total_chance:
        return None

    artifact_name = random.choice(artifacts_list)
    artifact = get_item_by_name(artifact_name)
    if artifact:
        return {'name': artifact_name, 'rarity': artifact.get('rarity', 'common')}

    return None


def equip_shells_bag(vk_id: int, bag_name: str) -> dict:
    """Надеть мешочек для гильз"""
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT id FROM users WHERE vk_id = %s", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return {'success': False, 'message': 'Пользователь не найден'}

        user_id = user['id']
        cursor.execute("""
            SELECT ui.quantity, i.name, i.backpack_bonus
            FROM user_inventory ui
            JOIN items i ON ui.item_id = i.id
            WHERE ui.user_id = %s AND i.name = %s AND ui.quantity > 0
            AND i.category = 'shells_bag'
        """, (user_id, bag_name))

        item = cursor.fetchone()
        if not item:
            return {'success': False, 'message': f'Мешочек "{bag_name}" не найден в инвентаре'}

        cursor.execute("""
            INSERT INTO user_equipment (user_id, slot, item_name)
            VALUES (%s, 'shells_bag', %s)
            ON CONFLICT (user_id, slot) DO UPDATE SET item_name = EXCLUDED.item_name
        """, (user_id, bag_name))

        capacity = item.get('backpack_bonus', 0)
        cursor.execute("SELECT shells FROM users WHERE id = %s", (user_id,))
        current_shells = cursor.fetchone()['shells']
        if current_shells > capacity:
            cursor.execute("UPDATE users SET shells = %s WHERE id = %s", (capacity, user_id))

        return {'success': True, 'message': f'Надет мешочек: {bag_name} (вместимость: {capacity} гильз)'}


def unequip_shells_bag(vk_id: int) -> dict:
    """Снять мешочек для гильз — гильзы сохраняются (макс 100 без мешка)"""
    with db_cursor() as (cursor, conn):
        cursor.execute("SELECT id, shells FROM users WHERE vk_id = %s", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return {'success': False, 'message': 'Пользователь не найден'}

        user_id = user['id']
        current_shells = user.get('shells', 0)
        max_without_bag = 100
        lost_shells = max(0, current_shells - max_without_bag)
        new_shells = min(current_shells, max_without_bag)

        cursor.execute("DELETE FROM user_equipment WHERE user_id = %s AND slot = 'shells_bag'", (user_id,))
        cursor.execute("UPDATE users SET shells = %s WHERE id = %s", (new_shells, user_id))

        msg = "Мешочек для гильз снят."
        if lost_shells > 0:
            msg += f"\n⚠️ Без мешка можно хранить до {max_without_bag} гильз. Потеряно: {lost_shells}."
        else:
            msg += f"\nГильзы сохранены: {new_shells} шт."

        return {'success': True, 'message': msg}


# ---------------------------------------------------------------------------

def give_newbie_kit(vk_id: int) -> dict:
    """Выдать набор новичка"""
    from game.constants import NEWBIE_KIT_ITEMS

    granted_items: list[tuple[str, int]] = []

    with db_cursor() as (cursor, _):
        cursor.execute("SELECT id FROM users WHERE vk_id = %s", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return {'success': False, 'message': 'Пользователь не найден'}

        user_id = user['id']

        # Проверяем, не получал ли уже
        cursor.execute("""
            SELECT value FROM user_flags 
            WHERE user_id = %s AND flag_name = 'newbie_kit_received'
        """, (user_id,))

        if cursor.fetchone():
            return {'success': False, 'message': 'Вы уже получили набор новичка'}

        # Выдаём предметы из NEWBIE_KIT_ITEMS
        for item_name, quantity in NEWBIE_KIT_ITEMS:
            cursor.execute("SELECT id FROM items WHERE name = %s", (item_name,))
            item = cursor.fetchone()
            if item:
                cursor.execute("""
                    INSERT INTO user_inventory (user_id, item_id, quantity)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, item_id) DO UPDATE 
                    SET quantity = user_inventory.quantity + EXCLUDED.quantity
                """, (user_id, item['id'], quantity))
                granted_items.append((item_name, int(quantity)))

        # Ставим флаг о получении
        cursor.execute("""
            INSERT INTO user_flags (user_id, flag_name, value)
            VALUES (%s, 'newbie_kit_received', 1)
            ON CONFLICT (user_id, flag_name) DO NOTHING
        """, (user_id,))

    # Донастройка после выдачи:
    # 1) надеваем стартовый мешочек и добавляем стартовый запас гильз;
    # 2) аккуратно автоэкипируем стартовый сет только в пустые слоты.
    equip_shells_bag(vk_id, "Маленький мешочек")
    shells_before = get_user_shells(vk_id)
    add_shells(vk_id, 10)
    shells_after = get_user_shells(vk_id)
    shells_added = max(0, int(shells_after) - int(shells_before))

    user_data = get_user_by_vk(vk_id) or {}
    equip_updates = {}
    if not user_data.get("equipped_weapon"):
        equip_updates["equipped_weapon"] = "ПМ"
    if not user_data.get("equipped_armor_head"):
        equip_updates["equipped_armor_head"] = "Кепка"
    if not user_data.get("equipped_armor_body"):
        equip_updates["equipped_armor_body"] = "Кожаная куртка"
    if not user_data.get("equipped_armor_legs"):
        equip_updates["equipped_armor_legs"] = "Джинсы"
    if not user_data.get("equipped_armor_hands"):
        equip_updates["equipped_armor_hands"] = "Перчатки без пальцев"
    if not user_data.get("equipped_armor_feet"):
        equip_updates["equipped_armor_feet"] = "Кеды"
    if equip_updates:
        update_user_stats(vk_id, **equip_updates)

    if shells_added > 0:
        granted_items.append(("Гильзы", shells_added))

    return {
        'success': True,
        'message': '✅ Набор новичка получен! Проверь инвентарь.',
        'items': granted_items,
    }


def get_user_flag(vk_id: int, flag_name: str, default: int = 0) -> int:
    """Получить значение флага пользователя. Возвращает default если флага нет."""
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT id FROM users WHERE vk_id = %s", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return default

        cursor.execute(
            "SELECT value FROM user_flags WHERE user_id = %s AND flag_name = %s",
            (user['id'], flag_name),
        )
        row = cursor.fetchone()
        return row['value'] if row else default


def get_user_rank_tier(vk_id: int, default: int = 1) -> int:
    """Получить ранг пользователя из users.rank_tier (с fallback на legacy flag)."""
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT rank_tier FROM users WHERE vk_id = %s", (vk_id,))
        row = cursor.fetchone()
        if row and row.get("rank_tier") is not None:
            try:
                return max(1, int(row["rank_tier"]))
            except (TypeError, ValueError):
                return max(1, int(default or 1))
    # Fallback для старых данных до миграции.
    legacy = get_user_flag(vk_id, "rank_tier", default=default)
    try:
        return max(1, int(legacy))
    except (TypeError, ValueError):
        return max(1, int(default or 1))


def set_user_rank_tier(vk_id: int, value: int):
    """Сохранить ранг пользователя в users.rank_tier."""
    safe_value = max(1, int(value or 1))
    with db_cursor() as (cursor, _):
        cursor.execute(
            "UPDATE users SET rank_tier = %s WHERE vk_id = %s",
            (safe_value, vk_id),
        )


def set_user_flag(vk_id: int, flag_name: str, value: int):
    """Установить значение флага пользователя."""
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT id FROM users WHERE vk_id = %s", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return

        cursor.execute(
            """
            INSERT INTO user_flags (user_id, flag_name, value)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, flag_name) DO UPDATE
            SET value = EXCLUDED.value
            """,
            (user['id'], flag_name, value),
        )


def set_runtime_state(vk_id: int, state_key: str, payload: dict):
    """Сохранить runtime-состояние пользователя как JSON."""
    if not state_key:
        return
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT id FROM users WHERE vk_id = %s", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return
        try:
            payload_json = json.dumps(payload or {}, ensure_ascii=False)
        except Exception:
            logger.exception("set_runtime_state: не удалось сериализовать payload key=%s vk_id=%s", state_key, vk_id)
            return

        cursor.execute(
            """
            INSERT INTO user_runtime_state (user_id, state_key, payload_json, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (user_id, state_key) DO UPDATE
            SET payload_json = EXCLUDED.payload_json,
                updated_at = NOW()
            """,
            (user["id"], state_key, payload_json),
        )


def get_runtime_state(vk_id: int, state_key: str) -> dict | None:
    """Получить runtime-состояние пользователя."""
    if not state_key:
        return None
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT id FROM users WHERE vk_id = %s", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return None

        cursor.execute(
            """
            SELECT payload_json
            FROM user_runtime_state
            WHERE user_id = %s AND state_key = %s
            """,
            (user["id"], state_key),
        )
        row = cursor.fetchone()
        if not row:
            return None
        try:
            data = json.loads(row["payload_json"] or "{}")
            return data if isinstance(data, dict) else None
        except Exception:
            logger.exception("get_runtime_state: не удалось распарсить payload key=%s vk_id=%s", state_key, vk_id)
            return None


def clear_runtime_state(vk_id: int, state_key: str):
    """Удалить runtime-состояние пользователя."""
    if not state_key:
        return
    with db_cursor() as (cursor, _):
        cursor.execute(
            """
            DELETE FROM user_runtime_state rs
            USING users u
            WHERE u.vk_id = %s
              AND rs.user_id = u.id
              AND rs.state_key = %s
            """,
            (vk_id, state_key),
        )


def get_all_runtime_states(state_key: str) -> list[dict]:
    """Получить все runtime-состояния указанного типа."""
    if not state_key:
        return []
    with db_cursor() as (cursor, _):
        cursor.execute(
            """
            SELECT u.vk_id, rs.payload_json, rs.updated_at
            FROM user_runtime_state rs
            JOIN users u ON u.id = rs.user_id
            WHERE rs.state_key = %s
            """,
            (state_key,),
        )
        rows = cursor.fetchall() or []

    result: list[dict] = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
            if not isinstance(payload, dict):
                payload = {}
        except Exception:
            payload = {}
        result.append(
            {
                "vk_id": int(row["vk_id"]),
                "payload": payload,
                "updated_at": row.get("updated_at"),
            }
        )
    return result


# ---------------------------------------------------------------------------
# Инициализация БД
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    print("База данных готова к работе!")


# =========================================================================
# Ежедневные задания (Daily Quests)
# =========================================================================

def init_daily_quests_table():
    """Создать таблицу ежедневных заданий (вызывается из init_db)"""
    with db_cursor() as (cursor, conn):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_quests (
                vk_id         BIGINT NOT NULL,
                quest_date    DATE NOT NULL DEFAULT CURRENT_DATE,
                quest_json    JSONB NOT NULL,
                progress_json JSONB NOT NULL DEFAULT '{}',
                streak        INTEGER NOT NULL DEFAULT 0,
                last_complete DATE,
                claimed       BOOLEAN NOT NULL DEFAULT FALSE,
                updated_at    TIMESTAMP NOT NULL DEFAULT NOW(),
                PRIMARY KEY (vk_id, quest_date)
            )
        """)
        cursor.execute("""
            ALTER TABLE daily_quests
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_daily_quests_date
            ON daily_quests(quest_date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_daily_quests_vk_date
            ON daily_quests(vk_id, quest_date DESC)
        """)


def get_daily_quests_for_user(vk_id: int) -> dict | None:
    """Получить ежедневные задания игрока на сегодня"""
    with db_cursor() as (cursor, _):
        cursor.execute("""
            SELECT quest_json, progress_json, streak, last_complete, claimed, quest_date, updated_at
            FROM daily_quests
            WHERE vk_id = %s AND quest_date = (NOW() AT TIME ZONE 'UTC')::date
        """, (vk_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "quests": row["quest_json"],
            "progress": row["progress_json"],
            "streak": row["streak"],
            "last_complete": row["last_complete"],
            "claimed": row["claimed"],
            "quest_date": row["quest_date"],
            "updated_at": row["updated_at"],
        }


def save_daily_quests(vk_id: int, quests: list, progress: dict = None, streak: int = 0):
    """Сохранить ежедневные задания для игрока"""
    import json
    with db_cursor() as (cursor, conn):
        cursor.execute("""
            INSERT INTO daily_quests (vk_id, quest_date, quest_json, progress_json, streak, claimed, updated_at)
            VALUES (%s, (NOW() AT TIME ZONE 'UTC')::date, %s, %s, %s, FALSE, NOW())
            ON CONFLICT (vk_id, quest_date)
            DO UPDATE SET
                quest_json = EXCLUDED.quest_json,
                progress_json = EXCLUDED.progress_json,
                streak = EXCLUDED.streak,
                claimed = FALSE,
                updated_at = NOW()
        """, (vk_id, json.dumps(quests, ensure_ascii=False), json.dumps(progress or {}, ensure_ascii=False), streak))


def update_quest_progress(vk_id: int, quest_id: str, increment: int = 1):
    """Обновить прогресс задания"""
    import json
    with db_cursor() as (cursor, conn):
        cursor.execute("""
            SELECT progress_json, quest_json FROM daily_quests
            WHERE vk_id = %s AND quest_date = (NOW() AT TIME ZONE 'UTC')::date
        """, (vk_id,))
        row = cursor.fetchone()
        if not row:
            return

        progress = row["progress_json"] or {}
        quests = row["quest_json"] or []
        quest_target = None
        for q in quests:
            if q.get("id") == quest_id:
                quest_target = int(q.get("target", 1))
                break
        new_value = int(progress.get(quest_id, 0)) + int(increment)
        if quest_target is not None:
            new_value = min(new_value, quest_target)
        progress[quest_id] = max(0, new_value)

        cursor.execute("""
            UPDATE daily_quests
            SET progress_json = %s,
                updated_at = NOW()
            WHERE vk_id = %s AND quest_date = (NOW() AT TIME ZONE 'UTC')::date
        """, (json.dumps(progress, ensure_ascii=False), vk_id))


def _calc_daily_xp_scale(level: int, rank_tier: int) -> float:
    """Мягкий множитель XP дейликов под прогрессию уровня/ранга."""
    lvl = max(1, int(level or 1))
    rank = max(1, int(rank_tier or 1))
    level_mult = 1.0 + min(1.6, (lvl - 1) / 130.0)
    rank_mult = 1.0 + min(0.7, (rank - 1) * 0.03)
    return min(2.8, level_mult * rank_mult)


def _apply_level_ups_after_xp(cursor, vk_id: int, user_row: dict) -> dict | None:
    """Синхронизировать уровень после прямого SQL-начисления XP."""
    try:
        from models.player import Player as _PlayerModel
    except Exception:
        logger.exception("Не удалось импортировать Player для синхронизации уровня: vk_id=%s", vk_id)
        return None

    old_level = int(user_row.get("level", 1) or 1)
    level = old_level
    experience = int(user_row.get("experience", 0) or 0)
    max_level = int(getattr(_PlayerModel, "MAX_LEVEL", 297) or 297)
    levels = getattr(_PlayerModel, "LEVELS", {}) or {}
    rank_tiers = getattr(_PlayerModel, "RANK_TIERS", []) or []
    rank_tier = max(1, int(user_row.get("rank_tier", 1) or 1))

    if rank_tiers and rank_tier < len(rank_tiers):
        safe_tier = max(1, min(len(rank_tiers), rank_tier))
        rank_level_cap = int(rank_tiers[safe_tier - 1].get("max_level", max_level) or max_level)
    else:
        rank_level_cap = max_level
    rank_level_cap = max(1, min(max_level, rank_level_cap))

    stat_changes = []
    stats = {
        "strength": int(user_row.get("strength", 1) or 1),
        "stamina": int(user_row.get("stamina", 1) or 1),
        "perception": int(user_row.get("perception", 1) or 1),
        "luck": int(user_row.get("luck", 1) or 1),
    }
    max_weight = int(user_row.get("max_weight", 10) or 10)
    max_health_bonus = int(user_row.get("max_health_bonus", 0) or 0)
    while level < max_level and level < rank_level_cap:
        exp_needed = int(levels.get(level + 1, levels.get(max_level, 0)) or 0)
        if exp_needed <= 0 or experience < exp_needed:
            break

        level += 1
        stat = random.choice(("strength", "stamina", "perception", "luck"))
        old_value = stats[stat]
        stats[stat] = old_value + 1
        stat_changes.append({"stat": stat, "old": old_value, "new": stats[stat]})
        if stat == "strength":
            max_weight += 2

    if level == old_level:
        return None

    from models.player import calculate_player_max_health
    max_health = calculate_player_max_health(level, stats["stamina"], max_health_bonus)

    cursor.execute(
        """
        UPDATE users
        SET level = %s,
            health = %s,
            energy = 100,
            strength = %s,
            stamina = %s,
            perception = %s,
            luck = %s,
            max_weight = %s
        WHERE vk_id = %s
        RETURNING id, money, experience, level, health, energy,
                  strength, stamina, perception, luck, max_weight
        """,
        (
            level,
            max_health,
            stats["strength"],
            stats["stamina"],
            stats["perception"],
            stats["luck"],
            max_weight,
            vk_id,
        ),
    )
    updated = cursor.fetchone()
    return {
        "old_level": old_level,
        "new_level": level,
        "rank_level_cap": rank_level_cap,
        "stat_changes": stat_changes,
        "rank_cap_reached": level >= rank_level_cap and level < max_level,
        "user": updated,
    }


def claim_daily_rewards(vk_id: int) -> dict | None:
    """
    Забрать награду за ежедневные задания.
    Возвращает dict с наградой или None, если нельзя забрать.
    """
    try:
        with db_cursor() as (cursor, conn):
            cursor.execute("""
                SELECT quest_json, progress_json, streak, claimed
                FROM daily_quests
                WHERE vk_id = %s AND quest_date = (NOW() AT TIME ZONE 'UTC')::date
                FOR UPDATE
            """, (vk_id,))
            row = cursor.fetchone()
            if not row:
                return None
            if row["claimed"]:
                return {"error": "already_claimed"}

            cursor.execute("""
                SELECT id, level, rank_tier, experience,
                       health, energy, strength, stamina, perception, luck,
                       max_weight, max_health_bonus
                FROM users
                WHERE vk_id = %s
                FOR UPDATE
            """, (vk_id,))
            user_meta = cursor.fetchone()
            if not user_meta:
                return {"error": "user_not_found"}

            user_internal_id = int(user_meta["id"])
            user_level = int(user_meta.get("level", 1) or 1)
            user_rank_tier = max(1, int(user_meta.get("rank_tier", 1) or 1))
            rank_locked_xp = False
            try:
                from models.player import Player as _PlayerModel
                tiers_total = len(_PlayerModel.RANK_TIERS)
                safe_tier = max(1, min(tiers_total, user_rank_tier))
                if safe_tier < tiers_total:
                    current_rank = _PlayerModel.RANK_TIERS[safe_tier - 1]
                    rank_level_cap = int(current_rank.get("max_level", 1) or 1)
                    rank_locked_xp = user_level >= rank_level_cap
            except Exception:
                rank_locked_xp = False

            quests = row["quest_json"] or []
            progress = row["progress_json"] or {}
            streak = row["streak"] or 0
            if not quests:
                return {"error": "not_found"}

            # Проверяем, все ли задания выполнены
            all_done = True
            for q in quests:
                qid = q["id"]
                target = max(1, int(q.get("target", 1) or 1))
                if progress.get(qid, 0) < target:
                    all_done = False
                    break

            if not all_done:
                return {"error": "not_all_complete"}

            # Считаем награду
            total_xp = 0
            total_money = 0
            bonus_items = []

            for q in quests:
                qid = q["id"]
                prog = progress.get(qid, 0)
                target = max(1, int(q.get("target", 1) or 1))
                xp = q.get("reward_xp", 0)
                money = q.get("reward_money", 0)

                # Пропорциональная награда за частичный прогресс
                ratio = min(prog, target) / target
                total_xp += int(xp * ratio)
                total_money += int(money * ratio)

            # Бонус за streak
            # Награда должна считаться по "новому" стрику (включая текущий день),
            # а не по вчерашнему значению.
            new_streak = int(streak) + 1

            from game.daily_quests import STREAK_BONUSES
            best_bonus = STREAK_BONUSES.get(1, {"multiplier": 1.0})
            for threshold, bonus in sorted(STREAK_BONUSES.items()):
                if new_streak >= int(threshold):
                    best_bonus = bonus
                else:
                    break

            mult = float(best_bonus.get("multiplier", 1.0) or 1.0)
            total_xp = int(total_xp * mult)
            total_money = int(total_money * mult)
            total_xp = int(total_xp * _calc_daily_xp_scale(user_level, user_rank_tier))
            if rank_locked_xp:
                total_xp = 0

            # Бонусный предмет выдаём только на пороговых значениях.
            from game.daily_quests import resolve_streak_bonus_item
            resolved_bonus_item = resolve_streak_bonus_item(new_streak)
            if resolved_bonus_item:
                bonus_items.append(resolved_bonus_item)

            # Обновляем streak и claimed
            cursor.execute("""
                UPDATE daily_quests
                SET claimed = TRUE,
                    streak = %s,
                    last_complete = (NOW() AT TIME ZONE 'UTC')::date,
                    updated_at = NOW()
                WHERE vk_id = %s AND quest_date = (NOW() AT TIME ZONE 'UTC')::date
            """, (new_streak, vk_id))

            # Обновляем деньги и XP игрока
            cursor.execute("""
                UPDATE users
                SET money = money + %s,
                    experience = experience + %s
                WHERE vk_id = %s
                RETURNING id, money, experience, level, rank_tier,
                          health, energy, strength, stamina, perception, luck,
                          max_weight, max_health_bonus
            """, (total_money, total_xp, vk_id))
            user_row = cursor.fetchone()
            level_up = _apply_level_ups_after_xp(cursor, vk_id, user_row) if user_row else None
            if level_up and level_up.get("user"):
                user_row = level_up["user"]

            # Бонусные предметы выдаём здесь же, в той же транзакции.
            if user_internal_id:
                for item_name, qty in bonus_items:
                    if int(qty or 0) <= 0:
                        continue
                    cursor.execute("SELECT id FROM items WHERE name = %s", (item_name,))
                    item_row = cursor.fetchone()
                    if not item_row:
                        logger.warning("claim_daily_rewards: бонусный предмет не найден: %s", item_name)
                        continue
                    cursor.execute(
                        """
                        INSERT INTO user_inventory (user_id, item_id, quantity)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (user_id, item_id)
                        DO UPDATE SET quantity = user_inventory.quantity + EXCLUDED.quantity
                        """,
                        (user_internal_id, item_row["id"], int(qty)),
                    )

            return {
                "success": True,
                "xp": total_xp,
                "money": total_money,
                "bonus_items": bonus_items,
                "new_streak": new_streak,
                "new_money": user_row["money"] if user_row else 0,
                "new_xp": user_row["experience"] if user_row else 0,
                "new_level": user_row["level"] if user_row else user_level,
                "level_up": level_up,
            }
    except Exception as e:
        logger.error("claim_daily_rewards ошибка для vk_id=%s: %s", vk_id, e)
        return {"error": "exception", "detail": str(e)}


def reset_daily_quests_if_needed(vk_id: int):
    """
    Проверить, сменился ли день. Если да - сгенерировать новые задания.
    Возвращает (quests, progress, streak) или генерирует новые.
    """
    from datetime import timezone, datetime, timedelta
    from game.daily_quests import generate_daily_quests

    existing = get_daily_quests_for_user(vk_id)
    if existing is not None:
        user_row = get_user_by_vk(vk_id) or {}
        user_level = int(user_row.get("level", 1) or 1)
        user_location = user_row.get("location")
        from game.daily_quests import _is_quest_available_for_player
        needs_repair = (
            not bool(existing.get("claimed"))
            and any(
                not _is_quest_available_for_player(q, player_level=user_level, current_location=user_location)
                for q in existing.get("quests", [])
            )
        )
        if needs_repair:
            today_seed = datetime.now(timezone.utc).date().strftime("%Y-%m-%d")
            new_quests = generate_daily_quests(
                today_seed,
                player_level=user_level,
                current_location=user_location,
            )
            old_progress = existing.get("progress", {}) or {}
            new_ids = {q.get("id") for q in new_quests}
            repaired_progress = {
                qid: value for qid, value in old_progress.items()
                if qid in new_ids
            }
            save_daily_quests(vk_id, new_quests, progress=repaired_progress, streak=int(existing.get("streak", 0) or 0))
            return new_quests, repaired_progress, int(existing.get("streak", 0) or 0)
        return existing["quests"], existing["progress"], existing["streak"]

    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)

    streak_seed = 0
    with db_cursor() as (cursor, _):
        cursor.execute("""
            SELECT quest_date, streak, claimed
            FROM daily_quests
            WHERE vk_id = %s
            ORDER BY quest_date DESC
            LIMIT 1
        """, (vk_id,))
        prev = cursor.fetchone()
        if prev and prev["claimed"] and prev["quest_date"] == yesterday:
            streak_seed = int(prev["streak"] or 0)

    user_row = get_user_by_vk(vk_id) or {}
    user_level = int(user_row.get("level", 1) or 1)
    user_location = user_row.get("location")
    quests = generate_daily_quests(
        today.strftime("%Y-%m-%d"),
        player_level=user_level,
        current_location=user_location,
    )
    save_daily_quests(vk_id, quests, progress={}, streak=streak_seed)
    return quests, {}, streak_seed


def track_quest_progress(vk_id: int, quest_type: str, location: str = None, increment: int = 1) -> dict:
    """
    Автоматически обновить прогресс подходящих заданий.
    Вызывается при действиях игрока.
    """
    result = {
        "updated": [],
        "completed_now": [],
        "all_completed": False,
        "all_completed_now": False,
    }

    existing = get_daily_quests_for_user(vk_id)
    if not existing:
        quests, progress, streak = reset_daily_quests_if_needed(vk_id)
        existing = {"quests": quests, "progress": progress, "streak": streak}

    quests = existing["quests"]
    progress_map = dict(existing.get("progress") or {})

    def _all_done(progress_dict: dict) -> bool:
        if not quests:
            return False
        for quest in quests:
            target = max(1, int(quest.get("target", 1) or 1))
            if int(progress_dict.get(quest["id"], 0) or 0) < target:
                return False
        return True

    all_done_before = _all_done(progress_map)

    for q in quests:
        qid = q["id"]
        qtype = q.get("type")
        qloc = q.get("location")

        matched = False
        if qtype == quest_type:
            if qloc is None or qloc == location:
                matched = True
        elif qtype == "kill_any" and quest_type in ("kill", "kill_any"):
            matched = True

        if matched:
            target = max(1, int(q.get("target", 1) or 1))
            before = int(progress_map.get(qid, 0) or 0)
            update_quest_progress(vk_id, qid, increment)
            after = min(target, before + max(0, int(increment or 0)))
            progress_map[qid] = after
            update_entry = {
                "id": qid,
                "text": q.get("text", qid),
                "before": before,
                "after": after,
                "target": target,
                "completed": after >= target,
            }
            result["updated"].append(update_entry)
            if before < target <= after:
                result["completed_now"].append(update_entry)

    all_done_after = _all_done(progress_map)
    result["all_completed"] = all_done_after
    result["all_completed_now"] = (not all_done_before) and all_done_after
    return result


# =========================================================================
# Выбросы (Emissions)
# =========================================================================

def init_emission_table():
    """Создать таблицу выбросов"""
    with db_cursor() as (cursor, conn):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS emissions (
                id              SERIAL PRIMARY KEY,
                emission_type   VARCHAR(20) NOT NULL DEFAULT 'normal',
                warning_time    TIMESTAMP NOT NULL,
                impact_time     TIMESTAMP NOT NULL,
                end_time        TIMESTAMP NOT NULL,
                aftermath_end   TIMESTAMP NOT NULL,
                status          VARCHAR(20) NOT NULL DEFAULT 'pending',
                admin_triggered BOOLEAN NOT NULL DEFAULT FALSE,
                created_at      TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_emissions_status
            ON emissions(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_emissions_impact
            ON emissions(impact_time)
        """)


def create_emission_schedule(warning_time, impact_time, end_time, aftermath_end,
                              emission_type='normal', admin_triggered=False):
    """Создать расписание выброса"""
    with db_cursor() as (cursor, conn):
        cursor.execute("""
            INSERT INTO emissions (warning_time, impact_time, end_time, aftermath_end,
                                   emission_type, admin_triggered, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'pending')
            RETURNING id
        """, (warning_time, impact_time, end_time, aftermath_end, emission_type, admin_triggered))
        return cursor.fetchone()["id"]


def get_active_emission():
    """Получить текущий активный выброс (warning или impact phase)"""
    with db_cursor() as (cursor, _):
        cursor.execute("""
            SELECT * FROM emissions
            WHERE
                -- impact должен оставаться "активным" до смены статуса на finished
                -- (иначе тик не увидит событие и не переведет в aftermath)
                status = 'impact'
                OR
                -- warning валиден только после warning_time
                (status = 'warning' AND warning_time <= NOW())
                OR
                -- pending живет до планового конца окна выброса
                (status = 'pending' AND end_time > NOW())
            ORDER BY
                CASE status
                    WHEN 'impact' THEN 0
                    WHEN 'warning' THEN 1
                    ELSE 2
                END,
                -- среди impact сначала самый свежий (текущий/только что завершившийся)
                CASE WHEN status = 'impact' THEN end_time END DESC,
                -- среди warning/pending — ближайший по impact_time
                CASE WHEN status IN ('warning', 'pending') THEN impact_time END ASC
            LIMIT 1
        """)
        row = cursor.fetchone()
        if not row:
            return None
        result = dict(row)
        # Нормализуем datetime — убираем tzinfo если есть (psycopg2 может вернуть aware)
        for field in ('warning_time', 'impact_time', 'end_time', 'aftermath_end'):
            if result.get(field) and hasattr(result[field], 'tzinfo') and result[field].tzinfo:
                result[field] = result[field].replace(tzinfo=None)
        return result


def get_emission_aftermath_active():
    """Проверить, активна ли фаза последствий выброса"""
    with db_cursor() as (cursor, _):
        cursor.execute("""
            SELECT id, aftermath_end FROM emissions
            WHERE status = 'finished'
              AND aftermath_end > NOW()
            ORDER BY aftermath_end DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        return dict(row) if row else None


def update_emission_status(emission_id: int, status: str):
    """Обновить статус выброса"""
    with db_cursor() as (cursor, conn):
        cursor.execute("""
            UPDATE emissions SET status = %s WHERE id = %s
        """, (status, emission_id))


def reconcile_emission_statuses() -> dict:
    """
    Привести статусы выбросов в консистентное состояние по времени.

    Возвращает:
        {
            "reset_to_pending": [id, ...],
            "finished_impacts": [{"id": int, "aftermath_end": datetime}, ...],
            "cancelled_warnings": [id, ...],
            "cancelled_pendings": [id, ...],
        }
    """
    with db_cursor() as (cursor, _):
        # warning с warning_time в будущем — это рассинхрон, откатываем в pending
        cursor.execute("""
            UPDATE emissions
               SET status = 'pending'
             WHERE status = 'warning'
               AND warning_time > NOW()
         RETURNING id
        """)
        reset_to_pending = [r["id"] for r in cursor.fetchall()]

        # impact, у которого end_time уже прошёл — должен быть finished
        cursor.execute("""
            UPDATE emissions
               SET status = 'finished'
             WHERE status = 'impact'
               AND end_time <= NOW()
         RETURNING id, aftermath_end
        """)
        finished_impacts = [dict(r) for r in cursor.fetchall()]

        # warning/pending, у которых окно полностью истекло — считаем отменёнными
        cursor.execute("""
            UPDATE emissions
               SET status = 'cancelled'
             WHERE status = 'warning'
               AND end_time <= NOW()
         RETURNING id
        """)
        cancelled_warnings = [r["id"] for r in cursor.fetchall()]

        cursor.execute("""
            UPDATE emissions
               SET status = 'cancelled'
             WHERE status = 'pending'
               AND end_time <= NOW()
         RETURNING id
        """)
        cancelled_pendings = [r["id"] for r in cursor.fetchall()]

    return {
        "reset_to_pending": reset_to_pending,
        "finished_impacts": finished_impacts,
        "cancelled_warnings": cancelled_warnings,
        "cancelled_pendings": cancelled_pendings,
    }


def get_all_active_players():
    """Получить всех активных игроков (vk_id, location, name, health)"""
    with db_cursor() as (cursor, _):
        cursor.execute("""
            SELECT vk_id, location, previous_location, name, health, level
            FROM users
            WHERE is_banned = 0
        """)
        return [dict(r) for r in cursor.fetchall()]


def get_emission_stats():
    """Получить статистику по выбросам"""
    with db_cursor() as (cursor, _):
        cursor.execute("""
            SELECT
                COUNT(*) as total_emissions,
                COUNT(*) FILTER (WHERE status = 'impact') as active_emissions,
                COUNT(*) FILTER (WHERE admin_triggered = TRUE) as admin_triggered,
                MAX(created_at) as last_emission
            FROM emissions
        """)
        row = cursor.fetchone()
        return dict(row) if row else {}


def record_emission_damage(vk_id: int, emission_id: int, damage: int, radiation: int,
                           items_lost: int, was_safe: bool):
    """Записать урон от выброса для игрока"""
    with db_cursor() as (cursor, conn):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS emission_damage_log (
                id              SERIAL PRIMARY KEY,
                vk_id           BIGINT NOT NULL,
                emission_id     INTEGER NOT NULL REFERENCES emissions(id),
                damage          INTEGER NOT NULL DEFAULT 0,
                radiation       INTEGER NOT NULL DEFAULT 0,
                items_lost      INTEGER NOT NULL DEFAULT 0,
                was_safe        BOOLEAN NOT NULL DEFAULT FALSE,
                created_at      TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)
        cursor.execute("""
            INSERT INTO emission_damage_log (vk_id, emission_id, damage, radiation, items_lost, was_safe)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (vk_id, emission_id, damage, radiation, items_lost, was_safe))
