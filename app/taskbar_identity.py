# taskbar_identity.py
"""
Идентичность окна на панели задач Windows: закреплённый ярлык получает
команду запуска, значок и имя Echoes.

Окну выставляются свойства оболочки (IPropertyStore):
    System.AppUserModel.ID, RelaunchCommand, RelaunchDisplayNameResource, RelaunchIconResource.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

AUMID = "echoes.player"
_VT_LPWSTR = 31


class _GUID(ctypes.Structure):
    _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, s: str):
        import uuid
        u = uuid.UUID(s)
        g = cls()
        g.a, g.b, g.c = u.time_low, u.time_mid, u.time_hi_version
        for i, byte in enumerate(u.bytes[8:]):
            g.d[i] = byte
        return g


class _PKEY(ctypes.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", wintypes.DWORD)]


class _PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt", wintypes.WORD), ("r1", wintypes.WORD), ("r2", wintypes.WORD), ("r3", wintypes.WORD),
                ("ptr", ctypes.c_void_p), ("pad", ctypes.c_void_p)]


_FMT = "9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"           # System.AppUserModel.*
_PID = {"id": 5, "cmd": 2, "icon": 3, "name": 4}


def set_window_identity(hwnd: int, command: str, icon_path: str, display_name: str = "ECHOES",
                        aumid: str = AUMID) -> bool:
    """Записать свойства окну. Возвращает True, если всё записалось."""
    if not sys.platform.startswith("win") or not hwnd:
        return False
    try:
        shell32 = ctypes.windll.shell32
        iid = _GUID.parse("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")          # IID_IPropertyStore
        ppv = ctypes.c_void_p()
        hr = shell32.SHGetPropertyStoreForWindow(wintypes.HWND(hwnd), ctypes.byref(iid), ctypes.byref(ppv))
        if hr != 0 or not ppv.value:
            return False
        vtbl = ctypes.cast(ctypes.cast(ppv, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
        SetValue = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(_PKEY),
                                      ctypes.POINTER(_PROPVARIANT))(vtbl[6])
        Commit = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p)(vtbl[7])
        Release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
        fmt = _GUID.parse(_FMT)
        keep = []
        for name, value in (("id", aumid), ("cmd", command), ("name", display_name), ("icon", icon_path)):
            buf = ctypes.create_unicode_buffer(value)
            keep.append(buf)
            pv = _PROPVARIANT()
            pv.vt = _VT_LPWSTR
            pv.ptr = ctypes.cast(buf, ctypes.c_void_p).value
            SetValue(ppv, ctypes.byref(_PKEY(fmt, _PID[name])), ctypes.byref(pv))
        Commit(ppv)
        Release(ppv)
        return True
    except Exception as e:                                  # noqa: BLE001
        print("[taskbar]", e)
        return False


def apply(window, app_dir: Path) -> bool:
    """Use the installed player image and its resources for pinned relaunches."""
    app_dir = Path(app_dir)
    player = app_dir.parent / "python" / "Echoes.exe"
    if player.is_file():
        return set_window_identity(int(window.winId()), f'"{player}" "{app_dir / "main.py"}"',
                                   f"{player},0", f"@{player},-101")
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    exe = pyw if pyw.exists() else exe
    main_py = app_dir / "main.py"
    icon = app_dir / "icon.ico"
    cmd = f'"{exe}" "{main_py}"'
    return set_window_identity(int(window.winId()), cmd, f"{icon},0" if icon.exists() else "", "ECHOES")
