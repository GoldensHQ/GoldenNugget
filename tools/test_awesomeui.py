"""Offline integration regressions for the awesomeUI migration."""
import ast
import hashlib
import json
import math
import os
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QCoreApplication, QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication
from settings_sandbox import SettingsSandbox

from awesomeui import Card, Sidebar, set_widget_style, widget_style
from awesomeui.liquid import controls
from src.gui.theme import ColorThemeManager

APP = QApplication.instance() or QApplication([])


class AwesomeUIIntegration(unittest.TestCase):
    def test_library_is_standalone_and_manifest_matches(self):
        # Vendored-hash pinning (awesomeui/upstream.json) was superseded by the
        # gitlink on the submodule; what still matters is that the library is
        # standalone and never imports the host's src.* modules — except the
        # deliberate guarded host imports (try/except ImportError fallbacks).
        for path in (ROOT / 'awesomeui').rglob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            guarded = set()
            # Any host import is only allowed inside a guarded fallback block
            # (ImportError or broad Exception — e.g. the optional resources_rc).
            for node in ast.walk(tree):
                if isinstance(node, ast.Try):
                    guarded.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and (node.module or '').startswith('src.'):
                    self.assertTrue(node.lineno in guarded, path.name)
                elif isinstance(node, ast.Import) and any(
                    n.name.startswith('src.') for n in node.names
                ):
                    self.assertTrue(node.lineno in guarded, path.name)

    def test_widget_style_switch(self):
        self.assertEqual(widget_style(), 'liquid')
        self.assertIn('rgba(', Card('T').styleSheet())
        self.assertIn('rgba(', Sidebar().styleSheet())
        set_widget_style('classic')
        try:
            self.assertIn('background: #20242b', Card('T').styleSheet())
            self.assertIn('#15181e', Sidebar().styleSheet())
        finally:
            set_widget_style('liquid')
        self.assertIn('rgba(', Sidebar().styleSheet())

    def test_main_window_navigation_gating_and_live_theme(self):
        from src.devicemanagement.device_manager import DeviceManager
        from src.gui.main_window import MainWindow
        from src.gui.translator import Translator
        with tempfile.TemporaryDirectory() as directory, \
                SettingsSandbox(Path(directory)) as make_settings:
            settings = make_settings('settings')
            previous = ColorThemeManager._inst
            ColorThemeManager._inst = ColorThemeManager()
            manager = DeviceManager()
            manager.pref_manager.settings = settings
            try:
                with patch.object(MainWindow, 'refresh_devices'), \
                     patch.object(MainWindow, '_load_last_preset'), \
                     patch.object(MainWindow, '_register_tweak_autosave'), \
                     patch('src.gui.main_window.DeviceMonitorThread.start'), \
                     patch('PySide6.QtCore.QStandardPaths.writableLocation', return_value=directory):
                    window = MainWindow(manager, Translator(APP, settings))
                try:
                    window.show()
                    APP.processEvents()
                    for index in (0, 4, 12, 6, 14, 2):
                        window.set_ios_page(index, animate=False)
                        APP.processEvents()
                        self.assertEqual(window.ios_pages.currentIndex(), index)
                    # attribute first: it resolves the lazy slot deterministically
                    # (widget(14) alone races the deferred first-open build)
                    self.assertIs(window.ios_templates, window.ios_pages.widget(14))
                    self.assertEqual(window.ios_posterboard.tab_stack.count(), 3)
                    window.ios_posterboard.video_tab_btn.click()
                    self.assertIs(window.ios_posterboard.tab_stack.currentWidget(),
                                  window.ios_posterboard.video_page)
                    self.assertFalse(hasattr(window.ios_posterboard, 'templates_tab_btn'))
                    # The feature grid is 6 tiles wide (7th entry became the
                    # compact GoldenNugget Mobile row + Catalog row).
                    self.assertEqual(len(window.ios_home._tiles), 6)
                    # Templates has no home card any more; PosterBoard's does.
                    for card, index in ((window.ios_home.posterboard_card, 2),):
                        card.mousePressEvent(None)
                        APP.processEvents()
                        self.assertEqual(window.ios_pages.currentIndex(), index)
                    self.assertEqual(window.ios_nav.title_lbl.text(), 'PosterBoard')
                    import_action = window.ios_nav._right_btn
                    with patch.object(window.ios_templates, 'show_add_templates_dialog') as import_templates:
                        window._nav_right_actions[14] = ('+ Import Templates', import_templates)
                        window._update_shared_nav(14)
                        self.assertTrue(import_action.isHidden())
                        window.ios_nav._right_btn.click()
                        import_templates.assert_called_once_with()
                    window._nav_right_actions[14] = ('+ Import Templates',
                                                     window.ios_templates.show_add_templates_dialog)
                    with patch('src.gui.main_window_mixins._hidden_feature_names',
                               return_value={'PosterBoard', 'Daemons'}):
                        window._apply_hidden_feature_gating()
                    self.assertTrue(window.ios_home.posterboard_card.isHidden())
                    # The whole window re-themes from one palette.
                    ColorThemeManager.instance().set_accent('purple')
                    APP.processEvents()
                    self.assertIn(ColorThemeManager.instance().accent_hex().lower(),
                                  window.styleSheet().lower())
                    # The first-run
                    # interface picker is gone with the sidebar mode: the
                    # prompt is consumed without asking anything.
                    settings.setValue('home_widget', 'presets')
                    settings.setValue('backup_prompt_done', True)
                    settings.remove('ui/interface_choice_done')
                    with patch.object(sys, 'argv', ['GoldenNugget', '--test-mode']):
                        window.run_first_launch_prompts()
                    self.assertTrue(settings.value('ui/interface_choice_done', False, type=bool))
                    self.assertFalse(window.ios_home.apply_btn.isHidden())
                    if os.environ.get('GOLDENNUGGET_UI_SCREENSHOT'):
                        path = Path(os.environ['GOLDENNUGGET_UI_SCREENSHOT'])
                        with patch('src.gui.main_window_mixins._hidden_feature_names', return_value=set()):
                            window._apply_hidden_feature_gating()
                        window.resize(1200, 850)
                        for index, suffix in ((0, ''), (14, '-templates'), (2, '-posterboard')):
                            window.set_ios_page(index, animate=False)
                            APP.processEvents()
                            window.grab().save(str(path.with_stem(path.stem + suffix)))
                finally:
                    window.close()
                    window.deleteLater()
                    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            finally:
                ColorThemeManager._inst = previous


