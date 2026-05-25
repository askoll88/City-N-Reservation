import unittest
import importlib
import sys
from unittest.mock import Mock, patch


class VkProfileSyncTests(unittest.TestCase):
    def test_sync_vk_profile_stores_real_name_and_throttles(self):
        main = sys.modules.get("main")
        if main is None or not hasattr(main, "_sync_vk_profile"):
            sys.modules.pop("main", None)
            main = importlib.import_module("main")

        class Users:
            def __init__(self):
                self.get = Mock(return_value=[{
                    "id": 777,
                    "first_name": "Иван",
                    "last_name": "Петров",
                    "screen_name": "ivan.petrov",
                }])

        class Vk:
            def __init__(self):
                self.users = Users()

        vk = Vk()
        main._vk_profile_sync_ts.clear()
        with patch("main.database.update_user_vk_profile", return_value=True) as update_profile:
            main._sync_vk_profile(777, vk)
            main._sync_vk_profile(777, vk)

        vk.users.get.assert_called_once_with(user_ids="777", fields="screen_name")
        update_profile.assert_called_once_with(
            777,
            first_name="Иван",
            last_name="Петров",
            screen_name="ivan.petrov",
        )


if __name__ == "__main__":
    unittest.main()
