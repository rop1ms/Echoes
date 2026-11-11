# blur_fx.py
"""
Размытие картинок для фонов, стекла и свечения — плавное, без «каши из пикселей».

Раньше почти везде размытие делалось так: обложка → 8×8 (или 10×10, 16×16) → растянуть обратно
сглаживанием. Билинейное растяжение такой крошечной картинки даёт ромбы, кресты и ступеньки —
каждый исходный пиксель виден пятном с жёсткими краями. Здесь — настоящее гауссово размытие:

  * картинка уменьшается ровно настолько, чтобы радиус размытия в ней остался ~3 пикселя
    (быстро и без потери качества — мелкие детали всё равно уйдут в размытие);
  * в маленькой копии — гаусс (три прохода «коробкой» по Куцкиру ≈ точный гаусс; при малом
    радиусе — точное ядро), края продолжаются, а не темнеют;
  * обратно — сглаженное растяжение: у уже размытой картинки оно незаметно.

Считается в numpy (большие операции отпускают GIL — звук не заикается) и не зависит от Qt
GUI-потока: функции можно звать из рабочих потоков, отдавая наружу QImage.
"""
from __future__ import annotations

import math

import numpy as np
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap

_ARGB = QImage.Format.Format_ARGB32_Premultiplied
_SMOOTH = Qt.TransformationMode.SmoothTransformation
_IGNORE = Qt.AspectRatioMode.IgnoreAspectRatio
WORK_SIGMA = 3.0            # радиус размытия в уменьшенной копии (пикселей)

_NF = None


def _native() -> bool:
    global _NF
    if _NF is None:
        try:
            import native_fx
            _NF = native_fx if native_fx.available() else False
        except Exception:                                  # noqa: BLE001
            _NF = False
    return bool(_NF)


# ------------------------------------------------------------------ #
#  QImage ↔ numpy                                                     #
# ------------------------------------------------------------------ #

def to_array(img: QImage) -> np.ndarray:
    """QImage → float32 (h, w, 4) с премультиплицированной альфой (порядок BGRA)."""
    img = img.convertToFormat(_ARGB)
    w, h = img.width(), img.height()
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    return np.frombuffer(ptr, np.uint8).reshape(h, img.bytesPerLine() // 4, 4)[:, :w, :].astype(np.float32)


def from_array(a: np.ndarray, dither: bool = False) -> QImage:
    if dither:
        # ±0.5 уровня шума против полос на тёмных плавных переходах
        rng = np.random.default_rng(7)
        a = a + rng.random(a.shape[:2] + (1,), dtype=np.float32) - 0.5
    out = np.ascontiguousarray(np.clip(a + 0.5, 0, 255).astype(np.uint8))
    h, w = out.shape[:2]
    a8 = out[..., 3:4]
    np.minimum(out[..., :3], a8, out=out[..., :3])         # премультипликация: цвет ≤ альфы
    return QImage(out.data, w, h, w * 4, _ARGB).copy()


# ------------------------------------------------------------------ #
#  Гаусс в numpy                                                      #
# ------------------------------------------------------------------ #

def _boxes_for_gauss(sigma: float, n: int = 3) -> list[int]:
    """Ширины n коробок, чьё последовательное применение ≈ гаусс sigma (Kutskir)."""
    w_ideal = math.sqrt(12.0 * sigma * sigma / n + 1)
    wl = int(math.floor(w_ideal))
    if wl % 2 == 0:
        wl -= 1
    wu = wl + 2
    m_ideal = (12 * sigma * sigma - n * wl * wl - 4 * n * wl - 3 * n) / (-4 * wl - 4)
    m = round(m_ideal)
    return [wl if i < m else wu for i in range(n)]


def _box(a: np.ndarray, r: int, axis: int) -> np.ndarray:
    if r < 1:
        return a
    n = a.shape[axis]
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r + 1, r)
    c = np.cumsum(np.pad(a, pad, mode="edge"), axis=axis, dtype=np.float32)
    hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return (hi - lo) * (1.0 / (2 * r + 1))


def _taps(a: np.ndarray, sigma: float, axis: int) -> np.ndarray:
    r = max(1, int(math.ceil(sigma * 3)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2).astype(np.float32)
    k /= k.sum()
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r, r)
    p = np.pad(a, pad, mode="edge")
    n = a.shape[axis]
    out = np.zeros_like(a)
    for i, w in enumerate(k):
        out += w * np.take(p, np.arange(i, i + n), axis=axis)
    return out


def gauss_array(a: np.ndarray, sigma: float) -> np.ndarray:
    """Гауссово размытие массива (h, w[, c]) по двум осям; края продолжаются."""
    if sigma <= 0.3:
        return a
    if sigma < 2.0:
        return _taps(_taps(a, sigma, 1), sigma, 0)
    for wdt in _boxes_for_gauss(sigma, 3):
        r = (wdt - 1) // 2
        a = _box(_box(a, r, 1), r, 0)
    return a


# ------------------------------------------------------------------ #
#  Картинки                                                           #
# ------------------------------------------------------------------ #

