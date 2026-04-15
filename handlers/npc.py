"""
Модуль диалогов с NPC
"""
import random
import time
from datetime import datetime, timedelta, timezone

import config
import database
import player as player_module
from player import invalidate_player_cache, get_player as get_player_from_module

from npcs import get_npc
from handlers.keyboards import (
    create_location_keyboard, 
    create_npc_dialog_keyboard,
    create_npc_select_keyboard,
    create_kpp_shop_keyboard
)
from handlers.inventory import (
    show_soldier_weapons, 
    show_soldier_armor,
    show_scientist_shop,
    show_artifacts,
    show_weapons,
    clear_shop_cache
)


# === Константы ===
CLASS_CHANGE_COST = 500000  # Цена смены класса
MEDIC_FIELD_CHECK_COOLDOWN = 6 * 60 * 60
MEDIC_SUPPLY_COOLDOWN = 12 * 60 * 60
MEDIC_FIELD_HEAL = 40
MEDIC_FIELD_RAD_REDUCE = 10
MEDIC_DETOX_COST = 150
MEDIC_DETOX_RAD_REDUCE = 35
MEDIC_SUPPLY_ENERGY = 20
DOSIMETER_FORECAST_BASIC_COST = 12000
DOSIMETER_FORECAST_ADVANCED_COST = 35000
MSK_TZ = timezone(timedelta(hours=3))


