#!/usr/bin/env python3
"""Fail a frozen build if QtWebEngine artifacts leaked into the bundle.

The app never imports QtWebEngine, but installing the full PySide6
meta-package brings in pyside6-webengine, and PyInstaller's Qt hooks collect
QML plugin trees by directory rather than by Python imports. That can drag
libQt6WebEngineCore.so (~195 MB on Linux) and its Chromium resources into a
release nobody asked for. Run this after PyInstaller:

    python tools/check_bundle_no_webengine.py [dist-dir]
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path

MARKER = "webengine"
MAX_REPORTED = 20


def parse_args(argv: Sequence[str]) -> Path:
    """Return the dist directory: explicit argument, else repo-relative dist."""
    if argv:
        return Path(argv[0])
    return Path(__file__).resolve().parents[1] / "dist"


def bundle_roots(dist: Path) -> list[Path]:
    """Both PyInstaller outputs: the loose dir and the macOS .app bundle."""
    if not dist.is_dir():
        return []
    return sorted(
        path
        for path in dist.iterdir()
        if path.is_dir() and path.name.startswith("GoldenNugget")
    )


def find_offenders(roots: Sequence[Path]) -> list[str]:
    """List files/directories whose names mention WebEngine, recursively."""
    hits: list[str] = []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            for name in [*dirnames, *filenames]:
                if MARKER in name.lower():
                    hits.append(str(Path(dirpath) / name))
    return sorted(hits)


def main(argv: Sequence[str] | None = None) -> int:
    dist = parse_args(sys.argv[1:] if argv is None else argv)
    roots = bundle_roots(dist)
    if not roots:
        print(f"[!] No GoldenNugget bundle under {dist}; nothing to check")
        return 1

    offenders = find_offenders(roots)
    if offenders:
        print("[!] QtWebEngine artifacts leaked into the frozen bundle:")
        for path in offenders[:MAX_REPORTED]:
            print(f"    {path}")
        if len(offenders) > MAX_REPORTED:
            print(f"    ... and {len(offenders) - MAX_REPORTED} more")
        return 1

    names = ", ".join(path.name for path in roots)
    print(f"[+] No QtWebEngine artifacts in {names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
