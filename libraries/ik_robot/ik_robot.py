"""
ik_robot.py  —  Standalone IK robot library for Webots
=======================================================

A single-file library that lets you control any Webots robot in
**Cartesian / task space** using inverse kinematics.

Quick start
-----------
Copy this file into your controller folder, then:

    from ik_robot import IKRobot

    robot = IKRobot("path/to/robot.urdf")

    # Move end-effector to a sequence of points (blocking)
    robot.move_to(x=0.20, y=0.00, z=0.35)
    robot.move_to(x=0.15, y=0.10, z=0.30)
    robot.move_to(x=0.00, y=0.20, z=0.40, speed=0.3)

    # Go home
    robot.home()

That's it — no manual Webots main loop needed.

Requirements
------------
    pip install ikpy

Coordinate frame
----------------
- Origin  : robot base (the first active link in the URDF)
- Distances in **metres**, angles in **radians**

How joint names are resolved
-----------------------------
ikpy uses the URDF **joint** names as link names inside the chain.
By default the library maps those directly to Webots **motor** device names
(same convention as the Dobot PROTO: joint1 → joint1, etc.).

If your URDF joint names differ from the Webots motor names, pass a mapping::

    robot = IKRobot("robot.urdf",
                    joint_name_map={"joint1": "motorA", "joint2": "motorB"})

Sensor names default to  ``<motor_name>_sensor``.  Override with
``sensor_name_map`` if needed.

Notes for advanced users
-------------------------
- ikpy **skips fixed joints** when building the kinematic chain, so you do
  not need to add dummy links to the URDF — just include the revolute joints.
- The "end-effector" position returned by FK is the origin of the last
  revolute link's child frame.  Add a small offset to your target if your
  tool tip is further along that frame.
"""

from __future__ import annotations

import os
import numpy as np
from typing import Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Optional dependencies — clear error messages when missing
# ---------------------------------------------------------------------------
try:
    from ikpy.chain import Chain
    _IKPY_OK = True
except ImportError:
    _IKPY_OK = False

try:
    from controller import Robot, Motor, PositionSensor
    _WEBOTS_OK = True
except ImportError:
    _WEBOTS_OK = False


# ===========================================================================
# Chain builder
# ===========================================================================

def _build_ik_chain(urdf_path: str) -> Tuple[Chain, List[bool], List[str]]:
    """
    Load a URDF and return (chain, active_mask, active_joint_names).

    ikpy automatically skips fixed joints and prepends an OriginLink, so
    we first load without a mask to discover the true chain length, then
    set active_mask = [False, True, True, …, True]  (inactive origin only).

    active_joint_names contains the ikpy link names for the revolute joints
    in chain order — these match the URDF joint names and are used as
    Webots motor device names.
    """
    # Step 1 — load without mask to get the real chain structure
    chain_raw = Chain.from_urdf_file(urdf_path)
    n_links = len(chain_raw.links)           # includes OriginLink at [0]

    if n_links < 2:
        raise ValueError(
            f"URDF '{urdf_path}' produced a chain with only {n_links} link(s). "
            "Check that the file contains at least one revolute joint reachable "
            "from 'base_link' (ikpy's default start)."
        )

    # Step 2 — mask: OriginLink inactive, everything else active
    active_mask = [False] + [True] * (n_links - 1)

    # Step 3 — active joint names (ikpy stores the URDF joint name on each link)
    active_joint_names = [link.name for link in chain_raw.links[1:]]

    # Step 4 — reload with explicit mask (same result, but validates length)
    chain = Chain.from_urdf_file(urdf_path, active_links_mask=active_mask)

    return chain, active_mask, active_joint_names


# ===========================================================================
# Main class
# ===========================================================================

