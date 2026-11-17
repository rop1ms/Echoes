# ph_widgets.py
"""
Базовые виджеты в стиле Phantom (на ph_style): стеклянная поверхность, родитель, рисующий тени детей,
сегменты-вкладки, кнопки-иконки, кикер и полоса перемотки.

Тени: виджет не может рисовать за своими краями, поэтому тень стеклянной карточки рисует РОДИТЕЛЬ —
ShadowHost — в своём paintEvent, до детей (картинки из кэша ph_style, по одной на размер).
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy,
                             QWidget)

import ph_style as ph


class PhButton(QPushButton):
    """Кнопка Phantom. Свой класс нужен, чтобы кэш отрисовки кнопок Echoes (paint_cache, только точный
    QPushButton) её не трогал: он рисует подпись шрифтом приложения, и мелкие подписи Phantom вылезали за края."""


class PhSurface(QFrame):
    """Стеклянная поверхность: kind = panel | card | soft | island | menu | row (см. ph_style.KINDS)."""

    def __init__(self, kind: str = "panel", parent=None, radius: float | None = None, edge_light: bool = False):
        super().__init__(parent)
        self.kind = kind
        self.radius = radius
        self.edge_light = edge_light
        self.hover_enabled = False
        self._hover = False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setFrameShape(QFrame.Shape.NoFrame)

    def surface_radius(self) -> float:
        return ph.px(ph.KINDS.get(self.kind, (ph.R_LG, None))[0]) if self.radius is None else self.radius

    def set_hover_enabled(self, on: bool):
        self.hover_enabled = on
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, on)

    def enterEvent(self, e):
        if self.hover_enabled:
            self._hover = True
            self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        if self._hover:
            self._hover = False
            self.update()
        super().leaveEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        ph.paint_surface(p, QRectF(self.rect()), self.kind, self.surface_radius(), hover=self._hover,
                         edge_light=self.edge_light)
        p.end()


class ShadowHost(QWidget):
    """Прозрачный контейнер: рисует тени своих прямых детей-PhSurface (видимых), затем Qt рисует детей."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def paintEvent(self, e):
        kids = [w for w in self.findChildren(PhSurface, options=Qt.FindChildOption.FindDirectChildrenOnly)
                if w.isVisible() and ph.KINDS.get(w.kind, (0, None))[1]]
        if not kids:
            return
        p = QPainter(self)
        clip = QRectF(e.rect())
        for w in kids:
            r = QRectF(w.geometry())
            m = ph.shadow_margin(w.kind)
            if not clip.intersects(r.adjusted(-m, -m, m, m)):
                continue
            ph.paint_shadow(p, r, w.kind, w.surface_radius())
        p.end()


def kicker(text: str, parent=None) -> QLabel:
    """Кикер (LYRICS, NOW PLAYING…): капс, 10 px, 600, разрядка .2em, белый 42 %."""
    lb = QLabel(text.upper(), parent)
    lb.setObjectName("PhKicker")
    ph.set_font(lb, ph.kicker_font())
    return lb


ROLE_FONTS = {                              # роль подписи → шрифт по умолчанию (как классы .pa-* у Phantom)
    "PhKicker": lambda: ph.kicker_font(),
    "PhWordmark": lambda: ph.wordmark_font(),
    "PhTitle": lambda: ph.title_font(20),
    "PhDisplay": lambda: ph.display_font(36),
    "PhHeading": lambda: ph.font(ph.TEXT_LG, 600, -.015),
    "PhBody": lambda: ph.font(ph.TEXT_BASE),
    "PhSub": lambda: ph.font(ph.TEXT_SM, 450),
    "PhMuted": lambda: ph.font(ph.TEXT_XS, 450),
    "PhGhost": lambda: ph.font(ph.TEXT_XS),
    "PhBadge": lambda: ph.font(ph.TEXT_2XS, 600, ph.TRACKING_WIDE),
}


