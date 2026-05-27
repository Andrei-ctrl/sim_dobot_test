"""Supervisor: scan front shelves and publish counts for task_manager (no tasks)."""

import json
import os
import sys
import urllib.error
import urllib.request

from controller import Supervisor

_DEMO_DIR = os.path.dirname(os.path.abspath(__file__))
_CONTROLLERS_DIR = os.path.dirname(_DEMO_DIR)
_SORTER_DIR = os.path.join(_CONTROLLERS_DIR, "youbot_sorter_demo")
for path in (_DEMO_DIR, _CONTROLLERS_DIR, _SORTER_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import project_paths  # noqa: E402
import shelf_monitoring_logic as logic  # noqa: E402
import sim_session  # noqa: E402

TIME_STEP = 32
PUBLISH_EVERY_STEPS = 16
BASELINE_SETTLE_STEPS = 80
BASELINE_MAX_WAIT_STEPS = 400
DASHBOARD_URL = "http://127.0.0.1:8000/update"
SEND_TO_DASHBOARD = True

SENSOR_NAMES = (
    "shelf_monitor_beer",
    "shelf_monitor_chips",
    "shelf_monitor_cheese",
    "shelf_monitor_milk",
)


class ShelfMonitoring:
    def __init__(self):
        self.robot = Supervisor()
        self.project_root = project_paths.project_root_from_controller_file(__file__)
        self.step = 0
        self.baseline_counts = {}
        self.peak_counts = {}
        self.baseline_locked = False
        self.baseline_run_id = None
        self.last_counts = {}
        self.last_log_step = 0
        self.scan_debug_logged = False

        self.sensors = {}
        for name in SENSOR_NAMES:
            device = self.robot.getDevice(name)
            if device is not None:
                device.enable(TIME_STEP)
                self.sensors[name] = device

        print("[SHELF MONITORING] Front shelf counter started")
        print(f"[SHELF MONITORING] Project root: {self.project_root}")
        print(
            f"[SHELF MONITORING] Slot match xy={logic.SLOT_XY_RADIUS}m "
            f"z={logic.SLOT_Z_RADIUS}m"
        )
        print(
            f"[SHELF MONITORING] Sensors={list(self.sensors.keys()) or 'scene-scan only'}"
        )
        print(f"[SHELF MONITORING] Output: {logic.shelf_counts_path(self.project_root)}")
        print("[SHELF MONITORING] Observations only — task_manager creates sort tasks")
        beer_slots = logic.slots_for_product("BEER_BOTTLE")
        if beer_slots:
            print(f"[SHELF MONITORING] Slot grid loaded ({len(beer_slots)} beer slots)")
        else:
            print(
                "[SHELF MONITORING WARNING] youbot_sorter_logic not loaded — "
                "shelf counts will be wrong"
            )

    def active_run_id(self):
        return sim_session.current_run_id(self.project_root)

    def node_world_position(self, node):
        """World XYZ for product proto nodes (Pose-derived in Webots)."""
        if node.getTypeName() not in logic.PRODUCT_TYPE_NAMES:
            return None
        try:
            pos = node.getPosition()
            if pos and len(pos) >= 3:
                return [float(pos[0]), float(pos[1]), float(pos[2])]
        except (AttributeError, TypeError, RuntimeError):
            pass
        try:
            pose = node.getPose()
            if pose and len(pose) >= 3:
                return [float(pose[0]), float(pose[1]), float(pose[2])]
        except (AttributeError, TypeError, RuntimeError):
            pass
        field = node.getField("translation")
        if field is not None:
            return list(field.getSFVec3f())
        return None

    def walk_field(self, field, entries, next_index):
        if field is None:
            return next_index
        index = 0
        while True:
            try:
                count = field.getCount()
            except (AttributeError, RuntimeError):
                break
            if index >= count:
                break
            try:
                node = field.getMFNode(index)
            except (AttributeError, RuntimeError):
                index += 1
                continue
            if node is None:
                index += 1
                continue
            type_name = node.getTypeName()
            if type_name in logic.PRODUCT_TYPE_NAMES:
                pos = self.node_world_position(node)
                if pos is not None and logic.in_shelf_bank(pos):
                    entries.append((next_index, type_name, pos))
                    next_index += 1
            try:
                children = node.getField("children")
            except (AttributeError, RuntimeError):
                children = None
            if children is not None:
                next_index = self.walk_field(children, entries, next_index)
            index += 1
        return next_index

    def collect_shelf_nodes(self):
        entries = []
        self.walk_field(self.robot.getRoot().getField("children"), entries, 0)
        if not self.scan_debug_logged:
            self.scan_debug_logged = True
            print(
                f"[SHELF MONITORING] Scene scan found {len(entries)} "
                f"product node(s) in shelf bank"
            )
            for _idx, type_name, pos in entries[:12]:
                print(
                    f"  {type_name} @ ({pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f})"
                )
        return entries

    def load_inventory(self):
        path = os.path.join(self.project_root, "data", "inventory.json")
        try:
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def post_dashboard(self, payload):
        if not SEND_TO_DASHBOARD:
            return
        body = json.dumps({"source": "shelf_monitoring", **payload}).encode("utf-8")
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

    def maybe_log_counts(self, counts, sim_time):
        if self.step - self.last_log_step < 120:
            return
        self.last_log_step = self.step
        parts = [
            f"{product_id}={counts.get(product_id, 0)}"
            for product_id in logic.product_ids()
        ]
        base = (
            f" baseline={self.baseline_counts}"
            if self.baseline_locked
            else " (baseline pending)"
        )
        print(f"[SHELF MONITORING] t={sim_time:.1f}s counts: {', '.join(parts)}{base}")

    def update_peak_counts(self, counts):
        self.peak_counts = logic.merge_peak_counts(self.peak_counts, counts)

    def try_lock_baseline(self, counts):
        self.update_peak_counts(counts)
        peak = dict(self.peak_counts)
        if sum(peak.values()) <= 0:
            if self.step >= BASELINE_MAX_WAIT_STEPS:
                print(
                    "[SHELF MONITORING WARNING] Baseline still zero after wait — "
                    "check shelf item positions / world reload"
                )
            return False
        self.baseline_counts = peak
        self.baseline_locked = True
        self.baseline_run_id = self.active_run_id()
        print(
            f"[SHELF MONITORING] Baseline shelf counts "
            f"(peak during settle, run id={self.baseline_run_id}):"
        )
        for product_id in logic.product_ids():
            item_count = peak.get(product_id, 0)
            rows = item_count // 3
            current = counts.get(product_id, 0)
            note = ""
            if current != item_count:
                note = f" (current={current})"
            print(f"  {product_id}: {item_count} items ({rows} rows){note}")
        return True

    def tick(self):
        sim_time = self.robot.getTime()
        entries = self.collect_shelf_nodes()
        counts = logic.count_all_products(entries)
        self.last_counts = counts

        if not self.baseline_locked:
            self.update_peak_counts(counts)
            if self.step >= BASELINE_SETTLE_STEPS:
                self.try_lock_baseline(counts)

        if self.step % PUBLISH_EVERY_STEPS != 0:
            return

        inventory = self.load_inventory()
        for product_id, count in counts.items():
            item = dict(inventory.get(product_id) or {})
            item["front_stock"] = logic.front_units(count)
            inventory[product_id] = item

        payload = logic.build_counts_payload(
            sim_time,
            counts,
            baseline=self.baseline_counts if self.baseline_locked else None,
            baseline_locked=self.baseline_locked,
            run_id=self.baseline_run_id if self.baseline_locked else self.active_run_id(),
        )
        payload["capacity"] = logic.shelf_capacity_summary(counts)
        logic.save_shelf_counts(self.project_root, payload)
        self.maybe_log_counts(counts, sim_time)
        self.post_dashboard(
            {
                "sim_time": sim_time,
                "shelf_counts": counts,
                "baseline_shelf_counts": self.baseline_counts,
                "inventory": inventory,
            }
        )

    def run(self):
        while self.robot.step(TIME_STEP) != -1:
            self.tick()
            self.step += 1


if __name__ == "__main__":
    ShelfMonitoring().run()
