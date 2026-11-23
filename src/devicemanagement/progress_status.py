"""Status text with optional backup-category metadata; remains string-compatible."""

# Emitted by the reconnect wait *after* the device has been rebooted. The GUI
# uses it to tell a genuine "device needs you" wait apart from the passcode
# prompts that happen during the pre-reboot backup.
REBOOT_WAIT_MESSAGE = "Waiting for device after reboot"


def is_waiting_after_reboot(text: str) -> bool:
    """Whether ``text`` comes from the post-reboot reconnect wait."""
    return REBOOT_WAIT_MESSAGE in text


class OperationStatus(str):
    def __new__(cls, text, category):
        instance = super().__new__(cls, text)
        instance.category = category
        return instance


class BackupStatus(OperationStatus):
    pass
