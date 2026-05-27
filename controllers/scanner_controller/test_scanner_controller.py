"""Unit tests for conveyor scanner box detection (verbose console output)."""

import sys
import unittest
from pathlib import Path

_LOGIC_DIR = Path(__file__).resolve().parent.parent / "youbot_restocker_demo"
if str(_LOGIC_DIR) not in sys.path:
    sys.path.insert(0, str(_LOGIC_DIR))

import youbot_restocker_logic as scan_logic  # noqa: E402

BOX = scan_logic.FIXED_PICK_BOX_POS


def log(title, detail=""):
    msg = f"[TEST] {title}"
    if detail:
        msg += f" — {detail}"
    print(msg)


class TestUpstreamScannerZone(unittest.TestCase):
    def test_box_on_conveyor_near_scanner_is_detected(self):
        pos = [0.0, 0.54, 0.2]
        info = scan_logic.build_box_scan_info("SPAWNED_BOX_1", pos)
        log("Conveyor box near scanner", f"dist={info['dist_to_scanner']:.3f}m")
        self.assertTrue(info["in_scanner_zone"])

    def test_fixed_pick_slot_not_in_upstream_scanner(self):
        pos = list(BOX)
        info = scan_logic.build_box_scan_info("SPAWNED_BOX_0", pos)
        log("Fixed pick slot vs upstream scanner", f"dist={info['dist_to_scanner']:.3f}m")
        self.assertFalse(info["in_scanner_zone"])
        self.assertTrue(info["at_fixed_pick_slot"])


class TestFixedPickSlotZone(unittest.TestCase):
    def test_webots_scene_box_at_pick_slot(self):
        pos = list(BOX)
        info = scan_logic.build_box_scan_info("SPAWNED_BOX_0", pos)
        log("Webots scene box", str(info["at_fixed_pick_slot"]))
        self.assertTrue(info["at_fixed_pick_slot"])
        self.assertTrue(info["pickable"])
        self.assertAlmostEqual(info["dist_to_pick_slot"], 0.0, places=3)

    def test_ipr_spawn_area_not_at_pick_slot(self):
        pos = [8.864, 1.138, 0.190]
        info = scan_logic.build_box_scan_info("SPAWNED_BOX_2", pos)
        log("IPR spawn area", f"dist_pick={info['dist_to_pick_slot']:.2f}m")
        self.assertFalse(info["at_fixed_pick_slot"])
        self.assertFalse(info["pickable"])


class TestBoxScanLog(unittest.TestCase):
    def test_format_includes_all_fields(self):
        info = scan_logic.build_box_scan_info("SPAWNED_BOX_0", list(BOX))
        info.update({
            "product_id": "BEER_BOTTLE",
            "name": "SPAWNED_BOX",
            "category": "Drinks",
            "size": [0.1, 0.1, 0.1],
            "mass": 0.1,
            "zone": "fixed_pick_slot",
            "distance_sensor": 0.42,
        })
        text = scan_logic.format_box_scan_log(info)
        log("Formatted scan log", f"{len(text.splitlines())} lines")
        print(text)
        self.assertIn("SPAWNED_BOX_0", text)
        self.assertIn("BEER_BOTTLE", text)
        self.assertIn("fixed_pick_slot", text)
        self.assertIn("at_slot=True", text)


class TestDualZoneWorkflow(unittest.TestCase):
    def test_box_journey_upstream_then_pick_slot(self):
        upstream_pos = [0.05, 0.60, 0.20]
        pick_pos = list(BOX)

        up = scan_logic.build_box_scan_info("SPAWNED_BOX_3", upstream_pos)
        pick = scan_logic.build_box_scan_info("SPAWNED_BOX_3", pick_pos)

        log("Journey stage 1 upstream", f"in_zone={up['in_scanner_zone']}")
        log("Journey stage 2 pick slot", f"at_slot={pick['at_fixed_pick_slot']}")

        self.assertTrue(up["in_scanner_zone"])
        self.assertFalse(up["at_fixed_pick_slot"])
        self.assertFalse(pick["in_scanner_zone"])
        self.assertTrue(pick["at_fixed_pick_slot"])


def run_tests():
    print("\n" + "=" * 60)
    print("Scanner Controller — unit tests (verbose console log)")
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
