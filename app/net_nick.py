"""Стиль ника в Echoes.NET (как «Стили отображаемого имени» в Discord): шрифт, эффект и цвета.

Хранится в settings["ya_profile_deco"]["nick"] = {"font", "fx", "c1", "c2"} и уходит друзьям и в публичную сеть
вместе с остальным оформлением профиля (deco). У каждого латинского шрифта есть кириллическая пара в том же духе:
буквы, которых нет в первом шрифте, Qt берёт из второго (QFont.setFamilies) — русский ник выглядит так же стильно.
Все шрифты — открытые (OFL/Apache, google/fonts), лежат в assets/fonts/nick.
"""
import math
import re
import time
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QFontDatabase, QFontMetricsF, QLinearGradient, QPainter, QPainterPath,
                         QPen)
from PyQt6.QtWidgets import (QColorDialog, QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                             QWidget)

FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts" / "nick"

# ключ, подпись, латинский шрифт, кириллическая пара
FONTS = [
    ("gg", "Обычный", "", ""),
    ("bangers", "Комикс", "Bangers", "Russo One"),
    ("biorhyme", "Брусок", "BioRhyme", "Podkova"),
    ("cherry", "Пузыри", "Cherry Bomb One", "Rubik Bubbles"),
    ("chicle", "Ретро", "Chicle", "Lobster"),
    ("museo", "Модерн", "MuseoModerno", "Unbounded"),
    ("pixel", "8 бит", "Pixelify Sans", "Pixelify Sans"),
    ("zilla", "Темпо", "Zilla Slab", "Kelly Slab"),
    ("fraktur", "Готика", "UnifrakturMaguntia", "Ruslan Display"),
    ("creep", "Хоррор", "Creepster", "Rubik Wet Paint"),
    ("fredoka", "Мармелад", "Fredoka", "Comfortaa"),
    ("type", "Машинка", "Special Elite", "PT Mono"),
]
FONT_KEYS = {k for k, *_ in FONTS}
EFFECTS = [("solid", "Минималистичный"), ("silver", "Серебро"), ("shimmer", "Блик"), ("halo", "Ореол"),
           ("outline", "Контур"), ("chrome", "Хром"),
           ("gradient", "Градиент"), ("neon", "Неон"), ("toon", "Мультфильм"),
           ("pop", "Выделение"), ("gummy", "Гамми"), ("prism", "Призма")]
ANIMATED = ("prism", "neon", "shimmer", "halo", "chrome")      # эффекты, которые двигаются (общий таймер)
FX_KEYS = {k for k, _ in EFFECTS}
COLORS = ["#ffffff", "#ff5c8a", "#ff9f43", "#ffdb1a", "#4cd964", "#38c6ff", "#7c5cff", "#c86bff"]
_HEX = re.compile(r"#[0-9a-fA-F]{6}")
_loaded = False


_pending = None


_FILE_OF = {"PT Mono": "ptm55ft"}                              # у этого шрифта имя файла не похоже на название


def _need(family: str):
    """Подключить только файлы одного шрифта. Каждый подключённый шрифт заставляет Qt заново подобрать шрифты
    всем виджетам окна — двадцать файлов разом давали ~0.3 с паузы при первом открытии профиля. Обычному нику
    («gg») шрифты не нужны вовсе, а нику со стилем — два файла."""
    global _loaded, _pending
    if not family or _loaded:
        return
    if _pending is None:
        _pending = sorted(FONT_DIR.glob("*.ttf"), reverse=True)
    pre = _FILE_OF.get(family, family.replace(" ", "").lower())
    for f in [f for f in _pending if f.name.lower().startswith(pre)]:
        QFontDatabase.addApplicationFont(str(f))
        _pending.remove(f)
    if not _pending:
        _loaded = True


