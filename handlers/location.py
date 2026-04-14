"""
Обработчики локаций и навигации
"""
import time
import database
from constants import RESEARCH_LOCATIONS, NPC_LOCATIONS

# Кулдаун рандомных событий
EVENT_COOLDOWN_SECONDS = 15 * 60        # 15 минут — базовый кулдаун
EVENT_CHANCE_RAMP_UP = 10 * 60          # каждые 10 минут после кулдауна
EVENT_CHANCE_INCREMENT = 1.5            # +1.5% шанс за каждый интервал
EVENT_MAX_CHANCE = 100                  # макс шанс


def _check_event_cooldown(user_id: int) -> bool:
    """
    Проверить кулдаун рандомных событий.
    Возвращает True если можно выдавать событие, False если на кулдауне.

    Механика:
    - После получения события — кулдаун 15 минут
    - После кулдауна — шанс растёт на 1.5% каждые 10 минут
    - Максимум 100%
    """
    last_event_time = database.get_user_flag(user_id, "last_random_event_time", 0)
    now = int(time.time())

    if last_event_time == 0:
        # Первый раз — всегда можно
        return True

    elapsed = now - last_event_time

    # Базовый кулдаун
    if elapsed < EVENT_COOLDOWN_SECONDS:
        return False

    # После кулдауна — нарастающий шанс
    time_after_cooldown = elapsed - EVENT_COOLDOWN_SECONDS
    intervals_passed = int(time_after_cooldown / EVENT_CHANCE_RAMP_UP)
    chance = min(EVENT_MAX_CHANCE, intervals_passed * EVENT_CHANCE_INCREMENT)

    import random
    return random.randint(1, 100) <= chance


def go_to_location(player, location_id: str, vk, user_id: int):
    """Переход в локацию"""
    from main import create_location_keyboard
    from random_events import get_random_event, format_event_message
    from state_manager import set_pending_event, has_pending_event, get_pending_event
    from handlers.keyboards import create_random_event_keyboard
    from handlers.quests import track_quest_explore, track_quest_visit

    # Проверка блокировки убежища
    if location_id == "убежище":
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT newbie_kit_received FROM users WHERE vk_id = %s", (user_id,))
        row = cursor.fetchone()
        cursor.close()
        database.release_connection(conn)

        if row and row['newbie_kit_received'] == 1:
            vk.messages.send(
                user_id=user_id,
                message="УБЕЖИЩЕ ЗАКРЫТО\n\n"
                        "Вход закрыт. Местный житель предупреждал — после получения набора ты должен выживать в Зоне сам.\n\n"
                        "Иди на КПП -> в Зону.",
                keyboard=create_location_keyboard("город").get_keyboard(),
                random_id=0
            )
            return

    # Трекаем квесты посещения
    track_quest_visit(user_id, location_id)

    # Сохраняем предыдущую локацию перед переходом (кроме инвентаря)
    if player.current_location_id not in ["инвентарь"]:
        player.previous_location = player.current_location_id
        database.update_user_stats(user_id, previous_location=player.current_location_id)

    player.current_location_id = location_id
    database.update_user_location(user_id, location_id)

    loc = player.location
    player_level = player.level if hasattr(player, 'level') else None

    # Трекаем квесты исследования (если дорога)
    if location_id in RESEARCH_LOCATIONS:
        track_quest_explore(user_id, location_id)

    # Случайное событие при переходе на дороги
    # НЕ очищаем pending event — если игрок в середине мульти-стадии, сохраняем
    if location_id in RESEARCH_LOCATIONS:
        # Проверяем кулдаун (нельзя спамить перезаходами)
        if _check_event_cooldown(user_id):
            # Проверяем нет ли уже активного события (мульти-стадия)
            if not has_pending_event(user_id):
                event = get_random_event(user_id=user_id)
                if event:
                    set_pending_event(user_id, event)
                    # Записываем время получения события
                    database.set_user_flag(user_id, "last_random_event_time", int(time.time()))
                    # Отправляем и сохраняем ID сообщения для редактирования
                    msg_id = vk.messages.send(
                        user_id=user_id,
                        message=f"{loc.name}\n\n{loc.description}\n\n{format_event_message(event)}",
                        keyboard=create_random_event_keyboard(event).get_keyboard(),
                        random_id=0,
                    )
                    # Сохраняем conversation_message_id для редактирования
                    if event.get("type") == "multi_stage":
                        event["_msg_id"] = msg_id
                        set_pending_event(user_id, event)
                    return
            else:
                # Уже есть активное событие — показываем его
                existing_event = get_pending_event(user_id)
                if existing_event:
                    stage_idx = existing_event.get("_stage_index", 0)
                    msg_id = vk.messages.send(
                        user_id=user_id,
                        message=f"{loc.name}\n\n{loc.description}\n\nУ тебя есть активное событие — заверши его!\n\n{format_event_message(existing_event, stage_idx)}",
                        keyboard=create_random_event_keyboard(existing_event, stage_index=stage_idx).get_keyboard(),
                        random_id=0,
                    )
                    if existing_event.get("type") == "multi_stage":
                        existing_event["_msg_id"] = msg_id
                        set_pending_event(user_id, existing_event)
                    return

    # Обычное сообщение о локации
    npc_message = ""
    npcs = NPC_LOCATIONS.get(location_id, [])
    if npcs:
        npc_list = ", ".join([f"{npc}" for npc in npcs])
        npc_message = f"\n\nNPC: {npc_list}"

    # Добавляем информацию о модификаторах локации (для исследовательских зон)
    location_info = ""
    from location_mechanics import get_location_modifier, get_zone_mutation_state
    mod = get_location_modifier(location_id)
    if mod:
        parts = []
        if mod.get("danger_mult", 1.0) > 1.0:
            parts.append(f"⚠️ Опасность +{int((mod['danger_mult'] - 1.0) * 100)}%")
        if mod.get("find_chance_mult", 1.0) > 1.0:
            parts.append(f"🔍 Находки +{int((mod['find_chance_mult'] - 1.0) * 100)}%")
        if mod.get("radiation_mult", 1.0) > 1.0:
            parts.append(f"☢️ Радиация +{int((mod['radiation_mult'] - 1.0) * 100)}%")
        if mod.get("energy_cost_mult", 1.0) > 1.0:
            parts.append(f"⚡ Энергия +{int((mod['energy_cost_mult'] - 1.0) * 100)}%")

        # Проверяем мутацию Зоны (НИИ)
        mutation_state = get_zone_mutation_state(location_id)
        if mutation_state.get("active"):
            parts.append(f"🌀 **МУТАЦИЯ ЗОНЫ!** Находки +{int(mutation_state['bonus_find'] * 100)}%")

        if parts:
            location_info = f"\n\n📊 **Параметры зоны:**\n" + "\n".join(f"• {p}" for p in parts)

    vk.messages.send(
        user_id=user_id,
        message=f"{loc.name}\n\n{loc.description}{npc_message}{location_info}",
        keyboard=create_location_keyboard(location_id, player_level).get_keyboard(),
        random_id=0
    )


