# ya_wave.py
"""
«Моя волна» для темы Echoes Music — как в Яндекс Музыке:

  • слева — список волн по ДУГЕ (без фона): к краям пункты уходят вправо
    и тают; у настроений — «кляксы»-иконки, у жанров — «молнии»,
    у исполнителей — круглые фото с подписью «Артист», «Назад к привычному» —
    жёлтая стрелка;
  • справа — живое сияние в цветах ОБЛОЖКИ ТЕКУЩЕГО ТРЕКА (пока ничего не играет или обложка\n    серая — в цветах настроения), по нему текут мягкие прожилки света, как у Яндекса:
    мягкое ядро, ореол и лучи, считается numpy-полем и растягивается со
    сглаживанием — получается настоящая «засветка», а не векторная клякса;
    дышит в такт басу;
  • поверх сияния — НАЗВАНИЕ НАСТРОЕНИЯ, под ним маленькая обложка,
    «пилюля» с названием трека, кнопки и подсказка; смена трека — обложка\n    проступает из размытия, цвет сияния плавно перетекает в новый.
"""
from __future__ import annotations

import colorsys
import threading
import math
import random
import time
import weakref
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from img_load import load_pixmap, read_image
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, QSize, QRect, pyqtSignal, QVariantAnimation, QEasingCurve
from frameclock import FrameTimer, animation_delta
from PyQt6.QtGui import (QRegion, QColor, QFont, QPainter, QPainterPath, QPainterPathStroker, QPixmap, QImage, QPen,
                         QLinearGradient, QRadialGradient, QFontMetrics)
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame,
                             QGraphicsBlurEffect, QGraphicsOpacityEffect, QStyle, QStyleOptionButton)

try:                                                       # C++-ядро сияния (echoes_fx.dll)
    import native_fx as _NF
    _NATIVE = _NF.available()
except Exception:                                          # noqa: BLE001
    _NF, _NATIVE = None, False

YELLOW = "#ffdb1a"
FAM = ["YS Text", "Inter", "Segoe UI Variable Display", "Segoe UI", "Arial"]
NEBULA_MAX_FPS = 60.0
HERO_MAX_FPS = 30.0                     # баннер «Моя волна» на «Для вас» — маленький, ему хватает 30
# Туманность считается сразу в размер окна (в фоновом потоке, C++): поток интерфейса только копирует
# готовый кадр 1:1. Раньше кадр в 75 % размера растягивался в каждом кадре на потоке интерфейса.
NEBULA_RENDER_SCALE = 1.0
GPU_PAGE_SCALE = 1.68                   # GPU-туманность на странице «Моя волна»: компактнее (баннер — 1.0)
GPU_PAGE_SPEED = 2.8                    # и живее: время туманности на странице идёт в 2.8 раза быстрее


def _tr(s):
    """Перевод для текста, который меряется до рисования (иначе ширина — по русскому варианту)."""
    try:
        import i18n
        return i18n.tr(s)
    except Exception:                                      # noqa: BLE001
        return s


def _font(px, w=QFont.Weight.Normal):
    f = QFont()
    f.setFamilies(FAM)
    f.setPixelSize(int(px))
    f.setWeight(w)
    return f


# ── палитры настроений: (ядро, ореол, лучи) ─────────────────────────────── #

def _hx(c):
    c = QColor(c)
    return np.array([c.redF(), c.greenF(), c.blueF()], dtype=np.float32)


MOOD_COLORS = {
    "my":       ("#fff04a", "#e5127d", "#ff4fb8"),
    "mood_day": ("#ffc56b", "#7a2cff", "#ff7a3d"),
    "energy":   ("#ffd23a", "#ff1d2d", "#ff6a00"),
    "calm":     ("#9ffcff", "#1f5bff", "#40c8ff"),
    "happy":    ("#f6ff57", "#18c95a", "#ffe23a"),
    "sad":      ("#b9c2ff", "#3a1aa8", "#6f5cff"),
    "fresh":    ("#a6fff4", "#a020ff", "#3fd8ff"),
    "fav":      ("#ffe0ef", "#ff1f6d", "#ffb02e"),
}


_LIVE = __import__("weakref").WeakSet()                       # волны на экране — перекрасить под новый фон


def retint():
    """Оттенок фона сменился (ph_style.set_tint) — перекрасить туманности в виде Phantom."""
    if not _phantom():
        return
    for w in list(_LIVE):
        try:
            if hasattr(w, "set_scheme"):
                w.set_scheme(scheme_for("my"))
            w.update()
        except RuntimeError:
            pass


def _ph_backdrop(widget, p) -> bool:
    """Вид Phantom: нарисовать под виджетом фон за панелью (ph_shell.paint_backdrop); иначе False."""
    if not _phantom():
        return False
    try:
        import ph_shell
        return ph_shell.paint_backdrop(widget, p)
    except Exception:                                          # noqa: BLE001
        return False


def _screen_backdrop(widget, W, H, dpr):
    """Phantom + туманность на GPU: фон за панелью как накладка, которая смешивается с туманностью почти как
    «экран» (премультипл. пиксель rgb=фон, альфа=max(rgb): итог = фон + туманность·(1−альфа)). Свет туманности
    ложится на размытую картинку, а не на чёрное. None — не Phantom / панель не открыта."""
    if not _phantom():
        return None
    w, h = max(1, int(W * dpr)), max(1, int(H * dpr))
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.setDevicePixelRatio(dpr)
    img.fill(QColor(0, 0, 0))
    q = QPainter(img)
    try:
        ok = _ph_backdrop(widget, q)
    finally:
        q.end()
    if not ok:
        return None
    a = np.frombuffer(img.constBits().asstring(img.sizeInBytes()), np.uint8).reshape(h, img.bytesPerLine() // 4, 4)
    a = a[:, :w].copy()
    a[..., 3] = a[..., :3].max(axis=2)
    out = QImage(a.data, w, h, w * 4, QImage.Format.Format_ARGB32_Premultiplied).copy()
    out.setDevicePixelRatio(dpr)
    return out


def _backdrop_key(widget):
    if not _phantom():
        return None
    try:
        import ph_shell
        return ph_shell.backdrop_key(widget)
    except Exception:                                          # noqa: BLE001
        return None


def _phantom() -> bool:
    try:
        import ya_skin
        return bool(ya_skin.PHANTOM_ON)
    except Exception:                                          # noqa: BLE001
        return False


# вид Phantom — монохром с оттенком картинки фона (ph_style.tone); цветные схемы остаются для прежнего вида


def _mono_palette():
    import ph_style
    return tuple(ph_style.tone(v, k=.38).name() for v in (255, 154, 214))


def _mono_scheme():
    import ph_style
    return ph_style.mono_scheme()


def palette_for(kind, arg=None):
    if _phantom():
        return _mono_palette()
    if kind in MOOD_COLORS:
        return MOOD_COLORS[kind]
    if kind == "mood" and arg in MOOD_COLORS:
        return MOOD_COLORS[arg]
    key = str(arg or kind)
    h = (sum(ord(c) * (i + 7) for i, c in enumerate(key)) % 360) / 360.0
    core = QColor.fromHsvF((h + 0.10) % 1, 0.55, 1.0).name()
    halo = QColor.fromHsvF(h, 0.95, 0.95).name()
    ray = QColor.fromHsvF((h + 0.05) % 1, 0.8, 1.0).name()
    return core, halo, ray


def cover_palette(pm) -> tuple | None:
    """(ядро, ореол, лучи) из главного цвета обложки (QPixmap/QImage): картинка 24×24 → гистограмма
    оттенков с весом «насыщенность × яркость». None — пустая или почти чёрно-белая обложка."""
    try:
        img = (pm.toImage() if isinstance(pm, QPixmap) else QImage(pm))
        if img.isNull():
            return None
        img = img.scaled(24, 24, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_RGB888)
        a = np.frombuffer(img.constBits().asstring(img.sizeInBytes()), dtype=np.uint8)
        a = a.reshape(24, img.bytesPerLine())[:, :72].reshape(-1, 3).astype(np.float32) / 255.0
        mx, mn = a.max(1), a.min(1)
        sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
        w = sat * mx
        r, g, b = a[:, 0], a[:, 1], a[:, 2]
        d = np.maximum(mx - mn, 1e-6)
        hue = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) / 6.0
        keep = w > 0.12
        if not keep.any():
            return None
        bins = (hue[keep] * 24).astype(int) % 24
        hist = np.bincount(bins, weights=w[keep], minlength=24)
        best = int(hist.argmax())
        if hist[best] < 1.5:
            return None
        sel = keep.copy()
        sel[keep] = bins == best
        col = (a[sel] * w[sel, None]).sum(0) / w[sel].sum()
        h, s, v = colorsys.rgb_to_hsv(*col)
        s = max(0.75, s)
        core = QColor.fromHsvF(h, 0.32, 1.0).name()
        halo = QColor.fromHsvF(h, s, 0.92).name()
        ray = QColor.fromHsvF((h + 0.03) % 1, 0.55, 1.0).name()
        return core, halo, ray
    except Exception as e:                                # noqa: BLE001
        print("[wave] cover palette:", e)
        return None


# ══════════════════════════════════════════════════════════════════════════ #
#  Сияние: поле из гауссовых пятен + ореол с лучами
# ══════════════════════════════════════════════════════════════════════════ #

