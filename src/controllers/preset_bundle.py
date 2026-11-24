"""Portable preset archives: JSON plus hashed template/icon assets.

``.gnpreset`` keeps the original ``manifest.json`` layout so older GoldenNugget
builds can still import it. ``.gnmpreset`` (the recommended merged export) is
a new-build archive: it keeps that v2 manifest and all assets, and adds a
``preset.gnmpreset`` YAML document holding the v3 header, the complete v3
preset, the complete v2 JSON preset and the note that v2 holds everything an
older build needs. Older builds should use the explicit Version 2 export;
they reject archives with members beyond ``manifest.json`` and ``assets/``.

Wallpapers remain excluded by the preset contract. Import never activates a
preset; assets are staged in a unique persistent directory owned by that import.
"""
import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from src.controllers.archive_safety import MAX_FILE_BYTES, checked_members

from . import preset_format as preset_files

FORMAT = 'GoldenNugget portable preset'
MERGED_FORMAT = 'GoldenNugget merged preset'
MANIFEST_NAME = 'manifest.json'
MERGED_MANIFEST_NAME = 'preset.gnmpreset'
MANIFEST_LIMIT = 4 * 1024 ** 2


def _asset_slots(data):
    for name, entry in data['tweaks'].items():
        if name == 'Templates':
            paths = entry.get('templates', [])
            for index in range(len(paths)):
                yield paths, index
        elif name == 'IconThemes':
            for theme in entry.get('themes', []):
                if theme.get('icon_path'):
                    yield theme, 'icon_path'


def export_bundle(data, destination, *, merged=False):
    data = copy.deepcopy(data)
    data['tweaks'].pop('PosterBoard', None)
    files, assets = {}, {}
    for owner, key in _asset_slots(data):
        path = Path(owner[key])
        if not path.is_file() or path.is_symlink():
            raise ValueError(f'Preset asset is missing or is a link: {path.name}')
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise ValueError(f'Preset asset is too large: {path.name}')
        # The ZIP name is generated locally; source paths never enter the bundle.
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        name = f'assets/{digest.hexdigest()}{path.suffix.lower()}'
        files[name] = path
        assets[name] = dict(sha256=digest.hexdigest(), size=size)
        owner[key] = 'bundle://' + name

    # The legacy manifest is always written so the merged archive carries the
    # same v2 selections and assets as a plain .gnpreset export. Old builds use
    # the Version 2 JSON export; their strict member check rejects the extra
    # preset.gnmpreset document.
    manifest = dict(format=FORMAT, version=1, merged=bool(merged),
                    preset=preset_files.v2_data(data), assets=assets)
    raw = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')
    if len(raw) > MANIFEST_LIMIT:
        raise ValueError('Preset metadata is too large.')
    merged_raw = None
    if merged:
        merged_raw = preset_files.dumps(preset_files.FORMAT_MERGED, data).encode('utf-8')
        if len(merged_raw) > MANIFEST_LIMIT:
            raise ValueError('Merged preset document is too large.')

    destination = Path(destination)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
            temporary = stream.name
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST_NAME, raw)
            if merged_raw is not None:
                archive.writestr(MERGED_MANIFEST_NAME, merged_raw)
            for name, path in files.items():
                digest, size = hashlib.sha256(), 0
                with path.open('rb') as src, archive.open(name, 'w') as dst:
                    for chunk in iter(lambda: src.read(1024 * 1024), b''):
                        size += len(chunk)
                        if size > MAX_FILE_BYTES:
                            raise ValueError('Preset asset grew beyond the size limit.')
                        digest.update(chunk)
                        dst.write(chunk)
                if size != assets[name]['size'] or digest.hexdigest() != assets[name]['sha256']:
                    raise ValueError(f'Preset asset changed during export: {path.name}')
            checked_members(archive)
        os.replace(temporary, destination)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def import_bundle(source, assets_base, validate):
    """Return (rewritten preset, owned asset directory); caller owns rollback."""
    owned = None
    try:
        with zipfile.ZipFile(source) as archive:
            members = checked_members(archive)
            if archive.getinfo(MANIFEST_NAME).file_size > MANIFEST_LIMIT:
                raise ValueError('Preset manifest is too large.')
            manifest = json.loads(archive.read(MANIFEST_NAME))
            if not isinstance(manifest, dict) or manifest.get('format') != FORMAT \
                    or manifest.get('version') != 1:
                raise ValueError('Unsupported portable preset format.')
            legacy_data, assets = manifest.get('preset'), manifest.get('assets')
            names = {info.filename for info in members if not info.is_dir()}

            data = legacy_data
            if MERGED_MANIFEST_NAME in names:
                if archive.getinfo(MERGED_MANIFEST_NAME).file_size > MANIFEST_LIMIT:
                    raise ValueError('Merged preset document is too large.')
                text = archive.read(MERGED_MANIFEST_NAME).decode('utf-8')
                data = preset_files.parse(text)
                # The v2 block must carry the same selections as the v3 block,
                # otherwise an older GoldenNugget would restore a different setup.
                if preset_files.v2_data(data).get('tweaks') != \
                        (legacy_data or {}).get('tweaks'):
                    raise ValueError('Merged preset versions do not match.')
            if not validate(data) or not isinstance(assets, dict):
                raise ValueError('Invalid portable preset metadata.')
            expected = {MANIFEST_NAME, *assets}
            if MERGED_MANIFEST_NAME in names:
                expected.add(MERGED_MANIFEST_NAME)
            if names != expected:
                raise ValueError('Preset contains missing or unlisted assets.')
            references = list(_asset_slots(data))
            used = set()
            for owner, key in references:
                ref = owner[key]
                if not isinstance(ref, str) or not ref.startswith('bundle://assets/'):
                    raise ValueError('Portable assets must use internal bundle references.')
                used.add(ref.removeprefix('bundle://'))
            if used != set(assets):
                raise ValueError('Preset asset references do not match its manifest.')
            os.makedirs(assets_base, exist_ok=True)
            owned = Path(tempfile.mkdtemp(prefix='import-', dir=assets_base))
            for name, metadata in assets.items():
                if not isinstance(metadata, dict) or not name.startswith('assets/') or name.count('/') != 1:
                    raise ValueError('Invalid asset record.')
                basename = name.removeprefix('assets/')
                if not re.fullmatch(r'[a-f0-9]{64}(?:\.[a-z0-9_-]+)?', basename):
                    raise ValueError('Invalid portable asset filename.')
                info = archive.getinfo(name)
                if type(metadata.get('size')) is not int or metadata['size'] != info.file_size:
                    raise ValueError('Preset asset size mismatch.')
                target = owned / name.removeprefix('assets/')
                digest = hashlib.sha256()
                with archive.open(info) as src, target.open('wb') as dst:
                    for chunk in iter(lambda: src.read(1024 * 1024), b''):
                        dst.write(chunk)
                        digest.update(chunk)
                if digest.hexdigest() != metadata.get('sha256'):
                    raise ValueError('Preset asset checksum mismatch.')
            for owner, key in references:
                owner[key] = str(owned / owner[key].removeprefix('bundle://assets/'))
            data['tweaks'].pop('PosterBoard', None)
            return data, owned
    except BaseException:
        if owned is not None:
            shutil.rmtree(owned, ignore_errors=True)
        raise
