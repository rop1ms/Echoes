# net_frames.py
"""
Рамки аватарок Echoes.NET.

  * за ачивки — у каждой ачивки своя рамка (виниловая у «Диджея», огненная у «Хитмейкера», корона у
    «Своей тусовки»…), выбрать можно только полученную;
  * за роль — у администратора золотое солнце, у модератора синяя рамка (ставятся сами, если своя не выбрана);
  * своя — загрузить картинку (середина вырезается под фото) или нарисовать прямо в ECHOES:
    кисть, ластик, симметрия по кругу (1–12 лучей), свечение, заливка кольца, отмена.

Рамка хранится в профиле: {"id": "ach:dj"} | {"id": "role"} | {"id": "custom", "png": base64 PNG ≤ 16 КБ}
и доходит друзьям вместе с карточкой профиля, а всем остальным — публичным событием echoes-deco.
Чужую ачивочную рамку без самой ачивки не показываем.
"""
from __future__ import annotations

import base64
import math

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (QBrush, QColor, QConicalGradient, QFont, QImage, QLinearGradient, QPainter, QPainterPath,
                         QPen, QPixmap, QRadialGradient)
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QColorDialog, QDialog, QFileDialog, QGridLayout, QHBoxLayout,
                             QLabel, QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget)

from raster_budget import ByteLRU

MAX_PNG = 16000                      # base64 своей рамки
INSET = 0.11                         # фото внутри рамки уменьшается на столько с каждой стороны

ACH_FRAMES = {                       # ачивка: подпись рамки
    "first_post": "Серебро", "author": "Чернила", "social": "Радуга", "dj": "Винил", "together": "Две орбиты",
    "inseparable": "Сердца", "sleuth": "Шерлок", "hitmaker": "Огонь", "melomane": "Золотые ноты",
    "collector": "Самоцветы", "group": "Корона", "champion": "Кубок", "night_owl": "Полночь",
    "early_bird": "Рассвет", "streak7": "Семь огней", "explorer": "Компас", "loyal": "Сердце фаната",
    "marathon": "Секундомер",
}
ROLE_FRAMES = {"admin": "Золотое солнце", "mod": "Синяя рамка модератора"}


def _season_on(key, t=None) -> bool:
    import time as _t
    lt = _t.localtime(t or _t.time())
    md = lt.tm_mon * 100 + lt.tm_mday
    return {"halloween": 1015 <= md <= 1105, "newyear": md >= 1220 or md <= 110,
            "winter": lt.tm_mon in (12, 1, 2), "spring": lt.tm_mon in (3, 4, 5),
            "summer": lt.tm_mon in (6, 7, 8)}.get(key, False)


SEASON_FRAMES = {"halloween": ("Хеллоуин", "15 октября — 5 ноября"), "newyear": ("Новый год", "20 декабря — 10 января"),
                 "winter": ("Зима", "декабрь — февраль"), "spring": ("Весна", "март — май"),
                 "summer": ("Лето", "июнь — август")}

RESOLVER = None                      # key (onion/npub) → (spec, ach, role) — ставит Echoes.NET
_CACHE = ByteLRU(4 * 2**20)


