"""
База данных для игры "Город N: Запретная Зона"
PostgreSQL с пулом соединений, нормальной схемой и корректной обработкой ошибок.

Ключевые изменения по сравнению с предыдущей версией:
- Экипировка вынесена в отдельную таблицу user_equipment (slot/item_name)
- menu_state и inventory_section убраны из БД — они в state_manager
- update_user_stats() переписан на **kwargs — добавление поля не требует трогать сигнатуру
- Все функции используют контекстный менеджер db_cursor() — соединения не утекают
- Покупка/продажа атомарны — нельзя потерять деньги без предмета
- Убраны дубли предметов в init_db()
- get_user_by_vk() возвращает плоский dict совместимый со старым кодом
"""

import logging
import math
import threading
import time
from contextlib import contextmanager
from datetime import datetime

import psycopg2
from psycopg2 import pool, OperationalError, DatabaseError
from psycopg2.extras import RealDictCursor

import config

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
    return get_connection_pool().getconn()


def release_connection(conn):
    get_connection_pool().putconn(conn)


# ---------------------------------------------------------------------------
# Контекстный менеджер — основа всей работы с БД
# Гарантирует что соединение вернётся в пул даже при исключении.
# ---------------------------------------------------------------------------

@contextmanager
def db_cursor():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            yield cursor, conn
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        release_connection(conn)


# ---------------------------------------------------------------------------
# Retry-декоратор для нестабильных соединений
# ---------------------------------------------------------------------------

def with_retry(max_retries=None, delay=None):
    if max_retries is None:
        max_retries = config.DB_MAX_RETRIES
    if delay is None:
        delay = config.DB_RETRY_DELAY

    def decorator(func):
        from functools import wraps

        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (OperationalError, DatabaseError) as e:
                    last_exc = e
                    logger.warning(
                        "БД ошибка в %s, попытка %d/%d: %s",
                        func.__name__, attempt + 1, max_retries, e,
                    )
                    if attempt < max_retries - 1:
                        time.sleep(delay * (attempt + 1))
            raise last_exc

        return wrapper

    return decorator


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
                artifact_slots    INTEGER DEFAULT 3,
                shells            INTEGER DEFAULT 0,
                player_class      VARCHAR(50),
                previous_location VARCHAR(50),
                hospital_treatments INTEGER DEFAULT 0,
                newbie_kit_received INTEGER DEFAULT 0,
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
                bonus_value   INTEGER      DEFAULT 0
            )
        """)

        # -- user_inventory -------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_inventory (
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
                price_per_item  INTEGER     NOT NULL CHECK (price_per_item > 0),
                listing_fee     INTEGER     NOT NULL DEFAULT 0,
                sale_fee        INTEGER     NOT NULL DEFAULT 0,
                status          VARCHAR(20) NOT NULL DEFAULT 'active',
                created_at      TIMESTAMP   NOT NULL DEFAULT NOW(),
                expires_at      TIMESTAMP   NOT NULL,
                completed_at    TIMESTAMP,
                cancelled_at    TIMESTAMP,
                expired_at      TIMESTAMP
            )
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
                price_per_item  INTEGER     NOT NULL,
                total_price     INTEGER     NOT NULL,
                sale_fee        INTEGER     NOT NULL,
                created_at      TIMESTAMP   NOT NULL DEFAULT NOW()
            )
        """)

        # -- Индексы --------------------------------------------------------
        for ddl in [
            "CREATE INDEX IF NOT EXISTS idx_users_vk_id          ON users(vk_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_inventory_user   ON user_inventory(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_inventory_item   ON user_inventory(item_id)",
            "CREATE INDEX IF NOT EXISTS idx_items_category        ON items(category)",
            "CREATE INDEX IF NOT EXISTS idx_user_equipment_user   ON user_equipment(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_market_listings_status ON market_listings(status)",
            "CREATE INDEX IF NOT EXISTS idx_market_listings_exp    ON market_listings(expires_at)",
            "CREATE INDEX IF NOT EXISTS idx_market_listings_seller ON market_listings(seller_vk_id)",
            "CREATE INDEX IF NOT EXISTS idx_market_trx_buyer       ON market_transactions(buyer_vk_id)",
            "CREATE INDEX IF NOT EXISTS idx_market_trx_seller      ON market_transactions(seller_vk_id)",
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
            ("artifact_slots",        "INTEGER DEFAULT 3"),
            ("shells",                "INTEGER DEFAULT 0"),
            ("is_admin",              "INTEGER DEFAULT 0"),
            ("is_banned",             "INTEGER DEFAULT 0"),
            ("ban_reason",            "TEXT"),
            ("inventory_section",     "VARCHAR(50)"),  # Текущий раздел инвентаря
        ]
        for col, definition in new_columns:
            if col not in existing:
                cursor.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {definition}")
                logger.info("Добавлена колонка users.%s", col)


# ---------------------------------------------------------------------------
# Справочник предметов
# ---------------------------------------------------------------------------

