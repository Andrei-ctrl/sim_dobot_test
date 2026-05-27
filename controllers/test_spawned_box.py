"""Unit tests for spawned_box labeling."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, "controllers")
import spawned_box as boxes


class TestSpawnedBox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_allocate_unique_uids(self):
        first = boxes.allocate_box_uid(self.tmp)
        second = boxes.allocate_box_uid(self.tmp)
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("BOX-"))
        self.assertTrue(second.startswith("BOX-"))

    def test_build_vrml_includes_product_name(self):
        vrml = boxes.build_cardboard_box_vrml(
            "SPAWNED_BOX_3",
            [1.0, 2.0, 0.2],
            boxes.DEFAULT_BOX_ROTATION,
            product_id="BEER_BOTTLE",
            box_uid="BOX-000003",
        )
        self.assertIn("DEF SPAWNED_BOX_3", vrml)
        self.assertIn("BEER_BOTTLE_BOX-000003", vrml)

    def test_label_vrml_has_two_lines(self):
        vrml = boxes.build_label_vrml("CHIPS", "BOX-000010")
        self.assertIn('"CHIPS"', vrml)
        self.assertIn('"BOX-000010"', vrml)


if __name__ == "__main__":
    unittest.main()
