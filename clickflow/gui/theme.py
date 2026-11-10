"""Design tokens (light / dark) and the application stylesheet.

The numbers come straight from the design hand-off (``clickflow.css``); each token maps 1:1 to a QSS colour.
Custom-painted widgets read colours through :func:`tok` at paint time, so one ``apply()`` re-skins everything.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPalette, QPen, QPixmap, QPolygonF
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from . import prefs

SANS = '"Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", sans-serif'
MONO = '"Cascadia Mono", Consolas, Menlo, "Microsoft YaHei UI", monospace'

TOKENS: dict[str, dict[str, str]] = {
    "light": dict(
        bg="#F6F7F8", pn="#FFFFFF", cd="#FFFFFF", fl="#FFFFFF", inp="#F1F2F4", tb="#EDEEF0",
        bd="#E1E3E7", bd2="#C9CCD3", hv="#F2F3F5", pr="#E7E9ED",
        tx="#16181D", tx2="#474B55", tx3="#5E636E", txi="#FFFFFF",
        ac="#2FB44F", ac_h="#29A247", ac_p="#238F3E", ac_tx="#1B7F37", ac_soft="#E6F6EA", on_ac="#FFFFFF", fc="#1B8A3B",
        ok="#0F7550", ok_bg="#E5F5EC", wn="#9A5700", wn_bg="#FFF3DC", er="#C62F3E", er_bg="#FDE8EA",
        inf="#4B5563", inf_bg="#EEF0F3", dg="#D1344A", on_dg="#FFFFFF", sw_off="#8D929C", sw_th="#FFFFFF", sw_on="#34C759",
        lg_i="#474B55", lg_w="#9A5700", lg_e="#C62F3E", lg_c="#0F7550", lg_m="#7A3FC4", lg_l="#6B7280",
        tp="#16181D", tpt="#FFFFFF", thumb="#1C1F26",
    ),
    "dark": dict(
        bg="#141517", pn="#1B1C1F", cd="#212327", fl="#27292E", inp="#17181B", tb="#0E0F10",
        bd="#303238", bd2="#464950", hv="#2B2D32", pr="#34363C",
        tx="#ECEDEF", tx2="#B4B7BE", tx3="#8B8F98", txi="#141517",
        ac="#30D158", ac_h="#4BDD72", ac_p="#26B84A", ac_tx="#5BE07F", ac_soft="#1B3626", on_ac="#06220F", fc="#30D158",
        ok="#3DDC97", ok_bg="#16342A", wn="#FFB84D", wn_bg="#3A2E15", er="#FF6B7A", er_bg="#3E1E25",
        inf="#A9B0BC", inf_bg="#2A2D33", dg="#FF5A6B", on_dg="#1A0509", sw_off="#555962", sw_th="#B4B7BE", sw_on="#30D158",
        lg_i="#B4B7BE", lg_w="#FFB84D", lg_e="#FF6B7A", lg_c="#3DDC97", lg_m="#B98BFF", lg_l="#9CA3AF",
        tp="#ECEDEF", tpt="#141517", thumb="#1C1F26",
    ),
}

_mode = "light"
_listeners: list[Callable[[], None]] = []


def mode() -> str:
    """The theme in force right now: ``"light"`` or ``"dark"``."""
    return _mode


def tok(name: str) -> str:
    return TOKENS[_mode][name]


def qcolor(name: str) -> QColor:
    return QColor(tok(name))


def rgba(hex_color: str, alpha: float) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{int(round(alpha * 255))})"


def on_change(fn: Callable[[], None]) -> None:
    _listeners.append(fn)


def resolve(pref: str) -> str:
    if pref in ("light", "dark"):
        return pref
    try:
        return "dark" if QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark else "light"
    except Exception:
        return "light"


# ---------------------------------------------------------------- tiny image assets referenced from QSS

def _asset_dir() -> Path:
    for base in (None,):
        try:
            d = Path(tempfile.gettempdir()) / "clickflow-ui"
            d.mkdir(parents=True, exist_ok=True)
            return d
        except OSError:
            pass
    return Path(tempfile.gettempdir())


def _arrow(path: Path, color: str, up: bool, w: int = 10, h: int = 6) -> None:
    px = QPixmap(w * 2, h * 2)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    pts = [QPointF(1, h * 2 - 1), QPointF(w, 1), QPointF(w * 2 - 1, h * 2 - 1)] if up else \
          [QPointF(1, 1), QPointF(w, h * 2 - 1), QPointF(w * 2 - 1, 1)]
    p.drawPolygon(QPolygonF(pts))
    p.end()
    px.save(str(path))


def _chevron(path: Path, color: str) -> None:
    px = QPixmap(28, 28)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 3)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawPolyline(QPolygonF([QPointF(7, 10), QPointF(14, 17), QPointF(21, 10)]))
    p.end()
    px.save(str(path))


def _check(path: Path, color: str) -> None:
    px = QPixmap(36, 36)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawPolyline(QPolygonF([QPointF(9, 18.5), QPointF(15, 24.5), QPointF(27, 11)]))
    p.end()
    px.save(str(path))


def _assets(t: dict[str, str], name: str) -> dict[str, str]:
    d = _asset_dir()
    files = {"up": d / f"{name}-up.png", "down": d / f"{name}-down.png", "chev": d / f"{name}-chev.png",
             "check": d / f"{name}-check.png"}
    _arrow(files["up"], t["tx3"], True)
    _arrow(files["down"], t["tx3"], False)
    _chevron(files["chev"], t["tx3"])
    _check(files["check"], "#FFFFFF")
    return {k: v.as_posix() for k, v in files.items()}


# ---------------------------------------------------------------- stylesheet

def build_qss(t: dict[str, str], a: dict[str, str]) -> str:
    dis = lambda c: rgba(c, 0.42)  # noqa: E731 - "disabled" = the same colour at 42 % (design: opacity .42)
    return f"""
