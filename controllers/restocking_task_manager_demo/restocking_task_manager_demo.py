"""Webots supervisor: monitor shelves + inventory, enqueue sort/restock tasks."""

import json
import os
import sys
import urllib.error
import urllib.request

from controller import Supervisor

_CONTROLLERS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SHELF_MON_DIR = os.path.join(_CONTROLLERS_DIR, "shelf_monitoring")
for path in (_CONTROLLERS_DIR, _SHELF_MON_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import project_paths  # noqa: E402
import product_routing  # noqa: E402
import restocking_task_manager as task_mgr  # noqa: E402
import shelf_monitoring_logic as shelf_mon  # noqa: E402
import sort_signal  # noqa: E402
import spawn_signal  # noqa: E402
import sim_session  # noqa: E402
import dashboard_client  # noqa: E402

TIME_STEP = 32
CHECK_EVERY_STEPS = 48
BASELINE_WAIT_STEPS = 100
PALLET_SYNC_STEPS = 156
PALLET_SYNC_CONFIRM_STEPS = 48
PALLET_SYNC_MAX_WAIT_STEPS = 312
DASHBOARD_URL = "http://127.0.0.1:8000/update"
SEND_TO_DASHBOARD = True


class RestockingTaskManagerDemo:
    def __init__(self):
        self.robot = Supervisor()
        self.project_root = project_paths.project_root_from_controller_file(__file__)
        self.step = 0
        self.state = task_mgr.load_state(self.project_root)
        self.run_id = sim_session.begin_run(self.project_root)
        self.state["last_pallet_spawn_time"] = {}
        self.state["awaiting_conveyor_scan"] = {}
        self.state["last_pallet_scan_time"] = {}
        self.state["last_conveyor_scan_seq"] = 0
        spawn_signal.clear_signal(self.project_root)
        task_mgr.save_state(self.project_root, self.state)
        self.baseline_counts = dict(self.state.get("baseline_shelf_counts") or {})
        self.baseline_locked = False
        self.pallet_synced = False
        self.pallet_counts_snapshot = None
        self.last_shelf_counts = {}
        self.sim_start_time = self.robot.getTime()

        os.makedirs(task_mgr.data_dir(self.project_root), exist_ok=True)
        if not os.path.isfile(task_mgr.restock_queue_path(self.project_root)):
            task_mgr.save_restock_queue(self.project_root, [])

        print("[TASK MANAGER] RestockingTaskManager started")
        print("[TASK MANAGER] Front-shelf rule: trigger sorter when >=1 row missing")
        print(
            f"[TASK MANAGER] Stock pallet rule: replenish via IPR when "
            f"<{task_mgr.PALLET_MIN_BOXES} boxes (target {task_mgr.PALLET_TARGET_BOXES})"
        )
        print("[TASK MANAGER] Shelf counts source: shelf_monitoring -> data/shelf_counts.json")
        print(f"[TASK MANAGER] Sort queue: {sort_signal.queue_path(self.project_root)}")
        print(f"[TASK MANAGER] Sim run id={self.run_id} (spawn cooldowns reset)")

    def get_from_def(self, name):
        return self.robot.getFromDef(name)

    def post_dashboard(self, payload):
        if not SEND_TO_DASHBOARD:
            return
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            DASHBOARD_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=0.4) as response:
                response.read()
        except (urllib.error.URLError, TimeoutError, OSError):
            pass

    def read_shelf_counts(self):
        return shelf_mon.read_counts(self.project_root)

    def try_lock_baseline(self, shelf_counts):
        baseline = shelf_mon.read_baseline_counts(self.project_root)
        if baseline and sum(baseline.values()) > 0:
            self.baseline_counts = dict(baseline)
        elif self.step >= BASELINE_WAIT_STEPS and sum(shelf_counts.values()) > 0:
            self.baseline_counts = dict(shelf_counts)
        else:
            return False

        self.state["baseline_shelf_counts"] = dict(self.baseline_counts)
        self.state["last_shelf_counts"] = dict(shelf_counts)
        task_mgr.save_state(self.project_root, self.state)
        self.baseline_locked = True
        print("[TASK MANAGER] Baseline shelf counts (from shelf_monitoring):")
        for product_id, count in self.baseline_counts.items():
            rows = task_mgr.rows_on_shelf(count)
            print(f"  {product_id}: {count} items ({rows} rows)")
        return True

    def apply_action(self, action, sim_time):
        product_id = action["product_id"]
        if action["kind"] == "sort":
            payload = task_mgr.create_sort_task(
                self.project_root,
                product_id,
                sim_time,
                box_def=action.get("box_def", ""),
                task_type="front_restock",
                reason=action.get("reason", ""),
            )
            self.state.setdefault("last_trigger_time", {})[product_id] = sim_time
            print(
                f"[TASK MANAGER] Sort task seq={payload['seq']} "
                f"product={product_id} type=front_restock "
                f"box={payload.get('box_def') or '(sorter will scan pallet)'}"
            )
            print(f"[TASK MANAGER]   reason: {action.get('reason', '')}")
            return payload

        if action["kind"] == "restock":
            task = task_mgr.append_restock_task(
                self.project_root,
                product_id,
                sim_time,
                reason=action.get("reason", ""),
            )
            self.state.setdefault("last_trigger_time", {})[product_id] = sim_time
            print(
                f"[TASK MANAGER] Restock queue seq={task['seq']} "
                f"product={product_id} (no stock pallet box / storage empty)"
            )
            return task

        if action["kind"] == "spawn_box":
            payload = task_mgr.create_spawn_request(
                self.project_root,
                product_id,
                sim_time,
                reason=action.get("reason", ""),
            )
            task_mgr.mark_pallet_spawn_ordered(self.state, product_id)
            print(
                f"[TASK MANAGER] IPR spawn request seq={payload['seq']} "
                f"product={product_id} pallet={action.get('pallet_def')} "
                f"(current={action.get('current_count')}, target={action.get('target_count')})"
            )
            print(f"[TASK MANAGER]   reason: {action.get('reason', '')}")
            print(
                f"[TASK MANAGER]   waiting for {product_id} box on conveyor scanner "
                f"before next order (+{task_mgr.SPAWN_ORDER_COOLDOWN_SEC:.0f}s)"
            )
            return payload
        return None

    def sync_pallet_state(self, sim_time):
        task_mgr.sync_pallet_stock_state(self.get_from_def, self.state)
        counts = task_mgr.count_all_pallet_boxes(self.get_from_def)
        task_mgr.save_state(self.project_root, self.state)
        if not self.state.get("pallet_replenish_target"):
            spawn_signal.clear_signal(self.project_root)
        print(f"[TASK MANAGER] Pallet box sync at t={sim_time:.2f}s: {counts}")
        for pallet_def in product_routing.iter_pallet_defs():
            boxes = task_mgr.list_boxes_on_pallet(self.get_from_def, pallet_def)
            if boxes:
                print(f"[TASK MANAGER]   {pallet_def}: {', '.join(boxes)}")
        self.pallet_synced = True
        self.apply_pallet_replenish_orders(sim_time)
        self.publish_dashboard(sim_time, self.read_shelf_counts())

    def publish_dashboard(self, sim_time, shelf_counts, event=None, threshold_events=None):
        inventory = task_mgr.load_inventory(self.project_root)
        inventory = task_mgr.sync_front_stock_from_shelves(inventory, shelf_counts)
        pallet_counts = task_mgr.pallet_counts_by_product(self.get_from_def)
        task_mgr.save_pallet_counts(
            self.project_root,
            pallet_counts,
            sim_time,
            source="task_manager",
        )

        shelf_capacity = None
        shelf_file = shelf_mon.shelf_counts_path(self.project_root)
        try:
            with open(shelf_file, encoding="utf-8") as handle:
                shelf_capacity = json.load(handle).get("capacity")
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass

        if threshold_events is None:
            threshold_events = task_mgr.collect_threshold_events(
                shelf_counts,
                self.baseline_counts,
                inventory,
                pallet_counts,
            )

        dashboard = task_mgr.dashboard_payload(
            self.project_root,
            sim_time,
            shelf_counts,
            self.baseline_counts,
            inventory,
            event=event,
            pallet_counts=pallet_counts,
            shelf_capacity=shelf_capacity,
            threshold_events=threshold_events,
        )
        task_mgr.publish_system_state(self.project_root, dashboard)
        if SEND_TO_DASHBOARD:
            dashboard_client.post_update({"source": "task_manager", **dashboard})

    def apply_pallet_replenish_orders(self, sim_time):
        actions = task_mgr.evaluate_pallet_stock_needs(
            self.project_root,
            self.get_from_def,
            sim_time,
            self.state,
        )
        for action in actions:
            if action["kind"] != "spawn_box":
                continue
            self.apply_action(action, sim_time)
        if actions:
            task_mgr.save_state(self.project_root, self.state)

    def tick(self):
        sim_time = self.robot.getTime()
        task_mgr.process_conveyor_scans(self.project_root, self.state, sim_time)
        shelf_counts = self.read_shelf_counts()

        if not self.baseline_locked:
            if not self.try_lock_baseline(shelf_counts):
                return

        if not self.pallet_synced:
            if self.step == PALLET_SYNC_STEPS:
                self.pallet_counts_snapshot = task_mgr.count_all_pallet_boxes(
                    self.get_from_def
                )
                return
            if self.step >= PALLET_SYNC_STEPS + PALLET_SYNC_CONFIRM_STEPS:
                confirm = task_mgr.count_all_pallet_boxes(self.get_from_def)
                snapshot = self.pallet_counts_snapshot or {}
                if (
                    snapshot != confirm
                    and self.step < PALLET_SYNC_MAX_WAIT_STEPS
                ):
                    print(
                        "[TASK MANAGER] Pallet counts still settling "
                        f"(was {snapshot}, now {confirm}) — waiting"
                    )
                    self.pallet_counts_snapshot = confirm
                    return
                self.sync_pallet_state(sim_time)
            else:
                return

        if self.step % CHECK_EVERY_STEPS != 0:
            return

        self.last_shelf_counts = shelf_counts
        inventory = task_mgr.load_inventory(self.project_root)
        inventory = task_mgr.sync_front_stock_from_shelves(inventory, shelf_counts)

        actions = task_mgr.evaluate_pallet_stock_needs(
            self.project_root,
            self.get_from_def,
            sim_time,
            self.state,
        )
        skip_log = []
        actions.extend(
            task_mgr.evaluate_restock_needs(
                self.project_root,
                shelf_counts,
                self.baseline_counts,
                inventory,
                sim_time,
                self.state,
                get_from_def=self.get_from_def,
                skip_log=skip_log,
            )
        )

        pallet_counts = task_mgr.pallet_counts_by_product(self.get_from_def)
        threshold_events = task_mgr.collect_threshold_events(
            shelf_counts,
            self.baseline_counts,
            inventory,
            pallet_counts,
        )
        for entry in skip_log:
            dashboard_client.append_threshold_log(self.project_root, entry)

        event = None
        for action in actions:
            result = self.apply_action(action, sim_time)
            event = {
                "event": "task_created",
                "kind": action["kind"],
                "product_id": action["product_id"],
                "reason": action.get("reason", ""),
                "seq": result.get("seq") if result else None,
                "t": sim_time,
            }

        if actions:
            task_mgr.save_state(self.project_root, self.state)

        if event is None and threshold_events:
            event = {**threshold_events[0], "t": sim_time}

        self.publish_dashboard(
            sim_time, shelf_counts, event=event, threshold_events=threshold_events
        )

    def run(self):
        while self.robot.step(TIME_STEP) != -1:
            self.tick()
            self.step += 1


if __name__ == "__main__":
    RestockingTaskManagerDemo().run()
