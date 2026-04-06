"""
Обработчики боя и исследования
"""
import random
import time
import threading
import database
import enemies
from constants import RESEARCH_LOCATIONS


# === Глобальное состояние ===
_combat_state = {}  # Хранит состояние боя для каждого пользователя
_research_timers = {}  # {user_id: {"start_time": timestamp, "time_sec": int, "player_data": {...}}}


# === События исследования ===
RESEARCH_EVENTS = {
    # Ничего не найдено (уменьшили шанс)
    "nothing": {
        "chance": 10,
        "message": "Ты обыскал территорию...\n\nНичего не найдено.",
        "danger": 0
    },
    # Предметы (увеличили шансы)
    "common_item": {
        "chance": 25,
        "message": "Что-то найдено!",
        "danger": 0,
        "type": "item",
        "rarity": "common"
    },
    "rare_item": {
        "chance": 15,
        "message": "Ценная находка!",
        "danger": 0,
        "type": "item",
        "rarity": "rare"
    },
    "artifact": {
        "chance": 12,
        "message": "Найден артефакт!",
        "danger": 0,
        "type": "artifact"
    },
    # Враги (максимальные шансы)
    "mutant": {
        "chance": 60,
        "message": "АТАКА МУТАНТА!",
        "danger": 30,
        "type": "enemy",
        "enemy_type": "mutant"
    },
    "bandit": {
        "chance": 50,
        "message": "Обнаружен бандит!",
        "danger": 25,
        "type": "enemy",
        "enemy_type": "bandit"
    },
    "military": {
        "chance": 35,
        "message": "Военный патруль!",
        "danger": 40,
        "type": "enemy",
        "enemy_type": "military"
    },
    # Опасность (максимальные шансы)
    "anomaly": {
        "chance": 30,
        "message": "Попадание в аномалию!",
        "danger": 35,
        "type": "anomaly"
    },
    "radiation": {
        "chance": 25,
        "message": "Радиоактивная зона!",
        "danger": 20,
        "type": "radiation"
    },
    "trap": {
        "chance": 22,
        "message": "Попадание в ловушку!",
        "danger": 25,
        "type": "trap"
    },
    # Бонусы (увеличили)
    "stash": {
        "chance": 8,
        "message": "Найден тайник сталкера!",
        "danger": 0,
        "type": "stash"
    },
    "survivor": {
        "chance": 6,
        "message": "Встречен выживший сталкер",
        "danger": 0,
        "type": "survivor"
    }
}

# Время исследования (сек) -> множитель шансов
RESEARCH_TIME_MULTIPLIERS = {
    5: {"chance": 1.0, "danger": 0.5, "name": "Быстрый поиск"},
    10: {"chance": 1.5, "danger": 1.0, "name": "Обычный поиск"},
    15: {"chance": 2.0, "danger": 1.5, "name": "Тщательный поиск"}
}

# Энергия затрачиваемая на исследование
RESEARCH_ENERGY_COST = {
    5: 1,
    10: 2,
    15: 3
}


def _get_main_imports():
    """Ленивый импорт для избежания циклической зависимости"""
    import main
    return _combat_state, main.create_location_keyboard, main.VkKeyboard, main.VkKeyboardColor


def _create_hp_bar(current: int, max_val: int, bar_length: int = 10) -> str:
    """Создать прогресс-бар HP"""
    filled = int((current / max_val) * bar_length)
    if current <= 0:
        filled = 0

    # Цвет зависит от процента HP
    percent = (current / max_val) * 100
    if percent >= 70:
        color = "[+]"
    elif percent >= 30:
        color = "[~]"
    else:
        color = "[-]"

    return color * filled + "[ ]" * (bar_length - filled)


def _handle_death(player, vk, user_id: int):
    """Обработка смерти персонажа в бою"""
    _, create_location_keyboard, _, _ = _get_main_imports()

    # Штрафы при смерти
    lost_money = player.money // 2
    lost_exp = player.experience // 4

    player.money -= lost_money
    player.experience -= lost_exp
    player.health = player.max_health // 2  # 50% HP
    player.energy = 50

    # Перемещаем игрока в город после смерти
    database.update_user_location(user_id, "город")

    database.update_user_stats(
        user_id,
        health=player.health,
        energy=player.energy,
        radiation=0,
        money=player.money,
        experience=player.experience
    )

    message = (
        f"ТЫ ПОГИБ!\n\n"
        f"Твоё тело нашли другие сталкеры и принесли в безопасное место.\n\n"
        f"Потери:\n"
        f"- Потеряно денег: {lost_money} руб.\n"
        f"- Потеряно опыта: {lost_exp}\n\n"
        f"Текущее состояние:\n"
        f"HP: {player.health}/{player.max_health}\n"
        f"Энергия: {player.energy}/100\n"
        f"Радиация: 0"
    )

    vk.messages.send(
        user_id=user_id,
        message=message,
        keyboard=create_location_keyboard("город").get_keyboard(),
        random_id=0
    )


