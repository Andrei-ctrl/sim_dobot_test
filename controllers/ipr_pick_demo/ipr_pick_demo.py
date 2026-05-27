from controller import Supervisor
import math
import os
import sys

_LOGIC_DIR = os.path.join(os.path.dirname(__file__), "..", "youbot_restocker_demo")
_CONTROLLERS_DIR = os.path.join(os.path.dirname(__file__), "..")
for path in (_LOGIC_DIR, _CONTROLLERS_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import youbot_restocker_logic as box_logic  # noqa: E402
import box_routing  # noqa: E402
import ipr_spawn_pad  # noqa: E402
import product_routing  # noqa: E402
import spawned_box  # noqa: E402
import spawn_signal  # noqa: E402
import sim_session  # noqa: E402

TIME_STEP = 32
SPAWN_AREA_RADIUS = ipr_spawn_pad.SPAWN_AREA_RADIUS

# IPR parallel gripper: 0 = closed, maxPosition (~1.22) = open.
GRIPPER_OPEN = 1.2
GRIPPER_CLOSE = 0.0
GRIPPER_MAX = 1.22171
GRIP_CLOSE_TOLERANCE = 0.08


class IprPickDemo:
    def __init__(self):
        self.robot = Supervisor()
        self.root = self.robot.getRoot()
        self.children = self.root.getField("children")
        self.project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

        self.box_spawn_position, self.box_spawn_rotation, pad_ok = (
            ipr_spawn_pad.resolve_spawn_pad(self.robot.getFromDef)
        )
        if pad_ok:
            print(
                "[BOX SPAWNER] Spawn pad: right_pallet_spawner(1) "
                f"({self.box_spawn_position[0]:.3f}, "
                f"{self.box_spawn_position[1]:.3f}, "
                f"{self.box_spawn_position[2]:.3f})"
            )
        else:
            print(
                "[BOX SPAWNER WARNING] DEF IPR_BOX_SPAWN_PAD not found — "
                f"using fallback spawn ({self.box_spawn_position[0]:.3f}, "
                f"{self.box_spawn_position[1]:.3f}, {self.box_spawn_position[2]:.3f})"
            )

        self.box_count = 0
        self.active_box_def = None
        self.pending_spawn = False
        self.spawn_after_time = None
        self.pending_spawn_product_id = ""
        self.pending_spawn_pallet = ""
        self.last_spawn_seq = 0
        self.sim_start_time = self.robot.getTime()
        self.waiting_for_spawn = True
        self.box_limit_logged = False
        self.pick_grip_logged = False

        self.motor_names = [
            "base",
            "upperarm",
            "forearm",
            "wrist",
            "rotational_wrist",
        ]

        self.motors = []

        for name in self.motor_names:
            motor = self.robot.getDevice(name)

            if motor is None:
                print(f"[ERROR] Motor not found: {name}")
            else:
                motor.setVelocity(1)
                self.motors.append(motor)
                print(f"[IPR] Motor loaded: {name}")

        self.gripper_left = self.robot.getDevice("gripper::left")
        self.gripper_right = self.robot.getDevice("gripper::right")
        self.gripper_left_sensor = self.robot.getDevice("gripper::left_sensor")
        self.gripper_right_sensor = self.robot.getDevice("gripper::right_sensor")
        self.gripper_sensors_enabled = False
        self.time_step = int(self.robot.getBasicTimeStep())

        for gripper, label in (
            (self.gripper_left, "gripper::left"),
            (self.gripper_right, "gripper::right"),
        ):
            if gripper is None:
                print(f"[ERROR] {label} not found")
            else:
                gripper.setVelocity(0.5)
                print(f"[IPR] Gripper loaded: {label}")

        for sensor, label in (
            (self.gripper_left_sensor, "gripper::left_sensor"),
            (self.gripper_right_sensor, "gripper::right_sensor"),
        ):
            if sensor is None:
                print(f"[IPR WARNING] {label} not found — using timed grip close")
            else:
                sensor.enable(self.time_step)
                self.gripper_sensors_enabled = True

        self.poses = [
            ("home", [0.0, 0.0, 0.0, 0.0, 0.0], GRIPPER_OPEN, 50),
            ("pre_pick_box", [0.0, -2.4, 1, -1, 0.0], GRIPPER_OPEN, 80),
            ("settle_pick", [0.0, -2.4, 1, -1, 0.0], GRIPPER_OPEN, 40),
            ("pick_box", [0.0, -2.4, 1, -1, 0.0], GRIPPER_CLOSE, 200),
            ("lift_box", [0.0, 0.0, 0.0, 0.0, 0.0], GRIPPER_CLOSE, 60),
            ("move_box_to_conveyor", [1.6, -1, 1, -2, 0.0], GRIPPER_CLOSE, 80),
            ("release_box_on_conveyor", [1.6, -1, 1, -2, 0.0], GRIPPER_OPEN, 60),
        ]

        self.pose_index = 0
        self.pose_step = 0
        self.last_announced_pose = None

        self.box_count = self.reserve_next_box_index()

        print("[SPAWNER] Box spawner initialized")
        print("[IPR] Pick demo initialized")
        print("[IPR] Physical grip mode: box is NOT teleported")
        print("[IPR] Waiting at home — spawn only when upstream conveyor scanner triggers")
        self.reset_to_home()

    def clamp_motor_position(self, motor, value):
        if motor is None:
            return value
        lo = motor.getMinPosition()
        hi = motor.getMaxPosition()
        if math.isfinite(lo) and math.isfinite(hi):
            if hi <= lo + 1e-9:
                return lo
            return max(lo, min(hi, value))
        return value

    def reset_to_home(self):
        """Force valid joint targets after world reload (avoids corrupted hidden state)."""
        home_label, home_pose, home_gripper, _ = self.poses[0]
        for motor, value in zip(self.motors, home_pose):
            if motor is not None:
                motor.setPosition(self.clamp_motor_position(motor, value))
        self.set_gripper(home_gripper)
        self.robot.step(TIME_STEP)
        print("[IPR] Reset to home pose")

    def set_pose(self, values):
        for motor, value in zip(self.motors, values):
            if motor is not None:
                motor.setPosition(self.clamp_motor_position(motor, value))

    def set_gripper(self, value, closing=False):
        safe_value = min(GRIPPER_MAX, max(0.0, value))
        velocity = 2.0 if closing else 0.5
        for gripper in (self.gripper_left, self.gripper_right):
            if gripper is not None:
                gripper.setVelocity(velocity)
                gripper.setPosition(self.clamp_motor_position(gripper, safe_value))

    def gripper_position(self, sensor):
        if sensor is None or not self.gripper_sensors_enabled:
            return None
        return sensor.getValue()

    def gripper_closed(self):
        if not self.gripper_sensors_enabled:
            return False
        readings = []
        for sensor in (self.gripper_left_sensor, self.gripper_right_sensor):
            value = self.gripper_position(sensor)
            if value is not None:
                readings.append(value)
        if not readings:
            return False
        return all(value <= GRIP_CLOSE_TOLERANCE for value in readings)

    def reserve_next_box_index(self):
        index = 0
        while self.robot.getFromDef(f"SPAWNED_BOX_{index}") is not None:
            index += 1
        if index > 0:
            print(f"[BOX SPAWNER] Reserved existing defs 0..{index - 1}, next={index}")
        return index

    def refresh_spawn_pad(self):
        position, rotation, _pad_ok = ipr_spawn_pad.resolve_spawn_pad(
            self.robot.getFromDef
        )
        self.box_spawn_position = position
        self.box_spawn_rotation = rotation

    def find_box_at_spawn_area(self):
        return ipr_spawn_pad.box_at_spawn_pad(
            self.robot.getFromDef,
            self.box_spawn_position[:2],
            radius=SPAWN_AREA_RADIUS,
        )

    def box_at_spawn_area(self):
        return self.find_box_at_spawn_area() is not None

    def spawn_box(self):
        live = box_logic.count_live_boxes(self.robot.getFromDef)
        if box_logic.box_limit_reached(live):
            self.pending_spawn = True
            if not self.box_limit_logged:
                print(
                    f"[BOX SPAWNER] At box limit ({live}/{box_logic.MAX_LIVE_BOXES}); "
                    "queued until a box is removed"
                )
                self.box_limit_logged = True
            return False

        self.box_limit_logged = False

        if self.box_at_spawn_area():
            self.pending_spawn = False
            return True

        self.refresh_spawn_pad()
        position = self.box_spawn_position
        rotation = self.box_spawn_rotation

        box_def = f"SPAWNED_BOX_{self.box_count}"
        product_id = self.pending_spawn_product_id or "UNASSIGNED"

        spawned_def, box_uid = spawned_box.spawn_labeled_box(
            self.children,
            self.robot.getFromDef,
            self.project_root,
            box_def,
            position,
            rotation,
            product_id,
            size=spawned_box.DEFAULT_BOX_SIZE,
            mass=spawned_box.DEFAULT_BOX_MASS,
        )

        new_box = self.robot.getFromDef(spawned_def) if spawned_def else None

        if new_box is not None:
            self.active_box_def = spawned_def
            self.pending_spawn = False
            pallet_def = self.pending_spawn_pallet
            if product_id and product_id != "UNASSIGNED":
                if not pallet_def:
                    pallet_def = product_routing.route_for_product_id(product_id)["def"]
                box_routing.assign_box_to_pallet(
                    self.project_root,
                    spawned_def,
                    pallet_def,
                    self.robot.getTime(),
                    box_uid=box_uid,
                )
                print(
                    f"[BOX SPAWNER] Routed {spawned_def} ({box_uid}) -> {pallet_def} "
                    f"({product_id}, task-manager order)"
                )
            print(
                f"[BOX SPAWNER] Spawned {spawned_def} "
                f"[{spawned_box.product_label(product_id)} / {box_uid}] "
                f"on IPR pick pad (right_pallet_spawner(1)) "
                f"({position[0]:.3f}, {position[1]:.3f}, {position[2]:.3f})"
            )
            self.pending_spawn_product_id = ""
            self.pending_spawn_pallet = ""
        else:
            print(f"[BOX SPAWNER ERROR] Could not spawn {box_def}")
            return False

        self.box_count += 1
        return True

    def process_spawn_messages(self):
        signal = spawn_signal.read_signal(self.project_root)
        if signal is None:
            return

        seq = int(signal.get("seq", 0))
        if seq <= self.last_spawn_seq:
            return

        detect_time = float(signal.get("t", self.robot.getTime()))
        now = self.robot.getTime()
        if not sim_session.is_signal_from_current_run(
            detect_time, self.sim_start_time, now
        ):
            return

        self.last_spawn_seq = seq
        trigger_box = signal.get("box_def") or "?"
        product_id = signal.get("product_id") or ""
        triggered_by = signal.get("triggered_by") or "scanner"
        self.pending_spawn_product_id = product_id
        self.pending_spawn_pallet = signal.get("target_pallet") or ""
        self.spawn_after_time = now + box_logic.SPAWN_DELAY_SEC
        self.pending_spawn = True
        if triggered_by == "task_manager" and product_id:
            print(
                f"[BOX SPAWNER] Task manager ordered {product_id}; "
                f"next spawn in {box_logic.SPAWN_DELAY_SEC:.0f}s "
                f"(at t={self.spawn_after_time:.1f})"
            )
        else:
            print(
                f"[BOX SPAWNER] Conveyor scanner saw {trigger_box}; "
                f"next spawn in {box_logic.SPAWN_DELAY_SEC:.0f}s "
                f"(at t={self.spawn_after_time:.1f})"
            )

    def try_scheduled_spawn(self):
        if self.spawn_after_time is None:
            return
        if self.robot.getTime() < self.spawn_after_time:
            return
        if self.box_at_spawn_area():
            self.pending_spawn = False
            self.spawn_after_time = None
            return
        if self.spawn_box():
            self.spawn_after_time = None

    def try_pending_spawn(self):
        self.try_scheduled_spawn()
        if not self.pending_spawn or self.spawn_after_time is not None:
            return
        if box_logic.box_limit_reached(
            box_logic.count_live_boxes(self.robot.getFromDef)
        ):
            return
        if self.box_at_spawn_area():
            self.pending_spawn = False
            return
        self.spawn_box()

    def hold_at_home(self):
        home_label, home_pose, home_gripper, _ = self.poses[0]
        self.set_pose(home_pose)
        self.set_gripper(home_gripper)
        if self.last_announced_pose != "waiting_for_spawn":
            print(
                "[IPR] Waiting at home for upstream conveyor scanner "
                "to trigger next box spawn"
            )
            self.last_announced_pose = "waiting_for_spawn"

    def start_pick_cycle(self, box_def):
        self.active_box_def = box_def
        self.waiting_for_spawn = False
        self.pose_index = 1
        self.pose_step = 0
        self.last_announced_pose = None
        self.pick_grip_logged = False
        print(f"[IPR] Box ready at spawn area ({box_def}), starting pick cycle")

    def pose_ready_to_advance(self, label, duration):
        if label != "pick_box":
            return self.pose_step + 1 >= duration
        min_close_steps = max(40, duration // 3)
        if self.pose_step + 1 < min_close_steps:
            return False
        if self.gripper_closed():
            return True
        return self.pose_step + 1 >= duration

    def run(self):
        while self.robot.step(TIME_STEP) != -1:
            self.process_spawn_messages()
            self.try_pending_spawn()

            if self.pose_index == 0 and not self.box_at_spawn_area():
                self.waiting_for_spawn = True
                self.hold_at_home()
                continue

            if self.waiting_for_spawn and self.box_at_spawn_area():
                self.start_pick_cycle(self.find_box_at_spawn_area())

            label, pose, gripper, duration = self.poses[self.pose_index]

            self.set_pose(pose)
            closing = gripper <= GRIP_CLOSE_TOLERANCE
            self.set_gripper(gripper, closing=closing)

            if label != self.last_announced_pose:
                print(f"[DEBUG] pose={label}, joints={pose}, gripper={gripper}")

                if label == "home":
                    print("[IPR] Home")
                elif label == "pre_pick_box":
                    print("[IPR] Moving toward spawned box")
                elif label == "settle_pick":
                    print("[IPR] Settling at pick pose")
                elif label == "pick_box":
                    print("[IPR] Picking spawned box — closing gripper")
                elif label == "lift_box":
                    print("[IPR] Lifting box")
                elif label == "move_box_to_conveyor":
                    print("[IPR] Moving box to ConveyorBelt")
                elif label == "release_box_on_conveyor":
                    print("[IPR] Releasing box on ConveyorBelt")

                self.last_announced_pose = label

            if label == "pick_box" and self.gripper_closed() and not self.pick_grip_logged:
                left = self.gripper_position(self.gripper_left_sensor)
                right = self.gripper_position(self.gripper_right_sensor)
                print(
                    f"[IPR] Gripper closed "
                    f"(left={left:.3f}, right={right:.3f})"
                )
                self.pick_grip_logged = True

            self.pose_step += 1

            if self.pose_ready_to_advance(label, duration):
                if (
                    label == "pick_box"
                    and self.gripper_sensors_enabled
                    and not self.gripper_closed()
                ):
                    print("[IPR WARNING] Pick timeout — gripper may not be fully closed")
                self.pose_step = 0
                self.pose_index += 1

                if self.pose_index >= len(self.poses):
                    self.pose_index = 0
                    self.waiting_for_spawn = True
                    self.active_box_def = None
                    self.last_announced_pose = None
                    print("[IPR] Cycle complete — waiting for next scanner-triggered spawn")


if __name__ == "__main__":
    IprPickDemo().run()
