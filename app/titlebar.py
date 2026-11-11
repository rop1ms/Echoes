# titlebar.py
"""
Собственный заголовок окна (окно без системной рамки). Внешний вид подстраивается
под тему: у каждой — свой характер.
  • Echoes Music (Я.Музыка) — чёрная плоская панель, жёлтая точка-логотип, плоские кнопки;
  • Winamp — стальной «объёмный» заголовок с полосками по краям, как у классического плеера;
  • Fluid — прозрачная панель на «бумажном» фоне, круглые мягкие кнопки;
  • остальные темы — панель в цветах темы с градиентной линией акцента снизу.

Перетаскивание и «разворот по двойному клику» — системные (startSystemMove), изменение
размера за края окна — startSystemResize, поэтому привязка к краям экрана (Win+←/→, снап) работает.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QEvent, QObject, QRectF, QPointF, QSize, QTimer
from PyQt6.QtGui import (QColor, QPainter, QPainterPath, QLinearGradient, QFont, QFontMetrics, QPen,
                         QGuiApplication)
from PyQt6.QtWidgets import QWidget, QAbstractButton, QHBoxLayout, QApplication

HEIGHT = 36
EDGE = 6


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


def _alpha(c: QColor, a: float) -> QColor:
    c = QColor(c)
    c.setAlphaF(max(0.0, min(1.0, a)))
    return c


class WinButton(QAbstractButton):
    """Кнопка окна: свернуть / развернуть(восстановить) / закрыть — рисуется кодом."""

    def __init__(self, kind, bar, parent=None):
        super().__init__(parent)
        self.kind, self.bar = kind, bar
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._hover = False
        self._down = False
        self.setMouseTracking(True)

    def sizeHint(self):
        return QSize(*self.bar.button_size())

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self._down = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._down = True
            self.update()
        e.accept()

    def mouseReleaseEvent(self, e):
        was = self._down
        self._down = False
        self.update()
        if was and e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        e.accept()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.bar.paint_button(p, self)
        p.end()


class TitleBar(QWidget):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.variant = "default"
        self.bg = QColor("#101018")
        self.fg = QColor("#e8e8f0")
        self.accent = QColor("#a78bfa")
        self.accent2 = QColor("#ff4fa3")
        self.light = False
        self.title = ""
        self.custom_bg = None
        self.custom_line = True
        self.setFixedHeight(HEIGHT)
        self.setMouseTracking(True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(2)
        lay.addStretch(1)
        self.btn_min = WinButton("min", self)
        self.btn_max = WinButton("max", self)
        self.btn_close = WinButton("close", self)
        for b, tip in ((self.btn_min, "Свернуть"), (self.btn_max, "Развернуть"), (self.btn_close, "Закрыть")):
            b.setToolTip(tip)
            lay.addWidget(b)
        self.btn_min.clicked.connect(lambda: getattr(win, "animated_minimize", win.showMinimized)())  # ui_anim
        self.btn_max.clicked.connect(self.toggle_maximize)
        self.btn_close.clicked.connect(win.close)
        win.installEventFilter(self)
        self._apply_sizes()
        # «Обновить» рядом с надписью ECHOES — когда друг/автор прислал новую версию (net_page._upd_ui)
        from PyQt6.QtWidgets import QPushButton
        self.upd_btn = QPushButton("Обновить", self)
        self.upd_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.upd_btn.setToolTip("Доступна новая версия ECHOES — открыть")
        self.upd_btn.hide()
        self._upd_cb = None
        self.upd_btn.clicked.connect(lambda: self._upd_cb and self._upd_cb())
        self._brand_end = 0

    # ── поведение ── #

    def toggle_maximize(self):
        w = self.win
        import ui_anim                                         # плавно: снимок окна тянется к новому размеру
        ui_anim.animate_state(w, "normal" if w.isMaximized() or w.isFullScreen() else "max")

    def eventFilter(self, obj, ev):
        if obj is self.win and ev.type() == QEvent.Type.WindowStateChange:
            self.btn_max.setToolTip("Восстановить" if self.win.isMaximized() else "Развернуть")
            self.update()
            self.btn_max.update()
        return False

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            h = self.win.windowHandle()
            if h is not None:
                h.startSystemMove()
            e.accept()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximize()
            e.accept()

    # ── тема ── #

    def set_theme(self, theme: dict):
        self.bg = QColor(theme.get("bg", "#101018"))
        self.fg = QColor(theme.get("text", "#e8e8f0"))
        self.accent = QColor(theme.get("accent", "#a78bfa"))
        self.accent2 = QColor(theme.get("accent2", theme.get("accent", "#ff4fa3")))
        self.light = self.bg.value() > 170
        self.variant = ("winamp" if theme.get("winamp") else "ya" if theme.get("yamusic")
                        else "fluid" if theme.get("fluid") else "custom" if theme.get("custom") else "default")
        # тема из конструктора: свой фон (пусто — прозрачный, сквозь него виден фон темы),
        # свой цвет текста и линия акцента
        tb = (theme.get("ct") or {}).get("components", {}).get("titlebar", {}) if theme.get("custom") else {}
        self.custom_bg = QColor(tb["bg"]) if tb.get("bg") else None
        if tb.get("fg"):
            self.fg = QColor(tb["fg"])
        self.custom_line = bool(tb.get("line", True))
        self._apply_sizes()
        if hasattr(self, "upd_btn"):
            self._style_upd()
        self.update()
        for b in (self.btn_min, self.btn_max, self.btn_close):
            b.update()

    def set_update(self, on: bool, cb=None, text="Обновить"):
        self._upd_cb = cb
        self.upd_btn.setText(text)
        self._style_upd()
        self.upd_btn.setVisible(bool(on))
        self._place_upd()

    def _style_upd(self):
        acc = QColor(self.accent)
        fg = "#000000" if acc.lightness() > 120 else "#ffffff"
        self.upd_btn.setStyleSheet(
            f"QPushButton{{background:{acc.name()};color:{fg};border:none;border-radius:9px;padding:0 9px 0 8px;"
            f"font-size:11px;font-weight:800;}}"
            f"QPushButton:hover{{background:{acc.lighter(115).name()};}}")
        try:
            from yamusic_theme import ya_icon
            self.upd_btn.setIcon(ya_icon("download", 12, fg))
        except Exception:                                      # noqa: BLE001
            pass
        self.upd_btn.adjustSize()
        self.upd_btn.setFixedHeight(18)

    def _place_upd(self):
        b = self.upd_btn
        if b.isHidden():
            return
        x = (self._brand_end or 110) + 8
        b.move(int(x), int((self.height() - b.height()) / 2))
        b.raise_()

    def set_title(self, text: str):
        self.title = text or ""
        self.update()

    def button_size(self):
        return {"winamp": (22, 18), "fluid": (28, 28), "ya": (44, 30)}.get(self.variant, (40, 28))

    def _apply_sizes(self):
        w, h = self.button_size()
        for b in (self.btn_min, self.btn_max, self.btn_close):
            b.setFixedSize(w, h)
        self.layout().setSpacing(2 if self.variant != "winamp" else 3)
        self.layout().setContentsMargins(0, 0, 8 if self.variant == "winamp" else 6, 0)

    # ── рисование ── #

    def _icon(self):
        ic = self.win.windowIcon()
        return ic.pixmap(18, 18) if not ic.isNull() else None

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        import wave_veil
        np_bg = self._now_playing_bg() if self.variant == "ya" else None
        if np_bg is not None:                                  # «Сейчас играет» / «Текст»: под заголовком — тот же
            bg, a = np_bg                                      # размытый фон обложки, отражённый от линии стыка,
            p.fillRect(0, 0, W, H, QColor("#000000"))          # — заголовок и экран без шва
            p.save()
            p.setOpacity(a)
            p.translate(0, H)
            p.scale(1, -1)
            p.drawPixmap(QRectF(0, 0, W, H), bg, QRectF(0, 0, bg.width(), min(H, bg.height())))
            p.restore()
            self._no_bg = True
            try:
                self._paint_ya(p, W, H)
            finally:
                self._no_bg = False
        elif self.variant == "ya" and wave_veil.level() > 0:   # «Моя волна»: фон заголовка растворяется,
            p.fillRect(0, 0, W, H, QColor("#000000"))          # под ним — волна на всё окно; знаки остаются
            wave_veil.paint(self, p, 0)
            self._no_bg = True
            try:
                self._paint_ya(p, W, H)
            finally:
                self._no_bg = False
        else:
            getattr(self, f"_paint_{self.variant}")(p, W, H)
        p.end()

    def _now_playing_bg(self):
        """Фон открытого экрана «Сейчас играет»/«Текст» и насколько он проявлен, или None."""
        try:
            shell = getattr(self.win, "_ya", None)
            np_ = shell.__dict__.get("_now_playing") if shell is not None else None
            if np_ is None or not np_.isVisible() or np_._bgc is None or np_._op <= 0.0:
                return None
            t = max(0.0, min(1.0, np_._op))
            return np_._bgc, 1.0 - (1.0 - t) ** 3
        except Exception:                                      # noqa: BLE001
            return None

    def _draw_brand(self, p, x, color, weight=QFont.Weight.ExtraBold, size=10, spacing=2.4, upper=True):
        f = QFont(self.font())
        f.setPixelSize(size + 2)
        f.setWeight(weight)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
        p.setFont(f)
        p.setPen(color)
        txt = "ECHOES"
        w = QFontMetrics(f).horizontalAdvance(txt)
        p.drawText(QRectF(x, 0, w + 6, self.height()), Qt.AlignmentFlag.AlignVCenter, txt)
        if abs(self._brand_end - (x + w + 6)) > 0.5:
            self._brand_end = x + w + 6
            QTimer.singleShot(0, self._place_upd)
        return x + w + 6

    def _draw_title(self, p, x0, x1, color, size=12, weight=QFont.Weight.DemiBold, center=False, upper=False):
        if not self.title or x1 - x0 < 40:
            return
        f = QFont(self.font())
        f.setPixelSize(size)
        f.setWeight(weight)
        p.setFont(f)
        p.setPen(color)
        txt = self.title.upper() if upper else self.title
        el = QFontMetrics(f).elidedText(txt, Qt.TextElideMode.ElideRight, int(x1 - x0))
        al = Qt.AlignmentFlag.AlignVCenter | (Qt.AlignmentFlag.AlignHCenter if center else Qt.AlignmentFlag.AlignLeft)
        p.drawText(QRectF(x0, 0, x1 - x0, self.height()), al, el)

    def _btn_area_left(self):
        return self.btn_min.geometry().left() - 8

    # Echoes Music (Я.Музыка): чёрная плоская панель
    def _paint_ya(self, p, W, H):
        if not getattr(self, "_no_bg", False):
            p.fillRect(0, 0, W, H, QColor("#000000"))
        ic = self._icon()
        try:                                                   # солнце — в акцент темы / обложки, как логотип
            import ya_decor
            ya_decor.paint_sun(p, QPointF(18, H / 2), 8, 0.0)
            ic = None
            drawn = True
        except Exception:                                      # noqa: BLE001
            drawn = False
        if drawn:
            pass
        elif ic is not None:
            p.drawPixmap(10, int((H - 16) / 2), 16, 16, ic)                  # значок-солнце
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self.accent)
            p.drawEllipse(QPointF(18, H / 2), 4.5, 4.5)
        x = self._draw_brand(p, 32, QColor("#ffffff"), size=10, spacing=2.6)
        if not self.upd_btn.isHidden():
            x += self.upd_btn.width() + 10
        self._draw_title(p, x + 14, self._btn_area_left(), QColor("#8a8a8a"), center=False)

    # Winamp: стальной объёмный заголовок с полосками
    def _paint_winamp(self, p, W, H):
        g = QLinearGradient(0, 0, 0, H)
        g.setColorAt(0.0, QColor("#5b6070"))
        g.setColorAt(0.5, QColor("#3a3e4b"))
        g.setColorAt(1.0, QColor("#262932"))
        p.fillRect(0, 0, W, H, g)
        p.setPen(QColor(255, 255, 255, 70))
        p.drawLine(0, 0, W, 0)
        p.setPen(QColor(0, 0, 0, 150))
        p.drawLine(0, H - 1, W, H - 1)
        ic = self._icon()
        if ic is not None:
            p.drawPixmap(8, int((H - 16) / 2), 16, 16, ic)
        # центр: полоски — заголовок — полоски
        f = QFont("Tahoma")
        f.setPixelSize(11)
        f.setBold(True)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
        p.setFont(f)
        txt = ("ECHOES" + (" — " + self.title if self.title else "")).upper()
        left, right = 34, self._btn_area_left()
        avail = right - left
        tw = min(QFontMetrics(f).horizontalAdvance(txt) + 16, avail - 40)
        tx = left + (avail - tw) / 2
        for (a, b) in ((left, tx - 6), (tx + tw + 6, right)):
            if b - a > 6:
                for yy in (H / 2 - 4, H / 2 - 1, H / 2 + 2):
                    p.setPen(QColor(255, 255, 255, 55))
                    p.drawLine(int(a), int(yy), int(b), int(yy))
                    p.setPen(QColor(0, 0, 0, 120))
                    p.drawLine(int(a), int(yy) + 1, int(b), int(yy) + 1)
        p.setPen(self.accent if self.accent.value() > 90 else QColor("#00ff66"))
        el = QFontMetrics(f).elidedText(txt, Qt.TextElideMode.ElideRight, int(tw))
        p.drawText(QRectF(tx, 0, tw, H), Qt.AlignmentFlag.AlignCenter, el)

    # Fluid: прозрачная панель на бумажном фоне
    def _paint_fluid(self, p, W, H):
        p.fillRect(0, 0, W, H, _alpha(self.bg, 1.0))
        ic = self._icon()
        if ic is not None:
            p.drawPixmap(14, int((H - 18) / 2), 18, 18, ic)
        self._draw_title(p, 42, self._btn_area_left(), _alpha(self.fg, 0.85), size=12,
                         weight=QFont.Weight.DemiBold, center=True)
        p.setPen(QPen(_alpha(self.fg, 0.07), 1))
        p.drawLine(14, H - 1, W - 14, H - 1)

    # тема из конструктора: прозрачный (или свой) фон, линия акцента по желанию
    def _paint_custom(self, p, W, H):
        if self.custom_bg is not None:
            p.fillRect(0, 0, W, H, self.custom_bg)
        if self.custom_line:
            g = QLinearGradient(0, 0, W, 0)
            g.setColorAt(0.0, _alpha(self.accent, 0.0))
            g.setColorAt(0.25, _alpha(self.accent, 0.9))
            g.setColorAt(0.75, _alpha(self.accent2, 0.9))
            g.setColorAt(1.0, _alpha(self.accent2, 0.0))
            p.fillRect(0, H - 2, W, 2, g)
        ic = self._icon()
        x = 14
        if ic is not None:
            p.drawPixmap(12, int((H - 18) / 2) - 1, 18, 18, ic)
            x = 36
        x = self._draw_brand(p, x, self.fg, size=10, spacing=2.4)
        self._draw_title(p, x + 14, self._btn_area_left(), _alpha(self.fg, 0.6))

    # остальные темы: цвета темы + линия акцента
    def _paint_default(self, p, W, H):
        base = self.bg.lighter(112) if not self.light else self.bg.darker(104)
        p.fillRect(0, 0, W, H, base)
        g = QLinearGradient(0, 0, W, 0)
        g.setColorAt(0.0, _alpha(self.accent, 0.0))
        g.setColorAt(0.25, _alpha(self.accent, 0.9))
        g.setColorAt(0.75, _alpha(self.accent2, 0.9))
        g.setColorAt(1.0, _alpha(self.accent2, 0.0))
        p.fillRect(0, H - 2, W, 2, g)
        ic = self._icon()
        x = 14
        if ic is not None:
            p.drawPixmap(12, int((H - 18) / 2) - 1, 18, 18, ic)
            x = 36
        x = self._draw_brand(p, x, self.fg, size=10, spacing=2.4)
        self._draw_title(p, x + 14, self._btn_area_left(), _alpha(self.fg, 0.6))

    # ── кнопки ── #

    def paint_button(self, p, b):
        W, H = b.width(), b.height()
        hover, down = b._hover, b._down
        v = self.variant
        close = b.kind == "close"
        if v == "winamp":
            g = QLinearGradient(0, 0, 0, H)
            if down:
                g.setColorAt(0, QColor("#1c1e25")); g.setColorAt(1, QColor("#3c404c"))
            else:
                g.setColorAt(0, QColor("#7b8090") if hover else QColor("#666b7b"))
                g.setColorAt(1, QColor("#363a46"))
            p.fillRect(0, 0, W, H, g)
            p.setPen(QColor(255, 255, 255, 90)); p.drawLine(0, 0, W - 1, 0); p.drawLine(0, 0, 0, H - 1)
            p.setPen(QColor(0, 0, 0, 170)); p.drawLine(0, H - 1, W - 1, H - 1); p.drawLine(W - 1, 0, W - 1, H - 1)
            col = QColor("#e8ecf4")
            sz = 7
        else:
            if v == "fluid":
                if hover or down:
                    path = QPainterPath(); path.addEllipse(QRectF(0, 0, W, H))
                    p.fillPath(path, QColor("#e5484d") if close else _alpha(self.fg, 0.12 if not down else 0.2))
                col = QColor("#ffffff") if (close and hover) else _alpha(self.fg, 0.85)
            else:
                if hover or down:
                    rr = QPainterPath(); rr.addRoundedRect(QRectF(0, 0, W, H), 6, 6)
                    if close:
                        p.fillPath(rr, QColor("#e5484d"))
                    else:
                        base = QColor("#ffffff") if v == "ya" or not self.light else QColor("#000000")
                        p.fillPath(rr, _alpha(self.fg if v in ("default", "custom") else base,
                                              0.14 if not down else 0.22))
                col = QColor("#ffffff") if (close and hover) else (
                    QColor("#d6d6d6") if v == "ya" else _alpha(self.fg, 0.9))
            sz = 9
        pen = QPen(col, 1.4 if v == "winamp" else 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                   Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy = W / 2, H / 2
        h = sz / 2
        if b.kind == "min":
            p.drawLine(QPointF(cx - h, cy + 2), QPointF(cx + h, cy + 2))
        elif b.kind == "max":
            if self.win.isMaximized():
                p.drawRect(QRectF(cx - h + 2, cy - h, sz - 2, sz - 2))
                p.drawLine(QPointF(cx - h, cy - h + 2), QPointF(cx - h, cy + h))
                p.drawLine(QPointF(cx - h, cy + h), QPointF(cx + h - 2, cy + h))
            else:
                p.drawRect(QRectF(cx - h, cy - h, sz, sz))
        else:
            p.drawLine(QPointF(cx - h, cy - h), QPointF(cx + h, cy + h))
            p.drawLine(QPointF(cx + h, cy - h), QPointF(cx - h, cy + h))


class EdgeResizer(QObject):
    """Изменение размера безрамочного окна за края/углы (системное, со снапом)."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self._cursor_on = False
        import native_ui
        native_ui.app_filter(self, (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress, QEvent.Type.Leave))

    def _edges(self, gpos):
        w = self.win
        if w.isMaximized() or w.isFullScreen():
            return Qt.Edge(0)
        p = w.mapFromGlobal(gpos.toPoint())
        if not w.rect().adjusted(-2, -2, 2, 2).contains(p):
            return Qt.Edge(0)
        e = Qt.Edge(0)
        if p.x() <= EDGE:
            e |= Qt.Edge.LeftEdge
        if p.x() >= w.width() - EDGE:
            e |= Qt.Edge.RightEdge
        if p.y() <= 3:
            e |= Qt.Edge.TopEdge
        if p.y() >= w.height() - EDGE:
            e |= Qt.Edge.BottomEdge
        return e

    @staticmethod
    def _cursor(e):
        L, R, T, B = Qt.Edge.LeftEdge, Qt.Edge.RightEdge, Qt.Edge.TopEdge, Qt.Edge.BottomEdge
        if (e & L and e & T) or (e & R and e & B):
            return Qt.CursorShape.SizeFDiagCursor
        if (e & R and e & T) or (e & L and e & B):
            return Qt.CursorShape.SizeBDiagCursor
        if e & (L | R):
            return Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.SizeVerCursor

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t not in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress, QEvent.Type.Leave):
            return False
        if not self.win.isVisible():
            return False
        if not isinstance(obj, QWidget) or obj.window() is not self.win:
            return False
        if t == QEvent.Type.Leave:
            return False
        e = self._edges(ev.globalPosition())
        if t == QEvent.Type.MouseMove:
            if e and not (ev.buttons() & Qt.MouseButton.LeftButton):
                cur = self._cursor(e)
                if self._cursor_on:
                    QGuiApplication.changeOverrideCursor(cur)
                else:
                    QGuiApplication.setOverrideCursor(cur)
                    self._cursor_on = True
            elif self._cursor_on:
                QGuiApplication.restoreOverrideCursor()
                self._cursor_on = False
            return False
        if e and ev.button() == Qt.MouseButton.LeftButton:
            h = self.win.windowHandle()
            if h is not None:
                h.startSystemResize(e)
                return True
        return False
