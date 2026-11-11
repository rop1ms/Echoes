# img_load.py
"""
Загрузка картинок (обложек) так, чтобы не рвался звук.

QPixmap(путь) в PyQt6 держит GIL всё время декодирования: обложка 2–3 МБ — это 70–130 мс,
и всё это время поток вывода звука (он на Python) не может отдать устройству следующий
блок — при прокрутке списка с обложками звук заикался. QImageReader.read() GIL отпускает,
а с setScaledSize JPEG уменьшается прямо при декодировании — ещё и в ~4 раза быстрее.
"""
from __future__ import annotations

import os
import threading
from collections import OrderedDict

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QImage, QImageReader, QPixmap

# ── «горячие» обложки: играющий трек и его соседи ──
# На смене трека одну и ту же обложку читали с диска 5–6 раз подряд в потоке интерфейса (плашка плеера,
# «Моя волна», текст, палитра, фон, размытие — каждому свой размер): PNG/прогрессивный JPEG 1000 px —
# это 10–25 мс за раз, в сумме 80–110 мс рывка на КАЖДОМ треке. warm() декодирует файл один раз
# (для следующего трека — заранее, в фоне), а read_image() отдаёт уменьшенную копию из памяти.
HOT_SIDE = 1600                                        # больше никто из рисующих играющий трек не просит
HOT_KEEP = 3                                           # текущий, следующий, предыдущий
_HOT: OrderedDict = OrderedDict()                      # путь → (подпись файла, QImage, целиком ли картинка)
_HOT_LOCK = threading.Lock()


def _file_sig(path: str):
    try:
        st = os.stat(path)
        return st.st_mtime_ns, st.st_size
    except OSError:
        return None


def warm(path) -> bool:
    """Декодировать обложку один раз и держать в памяти (любой поток). True — она в памяти."""
    path = str(path or "")
    if not path:
        return False
    sig = _file_sig(path)
    if sig is None:
        return False
    with _HOT_LOCK:
        hit = _HOT.get(path)
        if hit is not None and hit[0] == sig:
            _HOT.move_to_end(path)
            return True
    r = QImageReader(path)
    sz = r.size()
    full = not sz.isValid() or max(sz.width(), sz.height()) <= HOT_SIDE
    img = _decode(path, HOT_SIDE)
    if img.isNull():
        return False
    with _HOT_LOCK:
        _HOT[path] = (sig, img, full)
        _HOT.move_to_end(path)
        while len(_HOT) > HOT_KEEP:
            _HOT.popitem(last=False)
    return True


def forget(path=None):
    """Убрать обложку (или все) из памяти — файл заменили или память нужнее."""
    with _HOT_LOCK:
        if path is None:
            _HOT.clear()
        else:
            _HOT.pop(str(path), None)


def _from_hot(path: str, max_side: int):
    with _HOT_LOCK:
        hit = _HOT.get(path)
    if hit is None:
        return None
    sig, img, full = hit
    if _file_sig(path) != sig:                         # файл обложки заменили
        forget(path)
        return None
    side = max(img.width(), img.height())
    if max_side and max_side > 0 and side > max_side:
        return img.scaled(max_side, max_side, Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
    if full or (max_side and 0 < max_side <= side):
        return img
    return None                                        # в памяти уменьшенная, а просят крупнее — читать файл


def read_image(path, max_side: int = 0) -> QImage:
    """QImage из файла; max_side > 0 — большая сторона не больше max_side (с сохранением пропорций).
    Пустой QImage, если файла нет или он не читается."""
    if not path:
        return QImage()
    if _HOT:
        img = _from_hot(str(path), max_side)
        if img is not None:
            return img
    return _decode(path, max_side)


def _decode(path, max_side: int = 0) -> QImage:
    r = QImageReader(str(path))
    if max_side and max_side > 0:
        sz = r.size()
        if sz.isValid() and max(sz.width(), sz.height()) > max_side:
            k = max_side / max(sz.width(), sz.height())
            r.setScaledSize(QSize(max(1, round(sz.width() * k)), max(1, round(sz.height() * k))))
    img = r.read()
    return img


def load_pixmap(path, max_side: int = 0) -> QPixmap:
    """Замена QPixmap(путь): то же, но без удержания GIL и (с max_side) в разы быстрее."""
    img = read_image(path, max_side)
    return QPixmap.fromImage(img) if not img.isNull() else QPixmap()