* {{ font-family: {SANS}; font-size: 13px; color: {t['tx']}; outline: 0; }}
QMainWindow, QDialog, QWidget#root {{ background: {t['bg']}; }}
QWidget {{ background: transparent; }}
QDialog {{ background: {t['fl']}; }}
QLabel {{ background: transparent; }}
QLabel:disabled {{ color: {dis(t['tx'])}; }}
QLabel[role="muted"] {{ color: {t['tx2']}; }}
QLabel[role="hint"] {{ color: {t['tx3']}; font-size: 12px; }}
QLabel[role="field"] {{ color: {t['tx2']}; font-size: 12px; }}
QLabel[role="title"] {{ font-size: 14px; font-weight: 600; }}
QLabel[role="h1"] {{ font-size: 26px; font-weight: 700; }}
QLabel[role="h3"] {{ font-size: 16px; font-weight: 600; }}
QLabel[role="num"] {{ font-size: 28px; font-weight: 600; }}
QLabel[role="mono"] {{ font-family: {MONO}; font-size: 12px; }}
QLabel[role="count"] {{ background: {t['inp']}; border: 1px solid {t['bd']}; border-radius: 10px; padding: 0 8px;
    color: {t['tx2']}; font-size: 11px; font-weight: 600; min-height: 20px; max-height: 20px; }}
QLabel[role="kbd"] {{ background: {t['cd']}; border: 1px solid {t['bd2']}; border-radius: 6px; padding: 0 7px;
    font-family: {MONO}; font-size: 12px; font-weight: 600; min-height: 22px; max-height: 22px; }}
QLabel[tag] {{ border-radius: 10px; padding: 0 8px; font-size: 11px; font-weight: 600; min-height: 20px; max-height: 20px;
    background: {t['inp']}; color: {t['tx2']}; border: 1px solid {t['bd']}; }}
