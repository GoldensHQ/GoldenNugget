"""Small cross-platform file lock (``QLockFile`` replacement).

Used by the AutoSave writer so two GoldenNugget processes cannot interleave a
read-modify-write. The lock file contains the owning PID; a lock left behind
by a dead process is considered stale and is reclaimed.
"""

from __future__ import annotations

import os
import time

_STALE_SECONDS = 30.0


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not process:
                return False
            ctypes.windll.kernel32.CloseHandle(process)
            return True
        except Exception:
            return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class FileLock:
    """Exclusive lock file with ``QLockFile``-style ``tryLock(timeout_ms)``."""

    def __init__(self, path: str):
        self.path = str(path)
        self._locked = False
        # Set when the lock could not even be created (missing/permission-
        # denied parent, read-only volume). Without it every failure looks
        # like "another process holds it", which sent users chasing a ghost
        # process when the real cause was an unwritable folder.
        self.last_error: OSError | None = None

    def _stale(self) -> bool:
        try:
            with open(self.path, "r", encoding="utf-8") as stream:
                raw = stream.read().strip()
            pid = int(raw.split()[0]) if raw else -1
        except (OSError, ValueError):
            pid = -1
        if pid > 0 and _pid_alive(pid):
            return False
        try:
            age = time.time() - os.path.getmtime(self.path)
        except OSError:
            return True
        return age > _STALE_SECONDS

    def _reclaimable(self) -> bool:
        """True when the lock is stale right now.

        ``_stale()`` is checked, then the file's holder is re-read — between
        the two, another process may have created a fresh lock; deleting that
        one would leave two holders. Both reads must see the same stale
        holder before the unlink is allowed.
        """
        if not self._stale():
            return False
        try:
            with open(self.path, "r", encoding="utf-8") as stream:
                raw = stream.read().strip()
            pid = int(raw.split()[0]) if raw else -1
        except OSError:
            return True
        if pid > 0 and _pid_alive(pid):
            return False
        return self._stale()

    def tryLock(self, timeout_ms: int = 0) -> bool:  # noqa: N802 - QLockFile API
        self.last_error = None
        parent = os.path.dirname(self.path)
        if parent:
            try:
                os.makedirs(parent, exist_ok=True)
            except OSError as error:
                self.last_error = error
                return False
        deadline = time.monotonic() + max(0, timeout_ms) / 1000.0
        while True:
            try:
                descriptor = os.open(
                    self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                if self._reclaimable():
                    try:
                        os.unlink(self.path)
                    except OSError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.02)
                continue
            except OSError as error:
                self.last_error = error
                return False
            try:
                os.write(descriptor, f"{os.getpid()}\n".encode("ascii"))
            finally:
                os.close(descriptor)
            self._locked = True
            return True

    def unlock(self) -> None:
        if not self._locked:
            return
        self._locked = False
        try:
            os.unlink(self.path)
        except OSError:
            pass
