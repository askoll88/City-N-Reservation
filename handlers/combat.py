"""
Обработчики боя и исследования
"""
import random
import time
import threading
import database
import enemies
from constants import RESEARCH_LOCATIONS
from state_manager import _combat_state, set_combat_state, is_in_combat, get_combat_data
_research_timers = {}  # {user_id: {"start_time": timestamp, "time_sec": int, "player_data": {...}}}
_skill_cooldowns = {}  # {user_id: {"skill_name": turns_remaining}}
_active_skill_effects = {}  # {user_id: {"effect_name": turns_remaining, ...}}


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
    from vk_api.keyboard import VkKeyboard, VkKeyboardColor
    return _combat_state, main.create_location_keyboard, VkKeyboard, VkKeyboardColor


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
        clear_research_state(user_id)
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


def cleanup_research_timers():
    """Удалить записи таймеров, время которых уже истекло"""
    current_time = time.time()
    expired = [
        uid for uid, data in _research_timers.items()
        if current_time - data["start_time"] > data["time_sec"] + 60  # +60 сек запас
    ]
    for uid in expired:
        del _research_timers[uid]

def handle_explore_time(player, vk, user_id: int, time_sec: int = None):
    cleanup_research_timers()
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

    # Проверка энергии (с модификатором локации)
    from location_mechanics import get_energy_cost_mult
    energy_cost_base = RESEARCH_ENERGY_COST.get(time_sec, 2)
    energy_cost = max(1, int(energy_cost_base * get_energy_cost_mult(player.current_location_id)))

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
    current_energy = player.energy
    remaining_energy = current_energy - energy_cost

    vk.messages.send(
        user_id=user_id,
        message=(
            f"🔍ИССЛЕДОВАНИЕ НАЧАТО\n\n"
            f"⏱️ Время: {time_sec} секунд\n"
            f"⚡ Энергия: {current_energy} → {remaining_energy} (-{energy_cost})\n\n"
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

    # Выбираем событие (с модификаторами локации)
    event = _select_research_event_by_chance(find_chance, chance_mult, danger_mult, location_id)

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

            # Получаем данные детектора
            equipped_device = user_data.get('equipped_device') if user_data else None

            self.current_location_id = location_id
            self.find_chance = find_chance
            self.rare_find_chance = rare_find_chance
            self.energy = remaining_energy
            self.equipped_device = equipped_device  # Добавляем детектор
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

    # === Уникальные механики локаций ===
    _check_location_unique_mechanics(location_id, event, vk, user_id)


def _check_location_unique_mechanics(location_id: str, event_id: str, vk, user_id: int):
    """Проверить и применить уникальные механики локаций после исследования"""
    from location_mechanics import (
        check_ambush, check_zone_mutation, check_mutant_hunt,
        get_mutant_hunt_count,
    )
    _, create_location_keyboard, VkKeyboard, VkKeyboardColor = _get_main_imports()
    _combat_state_ref, _, _, _ = _get_main_imports()

    # === Военная дорога: ЗАСАДА ===
    if check_ambush(location_id):
        vk.messages.send(
            user_id=user_id,
            message=(
                "💀 **ЗАСАДА!**\n\n"
                "Ты попал в военную засаду! Солдаты заметили тебя...\n"
                "Будет бой — но награда стоит риска.\n\n"
                "⚔️ Лут после победы: x2"
            ),
            random_id=0,
        )
        # Запускаем бой с засадой — модифицируем состояние
        # Удвоенный лут будет обработан в _handle_enemy_loot
        combat_data = _combat_state_ref.get(user_id)
        if combat_data:
            combat_data["ambush"] = True  # Флаг для удвоенного лута

    # === НИИ: МУТАЦИЯ ЗОНЫ ===
    mutation = check_zone_mutation(location_id)
    if mutation and mutation.get("active"):
        vk.messages.send(
            user_id=user_id,
            message=mutation["message"],
            random_id=0,
        )

    # === Заражённый лес: ОХОТА МУТАНТОВ ===
    if check_mutant_hunt() and event_id and "enemy" in str(RESEARCH_EVENTS.get(event_id, {}).get("type", "")):
        hunt_count = get_mutant_hunt_count()
        vk.messages.send(
            user_id=user_id,
            message=(
                f"🐺 **ОХОТА МУТАНТОВ!**\n\n"
                "Ты убил мутанта, но его сородичи пришли мстить!\n"
                f"Стая из {hunt_count} мутантов атакует тебя!\n\n"
                "Приготовься к бою!"
            ),
            random_id=0,
        )
        # Запускаем дополнительный бой
        # (будет обработано через состояние боя)
        if _combat_state_ref.get(user_id):
            _combat_state_ref[user_id]["mutant_hunt"] = hunt_count


def _select_research_event_by_chance(find_chance: float, chance_mult: float, danger_mult: float, location_id: str = None):
    """Выбрать событие исследования на основе шансов и модификаторов локации"""
    from location_mechanics import get_event_weights, get_find_chance_mult, get_danger_mult

    # Применяем модификаторы локации
    loc_find_mult = get_find_chance_mult(location_id) if location_id else 1.0
    loc_danger_mult = get_danger_mult(location_id) if location_id else 1.0
    loc_event_weights = get_event_weights(location_id) if location_id else {}

    # Базовый шанс найти что-то (с модификатором локации)
    base_find_chance = min(95, find_chance * chance_mult * 1.5 * loc_find_mult)  # max 95%

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
            weight = base_chance * danger_mult * loc_danger_mult
        else:
            weight = base_chance * chance_mult

        # Применяем веса локации (если есть)
        if loc_event_weights:
            # Проверяем прямой вес для этого события
            loc_weight = loc_event_weights.get(event_id)
            if loc_weight is not None:
                weight *= loc_weight
            # Проверяем общий вес для типа события (например "enemy")
            event_type = event_data.get("type")
            if event_type and event_type in loc_event_weights:
                weight *= loc_event_weights[event_type]

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


# Состояние взаимодействия с аномалиями
_anomaly_state = {}


def _handle_anomaly(player, vk, user_id: int):
    """Обработка попадания в аномалию"""
    import anomalies as anomalies_module
    _, create_location_keyboard, VkKeyboard, VkKeyboardColor = _get_main_imports()

    # Получаем данные игрока
    user = database.get_user_by_vk(user_id)
    if not user:
        return

    # Проверяем детектор - БЕЗ ДЕТЕКТОРА АНОМАЛИЮ НЕ ВИДНО!
    detector = anomalies_module.get_equipped_detector(player)
    if not detector:
        # Без детектора аномалия не обнаружена - игрок просто исследует дальше
        vk.messages.send(
            user_id=user_id,
            message=(
                "Ты исследуешь территорию...\n\n"
                "Аномалий не обнаружено (нужен детектор).\n\n"
                "Энергия потрачена."
            ),
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
        return

    # Получаем случайную аномалию (с учётом локации)
    from location_mechanics import get_random_anomaly_for_location
    anomaly = get_random_anomaly_for_location(player.current_location_id)
    anomaly_type = anomaly["type"]
    anomaly_name = anomaly["name"]
    anomaly_icon = anomaly["icon"]
    anomaly_desc = anomaly["description"]
    anomaly_danger = anomaly["danger_level"]

    # Получаем бонус детектора
    detector_bonus = anomalies_module.get_detector_bonus(player)
    detector_name = detector["name"]

    # Урон с детектором (меньше)
    damage_min, damage_max = anomaly.get("damage_with_detector", [5, 15])

    # Возможные артефакты в этой аномалии
    possible_artifacts = anomaly.get("artifacts", [])

    # Получаем количество гильз
    shells = database.get_user_shells(user_id)

    # Сохраняем состояние аномалии
    _anomaly_state[user_id] = {
        "anomaly_type": anomaly_type,
        "anomaly_name": anomaly_name,
        "anomaly_icon": anomaly_icon,
        "damage_min": damage_min,
        "damage_max": damage_max,
        "possible_artifacts": possible_artifacts,
        "detector": detector_name,
        "detector_bonus": detector_bonus,
        "location_id": player.current_location_id
    }

    # Формируем сообщение
    message = (
        f"⚠️ АНОМАЛИЯ ОБНАРУЖЕНА! ⚠️\n\n"
        f"{anomaly_icon} {anomaly_name}\n"
        f"{anomaly_desc}\n\n"
        f"Опасность: {anomaly_danger}\n"
        f"Детектор: {detector_name} (+{detector_bonus}% к шансу)\n"
        f"Гильзы: {shells} шт.\n"
    )

    if possible_artifacts:
        message += f"Возможные артефакты: {', '.join(possible_artifacts)}\n"

    message += "\nВыбери действие:"

    # Клавиатура выбора
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Обойти", color=VkKeyboardColor.POSITIVE)
    if shells > 0:
        keyboard.add_button("Бросить гильзу", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Отступить", color=VkKeyboardColor.NEGATIVE)

    if shells == 0:
        message += "\n\n⚠️ У тебя нет гильз! Сначала найди гильзы."

    vk.messages.send(
        user_id=user_id,
        message=message,
        keyboard=keyboard.get_keyboard(),
        random_id=0
    )


def handle_anomaly_action(player, vk, user_id: int, action: str):
    """Обработка действия игрока с аномалией"""
    import anomalies as anomalies_module

    _, create_location_keyboard, VkKeyboard, VkKeyboardColor = _get_main_imports()

    # Получаем состояние аномалии
    anomaly_data = _anomaly_state.get(user_id)
    if not anomaly_data:
        return

    anomaly_type = anomaly_data["anomaly_type"]
    anomaly_name = anomaly_data["anomaly_name"]
    anomaly_icon = anomaly_data["anomaly_icon"]
    damage_min = anomaly_data["damage_min"]
    damage_max = anomaly_data["damage_max"]
    possible_artifacts = anomaly_data["possible_artifacts"]
    location_id = anomaly_data["location_id"]

    user = database.get_user_by_vk(user_id)
    if not user:
        return

    # Удаляем состояние аномалии
    del _anomaly_state[user_id]

    if action == "обойти":
        # Попытка обойти - зависит от восприятия
        perception = user.get('perception', 1)
        dodge_chance = 30 + perception * 5  # 30-80%

        if random.randint(1, 100) <= dodge_chance:
            vk.messages.send(
                user_id=user_id,
                message=(
                    f"{anomaly_icon} ОБХОД\n\n"
                    f"Ты аккуратно обошёл аномалию '{anomaly_name}'.\n\n"
                    f"Твоё восприятие помогло найти безопасный путь.\n\n"
                    f"Никаких потерь."
                ),
                keyboard=create_location_keyboard(location_id).get_keyboard(),
                random_id=0
            )
        else:
            # Не удалось обойти - получаем урон
            damage = random.randint(damage_min, damage_max)
            new_health = max(0, user['health'] - damage)
            database.update_user_stats(user_id, health=new_health)

            vk.messages.send(
                user_id=user_id,
                message=(
                    f"{anomaly_icon} НЕУДАЧНЫЙ ОБХОД\n\n"
                    f"Не удалось обойти аномалию '{anomaly_name}'!\n\n"
                    f"Получен урон: {damage}\n"
                    f"Текущее HP: {new_health}/100"
                ),
                keyboard=create_location_keyboard(location_id).get_keyboard(),
                random_id=0
            )

    elif action == "бросить гильзу" or action == "добыть":
        # === НОВАЯ МЕХАНИКА: бросок гильзы ===
        shells = database.get_user_shells(user_id)

        if shells <= 0:
            # Нет гильз - показываем сообщение и возвращаем в меню аномалии
            vk.messages.send(
                user_id=user_id,
                message=(
                    f"{anomaly_icon} НЕТ ГИЛЬЗ!\n\n"
                    f"У тебя нет гильз для добычи артефакта.\n\n"
                    f"Сначала найди гильзы (выпадают с врагов или покупаются)."
                ),
                keyboard=create_location_keyboard(location_id).get_keyboard(),
                random_id=0
            )
            return

        # Тратим одну гильзу
        database.remove_shells(user_id, 1)
        shells_after = shells - 1

        # Получаем бонус детектора
        detector = anomalies_module.get_equipped_detector(player)
        detector_bonus = anomalies_module.get_detector_bonus(player) if detector else 0

        # Бросок гильзы - пытаемся получить артефакт
        luck = user.get('luck', 5)
        result = database.roll_artifact_from_anomaly(anomaly_type, luck, detector_bonus)

        if result:
            # Артефакт получен!
            artifact_name = result["name"]
            rarity = result["rarity"]

            # Добавляем артефакт в инвентарь
            database.add_item_to_inventory(user_id, artifact_name, 1)
            from handlers.quests import track_quest_artifact
            track_quest_artifact(user_id)

            # Формируем сообщение об успехе
            rarity_emoji = {
                "common": "⚪",
                "rare": "🔵",
                "unique": "🟣",
                "legendary": "🟡"
            }.get(rarity, "⚪")

            vk.messages.send(
                user_id=user_id,
                message=(
                    f"{anomaly_icon} ✨ АРТЕФАКТ ПОЛУЧЕН! ✨\n\n"
                    f"Ты бросил гильзу в аномалию '{anomaly_name}'...\n\n"
                    f"{rarity_emoji}{artifact_name}\n"
                    f"Редкость: {rarity}\n\n"
                    f"Гильз осталось: {shells_after}\n\n"
                    f"Артефакт добавлен в инвентарь!"
                ),
                keyboard=create_location_keyboard(location_id).get_keyboard(),
                random_id=0
            )
        else:
            # Артефакт не выпал - гильза потеряна
            vk.messages.send(
                user_id=user_id,
                message=(
                    f"{anomaly_icon} ПОПЫТКА ДОБЫЧИ\n\n"
                    f"Ты бросил гильзу в аномалию '{anomaly_name}'...\n\n"
                    f"Гильза сгорела в аномалии!\n"
                    f"Артефакт не выпал.\n\n"
                    f"Гильз осталось: {shells_after}"
                ),
                keyboard=create_location_keyboard(location_id).get_keyboard(),
                random_id=0
            )

    elif action == "отступить":
        # Гарантированный урон при отступлении
        damage = random.randint(damage_min, damage_max)
        new_health = max(0, user['health'] - damage)
        database.update_user_stats(user_id, health=new_health)

        vk.messages.send(
            user_id=user_id,
            message=(
                f"{anomaly_icon} ОТСТУПЛЕНИЕ\n\n"
                f"Ты решил отступить от аномалии '{anomaly_name}'.\n\n"
                f"При отступлении аномалия нанесла удар:\n"
                f"Получен урон: {damage}\n"
                f"Текущее HP: {new_health}/100"
            ),
            keyboard=create_location_keyboard(location_id).get_keyboard(),
            random_id=0
        )


def _handle_radiation(player, vk, user_id: int):
    """Обработка радиоактивного заражения (с модификатором локации)"""
    from location_mechanics import get_radiation_mult
    _, create_location_keyboard, _, _ = _get_main_imports()

    # Получаем реальные данные игрока
    user = database.get_user_by_vk(user_id)
    if not user:
        return

    rad_mult = get_radiation_mult(player.current_location_id)
    rad_damage = int(random.randint(15, 35) * rad_mult)
    rad_gain = int(random.randint(10, 25) * rad_mult)
    new_health = max(0, user['health'] - rad_damage)
    new_radiation = user['radiation'] + rad_gain

    database.update_user_stats(user_id, health=new_health, radiation=new_radiation)

    rad_mult_text = f" (x{rad_mult:.1f} зона)" if rad_mult != 1.0 else ""

    vk.messages.send(
        user_id=user_id,
        message=(
            f"РАДИАЦИЯ!\n\n"
            f"Ты вошёл в зону повышенной радиации!{rad_mult_text}\n\n"
            f"Получен урон: {rad_damage}\n"
            f"Радиация: +{rad_gain}\n"
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
    from handlers.quests import track_quest_artifact
    track_quest_artifact(user_id)

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
    """Спавн предмета (с учётом локации)"""
    _combat_state, create_location_keyboard, _, _ = _get_main_imports()
    from location_mechanics import get_location_loot_bias, get_location_loot_bias_chance

    # Проверяем бонус локации
    bias_items = get_location_loot_bias(player.current_location_id)
    bias_chance = get_location_loot_bias_chance(player.current_location_id)

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

    # Проверяем бонус локации — шанс получить тематический предмет
    found_item = None
    is_rare = random.randint(1, 100) <= player.rare_find_chance

    if bias_items and random.random() < bias_chance:
        # Пытаемся найти предмет из бонусного списка
        for bias_name in bias_items:
            for item in items_in_category:
                if bias_name.lower() in item['name'].lower():
                    found_item = item
                    break
            if found_item:
                break

    # Если не нашли бонусный — выбираем случайно
    if not found_item:
        if is_rare and category in ['weapons', 'armor']:
            items_in_category = sorted(items_in_category, key=lambda x: x.get('price', 0), reverse=True)
            found_item = items_in_category[0] if items_in_category else None
            rarity_text = "РЕДКАЯ НАХОДКА!\n\n"
        else:
            found_item = random.choice(items_in_category)
            rarity_text = ""
    else:
        rarity_text = "🎯 **ТЕМАТИЧЕСКАЯ НАХОДКА!**\n\n"

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


def create_combat_keyboard(player=None, user_id=None):
    """Клавиатура боя"""
    from vk_api.keyboard import VkKeyboard, VkKeyboardColor
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Атаковать", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("Убежать", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    # Кнопка навыков - показываем только если есть класс
    if player and player.player_class:
        keyboard.add_button("Навыки", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("В КПП", color=VkKeyboardColor.PRIMARY)
    return keyboard


def create_skills_keyboard(player, user_id: int = None):
    """Клавиатура навыков в бою"""
    from vk_api.keyboard import VkKeyboard, VkKeyboardColor
    from classes import get_class, get_class_by_weapon

    keyboard = VkKeyboard(one_time=False)

    # Определяем текущий класс по оружию
    current_weapon = player.equipped_weapon
    class_id = get_class_by_weapon(current_weapon) if current_weapon else player.player_class

    if not class_id:
        return None

    player_class = get_class(class_id)
    if not player_class:
        return None

    # Получаем кулдауны игрока
    if user_id is None:
        user_id = getattr(player, 'vk_id', None)
    cooldowns = _skill_cooldowns.get(user_id, {})
    active_effects = _active_skill_effects.get(user_id, {})

    # Добавляем кнопки активных навыков
    for skill in player_class.active_skills:
        skill_name = skill["name"]
        skill_cost = skill["energy_cost"]
        cd = cooldowns.get(skill_name, 0)

        # Проверяем, можно ли использовать навык
        can_use = True
        status = ""

        if player.energy < skill_cost:
            can_use = False
            status = f" (мало энергии)"
        elif cd > 0:
            can_use = False
            status = f" (перезарядка {cd} ход)"

        # Проверяем активные эффекты
        for effect_name, effect_turns in active_effects.items():
            if "damage_boost" in str(skill.get("effect", {})) and effect_name == "damage_boost":
                status = f" (активен)"
            elif skill_name == "Уклонение" and effect_name == "perfect_dodge":
                status = f" (активен)"
            elif skill_name == "Бронирование" and effect_name == "temp_defense":
                status = f" (активен)"

        btn_text = f"{skill_name} ({skill_cost} эн)"
        if status:
            btn_text = f"{skill_name}{status}"

        color = VkKeyboardColor.POSITIVE if can_use else VkKeyboardColor.SECONDARY
        keyboard.add_button(btn_text, color=color)
        keyboard.add_line()

    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def show_skills_in_combat(player, vk, user_id):
    """Показать навыки в бою"""
    from classes import get_class, get_class_by_weapon

    current_weapon = player.equipped_weapon
    class_id = get_class_by_weapon(current_weapon) if current_weapon else player.player_class

    if not class_id:
        vk.messages.send(
            user_id=user_id,
            message="⚡ У тебя нет класса!\n\nСначала получи класс у Наставника в Убежище.",
            random_id=0
        )
        return

    player_class = get_class(class_id)
    if not player_class:
        return

    # Формируем сообщение
    msg = f"⚡НАВЫКИ КЛАССА {class_id.upper()}\n\n"
    msg += f"Твоя энергия: {player.energy}/100\n\n"

    cooldowns = _skill_cooldowns.get(user_id, {})
    active_effects = _active_skill_effects.get(user_id, {})

    for skill in player_class.active_skills:
        skill_name = skill["name"]
        skill_desc = skill["description"]
        skill_cost = skill["energy_cost"]
        cd = cooldowns.get(skill_name, 0)

        # Проверяем активные эффекты
        effect_active = False
        for effect_name in active_effects:
            if "damage_boost" in str(skill.get("effect", {})) and effect_name == "damage_boost":
                effect_active = True

        status = "✅ Готов" if cd == 0 and not effect_active else "⏳"
        if cd > 0:
            status = f"🔄 Перезарядка: {cd} ход"
        elif effect_active:
            status = f"✨ Активен"
        elif player.energy < skill_cost:
            status = f"❌ Мало энергии"

        msg += f"<b>{skill_name}\n"
        msg += f"   {skill_desc}\n"
        msg += f"   Энергия: {skill_cost} | Кулдаун: {skill['cooldown']} ходов\n"
        msg += f"   Статус: {status}\n\n"

    # Показываем активные эффекты
    if active_effects:
        msg += "🔮Активные эффекты:\n"
        for effect_name, turns in active_effects.items():
            msg += f"• {effect_name}: {turns} ходов\n"

    keyboard = create_skills_keyboard(player, user_id)
    if not keyboard:
        return

    vk.messages.send(
        user_id=user_id,
        message=msg,
        keyboard=keyboard.get_keyboard(),
        random_id=0
    )


def use_skill(player, vk, user_id: int, skill_name: str):
    """Использовать навык в бою"""
    from classes import get_class, get_class_by_weapon
    import database

    combat = _combat_state.get(user_id)
    if not combat:
        vk.messages.send(
            user_id=user_id,
            message="⚠️ Ты не в бою!",
            random_id=0
        )
        return

    current_weapon = player.equipped_weapon
    class_id = get_class_by_weapon(current_weapon) if current_weapon else player.player_class

    if not class_id:
        vk.messages.send(
            user_id=user_id,
            message="⚡ У тебя нет класса!",
            random_id=0
        )
        return

    player_class = get_class(class_id)
    if not player_class:
        return

    # Ищем навык
    skill = None
    for s in player_class.active_skills:
        if skill_name.lower() in s["name"].lower():
            skill = s
            break

    if not skill:
        vk.messages.send(
            user_id=user_id,
            message=f"⚡ Навык '{skill_name}' не найден!",
            random_id=0
        )
        return

    # Проверяем кулдаун
    cooldowns = _skill_cooldowns.get(user_id, {})
    if cooldowns.get(skill["name"], 0) > 0:
        vk.messages.send(
            user_id=user_id,
            message=f"⚡ Навык '{skill['name']}' на перезарядке! Осталось {cooldowns[skill['name']]} ходов.",
            random_id=0
        )
        return

    # Проверяем энергию
    if player.energy < skill["energy_cost"]:
        vk.messages.send(
            user_id=user_id,
            message=f"⚡ Не хватает энергии! Нужно {skill['energy_cost']}, есть {player.energy}.",
            random_id=0
        )
        return

    # Тратим энергию
    new_energy = player.energy - skill["energy_cost"]
    database.update_user_stats(user_id, energy=new_energy)
    player.energy = new_energy

    # Устанавливаем кулдаун
    if user_id not in _skill_cooldowns:
        _skill_cooldowns[user_id] = {}
    _skill_cooldowns[user_id][skill["name"]] = skill["cooldown"]

    # Применяем эффект навыка
    effect = skill.get("effect", {})
    result_msg = _apply_skill_effect(player, vk, user_id, skill, combat, effect)

    # === Проверяем, нанесен ли урон (мгновенные эффекты) или требуется следующий ход ===
    instant_damage_effects = ["double_shot", "burst_count", "damage_mult", "ignore_defense"]

    if any(eff in effect for eff in instant_damage_effects):
        # Мгновенный урон - обрабатываем ответ врага
        if combat['enemy_hp'] > 0:
            # Враг атакует
            enemy_damage = combat['enemy_damage']
            active_effects = get_active_effects(user_id)

            is_dodged = random.randint(1, 100) <= player.dodge_chance
            if is_dodged:
                result_msg += f"\nТы уклонился от атаки!"
            else:
                total_defense = player.total_defense

                # Применяем эффекты защиты
                if "temp_defense_active" in active_effects:
                    total_defense += active_effects.get("temp_defense", 0)
                if "incoming_damage_reduction" in active_effects:
                    enemy_damage = int(enemy_damage * (1 - active_effects["incoming_damage_reduction"]))
                if "enemy_damage_reduction" in active_effects:
                    enemy_damage = int(enemy_damage * (1 - active_effects["enemy_damage_reduction"]))

                final_damage = max(1, enemy_damage - total_defense)
                player.health -= final_damage
                result_msg += f"\n{combat['enemy_name']} атакует!\nПолучен урон: {final_damage}"

                # Проверка на смерть
                if player.health <= 0:
                    player.health = 0
                    database.update_user_stats(user_id, health=0)
                    del _combat_state[user_id]
                    _handle_death(player, vk, user_id)
                    return

        # Проверяем победу
        if combat['enemy_hp'] <= 0:
            result_msg += _handle_victory(player, combat, user_id)
            vk.messages.send(
                user_id=user_id,
                message=result_msg,
                keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
                random_id=0
            )
            return

        # Обновляем HP в БД
        database.update_user_stats(user_id, health=player.health)

        # Прогресс-бары
        enemy_hp_bar = _create_hp_bar(combat['enemy_hp'], combat['enemy_max_hp'])
        player_hp_bar = _create_hp_bar(player.health, player.max_health)

        result_msg += (
            f"\n\n{combat['enemy_name']}\n"
            f"HP {enemy_hp_bar} {combat['enemy_hp']}/{combat['enemy_max_hp']}\n\n"
            f"Ты\n"
            f"HP {player_hp_bar} {player.health}/{player.max_health}"
        )
    else:
        # Не мгновенный эффект - показываем сообщение и возвращаем в бой
        pass

    # Уменьшаем кулдауны
    _decrease_cooldowns(user_id)

    # Сохраняем состояние боя
    _combat_state[user_id] = combat

    # Показываем результат и клавиатуру боя
    vk.messages.send(
        user_id=user_id,
        message=result_msg,
        keyboard=create_combat_keyboard(player, user_id).get_keyboard(),
        random_id=0
    )


def _apply_skill_effect(player, vk, user_id: int, skill: dict, combat: dict, effect: dict):
    """Применить эффект навыка"""
    from classes import get_class, get_class_by_weapon
    import database

    skill_name = skill["name"]
    message = ""

    # === Двойной выстрел ===
    if "double_shot" in effect:
        second_mult = effect.get("second_damage_mult", 0.7)

        # Первый выстрел
        weapon_damage = 0
        if player.equipped_weapon:
            item = database.get_item_by_name(player.equipped_weapon)
            if item:
                weapon_damage = item.get('attack', 0)

        melee = player.melee_damage
        first_damage = weapon_damage + melee

        # Второй выстрел
        second_damage = int(first_damage * second_mult)

        total_damage = first_damage + second_damage
        combat['enemy_hp'] -= total_damage

        message = f"🎯{skill_name}\n\n"
        message += f"Первый выстрел: {first_damage} урона\n"
        message += f"Второй выстрел: {second_damage} урона ({int(second_mult*100)}%)\n"
        message += f"<b>Всего: {total_damage} урона\n\n"

    # === Точный выстрел (damage_boost) ===
    elif "damage_boost" in effect:
        mult = effect.get("damage_boost", 1.5)

        if user_id not in _active_skill_effects:
            _active_skill_effects[user_id] = {}
        _active_skill_effects[user_id]["damage_boost"] = 1  # 1 ход

        message = f"🎯{skill_name}\n\n"
        message += f"Прицел взят! Следующая атака нанесет {int((mult-1)*100)}% бонусного урона.\n\n"
        message += "Используй 'Атаковать' для нанесения удара!\n\n"

    # === Очередь (burst) ===
    elif "burst_count" in effect:
        burst_count = effect.get("burst_count", 3)
        burst_damage = effect.get("burst_damage", 0.4)

        weapon_damage = 0
        if player.equipped_weapon:
            item = database.get_item_by_name(player.equipped_weapon)
            if item:
                weapon_damage = item.get('attack', 0)

        melee = player.melee_damage
        base_damage = weapon_damage + melee
        per_shot = int(base_damage * burst_damage)
        total_damage = per_shot * burst_count

        combat['enemy_hp'] -= total_damage

        message = f"🔥{skill_name}\n\n"
        message += f"Очередь из {burst_count} выстрелов:\n"
        for i in range(burst_count):
            message += f"  Выстрел {i+1}: {per_shot} урона\n"
        message += f"<b>Всего: {total_damage} урона\n\n"

    # === Подавление ===
    elif "enemy_damage_reduction" in effect:
        reduction = effect.get("enemy_damage_reduction", 0.25)

        if user_id not in _active_skill_effects:
            _active_skill_effects[user_id] = {}
        _active_skill_effects[user_id]["enemy_damage_reduction"] = 1

        message = f"🛡️{skill_name}\n\n"
        message += f"Враг подавлен! Его атаки наносят на {int(reduction*100)}% меньше урона.\n\n"

    # === Прицельный выстрел ===
    elif "damage_mult" in effect:
        mult = effect.get("damage_mult", 2.5)
        cannot_dodge = effect.get("cannot_dodge", False)

        weapon_damage = 0
        if player.equipped_weapon:
            item = database.get_item_by_name(player.equipped_weapon)
            if item:
                weapon_damage = item.get('attack', 0)

        melee = player.melee_damage
        base_damage = weapon_damage + melee
        total_damage = int(base_damage * mult)

        combat['enemy_hp'] -= total_damage

        message = f"🎯{skill_name}\n\n"
        message += f"Мощный прицельный выстрел!\n"
        message += f"База: {base_damage} x {mult} = {total_damage} урона\n"
        if cannot_dodge:
            message += "Враг не может уклониться!\n"
        message += "\n"

    # === Незримый ===
    elif "incoming_damage_reduction" in effect:
        reduction = effect.get("incoming_damage_reduction", 0.5)

        if user_id not in _active_skill_effects:
            _active_skill_effects[user_id] = {}
        _active_skill_effects[user_id]["incoming_damage_reduction"] = 1

        message = f"👻{skill_name}\n\n"
        message += f"Ты стал невидимым! Следующий урон врага уменьшен на {int(reduction*100)}%.\n\n"

    # === Шквал огня ===
    elif "burst_count" in effect:  # Уже обработано выше, но для пулемётчика
        burst_count = effect.get("burst_count", 5)
        burst_damage = effect.get("burst_damage", 0.3)

        weapon_damage = 0
        if player.equipped_weapon:
            item = database.get_item_by_name(player.equipped_weapon)
            if item:
                weapon_damage = item.get('attack', 0)

        melee = player.melee_damage
        base_damage = weapon_damage + melee
        per_shot = int(base_damage * burst_damage)
        total_damage = per_shot * burst_count

        combat['enemy_hp'] -= total_damage

        message = f"💥{skill_name}\n\n"
        message += f"Шквал из {burst_count} выстрелов:\n"
        for i in range(burst_count):
            message += f"  Выстрел {i+1}: {per_shot} урона\n"
        message += f"<b>Всего: {total_damage} урона\n\n"

    # === Бронирование ===
    elif "temp_defense" in effect:
        defense = effect.get("temp_defense", 25)

        if user_id not in _active_skill_effects:
            _active_skill_effects[user_id] = {}
        _active_skill_effects[user_id]["temp_defense"] = defense
        _active_skill_effects[user_id]["temp_defense_active"] = 1

        message = f"🛡️{skill_name}\n\n"
        message += f"Бронирование активировано! +{defense} защиты на 1 ход.\n\n"

    # === Клинок в сердце ===
    elif "ignore_defense" in effect:
        ignore_def = effect.get("ignore_defense", 20)

        weapon_damage = 0
        if player.equipped_weapon:
            item = database.get_item_by_name(player.equipped_weapon)
            if item:
                weapon_damage = item.get('attack', 0)

        melee = player.melee_damage
        base_damage = weapon_damage + melee
        total_damage = int(base_damage * 1.5)  # 150% урона

        combat['enemy_hp'] -= total_damage

        message = f"🗡️{skill_name}\n\n"
        message += f"Точный удар в уязвимое место!\n"
        message += f"Урон: {total_damage} (150%)\n"
        message += f"Игнорирование защиты: {ignore_def}%\n\n"

    # === Уклонение (perfect_dodge) ===
    elif "perfect_dodge" in effect:
        if user_id not in _active_skill_effects:
            _active_skill_effects[user_id] = {}
        _active_skill_effects[user_id]["perfect_dodge"] = 1

        message = f"💨{skill_name}\n\n"
        message += "Ты готов уклониться от следующей атаки!\n\n"

    # === Заградительный огонь ===
    elif "aoe_damage_reduction" in effect:
        reduction = effect.get("aoe_damage_reduction", 0.15)

        if user_id not in _active_skill_effects:
            _active_skill_effects[user_id] = {}
        _active_skill_effects[user_id]["aoe_damage_reduction"] = reduction

        message = f"🔥{skill_name}\n\n"
        message += f"Заградительный огонь! Все враги поблизости наносят на {int(reduction*100)}% меньше урона.\n\n"

    else:
        message = f"⚡{skill_name}\n\nНавык активирован!\n\n"

    return message


def _decrease_cooldowns(user_id: int):
    """Уменьшить кулдауны навыков после хода"""
    if user_id not in _skill_cooldowns:
        return

    for skill_name in list(_skill_cooldowns[user_id].keys()):
        _skill_cooldowns[user_id][skill_name] -= 1
        if _skill_cooldowns[user_id][skill_name] <= 0:
            del _skill_cooldowns[user_id][skill_name]

    # Уменьшаем активные эффекты
    if user_id in _active_skill_effects:
        for effect_name in list(_active_skill_effects[user_id].keys()):
            if isinstance(_active_skill_effects[user_id][effect_name], int):
                _active_skill_effects[user_id][effect_name] -= 1
                if _active_skill_effects[user_id][effect_name] <= 0:
                    del _active_skill_effects[user_id][effect_name]


def get_active_effects(user_id: int) -> dict:
    """Получить активные эффекты игрока"""
    return _active_skill_effects.get(user_id, {})


def handle_combat_attack(player, vk, user_id: int):
    """Атаковать врага"""
    _combat_state, create_location_keyboard, _, _ = _get_main_imports()

    combat = _combat_state.get(user_id)
    if not combat:
        return
    
    # === Проверяем активные эффекты ===
    active_effects = get_active_effects(user_id)

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
    
    # === Применяем эффекты навыков ===
    skill_message = ""

    # Damage boost (Точный выстрел)
    if "damage_boost" in active_effects:
        total_damage = int(total_damage * 1.5)  # +50%
        skill_message += "🎯 Точный выстрел! +50% урона!\n"
        del _active_skill_effects[user_id]["damage_boost"]

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

    # Добавляем информацию о характеристиках
    crit_chance = player.crit_chance
    dodge_chance = player.dodge_chance
    total_defense = player.total_defense

    message = f"⚔️ТЫ АТАКУЕШЬ {combat['enemy_name'].upper()}\n\n"
    message += f"🎯 Шанс крита: {crit_chance}% | 💨 Уклонение: {dodge_chance}%\n"
    message += f"🛡️ Твоя защита: {total_defense}\n"

    if is_crit:
        message += f"\n🔥КРИТИЧЕСКИЙ УДАР! x1.5\n"
    message += f"Нанесён урон:{total_damage}\n"
    message += f"({(' | '.join(damage_details))})\n"

    # Сообщение о кровотечении
    if bleed_applied:
        message += f"\n🩸КРОВОТЕЧЕНИЕ! Враг истекает кровью!\n"
    if bleed_damage > 0:
        message += f"🩸 Кровотечение наносит {bleed_damage} урона!\n"

    # Определяем какую клавиатуру показывать
    keyboard = None

    if combat['enemy_hp'] <= 0:
        message += _handle_victory(player, combat, user_id)
        keyboard = create_location_keyboard(player.current_location_id)
    else:
        enemy_damage = combat['enemy_damage']
        
        # === Проверяем perfect_dodge (навык Уклонение) ===
        if "perfect_dodge" in active_effects:
            message += "\n💨УКЛОНЕНИЕ! (навык Уклонение)\n"
            del _active_skill_effects[user_id]["perfect_dodge"]
        else:
            is_dodged = random.randint(1, 100) <= player.dodge_chance
            if is_dodged:
                message += f"\n💨УКЛОНЕНИЕ! (шанс: {player.dodge_chance}%)\n"
            else:
                total_defense = player.total_defense

                # === Применяем temp_defense (Бронирование) ===
                if "temp_defense_active" in active_effects:
                    temp_def = active_effects.get("temp_defense", 0)
                    total_defense += temp_def
                    message += f"🛡️БРОНИРОВАНИЕ: +{temp_def} защиты!\n"

                # === Применяем incoming_damage_reduction (Незримый) ===
                if "incoming_damage_reduction" in active_effects:
                    reduction = active_effects["incoming_damage_reduction"]
                    enemy_damage = int(enemy_damage * (1 - reduction))
                    message += f"👻НЕЗРИМЫЙ: урон уменьшен на {int(reduction*100)}%!\n"
                    del _active_skill_effects[user_id]["incoming_damage_reduction"]

                # === Применяем enemy_damage_reduction (Подавление) ===
                if "enemy_damage_reduction" in active_effects:
                    reduction = active_effects["enemy_damage_reduction"]
                    enemy_damage = int(enemy_damage * (1 - reduction))
                    message += f"🔥ПОДАВЛЕНИЕ: враг ослаблен на {int(reduction*100)}%!\n"
                    del _active_skill_effects[user_id]["enemy_damage_reduction"]

                final_damage = max(1, enemy_damage - total_defense)
                player.health -= final_damage
                message += f"\n⚔️{combat['enemy_name']} АТАКУЕТ!\n"
                message += f"Урон врага: {enemy_damage} → Получено:{final_damage} (защита: {total_defense})\n"

            # Проверка на смерть
            if player.health <= 0:
                player.health = 0
                database.update_user_stats(user_id, health=0)
                del _combat_state[user_id]
                _handle_death(player, vk, user_id)
                return

            database.update_user_stats(user_id, health=player.health)

        # Показываем состояние кровотечения
        if combat.get('bleed_turns', 0) > 0:
            message += f"\n🩸 Кровотечение врага: {combat['bleed_turns']} ходов"

        # Прогресс-бары HP + энергия
        enemy_hp_bar = _create_hp_bar(combat['enemy_hp'], combat['enemy_max_hp'])
        player_hp_bar = _create_hp_bar(player.health, player.max_health)

        message += (
            f"\n\n╔════════════════════════════════╗\n"
            f"║СТАТУС БОЯ\n"
            f"╠════════════════════════════════╣\n"
            f"║ {combat['enemy_name']}\n"
            f"║ HP {enemy_hp_bar} {combat['enemy_hp']}/{combat['enemy_max_hp']}\n"
            f"╠════════════════════════════════╣\n"
            f"║ТЫ\n"
            f"║ ❤️ HP {player_hp_bar} {player.health}/{player.max_health}\n"
            f"║ ⚡ Энергия: {player.energy}/100\n"
            f"║ 🛡️ Защита: {player.total_defense}\n"
            f"╚════════════════════════════════╝"
        )

        # Уменьшаем кулдауны после хода
        _decrease_cooldowns(user_id)

        # Показываем активные эффекты
        active_effects = get_active_effects(user_id)
        if active_effects:
            effects_msg = "\n🔮АКТИВНЫЕ ЭФФЕКТЫ:\n"
            for eff_name, eff_val in active_effects.items():
                if isinstance(eff_val, int) and eff_val > 0:
                    effects_msg += f"• {eff_name}: {eff_val} ход\n"
            message += effects_msg

        # Показываем кулдауны навыков
        cooldowns = _skill_cooldowns.get(user_id, {})
        if cooldowns:
            cd_msg = "\n⏳ПЕРЕЗАРЯДКА НАВЫКОВ:\n"
            for skill_name, cd_val in cooldowns.items():
                cd_msg += f"• {skill_name}: {cd_val} ход\n"
            message += cd_msg

        # Сохраняем состояние боя и показываем клавиатуру боя
        _combat_state[user_id] = combat
        keyboard = create_combat_keyboard(player, user_id)

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
    from handlers.quests import track_quest_kill, track_quest_shells

    del _combat_state[user_id]
    
    experience = random.randint(10, 30)
    money = random.randint(5, 25)
    shells_drop = random.randint(1, 3)  # 1-3 гильзы с врага

    player.experience += experience
    player.money += money
    
    # Добавляем гильзы с учетом вместимости мешочка
    shells_info = database.get_shells_info(user_id)
    shells_before = database.get_user_shells(user_id)
    success, msg = database.add_shells(user_id, shells_drop)
    current_shells = database.get_user_shells(user_id)
    capacity = shells_info['capacity']

    # Автопрогресс daily-заданий: убийства и собранные гильзы.
    track_quest_kill(user_id, combat.get("location_id"))
    added_shells = max(0, int(current_shells or 0) - int(shells_before or 0))
    if added_shells > 0:
        track_quest_shells(user_id, count=added_shells)

    database.update_user_stats(user_id, experience=player.experience, money=player.money)
    
    level_up = player._check_level_up()
    
    player_hp_bar = _create_hp_bar(player.health, player.max_health)

    message = (
        f"ПОБЕДА!\n\n"
        f"Ты победил {combat['enemy_name']}!\n\n"
        f"Награда: {money} руб.\n"
        f"Опыт: +{experience}\n"
        f"Гильзы: {current_shells}/{capacity}\n"
    )

    if not success:
        message += f"⚠️ Мешочек переполнен! {msg}\n"

    message += f"\nТы\nHP {player_hp_bar} {player.health}/{player.max_health}\n"

    if level_up:
        message += f"\n{level_up}"
    
    return message