QLabel[tag="ok"] {{ background: {t['ok_bg']}; color: {t['ok']}; border-color: transparent; }}
QLabel[tag="wn"] {{ background: {t['wn_bg']}; color: {t['wn']}; border-color: transparent; }}
QLabel[tag="er"] {{ background: {t['er_bg']}; color: {t['er']}; border-color: transparent; }}
QLabel[tag="if"] {{ background: {t['inf_bg']}; color: {t['inf']}; border-color: transparent; }}
QLabel[tag="ac"] {{ background: {t['ac_soft']}; color: {t['ac_tx']}; border-color: transparent; }}

QFrame[card="true"] {{ background: {t['cd']}; border: 1px solid {t['bd']}; border-radius: 12px; }}
QFrame[card="true"] QFrame[card="true"] {{ border-radius: 10px; }}
QFrame[bare="true"] {{ background: transparent; border: 0; }}
QFrame#topbar {{ background: {t['pn']}; border: 0; border-bottom: 1px solid {t['bd']}; }}
QFrame#dock {{ background: {t['pn']}; border: 0; border-top: 1px solid {t['bd']}; }}
QFrame#logdrawer {{ background: {t['pn']}; border: 0; border-top: 1px solid {t['bd']}; }}
QFrame[alert] {{ border-radius: 10px; border: 0; }}
QFrame[alert="info"] {{ background: {t['inf_bg']}; }}
QFrame[alert="ok"] {{ background: {t['ok_bg']}; }}
QFrame[alert="wn"] {{ background: {t['wn_bg']}; }}
QFrame[alert="er"] {{ background: {t['er_bg']}; }}
QFrame[seg="true"] {{ background: {t['inp']}; border: 1px solid {t['bd']}; border-radius: 9px; }}
QFrame[sep="true"] {{ background: {t['bd']}; border: 0; max-height: 1px; min-height: 1px; }}
QFrame[tile="true"] {{ background: {t['cd']}; border: 1px solid {t['bd']}; border-radius: 12px; }}
QFrame[dlgfoot="true"] {{ background: {t['pn']}; border: 0; border-top: 1px solid {t['bd']}; }}
QFrame[choice="true"] {{ background: {t['cd']}; border: 1px solid {t['bd']}; border-radius: 10px; }}
QFrame[choice="true"][on="true"] {{ background: {t['ac_soft']}; border: 1px solid {t['fc']}; }}
QFrame[hero="true"] {{ background: {t['cd']}; border: 1px solid {t['bd']}; border-radius: 14px; }}
QFrame[gi] {{ border: 0; border-radius: 10px; }}
QFrame[gi="ac"] {{ background: {t['ac_soft']}; }}
QFrame[gi="wn"] {{ background: {t['wn_bg']}; }}
QFrame[gi="er"] {{ background: {t['er_bg']}; }}
QFrame[gi="if"] {{ background: {t['inf_bg']}; }}
QFrame[gi="ok"] {{ background: {t['ok_bg']}; }}
QFrame[stepno="true"] {{ background: {t['ac_soft']}; border: 0; border-radius: 10px; }}

QPushButton, QToolButton[btn="true"] {{ min-height: 30px; max-height: 30px; padding: 0 14px; border-radius: 8px;
    border: 1px solid {t['bd2']}; background: {t['cd']}; color: {t['tx']}; font-weight: 600; }}
QPushButton:hover, QToolButton[btn="true"]:hover {{ background: {t['hv']}; }}
QPushButton:pressed, QToolButton[btn="true"]:pressed {{ background: {t['pr']}; }}
QPushButton:focus, QToolButton[btn="true"]:focus {{ border: 2px solid {t['fc']}; padding: 0 13px; }}
QPushButton:disabled, QToolButton[btn="true"]:disabled {{ color: {dis(t['tx'])}; border-color: {rgba(t['bd2'], .5)};
    background: {t['cd']}; }}
QPushButton[variant="primary"], QToolButton[variant="primary"] {{ background: {t['ac']}; border: 1px solid transparent;
    color: {t['on_ac']}; }}
QPushButton[variant="primary"]:hover, QToolButton[variant="primary"]:hover {{ background: {t['ac_h']}; }}
QPushButton[variant="primary"]:pressed, QToolButton[variant="primary"]:pressed {{ background: {t['ac_p']}; }}
QPushButton[variant="primary"]:disabled, QToolButton[variant="primary"]:disabled {{ background: {rgba(t['ac'], .4)};
    color: {rgba(t['on_ac'], .5)}; border-color: transparent; }}