def show_npc_dialog(player, vk, user_id: int, npc_id: str, dialog_id: str = None):
    """Показать диалог с NPC"""
    from state_manager import get_dialog_info, set_dialog_state, clear_dialog_state

    npc = get_npc(npc_id)
    if not npc:
        vk.messages.send(
            user_id=user_id,
            message="😶 NPC не найден.",
            random_id=0
        )
        return

    # Если это начало диалога - показываем приветствие
    if dialog_id is None:
        from handlers.quests import track_quest_talk_npc
        track_quest_talk_npc(user_id)
        set_dialog_state(user_id, npc_id, "menu")
        vk.messages.send(
            user_id=user_id,
            message=npc.greeting,
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return

    # Получаем ответ на конкретный вопрос
    dialog = npc.get_dialog(dialog_id)
    if not dialog:
        vk.messages.send(
            user_id=user_id,
            message="NPC не понимает тебя.",
            random_id=0
        )
        return

    answer = dialog.get("answer", "NPC молчит.")
    next_stage = dialog.get("next")

    # Обработка специальных диалогов
    result = _handle_special_dialog(
        player, vk, user_id, npc_id, dialog_id, answer, next_stage
    )
    if result:
        return

    # Обработка перехода в магазин
    if next_stage in ["shop_menu", "shop_weapons", "shop_armor", "shop_meds", "shop_artifacts", "sell_items", "sell_gear", "buy_artifacts"]:
        _handle_shop_redirect(player, vk, user_id, npc_id, next_stage)
        return

    # Обработка завершения диалога
    if next_stage == "end":
        clear_dialog_state(user_id)
        vk.messages.send(
            user_id=user_id,
            message=answer,
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
        return

    # Обычный ответ
    vk.messages.send(
        user_id=user_id,
        message=answer,
        keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
        random_id=0
    )


def _handle_special_dialog(player, vk, user_id: int, npc_id: str, dialog_id: str, answer: str, next_stage: str):
    """Обработка специальных диалогов (набор, класс, смена класса)"""
    from classes import get_class_by_weapon, format_class_info, format_passive_status
    from state_manager import clear_dialog_state

    # Обработка набора новичка
    if dialog_id == "набор":
        result = database.give_newbie_kit(user_id)
        clear_dialog_state(user_id)

        if result is None or not result.get("success", False):
            vk.messages.send(
                user_id=user_id,
                message="👴 Местный житель:\n\n«Эй, я уже давал тебе набор! Не жадничай, сталкер. Иди в Зону — там добудешь всё сам.»",
                keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
                random_id=0
            )
        else:
            invalidate_player_cache(user_id)
            player = get_player_from_module(user_id)
            player.inventory.reload()

            # Безопасное получение списка предметов
            items = result.get("items", [])
            if items:
                items_list = "\n".join([f"• {name} x{qty}" for name, qty in items])
            else:
                items_list = "• Предметы выданы (список недоступен)"

            vk.messages.send(
                user_id=user_id,
                message=f"{answer}\n\n📦Получено:\n{items_list}\n\n💰 Деньги: 10000 руб.",
                keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
                random_id=0
            )
        return True

    # Обработка получения класса персонажа
    if dialog_id == "get_class":
        return _handle_get_class(player, vk, user_id, npc_id)

    # Обработка смены класса
    if dialog_id == "change_class":
        return _handle_change_class(player, vk, user_id, npc_id)

    # Обработка просмотра своего класса
    if dialog_id == "my_class":
        return _handle_show_class(player, vk, user_id, npc_id)

    # Сервисы медика
    if dialog_id == "осмотр":
        return _handle_medic_field_check(player, vk, user_id, npc_id)

    if dialog_id == "детокс":
        return _handle_medic_detox(player, vk, user_id, npc_id)

    if dialog_id == "пайки":
        return _handle_medic_supply(player, vk, user_id, npc_id)

    # Прогнозы выброса от дозиметриста
    if dialog_id == "прогноз":
        return _handle_dosimeter_forecast(player, vk, user_id, npc_id, advanced=False)

    if dialog_id == "прогнозпрем":
        return _handle_dosimeter_forecast(player, vk, user_id, npc_id, advanced=True)

    return False


def _format_seconds_left(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0:
        return f"{hours}ч {minutes}м"
    return f"{minutes}м"


def _fmt_clock_msk(dt_utc_naive: datetime | None) -> str:
    """Преобразовать UTC-naive в часы/минуты МСК."""
    if not dt_utc_naive:
        return "--:--"
    aware = dt_utc_naive.replace(tzinfo=timezone.utc).astimezone(MSK_TZ)
    return aware.strftime("%H:%M")


def _fmt_delta_short(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours = seconds // 3600
    minutes = seconds // 60
    sec = seconds % 60
    if hours > 0:
        rem_minutes = (seconds % 3600) // 60
        return f"{hours}:{rem_minutes:02d}:{sec:02d}"
    return f"{minutes}:{sec:02d}"


def _build_emission_forecast(emission: dict, advanced: bool) -> tuple[str, str]:
    """Сформировать текст прогноза и уровень качества."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    status = str(emission.get("status") or "pending")
    warning_time = emission.get("warning_time")
    impact_time = emission.get("impact_time")
    end_time = emission.get("end_time")

    to_warning = int((warning_time - now).total_seconds()) if warning_time else 0
    to_impact = int((impact_time - now).total_seconds()) if impact_time else 0
    to_end = int((end_time - now).total_seconds()) if end_time else 0
    to_lock = to_impact - 5 * 60

    roll = random.random()
    if advanced:
        if roll < 0.68:
            quality = "точный"
        elif roll < 0.95:
            quality = "коридор"
        else:
            quality = "шум"
    else:
        if roll < 0.33:
            quality = "точный"
        elif roll < 0.82:
            quality = "коридор"
        elif roll < 0.95:
            quality = "шум"
        else:
            quality = "ложный"

    cancel_text = f"Вероятность отмены перед impact: ~{int(config.EMISSION_CANCEL_CHANCE * 100)}%"

    if status == "impact":
        if quality == "точный":
            msg = (
                "☣️ Фаза: IMPACT (идёт прямо сейчас)\n"
                f"До конца волны: {_fmt_delta_short(to_end)}\n"
                f"Ориентир окончания: {_fmt_clock_msk(end_time)} МСК\n"
                "Рекомендация: не выходить из safe без антирада."
            )
        elif quality == "коридор":
            lo = max(0, to_end - 4 * 60)
            hi = max(0, to_end + 6 * 60)
            msg = (
                "☣️ Фаза: IMPACT\n"
                f"Окончание ожидается через ~{_fmt_delta_short(lo)} .. {_fmt_delta_short(hi)}\n"
                "Рекомендация: держать лечение на тиках и переждать волну."
            )
        elif quality == "ложный":
            msg = (
                "📡 Канал забит помехами.\n"
                "Сигнал противоречивый: возможен быстрый спад в ближайшие минуты.\n"
                "Доверие к прогнозу низкое."
            )
        else:
            msg = (
                "📡 Сильные помехи в эфире.\n"
                "Сигнатура нестабильна: амплитуда волны скачет, точный тайминг недоступен."
            )
        return msg, quality

    if status == "warning":
        if quality == "точный":
            msg = (
                "⚠️ Фаза: WARNING\n"
                f"До impact: {_fmt_delta_short(to_impact)}\n"
                f"Блок safe для рискнувших: через {_fmt_delta_short(to_lock)}\n"
                f"Impact ориентир: {_fmt_clock_msk(impact_time)} МСК\n"
                f"{cancel_text}"
            )
        elif quality == "коридор":
            lo = max(0, to_impact - 3 * 60)
            hi = max(0, to_impact + 5 * 60)
            msg = (
                "⚠️ Фаза: WARNING\n"
                f"Impact ожидается через ~{_fmt_delta_short(lo)} .. {_fmt_delta_short(hi)}\n"
                "Совет: уходить в safe сейчас, без затяжки."
            )
        elif quality == "ложный":
            msg = (
                "📡 Сигнал размазан.\n"
                "Есть версия, что удар может сорваться, но подтверждения нет.\n"
                "Риск всё ещё высокий."
            )
        else:
            msg = (
                "📡 Эфир нестабилен.\n"
                "Окно удара плавает в пределах ближайших 10-25 минут."
            )
        return msg, quality

    # pending
    if quality == "точный":
        msg = (
            "🛰️ Фаза: PENDING\n"
            f"Предупреждение: через {_fmt_delta_short(to_warning)} ({_fmt_clock_msk(warning_time)} МСК)\n"
            f"Impact: через {_fmt_delta_short(to_impact)} ({_fmt_clock_msk(impact_time)} МСК)\n"
            f"{cancel_text}"
        )
    elif quality == "коридор":
        spread = 8 if advanced else 16
        lo_warn = max(0, to_warning - spread * 60)
        hi_warn = max(0, to_warning + spread * 60)
        lo_imp = max(0, to_impact - spread * 60)
        hi_imp = max(0, to_impact + spread * 60)
        msg = (
            "🛰️ Фаза: PENDING\n"
            f"WARNING окно: {_fmt_delta_short(lo_warn)} .. {_fmt_delta_short(hi_warn)}\n"
            f"IMPACT окно: {_fmt_delta_short(lo_imp)} .. {_fmt_delta_short(hi_imp)}\n"
            "Рекомендация: подготовить антирады заранее."
        )
    elif quality == "ложный":
        msg = (
            "📡 Ложный след в данных.\n"
            "Похоже на затяжную паузу по активности, но точность прогноза низкая."
        )
    else:
        msg = (
            "📡 Сырые данные с датчиков.\n"
            "В ближайшие часы ожидается рост аномальной активности, точное окно не фиксируется."
        )

    return msg, quality


def _handle_dosimeter_forecast(player, vk, user_id: int, npc_id: str, advanced: bool):
    """Платный прогноз выброса с вариативной точностью."""
    tier_name = "Расширенный" if advanced else "Базовый"
    cost = DOSIMETER_FORECAST_ADVANCED_COST if advanced else DOSIMETER_FORECAST_BASIC_COST

    if int(player.money) < cost:
        vk.messages.send(
            user_id=user_id,
            message=(
                "☢️Дозиметрист:\n\n"
                f"{tier_name} прогноз стоит {cost:,} руб.\n"
                f"У тебя: {int(player.money):,} руб."
            ),
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    emission = database.get_active_emission()
    if not emission:
        vk.messages.send(
            user_id=user_id,
            message=(
                "☢️Дозиметрист:\n\n"
                "Сейчас нет активного цикла выброса в канале мониторинга.\n"
                "Подойди чуть позже — сниму прогноз, когда появится окно."
            ),
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    old_money = int(player.money)
    new_money = max(0, old_money - cost)
    database.update_user_stats(user_id, money=new_money)
    player.money = new_money

    forecast_text, quality = _build_emission_forecast(emission, advanced=advanced)
    quality_label = {
        "точный": "высокая",
        "коридор": "средняя",
        "шум": "низкая",
        "ложный": "критически низкая",
    }.get(quality, "неизвестная")

    vk.messages.send(
        user_id=user_id,
        message=(
            "☢️Дозиметрист:\n\n"
            f"Принято. Пакет: {tier_name}.\n"
            f"Списано: {cost:,} руб.\n"
            f"Баланс: {old_money:,} → {new_money:,}\n\n"
            f"{forecast_text}\n\n"
            f"Надёжность сигнала: {quality_label}."
        ),
        keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
        random_id=0
    )
    return True


def _handle_medic_field_check(player, vk, user_id: int, npc_id: str):
    """Бесплатный полевой осмотр с кулдауном."""
    from player import format_radiation_rate, get_radiation_stage
    now = int(time.time())
    last_use = int(database.get_user_flag(user_id, "medic_field_check_last", 0) or 0)
    elapsed = now - last_use if last_use else MEDIC_FIELD_CHECK_COOLDOWN

    if elapsed < MEDIC_FIELD_CHECK_COOLDOWN:
        wait_left = MEDIC_FIELD_CHECK_COOLDOWN - elapsed
        vk.messages.send(
            user_id=user_id,
            message=(
                "🩺Медик:\n\n"
                f"Полевой осмотр на перерыве. Подходи через {_format_seconds_left(wait_left)}."
            ),
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    old_health = int(player.health)
    old_radiation = int(player.radiation)
    new_health = min(int(player.max_health), old_health + MEDIC_FIELD_HEAL)
    new_radiation = max(0, old_radiation - MEDIC_FIELD_RAD_REDUCE)

    database.update_user_stats(user_id, health=new_health, radiation=new_radiation)
    database.set_user_flag(user_id, "medic_field_check_last", now)
    player.health = new_health
    player.radiation = new_radiation

    vk.messages.send(
        user_id=user_id,
        message=(
            "🩺Медик:\n\n"
            "Готово. Обработал раны и снял часть заражения.\n\n"
            f"❤️ HP: {old_health} → {new_health}\n"
            f"☢️ Радиация: {old_radiation} → {new_radiation} ед.\n"
            f"   ({format_radiation_rate(old_radiation)} → {format_radiation_rate(new_radiation)})\n"
            f"🧪 Стадия: {get_radiation_stage(new_radiation)['name']}\n\n"
            f"Следующий бесплатный осмотр: через {_format_seconds_left(MEDIC_FIELD_CHECK_COOLDOWN)}."
        ),
        keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
        random_id=0
    )
    return True


def _handle_medic_detox(player, vk, user_id: int, npc_id: str):
    """Платный детокс радиации."""
    from player import format_radiation_rate, get_radiation_stage
    if int(player.money) < MEDIC_DETOX_COST:
        vk.messages.send(
            user_id=user_id,
            message=(
                "🩺Медик:\n\n"
                f"Полный детокс стоит {MEDIC_DETOX_COST} руб.\n"
                f"У тебя: {player.money} руб."
            ),
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    if int(player.radiation) <= 0:
        vk.messages.send(
            user_id=user_id,
            message="🩺Медик:\n\nСейчас детокс не нужен — радиация в норме.",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    old_money = int(player.money)
    old_radiation = int(player.radiation)
    new_money = max(0, old_money - MEDIC_DETOX_COST)
    new_radiation = max(0, old_radiation - MEDIC_DETOX_RAD_REDUCE)

    database.update_user_stats(user_id, money=new_money, radiation=new_radiation)
    player.money = new_money
    player.radiation = new_radiation

    vk.messages.send(
        user_id=user_id,
        message=(
            "🩺Медик:\n\n"
            "Детокс завершён.\n\n"
            f"☢️ Радиация: {old_radiation} → {new_radiation} ед.\n"
            f"   ({format_radiation_rate(old_radiation)} → {format_radiation_rate(new_radiation)})\n"
            f"🧪 Стадия: {get_radiation_stage(new_radiation)['name']}\n"
            f"💰 Деньги: {old_money} → {new_money}"
        ),
        keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
        random_id=0
    )
    return True


def _handle_medic_supply(player, vk, user_id: int, npc_id: str):
    """Паёк перед выходом в рейд (кулдаун)."""
    now = int(time.time())
    last_use = int(database.get_user_flag(user_id, "medic_supply_last", 0) or 0)
    elapsed = now - last_use if last_use else MEDIC_SUPPLY_COOLDOWN

    if elapsed < MEDIC_SUPPLY_COOLDOWN:
        wait_left = MEDIC_SUPPLY_COOLDOWN - elapsed
        vk.messages.send(
            user_id=user_id,
            message=(
                "🩺Медик:\n\n"
                f"Паёк выдается раз в 12 часов. Осталось: {_format_seconds_left(wait_left)}."
            ),
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    old_energy = int(player.energy)
    new_energy = min(100, old_energy + MEDIC_SUPPLY_ENERGY)
    database.update_user_stats(user_id, energy=new_energy)
    database.add_item_to_inventory(user_id, "Бинт", 1)
    database.add_item_to_inventory(user_id, "Антирад", 1)
    database.add_item_to_inventory(user_id, "Вода", 1)
    database.set_user_flag(user_id, "medic_supply_last", now)

    player.energy = new_energy
    try:
        player.inventory.reload()
    except Exception:
        pass

    vk.messages.send(
        user_id=user_id,
        message=(
            "🩺Медик:\n\n"
            "Держи паёк перед выходом.\n\n"
            f"⚡ Энергия: {old_energy} → {new_energy}\n"
            "📦 Выдано: Бинт x1, Антирад x1, Вода x1"
        ),
        keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
        random_id=0
    )
    return True


def _handle_get_class(player, vk, user_id: int, npc_id: str):
    """Обработка получения класса"""
    from classes import get_class_by_weapon, format_class_info
    from state_manager import clear_dialog_state

    if player.level < 10:
        vk.messages.send(
            user_id=user_id,
            message="🎓Наставник:\n\n«Ты ещё слишком слаб, сталкер. Приходи, когда достигнешь 10 уровня. К тому времени я посмотрю, на что ты способен.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    if not player.equipped_weapon:
        vk.messages.send(
            user_id=user_id,
            message="🎓Наставник:\n\n«У тебя нет оружия! Как ты собираешься выживать в Зоне? Экипируй оружие и приходи снова.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    class_id = get_class_by_weapon(player.equipped_weapon)
    if not class_id:
        vk.messages.send(
            user_id=user_id,
            message="🎓Наставник:\n\n«Хм, это оружие мне не знакомо. Приходи с другим — я посмотрю, какой стиль боя тебе подходит.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    # Если класс уже есть - проверяем деньги на смену
    if player.player_class and player.player_class != class_id:
        if player.money < CLASS_CHANGE_COST:
            vk.messages.send(
                user_id=user_id,
                message=f"🎓Наставник:\n\n«Ты уже имеешь класс, но хочешь сменить на {class_id.upper()}. Это стоит {CLASS_CHANGE_COST:,} руб.\n\nУ тебя недостаточно денег — нужно ещё {CLASS_CHANGE_COST - player.money:,} руб.»",
                keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
                random_id=0
            )
            return True

        new_money = player.money - CLASS_CHANGE_COST
        database.update_user_stats(user_id, money=new_money, player_class=class_id)
        invalidate_player_cache(user_id)
        player = get_player_from_module(user_id)

        class_info = format_class_info(class_id)
        vk.messages.send(
            user_id=user_id,
            message=f"💰Наставник:\n\n«Переобучение прошло успешно! Списано {CLASS_CHANGE_COST:,} руб.\n\nТеперь ты — {class_id.split()[0]} {class_id.upper()}.\n\n{class_info}\n\n'Запомни: сила класса — в оружии. Меняй оружие — меняется и класс!'»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    # Если класса ещё нет - просто выдаём
    database.update_user_stats(user_id, player_class=class_id)
    from handlers.quests import track_quest_change_class
    track_quest_change_class(user_id)
    invalidate_player_cache(user_id)
    player = get_player_from_module(user_id)

    class_info = format_class_info(class_id)
    vk.messages.send(
        user_id=user_id,
        message=f"🎓Наставник:\n\n«Отлично! Теперь ты — {class_id.split()[0]} {class_id.upper()}. Вот твои навыки:\n\n{class_info}\n\n'Запомни: сила класса — в оружии. Меняй оружие — меняется и класс!'»",
        keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
        random_id=0
    )
    return True


def _handle_change_class(player, vk, user_id: int, npc_id: str):
    """Обработка смены класса"""
    from classes import get_class_by_weapon, format_class_info
    from state_manager import clear_dialog_state

    if player.level < 10:
        vk.messages.send(
            user_id=user_id,
            message="🎓Наставник:\n\n«Ты ещё слишком слаб для смены класса. Приходи на 10 уровне.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    if not player.equipped_weapon:
        vk.messages.send(
            user_id=user_id,
            message="🎓Наставник:\n\n«Экипируй оружие, на которое хочешь перейти, и приходи снова.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    new_class_id = get_class_by_weapon(player.equipped_weapon)
    if not new_class_id:
        vk.messages.send(
            user_id=user_id,
            message="🎓Наставник:\n\n«Это оружие мне не знакомо. Приходи с другим.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    if new_class_id == player.player_class:
        vk.messages.send(
            user_id=user_id,
            message=f"🎓Наставник:\n\n«У тебя уже есть класс {player.player_class.upper()}. Экипируй другое оружие для смены.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    if player.money < CLASS_CHANGE_COST:
        vk.messages.send(
            user_id=user_id,
            message=f"🎓Наставник:\n\n«Смена класса на {new_class_id.upper()} стоит {CLASS_CHANGE_COST:,} руб.\n\nУ тебя есть {player.money:,} руб. Не хватает {CLASS_CHANGE_COST - player.money:,} руб.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    new_money = player.money - CLASS_CHANGE_COST
    database.update_user_stats(user_id, money=new_money, player_class=new_class_id)
    from handlers.quests import track_quest_change_class
    track_quest_change_class(user_id)
    invalidate_player_cache(user_id)
    player = get_player_from_module(user_id)

    class_info = format_class_info(new_class_id)
    vk.messages.send(
        user_id=user_id,
        message=f"💰Наставник:\n\n«Класс успешно сменён! Списано {CLASS_CHANGE_COST:,} руб.\n\nТеперь ты — {new_class_id.split()[0]} {new_class_id.upper()}.\n\n{class_info}\n\n'Запомни: сила класса — в оружии!'»",
        keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
        random_id=0
    )
    return True


def _handle_show_class(player, vk, user_id: int, npc_id: str):
    """Обработка просмотра класса"""
    from classes import get_class_by_weapon, format_class_info, format_passive_status

    if not player.player_class:
        vk.messages.send(
            user_id=user_id,
            message="🎓Наставник:\n\n«У тебя ещё нет класса! Приходи, когда достигнешь 10 уровня и экипируй оружие. Я обучу тебя боевому стилю.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    class_info = format_class_info(player.player_class, player.level)
    current_weapon = player.equipped_weapon or "нет"
    current_class = get_class_by_weapon(current_weapon) if current_weapon != "нет" else None

    msg = f"🎓Наставник:\n\n"
    msg += f"📌Твой текущий класс: {player.player_class.upper()}\n"
    msg += f"🔫Экипированное оружие: {current_weapon}\n"
    msg += f"⭐Твой уровень: {player.level}\n\n"

    if current_class and current_class != player.player_class:
        msg += f"⚠️Внимание! Твой экипированный класс: {current_class.upper()}\n"
        msg += "Класс меняется в зависимости от оружия!\n\n"

    passive_status = format_passive_status(player.player_class, player.level)
    msg += f"{passive_status}\n"
    msg += f"<b>Информация о классе:\n{class_info}"

    vk.messages.send(
        user_id=user_id,
        message=msg,
        keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
        random_id=0
    )
    return True


def _handle_shop_redirect(player, vk, user_id: int, npc_id: str, next_stage: str):
    """Перенаправление в магазин"""
    from state_manager import set_dialog_state

    set_dialog_state(user_id, npc_id, next_stage)

    if next_stage == "shop_menu":
        vk.messages.send(
            user_id=user_id,
            message="🎖️Военный:\n\n«Выбирай, сталкер:\n\n🔫 Оружие — от пистолетов до автоматов\n🛡️ Броня — жилеты и шлемы\n💰 Продать — скупка трофеев\n\nЦены — как есть, торга не будет.»",
            keyboard=create_kpp_shop_keyboard().get_keyboard(),
            random_id=0
        )
    elif next_stage == "shop_weapons":
        show_soldier_weapons(player, vk, user_id)
    elif next_stage == "shop_armor":
        show_soldier_armor(player, vk, user_id)
    elif next_stage == "shop_meds":
        show_scientist_shop(player, vk, user_id, category='meds')
    elif next_stage == "shop_food":
        show_scientist_shop(player, vk, user_id, category='food')
    elif next_stage == "shop_artifacts":
        show_artifacts(player, vk, user_id)
    elif next_stage in ["sell_items", "sell_gear"]:
        show_weapons(player, vk, user_id)
    elif next_stage == "buy_artifacts":
        # Магазин артефактов у Барыги
        from handlers.inventory import show_artifact_shop

        set_dialog_state(user_id, npc_id, "buy_artifacts")
        show_artifact_shop(player, vk, user_id)
    elif next_stage == "sell_artifacts":
        # Продажа артефактов Барыге
        from handlers.inventory import show_sell_artifacts
        set_dialog_state(user_id, npc_id, "sell_artifacts")
        show_sell_artifacts(player, vk, user_id)


def handle_npc_choice(player, vk, user_id: int, npc_id: str):
    """Обработка выбора NPC для разговора"""
    show_npc_dialog(player, vk, user_id, npc_id, None)


def handle_npc_back(player, vk, user_id: int):
    """Обработка возврата из диалога с NPC"""
    from state_manager import clear_dialog_state, get_dialog_info
    from npcs import get_npc_by_location

    clear_dialog_state(user_id)
    clear_shop_cache(user_id)

    location_id = player.current_location_id
    npcs = get_npc_by_location(location_id)

    if npcs:
        npc_names = ", ".join([npc.name for npc in npcs])
        vk.messages.send(
            user_id=user_id,
            message=f"👥Выбери, с кем поговорить:\n\n{npc_names}",
            keyboard=create_npc_select_keyboard(location_id).get_keyboard(),
            random_id=0
        )
    else:
        vk.messages.send(user_id=user_id, message="😶 Здесь никого нет для разговора.", random_id=0)
