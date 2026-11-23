"""Backup errors must not be mistaken for a locked device."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymobiledevice3.exceptions import PasswordRequiredError

from src.exceptions.device_errors import (
    is_connection_error,
    is_device_locked_error,
    is_find_my_error,
    is_icloud_restore_in_progress,
    is_transient_restore_error,
)


class DeviceErrors(unittest.TestCase):
    def test_explicit_lock_errors_are_recognized(self):
        for error in (RuntimeError("Device locked"), RuntimeError("The device is locked"),
                      RuntimeError("MBErrorDomain/208"), PasswordRequiredError(),
                      RuntimeError("{'ErrorCode': 208, 'ErrorDescription': 'Locked'}"),
                      RuntimeError("ErrorCode 208")):
            with self.subTest(error=error):
                self.assertTrue(is_device_locked_error(error))

    def test_other_backup_errors_keep_their_original_meaning(self):
        for message in ("{'ErrorCode': 205, 'ErrorDomain': 'MBErrorDomain'}",
                        "ErrorCode 105: MBErrorDomain: disk full",
                        "ErrorCode 1208", "ErrorCode 2080",
                        "ErrorCode 205: missing payload in backup 208"):
            with self.subTest(message=message):
                self.assertFalse(is_device_locked_error(RuntimeError(message)))

    def test_alerts_without_an_exception_are_classified_safely(self):
        # A reconnect alert can carry only text. The GUI used to hand that
        # None straight to the chain walker, which crashed on __cause__.
        for predicate in (is_connection_error, is_find_my_error,
                          is_icloud_restore_in_progress,
                          is_transient_restore_error, is_device_locked_error):
            with self.subTest(predicate=predicate.__name__):
                self.assertFalse(predicate(None))

    def test_exception_args_may_contain_non_exceptions(self):
        # pymobiledevice3's result payloads often sit in args next to None or
        # a dict. They must be ignored, not traversed as exception wrappers.
        plain = RuntimeError("socket connection broken", None, {"Number": 3})
        self.assertTrue(is_connection_error(plain))
        self.assertFalse(is_icloud_restore_in_progress(plain))

        wrapped = RuntimeError("outer", None)
        wrapped.__cause__ = RuntimeError("MBErrorDomain/25")
        self.assertTrue(is_icloud_restore_in_progress(wrapped))

        # The code is normally followed by a colon and detail, not EOL.
        self.assertTrue(is_icloud_restore_in_progress(
            RuntimeError("MBErrorDomain/25: iCloud Restore In Progress")))
        self.assertFalse(is_icloud_restore_in_progress(
            RuntimeError("MBErrorDomain/250: different error")))


if __name__ == "__main__":
    unittest.main()
