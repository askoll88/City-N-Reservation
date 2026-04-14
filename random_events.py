"""
Случайные события в Зоне
Лор S.T.A.L.K.E.R. - Зона живёт своей жизнью и непредсказуема.

События触发атся при перемещении между локациями.
"""
import random


# === Пул случайных событий ===
# Каждое событие: {id, text, type, effect, chance_weight}
# type: "danger", "reward", "neutral", "story"

RANDOM_EVENTS = [
    # --- Выброс ---
    {
        "id": "emission_warning",
        "text": (
            "⚠️ ВНИМАНИЕ! Выброс приближается!\n\n"
            "Небо темнеет, земля дрожит. Зона готовится к выбросу.\n"
            "У тебя есть выбор:\n"
        ),
        "type": "danger",
        "choices": [
            {
                "label": "Спрятаться (потерять 10 энергии)",
                "effect": {"energy": -10, "message": "Ты спрятался в укрытии. Выброс прошёл мимо. Ты потерял силы, но жив."},
            },
            {
                "label": "Игнорировать (риск)",
                "effect": {"risk_damage": True, "message_ok": "Тебе повезло! Выброс прошёл, ты отделался лёгким испугом.", "message_fail": "Выброс застал тебя врасплох! -20 HP, -15 энергии."},
            },
        ],
        "chance_weight": 15,
    },

    # --- Тайник ---
    {
        "id": "stash_find",
        "text": (
            "💰 Ты заметил странную метку на стене - сталкерский тайник!\n\n"
            "Кто-то оставил припасы. Забрать?"
        ),
        "type": "reward",
        "choices": [
            {
                "label": "Забрать тайник",
                "effect": {"random_loot": True, "message": "Ты нашёл припасы! +{money} руб., +{item}"},
            },
            {
                "label": "Не трогать",
                "effect": {"message": "Ты решил не лезть. В Зоне жадность до добра не доводит."},
            },
        ],
        "chance_weight": 20,
    },

    # --- Встреча со сталкером ---
    {
        "id": "stalker_encounter",
        "text": (
            "🤝 На дороге ты встречаешь сталкера. Он выглядит уставшим.\n\n"
            "\"Здарова, брат. Иду с задания. Есть разговор.\" "
        ),
        "type": "neutral",
        "choices": [
            {
                "label": "Поговорить",
                "effect": {"random_dialog": True, "message": "Сталкер рассказал интересное о Зоне. +30 XP"},
            },
            {
                "label": "Пройти мимо",
                "effect": {"message": "Ты кивнул и пошёл дальше. Не до разговоров."},
            },
            {
                "label": "Обыскать (риск!)",
                "effect": {"risk_combat": True, "message_ok": "Сталкер оказался слабым. Ты забрал его вещи. +{money} руб.", "message_fail": "Сталкер оказался бойцом! Ты получил -15 HP."},
            },
        ],
        "chance_weight": 25,
    },

    # --- Аномальная буря ---
    {
        "id": "anomaly_storm",
        "text": (
            "🌩️ Аномальная буря! Ветер несёт обломки, аномалии вспыхивают одна за другой.\n\n"
            "Но в буре можно найти редкие артефакты..."
        ),
        "type": "danger",
        "choices": [
            {
                "label": "Искать артефакты (риск!)",
                "effect": {"artifact_chance": True, "message_ok": "Буря выбросила редкий артефакт! Ты нашёл {artifact}!", "message_fail": "Буря слишком сильна! -25 HP."},
            },
            {
                "label": "Переждать",
                "effect": {"message": "Ты переждал бурю в укрытии. Мудрое решение."},
            },
        ],
        "chance_weight": 10,
    },

    # --- Радиоперехват ---
    {
        "id": "radio_intercept",
        "text": (
            "📻 Рация шипит... Ты перехватываешь сообщение:\n\n"
            "\"...координаты тайника... сектор Б-7... повторяю...\""
        ),
        "type": "reward",
        "choices": [
            {
                "label": "Записать координаты",
                "effect": {"xp": 50, "money": 100, "message": "Ты записал координаты. Возможно, стоит проверить сектор Б-7. +50 XP, +100 руб."},
            },
            {
                "label": "Игнорировать",
                "effect": {"message": "Мало ли что ловит рация. Ты продолжил путь."},
            },
        ],
        "chance_weight": 15,
    },

    # --- Раненый сталкер ---
    {
        "id": "wounded_stalker",
        "text": (
            "🚑 У дороги лежит раненый сталкер. Он тяжело дышит.\n\n"
            "\"Помоги... мутант... напал...\" "
        ),
        "type": "neutral",
        "choices": [
            {
                "label": "Дать аптечку",
                "effect": {"need_item": "Аптечка", "xp": 100, "reputation": 10, "message": "Ты перевязал сталкера. Он благодарно кивнул: \"Спасибо, брат. Не забуду.\" +100 XP"},
            },
            {
                "label": "Пройти мимо",
                "effect": {"message": "Ты не можешь помочь всем. Сталкер молча смотрит тебе вслед."},
            },
        ],
        "chance_weight": 12,
    },

    # --- Мутант-одиночка ---
    {
        "id": "lone_mutant",
        "text": (
            "🐺 Из кустов выскочил мутировавший пёс! Он ранен, но агрессивен.\n"
        ),
        "type": "danger",
        "choices": [
            {
                "label": "Убить",
                "effect": {"xp": 40, "money": 30, "shells": 2, "message": "Ты убил мутанта. +40 XP, +30 руб., +2 гильзы."},
            },
            {
                "label": "Обойти",
                "effect": {"message": "Ты обошёл мутанта стороной. Не стоит тратить патроны."},
            },
        ],
        "chance_weight": 20,
    },

    # --- Странный артефакт ---
    {
        "id": "weird_artifact",
        "text": (
            "✨ Ты нашёл странный артефакт. Он пульсирует и светится.\n\n"
            "Взять его или оставить?"
        ),
        "type": "reward",
        "choices": [
            {
                "label": "Взять",
                "effect": {"random_artifact": True, "message": "Ты взял артефакт. Он тёплый на ощупь. +1 артефакт!"},
            },
            {
                "label": "Оставить",
                "effect": {"message": "Ты решил не рисковать. Зона полна ловушек."},
            },
        ],
        "chance_weight": 8,
    },

    # --- Военный патруль ---
    {
        "id": "military_patrol",
        "text": (
            "🎖️ Ты заметил военный патруль. Они проверяют документы.\n\n"
            "\"Стой! Пропуск есть?\""
        ),
        "type": "neutral",
        "choices": [
            {
                "label": "Показать документы",
                "effect": {"money_loss": 50, "message": "Патруль проверил документы и отпустил. Но \"случайно\" забрал 50 руб. на \"проверку\"."},
            },
            {
                "label": "Убежать",
                "effect": {"risk_combat": True, "message_ok": "Ты успешно скрылся. Патруль не догнал.", "message_fail": "Патруль открыл огонь! -30 HP."},
            },
        ],
        "chance_weight": 10,
    },

    # --- Торговец-одиночка ---
    {
        "id": "wandering_trader",
        "text": (
            "🧳 На дороге стоит торговец с тележкой. \"Эй, сталкер! Есть товар.\"\n"
        ),
        "type": "reward",
        "choices": [
            {
                "label": "Посмотреть товар",
                "effect": {"shop_discount": True, "message": "Торговец предложил скидку 20% на одну покупку. +100 XP"},
            },
            {
                "label": "Пройти мимо",
                "effect": {"message": "Ты не стал тратить время. Товар у торговца, скорее, краденый."},
            },
        ],
        "chance_weight": 12,
    },
]