class GlowField:
    GW = 176
    MARGIN = 0.04                 # запас по краям под «плавание» центра (сдвиг картинки при рисовании)

    def __init__(self):
        self.size = (0, 0)
        self.rng = np.random.default_rng(7)
        # параметры «пятен» ядра: смещение по орбите, частоты, радиус
        self.blobs = [(0.16 * self.rng.uniform(0.5, 1.0), self.rng.uniform(0.15, 0.45),
                       self.rng.uniform(0.15, 0.45), self.rng.uniform(0, 6.28),
                       self.rng.uniform(0.26, 0.40)) for _ in range(6)]
        self.core = _hx("#fff04a")
        self.halo = _hx("#e5127d")
        self.ray = _hx("#ff4fb8")
        self._to = None
        self._mix = 1.0
        self.tt = 0.0              # «музыкальное» время: бежит быстрее, когда музыка громче
        self.kick = 0.0            # импульс удара баса (0..1, затухает)
        self.rings: list = []      # ударные волны: [радиус, сила]
        self.energy = 0.0

    def hit(self, strength=1.0):
        """Удар баса: вспышка ядра и расходящееся кольцо света."""
        self.kick = min(1.0, self.kick + 0.7 * strength)
        self.rings.append([0.25, 0.55 * strength])
        if len(self.rings) > 5:
            self.rings.pop(0)

    def set_palette(self, core, halo, ray, instant=False):
        to = (_hx(core), _hx(halo), _hx(ray))
        if instant:
            self.core, self.halo, self.ray = to
            self._to = None
            return
        self._from = (self.core.copy(), self.halo.copy(), self.ray.copy())
        self._to = to
        self._mix = 0.0

    def _grid(self, W, H, cx=0.5, cy=0.5):
        """Сетка и всё, что зависит только от геометрии (радиус, угол, гармоники угла) — один раз на
        размер окна: раньше sqrt/arctan2 и десяток sin по всем точкам считались каждый кадр."""
        gw = self.GW
        gh = max(40, int(gw * H / max(1, W)))
        aspect = W / max(1, H)
        key = (gw, gh, round(aspect, 4), round(cx, 4), round(cy, 4))
        if getattr(self, "_gkey", None) != key:
            self._gkey = key
            self.size = (gw, gh)
            ys, xs = np.mgrid[0:gh, 0:gw].astype(np.float32)
            m = self.MARGIN                               # картинка шире окна на m с каждой стороны
            self.X = ((-m + (1 + 2 * m) * xs / (gw - 1)) * 2 - 1) * aspect
            self.Y = (-m + (1 + 2 * m) * ys / (gh - 1)) * 2 - 1
            X = self.X - np.float32((cx * 2 - 1) * aspect)
            Y = self.Y - np.float32(cy * 2 - 1)
            R2 = X * X + Y * Y
            R0 = np.sqrt(R2)
            ang = np.arctan2(Y, X)
            g = {"X": X, "Y": Y, "R2": R2, "R0": R0, "clipR": np.clip(R0 / 0.35, 0, 1).astype(np.float32),
                 "sinR": np.sin(R0 * 2.2).astype(np.float32), "cosR": np.cos(R0 * 2.2).astype(np.float32),
                 "xs": X[0, :].copy(), "ys": Y[:, 0].copy(), "a4": (4 * ang).astype(np.float32)}
            for k in (2, 3, 4, 5, 6, 7, 9):
                g[f"s{k}"] = np.sin(k * ang).astype(np.float32)
                g[f"c{k}"] = np.cos(k * ang).astype(np.float32)
            self.g = g
        return self.size

    @staticmethod
    def _field(px, py, t):
        qx = px + np.float32(0.55) * np.sin(py * np.float32(1.7) + np.float32(t * 0.6)) + \
            np.float32(0.30) * np.sin(py * np.float32(3.1) - np.float32(t * 0.4))
        qy = py + np.float32(0.55) * np.sin(px * np.float32(1.9) - np.float32(t * 0.5)) + \
            np.float32(0.30) * np.sin(px * np.float32(2.7) + np.float32(t * 0.35))
        return np.sin(qx * np.float32(1.6) + np.sin(qy * np.float32(1.3) + np.float32(t * 0.3))) + \
            np.sin(qy * np.float32(1.4) - np.sin(qx * np.float32(1.1) - np.float32(t * 0.25)))

    def _veins(self, px, py, t):
        """Яркость прожилок 0..~1.6: тонкая середина + широкое мягкое свечение, две сетки (как в шейдере телефона)."""
        f = np.sin(self._field(px, py, t) * np.float32(2.4))
        g = np.sin(self._field(px * np.float32(1.25) + np.float32(5.0), py * np.float32(1.25) - np.float32(3.0),
                               t * 1.2 + 7.0) * np.float32(2.0))
        w = np.float32(0.16)
        f2, g2 = (f / w) ** 2, (g / w) ** 2
        return np.exp(-f2) * np.float32(0.6) + np.exp(-g2) * np.float32(0.42) + \
            np.exp(-f2 / 16) * np.float32(0.35) + np.exp(-g2 / 16) * np.float32(0.25)

    def _advance(self, beat, dt):
        """Время, палитра, удары и «плавание» центра — общее для numpy- и C++-рендера."""
        if self._to is not None:
            self._mix = min(1.0, self._mix + dt / 1.4)
            k = self._mix * self._mix * (3 - 2 * self._mix)
            self.core = self._from[0] * (1 - k) + self._to[0] * k
            self.halo = self._from[1] * (1 - k) + self._to[1] * k
            self.ray = self._from[2] * (1 - k) + self._to[2] * k
            if self._mix >= 1.0:
                self._to = None
        self.energy += (beat - self.energy) * min(1.0, dt * 3)
        self.tt += dt * (1.0 + 2.2 * self.energy + 1.5 * self.kick)
        T = self.tt
        self.kick *= math.exp(-dt * 3.2)
        for r in self.rings:
            r[0] += dt * (1.6 + 0.8 * self.energy)
            r[1] *= math.exp(-dt * 1.4)
        self.rings = [r for r in self.rings if r[1] > 0.02 and r[0] < 3.5]
        self.offset = (0.018 * math.sin(T * 0.7) + 0.008 * math.sin(T * 1.9),
                       0.022 * math.cos(T * 0.55) + 0.008 * math.sin(T * 2.3))
        return T

    X0 = 0.34                     # левее — список волн на чёрном (сияние там не нужно)

    def render_native(self, W, H, cx, cy, beat, dt, dpr=1.0) -> QImage:
        """C++: кадр сразу размером с окно (пиксели устройства), «плавание» уже учтено —
        рисовать в (0, 0) без масштаба."""
        T = self._advance(beat, dt)
        Wd, Hd = max(8, int(W * dpr)), max(8, int(H * dpr))
        P = _NF.GlowParams()
        P.W, P.H = Wd, Hd
        P.x0 = int(Wd * self.X0)
        cols = Wd - P.x0
        P.gw = int(max(96, min(380, cols / 4.0)))      # ~4 пикселя окна на точку: вдвое чётче numpy-версии
        P.gh = int(max(64, P.gw * Hd / max(1, cols)))
        aspect = W / max(1, H)
        P.aspect = aspect
        P.cxo, P.cyo = (cx * 2 - 1) * aspect, cy * 2 - 1
        P.ox, P.oy = self.offset
        P.T, P.energy, P.kick, P.beat = T, self.energy, self.kick, beat
        for k in range(3):
            P.core[k], P.halo[k], P.ray[k] = float(self.core[k]), float(self.halo[k]), float(self.ray[k])
        pulse = 1.0 + 0.10 * beat + 0.20 * self.kick + 0.03 * math.sin(T * 2.1)
        P.nblobs = len(self.blobs)
        for i, (orb, fx, fy, ph, rad) in enumerate(self.blobs):
            P.blobs[i * 3] = orb * 1.9 * math.sin(T * fx * 2.4 + ph)
            P.blobs[i * 3 + 1] = orb * 1.5 * math.cos(T * fy * 2.4 + ph * 1.3)
            P.blobs[i * 3 + 2] = 1.0 / (rad * 1.7 * pulse) ** 2
        rings = self.rings[-8:]
        P.nrings = len(rings)
        for i, (rr, a) in enumerate(rings):
            P.rings[i * 2], P.rings[i * 2 + 1] = rr, a
        img = QImage(Wd, Hd, QImage.Format.Format_RGB32)
        _NF.glow_render(P, img)
        img.setDevicePixelRatio(dpr)
        return img

    def render(self, W, H, cx, cy, t, beat, dt) -> QImage:
        """cx, cy — центр сияния в долях окна. «Плавание» центра не пересчитывает сетку: оно отдаётся
        сдвигом картинки (self.offset, доли окна) — сияние мягкое, разницы не видно."""
        gw, gh = self._grid(W, H, cx, cy)
        g = self.g
        T = self._advance(beat, dt)
        X, Y, R0, R2 = g["X"], g["Y"], g["R0"], g["R2"]
        f32 = np.float32

        def sn(k, ph):                                    # sin(k·угол + ph) из готовых гармоник
            return g[f"s{k}"] * f32(math.cos(ph)) + g[f"c{k}"] * f32(math.sin(ph))
        pulse = 1.0 + 0.10 * beat + 0.20 * self.kick + 0.03 * math.sin(T * 2.1)
        lobes = (0.17 + 0.07 * self.energy) * sn(5, T * 0.65)
        lobes += f32(0.12) * sn(3, -T * 0.95 + 1.0)
        lobes += f32(0.07) * sn(7, T * 1.5)
        lobes += f32(0.05) * sn(2, -T * 0.4)
        lobes *= g["clipR"]
        lobes += f32(1.0)
        inv = f32(1.0) / lobes
        Xw, Yw = X * inv, Y * inv
        f = np.zeros_like(X)
        for (orb, fx, fy, ph, rad) in self.blobs:
            bx = orb * 1.9 * math.sin(T * fx * 2.4 + ph)
            by = orb * 1.5 * math.cos(T * fy * 2.4 + ph * 1.3)
            r2 = (rad * 1.7 * pulse) ** 2
            dx = Xw - f32(bx)
            dy = Yw - f32(by)
            e = dx * dx
            e += f32(1.1) * dy * dy
            e *= f32(-1.0 / r2)
            f += np.exp(e)
        f *= f32(1.0 / (len(self.blobs) * 0.42))
        inner_r = 1.4 * (g["sinR"] * f32(math.cos(T * 1.3)) - g["cosR"] * f32(math.sin(T * 1.3)))
        rays = f32(0.6) + f32(0.4) * np.sin(g["a4"] + f32(T * 0.45) + inner_r)
        rays *= rays
        rays *= f32(0.85) + f32(0.15) * sn(9, -T * 2.0)
        rh = 1.15 + 0.10 * beat + 0.25 * self.kick
        halo = np.exp(R2 * f32(-1.2 / (rh * rh)))
        halo *= f32(0.75) + f32(0.35) * rays
        rl = 1.6 + 0.3 * self.kick
        s6 = f32(0.5) + f32(0.5) * sn(6, -T * 0.5)
        s6 *= s6
        s6 *= s6
        ray_l = np.exp(R2 * f32(-1.0 / (rl * rl))) * s6 * f32(0.35 + 0.35 * self.energy)
        core = np.clip((f - f32(0.36)) * f32(1 / 0.85), 0, 1)
        core = core * core * (f32(3) - f32(2) * core)
        inner = np.clip((f - f32(0.95)), 0, 1) * f32(0.35 + 0.5 * self.kick)
        # ядро переливается к цвету лучей (переливы разделимы по x и y — внешнее произведение)
        shimmer = f32(0.5) + f32(0.5) * np.outer(np.cos(g["ys"] * f32(1.8) - f32(T * 0.7)),
                                                 np.sin(g["xs"] * f32(2.2) + f32(T * 0.9))).astype(np.float32)
        core_col = self.core.astype(np.float32)[None, None, :] * (f32(1) - f32(0.25) * shimmer[..., None]) + \
            self.ray.astype(np.float32)[None, None, :] * (f32(0.25) * shimmer[..., None])
        img = halo[..., None] * (self.halo * (1.2 + 0.4 * self.kick)).astype(np.float32) + \
            ray_l[..., None] * self.ray.astype(np.float32)
        for rr, a in self.rings:
            d = (R0 - f32(rr)) * f32(1 / 0.16)
            ring = np.exp(-(d * d)) * f32(a * 0.7)
            img += ring[..., None] * (self.ray * 0.7 + self.halo * 0.5).astype(np.float32)
        img = img * (f32(1) - core[..., None] * f32(0.92)) + core[..., None] * core_col
        # прожилки света (как у волны Яндекса): нулевые линии плавного «закрученного» поля на нескольких
        # уровнях — мягкий свет цвета ядра, вплетён в облако; под музыку ярче и текут быстрее
        vt = T * 0.45
        img += self._veins(X * f32(0.85), Y * f32(0.85), vt)[..., None] * \
            ((self.core * 0.55 + 0.45) * (0.20 + 0.10 * self.energy)).astype(np.float32) * \
            (f32(0.25) + f32(0.75) * np.clip(halo * f32(1.4), 0, 1) - f32(0.55) * core)[..., None]
        img += inner[..., None] * ((1.0 - self.core) * 0.6).astype(np.float32)
        np.clip(img, 0, 1, out=img)
        img *= f32(0.95) + f32(0.05) * img                 # ≈ x^1.05 без степени
        u8 = np.ascontiguousarray((img * 255).astype(np.uint8))
        self._buf = u8                                    # держим память под QImage
        return QImage(u8.data, gw, gh, gw * 3, QImage.Format.Format_RGB888)


# ══════════════════════════════════════════════════════════════════════════ #
#  Туманность в стиле Яндекс Музыки (C++: nebula.cpp)
# ══════════════════════════════════════════════════════════════════════════ #

# четыре цвета: ядро, середина, край 1, край 2 — как на экранах «Моей волны» в Яндекс Музыке
SCHEMES = {                             # ядро → середина → край → небольшие пятна: соседние оттенки (как у Яндекса)
    "my":       ("#ffd21a", "#ff8a1a", "#ff2a6a", "#b01aff"),
    "mood_day": ("#ffb04a", "#ff4a8a", "#7a2cff", "#ffd84a"),
    "energy":   ("#d21aff", "#ff2a9e", "#ff3a2a", "#ff8a1a"),
    "calm":     ("#7fe8ff", "#2a9bff", "#4a2cff", "#20e0c0"),
    "happy":    ("#fff23a", "#9dff3a", "#ffb31a", "#3aff9d"),
    "sad":      ("#2ee6b0", "#16c8c0", "#1a3cff", "#9a1fd6"),
    "fresh":    ("#3cff3c", "#1fd86a", "#1a6cff", "#0fd6c0"),
    "fav":      ("#ff4a8a", "#ff8a3a", "#b01aff", "#ffc0dc"),
}


