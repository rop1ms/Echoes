# player_prefs.py
"""Настройки плеера, которые работают в любой теме: горячие клавиши (в окне и везде — карточка в Настройках
Echoes Music → Инструменты), размер и пропорции окна. Окно «Окно и масштаб» — Ctrl+,.

Модуль самостоятельный: подключается одной строкой в main.py (install(win)) и ничего не правит
в чужих файлах — встроенные сочетания отключает, пластинку дорисовывает обёрткой VinylWidget.
"""
from __future__ import annotations

import data_home
import ctypes
import os
import shutil
import sys
from pathlib import Path

from img_load import load_pixmap
from PyQt6.QtCore import Qt, QObject, QEvent, QTimer, QAbstractNativeEventFilter, QPointF, QSize
from PyQt6.QtGui import QKeySequence, QShortcut, QPixmap, QPainter, QPainterPath, QColor, QPen, QIcon
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QKeySequenceEdit,
                             QCheckBox, QComboBox, QFrame, QApplication, QDoubleSpinBox, QScrollArea, QWidget)

DATA = data_home.root()

ACTIONS = [  # (ключ, название, сочетание по умолчанию — как было зашито в плеере)
    ("play_pause", "Пауза / воспроизведение", "Space"),
    ("prev", "Предыдущий трек", "Left"),
    ("next", "Следующий трек", "Right"),
    ("repeat", "Режим повтора", "Ctrl+R"),
    ("shuffle", "Перемешивание", "Ctrl+S"),
    ("vol_up", "Громче", "Ctrl+Alt+Up"),                    # дальше — ya_quick
    ("vol_down", "Тише", "Ctrl+Alt+Down"),
    ("mute", "Без звука / вернуть", "Ctrl+Alt+M"),
    ("like", "Мне нравится (играющий трек)", "Ctrl+Alt+L"),
    ("add_pl", "Играющий — в плейлист…", "Ctrl+Alt+P"),
    ("mini", "Мини-плеер поверх окон", "Ctrl+Alt+N"),
    ("show", "Показать / свернуть ECHOES", "Ctrl+Alt+E"),
    ("palette", "Палитра команд (только в окне)", "Ctrl+K"),
    ("voice", "Сказать голосовую команду", "Ctrl+Alt+V"),
]
LOCAL_ONLY = {"palette"}                                   # Ctrl+K нужен браузерам — не перехватывать везде

ASPECTS = [  # (ключ, название, w/h, готовые размеры)
    ("free", "Свободно", None, []),
    ("16:9", "16:9 — широкий", 16 / 9, [(1280, 720), (1600, 900), (1920, 1080), (2560, 1440)]),
    ("16:10", "16:10", 16 / 10, [(1280, 800), (1440, 900), (1680, 1050), (1920, 1200)]),
    ("4:3", "4:3 — классический", 4 / 3, [(1024, 768), (1280, 960), (1440, 1080), (1600, 1200)]),
    ("21:9", "21:9 — ультраширокий", 21 / 9, [(1680, 720), (2100, 900), (2520, 1080)]),
    ("1:1", "1:1 — квадрат", 1.0, [(720, 720), (900, 900), (1080, 1080)]),
    ("9:16", "9:16 — вертикальный", 9 / 16, [(540, 960), (720, 1280), (810, 1440)]),
]


def _save(win):
    try:
        mod = sys.modules.get(type(win).__module__)       # main.py запущен как __main__ — не импортировать заново
        mod.save_json(mod.SETTINGS_FILE, win.settings)
    except Exception as e:                                 # noqa: BLE001
        print("[prefs] save:", e)


# ══════════════════════════════════════════════════════════════════════════ #
#  Горячие клавиши
# ══════════════════════════════════════════════════════════════════════════ #

