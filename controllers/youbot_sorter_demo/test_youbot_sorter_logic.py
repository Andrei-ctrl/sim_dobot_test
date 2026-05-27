"""Unit tests for youBot sorter product-bottle logic."""

import math
import sys
import unittest

sys.path.insert(0, "controllers/youbot_sorter_demo")
sys.path.insert(0, "controllers")
import youbot_mecanum as mecanum
import youbot_sorter_logic as logic


def log(label, detail=""):
    print(f"  [{label}] {detail}")


class TestCubeConstants(unittest.TestCase):
    def test_inventory_delta_three_bottles(self):
        delta = logic.inventory_delta(3)
        log("inventory delta", f"3 bottles -> +{delta}")
        self.assertEqual(delta, 6)

    def test_inventory_delta_custom_units(self):
        delta = logic.inventory_delta(3, units_per_cube=1)
        self.assertEqual(delta, 3)

    def test_bottles_per_box(self):
        self.assertEqual(logic.BOTTLES_PER_BOX, 3)
        self.assertEqual(logic.CUBES_PER_BOX, logic.BOTTLES_PER_BOX)


class TestSignalParsing(unittest.TestCase):
    def test_should_process_new_signal(self):
        signal = {
            "seq": 2,
            "product_id": "BEER_BOTTLE",
            "box_def": "SPAWNED_BOX_0",
            "cube_count": 3,
            "units_per_cube": 2,
            "cube_defs": [],
        }
        ok, parsed = logic.should_process_signal(signal, last_seq=1)
        log("process new signal", str(ok))
        self.assertTrue(ok)
        self.assertEqual(parsed["seq"], 2)
        self.assertEqual(parsed["product_id"], "BEER_BOTTLE")

    def test_parse_task_type_fields(self):
        signal = {
            "seq": 1,
            "product_id": "BEER_BOTTLE",
            "cube_count": 3,
            "task_type": "front_restock",
            "reason": "missing 1 row(s)",
            "triggered_by": "task_manager",
        }
        parsed = logic.parse_sort_signal(signal)
        self.assertEqual(parsed["task_type"], "front_restock")
        self.assertEqual(parsed["reason"], "missing 1 row(s)")
        self.assertEqual(parsed["triggered_by"], "task_manager")

    def test_ignore_stale_signal(self):
        signal = {"seq": 1, "product_id": "BEER_BOTTLE", "cube_count": 3}
        ok, _ = logic.should_process_signal(signal, last_seq=1)
        self.assertFalse(ok)

    def test_next_pending_task(self):
        tasks = [
            {"seq": 2, "product_id": "BEER_BOTTLE", "cube_count": 3},
            {"seq": 1, "product_id": "BEER_BOTTLE", "cube_count": 3},
        ]
        task = logic.next_pending_task(tasks, last_seq=0)
        self.assertEqual(task["seq"], 1)


