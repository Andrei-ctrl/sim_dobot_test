import json
import math
import os
import sys
import urllib.error
import urllib.request

from controller import Supervisor

_DEMO_DIR = os.path.dirname(os.path.abspath(__file__))
_CONTROLLERS_DIR = os.path.join(_DEMO_DIR, "..")
for path in (_DEMO_DIR, _CONTROLLERS_DIR, os.path.join(_CONTROLLERS_DIR, "shelf_monitoring")):
    if path not in sys.path:
        sys.path.insert(0, path)

import product_cubes
import product_routing
import shelf_monitoring_logic as shelf_mon
import sort_signal
import motor_utils
import youbot_mecanum as mecanum
import youbot_sorter_logic as logic

ACTION_SPEED = 1.0

DRIVE_TOLERANCE = logic.NAV_POS_TOL
DRIVE_SPEED = 0.55 * ACTION_SPEED
MAX_DRIVE_TIME = int(12000 / ACTION_SPEED)

WHEEL_MAX_VEL = mecanum.WHEEL_MAX_VEL

INVENTORY_FILE = "inventory.json"
DASHBOARD_URL = "http://127.0.0.1:8000/update"
SEND_TO_DASHBOARD = True


class YoubotSorterDemo:
    def __init__(self):
        self.robot = Supervisor()
        TIME_STEP = int(self.robot.getBasicTimeStep())
        self.time_step = TIME_STEP
        self.self_node = self.robot.getSelf()
        self.root = self.robot.getRoot()
        self.children = self.root.getField("children")
        self.project_root = os.path.abspath(os.path.join(_CONTROLLERS_DIR, ".."))
        sort_signal.reset_signal(self.project_root, clear_queue=True)

        self.wheels = [self.robot.getDevice(f"wheel{i}") for i in range(1, 5)]
        missing = [i + 1 for i, wheel in enumerate(self.wheels) if wheel is None]
        if missing:
            print(f"[YOUBOT SORTER WARNING] Missing wheels: {missing}")
        else:
            for wheel in self.wheels:
                wheel.setPosition(float("inf"))
                wheel.setVelocity(0.0)
            print("[YOUBOT SORTER] Mecanum wheels ready (velocity mode)")

        for arm_name in ("arm1", "arm2", "arm3", "arm4", "arm5"):
            motor_utils.set_joint_position(self.robot.getDevice(arm_name), 0.0)
        self.gripper_motors = []
        for grip_name in ("gripper::left", "gripper::right"):
            grip = self.robot.getDevice(grip_name)
            self.gripper_motors.append(grip)
            motor_utils.set_joint_position(grip, 0.0)

        self.home_translation = list(
            self.self_node.getField("translation").getSFVec3f()
        )
        self.home_rotation = list(
            self.self_node.getField("rotation").getSFRotation()
        )
        self.home_heading = self.rotation_field_to_yaw(self.home_rotation)

        self.state = "WAIT_SIGNAL"
        self.timer = 0
        self.last_sort_seq = logic.initial_sort_seq_baseline(
            sort_signal.last_completed_seq(self.project_root)
        )
        self.signal_wait_logged = False
        self.queue_wait_log_step = 0
        self.active_task = None
        self.completed_product_id = ""
        self.last_sorted_product_id = ""
        self.loaded_cube_defs = []
        self.carried_box_def = ""
        self.nav_steps = []
        self.nav_step_index = 0
        self.nav_target = [0.0, 0.0, 0.0]
        self.last_nav_log = ""

        print("[YOUBOT SORTER] Product waypoint navigation v5 (cardinal mecanum, fixed path)")
        print(
            f"[YOUBOT SORTER] Home ({self.home_translation[0]:.3f}, "
            f"{self.home_translation[1]:.3f}), "
            f"products: {', '.join(logic.PRODUCT_SORT_ROUTES)}"
        )
        print(f"[YOUBOT SORTER] IPC queue: {sort_signal.queue_path(self.project_root)}")
        print(
            f"[YOUBOT SORTER] Sort baseline last_seq={self.last_sort_seq} "
            f"(pending IPC tasks will be accepted)"
        )
        print(
            "[YOUBOT SORTER] IPC only: task_manager + stock_monitoring "
            "(pallet auto-scan disabled)"
        )

    def task_trigger_source(self, parsed):
        triggered_by = (parsed.get("triggered_by") or "").strip()
        if triggered_by:
            return triggered_by
        task_type = parsed.get("task_type", "stock_pallet")
        if task_type == "front_restock":
            return "task_manager"
        if parsed.get("box_def"):
            return "stock_monitoring"
        return "sort_queue"

    def log_queue_status(self, force=False):
        if not force and self.timer - self.queue_wait_log_step < self.act_steps(120):
            return
        self.queue_wait_log_step = self.timer
        pending = sort_signal.pending_tasks(self.project_root, self.last_sort_seq)
        summaries = []
        for task in pending[:4]:
            summaries.append(
                f"seq={task.get('seq')} {task.get('product_id')} "
                f"type={task.get('task_type', 'stock_pallet')} "
                f"by={task.get('triggered_by') or '?'}"
            )
        detail = "; ".join(summaries) if summaries else "none"
        print(
            f"[YOUBOT SORTER] Queue poll last_seq={self.last_sort_seq} "
            f"pending={len(pending)} [{detail}]"
        )

    def act_steps(self, steps):
        return max(1, int(steps / ACTION_SPEED))

    def normalize_angle(self, angle):
        return logic.normalize_angle(angle)

    def rotation_field_to_yaw(self, rotation):
        axis_x, axis_y, axis_z, angle = rotation
        axis_len = math.sqrt(axis_x * axis_x + axis_y * axis_y + axis_z * axis_z)
        if axis_len < 1e-9:
            return 0.0
        x = axis_x / axis_len
        y = axis_y / axis_len
        z = axis_z / axis_len
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        t = 1.0 - cos_a
        r10 = t * x * y + z * sin_a
        r00 = t * x * x + cos_a
        return math.atan2(r10, r00)

    def get_robot_xy(self):
        pos = self.self_node.getField("translation").getSFVec3f()
        return pos[0], pos[1]

    def get_robot_xyz(self):
        return list(self.self_node.getField("translation").getSFVec3f())

    def get_robot_yaw(self):
        orientation = self.self_node.getOrientation()
        return math.atan2(orientation[3], orientation[0])

    def get_platform_yaw(self):
        return self.get_robot_yaw()

    def stop_wheels(self):
        for wheel in self.wheels:
            if wheel is not None:
                wheel.setVelocity(0.0)

    def set_wheel_velocities(self, wheel_speeds):
        for wheel, speed in zip(self.wheels, wheel_speeds):
            if wheel is None:
                continue
            wheel.setVelocity(max(-WHEEL_MAX_VEL, min(WHEEL_MAX_VEL, speed)))

    def set_mecanum(self, vx, vy, omega):
        speeds = mecanum.clamp_wheel_speeds(mecanum.wheel_speeds(vx, vy, omega))
        self.set_wheel_velocities(speeds)

    def log_nav(self, message):
        if message and message != self.last_nav_log:
            print(f"[SORTER NAV] {message}")
            self.last_nav_log = message

    def drive_toward_xyz_mecanum(self, target_x, target_y, target_z, tolerance=DRIVE_TOLERANCE):
        """Axis-aligned mecanum only — no rotation, no obstacle stops."""
        robot_x, robot_y = self.get_robot_xy()
        robot_z = self.get_robot_xyz()[2]
        dx = target_x - robot_x
        dy = target_y - robot_y
        dz = target_z - robot_z
        distance_xy = math.hypot(dx, dy)

        if distance_xy < tolerance and abs(dz) < tolerance:
            self.stop_wheels()
            return True

        yaw = self.get_robot_yaw()
        local_dx, local_dy = mecanum.world_delta_to_robot(dx, dy, yaw)
        vx, vy, omega = mecanum.cardinal_drive_cmd(local_dx, local_dy, DRIVE_SPEED)
        self.set_mecanum(vx, vy, 0.0)
        return False

    def snap_nav_z(self, z):
        pos = self.get_robot_xyz()
        if abs(pos[2] - z) > 0.001:
            pos[2] = z
            self.self_node.getField("translation").setSFVec3f(pos)

    def begin_nav_steps(self, steps):
        self.nav_steps = list(steps)
        self.nav_step_index = 0
        self.last_nav_log = ""
        if not self.nav_steps:
            self.change_state("WAIT_SIGNAL")
            return
        self.start_current_nav_step()
        self.change_state("NAV_WAYPOINT")

    def start_current_nav_step(self):
        if self.nav_step_index >= len(self.nav_steps):
            return False
        step = self.nav_steps[self.nav_step_index]
        self.nav_target = list(step["xyz"])
        self.log_nav(step.get("log", ""))
        return True

    def advance_nav_step(self):
        self.nav_step_index += 1
        if self.nav_step_index >= len(self.nav_steps):
            return False
        self.start_current_nav_step()
        return True

    def continue_to_deposit(self):
        product_id = self.active_task["product_id"]
        route = logic.sort_route_for_product(product_id)
        steps = []
        for waypoint in logic.axis_waypoints(self.get_robot_xyz(), route["deposit"]):
            steps.append(
                {
                    "xyz": list(waypoint),
                    "action": "deposit",
                    "log": logic.nav_log_message("deposit", product_id),
                }
            )
        self.begin_nav_steps(steps)

    def on_nav_waypoint_reached(self):
        step = self.nav_steps[self.nav_step_index]
        self.snap_nav_z(step["xyz"][2])
        action = step.get("action", "continue")

        if action in ("pre_pickup", "continue"):
            if not self.advance_nav_step():
                self.change_state("WAIT_SIGNAL")
            return

        if action == "pickup":
            self.change_state("LOAD_BOX_ON_PLATFORM")
        elif action == "deposit":
            self.change_state("SUPERVISOR_PLACE")
        elif action == "next_task":
            self.change_state("LOAD_BOX_ON_PLATFORM")
        elif action == "idle":
            product_id = self.completed_product_id or logic.DEFAULT_PRODUCT_ID
            print(
                f"[SORTER NAV] At {logic.sort_route_label(product_id)} idle pre-pickup, "
                f"waiting for task"
            )
            self.change_state("WAIT_SIGNAL")
        else:
            if not self.advance_nav_step():
                self.change_state("WAIT_SIGNAL")

    def peek_next_sort_task(self):
        pending = sort_signal.pending_tasks(self.project_root, self.last_sort_seq)
        parsed = logic.next_pending_task(pending, self.last_sort_seq)
        if parsed is not None:
            return parsed
        signal = sort_signal.read_signal(self.project_root)
        should_run, parsed = logic.should_process_signal(signal, self.last_sort_seq)
        if should_run:
            return parsed
        return None

    def peek_next_same_product_task(self, product_id):
        parsed = self.peek_next_sort_task()
        if parsed is not None and logic.is_same_product_task(parsed, product_id):
            return parsed
        return None

    def can_execute_sort_task(self, parsed):
        product_id = parsed["product_id"]
        cube_count = int(parsed.get("cube_count", logic.BOTTLES_PER_BOX))
        if not shelf_mon.shelf_monitoring_ready(self.project_root):
            return False, "waiting for shelf counts"
        counts = shelf_mon.read_counts(self.project_root)
        current = int(counts.get(product_id, 0))
        maximum = shelf_mon.max_slots_for_product(product_id)
        if not shelf_mon.can_accept_sort(current, product_id, cube_count):
            return False, f"front shelf full ({current}/{maximum}, need +{cube_count})"
        return True, ""

    def skip_sort_task(self, parsed, reason):
        print(
            f"[YOUBOT SORTER] Skip sort seq={parsed['seq']} product={parsed['product_id']}: "
            f"{reason}"
        )
        self.last_sort_seq = parsed["seq"]
        sort_signal.mark_task_done(self.project_root, parsed["seq"], status="skipped_full")
        self.active_task = None

    def next_executable_sort_task(self):
        while True:
            parsed = self.peek_next_sort_task()
            if parsed is None:
                return None
            ok, reason = self.can_execute_sort_task(parsed)
            if ok:
                return parsed
            if "waiting" in reason:
                return None
            self.skip_sort_task(parsed, reason)

    def accept_sort_task(self, parsed, *, source_hint=""):
        self.signal_wait_logged = False
        self.last_sort_seq = parsed["seq"]
        self.active_task = parsed
        self.loaded_cube_defs = list(parsed.get("cube_defs") or [])
        task_type = parsed.get("task_type", "stock_pallet")
        reason = parsed.get("reason", "")
        source = source_hint or self.task_trigger_source(parsed)
        print(
            f"[YOUBOT SORTER] RECEIVED sort trigger source={source} seq={parsed['seq']} "
            f"type={task_type} product={parsed['product_id']} "
            f"pallet={parsed['source_pallet']} box={parsed.get('box_def') or '(scan)'} "
            f"bottles={parsed['cube_count']}"
        )
        if reason:
            print(f"[YOUBOT SORTER]   reason: {reason}")
        self.post_dashboard(
            "busy",
            f"sort {parsed['product_id']} seq={parsed['seq']}",
        )

    def start_pickup_for_active_task(self):
        product_id = self.active_task["product_id"]
        from_xyz = self.get_robot_xyz()
        prev = self.last_sorted_product_id
        if prev and prev != product_id:
            steps = logic.build_product_switch_steps(from_xyz, prev, product_id)
            print(
                f"[SORTER NAV] Product switch {prev} -> {product_id} "
                f"(via {logic.sort_route_label(prev)} pre-pickup first)"
            )
        else:
            steps = logic.build_nav_steps(from_xyz, product_id, "pickup_run")
            if prev == product_id:
                print(f"[SORTER NAV] Same product {product_id} — pickup run from current position")
            else:
                print(f"[SORTER NAV] First task {product_id} — pickup run")
        self.begin_nav_steps(steps)

    def begin_post_deposit_navigation(self, product_id):
        next_task = self.next_executable_sort_task()
        if next_task and logic.is_same_product_task(next_task, product_id):
            self.accept_sort_task(next_task)
            steps = logic.build_nav_steps(self.get_robot_xyz(), product_id, "post_next")
        elif next_task:
            new_id = next_task["product_id"]
            self.accept_sort_task(next_task)
            steps = logic.build_product_switch_steps(
                self.get_robot_xyz(),
                product_id,
                new_id,
            )
            print(
                f"[SORTER NAV] Queued switch {product_id} -> {new_id} "
                f"(via {logic.sort_route_label(product_id)} pre-pickup before next task)"
            )
        else:
            steps = logic.build_nav_steps(self.get_robot_xyz(), product_id, "post_idle")
        self.begin_nav_steps(steps)

    def get_shelf_base(self, product_id=None):
        product_id = product_id or (
            self.active_task["product_id"] if self.active_task else logic.DEFAULT_PRODUCT_ID
        )
        return logic.shelf_base_for_product(product_id)

    def process_sort_signal(self):
        parsed = self.next_executable_sort_task()
        if parsed is None:
            if not self.signal_wait_logged:
                self.signal_wait_logged = True
                print(
                    "[YOUBOT SORTER] Waiting for sort task via IPC "
                    "(task_manager / stock_monitoring)"
                )
            self.log_queue_status()
            return False

        self.accept_sort_task(parsed)
        self.start_pickup_for_active_task()
        return True

    def scan_pallet_for_box_task(self):
        if sort_signal.pending_tasks(self.project_root, self.last_sort_seq):
            self.log_queue_status(force=True)
            print(
                "[YOUBOT SORTER] Pallet scan skipped — "
                "pending IPC sort task(s) in queue"
            )
            return False
        if self.peek_next_sort_task() is not None:
            return False
        for index in range(100):
            box_def = f"{product_routing.BOX_DEF_PREFIX}{index}"
            node = self.robot.getFromDef(box_def)
            if node is None:
                continue
            pos = list(node.getField("translation").getSFVec3f())
            pallet_def = None
            for candidate in product_routing.iter_pallet_defs():
                if product_routing.box_on_pallet(pos, candidate):
                    pallet_def = candidate
                    break
            if pallet_def is None:
                continue
            route = product_routing.route_for_pallet_def(pallet_def)
            parsed = {
                "seq": self.last_sort_seq + 1,
                "product_id": route["product_id"],
                "source_pallet": pallet_def,
                "box_def": box_def,
                "cube_count": logic.BOTTLES_PER_BOX,
                "units_per_cube": logic.UNITS_PER_CUBE,
                "cube_defs": [],
                "t": self.robot.getTime(),
            }
            print(
                f"[YOUBOT SORTER] Pallet fallback (no IPC task): {box_def} on {pallet_def} "
                f"({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f})"
            )
            self.last_sort_seq = max(self.last_sort_seq, int(parsed["seq"]))
            self.accept_sort_task(parsed, source_hint="pallet_fallback")
            self.start_pickup_for_active_task()
            return True
        return False

    def supervisor_load_box_on_platform(self):
        if not self.active_task:
            return False

        box_def = self.active_task.get("box_def", "")
        if not box_def:
            print("[YOUBOT SORTER WARNING] Sort task has no box_def")
            return False

        box_node = self.robot.getFromDef(box_def)
        if box_node is None:
            print(f"[YOUBOT SORTER WARNING] Box {box_def} not found on pallet")
            return False

        loaded = product_cubes.attach_box_to_platform(
            self.robot.getFromDef,
            box_def,
            self.get_robot_xyz(),
            self.get_platform_yaw(),
        )
        if not loaded:
            print(f"[YOUBOT SORTER WARNING] Failed to load {box_def} onto platform")
            return False

        self.carried_box_def = box_def
        slot = logic.box_platform_world_position(
            self.get_robot_xyz(),
            self.get_platform_yaw(),
        )
        print(
            f"[YOUBOT SORTER] Loaded {box_def} onto back platform "
            f"({slot[0]:.2f}, {slot[1]:.2f}, {slot[2]:.2f})"
        )
        return True

    def load_inventory(self):
        path = os.path.join(self.project_root, "data", INVENTORY_FILE)
        try:
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def supervisor_unpack_box_to_shelf(self):
        if not self.active_task:
            return False

        product_id = self.active_task["product_id"]
        shelf_base = self.get_shelf_base(product_id)
        route = product_routing.route_for_product_id(product_id)
        box_def = self.carried_box_def or self.active_task.get("box_def", "")
        count = self.active_task.get("cube_count", logic.BOTTLES_PER_BOX)

        inventory = self.load_inventory()
        operation_index = logic.shelf_operation_index(inventory, product_id)
        if not logic.shelf_has_capacity(inventory, product_id):
            print(
                f"[YOUBOT SORTER WARNING] Shelf full for {product_id} "
                f"({logic.SHELF_MAX_SORT_OPERATIONS} operations max)"
            )

        spawned = product_cubes.unpack_box_to_shelf(
            self.children,
            self.robot.getFromDef,
            box_def,
            shelf_base=shelf_base,
            product_id=product_id,
            count=count,
            operation_index=operation_index,
        )
        self.loaded_cube_defs = spawned
        self.carried_box_def = ""
        slots = logic.shelf_slots_for_operation(product_id, operation_index)
        print(
            f"[YOUBOT SORTER] Unpacked box to {route['shelf_name']} "
            f"(operation {operation_index + 1}/{logic.SHELF_MAX_SORT_OPERATIONS}): "
            f"{len(spawned)}/{count} bottles"
        )
        for index, slot in enumerate(slots[: len(spawned)]):
            print(
                f"[YOUBOT SORTER]   bottle {index + 1} -> "
                f"({slot[0]:.4f}, {slot[1]:.4f}, {slot[2]:.4f})"
            )
        return len(spawned) >= count

    def update_inventory(self):
        if not self.active_task:
            return
        product_id = self.active_task["product_id"]
        delta = logic.inventory_delta(
            self.active_task["cube_count"],
            self.active_task["units_per_cube"],
        )
        path = os.path.join(self.project_root, "data", INVENTORY_FILE)
        try:
            with open(path, encoding="utf-8") as handle:
                inventory = json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            inventory = {}

        if product_id not in inventory:
            route = product_routing.route_for_product_id(product_id)
            inventory[product_id] = {
                "name": product_id,
                "category": "Drinks",
                "storage_stock": 0,
                "front_stock": 0,
                "threshold": 2,
                "storage_shelf": route["shelf_name"],
                "front_shelf": "FRONT_DRINKS",
                "shelf_operations": 0,
            }

        inventory[product_id]["storage_stock"] += delta
        ops = logic.increment_shelf_operation(inventory, product_id)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(inventory, handle, indent=2)

        item = inventory[product_id]
        print(
            f"[YOUBOT SORTER] Inventory {product_id}: "
            f"storage={item['storage_stock']} front={item['front_stock']} "
            f"(+{delta}), shelf_operations={ops}/{logic.SHELF_MAX_SORT_OPERATIONS}"
        )

    def leave_stock_visible_on_shelf(self):
        print(
            f"[YOUBOT SORTER] Stock left visible on shelf "
            f"({len(self.loaded_cube_defs)} bottles)"
        )

    def post_dashboard(self, status, detail=""):
        if not SEND_TO_DASHBOARD:
            return
        body = json.dumps(
            {
                "source": "sorter",
                "sim_time": self.robot.getTime(),
                "robots": {
                    "sorter": {
                        "status": status,
                        "detail": detail or self.state,
                    }
                },
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            DASHBOARD_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=0.3) as response:
                response.read()
        except (urllib.error.URLError, TimeoutError, OSError):
            pass

    def change_state(self, state):
        if state != "NAV_WAYPOINT":
            self.stop_wheels()
        self.state = state
        self.timer = 0
        if state == "WAIT_SIGNAL":
            self.post_dashboard("idle", "waiting for sort task")
        elif state == "NAV_WAYPOINT":
            self.post_dashboard("busy", self.last_nav_log or "navigating")
        elif state in ("LOAD_BOX_ON_PLATFORM", "SUPERVISOR_PLACE", "UPDATE_INVENTORY"):
            self.post_dashboard("busy", state.lower())

    def maintain_gripper_targets(self):
        for grip in self.gripper_motors:
            motor_utils.set_joint_position(grip, 0.0)

    def run_state(self):
        self.maintain_gripper_targets()
        if self.state == "WAIT_SIGNAL":
            self.process_sort_signal()

        elif self.state == "NAV_WAYPOINT":
            self.maintain_carried_box()
            target = self.nav_target
            if self.drive_toward_xyz_mecanum(
                target[0],
                target[1],
                target[2],
                tolerance=DRIVE_TOLERANCE,
            ):
                self.on_nav_waypoint_reached()
            elif self.timer >= MAX_DRIVE_TIME:
                self.stop_wheels()
                print("[YOUBOT SORTER WARNING] Nav waypoint timeout, continuing")
                self.on_nav_waypoint_reached()

        elif self.state == "LOAD_BOX_ON_PLATFORM":
            if self.supervisor_load_box_on_platform():
                self.continue_to_deposit()
            elif self.timer >= self.act_steps(60):
                print("[YOUBOT SORTER WARNING] Box load incomplete, continuing route")
                self.continue_to_deposit()

        elif self.state == "SUPERVISOR_PLACE":
            if self.supervisor_unpack_box_to_shelf():
                self.change_state("UPDATE_INVENTORY")
            elif self.timer >= self.act_steps(60):
                print("[YOUBOT SORTER WARNING] Shelf unpack incomplete, updating inventory")
                self.change_state("UPDATE_INVENTORY")

        elif self.state == "UPDATE_INVENTORY":
            self.update_inventory()
            self.leave_stock_visible_on_shelf()
            if self.active_task:
                sort_signal.mark_task_done(
                    self.project_root, self.active_task["seq"]
                )
            self.completed_product_id = (
                self.active_task["product_id"] if self.active_task else ""
            )
            self.last_sorted_product_id = self.completed_product_id
            self.loaded_cube_defs = []
            self.carried_box_def = ""
            self.active_task = None
            self.begin_post_deposit_navigation(self.completed_product_id)

        self.timer += 1

    def maintain_carried_box(self):
        if not self.carried_box_def:
            return
        product_cubes.resnap_box_to_platform(
            self.robot.getFromDef,
            self.carried_box_def,
            self.get_robot_xyz(),
            self.get_platform_yaw(),
        )

    def run(self):
        while self.robot.step(self.time_step) != -1:
            self.run_state()


if __name__ == "__main__":
    YoubotSorterDemo().run()
