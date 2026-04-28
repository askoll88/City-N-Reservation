import importlib
import sys
import types
import unittest
from unittest.mock import Mock


class DummyInventory:
    def __init__(self, total_weight=0.0, weapons=None, armor=None, artifacts=None, backpacks=None, shells_bags=None, other=None):
        self._total_weight = total_weight
        self.weapons = weapons or []
        self.armor = armor or []
        self.artifacts = artifacts or []
        self.backpacks = backpacks or []
        self.shells_bags = shells_bags or []
        self.other = other or []
        self.reload_calls = 0

    @property
    def total_weight(self):
        return self._total_weight

    def reload(self):
        self.reload_calls += 1


class PlayerTransactionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Подменяем infra.database, чтобы тесты были изолированы от реальной БД.
        cls.fake_db = types.ModuleType("database")
        cls.fake_db.get_item_by_name = Mock()
        cls.fake_db.buy_item_transaction = Mock()
        cls.fake_db.sell_item_transaction = Mock()
        cls.player_module = importlib.import_module("models.player")
        import infra
        cls.real_db = infra.database
        infra.database = cls.fake_db
        sys.modules["infra.database"] = cls.fake_db

    @classmethod
    def tearDownClass(cls):
        import infra
        infra.database = cls.real_db
        sys.modules["infra.database"] = cls.real_db

    def setUp(self):
        self.fake_db.get_item_by_name.reset_mock()
        self.fake_db.buy_item_transaction.reset_mock()
        self.fake_db.sell_item_transaction.reset_mock()

    def _make_player(self, money=1000, max_weight=30):
        p = self.player_module.Player.__new__(self.player_module.Player)
        p.user_id = 42
        p.money = money
        p.max_weight = max_weight
        p.player_class = None
        p.level = 1
        p.inventory = DummyInventory(total_weight=5.0)
        return p

    def test_buy_item_uses_atomic_transaction(self):
        p = self._make_player(money=1000, max_weight=30)
        self.fake_db.get_item_by_name.return_value = {"name": "ПМ", "price": 150, "weight": 1.2}
        self.fake_db.buy_item_transaction.return_value = {
            "success": True,
            "remaining_money": 850,
        }

        success, msg = p.buy_item("ПМ")

        self.assertTrue(success)
        self.assertIn("Ты купил ПМ", msg)
        self.fake_db.buy_item_transaction.assert_called_once_with(42, "ПМ", merchant_id=None)
        self.assertEqual(p.money, 850)
        self.assertGreaterEqual(p.inventory.reload_calls, 1)

    def test_buy_item_stops_on_weight_limit_before_db(self):
        p = self._make_player(money=1000, max_weight=5)
        p.inventory = DummyInventory(total_weight=5.0)
        self.fake_db.get_item_by_name.return_value = {"name": "АК-74", "price": 500, "weight": 2.0}

        success, msg = p.buy_item("АК-74")

        self.assertFalse(success)
        self.assertIn("Не хватает места", msg)
        self.fake_db.buy_item_transaction.assert_not_called()

    def test_sell_item_uses_atomic_transaction_and_bonus(self):
        p = self._make_player(money=300)
        p._get_passive_bonuses = types.MethodType(lambda self: {"sell_bonus": 20}, p)
        p.inventory = DummyInventory(
            total_weight=3.0,
            weapons=[{"name": "ПМ", "quantity": 1}],
        )
        self.fake_db.sell_item_transaction.return_value = {
            "success": True,
            "sell_price": 60,
            "remaining_money": 360,
        }

        success, msg = p.sell_item("пм")

        self.assertTrue(success)
        self.assertIn("Ты продал пм", msg)
        self.fake_db.sell_item_transaction.assert_called_once_with(
            42, "ПМ", merchant_id=None, sell_bonus_pct=20
        )
        self.assertEqual(p.money, 360)
        self.assertGreaterEqual(p.inventory.reload_calls, 2)


if __name__ == "__main__":
    unittest.main()
