#!/usr/bin/env python3
"""Offline regressions for version-3 YAML presets and merged exports."""
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src' / 'qt'))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from src.controllers import preset_format as preset_files  # noqa: E402
from src.controllers.preset_bundle import (  # noqa: E402
    MANIFEST_NAME,
    MERGED_MANIFEST_NAME,
    export_bundle,
    import_bundle,
)
from src.controllers.preset_manager import PresetManager  # noqa: E402


def sample_data():
    return {
        'tweaks': {
            'RTL': {'enabled': True, 'value': {'yes': 'on', 'count': 3}},
            'SBBuildNumber': {'enabled': False},
        },
        'metadata': {
            'version': 3,
            'description': 'first line\nsecond line',
            'device_model': 'iPhone15,2',
            'ios_version': '26.2',
            'tags': ['on', 'yes'],
        },
        preset_files.GNUGGET_VERSION: '10.0-test',
    }


class TextFormats(unittest.TestCase):
    def test_v3_yaml_has_the_required_header_and_keeps_types(self):
        text = preset_files.dumps(preset_files.FORMAT_V3, sample_data())
        self.assertTrue(text.startswith('HEADER:\n'))
        for line in ('PresetVersion: 3', 'Device: iPhone15,2',
                     'OSVersion: iPhoneOS 26.2', 'Includes: 3'):
            self.assertIn(line, text)
        self.assertIn('GNVersion:', text)
        self.assertIn('10.0-test', text)
        loaded = preset_files.parse(text)
        self.assertEqual(loaded['tweaks'], sample_data()['tweaks'])
        self.assertEqual(loaded['metadata']['version'], 3)
        self.assertEqual(loaded['tweaks']['RTL']['value']['yes'], 'on')
        self.assertEqual(loaded['tweaks']['RTL']['value']['count'], 3)

    def test_v2_json_is_plain_legacy_json(self):
        text = preset_files.dumps(preset_files.FORMAT_V2, sample_data())
        self.assertEqual(text, json.dumps(json.loads(text), ensure_ascii=False, indent=2))
        self.assertNotIn('HEADER', text)
        loaded = preset_files.parse(text)
        self.assertEqual(loaded['tweaks'], sample_data()['tweaks'])
        self.assertEqual(loaded['metadata']['version'], 2)

    def test_merged_document_carries_both_complete_versions(self):
        text = preset_files.dumps(preset_files.FORMAT_MERGED, sample_data())
        self.assertIn('PresetVersion: 3', text)
        self.assertIn('Includes: 3,2', text)
        self.assertIn('Preset Version 3 (YAML): |', text)
        self.assertIn('Preset Version 2 (JSON): |', text)
        self.assertIn(preset_files.MERGED_NOTE, text)
        v3, v2 = preset_files.merged_blocks(text)
        self.assertEqual(preset_files.parse(v3)['tweaks'], sample_data()['tweaks'])
        self.assertEqual(preset_files.parse(v2)['tweaks'], sample_data()['tweaks'])
        self.assertEqual(json.loads(v2)['metadata']['version'], 2)
        self.assertEqual(preset_files.parse(text)['tweaks'], sample_data()['tweaks'])

    def test_bad_header_is_rejected(self):
        with self.assertRaises(preset_files.PresetFormatError):
            preset_files.parse('HEADER:\n  PresetVersion: 2\ntweaks: {}\n')
        with self.assertRaises(preset_files.PresetFormatError):
            preset_files.parse('HEADER:\n  PresetVersion: 3\n  GNVersion: x\n'
                               '  Device: iPhone15,2\n  OSVersion: iPadOS 26.2\n'
                               "  Includes: '3,2'\n"
                               'Preset Version 2 (JSON): |\n  {}\n')