def blur_image(img: QImage, sigma: float, size: QSize | tuple | None = None, dither: bool = False,
               post=None) -> QImage:
    """Гауссово размытие QImage с радиусом sigma (в пикселях результата).
    size — размер результата (по умолчанию как у исходной). post(QImage) → QImage — обработка размытой
    РАБОЧЕЙ копии до растяжения в размер результата (она в десятки раз меньше — цветокоррекция почти даром)."""
    if img is None or img.isNull():
        return QImage()
    if size is None:
        ow, oh = img.width(), img.height()
    elif isinstance(size, QSize):
        ow, oh = size.width(), size.height()
    else:
        ow, oh = int(size[0]), int(size[1])
    ow, oh = max(1, ow), max(1, oh)
    if sigma <= 0.3:
        out = img if (img.width(), img.height()) == (ow, oh) else img.scaled(ow, oh, _IGNORE, _SMOOTH)
        return out.convertToFormat(_ARGB)
    # уменьшаем так, чтобы в рабочей копии радиус был ~WORK_SIGMA пикселей
    f = max(1.0, sigma / WORK_SIGMA)
    sw, sh = max(4, int(round(ow / f))), max(4, int(round(oh / f)))
    sw, sh = min(sw, max(4, img.width())), min(sh, max(4, img.height()))
    work = img.convertToFormat(_ARGB)
    if (work.width(), work.height()) != (sw, sh):
        # большое уменьшение — в два шага (сглаженное уменьшение Qt усредняет площадь)
        if work.width() > sw * 4:
            work = work.scaled(sw * 2, sh * 2, _IGNORE, _SMOOTH)
        work = work.scaled(sw, sh, _IGNORE, _SMOOTH)
    s_small = sigma * sw / ow
    if _native():
        # C++: гаусс прямо в памяти картинки, в несколько потоков, без GIL
        small = work.copy() if work is img else work
        small = small.convertToFormat(_ARGB)
        _NF.blur_qimage(small, s_small, dither=dither and (sw, sh) == (ow, oh))
    else:
        a = gauss_array(to_array(work), s_small)
        small = from_array(a, dither=dither and (sw, sh) == (ow, oh))
    if post is not None:
        small = post(small)
    if (sw, sh) == (ow, oh):
        return small
    return small.scaled(ow, oh, _IGNORE, _SMOOTH)


def cover_crop(img: QImage, w: int, h: int, max_side: int = 0) -> QImage:
    """Вписать «с обрезкой» (cover) в пропорции w:h; max_side — ограничить размер результата."""
    if img.isNull():
        return img
    iw, ih = img.width(), img.height()
    k = max(w / iw, h / ih)
    cw, ch = min(iw, int(math.ceil(w / k))), min(ih, int(math.ceil(h / k)))
    crop = img.copy((iw - cw) // 2, (ih - ch) // 2, cw, ch)
    if max_side and max(cw, ch) > max_side:
        s = max_side / max(cw, ch)
        crop = crop.scaled(max(1, int(cw * s)), max(1, int(ch * s)), _IGNORE, _SMOOTH)
    return crop


def blurred_cover(src, w: int, h: int, sigma: float, dim: float = 0.0, sat: float = 1.0,
                  tint: QColor | None = None) -> QImage:
    """Размытая обложка ровно w×h (cover): src — путь или QImage/QPixmap. sigma — в пикселях результата.
    dim 0..1 — затемнение, sat — насыщенность, tint — цвет поверх (с его альфой)."""
    w, h = max(1, int(w)), max(1, int(h))
    if isinstance(src, QPixmap):
        img = src.toImage()
    elif isinstance(src, QImage):
        img = src
    elif src:
        from img_load import read_image
        # декодировать сразу уменьшенной: детали всё равно размоются
        need = max(64, int(max(w, h) / max(1.0, sigma / WORK_SIGMA)) * 3)
        img = read_image(str(src), min(2048, need))
    else:
        img = QImage()
    if img.isNull():
        out = QImage(w, h, _ARGB)
        out.fill(QColor(12, 12, 16))
        return out
    f = max(1.0, sigma / WORK_SIGMA)
    crop = cover_crop(img, w, h, max_side=int(max(w, h) / f * 2) + 8)
    # насыщенность — на рабочей копии: на картинке во весь экран это были 60–120 мс numpy в потоке
    # интерфейса (открытие страницы текста, смена трека на ней); после сильного размытия разницы не видно
    out = blur_image(crop, sigma, (w, h),
                     post=(lambda im: saturate(im, sat)) if abs(sat - 1.0) > 0.02 else None)
    if dim > 0.003 or tint is not None:
        p = QPainter(out)
        if dim > 0.003:
            p.fillRect(out.rect(), QColor(0, 0, 0, int(255 * min(1.0, dim))))
        if tint is not None:
            p.fillRect(out.rect(), tint)
        p.end()
    return out


def saturate(img: QImage, s: float) -> QImage:
    if abs(s - 1.0) < 0.02 or img.isNull():
        return img
    a = to_array(img)
    rgb = a[..., :3]
    gray = rgb @ np.array([0.114, 0.587, 0.299], np.float32)
    a[..., :3] = gray[..., None] + (rgb - gray[..., None]) * s
    np.clip(a[..., :3], 0, a[..., 3:4], out=a[..., :3])
    return from_array(a)


def glow(silhouette: QImage, sigma: float, strength: float = 1.0) -> QImage:
    """Мягкое свечение силуэта (например, текста): гаусс по альфе, без ступенек."""
    if silhouette.isNull():
        return silhouette
    out = blur_image(silhouette, sigma)
    if abs(strength - 1.0) > 0.01:
        a = to_array(out) * float(strength)
        out = from_array(np.minimum(a, 255.0))
    return out


def blurred_pixmap(src, w: int, h: int, sigma: float, dpr: float = 1.0, **kw) -> QPixmap:
    """То же, что blurred_cover, но QPixmap с учётом плотности пикселей (только в GUI-потоке)."""
    img = blurred_cover(src, int(w * dpr), int(h * dpr), sigma * dpr, **kw)
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(dpr)
    return pm