QPushButton[variant="danger"], QToolButton[variant="danger"] {{ background: {t['dg']}; border: 1px solid transparent;
    color: {t['on_dg']}; }}
QPushButton[variant="danger"]:hover, QToolButton[variant="danger"]:hover {{ background: {rgba(t['dg'], .88)}; }}
QPushButton[variant="danger"]:pressed {{ background: {rgba(t['dg'], .75)}; }}
QPushButton[variant="ghost"], QToolButton[variant="ghost"] {{ background: transparent; border: 1px solid transparent;
    color: {t['tx2']}; }}
QPushButton[variant="ghost"]:hover, QToolButton[variant="ghost"]:hover {{ background: {t['hv']}; color: {t['tx']}; }}
QPushButton[variant="ghost"]:pressed, QToolButton[variant="ghost"]:pressed {{ background: {t['pr']}; }}
QPushButton[variant="link"] {{ background: transparent; border: 0; color: {t['ac_tx']}; padding: 0 6px; }}
QPushButton[variant="link"]:hover {{ background: transparent; text-decoration: underline; }}
QPushButton[add="true"] {{ min-height: 44px; max-height: 44px; border: 1.5px dashed {t['ac_tx']}; color: {t['ac_tx']};
    background: {t['ac_soft']}; border-radius: 10px; }}
QPushButton[add="true"]:hover {{ background: {t['hv']}; }}
QPushButton[add="true"]:disabled {{ color: {t['tx3']}; border-color: {t['bd2']}; background: transparent; }}
QPushButton[size="lg"], QToolButton[size="lg"] {{ min-height: 38px; max-height: 38px; padding: 0 20px; font-size: 14px;
    border-radius: 10px; }}
QPushButton[size="sm"], QToolButton[size="sm"] {{ min-height: 26px; max-height: 26px; padding: 0 10px; font-size: 12px;
    border-radius: 7px; }}
QToolButton[icononly="true"] {{ padding: 0; min-width: 30px; max-width: 30px; }}
QToolButton[icononly="true"][size="sm"] {{ min-width: 26px; max-width: 26px; }}
QToolButton[btn="true"][variant="ghost"][icononly="true"] {{ border: 1px solid transparent; }}

QToolButton[seg="true"] {{ min-height: 26px; max-height: 26px; padding: 0 12px; border: 1px solid transparent;
    border-radius: 7px; background: transparent; color: {t['tx2']}; font-weight: 600; font-size: 12px; }}
QToolButton[seg="true"]:hover {{ color: {t['tx']}; }}
QToolButton[seg="true"]:checked {{ background: {t['fl']}; color: {t['tx']}; border: 1px solid {t['bd2']}; }}
QToolButton[seg="true"]:disabled {{ color: {dis(t['tx'])}; }}
QToolButton[tab="true"] {{ min-height: 34px; max-height: 34px; padding: 0 14px; border: 0; border-bottom: 2px solid transparent;
    background: transparent; color: {t['tx2']}; font-weight: 600; border-radius: 0; }}
QToolButton[tab="true"]:hover {{ color: {t['tx']}; }}
QToolButton[tab="true"]:checked {{ color: {t['ac_tx']}; border-bottom: 2px solid {t['ac_tx']}; }}
QToolButton[grouphead="true"] {{ border: 0; background: transparent; font-weight: 600; font-size: 13px; text-align: left;
    padding: 0 6px; min-height: 40px; max-height: 40px; border-radius: 8px; }}
QToolButton[grouphead="true"]:hover {{ background: {t['hv']}; }}
QToolButton[chip="true"] {{ border: 0; background: transparent; padding: 4px; border-radius: 8px; }}
QToolButton[chip="true"]:hover {{ background: {t['hv']}; }}
QToolButton[chip="true"]:disabled {{ background: transparent; }}
QToolButton[topbtn="true"] {{ min-height: 32px; max-height: 32px; padding: 0 10px; border: 1px solid transparent;
    background: transparent; color: {t['tx2']}; border-radius: 8px; font-weight: 600; }}
