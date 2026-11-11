# now_playing.py
"""
Экран «Сейчас играет» — во всё окно оболочки Echoes Music.

Большая обложка с мягкой тенью, название и исполнитель крупно, живой фон из цветов обложки
(та же рецептура, что у фона текста: echo_glass._dominant_colors + blur_fx), текущие строки
синхронного текста, «Далее» — два-три следующих трека, и управление с полоской времени.
Открывается кликом по обложке в нижнем плеере и по Ctrl+Shift+N, закрывается по Esc и стрелкой.

Режим «Текст» (кнопка текста в нижнем плеере или вверху экрана) — это прежняя страница текста, перенесённая
сюда: её панель текста (LyricsScrollPanel: перевод, заливка строк, оформление) и её кнопки («Синхронизировать
с ИИ», «Язык и оформление», «Найти текст вручную», «Теги трека») встают в правую колонку, а слева — обложка
и управление этого экрана. Отдельной страницы текста больше нет. Между режимами всё перетекает (раскладка,
«Далее» уходит, панель проявляется). Заголовок окна Windows в это время красится в цвет фона обложки
(DwmSetWindowAttribute, Windows 11), после закрытия — снова системный.

Как это сделано, чтобы ничего не тормозило:
  * обложка, тень, свечение и оба слоя фона готовятся в фоновом потоке (только QImage) — поток окна
    получает готовые картинки и лишь превращает их в QPixmap;
  * фон «дышит» дёшево: два заранее готовых слоя медленно перетекают друг в друга и сдвигаются,
    сводится это в одну картинку 10 раз в секунду, а не на каждом кадре;
  * всё рисуется одним виджетом (как cover_mode), дочерний — только ProgressLine;
  * таймер кадров работает, пока экран открыт; на паузе и при выключенных анимациях кадры
    рисуются только когда что-то действительно изменилось.
Смена трека — перетекание обложки, фона и подписей, а не скачок (motion.strength() == 0 — сразу).
"""
from __future__ import annotations

import bisect
import math
import random
import sys
import threading
import time
from pathlib import Path

from frameclock import FrameTimer
from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QFontMetrics, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                         QRegion, QRadialGradient)
from PyQt6.QtWidgets import QToolTip, QWidget

DRIFT = 56                      # на сколько пикселей второй слой фона больше окна с каждой стороны
BG_STEP = 0.1                   # как часто пересводить фон, с
_ARGB = QImage.Format.Format_ARGB32_Premultiplied


def _ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def _lerp_rect(a, b, t: float):
    if isinstance(a, QRect) and isinstance(b, QRect):
        return QRect(round(a.x() + (b.x() - a.x()) * t), round(a.y() + (b.y() - a.y()) * t),
                     round(a.width() + (b.width() - a.width()) * t), round(a.height() + (b.height() - a.height()) * t))
    return QRectF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t,
                  a.width() + (b.width() - a.width()) * t, a.height() + (b.height() - a.height()) * t)


def _lerp_geom(a: dict, b: dict, t: float) -> dict:
    """Раскладка между «Сейчас играет» (a) и «Текст» (b): прямоугольники плавно перетекают."""
    g = {}
    for k in set(a) | set(b):
        va, vb = a.get(k), b.get(k)
        if isinstance(va, (QRect, QRectF)) and isinstance(vb, (QRect, QRectF)):
            g[k] = _lerp_rect(va, vb, t)
        elif k == "next_rows":
            g[k] = va or []                                    # «Далее» уезжает вместе с раскладкой «Сейчас играет»
        elif va is None or vb is None:
            g[k] = vb if va is None else va                    # появляется/исчезает — место берётся у того, где есть
        else:
            g[k] = vb if t >= 0.5 else va
    return g


def _back(t: float) -> float:
    """Быстрый выход с лёгким перелётом — «пружина» для полёта обложки."""
    t = max(0.0, min(1.0, t)) - 1.0
    return 1.0 + 2.1 * t * t * t + 1.1 * t * t


def _fmt(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60}:{sec % 60:02d}"


# ══════════════════════ картинки (любой поток, только QImage) ══════════════════════ #

def backdrop_colors(src: QImage | None, fallback: list) -> list:
    """Главные цвета обложки (как у фона текста) или запасные — цвета оформления."""
    if src is not None and not src.isNull():
        from echo_glass import _dominant_colors
        return _dominant_colors(src)
    return [QColor(c) for c in fallback] or [QColor("#3a4a6a")]


