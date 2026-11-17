"""Общие детали страниц Echoes в виде Phantom: плитка с обложкой, ряд с прокруткой вбок, сетка, заголовок секции,
пустое состояние и мерцающая заглушка загрузки.

В Phantom ими заменяются прежние Card / card_row / card_grid / section_title (yamusic_theme зовёт phantom_* ниже),
поэтому «Для вас», «Альбомы», страница исполнителя, поиск и другие страницы выглядят одинаково. Прежние детали
и лента карточек на C++ остаются для прежнего вида Echoes.
"""
from __future__ import annotations

import math
import time

from PyQt6.QtCore import (QEasingCurve, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer, QVariantAnimation,
                          pyqtSignal)
from PyQt6.QtGui import QColor, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout,
                             QWidget)

import ph_style as ph
import ph_widgets as pw

LIFT = 4                                                       # на сколько px плитка приподнимается при наведении


def on() -> bool:
    try:
        import ya_skin
        return bool(ya_skin.PHANTOM_ON)
    except Exception:                                          # noqa: BLE001
        return False


# ══════════════════════════════════════════════════════════════════════════ #
#  Плитка: обложка (квадрат / круг / подборка) + подпись
# ══════════════════════════════════════════════════════════════════════════ #

def make_card_class():
    """PhCard наследует прежнюю Card (тот же конструктор, clicked, cover, «перелёт» обложки) — создаётся при
    первом вызове, чтобы не тянуть yamusic_theme при импорте."""
    global PhCard
    if PhCard is not None:
        return PhCard
    from yamusic_theme import Card, cover_pixmap

    class _PhCard(Card):
        """Плитка Phantom: скругление 14, при наведении приподнимается с тенью, белая кнопка «играть»
        проявляется и чуть растёт; подпись Inter 13/600, ниже серым."""
        hovered = pyqtSignal()

        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._hk = 0.0
            self._hanim = QVariantAnimation(self)
            self._hanim.setEasingCurve(ph.ease_out())
            self._hanim.valueChanged.connect(self._on_hk)
            if not self.circle:
                self._rad = float(ph.px(14)) * self.size_ / 150 + 4
            self._resize_fixed()

        def _resize_fixed(self):
            self.setFixedSize(self.size_, self.size_ + LIFT + (46 if self.subtitle else 30))

        def set_size(self, s: int):
            s = max(60, int(s))
            if s == self.size_:
                return
            self.size_ = s
            if not self.circle:
                self._rad = float(ph.px(14)) * s / 150 + 4
            self._resize_fixed()
            self.update()

        def _on_hk(self, v):
            self._hk = float(v)
            self.update()

        def enterEvent(self, e):
            self._hover = True
            self.hovered.emit()
            self._anim_to(1.0, 170)

        def leaveEvent(self, e):
            self._hover = False
            self._anim_to(0.0, 240)

        def _anim_to(self, v, ms):
            d = ph.duration(ms)
            self._hanim.stop()
            if d <= 0:
                self._on_hk(v)
                return
            self._hanim.setDuration(d)
            self._hanim.setStartValue(self._hk)
            self._hanim.setEndValue(v)
            self._hanim.start()

        def paintEvent(self, e):
            p = QPainter(self)
            try:
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                if self._appear < 1.0:                         # каскад появления (ya_decor)
                    p.setOpacity(self._appear)
                    p.translate(0, (1.0 - self._appear) * 12)
                s, k = self.size_, self._hk
                r = QRectF(0, LIFT - LIFT * k, s, s)
                path = QPainterPath()
                if self.circle:
                    path.addEllipse(r)
                else:
                    path.addRoundedRect(r, self._rad, self._rad)
                if k > .01:                                    # тень под приподнятой плиткой
                    p.save()
                    p.setOpacity(p.opacity() * k)
                    ph.paint_shadow(p, r, "card", s / 2 if self.circle else self._rad)
                    p.restore()
                if self.mix:
                    self._paint_mix(p, r, path)
                else:
                    pm = cover_pixmap(self.cover, s, self._rad, seed=self.seed, circle=self.circle, lazy=self)
                    p.drawPixmap(r, pm, QRectF(pm.rect()))
                p.setPen(QPen(ph.qcolor(ph.LINE_1), 1.0))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)
                if k > .01:
                    p.fillPath(path, QColor(0, 0, 0, int(60 * k)))
                    br = max(14.0, s * .12)
                    c = r.center() if self.circle else QPointF(r.right() - br - ph.px(10), r.bottom() - br - ph.px(10))
                    sc = .8 + .2 * k
                    p.save()
                    p.setOpacity(p.opacity() * k)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(255, 255, 255, 245))
                    p.drawEllipse(c, br * sc, br * sc)
                    ic = ph.icon_pixmap("play", int(br * .9), (10, 10, 10, 1.0), 2.2, fill=(10, 10, 10, 1.0))
                    w = br * .9 * sc
                    p.drawPixmap(QRectF(c.x() - w / 2 + br * .06, c.y() - w / 2, w, w), ic, QRectF(ic.rect()))
                    p.restore()
                al = Qt.AlignmentFlag.AlignHCenter if self.circle else Qt.AlignmentFlag.AlignLeft
                f = ph.font(ph.TEXT_MD, 600)
                p.setFont(f)
                p.setPen(ph.qcolor(ph.TEXT_PRIMARY))
                ty = LIFT + s + ph.px(8)
                p.drawText(QRectF(0, ty, s, ph.px(18)), al | Qt.AlignmentFlag.AlignVCenter,
                           QFontMetrics(f).elidedText(self.title, Qt.TextElideMode.ElideRight, s))
                if self.subtitle:
                    f2 = ph.font(ph.TEXT_SM)
                    p.setFont(f2)
                    p.setPen(ph.qcolor(ph.TEXT_TERTIARY))
                    p.drawText(QRectF(0, ty + ph.px(19), s, ph.px(16)), al | Qt.AlignmentFlag.AlignVCenter,
                               QFontMetrics(f2).elidedText(self.subtitle, Qt.TextElideMode.ElideRight, s))
            finally:
                p.end()

        def _paint_mix(self, p, r, path):
            """Подборка: обложки треков коллажем на тёмном стекле, название крупно внизу."""
            p.save()
            p.setClipPath(path)
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, ph.tone(46))
            g.setColorAt(1, QColor(10, 10, 10))
            p.fillRect(r, g)
            covs = self.mix_covers[:4]
            if covs:
                n = len(covs)
                cols = 2 if n >= 2 else 1
                rows = 2 if n >= 3 else 1
                cw, chh = r.width() / cols, r.height() / rows
                for i, cv in enumerate(covs[: cols * rows]):
                    pm = cover_pixmap(cv, int(max(cw, chh)), 0, lazy=self)
                    cell = QRectF(r.x() + (i % cols) * cw, r.y() + (i // cols) * chh, cw, chh)
                    p.drawPixmap(cell, pm, QRectF(pm.rect()))
                gg = QLinearGradient(0, r.top(), 0, r.bottom())
                gg.setColorAt(.5, QColor(0, 0, 0, 0))
                gg.setColorAt(1, QColor(0, 0, 0, 150))
                p.fillRect(r, gg)
            else:
                p.setPen(QPen(ph.white(.07), 1.0))
                m = r.width()
                for i, kk in enumerate((.18, .3, .44, .6)):
                    p.drawEllipse(QPointF(r.x() + m * .62 + i * 3, r.y() + m * .36), m * kk, m * kk)
            ic = ph.icon_pixmap("waves-horizontal", int(self.size_ * .16), ph.TEXT_PRIMARY, 2.0)
            w = self.size_ * .16                               # название — подписью под плиткой, здесь значок подборки
            p.drawPixmap(QRectF(r.x() + ph.px(12), r.bottom() - w - ph.px(12), w, w), ic, QRectF(ic.rect()))
            p.restore()

    PhCard = _PhCard
    return PhCard


PhCard = None


# ══════════════════════════════════════════════════════════════════════════ #
#  Ряд плиток с прокруткой вбок: стрелки ‹ › по краям при наведении, плавная прокрутка
# ══════════════════════════════════════════════════════════════════════════ #

class PhRow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.sa = QScrollArea(self)
        self.sa.setWidgetResizable(True)
        self.sa.setFrameShape(QFrame.Shape.NoFrame)
        self.sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sa.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sa.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self.sa.viewport().setAutoFillBackground(False)
        self.inner = QWidget()
        self.inner.setObjectName("YaPageInner")
        self.inner.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.lay = QHBoxLayout(self.inner)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(ph.px(16))
        self.lay.addStretch(1)
        self.sa.setWidget(self.inner)
        self.items = []
        self.b_l = pw.icon_button("chevron-left", "surface", "md", 16, "Назад", parent=self)
        self.b_r = pw.icon_button("chevron-right", "surface", "md", 16, "Дальше", parent=self)
        self.b_l.clicked.connect(lambda: self.scroll_by(-1))
        self.b_r.clicked.connect(lambda: self.scroll_by(1))
        for b in (self.b_l, self.b_r):
            b.hide()
        self._anim = QPropertyAnimation(self.sa.horizontalScrollBar(), b"value", self)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.sa.horizontalScrollBar().valueChanged.connect(lambda _v: self._sync_arrows())
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    @property
    def widget_(self):
        return self

    def clear(self):
        while self.lay.count() > 1:
            it = self.lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.items = []

    def add(self, w):
        self.lay.insertWidget(self.lay.count() - 1, w)
        self.items.append(w)
        self.setFixedHeight(max(self.height() if self.items[:-1] else 0, w.height() + 4))

    def card(self, *a, **kw):
        c = make_card_class()(*a, **kw)
        self.add(c)
        return c

    def relabel(self):
        pass

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.sa.setGeometry(self.rect())
        self._place_arrows()

    def _place_arrows(self):
        h = self.items[0].size_ if self.items and hasattr(self.items[0], "size_") else self.height() - 40
        y = int(LIFT + h / 2 - self.b_l.height() / 2)
        self.b_l.move(ph.px(6), y)
        self.b_r.move(self.width() - self.b_r.width() - ph.px(6), y)

    def _sync_arrows(self):
        sb = self.sa.horizontalScrollBar()
        hov = self.underMouse()
        self.b_l.setVisible(hov and sb.value() > 0)
        self.b_r.setVisible(hov and sb.value() < sb.maximum())

    def enterEvent(self, e):
        self._place_arrows()
        self._sync_arrows()

    def leaveEvent(self, e):
        self.b_l.hide()
        self.b_r.hide()

    def scroll_by(self, d: int):
        sb = self.sa.horizontalScrollBar()
        start = self._anim.endValue() if self._anim.state() == QPropertyAnimation.State.Running else sb.value()
        to = max(0, min(sb.maximum(), int(start + d * self.width() * .8)))
        dur = ph.duration(420)
        self._anim.stop()
        if dur <= 0:
            sb.setValue(to)
            return
        self._anim.setDuration(dur)
        self._anim.setStartValue(sb.value())
        self._anim.setEndValue(to)
        self._anim.start()

    def wheelEvent(self, e):
        dx = e.angleDelta().x()
        dy = e.angleDelta().y()
        if dx or (e.modifiers() & Qt.KeyboardModifier.ShiftModifier and dy):   # тачпад вбок / Shift+колесо
            sb = self.sa.horizontalScrollBar()
            sb.setValue(sb.value() - (dx or dy))
            e.accept()
            return
        e.ignore()                                             # обычное колесо — странице


# ══════════════════════════════════════════════════════════════════════════ #
#  Сетка плиток: столбцы по ширине, плитки растягиваются, чтобы заполнить ряд без дыры справа
# ══════════════════════════════════════════════════════════════════════════ #

class PhGrid(QScrollArea):
    def __init__(self, min_size: int = 150, parent=None):
        super().__init__(parent)
        self.min_size = min_size
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self.inner = QWidget()
        self.inner.setObjectName("YaPage")
        self.grid = QGridLayout(self.inner)
        self.grid.setContentsMargins(0, ph.px(6), ph.px(6), ph.px(6))
        self.grid.setHorizontalSpacing(ph.px(18))
        self.grid.setVerticalSpacing(ph.px(14))
        self.grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setWidget(self.inner)
        self.cards = []
        self._pending = []
        self._key = None

    @property
    def widget_(self):
        return self

    @property
    def items(self):
        return self.cards

    def clear(self):
        self._pending = []

    def card(self, *a, **kw):
        c = make_card_class()(*a, **kw)
        self._pending.append(c)
        return c

    def done(self):
        self.set_cards(self._pending)
        self._pending = []

    def relabel(self):
        pass

    def set_cards(self, cards):
        for c in self.cards:
            c.setParent(None)
            c.deleteLater()
        self.cards = list(cards)
        self._key = None
        self._relayout()
        self.verticalScrollBar().setValue(0)

    def _relayout(self):
        if not self.cards:
            return
        W = max(1, self.viewport().width() - ph.px(6))
        gap = self.grid.horizontalSpacing()
        cols = max(1, (W + gap) // (self.min_size + gap))
        size = max(self.min_size, (W - gap * (cols - 1)) // cols)
        key = (cols, size, len(self.cards))
        if key == self._key:
            return
        self._key = key
        for c in self.cards:
            self.grid.removeWidget(c)
        for i, c in enumerate(self.cards):
            if hasattr(c, "set_size"):
                c.set_size(size)
            self.grid.addWidget(c, i // cols, i % cols)
            c.show()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()


# ══════════════════════════════════════════════════════════════════════════ #
#  Заголовок секции, пустое состояние, мерцающая заглушка
# ══════════════════════════════════════════════════════════════════════════ #

def section_title(text: str, on_more=None) -> QWidget:
    w = QWidget()
    w.setObjectName("YaPageInner")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, ph.px(22), 0, ph.px(10))
    lay.setSpacing(ph.px(8))
    lb = pw.label(text, "PhTitle", font=ph.font(ph.TEXT_LG + 1, 650, -.01))
    lay.addWidget(lb)
    lay.addStretch(1)
    if on_more is not None:
        b = pw.text_button("Все", "ghost", icon="chevron-right")
        b.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        b.clicked.connect(on_more)
        lay.addWidget(b)
    return w


class Empty(QWidget):
    """Пустое состояние: значок в круге, заголовок, пояснение и (если есть) кнопка."""

    def __init__(self, icon: str, title: str, text: str = "", action: str = "", on_action=None, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, ph.px(28), 0, ph.px(28))
        v.setSpacing(ph.px(8))
        v.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        ic = QLabel()
        ic.setFixedSize(ph.px(52), ph.px(52))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic.setPixmap(ph.icon_pixmap(icon, 22, ph.TEXT_SECONDARY))
        ic.setStyleSheet(f"background:{ph.css((255, 255, 255, .05))};border:1px solid {ph.css(ph.LINE_2)};"
                         f"border-radius:{ph.px(26)}px;")
        v.addWidget(ic, 0, Qt.AlignmentFlag.AlignHCenter)
        t = pw.label(title, "PhTitle", font=ph.font(ph.TEXT_BASE + 1, 600))
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(t)
        if text:
            s = pw.label(text, "PhSub", font=ph.font(ph.TEXT_SM))
            s.setAlignment(Qt.AlignmentFlag.AlignCenter)
            s.setWordWrap(True)
            s.setMaximumWidth(ph.px(420))
            v.addWidget(s, 0, Qt.AlignmentFlag.AlignHCenter)
        if action and on_action is not None:
            b = pw.text_button(action, "secondary")
            b.clicked.connect(on_action)
            v.addWidget(b, 0, Qt.AlignmentFlag.AlignHCenter)


class Skeleton(QWidget):
    """Мерцающие силуэты плиток, пока грузится: по ним бежит мягкий блик (20 к/с, только пока видно)."""

    def __init__(self, count: int = 6, size: int = 150, circle: bool = False, parent=None):
        super().__init__(parent)
        self.count, self.size_, self.circle = count, size, circle
        self.setFixedHeight(size + LIFT + 46)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._t0 = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self.update)

    def showEvent(self, e):
        self._timer.start()

    def hideEvent(self, e):
        self._timer.stop()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = (time.monotonic() - self._t0) % 1.6 / 1.6
        gap = ph.px(16)
        s = self.size_
        for i in range(self.count):
            x = i * (s + gap)
            if x > self.width():
                break
            ph_ = (t - i * .08) % 1.0
            a = .05 + .05 * (0.5 + 0.5 * math.sin(ph_ * 2 * math.pi))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ph.white(a))
            r = QRectF(x, LIFT, s, s)
            if self.circle:
                p.drawEllipse(r)
            else:
                p.drawRoundedRect(r, ph.px(14), ph.px(14))
            p.drawRoundedRect(QRectF(x, LIFT + s + ph.px(10), s * .7, ph.px(10)), 5, 5)
            p.drawRoundedRect(QRectF(x, LIFT + s + ph.px(28), s * .45, ph.px(9)), 4, 4)
        p.end()


def size_hint_card(size: int, sub: bool = True) -> QSize:
    return QSize(size, size + LIFT + (46 if sub else 30))


# ══════════════════════════════════════════════════════════════════════════ #
#  Витрина «Для вас»: большая «Моя волна» слева и две карточки-подборки справа
# ══════════════════════════════════════════════════════════════════════════ #

class Pick(QWidget):
    """Карточка витрины: размытая обложка во всю карточку, кикер, название, подпись, белая кнопка «играть».
    При наведении светлеет и кнопка чуть растёт."""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.kick = self.title = self.sub = ""
        self.cover = ""
        self._bg, self._bg_k = None, None
        self._hk = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setEasingCurve(ph.ease_out())
        self._anim.valueChanged.connect(self._on_hk)

    def set_data(self, kick: str, title: str, sub: str, cover: str):
        self.kick, self.title, self.sub, self.cover = kick, title, sub, cover or ""
        self._bg_k = None
        self.update()

    def _on_hk(self, v):
        self._hk = float(v)
        self.update()

    def enterEvent(self, e):
        self._go(1.0, 170)

    def leaveEvent(self, e):
        self._go(0.0, 240)

    def _go(self, v, ms):
        d = ph.duration(ms)
        self._anim.stop()
        if d <= 0:
            self._on_hk(v)
            return
        self._anim.setDuration(d)
        self._anim.setStartValue(self._hk)
        self._anim.setEndValue(v)
        self._anim.start()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def _background(self):
        W, H = self.width(), self.height()
        dpr = self.devicePixelRatioF() or 1.0
        key = (W, H, dpr, self.cover)
        if key == self._bg_k and self._bg is not None:
            return self._bg
        from PyQt6.QtGui import QPixmap
        pm = QPixmap(max(1, int(W * dpr)), max(1, int(H * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0, 0, W, H)
        rad = float(ph.px(18))
        q.setClipPath(ph.surface_path(r, rad))
        if self.cover:
            import blur_fx
            q.drawImage(r, blur_fx.blurred_cover(self.cover, max(8, int(W * dpr / 3)), max(8, int(H * dpr / 3)),
                                                 8.0, dim=.38, sat=1.15))
            from yamusic_theme import cover_pixmap               # сама обложка — справа, чуть повёрнута
            s = H * .78
            cp = cover_pixmap(self.cover, int(s), 10)
            q.save()
            q.translate(W - s * .62, H * .5)
            q.rotate(-8)
            q.setOpacity(.92)
            q.drawPixmap(QRectF(-s / 2, -s / 2, s, s), cp, QRectF(cp.rect()))
            q.restore()
        else:
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, ph.tone(40))
            g.setColorAt(1, QColor(10, 10, 10))
            q.fillRect(r, g)
        g = QLinearGradient(0, 0, W, 0)                          # слева темнее — под текст
        g.setColorAt(0, QColor(0, 0, 0, 170))
        g.setColorAt(.65, QColor(0, 0, 0, 40))
        g.setColorAt(1, QColor(0, 0, 0, 0))
        q.fillRect(r, g)
        q.end()
        self._bg, self._bg_k = pm, key
        return pm

    def paintEvent(self, e):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            W, H = self.width(), self.height()
            r = QRectF(0, 0, W, H)
            rad = float(ph.px(18))
            p.drawPixmap(0, 0, self._background())
            if self._hk > .01:
                p.fillPath(ph.surface_path(r, rad), ph.white(.05 * self._hk))
            p.setPen(QPen(ph.qcolor(ph.LINE_2), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), rad, rad)
            pad = ph.px(18)
            p.setFont(ph.kicker_font())
            p.setPen(ph.qcolor(ph.TEXT_SECONDARY))
            fm = QFontMetrics(p.font())
            p.drawText(QPointF(pad, pad + fm.ascent()), self.kick.upper())
            f = ph.font(ph.TEXT_XL, 650, -.02)
            p.setFont(f)
            p.setPen(ph.qcolor(ph.TEXT_PRIMARY))
            fm = QFontMetrics(f)
            tw = int(W * .58)
            p.drawText(QRectF(pad, H - pad - fm.height() - ph.px(18), tw, fm.height()), Qt.AlignmentFlag.AlignLeft,
                       fm.elidedText(self.title, Qt.TextElideMode.ElideRight, tw))
            f2 = ph.font(ph.TEXT_SM, 500)
            p.setFont(f2)
            p.setPen(ph.qcolor(ph.TEXT_SECONDARY))
            fm2 = QFontMetrics(f2)
            p.drawText(QRectF(pad, H - pad - ph.px(16), tw, ph.px(16)), Qt.AlignmentFlag.AlignLeft,
                       fm2.elidedText(self.sub, Qt.TextElideMode.ElideRight, tw))
            br = ph.px(19) * (1 + .1 * self._hk)                     # кнопка «играть»
            c = QPointF(W - pad - ph.px(19), H - pad - ph.px(19))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 240))
            p.drawEllipse(c, br, br)
            ic = ph.icon_pixmap("play", int(br), (10, 10, 10, 1.0), 2.2, fill=(10, 10, 10, 1.0))
            p.drawPixmap(QRectF(c.x() - br / 2 + 1, c.y() - br / 2, br, br), ic, QRectF(ic.rect()))
        finally:
            p.end()


class Showcase(QWidget):
    """Верх «Для вас»: hero (баннер «Моя волна») слева, справа две Pick одна над другой. Живёт между пересборками
    страницы — баннер с туманностью на видеокарте не пересоздаётся."""

    def __init__(self, hero: QWidget, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.hero = hero
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(ph.px(16))
        h.addWidget(hero, 3)
        col = QVBoxLayout()
        col.setSpacing(ph.px(14))
        self.a, self.b = Pick(), Pick()
        col.addWidget(self.a, 1)
        col.addWidget(self.b, 1)
        h.addLayout(col, 2)

    def set_height(self, h: int):
        self.setFixedHeight(h)
        self.hero.setFixedHeight(h)


class BestMatch(QWidget):
    """«Лучшее совпадение» в поиске: крупная карточка — обложка (у исполнителя кружком), что это, название,
    подпись, белая кнопка «играть». clicked — открыть, play — включить."""
    clicked = pyqtSignal()
    play = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedHeight(ph.px(150))
        self.kind = self.title = self.sub = self.cover = ""
        self.circle = False
        self._hk = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setEasingCurve(ph.ease_out())
        self._anim.valueChanged.connect(self._on_hk)

    def _on_hk(self, v):
        self._hk = float(v)
        self.update()

    def set_data(self, kind: str, title: str, sub: str, cover: str, circle: bool = False):
        self.kind, self.title, self.sub, self.cover, self.circle = kind, title, sub, cover or "", circle
        self.update()

    def _play_rect(self) -> QRectF:
        s = ph.px(46)
        return QRectF(self.width() - s - ph.px(22), (self.height() - s) / 2, s, s)

    def enterEvent(self, e):
        self._go(1.0, 170)

    def leaveEvent(self, e):
        self._go(0.0, 240)

    def _go(self, v, ms):
        d = ph.duration(ms)
        self._anim.stop()
        if d <= 0:
            self._on_hk(v)
            return
        self._anim.setDuration(d)
        self._anim.setStartValue(self._hk)
        self._anim.setEndValue(v)
        self._anim.start()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or not self.rect().contains(e.position().toPoint()):
            return
        if self._play_rect().adjusted(-6, -6, 6, 6).contains(e.position()):
            self.play.emit()
        else:
            self.clicked.emit()

    def paintEvent(self, e):
        from yamusic_theme import cover_pixmap
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            W, H = self.width(), self.height()
            r = QRectF(0, 0, W, H)
            ph.paint_surface(p, r, "card", float(ph.px(18)))
            if self._hk > .01:
                p.fillPath(ph.surface_path(r, float(ph.px(18))), ph.white(.035 * self._hk))
            pad = ph.px(18)
            s = H - 2 * pad
            cr = QRectF(pad, pad, s, s)
            pm = cover_pixmap(self.cover, int(s), s / 2 if self.circle else 10, seed=self.title, circle=self.circle,
                              lazy=self)
            p.drawPixmap(cr, pm, QRectF(pm.rect()))
            x = pad + s + ph.px(20)
            tw = int(self._play_rect().left() - x - ph.px(12))
            p.setFont(ph.kicker_font())
            p.setPen(ph.qcolor(ph.TEXT_TERTIARY))
            fm = QFontMetrics(p.font())
            p.drawText(QPointF(x, pad + ph.px(14) + fm.ascent()), "ЛУЧШЕЕ СОВПАДЕНИЕ  ·  " + self.kind.upper())
            f = ph.font(ph.TEXT_2XL, 650, -.02)
            p.setFont(f)
            p.setPen(ph.qcolor(ph.TEXT_PRIMARY))
            fm = QFontMetrics(f)
            p.drawText(QRectF(x, H / 2 - fm.height() / 2 + ph.px(2), tw, fm.height()), Qt.AlignmentFlag.AlignLeft,
                       fm.elidedText(self.title, Qt.TextElideMode.ElideRight, max(20, tw)))
            f2 = ph.font(ph.TEXT_SM, 500)
            p.setFont(f2)
            p.setPen(ph.qcolor(ph.TEXT_SECONDARY))
            fm2 = QFontMetrics(f2)
            p.drawText(QRectF(x, H - pad - ph.px(30), tw, ph.px(18)), Qt.AlignmentFlag.AlignLeft,
                       fm2.elidedText(self.sub, Qt.TextElideMode.ElideRight, max(20, tw)))
            pr = self._play_rect()
            sc = 1 + .08 * self._hk
            c = pr.center()
            rad = pr.width() / 2 * sc
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 245))
            p.drawEllipse(c, rad, rad)
            ic = ph.icon_pixmap("play", int(rad), (10, 10, 10, 1.0), 2.2, fill=(10, 10, 10, 1.0))
            p.drawPixmap(QRectF(c.x() - rad / 2 + 1.5, c.y() - rad / 2, rad, rad), ic, QRectF(ic.rect()))
        finally:
            p.end()