QToolButton[topbtn="true"]:hover {{ background: {t['hv']}; color: {t['tx']}; }}
QToolButton[topbtn="true"]:pressed {{ background: {t['pr']}; }}
QToolButton[profile="true"] {{ min-height: 32px; max-height: 32px; padding: 0 10px 0 8px; border: 1px solid {t['bd2']};
    border-radius: 9px; background: {t['cd']}; font-weight: 600; text-align: left; }}
QToolButton[profile="true"]:hover {{ background: {t['hv']}; }}
QToolButton[profile="true"]::menu-indicator {{ image: none; width: 0; }}
QToolButton[logtoggle="true"] {{ border: 0; background: transparent; font-weight: 600; font-size: 12px; color: {t['tx2']};
    padding: 0 6px; min-height: 28px; max-height: 28px; border-radius: 7px; }}
QToolButton[logtoggle="true"]:hover {{ background: {t['hv']}; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background: {t['inp']}; border: 1px solid {t['bd2']}; border-radius: 8px;
    min-height: 30px; padding: 0 10px; selection-background-color: {t['ac']}; selection-color: {t['on_ac']}; }}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{ border-color: {t['tx3']}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 2px solid {t['fc']}; padding: 0 9px; }}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{ background: {t['bg']};
    color: {dis(t['tx'])}; border-color: {rgba(t['bd2'], .5)}; }}
QLineEdit[hotkey="true"] {{ font-family: {MONO}; font-weight: 600; }}
QSpinBox, QDoubleSpinBox {{ padding-right: 24px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right;
    width: 20px; border: 0; background: transparent; margin: 2px 2px 0 0; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right;
    width: 20px; border: 0; background: transparent; margin: 0 2px 2px 0; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({a['up']}); width: 9px; height: 5px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({a['down']}); width: 9px; height: 5px; }}
