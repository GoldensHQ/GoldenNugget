#!/usr/bin/env python3
"""Offline regressions for the writer-version mark in settings JSON.

``src.utils.settings`` leaves a top-level ``GNUGGET_VERSION`` stamp in every
JSON store it writes. The stamp is file metadata, not a preference: reading it
must not create a file, and the mark must never show up as a setting.

Run: python tools/test_settings_version_stamp.py
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from settings_sandbox import SettingsSandbox

from src.utils import settings as settings_module
from src.version import GNUGGET_VERSION, App_Version


class SettingsVersionStampTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="gn_settings_stamp_")
        self.root = Path(self.tmp.name)
        self.sandbox = SettingsSandbox(self.root)
        self.Settings = self.sandbox.__enter__()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.sandbox.__exit__, None, None, None)

    def path(self, app="settings", org="GoldenNugget"):
        return self.root / org / f"{app}.json"

    def payload(self):
        return json.loads(self.path().read_text(encoding="utf-8"))

    def test_read_never_creates_a_stamped_file(self):
        settings = self.Settings("settings")
        self.assertIsNone(settings.value("missing", None))
        self.assertFalse(self.path().exists())

    def test_first_write_leaves_current_build_stamp(self):
        settings = self.Settings("settings")
        settings.setValue("hotload_enabled", True)
        data = self.payload()
        self.assertEqual(data[GNUGGET_VERSION], App_Version)
        self.assertIs(data["hotload_enabled"], True)

    def test_stamp_is_metadata_not_a_preference(self):
        settings = self.Settings("settings")
        settings.setValue("hotload_enabled", True)
        self.assertNotIn(GNUGGET_VERSION, settings.allKeys())
        self.assertFalse(settings.contains(GNUGGET_VERSION))
        self.assertIsNone(settings.value(GNUGGET_VERSION))

    def test_stamp_refreshes_on_a_later_write(self):
        settings = self.Settings("settings")
        settings.setValue("first", 1)
        with patch.object(settings_module, "App_Version", "99.9"):
            settings.setValue("second", 2)
        self.assertEqual(self.payload()[GNUGGET_VERSION], "99.9")

    def test_stale_stamp_is_ignored_and_replaced(self):
        path = self.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({GNUGGET_VERSION: "0.1", "kept": "value"}), encoding="utf-8"
        )
        settings = self.Settings("settings")
        self.assertEqual(settings.value("kept"), "value")
        self.assertNotIn(GNUGGET_VERSION, settings.allKeys())
        settings.setValue("other", 3)
        data = self.payload()
        self.assertEqual(data[GNUGGET_VERSION], App_Version)
        self.assertEqual(data["kept"], "value")

    def test_stamp_from_a_legacy_json_store_is_not_imported(self):
        legacy = {GNUGGET_VERSION: "0.1", "old": "yes"}
        with patch.object(
            settings_module, "_legacy_json", lambda org, app: dict(legacy)
        ):
            settings = self.Settings("settings")
            self.assertEqual(settings.value("old"), "yes")
            self.assertNotIn(GNUGGET_VERSION, settings.allKeys())
            settings.setValue("new", 1)
        data = self.payload()
        self.assertEqual(data[GNUGGET_VERSION], App_Version)
        self.assertNotIn(GNUGGET_VERSION, settings.allKeys())


if __name__ == "__main__":
    unittest.main(verbosity=2)