def scheme_from_hue(h: float, s: float = 0.9) -> tuple:
    def c(dh, ss, vv):
        return QColor.fromHsvF((h + dh) % 1.0, max(0.0, min(1.0, ss)), vv).name()
    # соседние оттенки (±30°): цвета обложки/жанра не превращаются в «радугу»
    return c(0.0, 0.72 * s + 0.1, 1.0), c(0.04, 0.92 * s, 0.95), c(0.09, 0.90 * s, 0.90), c(-0.07, 0.88 * s, 0.92)


def scheme_for(kind, arg=None) -> tuple:
    if _phantom():
        return _mono_scheme()
    if kind in SCHEMES:
        return SCHEMES[kind]
    if kind == "mood" and arg in SCHEMES:
        return SCHEMES[arg]
    key = str(arg or kind)
    return scheme_from_hue((sum(ord(c) * (i + 7) for i, c in enumerate(key)) % 360) / 360.0)


def cover_scheme(pm) -> tuple | None:
    """Схема туманности из главного цвета обложки (None — серая обложка)."""
    if _phantom():
        return _mono_scheme()
    pal = cover_palette(pm)
    if pal is None:
        return None
    h, s, _v, _a = QColor(pal[1]).getHsvF()
    return scheme_from_hue(max(0.0, h), max(0.75, s))


class NebulaField:
    """Пятна туманности: позиция (доли радиуса), радиус, цвет (индекс схемы или смесь), сила,
    орбита и частоты дрейфа. Всё медленно вращается, дышит от баса, вспыхивает на ударе."""
    # x, y, r, цвет (0..3; 0.5 — смесь 0 и 1), сила, орбита, fx, fy, фаза
    LAYOUT = [(0.00, -0.02, 0.64, 0, 1.10, 0.08, 0.31, 0.27, 0.0),
              (0.18, 0.08, 0.42, 0.5, 0.80, 0.22, 0.23, 0.35, 1.3),
              (-0.50, 0.10, 0.52, 1, 0.70, 0.16, 0.19, 0.24, 2.1),
              (0.52, -0.12, 0.48, 1, 0.62, 0.18, 0.27, 0.21, 3.7),
              (-0.70, -0.46, 0.55, 2, 0.80, 0.14, 0.17, 0.29, 0.6),
              (0.84, 0.22, 0.50, 2, 0.65, 0.15, 0.21, 0.18, 4.4),
              (0.08, 0.86, 0.62, 3, 0.85, 0.13, 0.25, 0.20, 5.1),
              (-0.80, 0.62, 0.45, 3, 0.65, 0.17, 0.29, 0.23, 2.8),
              (0.70, -0.78, 0.45, 3, 0.55, 0.15, 0.22, 0.31, 1.9),
              (0.20, 0.06, 0.24, 0, 0.55, 0.20, 0.41, 0.37, 3.3)]

    def __init__(self):
        self.cols = np.array([_hx(c) for c in scheme_for("my")], np.float32)
        self._from = self._to = None
        self._mix = 1.0
        self.tt = 0.0
        self.kick = 0.0
        self.energy = 0.0
        self.rings: list = []
        self.frame = 0
        self._buf = None

    def hit(self, strength=1.0):
        self.kick = min(1.0, self.kick + 0.7 * strength)
        self.rings.append([0.15, 0.30 * strength])
        if len(self.rings) > 6:
            self.rings.pop(0)

    def set_scheme(self, cols, instant=False):
        to = np.array([_hx(c) for c in cols], np.float32)
        if instant:
            self.cols, self._to = to, None
            return
        self._from, self._to, self._mix = self.cols.copy(), to, 0.0

    def _advance(self, beat, dt):
        if self._to is not None:
            self._mix = min(1.0, self._mix + dt / 1.6)
            k = self._mix * self._mix * (3 - 2 * self._mix)
            self.cols = self._from * (1 - k) + self._to * k
            if self._mix >= 1.0:
                self._to = None
        self.energy += (beat - self.energy) * min(1.0, dt * 3)
        self.tt += dt * (1.0 + 1.6 * self.energy + 1.2 * self.kick)
        self.kick *= math.exp(-dt * 2.8)
        for r in self.rings:
            r[0] += dt * (0.9 + 0.5 * self.energy)
            r[1] *= math.exp(-dt * 1.3)
        self.rings = [r for r in self.rings if r[1] > 0.01 and r[0] < 2.6]
        self.frame += 1
        return self.tt

    def _blobs(self, T):
        rot = T * 0.035
        cr, sr = math.cos(rot), math.sin(rot)
        breath = 1.0 + 0.10 * self.energy + 0.16 * self.kick + 0.03 * math.sin(T * 0.9)
        out = []
        for (x, y, r, ci, inten, orb, fx, fy, ph) in self.LAYOUT:
            bx = (x + orb * math.sin(T * fx + ph)) * 0.74          # пятна собраны внутри одного облака
            by = (y + orb * math.cos(T * fy + ph * 1.3)) * 0.74
            bx, by = bx * cr - by * sr, bx * sr + by * cr
            col = (self.cols[0] + self.cols[1]) * 0.5 if ci == 0.5 else self.cols[int(ci)]
            rr = r * breath * 0.92
            out.append((bx, by, 1.0 / (rr * rr), col, inten * (1.0 + 0.25 * self.kick)))
        return out

    def params(self, W, H, cx, cy, R, beat, dt, x0=0, dpr=1.0):
        """Следующий кадр: продвинуть время и вернуть NebParams (для C++ на CPU и шейдера на GPU)."""
        T = self._advance(beat, dt)
        Wd, Hd = max(8, int(W * dpr)), max(8, int(H * dpr))
        return self._native_params(T, Wd, Hd, cx, cy, R, x0, dpr)

    def _native_params(self, T, Wd, Hd, cx, cy, R, x0, dpr):
        blobs = self._blobs(T)
        fil = np.clip(self.cols[0] * 0.5 + 0.55, 0, 1)
        ring_col = np.clip(self.cols[0] * 0.6 + 0.25, 0, 1)
        P = _NF.NebParams()
        P.W, P.H, P.x0 = Wd, Hd, int(x0 * dpr)
        cols = Wd - P.x0
        P.gw = int(max(96, min(560, cols / 3.0)))
        P.gh = int(max(64, P.gw * Hd / max(1, cols)))
        P.cx, P.cy, P.R = cx * dpr, cy * dpr, R * dpr
        P.T, P.flow, P.energy, P.kick = T, 0.55, self.energy, self.kick
        P.gain, P.fil_amt, P.ray_amt, P.grain = 1.15, 0.20 + 0.22 * self.energy, 0.18 + 0.25 * self.kick, 1.2 / 255
        for k in range(3):
            P.fil_col[k] = float(fil[k])
            P.ring_col[k] = float(ring_col[k])
        P.nblobs = len(blobs)
        for i, (bx, by, ib, col, inten) in enumerate(blobs):
            P.blobs[i * 7:i * 7 + 7] = [bx, by, ib, float(col[0]), float(col[1]), float(col[2]), inten]
        P.nrings = len(self.rings)
        for i, (rr, a) in enumerate(self.rings):
            P.rings[i * 2], P.rings[i * 2 + 1] = rr, a
        P.seed = self.frame
        P.env_r = 0.90 + 0.06 * self.energy + 0.07 * self.kick
        P.lobe = 0.08
        return P

    def render(self, W, H, cx, cy, R, beat, dt, x0=0, dpr=1.0) -> QImage:
        """Кадр размером с окно (пиксели устройства); cx, cy, R — в пикселях окна."""
        T = self._advance(beat, dt)
        Wd, Hd = max(8, int(W * dpr)), max(8, int(H * dpr))
        if _NATIVE and hasattr(_NF, "nebula_render"):
            P = self._native_params(T, Wd, Hd, cx, cy, R, x0, dpr)
            img = QImage(Wd, Hd, QImage.Format.Format_RGB32)
            _NF.nebula_render(P, img)
            img.setDevicePixelRatio(dpr)
            return img
        blobs = self._blobs(T)
        fil = np.clip(self.cols[0] * 0.5 + 0.55, 0, 1)
        ring_col = np.clip(self.cols[0] * 0.6 + 0.25, 0, 1)
        return self._render_numpy(W, H, cx, cy, R, T, blobs, fil, ring_col, x0)

    def _render_numpy(self, W, H, cx, cy, R, T, blobs, fil, ring_col, x0):
        """Без C++: то же поле в numpy на мелкой сетке, растягивает Qt."""
        gw = 220
        gh = max(40, int(gw * H / max(1, W)))
        f32 = np.float32
        ys, xs = np.mgrid[0:gh, 0:gw].astype(np.float32)
        u = (xs + 0.5) * f32(W / gw)
        v = (ys + 0.5) * f32(H / gh)
        u = (u - f32(cx)) / f32(R)
        v = (v - f32(cy)) / f32(R)
        t = T * 0.55
        w1x = u + f32(0.30) * np.sin(v * 1.9 + t * 0.7) + f32(0.15) * np.sin(v * 3.7 - t * 0.5 + u * 1.3)
        w1y = v + f32(0.30) * np.sin(u * 1.7 - t * 0.6) + f32(0.15) * np.sin(u * 3.3 + t * 0.45 - v * 1.1)
        w2x = w1x + f32(0.10) * np.sin(w1y * 5.1 + t * 0.9)
        w2y = w1y + f32(0.10) * np.sin(w1x * 4.7 - t * 0.8)
        acc = np.zeros((gh, gw, 3), np.float32)
        for bx, by, ib, col, inten in blobs:
            e = np.exp(-(((u + (w2x - u) * 0.55) - f32(bx)) ** 2 + ((v + (w2y - v) * 0.55) - f32(by)) ** 2) * f32(ib)) * f32(inten)
            acc += e[..., None] * col.astype(np.float32)
        lum = acc.max(2)
        f = np.sin((np.sin(w1x * 2.3 + np.sin(w1y * 1.7 + t * 0.3)) + np.sin(w1y * 2.1 - np.sin(w1x * 1.9 - t * 0.25))) * 2.6)
        fl = (np.exp(-(f / 0.075) ** 2) * 0.85 + np.exp(-(f / 0.3) ** 2) * 0.18) * np.clip(lum * 1.6, 0, 1) * \
            f32(0.32 + 0.25 * self.energy)
        acc += fl[..., None] * (fil.astype(np.float32) * 0.4 + 0.6 * np.clip(acc / np.maximum(lum, 0.05)[..., None], 0, 1))
        r = np.sqrt(u * u + v * v)
        for rr, a in self.rings:
            acc += (np.exp(-((r - rr) / 0.14) ** 2) * a)[..., None] * ring_col.astype(np.float32)
        ang = np.arctan2(v, u)
        rs = (0.90 + 0.06 * self.energy) * (1 + 0.11 * (0.55 * np.sin(3 * ang + t * 0.3) + 0.35 * np.sin(5 * ang - t * 0.42)
                                                        + 0.25 * np.sin(2 * ang + t * 0.21 + 1.7)))
        e2 = (r / rs) ** 2
        img = (1 - np.exp(-acc * 1.25)) * np.exp(-e2 * e2 * 1.1)[..., None]
        img[:, :int(gw * x0 / max(1, W))] = 0
        u8 = np.ascontiguousarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
        self._buf = u8
        q = QImage(u8.data, gw, gh, gw * 3, QImage.Format.Format_RGB888)
        return q.scaled(W, H, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)


# ══════════════════════════════════════════════════════════════════════════ #
#  Иконки пунктов
# ══════════════════════════════════════════════════════════════════════════ #

_ICONS = OrderedDict()


_GENRE_SHAPE = {"metal": "horns", "metalcore": "horns", "punk": "horns", "rock": "horns",
                "phonk": "mic", "trap": "mic", "drill": "mic", "hiphop": "mic", "cloudrap": "mic",
                "dnb": "eq", "dubstep": "eq", "electronic": "eq", "dance": "eq", "hyperpop": "eq",
                "synthwave": "retro", "dreampop": "cloud", "ambient": "cloud", "lofi": "moon", "emo": "broken",
                "jazz": "note", "funk": "note", "rnb": "note", "classical": "note", "soundtrack": "star",
                "folk": "pick", "latin": "pick", "indie": "pick", "pop": "star", "jpop": "star"}
