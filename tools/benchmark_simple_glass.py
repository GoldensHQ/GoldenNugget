#!/usr/bin/env python3
"""Offline A/B benchmark for the experimental Simple Glass card highlight.

Run from the repository root::

    .venv/bin/python tools/benchmark_simple_glass.py

Two measurements, both with the animated (default) and static (Simple Glass)
paths on the same widgets:

* ``pointer`` -- dispatch synthetic mouse moves and let in-flight animations
  settle. The static path skips the pointer animation and the repaints it
  drives; the animated path keeps them.
* ``paint`` -- render every card directly with ``grab()``. Simple Glass blits
  one fully baked pixmap (glass, highlight, rim and inset); the animated path
  rebuilds its gradients every frame.

No device or user data is touched.
"""
import json
import os
import statistics
import sys
import time
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QEvent, QPointF, Qt, QVariantAnimation
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from awesomeui.liquid import controls

APP = QApplication.instance() or QApplication([])
warnings.filterwarnings('ignore', message='.*QMouseEvent.*')

CARD_COUNT = 24
MOVES = 400
SETTLE_SECONDS = .3
REPEATS = 3


class CountingCard(controls.LiquidCard):
    """A card that counts real paint events for the A/B comparison."""

    def __init__(self):
        super().__init__()
        self.paints = 0

    def paintEvent(self, event):
        self.paints += 1
        super().paintEvent(event)


def _make_cards():
    # Hidden widgets never run paintEvent, so the cards need a visible host.
    host = QWidget()
    host.resize(800, 600)
    host.show()
    cards = []
    for _ in range(CARD_COUNT):
        card = CountingCard()
        card.setParent(host)
        card.setProperty('liquidHomeCard', True)
        card.resize(240, 120)
        card.show()
        card.hover = 1.0
        cards.append(card)
    APP.processEvents()
    return host, cards


def _reset(cards):
    for card in cards:
        motion = getattr(card, '_pointer_motion', None)
        if motion is not None:
            motion.stop()
        card.motion.stop()
        card._glass_pointer = QPointF(.5, .5)
        card.paints = 0
        card.hover = 1.0


def _pointer_sample(cards):
    start = time.perf_counter()
    for index in range(MOVES):
        card = cards[index % len(cards)]
        point = QPointF(20 + index % 200, 10 + index % 100)
        event = QMouseEvent(QEvent.MouseMove, point, Qt.NoButton,
                            Qt.NoButton, Qt.NoModifier)
        card.mouseMoveEvent(event)
        if index % 8 == 0:
            APP.processEvents()
    # Wait only while animations are actually running: the static path exits
    # immediately instead of paying a fixed sleep on every sample.
    deadline = time.perf_counter() + SETTLE_SECONDS
    while time.perf_counter() < deadline:
        running = any(
            getattr(card, '_pointer_motion', None) is not None
            and card._pointer_motion.state() == QVariantAnimation.Running
            for card in cards
        )
        APP.processEvents()
        if not running:
            break
        time.sleep(.005)
    return (time.perf_counter() - start) * 1000


def _paint_sample(cards):
    start = time.perf_counter()
    for card in cards:
        card.grab()
    return (time.perf_counter() - start) * 1000


def _ab(cards, sample):
    results = {}
    for name, simple in (('animated', False), ('simple_glass', True)):
        APP.setProperty('liquid_simple_glass', simple)
        samples = []
        paints = []
        for _ in range(REPEATS):
            _reset(cards)
            sample(cards)  # Warm the glass-art cache before the timed pass.
            _reset(cards)
            samples.append(sample(cards))
            paints.append(sum(card.paints for card in cards))
        results[name] = {
            'median_ms': round(statistics.median(samples), 3),
            'samples_ms': [round(value, 3) for value in samples],
            'median_paints': statistics.median(paints),
        }
    return results


def main():
    previous = APP.property('liquid_simple_glass')
    try:
        host, cards = _make_cards()  # Keep the host alive: it owns the cards.
        report = {
            'cards': CARD_COUNT,
            'moves': MOVES,
            'repeats': REPEATS,
            'pointer': _ab(cards, _pointer_sample),
            'paint': _ab(cards, _paint_sample),
        }
    finally:
        APP.setProperty('liquid_simple_glass', previous)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
