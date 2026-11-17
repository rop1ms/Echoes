# ya_home.py
"""
Главная «Для вас»: блок «Продолжить слушать».

Плитки в два-три столбца: обложка, название, исполнитель; фон плитки подкрашен главным цветом
обложки, при наведении плитка светлеет и справа появляется кнопка «играть» в цвет оформления.
При показе страницы плитки появляются по очереди (motion.strength() == 0 — сразу).

Цвета обложек считаются в фоновом потоке (только QImage) и приходят через мост окна; обложки —
ленивым загрузчиком cover_pixmap. В потоке окна файлы не читаются.
"""
from __future__ import annotations

import threading
import time

from frameclock import FrameTimer
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

_TINT: dict = {}                       # путь обложки → QColor (главный цвет)


def recent_items(shell, n=6) -> list:
    """Что продолжить: «Мне нравится» (если есть) и последние слушанные треки коллекции."""
    from yamusic_theme import LIKED, sanitize_title
    w = shell.win
    out = []
    liked = (w.playlists.get(LIKED) or {}).get("tracks") or []
    if liked:
        out.append({"title": LIKED, "sub": f"{len(liked)} треков", "cover": "",
                    "seed": LIKED, "fn": lambda: shell.open_playlist(LIKED), "liked": True})
    hist = w.settings.get("play_history", {}) or {}
    lib = w.library
    idx = {str(t.get("path", "")): i for i, t in enumerate(lib)}
    seen = sorted(((str(v.get("last", "")), p) for p, v in hist.items()
                   if isinstance(v, dict) and v.get("last") and p in idx), reverse=True)
    picked = [p for _, p in seen[:n * 2]]
    if len(picked) < 3:                                        # истории почти нет — недавно добавленные
        picked += [str(t.get("path", "")) for t in reversed(lib[-n * 2:])]
    used = set()
    for p in picked:
        if p in used or p not in idx:
            continue
        used.add(p)
        t = lib[idx[p]]
        out.append({"title": sanitize_title(t.get("title", "") or "Без названия"),
                    "sub": t.get("artist") or "Неизвестный исполнитель", "cover": t.get("cover", ""),
                    "seed": p, "fn": lambda i=idx[p]: w._play_index(i, "library")})
        if len(out) >= n:
            break
    return out