class IKRobot:
    """
    Controls a Webots robot in Cartesian space using inverse kinematics.

    Parameters
    ----------
    urdf_path : str
        Path to the URDF file (absolute, or relative to this library file).
    timestep : int | None
        Webots simulation timestep in milliseconds.
        ``None`` → use ``robot.getBasicTimeStep()`` automatically.
    speed : float
        Default speed for movements (0.0 – 1.0).  1.0 = max motor velocity.
    joint_name_map : dict | None
        Override URDF joint names → Webots motor names when they differ.
        Example:  ``{"joint1": "motor_base", "joint2": "motor_shoulder"}``
    sensor_name_map : dict | None
        Override Webots sensor names.
        Default: ``<motor_name>_sensor``
    tolerance : float
        Joint-angle tolerance (radians) used to decide "position reached".
    timeout : float
        Max seconds to wait for a move to complete before giving up.
    """

    def __init__(
        self,
        urdf_path: str,
        timestep: Optional[int] = None,
        speed: float = 0.5,
        joint_name_map: Optional[Dict[str, str]] = None,
        sensor_name_map: Optional[Dict[str, str]] = None,
        tolerance: float = 0.01,
        timeout: float = 15.0,
    ):
        if not _IKPY_OK:
            raise RuntimeError(
                "ikpy is required.  Install it with:  pip install ikpy"
            )
        if not _WEBOTS_OK:
            raise RuntimeError(
                "Webots Python controller module not found.  "
                "Run this code inside a Webots controller."
            )

        # Validate user-facing control parameters early.
        self.speed = self._validate_speed(speed)
        self.tolerance = self._validate_positive_finite(tolerance, "tolerance")
        self.timeout = self._validate_positive_finite(timeout, "timeout")

        # Resolve relative paths against this module, then current working dir.
        if not os.path.isabs(urdf_path):
            base_dir = os.path.dirname(os.path.abspath(__file__))
            candidate = os.path.join(base_dir, urdf_path)
            if os.path.isfile(candidate):
                urdf_path = candidate
            else:
                urdf_path = os.path.abspath(urdf_path)
        if not os.path.isfile(urdf_path):
            raise FileNotFoundError(f"URDF not found: '{urdf_path}'")
        self._urdf_path = urdf_path

        # ── Build ikpy chain ─────────────────────────────────────────────
        self._chain, self._active_mask, self._joint_names = (
            _build_ik_chain(urdf_path)
        )
        self._n_joints = len(self._joint_names)   # number of revolute joints

        if self._n_joints == 0:
            raise ValueError("No active joints found in URDF chain.")

        # ── Webots initialisation ────────────────────────────────────────
        self._robot    = Robot()
        self._timestep = timestep or int(self._robot.getBasicTimeStep())

        jmap = joint_name_map  or {}
        smap = sensor_name_map or {}

        self._motors : List[Optional[Motor]]          = []
        self._sensors: List[Optional[PositionSensor]] = []
        self._last_commanded: List[float] = [0.0] * self._n_joints

        for urdf_name in self._joint_names:
            motor_name  = jmap.get(urdf_name,   urdf_name)
            sensor_name = smap.get(motor_name, f"{motor_name}_sensor")

            motor = self._get_device_safe(motor_name)
            sensor = self._get_device_safe(sensor_name)

            if motor is None:
                print(f"[IKRobot] WARNING: motor '{motor_name}' not found "
                      "in the Webots scene.")
            else:
                motor.setPosition(0.0)
                motor.setVelocity(_safe_max_velocity(motor))

            if sensor is None:
                print(f"[IKRobot] WARNING: sensor '{sensor_name}' not found.")
            else:
                sensor.enable(self._timestep)

            self._motors.append(motor)
            self._sensors.append(sensor)

        if not any(m is not None for m in self._motors):
            raise RuntimeError(
                "No controllable motors were found for active joints. "
                "Check URDF joint names and joint_name_map."
            )

        # One step so sensors return valid readings
        self._robot.step(self._timestep)

        print(
            f"[IKRobot] Ready — {self._n_joints} joints: {self._joint_names}"
        )
        x, y, z = self.get_ee_position()
        print(f"[IKRobot] Home EE position: ({x:.4f}, {y:.4f}, {z:.4f}) m")

    # -----------------------------------------------------------------------
    # ── Public movement API ─────────────────────────────────────────────────
    # -----------------------------------------------------------------------

    def move_to(
        self,
        x: float,
        y: float,
        z: float,
        speed: Optional[float] = None,
    ) -> bool:
        """
        Move the end-effector to *(x, y, z)* in metres.

        **Blocks** until the robot reaches the target (within
        ``self.tolerance``) or ``self.timeout`` seconds have elapsed.
        Orientation is unconstrained — use :meth:`move_to_pose` to control it.

        Parameters
        ----------
        x, y, z : float  Target position in metres (robot base frame).
        speed   : float  Speed override (0.0 – 1.0).  None = default speed.

        Returns
        -------
        bool — ``True`` if reached, ``False`` on timeout or no IK solution.

        Example
        -------
        ::

            robot.move_to(0.20, 0.00, 0.35)
            robot.move_to(0.15, 0.10, 0.30, speed=0.3)
        """
        joints = self.solve_ik(x, y, z, position_only=True)
        if joints is None:
            print(f"[IKRobot] No IK solution for ({x:.4f}, {y:.4f}, {z:.4f})")
            return False
        return self._execute(joints, self._resolve_speed(speed))

    def move_to_pose(
        self,
        x: float,
        y: float,
        z: float,
        rx: float = 0.0,
        ry: float = 0.0,
        rz: float = 0.0,
        speed: Optional[float] = None,
    ) -> bool:
        """
        Move end-effector to a full pose (position + orientation).

        Parameters
        ----------
        x, y, z    : target position in metres.
        rx, ry, rz : target orientation as roll-pitch-yaw in radians.
        speed      : optional speed override.

        Returns
        -------
        bool — ``True`` if reached, ``False`` on timeout or no solution.
        """
        joints = self.solve_ik(x, y, z, rx, ry, rz, position_only=False)
        if joints is None:
            print(f"[IKRobot] No IK solution for pose "
                  f"({x:.3f},{y:.3f},{z:.3f}|{rx:.2f},{ry:.2f},{rz:.2f})")
            return False
        return self._execute(joints, self._resolve_speed(speed))

    def move_joints(
        self,
        joint_angles: Sequence[float],
        speed: Optional[float] = None,
    ) -> bool:
        """
        Move directly to a set of joint angles (joint space).

        Parameters
        ----------
        joint_angles : one angle per active joint, in radians.
        speed        : optional speed override.

        Returns
        -------
        bool — ``True`` if reached.
        """
        if len(joint_angles) != self._n_joints:
            raise ValueError(
                f"Expected {self._n_joints} joint angles, "
                f"got {len(joint_angles)}"
            )
        return self._execute(list(joint_angles), self._resolve_speed(speed))

    def home(self, speed: Optional[float] = None) -> bool:
        """
        Move all joints to zero (home / zero position).

        Returns
        -------
        bool — ``True`` if home was reached.
        """
        return self._execute([0.0] * self._n_joints, self._resolve_speed(speed))

    def step(self) -> bool:
        """
        Advance the Webots simulation by one timestep.

        Call this in your own loop for non-blocking control.

        Returns
        -------
        bool — ``False`` when the simulation has ended.
        """
        return self._robot.step(self._timestep) != -1

    # -----------------------------------------------------------------------
    # ── IK / FK queries ─────────────────────────────────────────────────────
    # -----------------------------------------------------------------------

    def solve_ik(
        self,
        x: float,
        y: float,
        z: float,
        rx: float = 0.0,
        ry: float = 0.0,
        rz: float = 0.0,
        position_only: bool = True,
        initial_joints: Optional[Sequence[float]] = None,
    ) -> Optional[List[float]]:
        """
        Compute joint angles for a target end-effector pose.

        Does **not** move the robot — only returns the solution.

        Parameters
        ----------
        x, y, z        : target position in metres.
        rx, ry, rz     : target orientation in radians (roll-pitch-yaw).
                         Ignored when *position_only* is ``True``.
        position_only  : ``True``  → orientation is free (easier to solve).
                         ``False`` → full pose IK.
        initial_joints : warm-start for the solver (list of n_joints floats).
                         Defaults to current joint readings.

        Returns
        -------
        List[float] of length n_joints, or ``None`` if no solution found.

        Example
        -------
        ::

            joints = robot.solve_ik(0.20, 0.00, 0.35)
            print(joints)          # inspect before deciding to move
            robot.move_joints(joints)
        """
        if not np.all(np.isfinite([x, y, z, rx, ry, rz])):
            print("[IKRobot] Invalid IK target: pose values must be finite.")
            return None

        target = _build_target_matrix(x, y, z, rx, ry, rz)
        seed_input = initial_joints if initial_joints is not None else self.get_joint_angles()
        try:
            seed = self._to_chain_vector(seed_input)
        except ValueError:
            seed = self._to_chain_vector(self._last_commanded)

        try:
            if position_only:
                result = self._chain.inverse_kinematics(
                    target_position=target[:3, 3],
                    orientation_mode=None,
                    initial_position=seed,
                )
            else:
                result = self._chain.inverse_kinematics(
                    target_position=target[:3, 3],
                    target_orientation=target[:3, :3],
                    orientation_mode="all",
                    initial_position=seed,
                )
        except Exception as exc:
            print(f"[IKRobot] IK solver failed: {exc}")
            return None

        if len(result) != len(self._chain.links) or not np.all(np.isfinite(result)):
            print("[IKRobot] IK solver returned an invalid result vector.")
            return None

        # Extract active joint angles (skip OriginLink at index 0)
        joints = list(result[1:])

        # Warn if the solver did not converge well
        fk  = self._chain.forward_kinematics(result)
        err = float(np.linalg.norm(fk[:3, 3] - target[:3, 3]))
        if err > 0.02:
            print(
                f"[IKRobot] IK warning: position error = {err*1000:.1f} mm. "
                "Target may be out of reach or the solver needs a better "
                "initial configuration."
            )

        return joints

    def forward_kinematics(
        self,
        joint_angles: Optional[Sequence[float]] = None,
    ) -> np.ndarray:
        """
        Compute the end-effector 4×4 transformation matrix.

        Parameters
        ----------
        joint_angles : angles in radians (length = n_joints),
                       or ``None`` to use current sensor readings.

        Returns
        -------
        numpy.ndarray shape (4, 4).  ``result[:3, 3]`` = (x, y, z) position.

        Example
        -------
        ::

            T = robot.forward_kinematics()
            print("EE position:", T[:3, 3])
        """
        angles = (
            joint_angles if joint_angles is not None
            else self.get_joint_angles()
        )
        return self._chain.forward_kinematics(self._to_chain_vector(angles))

    def get_ee_position(self) -> Tuple[float, float, float]:
        """
        Return the current end-effector position ``(x, y, z)`` in metres.

        Computed via forward kinematics from the current sensor readings.

        Example
        -------
        ::

            x, y, z = robot.get_ee_position()
            print(f"EE at ({x:.3f}, {y:.3f}, {z:.3f}) m")
        """
        T = self.forward_kinematics()
        return float(T[0, 3]), float(T[1, 3]), float(T[2, 3])

    def get_joint_angles(self) -> List[float]:
        """
        Return current joint angles from position sensors (radians).

        Example
        -------
        ::

            angles = robot.get_joint_angles()
        """
        values: List[float] = []
        for idx, sensor in enumerate(self._sensors):
            if sensor is None:
                # Keep missing-sensor joints coherent with the last command.
                values.append(self._last_commanded[idx])
            else:
                values.append(sensor.getValue())
        return values

    @property
    def joint_names(self) -> List[str]:
        """Names of the active joints (as found in the URDF)."""
        return list(self._joint_names)

    @property
    def n_joints(self) -> int:
        """Number of controllable (revolute/prismatic) joints."""
        return self._n_joints

    # -----------------------------------------------------------------------
    # ── Internal helpers ─────────────────────────────────────────────────────
    # -----------------------------------------------------------------------

    def _execute(self, joint_angles: List[float], speed: float) -> bool:
        """Send joint targets and step until reached or timeout."""
        if len(joint_angles) != self._n_joints:
            raise ValueError(
                f"Expected {self._n_joints} joint targets, got {len(joint_angles)}"
            )
        if not np.all(np.isfinite(joint_angles)):
            raise ValueError("joint_angles must contain finite values")

        velocity = self._to_velocity(speed)
        self._set_motors(joint_angles, velocity)
        self._last_commanded = list(joint_angles)

        t_start = self._robot.getTime()
        while self._robot.step(self._timestep) != -1:
            if _all_close(self.get_joint_angles(), joint_angles, self.tolerance):
                return True
            if self._robot.getTime() - t_start > self.timeout:
                print(
                    f"[IKRobot] Timeout after {self.timeout}s — "
                    "target may be unreachable or tolerance too tight."
                )
                return False
        return False   # simulation ended

    def _set_motors(self, angles: List[float], velocity: float):
        for motor, angle in zip(self._motors, angles):
            if motor is not None:
                motor.setVelocity(velocity)
                motor.setPosition(angle)

    def _to_chain_vector(self, joint_angles: Sequence[float]) -> np.ndarray:
        """
        Build the full ikpy chain vector from active joint angles.

        Layout: [0.0 (OriginLink), j1, j2, …, jN]
        Length = len(chain.links) = 1 + n_joints
        """
        angles = list(joint_angles)
        if len(angles) != self._n_joints:
            raise ValueError(
                f"Expected {self._n_joints} joint angles, got {len(angles)}"
            )
        if not np.all(np.isfinite(angles)):
            raise ValueError("joint_angles must contain finite values")
        return np.array([0.0] + angles)

    def _to_velocity(self, speed: float) -> float:
        speed = self._validate_speed(speed)
        max_v = min(
            (_safe_max_velocity(m) for m in self._motors if m is not None),
            default=1.0,
        )
        return speed * max_v

    def _resolve_speed(self, speed: Optional[float]) -> float:
        return self.speed if speed is None else self._validate_speed(speed)

    def _get_device_safe(self, name: str):
        try:
            return self._robot.getDevice(name)
        except Exception:
            return None

    @staticmethod
    def _validate_speed(speed: float) -> float:
        if not np.isfinite(speed):
            raise ValueError("speed must be finite")
        return max(0.0, min(1.0, float(speed)))

    @staticmethod
    def _validate_positive_finite(value: float, field: str) -> float:
        if not np.isfinite(value) or value <= 0:
            raise ValueError(f"{field} must be > 0 and finite")
        return float(value)