def label(text: str, role: str = "PhBody", parent=None, font=None) -> QLabel:
    """Подпись с ролью (цвет — из QSS, шрифт — по роли или font)."""
    lb = QLabel(text, parent)
    lb.setObjectName(role)
    f = font if font is not None else ROLE_FONTS.get(role, ROLE_FONTS["PhBody"])()
    ph.set_font(lb, f)
    return lb


def icon_button(name: str, kind: str = "ghost", size: str = "md", icon_px: int | None = None,
                tip: str = "", checkable: bool = False, parent=None, color=ph.TEXT_SECONDARY,
                active=ph.TEXT_PRIMARY) -> QPushButton:
    """Круглая кнопка-иконка Phantom: kind ghost | surface | solid, size sm(28) | top(30) | md(34) | lg(40) |
    play(44, только solid). Иконка 14/16/18 px по размеру."""
    b = PhButton(parent)
    b.setObjectName({"ghost": "PhIcon", "surface": "PhIconSurface", "solid": "PhIconSolid"}[kind])
    if size != "md":
        b.setProperty("phSize", size)
    ip = icon_px or {"sm": 14, "top": 16, "md": 16, "lg": 18, "play": 20}[size]
    if kind == "solid":
        color = active = (5, 5, 5, 1.0)
    b.setIcon(ph.icon(name, ip, color, active))
    b.setIconSize(QSize(ph.px(ip), ph.px(ip)))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    b.setCheckable(checkable)
    if tip:
        b.setToolTip(tip)
        b.setAccessibleName(tip)
    return b


def text_button(text: str, kind: str = "secondary", icon: str | None = None, parent=None) -> QPushButton:
    """Кнопка с текстом: primary (белая) | secondary (стекло) | ghost | danger | small."""
    b = PhButton(text, parent)
    b.setObjectName({"primary": "PhPrimary", "secondary": "PhSecondary", "ghost": "PhGhost",
                     "danger": "PhDanger", "small": "PhSmall"}[kind])
    ph.set_font(b, ph.font(ph.TEXT_XS if kind == "small" else ph.TEXT_SM, 550))
    if icon:
        col = (5, 5, 5, 1.0) if kind == "primary" else ph.TEXT_PRIMARY
        b.setIcon(ph.icon(icon, 14, col, col))
        b.setIconSize(QSize(ph.px(14), ph.px(14)))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return b


def chip(text: str, checked: bool = False, parent=None) -> QPushButton:
    """Пилюля-фильтр (Все файлы · Избранное · Недавно прослушано)."""
    b = PhButton(text, parent)
    b.setObjectName("PhChip")
    ph.set_font(b, ph.font(ph.TEXT_XS, 500))
    b.setCheckable(True)
    b.setChecked(checked)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return b


class PhSearch(QLineEdit):
    """Поле поиска Phantom: высота 40, лупа слева, «×» очистки появляется, когда есть текст."""

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("PhSearch")
        ph.set_font(self, ph.font(ph.TEXT_SM, 450))
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self._icon = ph.icon_pixmap("search", 15, ph.TEXT_TERTIARY)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        s = self._icon.width() / self._icon.devicePixelRatio()
        p.drawPixmap(int(ph.px(13)), int((self.height() - s) / 2), self._icon)
        p.end()


