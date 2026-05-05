import unittest
from unittest.mock import patch

from game.location_mechanics import (
    get_anomaly_rarity_chances,
    get_location_anomaly_types,
    get_random_anomaly_for_location,
    location_has_anomalies,
)
from infra.database import roll_artifact_from_anomaly


ARTIFACT_FIXTURE = {
    "Выверт": "rare",
    "Лунный свет": "rare",
    "Мамины бусы": "rare",
    "Душа": "legendary",
}


def fake_item_by_name(name):
    rarity = ARTIFACT_FIXTURE.get(name)
    if not rarity:
        return None
    return {"name": name, "category": "artifacts", "rarity": rarity}


class AnomalyLocationBalanceTests(unittest.TestCase):
    def test_roads_do_not_have_anomaly_pool(self):
        self.assertFalse(location_has_anomalies("дорога_военная_часть"))
        self.assertFalse(location_has_anomalies("дорога_нии"))
        self.assertFalse(location_has_anomalies("дорога_зараженный_лес"))
        self.assertIsNone(get_random_anomaly_for_location("дорога_зараженный_лес"))

    def test_internal_location_has_strict_anomaly_pool(self):
        allowed = get_location_anomaly_types("зараженный_лес")

        self.assertIn("кислотная топь", allowed)
        self.assertIn("огненный разлом", allowed)
        self.assertNotIn("электрошквал", allowed)

    def test_fractional_rare_chance_is_kept_for_location_anomaly(self):
        chances = get_anomaly_rarity_chances("главный_корпус_нии", "воронка")

        self.assertEqual(chances["rare"], 18.5)
        self.assertEqual(chances["legendary"], 0.0)

    def test_zero_legendary_chance_blocks_legendary_artifact(self):
        seen_candidates = []

        def choose_first(candidates):
            seen_candidates.extend(item["name"] for item in candidates)
            return candidates[0]

        with patch("infra.database.get_item_by_name", side_effect=fake_item_by_name), \
                patch("random.randint", return_value=1), \
                patch("random.uniform", return_value=99.99), \
                patch("random.choice", side_effect=choose_first):
            result = roll_artifact_from_anomaly(
                "пси-поле",
                luck=1,
                detector_bonus=0,
                location_id="военная_часть",
            )

        self.assertIsNotNone(result)
        self.assertEqual(result["rarity"], "rare")
        self.assertNotIn("Душа", seen_candidates)


if __name__ == "__main__":
    unittest.main()