def get_random_event() -> dict | None:
    """
    Получить случайное событие.
    Возвращает None, если событие не触发лось.
    Шанс любого события ~25% при каждом вызове.
    """
    if random.randint(1, 100) > 25:
        return None

    # Взвешенный выбор
    weights = [e["chance_weight"] for e in RANDOM_EVENTS]
    return random.choices(RANDOM_EVENTS, weights=weights, k=1)[0]


def format_event_message(event: dict) -> str:
    """Форматировать событие для отображения"""
    msg = f"{event['text']}\n\n"
    msg += "Выбери действие:\n"
    for i, choice in enumerate(event["choices"], 1):
        msg += f"{i}. {choice['label']}\n"
    return msg


def apply_event_choice(event: dict, choice_index: int, player) -> str:
    """
    Применить выбор игрока к событию.
    Возвращает текст результата.
    """
    if choice_index < 0 or choice_index >= len(event["choices"]):
        return "Неверный выбор."

    choice = event["choices"][choice_index]
    effect = choice["effect"]

    # Простое сообщение
    if "message" in effect and not any(k in effect for k in ["risk_damage", "risk_combat", "random_loot", "artifact_chance", "random_artifact", "random_dialog", "need_item", "shop_discount", "money_loss"]):
        if "xp" in effect:
            player.experience += effect["xp"]
        if "money" in effect:
            player.money += effect["money"]
        if "energy" in effect:
            player.energy = max(0, player.energy + effect["energy"])
        if "shells" in effect:
            player.shells = getattr(player, 'shells', 0) + effect["shells"]
        return effect["message"]

    # Риск - получение урона
    if effect.get("risk_damage"):
        if random.randint(1, 100) <= 40:
            player.health = max(1, player.health - 20)
            player.energy = max(0, player.energy - 15)
            return effect.get("message_fail", "Тебе не повезло!")
        else:
            return effect.get("message_ok", "Тебе повезло!")

    # Риск - бой
    if effect.get("risk_combat"):
        if random.randint(1, 100) <= 60:
            if "money" in effect:
                player.money += effect.get("money", 0)
            return effect.get("message_ok", "Всё прошло успешно!")
        else:
            player.health = max(1, player.health - 30)
            return effect.get("message_fail", "Что-то пошло не так!")

    # Случайный лут
    if effect.get("random_loot"):
        import database
        money_reward = random.randint(50, 300)
        player.money += money_reward
        # Шанс найти предмет
        item_msg = "ничего"
        if random.randint(1, 100) <= 40:
            common_items = [("Бинт", 2), ("Аптечка", 1), ("Гильзы", 10), ("Хлеб", 1), ("Вода", 1)]
            item_name, qty = random.choice(common_items)
            database.add_item_to_inventory(player.user_id, item_name, qty)
            item_msg = f"{item_name} x{qty}"
        return effect["message"].format(money=money_reward, item=item_msg)

    # Шанс артефакта
    if effect.get("artifact_chance"):
        if random.randint(1, 100) <= 30:
            from anomalies import get_random_anomaly, get_artifact_from_anomaly
            anomaly = get_random_anomaly()
            artifact = get_artifact_from_anomaly(anomaly["type"])
            return effect["message_ok"].format(artifact=artifact or "странный артефакт")
        else:
            player.health = max(1, player.health - 25)
            return effect.get("message_fail", "Буря слишком сильна!")

    # Случайный артефакт
    if effect.get("random_artifact"):
        from anomalies import get_artifact_from_anomaly
        import database
        anomaly_type = random.choice(["жарка", "электра", "воронка", "туман", "магнит"])
        artifact = get_artifact_from_anomaly(anomaly_type)
        if artifact:
            database.add_item_to_inventory(player.user_id, artifact, 1)
            return effect["message"]
        return "Артефакт рассыпался в руках..."

    # Нужен предмет
    if effect.get("need_item"):
        item_name = effect["need_item"]
        player.inventory.reload()
        has_item = any(
            item["name"].lower() == item_name.lower()
            for cat in [player.inventory.other, player.inventory.artifacts]
            for item in cat
        )
        if has_item:
            # Удаляем предмет
            import database
            database.remove_item_from_inventory(player.user_id, item_name, 1)
            player.experience += effect.get("xp", 0)
            return effect["message"]
        else:
            return f"У тебя нет {item_name}. Ты не можешь помочь."

    # Скидка
    if effect.get("shop_discount"):
        player.experience += effect.get("xp", 0)
        return effect["message"]

    # Потеря денег
    if effect.get("money_loss"):
        loss = effect["money_loss"]
        player.money = max(0, player.money - loss)
        return effect["message"]

    # XP + money
    if "xp" in effect:
        player.experience += effect["xp"]
    if "money" in effect:
        player.money += effect["money"]
    if "energy" in effect:
        player.energy = max(0, player.energy + effect["energy"])

    return effect.get("message", "Ничего не произошло.")
