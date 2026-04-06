"""
Обработчики локаций и навигации
"""
import database
from constants import RESEARCH_LOCATIONS, NPC_LOCATIONS


def go_to_location(player, location_id: str, vk, user_id: int):
    """Переход в локацию"""
    from main import create_location_keyboard
    
    # Проверка блокировки убежища
    if location_id == "убежище":
        # Проверяем, получал ли игрок набор новичка
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT newbie_kit_received FROM users WHERE vk_id = %s", (user_id,))
        row = cursor.fetchone()
        cursor.close()
        database.release_connection(conn)

        if row and row['newbie_kit_received'] == 1:
            # Убежище заблокировано после получения набора
            vk.messages.send(
                user_id=user_id,
                message="УБЕЖИЩЕ ЗАКРЫТО\n\n"
                        "Вход закрыт. Местный житель предупреждал — после получения набора ты должен выживать в Зоне сам.\n\n"
                        "Иди на КПП -> в Зону.",
                keyboard=create_location_keyboard("город").get_keyboard(),
                random_id=0
            )
            return

    player.current_location_id = location_id
    database.update_user_location(user_id, location_id)
    
    loc = player.location
    player_level = player.level if hasattr(player, 'level') else None

    # Добавляем информацию о NPC
    npc_message = ""
    npcs = NPC_LOCATIONS.get(location_id, [])
    if npcs:
        npc_list = ", ".join([f"{npc}" for npc in npcs])
        npc_message = f"\n\nNPC: {npc_list}"

    vk.messages.send(
        user_id=user_id,
        message=f"{loc.name}\n\n{loc.description}{npc_message}",
        keyboard=create_location_keyboard(location_id, player_level).get_keyboard(),
        random_id=0
    )


def go_to_inventory(player, vk, user_id: int):
    """Открыть инвентарь - показать все категории"""
    from main import create_inventory_keyboard
    from handlers.inventory import show_all

    # Сохраняем предыдущую локацию (не город и не кпп)
    if player.current_location_id not in ["город", "кпп", "инвентарь"]:
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
    """Лечиться в больнице"""
    from main import create_location_keyboard
    
    if player.current_location_id == "больница":
        message = (
            "Ты нашёл аптечку в ржавом ящике...\n\n"
            "Перевязал раны, выпил таблетки.\n"
            "Состояние улучшилось."
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
    # Просто показываем статус как информационное сообщение
    vk.messages.send(
        user_id=user_id,
        message=player.get_status(),
        random_id=0
    )


def show_welcome(vk, user_id: int):
    """Показать приветственное сообщение"""
    from main import create_main_keyboard, get_welcome_message, create_location_keyboard
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
            message=f"{loc.name}\n\n{loc.description}",
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
