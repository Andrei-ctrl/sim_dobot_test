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
import restocking_task_manager as task_mgr  # noqa: E402
import shelf_monitoring_logic as shelf_mon  # noqa: E402
import sort_signal  # noqa: E402
import spawn_signal  # noqa: E402

TIME_STEP = 32
CHECK_EVERY_STEPS = 48
BASELINE_WAIT_STEPS = 100
DASHBOARD_URL = "http://127.0.0.1:8000/update"
SEND_TO_DASHBOARD = True


class RestockingTaskManagerDemo:
    def __init__(self):
        self.robot = Supervisor()
        self.project_root = project_paths.project_root_from_controller_file(__file__)
        self.step = 0
        self.state = task_mgr.load_state(self.project_root)
        self.baseline_counts = dict(self.state.get("baseline_shelf_counts") or {})
        self.baseline_locked = False
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
            self.state.setdefault("last_pallet_spawn_time", {})[product_id] = sim_time
            print(
                f"[TASK MANAGER] IPR spawn request seq={payload['seq']} "
                f"product={product_id} pallet={action.get('pallet_def')} "
                f"(current={action.get('current_count')}, target={action.get('target_count')})"
            )
            print(f"[TASK MANAGER]   reason: {action.get('reason', '')}")
            return payload
        return None

    def tick(self):
        sim_time = self.robot.getTime()
        shelf_counts = self.read_shelf_counts()

        if not self.baseline_locked:
            if not self.try_lock_baseline(shelf_counts):
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
        actions.extend(
            task_mgr.evaluate_restock_needs(
                self.project_root,
                shelf_counts,
                self.baseline_counts,
                inventory,
                sim_time,
                self.state,
                get_from_def=self.get_from_def,
            )
        )

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

        dashboard = task_mgr.dashboard_payload(
            self.project_root,
            sim_time,
            shelf_counts,
            self.baseline_counts,
            inventory,
            event=event,
        )
        task_mgr.publish_system_state(self.project_root, dashboard)
        self.post_dashboard({"source": "task_manager", **dashboard})

    def run(self):
        while self.robot.step(TIME_STEP) != -1:
            self.tick()
            self.step += 1


if __name__ == "__main__":
    RestockingTaskManagerDemo().run()
