#!/usr/bin/env python3
"""Offline regressions for main's limited, merged-only preset compatibility."""
import argparse
import contextlib
import io
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

from src.cli.cmd_preset import add_parser  # noqa: E402
from src.controllers import preset_merged_export as merged  # noqa: E402
from src.controllers.preset_manager import PresetManager  # noqa: E402
from src.gui.ios.preset_menu import (  # noqa: E402
    DEFAULT_EXPORT_EXTENSION,
    EXPORT_FILTER_JSON,
    EXPORT_FILTER_MERGED,
    EXPORT_FILTER_PORTABLE,
    EXPORT_FILTERS,
    _export_choice,
    _export_filter_text,
)
from src.version import App_Version  # noqa: E402


def sample_data():
    return {
        'tweaks': {
            'RTL': {'enabled': True, 'value': {'yes': 'on', 'count': 3}},
            'SBBuildNumber': {'enabled': False},
        },
        'metadata': {
            'version': 2,
            'description': 'first line\nsecond line',
            'device_model': 'iPhone15,2',
            'ios_version': '26.2',
            'tags': ['on', 'yes'],
        },
        'exported': True,
    }


def literal_block(text: str, key: str) -> str:
    """Return the indented body of one ``key: |-`` block."""
    lines = text.splitlines()
    start = next(index for index, line in enumerate(lines)
                 if line.startswith(f"{key}:"))
    body = []
    for line in lines[start + 1:]:
        if line.startswith('  '):
            body.append(line[2:])
        elif line.strip():
            break
    return '\n'.join(body)


class MergedWriter(unittest.TestCase):
    def test_header_and_both_complete_preset_blocks(self):
        data = sample_data()
        text = merged.dumps_merged(data)
        self.assertTrue(text.startswith(f"{merged.HEADER_KEY}:\n"))
        for needle in (
            f"PresetVersion: {merged.CURRENT_VERSION}",
            str(App_Version),
            f"Device: {data['metadata']['device_model']}",
            f"OSVersion: iPhoneOS {data['metadata']['ios_version']}",
            f"Includes: {merged.CURRENT_VERSION},{merged.LEGACY_VERSION}",
            f"{merged.V3_KEY}: |",
            f"{merged.V2_KEY}: |",
            merged.NOTE,
        ):
            self.assertIn(needle, text)

        v2 = json.loads(literal_block(text, merged.V2_KEY))
        self.assertEqual(v2['tweaks'], data['tweaks'])
        self.assertEqual(v2['metadata']['version'], merged.LEGACY_VERSION)
        self.assertNotIn(merged.HEADER_KEY, v2)

        v3 = literal_block(text, merged.V3_KEY)
        self.assertTrue(v3.startswith(f"{merged.HEADER_KEY}:\n"))
        self.assertIn(f"PresetVersion: {merged.CURRENT_VERSION}", v3)
        metadata_line = next(line for line in v3.splitlines()
                             if line.startswith('metadata: '))
        tweaks_line = next(line for line in v3.splitlines()
                           if line.startswith('tweaks: '))
        self.assertEqual(json.loads(metadata_line.split(': ', 1)[1])['version'],
                         merged.CURRENT_VERSION)
        self.assertEqual(json.loads(tweaks_line.split(': ', 1)[1]), data['tweaks'])

    def test_header_uses_ipados_for_ipads(self):
        data = sample_data()
        data['metadata']['device_model'] = 'iPad15,2'
        data['metadata']['ios_version'] = '27.0'
        header = merged.build_header(data, merged.EXTENSION)
        self.assertEqual(header['OSVersion'], 'iPadOS 27.0')

    def test_write_merged_replaces_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f"demo{merged.EXTENSION}"
            merged.write_merged(sample_data(), path)
            merged.write_merged(sample_data(), path)
            self.assertEqual(path.read_text(encoding='utf-8'),
                             merged.dumps_merged(sample_data()))


class ManagerExport(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.pm = PresetManager.__new__(PresetManager)
        self.pm.presets_dir = str(self.root / 'presets')
        Path(self.pm.presets_dir).mkdir()
        self.pm.last_transfer_error = ''
        self.data = sample_data()
        self.assertTrue(self.pm.save_snapshot('Demo', self.data))

    def test_merged_export_leaves_storage_and_other_exports_alone(self):
        stored = Path(self.pm.get_preset_path('Demo'))
        self.assertEqual(stored.suffix, '.json')
        self.assertEqual(json.loads(stored.read_text(encoding='utf-8'))['metadata']['version'],
                         2)

        merged_path = self.root / f"Demo{merged.EXTENSION}"
        self.assertTrue(self.pm.export_preset('Demo', str(merged_path)),
                        self.pm.last_transfer_error)
        self.assertEqual(json.loads(literal_block(
            merged_path.read_text(encoding='utf-8'), merged.V2_KEY))['tweaks'],
            self.data['tweaks'])

        json_path = self.root / 'Demo.json'
        self.assertTrue(self.pm.export_preset('Demo', str(json_path)),
                        self.pm.last_transfer_error)
        self.assertEqual(json.loads(json_path.read_text(encoding='utf-8'))['tweaks'],
                         self.data['tweaks'])

        portable_path = self.root / 'Demo.gnpreset'
        self.assertTrue(self.pm.export_preset('Demo', str(portable_path)),
                        self.pm.last_transfer_error)
        self.assertTrue(zipfile.is_zipfile(portable_path))

    def test_partial_export_stays_complete_in_the_v2_block(self):
        path = self.root / f"Partial{merged.EXTENSION}"
        self.assertTrue(self.pm.export_preset('Demo', str(path), include=['RTL']),
                        self.pm.last_transfer_error)
        v2 = json.loads(literal_block(path.read_text(encoding='utf-8'), merged.V2_KEY))
        self.assertEqual(set(v2['tweaks']), {'RTL'})
        self.assertTrue(v2['metadata']['partial'])


class ExportChoices(unittest.TestCase):
    def test_gui_offers_merged_first_and_normalizes_extensions(self):
        self.assertEqual(EXPORT_FILTERS[0][1], merged.EXTENSION)
        self.assertEqual(DEFAULT_EXPORT_EXTENSION, merged.EXTENSION)
        self.assertIn('Merged Export', EXPORT_FILTER_MERGED)
        self.assertEqual(_export_filter_text(), ';;'.join(label for label, _ in EXPORT_FILTERS))
        for label, extension in EXPORT_FILTERS:
            path = _export_choice('Preset.txt', label)
            self.assertEqual(Path(path).suffix, extension)
        self.assertEqual(Path(_export_choice('Preset.txt', EXPORT_FILTER_JSON)).suffix, '.json')
        self.assertEqual(Path(_export_choice('Preset.txt', EXPORT_FILTER_PORTABLE)).suffix,
                         '.gnpreset')

    def test_cli_has_a_merged_option(self):
        parser = argparse.ArgumentParser()
        add_parser(parser.add_subparsers(dest='command'))
        args = parser.parse_args(['preset', 'export', 'Demo', '--merged'])
        self.assertTrue(args.merged)
        self.assertFalse(args.portable)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            parser.parse_args(['preset', 'export', 'Demo', '--merged', '--portable'])


if __name__ == '__main__':
    unittest.main()
