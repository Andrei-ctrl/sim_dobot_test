from controller import Supervisor
import json
import os
import sys
import urllib.request

_LOGIC_DIR = os.path.join(os.path.dirname(__file__), "..", "youbot_restocker_demo")
if _LOGIC_DIR not in sys.path:
    sys.path.insert(0, _LOGIC_DIR)

import youbot_restocker_logic as scan_logic  # noqa: E402

_CONTROLLERS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CONTROLLERS_DIR not in sys.path:
    sys.path.insert(0, _CONTROLLERS_DIR)

import spawn_signal  # noqa: E402
import box_routing  # noqa: E402
import product_routing  # noqa: E402

DASHBOARD_URL = "http://127.0.0.1:8000/update"
SEND_TO_DASHBOARD = True
PRODUCT_DEF_PREFIXES = ("SPAWNED_BOX_", "DEMO_BOTTLE")
DIAG_LOG_INTERVAL = 200
ENABLE_SCANNER_DIAG = False

# Keep this False while testing whether the box physically reaches the youBot
# platform. When False, this controller only scans/logs; it does not move any
# product or robot with Supervisor fields.
ENABLE_RESTOCKER_SUPERVISOR_ASSIST = False


class ScannerController:
    def __init__(self):
        self.robot = Supervisor()
        self.timestep = int(self.robot.getBasicTimeStep())
        self.step = 0
        self.project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.inventory_path = os.path.join(self.project_root, "data", "inventory.json")

        self.ds = self.robot.getDevice("distance sensor")
        if self.ds is None:
            print("[SCANNER ERROR] Distance sensor not found. Check sensor name.")
        else:
            self.ds.enable(self.timestep)
            print("[SCANNER] Distance sensor loaded (supplementary; zone uses DEF position).")

        self.self_node = self.robot.getSelf()
        self.scanner_position = list(
            self.self_node.getField("translation").getSFVec3f()
        )
        self.scanner_xy = self.scanner_position[:2]
        self.scan_radius = scan_logic.SCANNER_RADIUS

        self.scanned_upstream = set()
        self.scanned_pick_slot = set()
        self.completed_pickups = set()
        self.active_task = None

        self.restocker_node = self.robot.getFromDef("STORE_YOUBOT_RESTOCKER")
        self.restocker_translation_field = None
        self.restocker_rotation_field = None

        self.restocker_home_position = [-1.6356363857249125, 0.6166719978287399, 0.10346888943992652]
        self.restocker_home_rotation = [
            0.0005265689269977376,
            5.881459184608501e-07,
            0.9999998613624,
            3.12159,
        ]
        self.restocker_pick_position = self.restocker_home_position
        self.restocker_stock_position = [-2.45, 0.62, 0.112249]
        self.pickup_x = -0.9
        self.conveyor_y = 0.54
        self.default_box_z = 0.26
        self.carry_offset = [0.0, 0.0, 0.28]
        self.move_to_pick_steps = 90
        self.grab_steps = 50
        self.carry_steps = 140
        self.place_steps = 70

        if self.restocker_node is None:
            print("[RESTOCKER ERROR] STORE_YOUBOT_RESTOCKER not found in world.")
        else:
            self.restocker_translation_field = self.restocker_node.getField("translation")
            self.restocker_rotation_field = self.restocker_node.getField("rotation")
            print("[RESTOCKER] STORE_YOUBOT_RESTOCKER loaded.")
            if ENABLE_RESTOCKER_SUPERVISOR_ASSIST:
                self.set_restocker_pose(self.restocker_home_position, self.restocker_home_rotation)
            else:
                print("[RESTOCKER] Supervisor-assisted pickup is disabled for physical platform test.")

        self.product_database = {
            entry["product_id"]: {
                "name": entry["display_name"],
                "category": "Stock",
                "target_shelf": entry["shelf_name"],
                "target_pallet": entry["def"],
            }
            for entry in product_routing.STOCK_PALLETS.values()
        }

        print("[SCANNER] Product scanner started.")
        print(
            f"[SCANNER] Upstream zone center=({scan_logic.SCANNER_XY[0]:.3f}, "
            f"{scan_logic.SCANNER_XY[1]:.3f}) radius={self.scan_radius}m"
        )
        print(
            f"[SCANNER] Fixed pick slot=({scan_logic.FIXED_PICK_BOX_POS[0]:.3f}, "
            f"{scan_logic.FIXED_PICK_BOX_POS[1]:.3f}, "
            f"{scan_logic.FIXED_PICK_BOX_POS[2]:.3f}) "
            f"radius={scan_logic.FIXED_PICK_RADIUS}m"
        )
        print(f"[SCANNER] Robot mounted at {self.scanner_position}")

    def post_json(self, payload):
        if not SEND_TO_DASHBOARD:
            return

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            DASHBOARD_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=0.2) as resp:
                resp.read()
        except Exception:
            pass

    def get_product_defs(self):
        product_defs = ["DEMO_BOTTLE"]
        for i in range(100):
            product_defs.append(f"DEMO_BOTTLE_{i}")
            product_defs.append(f"SPAWNED_BOX_{i}")
        return product_defs

    def distance_2d(self, pos_a, pos_b):
        dx = pos_a[0] - pos_b[0]
        dy = pos_a[1] - pos_b[1]
        return (dx * dx + dy * dy) ** 0.5

    def read_box_fields(self, product):
        pos = list(product.getField("translation").getSFVec3f())
        name = ""
        name_field = product.getField("name")
        if name_field is not None:
            name = name_field.getSFString()

        size = None
        size_field = product.getField("size")
        if size_field is not None:
            size = list(size_field.getSFVec3f())

        mass = None
        mass_field = product.getField("mass")
        if mass_field is not None:
            mass = mass_field.getSFFloat()

        return pos, name, size, mass

    def build_scan_info(self, product_def, product):
        pos, name, size, mass = self.read_box_fields(product)
        info = scan_logic.build_box_scan_info(
            product_def,
            pos,
            scanner_xy=scan_logic.SCANNER_XY,
            scanner_radius=self.scan_radius,
        )
        product_id = self.identify_product_id(product_def, product)
        route = product_routing.route_for_box_def(product_def)
        product_info = self.product_database.get(product_id, {
            "name": "Unknown product",
            "category": "Unknown",
            "target_shelf": route["shelf_name"],
            "target_pallet": route["def"],
        })
        info["product_id"] = product_id
        info["name"] = name or product_info["name"]
        info["category"] = product_info["category"]
        info["target_shelf"] = product_info["target_shelf"]
        info["target_pallet"] = product_info.get("target_pallet", route["def"])
        info["front_shelf"] = product_info.get("front_shelf", product_info["target_shelf"])
        info["size"] = size
        info["mass"] = mass
        return info

    def report_scan(self, info, zone, ds_value):
        info = dict(info)
        info["zone"] = zone
        info["distance_sensor"] = ds_value
        print(scan_logic.format_box_scan_log(info))

        if zone == "upstream_scanner":
            print("[SCANNER] Product entered upstream conveyor scanner zone")
            assignment = box_routing.assign_box(
                self.project_root, info["def"], self.robot.getTime()
            )
            print(
                f"[SCANNER] Routed {info['def']} → {assignment['target_pallet']} "
                f"({assignment['product_id']}) shelf={assignment['shelf_name']}"
            )
            self.notify_box_spawner(info["def"])
        else:
            print("[SCANNER] Product arrived at youBot fixed pick slot")
            if box_routing.read_assignment(self.project_root, info["def"]) is None:
                assignment = box_routing.assign_box(
                    self.project_root, info["def"], self.robot.getTime()
                )
                print(
                    f"[SCANNER] Routed {info['def']} → {assignment['target_pallet']} "
                    f"({assignment['product_id']}) shelf={assignment['shelf_name']}"
                )
            if info["def"] not in self.scanned_upstream:
                self.notify_box_spawner(info["def"])

        print(f"[SCANNER] Target shelf: {info['target_shelf']}")
        if ENABLE_RESTOCKER_SUPERVISOR_ASSIST:
            print(f"[RESTOCKER TASK] Assign STORE_YOUBOT_RESTOCKER to collect {info['def']}")
        else:
            print("[RESTOCKER TEST] Supervisor pickup disabled; youBot uses wheel pickup")

        payload = {
            "t": self.robot.getTime(),
            "event": "product_scanned",
            "zone": zone,
            "def": info["def"],
            "product_id": info["product_id"],
            "name": info["name"],
            "category": info["category"],
            "target_shelf": info["target_shelf"],
            "position": info["position"],
            "size": info["size"],
            "mass": info["mass"],
            "dist_to_scanner": info["dist_to_scanner"],
            "dist_to_pick_slot": info["dist_to_pick_slot"],
            "ds": ds_value,
        }
        self.post_json(payload)

    def notify_box_spawner(self, box_def):
        live = scan_logic.count_live_boxes(self.robot.getFromDef)
        if scan_logic.box_limit_reached(live):
            print(
                f"[SCANNER] Skip spawn request for {box_def}: "
                f"{live}/{scan_logic.MAX_LIVE_BOXES} boxes already in world"
            )
            return
        payload = spawn_signal.write_signal(
            self.project_root,
            box_def,
            self.robot.getTime(),
            triggered_by="scanner",
        )
        print(
            f"[SCANNER] Requested next box spawn (triggered by {box_def}, "
            f"signal seq={payload['seq']})"
        )

    def log_diagnostics(self):
        print("[SCANNER DIAG] Box tracking snapshot:")
        found_any = False
        for product_def in self.get_product_defs():
            product = self.robot.getFromDef(product_def)
            if product is None:
                continue
            found_any = True
            info = self.build_scan_info(product_def, product)
            pos = info["position"]
            flags = []
            if product_def in self.scanned_upstream:
                flags.append("SCANNED_UPSTREAM")
            if product_def in self.scanned_pick_slot:
                flags.append("SCANNED_PICK")
            if product_def in self.completed_pickups:
                flags.append("COMPLETED")
            flag_str = ",".join(flags) if flags else "new"
            print(
                f"  {product_def} @ ({pos[0]:.3f},{pos[1]:.3f},{pos[2]:.3f}) "
                f"[{flag_str}] dist_scanner={info['dist_to_scanner']:.2f}m "
                f"dist_pick={info['dist_to_pick_slot']:.2f}m"
            )
            if not info["in_scanner_zone"] and not info["at_fixed_pick_slot"]:
                reject = scan_logic.pick_station_rejection_reason(pos)
                if reject:
                    print(f"    not at pick slot: {reject[0]}")
        if not found_any:
            print("  (no SPAWNED_BOX_* / DEMO_BOTTLE defs in world)")

    def scan_products(self):
        ds_value = self.ds.getValue() if self.ds is not None else None

        if self.active_task is not None:
            return

        for product_def in self.get_product_defs():
            product = self.robot.getFromDef(product_def)
            if product is None:
                continue

            info = self.build_scan_info(product_def, product)

            if info["in_scanner_zone"] and product_def not in self.scanned_upstream:
                self.report_scan(info, zone="upstream_scanner", ds_value=ds_value)
                self.scanned_upstream.add(product_def)
                if not ENABLE_RESTOCKER_SUPERVISOR_ASSIST:
                    continue

                self.active_task = {
                    "def": product_def,
                    "node": product,
                    "product_id": info["product_id"],
                    "phase": "wait_for_pickup",
                    "step": 0,
                    "pickup_box_position": None,
                }
                return

            if info["at_fixed_pick_slot"] and product_def not in self.scanned_pick_slot:
                self.report_scan(info, zone="fixed_pick_slot", ds_value=ds_value)
                self.scanned_pick_slot.add(product_def)

        if ENABLE_SCANNER_DIAG and self.step % DIAG_LOG_INTERVAL == 0:
            self.log_diagnostics()

    def interpolate(self, start, end, progress):
        progress = max(0.0, min(1.0, progress))
        return [
            start[0] + (end[0] - start[0]) * progress,
            start[1] + (end[1] - start[1]) * progress,
            start[2] + (end[2] - start[2]) * progress,
        ]

    def set_node_translation(self, node, position):
        node.getField("translation").setSFVec3f(position)
        node.resetPhysics()

    def set_restocker_pose(self, position, rotation=None):
        if self.restocker_node is None or self.restocker_translation_field is None:
            return

        self.restocker_translation_field.setSFVec3f(position)

        if rotation is not None and self.restocker_rotation_field is not None:
            self.restocker_rotation_field.setSFRotation(rotation)

        self.restocker_node.resetPhysics()

    def restocker_carry_position(self, restocker_position):
        return [
            restocker_position[0] + self.carry_offset[0],
            restocker_position[1] + self.carry_offset[1],
            restocker_position[2] + self.carry_offset[2],
        ]

    def stock_box_position(self):
        return [
            self.restocker_stock_position[0] + self.carry_offset[0],
            self.restocker_stock_position[1] + self.carry_offset[1],
            self.default_box_z,
        ]

    def update_restocker_task(self):
        if not ENABLE_RESTOCKER_SUPERVISOR_ASSIST:
            return

        if self.active_task is None:
            return

        product = self.robot.getFromDef(self.active_task["def"])
        if product is None:
            print(f"[RESTOCKER ERROR] Product disappeared: {self.active_task['def']}")
            self.active_task = None
            return

        phase = self.active_task["phase"]
        self.active_task["step"] += 1

        if phase == "wait_for_pickup":
            product_position = product.getField("translation").getSFVec3f()

            if product_position[0] > self.pickup_x:
                return

            pickup_position = [
                self.pickup_x,
                self.conveyor_y,
                max(product_position[2], self.default_box_z),
            ]
            self.active_task["pickup_box_position"] = pickup_position
            self.active_task["restocker_start"] = self.restocker_translation_field.getSFVec3f()
            self.active_task["phase"] = "move_to_pickup"
            self.active_task["step"] = 0
            self.set_node_translation(product, pickup_position)
            print(f"[RESTOCKER] {self.active_task['def']} reached pickup point on conveyor")
            print("[RESTOCKER] Moving youBot to conveyor pickup point")
            return

        if phase == "move_to_pickup":
            progress = self.active_task["step"] / self.move_to_pick_steps
            restocker_position = self.interpolate(
                self.active_task["restocker_start"],
                self.restocker_pick_position,
                progress,
            )
            self.set_restocker_pose(restocker_position, self.restocker_home_rotation)
            self.set_node_translation(product, self.active_task["pickup_box_position"])

            if progress >= 1.0:
                self.active_task["phase"] = "grab"
                self.active_task["step"] = 0
                print(f"[RESTOCKER PICK] STORE_YOUBOT_RESTOCKER takes {self.active_task['def']}")
            return

        if phase == "grab":
            progress = self.active_task["step"] / self.grab_steps
            start = self.active_task["pickup_box_position"]
            end = self.restocker_carry_position(self.restocker_pick_position)
            self.set_node_translation(product, self.interpolate(start, end, progress))

            if progress >= 1.0:
                self.active_task["phase"] = "carry_to_stock"
                self.active_task["step"] = 0
                print("[RESTOCKER] Carrying product box to stock area")
            return

        if phase == "carry_to_stock":
            progress = self.active_task["step"] / self.carry_steps
            restocker_position = self.interpolate(
                self.restocker_pick_position,
                self.restocker_stock_position,
                progress,
            )
            self.set_restocker_pose(restocker_position, self.restocker_home_rotation)
            self.set_node_translation(product, self.restocker_carry_position(restocker_position))

            if progress >= 1.0:
                self.active_task["phase"] = "place_in_stock"
                self.active_task["step"] = 0
                self.active_task["place_start"] = self.restocker_carry_position(self.restocker_stock_position)
                print("[RESTOCKER PLACE] Lowering product box into stock area")
            return

        if phase == "place_in_stock":
            progress = self.active_task["step"] / self.place_steps
            self.set_restocker_pose(self.restocker_stock_position, self.restocker_home_rotation)
            self.set_node_translation(
                product,
                self.interpolate(self.active_task["place_start"], self.stock_box_position(), progress),
            )

            if progress >= 1.0:
                self.finish_restocker_task(product)

    def run(self):
        while self.robot.step(self.timestep) != -1:
            self.scan_products()
            self.update_restocker_task()
            self.step += 1

    def load_inventory(self):
        try:
            with open(self.inventory_path, "r", encoding="utf-8") as file:
                return json.load(file)
        except FileNotFoundError:
            print("[INVENTORY ERROR] inventory.json not found")
            return {}

    def save_inventory(self, inventory):
        with open(self.inventory_path, "w", encoding="utf-8") as file:
            json.dump(inventory, file, indent=2)

    def update_inventory_after_stock(self, product_id):
        inventory = self.load_inventory()

        if product_id not in inventory:
            print(f"[INVENTORY] Unknown product, cannot update: {product_id}")
            return None

        inventory[product_id]["storage_stock"] += 1

        item = inventory[product_id]

        print(
            f"[INVENTORY] {product_id}: "
            f"storage={item['storage_stock']}, "
            f"front={item['front_stock']}, "
            f"threshold={item['threshold']}"
        )

        if item["front_stock"] < item["threshold"] and item["storage_stock"] > 0:
            print(f"[RESTOCK TASK] Front shelf below threshold for {product_id}")
            print(f"[RESTOCK TASK] Assign youBot restocker to move item to {item['front_shelf']}")

            item["storage_stock"] -= 1
            item["front_stock"] += 1

            print(
                f"[RESTOCK COMPLETE] {product_id}: "
                f"storage={item['storage_stock']}, "
                f"front={item['front_stock']}"
            )

        self.save_inventory(inventory)
        return inventory[product_id]

    def finish_restocker_task(self, product):
        product_id = self.active_task["product_id"]
        product_def = self.active_task["def"]

        self.set_node_translation(product, self.stock_box_position())
        updated_inventory_item = self.update_inventory_after_stock(product_id)

        print(f"[RESTOCKER COMPLETE] {product_def} placed in stock area")
        self.completed_pickups.add(product_def)

        self.post_json({
            "t": self.robot.getTime(),
            "event": "product_stocked_by_youbot",
            "def": product_def,
            "product_id": product_id,
            "inventory": updated_inventory_item,
        })

        self.active_task = None

    def identify_product_id(self, product_def, product):
        route = product_routing.route_for_box_def(product_def)
        return route["product_id"]


if __name__ == "__main__":
    ScannerController().run()