def _seed_items():
    """Заполнить таблицу items начальными данными."""

    # Формат: (name, category, description, price, attack, defense, weight)
    # Расширенный: добавить backpack_bonus или (rarity, anomaly_type, bonus_type, bonus_value)

    items = [
        # === ГИЛЬЗЫ ========================================================
        ("Гильза",  "resources", "Латунная гильза. Для добычи артефактов.", 1,  0, 0, 0.01),
        ("Гильзы",  "resources", "Связка гильз. Для добычи артефактов.",   10, 0, 0, 0.10),

        # === МЕШОЧКИ ДЛЯ ГИЛЬЗ ============================================
        ("Маленький мешочек",      "shells_bag", "Вмещает до 50 гильз.",    100,  0, 0, 0.2, 50),
        ("Средний мешочек",        "shells_bag", "Вмещает до 100 гильз.",   250,  0, 0, 0.3, 100),
        ("Большой мешочек",        "shells_bag", "Вмещает до 300 гильз.",   600,  0, 0, 0.5, 300),
        ("Профессиональный мешочек","shells_bag","Вмещает до 500 гильз.",  1200, 0, 0, 0.7, 500),
        ("Легендарный мешочек",    "shells_bag", "Вмещает до 1000 гильз.", 3000, 0, 0, 1.0, 1000),

        # === ОРУЖИЕ — ПИСТОЛЕТЫ ===========================================
        ("ПМ",   "weapons", "Пистолет Макарова. Надёжный, но слабый.",         50,  15, 0, 0.80),
        ("ТТ",   "weapons", "Пистолет Токарева. Мощнее ПМ, но ненадёжен.",     70,  20, 0, 0.90),
        ("Глок", "weapons", "Австрийский пистолет. Точный и современный.",     120,  25, 0, 0.70),
        ("Удав", "weapons", "Российский пистолет. Компактный и скорострельный.",180, 22, 0, 0.65),
        ("ПММ",  "weapons", "Модернизированный Макаров. Увеличенный магазин.",  90,  18, 0, 0.85),
        ("П-99", "weapons", "Спортивный пистолет. Высокая точность.",          140,  24, 0, 0.75),
        ("П-96", "weapons", "Профессиональный спортивный пистолет.",           200,  28, 0, 0.70),
        ("С-40П","weapons", "Самозарядный пистолет повышенной мощности.",      250,  32, 0, 0.90),

        # === ОРУЖИЕ — АВТОМАТЫ ============================================
        ("АК-74",      "weapons", "Автомат Калашникова. Хорошая огневая мощь.", 200, 35, 0, 3.5),
        ("АКС-74У",    "weapons", "Укороченный автомат. Для ближнего боя.",     180, 30, 0, 2.8),
        ("М4А1",       "weapons", "Американский карабин. Точный и лёгкий.",     220, 38, 0, 3.0),
        ("АК-101",     "weapons", "Экспортный вариант АК. Под натовский патрон.", 280, 40, 0, 3.6),
        ("АК-105",     "weapons", "Современный автомат под малокалиберный патрон.", 320, 42, 0, 3.2),
        ("ГРОЗ-35",    "weapons", "Бесшумный автомат специального назначения.", 380, 38, 0, 3.0),
        ("М4А1 Кастом","weapons", "Улучшенная версия М4 с длинным стволом.",    350, 45, 0, 3.4),
        ("АК-12",      "weapons", "Современный модульный автомат Калашникова.", 400, 48, 0, 3.5),

        # === ОРУЖИЕ — СНАЙПЕРСКИЕ =========================================
        ("СВД",     "weapons", "Снайперская винтовка Драгунова.",         350, 60, 0, 4.2),
        ("Винторез","weapons", "Снайперка с интегрированным глушителем.", 400, 70, 0, 3.8),
        ("СВ-98",   "weapons", "Снайперская винтовка повышенной точности.", 480, 75, 0, 4.5),
        ("Т-5000",  "weapons", "Точная винтовка для дальних дистанций.",  520, 80, 0, 4.8),
        ("ОСВ-96",  "weapons", "Крупнокалиберная снайперская винтовка.",  600, 95, 0, 6.0),
        ("Мосина",  "weapons", "Легендарная винтовка. Простая и надёжная.", 280, 55, 0, 3.8),
        ("ВСК-100", "weapons", "Спортивная винтовка для тренировок.",     320, 58, 0, 4.0),
        ("Лось-7",  "weapons", "Охотничий карабин. Мощный и точный.",     420, 72, 0, 4.2),

        # === ОРУЖИЕ — ДРОБОВИКИ ==========================================
        ("ИЖ-27",      "weapons", "Двуствольное охотничье ружьё.",           150, 45, 0, 3.2),
        ("Сайга-12",   "weapons", "Полуавтоматический дробовик.",            250, 40, 0, 3.5),
        ("МР-153",     "weapons", "Многозарядный дробовик. Надёжность.",     200, 48, 0, 3.3),
        ("Вепрь-12",   "weapons", "Самозарядный дробовик.",                  280, 52, 0, 3.6),
        ("Кострома",   "weapons", "Дробовик с длинным стволом. Точность.",   320, 55, 0, 3.8),
        ("Бекас-Авто", "weapons", "Автоматический дробовик для спорта.",     350, 50, 0, 3.4),
        ("Сайга-410",  "weapons", "Дробовик под малокалиберный патрон.",     220, 42, 0, 3.0),

        # === ОРУЖИЕ — ПУЛЕМЁТЫ ===========================================
        ("ПКМ",    "weapons", "Пулемёт Калашникова. Огонь на подавление.", 450, 30, 0, 7.5),
        ("РПК-74", "weapons", "Ручной пулемёт. Баланс мобильности и огня.", 380, 28, 0, 5.0),
        ("Печенег","weapons", "Модернизированный ПК. Повышенная надёжность.", 520, 35, 0, 8.0),
        ("М240",   "weapons", "Американский пулемёт. Тяжёлый, но мощный.", 580, 38, 0, 8.5),
        ("М249",   "weapons", "Лёгкий пулемёт. Мобильный огонь.",          480, 32, 0, 6.5),
        ("РПК-16", "weapons", "Современный ручной пулемёт.",                550, 36, 0, 6.0),
        ("Корд",   "weapons", "Крупнокалиберный пулемёт. Бронебойный.",     650, 42, 0, 10.0),

        # === ОРУЖИЕ — НОЖИ ===============================================
        ("Нож сталкера",  "weapons", "Простой нож. Лучше, чем ничего.",       30,  10, 0, 0.30),
        ("Мачете",        "weapons", "Длинный нож для рубки.",                60,  15, 0, 0.80),
        ("Нож разведчика","weapons", "Армейский нож. Прочный и острый.",      80,  18, 0, 0.35),
        ("Штык-нож",      "weapons", "Штык от автомата. Многофункциональный.", 70, 16, 0, 0.40),
        ("Финка",         "weapons", "Финский нож. Классика.",                50,  12, 0, 0.25),
        ("Кинжал",        "weapons", "Острый кинжал. Смертоносный в ближнем бою.", 90, 20, 0, 0.45),
        ("Ятаган",        "weapons", "Изогнутый клинок. Мощный рубящий удар.", 120, 22, 0, 0.90),

        # === БРОНЯ — ШЛЕМЫ ===============================================
        ("Вязаная шапка",    "armor", "Старая шапка. От холода, не от пуль.",   10,  0,  2, 0.20),
        ("Кепка",            "armor", "Лёгкая кепка. Минимальная защита.",       8,  0,  2, 0.15),
        ("Каска",            "armor", "Советская каска. Лёгкая защита.",         50,  0,  8, 0.80),
        ("Баллистический шлем","armor","Современный бронешлем.",               150,  0, 20, 1.20),
        ("Шлем-штурмовик",   "armor", "Усиленный шлем с забралом.",            220,  0, 25, 1.50),
        ("Шлем связиста",    "armor", "Шлем со встроенными наушниками.",       180,  0, 22, 1.30),
        ("Тактический шлем", "armor", "Лёгкий тактический шлем.",             280,  0, 28, 1.40),
        ("Десантный шлем",   "armor", "Шлем десантника. Прочный.",            200,  0, 24, 1.60),
        ("Шлем спецназа",    "armor", "Профессиональный шлем.",               350,  0, 32, 1.80),

        # === БРОНЯ — ТЕЛО ================================================
        ("Кожаная куртка",   "armor", "Минимальная защита.",        30,  0,  2, 1.5),
        ("Бронежилет",       "armor", "Армейский бронежилет.",     100,  0, 18, 3.0),
        ("Комбинезон сталкера","armor","Спецкостюм для Зоны.",     300,  0, 35, 5.0),
        ("Бронекостюм",      "armor", "Полный бронекостюм.",       450,  0, 45, 8.0),
        ("Скафандр",         "armor", "Изолирует от радиации.",    500,  0, 40, 7.5),
        ("Боевой комбинезон","armor", "Усиленный боевой комбинезон.", 380, 0, 38, 6.0),
        ("Штурмовой костюм", "armor", "Костюм для штурмовых операций.", 420, 0, 42, 6.5),
        ("Экзоскелет",       "armor", "Тяжёлая броня с приводом.", 600,  0, 55, 15.0),

        # === БРОНЯ — ШТАНЫ ===============================================
        ("Джинсы",           "armor", "Базовая защита ног.",                10,  0,  2, 0.5),
        ("Камуфляжные штаны","armor", "Военные штаны с карманами.",         40,  0,  8, 0.8),
        ("Боевой костюм",    "armor", "Штаны от боевого костюма.",         120,  0, 20, 1.5),
        ("Бронештаны",       "armor", "Штаны с бронепластинами.",          180,  0, 25, 2.0),
        ("Тактические штаны","armor", "Штаны с множеством карманов.",      150,  0, 22, 1.8),
        ("Горные штаны",     "armor", "Прочные штаны для горной местности.", 100, 0, 15, 1.3),
        ("Зимние штаны",     "armor", "Утеплённые штаны.",                 130,  0, 18, 1.6),
        ("Спецштаны",        "armor", "Штаны для спецподразделений.",      200,  0, 28, 2.2),

        # === БРОНЯ — ПЕРЧАТКИ ============================================
        ("Тканевые перчатки",    "armor", "Простые перчатки. От царапин.",      5, 0,  2, 0.10),
        ("Перчатки без пальцев", "armor", "Лёгкая защита.",                     8, 0,  2, 0.10),
        ("Кожаные перчатки",     "armor", "Кожаные перчатки.",                 20, 0,  4, 0.20),
        ("Боевые перчатки",      "armor", "Бронеперчатки с защитой кистей.",   60, 0,  8, 0.40),
        ("Тактические перчатки", "armor", "С противоударной защитой.",         80, 0, 10, 0.45),
        ("Зимние перчатки",      "armor", "Тёплые перчатки.",                  45, 0,  6, 0.30),
        ("Мотоперчатки",         "armor", "Защита от стирания.",               55, 0,  7, 0.35),
        ("Спецперчатки",         "armor", "Со встроенной защитой.",           100, 0, 12, 0.50),
        ("Огнестойкие перчатки", "armor", "Защита от огня.",                   90, 0, 11, 0.48),

        # === БРОНЯ — БОТИНКИ =============================================
        ("Кроссовки",          "armor", "Удобные кроссовки.",              10,  0,  2, 0.40),
        ("Кеды",               "armor", "Простые кеды.",                   12,  0,  2, 0.35),
        ("Армейские ботинки",  "armor", "Прочные армейские ботинки.",      40,  0,  8, 0.80),
        ("Боевые ботинки",     "armor", "Бронированные ботинки.",          80,  0, 15, 1.20),
        ("Тактические ботинки","armor", "Для тактических операций.",      120,  0, 18, 1.40),
        ("Берцы",              "armor", "Классические военные ботинки.",   60,  0, 12, 1.00),
        ("Треккинговые ботинки","armor","Удобные и прочные.",              70,  0, 10, 0.90),
        ("Зимние ботинки",     "armor", "Утеплённые ботинки.",             90,  0, 14, 1.30),
        ("Спецботинки",        "armor", "Ботинки для спецназа.",          150,  0, 20, 1.60),

        # === АРТЕФАКТЫ — ОБЫЧНЫЕ (common) ================================
        ("Слизь",           "artifacts", "Скользкий сгусток из тумана.",         400, 0, 0, 0.4, 0, "common", "туман",    "health_dodge", 10),
        ("Пружина",         "artifacts", "Упругая пружина из воронки.",          350, 0, 8, 0.3, 0, "common", "воронка",  "armor_dodge",  8),
        ("Пустышка",        "artifacts", "Пустой артефакт, но полезный.",        500, 0, 0, 0.2, 0, "common", "магнит",   "luck",         5),
        ("Капля",           "artifacts", "Капля аномальной жидкости.",           320, 0, 0, 0.3, 0, "common", "туман",    "health_rad",   8),
        ("Слюда",           "artifacts", "Прозрачная пластина.",                 450, 0, 0, 0.25,0, "common", "жарка",    "damage_resist",5),
        ("Вспышка",         "artifacts", "Мерцающий артефакт.",                  550, 0, 0, 0.2, 0, "common", "электра",  "find_perception",10),
        ("Бенгальский огонь","artifacts","Яркий искрящийся артефакт.",           600, 0, 0, 0.25,0, "common", "электра",  "damage_boost", 12),
        ("Батарейка",       "artifacts", "Электрический артефакт.",             480, 0, 0, 0.2, 0, "common", "электра",  "energy_crit",  15),
        ("Плёнка",          "artifacts", "Тонкая плёнка из тумана.",             380, 0, 0, 0.15,0, "common", "туман",    "dodge_rad",    6),
        ("Ломоть мяса",     "artifacts", "Кусок мутировавшей плоти.",            250, 0, 0, 0.5, 0, "common", "туман",    "health",       12),

        # === АРТЕФАКТЫ — РЕДКИЕ (rare) ====================================
        ("Грави",           "artifacts", "Тяжёлый артефакт с искажающим полем.", 2500, 0, 20, 2.0, 0, "rare", "воронка", "armor",       20),
        ("Выверт",          "artifacts", "Нестабильный пси-артефакт.",           1800, 0, 0,  0.3, 0, "rare", "туман",   "dodge",       15),
        ("Слизняк",         "artifacts", "Скользкий организм.",                  1200, 0, 0,  0.5, 0, "rare", "туман",   "health_dodge",15),
        ("Огненный шар",    "artifacts", "Пылающий шар из жарки.",              1500, 0, 10, 0.6, 0, "rare", "жарка",   "damage_fire", 15),
        ("Золотая рыбка",   "artifacts", "Редкий гравитационный артефакт.",     3000, 0, 0,  0.5, 0, "rare", "воронка", "luck",        15),
        ("Ночная звезда",   "artifacts", "Мерцающий гравитационный артефакт.",  2200, 0, 0,  0.4, 0, "rare", "воронка", "max_weight",  10),
        ("Колобок",         "artifacts", "Странный пульсирующий шар.",          1600, 0, 0,  0.35,0, "rare", "воронка", "multi",       10),
        ("Морской ёж",      "artifacts", "Острый электрический артефакт.",      1400, 0, 8,  0.45,0, "rare", "электра", "damage_armor",18),
        ("Колючка",         "artifacts", "Острая игла из магнита.",             1100, 0, 10, 0.3, 0, "rare", "магнит",  "armor_crit",  10),
        ("Кровь камня",     "artifacts", "Тёмно-красный минерал.",              1800, 0, 20, 0.8, 0, "rare", "жарка",   "armor_resist",20),
        ("Каменный цветок", "artifacts", "Кристаллическое образование.",        1700, 0, 0,  0.5, 0, "rare", "жарка",   "damage_resist",12),
        ("Мамины бусы",     "artifacts", "Семейная реликвия из воронки.",       2800, 0, 0,  0.3, 0, "rare", "воронка", "luck_rad",    20),
        ("Лунный свет",     "artifacts", "Светящийся пси-артефакт.",            2800, 0, 0,  0.2, 0, "rare", "воронка", "max_energy",  20),

        # === АРТЕФАКТЫ — УНИКАЛЬНЫЕ (unique) =============================
        ("Кристальная колючка","artifacts","Сверкающий кристалл.",  4500, 0, 25, 0.6, 0, "unique", "магнит", "armor_crit_dodge",25),
        ("Кристалл",           "artifacts","Острый кристалл.",      4000, 0, 15, 0.5, 0, "unique", "жарка",  "crit_armor",      20),
        ("Медуза",             "artifacts","Светящийся артефакт.",  3500, 0, 0,  0.5, 0, "unique", "жарка",  "damage_resist",   15),

        # === АРТЕФАКТЫ — ЛЕГЕНДАРНЫЕ (legendary) =========================
        ("Душа", "legendary_artifacts", "Артефакт чистой энергии Зоны. +30% ко всему!", 15000, 0, 0, 0.1, 0, "legendary", "воронка", "all_stats", 30),

        # === РЮКЗАКИ =====================================================
        ("Походный рюкзак",   "backpacks", "Обычный походный рюкзак.",          80,  0, 0, 3.0, 15),
        ("Военный рюкзак",    "backpacks", "Армейский рюкзак.",                150,  0, 0, 4.0, 25),
        ("Тактический рюкзак","backpacks", "Тактический рюкзак.",              250,  0, 0, 5.0, 40),
        ("Грузовой рюкзак",   "backpacks", "Большой грузовой рюкзак.",         400,  0, 0, 8.0, 60),

        # === МЕДИЦИНА (для магазина учёного) =============================
        ("Аптечка",          "meds", "Стандартная армейская аптечка. +50 HP.",  60,  0, 0, 0.30),
        ("Научная аптечка",  "meds", "Улучшенная аптечка учёных. +80 HP.",     120,  0, 0, 0.25),
        ("Бинт",             "meds", "Обычный бинт. +20 HP.",                   25,  0, 0, 0.10),
        ("Стимулятор",       "meds", "Военный стимулятор. +50 HP, +20 энергии.", 80, 0, 0, 0.10),
        ("Боевой стимулятор","meds", "Мощный стимулятор. +80 HP, +50 энергии.",150,  0, 0, 0.08),

        # === ЕДА (для магазина учёного) ==================================
        ("Энергетический батончик","food", "Солдатский паёк. +40 энергии.",  40, 0, 0, 0.15),
        ("Банка Энергетика",       "food", "Энергетический напиток. +60 энергии.", 70, 0, 0, 0.20),
        ("Чистая вода",            "food", "Отфильтрованная вода. +30 HP, -10 рад.", 50, 0, 0, 0.30),

        # === ДРУГОЕ — медицина и еда =====================================
        ("Хлеб",    "other", "Чёрствый хлеб. Лучше, чем ничего.",  10, 0, 0, 0.30),
        ("Тушёнка", "other", "Банка тушёнки. Восстанавливает силы.", 15, 0, 0, 0.40),
        ("Консервы","other", "Разные консервы. Сытно.",              12, 0, 0, 0.35),
        ("Кофе",    "other", "Банка кофе. Бодрит.",                   8, 0, 0, 0.25),
        ("Энергетик","other","Восстанавливает силы.",                 10, 0, 0, 0.25),
        ("Супер энергетик","other","Полностью восстанавливает энергию.", 50, 0, 0, 0.30),
        ("Вода",    "other", "Бутылка воды. Утоляет жажду.",          5, 0, 0, 0.50),
        ("Антирад", "other", "Выводит радиацию.",                    30, 0, 0, 0.20),

        # === ДРУГОЕ — приборы ============================================
        ("Детектор аномалий","other", "Обнаруживает аномалии.",      800, 0, 0, 0.50),
        ("Дозиметр",         "other", "Измеряет радиацию.",           25, 0, 0, 0.30),
        ("Фонарик",          "other", "Освещает темноту.",            15, 0, 0, 0.40),
        ("Компас",           "other", "Простой компас.",              10, 0, 0, 0.10),
        ("Рация",            "other", "Рация для связи.",             40, 0, 0, 0.80),

        # === РЕДКОЕ ОРУЖИЕ (с людей) =====================================
        ("Коготь кровососа", "rare_weapons", "Острый коготь мутанта.",        150, 25, 0, 0.5),
        ("Кость снорка",     "rare_weapons", "Обточенная кость снорка.",      100, 18, 0, 0.4),
        ("Клинок химеры",    "rare_weapons", "Лезвие из кости химеры.",       200, 30, 0, 0.6),
        ("Нож рейдера",      "rare_weapons", "Нож погибшего рейдера.",        120, 20, 0, 0.35),
        ("Топор выжившего",  "rare_weapons", "Самодельный топор.",            180, 28, 0, 0.9),
        ("Кастет",           "rare_weapons", "Стальной кастет.",               90, 15, 0, 0.3),
        ("Боевой молот",     "rare_weapons", "Тяжёлый молот. Один удар.",     250, 35, 0, 1.2),

        # === РЕДКАЯ БРОНЯ (с людей) ======================================
        ("Шкура волка",         "rare_armor", "Тёплая и прочная.",    100, 0, 12, 1.5),
        ("Броня из кожи химеры","rare_armor", "Прочная кожа химеры.", 180, 0, 18, 2.5),
        ("Шлем рейдера",        "rare_armor", "Бронированный шлем.",  150, 0, 15, 1.0),
        ("Бронежилет спецназа", "rare_armor", "Лучшая защита.",       300, 0, 28, 3.5),

        # === РАСХОДНИКИ (с монстров и людей) =============================
        ("Лечебная трава",        "consumables", "Трава из Зоны. +25 HP.",              30,  0, 0, 0.08),
        ("Витамины",              "consumables", "+10 к макс. HP навсегда.",           100,  0, 0, 0.05),
        ("Ремнабор",              "consumables", "Восстанавливает 10 защиты.",          60,  0, 0, 0.15),
        ("Антидот",               "consumables", "Средство от отравления. -30 рад.",   70,  0, 0, 0.10),
        ("Боевой стимулятор упак","consumables", "+80 HP, +50 энергии.",              150,  0, 0, 0.08),

        # === МУСОР (выпадает с монстров) =================================
        ("Ржавая гильза",    "trash", "Уже ни на что не годна.",   1, 0, 0, 0.01),
        ("Сломанный патрон", "trash", "Патрон без пороха.",        1, 0, 0, 0.01),
        ("Пустая гильза",    "trash", "Пустая латунная гильза.",   1, 0, 0, 0.01),
        ("Ржавый болт",      "trash", "Покрытый ржавчиной болт.",  1, 0, 0, 0.02),
        ("Обрывок проволоки","trash", "Кусок ржавой проволоки.",   1, 0, 0, 0.03),
        ("Грязная тряпка",   "trash", "Вонючая тряпка.",           2, 0, 0, 0.05),
        ("Пустая банка",     "trash", "Пустая консервная банка.",  1, 0, 0, 0.05),
        ("Пустая бутылка",   "trash", "Бутылка из-под водки.",     2, 0, 0, 0.08),
        ("Кость",            "trash", "Чья-то кость.",             3, 0, 0, 0.15),
        ("Мокрая газета",    "trash", "Нечитаемая газета.",        2, 0, 0, 0.08),
        ("Ржавая железка",   "trash", "Кусок ржавого железа.",     4, 0, 0, 0.15),
        ("Сломанный нож",    "trash", "Затупившийся ржавый нож.",  5, 0, 0, 0.15),
        ("Мёртвый артефакт", "trash", "Потухший артефакт.",        8, 0, 0, 0.08),
        ("Патрон 5.45",      "trash", "Один патрон для АК.",       2, 0, 0, 0.10),
        ("Патрон 9мм",       "trash", "Пистолетный патрон.",       2, 0, 0, 0.12),
        ("Медная проволока", "trash", "Кусок медной проволоки.",   8, 0, 0, 0.06),
        ("Зажигалка",        "trash", "Зажигалка не работает.",    2, 0, 0, 0.06),
        ("Монета",           "trash", "Старая монетка.",           3, 0, 0, 0.06),
        ("Документ",         "trash", "Документ, весь в крови.",   8, 0, 0, 0.05),
        ("Фотография",       "trash", "Старая размытая фотография.", 4, 0, 0, 0.05),
    ]

    with db_cursor() as (cursor, conn):
        for item in items:
            _insert_item(cursor, item)

    logger.info("Справочник предметов заполнен")


