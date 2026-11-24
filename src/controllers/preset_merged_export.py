"""Write the compatibility "merged export" without adopting preset v3 locally.

A merged ``.gnmpreset`` file is plain YAML text with one shared ``HEADER`` and
two complete presets as literal blocks: a version-3 YAML representation and the
legacy version-2 JSON dictionary this build still uses everywhere else. The
note spells out that v2 already carries everything an older build needs.

This module only WRITES. Main keeps its JSON presets, its JSON/portable imports
and its existing export choices; there is no v3 reader, no YAML dependency and
no raw v3 export here.
"""
import json
import os
import tempfile

from src.version import App_Version

# Older merged files may carry this stamp; main does not write it locally, but
# preserving it keeps the header faithful when one is present in the source.
GNUGGET_VERSION = "GNUGGET_VERSION"

FORMAT = "GoldenNugget merged preset"
EXTENSION = ".gnmpreset"
CURRENT_VERSION = 3
LEGACY_VERSION = 2

HEADER_KEY = "HEADER"
V3_KEY = "Preset Version 3 (YAML)"
V2_KEY = "Preset Version 2 (JSON)"
NOTE_KEY = "Note"
NOTE = "Preset version 2 contains all needed."


def _app_version(data: dict) -> str:
    value = data.get(GNUGGET_VERSION) if isinstance(data, dict) else None
    return str(value) if isinstance(value, str) and value else str(App_Version)


def _os_version(model, ios_version) -> str:
    name = "iPadOS" if str(model or "").startswith("iPad") else "iPhoneOS"
    version = str(ios_version or "Unknown").strip() or "Unknown"
    return f"{name} {version}"


def build_header(data: dict, includes: str) -> dict:
    """The shared header, derived from the preset's own metadata."""
    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    return {
        "PresetVersion": CURRENT_VERSION,
        "GNVersion": _app_version(data),
        "Device": str(meta.get("device_model") or "Unknown"),
        "OSVersion": _os_version(meta.get("device_model"), meta.get("ios_version")),
        "Includes": includes,
    }


def _scalar(value) -> str:
    # JSON is valid YAML flow style; json.dumps quotes strings and emits
    # YAML-compatible booleans, numbers and null without a YAML dependency.
    return json.dumps(value, ensure_ascii=False)


def _header_text(header: dict) -> str:
    lines = [f"{HEADER_KEY}:"]
    for key, value in header.items():
        # These are plain YAML scalars in block context; quoting them would
        # still parse, but the documented header spells them without quotes.
        # GNVersion stays quoted so a version like "9.7" cannot become a float.
        if key in ("Includes", "Device", "OSVersion"):
            rendered = str(value)
        else:
            rendered = _scalar(value)
        lines.append(f"  {key}: {rendered}")
    return "\n".join(lines)


def v2_document(data: dict) -> str:
    """The legacy, plain-JSON preset (metadata first, as main writes it)."""
    ignored = (HEADER_KEY, V3_KEY, V2_KEY, NOTE_KEY)
    out = {key: value for key, value in data.items() if key not in ignored}
    meta = dict(out.get("metadata") or {})
    meta["version"] = LEGACY_VERSION
    ordered = {"metadata": meta, **{key: value for key, value in out.items()
                                    if key != "metadata"}}
    return json.dumps(ordered, ensure_ascii=False, indent=2)


def v3_document(data: dict) -> str:
    """A YAML representation of the same preset, header first."""
    header = build_header(data, str(CURRENT_VERSION))
    meta = dict(data.get("metadata") or {})
    meta["version"] = CURRENT_VERSION
    lines = [_header_text(header), f"metadata: {_scalar(meta)}",
             f"tweaks: {_scalar(data.get('tweaks') or {})}"]
    ignored = {"metadata", "tweaks", GNUGGET_VERSION, HEADER_KEY,
               V3_KEY, V2_KEY, NOTE_KEY}
    for key in sorted(key for key in data if key not in ignored):
        lines.append(f"{key}: {_scalar(data[key])}")
    lines.append(f"{GNUGGET_VERSION}: {_scalar(_app_version(data))}")
    return "\n".join(lines)


def _literal_block(text: str) -> str:
    return "\n".join("  " + line for line in text.splitlines())


def dumps_merged(data: dict) -> str:
    """Serialize *data* as the merged YAML document."""
    header = build_header(data, f"{CURRENT_VERSION},{LEGACY_VERSION}")
    parts = [
        _header_text(header),
        f"{V3_KEY}: |-\n{_literal_block(v3_document(data))}",
        f"{V2_KEY}: |-\n{_literal_block(v2_document(data))}",
        f"{NOTE_KEY}: {NOTE}",
    ]
    return "\n".join(parts) + "\n"


def write_merged(data: dict, destination) -> str:
    """Atomically write a merged export and return the destination path."""
    destination = os.fspath(destination)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", delete=False,
            dir=os.path.dirname(os.path.abspath(destination)),
            prefix=".merged-preset-", suffix=".tmp",
        ) as stream:
            temporary = stream.name
            stream.write(dumps_merged(data))
        os.replace(temporary, destination)
        temporary = None
        return destination
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)
