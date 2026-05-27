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
import dashboard_client
import sim_session
import youbot_mecanum as mecanum
import youbot_sorter_logic as logic

ACTION_SPEED = 1.0
TELEPORT_NAV = True

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
        self.run_id = sim_session.current_run_id(self.project_root)

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
            sort_signal.last_completed_seq(self.project_root, run_id=self.run_id)
        )
        self.signal_wait_logged = False
        self.queue_wait_log_step = 0
        self.active_task = None
        self.completed_product_id = ""
        self.last_sorted_product_id = ""
        self.sort_succeeded = False
        self.loaded_cube_defs = []
        self.carried_box_def = ""
        self.unpack_attempted = False
        self.last_unpack_count = 0
        self.nav_steps = []
        self.nav_step_index = 0
        self.nav_target = [0.0, 0.0, 0.0]
        self.last_nav_log = ""

        print("[YOUBOT SORTER] Product waypoint navigation v5 (cardinal mecanum, fixed path)")
        if TELEPORT_NAV:
            print("[YOUBOT SORTER] Navigation: supervisor teleport to waypoints (fast path)")
        else:
            print("[YOUBOT SORTER] Navigation: mecanum wheel drive")
        print(
            f"[YOUBOT SORTER] Home ({self.home_translation[0]:.3f}, "
            f"{self.home_translation[1]:.3f}), "
            f"products: {', '.join(logic.PRODUCT_SORT_ROUTES)}"
        )
        print(f"[YOUBOT SORTER] IPC queue: {sort_signal.queue_path(self.project_root)}")
        print(f"[YOUBOT SORTER] Sim run id={self.run_id}")
        print(
            f"[YOUBOT SORTER] Sort baseline last_seq={self.last_sort_seq} "
            f"(pending IPC tasks will be accepted)"
        )
        print(
            "[YOUBOT SORTER] IPC only: task_manager creates sort tasks "
            "(stock_monitoring reports pallet counts only)"
        )
        if self.robot.step(self.time_step) != -1:
            motor_utils.snap_motors(
                (self.robot.getDevice(name), 0.0)
                for name in ("arm1", "arm2", "arm3", "arm4", "arm5")
            )
            motor_utils.snap_motors((grip, 0.0) for grip in self.gripper_motors)

    def active_run_id(self):
        return sim_session.current_run_id(self.project_root)

    def ensure_run_session(self):
        run_id = self.active_run_id()
        if run_id == self.run_id:
            return
        self.run_id = run_id
        self.last_sort_seq = logic.initial_sort_seq_baseline(
            sort_signal.last_completed_seq(self.project_root, run_id=self.run_id)
        )
        self.signal_wait_logged = False
        print(
            f"[YOUBOT SORTER] Session run id={self.run_id} "
            f"(sort baseline last_seq={self.last_sort_seq})"
        )

    def task_from_task_manager(self, parsed):
        return (parsed.get("triggered_by") or "").strip() == "task_manager"

    def log_queue_status(self, force=False):
        if not force and self.timer - self.queue_wait_log_step < self.act_steps(120):
            return
        self.queue_wait_log_step = self.timer
        pending = sort_signal.pending_tasks(
            self.project_root, self.last_sort_seq, run_id=self.run_id
        )
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

    def snap_to_pose(self, xyz):
        """Supervisor snap to calibrated waypoint (translation + home rotation)."""
        self.stop_wheels()
        self.self_node.getField("translation").setSFVec3f(
            [float(xyz[0]), float(xyz[1]), float(xyz[2])]
        )
        self.self_node.getField("rotation").setSFRotation(self.home_rotation)
        self.self_node.resetPhysics()
        self.maintain_carried_box()

    def run_nav_teleport(self):
        """Instantly visit axis waypoints; stop at pickup/deposit/idle actions."""
        while self.nav_step_index < len(self.nav_steps):
            step = self.nav_steps[self.nav_step_index]
            self.snap_to_pose(step["xyz"])
            self.log_nav(step.get("log", ""))
            action = step.get("action", "continue")
            if action in ("pre_pickup", "continue"):
                if not self.advance_nav_step():
                    self.change_state("WAIT_SIGNAL")
                continue
            self.on_nav_waypoint_reached()
            return
        self.change_state("WAIT_SIGNAL")

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
        pending = sort_signal.pending_tasks(
            self.project_root, self.last_sort_seq, run_id=self.run_id
        )
        parsed = logic.next_pending_task(pending, self.last_sort_seq)
        if parsed is not None:
            return parsed
        signal = sort_signal.read_signal(self.project_root)
        should_run, parsed = logic.should_process_signal(
            signal, self.last_sort_seq, run_id=self.run_id
        )
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
        if not shelf_mon.shelf_monitoring_ready(self.project_root, run_id=self.run_id):
            return False, "waiting for shelf counts"
        counts = shelf_mon.read_counts(self.project_root, run_id=self.run_id)
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
            if not self.task_from_task_manager(parsed):
                self.skip_sort_task(
                    parsed,
                    f"not from task_manager (by={parsed.get('triggered_by') or '?'})",
                )
                continue
            ok, reason = self.can_execute_sort_task(parsed)
            if ok:
                return parsed
            if "waiting" in reason:
                return None
            self.skip_sort_task(parsed, reason)

    def fail_sort_task(self, reason):
        if not self.active_task:
            return
        seq = int(self.active_task.get("seq", 0))
        product_id = self.active_task.get("product_id", "?")
        sim_time = self.robot.getTime()
        print(f"[YOUBOT SORTER] Sort failed seq={seq} product={product_id}: {reason}")
        sort_signal.mark_task_done(
            self.project_root, seq, status="failed", sim_time=sim_time
        )
        self.last_sort_seq = max(self.last_sort_seq, seq)
        dashboard_client.post_robot_failure(
            self.project_root,
            "sorter",
            reason,
            source="sorter",
            sim_time=sim_time,
            product_id=product_id,
            seq=seq,
        )
        self.active_task = None
        self.carried_box_def = ""
        self.loaded_cube_defs = []
        self.sort_succeeded = False
        self.change_state("WAIT_SIGNAL")

    def report_sorter_warning(self, reason):
        dashboard_client.post_event(
            self.project_root,
            {
                "event": "robot_warning",
                "robot": "sorter",
                "reason": reason,
                "t": self.robot.getTime(),
            },
            source="sorter",
        )

    def skip_pending_sorts_if_shelf_full(self, product_id):
        if not shelf_mon.shelf_monitoring_ready(self.project_root, run_id=self.run_id):
            return
        counts = shelf_mon.read_counts(self.project_root, run_id=self.run_id)
        current = int(counts.get(product_id, 0))
        if shelf_mon.can_accept_sort(current, product_id):
            return
        skipped = sort_signal.skip_open_tasks_for_product(
            self.project_root, product_id, run_id=self.run_id
        )
        if skipped:
            self.last_sort_seq = max(self.last_sort_seq, max(skipped))
            print(
                f"[YOUBOT SORTER] Cleared {len(skipped)} pending sort task(s) for "
                f"{product_id} — shelf full ({current}/"
                f"{shelf_mon.max_slots_for_product(product_id)})"
            )

    def accept_sort_task(self, parsed, *, source_hint=""):
        self.signal_wait_logged = False
        self.unpack_attempted = False
        self.last_unpack_count = 0
        self.last_sort_seq = parsed["seq"]
        self.active_task = parsed
        self.sort_succeeded = False
        self.loaded_cube_defs = list(parsed.get("cube_defs") or [])
        task_type = parsed.get("task_type", "stock_pallet")
        reason = parsed.get("reason", "")
        source = source_hint or (parsed.get("triggered_by") or "task_manager")
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
        self.ensure_run_session()
        parsed = self.next_executable_sort_task()
        if parsed is None:
            if not self.signal_wait_logged:
                self.signal_wait_logged = True
                print(
                    "[YOUBOT SORTER] Waiting for sort task via IPC (task_manager)"
                )
            self.log_queue_status()
            return False

        self.accept_sort_task(parsed)
        self.start_pickup_for_active_task()
        return True

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

    def node_world_position(self, node):
        if node.getTypeName() not in shelf_mon.PRODUCT_TYPE_NAMES:
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

    def walk_shelf_field(self, field, entries, next_index):
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
            if type_name in shelf_mon.PRODUCT_TYPE_NAMES:
                pos = self.node_world_position(node)
                if pos is not None and shelf_mon.in_shelf_bank(pos):
                    entries.append((next_index, type_name, pos))
                    next_index += 1
            try:
                children = node.getField("children")
            except (AttributeError, RuntimeError):
                children = None
            if children is not None:
                next_index = self.walk_shelf_field(children, entries, next_index)
            index += 1
        return next_index

    def collect_shelf_node_entries(self):
        entries = []
        self.walk_shelf_field(self.root.getField("children"), entries, 0)
        return entries

    def supervisor_unpack_box_to_shelf(self):
        if not self.active_task:
            return False
        if self.unpack_attempted:
            return self.last_unpack_count >= int(
                self.active_task.get("cube_count", logic.BOTTLES_PER_BOX)
            )

        product_id = self.active_task["product_id"]
        count = int(self.active_task.get("cube_count", logic.BOTTLES_PER_BOX))
        shelf_base = self.get_shelf_base(product_id)
        route = product_routing.route_for_product_id(product_id)
        box_def = self.carried_box_def or self.active_task.get("box_def", "")

        shelf_entries = self.collect_shelf_node_entries()
        operation_index, target_slots = shelf_mon.find_placement_slots(
            shelf_entries, product_id, count=count
        )
        if not target_slots:
            print(
                f"[YOUBOT SORTER] No empty shelf row for {product_id} — "
                "skipping placement"
            )
            self.unpack_attempted = True
            self.last_unpack_count = 0
            return False

        print(
            f"[YOUBOT SORTER] Target shelf row: {logic.shelf_row_label(operation_index)} "
            f"({len(target_slots)} empty slot(s))"
        )

        self.unpack_attempted = True
        spawned = product_cubes.unpack_box_to_shelf(
            self.children,
            self.robot.getFromDef,
            box_def,
            shelf_base=shelf_base,
            product_id=product_id,
            count=count,
            operation_index=operation_index,
            slot_positions=target_slots,
        )
        self.last_unpack_count = len(spawned)
        self.loaded_cube_defs = spawned
        self.carried_box_def = ""
        self.active_task["shelf_operation_index"] = operation_index
        print(
            f"[YOUBOT SORTER] Unpacked box to {route['shelf_name']} "
            f"({logic.shelf_row_label(operation_index)} row, "
            f"operation {operation_index + 1}/{logic.SHELF_MAX_SORT_OPERATIONS}): "
            f"{len(spawned)}/{count} bottles"
        )
        for index, slot in enumerate(target_slots[: len(spawned)]):
            print(
                f"[YOUBOT SORTER]   bottle {index + 1} -> "
                f"({slot[0]:.4f}, {slot[1]:.4f}, {slot[2]:.4f})"
            )
        return self.last_unpack_count >= count

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
        operation_index = self.active_task.get("shelf_operation_index")
        ops = logic.increment_shelf_operation(
            inventory, product_id, operation_index=operation_index
        )
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
            if TELEPORT_NAV:
                self.run_nav_teleport()
            else:
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
                    self.report_sorter_warning("nav waypoint timeout")
                    self.on_nav_waypoint_reached()

        elif self.state == "LOAD_BOX_ON_PLATFORM":
            if self.supervisor_load_box_on_platform():
                self.sort_succeeded = False
                self.continue_to_deposit()
            elif self.timer >= self.act_steps(60):
                print("[YOUBOT SORTER WARNING] Box load incomplete")
                self.fail_sort_task("box load incomplete — box missing or not on platform")

        elif self.state == "SUPERVISOR_PLACE":
            if self.unpack_attempted and self.last_unpack_count <= 0:
                self.fail_sort_task("shelf full — no empty row for placement")
            elif self.supervisor_unpack_box_to_shelf():
                self.sort_succeeded = True
                self.change_state("UPDATE_INVENTORY")
            elif self.unpack_attempted:
                self.fail_sort_task("shelf unpack incomplete")
            elif self.timer >= self.act_steps(60):
                print("[YOUBOT SORTER WARNING] Shelf unpack incomplete")
                self.fail_sort_task("shelf unpack incomplete")

        elif self.state == "UPDATE_INVENTORY":
            if self.sort_succeeded:
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
                self.skip_pending_sorts_if_shelf_full(self.completed_product_id)
            else:
                if self.active_task:
                    self.fail_sort_task("sort did not complete placement")
                    self.timer += 1
                    return
            self.loaded_cube_defs = []
            self.carried_box_def = ""
            completed = self.completed_product_id
            self.active_task = None
            self.begin_post_deposit_navigation(completed)

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
