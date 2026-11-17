"""Заставка при запуске ECHOES — монохромная, без акцентного цвета: из центра вырастает тонкая белая
линия, из-за неё буква за буквой поднимается надпись ECHOES, по ней пробегает блик. Пока плеер грузится,
по линии бежит блик загрузки. Заставка растворяется — и сцена Phantom собирается на глазах (ph_intro).

start_native() — в своём окне и потоке (echoes_ui.dll: intro_win.cpp), ещё до сборки окна плеера;
play(win) — то же самое поверх окна (без DLL и для «Посмотреть» в настройках); клик или клавиша — пропустить.
Время считается по часам, а не по кадрам: если плеер в эти секунды занят, анимация не «тормозит», а пропускает кадры.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QElapsedTimer, QEvent, QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QRadialGradient
from PyQt6.QtWidgets import QWidget

TEXT = "ECHOES"
T_LINE = 0.0            # линия вырастает из центра
LINE_GROW = 0.5
T_TEXT = 0.22           # первая буква
LETTER_STEP = 0.06
LETTER_RISE = 0.5
T_SWEEP = 0.95          # блик по надписи
SWEEP = 0.5
T_OUT = 1.45            # сюжет досмотрен — растворение
T_END = 1.90
LINE_W = 260.0


def _clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def _out_cubic(x):
    x = _clamp(x)
    return 1 - (1 - x) ** 3


def _in_out(x):
    x = _clamp(x)
    return 3 * x * x - 2 * x * x * x


def _font(px) -> QFont:
    try:
        from yamusic_theme import ya_font
        f = ya_font(px, QFont.Weight.Black)
    except Exception:                                          # noqa: BLE001
        f = QFont("Segoe UI", -1, QFont.Weight.Black)
        f.setPixelSize(px)
    return f


def paint(p: QPainter, W: float, H: float, t: float, out: float, hold: float, font: QFont):
    """Кадр заставки (тот же сюжет, что в intro_win.cpp). out — растворение 0..1; hold — сколько секунд
    плеер ещё грузится после сюжета (блик загрузки по линии)."""
    p.fillRect(QRectF(0, 0, W, H), QColor(0, 0, 0))
    a = 1.0 - out
    if a <= 0.01:
        return
    p.setOpacity(a)
    cx, cy = W / 2.0, H / 2.0
    line_y = cy + 30
    lift = -10 * out                                           # на выходе надпись чуть уплывает вверх
    # линия: из центра в стороны, к краям гаснет
    k = _out_cubic((t - T_LINE) / LINE_GROW)
    if k > 0:
        w = LINE_W * k
        g = QLinearGradient(QPointF(cx - w / 2, 0), QPointF(cx + w / 2, 0))
        g.setColorAt(0, QColor(255, 255, 255, 0))
        g.setColorAt(.5, QColor(255, 255, 255, 200))
        g.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(QRectF(cx - w / 2, line_y + lift, w, 1.5), g)
        if k < 1:                                              # светящиеся кончики, пока растёт
            for sx in (-1, 1):
                rg = QRadialGradient(QPointF(cx + sx * w / 2, line_y + lift + .75), 10)
                rg.setColorAt(0, QColor(255, 255, 255, int(180 * (1 - k))))
                rg.setColorAt(1, QColor(255, 255, 255, 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(rg)
                p.drawEllipse(QPointF(cx + sx * w / 2, line_y + lift + .75), 10, 10)
        if hold > 0:                                           # плеер ещё грузится — по линии бежит блик
            ph = math.fmod(hold / 1.2, 1.0)
            bx = cx - w / 2 + (w + 80) * ph - 40
            sg = QLinearGradient(QPointF(bx - 40, 0), QPointF(bx + 40, 0))
            sg.setColorAt(0, QColor(255, 255, 255, 0))
            sg.setColorAt(.5, QColor(255, 255, 255, 255))
            sg.setColorAt(1, QColor(255, 255, 255, 0))
            p.save()
            p.setClipRect(QRectF(cx - w / 2, line_y + lift - 1, w, 4))
            p.fillRect(QRectF(bx - 40, line_y + lift - .5, 80, 2.5), sg)
            p.restore()
    # надпись: буквы поднимаются из-за линии, разрядка сходится
    fm = QFontMetricsF(font)
    spread = 1 - _out_cubic((t - T_TEXT) / 0.8)
    gap = 4 + 22 * spread
    widths = [fm.horizontalAdvance(ch) for ch in TEXT]
    total = sum(widths) + gap * (len(TEXT) - 1)
    base_y = line_y - 14 + lift
    p.save()
    p.setClipRect(QRectF(0, 0, W, line_y + lift - 2))         # из-за линии: ниже неё букв не видно
    p.setFont(font)
    x = cx - total / 2
    path = QPainterPath()
    for j, ch in enumerate(TEXT):
        kj = _out_cubic((t - T_TEXT - j * LETTER_STEP) / LETTER_RISE)
        if kj > 0:
            p.setPen(QColor(228, 228, 228, int(255 * min(1.0, kj * 1.2))))   # чуть серее — блик виден
            p.drawText(QPointF(x, base_y + 70 * (1 - kj)), ch)
        path.addText(QPointF(x, base_y), font, ch)
        x += widths[j] + gap
    p.restore()
    sw = (t - T_SWEEP) / SWEEP
    if 0 < sw < 1:                                             # блик пробегает по надписи
        c = cx - total / 2 - 80 + (total + 160) * sw
        band = QLinearGradient(QPointF(c - 70, 0), QPointF(c + 70, 0))
        band.setColorAt(0, QColor(255, 255, 255, 0))
        band.setColorAt(.5, QColor(255, 255, 255, 230))
        band.setColorAt(1, QColor(255, 255, 255, 0))
        p.save()
        p.setClipPath(path)
        p.fillRect(QRectF(cx - total / 2 - 10, base_y - fm.ascent() - 10, total + 20, fm.height() + 20), band)
        p.restore()
        # под белыми буквами блик не виден — он подсвечивает соседний воздух мягким ореолом
        halo = QRadialGradient(QPointF(c, base_y - fm.ascent() / 2), 90)
        halo.setColorAt(0, QColor(255, 255, 255, int(26 * math.sin(math.pi * sw))))
        halo.setColorAt(1, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(halo)
        p.drawEllipse(QPointF(c, base_y - fm.ascent() / 2), 90, 90)


class IntroOverlay(QWidget):
    """Заставка поверх окна (без DLL; «Посмотреть» в настройках). На растворении — сборка сцены Phantom."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clock = QElapsedTimer()
        self.skip_at = None
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(15)
        self.timer.timeout.connect(self._tick)
        self.big = _font(64)
        self._built = False
        win.installEventFilter(self)
        self.setGeometry(win.rect())
        self.show()                                            # чёрный кадр сразу — интерфейс не мелькает
        self.raise_()
        self._n = 0
        try:
            import ph_intro
            ph_intro.prepare(win)                              # сцена Phantom — под чёрным слоем, до растворения
        except Exception as e:                                 # noqa: BLE001
            print("[intro] ph:", e)

    def _tick(self):
        self._n += 1
        if self._n % 8 == 0:
            self.raise_()                                      # плеер мог создать новые панели поверх
        if not self._built and self.now() >= T_OUT:
            self._built = True
            self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)   # растворяемся — под нами видно
            try:
                import ph_intro
                ph_intro.start(self.win)
            except Exception as e:                             # noqa: BLE001
                print("[intro] ph:", e)
        self.update()

    def start(self):
        self.setGeometry(self.win.rect())
        self.show()
        self.raise_()
        self.setFocus()
        self.clock.start()
        self.timer.start()

    def now(self) -> float:
        t = self.clock.elapsed() / 1000.0 if self.clock.isValid() else 0.0
        if self.skip_at is not None:                           # пропуск — сразу к растворению
            t = T_OUT + (t - self.skip_at) * 1.6
        return t

    def skip(self):
        if self.skip_at is None and self.clock.isValid():
            t = self.clock.elapsed() / 1000.0
            if t < T_OUT:
                self.skip_at = t

    def eventFilter(self, obj, ev):
        if obj is self.win and ev.type() == QEvent.Type.Resize:
            self.setGeometry(self.win.rect())
        return False

    def mousePressEvent(self, e):
        self.skip()

    def keyPressEvent(self, e):
        self.skip()

    def finish(self):
        self.timer.stop()
        try:
            self.win.removeEventFilter(self)
        except RuntimeError:
            pass
        self.hide()
        self.deleteLater()

    def paintEvent(self, _):
        t = self.now()
        if t >= T_END:
            QTimer.singleShot(0, self.finish)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        out = _in_out((t - T_OUT) / (T_END - T_OUT))
        if out > 0:                                            # растворяемся над собирающейся сценой
            p.setOpacity(1.0 - out)
        paint(p, self.width(), self.height(), min(t, T_OUT), 0.0, 0.0, self.big)
        p.end()


