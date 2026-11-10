"""Design-system dialogs: icon badge + title + body + footer buttons.

Every function here is modal and returns the user's choice, so callers read like the QMessageBox / QInputDialog code
they replace. Tests monkeypatch these module-level functions instead of driving a real modal loop.
"""
from __future__ import annotations

from typing import Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget,
)

from . import icons, theme
from .i18n import tr
from .widgets import Alert, Segmented, SafeComboBox, button, field, label, tag

_TONE_ICON = {"ac": ("file", "ac_tx"), "wn": ("warn", "wn"), "er": ("err", "er"), "if": ("info", "inf"), "ok": ("ok", "ok")}


class Dialog(QDialog):
    """Header (badge + title + subtitle), a body area and a footer row of buttons."""

    def __init__(self, parent: QWidget | None, title: str, sub: str = "", tone: str = "if", icon: str = "",
                 width: int = 460) -> None:
        super().__init__(parent)
        self.setWindowTitle("ClickFlow")
        self.setModal(True)
        self.setMinimumWidth(width)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(24, 20, 24, 8)
        head.setSpacing(14)
        badge = QFrame()
        badge.setProperty("gi", tone)
        badge.setFixedSize(36, 36)
        bl = QHBoxLayout(badge)
        bl.setContentsMargins(0, 0, 0, 0)
        glyph = QLabel()
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name, tok = _TONE_ICON.get(tone, ("info", "inf"))
        glyph.setPixmap(icons.pixmap(icon or name, theme.tok(tok), 20, 2.0, 1.6))
        bl.addWidget(glyph)
        head.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.title_label = label(title, "h3", True)
        col.addWidget(self.title_label)
        self.sub_label = label(sub, "muted", True)
        self.sub_label.setVisible(bool(sub))
        col.addWidget(self.sub_label)
        head.addLayout(col, 1)
        root.addLayout(head)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(24, 6, 24, 18)
        self.body.setSpacing(12)
        root.addLayout(self.body)
        self.footer = QFrame()
        self.footer.setProperty("dlgfoot", True)
        self.foot_lay = QHBoxLayout(self.footer)
        self.foot_lay.setContentsMargins(24, 12, 24, 12)
        self.foot_lay.setSpacing(8)
        self.foot_lay.addStretch(1)
        root.addWidget(self.footer)
        self.result_key = ""

    def add_button(self, text: str, key: str, variant: str = "", icon: str = "", default: bool = False,
                   left: bool = False) -> None:
        b = button(text, icon, variant)
        b.clicked.connect(lambda: self._finish(key))
        if left:
            self.foot_lay.insertWidget(0, b)
        else:
            self.foot_lay.addWidget(b)
        if default:
            b.setDefault(True)
            b.setAutoDefault(True)

    def _finish(self, key: str) -> None:
        self.result_key = key
        self.accept() if key != "cancel" else self.reject()

    def run(self) -> str:
        """Show modally; returns the key of the clicked button ("" when closed with Esc / the window button)."""
        self.exec()
        return self.result_key


# ---------------------------------------------------------------- simple messages

def message(parent, tone: str, title: str, text: str, ok: str = "") -> None:
    d = Dialog(parent, title, "", tone)
    body = label(text, "", True)
    body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    d.body.addWidget(body)
    d.add_button(ok or tr("Close"), "ok", "primary", default=True)
    d.run()


def warn(parent, title: str, text: str) -> None:
    message(parent, "wn", title, text)


def error(parent, title: str, text: str) -> None:
    message(parent, "er", title, text)


def info(parent, title: str, text: str) -> None:
    message(parent, "if", title, text)


def confirm(parent, title: str, text: str, ok: str, danger: bool = False) -> bool:
    d = Dialog(parent, title, text, "er" if danger else "wn")
    d.add_button(tr("Cancel"), "cancel")
    d.add_button(ok, "ok", "danger" if danger else "primary", default=True)
    return d.run() == "ok"


def confirm_unsaved(parent, name: str) -> str:
    """"save" | "discard" | "cancel"."""
    d = Dialog(parent, tr("Save changes to \"{name}\"?", name=name),
               tr("If you do not save, your changes will be lost."), "wn")
    d.add_button(tr("Don't save"), "discard", "ghost", left=True)
    d.add_button(tr("Cancel"), "cancel")
    d.add_button(tr("Save"), "save", "primary", "save", default=True)
    return d.run() or "cancel"


def show_problems(parent, problems: Sequence[str]) -> None:
    d = Dialog(parent, tr("Cannot start yet"), tr("{n} thing(s) need your attention first:", n=len(problems)), "er", width=520)
    for p in problems:
        row = QFrame()
        row.setProperty("choice", True)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(12, 10, 12, 10)
        rl.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("err", theme.tok("er"), 16, 2.0))
        rl.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        lb = label(p, "", True)
        rl.addWidget(lb, 1)
        d.body.addWidget(row)
    d.add_button(tr("Close"), "ok", "primary", default=True)
    d.run()


