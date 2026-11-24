"""Atomic local preset repository with bounded metadata reads; no tweak state or Qt."""
import copy
import logging
import os
import tempfile
import time
from threading import RLock

from .preset_format import (
    CURRENT_VERSION,
    JSON_EXTENSION,
    YAML_EXTENSIONS,
    dumps,
    read_metadata,
)
from .preset_version import stamp_preset_version

PRESET_VERSION = CURRENT_VERSION

_LOCAL_EXTENSIONS = YAML_EXTENSIONS + (JSON_EXTENSION,)


class PresetRepository:
    def __init__(self, directory):
        self.presets_dir = os.fspath(directory)
        self._metadata_cache = {}
        self._metadata_lock = RLock()
        self.last_error = ""
        os.makedirs(self.presets_dir, exist_ok=True)

    def _sanitize_name(self, name: str) -> str:
        safe = "".join(c for c in name if c.isalnum() or c in " _-").strip()
        return safe or "Preset"

    def get_preset_path(self, name: str) -> str:
        """The existing preset file for *name*, or the path a new one takes.

        Legacy ``.json`` presets stay readable under their original name; new
        presets are always written as version-3 ``.yaml``.
        """
        safe_name = self._sanitize_name(name)
        if name == "AutoSave":
            # AutoSave is a hot, JSON-only cache written by autosave_store.
            return os.path.join(self.presets_dir, f"{safe_name}{JSON_EXTENSION}")
        for ext in _LOCAL_EXTENSIONS:
            path = os.path.join(self.presets_dir, f"{safe_name}{ext}")
            if os.path.isfile(path):
                return path
        return os.path.join(self.presets_dir, f"{safe_name}{YAML_EXTENSIONS[0]}")

    def write_path(self, name: str) -> str:
        """Where a preset is written, independent of any legacy file present."""
        if name == "AutoSave":
            return os.path.join(self.presets_dir, f"{self._sanitize_name(name)}{JSON_EXTENSION}")
        return os.path.join(self.presets_dir, f"{self._sanitize_name(name)}{YAML_EXTENSIONS[0]}")

    def list_presets(self) -> list[str]:
        names = set()
        if not os.path.isdir(self.presets_dir):
            return []
        for file in os.listdir(self.presets_dir):
            for ext in _LOCAL_EXTENSIONS:
                if file.lower().endswith(ext):
                    names.add(file[:-len(ext)])
                    break
        return sorted(names)

    def get_preset_metadata(self, name: str) -> dict | None:
        """Get metadata for a preset without loading all of its tweaks."""
        file_path = self.get_preset_path(name)
        try:
            st = os.stat(file_path)
            signature = (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
            with self._metadata_lock:
                cached = self._metadata_cache.get(file_path)
                if cached is not None and cached[0] == signature:
                    return copy.deepcopy(cached[1])
            meta = read_metadata(file_path)
            with self._metadata_lock:
                if len(self._metadata_cache) >= 256 and file_path not in self._metadata_cache:
                    self._metadata_cache.pop(next(iter(self._metadata_cache)))
                self._metadata_cache[file_path] = signature, meta
            return copy.deepcopy(meta)
        except OSError:
            return None

    def save_snapshot(self, name: str, snapshot: dict, description="", tags=None,
                      device_model="", ios_version="", *, should_commit=None) -> bool:
        data = copy.copy(snapshot)
        self.last_error = ""
        now = int(time.time())
        meta = {
            "version": PRESET_VERSION,
            "description": description or "",
            "device_model": device_model or "Unknown",
            "ios_version": ios_version or "Unknown",
            "created_at": now,
            "updated_at": now,
            "tags": tags or [],
        }
        existing_meta = self.get_preset_metadata(name)
        if existing_meta and "created_at" in existing_meta:
            meta["created_at"] = existing_meta["created_at"]

        data["metadata"] = meta
        stamp_preset_version(data)

        file_path = self.write_path(name)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                    dir=self.presets_dir, prefix=".preset-", suffix=".tmp", delete=False) as f:
                temporary = f.name
                f.write(dumps("v3", data))
            if should_commit is not None and not should_commit():
                return False
            os.replace(temporary, file_path)
            temporary = None
            with self._metadata_lock:
                self._metadata_cache.pop(file_path, None)
                self._metadata_cache.pop(self.get_preset_path(name), None)
            return True
        except Exception as e:
            self.last_error = str(e)
            logging.getLogger("GoldenNugget.presets").error("Could not save preset %s: %s", name, e)
            return False
        finally:
            if temporary is not None:
                try:
                    os.remove(temporary)
                except FileNotFoundError:
                    pass

    def copy_preset(self, source_name: str, target_name: str) -> bool:
        """Copy one local preset to another name, normalizing to v3 YAML."""
        from .preset_format import PresetFormatError, load
        source = self.get_preset_path(source_name)
        if not os.path.isfile(source):
            return False
        try:
            data = load(source)
        except PresetFormatError:
            return False
        return self.save_snapshot(target_name, data,
                                  description=(data.get("metadata") or {}).get("description", ""),
                                  tags=(data.get("metadata") or {}).get("tags"),
                                  device_model=(data.get("metadata") or {}).get("device_model", ""),
                                  ios_version=(data.get("metadata") or {}).get("ios_version", ""))

    def delete_preset(self, name):
        removed = False
        for ext in _LOCAL_EXTENSIONS:
            path = os.path.join(self.presets_dir, f"{self._sanitize_name(name)}{ext}")
            try:
                os.remove(path)
                removed = True
            except FileNotFoundError:
                continue
            except OSError as exc:
                self.last_error = str(exc)
                logging.getLogger("GoldenNugget.presets").error("Could not delete preset %s: %s", name, exc)
                return False
            with self._metadata_lock:
                self._metadata_cache.pop(path, None)
        return removed
