"""Advanced error reporter: describe a problem, capture a screenshot, send to GitHub."""

from __future__ import annotations

import os
import tempfile
import time
from urllib.parse import quote

from PySide6.QtCore import QCoreApplication, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.controllers.nugget_logger import get_log_path, get_log_tail
from src.exceptions.crash_handler import _diagnostics_text, _truncate
from src.gui.theme import t

ISSUES_URL = "https://github.com/GoldensHQ/GoldenNugget/issues/new"


def _tr(text: str) -> str:
    return QCoreApplication.translate("BugReportDialog", text)


def _app_version() -> str:
    try:
        from src.version import App_Build, App_Version
        v = str(App_Version)
        b = int(App_Build)
        return f"{v} (build {b})" if b > 0 else v
    except Exception:
        return "unknown"


def build_report_body(title: str, description: str, steps: str,
                      screenshot_path: str | None) -> str:
    body = "## Bug report\n\n"
    body += f"**App version:** {_app_version()}\n\n"
    if title.strip():
        body += f"**Summary:** {title.strip()}\n\n"
    if description.strip():
        body += f"**What happened:**\n{description.strip()}\n\n"
    if steps.strip():
        body += f"**Steps to reproduce:**\n{steps.strip()}\n\n"
    if screenshot_path:
        body += (f"**Screenshot:** `{screenshot_path}` "
                 "(attach this file to the issue; it was also copied to the clipboard when captured)\n\n")
    body += ("<details><summary>Environment</summary>\n\n"
             "```\n" + _truncate(_diagnostics_text(), 8 * 1024) + "\n```\n\n</details>\n\n")
    try:
        tail = get_log_tail(48 * 1024).rstrip("\n")
    except Exception:
        tail = ""
    if tail:
        body += ("<details><summary>Session log</summary>\n\n"
                 "```\n" + _truncate(tail, 24 * 1024) + "\n```\n\n</details>\n\n")
    body += "<!-- Please attach the screenshot file if it is not visible above. -->"
    return body


def build_issues_url(title: str, body: str) -> str:
    t = title.strip() or "Bug report"
    return f"{ISSUES_URL}?title={quote(t[:120])}&body={quote(body)}"


