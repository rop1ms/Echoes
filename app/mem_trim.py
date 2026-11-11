# mem_trim.py
"""
Возврат памяти системе.

Освобождённая память (закрыли конструктор, сменили тему, отыграл анализ трека) остаётся
у процесса: куча Windows держит пустые страницы, а «рабочий набор» — страницы, к которым
давно не обращались. Диспетчер задач показывает это как занятую плеером память.

trim() собирает освобождённые объекты и уплотняет кучу. Принудительное урезание
рабочего набора выключено по умолчанию: оно может вызывать page faults и мешать звуку.
Вызывается после тяжёлых действий, при сворачивании окна и вскоре после запуска.
"""
from __future__ import annotations

import ctypes
import gc
import sys

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer

_pending = {"t": None}


def trim(working_set: bool = False):
    # Полная сборка обходит ВСЕ объекты плеера (сотни тысяч) — это 40–50 мс остановки интерфейса, и Python
    # время от времени запускает её сам, посреди прокрутки или анимации. После уборки «замораживаем» выжившее
    # (интерфейс, коллекция, кэши): автоматические сборки обходят только новое и занимают единицы мс.
    # Замороженное не теряется: перед каждой уборкой здесь оно размораживается и проверяется целиком.
    gc.unfreeze()
    gc.collect()
    gc.freeze()
    if not sys.platform.startswith("win"):
        return
    try:
        k32 = ctypes.windll.kernel32
        k32.GetProcessHeap.restype = ctypes.c_void_p
        k32.HeapCompact.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        k32.HeapCompact.restype = ctypes.c_size_t
        k32.HeapCompact(k32.GetProcessHeap(), 0)          # пустые страницы основной кучи — системе
        if working_set:
            k32.GetCurrentProcess.restype = ctypes.c_void_p
            k32.SetProcessWorkingSetSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t]
            minus1 = ctypes.c_size_t(-1).value
            k32.SetProcessWorkingSetSize(k32.GetCurrentProcess(), minus1, minus1)
    except Exception as e:                                # noqa: BLE001
        print("[mem]", e)


def trim_later(ms: int = 2500):
    """Отложенный trim: серия действий (несколько смен темы подряд) даёт один вызов."""
    t = _pending["t"]
    if t is None:
        t = QTimer()
        t.setSingleShot(True)
        t.timeout.connect(trim)
        _pending["t"] = t
    t.start(int(ms))


class _Watcher(QObject):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        win.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if obj is self.win and ev.type() == QEvent.Type.WindowStateChange:
            if self.win.windowState() & Qt.WindowState.WindowMinimized:
                trim_later(1500)                          # свернули — память не нужна, пока окно не вернут
        return False


def install(win):
    _Watcher(win)
    trim_later(20000)                                     # после запуска: инициализация больше не нужна
