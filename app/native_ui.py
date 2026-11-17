# native_ui.py
"""
Виджеты интерфейса на C++ — echoes_ui.dll (исходники и сборка: tools/native_ui).

DLL собрана против того же Qt, что у PyQt6, и живёт в том же процессе: C++ создаёт QWidget,
здесь он оборачивается sip.wrapinstance и дальше это обычный виджет PyQt6. Если DLL нет,
версия Qt не совпала или ECHOES_NO_NATIVE_UI=1 — available() == False, и вызывающий код
остаётся на прежних виджетах Python.
"""
from __future__ import annotations

import ctypes
import os

from PyQt6 import sip
from PyQt6.QtCore import qVersion
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QWidget

_DIR = os.path.dirname(os.path.abspath(__file__))
_lib = None
_err = ""
_tried = False


def _ver(s):
    return tuple(int(x) for x in (s.split(".") + ["0", "0"])[:3] if x.isdigit())


def _load():
    global _lib, _err, _tried
    _tried = True
    if os.environ.get("ECHOES_NO_NATIVE_UI") == "1":
        _err = "disabled by ECHOES_NO_NATIVE_UI"
        return None
    path = os.path.join(_DIR, "echoes_ui.dll")
    if not os.path.exists(path):
        _err = "echoes_ui.dll not found"
        return None
    try:
        import PyQt6
        from PyQt6 import QtNetwork  # Load the matching Qt runtime for the native catalogues.
        qt_bin = os.path.join(os.path.dirname(PyQt6.__file__), "Qt6", "bin")
        if os.path.isdir(qt_bin):
            os.add_dll_directory(qt_bin)                   # Qt6*.dll — те же, что уже загрузил PyQt6
        # PyDLL: вызовы короткие и только из потока интерфейса — GIL не отпускаем. С CDLL каждый вызов
        # отдавал GIL фоновым потокам (обложки, анализ) и ждал его обратно до 5 мс — дольше самой работы.
        lib = ctypes.PyDLL(path)
        lib.eui_qt_version.restype = ctypes.c_char_p
        built = lib.eui_qt_version().decode()
        # Qt 6 держит двоичную совместимость вперёд: DLL под 6.11 работает и на 6.11.x/6.12,
        # но не на более старом Qt и не на Qt 7
        b, r = _ver(built), _ver(qVersion())
        if b[0] != r[0] or r < b:
            _err = f"Qt mismatch: dll {built}, runtime {qVersion()}"
            return None
        _setup(lib)
        _lib = lib
        return lib
    except Exception as e:                                 # noqa: BLE001
        _err = f"echoes_ui.dll: {e}"
        return None


_STRIP_CB = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_int)