class CardHighlightTint(unittest.TestCase):
    """The card's specular glow keeps one weight across every accent preset."""

    @staticmethod
    def _luma(color):
        return sum(weight * channel for weight, channel in zip(
            controls._HIGHLIGHT_LUMA_WEIGHTS,
            (color.red(), color.green(), color.blue()),
        ))

    def test_every_preset_is_capped_without_losing_its_hue(self):
        from src.gui.theme.colors import ACCENT_PRESETS

        for name, (accent, _, _) in ACCENT_PRESETS.items():
            with self.subTest(accent=name):
                original = QColor(accent)
                tint = controls._highlight_tint(original)
                self.assertLessEqual(self._luma(tint), controls._HIGHLIGHT_MAX_LUMA)
                # 8-bit channel flooring can shift the hue by a degree.
                self.assertLessEqual(abs(tint.hue() - original.hue()), 2)

    def test_default_accent_keeps_its_original_tint(self):
        from src.gui.theme.colors import DARK

        original = QColor(DARK.accent)
        self.assertEqual(controls._highlight_tint(original).rgb(), original.rgb())


class SimpleGlassHighlights(unittest.TestCase):
    """Simple Glass freezes the card highlight; the animated path stays."""

    def setUp(self):
        self.app = QApplication.instance()
        self._previous = self.app.property('liquid_simple_glass')
        self.app.setProperty('liquid_simple_glass', False)

    def tearDown(self):
        self.app.setProperty('liquid_simple_glass', self._previous)

    @staticmethod
    def _move(card, x, y):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)
            event = QMouseEvent(QEvent.MouseMove, QPointF(x, y), Qt.NoButton,
                                Qt.NoButton, Qt.NoModifier)
        card.mouseMoveEvent(event)

    def test_static_mode_keeps_the_highlight_centred(self):
        self.app.setProperty('liquid_simple_glass', True)
        card = controls.LiquidCard()
        card.resize(240, 120)
        card.hover = 1.0
        self._move(card, 200, 100)
        self.assertFalse(hasattr(card, '_pointer_motion'))
        self.assertEqual(card._glass_pointer, QPointF(.5, .5))
        card._move_reflection(QPointF(.9, .9))
        self.assertEqual(card._glass_pointer, QPointF(.5, .5))

    def test_default_mode_still_follows_the_pointer(self):
        card = controls.LiquidCard()
        card.resize(240, 120)
        self._move(card, 200, 100)
        self.assertTrue(hasattr(card, '_pointer_motion'))
        card._move_reflection(QPointF(.9, .9))
        self.assertEqual(card._glass_pointer, QPointF(.9, .9))

    def test_refresh_recentres_existing_cards(self):
        card = controls.LiquidCard()
        card._glass_pointer = QPointF(.9, .9)
        controls.refresh_card_highlights()
        self.assertEqual(card._glass_pointer, QPointF(.5, .5))

    def test_entire_card_is_baked_into_the_cache(self):
        controls.clear_glass_cache()
        self.app.setProperty('liquid_simple_glass', True)
        card = controls.LiquidCard()
        card.setProperty('liquidControlCard', True)
        card.resize(240, 120)
        card.hover = 1.0
        card.grab()
        self.assertTrue(any(
            key[0][0] == 'baked_card' for key in controls._GLASS_CACHE))

        # Once baked, a repaint must not rebuild the gradients: intercept the
        # direct painter so any live painting would fail the test.
        original = controls._paint_dock_glass_uncached

        def forbidden(*args, **kwargs):
            self.fail('Simple Glass repainted gradients instead of blitting')

        controls._paint_dock_glass_uncached = forbidden
        try:
            card.grab()
        finally:
            controls._paint_dock_glass_uncached = original
            controls.clear_glass_cache()


