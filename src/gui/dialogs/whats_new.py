"""What's New window shown after the app was updated to a new version.

The last version the user saw is stored in the settings store under
``whats_new/last_version``; the window appears whenever the running version
is newer. A fresh install (no stored version) starts silent — the user has
nothing to catch up on.

The window content comes from the release's section in the bundled
``NEWS.md`` (single source of truth with the shipped changelog). Without it
the short :data:`WHATS_NEW` bullets are shown.

Release media: drop images/GIFs named ``<version>-*.png|.jpg|.gif|...`` into
``src/gui/whats_new/`` (see the README there); they ship with every packaged
version and are shown under the bullets, GIFs animating.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QSize, Qt
from PySide6.QtGui import QImageReader, QMovie, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
)

from awesomeui.liquid.controls import LiquidCard
from src.gui.theme import ColorThemeManager, t, theme_pixmap
from src.gui.theme.theme_manager import connect_visible_theme
from src.utils.i18n import QT_TRANSLATE_NOOP

# Short fallback bullets when NEWS.md is unavailable.
WHATS_NEW = {
    "10.0": [
        QT_TRANSLATE_NOOP("WhatsNew", "iOS 27 support is no longer experimental, and applies no longer reboot into a mid-apply wipe."),
        QT_TRANSLATE_NOOP("WhatsNew", "Faster repeat applies with the fast backup cache (experimental)."),
        QT_TRANSLATE_NOOP("WhatsNew", "Safer applies: the backup is verified before the device is touched."),
        QT_TRANSLATE_NOOP("WhatsNew", "Mobile Helper: sign in with your Apple ID to sign and sideload IPAs."),
        QT_TRANSLATE_NOOP("WhatsNew", "New dark look with 8 accent colors, loading screens and the gold dock shimmer."),
        QT_TRANSLATE_NOOP("WhatsNew", "Fixed the empty-window crash on Windows and dead releases on older Linux distros."),
    ],
}

_GENERIC = [
    QT_TRANSLATE_NOOP("WhatsNew", "Bug fixes and improvements."),
]

_MEDIA_DIR = Path(__file__).resolve().parents[1] / "whats_new"
_MEDIA_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
_ICON_PATH = ":/icon/star-fill.svg"


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split(".") if part.isdigit())


def _news_path() -> Path:
    """The bundled NEWS.md: PyInstaller bundle root in a frozen app."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "NEWS.md"
    return Path(__file__).resolve().parents[3] / "NEWS.md"


def _plain(markdown: str) -> str:
    """Markdown emphasis/backticks stripped for the plain-text labels."""
    return markdown.replace("**", "").replace("`", "")


def _release_blocks(version: str) -> list[tuple[str, str]]:
    """The ``## <version>`` section of NEWS.md as ``(kind, text)`` blocks.

    kind: ``head`` (### section), ``bullet`` (list item) or ``text`` (any
    other non-empty line). Empty when the file or section is missing — the
    caller falls back to the short :data:`WHATS_NEW` bullets.
    """
    try:
        lines = _news_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for index, line in enumerate(lines):
        if line.strip() == f"## {version}":
            start = index + 1
            break
    else:
        return []
    blocks: list[tuple[str, str]] = []
    for line in lines[start:]:
        stripped = line.strip()
        if stripped.startswith("## "):  # the next release's section
            break
        if line.startswith((" ", "\t")) and blocks:
            # A wrapped continuation of the previous bullet/paragraph.
            kind, text = blocks[-1]
            blocks[-1] = (kind, f"{text} {stripped}")
        elif stripped.startswith("### "):
            blocks.append(("head", _plain(stripped[4:])))
        elif stripped.startswith("- "):
            blocks.append(("bullet", _plain(stripped[2:])))
        elif stripped.startswith("#"):  # the file title, not a section
            continue
        else:
            blocks.append(("text", _plain(stripped)))
    return blocks


def _media_files(version: str) -> list[Path]:
    """Every bundled image/GIF for one version, in file-name order."""
    if not _MEDIA_DIR.is_dir():
        return []
    return sorted(
        path for path in _MEDIA_DIR.iterdir()
        if path.name.startswith(version + "-")
        and path.suffix.lower() in _MEDIA_EXTS)


