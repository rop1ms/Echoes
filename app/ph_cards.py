"""Содержимое карточек-виджетов слева в виде Phantom (этап 6).

Виды Phantom: живой спектр, круговой визуализатор, индикатор уровня, статистика, эквалайзер, часы, далее в очереди,
о треке. Наши: погода, друзья в Echoes.NET, ачивки.

Скорость: звуковые виды (спектр, круг, уровень) перерисовываются ~30 раз в секунду и только пока карточка видна,
окно не свёрнуто и музыка играет; остальные — раз в секунду и только если что-то поменялось. Тяжёлое (погода из
сети, подсчёт ачивок по истории) — в фоне и с кэшем.
"""
from __future__ import annotations

import json
import math
import threading
import time

import numpy as np
from PyQt6.QtCore import QObject, QPointF, QRectF, Qt, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

import ph_style as ph
from frameclock import FrameTimer

WEEKDAYS = ("ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС")
MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря")

# (вид, кикер, подпись)
KINDS = (("visualizer", "Audio visualizer", "Живой спектр аудиосигнала"),
         ("circle", "Circular visualizer", "Спектр по кругу"),
         ("meter", "Level meter", "Громкость сигнала, дБ"),
         ("stats", "Statistics", "Сколько вы слушаете"),
         ("eq", "Equalizer", "Тяните полосы мышью"),
         ("clock", "Clock", "Минималистичные часы"),
         ("queue", "Queue", "Далее в очереди"),
         ("info", "Music information", "Формат и файл трека"),
         ("weather", "Weather", "Погода за окном"),
         ("friends", "Echoes.NET", "Что слушают друзья"),
         ("achievements", "Achievements", "Ближайшие ачивки"))
AUDIO = {"visualizer", "circle", "meter"}

NBARS = 28


def _title(t) -> str:
    from yamusic_theme import sanitize_title
    return sanitize_title((t or {}).get("title", "") or "Без названия")


def _artist(t) -> str:
    return (t or {}).get("artist") or "Неизвестный исполнитель"


def _hm(sec: float) -> str:
    sec = int(sec or 0)
    h, m = sec // 3600, sec % 3600 // 60
    return f"{h}ч {m:02d}м" if h else f"{m} мин"


# ── звук: спектр и уровень из последних семплов движка ── #

class _Audio:
    """Общий анализ звука для всех карточек: один FFT на кадр, сглаживание как у Phantom (быстро вверх,
    плавно вниз), пиковое удержание у индикатора."""

    def __init__(self):
        self.bars = np.zeros(NBARS, np.float32)
        self.rms = self.peak = self.hold = 0.0
        self._hold_t = 0.0
        self._t = 0.0
        self._edges = None
        self._win = None

    def update(self, win) -> bool:
        now = time.monotonic()
        if now - self._t < .025:                               # две карточки — один расчёт на кадр
            return True
        dt = min(.1, now - self._t) if self._t else .033
        self._t = now
        eng = getattr(win, "engine", None)
        s = None
        try:
            if eng is not None and eng.is_playing():
                s = eng.get_visual_samples(2048)
        except Exception:                                      # noqa: BLE001
            s = None
        fall = math.exp(-dt / .18)
        if s is None or len(s) < 256:
            self.bars *= fall
            self.rms *= fall
            self.peak *= fall
            self.hold = max(self.peak, self.hold - dt * .5)
            return bool(self.bars.max() > .01 or self.hold > .01)
        a = np.asarray(s, np.float32)
        n = len(a)
        if self._win is None or len(self._win) != n:
            self._win = np.hanning(n).astype(np.float32)
            sr = float(getattr(eng, "visual_sample_rate", 44100) or 44100)
            freqs = np.fft.rfftfreq(n, 1.0 / sr)
            lo, hi = 40.0, min(16000.0, sr / 2)
            e = np.geomspace(lo, hi, NBARS + 1)
            self._edges = [max(1, int(np.searchsorted(freqs, f))) for f in e]
        mag = np.abs(np.fft.rfft(a * self._win)) / (n / 4)
        ed = self._edges
        raw = np.array([mag[ed[i]:max(ed[i] + 1, ed[i + 1])].max() for i in range(NBARS)], np.float32)
        db = 20 * np.log10(raw + 1e-6)
        lvl = np.clip((db + 62) / 56, 0, 1)                    # −62…−6 дБ → 0…1
        lvl *= np.linspace(.86, 1.12, NBARS)                   # высокие тише — чуть подтянуть
        self.bars = np.maximum(np.clip(lvl, 0, 1), self.bars * fall)
        r = float(np.sqrt(np.mean(a * a)))
        pk = float(np.max(np.abs(a)))
        self.rms = max(r, self.rms * fall)
        self.peak = max(pk, self.peak * fall)
        if self.peak >= self.hold or now - self._hold_t > 1.2:
            self.hold, self._hold_t = self.peak, now
        return True