def go_to_inventory(player, vk, user_id: int):
    """Открыть инвентарь - показать все категории"""
    from main import create_inventory_keyboard
    from handlers.inventory import show_all

    # Сохраняем текущую локацию как предыдущую (для возврата из инвентаря)
    if player.current_location_id not in ["инвентарь"]:
        player.previous_location = player.current_location_id
        database.update_user_stats(user_id, previous_location=player.current_location_id)

    player.current_location_id = "инвентарь"
    database.update_user_location(user_id, "инвентарь")
    
    # Показываем весь инвентарь по категориям
    show_all(player, vk, user_id)


def go_back(player, vk, user_id: int):
    """Вернуться назад (в предыдущую локацию)"""
    from main import create_location_keyboard
    
    # Используем предыдущую локацию или текущую
    target_location = player.previous_location or player.current_location_id

    # Если мы в специальных локациях - возвращаем в кпп
    if player.current_location_id in ["город", "кпп", "инвентарь"]:
        target_location = "кпп"

    if target_location != player.current_location_id:
        player.current_location_id = target_location
        database.update_user_location(user_id, target_location)

        loc = player.location
        vk.messages.send(
            user_id=user_id,
            message=f"Ты вернулся в {loc.name}\n\n{loc.description}",
            keyboard=create_location_keyboard(target_location).get_keyboard(),
            random_id=0
        )
    else:
        # Если локация та же - просто показываем клавиатуру
        vk.messages.send(
            user_id=user_id,
            message="Ты остаёшься на месте.",
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )


