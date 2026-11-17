"""Движение в виде Phantom для всех кнопок окна (и новых, и прежних Echoes).

Наведение — мягкая подсветка проявляется за 160 мс и гаснет за 240 мс (в таблице стилей у кнопок Phantom
фон при наведении больше не прыгает); нажатие — от точки щелчка расходится круг и гаснет (на белых кнопках —
тёмный). Всё рисует прозрачный для мыши слой поверх кнопки; он есть только у кнопок, на которые навели, и
перерисовывается только пока идёт анимация. «Уменьшенное движение» в настройках Phantom — без анимаций.
"""
from __future__ import annotations

import math
import re
import time

from PyQt6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, QVariantAnimation
from PyQt6.QtGui import QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import QAbstractButton, QApplication, QWidget

import ph_style as ph

LIGHT = {"PhPrimary", "PhIconSolid", "AccentBtn", "YaYellow", "NetPrimary", "PrimaryBtn"}
SKIP = {"PhWindowClose", "PhWindow"}                  # кнопки окна — своя подсветка


def _radius(b: QWidget) -> float:
    h, w = b.height(), b.width()
    name = b.objectName()
    if name.startswith("PhIcon") or name in ("YaIcon", "PhWindow") or abs(w - h) <= 2:
        return min(w, h) / 2
    return min(h / 2, float(ph.px(16)))


class _Glow(QWidget):
    def __init__(self, btn: QAbstractButton):
        super().__init__(btn)
        self.btn = btn
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.light = btn.objectName() in LIGHT
        self.hover = 0.0
        self.ripples: list = []                            # [(точка, t0)]
        self.anim = QVariantAnimation(self)
        self.anim.setEasingCurve(ph.ease_out())
        self.anim.valueChanged.connect(self._on_hover)
        self.rip = QVariantAnimation(self)
        self.rip.setStartValue(0.0)
        self.rip.setEndValue(1.0)
        self.rip.setDuration(460)
        self.rip.valueChanged.connect(lambda _v: self.update())
        self.rip.finished.connect(self._rip_done)
        self.setGeometry(btn.rect())
        self.show()
        self.raise_()

    def _on_hover(self, v):
        self.hover = float(v)
        self.update()

    def to_hover(self, on: bool):
        d = ph.duration(160 if on else 240)
        self.anim.stop()
        if d <= 0:
            self._on_hover(1.0 if on else 0.0)
            return
        self.anim.setDuration(d)
        self.anim.setStartValue(self.hover)
        self.anim.setEndValue(1.0 if on else 0.0)
        self.anim.start()

    def ripple(self, pos: QPointF):
        if ph.duration(460) <= 0:
            return
        self.ripples = [r for r in self.ripples if time.monotonic() - r[1] < .46][-2:]
        self.ripples.append((pos, time.monotonic()))
        self.rip.stop()
        self.rip.start()

    def _rip_done(self):
        self.ripples = []
        self.update()

    def paintEvent(self, e):
        if self.geometry() != self.btn.rect():
            self.setGeometry(self.btn.rect())
        if self.hover <= .001 and not self.ripples:
            return
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            r = QRectF(self.rect())
            rad = _radius(self.btn)
            path = QPainterPath()
            path.addRoundedRect(r.adjusted(.5, .5, -.5, -.5), rad, rad)
            p.setClipPath(path)
            p.setPen(Qt.PenStyle.NoPen)
            if self.hover > .001 and self.btn.isEnabled():
                base = QColor(0, 0, 0) if self.light else QColor(255, 255, 255)
                base.setAlphaF((.06 if self.light else .065) * self.hover)
                p.fillRect(r, base)
            now = time.monotonic()
            far = math.hypot(r.width(), r.height())
            for pt, t0 in self.ripples:
                k = min(1.0, (now - t0) / .46)
                ease = 1 - (1 - k) ** 3
                c = QColor(0, 0, 0) if self.light else QColor(255, 255, 255)
                c.setAlphaF((.16 if self.light else .14) * (1 - k))
                p.setBrush(c)
                p.drawEllipse(pt, far * (.12 + .9 * ease), far * (.12 + .9 * ease))
        finally:
            p.end()


