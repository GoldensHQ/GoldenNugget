"""Preset file formats: YAML v3, legacy JSON v2 and the merged ``.gnmpreset``.

A version-3 preset is YAML. Its first mapping key is ``HEADER``::

    HEADER:
      PresetVersion: 3
      GNVersion: '10.0'
      Device: iPhone15,2
      OSVersion: iPhoneOS 26.2
      Includes: '3,2'
    metadata:
      ...
    tweaks:
      ...

The header describes the file, not the tweak state. ``Includes`` lists the
preset versions carried by the file (``3`` for a raw YAML preset, ``3,2`` for a
merged one). The rest of the document is the ordinary preset dictionary that
the rest of the backend consumes, so loading never depends on the version
written in the header.

A merged ``.gnmpreset`` is a single YAML mapping with the header plus the two
complete presets as text blocks::

    HEADER: {…, Includes: '3,2'}
    PresetVersion3: |
      HEADER: …
      metadata: …
      tweaks: …
    PresetVersion2: |
      {"metadata": …, "tweaks": …}

Keeping the legacy v2 block as literal JSON text means an older GoldenNugget
build can still read it after extracting it, and newer builds can pick the
newest representation they understand. JSON files (v2, share codes, community
catalog) keep working unchanged: JSON is parsed with ``json`` so numeric and
string types stay byte-exact, never with the YAML resolver.

PyYAML's YAML 1.1 implicit types turn ``yes``/``no``/``on``/``off`` into bools
and dates into ``datetime`` objects, which silently corrupts user text (a
description of ``on``, a device named ``2026-01-01``). Our loader keeps the
conservative ``true``/``false`` booleans, numbers and null only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from .preset_version import GNUGGET_VERSION, preset_version

CURRENT_VERSION = 3
LEGACY_VERSION = 2

HEADER_KEY = "HEADER"
# The merged file spells the two blocks out with their human-readable names.
# The compact aliases are accepted on read so early v3 drafts keep working.
V3_KEY = "Preset Version 3 (YAML)"
V2_KEY = "Preset Version 2 (JSON)"
V3_KEYS = (V3_KEY, "PresetVersion3")
V2_KEYS = (V2_KEY, "PresetVersion2")
MERGED_NOTE_KEY = "Note"
MERGED_NOTE = "Preset version 2 contains all needed."

YAML_EXTENSIONS = (".yaml", ".yml")
MERGED_EXTENSION = ".gnmpreset"
JSON_EXTENSION = ".json"
BUNDLE_EXTENSION = ".gnpreset"
PRESET_EXTENSIONS = YAML_EXTENSIONS + (MERGED_EXTENSION, JSON_EXTENSION, BUNDLE_EXTENSION)

FORMAT_MERGED = "merged"
FORMAT_V3 = "v3"
FORMAT_V2 = "v2"
FORMAT_BUNDLE = "bundle"
FORMATS = (FORMAT_MERGED, FORMAT_V3, FORMAT_V2)

_EXTENSION_FORMATS = {
    MERGED_EXTENSION: FORMAT_MERGED,
    **{ext: FORMAT_V3 for ext in YAML_EXTENSIONS},
    JSON_EXTENSION: FORMAT_V2,
    BUNDLE_EXTENSION: FORMAT_BUNDLE,
}


class PresetFormatError(ValueError):
    """Raised when a file is not a preset any supported version can read."""


class PresetLoader(yaml.SafeLoader):
    """SafeLoader without YAML 1.1's bool/timestamp surprises."""


class PresetDumper(yaml.SafeDumper):
    """SafeDumper that keeps embedded presets readable as literal blocks."""


def _represent_str(dumper, value):
    # Multiline strings (the merged file's v3/v2 blocks, multi-line
    # descriptions) read far better as ``|`` blocks than escaped quotes.
    return dumper.represent_scalar(
        "tag:yaml.org,2002:str", value, style="|" if "\n" in value else None)


PresetDumper.add_representer(str, _represent_str)


# Copy the resolver table before changing it: SafeLoader's table is shared and
# mutating it in place would change yaml.safe_load for the whole process.
PresetLoader.yaml_implicit_resolvers = {
    first: [(tag, pattern) for tag, pattern in resolvers
            if tag not in ("tag:yaml.org,2002:bool", "tag:yaml.org,2002:timestamp")]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
PresetLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
)


