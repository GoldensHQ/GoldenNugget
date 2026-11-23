"""Shared preset actions.

Every action (``load_preset_flow`` and friends) takes a preset **name** and is
the single implementation of what a preset action does: confirm dialogs,
safety-rule warnings and restart. The Settings and Presets pages call into
them, so the two entry points can never drift apart.
"""

import os
import sys
from typing import Optional

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from src.controllers.hotload import HotLoad
from src.controllers.preset_manager import PresetManager
from src.devicemanagement.device_capabilities import device_os_name
from src.gui.dialogs.confirmation import ask_confirmation
from src.gui.dialogs.hotload_warning import confirm_flagged

# _ = translate
_T = QCoreApplication.translate


def restart_app():
    """Relaunch the app so freshly loaded settings take effect."""
    os.execl(sys.executable, sys.executable, *sys.argv)


# ---------------------------------------------------------------------------
# display helpers
# ---------------------------------------------------------------------------

def preset_subtitle(meta: dict) -> str:
    """One-line secondary text for a preset row: device, iOS, tags."""
    if not meta:
        return ""
    model = meta.get("device_model") or "Unknown"
    ios = meta.get("ios_version") or "Unknown"
    text = _T("Nugget", "{0} • {1} {2}").format(model, device_os_name(model), ios)
    tags = meta.get("tags") or []
    if tags:
        text += "  #" + " #".join(tags)
    return text


def _major_version(ver: str):
    try:
        return int(str(ver).split(".")[0])
    except (ValueError, TypeError, IndexError):
        return None


def _device_type(model: str) -> str:
    model = str(model or "")
    if model.lower().startswith("iphone"):
        return "iPhone"
    if model.lower().startswith("ipad"):
        return "iPad"
    return ""


def daemon_compat_warning(name: str, meta, window) -> Optional[str]:
    """Warn when a preset's daemons were saved for a different device/iOS."""
    pm = PresetManager()
    if not pm.preset_has_daemon_changes(name):
        return None
    dm = window.device_manager
    cur_ver = dm.get_current_device_version() or ""
    cur_model = dm.get_current_device_model() or ""
    pr_ver = (meta.get("ios_version") or "") if meta else ""
    pr_model = (meta.get("device_model") or "") if meta else ""

    mismatches = []
    pr_major, cur_major = _major_version(pr_ver), _major_version(cur_ver)
    if pr_major is not None and cur_major is not None and pr_major != cur_major:
        mismatches.append(
            _T("Nugget", "iOS {0}x vs current iOS {1}x").format(pr_major, cur_major))
    pr_type, cur_type = _device_type(pr_model), _device_type(cur_model)
    if pr_type and cur_type and pr_type != cur_type:
        mismatches.append(
            _T("Nugget", "{0} vs current {1}").format(pr_type, cur_type))
    if not mismatches:
        return None
    return (
        _T("Nugget",
           "This preset contains daemon modifications that were saved for a "
           "different device:\n\n")
        + "\n".join("• " + m for m in mismatches)
        + "\n\n"
        + _T("Nugget",
             "Daemons are sensitive to the iOS version and device type, and "
             "applying incompatible ones can bootloop your device. "
             "Proceed with caution.")
    )


# ---------------------------------------------------------------------------
# actions (shared by the Settings page and the popup)
# ---------------------------------------------------------------------------

