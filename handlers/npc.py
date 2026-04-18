"""
Модуль диалогов с NPC
"""
from __future__ import annotations

import random
import time
from datetime import datetime, timedelta, timezone

from infra import config
from infra import database
from models import player as player_module
from models.player import invalidate_player_cache, get_player as get_player_from_module

from models.npcs import get_npc
from handlers.keyboards import (
    create_location_keyboard, 
    create_npc_dialog_keyboard,
    create_npc_select_keyboard,
    create_class_selection_keyboard,
    create_class_confirm_keyboard,
    create_kpp_shop_keyboard
)
from handlers.inventory import (
    show_soldier_weapons, 
    show_soldier_armor,
    show_scientist_shop,
    show_artifacts,
    show_weapons,
    show_trader_shop_all,
    show_trader_sell_all,
    handle_buy_artifact_slot,
    handle_buy_shells_bag,
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
    from infra.state_manager import get_dialog_info, set_dialog_state, clear_dialog_state

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
        track_quest_talk_npc(user_id, vk=vk)
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
    if next_stage in ["shop_menu", "shop_weapons", "shop_armor", "shop_meds", "shop_artifacts", "sell_items", "sell_gear", "buy_artifacts", "sell_artifacts"]:
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
    from models.classes import get_all_classes, normalize_class_id
    from infra.state_manager import clear_dialog_state
    special_id = next(
        (
            value for value in (dialog_id, answer, next_stage)
            if value in {"get_class", "change_class", "my_class", "class_selection"}
            or str(value).startswith("select_class:")
        ),
        dialog_id,
    )

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
                message=f"{answer}\n\n📦Получено:\n{items_list}",
                keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
                random_id=0
            )
        return True

    # Обработка получения класса персонажа
    if special_id == "get_class":
        return _handle_get_class(player, vk, user_id, npc_id)

    # Обработка смены класса
    if special_id == "change_class":
        return _handle_change_class(player, vk, user_id, npc_id)

    # Обработка просмотра своего класса
    if special_id == "my_class":
        return _handle_show_class(player, vk, user_id, npc_id)

    if special_id == "class_selection":
        return _handle_class_selection_menu(player, vk, user_id, npc_id)

    if isinstance(special_id, str) and special_id.startswith("select_class:"):
        class_id = normalize_class_id(special_id.split(":", 1)[1])
        if class_id in get_all_classes():
            return _handle_class_preview(player, vk, user_id, npc_id, class_id)

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

    if dialog_id == "мойранг":
        return _handle_rank_status(player, vk, user_id, npc_id)

    if dialog_id == "условия":
        return _handle_rank_requirements(player, vk, user_id, npc_id)

    if dialog_id == "повысить":
        return _handle_rank_promotion(player, vk, user_id, npc_id)

    if dialog_id == "слоты":
        return _handle_trader_slot_info(player, vk, user_id, npc_id)

    if dialog_id == "купитьслот":
        handle_buy_artifact_slot(player, vk, user_id)
        return True

    if dialog_id == "мешочки":
        return _handle_soldier_shells_bag_info(player, vk, user_id, npc_id)

    if dialog_id == "купитьмешочек":
        handle_buy_shells_bag(player, vk, user_id)
        return True

    if dialog_id == "рынокигроков":
        if player.current_location_id != "черный рынок":
            vk.messages.send(
                user_id=user_id,
                message="📈 P2P рынок доступен только на локации «Черный рынок».",
                keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
                random_id=0
            )
            return True

        from handlers.market import show_market_menu
        clear_dialog_state(user_id)
        show_market_menu(player, vk, user_id)
        return True

    return False


def _handle_trader_slot_info(player, vk, user_id: int, npc_id: str):
    """Информация о прокачке слотов артефактов у Барыги."""
    current_slots = int(getattr(player, "artifact_slots", 3) or 3)
    max_slots = int(config.MAX_ARTIFACT_SLOTS)

    lines = [
        "💰Барыга:\n",
        "Контейнер под артефакты расширяю поэтапно.",
        f"Сейчас у тебя: {current_slots}/{max_slots} слотов.",
    ]

    if current_slots >= max_slots:
        lines.append("\nТы уже на максимуме. Дальше расширять некуда.")
    else:
        next_slot = current_slots + 1
        req = config.ARTIFACT_SLOT_REQUIREMENTS.get(next_slot, {})
        need_level = int(req.get("level", config.MIN_LEVEL_FOR_ARTIFACT_SLOT))
        need_money = int(req.get("cost", 0))

        lines.extend([
            "",
            f"Следующий апгрейд: слот {next_slot}/{max_slots}",
            f"• Уровень: {player.level}/{need_level}",
            f"• Деньги: {player.money}/{need_money} руб.",
            "",
            "Покупка: напиши «купить слот».",
            "Шкала апгрейдов растянута до 120 уровня.",
        ])

    vk.messages.send(
        user_id=user_id,
        message="\n".join(lines),
        keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
        random_id=0
    )
    return True