class BugReportDialog(QDialog):
    """Collect a user report with optional window screenshot and open GitHub issue."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._screenshot: QPixmap | None = None
        self._screenshot_path: str | None = None
        self.setWindowTitle(_tr("Report a Bug"))
        self.setModal(True)
        self.resize(760, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        heading = QLabel(_tr("Advanced Error Reporter"))
        heading.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(heading)

        hint = QLabel(_tr(
            "Describe the problem, capture a screenshot of the app, then send it to GitHub. "
            "The report (environment + session log) is copied to the clipboard; attach the saved screenshot to the issue."))
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(_tr("Short summary (issue title)"))
        root.addWidget(self.title_edit)

        self.desc_edit = QPlainTextEdit()
        self.desc_edit.setPlaceholderText(_tr("What happened? What did you expect?"))
        self.desc_edit.setMinimumHeight(90)
        root.addWidget(self.desc_edit, 1)

        self.steps_edit = QPlainTextEdit()
        self.steps_edit.setPlaceholderText(_tr("Steps to reproduce (optional)"))
        self.steps_edit.setMaximumHeight(90)
        root.addWidget(self.steps_edit)

        shot_row = QHBoxLayout()
        shot_row.addWidget(QLabel(_tr("Screenshot:")))
        capture_btn = QPushButton(_tr("Capture Window"))
        capture_btn.clicked.connect(self._capture)
        shot_row.addWidget(capture_btn)
        save_btn = QPushButton(_tr("Save Screenshot…"))
        save_btn.clicked.connect(self._save_screenshot)
        shot_row.addWidget(save_btn)
        copy_img_btn = QPushButton(_tr("Copy Screenshot"))
        copy_img_btn.clicked.connect(self._copy_screenshot)
        shot_row.addWidget(copy_img_btn)
        shot_row.addStretch(1)
        root.addLayout(shot_row)

        self.preview = QLabel(_tr("No screenshot captured."))
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(160)
        self.preview.setStyleSheet("border: 1px solid palette(mid); border-radius: 8px;")
        root.addWidget(self.preview)

        self.path_label = QLabel("")
        self.path_label.setWordWrap(True)
        self.path_label.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(self.path_label)

        log_label = QLabel(_tr("Log: {0}").format(get_log_path()))
        log_label.setWordWrap(True)
        log_label.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(log_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        copy_btn = QPushButton(_tr("Copy Report"))
        copy_btn.setToolTip(_tr("Copy the full report text to the clipboard."))
        copy_btn.clicked.connect(self._copy_report)
        buttons.addWidget(copy_btn)
        send_btn = QPushButton(_tr("Report on GitHub"))
        send_btn.setToolTip(_tr("Copy the report and open a pre-filled GitHub issue in your browser."))
        send_btn.setDefault(True)
        send_btn.clicked.connect(self._send)
        buttons.addWidget(send_btn)
        close_btn = QPushButton(_tr("Close"))
        close_btn.clicked.connect(self.reject)
        buttons.addWidget(close_btn)
        root.addLayout(buttons)

        try:
            self.setStyleSheet(t("confirm_dialog") + t("summary_dialog"))
        except Exception:
            pass

    def _target_window(self):
        w = self.parentWidget()
        while w is not None and not w.isWindow():
            w = w.parentWidget()
        if w is not None and w.isWindow() and w is not self:
            return w
        active = QGuiApplication.activeWindow()
        if active is not None and active is not self and active.isWindow():
            return active
        return w if (w is not None and w is not self) else None

    def _capture(self):
        target = self._target_window()
        # Make transparent instead of hide(): hiding/showing a modal exec()
        # dialog is unstable on some platforms. Opacity reveals the app behind
        # while keeping the dialog and its event loop intact.
        prev_opacity = self.windowOpacity()
        self.setWindowOpacity(0.0)
        QCoreApplication.processEvents()
        QCoreApplication.processEvents()
        try:
            pix = QPixmap()
            if target is not None and target is not self:
                try:
                    pix = target.grab()
                except Exception:
                    pix = QPixmap()
            if pix.isNull():
                screen = (target.screen() if target is not None else None) or QGuiApplication.primaryScreen()
                if screen is not None and target is not None and target is not self:
                    try:
                        geo = target.frameGeometry()
                        pix = screen.grabWindow(0, geo.x(), geo.y(), geo.width(), geo.height())
                    except Exception:
                        pix = QPixmap()
        except Exception:
            pix = QPixmap()
        finally:
            self.setWindowOpacity(prev_opacity)
            self.raise_()
            self.activateWindow()
        if pix.isNull():
            QMessageBox.warning(self, self.windowTitle(), _tr("Could not capture the window."))
            return
        self._screenshot = pix
        self._screenshot_path = self._write_temp(pix)
        w = max(1, self.preview.width() - 4)
        h = max(1, self.preview.height() - 4)
        scaled = pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview.setPixmap(scaled)
        if self._screenshot_path:
            self.path_label.setText(_tr("Saved: {0}").format(self._screenshot_path))
        try:
            QGuiApplication.clipboard().setPixmap(pix)
        except Exception:
            pass

    def _write_temp(self, pix: QPixmap) -> str | None:
        try:
            base = os.path.join(tempfile.gettempdir(), "goldennugget_bugreport")
            os.makedirs(base, exist_ok=True)
            path = os.path.join(base, f"screenshot_{int(time.time())}.png")
            if pix.save(path, "PNG"):
                return path
        except Exception:
            return None
        return None

    def _save_screenshot(self):
        if self._screenshot is None or self._screenshot.isNull():
            QMessageBox.information(self, self.windowTitle(), _tr("Capture a screenshot first."))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, _tr("Save Screenshot"), self._screenshot_path or "screenshot.png",
            "PNG Images (*.png)")
        if not path:
            return
        if self._screenshot.save(path, "PNG"):
            self._screenshot_path = path
            self.path_label.setText(_tr("Saved: {0}").format(path))
        else:
            QMessageBox.warning(self, self.windowTitle(), _tr("Could not save the screenshot."))

    def _copy_screenshot(self):
        if self._screenshot is None or self._screenshot.isNull():
            QMessageBox.information(self, self.windowTitle(), _tr("Capture a screenshot first."))
            return
        QGuiApplication.clipboard().setPixmap(self._screenshot)

    def _build_body(self) -> str:
        return build_report_body(
            self.title_edit.text(),
            self.desc_edit.toPlainText(),
            self.steps_edit.toPlainText(),
            self._screenshot_path,
        )

    def _copy_report(self):
        QGuiApplication.clipboard().setText(self._build_body())

    def _send(self):
        body = self._build_body()
        QGuiApplication.clipboard().setText(body)
        url = build_issues_url(self.title_edit.text(), body)
        QDesktopServices.openUrl(QUrl(url))
