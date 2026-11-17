# window_snap.py
"""Привязка безрамочного окна к краям экрана (Aero Snap, Windows 10/11).

Окно Qt с FramelessWindowHint создаётся без стилей WS_THICKFRAME / WS_MAXIMIZEBOX — и Windows не делает
для него ни «прижал к верху — развернулось на весь экран», ни половинки по краям, ни Win+↑. Здесь стили
добавляются обратно, а системная рамка, которую они бы нарисовали, убирается через WM_NCCALCSIZE
(вся площадь окна — клиентская). У развёрнутого окна Windows выносит рамку за край монитора — её
клиентская часть подрезается по рабочей области монитора.
"""
from __future__ import annotations

import sys

from PyQt6.QtCore import QAbstractNativeEventFilter, QEvent, QObject, QTimer
from PyQt6.QtWidgets import QApplication

GWL_STYLE = -16
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_BORDER = 0x00800000
WM_NCCALCSIZE = 0x0083
SWP_FLAGS = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020      # NOSIZE|NOMOVE|NOZORDER|NOACTIVATE|FRAMECHANGED


def _api():
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    u.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    u.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    u.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int, ctypes.c_uint]
    u.IsZoomed.argtypes = [wintypes.HWND]
    return ctypes, wintypes, u


def apply_styles(window) -> bool:
    try:
        ctypes, wintypes, u = _api()
        hwnd = wintypes.HWND(int(window.winId()))
        style = u.GetWindowLongPtrW(hwnd, GWL_STYLE)
        want = style | WS_THICKFRAME | WS_MAXIMIZEBOX | WS_MINIMIZEBOX
        if want != style:
            u.SetWindowLongPtrW(hwnd, GWL_STYLE, want)
            u.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_FLAGS)
        return True
    except Exception as e:                                 # noqa: BLE001
        print("[snap]", e)
        return False


def fullscreen_border(window):
    """Qt's Windows/OpenGL workaround: keep DWM composing popups in fullscreen.

    https://doc.qt.io/qt-6/windows-issues.html#fullscreen-opengl-based-windows
    """
    if sys.platform != 'win32':
        return
    ctypes, wintypes, u = _api()
    hwnd = wintypes.HWND(int(window.winId()))
    style = u.GetWindowLongPtrW(hwnd, GWL_STYLE)
    previous = getattr(window, '_fullscreen_border_hwnd', None)
    if window.isFullScreen():
        if previous != int(window.winId()):
            window._fullscreen_border_original = bool(style & WS_BORDER)
            window._fullscreen_border_hwnd = int(window.winId())
        want = style | WS_BORDER
    elif previous == int(window.winId()):
        want = style | WS_BORDER if window._fullscreen_border_original else style & ~WS_BORDER
        window._fullscreen_border_hwnd = None
    else:
        return
    if want != style:
        u.SetWindowLongPtrW(hwnd, GWL_STYLE, want)
        u.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_FLAGS)


class _NcFilter(QAbstractNativeEventFilter):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.hwnd = 0
        ctypes, wintypes, u = _api()
        self._c, self._w, self._u = ctypes, wintypes, u

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
        self.RECT = RECT

    def nativeEventFilter(self, etype, message):
        try:
            if etype != b"windows_generic_MSG" or not self.hwnd:
                return False, 0
            msg = self._w.MSG.from_address(int(message))
            if msg.message != WM_NCCALCSIZE or (msg.hWnd or 0) != self.hwnd or not msg.wParam:
                return False, 0
            if self.window.isFullScreen():
                # Preserve the real one-pixel DWM border in fullscreen.
                return False, 0
            if self._u.IsZoomed(self.hwnd):
                # развёрнутое окно Windows может вынести за край монитора на толщину рамки — подрезаем
                # клиентскую часть по рабочей области монитора (без панели задач)
                r = self.RECT.from_address(int(msg.lParam))       # NCCALCSIZE_PARAMS.rgrc[0]
                # монитор — по предлагаемому прямоугольнику, а не по нынешнему окну: при возврате из панели задач
                # окно ещё «свёрнуто» (−32000), и обрезка по рабочей области давала пустую клиентскую часть —
                # развёрнутое окно оставалось чёрным с белой полоской сверху
                work = self._work_area(r)
                if work is not None:
                    left, top = max(r.left, work.left), max(r.top, work.top)
                    right, bottom = min(r.right, work.right), min(r.bottom, work.bottom)
                    if right - left > 0 and bottom - top > 0:
                        r.left, r.top, r.right, r.bottom = left, top, right, bottom
            return True, 0                                         # без системной рамки и заголовка
        except Exception:                                          # noqa: BLE001
            return False, 0

    def _work_area(self, rect=None):
        c = self._c

        class MONITORINFO(c.Structure):
            _fields_ = [("cbSize", c.c_ulong), ("rcMonitor", self.RECT), ("rcWork", self.RECT), ("dwFlags", c.c_ulong)]
        try:
            self._u.MonitorFromWindow.restype = c.c_void_p
            self._u.MonitorFromWindow.argtypes = [self._w.HWND, c.c_ulong]
            if rect is not None:
                self._u.MonitorFromRect.restype = c.c_void_p
                self._u.MonitorFromRect.argtypes = [c.c_void_p, c.c_ulong]
                probe = self.RECT(rect.left, rect.top, rect.right, rect.bottom)
                mon = self._u.MonitorFromRect(c.byref(probe), 2)   # MONITOR_DEFAULTTONEAREST
            else:
                mon = self._u.MonitorFromWindow(self.hwnd, 2)      # MONITOR_DEFAULTTONEAREST
            mi = MONITORINFO()
            mi.cbSize = c.sizeof(MONITORINFO)
            self._u.GetMonitorInfoW.argtypes = [c.c_void_p, c.c_void_p]
            if mon and self._u.GetMonitorInfoW(mon, c.byref(mi)):
                return mi.rcWork
        except Exception:                                          # noqa: BLE001
            pass
        return None


class _Keeper(QObject):
    def __init__(self, window, nc):
        super().__init__(window)
        self.window, self.nc = window, nc

    def eventFilter(self, obj, ev):
        if obj is self.window and ev.type() in (QEvent.Type.WinIdChange, QEvent.Type.Show):
            QTimer.singleShot(0, self.refresh)
        return False

    def refresh(self):
        try:
            self.nc.hwnd = int(self.window.winId())
        except RuntimeError:
            return
        apply_styles(self.window)


def install(window) -> None:
    """Включить Aero Snap для безрамочного окна (только Windows)."""
    if not sys.platform.startswith("win") or getattr(window, "_snap_keeper", None) is not None:
        return
    try:
        nc = _NcFilter(window)
    except Exception as e:                                 # noqa: BLE001
        print("[snap]", e)
        return
    QApplication.instance().installNativeEventFilter(nc)
    k = _Keeper(window, nc)
    window.installEventFilter(k)
    window._snap_keeper = k
    window._snap_filter = nc                               # держать ссылку: иначе фильтр соберёт GC
    if window.isVisible():
        k.refresh()