def _load_fonts():
    """Все шрифты ников разом — для окна выбора стиля (там видны все)."""
    global _loaded, _pending
    if _loaded:
        return
    if _pending is None:
        _pending = sorted(FONT_DIR.glob("*.ttf"), reverse=True)
    while _pending:
        QFontDatabase.addApplicationFont(str(_pending.pop()))
    _loaded = True


def clean(spec) -> dict:
    """Чужой стиль из сети — только известные ключи и цвета #rrggbb."""
    if not isinstance(spec, dict):
        return {}
    out = {"font": spec.get("font") if spec.get("font") in FONT_KEYS else "gg",
           "fx": spec.get("fx") if spec.get("fx") in FX_KEYS else "solid"}
    for k, d in (("c1", "#ffffff"), ("c2", "#7c5cff")):
        v = str(spec.get(k) or "")
        out[k] = v if _HEX.fullmatch(v) else d
    if out == {"font": "gg", "fx": "solid", "c1": "#ffffff", "c2": "#7c5cff"}:
        return {}
    return out


def font_for(key, px, weight=QFont.Weight.Black) -> QFont:
    f = QFont()
    fam = next(((a, b) for k, _, a, b in FONTS if k == key), ("", ""))
    _need(fam[0])
    _need(fam[1])
    if fam[0]:
        f.setFamilies([fam[0], fam[1]])
        f.setWeight(QFont.Weight.Normal if key in ("bangers", "chicle", "fraktur", "creep", "type", "cherry")
                    else weight)
    else:
        f.setWeight(weight)
    f.setPixelSize(max(6, int(px)))
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


class _Ticker:
    """Один общий таймер на все анимированные ники (призма, неон) — и только пока они на экране."""
    def __init__(self):
        self.items = set()
        self.t = None

    def add(self, w):
        self.items.add(w)
        if self.t is None:
            self.t = QTimer()
            self.t.setInterval(50)
            self.t.timeout.connect(self._tick)
        if not self.t.isActive():
            self.t.start()

    def remove(self, w):
        self.items.discard(w)
        if not self.items and self.t is not None:
            self.t.stop()

    def _tick(self):
        for w in list(self.items):
            try:
                if w.isVisible() and not w.visibleRegion().isEmpty():
                    w.update()
            except RuntimeError:
                self.items.discard(w)
        if not self.items:
            self.t.stop()


_ticker = _Ticker()


