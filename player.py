"""
Классы игрока и инвентаря
"""
import database
from locations import get_location, Location


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

        # Инициализируем инвентарь
        self.inventory = Inventory(user_id)

        # Применяем бонус от рюкзака
        if self.equipped_backpack:
            backpack = next((b for b in self.inventory.backpacks if b['name'] == self.equipped_backpack), None)
            if backpack:
                self.max_weight += backpack.get('backpack_bonus', 0)

    def _get_artifact_bonuses(self) -> dict:
        """Получить бонусы от экипированных артефактов"""
        bonuses = database.get_artifact_bonuses(self.user_id)
        return bonuses

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

            # max_weight с учётом пассивных навыков
            passive = self._get_passive_bonuses()
            passive_weight_bonus = passive.get('max_weight', 0)
            base_max_weight = 20 + self.strength * 2 + passive_weight_bonus
            self.max_weight = base_max_weight
            if self.equipped_backpack:
                backpack = next((b for b in self.inventory.backpacks if b['name'] == self.equipped_backpack), None)
                if backpack:
                    self.max_weight += backpack.get('backpack_bonus', 0)

            # Обновляем бонусы от артефактов И max_health_bonus
            self._artifact_bonuses = self._get_artifact_bonuses()
            self.max_health_bonus = self._artifact_bonuses.get('max_health_bonus', 0)

            self.inventory.reload()

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
        base = self.perception * 3  # 3% за каждый пункт восприятия
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
        base = 5 + (self.luck - 1) * 2  # Базовый 5% + 2% за каждый пункт удачи свыше 1
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
        base = self.luck * 2  # 2% за каждый пункт удачи
        artifact_bonus = self._artifact_bonuses.get('rare_find_chance', 0)
        passive_bonus = self._get_passive_bonuses().get('rare_find_chance', 0)
        return min(100, base + artifact_bonus + passive_bonus)

    @property
    def melee_damage(self) -> int:
        """Урон в ближнем бою"""
        passive = self._get_passive_bonuses()
        strength_bonus = passive.get('strength', 0)
        return 5 + self.strength + strength_bonus

    @property
    def sell_bonus(self) -> int:
        """Бонус к продаже предметов (%)"""
        passive = self._get_passive_bonuses()
        return passive.get('sell_bonus', 0)

    @property
    def max_health(self) -> int:
        """Максимальное здоровье: 25 HP за единицу выносливости"""
        return self.stamina * 25 + self.max_health_bonus

    @property
    def total_defense(self) -> int:
        """Общая защита (броня + артефакты + пассивные навыки)"""
        artifact_def = self._get_artifact_bonuses().get('defense', 0)
        passive_bonus = self._get_passive_bonuses().get('defense', 0)
        return self.armor_defense + artifact_def + passive_bonus

    def _get_passive_bonuses(self) -> dict:
        """Получить бонусы от пассивных навыков класса"""
        if not self.player_class:
            return {}

        try:
            from classes import get_passive_bonuses
            return get_passive_bonuses(self.player_class, self.level)
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
        weight_status = "ОК" if current_weight <= self.max_weight else "ПЕРЕГРУЗ"

        # ═══════════════════════════════════════════════════
        # КРАСИВЫЕ ПРОГРЕСС-БАРЫ
        # ═══════════════════════════════════════════════════
        def create_bar(current: int, max_val: int, length: int = 10) -> str:
            """Создать красивый прогресс-бар"""
            percent = current / max_val
            filled = int(percent * length)

            # Символы для бара
            if percent >= 0.7:
                fill_char = "🟩"  # Зелёный
            elif percent >= 0.3:
                fill_char = "🟨"  # Жёлтый
            else:
                fill_char = "🟥"  # Красный

            empty_char = "⬜"  # Пустой
            return fill_char * filled + empty_char * (length - filled)

        def create_rad_bar(current: int, max_val: int = 100, length: int = 10) -> str:
            """Прогресс-бар радиации (инвертированный)"""
            percent = current / max_val
            filled = int(percent * length)

            # Для радиации: зелёный → жёлтый → красный
            if percent <= 0.3:
                fill_char = "🟩"  # Мало радиации
            elif percent <= 0.7:
                fill_char = "🟨"  # Средне
            else:
                fill_char = "🟥"  # Опасно

            empty_char = "⬜"
            return fill_char * filled + empty_char * (length - filled)

        def create_exp_bar(current: int, max_val: int, length: int = 10) -> str:
            """Прогресс-бар опыта (синий)"""
            percent = current / max_val
            filled = int(percent * length)
            fill_char = "🔵"  # Синий для опыта
            empty_char = "⬜"
            return fill_char * filled + empty_char * (length - filled)

        # Прогресс-бары
        hp_bar = create_bar(self.health, self.max_health)
        energy_bar = create_bar(self.energy, 100)
        rad_bar = create_rad_bar(self.radiation)
        exp_bar = create_exp_bar(self.experience, exp_needed)

        # Формируем строку экипировки
        equip_parts = []

        # Оружие с общей атакой
        total_attack = 0
        if self.equipped_weapon:
            weapon_item = database.get_item_by_name(self.equipped_weapon)
            attack = weapon_item.get('attack', 0) if weapon_item else 0
            total_attack = attack
            equip_parts.append(f"🔫 Оружие: {self.equipped_weapon} (атака {attack})")
        else:
            equip_parts.append("🔫 Оружие: нет")

        # Броня с общей защитой
        armor_parts = []
        total_armor = 0

        # Загружаем данные из БД для всех слотов брони
        if user_data:
            head = user_data.get('equipped_armor_head')
            body = user_data.get('equipped_armor_body')
            legs = user_data.get('equipped_armor_legs')
            hands = user_data.get('equipped_armor_hands')
            feet = user_data.get('equipped_armor_feet')

            if head:
                item = database.get_item_by_name(head)
                def_val = item.get('defense', 0) if item else 0
                armor_parts.append(f"   🧢 {head} (броня {def_val})")
                total_armor += def_val
            if body:
                item = database.get_item_by_name(body)
                def_val = item.get('defense', 0) if item else 0
                armor_parts.append(f"   🧥 {body} (броня {def_val})")
                total_armor += def_val
            if legs:
                item = database.get_item_by_name(legs)
                def_val = item.get('defense', 0) if item else 0
                armor_parts.append(f"   👖 {legs} (броня {def_val})")
                total_armor += def_val
            if hands:
                item = database.get_item_by_name(hands)
                def_val = item.get('defense', 0) if item else 0
                armor_parts.append(f"   🧤 {hands} (броня {def_val})")
                total_armor += def_val
            if feet:
                item = database.get_item_by_name(feet)
                def_val = item.get('defense', 0) if item else 0
                armor_parts.append(f"   👟 {feet} (броня {def_val})")
                total_armor += def_val

        if armor_parts:
            armor_text = "\n".join(armor_parts)
            equip_parts.append(f"🛡️ Броня:\n{armor_text}\n   ────────\n📊 Всего брони: {total_armor}")
        else:
            equip_parts.append("🛡️ Броня: нет\n📊 Всего брони: 0")

        # Добавляем итоговую атаку
        equip_parts.append(f"📊 Всего атаки: {total_attack}")

        # Артефакты
        equipped_artifacts_count = len(self.equipped_artifacts)
        if equipped_artifacts_count > 0:
            artifact_list = []
            for art_name in self.equipped_artifacts:
                art_item = database.get_item_by_name(art_name)
                if art_item:
                    bonuses = []
                    if art_item.get('crit_bonus'):
                        bonuses.append(f"крит:+{art_item['crit_bonus']}%")
                    if art_item.get('find_bonus'):
                        bonuses.append(f"находка:+{art_item['find_bonus']}%")
                    if art_item.get('radiation'):
                        bonuses.append(f"рад:{art_item['radiation']}")
                    if art_item.get('energy_bonus'):
                        bonuses.append(f"энергия:+{art_item['energy_bonus']}")
                    if art_item.get('defense_bonus'):
                        bonuses.append(f"защита:+{art_item['defense_bonus']}%")
                    if art_item.get('dodge_bonus'):
                        bonuses.append(f"уклон:+{art_item['dodge_bonus']}%")

                    bonus_str = f" ({', '.join(bonuses)})" if bonuses else ""
                    artifact_list.append(f"   🔮 {art_name}{bonus_str}")

            artifacts_text = "\n".join(artifact_list)
            equip_parts.append(f"🔮 Артефакты ({equipped_artifacts_count}/{self.artifact_slots}):")
            equip_parts.append(artifacts_text)
        else:
            equip_parts.append(f"🔮 Артефакты: 0/{self.artifact_slots}")

        if self.equipped_backpack:
            bp_item = database.get_item_by_name(self.equipped_backpack)
            bp_bonus = bp_item.get('backpack_bonus', 0) if bp_item else 0
            equip_parts.append(f"🎒 Рюкзак: {self.equipped_backpack} (+{bp_bonus}кг)")
        else:
            equip_parts.append("🎒 Рюкзак: нет")

        # Детектор
        if self.equipped_device:
            equip_parts.append(f"📡 Детектор: {self.equipped_device}")
        else:
            equip_parts.append("📡 Детектор: нет")

        # Защита: броня + артефакты
        artifact_def = self._get_artifact_bonuses().get('defense', 0)
        defense_info = f"+{self.total_defense}"
        if artifact_def > 0 and self.armor_defense > 0:
            defense_info = f"+{self.total_defense} (броня: {self.armor_defense}, артефакты: {artifact_def})"
        elif artifact_def > 0:
            defense_info = f"+{self.total_defense} (артефакты: {artifact_def})"
        elif self.armor_defense > 0:
            defense_info = f"+{self.total_defense} (броня: {self.armor_defense})"

        equip_text = "\n".join(equip_parts)

        # Получаем информацию о гильзах
        shells_info = database.get_shells_info(self.user_id)
        shells_current = shells_info['current']
        shells_capacity = shells_info['capacity']
        shells_bag = shells_info['equipped_bag'] or "нет"

        shells_text = f"Гильзы: {shells_current}/{shells_capacity}"
        if shells_bag != "нет":
            shells_text += f" (мешочек: {shells_bag})"

        # Получаем бонусы от пассивных навыков
        passive_bonuses = self._get_passive_bonuses()
        passive_info = ""
        if passive_bonuses and self.player_class:
            passive_info = "\n🎓 <b>Бонусы класса:</b>\n"
            bonus_parts = []
            if passive_bonuses.get('dodge'):
                bonus_parts.append(f"Уклонение: +{passive_bonuses['dodge']}%")
            if passive_bonuses.get('crit_chance'):
                bonus_parts.append(f"Крит: +{passive_bonuses['crit_chance']}%")
            if passive_bonuses.get('sell_bonus'):
                bonus_parts.append(f"Продажа: +{passive_bonuses['sell_bonus']}%")
            if passive_bonuses.get('weapon_damage'):
                bonus_parts.append(f"Урон оружия: +{passive_bonuses['weapon_damage']}%")
            if passive_bonuses.get('max_weight'):
                bonus_parts.append(f"Перенос: +{passive_bonuses['max_weight']}кг")
            if passive_bonuses.get('defense'):
                bonus_parts.append(f"Защита: +{passive_bonuses['defense']}")
            if passive_bonuses.get('strength'):
                bonus_parts.append(f"Сила: +{passive_bonuses['strength']}")
            if passive_bonuses.get('crit_damage'):
                bonus_parts.append(f"Крит урон: +{passive_bonuses['crit_damage']}%")
            passive_info += ", ".join(bonus_parts) if bonus_parts else "нет"

        class_info = f"\n🎭 Класс: {self.player_class.upper()}" if self.player_class else ""

        return (
            f"📊 СТАТУС ПЕРСОНАЖА{class_info}\n\n"
            f"❤️ HP:        {hp_bar} {self.health}/{self.max_health}\n"
            f"⚡ Энергия:    {energy_bar} {self.energy}/100\n"
            f"☢️ Радиация:  {rad_bar} {self.radiation}%\n\n"
            f"💰 Деньги: {self.money} руб.\n"
            f"🎯 Уровень: {self.level} | Опыт: {self.experience}/{exp_needed}\n"
            f"           {exp_bar}\n\n"
            f"🎒 Экипировка:\n{equip_text}\n\n"
            f"💪 Характеристики:\n"
            f"   • Сила: {self.strength} (урон: {self.melee_damage}, +{self.strength * 2}кг)\n"
            f"   • Выносливость: {self.stamina} (HP: {self.max_health})\n"
            f"   • Восприятие: {self.perception} (находка: {self.find_chance}%)\n"
            f"   • Удача: {self.luck} (крит: {self.crit_chance}%, редкое: {self.rare_find_chance}%)\n"
            f"   • Уклонение: {self.dodge_chance}%{passive_info}\n\n"
            f"📦 Груз:\n"
            f"   • Защита: {defense_info}\n"
            f"   • Вес: {current_weight}/{self.max_weight}кг {weight_status}\n\n"
            f"🎯 Гильзы: {shells_text}"
        )

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
            if self.radiation >= 100:
                self._handle_radiation_death()
                return
        if money is not None:
            self.money = max(0, money)
        if level is not None:
            self.level = max(1, min(20, level))
        if experience is not None:
            self.experience = max(0, experience)
            self._check_level_up()
        if strength is not None:
            self.strength = max(1, min(20, strength))
            passive = self._get_passive_bonuses()
            passive_weight_bonus = passive.get('max_weight', 0)
            self.max_weight = 20 + self.strength * 2 + passive_weight_bonus
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

        database.update_user_stats(
            self.user_id,
            self.health if health else None,
            self.energy if energy else None,
            self.radiation if radiation else None,
            self.money if money else None,
            self.level if level else None,
            self.experience if experience else None,
            self.strength if strength else None,
            self.stamina if stamina else None,
            self.perception if perception else None,
            self.luck if luck else None,
            self.armor_defense if armor_defense else None,
            self.max_weight if max_weight else None
        )

    def save(self):
        """Сохранить текущую локацию игрока"""
        database.update_user_location(self.user_id, self.current_location_id)

    def _handle_death(self):
        """Обработка смерти персонажа"""
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
                luck=self.luck
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
                passive = self._get_passive_bonuses()
                passive_weight_bonus = passive.get('max_weight', 0)
                self.max_weight = 20 + self.strength * 2 + passive_weight_bonus
                database.update_user_stats(self.user_id, equipped_backpack=None, max_weight=self.max_weight)
                return True, "Рюкзак снят."
            return False, "Рюкзак не надет."

        backpack = next((b for b in self.inventory.backpacks if b['name'] == backpack_name), None)
        if not backpack:
            return False, f"У тебя нет рюкзака '{backpack_name}' в инвентаре."

        self.equipped_backpack = backpack_name
        passive = self._get_passive_bonuses()
        passive_weight_bonus = passive.get('max_weight', 0)
        base_max_weight = 20 + self.strength * 2 + passive_weight_bonus
        backpack_bonus = backpack.get('backpack_bonus', 0)
        self.max_weight = base_max_weight + backpack_bonus

        database.update_user_stats(self.user_id, equipped_backpack=backpack_name, max_weight=base_max_weight)

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
            if self.equipped_armor:
                self.equipped_armor = None
                self.armor_defense = 0
                database.update_user_stats(self.user_id, equipped_armor=None, armor_defense=0)
                return True, "Броня снята."
            return False, "Броня не надета."

        armor = next((a for a in self.inventory.armor if a['name'] == armor_name), None)
        if not armor:
            return False, f"У тебя нет брони '{armor_name}' в инвентаре."

        defense = armor.get('defense', 0)
        armor_type = database.get_armor_type(armor_name)

        # Определяем, в какой слот надевать
        if armor_type == 'head':
            database.update_user_stats(self.user_id, equipped_armor_head=armor_name)
        elif armor_type == 'body':
            database.update_user_stats(self.user_id, equipped_armor_body=armor_name)
        elif armor_type == 'legs':
            database.update_user_stats(self.user_id, equipped_armor_legs=armor_name)
        elif armor_type == 'hands':
            database.update_user_stats(self.user_id, equipped_armor_hands=armor_name)
        elif armor_type == 'feet':
            database.update_user_stats(self.user_id, equipped_armor_feet=armor_name)
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

        for armor_name in armor_slots:
            if armor_name:
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

        if item_name.lower() in ['супер энергетик', 'super energy']:
            old_energy = self.energy
            self.energy = 100
            database.update_user_stats(self.user_id, energy=100)
            msg = f"Супер энергетик! Энергия: {old_energy} -> 100"
            used = True
        elif item_name.lower() == 'энергетик':
            old_energy = self.energy
            self.energy = min(100, self.energy + 30)
            database.update_user_stats(self.user_id, energy=self.energy)
            msg = f"Энергетик выпит! Энергия: {old_energy} -> {self.energy}"
            used = True
        elif item_name.lower() == 'кофе':
            old_energy = self.energy
            self.energy = min(100, self.energy + 15)
            database.update_user_stats(self.user_id, energy=self.energy)
            msg = f"Кофе выпит. Энергия: {old_energy} -> {self.energy}"
            used = True
        elif item_name.lower() == 'аптечка':
            old_health = self.health
            self.health = 100
            database.update_user_stats(self.user_id, health=100)
            msg = f"Аптечка использована! Здоровье: {old_health} -> 100"
            used = True
        elif item_name.lower() == 'бинт':
            old_health = self.health
            self.health = min(100, self.health + 25)
            database.update_user_stats(self.user_id, health=self.health)
            msg = f"Бинт использован. Здоровье: {old_health} -> {self.health}"
            used = True
        elif item_name.lower() == 'антирад':
            old_radiation = self.radiation
            self.radiation = max(0, self.radiation - 50)
            database.update_user_stats(self.user_id, radiation=self.radiation)
            msg = f"Антирад принят. Радиация: {old_radiation} -> {self.radiation}"
            used = True
        elif item_name.lower() == 'вода':
            old_energy = self.energy
            self.energy = min(100, self.energy + 10)
            database.update_user_stats(self.user_id, energy=self.energy)
            msg = f"Вода выпита. Энергия: {old_energy} -> {self.energy}"
            used = True
        elif item_name.lower() == 'хлеб':
            old_energy = self.energy
            self.energy = min(100, self.energy + 15)
            database.update_user_stats(self.user_id, energy=self.energy)
            msg = f"Хлеб съеден. Энергия: {old_energy} -> {self.energy}"
            used = True
        elif item_name.lower() == 'колбаса':
            old_energy = self.energy
            self.energy = min(100, self.energy + 20)
            database.update_user_stats(self.user_id, energy=self.energy)
            msg = f"Колбаса съедена. Энергия: {old_energy} -> {self.energy}"
            used = True
        elif item_name.lower() == 'консервы':
            old_energy = self.energy
            self.energy = min(100, self.energy + 25)
            database.update_user_stats(self.user_id, energy=self.energy)
            msg = f"Консервы съедены. Энергия: {old_energy} -> {self.energy}"
            used = True
        else:
            return False, f"Предмет '{item_name}' нельзя использовать."

        if used:
            database.remove_item_from_inventory(self.user_id, item['name'], 1)
            self.inventory.reload()

        return True, msg

    def buy_item(self, item_name: str) -> tuple[bool, str]:
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

        result = db.buy_item_transaction(self.user_id, item_name)
        if not result.get('success'):
            return False, result.get('message', 'Ошибка покупки.')

        self.money = result.get('remaining_money', self.money - price)

        self.inventory.reload()

        return True, f"Ты купил {item_name} за {price} руб.\nОсталось денег: {self.money} руб."

    def sell_item(self, item_name: str) -> tuple[bool, str]:
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
            sell_bonus_pct=sell_bonus
        )
        if not result.get('success'):
            return False, result.get('message', 'Ошибка продажи.')

        sell_price = result.get('sell_price', 0)
        self.money = result.get('remaining_money', self.money + sell_price)

        self.inventory.reload()

        bonus_msg = f" (+{sell_bonus}% бонус)" if sell_bonus > 0 else ""
        return True, f"Ты продал {item_name} за {sell_price} руб.{bonus_msg}\nДенег: {self.money} руб."

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