def _setup(lib):
    P, I, W, D = ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p, ctypes.c_double
    sig = {
        "eui_version": (I, []),
        "eui_probe_new": (P, [P]),
        "eui_strip_callbacks": (None, [_STRIP_CB, _STRIP_CB, _STRIP_CB, _STRIP_CB]),
        "eui_strip_invalidate": (None, [P, I]),
        "eui_strip_new": (P, [I]),
        "eui_grid_new": (P, [I]),
        "eui_strip_clear": (None, [P]),
        "eui_grid_done": (None, [P]),
        "eui_strip_style": (None, [P, P, P, W, I]),
        "eui_strip_add": (I, [P, W, W, I, D, I, P, P]),
        "eui_strip_text": (None, [P, I, W, W]),
        "eui_strip_cover": (None, [P, I, P]),
        "eui_strip_mix_covers": (None, [P, I, ctypes.POINTER(P), I, I]),
        "eui_strip_set_hover": (None, [P, I, I, P, P, P, P]),
        "eui_strip_count": (I, [P]),
        "eui_strip_card_pos": (None, [P, I, ctypes.POINTER(I), ctypes.POINTER(I)]),
        "eui_strip_card_pixmap": (None, [P, I, P]),
        "eui_liquid_surface": (None, [I, I, D, P]),
        "eui_grab_from_window": (I, [P, P]),
        "eui_liquid_surface_callback": (None, [_STRIP_CB]),
        "eui_liquid_surface_async": (None, [I, I, I, D]),
        "eui_liquid_surface_take": (I, [I, P]),
        "eui_trans_new": (P, []),
        "eui_trans_ok": (I, [P]),
        "eui_trans_old": (None, [P, P]),
        "eui_trans_new_image": (None, [P, P]),
        "eui_trans_frame": (None, [P, I, ctypes.c_float, ctypes.c_float, ctypes.c_float]),
        "eui_scroll_new": (P, []),
        "eui_scroll_ok": (I, [P]),
        "eui_scroll_backdrop": (None, [P, P]),
        "eui_scroll_tile": (None, [P, I, P]),
        "eui_scroll_drop": (None, [P, I]),
        "eui_scroll_release": (None, [P]),
        "eui_scroll_frame": (None, [P, ctypes.c_float, I]),
        "eui_fire_draw": (I, [P] + [ctypes.c_float] * 6 + [P, I, ctypes.c_float, ctypes.c_float, I]),
        "eui_foreground_info": (I, [ctypes.c_wchar_p, I, ctypes.POINTER(I), ctypes.POINTER(I)]),
        "eui_process_alive": (I, [I]),
        "eui_intro_start": (I, [I, I, I, I, D, I, I, I, W, W]),
        "eui_intro_follow": (None, [ctypes.c_ssize_t]),
        "eui_intro_ready": (None, []),
        "eui_intro_alive": (I, []),
        "eui_intro_fading": (I, []),
        "eui_gate_install": (P, [P, ctypes.POINTER(I), I, ctypes.c_char_p]),
        "eui_gate_remove": (None, [P]),
        "eui_grab_window_area": (I, [P, P]),
        "eui_intro_frames": (I, []),
        "eui_nebula_new": (P, []),
        "eui_nebula_ok": (I, [P]),
        "eui_nebula_params": (None, [P, P]),
        "eui_nebula_overlay": (None, [P, P]),
        "eui_nebula_burst": (None, [P, ctypes.c_float]),
        "eui_nebula_scale": (None, [P, ctypes.c_float]),
        "eui_text_cache_new": (P, []),
        "eui_text_cache_free": (None, [P]),
        "eui_draw_wrapped": (None, [P, P, I, I, I, I, I, W]),
        "eui_draw_liquid": (None, [P, P, I, I, I, ctypes.POINTER(W)] + [ctypes.POINTER(D)] * 5 + [D, I, P, P, D]),
    }
    for name, (res, args) in sig.items():
        fn = getattr(lib, name, None)
        if fn is None and name in ("eui_intro_fading",):      # новее DLL — со старой просто без неё
            continue
        if fn is None:
            raise AttributeError(name)
        fn.restype, fn.argtypes = res, args
    lib.eui_strip_callbacks(_on_click, _on_hover, _on_gone, _on_need)
    lib.eui_liquid_surface_callback(_on_glass)


def available() -> bool:
    if not _tried:
        _load()
    return _lib is not None