QComboBox {{ padding-right: 26px; }}
QComboBox::drop-down {{ subcontrol-origin: border; subcontrol-position: center right; width: 26px; border: 0; }}
QComboBox::down-arrow {{ image: url({a['chev']}); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{ background: {t['fl']}; border: 1px solid {t['bd']}; border-radius: 8px; padding: 4px;
    selection-background-color: {t['hv']}; selection-color: {t['tx']}; outline: 0; }}
QComboBox QAbstractItemView::item {{ min-height: 28px; padding: 0 8px; border-radius: 6px; }}

QPlainTextEdit, QTextEdit {{ background: {t['inp']}; border: 1px solid {t['bd2']}; border-radius: 8px; padding: 6px 8px;
    selection-background-color: {t['ac']}; selection-color: {t['on_ac']}; }}
QPlainTextEdit:focus {{ border: 2px solid {t['fc']}; padding: 5px 7px; }}
QPlainTextEdit[role="log"] {{ background: {t['inp']}; border: 0; border-top: 1px solid {t['bd']}; border-radius: 0;
    font-family: {MONO}; font-size: 12px; padding: 8px 16px; }}

QCheckBox {{ spacing: 10px; color: {t['tx']}; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1.5px solid {t['tx3']}; background: transparent; }}
QCheckBox::indicator:hover {{ border-color: {t['tx']}; }}
QCheckBox::indicator:checked {{ background: {t['sw_on']}; border-color: {t['sw_on']}; image: url({a['check']}); }}
QCheckBox::indicator:disabled {{ border-color: {dis(t['tx3'])}; }}
QCheckBox:disabled {{ color: {dis(t['tx'])}; }}
QRadioButton::indicator {{ width: 18px; height: 18px; border-radius: 9px; border: 1.5px solid {t['tx3']}; }}
QRadioButton::indicator:checked {{ border: 5px solid {t['ac']}; background: {t['on_ac']}; }}

QSlider::groove:horizontal {{ height: 4px; border-radius: 2px; background: {t['bd2']}; margin: 0; }}
QSlider::add-page:horizontal {{ background: {t['bd2']}; border-radius: 2px; height: 4px; }}
QSlider::sub-page:horizontal {{ background: {t['ac']}; border-radius: 2px; height: 4px; }}
QSlider::handle:horizontal {{ width: 14px; height: 14px; margin: -7px 0; border-radius: 9px; background: {t['cd']};
    border: 2px solid {t['fc']}; }}
QSlider::handle:horizontal:hover {{ background: {t['ac_soft']}; }}
QSlider::sub-page:horizontal:disabled {{ background: {t['tx3']}; }}
QSlider::handle:horizontal:disabled {{ border-color: {t['tx3']}; background: {t['cd']}; }}
QProgressBar {{ height: 6px; max-height: 6px; border-radius: 3px; background: {t['inp']}; border: 1px solid {t['bd']}; text-align: center; }}
QProgressBar::chunk {{ background: {t['ac']}; border-radius: 3px; }}

QScrollArea {{ border: 0; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t['bd2']}; border-radius: 3px; min-height: 28px; margin: 0 2px; }}
QScrollBar::handle:vertical:hover {{ background: {t['tx3']}; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t['bd2']}; border-radius: 3px; min-width: 28px; margin: 2px 0; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: 0; background: transparent; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QListWidget#steps {{ background: transparent; border: 0; padding: 0; }}
QToolTip {{ background: {t['tp']}; color: {t['tpt']}; border: 0; border-radius: 6px; padding: 6px 10px; font-size: 12px; }}
QMenu {{ background: {t['fl']}; border: 1px solid {t['bd']}; border-radius: 12px; padding: 6px; }}
QMenu::item {{ padding: 7px 28px 7px 12px; border-radius: 7px; margin: 1px 0; color: {t['tx']}; }}
QMenu::item:selected {{ background: {t['hv']}; }}
QMenu::item:disabled {{ color: {t['tx3']}; }}
QMenu::separator {{ height: 1px; background: {t['bd']}; margin: 4px 6px; }}
QSplitter::handle {{ background: transparent; }}
QMessageBox {{ background: {t['fl']}; }}
QStatusBar {{ background: {t['pn']}; color: {t['tx3']}; }}
"""


def _palette(t: dict[str, str]) -> QPalette:
    p = QPalette()
    role = QPalette.ColorRole
    for r, c in ((role.Window, t["bg"]), (role.WindowText, t["tx"]), (role.Base, t["inp"]), (role.AlternateBase, t["cd"]),
                 (role.Text, t["tx"]), (role.Button, t["cd"]), (role.ButtonText, t["tx"]), (role.Highlight, t["ac"]),
                 (role.HighlightedText, t["on_ac"]), (role.ToolTipBase, t["tp"]), (role.ToolTipText, t["tpt"]),
                 (role.PlaceholderText, t["tx3"]), (role.Link, t["ac_tx"]), (role.BrightText, t["tx"])):
        p.setColor(r, QColor(c))
    for r in (role.WindowText, role.Text, role.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, r, QColor(t["tx3"]))
    return p


def apply(app: QApplication | None = None, pref: str | None = None) -> str:
    """(Re)apply the theme to the whole application. ``pref`` is ``"auto" | "light" | "dark"`` (default: saved one)."""
    global _mode
    app = app or QApplication.instance()
    pref = pref or prefs.get("theme")
    _mode = resolve(pref)
    t = TOKENS[_mode]
    if app is not None:
        app.setStyle("Fusion")  # QSS draws on top of a predictable base on every OS
        app.setPalette(_palette(t))
        app.setStyleSheet(build_qss(t, _assets(t, _mode)))
    for fn in list(_listeners):
        try:
            fn()
        except Exception:
            pass
    return _mode


def set_pref(pref: str) -> str:
    prefs.set("theme", pref)
    return apply(pref=pref)


def toggle() -> str:
    """Flip between light and dark (leaves 'auto' for an explicit choice)."""
    return set_pref("light" if _mode == "dark" else "dark")
