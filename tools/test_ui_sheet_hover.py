"""The stretched hover pill must stay hidden while a sheet floats above its button.

The pill is painted by a window-level surface that reaches 36 px past the
button, so its bulge used to show through the 8 px gap between the sheet and
the button it was opened from (a stray red/blue bubble under the sheet).
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import resources_rc  # noqa: F401  (icons used by the sheet)
from PySide6.QtWidgets import QApplication, QWidget
from settings_sandbox import SettingsSandbox

from awesomeui.liquid.controls import LiquidDangerButton as AwesomeDangerButton
from src.gui.liquid.controls import LiquidDangerButton
from src.gui.liquid.restore_changes_panel import RestoreChangesPanel
from src.gui.theme import ColorThemeManager

APP = QApplication.instance() or QApplication([])

BUTTONS = (LiquidDangerButton, AwesomeDangerButton)


class SheetHoverLock(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        sandbox = SettingsSandbox(Path(directory.name))
        sandbox.__enter__()
        self.addCleanup(sandbox.__exit__, None, None, None)
        old_manager = ColorThemeManager._inst
        self.addCleanup(setattr, ColorThemeManager, '_inst', old_manager)
        ColorThemeManager._inst = ColorThemeManager()
        self.window = QWidget()
        self.window.resize(400, 320)
        self.window.show()
        self.addCleanup(self.window.deleteLater)

    def button(self, cls):
        button = cls('Restore Changes', self.window)
        button.setProperty('homeAction', True)
        button.setGeometry(20, 200, 300, 40)
        button.show()
        self.addCleanup(button.deleteLater)
        return button

    def test_locked_button_never_shows_the_pill(self):
        for cls in BUTTONS:
            with self.subTest(button=cls.__name__):
                button = self.button(cls)
                button._hover_to(1.0)
                button._set_hover(1.0)
                surface = button._stretch_surface
                self.assertIsNotNone(surface)
                self.assertTrue(surface.isVisible())

                button.set_hover_locked(True)
                self.assertFalse(surface.isVisible())

                button._hover_to(1.0)
                button._set_hover(1.0)
                self.assertFalse(surface.isVisible(), 'hover must stay locked')

                button.set_hover_locked(False)
                button._hover_to(1.0)
                button._set_hover(1.0)
                self.assertTrue(surface.isVisible(), 'hover must work again')
                button.set_hover_locked(True)

    def test_restore_sheet_locks_its_anchor(self):
        window = self.window
        manager = type('DeviceManager', (), {
            'get_current_device_udid': lambda self: None,
            'get_current_device_model': lambda self: '',
        })()
        window.device_manager = manager
        window.apply_in_progress = False
        window.ios_home = None
        window.liquid = type('Liquid', (), {
            'restore': type('Restore', (), {'hide': lambda self: None})(),
        })()
        panel = RestoreChangesPanel(window)
        self.addCleanup(panel.deleteLater)
        button = self.button(LiquidDangerButton)
        panel.anchor = button

        panel.show()
        self.assertTrue(getattr(button, '_hover_locked', False))
        panel.hide()
        self.assertFalse(getattr(button, '_hover_locked', True))


if __name__ == '__main__':
    unittest.main(verbosity=2)