AUDIO_STATE = _Audio()


# ── данные в фоне: погода, ачивки ── #

class _Bg(QObject):
    done = pyqtSignal(str)


BG = None
_CACHE: dict = {}


def _bg():
    global BG
    if BG is None:
        BG = _Bg()
    return BG


def _run_bg(key: str, fn, ttl: float):
    """Посчитать fn() в фоне и положить в _CACHE[key]; повторно — не чаще ttl секунд."""
    ent = _CACHE.get(key)
    now = time.time()
    if ent is not None and (ent[1] == "busy" or now - ent[1] < ttl):
        return ent[0]
    old = ent[0] if ent else None
    _CACHE[key] = (old, "busy")
    sig = _bg()

    def work():
        try:
            val = fn()
        except Exception as e:                                 # noqa: BLE001
            val = {"error": str(e)[:80]}
        _CACHE[key] = (val, time.time())
        try:
            sig.done.emit(key)
        except RuntimeError:
            pass
    threading.Thread(target=work, daemon=True, name=f"ph-card-{key}").start()
    return old


def weather_city(win) -> str:
    s = getattr(win, "settings", {}) or {}
    city = str(s.get("owm_city") or "").strip()
    if not city:
        try:
            import ya_decor
            city = str(ya_decor.cfg().get("weather_city") or "").strip()
        except Exception:                                      # noqa: BLE001
            city = ""
    return city


ACH = {"melomane": ("Меломан", "часов музыки"), "collector": ("Коллекционер", "треков в коллекции"),
       "night_owl": ("Ночной слушатель", "ночных прослушиваний"),
       "early_bird": ("Жаворонок", "утренних прослушиваний"), "streak7": ("7 дней подряд", "дней подряд"),
       "explorer": ("Исследователь", "разных исполнителей"),
       "loyal": ("Преданный фанат", "прослушиваний одного исполнителя"),
       "marathon": ("Марафон", "часов за день")}