def handle_sleep(player, vk, user_id: int):
    """Спать в убежище"""
    from main import create_location_keyboard
    
    if player.current_location_id == "убежище":
        message = (
            "Ты ложишься на старый матрас...\n\n"
            "Сон беспокойный, снятся кошмары. Но ты отдохнул.\n"
            "+20 выносливости"
        )
        vk.messages.send(
            user_id=user_id,
            message=message,
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
    elif player.current_location_id == "больница":
        vk.messages.send(user_id=user_id, message="Здесь нельзя спать. Лучше иди в Убежище.", random_id=0)
    else:
        vk.messages.send(user_id=user_id, message="Небезопасно спать здесь. Найди убежище.", random_id=0)


def handle_heal(player, vk, user_id: int):
    """Лечиться в больнице

    Ценообразование:
      - 1-е лечение: бесплатно (помощь новичкам)
      - 2+ лечение: базовая цена + бонус за уровень, с потолком

    Формула: min(HEAL_BASE_PRICE + (level - 1) * HEAL_LEVEL_MULTIPLIER, HEAL_PRICE_CAP)
    При стартовых настройках: 100 + (level-1) * 50, максимум 3000
    """
    from main import create_location_keyboard
    import database
    import config

    if player.current_location_id == "больница":
        user_data = database.get_user_by_vk(user_id)
        treatment_count = user_data.get('hospital_treatments', 0) if user_data else 0

        # Первое лечение всегда бесплатно
        if treatment_count == 0:
            price = 0
        else:
            base = getattr(config, 'HEAL_BASE_PRICE', 100)
            multiplier = getattr(config, 'HEAL_LEVEL_MULTIPLIER', 50)
            cap = getattr(config, 'HEAL_PRICE_CAP', 3000)
            price = min(base + (player.level - 1) * multiplier, cap)

        # Проверяем, хватает ли денег
        if player.money < price:
            vk.messages.send(
                user_id=user_id,
                message=f"💸 Лечение стоит {price:,} руб., а у тебя {player.money:,} руб.\n\nСначала заработай деньги!",
                keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
                random_id=0
            )
            return

        # Лечим полностью здоровье и восстанавливаем энергию
        player.health = player.max_health
        player.energy = 100
        database.update_user_stats(user_id, health=player.health, energy=player.energy)

        # Списываем деньги и увеличиваем счетчик лечений
        new_money = player.money - price
        new_treatment_count = treatment_count + 1
        database.update_user_stats(user_id, money=new_money, hospital_treatments=new_treatment_count)

        # Формируем сообщение
        if price == 0:
            price_text = "бесплатно (первое лечение)"
        else:
            price_text = f"{price:,} руб. (лечение #{new_treatment_count}, уровень {player.level})"

        message = (
            f"🏥ЛЕЧЕНИЕ В БОЛЬНИЦЕ\n\n"
            f"Врач осмотрел тебя, перевязал раны, сделал уколы.\n\n"
            f"✅ЗДОРОВЬЕ ПОЛНОСТЬЮ ВОССТАНОВЛЕНО!\n"
            f"   HP: {player.health}/{player.max_health}\n\n"
            f"⚡ЭНЕРГИЯ ВОССТАНОВЛЕНА!\n"
            f"   Энергия: {player.energy}/100\n\n"
            f"💰 Оплата: {price_text}\n"
            f"   Осталось денег: {new_money:,} руб.\n\n"
            f"📊 Всего лечений: {new_treatment_count}"
        )

        vk.messages.send(
            user_id=user_id,
            message=message,
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
    else:
        vk.messages.send(
            user_id=user_id,
            message="Лечение доступно только в Больнице.",
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )


def get_status(player, vk, user_id: int):
    """Показать статус персонажа"""
    from state_manager import try_edit_or_send
    try_edit_or_send(
        vk, user_id,
        message=player.get_status(),
    )


def show_welcome(vk, user_id: int):
    """Показать приветственное сообщение"""
    from handlers.keyboards import create_main_keyboard, create_location_keyboard
    from handlers.commands import get_welcome_message
    from locations import get_location
    import database

    # Проверяем, новый ли игрок
    user_data = database.get_user_by_vk(user_id)

    if user_data:
        # Игрок уже существует - показываем город
        loc = get_location("город")
        player_level = user_data.get('level', 0)
        vk.messages.send(
            user_id=user_id,
            message=(
                f"{loc.name}\n\n{loc.description}\n\n"
                "P2P рынок игроков находится на Черном рынке "
                "(доступ с 25 уровня)."
            ),
            keyboard=create_location_keyboard("город", player_level).get_keyboard(),
            random_id=0
        )
    else:
        # Новый игрок - показываем приветствие
        vk.messages.send(
            user_id=user_id,
            message=get_welcome_message(),
            keyboard=create_main_keyboard().get_keyboard(),
            random_id=0
        )
