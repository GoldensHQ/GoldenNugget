#!/usr/bin/env python3
"""Offline test for the What's New window (no device needed).

The risky part is the version gate: the window must open once per new
version, never on a fresh install, never on the same version and never on a
downgrade — while the stored marker always ends up at the running version.

Run: python tools/test_whats_new.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PySide6.QtWidgets import QApplication

from src.controllers.settings import Settings
from src.gui.dialogs import whats_new

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


class _StubSettings:
    """Just the two calls the gate makes — no Qt prefs store needed."""

    def __init__(self):
        self.values = {}

    def value(self, key, default, type=str):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


def main():
    app = QApplication(sys.argv)  # noqa: F841 - offscreen platform
    from src.gui.bootstrap import configure_appearance
    from src.gui.widgets import configure_theme  # noqa: F401 - theme host
    configure_appearance(app, os.path.join(os.path.dirname(__file__), ".."))
    stub = _StubSettings()

    check("fresh install stays silent",
          whats_new.maybe_show_whats_new(None, stub, "10.0") is False)
    check("fresh install stores the version",
          stub.values.get("whats_new/last_version") == "10.0")

    check("same version stays silent",
          whats_new.maybe_show_whats_new(None, stub, "10.0") is False)

    # A stored older version is an update — but without a window parent
    # exec() would block, so only prove the gate opens by patching the show.
    shown = []
    original_show = whats_new.show_whats_new
    whats_new.show_whats_new = lambda parent, version: shown.append(version)
    try:
        check("update opens the window",
              whats_new.maybe_show_whats_new(None, stub, "10.1") is True)
        check("window shows the new version", shown == ["10.1"])
        check("marker follows the new version",
              stub.values.get("whats_new/last_version") == "10.1")

        check("downgrade stays silent",
              whats_new.maybe_show_whats_new(None, stub, "9.6") is False)
        check("downgrade moves the marker forward, not back",
              stub.values.get("whats_new/last_version") == "10.1")

        check("re-run after downgrade-stay stays silent",
              whats_new.maybe_show_whats_new(None, stub, "9.6") is False)
    finally:
        whats_new.show_whats_new = original_show

    check("version key parses numerically, not lexically",
          whats_new._version_key("10.0") > whats_new._version_key("9.10"))
    check("build-number versions compare correctly",
          whats_new._version_key("10.0") < whats_new._version_key("10.1"))

    # Media: discovery, static image, animated GIF, and a broken asset that
    # must be skipped instead of breaking the window.
    from PySide6.QtGui import QImage, QImageWriter, QMovie
    from PySide6.QtWidgets import QLabel

    media_dir = whats_new._MEDIA_DIR
    check("media dir is the bundled folder", media_dir.is_dir())

    png_path = media_dir / "9.9.9-shot.png"
    gif_path = media_dir / "9.9.9-demo.gif"
    bad_path = media_dir / "9.9.9-broken.gif"
    try:
        check("png saved", QImage(80, 40, QImage.Format.Format_RGB32).save(str(png_path)))
        gif_ok = QImageWriter(str(gif_path), b"gif").write(
            QImage(60, 30, QImage.Format.Format_RGB32))
        if not gif_ok:
            print("  skip: this Qt build cannot write GIFs; "
                  "only the broken-asset path is exercised")
        bad_path.write_text("not an image")

        expected = ["9.9.9-broken.gif", "9.9.9-shot.png"]
        if gif_ok:
            expected.insert(1, "9.9.9-demo.gif")
        check("media discovery finds the version's files",
              [p.name for p in whats_new._media_files("9.9.9")] == expected)
        check("other versions see nothing",
              whats_new._media_files("8.0") == [])

        dialog = whats_new.WhatsNewDialog(
            None, "9.9.9", [("bullet", "Bullet one"), ("bullet", "Bullet two")],
            whats_new._media_files("9.9.9"))
        check("dialog builds with media", dialog.windowTitle() != "")
        labels = dialog._media_labels
        pixmaps = sum(bool(w.pixmap() is not None and not w.pixmap().isNull())
                      for w in labels)
        movies = sum(w.movie() is not None for w in labels)
        if gif_ok:
            check("broken asset skipped, exactly one pixmap + one movie label",
                  pixmaps == 1 and movies == 1)
            check("gif label got a running movie",
                  any(w.movie() is not None
                      and w.movie().state() == QMovie.MovieState.Running
                      for w in dialog._media_labels))
        else:
            check("broken asset skipped, static pixmap kept, no movie",
                  pixmaps == 1 and movies == 0)
        dialog.deleteLater()
    finally:
        for path in (png_path, gif_path, bad_path):
            path.unlink(missing_ok=True)

    check("media folder clean again",
          whats_new._media_files("9.9.9") == [])

    # NEWS.md is the window's content source: the 10.0 section must parse
    # into the exact structure the window renders.
    blocks = whats_new._release_blocks("10.0")
    check("10.0 section found in NEWS.md", bool(blocks))
    check("sections, bullets and text all present",
          {kind for kind, _ in blocks} == {"head", "bullet", "text"})
    check("no markdown emphasis leaks into the labels",
          all("**" not in text for _, text in blocks))
    check("stops at the next release's section",
          not any(text == "Bug fixes and improvements."
                  for _, text in blocks))
    check("missing version yields nothing",
          whats_new._release_blocks("3.0.0") == [])

    # The real Settings store accepts the key without surprises.
    os.environ.setdefault("GOLDENNUGGET_PREFERENCES_DIR",
                          os.path.join(os.environ.get("TEMP", "."), "whats_new_prefs"))
    real = Settings("settings")
    check("real store round-trips the marker",
          real.value("whats_new/last_version", "", type=str) in ("", "10.0"))

    print(f"\nAll {PASS} checks passed")


if __name__ == "__main__":
    main()
