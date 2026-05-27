import math
import os
import sys

from controller import Supervisor

_LOGIC_DIR = os.path.dirname(os.path.abspath(__file__))
_CONTROLLERS_DIR = os.path.join(_LOGIC_DIR, "..")
_SORTER_DIR = os.path.join(_CONTROLLERS_DIR, "youbot_sorter_demo")
for path in (_LOGIC_DIR, _CONTROLLERS_DIR, _SORTER_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import youbot_restocker_logic as detection
import box_routing
import motor_utils
import dashboard_client
import product_routing
import youbot_mecanum as mecanum
import conveyor_intrusion
import restocking_task_manager as task_mgr
import conveyor_unknown_signal

ACTION_SPEED = 1.0

GRIPPER_OPEN = 1.2
GRIPPER_CLOSE = 0.0
GRIPPER_MAX = 1.22171
ARM_PICK_VELOCITY = 1.5

# Tuned at conveyor pick slot with youBot at calibrated home pose.
REF_PICK = [0.0, -1.13, -0.2, 0.0, 0.0]
HOVER_OFFSET = [0.0, 0.05, 0.02, 0.0, 0.0]
PRE_PICK_OFFSET = [0.0, 0.18, 0.08, 0.0, 0.0]
LIFT_OFFSET = [0.0, 0.35, 0.10, 0.05, 0.0]
CARRY_OFFSET = [0.0, 0.28, 0.06, 0.0, 0.0]

PICKUP_X_MAX = -1.05
CONVEYOR_Y = detection.CONVEYOR_Y
Y_TOLERANCE = detection.Y_TOLERANCE
Z_MIN = detection.Z_MIN
Z_MAX = detection.Z_MAX

SENSOR_CLOSE = detection.SENSOR_CLOSE
DIAG_LOG_INTERVAL = 200

PALLET_APPROACH_OFFSET = [0.85, 0.0]
SCANNER_XY = [-0.01, 1.09]
SCANNER_RADIUS = 0.8
DRIVE_TOLERANCE = 0.22
DRIVE_SPEED = 0.55 * ACTION_SPEED
TURN_TOLERANCE = 0.06
HEADING_ALIGN = 0.28
MAX_TURN_TIME = int(4000 / ACTION_SPEED)
MAX_DRIVE_TIME = int(12000 / ACTION_SPEED)
MAX_RETURN_DRIVE_TIME = int(12000 / ACTION_SPEED)
# Calibrated wait pose (STORE_YOUBOT_RESTOCKER in Webots).
RESTOCKER_HOME_TRANSLATION = detection.RESTOCKER_HOME_TRANSLATION
RESTOCKER_HOME_ROTATION = detection.RESTOCKER_HOME_ROTATION
RESTOCKER_HOME_XY = detection.RESTOCKER_HOME_XY
HOME_DRIVE_TOLERANCE = 0.05
NEAR_CONVEYOR_RADIUS = 0.45
SEARCH_FORWARD_STEPS = int(60 / ACTION_SPEED)
SEARCH_LEFT_STEPS = int(45 / ACTION_SPEED)
SEARCH_FORWARD_SPEED = 0.18 * ACTION_SPEED
SEARCH_STRAFE_SPEED = 0.16 * ACTION_SPEED
MAX_SEARCH_CYCLES = 2
SEARCH_DELAY_SEC = detection.SEARCH_DELAY_SEC

WHEEL_RADIUS = mecanum.WHEEL_RADIUS
WHEEL_MAX_VEL = mecanum.WHEEL_MAX_VEL
TURN_OMEGA = 0.85 * ACTION_SPEED
STRAFE_SPEED = 0.35 * ACTION_SPEED

PICK_CYCLE_STATES = frozenset(
    {
        "OPEN_GRIP",
        "PRE_PICK",
        "APPROACH",
        "DESCEND",
        "CLOSE",
        "SETTLE",
        "LIFT",
        "CARRY",
        "TURN_180",
        "DRIVE_TO_PALLET",
        "OVER_PALLET",
        "PLACE_ON_PALLET",
        "RELEASE_ON_PALLET",
        "VERIFY_RESTOCK",
    }
)

class YoubotRestockerDemo:
    def __init__(self):
        self.robot = Supervisor()
        self.time_step = int(self.robot.getBasicTimeStep())
        self.self_node = self.robot.getSelf()
        self.project_root = os.path.dirname(os.path.dirname(_LOGIC_DIR))
        self.children = self.robot.getRoot().getField("children")

        self.arm_names = ["arm1", "arm2", "arm3", "arm4", "arm5"]
        self.arms = [self.robot.getDevice(name) for name in self.arm_names]
        self.wheels = [self.robot.getDevice(f"wheel{i}") for i in range(1, 5)]
        self.gripper_left = self.robot.getDevice("gripper::left")
        self.gripper_right = self.robot.getDevice("gripper::right")
        self.box_sensor = self.robot.getDevice("box distance sensor")

        for motor in self.arms:
            if motor is not None:
                motor.setVelocity(0.5 * ACTION_SPEED)

        for gripper in (self.gripper_left, self.gripper_right):
            if gripper is not None:
                max_vel = gripper.getMaxVelocity()
                if max_vel > 0:
                    gripper.setVelocity(min(max_vel, 2.0 * ACTION_SPEED))
                else:
                    gripper.setVelocity(2.0 * ACTION_SPEED)

        missing_wheels = [i + 1 for i, wheel in enumerate(self.wheels) if wheel is None]
        if missing_wheels:
            print(f"[YOUBOT RESTOCKER WARNING] Missing wheels: {missing_wheels}")
        else:
            for wheel in self.wheels:
                wheel.setPosition(float("inf"))
                wheel.setVelocity(0.0)
            print("[YOUBOT RESTOCKER] Mecanum wheels ready (velocity mode)")

        if self.box_sensor is not None:
            self.box_sensor.enable(self.time_step)
            print(
                f"[YOUBOT RESTOCKER] Box distance sensor enabled "
                f"(close threshold={SENSOR_CLOSE})"
            )
        else:
            print("[YOUBOT RESTOCKER WARNING] Box distance sensor not found on arm5")

        self.gripper_open = GRIPPER_OPEN
        self.gripper_close = GRIPPER_CLOSE
        if self.gripper_left is not None:
            max_pos = self.gripper_left.getMaxPosition()
            if max_pos > 0:
                self.gripper_open = min(max_pos, GRIPPER_OPEN)
                self.gripper_close = max(
                    self.gripper_left.getMinPosition() if math.isfinite(self.gripper_left.getMinPosition()) else 0.0,
                    min(max_pos, GRIPPER_CLOSE),
                )

        self.joint_limits = []
        for motor in self.arms:
            if motor is None:
                self.joint_limits.append((None, None))
            else:
                self.joint_limits.append((motor.getMinPosition(), motor.getMaxPosition()))

        self.wait_pose = self.clamp_pose([0.0, -0.95, -0.35, 0.0, 0.0])
        self.over_pallet_pose = self.clamp_pose([0.55, -0.85, -0.25, 0.15, 0.0])
        self.place_on_pallet_pose = self.clamp_pose([0.55, -1.05, -0.2, 0.25, 0.0])

        print("[YOUBOT RESTOCKER] Wheel drive + physical carry (no supervisor box hold)")
        print(f"[YOUBOT RESTOCKER] Action speed x{ACTION_SPEED:.0f}")

        self.state = "WAIT_BOX"
        self.timer = 0
        self.pick_count = 0
        self.completed_boxes = set()
        self.active_box_def = None
        self.active_box_pos = None
        self.active_target_pallet = product_routing.DEFAULT_PALLET_DEF
        self.derive_motion_poses(self.clamp_pose(REF_PICK))
        self.drive_target = [0.0, 0.0]
        self.departure_heading = 0.0
        self.home_heading = None
        self.conveyor_pick_heading = None
        self.conveyor_box_detected = False
        self.pending_box_def = None
        self.turn_debugged = False
        self.return_aligned_done = False
        self.waiting_for_box = True
        self.home_translation = list(RESTOCKER_HOME_TRANSLATION)
        self.home_rotation = list(RESTOCKER_HOME_ROTATION)
        self.ensure_calibrated_home()
        self.snap_to_home_pose()
        self.search_phase = 0
        self.search_step_timer = 0
        self.search_cycle_count = 0
        self.search_allowed = False
        self.conveyor_detect_time = None
        self.home_pose_logged = False
        self.conveyor_intrusion_key = None
        self.conveyor_blocked = False
        self.restock_verify_pallet = None
        self.restock_count_before = 0
        self.restock_count_before_release = 0
        self.restock_pending_box_def = None
        self.restock_cycle_active = False
        self.tracked_pick_box_def = None

    def setup_hardcoded_pick_poses(self):
        """Use calibrated REF_PICK only — no box/sensor-based pose adjustment."""
        self.derive_motion_poses(self.clamp_pose(REF_PICK))
        print(
            f"[YOUBOT RESTOCKER] Hardcoded pick arm pose "
            f"[{REF_PICK[0]:.3f}, {REF_PICK[1]:.3f}, {REF_PICK[2]:.3f}, "
            f"{REF_PICK[3]:.3f}, {REF_PICK[4]:.3f}]"
        )

    def act_steps(self, steps):
        """Scale state-machine durations (ACTION_SPEED=2 → half the steps)."""
        return max(1, int(steps / ACTION_SPEED))

    def pick_steps(self, steps):
        """Arm pick sequence uses full timing so joints reach target before grip."""
        return max(1, steps)

    def normalize_angle(self, angle):
        while angle > math.pi:
            angle -= 2.0 * math.pi
        while angle < -math.pi:
            angle += 2.0 * math.pi
        return angle

    def clamp_pose(self, values):
        clamped = []
        for i, value in enumerate(values):
            lo, hi = self.joint_limits[i]
            if lo is not None and hi is not None:
                clamped.append(max(lo, min(hi, value)))
            else:
                clamped.append(value)
        return clamped

    def set_arm(self, values):
        for motor, value in zip(self.arms, self.clamp_pose(values)):
            if motor is not None:
                motor.setVelocity(ARM_PICK_VELOCITY)
                motor_utils.set_joint_position(motor, value)

    def set_gripper(self, value, closing=False):
        safe = max(0.0, min(GRIPPER_MAX, value))
        velocity = 2.0 if closing else None
        for gripper in (self.gripper_left, self.gripper_right):
            if gripper is None:
                continue
            if velocity is not None:
                max_vel = gripper.getMaxVelocity()
                gripper.setVelocity(min(max_vel, velocity) if max_vel > 0 else velocity)
            motor_utils.set_joint_position(gripper, safe)

    def stop_wheels(self):
        for wheel in self.wheels:
            if wheel is not None:
                wheel.setVelocity(0.0)

    def get_robot_xy(self):
        pos = self.self_node.getField("translation").getSFVec3f()
        return pos[0], pos[1]

    def get_robot_yaw(self):
        orientation = self.self_node.getOrientation()
        return math.atan2(orientation[3], orientation[0])

    def set_wheel_velocities(self, wheel_speeds):
        for wheel, speed in zip(self.wheels, wheel_speeds):
            if wheel is None:
                continue
            clamped = max(-WHEEL_MAX_VEL, min(WHEEL_MAX_VEL, speed))
            wheel.setVelocity(clamped)

    def set_mecanum(self, vx, vy, omega):
        speeds = mecanum.clamp_wheel_speeds(mecanum.wheel_speeds(vx, vy, omega))
        self.set_wheel_velocities(speeds)

    def turn_in_place(self, counter_clockwise=True):
        sign = 1.0 if counter_clockwise else -1.0
        self.set_mecanum(0.0, 0.0, sign * TURN_OMEGA)
        if not self.turn_debugged:
            direction = "CCW" if counter_clockwise else "CW"
            print(
                f"[YOUBOT RESTOCKER] Turn {direction} in place "
                f"(omega={sign * TURN_OMEGA:.2f} rad/s)"
            )
            self.turn_debugged = True

    def drive_forward(self, speed, heading_correction=0.0):
        self.set_mecanum(speed, 0.0, 0.8 * heading_correction)

    def drive_backward(self, speed, heading_correction=0.0):
        self.drive_forward(-abs(speed), heading_correction)

    def strafe_left(self, speed=None):
        self.set_mecanum(0.0, -(speed if speed is not None else STRAFE_SPEED), 0.0)

    def strafe_right(self, speed=None):
        self.set_mecanum(0.0, speed if speed is not None else STRAFE_SPEED, 0.0)

    def heading_error(self, target_heading):
        return self.normalize_angle(target_heading - self.get_robot_yaw())

    def turn_to_heading(self, target_heading):
        error = self.heading_error(target_heading)
        if abs(error) < TURN_TOLERANCE:
            self.stop_wheels()
            return True
        self.turn_in_place(counter_clockwise=(error > 0))
        return False

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
        r00 = t * x * x + cos_a
        r10 = t * x * y + z * sin_a
        return math.atan2(r10, r00)

    def get_home_heading(self):
        return self.rotation_field_to_yaw(self.home_rotation)

    def ensure_calibrated_home(self):
        """Always return and wait at the fixed calibrated pose."""
        self.home_translation = list(RESTOCKER_HOME_TRANSLATION)
        self.home_rotation = list(RESTOCKER_HOME_ROTATION)
        self.home_heading = self.get_home_heading()
        self.conveyor_pick_heading = self.home_heading

    def capture_detected_home_pose(self):
        """Log robot pose at pick; home target stays at calibrated RESTOCKER_HOME_*."""
        pos = self.self_node.getField("translation").getSFVec3f()
        rot = self.self_node.getField("rotation").getSFRotation()
        print(
            f"[YOUBOT RESTOCKER] Pick triggered at robot pose "
            f"({pos[0]:.5f}, {pos[1]:.5f}, {pos[2]:.5f}); "
            f"return/wait target remains calibrated home "
            f"({RESTOCKER_HOME_TRANSLATION[0]:.5f}, "
            f"{RESTOCKER_HOME_TRANSLATION[1]:.5f}, "
            f"{RESTOCKER_HOME_TRANSLATION[2]:.5f})"
        )
        self.ensure_calibrated_home()

    def is_near_conveyor(self):
        robot_x, robot_y = self.get_robot_xy()
        home_x, home_y = self.get_conveyor_home_xy()
        return math.hypot(robot_x - home_x, robot_y - home_y) <= NEAR_CONVEYOR_RADIUS

    def reset_wait_for_box_state(self):
        """Clear conveyor/search tracking for a new wait cycle."""
        self.conveyor_box_detected = False
        self.pending_box_def = None
        self.search_allowed = False
        self.conveyor_detect_time = None
        self.ensure_calibrated_home()
        self.home_pose_logged = False

    def update_search_allowed(self):
        sim_time = self.robot.getTime()
        was_allowed = self.search_allowed
        self.search_allowed = detection.search_allowed(
            self.conveyor_box_detected,
            self.conveyor_detect_time,
            sim_time,
        )
        if self.search_allowed and not was_allowed:
            elapsed = sim_time - self.conveyor_detect_time
            print(
                f"[YOUBOT RESTOCKER] Search enabled after {elapsed:.1f}s "
                f"(conveyor scanner saw {self.pending_box_def})"
            )

    def has_box_at_pick_slot(self):
        _, box_def, _ = self.find_pickable_box()
        return box_def is not None

    def should_start_search(self):
        self.update_search_allowed()
        if self.has_box_at_pick_slot():
            return False
        return self.is_near_conveyor() and self.search_allowed

    def maybe_start_conveyor_search(self, context=""):
        """Enter search only if upstream conveyor scanner saw a box and delay passed."""
        if self.has_box_at_pick_slot():
            return False
        if self.should_start_search():
            suffix = f" ({context})" if context else ""
            print(f"[YOUBOT RESTOCKER] Starting conveyor search{suffix}")
            self.change_state("SEARCH_AT_CONVEYOR")
            return True
        if self.is_near_conveyor() and self.conveyor_box_detected:
            remaining = SEARCH_DELAY_SEC - (
                self.robot.getTime() - (self.conveyor_detect_time or 0)
            )
            if self.timer % DIAG_LOG_INTERVAL == 0 and remaining > 0:
                print(
                    f"[YOUBOT RESTOCKER] Waiting for {self.pending_box_def} "
                    f"at pick slot (search in {remaining:.0f}s)"
                )
        elif self.is_near_conveyor() and self.timer % DIAG_LOG_INTERVAL == 0:
            print(
                "[YOUBOT RESTOCKER] No upstream conveyor scan — "
                "holding position (search disabled)"
            )
        return False

    def run_conveyor_search(self):
        """Near belt with no box: one short forward nudge, brief left strafe, then stop."""
        phase_names = ("forward", "left")
        phase = phase_names[self.search_phase % 2]
        step_limit = (
            SEARCH_FORWARD_STEPS if phase == "forward" else SEARCH_LEFT_STEPS
        )
        if phase == "forward":
            self.drive_forward(SEARCH_FORWARD_SPEED)
        else:
            self.strafe_left(SEARCH_STRAFE_SPEED)

        self.search_step_timer += 1
        if self.search_step_timer >= step_limit:
            self.search_step_timer = 0
            self.search_phase += 1
            if self.search_phase >= len(phase_names):
                self.search_phase = 0
                self.search_cycle_count += 1
                self.stop_wheels()
                print(
                    f"[YOUBOT RESTOCKER] Conveyor search cycle "
                    f"{self.search_cycle_count}/{MAX_SEARCH_CYCLES} complete"
                )
            else:
                next_phase = phase_names[self.search_phase]
                print(f"[YOUBOT RESTOCKER] Conveyor search: next move -> {next_phase}")

    def abort_search_and_return_home(self, reason):
        self.stop_wheels()
        self.search_phase = 0
        self.search_step_timer = 0
        self.search_cycle_count = 0
        self.snap_to_home_pose()
        print(f"[YOUBOT RESTOCKER] Search ended — {reason}")
        self.change_state("WAIT_BOX")

    def is_at_home_position(self):
        robot_x, robot_y = self.get_robot_xy()
        home_x, home_y = self.get_conveyor_home_xy()
        pos_ok = math.hypot(robot_x - home_x, robot_y - home_y) <= HOME_DRIVE_TOLERANCE
        heading_ok = abs(self.heading_error(self.get_home_heading())) <= TURN_TOLERANCE
        return pos_ok and heading_ok

    def stabilize_arm_after_snap(self):
        """Re-command arm/gripper after resetPhysics so joints don't stay limp."""
        if self.state in ("OPEN_GRIP", "PRE_PICK", "APPROACH", "DESCEND", "CLOSE", "SETTLE", "LIFT"):
            self.set_arm(getattr(self, "pick_pose", self.wait_pose))
            self.set_gripper(self.gripper_close, closing=True)
        elif self.state in (
            "CARRY", "TURN_180", "DRIVE_TO_PALLET", "OVER_PALLET",
            "PLACE_ON_PALLET", "RELEASE_ON_PALLET",
        ):
            self.set_arm(self.carry_pose)
            self.set_gripper(self.gripper_close, closing=True)
        else:
            self.set_arm(self.conveyor_idle_arm_pose())
            self.set_gripper(self.gripper_open)

    def report_failure(self, reason, **fields):
        print(f"[YOUBOT RESTOCKER] RESTOCK FAILURE → dashboard: {reason}")
        posted = dashboard_client.post_robot_failure(
            self.project_root,
            "restocker",
            reason,
            source="restocker",
            sim_time=self.robot.getTime(),
            **fields,
        )
        if not posted:
            print("[YOUBOT RESTOCKER WARNING] Dashboard POST failed (is dashboard_server.py running?)")

    def box_def_alive(self, box_def):
        if not box_def:
            return False
        node = self.robot.getFromDef(box_def)
        if node is None:
            return False
        try:
            pos = product_routing.node_world_xyz(node)
            if pos is None:
                return False
            if abs(pos[0]) > 500 or abs(pos[1]) > 500:
                return False
            return True
        except (AttributeError, RuntimeError, TypeError):
            return False

    def box_near_robot(self, box_def, max_dist=1.35):
        node = self.robot.getFromDef(box_def)
        if node is None:
            return False
        pos = product_routing.node_world_xyz(node)
        if pos is None:
            return False
        rx, ry = self.get_robot_xy()
        return math.hypot(pos[0] - rx, pos[1] - ry) <= max_dist

    def active_restock_box_def(self):
        return (
            self.restock_pending_box_def
            or self.tracked_pick_box_def
            or self.active_box_def
        )

    def end_restock_cycle(self):
        self.restock_cycle_active = False
        self.tracked_pick_box_def = None

    def snap_to_home_pose(self, log=True):
        """Align exactly to the calibrated conveyor home pose after wheel navigation."""
        self.stop_wheels()
        self.self_node.getField("translation").setSFVec3f(self.home_translation)
        self.self_node.getField("rotation").setSFRotation(self.home_rotation)
        self.self_node.resetPhysics()
        self.stabilize_arm_after_snap()
        if log:
            print(
                f"[YOUBOT RESTOCKER] Snapped to home "
                f"({self.home_translation[0]:.5f}, "
                f"{self.home_translation[1]:.5f}, "
                f"{self.home_translation[2]:.5f})"
            )

    def capture_home_heading(self):
        """Log calibrated home target once per wait cycle."""
        self.ensure_calibrated_home()
        if self.home_pose_logged:
            return
        self.home_pose_logged = True
        print(
            f"[YOUBOT RESTOCKER] Wait pose "
            f"({self.home_translation[0]:.5f}, {self.home_translation[1]:.5f}), "
            f"heading {math.degrees(self.home_heading):.2f} deg"
        )

    def drive_toward_xy(self, target_x, target_y, tolerance=DRIVE_TOLERANCE):
        robot_x, robot_y = self.get_robot_xy()
        dx = target_x - robot_x
        dy = target_y - robot_y
        distance = math.hypot(dx, dy)
        if distance < tolerance:
            self.stop_wheels()
            return True

        target_heading = math.atan2(dy, dx)
        error = self.heading_error(target_heading)
        vx, vy, omega = mecanum.turn_forward_cmd(
            distance,
            error,
            DRIVE_SPEED,
            heading_align=HEADING_ALIGN,
        )
        self.set_mecanum(vx, vy, omega)
        return False

    def get_pallet_target_xy(self, pallet_def=None):
        pallet_def = pallet_def or self.active_target_pallet
        route = product_routing.route_for_pallet_def(pallet_def)
        pallet = self.robot.getFromDef(pallet_def)
        if pallet is not None:
            position = pallet.getField("translation").getSFVec3f()
            return [
                position[0] + PALLET_APPROACH_OFFSET[0],
                position[1] + PALLET_APPROACH_OFFSET[1],
            ]
        return list(route["approach_xy"])

    def load_box_routing(self, box_def):
        assignment = box_routing.read_assignment(self.project_root, box_def)
        if assignment is not None:
            return assignment
        route = product_routing.route_for_box_def(box_def)
        return {
            "target_pallet": route["def"],
            "product_id": route["product_id"],
            "shelf_name": route["shelf_name"],
        }

    def get_conveyor_home_xy(self):
        return [self.home_translation[0], self.home_translation[1]]

    def box_in_scanner_zone(self, pos):
        return detection.box_in_scanner_zone(pos)

    def remove_box_from_world(self, box_def):
        if not box_def:
            return
        box = self.robot.getFromDef(box_def)
        if box is None:
            return
        box.remove()
        print(f"[YOUBOT RESTOCKER] Removed {box_def} from world (delivered to pallet)")

    def iter_tracked_boxes(self):
        for prefix in ("SPAWNED_BOX_", "BOX_"):
            for i in range(100):
                box_def = f"{prefix}{i}"
                box = self.robot.getFromDef(box_def)
                if box is None:
                    continue
                pos = box.getField("translation").getSFVec3f()
                yield box_def, pos, box

    def get_detection_snapshot(self):
        boxes = [(box_def, pos) for box_def, pos, _ in self.iter_tracked_boxes()]
        sensor_val = (
            self.box_sensor.getValue() if self.box_sensor is not None else None
        )
        robot_xy = self.get_robot_xy()
        home_xy = self.get_conveyor_home_xy()
        diag = detection.evaluate_detection(
            boxes=boxes,
            completed_boxes=self.completed_boxes,
            sensor_value=sensor_val,
            sensor_present=self.box_sensor is not None,
            robot_xy=robot_xy,
            home_xy=home_xy,
            conveyor_box_detected=self.conveyor_box_detected,
            pending_box_def=self.pending_box_def,
        )
        diag["robot_xy"] = robot_xy
        return diag

    def log_detection_snapshot(self, reason=""):
        diag = self.get_detection_snapshot()
        suffix = f" ({reason})" if reason else ""
        print(detection.format_detection_log(diag) + suffix)

    def conveyor_sensor_triggered(self):
        """Stage 1: box entered the upstream conveyor scanner zone."""
        for box_def, pos, _ in self.iter_tracked_boxes():
            if box_def in self.completed_boxes:
                continue
            if self.box_in_scanner_zone(pos):
                return True, box_def, pos
        return False, None, None

    def is_at_pick_station(self, pos):
        return detection.is_box_pickable(pos)

    def find_pickable_box(self):
        for box_def, pos, box in self.iter_tracked_boxes():
            if box_def in self.completed_boxes:
                continue
            if self.is_at_pick_station(pos):
                return box, box_def, pos
        return None, None, None

    def begin_pick_cycle(self, box_def, box_pos, stage):
        self.capture_detected_home_pose()
        self.stop_wheels()
        if not self.is_at_home_position():
            self.snap_to_home_pose()
        else:
            self.set_arm(self.wait_pose)
            self.set_gripper(self.gripper_open)
        self.waiting_for_box = False
        self.active_box_def = box_def
        self.active_box_pos = list(box_pos)
        if box_routing.read_assignment(self.project_root, box_def) is None:
            box_routing.assign_box(self.project_root, box_def, self.robot.getTime())
        routing = self.load_box_routing(box_def)
        self.active_target_pallet = routing["target_pallet"]
        self.restock_verify_pallet = routing["target_pallet"]
        self.restock_count_before = task_mgr.count_boxes_on_pallet(
            self.robot.getFromDef,
            self.restock_verify_pallet,
        )
        self.restock_pending_box_def = box_def
        self.tracked_pick_box_def = box_def
        self.restock_cycle_active = True
        self.pick_count += 1
        self.search_allowed = False
        self.conveyor_detect_time = None
        self.conveyor_box_detected = False
        self.pending_box_def = None
        self.search_cycle_count = 0
        self.search_phase = 0
        self.search_step_timer = 0
        self.setup_hardcoded_pick_poses()
        print(
            f"[YOUBOT RESTOCKER] Stage {stage} - starting pick cycle for {box_def} "
            f"at ({box_pos[0]:.3f}, {box_pos[1]:.3f}, {box_pos[2]:.3f}) "
            f"→ {self.active_target_pallet} "
            f"(pallet boxes before={self.restock_count_before})"
        )
        self.change_state("OPEN_GRIP")

    def verify_restock_placement(self):
        """Supervisor check: carried box must exist on the routed pallet (+ count +1)."""
        pallet_def = self.restock_verify_pallet or self.active_target_pallet
        box_def = self.active_restock_box_def()
        count_before = self.restock_count_before_release
        route = product_routing.route_for_pallet_def(pallet_def)
        product_id = route.get("product_id", "")

        delivered, reason = task_mgr.box_delivered_to_pallet(
            self.robot.getFromDef,
            box_def,
            pallet_def,
        )
        count_after = task_mgr.count_boxes_on_pallet(
            self.robot.getFromDef,
            pallet_def,
        )
        delta = count_after - int(count_before)

        if not delivered:
            reason_text = {
                "box_removed": "box removed before pallet drop",
                "not_on_pallet": "box not on target pallet after release",
                "missing_box_def": "restock placement failed: missing box reference",
                "no_position": "box position unavailable after release",
            }.get(reason, f"restock placement failed: {reason}")
            print(
                f"[YOUBOT RESTOCKER] RESTOCK FAILURE on {pallet_def}: {reason_text} "
                f"(box={box_def}, count {count_before} → {count_after})"
            )
            self.report_failure(
                reason_text,
                box_def=box_def or "",
                target_pallet=pallet_def,
                product_id=product_id,
                count_before=count_before,
                count_after=count_after,
                delta=delta,
            )
            self.end_restock_cycle()
            return False

        if delta < 1:
            print(
                f"[YOUBOT RESTOCKER] RESTOCK FAILURE on {pallet_def}: "
                f"pallet count did not increase ({count_before} → {count_after})"
            )
            self.report_failure(
                "restock placement failed: pallet count did not increase",
                box_def=box_def or "",
                target_pallet=pallet_def,
                product_id=product_id,
                count_before=count_before,
                count_after=count_after,
                delta=delta,
            )
            self.end_restock_cycle()
            return False

        print(
            f"[YOUBOT RESTOCKER] Restock verified on {pallet_def}: "
            f"{count_before} → {count_after} (+{delta}), box={box_def} on pallet"
        )
        pallet_counts = task_mgr.pallet_counts_by_product(self.robot.getFromDef)
        task_mgr.save_pallet_counts(
            self.project_root,
            pallet_counts,
            self.robot.getTime(),
            source="restocker",
        )
        dashboard_client.post_event(
            self.project_root,
            {
                "event": "restock_complete",
                "robot": "restocker",
                "t": self.robot.getTime(),
                "box_def": box_def or "",
                "target_pallet": pallet_def,
                "product_id": product_id,
                "count_before": count_before,
                "count_after": count_after,
            },
            source="restocker",
            extra={"pallet_counts": pallet_counts},
        )
        if box_def:
            self.completed_boxes.add(box_def)
        return True

    def abort_restock_failure(self, reason, **fields):
        print(f"[YOUBOT RESTOCKER] RESTOCK FAILURE: {reason}")
        self.report_failure(reason, **fields)
        self.end_restock_cycle()
        self.restock_pending_box_def = None
        self.active_box_def = None
        self.active_box_pos = None
        self.restock_verify_pallet = None
        self.restock_count_before = 0
        self.restock_count_before_release = 0
        self.waiting_for_box = True
        self.reset_wait_for_box_state()
        self.change_state("HOME")

    def monitor_pending_conveyor_box(self):
        """Expected upstream box vanished before the restocker could pick it."""
        box_def = self.pending_box_def
        if not box_def or self.restock_cycle_active:
            return False
        if self.state not in ("WAIT_BOX", "SEARCH_AT_CONVEYOR"):
            return False
        if box_def in self.completed_boxes:
            return False
        if self.box_def_alive(box_def):
            return False
        print(
            f"[YOUBOT RESTOCKER] RESTOCK FAILURE: tracked conveyor box "
            f"{box_def} removed before pick"
        )
        self.report_failure(
            "expected restock box removed before pick",
            box_def=box_def,
            phase=self.state,
        )
        self.pending_box_def = None
        self.conveyor_box_detected = False
        self.conveyor_detect_time = None
        return True

    def monitor_restock_integrity(self):
        if self.monitor_pending_conveyor_box():
            return True

        if not self.restock_cycle_active:
            return False

        box_def = self.active_restock_box_def()
        if not box_def:
            return False

        if not self.box_def_alive(box_def):
            self.abort_restock_failure(
                "box removed before pallet drop",
                box_def=box_def,
                phase=self.state,
                target_pallet=self.restock_verify_pallet or self.active_target_pallet,
            )
            return True

        carry_states = (
            "LIFT",
            "CARRY",
            "TURN_180",
            "DRIVE_TO_PALLET",
            "OVER_PALLET",
            "PLACE_ON_PALLET",
        )
        if self.state in carry_states and not self.box_near_robot(box_def):
            self.abort_restock_failure(
                "box lost during carry (not with robot)",
                box_def=box_def,
                phase=self.state,
                target_pallet=self.restock_verify_pallet or self.active_target_pallet,
            )
            return True

        return False

    def monitor_pick_cycle_integrity(self):
        return self.monitor_restock_integrity()

    def check_conveyor_intrusion(self):
        """Block restock while a foreign object flagged at the upstream scanner remains."""
        signal = conveyor_unknown_signal.read_signal(self.project_root)
        if signal and signal.get("active"):
            if conveyor_intrusion.unknown_still_present(
                self.children,
                signal,
                self.robot.getFromDef,
            ):
                self.conveyor_blocked = True
                label = signal.get("label") or signal.get("object_name") or "unknown"
                if label != self.conveyor_intrusion_key:
                    self.conveyor_intrusion_key = label
                    print(
                        f"[YOUBOT RESTOCKER] Conveyor blocked — unknown object "
                        f"passed scanner: {label}"
                    )
                return True
            conveyor_unknown_signal.clear_signal(self.project_root)

        live_unknowns = conveyor_intrusion.find_unknown_at_scanner(
            self.children,
            self.robot.getFromDef,
            detection.SCANNER_XY,
            detection.SCANNER_RADIUS,
        )
        if live_unknowns:
            obj = live_unknowns[0]
            key = conveyor_intrusion.object_key(obj)
            self.conveyor_blocked = True
            if key != self.conveyor_intrusion_key:
                self.conveyor_intrusion_key = key
                label = conveyor_intrusion.format_object_label(obj)
                conveyor_unknown_signal.write_signal(
                    self.project_root,
                    obj,
                    self.robot.getTime(),
                    scanner_xy=detection.SCANNER_XY,
                )
                print(
                    f"[YOUBOT RESTOCKER EXCEPTION] Unknown object at conveyor scanner: "
                    f"{label}"
                )
                self.report_failure(
                    f"unknown object at conveyor scanner: {label}",
                    object_name=obj.get("name") or "",
                    object_type=obj.get("type_name") or "",
                    position=obj.get("position"),
                    zone="upstream_scanner",
                )
            return True

        self.conveyor_intrusion_key = None
        self.conveyor_blocked = False
        return False

    def run_box_scanners(self):
        """Poll stage-1 zone every step while waiting; log when box enters pick zone."""
        if self.check_conveyor_intrusion():
            if self.timer % DIAG_LOG_INTERVAL == 0:
                print(
                    "[YOUBOT RESTOCKER] Conveyor blocked by unknown object — "
                    "waiting for manual removal"
                )
            return

        triggered, box_def, pos = self.conveyor_sensor_triggered()
        if triggered and box_def not in self.completed_boxes:
            if not self.conveyor_box_detected or self.pending_box_def != box_def:
                print(
                    f"[YOUBOT RESTOCKER] Stage 1 - upstream scanner: {box_def} "
                    f"in scanner zone ({pos[0]:.3f}, {pos[1]:.3f})"
                )
            if self.conveyor_detect_time is None:
                self.conveyor_detect_time = self.robot.getTime()
                print(
                    f"[YOUBOT RESTOCKER] Conveyor scan recorded; search allowed "
                    f"after {SEARCH_DELAY_SEC:.0f}s if box not at pick slot"
                )
            self.conveyor_box_detected = True
            self.pending_box_def = box_def

        _, pick_def, pick_pos = self.find_pickable_box()
        if (
            pick_def is not None
            and not self.conveyor_box_detected
            and self.timer % DIAG_LOG_INTERVAL == 0
        ):
            print(
                f"[YOUBOT RESTOCKER] Stage 1 miss: {pick_def} at pick station "
                f"({pick_pos[0]:.3f}, {pick_pos[1]:.3f}) but not in upstream "
                f"scanner zone ({SCANNER_XY[0]:.3f}, {SCANNER_XY[1]:.3f})"
            )

        if self.timer % DIAG_LOG_INTERVAL == 0:
            diag = self.get_detection_snapshot()
            if not diag["should_pick"] and diag.get("nearest_box_dist") is not None:
                print(
                    f"[YOUBOT RESTOCKER] Waiting for conveyor delivery: "
                    f"nearest={diag.get('nearest_box_def')} "
                    f"dist_to_pick_slot={diag['nearest_box_dist']:.2f}m"
                )
            self.log_detection_snapshot("waiting for box")

    def try_start_pick_cycle(self):
        """Start pick when a box is ready (at conveyor / during search)."""
        if self.conveyor_blocked or self.check_conveyor_intrusion():
            return

        diag = self.get_detection_snapshot()
        if not diag["should_pick"]:
            return

        box_def = diag["pick_def"]
        box_pos = diag["pick_pos"]
        stage = diag["pick_stage"]
        box = self.robot.getFromDef(box_def) if box_def else None
        if box is None:
            print(f"[YOUBOT RESTOCKER WARNING] Pick target {box_def} missing from world")
            self.report_failure("pick target missing from world", box_def=box_def)
            self.log_detection_snapshot("pick target missing")
            return

        if stage == 2:
            print(
                f"[YOUBOT RESTOCKER] Stage 2 - arm sensor "
                f"(value={diag['sensor_value']:.0f} in [{SENSOR_CLOSE},{detection.SENSOR_MAX_VALID}])"
            )
        elif stage == 1:
            print(
                f"[YOUBOT RESTOCKER] Stage 1 - scanner tracked box at pick station"
            )
        elif stage == 3:
            sensor_txt = (
                f"{diag['sensor_value']:.0f}"
                if diag["sensor_value"] is not None
                else "n/a"
            )
            print(
                f"[YOUBOT RESTOCKER] Stage 3 - physical pick "
                f"(box at station, robot near conveyor, sensor={sensor_txt})"
            )
        self.begin_pick_cycle(box_def, box_pos, stage)

    def conveyor_idle_arm_pose(self):
        """Arm staging pose at conveyor home (ready for next pick)."""
        self.derive_motion_poses(self.clamp_pose(REF_PICK))
        return self.pre_pick_pose

    def derive_motion_poses(self, pick_pose):
        pick_pose = self.clamp_pose(pick_pose)
        self.pick_pose = list(pick_pose)
        self.pre_pick_pose = self.clamp_pose([
            pick_pose[i] + PRE_PICK_OFFSET[i] for i in range(len(pick_pose))
        ])
        self.hover_pose = self.clamp_pose([
            pick_pose[i] + HOVER_OFFSET[i] for i in range(len(pick_pose))
        ])
        self.lift_pose = self.clamp_pose([
            pick_pose[i] + LIFT_OFFSET[i] for i in range(len(pick_pose))
        ])
        self.carry_pose = self.clamp_pose([
            pick_pose[0] * 0.25 + CARRY_OFFSET[0],
            pick_pose[1] + CARRY_OFFSET[1],
            pick_pose[2] + CARRY_OFFSET[2],
            pick_pose[3] * 0.4 + CARRY_OFFSET[3],
            pick_pose[4] + CARRY_OFFSET[4],
        ])

    def change_state(self, state):
        wheel_states = (
            "TURN_180",
            "TURN_TO_PICKUP",
            "DRIVE_TO_PALLET",
            "DRIVE_TO_CONVEYOR",
            "SEARCH_AT_CONVEYOR",
        )
        if state not in wheel_states:
            self.stop_wheels()
        if state in ("TURN_180", "TURN_TO_PICKUP"):
            self.turn_debugged = False
        if state == "TURN_TO_PICKUP":
            self.return_aligned_done = False
        if state == "SEARCH_AT_CONVEYOR":
            self.search_phase = 0
            self.search_step_timer = 0
            self.search_cycle_count = 0
        self.state = state
        self.timer = 0

    def lerp_joints(self, start, end, progress):
        progress = max(0.0, min(1.0, progress))
        return self.clamp_pose([
            start[i] + (end[i] - start[i]) * progress
            for i in range(len(start))
        ])

    def run_state(self):
        if self.monitor_pick_cycle_integrity():
            return

        if self.waiting_for_box and self.state in ("WAIT_BOX", "SEARCH_AT_CONVEYOR"):
            self.run_box_scanners()

        if self.state == "WAIT_BOX":
            self.capture_home_heading()
            self.set_arm(self.conveyor_idle_arm_pose())
            self.set_gripper(self.gripper_open)
            if self.waiting_for_box:
                self.try_start_pick_cycle()
            if self.state == "WAIT_BOX" and self.is_near_conveyor():
                self.maybe_start_conveyor_search("wait at conveyor")

        elif self.state == "SEARCH_AT_CONVEYOR":
            self.set_arm(self.conveyor_idle_arm_pose())
            self.set_gripper(self.gripper_open)
            if self.waiting_for_box:
                self.try_start_pick_cycle()
            if self.state != "SEARCH_AT_CONVEYOR":
                pass
            elif self.has_box_at_pick_slot():
                self.abort_search_and_return_home("box at pick slot")
                if self.waiting_for_box:
                    self.try_start_pick_cycle()
            elif self.search_cycle_count >= MAX_SEARCH_CYCLES:
                self.abort_search_and_return_home("search cycle limit reached")
            else:
                self.run_conveyor_search()

        elif self.state == "OPEN_GRIP":
            self.set_arm(self.conveyor_idle_arm_pose())
            self.set_gripper(self.gripper_open)
            if self.timer >= self.pick_steps(40):
                self.change_state("APPROACH")

        elif self.state == "PRE_PICK":
            dur = self.pick_steps(80)
            progress = self.timer / dur
            self.set_arm(self.lerp_joints(self.wait_pose, self.pre_pick_pose, progress))
            self.set_gripper(self.gripper_open)
            if self.timer >= dur:
                self.change_state("APPROACH")

        elif self.state == "APPROACH":
            dur = self.pick_steps(50)
            progress = self.timer / dur
            self.set_arm(self.lerp_joints(self.pre_pick_pose, self.hover_pose, progress))
            self.set_gripper(self.gripper_open)
            if self.timer >= dur:
                self.change_state("DESCEND")

        elif self.state == "DESCEND":
            dur = self.pick_steps(50)
            progress = self.timer / dur
            self.set_arm(self.lerp_joints(self.hover_pose, self.pick_pose, progress))
            self.set_gripper(self.gripper_open)
            if self.timer >= dur:
                print("[YOUBOT RESTOCKER] At hardcoded pick pose, closing gripper")
                self.change_state("CLOSE")

        elif self.state == "CLOSE":
            self.set_arm(self.pick_pose)
            dur = self.pick_steps(80)
            close_progress = min(1.0, self.timer / dur)
            grip = self.gripper_open + (self.gripper_close - self.gripper_open) * close_progress
            self.set_gripper(grip, closing=True)
            if self.timer >= dur:
                self.change_state("SETTLE")

        elif self.state == "SETTLE":
            self.set_arm(self.pick_pose)
            self.set_gripper(self.gripper_close, closing=True)
            if self.timer >= self.pick_steps(120):
                box_def = self.active_restock_box_def()
                if not self.box_def_alive(box_def):
                    self.abort_restock_failure(
                        "box removed before lift from conveyor",
                        box_def=box_def or "",
                        phase=self.state,
                    )
                elif not self.box_near_robot(box_def, max_dist=1.05):
                    self.abort_restock_failure(
                        "box not gripped after close (still on conveyor)",
                        box_def=box_def,
                        phase=self.state,
                    )
                else:
                    print("[YOUBOT RESTOCKER] Grip settled, lifting box")
                    self.change_state("LIFT")

        elif self.state == "LIFT":
            dur = self.pick_steps(90)
            progress = self.timer / dur
            self.set_arm(self.lerp_joints(self.pick_pose, self.lift_pose, progress))
            self.set_gripper(self.gripper_close, closing=True)
            if self.timer >= dur:
                self.change_state("CARRY")

        elif self.state == "CARRY":
            dur = self.act_steps(70)
            progress = self.timer / dur
            self.set_arm(self.lerp_joints(self.lift_pose, self.carry_pose, progress))
            self.set_gripper(self.gripper_close, closing=True)
            if self.timer >= dur:
                self.drive_target = self.get_pallet_target_xy()
                pickup_yaw = self.get_robot_yaw()
                self.departure_heading = self.normalize_angle(pickup_yaw + math.pi)
                robot_x, robot_y = self.get_robot_xy()
                distance = math.hypot(
                    self.drive_target[0] - robot_x,
                    self.drive_target[1] - robot_y,
                )
                print(
                    f"[YOUBOT RESTOCKER] 180 turn then drive to {self.active_target_pallet} "
                    f"({self.drive_target[0]:.2f}, {self.drive_target[1]:.2f}), "
                    f"distance={distance:.2f} m"
                )
                self.change_state("TURN_180")

        elif self.state == "TURN_180":
            self.set_arm(self.carry_pose)
            self.set_gripper(self.gripper_close, closing=True)
            if self.turn_to_heading(self.departure_heading):
                print(
                    f"[YOUBOT RESTOCKER] Turn complete, heading "
                    f"{math.degrees(self.get_robot_yaw()):.1f} deg"
                )
                self.change_state("DRIVE_TO_PALLET")
            elif self.timer >= MAX_TURN_TIME:
                self.stop_wheels()
                print("[YOUBOT RESTOCKER WARNING] Turn timeout, driving anyway")
                self.report_failure("turn timeout at pallet approach")
                self.change_state("DRIVE_TO_PALLET")

        elif self.state == "DRIVE_TO_PALLET":
            self.set_arm(self.carry_pose)
            self.set_gripper(self.gripper_close, closing=True)
            if self.drive_toward_xy(self.drive_target[0], self.drive_target[1]):
                print("[YOUBOT RESTOCKER] At pallet, placing box")
                self.change_state("OVER_PALLET")
            elif self.timer >= MAX_DRIVE_TIME:
                self.stop_wheels()
                print("[YOUBOT RESTOCKER WARNING] Drive timeout, attempting place")
                self.report_failure("drive timeout to stock pallet")
                self.change_state("OVER_PALLET")

        elif self.state == "OVER_PALLET":
            dur = self.act_steps(100)
            progress = self.timer / dur
            self.set_arm(self.lerp_joints(self.carry_pose, self.over_pallet_pose, progress))
            self.set_gripper(self.gripper_close, closing=True)
            if self.timer >= dur:
                self.change_state("PLACE_ON_PALLET")

        elif self.state == "PLACE_ON_PALLET":
            dur = self.act_steps(80)
            progress = self.timer / dur
            self.set_arm(
                self.lerp_joints(self.over_pallet_pose, self.place_on_pallet_pose, progress)
            )
            self.set_gripper(self.gripper_close, closing=True)
            if self.timer >= dur:
                self.change_state("RELEASE_ON_PALLET")

        elif self.state == "RELEASE_ON_PALLET":
            if self.timer == 0:
                pallet = self.restock_verify_pallet or self.active_target_pallet
                self.restock_count_before_release = task_mgr.count_boxes_on_pallet(
                    self.robot.getFromDef,
                    pallet,
                )
            self.set_arm(self.place_on_pallet_pose)
            dur = self.act_steps(60)
            open_progress = min(1.0, self.timer / dur)
            grip = self.gripper_close + (self.gripper_open - self.gripper_close) * open_progress
            self.set_gripper(grip)
            if self.timer >= dur:
                delivered_box = self.restock_pending_box_def or self.active_box_def
                print(
                    f"[YOUBOT RESTOCKER] Box released toward {self.active_target_pallet} "
                    f"({delivered_box}), verifying pallet count"
                )
                self.change_state("VERIFY_RESTOCK")

        elif self.state == "VERIFY_RESTOCK":
            self.set_arm(self.place_on_pallet_pose)
            self.set_gripper(self.gripper_open)
            box_def = self.active_restock_box_def()
            if not self.box_def_alive(box_def):
                self.abort_restock_failure(
                    "box removed before pallet drop",
                    box_def=box_def or "",
                    phase=self.state,
                    target_pallet=self.restock_verify_pallet or self.active_target_pallet,
                )
            else:
                settle = self.act_steps(detection.RESTOCK_VERIFY_SETTLE_STEPS)
                if self.timer >= settle:
                    self.verify_restock_placement()
                    self.end_restock_cycle()
                    self.active_target_pallet = product_routing.DEFAULT_PALLET_DEF
                    self.active_box_def = None
                    self.active_box_pos = None
                    self.restock_verify_pallet = None
                    self.restock_pending_box_def = None
                    self.restock_count_before = 0
                    self.restock_count_before_release = 0
                    self.waiting_for_box = True
                    self.reset_wait_for_box_state()
                    self.change_state("HOME")

        elif self.state == "HOME":
            dur = self.act_steps(100)
            progress = self.timer / dur
            self.set_arm(self.lerp_joints(self.place_on_pallet_pose, self.conveyor_idle_arm_pose(), progress))
            self.set_gripper(self.gripper_open)
            if self.timer >= dur:
                print(
                    f"[YOUBOT RESTOCKER] Pick cycle #{self.pick_count} complete, "
                    f"returning to conveyor pre-pick pose"
                )
                self.drive_target = self.get_conveyor_home_xy()
                robot_x, robot_y = self.get_robot_xy()
                distance = math.hypot(
                    self.drive_target[0] - robot_x,
                    self.drive_target[1] - robot_y,
                )
                print(
                    f"[YOUBOT RESTOCKER] Return: turn + drive to conveyor "
                    f"({self.drive_target[0]:.3f}, {self.drive_target[1]:.3f}), "
                    f"distance={distance:.2f} m"
                )
                self.change_state("DRIVE_TO_CONVEYOR")

        elif self.state == "DRIVE_TO_CONVEYOR":
            self.set_arm(self.conveyor_idle_arm_pose())
            self.set_gripper(self.gripper_open)
            if self.drive_toward_xy(
                self.drive_target[0],
                self.drive_target[1],
                tolerance=HOME_DRIVE_TOLERANCE,
            ):
                print("[YOUBOT RESTOCKER] At conveyor area, aligning pick heading")
                self.change_state("TURN_TO_PICKUP")
            elif self.timer >= MAX_RETURN_DRIVE_TIME:
                self.stop_wheels()
                print("[YOUBOT RESTOCKER WARNING] Return drive timeout, aligning heading")
                self.report_failure("return drive timeout to conveyor")
                self.change_state("TURN_TO_PICKUP")

        elif self.state == "TURN_TO_PICKUP":
            self.set_arm(self.conveyor_idle_arm_pose())
            self.set_gripper(self.gripper_open)
            if self.turn_to_heading(self.get_home_heading()):
                if not self.return_aligned_done:
                    self.snap_to_home_pose()
                    print(
                        f"[YOUBOT RESTOCKER] Return heading aligned "
                        f"({math.degrees(self.get_robot_yaw()):.2f} deg)"
                    )
                    self.return_aligned_done = True
                self.waiting_for_box = True
                self.try_start_pick_cycle()
                if self.state == "TURN_TO_PICKUP":
                    if not self.maybe_start_conveyor_search("after return"):
                        self.change_state("WAIT_BOX")
            elif self.timer >= MAX_TURN_TIME:
                self.stop_wheels()
                self.snap_to_home_pose()
                print("[YOUBOT RESTOCKER WARNING] Pick heading turn timeout")
                self.report_failure("pick heading turn timeout")
                self.waiting_for_box = True
                if self.should_start_search():
                    self.change_state("SEARCH_AT_CONVEYOR")
                else:
                    self.change_state("WAIT_BOX")

        self.timer += 1

    def run(self):
        while self.robot.step(self.time_step) != -1:
            self.run_state()


if __name__ == "__main__":
    YoubotRestockerDemo().run()