def _scaled_size(max_w: int, max_h: int, width: int, height: int) -> QSize:
    """Display size within the card, aspect kept."""
    if width <= 0 or height <= 0:
        return QSize(max_w, max_h // 2)  # unknown intrinsic size (a broken GIF)
    scale = min(1.0, max_w / width, max_h / height)
    return QSize(round(width * scale), round(height * scale))


def _media_label(path: Path, dpr: float, max_w: int, max_h: int):
    """One image/GIF as ``(label, display height, movie-or-None)``.

    An unreadable asset returns ``(None, 0, None)`` and is skipped — a bad
    screenshot must never block the window.
    """
    label = QLabel()
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    reader = QImageReader(str(path))
    if not reader.canRead():  # unreadable/broken asset: skip it silently
        return None, 0, None
    if path.suffix.lower() == ".gif":  # animated: QMovie, sized from the header
        display = _scaled_size(
            max_w, max_h, reader.size().width(), reader.size().height())
        movie = QMovie(str(path))
        movie.setScaledSize(display)
        label.setMovie(movie)
        label.setFixedSize(display)
        movie.start()
        return label, display.height(), movie
    pixmap = reader.read()
    if pixmap.isNull():
        return None, 0, None
    display = _scaled_size(max_w, max_h, pixmap.width(), pixmap.height())
    device = QSize(round(display.width() * dpr), round(display.height() * dpr))
    pixmap = pixmap.scaled(
        device, Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation)
    pixmap.setDevicePixelRatio(dpr)
    label.setPixmap(QPixmap.fromImage(pixmap))
    label.setFixedSize(display)
    return label, display.height(), None


class WhatsNewDialog(QDialog):
    """ConfirmationDialog's look, plus a media strip under the bullets."""

    def __init__(self, parent, version: str,
                 blocks: list[tuple[str, str]], media: list[Path]):
        super().__init__(parent)
        # Object names match ConfirmationDialog's so the same stylesheet,
        # ``t("confirmation_dialog")``, themes everything here.
        self.setObjectName("themedConfirmation")
        self.setWindowTitle(QCoreApplication.translate(
            "WhatsNew", "What's New in GoldenNugget {0}").format(version))
        self.setModal(True)
        self.setMinimumWidth(460)
        # Same size as the main window (main_app.py's resize rule for
        # MainWindow: 1000x600 minimum, 1100x760 cap, 80px screen margin).
        avail = self.screen().availableGeometry()
        self.resize(max(1000, min(1100, avail.width() - 80)),
                    max(600, min(760, avail.height() - 80)))
        self._movies: list[QMovie] = []
        self._media_labels: list[QLabel] = []
        # Card content width: window minus 24px layout margins on each side
        # and the card's own 16px padding.
        media_max_w = self.width() - 80
        media_max_h = self.height() * 45 // 100

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        header = QHBoxLayout()
        header.setSpacing(12)
        self.icon_label = QLabel(self)
        self.icon_label.setFixedSize(30, 30)
        header.addWidget(self.icon_label)
        heading = QLabel(self.windowTitle(), self)
        heading.setObjectName("confirmationTitle")
        heading.setWordWrap(True)
        heading.setTextFormat(Qt.TextFormat.PlainText)
        header.addWidget(heading, 1)
        layout.addLayout(header)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        card = LiquidCard(scroll)
        body = QVBoxLayout(card)
        body.setContentsMargins(16, 16, 16, 16)
        body.setSpacing(8)
        for kind, text in blocks:
            label = QLabel(("•  " + text) if kind == "bullet" else text, card)
            label.setObjectName(
                "confirmationSubject" if kind == "head"
                else "confirmationMessage")
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            body.addWidget(label, 0, Qt.AlignmentFlag.AlignTop)
        dpr = self.devicePixelRatioF()
        for path in media:
            label, _unused_height, movie = _media_label(
                path, dpr, media_max_w, media_max_h)
            if label is None:
                continue
            body.addWidget(label)
            self._media_labels.append(label)
            if movie is not None:
                self._movies.append(movie)
        scroll.setWidget(card)
        # The card takes the window's spare space (window is main-window
        # sized); no fixed height, so the layout never fights a resize.
        layout.addWidget(scroll, 1)

        actions = QHBoxLayout()
        actions.setSpacing(12)
        continue_btn = QPushButton(
            QCoreApplication.translate("WhatsNew", "Continue"), self)
        continue_btn.setObjectName("confirmationAction")
        continue_btn.clicked.connect(self.accept)
        continue_btn.setMinimumWidth(140)
        continue_btn.setFixedHeight(48)
        continue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        continue_btn.setDefault(True)
        continue_btn.setAutoDefault(False)
        continue_btn.setFocus()
        actions.addWidget(continue_btn, 1)
        layout.addLayout(actions)

        self._retheme()
        connect_visible_theme(self)

    def _retheme(self):
        self.setStyleSheet(t("confirmation_dialog"))
        self.icon_label.setPixmap(theme_pixmap(
            _ICON_PATH, ColorThemeManager.instance().colors.text_primary,
            28, self.devicePixelRatioF()))


def show_whats_new(parent=None, version: str | None = None) -> None:
    from src.version import App_Version

    version = version or App_Version
    blocks = _release_blocks(version)
    if not blocks:
        bullets = WHATS_NEW.get(version, _GENERIC)
        blocks = [("bullet", QCoreApplication.translate("WhatsNew", bullet))
                  for bullet in bullets]
    dialog = WhatsNewDialog(parent, version, blocks, _media_files(version))
    dialog.exec()
    dialog.deleteLater()


def maybe_show_whats_new(parent, settings, version: str | None = None) -> bool:
    """Show the window once per new version; returns True when shown."""
    from src.version import App_Version

    version = version or App_Version
    last = settings.value("whats_new/last_version", "", type=str)
    if last and _version_key(version) <= _version_key(last):
        return False
    if last:  # fresh installs start silent; only an update opens the window
        show_whats_new(parent, version)
    settings.setValue("whats_new/last_version", version)
    return bool(last)
