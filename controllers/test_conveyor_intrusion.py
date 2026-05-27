import os
import sys
import unittest

_CONTROLLERS = os.path.dirname(os.path.abspath(__file__))
if _CONTROLLERS not in sys.path:
    sys.path.insert(0, _CONTROLLERS)

import conveyor_intrusion as logic


class TestConveyorIntrusion(unittest.TestCase):
    def test_duck_position_in_corridor(self):
        pos = [2.15, 0.56, 0.21]
        self.assertTrue(logic.in_conveyor_corridor(pos))

    def test_duck_not_in_scanner_zone_until_upstream(self):
        downstream = [2.15, 0.56, 0.21]
        upstream = [-0.02, 0.56, 0.20]
        self.assertFalse(logic.in_scanner_zone(downstream))
        self.assertTrue(logic.in_scanner_zone(upstream))

    def test_zone_marker_below_z_min(self):
        pos = [2.25, 0.54, 0.015]
        self.assertFalse(logic.in_conveyor_corridor(pos))

    def test_known_spawn_def_ignored(self):
        self.assertTrue(logic.is_known_def("SPAWNED_BOX_3"))
        self.assertFalse(logic.is_known_def("RubberDuck"))

    def test_ignore_conveyor_names(self):
        self.assertTrue(
            logic.should_ignore_node("Solid", "CONVEYOR_ZONE", "")
        )
        self.assertFalse(
            logic.should_ignore_node("RubberDuck", "rubber duck", "")
        )


if __name__ == "__main__":
    unittest.main()
