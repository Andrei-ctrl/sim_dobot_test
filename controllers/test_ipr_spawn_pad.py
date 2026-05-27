"""Unit tests for ipr_spawn_pad."""

import sys
import unittest
from unittest import mock

sys.path.insert(0, "controllers")
import ipr_spawn_pad as pad


class TestIprSpawnPad(unittest.TestCase):
    def test_fallback_when_def_missing(self):
        position, rotation, ok = pad.resolve_spawn_pad(lambda _name: None)
        self.assertFalse(ok)
        self.assertEqual(position, pad.FALLBACK_SPAWN_XYZ)
        self.assertEqual(rotation, pad.FALLBACK_SPAWN_ROTATION)

    def test_resolves_from_spawn_pad_def(self):
        node = mock.MagicMock()

        def get_from_def(name):
            return node if name == pad.IPR_BOX_SPAWN_PAD_DEF else None

        position, rotation, ok = pad.resolve_spawn_pad(get_from_def)
        self.assertTrue(ok)
        self.assertEqual(position, pad.BOX_SPAWN_XYZ)
        self.assertEqual(rotation, pad.BOX_SPAWN_ROTATION)

    def test_fallback_uses_measured_box_pose(self):
        position, rotation, ok = pad.resolve_spawn_pad(lambda _name: None)
        self.assertFalse(ok)
        self.assertEqual(position, pad.BOX_SPAWN_XYZ)
        self.assertEqual(rotation, pad.BOX_SPAWN_ROTATION)


if __name__ == "__main__":
    unittest.main()