def _insert_item(cursor, item: tuple):
    """Вставить один предмет. ON CONFLICT DO UPDATE обновляет всё кроме id."""
    if len(item) == 7:
        name, category, description, price, attack, defense, weight = item
        cursor.execute("""
            INSERT INTO items (name, category, description, price, attack, defense, weight,
                               rarity, anomaly_type, bonus_type, bonus_value)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'common',NULL,NULL,0)
            ON CONFLICT (name) DO UPDATE SET
                category=EXCLUDED.category, description=EXCLUDED.description,
                price=EXCLUDED.price, attack=EXCLUDED.attack,
                defense=EXCLUDED.defense, weight=EXCLUDED.weight
        """, (name, category, description, price, attack, defense, weight))

    elif len(item) == 8:
        name, category, description, price, attack, defense, weight, backpack_bonus = item
        cursor.execute("""
            INSERT INTO items (name, category, description, price, attack, defense, weight,
                               backpack_bonus, rarity, anomaly_type, bonus_type, bonus_value)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'common',NULL,NULL,0)
            ON CONFLICT (name) DO UPDATE SET
                category=EXCLUDED.category, description=EXCLUDED.description,
                price=EXCLUDED.price, attack=EXCLUDED.attack,
                defense=EXCLUDED.defense, weight=EXCLUDED.weight,
                backpack_bonus=EXCLUDED.backpack_bonus
        """, (name, category, description, price, attack, defense, weight, backpack_bonus))

    elif len(item) == 11:
        name, category, description, price, attack, defense, weight, \
            backpack_bonus, rarity, anomaly_type, bonus_type = item
        # этот формат не используется — оставлен для совместимости
        pass

    elif len(item) == 12:
        name, category, description, price, attack, defense, weight, \
            backpack_bonus, rarity, anomaly_type, bonus_type, bonus_value = item
        cursor.execute("""
            INSERT INTO items (name, category, description, price, attack, defense, weight,
                               backpack_bonus, rarity, anomaly_type, bonus_type, bonus_value)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (name) DO UPDATE SET
                category=EXCLUDED.category, description=EXCLUDED.description,
                price=EXCLUDED.price, attack=EXCLUDED.attack,
                defense=EXCLUDED.defense, weight=EXCLUDED.weight,
                backpack_bonus=EXCLUDED.backpack_bonus,
                rarity=EXCLUDED.rarity, anomaly_type=EXCLUDED.anomaly_type,
                bonus_type=EXCLUDED.bonus_type, bonus_value=EXCLUDED.bonus_value
        """, (name, category, description, price, attack, defense, weight,
              backpack_bonus, rarity, anomaly_type, bonus_type, bonus_value))


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
        "artifact_1": "equipped_artifact_1",
        "artifact_2": "equipped_artifact_2",
        "artifact_3": "equipped_artifact_3",
        # legacy поле — оставляем для совместимости
        "armor":      "equipped_armor",
    }
    # Дефолты
    for field in slot_to_field.values():
        result.setdefault(field, None)

    for row in equipment_rows:
        field = slot_to_field.get(row["slot"])
        if field:
            result[field] = row["item_name"]

    # Флаги
    for row in flags_rows:
        result[row["flag_name"]] = row["value"]

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
    "equipped_artifact_1":   "artifact_1",
    "equipped_artifact_2":   "artifact_2",
    "equipped_artifact_3":   "artifact_3",
}


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
        cursor.execute("SELECT id FROM users WHERE vk_id = %s", (vk_id,))
        row = cursor.fetchone()
        if not row:
            return []
        cursor.execute("""
            SELECT i.name, i.category, i.description, i.price,
                   i.attack, i.defense, i.weight, i.backpack_bonus,
                   ui.quantity
            FROM user_inventory ui
            JOIN items i ON ui.item_id = i.id
            WHERE ui.user_id = %s
        """, (row["id"],))
        return [dict(r) for r in cursor.fetchall()]


