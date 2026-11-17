"""Сборка сцены Phantom при запуске: заставка растворяется — и плеер «строится» на глазах.

Сюжет (~1.6 с): чёрный экран светлеет до фона; сверху опускается полоса; у каждой карточки слева
(обложка, плеер, виджеты) сначала прочерчивается тонкий контур, потом она слетается из кусочков —
плитки прилетают с разных сторон, доворачиваются и встают на место волной от верхнего левого угла;
колонка текста справа всплывает снизу. В конце слой растворяется, под ним — живой плеер.

Чтобы ничего не тормозило и не прыгало: настоящие виджеты не трогаем (не прячем, не двигаем). Один раз
снимаем готовый кадр окна (lay.root.grab) и фон (lay.bg.grab); слой поверх рисует фон и куски кадра, пока
они летят, а собранная карточка — это ровно её место в готовом кадре. Поэтому в конце подмены не видно.

prepare(win) — сразу после показа окна: чёрный слой закрывает плеер (под заставкой ничего не мелькнёт);
start(win) — когда заставка начала растворяться: снять кадр и собрать сцену; клик или клавиша — сразу в конец.
"""
from __future__ import annotations

import math
import random
import time

from frameclock import FrameTimer
from PyQt6.QtCore import QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QWidget

T_DARK = 0.5            # чёрный → фон
T_TOP = 0.0             # полоса сверху
T_LEFT = 0.12           # первая карточка слева
LEFT_STEP = 0.13        # следующая — через столько
TRACE = 0.34            # контур карточки прочерчивается
TILE_WAVE = 0.26        # волна плиток по карточке (от угла к углу)
TILE_FLY = 0.55         # полёт одной плитки
T_RIGHT = 0.30          # колонка текста
RIGHT_RISE = 0.7
FADE_OUT = 0.22         # слой растворяется над живым плеером
TILE = 72               # размер плитки (логические px), примерно


def _clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def _out_cubic(x):
    x = _clamp(x)
    return 1 - (1 - x) ** 3


def _out_back(x, s=1.4):
    x = _clamp(x) - 1
    return x * x * ((s + 1) * x + s) + 1


def _in_out(x):
    x = _clamp(x)
    return 3 * x * x - 2 * x * x * x


def _layout(win):
    sh = getattr(win, "_ya", None)
    return getattr(sh, "ph", None) if sh is not None else None


class _Piece:
    """Кусок готового кадра: карточка слева (плитками), полоса сверху или колонка текста."""

    def __init__(self, kind: str, rect: QRect, t0: float, radius: float = 0.0):
        self.kind, self.rect, self.t0, self.radius = kind, QRectF(rect), t0, radius
        self.tiles: list = []                                  # [(QRectF место, задержка, dx, dy, угол)]

    def make_tiles(self, rnd: random.Random):
        r = self.rect
        cols = max(2, round(r.width() / TILE))
        rows = max(2, round(r.height() / TILE))
        cw, ch = r.width() / cols, r.height() / rows
        c = r.center()
        for j in range(rows):
            for i in range(cols):
                cell = QRectF(r.left() + i * cw, r.top() + j * ch, cw, ch)
                diag = (i / max(1, cols - 1) + j / max(1, rows - 1)) / 2     # волна от верхнего левого угла
                d = TILE_WAVE * diag + rnd.uniform(0, .06)
                v = cell.center() - c
                n = math.hypot(v.x(), v.y()) or 1.0
                dist = rnd.uniform(36, 90)
                dx = v.x() / n * dist + rnd.uniform(-18, 18)
                dy = v.y() / n * dist + rnd.uniform(-18, 18) + 14
                self.tiles.append((cell, d, dx, dy, rnd.uniform(-16, 16)))

    def end(self) -> float:
        if self.kind == "card":
            return self.t0 + TRACE * .5 + TILE_WAVE + .06 + TILE_FLY
        if self.kind == "right":
            return self.t0 + RIGHT_RISE
        return self.t0 + .4


