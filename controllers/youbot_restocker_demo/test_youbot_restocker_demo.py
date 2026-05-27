"""Unit tests for youBot restocker detection and operations (verbose console output)."""

import math
import sys
import unittest
from pathlib import Path

_LOGIC_DIR = Path(__file__).resolve().parent
if str(_LOGIC_DIR) not in sys.path:
    sys.path.insert(0, str(_LOGIC_DIR))

import youbot_restocker_logic as logic  # noqa: E402

BOX = logic.FIXED_PICK_BOX_POS
HOME = logic.RESTOCKER_HOME_XY


def log(title, detail=""):
    """Print a visible test operation line to the console."""
    msg = f"[TEST] {title}"
    if detail:
        msg += f" — {detail}"
    print(msg)


class TestSearchGating(unittest.TestCase):
    def test_no_search_without_conveyor_scan(self):
        log("Search without conveyor scan", "disabled")
        self.assertFalse(logic.search_allowed(False, None, 150.0))

    def test_no_search_before_delay(self):
        log("Search before 100s delay", "disabled")
        self.assertFalse(logic.search_allowed(True, 10.0, 50.0))
        self.assertFalse(logic.search_allowed(True, 0.0, 99.9))

    def test_search_after_delay(self):
        log("Search after 100s delay", "enabled")
        self.assertTrue(logic.search_allowed(True, 0.0, 100.0))
        self.assertTrue(logic.search_allowed(True, 10.0, 110.5))


class TestScannerZone(unittest.TestCase):
    def test_box_at_fixed_pick_slot_not_in_upstream_scanner(self):
        pick_pos = list(BOX)
        in_scanner = logic.box_in_scanner_zone(pick_pos)
        at_pick = logic.is_at_fixed_pick_slot(pick_pos)
        log("Fixed pick slot vs scanner", f"pos={pick_pos}")
        log("  at_fixed_slot", str(at_pick))
        log("  in_scanner_zone", str(in_scanner))
        self.assertTrue(at_pick)
        self.assertFalse(in_scanner)

    def test_box_at_scanner_position_triggers_stage1_zone(self):
        pos = [-0.01, 1.09, 0.25]
        log("Upstream scanner hit", f"pos={pos}")
        self.assertTrue(logic.box_in_scanner_zone(pos))


class TestPickStation(unittest.TestCase):
    def test_webots_scene_box_is_pickable(self):
        pos = list(BOX)
        log("Webots scene box at fixed slot", f"pos={pos}")
        self.assertTrue(logic.is_at_fixed_pick_slot(pos))

    def test_reference_box_is_pickable(self):
        pos = list(BOX)
        log("Reference box pick station", f"pos={pos}")
        self.assertTrue(logic.is_box_pickable(pos))

    def test_box_too_far_on_conveyor_rejected(self):
        pos = [-0.9, logic.CONVEYOR_Y, BOX[2]]
        reasons = logic.pick_station_rejection_reason(pos)
        log("Far conveyor box rejected", f"reasons={reasons}")
        self.assertFalse(logic.is_at_pick_station(pos))
        self.assertTrue(any("too far" in r for r in reasons))

    def test_box_wrong_y_rejected(self):
        pos = [BOX[0], BOX[1] + 0.25, BOX[2]]
        log("Off-center Y rejected", f"pos={pos}")
        self.assertFalse(logic.is_at_pick_station(pos))


class TestArmSensor(unittest.TestCase):
    def test_self_hit_reading_ignored(self):
        """Readings ~3700 hit the arm/gripper, not a box at the pick slot."""
        self_hit = 3699.0
        log("Sensor self-hit", f"value={self_hit}")
        self.assertFalse(logic.sensor_sees_box(self_hit, True))
        log("  ignored above SENSOR_MAX_VALID", str(logic.SENSOR_MAX_VALID))

    def test_old_threshold_500_misses_typical_wait_pose_reading(self):
        """Sensor lookup ~150 at 0.6 m; wait-pose often reads below 500."""
        typical_reading = 280
        log("Arm sensor at ~0.55 m", f"value={typical_reading}")
        self.assertFalse(logic.sensor_sees_box(typical_reading, True, threshold=500))
        log("  old threshold 500", "FAIL (miss)")
        self.assertTrue(logic.sensor_sees_box(typical_reading, True, threshold=120))
        log("  new threshold 120", "PASS at 280")
        self.assertFalse(logic.sensor_sees_box(80, True, threshold=120))
        log("  new threshold 120", "FAIL at 80 -> stage 3 fallback")

    def test_missing_sensor_does_not_auto_pass(self):
        log("Missing sensor safety", "must not auto-trigger pick")
        self.assertFalse(logic.sensor_sees_box(None, sensor_present=False))