def _handle_soldier_shells_bag_info(player, vk, user_id: int, npc_id: str):
    """Информация о прогрессии мешочков для гильз у Военного на КПП."""
    bag_order = list(getattr(config, "SHELLS_BAG_ORDER", ()) or ())
    requirements = dict(getattr(config, "SHELLS_BAG_REQUIREMENTS", {}) or {})

    if not bag_order:
        vk.messages.send(
            user_id=user_id,
            message="🎖️Военный:\n\nДля мешочков пока нет настроек. Подойди позже.",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    player.inventory.reload()
    user_data = database.get_user_by_vk(user_id) or {}
    equipped_bag = user_data.get("equipped_shells_bag")
    shells_info = database.get_shells_info(user_id)
    capacity = int(shells_info.get("capacity", 0) or 0)

    owned_names = {item.get("name") for item in player.inventory.shells_bags}
    if equipped_bag:
        owned_names.add(equipped_bag)

    highest_owned_index = -1
    for idx, bag_name in enumerate(bag_order):
        if bag_name in owned_names:
            highest_owned_index = idx

    lines = [
        "🎖️Военный:\n",
        "Мешочки для гильз выдаю по допуску, не всем подряд.",
        f"Текущий ранг мешочка: {equipped_bag or 'не экипирован'}",
        f"Вместимость сейчас: {capacity} гильз.",
    ]

    if highest_owned_index >= len(bag_order) - 1:
        lines.append("\nТы уже получил максимальный мешочек.")
    else:
        next_index = highest_owned_index + 1
        next_bag = bag_order[next_index]
        req = requirements.get(next_bag, {})
        need_level = int(req.get("level", getattr(config, "MIN_LEVEL_FOR_SHELLS_BAG", 1)))
        need_money = int(req.get("cost", 0))

        bag_item = database.get_item_by_name(next_bag) or {}
        next_capacity = int(bag_item.get("backpack_bonus", 0) or 0)

        lines.extend([
            "",
            f"Следующий мешочек: {next_bag}",
            f"• Вместимость: до {next_capacity} гильз",
            f"• Уровень: {player.level}/{need_level}",
            f"• Деньги: {player.money}/{need_money} руб.",
            "",
            "Покупка: напиши «купить мешочек».",
            "Прогрессия растянута до 120 уровня.",
        ])

    vk.messages.send(
        user_id=user_id,
        message="\n".join(lines),
        keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
        random_id=0
    )
    return True


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
    from models.player import format_radiation_rate, get_radiation_stage
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
    from models.player import format_radiation_rate, get_radiation_stage
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


def _handle_rank_status(player, vk, user_id: int, npc_id: str):
    """Показать текущий ранг игрока и прогресс до следующего."""
    tier = int(player._get_rank_tier())
    total = len(player.RANK_TIERS)
    rank_name = player.get_rank_name()
    progress_block = player.get_rank_progress_block()

    vk.messages.send(
        user_id=user_id,
        message=(
            "🧭Куратор рангов:\n\n"
            f"Твой текущий ранг: {rank_name} ({tier}/{total}).\n\n"
            f"{progress_block}"
        ),
        keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
        random_id=0
    )
    return True


def _handle_rank_requirements(player, vk, user_id: int, npc_id: str):
    """Показать требования для следующего ранга."""
    tier = int(player._get_rank_tier())
    total = len(player.RANK_TIERS)
    current_name = player.get_rank_name()

    if tier >= total:
        vk.messages.send(
            user_id=user_id,
            message=(
                "🧭Куратор рангов:\n\n"
                f"Твой ранг: {current_name} ({tier}/{total}).\n"
                "Это максимальная ступень. Дальше только удерживать планку."
            ),
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    next_tier = tier + 1
    next_rank = player.RANK_TIERS[next_tier - 1]
    req_lines = player._rank_requirements_lines(next_tier)

    vk.messages.send(
        user_id=user_id,
        message=(
            "🧭Куратор рангов:\n\n"
            f"Сейчас: {current_name} ({tier}/{total}).\n"
            f"Следующий ранг: {next_rank['name']}.\n\n"
            "Требования к повышению:\n"
            + "\n".join(req_lines)
        ),
        keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
        random_id=0
    )
    return True


def _handle_rank_promotion(player, vk, user_id: int, npc_id: str):
    """Попытка повышения ранга у НПС."""
    promoted = player._try_rank_promotions()

    if promoted:
        tier = int(player._get_rank_tier())
        total = len(player.RANK_TIERS)
        lines = "\n".join(f"• {name}" for name in promoted)
        vk.messages.send(
            user_id=user_id,
            message=(
                "🧭Куратор рангов:\n\n"
                "Досье подтверждено. Повышение оформлено:\n"
                f"{lines}\n\n"
                f"Текущий статус: {player.get_rank_name()} ({tier}/{total}).\n\n"
                f"{player.get_rank_progress_block()}"
            ),
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    vk.messages.send(
        user_id=user_id,
        message=(
            "🧭Куратор рангов:\n\n"
            "Пока не могу подтвердить повышение. Закрой условия и приходи снова.\n\n"
            f"{player.get_rank_progress_block()}"
        ),
        keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
        random_id=0
    )
    return True


def _handle_get_class(player, vk, user_id: int, npc_id: str):
    """Обработка получения класса"""
    return _handle_class_selection_menu(player, vk, user_id, npc_id)


def _handle_class_selection_menu(player, vk, user_id: int, npc_id: str):
    """Показать выбор специализаций у Наставника."""
    from models.classes import format_all_classes

    if player.level < 10:
        vk.messages.send(
            user_id=user_id,
            message=(
                "🎓Наставник:\n\n"
                "«Ты ещё слишком сырой для специализации. Доживи до 10 уровня, тогда разговор будет предметным.»"
            ),
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    current = f"\n\nТекущий класс: {player.player_class.upper()}." if player.player_class else ""
    change_note = (
        f"\nСмена уже выбранного класса стоит {CLASS_CHANGE_COST:,} руб."
        if player.player_class else
        "\nПервый выбор бесплатный."
    )
    vk.messages.send(
        user_id=user_id,
        message=(
            "🎓Наставник:\n\n"
            "«Класс теперь не привязан к стволу. Оружие меняй под задачу, а специализация остаётся твоей школой выживания.»\n\n"
            f"{format_all_classes()}"
            f"{current}"
            f"{change_note}\n\n"
            "Нажми на специализацию ниже — покажу лор, навыки и пассивки перед подтверждением."
        ),
        keyboard=create_class_selection_keyboard().get_keyboard(),
        random_id=0
    )
    return True


def _handle_change_class(player, vk, user_id: int, npc_id: str):
    """Обработка смены класса"""
    return _handle_class_selection_menu(player, vk, user_id, npc_id)


def _format_class_preview(player, class_id: str) -> str:
    """Собрать подробный предпросмотр класса перед подтверждением."""
    from models.classes import get_class

    selected = get_class(class_id)
    if not selected:
        return "Класс не найден."

    lines = [
        f"{selected.name}",
        selected.description,
        "",
        "Что даёт класс:",
        "• Оружие: любое экипированное",
    ]

    if selected.active_skills:
        lines.append("")
        lines.append("Активные навыки:")
        for skill in selected.active_skills:
            lines.append(
                f"• {skill['name']} — {skill['description']} "
                f"({skill['energy_cost']} энергии, перезарядка {skill['cooldown']} ход.)"
            )

    if selected.passive_skills:
        lines.append("")
        lines.append("Пассивные навыки:")
        for passive in selected.passive_skills:
            required = int(passive.get("required_level", 10) or 10)
            status = "доступно" if int(player.level) >= required else "откроется"
            lines.append(
                f"• {passive['name']} — {passive['description']} "
                f"(ур. {required}, {status})"
            )

    is_change = bool(player.player_class and player.player_class != class_id)
    if player.player_class == class_id:
        lines.extend(["", "Это уже твоя текущая специализация."])
    elif is_change:
        lines.extend([
            "",
            f"Смена с текущего класса стоит {CLASS_CHANGE_COST:,} руб.",
            f"Твои деньги: {int(player.money):,} руб.",
        ])
    else:
        lines.extend(["", "Первый выбор класса бесплатный."])

    return "\n".join(lines)


def _handle_class_preview(player, vk, user_id: int, npc_id: str, class_id: str):
    """Показать лор и бонусы класса перед подтверждением."""
    from models.classes import get_class
    from infra.state_manager import set_dialog_state

    if player.level < 10:
        vk.messages.send(
            user_id=user_id,
            message="🎓Наставник:\n\n«Сначала 10 уровень. До этого специализация только навредит: будешь копировать форму без понимания.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    selected = get_class(class_id)
    if not selected:
        vk.messages.send(
            user_id=user_id,
            message="🎓Наставник:\n\n«Такой школы у меня нет. Выбери нормальную специализацию из списка.»",
            keyboard=create_class_selection_keyboard().get_keyboard(),
            random_id=0
        )
        return True

    set_dialog_state(user_id, npc_id, f"class_confirm:{class_id}")
    vk.messages.send(
        user_id=user_id,
        message=(
            "🎓Наставник:\n\n"
            "«Сначала слушай, потом решай. Класс меняет привычки, а не только строчку в досье.»\n\n"
            f"{_format_class_preview(player, class_id)}"
        ),
        keyboard=create_class_confirm_keyboard().get_keyboard(),
        random_id=0
    )
    return True


def _handle_select_class(player, vk, user_id: int, npc_id: str, class_id: str):
    """Выбрать или сменить специализацию."""
    from models.classes import format_class_info, get_class
    from infra.state_manager import set_dialog_state

    if player.level < 10:
        vk.messages.send(
            user_id=user_id,
            message="🎓Наставник:\n\n«Сначала 10 уровень. До этого специализация только навредит: будешь копировать форму без понимания.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    selected = get_class(class_id)
    if not selected:
        vk.messages.send(
            user_id=user_id,
            message="🎓Наставник:\n\n«Такой школы у меня нет. Выбери нормальную специализацию из списка.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    if class_id == player.player_class:
        set_dialog_state(user_id, npc_id, "menu")
        vk.messages.send(
            user_id=user_id,
            message=f"🎓Наставник:\n\n«Ты уже идёшь школой {selected.name}. Тренируй её в поле, а не на кнопках.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    is_change = bool(player.player_class)
    if is_change and player.money < CLASS_CHANGE_COST:
        set_dialog_state(user_id, npc_id, "menu")
        vk.messages.send(
            user_id=user_id,
            message=(
                "🎓Наставник:\n\n"
                f"«Переобучение на {selected.name} стоит {CLASS_CHANGE_COST:,} руб.\n\n"
                f"У тебя есть {player.money:,} руб. Не хватает {CLASS_CHANGE_COST - player.money:,} руб.»"
            ),
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    old_money = int(player.money)
    new_money = old_money - CLASS_CHANGE_COST if is_change else old_money
    database.update_user_stats(user_id, money=new_money, player_class=class_id)
    set_dialog_state(user_id, npc_id, "menu")
    from handlers.quests import track_quest_change_class
    track_quest_change_class(user_id, vk=vk)
    invalidate_player_cache(user_id)
    player = get_player_from_module(user_id)

    class_info = format_class_info(class_id, player.level)
    payment_line = (
        f"Списано за переобучение: {CLASS_CHANGE_COST:,} руб.\nБаланс: {old_money:,} → {new_money:,}\n\n"
        if is_change else
        "Первое обучение бесплатно.\n\n"
    )
    vk.messages.send(
        user_id=user_id,
        message=(
            "🎓Наставник:\n\n"
            f"«Принято. Теперь твоя специализация — {selected.name}. "
            "Оружие выбирай под рейд, но навыки и пассивки останутся от выбранной школы.»\n\n"
            f"{payment_line}"
            f"{class_info}"
        ),
        keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
        random_id=0
    )
    return True


def _handle_show_class(player, vk, user_id: int, npc_id: str):
    """Обработка просмотра класса"""
    from models.classes import format_class_info, format_passive_status

    if not player.player_class:
        vk.messages.send(
            user_id=user_id,
            message="🎓Наставник:\n\n«У тебя ещё нет класса. Дойди до 10 уровня и выбери специализацию здесь, в Убежище.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    class_info = format_class_info(player.player_class, player.level)
    current_weapon = player.equipped_weapon or "нет"

    msg = f"🎓Наставник:\n\n"
    msg += f"📌Твой текущий класс: {player.player_class.upper()}\n"
    msg += f"🔫Экипированное оружие: {current_weapon}\n"
    msg += f"⭐Твой уровень: {player.level}\n\n"

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
    from infra.state_manager import set_dialog_state

    if npc_id != "барыга":
        vk.messages.send(
            user_id=user_id,
            message="🕴️ Торговля доступна только у Барыги.\nУ остальных NPC купля/продажа отключена.",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return

    set_dialog_state(user_id, npc_id, next_stage)

    if next_stage == "shop_menu":
        set_dialog_state(user_id, npc_id, "buy_all")
        show_trader_shop_all(player, vk, user_id)
    elif next_stage in ["shop_weapons", "shop_armor", "shop_meds", "shop_food", "shop_artifacts", "buy_artifacts"]:
        set_dialog_state(user_id, npc_id, "buy_all")
        show_trader_shop_all(player, vk, user_id)
    elif next_stage in ["sell_items", "sell_gear", "sell_artifacts"]:
        set_dialog_state(user_id, npc_id, "sell_all")
        show_trader_sell_all(player, vk, user_id)


def handle_npc_choice(player, vk, user_id: int, npc_id: str):
    """Обработка выбора NPC для разговора"""
    show_npc_dialog(player, vk, user_id, npc_id, None)


def handle_npc_back(player, vk, user_id: int):
    """Обработка возврата из диалога с NPC"""
    from infra.state_manager import clear_dialog_state, get_dialog_info
    from models.npcs import get_npc_by_location

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