def format_for_path(path) -> str:
    """The requested export format from a destination's extension."""
    suffix = Path(str(path)).suffix.lower()
    return _EXTENSION_FORMATS.get(suffix, FORMAT_MERGED)


def default_extension(fmt: str) -> str:
    return {
        FORMAT_MERGED: MERGED_EXTENSION,
        FORMAT_V3: YAML_EXTENSIONS[0],
        FORMAT_V2: JSON_EXTENSION,
        FORMAT_BUNDLE: BUNDLE_EXTENSION,
    }.get(fmt, MERGED_EXTENSION)


def _os_version(model: str, ios_version: str) -> str:
    name = "iPadOS" if str(model or "").startswith("iPad") else "iPhoneOS"
    version = str(ios_version or "Unknown").strip() or "Unknown"
    return f"{name} {version}"


def validate_header(header, *, merged: bool = False) -> dict:
    """Validate the required v3 header fields, returning *header*."""
    if not isinstance(header, dict):
        raise PresetFormatError("Preset header must be a mapping.")
    if header.get("PresetVersion") != CURRENT_VERSION:
        raise PresetFormatError("Unsupported preset header version.")
    for key in ("GNVersion", "Device", "OSVersion"):
        value = header.get(key)
        if not isinstance(value, str) or not value.strip():
            raise PresetFormatError(f"Preset header is missing {key}.")
    if not str(header["OSVersion"]).startswith(("iPhoneOS ", "iPadOS ")):
        raise PresetFormatError("Preset header OSVersion must name iPhoneOS or iPadOS.")
    includes = {part.strip() for part in str(header.get("Includes", "")).split(",")
                if part.strip()}
    if str(CURRENT_VERSION) not in includes:
        raise PresetFormatError("Preset header must include version 3.")
    if merged and str(LEGACY_VERSION) not in includes:
        raise PresetFormatError("Merged preset header must include version 2.")
    return header


def build_header(data: dict, *, includes: str | None = None) -> dict:
    """Build the ``HEADER`` mapping for *data* from its own metadata."""
    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    version = data.get(GNUGGET_VERSION) or preset_version()
    return {
        "PresetVersion": CURRENT_VERSION,
        "GNVersion": str(version),
        "Device": str(meta.get("device_model") or "Unknown"),
        "OSVersion": _os_version(meta.get("device_model", ""), meta.get("ios_version", "")),
        "Includes": includes if includes is not None else CURRENT_VERSION,
    }


def _ordered(data: dict) -> dict:
    """Put the header (when present), metadata and tweaks first for readability."""
    order = (HEADER_KEY, "metadata", "tweaks")
    return {key: data[key] for key in order if key in data} | {
        key: value for key, value in data.items() if key not in order
    }


def _yaml_text(data: dict) -> str:
    return yaml.dump(_ordered(data), Dumper=PresetDumper, sort_keys=False,
                     allow_unicode=True, default_flow_style=False, indent=2, width=120)


def v2_data(data: dict) -> dict:
    """A plain v2 dictionary: same selections, legacy metadata version."""
    out = dict(data)
    out.pop(HEADER_KEY, None)
    for key in (*V3_KEYS, *V2_KEYS):
        out.pop(key, None)
    meta = dict(out.get("metadata") or {})
    meta["version"] = LEGACY_VERSION
    out["metadata"] = meta
    return _ordered(out)


def dumps(fmt: str, data: dict) -> str:
    """Serialize *data* into the requested textual format."""
    if fmt == FORMAT_V3:
        header = build_header(data)
        validate_header(header)
        return _yaml_text({HEADER_KEY: header, **data})
    if fmt == FORMAT_V2:
        return json.dumps(v2_data(data), ensure_ascii=False, indent=2)
    if fmt == FORMAT_MERGED:
        header = build_header(data, includes=f"{CURRENT_VERSION},{LEGACY_VERSION}")
        validate_header(header, merged=True)
        merged = {
            HEADER_KEY: header,
            V3_KEY: dumps(FORMAT_V3, data),
            V2_KEY: dumps(FORMAT_V2, data),
            MERGED_NOTE_KEY: MERGED_NOTE,
        }
        return _yaml_text(merged)
    raise ValueError(f"Unsupported preset format: {fmt}")