_MOOD_SHAPE = {"energy": "burst", "happy": "flower", "calm": "wave", "sad": "drop", "mood_day": "planet",
               "fresh": "sparkle", "fav": "heart"}


def _star_path(cx, cy, r, n, inner, rot=-90.0):
    path = QPainterPath()
    for i in range(n * 2):
        a = math.radians(rot + i * 180.0 / n)
        rr = r if i % 2 == 0 else r * inner
        pt = QPointF(cx + math.cos(a) * rr, cy + math.sin(a) * rr)
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    path.closeSubpath()
    return path


def _heart_path(cx, cy, s):
    path = QPainterPath(QPointF(cx, cy + s * 0.36))
    path.cubicTo(QPointF(cx - s * 0.58, cy), QPointF(cx - s * 0.36, cy - s * 0.48), QPointF(cx, cy - s * 0.2))
    path.cubicTo(QPointF(cx + s * 0.36, cy - s * 0.48), QPointF(cx + s * 0.58, cy), QPointF(cx, cy + s * 0.36))
    return path


def _shape(kind: str, s: float):
    """Фигуры значков «Моей волны»: «mood:calm», «genre:phonk» … (None — старая клякса/молния)."""
    group, _, key = kind.partition(":")
    name = (_MOOD_SHAPE if group == "mood" else _GENRE_SHAPE).get(key)
    cx = cy = s / 2
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)
    if name == "burst":                                  # бодрое — колючая вспышка
        return _star_path(cx, cy, s * 0.47, 10, 0.58)
    if name == "flower":                                 # весёлое — цветок-солнышко
        for i in range(6):
            a = math.radians(i * 60 - 90)
            path.addEllipse(QPointF(cx + math.cos(a) * s * 0.24, cy + math.sin(a) * s * 0.24), s * 0.17, s * 0.17)
        path.addEllipse(QPointF(cx, cy), s * 0.2, s * 0.2)
        return path.simplified()
    if name == "wave":                                   # спокойное — гладкая волна-лента
        top, bot = QPainterPath(), None
        n = 48
        pts = [(s * 0.08 + i / n * s * 0.84, cy - s * 0.06 + math.sin(i / n * math.pi * 2.0) * s * 0.16)
               for i in range(n + 1)]
        top.moveTo(pts[0][0], pts[0][1] - s * 0.12)
        for x, y in pts:
            top.lineTo(x, y - s * 0.12)
        for x, y in reversed(pts):
            top.lineTo(x, y + s * 0.12)
        top.closeSubpath()
        return top
    if name == "drop":                                   # грустное — капля
        path.moveTo(cx, s * 0.06)
        path.cubicTo(QPointF(cx + s * 0.1, s * 0.3), QPointF(cx + s * 0.36, s * 0.46), QPointF(cx + s * 0.32, s * 0.66))
        path.cubicTo(QPointF(cx + s * 0.28, s * 0.92), QPointF(cx - s * 0.28, s * 0.92), QPointF(cx - s * 0.32, s * 0.66))
        path.cubicTo(QPointF(cx - s * 0.36, s * 0.46), QPointF(cx - s * 0.1, s * 0.3), QPointF(cx, s * 0.06))
        return path
    if name == "planet":                                 # настроение дня — планета с кольцом
        path.addEllipse(QPointF(cx, cy), s * 0.27, s * 0.27)
        ring = QPainterPath()
        ring.addEllipse(QPointF(0, 0), s * 0.46, s * 0.13)
        st = QPainterPathStroker()
        st.setWidth(s * 0.07)
        r2 = st.createStroke(ring)
        from PyQt6.QtGui import QTransform
        r2 = QTransform().translate(cx, cy).rotate(-22).map(r2)
        return path.united(r2)
    if name == "sparkle":                                # незнакомое — искра
        return _star_path(cx, cy, s * 0.47, 4, 0.26).united(_star_path(s * 0.8, s * 0.2, s * 0.13, 4, 0.3))
    if name == "heart":                                  # любимое — сердце
        return _heart_path(cx, cy + s * 0.04, s * 1.1)
    if name == "horns":                                  # рок/метал — «коза»
        k = s / 56.0
        pts = [(8, 48), (14, 8), (28, 24), (44, 6), (50, 46), (40, 46), (38, 24), (28, 36), (18, 22), (17, 48)]
        path.moveTo(pts[0][0] * k, pts[0][1] * k)
        for x, y in pts[1:]:
            path.lineTo(x * k, y * k)
        path.closeSubpath()
        return path
    if name == "mic":                                    # хип-хоп/трэп/фонк — микрофон
        path.addRoundedRect(QRectF(cx - s * 0.16, s * 0.06, s * 0.32, s * 0.48), s * 0.16, s * 0.16)
        path.addRoundedRect(QRectF(cx - s * 0.05, s * 0.5, s * 0.1, s * 0.3), s * 0.04, s * 0.04)
        path.addRoundedRect(QRectF(cx - s * 0.2, s * 0.8, s * 0.4, s * 0.1), s * 0.05, s * 0.05)
        arc = QPainterPath()
        arc.arcMoveTo(QRectF(cx - s * 0.26, s * 0.12, s * 0.52, s * 0.52), 200)
        arc.arcTo(QRectF(cx - s * 0.26, s * 0.12, s * 0.52, s * 0.52), 200, 140)
        st = QPainterPathStroker()
        st.setWidth(s * 0.06)
        st.setCapStyle(Qt.PenCapStyle.RoundCap)
        return path.united(st.createStroke(arc)).simplified()
    if name == "eq":                                     # электроника — эквалайзер
        for i, h in enumerate((0.42, 0.7, 0.52, 0.86, 0.6)):
            x = s * 0.1 + i * s * 0.165
            path.addRoundedRect(QRectF(x, s * 0.92 - s * h, s * 0.12, s * h), s * 0.06, s * 0.06)
        return path.simplified()
    if name == "retro":                                  # синтвейв — закатное солнце в полоску
        path.addEllipse(QPointF(cx, cy), s * 0.42, s * 0.42)
        cut = QPainterPath()
        for i, y in enumerate((0.56, 0.68, 0.79)):
            cut.addRect(QRectF(0, s * y, s, s * (0.035 + i * 0.015)))
        return path.subtracted(cut)
    if name == "cloud":                                  # эмбиент/дрим-поп — облако
        for x, y, r in ((0.32, 0.56, 0.2), (0.52, 0.42, 0.25), (0.7, 0.58, 0.18)):
            path.addEllipse(QPointF(s * x, s * y), s * r, s * r)
        path.addRoundedRect(QRectF(s * 0.14, s * 0.56, s * 0.72, s * 0.2), s * 0.1, s * 0.1)
        return path.simplified()
    if name == "moon":                                   # lo-fi — полумесяц
        path.addEllipse(QPointF(cx, cy), s * 0.4, s * 0.4)
        cut = QPainterPath()
        cut.addEllipse(QPointF(cx + s * 0.2, cy - s * 0.14), s * 0.33, s * 0.33)
        return path.subtracted(cut)
    if name == "broken":                                 # эмо — разбитое сердце
        h = _heart_path(cx, cy + s * 0.04, s * 1.1)
        crack = QPainterPath()
        crack.moveTo(cx + s * 0.02, s * 0.2)
        for x, y in ((-0.06, 0.38), (0.05, 0.5), (-0.04, 0.66), (0.02, 0.86), (0.08, 0.86), (0.03, 0.66),
                     (0.11, 0.5), (0.0, 0.38), (0.08, 0.2)):
            crack.lineTo(cx + s * x, s * y)
        crack.closeSubpath()
        return h.subtracted(crack)
    if name == "note":                                   # джаз/фанк/R&B/классика — две ноты
        path.addEllipse(QPointF(s * 0.28, s * 0.74), s * 0.14, s * 0.11)
        path.addEllipse(QPointF(s * 0.7, s * 0.66), s * 0.14, s * 0.11)
        path.addRect(QRectF(s * 0.37, s * 0.18, s * 0.06, s * 0.56))
        path.addRect(QRectF(s * 0.79, s * 0.1, s * 0.06, s * 0.56))
        beam = QPainterPath()
        beam.moveTo(s * 0.37, s * 0.18)
        beam.lineTo(s * 0.85, s * 0.1)
        beam.lineTo(s * 0.85, s * 0.24)
        beam.lineTo(s * 0.37, s * 0.32)
        beam.closeSubpath()
        return path.united(beam).simplified()
    if name == "pick":                                   # фолк/инди/латино — медиатор
        path.moveTo(cx, s * 0.92)
        path.cubicTo(QPointF(s * 0.2, s * 0.62), QPointF(s * 0.02, s * 0.2), QPointF(s * 0.22, s * 0.1))
        path.cubicTo(QPointF(s * 0.4, s * 0.02), QPointF(s * 0.6, s * 0.02), QPointF(s * 0.78, s * 0.1))
        path.cubicTo(QPointF(s * 0.98, s * 0.2), QPointF(s * 0.8, s * 0.62), QPointF(cx, s * 0.92))
        return path
    if name == "star":                                   # поп/саундтреки — звезда
        return _star_path(cx, cy + s * 0.03, s * 0.47, 5, 0.47)
    return None