def _do(win, key):
    try:
        if key == "play_pause":
            win.toggle_play()
        elif key == "prev":
            win.prev_track()
        elif key == "next":
            win.next_track()
        elif key == "repeat":
            win._cycle_repeat()
        elif key == "shuffle":
            win.btn_shuffle.click()                        # как было в плеере (кнопка сама переключает режим)
        else:
            import ya_quick
            ya_quick.do(win, key)
    except Exception as e:                                 # noqa: BLE001
        print("[prefs] действие", key, e)


def binds(win) -> dict:
    """Сочетания в окне ECHOES (пробел, стрелки…)."""
    b = dict((k, d) for k, _t, d in ACTIONS)
    b.update({k: v for k, v in (win.settings.get("keybinds") or {}).items() if k in b})
    return b


def global_binds(win) -> dict:
    """Сочетания везде в системе — отдельно от сочетаний в окне. Раньше был один набор и галочка
    «работают везде»: при первом чтении он переносится сюда как был."""
    st = win.settings
    if not isinstance(st.get("keybinds_global_map"), dict):
        old = binds(win) if st.get("keybinds_global") else {}
        # пробел/стрелки без Ctrl/Alt глобально ломали бы ввод в других программах — их не переносим
        st["keybinds_global_map"] = {k: v for k, v in old.items() if k not in LOCAL_ONLY and _to_win(v)}
    keys = {k for k, _t, _d in ACTIONS if k not in LOCAL_ONLY}
    return {k: v for k, v in st["keybinds_global_map"].items() if k in keys and v}


_VK = {Qt.Key.Key_Space: 0x20, Qt.Key.Key_Left: 0x25, Qt.Key.Key_Up: 0x26, Qt.Key.Key_Right: 0x27,
       Qt.Key.Key_Down: 0x28, Qt.Key.Key_Return: 0x0D, Qt.Key.Key_Enter: 0x0D, Qt.Key.Key_Tab: 0x09,
       Qt.Key.Key_Home: 0x24, Qt.Key.Key_End: 0x23, Qt.Key.Key_PageUp: 0x21, Qt.Key.Key_PageDown: 0x22,
       Qt.Key.Key_Insert: 0x2D, Qt.Key.Key_Delete: 0x2E, Qt.Key.Key_Pause: 0x13,
       Qt.Key.Key_MediaPlay: 0xB3, Qt.Key.Key_MediaTogglePlayPause: 0xB3, Qt.Key.Key_MediaNext: 0xB0,
       Qt.Key.Key_MediaPrevious: 0xB1, Qt.Key.Key_MediaStop: 0xB2,
       Qt.Key.Key_Comma: 0xBC, Qt.Key.Key_Period: 0xBE, Qt.Key.Key_Minus: 0xBD, Qt.Key.Key_Equal: 0xBB,
       Qt.Key.Key_Slash: 0xBF, Qt.Key.Key_Semicolon: 0xBA, Qt.Key.Key_BracketLeft: 0xDB,
       Qt.Key.Key_BracketRight: 0xDD}


def _to_win(seq_text):
    """«Ctrl+Shift+P» → (модификаторы RegisterHotKey, VK) или None."""
    seq = QKeySequence(seq_text)
    if seq.isEmpty():
        return None
    kc = seq[0]
    key, mods = kc.key(), kc.keyboardModifiers()
    m = 0
    if mods & Qt.KeyboardModifier.AltModifier:
        m |= 0x1
    if mods & Qt.KeyboardModifier.ControlModifier:
        m |= 0x2
    if mods & Qt.KeyboardModifier.ShiftModifier:
        m |= 0x4
    if mods & Qt.KeyboardModifier.MetaModifier:
        m |= 0x8
    k = key.value if hasattr(key, "value") else int(key)
    if Qt.Key.Key_A.value <= k <= Qt.Key.Key_Z.value or Qt.Key.Key_0.value <= k <= Qt.Key.Key_9.value:
        vk = k
    elif Qt.Key.Key_F1.value <= k <= Qt.Key.Key_F24.value:
        vk = 0x70 + (k - Qt.Key.Key_F1.value)
    else:
        vk = _VK.get(key)
    if not vk:
        return None
    media = vk in (0xB0, 0xB1, 0xB2, 0xB3, 0x13) or 0x70 <= vk <= 0x87
    if not m and not media:
        return None                                       # «Пробел» без Ctrl/Alt сломал бы ввод во всех программах
    return (m | 0x4000, vk)                               # 0x4000 = MOD_NOREPEAT


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.ids = {}

    def nativeEventFilter(self, etype, message):
        try:
            if etype in (b"windows_generic_MSG", "windows_generic_MSG"):
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0312 and msg.wParam in self.ids:      # WM_HOTKEY
                    key = self.ids[msg.wParam]
                    QTimer.singleShot(0, lambda: _do(self.win, key))
                    return True, 0
        except Exception:                                  # noqa: BLE001
            pass
        return False, 0


