# scene_mode.py
"""
«Сцена» — режим просмотра песни во всё окно оболочки Echoes Music (пункт «Сцена» в «⋯» нижнего плеера).

Сеттинг — как у экрана плеера на планшете: сверху часы с датой и «островок» с названием трека и столбиками
звука, слева крупный текст и две карточки-виджета под ним, справа обложка, название, время, кнопки и
громкость; фон — светлый, из цветов обложки. От трека зависят цвета, то, что летает в воздухе (искры, снег,
дождь, угли, пузыри — по словам песни), картинка и резкость движений (scene_look; там же выключенный по
умолчанию режим разных шрифтов, раскладок и тёмных сцен).

Режиссёр распознаёт образы в тексте и строит звуковую карту трека (scene_director). Под строкой
появляются тематические карточки и измеренные характеристики, а на словах и ударах меняется анимация.
На месте обложки может играть подобранная или выбранная пользователем гифка (scene_art).

Как сделано, чтобы не тормозило и не ело память:
  * фон, рамка и картинка готовятся в фоновом потоке (только QImage), окно получает готовое; поиск гифки и
    вырезание фона — тоже там, сначала показывается обложка, потом она сменяется;
  * фон считается в четверть размера и хранится одной картинкой в размер экрана (≈8 МБ при 1920×1080);
  * гифка играет через QMovie без кэша кадров и уже уменьшенной до размера на экране; на паузе стоит;
  * раскладка слов, подложки карточек и значки-эмодзи кэшируются (малые словари, чистятся при смене трека);
  * один виджет, без дочерних; кадры идут через общие часы (frameclock) не чаще ~55 раз в секунду, а на паузе,
    когда ничего не движется, — 10 раз в секунду и только если что-то изменилось;
  * через полминуты после закрытия все картинки и гифка отпускаются.
"""
from __future__ import annotations

import bisect
import math
import random
import threading
import time
from pathlib import Path

from frameclock import FrameTimer
from PyQt6.QtCore import QObject, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QFontDatabase, QFontMetricsF, QImage, QImageReader, QMovie, QPainter,
                         QPainterPath, QPen, QPixmap, QPolygonF, QRadialGradient)
from PyQt6.QtWidgets import QWidget

import scene_cards
import scene_director
import scene_look
import scene_motion

_ARGB = QImage.Format.Format_ARGB32_Premultiplied
NOTE_S = 4.4                                                   # сколько висит «уведомление»
SPARKS = 30
# шрифты разного «роста» при одном кегле — выравниваем, чтобы строка занимала примерно одно место
FONT_SCALE = {"Caveat": 1.32, "Neucha": 1.1, "Bad Script": 1.0, "Segoe Script": 0.88, "Segoe Print": 0.9,
              "Bebas Neue": 1.28, "Oswald": 1.1, "Impact": 1.1, "Unbounded": 0.84, "Rubik Mono One": 0.78,
              "Bungee": 0.84, "Cormorant Garamond": 1.22, "Russo One": 0.94, "Comfortaa": 0.94}
_FAMS: set | None = None


def _ease(t: float) -> float:
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return t * t * (3.0 - 2.0 * t)


def _back(t: float) -> float:
    """0 → 1 с небольшим перелётом (наклейка «шлёпается»)."""
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    c = 1.9
    return 1.0 + (c + 1.0) * (t - 1.0) ** 3 + c * (t - 1.0) ** 2


def _fmt(sec: float) -> str:
    s = max(0, int(sec))
    return f"{s // 60}:{s % 60:02d}"


def _hsl(h, s, l_) -> QColor:
    return QColor.fromHslF(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, l_)))


def _alpha(c: QColor, a: int) -> QColor:
    c = QColor(c)
    c.setAlpha(max(0, min(255, int(a))))
    return c


def _cover_colors(src):
    if src is not None and not src.isNull():
        try:
            from echo_glass import _dominant_colors
        except ImportError:
            from blur_fx import to_array
            from fluid_core import dominant_rgb
            rgb, _ = dominant_rgb(to_array(src.scaled(48, 48))[:, :, 2::-1])
            return [QColor(*map(int, rgb))]
        return list(_dominant_colors(src))
    return [QColor("#8f8cf0")]


def _art_glow(color, side):
    n = max(16, side)
    img = QImage(n, n, _ARGB)
    img.fill(Qt.GlobalColor.transparent)
    gradient = QRadialGradient(QPointF(n / 2, n / 2), n / 2)
    gradient.setColorAt(0, _alpha(color, 155))
    gradient.setColorAt(.52, _alpha(color, 80))
    gradient.setColorAt(1, _alpha(color, 0))
    painter = QPainter(img)
    painter.fillRect(img.rect(), gradient)
    painter.end()
    return img


def pick_family(candidates: list, cyr: bool) -> str:
    """Первый из шрифтов, который есть в системе (и знает кириллицу, если она нужна). "" — шрифт оболочки."""
    global _FAMS
    if _FAMS is None:
        _FAMS = set(QFontDatabase.families())
    for fam in candidates:
        if not fam:
            return ""
        if fam in _FAMS:
            if cyr:
                try:
                    if QFontDatabase.WritingSystem.Cyrillic not in QFontDatabase.writingSystems(fam):
                        continue
                except Exception:                              # noqa: BLE001
                    continue
            return fam
    return ""


def palette(cols: list, dark: bool = False) -> dict:
    """Палитра сцены из главных цветов обложки: фон, пятна, акцент (ключевые слова), чернила, бумага."""
    best, h, s = -1.0, 0.69, 0.30                              # нет цветных — спокойный сиреневый
    for k, c in enumerate(cols):                               # самый насыщенный из главных цветов обложки;
        hh, ss, ll, _a = QColor(c).getHslF()                   # белый, чёрный и серый фон обложки не в счёт
        if hh < 0 or ss < 0.18 or not 0.12 < ll < 0.92:
            continue
        score = ss * (1.0 - abs(ll - 0.5)) * (1.0 - 0.12 * k)
        if score > best:
            best, h, s = score, hh, ss
    s = max(0.35, min(0.95, s))
    extra = []
    for c in cols[1:3]:                                        # второй-третий цвет обложки — тоже пятнами
        hh, ss, _ll, _aa = QColor(c).getHslF()
        if hh >= 0 and ss >= 0.15:
            extra.append((hh, min(0.9, ss)))
    if dark:
        blobs = [_hsl(h, s * 0.9, 0.30), _hsl(h + 0.06, s * 0.8, 0.22), _hsl(h - 0.07, s * 0.7, 0.18)]
        blobs += [_hsl(hh, ss, 0.26) for hh, ss in extra]
        return {"dark": True, "base": _hsl(h, s * 0.55, 0.075), "blobs": blobs,
                "accent": _hsl(h, max(0.7, s), 0.66), "ink": _hsl(h, 0.25, 0.95),
                "glow": _hsl(h, max(0.8, s), 0.6), "paper": _hsl(h, 0.28, 0.16), "on_accent": _hsl(h, 0.45, 0.07)}
    blobs = [_hsl(h, s * 0.9, 0.80), _hsl(h + 0.06, s * 0.8, 0.84), _hsl(h - 0.07, s * 0.7, 0.88)]
    blobs += [_hsl(hh, ss, 0.84) for hh, ss in extra]
    return {"dark": False, "base": _hsl(h, s * 0.55, 0.91), "blobs": blobs, "accent": _hsl(h, max(0.55, s), 0.46),
            "ink": _hsl(h, 0.30, 0.13), "glow": _hsl(h, max(0.7, s), 0.58), "paper": _hsl(h, 0.40, 0.975),
            "on_accent": QColor(255, 255, 255)}


def build_bg(src: QImage | None, w: int, h: int, pal: dict, pattern: str = "blobs",
             center: tuple = (0.8, 0.4)) -> QImage:
    """Фон w×h: цвета обложки мягкими пятнами, сама обложка, размытая до неузнаваемости, и узор трека.
    center — где стоит обложка (доли ширины и высоты): от неё расходятся кольца, к ней тянется главное пятно."""
    w, h = max(8, int(w)), max(8, int(h))
    lw, lh = max(16, w // 4), max(16, h // 4)
    dark = pal["dark"]
    img = QImage(lw, lh, _ARGB)
    img.fill(pal["base"])
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    rnd = random.Random(sum(c.rgb() for c in pal["blobs"]) & 0xFFFFFF)
    spots = [(center[0], center[1], 0.62), (1.0 - center[0], 0.88, 0.55), (0.5, 0.04, 0.45)]
    for i, c in enumerate(pal["blobs"]):
        cx, cy, r = spots[i] if i < len(spots) else (rnd.random(), rnd.random(), rnd.uniform(0.3, 0.5))
        g = QRadialGradient(QPointF(cx * lw, cy * lh), r * max(lw, lh))
        g.setColorAt(0, _alpha(c, 235 if i == 0 else 170))
        g.setColorAt(1, _alpha(c, 0))
        p.fillRect(img.rect(), g)
    if src is not None and not src.isNull():
        try:
            import blur_fx
            cov = blur_fx.blurred_cover(src, lw, lh, max(lw, lh) / 9.0, sat=1.25)
            p.setOpacity(0.26 if dark else 0.20)
            p.drawImage(0, 0, cov)
            p.setOpacity(1.0)
        except Exception as e:                                 # noqa: BLE001
            print("[scene] blur:", e)
    tx = 0.78 if center[0] < 0.5 else 0.22                     # поле под текстом — с другой стороны от обложки
    g = QRadialGradient(QPointF(lw * tx, lh * 0.30), max(lw, lh) * 0.62)
    g.setColorAt(0, QColor(0, 0, 0, 120) if dark else QColor(255, 255, 255, 150))
    g.setColorAt(1, QColor(0, 0, 0, 0) if dark else QColor(255, 255, 255, 0))
    p.fillRect(img.rect(), g)
    p.end()
    out = img.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    try:
        import blur_fx
        out = blur_fx.from_array(blur_fx.to_array(out), dither=True)
    except Exception:                                          # noqa: BLE001
        pass
    out = out.convertToFormat(QImage.Format.Format_RGB32)
    if pattern != "blobs":                                     # узор — поверх, в полном размере: линии остаются чёткими
        p = QPainter(out)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ink, acc = pal["ink"], pal["blobs"][0]
        u = max(0.6, h / 720.0)
        if pattern == "bands":
            p.translate(w / 2, h / 2)
            p.rotate(-24)
            p.setPen(Qt.PenStyle.NoPen)
            step = max(60.0, w * 0.15)
            k = -8
            while k * step < w:
                p.setBrush(_alpha(acc, 46 if k % 2 else 26))
                p.drawRect(QRectF(k * step, -h * 1.5, step * (0.42 if k % 2 else 0.16), h * 3))
                k += 1
        elif pattern == "rings":
            c = QPointF(center[0] * w, center[1] * h)
            p.setBrush(Qt.BrushStyle.NoBrush)
            step = max(40.0, w * 0.062)
            for k in range(1, 26):
                p.setPen(QPen(_alpha(acc if k % 3 == 0 else ink, 58 if k % 3 == 0 else (24 if dark else 15)),
                              (2.4 if k % 3 == 0 else 1.2) * u))
                p.drawEllipse(c, k * step, k * step)
        elif pattern == "grid":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_alpha(ink, 34 if dark else 26))
            step = 26.0 * u
            r = 1.5 * u
            y = step / 2
            row = 0
            while y < h:
                x = step / 2 + (step / 2 if row % 2 else 0)
                while x < w:
                    p.drawEllipse(QPointF(x, y), r, r)
                    x += step
                y += step
                row += 1
        p.end()
    return out


# ── рамка обложки ─────────────────────────────────────────────────────── #

def content_rect(side: float, frame: str) -> QRectF:
    """Где внутри квадрата side×side стоит сама картинка."""
    if frame == "polaroid":
        pad = side * 0.05
        return QRectF(pad, pad, side - 2 * pad, side * 0.80 - pad)
    return QRectF(0, 0, side, side)