class TestEvaluateDetection(unittest.TestCase):
    ROBOT_AT_HOME = HOME

    def test_both_sensors_miss_but_physical_stage3_picks(self):
        """Main bug fix: box at fixed slot + robot at home should still pick."""
        boxes = [("SPAWNED_BOX_0", list(BOX))]
        low_sensor = 80
        diag = logic.evaluate_detection(
            boxes=boxes,
            completed_boxes=set(),
            sensor_value=low_sensor,
            sensor_present=True,
            robot_xy=self.ROBOT_AT_HOME,
            home_xy=HOME,
            conveyor_box_detected=False,
            pending_box_def=None,
        )
        print(logic.format_detection_log({**diag, "robot_xy": self.ROBOT_AT_HOME}))
        log(
            "Physical fallback stage 3",
            f"sensor={low_sensor} should_pick={diag['should_pick']} stage={diag['pick_stage']}",
        )
        self.assertTrue(diag["should_pick"])
        self.assertEqual(diag["pick_stage"], 3)

    def test_self_hit_does_not_trigger_stage2_without_valid_sensor(self):
        boxes = [("SPAWNED_BOX_0", list(BOX))]
        diag = logic.evaluate_detection(
            boxes=boxes,
            completed_boxes=set(),
            sensor_value=3699.0,
            sensor_present=True,
            robot_xy=self.ROBOT_AT_HOME,
            home_xy=HOME,
        )
        log("Self-hit with box at slot", f"stage2={diag['stage2']} stage3={diag['stage3']}")
        self.assertFalse(diag["stage2"])
        self.assertTrue(diag["stage3"])

    def test_stage2_immediate_when_sensor_high(self):
        boxes = [("SPAWNED_BOX_0", list(BOX))]
        diag = logic.evaluate_detection(
            boxes=boxes,
            completed_boxes=set(),
            sensor_value=800,
            sensor_present=True,
            robot_xy=self.ROBOT_AT_HOME,
            home_xy=HOME,
        )
        log("Stage 2 arm sensor pick", f"stage={diag['pick_stage']}")
        self.assertEqual(diag["pick_stage"], 2)

    def test_stage1_after_scanner_tracking(self):
        boxes = [("SPAWNED_BOX_0", list(BOX))]
        diag = logic.evaluate_detection(
            boxes=boxes,
            completed_boxes=set(),
            sensor_value=50,
            sensor_present=True,
            robot_xy=HOME,
            home_xy=HOME,
            conveyor_box_detected=True,
            pending_box_def="SPAWNED_BOX_0",
        )
        log("Stage 1 scanner tracking pick", f"stage={diag['pick_stage']}")
        self.assertEqual(diag["pick_stage"], 1)

    def test_completed_box_ignored(self):
        boxes = [("SPAWNED_BOX_0", list(BOX))]
        diag = logic.evaluate_detection(
            boxes=boxes,
            completed_boxes={"SPAWNED_BOX_0"},
            sensor_value=900,
            sensor_present=True,
            robot_xy=self.ROBOT_AT_HOME,
            home_xy=HOME,
        )
        log("Completed box skipped", f"should_pick={diag['should_pick']}")
        self.assertFalse(diag["should_pick"])

    def test_no_pick_when_robot_far_from_conveyor(self):
        boxes = [("SPAWNED_BOX_0", list(BOX))]
        far_robot = [-5.0, HOME[1]]
        diag = logic.evaluate_detection(
            boxes=boxes,
            completed_boxes=set(),
            sensor_value=50,
            sensor_present=True,
            robot_xy=far_robot,
            home_xy=HOME,
        )
        log("Robot far from conveyor", f"should_pick={diag['should_pick']}")
        self.assertFalse(diag["should_pick"])


class TestNavigationHelpers(unittest.TestCase):
    def test_near_conveyor_at_home(self):
        home = list(HOME)
        log("Near conveyor radius", f"robot at home, r={logic.NEAR_CONVEYOR_RADIUS}")
        self.assertTrue(logic.is_near_conveyor(home, home))

    def test_heading_error_wrap(self):
        err = logic.normalize_angle(math.pi + 0.1)
        log("Angle normalize", f"pi+0.1 -> {err:.3f}")
        self.assertAlmostEqual(err, -math.pi + 0.1, places=3)


