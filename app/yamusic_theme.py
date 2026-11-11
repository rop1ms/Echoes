# yamusic_theme.py
"""
Тема «Echoes Music» — интерфейс в духе Яндекс Музыки (полная тема, как Winamp).

Силуэт:
  ┌──────────┬──────────────────────────────────────────────┐
  │ ECHOES   │  ┌ контент (скруглённая панель) ────────────┐ │
  │ Поиск    │  │  страницы: Поиск · Моя волна · Для вас · │ │
  │ Моя волна│  │  Коллекция · Плейлист · Исполнитель ·    │ │
  │ Для вас  │  │  Текст · Настройки                       │ │
  │ Коллекция│  └──────────────────────────────────────────┘ │
  │ Настройки│                                               │
  │ плейлисты│                                               │
  │ профиль  │  ┌ плеер: обложка · кнопки · текст/очередь ┐ │
  └──────────┴──────────────────────────────────────────────┘

Оболочка (YaShell) собрана из НОВЫХ виджетов и общается с MainWindow
только через его методы (_play_index, toggle_play, next_track…), поэтому
обычная раскладка плеера при этой теме просто спрятана и возвращается
без изменений. Единственное, что переезжает, — правая панель настроек
(эквалайзер, пресеты, таймеры, темы): она живёт на странице «Настройки».
"""
from __future__ import annotations

import data_home
import math
import random
import time
from pathlib import Path

from frameclock import FrameTimer
from img_load import load_pixmap, read_image
from PyQt6.QtCore import (Qt, QTimer, QSize, QRectF, QPointF, QRect, QPoint, pyqtSignal,
                          QAbstractListModel, QModelIndex, QEvent, QVariantAnimation, QEasingCurve,
                          QItemSelectionModel)
from PyQt6.QtGui import (QColor, QFont, QPainter, QPainterPath, QPixmap, QIcon, QPen,
                         QLinearGradient, QRadialGradient, QImage, QFontMetrics, QBrush, QCursor, QTransform)
from PyQt6.QtWidgets import (QWidget, QFrame, QLayout, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QStackedWidget, QScrollArea, QListView, QStyledItemDelegate, QStyle,
                             QLineEdit, QSlider, QMenu, QListWidget, QListWidgetItem,
                             QSizePolicy, QAbstractItemView, QButtonGroup, QGridLayout, QComboBox,
                             QMessageBox, QCheckBox, QAbstractButton, QApplication)

try:
    from lyrics import sanitize_title
except Exception:                                  # noqa: BLE001
    def sanitize_title(t):
        return t or ""

YELLOW = "#ffdb1a"
BG = "#000000"
PANEL = "#121212"
PANEL2 = "#1a1a1a"
CARD = "#232323"
TEXT = "#ffffff"
MUTED = "#8a8a8a"
LIKED = "Мне нравится"
WAVE_PL = "\u2063wave"
ALBUM_PL = "\u2063album"             # временная очередь, не сохраняется в плейлисты
AUTO_PLAYLISTS = {WAVE_PL, ALBUM_PL}
_NO_ALBUM = {"", "unknown", "unknown album", "неизвестный альбом", "<unknown>", "none", "null",
             "youtube", "soundcloud", "single"}
# «ECHOES Symbols» — последним: значки интерфейса (U+F1000…) берутся из него, а не из системной подстановки
# Windows, которая рисовала вместо трофея квадратик
FAMILIES = ["YS Text", "Inter", "Segoe UI Variable Display", "Segoe UI", "Helvetica Neue", "Arial", "ECHOES Symbols"]
TITLE_FAMILIES: list = []           # шрифт заголовков и логотипа (ya_skin «Шрифт заголовков»); пусто — как текст
DENSITY = 1.0                       # размер карточек: просторно 1.15 / обычно 1 / компактно 0.86 (ya_skin)
CARD_RADIUS = 10                    # скругление обложек альбомов, px при 150 px (0 — квадрат, 75 — круг)
ARTIST_ROUND = True                 # исполнители — круглые (иначе как альбомы)


def ya_font(px: int, weight=QFont.Weight.Normal) -> QFont:
    f = QFont()
    f.setFamilies(FAMILIES)
    f.setPixelSize(int(px))
    f.setWeight(weight)
    return f


# ══════════════════════════════════════════════════════════════════════════ #
#  Тема: словарь цветов + QSS
# ══════════════════════════════════════════════════════════════════════════ #

def ya_theme_dict() -> dict:
    return {
        "bg": BG, "panel": PANEL, "panel2": PANEL2,
        "glass": "rgba(255,255,255,0.05)", "glass2": "rgba(255,255,255,0.09)",
        "text": TEXT, "muted": MUTED, "accent": YELLOW, "accent2": "#ff4fa3",
        "border": "rgba(255,255,255,0.08)", "border2": "rgba(255,255,255,0.16)",
        "danger": "#ff5c5c", "glow": "#000000", "yamusic": True,
    }


def _ui_assets() -> dict:
    """PNG для QSS: тумблер (выкл/вкл) вместо квадратной галочки и стрелка выпадающего списка."""
    d = data_home.root() / "ui_cache"
    out = {k: d / f"{k}.png" for k in ("sw_off", "sw_on", "arrow")}
    if all(p.exists() for p in out.values()) and (d / "v2").exists():
        return {k: p.as_posix() for k, p in out.items()}
    try:
        d.mkdir(parents=True, exist_ok=True)
        W, H, S = 46, 26, 4                                   # рисуем в 4× и сжимаем — гладкие края
        for key, on in (("sw_off", False), ("sw_on", True)):
            pm = QPixmap(W * S, H * S)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            track = QPainterPath()
            track.addRoundedRect(QRectF(0, 0, W * S, H * S), H * S / 2, H * S / 2)
            p.fillPath(track, QColor(YELLOW) if on else QColor(72, 72, 72))
            r = (H - 8) * S
            x = (W - 4) * S - r if on else 4 * S
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0) if on else QColor(236, 236, 236))
            p.drawEllipse(QRectF(x, 4 * S, r, r))
            p.end()
            pm.scaled(W, H, Qt.AspectRatioMode.IgnoreAspectRatio,
                      Qt.TransformationMode.SmoothTransformation).save(str(out[key]))
        pm = QPixmap(12 * S, 8 * S)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#bdbdbd"), 1.8 * S, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        p.drawLine(QPointF(1.5 * S, 1.8 * S), QPointF(6 * S, 6.2 * S))
        p.drawLine(QPointF(6 * S, 6.2 * S), QPointF(10.5 * S, 1.8 * S))
        p.end()
        pm.scaled(12, 8, Qt.AspectRatioMode.IgnoreAspectRatio,
                  Qt.TransformationMode.SmoothTransformation).save(str(out["arrow"]))
        (d / "v2").write_text("1")
    except Exception as e:                                    # noqa: BLE001
        print("[ya] ui assets:", e)
    return {k: p.as_posix() for k, p in out.items()}


def _rgba(c: str, a: float) -> str:
    q = QColor(c)
    return f"rgba({q.red()},{q.green()},{q.blue()},{a})"


def ya_qss(t: dict) -> str:
    A = _ui_assets()
    from echo_glass import glass_controls_qss
    return f"""
    QWidget {{ color:{TEXT}; font-family:"YS Text","Inter","Segoe UI","ECHOES Symbols"; font-size:13px; }}
    QMainWindow, QWidget#Root {{ background:{BG}; }}
    QDialog, QMenu {{ background:{PANEL2}; color:{TEXT}; }}
    QMenu {{ border:1px solid #2c2c2c; border-radius:10px; padding:6px; }}
    QMenu::item {{ padding:7px 18px; border-radius:6px; }}
    QMenu::item:selected {{ background:#2c2c2c; }}
    QMenu::section {{ color:{MUTED}; font-size:11px; padding:6px 12px; }}
    QToolTip {{ background:#2a2a2a; color:#fff; border:none; padding:5px 8px; border-radius:6px; }}
    QFrame#YaContent {{ background:{PANEL}; border-radius:22px; }}
    QFrame#YaPlayer {{ background:{PANEL2}; border:1px solid #252527; border-radius:18px; }}
    QWidget#YaSide, QWidget#YaPage, QWidget#YaPageInner {{ background:transparent; }}
    QLabel {{ background:transparent; }}
    QLabel#YaH1 {{ font-size:28px; font-weight:800; }}
    QLabel#YaH2 {{ font-size:20px; font-weight:800; }}
    QLabel#YaSub, QLabel#Sub {{ color:{MUTED}; font-size:12px; }}
    QLabel#Section {{ color:{MUTED}; font-size:11px; font-weight:700; letter-spacing:1px; }}
    QLabel#Big {{ font-size:15px; font-weight:700; }}
    QPushButton {{ background:#262626; color:{TEXT}; border:none; border-radius:13px;
                   padding:9px 16px; font-weight:600; }}
    QPushButton:hover {{ background:#303030; }}
    QPushButton:pressed {{ background:#3a3a3a; }}
    QPushButton:checked {{ background:#3a3a3a; }}
    QPushButton:disabled {{ color:#555; }}
    QPushButton#AccentBtn, QPushButton#YaYellow {{ background:{YELLOW}; color:#000; }}
    QPushButton#AccentBtn:hover, QPushButton#YaYellow:hover {{ background:#ffe55c; }}
    QPushButton#GhostBtn {{ background:transparent; border:1px solid #333; }}
    QPushButton#GhostBtn:hover {{ border-color:#555; }}
    QPushButton#YaNav {{ background:transparent; text-align:left; padding:9px 12px; border-radius:10px;
                         font-size:13px; font-weight:600; color:#c6c6ca; }}
    QPushButton#YaNav:hover {{ background:#141414; color:#fff; }}
    QFrame#YaTopBar, QFrame#YaSideNav, QFrame#YaCornerBox {{ background:transparent; border-radius:18px; }}
    QLabel#YaSideHead {{ color:#7a7a80; font-size:10px; font-weight:800; letter-spacing:1.5px; padding:2px 12px 6px 12px;
                         background:transparent; }}
    QPushButton#YaTopTile {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {_rgba(YELLOW, 0.30)},
                                                        stop:1 {_rgba(YELLOW, 0.08)});
                             border-radius:10px; border:1px solid rgba(255,255,255,0.10); }}
    QPushButton#YaTopTile:hover {{ border:1px solid {YELLOW}; }}
    QPushButton#YaTopTile:checked {{ border:2px solid {YELLOW}; }}
    QPushButton#YaTopRound {{ background:rgba(255,255,255,0.06); border-radius:22px;
                              border:1px solid rgba(255,255,255,0.10); }}
    QPushButton#YaTopRound:hover {{ background:rgba(255,255,255,0.12); }}
    QPushButton#YaTopRound:checked {{ border:2px solid {YELLOW}; }}
    QPushButton#YaPlTile {{ background:transparent; border-radius:10px; border:1px solid rgba(255,255,255,0.06);
                            padding:0; }}
    QPushButton#YaPlTile:hover {{ border:1px solid {YELLOW}; }}
    QPushButton#YaPlMore {{ background:rgba(255,255,255,0.06); border-radius:10px; color:#d6d6d6; font-size:18px;
                            font-weight:900; border:1px solid rgba(255,255,255,0.10); padding:0 0 6px 0; }}
    QPushButton#YaPlMore:hover {{ background:rgba(255,255,255,0.12); color:#fff; }}
    QPushButton#YaCornerBtn {{ background:transparent; border-radius:18px; }}
    QPushButton#YaCornerBtn:hover {{ background:rgba(255,255,255,0.07); }}
    QPushButton#YaNetCorner {{ background:transparent; border-radius:18px; }}
    QPushButton#YaNetCorner:hover {{ background:rgba(255,255,255,0.07); }}
    QPushButton#YaNetCorner:checked {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {_rgba(YELLOW, 0.22)},
                                                                  stop:1 {PANEL}); }}
    QPushButton#YaNav:checked {{ color:#fff; font-weight:800;
        background:qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {_rgba(YELLOW, 0.16)},
                                   stop:0.55 {_rgba(YELLOW, 0.05)}, stop:1 rgba(255,255,255,0.02)); }}
    QLabel#YaBadge {{ background:{YELLOW}; color:#000; border-radius:9px; font-size:11px; font-weight:800;
                      padding:0 6px; }}
    QPushButton#YaChip {{ background:rgba(255,255,255,0.08); border:none; border-radius:16px;
                          padding:10px 18px; font-size:13px; font-weight:700; color:#d0d0d0; }}
    QPushButton#YaChip:hover {{ background:rgba(255,255,255,0.15); color:#ffffff; }}
    QPushButton#YaChip:checked {{ background:{YELLOW}; color:#000000; }}
    QFrame#YaSegTrack {{ background:rgba(255,255,255,0.07); border:none; border-radius:22px; }}
    QPushButton#YaSeg {{ background:transparent; border:none; border-radius:18px;
                         padding:8px 20px; font-size:13px; font-weight:700; color:#b5b5b5; }}
    QPushButton#YaSeg:hover {{ color:#ffffff; background:rgba(255,255,255,0.08); }}
    QPushButton#YaSeg:checked {{ background:{YELLOW}; color:#000000; }}
    QPushButton#YaIcon {{ background:transparent; border:none; border-radius:18px; padding:0; }}
    QPushButton#YaIcon:hover {{ background:#2a2a2a; }}
    QPushButton#YaIcon:checked {{ background:#2f2f2f; }}
    QLineEdit {{ background:#1f1f1f; border:1px solid #2c2c2c; border-radius:18px; padding:8px 16px;
                 color:{TEXT}; selection-background-color:{YELLOW}; selection-color:#000; }}
    QLineEdit:focus {{ border-color:#4a4a4a; }}
    QComboBox {{ background:rgba(255,255,255,0.07); border:none; border-radius:14px; padding:9px 16px;
                 font-weight:600; }}
    QComboBox:hover {{ background:rgba(255,255,255,0.12); }}
    QComboBox::drop-down {{ border:none; width:34px; }}
    QComboBox::down-arrow {{ image:url({A["arrow"]}); width:12px; height:8px; }}
    QComboBox QAbstractItemView {{ background:{PANEL2}; border:1px solid #2c2c2c; border-radius:10px; padding:4px;
                                   selection-background-color:#2c2c2c; outline:0; }}
    QSpinBox {{ background:rgba(255,255,255,0.07); border:none; border-radius:10px; padding:5px 8px; }}
    QTextEdit, QPlainTextEdit {{ background:rgba(255,255,255,0.05); border:none; border-radius:14px;
                                 padding:10px 12px; selection-background-color:{YELLOW}; selection-color:#000; }}
    QCheckBox {{ spacing:12px; padding:3px 0; }}
    QCheckBox::indicator {{ width:46px; height:26px; border:none; background:transparent; image:url({A["sw_off"]}); }}
    QCheckBox::indicator:checked {{ image:url({A["sw_on"]}); }}
    QWidget#YaSettingsCard {{ background:transparent; }}
    QSlider::groove:horizontal {{ height:4px; background:#3a3a3a; border-radius:2px; }}
    QSlider::sub-page:horizontal {{ background:#ffffff; border-radius:2px; }}
    QSlider::handle:horizontal {{ background:#ffffff; width:12px; height:12px; margin:-4px 0; border-radius:6px; }}
    QSlider::groove:vertical {{ width:4px; background:#3a3a3a; border-radius:2px; }}
    QSlider::add-page:vertical {{ background:{YELLOW}; border-radius:2px; }}
    QSlider::handle:vertical {{ background:#ffffff; height:12px; width:12px; margin:0 -4px; border-radius:6px; }}
    QListWidget, QListView {{ background:transparent; border:none; outline:none; }}
    QListWidget::item {{ padding:6px; border-radius:8px; }}
    QListWidget::item:hover {{ background:#1c1c1c; }}
    QListWidget::item:selected {{ background:#262626; color:#fff; }}
    QScrollArea {{ background:transparent; border:none; }}
    QScrollBar:vertical {{ background:transparent; width:8px; margin:4px 2px; }}
    QScrollBar::handle:vertical {{ background:#3a3a3a; border-radius:3px; min-height:30px; }}
    QScrollBar::handle:vertical:hover {{ background:#555; }}
    QScrollBar:horizontal {{ background:transparent; height:8px; margin:2px 4px; }}
    QScrollBar::handle:horizontal {{ background:#3a3a3a; border-radius:3px; min-width:30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}
    QFrame#Panel {{ background:transparent; border:none; }}
    QTabWidget::pane {{ border:none; }}
    """ + glass_controls_qss()


# ══════════════════════════════════════════════════════════════════════════ #
#  Иконки (рисуются кодом — без файлов и эмодзи)
# ══════════════════════════════════════════════════════════════════════════ #

_ICON_CACHE: dict = {}


def ya_icon(name: str, size: int = 22, color: str = "#ffffff") -> QIcon:
    key = (name, size, color)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    dpr = 2
    pm = QPixmap(size * dpr, size * dpr)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 24.0, size / 24.0)
    col = QColor(color)
    pen = QPen(col, 1.9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    _draw_icon(p, name, col)
    p.end()
    ic = QIcon(pm)
    _ICON_CACHE[key] = ic
    return ic


def _heart_path(cx=12.0, cy=12.5, s=1.0) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(cx, cy + 7 * s)
    path.cubicTo(cx - 9 * s, cy + 1 * s, cx - 8 * s, cy - 8 * s, cx - 4 * s, cy - 7.5 * s)
    path.cubicTo(cx - 2 * s, cy - 7.3 * s, cx - 0.6 * s, cy - 5.8 * s, cx, cy - 4.4 * s)
    path.cubicTo(cx + 0.6 * s, cy - 5.8 * s, cx + 2 * s, cy - 7.3 * s, cx + 4 * s, cy - 7.5 * s)
    path.cubicTo(cx + 8 * s, cy - 8 * s, cx + 9 * s, cy + 1 * s, cx, cy + 7 * s)
    return path


def _draw_icon(p: QPainter, name: str, col: QColor):
    if name == "search":
        p.drawEllipse(QRectF(4, 4, 12, 12))
        p.drawLine(QPointF(14.6, 14.6), QPointF(20, 20))
    elif name == "performance":
        p.drawArc(QRectF(3,4,18,18),0,180*16)
        p.drawLine(QPointF(4,17),QPointF(20,17))
        p.drawLine(QPointF(12,14),QPointF(17,8))
        for x,y in ((5,12),(7,7),(12,5),(18,7)):p.drawPoint(QPointF(x,y))
    elif name == "bug":
        p.drawRoundedRect(QRectF(7,7,10,13),5,5)
        p.drawArc(QRectF(8,3,8,8),0,180*16)
        p.drawLine(QPointF(12,9),QPointF(12,19))
        for y in (9,13,17):
            p.drawLine(QPointF(3,y-1),QPointF(7,y))
            p.drawLine(QPointF(17,y),QPointF(21,y-1))
    elif name == "wave":                     # «Моя волна»: светящееся ядро и волна, что расходится от него
        path = QPainterPath()
        for i in range(41):
            x = 2 + i * 0.5
            d = (x - 12) / 6.5
            y = 12 - math.sin((x - 12) * 0.95) * 5.2 * math.exp(-d * d)
            path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
        p.drawPath(path)
        p.setPen(QPen(col, 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(QRectF(3.5, 3.5, 17, 17), 30 * 16, 60 * 16)
        p.drawArc(QRectF(3.5, 3.5, 17, 17), 210 * 16, 60 * 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(12, 12), 2.3, 2.3)
    elif name == "ai_sync":                  # ИИ-синхронизация: строки текста с отметками времени и искра
        pen = p.pen()
        for y, w in ((7.0, 9.0), (12.0, 12.0), (17.0, 7.0)):
            p.drawLine(QPointF(8, y), QPointF(8 + w, y))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawEllipse(QPointF(4, y), 1.5, 1.5)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(pen)
        star = QPainterPath()
        cx, cy, r = 19.5, 5.0, 4.2
        for i in range(8):
            a = math.radians(-90 + i * 45)
            rr = r if i % 2 == 0 else r * 0.3
            pt = QPointF(cx + math.cos(a) * rr, cy + math.sin(a) * rr)
            star.moveTo(pt) if i == 0 else star.lineTo(pt)
        star.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawPath(star)
    elif name == "note":
        p.drawLine(QPointF(9, 17), QPointF(9, 5))
        p.drawLine(QPointF(9, 5), QPointF(19, 3.5))
        p.drawLine(QPointF(19, 3.5), QPointF(19, 15))
        p.drawEllipse(QRectF(4, 14.5, 5.5, 5))
        p.drawEllipse(QRectF(13.8, 12.5, 5.5, 5))
    elif name in ("heart", "collection"):
        p.drawPath(_heart_path())
    elif name == "heart_fill":
        p.setBrush(col)
        p.drawPath(_heart_path())
    elif name == "play":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        path = QPainterPath()
        path.moveTo(8, 5); path.lineTo(8, 19); path.lineTo(19, 12); path.closeSubpath()
        p.drawPath(path)
    elif name == "pause":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(QRectF(7, 5, 3.6, 14), 1, 1)
        p.drawRoundedRect(QRectF(13.4, 5, 3.6, 14), 1, 1)
    elif name in ("prev", "next"):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        path = QPainterPath()
        if name == "next":
            path.moveTo(6, 5.5); path.lineTo(6, 18.5); path.lineTo(16, 12); path.closeSubpath()
            p.drawPath(path)
            p.drawRoundedRect(QRectF(16.4, 5.5, 2.4, 13), 1, 1)
        else:
            path.moveTo(18, 5.5); path.lineTo(18, 18.5); path.lineTo(8, 12); path.closeSubpath()
            p.drawPath(path)
            p.drawRoundedRect(QRectF(5.2, 5.5, 2.4, 13), 1, 1)
    elif name == "shuffle":
        p.drawLine(QPointF(4, 7), QPointF(8, 7))
        path = QPainterPath(); path.moveTo(8, 7); path.cubicTo(12, 7, 12, 17, 16, 17); path.lineTo(20, 17)
        p.drawPath(path)
        p.drawLine(QPointF(4, 17), QPointF(8, 17))
        path = QPainterPath(); path.moveTo(8, 17); path.cubicTo(12, 17, 12, 7, 16, 7); path.lineTo(20, 7)
        p.drawPath(path)
        for y in (7, 17):
            p.drawLine(QPointF(17.5, y - 2.5), QPointF(20, y)); p.drawLine(QPointF(17.5, y + 2.5), QPointF(20, y))
    elif name in ("repeat", "repeat_one"):
        path = QPainterPath()
        path.moveTo(6, 11); path.lineTo(6, 9); path.quadTo(6, 7, 8, 7); path.lineTo(18, 7)
        p.drawPath(path)
        p.drawLine(QPointF(15.5, 4.5), QPointF(18, 7)); p.drawLine(QPointF(15.5, 9.5), QPointF(18, 7))
        path = QPainterPath()
        path.moveTo(18, 13); path.lineTo(18, 15); path.quadTo(18, 17, 16, 17); path.lineTo(6, 17)
        p.drawPath(path)
        p.drawLine(QPointF(8.5, 14.5), QPointF(6, 17)); p.drawLine(QPointF(8.5, 19.5), QPointF(6, 17))
        if name == "repeat_one":
            f = ya_font(8, QFont.Weight.Black)
            p.setFont(f)
            p.drawText(QRectF(9, 8, 6, 8), Qt.AlignmentFlag.AlignCenter, "1")
    elif name == "clip":                                  # экран с кнопкой «play» — клип
        p.drawRoundedRect(QRectF(3, 5, 18, 14), 3, 3)
        tri = QPainterPath()
        tri.moveTo(10, 9)
        tri.lineTo(10, 15)
        tri.lineTo(15.5, 12)
        tri.closeSubpath()
        p.setBrush(col)
        p.drawPath(tri)
        p.setBrush(Qt.BrushStyle.NoBrush)
    elif name == "lyrics":
        for y, w in ((6, 14), (10.5, 11), (15, 14), (19.5, 8)):
            p.drawLine(QPointF(5, y), QPointF(5 + w, y))
    elif name == "queue":
        for y in (6, 12, 18):
            p.drawLine(QPointF(9, y), QPointF(20, y))
            p.setBrush(col); p.drawEllipse(QPointF(5, y), 1.2, 1.2); p.setBrush(Qt.BrushStyle.NoBrush)
    elif name == "attach":
        path = QPainterPath()
        path.moveTo(8, 13)
        path.lineTo(14, 7)
        path.cubicTo(17, 4, 21, 8, 18, 11)
        path.lineTo(10, 19)
        path.cubicTo(5, 24, 0, 17, 5, 12)
        path.lineTo(13, 4)
        p.drawPath(path)
    elif name == "star":                                   # ачивки
        path = QPainterPath()
        for i in range(11):
            a = i * math.pi / 5 - math.pi / 2
            r = 9 if i % 2 == 0 else 4
            pt = QPointF(12 + math.cos(a) * r, 12.5 + math.sin(a) * r)
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        p.drawPath(path)
    elif name == "headphones":
        p.drawArc(QRectF(4, 3, 16, 18), 0, 180 * 16)
        p.drawRoundedRect(QRectF(3, 11, 4, 9), 2, 2)
        p.drawRoundedRect(QRectF(17, 11, 4, 9), 2, 2)
    elif name == "settings":
        for y, x in ((6, 15), (12, 8), (18, 13)):
            p.drawLine(QPointF(4, y), QPointF(20, y))
            p.setBrush(QColor(0, 0, 0)); p.drawEllipse(QPointF(x, y), 2.4, 2.4); p.setBrush(Qt.BrushStyle.NoBrush)
    elif name == "eq":                                     # столбики эквалайзера — панель «Звук»
        for x, top in ((5, 11), (9.7, 6), (14.3, 9), (19, 4)):
            p.drawLine(QPointF(x, 20), QPointF(x, top))
    elif name in ("volume", "mute"):
        path = QPainterPath()
        path.moveTo(4, 9.5); path.lineTo(7.5, 9.5); path.lineTo(12, 5.5); path.lineTo(12, 18.5)
        path.lineTo(7.5, 14.5); path.lineTo(4, 14.5); path.closeSubpath()
        p.drawPath(path)
        if name == "volume":
            p.drawArc(QRectF(11, 8, 6, 8), -60 * 16, 120 * 16)
            p.drawArc(QRectF(11, 5, 10, 14), -60 * 16, 120 * 16)
        else:
            p.drawLine(QPointF(15, 9), QPointF(20, 15)); p.drawLine(QPointF(20, 9), QPointF(15, 15))
    elif name == "cover":
        p.drawRoundedRect(QRectF(4, 4, 16, 16), 3.5, 3.5)
        path = QPainterPath(); path.moveTo(6, 17); path.lineTo(10.5, 12); path.lineTo(13.5, 15)
        path.lineTo(15.5, 13); path.lineTo(18, 16)
        p.drawPath(path)
        p.drawEllipse(QPointF(15, 8.5), 1.5, 1.5)
    elif name == "plus":
        p.drawLine(QPointF(12, 5), QPointF(12, 19)); p.drawLine(QPointF(5, 12), QPointF(19, 12))
    elif name == "check":
        p.drawLine(QPointF(5, 12.5), QPointF(10, 17.5)); p.drawLine(QPointF(10, 17.5), QPointF(19.5, 7))
    elif name in ("thumb_up", "thumb_down", "thumb_up_fill", "thumb_down_fill"):   # «больше / меньше такого»
        if name.startswith("thumb_down"):
            p.translate(0, 24); p.scale(1, -1)
        path = QPainterPath(); path.moveTo(8, 10.5); path.lineTo(11.3, 3.6)
        path.cubicTo(13.2, 3.4, 14.4, 4.8, 13.9, 6.9); path.lineTo(13.2, 9.6); path.lineTo(18.6, 9.6)
        path.cubicTo(20.2, 9.6, 21.2, 11, 20.8, 12.5); path.lineTo(19.2, 18.6)
        path.cubicTo(18.9, 19.7, 18, 20.4, 16.9, 20.4); path.lineTo(8, 20.4); path.closeSubpath()
        if name.endswith("_fill"):
            p.setBrush(col)
        p.drawPath(path)
        p.drawRoundedRect(QRectF(3.2, 10.5, 3.4, 9.9), 1.2, 1.2)
    elif name == "bell":
        path = QPainterPath(); path.moveTo(6, 16.5); path.cubicTo(7, 15, 7, 13, 7, 10.5)
        path.cubicTo(7, 7.5, 9.2, 5.2, 12, 5.2); path.cubicTo(14.8, 5.2, 17, 7.5, 17, 10.5)
        path.cubicTo(17, 13, 17, 15, 18, 16.5); path.closeSubpath(); p.drawPath(path)
        p.drawLine(QPointF(10.2, 19.2), QPointF(13.8, 19.2))
    elif name == "gamepad":
        body = QPainterPath(); body.moveTo(7.2, 7.5); body.lineTo(16.8, 7.5)
        body.cubicTo(19.6, 7.5, 21.2, 10.5, 21.6, 14.5); body.cubicTo(22, 17.6, 19.8, 19, 18.2, 17.4)
        body.lineTo(16, 15.2); body.lineTo(8, 15.2); body.lineTo(5.8, 17.4)
        body.cubicTo(4.2, 19, 2, 17.6, 2.4, 14.5); body.cubicTo(2.8, 10.5, 4.4, 7.5, 7.2, 7.5)
        body.closeSubpath(); p.drawPath(body)
        p.drawLine(QPointF(7.6, 9.9), QPointF(7.6, 13)); p.drawLine(QPointF(6.05, 11.45), QPointF(9.15, 11.45))
        p.drawEllipse(QPointF(15.6, 10.4), 0.75, 0.75); p.drawEllipse(QPointF(17.6, 12.4), 0.75, 0.75)
    elif name == "folder":
        path = QPainterPath(); path.moveTo(3.5, 7); path.lineTo(9, 7); path.lineTo(11, 9); path.lineTo(20.5, 9)
        path.lineTo(20.5, 18); path.lineTo(3.5, 18); path.closeSubpath()
        p.drawPath(path)
    elif name == "download":
        p.drawLine(QPointF(12, 4), QPointF(12, 15))
        p.drawLine(QPointF(7.5, 11), QPointF(12, 15.5)); p.drawLine(QPointF(16.5, 11), QPointF(12, 15.5))
        p.drawLine(QPointF(5, 19.5), QPointF(19, 19.5))
    elif name == "chevron_down":
        p.drawLine(QPointF(6, 9.5), QPointF(12, 15.5)); p.drawLine(QPointF(12, 15.5), QPointF(18, 9.5))
    elif name == "back":
        p.drawLine(QPointF(14.5, 6), QPointF(8.5, 12)); p.drawLine(QPointF(8.5, 12), QPointF(14.5, 18))
    elif name == "palette":
        p.drawEllipse(QRectF(4, 4, 16, 16))
        p.setBrush(col)
        for x, y in ((9, 9), (14.5, 8.5), (16, 13), (8.5, 14.5)):
            p.drawEllipse(QPointF(x, y), 1.3, 1.3)
    elif name == "dots":
        p.setBrush(col)
        for x in (6, 12, 18):
            p.drawEllipse(QPointF(x, 12), 1.5, 1.5)
    elif name == "album":
        p.drawEllipse(QRectF(3.5, 3.5, 17, 17))
        p.drawEllipse(QRectF(9.5, 9.5, 5, 5))
        p.drawArc(QRectF(6.5, 6.5, 11, 11), 100 * 16, 70 * 16)
    elif name == "close":
        p.drawLine(QPointF(6.5, 6.5), QPointF(17.5, 17.5))
        p.drawLine(QPointF(17.5, 6.5), QPointF(6.5, 17.5))
    elif name == "user":
        p.drawEllipse(QRectF(8, 4, 8, 8))
        p.drawArc(QRectF(4.5, 14, 15, 12), 20 * 16, 140 * 16)
    elif name == "clock":
        p.drawEllipse(QRectF(3.5, 3.5, 17, 17))
        p.drawLine(QPointF(12, 7.5), QPointF(12, 12))
        p.drawLine(QPointF(12, 12), QPointF(15.5, 14))
    elif name == "edit":
        path = QPainterPath(); path.moveTo(5, 19); path.lineTo(6, 15); path.lineTo(15.5, 5.5); path.lineTo(18.5, 8.5)
        path.lineTo(9, 18); path.closeSubpath()
        p.drawPath(path)
    elif name == "net":                                    # Echoes.NET — точка и расходящееся «эхо» ((•))
        p.setBrush(col)
        p.drawEllipse(QPointF(12, 12), 2.4, 2.4)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for r in (5.6, 9.6):
            rect = QRectF(12 - r, 12 - r, 2 * r, 2 * r)
            p.drawArc(rect, int(-42 * 16), int(84 * 16))          # справа
            p.drawArc(rect, int(138 * 16), int(84 * 16))          # слева
    elif name == "tier":                                   # тирлист — уровни разной длины
        for y, x2 in ((6, 19), (12, 15), (18, 10.5)):
            p.drawLine(QPointF(5, y), QPointF(x2, y))
        p.setBrush(col)
        p.drawEllipse(QPointF(5, 6), 1.2, 1.2)
    elif name == "duel":                                   # дуэль — две карточки «против»
        p.drawRoundedRect(QRectF(3, 6, 8, 12), 2, 2)
        p.drawRoundedRect(QRectF(13, 6, 8, 12), 2, 2)
        p.drawLine(QPointF(11.2, 9), QPointF(12.8, 15))
    elif name == "send":
        path = QPainterPath(); path.moveTo(4, 11.5); path.lineTo(20, 4.5); path.lineTo(14, 20)
        path.lineTo(11, 13); path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(11, 13), QPointF(20, 4.5))
    elif name == "chat":
        path = QPainterPath(); path.addRoundedRect(QRectF(3.5, 4.5, 17, 12), 4, 4)
        p.drawPath(path)
        p.drawLine(QPointF(8, 16.5), QPointF(6.5, 20)); p.drawLine(QPointF(6.5, 20), QPointF(11.5, 16.5))
    elif name in ("up", "down"):
        path = QPainterPath()
        if name == "up":
            path.moveTo(12, 5); path.lineTo(19, 13); path.lineTo(14.5, 13); path.lineTo(14.5, 19)
            path.lineTo(9.5, 19); path.lineTo(9.5, 13); path.lineTo(5, 13)
        else:
            path.moveTo(12, 19); path.lineTo(19, 11); path.lineTo(14.5, 11); path.lineTo(14.5, 5)
            path.lineTo(9.5, 5); path.lineTo(9.5, 11); path.lineTo(5, 11)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "tastemap":
        path = QPainterPath(QPointF(3, 7))
        path.lineTo(10, 3); path.lineTo(20, 7); path.lineTo(20, 20)
        path.lineTo(13, 16); path.lineTo(3, 20); path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(10, 3), QPointF(10, 11))
        p.drawLine(QPointF(13, 16), QPointF(13, 20))
        p.drawEllipse(QPointF(13, 10), 2.5, 2.5)
        p.drawLine(QPointF(13, 12.5), QPointF(13, 15))
    elif name == "broadcast_tower":
        p.drawLine(QPointF(12, 9), QPointF(7, 21))
        p.drawLine(QPointF(12, 9), QPointF(17, 21))
        p.drawLine(QPointF(9, 17), QPointF(15, 17))
        p.drawEllipse(QPointF(12, 7), 1.5, 1.5)
        for radius in (5, 9):
            box = QRectF(12-radius, 7-radius, radius*2, radius*2)
            p.drawArc(box, 140*16, 80*16)
            p.drawArc(box, -40*16, 80*16)
    elif name == "users":
        p.drawEllipse(QRectF(5, 5, 7, 7))
        p.drawArc(QRectF(2.5, 14, 12, 10), 20 * 16, 140 * 16)
        p.drawEllipse(QRectF(13.5, 6.5, 5.5, 5.5))
        p.drawArc(QRectF(13, 14.5, 9, 8), 30 * 16, 110 * 16)
    elif name == "copy":
        p.drawRoundedRect(QRectF(8.5, 8.5, 11, 11), 2.5, 2.5)
        p.drawLine(QPointF(5, 15), QPointF(5, 6.5)); p.drawLine(QPointF(5, 6.5), QPointF(6.5, 5))
        p.drawLine(QPointF(6.5, 5), QPointF(15, 5))


def icon_button(name, tip="", size=36, icon_size=22, color="#ffffff", checkable=False) -> QPushButton:
    b = QPushButton()
    b.setObjectName("YaIcon")
    b.setIcon(ya_icon(name, icon_size, color))
    b.setIconSize(QSize(icon_size, icon_size))
    b.setFixedSize(size, size)
    b.setStyleSheet(f"QPushButton{{border-radius:{size // 2}px;padding:0;}}")
    b.setToolTip(tip)
    b.setCheckable(checkable)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return b


# ══════════════════════════════════════════════════════════════════════════ #
#  Обложки (кэш скруглённых картинок)
# ══════════════════════════════════════════════════════════════════════════ #

# Скруглённые обложки: кэш с бюджетом по памяти (вытесняются давно не показанные).
# Раньше держалось до 1500 штук в двойном разрешении — до полугигабайта картинок.
_COVER_CACHE: dict = {}
_COVER_BYTES = [0]
_COVER_BUDGET = 40 * 2 ** 20


def _pm_bytes(pm) -> int:
    return pm.width() * pm.height() * 4


def clear_cover_cache():
    _COVER_CACHE.clear()
    _COVER_BYTES[0] = 0
    try:
        _NO_COVER.clear()
    except NameError:
        pass


PLACEHOLDER = {"path": "", "pm": None}                         # своя картинка вместо ноты (Оформление)


def set_placeholder(path: str):
    """Своя картинка-заглушка для треков и исполнителей без обложки ('' — стандартная нота)."""
    path = str(path or "")
    pm = QPixmap(path) if path and Path(path).exists() else QPixmap()
    PLACEHOLDER["path"], PLACEHOLDER["pm"] = (path, pm) if not pm.isNull() else ("", None)
    PLACEHOLDER["scaled"] = {}
    clear_cover_cache()


def _placeholder(size: int, seed: str = "") -> QPixmap:
    own = PLACEHOLDER.get("pm")
    if own is not None:                                        # своя картинка — по центру, квадратом
        cache = PLACEHOLDER.setdefault("scaled", {})
        key = (own.cacheKey(), size)
        hit = cache.get(key)
        if hit is not None:
            return QPixmap(hit)
        s0 = min(own.width(), own.height())
        sq = own.copy((own.width() - s0) // 2, (own.height() - s0) // 2, s0, s0)
        out = sq.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        if size <= 512:
            cache[key] = QPixmap(out)
            while len(cache) > 16:
                cache.pop(next(iter(cache)))
        return out
    rnd = random.Random(seed)
    h1 = rnd.random()
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor.fromHsvF(h1, 0.55, 0.55))
    g.setColorAt(1, QColor.fromHsvF((h1 + 0.15) % 1, 0.7, 0.22))
    p.fillRect(pm.rect(), g)
    p.setPen(QPen(QColor(255, 255, 255, 90), max(1.5, size / 30)))
    s = size / 24.0
    p.scale(s, s)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(10, 16.5), QPointF(10, 7))
    p.drawLine(QPointF(10, 7), QPointF(16, 6))
    p.drawLine(QPointF(16, 6), QPointF(16, 14.5))
    p.drawEllipse(QRectF(6.5, 14.5, 4, 3.6))
    p.drawEllipse(QRectF(12.5, 12.6, 4, 3.6))
    p.end()
    return pm


def _cover_image(path: str, size: int, radius: float, circle: bool) -> QImage:
    """Скруглённая обложка как QImage — можно строить в фоновом потоке (QPixmap — только в GUI)."""
    src = read_image(path, size * 4)
    if src.isNull():
        return QImage()
    s = min(src.width(), src.height())
    src = src.copy((src.width() - s) // 2, (src.height() - s) // 2, s, s)
    n = size * 2
    sc = src.scaled(n, n, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    out = QImage(n, n, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    if circle:
        clip.addEllipse(QRectF(0, 0, n, n))
    else:
        clip.addRoundedRect(QRectF(0, 0, n, n), radius * 2, radius * 2)
    p.setClipPath(clip)
    p.drawImage(0, 0, sc)
    p.end()
    return out


class _CoverLoader:
    """Обложки для списков и карточек декодируются в фоновом потоке (сначала свежие запросы), а
    пока на их месте заглушка; готовая обложка перерисовывает свой виджет."""
    BUDGET = 0.006

    def __init__(self):
        import collections
        import threading
        self.q = collections.deque()
        self.waiting = {}                            # ключ → [weakref виджетов]
        self.cv = threading.Condition()
        self.bridge = None
        self.thread = None
        self._frame = (0.0, 0.0)                     # (начало «кадра», потрачено)

    def sync_ok(self) -> bool:
        # «кадр» — до возврата в цикл событий (а не 30 мс по часам: внутри одной долгой отрисовки — снимок
        # страницы для перехода — бюджет раньше обнулялся снова и снова, и декодировались все обложки сразу)
        if not self.__dict__.get("_armed"):
            self._armed = True
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self._new_frame)
        return self._frame[1] < self.BUDGET

    def _new_frame(self):
        self._armed = False
        self._frame = (time.perf_counter(), 0.0)

    def spent(self, dt):
        t0, used = self._frame
        self._frame = (t0, used + dt)

    def request(self, key, path, size, radius, circle, widget):
        import weakref
        from PyQt6.QtCore import QObject

        if self.bridge is None:
            class _Bridge(QObject):
                ready = pyqtSignal(object, object)
            self.bridge = _Bridge()
            self.bridge.ready.connect(self._ready)
        lst = self.waiting.get(key)
        try:
            ref = weakref.ref(widget) if widget is not None else None
        except TypeError:
            ref = None
        if lst is not None:
            if ref is not None and ref not in lst:
                lst.append(ref)
            return
        self.waiting[key] = [ref] if ref is not None else []
        with self.cv:
            self.q.append((key, path, size, radius, circle))
            while len(self.q) > 300:                 # ушли далеко — старые запросы не нужны
                old = self.q.popleft()
                self.waiting.pop(old[0], None)
            self.cv.notify()
        if self.thread is None:
            import threading
            self.thread = threading.Thread(target=self._run, daemon=True, name="ya-covers")
            self.thread.start()

    def _run(self):
        while True:
            with self.cv:
                while not self.q:
                    self.cv.wait()
                key, path, size, radius, circle = self.q.pop()        # сначала свежие — то, что на экране
            try:
                img = _cover_image(path, size, radius, circle)
            except Exception:                        # noqa: BLE001
                img = QImage()
            try:
                self.bridge.ready.emit(key, img)
            except RuntimeError:
                return

    def _ready(self, key, img):
        refs = self.waiting.pop(key, None)
        if img is None or img.isNull():
            _remember_missing_cover(key)
        else:
            out = QPixmap.fromImage(img)
            out.setDevicePixelRatio(2)
            _cache_put(key, out)
        for r in refs or []:
            w = r() if r is not None else None
            if w is not None:
                try:
                    w.update()
                except RuntimeError:
                    pass
                import gpu_scroll                              # идёт прокрутка на GPU — обновить её полосы
                if gpu_scroll.ACTIVE is not None:
                    gpu_scroll.ACTIVE.touch(w)


_LOADER = _CoverLoader()
_NO_COVER: set = set()                               # файл есть, но не читается — заглушка, без повторов


def _remember_missing_cover(key):
    if len(_NO_COVER) >= 1024:
        _NO_COVER.pop()
    _NO_COVER.add(key)


def _cache_put(key, out):
    old = _COVER_CACHE.pop(key, None)
    if old is not None:
        _COVER_BYTES[0] -= _pm_bytes(old)
    _COVER_CACHE[key] = out
    _COVER_BYTES[0] += _pm_bytes(out)
    prune_cover_cache()


def prune_cover_cache():
    while _COVER_BYTES[0] > _COVER_BUDGET and _COVER_CACHE:
        o = _COVER_CACHE.pop(next(iter(_COVER_CACHE)))
        _COVER_BYTES[0] -= _pm_bytes(o)


def cover_pixmap(path: str, size: int, radius: float = 6, seed: str = "", circle=False, lazy=None) -> QPixmap:
    """lazy — виджет, который перерисовать, когда обложка догрузится в фоне (списки, карточки):
    файловая система и декодирование не задерживают отрисовку даже первой обложки."""
    key = (path or "", size, radius, circle, seed if not path else "")
    pm = _COVER_CACHE.pop(key, None)
    if pm is not None:
        _COVER_CACHE[key] = pm                       # в конец очереди — недавно показана
        return pm
    if path and key not in _NO_COVER:
        if lazy is not None:
            _LOADER.request(key, path, size, radius, circle, lazy)
            return cover_pixmap("", size, radius, seed or path, circle)
        t0 = time.perf_counter()
        img = _cover_image(path, size, radius, circle) if Path(path).exists() else QImage()
        _LOADER.spent(time.perf_counter() - t0)
        if not img.isNull():
            out = QPixmap.fromImage(img)
            out.setDevicePixelRatio(2)
            _cache_put(key, out)
            return out
        _remember_missing_cover(key)
    src = QPixmap()
    if src.isNull():
        src = _placeholder(size * 2, seed or path or "x")
    s = min(src.width(), src.height())
    src = src.copy((src.width() - s) // 2, (src.height() - s) // 2, s, s)
    dpr = 2
    sc = src.scaled(size * dpr, size * dpr, Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
    out = QPixmap(size * dpr, size * dpr)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    if circle:
        clip.addEllipse(QRectF(0, 0, size * dpr, size * dpr))
    else:
        clip.addRoundedRect(QRectF(0, 0, size * dpr, size * dpr), radius * dpr, radius * dpr)
    p.setClipPath(clip)
    p.drawPixmap(0, 0, sc)
    p.end()
    out.setDevicePixelRatio(dpr)
    _COVER_CACHE[key] = out
    _COVER_BYTES[0] += _pm_bytes(out)
    while _COVER_BYTES[0] > _COVER_BUDGET and len(_COVER_CACHE) > 1:
        old = _COVER_CACHE.pop(next(iter(_COVER_CACHE)))
        _COVER_BYTES[0] -= _pm_bytes(old)
    return out


def cover_colors(path: str):
    """Два цвета обложки для фона «Моей волны»: насыщенный и второй."""
    img = read_image(path, 64) if path and Path(path).exists() else QImage()
    if img.isNull():
        return QColor("#ffd60a"), QColor("#e0218a")
    img = img.scaled(12, 12, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    cols = []
    for y in range(img.height()):
        for x in range(img.width()):
            c = QColor(img.pixel(x, y))
            h, s, v, _ = c.getHsvF()
            cols.append((s * v, h, s, v))
    cols.sort(reverse=True)
    best = cols[0]
    h1 = best[1] if best[1] >= 0 else 0.13
    other = next((c for c in cols[1:] if c[1] >= 0 and min(abs(c[1] - h1), 1 - abs(c[1] - h1)) > 0.12), None)
    h2 = other[1] if other else (h1 + 0.8) % 1.0
    return QColor.fromHsvF(h1, min(1.0, best[2] * 1.2 + 0.2), 1.0), QColor.fromHsvF(h2, 0.85, 0.9)


def _fmt(sec) -> str:
    sec = max(0, int(float(sec or 0)))
    return f"{sec // 60:02d}:{sec % 60:02d}"


def _artists_of(a) -> list:
    """Ключи всех исполнителей строки «автор» (или трека — тогда и «(feat. X)» из названия), с учётом склеек."""
    from artist_identity import split, credits, ident
    names = credits(a) if isinstance(a, dict) else split(a)
    return [ident(n) for n in names]


def _is_by(t: dict, name: str) -> bool:
    from artist_identity import ident
    k = ident(name)
    return bool(k) and k in _artists_of(t)


def _artist_main(a: str) -> str:
    """Основной исполнитель строки «автор» в общем написании (Lil Flash$ = LiL Flash$)."""
    from artist_identity import split, ident, _ALIAS
    names = split(a)
    if not names:
        return ""
    if _ALIAS:
        disp = _DISPLAY.get(ident(names[0]))
        if disp:
            return disp
    return names[0]


_DISPLAY: dict = {}                    # ключ исполнителя → общее написание (обновляет _artist_index)


def _artist_index(lib):
    from artist_identity import index_for
    idx = index_for(lib)
    if getattr(_artist_index, "_last", None) is not idx:
        _artist_index._last = idx
        _DISPLAY.clear()
        _DISPLAY.update({k: idx._best(c) for k, c in idx.names.items()})
    return idx


# ══════════════════════════════════════════════════════════════════════════ #
#  Список треков (модель + делегат + вид)
# ══════════════════════════════════════════════════════════════════════════ #

class _RowBox:
    """Обёртка над строкой списка: Qt при передаче dict делает его КОПИЮ, а объект-обёртка проходит как есть."""
    __slots__ = ("d",)

    def __init__(self, d):
        self.d = d


def _row(idx):
    v = idx.data(Qt.ItemDataRole.UserRole)
    return v.d if isinstance(v, _RowBox) else v


class TrackModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[dict] = []        # {"t": track, "ctx": "library"|имя, "i": индекс}

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, idx, role=Qt.ItemDataRole.DisplayRole):
        if not idx.isValid() or not (0 <= idx.row() < len(self.rows)):
            return None
        r = self.rows[idx.row()]
        if role == Qt.ItemDataRole.UserRole:
            return _RowBox(r)              # не dict: Qt копирует словари, а нам нужна сама строка (состояние превью/загрузки)
        if role == Qt.ItemDataRole.DisplayRole:
            return r["t"].get("title", "")
        return None


class TrackDelegate(QStyledItemDelegate):
    ROW_H = 56

    def __init__(self, shell, parent=None):
        super().__init__(parent)
        self.shell = shell

    def sizeHint(self, opt, idx):
        return QSize(opt.rect.width(), self.ROW_H)

    @staticmethod
    def zones(r: QRect):
        heart = QRect(r.right() - 120, r.top() + 14, 28, 28)
        cover = QRect(r.left() + 10, r.top() + 8, 40, 40)
        return heart, cover

    @staticmethod
    def dots_zone(r: QRect):
        return QRect(r.right() - 156, r.top() + 14, 28, 28)

    @staticmethod
    def preview_zone(r: QRect):
        """Кнопка «30 с» (послушать до скачивания) — только у треков, которых нет в коллекции."""
        return QRect(r.right() - 270, r.top() + 14, 86, 28)

    ALBUM_MIN_W = 720                                          # уже — колонка альбома прячется

    @staticmethod
    def album_of(row) -> str:
        """Альбом для колонки в строке ('' — не показывать: неизвестен, сингл с тем же названием, что у трека,
        строка самого альбома или не скачанный трек)."""
        if not row or row.get("remote") or row.get("ctx") == ALBUM_PL:
            return ""
        alb = " ".join(str(row["t"].get("album") or "").split())
        if alb.lower() in _NO_ALBUM or alb.lower() == " ".join(str(row["t"].get("title") or "").split()).lower():
            return ""
        return alb

    @staticmethod
    def album_zone(r: QRect):
        """Колонка альбома в пустой середине строки; None — строка узкая, колонки нет."""
        if r.width() < TrackDelegate.ALBUM_MIN_W:
            return None
        x = r.left() + int(r.width() * 0.52)
        return QRect(x, r.top() + 14, max(0, r.right() - 156 - 16 - x), 28)

    @staticmethod
    def album_hit(r: QRect, row):
        """Прямоугольник самой надписи альбома (по нему клик открывает альбом) или None."""
        z = TrackDelegate.album_zone(r)
        alb = TrackDelegate.album_of(row)
        if z is None or not alb or z.width() < 40:
            return None
        w = min(z.width(), QFontMetrics(ya_font(12)).horizontalAdvance(alb) + 4)
        return QRect(z.left(), z.top(), w, z.height())

    EQ_BARS = 4

    @staticmethod
    def eq_levels(playing: bool, now=None) -> list:
        """Высоты столбиков эквалайзера 0..1 на обложке играющего трека. На паузе и без анимаций — застывшие."""
        if not playing:
            return [0.34, 0.62, 0.46, 0.26]
        import motion
        if motion.strength() <= 0:
            return [0.55, 0.9, 0.7, 0.4]
        ph = (time.monotonic() if now is None else now)
        out = []
        for k in range(TrackDelegate.EQ_BARS):                  # две синусоиды на столбик — без видимого повтора
            v = 0.5 + 0.3 * math.sin(ph * (6.1 + 1.3 * k) + k * 1.9) + 0.2 * math.sin(ph * (9.7 - 0.9 * k) + k * 0.7)
            out.append(max(0.16, min(1.0, v)))
        return out

    def _paint_eq(self, p: QPainter, cov_r: QRect, playing: bool):
        """Эквалайзер поверх обложки играющей строки — рисуется вживую, поверх готовой картинки строки."""
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(YELLOW))
        bw, gap, top_h = 3.0, 2.5, 17.0
        n = self.EQ_BARS
        x0 = cov_r.center().x() + 0.5 - (n * bw + (n - 1) * gap) / 2
        base = cov_r.center().y() + 0.5 + top_h / 2
        for k, v in enumerate(self.eq_levels(playing)):
            h = max(3.0, top_h * v)
            p.drawRoundedRect(QRectF(x0 + k * (bw + gap), base - h, bw, h), 1.5, 1.5)
        p.restore()

    def paint(self, p: QPainter, opt, idx):
        """Строка рисуется один раз в картинку и дальше копируется (прокрутка без потери кадров);
        пересобирается, когда меняется трек, обложка, наведение, выделение, «играет», лайк, загрузка.
        Вживую поверх картинки — только эквалайзер на обложке играющего трека."""
        row = _row(idx)
        if not row:
            return
        self._paint_cached(p, opt, row)
        hover = bool(opt.state & QStyle.StateFlag.State_MouseOver)
        if not hover and not row.get("remote") and self.shell.is_current(row["t"]):
            playing = self.shell.is_playing()
            self._paint_eq(p, self.zones(opt.rect)[1], playing)
            view = getattr(opt, "widget", None)
            if playing and hasattr(view, "eq_seen"):
                view.eq_seen(idx.row())                        # только эта строка перерисовывается по кадрам

    def _paint_cached(self, p: QPainter, opt, row):
        t = row["t"]
        r = opt.rect
        pv = row.get("pv") or ("idle", 0)
        if pv[0] == "playing":                                 # живой «эквалайзер» превью — без кэша
            return self._paint_row(p, opt, row)
        hover = bool(opt.state & QStyle.StateFlag.State_MouseOver)
        sel = bool(opt.state & QStyle.StateFlag.State_Selected)
        remote = bool(row.get("remote"))
        cur = self.shell.is_current(t) and not remote
        view = getattr(opt, "widget", None)
        from raster_budget import ROWS
        cache_key=(id(self),id(row))
        c = ROWS.get(cache_key)
        cov = t.get("cover", "")
        if c is not None and c[3] == cov:                      # уже с настоящей обложкой — не декодировать заново
            cpk = c[4]
        else:
            cpk = cover_pixmap(cov, 40, 6, seed=t.get("path", "") or t.get("title", ""),
                               lazy=view.viewport() if hasattr(view, "viewport") else view).cacheKey()
        dpr = p.device().devicePixelRatioF() if p.device() is not None else 1.0
        viewport=view.viewport() if hasattr(view,'viewport') else view
        if viewport is not None and ROWS.limit < viewport.width()*viewport.height()*dpr*dpr*3.6:
            return self._paint_row(p,opt,row)
        key = (r.width(), r.height(), dpr, hover, sel, remote, bool(row.get("owned")), cur,
               cur and self.shell.is_playing(), not remote and self.shell.is_liked(t), str(row.get("dl")), str(pv),
               cpk, t.get("title"), t.get("artist"), t.get("duration"), t.get("album"), row.get("ctx"),
               TEXT, MUTED, YELLOW)
        if c is None or c[0] != key:
            buf = QPixmap(max(1, int(r.width() * dpr + 0.5)), max(1, int(r.height() * dpr + 0.5)))
            buf.setDevicePixelRatio(dpr)
            buf.fill(Qt.GlobalColor.transparent)
            bp = QPainter(buf)
            bp.translate(-r.left(), -r.top())
            self._paint_row(bp, opt, row)
            bp.end()
            real = bool(cov) and (cov, 40, 6, False, "") in _COVER_CACHE
            c = (key, buf, row, cov if real else None, cpk)
            ROWS.put(cache_key,c,buf.width()*buf.height()*4)
        p.drawPixmap(r.topLeft(), c[1])

    def _paint_row(self, p: QPainter, opt, row):
        t = row["t"]
        r = opt.rect
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        hover = bool(opt.state & QStyle.StateFlag.State_MouseOver)
        sel = bool(opt.state & QStyle.StateFlag.State_Selected)
        remote = bool(row.get("remote"))                       # трек альбома, которого ещё нет в коллекции
        owned = bool(row.get("owned"))                         # скачанный — подсвечиваем зелёным
        cur = self.shell.is_current(t) and not remote
        if owned:
            path = QPainterPath()
            path.addRoundedRect(QRectF(r.adjusted(2, 2, -2, -2)), 10, 10)
            p.fillPath(path, QColor(61, 220, 132, 26))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(61, 220, 132, 190))
            p.drawRoundedRect(QRectF(r.left() + 2, r.top() + 12, 3, r.height() - 24), 1.5, 1.5)
        if hover or sel:
            path = QPainterPath()
            path.addRoundedRect(QRectF(r.adjusted(2, 2, -2, -2)), 10, 10)
            p.fillPath(path, QColor(255, 255, 255, 22 if sel else 14))
        if remote:
            p.setOpacity(0.5 if not hover else 0.8)
        heart_r, cov_r = self.zones(r)
        dots_r = self.dots_zone(r)
        view = getattr(opt, "widget", None)
        pm = cover_pixmap(t.get("cover", ""), 40, 6, seed=t.get("path", "") or t.get("title", ""),
                          lazy=view.viewport() if hasattr(view, "viewport") else view)
        p.drawPixmap(cov_r, pm)
        if hover or cur:
            shade = QPainterPath()                             # затемнение — по скруглению обложки
            shade.addRoundedRect(QRectF(cov_r), 6, 6)
            p.fillPath(shade, QColor(0, 0, 0, 120 if hover else 140))
            if hover:                                          # наведение — значок действия; без него на играющей
                ic = ya_icon("download" if remote else         # строке вживую рисуется эквалайзер (_paint_eq)
                             ("pause" if (cur and self.shell.is_playing()) else "play"), 18, "#ffffff")
                ic.paint(p, cov_r.adjusted(11, 11, -11, -11))
        tx = cov_r.right() + 14
        tw = dots_r.left() - tx - 10
        alb = self.album_of(row)
        alb_r = self.album_zone(r) if alb else None
        if alb_r is not None and alb_r.width() >= 40:           # альбом — в пустой середине широкой строки
            tw = alb_r.left() - tx - 24
            fa = ya_font(12)
            p.setFont(fa)
            p.setPen(QColor("#cfcfcf") if hover else QColor(MUTED))
            p.drawText(alb_r, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       QFontMetrics(fa).elidedText(alb, Qt.TextElideMode.ElideRight, alb_r.width()))
        title = sanitize_title(t.get("title", "") or "Без названия")
        artist = t.get("artist") or "Неизвестный исполнитель"
        f = ya_font(14, QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor(YELLOW) if cur else QColor(TEXT))
        fm = QFontMetrics(f)
        p.drawText(QRect(tx, r.top() + 9, tw, 20), Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(title, Qt.TextElideMode.ElideRight, tw))
        f2 = ya_font(12)
        p.setFont(f2)
        p.setPen(QColor(MUTED))
        p.drawText(QRect(tx, r.top() + 29, tw, 18), Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(f2).elidedText(artist, Qt.TextElideMode.ElideRight, tw))
        if hover:
            # «⋯» — все действия с треком (то же, что правая кнопка)
            ya_icon("dots", 20, "#cfcfcf").paint(p, dots_r.adjusted(4, 4, -4, -4))
        if remote and (row.get("dl") or ("",))[0] not in ("queued", "progress", "retry"):
            pz = self.preview_zone(r)
            pv = row.get("pv") or ("idle", 0)
            active = pv[0] in ("playing", "paused", "loading")
            p.setOpacity(1.0)
            pill = QPainterPath()
            pill.addRoundedRect(QRectF(pz), 14, 14)
            if active:
                p.fillPath(pill, QColor(255, 219, 26, 46))
            else:
                p.fillPath(pill, QColor(255, 255, 255, 30 if hover else 18))
            col = YELLOW if active else "#d6d6d6"
            if pv[0] == "playing" and not hover:
                # живой «эквалайзер»: видно, что звучит; при наведении — значок паузы
                import time as _t
                ph = _t.monotonic() * 7.0
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(YELLOW))
                for k in range(3):
                    hb = 4 + 8 * abs(math.sin(ph + k * 1.7))
                    p.drawRoundedRect(QRectF(pz.left() + 11 + k * 5, pz.top() + 14 - hb / 2, 3, hb), 1.5, 1.5)
            else:
                ya_icon("pause" if pv[0] == "playing" else "play", 14, col).paint(
                    p, QRect(pz.left() + 10, pz.top() + 7, 14, 14))
            p.setFont(ya_font(11, QFont.Weight.Bold))
            p.setPen(QColor(col))
            txt = ("…" if pv[0] == "loading" else f"{int(pv[1]) + 1} с" if pv[0] in ("playing", "paused")
                   else "нет" if pv[0] == "error" else "30 с")
            p.drawText(QRect(pz.left() + 28, pz.top(), pz.width() - 32, pz.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, txt)
            p.setOpacity(0.5 if not hover else 0.8)
        if remote:
            st = row.get("dl") or ("", 0)
            p.setFont(ya_font(11, QFont.Weight.DemiBold))
            p.setPen(QColor(YELLOW) if st[0] in ("queued", "progress", "retry") else
                     QColor("#ff6b6b") if st[0] == "error" else QColor("#bdbdbd"))
            label = {"queued": "в очереди", "progress": f"{int(st[1])}%", "retry": "ещё раз…",
                     "error": "ошибка"}.get(st[0], "")
            if label:
                p.drawText(QRect(r.right() - 200, r.top(), 112, r.height()),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, label)
            else:
                ya_icon("download", 20, "#bdbdbd").paint(p, heart_r.adjusted(4, 4, -4, -4))
        else:
            liked = self.shell.is_liked(t)
            if liked or hover:
                ya_icon("heart_fill" if liked else "heart", 20, YELLOW if liked else "#9a9a9a").paint(
                    p, heart_r.adjusted(4, 4, -4, -4))                 # лайк виден всегда — в цвет оформления
        p.setFont(ya_font(12))
        p.setPen(QColor(MUTED))
        dur = float(t.get("duration") or 0)
        p.drawText(QRect(r.right() - 82, r.top(), 64, r.height()),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, _fmt(dur))
        p.restore()


class SelectionBar(QFrame):
    """Панель над списком, когда выделено несколько треков: что с ними сделать."""

    def __init__(self, shell, view, parent=None):
        super().__init__(parent)
        self.shell, self.view = shell, view
        self.setObjectName("YaSelBar")
        self.setStyleSheet("QFrame#YaSelBar{background:#2a2a2a;border-radius:12px;}")
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 6, 8, 6)
        h.setSpacing(8)
        self.lbl = QLabel("")
        self.lbl.setStyleSheet("font-weight:700;")
        h.addWidget(self.lbl)
        h.addStretch(1)
        self.b_add = QPushButton("＋ В плейлист")
        self.b_add.clicked.connect(self._add)
        self.b_remove = QPushButton("Убрать из плейлиста")
        self.b_remove.clicked.connect(lambda: self.shell.remove_rows(self.view.selected_rows()))
        self.b_delete = QPushButton("Удалить из плеера…")
        self.b_delete.setObjectName("YaYellow")
        self.b_delete.clicked.connect(lambda: self.shell.win.remove_tracks_everywhere(
            [r["t"] for r in self.view.selected_rows()], parent=self))
        self.b_clear = QPushButton("Снять выделение")
        self.b_clear.clicked.connect(self.view.clearSelection)
        for b in (self.b_add, self.b_remove, self.b_delete, self.b_clear):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            h.addWidget(b)
        self.hide()
        view.selectionModel().selectionChanged.connect(self._update)
        view.model_.modelReset.connect(self._update)

    def _update(self, *_):
        rows = self.view.selected_rows()
        n = len(rows)
        if n < 2:
            self.hide()
            return
        self.lbl.setText(f"Выделено: {n}")
        self.b_remove.setVisible(self.view._editable(rows[0]))
        self.show()

    def _add(self):
        tracks = [r["t"] for r in self.view.selected_rows()]
        m = QMenu(self)
        for name in self.shell.user_playlists():
            m.addAction(name, lambda nm=name: self.shell.win.playlist_add_tracks(nm, tracks))
        m.addSeparator()
        m.addAction("Новый плейлист…", lambda: self.shell.add_many_to_new_playlist(tracks))
        m.exec(self.b_add.mapToGlobal(self.b_add.rect().bottomLeft()))


class TrackListView(QListView):
    """Список треков в стиле Я.Музыки: клик по обложке / двойной клик —
    играть, сердце — «Мне нравится», ПКМ — меню."""

    LIVE = __import__("weakref").WeakSet()                     # все списки: findChildren по окну — сотни мс

    @staticmethod
    def refresh_visible():
        """Перерисовать видимые списки (сменился трек, пауза, лайк)."""
        for v in list(TrackListView.LIVE):
            try:
                if v.isVisible():
                    v.viewport().update()
            except RuntimeError:
                pass

    def __init__(self, shell, parent=None):
        super().__init__(parent)
        TrackListView.LIVE.add(self)
        self.shell = shell
        self.model_ = TrackModel(self)
        self.setModel(self.model_)
        self.setItemDelegate(TrackDelegate(shell, self))
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Ctrl+клик / Ctrl+Shift+клик / Ctrl+A — выделить много треков сразу (без Ctrl не выделяется — selectionCommand)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.doubleClicked.connect(lambda idx: self._play(idx))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._auto_height = False
        self._drag_from = None          # (строка, y нажатия) — для перетаскивания в плейлисте
        self._drag_on = False
        self._drop_at = -1
        self._eq_row = -1               # строка играющего трека (эквалайзер на обложке) и когда её рисовали
        self._eq_at = 0.0
        self._eq_timer = None
        from PyQt6.QtGui import QShortcut, QKeySequence
        sc = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        sc.setContext(Qt.ShortcutContext.WidgetShortcut)
        sc.activated.connect(self._delete_key)

    def eq_seen(self, row: int):
        """Делегат нарисовал эквалайзер играющей строки: дальше по кадрам обновляется только её обложка.
        Таймер сам гаснет, когда строку перестали рисовать (ушла из вида, пауза, другой трек) или анимации выключены."""
        self._eq_row, self._eq_at = row, time.monotonic()
        tm = self._eq_timer
        if tm is None:
            tm = self._eq_timer = FrameTimer(self)
            tm.setInterval(50)
            tm.timeout.connect(self._eq_tick)
        if not tm.isActive():
            import motion
            if motion.strength() > 0:
                tm.start()

    def _eq_tick(self):
        try:
            alive = self.isVisible() and time.monotonic() - self._eq_at < 0.4 and self.shell.is_playing() \
                and 0 <= self._eq_row < self.model_.rowCount()
        except RuntimeError:
            alive = False
        if not alive:
            self._eq_timer.stop()
            return
        r = self.visualRect(self.model_.index(self._eq_row))
        self.viewport().update(TrackDelegate.zones(r)[1])

    def selectionCommand(self, index, event=None):
        """Выделять треки — только с зажатым Ctrl (Ctrl+клик, Ctrl+Shift+клик — диапазон, Ctrl+A).
        Обычный клик, протягивание мышью, Shift без Ctrl и стрелки ничего не выделяют, а клик снимает выделение."""
        SF = QItemSelectionModel.SelectionFlag
        mods = event.modifiers() if event is not None and hasattr(event, "modifiers") else Qt.KeyboardModifier.NoModifier
        if mods & Qt.KeyboardModifier.ControlModifier:
            return super().selectionCommand(index, event)
        if event is not None and event.type() == QEvent.Type.MouseButtonPress:
            return SF.Clear
        return SF.NoUpdate

    def set_rows(self, rows):
        self._all_rows = list(rows)
        self._apply_rows()

    def set_filter(self, q: str):
        """Поиск внутри списка: каждое слово запроса должно быть в «исполнитель + название + альбом»."""
        self.filter_q = (q or "").strip()
        self._apply_rows()

    def set_pred(self, fn):
        """Дополнительное условие по треку (фильтры «жанр» / «настроение»); None — без условия."""
        self.pred = fn
        self._apply_rows()

    def _apply_rows(self):
        rows = getattr(self, "_all_rows", [])
        q = getattr(self, "filter_q", "")
        pred = getattr(self, "pred", None)
        if q:
            from search_util import track_matches
            rows = [r for r in rows if track_matches(q, r["t"])]
        if pred is not None:
            rows = [r for r in rows if pred(r["t"])]
        self.model_.set_rows(rows)
        if self._auto_height:
            self._section.refresh()

    def set_auto_height(self, on=True):
        """Высота по содержимому — список внутри прокручиваемой страницы."""
        self._auto_height = on
        if on:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            if not hasattr(self,'_section'):
                from track_section import TrackSection
                self._section=TrackSection(self,TrackDelegate.ROW_H)

    def section_widget(self):
        return getattr(self,'_section',self)

    def scrollTo(self,index,hint=QAbstractItemView.ScrollHint.EnsureVisible):
        if getattr(self,'_auto_height',False) and hasattr(self,'_section'):
            if index.isValid():self._section.scroll_to(index.row())
            return
        super().scrollTo(index,hint)

    def wheelEvent(self, e):
        if self._auto_height:
            e.ignore()                     # колесо — родительской странице
            return
        super().wheelEvent(e)

    def _play(self, idx):
        row = _row(idx)
        if row:
            self.shell.play_row(row)

    def selected_rows(self) -> list:
        """Выделенные строки (dict-ы модели) в порядке списка."""
        idxs = sorted({i.row() for i in self.selectionModel().selectedIndexes()})
        return [self.model_.rows[i] for i in idxs if 0 <= i < len(self.model_.rows)]

    def _editable(self, row) -> bool:
        """Строка из пользовательского плейлиста — её можно двигать/убирать."""
        return bool(row) and not getattr(self, "filter_q", "") and getattr(self, "pred", None) is None and row.get("ctx") not in ("library", None) \
            and row["ctx"] not in AUTO_PLAYLISTS and row["ctx"] in self.shell.win.playlists   # при поиске порядок не двигаем

    def mousePressEvent(self, e):
        idx = self.indexAt(e.position().toPoint())
        self._drag_from, self._drag_on = None, False
        if idx.isValid() and e.button() == Qt.MouseButton.LeftButton:
            heart, cov = TrackDelegate.zones(self.visualRect(idx))
            dots = TrackDelegate.dots_zone(self.visualRect(idx))
            pt = e.position().toPoint()
            row = _row(idx)
            if dots.contains(pt):
                self.setCurrentIndex(idx)
                self._menu(pt)
                return
            if row.get("remote") and TrackDelegate.preview_zone(self.visualRect(idx)).contains(pt):
                self.shell.preview_row(row, self)
                return
            if self._editable(row):
                self._drag_from = (idx.row(), pt.y())
            if heart.contains(pt):
                if row.get("remote"):
                    self.shell.download_remote(row, self)
                    return
                self.shell.toggle_like(row["t"])
                self.viewport().update()
                return
            if cov.contains(pt):
                if self.shell.is_current(row["t"]):
                    self.shell.win.toggle_play()
                else:
                    self.shell.play_row(row)
                self.viewport().update()
                return
            ah = TrackDelegate.album_hit(self.visualRect(idx), row)
            if ah is not None and ah.contains(pt) and not (e.modifiers() & Qt.KeyboardModifier.ControlModifier):
                self.shell.open_album(TrackDelegate.album_of(row).lower())   # клик по альбому — открыть альбом
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_from is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            y = e.position().toPoint().y()
            if not self._drag_on and abs(y - self._drag_from[1]) > 8:
                self._drag_on = True
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            if self._drag_on:
                n = self.model_.rowCount()
                tgt = int(round((y + self.verticalScrollBar().value()) / TrackDelegate.ROW_H))
                self._drop_at = max(0, min(n, tgt))
                outer=getattr(getattr(self,'_section',None),'outer',None)
                scroll=outer.verticalScrollBar() if outer is not None else self.verticalScrollBar()
                pointer_y=self.viewport().mapTo(outer.viewport(),e.position().toPoint()).y() if outer is not None else y
                visible_height=outer.viewport().height() if outer is not None else self.viewport().height()
                if pointer_y < 20:
                    scroll.setValue(scroll.value()-12)
                elif pointer_y > visible_height - 20:
                    scroll.setValue(scroll.value()+12)
                self.viewport().update()
                return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._drag_on and self._drag_from is not None:
            src = self._drag_from[0]
            dst = self._drop_at
            self._drag_from, self._drag_on, self._drop_at = None, False, -1
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.viewport().update()
            sel = sorted({i.row() for i in self.selectionModel().selectedIndexes()})
            rows = sel if (src in sel and len(sel) > 1) else [src]
            if dst >= 0 and not (len(rows) == 1 and dst in (src, src + 1)):
                ctx = self.model_.rows[src]["ctx"]
                before = sum(1 for r in rows if r < dst)       # позиция в списке без перемещаемых
                self.shell.move_rows(ctx, [self.model_.rows[r]["i"] for r in rows], dst - before)
            return
        self._drag_from = None
        super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        super().paintEvent(e)
        if self._drag_on and self._drop_at >= 0:
            p = QPainter(self.viewport())
            y = self._drop_at * TrackDelegate.ROW_H - self.verticalScrollBar().value()
            p.setPen(QPen(QColor(YELLOW), 3))
            p.drawLine(8, y, self.viewport().width() - 8, y)
            p.setBrush(QColor(YELLOW))
            p.drawEllipse(QPointF(8, y), 4, 4)
            p.end()

    def _delete_key(self):
        rows = self.selected_rows()
        if not rows:
            idx = self.currentIndex()
            if not idx.isValid():
                return
            rows = [_row(idx)]
        if self._editable(rows[0]):
            self.shell.remove_rows(rows)
        else:
            self.shell.win.remove_tracks_everywhere([r["t"] for r in rows], parent=self)

    def _menu(self, pos):
        idx = self.indexAt(pos)
        if not idx.isValid():
            return
        row = _row(idx)
        if row and row.get("remote"):
            m = QMenu(self)
            m.addAction("Послушать 30 секунд", lambda: self.shell.preview_row(row, self))
            m.addAction("Скачать", lambda: self.shell.download_remote(row, self))
            m.addAction("Скачать и слушать", lambda: self.shell.download_remote(row, self, play=True))
            m.exec(self.viewport().mapToGlobal(pos))
            return
        sel = [r for r in self.selected_rows() if not r.get("remote")]
        if len(sel) > 1 and any(r is row for r in sel):
            self._batch_menu(sel, pos)
            return
        t = row["t"]
        m = QMenu(self)
        m.addAction("Слушать", lambda: self.shell.play_row(row))
        m.addAction("Играть следующим", lambda: self.shell.win.queue_add([t], next_=True))
        m.addAction("＋  Добавить в очередь", lambda: self.shell.win.queue_add([t]))
        m.addAction("Теги, обложка и текст…", lambda: self.shell.win.edit_track_tags(t))
        self.shell.win.reveal_action(m, t)
        if row.get("ctx") != "library":
            m.addAction("Найти в коллекции", lambda: self.shell.find_in_collection(t))
        if hasattr(self.shell.win, "export_effects"):
            m.addAction("Экспорт с эффектами…", lambda: self.shell.win.export_effects([t]))
        m.addAction("Убрать из «Мне нравится»" if self.shell.is_liked(t) else "Мне нравится",
                    lambda: self.shell.toggle_like(t))
        sub = m.addMenu("Добавить в плейлист")
        for name in self.shell.user_playlists():
            sub.addAction(name, lambda n=name: self.shell.add_to_playlist(t, n))
        sub.addSeparator()
        sub.addAction("Новый плейлист…", lambda: self.shell.add_to_new_playlist(t))
        a = _artist_main(t.get("artist", ""))
        if a:
            m.addAction(f"Исполнитель: {a}", lambda: self.shell.open_artist(a))
        alb = " ".join(str(t.get("album") or "").split())
        if alb.lower() not in _NO_ALBUM and row.get("ctx") != ALBUM_PL:
            m.addAction(f"Альбом: {alb}", lambda: self.shell.open_album(alb.lower()))
        if self._editable(row):
            m.addSeparator()
            n = len(self.shell.win.playlists[row["ctx"]].get("tracks", []))
            i = row["i"]
            a = m.addAction("Выше", lambda: self.shell.move_rows(row["ctx"], [i], i - 1))
            a.setEnabled(i > 0)
            a = m.addAction("Ниже", lambda: self.shell.move_rows(row["ctx"], [i], i + 1))
            a.setEnabled(i < n - 1)
            a = m.addAction("В начало", lambda: self.shell.move_rows(row["ctx"], [i], 0))
            a.setEnabled(i > 0)
            a = m.addAction("В конец", lambda: self.shell.move_rows(row["ctx"], [i], n - 1))
            a.setEnabled(i < n - 1)
            m.addSeparator()
            m.addAction("Убрать из этого плейлиста", lambda: self.shell.remove_from_playlist(row))
        else:
            m.addSeparator()
        m.addAction("    Удалить из плеера…", lambda: self.shell.win.remove_tracks_everywhere([t], parent=self))
        m.exec(self.viewport().mapToGlobal(pos))

    def _batch_menu(self, rows, pos):
        n = len(rows)
        tracks = [r["t"] for r in rows]
        m = QMenu(self)
        sec = m.addAction(f"Выделено треков: {n}")
        sec.setEnabled(False)
        m.addAction("Слушать первый", lambda: self.shell.play_row(rows[0]))
        m.addAction(f"Играть следующими ({n})", lambda: self.shell.win.queue_add(tracks, next_=True))
        m.addAction(f"＋  Добавить в очередь ({n})", lambda: self.shell.win.queue_add(tracks))
        if hasattr(self.shell.win, "export_effects"):
            m.addAction(f"Экспорт с эффектами ({n})…", lambda: self.shell.win.export_effects(tracks))
        sub = m.addMenu(f"＋  Добавить в плейлист ({n})")
        for name in self.shell.user_playlists():
            sub.addAction(name, lambda nm=name: self.shell.win.playlist_add_tracks(nm, tracks))
        sub.addSeparator()
        sub.addAction("Новый плейлист…", lambda: self.shell.add_many_to_new_playlist(tracks))
        m.addSeparator()
        if self._editable(rows[0]):
            m.addAction(f"Убрать из этого плейлиста ({n})", lambda: self.shell.remove_rows(rows))
        m.addAction(f"    Удалить из плеера ({n})…",
                    lambda: self.shell.win.remove_tracks_everywhere(tracks, parent=self))
        m.addSeparator()
        m.addAction("Снять выделение", self.clearSelection)
        m.exec(self.viewport().mapToGlobal(pos))


# ══════════════════════════════════════════════════════════════════════════ #
#  Карточки
# ══════════════════════════════════════════════════════════════════════════ #

class Card(QWidget):
    """Квадратная обложка + подпись (или круглая — исполнитель, или «микс»)."""
    clicked = pyqtSignal()

    def __init__(self, title, subtitle="", cover="", size=150, circle=False, mix=None,
                 seed="", parent=None, mix_covers=None):
        super().__init__(parent)
        self.title, self.subtitle, self.cover = title, subtitle, cover
        size = int(round(size * DENSITY))                      # «Плотность» темы (ya_skin)
        self.size_ = size
        self.circle = circle and ARTIST_ROUND                  # форма карточек исполнителей (ya_skin)
        self._rad = (max(6.0, CARD_RADIUS * size / 150) if circle else CARD_RADIUS * size / 150)
        self.mix = mix                    # (QColor, QColor) — градиентная «подборка»
        self.mix_covers = [c for c in (mix_covers or []) if c]
        if mix and self.mix_covers:
            import ya_decor
            mc = ya_decor.mix_colors(self.mix_covers) if ya_decor.on("mix_covers") else None
            if mc:
                self.mix = mc                                  # пятна — из цветов обложек треков микса
        self.seed = seed or title
        self._hover = False
        self._appear = 1.0
        self._shown = False
        self.setFixedSize(size, size + (46 if subtitle else 30))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def showEvent(self, e):
        super().showEvent(e)
        if not self._shown:                                    # каскад появления — только при первом показе
            self._shown = True
            import ya_decor
            ya_decor.cascade(self)

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            import ya_decor
            ya_decor.card_clicked(self)                        # для «перелёта» обложки на страницу альбома
            self.clicked.emit()

    def paintEvent(self, _):
        # Карточка рисуется один раз в картинку под экран — при прокрутке каждый кадр это одно копирование,
        # без масштабирования обложки (она хранится в 2×) и раскладки текста. Перерисовка — только если
        # поменялись обложка (догрузилась), подписи, наведение или размер.
        # уже нарисована с настоящей обложкой и та же обложка — не трогаем её (иначе выкинутая из кэша
        # памяти обложка декодировалась с диска заново в кадре перехода на страницу — подвисание)
        cid = (self.cover, self.size_, self.circle, self.seed)
        if not self.mix and self.__dict__.get("_c_real") == cid:
            pm, pmk = None, self._c_pmk
        else:
            pm = None if self.mix else cover_pixmap(self.cover, self.size_, self._rad, seed=self.seed,
                                                    circle=self.circle, lazy=self)
            pmk = pm.cacheKey() if pm is not None else 0
        dpr = self.devicePixelRatioF()
        import ya_decor
        glow = self._hover and ya_decor.on("card_glow")
        key = (pmk, self.title, self.subtitle, self._hover, self.size_,
               self.circle, dpr, self.width(), self.height(), TEXT, MUTED, YELLOW, glow, ya_decor.accent().rgb())
        if key != self.__dict__.get("_ck"):
            if pm is None and not self.mix:
                pm = cover_pixmap(self.cover, self.size_, self._rad, seed=self.seed, circle=self.circle, lazy=self)
            buf = QPixmap(max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr)))
            buf.setDevicePixelRatio(dpr)
            buf.fill(Qt.GlobalColor.transparent)
            bp = QPainter(buf)
            self._paint_card(bp, pm)
            bp.end()
            self._ck, self._cbuf = key, buf
            real = bool(self.cover) and (self.cover or "", self.size_, self._rad, self.circle, "") in _COVER_CACHE
            self._c_real, self._c_pmk = (cid if real else None), pmk
        p = QPainter(self)
        if self._appear < 1.0:                                 # каскад: проявляется и чуть всплывает
            p.setOpacity(self._appear)
            p.translate(0, (1.0 - self._appear) * 12)
        p.drawPixmap(0, 0, self._cbuf)
        p.end()

    def _paint_card(self, p, pm):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        s = self.size_
        r = QRectF(0, 0, s, s)
        import ya_decor
        glow = self._hover and ya_decor.on("card_glow")
        if glow:
            ya_decor.card_glow(p, s, self.mix_covers[0] if self.mix and self.mix_covers else self.cover, self.circle)
        if self.mix:
            c1, c2 = self.mix
            path = QPainterPath(); path.addRoundedRect(r, max(4.0, self._rad + 2), max(4.0, self._rad + 2))
            p.setClipPath(path)
            p.fillRect(r, QColor(20, 20, 20))
            for (cx, cy, rad, col) in ((0.3, 0.35, 0.8, c1), (0.8, 0.75, 0.7, c2), (0.75, 0.2, 0.45, c1.lighter(130))):
                g = QRadialGradient(QPointF(cx * s, cy * s), rad * s)
                cc = QColor(col); cc.setAlpha(230)
                g.setColorAt(0, cc)
                cc2 = QColor(col); cc2.setAlpha(0)
                g.setColorAt(1, cc2)
                p.fillRect(r, g)
            if self.mix_covers and ya_decor.on("mix_covers"):
                ya_decor.mix_paint(p, s, self.mix_covers)
            p.setClipping(False)
            p.setPen(QColor(255, 255, 255))
            p.setFont(ya_font(int(s * 0.12), QFont.Weight.Black))
            p.drawText(r.adjusted(10, 10, -10, -10),
                       Qt.AlignmentFlag.AlignLeft.value | Qt.AlignmentFlag.AlignBottom.value
                       | Qt.TextFlag.TextWordWrap.value, self.title)
        else:
            p.drawPixmap(QRectF(0, 0, s, s), pm, QRectF(pm.rect()))
        if self._hover:
            path = QPainterPath()
            if self.circle:
                path.addEllipse(r)
            else:
                path.addRoundedRect(r, self._rad, self._rad)
            p.fillPath(path, QColor(0, 0, 0, 70))
            if glow:
                ya_decor.card_ring(p, r, self.cover, self.circle, self._rad)
            br = QRectF(s - 52, s - 52, 42, 42) if not self.circle else QRectF(s / 2 - 22, s / 2 - 22, 44, 44)
            p.setPen(Qt.PenStyle.NoPen)
            acc = ya_decor.accent()
            p.setBrush(acc)
            p.drawEllipse(br)
            ya_icon("play", 20, ya_decor.on_accent(acc).name()).paint(p, br.adjusted(11, 11, -10, -11).toRect())
        if not self.mix:
            p.setPen(QColor(TEXT))
            f = ya_font(13, QFont.Weight.DemiBold)
            p.setFont(f)
            al = Qt.AlignmentFlag.AlignHCenter if self.circle else Qt.AlignmentFlag.AlignLeft
            p.drawText(QRectF(0, s + 6, s, 18), al | Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(f).elidedText(self.title, Qt.TextElideMode.ElideRight, s))
            if self.subtitle:
                f2 = ya_font(12)
                p.setFont(f2)
                p.setPen(QColor(MUTED))
                p.drawText(QRectF(0, s + 25, s, 16), al | Qt.AlignmentFlag.AlignVCenter,
                           QFontMetrics(f2).elidedText(self.subtitle, Qt.TextElideMode.ElideRight, s))
        else:
            p.setPen(QColor(TEXT))
            f = ya_font(13, QFont.Weight.DemiBold)
            p.setFont(f)
            p.drawText(QRectF(0, s + 6, s, 18), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(f).elidedText(self.subtitle or "", Qt.TextElideMode.ElideRight, s))


class FlowLayout(QLayout):
    """Кнопки в ряд с переносом на новую строку, когда не помещаются (а не за край окна)."""

    def __init__(self, parent=None, hspacing=8, vspacing=8):
        super().__init__(parent)
        self._items = []
        self._hs, self._vs = hspacing, vspacing

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._do(QRect(0, 0, w, 0), True)

    def setGeometry(self, r):
        super().setGeometry(r)
        self._do(r, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        sz = QSize()
        for it in self._items:
            sz = sz.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return sz + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do(self, rect, test):
        m = self.contentsMargins()
        r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line = r.x(), r.y(), 0
        for it in self._items:
            sh = it.sizeHint()
            nx = x + sh.width() + self._hs
            if nx - self._hs > r.right() + 1 and line > 0:
                x, y = r.x(), y + line + self._vs
                nx = x + sh.width() + self._hs
                line = 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), sh))
            x = nx
            line = max(line, sh.height())
        return y + line - rect.y() + m.bottom()


class HRow(QScrollArea):
    """Горизонтальная лента карточек; колесом листается страница, ленту вбок — полосой прокрутки."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.inner = QWidget()
        self.inner.setObjectName("YaPageInner")
        self.lay = QHBoxLayout(self.inner)
        self.lay.setContentsMargins(0, 0, 0, 6)
        self.lay.setSpacing(16)
        self.lay.addStretch(1)
        self.setWidget(self.inner)
        self.setFrameShape(QFrame.Shape.NoFrame)

    def clear(self):
        while self.lay.count() > 1:
            it = self.lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def add(self, w):
        self.lay.insertWidget(self.lay.count() - 1, w)
        self.setFixedHeight(w.height() + 16)

    def wheelEvent(self, e):
        e.ignore()                         # колесо — странице; ленту вбок листают полосой прокрутки

    @property
    def widget_(self):
        return self

    def card(self, *a, **kw) -> "Card":
        c = Card(*a, **kw)
        self.add(c)
        return c


class _Clicked:
    """clicked у карточки ленты на C++: тот же connect(), что у pyqtSignal."""
    __slots__ = ("slots",)

    def __init__(self):
        self.slots = []

    def connect(self, fn):
        self.slots.append(fn)

    def emit(self):
        for fn in list(self.slots):
            fn()


class CardItem:
    """Карточка внутри NativeCardRow — данные, а не виджет. Повторяет то, что вызывающий код
    трогает у Card: clicked, cover (+update), title/subtitle; для «перелёта» обложки (ya_decor.fly_to) —
    size_, mapTo, isVisible и _cbuf."""

    def __init__(self, row, index, title, subtitle, cover, size, rad, circle, mix, mix_covers, seed):
        self.row, self.index = row, index
        self.title, self.subtitle, self._cover = title, subtitle, cover
        self.size_, self._rad, self.circle, self.mix, self.mix_covers = size, rad, circle, mix, mix_covers
        self.seed = seed or title
        self.clicked = _Clicked()
        self.hovered = _Clicked()                              # курсор на карточке (подсказка для онлайн-треков)

    @property
    def cover(self):
        return self._cover

    @cover.setter
    def cover(self, path):
        self._cover = path

    def update(self):
        """Догрузилась обложка (_CoverLoader) или поменялся cover — C++ спросит её снова при отрисовке."""
        self.row.strip.invalidate(self.index)

    def resolve(self):
        """Карточку рисуют: обложка (как Card.paintEvent — только видимым, догрузка в фоне)."""
        import ya_decor
        if not self.mix:
            self.row.strip.cover(self.index, cover_pixmap(self._cover, self.size_, self._rad, seed=self.seed,
                                                          circle=self.circle, lazy=self))
        elif self.mix_covers and ya_decor.on("mix_covers"):
            sz = int(self.size_ * 0.36)
            self.row.strip.mix_covers(self.index, [cover_pixmap(cv, sz, 6) for cv in self.mix_covers[:3]], True)

    # ya_decor.fly_to
    def isVisible(self):
        w = self.row.strip.widget
        return bool(self.row.strip.alive and w is not None and w.isVisible())

    def mapTo(self, top, pt):
        x, y = self.row.strip.card_pos(self.index)
        return self.row.strip.widget.mapTo(top, QPoint(x + pt.x(), y + pt.y()))


class NativeCardRow:
    """Лента карточек на C++ (echoes_ui.dll, tools/native_ui/card_strip.cpp): один виджет на ряд
    вместо HRow с десятками Card. Выглядит так же — рисование портировано из Card._paint_card."""

    def __init__(self, grid=False):
        import native_ui
        import ya_decor
        self.strip = native_ui.Strip(grid)
        self.items = []
        self.strip.on_click = self._click
        self.strip.on_hover = self._hover
        self.strip.on_need = lambda i: self.items[i].resolve()
        self.strip.style(QColor(TEXT), QColor(MUTED), FAMILIES,
                         ya_decor.on("cascade") and ya_decor._motion() > 0)
        _NATIVE_ROWS.add(self)

    @property
    def widget_(self):
        return self.strip.widget

    def card(self, title, subtitle="", cover="", size=150, circle=False, mix=None, seed="",
             parent=None, mix_covers=None) -> CardItem:
        import ya_decor
        size = int(round(size * DENSITY))
        rad = max(6.0, CARD_RADIUS * size / 150) if circle else CARD_RADIUS * size / 150
        circle = circle and ARTIST_ROUND
        mix_covers = [c for c in (mix_covers or []) if c]
        if mix and mix_covers:
            mc = ya_decor.mix_colors(mix_covers) if ya_decor.on("mix_covers") else None
            if mc:
                mix = mc
        i = self.strip.add(i18n_tr(title), i18n_tr(subtitle), size, rad, circle, mix)
        it = CardItem(self, i, title, subtitle, cover, size, rad, circle, mix, mix_covers, seed)
        self.items.append(it)
        return it

    def relabel(self):
        for it in self.items:
            self.strip.text(it.index, i18n_tr(it.title), i18n_tr(it.subtitle))

    def _click(self, i):
        import ya_decor
        it = self.items[i]
        it._cbuf = self.strip.card_pixmap(i)              # для «перелёта» обложки (ya_decor.fly_to)
        ya_decor.card_clicked(it)
        it.clicked.emit()

    def _hover(self, i):
        import ya_decor
        it = self.items[i]
        it.hovered.emit()
        glow = ya_decor.on("card_glow")
        acc = ya_decor.accent()
        src = it.mix_covers[0] if it.mix and it.mix_covers else it.cover
        glow_c = ya_decor.palette(src)[0][0] if (glow and src) else acc
        ring_c = ya_decor.palette(it.cover)[0][0] if (glow and it.cover) else acc
        self.strip.hover_style(i, glow, QColor(glow_c), QColor(ring_c), acc,
                               ya_icon("play", 20, ya_decor.on_accent(acc).name()))


import weakref as _weakref                                       # noqa: E402
_NATIVE_ROWS = _weakref.WeakSet()


def i18n_tr(s):
    import i18n
    return i18n.tr(s) if s else s


class NativeCardGrid(NativeCardRow):
    """CardGrid на C++: та же лента карточек, но сеткой с вертикальной прокруткой (страница «Альбомы»).
    Карточки задаются заново: clear(), card(...) на каждую, done()."""

    def __init__(self):
        super().__init__(grid=True)
        self.widget_.setStyleSheet("QScrollArea{background:transparent;border:none;}")

    def clear(self):
        self.strip.clear()
        self.items = []

    def done(self):
        self.strip.grid_done()


def card_grid():
    """Сетка карточек: на C++, если echoes_ui.dll подходит, иначе прежняя CardGrid."""
    import native_ui
    return NativeCardGrid() if native_ui.available() else CardGrid()


def card_row():
    """Лента карточек: на C++, если echoes_ui.dll подходит к этому Qt, иначе прежняя HRow."""
    import native_ui
    return NativeCardRow() if native_ui.available() else HRow()


def section_title(text, on_more=None) -> QWidget:
    w = QWidget()
    w.setObjectName("YaPageInner")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 18, 0, 8)
    lay.setSpacing(6)
    lbl = QLabel(text)
    lbl.setObjectName("YaH2")
    lay.addWidget(lbl)
    if on_more is not None:
        b = QPushButton("›")
        b.setObjectName("YaIcon")
        b.setFixedSize(26, 26)
        b.setStyleSheet("font-size:20px;color:#8a8a8a;")
        b.clicked.connect(on_more)
        lay.addWidget(b)
    lay.addStretch(1)
    return w


def chip(text, checkable=True) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("YaChip")
    b.setCheckable(checkable)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return b


def seg_group(*buttons) -> QFrame:
    """Сегментированный переключатель: тёмная капсула, внутри кнопки; выбранная — жёлтая."""
    f = QFrame()
    f.setObjectName("YaSegTrack")
    f.setFixedHeight(44)
    lay = QHBoxLayout(f)
    lay.setContentsMargins(4, 4, 4, 4)
    lay.setSpacing(2)
    for b in buttons:
        b.setObjectName("YaSeg")
        b.setFixedHeight(36)
        lay.addWidget(b)
    return f


class Switch(QAbstractButton):
    """Современный тумблер с плавным переездом ползунка."""

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(52, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._pos = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(lambda v: (setattr(self, "_pos", float(v)), self.update()))
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        off, on = QColor(70, 70, 70), QColor(YELLOW)
        t = self._pos
        col = QColor(int(off.red() + (on.red() - off.red()) * t), int(off.green() + (on.green() - off.green()) * t),
                     int(off.blue() + (on.blue() - off.blue()) * t))
        track = QPainterPath()
        track.addRoundedRect(QRectF(0, 0, W, H), H / 2, H / 2)
        p.fillPath(track, col)
        r = H - 8
        x = 4 + (W - 8 - r) * t
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0) if t > 0.5 else QColor(235, 235, 235))
        p.drawEllipse(QRectF(x, 4, r, r))
        p.end()


class Page(QScrollArea):
    """Прокручиваемая страница контента."""

    def __init__(self, parent=None, margins=(32, 22, 32, 24)):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.inner = QWidget()
        self.inner.setObjectName("YaPage")
        self.v = QVBoxLayout(self.inner)
        self.v.setContentsMargins(*margins)
        self.v.setSpacing(4)
        self.setWidget(self.inner)

    def clear(self):
        while self.v.count():
            it = self.v.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
            elif it.layout() is not None:
                _clear_layout(it.layout())


def _clear_layout(lay):
    while lay.count():
        it = lay.takeAt(0)
        if it.widget() is not None:
            it.widget().hide()
            it.widget().deleteLater()
        elif it.layout() is not None:
            _clear_layout(it.layout())


# ══════════════════════════════════════════════════════════════════════════ #
#  Логотип и мелкие виджеты
# ══════════════════════════════════════════════════════════════════════════ #

class Logo(QWidget):
    """Колючая «звезда» + ECHOES (вместо «Яндекс Музыки»). Клик — на главную («Для вас и тренды»)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(54)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("На главную")

    def _text_font(self) -> QFont:
        f = QFont(self.font())                                 # тот же строгий шрифт, что в шапке окна
        if TITLE_FAMILIES:
            f.setFamilies(TITLE_FAMILIES)
        f.setPixelSize(21)
        f.setWeight(QFont.Weight.ExtraBold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3.4)
        return f

    def sizeHint(self):
        # ширина — по настоящему шрифту: с широким шрифтом темы «ECHOES» обрезалось до «ECHOE»
        w = 48 + QFontMetrics(self._text_font()).horizontalAdvance("ECHOES") + 10
        return QSize(max(150, w), 54)

    def minimumSizeHint(self):
        return self.sizeHint()

    def changeEvent(self, e):
        if e.type() == QEvent.Type.FontChange:
            self.updateGeometry()
        super().changeEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            w = self.parentWidget()
            while w is not None and not hasattr(w, "show_page"):
                w = w.parentWidget()
            dec = getattr(w, "decor", None)
            if dec is not None and e.position().x() < 46 and dec.logo_clicked():
                return                                         # кликают по солнцу подряд — пасхалка
            if w is not None:
                w.show_page("foryou")

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        import ya_decor
        acc = ya_decor.accent()
        c = QPointF(24, 27)
        path = QPainterPath()
        n = 14
        for i in range(n * 2):
            a = i * math.pi / n - math.pi / 2
            r = 15 if i % 2 == 0 else (6.5 if i % 4 else 8.5)
            pt = QPointF(c.x() + math.cos(a) * r, c.y() + math.sin(a) * r)
            if i == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
        path.closeSubpath()
        g = QRadialGradient(c, 16)
        g.setColorAt(0, acc.lighter(150))
        g.setColorAt(0.6, acc)
        g.setColorAt(1, ya_decor.accent2())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawPath(path)
        p.setPen(acc)
        p.setFont(self._text_font())
        p.drawText(QRectF(48, 6, max(200, self.width() - 48), 42),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "ECHOES")
        p.end()


class AmbientFrame(QFrame):
    """Cached graphite liquid glass, independent of the playing track."""

    LIVE = __import__("weakref").WeakSet()                     # findChildren(AmbientFrame) по окну — сотни мс

    @staticmethod
    def live(root):
        """Стеклянные панели внутри root — без обхода всего дерева виджетов."""
        out = []
        for f in list(AmbientFrame.LIVE):
            try:
                if root is f or root.isAncestorOf(f):
                    out.append(f)
            except RuntimeError:
                pass
        return out

    def __init__(self, parent=None):
        super().__init__(parent)
        AmbientFrame.LIVE.add(self)
        self._surface = None

    def paintEvent(self, e):
        from echo_glass import liquid_surface, surface_for, surface_ready
        from ya_skin import interface_radius
        radius = interface_radius()
        if getattr(self, "_surface_radius", None) != radius:
            self._surface_radius, self._surface = radius, None
        if getattr(self, "_glass_stretch", False) and not self._glass_timer.isActive() and \
                surface_ready(self.size(), radius, self):     # чёткое стекло считается в фоне (echoes_ui.dll)
            self._glass_stretch = False                         # окно перестало меняться — чёткое стекло
            self._surface = liquid_surface(self.size(), radius)
        elif self._surface is None or self._surface.size() != self.size():
            self._surface = surface_for(self, self._surface, radius)
        p = QPainter(self)
        er, k = e.rect(), int(radius) + 1
        # скругление обрезаем, только если перерисовка задевает угол: путь размером с панель на каждый
        # маленький кусок (ползунок прокрутки, кнопка) стоил ~1–2 мс за кадр
        if radius > 0 and not (self.rect().adjusted(0, k, 0, -k).contains(er) or
                               self.rect().adjusted(k, 0, -k, 0).contains(er)):
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(self.rect()), radius, radius)
            p.setClipPath(clip)
        import ya_decor                                        # режим стекла, зерно, «погода», кант
        if ya_decor.CURRENT is not None:
            ya_decor.paint_frame(self, p, self._surface, er)
        else:
            p.drawPixmap(0, 0, self._surface)
        import wave_veil                                       # «Моя волна»: темнота и туман поверх стекла
        if wave_veil.level() > 0:
            wave_veil.paint(self, p, radius)
        p.end()


class ProgressLine(QWidget):
    """Полоска воспроизведения: скруглённая, при наведении плавно толстеет, под курсором —
    «призрак» перемотки и время в подсказке, ползунок со свечением. Клик/перетаскивание — перемотка."""
    seek_to = pyqtSignal(float)          # доля 0..1
    PAD = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(20)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.frac = 0.0
        self.dur = 0.0
        self.peaks = None                  # силуэт громкости трека (ya_decor) — рисуется волной вместо линии
        self._hover = False
        self._drag = None
        self._hx = None
        self._grow = 0.0
        self._bubble = None
        self.times = False                 # «прошло / всего» по краям полоски (show_times)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(lambda v: (setattr(self, "_grow", float(v)), self.update()))

    TIME_PAD = 60                          # место под «02:07» с каждой стороны

    def show_times(self, on=True):
        """Время по краям полоски: слева — сколько прошло, справа — длина трека. Без них позицию
        было видно только при наведении на полоску."""
        self.times = bool(on)
        self.PAD = self.TIME_PAD if on else ProgressLine.PAD
        self.update()

    def set_state(self, frac, dur):
        frac = max(0.0, min(1.0, frac))
        # 10 раз/с из таймера оболочки: перерисовать, только если ползунок сдвинулся хотя бы на полпикселя
        # (или сменилась секунда в подписи времени)
        if dur == self.dur and abs(frac - self.frac) * max(1, self.width() - 2 * self.PAD) < 0.5 \
                and not (self.times and int(frac * dur) != int(self.frac * dur)):
            return
        self.frac = frac
        self.dur = dur
        self.update()

    def _animate(self, to):
        import motion
        self._anim.stop()
        if motion.strength() <= 0:
            self._grow=to
            self.update()
            return
        self._anim.setDuration(150)
        self._anim.setStartValue(self._grow)
        self._anim.setEndValue(to)
        self._anim.start()

    def _f(self, x):
        return max(0.0, min(1.0, (x - self.PAD) / max(1, self.width() - 2 * self.PAD)))

    def enterEvent(self, e):
        self._hover = True
        self._animate(1.0)

    def leaveEvent(self, e):
        self._hover = False
        self._hx = None
        if self._drag is None:
            self._animate(0.0)
        if self._bubble is not None:
            self._bubble.hide_now()
        self.update()

    def mouseMoveEvent(self, e):
        self._hx = e.position().x()
        if self._drag is not None:
            self._drag = self._f(self._hx)
        if self.dur > 0:
            from seekbar import TimeBubble
            if self._bubble is None:
                self._bubble = TimeBubble()
            self._bubble.show_at(self.mapToGlobal(QPoint(int(self._hx), 0)), _fmt(self._f(self._hx) * self.dur))
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = self._f(e.position().x())
            self._animate(1.0)
            self.update()

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self.seek_to.emit(self._drag)
            self.frac = self._drag
            self._drag = None
            if not self._hover:
                self._animate(0.0)
            self.update()

    def _paint_wave(self, p, x0, x1, H, frac, g, acc):
        """Волна громкости: пройденное — акцентом, под курсором — «призрак» перемотки."""
        pk = self.peaks
        n = max(8, int((x1 - x0) / 3))
        fx = x0 + (x1 - x0) * frac
        hx = None if self._hx is None or self._drag is not None else max(x0, min(x1, self._hx))
        top = acc.lighter(115)
        for i in range(n):
            v = pk[min(len(pk) - 1, int(i * len(pk) / n))]
            x = x0 + i * (x1 - x0) / n
            bh = 2.5 + v * (9 + 7 * g)
            if x < fx:
                c = QColor(top) if g >= 0.05 else QColor(255, 255, 255, 225)
            elif hx is not None and x < hx:
                c = QColor(255, 255, 255, 95)
            else:
                c = QColor(255, 255, 255, 52)
            p.setBrush(c)
            p.drawRoundedRect(QRectF(x, (H - bh) / 2, 2, bh), 1, 1)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        import ya_decor
        acc = ya_decor.accent()
        W, H = self.width(), self.height()
        g = self._grow
        h = 4 + 4 * g
        y = (H - h) / 2
        x0, x1 = self.PAD, W - self.PAD
        p.setPen(Qt.PenStyle.NoPen)
        frac = self._drag if self._drag is not None else self.frac
        fx = x0 + (x1 - x0) * frac
        if self.times and self.dur > 0:                         # «прошло» слева, «всего» справа
            p.setFont(ya_font(11, QFont.Weight.DemiBold))
            p.setPen(QColor(255, 255, 255, 235 if (self._hover or self._drag is not None) else 150))
            p.drawText(QRectF(0, 0, x0 - 10, H), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       _fmt(frac * self.dur))
            p.setPen(QColor(255, 255, 255, 150))
            p.drawText(QRectF(x1 + 10, 0, W - x1 - 10, H), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       _fmt(self.dur))
            p.setPen(Qt.PenStyle.NoPen)
        if getattr(self, "moments", None):                      # метки реакций друзей на моменты трека
            import net_moments
            net_moments.paint_marks(self, p, x0, x1, H)
        if self.peaks and ya_decor.on("wave_bar"):
            self._paint_wave(p, x0, x1, H, frac, g, acc)
            r = 5.5 * g
            if r > 0.5:
                p.setBrush(QColor("#ffffff"))
                p.drawEllipse(QPointF(fx, H / 2), r, r)
            p.end()
            return
        p.setBrush(QColor(255, 255, 255, 38))
        p.drawRoundedRect(QRectF(x0, y, x1 - x0, h), h / 2, h / 2)
        if self._hx is not None and self._drag is None:
            hx = max(x0, min(x1, self._hx))
            if hx > fx:
                p.setBrush(QColor(255, 255, 255, 45))
                p.drawRoundedRect(QRectF(x0, y, hx - x0, h), h / 2, h / 2)
        if frac > 0:
            gr = QLinearGradient(x0, 0, max(x0 + 1, fx), 0)
            gr.setColorAt(0.0, QColor(255, 255, 255, 235) if g < 0.05 else acc)
            gr.setColorAt(1.0, QColor(255, 255, 255, 235) if g < 0.05 else ya_decor.accent2())
            if g >= 0.05:
                p.setBrush(gr)
            else:
                p.setBrush(QColor(255, 255, 255, 225))
            p.drawRoundedRect(QRectF(x0, y, max(h, fx - x0), h), h / 2, h / 2)
        r = 6.5 * g
        if r > 0.5:
            glow = QRadialGradient(QPointF(fx, H / 2), r * 2.6)
            c = QColor(acc); c.setAlpha(int(120 * g))
            glow.setColorAt(0.0, c)
            c.setAlpha(0)
            glow.setColorAt(1.0, c)
            p.setBrush(glow)
            p.drawEllipse(QPointF(fx, H / 2), r * 2.6, r * 2.6)
            p.setBrush(QColor("#ffffff"))
            p.drawEllipse(QPointF(fx, H / 2), r, r)
        p.end()


class RoundCover(QLabel):
    def __init__(self, size, radius=6, parent=None):
        super().__init__(parent)
        self.size_, self.radius = size, radius
        self.setFixedSize(size, size)
        self._path = None

    def set_cover(self, path, seed=""):
        if path == self._path and seed == getattr(self,'_seed',None):
            return
        self._path = path
        self._seed = seed
        self.setPixmap(cover_pixmap(path or "", self.size_, self.radius, seed=seed))


# ══════════════════════════════════════════════════════════════════════════ #
#  «Моя волна»: живой фон-пятно
# ══════════════════════════════════════════════════════════════════════════ #

# ══════════════════════════════════════════════════════════════════════════ #
#  Оболочка
# ══════════════════════════════════════════════════════════════════════════ #

MOODS = [
    ("energy", "Бодрое", lambda pr: pr["energy"], True),
    ("calm", "Спокойное", lambda pr: pr["energy"], False),
    ("happy", "Весёлое", lambda pr: pr["valence"], True),
    ("sad", "Грустное", lambda pr: pr["valence"], False),
]


def _plural(n, one, few, many):
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


class CardGrid(QScrollArea):
    """Сетка карточек, сама подстраивает число колонок под ширину."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self.inner = QWidget(); self.inner.setObjectName("YaPage")
        self.grid = QGridLayout(self.inner)
        self.grid.setContentsMargins(0, 6, 0, 6)
        self.grid.setHorizontalSpacing(22)
        self.grid.setVerticalSpacing(20)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setWidget(self.inner)
        self.cards = []
        self._cols = 0

    @property
    def widget_(self):
        return self

    # тот же интерфейс, что у NativeCardGrid
    def clear(self):
        self._pending = []

    def card(self, *a, **kw) -> "Card":
        c = Card(*a, **kw)
        self.__dict__.setdefault("_pending", []).append(c)
        return c

    def done(self):
        self.set_cards(self.__dict__.pop("_pending", []))

    def set_cards(self, cards):
        for c in self.cards:
            c.setParent(None)
            c.deleteLater()
        self.cards = list(cards)
        self._cols = 0
        self._relayout()
        self.verticalScrollBar().setValue(0)

    def _relayout(self):
        if not self.cards:
            return
        cw = self.cards[0].width() + self.grid.horizontalSpacing()
        cols = max(1, (self.viewport().width() + self.grid.horizontalSpacing()) // max(1, cw))
        if cols == self._cols and all(c.parent() is self.inner for c in self.cards):
            return
        self._cols = cols
        for c in self.cards:
            self.grid.removeWidget(c)
        for i, c in enumerate(self.cards):
            self.grid.addWidget(c, i // cols, i % cols)
            c.show()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()


_LIKED_PM: dict = {}


def liked_cover(size: int, radius: float = 9) -> QPixmap:
    """Обложка «Мне нравится»: глянцевое заполненное сердце с бликом на тёплом градиенте — сразу видно, что это
    любимое, и не похоже на контурное сердце коллекции."""
    key = (size, radius, YELLOW)
    pm = _LIKED_PM.get(key)
    if pm is not None:
        return pm
    dpr = 2.0
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = QRectF(0, 0, size, size)
    clip = QPainterPath()
    clip.addRoundedRect(r, radius, radius)
    p.setClipPath(clip)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor("#ff5fa2"))
    g.setColorAt(0.55, QColor("#c13cff"))
    g.setColorAt(1, QColor("#5b3cff"))
    p.fillRect(r, g)
    glow = QRadialGradient(QPointF(size * 0.3, size * 0.22), size * 0.7)
    glow.setColorAt(0, QColor(255, 255, 255, 90))
    glow.setColorAt(1, QColor(255, 255, 255, 0))
    p.fillRect(r, glow)
    s = size * 0.56
    x0, y0 = (size - s) / 2, size * 0.25
    heart = QPainterPath()
    heart.moveTo(x0 + s / 2, y0 + s * 0.95)
    heart.cubicTo(x0 - s * 0.15, y0 + s * 0.45, x0 + s * 0.05, y0 - s * 0.12, x0 + s / 2, y0 + s * 0.22)
    heart.cubicTo(x0 + s * 0.95, y0 - s * 0.12, x0 + s * 1.15, y0 + s * 0.45, x0 + s / 2, y0 + s * 0.95)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawPath(heart.translated(0, size * 0.03))
    p.setBrush(QColor("#ffffff"))
    p.drawPath(heart)
    p.setBrush(QColor(255, 255, 255, 110))                    # искорка
    c = QPointF(size * 0.8, size * 0.24)
    star = QPainterPath()
    for i, k in enumerate((1, 0.3, 1, 0.3, 1, 0.3, 1, 0.3)):
        import math as _m
        a = _m.pi / 4 * i
        pt = QPointF(c.x() + _m.cos(a) * size * 0.09 * k, c.y() + _m.sin(a) * size * 0.09 * k)
        star.moveTo(pt) if i == 0 else star.lineTo(pt)
    star.closeSubpath()
    p.drawPath(star)
    p.end()
    _LIKED_PM[key] = pm
    return pm


class PlaylistStrip(QWidget):
    """Плитки плейлистов в верхней панели: частые — первыми; сколько влезает по ширине, остальное — «⋯»."""

    TILE = 46
    GAP = 8

    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.setObjectName("YaSide")
        self.setMinimumWidth(self.TILE + 60)
        self.h = QHBoxLayout(self)
        self.h.setContentsMargins(0, 0, 0, 0)
        self.h.setSpacing(self.GAP)
        self.more = QPushButton("⋯", self)
        self.more.setObjectName("YaPlMore")
        self.more.setFixedSize(self.TILE, self.TILE)
        self.more.setToolTip("Все плейлисты")
        self.more.setCursor(Qt.CursorShape.PointingHandCursor)
        self.more.clicked.connect(self.open_all)
        self._fit = -1

    def _capacity(self) -> int:
        return max(0, (self.width() - self.TILE - self.GAP) // (self.TILE + self.GAP))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._capacity() != self._fit:
            QTimer.singleShot(0, self.refresh)

    def refresh(self):
        sh = self.shell
        while self.h.count():
            it = self.h.takeAt(0)
            w_ = it.widget()
            if w_ is not None and w_ is not self.more:
                w_.deleteLater()
        self._fit = self._capacity()
        for n in sh.playlists_by_usage()[:self._fit]:
            pl = sh.win.playlists.get(n) or {}
            tr = pl.get("tracks", [])
            cov = pl.get("cover") or (tr[0].get("cover", "") if tr else "")
            b = QPushButton(self)
            b.setObjectName("YaPlTile")
            b.setFixedSize(self.TILE, self.TILE)
            b.setIcon(QIcon(liked_cover(self.TILE - 2, 9) if n == LIKED and not pl.get("cover")
                            else cover_pixmap(cov, self.TILE - 2, 9, seed=n)))
            b.setIconSize(QSize(self.TILE - 2, self.TILE - 2))
            b.setToolTip(f"{n} · {len(tr)} {_plural(len(tr), 'трек', 'трека', 'треков')}")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, n=n: sh.open_playlist(n))
            b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda pos, n=n, b=b: self._menu(n, b.mapToGlobal(pos)))
            self.h.addWidget(b)
        self.h.addWidget(self.more)
        self.h.addStretch(1)

    def _menu(self, name, gpos):
        sh = self.shell
        m = QMenu(self)
        m.addAction("Открыть", lambda: sh.open_playlist(name))
        if name != LIKED:
            m.addAction("Переименовать…", lambda: sh.win._pd_rename(name))
            m.addSeparator()
            m.addAction("Удалить плейлист", lambda: sh._delete_playlist(name))
        m.exec(gpos)

    def open_all(self):
        PlaylistPopup(self.shell, self.more).show()


class PlaylistPopup(QFrame):
    """«⋯»: маленькое окошко со всеми плейлистами (частые первыми), поиском и «Создать плейлист»."""

    def __init__(self, shell, anchor):
        super().__init__(shell.win, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.NoDropShadowWindowHint)
        self.shell = shell
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        from echo_glass import GlassFrame
        box = GlassFrame(self, 16)
        box.setObjectName("YaPlPop")
        box.setStyleSheet("QFrame#YaPlPop{background:transparent;border:none;} QLabel{background:transparent;}")
        outer.addWidget(box)
        v = QVBoxLayout(box)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)
        head = QHBoxLayout()
        t = QLabel("Плейлисты", box)
        t.setStyleSheet("font-size:15px;font-weight:800;")
        head.addWidget(t, 1)
        nb = QPushButton("  Создать", box)
        nb.setObjectName("YaChip")
        nb.setIcon(ya_icon("plus", 14, "#e6e6e6"))
        nb.clicked.connect(lambda: (self.close(), shell.new_playlist()))
        head.addWidget(nb)
        v.addLayout(head)
        self.q = QLineEdit(box)
        self.q.setPlaceholderText("Найти плейлист…")
        v.addWidget(self.q)
        self.lst = QListWidget(box)
        self.lst.setIconSize(QSize(40, 40))
        self.lst.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.lst.setStyleSheet("QListWidget{background:transparent;border:none;}"
                               "QListWidget::item{padding:5px 4px;border-radius:8px;font-size:12px;font-weight:600;}"
                               "QListWidget::item:hover{background:#1e1e21;}")
        self.lst.itemClicked.connect(lambda it: (self.close(), shell.open_playlist(it.data(Qt.ItemDataRole.UserRole))))
        v.addWidget(self.lst, 1)
        usage = shell.win.settings.get("pl_usage") or {}
        for n in shell.playlists_by_usage():
            pl = shell.win.playlists.get(n) or {}
            tr = pl.get("tracks", [])
            cov = pl.get("cover") or (tr[0].get("cover", "") if tr else "")
            sub = f"{len(tr)} {_plural(len(tr), 'трек', 'трека', 'треков')}" + \
                (" · часто слушаете" if int(usage.get(n, 0)) >= 5 else "")
            it = QListWidgetItem(QIcon(liked_cover(40, 7) if n == LIKED and not pl.get("cover")
                                       else cover_pixmap(cov, 40, 7, seed=n)), f"{n}\n{sub}")
            it.setData(Qt.ItemDataRole.UserRole, n)
            self.lst.addItem(it)
        self.q.textChanged.connect(self._filter)
        self.resize(320, 430)
        g = anchor.mapToGlobal(anchor.rect().bottomLeft())
        scr = anchor.screen().availableGeometry()
        x = min(max(scr.left() + 8, g.x() - 140), scr.right() - self.width() - 8)
        self.move(x, g.y() + 8)
        QTimer.singleShot(0, self.q.setFocus)

    def _filter(self, text):
        t = text.strip().lower()
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            it.setHidden(bool(t) and t not in str(it.data(Qt.ItemDataRole.UserRole)).lower())


class PlayerMorePopup(QFrame):
    """«Ещё» в нижнем плеере: всё, что раньше стояло в ряд значками без подписей, — списком «значок + название»
    (и сочетание клавиш справа). Пункты даёт YaShell.player_more_items()."""

    def __init__(self, shell, anchor):
        super().__init__(shell.win, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.NoDropShadowWindowHint)
        self.shell = shell
        self.buttons = {}                                      # ключ пункта → кнопка
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        from echo_glass import GlassFrame
        from ya_skin import interface_radius
        box = GlassFrame(self, max(8, min(18, interface_radius(16))))
        box.setObjectName("YaMorePop")
        box.setStyleSheet(
            "QFrame#YaMorePop{background:transparent;border:none;} QLabel{background:transparent;}"
            "QPushButton#YaMoreItem{background:transparent;border:none;border-radius:10px;padding:0 12px;"
            f"text-align:left;font-size:13px;font-weight:600;color:{TEXT};}}"
            "QPushButton#YaMoreItem:hover{background:rgba(255,255,255,0.09);}"
            "QPushButton#YaMoreItem:pressed{background:rgba(255,255,255,0.15);}")
        outer.addWidget(box)
        v = QVBoxLayout(box)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(2)
        for it in shell.player_more_items():
            b = QPushButton("   " + it["text"], box)
            b.setObjectName("YaMoreItem")
            b.setIcon(it["icon"] if isinstance(it["icon"], QIcon) else ya_icon(it["icon"], 20, "#e6e6e6"))
            b.setIconSize(QSize(20, 20))
            b.setFixedHeight(40)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            if it.get("tip"):
                b.setToolTip(it["tip"])
            if it.get("hint"):                                 # сочетание клавиш — справа, приглушённо
                hl = QHBoxLayout(b)
                hl.setContentsMargins(0, 0, 12, 0)
                hl.addStretch(1)
                k = QLabel(it["hint"], b)
                k.setStyleSheet(f"font-size:11px;font-weight:600;color:{MUTED};")
                k.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                hl.addWidget(k)
            b.clicked.connect(lambda _=False, key=it["key"]: self.trigger(key))
            self.buttons[it["key"]] = b
            v.addWidget(b)
        self.resize(312, 16 + len(self.buttons) * 42 - 2)
        g = anchor.mapToGlobal(anchor.rect().topRight())
        scr = anchor.screen().availableGeometry()
        x = min(max(scr.left() + 8, g.x() - self.width() + 6), scr.right() - self.width() - 8)
        self.move(x, max(scr.top() + 8, g.y() - self.height() - 10))

    def showEvent(self, e):
        super().showEvent(e)
        import motion
        if motion.strength() <= 0:
            return
        end = self.pos()                                       # окошко «выныривает» из-под кнопки
        a = self._in_anim = QVariantAnimation(self)
        a.setDuration(motion.duration(180))
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setWindowOpacity(0.0)
        a.valueChanged.connect(lambda v: (self.setWindowOpacity(float(v)),
                                          self.move(end.x(), end.y() + int(round((1.0 - float(v)) * 16)))))
        a.start()

    def trigger(self, key):
        """Нажатие на пункт: окошко закрывается, действие — следующим шагом (оно само может открыть меню/панель)."""
        fn = next((it["fn"] for it in self.shell.player_more_items() if it["key"] == key), None)
        self.close()
        if fn is not None:
            QTimer.singleShot(0, fn)

    def closeEvent(self, e):
        self.shell._more_closed_at = time.monotonic()
        if self.shell.__dict__.get("_more_pop") is self:
            self.shell._more_pop = None
        super().closeEvent(e)


class NetCornerArt(QWidget):
    """Рисунок угловой кнопки Echoes.NET: значок «эхо» и подпись (поверх кнопки, клики проходят насквозь)."""

    def __init__(self, btn):
        super().__init__(btn)
        self.btn = btn
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        btn.installEventFilter(self)
        self.setGeometry(btn.rect())

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.Resize:
            self.setGeometry(self.btn.rect())
        elif ev.type() in (QEvent.Type.Enter, QEvent.Type.Leave):
            self.update()
        return False

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        on = self.btn.isChecked() or self.btn.underMouse()
        acc = QColor(YELLOW)
        cx, cy = W / 2, H / 2 - 9
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(acc)
        p.drawEllipse(QPointF(cx, cy), 4.2, 4.2)
        for i, r in enumerate((10.0, 17.0)):
            c = QColor(acc) if on else QColor("#e6e6e6")
            c.setAlpha(255 if i == 0 else 170)
            p.setPen(QPen(c, 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.setBrush(Qt.BrushStyle.NoBrush)
            rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
            p.drawArc(rect, int(-42 * 16), int(84 * 16))
            p.drawArc(rect, int(138 * 16), int(84 * 16))
        p.setFont(ya_font(11, QFont.Weight.Black))
        p.setPen(QColor("#ffffff") if on else QColor("#d6d6d6"))
        p.drawText(QRectF(0, H - 28, W, 18), Qt.AlignmentFlag.AlignHCenter, "Echoes.NET")
        p.end()


LYR_GLASS_BTN = ("QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(255,255,255,0.26),"
                 "stop:0.5 rgba(255,255,255,0.12),stop:1 rgba(255,255,255,0.18));"
                 "color:#ffffff;border:1px solid rgba(255,255,255,0.32);border-top-color:rgba(255,255,255,0.55);"
                 "border-bottom-color:rgba(255,255,255,0.18);border-radius:18px;padding:0 14px;font-weight:800;}"
                 "QPushButton:hover{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(255,255,255,0.36),"
                 "stop:1 rgba(255,255,255,0.22));border-color:rgba(255,255,255,0.6);}"
                 "QPushButton:pressed{background:rgba(255,255,255,0.10);}")   # кнопки над текстом песни

SIDE_W = 236                                                   # боковая панель разделов (новый вид)


class YaShell(QWidget):
    """Весь интерфейс темы. win — MainWindow."""

    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        self.setObjectName("YaShell")
        self._track_key = None
        self._lib_sig = None
        self._pl_sig = None
        self._dirty = set()
        self._history: list[int] = []
        self._profiles = None
        self._settings_host = None
        self._lyr_src = None
        self._wave_kind = None
        self._coll_filter = ("all", None)

        self._layout_mode = win.settings.get("ya_layout", "new")
        self._build_nav_common(win)
        if self._layout_mode == "classic":
            self._layout_classic(win)
        else:
            self._layout_new(win)

        # ── страницы ──
        self.pages = {}
        self.pages["search"] = self._build_search()
        self.pages["wave"] = self._build_wave()
        self.pages["foryou"] = Page()
        self.pages["collection"] = self._build_collection()
        self.pages["albums"] = self._build_albums()
        from music_tierlist import MusicTierPage
        self.pages["tierlist"] = MusicTierPage(self)
        self.pages["playlist"] = self._build_playlist_page()
        self.pages["lyrics"] = self._build_lyrics()
        self.pages["settings"] = self._build_settings()
        self.pages["artist"] = ArtistPage(self)
        from ya_profile import ProfilePage
        self.pages["profile"] = ProfilePage(self)
        from ya_queue import QueuePage
        self.pages["queue"] = QueuePage(self)
        from music_duel import DuelPage
        self.pages["duel"] = DuelPage(self)
        from ya_follows import FollowsPage                     # подписки на исполнителей и их новые релизы
        self.pages["follows"] = FollowsPage(self)
        import artist_follow
        if getattr(win, "_release_watch", None) is None:
            win._release_watch = artist_follow.ReleaseWatcher(win)
        from net_page import NetPage
        self.pages["net"] = NetPage(self)
        for k, w in self.pages.items():
            self.stack.addWidget(w)
        self._cur_page = None
        self._prev_page = "foryou"

        self._lib_sig = len(win.library)
        _artist_index(win.library)
        self._pl_sig = tuple((n, len(p.get("tracks", []))) for n, p in win.playlists.items())
        import ya_decor                                        # живое оформление: акцент, аура, волна, пластинка
        self.decor = ya_decor.Decor(self)
        # Изменившиеся страницы, на которых вас нет, — пересобрать заранее, в простое: иначе «Для вас»
        # (рекомендации пришли во время загрузки) пересобиралась ~200 мс прямо в момент первого перехода
        self._last_nav = 0.0
        self._idle_rb = QTimer(self)
        self._idle_rb.setInterval(1500)
        self._idle_rb.timeout.connect(self._idle_rebuild)
        self._idle_rb.start()
        QTimer.singleShot(2000, lambda: __import__("overlay_live").apply(win))   # игровой оверлей (если включён)
        QTimer.singleShot(3000, lambda: __import__("ya_weather").install(win))   # погода за окном (если включена)
        QTimer.singleShot(3000, lambda: __import__("ya_auto").get(win))          # автоматика (правила)
        __import__("ya_voice").install(win)                                    # голосовые команды (если включены)
        self.nav.buttonClicked.connect(lambda _b: ya_decor.ui_click())
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self.refresh_sidebar()
        self.show_page(win.settings.get("ya_page", "foryou") if win.settings.get("ya_page") in
                       ("search", "wave", "foryou", "collection", "albums", "tierlist") else "foryou")


    def _layout_classic(self, win):
        """Прежняя раскладка: слева логотип, вкладки, плейлисты и профиль; справа контент и плеер."""
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 10, 10)
        root.setSpacing(0)

        # ── левая колонка ──
        side = QWidget(); side.setObjectName("YaSide")
        side.setFixedWidth(210)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(14, 12, 10, 0)
        sv.setSpacing(2)
        self._logo = Logo()
        sv.addWidget(self._logo)
        sv.addSpacing(10)
        for key in ("search", "wave", "foryou", "collection", "albums", "follows", "tierlist", "duel", "net",
                    "settings"):
            b = self._nav_btns[key]
            b.setText("  " + self.NAV_TEXT[key])
            sv.addWidget(b)
        self._badge_on(self._nav_btns["net"])
        sv.addSpacing(14)
        new_pl = QPushButton("  Создать плейлист")
        new_pl.setObjectName("YaNav")
        new_pl.setIcon(ya_icon("plus", 18, "#e6e6e6"))
        new_pl.setIconSize(QSize(18, 18))
        new_pl.setCursor(Qt.CursorShape.PointingHandCursor)
        new_pl.clicked.connect(self.new_playlist)
        sv.addWidget(new_pl)
        self.pl_side.setStyleSheet("QListWidget::item{padding:5px 4px;font-size:12px;font-weight:600;}")
        sv.addWidget(self.pl_side, 1)
        # профиль
        prof = QWidget(); prof.setObjectName("YaSide")
        pl = QHBoxLayout(prof)
        pl.setContentsMargins(4, 8, 0, 14)
        pl.setSpacing(10)
        col = QVBoxLayout(); col.setSpacing(0); col.addWidget(self.nick); col.addWidget(self.status)
        pl.addWidget(self.avatar); pl.addLayout(col, 1)
        tb = icon_button("palette", "Сменить тему", 30, 18, "#cfcfcf")
        tb.clicked.connect(lambda: win._winamp_theme_menu(tb.mapToGlobal(tb.rect().topLeft())))
        pl.addWidget(tb)
        prof.mousePressEvent = lambda e: win._open_profile()
        sv.addWidget(prof)
        root.addWidget(side)

        # ── правая часть: контент + плеер ──
        right = QWidget(); right.setObjectName("YaSide")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 10, 0, 0)
        rv.setSpacing(8)
        self.content = AmbientFrame(); self.content.setObjectName("YaContent")
        cl = QVBoxLayout(self.content)
        cl.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        cl.addWidget(self.stack)
        rv.addWidget(self.content, 1)
        rv.addWidget(self._build_player())
        root.addWidget(right, 1)



    NAV_TEXT = {"search": "Поиск", "wave": "Моя волна", "foryou": "Для вас и тренды", "collection": "Коллекция",
                "albums": "Альбомы", "follows": "Подписки", "tierlist": "Тирлист музыки", "duel": "Дуэль треков", "net": "Echoes.NET",
                "settings": "Настройки и звук"}
    NAV_ICON = {"search": "search", "wave": "wave", "foryou": "note", "collection": "collection", "albums": "album",
                "follows": "users",
                "tierlist": "tier", "duel": "duel", "net": "net", "settings": "settings"}

    def _build_nav_common(self, win):
        """Кнопки разделов (общие для обеих раскладок), список плейлистов, профиль, счётчик Echoes.NET."""
        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        self._nav_btns = {}
        for key in ("search", "wave", "foryou", "collection", "albums", "follows", "tierlist", "duel", "net",
                    "settings"):
            ic = self.NAV_ICON[key]
            b = QPushButton()
            b.setObjectName("YaNav")
            icon = QIcon(ya_icon(ic, 18, "#e6e6e6"))            # выбранная вкладка — жёлтая иконка
            icon.addPixmap(ya_icon(ic, 18, YELLOW).pixmap(18, 18), QIcon.Mode.Normal, QIcon.State.On)
            b.setIcon(icon)
            b.setIconSize(QSize(18, 18))
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setToolTip(self.NAV_TEXT[key])
            b.clicked.connect(lambda _=False, k=key: self.show_page(k))
            self.nav.addButton(b)
            self._nav_btns[key] = b
        self.net_badge = QLabel("")
        self.net_badge.setObjectName("YaBadge")
        self.net_badge.setFixedHeight(18)
        self.net_badge.hide()
        self.pl_side = QListWidget()                           # список плейлистов (классика; в новой — данные)
        self.pl_side.setIconSize(QSize(36, 36))
        self.pl_side.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.pl_side.itemClicked.connect(lambda it: self.open_playlist(it.data(Qt.ItemDataRole.UserRole)))
        self.pl_side.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.pl_side.customContextMenuRequested.connect(self._side_menu)
        self.pl_side.setToolTip("Клик — открыть плейлист · правая кнопка — переименовать, удалить")
        self.avatar = QLabel(); self.avatar.setFixedSize(36, 36)
        self.nick = QLabel(""); self.nick.setStyleSheet("font-weight:700;font-size:12px;")
        self.status = QLabel(""); self.status.setObjectName("YaSub")

    def _badge_on(self, btn):
        """Счётчик непрочитанного Echoes.NET — в правый край кнопки."""
        bl = QHBoxLayout(btn)
        if btn.width() <= 60:                                  # круглая кнопка в шапке — значок в правый верхний угол
            bl.setContentsMargins(0, 0, 0, 0)
            bl.addStretch(1)
            bl.addWidget(self.net_badge, 0, Qt.AlignmentFlag.AlignTop)
            return
        bl.setContentsMargins(0, 0, 8, 0)
        bl.addStretch(1)
        bl.addWidget(self.net_badge)

    def _layout_new(self, win):
        """Новая раскладка: сверху — логотип, плейлисты (частые первыми), коллекция, поиск, профиль;
        сбоку (справа или слева) — разделы; снизу — «сменить тему», плеер, Echoes.NET в углу."""
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 4, 10, 10)
        root.setSpacing(8)
        # ── верх ──
        top = AmbientFrame(); top.setObjectName("YaTopBar")
        top.setFixedHeight(66)
        th = QHBoxLayout(top)
        th.setContentsMargins(8, 0, 14, 0)
        th.setSpacing(10)
        self._logo = Logo()
        th.addWidget(self._logo)
        th.addSpacing(6)
        coll = self._nav_btns["collection"]                    # коллекция — первой плиткой рядом с плейлистами
        coll.setObjectName("YaTopTile")
        coll.setText("")
        coll.setFixedSize(46, 46)
        coll.setIconSize(QSize(22, 22))
        th.addWidget(coll)
        self.pl_strip = PlaylistStrip(self)
        th.addWidget(self.pl_strip, 1)
        srch = self._nav_btns["search"]
        srch.setObjectName("YaTopRound")
        srch.setText("")
        srch.setFixedSize(44, 44)
        srch.setIconSize(QSize(20, 20))
        th.addWidget(srch)
        from duel_settings import tr as _duel_tr
        # режим геймера — кнопкой в Настройках → Производительность (performance_ui) или сам, когда запущена игра;
        # здесь кнопка остаётся вне окна, чтобы подсказки и состояние режима работали как раньше
        self.gamer_btn = QPushButton()
        self.gamer_btn.setObjectName("YaTopRound")
        self.gamer_btn.setCheckable(True)
        self.gamer_btn.setFixedSize(44, 44)
        self.gamer_btn.setIconSize(QSize(22, 22))
        self.gamer_btn.setIcon(ya_icon("gamepad", 22))
        self.gamer_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gamer_btn.setToolTip(_duel_tr(win, "Режим геймера: ECHOES только играет музыку и не мешает игре",
                                           "Gamer mode: ECHOES only plays music and stays out of the game's way"))
        self.gamer_btn.clicked.connect(self._gamer_clicked)
        QTimer.singleShot(1200, self._gamer_setup)
        # Echoes.NET — круглой кнопкой там, где был геймпад; жучок «сообщить об ошибке» — только внутри Echoes.NET
        net = self._nav_btns["net"]
        net.setObjectName("YaTopRound")
        net.setText("")
        net.setFixedSize(44, 44)
        net.setIcon(ya_icon("net", 22))
        net.setIconSize(QSize(22, 22))
        net.setToolTip("Echoes.NET — друзья, сообщения, звонки, лента")
        self._badge_on(net)
        th.addWidget(net)
        th.addSpacing(10)
        prof = QWidget(); prof.setObjectName("YaSide")
        prof.setCursor(Qt.CursorShape.PointingHandCursor)
        prof.setToolTip("Мой профиль")
        ph = QHBoxLayout(prof)
        ph.setContentsMargins(4, 0, 0, 0)
        ph.setSpacing(10)
        col = QVBoxLayout(); col.setSpacing(0)
        col.addStretch(1); col.addWidget(self.nick, 0, Qt.AlignmentFlag.AlignRight)
        col.addWidget(self.status, 0, Qt.AlignmentFlag.AlignRight); col.addStretch(1)
        ph.addLayout(col)
        self.avatar.setFixedSize(40, 40)
        ph.addWidget(self.avatar)
        prof.mousePressEvent = lambda e: win._open_profile()
        th.addWidget(prof)
        root.addWidget(top)
        # ── середина: контент + разделы ──
        mid = QHBoxLayout()
        mid.setSpacing(10)
        self.content = AmbientFrame(); self.content.setObjectName("YaContent")
        cl = QVBoxLayout(self.content)
        cl.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        cl.addWidget(self.stack)
        side = AmbientFrame(); side.setObjectName("YaSideNav")
        side.setFixedWidth(SIDE_W)
        self._side_nav = side
        sv = QVBoxLayout(side)
        sv.setContentsMargins(10, 12, 10, 12)
        sv.setSpacing(3)
        sec = QLabel("РАЗДЕЛЫ"); sec.setObjectName("YaSideHead")
        self._side_head = sec
        sv.addWidget(sec)
        for key in ("wave", "foryou", "albums", "follows", "tierlist", "duel"):
            b = self._nav_btns[key]
            b.setText("  " + self.NAV_TEXT[key])
            sv.addWidget(b)
        sv.addSpacing(10)
        from ya_artist_card import ArtistCard                  # «Об исполнителе» играющего трека (как в Spotify)
        self.artist_card = ArtistCard(self, side)
        sv.addWidget(self.artist_card, 1)                     # растягивается до «Настроек»
        sv.addStretch(0)
        st_b = self._nav_btns["settings"]
        st_b.setText("  " + self.NAV_TEXT["settings"])
        sv.addWidget(st_b)
        left = win.settings.get("ya_side", "right") == "left"
        if left:
            mid.addWidget(side)
            mid.addWidget(self.content, 1)
        else:
            mid.addWidget(self.content, 1)
            mid.addWidget(side)
        root.addLayout(mid, 1)
        # ── низ: одна панель плеера (смена темы — её первой кнопкой) ──
        root.addWidget(self._build_player())

    def _pl_usage_bump(self, name, k=1):
        """Сколько слушали плейлист — по нему порядок плиток сверху."""
        u = self.win.settings.setdefault("pl_usage", {})
        if isinstance(u, dict) and name:
            u[name] = int(u.get(name, 0)) + k

    def playlists_by_usage(self) -> list:
        w = self.win
        u = w.settings.get("pl_usage") or {}
        names = [n for n in w.playlists.keys() if n not in (WAVE_PL, ALBUM_PL)]
        order = {n: i for i, n in enumerate(names)}
        # «Мне нравится» — всегда первой, сразу после коллекции; остальные — по тому, как часто их слушают
        return sorted(names, key=lambda n: (n != LIKED, -int(u.get(n, 0)), order[n]))

    # ── данные / помощники ─────────────────────────────────────────────── #

    def current_track(self):
        w = self.win
        tracks = w.library if w.queue_context == "library" else w.playlists.get(w.queue_context, {}).get("tracks", [])
        if 0 <= w.current_index < len(tracks):
            return tracks[w.current_index]
        return None

    def is_current(self, t) -> bool:
        cur = self.current_track()
        return bool(cur is not None and str(cur.get("path", "")) == str(t.get("path", "")))

    def is_playing(self) -> bool:
        try:
            return bool(self.win.engine.is_playing())
        except Exception:                            # noqa: BLE001
            return False

    def _liked_paths(self):
        return {str(t.get("path", "")) for t in self.win.playlists.get(LIKED, {}).get("tracks", [])}

    def is_liked(self, t) -> bool:
        lp = getattr(self, "_liked_cache", None)
        if lp is None:
            lp = self._liked_cache = self._liked_paths()
        return str(t.get("path", "")) in lp

    def _like_pop(self, t):
        """Лайк играющего трека — сердце в нижнем плеере «подпрыгивает»."""
        import motion
        b = getattr(self, "b_like", None)
        if b is None or motion.strength() <= 0 or not self.is_current(t):
            return
        a = self.__dict__.get("_like_anim")
        if a is None:
            a = self._like_anim = QVariantAnimation(self)
            a.setStartValue(0.0)
            a.setEndValue(1.0)

            def step(v):
                v = float(v)
                n = int(round(20 + 11 * math.sin(math.pi * v) * (1.0 - v * 0.6)))
                b.setIconSize(QSize(n, n))
            a.valueChanged.connect(step)
            a.finished.connect(lambda: b.setIconSize(QSize(20, 20)))
        a.stop()
        a.setDuration(motion.duration(420))
        a.start()

    def toggle_like(self, t):
        pls = self.win.playlists
        pl = pls.setdefault(LIKED, {"tracks": [], "desc": "Треки, которые вам понравились", "cover": ""})
        path = str(t.get("path", ""))
        if any(str(x.get("path", "")) == path for x in pl["tracks"]):
            pl["tracks"] = [x for x in pl["tracks"] if str(x.get("path", "")) != path]
        else:
            pl["tracks"].insert(0, dict(t))
            self._like_pop(t)
            if hasattr(self, "_wave_good"):
                self.wave_like_seed(t)               # лайк в волне — следующее новое будет похоже на этот трек
        self._liked_cache = None
        self.win._ya_save_playlists()
        self._update_like_btn()
        TrackListView.refresh_visible()
        if self._cur_page == "playlist" and self._pl_name == LIKED:
            self.open_playlist(LIKED, keep_history=True)

    def user_playlists(self):
        return [n for n in self.win.playlists if n not in AUTO_PLAYLISTS]

    def add_to_playlist(self, t, name):
        self.win.playlist_add_tracks(name, [t])
        self.refresh_sidebar()

    def remove_rows(self, rows):
        """Убрать несколько строк из их пользовательского плейлиста."""
        rows = [r for r in rows if r]
        if not rows:
            return
        ctx = rows[0]["ctx"]
        if ctx not in self.win.playlists or ctx in AUTO_PLAYLISTS:
            return
        self.win.playlist_remove_rows(ctx, [r["i"] for r in rows if r["ctx"] == ctx])
        if self._cur_page == "playlist" and self._pl_name == ctx:
            self.open_playlist(ctx, keep_history=True)

    def add_many_to_new_playlist(self, tracks):
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Новый плейлист", "Название:")
        name = (name or "").strip()
        if ok and name:
            self.win.playlist_add_tracks(name, tracks)
            self.refresh_sidebar()

    def move_rows(self, name, rows, target):
        self.win.playlist_move(name, rows, target)
        if self._cur_page == "playlist" and self._pl_name == name:
            self.open_playlist(name, keep_history=True)
            self.pp_list.setCurrentIndex(self.pp_list.model_.index(max(0, min(target, self.pp_list.model_.rowCount() - 1))))

    def on_tracks_changed(self):
        """MainWindow: треки/плейлисты изменились (порядок, теги, удаление)."""
        self._liked_cache = None
        self._profiles = None
        _artist_index(self.win.library)                # исполнители: склейки написаний и совместки заново
        self._dirty.update({"foryou", "collection", "search", "albums"})
        self.pages["tierlist"].refresh()
        self.refresh_sidebar()
        cur = self._cur_page
        if cur == "playlist" and self._pl_kind == "playlist":
            if self._pl_name in self.win.playlists:
                self.open_playlist(self._pl_name, keep_history=True)
            else:
                self.show_page("collection")
        elif cur == "playlist" and self._pl_kind == "album":
            self._albums = self.album_index()
            if self._pl_name in self._albums:
                self.open_album(self._pl_name, keep_history=True)
            else:
                self.show_page("albums")
        elif cur in ("collection", "albums", "search"):
            self._rebuild(cur)
        TrackListView.refresh_visible()

    def new_playlist(self):
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Новый плейлист", "Название плейлиста:")
        name = (name or "").strip()
        if not ok or not name:
            return
        if name in self.win.playlists:
            QMessageBox.information(self, "Такой уже есть", "Плейлист с таким названием уже существует.")
            return
        self.win.playlists[name] = {"tracks": [], "desc": "", "cover": ""}
        self.win._ya_save_playlists()
        self.refresh_sidebar()
        self.open_playlist(name)

    def _side_menu(self, pos):
        it = self.pl_side.itemAt(pos)
        if it is None:
            return
        name = it.data(Qt.ItemDataRole.UserRole)
        m = QMenu(self)
        m.addAction("Открыть", lambda: self.open_playlist(name))
        m.addAction("Слушать", lambda: self.win._play_index(0, name) if self.win.playlists.get(name, {}).get("tracks") else None)
        m.addAction("＋  Добавить треки из коллекции…", lambda: (self.win.pick_tracks_for_playlist(name, self),))
        m.addSeparator()
        m.addAction("Переименовать…", lambda: self.win._pd_rename(name))
        m.addAction("Поделиться файлом…", lambda: getattr(self.win, "share_playlist", lambda *_: None)(name))
        m.addAction("Удалить плейлист", lambda: self._delete_playlist(name))
        m.exec(self.pl_side.viewport().mapToGlobal(pos))

    def _delete_playlist(self, name):
        self.win._pd_delete_playlist(name)
        if name not in self.win.playlists:
            self.refresh_sidebar()
            if self._cur_page == "playlist" and self._pl_name == name:
                self.show_page("collection")

    def add_to_new_playlist(self, t):
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Новый плейлист", "Название:")
        name = (name or "").strip()
        if ok and name:
            self.add_to_playlist(t, name)

    def remove_from_playlist(self, row):
        if row["ctx"] not in self.win.playlists:
            return
        self.win.playlist_remove_rows(row["ctx"], [row["i"]])
        if self._cur_page == "playlist" and self._pl_name == row["ctx"]:
            self.open_playlist(row["ctx"], keep_history=True)

    def preview_row(self, row, view=None):
        """30 секунд трека альбома до скачивания (повторное нажатие — пауза / продолжить)."""
        from preview import get_preview
        cb = row.get("_pv_cb")
        if cb is None:
            def cb(state, left, row=row, view=view):
                row["pv"] = (state, left)
                if view is not None:
                    try:
                        view.viewport().update()
                    except RuntimeError:                   # список уже пересобран
                        pass
            row["_pv_cb"] = cb
        get_preview(self.win).toggle(row["url"], row["t"].get("duration", 0), cb)

    def download_remote(self, row, view=None, play=False):
        """Скачать трек альбома, которого нет в коллекции (YouTube Music), прямо из списка альбома."""
        if (row.get("dl") or ("",))[0] in ("queued", "progress", "retry"):
            return
        t = row["t"]
        row["dl"] = ("queued", 0)
        if view is not None:
            view.viewport().update()

        states = self.__dict__.setdefault("_dl_states", {})
        url = row.get("url", "")
        states[url] = ("queued", 0)

        def cb(st, v):
            if st in ("progress", "queued", "retry"):
                row["dl"] = (st, float(v) if st == "progress" else 0)
            elif st == "error":
                row["dl"] = ("error", 0)
            elif st == "done":
                row["dl"] = ("done", 0)
                self._dirty.update({"albums", "foryou", "collection", "search"})
                if self._cur_page == "playlist" and self._pl_kind == "album":
                    self._album_reload_soon()
            states[url] = row["dl"]
            try:                                           # список могли пересобрать — обновить и новую строку
                for r in self.pp_list.model_.rows:
                    if r is not row and r.get("remote") and r.get("url") == url:
                        r["dl"] = row["dl"]
                self.pp_list.viewport().update()
            except (RuntimeError, AttributeError):
                pass
            if self._cur_page == "playlist" and self._pl_kind == "album":
                self._album_dl_button(self.pp_list.model_.rows)
            if view is not None:
                try:
                    view.viewport().update()
                except RuntimeError:
                    pass
        from ya_online import _meta
        self.win._quick_download(row["url"], playlist=None, play=play, cb=cb, meta=_meta(row["remote_t"]))

    def _album_reload_soon(self):
        """Скачался трек альбома — пересобрать список (раз в 1.5 с, а не после каждого трека)."""
        t = self.__dict__.get("_alb_reload_t")
        if t is None:
            t = QTimer(self)
            t.setSingleShot(True)
            t.setInterval(1500)
            t.timeout.connect(lambda: self._cur_page == "playlist" and self._pl_kind == "album"
                              and self.open_album(self._pl_name, keep_history=True))
            self._alb_reload_t = t
        t.start()

    def _album_dl_button(self, rows):
        """«Скачать альбом» — когда в альбоме есть недостающие треки; пока качаются — счётчик."""
        remote = [r for r in rows if r.get("remote")]
        busy = [r for r in remote if (r.get("dl") or ("",))[0] in ("queued", "progress", "retry", "done")]
        if not remote:
            self.pp_dlalb.hide()
            self.pp_sort.hide()
            return
        self.pp_dlalb.show()
        if busy:
            self.pp_dlalb.setText(f"  Скачивается {len(busy)} из {len(remote)}")
            self.pp_dlalb.setEnabled(len(busy) < len(remote))
        else:
            self.pp_dlalb.setText(f"  Скачать альбом ({len(remote)})")
            self.pp_dlalb.setEnabled(True)

    def download_album(self):
        """Все недостающие треки альбома — в коллекцию (обычные треки медиатеки, не плейлист)."""
        if self._pl_kind != "album":
            return
        rows = [r for r in self.pp_list.model_.rows if r.get("remote") and r.get("url")]
        n = 0
        for r in rows:
            if (r.get("dl") or ("",))[0] not in ("queued", "progress", "retry", "done"):
                self.download_remote(r, self.pp_list)
                n += 1
        self._album_dl_button(self.pp_list.model_.rows)
        if n:
            try:
                self.win._toast(f"Альбом скачивается в коллекцию: {n} {_plural(n, 'трек', 'трека', 'треков')}")
            except Exception:                              # noqa: BLE001
                pass

    def _remember_order(self, row):
        """Трек запустили из списка — дальше треки играют в порядке этого списка (сортировка, фильтр, поиск)."""
        ctx = row.get("ctx")
        for lst in (getattr(self, "c_list", None), getattr(self, "pp_list", None)):
            rows = getattr(getattr(lst, "model_", None), "rows", None) or []
            if any(r is row for r in rows):
                order = [r["i"] for r in rows if r.get("ctx") == ctx and isinstance(r.get("i"), int)]
                self.win.__dict__.setdefault("_view_order", {})[ctx] = order
                return
        (self.win.__dict__.get("_view_order") or {}).pop(ctx, None)

    def play_row(self, row):
        self._remember_order(row)
        if row.get("remote"):
            self.download_remote(row, self.pp_list, play=True)
            return
        if row.get("ctx") == ALBUM_PL and row.get("alb_tracks") is not None:
            # альбом играет своей очередью — по порядку треков
            self.win.playlists[ALBUM_PL] = {"tracks": [dict(t) for t in row["alb_tracks"]],
                                            "desc": f"auto: альбом {row.get('alb_name', '')}", "cover": ""}
        self.win._play_index(row["i"], row["ctx"])
        if row.get("ctx") in self.win.playlists and row.get("ctx") not in (WAVE_PL, ALBUM_PL):
            self._pl_usage_bump(row["ctx"], 2)

    def _lib_rows(self, tracks=None):
        lib = self.win.library
        if tracks is None:
            return [{"t": t, "ctx": "library", "i": i} for i, t in enumerate(lib)]
        idx = {str(t.get("path", "")): i for i, t in enumerate(lib)}
        return [{"t": t, "ctx": "library", "i": idx[str(t.get("path", ""))]}
                for t in tracks if str(t.get("path", "")) in idx]

    def profiles(self):
        """Профили настроения треков (music_intel) или None, пока считаются."""
        if self._profiles is None:
            try:
                self._profiles = self.win._ya_profiles(self._on_profiles)
            except Exception as error:
                # Optional analysis must never prevent the library from being
                # displayed. A later library change retries the analysis.
                print('[collection] optional profiles:',error)
                self._profiles = {}
        return self._profiles

    def _on_profiles(self, prof):
        self._profiles = prof or {}
        if self._cur_page == "playlist" and getattr(self, "_pp_tracks", None) is not None:
            self._pp_filters_reset(self._pp_tracks, getattr(self, "_pp_fkey", None))
        self._dirty.update({"foryou", "collection", "wave"})
        if self._cur_page in ("foryou", "collection", "wave"):
            self._rebuild(self._cur_page)

    # ── навигация ─────────────────────────────────────────────────────── #

    def show_page(self, key, remember=True):
        previous_widget=self.stack.currentWidget()
        previous=next((name for name,page in self.pages.items() if page is previous_widget),self._cur_page)
        missing=object()
        previous_hint=self.__dict__.get('_prev_page',missing)
        history=self.__dict__.get('_page_hist',missing)
        if history is not missing:history=list(history)
        saved_choice=self.win.settings.get('ya_page',missing)
        lyrics=self.btn_lyrics.isChecked();queue_style=self.btn_queue.styleSheet()
        try:
            self._show_page(key,remember)
        except Exception:
            # A failed first build must not select a different navigation item,
            # overwrite startup choice/history, or leave a frozen half-page.
            import ui_anim
            ui_anim._finish(self.stack)
            if previous_widget is not None and self.stack.indexOf(previous_widget)>=0:
                self.stack.setCurrentWidget(previous_widget)
            self._cur_page=previous
            if previous_hint is missing:self.__dict__.pop('_prev_page',None)
            else:self._prev_page=previous_hint
            if history is missing:self.__dict__.pop('_page_hist',None)
            else:self._page_hist=history
            if saved_choice is missing:self.win.settings.pop('ya_page',None)
            else:self.win.settings['ya_page']=saved_choice
            if previous in self._nav_btns:self._nav_btns[previous].setChecked(True)
            else:
                selected=self.nav.checkedButton()
                if selected is not None:
                    self.nav.setExclusive(False);selected.setChecked(False);self.nav.setExclusive(True)
            self.btn_lyrics.setChecked(lyrics);self.btn_queue.setStyleSheet(queue_style)
            raise

    def _show_page(self, key, remember=True):
        if key == "listening":
            self._ensure_listening_tools()
            key = "settings"
            QTimer.singleShot(0, lambda: self.pages["settings"].ensureWidgetVisible(self._listener_panel))
        if key == "settings" and getattr(self, "_listener_panel", None) is not None:
            self.win._listening_tools.dialog = self._listener_panel
        if key not in self.pages:
            return
        np_ = self.__dict__.get("_now_playing")
        if np_ is not None and np_.isVisible():                # переход на страницу — экран «Сейчас играет» убирается
            np_.close_mode(instant=True)
        try:                                                   # «Моя волна» — панели вокруг уходят в темноту
            import wave_veil
            wave_veil.install(self).set_on(key == "wave")
        except Exception as e:                                 # noqa: BLE001
            print("[veil]", e)
        if remember and self._cur_page != key:
            self._remember()
        self._cur_page = key
        self._last_nav = __import__("time").monotonic()
        try:                              # вкладки листают — фоновые расчёты на Python уступают процессор
            import bgproc
            bgproc.set_soft_busy("nav", True)
            t = self.__dict__.get("_nav_soft")
            if t is None:
                t = self._nav_soft = QTimer(self)
                t.setSingleShot(True)
                t.timeout.connect(lambda: bgproc.set_soft_busy("nav", False))
            t.start(1500)
        except Exception:                                      # noqa: BLE001
            pass
        if key in self._nav_btns:
            self._nav_btns[key].setChecked(True)
            if key in ("search", "wave", "foryou", "collection", "albums", "tierlist"):
                self.win.settings["ya_page"] = key
        else:
            b = self.nav.checkedButton()
            if b is not None:
                self.nav.setExclusive(False)
                b.setChecked(False)
                self.nav.setExclusive(True)
        if key == "profile":
            self.pages["profile"].refresh()
        if key == "queue":
            self.pages["queue"].refresh()
        if key == "tierlist":
            self.pages["tierlist"].refresh()
        if key == "follows":
            self.pages["follows"].refresh()
        if key == "net":
            self.pages["net"].on_show()
        if key in ("foryou", "collection", "wave", "search", "albums") and (key in self._dirty or key == "foryou"
                                                                  and not self.pages["foryou"].v.count()):
            # «Для вас» и «Моя волна» обновляются данными из фона (рекомендации, профили вкуса): уже собранную
            # показываем сразу, а свежую версию соберёт простой (_idle_rebuild) — переход не ждёт пересборку
            if not (key in self.STALE_OK and key in self.__dict__.get("_built", ())):
                self._rebuild(key)
        # плавная смена страницы (ui_anim): вперёд/назад — по порядку вкладок слева
        order = ["wave", "search", "foryou", "collection", "albums", "follows", "tierlist", "duel", "net", "playlist",
                 "artist",
                 "profile", "queue", "lyrics", "listening", "settings"]
        cur = self.stack.currentWidget()
        old_key = next((k for k, w in self.pages.items() if w is cur), None)
        d = 0 if old_key not in order or key not in order else (1 if order.index(key) > order.index(old_key) else -1)
        # «Текст» и «Очередь» — шторки из плеера внизу: выезжают снизу, а по стрелке «свернуть» уезжают вниз
        sheets = ("lyrics", "queue")
        kind = ("up" if key in sheets and old_key not in sheets else
                "down" if old_key in sheets and key not in sheets else "slide")
        sw = getattr(self.win, "animate_switch", None)
        sw(self.stack, self.pages[key], d, kind) if sw else self.stack.setCurrentWidget(self.pages[key])
        self.btn_lyrics.setChecked(key == "lyrics")
        self.btn_queue.setStyleSheet(f"QPushButton{{background:{_rgba(YELLOW, 0.22)};border-radius:18px;}}" if key == "queue" else "")

    IDLE_REBUILD = ("foryou", "collection", "albums", "wave")
    STALE_OK = ("foryou", "wave")         # можно показать прежнюю версию и обновить в простое

    def _idle_rebuild(self):
        """Одна изменившаяся страница за раз, только в простое: вкладку не переключали 1.5 с, колесо не крутили,
        кнопки мыши отпущены, окно на экране."""
        import time as _t
        from PyQt6.QtWidgets import QApplication
        if not self._dirty or not self.isVisible() or self.win.isMinimized():
            return
        now = _t.monotonic()
        if now - self._last_nav < 1.5 or now - self.decor.__dict__.get("_busy_t", 0) < 1.5 \
                or QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            return
        try:
            import bgproc
            if bgproc.fg_busy():
                return
        except Exception:                                      # noqa: BLE001
            pass
        key = next((k for k in self.IDLE_REBUILD if k in self._dirty
                    and (k != self._cur_page or k in self.STALE_OK)), None)
        if key is not None:
            pg = self.pages.get(key)
            sb = pg.verticalScrollBar() if hasattr(pg, "verticalScrollBar") else None
            keep = sb.value() if sb is not None else 0
            try:
                self._rebuild(key)
            except Exception as e:                             # noqa: BLE001
                print("[idle rebuild]", key, e)
            if sb is not None and key == self._cur_page:       # открытая страница — на том же месте
                QTimer.singleShot(0, lambda sb=sb, keep=keep: sb.setValue(keep))

    def _rebuild(self, key):
        self._dirty.discard(key)
        self.__dict__.setdefault("_built", set()).add(key)
        try:
            # A background data update must not leave an obsolete snapshot
            # covering the refreshed model until the animation ends.
            if self.stack.currentWidget() is self.pages.get(key):
                import ui_anim
                ui_anim._finish(self.stack)
            if key == "foryou":
                self._fill_foryou()
            elif key == "collection":
                self._fill_collection()
            elif key == "albums":
                self._fill_albums()
            elif key == "wave":
                self._fill_wave_list()
            elif key == "search":
                self._search_changed()
        except Exception:
            # Keep a failed first build retryable on the next visit.
            self._dirty.add(key)
            raise

    # ── история страниц: «Назад» возвращает ровно туда, где были (артист → другой артист → альбом …) ── #

    def _hist_state(self) -> tuple:
        k = self._cur_page
        if k == "artist":
            return ("artist", self.pages["artist"].name)
        if k == "playlist":
            return ("playlist", self._pl_kind, self._pl_name)
        return (k,)

    # ── режим геймера (game_mode.py) ──
    def _gamer_setup(self):
        try:
            import game_mode
            gm = game_mode.install(self.win)
            gm.changed.connect(self._gamer_changed)
            self._gamer_changed(gm.active, "")
        except Exception as e:                                 # noqa: BLE001
            print("[gamer]", e)

    def _gamer_clicked(self):
        gm = getattr(self.win, "_game_mode", None)
        if gm is None:
            self.gamer_btn.setChecked(False)
            return
        gm.toggle()

    def _gamer_changed(self, on, why):
        b = getattr(self, "gamer_btn", None)
        if b is None:
            return
        b.setChecked(bool(on))
        b.setIcon(ya_icon("gamepad", 22, YELLOW if on else "#ffffff"))
        from duel_settings import tr
        gm = getattr(self.win, "_game_mode", None)
        game = gm.game[0] if gm is not None and gm.game[0] else ""
        if on:
            b.setToolTip(tr(self.win, "Режим геймера включён", "Gamer mode is on") + (f" — {game}" if game else "") +
                         tr(self.win, ". Анимации стоят, пока окно не в фокусе; фоновые задачи ждут; игра — в приоритете."
                                      "\nНажмите, чтобы выключить.",
                            ". Animations stop while the window is not focused; background work waits; the game comes first."
                            "\nClick to turn off."))
        else:
            b.setToolTip(tr(self.win, "Режим геймера: ECHOES только играет музыку и не мешает игре."
                                      "\nВключается и сам, когда запущена игра (Настройки → Производительность).",
                            "Gamer mode: ECHOES only plays music and stays out of the game's way."
                            "\nTurns on by itself while a game is running (Settings → Performance)."))
        toast = getattr(self.win, "_toast", None)
        if callable(toast) and why and why != "manual":
            if on:
                toast(tr(self.win, "Режим геймера включён: ", "Gamer mode on: ") + why)
            elif why == "game_closed":
                toast(tr(self.win, "Игра закрыта — режим геймера выключен", "Game closed — gamer mode off"))

    def _stream_hint(self, t):
        try:
            import stream_core
            self.win.streams.hint(t if str(t.get("path", "")).startswith("stream:") else stream_core.make_track(t))
        except Exception as e:                                 # noqa: BLE001
            print("[stream] hint:", e)

    def _remember(self):
        """Запомнить текущую страницу (вызывать ДО перехода: страницы артиста/плейлиста грузятся заранее)."""
        if not self._cur_page or self._cur_page == "lyrics":
            return
        hist = self.__dict__.setdefault("_page_hist", [])
        st = self._hist_state()
        if not hist or hist[-1] != st:
            hist.append(st)
            del hist[:-50]
        self._prev_page = self._cur_page

    def go_back(self):
        hist = self.__dict__.get("_page_hist") or []
        cur = self._hist_state()
        while hist:
            st = hist.pop()
            if st == cur or st[0] not in self.pages:
                continue
            if st[0] == "artist" and st[1]:
                from artist_identity import ArtistIndex
                index = _artist_index(self.win.library)
                self.pages["artist"].load(st[1], index.tracks_for(st[1]))
                self.show_page("artist", remember=False)
            elif st[0] == "playlist" and st[2]:
                if st[1] == "album":
                    self.open_album(st[2], keep_history=True)
                else:
                    self.open_playlist(st[2], keep_history=True)
            else:
                self.show_page(st[0], remember=False)
            return
        self.show_page("foryou", remember=False)

    # ── плеер (низ) ───────────────────────────────────────────────────── #

    def _build_player(self) -> QWidget:
        w = self.win
        bar = AmbientFrame(); bar.setObjectName("YaPlayer")
        bar.setFixedHeight(84)
        v = QVBoxLayout(bar)
        v.setContentsMargins(0, 2, 0, 8)
        v.setSpacing(0)
        self.progress = ProgressLine()
        self.progress.show_times(True)
        self.progress.seek_to.connect(self._seek_frac)
        v.addWidget(self.progress)
        h = QHBoxLayout()
        h.setContentsMargins(12, 0, 14, 0)
        h.setSpacing(6)
        h.addSpacing(2)                                        # «Сменить тему» переехала в «Ещё» справа
        # слева: обложка + название
        from ya_decor import VinylCover, PlayButton, MiniLyric
        self.p_cover = VinylCover(52, 6)                       # из-за обложки выглядывает пластинка
        self.p_cover.setCursor(Qt.CursorShape.PointingHandCursor)
        self.p_cover.setToolTip("Сейчас играет — на весь экран (Ctrl+Shift+N). Правый клик — найти в коллекции, текст, ещё")
        self.p_cover.mousePressEvent = self._p_cover_press
        h.addWidget(self.p_cover)
        h.addSpacing(2)
        tcol = QVBoxLayout(); tcol.setSpacing(1)
        self.p_title = QLabel("—"); self.p_title.setStyleSheet("font-size:14px;font-weight:700;")
        from artist_links import ArtistLinks
        self.p_artist = ArtistLinks(); self.p_artist.setObjectName("YaSub")
        self.p_artist.artist_clicked.connect(self.open_artist)
        self.p_lyric = MiniLyric()                             # текущая строка текста песни
        self.p_lyric.hide()
        tcol.addStretch(1); tcol.addWidget(self.p_title); tcol.addWidget(self.p_artist); tcol.addWidget(self.p_lyric)
        tcol.addStretch(1)
        left = QWidget(); left.setObjectName("YaSide"); left.setLayout(tcol)
        left.setMinimumWidth(120); left.setMaximumWidth(300)
        h.addWidget(left, 1)
        # центр: управление
        self.b_shuffle = icon_button("shuffle", "Перемешать", 38, 20, "#cfcfcf", True)
        self.b_shuffle.clicked.connect(lambda: w.btn_shuffle.click())
        self.b_prev = icon_button("prev", "Предыдущий", 40, 22)
        self.b_prev.clicked.connect(w.prev_track)
        self.b_play = PlayButton()                             # в цвет обложки, со свечением в такт
        self.b_play.setObjectName("YaYellow")
        self.b_play.setToolTip("Играть / пауза")
        self.b_play.clicked.connect(w.toggle_play)
        self.b_next = icon_button("next", "Следующий", 40, 22)
        self.b_next.clicked.connect(w.next_track)
        self.b_repeat = icon_button("repeat", "Повтор", 38, 20, "#cfcfcf", True)
        self.b_repeat.clicked.connect(w._cycle_repeat)
        self.b_like = icon_button("heart", "Мне нравится", 38, 20)
        self.b_like.clicked.connect(lambda: self.current_track() and self.toggle_like(self.current_track()))
        center = QHBoxLayout(); center.setSpacing(6)
        for b in (self.b_shuffle, self.b_prev, self.b_play, self.b_next, self.b_repeat, self.b_like):
            center.addWidget(b)
        h.addStretch(1)
        h.addLayout(center)
        h.addStretch(1)
        # справа: только текст, очередь и громкость; всё остальное — в «Ещё» с подписями (PlayerMorePopup)
        self.btn_lyrics = icon_button("lyrics", "Текст песни", 36, 20, "#cfcfcf", True)
        self.btn_lyrics.clicked.connect(self.toggle_lyrics)
        self.btn_queue = icon_button("queue", "Очередь", 36, 20, "#cfcfcf")
        self.btn_queue.clicked.connect(self.toggle_queue)
        self.b_vol = icon_button("volume", "Громкость: нажмите — выключить звук", 34, 20, "#cfcfcf")
        self.b_vol.clicked.connect(self._toggle_mute)
        self.vol = QSlider(Qt.Orientation.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setFixedWidth(90)
        self.vol.setToolTip("Громкость")
        self.vol.setValue(w.vol.value())
        self.vol.valueChanged.connect(lambda v: w.vol.setValue(v))
        self.b_pmore = icon_button("dots", "Ещё: сейчас играет, клип, реакция, звук, тема, настройки", 36, 20, "#cfcfcf")
        self.b_pmore.clicked.connect(self.toggle_player_more)
        # панель «Звук» и выбор реакции всплывают над «Ещё» (раньше — над своими кнопками)
        self.b_sound = self.b_moment = self.b_pmore
        self._more_pop = None
        self._more_closed_at = 0.0
        for b in (self.btn_lyrics, self.btn_queue, self.b_pmore):
            h.addWidget(b)
        h.addSpacing(6)
        h.addWidget(self.b_vol)
        h.addWidget(self.vol)
        self._player_bar = bar
        v.addLayout(h, 1)
        self._muted_from = None
        return bar

    def player_more_items(self) -> list:
        """Пункты «Ещё» в плеере: ключ, значок, подпись, сочетание клавиш, действие."""
        w = self.win
        fire = self.__dict__.get("_fire_icon")
        if fire is None:                                       # «🔥» — значком того же размера, что остальные
            pm = QPixmap(40, 40)
            pm.fill(Qt.GlobalColor.transparent)
            fp = QPainter(pm)
            ff = QFont("Segoe UI Emoji")
            ff.setPixelSize(28)
            fp.setFont(ff)
            fp.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "🔥")
            fp.end()
            pm.setDevicePixelRatio(2)
            fire = self._fire_icon = QIcon(pm)
        return [
            {"key": "now", "icon": "headphones", "text": "Сейчас играет", "hint": "Ctrl+Shift+N",
             "tip": "Обложка, текст и очередь — на всё окно",
             "fn": self.open_now_playing},
            {"key": "moment", "icon": fire, "text": "Реакция на этот момент",
             "tip": "Реакция на этот момент трека — друзья увидят её, когда будут его слушать",
             "fn": lambda: __import__("net_moments").show_picker(self, self.b_pmore)},
            {"key": "clip", "icon": "clip", "text": "Клип песни", "hint": "Ctrl+Shift+K", "fn": w._toggle_clip_mode},
            {"key": "cover", "icon": "cover", "text": "Режим обложки", "fn": w._toggle_cover_mode},
            {"key": "sound", "icon": "eq", "text": "Звук и эффекты",
             "tip": "Звук: басс буст, громкость, найткор, словед", "fn": self.toggle_sound_panel},
            {"key": "theme", "icon": "palette", "text": "Сменить тему",
             "fn": lambda: w._winamp_theme_menu(self.b_pmore.mapToGlobal(self.b_pmore.rect().topLeft()))},
            {"key": "settings", "icon": "settings", "text": "Настройки", "hint": "Ctrl+,",
             "fn": lambda: self.show_page("settings")},
        ]

    def open_player_more(self):
        self.close_player_more()
        self._more_pop = PlayerMorePopup(self, self.b_pmore)
        self._more_pop.show()
        return self._more_pop

    def close_player_more(self):
        pop = self.__dict__.get("_more_pop")
        if pop is not None:
            self._more_pop = None
            try:
                pop.close()
            except RuntimeError:
                pass

    def toggle_player_more(self):
        if self.__dict__.get("_more_pop") is not None:
            self.close_player_more()
        elif time.monotonic() - self.__dict__.get("_more_closed_at", 0.0) > 0.25:   # клик по кнопке уже закрыл окошко
            self.open_player_more()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        dec = getattr(self, "decor", None)
        if dec is not None:
            dec._gap = None
        np_ = self.__dict__.get("_now_playing")
        if np_ is not None and np_.isVisible():
            np_.setGeometry(self.rect())
        self._responsive()                                     # сразу — до первого кадра нового размера
        QTimer.singleShot(0, self._responsive)                 # и после раскладки (ширина плеера уже новая)

    def _responsive(self):
        """Узкое окно: разделы — только значками, ползунок громкости и ник прячутся."""
        W = self.width()
        bar = getattr(self, "_player_bar", None)
        if bar is not None:
            self.vol.setVisible(bar.width() >= 760)
        if self._layout_mode != "new":
            return
        icons = W < 1180
        side = getattr(self, "_side_nav", None)
        if side is not None and icons != self.__dict__.get("_nav_icons"):
            self._nav_icons = icons
            side.setFixedWidth(64 if icons else SIDE_W)
            card = getattr(self, "artist_card", None)
            if card is not None:
                card.setVisible(not icons and bool(card.name))
            self._side_head.setVisible(not icons)
            for key in ("wave", "foryou", "albums", "follows", "tierlist", "duel", "settings"):
                b = self._nav_btns[key]
                b.setText("" if icons else "  " + self.NAV_TEXT[key])
                b.setStyleSheet("QPushButton{padding:9px 0px;text-align:center;}" if icons else "")
        self.nick.setVisible(W >= 1000)
        self.status.setVisible(W >= 1000)

    def toggle_sound_panel(self):
        """Панель «Звук» над кнопкой: басс буст, супер громкость, найткор, словед (ya_sound_panel)."""
        pan = getattr(self, "_sound_panel", None)
        if pan is None:
            from ya_sound_panel import SoundPanel
            pan = self._sound_panel = SoundPanel(self)
        if pan.isVisible():
            pan.hide()
            return
        if getattr(self, "_sound_closed_at", 0) and __import__("time").monotonic() - self._sound_closed_at < 0.25:
            return                                         # клик по кнопке закрыл попап — не открывать снова
        pan.popup(self.b_sound)

    def _toggle_mute(self):
        if self._muted_from is None:
            self._muted_from = self.win.vol.value()
            self.win.vol.setValue(0)
        else:
            self.win.vol.setValue(self._muted_from or 60)
            self._muted_from = None

    def _seek_frac(self, frac):
        try:
            dur = float(self.win.engine.duration or 0)
            if dur > 0:
                self.win.engine.seek(frac * dur)
        except Exception as e:                       # noqa: BLE001
            print("[ya] seek:", e)

    def _open_current_artist(self):
        t = self.current_track()
        if t:
            self.open_artist(_artist_main(t.get("artist", "")))

    def _update_like_btn(self):
        t = self.current_track()
        liked = bool(t and self.is_liked(t))
        self.b_like.setIcon(ya_icon("heart_fill" if liked else "heart", 20, "#ffffff"))
        if hasattr(self, "wave"):
            self.wave.like_btn.setIcon(ya_icon("heart_fill" if liked else "heart", 20))

    def _tick(self):
        w = self.win
        eng = w.engine
        t = self.current_track()
        key = str(t.get("path", "")) if t else None
        if key != self._track_key:
            self._track_key = key
            self._on_track_changed(t)
        if self._cur_page == "queue":
            qp = self.pages["queue"]
            if qp.signature() != qp.sig:
                qp.refresh()
        playing = self.is_playing()
        if getattr(self, "_playing_ui", None) != playing:
            self._playing_ui = playing
            self.b_play.playing = playing
            self.b_play.update()
            TrackListView.refresh_visible()
            self.wave_play.setIcon(ya_icon("pause" if playing else "play", 26, "#000000"))
        try:
            dur = float(eng.duration or 0)
            pos = float(eng.get_position() or 0)
        except Exception:                            # noqa: BLE001
            dur = pos = 0.0
        self.progress.set_state(pos / dur if dur > 0 else 0.0, dur)
        dec = getattr(self, "decor", None)
        if dec is not None:
            dec.mini_lyrics(pos)
        if getattr(self.progress, "moments", None):            # чужие реакции на момент — всплывашки
            import net_moments
            net_moments.tick(self, pos, dur)
        if self.b_shuffle.isChecked() != bool(w.shuffle):
            self.b_shuffle.setChecked(bool(w.shuffle))
        rm = int(getattr(w, "repeat_mode", 0))
        if getattr(self, "_rm", None) != rm:
            self._rm = rm
            self.b_repeat.setChecked(rm != 0)
            self.b_repeat.setIcon(ya_icon("repeat_one" if rm == 2 else "repeat", 20,
                                          YELLOW if rm else "#cfcfcf"))
        if getattr(self, "_shuf_ui", None) != bool(w.shuffle):       # иконку — только когда сменилась
            self._shuf_ui = bool(w.shuffle)
            self.b_shuffle.setIcon(ya_icon("shuffle", 20, YELLOW if w.shuffle else "#cfcfcf"))
        if self.vol.value() != w.vol.value() and not self.vol.isSliderDown():
            self.vol.blockSignals(True); self.vol.setValue(w.vol.value()); self.vol.blockSignals(False)
            self.b_vol.setIcon(ya_icon("mute" if w.vol.value() == 0 else "volume", 20, "#cfcfcf"))
        # библиотека / плейлисты поменялись — обновить страницы
        lib_sig = len(w.library)
        # служебные очереди (онлайн-треки «Моей волны», дуэли, «Для вас» — префикс ⁣) меняются при каждом
        # включении онлайн-трека: из-за них «Для вас», коллекция и альбомы пересобирались на каждом входе
        pl_sig = tuple((n, len(p.get("tracks", []))) for n, p in w.playlists.items() if not str(n).startswith("⁣"))
        if lib_sig != self._lib_sig or pl_sig != self._pl_sig:
            lib_changed = lib_sig != self._lib_sig
            self._lib_sig, self._pl_sig = lib_sig, pl_sig
            self._liked_cache = None
            self.refresh_sidebar()
            self._dirty.update({"foryou", "collection", "search", "albums"})
            if lib_changed:
                self._profiles = None
                self.pages["tierlist"].refresh()
            if self._cur_page in ("collection",) and self._timer.interval():
                self._rebuild(self._cur_page)
        # текст
        if self._cur_page == "lyrics":
            self._lyrics_tick(None, dur)           # позиция — плавная, см. ниже

    def _on_track_changed(self, t):
        if t is None:
            self.p_title.setText("—")
            self.p_artist.set_track(None)
            self.l_artist.set_track(None)
            self.p_cover.set_cover("", "none")
            return
        title = sanitize_title(t.get("title", "") or "Без названия")
        artist = t.get("artist") or "Неизвестный исполнитель"
        fm = QFontMetrics(self.p_title.font())
        self.p_title.setText(fm.elidedText(title, Qt.TextElideMode.ElideRight, 280))
        self.p_title.setToolTip(title)
        self.p_artist.set_track(t)
        self.p_cover.set_cover(t.get("cover", ""), str(t.get("path", "")))
        self._update_like_btn()
        dec = getattr(self, "decor", None)
        if dec is not None:
            dec.track_changed(t)
        try:
            import net_moments
            net_moments.refresh_marks(self)
        except Exception:                                      # noqa: BLE001
            pass
        card = getattr(self, "artist_card", None)
        if card is not None:
            card.set_artist(_artist_main(t.get("artist", "")))
            if self.__dict__.get("_nav_icons"):
                card.hide()
        QTimer.singleShot(1500, self._wave_arts_check)     # прослушивание уже записано в статистику
        TrackListView.refresh_visible()
        # «Моя волна» и текст — под новый трек
        wl = self.wave.track_lbl
        wl.setText(QFontMetrics(wl.font()).elidedText(f"{title}  ·  {artist}", Qt.TextElideMode.ElideRight, 400))
        self.wave.cover.setPixmap(cover_pixmap(t.get("cover", ""), 60, 6, seed=str(t.get("path", ""))))
        if hasattr(self.wave, "set_track"):                # сияние — в цвет обложки, смена — из размытия
            self.wave.set_track(self.wave.cover.pixmap())
        liked = self.is_liked(t)
        self.wave.like_btn.setIcon(ya_icon("heart_fill" if liked else "heart", 20))
        if self.win.queue_context == WAVE_PL and hasattr(self, "_disc_pool"):
            self._wave_track_feedback(t)
            self._update_wave_hint()
            self._disc_feed()
        self.l_cover.set_cover(t.get("cover", ""), str(t.get("path", "")))
        self.l_title.setText(title)
        self.l_artist.set_track(t)
        self._lyr_bg = None
        self.pages["lyrics"].update()
        # панель текста непрозрачна и рисует свой кусок фона сама; без таймингов она не перерисовывается
        # (строки не меняются) — иначе остаётся фон прошлого трека прямоугольником
        self.l_panel.update()

    # ── страница «Поиск» ─────────────────────────────────────────────── #

    def _build_search(self):
        page = Page()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Трек, исполнитель, альбом…")
        self.search_edit.addAction(ya_icon("search", 18, "#8a8a8a"), QLineEdit.ActionPosition.LeadingPosition)
        self.search_edit.setMinimumHeight(40)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(lambda: self._search_now() if self._search_online()
                                           else self._search_changed())
        # в интернете — пауза подольше, чтобы не дёргать серверы на каждую букву
        self.search_edit.textChanged.connect(
            lambda _: self._search_timer.start(900 if self._search_online() else 180))
        self.search_edit.returnPressed.connect(self._search_now)
        page.v.addWidget(self.search_edit)
        # где искать: коллекция или интернет (YouTube Music + SoundCloud)
        mrow = QHBoxLayout(); mrow.setSpacing(8); mrow.setContentsMargins(0, 14, 0, 0)
        self.s_local = chip("В коллекции"); self.s_net = chip("В интернете")
        self.s_net.setIcon(ya_icon("wave", 16)); self.s_net.setIconSize(QSize(16, 16))
        gm = QButtonGroup(page); gm.setExclusive(True)
        for b in (self.s_local, self.s_net):
            gm.addButton(b)
            b.clicked.connect(self._search_mode_changed)
        self.s_net.toggled.connect(lambda on: self.s_net.setIcon(ya_icon("wave", 16, "#000000" if on else "#cfcfcf")))
        self.s_net.setIcon(ya_icon("wave", 16, "#cfcfcf"))
        self.s_net.setChecked(True)                             # по умолчанию ищем в интернете
        self.s_net.setIcon(ya_icon("wave", 16, "#000000"))
        mrow.addWidget(seg_group(self.s_local, self.s_net))
        mrow.addSpacing(14)
        self.s_src = {}
        gs = QButtonGroup(page); gs.setExclusive(True)
        src_btns = []
        for key, text in (("all", "Везде"), ("ytm", "YouTube Music"), ("sc", "SoundCloud")):
            b = chip(text)
            gs.addButton(b)
            b.clicked.connect(self._search_now)
            self.s_src[key] = b
            src_btns.append(b)
        self.s_src["all"].setChecked(True)
        self.s_src_group = seg_group(*src_btns)
        mrow.addWidget(self.s_src_group)
        mrow.addStretch(1)
        self.s_target_lbl = QLabel("Скачивать в:"); self.s_target_lbl.setObjectName("YaSub")
        self.s_target = QComboBox(); self.s_target.setMinimumWidth(170)
        mrow.addWidget(self.s_target_lbl); mrow.addWidget(self.s_target)
        page.v.addLayout(mrow)
        row = QHBoxLayout(); row.setSpacing(8); row.setContentsMargins(0, 10, 0, 0)
        self.s_pop = chip("Популярное"); self.s_hist = chip("История")
        g = QButtonGroup(page); g.setExclusive(True)
        for b in (self.s_pop, self.s_hist):
            g.addButton(b)
            b.clicked.connect(self._search_changed)
        self.s_pop.setChecked(True)
        row.addWidget(seg_group(self.s_pop, self.s_hist))
        row.addStretch(1)
        self.s_local_row = QWidget(); self.s_local_row.setObjectName("YaPage"); self.s_local_row.setLayout(row)
        page.v.addWidget(self.s_local_row)
        self.s_title = section_title("Популярное у вас")
        page.v.addWidget(self.s_title)
        self.s_artists = HRow()
        page.v.addWidget(self.s_artists)
        self.s_list = TrackListView(self)
        self.s_list.set_auto_height(True)
        page.v.addWidget(self.s_list.section_widget())
        from ya_online import OnlineResults
        self.s_online = OnlineResults(self)
        page.v.addWidget(self.s_online)
        page.v.addStretch(1)
        self._dirty.add("search")
        self._search_mode_changed()
        return page

    # ── онлайн-поиск ── #

    def _search_online(self) -> bool:
        return self.s_net.isChecked()

    def _search_mode_changed(self, *_):
        net = self._search_online()
        self.s_src_group.setVisible(net)
        self.s_target_lbl.setVisible(net)
        self.s_target.setVisible(net)
        self.s_local_row.setVisible(not net)
        self.s_title.setVisible(not net)
        self.s_list.section_widget().setVisible(not net)
        self.s_artists.setVisible(False)
        self.s_online.setVisible(net)
        self.search_edit.setPlaceholderText("Найти в интернете: трек или исполнитель (Enter — искать)" if net
                                            else "Трек, исполнитель, альбом…")
        if net:
            self._fill_target_combo()
        self._search_now()

    def _fill_target_combo(self):
        cur = self.s_target.currentData() or self.win.settings.get("online_target", "")
        self.s_target.blockSignals(True)
        self.s_target.clear()
        self.s_target.addItem("Только в коллекцию", "")
        names = self.user_playlists()
        for n in names:
            self.s_target.addItem(n, n)
        i = self.s_target.findData(cur)
        self.s_target.setCurrentIndex(i if i >= 0 else 0)
        self.s_target.blockSignals(False)
        try:
            self.s_target.currentIndexChanged.disconnect()
        except TypeError:
            pass
        self.s_target.currentIndexChanged.connect(
            lambda _: self.win.settings.__setitem__("online_target", self.s_target.currentData() or ""))

    def online_target_playlist(self):
        return self.s_target.currentData() or None

    def online_local_path(self, url):
        p = self.win.settings.get("online_downloaded", {}).get(url)
        if p and any(t.get("path") == p for t in self.win.library):
            return p
        return ""

    def play_path(self, path):
        rows = [r for r in self._lib_rows() if r["t"].get("path") == path]
        if rows:
            self.play_row(rows[0])

    def _search_now(self, *_):
        if not hasattr(self, "s_online"):
            return
        if self._search_online():
            src = next((k for k, b in self.s_src.items() if b.isChecked()), "all")
            self.s_online.search(self.search_edit.text().strip(), src)
        else:
            self._search_changed()

    def online_find_artist(self, name, source=None):
        self.show_page("search")
        self.s_net.setChecked(True)
        if source in ("ytm", "sc"):
            self.s_src[source].setChecked(True)
        self.search_edit.blockSignals(True)
        self.search_edit.setText(name)
        self.search_edit.blockSignals(False)
        self._search_mode_changed()

    def open_release(self, kind, artist, rel=None, browse_id=None):
        """Альбом / сингл исполнителя (треклист с прослушиваниями) или все его треки."""
        page = self.pages.get("release")
        if page is None:
            from ya_online import ReleasePage
            page = ReleasePage(self)
            self.pages["release"] = page
            self.stack.addWidget(page)
        if kind == "all":
            page.open_all(artist, browse_id)
        else:
            page.open_album(artist, rel or {})
        self.show_page("release")

    def open_online_artist(self, artist: dict):
        page = self.pages.get("online_artist")
        if page is None:
            from ya_online import OnlineProfilePage
            page = OnlineProfilePage(self)
            self.pages["online_artist"] = page
            self.stack.addWidget(page)
        page.load(artist)
        self.show_page("online_artist")

    def _search_changed(self):
        if self._search_online():
            return                                   # в интернете ищем по Enter/кнопкам, не на каждый символ
        q = self.search_edit.text().strip().lower()
        lib = self.win.library
        hist = self.win.settings.get("play_history", {})
        lbl = self.s_title.findChild(QLabel)
        self.s_artists.clear()
        if q:
            from search_util import track_matches, tokens
            qt = tokens(q)
            found = [t for t in lib if track_matches(q, t)]
            lbl.setText(f"Найдено: {len(found)}" if found else "Ничего не нашлось")
            arts = {}
            for t in found:
                a = _artist_main(t.get("artist", ""))
                if a and any(len(w) > 1 and w in a.lower() for w in qt):      # исполнитель, чьё имя есть в запросе
                    arts.setdefault(a, t)
            for a, t in list(arts.items())[:12]:
                c = Card(a, "Исполнитель", t.get("cover", ""), 120, circle=True)
                c.clicked.connect(lambda a=a: self.open_artist(a))
                self.s_artists.add(c)
            self.s_artists.setVisible(bool(arts))
            self.s_list.set_rows(self._lib_rows(found[:300]))
            return
        self.s_artists.setVisible(False)
        if self.s_hist.isChecked():
            items = sorted(((h.get("last", ""), int(h.get("count", 0)), p) for p, h in hist.items()), reverse=True)
            lbl.setText("Недавно слушали")
        else:
            items = sorted(((int(h.get("count", 0)), h.get("last", ""), p) for p, h in hist.items()), reverse=True)
            lbl.setText("Популярное у вас")
        bypath = {str(t.get("path", "")): t for t in lib}
        tracks = [bypath[p] for *_, p in items if p in bypath][:60]
        if not tracks:
            tracks = list(reversed(lib[-40:]))
            lbl.setText("Недавно добавленные")
        self.s_list.set_rows(self._lib_rows(tracks))

    # ── страница «Для вас» ───────────────────────────────────────────── #

    def _fill_foryou(self):
        page = self.pages["foryou"]
        spoken = self.__dict__.get('_spoken_panel')
        if spoken is not None:
            try:
                page.v.removeWidget(spoken)
            except RuntimeError:
                spoken = self._spoken_panel = None
        hero = self.__dict__.get("_fy_hero")
        try:                                           # баннер «Моя волна» переживает пересборку: его туманность
            if hero is not None:                       # на видеокарте создавалась заново (~150 мс на переходе);
                page.v.removeWidget(hero)              # родитель тот же — без пересоздания контекста OpenGL
        except RuntimeError:
            hero = self._fy_hero = None
        page.clear()
        w = self.win
        lib = w.library
        hr = time.localtime().tm_hour
        hello = ("Доброй ночи" if hr < 5 else "Доброе утро" if hr < 12 else "Добрый день" if hr < 18
                 else "Добрый вечер")
        nick = str(w.profile.get("nickname") or "").strip()
        h = QLabel(f"{hello}, {nick}" if nick and nick != "user" else hello); h.setObjectName("YaH1")
        page.v.addWidget(h)
        sub = QLabel("Подборки, тренды и то, что слушают друзья"); sub.setObjectName("YaSub")
        sub.setStyleSheet("font-size:13px;margin-bottom:10px;")
        page.v.addWidget(sub)
        try:                                           # живой баннер «▶ Моя волна» (туманность на C++)
            if hero is None:
                from ya_wave import WaveHero
                hero = self._fy_hero = WaveHero(w.engine)
                hero.clicked.connect(lambda: self.start_wave("my"))
            page.v.addWidget(hero)
            hero.show()
        except Exception as e:                         # noqa: BLE001
            print("[ya] wave hero:", e)

        try:                                           # Echoes.NET: друзья сейчас слушают / открытые комнаты
            self.pages["net"].add_friends_row(page)
        except Exception as e:                         # noqa: BLE001
            print("[ya] net row:", e)
        self._foryou_net(page)

        # подборки-миксы
        page.v.addWidget(section_title("Миксы и подборки"))
        row = card_row()
        mixes = [("Моя волна", "Всё, что вы любите", ("my", None), QColor("#ffd60a"), QColor("#e0218a")),
                 ("Настроение дня", "Время суток и погода", ("mood_day", None), QColor("#ff8a00"), QColor("#7a2cff")),
                 ("Трек дня", "Давно не слушали", ("track_day", None), QColor("#00d4ff"), QColor("#2b5bff"))]
        lib_cov = {str(t.get("path", "")): t.get("cover", "") for t in self.win.library if t.get("cover")}
        liked = [lib_cov.get(str(t.get("path", ""))) for t in (self.win.playlists.get(LIKED, {}).get("tracks") or [])]
        covs = list(lib_cov.values())
        mix_cov = {"my": [c for c in liked if c][-3:] or covs[:3], "mood_day": covs[3:6], "track_day": covs[-1:]}
        for title, sub, kind, c1, c2 in mixes:
            c = row.card(title, sub, size=150, mix=(c1, c2), mix_covers=mix_cov.get(kind[0]))
            c.clicked.connect(lambda k=kind: self.start_wave(*k))
        prof = self.profiles()
        if prof:
            fam_count = {}
            for pr in prof.values():
                for f in pr.get("families", [])[:1]:
                    fam_count[f] = fam_count.get(f, 0) + 1
            try:
                from music_intel import GENRE_RU
            except Exception:                        # noqa: BLE001
                GENRE_RU = {}
            fam_cov = {}
            for pth, pr in prof.items():
                for f in pr.get("families", [])[:1]:
                    if lib_cov.get(str(pth)) and len(fam_cov.setdefault(f, [])) < 3:
                        fam_cov[f].append(lib_cov[str(pth)])
            for f, n in sorted(fam_count.items(), key=lambda x: -x[1])[:6]:
                if n < 3:
                    continue
                hue = (hash(f) % 360) / 360.0
                c = row.card(GENRE_RU.get(f, f).capitalize(), f"{n} треков",
                         size=150, mix=(QColor.fromHsvF(hue, 0.85, 1.0), QColor.fromHsvF((hue + 0.3) % 1, 0.8, 0.8)),
                         mix_covers=fam_cov.get(f))
                c.clicked.connect(lambda f=f: self.start_wave("genre", f))
            for key, name, _fn, _hi in MOODS:
                hue = {"energy": 0.02, "calm": 0.55, "happy": 0.14, "sad": 0.66}[key]
                c = row.card(name, "Под настроение", size=150,
                         mix=(QColor.fromHsvF(hue, 0.85, 1.0), QColor.fromHsvF((hue + 0.12) % 1, 0.9, 0.7)))
                c.clicked.connect(lambda k=key: self.start_wave("mood", k))
        page.v.addWidget(row.widget_)

        import native_spoken
        if spoken is None:
            spoken = self._spoken_panel = native_spoken.create(w)
        if spoken is not None:
            page.v.addWidget(spoken)
            spoken.show()

        # плейлисты
        pls = [n for n in w.playlists if n not in AUTO_PLAYLISTS or n == "Настроение дня"]
        if pls:
            page.v.addWidget(section_title("Ваши плейлисты"))
            row = card_row()
            for n in pls:
                tr = w.playlists[n].get("tracks", [])
                cov = w.playlists[n].get("cover") or (tr[0].get("cover", "") if tr else "")
                c = row.card(n, f"{len(tr)} треков", cov, 150, seed=n)
                c.clicked.connect(lambda n=n: self.open_playlist(n))
            page.v.addWidget(row.widget_)

        # исполнители
        arts = {}
        for a, tracks in _artist_index(lib).groups():
            if a.lower() not in ("unknown artist", "неизвестный исполнитель"):
                arts[a] = [len(tracks), next((t.get("cover") for t in tracks if t.get("cover")), "")]
        top = sorted(arts.items(), key=lambda x: -x[1][0])[:16]
        if top:
            page.v.addWidget(section_title("Ваши исполнители"))
            row = card_row()
            for a, (n, cov) in top:
                c = row.card(a, f"{n} треков", cov, 130, circle=True)
                c.clicked.connect(lambda a=a: self.open_artist(a))
            page.v.addWidget(row.widget_)

        # недавно добавленные
        if lib:
            page.v.addWidget(section_title("Недавно добавленные"))
            row = card_row()
            idx_map = {str(t.get("path", "")): i for i, t in enumerate(lib)}
            for t in list(reversed(lib))[:18]:
                title = sanitize_title(t.get("title", ""))
                c = row.card(title, t.get("artist", ""), t.get("cover", ""), 150, seed=str(t.get("path", "")))
                c.clicked.connect(lambda i=idx_map[str(t.get("path", ""))]: self.win._play_index(i, "library"))
            page.v.addWidget(row.widget_)

        # давно не слушали
        hist = w.settings.get("play_history", {})
        old = sorted(lib, key=lambda t: hist.get(str(t.get("path", "")), {}).get("last", "0"))[:30]
        if old:
            page.v.addWidget(section_title("Вы могли забыть"))
            lv = TrackListView(self)
            lv.set_auto_height(True)
            lv.set_rows(self._lib_rows(old[:12]))
            page.v.addWidget(lv.section_widget())
        page.v.addStretch(1)

    # ── «Для вас»: тренды и рекомендации по всей медиатеке (ya_foryou) ── #

    FY_PL = "⁣foryou"                                 # скрытая очередь: тренды и рекомендации играют потоком

    def _foryou_net(self, page):
        import ya_foryou as F
        tt = F.taste(self.win)
        cache = F.load_cache()
        old_tr, old_rc = F.stale(cache, tt)
        trends = (cache.get("trends") or {}).get("data") or {}
        recs = (cache.get("recs") or {}).get("data") or {}
        retry_at = getattr(self, "_fy_retry_at", 0.0)
        if (old_tr or old_rc) and not getattr(self, "_fy_busy", False) and time.monotonic() >= retry_at:
            self._fy_busy = True
            # An empty/failed refresh rebuilds this page too. Back off before
            # starting the worker, so that rebuild cannot start a request loop.
            self._fy_retry_at = time.monotonic() + 60.0
            first = not (trends and recs)                  # пустая страница — перерисовать сразу, как придёт

            def work():
                try:
                    F.refresh(tt, old_tr, old_rc)
                except Exception as e:                     # noqa: BLE001
                    print("[foryou]", e)

                def done():
                    self._fy_busy = False
                    self._dirty.add("foryou")
                    if first and self._cur_page == "foryou":
                        self._rebuild("foryou")
                self.win._ui_bridge.call.emit(done)
            import threading as _th
            _th.Thread(target=work, daemon=True, name="foryou-net").start()

        now = [a for a, _ in tt["now"][:5]]
        if now:
            lbl = QLabel("Сейчас вы чаще всего слушаете: " + ", ".join(now))
            lbl.setObjectName("YaSub")
            lbl.setWordWrap(True)
            page.v.addWidget(lbl)

        if not trends and not recs:
            page.v.addWidget(section_title("Тренды и рекомендации"))
            wait = QLabel("Загружаю чарты и подбираю музыку по вашей коллекции…" if getattr(self, "_fy_busy", False)
                          else "Не получилось загрузить — нет интернета? Попробую при следующем открытии.")
            wait.setObjectName("YaSub")
            page.v.addWidget(wait)
            return

        import fy_feedback as FB
        fbs = getattr(self.win, "settings", None) or {}

        def track_row(title, tracks, genre="", rank=True):
            tracks = FB.shape(fbs, tracks, rank=rank)      # 👎 — убрать, 👍-исполнителей — вперёд
            if not tracks:
                return
            page.v.addWidget(section_title(title))
            row = card_row()
            pairs = []
            for i, t in enumerate(tracks):
                sub = t.get("artist", "")
                if t.get("because") and t["because"].startswith("похож"):
                    sub = f"{sub} · {t['because']}"
                c = row.card(t.get("title", ""), sub, "", 150, seed=f"{t.get('artist')}|{t.get('title')}")
                c.clicked.connect(lambda i=i, lst=tracks: self.win.stream_tracks(lst, start=i, playlist=self.FY_PL))
                hov = getattr(c, "hovered", None)
                if hov is not None:                            # навели — ссылку на поток готовим заранее
                    hov.connect(lambda t=t: self._stream_hint(t))
                self._fy_cover(c, t.get("cover_url", ""))
                pairs.append((c, t))
            page.v.addWidget(row.widget_)
            FB.bind(self, row, pairs, genre)

        ups, downs = FB.counts(fbs)
        if ups or downs:
            hint = QLabel(f"Лента учитывает ваши оценки: 👍 {ups} · 👎 {downs}. Наведите на карточку или нажмите "
                          "правой кнопкой — «больше такого» / «меньше такого».")
        else:
            hint = QLabel("Наведите на карточку: 👍 — больше такого, 👎 — меньше такого. Лента подстроится.")
        hint.setObjectName("YaSub")
        hint.setWordWrap(True)
        page.v.addWidget(hint)
        if ups or downs:
            rst = QPushButton("Сбросить оценки")
            rst.setObjectName("YaChip")
            rst.setCursor(Qt.CursorShape.PointingHandCursor)

            def _reset():
                FB.reset(self.win.settings)
                self.win.save_settings()
                self._rebuild("foryou")
            rst.clicked.connect(_reset)
            hr = QHBoxLayout()
            hr.addWidget(rst)
            hr.addStretch(1)
            page.v.addLayout(hr)

        if trends:
            track_row("Тренды · Чарт России", trends.get("ru") or [], rank=False)
            track_row("Тренды · Мировой чарт", trends.get("world") or [], rank=False)
            try:                                               # где эти треки на YouTube — заранее, в простое
                import stream_core
                warm = [stream_core.make_track(t) for t in ((trends.get("ru") or [])[:8] + (trends.get("world") or [])[:8])]
                QTimer.singleShot(4000, lambda w=warm: self.win.streams.warm_pages(w))
            except Exception as e:                             # noqa: BLE001
                print("[stream] warm:", e)
        if recs:
            arts = recs.get("artists") or []
            if arts:
                page.v.addWidget(section_title("Исполнители для вас"))
                row = card_row()
                for a in arts:
                    c = row.card(a["name"], "похож на " + " и ".join(a.get("because") or []), "", 130, circle=True)
                    c.clicked.connect(lambda n=a["name"]: self.open_artist(n))
                    self._fy_cover(c, a.get("pic", ""))
                page.v.addWidget(row.widget_)
            track_row("Треки для вас", recs.get("tracks") or [])
            track_row("Ещё от ваших исполнителей — этого нет в коллекции", recs.get("more") or [])
            for g in recs.get("genres") or []:
                track_row(f"Новое в жанре «{g['name']}» · {int(round(g['share'] * 100))} % вашей коллекции",
                          g.get("tracks") or [], genre=g["name"])

    def _fy_cover(self, card, url):
        if not url:
            return
        from ya_online import load_thumb

        def got(path, c=card):
            try:
                c.cover = path
                c.update()
            except RuntimeError:                           # страницу уже пересобрали
                pass
        load_thumb(self.win, url, got)

    # ── «Моя волна» ──────────────────────────────────────────────────── #

    def _build_wave(self):
        from ya_wave import WavePage
        pg = WavePage(self.win.engine)
        self.wave = pg
        pg.wheel.activated.connect(self._wheel_activated)
        pg.tune_btn.setIcon(ya_icon("settings", 18)); pg.tune_btn.setIconSize(QSize(18, 18))
        pg.tune_btn.clicked.connect(lambda: self._wave_tune_open(toggle=True))
        pg.title_clicked.connect(self._wave_play_clicked)              # «▶ Моя волна» — играть / пауза
        pg.reset_mood.connect(lambda: self.start_wave("my"))           # крестик на чипе настроения
        pg.prev_btn.setIcon(ya_icon("prev", 24)); pg.prev_btn.setIconSize(QSize(24, 24))
        pg.next_btn.setIcon(ya_icon("next", 24)); pg.next_btn.setIconSize(QSize(24, 24))
        pg.prev_btn.clicked.connect(self.win.prev_track)
        pg.next_btn.clicked.connect(self.win.next_track)
        pg.play_btn.setIconSize(QSize(26, 26))
        pg.play_btn.setIcon(ya_icon("play", 26, "#000000"))
        pg.play_btn.clicked.connect(self._wave_play_clicked)
        pg.like_btn.setIcon(ya_icon("heart", 20)); pg.like_btn.setIconSize(QSize(20, 20))
        pg.like_btn.clicked.connect(lambda: self.current_track() and self.toggle_like(self.current_track()))
        pg.more_btn.setIcon(ya_icon("dots", 20)); pg.more_btn.setIconSize(QSize(20, 20))
        pg.more_btn.clicked.connect(self._wave_menu)
        pg.set_mood("Моя волна", "my", None, instant=True)
        pg.hint.setText("Выберите настроение слева — волна подстроится")
        self.wave_play = pg.play_btn
        self._dirty.add("wave")
        return pg

    # ── «Настроить Мою волну» ── #
    def _wave_tune(self) -> dict:
        t = self.win.settings.get("wave_tune")
        return dict(t) if isinstance(t, dict) else {}

    def _wheel_activated(self, kind, arg=None):
        self.start_wave(kind, arg)
        if kind == "my":                       # «Назад к привычному» — и сразу окошко настроек, как в Яндексе
            self._wave_tune_open()

    def _wave_tune_open(self, toggle=False):
        from ya_wave_tune import WaveTunePopup
        pop = getattr(self, "_tune_pop", None)
        if pop is None:
            pop = self._tune_pop = WaveTunePopup(self.wave, self._wave_tune())
            pop.changed.connect(self._wave_tune_changed)
            self._tune_timer = QTimer(self)
            self._tune_timer.setSingleShot(True)
            self._tune_timer.timeout.connect(self._wave_tune_apply)
        if toggle and pop.isVisible():
            pop.hide()
            return
        pop.popup(self.wave.tune_btn)

    def _wave_tune_changed(self, tune):
        self.win.settings["wave_tune"] = dict(tune)
        try:
            self.win.save_settings()
        except Exception:                      # noqa: BLE001
            pass
        self._tune_timer.start(350)            # щёлкают подряд — пересобираем один раз

    def _wave_tune_apply(self):
        """Настройки поменялись: текущий трек доигрывает, дальше — уже новая подборка."""
        w = self.win
        playing_my = w.current_index >= 0 and w.queue_context == WAVE_PL and \
            (self._wave_kind or ("my",))[0] == "my"
        if not playing_my:
            self.start_wave("my")
            return
        tracks = w.playlists.get(WAVE_PL, {}).get("tracks", [])
        cur = tracks[w.current_index] if 0 <= w.current_index < len(tracks) else None
        out = self._wave_my_tracks(random.Random(), exclude=cur)
        w.playlists[WAVE_PL]["tracks"] = ([cur] if cur else []) + out[:59]
        w.current_index = 0 if cur else -1
        if getattr(w, "shuffle", False):
            try:
                w._build_shuffle_queue()
            except Exception:                  # noqa: BLE001
                pass
        w._ya_save_playlists()
        try:
            w._preload_adjacent()
        except Exception:                      # noqa: BLE001
            pass
        self._wave_set_hint("my", None, len(out[:59]) + (1 if cur else 0))
        self._wave_src = list(out)
        self._wave_discover(out[:20], "my")

    def _wave_my_tracks(self, rng, exclude=None) -> list:
        """«Моя волна» под настройки окошка: без повторов исполнителя подряд."""
        from ya_wave_tune import build_pool
        w = self.win
        lib = [t for t in w.library if not exclude or t.get("path") != exclude.get("path")]
        pool = build_pool(lib, self.profiles() or {}, w.settings.get("play_history", {}), self._liked_paths(),
                          self._wave_tune(), rng, artist_of=lambda t: _artist_main(t.get("artist", "")))
        out, rest = [], pool[:120]
        while rest and len(out) < 60:
            last = _artist_main(out[-1].get("artist", "")) if out else None
            j = next((k for k, t in enumerate(rest) if _artist_main(t.get("artist", "")) != last), 0)
            out.append(rest.pop(j))
        return out

    def _wave_set_hint(self, kind, arg, n):
        from ya_wave_tune import summary
        hints = {"my": "Всё, что вы любите, и немного нового", "fresh": "Треки, которые вы ещё не слушали",
                 "fav": "То, что вы слушаете чаще всего", "artist": f"Треки исполнителя {arg}",
                 "genre": "Подборка из вашей коллекции", "mood": "Подобрано по звучанию треков"}
        base = hints.get(kind, "")
        if kind == "my" and summary(self._wave_tune()):
            base = summary(self._wave_tune())
        self._wave_base_hint = f"{base}  ·  {n} треков"
        self.wave.hint.setText(self._wave_base_hint)

    def _wave_menu(self):
        m = QMenu(self)
        m.addAction("Настроить Мою волну", lambda: self._wave_tune_open())
        m.addAction("Очередь", self.win._show_queue_popup)
        m.addAction("Текст песни", self.toggle_lyrics)
        m.addAction("Клип песни", self.win._toggle_clip_mode)
        t = self.current_track()
        if t and _artist_main(t.get("artist", "")):
            a = _artist_main(t.get("artist", ""))
            m.addAction(f"Исполнитель: {a}", lambda: self.open_artist(a))
            m.addAction("Волна по исполнителю", lambda: self.start_wave("artist", a))
        if t and str(t.get("path", "")).startswith("stream:"):
            m.addSeparator()
            m.addAction("Скачать этот трек в коллекцию", self.win.stream_download_current)
        m.exec(QCursor.pos())

    @staticmethod
    def _blob_icon(c1: QColor, c2: QColor, shape: int) -> QIcon:
        pm = QPixmap(88, 88)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(0, 0, 88, 88)
        g.setColorAt(0, c1)
        g.setColorAt(1, c2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        path = QPainterPath()
        if shape == 0:                               # «X»-клякса
            pa = QPainterPath(); pa.addRoundedRect(QRectF(32, 6, 24, 76), 12, 12)
            t = QPainterPath(); t.addRoundedRect(QRectF(6, 32, 76, 24), 12, 12)
            path = pa.united(t)
            p.translate(44, 44); p.rotate(45); p.translate(-44, -44)
        elif shape == 1:                             # молния-«Z»
            path.moveTo(14, 16); path.lineTo(74, 10); path.lineTo(38, 46); path.lineTo(76, 44)
            path.lineTo(14, 80); path.lineTo(46, 44); path.lineTo(18, 46); path.closeSubpath()
        else:                                        # капля
            path.addEllipse(QRectF(10, 14, 68, 62))
        p.drawPath(path)
        p.end()
        return QIcon(pm)

    def _wave_arts_check(self):
        """Сменились «ваши исполнители сейчас» — список «Моей волны» пересоберётся при следующем открытии
        (или сразу, если волна открыта, а список не крутят)."""
        try:
            import ya_foryou
            sig = tuple(ya_foryou.now_artists(self.win, 4))
        except Exception:                                  # noqa: BLE001
            return
        if sig == getattr(self, "_wave_arts_sig", None):
            return
        self._dirty.add("wave")
        if self._cur_page == "wave" and not self.wave.underMouse():
            self._rebuild("wave")

    def _fill_wave_list(self):
        from ya_wave import palette_for
        items = []
        prof = self.profiles()
        try:
            from music_intel import GENRE_RU
        except Exception:                            # noqa: BLE001
            GENRE_RU = {}
        genres = []
        if prof:
            fam_count = {}
            for pr in prof.values():
                for f in pr.get("families", [])[:1]:
                    fam_count[f] = fam_count.get(f, 0) + 1
            genres = [f for f, n in sorted(fam_count.items(), key=lambda x: -x[1]) if n >= 3][:8]

        def genre_item(f):
            core, halo, ray = palette_for("genre", f)
            icon = f"genre:{f}" if f in __import__("ya_wave")._GENRE_SHAPE else "bolt"   # свой значок у жанра
            return {"kind": "genre", "arg": f, "label": GENRE_RU.get(f, f).capitalize(),
                    "icon": icon, "c1": ray, "c2": halo}

        def mood_item(key, name):
            core, halo, ray = palette_for("mood", key)
            return {"kind": "mood", "arg": key, "label": name, "icon": f"mood:{key}", "c1": ray, "c2": halo}

        for f in genres[:3]:
            items.append(genre_item(f))
        names = {m[0]: m[1] for m in MOODS}
        items.append(mood_item("energy", names["energy"]))
        core, halo, ray = palette_for("mood_day")
        items.append({"kind": "mood_day", "arg": None, "label": "Настроение дня", "icon": "mood:mood_day",
                      "c1": ray, "c2": halo})
        back_index = len(items)
        items.append({"kind": "my", "arg": None, "label": "Назад к привычному", "icon": "back",
                      "accent": True})
        # исполнители — те, кого вы СЕЙЧАС часто слушаете (последние прослушивания), а не навсегда самые частые
        import ya_foryou
        top_arts = ya_foryou.now_artists(self.win, 4)
        self._wave_arts_sig = tuple(top_arts)

        def artist_item(a):
            cov = next((t.get("cover", "") for t in self.win.library
                        if _artist_main(t.get("artist", "")) == a and t.get("cover")), "")
            return {"kind": "artist", "arg": a, "label": a, "sub": "Артист", "icon": "artist",
                    "cover": cov or "", "c1": "#444", "c2": "#222"}

        if top_arts:
            items.append(artist_item(top_arts[0]))
        items.append(mood_item("calm", names["calm"]))
        for f in genres[3:5]:
            items.append(genre_item(f))
        if len(top_arts) > 1:
            items.append(artist_item(top_arts[1]))
        items.append(mood_item("happy", names["happy"]))
        items.append(mood_item("sad", names["sad"]))
        core, halo, ray = palette_for("fresh")
        items.append({"kind": "fresh", "arg": None, "label": "Незнакомое", "icon": "mood:fresh", "c1": ray, "c2": halo})
        for a in top_arts[2:]:
            items.append(artist_item(a))
        core, halo, ray = palette_for("fav")
        items.append({"kind": "fav", "arg": None, "label": "Любимое", "icon": "mood:fav", "c1": ray, "c2": halo})
        for f in genres[5:]:
            items.append(genre_item(f))
        self.wave.wheel.set_items(items)
        self.wave.wheel.off = self.wave.wheel.target = float(back_index)
        if self._wave_kind:
            self.wave.wheel.set_active(tuple(self._wave_kind))

    def _wave_play_clicked(self):
        w = self.win
        in_wave = w.current_index >= 0 and w.queue_context == WAVE_PL
        if in_wave:
            w.toggle_play()                    # волна уже идёт — обычная пауза / продолжить
        else:
            # волна не играет: каждый раз собираем новую и начинаем со случайного трека
            kind, arg = self._wave_kind if self._wave_kind and self._wave_kind[0] not in ("mood_day", "track_day")                 else ("my", None)
            self.start_wave(kind, arg)

    def start_wave(self, kind, arg=None):
        """Собрать очередь «волны» и запустить."""
        w = self.win
        lib = list(w.library)
        if not lib:
            return
        if kind == "mood_day":
            w._build_smart_playlist()
            self._wave_kind = ("mood_day", None)
            self.wave.set_mood("Настроение дня", "mood_day", None)
            self.wave.wheel.set_active(("mood_day", None))
            self.wave.hint.setText("Время суток, погода и звучание ваших треков")
            self.show_page("wave")
            return
        if kind == "track_day":
            w._play_track_of_the_day()
            return
        prof = self.profiles() or {}
        hist = w.settings.get("play_history", {})
        rng = random.Random()
        name = "Моя волна"
        pool = lib
        if kind == "mood" and prof:
            fn, hi = next((m[2], m[3]) for m in MOODS if m[0] == arg)
            scored = [(fn(prof[str(t.get("path", ""))]), t) for t in lib if str(t.get("path", "")) in prof]
            scored.sort(key=lambda x: -x[0] if hi else x[0])
            pool = [t for _, t in scored[:max(20, len(scored) // 3)]]
            name = next(m[1] for m in MOODS if m[0] == arg)
        elif kind == "genre" and prof:
            pool = [t for t in lib if arg in prof.get(str(t.get("path", "")), {}).get("families", [])[:2]]
            try:
                from music_intel import GENRE_RU
                name = GENRE_RU.get(arg, arg).capitalize()
            except Exception:                        # noqa: BLE001
                name = arg
        elif kind == "fresh":
            pool = [t for t in lib if int(hist.get(str(t.get("path", "")), {}).get("count", 0)) == 0] or lib
            name = "Незнакомое"
        elif kind == "fav":
            pool = sorted(lib, key=lambda t: -int(hist.get(str(t.get("path", "")), {}).get("count", 0)))[:60]
            name = "Любимое"
        elif kind == "artist":
            pool = [t for t in lib if _is_by(t, arg)]       # только его треки (и где он приглашён)
            name = arg
        elif kind == "my" and self._wave_tune():
            name = "Моя волна"                       # с настройками окошка «Настроить Мою волну»
            from ya_wave_tune import build_pool
            pool = build_pool(lib, prof, hist, self._liked_paths(), self._wave_tune(), rng,
                              artist_of=lambda t: _artist_main(t.get("artist", "")))
        elif kind == "my":
            name = "Моя волна"
            # взвешенная случайная выборка: любимое выпадает чаще, но порядок и первый трек — каждый раз новые
            # (ключ Efraimidis–Спиракиса: rand^(1/вес)); без повторов исполнителя подряд — ниже
            pool = sorted(lib, key=lambda t: -(rng.random() ** (1.0 / (1.0 + int(
                hist.get(str(t.get("path", "")), {}).get("count", 0)) ** 0.5))))
        pool = list(pool) or (lib if kind != "artist" else [])
        self._wave_src = list(pool)                  # из неё волна продолжается, когда очередь подходит к концу
        if kind != "my":
            rng.shuffle(pool)
        # без двух одинаковых исполнителей подряд
        out = []
        rest = pool[:]
        while rest and len(out) < 60:
            last = _artist_main(out[-1].get("artist", "")) if out else None
            j = next((k for k, t in enumerate(rest) if _artist_main(t.get("artist", "")) != last), 0)
            out.append(rest.pop(j))
        # первый трек — случайный из начала подборки и не тот, что только что играл
        cur = w.library[w.current_index] if (w.queue_context == "library" and 0 <= w.current_index < len(w.library))             else None
        if len(out) > 1:
            head = [t for t in out[:min(len(out), 12)] if not cur or t.get("path") != cur.get("path")] or out[:1]
            first = rng.choice(head)
            out.remove(first)
            out.insert(0, first)
        w.playlists[WAVE_PL] = {"tracks": out, "desc": f"auto: {name}", "cover": ""}
        w._ya_save_playlists()
        self._wave_kind = (kind, arg)
        self.wave.set_mood(name, kind, arg)
        self.wave.wheel.set_active((kind, arg))
        hints = {"my": "Всё, что вы любите, и немного нового", "fresh": "Треки, которые вы ещё не слушали",
                 "fav": "То, что вы слушаете чаще всего", "artist": f"Треки исполнителя {arg}",
                 "genre": f"{name}: подборка из вашей коллекции", "mood": "Подобрано по звучанию треков"}
        base = hints.get(kind, "")
        if kind == "my" and self._wave_tune():
            from ya_wave_tune import summary
            base = summary(self._wave_tune()) or base
        self._wave_base_hint = f"{base}  ·  {len(out)} треков"
        self.wave.hint.setText(self._wave_base_hint)
        w._play_index(0, WAVE_PL)
        self.show_page("wave")
        self._wave_discover(out, name)

    # ── новые похожие треки в волне: онлайн, потоком, без скачивания ──────── #
    #
    # Волна задумана как в Яндекс Музыке: бесконечная, со «знакомым» из коллекции и новым из сети,
    # и сразу без задержек. Новое берётся из радио YouTube Music / «похожих» SoundCloud по трекам
    # волны и играет потоком (stream_core): ссылки на поток следующих треков готовятся заранее.
    #   • доля нового — от характера волны: «Незнакомое» — половина, «Любимое» — немного, обычно — треть;
    #   • пропустили новый трек в первые 25 с — его исполнитель больше не подмешивается;
    #   • дослушали новый трек (или лайкнули) — он становится «семенем»: следующее новое похоже на него;
    #   • очередь сама продолжается: и коллекцией, и новым из сети — волна не кончается.

    NEW_SHARE = {"fresh": 0.5, "fav": 0.15, "popular": 0.3, "artist": 0.34}

    def _wave_new_share(self) -> float:
        kind = (self._wave_kind or ("my",))[0]
        if kind in self.NEW_SHARE:
            return self.NEW_SHARE[kind]
        ch = (self._wave_tune() or {}).get("character")
        return self.NEW_SHARE.get(ch, 0.34)

    def _wave_discover(self, pool, name):
        """Новое из сети под эту волну: радио по 5 «семенам» из её начала."""
        self._disc_gen = getattr(self, "_disc_gen", 0) + 1
        self._disc_pool, self._disc_pending, self._disc_added = [], 0, 0
        self._disc_seen = set()
        self._disc_fetching = False
        self._disc_seeded = set()
        self._wave_skip_artists = set()
        self._wave_good = []
        self._wave_last = None
        if not pool:
            return
        seeds = [t for t in pool if (t.get("artist") or "").strip()][:5] or pool[:3]
        self._disc_fetch(seeds)

    def _disc_fetch(self, seeds):
        """Фоном: «похожие» по семенам → пул нового (без того, что есть в коллекции и уже было в волне)."""
        if getattr(self, "_disc_fetching", False) or not seeds:
            return
        self._disc_fetching = True
        gen = self._disc_gen
        lib = list(self.win.library)
        seen = set(self._disc_seen)
        skip = set(self._wave_skip_artists)
        wk = self._wave_kind or ("my", None)
        only = wk[1] if wk[0] == "artist" else None       # волна по исполнителю: новое — только его же треки
        seeds = [s for s in seeds if str(s.get("path", "")) not in self._disc_seeded][:5]
        for s in seeds:
            self._disc_seeded.add(str(s.get("path", "")))
        win = self.win

        def work():
            out = []
            try:
                import online_search
                from track_identity import norm as _n
                have = {(_n(_artist_main(x.get("artist", ""))), _n(sanitize_title(x.get("title", "")))) for x in lib}
                have_t = {k[1] for k in have}
                per_seed = []
                if only:
                    songs = []
                    try:
                        bid = online_search.ytm_artist_id(only)
                        songs = online_search.ytm_all_songs(bid) if bid else []
                        if not songs:
                            sid = online_search.sc_artist_id(only)
                            songs = online_search.sc_all_songs(sid) if sid else []
                    except Exception as e:               # noqa: BLE001
                        print("[wave artist] songs:", e)
                    lst = [t for t in songs if _is_by(t, only)
                           and (_n(_artist_main(t.get("artist", ""))), _n(t.get("title", ""))) not in have
                           and _n(t.get("title", "")) not in have_t and 60 <= (t.get("duration") or 180) <= 600
                           and not t.get("snip")]
                    random.shuffle(lst)
                    per_seed.append(lst)
                # раньше здесь было seeds = [] — переменная становилась локальной для всей work(), и в любой
                # волне, кроме «по исполнителю», поток падал на первой строке цикла (новое из сети не приходило)
                for sd in ([] if only else seeds):
                    if gen != self._disc_gen:
                        return
                    try:
                        rel = online_search.radio(sanitize_title(sd.get("title", "")),
                                                  _artist_main(sd.get("artist", "")), 25)
                    except Exception as e:               # noqa: BLE001
                        print("[wave new] radio:", e)
                        rel = []
                    lst = []
                    for t in rel:
                        a = _artist_main(t.get("artist", ""))
                        key = (_n(a), _n(t.get("title", "")))
                        if key in have or key[1] in have_t or key in seen or _n(a) in skip:
                            continue
                        if not 60 <= (t.get("duration") or 180) <= 600 or t.get("snip"):
                            continue                     # миксы, часовые видео, 30-секундные превью — мимо
                        lst.append(t)
                    per_seed.append(lst)
                for k in range(max([len(x) for x in per_seed] + [0])):    # чередуем семена
                    for lst in per_seed:
                        if k < len(lst):
                            t = lst[k]
                            key = (_n(_artist_main(t.get("artist", ""))), _n(t.get("title", "")))
                            if key not in seen:
                                seen.add(key)
                                out.append(t)
            finally:
                win._ui_bridge.call.emit(lambda: self._disc_ready(gen, out))
        _threading.Thread(target=work, daemon=True).start()

    def _disc_ready(self, gen, cands):
        self._disc_fetching = False
        if gen != self._disc_gen:
            return
        try:
            from track_identity import norm as _n
            for t in cands:
                self._disc_seen.add((_n(_artist_main(t.get("artist", ""))), _n(t.get("title", ""))))
        except Exception:                                # noqa: BLE001
            pass
        wk = self._wave_kind or ("my", None)
        if wk[0] == "artist":                            # никаких чужих треков в волне исполнителя
            cands = [t for t in cands if _is_by(t, wk[1])]
        self._disc_pool.extend(cands)
        del self._disc_pool[:-80]
        self._update_wave_hint()
        self._disc_feed()

    def _disc_feed(self):
        """Подмешать новое в ближайшие треки волны (потоком) и продлить волну, если кончается."""
        w = self.win
        if w.queue_context != WAVE_PL:
            return
        pl = w.playlists.get(WAVE_PL)
        if not pl:
            return
        tracks = pl["tracks"]
        cur = max(0, w.current_index)
        changed = self._wave_extend_local(tracks, cur)
        share = self._wave_new_share()
        gap = max(1, round((1 - share) / share))         # сколько знакомых между новыми
        import stream_core
        try:
            from track_identity import norm as _n
        except Exception:                                # noqa: BLE001
            _n = str.lower
        i, run, end = cur + 1, 0, min(len(tracks), cur + 13)
        while i < end and self._disc_pool:
            if tracks[i].get("wave_new"):
                run = 0
                i += 1
                continue
            run += 1
            if run > gap:
                t = self._disc_pool.pop(0)
                if _n(_artist_main(t.get("artist", ""))) in self._wave_skip_artists:
                    continue
                item = stream_core.make_track(t)
                item["wave_new"] = True
                tracks.insert(i, item)
                if w.shuffle and w._shuffle_queue:
                    w._build_shuffle_queue()
                self._disc_added += 1
                changed = True
                run = 0
                end = min(len(tracks), cur + 13)
            i += 1
        if changed:
            w._ya_save_playlists()
            w._stream_prefetch()                         # ссылки на поток ближайших — заранее
        if len(self._disc_pool) < 6:                     # новое кончается — ещё похожих, по тому, что зашло
            seeds = list(reversed(self._wave_good[-4:])) + [t for t in tracks[max(0, cur - 3):cur + 1]
                                                           if not str(t.get("path", "")).startswith("stream:")]
            self._disc_fetch(seeds)
        self._update_wave_hint()

    def _wave_extend_local(self, tracks, cur) -> bool:
        """Бесконечная волна: осталось мало — дописать треками коллекции из той же подборки."""
        if len(tracks) - cur - 1 >= 8:
            return False
        src = getattr(self, "_wave_src", None) or list(self.win.library)
        if not src:
            return False
        recent = {str(t.get("path", "")) for t in tracks[-40:]}
        rng = random.Random()
        cand = [t for t in src if str(t.get("path", "")) not in recent] or list(src)
        rng.shuffle(cand)
        last = _artist_main(tracks[-1].get("artist", "")) if tracks else None
        added = 0
        while cand and added < 20:
            j = next((k for k, t in enumerate(cand) if _artist_main(t.get("artist", "")) != last), 0)
            t = cand.pop(j)
            tracks.append(t)
            last = _artist_main(t.get("artist", ""))
            added += 1
        if len(tracks) > 400:                            # хвост истории волны не копим бесконечно
            cut = min(len(tracks) - 400, max(0, cur - 20))
            if cut > 0:
                del tracks[:cut]
                self.win.current_index = cur - cut
                if self.win.shuffle:
                    self.win._build_shuffle_queue()
        return added > 0

    def _wave_track_feedback(self, t):
        """Смена трека в волне: что было с прошлым — пропустили новое или дослушали."""
        last, self._wave_last = getattr(self, "_wave_last", None), (t, time.monotonic())
        if not last or self.win.queue_context != WAVE_PL:
            return
        pt, t0 = last
        if pt is None or pt is t:
            return
        played = time.monotonic() - t0
        dur = float(pt.get("duration") or 0)
        try:
            from track_identity import norm as _n
        except Exception:                                # noqa: BLE001
            _n = str.lower
        if pt.get("wave_new") and played < 25:
            a = _n(_artist_main(pt.get("artist", "")))
            self._wave_skip_artists.add(a)
            self._disc_pool = [x for x in self._disc_pool if _n(_artist_main(x.get("artist", ""))) != a]
        elif dur and played >= dur * 0.7:
            self._wave_good.append(pt)                   # зашло — следующее новое будет похоже на это
            del self._wave_good[:-12]

    def wave_like_seed(self, t):
        """Лайк в волне — сильное «семя» для нового."""
        if self.win.queue_context == WAVE_PL and t is not None:
            self._wave_good.append(t)
            self._disc_fetch([t])

    def _update_wave_hint(self):
        base = getattr(self, "_wave_base_hint", "")
        extra = ""
        if self._disc_added or self._disc_pool:
            extra = f"  ·  + новое для вас: {self._disc_added}"
        t = self.current_track()
        try:                                          # страницу волны могли пересоздать, пока шёл поиск нового
            if t is not None and t.get("wave_new"):
                m = f" · совпадение {t['match']}%" if t.get("match") else ""
                self.wave.hint.setText("Новое для вас · онлайн, похоже на то, что вы слушаете" + m + extra)
            else:
                self.wave.hint.setText(base + extra)
        except RuntimeError:
            pass

    # ── «Коллекция» ──────────────────────────────────────────────────── #

    def _build_collection(self):
        page = QWidget(); page.setObjectName("YaPage")
        v = QVBoxLayout(page)
        v.setContentsMargins(32, 22, 24, 10)
        v.setSpacing(10)
        top = QHBoxLayout()
        self.c_title = QLabel("Коллекция"); self.c_title.setObjectName("YaH1")
        top.addWidget(self.c_title)
        top.addSpacing(10)
        self.c_shuffle = QPushButton("  Перемешать")              # слушать всю коллекцию (с фильтром) вперемешку
        self.c_shuffle.setObjectName("AccentBtn")
        self.c_shuffle.setIcon(ya_icon("shuffle", 18, "#000000"))
        self.c_shuffle.setMinimumHeight(38)
        self.c_shuffle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.c_shuffle.clicked.connect(self._coll_shuffle)
        top.addWidget(self.c_shuffle)
        self.c_sort = self._sort_button(lambda b: __import__("track_sort").menu(
            b, self.win.settings.get("sort_coll") or "default", self._set_coll_sort, collection=True))
        top.addWidget(self.c_sort)
        top.addStretch(1)
        self.c_search = QLineEdit()
        self.c_search.setPlaceholderText("Поиск в коллекции")
        self.c_search.setMinimumWidth(110)                     # в узком окне поле сжимается, а не уезжает
        self.c_search.setMaximumWidth(230)                     # под кнопку «+»
        self.c_search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.c_search.addAction(ya_icon("search", 16, "#8a8a8a"), QLineEdit.ActionPosition.LeadingPosition)
        self.c_search.textChanged.connect(lambda _: self._coll_apply())
        top.addWidget(self.c_search, 100)                      # растёт первым (до 230), остальное — отступу
        for ic, tip, fn in (("plus", "Добавить файлы", self.win._add_files),
                            ("folder", "Добавить папку", self.win._add_folder),
                            ("download", "Скачать по ссылке", self.win._open_downloader)):
            b = icon_button(ic, tip, 38, 20)
            b.clicked.connect(fn)
            top.addWidget(b)
        v.addLayout(top)
        self.c_chips_w = QWidget(); self.c_chips_w.setObjectName("YaPage")
        self.c_chips = QHBoxLayout(self.c_chips_w)
        self.c_chips.setContentsMargins(0, 0, 0, 0)
        self.c_chips.setSpacing(8)
        # фильтров больше, чем влезает: лента прокручивается вбок (колесом тоже), пилюли не сжимаются
        cs = QScrollArea()
        cs.setWidgetResizable(True)
        cs.setFrameShape(QFrame.Shape.NoFrame)
        cs.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        cs.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        cs.setFixedHeight(46)
        cs.setWidget(self.c_chips_w)
        cs.viewport().setAutoFillBackground(False)

        def _chips_wheel(e, sb=cs.horizontalScrollBar()):
            d = e.angleDelta().y() or e.angleDelta().x()
            sb.setValue(sb.value() - d)
        cs.wheelEvent = _chips_wheel
        v.addWidget(cs)
        self.c_list = TrackListView(self)
        self.c_selbar = SelectionBar(self, self.c_list)
        v.addWidget(self.c_selbar)
        v.addWidget(self.c_list, 1)
        self.c_count = QLabel(""); self.c_count.setObjectName("YaSub")
        v.addWidget(self.c_count)
        self._dirty.add("collection")
        return page

    def _fill_collection(self):
        _clear_layout(self.c_chips)
        previous=getattr(self,'_collection_group',None)
        if previous is not None:previous.deleteLater()
        g = QButtonGroup(self.c_chips_w)
        self._collection_group=g
        g.setExclusive(True)
        opts = [("all", None, "Всё"), ("liked", None, "Мне нравится")]
        prof = self.profiles()
        if prof:
            opts += [("mood", m[0], m[1]) for m in MOODS]
            try:
                from music_intel import GENRE_RU
            except Exception:                        # noqa: BLE001
                GENRE_RU = {}
            fam_count = {}
            for pr in prof.values():
                for f in pr.get("families", [])[:1]:
                    fam_count[f] = fam_count.get(f, 0) + 1
            for f, n in sorted(fam_count.items(), key=lambda x: -x[1])[:7]:
                if n >= 3:
                    opts.append(("genre", f, GENRE_RU.get(f, f).capitalize()))
        for kind, arg, text in opts:
            b = chip(text)
            b.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            g.addButton(b)
            b.setChecked((kind, arg) == self._coll_filter)
            b.clicked.connect(lambda _=False, k=kind, a=arg: self._set_coll_filter(k, a))
            self.c_chips.addWidget(b)
        self.c_chips.addStretch(1)
        if prof is None:
            note = QLabel("жанры и настроения появятся после анализа библиотеки")
            note.setObjectName("YaSub")
            self.c_chips.addWidget(note)
        self._coll_apply()

    # ── обложка в плеере: найти трек в коллекции ── #

    def _p_cover_press(self, e):
        t = self.current_track()
        if e.button() == Qt.MouseButton.RightButton:
            m = QMenu(self)
            m.addAction("Сейчас играет — на весь экран  (Ctrl+Shift+N)", self.open_now_playing)
            m.addAction("Найти в коллекции", lambda: self.find_in_collection(t))
            if t is not None:
                self.win.reveal_action(m, t)
            m.addAction("Текст песни", self.toggle_lyrics)
            m.addAction("Версии трека… (slowed, sped up, remix)", lambda: __import__("ya_versions").open_versions(self))
            m.addAction("Мини-плеер поверх окон  (Ctrl+Alt+N)", lambda: __import__("ya_quick").toggle_mini(self.win))
            m.addAction("Палитра команд  (Ctrl+K)", lambda: __import__("ya_quick").open_palette(self.win))
            m.exec(QCursor.pos())
            return
        if e.button() == Qt.MouseButton.LeftButton:
            self.open_now_playing()

    # ── «Сейчас играет» во всё окно (now_playing.py) ── #

    def now_playing_open(self) -> bool:
        np_ = self.__dict__.get("_now_playing")
        return bool(np_ is not None and np_.is_open())

    def open_now_playing(self, mode=None):
        np_ = self.__dict__.get("_now_playing")
        if np_ is None:
            from now_playing import NowPlaying
            np_ = self._now_playing = NowPlaying(self)
        np_.open(mode)

    def close_now_playing(self, instant=False):
        np_ = self.__dict__.get("_now_playing")
        if np_ is not None:
            np_.close_mode(instant=instant)

    def toggle_now_playing(self):
        if self.now_playing_open():
            self.close_now_playing()
        else:
            self.open_now_playing()

    def find_in_collection(self, t=None):
        """Открыть «Коллекцию» на этом треке: сбросить поиск и фильтр, прокрутить, выделить."""
        t = t if t is not None else self.current_track()
        if t is None:
            return
        p = str(t.get("path", ""))
        if p.startswith("stream:"):
            self.win._toast("Трек играет онлайн — в коллекции его нет. Скачать: меню волны или кнопка у трека")
            return
        if not any(str(x.get("path", "")) == p for x in self.win.library):
            self.win._toast("Этого трека нет в коллекции")
            return
        self.show_page("collection")
        if self._coll_filter != ("all", None) or self.c_search.text():
            self.c_search.blockSignals(True)
            self.c_search.clear()
            self.c_search.blockSignals(False)
            self._coll_filter = ("all", None)
            self._fill_collection()
        QTimer.singleShot(0, lambda: self._coll_select(p))

    def _coll_select(self, path):
        lst = self.c_list
        rows = getattr(lst.model_, "rows", [])
        i = next((k for k, r in enumerate(rows) if str((r.get("t") or {}).get("path", "")) == path), -1)
        if i < 0:
            return
        idx = lst.model_.index(i, 0)
        lst.clearSelection()
        lst.setCurrentIndex(idx)
        lst.scrollTo(idx, QAbstractItemView.ScrollHint.PositionAtCenter)
        lst.setFocus()

    def _set_coll_filter(self, kind, arg):
        self._coll_filter = (kind, arg)
        self._coll_apply()

    def _coll_apply(self):
        kind, arg = self._coll_filter
        lib = self.win.library
        prof = self._profiles or {}
        if kind == "liked":
            tracks = self.win.playlists.get(LIKED, {}).get("tracks", [])
            rows = [{"t": t, "ctx": LIKED, "i": i} for i, t in enumerate(tracks)]
        else:
            if kind == "mood" and prof:
                fn, hi = next((m[2], m[3]) for m in MOODS if m[0] == arg)
                sc = [(fn(prof[str(t.get("path", ""))]), i, t) for i, t in enumerate(lib)
                      if str(t.get("path", "")) in prof]
                sc = [x for x in sc if (x[0] >= 0.58 if hi else x[0] <= 0.42)]
                sc.sort(key=lambda x: -x[0] if hi else x[0])
                rows = [{"t": t, "ctx": "library", "i": i} for _, i, t in sc]
            elif kind == "genre" and prof:
                rows = [{"t": t, "ctx": "library", "i": i} for i, t in enumerate(lib)
                        if arg in prof.get(str(t.get("path", "")), {}).get("families", [])[:2]]
            else:
                rows = [{"t": t, "ctx": "library", "i": i} for i, t in enumerate(lib)]
                rows.reverse()                       # новые сверху
        key = (getattr(self.win, "settings", None) or {}).get("sort_coll") or "default"
        if key != "default":                          # своя сортировка (track_sort)
            import track_sort
            own = kind in ("liked", "mood", "genre")   # у фильтров свой порядок, у «Всё» — «новые сверху»
            base = rows if own else list(reversed(rows))
            rows = list(base) if key == "reverse" and not own else track_sort.apply(base, key, self.win)
        if getattr(self, "c_sort", None) is not None:
            self._sort_btn_text(self.c_sort, key, True)
        q = self.c_search.text().strip().lower()
        if q:
            from search_util import track_matches
            rows = [r for r in rows if track_matches(q, r["t"])]
        self.c_list.set_rows(rows)
        self.c_count.setText(f"{len(rows)} треков  ·  Ctrl/Shift + клик — выделить несколько, "
                             f"Ctrl+A — все, Delete — удалить выделенные")

    # ── альбомы (треки с одинаковым тегом «альбом») ──────────────────── #

    def album_index(self):
        """{ключ: {name, artist, tracks, cover}} — группы треков коллекции по тегу «альбом»."""
        groups = {}
        for t in self.win.library:
            a = " ".join(str(t.get("album") or "").split())
            if a.lower() in _NO_ALBUM:
                continue
            groups.setdefault(a.lower(), []).append(t)
        out = {}
        for k, ts in groups.items():
            names = {}
            for t in ts:
                n = " ".join(str(t.get("album")).split())
                names[n] = names.get(n, 0) + 1
            arts = {}
            for t in ts:
                a = _artist_main(t.get("artist", "")) or "Неизвестный исполнитель"
                arts[a] = arts.get(a, 0) + 1
            top_a, n_a = max(arts.items(), key=lambda x: x[1])
            cover = next((t.get("cover") for t in ts if t.get("cover") and Path(t["cover"]).exists()), "")
            out[k] = {"key": k, "name": max(names.items(), key=lambda x: x[1])[0],
                      "artist": top_a if n_a >= len(ts) * 0.6 else "Разные исполнители",
                      "tracks": ts, "cover": cover,
                      "dur": sum(float(t.get("duration") or 0) for t in ts)}
        return out

    def _build_albums(self):
        page = QWidget(); page.setObjectName("YaPage")
        v = QVBoxLayout(page)
        v.setContentsMargins(32, 22, 24, 10)
        v.setSpacing(10)
        top = QHBoxLayout()
        h = QLabel("Альбомы"); h.setObjectName("YaH1")
        top.addWidget(h)
        top.addStretch(1)
        self.al_singles = QCheckBox("показывать синглы")
        self.al_singles.setChecked(bool(self.win.settings.get("ya_album_singles", False)))
        self.al_singles.setToolTip("Альбомы, в которых у вас всего один трек")
        self.al_singles.toggled.connect(self._albums_singles)
        top.addWidget(self.al_singles)
        self.al_sort = QComboBox()
        for txt, key in (("По названию", "name"), ("По исполнителю", "artist"), ("Больше треков", "count"),
                         ("Недавно добавленные", "recent")):
            self.al_sort.addItem(txt, key)
        self.al_sort.setCurrentIndex(max(0, self.al_sort.findData(self.win.settings.get("ya_album_sort", "name"))))
        self.al_sort.currentIndexChanged.connect(lambda _: self._albums_apply())
        top.addWidget(self.al_sort)
        self.al_search = QLineEdit()
        self.al_search.setPlaceholderText("Альбом или исполнитель")
        self.al_search.setFixedWidth(220)
        self.al_search.addAction(ya_icon("search", 16, "#8a8a8a"), QLineEdit.ActionPosition.LeadingPosition)
        self.al_search.textChanged.connect(lambda _: self._albums_apply())
        top.addWidget(self.al_search)
        v.addLayout(top)
        self.al_grid = card_grid()
        v.addWidget(self.al_grid.widget_, 1)
        self.al_count = QLabel(""); self.al_count.setObjectName("YaSub")
        v.addWidget(self.al_count)
        self._albums = {}
        self._dirty.add("albums")
        return page

    def _albums_singles(self, on):
        self.win.settings["ya_album_singles"] = bool(on)
        self._albums_apply()

    def _fill_albums(self):
        self._albums = self.album_index()
        self._albums_apply()

    def _albums_apply(self):
        sort = self.al_sort.currentData() or "name"
        self.win.settings["ya_album_sort"] = sort
        q = self.al_search.text().strip().lower()
        singles = self.al_singles.isChecked()
        items = [a for a in self._albums.values() if singles or len(a["tracks"]) >= 2]
        if q:
            from search_util import matches
            items = [a for a in items if matches(q, a["name"], a["artist"],
                                                 " ".join(t.get("artist") or "" for t in a["tracks"]))]
        if sort == "artist":
            items.sort(key=lambda a: (a["artist"].lower(), a["name"].lower()))
        elif sort == "count":
            items.sort(key=lambda a: (-len(a["tracks"]), a["name"].lower()))
        elif sort == "recent":
            pos = {id(t): i for i, t in enumerate(self.win.library)}
            items.sort(key=lambda a: -max(pos.get(id(t), 0) for t in a["tracks"]))
        else:
            items.sort(key=lambda a: a["name"].lower())
        self.al_grid.clear()
        for a in items:
            n = len(a["tracks"])
            c = self.al_grid.card(a["name"], f"{a['artist']} · {n} {_plural(n, 'трек', 'трека', 'треков')}",
                                  a["cover"], 160, seed=a["name"])
            c.clicked.connect(lambda k=a["key"]: self.open_album(k))
        self.al_grid.done()
        total = len(self._albums)
        if not self._albums:
            self.al_count.setText("Альбомы появятся, когда у треков будет заполнен тег «альбом» "
                                  "(у скачанных с YouTube Music он ставится сам)")
        else:
            self.al_count.setText(f"{len(items)} из {total} альбомов" if len(items) != total
                                  else f"{total} альбомов")

    @staticmethod
    def _track_no(path):
        """(диск, номер трека) из тегов — для правильного порядка в альбоме."""
        try:
            import mutagen
            m = mutagen.File(path, easy=True)
            if m is None or not m.tags:
                return (99, 999)

            def num(key):
                v = (m.tags.get(key) or [""])[0]
                v = str(v).split("/")[0].strip()
                return int(v) if v.isdigit() else None
            return (num("discnumber") or 1, num("tracknumber") or 999)
        except Exception:                            # noqa: BLE001
            return (99, 999)

    def open_album(self, key, keep_history=False):
        if not keep_history:
            self._remember()
        if not self._albums or key not in self._albums or "albums" in self._dirty:
            self._albums = self.album_index()
        a = self._albums.get(key)
        if not a:
            return
        tracks = list(a["tracks"])
        order = {id(t): (self._track_no(t.get("path", "")), i) for i, t in enumerate(tracks)}
        tracks.sort(key=lambda t: order[id(t)])
        self._pl_name, self._pl_kind = key, "album"
        self.pp_dlalb.hide()
        self.pp_sort.hide()
        self.pp_cover.size_ = 180
        self.pp_cover.setFixedSize(180, 180)
        self.pp_cover._path = None
        self.pp_cover.radius = 12
        self.pp_cover.set_cover(a["cover"], a["name"])
        self.pp_kind.setText("Альбом")
        self.pp_name.setText(a["name"])
        total = a["dur"]
        n = len(tracks)
        self.pp_meta.setText(f"{a['artist']} · {n} {_plural(n, 'трек', 'трека', 'треков')} · "
                             f"{int(total // 3600)} ч {int(total % 3600 // 60)} мин" if total >= 3600 else
                             f"{a['artist']} · {n} {_plural(n, 'трек', 'трека', 'треков')} · {int(total // 60)} мин")
        self.pp_wave.hide()
        self.pp_more.show()
        self.pp_add.hide()
        self.pp_hint.hide()
        self.pp_empty.hide()
        self.pp_list.show()
        self._pp_search_reset(True, key)
        self._pp_filters_reset(tracks, key)
        self.pp_list.set_rows([{"t": t, "ctx": ALBUM_PL, "i": i, "alb_tracks": tracks, "alb_name": a["name"],
                                "owned": True} for i, t in enumerate(tracks)])
        import ya_decor
        ya_decor.fly_to(self, self.pp_cover)                   # обложка «перелетает» с карточки
        self.show_page("playlist", remember=False)
        for i in range(self.pl_side.count()):
            self.pl_side.item(i).setSelected(False)
        self._album_fetch_full(key, a, tracks)

    def _album_fetch_full(self, key, a, local_tracks):
        """Подгрузить полный список треков альбома (YouTube Music) и показать ещё не скачанные."""
        cache = self.__dict__.setdefault("_alb_cache", {})
        self._alb_req = getattr(self, "_alb_req", 0) + 1
        req = self._alb_req
        if key in cache:
            self._album_merge(req, key, a, local_tracks, cache[key])
            return
        artist = a["artist"] if a["artist"] != "Разные исполнители" else ""

        def work():
            alb = None
            try:
                import online_search
                alb = online_search.album_tracks(artist, a["name"])
            except Exception as e:                   # noqa: BLE001
                print("[album full]", e)
            self.win._ui_bridge.call.emit(lambda: (cache.__setitem__(key, alb) if alb else None,
                                                   self._album_merge(req, key, a, local_tracks, alb)))
        _threading.Thread(target=work, daemon=True).start()

    def _album_merge(self, req, key, a, local_tracks, alb):
        if req != getattr(self, "_alb_req", 0) or self._pl_kind != "album" or self._pl_name != key:
            return
        remote = (alb or {}).get("tracks") or []
        if not remote:
            return
        from track_identity import similarity
        used, matched = set(), {}
        for ri, rt in enumerate(remote):
            best, bs = None, 0.0
            for li, lt in enumerate(local_tracks):
                if li in used:
                    continue
                s = similarity(sanitize_title(rt.get("title", "")), sanitize_title(lt.get("title", "")))
                if s > bs:
                    best, bs = li, s
            if best is not None and bs >= 0.82:
                used.add(best)
                matched[ri] = best
        ordered = [local_tracks[matched[ri]] for ri in range(len(remote)) if ri in matched] + \
                  [lt for li, lt in enumerate(local_tracks) if li not in used]       # лишние локальные — в конец
        pos = {id(t): i for i, t in enumerate(ordered)}
        rows = []
        for ri, rt in enumerate(remote):
            if ri in matched:
                lt = local_tracks[matched[ri]]
                rows.append({"t": lt, "ctx": ALBUM_PL, "i": pos[id(lt)], "alb_tracks": ordered,
                             "alb_name": a["name"], "owned": True})
            else:
                ph = {"title": rt.get("title", ""), "artist": rt.get("artist", "") or a["artist"],
                      "duration": rt.get("duration", 0), "cover": a["cover"], "path": "", "album": a["name"]}
                url = rt.get("url", "")
                row = {"t": ph, "ctx": ALBUM_PL, "remote": True, "url": url, "remote_t": rt, "alb_name": a["name"]}
                st = self.__dict__.get("_dl_states", {}).get(url)
                if st and st[0] != "done":                 # качается — прогресс не теряется при пересборке списка
                    row["dl"] = st
                rows.append(row)
        for lt in ordered[len(matched):]:
            rows.append({"t": lt, "ctx": ALBUM_PL, "i": pos[id(lt)], "alb_tracks": ordered,
                         "alb_name": a["name"], "owned": True})
        self.pp_list.set_rows(rows)
        total = len(rows)
        have = sum(1 for r in rows if r.get("owned"))
        self._album_dl_button(rows)
        dur = sum(float(r["t"].get("duration") or 0) for r in rows)
        self.pp_meta.setText(f"{a['artist']} · {total} {_plural(total, 'трек', 'трека', 'треков')} · "
                             f"скачано {have} из {total} · "
                             + (f"{int(dur // 3600)} ч {int(dur % 3600 // 60)} мин" if dur >= 3600 else f"{int(dur // 60)} мин"))

    def _album_menu(self, key):
        a = (self._albums or {}).get(key)
        if not a:
            return
        m = QMenu(self)
        if self._pl_kind == "album" and any(r.get("remote") for r in self.pp_list.model_.rows):
            m.addAction("Скачать альбом в коллекцию", self.download_album)
        m.addAction("Сохранить как плейлист", lambda: self._album_to_playlist(a))
        if a["artist"] != "Разные исполнители":
            m.addAction(f"Исполнитель «{a['artist']}»", lambda: self.open_artist(a["artist"]))
        m.exec(QCursor.pos())

    def _album_to_playlist(self, a):
        name = a["name"]
        if name in self.win.playlists and name not in AUTO_PLAYLISTS:
            name = f"{name} — {a['artist']}"
        rows = self.pp_list.model_.rows
        tracks = [dict(r["t"]) for r in rows] if self._pl_kind == "album" else [dict(t) for t in a["tracks"]]
        self.win.playlists[name] = {"tracks": tracks, "desc": f"Альбом · {a['artist']}", "cover": a.get("cover", "")}
        self.win._ya_save_playlists()
        self.refresh_sidebar()
        self.open_playlist(name)

    # ── плейлист / исполнитель ───────────────────────────────────────── #

    def _build_playlist_page(self):
        page = QWidget(); page.setObjectName("YaPage")
        v = QVBoxLayout(page)
        v.setContentsMargins(32, 18, 24, 10)
        v.setSpacing(12)
        b = icon_button("back", "Назад", 34, 20)
        b.clicked.connect(self.go_back)
        v.addWidget(b)
        head = QHBoxLayout(); head.setSpacing(24)
        self.pp_cover = RoundCover(180, 12)
        head.addWidget(self.pp_cover)
        col = QVBoxLayout(); col.setSpacing(6)
        col.addStretch(1)
        self.pp_kind = QLabel("Плейлист"); self.pp_kind.setObjectName("YaSub")
        self.pp_name = QLabel(""); self.pp_name.setStyleSheet("font-size:40px;font-weight:900;")
        self.pp_meta = QLabel(""); self.pp_meta.setObjectName("YaSub")
        col.addWidget(self.pp_kind); col.addWidget(self.pp_name); col.addWidget(self.pp_meta)
        btns = QHBoxLayout(); btns.setSpacing(10)
        self.pp_play = QPushButton("  Слушать")
        self.pp_play.setObjectName("YaYellow")
        self.pp_play.setIcon(ya_icon("play", 18, "#000000"))
        self.pp_play.setMinimumHeight(40)
        self.pp_play.clicked.connect(lambda: self._pp_play(False))
        self.pp_shuffle = QPushButton("  Вперемешку")
        self.pp_shuffle.setIcon(ya_icon("shuffle", 18, "#ffffff"))
        self.pp_shuffle.setMinimumHeight(40)
        self.pp_shuffle.clicked.connect(lambda: self._pp_play(True))
        self.pp_wave = QPushButton("  Волна по артисту")
        self.pp_wave.setIcon(ya_icon("wave", 18, "#ffffff"))
        self.pp_wave.setMinimumHeight(40)
        self.pp_wave.clicked.connect(lambda: self.start_wave("artist", self._pl_name))
        self.pp_add = QPushButton("  Добавить треки")
        self.pp_add.setIcon(ya_icon("plus", 18, "#ffffff"))
        self.pp_add.setMinimumHeight(40)
        self.pp_add.setToolTip("Выбрать треки из коллекции и добавить в этот плейлист")
        self.pp_add.clicked.connect(self._pp_add)
        self.pp_dlalb = QPushButton("  Скачать альбом")
        self.pp_dlalb.setIcon(ya_icon("download", 18, "#ffffff"))
        self.pp_dlalb.setMinimumHeight(40)
        self.pp_dlalb.setToolTip("Скачать недостающие треки альбома в коллекцию")
        self.pp_dlalb.clicked.connect(self.download_album)
        self.pp_dlalb.hide()
        self.pp_more = icon_button("dots", "Ещё: обложка, переименовать, удалить плейлист", 40, 20)
        self.pp_more.clicked.connect(self._pp_menu)
        self.pp_sort = self._sort_button(lambda b: __import__("track_sort").menu(
            b, (self.win.settings.get("sort_pl") or {}).get(getattr(self, "_pl_name", "")) or "default",
            self._set_pl_sort))
        self.pp_sort.hide()                             # только у плейлистов (у альбома — порядок альбома)
        for b in (self.pp_play, self.pp_shuffle, self.pp_wave, self.pp_add, self.pp_dlalb, self.pp_sort,
                  self.pp_more):
            btns.addWidget(b)
        btns.addStretch(1)
        col.addLayout(btns)
        col.addStretch(1)
        head.addLayout(col, 1)
        v.addLayout(head)
        self.pp_hint = QLabel("Перетаскивайте треки мышкой, чтобы поменять порядок  ·  Ctrl/Shift + клик — "
                              "выделить несколько  ·  «⋯» или правая кнопка — убрать, теги, удалить")
        self.pp_hint.setObjectName("YaSub")
        v.addWidget(self.pp_hint)
        from ya_decor import EmptyArt
        self.pp_empty = EmptyArt("Здесь пока пусто.\nНажмите «Добавить треки» — или в любом списке треков "
                               "правая кнопка → «Добавить в плейлист».")
        self.pp_empty.setObjectName("YaSub")
        self.pp_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pp_empty.setStyleSheet("font-size:15px;padding:40px;")
        self.pp_empty.hide()
        v.addWidget(self.pp_empty)
        self.pp_search = QLineEdit()
        self.pp_search.setPlaceholderText("Поиск в плейлисте: исполнитель, название…")
        self.pp_search.addAction(ya_icon("search", 16, "#8a8a8a"), QLineEdit.ActionPosition.LeadingPosition)
        self.pp_search.setClearButtonEnabled(True)
        self.pp_search.setMaximumWidth(420)
        self.pp_search.textChanged.connect(self._pp_filter_changed)
        v.addWidget(self.pp_search)
        self.pp_fbar = QWidget()
        self.pp_fbar.setObjectName("YaPageInner")
        fh = QHBoxLayout(self.pp_fbar)
        fh.setContentsMargins(0, 0, 0, 0)
        fh.setSpacing(12)
        self.pp_genre = QComboBox()
        self.pp_genre.setMinimumWidth(210)
        self.pp_genre.setToolTip("Показать только треки выбранного жанра")
        self.pp_genre.currentIndexChanged.connect(self._pp_apply_filters)
        fh.addWidget(self.pp_genre)
        self.pp_mood_btns = {}
        mood_btns = []
        mg = QButtonGroup(page)
        mg.setExclusive(True)
        for key, text in (("any", "Любое настроение"),) + tuple((m[0], m[1]) for m in MOODS):
            b = chip(text)
            mg.addButton(b)
            b.clicked.connect(self._pp_apply_filters)
            self.pp_mood_btns[key] = b
            mood_btns.append(b)
        self.pp_mood_btns["any"].setChecked(True)
        self.pp_mood_group = seg_group(*mood_btns)
        fh.addWidget(self.pp_mood_group)
        fh.addStretch(1)
        v.addWidget(self.pp_fbar)
        self.pp_nores = QLabel("Ничего не нашлось")
        self.pp_nores.setObjectName("YaSub")
        self.pp_nores.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pp_nores.setStyleSheet("font-size:15px;padding:30px;")
        self.pp_nores.hide()
        v.addWidget(self.pp_nores)
        self.pp_list = TrackListView(self)
        self.pp_selbar = SelectionBar(self, self.pp_list)
        v.addWidget(self.pp_selbar)
        v.addWidget(self.pp_list, 1)
        self._pl_name = None
        self._pl_kind = "playlist"
        self.pp_dlalb.hide()
        self.pp_sort.hide()
        from ya_decor import _HeaderTint
        self.pp_name.setObjectName("YaHero")
        self._pp_tint = _HeaderTint(page, self.pp_cover, self.pp_list)   # шапка в цвет обложки
        return page

    def _pp_filter_changed(self, text):
        self.pp_list.set_filter(text)
        self._pp_update_nores()

    def _pp_update_nores(self):
        active = bool(self.pp_search.text().strip()) or getattr(self.pp_list, "pred", None) is not None
        self.pp_nores.setVisible(active and self.pp_list.model_.rowCount() == 0
                                 and bool(getattr(self.pp_list, "_all_rows", None)))   # список ещё не заполняли

    # ── фильтры по жанру и настроению ── #

    def _pp_filters_reset(self, tracks, key):
        """Подготовить фильтры для открытого списка. Тот же список (обновился) — выбор сохраняется."""
        self._pp_tracks = list(tracks)
        same = key is not None and key == getattr(self, "_pp_fkey", None)
        self._pp_fkey = key
        prof = self.profiles() or {}
        counts = {}
        for t in tracks:
            for f in (prof.get(str(t.get("path", "")), {}).get("families") or [])[:2]:
                counts[f] = counts.get(f, 0) + 1
        try:
            from music_intel import GENRE_RU
        except Exception:                            # noqa: BLE001
            GENRE_RU = {}
        keep = self.pp_genre.currentData() if same else None
        self.pp_genre.blockSignals(True)
        self.pp_genre.clear()
        self.pp_genre.addItem("Все жанры", None)
        for fam, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            self.pp_genre.addItem(f"{str(GENRE_RU.get(fam, fam)).capitalize()}  ·  {n}", fam)
        i = self.pp_genre.findData(keep) if keep else 0
        self.pp_genre.setCurrentIndex(max(0, i))
        self.pp_genre.blockSignals(False)
        show_genre = bool(counts)
        show_mood = bool(self.win.settings.get("mood_filter", False)) and bool(prof)
        self._pp_show_mood = show_mood
        self.pp_genre.setVisible(show_genre)
        self.pp_mood_group.setVisible(show_mood)
        self.pp_fbar.setVisible(show_genre or show_mood)
        if not same:
            self.pp_mood_btns["any"].setChecked(True)
        self._pp_apply_filters()

    def _pp_apply_filters(self, *_):
        prof = self.profiles() or {}
        fam = self.pp_genre.currentData() if self.pp_genre.count() > 1 else None
        mood = next((k for k, b in self.pp_mood_btns.items() if b.isChecked()), "any") \
            if getattr(self, "_pp_show_mood", False) else "any"
        if not fam and mood == "any":
            self.pp_list.set_pred(None)
            self._pp_update_nores()
            return
        rule = next((m for m in MOODS if m[0] == mood), None)

        def pred(t):
            pr = prof.get(str(t.get("path", "")))
            if not pr:
                return False
            if fam and fam not in (pr.get("families") or [])[:2]:
                return False
            if rule is not None:
                x = float(rule[2](pr))
                return x >= 0.60 if rule[3] else x <= 0.40
            return True
        self.pp_list.set_pred(pred)
        self._pp_update_nores()

    def _pp_search_reset(self, show: bool, key=None):
        """Другой плейлист/альбом: поиск очищается. Тот же (обновился после правки) — запрос сохраняется."""
        same = key is not None and key == getattr(self, "_pp_key", None)
        self._pp_key = key
        if not same:
            self.pp_search.blockSignals(True)
            self.pp_search.clear()
            self.pp_search.blockSignals(False)
            self.pp_list.set_filter("")
            self.pp_nores.hide()
        else:
            QTimer.singleShot(0, lambda: self._pp_filter_changed(self.pp_search.text()))
        self.pp_search.setVisible(show)

    def open_playlist(self, name, keep_history=False):
        if not keep_history:
            self._pl_usage_bump(name)
            if name in self.win.playlists:
                self._remember()
        if not name or name not in self.win.playlists:
            return
        self._pl_name, self._pl_kind = name, "playlist"
        self.pp_dlalb.hide()
        self.pp_sort.hide()
        pl = self.win.playlists[name]
        tr = pl.get("tracks", [])
        cov = pl.get("cover") or (tr[0].get("cover", "") if tr else "")
        self.pp_cover.size_ = 180
        self.pp_cover.setFixedSize(180, 180)
        self.pp_cover._path = None
        self.pp_cover.radius = 12
        self.pp_cover.set_cover(cov, name)
        import net_collab
        self.pp_kind.setText(net_collab.label(pl) or ("Открытый плейлист  ·  виден в профиле" if pl.get("public")
                                                      else "Плейлист"))
        self.pp_name.setText(name)
        total = sum(float(t.get("duration") or 0) for t in tr)
        self.pp_meta.setText(f"{len(tr)} треков · {int(total // 3600)} ч {int(total % 3600 // 60)} мин"
                             + (f"\n{pl.get('desc')}" if pl.get("desc") and not str(pl.get("desc")).startswith("auto") else ""))
        self.pp_wave.hide()
        self.pp_more.show()
        user_pl = name not in AUTO_PLAYLISTS
        self.pp_add.setVisible(user_pl)
        self.pp_hint.setVisible(user_pl and bool(tr))
        self.pp_empty.setVisible(not tr)
        self.pp_list.setVisible(bool(tr))
        self._pp_search_reset(bool(tr), name)
        self._pp_filters_reset(tr, name)
        import track_sort
        key = (self.win.settings.get("sort_pl") or {}).get(name) or "default"
        self.pp_list.set_rows(track_sort.apply([{"t": t, "ctx": name, "i": i} for i, t in enumerate(tr)], key,
                                               self.win))
        self.pp_sort.setVisible(bool(tr))
        self._sort_btn_text(self.pp_sort, key)
        import ya_decor
        ya_decor.fly_to(self, self.pp_cover)
        self.show_page("playlist", remember=False)
        for i in range(self.pl_side.count()):
            it = self.pl_side.item(i)
            it.setSelected(it.data(Qt.ItemDataRole.UserRole) == name)

    def open_artist(self, artist):
        """Карточка исполнителя: данные с серверов + треки из коллекции
        (даже если в коллекции его нет — для «Похожих исполнителей»)."""
        if not artist:
            return
        from artist_identity import ArtistIndex, key
        index=_artist_index(self.win.library)
        artist=index.display(artist)
        tracks=index.tracks_for(artist)
        if not (self._cur_page == "artist" and self.pages["artist"].name == artist):
            self._remember()                                   # с артиста на артиста — тоже шаг истории
        self.pages["artist"].load(artist, tracks)
        self.show_page("artist", remember=False)

    def _sort_button(self, on_click) -> QPushButton:
        b = QPushButton("  Сортировка")
        b.setObjectName("YaChip")
        b.setIcon(ya_icon("queue", 16, "#d0d0d0"))
        b.setIconSize(QSize(16, 16))
        b.setMinimumHeight(38)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setToolTip("Порядок треков — в нём же они и играют дальше")
        b.clicked.connect(lambda: on_click(b))
        return b

    def _sort_btn_text(self, b, key, collection=False):
        import track_sort
        names = track_sort.COLL_NAMES if collection else track_sort.NAMES
        try:
            b.setText("  " + names.get(key or "default", "Сортировка"))
        except RuntimeError:
            pass

    def _set_coll_sort(self, key):
        self.win.settings["sort_coll"] = key
        self.win._schedule_settings_save()
        self._coll_apply()

    def _set_pl_sort(self, key):
        name = getattr(self, "_pl_name", None)
        if not name or getattr(self, "_pl_kind", "") != "playlist":
            return
        self.win.settings.setdefault("sort_pl", {})[name] = key
        self.win._schedule_settings_save()
        self.open_playlist(name, keep_history=True)

    def _coll_shuffle(self):
        rows = getattr(self.c_list.model_, "rows", None) or []
        if not rows:
            self.win._toast("В коллекции пока нет треков")
            return
        if not self.win.shuffle:
            self.win.btn_shuffle.click()
        self.play_row(random.choice(rows))

    def _pp_play(self, shuffle):
        rows = self.pp_list.model_.rows
        if not rows:
            return
        if shuffle != bool(self.win.shuffle):
            self.win.btn_shuffle.click()
        r = random.choice(rows) if shuffle else rows[0]
        self.play_row(r)

    def _pp_menu(self):
        name = self._pl_name
        if self._pl_kind == "album" and name:
            self._album_menu(name)
            return
        if self._pl_kind != "playlist" or not name:
            return
        m = QMenu(self)
        m.addAction("＋  Добавить треки из коллекции…", lambda: self._pp_add())
        m.addAction("Сменить обложку…", lambda: (self.win._pd_set_cover(name), self.open_playlist(name, True)))
        m.addAction("Переименовать…", lambda: self.win._pd_rename(name))
        m.addAction("Описание…", lambda: self.win._pd_edit_description(name))
        m.addAction("Поделиться файлом…", lambda: getattr(self.win, "share_playlist", lambda *_: None)(name))
        pub = bool(self.win.playlists.get(name, {}).get("public"))
        m.addAction("\U000f1002  Сделать закрытым (убрать из профиля)" if pub else "\U000f100c  Сделать открытым (виден в профиле всем)",
                    lambda: self._set_pl_public(name, not pub))
        import net_collab                                      # совместный — правят несколько друзей
        shared = isinstance(self.win.playlists.get(name, {}).get("shared"), dict)
        m.addAction("\U000f100d  Позвать ещё друзей…" if shared else "\U000f100d  Сделать совместным (правят друзья)…",
                    lambda: net_collab.make_shared(self, name))
        if shared:
            m.addAction("Выйти из совместного", lambda: (net_collab.leave(self, name), self.open_playlist(name, True)))
        m.addSeparator()
        m.addAction("Удалить плейлист", lambda: self._delete_playlist(name))
        m.exec(QCursor.pos())

    def _set_pl_public(self, name, on):
        """Открытый плейлист — в профиле Echoes.NET, его может открыть и послушать любой."""
        pl = self.win.playlists.get(name)
        if pl is None:
            return
        n_pub = sum(1 for p in self.win.playlists.values() if isinstance(p, dict) and p.get("public"))
        if on and n_pub >= 6:
            self.win._toast("Открытых плейлистов может быть до 6 — сначала закройте какой-нибудь")
            return
        pl["public"] = bool(on)
        self.win._save_playlists()
        net = self.pages.get("net")
        if net is not None and hasattr(net, "push_profile"):
            net.push_profile()
        self.win._toast(f"«{name}» теперь открытый — виден в вашем профиле" if on else f"«{name}» теперь закрытый")
        if self._pl_kind == "playlist" and self._pl_name == name:
            self.open_playlist(name, keep_history=True)

    def _pp_add(self):
        name = self._pl_name
        if self._pl_kind == "playlist" and name in self.win.playlists:
            if self.win.pick_tracks_for_playlist(name, self):
                self.open_playlist(name, keep_history=True)

    def refresh_sidebar(self):
        lst = self.pl_side
        lst.clear()
        w = self.win
        names = list(w.playlists.keys())
        if LIKED in names:
            names.remove(LIKED)
            names.insert(0, LIKED)
        for n in names:
            if n in (WAVE_PL, ALBUM_PL):
                continue
            pl = w.playlists[n]
            tr = pl.get("tracks", [])
            cov = pl.get("cover") or (tr[0].get("cover", "") if tr else "")
            it = QListWidgetItem(QIcon(liked_cover(36, 6) if n == LIKED and not pl.get("cover")
                                       else cover_pixmap(cov, 36, 6, seed=n)), f"{n}\nПлейлист · {len(tr)}")
            it.setData(Qt.ItemDataRole.UserRole, n)
            lst.addItem(it)
        nick = w.profile.get("nickname", "user")
        self.nick.setText(nick)
        self.status.setText(w.profile.get("status", ""))
        av = w.profile.get("avatar", "")
        d = self.avatar.width()
        self.avatar.setPixmap(cover_pixmap(av, d, d / 2, seed=nick, circle=True))
        strip = getattr(self, "pl_strip", None)
        if strip is not None:
            strip.refresh()

    # ── «Текст» (как в Я.Музыке) ─────────────────────────────────────── #

    def _build_lyrics(self):
        from lyrics_view import LyricsScrollPanel

        shell = self

        class _LyricsPage(QWidget):
            def resizeEvent(self, e):
                super().resizeEvent(e)
                path = QPainterPath()                    # скруглённые края, как у главного экрана
                path.addRoundedRect(QRectF(self.rect()), 22, 22)
                from PyQt6.QtGui import QRegion
                self.setMask(QRegion(path.toFillPolygon().toPolygon()))

            def paintEvent(self, _):
                p = QPainter(self)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                clip = QPainterPath()
                clip.addRoundedRect(QRectF(self.rect()), 22, 22)
                p.setClipPath(clip)
                bg = getattr(shell, "_lyr_bg", None)
                if bg is None or bg.size() != self.size():
                    bg = shell._make_lyrics_bg(self.size())
                    shell._lyr_bg = bg
                    lp = getattr(shell, "l_panel", None)
                    if lp is not None:                   # новый фон — и кусок под панелью текста
                        lp.update()
                p.drawPixmap(0, 0, bg)
                p.end()

        page = _LyricsPage()
        page.setObjectName("YaLyrics")
        h = QHBoxLayout(page)
        h.setContentsMargins(40, 20, 20, 20)
        h.setSpacing(30)
        left = QVBoxLayout(); left.setSpacing(10)
        left.addStretch(1)
        self.l_cover = RoundCover(300, 10)
        left.addWidget(self.l_cover, 0, Qt.AlignmentFlag.AlignHCenter)
        self.l_title = QLabel(""); self.l_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.l_title.setStyleSheet("font-size:15px;font-weight:800;")
        from artist_links import ArtistLinks
        self.l_artist = ArtistLinks(); self.l_artist.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.l_artist.artist_clicked.connect(self.open_artist)
        self.l_artist.setObjectName("YaSub")
        left.addWidget(self.l_title)
        left.addWidget(self.l_artist)
        self.l_prog = ProgressLine()
        self.l_prog.setFixedWidth(300)
        self.l_prog.seek_to.connect(self._seek_frac)
        left.addWidget(self.l_prog, 0, Qt.AlignmentFlag.AlignHCenter)
        left.addStretch(1)
        h.addLayout(left)
        rcol = QVBoxLayout()
        top_holder = QWidget()
        top = FlowLayout(top_holder, 8, 8)
        top.setContentsMargins(0, 0, 0, 0)
        self.l_ai = QPushButton("  Синхронизировать с ИИ")
        self.l_ai.setObjectName("YaChip")
        self.l_ai.setIcon(ya_icon("ai_sync", 16, YELLOW))
        self.l_ai.setIconSize(QSize(16, 16))
        self.l_ai.setFixedHeight(34)
        self.l_ai.setCursor(Qt.CursorShape.PointingHandCursor)
        self.l_ai.setToolTip("Нейросеть Whisper послушает трек (локально) и расставит таймкоды по строкам текста")
        self.l_ai.clicked.connect(self.win.ai_sync_lyrics)
        self.l_ai.hide()
        self.l_ai_lbl = QLabel("")
        self.l_ai_lbl.setWordWrap(True)
        self.l_ai_lbl.setObjectName("YaSub")
        self.l_find = QPushButton("  Найти текст вручную")
        self.l_find.setObjectName("YaChip")
        self.l_find.setIcon(ya_icon("search", 16))
        self.l_find.setIconSize(QSize(16, 16))
        self.l_find.setFixedHeight(34)
        self.l_find.setCursor(Qt.CursorShape.PointingHandCursor)
        self.l_find.setToolTip("Свой запрос «исполнитель - название» — поиск текста по всем источникам")
        self.l_find.clicked.connect(self.win._manual_lyrics_search)
        self.l_tags = QPushButton("  Теги трека")
        self.l_tags.setObjectName("YaChip")
        self.l_tags.setIcon(ya_icon("edit", 16))
        self.l_tags.setIconSize(QSize(16, 16))
        self.l_tags.setFixedHeight(34)
        self.l_tags.setCursor(Qt.CursorShape.PointingHandCursor)
        self.l_tags.setToolTip("Исполнитель, альбом, обложка и название файла — теги для этого трека "
                               "дополнялись из интернета или их не хватает")
        self.l_tags.clicked.connect(self.win.edit_current_tags)
        self.l_tags.setVisible(bool(getattr(self.win, "_tags_btn_path", "")))
        top.addWidget(self.l_ai)
        self.l_appearance = chip("Язык и оформление", checkable=False)
        self.l_appearance.setFixedHeight(34)
        self.l_appearance.clicked.connect(lambda: self.win._lyrics_options.open())
        top.addWidget(self.l_appearance)
        top.addWidget(self.l_find)
        top.addWidget(self.l_tags)
        for b_ in (self.l_ai, self.l_appearance, self.l_find, self.l_tags):   # текст кнопок не обрезается
            b_.setMinimumHeight(36)
            b_.setMaximumHeight(16777215)
            b_.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            b_.setStyleSheet(LYR_GLASS_BTN)                     # прозрачное стекло поверх размытой обложки
            b_.ensurePolished()
        top.addWidget(self.l_ai_lbl)
        b = icon_button("chevron_down", "Свернуть текст", 40, 22)
        b.setStyleSheet(LYR_GLASS_BTN.replace("border-radius:18px", "border-radius:20px").replace("padding:0 14px", "padding:0"))
        b.clicked.connect(self.toggle_lyrics)
        top.addWidget(b)
        rcol.addWidget(top_holder)
        self.l_panel = LyricsScrollPanel()
        self.l_panel.liquid = self.win.settings.get("lyrics_liquid", True)   # строка заливается белым по буквам
        self.l_panel.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.l_panel.customContextMenuRequested.connect(lambda _:self.win._lyrics_options.open())
        self.l_panel.seek_cb = self.win._lyrics_seek

        def backdrop(page=page):
            bg = getattr(shell, "_lyr_bg", None)
            if bg is None or bg.size() != page.size():
                bg = shell._make_lyrics_bg(page.size())
                shell._lyr_bg = bg
            return bg, self.l_panel.mapTo(page, QPoint(0, 0))
        self.l_panel.set_backdrop(backdrop)
        rcol.addWidget(self.l_panel, 1)
        h.addLayout(rcol, 1)
        return page

    def _translation_mode_changed(self):
        options=getattr(self.win,'_lyrics_options',None)
        if options is None:return
        self.win.settings['lyrics_translation_mode']=self.l_translation_mode.currentData()
        self.win.save_settings()
        options.render()
        self._lyrics_tick(None,None)

    def _manual_lyrics_changed(self,on):
        self.win.settings.setdefault('lyrics_display',{})['manual_scroll']=bool(on)
        self.win.save_settings()
        options=getattr(self.win,'_lyrics_options',None)
        if options:options.apply_style()

    def _lyrics_size_changed(self,delta):
        style=self.win.settings.setdefault('lyrics_display',{})
        current=int(style.get('size',0)) or self.l_panel._font_px()
        style['size']=max(10,min(120,current+delta))
        self.win.save_settings()
        options=getattr(self.win,'_lyrics_options',None)
        if options:options.apply_style()

    def _make_lyrics_bg(self, size) -> QPixmap:
        from echo_glass import lyrics_background
        accent = None; cover = None; image = None
        track = self.current_track()
        path = (track or {}).get('cover', '')
        if path and Path(path).is_file():
            image = read_image(path, 1280)
            if not image.isNull():
                accent = image.pixelColor(image.width() // 2, image.height() // 2)
        glass = self.win.settings.get('lyrics_display', {}).get('liquid_glass', True)
        src = image if path and Path(path).is_file() and not image.isNull() else None
        if src is not None:                                    # фон как на iPhone — всегда; «стекло» в настройках —
            return lyrics_background(size, cover, accent, True, src)   # только подложка под строками
        return lyrics_background(size, cover, accent, glass, src)

    def toggle_queue(self):
        """Кнопка «Очередь»: страница внутри плеера; повторное нажатие — назад."""
        if self._cur_page == "queue":
            self.go_back()
        else:
            self.show_page("queue")

    def set_tags_button(self, on: bool):
        """«Поменять теги трека» над текстом (решает MainWindow._tags_btn_update)."""
        b = getattr(self, "l_tags", None)
        if b is not None:
            b.setVisible(bool(on))

    def toggle_lyrics(self):
        """Кнопка текста в нижнем плеере: текст на весь экран — тот же экран, что у обложки (now_playing)."""
        np_ = self.__dict__.get("_now_playing")
        if np_ is not None and np_.is_open():
            if np_.mode() == "lyrics":
                np_.close_mode()
            else:
                np_.set_mode("lyrics")
            return
        if self._cur_page == "lyrics":
            self.go_back()
            return
        try:
            self.open_now_playing(mode="lyrics")
        except Exception as e:                                 # noqa: BLE001
            print("[lyrics] full screen:", e)
            self.show_lyrics_tools()

    def show_lyrics_tools(self):
        """Прежняя страница текста: поиск вручную, синхронизация с ИИ, язык и оформление."""
        self._lyr_src = None
        self.show_page("lyrics")
        self._lyrics_tick(None, None)

    def _refine_words(self, lines):
        """Через доли секунды — тайминги слов по звуку трека (word_sync), в фоне."""
        panel = self.l_panel
        est = getattr(panel, "_est", None)
        t = self.current_track()
        path = str((t or {}).get("path", ""))
        if not est or not any(est) or not path or not Path(path).exists():
            return
        bus = self.__dict__.get("_words_bus")
        if bus is None:
            from PyQt6.QtCore import QObject as _QO, pyqtSignal as _sig

            class _WB(_QO):
                done = _sig(object, object)
            bus = self._words_bus = _WB(self)
            bus.done.connect(lambda ln, w: self.l_panel.set_word_timings(ln, w))

        def work(lines=lines, est=list(est), path=path):
            try:
                import word_sync
                w = word_sync.refine(lines, est, word_sync.envelope(path))
                bus.done.emit(lines, w)
            except Exception as e:                         # noqa: BLE001
                print("[words]", e)
        import threading
        threading.Thread(target=work, name="echoes-words", daemon=True).start()

    def _lyrics_tick(self, pos, dur):
        lv = self.win.lyrics_view
        options = getattr(self.win, '_lyrics_options', None)
        lines = (options.display_lines if options is not None else getattr(lv, '_lines', None)) or []
        data_key = options.data_revision if options is not None else id(lines)
        signature = (data_key, options.revision if options is not None else 0)
        if signature != self._lyr_src:
            data_changed = not self._lyr_src or self._lyr_src[0] != data_key
            self._lyr_src = signature
            self.l_panel._translation_below = bool(getattr(lv._text_panel, '_translation_below', False))
            if data_changed:
                self.l_panel.load(lines, bool(getattr(lv, "_has_timings", False)))
                self._refine_words(lines)
            self.l_panel.set_style(lv._text_panel._st, lv._text_panel._st_family)
        ai = getattr(self.win, "_ai", None)
        running = bool(ai and ai["running"])
        self.l_ai.setVisible(running or (bool(lines) and not getattr(lv, "_has_timings", False)))
        self.l_ai.setText("  Отмена" if running else "  Синхронизировать с ИИ")
        self.l_ai_lbl.setText(ai["status"] if running else getattr(options, 'status_text', ''))
        if pos is None:
            try:
                eng = self.win.engine
                pos = float(eng.get_position_smooth() if hasattr(eng, "get_position_smooth")
                            else eng.get_position() or 0)
                dur = float(eng.duration or 0)
            except Exception:                        # noqa: BLE001
                pos = dur = 0.0
        f = float(getattr(self.win.engine, "preset_factor", 1.0) or 1.0)
        if self.is_playing():
            self.l_panel.set_pos_ms(int(pos * 1000 * f))
        self.l_panel.set_time(int(pos * 1000 * f), int(dur * 1000 * f))
        self.l_prog.set_state(pos / dur if dur else 0.0, dur)

    # ── «Настройки» ──────────────────────────────────────────────────── #

    def _ensure_listening_tools(self):
        if self._listener_panel is None:
            from listening_tools import ToolsDialog
            self._listener_panel = ToolsDialog(self.win._listening_tools,
                                               parent=self._listener_layout.parentWidget(), embedded=True)
            self._listener_layout.addWidget(self._listener_panel)
            self._listener_launch.hide()
        self.win._listening_tools.dialog = self._listener_panel

    def _open_listening_tab(self,name):
        from PyQt6.QtWidgets import QTabWidget
        self.win._listening_tools.open()
        tabs=self.win._listening_tools.dialog.findChild(QTabWidget)
        for i in range(tabs.count()):
            if tabs.tabText(i)==name:tabs.setCurrentIndex(i);break

    def _build_settings(self):
        """Настройки по разделам (ya_settings.SettingsHub): слева — разделы, сверху — умный поиск."""
        from ya_settings import SettingsHub
        hub = SettingsHub(Page, ya_icon, YELLOW)
        self.settings_hub = hub
        from ya_sound_panel import SoundPanel
        sound_controls=SoundPanel(self,embedded=True);hub.v.addWidget(sound_controls)
        hub.add('sound','Эффекты плеера и экспорт',sound_controls,'bass boost slowed speed up nightcore export effects настройки эффекты бас экспорт громкость')
        from performance_ui import settings_card
        perf=settings_card(self.win);hub.v.addWidget(perf)
        hub.add('performance','Производительность',perf,'performance memory ram fps cache graphics animation озу память кэш нагрузка')
        # ── Оформление: своя тема Echoes Music ──
        hub.add("look", "Тема Echoes Music", self._build_skin_card(hub),
                "цвета акцент шрифт размер текста кнопки панели скругление стиль дизайн пресеты живое оформление аура фон стекло oled пластинка винил анимации погода")
        import overlay_demo
        w = overlay_demo.settings_card(self); hub.v.addWidget(w)
        hub.add("look", "Игровой оверлей", w, "оверлей игра discord дискорд поверх игры бинды горячие клавиши "
                "голосовой чат в игре уведомления")
        w = self._build_layout_card(); hub.v.addWidget(w); hub.add("look", "Вид Echoes Music", w,
                                                                   "раскладка legacy старый вид классический панель "
                                                                   "слева справа разделы плейлисты сверху дизайн")
        w = self._build_placeholder_card(); hub.v.addWidget(w); hub.add("look", "Картинка без обложки", w,
                                                                         "заглушка нота нет обложки своя картинка "
                                                                         "placeholder обложка исполнитель")
        w = self._build_intro_card(); hub.v.addWidget(w); hub.add("look", "Анимация при запуске", w,
                                                                  "заставка интро солнце запуск старт анимация логотип")
        # ── Инструменты слушателя ──
        tools_card = AmbientFrame(); tools_card.setObjectName("ListenerCard")
        tools_card.setStyleSheet("QFrame#ListenerCard{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #393018,stop:1 #25202c);border:1px solid #66542a;border-radius:18px;}")
        tools_layout = QVBoxLayout(tools_card)
        tools_layout.setContentsMargins(22,18,22,18)
        title = QLabel("Инструменты слушателя"); title.setStyleSheet("font-size:22px;font-weight:800;background:transparent;")
        tools_layout.addWidget(title)
        description = QLabel("Фрагменты A–B · Закладки · Звуковая сцена · Сон · Личные границы трека · Дневник · Анимации")
        description.setWordWrap(True); tools_layout.addWidget(description)
        launch = chip("Открыть инструменты слушателя   Ctrl+J", checkable=False)
        launch.clicked.connect(lambda: self.show_page("listening")); tools_layout.addWidget(launch)
        self._listener_layout = tools_layout
        self._listener_launch = launch
        self._listener_panel = None
        tools_card.setMaximumWidth(760)
        hub.v.addWidget(tools_card)
        hub.add("tools", "Инструменты слушателя", tools_card, "закладки сон дневник анимации фрагменты")
        import ya_auto, ya_backup, ya_voice
        w = ya_auto.settings_card(self); hub.v.addWidget(w)
        hub.add("tools", "Автоматика", w, "правила расписание время игра тише друг в сети уведомить автоматически")
        w = ya_voice.settings_card(self); hub.v.addWidget(w)
        hub.add("tools", "Голосовые команды", w, "голос микрофон сказать команду эхос следующий громче")
        w = ya_backup.settings_card(self); hub.v.addWidget(w)
        hub.add("tools", "Резервная копия", w, "бэкап backup копия перенос новый пк восстановить экспорт")
        import player_prefs
        w = self._keybinds_card = player_prefs.keybinds_card(self.win); hub.v.addWidget(w)
        hub.add("tools", "Горячие клавиши", w, "клавиши бинды сочетания горячие пробел глобальные везде hotkey "
                                              "shortcut keybind")
        self._build_inline_tools(hub)                      # бывшие кнопки-окна — строки настроек, раскрываются на месте
        w = self._build_wave_setting(); hub.v.addWidget(w); hub.add("play", "Слушать онлайн без скачивания", w,
                                                                    "стриминг поток youtube soundcloud")
        w = self._build_mood_filter_setting(); hub.v.addWidget(w); hub.add("library", "Фильтр по настроению", w)
        w = self._build_boost_setting(); hub.v.addWidget(w); hub.add("sound", "Экстремальная громкость", w,
                                                                     "громкость усиление boost")
        w = self._build_net_setting_card(); hub.v.addWidget(w); hub.add("apps", "Echoes.NET", w,
                                                                        "друзья сеть соцсеть комнаты профиль код")
        w = self._build_notif_setting_card(); hub.v.addWidget(w); hub.add("apps", "Уведомления", w,
                                                                          "уведомления звук оповещения подписки "
                                                                          "не беспокоить сообщения всплывающие")
        hub.v.addSpacing(10)
        self._settings_slot = QVBoxLayout()
        holder = QWidget(); holder.setObjectName("YaSettingsCard")
        holder.setMaximumWidth(760)
        self._settings_slot.setContentsMargins(0, 8, 0, 12)
        self._settings_slot.setSpacing(0)
        holder.setLayout(self._settings_slot)
        hub.v.addWidget(holder)
        hub.v.addStretch(1)
        QTimer.singleShot(0, hub.refresh)
        return hub

    def _build_inline_tools(self, hub):
        """Инструменты, что раньше были кнопками с отдельными окнами, — обычные строки в своих разделах Настроек:
        раскрываются прямо здесь (settings_inline). Окнами остаются только то, что само по себе приложение или режим."""
        import settings_inline as si
        from duel_settings import tr as _tr
        w = self.win

        def put(cat, title, widget, keys=""):
            hub.v.addWidget(widget)
            hub.add(cat, title, widget, keys)

        def sec(cat, title, sub, icon, factory, keys="", height=None, on_closed=None):
            put(cat, title, si.Section(title, sub, ya_icon(icon, 20, YELLOW), factory, YELLOW, height, on_closed), keys)

        def row(cat, title, sub, icon, actions, keys=""):
            put(cat, title, si.Row(title, sub, ya_icon(icon, 20, YELLOW), actions, YELLOW), keys)

        # ── Оформление ──
        sec("look", "Темы оформления", "Все темы плеера — выберите, и плеер переоденется", "palette",
            self._inline_themes, "тема темы оформление скин winamp классическая")
        row("look", "Конструктор тем", "Своя тема с нуля: цвета, слои, кнопки и анимации — отдельный редактор", "edit",
            [("Открыть", lambda: w._open_theme_studio())], "конструктор тем свой дизайн")
        row("look", "Режим обложки", "Во весь экран — только обложка, трек и управление", "cover",
            [("Включить", w._toggle_cover_mode)], "обложка полный экран")
        import player_prefs
        sec("look", "Масштаб и окно", "Размер и пропорции окна, масштаб интерфейса", "settings",
            self._inline_prefs,
            "масштаб окно размер разрешение пропорции")
        # ── Тексты песен ──
        sec("lyrics", "Перевод и прокрутка текста", "Перевод, размер шрифта, интервал, скорость прокрутки, стекло",
            "lyrics", lambda: w._lyrics_options.build(), "перевод прокрутка шрифт текст караоке")
        row("lyrics", "Редактор текста", "Текст, таймкоды, теги и обложка играющего трека", "lyrics",
            [("Открыть для трека", w._open_lyrics_editor)], "редактор текста таймкоды lrc")
        # ── Медиатека ──
        from spotify_import import SpotifyImportDialog
        sec("library", "Перенести плейлист с площадки",
            "SoundCloud, YouTube Music, YouTube, Deezer, Apple Music, Spotify, Яндекс Музыка, VK — вставьте ссылку, "
            "площадка определится сама", "download", lambda: SpotifyImportDialog(w, provider="auto"),
            "перенести импорт плейлист soundcloud саундклауд youtube ютуб deezer дизер apple эпл spotify спотифай "
            "яндекс vk вк площадка")
        row("library", "Плейлист из файла", "Файл ECHOES, M3U или список треков", "download",
            [("Выбрать файл…", lambda: getattr(w, "import_playlist_file", lambda *_: None)())],
            "плейлист файл m3u импорт")
        row("library", "Плейлисты на телефон", "Все плейлисты одним файлом — для ECHOES на iPhone", "download",
            [("Сохранить файл…", lambda: getattr(w, "export_playlists_for_phone", lambda *_: None)())],
            "телефон iphone экспорт плейлисты")
        import playlist_share
        sec("library", "Куда класть файлы тем и плейлистов", "Папки импорта и перетаскивание на окно", "settings",
            lambda: playlist_share.FilesHelpDialog(w), "файлы папка импорт темы")
        import tag_all
        sec("library", "Найти теги для всей музыки", "Исполнитель, альбом, жанр и обложка для каждого трека",
            "search", lambda: tag_all.TagAllDialog(w), "теги обложки жанр альбом", height=460)
        import cleanup
        sec("library", "Очистка медиатеки и кэша", "Битые файлы, клипы и кэш — сколько места занимает и что убрать",
            "settings", lambda: cleanup.CleanupDialog(w, 0), "очистка кэш место диск удалить", height=640)
        sec("library", "Найти пропавшие треки", "Треки, файлы которых на диске, а в коллекции их нет", "search",
            lambda: si.LostTracks(w), "пропавшие треки вернуть восстановить коллекция")
        # ── Инструменты ──
        row("tools", "Палитра команд", "Любое действие плеера по названию — Ctrl+Shift+P", "search",
            [("Открыть", lambda: w._listening_tools.palette())], "команды палитра поиск действий")
        import stream_designer
        sec("tools", "Конструктор окна стримера", "Окно «Сейчас играет» для OBS и TikTok Studio — соберите своё",
            "edit", lambda: stream_designer.StreamStudio(w), "стример obs стрим окно оверлей конструктор")
        # ── Профиль ──
        from profile_editor import ProfileEditor

        def profile_saved(result):
            if result:
                w._load_profile()
                try:
                    self.refresh_sidebar()
                    if "net" in self.pages:
                        self.pages["net"].on_profile_changed()
                except Exception as e:                       # noqa: BLE001
                    print("[profile]", e)
        sec("apps", "Профиль", "Фото, ник, статус, «о себе» и любимые треки", "user",
            lambda: ProfileEditor(w), "профиль ник аватар статус", on_closed=profile_saved)
        row("apps", "Страница профиля", "Статистика, ачивки и оформление", "user",
            [("Открыть", w._open_profile)], "профиль страница")
        sec("apps", "Обновления", "Подписанные выпуски автора; бета — раньше всех, для тестеров", "download",
            self._inline_updates, "обновления обновить версия бета канал откат подпись")

    def _inline_updates(self) -> QWidget:
        """Канал обновлений (stable / beta) и проверка сейчас (github_update)."""
        import github_update
        w = self.win
        box = QWidget(); box.setObjectName("YaPageInner")
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        info = QLabel(f"Сейчас: {github_update.local_version() or '?'}. Ставятся только выпуски, подписанные "
                      "автором; если новая версия не запустится, ECHOES сам вернёт прошлую.")
        info.setObjectName("YaSub")
        info.setWordWrap(True)
        v.addWidget(info)
        row = QHBoxLayout()
        from PyQt6.QtWidgets import QComboBox
        cb = QComboBox()
        cb.addItem("Стабильные — для всех", "stable")
        cb.addItem("Бета — раньше всех, могут быть ошибки", "beta")
        cb.setCurrentIndex(max(0, cb.findData(github_update.channel_of(w.settings))))

        def picked(i):
            w.settings["update_channel"] = cb.itemData(i)
            w._schedule_settings_save()
            up = getattr(w, "_gh_updater", None)
            if up is not None:
                up.check(manual=True)
        cb.currentIndexChanged.connect(picked)
        row.addWidget(cb, 1)
        chk = QPushButton("Проверить сейчас")
        chk.setObjectName("InlineAct")
        chk.clicked.connect(lambda: getattr(w, "_gh_updater", None) and w._gh_updater.check(manual=True))
        row.addWidget(chk)
        v.addLayout(row)
        return box

    def _inline_prefs(self):
        """«Окно и масштаб» без кнопок-переходов: всё, куда они вели, теперь рядом в Настройках."""
        import player_prefs
        dlg = player_prefs.PrefsDialog(self.win, (self.win.__dict__.get("_prefs") or {}).get("keys") or {})
        for b in dlg.findChildren(QPushButton):
            if b.text().endswith("…") or b.text().startswith(("Горячие клавиши —", "Палитра команд")):
                b.hide()
        return dlg

    def _inline_themes(self) -> QWidget:
        """Все темы плеера плитками по группам (вместо меню)."""
        from themes import theme_groups
        box = QWidget(); box.setObjectName("YaPageInner")
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        cur = self.win.settings.get("theme", "")
        btns = []

        def pick(name):
            for b in btns:
                b.setChecked(b.text() == name)
            self.win._request_theme(name)
        for title, hint, names in theme_groups():
            if not names:
                continue
            lab = QLabel(title); lab.setObjectName("YaSub")
            lab.setToolTip(hint)
            v.addWidget(lab)
            holder = QWidget(); holder.setObjectName("YaPageInner")
            fl = FlowLayout(holder, 6, 6)
            for name in names:
                b = chip(name)
                b.setChecked(name == cur)
                b.setToolTip(hint)
                b.clicked.connect(lambda _=False, n=name: pick(n))
                fl.addWidget(b)
                btns.append(b)
            v.addWidget(holder)
        return box

    def _build_skin_card(self, hub) -> QWidget:
        """«Тема Echoes Music»: цвета, шрифт и кнопки — окно настройки с предпросмотром (ya_skin)."""
        import ya_skin
        sk = ya_skin.normalize(self.win.settings.get("ya_skin"))
        card = QFrame()
        card.setObjectName("YaSkinCard")
        card.setStyleSheet("QFrame#YaSkinCard{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 %s,stop:1 #151515);"
                           "border-radius:18px;}" % ya_skin.rgba(sk["accent"], 0.22))
        card.setMaximumWidth(760)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(18)
        col = QVBoxLayout()
        col.setSpacing(4)
        t = QLabel("Тема Echoes Music")
        t.setStyleSheet("font-size:22px;font-weight:800;background:transparent;")
        col.addWidget(t)
        d = QLabel("Цвета, шрифты, отдельное скругление кнопок и интерфейса, стекло, фон и живые эффекты — в одном окне с предпросмотром.")
        d.setObjectName("YaSub")
        d.setWordWrap(True)
        col.addWidget(d)
        sw = QHBoxLayout()
        sw.setSpacing(6)
        for k in ("accent", "bg", "panel", "card", "text"):
            dot = QLabel()
            dot.setFixedSize(22, 22)
            dot.setStyleSheet(f"background:{sk[k]};border:1px solid rgba(255,255,255,0.25);border-radius:11px;")
            sw.addWidget(dot)
        sw.addStretch(1)
        col.addLayout(sw)
        lay.addLayout(col, 1)
        b = QPushButton("  Настроить")
        b.setObjectName("AccentBtn")
        b.setIcon(ya_icon("palette", 16, "#000000"))
        b.clicked.connect(lambda: ya_skin.SkinEditor(self.win, self.win).exec())
        lay.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        hub.v.addWidget(card)
        return card

    def _build_layout_card(self) -> QWidget:
        """Новая раскладка или Legacy (старый вид), панель разделов справа/слева — сразу, без перезапуска."""
        win = self.win
        card = QFrame()
        card.setObjectName("YaWaveCard")
        card.setStyleSheet("QFrame#YaWaveCard{background:#171717;border-radius:16px;}")
        card.setMaximumWidth(760)
        v = QVBoxLayout(card)
        v.setContentsMargins(18, 14, 18, 14)
        v.setSpacing(8)
        t = QLabel("Вид Echoes Music")
        t.setStyleSheet("font-size:14px;font-weight:700;background:transparent;")
        v.addWidget(t)
        d = QLabel("Новый вид: плейлисты и поиск сверху, разделы на боковой панели, плеер снизу, Echoes.NET в углу. "
                   "Legacy — прежний вид ECHOES: всё в колонке слева.")
        d.setObjectName("YaSub")
        d.setWordWrap(True)
        v.addWidget(d)
        cur = win.settings.get("ya_layout", "new")
        side = win.settings.get("ya_side", "right")

        def apply(**kw):
            win.settings.update(kw)
            try:
                win.save_settings()
            except Exception:                                  # noqa: BLE001
                pass
            import ya_skin
            QTimer.singleShot(0, lambda: ya_skin.reskin(win))
        r1 = QHBoxLayout()
        for key, text in (("new", "Новый вид"), ("classic", "Legacy — старый вид ECHOES")):
            b = chip(text)
            b.setChecked(cur == key)
            b.clicked.connect(lambda _=False, key=key: apply(ya_layout=key) if key != cur else None)
            r1.addWidget(b)
        r1.addStretch(1)
        v.addLayout(r1)
        r2 = QHBoxLayout()
        lab = QLabel("Панель разделов:")
        lab.setStyleSheet("background:transparent;")
        r2.addWidget(lab)
        for key, text in (("right", "Справа"), ("left", "Слева")):
            b = chip(text)
            b.setChecked(side == key)
            b.setEnabled(cur != "classic")
            b.clicked.connect(lambda _=False, key=key: apply(ya_side=key) if key != side else None)
            r2.addWidget(b)
        r2.addStretch(1)
        v.addLayout(r2)
        return card

    def _build_placeholder_card(self) -> QWidget:
        """Своя картинка вместо полупрозрачной ноты, когда у трека или исполнителя нет обложки."""
        win = self.win
        card = QFrame()
        card.setObjectName("YaWaveCard")
        card.setStyleSheet("QFrame#YaWaveCard{background:#171717;border-radius:16px;}")
        card.setMaximumWidth(760)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(14)
        prev = QLabel()
        prev.setFixedSize(56, 56)

        def show_prev():
            prev.setPixmap(_placeholder(112, "ECHOES").scaled(56, 56, Qt.AspectRatioMode.IgnoreAspectRatio,
                                                               Qt.TransformationMode.SmoothTransformation))
        show_prev()
        lay.addWidget(prev, 0, Qt.AlignmentFlag.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel("Картинка, когда нет обложки")
        t.setStyleSheet("font-size:14px;font-weight:700;background:transparent;")
        d = QLabel("Вместо полупрозрачной ноты — своя картинка у треков и исполнителей без обложки.")
        d.setObjectName("YaSub")
        d.setWordWrap(True)
        col.addWidget(t)
        col.addWidget(d)
        lay.addLayout(col, 1)

        def apply(path):
            win.settings["placeholder_img"] = path
            try:
                win.save_settings()
            except Exception:                                  # noqa: BLE001
                pass
            set_placeholder(path)
            show_prev()
            self._dirty.update({"foryou", "collection", "albums", "wave", "search"})
            if hasattr(self, "pl_strip"):
                self.pl_strip.refresh()
            self.update()

        def pick():
            from PyQt6.QtWidgets import QFileDialog
            fn, _ = QFileDialog.getOpenFileName(self, "Картинка вместо ноты", "",
                                                "Картинки (*.png *.jpg *.jpeg *.webp *.bmp *.gif)")
            if not fn:
                return
            try:                                               # копия рядом с настройками — не потеряется
                import shutil
                dst = data_home.root() / ("placeholder" + Path(fn).suffix.lower())
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(fn, dst)
                fn = str(dst)
            except OSError:
                pass
            apply(fn)
        b = QPushButton("Выбрать…")
        b.clicked.connect(pick)
        lay.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        r = QPushButton("Нота")
        r.setToolTip("Вернуть стандартную полупрозрачную ноту")
        r.clicked.connect(lambda: apply(""))
        lay.addWidget(r, 0, Qt.AlignmentFlag.AlignVCenter)
        return card

    def _build_intro_card(self) -> QWidget:
        """Заставка при запуске (intro_anim): включить/выключить и посмотреть."""
        import intro_anim
        card = QFrame()
        card.setObjectName("YaWaveCard")
        card.setStyleSheet("QFrame#YaWaveCard{background:#171717;border-radius:16px;}")
        card.setMaximumWidth(760)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        sw = Switch(intro_anim.enabled(self.win.settings))

        def flip(on):
            self.win.settings["intro_anim"] = bool(on)
            try:
                self.win.save_settings()
            except Exception:                                  # noqa: BLE001
                pass
        sw.toggled.connect(flip)
        lay.addWidget(sw, 0, Qt.AlignmentFlag.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel("Анимация при запуске")
        t.setStyleSheet("font-size:14px;font-weight:700;background:transparent;")
        d = QLabel("Солнце выпускает лучи, из темноты выходит надпись ECHOES. Клик — пропустить.")
        d.setObjectName("YaSub")
        d.setWordWrap(True)
        col.addWidget(t)
        col.addWidget(d)
        lay.addLayout(col, 1)
        b = QPushButton("Показать")
        b.clicked.connect(lambda: intro_anim.play(self.win))
        lay.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        return card

    def _build_net_setting_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("YaWaveCard")
        card.setStyleSheet("QFrame#YaWaveCard{background:#171717;border-radius:16px;}")
        card.setMaximumWidth(760)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel("Echoes.NET — друзья, сообщения, комнаты")
        t.setStyleSheet("font-size:14px;font-weight:700;background:transparent;")
        d = QLabel("Профиль, приватность («для всех» или только друзьям), уведомления, GIF и свои реакции.")
        d.setObjectName("YaSub")
        d.setWordWrap(True)
        col.addWidget(t)
        col.addWidget(d)
        lay.addLayout(col, 1)
        b = QPushButton("Открыть")
        b.clicked.connect(self._open_net_settings)
        lay.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        return card

    def _build_notif_setting_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("YaWaveCard")
        card.setStyleSheet("QFrame#YaWaveCard{background:#171717;border-radius:16px;}")
        card.setMaximumWidth(760)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        ic = QLabel()
        ic.setPixmap(ya_icon("bell", 22, YELLOW).pixmap(22, 22))
        ic.setStyleSheet("background:transparent;")
        lay.addWidget(ic, 0, Qt.AlignmentFlag.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel("Уведомления")
        t.setStyleSheet("font-size:14px;font-weight:700;background:transparent;")
        d = QLabel("Карточки в углу экрана со звуком: сообщения, заявки, посты подписок, друзья в сети. "
                   "Звук, громкость, угол экрана, «Не беспокоить».")
        d.setObjectName("YaSub")
        d.setWordWrap(True)
        col.addWidget(t)
        col.addWidget(d)
        lay.addLayout(col, 1)
        b = QPushButton("Настроить")
        b.clicked.connect(lambda: self._open_net_settings("_notif_anchor"))
        lay.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        return card

    def _open_net_settings(self, anchor=None):
        self.show_page("net")
        try:
            np_ = self.pages["net"]
            np_.show_tab("net")
            if anchor:
                def scroll():                                  # вкладку за это время могли пересобрать —
                    from PyQt6 import sip                      # берём виджет заново, а не прежний (удалённый)
                    w = getattr(np_, anchor, None)
                    if w is not None and not sip.isdeleted(w):
                        np_.net_page.ensureWidgetVisible(w, 0, 40)
                QTimer.singleShot(120, scroll)
        except Exception:                                      # noqa: BLE001
            pass

    def _build_wave_setting(self) -> QWidget:
        """Карточка «Слушать онлайн»: стриминг онлайн-треков по умолчанию (вместо тумблера «скачивать новое с волны» —
        новое в волне теперь всегда играет потоком, сразу и без скачивания)."""
        card = QFrame()
        card.setObjectName("YaWaveCard")
        card.setStyleSheet("QFrame#YaWaveCard{background:#171717;border-radius:16px;}")
        card.setMaximumWidth(760)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(16)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel("Слушать онлайн без скачивания")
        t.setStyleSheet("font-size:14px;font-weight:700;background:transparent;")
        d = QLabel("Треки из поиска, альбомов и исполнителей играют сразу — потоком с YouTube Music / SoundCloud. "
                   "Скачать в коллекцию — кнопкой у трека. В «Моей волне» новые похожие треки всегда идут потоком.")
        d.setObjectName("YaSub")
        d.setWordWrap(True)
        d.setStyleSheet("background:transparent;")
        col.addWidget(t)
        col.addWidget(d)
        lay.addLayout(col, 1)
        self.stream_sw = Switch(bool(self.win.settings.get("stream_default", True)))
        self.stream_sw.toggled.connect(self._on_stream_default)
        lay.addWidget(self.stream_sw, 0, Qt.AlignmentFlag.AlignVCenter)
        return card

    def _build_mood_filter_setting(self) -> QWidget:
        """Карточка-тумблер: фильтр по настроению на страницах плейлистов (по умолчанию выключен)."""
        card = QFrame()
        card.setObjectName("YaWaveCard")
        card.setStyleSheet("QFrame#YaWaveCard{background:#171717;border-radius:16px;}")
        card.setMaximumWidth(760)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(16)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel("Фильтр по настроению в плейлистах")
        t.setStyleSheet("font-size:14px;font-weight:700;background:transparent;")
        d = QLabel("Экспериментальная функция: на страницах плейлистов и «Мне нравится» появляются кнопки "
                   "«Бодрое / Спокойное / Весёлое / Грустное». Настроение определяется по звучанию треков.")
        d.setObjectName("YaSub")
        d.setWordWrap(True)
        d.setStyleSheet("background:transparent;")
        col.addWidget(t)
        col.addWidget(d)
        lay.addLayout(col, 1)
        self.mood_filter_sw = Switch(bool(self.win.settings.get("mood_filter", False)))
        self.mood_filter_sw.toggled.connect(self._on_mood_filter)
        lay.addWidget(self.mood_filter_sw, 0, Qt.AlignmentFlag.AlignVCenter)
        return card

    def _build_boost_setting(self) -> QWidget:
        """Карточка «Экстремальная громкость» (100 %…10 000 %) — общий блок плеера."""
        card = QFrame()
        card.setObjectName("YaWaveCard")
        card.setStyleSheet("QFrame#YaWaveCard{background:#171717;border-radius:16px;}")
        card.setMaximumWidth(760)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(6)
        t = QLabel("Экстремальная громкость")
        t.setStyleSheet("font-size:14px;font-weight:700;background:transparent;")
        d = QLabel("Множитель поверх ползунка громкости: 500 % — в 5 раз громче, "
                   "10 000 % — в 100 раз. На больших значениях будет перегруз.")
        d.setObjectName("YaSub")
        d.setWordWrap(True)
        d.setStyleSheet("background:transparent;")
        lay.addWidget(t)
        lay.addWidget(d)
        lay.addWidget(self.win._make_boost_block(compact=True))
        return card

    def _on_mood_filter(self, on):
        self.win.settings["mood_filter"] = bool(on)
        self.win.save_settings()
        if getattr(self, "_pp_tracks", None) is not None:
            self._pp_filters_reset(self._pp_tracks, getattr(self, "_pp_fkey", None))

    def _on_stream_default(self, on):
        self.win.settings["stream_default"] = bool(on)
        self.win.save_settings()

    def adopt_settings(self, panel: QWidget):
        """Правая панель плеера (эквалайзер, пресеты, таймеры…) — сюда, одной сплошной лентой, как настройки
        в Spotify: все её страницы друг под другом, без листания ‹ › и без отдельной карточки."""
        self._settings_host = panel
        self._settings_slot.addWidget(panel)
        panel.hide()
        self._unfolded = []
        stack = getattr(self.win, "_rp_stack", None)
        if stack is None:                                  # на всякий случай — как раньше, панелью
            panel.show()
            self._restyle_pager(True)
            return
        for i in range(stack.count()):
            sc = stack.widget(i)
            take = getattr(sc, "takeWidget", None)
            content = take() if take is not None else None
            if content is None:
                continue
            if i:
                line = QFrame()
                line.setFixedHeight(1)
                line.setStyleSheet("background:rgba(255,255,255,0.08);margin:0;")
                self._settings_slot.addSpacing(14)
                self._settings_slot.addWidget(line)
                self._settings_slot.addSpacing(6)
            else:
                line = None
            self._settings_slot.addWidget(content)
            content.show()
            ss = content.styleSheet()
            content.setStyleSheet(ss + "QLabel#Section{font-size:18px;font-weight:800;color:#ffffff;"
                                       "letter-spacing:0px;padding-top:12px;padding-bottom:2px;}")
            self._unfolded.append((sc, content, line, ss))
            if line is not None:
                line.hide()                                    # разделы сами делят настройки — линии не нужны
            hub = getattr(self, "settings_hub", None)
            if hub is not None and content.layout() is not None:
                hub.index_layout(content.layout(), container=content)
        hub = getattr(self, "settings_hub", None)
        if hub is not None:
            # «Мощность звука» старой панели — тот же множитель, что карточка «Экстремальная громкость»
            # раздела «Звук»: два одинаковых блока подряд выглядели как развалившаяся страница
            for _sc, content, _line, _ss in self._unfolded:
                for box in content.findChildren(QWidget, "BoostBlock"):
                    if any(l.objectName() == "Section" for l in box.findChildren(QLabel)):
                        box.hide()                    # спрятан не разделом — при переключении разделов не вернётся
            hub.refresh()

    def _restyle_pager(self, on: bool):
        """«‹ Оформление ›» панели настроек: в этой теме — круглые кнопки и крупный заголовок."""
        w = self.win
        prev, nxt, lbl = (getattr(w, n, None) for n in ("_rp_prev_btn", "_rp_next_btn", "_rp_page_lbl"))
        if prev is None or nxt is None or lbl is None:
            return
        if on:
            self._pager_saved = [(b, b.styleSheet(), b.text(), b.minimumSize(), b.maximumSize()) for b in (prev, nxt)] \
                + [(lbl, lbl.styleSheet(), "", None, None)]
            ic = ya_icon("back", 20, "#e6e6e6")
            for b, ico in ((prev, ic), (nxt, QIcon(ic.pixmap(20, 20).transformed(QTransform().scale(-1, 1))))):
                b.setStyleSheet("")
                b.setObjectName("YaIcon")
                b.setText("")
                b.setIcon(ico)
                b.setIconSize(QSize(20, 20))
                b.setFixedSize(38, 38)
                b.style().unpolish(b); b.style().polish(b)
            lbl.setStyleSheet("color:#ffffff;font-size:14px;font-weight:800;background:transparent;")
        else:
            for wdg, ss, txt, mn, mx in getattr(self, "_pager_saved", []):
                wdg.setStyleSheet(ss)
                if mn is not None:
                    wdg.setObjectName("")
                    wdg.setText(txt)
                    wdg.setIcon(QIcon())
                    wdg.setMinimumSize(mn); wdg.setMaximumSize(mx)
                    wdg.style().unpolish(wdg); wdg.style().polish(wdg)
            self._pager_saved = []

    def release_settings(self):
        self._restyle_pager(False)
        hub = getattr(self, "settings_hub", None)
        if hub is not None:                                    # всё спрятанное разделами — вернуть видимым
            ws = []
            for _sc, content, _line, _ss in getattr(self, "_unfolded", []):
                try:
                    ws += [content] + content.findChildren(QWidget)
                except RuntimeError:
                    pass
            hub.remove_widgets(ws)
        for sc, content, line, ss in getattr(self, "_unfolded", []):   # страницы — обратно в панель
            try:
                content.setStyleSheet(ss)
                self._settings_slot.removeWidget(content)
                sc.setWidget(content)
                if line is not None:
                    self._settings_slot.removeWidget(line)
                    line.deleteLater()
            except RuntimeError:
                pass
        self._unfolded = []
        for i in reversed(range(self._settings_slot.count())):    # промежутки между страницами
            if self._settings_slot.itemAt(i).spacerItem() is not None:
                self._settings_slot.takeAt(i)
        p = self._settings_host
        if p is not None:
            self._settings_slot.removeWidget(p)
            p.show()
        self._settings_host = None
        return p

    def paintEvent(self, e):
        dec = getattr(self, "decor", None)
        if dec is not None:                                    # аура обложки / своя картинка / время суток
            p = QPainter(self)
            dec.paint_shell(p, e.rect())
            p.end()

    def shutdown(self):
        dec = getattr(self, "decor", None)
        if dec is not None:
            dec.shutdown()
        if getattr(self, "_listener_panel", None) is not None:
            panel = self._listener_panel
            panel.metric_timer.stop()
            if self.win._listening_tools.dialog is panel:
                self.win._listening_tools.dialog = None
        self.pages["tierlist"].shutdown()
        self._timer.stop()
        import ui_anim
        ui_anim._finish(self.stack)
        from ya_wave import WaveHero
        for hero in self.findChildren(WaveHero):
            hero._timer.stop();hero._worker.stop()
            if hero._worker.is_alive():hero._worker.join(2)
        try:
            self.wave.shutdown()
            self.wave.wheel._timer.stop()
        except RuntimeError:
            pass
        clear_cover_cache()                          # тема закрыта — её обложки в памяти не нужны
        _ICON_CACHE.clear()


# ══════════════════════════════════════════════════════════════════════════ #
#  Онлайн-страница исполнителя (как в Яндекс Музыке)
# ══════════════════════════════════════════════════════════════════════════ #

import re as _re
import threading as _threading


class ArtistHeader(QWidget):
    """Шапка артиста: нейтральное стекло, круглое фото, имя, статистика
    и «серверы» (Deezer / Wikipedia / Last.fm) с индикаторами подключения."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(300)
        self.name = ""
        self.kind = "Исполнитель"
        self.stats = ""
        self.picture = ""
        self.sources = []          # [(имя, состояние: "wait"|"ok"|"off")]
        self._banner = None
        self._banner_key = None
        self._t0 = time.monotonic()
        self._loading = False
        self._timer = FrameTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self.update)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(250, 0, 30, 26)
        lay.addStretch(1)
        self.btn_row = QHBoxLayout()
        self.btn_row.setSpacing(10)
        lay.addLayout(self.btn_row)

    def set_loading(self, on):
        self._loading = on
        if on:
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def set_picture(self, path):
        self.picture = path or ""
        self._banner = None
        self.update()

    def _make_banner(self, W, H):
        import ya_decor                                        # размытое фото исполнителя в шапке
        pm = ya_decor.artist_banner(W, H, self.picture)
        if pm is not None:
            return pm
        from echo_glass import liquid_surface
        return liquid_surface(QSize(W, H), radius=16)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        W, H = self.width(), self.height()
        key = (W, H, self.picture)
        if self._banner is None or self._banner_key != key:
            self._banner = self._make_banner(W, H)
            self._banner_key = key
        clip = QPainterPath(); clip.addRoundedRect(QRectF(0, 0, W, H + 20), 16, 16)
        p.setClipPath(clip)
        p.drawPixmap(0, 0, self._banner)
        p.setClipping(False)
        # фото
        ph = QRectF(32, H - 222, 190, 190)
        import ya_decor
        if self.picture:
            p.drawPixmap(ph.toRect(), cover_pixmap(self.picture, 190, 95, circle=True))
        elif self._loading and ya_decor.on("sun_loader"):     # солнце ECHOES: лучи загораются по кругу
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 12))
            p.drawEllipse(ph)
            ya_decor.paint_sun(p, ph.center(), 46, time.monotonic() - self._t0, spin=True)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 18 if not self._loading else
                              int(18 + 14 * (0.5 + 0.5 * math.sin((time.monotonic() - self._t0) * 4)))))
            p.drawEllipse(ph)
        x = 250
        p.setPen(QColor(255, 255, 255, 170))
        p.setFont(ya_font(12, QFont.Weight.DemiBold))
        p.drawText(QRectF(x, H - 220, W - x - 20, 18), Qt.AlignmentFlag.AlignLeft, self.kind)
        f = ya_font(int(max(34, min(60, W * 0.045))), QFont.Weight.Black)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(x, H - 200, W - x - 20, 76), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(f).elidedText(self.name, Qt.TextElideMode.ElideRight, int(W - x - 20)))
        p.setFont(ya_font(13, QFont.Weight.DemiBold))
        p.setPen(QColor(255, 255, 255, 215))
        stats = self.stats
        if self._loading:
            stats = "Загружаем данные с серверов" + "." * (1 + int((time.monotonic() - self._t0) * 3) % 3)
        p.drawText(QRectF(x, H - 122, W - x - 20, 20), Qt.AlignmentFlag.AlignLeft, stats)
        # индикаторы серверов (справа сверху)
        p.setFont(ya_font(11, QFont.Weight.DemiBold))
        bx = W - 20
        for name, st in reversed(self.sources):
            fm = QFontMetrics(p.font())
            w = fm.horizontalAdvance(name) + 30
            r = QRectF(bx - w, 16, w, 24)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 120))
            p.drawRoundedRect(r, 12, 12)
            if st == "ok":
                dot = QColor("#3ddc84")
            elif st == "wait":
                a = 0.5 + 0.5 * math.sin((time.monotonic() - self._t0) * 6)
                dot = QColor(255, 219, 26, int(120 + 135 * a))
            else:
                dot = QColor(120, 120, 120)
            p.setBrush(dot)
            p.drawEllipse(QPointF(r.left() + 13, r.center().y()), 4, 4)
            p.setPen(QColor(255, 255, 255, 220 if st == "ok" else 140))
            p.drawText(r.adjusted(22, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)
            bx -= w + 8
        p.end()


class TopTrackRow(QWidget):
    """Строка «Популярных треков» с сервера: номер, обложка, название,
    прослушивания (Last.fm) или полоса популярности (Deezer), «в коллекции»."""
    clicked = pyqtSignal()
    download = pyqtSignal()

    def __init__(self, n, t, local, max_rank, parent=None):
        super().__init__(parent)
        self.n, self.t, self.local, self.max_rank = n, t, local, max(1, max_rank)
        self._hover = False
        self.state, self.pct, self.path = "", 0.0, ""
        self.setFixedHeight(56)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

    def enterEvent(self, e):
        self._hover = True; self.update()

    def leaveEvent(self, e):
        self._hover = False; self.update()

    def mouseMoveEvent(self, e):
        self._mx = e.position().x()
        self.update()

    def _listen_rect(self) -> QRect:
        """Кнопка «слушать» — онлайн (потоком) или из коллекции, если трек уже скачан."""
        return QRect(self.width() - 262, int(self.height() / 2 - 15), 100, 30)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if not self.local and self.width()-145 <= e.position().x() <= self.width()-45:
                self.download.emit()
            else:
                self.clicked.emit()                       # и кнопка «слушать», и вся строка — играть

    def _on_state(self, state, value):
        """Колбэк очереди закачки (queued / progress / retry / done / error)."""
        if state == "progress":
            self.state, self.pct = "progress", float(value)
        elif state == "done":
            self.state, self.path, self.local = "done", str(value), True
            self.setToolTip("Скачано — нажмите, чтобы слушать")
        elif state == "error":
            self.state = "error"
            self.setToolTip(f"Не удалось скачать: {value}")
        elif state in ("queued", "retry", "search"):
            self.state = state
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        if self._hover:
            path = QPainterPath(); path.addRoundedRect(QRectF(0, 2, W, H - 4), 10, 10)
            p.fillPath(path, QColor(255, 255, 255, 14))
        dim = 1.0 if (self.local or self.state) else 0.55
        p.setFont(ya_font(14, QFont.Weight.DemiBold))
        p.setPen(QColor(255, 255, 255, int(150 * dim)))
        p.drawText(QRectF(4, 0, 28, H), Qt.AlignmentFlag.AlignCenter, ("▶" if self._hover else str(self.n)))
        cov = QRect(40, 8, 40, 40)
        p.setOpacity(dim)
        p.drawPixmap(cov, cover_pixmap(self.t.get("cover", ""), 40, 6, seed=self.t.get("title", ""), lazy=self))
        p.setOpacity(1.0)
        tx = 94
        tw = int(W * 0.48) - tx
        f = ya_font(14, QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, int(255 * dim)))
        p.drawText(QRect(tx, 9, tw, 20), Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(f).elidedText(self.t.get("title", ""), Qt.TextElideMode.ElideRight, tw))
        f2 = ya_font(12)
        p.setFont(f2)
        p.setPen(QColor(140, 140, 140))
        sub = self.t.get("artists", "")
        if self.t.get("album"):
            sub += "  ·  " + self.t["album"]
        p.drawText(QRect(tx, 29, tw, 18), Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(f2).elidedText(sub, Qt.TextElideMode.ElideRight, tw))
        # прослушивания или популярность
        from artist_net import human
        mx = int(W * 0.52)
        if self.t.get("playcount"):
            p.setFont(ya_font(12, QFont.Weight.DemiBold))
            p.setPen(QColor(220, 220, 220))
            p.drawText(QRect(mx, 0, 190, H), Qt.AlignmentFlag.AlignVCenter,
                       f"{human(self.t['playcount'])} прослушиваний")
        else:
            frac = min(1.0, self.t.get("rank", 0) / self.max_rank)
            p.setPen(Qt.PenStyle.NoPen)
            for k in range(10):
                on = k < round(frac * 10)
                p.setBrush(QColor(255, 255, 255, 200 if on else 40))
                p.drawRoundedRect(QRectF(mx + k * 9, H / 2 - 7, 5, 14), 2, 2)
        # слушать (онлайн или из коллекции)
        lr = QRectF(self._listen_rect())
        on = self._hover and lr.contains(QPointF(getattr(self, "_mx", -1), H / 2))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(YELLOW) if on else QColor(255, 255, 255, 26))
        p.drawRoundedRect(lr, 15, 15)
        ink = "#111111" if on else "#ffffff"
        ya_icon("play", 14, ink).paint(p, QRect(int(lr.x()) + 12, int(lr.center().y()) - 7, 14, 14))
        p.setFont(ya_font(12, QFont.Weight.Bold))
        p.setPen(QColor(ink))
        p.drawText(lr.adjusted(30, 0, -6, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   "ищу…" if getattr(self,'_stream_busy',False) else "слушать" if (self.local or self.state == "done") else "онлайн")
        # в коллекции
        p.setFont(ya_font(11, QFont.Weight.DemiBold))
        st_txt = {"search": ("ищу…", "#ffdb1a"), "queued": ("в очереди", "#ffdb1a"),
                  "retry": ("другой источник…", "#ffb347"), "error": ("ошибка", "#ff6b6b")}
        if self.state == "progress":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 40))
            p.drawRoundedRect(QRectF(W - 150, H / 2 - 2, 80, 4), 2, 2)
            p.setBrush(QColor(YELLOW))
            p.drawRoundedRect(QRectF(W - 150, H / 2 - 2, 80 * min(1.0, self.pct / 100.0), 4), 2, 2)
        elif self.state in st_txt:
            txt, colr = st_txt[self.state]
            p.setPen(QColor(colr))
            p.drawText(QRect(W - 150, 0, 96, H), Qt.AlignmentFlag.AlignVCenter, txt)
        elif self.local:
            p.setBrush(QColor("#3ddc84")); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(W - 150, H / 2), 3.5, 3.5)
            p.setPen(QColor("#3ddc84"))
            p.drawText(QRect(W - 142, 0, 90, H), Qt.AlignmentFlag.AlignVCenter, "в коллекции")
        else:
            ya_icon("download", 14, "#bdbdbd").paint(p, QRect(W - 150, int(H / 2 - 7), 14, 14))
            p.setPen(QColor(170, 170, 170))
            p.drawText(QRect(W - 132, 0, 80, H), Qt.AlignmentFlag.AlignVCenter, "скачать")
        dur = int(self.t.get("duration") or 0)
        if dur:
            p.setPen(QColor(140, 140, 140))
            p.setFont(ya_font(12))
            p.drawText(QRect(W - 56, 0, 50, H), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, _fmt(dur))
        p.end()


class ArtistPage(Page):
    """Карточка исполнителя: данные с серверов + ваша коллекция."""

    def __init__(self, shell, parent=None):
        super().__init__(parent, margins=(0, 0, 0, 24))
        self.shell = shell
        self.name = ""
        self.local = []
        self.data = None
        self._req = 0
        self.header = None

    # ── загрузка ── #

    def load(self, name, local_tracks, force=False):
        self.name, self.local = name, list(local_tracks)
        self._req += 1
        req = self._req
        from artist_net import cached
        c = cached(name)
        self._render(c, loading=True)
        key = self.shell.win.settings.get("lastfm_key", "")

        def work():
            from artist_net import fetch_artist
            try:
                d = fetch_artist(name, key, force=force, titles=[t.get("title", "") for t in local_tracks])
            except Exception as e:                   # noqa: BLE001
                print("[artist]", e)
                d = {"name": name, "sources": [], "error": str(e)}
            self.shell.win._ui_bridge.call.emit(lambda: req == self._req and self._render(d, loading=False))
        _threading.Thread(target=work, daemon=True).start()

    # ── отрисовка ── #

    def _local_match(self, title):
        from track_identity import similarity as _sim
        best, bs = None, 0.0
        for t in self.local:
            s = _sim(title, sanitize_title(t.get("title", "")))
            if s > bs:
                best, bs = t, s
        return best if bs >= 0.84 else None

    def _render(self, d, loading):
        from artist_net import human
        self.clear()
        self.data = d
        w = self.shell.win
        d = d or {}
        hdr = ArtistHeader()
        self.header = hdr
        hdr.name = d.get("name") or self.name
        hdr.kind = "Исполнитель"
        hdr.set_picture(d.get("picture", ""))
        parts = []
        from artist_net import audience
        n_aud, what = audience(d)
        if n_aud:
            parts.append(f"{human(n_aud)} {what}")
        if d.get("fans") and what != "поклонников":
            parts.append(f"{human(d['fans'])} поклонников на Deezer")
        if d.get("playcount"):
            label = 'прослушиваний'
            if d.get('sc_profile'):
                label = f"прослушиваний SoundCloud · {d.get('sc_counted',0)} треков"
                if not d.get('sc_complete'):label += ' · неполная сумма'
            parts.append(f"{human(d['playcount'])} {label}")
        if d.get("albums_count"):
            parts.append(f"{d['albums_count']} релизов")
        parts.append(f"{len(self.local)} в вашей коллекции")
        hdr.stats = "  ·  ".join(parts)
        if d.get("error") and not loading:
            hdr.stats = d["error"] + ("  ·  показаны сохранённые данные" if d.get("stale") else "")
        srcs = d.get("sources", [])
        names = ["Deezer", "Wikipedia"] + (["Last.fm"] if w.settings.get("lastfm_key") else []) +             (["SoundCloud"] if "SoundCloud" in srcs else [])
        hdr.sources = [(n, "ok" if n in srcs else ("wait" if loading else "off")) for n in names]
        hdr.set_loading(loading and not d.get("sources"))
        b = QPushButton("  Слушать")
        b.setObjectName("YaYellow"); b.setIcon(ya_icon("play", 18, "#000000")); b.setMinimumHeight(40)
        b.clicked.connect(self._play_all)
        hdr.btn_row.addWidget(b)
        b = QPushButton("  Моя волна по артисту"); b.setIcon(ya_icon("wave", 18)); b.setMinimumHeight(40)
        b.clicked.connect(lambda: self.shell.start_wave("artist", self.name))
        hdr.btn_row.addWidget(b)
        b = QPushButton("  Все треки"); b.setIcon(ya_icon("note", 18)); b.setMinimumHeight(40)
        b.setToolTip("Вся дискография исполнителя с YouTube Music: каждый трек и число прослушиваний")
        b.clicked.connect(lambda: self.shell.open_release("all", (self.data or {}).get("name") or self.name))
        hdr.btn_row.addWidget(b)
        top_all = d.get("top") or []
        if any(self._local_match(t.get("title", "")) is None for t in top_all[:10]):
            b = QPushButton("  Скачать популярные"); b.setIcon(ya_icon("download", 18)); b.setMinimumHeight(40)
            b.setToolTip("Найти на YouTube Music / SoundCloud и скачать все популярные треки, которых нет в коллекции")
            b.clicked.connect(self._download_all_top)
            hdr.btn_row.addWidget(b)
        import artist_follow as _AF
        art_name = d.get("name") or self.name
        fb = QPushButton()
        fb.setMinimumHeight(40)

        def style_fb(btn=fb, n=art_name):
            on = _AF.is_followed(self.shell.win, n)
            btn.setText("  Вы подписаны" if on else "  Подписаться")
            btn.setIcon(ya_icon("check" if on else "plus", 18))
            btn.setToolTip("Отписаться" if on else "Новые релизы исполнителя — уведомлениями, он появится в «Подписках»")
        style_fb()
        fb.clicked.connect(lambda _=False, n=art_name: (_AF.set_follow(self.shell.win, n,
                                                                       not _AF.is_followed(self.shell.win, n)),
                                                        style_fb()))
        hdr.btn_row.addWidget(fb)
        b = icon_button("repeat", "Обновить с серверов", 40, 20)
        b.clicked.connect(lambda: self.load(self.name, self.local, force=True))
        hdr.btn_row.addWidget(b)
        hdr.btn_row.addStretch(1)
        back = icon_button("back", "Назад", 36, 20)
        back.setParent(hdr)
        back.move(14, 14)
        back.setStyleSheet("QPushButton{border-radius:18px;}")
        back.clicked.connect(self.shell.go_back)
        self.v.addWidget(hdr)
        import ya_decor                                        # имя «прилипает» сверху, когда шапка уехала

        def play_first(row=hdr.btn_row):
            it = row.itemAt(0)
            w_ = it.widget() if it is not None else None
            if isinstance(w_, QPushButton):
                w_.click()
        ya_decor.attach_sticky(self, hdr.name, play_first)

        body = QWidget(); body.setObjectName("YaPage")
        bv = QVBoxLayout(body)
        bv.setContentsMargins(32, 4, 32, 0)
        bv.setSpacing(4)
        self.v.addWidget(body)

        if self.local:
            bv.addWidget(section_title("В вашей коллекции"))
            lv = TrackListView(self.shell)
            lv.set_auto_height(True)
            lv.set_rows(self.shell._lib_rows(self.local))
            bv.addWidget(lv.section_widget())

        top = d.get("top") or []
        if top:
            bv.addWidget(section_title("Популярные треки"))
            mr = max([t.get("rank", 0) for t in top] + [1])
            self._top_rows = []
            for i, t in enumerate(top[:10]):
                loc = self._local_match(t.get("title", ""))
                r = TopTrackRow(i + 1, t, loc is not None, mr)
                r.clicked.connect(lambda r=r, loc=loc: self._top_click(r, loc))
                r.download.connect(lambda r=r: self._download_top(r, play=False))
                bv.addWidget(r)
                if loc is None:
                    self._top_rows.append(r)
        elif loading:
            for i in range(5):
                sk = QFrame(); sk.setFixedHeight(48)
                sk.setStyleSheet("background:rgba(255,255,255,0.05);border-radius:10px;")
                bv.addWidget(sk)

        # вся дискография (YouTube Music): альбомы и синглы открываются — треки и прослушивания,
        # «Все треки исполнителя»; если YouTube Music не ответил — альбомы Deezer
        if not loading or d.get("albums"):
            from ya_online import DiscographyBlock
            bv.addWidget(DiscographyBlock(self.shell, d.get("name") or self.name, fallback=d.get("albums") or []))

        # «Об исполнителе» (как в Spotify): фото, слушатели, начало описания; клик — всё о нём
        if not loading or d.get("sources"):
            from ya_artist_about import AboutCard
            bv.addWidget(section_title("Об исполнителе"))
            bv.addWidget(AboutCard(self.shell, d, self.name))

        # «Поклонникам также нравится»: похожие с Deezer, если там нет — с YouTube Music
        rel = [{"name": r.get("name", ""), "sub": f"{human(r.get('fans', 0))} поклонников" if r.get("fans") else "Исполнитель",
                "picture": r.get("picture", ""), "url": r.get("picture_url", "")} for r in (d.get("related") or [])]
        if not rel:
            rel = [{"name": r.get("name", ""), "sub": f"{human(r['subs'])} подписчиков" if r.get("subs") else "Исполнитель",
                    "picture": "", "url": r.get("picture_url", "")} for r in (d.get("ytm_related") or [])]
        if rel:
            bv.addWidget(section_title("Поклонникам также нравится"))
            row = HRow()
            missing = []
            for r in rel[:14]:
                c = Card(r["name"], r["sub"], r["picture"], 150, circle=True, seed=r["name"])
                c.clicked.connect(lambda n=r["name"]: self.shell.open_artist(n))
                row.add(c)
                if not r["picture"] and r["url"]:
                    missing.append((c, r["url"]))
            bv.addWidget(row)
            if missing:
                from ya_artist_about import load_pictures
                load_pictures(self, missing)
        self.v.addStretch(1)
        self.verticalScrollBar().setValue(0)

    # ── действия ── #

    def _play_local(self, t):
        if t is None:
            return
        rows = self.shell._lib_rows([t])
        if rows:
            self.shell.play_row(rows[0])

    def _artist_for(self, t):
        return (self.data or {}).get("name") or self.name

    def _top_click(self, row, loc):
        if loc is not None:
            self._play_local(loc)
        elif row.path:
            self.shell.play_path(row.path)
        else:
            self._stream_top(row)

    def _stream_top(self, row):
        if getattr(row, '_stream_busy', False):return
        row._stream_busy=True
        row.update()
        t=dict(row.t);artist=self._artist_for(t);win=self.shell.win
        def work():
            try:
                import online_search
                found=([t] if t.get('url') else online_search.find_candidates(t.get('title',''),artist,t.get('duration',0)))
            except Exception:found=[]
            def done():
                from PyQt6 import sip
                if sip.isdeleted(row):return
                row._stream_busy=False
                row.update()
                if found:win.stream_tracks([dict(found[0])],playlist='Популярные треки')
                else:win._toast('Не удалось найти доступный поток для этого трека')
            win._ui_bridge.call.emit(done)
        _threading.Thread(target=work,daemon=True).start()

    def _download_all_top(self):
        for r in list(getattr(self, "_top_rows", [])):
            try:
                if not r.local and r.state in ("", "error"):
                    self._download_top(r, play=False)
            except RuntimeError:
                pass

    def _download_top(self, row, play=False):
        """Популярный трек с сервера → найти на YT Music / SoundCloud → скачать."""
        if row.state in ("search", "queued", "progress", "retry"):
            return
        row._on_state("search", 0)
        t = dict(row.t)
        artist = self._artist_for(t)
        w = self.shell.win
        target = self.shell.online_target_playlist()

        def work():
            cands = []
            try:
                import online_search
                cands = online_search.find_candidates(t.get("title", ""), artist, t.get("duration", 0))
            except Exception as e:                   # noqa: BLE001
                print("[artist dl]", e)

            def go():
                try:
                    row.state
                except RuntimeError:
                    return                           # страница уже перерисована
                if cands:
                    res, alts = dict(cands[0]), [c["url"] for c in cands[1:]]
                else:
                    q = f"{artist} - {t.get('title', '')}".replace(":", " ")
                    res, alts = {"url": f"ytsearch1:{q} audio"}, []
                cov = t.get("cover", "") if str(t.get("cover", "")).startswith("http") else ""
                w._quick_download(res["url"], playlist=target, play=play, cb=row._on_state,
                                  meta={"title": t.get("title", ""), "artist": artist,
                                        "album": t.get("album") or res.get("album") or "",
                                        "thumb_url": res.get("thumb_url") or cov,
                                        "duration": t.get("duration") or 0, "alts": alts})
            w._ui_bridge.call.emit(go)
        _threading.Thread(target=work, daemon=True).start()

    def _download_album(self, a, card):
        """Релиз с сервера → альбом на YouTube Music → все треки в плейлист «Название»."""
        if getattr(card, "_busy", False):
            return
        card._busy = True
        old_sub = card.subtitle
        card.subtitle = "ищу на YouTube Music…"
        card.update()
        w = self.shell.win
        artist = (self.data or {}).get("name") or self.name

        def work():
            alb = None
            try:
                import online_search
                alb = online_search.album_tracks(artist, a.get("title", ""))
            except Exception as e:                   # noqa: BLE001
                print("[album dl]", e)

            def go():
                try:
                    card.subtitle
                except RuntimeError:
                    return
                card._busy = False
                if not alb or not alb.get("tracks"):
                    card.subtitle = "не найден на YouTube Music"
                    card.update()
                    return
                tr = alb["tracks"]
                name = alb["title"] or a.get("title", "Альбом")
                ans = QMessageBox.question(self, "Скачать альбом",
                                           f"«{name}» — {alb.get('artist', '')}\n{len(tr)} треков.\n\n"
                                           "Скачать в коллекцию?")
                if ans != QMessageBox.StandardButton.Yes:
                    card.subtitle = old_sub
                    card.update()
                    return
                state = {"done": 0, "fail": 0}

                def cb(st, v):
                    if st not in ("done", "error"):
                        return
                    state["done" if st == "done" else "fail"] += 1
                    try:
                        card.subtitle = f"скачано {state['done']}/{len(tr)}" + \
                            (f" · ошибок {state['fail']}" if state["fail"] else "")
                        card.update()
                    except RuntimeError:
                        pass
                card.subtitle = f"скачано 0/{len(tr)}"
                card.update()
                for t in tr:
                    w._quick_download(t["url"], playlist=None, cb=cb,
                                      meta={"title": t.get("title"), "artist": t.get("artist"),
                                            "album": name, "thumb_url": alb.get("thumb_url") or t.get("thumb_url"),
                                            "duration": t.get("duration") or 0})
            w._ui_bridge.call.emit(go)
        _threading.Thread(target=work, daemon=True).start()

    def _play_all(self):
        rows = self.shell._lib_rows(self.local)
        if rows:
            self.shell.play_row(rows[0])

    def _fan_wave(self):
        """Волна из всего, что связано с артистом вкладки."""
        w = self.shell.win
        tracks = list(self.local)
        random.shuffle(tracks)
        if not tracks:
            return
        w.playlists[WAVE_PL] = {"tracks": tracks, "desc": f"auto: {self.name}", "cover": ""}
        w._ya_save_playlists()
        self.shell._wave_kind = ("artist", self.name)
        self.shell._wave_src = list(tracks)                # продолжение волны — тоже только его треки
        self.shell.wave.set_mood(self.name, "artist", self.name)
        w._play_index(0, WAVE_PL)