class PhBuildIn(QWidget):
    """Слой поверх раскладки Phantom: до start() — чёрный, потом собирает сцену и растворяется."""

    def __init__(self, lay, parent):
        super().__init__(parent)
        self.lay = lay
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._frame: QPixmap | None = None                     # готовый кадр окна
        self._bg: QPixmap | None = None                        # только фон
        self._pieces: list[_Piece] = []
        self._t0 = None
        self._skip_at = None
        self._end = 1.0
        self._timer = FrameTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._frame_tick)
        self.setGeometry(parent.rect())
        self.show()
        self.raise_()

    # ── запуск ── #
    def start(self):
        if self._t0 is not None:
            return
        lay = self.lay
        root = self.parentWidget()
        self.setGeometry(root.rect())
        self.hide()                                            # снять кадр без себя
        try:
            self._frame = root.grab()
            self._bg = lay.bg.grab()
        except Exception as e:                                 # noqa: BLE001
            print("[ph intro] grab:", e)
            self._frame = None
        self.show()
        self.raise_()
        if self._frame is None or self._frame.isNull():
            self._finish()
            return
        rnd = random.Random(7)
        top = lay.top.geometry()
        self._pieces.append(_Piece("top", top, T_TOP))
        rad = 22.0
        for i, it in enumerate(lay.left_items):
            w = lay.block_widget(it)
            if not w.isVisible():
                continue
            pc = _Piece("card", w.geometry(), T_LEFT + i * LEFT_STEP, rad)
            pc.make_tiles(rnd)
            self._pieces.append(pc)
        if lay.right.isVisible():
            self._pieces.append(_Piece("right", lay.right.geometry(), T_RIGHT))
        self._end = max([T_DARK] + [p.end() for p in self._pieces])
        self._t0 = time.monotonic()
        self.setFocus()
        self._timer.start()
        self.update()

    def _now(self) -> float:
        if self._t0 is None:
            return 0.0
        t = time.monotonic() - self._t0
        if self._skip_at is not None:                          # пропуск — сразу к растворению
            t = self._end + (t - self._skip_at)
        return t

    def skip(self):
        if self._t0 is not None and self._skip_at is None:
            self._skip_at = time.monotonic() - self._t0

    def mousePressEvent(self, e):
        self.skip()

    def keyPressEvent(self, e):
        self.skip()

    def _frame_tick(self):
        if self._now() >= self._end + FADE_OUT:
            self._finish()
            return
        self.update()

    def _finish(self):
        self._timer.stop()
        self.hide()
        self.deleteLater()
        if getattr(self.lay, "_build_in", None) is self:
            self.lay._build_in = None

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._t0 is not None and self.size() != self.parentWidget().size():
            self.skip()                                        # окно поменяли посреди сборки — к концу

    # ── рисование ── #
    def paintEvent(self, e):
        p = QPainter(self)
        try:
            if self._t0 is None:                               # ждём заставку: просто чёрный
                p.fillRect(self.rect(), Qt.GlobalColor.black)
                return
            t = self._now()
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            out = _in_out((t - self._end) / FADE_OUT)
            p.setOpacity(1.0 - out)
            if t >= self._end:                                 # всё на местах — готовый кадр растворяется
                if self.testAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent):
                    self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
                p.drawPixmap(QRectF(self.rect()), self._frame, QRectF(self._frame.rect()))
                return
            if self._bg is not None and not self._bg.isNull():
                p.drawPixmap(QRectF(self.lay.bg.geometry()), self._bg, QRectF(self._bg.rect()))
            else:
                p.fillRect(self.rect(), Qt.GlobalColor.black)
            for pc in self._pieces:
                getattr(self, "_draw_" + pc.kind)(p, pc, t)
            dark = 1.0 - _out_cubic(t / T_DARK)                # чёрная пелена сходит
            if dark > 0:
                p.setOpacity(dark * (1.0 - out))
                p.fillRect(self.rect(), Qt.GlobalColor.black)
        finally:
            p.end()

    def _src(self, r: QRectF) -> QRectF:
        k = self._frame.devicePixelRatio()
        return QRectF(r.x() * k, r.y() * k, r.width() * k, r.height() * k)

    def _draw_top(self, p: QPainter, pc: _Piece, t: float):
        k = _out_cubic((t - pc.t0) / .4)
        if k <= 0:
            return
        p.save()
        p.setOpacity(p.opacity() * k)
        r = pc.rect.translated(0, -14 * (1 - k))
        p.drawPixmap(r, self._frame, self._src(pc.rect))
        p.restore()

    def _draw_right(self, p: QPainter, pc: _Piece, t: float):
        k = _out_cubic((t - pc.t0) / RIGHT_RISE)
        if k <= 0:
            return
        p.save()
        p.setOpacity(p.opacity() * k)
        r = pc.rect.translated(0, 34 * (1 - k))
        p.drawPixmap(r, self._frame, self._src(pc.rect))
        p.restore()

    def _draw_card(self, p: QPainter, pc: _Piece, t: float):
        lt = t - pc.t0
        if lt <= 0:
            return
        r = pc.rect
        base = p.opacity()
        land = TRACE * .5                                      # плитки летят, пока контур дочерчивается
        done = all(lt >= land + d + TILE_FLY for _c, d, *_ in pc.tiles)
        if done:
            p.drawPixmap(r, self._frame, self._src(r))         # собрана — одним куском, без швов
        else:
            for cell, d, dx, dy, ang in pc.tiles:
                k = (lt - land - d) / TILE_FLY
                if k <= 0:
                    continue
                if k >= 1:
                    p.setOpacity(base)
                    p.drawPixmap(cell, self._frame, self._src(cell))
                    continue
                m = _out_back(k)
                a = _out_cubic(k * 1.6)
                s = .72 + .28 * m
                c = cell.center()
                p.save()
                p.setOpacity(base * a)
                p.translate(c.x() + dx * (1 - m), c.y() + dy * (1 - m))
                p.rotate(ang * (1 - m))
                p.scale(s, s)
                p.drawPixmap(QRectF(-cell.width() / 2, -cell.height() / 2, cell.width(), cell.height()),
                             self._frame, self._src(cell))
                p.restore()
        # контур: прочерчивается по периметру, потом гаснет, когда карточка собрана
        tr = _out_cubic(lt / TRACE)
        fade = 1.0 - _out_cubic((lt - (pc.end() - pc.t0) + .25) / .3)
        if tr > 0 and fade > 0:
            path = QPainterPath()
            path.addRoundedRect(r.adjusted(.5, .5, -.5, -.5), pc.radius, pc.radius)
            per = 2 * (r.width() + r.height())
            pen = QPen(QColor(255, 255, 255, int(150 * fade)), 1.2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            seg = max(.01, per * tr / 1.2)                     # длина прочерченного, в толщинах пера
            pen.setDashPattern([seg, per])
            p.save()
            p.setOpacity(base)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            p.restore()
        p.setOpacity(base)


def _enabled(win) -> bool:
    try:
        import ph_style as ph
        if ph.motion_reduced():
            return False
    except Exception:                                          # noqa: BLE001
        pass
    lay = _layout(win)
    return lay is not None and not lay.overlay.isVisible() and not lay.edit.isVisible()


def prepare(win) -> bool:
    """Закрыть раскладку чёрным слоем до start(). False — сборки не будет (не Phantom, меньше движения)."""
    try:
        if not _enabled(win):
            return False
        lay = _layout(win)
        old = getattr(lay, "_build_in", None)
        if old is not None:
            return True
        lay._build_in = PhBuildIn(lay, lay.root)
        return True
    except Exception as e:                                     # noqa: BLE001
        print("[ph intro] prepare:", e)
        return False


def start(win):
    """Заставка растворяется — собрать сцену."""
    lay = _layout(win)
    bi = getattr(lay, "_build_in", None) if lay is not None else None
    if bi is None:
        return
    try:
        bi.start()
    except Exception as e:                                     # noqa: BLE001
        print("[ph intro] start:", e)
        bi._finish()


def cancel(win):
    lay = _layout(win)
    bi = getattr(lay, "_build_in", None) if lay is not None else None
    if bi is not None:
        bi._finish()