def png_b64(img: QImage, limit=MAX_PNG) -> str:
    for side in (160, 136, 120, 104, 96):
        im = img.scaled(side, side, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        for fmt in (QImage.Format.Format_ARGB32, QImage.Format.Format_Indexed8):
            src = im.convertToFormat(fmt) if fmt != QImage.Format.Format_ARGB32 else im
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            src.save(buf, "PNG", 9)
            b = base64.b64encode(bytes(ba)).decode()
            if len(b) <= limit:
                return b
    return ""


FRAME_ANIMS = {"": "Без анимации", "pulse": "Пульс", "spin": "Вращение", "glow": "Сияние", "beat": "Под музыку"}
ENGINE = None                        # плеер (net_page ставит) — для «под музыку»
_LVL = [0.0]


def music_level() -> float:
    """Громкость играющей музыки 0..1 (сглаженная: быстрый подъём, плавный спад)."""
    raw = 0.0
    try:
        if ENGINE is not None and ENGINE.is_playing():
            raw = min(1.0, float(ENGINE.get_level()) * 4.0)
    except Exception:                                          # noqa: BLE001
        raw = 0.0
    _LVL[0] = raw if raw > _LVL[0] else _LVL[0] * 0.85 + raw * 0.15
    return _LVL[0]


def clean_spec(spec) -> dict:
    out = _clean_spec(spec)
    a = spec.get("anim") if isinstance(spec, dict) else ""
    if out and out.get("id") != "none" and a in FRAME_ANIMS and a:
        out["anim"] = a
    return out


def _clean_spec(spec) -> dict:
    if not isinstance(spec, dict):
        return {}
    fid = str(spec.get("id") or "")[:40]
    if fid == "custom":
        png = spec.get("png")
        if isinstance(png, str) and len(png) <= MAX_PNG:
            try:
                if base64.b64decode(png)[:8] == b"\x89PNG\r\n\x1a\n":
                    return {"id": "custom", "png": png}
            except ValueError:
                pass
        return {}
    if fid == "role" or (fid.startswith("ach:") and fid[4:] in ACH_FRAMES) or fid == "none" or \
            (fid.startswith("season:") and fid[7:] in SEASON_FRAMES):
        return {"id": fid}
    import net_cosmetics                                       # рамки Phantom: бесплатные и для спонсоров
    if (fid.startswith("ph:") and fid[3:] in net_cosmetics.FREE) or \
            (fid.startswith("sp:") and fid[3:] in net_cosmetics.SPONSOR):
        return {"id": fid}
    return {}


def _ph() -> bool:
    try:
        import ya_skin
        return bool(ya_skin.PHANTOM_ON)
    except Exception:                                          # noqa: BLE001
        return False


def ph_animated(spec) -> bool:
    """Вид Phantom: у встроенных рамок своя анимация (если не выбрана другая)."""
    if not _ph() or not spec or spec.get("anim"):
        return False
    import net_cosmetics
    return net_cosmetics.has(net_cosmetics.kind_of(spec))


def effective(spec, ach=(), role="") -> dict:
    """Какая рамка видна: ачивочная — только если ачивка есть; без своей — рамка роли."""
    spec = clean_spec(spec)
    fid = spec.get("id", "")
    if fid.startswith("ach:") and fid[4:] not in set(ach or ()):
        spec, fid = {}, ""
    if fid.startswith("sp:") and "__sponsor__" not in set(ach or ()):   # рамки спонсоров — только у спонсоров
        spec, fid = {}, ""
    if fid == "role" and role not in ROLE_FRAMES:
        spec, fid = {}, ""
    if not fid and role in ROLE_FRAMES:
        return {"id": "role", "role": role}
    if fid == "role":
        return {"id": "role", "role": role}
    if fid == "none":
        return {}
    return spec


# ══════════════════════════ встроенные рамки ══════════════════════════ #

def _ring(p, c, R, w, brush):
    path = QPainterPath()
    path.addEllipse(c, R, R)
    inner = QPainterPath()
    inner.addEllipse(c, R - w, R - w)
    p.fillPath(path.subtracted(inner), brush)


def _sparkle(p, x, y, r, col):
    path = QPainterPath()
    path.moveTo(x, y - r)
    path.quadTo(x, y, x + r, y)
    path.quadTo(x, y, x, y + r)
    path.quadTo(x, y, x - r, y)
    path.quadTo(x, y, x, y - r)
    p.fillPath(path, col)


def _heart(p, x, y, s, col):
    path = QPainterPath()
    path.moveTo(x, y + s * 0.35)
    path.cubicTo(x - s * 0.9, y - s * 0.25, x - s * 0.35, y - s * 0.95, x, y - s * 0.35)
    path.cubicTo(x + s * 0.35, y - s * 0.95, x + s * 0.9, y - s * 0.25, x, y + s * 0.35)
    p.fillPath(path, col)


def _note(p, x, y, s, col):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    p.drawEllipse(QPointF(x, y), s * 0.32, s * 0.24)
    p.fillRect(QRectF(x + s * 0.22, y - s * 0.95, s * 0.11, s * 0.95), col)
    path = QPainterPath()
    path.moveTo(x + s * 0.33, y - s * 0.95)
    path.quadTo(x + s * 0.75, y - s * 0.7, x + s * 0.6, y - s * 0.35)
    path.quadTo(x + s * 0.6, y - s * 0.62, x + s * 0.33, y - s * 0.7)
    p.fillPath(path, col)


def draw_builtin(p: QPainter, kind: str, S: float):
    """Нарисовать встроенную рамку размером S×S (центр — середина)."""
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if _ph():                                                  # Phantom: стекло и серебро вместо неона
        import net_cosmetics
        if net_cosmetics.draw(p, kind, S, 0.0):
            return
    c = QPointF(S / 2, S / 2)
    R = S / 2 - S * 0.01
    w = S * 0.085
    if kind == "first_post":
        g = QConicalGradient(c, 40)
        for pos, col in ((0, "#f4f6fa"), (0.25, "#8d96a6"), (0.5, "#ffffff"), (0.75, "#7b8494"), (1, "#f4f6fa")):
            g.setColorAt(pos, QColor(col))
        _ring(p, c, R, w, QBrush(g))
        _sparkle(p, S * 0.8, S * 0.17, S * 0.07, QColor("#ffffff"))
    elif kind == "author":
        _ring(p, c, R, w, QColor("#1d2a5c"))
        for i in range(12):
            a = i * math.pi / 6
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#7fa3ff") if i % 3 else QColor("#ffffff"))
            p.drawEllipse(QPointF(c.x() + math.cos(a) * (R - w / 2), c.y() + math.sin(a) * (R - w / 2)),
                          S * 0.014 * (1.6 if i % 3 == 0 else 1), S * 0.014 * (1.6 if i % 3 == 0 else 1))
    elif kind == "social":
        g = QConicalGradient(c, 90)
        for i, col in enumerate(("#ff4d4d", "#ffb84d", "#ffef4d", "#4dff88", "#4dd2ff", "#8a4dff", "#ff4dd2",
                                 "#ff4d4d")):
            g.setColorAt(i / 7, QColor(col))
        _ring(p, c, R, w, QBrush(g))
    elif kind == "dj":
        _ring(p, c, R, w * 1.25, QColor("#0d0d0f"))
        p.setPen(QPen(QColor(255, 255, 255, 40), max(0.6, S * 0.004)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for k in range(1, 5):
            p.drawEllipse(c, R - k * w * 0.25, R - k * w * 0.25)
        p.setPen(QPen(QColor(255, 255, 255, 110), S * 0.012))
        p.drawArc(QRectF(c.x() - R + w * 0.6, c.y() - R + w * 0.6, 2 * R - w * 1.2, 2 * R - w * 1.2), 30 * 16, 50 * 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ffdb1a"))
        p.drawEllipse(QPointF(c.x() + R * 0.72, c.y() + R * 0.72), S * 0.07, S * 0.07)
        p.setBrush(QColor("#0d0d0f"))
        p.drawEllipse(QPointF(c.x() + R * 0.72, c.y() + R * 0.72), S * 0.018, S * 0.018)
    elif kind == "together":
        for dx, col in ((-S * 0.012, "#ff5fa8"), (S * 0.012, "#4dd2ff")):
            p.setPen(QPen(QColor(col), w * 0.45))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(c.x() + dx, c.y() - dx), R - w * 0.4, R - w * 0.4)
    elif kind == "inseparable":
        _ring(p, c, R, w * 0.55, QColor("#ff5fa8"))
        for i in range(6):
            a = i * math.pi / 3 - math.pi / 2
            _heart(p, c.x() + math.cos(a) * (R - w * 0.3), c.y() + math.sin(a) * (R - w * 0.3), S * 0.075,
                   QColor("#ff2f7d"))
    elif kind == "sleuth":
        p.setPen(QPen(QColor("#c9a46a"), w * 0.5, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, R - w * 0.35, R - w * 0.35)
        mx, my = c.x() + R * 0.66, c.y() + R * 0.66
        p.setPen(QPen(QColor("#5a4026"), S * 0.035, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(mx + S * 0.05, my + S * 0.05), QPointF(mx + S * 0.13, my + S * 0.13))
        p.setPen(QPen(QColor("#e8d2a8"), S * 0.02))
        p.setBrush(QColor(200, 230, 255, 90))
        p.drawEllipse(QPointF(mx, my), S * 0.07, S * 0.07)
    elif kind == "hitmaker":
        n = 18
        path = QPainterPath()
        for i in range(n * 2 + 1):
            a = i * math.pi / n - math.pi / 2
            r = R if i % 2 == 0 else R - w * 0.9
            pt = QPointF(c.x() + math.cos(a) * r, c.y() + math.sin(a) * r)
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        inner = QPainterPath()
        inner.addEllipse(c, R - w * 1.2, R - w * 1.2)
        g = QRadialGradient(c, R)
        g.setColorAt(0.75, QColor("#ffd23f"))
        g.setColorAt(0.88, QColor("#ff7a1a"))
        g.setColorAt(1.0, QColor("#e3261b"))
        p.fillPath(path.subtracted(inner), g)
    elif kind == "melomane":
        g = QLinearGradient(0, 0, S, S)
        g.setColorAt(0, QColor("#fff1a6"))
        g.setColorAt(0.5, QColor("#d6a21e"))
        g.setColorAt(1, QColor("#fff1a6"))
        _ring(p, c, R, w * 0.6, QBrush(g))
        for i in range(5):
            a = -math.pi / 2 + (i - 2) * 0.42
            _note(p, c.x() + math.cos(a) * (R - w * 0.35), c.y() + math.sin(a) * (R - w * 0.35) + S * 0.02,
                  S * 0.09, QColor("#ffd84a"))
    elif kind == "collector":
        _ring(p, c, R, w * 0.6, QColor("#3b1d6e"))
        for i in range(8):
            a = i * math.pi / 4
            x, y = c.x() + math.cos(a) * (R - w * 0.3), c.y() + math.sin(a) * (R - w * 0.3)
            s = S * 0.045
            gem = QPainterPath()
            gem.moveTo(x, y - s); gem.lineTo(x + s * 0.8, y); gem.lineTo(x, y + s); gem.lineTo(x - s * 0.8, y)
            gem.closeSubpath()
            gg = QLinearGradient(x - s, y - s, x + s, y + s)
            col = ("#c77dff", "#4dd2ff", "#ff5fa8", "#7dffb0")[i % 4]
            gg.setColorAt(0, QColor("#ffffff"))
            gg.setColorAt(0.4, QColor(col))
            gg.setColorAt(1, QColor(col).darker(160))
            p.fillPath(gem, gg)
    elif kind == "group":
        _ring(p, c, R, w * 0.55, QColor("#2fbf71"))
        x, y, s = c.x(), c.y() - R + S * 0.02, S * 0.12
        crown = QPainterPath()
        crown.moveTo(x - s, y + s * 0.5)
        for k, (dx, dy) in enumerate(((-s, -s * 0.4), (-s * 0.5, s * 0.1), (0, -s * 0.6), (s * 0.5, s * 0.1),
                                      (s, -s * 0.4), (s, s * 0.5))):
            crown.lineTo(x + dx, y + dy)
        crown.closeSubpath()
        cg = QLinearGradient(x, y - s, x, y + s)
        cg.setColorAt(0, QColor("#fff3a0"))
        cg.setColorAt(1, QColor("#e0a800"))
        p.fillPath(crown, cg)
    elif kind == "champion":                                   # кубок: золотое кольцо, лавровые ветви, кубок внизу
        g = QConicalGradient(c, 90)
        for pos, col in ((0, "#fff3a0"), (0.25, "#e0a800"), (0.5, "#fff3a0"), (0.75, "#c08a00"), (1, "#fff3a0")):
            g.setColorAt(pos, QColor(col))
        _ring(p, c, R, w * 0.6, QBrush(g))
        for side in (-1, 1):                                   # листья
            for j in range(6):
                a = math.pi / 2 + side * (0.35 + j * 0.2)
                x, y = c.x() + math.cos(a) * (R - w * 0.3), c.y() + math.sin(a) * (R - w * 0.3)
                leaf = QPainterPath()
                leaf.addEllipse(QPointF(x, y), S * 0.026, S * 0.012)
                p.save()
                p.translate(x, y)
                p.rotate(math.degrees(a) + 90)
                p.translate(-x, -y)
                p.fillPath(leaf, QColor("#7ddc6a"))
                p.restore()
        x, y, s = c.x(), c.y() + R - S * 0.02, S * 0.09
        cup = QPainterPath()
        cup.moveTo(x - s, y - s * 1.1)
        cup.lineTo(x + s, y - s * 1.1)
        cup.quadTo(x + s * 0.9, y - s * 0.1, x, y)
        cup.quadTo(x - s * 0.9, y - s * 0.1, x - s, y - s * 1.1)
        cg = QLinearGradient(x - s, y, x + s, y)
        cg.setColorAt(0, QColor("#ffe066"))
        cg.setColorAt(1, QColor("#c08a00"))
        p.fillPath(cup, cg)
        p.fillRect(QRectF(x - s * 0.12, y, s * 0.24, s * 0.35), QColor("#c08a00"))
        p.fillRect(QRectF(x - s * 0.5, y + s * 0.35, s, s * 0.18), QColor("#e0a800"))
    elif kind == "night_owl":                                  # полночь: тёмно-синее кольцо, луна и звёзды
        _ring(p, c, R, w * 0.7, QColor("#16245a"))
        moon = QPainterPath()
        moon.addEllipse(QPointF(c.x() + R * 0.62, c.y() - R * 0.62), S * 0.08, S * 0.08)
        cut = QPainterPath()
        cut.addEllipse(QPointF(c.x() + R * 0.62 + S * 0.035, c.y() - R * 0.62 - S * 0.02), S * 0.07, S * 0.07)
        p.fillPath(moon.subtracted(cut), QColor("#ffe58a"))
        for i in range(7):
            a = math.pi * 0.7 + i * 0.32
            _sparkle(p, c.x() + math.cos(a) * (R - w * 0.35), c.y() + math.sin(a) * (R - w * 0.35), S * 0.025,
                     QColor("#dfe8ff"))
    elif kind == "early_bird":                                 # рассвет: тёплый градиент снизу вверх
        g = QLinearGradient(0, S, 0, 0)
        g.setColorAt(0, QColor("#ff7a3d"))
        g.setColorAt(0.5, QColor("#ffc06b"))
        g.setColorAt(1, QColor("#8fc9ff"))
        _ring(p, c, R, w * 0.65, QBrush(g))
        for i in range(9):
            a = math.pi + i * math.pi / 8
            p.setPen(QPen(QColor(255, 220, 140, 200), S * 0.012))
            p.drawLine(QPointF(c.x() + math.cos(a) * (R - w * 0.05), c.y() + math.sin(a) * (R - w * 0.05)),
                       QPointF(c.x() + math.cos(a) * (R + 0.0), c.y() + math.sin(a) * (R + 0.0)))
    elif kind == "streak7":                                    # семь огней по кругу
        _ring(p, c, R, w * 0.45, QColor("#3a1608"))
        for i in range(7):
            a = -math.pi / 2 + i * 2 * math.pi / 7
            x, y, s = c.x() + math.cos(a) * (R - w * 0.25), c.y() + math.sin(a) * (R - w * 0.25), S * 0.05
            fl = QPainterPath()
            fl.moveTo(x, y - s)
            fl.cubicTo(x + s * 0.9, y - s * 0.2, x + s * 0.7, y + s, x, y + s)
            fl.cubicTo(x - s * 0.7, y + s, x - s * 0.9, y - s * 0.2, x, y - s)
            fg = QLinearGradient(x, y - s, x, y + s)
            fg.setColorAt(0, QColor("#ffe066"))
            fg.setColorAt(1, QColor("#ff5a1f"))
            p.fillPath(fl, fg)
    elif kind == "explorer":                                   # компас: деления и стрелка
        _ring(p, c, R, w * 0.6, QColor("#1f4a3a"))
        p.setPen(QPen(QColor("#bff5d8"), S * 0.008))
        for i in range(24):
            a = i * math.pi / 12
            l = w * (0.45 if i % 6 == 0 else 0.25)
            p.drawLine(QPointF(c.x() + math.cos(a) * (R - w * 0.1), c.y() + math.sin(a) * (R - w * 0.1)),
                       QPointF(c.x() + math.cos(a) * (R - w * 0.1 - l), c.y() + math.sin(a) * (R - w * 0.1 - l)))
        nd = QPainterPath()
        nd.moveTo(c.x(), c.y() - R + w * 0.05)
        nd.lineTo(c.x() + S * 0.025, c.y() - R + w * 0.75)
        nd.lineTo(c.x() - S * 0.025, c.y() - R + w * 0.75)
        nd.closeSubpath()
        p.fillPath(nd, QColor("#ff4d4d"))
    elif kind == "loyal":                                      # сердце фаната: фиолетовое кольцо, большое сердце внизу
        _ring(p, c, R, w * 0.55, QColor("#7a2cff"))
        _heart(p, c.x(), c.y() + R - S * 0.04, S * 0.11, QColor("#ff3d8b"))
    elif kind == "marathon":                                   # секундомер: кольцо-циферблат, кнопка сверху
        _ring(p, c, R, w * 0.55, QColor("#d9dde6"))
        p.setPen(QPen(QColor("#30343c"), S * 0.01))
        for i in range(12):
            a = i * math.pi / 6
            p.drawLine(QPointF(c.x() + math.cos(a) * (R - w * 0.08), c.y() + math.sin(a) * (R - w * 0.08)),
                       QPointF(c.x() + math.cos(a) * (R - w * 0.42), c.y() + math.sin(a) * (R - w * 0.42)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#d9dde6"))
        p.drawRoundedRect(QRectF(c.x() - S * 0.04, c.y() - R - S * 0.03, S * 0.08, S * 0.06), 3, 3)
    elif kind.startswith("season:"):                           # сезонные
        sk = kind[7:]
        if sk == "halloween":
            _ring(p, c, R, w * 0.6, QColor("#2a1240"))
            for i in range(5):
                a = -math.pi / 2 + i * 2 * math.pi / 5
                x, y, s = c.x() + math.cos(a) * (R - w * 0.3), c.y() + math.sin(a) * (R - w * 0.3), S * 0.055
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#ff7a1a"))
                p.drawEllipse(QPointF(x, y), s, s * 0.85)
                p.setBrush(QColor("#3a6b1a"))
                p.drawRect(QRectF(x - s * 0.12, y - s * 1.05, s * 0.24, s * 0.3))
        elif sk == "newyear":
            _ring(p, c, R, w * 0.35, QColor("#1f5a2e"))
            cols = ("#ff3b3b", "#ffdb1a", "#2fc6ff", "#7ddc6a", "#ff5fa8")
            for i in range(16):
                a = i * math.pi / 8
                p.setPen(Qt.PenStyle.NoPen)
                gl = QRadialGradient(QPointF(c.x() + math.cos(a) * (R - w * 0.17), c.y() + math.sin(a) * (R - w * 0.17)),
                                     S * 0.035)
                col = QColor(cols[i % len(cols)])
                gl.setColorAt(0, col)
                col.setAlpha(0)
                gl.setColorAt(1, col)
                p.setBrush(gl)
                p.drawEllipse(QPointF(c.x() + math.cos(a) * (R - w * 0.17), c.y() + math.sin(a) * (R - w * 0.17)),
                              S * 0.035, S * 0.035)
        elif sk == "winter":
            g = QConicalGradient(c, 90)
            for pos, col in ((0, "#e8f6ff"), (0.5, "#8fd3ff"), (1, "#e8f6ff")):
                g.setColorAt(pos, QColor(col))
            _ring(p, c, R, w * 0.5, QBrush(g))
            p.setPen(QPen(QColor("#ffffff"), S * 0.008))
            for i in range(8):
                a = i * math.pi / 4
                x, y, s = c.x() + math.cos(a) * (R - w * 0.25), c.y() + math.sin(a) * (R - w * 0.25), S * 0.035
                for k in range(3):
                    b = k * math.pi / 3
                    p.drawLine(QPointF(x - math.cos(b) * s, y - math.sin(b) * s), QPointF(x + math.cos(b) * s, y + math.sin(b) * s))
        elif sk == "spring":
            _ring(p, c, R, w * 0.45, QColor("#7ddc6a"))
            for i in range(7):
                a = -math.pi / 2 + i * 2 * math.pi / 7
                x, y = c.x() + math.cos(a) * (R - w * 0.25), c.y() + math.sin(a) * (R - w * 0.25)
                for k in range(5):
                    b = k * 2 * math.pi / 5
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor("#ffc1dc"))
                    p.drawEllipse(QPointF(x + math.cos(b) * S * 0.02, y + math.sin(b) * S * 0.02), S * 0.018, S * 0.018)
                p.setBrush(QColor("#ffdb1a"))
                p.drawEllipse(QPointF(x, y), S * 0.012, S * 0.012)
        elif sk == "summer":
            g = QRadialGradient(c, R)
            g.setColorAt(0.8, QColor("#ffd23f"))
            g.setColorAt(1.0, QColor("#ff8a00"))
            _ring(p, c, R, w * 0.55, QBrush(g))
            p.setPen(QPen(QColor(255, 200, 60, 220), S * 0.012, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            for i in range(16):
                a = i * math.pi / 8
                p.drawLine(QPointF(c.x() + math.cos(a) * (R - w * 0.6), c.y() + math.sin(a) * (R - w * 0.6)),
                           QPointF(c.x() + math.cos(a) * (R - w * 0.9), c.y() + math.sin(a) * (R - w * 0.9)))
    elif kind == "admin":                                      # золотое солнце — колючие лучи как у логотипа
        n = 22
        path = QPainterPath()
        for i in range(n * 2 + 1):
            a = i * math.pi / n - math.pi / 2
            r = R if i % 2 == 0 else R - w * 0.75
            pt = QPointF(c.x() + math.cos(a) * r, c.y() + math.sin(a) * r)
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        inner = QPainterPath()
        inner.addEllipse(c, R - w * 1.05, R - w * 1.05)
        g = QRadialGradient(c, R)
        g.setColorAt(0.7, QColor("#fff27a"))
        g.setColorAt(0.9, QColor("#ffcc00"))
        g.setColorAt(1.0, QColor("#ff9d00"))
        p.fillPath(path.subtracted(inner), g)
    elif kind == "mod":
        g = QLinearGradient(0, 0, S, S)
        g.setColorAt(0, QColor("#9fd0ff"))
        g.setColorAt(0.5, QColor("#2f7bff"))
        g.setColorAt(1, QColor("#9fd0ff"))
        _ring(p, c, R, w * 0.55, QBrush(g))
        p.setPen(QPen(QColor(120, 180, 255, 120), S * 0.012))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, R - w * 0.85, R - w * 0.85)


def frame_pixmap(spec: dict, size: int) -> QPixmap | None:
    """Рамка в 2× для экрана (кэш)."""
    if not spec:
        return None
    fid = spec.get("id", "")
    png = spec.get("png") or ""
    key = (fid, spec.get("role", ""), png, size)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    dpr = 2
    pm = QPixmap(size * dpr, size * dpr)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    if fid == "custom":
        img = QImage()
        try:
            img.loadFromData(base64.b64decode(png), "PNG")
        except ValueError:
            pass
        if img.isNull():
            p.end()
            return None
        p.drawImage(QRectF(0, 0, size, size), img)
    elif fid == "role":
        draw_builtin(p, spec.get("role", ""), size)
    elif fid.startswith("ach:"):
        draw_builtin(p, fid[4:], size)
    elif fid.startswith("season:"):
        draw_builtin(p, fid, size)
    elif fid.startswith(("ph:", "sp:")):
        import net_cosmetics
        net_cosmetics.draw(p, fid[3:], size, 0.0)
    else:
        p.end()
        return None
    p.end()
    _CACHE.put(key, pm, pm.width() * pm.height() * 4 + len(png))
    return pm


def overlay_for(key: str, size: int) -> QPixmap | None:
    """Рамка для аватарки человека (по onion/npub) — через RESOLVER Echoes.NET."""
    if RESOLVER is None or not key:
        return None
    try:
        r = RESOLVER(key)
    except Exception:                                          # noqa: BLE001
        return None
    if not r:
        return None
    spec, ach, role = r
    eff = effective(spec, ach, role)
    return frame_pixmap(eff, size) if eff else None


def framed_anim(avatar: QPixmap, spec: dict, size: int, t: float) -> QPixmap:
    """Кадр анимированной рамки: аватарка на месте, рамка пульсирует / вращается / сияет / качается под музыку."""
    import math
    a = (spec or {}).get("anim") or ""
    if not a and ph_animated(spec):                            # своя анимация рамки Phantom
        import net_cosmetics
        dpr = 2
        pm = QPixmap(size * dpr, size * dpr)
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        ins = size * INSET
        if not avatar.isNull():                                # аватарка в нужном размере — один раз, не в каждом кадре
            key = (avatar.cacheKey(), size)
            av = _AV_SCALED.get(key)
            if av is None:
                side = int(round((size - 2 * ins) * dpr))
                av = avatar.scaled(side, side, Qt.AspectRatioMode.IgnoreAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
                if len(_AV_SCALED) > 40:
                    _AV_SCALED.clear()
                _AV_SCALED[key] = av
            p.drawPixmap(QRectF(ins, ins, size - 2 * ins, size - 2 * ins), av, QRectF(av.rect()))
        net_cosmetics.draw(p, net_cosmetics.kind_of(spec), size, t)
        p.end()
        return pm
    if not a:
        return framed(avatar, spec, size)
    dpr = 2
    pm = QPixmap(size * dpr, size * dpr)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    fr = frame_pixmap({k: v for k, v in spec.items() if k != "anim"}, size)
    ins = size * INSET if fr is not None else 0.0
    if not avatar.isNull():
        p.drawPixmap(QRectF(ins, ins, size - 2 * ins, size - 2 * ins), avatar, QRectF(avatar.rect()))
    if fr is not None:
        c = size / 2
        p.translate(c, c)
        glow = 0.0
        if a == "pulse":
            s = 1 + 0.035 * math.sin(t * 2 * math.pi / 1.6)
            p.scale(s, s)
        elif a == "spin":
            p.rotate((t * 40) % 360)
        elif a == "beat":
            lv = music_level()
            s = 1 + 0.09 * lv
            p.scale(s, s)
            glow = lv
        elif a == "glow":
            glow = 0.5 + 0.5 * math.sin(t * 2 * math.pi / 2.2)
        p.translate(-c, -c)
        if glow > 0.02:                                        # ореол: увеличенная полупрозрачная копия
            p.save()
            p.setOpacity(0.45 * glow)
            p.translate(c, c)
            p.scale(1.07, 1.07)
            p.translate(-c, -c)
            p.drawPixmap(QRectF(0, 0, size, size), fr, QRectF(fr.rect()))
            p.restore()
        p.drawPixmap(QRectF(0, 0, size, size), fr, QRectF(fr.rect()))
        if glow > 0.02:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            p.setOpacity(0.35 * glow)
            p.drawPixmap(QRectF(0, 0, size, size), fr, QRectF(fr.rect()))
    p.end()
    return pm


def animate_label(label, avatar: QPixmap, spec: dict, size: int, anim_path: str = ""):
    """Живая рамка и/или анимированная аватарка (ya_avanim) на QLabel (шапка профиля, предпросмотр):
    ~30 кадров/с, пока виджет виден."""
    import time
    from PyQt6.QtCore import QTimer
    old = getattr(label, "_frame_anim", None)
    if old is not None:
        old.stop()
        old.deleteLater()
        label._frame_anim = None
    oldm = getattr(label, "_av_movie", None)
    if oldm is not None:
        oldm.stop()
        oldm.deleteLater()
        label._av_movie = None
    mv = None
    if anim_path:
        import ya_avanim
        mv = ya_avanim.movie(anim_path, label)
        label._av_movie = mv
    spec = spec or {}
    live = bool(spec.get("anim")) or ph_animated(spec)
    if not live and mv is None:
        label.setPixmap(framed(avatar, spec, size))
        return
    t0 = time.monotonic()
    tm = QTimer(label)
    tm.setInterval(33)

    def frame(t):
        av = avatar
        if mv is not None:
            import ya_avanim
            av = ya_avanim.circle(mv.currentImage(), size)
        return framed_anim(av, spec, size, t) if live else framed(av, spec, size)

    def tick():
        try:
            if label.isVisible() and label.window().isVisible():
                label.setPixmap(frame(time.monotonic() - t0))
        except RuntimeError:
            tm.stop()
    tm.timeout.connect(tick)
    tm.start()
    label._frame_anim = tm
    label.setPixmap(frame(0.0))


_AV_SCALED: dict = {}
_FRAMED: dict = {}


def framed(avatar: QPixmap, spec: dict, size: int) -> QPixmap:
    """Готовая аватарка + рамка (для предпросмотра). Кэш: магазин и окно рамок просят одно и то же много раз."""
    key = (avatar.cacheKey(), (spec or {}).get("id", ""), (spec or {}).get("role", ""),
           len((spec or {}).get("png") or ""), size)
    hit = _FRAMED.get(key)
    if hit is not None:
        return hit
    pm = _framed(avatar, spec, size)
    if len(_FRAMED) > 200:
        _FRAMED.clear()
    _FRAMED[key] = pm
    return pm


def _framed(avatar: QPixmap, spec: dict, size: int) -> QPixmap:
    dpr = 2
    pm = QPixmap(size * dpr, size * dpr)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    fr = frame_pixmap(spec, size) if spec else None
    ins = size * INSET if fr is not None else 0
    p.drawPixmap(QRectF(ins, ins, size - 2 * ins, size - 2 * ins), avatar, QRectF(avatar.rect()))
    if fr is not None:
        p.drawPixmap(QRectF(0, 0, size, size), fr, QRectF(fr.rect()))
    p.end()
    return pm


def cut_center(img: QImage) -> QImage:
    """Загруженная картинка → рамка: квадрат по центру, середина прозрачная (там будет фото)."""
    side = min(img.width(), img.height())
    img = img.copy((img.width() - side) // 2, (img.height() - side) // 2, side, side)
    out = QImage(320, 320, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(0)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    ring = QPainterPath()
    ring.addEllipse(QPointF(160, 160), 160, 160)
    hole = QPainterPath()
    hole.addEllipse(QPointF(160, 160), 160 * (0.5 - INSET) * 2 - 2, 160 * (0.5 - INSET) * 2 - 2)
    if not img.hasAlphaChannel() or _opaque_center(img):
        p.setClipPath(ring.subtracted(hole))
    p.drawImage(QRectF(0, 0, 320, 320), img)
    p.end()
    return out


def _opaque_center(img: QImage) -> bool:
    c = img.pixelColor(img.width() // 2, img.height() // 2)
    return c.alpha() > 200


# ══════════════════════════ рисовалка ══════════════════════════ #

class DrawCanvas(QWidget):
    """Холст 320×320: кольцо-подсказка, своё фото в середине; кисть с симметрией по кругу."""
    changed = pyqtSignal()
    N = 320

    def __init__(self, avatar: QPixmap, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.N + 40, self.N + 40)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.avatar = avatar
        self.img = QImage(self.N, self.N, QImage.Format.Format_ARGB32_Premultiplied)
        self.img.fill(0)
        self.undo = []
        self.color = QColor("#ffdb1a")
        self.width_ = 14
        self.sym = 1                     # без зеркала; симметрию включают кнопками 2–12
        self.eraser = False
        self.glow = True
        self.protect = True
        self._last = None

    def _push(self):
        self.undo.append(self.img.copy())
        del self.undo[:-25]

    def do_undo(self):
        if self.undo:
            self.img = self.undo.pop()
            self.update()
            self.changed.emit()

    def clear(self):
        self._push()
        self.img.fill(0)
        self.update()
        self.changed.emit()

    def set_image(self, img: QImage):
        self._push()
        self.img = img.scaled(self.N, self.N, Qt.AspectRatioMode.IgnoreAspectRatio,
                              Qt.TransformationMode.SmoothTransformation).convertToFormat(
            QImage.Format.Format_ARGB32_Premultiplied)
        self.update()
        self.changed.emit()

    def fill_ring(self, gradient=False):
        self._push()
        p = QPainter(self.img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.N / 2, self.N / 2)
        R = self.N / 2 - 2
        w = self.N * 0.09
        if gradient:
            g = QConicalGradient(c, 90)
            h, s, v, _ = self.color.getHsvF()
            for i in range(7):
                g.setColorAt(i / 6, QColor.fromHsvF(((h if h >= 0 else 0) + i * 0.08) % 1.0, max(0.5, s), max(0.7, v)))
            _ring(p, c, R, w, QBrush(g))
        else:
            _ring(p, c, R, w, self.color)
        p.end()
        self.update()
        self.changed.emit()

    def _to_img(self, pos) -> QPointF:
        return QPointF(pos.x() - 20, pos.y() - 20)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._push()
            self._last = self._to_img(e.position())
            self._stroke(self._last, self._last)

    def mouseMoveEvent(self, e):
        if self._last is not None:
            pt = self._to_img(e.position())
            self._stroke(self._last, pt)
            self._last = pt

    def mouseReleaseEvent(self, e):
        if self._last is not None:
            self._last = None
            self.changed.emit()

    def _stroke(self, a: QPointF, b: QPointF):
        p = QPainter(self.img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.N / 2, self.N / 2)
        if self.protect:                                       # середина — под фото
            clip = QPainterPath()
            clip.addRect(QRectF(0, 0, self.N, self.N))
            hole = QPainterPath()
            r = self.N * (0.5 - INSET) - 1
            hole.addEllipse(c, r, r)
            p.setClipPath(clip.subtracted(hole))
        if self.eraser:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        n = max(1, self.sym)
        for k in range(n):
            p.save()
            p.translate(c)
            p.rotate(360.0 * k / n)
            p.translate(-c)
            if self.glow and not self.eraser:
                gc = QColor(self.color)
                gc.setAlpha(60)
                p.setPen(QPen(gc, self.width_ * 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                              Qt.PenJoinStyle.RoundJoin))
                p.drawLine(a, b)
            p.setPen(QPen(self.color if not self.eraser else QColor(0, 0, 0), self.width_, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawLine(a, b)
            p.restore()
        p.end()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(24, 24, 27))
        for y in range(0, self.height(), 16):                 # «шахматка» прозрачности
            for x in range(0, self.width(), 16):
                if (x + y) // 16 % 2:
                    p.fillRect(x, y, 16, 16, QColor(30, 30, 34))
        o = QPointF(20, 20)
        N = self.N
        ins = N * INSET
        p.drawPixmap(QRectF(o.x() + ins, o.y() + ins, N - 2 * ins, N - 2 * ins), self.avatar,
                     QRectF(self.avatar.rect()))
        p.drawImage(QRectF(o.x(), o.y(), N, N), self.img)
        p.setPen(QPen(QColor(255, 255, 255, 50), 1, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(o.x() + N / 2, o.y() + N / 2), N / 2, N / 2)
        p.drawEllipse(QPointF(o.x() + N / 2, o.y() + N / 2), N / 2 - ins, N / 2 - ins)
        if self.sym > 1:                                       # оси симметрии
            p.setPen(QPen(QColor(255, 255, 255, 18), 1))
            for k in range(self.sym):
                a = math.radians(360.0 * k / self.sym - 90)
                p.drawLine(QPointF(o.x() + N / 2, o.y() + N / 2),
                           QPointF(o.x() + N / 2 + math.cos(a) * N / 2, o.y() + N / 2 + math.sin(a) * N / 2))
        p.end()


class FrameDrawer(QDialog):
    """«Нарисовать рамку»: холст + инструменты; «Готово» — рамка в профиль."""

    def __init__(self, avatar: QPixmap, start: QImage | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Нарисовать рамку")
        self.setStyleSheet(_QSS)
        self.result_png = ""
        root = QHBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(16)
        self.canvas = DrawCanvas(avatar)
        if start is not None and not start.isNull():
            self.canvas.set_image(start)
            self.canvas.undo.clear()
        root.addWidget(self.canvas)
        col = QVBoxLayout()
        col.setSpacing(6)
        t = QLabel("Своя рамка")
        t.setStyleSheet("font-size:20px;font-weight:900;")
        col.addWidget(t)
        tip = QLabel("Рисуйте мышкой. Кнопки «Симметрия» 2–12 — штрих по кругу.\nСередина защищена: там будет фото.")
        tip.setObjectName("Sub")
        col.addWidget(tip)
        col.addWidget(_sec("ЦВЕТ"))
        pal = QGridLayout()
        pal.setSpacing(4)
        cols = ("#ffdb1a", "#ff9d00", "#ff3b3b", "#ff5fa8", "#c77dff", "#7c8cff", "#2fc6ff", "#5ef2c2", "#7ddc6a",
                "#ffffff", "#9a9aa2", "#000000")
        for i, cc in enumerate(cols):
            b = QPushButton()
            b.setFixedSize(30, 26)
            b.setStyleSheet(f"QPushButton{{background:{cc};border:2px solid rgba(255,255,255,0.18);border-radius:7px;}}"
                            "QPushButton:hover{border-color:#fff;}")
            b.clicked.connect(lambda _=False, cc=cc: self._color(QColor(cc)))
            pal.addWidget(b, i // 6, i % 6)
        col.addLayout(pal)
        more = QPushButton("Другой цвет…")
        more.clicked.connect(lambda: self._color(QColorDialog.getColor(self.canvas.color, self, "Цвет")))
        col.addWidget(more)
        col.addWidget(_sec("КИСТЬ"))
        self.w_lbl = QLabel()
        col.addWidget(self.w_lbl)
        ws = QSlider(Qt.Orientation.Horizontal)
        ws.setRange(2, 40)
        ws.setValue(self.canvas.width_)
        ws.valueChanged.connect(self._width)
        col.addWidget(ws)
        self._width(ws.value())
        tools = QHBoxLayout()
        grp = QButtonGroup(self)
        for name, er in (("Кисть", False), ("Ластик", True)):
            b = QPushButton(name)
            b.setCheckable(True)
            b.setChecked(not er)
            b.clicked.connect(lambda _=False, er=er: setattr(self.canvas, "eraser", er))
            grp.addButton(b)
            tools.addWidget(b)
        col.addLayout(tools)
        g = QCheckBox("Свечение кисти")
        g.setChecked(True)
        g.toggled.connect(lambda on: setattr(self.canvas, "glow", on))
        col.addWidget(g)
        pr = QCheckBox("Не рисовать на фото")
        pr.setChecked(True)
        pr.toggled.connect(lambda on: setattr(self.canvas, "protect", on))
        col.addWidget(pr)
        col.addWidget(_sec("СИММЕТРИЯ"))
        sym = QHBoxLayout()
        sg = QButtonGroup(self)
        for n in (1, 2, 4, 6, 8, 12):
            b = QPushButton(str(n))
            b.setCheckable(True)
            b.setChecked(n == self.canvas.sym)
            b.setFixedWidth(40)
            b.clicked.connect(lambda _=False, n=n: (setattr(self.canvas, "sym", n), self.canvas.update()))
            sg.addButton(b)
            sym.addWidget(b)
        col.addLayout(sym)
        col.addWidget(_sec("БЫСТРО"))
        r1 = QHBoxLayout()
        f1 = QPushButton("Залить кольцо")
        f1.clicked.connect(lambda: self.canvas.fill_ring(False))
        f2 = QPushButton("Радужное кольцо")
        f2.clicked.connect(lambda: self.canvas.fill_ring(True))
        r1.addWidget(f1)
        r1.addWidget(f2)
        col.addLayout(r1)
        r2 = QHBoxLayout()
        imp = QPushButton("Из картинки…")
        imp.clicked.connect(self._import)
        un = QPushButton("Отменить")
        un.clicked.connect(self.canvas.do_undo)
        cl = QPushButton("Очистить")
        cl.clicked.connect(self.canvas.clear)
        for b in (imp, un, cl):
            r2.addWidget(b)
        col.addLayout(r2)
        col.addStretch(1)
        bot = QHBoxLayout()
        bot.addStretch(1)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Готово")
        ok.setObjectName("Accent")
        ok.clicked.connect(self._done)
        bot.addWidget(cancel)
        bot.addWidget(ok)
        col.addLayout(bot)
        root.addLayout(col)

    def _color(self, c):
        if c is not None and c.isValid():
            self.canvas.color = c
            self.canvas.eraser = False

    def _width(self, v):
        self.canvas.width_ = v
        self.w_lbl.setText(f"Толщина: {v}")

    def _import(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Картинка для рамки", "", "Картинки (*.png *.jpg *.jpeg *.webp *.gif)")
        if fn:
            img = QImage(fn)
            if not img.isNull():
                self.canvas.set_image(cut_center(img))

    def _done(self):
        self.result_png = png_b64(self.canvas.img)
        if self.result_png:
            self.accept()


# ══════════════════════════ выбор рамки ══════════════════════════ #

_QSS = ("QDialog{background:#111113;} QLabel{color:#f0f0f0;background:transparent;}"
        "QLabel#Sec{color:#8a8a8a;font-size:11px;font-weight:800;letter-spacing:1px;padding-top:10px;}"
        "QLabel#Sub{color:#8a8a8a;font-size:11px;}"
        "QPushButton{background:#232326;color:#f0f0f0;border:none;border-radius:12px;padding:7px 14px;font-weight:700;}"
        "QPushButton:hover{background:#2e2e32;} QPushButton:checked{background:#f0f0f0;color:#000;}"
        "QPushButton#Accent{background:#ffdb1a;color:#000;} QPushButton:disabled{color:#555;}"
        "QCheckBox{color:#f0f0f0;} QScrollArea{background:transparent;border:none;}")


def _sec(text):
    l = QLabel(text)
    l.setObjectName("Sec")
    return l


class _Tile(QPushButton):
    def __init__(self, avatar, spec, title, locked, how=""):
        super().__init__()
        self.spec = spec
        self.setCheckable(True)
        self.setFixedSize(112, 132)
        self.setEnabled(not locked)
        self.setToolTip(("\U000f1002 " + how) if locked else title)
        self._pm = framed(avatar, spec, 84)
        self._title = title
        self._locked = locked
        # размер — и в стиле: общий стиль кнопок задаёт min-height и перебивал setFixedSize (плитки обрезались)
        self.setStyleSheet("QPushButton{background:#1b1b1e;border-radius:14px;border:2px solid transparent;"
                           "min-height:132px;max-height:132px;min-width:112px;max-width:112px;padding:0;}"
                           "QPushButton:hover{background:#242428;} QPushButton:checked{border-color:#ffdb1a;}"
                           "QPushButton:disabled{background:#151517;}")

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(0.35 if self._locked else 1.0)
        p.drawPixmap(QRectF(14, 8, 84, 84), self._pm, QRectF(self._pm.rect()))
        p.setOpacity(1.0)
        f = QFont()
        f.setPixelSize(11)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#777" if self._locked else "#e6e6e6"))
        p.drawText(QRectF(4, 96, 104, 30), Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap,
                   ("\U000f1002 " if self._locked else "") + self._title)
        p.end()


class FramePicker(QDialog):
    """Окно «Рамка профиля»: без рамки, за ачивки, за роль, своя (загрузить / нарисовать)."""

    def __init__(self, avatar: QPixmap, current: dict, ach: list, role: str, ach_names: dict, parent=None,
                 gifts=()):
        super().__init__(parent)
        self.setWindowTitle("Рамка профиля")
        self.setStyleSheet(_QSS)
        self.resize(720, 640)
        self.avatar = avatar
        self.spec = clean_spec(current)
        self.custom_png = self.spec.get("png", "") if self.spec.get("id") == "custom" else ""
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        top = QHBoxLayout()
        self.big = QLabel()
        self.big.setFixedSize(150, 150)
        top.addWidget(self.big)
        col = QVBoxLayout()
        t = QLabel("Рамка профиля")
        t.setStyleSheet("font-size:22px;font-weight:900;")
        col.addWidget(t)
        s = QLabel("Видна всем в Echoes.NET: в профиле, ленте, чатах. Рамки за ачивки открываются, когда "
                   "ачивка получена. Свою можно загрузить или нарисовать.")
        s.setObjectName("Sub")
        s.setWordWrap(True)
        col.addWidget(s)
        btns = QHBoxLayout()
        up = QPushButton("Загрузить картинку…")
        up.clicked.connect(self._upload)
        dr = QPushButton("Нарисовать")
        dr.clicked.connect(self._draw)
        btns.addWidget(up)
        btns.addWidget(dr)
        btns.addStretch(1)
        col.addLayout(btns)
        an = QHBoxLayout()
        an.addWidget(QLabel("Анимация:"))
        self.anim_group = QButtonGroup(self)
        for k, n in FRAME_ANIMS.items():
            b = QPushButton(n)
            b.setCheckable(True)
            b.setChecked(k == (self.spec.get("anim") or ""))
            b.setToolTip("Видна в профиле. «Под музыку» — рамка качается в такт тому, что играет у смотрящего"
                         if k == "beat" else "")
            b.clicked.connect(lambda _=False, k=k: self._set_anim(k))
            self.anim_group.addButton(b)
            an.addWidget(b)
        an.addStretch(1)
        col.addLayout(an)
        col.addStretch(1)
        top.addLayout(col, 1)
        root.addLayout(top)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        inner = QWidget()
        inner.setStyleSheet("background:transparent;")
        self.grid_v = QVBoxLayout(inner)
        self.grid_v.setContentsMargins(0, 0, 0, 0)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self._add_section("ОБЫЧНЫЕ", [({"id": "none"}, "Без рамки", False, "")] +
                          ([({"id": "custom", "png": self.custom_png}, "Своя", False, "")] if self.custom_png else []))
        import net_cosmetics                                   # рамки Phantom: свои анимации у каждой
        self._add_section("PHANTOM — БЕСПЛАТНО", [({"id": "ph:" + k}, n, False, "") for k, n in
                                                   net_cosmetics.FREE.items()])
        sp = "__sponsor__" in set(ach or ())
        self._add_section("ДЛЯ СПОНСОРОВ ECHOES", [({"id": "sp:" + k}, n, not sp,
                                                     "Для спонсоров ECHOES — магазин, кнопка с пакетом вверху")
                                                    for k, n in net_cosmetics.SPONSOR.items()])
        gl = [g for g in gifts or () if isinstance(g, dict) and g.get("png") and g.get("png") != self.custom_png]
        if gl:                                                 # подарки друзей (net_gifts)
            self._add_section("ПОДАРЕННЫЕ", [({"id": "custom", "png": g["png"]}, "От " + (g.get("from") or "друга"),
                                              False, "") for g in gl])
        if role in ROLE_FRAMES:
            self._add_section("ЗА РОЛЬ", [({"id": "role", "role": role}, ROLE_FRAMES[role], False, "")])
        self._add_section("СЕЗОННЫЕ (выбрать можно только в свой сезон)",
                          [({"id": "season:" + k}, v[0], not _season_on(k) and self.spec.get("id") != "season:" + k,
                            "Доступна: " + v[1]) for k, v in SEASON_FRAMES.items()])
        have = set(ach or ())
        self._add_section("ЗА АЧИВКИ", [({"id": "ach:" + k}, f"{ach_names.get(k, (k, ''))[0]} · {v}", k not in have,
                                         ach_names.get(k, ("", ""))[1]) for k, v in ACH_FRAMES.items()])
        self.grid_v.addStretch(1)
        sc.setWidget(inner)
        root.addWidget(sc, 1)
        bot = QHBoxLayout()
        bot.addStretch(1)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Сохранить")
        ok.setObjectName("Accent")
        ok.clicked.connect(self.accept)
        bot.addWidget(cancel)
        bot.addWidget(ok)
        root.addLayout(bot)
        self.role = role
        self._preview()
        cur = self.spec.get("id") or "none"
        for b in self.group.buttons():
            if b.spec.get("id") == cur:
                b.setChecked(True)

    def _add_section(self, title, items):
        self.grid_v.addWidget(_sec(title))
        g = QGridLayout()
        g.setSpacing(8)
        g.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        for i, (spec, name, locked, how) in enumerate(items):
            t = _Tile(self.avatar, spec, name, locked, how)
            t.clicked.connect(lambda _=False, t=t: self._pick(t.spec))
            self.group.addButton(t)
            g.addWidget(t, i // 5, i % 5)
        self.grid_v.addLayout(g)

    def _pick(self, spec):
        anim = self.spec.get("anim")
        self.spec = {"id": spec["id"], **({"png": spec["png"]} if spec.get("png") else {}),
                     **({"anim": anim} if anim else {})}
        self._preview()

    def _set_anim(self, k):
        self.spec.pop("anim", None)
        if k:
            self.spec["anim"] = k
        self._preview()

    def _preview(self):
        eff = dict(self.spec)
        if eff.get("id") == "role":
            eff["role"] = self.role
        if eff.get("id") == "none":
            eff = {}
        animate_label(self.big, self.avatar, eff, 150)

    def _set_custom(self, png):
        if not png:
            return
        self.custom_png = png
        self.spec = {"id": "custom", "png": png}
        self._preview()
        for b in self.group.buttons():
            b.setChecked(False)

    def _upload(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Картинка-рамка", "", "Картинки (*.png *.jpg *.jpeg *.webp *.gif)")
        if not fn:
            return
        img = QImage(fn)
        if img.isNull():
            return
        self._set_custom(png_b64(cut_center(img)))

    def _draw(self):
        start = None
        if self.custom_png:
            start = QImage()
            start.loadFromData(base64.b64decode(self.custom_png), "PNG")
        d = FrameDrawer(self.avatar, start, self)
        if d.exec() and d.result_png:
            self._set_custom(d.result_png)

    def result_spec(self) -> dict:
        s = clean_spec(self.spec)
        return s if s.get("id") != "none" else {"id": "none"}
