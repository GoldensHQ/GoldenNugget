"""GoldenNugget's theme adapter for the shared awesomeUI controls.

Keep application settings and theme ownership here; implementations live in awesomeui.
"""
from PySide6.QtCore import QTimer

from awesomeui import configure_theme
from src.gui.theme import ColorThemeManager, t, theme_pixmap
from src.gui.theme.theme_manager import connect_visible_theme

configure_theme(manager=ColorThemeManager.instance, stylesheet=t,
                pixmap=theme_pixmap, connect=connect_visible_theme)

from awesomeui.controls import (
    IOSCard,
    IOSDangerButton,
    IOSPrimaryButton,
    IOSSearchEmpty,
    IOSSectionHeader,
    IOSSegmentedFilter,
    IOSSettingsAction,
    IOSSettingsRow,
    IOSSwitch,
    IOSValueRow,
    _auto_retheme,
)
from awesomeui.controls import (
    IOSCollapsibleSection as _CollapsibleSection,
)
from awesomeui.controls import (
    IOSNavBar as _NavBar,
)
from awesomeui.controls import (
    IOSSearchField as _SearchField,
)


class IOSSearchField(_SearchField):
    def connect_filter(self, callback):
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(100)
        timer.timeout.connect(callback)
        self.textChanged.connect(lambda: timer.start())
        self._filter_timer = timer

    def matches(self, *texts):
        if not hasattr(self, "_search_index"):
            self._search_index = {}
        key = tuple(text or "" for text in texts)
        if key not in self._search_index:
            self._search_index[key] = " ".join(key).casefold()
        query = self.text()
        if query != getattr(self, "_last_query", None):
            self._last_query = query
            self._search_words = query.casefold().split()
        return all(word in self._search_index[key] for word in self._search_words)


class IOSCollapsibleSection(_CollapsibleSection):
    def _update_header_text(self):
        chevron = self.EXPANDED_CHEVRON if self._expanded else self.COLLAPSED_CHEVRON
        self.header.setText(f"{chevron}  {self._title.replace('&', '&&')}{self._title_suffix}")


class IOSNavBar(_NavBar):
    def _clear_right(self):
        # Hide the outgoing action immediately; deferred deletion alone leaves
        # an overlapping button visible during rapid page changes.
        if self._right_btn is not None:
            self._right_btn.hide()
        super()._clear_right()


from src.gui.liquid.controls import LiquidActionButton as IOSPrimaryButton
from src.gui.liquid.controls import LiquidCard as IOSCard
from src.gui.liquid.controls import LiquidDangerButton as IOSDangerButton
from src.gui.liquid.controls import LiquidSwitch as IOSSwitch
from src.gui.liquid.navigation import LiquidNavBar as IOSNavBar
