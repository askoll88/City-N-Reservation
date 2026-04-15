"""
Классы игрока и инвентаря
"""
import database
import logging
from locations import get_location, Location
import ui

logger = logging.getLogger(__name__)


RADIATION_RPH_PER_POINT = 0.2


def radiation_points_to_rph(radiation: int) -> float:
    """Перевести внутренние очки радиации в эквивалент мощности дозы (Р/ч)."""
    rad = max(0, int(radiation or 0))
    return rad * RADIATION_RPH_PER_POINT


def format_radiation_rate(radiation: int) -> str:
    """Строка мощности дозы в Р/ч."""
    rate = radiation_points_to_rph(radiation)
    if rate < 10:
        return f"{rate:.2f} Р/ч"
    return f"{rate:.1f} Р/ч"


def get_radiation_stage(radiation: int) -> dict:
    """
    Игровая шкала стадий, вдохновлённая реальной лучевой болезнью.
    Привязка по внутренним очкам, но в UI показываем эквивалент Р/ч.
    """
    rad = max(0, int(radiation or 0))
    if rad < 30:
        return {"name": "I. Фоновый уровень", "note": "Клинических симптомов нет"}
    if rad < 80:
        return {"name": "II. Лёгкое облучение", "note": "Риск ранних симптомов"}
    if rad < 120:
        return {"name": "III. Ранняя лучевая реакция", "note": "Слабость, тошнота, падение выносливости"}
    if rad < 170:
        return {"name": "IV. Средняя лучевая болезнь", "note": "Стабильный вред без лечения"}
    if rad < 220:
        return {"name": "V. Тяжёлая лучевая болезнь", "note": "Высокий риск отказа организма"}
    if rad < 250:
        return {"name": "VI. Критическое состояние", "note": "Нужен антирад немедленно"}
    return {"name": "VII. Терминальная стадия", "note": "Почти неизбежная смерть без срочной помощи"}


def format_radiation_state(radiation: int) -> str:
    """Краткий формат радиации: очки, Р/ч и стадия."""
    stage = get_radiation_stage(radiation)
    return f"{int(max(0, radiation or 0))} ед. ({format_radiation_rate(radiation)}) • {stage['name']}"


def calculate_radiation_hp_loss(radiation: int, current_hp: int) -> int:
    """
    Тик-урон от накопленной радиации.
    До ~100 растёт плавно, после 150 ускоряется, а на 250+ почти смертелен.
    """
    rad = max(0, int(radiation or 0))
    hp = max(1, int(current_hp or 1))

    if rad < 30:
        return 0
    if rad < 80:
        return 1 + (rad - 30) // 25          # 1..2
    if rad < 120:
        return 3 + (rad - 80) // 15          # 3..5
    if rad < 170:
        return 6 + (rad - 120) // 10         # 6..10
    if rad < 220:
        return 11 + (rad - 170) // 6         # 11..19
    if rad < 250:
        return 20 + (rad - 220) // 2         # 20..34

    # 250+ — почти мгновенная смерть, но не всегда 100%.
    return max(35, int(hp * 0.85))


class Inventory:
    """Класс инвентаря игрока"""

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.reload()

    def reload(self):
        """Перезагрузить данные инвентаря из БД"""
        items = database.get_user_inventory(self.user_id)

        self.weapons = []
        self.armor = []
        self.backpacks = []
        self.artifacts = []
        self.shells_bags = []
        self.other = []

        for item in items:
            category = item.get('category', 'other')
            if category == 'weapons':
                self.weapons.append(item)
            elif category == 'armor':
                self.armor.append(item)
            elif category == 'backpacks':
                self.backpacks.append(item)
            elif category == 'artifacts':
                self.artifacts.append(item)
            elif category == 'shells_bag':
                self.shells_bags.append(item)
            else:
                self.other.append(item)

    @property
    def total_weight(self) -> float:
        """Общий вес инвентаря"""
        total = 0.0
        for item in (self.weapons + self.armor + self.backpacks +
                     self.artifacts + self.other):
            total += item.get('weight', 1.0) * item.get('quantity', 1)
        return round(total, 1)

    def is_empty(self) -> bool:
        """Проверить, пуст ли инвентарь"""
        return not (self.weapons or self.armor or self.artifacts or
                    self.backpacks or self.other)

    def __str__(self) -> str:
        """Строковое представление инвентаря"""
        lines = []

        if self.weapons:
            lines.append("Оружие:\n" + "\n".join(
                f"- {item['name']} x{item['quantity']} УРН:{item.get('attack', 0)} ВЕС:{item.get('weight', 1.0)}кг"
                for item in self.weapons
            ))
        else:
            lines.append("Оружие:\n  Пусто")

        if self.armor:
            lines.append("Броня:\n" + "\n".join(
                f"- {item['name']} x{item['quantity']} ЗАЩ:{item.get('defense', 0)} ВЕС:{item.get('weight', 1.0)}кг"
                for item in self.armor
            ))
        else:
            lines.append("Броня:\n  Пусто")

        if self.backpacks:
            lines.append("Рюкзаки:\n" + "\n".join(
                f"- {item['name']} x{item['quantity']} +{item.get('backpack_bonus', 0)}кг ВЕС:{item.get('weight', 1.0)}кг"
                for item in self.backpacks
            ))
        else:
            lines.append("Рюкзаки:\n  Пусто")

        if self.artifacts:
            lines.append("Артефакты:\n" + "\n".join(
                f"- {item['name']} x{item['quantity']} ВЕС:{item.get('weight', 1.0)}кг"
                for item in self.artifacts
            ))
        else:
            lines.append("Артефакты:\n  Пусто")

        if self.other:
            lines.append("Другое:\n" + "\n".join(
                f"{idx}. {item['name']} x{item['quantity']} ВЕС:{item.get('weight', 1.0)}кг"
                for idx, item in enumerate(self.other, 1)
            ))
            lines.append("\nНажми цифру чтобы использовать предмет")
        else:
            lines.append("Другое:\n  Пусто")

        return "\n\n".join(lines)