def _v3_data(document: dict) -> dict:
    data = {key: value for key, value in document.items() if key != HEADER_KEY}
    header = validate_header(document.get(HEADER_KEY))
    meta = dict(data.get("metadata") or {})
    # The header is authoritative about the format; old files may miss the
    # metadata version or still carry the v2 number.
    if isinstance(header, dict) and header.get("PresetVersion") == CURRENT_VERSION:
        meta["version"] = CURRENT_VERSION
    data["metadata"] = meta
    return data


def parse(text: str) -> dict:
    """Parse any textual preset representation into a preset dictionary.

    Detection is by content, so a renamed file still imports. A ZIP bundle is
    handled by :mod:`src.controllers.preset_bundle` and is rejected here.
    """
    if text.lstrip().startswith("PK"):
        raise PresetFormatError("Portable preset archives are not text presets.")
    try:
        document = yaml.load(text, Loader=PresetLoader)
    except yaml.YAMLError:
        document = None
    # A header means v3+: never fall through to the permissive v2 dictionary
    # branch with a header from an unknown or future format.
    if isinstance(document, dict) and isinstance(document.get(HEADER_KEY), dict) \
            and document[HEADER_KEY].get("PresetVersion") != CURRENT_VERSION:
        raise PresetFormatError("Unsupported preset header version.")
    # Merged: header plus one or both complete preset blocks.
    if isinstance(document, dict) and HEADER_KEY in document \
            and any(key in document for key in (*V3_KEYS, *V2_KEYS)):
        validate_header(document.get(HEADER_KEY), merged=True)
        for key in (*V3_KEYS, *V2_KEYS):
            block = document.get(key)
            if isinstance(block, str) and block.strip():
                try:
                    candidate = parse(block)
                except PresetFormatError:
                    continue
                if isinstance(candidate, dict) and isinstance(candidate.get("tweaks"), dict):
                    return candidate
        raise PresetFormatError("Merged preset has no readable version block.")
    # Raw v3 YAML with a header.
    if isinstance(document, dict) and isinstance(document.get(HEADER_KEY), dict) \
            and document[HEADER_KEY].get("PresetVersion") == CURRENT_VERSION \
            and isinstance(document.get("tweaks"), dict):
        return _v3_data(document)
    # JSON v2 (and headerless YAML dictionaries written by older tools).
    if isinstance(document, dict) and isinstance(document.get("tweaks"), dict):
        try:
            as_json = json.loads(text)
        except (ValueError, TypeError):
            pass
        else:
            if isinstance(as_json, dict) and isinstance(as_json.get("tweaks"), dict):
                return as_json
        return document
    raise PresetFormatError("Unrecognized preset file. Expected a YAML or JSON preset.")


def merged_blocks(text: str) -> tuple[str, str]:
    """Return the raw v3 and v2 blocks from a merged document."""
    try:
        document = yaml.load(text, Loader=PresetLoader)
    except yaml.YAMLError as error:
        raise PresetFormatError(str(error)) from error
    if not isinstance(document, dict) or HEADER_KEY not in document \
            or not any(key in document for key in (*V3_KEYS, *V2_KEYS)):
        raise PresetFormatError("Not a merged preset document.")
    validate_header(document.get(HEADER_KEY), merged=True)
    blocks = []
    for keys in (V3_KEYS, V2_KEYS):
        value = next((document[key] for key in keys if key in document), None)
        if not isinstance(value, str) or not value.strip():
            raise PresetFormatError("Merged preset block is missing.")
        blocks.append(value)
    return blocks[0], blocks[1]


def load(path) -> dict:
    """Read and parse a preset file (any supported textual format)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise PresetFormatError(str(error)) from error
    return parse(text)


def read_metadata(path) -> dict:
    """Read just the metadata, with no full preset parse when possible."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {}
    # JSON's metadata is a leading object: decode it without parsing the rest.
    first = re.match(r'\A\s*\{\s*"metadata"\s*:\s*', text)
    if first is not None:
        try:
            meta, end = json.JSONDecoder().raw_decode(text, first.end())
            if isinstance(meta, dict) and text[end:].lstrip().startswith((',', '}')):
                return meta
        except ValueError:
            pass
    try:
        data = parse(text)
    except PresetFormatError:
        return {}
    meta = data.get("metadata", {})
    return meta if isinstance(meta, dict) else {}
