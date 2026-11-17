# net_reactions.py
"""
Свои (авторские) реакции Echoes.NET — маленькие картинки, которыми можно реагировать на посты.

Добавляются в настройках Echoes.NET: любая картинка (PNG, JPG, GIF, WebP) ужимается до 64×64 PNG
(не больше 16 КБ). Реакция — значение «c:<16 hex>» = начало SHA-256 картинки; сама картинка едет
внутри подписанной реакции (поле img, base64), так что друзья и все, кому разошлась ветка, видят её
без отдельной загрузки. Получатель проверяет, что хэш сходится, — подменить картинку нельзя.

Файлы: ~/Echoes/net/reactions/mine/<id>.png (свои; mine.json — порядок и названия)
       ~/Echoes/net/reactions/<id>.png       (увиденные у других)
"""
from __future__ import annotations

import data_home
import base64
import hashlib
import json
import re
from pathlib import Path

from raster_budget import ByteLRU

DIR = data_home.root() / "net" / "reactions"
MINE = DIR / "mine"
INDEX = MINE / "mine.json"
SIZE = 64
MAX_BYTES = 16 * 1024
MAX_MINE = 40
_ID = re.compile(r"^c:[0-9a-f]{16}$")
_pm_cache = ByteLRU(4 * 2**20)


def is_custom(val) -> bool:
    return isinstance(val, str) and bool(_ID.match(val))


def _id_of(data: bytes) -> str:
    return "c:" + hashlib.sha256(data).hexdigest()[:16]


def _decode(b64) -> bytes | None:
    if not isinstance(b64, str) or len(b64) > MAX_BYTES * 4 // 3 + 8:
        return None
    try:
        data = base64.b64decode(b64, validate=True)
    except ValueError:
        return None
    if len(data) > MAX_BYTES or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return data


def valid(r: dict) -> bool:
    """Реакция-картинка из сети: значение c:<hex>, картинка PNG ≤ 16 КБ и её хэш совпадает."""
    val = r.get("val")
    if not is_custom(val):
        return False
    data = _decode(r.get("img"))
    return data is not None and _id_of(data) == val


# ── свои ── #

def _index() -> list:
    try:
        d = json.loads(INDEX.read_text(encoding="utf-8"))
        return [x for x in d if isinstance(x, dict) and is_custom(x.get("id")) and (MINE / f"{x['id'][2:]}.png").exists()]
    except (OSError, ValueError):
        return []


def _save_index(items):
    MINE.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def mine() -> list:
    """[{id, name}] — свои реакции в порядке добавления."""
    return _index()


def normalize(path) -> bytes:
    """Картинка → PNG 64×64 (вписана, прозрачные поля), не больше 16 КБ."""
    from PyQt6.QtCore import QBuffer, QIODevice, Qt
    from PyQt6.QtGui import QImage, QImageReader, QPainter
    r = QImageReader(str(path))
    r.setAutoTransform(True)
    img = r.read()
    if img.isNull():
        raise ValueError("не картинка или файл повреждён")
    for side in (SIZE, 56, 48, 40):
        sc = img.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        out = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        p.drawImage((side - sc.width()) // 2, (side - sc.height()) // 2, sc)
        p.end()
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        out.save(buf, "PNG", 0)
        data = bytes(buf.data())
        if len(data) <= MAX_BYTES:
            return data
    raise ValueError("картинка слишком сложная даже в 40×40 — попробуйте попроще")


def add(path, name="") -> str:
    """Добавить свою реакцию из файла. Возвращает id."""
    items = _index()
    if len(items) >= MAX_MINE:
        raise ValueError(f"не больше {MAX_MINE} своих реакций")
    data = normalize(path)
    rid = _id_of(data)
    MINE.mkdir(parents=True, exist_ok=True)
    (MINE / f"{rid[2:]}.png").write_bytes(data)
    if all(x["id"] != rid for x in items):
        items.append({"id": rid, "name": (name or Path(str(path)).stem)[:40]})
        _save_index(items)
    _pm_cache.clear()
    return rid


def remove(rid):
    _save_index([x for x in _index() if x["id"] != rid])


def rename(rid, name):
    items = _index()
    for x in items:
        if x["id"] == rid:
            x["name"] = str(name)[:40]
    _save_index(items)


def b64(rid) -> str:
    """Картинка своей (или увиденной) реакции для отправки."""
    f = _file(rid)
    return base64.b64encode(f.read_bytes()).decode() if f is not None else ""


# ── увиденные ── #

def _file(rid) -> Path | None:
    if not is_custom(rid):
        return None
    for f in (MINE / f"{rid[2:]}.png", DIR / f"{rid[2:]}.png"):
        if f.exists():
            return f
    return None


def keep(reacts):
    """Сохранить картинки реакций из ветки (сырые подписанные объекты), которых ещё нет."""
    for r in reacts or []:
        if not isinstance(r, dict) or not is_custom(r.get("val")) or _file(r["val"]) is not None:
            continue
        if valid(r):
            DIR.mkdir(parents=True, exist_ok=True)
            (DIR / f"{r['val'][2:]}.png").write_bytes(base64.b64decode(r["img"]))


def name_of(rid) -> str:
    return next((x["name"] for x in _index() if x["id"] == rid), "Реакция")


def pixmap(rid, size=20):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QPixmap
    key = (rid, size)
    hit = _pm_cache.get(key)
    if hit is not None:
        return hit
    f = _file(rid)
    if f is None:
        return QPixmap()
    pm = QPixmap(str(f)).scaled(size * 2, size * 2, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
    if not pm.isNull():
        pm.setDevicePixelRatio(2)
        _pm_cache.put(key, pm, pm.width() * pm.height() * 4)
    return pm
