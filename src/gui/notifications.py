"""Native OS notification-centre messages.

Qt's tray bridge is used (QSystemTrayIcon.showMessage): macOS posts to
Notification Center, Windows to Action Center toasts, Linux to
org.freedesktop.Notifications. No third-party dependency.
"""
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

_tray = None
_last = None  # last (title, message) — repeat messages stay silent, as the
              # old in-app notification list deduplicated identical entries
_action = None


def notify(title, message, activated=None):
    """Post to the OS notification centre; `activated` runs when clicked."""
    global _last, _action
    if (title, message) == _last:
        return
    _last = (title, message)
    app = QApplication.instance()
    if app is None:
        return
    tray = _ensure_tray(app)
    if tray is None:
        return
    _action = activated
    tray.showMessage(title, message, QSystemTrayIcon.Information, 10000)


def _ensure_tray(app):
    global _tray
    if _tray is not None:
        return _tray
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None
    tray = QSystemTrayIcon(app.windowIcon() or QIcon(), app)
    tray.messageClicked.connect(_clicked)
    # macOS delivers notifications with no visible status item, so the menu
    # bar stays clean; every other desktop needs a registered tray icon for
    # showMessage — it lands in the overflow area unless the user pins it.
    if sys.platform != 'darwin':
        tray.show()
    _tray = tray
    return _tray


def _clicked():
    global _action
    callback, _action = _action, None
    if callback:
        callback()
