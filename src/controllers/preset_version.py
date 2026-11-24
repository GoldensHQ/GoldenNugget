"""Record which GoldenNugget build wrote a preset.

The stamp lives at the top level of the preset JSON (next to ``metadata`` and
``tweaks``), under ``GNUGGET_VERSION``. It is metadata about the *writer*, not
the preset format version or the device's iOS version, so it survives export
and import instead of being refreshed by whichever build happens to import
the file.
"""

from src.version import GNUGGET_VERSION, App_Version  # noqa: F401 - re-exported


def preset_version() -> str:
    """The version written into new preset stamps."""
    return str(App_Version)


def stamp_preset_version(data: dict, *, preserve: bool = False) -> dict:
    """Put ``GNUGGET_VERSION`` on *data* and return it.

    With ``preserve=True`` an existing non-empty string stamp (the build that
    originally created the preset) wins; legacy presets without a usable stamp
    are stamped with the current version.
    """
    if not isinstance(data, dict):
        return data
    existing = data.get(GNUGGET_VERSION)
    if preserve and isinstance(existing, str) and existing:
        return data
    data[GNUGGET_VERSION] = preset_version()
    return data
