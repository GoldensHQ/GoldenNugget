#!/usr/bin/env python3
"""Offline test for the staggered fade-in of Settings history rows.

Each row owns a ``QGraphicsOpacityEffect`` and a ``QPropertyAnimation`` whose
``start`` is deferred by a few milliseconds. A history refresh can clear the
list (and with it the effects) before those timers fire; starting an animation
whose target is gone makes Qt log ``Changing state of an animation without
target``. Refreshing must also stop and release the old animations instead of
leaking them onto the settings page.

Run: python tools/test_settings_row_fades.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PySide6.QtCore import QPropertyAnimation, qInstallMessageHandler
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QLabel,
    QListWidget,
    QListWidgetItem,
)

from src.gui.ios.settings import _cancel_row_fades, _fade_in_row

APP = QApplication.instance() or QApplication([])
PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def run_capturing(action):
    """Run ``action``, returning the Qt messages it produced."""
    messages = []

    def handler(_mode, _context, message):
        messages.append(message)

    previous = qInstallMessageHandler(handler)
    try:
        action()
        QTest.qWait(400)
    finally:
        qInstallMessageHandler(previous)
    return messages


def add_row(host, animations, delay):
    item = QListWidgetItem(host)
    label = QLabel("operation")
    host.setItemWidget(item, label)
    _fade_in_row(label, host, animations, delay)
    return label


def targetless_warnings(messages):
    return [msg for msg in messages if "without target" in msg]


def test_unsafe_start_is_detected():
    # Sanity check: the capture above really sees the warning this test guards
    # against, so the other checks can never pass vacuously.
    host = QListWidget()

    def action():
        effect = QGraphicsOpacityEffect()
        label = QLabel("operation")
        label.setGraphicsEffect(effect)
        item = QListWidgetItem(host)
        host.setItemWidget(item, label)
        anim = QPropertyAnimation(effect, b"opacity", host)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        host.clear()
        QTest.qWait(20)  # let Qt delete the row and its effect
        anim.start()

    messages = run_capturing(action)
    check("capture sees a targetless animation", bool(targetless_warnings(messages)),
          "; ".join(messages))


def test_fade_completes_when_row_survives():
    host = QListWidget()
    animations = []
    labels = []

    def action():
        labels.append(add_row(host, animations, 0))

    messages = run_capturing(action)
    check("no warning on a normal fade", not targetless_warnings(messages),
          "; ".join(messages))
    check("row ends fully opaque", labels[0].graphicsEffect().opacity() == 1.0)
    check("animation is retained until refresh", len(animations) == 1)


def test_row_removed_before_its_timer():
    host = QListWidget()

    def action():
        animations = []
        for index in range(3):
            add_row(host, animations, index * 25)
        host.clear()

    messages = run_capturing(action)
    check("cleared rows never start targetless fades",
          not targetless_warnings(messages), "; ".join(messages))


def test_refresh_cancels_pending_fades():
    host = QListWidget()

    def action():
        animations = []
        for index in range(3):
            add_row(host, animations, index * 25)
        _cancel_row_fades(animations)
        check("animations released on refresh", not animations)
        host.clear()

    messages = run_capturing(action)
    check("refresh is silent", not targetless_warnings(messages), "; ".join(messages))


def main():
    test_unsafe_start_is_detected()
    test_fade_completes_when_row_survives()
    test_row_removed_before_its_timer()
    test_refresh_cancels_pending_fades()
    print(f"\n{PASS} checks passed")


if __name__ == "__main__":
    main()
