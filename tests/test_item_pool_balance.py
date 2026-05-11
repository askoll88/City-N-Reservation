import unittest

from game.item_pool import ITEMS_POOL


def _rarity(item: tuple) -> str:
    return item[8] if len(item) >= 12 else "common"


def _by_name(name: str) -> tuple:
    for item in ITEMS_POOL:
        if item[0] == name:
            return item
    raise AssertionError(f"item not found: {name}")


class ItemPoolBalanceTest(unittest.TestCase):
    def test_restored_trash_is_separate_from_useful_resources(self):
        still_retired = {"Суп с опилками", "Патрон 5.45", "Патрон 9мм"}
        still_retired.update({
            "Ржавая гильза",
            "Сломанный патрон",
            "Пустая гильза",
            "Ржавый болт",
            "Обрывок проволоки",
            "Грязная тряпка",
            "Пустая банка",
            "Пустая бутылка",
            "Кость",
            "Мокрая газета",
            "Ржавая железка",
            "Сломанный нож",
            "Мёртвый артефакт",
            "Зажигалка",
            "Монета",
            "Документ",
            "Фотография",
        })
        restored_trash = {
            "Погнутый жетон",
            "Треснувший изолятор",
            "Комок ржавой стружки",
            "Плавленая пуговица",
            "Слипшийся блокнот",
            "Обугленный ремешок",
            "Коробок сырых спичек",
            "Треснувшая линза",
            "Пустой фильтр",
            "Осколок керамики",
            "Почерневшая батарейка",
            "Провонявший бинт",
            "Мятый шеврон",
            "Застывшая капля смолы",
            "Крышка от фляги",
            "Сломанная пряжка",
            "Пыльный предохранитель",
        }
        names = {item[0] for item in ITEMS_POOL}

        self.assertTrue(still_retired.isdisjoint(names))
        self.assertTrue(restored_trash.issubset(names))
        for item_name in restored_trash:
            self.assertEqual(_by_name(item_name)[1], "trash", item_name)
        for replacement in {"Металлолом", "Ветошь", "Стеклянная тара", "Старые документы", "Аномальный шлак"}:
            self.assertIn(replacement, names)
            self.assertEqual(_by_name(replacement)[1], "resources", replacement)

    def test_powerful_legacy_items_are_not_common(self):
        expected = {
            "Экзоскелет": "legendary",
            "Бронекостюм": "epic",
            "Комбинезон сталкера": "epic",
            "Шлем спецназа": "legendary",
            "ТОЗ-34": "rare",
            "Ф-1": "legendary",
            "РГД-5": "legendary",
            "АК-74": "uncommon",
        }

        for item_name, rarity in expected.items():
            self.assertEqual(_rarity(_by_name(item_name)), rarity, item_name)

    def test_common_equipment_stays_starter_power(self):
        for item in ITEMS_POOL:
            if len(item) < 7:
                continue
            name, category, _desc, _price, attack, defense, _weight = item[:7]
            if _rarity(item) != "common":
                continue
            if category in {"weapons", "rare_weapons"}:
                self.assertLess(int(attack or 0), 30, name)
            if category in {"armor", "rare_armor"}:
                self.assertLess(int(defense or 0), 16, name)

    def test_backpacks_have_meaningful_long_trip_progression(self):
        backpacks = [item for item in ITEMS_POOL if item[1] == "backpacks"]
        self.assertGreaterEqual(len(backpacks), 4)

        previous_price = 0
        previous_bonus = 0
        previous_net = 0.0
        for name, _category, _desc, price, _attack, _defense, weight, bonus, *_rest in backpacks:
            net_capacity = float(bonus) - float(weight)
            self.assertGreater(price, previous_price, name)
            self.assertGreater(bonus, previous_bonus, name)
            self.assertGreater(net_capacity, previous_net, name)
            self.assertGreaterEqual(price / max(1, net_capacity), 50, name)
            previous_price = price
            previous_bonus = bonus
            previous_net = net_capacity

        starter = _by_name("Походный рюкзак")
        cargo = _by_name("Грузовой рюкзак")
        self.assertLessEqual(starter[7], 12)
        self.assertGreaterEqual(cargo[3], 10_000)
        self.assertGreaterEqual(cargo[6], 8.0)


if __name__ == "__main__":
    unittest.main()
