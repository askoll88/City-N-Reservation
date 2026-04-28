import unittest
from unittest.mock import patch

from handlers.location import _is_location_locked


class LocationLocksTest(unittest.TestCase):
    @patch("handlers.location.database.get_user_flag", return_value=1)
    def test_shelter_locks_after_newbie_kit_flag(self, get_flag_mock):
        self.assertTrue(_is_location_locked(1, "убежище"))
        get_flag_mock.assert_called_once_with(1, "newbie_kit_received", default=0)

    @patch("handlers.location.database.get_user_flag")
    def test_non_shelter_locations_do_not_read_newbie_flag(self, get_flag_mock):
        self.assertFalse(_is_location_locked(1, "город"))
        get_flag_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