def permission_issues(parent, issues) -> None:
    d = Dialog(parent, tr("Permission needed"), "", "if", "shield", width=520)
    for i in issues:
        d.body.addWidget(Alert(f"{i.name}: {i.message}", "info"))
    d.add_button(tr("Close"), "ok", "primary", default=True)
    d.run()


# ---------------------------------------------------------------- input

def ask_text(parent, title: str, sub: str, caption: str, default: str = "", ok: str = "",
             starts: Sequence[tuple[str, str]] = ()) -> Optional[tuple[str, str]]:
    """Single-line text prompt. Returns ``(text, start_key)`` or None when cancelled; ``starts`` adds a
    "start from" segmented choice [(key, caption), ...]."""
    d = Dialog(parent, title, sub, "ac", "file")
    edit = QLineEdit(default)
    edit.selectAll()
    d.body.addWidget(field(caption, edit))
    seg = None
    if starts:
        seg = Segmented()
        for key, text in starts:
            seg.addItem(text, key)
        d.body.addWidget(field(tr("Start from"), seg))
    d.add_button(tr("Cancel"), "cancel")
    d.add_button(ok or tr("OK"), "ok", "primary", default=True)
    edit.returnPressed.connect(lambda: d._finish("ok"))
    edit.setFocus()
    if d.run() != "ok":
        return None
    return edit.text(), (seg.currentData() if seg else "")


def choose(parent, title: str, sub: str, items: Sequence[str]) -> Optional[int]:
    d = Dialog(parent, title, sub, "ac", "display")
    combo = SafeComboBox()
    combo.addItems(list(items))
    d.body.addWidget(combo)
    d.add_button(tr("Cancel"), "cancel")
    d.add_button(tr("OK"), "ok", "primary", default=True)
    return combo.currentIndex() if d.run() == "ok" else None


def diagnosis(parent, step_name: str, text: str, has_fix: bool) -> bool:
    """Why a test found nothing. Returns True when the user asks to apply the suggested fix."""
    d = Dialog(parent, tr("Target not found"), tr("Step \"{name}\": this step would NOT click.", name=step_name), "wn", "test",
               width=540)
    box = QPlainTextEdit(text)
    box.setReadOnly(True)
    box.setMinimumHeight(110)
    d.body.addWidget(box)
    if has_fix:
        d.body.addWidget(Alert(tr("A fix is available. Apply it, then press \"Test this step\" again."), "ok"))
    d.add_button(tr("Close"), "close", "ghost", left=True)
    if has_fix:
        d.add_button(tr("Apply suggested fix"), "apply", "primary", default=True)
    return d.run() == "apply"


# ---------------------------------------------------------------- about / licenses

def about(parent, version: str, licenses: Sequence[tuple[str, str]], start_tab: int = 0) -> None:
    from .widgets import TabStrip

    d = Dialog(parent, f"ClickFlow  {version}", tr("Image-matching auto clicker"), "ac", "cursor", width=640)
    tabs = TabStrip()
    tabs.add(tr("About"))
    tabs.add(tr("Open-source licenses"))
    tabs.finish()
    d.body.addWidget(tabs)
    pages = QWidget()
    pl = QVBoxLayout(pages)
    pl.setContentsMargins(0, 0, 0, 0)
    pl.setSpacing(12)
    # about page
    about_w = QWidget()
    al = QVBoxLayout(about_w)
    al.setContentsMargins(0, 0, 0, 0)
    al.setSpacing(12)
    al.addWidget(Alert(tr("Automating clicks may violate a website's or app's terms of service and can get an account "
                          "limited or banned. Use low volume, sensible delays and a click limit, at your own risk."), "wn"))
    for txt in (tr("Press the stop hotkey (default F8) at any time."),
                tr("Click the red STOP button at the top of the screen."),
                tr("Move the mouse into any screen corner.")):
        row = QHBoxLayout()
        row.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("ok", theme.tok("ok"), 16, 2.0))
        row.addWidget(ic)
        row.addWidget(label(txt, "", True), 1)
        al.addLayout(row)
    al.addWidget(label(tr("ClickFlow is free software under the MIT License, provided as is, without warranty. It is "
                          "independent and not affiliated with any service it can be pointed at."), "hint", True))
    pl.addWidget(about_w)
    # licenses page
    lic_w = QWidget()
    ll = QVBoxLayout(lic_w)
    ll.setContentsMargins(0, 0, 0, 0)
    inner = TabStrip()
    for title, _txt in licenses:
        inner.add(title)
    inner.finish()
    ll.addWidget(inner)
    view = QPlainTextEdit()
    view.setReadOnly(True)
    view.setMinimumHeight(280)
    ll.addWidget(view)

    def show_lic(i: int) -> None:
        view.setPlainText(licenses[i][1] if 0 <= i < len(licenses) else "")

    inner.currentChanged.connect(show_lic)
    show_lic(0)
    pl.addWidget(lic_w)

    def pick(i: int) -> None:
        about_w.setVisible(i == 0)
        lic_w.setVisible(i == 1)

    tabs.currentChanged.connect(pick)
    d.body.addWidget(pages)
    pick(start_tab)
    tabs.setCurrentIndex(start_tab)
    d.add_button(tr("Close"), "ok", "primary", default=True)
    d.run()
