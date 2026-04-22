import unittest

from handlers.storage import _parse_transfer_payload


class StorageParsingTest(unittest.TestCase):
    def test_parse_default_qty(self):
        qty, name = _parse_transfer_payload("Бинт")
        self.assertEqual(qty, 1)
        self.assertEqual(name, "Бинт")

    def test_parse_with_qty(self):
        qty, name = _parse_transfer_payload("3 Бинт")
        self.assertEqual(qty, 3)
        self.assertEqual(name, "Бинт")

    def test_parse_errors(self):
        res = _parse_transfer_payload("")
        self.assertIsNone(res[0])
        self.assertIn("Укажи предмет", res[1])

        res = _parse_transfer_payload("0 Бинт")
        self.assertIsNone(res[0])
        self.assertIn("Количество", res[1])


if __name__ == "__main__":
    unittest.main()