def _achievements(win) -> list:
    """[(название, есть, нужно, подпись)] — слушательские ачивки, ближайшие к получению первыми."""
    import net_ach
    cur = net_ach.listening_counts(win)
    cur["melomane"] = int(float((win.stats.data or {}).get("total") or 0) // 3600)
    cur["collector"] = len(getattr(win, "library", []) or [])
    out = []
    for k, (name, unit) in ACH.items():
        need = net_ach.NEED.get(k, 1)
        have = min(int(cur.get(k, 0)), need)
        out.append((name, have, need, unit))
    out.sort(key=lambda x: (x[1] >= x[2], -(x[1] / max(1, x[2]))))
    return out


def _friends(win) -> list | None:
    """[(имя, что слушает или '')] друзей в сети; None — Echoes.NET не включён."""
    sh = getattr(win, "_ya", None)
    page = sh.pages.get("net") if sh is not None else None
    if page is None or not getattr(page, "node", None) or not page.running():
        return None
    out = []
    for c in page.node.store.contacts("friend"):
        if not page.node.is_online(c["onion"]):
            continue
        now = ""
        try:
            n = json.loads(c["now"]) if c["now"] else None
            if n:
                now = f"{n.get('artist', '')} — {n.get('title', '')}"
        except Exception:                                      # noqa: BLE001
            now = ""
        out.append((c["name"] or c["onion"][:8], now))
    out.sort(key=lambda x: not x[1])
    return out


# ══════════════════════════════════════════════════════════════════════════ #

class WidgetBody(QWidget):
    """Тело карточки-виджета: рисует выбранный вид. card — PhWidgetCard (widget_kind(), lay)."""

    def __init__(self, card):
        super().__init__(card)
        self.card = card
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self._sig = None
        self._timer = FrameTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._frame)
        self._eq_drag = -1
        self._slide = None                                     # (снимок прежнего вида, направление, t0)
        self._slide_anim = QVariantAnimation(self)
        self._slide_anim.setStartValue(0.0)
        self._slide_anim.setEndValue(1.0)
        self._slide_anim.valueChanged.connect(lambda _v: self.update())
        self._slide_anim.finished.connect(self._slide_done)
        _bg().done.connect(self._on_bg)

    def slide(self, old_pm, d: int):
        dur = ph.duration(260)
        if dur <= 0:
            return
        self._slide = (old_pm, 1 if d > 0 else -1)
        self._slide_anim.stop()
        self._slide_anim.setDuration(dur)
        self._slide_anim.setEasingCurve(ph.ease_out())
        self._slide_anim.start()

    def _slide_done(self):
        self._slide = None
        self.update()

    # ── обновление ── #
    def kind_changed(self):
        self._sig = None
        self._sync_timer()
        self.tick()
        self.update()

    def _sync_timer(self):
        w = self.window()
        run = (self.card.widget_kind() in AUDIO and self.isVisible() and not (w and w.isMinimized()))
        if run and not self._timer.isActive():
            self._timer.start()
        elif not run and self._timer.isActive():
            self._timer.stop()

    def showEvent(self, e):
        super().showEvent(e)
        self._sync_timer()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._sync_timer()

    def _frame(self):
        w = self.window()
        if w is not None and w.isMinimized():
            return
        if AUDIO_STATE.update(self.card.lay.win) or self.__dict__.get("_was_live"):
            self.update()
        self._was_live = bool(AUDIO_STATE.bars.max() > .01)

    def tick(self):
        """Раз в секунду: перерисовать, только если поменялись данные вида."""
        self._sync_timer()
        sig = self._signature()
        if sig != self._sig:
            self._sig = sig
            self.update()

    def _on_bg(self, _key):
        self._sig = None
        self.tick()

    def _signature(self):
        k = self.card.widget_kind()
        lay = self.card.lay
        win = lay.win
        if k in AUDIO:
            return (k,)
        if k == "clock":
            return ("clock", time.strftime("%H:%M"))
        if k == "queue":
            return ("queue", tuple(str(t.get("path", "")) for t in lay.upcoming(3)))
        if k == "info":
            return ("info", str((lay.shell.current_track() or {}).get("path", "")))
        if k == "stats":
            d = (win.stats.data.get("days") or {}).get(time.strftime("%Y-%m-%d"), 0)
            return ("stats", int(d // 60))
        if k == "eq":
            return ("eq", tuple(sl.value() for sl in getattr(win, "_eq_sliders", []) or []),
                    str((win.settings or {}).get("eq_preset", "")))
        if k == "weather":
            city = weather_city(win)
            val = _run_bg("weather:" + city, lambda: __import__("ya_weather").fetch(city), 1800) if city else None
            return ("weather", city, json.dumps(val, default=str, sort_keys=True))
        if k == "friends":
            return ("friends", repr(_friends(win)))
        if k == "achievements":
            return ("ach", repr(_run_bg("ach", lambda: _achievements(win), 300)))
        return (k,)

    # ── эквалайзер: тянуть полосы мышью ── #
    def _eq_band_at(self, x: float) -> int:
        n = 10
        r = self._eq_rect()
        if r.width() <= 0:
            return -1
        return max(0, min(n - 1, int((x - r.left()) / (r.width() / n))))

    def _eq_rect(self) -> QRectF:
        r = QRectF(self.rect())
        return QRectF(r.left(), r.top() + ph.px(6), r.width() - ph.px(4), r.height() - ph.px(22))

    def _eq_set(self, pos):
        sl = getattr(self.card.lay.win, "_eq_sliders", None) or []
        i = self._eq_band_at(pos.x())
        if i < 0 or i >= len(sl):
            return
        r = self._eq_rect()
        k = 1.0 - (pos.y() - r.top()) / max(1.0, r.height())
        sl[i].setValue(int(round(max(-1.0, min(1.0, k * 2 - 1)) * 20)))
        self._sig = None
        self.update()

    def mousePressEvent(self, e):
        if self.card.widget_kind() == "eq" and e.button() == Qt.MouseButton.LeftButton:
            self._eq_drag = self._eq_band_at(e.position().x())
            self._eq_set(e.position())
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._eq_drag >= 0:
            self._eq_set(e.position())
        if self.card.widget_kind() == "eq":
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.unsetCursor()

    def mouseReleaseEvent(self, e):
        self._eq_drag = -1

    def mouseDoubleClickEvent(self, e):
        if self.card.widget_kind() == "eq":                    # двойной щелчок — полосу в ноль
            sl = getattr(self.card.lay.win, "_eq_sliders", None) or []
            i = self._eq_band_at(e.position().x())
            if 0 <= i < len(sl):
                sl[i].setValue(0)
                self.update()

    # ── отрисовка ── #
    def paintEvent(self, e):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            r = QRectF(self.rect())
            k = self.card.widget_kind()
            fn = getattr(self, "_paint_" + k, None)
            sl = self._slide
            if sl is not None:                                 # перелистывание: старый уезжает, новый въезжает
                e = float(self._slide_anim.currentValue() or 0.0)
                pm, d = sl
                shift = r.width() * .28
                p.save()
                p.setOpacity(max(0.0, 1.0 - e * 1.4))
                p.drawPixmap(QPointF(-d * shift * e, 0), pm)
                p.restore()
                p.setOpacity(min(1.0, e * 1.2))
                p.translate(d * shift * (1.0 - e), 0)
            if fn is not None:
                fn(p, r)
        finally:
            p.end()

    def _paint_visualizer(self, p: QPainter, r: QRectF):
        bars = AUDIO_STATE.bars
        base = r.bottom() - ph.px(10)
        top = r.top() + ph.px(6)
        if bars.max() <= .01:
            ph.paint_hairline(p, r.left(), r.right() - ph.px(4), base, ph.LINE_2)
            return
        n = len(bars)
        gap = max(2.0, r.width() / n * .32)
        bw = max(1.5, (r.width() - ph.px(4) - gap * (n - 1)) / n)
        p.setPen(Qt.PenStyle.NoPen)
        for i, v in enumerate(bars):
            h = max(2.0, float(v) * (base - top))
            x = r.left() + i * (bw + gap)
            p.setBrush(ph.white(.28 + .62 * float(v)))
            p.drawRoundedRect(QRectF(x, base - h, bw, h), bw / 2, bw / 2)
            p.setBrush(ph.white(.06 * float(v)))                # слабое отражение под линией
            p.drawRoundedRect(QRectF(x, base + 2, bw, h * .22), bw / 2, bw / 2)

    def _paint_circle(self, p: QPainter, r: QRectF):
        bars = AUDIO_STATE.bars
        cx, cy = r.center().x(), r.center().y() - ph.px(2)
        R = max(8.0, min(r.height(), r.width()) / 2 - ph.px(10))
        r0 = R * .55
        n = 56
        lvl = np.interp(np.linspace(0, len(bars) - 1, n // 2), np.arange(len(bars)), bars)
        vals = np.concatenate([lvl, lvl[::-1]])                # симметрично, как у Phantom
        p.setPen(QPen(ph.white(.10), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r0, r0)
        for i, v in enumerate(vals):
            a = 2 * math.pi * i / n - math.pi / 2
            ln = (R - r0) * (.08 + .92 * float(v))
            c, s = math.cos(a), math.sin(a)
            p.setPen(QPen(ph.white(.25 + .65 * float(v)), max(1.4, R * .045), Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(cx + c * (r0 + 3), cy + s * (r0 + 3)), QPointF(cx + c * (r0 + 3 + ln),
                                                                            cy + s * (r0 + 3 + ln)))
        img = self.card.lay.cover._img                          # в центре — обложка кружком
        if not img.isNull() and r0 > 10:
            path = QPainterPath()
            rr = r0 - 3
            path.addEllipse(QPointF(cx, cy), rr, rr)
            p.save()
            p.setClipPath(path)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            pm = self.__dict__.get("_circ_pm")
            key = (img.cacheKey(), int(rr))
            if pm is None or self.__dict__.get("_circ_k") != key:
                d = int(rr * 2 * max(1.0, self.devicePixelRatioF()))
                pm = img.scaled(d, d, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                Qt.TransformationMode.SmoothTransformation)
                self._circ_pm, self._circ_k = pm, key
            p.drawImage(QRectF(cx - rr, cy - rr, 2 * rr, 2 * rr), pm,
                        QRectF((pm.width() - min(pm.width(), pm.height())) / 2,
                               (pm.height() - min(pm.width(), pm.height())) / 2,
                               min(pm.width(), pm.height()), min(pm.width(), pm.height())))
            p.restore()

    def _paint_meter(self, p: QPainter, r: QRectF):
        st = AUDIO_STATE

        def db(v):
            return 20 * math.log10(max(1e-5, v))
        rows = (("RMS", st.rms, None), ("PEAK", st.peak, st.hold))
        y = r.top() + ph.px(8)
        segs = 24
        lab_w = ph.px(40)
        val_w = ph.px(48)
        x0, x1 = r.left() + lab_w, r.right() - val_w
        sw = (x1 - x0) / segs
        h = max(4.0, min(ph.px(10), (r.height() - ph.px(26)) / 2))
        for name, v, hold in rows:
            p.setFont(ph.font(ph.TEXT_2XS, 600, .08))
            p.setPen(ph.qcolor(ph.TEXT_TERTIARY))
            p.drawText(QRectF(r.left(), y - 2, lab_w, h + 4), Qt.AlignmentFlag.AlignVCenter, name)
            k = max(0.0, min(1.0, (db(v) + 60) / 60))             # −60…0 дБ
            on = int(round(k * segs))
            p.setPen(Qt.PenStyle.NoPen)
            for i in range(segs):
                lit = i < on
                hot = i >= segs - 3
                a = (.92 if hot else .72) if lit else .07
                p.setBrush(ph.white(a))
                p.drawRoundedRect(QRectF(x0 + i * sw + 1, y, sw - 2, h), 1.5, 1.5)
            if hold is not None and hold > 1e-4:
                hk = max(0.0, min(1.0, (db(hold) + 60) / 60))
                hx = x0 + min(segs - 1, int(hk * segs)) * sw + 1
                p.setBrush(ph.white(.95))
                p.drawRect(QRectF(hx, y - 2, 2, h + 4))
            p.setFont(ph.font(ph.TEXT_2XS, 600, tnum=True))
            p.setPen(ph.qcolor(ph.TEXT_SECONDARY))
            txt = "−∞" if v < 1e-4 else f"{db(v):.1f}".replace("-", "−")
            p.drawText(QRectF(x1 + ph.px(6), y - 2, val_w - ph.px(6), h + 4),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, txt + " дБ")
            y += h + ph.px(12)

    def _paint_stats(self, p: QPainter, r: QRectF):
        win = self.card.lay.win
        st = win.stats
        days = st.data.get("days") or {}
        today = days.get(time.strftime("%Y-%m-%d"), 0)
        week = st.seconds_since(7) if hasattr(st, "seconds_since") else 0
        top = st.top_artists(1) if hasattr(st, "top_artists") else []
        fav = top[0][0] if top and isinstance(top[0], (list, tuple)) else (top[0] if top else "—")
        # слева — цифры, справа — столбики за 7 дней
        chart_w = min(r.width() * .32, ph.px(100))
        rows = (("День", _hm(today)), ("7 дней", _hm(week)), ("Топ", str(fav) or "—"))
        self._rows(p, QRectF(r.left(), r.top(), r.width() - chart_w - ph.px(8), r.height()), rows, ph.px(52))
        vals = []
        for i in range(6, -1, -1):
            d = time.strftime("%Y-%m-%d", time.localtime(time.time() - i * 86400))
            vals.append(float(days.get(d, 0)))
        mx = max(vals) or 1.0
        cx0 = r.right() - chart_w
        base = r.bottom() - ph.px(14)
        top_y = r.top() + ph.px(10)
        bw = chart_w / 7 * .56
        p.setPen(Qt.PenStyle.NoPen)
        for i, v in enumerate(vals):
            h = max(2.0, v / mx * (base - top_y))
            x = cx0 + i * chart_w / 7 + (chart_w / 7 - bw) / 2
            p.setBrush(ph.white(.85 if i == 6 else .26))
            p.drawRoundedRect(QRectF(x, base - h, bw, h), bw / 2, bw / 2)
        p.setFont(ph.font(ph.TEXT_2XS, 500))
        p.setPen(ph.qcolor(ph.TEXT_GHOST))
        wd = time.localtime().tm_wday
        for i in range(7):
            x = cx0 + i * chart_w / 7
            p.drawText(QRectF(x, base + 2, chart_w / 7, ph.px(12)), Qt.AlignmentFlag.AlignCenter,
                       WEEKDAYS[(wd - 6 + i) % 7][:1].upper())

    def _paint_eq(self, p: QPainter, r: QRectF):
        win = self.card.lay.win
        sl = getattr(win, "_eq_sliders", None) or []
        if not sl:
            self._center_text(p, r, "Эквалайзер недоступен")
            return
        er = self._eq_rect()
        n = len(sl)
        cw = er.width() / n
        mid = er.center().y()
        p.setPen(QPen(ph.white(.08), 1.0))
        p.drawLine(QPointF(er.left(), mid), QPointF(er.right(), mid))
        labels = ("31", "62", "125", "250", "500", "1K", "2K", "4K", "8K", "16K")
        for i, s in enumerate(sl):
            v = s.value() / 20.0
            x = er.left() + i * cw + cw / 2
            p.setPen(QPen(ph.white(.10), max(2.0, cw * .18), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(x, er.top() + 2), QPointF(x, er.bottom() - 2))
            y = mid - v * (er.height() / 2 - 3)
            p.setPen(QPen(ph.white(.85), max(2.0, cw * .18), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(x, mid), QPointF(x, y))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ph.white(.96))
            p.drawEllipse(QPointF(x, y), max(2.5, cw * .16), max(2.5, cw * .16))
            if cw >= ph.px(18):
                p.setFont(ph.font(ph.TEXT_2XS - 1, 500))
                p.setPen(ph.qcolor(ph.TEXT_GHOST))
                p.drawText(QRectF(x - cw / 2, er.bottom() + 2, cw, ph.px(14)), Qt.AlignmentFlag.AlignCenter,
                           labels[i] if i < len(labels) else "")

    def _paint_clock(self, p: QPainter, r: QRectF):
        tm = time.localtime()
        cx, cy = r.left() + ph.px(28), r.center().y() + ph.px(2)
        rad = ph.px(24)
        p.setPen(QPen(ph.white(.12), 1.5))
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        frac = (tm.tm_hour % 12 * 60 + tm.tm_min) / 720.0
        p.setPen(QPen(ph.white(.86), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(QRectF(cx - rad, cy - rad, 2 * rad, 2 * rad), 90 * 16, int(-frac * 360 * 16))
        x = cx + rad + ph.px(16)
        p.setFont(ph.font(17, 650, -.01, tnum=True))
        p.setPen(ph.qcolor(ph.TEXT_PRIMARY))
        p.drawText(QPointF(x, cy + ph.px(1)), time.strftime("%H:%M", tm))
        p.setFont(ph.font(ph.TEXT_2XS, 500))
        p.setPen(ph.qcolor(ph.TEXT_TERTIARY))
        p.drawText(QPointF(x, cy + ph.px(17)),
                   f"{WEEKDAYS[tm.tm_wday]} · {tm.tm_mday} {MONTHS[tm.tm_mon - 1]} {tm.tm_year}")

    def _paint_info(self, p: QPainter, r: QRectF):
        t = self.card.lay.shell.current_track() or {}
        path = str(t.get("path", ""))
        ext = path.rsplit(".", 1)[-1].upper() if "." in path[-6:] else ("ONLINE" if path else "—")
        rows = (("Формат", ext), ("Исполнитель", _artist(t) if t else "—"), ("Альбом", t.get("album") or "—"))
        self._rows(p, r, rows)

    def _paint_queue(self, p: QPainter, r: QRectF):
        nx = self.card.lay.upcoming(3)
        rows = [(f"{i + 1:02d}", f"{_title(t)} — {_artist(t)}") for i, t in enumerate(nx)] or [("", "Очередь пуста")]
        self._rows(p, r, rows)

    def _paint_weather(self, p: QPainter, r: QRectF):
        win = self.card.lay.win
        city = weather_city(win)
        if not city:
            self._center_text(p, r, "Укажите город: Настройки → «Погода и ключи»")
            return
        w = (_CACHE.get("weather:" + city) or (None,))[0]
        if not w:
            self._center_text(p, r, "Загружаю погоду…")
            return
        if w.get("error"):
            self._center_text(p, r, str(w["error"]))
            return
        import ya_weather
        icon = {"rain": "waves-horizontal", "storm": "waves-horizontal", "fog": "waves-horizontal",
                "snow": "sparkles"}.get(w.get("kind"), "cloud-sun")
        cy = r.center().y()
        ic = ph.icon_pixmap(icon, 26, ph.TEXT_SECONDARY)
        p.drawPixmap(QPointF(r.left() + ph.px(2), cy - ph.px(13)), ic)
        t = w.get("temp")
        temp = (f"{round(t):+d}°".replace("+0", "0").replace("-", "−")) if isinstance(t, (int, float)) else "—"
        x = r.left() + ph.px(42)
        p.setFont(ph.font(22, 650, -.02, tnum=True))
        p.setPen(ph.qcolor(ph.TEXT_PRIMARY))
        fm = QFontMetrics(p.font())
        p.drawText(QPointF(x, cy + fm.ascent() / 2 - ph.px(2)), temp)
        x2 = x + fm.horizontalAdvance(temp) + ph.px(14)
        p.setFont(ph.font(ph.TEXT_XS, 550))
        p.setPen(ph.qcolor(ph.TEXT_SECONDARY))
        f2 = QFontMetrics(p.font())
        kind = ya_weather.KINDS.get(w.get("kind"), "") if hasattr(ya_weather, "KINDS") else ""
        p.drawText(QPointF(x2, cy - ph.px(2)), f2.elidedText(str(kind).capitalize(), Qt.TextElideMode.ElideRight,
                                                             int(r.right() - x2)))
        p.setFont(ph.font(ph.TEXT_2XS, 500))
        p.setPen(ph.qcolor(ph.TEXT_TERTIARY))
        p.drawText(QPointF(x2, cy + ph.px(13)), QFontMetrics(p.font()).elidedText(
            str(w.get("city") or city), Qt.TextElideMode.ElideRight, int(r.right() - x2)))

    def _paint_friends(self, p: QPainter, r: QRectF):
        fr = _friends(self.card.lay.win)
        if fr is None:
            self._center_text(p, r, "Echoes.NET выключен")
            return
        if not fr:
            self._center_text(p, r, "Никого из друзей нет в сети")
            return
        rows = [(name, now or "в сети") for name, now in fr[:3]]
        self._rows(p, r, rows, ph.px(78), live=[bool(now) for _n, now in fr[:3]])

    def _paint_achievements(self, p: QPainter, r: QRectF):
        val = (_CACHE.get("ach") or (None,))[0]
        if not val or isinstance(val, dict):
            self._center_text(p, r, "Считаю…" if not val else "Не удалось посчитать")
            return
        y = r.top() + ph.px(8)
        step = max(ph.px(18), min(ph.px(24), (r.height() - ph.px(8)) / 3))
        for name, have, need, unit in val[:3]:
            if y + step > r.bottom() + 2:
                break
            p.setFont(ph.font(ph.TEXT_XS, 550))
            p.setPen(ph.qcolor(ph.TEXT_PRIMARY if have < need else ph.TEXT_TERTIARY))
            nw = min(r.width() * .45, ph.px(118))
            p.drawText(QRectF(r.left(), y, nw, step - 6), Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(p.font()).elidedText(name, Qt.TextElideMode.ElideRight, int(nw)))
            bx, bw = r.left() + nw + ph.px(8), r.width() - nw - ph.px(64)
            by = y + (step - 6) / 2 - 2
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ph.white(.08))
            p.drawRoundedRect(QRectF(bx, by, bw, 4), 2, 2)
            p.setBrush(ph.white(.85))
            p.drawRoundedRect(QRectF(bx, by, bw * min(1.0, have / max(1, need)), 4), 2, 2)
            p.setFont(ph.font(ph.TEXT_2XS, 600, tnum=True))
            p.setPen(ph.qcolor(ph.TEXT_SECONDARY))
            p.drawText(QRectF(bx + bw + ph.px(6), y, ph.px(56), step - 6),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       "есть" if have >= need else f"{have}/{need}")
            y += step

    # ── общие ── #
    @staticmethod
    def _center_text(p: QPainter, r: QRectF, text: str):
        p.setFont(ph.font(ph.TEXT_XS, 500))
        p.setPen(ph.qcolor(ph.TEXT_TERTIARY))
        p.drawText(r.adjusted(0, 0, -ph.px(4), 0), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)

    @staticmethod
    def _rows(p: QPainter, r: QRectF, rows, label_w=None, live=None):
        y = r.top() + ph.px(8)
        step = max(ph.px(16), min(ph.px(22), (r.height() - ph.px(8)) / max(1, len(rows))))
        for i, (a, b) in enumerate(rows):
            if y + step > r.bottom() + 4:
                break
            p.setFont(ph.font(ph.TEXT_2XS, 600, .08))
            p.setPen(ph.qcolor(ph.TEXT_TERTIARY))
            num = a[:1].isdigit()
            lw = ph.px(24) if num else (label_w if label_w is not None else ph.px(78))
            p.drawText(QRectF(r.left(), y, lw - ph.px(4), step), Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(p.font()).elidedText(a if num else a.upper(), Qt.TextElideMode.ElideRight,
                                                         int(lw - ph.px(6))))
            p.setFont(ph.font(ph.TEXT_XS, 550))
            p.setPen(ph.qcolor(ph.TEXT_PRIMARY))
            x = r.left() + lw
            if live and i < len(live) and live[i]:              # друг сейчас слушает — точка
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(ph.white(.9))
                p.drawEllipse(QPointF(x + 3, y + step / 2), 2.5, 2.5)
                p.setPen(ph.qcolor(ph.TEXT_PRIMARY))
                x += ph.px(10)
            p.drawText(QRectF(x, y, r.right() - x - ph.px(4), step), Qt.AlignmentFlag.AlignVCenter,
                       p.fontMetrics().elidedText(str(b), Qt.TextElideMode.ElideRight, int(r.right() - x - ph.px(4))))
            y += step