def add_item_to_inventory(vk_id: int, item_name: str, quantity: int = 1) -> bool:
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
            INSERT INTO user_inventory (user_id, item_id, quantity)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, item_id)
            DO UPDATE SET quantity = user_inventory.quantity + %s
        """, (user["id"], item["id"], quantity, quantity))
    return True


def remove_item_from_inventory(vk_id: int, item_name: str, quantity: int = 1) -> bool:
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
        """, (quantity, user["id"], item["id"], quantity))

        cursor.execute("""
            DELETE FROM user_inventory
            WHERE user_id = %s AND item_id = %s AND quantity <= 0
        """, (user["id"], item["id"]))
    return True


def drop_item_from_inventory(vk_id: int, item_name: str, quantity: int = 1) -> dict:
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
        if inv["quantity"] < quantity:
            return {"success": False, "message": f"У тебя только {inv['quantity']} шт."}

        if inv["quantity"] == quantity:
            cursor.execute(
                "DELETE FROM user_inventory WHERE user_id = %s AND item_id = %s",
                (user["id"], item["id"]),
            )
        else:
            cursor.execute("""
                UPDATE user_inventory SET quantity = quantity - %s
                WHERE user_id = %s AND item_id = %s
            """, (quantity, user["id"], item["id"]))

    return {"success": True, "message": f"✅ Ты выбросил {quantity} шт. '{item_name}'"}