class ButtonMotion(QObject):
    """Фильтр событий приложения: наведение и нажатие кнопок → _Glow поверх кнопки."""

    def __init__(self, scope: QWidget):
        super().__init__(scope)
        self.scope = scope                                 # окно, в котором действует (кнопки его и его всплывашек)

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t not in (QEvent.Type.Enter, QEvent.Type.Leave, QEvent.Type.MouseButtonPress):
            return False
        if not isinstance(obj, QAbstractButton) or obj.objectName() in SKIP:
            return False
        try:
            import ya_skin
            if not ya_skin.PHANTOM_ON:
                return False
        except Exception:                                  # noqa: BLE001
            return False
        g = obj.findChild(_Glow, options=Qt.FindChildOption.FindDirectChildrenOnly)
        if t == QEvent.Type.Enter:
            if g is None:
                if obj.width() > 600 or obj.height() > 200:    # большие «кнопки»-плитки — свои эффекты
                    return False
                g = _Glow(obj)
            g.raise_()
            g.to_hover(True)
        elif t == QEvent.Type.Leave:
            if g is not None:
                g.to_hover(False)
        elif t == QEvent.Type.MouseButtonPress and ev.button() == Qt.MouseButton.LeftButton:
            if g is None:
                if obj.width() > 600 or obj.height() > 200:
                    return False
                g = _Glow(obj)
            g.raise_()
            g.ripple(ev.position())
        return False


# ── старые таблицы стилей Echoes в виде Phantom: веса Inter 600/700 вместо 800/900, жёлтое → белое ── #
_W = re.compile(r"font-weight\s*:\s*(800|900|bold|black)", re.I)
_YEL = re.compile(r"rgba\(\s*255\s*,\s*219\s*,\s*26\s*,", re.I)
_YHEX = re.compile(r"#ffdb1a|#ffd60a|#ffcc00", re.I)


_SLAB = re.compile(r"(QFrame[^{]*\{[^}]*?background(?:-color)?\s*:\s*)#(?:1[0-9a-f]{5}|2[0-2][0-9a-f]{4}|0[0-9a-f]{5})",
                   re.I)


def phantom_qss(ss: str) -> str:
    ss = _SLAB.sub(lambda m: m.group(1) + "rgba(255,255,255,0.045)", ss)          # тёмные плашки страниц — стекло Phantom
    out = _W.sub(lambda m: "font-weight:700" if m.group(1).lower() in ("900", "black") else "font-weight:600", ss)
    out = _YEL.sub("rgba(255,255,255,", out)
    return _YHEX.sub("#f2f2f2", out)


class StyleFix(QObject):
    """Когда виджету задают свою таблицу стилей (setStyleSheet) — переписать её под Phantom (один раз)."""

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t != QEvent.Type.Polish and t != QEvent.Type.StyleChange:
            return False
        if not isinstance(obj, QWidget):
            return False
        try:
            import ya_skin
            if not ya_skin.PHANTOM_ON:
                return False
            ss = obj.styleSheet()
            if not ss or obj.property("_phqss") == ss:
                return False
            new = phantom_qss(ss)
            obj.setProperty("_phqss", new)
            if new != ss:
                obj.setStyleSheet(new)
        except RuntimeError:
            pass
        return False


_INSTALLED = None
_STYLE = None


def install(scope: QWidget):
    global _INSTALLED, _STYLE
    if _INSTALLED is not None:
        return _INSTALLED
    _INSTALLED = ButtonMotion(scope)
    _STYLE = StyleFix(scope)
    app = QApplication.instance()
    app.installEventFilter(_INSTALLED)
    app.installEventFilter(_STYLE)
    return _INSTALLED