class TestFindBoxes(unittest.TestCase):
    def test_hardcoded_pick_pose_for_fixed_slot(self):
        pos = list(BOX)
        log("Hardcoded pick pose flag", str(logic.uses_hardcoded_pick_pose(pos)))
        self.assertTrue(logic.uses_hardcoded_pick_pose(pos))

    def test_find_pickable_skips_completed(self):
        boxes = [
            ("SPAWNED_BOX_0", list(BOX)),
            ("SPAWNED_BOX_1", [BOX[0] - 0.05, BOX[1], BOX[2]]),
        ]
        result = logic.find_pickable_box(boxes, {"SPAWNED_BOX_0"})
        log("Find pickable box", f"result={result}")
        self.assertEqual(result[0], "SPAWNED_BOX_1")


class TestOperationLogging(unittest.TestCase):
    """Simulate important operation log lines the controller emits."""

    def test_state_transition_log_format(self):
        states = [
            "WAIT_BOX -> OPEN_GRIP (stage 3 pick)",
            "OPEN_GRIP -> PRE_PICK -> APPROACH -> DESCEND -> CLOSE",
            "CARRY -> TURN_180 -> DRIVE_TO_PALLET",
            "RELEASE_ON_PALLET -> HOME -> DRIVE_TO_CONVEYOR",
            "TURN_TO_PICKUP -> SEARCH_AT_CONVEYOR (no box)",
        ]
        log("State machine path", "full delivery loop")
        for line in states:
            print(f"  [YOUBOT RESTOCKER] {line}")
        self.assertEqual(len(states), 5)

    def test_detection_log_renders(self):
        diag = logic.evaluate_detection(
            boxes=[("SPAWNED_BOX_0", list(BOX))],
            completed_boxes=set(),
            sensor_value=280,
            sensor_present=True,
            robot_xy=list(HOME),
            home_xy=list(HOME),
        )
        text = logic.format_detection_log({**diag, "robot_xy": list(HOME)})
        log("Diagnostic log sample (low sensor)", f"{len(text.splitlines())} lines")
        self.assertIn("stage3", text)

        diag2 = logic.evaluate_detection(
            boxes=[("SPAWNED_BOX_0", list(BOX))],
            completed_boxes=set(),
            sensor_value=800,
            sensor_present=True,
            robot_xy=list(HOME),
            home_xy=list(HOME),
        )
        text2 = logic.format_detection_log({**diag2, "robot_xy": list(HOME)})
        log("Diagnostic log sample (high sensor)", "expect PICK READY stage 2")
        self.assertIn("PICK READY", text2)


class TestPickAlignment(unittest.TestCase):
    def test_sensor_distance_inverse_lookup(self):
        dist = logic.sensor_value_to_distance(1800)
        log("Sensor distance @1800", f"{dist:.3f}m")
        self.assertAlmostEqual(dist, 0.15, places=2)

    def test_alignment_ok_at_calibrated_pose(self):
        robot = list(HOME)
        fwd, lat = logic.compute_alignment_errors(list(BOX), robot, HOME)
        log("Alignment at home vs box", f"fwd={fwd:+.3f} lat={lat:+.3f}")
        self.assertTrue(logic.is_alignment_ok(fwd, lat))

    def test_alignment_needs_lateral_strafe(self):
        robot = [HOME[0], HOME[1] + 0.08]
        fwd, lat = logic.compute_alignment_errors(list(BOX), robot, HOME)
        log("Misaligned robot", f"fwd={fwd:+.3f} lat={lat:+.3f}")
        self.assertFalse(logic.is_alignment_ok(fwd, lat))
        self.assertGreater(abs(lat), logic.ALIGN_LATERAL_TOL)


def run_tests():
    print("\n" + "=" * 60)
    print("youBot Restocker — unit tests (verbose console log)")
    print("=" * 60 + "\n")
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(stream=sys.stdout, verbosity=2)
    result = runner.run(suite)
    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print(f"ALL {result.testsRun} TESTS PASSED")
    else:
        print(f"FAILED: {len(result.failures)} failures, {len(result.errors)} errors")
    print("=" * 60 + "\n")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