# ---------------------------------------------------------------------------
# Атомарные операции покупки / продажи
# ---------------------------------------------------------------------------

def buy_item_transaction(vk_id: int, item_name: str) -> dict:
    """
    Купить предмет. Атомарно: деньги списываются и предмет добавляется
    в одной транзакции — нельзя потерять деньги без предмета.
    Возвращает {"success": bool, "message": str, "price": int}
    """
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT id FROM items WHERE name = %s", (item_name,))
        item = cursor.fetchone()
        if not item:
            return {"success": False, "message": f"Предмет '{item_name}' не найден"}

        cursor.execute("SELECT * FROM items WHERE id = %s", (item["id"],))
        item_data = dict(cursor.fetchone())
        price = item_data["price"]

        # Списываем деньги с проверкой баланса в одном запросе
        cursor.execute("""
            UPDATE users SET money = money - %s
            WHERE vk_id = %s AND money >= %s
            RETURNING id, money
        """, (price, vk_id, price))
        result = cursor.fetchone()
        if not result:
            cursor.execute("SELECT money FROM users WHERE vk_id = %s", (vk_id,))
            balance = cursor.fetchone()
            have = balance["money"] if balance else 0
            return {
                "success": False,
                "message": f"Не хватает денег. Нужно {price} руб., у тебя {have} руб.",
            }

        user_id = result["id"]

        # Добавляем предмет
        cursor.execute("""
            INSERT INTO user_inventory (user_id, item_id, quantity)
            VALUES (%s, %s, 1)
            ON CONFLICT (user_id, item_id)
            DO UPDATE SET quantity = user_inventory.quantity + 1
        """, (user_id, item_data["id"]))

    return {
        "success": True,
        "message": f"Ты купил {item_name} за {price} руб.",
        "price": price,
        "remaining_money": result["money"],
    }