# ===========================================================================
# Pure-math helpers (no Webots dependency)
# ===========================================================================

def _build_target_matrix(
    x: float, y: float, z: float,
    rx: float = 0.0, ry: float = 0.0, rz: float = 0.0,
) -> np.ndarray:
    """4×4 homogeneous transform from position + RPY (intrinsic Rz·Ry·Rx)."""
    cr, sr = np.cos(rx), np.sin(rx)
    cp, sp = np.cos(ry), np.sin(ry)
    cy, sy = np.cos(rz), np.sin(rz)
    R = np.array([
        [cy*cp,  cy*sp*sr - sy*cr,  cy*sp*cr + sy*sr],
        [sy*cp,  sy*sp*sr + cy*cr,  sy*sp*cr - cy*sr],
        [  -sp,            cp*sr,             cp*cr  ],
    ])
    T = np.eye(4)
    T[:3, :3] = R
    T[:3,  3] = [x, y, z]
    return T


def _all_close(a: Sequence[float], b: Sequence[float], tol: float) -> bool:
    if len(a) != len(b):
        return False
    return all(abs(ai - bi) < tol for ai, bi in zip(a, b))


def _safe_max_velocity(motor: "Motor") -> float:
    try:
        v = motor.getMaxVelocity()
        return v if v > 0 else 1.0
    except Exception:
        return 1.0