class Player:
    """Класс игрока (загружается из БД)"""

    # Опыт для каждого уровня
    LEVELS = {
        1: 0, 2: 100, 3: 250, 4: 450, 5: 700,
        6: 1000, 7: 1400, 8: 1900, 9: 2500, 10: 3200,
        11: 4000, 12: 5000, 13: 6200, 14: 7600, 15: 9200,
        16: 11000, 17: 13000, 18: 15500, 19: 18500, 20: 22000
    }

    def __init__(self, user_id: int):
        self.user_id = user_id
        self._data = database.get_user_by_vk(user_id)

        if not self._data:
            # Создаём нового пользователя
            self._data = database.create_user(user_id, f"Сталкер_{user_id}")

        self.name = self._data['name']
        self.current_location_id = self._data['location']

        # Базовые параметры
        self.health = self._data['health']
        self.energy = self._data['energy']
        self.radiation = self._data['radiation']
        self.money = self._data['money']

        # RPG параметры
        self.level = self._data['level']
        self.experience = self._data['experience']
        self.strength = self._data['strength']       # Сила - урон в ближнем бою, переносимый вес
        self.stamina = self._data['stamina']         # Выносливость - скорость восстановления энергии
        self.perception = self._data['perception']   # Восприятие - шанс найти артефакты
        self.luck = self._data['luck']               # Удача - криты, редкие находки
        self.armor_defense = self._data['armor_defense']  # Защита брони
        self.equipped_backpack = self._data.get('equipped_backpack')  # Надетый рюкзак
        self.equipped_weapon = self._data.get('equipped_weapon')  # Надетое оружие
        self.equipped_armor = self._data.get('equipped_armor')  # Надетая броня (старый формат)
        self.equipped_device = self._data.get('equipped_device')  # Экипированное устройство (детектор)
        self.newbie_kit_received = self._data.get('newbie_kit_received', 0)  # Получил набор новичка
        self.max_weight = self._data['max_weight']   # Максимальный переносимый вес
        self.artifact_slots = self._data.get('artifact_slots', 3)  # Слоты для артефактов
        self.max_health_bonus = self._data.get('max_health_bonus', 0)  # Бонус к HP от артефактов
        self.hp_upgrade_level = int(self._data.get('hp_upgrade_level', 0) or 0)
        self.inventory_section = self._data.get('inventory_section')  # Текущий раздел инвентаря
        self.previous_location = self._data.get('previous_location')  # Предыдущая локация для возврата
        self.player_class = self._data.get('player_class')  # Класс персонажа
        self.is_admin = self._data.get('is_admin', 0)
        self.is_banned = self._data.get('is_banned', 0)
        self.ban_reason = self._data.get('ban_reason')

        # Слоты брони (новый формат)
        self.equipped_armor_head = self._data.get('equipped_armor_head')
        self.equipped_armor_body = self._data.get('equipped_armor_body')
        self.equipped_armor_legs = self._data.get('equipped_armor_legs')
        self.equipped_armor_hands = self._data.get('equipped_armor_hands')
        self.equipped_armor_feet = self._data.get('equipped_armor_feet')

        # Экипированные артефакты
        self.equipped_artifact_1 = self._data.get('equipped_artifact_1')
        self.equipped_artifact_2 = self._data.get('equipped_artifact_2')
        self.equipped_artifact_3 = self._data.get('equipped_artifact_3')

        # Загружаем бонусы от артефактов
        self._artifact_bonuses = self._get_artifact_bonuses()
        self.max_health_bonus = self._artifact_bonuses.get('max_health_bonus', 0)

        # Инициализируем инвентарь
        self.inventory = Inventory(user_id)

        # Пересчитываем переносимый вес сразу с учетом всех источников.
        self._recalculate_max_weight()

    def _get_artifact_bonuses(self) -> dict:
        """Получить бонусы от экипированных артефактов"""
        bonuses = database.get_artifact_bonuses(self.user_id)
        return bonuses

    def _recalculate_max_weight(self):
        """Пересчитать переносимый вес с учетом силы, пассивок, артефактов и рюкзака."""
        passive = self._get_passive_bonuses()
        passive_weight_bonus = int(passive.get('max_weight', 0) or 0)
        artifact_weight_bonus = int(self._artifact_bonuses.get('max_weight', 0) or 0)
        base_max_weight = 20 + self.effective_strength * 2 + passive_weight_bonus + artifact_weight_bonus

        backpack_bonus = 0
        if self.equipped_backpack:
            backpack = next((b for b in self.inventory.backpacks if b['name'] == self.equipped_backpack), None)
            if backpack:
                backpack_bonus = int(backpack.get('backpack_bonus', 0) or 0)

        self.max_weight = max(10, base_max_weight + backpack_bonus)

    # === Вычисляемые характеристики ===

    def reload(self):
        """Перезагрузить данные из БД"""
        self._data = database.get_user_by_vk(self.user_id)
        if self._data:
            self.current_location_id = self._data['location']
            self.health = self._data['health']
            self.energy = self._data['energy']
            self.radiation = self._data['radiation']
            self.money = self._data['money']
            self.level = self._data['level']
            self.experience = self._data['experience']
            self.strength = self._data['strength']
            self.stamina = self._data['stamina']
            self.perception = self._data['perception']
            self.luck = self._data['luck']
            self.armor_defense = self._data['armor_defense']
            self.equipped_backpack = self._data.get('equipped_backpack')
            self.equipped_weapon = self._data.get('equipped_weapon')
            self.equipped_armor = self._data.get('equipped_armor')
            self.equipped_device = self._data.get('equipped_device')
            self.newbie_kit_received = self._data.get('newbie_kit_received', 0)
            self.hp_upgrade_level = int(self._data.get('hp_upgrade_level', 0) or 0)
            self.inventory_section = self._data.get('inventory_section')
            self.previous_location = self._data.get('previous_location')
            self.is_admin = self._data.get('is_admin', 0)
            self.is_banned = self._data.get('is_banned', 0)
            self.ban_reason = self._data.get('ban_reason')
            # Слоты брони (новый формат)
            self.equipped_armor_head = self._data.get('equipped_armor_head')
            self.equipped_armor_body = self._data.get('equipped_armor_body')
            self.equipped_armor_legs = self._data.get('equipped_armor_legs')
            self.equipped_armor_hands = self._data.get('equipped_armor_hands')
            self.equipped_armor_feet = self._data.get('equipped_armor_feet')

            self.inventory.reload()
            # Обновляем бонусы от артефактов, HP и переносимый вес
            self._artifact_bonuses = self._get_artifact_bonuses()
            self.max_health_bonus = self._artifact_bonuses.get('max_health_bonus', 0)
            self._recalculate_max_weight()

    @property
    def effective_strength(self) -> int:
        """Сила с учетом бонусов от артефактов."""
        return max(1, int(self.strength + self._artifact_bonuses.get('strength', 0)))

    @property
    def effective_stamina(self) -> int:
        """Выносливость с учетом бонусов от артефактов."""
        return max(1, int(self.stamina + self._artifact_bonuses.get('stamina', 0)))

    @property
    def effective_perception(self) -> int:
        """Восприятие с учетом бонусов от артефактов."""
        return max(1, int(self.perception + self._artifact_bonuses.get('perception', 0)))

    @property
    def effective_luck(self) -> int:
        """Удача с учетом бонусов от артефактов."""
        return max(1, int(self.luck + self._artifact_bonuses.get('luck', 0)))

    @property
    def dodge_chance(self) -> int:
        """Шанс уклонения (%)"""
        base = 10  # Базовый шанс уклонения
        passive = self._get_passive_bonuses()
        artifact = self._artifact_bonuses.get('dodge', 0)
        return base + passive.get('dodge', 0) + artifact

    @property
    def artifact_radiation(self) -> int:
        """Радиация от экипированных артефактов"""
        return self._artifact_bonuses.get('radiation', 0)

    @property
    def find_chance(self) -> int:
        """Шанс что-либо найти (%)"""
        base = self.effective_perception * 3  # 3% за каждый пункт восприятия
        artifact_bonus = self._artifact_bonuses.get('find_chance', 0)

        # Бонус от детектора
        detector_bonus = 0
        if self.equipped_device:
            try:
                from anomalies import get_detector_bonus
                detector_bonus = get_detector_bonus(self)
            except:
                pass

        return min(100, base + artifact_bonus + detector_bonus)

    @property
    def crit_chance(self) -> int:
        """Шанс критического удара (%)"""
        base = 5 + (self.effective_luck - 1) * 2  # Базовый 5% + 2% за каждый пункт удачи свыше 1
        artifact_bonus = self._artifact_bonuses.get('crit', 0)
        passive_bonus = self._get_passive_bonuses().get('crit_chance', 0)
        return min(100, base + artifact_bonus + passive_bonus)

    @property
    def crit_damage(self) -> int:
        """Бонус к критическому урону (%)"""
        passive = self._get_passive_bonuses()
        return passive.get('crit_damage', 0)

    @property
    def rare_find_chance(self) -> int:
        """Шанс редкой находки (%)"""
        base = self.effective_luck * 2  # 2% за каждый пункт удачи
        artifact_bonus = self._artifact_bonuses.get('rare_find_chance', 0)
        passive_bonus = self._get_passive_bonuses().get('rare_find_chance', 0)
        return min(100, base + artifact_bonus + passive_bonus)

    @property
    def melee_damage(self) -> int:
        """Урон в ближнем бою"""
        passive = self._get_passive_bonuses()
        strength_bonus = passive.get('strength', 0)
        artifact_damage_boost = int(self._artifact_bonuses.get('damage_boost', 0) or 0)
        base_damage = 5 + self.effective_strength + strength_bonus
        if artifact_damage_boost > 0:
            base_damage = int(base_damage * (1 + artifact_damage_boost / 100))
        return base_damage

    @property
    def sell_bonus(self) -> int:
        """Бонус к продаже предметов (%)"""
        passive = self._get_passive_bonuses()
        return passive.get('sell_bonus', 0)

    @property
    def max_health(self) -> int:
        """Максимальное здоровье: 25 HP за единицу выносливости"""
        return self.effective_stamina * 25 + self.max_health_bonus + self.hp_upgrade_bonus

    def _get_hp_upgrade_settings(self) -> tuple[int, int]:
        """Получить параметры прокачки HP с безопасными дефолтами."""
        try:
            import config as game_config
            per_level = max(1, int(getattr(game_config, "HP_UPGRADE_PER_LEVEL", 3) or 3))
            max_level = max(0, int(getattr(game_config, "HP_UPGRADE_MAX_LEVEL", 10) or 10))
            return per_level, max_level
        except Exception:
            return 3, 10

    @property
    def hp_upgrade_bonus(self) -> int:
        """Перманентный бонус к максимальному HP от прокачки."""
        per_level, max_level = self._get_hp_upgrade_settings()
        return min(max_level, self.hp_upgrade_level) * per_level

    @property
    def hp_upgrade_max_level(self) -> int:
        _, max_level = self._get_hp_upgrade_settings()
        return max_level

    @property
    def total_defense(self) -> int:
        """Общая защита (броня + артефакты + пассивные навыки)"""
        artifact_def = self._get_artifact_bonuses().get('defense', 0)
        passive_bonus = self._get_passive_bonuses().get('defense', 0)
        return self.armor_defense + artifact_def + passive_bonus

    def _get_passive_bonuses(self) -> dict:
        """Получить бонусы от пассивных навыков класса"""
        try:
            from classes import get_passive_bonuses, get_class_by_weapon
            # Приоритет: класс по текущему оружию (фактическая роль в бою),
            # fallback: сохранённый класс персонажа.
            class_id = None
            if self.equipped_weapon:
                class_id = get_class_by_weapon(self.equipped_weapon)
            if not class_id:
                class_id = self.player_class
            if not class_id:
                return {}
            return get_passive_bonuses(class_id, self.level)
        except Exception:
            return {}

    @property
    def fire_defense(self) -> int:
        """Защита от огня от артефактов"""
        bonuses = self._get_artifact_bonuses()
        return bonuses.get('defense_fire', 0)

    @property
    def is_fire_immune(self) -> bool:
        """Иммунитет к огню от артефактов"""
        return self._artifact_bonuses.get('fire_immune', False)

    @property
    def equipped_artifacts(self) -> list:
        """Список экипированных артефактов"""
        artifacts = []
        if self.equipped_artifact_1:
            artifacts.append(self.equipped_artifact_1)
        if self.equipped_artifact_2:
            artifacts.append(self.equipped_artifact_2)
        if self.equipped_artifact_3:
            artifacts.append(self.equipped_artifact_3)
        return artifacts

    @property
    def location(self) -> Location:
        return get_location(self.current_location_id)

    def move(self, direction: str) -> tuple[bool, str]:
        """
        Переместиться в другую локацию.
        Возвращает (успех, сообщение)
        """
        new_location_id = self.location.get_exit(direction)

        if new_location_id:
            self.current_location_id = new_location_id
            database.update_user_location(self.user_id, new_location_id)
            loc = self.location
            return True, f"Ты перешёл в локацию: {loc.name}\n\n{loc.description}"
        else:
            return False, "Туда нельзя пройти. Попробуй назвать другое направление."

    def get_status(self) -> str:
        """Получить текущий статус игрока"""
        # Перезагружаем данные из БД
        self.inventory.reload()

        # Обновляем значения из БД
        user_data = database.get_user_by_vk(self.user_id)
        if user_data:
            self.health = user_data.get('health', 100)
            self.energy = user_data.get('energy', 100)
            self.radiation = user_data.get('radiation', 0)
            self.equipped_armor = user_data.get('equipped_armor')
            self.equipped_weapon = user_data.get('equipped_weapon')
            self.equipped_backpack = user_data.get('equipped_backpack')
            self.equipped_device = user_data.get('equipped_device')

        loc = self.location
        exp_needed = self.LEVELS.get(self.level + 1, self.LEVELS[20])
        current_weight = self.inventory.total_weight
        weight_status = "✅ В норме" if current_weight <= self.max_weight else "❌ ПЕРЕГРУЗ"

        # Прогресс-бары
        hp_line = ui.meter_line("HP", self.health, self.max_health, width=14)
        energy_line = ui.meter_line("Энергия", self.energy, 100, width=14)
        exp_line = ui.meter_line("Опыт", self.experience, exp_needed, width=14)

        # ═══════════════════════════════════════════════════
        # СНАРЯЖЕНИЕ
        # ═══════════════════════════════════════════════════
        total_attack = 0
        if self.equipped_weapon:
            weapon_item = database.get_item_by_name(self.equipped_weapon)
            attack = weapon_item.get('attack', 0) if weapon_item else 0
            total_attack = attack

        # Броня по слотам
        armor_slots = []
        total_armor = 0
        slot_icons = {
            'equipped_armor_head': '🧢',
            'equipped_armor_body': '🧥',
            'equipped_armor_legs': '👖',
            'equipped_armor_hands': '🧤',
            'equipped_armor_feet': '👟',
        }
        slot_names = {
            'equipped_armor_head': 'Голова',
            'equipped_armor_body': 'Тело',
            'equipped_armor_legs': 'Ноги',
            'equipped_armor_hands': 'Руки',
            'equipped_armor_feet': 'Ноги (обувь)',
        }

        if user_data:
            for slot, icon in slot_icons.items():
                item_name = user_data.get(slot)
                if item_name:
                    item = database.get_item_by_name(item_name)
                    def_val = item.get('defense', 0) if item else 0
                    armor_slots.append(f"{icon} {item_name} (+{def_val})")
                    total_armor += def_val

        # Артефакты
        equipped_artifacts_count = len(self.equipped_artifacts)

        # Рюкзак
        backpack_display = self.equipped_backpack or "—"

        # Детектор
        detector_display = self.equipped_device or "—"

        # ═══════════════════════════════════════════════════
        # ГИЛЬЗЫ
        # ═══════════════════════════════════════════════════
        shells_info = database.get_shells_info(self.user_id)
        shells_current = shells_info['current']
        shells_capacity = shells_info['capacity']
        shells_bag = shells_info['equipped_bag'] or "—"

        # ═══════════════════════════════════════════════════
        # ПАССИВНЫЕ БОНУСЫ
        # ═══════════════════════════════════════════════════
        passive_bonuses = self._get_passive_bonuses()
        class_info = f"🎭 {self.player_class.upper()}" if self.player_class else "🎭 Нет класса"

        # ═══════════════════════════════════════════════════
        # ХАРАКТЕРИСТИКИ (derived)
        # ═══════════════════════════════════════════════════
        loc_name = loc.name if loc else "—"

        # ═══════════════════════════════════════════════════
        # ФОРМИРОВАНИЕ HUD
        # ═══════════════════════════════════════════════════

        # --- Верхний блок: основное ---
        lines = []
        lines.append(ui.title("Статус персонажа"))
        lines.append(f"📍 {loc_name}")
        lines.append(f"🎯 Ур. {self.level}  |  {class_info}")
        lines.append("")

        # --- Жизненные показатели ---
        lines.append(ui.section("Показатели"))
        lines.append(f"❤️ {hp_line}")
        lines.append(f"⚡ {energy_line}")
        rad_stage = get_radiation_stage(self.radiation)
        lines.append(f"☢️ Радфон: {int(self.radiation)} ед. ({format_radiation_rate(self.radiation)})")
        lines.append(f"🧪 Стадия: {rad_stage['name']}")
        lines.append(f"   {rad_stage['note']}")
        lines.append("")

        # --- Опыт и деньги ---
        lines.append(ui.section("Прогресс"))
        lines.append(f"⭐ {exp_line}")
        lines.append(f"💰 {self.money:,} ₽")
        lines.append("")

        # --- Снаряжение ---
        lines.append(ui.section("Снаряжение"))
        lines.append(f"🔫 {self.equipped_weapon or '—'}  |  ⚔️ Атака: {total_attack}")

        if armor_slots:
            for slot_line in armor_slots:
                lines.append(f"🛡️ {slot_line}")
            lines.append(f"   📊 Всего брони: {total_armor}")
        else:
            lines.append(f"🛡️ Броня: —")

        if equipped_artifacts_count > 0:
            art_names = ", ".join(self.equipped_artifacts)
            lines.append(f"🔮 Артефакты ({equipped_artifacts_count}/{self.artifact_slots}): {art_names}")
        else:
            lines.append(f"🔮 Артефакты: 0/{self.artifact_slots}")

        lines.append(f"🎒 Рюкзак: {backpack_display}  |  📡 {detector_display}")
        lines.append("")

        # --- Характеристики ---
        lines.append(ui.section("Характеристики"))
        lines.append(f"⚔️ Сила: {self.effective_strength}  |  🏃 Выносливость: {self.effective_stamina}")
        lines.append(f"👁️ Восприятие: {self.effective_perception}  |  🍀 Удача: {self.effective_luck}")
        lines.append(f"🧬 Прокачка HP: {self.hp_upgrade_level}/{self.hp_upgrade_max_level} (+{self.hp_upgrade_bonus} HP)")
        lines.append("")
        lines.append(f"📊 Урон: {self.melee_damage}  |  Броня: {self.total_defense}")
        lines.append(f"🎯 Крит: {self.crit_chance}%  |  Уклонение: {self.dodge_chance}%")
        lines.append(f"🔍 Находки: {self.find_chance}%  |  Редкое: {self.rare_find_chance}%")
        lines.append("")

        # --- Груз ---
        lines.append(ui.section("Груз"))
        lines.append(f"⚖️ {current_weight:.1f} / {self.max_weight} кг  {weight_status}")
        lines.append(f"🎯 Гильзы: {shells_current} / {shells_capacity}  ({shells_bag})")

        # --- Пассивные бонусы класса ---
        if passive_bonuses and self.player_class:
            bonus_parts = []
            if passive_bonuses.get('dodge'):
                bonus_parts.append(f"уклон +{passive_bonuses['dodge']}%")
            if passive_bonuses.get('crit_chance'):
                bonus_parts.append(f"крит +{passive_bonuses['crit_chance']}%")
            if passive_bonuses.get('sell_bonus'):
                bonus_parts.append(f"продажа +{passive_bonuses['sell_bonus']}%")
            if passive_bonuses.get('weapon_damage'):
                bonus_parts.append(f"урон +{passive_bonuses['weapon_damage']}%")
            if passive_bonuses.get('max_weight'):
                bonus_parts.append(f"вес +{passive_bonuses['max_weight']}кг")
            if passive_bonuses.get('defense'):
                bonus_parts.append(f"защита +{passive_bonuses['defense']}")
            if passive_bonuses.get('strength'):
                bonus_parts.append(f"сила +{passive_bonuses['strength']}")
            if passive_bonuses.get('crit_damage'):
                bonus_parts.append(f"крит.урон +{passive_bonuses['crit_damage']}%")
            if bonus_parts:
                lines.append("")
                lines.append(f"🎓 Бонусы {self.player_class}: {'  '.join(bonus_parts)}")

        return "\n".join(lines)

    def update_stats(self, health: int = None, energy: int = None, radiation: int = None, money: int = None, level: int = None, experience: int = None, strength: int = None, stamina: int = None, perception: int = None, luck: int = None, armor_defense: int = None, max_weight: int = None):
        """Обновить характеристики"""
        if health is not None:
            self.health = max(0, min(self.max_health, health))
            if self.health <= 0:
                self._handle_death()
                return
        if energy is not None:
            self.energy = max(0, min(100, energy))
        if radiation is not None:
            self.radiation = max(0, radiation)
        if money is not None:
            self.money = max(0, money)
        if level is not None:
            self.level = max(1, min(20, level))
        if experience is not None:
            self.experience = max(0, experience)
            self._check_level_up()
        if strength is not None:
            self.strength = max(1, min(20, strength))
        if stamina is not None:
            self.stamina = max(1, min(20, stamina))
        if perception is not None:
            self.perception = max(1, min(20, perception))
        if luck is not None:
            self.luck = max(1, min(20, luck))
        if armor_defense is not None:
            self.armor_defense = max(0, armor_defense)
        if max_weight is not None:
            self.max_weight = max(10, max_weight)
        elif strength is not None:
            self._recalculate_max_weight()

        update_fields = {}
        if health is not None:
            update_fields["health"] = self.health
        if energy is not None:
            update_fields["energy"] = self.energy
        if radiation is not None:
            update_fields["radiation"] = self.radiation
        if money is not None:
            update_fields["money"] = self.money
        if level is not None:
            update_fields["level"] = self.level
        if experience is not None:
            update_fields["experience"] = self.experience
        if strength is not None:
            update_fields["strength"] = self.strength
            update_fields["max_weight"] = self.max_weight
        if stamina is not None:
            update_fields["stamina"] = self.stamina
        if perception is not None:
            update_fields["perception"] = self.perception
        if luck is not None:
            update_fields["luck"] = self.luck
        if armor_defense is not None:
            update_fields["armor_defense"] = self.armor_defense
        if max_weight is not None:
            update_fields["max_weight"] = self.max_weight

        if update_fields:
            database.update_user_stats(self.user_id, **update_fields)

    def save(self):
        """Сохранить текущую локацию игрока"""
        database.update_user_location(self.user_id, self.current_location_id)

    def _handle_death(self):
        """Обработка смерти персонажа"""
        from state_manager import clear_travel_state

        # Штрафы при смерти
        old_money = self.money
        old_experience = self.experience

        # Теряем 10% денег
        self.money = max(0, self.money - int(self.money * 0.1))
        money_lost = old_money - self.money

        # Теряем 25% опыта, но не ниже порога текущего уровня
        exp_loss = int(old_experience * 0.25)
        exp_needed_current = self.LEVELS.get(self.level, 0)
        exp_needed_next = self.LEVELS.get(self.level + 1, self.LEVELS[20])

        # Минимальный опыт для сохранения текущего уровня
        min_exp = exp_needed_current

        # Новый опыт не может быть ниже порога текущего уровня
        self.experience = max(min_exp, old_experience - exp_loss)

        # Дополнительно проверяем: если опыт был ниже следующего уровня, не опускаем ниже текущего
        if old_experience < exp_needed_next:
            self.experience = max(min_exp, self.experience)

        experience_lost = old_experience - self.experience

        # Восстановление после смерти
        self.health = self.max_health // 2  # 50% здоровья
        self.energy = 50  # 50% энергии
        self.radiation = 0
        self.current_location_id = "больница"

        clear_travel_state(self.user_id)
        database.update_user_location(self.user_id, "больница")

        database.update_user_stats(
            self.user_id,
            health=self.health,
            energy=self.energy,
            radiation=0,
            money=self.money,
            experience=self.experience
        )

        logger.info(f"Игрок {self.user_id} умер. Потеряно: денег={money_lost}, опыта={experience_lost}. HP={self.health}, Energy={self.energy}")

    def _handle_radiation_death(self):
        """Обработка смерти от радиации"""
        from state_manager import clear_travel_state

        # Штрафы при смерти от радиации
        old_money = self.money
        old_experience = self.experience

        # Теряем 10% денег
        self.money = max(0, self.money - int(self.money * 0.1))
        money_lost = old_money - self.money

        # Теряем 25% опыта, но не ниже порога текущего уровня
        exp_loss = int(old_experience * 0.25)
        exp_needed_current = self.LEVELS.get(self.level, 0)
        exp_needed_next = self.LEVELS.get(self.level + 1, self.LEVELS[20])

        # Минимальный опыт для сохранения текущего уровня
        min_exp = exp_needed_current

        # Новый опыт не может быть ниже порога текущего уровня
        self.experience = max(min_exp, old_experience - exp_loss)

        # Дополнительно проверяем: если опыт был ниже следующего уровня, не опускаем ниже текущего
        if old_experience < exp_needed_next:
            self.experience = max(min_exp, self.experience)

        experience_lost = old_experience - self.experience

        # Восстановление после смерти
        self.radiation = 0
        self.health = self.max_health // 2  # 50% здоровья
        self.energy = 50  # 50% энергии
        self.current_location_id = "больница"

        clear_travel_state(self.user_id)
        database.update_user_location(self.user_id, "больница")

        database.update_user_stats(
            self.user_id,
            health=self.health,
            energy=self.energy,
            radiation=0,
            money=self.money,
            experience=self.experience
        )

        logger.info(f"Игрок {self.user_id} умер от радиации. Потеряно: денег={money_lost}, опыта={experience_lost}. HP={self.health}, Energy={self.energy}")

    def _check_level_up(self) -> str | None:
        """Проверить повышение уровня. Возвращает сообщение о повышении или None"""
        exp_needed = self.LEVELS.get(self.level + 1, self.LEVELS[20])
        if self.experience >= exp_needed and self.level < 20:
            old_level = self.level
            self.level += 1

            self.health = self.max_health
            self.energy = 100

            import random
            stat = random.choice(['strength', 'stamina', 'perception', 'luck'])
            old_value = getattr(self, stat)
            setattr(self, stat, old_value + 1)
            self._recalculate_max_weight()

            stat_names = {
                'strength': 'Сила',
                'stamina': 'Выносливость',
                'perception': 'Восприятие',
                'luck': 'Удача'
            }

            database.update_user_stats(
                self.user_id,
                level=self.level,
                health=self.health,
                energy=100,
                strength=self.strength,
                stamina=self.stamina,
                perception=self.perception,
                luck=self.luck,
                max_weight=self.max_weight
            )

            return (
                f"НОВЫЙ УРОВЕНЬ!\n\n"
                f"Был уровень: {old_level} -> Стал: {self.level}\n"
                f"Здоровье восстановлено: {self.health}\n\n"
                f"+1 к характеристике {stat_names[stat]}!\n"
                f"Было: {old_value} -> Стало: {old_value + 1}"
            )

        return None

    def add_experience(self, amount: int):
        """Добавить опыт и проверить повышение уровня"""
        self.experience += amount
        self._check_level_up()
        database.update_user_stats(self.user_id, experience=self.experience)

    def equip_backpack(self, backpack_name: str = None) -> tuple[bool, str]:
        """Надеть или снять рюкзак"""
        self.inventory.reload()

        if backpack_name is None:
            if self.equipped_backpack:
                self.equipped_backpack = None
                self._recalculate_max_weight()
                database.update_user_stats(self.user_id, equipped_backpack=None, max_weight=self.max_weight)
                return True, "Рюкзак снят."
            return False, "Рюкзак не надет."

        backpack = next((b for b in self.inventory.backpacks if b['name'] == backpack_name), None)
        if not backpack:
            return False, f"У тебя нет рюкзака '{backpack_name}' в инвентаре."

        self.equipped_backpack = backpack_name
        backpack_bonus = backpack.get('backpack_bonus', 0)
        self._recalculate_max_weight()

        database.update_user_stats(self.user_id, equipped_backpack=backpack_name, max_weight=self.max_weight)

        return True, f"Надет рюкзак: {backpack_name} (+{backpack_bonus}кг к переносимому весу)"

    def equip_weapon(self, weapon_name: str = None) -> tuple[bool, str]:
        """Надеть или снять оружие"""
        self.inventory.reload()

        if weapon_name is None:
            if self.equipped_weapon:
                self.equipped_weapon = None
                database.update_user_stats(self.user_id, equipped_weapon=None)
                return True, "Оружие снято."
            return False, "Оружие не надето."

        weapon = next((w for w in self.inventory.weapons if w['name'] == weapon_name), None)
        if not weapon:
            return False, f"У тебя нет оружия '{weapon_name}' в инвентаре."

        self.equipped_weapon = weapon_name
        attack = weapon.get('attack', 0)
        database.update_user_stats(self.user_id, equipped_weapon=weapon_name)

        return True, f"Надето оружие: {weapon_name} ({attack})"

    def equip_armor(self, armor_name: str = None) -> tuple[bool, str]:
        """Надеть или снять броню"""
        self.inventory.reload()

        if armor_name is None:
            has_any_armor = any([
                self.equipped_armor,
                self.equipped_armor_head,
                self.equipped_armor_body,
                self.equipped_armor_legs,
                self.equipped_armor_hands,
                self.equipped_armor_feet,
            ])
            if has_any_armor:
                self.equipped_armor = None
                self.equipped_armor_head = None
                self.equipped_armor_body = None
                self.equipped_armor_legs = None
                self.equipped_armor_hands = None
                self.equipped_armor_feet = None
                self.armor_defense = 0
                database.update_user_stats(
                    self.user_id,
                    equipped_armor=None,
                    equipped_armor_head=None,
                    equipped_armor_body=None,
                    equipped_armor_legs=None,
                    equipped_armor_hands=None,
                    equipped_armor_feet=None,
                    armor_defense=0
                )
                return True, "Броня снята."
            return False, "Броня не надета."

        armor = next((a for a in self.inventory.armor if a['name'] == armor_name), None)
        if not armor:
            return False, f"У тебя нет брони '{armor_name}' в инвентаре."

        defense = armor.get('defense', 0)
        armor_type = database.get_armor_type(armor_name)

        # Определяем, в какой слот надевать
        if armor_type == 'head':
            database.update_user_stats(self.user_id, equipped_armor_head=armor_name, equipped_armor=None)
            self.equipped_armor_head = armor_name
        elif armor_type == 'body':
            database.update_user_stats(self.user_id, equipped_armor_body=armor_name, equipped_armor=None)
            self.equipped_armor_body = armor_name
        elif armor_type == 'legs':
            database.update_user_stats(self.user_id, equipped_armor_legs=armor_name, equipped_armor=None)
            self.equipped_armor_legs = armor_name
        elif armor_type == 'hands':
            database.update_user_stats(self.user_id, equipped_armor_hands=armor_name, equipped_armor=None)
            self.equipped_armor_hands = armor_name
        elif armor_type == 'feet':
            database.update_user_stats(self.user_id, equipped_armor_feet=armor_name, equipped_armor=None)
            self.equipped_armor_feet = armor_name
        else:
            # Для старой брони - в основной слот
            database.update_user_stats(self.user_id, equipped_armor=armor_name, armor_defense=defense)
            self.equipped_armor = armor_name
            self.armor_defense = defense
            return True, f"Надета броня: {armor_name} ({defense})"

        # Пересчитываем общую защиту
        self._recalc_armor_defense()

        # Обновляем old-style поле для совместимости
        self.equipped_armor = armor_name

        return True, f"Надета броня: {armor_name}! Защита: +{self.armor_defense}"

    def _recalc_armor_defense(self):
        """Пересчитать общую защиту от всей надетой брони"""
        user_data = database.get_user_by_vk(self.user_id)
        if not user_data:
            return

        total_defense = 0

        # Список всех слотов брони
        armor_slots = [
            user_data.get('equipped_armor'),
            user_data.get('equipped_armor_head'),
            user_data.get('equipped_armor_body'),
            user_data.get('equipped_armor_legs'),
            user_data.get('equipped_armor_hands'),
            user_data.get('equipped_armor_feet'),
        ]

        seen = set()
        for armor_name in armor_slots:
            if armor_name:
                if armor_name in seen:
                    continue
                seen.add(armor_name)
                item = database.get_item_by_name(armor_name)
                if item:
                    total_defense += item.get('defense', 0)

        self.armor_defense = total_defense
        database.update_user_stats(self.user_id, armor_defense=total_defense)

    def equip_device(self, device_name: str = None) -> tuple[bool, str]:
        """Надеть или снять устройство (детектор аномалий)"""
        self.inventory.reload()

        if device_name is None:
            if self.equipped_device:
                self.equipped_device = None
                database.update_user_stats(self.user_id, equipped_device=None)
                return True, "Устройство снято."
            return False, "Устройство не надето."

        device = next((d for d in self.inventory.other if d['name'].lower() == device_name.lower()), None)
        if not device:
            return False, f"У тебя нет устройства '{device_name}' в инвентаре."

        self.equipped_device = device_name
        database.update_user_stats(self.user_id, equipped_device=device_name)

        return True, f"Надето устройство: {device_name}"

    def equip_shells_bag(self, bag_name: str = None) -> tuple[bool, str]:
        """Надеть или снять мешочек для гильз"""
        self.inventory.reload()

        # Проверяем, есть ли категория shells_bag в инвентаре
        if not hasattr(self.inventory, 'shells_bags'):
            return False, "У тебя нет мешочков для гильз."

        if bag_name is None:
            # Снять мешочек
            user_data = database.get_user_by_vk(self.user_id)
            current_bag = user_data.get('equipped_shells_bag') if user_data else None
            if current_bag:
                result = database.unequip_shells_bag(self.user_id)
                return result['success'], result['message']
            return False, "Мешочек не надет."

        # Надеть мешочек
        bag = next((b for b in self.inventory.shells_bags if b['name'].lower() == bag_name.lower()), None)
        if not bag:
            return False, f"У тебя нет мешочка '{bag_name}' в инвентаре."

        result = database.equip_shells_bag(self.user_id, bag['name'])
        return result['success'], result['message']

    def use_item(self, item_name: str) -> tuple[bool, str]:
        """Использовать предмет из инвентаря"""
        self.inventory.reload()

        all_items = (
            self.inventory.weapons +
            self.inventory.armor +
            self.inventory.artifacts +
            self.inventory.backpacks +
            self.inventory.other
        )
        item = next((i for i in all_items if i['name'].lower() == item_name.lower()), None)

        if not item:
            return False, f"У тебя нет предмета '{item_name}'."

        used = False
        msg = ""
        item_key = item_name.lower().strip()

        old_health = int(self.health)
        old_energy = int(self.energy)
        old_radiation = int(self.radiation)
        old_max_health = int(self.max_health)

        hp_restore = {
            "аптечка": 50,
            "научная аптечка": 80,
            "бинт": 20,
            "стимулятор": 50,
            "боевой стимулятор": 80,
            "боевой стимулятор упак": 80,
            "чистая вода": 30,
            "лечебная трава": 25,
        }
        energy_restore = {
            "супер энергетик": 9999,  # полный заряд
            "super energy": 9999,
            "энергетик": 30,
            "кофе": 15,
            "вода": 10,
            "хлеб": 15,
            "колбаса": 20,
            "консервы": 25,
            "стимулятор": 20,
            "боевой стимулятор": 50,
            "боевой стимулятор упак": 50,
        }
        radiation_delta = {
            "антирад": -50,
            "чистая вода": -10,
        }

        if item_key == "витамины":
            per_upgrade_hp, max_upgrade_level = self._get_hp_upgrade_settings()
            if self.hp_upgrade_level >= max_upgrade_level:
                return False, (
                    "🧬 Витамины больше не дают эффект.\n"
                    f"Достигнут лимит прокачки HP: {self.hp_upgrade_level}/{max_upgrade_level}."
                )
            self.hp_upgrade_level += 1
            self.health = min(self.max_health, self.health + per_upgrade_hp)
            database.update_user_stats(
                self.user_id,
                hp_upgrade_level=self.hp_upgrade_level,
                health=self.health,
            )
            msg = (
                f"🧬 Витамины приняты!\n"
                f"Макс. HP: {old_max_health} -> {self.max_health}\n"
                f"Текущее HP: {old_health} -> {self.health}\n"
                f"Прокачка: {self.hp_upgrade_level}/{max_upgrade_level}"
            )
            used = True
        elif item_key in hp_restore or item_key in energy_restore or item_key in radiation_delta:
            if item_key in hp_restore:
                self.health = min(self.max_health, self.health + hp_restore[item_key])
            if item_key in energy_restore:
                self.energy = min(100, self.energy + energy_restore[item_key])
            if item_key in radiation_delta:
                self.radiation = max(0, self.radiation + radiation_delta[item_key])
            database.update_user_stats(
                self.user_id,
                health=self.health,
                energy=self.energy,
                radiation=self.radiation
            )
            parts = [f"Использовано: {item_name}"]
            if self.health != old_health:
                parts.append(f"❤️ HP: {old_health} -> {self.health}/{self.max_health}")
            if self.energy != old_energy:
                parts.append(f"⚡ Энергия: {old_energy} -> {self.energy}/100")
            if self.radiation != old_radiation:
                parts.append(
                    "☢️ Радиация: "
                    f"{old_radiation} -> {self.radiation} ед. "
                    f"({format_radiation_rate(old_radiation)} -> {format_radiation_rate(self.radiation)})"
                )
                parts.append(f"🧪 {get_radiation_stage(self.radiation)['name']}")
            if len(parts) == 1:
                parts.append("Эффект не сработал, параметры уже были на максимуме.")
            msg = "\n".join(parts)
            used = True
        else:
            return False, f"Предмет '{item_name}' нельзя использовать."

        if used:
            database.remove_item_from_inventory(self.user_id, item['name'], 1)
            self.inventory.reload()

        return True, msg

    def buy_item(self, item_name: str, merchant_id: str | None = None) -> tuple[bool, str]:
        """Купить предмет у торговца"""
        import database as db

        item_info = db.get_item_by_name(item_name)

        if not item_info:
            return False, f"Такой предмет не продаётся."

        price = item_info.get('price', 0)

        if self.money < price:
            return False, f"Не хватает денег. Нужно {price} руб., у тебя {self.money} руб."

        weight = item_info.get('weight', 1.0)
        current_weight = self.inventory.total_weight
        if current_weight + weight > self.max_weight:
            return False, f"Не хватает места в рюкзаке. Вес: {current_weight}/{self.max_weight}кг"

        result = db.buy_item_transaction(self.user_id, item_name, merchant_id=merchant_id)
        if not result.get('success'):
            return False, result.get('message', 'Ошибка покупки.')

        self.money = result.get('remaining_money', self.money - price)

        self.inventory.reload()

        paid_price = result.get('price', price)
        return True, f"Ты купил {item_name} за {paid_price} руб.\nОсталось денег: {self.money} руб."

    def sell_item(self, item_name: str, merchant_id: str | None = None) -> tuple[bool, str]:
        """Продать предмет торговцу"""
        import database as db

        self.inventory.reload()

        all_items = (
            self.inventory.weapons +
            self.inventory.armor +
            self.inventory.artifacts +
            self.inventory.backpacks +
            self.inventory.other
        )

        item = next((i for i in all_items if i['name'].lower() == item_name.lower()), None)

        if not item:
            return False, f"У тебя нет предмета '{item_name}'."

        sell_bonus = self.sell_bonus
        result = db.sell_item_transaction(
            self.user_id,
            item['name'],
            sell_bonus_pct=sell_bonus,
            merchant_id=merchant_id,
        )
        if not result.get('success'):
            return False, result.get('message', 'Ошибка продажи.')

        sell_price = result.get('sell_price', 0)
        self.money = result.get('remaining_money', self.money + sell_price)

        self.inventory.reload()

        return True, f"Ты продал {item_name} за {sell_price} руб.\nДенег: {self.money} руб."

    def get_shop_items(self, category: str = None) -> list[dict]:
        """Получить список предметов в магазине"""
        import database as db
        return db.get_shop_items(category)


# Кэш игроков в памяти
_player_cache = {}
import threading
_cache_lock = threading.Lock()
_CACHE_TTL = 60  # Время жизни кэша в секундах


def get_player(user_id: int) -> Player:
    """Получить игрока (с кэшированием)"""
    global _player_cache
    import time

    current_time = time.time()

    with _cache_lock:
        cached = _player_cache.get(user_id)

        if cached and (current_time - cached['_timestamp']) < _CACHE_TTL:
            return cached['_player']

        player = Player(user_id)

        _player_cache[user_id] = {
            '_player': player,
            '_timestamp': current_time
        }

        if len(_player_cache) > 100:
            oldest = min(_player_cache.items(), key=lambda x: x[1]['_timestamp'])
            del _player_cache[oldest[0]]

        return player


def invalidate_player_cache(user_id: int = None):
    """Инвалидировать кэш игрока"""
    global _player_cache

    with _cache_lock:
        if user_id:
            _player_cache.pop(user_id, None)
        else:
            _player_cache.clear()
