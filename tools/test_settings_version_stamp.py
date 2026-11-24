#!/usr/bin/env python3
"""Offline checks for the writer-version mark in the settings file.

The 9.7.x settings wrapper is QSettings-based: ``GNUGGET_VERSION`` is left in
the primary ("GoldenNugget") store on the first real write and refreshed on
each later one. Reads alone must not create the file, and the legacy "Nugget"
store is never stamped so an older build still sees its own values.

Run: python tools/test_settings_version_stamp.py
"""

import configparser
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QSettings

from src.controllers import settings as settings_module
from src.version import GNUGGET_VERSION, App_Version


class SettingsVersionStampTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Qt caches the XDG config location at first use, so isolate it before
        # QCoreApplication (and any QSettings) is created. Each test below uses
        # its own app name to keep the stores independent.
        cls.tmp = tempfile.TemporaryDirectory(prefix="gn_settings_stamp_")
        os.environ["XDG_CONFIG_HOME"] = cls.tmp.name
        cls.app = QCoreApplication.instance() or QCoreApplication([])
        QSettings.setDefaultFormat(QSettings.IniFormat)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def path(self, app, org="GoldenNugget"):
        return Path(self.tmp.name) / org / f"{app}.conf"

    def payload(self, app):
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(self.path(app), encoding="utf-8")
        return dict(parser["General"])

    def test_read_never_creates_a_stamped_file(self):
        settings = settings_module.Settings("read_only")
        self.assertIsNone(settings.value("missing", None))
        self.assertFalse(self.path("read_only").exists())

    def test_first_write_leaves_current_build_stamp(self):
        settings = settings_module.Settings("first_write")
        settings.setValue("hotload_enabled", True)
        settings.sync()
        data = self.payload("first_write")
        self.assertEqual(data[GNUGGET_VERSION.lower()], App_Version)
        self.assertEqual(data["hotload_enabled"], "true")

    def test_stamp_is_readable_and_refreshed_on_a_later_write(self):
        settings = settings_module.Settings("refresh")
        settings.setValue("first", 1)
        self.assertEqual(settings.value(GNUGGET_VERSION, type=str), App_Version)
        with patch.object(settings_module, "App_Version", "99.9"):
            settings.setValue("second", 2)
            settings.sync()
        self.assertEqual(self.payload("refresh")[GNUGGET_VERSION.lower()], "99.9")

    def test_legacy_store_is_never_stamped(self):
        settings = settings_module.Settings("primary_only")
        settings.setValue("new", 1)
        settings.sync()
        self.assertTrue(self.path("primary_only").exists())
        self.assertFalse(self.path("primary_only", "Nugget").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
