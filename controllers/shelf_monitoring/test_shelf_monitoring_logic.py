"""Unit tests for shelf_monitoring_logic."""

import sys
import unittest

sys.path.insert(0, "controllers")
sys.path.insert(0, "controllers/youbot_sorter_demo")
sys.path.insert(0, "controllers/shelf_monitoring")
import shelf_monitoring_logic as logic


def beer_slot(index):
    import youbot_sorter_logic as sorter_logic

    return sorter_logic.BEER_SHELF_ALL_SLOTS[index]


class TestShelfMonitoringLogic(unittest.TestCase):
    def test_full_beer_bottom_row(self):
        entries = [
            (0, "BeerBottle", beer_slot(6)),
            (1, "BeerBottle", beer_slot(7)),
            (2, "BeerBottle", beer_slot(8)),
        ]
        self.assertEqual(logic.count_items_for_product(entries, "BEER_BOTTLE"), 3)

    def test_beer_missing_middle_row(self):
        entries = [
            (0, "BeerBottle", beer_slot(0)),
            (1, "BeerBottle", beer_slot(1)),
            (2, "BeerBottle", beer_slot(2)),
            (3, "BeerBottle", beer_slot(6)),
            (4, "BeerBottle", beer_slot(7)),
            (5, "BeerBottle", beer_slot(8)),
        ]
        self.assertEqual(logic.count_items_for_product(entries, "BEER_BOTTLE"), 6)

    def test_ignores_items_outside_shelf_bank(self):
        entries = [(0, "BeerBottle", [-10.0, 0.5, 0.8])]
        self.assertEqual(logic.count_items_for_product(entries, "BEER_BOTTLE"), 0)

    def test_count_all_products(self):
        entries = [
            (0, "BeerBottle", beer_slot(0)),
            (1, "ChipsPack", [-11.5697, 4.56, 0.12]),
        ]
        counts = logic.count_all_products(entries)
        self.assertEqual(counts["BEER_BOTTLE"], 1)
        self.assertIn("CHIPS", counts)

    def test_shelf_full_at_nine_beers(self):
        self.assertTrue(logic.shelf_is_full(9, "BEER_BOTTLE"))
        self.assertFalse(logic.can_accept_sort(9, "BEER_BOTTLE"))
        self.assertTrue(logic.can_accept_sort(6, "BEER_BOTTLE"))

    def test_shelf_capacity_summary(self):
        counts = {"BEER_BOTTLE": 9, "MILK": 6}
        summary = logic.shelf_capacity_summary(counts)
        self.assertTrue(summary["BEER_BOTTLE"]["full"])
        self.assertEqual(summary["BEER_BOTTLE"]["free_slots"], 0)
        self.assertFalse(summary["MILK"]["full"])
        self.assertEqual(summary["MILK"]["free_slots"], 3)


if __name__ == "__main__":
    unittest.main()
