import os
import tempfile
import unittest

from core import utils, config


class TestUtils(unittest.TestCase):
    def test_save_list_creates_file_and_contents(self):
        with tempfile.TemporaryDirectory() as td:
            # point SAVE_DIR to temp dir
            old_save = config.SAVE_DIR
            config.SAVE_DIR = td
            try:
                filename = "test_list.txt"
                items = ["a", "b", "c"]
                path = utils.save_list(filename, items)
                self.assertIsNotNone(path)
                self.assertTrue(os.path.exists(path))
                with open(path, "r", encoding="utf-8") as f:
                    lines = [l.strip() for l in f.readlines()]
                self.assertEqual(lines, items)
            finally:
                config.SAVE_DIR = old_save
