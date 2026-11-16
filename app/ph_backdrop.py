# ph_backdrop.py
"""
Фон Phantom Audio для Echoes: тёмная база с мягкими пятнами света, размытая картинка (фон приложения или
обложка), «атмосфера» — медленные вспышки, дым и пылинки, зерно и виньетка. Повторяет фон Phantom
(компонент фона и его canvas), но устроен так, чтобы почти ничего не стоить:

  * всё неподвижное (база, картинка, затемнение, зерно, виньетка) собирается ОДИН раз в картинку размером
    с окно — при смене размера (с задержкой), картинки или настроек; размытие картинки — в фоновом потоке;
  * вспышки и дым у Phantom движутся с периодом в минуты (скорости 0.005–0.1 рад/с) — их не нужно
    перерисовывать 30 раз в секунду: слой считается в 1/6 размера 4 раза в секунду и смешивается
    с неподвижной картинкой; глазом шаги не видны (сдвиг за шаг меньше пикселя);
  * 30 раз в секунду рисуются только пылинки — 35–50 точек по 1–3 px. Перерисовывается не окно, а
    крошечные прямоугольники вокруг них; пылинки под стеклянными панелями не рисуются вовсе
    (set_occluders) — там их всё равно не видно, а лишняя перерисовка задела бы панели;
  * кадры — через общие часы frameclock; окно свёрнуто или скрыто, «уменьшенное движение» или эффекты
    выключены — таймеры стоят, фон неподвижен.

frozen_blur(widget) — «снимок с размытием» под выезжающие панели: один раз при открытии панели, а не
backdrop-filter на каждом кадре, как в Electron.
"""
from __future__ import annotations

import math
import random
import threading
import time
from pathlib import Path

from frameclock import FrameTimer
from PyQt6.QtCore import QObject, QRect, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QBrush, QColor, QImage, QLinearGradient, QPainter, QPixmap, QRadialGradient, QRegion)
from PyQt6.QtWidgets import QWidget

import ph_style as ph

_ARGB = QImage.Format.Format_ARGB32_Premultiplied
DEFAULT_IMAGE = ph.ASSETS / "ph" / "background.jpg"
ATMO_SCALE = 1 / 6          # слой вспышек и дыма — в 1/6 размера окна
ATMO_MS = 250               # и обновляется 4 раза в секунду
DUST_MS = 33                # пылинки — 30 кадров в секунду (как у Phantom)
REBUILD_DELAY_MS = 120      # пересборка неподвижного слоя после смены размера


def phantom_params(intensity: float, brightness: float = 1.0) -> dict:
    """Те же формулы, что у Phantom (intensity — «Интенсивность фона», brightness — «Яркость фона»)."""
    n = max(0.0, min(1.0, intensity))
    a = max(0.2, min(1.6, brightness))
    return {
        "image_opacity": .35 + n * .55,
        "image_blur": round(22 + n * (36 - 22)),
        "image_brightness": (.42 + n * .18) * a,
        "shade_opacity": .52 - n * .16,
        "base_brightness": 1 + (a - 1) * .35,
        "dust_count": round(35 + (50 - 35) * n),
    }


# ══════════════════════════════════════════════════════════════════════════ #
#  Спрайты и частицы (как у Phantom, с тем же генератором случайных чисел)
# ══════════════════════════════════════════════════════════════════════════ #