class TestProductSortRoutes(unittest.TestCase):
    def test_four_product_routes_exist(self):
        self.assertEqual(set(logic.PRODUCT_SORT_ROUTES.keys()), {
            "BEER_BOTTLE", "CHIPS", "CHEESE", "MILK"
        })

    def test_beer_route_coordinates(self):
        route = logic.sort_route_for_product("BEER_BOTTLE")
        self.assertEqual(route["pre_pickup"], [-9.38793, 2.59907, 0.0977153])
        self.assertEqual(route["pickup"], [-10.3879, 2.59907, 0.0954989])
        self.assertEqual(route["deposit"], [-11.0279, 2.59907, 0.0940796])

    def test_cheese_pickup_equals_deposit(self):
        route = logic.sort_route_for_product("CHEESE")
        self.assertEqual(route["pickup"], route["deposit"])

    def test_milk_pickup_equals_deposit(self):
        route = logic.sort_route_for_product("MILK")
        self.assertEqual(route["pickup"], route["deposit"])

    def test_axis_waypoints_y_then_x(self):
        points = logic.axis_waypoints(
            [-7.5, 4.6, 0.1],
            [-9.38793, 2.59907, 0.0977153],
        )
        self.assertEqual(points[0][1], 2.59907)
        self.assertEqual(points[-1][0], -9.38793)

    def test_build_pickup_run_steps(self):
        steps = logic.build_nav_steps(
            [-7.5277, 4.58907, 0.101917],
            "BEER_BOTTLE",
            "pickup_run",
        )
        self.assertGreater(len(steps), 0)
        self.assertEqual(steps[-1]["action"], "deposit")
        self.assertIn("Depositing beer on shelf", steps[-1]["log"])

    def test_build_post_next_steps(self):
        steps = logic.build_nav_steps(
            [-11.0279, 2.59907, 0.0940796],
            "BEER_BOTTLE",
            "post_next",
        )
        self.assertEqual(steps[-1]["xyz"], [-10.3879, 2.59907, 0.0954989])
        self.assertIn("Returning for next beer task", steps[-1]["log"])

    def test_build_post_idle_steps(self):
        steps = logic.build_nav_steps(
            [-11.0279, 2.59907, 0.0940796],
            "BEER_BOTTLE",
            "post_idle",
        )
        self.assertEqual(steps[-1]["xyz"], [-9.2979, 2.59907, 0.0979143])
        self.assertIn("Returning to idle/pre-pickup position", steps[-1]["log"])

    def test_nav_log_messages(self):
        self.assertEqual(
            logic.nav_log_message("pre_pickup", "CHIPS"),
            "Moving to chips pre-pickup",
        )
        self.assertEqual(logic.nav_log_message("pickup", "MILK"), "Picking milk")

    def test_is_same_product_task(self):
        self.assertTrue(
            logic.is_same_product_task({"product_id": "CHIPS"}, "CHIPS")
        )
        self.assertFalse(
            logic.is_same_product_task({"product_id": "MILK"}, "CHIPS")
        )


class TestMecanumCardinal(unittest.TestCase):
    def test_cardinal_forward(self):
        vx, vy, omega = mecanum.cardinal_drive_cmd(0.5, 0.0, 0.55)
        self.assertGreater(vx, 0.0)
        self.assertAlmostEqual(vy, 0.0)
        self.assertAlmostEqual(omega, 0.0)

    def test_cardinal_sideways(self):
        vx, vy, omega = mecanum.cardinal_drive_cmd(0.0, -0.4, 0.55)
        self.assertAlmostEqual(vx, 0.0)
        self.assertLess(vy, 0.0)

    def test_cardinal_bearing_detection(self):
        self.assertTrue(mecanum.is_cardinal_bearing(0.0))
        self.assertTrue(mecanum.is_cardinal_bearing(math.pi / 2))
        self.assertFalse(mecanum.is_cardinal_bearing(math.pi / 4))