class ContinueGrid(QWidget):
    TILE_H = 72
    GAP = 10

    def __init__(self, shell, items, parent=None):
        super().__init__(parent)
        self.shell = shell
        self.items = list(items)
        self._hover = -1
        self._down = -1
        self._t0 = None                # начало появления
        self._timer = None
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._relayout()
        self._ask_tints()

    # ── раскладка ── #

    def _cols(self) -> int:
        w = self.width()
        return 3 if w >= 860 else 2 if w >= 520 else 1

    def _relayout(self):
        cols = self._cols()
        rows = (len(self.items) + cols - 1) // cols
        self.setFixedHeight(max(1, rows * self.TILE_H + max(0, rows - 1) * self.GAP))

    def _rect(self, k: int) -> QRectF:
        cols = self._cols()
        tw = (self.width() - (cols - 1) * self.GAP) / cols
        return QRectF((k % cols) * (tw + self.GAP), (k // cols) * (self.TILE_H + self.GAP), tw, self.TILE_H)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()

    # ── появление ── #

    def showEvent(self, e):
        super().showEvent(e)
        try:
            import motion
            on = motion.strength() > 0
        except Exception:                                      # noqa: BLE001
            on = False
        if not on:
            self._t0 = None
            return
        self._t0 = time.monotonic()
        if self._timer is None:
            self._timer = FrameTimer(self)
            self._timer.setInterval(8)
            self._timer.timeout.connect(self._tick)
        self._timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        if self._timer is not None:
            self._timer.stop()
        self._t0 = None

    def _tick(self):
        if self._t0 is None or time.monotonic() - self._t0 > 0.42 + 0.05 * len(self.items):
            self._t0 = None
            self._timer.stop()
        self.update()

    def _appear(self, k: int) -> float:
        if self._t0 is None:
            return 1.0
        t = (time.monotonic() - self._t0 - 0.05 * k) / 0.34
        t = max(0.0, min(1.0, t))
        return 1.0 - (1.0 - t) ** 3

    # ── цвета обложек — в фоне ── #

    def _ask_tints(self):
        need = [it["cover"] for it in self.items if it.get("cover") and it["cover"] not in _TINT]
        if not need:
            return
        bridge = getattr(self.shell.win, "_ui_bridge", None)

        def work():
            from echo_glass import _dominant_colors
            from img_load import read_image
            got = {}
            for path in need:
                try:
                    img = read_image(path, 64)
                    if not img.isNull():
                        c = _dominant_colors(img, 1)[0]
                        h, sat, _v, _a = c.getHsvF()
                        # тёмная обложка давала почти чёрный оттенок — плитки не различались; берём сам тон, ярко
                        got[path] = (QColor.fromHsvF(h, min(1.0, max(0.55, sat * 1.2)), 0.95) if h >= 0 and sat > 0.12
                                     else QColor(200, 200, 210))
                except Exception as e:                         # noqa: BLE001
                    print("[home] tint:", e)

            def done():
                _TINT.update(got)
                if len(_TINT) > 600:
                    for key in list(_TINT)[:200]:
                        _TINT.pop(key, None)
                try:
                    self.update()
                except RuntimeError:
                    pass
            if bridge is not None:
                bridge.call.emit(done)
        threading.Thread(target=work, name="echoes-home-tint", daemon=True).start()

    # ── ввод ── #

    def _at(self, pos) -> int:
        for k in range(len(self.items)):
            if self._rect(k).contains(pos):
                return k
        return -1

    def mouseMoveEvent(self, e):
        k = self._at(e.position())
        if k != self._hover:
            self._hover = k
            self.setCursor(Qt.CursorShape.PointingHandCursor if k >= 0 else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, e):
        if self._hover != -1:
            self._hover = -1
            self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._down = self._at(e.position())
            self.update()

    def mouseReleaseEvent(self, e):
        k, self._down = self._down, -1
        self.update()
        if e.button() == Qt.MouseButton.LeftButton and k >= 0 and self._at(e.position()) == k:
            self.items[k]["fn"]()

    # ── рисование ── #

    def paintEvent(self, _):
        import ya_decor
        from ya_skin import interface_radius
        from yamusic_theme import MUTED, TEXT, cover_pixmap, liked_cover, ya_font
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        acc = ya_decor.accent()
        rad = float(max(6, min(16, interface_radius(14))))
        f1, f2 = ya_font(14, QFont.Weight.Bold), ya_font(12)
        fm1, fm2 = QFontMetrics(f1), QFontMetrics(f2)
        cs = self.TILE_H
        for k, it in enumerate(self.items):
            a = self._appear(k)
            if a <= 0.0:
                continue
            r = self._rect(k).translated(0, (1.0 - a) * 16)
            hot, down = k == self._hover, k == self._down
            if down:
                r = r.adjusted(2, 1, -2, -1)
            p.setOpacity(a)
            path = QPainterPath()
            path.addRoundedRect(r, rad, rad)
            p.fillPath(path, QColor(255, 255, 255, 30 if hot else 16))
            tint = _TINT.get(it.get("cover") or "") or (acc if it.get("liked") else None)
            if tint is not None:                               # фон плитки — в цвет обложки, гаснет вправо
                g = QLinearGradient(r.left(), 0, r.right(), 0)
                c0 = QColor(tint)
                c0.setAlpha(120 if hot else 84)
                c1 = QColor(tint)
                c1.setAlpha(26 if hot else 8)
                g.setColorAt(0.0, c0)
                g.setColorAt(1.0, c1)
                p.fillPath(path, g)
            p.save()
            p.setClipPath(path)
            if it.get("liked") and not it.get("cover"):
                pm = liked_cover(cs, 0)
            else:
                pm = cover_pixmap(it.get("cover", ""), cs, 0, seed=it.get("seed", ""), lazy=self)
            p.drawPixmap(QRectF(r.left(), r.top(), cs, cs).toRect(), pm)
            p.restore()
            if hot:                                            # кант в цвет оформления
                pen = QColor(acc)
                pen.setAlpha(150)
                p.setPen(QPen(pen, 1.2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r.adjusted(0.6, 0.6, -0.6, -0.6), rad, rad)
            tx = r.left() + cs + 14
            tw = r.right() - tx - (58 if hot else 14)
            p.setFont(f1)
            p.setPen(QColor(TEXT))
            p.drawText(QRectF(tx, r.center().y() - 21, tw, 20), int(Qt.AlignmentFlag.AlignVCenter),
                       fm1.elidedText(it["title"], Qt.TextElideMode.ElideRight, int(tw)))
            p.setFont(f2)
            p.setPen(QColor("#d0d0d0") if hot else QColor(MUTED))
            p.drawText(QRectF(tx, r.center().y() + 1, tw, 18), int(Qt.AlignmentFlag.AlignVCenter),
                       fm2.elidedText(it["sub"], Qt.TextElideMode.ElideRight, int(tw)))
            if hot:                                            # кнопка «играть»
                c = QPointF(r.right() - 32, r.center().y())
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(acc)
                p.drawEllipse(c, 19, 19)
                p.setBrush(ya_decor.on_accent(acc))
                tri = QPainterPath()
                tri.moveTo(c.x() - 5, c.y() - 8)
                tri.lineTo(c.x() - 5, c.y() + 8)
                tri.lineTo(c.x() + 9, c.y())
                tri.closeSubpath()
                p.drawPath(tri)
        p.end()