def wave_icon(kind: str, c1: str, c2: str, size: int = 56, seed: int = 0, cover: str = "",
              source=None) -> QPixmap:
    key = (kind, c1, c2, size, seed, cover, source.cacheKey() if source is not None else 0)
    if key in _ICONS:
        _ICONS.move_to_end(key)
        return _ICONS[key]
    dpr = 2
    pm = QPixmap(size * dpr, size * dpr)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size
    rng = random.Random(seed)
    if kind == "artist":
        path = QPainterPath()
        path.addEllipse(QRectF(2, 2, s - 4, s - 4))
        p.setClipPath(path)
        src = QPixmap.fromImage(source) if source is not None else (load_pixmap(cover, size * dpr) if cover else QPixmap())
        if src.isNull():
            g = QLinearGradient(0, 0, s, s)
            g.setColorAt(0, QColor(c1)); g.setColorAt(1, QColor(c2))
            p.fillRect(pm.rect(), g)
        else:
            m = min(src.width(), src.height())
            p.drawPixmap(QRectF(2, 2, s - 4, s - 4), src,
                         QRectF((src.width() - m) / 2, (src.height() - m) / 2, m, m))
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(2, 2, s - 4, s - 4))
    elif kind == "back":
        pen = QPen(QColor(YELLOW), s * 0.075, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                   Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        path = QPainterPath()
        path.moveTo(s * 0.26, s * 0.42)
        path.lineTo(s * 0.62, s * 0.42)
        path.cubicTo(s * 0.86, s * 0.42, s * 0.86, s * 0.76, s * 0.62, s * 0.76)
        path.lineTo(s * 0.22, s * 0.76)
        p.drawPath(path)
        p.drawLine(QPointF(s * 0.26, s * 0.42), QPointF(s * 0.40, s * 0.28))
        p.drawLine(QPointF(s * 0.26, s * 0.42), QPointF(s * 0.40, s * 0.56))
    else:
        cx, cy = s / 2, s / 2
        path = QPainterPath()
        shaped = _shape(kind, s) if ":" in kind else None
        if shaped is not None:                # своя фигура у каждого настроения и жанра (_shape)
            path = shaped
        elif kind == "blob":                  # четырёхлепестковая «клякса»-X
            n = 220
            rot = math.radians(45 + rng.uniform(-14, 14))
            for i in range(n + 1):
                a = i / n * 2 * math.pi
                r = s * 0.46 * (0.52 + 0.48 * abs(math.cos(2 * a)) ** 0.55)
                r *= 1 + 0.05 * math.sin(3 * a + seed)
                x = cx + math.cos(a + rot) * r
                y = cy + math.sin(a + rot) * r
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            path.closeSubpath()
        elif kind == "bolt":                  # «Z»-молния
            k = s / 56.0
            pts = [(9, 12), (47, 6), (30, 26), (49, 27), (9, 51), (25, 30), (7, 31)]
            path.moveTo(pts[0][0] * k, pts[0][1] * k)
            for x, y in pts[1:]:
                path.lineTo(x * k, y * k)
            path.closeSubpath()
            p.translate(cx, cy); p.rotate(rng.uniform(-10, 10)); p.translate(-cx, -cy)
        elif kind == "m":                      # «М»-форма (метал/рок)
            k = s / 56.0
            pts = [(8, 48), (14, 8), (28, 24), (44, 6), (50, 46), (40, 46), (38, 24), (28, 36),
                   (18, 22), (17, 48)]
            path.moveTo(pts[0][0] * k, pts[0][1] * k)
            for x, y in pts[1:]:
                path.lineTo(x * k, y * k)
            path.closeSubpath()
        else:                                  # «капля»
            path.addEllipse(QRectF(s * 0.12, s * 0.12, s * 0.76, s * 0.76))
        g = QLinearGradient(0, 0, s, s)
        g.setColorAt(0.0, QColor(c1))
        g.setColorAt(1.0, QColor(c2))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawPath(path)
        # объём: блик сверху-слева и тень снизу
        hl = QRadialGradient(QPointF(s * 0.32, s * 0.28), s * 0.55)
        hl.setColorAt(0, QColor(255, 255, 255, 110))
        hl.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(hl)
        p.drawPath(path)
        sh = QLinearGradient(0, s * 0.4, 0, s)
        sh.setColorAt(0, QColor(0, 0, 0, 0))
        sh.setColorAt(1, QColor(0, 0, 0, 80))
        p.setBrush(sh)
        p.drawPath(path)
    p.end()
    _ICONS[key] = pm
    while len(_ICONS) > 128:
        _ICONS.popitem(last=False)
    return pm


# ══════════════════════════════════════════════════════════════════════════ #
#  Список волн по дуге
# ══════════════════════════════════════════════════════════════════════════ #

class WaveWheel(QWidget):
    """items: dict(kind, arg, label, icon, c1, c2, sub, cover, accent)."""
    activated = pyqtSignal(object, object)
    _avatar_ready = pyqtSignal(int, int, str, object)

    ITEM_H = 68
    ROW_BUDGET = 8 * 1024 * 1024

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self._backdrop = None
        self.items: list[dict] = []
        self.off = 0.0               # индекс пункта в центре (дробный)
        self.target = 0.0
        self.active = None           # (kind, arg) текущей волны
        self._hover = -1
        self._rows = OrderedDict()
        self._row_bytes = 0
        self._avatars = OrderedDict()
        self._pending = {}
        self._avatar_pool = None
        self._generation = 0
        self._avatar_ready.connect(self._on_avatar_ready)
        self._timer = FrameTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._rows_ver = 0                   # меняется вместе с картинками строк (аватары, размер, пункты)
        self._layer = None
        self._layer_k = None
        self._clear_from = None              # GPU-туманность: правее этого x — прозрачно (её видно сквозь)

    def set_items(self, items):
        self._timer.stop()
        self._rows_ver += 1
        self._hover = -1
        self._generation += 1
        for future in self._pending.values():
            future.cancel()
        self._pending.clear()
        self._avatars.clear()
        self._rows.clear()
        self._row_bytes = 0
        self.items = items
        mid = (len(items) - 1) / 2.0
        self.off = self.target = min(mid, 4.0)
        self.update()

    def shutdown(self):
        self._timer.stop()
        self._generation += 1
        if self._avatar_pool is not None:
            self._avatar_pool.shutdown(wait=False, cancel_futures=True)
            self._avatar_pool = None
        self._pending.clear()

    def hideEvent(self, e):
        self._timer.stop()
        super().hideEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        if abs(self.target - self.off) > 0.002:
            self._start_scroll()

    def resizeEvent(self, e):
        self._rows.clear()
        self._row_bytes = 0
        self._rows_ver += 1
        super().resizeEvent(e)

    def _start_scroll(self):
        if not self._timer.isActive():
            self._last_t = time.monotonic()
            self._timer.start()

    def set_active(self, key):
        self.active = key
        self.update()

    def _tick(self):
        n = len(self.items)
        if n and abs(self.off) > n * 4:               # держим числа маленькими
            shift = round(self.off / n) * n
            self.off -= shift
            self.target -= shift
        d = self.target - self.off
        now = time.monotonic()
        dt = animation_delta(now - getattr(self, "_last_t", now - 1 / 60), .05)
        self._last_t = now
        if abs(d) < 0.002:
            self.off = self.target
            self._timer.stop()
        else:
            self.off += d * (1.0 - 0.82 ** (dt * 60.0))        # 0.18 «за кадр 60 Гц» при любой частоте
        self.update()

    def wheelEvent(self, e):
        pixels = e.pixelDelta().y()
        delta = pixels / self.ITEM_H if pixels else e.angleDelta().y() / 120.0
        self.target -= delta                       # бесконечная лента — без упора
        self._start_scroll()
        e.accept()

    def _pos(self, i, copy=0):
        """Позиция пункта относительно центра (в пунктах) — с заворотом по кругу."""
        n = max(1, len(self.items))
        p = (i - self.off + n / 2) % n - n / 2
        return p + copy * n

    def _geom(self, i, copy=0):
        return self._geom_at(self._pos(i, copy))

    def _geom_at(self, pos):
        H, W = self.height(), self.width()
        cy = H / 2
        y = cy + pos * self.ITEM_H
        d = (y - cy) / max(1.0, H / 2)               # -1..1
        x = W * 0.20 + (d * d) * W * 0.24            # дуга: середина левее, края правее
        alpha = max(0.0, 1.0 - abs(d) ** 2.2 * 0.85)
        sc = 1.0 - 0.10 * min(1.0, abs(d))
        return x, y, alpha, sc

    def _copies(self):
        n = max(1, len(self.items))
        k = int(math.ceil(self.height() / max(1, n * self.ITEM_H))) + 1
        return range(-k, k + 1)

    def _hit(self, pos):
        for i, slot, x, y, a, sc in self._visible_items():
            if a > 0.1 and abs(pos.y() - y) < self.ITEM_H / 2 and x - 10 <= pos.x() <= self.width() - 10:
                return (i, slot)
        return None

    def _visible_items(self):
        """Work depends on viewport height, even for a long artist list."""
        n = len(self.items)
        if not n:
            return
        reach = self.height() / (2 * self.ITEM_H) + 1
        for slot in range(math.floor(self.off - reach), math.ceil(self.off + reach) + 1):
            x, y, a, sc = self._geom_at(slot - self.off)
            if -self.ITEM_H <= y <= self.height() + self.ITEM_H and a > 0.02:
                yield slot % n, slot, x, y, a, sc

    def _request_avatar(self, i, it):
        cover = it.get("cover", "")
        if it.get("icon") != "artist" or not cover or i in self._avatars or i in self._pending:
            return
        if len(self._pending) >= 8:
            return
        if self._avatar_pool is None:
            pool = self._avatar_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wave-avatar")
            self.destroyed.connect(lambda: pool.shutdown(wait=False, cancel_futures=True))
        self._pending[i] = self._avatar_pool.submit(
            self._decode_avatar, weakref.ref(self), self._generation, i, cover)

    @staticmethod
    def _decode_avatar(ref, generation, i, cover):
        try:
            image = read_image(cover, 112)
        except Exception:                            # unreadable avatar still completes its request
            image = QImage()
        widget = ref()
        if widget is not None:
            try:
                widget._avatar_ready.emit(generation, i, cover, image)
            except RuntimeError:                    # widget deleted during decode
                pass

    def _on_avatar_ready(self, generation, i, cover, image):
        if generation != self._generation or i >= len(self.items) or self.items[i].get("cover") != cover:
            return
        self._pending.pop(i, None)
        self._avatars[i] = image
        self._avatars.move_to_end(i)
        while len(self._avatars) > 32:
            self._avatars.popitem(last=False)
        for key in list(self._rows):
            if key[0] == i:
                pm = self._rows.pop(key)
                self._row_bytes -= pm.width() * pm.height() * 4
        self._rows_ver += 1
        self.update()

    def _row_pixmap(self, i, active):
        """Rasterize text once; scrolling scales a small cached row, not glyphs."""
        key = (i, active)
        if key in self._rows:
            self._rows.move_to_end(key)
            return self._rows[key]
        it = self.items[i]
        label_font = _font(15, QFont.Weight.Bold)
        sub_font = _font(11, QFont.Weight.DemiBold)
        tx = 70
        text_width = max(QFontMetrics(label_font).horizontalAdvance(it["label"]),
                         QFontMetrics(sub_font).horizontalAdvance(it.get("sub", "")))
        width = max(56, min(int(self.width() * .8), tx + text_width + 4))
        pm = QPixmap(max(1, width * 2), self.ITEM_H * 2)
        pm.setDevicePixelRatio(2)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        image = self._avatars.get(i)
        loaded = image is not None and not image.isNull()
        icon = wave_icon(it["icon"], it.get("c1", "#fff"), it.get("c2", "#888"), 56,
                         seed=i * 13 + 5, cover=it.get("cover", "") if loaded else "", source=image)
        p.drawPixmap(QPointF(0, (self.ITEM_H - 56) / 2), icon)
        if it.get("sub"):
            p.setFont(sub_font)
            p.setPen(QColor(150, 150, 150))
            p.drawText(QRectF(tx, self.ITEM_H / 2 - 19, width - tx, 16),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, it["sub"])
        p.setFont(label_font)
        p.setPen(QColor(YELLOW) if (it.get("accent") or active) else QColor(255, 255, 255))
        p.drawText(QRectF(tx, self.ITEM_H / 2 - (3 if it.get("sub") else 12), width - tx,
                          22 if it.get("sub") else 24),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, it["label"])
        p.end()
        self._rows[key] = pm
        self._row_bytes += pm.width() * pm.height() * 4
        while self._row_bytes > self.ROW_BUDGET and len(self._rows) > 1:
            _, old = self._rows.popitem(last=False)
            self._row_bytes -= old.width() * old.height() * 4
        return pm

    def mouseMoveEvent(self, e):
        h = self._hit(e.position())
        hi = h[0] if h else -1
        if hi != self._hover:
            self._hover = hi
            self.setCursor(Qt.CursorShape.PointingHandCursor if hi >= 0 else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mousePressEvent(self, e):
        h = self._hit(e.position())
        if h and e.button() == Qt.MouseButton.LeftButton:
            i, slot = h
            it = self.items[i]
            self.target = float(slot)
            self._start_scroll()
            self.activated.emit(it["kind"], it.get("arg"))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._clear_from is not None:             # под нами туманность на GPU: чёрное — только слева от неё
            p.fillRect(QRect(0, 0, int(self._clear_from), self.height()), QColor(0, 0, 0))
        else:
            if not _ph_backdrop(self, p):
                p.fillRect(self.rect(), QColor(0, 0, 0))
            if self._backdrop is not None:
                self._backdrop(p)
        if self._timer.isActive():                   # круг крутится — пункты рисуются прямо в кадр
            self._paint_items(p)
            p.end()
            return
        # Круг стоит, а фон под ним (туманность) меняется каждый кадр: пункты — одна готовая картинка.
        dpr = self.devicePixelRatioF()
        key = (self.off, self._hover, self.active, self.width(), self.height(), dpr, self._rows_ver,
               len(self.items))
        if key != self._layer_k or self._layer is None:
            layer = QPixmap(max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr)))
            layer.setDevicePixelRatio(dpr)
            layer.fill(Qt.GlobalColor.transparent)
            lp = QPainter(layer)
            lp.setRenderHint(QPainter.RenderHint.Antialiasing)
            lp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            self._paint_items(lp)
            lp.end()
            self._layer, self._layer_k = layer, key
        p.drawPixmap(0, 0, self._layer)
        p.end()

    def _paint_items(self, p):
        for i, slot, x, y, alpha, sc in self._visible_items():
            it = self.items[i]
            self._request_avatar(i, it)
            hover = i == self._hover
            act = self.active == (it["kind"], it.get("arg"))
            p.save()
            p.setOpacity(min(1.0, alpha * (1.0 if (hover or act) else 0.92)))
            p.translate(x, y)
            s = sc * (1.06 if hover else 1.0)
            p.scale(s, s)
            p.drawPixmap(QPointF(0, -self.ITEM_H / 2), self._row_pixmap(i, act))
            p.restore()


