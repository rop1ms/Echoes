# ya_decor.py
"""
Живое оформление Echoes Music — всё, что делает тему «живой», с выключателем на каждую вещь
(Настройки → «Живое оформление»). Хранится в settings["ya_decor"].

Цвет и фон
  * акцент из обложки — кнопка Play, полоска прогресса, логотип и волна плавно (~1 с) перекрашиваются
    в главный цвет обложки играющего трека;
  * аура окна — цветные пятна обложки медленно плавают за стеклянными панелями (видны в щелях между
    ними и в углах), на паузе замирают; пульс — светлеют на сильных долях баса;
  * время суток — утром тёплый свет, днём нейтрально, вечером закат, ночью тёмно-синий;
  * «погода» из обложки — холодная обложка: капли на стекле, тёплая: мягкие лучи;
  * параллакс — пятна чуть смещаются за курсором; своя картинка фона окна (размыта и затемнена).
Стекло
  * режимы: матовое (как было), прозрачное (видно фон окна), чёрное OLED, цветное (тон обложки);
  * зерно 2–3 % и светлый кант по верхнему краю, ярче под курсором.
Плеер
  * волна вместо линии прогресса (силуэт громкости трека, считается в фоне один раз);
  * пластинка выглядывает из-за обложки и крутится, на паузе — останавливается и уезжает;
  * строка текста песни под названием; кнопка Play в цвет обложки со свечением-эквалайзером.
Страницы и анимации
  * шапки плейлистов/альбомов/исполнителей в цвет обложки (растворяются при прокрутке),
    липкий заголовок у исполнителя, свечение карточек в цвет обложки, миксы из обложек треков;
  * перелёт обложки с карточки на страницу альбома, каскад появления карточек, пружинящие кнопки,
    солнце ECHOES вместо «загрузки», пустые страницы с живым солнцем.
Мелочи
  * прогресс трека на значке в панели задач и кнопки ◀ ⏯ ▶ в превью окна (win_taskbar);
  * тихие щелчки при смене вкладок (по умолчанию выключено); 10 кликов по солнцу — дождь из обложек.

Всё дорогое считается один раз (при смене трека/размера) и кэшируется; анимация фона перерисовывает
только щели между панелями, а не весь интерфейс — прокрутка и переходы не тормозят.
"""
from __future__ import annotations

import data_home
import threading
import os
import json
import math
import random
import time
import weakref
from pathlib import Path

from PyQt6.QtCore import (QEasingCurve, QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer,
                          QVariantAnimation, pyqtSignal)
from PyQt6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QImage, QLinearGradient, QPainter, QPainterPath,
                         QPen, QPixmap, QRadialGradient, QRegion)
from PyQt6.QtWidgets import QAbstractButton, QApplication, QLabel, QWidget

DEFAULTS = {                                                   # по умолчанию всё выключено — ECHOES как обычно
    "cover_accent": False, "aura": False, "pulse": False, "daytime": False, "weather": False, "parallax": False,
    "glass": "matte", "grain": False, "rim": False,
    "wave_bar": False, "vinyl": False, "mini_lyrics": False, "play_glow": False,
    "headers": False, "sticky": False, "card_glow": False, "mix_covers": False, "empty_art": False,
    "shared": False, "cascade": False, "spring": False, "sun_loader": False,
    "bg_image": "", "bg_dim": 60,
    "taskbar": False, "thumb_buttons": False, "ui_sounds": False, "egg": False,
    "net_aura": False, "now_eq": False,
    "real_weather": False, "weather_city": "",                # погода за окном (ya_weather)
}
GLASS_MODES = (("matte", "Матовое"), ("clear", "Прозрачное"), ("oled", "Чёрное OLED"), ("tint", "Цветное"))

CURRENT: "Decor | None" = None                                # одна оболочка Echoes Music за раз
_CFG = dict(DEFAULTS)


def cfg() -> dict:
    return _CFG


def on(key) -> bool:
    return bool(_CFG.get(key))


def load_cfg(settings) -> dict:
    d = dict(DEFAULTS)
    if settings is not None and not settings.get("ya_decor_plain_v1"):
        settings["ya_decor"] = {}                              # один раз: всё живое оформление — выключено
        settings["ya_decor_plain_v1"] = True
    raw = (settings or {}).get("ya_decor")
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k in DEFAULTS:
                d[k] = v
    if d["glass"] not in dict(GLASS_MODES):
        d["glass"] = "matte"
    try:
        d["bg_dim"] = max(0, min(90, int(d["bg_dim"])))
    except (TypeError, ValueError):
        d["bg_dim"] = 60
    _CFG.clear()
    _CFG.update(d)
    return d


def _motion() -> float:
    try:
        import motion
        return float(motion.strength())
    except Exception:                                          # noqa: BLE001
        return 1.0


def _Y():
    import yamusic_theme as Y
    return Y


_BASE = {}


def _phantom() -> bool:
    try:
        import ya_skin
        return bool(ya_skin.PHANTOM_ON)
    except Exception:                                          # noqa: BLE001
        return False


def base_accent() -> QColor:
    y = _Y().YELLOW
    c = _BASE.get(y)
    if c is None:
        _BASE.clear()
        c = _BASE[y] = QColor(y)
    return QColor(c)


def accent() -> QColor:
    """Текущий живой акцент (цвет обложки) — или акцент темы."""
    if _phantom():                                             # вид Phantom — монохром, без цвета обложки
        return base_accent()
    d = CURRENT
    if d is not None and on("cover_accent") and d.accent is not None:
        return QColor(d.accent)
    return base_accent()


def accent2() -> QColor:
    c = accent()
    h, s, v, _ = c.getHsvF()
    return QColor.fromHsvF((h + 0.06) % 1.0 if h >= 0 else 0.1, min(1.0, s * 1.05), max(0.0, v * 0.86))


def on_accent(c: QColor) -> QColor:
    lum = 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()
    return QColor(0, 0, 0) if lum > 0.55 else QColor(255, 255, 255)


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t), int(a.alpha() + (b.alpha() - a.alpha()) * t))


# ══════════════════════════ цвета обложки ══════════════════════════ #

_PAL: dict = {}
_PAL_DISK: dict | None = None       # «путь|время|размер» → [[#rrggbb…], температура] — живёт между запусками
_PAL_DIRTY = False
_PAL_LOCK = threading.Lock()
PAL_DISK_MAX = 6000


def _pal_file() -> Path:
    return data_home.root() / "cover_palettes.json"


def _pal_disk() -> dict:
    global _PAL_DISK
    if _PAL_DISK is None:
        try:
            d = json.loads(_pal_file().read_text(encoding="utf-8"))
            _PAL_DISK = d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            _PAL_DISK = {}
    return _PAL_DISK


def _pal_key(path: str) -> str:
    try:
        st = os.stat(path)
        return f"{path}|{st.st_mtime_ns}|{st.st_size}"
    except OSError:
        return ""


def _pal_save():
    global _PAL_DIRTY
    with _PAL_LOCK:
        if not _PAL_DIRTY or _PAL_DISK is None:
            return
        _PAL_DIRTY = False
        data = dict(_PAL_DISK)
    try:
        f = _pal_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(f)
    except OSError as e:
        print("[decor] palettes:", e)


