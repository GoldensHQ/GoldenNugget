from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

from src.gui.ios.components import LiquidCard
from src.gui.theme import ColorThemeManager, theme_pixmap


class ControlGuideCard(LiquidCard):
    def __init__(self, title, description, parent=None):
        super().__init__(parent)
        self.setProperty("silentHoverAudio", True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.setMinimumHeight(136)

        root = QHBoxLayout(self)
        root.setContentsMargins(18, 13, 18, 13)
        root.setSpacing(18)

        details = QVBoxLayout()
        details.setSpacing(7)
        self.heading = QLabel(title, self)
        details.addWidget(self.heading)
        self.description = QLabel(description, self)
        self.description.setTextFormat(Qt.PlainText)
        self.description.setWordWrap(True)
        details.addWidget(self.description)

        icons = QHBoxLayout()
        icons.setSpacing(18)
        self.hints = []
        for path, text in (
            (":/icon/star.svg", self.tr("Save to Favorites")),
            (":/icon/questionmark.circle.svg", self.tr("Compatibility and cautions")),
        ):
            item = QHBoxLayout()
            item.setSpacing(7)
            icon = QLabel(self)
            icon.setFixedSize(20, 20)
            icon.setAlignment(Qt.AlignCenter)
            label = QLabel(text, self)
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            item.addWidget(icon)
            item.addWidget(label)
            icons.addLayout(item)
            self.hints.append((icon, label, path))
        icons.addStretch()
        details.addLayout(icons)
        root.addLayout(details, 1)

        self.divider = QFrame(self)
        self.divider.setFixedWidth(1)
        root.addWidget(self.divider)

        counts = QVBoxLayout()
        counts.setSpacing(8)
        counts.setAlignment(Qt.AlignVCenter)
        self.enabled_count = QLabel(self)
        self.disabled_count = QLabel(self)
        counts.addWidget(self.enabled_count)
        self.count_divider = QFrame(self)
        self.count_divider.setFixedHeight(1)
        counts.addWidget(self.count_divider)
        counts.addWidget(self.disabled_count)
        root.addLayout(counts)

        ColorThemeManager.instance().theme_changed.connect(self.retheme)
        self.set_counts(0, 0)
        self.retheme()

    def set_counts(self, enabled, total):
        self.enabled_count.setText(self.tr("Enabled: {0}").format(enabled))
        self.disabled_count.setText(self.tr("Disabled: {0}").format(total - enabled))

    def retheme(self):
        colors = ColorThemeManager.instance().colors
        self.heading.setStyleSheet(
            f"color:{colors.text_primary};font-size:16px;font-weight:650;background:transparent;")
        self.description.setStyleSheet(
            f"color:{colors.text_secondary};font-size:13px;background:transparent;")
        for icon, label, path in self.hints:
            icon.setPixmap(theme_pixmap(path, colors.text_secondary, 19, icon.devicePixelRatioF()))
            label.setStyleSheet(
                f"color:{colors.text_secondary};font-size:12px;background:transparent;")
        self.divider.setStyleSheet(f"background:{colors.divider};border:none;")
        self.count_divider.setStyleSheet(f"background:{colors.divider};border:none;")
        self.enabled_count.setStyleSheet(
            f"color:{colors.text_primary};font-size:16px;font-weight:600;background:transparent;")
        self.disabled_count.setStyleSheet(
            f"color:{colors.text_secondary};font-size:16px;font-weight:600;background:transparent;")
