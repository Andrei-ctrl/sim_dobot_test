"""Clamp Webots joint targets to motor limits (avoids limit warnings)."""

import math


def clamp_joint_position(motor, value):
    if motor is None:
        return value
    lo = motor.getMinPosition()
    hi = motor.getMaxPosition()
    if not (math.isfinite(lo) and math.isfinite(hi)):
        return value
    if hi <= lo + 1e-9:
        return lo
    return max(lo, min(hi, value))


def set_joint_position(motor, value):
    if motor is not None:
        motor.setPosition(clamp_joint_position(motor, value))