def cancel_research(user_id: int):
    """Отменить исследование"""
    if user_id in _research_timers:
        del _research_timers[user_id]
        return True
    return False


def is_researching(user_id: int) -> bool:
    """Проверить, идёт ли исследование"""
    return user_id in _research_timers


def get_research_status(user_id: int) -> dict:
    """Получить статус исследования"""
    if user_id not in _research_timers:
        return None

    data = _research_timers[user_id]
    elapsed = time.time() - data["start_time"]
    remaining = max(0, data["time_sec"] - elapsed)

    return {
        "time_sec": data["time_sec"],
        "remaining": int(remaining),
        "location_id": data["location_id"]
    }


def show_explore_menu(player, vk, user_id: int):
    """Показать меню исследования (случайное время)"""
    _, create_location_keyboard, VkKeyboard, VkKeyboardColor = _get_main_imports()

    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Исследовать", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)

    message = (
        f"ИССЛЕДОВАНИЕ ЛОКАЦИИ\n\n"
        f"Нажми 'Исследовать' — время будет выбрано случайно.\n\n"
        f"Возможные варианты:\n"
        f"5 сек — быстрый поиск (1 энергия)\n"
        f"10 сек — обычный поиск (2 энергии)\n"
        f"15 сек — тщательный поиск (3 энергии)\n\n"
        f"Чем дольше время — тем больше находок, но выше риск.\n\n"
        f"Твоя энергия: {player.energy}/100"
    )

    vk.messages.send(
        user_id=user_id,
        message=message,
        keyboard=keyboard.get_keyboard(),
        random_id=0
    )