def build_backdrop(src: QImage | None, w: int, h: int, cols: list, variant: int = 0) -> QImage:
    """Фон w×h: цвета обложки большими мягкими пятнами + сильно размытая обложка + затемнение
    под белый текст. Считается в четверть размера (всё равно размыто) и растягивается.
    variant — другой расклад пятен и зеркальная обложка: между двумя вариантами фон «течёт»."""
    w, h = max(8, int(w)), max(8, int(h))
    lw, lh = max(16, w // 4), max(16, h // 4)
    base = QImage(lw, lh, _ARGB)
    dark = QColor(cols[-1])
    hh, ss, _vv, _a = dark.getHsvF()
    base.fill(QColor.fromHsvF(hh if hh >= 0 else 0.0, min(1.0, ss), 0.10))
    p = QPainter(base)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    rnd = random.Random((sum(c.rgb() for c in cols) & 0xFFFFFF) + variant * 7919)
    for i in range(7):
        c = QColor(cols[i % len(cols)])
        hh, ss, vv, _a = c.getHsvF()
        c = QColor.fromHsvF(hh if hh >= 0 else 0.0, min(1.0, ss * 1.3 + 0.06), min(0.74, vv * 1.05 + 0.04))
        cx, cy = rnd.uniform(-0.1, 1.1) * lw, rnd.uniform(-0.1, 1.1) * lh
        r = rnd.uniform(0.45, 0.85) * max(lw, lh)
        g = QRadialGradient(QPointF(cx, cy), r)
        c0 = QColor(c)
        c0.setAlpha(230 if i < 3 else 165)
        c1 = QColor(c)
        c1.setAlpha(0)
        g.setColorAt(0, c0)
        g.setColorAt(1, c1)
        p.fillRect(base.rect(), g)
    if src is not None and not src.isNull():
        try:
            import blur_fx
            cov = blur_fx.blurred_cover(src, lw, lh, max(lw, lh) / 14.0, sat=1.4)
            if variant:
                cov = cov.mirrored(True, False)
            p.setOpacity(0.5)
            p.drawImage(0, 0, cov)
            p.setOpacity(1.0)
        except Exception as e:                                 # noqa: BLE001
            print("[now playing] blur:", e)
    p.end()
    sm = base.scaled(12, 12, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    lum = sum(sm.pixelColor(x, y).lightnessF() for y in range(12) for x in range(12)) / 144.0
    p = QPainter(base)
    p.fillRect(base.rect(), QColor(0, 0, 0, int(min(165, 62 + max(0.0, lum - 0.22) * 300))))
    vig = QRadialGradient(QPointF(lw * 0.5, lh * 0.45), max(lw, lh) * 0.8)
    vig.setColorAt(0.5, QColor(0, 0, 0, 0))
    vig.setColorAt(1.0, QColor(0, 0, 0, 105))
    p.fillRect(base.rect(), vig)
    p.end()
    out = base.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    try:                                                       # шум ±0.5 уровня — без полос на тёмных переходах
        import blur_fx
        out = blur_fx.from_array(blur_fx.to_array(out), dither=True)
    except Exception:                                          # noqa: BLE001
        pass
    return out.convertToFormat(QImage.Format.Format_RGB32)


def card_image(cover: QImage, side: int, radius: float, dpr: float = 1.0) -> tuple:
    """Обложка side×side со скруглением и мягкой тенью вокруг. → (картинка, поле вокруг в логических px)."""
    side = max(8, int(side))
    m = int(side * 0.16) + 8
    n = int(round((side + 2 * m) * dpr))
    out = QImage(n, n, _ARGB)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.scale(dpr, dpr)
    r = QRectF(m, m, side, side)
    p.setPen(Qt.PenStyle.NoPen)
    steps = 14
    for i in range(steps, 0, -1):                              # тень: много слабых слоёв — без ступенек
        k = i / steps
        grow = m * 0.72 * k
        sh = QPainterPath()
        sh.addRoundedRect(r.adjusted(-grow * 0.75, -grow * 0.35 + m * 0.16, grow * 0.75, grow + m * 0.16),
                          radius + grow, radius + grow)
        p.fillPath(sh, QColor(0, 0, 0, int(5 + 13 * (1 - k))))
    clip = QPainterPath()
    clip.addRoundedRect(r, radius, radius)
    p.setClipPath(clip)
    s = min(cover.width(), cover.height())
    sq = cover.copy((cover.width() - s) // 2, (cover.height() - s) // 2, s, s)
    px = max(1, int(round(side * dpr)))
    if s != px:
        sq = sq.scaled(px, px, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    p.drawImage(r, sq)
    p.setClipping(False)
    p.setBrush(Qt.BrushStyle.NoBrush)                          # тонкий светлый кант — обложка «стеклянная»
    p.setPen(QPen(QColor(255, 255, 255, 34), 1.0))
    p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    p.end()
    return out, m


def glow_image(col: QColor, side: int) -> QImage:
    """Мягкое пятно цвета обложки за обложкой (дышит в такт басу). Сразу в размер экрана: при сведении фона
    оно копируется как есть — растягивать полупрозрачную картинку на каждом кадре дорого."""
    n = max(16, int(side))
    out = QImage(n, n, _ARGB)
    out.fill(Qt.GlobalColor.transparent)
    hh, ss, vv, _a = col.getHsvF()
    c = QColor.fromHsvF(hh if hh >= 0 else 0.0, min(1.0, ss * 1.1 + 0.05), max(0.75, min(1.0, vv * 1.2)))
    g = QRadialGradient(QPointF(n / 2, n / 2), n / 2)
    for stop, a in ((0.0, 150), (0.45, 86), (0.75, 26), (1.0, 0)):
        cc = QColor(c)
        cc.setAlpha(a)
        g.setColorAt(stop, cc)
    p = QPainter(out)
    p.fillRect(out.rect(), g)
    p.end()
    return out


class _Bus(QObject):
    done = pyqtSignal(int, object)


class _Layer:
    """Всё, что относится к одному треку: подписи и готовые картинки."""
    __slots__ = ("key", "title", "artist", "track", "bg_a", "bg_b", "card", "card_m", "glow", "size")

    def __init__(self, key="", title="", artist="", track=None):
        self.key, self.title, self.artist, self.track = key, title, artist, track
        self.bg_a = self.bg_b = self.card = self.glow = None
        self.card_m = 0
        self.size = None


# ══════════════════════════════ сам экран ══════════════════════════════ #

class NowPlaying(QWidget):
    """Оверлей поверх оболочки (YaShell). open() / close_mode() / is_open()."""

    closed = pyqtSignal()
    opened = pyqtSignal()

    TIPS = {
        "back": "Свернуть (Esc)", "lyrics": "Текст песни", "queue": "Очередь",
        "like": "Мне нравится", "shuffle": "Перемешать", "prev": "Предыдущий",
        "play": "Играть / пауза", "next": "Следующий", "repeat": "Повтор",
    }

    def __init__(self, shell):
        super().__init__(shell)
        self.shell = shell
        self.win = shell.win
        self.setObjectName("YaNowPlaying")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._op = 0.0                 # 0 — закрыт, 1 — открыт
        self._op_to = 0.0
        self._cur: _Layer | None = None
        self._prev: _Layer | None = None
        self._xf = 1.0                 # перетекание prev → cur
        self._job = 0
        self._pending = None           # (ключ, размер) заказанных картинок
        self._want_key = None
        self._resized_at = 0.0
        self._bgc: QPixmap | None = None
        self._bg_t = 0.0
        self._phase = 0.0
        self._lvl = 0.0
        self._scale = 1.0
        self._playing = False
        self._pos = self._dur = 0.0
        self._sec = -1
        self._hover = None
        self._down = None
        self._state_sig = None
        self._nexts: list = []
        self._nexts_t = 0.0
        self._ly_src = None            # id списка строк
        self._ly_ms: list = []
        self._ly_tx: list = []
        self._li = -1
        self._li_from = -1
        self._li_t = 1.0
        self._ly_hits: list = []
        self._h_cache: dict = {}
        self._geom_sig = None
        self._g: dict = {}
        self._last = time.monotonic()
        self._free_at = 0.0
        self._nx_cache = None
        self._from = None              # откуда «вылетает» обложка при открытии (обложка в нижнем плеере)
        self._thumb = None
        self._dir = 1                  # смена трека: +1 — вперёд (новая обложка въезжает справа), −1 — назад
        self._last_idx = None
        self._sync_key = None
        self._like_t = 1.0             # всплеск на лайке и отскок кнопки play: 0 → 1
        self._play_t = 1.0
        self._key_at = 0.0
        self._under = None             # снимок окна под экраном: пока экран проявляется, страницу под ним не перерисовывать
        self._mode = "cover"           # "cover" — «Сейчас играет», "lyrics" — текст на весь экран
        self._lm = self._lm_to = 0.0   # 0 — раскладка «Сейчас играет», 1 — «Текст»; между ними — перетекание
        self._gm: dict = {}            # готовые раскладки обоих режимов для текущего размера
        self._cap = None               # цвет, в который сейчас покрашен заголовок окна (None — системный)
        self._cap_t = 0.0
        self._lyr_box = None           # кнопки и панель прежней страницы текста — в режиме «Текст»
        self._lyr_snap = None          # их снимок, пока они проявляются или гаснут
        self._lyr_a = 0.0
        self._under_key = None
        self._bus = _Bus(self)
        self._bus.done.connect(self._on_assets)
        from yamusic_theme import ProgressLine
        self.prog = ProgressLine(self)
        self.prog.seek_to.connect(shell._seek_frac)
        self.prog.hide()
        self._timer = FrameTimer(self)
        self._timer.setInterval(33)                            # в покое; пока что-то движется — каждый кадр (см. _tick)
        self._timer.timeout.connect(self._tick)
        self.hide()

    # ── открыть / закрыть ─────────────────────────────────────────────── #

    def is_open(self) -> bool:
        return self.isVisible() and self._op_to > 0.5

    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str):
        """Переключить «Сейчас играет» ↔ «Текст» на открытом экране — раскладка перетекает."""
        mode = "lyrics" if mode == "lyrics" else "cover"
        self._mode = mode
        self._lm_to = 1.0 if mode == "lyrics" else 0.0
        if self._motion() <= 0:
            self._lm = self._lm_to
        self._geom_sig = None
        if mode == "lyrics":
            self._refresh_lyrics()
            self._lyr_snap = None                              # снимок — уже с текстом этого трека
        self._sync_lyrics_button()
        self._timer.setInterval(8)
        if not self._timer.isActive() and self.isVisible():
            self._timer.start()
        self.update()

    def _refresh_lyrics(self):
        """Панель текста — под играющий трек (раньше это делало открытие страницы текста)."""
        sh = self.shell
        try:
            sh._lyr_src = None
            sh._lyrics_tick(None, None)
        except Exception as e:                                 # noqa: BLE001
            print("[now playing] lyrics:", e)

    def _lyrics_box(self):
        """Кнопки и панель прежней страницы текста — переносятся сюда один раз, при первом режиме «Текст»."""
        box = self._lyr_box
        if box is not None:
            return box
        sh = self.shell
        panel, top = getattr(sh, "l_panel", None), getattr(sh, "l_top", None)
        if panel is None or top is None:
            return None
        from PyQt6.QtWidgets import QVBoxLayout
        box = self._lyr_box = QWidget(self)
        box.setObjectName("NpLyrics")
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        v.addWidget(top)
        v.addWidget(panel, 1)
        col = getattr(sh, "l_collapse", None)
        if col is not None:                                    # свернуть — стрелкой экрана слева вверху
            col.hide()
        # своя подложка панели (кусок фона страницы) здесь не нужна: панель прозрачная, под ней живой фон экрана
        # (с подложкой из этого фона кусок под панелью выходил чёрным)
        panel.set_backdrop(None)
        top.show()
        panel.show()
        box.hide()
        return box

    def _content_op(self) -> float:
        """Насколько проявлено содержимое экрана (как в paintEvent: при полёте обложки — позже фона)."""
        if self._op < 1.0 and self._from is not None:
            return _ease(max(0.0, (self._op - 0.42) / 0.58))
        return _ease(self._op)

    def _place_lyrics(self, g):
        """Кнопки и панель текста стоят на месте правой колонки режима «Текст». Пока они проявляются или гаснут,
        экран рисует их снимок с прозрачностью (paintEvent); живые виджеты — только когда экран открыт целиком.
        (QGraphicsOpacityEffect и показ до открытия экрана оставляли контейнер невидимым.)"""
        lm = g.get("lm", 0.0)
        box = self._lyrics_box() if lm > 0.0 else self._lyr_box
        if box is None:
            return
        fin = self._geom_mode(True)["lyr"]
        self._lyr_a = self._content_op() * lm if self.isVisible() else 0.0
        if fin is None:
            self._lyr_a = 0.0
            if box.isVisible():
                box.hide()
            return
        r = fin.toRect()
        if box.geometry() != r:
            box.setGeometry(r)
            self._lyr_snap = None
        self._ensure_updates(box)
        if self._lyr_a >= 0.995 and self.isVisible():
            self._lyr_snap = None
            if not box.isVisible():
                box.show()
                box.raise_()
            return
        if box.isVisible():
            self._lyr_snap = self._snap_box(box)               # гаснет — с последнего живого кадра
            box.hide()
        if self._lyr_a > 0.01 and self._lyr_snap is None:
            self._lyr_snap = self._snap_box(box)

    @staticmethod
    def _ensure_updates(box):
        """Окно на время анимаций выключает перерисовку (setUpdatesEnabled(False)); виджеты, переехавшие в это
        время со страницы текста, оставались с выключенной перерисовкой — Qt их не рисовал вовсе."""
        if not box.updatesEnabled():
            box.setUpdatesEnabled(True)
        for w in box.findChildren(QWidget):
            if not w.updatesEnabled():
                w.setUpdatesEnabled(True)

    @staticmethod
    def _snap_box(box):
        lay = box.layout()
        if lay is not None:
            lay.activate()
        dpr = box.devicePixelRatioF()
        pm = QPixmap(max(1, int(box.width() * dpr)), max(1, int(box.height() * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        box.render(pm, QPoint(0, 0), QRegion(), QWidget.RenderFlag.DrawChildren)
        return pm

    def _sync_lyrics_button(self):
        try:
            b = getattr(self.shell, "btn_lyrics", None)
            if b is not None:
                b.setChecked(self.isVisible() and self._op_to > 0.5 and self._mode == "lyrics")
        except RuntimeError:
            pass

    def open(self, mode=None):
        if mode is not None:                                   # открыть сразу в нужном режиме (без перетекания)
            self._mode = "lyrics" if mode == "lyrics" else "cover"
            self._lm = self._lm_to = 1.0 if self._mode == "lyrics" else 0.0
            self._geom_sig = None
            self._lyr_snap = None
            if self._mode == "lyrics":
                self._refresh_lyrics()
        p = self.parentWidget()
        if p is not None:
            self.setGeometry(p.rect())
        t = self.shell.current_track()
        key = str(t.get("path", "")) if t else ""
        if self._cur is None or self._cur.key != key:
            self._cur = _Layer(key, *self._texts(t), track=t)
            self._bgc = None
        self._prev, self._xf = None, 1.0
        self._want_key = key
        self._free_at = 0.0
        self._from = self._thumb = None
        self._like_t = self._play_t = 1.0
        self._playing = self.shell.is_playing()
        self._scale = 1.0 if self._playing else 0.94
        self._key_at = time.monotonic()
        self._last_idx = (self.win.queue_context, self.win.current_index)
        pc = getattr(self.shell, "p_cover", None)
        if pc is not None and pc.isVisible() and self._motion() > 0:   # обложка «вылетает» из нижнего плеера
            tl = pc.mapTo(self.shell, QPoint(0, 0))
            side = min(pc.width(), pc.height())
            self._from = QRectF(tl.x(), tl.y() + (pc.height() - side) / 2, side, side)
            self._thumb = pc.grab(QRect(0, (pc.height() - side) // 2, side, side))
        if self._cur.card is None or self._cur.size != (self.width(), self.height()):
            self._request(t)                                   # иначе картинки этого трека уже готовы
        self._nexts_t = 0.0
        self._last = time.monotonic()
        self._op_to = 1.0
        if self._motion() <= 0:
            self._op = 1.0
        self._sync(force=True)
        self._place()
        self._under = self._snap_under() if self._op < 1.0 else None
        self._under_key = key
        self._timer.setInterval(8)
        self.show()
        self.raise_()
        self.setFocus()
        self._set_opaque()
        self._timer.start()
        self.opened.emit()
        self._sync_lyrics_button()
        self.update()

    def close_mode(self, instant=False):
        if not self.isVisible():
            return
        self._op_to = 0.0
        if instant or self._motion() <= 0:
            self._op = 0.0
            self._finish_close()
        else:
            t = self.shell.current_track()
            if self._under is not None and (self._under_key != (str(t.get("path", "")) if t else "")
                                            or self._under.deviceIndependentSize().toSize() != self.size()):
                self._under = self._render_under()             # под экраном уже другое — снять страницу заново
            self._timer.setInterval(8)
            self._set_opaque()
            self.prog.hide()
        self._sync_lyrics_button()

    def _snap_under(self):
        """Снимок оболочки с экрана (вместе с GPU-слоями). С ним экран непрозрачен с первого кадра: иначе каждый
        кадр открытия Qt заново рисует всю страницу под ним — отсюда и были редкие кадры."""
        try:
            from PyQt6.QtGui import QGuiApplication
            if QGuiApplication.platformName() == "offscreen":
                return None
            win, sh = self.window(), self.shell
            if win.isMinimized() or not win.isVisible():
                return None
            tl = sh.mapTo(win, QPoint(0, 0))
            pm = win.screen().grabWindow(int(win.winId()), tl.x(), tl.y(), sh.width(), sh.height())
            return None if pm.isNull() else pm
        except Exception as e:                                 # noqa: BLE001
            print("[now playing] snapshot:", e)
            return None

    def _render_under(self):
        """Страница под открытым экраном (её на экране не видно — рисуем в картинку один раз перед закрытием)."""
        sh = self.shell
        if getattr(sh, "_cur_page", "") == "wave":             # GPU-слой «Моей волны» в картинку не попадает
            return None
        try:
            sh.setUpdatesEnabled(False)
            self.hide()
            pm = sh.grab()
            self.show()
            self.raise_()
            self.setFocus()
            return None if pm.isNull() else pm
        except Exception as e:                                 # noqa: BLE001
            print("[now playing] render under:", e)
            return None
        finally:
            sh.setUpdatesEnabled(True)

    def _finish_close(self):
        self._timer.stop()
        self._caption(False)
        if self._lyr_box is not None:
            self._lyr_box.hide()
        self._under = None
        self.hide()
        self.prog.hide()
        self._prev = None
        self._bgc = None
        self._hover = self._down = None
        self._free_at = time.monotonic() + 30.0                # картинки трека держим полминуты — вдруг откроют снова
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(31000, self._free_assets)
        sh = self.shell
        try:
            sh.setFocus()
        except RuntimeError:
            pass
        self._sync_lyrics_button()
        self.closed.emit()

    def _free_assets(self):
        """Экран давно закрыт — отпустить фон и обложку (десятки мегабайт картинок)."""
        if not self.isVisible() and self._free_at and time.monotonic() >= self._free_at:
            self._cur = self._prev = self._bgc = None
            self._nx_cache = None
            self._free_at = 0.0

    def _set_opaque(self):
        """Открыт полностью — фон сплошной: страницу под экраном Qt не перерисовывает."""
        full = self._op >= 0.999 and self._op_to >= 1.0
        on = full or self._under is not None                   # со снимком окна под собой — непрозрачен всегда
        if on != self.testAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent):
            self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, on)
        want = full
        if self.prog.isVisible() != want:
            self.prog.setVisible(want)

    @staticmethod
    def _motion() -> float:
        try:
            import motion
            return float(motion.strength())
        except Exception:                                      # noqa: BLE001
            return 1.0

    @staticmethod
    def _dur_ms(ms: int) -> float:
        try:
            import motion
            return float(motion.duration(ms))
        except Exception:                                      # noqa: BLE001
            return float(ms)

    # ── данные ────────────────────────────────────────────────────────── #

    @staticmethod
    def _texts(t) -> tuple:
        if not t:
            return "Ничего не играет", ""
        from yamusic_theme import sanitize_title
        return (sanitize_title(t.get("title", "") or "Без названия"),
                t.get("artist") or "Неизвестный исполнитель")

    def _request(self, t):
        """Заказать картинки трека под текущий размер (фоновый поток)."""
        W, H = self.width(), self.height()
        if W < 8 or H < 8:
            return
        key = str(t.get("path", "")) if t else ""
        if self._pending == (key, (W, H)):
            return
        self._pending = (key, (W, H))
        self._job += 1
        job = self._job
        cover = str((t or {}).get("cover", "") or "")
        try:
            if cover and not Path(cover).is_file():
                cover = ""
        except OSError:
            cover = ""
        g = self._geom()
        side = int(g["cover"].width())
        radius = self._radius(side)
        dpr = float(self.devicePixelRatioF())
        import ya_decor
        fallback = [QColor(c) for c in ya_decor.palette("")[0]]
        if not cover:                                          # нет обложки — заглушка плеера (поток окна, редко)
            from yamusic_theme import cover_pixmap
            ph = cover_pixmap("", 256, 0, seed=key or "x").toImage()
        else:
            ph = None
        title, artist = self._texts(t)
        bus = self._bus

        def work():
            res = {"key": key, "title": title, "artist": artist, "track": t, "size": (W, H)}
            try:
                from img_load import read_image
                src = read_image(cover, 1600) if cover else QImage()
                src = src if not src.isNull() else None
                cols = backdrop_colors(src, fallback)
                res["bg_a"] = build_backdrop(src, W, H, cols, 0)
                res["bg_b"] = build_backdrop(src, W + 2 * DRIFT, H + 2 * DRIFT, cols, 1)
                res["card"], res["card_m"] = card_image(src if src is not None else ph, side, radius, dpr)
                res["glow"] = glow_image(cols[0], int(side * 1.9))
            except Exception as e:                             # noqa: BLE001
                print("[now playing] assets:", e)
            try:
                bus.done.emit(job, res)
            except RuntimeError:                               # экран уже удалён
                pass
        threading.Thread(target=work, name="echoes-nowplaying", daemon=True).start()

    def _on_assets(self, job, res):
        if job != self._job:
            return
        self._pending = None
        if "bg_a" not in res:
            return
        lay = _Layer(res["key"], res["title"], res["artist"], res["track"])
        lay.bg_a = QPixmap.fromImage(res["bg_a"])
        lay.bg_b = QPixmap.fromImage(res["bg_b"])
        card = QPixmap.fromImage(res["card"])
        card.setDevicePixelRatio(float(self.devicePixelRatioF()))
        lay.card, lay.card_m = card, res["card_m"]
        lay.glow = QPixmap.fromImage(res["glow"])
        lay.size = res["size"]
        cur = self._cur
        same = cur is not None and cur.key == lay.key
        if cur is None or same or self._motion() <= 0 or self._op_to < 1.0:
            self._cur = lay                                    # тот же трек (первый показ, новый размер) — без перетекания
            if not same:
                self._prev, self._xf = None, 1.0
        else:
            w = self.win
            now_i, old = (w.queue_context, w.current_index), self._last_idx
            self._dir = -1 if (old and old[0] == now_i[0] and now_i[1] < old[1]
                               and not getattr(w, "shuffle", False)) else 1
            self._prev, self._cur, self._xf = cur, lay, 0.0
        self._last_idx = (self.win.queue_context, self.win.current_index)
        self._compose_bg()
        self.update()

    def _sync(self, force=False):
        """Положение, пауза, лайк/повтор/перемешивание — что изменилось с прошлого кадра."""
        sh, w = self.shell, self.win
        try:
            eng = w.engine
            pos = float((eng.get_position_smooth() if hasattr(eng, "get_position_smooth")
                         else eng.get_position()) or 0)
            dur = float(eng.duration or 0)
        except Exception:                                      # noqa: BLE001
            pos = dur = 0.0
        self._pos, self._dur = pos, dur
        t = sh.current_track()
        sig = (bool(t and sh.is_liked(t)), bool(getattr(w, "shuffle", False)),
               int(getattr(w, "repeat_mode", 0) or 0))
        key = str(t.get("path", "")) if t else ""
        if key == self._sync_key and self._state_sig is not None and sig[0] and not self._state_sig[0]:
            self._like_t = 0.0                                 # трек только что лайкнули — всплеск
        self._sync_key = key
        changed = force or sig != self._state_sig
        self._state_sig = sig
        return changed

    def _lyrics(self):
        """Строки синхронного текста: (моменты в мс, тексты). Пусто — текста с таймкодами нет."""
        lv = getattr(self.win, "lyrics_view", None)
        lines = getattr(lv, "_lines", None) or []
        if not lines or not getattr(lv, "_has_timings", False):
            if self._ly_src is not None:
                self._ly_src, self._ly_ms, self._ly_tx = None, [], []
                self._li = self._li_from = -1
                self._li_t = 1.0
            return
        if id(lines) == self._ly_src and len(lines) == getattr(self, "_ly_n", -1):
            return
        ms, tx = [], []
        for ln in lines:
            if not isinstance(ln, dict):
                continue
            m = ln.get("ms", -1)
            s = " ".join(str(ln.get("text") or "").split())
            if m is None or m < 0 or not s:
                continue
            ms.append(float(m))
            tx.append(s)
        self._ly_src, self._ly_n, self._ly_ms, self._ly_tx = id(lines), len(lines), ms, tx
        self._li = self._li_from = -1
        self._li_t = 1.0
        self._h_cache.clear()

    def _collect_nexts(self, n=5) -> list:
        """Следующие треки: сначала «ваша очередь», потом порядок страницы «Очередь»."""
        w, sh = self.win, self.shell
        out = []
        try:
            for k, t in enumerate(list(getattr(w, "user_queue", []) or [])[:n]):
                out.append((t, ("q", k)))
            qp = sh.pages.get("queue")
            if len(out) < n and qp is not None:
                ctx, cur_i, sq, sp = qp._context_view()
                tracks = w.library if ctx == "library" else w.playlists.get(ctx, {}).get("tracks", [])
                for i in qp._upcoming(tracks, cur_i, sq, sp)[:n - len(out)]:
                    out.append((tracks[i], ("i", ctx, i)))
        except Exception as e:                                 # noqa: BLE001
            print("[now playing] next:", e)
        return out

    # ── кадр ──────────────────────────────────────────────────────────── #

    def _tick(self):
        now = time.monotonic()
        dt = min(0.1, now - self._last)
        self._last = now
        dirty = False
        bg_dirty = False
        if self._op != self._op_to:                            # открытие / закрытие
            step = dt * 1000.0 / max(1.0, self._dur_ms(430 if self._from is not None else 280))
            self._op = min(1.0, self._op + step) if self._op_to > self._op else max(0.0, self._op - step)
            if self._op <= 0.0 and self._op_to <= 0.0:
                self._finish_close()
                return
            self._set_opaque()
            dirty = True
        sh = self.shell
        t = sh.current_track()
        key = str(t.get("path", "")) if t else ""
        if key != self._want_key:                              # сменился трек — заказать картинки
            self._want_key = key
            self._key_at = now
            self._request(t)
            self._nexts_t = 0.0
        elif self._pending is None and self._cur is not None and self._cur.size not in (None, (self.width(), self.height())) \
                and now - self._resized_at > 0.18:
            self._request(t)                                   # окно изменили — те же картинки в новом размере
        playing = sh.is_playing()
        if playing != self._playing:
            self._playing = playing
            if now - self._key_at > 1.2:                       # не при смене трека — только настоящие пуск/пауза
                self._play_t = 0.0
            dirty = bg_dirty = True
        ms = self._motion()
        target = 1.0 if playing else 0.94                      # на паузе обложка чуть «отходит»
        if abs(target - self._scale) > 0.0005:
            self._scale = target if ms <= 0 else self._scale + (target - self._scale) * min(1.0, dt * 9.0)
            dirty = True
        if self._xf < 1.0:
            self._xf = 1.0 if ms <= 0 else min(1.0, self._xf + dt * 1000.0 / max(1.0, self._dur_ms(560)))
            if self._xf >= 1.0:
                self._prev = None
            dirty = True                                       # фон при перетекании — не чаще 30 раз/с, обложки — каждый кадр
            bg_dirty = bg_dirty or self._xf >= 1.0 or now - self._bg_t >= 0.03
        if playing and ms > 0:
            self._phase += dt * min(1.5, ms)
            if now - self._bg_t >= BG_STEP:
                bg_dirty = True
        lvl = 0.0
        if playing and ms > 0:
            try:
                import ya_decor
                d = ya_decor.CURRENT
                lvl = float(d.level) if d is not None and (ya_decor.on("pulse") or ya_decor.on("play_glow")) else 0.0
            except Exception:                                  # noqa: BLE001
                lvl = 0.0
        if abs(lvl - self._lvl) > 0.012:                       # свечение живёт в сведённом фоне (10 раз/с)
            self._lvl += (lvl - self._lvl) * 0.45
            if not playing:
                bg_dirty = True                                # затухает после паузы — досвести
        if self._sync():
            dirty = True
        for attr, dur_ in (("_like_t", 650), ("_play_t", 480)):
            v = getattr(self, attr)
            if v < 1.0:
                setattr(self, attr, 1.0 if ms <= 0 else min(1.0, v + dt * 1000.0 / max(1.0, self._dur_ms(dur_))))
                dirty = True
        self.prog.peaks = getattr(sh.progress, "peaks", None)
        self.prog.set_state(self._pos / self._dur if self._dur > 0 else 0.0, self._dur)
        sec = int(self._pos)
        if sec != self._sec:
            self._sec = sec
            dirty = True
        self._lyrics()
        if self._ly_ms:
            f = float(getattr(self.win.engine, "preset_factor", 1.0) or 1.0)
            li = bisect.bisect_right(self._ly_ms, self._pos * 1000.0 * f + 150.0) - 1
            if li != self._li:
                far = abs(li - self._li) > 3 or ms <= 0
                self._li_from, self._li = self._li, li
                self._li_t = 1.0 if far else 0.0
                dirty = True
            if self._li_t < 1.0:
                self._li_t = min(1.0, self._li_t + dt * 1000.0 / max(1.0, self._dur_ms(420)))
                dirty = True
        if now - self._nexts_t > 0.4:
            self._nexts_t = now
            nx = self._collect_nexts()
            sig = [(str(t_.get("path", "")), t_.get("title"), t_.get("cover")) for t_, _ in nx]
            if sig != [(str(t_.get("path", "")), t_.get("title"), t_.get("cover")) for t_, _ in self._nexts]:
                dirty = True
            self._nexts = nx
        if self._lm != self._lm_to:                            # «Сейчас играет» ↔ «Текст»
            step = dt * 1000.0 / max(1.0, self._dur_ms(560))
            self._lm = min(self._lm_to, self._lm + step) if self._lm_to > self._lm else max(self._lm_to, self._lm - step)
            dirty = True
            bg_dirty = bg_dirty or now - self._bg_t >= 0.03       # свечение за обложкой едет вместе с ней
        self._place()
        if bg_dirty or self._bgc is None:
            self._compose_bg()
            dirty = True
        if dirty:
            self.update()
        if self._op_to >= 1.0 and self._op >= 0.5 and (self._cap is None or now - self._cap_t > 0.5):
            self._caption(True)                                # заголовок окна — в цвет фона (не чаще 2 раз/с)
        elif self._op_to <= 0.0 and self._op < 0.5 and self._cap is not None:
            self._caption(False)
        fast = (self._op != self._op_to or self._xf < 1.0 or self._like_t < 1.0 or self._play_t < 1.0
                or self._li_t < 1.0 or abs(target - self._scale) > 0.0005 or self._lm != self._lm_to)
        want = 8 if fast else 33                               # движение — каждый кадр общих часов, покой — 30 раз/с
        if self._timer.interval() != want:
            self._timer.setInterval(want)

    def _caption(self, on: bool):
        """Заголовок окна Windows — в цвет верхнего края фона обложки; off — вернуть системный цвет."""
        self._cap_t = time.monotonic()
        if sys.platform != "win32":
            return
        try:
            import ctypes
            win = self.window()
            if win is None or not win.isVisible():
                return
            hwnd = int(win.winId())
            dwm = ctypes.windll.dwmapi
            caption, text = 35, 36                             # DWMWA_CAPTION_COLOR, DWMWA_TEXT_COLOR (Windows 11)
            if not on:
                if self._cap is not None:
                    d = ctypes.c_uint(0xFFFFFFFF)              # DWMWA_COLOR_DEFAULT
                    dwm.DwmSetWindowAttribute(hwnd, caption, ctypes.byref(d), 4)
                    dwm.DwmSetWindowAttribute(hwnd, text, ctypes.byref(d), 4)
                self._cap = None
                return
            if self._bgc is None or self._bgc.width() < 8:
                return
            # среднее по верхней полосе фона (а не по самой кромке — она у размытых обложек темнее, и заголовок
            # почти не отличался от обычного); в paintEvent верх фона потом плавно уходит ровно в этот цвет
            img = self._bgc.copy(0, 0, self._bgc.width(), 72).toImage()
            r = g = b = n = 0
            for y in (2, 18, 36, 54, 70):
                for x in range(0, img.width(), max(1, img.width() // 32)):
                    c = img.pixelColor(x, min(y, img.height() - 1))
                    r, g, b, n = r + c.red(), g + c.green(), b + c.blue(), n + 1
            col = (r // n, g // n, b // n)
            if self._cap is not None and max(abs(col[i] - self._cap[i]) for i in range(3)) < 3:
                return
            ref = ctypes.c_uint(col[0] | (col[1] << 8) | (col[2] << 16))
            dwm.DwmSetWindowAttribute(hwnd, caption, ctypes.byref(ref), 4)
            white = ctypes.c_uint(0x00FFFFFF)
            dwm.DwmSetWindowAttribute(hwnd, text, ctypes.byref(white), 4)
            self._cap = col
        except Exception as e:                                 # noqa: BLE001
            print("[now playing] caption:", e)

    def _compose_bg(self):
        """Свести фон в одну картинку: слой A + плывущий слой B (+ предыдущий трек при перетекании)."""
        W, H = self.width(), self.height()
        if W < 2 or H < 2:
            return
        pm = self._bgc
        if pm is None or pm.width() != W or pm.height() != H:
            pm = self._bgc = QPixmap(W, H)
        self._bg_t = time.monotonic()
        p = QPainter(pm)
        p.fillRect(pm.rect(), QColor(10, 10, 13))
        ph = self._phase
        mix = 0.5 + 0.5 * math.sin(ph * 0.33)
        dx = int(round(DRIFT * 0.9 * math.sin(ph * 0.11)))
        dy = int(round(DRIFT * 0.9 * math.cos(ph * 0.083)))
        xf = _ease(self._xf)
        for lay, a in ((self._prev, 1.0), (self._cur, xf if self._prev is not None else 1.0)):
            if lay is None or lay.bg_a is None or a <= 0.0:
                continue
            p.setOpacity(a)
            if lay.size == (W, H):
                p.drawPixmap(0, 0, lay.bg_a)
                p.setOpacity(a * mix * 0.9)
                p.drawPixmap(-DRIFT + dx, -DRIFT + dy, lay.bg_b)
            else:                                              # окно тянут — старый размер растянуть
                p.drawPixmap(QRect(0, 0, W, H), lay.bg_a)
        cur = self._cur
        if cur is not None and cur.glow is not None and cur.size == (W, H):   # свечение за обложкой — в такт басу
            c = self._geom()["cover"].center()
            a = (0.30 + 0.62 * self._lvl) * (1.0 if self._playing else 0.55) * (xf if self._prev is not None else 1.0)
            p.setOpacity(max(0.0, min(1.0, a)))
            p.drawPixmap(int(c.x() - cur.glow.width() / 2), int(c.y() - cur.glow.height() / 2 + cur.glow.height() * 0.02),
                         cur.glow)
        p.end()

    # ── геометрия ─────────────────────────────────────────────────────── #

    @staticmethod
    def _radius(side: int) -> float:
        try:
            from ya_skin import interface_radius
            r = float(interface_radius())
        except Exception:                                      # noqa: BLE001
            r = 22.0
        return max(0.0, min(side * 0.08, r * (0.6 + side / 900.0)))

    def _has_lyrics(self) -> bool:
        return bool(self._ly_ms)

    def _geom(self) -> dict:
        W, H = self.width(), self.height()
        lm = _ease(self._lm)
        sig = (W, H, self._has_lyrics(), len(self._nexts), round(lm, 4))
        if sig == self._geom_sig:
            return self._g
        if lm <= 0.0:
            g = dict(self._geom_mode(False))
        elif lm >= 1.0:
            g = dict(self._geom_mode(True))
        else:
            g = _lerp_geom(self._geom_mode(False), self._geom_mode(True), lm)
        g["lm"] = lm
        self._geom_sig, self._g = sig, g
        return g

    def _geom_mode(self, lyr_mode: bool) -> dict:
        W, H = self.width(), self.height()
        ly = self._has_lyrics()
        n_next = len(self._nexts)
        sig = (W, H, ly, n_next, lyr_mode)
        if sig in self._gm:
            return self._gm[sig]
        if len(self._gm) > 8:
            self._gm.clear()
        compact = W < 1180 or H < 760
        pad = 28 if compact else 52
        top = 66 if compact else 84
        right = W >= 760 and (ly or n_next > 0 or lyr_mode)
        Lw = (W * 0.38 if lyr_mode else W * 0.47) if right else float(W)
        title_px = 24 if compact else 32
        artist_px = 14 if compact else 17
        play_d = 60 if compact else 70
        ctrl_h = title_px + 12 + artist_px + 10 + 20 + 20 + 20 + 12 + play_d
        avail = H - top - pad
        side = int(max(120, min(Lw - 2 * pad, avail - ctrl_h - 22, 430 if lyr_mode else 560)))
        block = side + 22 + ctrl_h
        y0 = top + max(0.0, (avail - block) / 2)
        cx = Lw / 2
        g = {"compact": compact, "pad": pad, "title_px": title_px, "artist_px": artist_px, "right": right}
        g["cover"] = QRectF(cx - side / 2, y0, side, side)
        tw = min(Lw - 2 * pad, max(side, 300))               # подписи и полоска — по ширине обложки
        tx = cx - tw / 2
        y = g["cover"].bottom() + 22
        g["title"] = QRectF(tx, y, tw - 52, title_px + 12)
        g["like"] = QRectF(tx + tw - 42, y + (title_px + 12 + artist_px + 10) / 2 - 21, 42, 42)
        y += title_px + 12
        g["artist"] = QRectF(tx, y, tw - 52, artist_px + 10)
        y += artist_px + 10 + 12
        g["prog"] = QRect(int(tx) - 14, int(y), int(tw) + 28, 20)
        y += 20
        g["times"] = QRectF(tx, y, tw, 18)
        y += 20 + 12
        cy = y + play_d / 2
        g["play"] = QRectF(cx - play_d / 2, cy - play_d / 2, play_d, play_d)
        s = 46 if compact else 50
        gap = 16 if compact else 22
        g["prev"] = QRectF(g["play"].left() - gap - s, cy - s / 2, s, s)
        g["next"] = QRectF(g["play"].right() + gap, cy - s / 2, s, s)
        s2 = 40 if compact else 42
        g["shuffle"] = QRectF(g["prev"].left() - gap - s2, cy - s2 / 2, s2, s2)
        g["repeat"] = QRectF(g["next"].right() + gap, cy - s2 / 2, s2, s2)
        g["back"] = QRectF(pad - 8, (top - 44) / 2 + 2, 44, 44)
        g["queue"] = QRectF(W - pad - 36, (top - 44) / 2 + 2, 44, 44)
        g["lyrics"] = QRectF(g["queue"].left() - 50, g["queue"].top(), 44, 44)
        g["head"] = QRectF(g["back"].right() + 12, g["back"].top(), max(40.0, g["lyrics"].left() - g["back"].right() - 24), 44)
        g["next_rows"] = []
        g["lyr"] = None
        g["next_head"] = None
        if lyr_mode:                                           # «Текст»: вся правая колонка — строки песни
            if right:
                rx0 = Lw + (8 if compact else 24)
                g["lyr"] = QRectF(rx0, top + 6, W - pad - rx0, H - top - pad - 6)
            else:                                              # узкое окно — текст над подписью, обложка прячется
                g["lyr"] = QRectF(pad, top + 6, W - 2 * pad, max(80.0, g["title"].top() - top - 22))
                c = g["cover"].center()
                g["cover"] = QRectF(c.x(), c.y(), 0.0, 0.0)
        elif right:
            rx0 = Lw + (8 if compact else 20)
            rx1 = W - pad
            rw = rx1 - rx0
            row_h = 56 if compact else 60
            if ly:
                rows = min(n_next, 2 if H < 720 else 3)
                nh = (30 + rows * row_h) if rows else 0
                ny = H - pad - nh
                g["lyr"] = QRectF(rx0, top + 6, rw, max(60.0, ny - (26 if rows else 0) - top - 6))
            else:
                rows = min(n_next, max(2, min(5, int((avail - 40) // row_h))))
                nh = 30 + rows * row_h
                ny = top + max(0.0, (avail - nh) / 2)
            if rows:
                g["next_head"] = QRectF(rx0 + 10, ny, rw - 20, 26)
                g["next_rows"] = [QRectF(rx0, ny + 30 + k * row_h, min(rw, 620), row_h - 4) for k in range(rows)]
        self._gm[sig] = g
        return g

    def _place(self):
        g = self._geom()
        r = g["prog"]
        if self.prog.geometry() != r:
            self.prog.setGeometry(r)
        self._place_lyrics(g)

    def _hit(self, pos):
        g = self._geom()
        for name in ("back", "lyrics", "queue", "like", "shuffle", "prev", "play", "next", "repeat"):
            if g[name].contains(pos):
                return name
        for k, r in enumerate(g["next_rows"]):
            if r.contains(pos):
                return ("row", k)
        for r, ms in self._ly_hits:
            if r.contains(pos):
                return ("line", ms)
        if g["cover"].contains(pos):
            return "cover"
        return None

    # ── ввод ──────────────────────────────────────────────────────────── #

    def mouseMoveEvent(self, e):
        h = self._hit(e.position())
        if h != self._hover:
            self._hover = h
            self.setCursor(Qt.CursorShape.PointingHandCursor if h not in (None, "cover")
                           else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, e):
        if self._hover is not None:
            self._hover = None
            self.update()

    def mousePressEvent(self, e):
        e.accept()
        if e.button() != Qt.MouseButton.LeftButton:
            return
        self._down = self._hit(e.position())
        self.update()

    def mouseReleaseEvent(self, e):
        e.accept()
        down, self._down = self._down, None
        if e.button() == Qt.MouseButton.LeftButton and down is not None and self._hit(e.position()) == down:
            self.activate(down)
        self.update()

    def mouseDoubleClickEvent(self, e):
        e.accept()
        if self._hit(e.position()) == "cover":
            self.win.toggle_play()
        else:
            self.mousePressEvent(e)

    def wheelEvent(self, e):
        e.accept()                                             # страница под экраном не прокручивается

    def contextMenuEvent(self, e):
        e.accept()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close_mode()
            e.accept()
            return
        super().keyPressEvent(e)

    def event(self, e):
        if e.type() == QEvent.Type.ToolTip:
            h = self._hit(QPointF(e.pos()))
            tip = self.TIPS.get(h) if isinstance(h, str) else None
            if tip:
                QToolTip.showText(e.globalPos(), tip, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)

    def activate(self, what):
        """Нажатие на элемент экрана (имя кнопки, ("row", k) — трек из «Далее», ("line", мс) — строка текста)."""
        sh, w = self.shell, self.win
        if what == "back":
            self.close_mode()
        elif what == "lyrics":                                 # «Сейчас играет» ↔ «Текст» — на этом же экране
            self.set_mode("cover" if self._mode == "lyrics" else "lyrics")
        elif what == "queue":
            self.close_mode(instant=True)
            if sh._cur_page != "queue":
                sh.show_page("queue")
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
        elif isinstance(what, tuple) and what[0] == "row":
            if 0 <= what[1] < len(self._nexts):
                t, ref = self._nexts[what[1]]
                if ref[0] == "q":
                    q = w.user_queue
                    if 0 <= ref[1] < len(q):
                        q.insert(0, q.pop(ref[1]))
                        w._play_from_queue()
                else:
                    sh.play_row({"t": t, "ctx": ref[1], "i": ref[2]})
                self._nexts_t = 0.0
        elif isinstance(what, tuple) and what[0] == "line":
            try:
                f = float(getattr(w.engine, "preset_factor", 1.0) or 1.0)
                w.engine.seek(max(0.0, what[1] / 1000.0 / f))
            except Exception as e:                             # noqa: BLE001
                print("[now playing] seek:", e)
        self._sync(force=True)
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._resized_at = time.monotonic()
        self._under = None
        self._geom_sig = None
        self._h_cache.clear()
        self._bgc = None
        self._place()

    # ── рисование ─────────────────────────────────────────────────────── #

    def _line_h(self, text, width, font) -> float:
        key = (text, int(width), font.pixelSize())
        h = self._h_cache.get(key)
        if h is None:
            fm = QFontMetrics(font)
            h = float(fm.boundingRect(QRect(0, 0, int(width), 4000),
                                      int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap), text).height())
            if len(self._h_cache) > 600:
                self._h_cache.clear()
            self._h_cache[key] = h
        return h

    def _paint_lyrics(self, p, area: QRectF, op: float, compact: bool):
        from yamusic_theme import ya_font
        n = len(self._ly_tx)
        self._ly_hits = []
        if not n:
            return
        px = 21 if compact else (27 if area.height() < 520 else 30)
        font = ya_font(px, QFont.Weight.Bold)
        gap = px * 0.62
        w = area.width() - 16
        i = self._li
        i_eff = max(0, i)
        lo, hi = max(0, i_eff - 3), min(n - 1, i_eff + 6)
        # центры строк относительно центра текущей
        hs = {j: self._line_h(self._ly_tx[j], w, font) for j in range(lo, hi + 1)}
        cy = {i_eff: 0.0}
        for j in range(i_eff + 1, hi + 1):
            cy[j] = cy[j - 1] + hs[j - 1] / 2 + gap + hs[j] / 2
        for j in range(i_eff - 1, lo - 1, -1):
            cy[j] = cy[j + 1] - hs[j + 1] / 2 - gap - hs[j] / 2
        e = _ease(self._li_t)
        o = self._li_from
        o_eff = max(0, o)
        shift = cy.get(o_eff, 0.0) * (1.0 - e) if e < 1.0 else 0.0
        anchor = area.top() + area.height() * 0.36

        def alpha(j, cur):
            if j == cur:
                return 1.0
            d = abs(j - max(0, cur))
            return (0.46, 0.30, 0.19, 0.11, 0.06, 0.03)[min(5, d - 1 if d else 0)]
        p.save()
        p.setClipRect(area)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255))
        flags = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap)
        for j in range(lo, hi + 1):
            y = anchor + cy[j] - shift
            r = QRectF(area.left() + 8, y - hs[j] / 2, w, hs[j])
            if r.bottom() < area.top() or r.top() > area.bottom():
                continue
            a = alpha(j, i) if e >= 1.0 else alpha(j, o) + (alpha(j, i) - alpha(j, o)) * e
            edge = min(1.0, max(0.0, (area.bottom() - r.center().y()) / 60.0),     # у краёв — растворяется
                       max(0.0, (r.center().y() - area.top()) / 40.0))
            hot = self._hover == ("line", self._ly_ms[j])
            p.setOpacity(op * max(a, 0.7 if hot else 0.0) * edge)
            p.drawText(r, flags, self._ly_tx[j])
            self._ly_hits.append((r, self._ly_ms[j]))
        p.restore()

    def _paint_nexts(self, p, g, op: float):
        """«Далее» рисуется один раз в картинку (обложки, подписи) и дальше копируется: пересобирается, когда
        меняется очередь, наведение, размер или догрузилась обложка."""
        from yamusic_theme import cover_pixmap
        rows = g["next_rows"]
        if not rows or g["next_head"] is None:
            return
        box = QRectF(g["next_head"])
        for r in rows:
            box = box.united(r)
        box = box.adjusted(-12, -2, 2, 2).toAlignedRect()
        dpr = float(self.devicePixelRatioF())
        key = (box.x(), box.y(), box.width(), box.height(), dpr, self._hover if isinstance(self._hover, tuple) else None,
               self._down if isinstance(self._down, tuple) else None,
               tuple((str(t.get("path", "")), t.get("title"), t.get("artist"), t.get("duration"),
                      cover_pixmap(t.get("cover", ""), 44, 8, seed=str(t.get("path", "") or t.get("title", "")),
                                   lazy=self).cacheKey()) for t, _ in self._nexts[:len(rows)]))
        hit = getattr(self, "_nx_cache", None)
        if hit is None or hit[0] != key:
            pm = QPixmap(max(1, int(box.width() * dpr)), max(1, int(box.height() * dpr)))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.GlobalColor.transparent)
            pp = QPainter(pm)
            pp.setRenderHint(QPainter.RenderHint.Antialiasing)
            pp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            pp.translate(-box.x(), -box.y())
            self._draw_nexts(pp, g, 1.0)
            pp.end()
            hit = self._nx_cache = (key, pm)
        p.setOpacity(op)
        p.drawPixmap(box.topLeft(), hit[1])

    def _draw_nexts(self, p, g, op: float):
        from yamusic_theme import _fmt as fmt_dur
        from yamusic_theme import cover_pixmap, sanitize_title, ya_font
        rows = g["next_rows"]
        f = ya_font(11, QFont.Weight.Bold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.6)
        p.setFont(f)
        p.setOpacity(op * 0.62)
        p.setPen(QColor(255, 255, 255))
        p.drawText(g["next_head"], int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), "ДАЛЕЕ")
        f1, f2 = ya_font(14, QFont.Weight.DemiBold), ya_font(12)
        fm1, fm2 = QFontMetrics(f1), QFontMetrics(f2)
        for k, r in enumerate(rows):
            if k >= len(self._nexts):
                break
            t, _ref = self._nexts[k]
            hot = self._hover == ("row", k)
            if hot or self._down == ("row", k):
                p.setOpacity(op)
                path = QPainterPath()
                path.addRoundedRect(r, 12, 12)
                p.fillPath(path, QColor(255, 255, 255, 30 if self._down == ("row", k) else 20))
            p.setOpacity(op)
            cs = int(r.height() - 12)
            pm = cover_pixmap(t.get("cover", ""), 44, 8, seed=str(t.get("path", "") or t.get("title", "")), lazy=self)
            cr = QRectF(r.left() + 10, r.top() + (r.height() - cs) / 2, cs, cs)
            p.drawPixmap(cr.toRect(), pm)
            if hot:
                from yamusic_theme import ya_icon
                p.fillRect(cr.toRect(), QColor(0, 0, 0, 110))
                ya_icon("play", 18, "#ffffff").paint(p, QRectF(cr.center().x() - 9, cr.center().y() - 9, 18, 18).toRect())
            tx = cr.right() + 14
            tw = r.right() - 70 - tx
            p.setFont(f1)
            p.setPen(QColor(255, 255, 255))
            p.drawText(QRectF(tx, r.top() + r.height() / 2 - 20, tw, 20), int(Qt.AlignmentFlag.AlignVCenter),
                       fm1.elidedText(sanitize_title(t.get("title", "") or "Без названия"),
                                      Qt.TextElideMode.ElideRight, int(tw)))
            p.setFont(f2)
            p.setOpacity(op * 0.62)
            p.drawText(QRectF(tx, r.top() + r.height() / 2 + 1, tw, 18), int(Qt.AlignmentFlag.AlignVCenter),
                       fm2.elidedText(t.get("artist") or "Неизвестный исполнитель",
                                      Qt.TextElideMode.ElideRight, int(tw)))
            dur = float(t.get("duration") or 0)
            if dur > 0:
                p.drawText(QRectF(r.right() - 64, r.top(), 52, r.height()),
                           int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), fmt_dur(dur))

    def _paint_title(self, p, lay: _Layer, g, a: float, dy: float):
        from yamusic_theme import ya_font
        if lay is None or a <= 0.003:
            return
        r = QRectF(g["title"]).translated(0, dy)
        px = g["title_px"]
        f = ya_font(px, QFont.Weight.Bold)
        if QFontMetrics(f).horizontalAdvance(lay.title) > r.width():
            f = ya_font(int(px * 0.84), QFont.Weight.Bold)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255))
        p.setOpacity(a)
        p.drawText(r, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                   QFontMetrics(f).elidedText(lay.title, Qt.TextElideMode.ElideRight, int(r.width())))
        f2 = ya_font(g["artist_px"], QFont.Weight.Medium)
        p.setFont(f2)
        p.setOpacity(a * 0.72)
        r2 = QRectF(g["artist"]).translated(0, dy)
        p.drawText(r2, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                   QFontMetrics(f2).elidedText(lay.artist, Qt.TextElideMode.ElideRight, int(r2.width())))

    def _paint_card(self, p, lay: _Layer, cover: QRectF, a: float, scale: float, dx: float = 0.0):
        if lay is None or lay.card is None or a <= 0.003:
            return
        if dx:
            cover = cover.translated(dx, 0)
        k = cover.width() / max(1.0, lay.card.width() / lay.card.devicePixelRatio() - 2 * lay.card_m)
        m = lay.card_m * k
        r = cover.adjusted(-m, -m, m, m)
        if abs(scale - 1.0) > 0.001:
            c = r.center()
            r = QRectF(c.x() - r.width() * scale / 2, c.y() - r.height() * scale / 2,
                       r.width() * scale, r.height() * scale)
        p.setOpacity(a)
        if abs(k - 1.0) < 0.002 and abs(scale - 1.0) <= 0.001:
            p.drawPixmap(r.topLeft(), lay.card)
        else:
            p.drawPixmap(r, lay.card, QRectF(lay.card.rect()))

    def paintEvent(self, _):
        if self._op <= 0.0:
            return
        from yamusic_theme import ya_font
        import ya_decor
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        op = _ease(self._op)
        W, H = self.width(), self.height()
        g = self._geom()
        if op < 1.0 and self._under is not None:               # под проявляющимся экраном — готовый снимок окна
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            p.drawPixmap(self.rect(), self._under)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setOpacity(op)
        if self._bgc is None:
            self._compose_bg()
        if self._bgc is not None:
            if op >= 1.0:                                      # сплошной фон — простое копирование без смешивания
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                p.drawPixmap(0, 0, self._bgc)
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            else:
                p.drawPixmap(0, 0, self._bgc)
        else:
            p.fillRect(self.rect(), QColor(10, 10, 13))
        cap = self._cap
        if cap is not None:                                    # шов с заголовком окна: верх фона уходит ровно в его цвет,
            band = 72                                          # и заголовок выглядит продолжением размытой обложки
            grad = QLinearGradient(0, 0, 0, band)
            grad.setColorAt(0.0, QColor(cap[0], cap[1], cap[2], 255))
            grad.setColorAt(1.0, QColor(cap[0], cap[1], cap[2], 0))
            p.fillRect(QRectF(0, 0, W, band), grad)
        cur, prev = self._cur, self._prev
        xf = _ease(self._xf) if prev is not None else 1.0
        acc = ya_decor.accent()
        cover = g["cover"]
        card_a = op
        if self._op < 1.0 and self._from is not None:
            # открытие: обложка вылетает из нижнего плеера на своё место (закрытие — летит обратно),
            # фон проявляется сразу, остальное — когда обложка почти долетела
            t = self._op
            e = _back(t) if self._op_to >= 1.0 else _ease(t)
            a, b = self._from, cover
            cover = QRectF(a.x() + (b.x() - a.x()) * e, a.y() + (b.y() - a.y()) * e,
                           a.width() + (b.width() - a.width()) * e, a.height() + (b.height() - a.height()) * e)
            card_a = min(1.0, t * 7.0)
            op = _ease(max(0.0, (t - 0.42) / 0.58))
        elif op < 1.0:
            p.translate(0, (1.0 - op) * 26)                    # без плеера под рукой — содержимое «поднимается»

        # обложка: старая остаётся, новая проявляется поверх (свечение за ней — в сведённом фоне)
        if prev is not None and xf < 1.0:                      # смена трека: старая уезжает и уменьшается,
            way = self._dir * cover.width() * 0.5              # новая въезжает с другой стороны
            # без масштабирования: готовые картинки просто сдвигаются — кадр стоит ~1 мс вместо ~8
            self._paint_card(p, prev, cover, card_a * (1.0 - xf), self._scale, round(-way * xf))
            self._paint_card(p, cur, cover, card_a * xf, self._scale, round(way * (1.0 - xf)))
        elif cur is not None and cur.card is not None:
            self._paint_card(p, cur, cover, card_a, self._scale)
        elif self._thumb is not None and prev is None:         # большая обложка ещё готовится — летит маленькая
            p.setOpacity(card_a)
            p.drawPixmap(cover, self._thumb, QRectF(self._thumb.rect()))
        elif prev is None:                                     # картинки ещё готовятся — тихая подложка
            p.setOpacity(op * 0.5)
            ph = QPainterPath()
            rad = self._radius(int(cover.width()))
            ph.addRoundedRect(cover, rad, rad)
            p.fillPath(ph, QColor(255, 255, 255, 16))

        # название и исполнитель
        if prev is not None and xf < 1.0 and prev.key != (cur.key if cur else None):
            lin = self._xf                                     # старая подпись уходит раньше, чем входит новая
            self._paint_title(p, prev, g, op * (1.0 - min(1.0, lin * 2.4)), -12.0 * lin)
            a_new = _ease(max(0.0, (lin - 0.3) / 0.7))
            self._paint_title(p, cur, g, op * a_new, 12.0 * (1.0 - a_new))
        else:
            self._paint_title(p, cur, g, op, 0.0)

        # шапка: свернуть · откуда играет · текст · очередь
        lm = g.get("lm", 0.0)
        for name, icon, size in (("back", "chevron_down", 24), ("lyrics", "lyrics", 20), ("queue", "queue", 20)):
            on = name == "lyrics" and lm > 0.5
            self._named_icon(p, name, icon, g[name], size, op, 1.0 if on else 0.78,
                             ya_decor.accent().name() if on else "#ffffff")
        f = ya_font(11, QFont.Weight.Bold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.6)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255))
        p.setOpacity(op * 0.6)
        hr = g["head"]
        ctx = self._context_name()
        p.drawText(QRectF(hr.left(), hr.top() + (2 if ctx else 12), hr.width(), 20),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), "ТЕКСТ ПЕСНИ" if lm > 0.5 else "СЕЙЧАС ИГРАЕТ")
        if ctx:
            f = ya_font(14, QFont.Weight.DemiBold)
            p.setFont(f)
            p.setOpacity(op * 0.95)
            p.drawText(QRectF(hr.left(), hr.top() + 21, hr.width(), 22),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                       QFontMetrics(f).elidedText(ctx, Qt.TextElideMode.ElideRight, int(hr.width())))

        # лайк
        liked, shuffle, rm = self._state_sig or (False, False, 0)
        acc_name = acc.name()
        lt = self._like_t
        bump = math.sin(math.pi * lt) * (1.0 - lt) * 1.7 if lt < 1.0 else 0.0
        self._named_icon(p, "like", "heart_fill" if liked else "heart", g["like"], 24, op,
                         1.0 if liked else 0.8, acc_name if liked else "#ffffff", zoom=1.0 + 0.5 * bump)
        if lt < 1.0:                                           # всплеск: кольцо и искры разлетаются от сердца
            c = g["like"].center()
            e = _ease(lt)
            p.setOpacity(op * (1.0 - lt))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(acc, 2.4 * (1.0 - lt) + 0.4))
            p.drawEllipse(c, 12 + 20 * e, 12 + 20 * e)
            p.setPen(Qt.PenStyle.NoPen)
            for k in range(8):
                ang = k * math.pi / 4 + 0.4
                rr_ = 16 + 26 * e + (4 if k % 2 else 0)
                p.setBrush(acc if k % 2 else QColor(255, 255, 255))
                d = 3.4 * (1.0 - lt) + 0.6
                p.drawEllipse(QPointF(c.x() + math.cos(ang) * rr_, c.y() + math.sin(ang) * rr_), d, d)

        # полоска времени (пока экран проявляется — её картинка, потом сам виджет) и время под ней
        if not self.prog.isVisible():
            pr = g["prog"]
            pm = QPixmap(pr.size())
            pm.fill(Qt.GlobalColor.transparent)
            self.prog.render(pm, QPoint(0, 0), QRegion(), QWidget.RenderFlag.DrawChildren)
            p.setOpacity(op)
            p.drawPixmap(pr.topLeft(), pm)
        p.setFont(ya_font(12, QFont.Weight.DemiBold))
        p.setPen(QColor(255, 255, 255))
        p.setOpacity(op * 0.66)
        tr_ = g["times"]
        p.drawText(tr_, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), _fmt(self._pos))
        if self._dur > 0:
            p.drawText(tr_, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), _fmt(self._dur))

        # управление
        self._named_icon(p, "shuffle", "shuffle", g["shuffle"], 22, op, 1.0 if shuffle else 0.7,
                         acc_name if shuffle else "#ffffff")
        self._named_icon(p, "repeat", "repeat_one" if rm == 2 else "repeat", g["repeat"], 22, op,
                         1.0 if rm else 0.7, acc_name if rm else "#ffffff")
        self._named_icon(p, "prev", "prev", g["prev"], 30, op, 0.95)
        self._named_icon(p, "next", "next", g["next"], 30, op, 0.95)
        pr = g["play"]
        hot, down = self._hover == "play", self._down == "play"
        k = 0.95 if down else (1.04 if hot else 1.0)
        pt = self._play_t
        if pt < 1.0:                                           # пуск/пауза: кнопка «отпружинивает», от неё идёт волна
            k *= 1.0 + 0.2 * math.sin(math.pi * pt) * (1.0 - pt)
        c = pr.center()
        rr = pr.width() / 2 * k
        if pt < 1.0:
            p.setOpacity(op * (1.0 - pt) * 0.7)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(255, 255, 255), 2.0))
            wave = pr.width() / 2 + 34 * _ease(pt)
            p.drawEllipse(c, wave, wave)
        p.setOpacity(op)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(c, rr, rr)
        p.setBrush(QColor(14, 14, 18))
        u = pr.width() / 70.0
        if self._playing:
            bw, bh, bg = 7.0 * u, 24.0 * u, 7.0 * u
            p.drawRoundedRect(QRectF(c.x() - bg / 2 - bw, c.y() - bh / 2, bw, bh), 2 * u, 2 * u)
            p.drawRoundedRect(QRectF(c.x() + bg / 2, c.y() - bh / 2, bw, bh), 2 * u, 2 * u)
        else:
            tri = QPainterPath()
            tri.moveTo(c.x() - 8 * u, c.y() - 13 * u)
            tri.lineTo(c.x() - 8 * u, c.y() + 13 * u)
            tri.lineTo(c.x() + 14 * u, c.y())
            tri.closeSubpath()
            p.drawPath(tri)

        # справа: текст и «Далее»
        if g["lyr"] is not None and lm < 1.0:                  # свои строки — только в «Сейчас играет»;
            self._paint_lyrics(p, g["lyr"], op * (1.0 - lm), g["compact"])   # в «Тексте» — панель текста
        else:
            self._ly_hits = []
        if lm < 1.0:
            self._paint_nexts(p, g, op * (1.0 - lm))
        box, snap = self._lyr_box, self._lyr_snap              # кнопки и панель текста проявляются / гаснут
        if box is not None and snap is not None and not box.isVisible() and self._lyr_a > 0.01:
            p.resetTransform()
            p.setOpacity(self._lyr_a)
            p.drawPixmap(box.pos(), snap)
        p.end()

    def _named_icon(self, p, name, icon, r: QRectF, size, op, alpha=1.0, color="#ffffff", zoom=1.0):
        from yamusic_theme import ya_icon
        hot, down = self._hover == name, self._down == name
        if hot or down:
            p.setOpacity(op)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 44 if down else 26))
            p.drawEllipse(r)
        p.setOpacity(op * (1.0 if hot else alpha))
        s = size * zoom * (0.9 if down else 1.0)
        c = r.center()
        ya_icon(icon, size, color).paint(p, QRectF(c.x() - s / 2, c.y() - s / 2, s, s).toRect())

    def _context_name(self) -> str:
        w = self.win
        try:
            name = w.ctx_title() if hasattr(w, "ctx_title") else ""
        except Exception:                                      # noqa: BLE001
            name = ""
        return str(name or "").replace("⁣", "").strip()