class ManagerFormats(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pm = PresetManager.__new__(PresetManager)
        self.pm.presets_dir = str(self.root / 'presets')
        Path(self.pm.presets_dir).mkdir()
        self.pm.last_transfer_error = ''
        self.assertTrue(self.pm.save_snapshot('Demo', sample_data()))

    def test_local_preset_is_yaml_and_legacy_json_still_loads(self):
        stored = Path(self.pm.get_preset_path('Demo'))
        self.assertEqual(stored.suffix, '.yaml')
        self.assertEqual(preset_files.load(stored)['tweaks'], sample_data()['tweaks'])

        legacy = self.root / 'legacy.json'
        legacy.write_text(json.dumps({'tweaks': {'RTL': {'enabled': True}}}), encoding='utf-8')
        ok, name = self.pm.import_preset(str(legacy), 'Legacy')
        self.assertTrue(ok)
        imported = Path(self.pm.get_preset_path(name))
        self.assertEqual(imported.suffix, '.yaml')
        self.assertTrue(self.pm.load_preset(name))

    def test_export_formats_and_import_round_trip(self):
        for fmt, extension in (
            (preset_files.FORMAT_MERGED, '.gnmpreset'),
            (preset_files.FORMAT_V3, '.yaml'),
            (preset_files.FORMAT_V2, '.json'),
        ):
            with self.subTest(format=fmt):
                path = self.root / f'export-{fmt}{extension}'
                self.assertTrue(self.pm.export_preset('Demo', str(path), fmt=fmt),
                                self.pm.last_transfer_error)
                if fmt == preset_files.FORMAT_MERGED:
                    with zipfile.ZipFile(path) as archive:
                        loaded = preset_files.parse(
                            archive.read(MERGED_MANIFEST_NAME).decode('utf-8'))
                else:
                    loaded = preset_files.load(path)
                self.assertEqual(loaded['tweaks'], sample_data()['tweaks'])
                ok, name = self.pm.import_preset(str(path), f'Imported {fmt}')
                self.assertTrue(ok)
                self.assertEqual(Path(self.pm.get_preset_path(name)).suffix, '.yaml')

    def test_default_export_extension_is_merged(self):
        path = self.root / 'Default.gnmpreset'
        self.assertTrue(self.pm.export_preset('Demo', str(path)))
        self.assertEqual(path.suffix, '.gnmpreset')
        self.assertEqual(preset_files.format_for_path(path), preset_files.FORMAT_MERGED)


class PortableMerged(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.template = self.root / 'source.batter'
        self.template.write_bytes(b'example-template')
        data = sample_data()
        data['tweaks']['Templates'] = {'templates': [str(self.template)]}
        self.data = data
        self.destination = self.root / 'preset.gnmpreset'

    def test_merged_archive_keeps_assets_and_full_v2_manifest(self):
        export_bundle(self.data, self.destination, merged=True)
        with zipfile.ZipFile(self.destination) as archive:
            names = set(archive.namelist())
        self.assertIn(MANIFEST_NAME, names)
        self.assertIn(MERGED_MANIFEST_NAME, names)
        with zipfile.ZipFile(self.destination) as archive:
            manifest = json.loads(archive.read(MANIFEST_NAME))
        self.assertEqual(set(manifest['preset']['tweaks']), set(self.data['tweaks']))
        self.assertTrue(all(ref.startswith('bundle://assets/')
                            for ref in manifest['preset']['tweaks']['Templates']['templates']))
        self.assertTrue(manifest['merged'])

        self.template.unlink()
        data, owned = import_bundle(
            self.destination, self.root / 'persistent', PresetManager._valid_import_structure)
        self.assertEqual(Path(data['tweaks']['Templates']['templates'][0]).read_bytes(),
                         b'example-template')
        self.assertTrue(Path(data['tweaks']['Templates']['templates'][0]).is_relative_to(owned))


class GuiChoices(unittest.TestCase):
    def test_export_filters_and_extension_resolution(self):
        from src.gui.ios.preset_menu import (
            EXPORT_FILTERS,
            _export_choice,
            _export_filter_text,
        )

        labels = [label for label, _ in EXPORT_FILTERS]
        self.assertEqual(len(labels), 3)
        self.assertIn('Merged Export (recommended)', labels[0])
        self.assertIn('Version 3', labels[1])
        self.assertIn('Version 2 (Deprecated, not recommended)', labels[2])
        self.assertEqual(_export_filter_text(), ';;'.join(labels))

        for label, fmt in EXPORT_FILTERS:
            path, chosen = _export_choice('Preset.txt', label)
            self.assertEqual(chosen, fmt)
            self.assertEqual(Path(path).suffix, preset_files.default_extension(fmt))

        self.assertIn('*.gnmpreset', _export_filter_text())
        self.assertIn('*.yaml', _export_filter_text())


if __name__ == '__main__':
    unittest.main()