def _rng(seed: int = 2654435769):
    """mulberry32 — те же частицы, что у Phantom, при каждом запуске."""
    s = [seed & 0xFFFFFFFF]

    def nxt() -> float:
        s[0] = (s[0] + 1831565813) & 0xFFFFFFFF
        n = s[0]
        n = ((n ^ (n >> 15)) * (n | 1)) & 0xFFFFFFFF
        n ^= (n + (((n ^ (n >> 7)) * (n | 61)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return ((n ^ (n >> 14)) & 0xFFFFFFFF) / 4294967296
    return nxt


def _sprite(size: int, stops) -> QImage:
    img = QImage(size, size, _ARGB)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    g = QRadialGradient(size / 2, size / 2, size / 2)
    for at, a in stops:
        g.setColorAt(at, QColor(255, 255, 255, int(255 * a)))
    p.fillRect(img.rect(), g)
    p.end()
    return img


BLOOMS = [dict(x=.12, y=-.05, radius=.62, alpha=.05, drift=.012, speed=.006, phase=.4),
          dict(x=1.02, y=1.04, radius=.56, alpha=.038, drift=.01, speed=.005, phase=2.1),
          dict(x=.56, y=.42, radius=.36, alpha=.026, drift=.055, speed=.014, phase=4.2)]
TAU = math.pi * 2


def _plumes(r):
    out = []
    for x, y in ((.24, .3), (.7, .58), (.46, .86)):
        blobs = [dict(x=(r() * 2 - 1) * .17, y=(r() * 2 - 1) * .13, radius=.16 + r() * .2, alpha=.012 + r() * .009,
                      driftX=.015 + r() * .032, driftY=.012 + r() * .026, speedX=.03 + r() * .05,
                      speedY=.025 + r() * .045, phaseX=r() * TAU, phaseY=r() * TAU) for _ in range(5)]
        out.append(dict(x=x, y=y, drift=.02 + r() * .03, speed=.006 + r() * .008, phase=r() * TAU, blobs=blobs))
    return out


def _dust(r, n=50):
    out = []
    for _ in range(n):
        d = .35 + r() * .65
        out.append(dict(x=r(), y=r(), depth=d, radius=.7 + r() * 1.6, drift=.004 + r() * .008,
                        speedX=.03 + r() * .09, rise=.004 + r() * .006, phaseX=r() * TAU, phaseY=r() * TAU,
                        alpha=(.11 + r() * .17) * (.35 + d * .65)))
    return out


def _grain_tile(seed: int = 128, size=128) -> QImage:
    """Плитка зерна: чёрные и белые точки с прозрачностью 0..10 % (как у Phantom), numpy — без цикла."""
    import numpy as np
    g = np.random.default_rng(seed)
    v = (g.random((size, size)) > .5).astype(np.float32)
    a = np.floor(g.random((size, size)) * 26).astype(np.float32)
    arr = np.empty((size, size, 4), np.uint8)                  # BGRA, премультиплицированная
    c = (v * a).astype(np.uint8)
    arr[..., 0] = arr[..., 1] = arr[..., 2] = c
    arr[..., 3] = a.astype(np.uint8)
    img = QImage(arr.data, size, size, size * 4, _ARGB)
    return img.copy()


_SPRITES: dict = {}


def _sprites():
    if not _SPRITES:
        r = _rng()
        _SPRITES["plumes"] = _plumes(r)
        _SPRITES["dust"] = _dust(r)
        _SPRITES["bloom"] = _sprite(192, [(0, .92), (.22, .52), (.48, .18), (.74, .045), (1, 0)])
        _SPRITES["smoke"] = _sprite(256, [(0, .62), (.28, .34), (.56, .12), (.8, .028), (1, 0)])
        _SPRITES["dustimg"] = _sprite(64, [(0, .95), (.3, .46), (.62, .13), (1, 0)])
        _SPRITES["grain"] = _grain_tile()
    return _SPRITES


# ══════════════════════════════════════════════════════════════════════════ #
#  Размытая картинка фона — в фоновом потоке
# ══════════════════════════════════════════════════════════════════════════ #

class _ImageJob(QObject):
    done = pyqtSignal(int, QImage)

    def run(self, token: int, src, size: QSize, blur: float, brightness: float):
        def work():
            img = QImage()
            try:
                import blur_fx
                # inset -8 %: картинка на 16 % больше окна, чтобы размытые края не темнели
                w, h = max(8, int(size.width() * 1.16)), max(8, int(size.height() * 1.16))
                q = .25                                         # считаем в четверть размера — всё равно размыто
                img = blur_fx.blurred_cover(src, max(4, int(w * q)), max(4, int(h * q)), blur * q, sat=.48)
                if not img.isNull() and brightness < .999:
                    p = QPainter(img)
                    p.fillRect(img.rect(), QColor(0, 0, 0, int(255 * (1 - max(0.0, brightness)))))
                    p.end()
            except Exception:                                  # noqa: BLE001 — без картинки фон просто тёмный
                img = QImage()
            self.done.emit(token, img)
        threading.Thread(target=work, name="ph-backdrop", daemon=True).start()


class PhBackground(QWidget):
    """Нижний слой оболочки. Дети (колонки, панели) лежат поверх; сам фон мышь не ловит."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._intensity = .6
        self._brightness = 1.0
        self._animated = True
        self._image_src = str(DEFAULT_IMAGE) if DEFAULT_IMAGE.exists() else None
        self._image = QImage()                   # размытая картинка (¼ размера, с запасом 16 %)
        self._image_for: tuple | None = None
        self._token = 0
        self._job = _ImageJob(self)
        self._job.done.connect(self._on_image)
        self._static = QPixmap()                 # база + картинка + затемнение + зерно + виньетка
        self._frame = QPixmap()                  # static + вспышки и дым — то, что рисует paintEvent
        self._atmo_img = QImage()
        self._t0 = time.perf_counter()
        self._time_offset = random.Random(7).random() * 600   # не с нуля: пятна сразу в «середине» пути
        self._dust_rects: list[QRect] = []
        self._occluders: list[QRect] = []
        self._rebuild = QTimer(self)
        self._rebuild.setSingleShot(True)
        self._rebuild.setInterval(REBUILD_DELAY_MS)
        self._rebuild.timeout.connect(self._rebuild_static)
        self._atmo_timer = FrameTimer(self)
        self._atmo_timer.setInterval(ATMO_MS)
        self._atmo_timer.timeout.connect(self._atmo_tick)
        self._dust_timer = FrameTimer(self)
        self._dust_timer.setInterval(DUST_MS)
        self._dust_timer.timeout.connect(self._dust_tick)
        self.stats = {"static_builds": 0, "atmo_frames": 0, "dust_frames": 0}

    # ── настройки ── #
    def configure(self, intensity: float | None = None, brightness: float | None = None,
                  animated: bool | None = None, image=...):
        """image: путь / QImage / None (без картинки); не передан — оставить как есть."""
        changed = False
        if intensity is not None and abs(intensity - self._intensity) > 1e-3:
            self._intensity, changed = float(intensity), True
        if brightness is not None and abs(brightness - self._brightness) > 1e-3:
            self._brightness, changed = float(brightness), True
        if image is not ...:
            self._image_src, self._image_for, self._image = image, None, QImage()
            changed = True
        if animated is not None:
            self._animated = bool(animated)
        if changed:
            self._request_image()
            self._rebuild_static()
        self._sync_timers()

    def set_occluders(self, rects: list[QRect]):
        """Прямоугольники стеклянных панелей (в координатах фона): под ними пылинок нет."""
        self._occluders = [QRect(r) for r in rects]

    def animating(self) -> bool:
        return self._animated and not ph.motion_reduced() and self.isVisible() and \
            not (self.window() and self.window().isMinimized())

    # ── жизненный цикл ── #
    def showEvent(self, e):
        super().showEvent(e)
        self._request_image()
        if self._static.isNull():
            self._rebuild_static()
        self._sync_timers()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._sync_timers()

    def changeEvent(self, e):
        super().changeEvent(e)
        self._sync_timers()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._rebuild.start()
        self._request_image()

    def release(self):
        """Отпустить картинки (окно надолго скрыто): при показе всё соберётся заново."""
        self._atmo_timer.stop()
        self._dust_timer.stop()
        self._static = QPixmap()
        self._frame = QPixmap()
        self._image = QImage()
        self._image_for = None
        self._atmo_img = QImage()

    def _sync_timers(self):
        on = self.animating()
        for t in (self._atmo_timer, self._dust_timer):
            if on and not t.isActive():
                t.start()
            elif not on and t.isActive():
                t.stop()
        if not on and self._dust_rects:
            rects, self._dust_rects = self._dust_rects, []
            self._update_rects(rects)

    # ── картинка ── #
    def _request_image(self):
        if not self.isVisible() or self.width() < 8 or self.height() < 8:
            return
        p = phantom_params(self._intensity, self._brightness)
        want = (str(self._image_src) if not isinstance(self._image_src, QImage) else id(self._image_src),
                self.width() // 32, self.height() // 32, p["image_blur"], round(p["image_brightness"], 3))
        if not self._image_src or want == self._image_for:
            return
        self._image_for = want
        self._token += 1
        self._job.run(self._token, self._image_src, self.size(), p["image_blur"], p["image_brightness"])

    def _on_image(self, token: int, img: QImage):
        if token != self._token:
            return
        self._image = img
        self._rebuild_static()

    # ── неподвижный слой ── #
    def _rebuild_static(self):
        w, h = self.width(), self.height()
        if w < 2 or h < 2:
            return
        self.stats["static_builds"] += 1
        dpr = self.devicePixelRatioF()
        pm = QPixmap(int(w * dpr), int(h * dpr))
        pm.setDevicePixelRatio(dpr)
        p = QPainter(pm)
        try:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            par = phantom_params(self._intensity, self._brightness)
            self._paint_base(p, w, h, par["base_brightness"])
            if not self._image.isNull():
                p.setOpacity(par["image_opacity"])
                p.drawImage(QRectF(-w * .08, -h * .08, w * 1.16, h * 1.16), self._image)
                p.setOpacity(par["shade_opacity"])
                self._paint_shade(p, w, h)
                p.setOpacity(1.0)
            if ph.setting("effects"):
                p.setOpacity(.34)
                p.fillRect(QRectF(0, 0, w, h), QBrush(_sprites()["grain"]))    # плиткой
                p.setOpacity(1.0)
            self._paint_vignette(p, w, h)
        finally:
            p.end()
        self._static = pm
        self._compose()

    @staticmethod
    def _paint_base(p: QPainter, w: float, h: float, bright: float):
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor("#070707"))
        g.setColorAt(.46, QColor("#050505"))
        g.setColorAt(1, QColor("#030303"))
        p.fillRect(QRectF(0, 0, w, h), g)
        for cx, cy, rx, ry, a, stop in ((.10, -.12, 1.18, .88, .05, .62), (1.04, 1.06, .92, .78, .03, .64),
                                        (.64, .44, .70, .60, .018, .70)):
            p.save()
            p.translate(w * cx, h * cy)
            p.scale(rx * w / 2, ry * h / 2)
            rg = QRadialGradient(0, 0, 1)
            rg.setColorAt(0, QColor(255, 255, 255, int(255 * a * bright)))
            rg.setColorAt(stop, QColor(255, 255, 255, 0))
            p.fillRect(QRectF(-1, -1, 2, 2), rg)
            p.restore()

    @staticmethod
    def _paint_shade(p: QPainter, w: float, h: float):
        p.save()
        p.translate(w * .5, h * .42)
        p.scale(w * 1.2 / 2, h * 1.0 / 2)
        rg = QRadialGradient(0, 0, 1)
        rg.setColorAt(0, QColor(5, 5, 5, 0x1f))
        rg.setColorAt(.62, QColor(5, 5, 5, 0x6b))
        rg.setColorAt(1, QColor(5, 5, 5, 0x9e))
        p.fillRect(QRectF(-2, -2, 4, 4), rg)
        p.restore()
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor(5, 5, 5, 0x6b))
        g.setColorAt(.4, QColor(5, 5, 5, 0x42))
        g.setColorAt(1, QColor(5, 5, 5, 0x8f))
        p.fillRect(QRectF(0, 0, w, h), g)

    @staticmethod
    def _paint_vignette(p: QPainter, w: float, h: float):
        p.save()
        p.translate(w * .5, h * .47)
        m = max(w, h) * .78
        rg = QRadialGradient(0, 0, m, 0, 0, min(w, h) * .22)
        rg.setColorAt(0, QColor(0, 0, 0, 0))
        rg.setColorAt(.58, QColor(0, 0, 0, 20))
        rg.setColorAt(.82, QColor(0, 0, 0, 61))
        rg.setColorAt(1, QColor(0, 0, 0, 117))
        p.fillRect(QRectF(-w, -h, 2 * w, 2 * h), rg)
        p.restore()
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor(0, 0, 0, 46))
        g.setColorAt(.16, QColor(0, 0, 0, 0))
        g.setColorAt(.84, QColor(0, 0, 0, 0))
        g.setColorAt(1, QColor(0, 0, 0, 61))
        p.fillRect(QRectF(0, 0, w, h), g)

    # ── вспышки и дым ── #
    def _time(self) -> float:
        return time.perf_counter() - self._t0 + self._time_offset

    def _render_atmo(self):
        w, h = self.width(), self.height()
        aw, ah = max(4, int(w * ATMO_SCALE)), max(4, int(h * ATMO_SCALE))
        if self._atmo_img.size() != QSize(aw, ah):
            self._atmo_img = QImage(aw, ah, _ARGB)
        img = self._atmo_img
        img.fill(Qt.GlobalColor.transparent)
        n = self._intensity
        if n <= .001:
            return
        sp = _sprites()
        t = self._time()
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        mx = max(aw, ah)
        for b in BLOOMS:
            u = math.sin(t * b["speed"] + b["phase"]) * b["drift"]
            m = math.cos(t * b["speed"] * .83 + b["phase"] * 1.7) * b["drift"] * .7
            a = b["alpha"] * n
            r = b["radius"] * mx
            p.setOpacity(a)
            p.drawImage(QRectF((b["x"] + u) * aw - r, (b["y"] + m) * ah - r, 2 * r, 2 * r), sp["bloom"])
        for pl in sp["plumes"]:
            ux = (pl["x"] + math.sin(t * pl["speed"] + pl["phase"]) * pl["drift"]) * aw
            uy = (pl["y"] + math.cos(t * pl["speed"] * .77 + pl["phase"] * 1.31) * pl["drift"] * .6) * ah
            for c in pl["blobs"]:
                hx = (c["x"] + math.sin(t * c["speedX"] + c["phaseX"]) * c["driftX"]) * mx
                hy = (c["y"] + math.cos(t * c["speedY"] + c["phaseY"]) * c["driftY"]) * mx
                r = c["radius"] * mx
                p.setOpacity(c["alpha"] * n)
                p.drawImage(QRectF(ux + hx - r, uy + hy - r, 2 * r, 2 * r), sp["smoke"])
        p.end()

    def _compose(self):
        """frame = неподвижный слой + вспышки и дым (растянутые из 1/6)."""
        if self._static.isNull():
            return
        if not ph.setting("effects"):
            self._frame = self._static
            self.update()
            return
        self._render_atmo()
        pm = QPixmap(self._static)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.drawImage(QRectF(0, 0, self.width(), self.height()), self._atmo_img)
        p.end()
        self._frame = pm
        self.update()

    def _atmo_tick(self):
        if not self.animating():
            self._sync_timers()
            return
        self.stats["atmo_frames"] += 1
        self._compose()

    # ── пылинки ── #
    def _dust_positions(self):
        """(x, y, радиус, прозрачность) каждой видимой пылинки — по формулам Phantom."""
        w, h = self.width(), self.height()
        t = self._time()
        n = phantom_params(self._intensity)["dust_count"]
        out = []
        for d in _sprites()["dust"][:n]:
            m = d["depth"]
            x = (d["x"] + math.sin(t * d["speedX"] + d["phaseX"]) * d["drift"] * m) % 1.0
            y = (d["y"] - t * d["rise"] * m + math.sin(t * d["speedX"] * .7 + d["phaseY"]) * .005 * m) % 1.0
            r = d["radius"] * (.7 + m * .7)
            out.append((x * w, y * h, r, d["alpha"] * self._intensity))
        return out

    def _visible_dust(self):
        occ = self._occluders
        for x, y, r, a in self._dust_positions():
            if occ and any(o.contains(int(x), int(y)) for o in occ):
                continue
            yield x, y, r, a

    def _dust_tick(self):
        if not self.animating():
            self._sync_timers()
            return
        self.stats["dust_frames"] += 1
        new = [QRect(int(x - r) - 2, int(y - r) - 2, int(2 * r) + 5, int(2 * r) + 5)
               for x, y, r, _a in self._visible_dust()]
        old, self._dust_rects = self._dust_rects, new
        self._update_rects(old + new)

    def _update_rects(self, rects):
        if not rects:
            return
        reg = QRegion()
        for r in rects:
            reg = reg.united(r)
        self.update(reg)

    # ── рисование ── #
    def paintEvent(self, e):
        p = QPainter(self)
        try:
            self._paint(p, e)
        finally:
            p.end()

    def _paint(self, p: QPainter, e):
        src = self._frame if not self._frame.isNull() else self._static
        if src.isNull():
            p.fillRect(self.rect(), QColor(ph.BG_BASE))
            return
        sw = src.width() / src.devicePixelRatio()
        if abs(sw - self.width()) > 1:                         # окно тянут — старый кадр растянуть
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawPixmap(QRectF(self.rect()), src, QRectF(src.rect()))
        else:
            # Qt уже обрезал рисование по обновляемой области (пылинки — крошечные прямоугольники):
            # копируются только они, а не весь кадр
            p.drawPixmap(0, 0, src)
        if self._dust_timer.isActive():
            img = _sprites()["dustimg"]
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            clip = e.rect()
            for x, y, r, a in self._visible_dust():
                rr = QRectF(x - r, y - r, 2 * r, 2 * r)
                if not clip.intersects(rr.toAlignedRect()):
                    continue
                p.setOpacity(a)
                p.drawImage(rr, img)


# ══════════════════════════════════════════════════════════════════════════ #
#  Снимок с размытием — подложка выезжающих панелей
# ══════════════════════════════════════════════════════════════════════════ #

def frozen_blur(widget: QWidget, blur: float = 6.0, dim: float = .55, saturation: float = 1.0,
                layers: list | None = None) -> QPixmap:
    """Снимок widget (обычно — оболочки под панелью), размытый и затемнённый, как скрим Phantom
    (#0000008c + blur(6px) saturate(110%)). Делается ОДИН раз при открытии панели: дальше это просто
    картинка. Считается в половинном размере — размытое всё равно мягкое. Насыщенность (saturate 110 % у Phantom)
    по умолчанию не трогается: под размытием и затемнением её не видно, а numpy на снимок окна — 60–80 мс.
    layers — нарисовать только эти виджеты (по порядку, в координатах widget), а не всё окно: так в снимок
    не попадает сама панель, если она уже на экране."""
    import blur_fx
    if layers:
        dpr = widget.devicePixelRatioF() or 1.0
        shot = QPixmap(int(widget.width() * dpr), int(widget.height() * dpr))
        shot.setDevicePixelRatio(dpr)
        shot.fill(QColor(ph.BG_BASE))
        p = QPainter(shot)
        for w in layers:
            if w is None:
                continue
            off = w.mapTo(widget, w.rect().topLeft()) if w is not widget else w.rect().topLeft()
            w.render(p, off, QRegion(), QWidget.RenderFlag.DrawChildren)
        p.end()
    else:
        shot = widget.grab()
    img = shot.toImage()
    if img.isNull():
        return shot
    dpr = shot.devicePixelRatio()
    w, h = img.width(), img.height()
    q = .5
    small = img.scaled(max(4, int(w * q)), max(4, int(h * q)), Qt.AspectRatioMode.IgnoreAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
    small = blur_fx.blur_image(small, max(.5, blur * dpr * q),
                               post=(lambda im: blur_fx.saturate(im, saturation)) if abs(saturation - 1) > .02
                               else None)
    p = QPainter(small)
    p.fillRect(small.rect(), QColor(0, 0, 0, int(255 * max(0.0, min(1.0, dim)))))
    p.end()
    out = QPixmap.fromImage(small.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation))
    out.setDevicePixelRatio(dpr)
    return out


def default_image_path() -> Path | None:
    return DEFAULT_IMAGE if DEFAULT_IMAGE.exists() else None