class PhSegments(QFrame):
    """Сегменты-вкладки (Треки | Плейлисты | Папки, LIVE | ТЕКСТ, меню Echoes). changed(key)."""

    changed = pyqtSignal(str)

    def __init__(self, items: list[tuple[str, str] | tuple[str, str, str]], compact: bool = False,
                 stretch: bool = True, parent=None):
        """items: (ключ, подпись) или (ключ, подпись, иконка Lucide)."""
        super().__init__(parent)
        self.setObjectName("PhSegments")
        if compact:
            self.setProperty("phCompact", "true")
        self.setFixedHeight(ph.px(30) if compact else ph.px(36))
        self.setSizePolicy(QSizePolicy.Policy.Expanding if stretch else QSizePolicy.Policy.Maximum,
                           QSizePolicy.Policy.Fixed)
        seg_font = ph.font(ph.TEXT_2XS, 600) if compact else ph.font(ph.TEXT_SM, 550)
        lay = QHBoxLayout(self)
        m = 3
        lay.setContentsMargins(m, m, m, m)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        for it in items:
            key, text = it[0], it[1]
            b = PhButton(text)
            b.setObjectName("PhSegment")
            ph.set_font(b, seg_font)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            if len(it) > 2 and it[2]:
                b.setIcon(ph.icon(it[2], 14, ph.TEXT_TERTIARY, ph.TEXT_SECONDARY, checked=ph.TEXT_PRIMARY))
                b.setIconSize(QSize(ph.px(14), ph.px(14)))
            if stretch:
                b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.group.addButton(b)
            self.buttons[key] = b
            lay.addWidget(b, 1 if stretch else 0)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
        self._full = {k: b.text() for k, b in self.buttons.items()}
        self._icons = bool(items) and all(len(it) > 2 and it[2] for it in items)
        self._fm = QFontMetrics(seg_font)
        if items:
            self.buttons[items[0][0]].setChecked(True)
        self.group.buttonToggled.connect(lambda *_: self._fit())
        # плашка выбранной вкладки едет к новой (как у Phantom), а не прыгает
        self._ind = None
        self._ind_from = self._ind_to = None
        self._ind_anim = QVariantAnimation(self)
        self._ind_anim.setStartValue(0.0)
        self._ind_anim.setEndValue(1.0)
        self._ind_anim.setEasingCurve(ph.ease_out())
        self._ind_anim.valueChanged.connect(self._ind_step)
        self.group.buttonToggled.connect(self._ind_go)

    def _fit(self):
        """Узко: у невыбранных вкладок остаются только значки (подпись — в подсказке), чтобы слова
        не обрезались посередине; совсем узко — и у выбранной."""
        if not self._icons or not self.buttons:
            return
        n = len(self.buttons)
        avail = self.width() - 6 - 2 * (n - 1)
        pad = ph.px(14) + ph.px(26)                     # значок, отступы кнопки
        need = sum(self._fm.horizontalAdvance(t) + pad for t in self._full.values())
        cur = self.current()
        keep_cur = (avail - (n - 1) * (ph.px(14) + ph.px(18))
                    >= self._fm.horizontalAdvance(self._full.get(cur, "")) + pad)
        for k, b in self.buttons.items():
            full = self._full[k]
            show = need <= avail or (k == cur and keep_cur)
            txt = full if show else ""
            if b.text() != txt:
                b.setText(txt)
            b.setToolTip("" if show else full.strip())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()
        self._ind_anim.stop()
        self._ind = None                                       # после раскладки — сразу на место

    def _target(self):
        b = self.group.checkedButton()
        return QRectF(b.geometry()) if b is not None and b.isVisible() else None

    def _ind_go(self, btn, on):
        if not on:
            return
        to = QRectF(btn.geometry())
        d = ph.duration(ph.DUR_BASE)
        if self._ind is None or d <= 0 or not self.isVisible():
            self._ind = None
            self.update()
            return
        self._ind_from, self._ind_to = QRectF(self._ind), to
        self._ind_anim.stop()
        self._ind_anim.setDuration(d)
        self._ind_anim.start()

    def _ind_step(self, v):
        a, b = self._ind_from, self._ind_to
        if a is None or b is None:
            return
        k = float(v)
        self._ind = QRectF(a.x() + (b.x() - a.x()) * k, a.y() + (b.y() - a.y()) * k,
                           a.width() + (b.width() - a.width()) * k, a.height() + (b.height() - a.height()) * k)
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        if self._ind is None or not self._ind_anim.state() == QVariantAnimation.State.Running:
            self._ind = self._target()
        r = self._ind
        if r is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(ph.qcolor(ph.LINE_2), 1.0))
        p.setBrush(ph.white(.13))
        rad = r.height() / 2
        p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), rad, rad)
        p.end()

    def current(self) -> str:
        for k, b in self.buttons.items():
            if b.isChecked():
                return k
        return ""

    def set_current(self, key: str, emit: bool = False):
        b = self.buttons.get(key)
        if b and not b.isChecked():
            b.setChecked(True)
            if emit:
                self.changed.emit(key)


