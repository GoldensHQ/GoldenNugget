"""Supervision page (not yet wired into navigation).

Surfaced as a dedicated page for the supervision-related tweak(s). This file
only defines the UI; registering it in the main window / navigation is handled
separately.
"""

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from awesomeui.liquid.controls import IOSSectionHeader, LiquidCard
from src.gui.theme import ColorThemeManager


class IOSSupervisionPage(QWidget):
    """iOS-style page for supervision controls."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setObjectName("iosContainer")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        content = QWidget()
        self._scroll.setWidget(content)
        layout.addWidget(self._scroll)

        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(16, 16, 16, 32)
        self.content_layout.setSpacing(8)

        self._intro = QLabel(
            QCoreApplication.translate(
                "Nugget",
                "Shows the device-supervision text on the Lock Screen, like the "
                "'<Device> is supervised by <org>' label seen on MDM-managed devices.",
            )
        )
        self._intro.setWordWrap(True)
        self.content_layout.addWidget(self._intro)

        self.content_layout.addWidget(
            IOSSectionHeader(QCoreApplication.translate("Nugget", "Supervision"))
        )

        self._status_card = LiquidCard()
        status_layout = QVBoxLayout(self._status_card)
        status_layout.setContentsMargins(16, 12, 16, 12)
        status_layout.setSpacing(8)

        self._status_title = QLabel(
            QCoreApplication.translate("Nugget", "Show Device Management Message")
        )
        self._status_title.setWordWrap(True)
        status_layout.addWidget(self._status_title)

        self._status_desc = QLabel(
            QCoreApplication.translate(
                "Nugget",
                "Shows the device-management message on the Lock Screen when available.",
            )
        )
        self._status_desc.setWordWrap(True)
        status_layout.addWidget(self._status_desc)

        self.content_layout.addWidget(self._status_card)
        self.content_layout.addStretch()

        self._retheme()

    def _retheme(self):
        c = ColorThemeManager.instance().colors
        self._scroll.setStyleSheet(
            f"background-color: {c.bg_primary}; border: none;"
        )
        self._intro.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 13px; background-color: transparent;"
        )
        self._status_title.setStyleSheet(
            f"color: {c.text_primary}; font-size: 15px; font-weight: 600; "
            "background-color: transparent;"
        )
        self._status_desc.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 13px; background-color: transparent;"
        )
