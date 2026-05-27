"""Supervisor: detect boxes on stock pallets and publish pallet counts."""

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

import box_routing  # noqa: E402
import product_routing  # noqa: E402
import restocking_task_manager as task_mgr  # noqa: E402

TIME_STEP = 32
PUBLISH_EVERY_STEPS = 48
DASHBOARD_URL = "http://127.0.0.1:8000/update"
SEND_TO_DASHBOARD = True
PROCESSED_FILENAME = "stock_processed.json"
SENSOR_NAMES = (
    "stock_monitoring_beer",
    "stock_monitoring_chips",
    "stock_monitoring_cheese",
    "stock_monitoring_milk",
)


class StockMonitoring:
    def __init__(self):
        self.robot = Supervisor()
        self.project_root = os.path.dirname(_CONTROLLERS_DIR)
        self.processed = set()
        self.reset_processed_file()
        self.step = 0
        self.sensors = {}
        for name in SENSOR_NAMES:
            device = self.robot.getDevice(name)
            if device is not None:
                device.enable(TIME_STEP)
                self.sensors[name] = device
        print(
            f"[STOCK MONITORING] Started; zone radius "
            f"{product_routing.PALLET_ZONE_RADIUS}m, "
            f"sensors={list(self.sensors.keys()) or 'zone-only'}"
        )

    def processed_path(self):
        return os.path.join(self.project_root, "data", PROCESSED_FILENAME)

    def load_processed(self):
        path = self.processed_path()
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
                return set(data) if isinstance(data, list) else set()
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return set()

    def reset_processed_file(self):
        path = self.processed_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump([], handle)

    def save_processed(self):
        path = self.processed_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(sorted(self.processed), handle, indent=2)

    def iter_boxes(self):
        for index in range(100):
            box_def = f"{product_routing.BOX_DEF_PREFIX}{index}"
            node = self.robot.getFromDef(box_def)
            if node is None:
                continue
            pos = list(node.getField("translation").getSFVec3f())
            yield box_def, pos

    def pallet_for_box(self, box_pos):
        for pallet_def in product_routing.iter_pallet_defs():
            if product_routing.box_on_pallet(box_pos, pallet_def):
                return pallet_def
        return None

    def note_box_on_pallet(self, box_def, pallet_def, route):
        """Track pallet boxes; sort tasks are created only by task_manager."""
        if box_def in self.processed:
            return
        self.processed.add(box_def)
        self.save_processed()

    def count_pallet_boxes_by_product(self):
        counts = {
            product_routing.route_for_pallet_def(pallet_def)["product_id"]: 0
            for pallet_def in product_routing.iter_pallet_defs()
        }
        for box_def, box_pos in self.iter_boxes():
            pallet_def = self.pallet_for_box(box_pos)
            if pallet_def is None:
                continue
            product_id = product_routing.route_for_pallet_def(pallet_def)["product_id"]
            counts[product_id] = counts.get(product_id, 0) + 1
        return counts

    def publish_pallet_counts(self):
        sim_time = self.robot.getTime()
        counts = self.count_pallet_boxes_by_product()
        rules = task_mgr.stock_rules_payload()
        task_mgr.save_pallet_counts(
            self.project_root,
            counts,
            sim_time,
            source="stock_monitoring",
        )
        if not SEND_TO_DASHBOARD:
            return
        body = json.dumps(
            {
                "source": "stock_monitoring",
                "sim_time": sim_time,
                "pallet_counts": counts,
                "stock_rules": rules,
            }
        ).encode("utf-8")
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

    def check_pallets(self):
        for box_def, box_pos in self.iter_boxes():
            if box_def in self.processed:
                continue
            pallet_def = self.pallet_for_box(box_pos)
            if pallet_def is None:
                continue
            route = product_routing.route_for_pallet_def(pallet_def)
            if box_routing.read_assignment(self.project_root, box_def) is None:
                continue
            self.note_box_on_pallet(box_def, pallet_def, route)

    def run(self):
        while self.robot.step(TIME_STEP) != -1:
            self.check_pallets()
            if self.step % PUBLISH_EVERY_STEPS == 0:
                self.publish_pallet_counts()
            self.step += 1


if __name__ == "__main__":
    StockMonitoring().run()
