import os
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

app = QApplication([])

from src.devicemanagement.progress_status import REBOOT_WAIT_MESSAGE
from src.gui.main_window_mixins import ApplyMixin


class FakeSurface:
    def __init__(self):
        self.statuses = []

    def show_process_status(self, text):
        self.statuses.append(text)

    def set_status(self, text):
        self.statuses.append(text)


class FakeWindow:
    def __init__(self):
        self.ios_home = FakeSurface()
        self.ios_apply = FakeSurface()


window = FakeWindow()

with patch('src.gui.main_window_mixins.notify') as notify:
    # Both of these arrive before the reboot and used to pop the notification.
    ApplyMixin.update_label(window, 'iOS authentication prompt detected. '
                            'Check your iPhone and enter its passcode if '
                            'requested to continue the protective backup.')
    ApplyMixin.update_label(window, 'Your iPhone is locked. Unlock it and '
                            'enter its passcode to continue restoring your '
                            'photos and videos.')
    assert notify.call_count == 0, notify.call_args_list

    # This is the post-reboot reconnect wait — the one time the user is needed.
    ApplyMixin.update_label(window, f'{REBOOT_WAIT_MESSAGE} (0:03 elapsed)...')
    assert notify.call_count == 1, notify.call_args_list

    # A later passcode prompt for the same wait must not notify again.
    ApplyMixin.update_label(window, 'Your iPhone is locked. Unlock it and '
                            'enter its passcode to continue.')
    assert notify.call_count == 1, notify.call_args_list

assert window.ios_home.statuses
assert window.ios_apply.statuses == window.ios_home.statuses

print('attention notification timing OK')