def app_filter(target, types, cls: str = ""):
    """Сделать target фильтром событий всего приложения, но звать его eventFilter только для types
    (и, если задан cls, только у объектов ровно этого класса Qt) — проверка в C++ (event_gate.cpp).
    Без DLL — обычный installEventFilter, как раньше."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        return
    if available():
        try:
            vals = [int(getattr(t, "value", t)) for t in types]
            arr = (ctypes.c_int * len(vals))(*vals)
            h = _lib.eui_gate_install(_ptr(target), arr, len(vals), cls.encode() if cls else None)
            if h:
                target.__dict__["_echoes_gate"] = h
                return
        except Exception as e:                             # noqa: BLE001
            print("[gate]", e)
    app.installEventFilter(target)


def app_filter_remove(target):
    h = target.__dict__.pop("_echoes_gate", None)
    if h:
        _lib.eui_gate_remove(h)
        return
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is not None:
        app.removeEventFilter(target)


def error() -> str:
    return _err


def _wrap(ptr) -> QWidget:
    # Виджет создаётся без родителя и принадлежит Python, как обычный QWidget(): addWidget/
    # setParent передают владение Qt (sip это отслеживает), иначе удаляется вместе с обёрткой.
    w = sip.wrapinstance(ptr, QWidget)
    sip.transferback(w)
    return w


def probe() -> QWidget:
    return _wrap(_lib.eui_probe_new(None))


# ── лента карточек (card_strip.cpp) ────────────────────────────────────── #

_STRIPS: dict = {}                                         # id → Strip, пока C++-виджет жив
_next_id = [0]


def _guard(fn):
    def call(sid, index):
        try:
            fn(sid, index)
        except Exception:                                  # noqa: BLE001 — исключение в колбэке ctypes иначе теряется
            import sys
            sys.excepthook(*sys.exc_info())
    return _STRIP_CB(call)


def _click(sid, index):
    s = _STRIPS.get(sid)
    if s is not None and s.on_click is not None:
        s.on_click(index)


def _hover(sid, index):
    s = _STRIPS.get(sid)
    if s is not None and s.on_hover is not None:
        s.on_hover(index)


def _need(sid, index):
    s = _STRIPS.get(sid)
    if s is not None and s.on_need is not None:
        s.on_need(index)


def _gone(sid, _index):
    s = _STRIPS.pop(sid, None)
    if s is not None:
        s.alive = False
        try:
            sip.setdeleted(s.widget)                       # Qt удалил виджет — обёртка больше не годится
        except Exception:                                  # noqa: BLE001
            pass
        s.widget = None


_GLASS: dict = {}                                          # билет → колбэк(QPixmap)


def _glass(ticket, _ok):
    fn = _GLASS.pop(ticket, None)
    if fn is not None:
        from PyQt6.QtGui import QPixmap
        pm = QPixmap()
        if _lib.eui_liquid_surface_take(ticket, _ptr(pm)):
            fn(pm)


_on_click, _on_hover, _on_gone, _on_need = _guard(_click), _guard(_hover), _guard(_gone), _guard(_need)
_on_glass = _guard(_glass)


def _ptr(obj):
    return sip.unwrapinstance(obj) if obj is not None else None


class Strip:
    """Python-сторона одной ленты. widget — сам QWidget (кладётся в layout как обычно).
    on_click(i) / on_hover(i) задаёт владелец; после удаления виджета alive == False и все
    вызовы — пустые (поздняя обложка из фонового потока не обратится к удалённому объекту)."""

    def __init__(self, grid=False):
        _next_id[0] += 1
        self.id = _next_id[0]
        self.alive = True
        self.on_click = None
        self.on_hover = None
        self.on_need = None                                # карточку рисуют впервые / после invalidate
        self._p = (_lib.eui_grid_new if grid else _lib.eui_strip_new)(self.id)
        self.widget = _wrap(self._p)
        _STRIPS[self.id] = self

    def style(self, text, muted, families, cascade: bool):
        if self.alive:
            # QColor держим в переменных до конца вызова: _ptr() временного объекта — висячий указатель
            text, muted = QColor(text), QColor(muted)
            _lib.eui_strip_style(self._p, _ptr(text), _ptr(muted), "\n".join(families), int(cascade))

    def add(self, title, subtitle, size, rad, circle, mix=None) -> int:
        if not self.alive:
            return -1
        c1, c2 = (QColor(mix[0]), QColor(mix[1])) if mix else (None, None)
        return _lib.eui_strip_add(self._p, title, subtitle, int(size), float(rad), int(bool(circle)),
                                  _ptr(c1), _ptr(c2))

    def clear(self):
        if self.alive:
            _lib.eui_strip_clear(self._p)

    def grid_done(self):
        if self.alive:
            _lib.eui_grid_done(self._p)

    def text(self, i, title, subtitle):
        if self.alive:
            _lib.eui_strip_text(self._p, i, title, subtitle)

    def invalidate(self, i):
        if self.alive:
            _lib.eui_strip_invalidate(self._p, i)

    def cover(self, i, pixmap):
        if self.alive:
            _lib.eui_strip_cover(self._p, i, _ptr(pixmap))

    def mix_covers(self, i, pixmaps, on):
        if self.alive:
            arr = (ctypes.c_void_p * max(1, len(pixmaps)))(*[_ptr(p) for p in pixmaps])
            _lib.eui_strip_mix_covers(self._p, i, arr, len(pixmaps), int(bool(on)))

    def hover_style(self, i, glow, glow_color, ring_color, accent, icon):
        if self.alive:
            cols = QColor(glow_color), QColor(ring_color), QColor(accent)
            _lib.eui_strip_set_hover(self._p, i, int(bool(glow)), *[_ptr(c) for c in cols], _ptr(icon))

    def card_pos(self, i):
        x, y = ctypes.c_int(), ctypes.c_int()
        if self.alive:
            _lib.eui_strip_card_pos(self._p, i, ctypes.byref(x), ctypes.byref(y))
        return x.value, y.value

    def card_pixmap(self, i):
        from PyQt6.QtGui import QPixmap
        pm = QPixmap()
        if self.alive:
            _lib.eui_strip_card_pixmap(self._p, i, _ptr(pm))
        return pm


# ── фон окна и снимки переходов (glass.cpp) ─────────────────────────────── #

def liquid_surface(w: int, h: int, radius: float):
    """echo_glass._liquid_surface на C++ (тот же рисунок, включая зерно)."""
    from PyQt6.QtGui import QPixmap
    pm = QPixmap()
    _lib.eui_liquid_surface(int(w), int(h), float(radius), _ptr(pm))
    return pm


def liquid_surface_later(w: int, h: int, radius: float, done):
    """liquid_surface в фоновом потоке C++; done(QPixmap) — в потоке интерфейса."""
    _next_id[0] += 1
    ticket = _next_id[0]
    _GLASS[ticket] = done
    _lib.eui_liquid_surface_async(ticket, int(w), int(h), float(radius))


def grab_window_area(widget):
    """Область виджета из буфера окна с прозрачностью (дыры там, где рисует OpenGL), или None."""
    from PyQt6.QtGui import QPixmap
    pm = QPixmap()
    try:
        return pm if _lib.eui_grab_window_area(_ptr(widget), _ptr(pm)) else None
    except AttributeError:
        return None


def grab_from_window(widget):
    """Область виджета, как она уже нарисована в окне (без повторной отрисовки), или None."""
    from PyQt6.QtGui import QPixmap
    pm = QPixmap()
    return pm if _lib.eui_grab_from_window(_ptr(widget), _ptr(pm)) else None


# ── текст экрана «Текст песни» (text_cache.cpp) ─────────────────────────── #

class TextCache:
    """Готовые раскладки строк и глифы букв для одной панели текста (кэш живёт вместе с ней)."""

    def __init__(self):
        self._h = _lib.eui_text_cache_new()

    def __del__(self):
        if _lib is not None and self._h:
            _lib.eui_text_cache_free(self._h)
            self._h = None

    def draw_wrapped(self, painter, rect, flags: int, text: str):
        """= painter.drawText(rect, flags, text) — текст уже переведён (i18n.tr)."""
        _lib.eui_draw_wrapped(self._h, _ptr(painter), rect.x(), rect.y(), rect.width(), rect.height(),
                              int(flags), text)

    def draw_liquid(self, painter, ox, oy, arrays, now, px, col, dim_col, alpha):
        n, chars, cx, base, cw, t0, t1 = arrays
        col, dim_col = QColor(col), QColor(dim_col)        # живут до конца вызова
        _lib.eui_draw_liquid(self._h, _ptr(painter), int(ox), int(oy), n, chars, cx, base, cw, t0, t1,
                             float(now), int(px), _ptr(col), _ptr(dim_col), float(alpha))


def liquid_arrays(chars, tr=lambda s: s):
    """Раскладка «жидкой» строки ([символ, x, база, ширина, слово, t0, t1]) → массивы для C++."""
    n = len(chars)
    col = lambda k: (ctypes.c_double * max(1, n))(*[float(c[k]) for c in chars])
    keep = [tr(c[0]) for c in chars]
    arr = (ctypes.c_wchar_p * max(1, n))(*keep)
    return (n, arr, col(1), col(2), col(3), col(5), col(6))


# ── туманность «Моей волны» на видеокарте (nebula_gl.cpp) ─────────────── #

class NebulaGL:
    """QOpenGLWidget с шейдером туманности. params — native_fx.NebParams (как для CPU-рендера);
    overlay — QPixmap поверх (полоса, градиент, заголовок). ok() — после первого показа: GL есть."""

    def __init__(self):
        self.widget = _wrap(_lib.eui_nebula_new())

    def ok(self) -> bool:
        return bool(_lib.eui_nebula_ok(_ptr(self.widget)))

    def params(self, p):
        _lib.eui_nebula_params(_ptr(self.widget), ctypes.byref(p))

    def overlay(self, pm):
        _lib.eui_nebula_overlay(_ptr(self.widget), _ptr(pm))

    def scale(self, value: float):
        """>1 — облако компактнее; 1 — обычный масштаб."""
        _lib.eui_nebula_scale(_ptr(self.widget), float(value))

    def burst(self, value: float):
        """Вспышка при включении волны: 1 — лучи вылетают, 0 — спокойно."""
        _lib.eui_nebula_burst(_ptr(self.widget), float(value))


# ── кадры смены страниц на видеокарте (transition_gl.cpp) ──────────────── #

class TransitionGL:
    """GL-слой поверх стека страниц на время перехода: снимки — текстурами, кадр смешивает GPU."""

    def __init__(self):
        self.widget = _wrap(_lib.eui_trans_new())

    def ok(self) -> bool:
        return bool(_lib.eui_trans_ok(_ptr(self.widget)))

    def old(self, pm):
        _lib.eui_trans_old(_ptr(self.widget), _ptr(pm) if pm is not None and not pm.isNull() else None)

    def new_image(self, pm):
        _lib.eui_trans_new_image(_ptr(self.widget), _ptr(pm) if pm is not None and not pm.isNull() else None)

    def frame(self, kind: int, e: float, dx: float = 0.0, dy: float = 0.0):
        _lib.eui_trans_frame(_ptr(self.widget), int(kind), float(e), float(dx), float(dy))

    def grab(self):
        """Текущий кадр перехода (для снимка, если переход прерывают новым)."""
        from PyQt6.QtOpenGLWidgets import QOpenGLWidget
        return QPixmap_from(sip.wrapinstance(_ptr(self.widget), QOpenGLWidget).grabFramebuffer())


def fire_draw(painter, cw: float, ch: float, margin: float, color, tier: int, now: float, quality: int) -> bool:
    """Огонь вокруг карточки дуэли шейдером (fire_gl.cpp) — внутри paintGL, с текущим преобразованием
    QPainter (центр карточки в 0,0). False — нарисовать не вышло (рисуйте по-старому)."""
    dev = painter.device()
    dpr = dev.devicePixelRatioF()
    t = painter.combinedTransform()
    col = QColor(color)
    painter.beginNativePainting()
    try:
        return bool(_lib.eui_fire_draw(_ptr(t), dpr, dev.width() * dpr, dev.height() * dpr, cw, ch, margin,
                                       _ptr(col), int(tier), float(now % 900.0), float(painter.opacity()), int(quality)))
    finally:
        painter.endNativePainting()


class ScrollGL:
    """GL-слой прокрутки (scroll_gl.cpp): фон и плитки содержимого — текстурами, кадр — только сдвиг."""

    def __init__(self):
        self.widget = _wrap(_lib.eui_scroll_new())

    def ok(self) -> bool:
        return bool(_lib.eui_scroll_ok(_ptr(self.widget)))

    def backdrop(self, img):
        _lib.eui_scroll_backdrop(_ptr(self.widget), _ptr(img))

    def tile(self, i: int, img):
        _lib.eui_scroll_tile(_ptr(self.widget), int(i), _ptr(img))

    def drop(self, i: int):
        _lib.eui_scroll_drop(_ptr(self.widget), int(i))

    def release(self):
        _lib.eui_scroll_release(_ptr(self.widget))

    def frame(self, off: float, tile_h: int):
        _lib.eui_scroll_frame(_ptr(self.widget), float(off), int(tile_h))


def QPixmap_from(img):
    from PyQt6.QtGui import QPixmap
    return QPixmap.fromImage(img)