# ── заставка в своём потоке (echoes_ui.dll: intro_win.cpp) ── #

def start_native() -> bool:
    """Заставка в своём окне и потоке — сразу после QApplication, ещё до сборки окна плеера: она не
    дёргается, пока плеер строит окно и загружает всё заранее (warmup.preload). False — нет DLL."""
    try:
        import native_ui
        if not native_ui.available() or not hasattr(native_ui._lib, "eui_intro_start"):
            return False
        from PyQt6.QtGui import QGuiApplication
        scr = QGuiApplication.primaryScreen()
        ag = scr.availableGeometry()
        dpr = scr.devicePixelRatio()
        w, h = min(1120, ag.width()), min(720, ag.height())     # там, где откроется окно плеера
        x, y = ag.x() + (ag.width() - w) // 2, ag.y() + (ag.height() - h) // 2
        fam = _font(64).family()
        ok = native_ui._lib.eui_intro_start(int(x * dpr), int(y * dpr), int(w * dpr), int(h * dpr), float(dpr),
                                            255, 255, 255, TEXT, fam)          # без акцента — белым
        return bool(ok)
    except Exception as e:                                     # noqa: BLE001
        print("[intro] native:", e)
        return False


def follow(win):
    """Окно плеера показано — заставка встаёт ровно поверх него; под ней сцена Phantom ждёт сборки."""
    try:
        import ph_intro
        ph_intro.prepare(win)
    except Exception as e:                                     # noqa: BLE001
        print("[intro] ph:", e)
    try:
        import native_ui
        native_ui._lib.eui_intro_follow(int(win.winId()))
    except Exception as e:                                     # noqa: BLE001
        print("[intro] follow:", e)


