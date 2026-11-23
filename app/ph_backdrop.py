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

Фон из обложки (set_cover, настройка «Фон — обложка трека»): размытая обложка играющего трека вместо
картинки, при смене трека старая картинка плавно растворяется в новой (FADE_MS), а поверх медленно плывут
и перетекают друг в друга большие мягкие пятна цветов обложки (cover_palette). Пятна живут в том же
маленьком слое, что вспышки и дым, только он обновляется чаще (FLOW_MS); при смене трека цвета пятен
плавно переходят в цвета новой обложки (PALETTE_MS).

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
ASSETS_VIDEO = ph.ASSETS / "ph" / "cover-video.mp4"      # встроенная видео-обложка Phantom
ATMO_SCALE = 1 / 6          # слой вспышек и дыма — в 1/6 размера окна
ATMO_MS = 250               # и обновляется 4 раза в секунду
DUST_MS = 33                # пылинки — 30 кадров в секунду (как у Phantom)
REBUILD_DELAY_MS = 120      # пересборка неподвижного слоя после смены размера
FLOW_MS = 125               # слой с пятнами цветов обложки — 8 раз в секунду (пятна плывут медленно)
FADE_MS = 1400              # растворение старой картинки фона в новой
PALETTE_MS = 2600           # переход цветов пятен к цветам новой обложки
FADE_TICK_MS = 33           # кадры на время растворения


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

    def run(self, token: int, src, size: QSize, blur: float, brightness: float, sat: float = .48):
        def work():
            img = QImage()
            try:
                import blur_fx
                # inset -8 %: картинка на 16 % больше окна, чтобы размытые края не темнели
                w, h = max(8, int(size.width() * 1.16)), max(8, int(size.height() * 1.16))
                q = .25                                         # считаем в четверть размера — всё равно размыто
                img = blur_fx.blurred_cover(src, max(4, int(w * q)), max(4, int(h * q)), blur * q, sat=sat)
                if not img.isNull() and brightness < .999:
                    p = QPainter(img)
                    p.fillRect(img.rect(), QColor(0, 0, 0, int(255 * (1 - max(0.0, brightness)))))
                    p.end()
            except Exception:                                  # noqa: BLE001 — без картинки фон просто тёмный
                img = QImage()
            try:
                self.done.emit(token, img)
            except RuntimeError:                              # фон уже закрыт
                pass
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
        self._image_serial = 0                  # номер картинки (у QImage обложки нет пути)
        self._image_sat = .48                   # насыщенность размытой картинки (у обложки — ярче)
        self._fade_from = QPixmap()             # прежний неподвижный слой, пока растворяется
        self._fade_t0 = 0.0
        self._fade_timer = FrameTimer(self)
        self._fade_timer.setInterval(FADE_TICK_MS)
        self._fade_timer.timeout.connect(self._fade_tick)
        self._flow = False                      # пятна цветов обложки
        self._pal_from: list[QColor] = []
        self._pal_to: list[QColor] = []
        self._pal_t0 = 0.0
        self._image = QImage()                   # размытая картинка (¼ размера, с запасом 16 %)
        self._image_for: tuple | None = None
        self._token = 0
        self._image_loading = False
        self._job = _ImageJob(self)
        self._job.done.connect(self._on_image)
        self._static = QPixmap()                 # база + картинка + затемнение + зерно + виньетка
        self._atmo_img = QImage()
        self._t0 = time.perf_counter()
        self._time_offset = random.Random(7).random() * 600   # не с нуля: пятна сразу в «середине» пути
        self._dust_rects: list[QRect] = []
        self._occluders: list[QRect] = []
        self._rebuild = QTimer(self)
        self._rebuild.setSingleShot(True)
        self._rebuild.setInterval(REBUILD_DELAY_MS)
        self._rebuild.timeout.connect(self._resize_settled)
        self._atmo_timer = FrameTimer(self)
        self._atmo_timer.setInterval(ATMO_MS)
        self._atmo_timer.timeout.connect(self._atmo_tick)
        self._dust_timer = FrameTimer(self)
        self._dust_timer.setInterval(DUST_MS)
        self._dust_timer.timeout.connect(self._dust_tick)
        self.stats = {"static_builds": 0, "atmo_frames": 0, "dust_frames": 0}

    # ── настройки ── #
    def configure(self, intensity: float | None = None, brightness: float | None = None,
                  animated: bool | None = None, image=..., saturation: float | None = None):
        """image: путь / QImage / None (без картинки); не передан — оставить как есть. Прежняя картинка
        остаётся на экране, пока новая размывается в фоне, и затем растворяется в ней."""
        changed = False
        if saturation is not None and abs(saturation - self._image_sat) > 1e-3:
            self._image_sat, changed = float(saturation), True
        if intensity is not None and abs(intensity - self._intensity) > 1e-3:
            self._intensity, changed = float(intensity), True
        if brightness is not None and abs(brightness - self._brightness) > 1e-3:
            self._brightness, changed = float(brightness), True
        if image is not ...:
            self._image_src, self._image_for = image, None
            self._image_serial += 1
            if not image:                                      # без картинки — сразу (новой ждать нечего)
                self._begin_fade()
                self._image = QImage()
            changed = True
        if animated is not None:
            self._animated = bool(animated)
        if changed:
            self._image_for = None
            self._token += 1
            self._request_image()
            self._rebuild_static()
        self._sync_timers()

    def set_flow(self, on: bool):
        """Пятна цветов обложки поверх фона (палитра — set_palette)."""
        on = bool(on)
        if on != self._flow:
            self._flow = on
            self._sync_timers()
            self._refresh_atmosphere()

    def set_palette(self, colors: list[QColor] | None):
        """Новые цвета пятен; переход от нынешних — PALETTE_MS (без движения — сразу)."""
        new = [QColor(c) for c in (colors or [])]
        if self.animating() and (self._pal_from or self._pal_to):
            self._pal_from = self._palette_now()
            self._pal_t0 = time.perf_counter()
        else:
            self._pal_from, self._pal_t0 = list(new), 0.0
        self._pal_to = new
        self._sync_timers()
        self._refresh_atmosphere()

    def set_cover(self, img: QImage | None, fallback=None):
        """Фон из обложки: img — обложка (пустая — вернуть fallback: свою картинку или встроенную)."""
        if img is not None and not img.isNull():
            self.configure(image=QImage(img), saturation=.95)
            self.set_palette(cover_palette(img))
        else:
            self.configure(image=fallback, saturation=.48)
            self.set_palette([])

    def _palette_now(self) -> list[QColor]:
        """Цвета пятен сейчас (с учётом перехода между палитрами)."""
        a, b = self._pal_from, self._pal_to
        if not self._pal_t0 or not a:
            return list(b)
        k = min(1.0, (time.perf_counter() - self._pal_t0) * 1000 / PALETTE_MS)
        if k >= 1.0:
            self._pal_from, self._pal_t0 = list(b), 0.0
            return list(b)
        k = k * k * (3 - 2 * k)                                  # плавно в начале и в конце
        dark = QColor(0, 0, 0)                                   # пятна без пары гаснут / проявляются
        return [_mix(a[i % len(a)] if a else dark, b[i % len(b)] if b else dark, k)
                for i in range(max(len(a), len(b)))]

    def _palette_moving(self) -> bool:
        return bool(self._pal_t0) and (time.perf_counter() - self._pal_t0) * 1000 < PALETTE_MS

    def _flow_active(self) -> bool:
        return self._flow and bool(self._pal_to or self._pal_from) and ph.setting("effects")

    # ── растворение старой картинки в новой ── #
    def _begin_fade(self):
        if self._static.isNull() or not self.animating():
            self._fade_from = QPixmap()
            return
        self._fade_from = QPixmap(self._static)
        self._fade_t0 = time.perf_counter()
        if not self._fade_timer.isActive():
            self._fade_timer.start()

    def _fade_k(self) -> float:
        if self._fade_from.isNull():
            return 1.0
        return min(1.0, (time.perf_counter() - self._fade_t0) * 1000 / FADE_MS)

    def _fade_tick(self):
        fading = not self._fade_from.isNull() and self._fade_k() < 1.0 and self.animating()
        if not fading:
            self._fade_from = QPixmap()
        moving = self._palette_moving() and self.animating()
        if moving:
            self._refresh_atmosphere()                        # обновит и окно
        else:
            self.update()
        if not fading and not moving:
            self._fade_timer.stop()

    def set_occluders(self, rects: list[QRect]):
        """Прямоугольники стеклянных панелей (в координатах фона): под ними пылинок нет."""
        self._occluders = [QRect(r) for r in rects]

    def animating(self) -> bool:
        return self._animated and ph.setting("effects") and not ph.motion_reduced() and self.isVisible() and \
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

    def _resize_settled(self):
        if not self.isVisible():
            return
        self._request_image()
        self._rebuild_static()

    def release(self):
        """Отпустить картинки (окно надолго скрыто): при показе всё соберётся заново."""
        self._atmo_timer.stop()
        self._dust_timer.stop()
        self._fade_timer.stop()
        self._fade_from = QPixmap()
        self._rebuild.stop()
        self._static = QPixmap()
        self._image = QImage()
        self._image_for = None
        self._token += 1
        self._atmo_img = QImage()

    def _sync_timers(self):
        on = self.animating()
        want = FLOW_MS if self._flow_active() else ATMO_MS
        if self._atmo_timer.interval() != want:
            self._atmo_timer.setInterval(want)
        if on and self._palette_moving() and not self._fade_timer.isActive():
            self._fade_timer.start()                           # переход цветов — плавными кадрами
        elif not on and self._fade_timer.isActive():
            self._fade_timer.stop()
            self._fade_from = QPixmap()
        for t in (self._atmo_timer, self._dust_timer):
            if on and not t.isActive():
                t.start()
            elif not on and t.isActive():
                t.stop()
        if not on and self._dust_rects:
            rects, self._dust_rects = self._dust_rects, []
            self._update_rects(rects)
        if not ph.setting("effects") and not self._atmo_img.isNull():
            self._atmo_img = QImage()
            self.update()

    # ── картинка ── #
    def _request_image(self):
        if self._image_loading or not self.isVisible() or self.width() < 8 or self.height() < 8:
            return
        p = phantom_params(self._intensity, self._brightness)
        want = (self._image_serial, self.width() // 32, self.height() // 32, p["image_blur"],
                round(p["image_brightness"], 3), round(self._image_sat, 2))
        if not self._image_src or want == self._image_for:
            return
        self._image_for = want
        self._token += 1
        self._image_loading = True
        self._job_serial = self._image_serial
        self._job.run(self._token, self._image_src, self.size(), p["image_blur"], p["image_brightness"],
                      self._image_sat)

    def _on_image(self, token: int, img: QImage):
        self._image_loading = False
        if token == self._token:
            serial = self.__dict__.get("_job_serial", 0)
            if serial != self.__dict__.get("_shown_serial") and self._fade_from.isNull():
                self._begin_fade()                             # другая картинка (не новый размер) — растворить
            self._shown_serial = serial
            self._image = img
            ph.set_tint(image_tint(img))
            if self.isVisible() and not self._rebuild.isActive():
                self._rebuild_static()
        if not self._rebuild.isActive():
            self._request_image()

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
        self._refresh_atmosphere()

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
        flow = self._flow_active()
        if n <= .001 and not flow:
            return
        sp = _sprites()
        t = self._time()
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        mx = max(aw, ah)
        if flow:
            self._paint_flow(p, aw, ah, t, max(.35, n))
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

    def _paint_flow(self, p: QPainter, aw: int, ah: int, t: float, n: float):
        """Большие мягкие пятна цветов обложки: плывут по своим медленным петлям, и цвет каждого
        перетекает в цвет соседа. Периоды — 1,5–3 минуты: при 8 кадрах в секунду пятно сдвигается
        меньше чем на 3 px за кадр, глазом это плавное течение."""
        pal = self._palette_now()
        if not pal:
            return
        mx = max(aw, ah)
        k = len(pal)
        p.setOpacity(1.0)
        for i, b in enumerate(FLOW_BLOBS):
            mixk = .5 + .5 * math.sin(t * b["hue"] + b["phase"] * 2.3)
            c = _mix(pal[i % k], pal[(i + 1) % k], mixk)
            x = (b["x"] + math.sin(t * b["sx"] + b["phase"]) * b["ax"]) * aw
            y = (b["y"] + math.cos(t * b["sy"] + b["phase"] * 1.4) * b["ay"]) * ah
            r = b["r"] * mx * (1 + .08 * math.sin(t * b["sx"] * 1.7 + b["phase"]))
            g = QRadialGradient(x, y, r)
            for at, m in ((0, 1.0), (.35, .62), (.7, .2), (1, 0)):
                cc = QColor(c)
                cc.setAlphaF(max(0.0, min(1.0, b["a"] * n * m)))
                g.setColorAt(at, cc)
            p.fillRect(QRectF(x - r, y - r, 2 * r, 2 * r), g)

    def _refresh_atmosphere(self):
        # Blend the small atmosphere on the widget's backing store, using Qt's
        # dirty region. No second full-screen pixmap is needed.
        if ph.setting("effects") and (self._intensity > .001 or self._flow_active()):
            self._render_atmo()
        else:
            self._atmo_img = QImage()
        self.update()

    def _atmo_tick(self):
        if not self.animating():
            self._sync_timers()
            return
        self.stats["atmo_frames"] += 1
        self._refresh_atmosphere()

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
        src = self._static
        if src.isNull():
            p.fillRect(self.rect(), QColor(ph.BG_BASE))
            return
        size = src.deviceIndependentSize()
        if abs(size.width() - self.width()) > 1 or abs(size.height() - self.height()) > 1:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawPixmap(QRectF(self.rect()), src, QRectF(src.rect()))
        else:
            # Qt уже обрезал рисование по обновляемой области (пылинки — крошечные прямоугольники):
            # копируются только они, а не весь кадр
            p.drawPixmap(0, 0, src)
        old = self._fade_from
        if not old.isNull():
            k = self._fade_k()
            if k < 1.0:                                        # прежняя картинка тает поверх новой
                p.setOpacity(1.0 - k * k * (3 - 2 * k))
                p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                p.drawPixmap(QRectF(self.rect()), old, QRectF(old.rect()))
                p.setOpacity(1.0)
        if not self._atmo_img.isNull():
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            p.drawImage(QRectF(self.rect()), self._atmo_img)
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
    q = .5
    if layers:
        dpr = widget.devicePixelRatioF()
        w, h = int(widget.width() * dpr), int(widget.height() * dpr)
        if not w or not h:
            return QPixmap()
        small = QImage(max(4, int(w * q)), max(4, int(h * q)), _ARGB)
        small.fill(QColor(ph.BG_BASE))
        p = QPainter(small)
        try:
            p.scale(small.width() / widget.width(), small.height() / widget.height())
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            for layer in layers:
                if layer is not None:
                    off = layer.mapTo(widget, layer.rect().topLeft())
                    layer.render(p, off, QRegion(), QWidget.RenderFlag.DrawChildren)
        finally:
            p.end()
    else:
        shot = widget.grab()
        if shot.isNull():
            return shot
        dpr = shot.devicePixelRatio()
        w, h = shot.width(), shot.height()
        small = shot.toImage().scaled(max(4, int(w * q)), max(4, int(h * q)),
                                      Qt.AspectRatioMode.IgnoreAspectRatio,
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


FLOW_BLOBS = [dict(x=.16, y=.20, r=.58, a=.30, ax=.16, ay=.12, sx=.052, sy=.041, hue=.061, phase=.3),
              dict(x=.84, y=.28, r=.52, a=.26, ax=.14, ay=.16, sx=.044, sy=.057, hue=.049, phase=1.9),
              dict(x=.64, y=.88, r=.60, a=.27, ax=.18, ay=.10, sx=.038, sy=.047, hue=.072, phase=3.4),
              dict(x=.22, y=.82, r=.46, a=.22, ax=.12, ay=.14, sx=.058, sy=.036, hue=.055, phase=4.8),
              dict(x=.50, y=.46, r=.40, a=.14, ax=.20, ay=.18, sx=.033, sy=.043, hue=.067, phase=5.6)]


def _mix(a: QColor, b: QColor, k: float) -> QColor:
    k = max(0.0, min(1.0, k))
    return QColor.fromRgbF(a.redF() + (b.redF() - a.redF()) * k, a.greenF() + (b.greenF() - a.greenF()) * k,
                           a.blueF() + (b.blueF() - a.blueF()) * k)


def cover_palette(img: QImage, n: int = 4) -> list[QColor]:
    """До n главных цветов обложки для пятен фона: пиксели раскладываются по 12 оттенкам с весом
    «насыщенность × яркость», берутся самые весомые оттенки; цвета светлеют и чуть насыщаются, чтобы на
    тёмном фоне светиться, а не грязнить. Чёрно-белая обложка — мягкие холодные и тёплые серые."""
    if img is None or img.isNull():
        return []
    small = img.scaled(24, 24, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    bins = [[0.0, 0.0, 0.0, 0.0] for _ in range(12)]          # r, g, b, вес
    for y in range(small.height()):
        for x in range(small.width()):
            c = small.pixelColor(x, y)
            h, sat, v, _a = c.getHsvF()
            if h < 0 or sat < .14 or v < .12:
                continue
            w = sat * v * (.5 + v)
            b = bins[int(h * 12) % 12]
            b[0] += c.redF() * w
            b[1] += c.greenF() * w
            b[2] += c.blueF() * w
            b[3] += w
    total = sum(b[3] for b in bins)
    ranked = sorted((i for i, b in enumerate(bins) if b[3] > max(.4, total * .04)), key=lambda i: -bins[i][3])
    picked = []
    for i in ranked:                                          # сначала разные оттенки, не соседние
        if all(min((i - j) % 12, (j - i) % 12) > 1 for j in picked):
            picked.append(i)
    picked += [i for i in ranked if i not in picked]
    out = []
    for b in (bins[i] for i in picked[:n]):
        c = QColor.fromRgbF(b[0] / b[3], b[1] / b[3], b[2] / b[3])
        h, sat, _v, _a = c.getHsvF()
        out.append(QColor.fromHsvF(max(0.0, h), min(.85, max(.42, sat * 1.15)), .92))
    if not out:                                                # чёрно-белая обложка
        return [QColor(196, 200, 214), QColor(150, 146, 140), QColor(120, 124, 136)]
    while len(out) < min(3, n):                                # один цвет — соседние оттенки того же
        h, sat, v, _a = out[0].getHsvF()
        out.append(QColor.fromHsvF((max(0.0, h) + .06 * len(out)) % 1.0, max(.3, sat * .8), v * .8))
    return out


def image_tint(img: QImage) -> QColor:
    """Главный оттенок картинки фона: средний цвет с весом «насыщенность × яркость», насыщенность поднята,
    яркость — светлая (для смешивания с серым). Серая картинка — почти белый (нейтрально)."""
    if img is None or img.isNull():
        return QColor(255, 255, 255)
    small = img.scaled(16, 16, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    sr = sg = sb = sw = 0.0
    for y in range(16):
        for x in range(16):
            c = small.pixelColor(x, y)
            h, sat, v, _a = c.getHsvF()
            w = max(0.0, sat) * v + .02
            sr += c.redF() * w
            sg += c.greenF() * w
            sb += c.blueF() * w
            sw += w
    avg = QColor.fromRgbF(sr / sw, sg / sw, sb / sw)
    h, sat, _v, _a = avg.getHsvF()
    if h < 0 or sat < .06:
        return QColor(255, 255, 255)
    return QColor.fromHsvF(h, min(.55, sat * 1.6), 1.0)


def default_image_path() -> Path | None:
    return DEFAULT_IMAGE if DEFAULT_IMAGE.exists() else None
