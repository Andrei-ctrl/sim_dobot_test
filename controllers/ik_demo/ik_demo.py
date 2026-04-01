"""
ik_demo.py — Demonstration controller using IKRobot
====================================================

This is a complete, runnable Webots controller that shows students how to
use the IKRobot library to move a robot by specifying Cartesian points.

How to use this as a template
------------------------------
1. Copy this file to your own controller folder (e.g. my_controller/).
2. Copy (or symlink)  ik_robot.py  from  libraries/ik_robot/  into the
   same folder  —  OR add the path as shown below.
3. Set your Webots robot node to use this controller.
4. Adjust the URDF path and waypoints to match your robot.

Folder structure expected
--------------------------
    my_controller/
        my_controller.py   ← your code (copy this file)
        ik_robot.py        ← copy from libraries/ik_robot/
        robot.urdf         ← your URDF (or point URDF_PATH elsewhere)
"""

import sys
import os

# ── Path setup ────────────────────────────────────────────────────────────
# Option A: ik_robot.py is in the same folder as this controller (recommended
#           for standalone projects — just copy the file).
# Option B: import from the shared libraries folder.  Uncomment the line
#           below and remove Option A if you prefer a single shared copy.
#
# Option A (default — ik_robot.py lives next to this script):
# sys.path.insert(0, os.path.dirname(__file__))
#
# Option B (shared library at project root):
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../libraries/ik_robot"))

from ik_robot import IKRobot   # noqa: E402  (import after path setup)

# ── Configuration ─────────────────────────────────────────────────────────
# Path to your robot's URDF.  Can be absolute or relative to this file.
URDF_PATH = os.path.join(
    os.path.dirname(__file__),
    "./me6.urdf",   # ← change this
)



# Default movement speed (0.0 – 1.0)
SPEED = 0.0005

# ── Waypoints ─────────────────────────────────────────────────────────────
# List of (x, y, z) positions in metres that the end-effector will visit
# in sequence.  Add, remove or change these to suit your task.
WAYPOINTS = [
    (0.3, 0.0, 0.2),
    (0.3, 0.2, 0.2),
    (0.3, 0.2, 0.4),
]


def main():
    # ── Create the robot ───────────────────────────────────────────────────
    try:
        robot = IKRobot(
            urdf_path=URDF_PATH,
            speed=SPEED,
            # Leave name mapping unset when URDF joint names already match Webots.
            # Use joint_name_map only if your scene uses different motor names.
        )
    except RuntimeError as exc:
        print(f"Failed to initialize IKRobot: {exc}")
        print("Run this script as the robot controller inside Webots.")
        return

    # ── Go home first ──────────────────────────────────────────────────────
    print("\n--- Moving to home position ---")
    robot.home(speed=0.003)

    # ── Print initial end-effector position ───────────────────────────────
    x, y, z = robot.get_ee_position()
    print(f"Home EE position: x={x:.4f}, y={y:.4f}, z={z:.4f} m\n")

    # ── Follow the waypoints ───────────────────────────────────────────────
    for i, (wx, wy, wz) in enumerate(WAYPOINTS):
        print(f"--- Waypoint {i+1}/{len(WAYPOINTS)}:  ({wx}, {wy}, {wz}) ---")
        reached = robot.move_to(wx, wy, wz)

        if reached:
            x, y, z = robot.get_ee_position()
            print(f"    Reached.  EE = ({x:.4f}, {y:.4f}, {z:.4f}) m")
        else:
            print("    WARNING: could not reach this waypoint (skipping)")

    # ── Done — return home ─────────────────────────────────────────────────
    print("\n--- Returning to home ---")
    robot.home(speed=0.003)
    print("Demo complete.")


if __name__ == "__main__":
    main()
