#!/usr/bin/env python3
"""Offline guard for the no-WebEngine bundle check (no build required).

Run: python tools/test_no_webengine_bundle.py
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from check_bundle_no_webengine import bundle_roots, find_offenders, parse_args

PASSED = 0


def check(name, cond, extra=""):
    global PASSED
    assert cond, f"FAILED: {name} {extra}"
    PASSED += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


repo_dist = Path(__file__).resolve().parents[1] / "dist"
check("default dist is repo-relative", parse_args([]) == repo_dist)
with tempfile.TemporaryDirectory() as tmp:
    dist = Path(tmp) / "dist"
    bundle = dist / "GoldenNugget" / "_internal"
    bundle.mkdir(parents=True)
    check("bundle root discovered", bundle_roots(dist) == [dist / "GoldenNugget"])
    check("clean bundle passes", find_offenders(bundle_roots(dist)) == [])

    (bundle / "libQt6WebEngineCore.so.6").touch()
    hits = find_offenders(bundle_roots(dist))
    check(
        "WebEngine library detected", any("libQt6WebEngineCore.so.6" in h for h in hits)
    )
    (bundle / "PySide6" / "Qt" / "qml" / "QtWebEngine").mkdir(parents=True)
    hits = find_offenders(bundle_roots(dist))
    check("WebEngine QML dir detected", any("QtWebEngine" in h for h in hits))

    app = dist / "GoldenNugget.app" / "Contents" / "MacOS"
    app.mkdir(parents=True)
    roots = bundle_roots(dist)
    check(
        "macOS .app discovered too", any(root.name.endswith(".app") for root in roots)
    )
    (app / "QtWebEngineProcess").touch()
    check(
        "helper process detected",
        any("QtWebEngineProcess" in h for h in find_offenders(roots)),
    )

print(f"{PASSED} checks passed")
print("ALL PASSED")