class TestShelfSlots(unittest.TestCase):
    def test_beer_has_nine_slots(self):
        self.assertEqual(len(logic.BEER_SHELF_ALL_SLOTS), 9)

    def test_all_products_have_nine_slots(self):
        for product_id in ("BEER_BOTTLE", "CHIPS", "MILK", "CHEESE"):
            self.assertEqual(len(logic.PRODUCT_SHELF_ALL_SLOTS[product_id]), 9)

    def test_beer_first_operation_slots(self):
        slots = logic.shelf_slots_for_operation("BEER_BOTTLE", 0)
        self.assertEqual(len(slots), 3)
        self.assertAlmostEqual(slots[0][2], 0.8126949793078967, places=4)

    def test_chips_y_shift_from_beer(self):
        chips = logic.PRODUCT_SHELF_ALL_SLOTS["CHIPS"][0]
        beer = logic.BEER_SHELF_ALL_SLOTS[0]
        self.assertAlmostEqual(chips[1] - beer[1], 4.35 - 2.7, places=2)
        self.assertAlmostEqual(chips[0], beer[0], places=4)
        self.assertAlmostEqual(chips[2], beer[2], places=4)

    def test_milk_first_row_calibrated(self):
        slots = logic.shelf_slots_for_operation("MILK", 0)
        self.assertAlmostEqual(slots[0][1], 8.1500135446762, places=4)
        self.assertAlmostEqual(slots[2][1], 7.650497765754047, places=4)

    def test_cheese_uses_beer_grid_at_61(self):
        slots = logic.shelf_slots_for_operation("CHEESE", 0)
        beer = logic.shelf_slots_for_operation("BEER_BOTTLE", 0)
        self.assertAlmostEqual(slots[0][1] - beer[0][1], 6.1 - 2.7, places=2)

    def test_product_switch_steps(self):
        steps = logic.build_product_switch_steps(
            [-11.0279, 2.59907, 0.094],
            "BEER_BOTTLE",
            "CHIPS",
        )
        self.assertGreater(len(steps), 0)
        self.assertIn("Via beer pre-pickup before product switch", steps[0]["log"])
        self.assertEqual(steps[-1]["action"], "deposit")

    def test_shelf_operation_index(self):
        inv = {"BEER_BOTTLE": {"shelf_operations": 1}}
        self.assertEqual(logic.shelf_operation_index(inv, "BEER_BOTTLE"), 1)
        self.assertTrue(logic.shelf_has_capacity(inv, "BEER_BOTTLE"))

    def test_shelf_item_proto(self):
        self.assertEqual(logic.shelf_item_proto("CHIPS"), "ChipsPack")
        self.assertEqual(logic.shelf_item_proto("MILK"), "MilkCarton")
        self.assertEqual(logic.shelf_item_proto("CHEESE"), "CheeseWedge")
        self.assertEqual(logic.shelf_item_proto("BEER_BOTTLE"), "BeerBottle")

    def test_shelf_full(self):
        inv = {"BEER_BOTTLE": {"shelf_operations": 3}}
        self.assertFalse(logic.shelf_has_capacity(inv, "BEER_BOTTLE"))

    def test_find_empty_middle_row_when_top_and_bottom_full(self):
        slots = logic.BEER_SHELF_ALL_SLOTS
        positions = [
            slots[0],
            slots[1],
            slots[2],
            slots[6],
            slots[7],
            slots[8],
        ]
        row, targets = logic.find_empty_row_placement(positions, "BEER_BOTTLE")
        self.assertEqual(row, 1)
        self.assertEqual(len(targets), 3)
        self.assertAlmostEqual(targets[0][2], slots[3][2], places=4)

    def test_find_empty_top_row_first(self):
        row, targets = logic.find_empty_row_placement([], "BEER_BOTTLE")
        self.assertEqual(row, 0)
        self.assertEqual(len(targets), 3)
        self.assertEqual(logic.shelf_row_label(row), "top")


class TestProductCubes(unittest.TestCase):
    def test_build_shelf_item_strings(self):
        sys.path.insert(0, "controllers")
        import product_cubes

        chips = product_cubes.build_shelf_item_node_string(
            "PRODUCT_CUBE_0", [0, 0, 0.8], "CHIPS"
        )
        self.assertIn("ChipsPack", chips)
        self.assertIn("CHIPS", chips)
        milk = product_cubes.build_shelf_item_node_string(
            "PRODUCT_CUBE_1", [0, 0, 0.8], "MILK"
        )
        self.assertIn("MilkCarton", milk)


class TestPositions(unittest.TestCase):
    def test_shelf_base_from_deposit(self):
        base = logic.shelf_base_for_product("BEER_BOTTLE")
        self.assertEqual(base[0], -11.0279)
        self.assertEqual(base[1], 2.59907)

    def test_platform_world_positions(self):
        robot = [-11.0, 2.6, 0.10]
        yaw = math.pi
        positions = logic.platform_world_positions(robot, yaw)
        self.assertEqual(len(positions), logic.BOTTLES_PER_BOX)

    def test_obstacle_detection(self):
        self.assertFalse(logic.obstacle_blocks_forward(0.0))
        self.assertTrue(logic.obstacle_blocks_forward(900.0))


class TestReserveIndex(unittest.TestCase):
    def test_reserve_from_empty(self):
        nodes = {}

        def get_node(name):
            return nodes.get(name)

        idx = logic.reserve_next_cube_index(get_node)
        self.assertEqual(idx, 0)


def run_tests():
    print("\n" + "=" * 60)
    print("youBot Sorter — unit tests")
    print("=" * 60 + "\n")
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(stream=sys.stdout, verbosity=2)
    result = runner.run(suite)
    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print(f"ALL {result.testsRun} TESTS PASSED")
    else:
        print(f"FAILED: {len(result.failures)} failures, {len(result.errors)} errors")
    print("=" * 60 + "\n")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(run_tests())
