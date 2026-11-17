# emoji_pack.py
"""
Эмодзи для реакций — Noto Color Emoji (Google, лицензия Apache 2.0), а не системные смайлики Windows 11.

Картинки маленькие (72×72 PNG, ~3–6 КБ): при первом показе скачиваются с CDN jsDelivr (GitHub
googlefonts/noto-emoji; запасной — Twemoji) и лежат в ~/Echoes/emoji. Пока картинки нет или
сети нет — рисуется символ системным шрифтом, а когда картинка докачается, виджеты, подписанные
на ready, перерисовываются.
"""
from __future__ import annotations

import data_home
import threading
from pathlib import Path

from PyQt6.QtCore import QObject, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QPainter, QPixmap

from raster_budget import ByteLRU

DIR = data_home.root() / "emoji"
SOURCES = (
    "https://cdn.jsdelivr.net/gh/googlefonts/noto-emoji@main/png/72/emoji_u{code}.png",
    "https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.1.0/assets/72x72/{tw}.png",
)


def _codes(ch: str):
    cps = [f"{ord(c):x}" for c in ch if ord(c) != 0xFE0F]           # вариационный селектор в именах не пишется
    return "_".join(cps), "-".join(cps)


class _Bus(QObject):
    ready = pyqtSignal(str)


bus = _Bus()
_pm_cache = ByteLRU(4 * 2**20)
_loading: set = set()
_lock = threading.Lock()


def _file(ch) -> Path:
    return DIR / f"{_codes(ch)[0]}.png"


def _fetch(ch):
    code, tw = _codes(ch)
    data = b""
    try:
        import requests
        for url in SOURCES:
            try:
                r = requests.get(url.format(code=code, tw=tw), timeout=8)
                if r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n" and len(r.content) < 200_000:
                    data = r.content
                    break
            except Exception:                                    # noqa: BLE001
                continue
        if data:
            DIR.mkdir(parents=True, exist_ok=True)
            tmp = _file(ch).with_suffix(".part")
            tmp.write_bytes(data)
            tmp.replace(_file(ch))
    finally:
        with _lock:
            _loading.discard(ch)
    if data:
        try:
            bus.ready.emit(ch)                                   # сигнал в поток интерфейса (очередь Qt)
        except RuntimeError:
            pass


def _fallback(ch, size) -> QPixmap:
    dpr = 2
    pm = QPixmap(size * dpr, size * dpr)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)
    p = QPainter(pm)
    f = QFont("Segoe UI Emoji")
    f.setPixelSize(int(size * 0.86))
    p.setFont(f)
    p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, ch)
    p.end()
    return pm


def pixmap(ch: str, size: int = 20) -> QPixmap:
    """Эмодзи картинкой Noto нужного размера (с учётом HiDPI). Нет файла — символ, файл качается."""
    key = (ch, size)
    pm = _pm_cache.get(key)
    if pm is not None:
        return pm
    f = _file(ch)
    if f.exists():
        src = QPixmap(str(f))
        if not src.isNull():
            pm = src.scaled(size * 2, size * 2, Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
            pm.setDevicePixelRatio(2)
            _pm_cache.put(key, pm, pm.width() * pm.height() * 4)
            return pm
    with _lock:
        start = ch not in _loading
        _loading.add(ch)
    if start:
        threading.Thread(target=_fetch, args=(ch,), daemon=True, name="emoji").start()
    return _fallback(ch, size)                                   # не кэшируем: заменится на Noto


def icon(ch: str, size: int = 20) -> QIcon:
    return QIcon(pixmap(ch, size))


def prefetch(chars):
    for ch in chars:
        if not _file(ch).exists():
            pixmap(ch, 20)