def sell_item_transaction(vk_id: int, item_name: str, sell_bonus_pct: int = 0) -> dict:
    """
    Продать предмет. Атомарно: предмет убирается и деньги зачисляются
    в одной транзакции.
    sell_bonus_pct — бонус к цене от пассивных навыков класса (в процентах).
    """
    with db_cursor() as (cursor, _):
        cursor.execute("""
            SELECT i.id, i.price
            FROM items i
            WHERE i.name = %s
        """, (item_name,))
        item = cursor.fetchone()
        if not item:
            return {"success": False, "message": f"Предмет '{item_name}' не найден"}

        base_price = item["price"] // 2
        sell_price = int(base_price * (1 + sell_bonus_pct / 100))

        cursor.execute("SELECT id FROM users WHERE vk_id = %s", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return {"success": False, "message": "Пользователь не найден"}

        # Убираем предмет (проверяем что он есть)
        cursor.execute("""
            UPDATE user_inventory
            SET quantity = quantity - 1
            WHERE user_id = %s AND item_id = %s AND quantity >= 1
            RETURNING quantity
        """, (user["id"], item["id"]))
        if not cursor.fetchone():
            return {"success": False, "message": f"У тебя нет '{item_name}'"}

        cursor.execute("""
            DELETE FROM user_inventory
            WHERE user_id = %s AND item_id = %s AND quantity <= 0
        """, (user["id"], item["id"]))

        # Зачисляем деньги
        cursor.execute("""
            UPDATE users SET money = money + %s
            WHERE vk_id = %s
            RETURNING money
        """, (sell_price, vk_id))
        new_balance = cursor.fetchone()["money"]

    bonus_msg = f" (+{sell_bonus_pct}% бонус)" if sell_bonus_pct else ""
    return {
        "success": True,
        "message": f"Ты продал {item_name} за {sell_price} руб.{bonus_msg}",
        "sell_price": sell_price,
        "remaining_money": new_balance,
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

        cursor.execute("SELECT id, name FROM items WHERE LOWER(name) = LOWER(%s)", (item_name,))
        item = cursor.fetchone()
        if not item:
            return {"success": False, "message": f"Предмет '{item_name}' не найден."}

        cursor.execute("""
            INSERT INTO user_inventory (user_id, item_id, quantity)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, item_id)
            DO UPDATE SET quantity = user_inventory.quantity + EXCLUDED.quantity
        """, (user["id"], item["id"], quantity))
    return {
        "success": True,
        "message": f"Выдано: {item['name']} x{quantity} пользователю {vk_id}.",
    }


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
        SET status = 'expired', expired_at = NOW()
        WHERE id = ANY(%s)
    """, (listing_ids,))
    return len(expired_rows)


def expire_market_listings(limit: int = 200) -> int:
    with db_cursor() as (cursor, _):
        return _expire_market_listings_tx(cursor, limit=limit)


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
            SELECT quantity
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
                seller_vk_id, item_id, item_name, quantity, price_per_item,
                listing_fee, expires_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                NOW() + (%s * INTERVAL '1 hour')
            )
            RETURNING id, expires_at
        """, (
            vk_id, item["id"], item["name"], quantity, price_per_item,
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
            INSERT INTO user_inventory (user_id, item_id, quantity)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, item_id)
            DO UPDATE SET quantity = user_inventory.quantity + EXCLUDED.quantity
        """, (buyer["id"], lot["item_id"], lot["quantity"]))

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
                quantity, price_per_item, total_price, sale_fee
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            listing_id, lot["seller_vk_id"], vk_id, lot["item_id"], lot["item_name"],
            lot["quantity"], lot["price_per_item"], total_price, sale_fee
        ))

    return {
        "success": True,
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
            INSERT INTO user_inventory (user_id, item_id, quantity)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, item_id)
            DO UPDATE SET quantity = user_inventory.quantity + EXCLUDED.quantity
        """, (seller["id"], lot["item_id"], lot["quantity"]))

        cursor.execute("""
            UPDATE market_listings
            SET status = 'cancelled', cancelled_at = NOW()
            WHERE id = %s
        """, (listing_id,))

    return {
        "success": True,
        "message": f"Лот #{listing_id} снят. Предмет возвращён в инвентарь.",
    }


def get_market_listings(limit: int = 10, offset: int = 0, category: str | None = None) -> list[dict]:
    if not is_market_enabled():
        return []
    with db_cursor() as (cursor, _):
        _expire_market_listings_tx(cursor)
        if category:
            cursor.execute("""
                SELECT l.id, l.seller_vk_id, l.item_name, l.quantity, l.price_per_item,
                       (l.quantity * l.price_per_item) AS total_price,
                       l.expires_at, i.category, i.rarity
                FROM market_listings l
                JOIN items i ON i.id = l.item_id
                WHERE l.status = 'active'
                  AND l.expires_at > NOW()
                  AND i.category = %s
                ORDER BY l.created_at DESC
                LIMIT %s OFFSET %s
            """, (category, limit, offset))
        else:
            cursor.execute("""
                SELECT l.id, l.seller_vk_id, l.item_name, l.quantity, l.price_per_item,
                       (l.quantity * l.price_per_item) AS total_price,
                       l.expires_at, i.category, i.rarity
                FROM market_listings l
                JOIN items i ON i.id = l.item_id
                WHERE l.status = 'active'
                  AND l.expires_at > NOW()
                ORDER BY l.created_at DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_market_user_listings(vk_id: int, status: str = "active", limit: int = 20) -> list[dict]:
    if not is_market_enabled():
        return []
    with db_cursor() as (cursor, _):
        _expire_market_listings_tx(cursor)
        cursor.execute("""
            SELECT id, item_name, quantity, price_per_item,
                   (quantity * price_per_item) AS total_price,
                   status, created_at, expires_at, completed_at, cancelled_at
            FROM market_listings
            WHERE seller_vk_id = %s
              AND (%s = 'all' OR status = %s)
            ORDER BY created_at DESC
            LIMIT %s
        """, (vk_id, status, status, limit))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


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

    return {"success": True, "message": f"Лот #{listing_id} принудительно снят администратором."}


# ---------------------------------------------------------------------------
# Предметы — справочные функции
# ---------------------------------------------------------------------------

def get_item_by_name(item_name: str) -> dict | None:
    items, _, _ = _get_cached_items()
    return items.get(item_name)


def get_items_by_category(category: str) -> list[dict]:
    _, by_category, _ = _get_cached_items()
    return by_category.get(category, [])


def get_items_by_rarity(rarity: str) -> list[dict]:
    all_items, _, _ = _get_cached_items()
    return [i for i in all_items.values() if i.get("rarity") == rarity]


def get_artifacts_by_rarity(rarity: str) -> list[dict]:
    artifact_categories = {"artifacts", "rare_artifacts", "legendary_artifacts"}
    all_items, _, _ = _get_cached_items()
    return [
        i for i in all_items.values()
        if i.get("rarity") == rarity and i.get("category") in artifact_categories
    ]


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


def get_random_trash(count: int = 3) -> list[dict]:
    import random
    _, by_cat, _ = _get_cached_items()
    trash = by_cat.get("trash", [])
    return random.sample(trash, min(count, len(trash))) if trash else []


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


def get_loot_from_human(player_luck: int = 5) -> list[dict]:
    import random
    _, by_cat, _ = _get_cached_items()
    weapons = by_cat.get("weapons", [])
    armor   = by_cat.get("armor", [])
    trash   = by_cat.get("trash", [])
    consumables = by_cat.get("consumables", [])

    luck_bonus = max(0, player_luck - 10) // 5
    loot = []

    if trash:
        loot.extend(random.sample(trash, min(1, len(trash))))

    roll = random.randint(1, 100)
    weapon_chance = 7 + luck_bonus
    armor_chance  = 7 + luck_bonus
    consumable_chance = 31 + luck_bonus

    if roll <= weapon_chance and weapons:
        loot.append(random.choice(weapons))
    elif roll <= weapon_chance + armor_chance and armor:
        loot.append(random.choice(armor))
    elif roll <= weapon_chance + armor_chance + consumable_chance and consumables:
        loot.append(random.choice(consumables))
    elif trash:
        loot.append(random.choice(trash))

    return loot


def get_loot_from_mutant(player_luck: int = 5) -> list[dict]:
    import random
    _, by_cat, _ = _get_cached_items()
    trash = by_cat.get("trash", [])
    consumables = by_cat.get("consumables", [])

    loot = []
    if trash:
        loot.extend(random.sample(trash, min(random.randint(2, 4), len(trash))))

    luck_bonus = max(0, player_luck - 10) // 5
    if consumables and random.randint(1, 100) <= 40 + luck_bonus:
        loot.append(random.choice(consumables))

    return loot


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

    equipped = [user.get(f"equipped_artifact_{i}") for i in range(1, 4)]
    if artifact_name in equipped:
        return {"success": False, "message": "Этот артефакт уже экипирован"}

    max_slots = user.get("artifact_slots", 3)
    used_slots = sum(1 for s in equipped if s)
    if used_slots >= max_slots:
        return {"success": False, "message": f"Недостаточно слотов! Занято: {used_slots}/{max_slots}"}

    for i in range(1, 4):
        if not user.get(f"equipped_artifact_{i}"):
            update_user_stats(vk_id, **{f"equipped_artifact_{i}": artifact_name})
            return {"success": True, "message": f"✅ Артефакт {artifact_name} экипирован!"}

    return {"success": False, "message": "Нет свободных слотов"}


def unequip_artifact(vk_id: int, artifact_name: str) -> dict:
    user = get_user_by_vk(vk_id)
    if not user:
        return {"success": False, "message": "Пользователь не найден"}

    for i in range(1, 4):
        if user.get(f"equipped_artifact_{i}") == artifact_name:
            update_user_stats(vk_id, **{f"equipped_artifact_{i}": ""})
            return {"success": True, "message": f"✅ Артефакт {artifact_name} снят!"}

    return {"success": False, "message": "Этот артефакт не экипирован"}


def get_equipped_artifacts(vk_id: int) -> list:
    user = get_user_by_vk(vk_id)
    if not user:
        return []
    return [user[f"equipped_artifact_{i}"] for i in range(1, 4) if user.get(f"equipped_artifact_{i}")]


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
    }

    for artifact_name in equipped:
        bonus_data = ARTIFACT_BONUSES.get(artifact_name, {})
        for key, value in bonus_data.items():
            if key in bonuses:
                if isinstance(value, bool):
                    bonuses[key] = bonuses[key] or value
                else:
                    bonuses[key] += value

    return bonuses


def roll_artifact_from_anomaly(anomaly_type: str, luck: int, detector_bonus: int) -> dict | None:
    """Попытаться получить артефакт из аномалии с броском гильзы"""
    import random
    from anomalies import ANOMALIES

    if anomaly_type not in ANOMALIES:
        return None

    anomaly = ANOMALIES[anomaly_type]
    artifacts_list = anomaly.get("artifacts", [])

    if not artifacts_list:
        return None

    base_chance = anomaly.get("success_chance_with_detector", 50)
    total_chance = base_chance + (luck * 2) + detector_bonus
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
            SELECT ui.quantity, i.name 
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
    """Снять мешочек для гильз"""
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT id FROM users WHERE vk_id = %s", (vk_id,))
        user = cursor.fetchone()
        if not user:
            return {'success': False, 'message': 'Пользователь не найден'}

        user_id = user['id']
        cursor.execute("DELETE FROM user_equipment WHERE user_id = %s AND slot = 'shells_bag'", (user_id,))
        cursor.execute("UPDATE users SET shells = 0 WHERE id = %s", (user_id,))

        return {'success': True, 'message': 'Мешочек для гильз снят. Гильзы потеряны.'}


# ---------------------------------------------------------------------------

def give_newbie_kit(vk_id: int) -> dict:
    """Выдать набор новичка"""
    from constants import NEWBIE_KIT_ITEMS
    
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
        
        # Ставим флаг о получении
        cursor.execute("""
            INSERT INTO user_flags (user_id, flag_name, value)
            VALUES (%s, 'newbie_kit_received', 1)
            ON CONFLICT (user_id, flag_name) DO NOTHING
        """, (user_id,))
    
    return {'success': True, 'message': '✅ Набор новичка получен! Проверь инвентарь.'}

# Рынок P2P
# ---------------------------------------------------------------------------

def is_market_enabled() -> bool:
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT value FROM game_settings WHERE key = 'p2p_market_enabled'")
        row = cursor.fetchone()
        return row and row['value'] == '1'


def get_market_listings(limit: int = 50) -> list[dict]:
    with db_cursor() as (cursor, _):
        cursor.execute("""
            SELECT * FROM market_listings
            WHERE status = 'active'
            ORDER BY created_at DESC
            LIMIT %s
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


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
        cursor.execute("""
            SELECT id, seller_vk_id, buyer_vk_id, item_name, quantity, price_per_item,
                   (quantity * price_per_item) AS total_price,
                   status, created_at, expires_at, completed_at
            FROM market_listings
            WHERE (%s = 'all' OR status = %s)
            ORDER BY created_at DESC
            LIMIT %s
        """, (status, status, limit))
        return [dict(r) for r in cursor.fetchall()]


def admin_cancel_market_listing(listing_id: int) -> dict:
    with db_cursor() as (cursor, _):
        cursor.execute("SELECT * FROM market_listings WHERE id = %s FOR UPDATE", (listing_id,))
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
                ON CONFLICT (user_id, item_id) DO UPDATE SET quantity = user_inventory.quantity + EXCLUDED.quantity
            """, (seller["id"], lot["item_id"], lot["quantity"]))

        cursor.execute("UPDATE market_listings SET status = 'cancelled', cancelled_at = NOW() WHERE id = %s", (listing_id,))

    return {"success": True, "message": f"Лот #{listing_id} принудительно снят администратором."}


# ---------------------------------------------------------------------------
# Инициализация БД
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    print("База данных готова к работе!")