class GlassArtCache(unittest.TestCase):
    """Static glass artwork is rendered once per shape/palette/DPR and blitted."""

    def setUp(self):
        self._previous_manager = ColorThemeManager._inst
        controls.clear_glass_cache()

    def tearDown(self):
        controls.clear_glass_cache()
        ColorThemeManager._inst = self._previous_manager

    @staticmethod
    def _render_dock(rect, dpr, cached):
        """Draw a dock glass shape into a DPR-aware image, cached or direct."""
        image = QImage(
            math.ceil((rect.right() + controls._GLASS_PAD + 2) * dpr),
            math.ceil((rect.bottom() + controls._GLASS_PAD + 2) * dpr),
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.setDevicePixelRatio(dpr)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        shape = QPainterPath()
        shape.addRoundedRect(rect, 16, 16)
        paint = controls.paint_dock_glass if cached else controls._paint_dock_glass_uncached
        paint(painter, shape)
        painter.end()
        return image

    @staticmethod
    def _mismatches(left, right):
        return sum(1 for y in range(left.height())
                   for x in range(left.width())
                   if left.pixel(x, y) != right.pixel(x, y))

    def test_cached_dock_art_is_pixel_identical_to_direct_painting(self):
        rect = QRectF(2.25, 3.75, 130.5, 60.25)
        for dpr in (1.0, 1.25, 1.5, 2.0):
            with self.subTest(dpr=dpr):
                controls.clear_glass_cache()
                direct = self._render_dock(rect, dpr, False)
                cached = self._render_dock(rect, dpr, True)
                self.assertEqual(direct.size(), cached.size())
                self.assertEqual(self._mismatches(direct, cached), 0)

    def test_cached_panel_art_matches_direct_painting(self):
        class DirectPanel(controls.GlassPanel):
            def paintEvent(self, event):
                painter = QPainter(self)
                painter.setRenderHint(QPainter.Antialiasing)
                controls._paint_panel_art(
                    painter, QRectF(self.rect()).adjusted(.5, .5, -.5, -.5))
                painter.end()

        direct, cached = DirectPanel(), controls.GlassPanel()
        for panel in (direct, cached):
            panel.resize(260, 180)
            panel.show()
        APP.processEvents()
        try:
            self.assertEqual(self._mismatches(direct.grab().toImage(),
                                              cached.grab().toImage()), 0)
        finally:
            for panel in (direct, cached):
                panel.close()
                panel.deleteLater()

    def test_repeated_paints_reuse_one_pixmap(self):
        rect = QRectF(2, 3, 100, 40)
        self._render_dock(rect, 1.0, True)
        pixmap = next(iter(controls._GLASS_CACHE.values()))[0]
        self._render_dock(rect, 1.0, True)
        self.assertEqual(len(controls._GLASS_CACHE), 1)
        self.assertIs(next(iter(controls._GLASS_CACHE.values()))[0], pixmap)

    def test_pixmap_is_rendered_at_the_painters_dpr(self):
        rect = QRectF(2, 3, 100, 40)
        for dpr in (1.0, 2.0):
            with self.subTest(dpr=dpr):
                controls.clear_glass_cache()
                self._render_dock(rect, dpr, True)
                pixmap = next(iter(controls._GLASS_CACHE.values()))[0]
                self.assertEqual(pixmap.devicePixelRatioF(), dpr)
                self.assertEqual(pixmap.width(),
                                 math.ceil((rect.width() + 2 * controls._GLASS_PAD) * dpr))

    def test_accent_change_creates_a_fresh_cache_entry(self):
        with tempfile.TemporaryDirectory() as directory, SettingsSandbox(Path(directory)):
            ColorThemeManager._inst = ColorThemeManager()
            rect = QRectF(2, 3, 100, 40)
            self._render_dock(rect, 1.0, True)
            self.assertEqual(len(controls._GLASS_CACHE), 1)
            revision = ColorThemeManager.instance().revision
            ColorThemeManager.instance().set_accent('purple')
            self.assertEqual(ColorThemeManager.instance().revision, revision + 1)
            self._render_dock(rect, 1.0, True)
            self.assertEqual(len(controls._GLASS_CACHE), 2)

    def test_cache_stays_within_its_budget(self):
        for index in range(controls._GLASS_CACHE_LIMIT + 12):
            self._render_dock(QRectF(2, 3, 100 + index, 40 + index), 1.0, True)
        self.assertLessEqual(len(controls._GLASS_CACHE), controls._GLASS_CACHE_LIMIT)
        self.assertLessEqual(controls._GLASS_CACHE_BYTES, controls._GLASS_CACHE_BUDGET)

    def test_clear_empties_pixmaps_and_accounting(self):
        self._render_dock(QRectF(2, 3, 100, 40), 1.0, True)
        self.assertGreater(controls._GLASS_CACHE_BYTES, 0)
        controls.clear_glass_cache()
        self.assertFalse(controls._GLASS_CACHE)
        self.assertEqual(controls._GLASS_CACHE_BYTES, 0)


if __name__ == '__main__':
    unittest.main()