def frame_path(r: QRectF, frame: str) -> QPainterPath:
    path = QPainterPath()
    if frame == "circle":
        path.addEllipse(r)
    elif frame == "cut":
        k = r.width() * 0.13
        path.addPolygon(QPolygonF([QPointF(r.left() + k, r.top()), QPointF(r.right(), r.top()),
                                   QPointF(r.right(), r.bottom() - k), QPointF(r.right() - k, r.bottom()),
                                   QPointF(r.left(), r.bottom()), QPointF(r.left(), r.top() + k)]))
        path.closeSubpath()
    elif frame == "polaroid":
        path.addRoundedRect(r, r.width() * 0.012, r.width() * 0.012)
    else:
        path.addRoundedRect(r, r.width() * 0.075, r.width() * 0.075)
    return path


def under_image(side: int, frame: str, dpr: float, pal: dict) -> tuple:
    """То, что лежит под картинкой: тень, бумага полароида, пятно под ногами персонажа. → (картинка, поле)."""
    side = max(8, int(side))
    m = int(side * 0.16) + 8
    n = int(round((side + 2 * m) * dpr))
    out = QImage(n, n, _ARGB)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(dpr, dpr)
    p.translate(m, m)
    p.setPen(Qt.PenStyle.NoPen)
    box = QRectF(0, 0, side, side)
    if frame == "free":                                        # персонаж без рамки — мягкое пятно под ногами
        g = QRadialGradient(QPointF(side / 2, 0), side * 0.36)
        g.setColorAt(0, QColor(0, 0, 0, 150 if pal["dark"] else 90))
        g.setColorAt(1, QColor(0, 0, 0, 0))
        p.save()
        p.translate(0, side * 0.985)
        p.scale(1.0, 0.16)
        p.fillRect(QRectF(0, -side, side, 2 * side), g)
        p.restore()
        p.end()
        return out, m
    steps = 14
    rad = side * (0.5 if frame == "circle" else 0.075 if frame == "round" else 0.02)
    for i in range(steps, 0, -1):                              # тень: много слабых слоёв — без ступенек
        k = i / steps
        grow = m * 0.72 * k
        sh = QPainterPath()
        sh.addRoundedRect(box.adjusted(-grow * 0.75, -grow * 0.35 + m * 0.16, grow * 0.75, grow + m * 0.16),
                          rad + grow, rad + grow)
        p.fillPath(sh, QColor(0, 0, 0, int(5 + 13 * (1 - k))))
    if frame == "polaroid":
        p.setBrush(QColor(252, 251, 247))
        p.drawRoundedRect(box, side * 0.02, side * 0.02)
    p.end()
    return out, m


class _Bus(QObject):
    done = pyqtSignal(int, object)
    sound = pyqtSignal(int, object)
    gif = pyqtSignal(object, str)