class Keys:
    """Сочетания из настроек: в окне плеера (QShortcut) или везде в системе (RegisterHotKey)."""

    def __init__(self, win):
        self.win = win
        self.shortcuts = []
        self.filter = None
        self.registered = []
        self.failed = []
        self._disable_builtin()
        self.apply()

    def _disable_builtin(self):
        """Встроенные сочетания для тех же действий выключаем — иначе старое и новое сработают вместе."""
        defaults = {QKeySequence(d).toString() for _k, _t, d in ACTIONS}
        for sc in self.win.findChildren(QShortcut):
            if sc.parent() is self.win and sc.key().toString() in defaults and not getattr(sc, "_prefs", False):
                sc.setEnabled(False)

    def _clear(self):
        for sc in self.shortcuts:
            sc.setEnabled(False)
            sc.deleteLater()
        self.shortcuts = []
        if sys.platform.startswith("win") and self.registered:
            hwnd = int(self.win.winId())
            for hid in self.registered:
                ctypes.windll.user32.UnregisterHotKey(hwnd, hid)
        self.registered = []
        if self.filter is not None:
            self.filter.ids = {}

    def apply(self):
        """В окне — QShortcut по сочетаниям binds(); везде — RegisterHotKey по global_binds()."""
        self._clear()
        self.failed = []
        for key, seq in binds(self.win).items():
            if not seq:
                continue
            sc = QShortcut(QKeySequence(seq), self.win)
            sc._prefs = True
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(lambda k=key: _do(self.win, k))
            self.shortcuts.append(sc)
        glob = global_binds(self.win) if sys.platform.startswith("win") else {}
        if not glob:
            return
        if self.filter is None:
            self.filter = _HotkeyFilter(self.win)
            QApplication.instance().installNativeEventFilter(self.filter)
        hwnd = int(self.win.winId())
        order = [k for k, _t, _d in ACTIONS]
        for key, seq in glob.items():
            wk = _to_win(seq)
            hid = 0xB000 + order.index(key)
            if wk and ctypes.windll.user32.RegisterHotKey(hwnd, hid, wk[0], wk[1]):
                self.registered.append(hid)
                self.filter.ids[hid] = key
            else:
                self.failed.append(seq)                    # занято другой программой или без Ctrl/Alt/Shift/Win


# ══════════════════════════════════════════════════════════════════════════ #
#  Размер и пропорции окна
# ══════════════════════════════════════════════════════════════════════════ #

def _aspect(win):
    k = win.settings.get("win_aspect", "free")
    return next((a for a in ASPECTS if a[0] == k), ASPECTS[0])