def ready(win=None):
    """Плеер всё загрузил — заставка досматривает сюжет и растворяется; в этот миг собирается сцена."""
    try:
        import native_ui
        native_ui._lib.eui_intro_ready()
    except Exception as e:                                     # noqa: BLE001
        print("[intro] ready:", e)
    if win is not None:
        _when_native_fades(win)


def _when_native_fades(win):
    """Ждать, пока заставка из DLL начнёт растворяться, и тогда собрать сцену (ph_intro.start)."""
    try:
        import native_ui
        import ph_intro
        lib = native_ui._lib
    except Exception as e:                                     # noqa: BLE001
        print("[intro] ph:", e)
        return
    has_fade = hasattr(lib, "eui_intro_fading")
    clock = QElapsedTimer()
    clock.start()
    timer = QTimer(win)
    timer.setInterval(10)

    def poll():
        try:
            fading = bool(lib.eui_intro_fading()) if has_fade else False
            alive = bool(lib.eui_intro_alive())
        except Exception:                                      # noqa: BLE001
            fading, alive = True, False
        if fading or not alive or clock.elapsed() > 15000:
            timer.stop()
            timer.deleteLater()
            ph_intro.start(win)
    timer.timeout.connect(poll)
    timer.start()
    poll()


def enabled(settings) -> bool:
    return bool((settings or {}).get("intro_anim", True))


def play(win) -> IntroOverlay | None:
    """Показать заставку поверх окна (вызывать сразу после win.show())."""
    try:
        ov = IntroOverlay(win)
        QTimer.singleShot(0, ov.start)
        return ov
    except Exception as e:                                     # noqa: BLE001
        print("[intro]", e)
        return None