class SceneMode(QWidget):
    """Оверлей поверх оболочки (YaShell). open() / close_mode() / is_open()."""

    closed = pyqtSignal()
    TIPS = {"back": "Свернуть (Esc)", "like": "Мне нравится", "shuffle": "Перемешать", "prev": "Предыдущий",
            "play": "Играть / пауза", "next": "Следующий", "repeat": "Повтор",
            "art": "Правый клик — своя гифка или картинка", "lyr": "Текст песни", "queue": "Очередь",
            "vol": "Громкость"}
    ART_NET = True                 # можно ли ходить в сеть за гифкой (в тестах выключается)

    def __init__(self, shell):
        super().__init__(shell)
        self.shell = shell
        self.win = shell.win
        self.setObjectName("YaScene")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._op = self._op_to = 0.0
        self._key = None               # путь трека, для которого готовы картинки
        self._track_key = None         # путь трека, под который посчитаны раскладка и подписи
        self._title = self._artist = ""
        self._tag = ""                 # «Lossless», «MP3»… — по файлу трека
        self._mini: QPixmap | None = None
        self._bg: QPixmap | None = None
        self._bg_old: QPixmap | None = None
        self._bg_t = 1.0
        self._under: QPixmap | None = None
        self._under_m = 0
        self._art: QPixmap | None = None
        self._movie: QMovie | None = None
        self._frame = "round"
        self._art_info: dict = {}
        self._glow: QPixmap | None = None
        self._pal = palette([])
        self._look = scene_look.make()
        self._take = 0
        self._track_since = 0.0
        self._sound = None
        self._sound_started = self._sound_busy = False
        self._gif_busy = False
        self._gif_attempt = None
        self._theme = self._motif = self._old_motif = ""
        self._motif_mix = 1.0
        self._drive = self._bass = self._last_level = 0.0
        self._last_read = self._last_position = 0.0
        self._sound_cards = []
        self._live = []
        self._waveform = None
        self._wave_duration = 0.
        self._family = ""
        self._size = None
        self._job = 0
        self._pending = None
        self._g: dict = {}
        self._hover = self._down = None
        self._drag = False
        self._pos = self._dur = 0.0
        self._playing = False
        self._scale = 1.0
        self._lvl = 0.0
        self._flash = 0.0              # вспышка за обложкой на ключевом слове
        self._flash_word = None
        self._phase = 0.0
        self._sig = None
        self._paint_sig = None
        # текст
        self._ly_src = None
        self._ly_n = -1
        self._ms: list = []
        self._tx: list = []
        self._src_i: list = []
        self._plain = ()
        self._scene: list = []
        self._li = self._li_from = -1
        self._li_t = 1.0
        self._lay_cache: dict = {}
        self._emoji: dict = {}
        self._card_bg = None
        self._note = None
        self._note_at = 0.0
        self._free_at = 0.0
        self._last = time.monotonic()
        self._sparks = [(random.random(), random.random(), random.uniform(0.6, 1.6), random.random() * 6.28,
                         random.uniform(0.02, 0.06)) for _ in range(SPARKS)]
        self._bus = _Bus(self)
        self._bus.done.connect(self._on_assets)
        self._bus.sound.connect(self._on_sound)
        self._bus.gif.connect(self._on_auto_gif)
        self._timer = FrameTimer(self)
        self._timer.setInterval(18)
        self._timer.timeout.connect(self._tick)
        self._layout()
        self.hide()

    # ── открыть / закрыть ─────────────────────────────────────────────── #

    def is_open(self) -> bool:
        return self.isVisible() and self._op_to > 0.0

    @staticmethod
    def _motion() -> float:
        try:
            import motion
            return float(motion.strength())
        except Exception:                                      # noqa: BLE001
            return 1.0

    def open(self):
        p = self.parentWidget()
        if p is not None:
            self.setGeometry(p.rect())
        self._free_at = 0.0
        self._op_to = 1.0
        if self._motion() <= 0:
            self._op = 1.0
        self._last = time.monotonic()
        self._sync_track(force=True)
        self._timer.setInterval(18)
        self.show()
        self.raise_()
        self.setFocus()
        self._timer.start()
        self.update()

    def close_mode(self, instant=False):
        if not self.isVisible():
            return
        self._op_to = 0.0
        self._timer.setInterval(18)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        if instant or self._motion() <= 0:
            self._op = 0.0
            self._finish_close()

    def _finish_close(self):
        self._timer.stop()
        self.hide()
        if self._movie is not None:
            self._movie.setPaused(True)
        self._hover = self._down = None
        self._drag = False
        self._bg_old = None
        self._free_at = time.monotonic() + 30.0
        QTimer.singleShot(31000, self._free_assets)
        try:
            self.shell.setFocus()
        except RuntimeError:
            pass
        self.closed.emit()

    def _drop_movie(self):
        m, self._movie = self._movie, None
        if m is not None:
            m.stop()
            m.setFileName("")
            m.deleteLater()

    def _free_assets(self):
        if not self.isVisible() and self._free_at and time.monotonic() >= self._free_at:
            self._bg = self._bg_old = self._under = self._art = self._glow = self._card_bg = self._mini = None
            self._drop_movie()
            self._key = self._size = None
            self._emoji.clear()
            self._lay_cache.clear()
            self._free_at = 0.0

    # ── данные ────────────────────────────────────────────────────────── #

    def _profile(self, t) -> dict | None:
        try:
            prof = getattr(self.win, "_intel_profiles", None) or {}
            return prof.get(str((t or {}).get("path", "")))
        except Exception:                                      # noqa: BLE001
            return None

    def _scene_key(self) -> str:
        return scene_cards.scene_key(self._artist, self._title)

    def _sync_track(self, force=False):
        t = self.shell.current_track()
        key = str(t.get("path", "")) if t else ""
        size = (self.width(), self.height())
        if not force and key == self._key and size == self._size:
            return
        if key != self._track_key:
            if t:
                from yamusic_theme import sanitize_title
                self._title = sanitize_title(t.get("title", "") or "Без названия")
                self._artist = t.get("artist") or "Неизвестный исполнитель"
            else:
                self._title, self._artist = "Ничего не играет", ""
            ext = Path(key).suffix.lower().lstrip(".") if key and "://" not in key else ""
            self._tag = ("Lossless" if ext in ("flac", "wav", "aiff", "aif", "alac", "ape", "wv")
                         else ext.upper() if ext in ("mp3", "m4a", "aac", "ogg", "opus", "wma") else "")
            self._track_key = key
            self._take += 1
            self._track_since = time.monotonic()
            self._sound = None
            self._sound_started = False
            self._theme = self._motif = self._old_motif = ""
            self._motif_mix = 1.0
            self._drive = self._bass = self._lvl = self._last_level = self._flash = 0.0
            self._last_position = 0.0
            self._live.clear()
            self._waveform = None
            self._drop_movie()
            self._art = self._under = self._mini = None
            self._art_info = {}
            self._look = scene_look.make(self._profile(t))
            self._ly_src, self._ms, self._tx, self._src_i, self._scene = None, [], [], [], []   # текст — нового трека
            self._ly_n, self._plain = -1, ()
            self._li = self._li_from = -1
            self._li_t = 1.0
            self._emoji.clear()
            self._note = None
            self._layout()
            self._replan()
        self._request(t, key, size)

    def _analyse(self, now):
        key = self._track_key
        if not key or not self._op_to or now - self._track_since < .22:
            return
        if not self._sound_started and not self._sound_busy:
            take, duration, bus = self._take, self._dur, self._bus
            self._sound_started = self._sound_busy = True

            def work():
                sound = None
                try:
                    sound = scene_director.analyse_file(key, duration)
                except Exception as exc:
                    print("[scene] sound:", exc)
                try:
                    bus.sound.emit(take, sound)
                except RuntimeError:
                    pass

            threading.Thread(target=work, name="echoes-scene-analysis", daemon=True).start()
        self._fetch_gif(now)

    def _on_sound(self, take, sound):
        self._sound_busy = False
        if take != self._take or sound is None or not self._op_to:
            if take == self._take and sound is not None:
                self._sound_started = False
            return
        self._sound = sound
        self._waveform = None
        self._replan()
        self._refresh_assets()

    def _fetch_gif(self, now):
        if (not self.ART_NET or self._gif_busy or not self._op_to
                or now - self._track_since < (1.2 if self._tx else 4.5)):
            return
        import scene_art
        gif = scene_art.gif_settings(self.win)
        identity = (self._take, self._theme)
        if not gif[0] or identity == self._gif_attempt:
            return
        skey, artist, title, bus = self._scene_key(), self._artist, self._title, self._bus
        self._gif_busy, self._gif_attempt = True, identity

        def work():
            path = ""
            try:
                path = scene_art.fetch_auto(skey, artist, title, gif, identity[1])
            except Exception as exc:
                print("[scene] gif search:", type(exc).__name__)
            try:
                bus.gif.emit(identity, path)
            except RuntimeError:
                pass

        threading.Thread(target=work, name="echoes-scene-gif", daemon=True).start()

    def _on_auto_gif(self, identity, path):
        self._gif_busy = False
        if path and identity == (self._take, self._theme) and self._op_to:
            self._refresh_assets()

    def _refresh_assets(self):
        self._key = self._pending = None
        self._sync_track()

    def _request(self, t, key, size):
        W, H = size
        if W < 8 or H < 8 or self._pending == (key, size):
            return
        self._pending = (key, size)
        self._job += 1
        job = self._job
        cover = str((t or {}).get("cover", "") or "")
        try:
            if cover and not Path(cover).is_file():
                cover = ""
        except OSError:
            cover = ""
        side = int(self._g["cover"].width())
        dpr = float(self.devicePixelRatioF())
        ph = None
        if not cover:                                          # нет обложки — заглушка плеера
            from yamusic_theme import cover_pixmap
            ph = cover_pixmap("", 256, 0, seed=key or "x").toImage()
        prof = dict(self._profile(t) or {})
        if self._sound:
            prof.update(self._sound.profile)
        theme = self._theme
        skey = self._scene_key()
        center = (self._g["cover"].center().x() / max(1.0, W), self._g["cover"].center().y() / max(1.0, H))
        import scene_art
        gif = scene_art.gif_settings(self.win) if self.ART_NET else ("", "")
        bus = self._bus

        def assemble(info):
            res = {"key": key, "size": size, "info": info}
            from img_load import read_image
            path = info["path"]
            src = None
            if path and info["animated"]:
                rd = QImageReader(path)                        # Qt не прыгает по кадрам гифки — читаем подряд
                fr = rd.read()
                src = fr if not fr.isNull() else None
            elif path:
                src = read_image(path, 1200)
                src = src if not src.isNull() else None
            col_src = src if src is not None else ph
            if info["source"] == "gif" and cover:
                cover_image = read_image(cover, 640)
                if not cover_image.isNull():
                    col_src = cover_image
            cols = _cover_colors(col_src)
            if theme in scene_director.MOTIFS:
                cols.append(QColor(scene_director.MOTIFS[theme].color))
            lum = 0.5
            if col_src is not None:
                sm = col_src.scaled(12, 12, Qt.AspectRatioMode.IgnoreAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)
                lum = sum(sm.pixelColor(x, y).lightnessF() for y in range(12) for x in range(12)) / 144.0
            look = scene_look.make(prof, lum, theme)
            pal = palette(cols, look["dark"])
            frame = look["frame"]
            movie, img = None, None
            if info["animated"] and path:
                cut = scene_art.animated_cutout(path) if info["cut"] else ""
                movie = cut or path
                if cut or (info["cut"] and src is not None and src.hasAlphaChannel()
                           and src.pixelColor(0, 0).alpha() < 40):
                    frame = "free"
            if movie is None or src is not None:
                rgba = scene_art.static_cutout(path) if (info["cut"] and path and movie is None) else None
                if rgba is not None:
                    hh, ww = rgba.shape[:2]
                    img = QImage(rgba.tobytes(), ww, hh, ww * 4, QImage.Format.Format_RGBA8888).copy()
                    img = img.scaled(int(side * dpr), int(side * dpr), Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
                    frame = "free"
                else:
                    base = src if src is not None else ph
                    cr = content_rect(side, frame)
                    tw, th = max(1, int(cr.width() * dpr)), max(1, int(cr.height() * dpr))
                    if base is not None:
                        img = base.scaled(tw, th, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                          Qt.TransformationMode.SmoothTransformation)
                        img = img.copy((img.width() - tw) // 2, (img.height() - th) // 2, tw, th)
            res.update(look=look, pal=pal, frame=frame, movie=movie, art=img)
            if col_src is not None:
                mini = col_src.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                      Qt.TransformationMode.SmoothTransformation)
                res["mini"] = mini.copy((mini.width() - 48) // 2, (mini.height() - 48) // 2, 48, 48)
            res["bg"] = build_bg(col_src, W, H, pal, look["pattern"], center)
            res["under"], res["under_m"] = under_image(side, frame, dpr, pal)
            res["glow"] = _art_glow(pal["glow"], int(side * 1.7))
            return res

        def work():
            try:
                info = scene_art.resolve(skey, cover, gif, theme)
                res = assemble(info)
            except Exception as e:                             # noqa: BLE001
                print("[scene] assets:", e)
                res = {"key": key, "size": size}
            try:
                bus.done.emit(job, res)
            except RuntimeError:
                return
        threading.Thread(target=work, name="echoes-scene", daemon=True).start()

    def _on_assets(self, job, res):
        if job == -1:                                          # гифка из поиска скачана — она теперь картинка трека
            import scene_art
            if res.get("path") and res.get("skey") == self._scene_key():
                self._art_changed(lambda: scene_art.set_user_art(res["skey"], res["path"]))
            return
        if job != self._job:
            return
        self._pending = None
        self._key, self._size = res["key"], res["size"]
        if "bg" not in res:
            self.update()
            return
        if self._bg is not None and self._motion() > 0 and self._op >= 1.0:
            self._bg_old, self._bg_t = self._bg, 0.0           # фон перетекает в новый
        dpr = float(self.devicePixelRatioF())
        self._bg = QPixmap.fromImage(res["bg"])
        under = QPixmap.fromImage(res["under"])
        under.setDevicePixelRatio(dpr)
        self._under, self._under_m = under, res["under_m"]
        self._glow = QPixmap.fromImage(res["glow"])
        self._mini = QPixmap.fromImage(res["mini"]) if res.get("mini") is not None else None
        self._pal, self._frame, self._art_info = res["pal"], res["frame"], res["info"]
        self._look = res["look"]
        self._drop_movie()
        self._art = None
        if res["movie"]:
            mv = QMovie(res["movie"], parent=self)
            mv.setCacheMode(QMovie.CacheMode.CacheNone)
            if mv.isValid() and mv.jumpToFrame(0):
                sz = mv.currentImage().size()
                side = self._g["cover"].width()
                cr = content_rect(side, self._frame)
                if self._frame == "free":
                    k = side * dpr / max(1, max(sz.width(), sz.height()))
                else:                                          # в рамке — заполнить её целиком
                    k = max(cr.width() * dpr / max(1, sz.width()), cr.height() * dpr / max(1, sz.height()))
                if k < 1.0:                                    # крупную гифку уменьшаем сразу при чтении кадра
                    mv.setScaledSize(QSize(max(1, int(sz.width() * k)), max(1, int(sz.height() * k))))
                mv.start()
                mv.setPaused(not self.shell.is_playing())
                self._movie = mv
            else:
                mv.deleteLater()
        if self._movie is None and res["art"] is not None:
            self._art = QPixmap.fromImage(res["art"])
        self._card_bg = None
        self._paint_sig = None
        self._pick_font()
        self.update()

    def _pick_font(self):
        sample = self._tx[:6] or [self._title]
        cyr = any("а" <= ch.lower() <= "я" or ch.lower() == "ё" for t in sample for ch in t)
        fam = pick_family(self._look.get("fonts") or [""], cyr)
        if fam != self._family:
            self._family = fam
            self._lay_cache.clear()

    def _lyrics(self):
        """Строки синхронного текста и сцена к ним; пересчёт — только когда текст сменился."""
        lv = getattr(self.win, "lyrics_view", None)
        lines = getattr(lv, "_lines", None) or []
        timed = bool(getattr(lv, "_has_timings", False))
        signature = (len(lines), timed)
        if (lines is self._ly_src or not lines and self._ly_src is None) and signature == self._ly_n:
            return
        self._ly_src, self._ly_n = (lines or None), signature
        ms, tx, si = [], [], []
        plain = []
        for k, ln in enumerate(lines):
            if not isinstance(ln, dict):
                continue
            m = ln.get("ms", -1)
            s = " ".join(str(ln.get("text") or "").split())
            if not s:
                continue
            if timed and m is not None and m >= 0:
                ms.append(float(m))
                tx.append(s)
                si.append(k)
            elif not timed:
                plain.append(s)
        self._ms, self._tx, self._src_i = ms, tx, si
        # A single untimed line is also how the lyrics pane communicates loading/errors.
        self._plain = tuple(plain) if len(plain) >= 2 else ()
        self._replan()
        self._li = self._li_from = -1
        self._li_t = 1.0
        self._lay_cache.clear()
        self._pick_font()

    def _replan(self):
        tx, ms = self._tx, self._ms
        scene, theme = scene_director.plan(tx, ms, self._title, self._sound, self._plain)
        try:
            scene = scene_cards.apply_overrides(scene, tx, scene_cards.scene_path(self._artist, self._title))
        except (OSError, ValueError) as e:
            print("[scene] cards:", e)
        old_theme = self._theme
        self._scene = scene
        self._theme = theme
        self._sound_cards = []
        if self._sound and self._sound.bpm:
            from i18n import LANG
            en = LANG == "en"
            self._sound_cards.append(scene_director.stat("Tempo" if en else "Темп", "♫", self._sound.bpm,
                                                        "BPM · estimated" if en else "BPM · оценка темпа"))
        if theme != old_theme and (self._pending is not None or self._key is not None):
            self._refresh_assets()
        self.update()

    def _audio_frame(self, now, dt, pms, playing):
        seconds = pms / 1000
        jump = abs(seconds - self._last_position) > max(.32, dt * 5)
        if jump:
            self._flash = self._drive = self._last_level = 0.0
            self._note = None
            self._live.clear()
        self._last_position = seconds
        metrics = self._sound.sample(seconds) if self._sound else None
        if metrics is not None:
            self._lvl, self._bass = metrics
            self._drive = self._sound.hit(seconds)
        elif playing and now - self._last_read >= .043:
            self._last_read = now
            engine = getattr(self.win, "engine", None)
            read = getattr(engine, "get_visual_samples", None)
            samples = read(2048) if read else None
            if samples is not None:
                lvl, bass = scene_director.live_level(samples, engine.visual_sample_rate)
            else:
                read_level = getattr(engine, "get_level", None)
                lvl = bass = min(1.0, float(read_level() or 0) * 3.1) if read_level else 0.0
            attack = max(0.0, .65 * bass + .35 * lvl - self._last_level - .035)
            self._lvl += (lvl - self._lvl) * .47
            self._bass += (bass - self._bass) * .52
            self._drive = max(self._drive * .80, min(1., attack * 4))
            self._last_level = .65 * bass + .35 * lvl
            self._live.append(self._lvl)
            del self._live[:-64]

    def _word_spans(self, i, n_words):
        """[(начало, конец) в мс] по словам строки i — из меток LRC или оценки/звука (word_sync); иначе None."""
        lv = getattr(self.win, "lyrics_view", None)
        k = self._src_i[i]
        wt = None
        for name in ("_words", "_est"):
            arr = getattr(lv, name, None)
            if arr and k < len(arr) and arr[k] and len(arr[k]) == n_words:
                wt = arr[k]
                break
        if not wt:
            return None
        end = self._line_end(i)
        out = []
        for j, ent in enumerate(wt):
            a = float(ent[0])
            b = float(ent[2]) if len(ent) > 2 else (float(wt[j + 1][0]) if j + 1 < len(wt) else end)
            out.append((a, max(a + 60.0, b)))
        return out

    def _line_end(self, i) -> float:
        start = self._ms[i]
        nxt = self._ms[i + 1] if i + 1 < len(self._ms) else start + 5000.0
        return max(start + 400.0, min(nxt - 80.0, start + 9000.0))

    def _pms(self) -> float:
        f = float(getattr(getattr(self.win, "engine", None), "preset_factor", 1.0) or 1.0)
        return self._pos * 1000.0 * f

    # ── кадр ──────────────────────────────────────────────────────────── #

    def _tick(self):
        now = time.monotonic()
        dt = min(0.1, now - self._last)
        self._last = now
        ms = self._motion()
        moving = False
        if self._op != self._op_to:
            step = dt / 0.26
            self._op = min(1.0, self._op + step) if self._op_to > self._op else max(0.0, self._op - step)
            if self._op <= 0.0 and self._op_to <= 0.0:
                self._finish_close()
                return
            if self._op >= 1.0:
                self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
            moving = True
        self._sync_track()
        w = self.win
        try:
            eng = w.engine
            pos = float((eng.get_position_smooth() if hasattr(eng, "get_position_smooth")
                         else eng.get_position()) or 0)
            dur = float(eng.duration or 0)
        except Exception:                                      # noqa: BLE001
            pos, dur = 0.0, 0.0
        if not self._drag:
            self._pos, self._dur = pos, dur
        playing = self.shell.is_playing()
        self._playing = playing
        if self._movie is not None and (self._movie.state() == QMovie.MovieState.Paused) == playing:
            self._movie.setPaused(not playing)                 # на паузе гифка стоит — и кадры не нужны
        t = self.shell.current_track()
        sig = (bool(t and self.shell.is_liked(t)), bool(getattr(w, "shuffle", False)),
               int(getattr(w, "repeat_mode", 0) or 0), playing, self._hover, self._down)
        if sig != self._sig:
            self._sig = sig
            moving = True
        # строка текста
        self._lyrics()
        pms = self._pms()
        self._analyse(now)
        self._audio_frame(now, dt, pms, playing and ms > 0)
        li = bisect.bisect_right(self._ms, pms + 60.0) - 1 if self._ms else -1
        if li != self._li:
            jump = abs(li - self._li) != 1
            self._li_from, self._li, self._li_t = self._li, li, (0.0 if ms > 0 else 1.0)
            self._flash_word = None
            if jump:
                self._li_t = max(self._li_t, 0.55)             # перемотка — почти без езды
            note = self._scene[li]["note"] if 0 <= li < len(self._scene) else None
            if note is not None and playing and not jump and abs(self._ms[li] - pms) < 280:
                self._note, self._note_at = note, pms / 1000
            moving = True
        if self._li_t < 1.0:
            self._li_t = min(1.0, self._li_t + dt / max(0.2, float(self._look.get("speed", 0.42))))
            moving = True
        if self._bg_t < 1.0:
            self._bg_t = min(1.0, self._bg_t + dt / 0.5)
            if self._bg_t >= 1.0:
                self._bg_old = None
            moving = True
        if self._note is not None:
            if pms / 1000 - self._note_at > NOTE_S:
                self._note = None
        motif = self._theme
        if 0 <= li < len(self._scene):
            cue = self._scene[li]
            motif = cue["motif"]
            words = self._tx[li].split(" ")
            spans = self._word_spans(li, len(words))
            if spans is None:
                # Line-timed LRC still gives each visual a stable cue within the line.
                start, end = self._ms[li], self._line_end(li)
                stride = (end - start) / len(words)
                spans = [(start + i * stride, start + (i + 1) * stride) for i in range(len(words))]
            for k in cue["keys"]:
                if k < len(spans) and pms >= spans[k][0]:
                    motif = cue["motifs"].get(k, motif)
                    if playing and ms > 0 and pms < spans[k][0] + 140 and self._flash_word != k:
                        self._flash_word, self._flash = k, 1.0
        if motif != self._motif:
            self._old_motif, self._motif, self._motif_mix = self._motif, motif, (0.0 if ms > 0 else 1.0)
            moving = True
        if self._motif_mix < 1:
            self._motif_mix = min(1., self._motif_mix + dt / .38)
            moving = True
        if self._flash > 0.0:
            self._flash = max(0.0, self._flash - dt / 0.7)
            moving = True
        target = 1.0 if playing else 0.94
        if abs(self._scale - target) > 0.001:
            self._scale += (target - self._scale) * min(1.0, dt * 9.0)
            moving = True
        self._phase = pms / 1000 if ms > 0 else 0.
        if playing or moving:
            self._timer.setInterval(18)
            self.update()
        else:                                                  # пауза и тишина — редкие проверки, кадр только по делу
            self._timer.setInterval(100)
            psig = (int(self._pos), self._li, self._key, self._size, time.localtime().tm_min)
            if psig != self._paint_sig:
                self._paint_sig = psig
                self.update()

    # ── раскладка ─────────────────────────────────────────────────────── #

    def _place_info(self, g, x, y, w, u):
        """Название, исполнитель, полоска времени и кнопки — блоком шириной w от точки (x, y)."""
        g["title"] = QRectF(x, y, w - 40 * u, 34 * u)
        g["like"] = QRectF(x + w - 36 * u, y - 2 * u, 36 * u, 36 * u)
        g["artist"] = QRectF(x, y + 34 * u, w, 22 * u)
        g["prog"] = QRectF(x, y + 72 * u, w, 18 * u)
        g["times"] = QRectF(x, y + 90 * u, w, 18 * u)
        bs = 40 * u
        names = ("shuffle", "prev", "play", "next", "repeat")
        for k, name in enumerate(names):
            g[name] = QRectF(x + (w - bs) * k / (len(names) - 1), y + 118 * u, bs, bs)
        vy = y + 172 * u                                       # громкость и два значка: текст, очередь
        g["vol_lo"] = QRectF(x, vy - 4 * u, 18 * u, 26 * u)
        g["vol"] = QRectF(x + 24 * u, vy, w - 24 * u - 26 * u - 62 * u, 18 * u)
        g["vol_hi"] = QRectF(g["vol"].right() + 6 * u, vy - 4 * u, 20 * u, 26 * u)
        g["lyr"] = QRectF(x + w - 56 * u, vy - 5 * u, 28 * u, 28 * u)
        g["queue"] = QRectF(x + w - 26 * u, vy - 5 * u, 28 * u, 28 * u)

    def _layout(self):
        W, H = float(max(8, self.width())), float(max(8, self.height()))
        m = max(24.0, W * 0.044)
        u = max(0.6, min(1.6, H / 720.0))
        layout = self._look.get("layout", "split")
        sy = max(16.0, H * 0.032)                              # строка состояния: часы слева, островок по центру
        g = {"u": u, "m": m, "status_y": sy}
        top = max(56.0, H * 0.10)
        gap = 14 * u
        side = iw = cards_x = cw = mb = 0.0
        if layout == "banner":
            side = max(110.0, min(H * 0.30, W * 0.20))
            mb = max(28.0, H * 0.07)
            iw = max(200 * u, W * 0.21)
            cards_x = m + side + 26 * u + iw + 34 * u
            cw = (W - m - cards_x - gap) / 2
            if cw < 150 * u:
                layout = "split"                               # узко — карточкам не хватит места
        if layout == "banner":
            g["cover"] = QRectF(m, H - mb - side, side, side)
            self._place_info(g, m + side + 26 * u, g["cover"].center().y() - 79 * u, iw, u)
            ch = min(side, max(96.0, H * 0.245))
            g["card0"] = QRectF(cards_x, g["cover"].bottom() - ch, cw, ch)
            g["card1"] = QRectF(cards_x + cw + gap, g["cover"].bottom() - ch, cw, ch)
            g["lyrics"] = QRectF(m, top, W - 2 * m, g["cover"].top() - top - 34 * u)
            g["font"] = max(18.0, min(84.0, H * 0.070))
            g["back"] = QRectF(W - m - 104 * u, sy - 17, 34, 34)
        else:
            side = max(120.0, min(W * 0.29, H * 0.54))
            cy = max(64.0, H * 0.115)
            mirror = layout == "mirror"
            cx = m if mirror else W - m - side
            g["cover"] = QRectF(cx, cy, side, side)
            self._place_info(g, cx, cy + side + 22 * u, side, u)
            colgap = max(28.0, W * 0.04)
            lx = m + side + colgap if mirror else m
            lw = W - 2 * m - side - colgap
            ch = max(96.0, H * 0.245)
            cards_y = H - max(28.0, H * 0.075) - ch
            g["lyrics"] = QRectF(lx, top, lw, cards_y - top - 24 * u)
            cw = (lw - gap) / 2
            g["card0"] = QRectF(lx, cards_y, cw, ch)
            g["card1"] = QRectF(lx + cw + gap, cards_y, cw, ch)
            g["font"] = max(17.0, min(72.0, H * 0.058))
            g["back"] = QRectF(W - m - 104 * u, sy - 17, 34, 34)
        lr = g["lyrics"]
        nw = min(lr.width() * 0.62, 420 * u)
        g["note"] = QRectF(lr.right() - nw, sy + 20 * u, nw, 74 * u)
        g["layout"] = layout
        g["back"].moveRight(W - m)
        self._g = g
        self._lay_cache.clear()
        self._card_bg = None

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._layout()
        self._paint_sig = None

    # ── мышь и клавиши ────────────────────────────────────────────────── #

    def _hit(self, pos):
        g = self._g
        for name in ("back", "like", "shuffle", "prev", "play", "next", "repeat", "lyr", "queue"):
            if g[name].contains(pos):
                return name
        if g["prog"].adjusted(-6, -10, 6, 10).contains(pos):
            return "prog"
        if g["vol"].adjusted(-6, -8, 6, 8).contains(pos):
            return "vol"
        if g["cover"].contains(pos):
            return "art"
        return None

    def _seek_at(self, x, commit):
        r = self._g["prog"]
        frac = max(0.0, min(1.0, (x - r.left()) / max(1.0, r.width())))
        if self._dur > 0:
            self._pos = frac * self._dur
        if commit:
            self.shell._seek_frac(frac)
        self.update()

    def _vol_at(self, x):
        r = self._g["vol"]
        try:
            self.win.vol.setValue(int(round(max(0.0, min(1.0, (x - r.left()) / max(1.0, r.width()))) * 100)))
        except Exception as e:                                 # noqa: BLE001
            print("[scene] volume:", e)
        self.update()

    def mouseMoveEvent(self, e):
        pos = QPointF(e.position())
        if self._drag:
            if self._drag == "vol":
                self._vol_at(pos.x())
            else:
                self._seek_at(pos.x(), False)
            return
        h = self._hit(pos)
        if h != self._hover:
            self._hover = h
            self.setCursor(Qt.CursorShape.PointingHandCursor if h and h != "art" else Qt.CursorShape.ArrowCursor)
            self.setToolTip(self.TIPS.get(h, ""))
            self.update()

    def leaveEvent(self, e):
        if self._hover is not None:
            self._hover = None
            self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            e.accept()
            return
        pos = QPointF(e.position())
        self._down = self._hit(pos)
        if self._down == "prog":
            self._drag = "prog"
            self._seek_at(pos.x(), False)
        elif self._down == "vol":
            self._drag = "vol"
            self._vol_at(pos.x())
        self.update()

    def mouseReleaseEvent(self, e):
        pos = QPointF(e.position())
        down, self._down = self._down, None
        if self._drag:
            drag, self._drag = self._drag, False
            if drag == "prog":
                self._seek_at(pos.x(), True)
        elif down is not None and down == self._hit(pos):
            self.activate(down)
        self.update()

    def wheelEvent(self, e):
        e.accept()

    def contextMenuEvent(self, e):
        e.accept()
        if self._g["cover"].contains(QPointF(e.pos())):
            self.art_menu().exec(e.globalPos())

    def art_menu(self):
        """Меню картинки: своя гифка, вернуть как было, вырезать фон или нет, искать ли гифку."""
        import scene_art
        from PyQt6.QtWidgets import QMenu
        key = self._scene_key()
        st = scene_art.load_store()
        info = self._art_info or {}
        m = QMenu(self)
        m.addAction("Своя гифка или картинка…", self._choose_art)
        if scene_art.gif_settings(self.win)[0]:
            m.addAction("Выбрать гифку из поиска…", self._search_art)
        if key in st["user"]:
            m.addAction("Убрать свою картинку", lambda: self._art_changed(lambda: scene_art.set_user_art(key, None)))
        if info.get("source", "cover") == "cover":            # обложку режем только по просьбе
            cut_on = key in st["cut"]
            m.addAction("Вернуть обложку целиком" if cut_on else "Вырезать персонажа с обложки",
                        lambda: self._art_changed(lambda: scene_art.set_flag(key, "cut", not cut_on)))
        else:
            cut_off = key in st["nocut"]
            m.addAction("Вырезать фон у картинки" if cut_off else "Не вырезать фон",
                        lambda: self._art_changed(lambda: scene_art.set_flag(key, "nocut", not cut_off)))
        if scene_art.gif_settings(self.win)[0]:
            gif_off = key in st["nogif"]
            m.addAction("Искать гифку для этого трека" if gif_off else "Не искать гифку для этого трека",
                        lambda: self._art_changed(lambda: scene_art.set_flag(key, "nogif", not gif_off)))
            if info.get("source") == "gif":
                m.addAction("Найти гифку заново", lambda: self._art_changed(lambda: scene_art.clear_auto(key)))
        return m

    def _choose_art(self):
        import scene_art
        from PyQt6.QtWidgets import QFileDialog
        path, _f = QFileDialog.getOpenFileName(self, "Гифка или картинка для этого трека", "",
                                               "Картинки и гифки (*.gif *.webp *.png *.jpg *.jpeg)")
        if path:
            self._art_changed(lambda: scene_art.set_user_art(self._scene_key(), path))

    def _search_art(self):
        """Окно поиска гифок Echoes.NET (на своём ключе), в строке поиска — название трека."""
        import net_gif
        import scene_art
        node = getattr(self.win, "_net_node", None)
        if node is None:
            return
        skey, bus = self._scene_key(), self._bus

        def picked(g):
            url = (g or {}).get("url")

            def work():
                path = scene_art.download_gif(url)
                try:
                    bus.done.emit(-1, {"path": path, "skey": skey})
                except RuntimeError:
                    pass
            threading.Thread(target=work, name="echoes-scene-gif", daemon=True).start()
        dlg = net_gif.GifPicker(self, node.settings, picked, "", save_cb=getattr(node, "save_settings", None))
        box = getattr(dlg, "q", None) or getattr(dlg, "search", None)
        if box is not None and hasattr(box, "setText"):
            box.setText(f"{self._artist} {self._title}".strip())
        dlg.exec()

    def _art_changed(self, change):
        try:
            change()
        except OSError as e:
            print("[scene] art store:", e)
        self._gif_attempt = None
        self._refresh_assets()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close_mode()
            e.accept()
            return
        super().keyPressEvent(e)

    def activate(self, what):
        sh, w = self.shell, self.win
        if what == "back":
            self.close_mode()
        elif what == "like":
            t = sh.current_track()
            if t:
                sh.toggle_like(t)
        elif what == "shuffle":
            w.btn_shuffle.click()
        elif what == "repeat":
            w._cycle_repeat()
        elif what == "prev":
            w.prev_track()
        elif what == "next":
            w.next_track()
        elif what == "play":
            w.toggle_play()
        elif what == "lyr":                                    # текст песни целиком — на экране «Сейчас играет»
            if hasattr(sh, "open_now_playing"):
                sh.open_now_playing(mode="lyrics")
            else:
                self.close_mode(instant=True)
                sh.toggle_lyrics()
        elif what == "queue":
            self.close_mode(instant=True)
            if getattr(sh, "_cur_page", "") != "queue":
                sh.show_page("queue")

    # ── рисование ─────────────────────────────────────────────────────── #

    def _font(self, px, weight=QFont.Weight.Bold, lyric=False) -> QFont:
        from yamusic_theme import ya_font
        px = max(8, int(round(px)))
        if lyric and self._family:
            f = QFont(self._family)
            f.setPixelSize(max(8, int(round(px * FONT_SCALE.get(self._family, 1.0)))))
            f.setWeight(weight)
            return f
        return ya_font(px, weight)

    def _line_layout(self, i):
        """Слова строки i по рядам: ([(номер слова, слово, x, y_верх_ряда, ширина)], высота, высота ряда)."""
        lay = self._lay_cache.get(i)
        if lay is not None:
            return lay
        g = self._g
        fm = QFontMetricsF(self._font(g["font"], lyric=True))
        width = g["lyrics"].width()
        space = fm.horizontalAdvance(" ")
        row_h = fm.height() * 1.06
        caps = bool(self._look.get("caps"))
        x = y = 0.0
        words = []
        for k, wd in enumerate(self._tx[i].split(" ")):
            if caps:
                wd = wd.upper()
            ww = fm.horizontalAdvance(wd)
            if x > 0 and x + ww > width:
                x, y = 0.0, y + row_h
            words.append((k, wd, x, y, ww))
            x += ww + space
        lay = (words, y + row_h, row_h)
        if len(self._lay_cache) > 24:
            self._lay_cache.clear()
        self._lay_cache[i] = lay
        return lay

    def _slots(self, i) -> dict:
        """Где стоят строки, когда текущая — i: {номер: (y, непрозрачность)}."""
        g = self._g
        area = g["lyrics"]
        gap = g["font"] * 0.62
        out = {}
        if not (0 <= i < len(self._tx)):
            return out
        h_i = self._line_layout(i)[1]
        y = area.top() + min(area.height() * 0.30, max(0.0, area.height() - h_i) * 0.5)
        out[i] = (y, 1.0)
        yy = y
        for k in (i - 1, i - 2):
            if k < 0:
                break
            yy -= self._line_layout(k)[1] + gap
            out[k] = (yy, 0.30 if k == i - 1 else 0.0)
        yy = y + h_i + gap
        for k in (i + 1, i + 2):
            if k >= len(self._tx):
                break
            out[k] = (yy, 0.34 if k == i + 1 else 0.0)
            yy += self._line_layout(k)[1] + gap
        return out

    def _mark(self, p, mark, x, y, w, row_h, fr, a, em):
        """Отметка ключевого слова (маркер, подчёркивание, плашка) — рисуется под буквами."""
        acc = self._pal["accent"]
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(acc)
        if mark == "marker":
            r = QRectF(x - em * 0.10, y + row_h * 0.34, (w + em * 0.20), row_h * 0.52)
            p.setOpacity(a * 0.16)
            p.drawRoundedRect(r, em * 0.10, em * 0.10)
            if fr > 0:
                p.setOpacity(a * (0.62 if self._pal["dark"] else 0.46))
                p.drawRoundedRect(QRectF(r.left(), r.top(), r.width() * fr, r.height()), em * 0.10, em * 0.10)
        elif mark == "underline":
            th = max(2.0, em * 0.085)
            ly = y + row_h * 0.90
            p.setOpacity(a * 0.24)
            p.drawRoundedRect(QRectF(x, ly, w, th), th / 2, th / 2)
            if fr > 0:
                p.setOpacity(a)
                p.drawRoundedRect(QRectF(x, ly, max(th, w * fr), th), th / 2, th / 2)
        elif mark == "box" and fr > 0:
            k = min(1.0, fr * 6.0)                             # плашка «выстреливает» с первым слогом
            r = QRectF(x - em * 0.12, y + row_h * 0.10, w + em * 0.24, row_h * 0.84)
            c = r.center()
            p.setOpacity(a * k)
            p.drawRoundedRect(QRectF(c.x() - r.width() / 2 * (0.9 + 0.1 * k), r.top(),
                                     r.width() * (0.9 + 0.1 * k), r.height()), em * 0.08, em * 0.08)

    def _paint_lyrics(self, p, op):
        g, pal = self._g, self._pal
        area = g["lyrics"]
        ink, acc = pal["ink"], pal["accent"]
        if not self._tx or self._li < 0:
            self._paint_sound(p, op, area)
            return
        t = _ease(self._li_t)
        a_sl = self._slots(self._li_from) if (t < 1.0 and self._li_from >= 0) else None
        b_sl = self._slots(self._li)
        font = self._font(g["font"], lyric=True)
        p.setFont(font)
        fm = QFontMetricsF(font)
        asc = fm.ascent()
        em = float(font.pixelSize())
        mark = self._look.get("mark", "color")
        pms = self._pms()
        p.save()
        p.setClipRect(area.adjusted(-em * 0.3, -em * 0.4, em * 0.3, 8))
        for k in sorted(set(b_sl) | set(a_sl or ())):
            yb, ab = b_sl.get(k, (None, 0.0))
            if a_sl is not None:
                ya, aa = a_sl.get(k, (None, 0.0))
                if ya is None:
                    ya = yb + g["font"] * 1.6
                if yb is None:
                    yb = ya - g["font"] * 1.6
                y, a = ya + (yb - ya) * t, aa + (ab - aa) * t
            else:
                y, a = yb, ab
            if a <= 0.01 or y is None:
                continue
            words, _h, row_h = self._line_layout(k)
            cur = k == self._li
            keys = self._scene[k]["keys"] if k < len(self._scene) else []
            spans = self._word_spans(k, len(words)) if cur else None
            l0, l1 = self._ms[k], self._line_end(k)
            for wi, wd, x, wy, ww in words:
                px_, py_ = area.left() + x, y + wy + asc
                key = wi in keys
                coloured = key and mark in ("color", "box")
                col = acc if coloured else ink
                if not cur:
                    if key and mark in ("marker", "underline"):
                        self._mark(p, mark, px_, y + wy, ww, row_h, 0.0, op * a, em)
                    p.setPen(col)
                    if k < self._li:                           # спетая строка расплывается: шесть слабых копий вокруг
                        d = em * 0.04
                        p.setOpacity(op * a * 0.36)
                        for dx, dy in ((-d, 0), (d, 0), (0, -d), (0, d), (-d * 0.7, d * 0.7), (d * 0.7, -d * 0.7)):
                            p.drawText(QPointF(px_ + dx, py_ + dy), wd)
                        continue
                    p.setOpacity(op * a)
                    p.drawText(QPointF(px_, py_), wd)
                    continue
                if spans is not None:
                    s0, s1 = spans[wi]
                else:                                          # нет пословных меток — ровно по длине строки
                    n = max(1, len(words))
                    s0, s1 = l0 + (l1 - l0) * wi / n, l0 + (l1 - l0) * (wi + 1) / n
                fr = 0.0 if pms <= s0 else 1.0 if pms >= s1 else (pms - s0) / (s1 - s0)
                dim = 0.36 + 0.64 * (1.0 - a)                  # пока строка въезжает — как соседняя
                if key and mark != "color":
                    self._mark(p, mark, px_, y + wy, ww, row_h, fr, op * a, em)
                    if mark == "box" and fr > 0:               # на плашке — буквы цветом фона, сразу целиком
                        p.setOpacity(op * a)
                        p.setPen(pal["on_accent"])
                        p.drawText(QPointF(px_, py_), wd)
                        continue
                if fr < 1.0:
                    p.setOpacity(op * a * (0.46 if coloured else dim))
                    p.setPen(col)
                    p.drawText(QPointF(px_, py_), wd)
                if fr > 0.0:
                    p.setOpacity(op * a)
                    p.setPen(col)
                    if fr < 1.0:
                        p.save()
                        p.setClipRect(QRectF(px_ - 1, y + wy - 2, ww * fr + 1, row_h + 4),
                                      Qt.ClipOperation.IntersectClip)
                        p.drawText(QPointF(px_, py_), wd)
                        p.restore()
                    else:
                        p.drawText(QPointF(px_, py_), wd)
        p.restore()

    def _emoji_pm(self, ch: str, px: int) -> QPixmap:
        key = (ch, px)
        pm = self._emoji.get(key)
        if pm is None:
            dpr = float(self.devicePixelRatioF())
            n = int(px * 1.5 * dpr)
            pm = QPixmap(n, n)
            pm.fill(Qt.GlobalColor.transparent)
            pm.setDevicePixelRatio(dpr)
            q = QPainter(pm)
            ff = QFont("Segoe UI Emoji")
            ff.setPixelSize(px)
            q.setFont(ff)
            q.drawText(QRectF(0, 0, px * 1.5, px * 1.5), int(Qt.AlignmentFlag.AlignCenter), ch)
            q.end()
            if len(self._emoji) > 48:
                self._emoji.clear()
            self._emoji[key] = pm
        return pm

    def _card_colors(self) -> tuple:
        """(цвет текста, цвет полоски, цвет дорожки полоски) для вида карточек трека."""
        pal = self._pal
        if self._look.get("card") == "sticker":
            fg = pal["on_accent"]
            return fg, fg, _alpha(fg, 60)
        return pal["ink"], pal["accent"], _alpha(pal["ink"], 30)

    def _card_back(self) -> QPixmap:
        """Подложка карточки в стиле трека — одна картинка на обе карточки."""
        pm = self._card_bg
        if pm is not None:
            return pm
        r = self._g["card0"]
        u = self._g["u"]
        pal = self._pal
        dark = pal["dark"]
        style = self._look.get("card", "glass")
        mrg = int(18 * u)
        dpr = float(self.devicePixelRatioF())
        pm = QPixmap(int((r.width() + 2 * mrg) * dpr), int((r.height() + 2 * mrg) * dpr))
        pm.fill(Qt.GlobalColor.transparent)
        pm.setDevicePixelRatio(dpr)
        q = QPainter(pm)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        q.setPen(Qt.PenStyle.NoPen)
        box = QRectF(mrg, mrg, r.width(), r.height())
        if style == "sticker":                                 # наклейка: цвет трека, светлый кант, жёсткая тень
            rad = 18 * u
            q.setBrush(QColor(0, 0, 0, 130 if dark else 70))
            q.drawRoundedRect(box.translated(5 * u, 6 * u), rad, rad)
            q.setBrush(pal["ink"] if dark else QColor(255, 255, 255))
            q.drawRoundedRect(box, rad, rad)
            q.setBrush(pal["accent"])
            q.drawRoundedRect(box.adjusted(4 * u, 4 * u, -4 * u, -4 * u), rad - 4 * u, rad - 4 * u)
        elif style == "outline":                               # контур со срезанными углами
            k = 14 * u
            path = QPainterPath()
            path.addPolygon(QPolygonF([QPointF(box.left() + k, box.top()), QPointF(box.right(), box.top()),
                                       QPointF(box.right(), box.bottom() - k), QPointF(box.right() - k, box.bottom()),
                                       QPointF(box.left(), box.bottom()), QPointF(box.left(), box.top() + k)]))
            path.closeSubpath()
            q.fillPath(path, _alpha(pal["base"], 150))
            q.setBrush(Qt.BrushStyle.NoBrush)
            q.setPen(QPen(pal["ink"], 2.0 * u))
            q.drawPath(path)
            q.setPen(QPen(pal["accent"], 2.0 * u))             # цветная засечка в углу
            q.drawLine(QPointF(box.left(), box.top() + k), QPointF(box.left() + k, box.top()))
            q.drawLine(QPointF(box.right() - k, box.bottom()), QPointF(box.right(), box.bottom() - k))
        else:
            rad = (10 if style == "ticket" else 20) * u
            sh = QColor(0, 0, 0) if dark else QColor(pal["ink"])
            for i in range(8, 0, -1):
                k = i / 8.0
                sh.setAlpha(int((3 + 7 * (1 - k)) * (2.2 if dark else 1.0)))
                gr = mrg * 0.8 * k
                q.setBrush(sh)
                q.drawRoundedRect(box.adjusted(-gr * 0.6, -gr * 0.2 + 4 * u, gr * 0.6, gr + 4 * u), rad + gr, rad + gr)
            if style == "ticket":                              # билет: бумага, корешок за пунктиром, выемки
                path = QPainterPath()
                path.addRoundedRect(box, rad, rad)
                dx = box.left() + box.width() * 0.70
                holes = QPainterPath()
                holes.addEllipse(QPointF(dx, box.top()), 8 * u, 8 * u)
                holes.addEllipse(QPointF(dx, box.bottom()), 8 * u, 8 * u)
                q.fillPath(path.subtracted(holes), pal["paper"])
                q.setPen(QPen(_alpha(pal["ink"], 70), 1.4 * u, Qt.PenStyle.DashLine))
                q.drawLine(QPointF(dx, box.top() + 14 * u), QPointF(dx, box.bottom() - 14 * u))
            else:                                              # стекло
                q.setBrush(QColor(255, 255, 255, 30) if dark else QColor(255, 255, 255, 214))
                q.drawRoundedRect(box, rad, rad)
                q.setBrush(Qt.BrushStyle.NoBrush)
                q.setPen(QPen(QColor(255, 255, 255, 60 if dark else 235), 1.0))
                q.drawRoundedRect(box.adjusted(0.5, 0.5, -0.5, -0.5), rad, rad)
        q.end()
        self._card_bg = pm
        return pm

    def _card_angle(self, line: int, n: int) -> float:
        tilt = float(self._look.get("tilt", 0.0))
        if tilt <= 0 or self._motion() <= 0:
            return 0.0
        rnd = random.Random((int(self._look.get("seed", 0)) ^ (line * 7919 + n * 104729)) & 0xFFFFFFFF)
        a = rnd.uniform(0.35, 1.0) * tilt
        return a if (n + line) % 2 else -a                     # соседние наклейки смотрят в разные стороны

    def _paint_card(self, p, r: QRectF, card: dict, tl: float, a: float, dy: float, angle=0.0, scale=1.0):
        if a <= 0.01:
            return
        u = self._g["u"]
        fg, bar_c, track_c = self._card_colors()
        mrg = int(18 * u)
        p.save()
        c = r.center()
        p.translate(c.x(), c.y() + dy)
        if angle:
            p.rotate(angle)
        if scale != 1.0:
            p.scale(scale, scale)
        r = QRectF(-r.width() / 2, -r.height() / 2, r.width(), r.height())
        p.setOpacity(a)
        p.drawPixmap(QPointF(r.left() - mrg, r.top() - mrg), self._card_back())
        pad = 16 * u
        value, frac = scene_cards.card_value(card, tl)
        # заголовок со значком
        hs = int(15 * u)
        p.drawPixmap(QPointF(r.left() + pad - hs * 0.25, r.top() + pad - hs * 0.3), self._emoji_pm(card["emoji"], hs))
        p.setFont(self._font(13 * u, QFont.Weight.DemiBold))
        p.setPen(fg)
        p.setOpacity(a * 0.8)
        big = int(min(r.height() * 0.42, 58 * u))
        tw = r.width() - 2 * pad - hs * 1.5
        fm = QFontMetricsF(p.font())
        p.drawText(QRectF(r.left() + pad + hs * 1.45, r.top() + pad - 2 * u, tw, hs * 1.5),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                   fm.elidedText(card["title"], Qt.TextElideMode.ElideRight, tw))
        if card.get("layout", "stat") != "stat":
            self._card_extra(p, r, card, value, frac, tl, a, fg, bar_c, track_c, pad, u)
            p.restore()
            return
        # большой значок справа
        p.setOpacity(a)
        ex = r.right() - pad - big * 1.25
        motif = card.get("motif")
        if motif:
            scene_motion.sticker(p, QPointF(ex + big * .52, 0), big * .90,
                                 motif, self._phase, self._drive, a)
        else:
            p.drawPixmap(QPointF(ex, -big * 0.72), self._emoji_pm(card["emoji"], big))
        # значение и подпись
        vw = max(40.0, ex - r.left() - pad - 6 * u)
        vf = self._font(min(r.height() * 0.27, 40 * u))
        vfm = QFontMetricsF(vf)
        if vfm.horizontalAdvance(value) > vw:                  # длинное значение — мельче, а не обрезать
            vf = self._font(vf.pixelSize() * max(0.55, vw / vfm.horizontalAdvance(value)))
        p.setFont(vf)
        p.setPen(fg)
        vy = r.top() + r.height() * 0.30
        p.drawText(QRectF(r.left() + pad, vy, vw, r.height() * 0.32),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), value)
        p.setOpacity(a * 0.66)
        cf = self._font(12 * u, QFont.Weight.Medium)
        p.setFont(cf)
        cfm = QFontMetricsF(cf)
        p.drawText(QRectF(r.left() + pad, vy + r.height() * 0.32, vw, 20 * u),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                   cfm.elidedText(card.get("caption", ""), Qt.TextElideMode.ElideRight, vw))
        if frac is not None:                                   # полоска
            bh = 4 * u
            bw = r.width() * 0.70 - pad * 1.7 if self._look.get("card") == "ticket" else r.width() - 2 * pad
            br = QRectF(r.left() + pad, r.bottom() - pad - bh, bw, bh)
            p.setPen(Qt.PenStyle.NoPen)
            p.setOpacity(a)
            p.setBrush(track_c)
            p.drawRoundedRect(br, bh / 2, bh / 2)
            p.setBrush(bar_c)
            p.drawRoundedRect(QRectF(br.left(), br.top(), max(bh, br.width() * max(0.0, min(1.0, frac))), bh),
                              bh / 2, bh / 2)
        p.restore()

    def _chip(self, p, right, y, text, icon, a, u) -> float:
        """Плашка-пилюля, прижатая правым краем к right. → её левый край."""
        acc = self._pal["accent"]
        f = self._font(11 * u, QFont.Weight.Bold)
        fm = QFontMetricsF(f)
        iw = 16 * u if icon else 0.0
        w = fm.horizontalAdvance(text) + iw + 20 * u
        r = QRectF(right - w, y, w, 24 * u)
        p.setOpacity(a)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_alpha(acc, 40))
        p.drawRoundedRect(r, 12 * u, 12 * u)
        if icon:
            es = int(11 * u)
            p.drawPixmap(QPointF(r.left() + 8 * u - es * 0.25, r.center().y() - es * 0.75), self._emoji_pm(icon, es))
        p.setFont(f)
        p.setPen(acc)
        p.drawText(QRectF(r.left() + 10 * u + iw, r.top(), w - iw - 14 * u, r.height()),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), text)
        return r.left()

    def _card_extra(self, p, r, card, value, frac, tl, a, fg, bar_c, track_c, pad, u):
        """Карточки посложнее: goal — уровень с плашкой и флажком цели, spark — с графиком, range — «от — до»."""
        layout, chip, h = card.get("layout"), card.get("chip", ""), r.height()
        left, right = r.left() + pad, r.right() - pad
        bh = 4 * u
        br = QRectF(left, r.bottom() - pad - bh, right - left, bh)
        big = self._font(min(h * 0.29, 42 * u))
        small = self._font(12 * u, QFont.Weight.Medium)
        vy = r.top() + h * 0.30
        if layout == "goal":
            p.setOpacity(a * 0.6)
            p.setPen(fg)
            p.setFont(small)
            p.drawText(QRectF(left, r.top() + h * 0.25, right - left, 16 * u), int(Qt.AlignmentFlag.AlignLeft),
                       card.get("caption", ""))
            p.setOpacity(a)
            p.setFont(big)
            p.drawText(QRectF(left, r.top() + h * 0.36, (right - left) * 0.5, h * 0.34),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), value)
            if chip:
                self._chip(p, right, r.top() + h * 0.36, chip, "🔒", a, u)
            p.setOpacity(a)
            p.setPen(fg)
            p.setFont(self._font(11 * u, QFont.Weight.Bold))
            p.drawText(QRectF(left, r.top() + h * 0.36 + 28 * u, right - left, 16 * u),
                       int(Qt.AlignmentFlag.AlignRight), "to goal: ∞" if chip.isascii() else "до цели: ∞")
            fx = br.left() + br.width() * 0.60                 # флажок цели — до него полоска не доходит
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(track_c)
            p.drawRoundedRect(br, bh / 2, bh / 2)
            p.setBrush(bar_c)
            fill = br.width() * 0.60 * (0.45 + 0.5 * max(0.0, min(1.0, tl)))
            p.drawRoundedRect(QRectF(br.left(), br.top(), max(bh, fill), bh), bh / 2, bh / 2)
            es = int(12 * u)
            p.drawPixmap(QPointF(fx - es * 0.4, br.top() - es * 1.45), self._emoji_pm("🚩", es))
        elif layout == "spark":
            p.setOpacity(a)
            p.setPen(fg)
            p.setFont(big)
            vw = (right - left) * 0.62
            fm = QFontMetricsF(big)
            if fm.horizontalAdvance(value) > vw:
                big = self._font(big.pixelSize() * max(0.55, vw / fm.horizontalAdvance(value)))
                p.setFont(big)
            p.drawText(QRectF(left, vy, vw, h * 0.32), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                       value)
            p.setOpacity(a * 0.6)
            p.setFont(small)
            p.drawText(QRectF(left, vy + h * 0.32, vw, 18 * u), int(Qt.AlignmentFlag.AlignLeft), card.get("caption", ""))
            if chip:
                self._chip(p, right, r.bottom() - pad - 24 * u, chip, "", a, u)
            try:
                down = float(card["b"]) < float(card["a"])
            except (TypeError, ValueError):
                down = True
            gx0, gx1 = left + (right - left) * 0.64, right
            gy0, gy1 = r.top() + h * 0.30, r.top() + h * 0.58
            rnd = random.Random(card.get("title", ""))
            n = 7
            pts = []
            for k in range(n):
                t = k / (n - 1)
                yv = (t if down else 1.0 - t) + rnd.uniform(-0.16, 0.16) * (0 < k < n - 1)
                pts.append(QPointF(gx0 + (gx1 - gx0) * t, gy0 + (gy1 - gy0) * max(0.0, min(1.0, yv))))
            path = QPainterPath(pts[0])
            for k in range(1, n):
                mid = (pts[k - 1].x() + pts[k].x()) / 2
                path.cubicTo(QPointF(mid, pts[k - 1].y()), QPointF(mid, pts[k].y()), pts[k])
            show = 0.25 + 0.75 * max(0.0, min(1.0, tl))        # график дорисовывается, пока поётся строка
            p.save()
            p.setClipRect(QRectF(gx0 - 4, gy0 - 8, (gx1 - gx0) * show + 6, gy1 - gy0 + 16),
                          Qt.ClipOperation.IntersectClip)
            p.setOpacity(a)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(bar_c, 2.2 * u, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawPath(path)
            p.restore()
        else:                                                  # range: «6:03 ··· 12:03»
            p.setOpacity(a)
            p.setPen(fg)
            p.setFont(big)
            fm = QFontMetricsF(big)
            w0 = fm.horizontalAdvance(value)
            to = str(card.get("to", ""))
            p.drawText(QRectF(left, vy, w0 + 4, h * 0.32), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                       value)
            p.setOpacity(a * 0.5)
            p.drawText(QRectF(left, vy, right - left, h * 0.32),
                       int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), to)
            x0, x1 = left + w0 + 14 * u, right - fm.horizontalAdvance(to) - 14 * u
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bar_c)
            k = 0
            while x0 + k * 10 * u < x1:
                p.setOpacity(a * (0.9 if (k / max(1.0, (x1 - x0) / (10 * u))) <= tl else 0.3))
                p.drawEllipse(QPointF(x0 + k * 10 * u, vy + h * 0.16), 1.8 * u, 1.8 * u)
                k += 1
            p.setOpacity(a * 0.6)
            p.setPen(fg)
            p.setFont(small)
            p.drawText(QRectF(left, vy + h * 0.32, right - left, 18 * u), int(Qt.AlignmentFlag.AlignLeft),
                       card.get("caption", ""))
            if frac is not None:
                p.setOpacity(a)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(track_c)
                p.drawRoundedRect(br, bh / 2, bh / 2)
                p.setBrush(bar_c)
                p.drawRoundedRect(QRectF(br.left(), br.top(), max(bh, br.width() * max(0.0, min(1.0, frac))), bh),
                                  bh / 2, bh / 2)

    def _paint_sound(self, p, op, area):
        from i18n import LANG
        en = LANG == "en"
        ink, accent = self._pal["ink"], self._pal["accent"]
        u = self._g["u"]
        top = area.center().y() - 84 * u
        size = self._g["font"]
        p.setPen(ink)
        p.setOpacity(op)
        p.setFont(self._font(size))
        fm = QFontMetricsF(p.font())
        p.drawText(QRectF(area.left(), top + 22 * u, area.width(), size * 1.36),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                   fm.elidedText(self._title, Qt.TextElideMode.ElideRight, area.width()))
        p.setOpacity(op * .68)
        p.setFont(self._font(14 * u, QFont.Weight.DemiBold))
        label = ("INTRO" if en else "ВСТУПЛЕНИЕ") if self._tx else ("SOUND" if en else "ЗВУК")
        if not self._track_key:
            label = ""
        p.drawText(QRectF(area.left(), top, area.width(), 18 * u), int(Qt.AlignmentFlag.AlignLeft), label)
        count = 64
        if self._sound and self._dur > 0:
            factor = float(getattr(self.win.engine, "preset_factor", 1.) or 1.)
            duration = round(self._dur * factor, 1)
            if self._waveform is None or duration != self._wave_duration:
                self._waveform = self._sound.waveform(duration, count)
                self._wave_duration = duration
            values = self._waveform
            progress = self._pos / self._dur
        else:
            values = [0.] * (count - len(self._live)) + self._live
            progress = 1.
        if not self._track_key:
            return
        gap = area.width() / count
        y = top + 32 * u + size * 1.36 + 33 * u
        p.setPen(Qt.PenStyle.NoPen)
        for i, level in enumerate(values):
            h = (4. + level * 51.) * u
            p.setBrush(_alpha(accent, 210 if i / count <= progress else 62))
            p.drawRoundedRect(QRectF(area.left() + i * gap, y - h / 2, gap * .58, h), 2 * u, 2 * u)

    def _paint_cards(self, p, op):
        if not self._scene or self._li < 0:
            if not self._track_key:
                return
            from i18n import LANG
            en = LANG == "en"
            mode = ("Audio profile" if en else "Профиль звука") if self._sound else (
                "Live analysis" if en else "Анализ в реальном времени")
            card = scene_director.stat("Energy" if en else "Энергия", "〰️", f"{self._lvl:.0%}", mode,
                                       bar=(self._lvl, self._lvl))
            for i, item in enumerate([card] + self._sound_cards):
                self._paint_card(p, self._g[f"card{i}"], item, 1., op, 0.)
            return
        g = self._g
        pms = self._pms()
        t = _ease(self._li_t)
        pop = self._look.get("card") in ("sticker", "outline") and self._motion() > 0
        if t < 1.0 and 0 <= self._li_from < len(self._scene):  # прежние карточки уходят вверх и гаснут
            for n, card in enumerate(self._scene[self._li_from]["cards"]):
                self._paint_card(p, g[f"card{n}"], card, 1.0, op * (1.0 - min(1.0, t * 1.8)), -10.0 * t,
                                 self._card_angle(self._li_from, n))
        i = self._li
        l0, l1 = self._ms[i], self._line_end(i)
        tl = (pms - l0) / max(1.0, l1 - l0)
        for n, card in enumerate(self._scene[i]["cards"]):
            if card.get("metric") == "energy":
                value = f"{self._lvl:.0%}"
                card = {**card, "a": value, "b": value, "bar": (self._lvl, self._lvl)}
            lin = max(0.0, min(1.0, (self._li_t - 0.25 - 0.08 * n) / 0.6))
            tn = _ease(lin)
            self._paint_card(p, g[f"card{n}"], card, tl, op * tn, 0.0 if pop else 16.0 * (1.0 - tn),
                             self._card_angle(i, n), (0.82 + 0.18 * _back(lin)) if pop else 1.0)

    def _paint_note(self, p, op):
        note = self._note
        if note is None:
            return
        g, pal, u = self._g, self._pal, self._g["u"]
        age = self._pms() / 1000 - self._note_at
        k = _ease(min(1.0, age / 0.36)) * _ease(min(1.0, max(0.0, (NOTE_S - age) / 0.36)))
        if k <= 0.01:
            return
        r = g["note"].translated(0, -(1.0 - k) * (g["note"].height() + 30))
        ink = pal["ink"]
        p.setOpacity(op * k)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 90 if pal["dark"] else 26))
        p.drawRoundedRect(r.adjusted(-2, 3 * u, 2, 7 * u), 20 * u, 20 * u)
        p.setBrush(pal["paper"])
        p.drawRoundedRect(r, 18 * u, 18 * u)
        tile = QRectF(r.left() + 12 * u, r.top() + 12 * u, 30 * u, 30 * u)
        p.setBrush(pal["accent"])
        p.drawRoundedRect(tile, 8 * u, 8 * u)
        es = int(17 * u)
        p.drawPixmap(QPointF(tile.center().x() - es * 0.75, tile.center().y() - es * 0.75),
                     self._emoji_pm(note["emoji"], es))
        tx = tile.right() + 10 * u
        tw = r.right() - tx - 12 * u
        p.setPen(ink)
        p.setOpacity(op * k * 0.6)
        p.setFont(self._font(11 * u, QFont.Weight.Medium))
        from i18n import tr
        p.drawText(QRectF(tx, r.top() + 8 * u, tw, 16 * u), int(Qt.AlignmentFlag.AlignLeft), note.get("app", ""))
        p.drawText(QRectF(tx, r.top() + 8 * u, tw, 16 * u), int(Qt.AlignmentFlag.AlignRight), tr("сейчас"))
        p.setOpacity(op * k)
        p.setFont(self._font(13 * u, QFont.Weight.Bold))
        fm = QFontMetricsF(p.font())
        p.drawText(QRectF(tx, r.top() + 25 * u, tw, 18 * u), int(Qt.AlignmentFlag.AlignLeft),
                   fm.elidedText(note["title"], Qt.TextElideMode.ElideRight, tw))
        p.setOpacity(op * k * 0.8)
        p.setFont(self._font(12 * u, QFont.Weight.Medium))
        fm = QFontMetricsF(p.font())
        p.drawText(QRectF(tx, r.top() + 44 * u, tw, 18 * u), int(Qt.AlignmentFlag.AlignLeft),
                   fm.elidedText(note.get("text", ""), Qt.TextElideMode.ElideRight, tw))

    def _icon(self, p, name, icon, size, op, color: QColor, alpha=1.0):
        from yamusic_theme import ya_icon
        r = self._g[name]
        hot, down = self._hover == name, self._down == name
        if hot or down:
            p.setOpacity(op)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_alpha(self._pal["ink"], 34 if down else 20))
            p.drawEllipse(r)
        p.setOpacity(op * (1.0 if hot else alpha))
        s = size * (0.9 if down else 1.0)
        c = r.center()
        ya_icon(icon, int(size), color.name()).paint(p, QRectF(c.x() - s / 2, c.y() - s / 2, s, s).toRect())

    def _paint_art(self, p, op):
        cover = self._g["cover"]
        c = cover.center()
        side = cover.width()
        frame = self._frame
        amount = max(self._flash, self._drive * .55)
        if self._glow is not None and amount > 0:
            gs = self._glow.width() * (1.0 + 0.18 * (1.0 - amount))
            p.setOpacity(op * min(1.0, amount * 0.9))
            p.drawPixmap(QRectF(c.x() - gs / 2, c.y() - gs / 2, gs, gs), self._glow, QRectF(self._glow.rect()))
        if self._under is None:
            return
        mix = _ease(self._motif_mix)
        drive = min(1., self._drive * .72 + self._bass * .28)
        scene_motion.halo(p, cover, self._motif, self._pal["glow"], self._phase, drive, op * .78)
        pulse = float(self._look.get("pulse", 1.0))
        sc = self._scale * (1.0 + .020 * pulse * drive + .012 * self._flash)
        p.setOpacity(op)
        p.save()
        p.translate(c)
        if self._motion() > 0:
            if frame == "polaroid":
                p.rotate(float(self._look.get("art_tilt", 0.0)))
            elif frame == "free" and self._playing:
                p.rotate(math.sin(self._phase * 1.6) * 1.2 * pulse)    # персонаж покачивается
        p.scale(sc, sc)
        p.translate(-side / 2, -side / 2)
        m = self._under_m
        p.drawPixmap(QRectF(-m, -m, side + 2 * m, side + 2 * m), self._under, QRectF(self._under.rect()))
        pm = self._movie.currentPixmap() if self._movie is not None else self._art
        if pm is not None and not pm.isNull():
            pw, ph = float(pm.width()), float(pm.height())
            if frame == "free":                                # целиком, стоя на «полу»
                k = min(side / pw, side / ph)
                tw, th = pw * k, ph * k
                p.drawPixmap(QRectF((side - tw) / 2, side - th, tw, th), pm, QRectF(0, 0, pw, ph))
            else:
                cr = content_rect(side, frame)
                p.setClipPath(frame_path(cr, frame))
                k = max(cr.width() / pw, cr.height() / ph)
                tw, th = pw * k, ph * k
                p.drawPixmap(QRectF(cr.center().x() - tw / 2, cr.center().y() - th / 2, tw, th), pm,
                             QRectF(0, 0, pw, ph))
                p.setClipping(False)
                if frame != "polaroid":                        # тонкий светлый кант
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.setPen(QPen(QColor(255, 255, 255, 40), 1.0))
                    p.drawPath(frame_path(cr.adjusted(0.5, 0.5, -0.5, -0.5), frame))
        p.restore()
        if self._art_info.get("source") != "user":
            position = QPointF(cover.right() - side * .025, cover.bottom() - side * .106)
            scene_motion.sticker(p, position, side * .232, self._old_motif, self._phase, drive, op * (1 - mix))
            scene_motion.sticker(p, position, side * .232, self._motif, self._phase, drive, op * mix)

    def _paint_side(self, p, op):
        g, pal, u = self._g, self._pal, self._g["u"]
        ink, acc = pal["ink"], pal["accent"]
        self._paint_art(p, op)
        p.setOpacity(op)
        p.setPen(ink)
        tf = self._font(24 * u)
        p.setFont(tf)
        fm = QFontMetricsF(tf)
        p.drawText(g["title"], int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                   fm.elidedText(self._title, Qt.TextElideMode.ElideRight, g["title"].width()))
        p.setOpacity(op * 0.62)
        af = self._font(14 * u, QFont.Weight.Medium)
        p.setFont(af)
        fm = QFontMetricsF(af)
        p.drawText(g["artist"], int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                   fm.elidedText(self._artist, Qt.TextElideMode.ElideRight, g["artist"].width()))
        sig = self._sig or (False, False, 0, False, None, None)
        self._icon(p, "like", "heart_fill" if sig[0] else "heart", 24 * u, op, acc if sig[0] else ink,
                   1.0 if sig[0] else 0.7)
        # время
        pr = g["prog"]
        frac = (self._pos / self._dur) if self._dur > 0 else 0.0
        frac = max(0.0, min(1.0, frac))
        ly = pr.center().y()
        hot = self._hover == "prog" or self._drag == "prog"
        th = (5 if hot else 3) * u
        p.setPen(Qt.PenStyle.NoPen)
        p.setOpacity(op)
        p.setBrush(_alpha(ink, 40))
        p.drawRoundedRect(QRectF(pr.left(), ly - th / 2, pr.width(), th), th / 2, th / 2)
        p.setBrush(ink)
        p.drawRoundedRect(QRectF(pr.left(), ly - th / 2, pr.width() * frac, th), th / 2, th / 2)
        kr = (7 if hot else 5) * u
        p.drawEllipse(QPointF(pr.left() + pr.width() * frac, ly), kr, kr)
        p.setOpacity(op * 0.6)
        p.setPen(ink)
        p.setFont(self._font(11 * u, QFont.Weight.DemiBold))
        p.drawText(g["times"], int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), _fmt(self._pos))
        if self._dur > 0:
            p.drawText(g["times"], int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), _fmt(self._dur))
        # управление
        self._icon(p, "shuffle", "shuffle", 20 * u, op, acc if sig[1] else ink, 1.0 if sig[1] else 0.6)
        self._icon(p, "repeat", "repeat_one" if sig[2] == 2 else "repeat", 20 * u, op, acc if sig[2] else ink,
                   1.0 if sig[2] else 0.6)
        self._icon(p, "prev", "prev", 26 * u, op, ink, 0.92)
        self._icon(p, "next", "next", 26 * u, op, ink, 0.92)
        from yamusic_theme import ya_icon
        pb = g["play"]
        p.setOpacity(op)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ink)
        k = 0.94 if self._down == "play" else 1.06 if self._hover == "play" else 1.0
        rr = pb.width() / 2 * k
        p.drawEllipse(pb.center(), rr, rr)
        s = 20 * u
        ya_icon("pause" if self._playing else "play", int(s), pal["base"].name()).paint(
            p, QRectF(pb.center().x() - s / 2, pb.center().y() - s / 2, s, s).toRect())
        self._icon(p, "back", "chevron_down", 22, op, ink, 0.6)
        # метка формата после исполнителя
        if self._tag:
            tf2 = self._font(10 * u, QFont.Weight.DemiBold)
            tw = QFontMetricsF(tf2).horizontalAdvance(self._tag) + 12 * u
            ax = g["artist"].left() + min(fm.horizontalAdvance(self._artist), g["artist"].width() - tw - 8 * u) + 8 * u
            tr_ = QRectF(ax, g["artist"].center().y() - 8 * u, tw, 16 * u)
            p.setOpacity(op)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_alpha(ink, 22))
            p.drawRoundedRect(tr_, 5 * u, 5 * u)
            p.setOpacity(op * 0.62)
            p.setPen(ink)
            p.setFont(tf2)
            p.drawText(tr_, int(Qt.AlignmentFlag.AlignCenter), self._tag)
        # громкость и значки текста и очереди
        try:
            vol = max(0.0, min(1.0, float(self.win.vol.value()) / 100.0))
        except Exception:                                      # noqa: BLE001
            vol = 0.7
        vr = g["vol"]
        vhot = self._hover == "vol" or self._drag == "vol"
        th = (5 if vhot else 3) * u
        ly = vr.center().y()
        p.setPen(Qt.PenStyle.NoPen)
        p.setOpacity(op)
        p.setBrush(_alpha(ink, 40))
        p.drawRoundedRect(QRectF(vr.left(), ly - th / 2, vr.width(), th), th / 2, th / 2)
        p.setBrush(ink)
        p.drawRoundedRect(QRectF(vr.left(), ly - th / 2, vr.width() * vol, th), th / 2, th / 2)
        p.drawEllipse(QPointF(vr.left() + vr.width() * vol, ly), (6 if vhot else 4.5) * u, (6 if vhot else 4.5) * u)
        for name, size, al in (("vol_lo", 13, 0.5), ("vol_hi", 17, 0.7)):
            rr_ = g[name]
            s2 = size * u
            p.setOpacity(op * al)
            ya_icon("volume", int(s2), ink.name()).paint(
                p, QRectF(rr_.center().x() - s2 / 2, rr_.center().y() - s2 / 2, s2, s2).toRect())
        self._icon(p, "lyr", "lyrics", 17 * u, op, ink, 0.7)
        self._icon(p, "queue", "queue", 17 * u, op, ink, 0.7)

    def _paint_chrome(self, p, op):
        """Строка состояния: часы с датой слева, «островок» с треком по центру, связь и батарея справа."""
        g, pal, u = self._g, self._pal, self._g["u"]
        ink = pal["ink"]
        W, m, sy = float(self.width()), g["m"], g["status_y"]
        lt = time.localtime()
        try:
            import i18n
            en = getattr(i18n, "LANG", "ru") == "en"
        except Exception:                                      # noqa: BLE001
            en = False
        days = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun") if en else ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
        months = (("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec") if en else
                  ("янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"))
        clock = f"{lt.tm_hour}:{lt.tm_min:02d}"
        date = f"{days[lt.tm_wday]} {lt.tm_mday} {months[lt.tm_mon - 1]}"
        f1 = self._font(13 * u, QFont.Weight.Bold)
        p.setFont(f1)
        p.setPen(ink)
        p.setOpacity(op * 0.9)
        cw = QFontMetricsF(f1).horizontalAdvance(clock)
        p.drawText(QRectF(m, sy - 10 * u, cw + 4, 20 * u), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                   clock)
        p.setFont(self._font(13 * u, QFont.Weight.Medium))
        p.setOpacity(op * 0.55)
        p.drawText(QRectF(m + cw + 10 * u, sy - 10 * u, 200 * u, 20 * u),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), date)
        # Статус анализа показывает, какие данные режиссёр сейчас использует.
        status = ("SCENE AI" if en else "РЕЖИССЁР ИИ")
        if self._sound and self._sound.bpm:
            status += f"  ·  {self._sound.bpm} BPM"
        elif self._sound_busy:
            status += "  ·  …"
        p.setFont(self._font(11 * u, QFont.Weight.DemiBold))
        p.setPen(ink)
        p.setOpacity(op * .68)
        p.drawText(QRectF(ir_x := W / 2 + 88 * u, sy - 11 * u, max(0., g["back"].left() - ir_x - 4 * u), 22 * u),
                   int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), status if self._track_key else "")
        p.setPen(Qt.PenStyle.NoPen)
        # островок: обложка, название, столбики звука
        f2 = self._font(12 * u, QFont.Weight.DemiBold)
        fm = QFontMetricsF(f2)
        title = fm.elidedText(self._title, Qt.TextElideMode.ElideRight, 220 * u)
        tw = fm.horizontalAdvance(title)
        ih = 27 * u
        iw = 10 * u + 18 * u + 8 * u + tw + 10 * u + 18 * u + 12 * u
        ir = QRectF(W / 2 - iw / 2, sy - ih / 2, iw, ih)
        p.setOpacity(op)
        p.setBrush(QColor(10, 10, 12))
        p.drawRoundedRect(ir, ih / 2, ih / 2)
        cr = QRectF(ir.left() + 10 * u, ir.center().y() - 9 * u, 18 * u, 18 * u)
        if self._mini is not None:
            clip = QPainterPath()
            clip.addRoundedRect(cr, 5 * u, 5 * u)
            p.save()
            p.setClipPath(clip)
            p.drawPixmap(cr, self._mini, QRectF(self._mini.rect()))
            p.restore()
        p.setPen(QColor(255, 255, 255))
        p.setFont(f2)
        p.drawText(QRectF(cr.right() + 8 * u, ir.top(), tw + 2, ih),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), title)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal["glow"])
        ex = ir.right() - 12 * u - 16 * u
        for k, rate in enumerate((self._bass, self._lvl, self._drive, (self._bass + self._lvl) * .5)):
            lv = (.12 + rate * .88) if self._playing else .23
            hh = (4 + 9 * lv) * u
            p.drawRoundedRect(QRectF(ex + k * 4.4 * u, ir.center().y() - hh / 2, 2.6 * u, hh), 1.3 * u, 1.3 * u)

    def _paint_particles(self, p, op):
        """Что летает в воздухе у этого трека: искры, снег, дождь, угли костра, пузыри или пыль."""
        if self._motion() <= 0:
            return
        motif = scene_director.MOTIFS.get(self._motif)
        kind = motif.particles if motif else self._look.get("particles", "dust")
        W, H = self.width(), self.height()
        pal = self._pal
        dark = pal["dark"]
        ph = self._phase
        boost = 1.0 + 1.2 * max(self._flash, self._drive * .65)
        white = QColor(255, 255, 255)
        p.setPen(Qt.PenStyle.NoPen)
        for k, (x, y, sz, a0, sp) in enumerate(self._sparks):
            tw = 0.5 + 0.5 * math.sin(ph * 1.7 + a0 * 3.0)
            if kind == "snow":
                yy = (y + ph * sp * 1.1) % 1.0
                xx = x + math.sin(ph * 0.7 + a0) * 0.02
                p.setOpacity(op * (0.55 + 0.4 * tw))
                p.setBrush(white)
                r = sz * 2.1
                p.drawEllipse(QPointF(xx * W, yy * H), r, r)
            elif kind == "rain":
                yy = (y + ph * sp * 11.0) % 1.0
                xx = (x + yy * 0.08) % 1.0
                p.setOpacity(op * (0.30 if dark else 0.22))
                p.setPen(QPen(white if dark else pal["ink"], max(1.0, sz * 0.9)))
                ln = H * 0.035 * sz
                p.drawLine(QPointF(xx * W, yy * H), QPointF(xx * W + ln * 0.16, yy * H + ln))
                p.setPen(Qt.PenStyle.NoPen)
            elif kind == "embers":
                yy = (y - ph * sp * 1.8) % 1.0
                xx = x + math.sin(ph * 1.1 + a0) * 0.015
                p.setOpacity(op * (0.25 + 0.7 * tw) * (0.4 + 0.6 * yy))
                p.setBrush(QColor(255, 150, 60) if k % 3 else pal["accent"])
                r = sz * (1.0 + 1.2 * tw) * boost
                p.drawEllipse(QPointF(xx * W, yy * H), r, r)
            elif kind == "bubbles":
                yy = (y - ph * sp * 0.6) % 1.0
                xx = x + math.sin(ph * 0.6 + a0) * 0.02
                p.setOpacity(op * (0.30 + 0.25 * tw))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(white if (dark or k % 2) else pal["accent"], 1.4))
                r = sz * 6.0
                p.drawEllipse(QPointF(xx * W, yy * H), r, r)
                p.setPen(Qt.PenStyle.NoPen)
            elif kind == "dust":
                yy = (y - ph * sp * 0.12) % 1.0
                xx = (x + ph * sp * 0.08) % 1.0
                p.setOpacity(op * (0.14 + 0.3 * tw))
                p.setBrush(white if (dark or k % 2) else pal["accent"])
                r = sz * 1.3
                p.drawEllipse(QPointF(xx * W, yy * H), r, r)
            else:                                              # искры-звёздочки
                yy = (y - ph * sp * 0.35) % 1.0
                xx = x + math.sin(ph * 0.5 + a0) * 0.012
                p.setOpacity(op * (0.16 + 0.5 * tw) * (0.75 if k % 4 == 0 else 1.0))
                p.setBrush(pal["accent"] if k % 4 == 0 else white)
                r = sz * (1.2 + 1.4 * tw) * boost
                cx, cy = xx * W, yy * H
                if k % 3 == 0:
                    path = QPainterPath()
                    path.moveTo(cx, cy - r * 2.2)
                    path.quadTo(cx, cy, cx + r * 2.2, cy)
                    path.quadTo(cx, cy, cx, cy + r * 2.2)
                    path.quadTo(cx, cy, cx - r * 2.2, cy)
                    path.quadTo(cx, cy, cx, cy - r * 2.2)
                    p.drawPath(path)
                else:
                    p.drawEllipse(QPointF(cx, cy), r, r)

    def paintEvent(self, _):
        p = QPainter(self)
        op = _ease(self._op)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setOpacity(op)
        if self._bg is not None:
            if self._bg_old is not None and self._bg_t < 1.0:
                p.drawPixmap(self.rect(), self._bg_old)
                p.setOpacity(op * _ease(self._bg_t))
            p.drawPixmap(self.rect(), self._bg)
        else:
            p.fillRect(self.rect(), self._pal["base"])
        self._paint_particles(p, op)
        self._paint_chrome(p, op)
        self._paint_lyrics(p, op)
        self._paint_cards(p, op)
        self._paint_side(p, op)
        self._paint_note(p, op)
        p.end()