class PhSeek(QWidget):
    """Полоса перемотки/громкости Phantom: дорожка 3 px (белый 92 % / 14 %), кружок 12 px появляется
    при наведении и перетаскивании. value 0..1; moved(v) — тянут, released(v) — отпустили."""

    moved = pyqtSignal(float)
    released = pyqtSignal(float)

    def __init__(self, parent=None, always_thumb: bool = False):
        super().__init__(parent)
        self._v = 0.0
        self._hover = False
        self._drag = False
        self.always_thumb = always_thumb
        self.setMinimumHeight(14)
        self.setFixedHeight(ph.px(14))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def value(self) -> float:
        return self._v

    def set_value(self, v: float):
        v = max(0.0, min(1.0, float(v)))
        if self._drag:
            return
        # перерисовать только если сдвиг заметен (≥ полпикселя) — полоса тикает 10 раз в секунду
        if abs(v - self._v) * max(1, self.width()) >= .5:
            self._v = v
            self.update()
        else:
            self._v = v

    def _at(self, x: float) -> float:
        return max(0.0, min(1.0, x / max(1, self.width())))

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = True
            self._v = self._at(e.position().x())
            self.moved.emit(self._v)
            self.update()

    def mouseMoveEvent(self, e):
        if self._drag:
            self._v = self._at(e.position().x())
            self.moved.emit(self._v)
            self.update()

    def mouseReleaseEvent(self, e):
        if self._drag:
            self._drag = False
            self._v = self._at(e.position().x())
            self.released.emit(self._v)
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cy = h / 2
        x = self._v * w
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ph.white(.14))
        p.drawRoundedRect(QRectF(0, cy - 1.5, w, 3), 1.5, 1.5)
        if x > 0:
            p.setBrush(ph.white(.92))
            p.drawRoundedRect(QRectF(0, cy - 1.5, x, 3), 1.5, 1.5)
        if self._hover or self._drag or self.always_thumb:
            k = 1.15 if (self._hover and not self._drag) else 1.0
            r = 6 * k
            p.setBrush(QColor(0, 0, 0, 90))
            p.drawEllipse(QPointF(x, cy + 1), r + .5, r + .5)
            p.setBrush(QColor(255, 255, 255))
            p.drawEllipse(QPointF(max(r, min(w - r, x)), cy), r, r)
        p.end()


class PhDots(QWidget):
    """Точки-страницы под виджетами: активная — палочка 14×3, остальные — точки 3 px."""

    def __init__(self, count: int, current: int = 0, parent=None):
        super().__init__(parent)
        self.count, self.current = count, current
        self.setFixedHeight(8)
        self.setMinimumWidth(count * 8 + 12)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def set_current(self, i: int):
        if i != self.current:
            self.current = i
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        gap, dot, bar = 7.0, 3.0, 14.0
        total = (self.count - 1) * gap + bar
        x = (self.width() - total) / 2
        cy = self.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(self.count):
            if i == self.current:
                p.setBrush(ph.white(.9))
                p.drawRoundedRect(QRectF(x, cy - 1.5, bar, 3), 1.5, 1.5)
                x += bar + gap - dot
            else:
                p.setBrush(ph.white(.22))
                p.drawEllipse(QRectF(x, cy - 1.5, dot, dot))
                x += gap
        p.end()


class PhHairline(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PhHairline")
        self.setFixedHeight(1)


class PhPulseDot(QWidget):
    """Маленькая точка статуса (● Синхронизировано / ○ Неизвестно)."""

    def __init__(self, on: bool = True, parent=None):
        super().__init__(parent)
        self.on = on
        self.setFixedSize(8, 8)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.on:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ph.white(.86))
        else:
            p.setPen(QPen(ph.white(.5), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(1.5, 1.5, 5, 5))
        p.end()