def paint_nick(p: QPainter, rect: QRectF, text: str, spec: dict, px: float, t: float = 0.0,
               align=Qt.AlignmentFlag.AlignLeft):
    """Нарисовать ник в rect (по вертикали — по центру)."""
    spec = spec or {}
    fx = spec.get("fx", "solid")
    c1 = QColor(spec.get("c1") or "#ffffff")
    c2 = QColor(spec.get("c2") or "#7c5cff")
    f = font_for(spec.get("font", "gg"), px)
    fm = QFontMetricsF(f)
    tw = fm.horizontalAdvance(text)
    x = rect.left() + (rect.width() - tw) / 2 if align & Qt.AlignmentFlag.AlignHCenter else rect.left() + 2
    if fx == "pop":
        x += px * 0.25 if not align & Qt.AlignmentFlag.AlignHCenter else 0
    base = rect.center().y() + (fm.ascent() - fm.descent()) / 2
    path = QPainterPath()
    path.addText(QPointF(x, base), f, text)
    br = path.boundingRect()
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    if fx == "solid":
        p.setBrush(c1)
        p.drawPath(path)
    elif fx == "silver":                                       # Phantom: металл — светлый верх, холодный низ
        g = QLinearGradient(br.topLeft(), br.bottomLeft())
        g.setColorAt(0, QColor(255, 255, 255))
        g.setColorAt(.55, QColor(196, 200, 210))
        g.setColorAt(1, QColor(240, 242, 248))
        p.setBrush(QColor(0, 0, 0, 90))
        p.drawPath(path.translated(0, max(1.0, px * .04)))
        p.setBrush(g)
        p.drawPath(path)
    elif fx == "shimmer":                                      # Phantom: по нику пробегает световой блик
        p.setBrush(QColor(c1))
        p.drawPath(path)
        span = br.width() * .35
        x0 = br.left() - span + ((t * .45) % 1.6) / 1.6 * (br.width() + 2 * span)
        g = QLinearGradient(QPointF(x0, br.top()), QPointF(x0 + span, br.bottom()))
        g.setColorAt(0, QColor(255, 255, 255, 0))
        g.setColorAt(.5, QColor(255, 255, 255, 230))
        g.setColorAt(1, QColor(255, 255, 255, 0))
        p.setClipPath(path)
        p.setBrush(g)
        p.drawRect(br.adjusted(-span, 0, span, 0))
    elif fx == "halo":                                         # Phantom: мягкий белый ореол дышит
        k = .6 + .4 * math.sin(t * 1.8)
        for w_, a in ((px * .34, 18), (px * .18, 34)):
            c = QColor(c1)
            c.setAlpha(int(a * k))
            p.strokePath(path, QPen(c, w_, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(QColor(c1))
        p.drawPath(path)
    elif fx == "outline":                                      # Phantom: тонкий контур, внутри стекло
        c = QColor(c1)
        c.setAlpha(40)
        p.setBrush(c)
        p.drawPath(path)
        p.strokePath(path, QPen(QColor(c1), max(1.0, px * .045), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                                Qt.PenJoinStyle.RoundJoin))
    elif fx == "chrome":                                       # Phantom: хром — полосы отражения медленно едут
        g = QLinearGradient(br.topLeft(), br.bottomRight())
        sh = (t * .12) % 1.0
        for i, v in enumerate((250, 150, 255, 120, 235, 170, 250)):
            g.setColorAt((i / 6 + sh) % 1.0 if i not in (0, 6) else i / 6, QColor(v, v, min(255, v + 8)))
        p.setBrush(g)
        p.drawPath(path)
    elif fx == "gradient":
        g = QLinearGradient(br.topLeft(), br.topRight())
        g.setColorAt(0, c1)
        g.setColorAt(1, c2)
        p.setBrush(g)
        p.drawPath(path)
    elif fx == "neon":
        pulse = 0.75 + 0.25 * math.sin(t * 2.4)
        for w_, a in ((px * 0.42, 26), (px * 0.26, 46), (px * 0.13, 90)):
            c = QColor(c1)
            c.setAlpha(int(a * pulse))
            p.strokePath(path, QPen(c, w_, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                                    Qt.PenJoinStyle.RoundJoin))
        p.setBrush(QColor(c1).lighter(170))
        p.drawPath(path)
    elif fx == "toon":
        off = max(1.5, px * 0.07)
        dark = QColor(c2).darker(260)
        p.setBrush(dark)
        p.drawPath(path.translated(off, off))
        p.strokePath(path, QPen(dark, max(2.0, px * 0.12), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                                Qt.PenJoinStyle.RoundJoin))
        g = QLinearGradient(br.topLeft(), br.bottomLeft())
        g.setColorAt(0, QColor(c1).lighter(125))
        g.setColorAt(1, c1)
        p.setBrush(g)
        p.drawPath(path)
    elif fx == "pop":
        hl = QColor(c2)
        hl.setAlpha(110)
        pad = px * 0.22
        r = QRectF(br.left() - pad, br.top() - pad * 0.6, br.width() + pad * 2, br.height() + pad * 1.2)
        p.setBrush(hl)
        p.drawRoundedRect(r, pad * 1.4, pad * 1.4)
        p.setBrush(c1)
        p.drawPath(path)
    elif fx == "gummy":
        p.strokePath(path, QPen(QColor(c1).darker(190), max(1.5, px * 0.09), Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        g = QLinearGradient(br.topLeft(), br.bottomLeft())
        g.setColorAt(0, QColor(c1).lighter(160))
        g.setColorAt(0.5, c1)
        g.setColorAt(1, QColor(c1).darker(140))
        p.setBrush(g)
        p.drawPath(path)
        p.setClipPath(path)                                   # глянцевый блик сверху, как у мармелада
        gl = QLinearGradient(br.topLeft(), QPointF(br.left(), br.top() + br.height() * 0.55))
        gl.setColorAt(0, QColor(255, 255, 255, 170))
        gl.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(gl)
        p.drawRect(QRectF(br.left(), br.top(), br.width(), br.height() * 0.5))
    else:                                                     # prism — переливается радугой
        g = QLinearGradient(br.topLeft(), br.topRight())
        sh = (t * 0.18) % 1.0
        for i in range(7):
            pos = i / 6
            g.setColorAt(pos, QColor.fromHsvF((pos * 0.85 + sh) % 1.0, 0.62, 1.0))
        p.strokePath(path, QPen(QColor(255, 255, 255, 60), max(1.0, px * 0.06)))
        p.setBrush(g)
        p.drawPath(path)
    p.restore()
    return br


class NickLabel(QWidget):
    """Ник со стилем. Без стиля рисуется обычным жирным шрифтом приложения."""
    def __init__(self, text, spec=None, px=13, parent=None, center=False):
        super().__init__(parent)
        self.text = str(text or "")
        self.spec = clean(spec)
        self.px = px
        self.center = center
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._fit()
        self.setToolTip(self.text)

    def set_style(self, spec):
        self.spec = clean(spec)
        self._fit()
        self.update()

    def set_text(self, text):
        self.text = str(text or "")
        self._fit()
        self.update()

    def _anim(self):
        return self.spec.get("fx") in ANIMATED

    def _fit(self):
        fm = QFontMetricsF(font_for(self.spec.get("font", "gg"), self.px))
        extra = self.px * (0.9 if self.spec.get("fx") in ("neon", "pop", "toon") else 0.3)
        self._w = int(fm.horizontalAdvance(self.text) + extra + 4)
        self.setMinimumHeight(int(fm.height() + extra))
        self.updateGeometry()
        if self._anim():
            _ticker.add(self)
        else:
            _ticker.remove(self)

    def sizeHint(self):
        return QSize(self._w, self.minimumHeight())

    def minimumSizeHint(self):
        return QSize(min(self._w, int(self.px * 4)), self.minimumHeight())

    def paintEvent(self, _):
        p = QPainter(self)
        spec = self.spec or {"fx": "solid", "c1": self.palette().windowText().color().name()}
        al = Qt.AlignmentFlag.AlignHCenter if self.center else Qt.AlignmentFlag.AlignLeft
        pad = self.px * 0.45 if spec.get("fx") in ("neon", "pop", "toon") else 0
        paint_nick(p, QRectF(self.rect()).adjusted(pad, 0, 0, 0), self.text, spec, self.px, time.monotonic(), al)
        p.end()

    def hideEvent(self, e):
        _ticker.remove(self)
        super().hideEvent(e)

    def showEvent(self, e):
        if self._anim():
            _ticker.add(self)
        super().showEvent(e)


def swap(label: QLabel, text, spec, px) -> QWidget:
    """Заменить обычный QLabel ника на стильный (если стиль задан)."""
    spec = clean(spec)
    if not spec or label is None:
        return label
    lay = label.parentWidget().layout() if label.parentWidget() else None
    nl = NickLabel(text, spec, px)
    nl.setObjectName(label.objectName())
    if lay is not None:
        idx = _index_in(lay, label)
        if idx is not None:
            idx[0].insertWidget(idx[1], nl)
            label.hide()
            return nl
    return label


def _index_in(lay, w):
    for i in range(lay.count()):
        it = lay.itemAt(i)
        if it.widget() is w:
            return lay, i
        if it.layout() is not None:
            r = _index_in(it.layout(), w)
            if r:
                return r
    return None


# ── редактор (как на скриншоте Discord: шрифт · эффект · цвет) ──

class _Tile(QPushButton):
    def __init__(self, paint, tip, w=72, h=60):
        super().__init__()
        self._paint = paint
        self.setCheckable(True)
        self.setFixedSize(w, h)
        self.setToolTip(tip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        p.setPen(QPen(QColor("#ffdb1a") if self.isChecked() else QColor(255, 255, 255, 40 if not self.underMouse()
                                                                          else 90), 2 if self.isChecked() else 1))
        p.setBrush(QColor(255, 255, 255, 18 if self.isChecked() else 8))
        p.drawRoundedRect(r, 12, 12)
        self._paint(p, r)
        p.end()


class NickStyleDialog(QDialog):
    changed = pyqtSignal(dict)

    def __init__(self, name, spec, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Стиль ника")
        self.setModal(True)
        self.name = name or "Echoes"
        self.spec = clean(spec) or {"font": "gg", "fx": "solid", "c1": "#ffffff", "c2": "#7c5cff"}
        self.setStyleSheet("QDialog{background:#141416;} QLabel{color:#e8e8e8;background:transparent;}"
                           "QLabel#H{font-size:14px;font-weight:800;} QLabel#S{color:#8a8a8a;font-size:11px;}"
                           "QPushButton#Sw{border-radius:15px;border:2px solid rgba(255,255,255,0.15);}"
                           "QPushButton#Sw:checked{border:3px solid #ffffff;}"
                           "QPushButton#Act{background:#ffdb1a;color:#000;border:none;border-radius:10px;"
                           "padding:9px 22px;font-weight:800;}"
                           "QPushButton#Ghost{background:rgba(255,255,255,0.08);color:#fff;border:none;"
                           "border-radius:10px;padding:9px 18px;font-weight:700;}")
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(10)
        self.preview = NickLabel(self.name, self.spec, 34, center=True)
        self.preview.setMinimumHeight(70)
        box = QWidget()
        box.setStyleSheet("background:rgba(255,255,255,0.04);border-radius:14px;")
        bl = QVBoxLayout(box)
        bl.addWidget(self.preview)
        v.addWidget(box)
        v.addWidget(self._h("Выбор шрифта", "у каждого шрифта есть пара для кириллицы — русский ник тоже красивый"))
        g = QGridLayout(); g.setSpacing(8)
        self.font_tiles = {}
        for i, (k, title, *_r) in enumerate(FONTS):
            t = _Tile(lambda p, r, k=k: self._paint_font(p, r, k), title)
            t.clicked.connect(lambda _=False, k=k: self._set("font", k))
            g.addWidget(t, i // 6, i % 6)
            self.font_tiles[k] = t
        v.addLayout(g)
        v.addWidget(self._h("Выбор эффекта"))
        g2 = QGridLayout(); g2.setSpacing(8)
        self.fx_tiles = {}
        for i, (k, title) in enumerate(EFFECTS):
            t = _Tile(lambda p, r, k=k: self._paint_fx(p, r, k), title, 116, 56)
            t.clicked.connect(lambda _=False, k=k: self._set("fx", k))
            g2.addWidget(t, i // 4, i % 4)
            self.fx_tiles[k] = t
        v.addLayout(g2)
        v.addWidget(self._h("Выбор цвета", "второй цвет — для градиента, тени «Мультфильма» и подсветки «Выделения»"))
        self.sw1, self.sw2 = self._swatches("c1"), self._swatches("c2")
        v.addLayout(self.sw1[0])
        v.addLayout(self.sw2[0])
        row = QHBoxLayout()
        reset = QPushButton("Сбросить"); reset.setObjectName("Ghost")
        reset.clicked.connect(self._reset)
        row.addWidget(reset)
        row.addStretch(1)
        cancel = QPushButton("Отмена"); cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Сохранить"); ok.setObjectName("Act")
        ok.clicked.connect(self.accept)
        row.addWidget(cancel); row.addWidget(ok)
        v.addSpacing(6)
        v.addLayout(row)
        self._sync()
        self._t = QTimer(self)
        self._t.timeout.connect(lambda: [t.update() for k, t in self.fx_tiles.items() if k in ANIMATED])
        self._t.start(60)

    def _h(self, title, sub=""):
        w = QWidget()
        l = QHBoxLayout(w); l.setContentsMargins(0, 6, 0, 0); l.setSpacing(10)
        h = QLabel(title); h.setObjectName("H")
        l.addWidget(h)
        if sub:
            s = QLabel(sub); s.setObjectName("S")
            l.addWidget(s)
        l.addStretch(1)
        return w

    def _swatches(self, key):
        row = QHBoxLayout(); row.setSpacing(8)
        lab = QLabel("Основной" if key == "c1" else "Второй"); lab.setObjectName("S"); lab.setFixedWidth(64)
        row.addWidget(lab)
        pick = QPushButton("＋"); pick.setFixedSize(30, 30); pick.setToolTip("Свой цвет…")
        pick.setStyleSheet("QPushButton{border-radius:15px;background:qconicalgradient(cx:0.5,cy:0.5,angle:0,"
                           "stop:0 #ff4d4d,stop:0.33 #4dff88,stop:0.66 #4d7cff,stop:1 #ff4d4d);color:#fff;"
                           "font-weight:900;border:none;}")
        pick.clicked.connect(lambda: self._pick(key))
        row.addWidget(pick)
        btns = []
        for c in COLORS:
            b = QPushButton(); b.setObjectName("Sw"); b.setCheckable(True); b.setFixedSize(30, 30)
            b.setStyleSheet(f"QPushButton#Sw{{background:{c};}}")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, c=c: self._set(key, c))
            row.addWidget(b)
            btns.append((c, b))
        row.addStretch(1)
        return row, btns

    def _pick(self, key):
        c = QColorDialog.getColor(QColor(self.spec.get(key)), self, "Цвет ника")
        if c.isValid():
            self._set(key, c.name())

    def _set(self, key, val):
        self.spec[key] = val
        self._sync()

    def _reset(self):
        self.spec = {"font": "gg", "fx": "solid", "c1": "#ffffff", "c2": "#7c5cff"}
        self._sync()

    def _sync(self):
        self.preview.set_style(self.spec)
        for k, t in self.font_tiles.items():
            t.setChecked(k == self.spec["font"])
            t.update()
        for k, t in self.fx_tiles.items():
            t.setChecked(k == self.spec["fx"])
            t.update()
        for key, (_row, btns) in (("c1", self.sw1), ("c2", self.sw2)):
            for c, b in btns:
                b.setChecked(c.lower() == str(self.spec.get(key)).lower())
        self.changed.emit(dict(self.spec))

    def _paint_font(self, p, r, k):
        spec = dict(self.spec, font=k, fx="solid", c1="#ffffff")
        paint_nick(p, r.adjusted(0, -6, 0, -6), "Gg", spec, 22, 0, Qt.AlignmentFlag.AlignHCenter)
        ry = QRectF(r.left(), r.bottom() - 18, r.width(), 14)
        spec["c1"] = "#9a9a9a"
        paint_nick(p, ry, "Яя", spec, 11, 0, Qt.AlignmentFlag.AlignHCenter)

    def _paint_fx(self, p, r, k):
        spec = dict(self.spec, fx=k)
        paint_nick(p, r.adjusted(0, -8, 0, -8), "Aa", spec, 20, time.monotonic(), Qt.AlignmentFlag.AlignHCenter)
        f = QFont(); f.setPixelSize(10); f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor("#9a9a9a"))
        p.drawText(r.adjusted(0, 0, 0, -4), int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom),
                   dict(EFFECTS)[k])

    def result(self) -> dict:
        return clean(self.spec)
