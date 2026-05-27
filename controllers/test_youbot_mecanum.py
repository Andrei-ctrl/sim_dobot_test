"""Unit tests for youBot mecanum kinematics."""

import math
import sys
import unittest

sys.path.insert(0, "controllers")
import youbot_mecanum as mecanum


class TestYoubotMecanum(unittest.TestCase):
    def test_forward_all_wheels_same_sign(self):
        speeds = mecanum.wheel_speeds(0.4, 0.0, 0.0)
        self.assertTrue(all(s > 0 for s in speeds))

    def test_turn_opposite_pairs(self):
        speeds = mecanum.wheel_speeds(0.0, 0.0, 0.5)
        self.assertGreater(speeds[0], 0)
        self.assertLess(speeds[1], 0)
        self.assertGreater(speeds[2], 0)
        self.assertLess(speeds[3], 0)

    def test_strafe_left(self):
        speeds = mecanum.wheel_speeds(0.0, -0.3, 0.0)
        self.assertLess(speeds[0], 0)
        self.assertGreater(speeds[1], 0)

    def test_clamp_scales_down(self):
        raw = mecanum.wheel_speeds(2.0, 2.0, 0.0)
        clamped = mecanum.clamp_wheel_speeds(raw)
        self.assertLessEqual(max(abs(s) for s in clamped), mecanum.WHEEL_MAX_VEL + 1e-6)

    def test_turn_forward_cmd_aligns_before_drive(self):
        vx, vy, omega = mecanum.turn_forward_cmd(2.0, 0.8, 0.5, heading_align=0.28)
        self.assertAlmostEqual(vx, 0.0, places=3)
        self.assertAlmostEqual(vy, 0.0, places=3)
        self.assertNotAlmostEqual(omega, 0.0, places=3)

    def test_turn_forward_cmd_drives_forward_when_aligned(self):
        vx, vy, omega = mecanum.turn_forward_cmd(2.0, 0.0, 0.5, heading_align=0.28)
        self.assertAlmostEqual(vy, 0.0, places=3)
        self.assertGreater(vx, 0.0)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
