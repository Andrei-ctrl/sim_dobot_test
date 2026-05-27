"""Clamp Webots joint targets to motor limits (avoids limit warnings)."""

import math

JOINT_ZERO_EPS = 1e-4


def clamp_joint_position(motor, value):
    if motor is None:
        return value
    lo = motor.getMinPosition()
    hi = motor.getMaxPosition()
    if not (math.isfinite(lo) and math.isfinite(hi)):
        return value
    if hi <= lo + 1e-9:
        return lo
    clamped = max(lo, min(hi, value))
    if lo <= 0.0 <= hi and abs(clamped) < JOINT_ZERO_EPS:
        return 0.0
    if abs(clamped - lo) < JOINT_ZERO_EPS:
        return lo
    if abs(clamped - hi) < JOINT_ZERO_EPS:
        return hi
    return clamped


def set_joint_position(motor, value):
    if motor is not None:
        motor.setPosition(clamp_joint_position(motor, value))


def snap_motors(motor_values):
    """motor_values: iterable of (motor, target) pairs."""
    for motor, value in motor_values:
        set_joint_position(motor, value)
