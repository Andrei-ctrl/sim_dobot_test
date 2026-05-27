"""Unit tests for RestockingTaskManager logic."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, "controllers")
import product_routing
import restocking_task_manager as mgr
import sort_signal


class TestShelfRowLogic(unittest.TestCase):
    def test_missing_one_row(self):
        self.assertTrue(mgr.shelf_needs_restock(baseline_count=9, current_count=6))
        self.assertEqual(mgr.missing_row_count(9, 6), 1)

    def test_missing_two_items_not_a_row(self):
        self.assertFalse(mgr.shelf_needs_restock(baseline_count=9, current_count=7))
        self.assertEqual(mgr.missing_row_count(9, 7), 0)

    def test_missing_two_rows(self):
        self.assertEqual(mgr.missing_row_count(9, 3), 2)

    def test_zero_baseline_never_triggers(self):
        self.assertFalse(mgr.shelf_needs_restock(0, 0))


class TestInventoryThreshold(unittest.TestCase):
    def test_below_threshold_with_storage(self):
        inv = {"BEER_BOTTLE": {"front_stock": 1, "threshold": 2, "storage_stock": 10}}
        self.assertTrue(mgr.inventory_needs_restock(inv, "BEER_BOTTLE"))

    def test_at_threshold_no_trigger(self):
        inv = {"BEER_BOTTLE": {"front_stock": 2, "threshold": 2, "storage_stock": 10}}
        self.assertFalse(mgr.inventory_needs_restock(inv, "BEER_BOTTLE"))

    def test_no_storage_no_trigger(self):
        inv = {"BEER_BOTTLE": {"front_stock": 0, "threshold": 2, "storage_stock": 0}}
        self.assertFalse(mgr.inventory_needs_restock(inv, "BEER_BOTTLE"))


class TestPalletStockLogic(unittest.TestCase):
    def test_count_boxes_on_pallet(self):
        pallet = "BEER_STOCK"
        px, py, _ = product_routing.pallet_translation(pallet)

        def get_from_def(name):
            if name == "SPAWNED_BOX_0":
                node = mock.MagicMock()
                node.getField.return_value.getSFVec3f.return_value = [px, py, 0.22]
                return node
            return None

        self.assertEqual(mgr.count_boxes_on_pallet(get_from_def, pallet), 1)

    def test_verify_restock_increase(self):
        pallet = "MILK_STOCK"
        px, py, _ = product_routing.pallet_translation(pallet)
        counts = {"SPAWNED_BOX_0": False, "SPAWNED_BOX_1": False}

        def get_from_def(name):
            if name not in counts:
                return None
            node = mock.MagicMock()
            if counts[name]:
                node.getPosition.return_value = [px, py, 0.22]
            else:
                node.getPosition.return_value = [0.0, 0.0, 0.22]
            return node

        ok, after, delta = mgr.verify_restock_increase(get_from_def, pallet, 0)
        self.assertFalse(ok)
        self.assertEqual(after, 0)
        self.assertEqual(delta, 0)

        counts["SPAWNED_BOX_1"] = True
        ok, after, delta = mgr.verify_restock_increase(get_from_def, pallet, 0)
        self.assertTrue(ok)
        self.assertEqual(after, 1)
        self.assertEqual(delta, 1)

    def test_box_delivered_to_pallet(self):
        pallet = "BEER_STOCK"
        px, py, _ = product_routing.pallet_translation(pallet)

        def get_from_def(name):
            if name != "SPAWNED_BOX_0":
                return None
            node = mock.MagicMock()
            node.getPosition.return_value = [px, py, 0.22]
            return node

        ok, reason = mgr.box_delivered_to_pallet(get_from_def, "SPAWNED_BOX_0", pallet)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

        ok, reason = mgr.box_delivered_to_pallet(get_from_def, "SPAWNED_BOX_0", "MILK_STOCK")
        self.assertFalse(ok)
        self.assertEqual(reason, "not_on_pallet")

        ok, reason = mgr.box_delivered_to_pallet(get_from_def, "SPAWNED_BOX_9", pallet)
        self.assertFalse(ok)
        self.assertEqual(reason, "box_removed")

    def test_replenish_when_below_min(self):
        def get_from_def(_name):
            return None

        state = {"pallet_ever_full": {"BEER_BOTTLE": True, "CHIPS": True, "CHEESE": True, "MILK": True}}
        actions = mgr.evaluate_pallet_stock_needs(
            ".",
            get_from_def,
            sim_time=100.0,
            state=state,
        )
        self.assertTrue(actions)
        self.assertTrue(all(action["kind"] == "spawn_box" for action in actions))
        self.assertEqual(state["pallet_replenish_target"]["BEER_BOTTLE"], 5)

    def test_no_replenish_when_at_target(self):
        pallet = "BEER_STOCK"
        px, py, _ = product_routing.pallet_translation(pallet)

        def get_from_def(name):
            index = int(name.rsplit("_", 1)[-1])
            if index >= 5:
                return None
            node = mock.MagicMock()
            node.getField.return_value.getSFVec3f.return_value = [px, py, 0.22 + index * 0.05]
            return node

        state = {}
        beer_count = mgr.count_boxes_for_product(get_from_def, "BEER_BOTTLE")
        self.assertEqual(beer_count, 5)
        actions = [
            action
            for action in mgr.evaluate_pallet_stock_needs(
                ".",
                get_from_def,
                sim_time=100.0,
                state=state,
            )
            if action["product_id"] == "BEER_BOTTLE"
        ]
        self.assertEqual(actions, [])

    def test_sync_clears_stale_replenish_when_full(self):
        pallet = "MILK_STOCK"
        px, py, _ = product_routing.pallet_translation(pallet)

        def get_from_def(name):
            index = int(name.rsplit("_", 1)[-1])
            if index >= 5:
                return None
            node = mock.MagicMock()
            node.getField.return_value.getSFVec3f.return_value = [px, py, 0.22 + index * 0.05]
            return node

        state = {
            "pallet_replenish_target": {"MILK": 5},
            "pallet_ever_full": {"MILK": True},
            "last_pallet_spawn_time": {"MILK": 0.032},
        }
        mgr.sync_pallet_stock_state(get_from_def, state)
        self.assertNotIn("MILK", state["pallet_replenish_target"])
        self.assertNotIn("MILK", state["last_pallet_spawn_time"])
        actions = mgr.evaluate_pallet_stock_needs(
            ".",
            get_from_def,
            sim_time=100.0,
            state=state,
        )
        self.assertEqual(actions, [])

    def test_no_replenish_during_warmup(self):
        state = {"pallet_ever_full": {"MILK": True}, "pallet_replenish_target": {"MILK": 5}}

        def get_from_def(_name):
            return None

        actions = mgr.evaluate_pallet_stock_needs(
            ".",
            get_from_def,
            sim_time=0.5,
            state=state,
        )
        self.assertEqual(actions, [])

    def test_first_spawn_allowed_without_prior_scan(self):
        state = {"pallet_ever_full": {"CHEESE": True}, "pallet_replenish_target": {"CHEESE": 5}}
        self.assertTrue(mgr.pallet_spawn_cooldown_elapsed(state, "CHEESE", sim_time=10.0))

    def test_blocks_while_awaiting_conveyor_scan(self):
        state = {
            "pallet_ever_full": {"CHEESE": True},
            "awaiting_conveyor_scan": {"CHEESE": True},
            "last_pallet_scan_time": {"CHEESE": 5.0},
        }
        self.assertFalse(mgr.pallet_spawn_cooldown_elapsed(state, "CHEESE", sim_time=60.0))

    def test_requires_fifty_seconds_after_scan(self):
        state = {
            "pallet_ever_full": {"CHEESE": True},
            "awaiting_conveyor_scan": {"CHEESE": False},
            "last_pallet_scan_time": {"CHEESE": 100.0},
        }
        self.assertFalse(mgr.pallet_spawn_cooldown_elapsed(state, "CHEESE", sim_time=140.0))
        self.assertTrue(mgr.pallet_spawn_cooldown_elapsed(state, "CHEESE", sim_time=150.0))


class TestEvaluateRestockNeeds(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "data"), exist_ok=True)
        self.inventory = {
            "BEER_BOTTLE": {"front_stock": 4, "threshold": 2, "storage_stock": 20},
            "CHIPS": {"front_stock": 4, "threshold": 2, "storage_stock": 20},
        }
        mgr.save_inventory(self.tmp, self.inventory)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sort_when_row_missing_and_storage(self):
        actions = mgr.evaluate_restock_needs(
            self.tmp,
            shelf_counts={"BEER_BOTTLE": 6, "CHIPS": 9},
            baseline_counts={"BEER_BOTTLE": 9, "CHIPS": 9},
            inventory=self.inventory,
            sim_time=100.0,
            state={"last_trigger_time": {}},
        )
        kinds = {a["product_id"]: a["kind"] for a in actions}
        self.assertEqual(kinds["BEER_BOTTLE"], "sort")
        self.assertNotIn("CHIPS", kinds)

    def test_restock_when_no_storage_and_no_box(self):
        inv = dict(self.inventory)
        inv["BEER_BOTTLE"] = {"front_stock": 0, "threshold": 2, "storage_stock": 0}
        actions = mgr.evaluate_restock_needs(
            self.tmp,
            shelf_counts={"BEER_BOTTLE": 6},
            baseline_counts={"BEER_BOTTLE": 9},
            inventory=inv,
            sim_time=100.0,
            state={"last_trigger_time": {}},
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["kind"], "restock")

    def test_skips_when_sort_task_open(self):
        sort_signal.write_signal(
            self.tmp,
            product_id="BEER_BOTTLE",
            source_pallet="BEER_PALLET",
            cube_count=3,
            units_per_cube=2,
            sim_time=1.0,
            task_type="front_restock",
        )
        actions = mgr.evaluate_restock_needs(
            self.tmp,
            shelf_counts={"BEER_BOTTLE": 6},
            baseline_counts={"BEER_BOTTLE": 9},
            inventory=self.inventory,
            sim_time=100.0,
            state={"last_trigger_time": {}},
        )
        self.assertEqual(actions, [])

    def test_respects_cooldown(self):
        actions = mgr.evaluate_restock_needs(
            self.tmp,
            shelf_counts={"BEER_BOTTLE": 6},
            baseline_counts={"BEER_BOTTLE": 9},
            inventory=self.inventory,
            sim_time=5.0,
            state={"last_trigger_time": {"BEER_BOTTLE": 0.0}},
        )
        self.assertEqual(actions, [])

    def test_sort_on_inventory_threshold_without_full_row(self):
        """Inventory low but shelf has <3 free slots — no sort (need room for one box)."""
        inv = dict(self.inventory)
        inv["BEER_BOTTLE"] = {
            "front_stock": 16,
            "threshold": 20,
            "storage_stock": 10,
        }
        skip_log = []
        actions = mgr.evaluate_restock_needs(
            self.tmp,
            shelf_counts={"BEER_BOTTLE": 8},
            baseline_counts={"BEER_BOTTLE": 9},
            inventory=inv,
            sim_time=100.0,
            state={"last_trigger_time": {}},
            skip_log=skip_log,
        )
        self.assertEqual(actions, [])
        self.assertTrue(any(s.get("reason", "").startswith("no room") for s in skip_log))


class TestTaskCreation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "data"), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_sort_task_fields(self):
        payload = mgr.create_sort_task(
            self.tmp,
            "BEER_BOTTLE",
            sim_time=12.5,
            task_type="front_restock",
            reason="missing 1 row(s)",
        )
        self.assertEqual(payload["task_type"], "front_restock")
        self.assertEqual(payload["reason"], "missing 1 row(s)")
        self.assertEqual(payload["triggered_by"], "task_manager")
        queue = sort_signal.read_queue(self.tmp)
        self.assertEqual(len(queue), 1)

    def test_append_restock_task(self):
        task = mgr.append_restock_task(
            self.tmp, "MILK", sim_time=3.0, reason="no stock"
        )
        self.assertEqual(task["task_type"], "pallet_restock")
        path = mgr.restock_queue_path(self.tmp)
        with open(path, encoding="utf-8") as handle:
            queue = json.load(handle)
        self.assertEqual(len(queue), 1)


class TestSortSignalReset(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "data"), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_reset_preserves_queue_by_default(self):
        sort_signal.write_signal(
            self.tmp,
            product_id="BEER_BOTTLE",
            source_pallet="BEER_PALLET",
            cube_count=3,
            units_per_cube=2,
            sim_time=1.0,
        )
        sort_signal.reset_signal(self.tmp)
        self.assertEqual(len(sort_signal.read_queue(self.tmp)), 1)

    def test_reset_can_clear_queue(self):
        sort_signal.write_signal(
            self.tmp,
            product_id="BEER_BOTTLE",
            source_pallet="BEER_PALLET",
            cube_count=3,
            units_per_cube=2,
            sim_time=1.0,
        )
        sort_signal.reset_signal(self.tmp, clear_queue=True)
        self.assertEqual(sort_signal.read_queue(self.tmp), [])

    def test_mark_task_done_baseline(self):
        sort_signal.write_signal(
            self.tmp,
            product_id="BEER_BOTTLE",
            source_pallet="BEER_STOCK",
            cube_count=3,
            units_per_cube=2,
            sim_time=1.0,
            triggered_by="task_manager",
            task_type="front_restock",
        )
        sort_signal.mark_task_done(self.tmp, 1)
        self.assertEqual(sort_signal.last_completed_seq(self.tmp), 1)
        pending = sort_signal.pending_tasks(self.tmp, 1)
        self.assertEqual(pending, [])

    def test_skip_open_tasks_for_product(self):
        sort_signal.write_signal(
            self.tmp,
            product_id="MILK",
            source_pallet="MILK_STOCK",
            cube_count=3,
            units_per_cube=2,
            sim_time=1.0,
            triggered_by="stock_monitoring",
            task_type="stock_pallet",
        )
        sort_signal.write_signal(
            self.tmp,
            product_id="MILK",
            source_pallet="MILK_STOCK",
            cube_count=3,
            units_per_cube=2,
            sim_time=2.0,
            triggered_by="stock_monitoring",
            task_type="stock_pallet",
        )
        sort_signal.write_signal(
            self.tmp,
            product_id="BEER_BOTTLE",
            source_pallet="BEER_STOCK",
            cube_count=3,
            units_per_cube=2,
            sim_time=3.0,
            triggered_by="task_manager",
            task_type="front_restock",
        )
        n = sort_signal.skip_open_tasks_for_product(self.tmp, "MILK")
        self.assertEqual(len(n), 2)
        pending = sort_signal.pending_tasks(self.tmp, 0)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["product_id"], "BEER_BOTTLE")
        for t in sort_signal.read_queue(self.tmp):
            if t.get("product_id") == "MILK":
                self.assertEqual(t.get("status"), "skipped_full")


if __name__ == "__main__":
    unittest.main()
