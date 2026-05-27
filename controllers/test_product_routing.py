"""Unit tests for product routing registry."""

import sys
import unittest

sys.path.insert(0, "controllers")
import product_routing as routing


class TestProductRouting(unittest.TestCase):
    def test_box_round_robin_routes(self):
        routes = [routing.route_for_box_def(f"SPAWNED_BOX_{i}")["def"] for i in range(4)]
        self.assertEqual(
            routes,
            ["BEER_STOCK", "CHIPS_STOCK", "CHEESE_STOCK", "MILK_STOCK"],
        )

    def test_box_routes_by_product_id(self):
        route = routing.route_for_box_def("SPAWNED_BOX_0", product_id="MILK")
        self.assertEqual(route["def"], "MILK_STOCK")
        self.assertEqual(route["product_id"], "MILK")

    def test_four_pallet_defs_exist(self):
        self.assertEqual(len(routing.STOCK_PALLETS), 4)
        self.assertIn("BEER_STOCK", routing.STOCK_PALLETS)
        self.assertIn("MILK_STOCK", routing.STOCK_PALLETS)

    def test_box_on_beer_pallet(self):
        pos = [-10.5, 1.83, 0.15]
        self.assertTrue(routing.box_on_pallet(pos, "BEER_STOCK"))
        self.assertFalse(routing.box_on_pallet(pos, "MILK_STOCK"))

    def test_pallet_approach_xy(self):
        approach = routing.pallet_approach_xy("BEER_STOCK")
        self.assertEqual(approach, [-11.0, 1.83])

    def test_shelf_base_for_beer(self):
        base = routing.shelf_base_for_product("BEER_BOTTLE")
        self.assertEqual(base, [-11.5, 2.7, 0.0])

    def test_shelf_bases_all_products(self):
        self.assertEqual(routing.shelf_base_for_product("CHIPS"), [-11.5, 4.35, 0.0])
        self.assertEqual(routing.shelf_base_for_product("MILK"), [-11.5, 7.9, 0.0])
        self.assertEqual(routing.shelf_base_for_product("CHEESE"), [-11.5, 6.1, 0.0])

    def test_pallet_obstacle_centers(self):
        centers = routing.pallet_obstacle_centers()
        self.assertEqual(len(centers), 4)


def run_tests():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(stream=sys.stdout, verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(run_tests())
