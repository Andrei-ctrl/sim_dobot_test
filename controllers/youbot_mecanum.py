"""KUKA youBot mecanum inverse kinematics (Webots wheel1..4 layout).

Wheel layout (view from above, robot +X forward):
  w2 LF (Exterior)  ----  w1 RF (Interior)
  w4 LB (Interior)  ----  w3 RB (Exterior)

Based on the official Webots youBot base kinematics.
"""

import math

WHEEL_RADIUS = 0.05
# Distance from robot centre to each wheel contact (0.228 + 0.158 m).
WHEEL_AXLE = 0.386
WHEEL_MAX_VEL = 14.81


def wheel_speeds(vx, vy, omega, radius=WHEEL_RADIUS, axle=WHEEL_AXLE):
    """Return rad/s for wheel1..4 given robot-frame m/s and rad/s."""
    r = radius
    d = axle
    return [
        (vx + vy + omega * d) / r,  # w1 RF
        (vx - vy - omega * d) / r,  # w2 LF
        (vx - vy + omega * d) / r,  # w3 RB
        (vx + vy - omega * d) / r,  # w4 LB
    ]


def clamp_wheel_speeds(speeds, max_vel=WHEEL_MAX_VEL):
    peak = max(abs(s) for s in speeds) if speeds else 0.0
    if peak <= max_vel or peak < 1e-9:
        return speeds
    scale = max_vel / peak
    return [s * scale for s in speeds]


def turn_forward_cmd(
    distance,
    heading_error,
    max_speed,
    heading_align=0.28,
    turn_omega=0.85,
):
    """Align heading first, then drive forward only (no diagonal strafe)."""
    if abs(heading_error) > heading_align:
        omega = max(-turn_omega, min(turn_omega, 1.4 * heading_error))
        return 0.0, 0.0, omega
    speed = min(max_speed, max(0.08, 0.55 * distance))
    omega = max(-0.6, min(0.6, 0.9 * heading_error))
    return speed, 0.0, omega


CARDINAL_ANGLE_TOL = 0.14


def world_delta_to_robot(dx, dy, yaw):
    """World-frame delta to robot-frame forward/left (m)."""
    cos_a = math.cos(yaw)
    sin_a = math.sin(yaw)
    return dx * cos_a + dy * sin_a, -dx * sin_a + dy * cos_a


def relative_bearing(from_yaw, to_bearing):
    delta = to_bearing - from_yaw
    while delta > math.pi:
        delta -= 2.0 * math.pi
    while delta < -math.pi:
        delta += 2.0 * math.pi
    return delta


def is_cardinal_bearing(relative_bearing):
    """True when target lies on 0/90/180/270 deg from robot heading."""
    candidates = (0.0, math.pi / 2.0, -math.pi / 2.0, math.pi, -math.pi)
    return any(abs(relative_bearing - angle) <= CARDINAL_ANGLE_TOL for angle in candidates)


def cardinal_drive_cmd(local_dx, local_dy, max_speed, axis_tol=0.04):
    """
    Prefer pure forward/backward or sideways motion in robot frame.
    Moves one axis at a time when both deltas are significant.
    Returns (vx, vy, omega).
    """
    if abs(local_dx) <= axis_tol and abs(local_dy) <= axis_tol:
        return 0.0, 0.0, 0.0

    if abs(local_dx) > axis_tol and abs(local_dy) <= axis_tol:
        speed = min(max_speed, max(0.08, 0.55 * abs(local_dx)))
        return (speed if local_dx > 0 else -speed), 0.0, 0.0

    if abs(local_dy) > axis_tol and abs(local_dx) <= axis_tol:
        speed = min(max_speed, max(0.08, 0.55 * abs(local_dy)))
        return 0.0, (speed if local_dy > 0 else -speed), 0.0

    if abs(local_dx) >= abs(local_dy):
        speed = min(max_speed, max(0.08, 0.55 * abs(local_dx)))
        return (speed if local_dx > 0 else -speed), 0.0, 0.0

    speed = min(max_speed, max(0.08, 0.55 * abs(local_dy)))
    return 0.0, (speed if local_dy > 0 else -speed), 0.0