# ══════════════════════════════════════════════════════════════════════════ #
#  Страница «Моя волна»
# ══════════════════════════════════════════════════════════════════════════ #

class _CachedButton(QPushButton):
    """Кнопка поверх живой туманности перерисовывается с каждым её кадром. Вид кнопки (QSS-стекло,
    текст, иконка, наведение/нажатие) рисуется стилем один раз в картинку, дальше — копия."""

    def paintEvent(self, _):
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        dpr = self.devicePixelRatioF()
        key = (self.width(), self.height(), dpr, opt.state.value, opt.text, self.styleSheet(),
               opt.icon.cacheKey(), opt.iconSize.width(), opt.iconSize.height())
        if key != self.__dict__.get("_ck"):
            pm = QPixmap(max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr)))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.GlobalColor.transparent)
            q = QPainter(pm)
            self.style().drawControl(QStyle.ControlElement.CE_PushButton, opt, q, self)
            q.end()
            self._ck, self._cpm = key, pm
        p = QPainter(self)
        p.drawPixmap(0, 0, self._cpm)
        p.end()


class _ShadowLabel(QLabel):
    """Подпись с мягкой тенью над туманностью. QGraphicsDropShadowEffect размывал тень заново
    на каждом кадре туманности; здесь текст с тенью — готовая картинка, пересобирается при смене
    текста или размера."""
    BLUR = 10
    OFFSET = 1
    SHADOW = QColor(0, 0, 0, 150)

    def paintEvent(self, e):
        dpr = self.devicePixelRatioF()
        key = (self.text(), self.width(), self.height(), dpr, self.styleSheet())
        if key != self.__dict__.get("_ck"):
            W, H = max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr))
            text = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
            text.setDevicePixelRatio(dpr)
            text.fill(0)
            q = QPainter(text)                                 # как QLabel: текст стилем, цвет из QSS
            q.setFont(self.font())
            self.style().drawItemText(q, self.contentsRect(), int(self.alignment().value), self.palette(),
                                      self.isEnabled(), self.text(), self.foregroundRole())
            q.end()
            shadow = QImage(text)
            q = QPainter(shadow)
            q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            q.fillRect(shadow.rect(), self.SHADOW)
            q.end()
            try:
                from blur_fx import blur_image
                shadow = blur_image(shadow, self.BLUR * 0.5 * dpr)
                shadow.setDevicePixelRatio(dpr)
            except Exception:                                  # noqa: BLE001
                pass
            pm = QPixmap(W, H)
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.GlobalColor.transparent)
            q = QPainter(pm)
            q.drawImage(QRectF(0, self.OFFSET, self.width(), self.height()), shadow)
            q.drawImage(QRectF(0, 0, self.width(), self.height()), text)
            q.end()
            self._ck, self._cpm = key, pm
        p = QPainter(self)
        p.drawPixmap(0, 0, self._cpm)
        p.end()


def gpu_enabled() -> bool:
    import os
    if os.environ.get("ECHOES_NO_GPU_NEBULA") == "1" or os.environ.get("ECHOES_SOFT_GL") == "1"             or not (_NATIVE and hasattr(_NF, "NebParams")):       # программный OpenGL (sysprobe) — без GL-слоёв
        return False
    try:
        import native_ui
        return native_ui.available()
    except Exception:                                      # noqa: BLE001
        return False


GL_RELEASE_MS = 600000                 # страница скрыта 10 мин — её GL-контекст отдаём (≈19 МБ у драйвера);
                                       # раньше (20 с) возвращение на страницу пересоздавало его — рывок


def release_gl_later(owner):
    """owner (WavePage / WaveHero) скрыт: через GL_RELEASE_MS, если он всё ещё скрыт, удалить его GL-виджет.
    У драйвера видеокарты каждый контекст OpenGL — ~19 МБ памяти процесса; при следующем показе виджет
    создаётся заново тем же путём, что и в первый раз (_gl_try)."""
    t = owner.__dict__.get("_gl_release_t")
    if t is None:
        t = owner._gl_release_t = QTimer(owner)
        t.setSingleShot(True)

        def fire():
            try:
                if owner.isVisible() or owner._gl is None or owner._gl_state != "on":
                    return
                gl, owner._gl = owner._gl, None
                owner._gl_state = "untried"
                gl.widget.hide()
                gl.widget.deleteLater()
            except RuntimeError:
                pass
        t.timeout.connect(fire)
    t.start(GL_RELEASE_MS)