def handle_explore_time(player, vk, user_id: int, time_sec: int = None):
    """Запустить исследование с таймером (случайное время если не указано)"""
    # Если время не указано - выбираем случайное
    if time_sec is None:
        # Доступные варианты с весами
        time_options = [
            (5, 40),   # 40% шанс - быстрый
            (10, 35),  # 35% шанс - обычный
            (15, 25),  # 25% шанс - тщательный
        ]
        total = sum(w for _, w in time_options)
        rand = random.randint(1, total)
        cumulative = 0
        for t, w in time_options:
            cumulative += w
            if rand <= cumulative:
                time_sec = t
                break
    _combat_state, create_location_keyboard, _, _ = _get_main_imports()

    if player.current_location_id not in RESEARCH_LOCATIONS:
        return

    # Проверка: не идёт ли уже исследование
    if user_id in _research_timers:
        vk.messages.send(
            user_id=user_id,
            message="Исследование уже идёт! Дождись завершения.",
            random_id=0
        )
        return

    # Проверка энергии
    energy_cost = RESEARCH_ENERGY_COST.get(time_sec, 2)
    if player.energy < energy_cost:
        vk.messages.send(
            user_id=user_id,
            message=(
                f"Не хватает энергии!\n\n"
                f"Нужно: {energy_cost} энергии\n"
                f"У тебя: {player.energy}/100\n\n"
                f"Восстанови энергию: поешь, выпей кофе или энергетик."
            ),
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
        return

    # Тратим энергию
    player.energy -= energy_cost
    database.update_user_stats(user_id, energy=player.energy)

    # Запускаем таймер исследования
    start_time = time.time()
    location_id = player.current_location_id
    find_chance = player.find_chance
    rare_find_chance = player.rare_find_chance
    current_energy = player.energy
    max_energy = player.max_health  # используем для энергии

    # Сохраняем состояние исследования
    _research_timers[user_id] = {
        "start_time": start_time,
        "time_sec": time_sec,
        "location_id": location_id,
        "find_chance": find_chance,
        "rare_find_chance": rare_find_chance,
        "remaining_energy": current_energy,
        "player_id": user_id
    }

    # Запускаем фоновый таймер
    timer = threading.Timer(time_sec, _complete_research, args=(user_id, vk, start_time))
    timer.daemon = True
    timer.start()

    # Отправляем сообщение о начале исследования
    vk.messages.send(
        user_id=user_id,
        message=(
            f"ИССЛЕДОВАНИЕ НАЧАТО\n\n"
            f"Время: {time_sec} секунд\n"
            f"Потрачено энергии: {energy_cost}\n\n"
            f"Сканирование территории...\n"
            f"Результат придёт автоматически."
        ),
        random_id=0
    )


def _complete_research(user_id: int, vk, expected_start_time: float):
    """Завершение исследования по таймеру"""
    # Проверяем, не отменено ли исследование
    if user_id not in _research_timers:
        return

    data = _research_timers[user_id]

    # Проверяем, что это тот же таймер (не перезапущен)
    if data["start_time"] != expected_start_time:
        return

    time_sec = data["time_sec"]
    location_id = data["location_id"]
    find_chance = data["find_chance"]
    rare_find_chance = data["rare_find_chance"]
    remaining_energy = data["remaining_energy"]

    # Удаляем из активных исследований
    del _research_timers[user_id]

    # Получаем множители
    multiplier = RESEARCH_TIME_MULTIPLIERS[time_sec]
    chance_mult = multiplier['chance']
    danger_mult = multiplier['danger']

    # Выбираем событие
    event = _select_research_event_by_chance(find_chance, chance_mult, danger_mult)

    # Создаём временный объект игрока для обработки
    class TempPlayer:
        def __init__(self):
            # Получаем данные игрока для расчёта max_weight
            user_data = database.get_user_by_vk(user_id)
            strength = user_data.get('strength', 1) if user_data else 1
            base_max_weight = 20 + strength * 2

            # Проверяем экипированный рюкзак
            equipped_backpack = user_data.get('equipped_backpack') if user_data else None
            if equipped_backpack:
                backpack_item = database.get_item_by_name(equipped_backpack)
                if backpack_item:
                    base_max_weight += backpack_item.get('backpack_bonus', 0)

            self.current_location_id = location_id
            self.find_chance = find_chance
            self.rare_find_chance = rare_find_chance
            self.energy = remaining_energy
            self.health = 100  # Для обработки урона
            self.radiation = 0
            self.money = 0
            self.vk_id = user_id
            self.max_weight = base_max_weight

            class TempInventory:
                def reload(self): pass

                @property
                def total_weight(self) -> float:
                    """Общий вес инвентаря"""
                    items = database.get_user_inventory(user_id)
                    total = 0.0
                    for item in items:
                        weight = item.get('weight', 1.0)
                        quantity = item.get('quantity', 1)
                        total += weight * quantity
                    return round(total, 1)
            self.inventory = TempInventory()

    temp_player = TempPlayer()

    # Обрабатываем событие
    _handle_research_event(temp_player, vk, user_id, event, time_sec)


def _select_research_event_by_chance(find_chance: float, chance_mult: float, danger_mult: float):
    """Выбрать событие исследования на основе шансов"""
    # Базовый шанс найти что-то (увеличили базовый множитель)
    base_find_chance = min(95, find_chance * chance_mult * 1.5)  # max 95%

    # Проверяем, нашли ли что-то
    if random.randint(1, 100) > base_find_chance:
        return "nothing"

    # Выбираем событие
    weights = []
    event_ids = []

    for event_id, event_data in RESEARCH_EVENTS.items():
        if event_id == "nothing":
            continue

        base_chance = event_data["chance"]

        if event_data.get("danger", 0) > 0:
            weight = base_chance * danger_mult
        else:
            weight = base_chance * chance_mult

        weights.append(weight)
        event_ids.append(event_id)

    total_weight = sum(weights)
    if total_weight == 0:
        return "nothing"

    rand = random.uniform(0, total_weight)
    cumulative = 0

    for i, weight in enumerate(weights):
        cumulative += weight
        if rand <= cumulative:
            return event_ids[i]

    return "nothing"


def _select_research_event(player, chance_mult: float, danger_mult: float):
    """Выбрать событие исследования на основе шансов"""
    # Базовый шанс найти что-то
    find_chance = player.find_chance * chance_mult

    # Проверяем, нашли ли что-то
    if random.randint(1, 100) > find_chance:
        return "nothing"

    # Выбираем событие с учетом danger_mult
    weights = []
    event_ids = []

    for event_id, event_data in RESEARCH_EVENTS.items():
        if event_id == "nothing":
            continue

        base_chance = event_data["chance"]

        # Модифицируем шанс в зависимости от типа
        if event_data.get("danger", 0) > 0:
            # Опасные события чаще при большем danger_mult
            weight = base_chance * danger_mult
        else:
            # Находки чаще при большем chance_mult
            weight = base_chance * chance_mult

        weights.append(weight)
        event_ids.append(event_id)

    # Выбираем событие по весам
    total_weight = sum(weights)
    if total_weight == 0:
        return "nothing"

    rand = random.uniform(0, total_weight)
    cumulative = 0

    for i, weight in enumerate(weights):
        cumulative += weight
        if rand <= cumulative:
            return event_ids[i]

    return "nothing"


def _handle_research_event(player, vk, user_id: int, event_id: str, time_sec: int):
    """Обработать событие исследования"""
    _combat_state, create_location_keyboard, _, _ = _get_main_imports()

    event = RESEARCH_EVENTS.get(event_id, RESEARCH_EVENTS["nothing"])
    event_type = event.get("type", "nothing")

    if event_type == "nothing":
        vk.messages.send(
            user_id=user_id,
            message=f"Ты исследовал локацию {time_sec} секунд...\n\n{event['message']}\n\nЭнергия потрачена.",
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
        return

    if event_type == "item":
        _spawn_item(player, vk, user_id)
        return

    if event_type == "artifact":
        _spawn_artifact(player, vk, user_id)
        return

    if event_type == "enemy":
        _spawn_enemy(player, vk, user_id, event.get("enemy_type"))
        return

    if event_type == "anomaly":
        _handle_anomaly(player, vk, user_id)
        return

    if event_type == "radiation":
        _handle_radiation(player, vk, user_id)
        return

    if event_type == "trap":
        _handle_trap(player, vk, user_id)
        return

    if event_type == "stash":
        _handle_stash(player, vk, user_id)
        return

    if event_type == "survivor":
        _handle_survivor(player, vk, user_id)
        return


def _handle_anomaly(player, vk, user_id: int):
    """Обработка попадания в аномалию"""
    _, create_location_keyboard, _, _ = _get_main_imports()

    # Получаем реальные данные игрока
    user = database.get_user_by_vk(user_id)
    if not user:
        return

    damage = random.randint(10, 25)
    new_health = max(0, user['health'] - damage)
    database.update_user_stats(user_id, health=new_health)

    vk.messages.send(
        user_id=user_id,
        message=(
            f"АНОМАЛИЯ!\n\n"
            f"Ты попал в гравитационную ловушку! Тебя сильно сдавило.\n\n"
            f"Получен урон: {damage}\n"
            f"Текущее HP: {new_health}/100"
        ),
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


def _handle_radiation(player, vk, user_id: int):
    """Обработка радиоактивного заражения"""
    _, create_location_keyboard, _, _ = _get_main_imports()

    # Получаем реальные данные игрока
    user = database.get_user_by_vk(user_id)
    if not user:
        return

    rad_damage = random.randint(15, 35)
    new_health = max(0, user['health'] - rad_damage)
    new_radiation = user['radiation'] + random.randint(10, 25)

    database.update_user_stats(user_id, health=new_health, radiation=new_radiation)

    vk.messages.send(
        user_id=user_id,
        message=(
            f"РАДИАЦИЯ!\n\n"
            f"Ты вошёл в зону повышенной радиации!\n\n"
            f"Получен урон: {rad_damage}\n"
            f"Радиация: +{new_radiation}\n"
            f"HP: {new_health}/100"
        ),
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


def _handle_trap(player, vk, user_id: int):
    """Обработка ловушки"""
    _, create_location_keyboard, _, _ = _get_main_imports()

    # Получаем реальные данные игрока
    user = database.get_user_by_vk(user_id)
    if not user:
        return

    damage = random.randint(15, 30)
    new_health = max(0, user['health'] - damage)
    database.update_user_stats(user_id, health=new_health)

    vk.messages.send(
        user_id=user_id,
        message=(
            f"ЛОВУШКА!\n\n"
            f"Ты задел растяжку! Раздался щелчок...\n\n"
            f"Получен урон: {damage}\n"
            f"Текущее HP: {new_health}/100"
        ),
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


def _handle_stash(player, vk, user_id: int):
    """Обработка тайника сталкера"""
    _, create_location_keyboard, _, _ = _get_main_imports()

    # Получаем реальные данные игрока
    user = database.get_user_by_vk(user_id)
    if not user:
        return

    money = random.randint(50, 200)
    new_money = user['money'] + money
    database.update_user_stats(user_id, money=new_money)

    vk.messages.send(
        user_id=user_id,
        message=(
            f"ТАЙНИК СТАЛКЕРА!\n\n"
            f"Ты нашёл спрятанный тайник с припасами!\n\n"
            f"Найдено: {money} руб.\n"
            f"Твой баланс: {new_money} руб."
        ),
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


def _handle_survivor(player, vk, user_id: int):
    """Обработка встречи с выжившим"""
    _, create_location_keyboard, _, _ = _get_main_imports()

    # Даём небольшой бонус
    items = ["Бинт", "Аптечка", "Энергетик", "Хлеб", "Вода"]
    item = random.choice(items)
    database.add_item_to_inventory(user_id, item, 1)

    vk.messages.send(
        user_id=user_id,
        message=(
            f"ВЫЖИВШИЙ СТАЛКЕР\n\n"
            f"Ты встретил другого сталкера. Он обрадовался живому лицу.\n\n"
            f"Он поделился с тобой: {item}\n\n"
            f"'Удачи, братан. В Зоне каждый сам за себя.'"
        ),
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


def _spawn_artifact(player, vk, user_id: int):
    """Спавн артефакта"""
    _, create_location_keyboard, _, _ = _get_main_imports()

    # Получаем случайный артефакт
    artifacts = database.get_items_by_category('artifacts')
    if not artifacts:
        vk.messages.send(
            user_id=user_id,
            message="Ты обыскал территорию...\n\nАртефактов не найдено.",
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
        return

    artifact = random.choice(artifacts)
    database.add_item_to_inventory(user_id, artifact['name'], 1)

    vk.messages.send(
        user_id=user_id,
        message=(
            f"АРТЕФАКТ!\n\n"
            f"Ты нашёл редкий артефакт: {artifact['name']}!\n\n"
            f"{artifact['description']}\n\n"
            f"Добавлено в инвентарь."
        ),
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


def handle_explore(player, vk, user_id: int):
    """Исследовать локацию - показать меню выбора времени"""
    show_explore_menu(player, vk, user_id)


def _handle_found_something(player, vk, user_id: int):
    """Обработка найденного предмета/врага"""
    encounter_type = random.randint(1, 100)
    
    if encounter_type <= 50:
        _spawn_enemy(player, vk, user_id)
    else:
        _spawn_item(player, vk, user_id)


def _spawn_enemy(player, vk, user_id: int, enemy_type: str = None):
    """Спавн врага"""
    _combat_state, create_location_keyboard, VkKeyboard, VkKeyboardColor = _get_main_imports()

    # Если указан тип врага - используем его, иначе - случайный для локации
    if enemy_type:
        enemy = enemies.get_enemy_by_type(enemy_type)
    else:
        enemy = enemies.get_enemy_for_location(player.current_location_id)

    if not enemy:
        return
    
    # Сохраняем состояние боя
    _combat_state[user_id] = {
        'enemy_name': enemy['name'],
        'enemy_hp': enemy['hp'],
        'enemy_max_hp': enemy['hp'],
        'enemy_damage': enemy['damage'],
        'enemy_description': enemy['description'],
        'location_id': player.current_location_id
    }
    
    # Отладочный вывод
    import sys
    print(f"[DEBUG] Spawned enemy for user {user_id}: {enemy['name']}, combat state: {_combat_state.get(user_id)}", file=sys.stderr)

    message = (
        f"ОПАСНОСТЬ!\n\n"
        f"Во время исследования ты заметил {enemy['name']}!\n\n"
        f"{enemy['description']}\n\n"
        f"HP: {enemy['hp']} | Урон: {enemy['damage']}\n\n"
        f"Что будешь делать?"
    )
    
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Атаковать", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("Убежать", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("В КПП", color=VkKeyboardColor.PRIMARY)

    vk.messages.send(user_id=user_id, message=message, keyboard=keyboard.get_keyboard(), random_id=0)


def _spawn_item(player, vk, user_id: int):
    """Спавн предмета"""
    _combat_state, create_location_keyboard, _, _ = _get_main_imports()

    category = random.choice(['weapons', 'armor', 'artifacts', 'other'])
    items_in_category = database.get_items_by_category(category)

    if not items_in_category:
        vk.messages.send(
            user_id=user_id,
            message="Ты обыскал территорию...\n\nНичего не найдено.",
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
        return
    
    is_rare = random.randint(1, 100) <= player.rare_find_chance
    
    if is_rare and category in ['weapons', 'armor']:
        items_in_category = sorted(items_in_category, key=lambda x: x.get('price', 0), reverse=True)
        found_item = items_in_category[0] if items_in_category else None
        rarity_text = "РЕДКАЯ НАХОДКА!\n\n"
    else:
        found_item = random.choice(items_in_category)
        rarity_text = ""
    
    if not found_item:
        return
    
    item_weight = found_item.get('weight', 1.0)
    current_weight = player.inventory.total_weight
    
    if current_weight + item_weight > player.max_weight:
        message = (
            f"Ты обыскал территорию!\n\n"
            f"Найдено {found_item['name']}, но не можешь взять — не хватает места!\n"
            f"Вес предмета: {item_weight}кг\n"
            f"Твой рюкзак: {current_weight}/{player.max_weight}кг"
        )
    else:
        database.add_item_to_inventory(user_id, found_item['name'], 1)
        player.inventory.reload()
        
        item_info = f"{found_item['name']}"
        if found_item.get('attack'):
            item_info += f" УРН:{found_item['attack']}"
        if found_item.get('defense'):
            item_info += f" ЗАЩ:{found_item['defense']}"

        message = f"Ты обыскал территорию!\n\n{rarity_text}Найдено: {item_info}\nВес: {item_weight}кг"

    vk.messages.send(
        user_id=user_id,
        message=message,
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


def create_combat_keyboard():
    """Клавиатура боя"""
    from vk_api.keyboard import VkKeyboard, VkKeyboardColor
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Атаковать", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("Убежать", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("В КПП", color=VkKeyboardColor.PRIMARY)
    return keyboard


def handle_combat_attack(player, vk, user_id: int):
    """Атаковать врага"""
    _combat_state, create_location_keyboard, _, _ = _get_main_imports()

    combat = _combat_state.get(user_id)
    if not combat:
        return
    
    weapon_damage = 0
    weapon_name = None
    weapon_is_knife = False

    if player.equipped_weapon:
        item = database.get_item_by_name(player.equipped_weapon)
        if item:
            weapon_damage = item.get('attack', 0)
            weapon_name = player.equipped_weapon
            # Проверяем, нож ли это
            weapon_lower = weapon_name.lower()
            weapon_is_knife = ("knife" in weapon_lower or "machete" in weapon_lower or
                             "bayonet" in weapon_lower or "dagger" in weapon_lower or
                             "нож" in weapon_lower or "мачете" in weapon_lower)

    melee = player.melee_damage
    total_damage = weapon_damage + melee
    
    is_crit = random.randint(1, 100) <= player.crit_chance
    if is_crit:
        total_damage = int(total_damage * 1.5)
    
    combat['enemy_hp'] -= total_damage
    
    # Проверка кровотечения при атаке ножом
    bleed_applied = False
    if weapon_is_knife:
        bleed_chance = 30 + player.luck * 2  # 30-50% + удача
        if random.randint(1, 100) <= bleed_chance:
            combat['bleed_turns'] = combat.get('bleed_turns', 0) + 3  # 3 хода кровотечения
            bleed_applied = True

    # Урон от кровотечения (если есть)
    bleed_damage = 0
    if combat.get('bleed_turns', 0) > 0:
        bleed_damage = 5 + player.luck  # 5-10 урона от кровотечения
        combat['enemy_hp'] -= bleed_damage
        combat['bleed_turns'] -= 1

    # Формируем сообщение об уроне
    damage_details = []
    if weapon_damage > 0:
        damage_details.append(f"Оружие {weapon_name}: {weapon_damage}")
    damage_details.append(f"Рукопашный: {melee}")

    message = f"Ты атакуешь {combat['enemy_name']}!\n\n"
    if is_crit:
        message += f"КРИТИЧЕСКИЙ УДАР! x1.5\n"
    message += f"Нанесён урон: {total_damage}\n"
    message += f"({' | '.join(damage_details)})\n"

    # Сообщение о кровотечении
    if bleed_applied:
        message += f"КРОВОТЕЧЕНИЕ! Враг истекает кровью!\n"
    if bleed_damage > 0:
        message += f"Кровотечение наносит {bleed_damage} урона!\n"

    # Определяем какую клавиатуру показывать
    keyboard = None

    if combat['enemy_hp'] <= 0:
        message += _handle_victory(player, combat, user_id)
        keyboard = create_location_keyboard(player.current_location_id)
    else:
        enemy_damage = combat['enemy_damage']
        
        is_dodged = random.randint(1, 100) <= player.dodge_chance
        if is_dodged:
            message += f"\nТы уклонился от атаки!"
        else:
            total_defense = player.total_defense
            final_damage = max(1, enemy_damage - total_defense)
            player.health -= final_damage

            # Проверка на смерть
            if player.health <= 0:
                player.health = 0
                database.update_user_stats(user_id, health=0)
                del _combat_state[user_id]
                _handle_death(player, vk, user_id)
                return

            database.update_user_stats(user_id, health=player.health)
            message += f"\n{combat['enemy_name']} атакует!\nПолучен урон: {final_damage}"

        # Показываем состояние кровотечения
        if combat.get('bleed_turns', 0) > 0:
            message += f"\nКровотечение: {combat['bleed_turns']} ходов"

        # Прогресс-бары HP
        enemy_hp_bar = _create_hp_bar(combat['enemy_hp'], combat['enemy_max_hp'])
        player_hp_bar = _create_hp_bar(player.health, player.max_health)

        message += (
            f"\n\n{combat['enemy_name']}\n"
            f"HP {enemy_hp_bar} {combat['enemy_hp']}/{combat['enemy_max_hp']}\n\n"
            f"Ты\n"
            f"HP {player_hp_bar} {player.health}/{player.max_health}"
        )

        # Сохраняем состояние боя и показываем клавиатуру боя
        _combat_state[user_id] = combat
        keyboard = create_combat_keyboard()

    vk.messages.send(
        user_id=user_id,
        message=message,
        keyboard=keyboard.get_keyboard(),
        random_id=0
    )


def handle_combat_flee(player, vk, user_id: int):
    """Попытаться убежать"""
    _combat_state, create_location_keyboard, _, _ = _get_main_imports()

    combat = _combat_state.get(user_id)
    if not combat:
        return
    
    if random.randint(1, 100) <= 50:
        del _combat_state[user_id]
        player_hp_bar = _create_hp_bar(player.health, player.max_health)
        vk.messages.send(
            user_id=user_id,
            message=f"Тебе удалось сбежать!\n\nТы\nHP {player_hp_bar} {player.health}/{player.max_health}",
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
    else:
        enemy_damage = combat['enemy_damage']
        total_defense = player.total_defense
        final_damage = max(1, enemy_damage - total_defense)
        player.health -= final_damage

        # Проверка на смерть
        if player.health <= 0:
            player.health = 0
            database.update_user_stats(user_id, health=0)
            del _combat_state[user_id]
            _handle_death(player, vk, user_id)
            return

        database.update_user_stats(user_id, health=player.health)
        
        player_hp_bar = _create_hp_bar(player.health, player.max_health)

        vk.messages.send(
            user_id=user_id,
            message=f"Не удалось сбежать!\n\n{combat['enemy_name']} атакует!\nПолучен урон: {final_damage} (защита: {total_defense})\n\nТы\nHP {player_hp_bar} {player.health}/{player.max_health}",
            keyboard=create_combat_keyboard().get_keyboard(),
            random_id=0
        )


def _handle_victory(player, combat, user_id: int) -> str:
    """Обработка победы над врагом"""
    _combat_state, _, _, _ = _get_main_imports()

    del _combat_state[user_id]
    
    experience = random.randint(10, 30)
    money = random.randint(5, 25)
    
    player.experience += experience
    player.money += money
    
    database.update_user_stats(user_id, experience=player.experience, money=player.money)
    
    level_up = player._check_level_up()
    
    player_hp_bar = _create_hp_bar(player.health, player.max_health)

    message = (
        f"ПОБЕДА!\n\n"
        f"Ты победил {combat['enemy_name']}!\n\n"
        f"Награда: {money} руб.\n"
        f"Опыт: +{experience}\n\n"
        f"Ты\n"
        f"HP {player_hp_bar} {player.health}/{player.max_health}\n"
    )

    if level_up:
        message += f"\n{level_up}"
    
    return message