def load_preset_flow(parent, window, pm: PresetManager, name: str,
                     display_name: str = None, *, restart: bool = True) -> bool:
    """Confirm, safety-check, load *name*, then restart. True if loaded."""
    shown_name = display_name or name
    meta = pm.get_preset_metadata(name)
    desc = meta.get("description", "") if meta else ""
    model = meta.get("device_model", "Unknown") if meta else "Unknown"
    ios = meta.get("ios_version", "Unknown") if meta else "Unknown"
    confirm = ask_confirmation(parent,
            _T("Nugget", "Load Preset"),
            _T("Nugget",
           "Load preset \"{0}\"?\n\nDescription: {1}\nDevice: {2} • iOS {3}"
           "\n\nThis will replace your current configuration.").format(
               shown_name, desc, model, ios),
            confirm_text=QCoreApplication.translate("Nugget", "Load Preset"))
    if not confirm:
        return False

    dm = window.device_manager
    hotload = HotLoad(getattr(window, "settings", None))
    hidden_feats = pm.preset_hidden_feature_names(
        name, hotload,
        device_version=dm.get_current_device_version(),
        device_model=dm.get_current_device_model())
    if hidden_feats:
        QMessageBox.warning(
            parent, _T("Nugget", "Hidden Features Skipped"),
            _T("Nugget",
               "This preset contains features that are currently hidden by "
               "the safety rules for this device:\n\n• {0}\n\n"
               "They will NOT be loaded, so applying may not match the "
               "preset's intended state.").format("\n• ".join(hidden_feats)))

    compat_msg = daemon_compat_warning(name, meta, window)
    if compat_msg:
        reply = ask_confirmation(
            parent, _T("Nugget", "Daemon Compatibility"), compat_msg,
            confirm_text=_T("Nugget", "Load Anyway"))
        if not reply:
            return False

    if pm.preset_has_daemon_changes(name):
        rule = hotload.rule_for(
            "Daemons",
            device_version=dm.get_current_device_version(),
            device_model=dm.get_current_device_model())
        if rule is not None and not confirm_flagged(rule, parent):
            return False

    if not pm.load_preset(name):
        QMessageBox.critical(
            parent, _T("Nugget", "Load Preset"),
            _T("Nugget", "Failed to load the preset."))
        return False

    window.settings.setValue("last_loaded_preset", name)
    # Loading sets the tweaks directly, without the change callback that keeps
    # AutoSave current, and startup restores AutoSave when autosave is on, so
    # write it now or the restart would bring back the previous configuration
    # (the CLI's `preset load` does the same).
    save_autosave = getattr(window, "_save_autosave_preset", None)
    if save_autosave is not None:
        save_autosave()
    window._sync_settings()
    if not restart:
        return True
    QMessageBox.information(
        parent, _T("Nugget", "Load Preset"),
        _T("Nugget",
           "Preset \"{0}\" loaded.\n\nGoldenNugget will now restart to "
           "apply the changes.").format(shown_name))
    restart_app()
    return True


def rollback_preset_flow(parent, window, pm: PresetManager) -> bool:
    """Load the snapshot captured before the last successful apply."""
    name = "__Rollback"
    if not os.path.isfile(pm.get_preset_path(name)):
        QMessageBox.information(
            parent, _T("Nugget", "Rollback Last Apply"),
            _T("Nugget", "There is no previous successful apply to roll back yet."))
        return False
    return load_preset_flow(
        parent, window, pm, name,
        display_name=_T("Nugget", "Previous applied state"))


def save_preset_flow(parent, window, pm: PresetManager,
                     name: str, desc: str = "") -> bool:
    name = (name or "").strip()
    if not name:
        QMessageBox.warning(
            parent, _T("Nugget", "Save Preset"),
            _T("Nugget", "Enter a name for this preset."))
        return False
    dm = window.device_manager
    if not pm.save_preset(
            name, desc, tags=[],
            device_model=dm.get_current_device_model() or "",
            ios_version=dm.get_current_device_version() or ""):
        QMessageBox.critical(
            parent, _T("Nugget", "Save Preset"),
            _T("Nugget", "Failed to save the preset."))
        return False
    return True


def delete_preset_flow(parent, pm: PresetManager, name: str) -> bool:
    if not name:
        QMessageBox.warning(
            parent, _T("Nugget", "Delete Preset"),
            _T("Nugget", "Select a preset to delete first."))
        return False
    confirm = ask_confirmation(parent,
            _T("Nugget", "Delete Preset"),
            _T("Nugget", "Delete preset \"{0}\"?").format(name),
            confirm_text=QCoreApplication.translate("Nugget", "Delete Preset"),
            destructive=True)
    if not confirm:
        return False
    if not pm.delete_preset(name):
        QMessageBox.critical(
            parent, _T("Nugget", "Delete Preset"),
            _T("Nugget", "Failed to delete the preset."))
        return False
    return True