def gpu_anchor(win):
    """Крошечный GL-виджет в главном окне до его показа: окно сразу создаётся с GPU-совмещением.
    Без него первый GPU-слой заставлял Qt спрятать окно и создать его заново (окно «мигало»)."""
    if not gpu_enabled() or win.__dict__.get("_gpu_anchor") is not None:
        return
    import native_ui
    host = win.centralWidget() or win
    a = native_ui.NebulaGL()
    a.widget.setParent(host)
    a.widget.setGeometry(max(0, host.width() // 2), max(0, host.height() // 2), 1, 1)
    a.widget.lower()                                       # под непрозрачным фоном интерфейса — не виден
    a.widget.show()
    win._gpu_anchor = a

    def check(tries=[0]):
        if a.ok():
            return
        tries[0] += 1
        if tries[0] < 30 and not win.isVisible() or tries[0] < 12:   # OpenGL готов не сразу после show()
            QTimer.singleShot(150, check)
            return
        print("[gpu] OpenGL недоступен — GPU-слои выключены")
        a.widget.hide()
        a.widget.deleteLater()
        win._gpu_anchor = None
    QTimer.singleShot(150, check)


_GLOW_WORKERS=weakref.WeakSet()

def shutdown_workers():
    workers=list(_GLOW_WORKERS)
    for worker in workers:worker.stop()
    for worker in workers:
        if worker.is_alive() and worker is not threading.current_thread():worker.join(2)

class _GlowWorker(threading.Thread):
    """Считает кадры туманности в фоне (C++ и numpy отпускают GIL) — GUI только рисует."""

    def __init__(self, neb: NebulaField):
        super().__init__(daemon=True, name="wave-glow")
        _GLOW_WORKERS.add(self)
        self.neb = neb
        self._cond = threading.Condition()
        self._job = None
        self._alive = True
        self.result = None
        self._scheme = None
        self._hit = 0.0
        self.lock = threading.Lock()          # render state belongs to this worker

    def set_scheme(self, cols, instant=False):
        with self._cond:
            self._scheme = (cols, instant)

    def hit(self, strength):
        with self._cond:
            self._hit = max(self._hit, strength)

    def submit(self, *job) -> bool:
        with self._cond:
            if self._job is not None:
                return False
            self._job = job
            self._cond.notify()
            return True

    def stop(self):
        with self._cond:
            self._alive = False
            self._cond.notify()

    def take(self):
        with self._cond:
            r, self.result = self.result, None
        return r

    def run(self):
        while True:
            with self._cond:
                while self._job is None and self._alive:
                    self._cond.wait()
                if not self._alive:
                    return
                job = self._job
                scheme, strength = self._scheme, self._hit
                self._scheme, self._hit = None, 0.0
            img = None
            try:
                with self.lock:
                    if scheme is not None:
                        self.neb.set_scheme(*scheme)
                    if strength:
                        self.neb.hit(strength)
                    img = self.neb.render(*job)
                if not (_NATIVE and hasattr(_NF, "nebula_render")):
                    img = img.copy()
            except Exception as e:                 # noqa: BLE001
                print("[wave] nebula:", e)
            finally:
                with self._cond:
                    if img is not None:
                        self.result = img
                    self._job = None


def _rgba(c, a):
    q = QColor(c)
    return f"rgba({q.red()},{q.green()},{q.blue()},{a:.2f})"


class WavePage(QWidget):
    """Чёрная страница в стиле Яндекс Музыки: слева дуга-список волн, справа живая туманность,
    по центру «▶ Моя волна» (щелчок — играть/пауза), под ней — чип настроения с крестиком или
    «Настроить»."""
    title_clicked = pyqtSignal()
    reset_mood = pyqtSignal()
    LEFT = 0.30                                  # доля ширины под список волн

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setMouseTracking(True)
        self.neb = NebulaField()
        self.glow = self.neb                     # старое имя (тесты, тема)
        _LIVE.add(self)
        self._worker = _GlowWorker(self.neb)
        self._worker.start()
        self._title_pm = None
        self._title_rect = QRectF()
        self.title = "Моя волна"
        self.kind = "my"
        self._playing = False
        self._img = None
        self._beat = 0.0
        self._t0 = time.monotonic()
        self._last = time.monotonic()
        self.wheel = WaveWheel(self)
        self.wheel._backdrop = self._paint_wheel_background

        # прежний блок (обложка, подпись, кнопки) — скрыт: в новом виде управление в нижней панели,
        # но объекты нужны теме (иконки, сердечко, обложка для цвета туманности)
        self.ctrl = QWidget(self)
        self.ctrl.setObjectName("YaPage")
        self.ctrl.hide()
        v = QVBoxLayout(self.ctrl)
        self.cover = QLabel()
        self.cover.setFixedSize(60, 60)
        self.track_lbl = QLabel("Ничего не играет")
        self.like_btn = QPushButton()
        self.more_btn = QPushButton()
        self.prev_btn = QPushButton()
        self.play_btn = QPushButton()
        self.next_btn = QPushButton()
        for w_ in (self.cover, self.track_lbl, self.like_btn, self.more_btn, self.prev_btn, self.play_btn,
                   self.next_btn):
            v.addWidget(w_)

        # «Настроить» (пилюля, когда настроение не выбрано, или круглая кнопка рядом с чипом)
        self.tune_btn = _CachedButton("  Настроить", self)
        self.tune_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tune_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tune_btn.setFixedHeight(40)
        # чип выбранного настроения/жанра/исполнителя: щелчок — вернуться к «Моей волне»
        self.mood_chip = _CachedButton("", self)
        self.mood_chip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mood_chip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.mood_chip.setFixedHeight(40)
        self.mood_chip.setToolTip("Вернуться к «Моей волне»")
        self.mood_chip.clicked.connect(self.reset_mood.emit)
        self.mood_chip.hide()
        self.hint = _ShadowLabel("", self)
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setStyleSheet("color:rgba(255,255,255,0.82);font-size:12px;font-weight:600;background:transparent;")
        self._scheme = scheme_for("my")
        self._mood_scheme = scheme_for("my")
        self._cover_scheme = None
        self._style_chips()

        self._timer = FrameTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._gl = None                         # туманность на видеокарте (echoes_ui.dll), если есть OpenGL
        self._gl_state = "untried"              # untried → trying → on / off
        self._overlay_k = None

    # ── туманность на GPU ── #

    def _gl_try(self):
        """Первый показ: создать GL-виджет под всем остальным. OpenGL не завёлся — остаёмся на CPU."""
        if self._gl_state != "untried":
            return
        self._gl_state = "off"
        if not gpu_enabled():
            return
        try:
            import native_ui
            if not native_ui.available():
                return
            gl = native_ui.NebulaGL()
            gl.widget.setParent(self)
            gl.widget.setGeometry(self.rect())
            gl.widget.lower()
            gl.widget.show()
            self._gl = gl
            self._gl_state = "trying"
            QTimer.singleShot(0, self._gl_check)
        except Exception as e:                       # noqa: BLE001
            print("[wave] gpu:", e)

    def _gl_check(self):
        gl = self._gl
        if gl is None:
            return
        if gl.ok():
            self._gl_state = "on"
            gl.scale(GPU_PAGE_SCALE)                    # на странице облако компактнее, чем на баннере
            self.wheel._clear_from = 0                  # туманность видна и под списком (лучи без обреза)
            self.wheel.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
            self._gl_mask()
            self._overlay_k = None
            self.update()
            self.wheel.update()
            return
        print("[wave] gpu: OpenGL недоступен — туманность на CPU")
        self._gl_state = "off"
        gl.widget.hide()
        gl.widget.deleteLater()
        self._gl = None

    def _gl_mask(self):
        if self._gl is None:
            return
        if _phantom():                                 # фон за панелью — в накладке: скруглять нечего, без уголков
            self._gl.widget.clearMask()
            return
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 16, 16)
        self._gl.widget.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def _gl_overlay(self):
        """Всё, что поверх туманности и меняется редко: чёрная полоса под списком, градиент, заголовок."""
        W, H = self.width(), self.height()
        dpr = self.devicePixelRatioF()
        if self._title_pm is None:
            self._title_pm = self._make_title(W)
        key = (W, H, dpr, id(self._title_pm), _backdrop_key(self))
        if key == self._overlay_k:
            return
        self._overlay_k = key
        pm = QPixmap(max(1, int(W * dpr)), max(1, int(H * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        bd = _screen_backdrop(self, W, H, dpr)          # Phantom: туманность светит поверх размытой картинки
        if bd is not None:
            p.drawImage(0, 0, bd)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self._paint_decor(p, W, H, soft=True)
        p.end()
        self._gl.overlay(pm)

    # ── API ── #

    def burst(self):
        """Волну включили: лучи света вылетают и через пару секунд успокаиваются (на GPU)."""
        self._burst_t0 = time.monotonic()

    def _burst_level(self) -> float:
        t0 = self.__dict__.get("_burst_t0")
        if t0 is None:
            return 0.0
        el = time.monotonic() - t0
        if el > 4.0:
            self._burst_t0 = None
            return 0.0
        return (1.0 - math.exp(-el / 0.08)) * math.exp(-el / 0.9)   # быстрый выброс, плавное затухание

    def set_mood(self, title, kind, arg, instant=False):
        self.kind = kind
        self.mood_title = title
        if not instant:
            self.burst()
        self._mood_scheme = scheme_for(kind, arg)
        # «Моя волна» — в цветах обложки играющего трека; выбранное настроение/жанр — в своих цветах
        self._apply_scheme(self._cover_scheme if (kind == "my" and self._cover_scheme) else self._mood_scheme,
                           instant)
        if kind == "my":
            self.mood_chip.hide()
        else:
            self.mood_chip.setText(f"{title}   ×")
            self.mood_chip.show()
        self._style_chips()
        self._layout()
        self.update()

    def set_track(self, cover=None):
        """Новый трек: туманность перетекает в цвета его обложки (серая/нет — цвета настроения)."""
        sch = cover_scheme(cover) if cover is not None else None
        self._cover_scheme = sch
        self._apply_scheme(sch if (self.kind == "my" and sch) else self._mood_scheme)

    def _apply_scheme(self, sch, instant=False):
        self._scheme = sch
        self._worker.set_scheme(sch, instant)
        if self._gl_state == "on":
            with self._worker.lock:
                self.neb.set_scheme(sch, instant)
        self._style_chips()

    def _style_chips(self):
        from echo_glass import glass_controls_qss
        glass = glass_controls_qss()
        self.mood_chip.setStyleSheet(glass + "QPushButton{color:#ffffff;border-radius:20px;padding:0 18px;font-size:15px;font-weight:700;}")
        icon_only = self.kind != "my"
        self.tune_btn.setText("" if icon_only else "  Настроить")
        # «Настроить» — прозрачная: туманность видна сквозь неё, кнопку выдаёт только тонкий контур
        self.tune_btn.setStyleSheet(f"QPushButton{{background:transparent;color:#ffffff;border:1px solid rgba(255,255,255,0.22);"
                                    f"border-radius:20px;padding:0 {0 if icon_only else 18}px;font-size:14px;font-weight:700;}}"
                                    "QPushButton:hover{background:rgba(255,255,255,0.08);border-color:rgba(255,255,255,0.45);}"
                                    "QPushButton:pressed{background:rgba(255,255,255,0.14);}")
        self.tune_btn.ensurePolished()
        self.tune_btn.setFixedWidth(40 if icon_only else self.tune_btn.sizeHint().width() + 20)

    # ── цикл ── #

    def showEvent(self, e):
        super().showEvent(e)
        self._gl_try()
        self._last = time.monotonic()
        self._timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()
        release_gl_later(self)

    def shutdown(self):
        self._timer.stop()
        self.wheel.shutdown()
        self._worker.stop()
        if self._worker.is_alive():self._worker.join(2)

    def _center(self):
        return (self.LEFT + 1.0) / 2 + 0.01, 0.42

    def _geom(self):
        W, H = max(1, self.width()), max(1, self.height())
        cx, cy = self._center()
        area = W * (1 - self.LEFT)
        R = max(140.0, min(area, H) * 0.46)
        return W, H, cx * W, cy * H, R

    def _layout(self):
        W, H, cx, cy, _R = self._geom()
        y = int(cy + max(40, min(76, W * 0.045)) * 0.75 + 24)
        tw = self.tune_btn.width()
        cw = self.mood_chip.sizeHint().width() + 8 if self.mood_chip.isVisible() else 0
        if self.mood_chip.isVisible():
            self.mood_chip.setFixedWidth(cw)
        gap = 10 if cw else 0
        x = int(cx - (tw + gap + cw) / 2)
        self.tune_btn.move(x, y)
        if cw:
            self.mood_chip.move(x + tw + gap, y)
        self.hint.setGeometry(int(cx - 300), y + 54, 600, 22)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        W, H = self.width(), self.height()
        ww = max(int(W * 0.34), min(320, int(W * 0.44)))   # узкое окно: подписи настроений не обрезаются
        self.wheel.setGeometry(0, 0, ww, H)
        self.LEFT = max(WavePage.LEFT, ww / max(1, W) - 0.04)
        self._title_pm = None
        if self._gl is not None:
            self._gl.widget.setGeometry(self.rect())
            self._gl_mask()
            if self._gl_state == "on":
                self.wheel._clear_from = 0
        self._layout()

    def _tick(self):
        now = time.monotonic()
        dt = animation_delta(now - self._last)
        self._last = now
        lvl = 0.0
        playing = False
        try:
            playing = bool(self.engine.is_playing())
            if playing:
                s = self.engine.get_visual_samples(512)
                if s is not None and len(s):
                    a = np.asarray(s, dtype=np.float32)
                    lvl = float(np.sqrt(np.mean(a * a)))
        except Exception:                            # noqa: BLE001
            lvl = 0.0
        if playing != self._playing:
            self._playing = playing
            self._title_pm = None
            self.update()
        target = min(1.0, lvl * 4.5)
        k = (1.0 - math.exp(-dt * 26.0)) if target > self._beat else (1.0 - math.exp(-dt * 5.0))
        self._beat += (target - self._beat) * k
        avg = getattr(self, "_avg", 0.0)
        a = 1.0 - math.exp(-dt * 1.9)
        self._avg = avg * (1.0 - a) + lvl * a
        self._cool = max(0.0, getattr(self, "_cool", 0.0) - dt)
        gpu = self._gl_state == "on"
        if lvl > 0.04 and lvl > avg * 1.32 and self._cool <= 0:
            strength = min(1.0, (lvl / max(avg, 1e-3) - 1.0) * 1.5 + 0.3)
            if gpu:
                with self._worker.lock:
                    self.neb.hit(strength)
            else:
                self._worker.hit(strength)
            self._cool = 0.28
        W, H, cx, cy, R = self._geom()
        if gpu:                                      # кадр считает видеокарта; темп задаёт FrameTimer (частота экрана)
            self._gl_overlay()
            b = self._burst_level()
            with self._worker.lock:                      # прежний кадр CPU мог ещё считаться в фоне
                P = self.neb.params(W, H, cx, cy, R, self._beat, dt * (GPU_PAGE_SPEED + 1.8 * b), 0,
                                    self.devicePixelRatioF())
            self._gl.burst(b)
            self._gl.params(P)
            import wave_veil                                 # та же туманность — на всё окно, под интерфейсом
            wave_veil.feed(self, P, b, GPU_PAGE_SCALE)
            return
        res = self._worker.take()
        if res is not None:
            self._img = res
            x0 = int(W * self.LEFT)
            self.update(QRect(x0, 0, W - x0, H))
            self.wheel.update(QRect(x0, 0, max(0, self.wheel.width() - x0), H))
        acc = min(.1, getattr(self, "_acc_dt", 0.0) + dt)
        target = __import__("frameclock").clock().rate
        step = 1 / min(NEBULA_MAX_FPS, max(30, target)) if _NATIVE else 1 / 30
        if (getattr(self.window(), "settings", None) or {}).get("lite_mode"):
            step = max(step, 1 / 24)                      # лёгкий режим: туманность 24 к/с
        # Рендер туманности ограничен 60 к/с и идёт в фоновом потоке сразу в размер окна.
        if acc >= step and self._worker.submit(max(8, int(W * NEBULA_RENDER_SCALE)),
                                                max(8, int(H * NEBULA_RENDER_SCALE)),
                                                cx * NEBULA_RENDER_SCALE, cy * NEBULA_RENDER_SCALE,
                                                R * NEBULA_RENDER_SCALE, self._beat, acc,
                                                W * self.LEFT * NEBULA_RENDER_SCALE,
                                                self.devicePixelRatioF()):
            self._acc_dt = 0.0
        else:
            self._acc_dt = acc

    # ── заголовок «▶ Моя волна» ── #

    def _make_title(self, W):
        px = max(40, min(80, W * 0.046))
        f = _font(px, QFont.Weight.Black)
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 97)
        fm = QFontMetrics(f)
        txt = _tr("Моя волна")
        gs = px * 0.62                                     # значок ▶ / ❚❚
        gap = px * 0.28
        tw = fm.horizontalAdvance(txt)
        pad = int(px * 0.6)
        Wp, Hp = int(gs + gap + tw + pad * 2), int(px * 1.5 + pad)
        dpr = self.devicePixelRatioF()

        def draw(q, col):
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            q.setPen(Qt.PenStyle.NoPen)
            q.setBrush(col)
            gy = Hp / 2
            gx = pad
            if self._playing:
                bw = gs * 0.30
                q.drawRoundedRect(QRectF(gx + gs * 0.08, gy - gs * 0.5, bw, gs), bw * 0.25, bw * 0.25)
                q.drawRoundedRect(QRectF(gx + gs * 0.62, gy - gs * 0.5, bw, gs), bw * 0.25, bw * 0.25)
            else:
                path = QPainterPath()
                path.moveTo(gx + gs * 0.08, gy - gs * 0.55)
                path.lineTo(gx + gs * 0.98, gy)
                path.lineTo(gx + gs * 0.08, gy + gs * 0.55)
                path.closeSubpath()
                q.drawPath(path)
            q.setFont(f)
            q.setPen(col)
            q.drawText(QRectF(gx + gs + gap, 0, tw + pad, Hp), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       txt)

        sh = QImage(int(Wp * dpr), int(Hp * dpr), QImage.Format.Format_ARGB32_Premultiplied)
        sh.setDevicePixelRatio(dpr)
        sh.fill(0)
        q = QPainter(sh)
        draw(q, QColor(0, 0, 0, 120))
        q.end()
        try:
            from blur_fx import blur_image
            sh = blur_image(sh, px * 0.22 * dpr)
            sh.setDevicePixelRatio(dpr)
        except Exception:                                  # noqa: BLE001
            pass
        pm = QPixmap(int(Wp * dpr), int(Hp * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.drawImage(QRectF(0, px * 0.04, Wp, Hp), sh)
        draw(q, QColor(255, 255, 255, 238))
        q.end()
        return pm, Wp, Hp

    def mouseMoveEvent(self, e):
        over = self._title_rect.contains(e.position())
        self.setCursor(Qt.CursorShape.PointingHandCursor if over else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._title_rect.contains(e.position()):
            if not self._playing:
                self.burst()                                   # «▶ Моя волна» — включили
            self.title_clicked.emit()
            return
        super().mousePressEvent(e)

    def _paint_wheel_background(self, p):
        # The wheel paints its own small background strip. Scrolling therefore
        # does not make Qt repaint the full nebula behind a transparent child.
        W, H = self.width(), self.height()
        x0 = int(W * self.LEFT)
        overlap = self.wheel.width() - x0
        if overlap <= 0 or self._img is None:
            return
        p.save()
        p.setClipRect(QRect(x0, 0, overlap, H))
        glass = _phantom()
        if glass:                                      # Phantom: свет туманности поверх фона панели
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        p.drawImage(QRectF(0, 0, W, H), self._img)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        if not glass:                                  # Phantom: без затемнения — список на том же стекле
            g = QLinearGradient(x0, 0, W * .44, 0)
            g.setColorAt(0.0, QColor(0, 0, 0, 255))
            g.setColorAt(.4, QColor(0, 0, 0, 170))
            g.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(QRectF(x0, 0, overlap, H), g)
        p.restore()

    def _paint_decor(self, p, W, H, soft=False):
        x0 = int(W * self.LEFT)
        if soft and _phantom():
            pass                                           # Phantom: лучи уходят под список без затемнения
        elif soft:
            # GPU: туманность идёт на всю ширину, лучи уходят под список и гаснут плавно (без обреза у края списка)
            g = QLinearGradient(0, 0, W * 0.46, 0)
            g.setColorAt(0.0, QColor(0, 0, 0, 236))
            g.setColorAt(x0 / max(1.0, W * 0.46) * 0.55, QColor(0, 0, 0, 214))
            g.setColorAt(x0 / max(1.0, W * 0.46), QColor(0, 0, 0, 150))
            g.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(QRectF(0, 0, W * 0.46, H), g)
        elif _phantom():                                   # Phantom: без затемнения у списка — нет шва
            pass
        else:
            p.fillRect(QRectF(0, 0, x0 + 1, H), QColor(0, 0, 0))
            g = QLinearGradient(x0, 0, W * 0.44, 0)        # мягкий переход от списка к туманности
            g.setColorAt(0.0, QColor(0, 0, 0, 255))
            g.setColorAt(0.4, QColor(0, 0, 0, 170))
            g.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(QRectF(x0, 0, W * 0.44 - x0, H), g)
        _W, _H, cx, cy, _R = self._geom()
        if self._title_pm is None:
            self._title_pm = self._make_title(W)
        pm, tw, th = self._title_pm
        tx, ty = cx - tw / 2, cy - th / 2
        p.drawPixmap(QPointF(tx, ty), pm)
        self._title_rect = QRectF(tx + th * 0.2, ty + th * 0.15, tw - th * 0.4, th * 0.7)

    def paintEvent(self, _):
        if self._gl_state == "on":                   # всё рисует GPU-виджет (туманность + накладка)
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        W, H = self.width(), self.height()
        if getattr(self, "_clip_key", None) != (W, H):
            path = QPainterPath()
            path.addRoundedRect(QRectF(0, 0, W, H), 16, 16)
            self._clip_rgn = QRegion(path.toFillPolygon().toPolygon())
            self._clip_key = (W, H)
        glass = _ph_backdrop(self, p)                  # Phantom: под туманностью — фон за панелью, не чёрное
        if not glass:                                  # (во всю площадь, без скругления — иначе чёрные уголки)
            p.setClipRegion(self._clip_rgn)
            p.fillRect(self.rect(), QColor(0, 0, 0))
        if self._img is not None:
            if glass:
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
            p.drawImage(QRectF(0, 0, W, H), self._img)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        self._paint_decor(p, W, H)
        p.end()


class WaveHero(QWidget):
    """Баннер «▶ Моя волна» на главной: живая туманность (C++), по щелчку — запустить волну.
    Туманность обновляется максимум 60 раз/с и только пока баннер виден."""
    clicked = pyqtSignal()

    def __init__(self, engine=None, parent=None, height=250):
        super().__init__(parent)
        self.engine = engine
        self.setFixedHeight(height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # непрозрачный: каждый кадр туманности не тянет перерисовку окна, фона и подсветки под баннером
        # (углы закрашиваются цветом панели). Раньше это было до 144 перерисовок всего окна в секунду.
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAutoFillBackground(False)
        self.corner = QColor(18, 18, 18)
        self.neb = NebulaField()
        self.neb.set_scheme(scheme_for("my"), True)
        _LIVE.add(self)
        for _ in range(40):
            self.neb._advance(0.0, 0.05)
        self.sub = "Всё, что вы любите, и немного нового"
        self._img = None
        self._title = None
        self._hover = 0.0
        self._last = time.monotonic()
        self._timer = FrameTimer(self)
        self._timer.setInterval(33)                            # баннер: 30 кадров/с хватает медленной туманности
        self._timer.timeout.connect(self._tick)
        self._worker = _GlowWorker(self.neb)
        self._worker.start()
        self.destroyed.connect(self._worker.stop)
        self._acc_dt=0.
        self._gl = None                                        # туманность баннера на видеокарте
        self._gl_state = "untried"
        self._gl_ov_k = None

    def set_scheme(self, cols):
        self._worker.set_scheme(cols)
        if self._gl_state == "on":
            with self._worker.lock:
                self.neb.set_scheme(cols)

    def _gl_try(self):
        if self._gl_state != "untried":
            return
        self._gl_state = "off"
        if not gpu_enabled():
            return
        try:
            import native_ui
            gl = native_ui.NebulaGL()
            gl.widget.setParent(self)
            gl.widget.setGeometry(self.rect())
            gl.widget.show()
            self._gl, self._gl_state = gl, "trying"
            QTimer.singleShot(0, self._gl_check)
        except Exception as e:                             # noqa: BLE001
            print("[wave hero] gpu:", e)

    def _gl_check(self):
        gl = self._gl
        if gl is None:
            return
        if gl.ok():
            self._gl_state = "on"
            self._gl_mask()
            self._timer.setInterval(16)                    # на GPU кадр почти бесплатный — в ритме экрана
            return
        self._gl_state = "off"
        gl.widget.hide()
        gl.widget.deleteLater()
        self._gl = None

    def _gl_mask(self):
        if _phantom():
            self._gl.widget.clearMask()
            return
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 22, 22)
        self._gl.widget.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def _gl_overlay(self):
        W, H = self.width(), self.height()
        dpr = self.devicePixelRatioF()
        key = (W, H, dpr, bool(self._hover), _tr("Моя волна"), _tr(self.sub), _backdrop_key(self))
        if key == self._gl_ov_k:
            return
        self._gl_ov_k = key
        pm = QPixmap(max(1, int(W * dpr)), max(1, int(H * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        bd = _screen_backdrop(self, W, H, dpr)
        if bd is not None:
            q.drawImage(0, 0, bd)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_text(q, W, H)
        q.end()
        self._gl.overlay(pm)

    def showEvent(self, e):
        super().showEvent(e)
        self._gl_try()
        self._last = time.monotonic()
        self._timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()
        release_gl_later(self)

    def enterEvent(self, e):
        self._hover = 1.0
        self.update()

    def leaveEvent(self, e):
        self._hover = 0.0
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._title = None
        if self._gl is not None:
            self._gl.widget.setGeometry(self.rect())
            if self._gl_state == "on":
                self._gl_mask()

    def _tick(self):
        now = time.monotonic()
        dt = animation_delta(now - self._last)
        self._last = now
        lvl = 0.0
        try:
            if self.engine is not None and self.engine.is_playing():
                s = self.engine.get_visual_samples(512)
                if s is not None and len(s):
                    a = np.asarray(s, dtype=np.float32)
                    lvl = min(1.0, float(np.sqrt(np.mean(a * a))) * 4.0)
        except Exception:                                  # noqa: BLE001
            lvl = 0.0
        W, H = max(8, self.width()), max(8, self.height())
        if self._gl_state == "on":                         # кадр считает видеокарта
            self._gl_overlay()
            with self._worker.lock:
                P = self.neb.params(W, H, W * .5, H * .52, max(W * .26, H * 1.05), lvl, dt, 0,
                                    self.devicePixelRatioF())
            self._gl.params(P)
            return
        ready=self._worker.take()
        if ready is not None:
            self._img=ready
            self.update()
        self._acc_dt=min(.2,self._acc_dt+dt)
        target = __import__("frameclock").clock().rate
        step = 1 / min(HERO_MAX_FPS, max(24, target))
        if self._acc_dt >= step and self._worker.submit(
                max(8, int(W * NEBULA_RENDER_SCALE)), max(8, int(H * NEBULA_RENDER_SCALE)),
                W * NEBULA_RENDER_SCALE * .5, H * NEBULA_RENDER_SCALE * .52,
                max(W * NEBULA_RENDER_SCALE * .26, H * NEBULA_RENDER_SCALE * 1.05),
                lvl, self._acc_dt, 0, self.devicePixelRatioF()):
            self._acc_dt=0.

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        glass = _ph_backdrop(self, p)                          # Phantom: углы и фон — то, что за панелью
        if not glass:
            p.fillRect(self.rect(), self.corner)               # непрозрачный виджет: углы — цветом панели
        if self._gl_state == "on":                             # туманность и надписи — на GPU-виджете
            p.end()
            return
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, W, H), 22, 22)
        p.setClipPath(path)
        if not glass:
            p.fillRect(self.rect(), QColor(0, 0, 0))
        if self._img is not None:
            if glass:
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
            p.drawImage(QRectF(0, 0, W, H), self._img)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        dpr = self.devicePixelRatioF()
        key = (W, H, dpr, bool(self._hover), _tr("Моя волна"), _tr(self.sub))
        if key != self.__dict__.get("_ov_k"):              # надписи не меняются от кадра к кадру туманности
            ov = QPixmap(max(1, int(W * dpr)), max(1, int(H * dpr)))
            ov.setDevicePixelRatio(dpr)
            ov.fill(Qt.GlobalColor.transparent)
            q = QPainter(ov)
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._paint_text(q, W, H)
            q.end()
            self._ov, self._ov_k = ov, key
        p.drawPixmap(0, 0, self._ov)
        p.end()

    def _paint_text(self, p, W, H):
        if self._title is None:
            f = _font(max(30, min(58, H * 0.23)), QFont.Weight.Bold)
            fm = QFontMetrics(f)
            self._title = (f, fm)
        f, fm = self._title
        txt = _tr("Моя волна")
        gs = f.pixelSize() * 0.62
        tw = fm.horizontalAdvance(txt) + gs + f.pixelSize() * 0.28
        x0, cy = (W - tw) / 2, H * 0.44
        p.setPen(Qt.PenStyle.NoPen)
        for col, off in ((QColor(0, 0, 0, 70), 2.0), (QColor(255, 255, 255, 240), 0.0)):
            p.setBrush(col)
            tri = QPainterPath()
            tri.moveTo(x0 + gs * 0.08, cy - gs * 0.55 + off)
            tri.lineTo(x0 + gs * 0.98, cy + off)
            tri.lineTo(x0 + gs * 0.08, cy + gs * 0.55 + off)
            tri.closeSubpath()
            p.drawPath(tri)
            p.setFont(f)
            p.setPen(col)
            p.drawText(QRectF(x0 + gs + f.pixelSize() * 0.28, cy - H * 0.2 + off, tw, H * 0.4),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, txt)
            p.setPen(Qt.PenStyle.NoPen)
        pf = _font(13, QFont.Weight.Bold)
        p.setFont(pf)
        sub = _tr(self.sub)
        pw = QFontMetrics(pf).horizontalAdvance(sub) + 36
        pr = QRectF((W - pw) / 2, H * 0.62, pw, 34)
        p.setBrush(QColor(0, 0, 0, 92 if self._hover else 70))
        p.drawRoundedRect(pr, 17, 17)
        p.setPen(QColor(255, 255, 255, 235))
        p.drawText(pr, Qt.AlignmentFlag.AlignCenter, sub)