class AspectLock(QObject):
    """Держит пропорции окна при растягивании (кроме «развёрнуто» и «на весь экран»)."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self._busy = False
        self._last = win.size()
        win.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if obj is self.win and ev.type() == QEvent.Type.Resize and not self._busy:
            ratio = _aspect(self.win)[2]
            w = self.win
            if ratio and not (w.isMaximized() or w.isFullScreen() or w.isMinimized()):
                s = ev.size()
                dw, dh = abs(s.width() - self._last.width()), abs(s.height() - self._last.height())
                if dw >= dh:
                    nw, nh = s.width(), round(s.width() / ratio)
                else:
                    nw, nh = round(s.height() * ratio), s.height()
                if (nw, nh) != (s.width(), s.height()):
                    self._busy = True
                    QTimer.singleShot(0, lambda: self._fix(nw, nh))
            self._last = ev.size()
        return False

    def _fix(self, w, h):
        try:
            self.win.resize(w, h)
        finally:
            self._busy = False


def apply_size(win, w, h):
    """Развернуть в обычное окно нужного размера (не больше экрана), по центру экрана."""
    if win.isMaximized() or win.isFullScreen():
        win.showNormal()
    scr = (win.screen() or QApplication.primaryScreen()).availableGeometry()
    k = min(1.0, scr.width() / w, scr.height() / h)
    w, h = int(w * k), int(h * k)
    win.resize(w, h)
    win.move(scr.x() + (scr.width() - w) // 2, scr.y() + (scr.height() - h) // 2)


# ══════════════════════════════════════════════════════════════════════════ #
#  Своя картинка вместо пластинки
# ══════════════════════════════════════════════════════════════════════════ #

_VINYL = {"pm": None, "path": ""}  # QPixmap requires an existing QApplication.


def set_vinyl_image(win, path):
    """Скопировать картинку к себе (чтобы не пропала, если исходник удалят) и показать на пластинке."""
    if path:
        d = DATA / "vinyl"
        d.mkdir(parents=True, exist_ok=True)
        dst = d / ("custom" + Path(path).suffix.lower())
        for old in d.glob("custom.*"):
            if old != dst:
                old.unlink(missing_ok=True)
        if Path(path).resolve() != dst.resolve():
            shutil.copyfile(path, dst)
        path = str(dst)
    win.settings["vinyl_image"] = path or ""
    _load_vinyl(path)
    v = getattr(win, "vinyl", None)
    if v is not None:
        v._real_key = None                                 # перестроить слои пластинки
        v.__dict__.pop("_cv_key", None)
        v.update()


def apply_vinyl_image(win, path):
    """Картинка вместо диска пластинки (vinyl.py) — задаётся темой из конструктора; "" — обычный диск.
    В настройках плеера её больше нет: только конструктор, только для своей темы."""
    if path == _VINYL["path"] or (not path and (_VINYL["pm"] is None or _VINYL["pm"].isNull())):
        return
    _load_vinyl(path)
    v = getattr(win, "vinyl", None)
    if v is not None:
        v._real_key = None                                 # перестроить слои пластинки
        v.__dict__.pop("_cv_key", None)
        v.update()


def _load_vinyl(path):
    pm = load_pixmap(path, 2048) if path and os.path.exists(path) else QPixmap()
    _VINYL["pm"], _VINYL["path"] = pm, (path if not pm.isNull() else "")


def _wrap_vinyl():
    try:
        import vinyl as V
    except Exception as e:                                 # noqa: BLE001
        print("[prefs] vinyl:", e)
        return
    cls = V.VinylWidget
    if getattr(cls, "_prefs_wrapped", False):
        return
    orig = cls._real_layers

    def _real_layers(self, r):
        static, spin, sheen = orig(self, r)
        pm = _VINYL["pm"]
        if pm is None or pm.isNull():
            return static, spin, sheen
        dpr = max(1.0, float(self.devicePixelRatioF()))
        key = (int(r), dpr, pm.cacheKey())
        if self.__dict__.get("_cv_key") != key:
            S = int(r * 2) + 4
            out = QPixmap(int(S * dpr), int(S * dpr))
            out.setDevicePixelRatio(dpr)
            out.fill(Qt.GlobalColor.transparent)
            q = QPainter(out)
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            q.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            q.translate(S / 2.0, S / 2.0)
            rr = r * 0.985
            clip = QPainterPath()
            clip.addEllipse(QPointF(0, 0), rr, rr)
            q.setClipPath(clip)
            d = max(2, int(rr * 2 * dpr))
            sc = pm.scaled(d, d, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                           Qt.TransformationMode.SmoothTransformation)
            sc.setDevicePixelRatio(dpr)
            q.drawPixmap(QPointF(-sc.width() / (2 * dpr), -sc.height() / (2 * dpr)), sc)
            # лёгкие бороздки поверх картинки — всё ещё похоже на пластинку
            q.setBrush(Qt.BrushStyle.NoBrush)
            g, i = r - 16, 0
            while g > r * 0.2:
                q.setPen(QPen(QColor(0, 0, 0, 22 if i % 2 else 14), 1))
                q.drawEllipse(QPointF(0, 0), g, g)
                g -= 6
                i += 1
            q.setClipping(False)
            q.setPen(QPen(QColor(0, 0, 0, 120), 2))
            q.drawEllipse(QPointF(0, 0), rr, rr)
            q.setPen(Qt.PenStyle.NoPen)
            q.setBrush(QColor(10, 10, 11))
            q.drawEllipse(QPointF(0, 0), 4.6, 4.6)          # шпиндель
            q.end()
            self._cv_key, self._cv_spin = key, out
        empty = self.__dict__.get("_cv_static")
        if empty is None or empty.size() != static.size():
            empty = QPixmap(static.size())
            empty.setDevicePixelRatio(static.devicePixelRatio())
            empty.fill(Qt.GlobalColor.transparent)
            self._cv_static = empty
        return empty, self._cv_spin, sheen

    cls._real_layers = _real_layers
    cls._prefs_wrapped = True


# ══════════════════════════════════════════════════════════════════════════ #
#  Окно настроек
# ══════════════════════════════════════════════════════════════════════════ #

QSS = """
QDialog { background: #141418; }
QLabel { color: #e9e9ee; background: transparent; }
QLabel#H { font-size: 15px; font-weight: 800; padding-top: 8px; }
QLabel#Sub { color: #8b8b96; font-size: 11px; }
QPushButton, QComboBox, QKeySequenceEdit, QLineEdit { background: #222228; color: #ececf2; border: 1px solid #33333c;
    border-radius: 12px; padding: 6px 12px; min-height: 18px; }
QPushButton:hover { border-color: #ffdb4d; }
QPushButton#Accent { background: #ffdb4d; color: #111; border: none; font-weight: 700; }
QCheckBox { color: #e9e9ee; }
QFrame#Card { background: #1b1b21; border-radius: 16px; }
"""


class PrefsDialog(QDialog):
    def __init__(self, win, keys):
        super().__init__(win)
        self.win, self.keys = win, keys
        self.setWindowTitle("Окно и масштаб")
        self.setStyleSheet(QSS)
        self.setMinimumWidth(520)
        self.resize(560, 760)
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        v = QVBoxLayout(content)
        v.setSpacing(10)

        keys_moved = QPushButton("Горячие клавиши — в Настройках → Инструменты")
        keys_moved.clicked.connect(lambda: (self.accept(), open_keybinds(win)))
        v.addWidget(keys_moved)

        # ── окно ──
        v.addWidget(self._h("Размер окна", "Пропорции держатся, когда тянете край окна. «Развернуть» и F11 — как обычно."))
        card, h = self._card(QGridLayout)
        h.addWidget(QLabel("Пропорции"), 0, 0)
        self.cb_aspect = QComboBox()
        for k, title, _r, _s in ASPECTS:
            self.cb_aspect.addItem(title, k)
        self.cb_aspect.setCurrentIndex(max(0, self.cb_aspect.findData(win.settings.get("win_aspect", "free"))))
        self.cb_aspect.currentIndexChanged.connect(self._aspect_changed)
        h.addWidget(self.cb_aspect, 0, 1)
        h.addWidget(QLabel("Разрешение"), 1, 0)
        self.cb_size = QComboBox()
        h.addWidget(self.cb_size, 1, 1)
        go = QPushButton("Применить")
        go.setObjectName("Accent")
        go.clicked.connect(self._apply_size)
        h.addWidget(go, 1, 2)
        v.addWidget(card)
        self._fill_sizes()

        card, scale_form = self._card(QGridLayout)
        for row, (key, title) in enumerate((("ui_scale", "Масштаб интерфейса"),
                                           ("font_scale", "Масштаб шрифта"))):
            scale_form.addWidget(QLabel(title), row, 0)
            spin = QDoubleSpinBox()
            spin.setRange(0.75, 2.5)
            spin.setSingleStep(0.05)
            spin.setSuffix(" ×")
            spin.setValue(float(win.settings.get(key, 1)))
            spin.valueChanged.connect(lambda value, key=key: (win.settings.__setitem__(key, value), _save(win)))
            scale_form.addWidget(spin, row, 1)
        scale_form.addWidget(QLabel("Масштаб применяется после перезапуска во всех темах."), 2, 0, 1, 2)
        v.addWidget(card)
        tools = QPushButton("Анимации, память и инструменты слушателя…")
        tools.clicked.connect(lambda: win._listening_tools.open())
        v.addWidget(tools)
        commands = QPushButton("Палитра команд — Ctrl+Shift+P")
        commands.clicked.connect(lambda: win._listening_tools.palette())
        v.addWidget(commands)
        lyrics = QPushButton("Текст: перевод, оформление и прокрутка…")
        lyrics.clicked.connect(win._lyrics_options.open)
        v.addWidget(lyrics)
        stream = QPushButton("Конструктор окна стримера…")
        stream.clicked.connect(lambda: __import__('stream_designer').StreamEditor(win).exec())
        v.addWidget(stream)

        ok = QPushButton("Готово")
        ok.setObjectName("Accent")
        ok.clicked.connect(self.accept)
        v.addWidget(ok, 0, Qt.AlignmentFlag.AlignRight)

    def _h(self, title, sub):
        w = QFrame()
        l = QVBoxLayout(w)
        l.setContentsMargins(2, 0, 2, 0)
        l.setSpacing(0)
        a = QLabel(title)
        a.setObjectName("H")
        b = QLabel(sub)
        b.setObjectName("Sub")
        b.setWordWrap(True)
        l.addWidget(a)
        l.addWidget(b)
        return w

    def _card(self, lay_cls):
        c = QFrame()
        c.setObjectName("Card")
        l = lay_cls(c)
        l.setContentsMargins(14, 12, 14, 12)
        return c, l

    # окно
    def _fill_sizes(self):
        self.cb_size.clear()
        a = _aspect_by(self.cb_aspect.currentData())
        if not a[3]:
            self.cb_size.addItem("— выберите пропорции —", None)
            self.cb_size.setEnabled(False)
            return
        self.cb_size.setEnabled(True)
        for w, h in a[3]:
            self.cb_size.addItem(f"{w} × {h}", (w, h))

    def _aspect_changed(self):
        self.win.settings["win_aspect"] = self.cb_aspect.currentData()
        _save(self.win)
        self._fill_sizes()
        a = _aspect_by(self.cb_aspect.currentData())
        if a[2] and not (self.win.isMaximized() or self.win.isFullScreen()):
            w = self.win.width()                           # сразу привести окно к пропорциям
            apply_size(self.win, w, round(w / a[2]))

    def _apply_size(self):
        s = self.cb_size.currentData()
        if s:
            apply_size(self.win, *s)
            self.win.settings["win_size"] = list(s)
            _save(self.win)


def _aspect_by(key):
    return next((a for a in ASPECTS if a[0] == key), ASPECTS[0])


# ══════════════════════════════════════════════════════════════════════════ #

def open_dialog(win):
    st = win.__dict__.get("_prefs")
    if st is None:
        return
    dlg = PrefsDialog(win, st["keys"])
    try:
        import inapp
        inapp.present(win, dlg, "Окно и масштаб")
    except Exception:                                      # noqa: BLE001
        dlg.show()


def open_keybinds(win):
    """Карточка горячих клавиш живёт в Настройках Echoes Music → Инструменты."""
    shell = getattr(win, "_ya", None)
    hub = getattr(shell, "settings_hub", None) if shell is not None else None
    try:
        shell.show_page("settings")
        if hub is not None:
            hub.select("tools")
        card = getattr(shell, "_keybinds_card", None)
        if card is not None:
            QTimer.singleShot(50, lambda: shell.pages["settings"].ensureWidgetVisible(card))
    except Exception as e:                                 # noqa: BLE001
        print("[prefs] keybinds:", e)


def keybinds_card(win):
    """Горячие клавиши: два набора — в окне ECHOES и везде в системе."""
    from echo_glass import GlassFrame, glass_controls_qss
    card = GlassFrame(radius=16)
    card.setMaximumWidth(800)
    card.setStyleSheet("QLabel,QCheckBox{color:#edf3fb;background:transparent;}"
                       "QLabel#YaSub{color:#a8b5c6;} QLabel#Col{color:#a8b5c6;font-weight:700;}"
                       "QPushButton{border-radius:10px;padding:6px 12px;}"
                       "QKeySequenceEdit,QLineEdit{border-radius:8px;padding:4px 8px;}" + glass_controls_qss())
    v = QVBoxLayout(card)
    v.setContentsMargins(18, 16, 18, 16)
    title = QLabel("Горячие клавиши")
    title.setStyleSheet("font-size:15px;font-weight:700;background:transparent;")
    v.addWidget(title)
    sub = QLabel("«В ECHOES» — когда окно плеера активно (пробел, стрелки…). «Везде» — даже когда плеер "
                 "свёрнут или вы в другой программе: только с Ctrl, Alt, Shift или Win (или F-клавиша / "
                 "медиаклавиша). Щёлкните по полю и нажмите сочетание; пусто — без клавиши.")
    sub.setObjectName("YaSub")
    sub.setWordWrap(True)
    v.addWidget(sub)
    g = QGridLayout()
    g.setHorizontalSpacing(8)
    g.setVerticalSpacing(6)
    for c, text in ((1, "В ECHOES"), (3, "Везде")):
        h = QLabel(text)
        h.setObjectName("Col")
        g.addWidget(h, 0, c)
    local_edits, global_edits = {}, {}
    note = QLabel("")
    note.setObjectName("YaSub")
    note.setWordWrap(True)

    def read(edits) -> dict:
        out = {}
        for k, e in edits.items():
            try:
                out[k] = e.keySequence().toString()
            except RuntimeError:                           # поле уже удалено (страницу пересобрали) — пропустить
                pass
        return out

    def save():
        # Сначала — в настройки и на диск, потом регистрация клавиш: ошибка регистрации (или одно сломанное поле)
        # раньше обрывала сохранение целиком, и после перезапуска сочетания возвращались к прежним.
        keys = (win.__dict__.get("_prefs") or {}).get("keys")      # карточку строят раньше install()
        win.settings["keybinds"] = dict(binds(win), **read(local_edits))
        gmap = dict(win.settings.get("keybinds_global_map") or {})
        gmap.update(read(global_edits))
        win.settings["keybinds_global_map"] = gmap
        win.settings.pop("keybinds_global", None)
        _save(win)
        if keys is not None:
            try:
                keys.apply()
            except Exception as e:                         # noqa: BLE001
                print("[prefs] keybinds apply:", e)
        msgs = []
        for name, values in (("в ECHOES", win.settings["keybinds"]), ("везде", win.settings["keybinds_global_map"])):
            seqs = [x for x in values.values() if x]
            dup = sorted({x for x in seqs if seqs.count(x) > 1})
            if dup:
                msgs.append(f"Одно сочетание на два действия ({name}): " + ", ".join(dup))
        if keys is not None and keys.failed:
            msgs.append("Не работают везде (заняты другой программой или без Ctrl/Alt/Shift/Win): "
                        + ", ".join(keys.failed))
        try:
            note.setText("  ·  ".join(msgs))
        except RuntimeError:
            pass

    later = QTimer(card)                                   # сохранить и без «редактирование закончено»:
    later.setSingleShot(True)                              # сразу после того, как сочетание в поле изменилось
    later.setInterval(400)
    later.timeout.connect(save)

    def edit(seq, row, col, store, key):
        e = QKeySequenceEdit(QKeySequence(seq))
        if hasattr(e, "setMaximumSequenceLength"):
            e.setMaximumSequenceLength(1)
        e.setMinimumWidth(150)
        from PyQt6.QtWidgets import QLineEdit
        for le in e.findChildren(QLineEdit):
            le.setPlaceholderText("Нажмите сочетание")
        e.editingFinished.connect(save)
        e.keySequenceChanged.connect(lambda _seq: later.start())
        g.addWidget(e, row, col)
        clr = QPushButton("✕")
        clr.setToolTip("Без клавиши")
        clr.setFixedWidth(36)
        clr.clicked.connect(lambda _=False, ed=e: (ed.clear(), save()))
        g.addWidget(clr, row, col + 1)
        store[key] = e

    local, glob = binds(win), global_binds(win)
    for r, (k, text, _d) in enumerate(ACTIONS, start=1):
        g.addWidget(QLabel(text), r, 0)
        edit(local.get(k, ""), r, 1, local_edits, k)
        if k in LOCAL_ONLY:
            only = QLabel("только в окне")
            only.setObjectName("YaSub")
            g.addWidget(only, r, 3, 1, 2)
        else:
            edit(glob.get(k, ""), r, 3, global_edits, k)
    g.setColumnStretch(0, 1)
    v.addLayout(g)
    row = QHBoxLayout()
    reset = QPushButton("Сбросить как было")

    def do_reset():
        for k, _t, d in ACTIONS:
            local_edits[k].setKeySequence(QKeySequence(d))
        for e in global_edits.values():
            e.clear()
        save()
    reset.clicked.connect(do_reset)
    row.addWidget(reset)
    row.addStretch(1)
    v.addLayout(row)
    v.addWidget(note)
    return card


def _cleanup_tiktok():
    """TikTok удалён — убрать его остатки (кэш роликов, профиль браузера), если они ещё на диске."""
    for d in (DATA / "tiktok_cache", DATA / "web"):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)


def install(win):
    if win.__dict__.get("_prefs") is not None:
        return
    from lyrics_options import LyricsOptions
    win._lyrics_options = LyricsOptions(win)
    win._lyrics_options.set_lyrics(win.lyrics_box.toPlainText())
    _cleanup_tiktok()
    _wrap_vinyl()
    win.settings.pop("vinyl_image", None)                  # общая «своя пластинка» убрана — теперь только в теме
    _load_vinyl("")
    keys = Keys(win)
    lock = AspectLock(win)
    sc = QShortcut(QKeySequence("Ctrl+,"), win)
    sc._prefs = True
    sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
    sc.activated.connect(lambda: open_dialog(win))
    win._prefs = {"keys": keys, "lock": lock, "open": sc}
    win.open_player_prefs = lambda: open_dialog(win)
    s = win.settings.get("win_size")
    if s and win.settings.get("win_aspect", "free") != "free":
        QTimer.singleShot(0, lambda: apply_size(win, int(s[0]), int(s[1])))