def export_preset_flow(parent, pm: PresetManager, name: str) -> bool:
    if not name:
        QMessageBox.warning(
            parent, _T("Nugget", "Export Preset"),
            _T("Nugget", "Select a preset to export first."))
        return False
    file_path, selected_filter = QFileDialog.getSaveFileName(
        parent, _T("Nugget", "Export Preset"), f"{name}.json",
        _T("Nugget", "JSON Files (*.json);;Portable Preset with Templates and Icons (*.gnpreset)"))
    if not file_path:
        return False
    if '*.gnpreset' in selected_filter and not file_path.lower().endswith('.gnpreset'):
        file_path = os.path.splitext(file_path)[0] + '.gnpreset'
    from src.gui.dialogs.file_task import run_file_task
    if not run_file_task(parent, _T('Nugget', 'Export Preset'),
                         lambda: pm.export_preset(name, file_path)):
        QMessageBox.critical(
            parent, _T("Nugget", "Export Preset"),
            _T("Nugget", "Failed to export preset:\n{0}").format(pm.last_transfer_error))
        return False
    QMessageBox.information(
        parent, _T("Nugget", "Export Preset"),
        _T("Nugget", "Preset exported to:\n{0}").format(file_path))
    return True


def partial_export_preset_flow(parent, pm: PresetManager, name: str) -> bool:
    if not name:
        QMessageBox.warning(
            parent, _T("Nugget", "Partial Export"),
            _T("Nugget", "Select a preset to export first."))
        return False
    from src.gui.dialogs.preset_partial_export import PartialExportDialog
    dialog = PartialExportDialog(parent=parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return False
    selected = dialog.selected_tweaks()
    if not selected:
        QMessageBox.warning(
            parent, _T("Nugget", "Partial Export"),
            _T("Nugget", "Select at least one tweak to export."))
        return False
    file_path, selected_filter = QFileDialog.getSaveFileName(
        parent, _T("Nugget", "Partial Export"), f"{name}.json",
        _T("Nugget", "JSON Files (*.json);;Portable Preset with Templates and Icons (*.gnpreset)"))
    if not file_path:
        return False
    if '*.gnpreset' in selected_filter and not file_path.lower().endswith('.gnpreset'):
        file_path = os.path.splitext(file_path)[0] + '.gnpreset'
    from src.gui.dialogs.file_task import run_file_task
    if not run_file_task(parent, _T('Nugget', 'Partial Export'),
                         lambda: pm.export_preset(name, file_path, include=selected)):
        QMessageBox.critical(
            parent, _T("Nugget", "Partial Export"),
            _T("Nugget", "Failed to export preset:\n{0}").format(pm.last_transfer_error))
        return False
    QMessageBox.information(
        parent, _T("Nugget", "Partial Export"),
        _T("Nugget", "Preset exported to:\n{0}").format(file_path))
    return True


def import_preset_flow(parent, pm: PresetManager) -> Optional[str]:
    """Import a preset file. Returns the new preset name, or None."""
    file_path, _ = QFileDialog.getOpenFileName(
        parent, _T("Nugget", "Import Preset"), "",
        _T("Nugget", "Preset Files (*.json *.gnpreset)"))
    if not file_path:
        return None
    from src.gui.dialogs.file_task import run_file_task
    success, result = run_file_task(parent, _T('Nugget', 'Import Preset'),
                                    lambda: pm.import_preset(file_path))
    if not success:
        QMessageBox.critical(
            parent, _T("Nugget", "Import Preset"),
            _T("Nugget", "Failed to import preset:\n{0}").format(result))
        return None
    QMessageBox.information(
        parent, _T("Nugget", "Import Preset"),
        _T("Nugget", "Preset \"{0}\" imported successfully.").format(result))
    return result