def _pal_put(dk: str, out: list):
    global _PAL_DIRTY
    disk = _pal_disk()
    if len(disk) >= PAL_DISK_MAX:
        for k in list(disk)[:PAL_DISK_MAX // 4]:
            disk.pop(k, None)
    disk[dk] = [[c.name() for c in out[0]], round(float(out[1]), 4)]
    first = not _PAL_DIRTY
    _PAL_DIRTY = True
    if first:                                                  # записать разом, через несколько секунд, не в потоке окна
        t = threading.Timer(6.0, _pal_save)
        t.daemon = True
        t.start()


def palette(path: str) -> list:
    """3–4 цвета обложки (насыщенные первыми) + «температура» −1 (холодная) … +1 (тёплая)."""
    key = path or ""
    hit = _PAL.get(key)
    if hit is not None:
        return hit
    dk = _pal_key(path) if path else ""
    if dk:                                                     # уже считали в прошлый запуск — файл не читаем
        ent = _pal_disk().get(dk)
        try:
            if ent and len(ent[0]) >= 3:
                out = [[QColor(c) for c in ent[0]], float(ent[1])]
                if len(_PAL) > 400:
                    _PAL.clear()
                _PAL[key] = out
                return out
        except (TypeError, ValueError, IndexError):
            pass
    cols, temp = [], 0.0
    img = QImage()
    if path and Path(path).exists():
        try:
            from img_load import read_image
            img = read_image(path, 64)
        except Exception:                                      # noqa: BLE001
            img = QImage(path)
    if not img.isNull():
        img = img.scaled(16, 16, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        px = []
        warm = cold = 0.0
        for y in range(img.height()):
            for x in range(img.width()):
                c = QColor(img.pixel(x, y))
                h, s, v, _ = c.getHsvF()
                w = s * v
                px.append((w, h, s, v))
                if h >= 0 and w > 0.12:
                    if h < 0.17 or h > 0.92:
                        warm += w
                    elif 0.45 < h < 0.75:
                        cold += w
        tot = warm + cold
        temp = 0.0 if tot < 0.5 else (warm - cold) / tot
        px.sort(reverse=True)
        hues = []
        for w, h, s, v in px:
            if h < 0 or w < 0.08:
                continue
            if all(min(abs(h - q), 1 - abs(h - q)) > 0.08 for q in hues):
                hues.append(h)
                cols.append(QColor.fromHsvF(h, min(1.0, max(0.55, s * 1.15)), max(0.78, min(1.0, v * 1.15))))
            if len(cols) >= 3:
                break
        if not cols:                                           # ч/б обложка — серебро
            v = sum(p[3] for p in px) / max(1, len(px))
            cols = [QColor.fromHsvF(0, 0, max(0.75, v)), QColor("#9a9aa2")]
    if not cols:
        cols = [base_accent(), QColor("#ff4fa3")]
    while len(cols) < 3:
        h, s, v, _ = cols[-1].getHsvF()
        cols.append(QColor.fromHsvF(((h if h >= 0 else 0.13) + 0.33) % 1.0, max(0.5, s), max(0.7, v)))
    out = [cols, temp]
    if len(_PAL) > 400:
        _PAL.clear()
    _PAL[key] = out
    if dk and not img.isNull():                                # запасные цвета (нет картинки) зависят от темы — не храним
        _pal_put(dk, out)
    return out


def vivid(path: str) -> QColor | None:
    """Главный цвет обложки для акцента — яркий и читаемый на тёмном; None — обложки нет."""
    if not path or not Path(path).exists():
        return None
    c = palette(path)[0][0]
    h, s, v, _ = c.getHsvF()
    if s < 0.18:
        return None                                            # серая обложка — остаётся акцент темы
    return QColor.fromHsvF(h, min(1.0, max(0.6, s)), max(0.88, v))


# ══════════════════════════ время суток ══════════════════════════ #

def daytime_tint(hour: float | None = None) -> tuple[QColor, QColor]:
    """(цвет сверху, цвет снизу) для подсветки окна по времени суток."""
    if hour is None:
        lt = time.localtime()
        hour = lt.tm_hour + lt.tm_min / 60.0
    if 5 <= hour < 10:                                          # утро — тёплое, светлее
        return QColor(255, 196, 120, 46), QColor(255, 150, 90, 14)
    if 10 <= hour < 17:                                         # день — нейтрально
        return QColor(255, 255, 255, 14), QColor(200, 220, 255, 6)
    if 17 <= hour < 22:                                         # вечер — закат
        return QColor(255, 120, 80, 34), QColor(150, 70, 200, 30)
    return QColor(40, 70, 170, 44), QColor(10, 20, 70, 50)      # ночь — почти чёрный с синим


# ══════════════════════════ зерно / погода / стекло ══════════════════════════ #

_GRAIN = None


def grain_tile() -> QPixmap:
    global _GRAIN
    if _GRAIN is None:
        rng = random.Random(11)
        img = QImage(128, 128, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        for _ in range(2600):
            x, y = rng.randrange(128), rng.randrange(128)
            a = rng.randint(4, 11)
            v = 255 if rng.random() < 0.5 else 0
            img.setPixelColor(x, y, QColor(v, v, v, a))
        _GRAIN = QPixmap.fromImage(img)
    return _GRAIN


def _weather_layer(p: QPainter, w: int, h: int, kind: str, col: QColor):
    """Капли на стекле (холодная обложка) или мягкие лучи (тёплая) — запекаются в поверхность."""
    if kind == "rain":
        rng = random.Random(w * 31 + h)
        n = max(12, min(70, w * h // 16000))
        for _ in range(n):
            x = rng.random() * w
            y = (rng.random() ** 1.6) * h * 0.85                 # больше капель вверху
            r = 1.2 + rng.random() ** 2 * 3.4
            g = QRadialGradient(QPointF(x - r * 0.3, y - r * 0.35), r * 1.4)
            g.setColorAt(0, QColor(255, 255, 255, 34))
            g.setColorAt(0.55, QColor(col.red(), col.green(), col.blue(), 16))
            g.setColorAt(1, QColor(0, 0, 0, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawEllipse(QPointF(x, y), r, r * 1.15)
            p.setPen(QPen(QColor(0, 0, 0, 40), 0.8))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRectF(x - r, y - r * 1.15, r * 2, r * 2.3), 200 * 16, 140 * 16)
            if r > 3 and rng.random() < 0.4:                    # след стёкшей капли
                tr = QLinearGradient(x, y, x, y + r * 9)
                tr.setColorAt(0, QColor(255, 255, 255, 14))
                tr.setColorAt(1, QColor(255, 255, 255, 0))
                p.setPen(QPen(QBrush(tr), 1.0))
                p.drawLine(QPointF(x, y + r), QPointF(x + rng.uniform(-1, 1), y + r * 9))
    elif kind == "sun":
        o = QPointF(-w * 0.04, -h * 0.12)
        for i, (ang, wid, a) in enumerate(((22, 0.06, 16), (31, 0.035, 12), (40, 0.08, 10), (52, 0.04, 8))):
            p.save()
            p.translate(o)
            p.rotate(ang)
            L = math.hypot(w, h) * 1.1
            g = QLinearGradient(0, 0, L, 0)
            c = QColor(col)
            c.setAlpha(a)
            g.setColorAt(0, c)
            c.setAlpha(0)
            g.setColorAt(0.75, c)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            ww = L * wid
            p.drawPolygon(QPointF(0, -ww * 0.1), QPointF(L, -ww), QPointF(L, ww), QPointF(0, ww * 0.1))
            p.restore()
        g = QRadialGradient(o, max(w, h) * 0.45)
        c = QColor(col)
        c.setAlpha(26)
        g.setColorAt(0, c)
        c.setAlpha(0)
        g.setColorAt(1, c)
        p.fillRect(QRectF(0, 0, w, h), g)


def decorate_surface(frame, base: QPixmap) -> QPixmap:
    """Стекло панели + режим, тон, погода, зерно. Кэш на панели: пересобирается при смене размера/трека."""
    d = CURRENT
    mode = _CFG["glass"]
    content = frame.objectName() == "YaContent"
    weather = (d.weather if d is not None and on("weather") and content and mode in ("matte", "tint") else "")
    tint = accent().name() if mode == "tint" else ""
    key = (base.cacheKey(), base.size(), mode, weather, tint, on("grain"),
           (d.pal_key if d is not None and weather else ""))
    hit = frame.__dict__.get("_deco_pm")
    if hit is not None and hit[0] == key:
        return hit[1]
    w, h = base.width(), base.height()
    pm = QPixmap(base.size())
    pm.setDevicePixelRatio(base.devicePixelRatio())
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    from ya_skin import interface_radius
    rad = interface_radius()
    shape = QPainterPath()
    shape.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), rad, rad)
    if mode == "oled":
        p.fillPath(shape, QColor(0, 0, 0))
        p.setPen(QPen(QColor(255, 255, 255, 22), 1))
        p.drawPath(shape)
    else:
        if mode == "clear":
            p.setOpacity(0.58)
        p.drawPixmap(0, 0, base)
        p.setOpacity(1.0)
        p.setClipPath(shape)
        if mode == "tint":
            c = accent()
            g = QLinearGradient(0, 0, w * 0.6, h)
            c1 = QColor(c); c1.setAlpha(34)
            c2 = QColor(c); c2.setAlpha(8)
            g.setColorAt(0, c1)
            g.setColorAt(1, c2)
            p.fillPath(shape, g)
        if weather and d is not None:
            _weather_layer(p, w, h, weather, d.pal[0] if d.pal else accent())
        if on("grain"):
            p.setOpacity(0.9)
            p.drawTiledPixmap(QRectF(0, 0, w, h), grain_tile())
            p.setOpacity(1.0)
    p.end()
    frame._deco_pm = (key, pm)
    return pm


def paint_frame(frame, p: QPainter, surface: QPixmap, area=None):
    """AmbientFrame.paintEvent: стекло в выбранном режиме + светлый кант по верхнему краю.
    area — перерисовываемый прямоугольник: ниже канта кант не трогаем."""
    if getattr(frame, "_glass_stretch", False) and _CFG["glass"] != "oled":
        p.drawPixmap(0, 0, surface)                            # окно тянут — растянутое стекло, без украшений
        return
    p.drawPixmap(0, 0, decorate_surface(frame, surface))
    if not on("rim") or CURRENT is None or (area is not None and area.top() > 3):
        return
    w = frame.width()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    from ya_skin import interface_radius
    radius = interface_radius()
    clip.addRoundedRect(QRectF(0.5, 0.5, w - 1, frame.height() - 1), radius, radius)
    p.setClipPath(clip)
    mx = CURRENT.mouse_in(frame)
    g = QLinearGradient(0, 0, w, 0)
    base_a = 26
    if mx is None:
        g.setColorAt(0, QColor(255, 255, 255, 0))
        g.setColorAt(0.5, QColor(255, 255, 255, base_a))
        g.setColorAt(1, QColor(255, 255, 255, 0))
    else:
        f = max(0.0, min(1.0, mx / max(1, w)))
        g.setColorAt(0, QColor(255, 255, 255, 8))
        g.setColorAt(max(0.0, f - 0.18), QColor(255, 255, 255, base_a))
        g.setColorAt(f, QColor(255, 255, 255, 120))
        g.setColorAt(min(1.0, f + 0.18), QColor(255, 255, 255, base_a))
        g.setColorAt(1, QColor(255, 255, 255, 8))
    p.setPen(QPen(QBrush(g), 1.2))
    p.drawLine(QPointF(14, 1.2), QPointF(w - 14, 1.2))
    p.setClipping(False)


# ══════════════════════════ волна трека для прогресса ══════════════════════════ #

_PEAKS: dict = {}
_PEAK_DIR = data_home.root() / "wave_cache"


def _peak_file(path: str) -> Path:
    import hashlib
    try:
        st = Path(path).stat()
        sig = f"{path}|{st.st_size}|{int(st.st_mtime)}"
    except OSError:
        sig = path
    return _PEAK_DIR / (hashlib.sha1(sig.encode("utf-8", "ignore")).hexdigest()[:20] + ".json")


def compute_peaks(path: str, n: int = 220) -> list | None:
    """Силуэт громкости файла: n значений 0..1 (ffmpeg, 2 кГц моно — секунда на трек, один раз)."""
    import json
    f = _peak_file(path)
    try:
        v = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(v, list) and len(v) == n:
            return v
    except (OSError, ValueError):
        pass
    try:
        import numpy as np
        from daw_dsp import decode
        x = decode(path, sr=2000, channels=1, timeout=60)[:, 0]
    except Exception:                                          # noqa: BLE001
        return None
    if x.size < n * 4:
        return None
    import numpy as np
    m = x.size // n
    blk = np.abs(x[: m * n]).reshape(n, m)
    rms = np.sqrt(np.mean(np.square(blk), axis=1))
    pk = blk.max(axis=1)
    v = 0.6 * rms / max(1e-6, float(np.percentile(rms, 97))) + 0.4 * pk / max(1e-6, float(np.percentile(pk, 97)))
    v = np.clip(v, 0.0, 1.0) ** 0.85
    out = [round(float(a), 3) for a in v]
    try:
        _PEAK_DIR.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(out), encoding="utf-8")
    except OSError:
        pass
    return out


# ══════════════════════════ виджеты плеера ══════════════════════════ #

class PlayButton(QAbstractButton):
    """Круглая кнопка Play в цвет акцента (обложки) со свечением, которое дышит в такт басу."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(56, 56)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._hover = False
        self.playing = False

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        c = QPointF(W / 2, H / 2)
        acc = accent()
        d = CURRENT
        lvl = d.level if d is not None and self.playing else 0.0
        import wave_veil
        if wave_veil.void():                                   # «Моя волна»: на черноте — только белый знак
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 255 if self._hover or self.isDown() else 225))
            if self.playing:
                p.drawRoundedRect(QRectF(c.x() - 7, c.y() - 8, 5, 16), 1.5, 1.5)
                p.drawRoundedRect(QRectF(c.x() + 2, c.y() - 8, 5, 16), 1.5, 1.5)
            else:
                tri = QPainterPath()
                tri.moveTo(c.x() - 5, c.y() - 9)
                tri.lineTo(c.x() + 10, c.y())
                tri.lineTo(c.x() - 5, c.y() + 9)
                tri.closeSubpath()
                p.drawPath(tri)
            p.end()
            return
        if on("play_glow") and self.playing:                    # свечение + кольцо-эквалайзер
            gr = QRadialGradient(c, 27)
            g0 = QColor(acc); g0.setAlpha(int(70 + 110 * lvl))
            g1 = QColor(acc); g1.setAlpha(0)
            gr.setColorAt(0.62, g0)
            gr.setColorAt(1.0, g1)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(gr)
            p.drawEllipse(c, 28, 28)
            if d is not None and d.bands:
                pen = QPen(QColor(acc.red(), acc.green(), acc.blue(), 190), 2.0, Qt.PenStyle.SolidLine,
                           Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                n = len(d.bands)
                for i, b in enumerate(d.bands):
                    a = -math.pi / 2 + i * 2 * math.pi / n
                    r0 = 23.5
                    r1 = r0 + 1 + 3.6 * b
                    p.drawLine(QPointF(c.x() + math.cos(a) * r0, c.y() + math.sin(a) * r0),
                               QPointF(c.x() + math.cos(a) * r1, c.y() + math.sin(a) * r1))
        r = 22 * (0.96 if self.isDown() else (1.03 if self._hover else 1.0))
        g = QLinearGradient(c.x(), c.y() - r, c.x(), c.y() + r)
        g.setColorAt(0, acc.lighter(118))
        g.setColorAt(1, accent2())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(c, r, r)
        p.setPen(QPen(QColor(255, 255, 255, 70), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(c.x() - r + 1, c.y() - r + 1, 2 * r - 2, 2 * r - 2), 30 * 16, 120 * 16)
        fg = on_accent(acc)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fg)
        if self.playing:
            p.drawRoundedRect(QRectF(c.x() - 7, c.y() - 8, 5, 16), 1.5, 1.5)
            p.drawRoundedRect(QRectF(c.x() + 2, c.y() - 8, 5, 16), 1.5, 1.5)
        else:
            tri = QPainterPath()
            tri.moveTo(c.x() - 5, c.y() - 9)
            tri.lineTo(c.x() + 10, c.y())
            tri.lineTo(c.x() - 5, c.y() + 9)
            tri.closeSubpath()
            p.drawPath(tri)
        p.end()


class MiniLyric(QWidget):
    """Текущая строка текста песни под исполнителем в плеере: смена — плавной сменой."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(15)
        self.setMinimumWidth(80)
        self.text = ""
        self._old = ""
        self._t = 1.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(260)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(lambda v: (setattr(self, "_t", float(v)), self.update()))

    def set_text(self, s):
        s = (s or "").strip()
        if s == self.text:
            return
        self._old, self.text = self.text, s
        if _motion() > 0 and self.isVisible():
            self._t = 0.0
            self._anim.stop()
            self._anim.start()
        else:
            self._t = 1.0
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        f = _Y().ya_font(11, QFont.Weight.DemiBold)
        p.setFont(f)
        fm = QFontMetrics(f)
        W, H = self.width(), self.height()
        acc = accent()
        for s, a, dy in ((self._old, 1 - self._t, -6 * self._t), (self.text, self._t, 6 * (1 - self._t))):
            if not s or a <= 0.02:
                continue
            c = QColor(acc)
            c.setAlphaF(0.85 * a)
            p.setPen(c)
            p.drawText(QRectF(0, dy, W, H), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText("♪ " + s, Qt.TextElideMode.ElideRight, W))
        p.end()


class SunSpinner(QWidget):
    """Солнце ECHOES как индикатор загрузки: лучи по очереди загораются."""

    def __init__(self, size=28, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._t0 = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self.update)

    def showEvent(self, e):
        self._timer.start()

    def hideEvent(self, e):
        self._timer.stop()

    def paintEvent(self, _):
        p = QPainter(self)
        paint_sun(p, QPointF(self.width() / 2, self.height() / 2), self.width() / 2 - 1,
                  time.monotonic() - self._t0, spin=True)
        p.end()


def paint_sun(p: QPainter, c: QPointF, R: float, t: float, spin=False, alpha=1.0):
    """Колючее солнце логотипа. spin — лучи загораются по кругу (загрузка); иначе — медленно дышит."""
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    acc = accent()
    n = 14
    lit = (t * 14) % n if spin else -1
    for i in range(n):
        a = i * 2 * math.pi / n - math.pi / 2 + (0 if spin else t * 0.15)
        k = 1.0
        if spin:
            dist = (i - lit) % n
            k = 0.25 + 0.75 * max(0.0, 1 - dist / 5)
        else:
            k = 0.75 + 0.25 * math.sin(t * 1.4 + i)
        r0, r1 = R * 0.42, R * (0.82 + 0.18 * k)
        col = QColor(acc)
        col.setAlphaF(max(0.0, min(1.0, alpha * (0.35 + 0.65 * k))))
        path = QPainterPath()
        w = 0.17
        path.moveTo(c.x() + math.cos(a - w) * r0, c.y() + math.sin(a - w) * r0)
        path.lineTo(c.x() + math.cos(a) * r1, c.y() + math.sin(a) * r1)
        path.lineTo(c.x() + math.cos(a + w) * r0, c.y() + math.sin(a + w) * r0)
        path.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawPath(path)
    g = QRadialGradient(c, R * 0.46)
    c0 = QColor("#fff6b0"); c0.setAlphaF(alpha)
    c1 = QColor(acc); c1.setAlphaF(alpha)
    g.setColorAt(0, c0)
    g.setColorAt(1, c1)
    p.setBrush(g)
    p.drawEllipse(c, R * 0.44, R * 0.44)


class EmptyArt(QLabel):
    """Пустая страница с характером: живое солнце ECHOES над подписью."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        self.setWordWrap(True)
        self._t0 = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(lambda: self.update(QRect(0, 0, self.width(), 96)))

    def _art(self) -> bool:
        return on("empty_art")

    def showEvent(self, e):
        super().showEvent(e)
        if self._art() and _motion() > 0:
            self._timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()

    def sizeHint(self):
        s = super().sizeHint()
        return QSize(s.width(), s.height() + (96 if self._art() else 0))

    def minimumSizeHint(self):
        s = super().minimumSizeHint()
        return QSize(s.width(), s.height() + (96 if self._art() else 0))

    def paintEvent(self, e):
        if self._art():
            p = QPainter(self)
            t = time.monotonic() - self._t0
            cy = 52 + 4 * math.sin(t * 1.6)
            paint_sun(p, QPointF(self.width() / 2, cy), 34, t, alpha=0.9)
            p.setPen(Qt.PenStyle.NoPen)                          # тень-«горизонт»
            g = QRadialGradient(QPointF(self.width() / 2, 94), 46)
            g.setColorAt(0, QColor(0, 0, 0, 90))
            g.setColorAt(1, QColor(0, 0, 0, 0))
            p.setBrush(g)
            p.drawEllipse(QPointF(self.width() / 2, 94), 46, 6)
            p.end()
        super().paintEvent(e)


class MiniEq(QWidget):
    """Крошечный живой эквалайзер у «Сейчас слушает» друга."""

    def __init__(self, parent=None, color=None):
        super().__init__(parent)
        self.setFixedSize(18, 14)
        self.color = color
        self._t0 = time.monotonic() + random.random() * 10
        self._timer = QTimer(self)
        self._timer.setInterval(70)
        self._timer.timeout.connect(self.update)

    def showEvent(self, e):
        if on("now_eq") and _motion() > 0:
            self._timer.start()

    def hideEvent(self, e):
        self._timer.stop()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = time.monotonic() - self._t0
        col = QColor(self.color) if self.color else accent()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        for i in range(4):
            v = 0.3 + 0.7 * abs(math.sin(t * (3.1 + i * 1.3) + i * 1.7)) if on("now_eq") else 0.5
            h = 3 + v * 11
            p.drawRoundedRect(QRectF(i * 4.6, 14 - h, 3.2, h), 1.4, 1.4)
        p.end()


# ══════════════════════════ липкий заголовок ══════════════════════════ #

class StickyBar(QWidget):
    """Стеклянная плашка с именем и кнопкой Play — «прилипает» сверху, когда шапка уехала."""

    def __init__(self, page, title, on_play=None):
        super().__init__(page)
        self.page = page
        self.title = title
        self.on_play = on_play
        self._a = 0.0
        self._target = 0.0
        self.setFixedHeight(58)
        self.setMouseTracking(True)
        self.hide()
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(180)
        self._anim.valueChanged.connect(self._step)
        page.verticalScrollBar().valueChanged.connect(self._scrolled)

    def _step(self, v):
        self._a = float(v)
        if self._a <= 0.01 and self._target == 0:
            self.hide()
        self.update()

    def _scrolled(self, v):
        hdr = getattr(self.page, "header", None)
        lim = (hdr.height() - 70) if hdr is not None else 220
        want = 1.0 if v > lim else 0.0
        if want == self._target:
            return
        self._target = want
        self.setGeometry(0, 0, self.page.viewport().width(), self.height())
        self.raise_()
        if want:
            self.show()
        self._anim.stop()
        self._anim.setStartValue(self._a)
        self._anim.setEndValue(want)
        self._anim.setDuration(180 if _motion() > 0 else 1)
        self._anim.start()

    def _btn_rect(self) -> QRectF:
        return QRectF(18, 9, 40, 40)

    def mouseReleaseEvent(self, e):
        if self._btn_rect().contains(e.position()) and self.on_play:
            self.on_play()

    def mouseMoveEvent(self, e):
        self.setCursor(Qt.CursorShape.PointingHandCursor if self._btn_rect().contains(e.position())
                       else Qt.CursorShape.ArrowCursor)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._a)
        W, H = self.width(), self.height()
        acc = accent()
        g = QLinearGradient(0, 0, W, 0)
        c0 = QColor(acc).darker(330); c0.setAlpha(240)
        g.setColorAt(0, c0)
        g.setColorAt(1, QColor(18, 18, 20, 236))
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, W, H), 0, 0)
        p.fillPath(path, g)
        p.setPen(QPen(QColor(255, 255, 255, 26), 1))
        p.drawLine(QPointF(0, H - 0.5), QPointF(W, H - 0.5))
        br = self._btn_rect()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(acc)
        p.drawEllipse(br)
        p.setBrush(on_accent(acc))
        tri = QPainterPath()
        cx, cy = br.center().x(), br.center().y()
        tri.moveTo(cx - 5, cy - 8)
        tri.lineTo(cx + 9, cy)
        tri.lineTo(cx - 5, cy + 8)
        tri.closeSubpath()
        p.drawPath(tri)
        f = _Y().ya_font(20, QFont.Weight.Black)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(72, 0, W - 90, H), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   QFontMetrics(f).elidedText(self.title, Qt.TextElideMode.ElideRight, W - 90))
        p.end()


def attach_sticky(page, title, on_play=None):
    if not on("sticky"):
        return None
    old = page.__dict__.get("_sticky")
    if old is not None:
        try:
            old.deleteLater()
        except RuntimeError:
            pass
    bar = StickyBar(page, title, on_play)
    page._sticky = bar
    return bar


# ══════════════════════════ шапка страницы плейлиста/альбома ══════════════════════════ #

class _HeaderTint(QObject):
    """Градиент цвета обложки за шапкой страницы плейлиста; при прокрутке списка — растворяется."""
    H = 330

    def __init__(self, page, cover_widget, scroll_view):
        super().__init__(page)
        self.page, self.cov, self.view = page, cover_widget, scroll_view
        page.installEventFilter(self)
        self._pending = False
        scroll_view.verticalScrollBar().valueChanged.connect(self._scrolled)

    def _scrolled(self, _v):
        if not self._pending:
            self._pending = True
            QTimer.singleShot(16, self._flush)

    def _flush(self):
        self._pending = False
        self.page.update(QRect(0, 0, self.page.width(), self.H))

    def eventFilter(self, obj, ev):
        from PyQt6.QtCore import QEvent
        if ev.type() == QEvent.Type.Paint and on("headers"):
            path = getattr(self.cov, "_path", "") or ""
            cols = palette(path)[0] if path else [accent()]
            fade = 1.0 - min(1.0, self.view.verticalScrollBar().value() / 260.0)
            if fade > 0.01:
                p = QPainter(obj)
                W = obj.width()
                g = QLinearGradient(0, 0, 0, self.H)
                c = QColor(cols[0]); c.setAlpha(int(92 * fade))
                c2 = QColor(cols[1] if len(cols) > 1 else cols[0]); c2.setAlpha(int(30 * fade))
                g.setColorAt(0, c)
                g.setColorAt(0.55, c2)
                g.setColorAt(1, QColor(0, 0, 0, 0))
                path_ = QPainterPath()
                path_.addRoundedRect(QRectF(0, 0, W, self.H + 30), 22, 22)
                p.setClipRect(QRect(0, 0, W, self.H))
                p.fillPath(path_, g)
                p.end()
        return False


def artist_banner(W, H, picture) -> QPixmap | None:
    """Шапка исполнителя: размытое фото поверх стекла + цвет фото снизу вверх."""
    if not on("headers") or not picture:
        return None
    try:
        from img_load import read_image
        img = read_image(picture, 256)
    except Exception:                                          # noqa: BLE001
        img = QImage(picture)
    if img.isNull():
        return None
    from echo_glass import liquid_surface
    pm = liquid_surface(QSize(W, H), radius=16)
    small = img.scaled(28, max(8, int(28 * H / max(1, W))), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                       Qt.TransformationMode.SmoothTransformation)
    big = small.scaled(W, H, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, W, H + 20), 16, 16)
    p.setClipPath(clip)
    p.setOpacity(0.55)
    p.drawImage(QRectF(0, 0, W, H), big, QRectF((big.width() - W) / 2, (big.height() - H) / 2, W, H))
    p.setOpacity(1.0)
    col = palette(picture)[0][0]
    g = QLinearGradient(0, 0, 0, H)
    c = QColor(col).darker(260); c.setAlpha(80)
    g.setColorAt(0, QColor(0, 0, 0, 40))
    g.setColorAt(0.6, c)
    g.setColorAt(1, QColor(0, 0, 0, 170))
    p.fillRect(QRectF(0, 0, W, H), g)
    p.end()
    return pm


# ══════════════════════════ карточки ══════════════════════════ #

def card_glow(p: QPainter, s: float, cover: str, circle: bool):
    """Свечение под карточкой в цвет обложки (рисуется до самой обложки)."""
    col = palette(cover)[0][0] if cover else accent()
    g = QRadialGradient(QPointF(s / 2, s * 0.98), s * 0.55)
    c = QColor(col); c.setAlpha(150)
    g.setColorAt(0, c)
    c.setAlpha(0)
    g.setColorAt(1, c)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawEllipse(QRectF(s * 0.05, s * 0.84, s * 0.9, s * 0.26))


def card_ring(p: QPainter, r: QRectF, cover: str, circle: bool, radius: float):
    col = palette(cover)[0][0] if cover else accent()
    pen = QPen(QColor(col.red(), col.green(), col.blue(), 200), 1.6)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    rr = r.adjusted(0.8, 0.8, -0.8, -0.8)
    if circle:
        p.drawEllipse(rr)
    else:
        p.drawRoundedRect(rr, radius, radius)


class _Cascade(QObject):
    """Каскад появления: новые карточки, показанные «пачкой», возникают по очереди (20 мс шаг)."""

    def __init__(self):
        super().__init__()
        self.cards = []
        self._burst_t = 0.0
        self._burst_n = 0
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)

    def add(self, card):
        now = time.monotonic()
        if now - self._burst_t > 0.12:
            self._burst_n = 0
        self._burst_t = now
        delay = min(0.3, self._burst_n * 0.018)
        self._burst_n += 1
        card._appear = 0.0
        card._appear_t0 = now + delay
        self.cards.append(weakref.ref(card))
        if not self.timer.isActive():
            self.timer.start()

    def _tick(self):
        now = time.monotonic()
        live = []
        for ref in self.cards:
            c = ref()
            if c is None:
                continue
            try:
                a = max(0.0, min(1.0, (now - c._appear_t0) / 0.22))
                a = 1 - (1 - a) ** 3
                if a != c._appear:
                    c._appear = a
                    c.update()
                if a < 1.0:
                    live.append(ref)
            except RuntimeError:
                continue
        self.cards = live
        if not live:
            self.timer.stop()


_CASCADE = None


def cascade(card):
    global _CASCADE
    if not on("cascade") or _motion() <= 0:
        return
    if _CASCADE is None:
        _CASCADE = _Cascade()
    _CASCADE.add(card)


# ══════════════════════════ перелёт обложки ══════════════════════════ #

_LAST_CARD = {"ref": None, "t": 0.0}


def card_clicked(card):
    _LAST_CARD["ref"] = weakref.ref(card)
    _LAST_CARD["t"] = time.monotonic()


class _Flight(QWidget):
    def __init__(self, top, pm, src: QRectF, dst: QRectF, src_rad, dst_rad, done):
        super().__init__(top)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.pm, self.src, self.dst, self.sr, self.dr, self.done = pm, src, dst, src_rad, dst_rad, done
        self._t = 0.0
        self.setGeometry(top.rect())
        self.show()
        self.raise_()
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(380)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.valueChanged.connect(self._step)
        self.anim.finished.connect(self._end)
        self.anim.start()
        self._last = QRect()

    def _rect(self, t) -> QRectF:
        a, b = self.src, self.dst
        arc = math.sin(t * math.pi) * -18                      # лёгкая дуга вверх
        return QRectF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t + arc,
                      a.width() + (b.width() - a.width()) * t, a.height() + (b.height() - a.height()) * t)

    def _step(self, v):
        self._t = float(v)
        r = self._rect(self._t).toAlignedRect().adjusted(-24, -24, 24, 24)
        self.update(r.united(self._last))
        self._last = r

    def _end(self):
        try:
            self.done()
        finally:
            self.hide()
            self.deleteLater()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = self._rect(self._t)
        rad = self.sr + (self.dr - self.sr) * self._t
        sh = QRadialGradient(r.center() + QPointF(0, 14), max(r.width(), r.height()) * 0.7)
        sh.setColorAt(0, QColor(0, 0, 0, int(120 * math.sin(self._t * math.pi))))
        sh.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(r.adjusted(-24, -24, 24, 24), sh)
        path = QPainterPath()
        path.addRoundedRect(r, rad, rad)
        p.setClipPath(path)
        p.drawPixmap(r, self.pm, QRectF(self.pm.rect()))
        p.end()


def fly_to(shell, target):
    """Если только что кликнули по карточке — обложка «перелетит» с неё на target (RoundCover страницы)."""
    ref = _LAST_CARD.get("ref")
    card = ref() if ref else None
    _LAST_CARD["ref"] = None
    if card is None or not on("shared") or _motion() <= 0 or time.monotonic() - _LAST_CARD["t"] > 0.6:
        return
    try:
        top = shell.window()
        s = card.size_
        src = QRectF(QPointF(card.mapTo(top, QPoint(0, 0))), QSize(s, s).toSizeF())
        pm = card.__dict__.get("_cbuf")
        if pm is None or not card.isVisible():
            return
        dpr = pm.devicePixelRatio()
        pm = pm.copy(0, 0, int(s * dpr), int(s * dpr))
        pm.setDevicePixelRatio(dpr)
    except RuntimeError:
        return
    saved = target.pixmap()
    blank = QPixmap(max(1, target.width()), max(1, target.height()))
    blank.fill(Qt.GlobalColor.transparent)
    target.setPixmap(blank)                                    # снимок перехода — уже без обложки

    def go():
        try:
            dst = QRectF(QPointF(target.mapTo(top, QPoint(0, 0))), target.size().toSizeF())

            def done():
                try:
                    target.setPixmap(saved)
                except RuntimeError:
                    pass
            _Flight(top, pm, src, dst, 10, getattr(target, "radius", 12), done)
        except RuntimeError:
            pass
    QTimer.singleShot(0, go)


# ══════════════════════════ миксы из обложек ══════════════════════════ #

def mix_paint(p: QPainter, s: float, covers: list):
    """Поверх градиента «микса» — веер из 3 обложек треков в правом нижнем углу (как Daily Mix)."""
    Y = _Y()
    covers = [c for c in covers if c][:3]
    for i, cv in enumerate(reversed(covers)):
        k = len(covers) - 1 - i
        sz = s * 0.36
        p.save()
        p.translate(s * 0.86 - k * s * 0.12, s * 0.30 + k * s * 0.05)
        p.rotate(8 - k * 8)
        r = QRectF(-sz / 2, -sz / 2, sz, sz)
        sh = QPainterPath()
        sh.addRoundedRect(r.adjusted(-1, 2, 1, 4), 7, 7)
        p.fillPath(sh, QColor(0, 0, 0, 90))
        pm = Y.cover_pixmap(cv, int(sz), 6)
        p.drawPixmap(r, pm, QRectF(pm.rect()))
        p.restore()


def mix_colors(covers: list):
    cols = []
    for cv in covers[:3]:
        if cv:
            cols.append(palette(cv)[0][0])
    if len(cols) >= 2:
        return cols[0], cols[1]
    return None


# ══════════════════════════ звуки интерфейса ══════════════════════════ #

_CLICK = None


def ui_click():
    if not on("ui_sounds"):
        return
    global _CLICK
    try:
        import sys
        if sys.platform != "win32":
            return
        import winsound
        if _CLICK is None:
            import struct
            import wave
            f = data_home.root() / "ui_cache" / "click.wav"
            if not f.exists():
                f.parent.mkdir(parents=True, exist_ok=True)
                sr = 44100
                n = int(sr * 0.045)
                with wave.open(str(f), "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(sr)
                    data = bytearray()
                    rng = random.Random(3)
                    for i in range(n):
                        env = math.exp(-i / (sr * 0.006))
                        v = (0.55 * math.sin(2 * math.pi * 2100 * i / sr) + 0.45 * (rng.random() * 2 - 1)) * env
                        data += struct.pack("<h", int(v * 32767 * 0.12))
                    w.writeframes(bytes(data))
            _CLICK = str(f)
        winsound.PlaySound(_CLICK, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except Exception:                                          # noqa: BLE001
        pass


# ══════════════════════════ пасхалка: дождь из обложек ══════════════════════════ #

class CoverRain(QWidget):
    def __init__(self, top, covers):
        super().__init__(top)
        self.setGeometry(top.rect())
        self.bg = top.grab()
        rng = random.Random()
        W, H = self.width(), self.height()
        self.drops = []
        for i in range(46):
            cv = covers[i % len(covers)] if covers else ""
            sz = rng.randint(54, 120)
            self.drops.append({"pm": _Y().cover_pixmap(cv, sz, 8, seed=str(i)), "x": rng.random() * W,
                               "y": -sz - rng.random() * H * 1.1, "v": rng.uniform(420, 820), "s": sz,
                               "a": rng.uniform(-30, 30), "va": rng.uniform(-90, 90)})
        self._t0 = time.monotonic()
        self._last = self._t0
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self.show()
        self.raise_()

    def _tick(self):
        now = time.monotonic()
        dt = min(0.05, now - self._last)
        self._last = now
        for d in self.drops:
            d["y"] += d["v"] * dt
            d["a"] += d["va"] * dt
        if now - self._t0 > 3.6:
            self.timer.stop()
            self.deleteLater()
            return
        self.update()

    def mousePressEvent(self, e):
        self.timer.stop()
        self.deleteLater()

    def paintEvent(self, _):
        p = QPainter(self)
        p.drawPixmap(0, 0, self.bg)
        t = time.monotonic() - self._t0
        k = min(1.0, t / 0.3) * min(1.0, max(0.0, (3.6 - t) / 0.4))
        p.fillRect(self.rect(), QColor(0, 0, 0, int(120 * k)))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for d in self.drops:
            p.save()
            p.translate(d["x"], d["y"])
            p.rotate(d["a"])
            s = d["s"]
            p.drawPixmap(QRectF(-s / 2, -s / 2, s, s), d["pm"], QRectF(d["pm"].rect()))
            p.restore()
        p.end()


# ══════════════════════════ двигатель ══════════════════════════ #

class _PeakBus(QObject):
    done = pyqtSignal(str, object)


class Decor(QObject):
    """Живое оформление одной оболочки YaShell: акцент, аура, пульс, кант, волна, пластинка, текст."""

    def __init__(self, shell):
        super().__init__(shell)
        global CURRENT
        CURRENT = self
        self.shell = shell
        load_cfg(shell.win.settings)
        self.accent = None                                     # QColor | None (None — акцент темы)
        self._acc_from = None
        self._acc_to = None
        self.pal = []
        self.pal_key = ""
        self.temp = 0.0
        self.weather = ""
        self.level = 0.0
        self.bands = []
        self.phase = random.random() * 100
        self._mouse = None                                     # глобальная позиция курсора
        self._mouse_dirty = False
        self._gap = None
        self._gap_t = 0.0
        self._bg_pm = None
        self._bg_key = None
        self._peaks_bus = _PeakBus()
        self._peaks_bus.done.connect(self._peaks_ready)
        self._peaks_for = ""
        self._rim_last = {}
        self._acc_anim = QVariantAnimation(self)
        self._acc_anim.setDuration(900)
        self._acc_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._acc_anim.setStartValue(0.0)
        self._acc_anim.setEndValue(1.0)
        self._acc_anim.valueChanged.connect(self._acc_step)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._slow = QTimer(self)
        self._slow.setInterval(1000)
        self._slow.timeout.connect(self._slow_tick)
        self._slow.start()
        self._last_t = time.monotonic()
        import native_ui                                  # в Python — только колесо и движение мыши
        from PyQt6.QtCore import QEvent
        native_ui.app_filter(self, (QEvent.Type.Wheel, QEvent.Type.MouseMove))
        self.taskbar = None
        QTimer.singleShot(1500, self._taskbar_init)
        try:
            import paint_cache
            paint_cache.SPRING = on("spring") and _motion() > 0
        except Exception:                                      # noqa: BLE001
            pass

    # ── настройки ── #

    def apply_settings(self):
        load_cfg(self.shell.win.settings)
        try:
            import paint_cache
            paint_cache.SPRING = on("spring") and _motion() > 0
        except Exception:                                      # noqa: BLE001
            pass
        self._bg_pm = None
        self._gap = None
        if not on("cover_accent"):
            self.accent = None
        self.refresh_all()
        self._taskbar_init()
        try:
            import ya_weather
            ya_weather.install(self.shell.win)
        except Exception as e:                                 # noqa: BLE001
            print("[weather]", e)

    def refresh_all(self):
        """Перерисовать всё один раз (смена режима стекла, акцента, фона)."""
        sh = self.shell
        try:
            from yamusic_theme import AmbientFrame, Logo
            for f in AmbientFrame.live(sh):
                f.__dict__.pop("_deco_pm", None)
            sh.update()
            for w in sh.findChildren(QWidget):
                if isinstance(w, (Logo, PlayButton, MiniLyric)) or type(w).__name__ == "ProgressLine":
                    w.update()
        except RuntimeError:
            pass
        mini = getattr(sh, "p_lyric", None)
        if mini is not None:
            mini.setVisible(on("mini_lyrics") and bool(mini.text))
        vc = getattr(sh, "p_cover", None)
        if isinstance(vc, VinylCover):
            vc.fit()

    def shutdown(self):
        global CURRENT
        self._timer.stop()
        self._slow.stop()
        try:
            import native_ui
            native_ui.app_filter_remove(self)
        except RuntimeError:
            pass
        if self.taskbar is not None:                         # сам объект живёт с окном (win_taskbar.get)
            self.taskbar.clear()
            self.taskbar.set_buttons(False)
        if CURRENT is self:
            CURRENT = None

    # ── трек ── #

    def track_changed(self, t):
        cover = str((t or {}).get("cover") or "")
        self.pal, self.temp = palette(cover) if cover else ([], 0.0)
        self.pal_key = cover
        self.weather = ("rain" if self.temp < -0.35 else "sun" if self.temp > 0.45 else "") if cover else ""
        new = vivid(cover) if on("cover_accent") else None
        old = QColor(self.accent) if self.accent is not None else base_accent()
        target = new if new is not None else base_accent()
        self._acc_from, self._acc_to = old, target
        if _motion() > 0 and self.shell.isVisible():
            self._acc_anim.stop()
            self._acc_anim.start()
        else:
            self._acc_step(1.0)
        self._bg_pm = None
        self.shell.update()                                     # аура/тон — под новую обложку
        try:
            from yamusic_theme import AmbientFrame
            if _CFG["glass"] in ("tint",) or self.weather or on("weather"):
                for f in AmbientFrame.live(self.shell):
                    f.update()
        except RuntimeError:
            pass
        self._request_peaks(t)
        mini = getattr(self.shell, "p_lyric", None)
        if mini is not None:
            mini.set_text("")
            mini.hide()

    def _acc_step(self, v):
        if self._acc_from is None or self._acc_to is None:
            return
        self.accent = _mix(self._acc_from, self._acc_to, float(v))
        sh = self.shell
        for name in ("b_play", "progress", "p_lyric"):
            w = getattr(sh, name, None)
            if w is not None:
                w.update()
        logo = sh.__dict__.get("_logo")
        if logo is not None:
            logo.update()
        tb = getattr(sh.win, "titlebar", None)                 # солнце в заголовке окна — тоже
        if tb is not None:
            tb.update(0, 0, 40, tb.height())
        if float(v) >= 1.0:
            from yamusic_theme import AmbientFrame
            if _CFG["glass"] == "tint":
                for f in AmbientFrame.live(sh):
                    f.update()
            st = getattr(sh.pages.get("artist"), "_sticky", None) if hasattr(sh, "pages") else None
            if st is not None:
                st.update()

    # ── волна ── #

    def _request_peaks(self, t):
        prog = getattr(self.shell, "progress", None)
        if prog is None:
            return
        prog.peaks = None
        prog.update()
        path = str((t or {}).get("path") or "")
        if not on("wave_bar") or not path or not Path(path).exists():
            return
        self._peaks_for = path
        hit = _PEAKS.get(path)
        if hit is not None:
            prog.peaks = hit
            return
        import threading

        def work():
            v = compute_peaks(path)
            try:
                self._peaks_bus.done.emit(path, v)
            except RuntimeError:
                pass
        threading.Thread(target=work, name="echoes-peaks", daemon=True).start()

    def _peaks_ready(self, path, v):
        if v is None:
            return
        _PEAKS[path] = v
        if len(_PEAKS) > 60:
            _PEAKS.pop(next(iter(_PEAKS)))
        prog = getattr(self.shell, "progress", None)
        if prog is not None and path == self._peaks_for:
            prog.peaks = v
            prog.update()

    # ── мини-текст ── #

    def mini_lyrics(self, pos_s):
        mini = getattr(self.shell, "p_lyric", None)
        if mini is None:
            return
        if not on("mini_lyrics"):
            if mini.isVisible():
                mini.hide()
            return
        lv = getattr(self.shell.win, "lyrics_view", None)
        lines = getattr(lv, "_lines", None) or []
        if not lines or not getattr(lv, "_has_timings", False):
            if mini.isVisible():
                mini.hide()
            return
        f = float(getattr(self.shell.win.engine, "preset_factor", 1.0) or 1.0)
        ms = pos_s * 1000 * f + 150
        cur = ""
        for ln in lines:
            m = ln.get("ms", -1) if isinstance(ln, dict) else -1
            if m is None or m < 0:
                continue
            if m <= ms:
                cur = ln.get("text") or ""
            else:
                break
        mini.set_text(cur)
        vis = bool(cur)
        if mini.isVisible() != vis:
            mini.setVisible(vis)

    # ── фон окна (аура) ── #

    def _gap_region(self) -> QRegion:
        now = time.monotonic()
        if self._gap is not None and now - self._gap_t < 0.7:
            return self._gap
        sh = self.shell
        reg = QRegion(sh.rect())
        try:
            from yamusic_theme import AmbientFrame
            for f in AmbientFrame.live(sh):
                if not f.isVisible() or f.window() is not sh.window():
                    continue
                r = QRect(f.mapTo(sh, QPoint(0, 0)), f.size())
                R = 22
                if r.width() > 2 * R and r.height() > 2 * R:    # углы остаются в области — они скруглены
                    reg -= QRegion(r.adjusted(R, 0, -R, 0))
                    reg -= QRegion(r.adjusted(0, R, 0, -R))
        except RuntimeError:
            pass
        self._gap, self._gap_t = reg, now
        return reg

    def _bg_image(self, W, H):
        path = str(_CFG.get("bg_image") or "")
        if not path:
            return None
        key = (path, W, H, _CFG["bg_dim"])
        if self._bg_key == key and self._bg_pm is not None:
            return self._bg_pm
        try:
            from img_load import read_image
            img = read_image(path, 1600)
        except Exception:                                      # noqa: BLE001
            img = QImage(path)
        if img.isNull():
            self._bg_pm, self._bg_key = None, key
            return None
        small = img.scaled(max(8, W // 14), max(8, H // 14), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                           Qt.TransformationMode.SmoothTransformation)
        big = small.scaled(W, H, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                           Qt.TransformationMode.SmoothTransformation)
        pm = QPixmap(W, H)
        pm.fill(QColor(0, 0, 0))
        p = QPainter(pm)
        p.drawImage(0, 0, big, (big.width() - W) // 2, (big.height() - H) // 2, W, H)
        p.fillRect(pm.rect(), QColor(0, 0, 0, int(255 * _CFG["bg_dim"] / 100)))
        p.end()
        self._bg_pm, self._bg_key = pm, key
        return pm

    AURA_DIV = 8                                               # аура считается в 1/8 размера и растягивается

    def _aura(self, W, H) -> QPixmap:
        """Пятна обложки + время суток — в маленькую картинку; пересобирается раз за кадр анимации."""
        animated = _CFG["glass"] != "clear"
        t = self.phase if animated else 0.0
        mx = my = 0.0
        if on("parallax") and animated and self._mouse is not None:
            lp = self.shell.mapFromGlobal(self._mouse)
            mx = (lp.x() / max(1, W) - 0.5) * -14
            my = (lp.y() / max(1, H) - 0.5) * -10
        boost = 0.75 + (0.55 * self.level if on("pulse") and animated else 0.0)
        key = (W, H, round(t, 3), round(boost, 3), round(mx, 1), round(my, 1), self.pal_key, on("aura"),
               on("daytime"), time.localtime().tm_hour, self._bg_key is not None and self._bg_pm is not None,
               accent().rgb() if not self.pal else 0)
        hit = self.__dict__.get("_aura_pm")
        if hit is not None and hit[0] == key:
            return hit[1]
        D = self.AURA_DIV
        w, h = max(4, W // D), max(4, H // D)
        pm = QPixmap(w, h)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        if on("aura"):
            cols = self.pal or [accent(), QColor("#ff4fa3"), QColor("#2fc6ff")]
            spots = ((0.15, 0.2, 0.55, 0), (0.85, 0.3, 0.5, 1), (0.5, 0.95, 0.65, 2), (0.9, 0.95, 0.4, 0))
            for i, (cx, cy, rr, ci) in enumerate(spots):
                ox = math.sin(t * (0.11 + 0.03 * i) + i * 1.9) * w * 0.08
                oy = math.cos(t * (0.09 + 0.02 * i) + i * 2.3) * h * 0.08
                c = QPointF(cx * w + ox + mx / D * (1 + i * 0.3), cy * h + oy + my / D * (1 + i * 0.3))
                g = QRadialGradient(c, max(w, h) * rr)
                col = QColor(cols[ci % len(cols)])
                col.setAlpha(int(min(255, 74 * boost)))
                g.setColorAt(0, col)
                col.setAlpha(0)
                g.setColorAt(1, col)
                p.fillRect(pm.rect(), g)
        if on("daytime"):
            top, bot = daytime_tint()
            g = QLinearGradient(0, 0, 0, h)
            g.setColorAt(0, top)
            g.setColorAt(1, bot)
            p.fillRect(pm.rect(), g)
        p.end()
        self._aura_pm = (key, pm)
        return pm

    def paint_shell(self, p: QPainter, rect: QRect):
        W, H = self.shell.width(), self.shell.height()
        bg = self._bg_image(W, H)
        if not on("aura") and bg is None and not on("daytime"):
            return
        if _CFG["glass"] == "clear":                           # прозрачные панели — фон виден везде
            p.setClipRect(rect)
        else:                                                  # под матовым стеклом фон не виден — только щели
            reg = self._gap_region() & QRegion(rect)
            if reg.isEmpty():
                return
            p.setClipRegion(reg)
            rect = reg.boundingRect()
        if bg is not None:
            p.drawPixmap(rect, bg, rect)
        else:
            p.fillRect(rect, QColor(_Y().BG))
        if on("aura") or on("daytime"):
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawPixmap(QRect(0, 0, W, H), self._aura(W, H))

    # ── события: курсор (кант, параллакс) ── #

    def mouse_in(self, frame) -> float | None:
        if self._mouse is None:
            return None
        try:
            lp = frame.mapFromGlobal(self._mouse)
        except RuntimeError:
            return None
        if -40 <= lp.x() <= frame.width() + 40 and -30 <= lp.y() <= frame.height():
            return float(lp.x())
        return None

    def _transition(self) -> bool:
        try:
            import ui_anim
            st = getattr(self.shell, "stack", None)
            return bool(st is not None and ui_anim._OVERLAYS.get(id(st)) is not None)
        except Exception:                                      # noqa: BLE001
            return False

    def eventFilter(self, obj, ev):
        from PyQt6.QtCore import QEvent
        if ev.type() == QEvent.Type.Wheel:
            self._busy_t = time.monotonic()
            return False
        if ev.type() == QEvent.Type.MouseMove and (on("rim") or on("parallax")):
            try:
                self._mouse = ev.globalPosition().toPoint()
            except AttributeError:
                return False
            self._mouse_dirty = True
            if not self._timer.isActive():
                self._timer.start()
        return False

    # ── кадр ── #

    def _active(self) -> bool:
        sh = self.shell
        try:
            win = sh.window()
            return sh.isVisible() and not win.isMinimized()
        except RuntimeError:
            return False

    def _audio(self):
        eng = getattr(self.shell.win, "engine", None)
        if eng is None:
            return
        try:
            x = eng.get_visual_samples(1024)
        except Exception:                                      # noqa: BLE001
            x = None
        if x is None:
            self.level *= 0.9
            return
        import numpy as np
        sp = np.abs(np.fft.rfft(x * np.hanning(x.size)))
        sr = 44100.0
        hz = np.fft.rfftfreq(x.size, 1.0 / sr)
        bass = float(sp[(hz > 35) & (hz < 160)].mean()) if sp.size else 0.0
        v = max(0.0, min(1.0, bass / 22.0))
        self.level = v if v > self.level else self.level * 0.86 + v * 0.14
        edges = (40, 90, 180, 350, 700, 1400, 2800, 5000, 9000, 15000)
        bands = []
        for i in range(len(edges) - 1):
            m = (hz >= edges[i]) & (hz < edges[i + 1])
            b = float(sp[m].mean()) if m.any() else 0.0
            bands.append(max(0.0, min(1.0, (math.log10(1 + b) / 1.6))))
        bands = bands + bands[::-1]
        if len(self.bands) == len(bands):
            bands = [max(b, o * 0.82) for b, o in zip(bands, self.bands)]
        self.bands = bands

    def _tick(self):
        if not self._active():
            self._timer.stop()
            return
        now = time.monotonic()
        dt = min(0.1, now - self._last_t)
        self._last_t = now
        sh = self.shell
        playing = bool(sh.is_playing()) if hasattr(sh, "is_playing") else False
        animated = _CFG["glass"] != "clear"
        need = False
        if playing and (on("pulse") or on("play_glow")):
            self._audio()
            need = True
        elif self.level > 0.01:
            self.level *= 0.85
            self.bands = [b * 0.8 for b in self.bands]
            need = True
        if playing and on("aura") and animated and _motion() > 0:
            self.phase += dt
            need = True
        busy = now - self.__dict__.get("_busy_t", 0) < 0.45 or self._transition()
        if on("aura") and animated and (need or self._mouse_dirty) and not busy and                 now - self.__dict__.get("_aura_t", 0) >= 0.066:
            self._aura_t = now                                 # фон — 15 кадров/с, только щели между панелями;
            sh.update(self._gap_region())                      # пока крутят колесо или идёт переход — замирает
        if on("play_glow"):
            b = getattr(sh, "b_play", None)
            if b is not None and (playing or self.level > 0.01):
                b.update()
        vc = getattr(sh, "p_cover", None)
        if isinstance(vc, VinylCover) and vc.tick(dt, playing):
            need = True
        if self._mouse_dirty and on("rim"):
            self._mouse_dirty = False
            self._update_rims()
        if not need and not vc_moving(vc):
            self._timer.stop()

    def _update_rims(self):
        try:
            from yamusic_theme import AmbientFrame
            frames = AmbientFrame.live(self.shell)
        except RuntimeError:
            return
        for f in frames:
            if not f.isVisible():
                continue
            x = self.mouse_in(f)
            old = self._rim_last.get(id(f), "none")
            k = None if x is None else int(x // 6)
            if k == old:
                continue
            self._rim_last[id(f)] = k
            f.update(QRect(0, 0, f.width(), 4))

    def _slow_tick(self):
        """Раз в секунду: разбудить кадры, если играет; прогресс на значке в панели задач."""
        sh = self.shell
        try:
            playing = bool(sh.is_playing())
        except Exception:                                      # noqa: BLE001
            playing = False
        if playing and self._active() and not self._timer.isActive() and (
                on("aura") or on("pulse") or on("play_glow") or on("vinyl")):
            self._last_t = time.monotonic()
            self._timer.start()
        vc = getattr(sh, "p_cover", None)
        if isinstance(vc, VinylCover) and vc.wants_tick(playing) and not self._timer.isActive():
            self._last_t = time.monotonic()
            self._timer.start()
        if self.taskbar is not None:
            try:
                eng = sh.win.engine
                dur = float(eng.duration or 0)
                pos = float(eng.get_position() or 0)
                t = sh.current_track()
                self.taskbar.update(pos / dur if dur > 0 and t else None, playing)
            except Exception:                                  # noqa: BLE001
                pass

    # ── панель задач ── #

    def _taskbar_init(self):
        import sys
        if sys.platform != "win32":
            return
        want = on("taskbar") or on("thumb_buttons")
        if not want:
            if self.taskbar is not None:
                self.taskbar.clear()
                self.taskbar.set_buttons(False)
                self.taskbar = None
            return
        try:
            import win_taskbar
            if self.taskbar is None:
                self.taskbar = win_taskbar.get(self.shell.win)
            self.taskbar.progress_on = on("taskbar")
            self.taskbar.set_buttons(on("thumb_buttons"))
        except Exception as e:                                 # noqa: BLE001
            print("[decor] taskbar:", e)
            self.taskbar = None

    # ── пасхалка ── #

    def logo_clicked(self):
        if not on("egg"):
            return False
        now = time.monotonic()
        clicks = [c for c in self.__dict__.get("_egg", []) if now - c < 4.0] + [now]
        self._egg = clicks
        if len(clicks) >= 10:
            self._egg = []
            covers = [str(t.get("cover")) for t in self.shell.win.library if t.get("cover")]
            random.shuffle(covers)
            CoverRain(self.shell.window(), covers[:24] or [""])
            return True
        return len(clicks) > 1


def vc_moving(vc) -> bool:
    return isinstance(vc, VinylCover) and vc.moving()


class VinylCover(QLabel):
    """Обложка в плеере, из-за которой выглядывает и крутится пластинка; на паузе — останавливается и уезжает."""
    OUT = 18

    def __init__(self, size, radius=6, parent=None):
        super().__init__(parent)
        self.size_, self.radius = size, radius
        self._path = None
        self._seed = None
        self._k = 0.0
        self._rot = 0.0
        self.fit()

    def fit(self):
        """Место под пластинку — только когда она включена (иначе обычная обложка, как раньше)."""
        self.setFixedSize(self.size_ + (self.OUT if on("vinyl") else 0), self.size_)

    def set_cover(self, path, seed=""):
        if path == self._path and seed == self._seed:
            return
        self._path, self._seed = path, seed
        self.setPixmap(_Y().cover_pixmap(path or "", self.size_, self.radius, seed=seed))
        self.update()

    def moving(self) -> bool:
        return 0.0 < self._k < 1.0

    def wants_tick(self, playing) -> bool:
        return on("vinyl") and (playing or self._k > 0)

    def tick(self, dt, playing) -> bool:
        if not on("vinyl"):
            if self._k:
                self._k = 0.0
                self.update()
            return False
        target = 1.0 if playing else 0.0
        changed = False
        if self._k != target:
            step = dt / 0.45
            self._k = min(target, self._k + step) if target > self._k else max(target, self._k - step)
            changed = True
        if playing:
            self._rot = (self._rot + dt * 200) % 360
            changed = True
        if changed:
            self.update()
        return playing or self.moving()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        s = self.size_
        k = 1 - (1 - self._k) ** 3
        if k > 0.01:
            c = QPointF(s / 2 + self.OUT * k, s / 2)
            R = s / 2 - 2
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(12, 12, 14))
            p.drawEllipse(c, R, R)
            p.setPen(QPen(QColor(255, 255, 255, 16), 0.7))
            p.setBrush(Qt.BrushStyle.NoBrush)
            for rr in range(int(R * 0.45), int(R), 3):
                p.drawEllipse(c, rr, rr)
            p.save()                                           # блик крутится
            p.translate(c)
            p.rotate(self._rot)
            g = QLinearGradient(-R, 0, R, 0)
            g.setColorAt(0.35, QColor(255, 255, 255, 0))
            g.setColorAt(0.5, QColor(255, 255, 255, 34))
            g.setColorAt(0.65, QColor(255, 255, 255, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawEllipse(QPointF(0, 0), R, R)
            p.restore()
            p.setBrush(accent())
            p.drawEllipse(c, R * 0.3, R * 0.3)
            p.setBrush(QColor(0, 0, 0))
            p.drawEllipse(c, 1.6, 1.6)
        pm = self.pixmap()
        if pm is not None and not pm.isNull():
            sh = QRadialGradient(QPointF(s * 0.55, s * 0.55), s * 0.7)
            sh.setColorAt(0.6, QColor(0, 0, 0, 90 if k > 0.01 else 0))
            sh.setColorAt(1, QColor(0, 0, 0, 0))
            p.fillRect(QRectF(0, 0, s + 6, s), sh)
            p.drawPixmap(QRectF(0, 0, s, s), pm, QRectF(pm.rect()))
        p.end()
