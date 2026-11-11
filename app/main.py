# main.py
import startup_trace as _strace            # ECHOES_STARTUP_TRACE — замер времени запуска (qa/probe_startup_time.py)
_strace.mark("python")
import boot_guard                          # откат версии, которая дважды не запустилась
if __name__ == "__main__":
    boot_guard.enter()
import data_home
if __name__ == "__main__":                  # папка данных ~/.neon_player → ~/Echoes — до того, как что-то её откроет
    _moved = data_home.migrate()
    if _moved:
        print("[data]", _moved)
import sys
try:                      # без мелькающих окон консоли у ffmpeg/yt-dlp/python-помощников (noflash.py)
    import noflash
    noflash.install()
except Exception as _e:   # noqa: BLE001
    print("[noflash]", _e)
import json
import random
import hashlib
import traceback
from pathlib import Path

# ── портативные VLC и ffmpeg, которые кладёт установщик ECHOES рядом с app\ ──
import os as _os
_APP_DIR = Path(__file__).resolve().parent
# запуск из папки исходников: рядом ffmpeg нет — берём установленный ECHOES, а не случайный из PATH
# (у некоторых в PATH лежит ffmpeg 2013 года из pip-пакета: он не понимает -hide_banner, и анализ звука
# — громкость, темп, жанр по звуку, припев в дуэли — молча ничего не находил)
_INST = Path(_os.environ.get("LOCALAPPDATA", "")) / "Programs" / "ECHOES"
for _d in (_APP_DIR.parent / "ffmpeg", _APP_DIR / "ffmpeg", _APP_DIR.parent / "vlc", _APP_DIR / "vlc"):
    if not _d.is_dir() and _d.parent == _APP_DIR.parent and (_INST / _d.name).is_dir():
        _d = _INST / _d.name
    if _d.is_dir():
        _os.environ["PATH"] = str(_d) + _os.pathsep + _os.environ.get("PATH", "")
try:                                                     # одна HTTP-сессия на весь плеер (net_pool.py)
    import net_pool as _net_pool
    _net_pool.install()
except Exception as _e:                                  # noqa: BLE001
    print("[net_pool]", _e)
# Математика numpy/scipy (OpenBLAS) по умолчанию держит буфер 32 МБ на КАЖДОЕ ядро процессора —
# на 12 ядрах это ~770 МБ памяти ещё до первой песни. Плееру хватает одного потока:
# тяжёлое (анализ треков, FFT) и так идёт в фоновых потоках, а не в BLAS.
for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ.setdefault(_v, "1")
# Звук выводит поток на Python: ему нужен GIL каждые 10 мс. По умолчанию занятый поток
# отдаёт GIL раз в 5 мс (а при нескольких потоках очередь выходит в десятки мс) — чаще
# передаём, чтобы тяжёлая отрисовка не опустошала звуковой буфер.
sys.setswitchinterval(0.002)
# C++-ядро эффектов (echoes_fx.dll, см. native_fx.py) можно выключить в настройках — модули
# эффектов решают это при импорте, поэтому настройку читаем до них.
try:
    _st = json.loads((data_home.root() / "settings.json").read_text(encoding="utf-8"))
    if isinstance(_st, dict) and _st.get("native_fx", True) is False:
        _os.environ["ECHOES_NO_NATIVE"] = "1"
except Exception:                                          # noqa: BLE001
    pass

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QSlider, QFileDialog,
    QTextEdit, QFrame, QComboBox, QCheckBox, QSpinBox, QMessageBox,
    QInputDialog, QSizePolicy, QSplitter, QLineEdit, QTabWidget, QAbstractItemView,
    QScrollArea, QMenu, QGridLayout
)
from PyQt6.QtCore import Qt, QTimer, QSize, QEvent, QAbstractNativeEventFilter, pyqtSignal, QPropertyAnimation, QEasingCurve, QRectF, QObject, QPoint
from PyQt6.QtGui import QPixmap, QShortcut, QKeySequence, QColor, QIcon, QImage, QPainter, QPainterPath, QFont
from PyQt6.QtWidgets import QGraphicsOpacityEffect
import datetime
import time


class _UiBridge(QObject):
    """Передаёт вызов из фонового потока в GUI-поток (queued-сигнал).
    QTimer.singleShot из обычного Python-потока ненадёжен: у потока нет
    цикла событий Qt, и таймер может так и не сработать."""
    call = pyqtSignal(object)


class PlayPauseButton(QPushButton):
    """Play/Pause без юникод-эмодзи (▶/⏸) — иконка рисуется вручную,
    поэтому не зависит от эмодзи-шрифта системы и выглядит одинаково везде."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._playing = False
        self._icon_color = QColor("#000000")
        self.setText("")

    def set_playing(self, playing: bool):
        self._playing = bool(playing)
        self.update()

    def set_icon_color(self, color: QColor):
        self._icon_color = QColor(color)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._icon_color)

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0

        if self._playing:
            bar_w, bar_h, gap = 4.5, 15.0, 5.5
            p.drawRoundedRect(QRectF(cx - gap - bar_w, cy - bar_h / 2, bar_w, bar_h), 1.5, 1.5)
            p.drawRoundedRect(QRectF(cx + gap, cy - bar_h / 2, bar_w, bar_h), 1.5, 1.5)
        else:
            side = 16.0
            path = QPainterPath()
            # небольшой сдвиг вправо — оптический центр треугольника иначе выглядит левее
            ox = cx - side * 0.32
            path.moveTo(ox, cy - side * 0.58)
            path.lineTo(ox, cy + side * 0.58)
            path.lineTo(ox + side * 0.66, cy)
            path.closeSubpath()
            p.drawPath(path)
        p.end()

from audio_engine import AudioEngine
from listen_stats import ListenStats, ProfileDialog
from loudness import LoudnessStore
from titlebar import TitleBar, EdgeResizer
from seekbar import FancySlider
import inapp
from search_util import matches as _words_match
from img_load import load_pixmap
import threading
from themes import THEMES, build_qss, theme_groups, register_custom_themes, CUSTOM_PREFIX
import theme_kit
from lyrics import fetch_lyrics, fetch_lyrics_ex, sanitize_title
from visualizer import Visualizer, MilkdropVisualizer
from vinyl import VinylWidget
from playlist_view import PlaylistDetailView
from lyrics_view import LyricsView
from ambience import BackgroundAmbience, DustParticles
from fluid_theme import FluidPanel, load_fonts   # тема «Fluid»: жидкая текстура + шрифты
from downloader_ui import DownloaderDialog
from lyrics_editor import LyricsEditorDialog
from lyrics_tags import read_local_lyrics
from smart_features import (
    get_daypart, DAYPART_RU, WEATHER_RU, fetch_weather, fallback_weather,
    build_smart_playlist, SleepTimer, PomodoroTimer, NoiseGenerator,
    pick_track_of_the_day,
)
try:
    from smart_features import get_weather, build_smart_playlist_v2
    import music_intel
except Exception as _e:                      # не мешаем запуску, если модуля нет
    print("[intel] недоступно:", _e)
    music_intel = None

try:
    from mutagen import File as MutaFile
except ImportError:
    MutaFile = None

DATA_DIR = data_home.root()
COVER_DIR = DATA_DIR / "covers"
DATA_DIR.mkdir(exist_ok=True)
try:                                                       # восстановление из копии — до чтения настроек
    import ya_backup as _ya_backup
    _restored_from = _ya_backup.apply_pending(DATA_DIR)
except Exception as _e:                                    # noqa: BLE001
    print("[backup]", _e)
COVER_DIR.mkdir(exist_ok=True)
LIB_FILE = DATA_DIR / "library.json"
LYRICS_CACHE_FILE = DATA_DIR / "lyrics_cache.json"
INTEL_FILE = DATA_DIR / "track_intel.json"
TIER_FILE = DATA_DIR / "music_tierlist.json"
PL_FILE = DATA_DIR / "playlists.json"
PROFILE_FILE = DATA_DIR / "profile.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
AUDIO_EXTS = {".mp3", ".ogg", ".wav", ".flac", ".m4a", ".opus"}

def load_json(path, default, validator=None):
    from atomic_json import load_json as read_profile_json
    return read_profile_json(path,default,validator=validator)

def load_library(path):
    records=load_json(path,[],validator=lambda rows:not rows or any(isinstance(row,dict) for row in rows))
    tracks=[record for record in records if isinstance(record,dict)]
    if len(tracks)!=len(records):
        print('[data] ignored invalid library records:',len(records)-len(tracks))
    return tracks

def save_json(path, obj):
    # Compact encoding stays in the C encoder; pretty-printing large settings
    # recursively in Python used an entire input frame on every slider step.
    from atomic_json import save_json_async               # диск — в фоновом потоке (atomic_json)
    if isinstance(obj, dict) and str(path).replace("\\", "/").endswith("/settings.json"):
        import settings_store                              # тяжёлые разделы — отдельными файлами, по изменению
        return settings_store.save(path, obj)
    return save_json_async(path,obj)


def _round_image(path, side: int, size: int):
    """Обложка → квадрат size×size со скруглением 30 % (как MainWindow._round_pixmap), но QImage:
    можно делать в фоновом потоке. None — файла нет или не читается."""
    from img_load import read_image
    src = read_image(path, side)
    if src.isNull():
        return None
    sc = src.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation)
    sc = sc.copy((sc.width() - size) // 2, (sc.height() - size) // 2, size, size)
    out = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path_ = QPainterPath()
    path_.addRoundedRect(0, 0, size, size, size * 0.30, size * 0.30)
    p.setClipPath(path_)
    p.drawImage(0, 0, sc)
    p.end()
    return out


HIDDEN_PL = "\u2063"          # префикс служебных очередей (онлайн-треки): не видны и не сохраняются


class PlaylistStore(dict):
    """Плейлисты. Ключи с HIDDEN_PL — служебные очереди воспроизведения (онлайн-треки из поиска/альбома):
    по имени доступны как обычный плейлист (get / [] / in — контекст играет, «дальше» работает), но в
    списках плейлистов (keys / items / values / for / len) и в playlists.json их нет."""

    def _vis(self):
        return [k for k in dict.keys(self) if not str(k).startswith(HIDDEN_PL)]

    def __iter__(self):
        return iter(self._vis())

    def keys(self):
        return self._vis()

    def items(self):
        return [(k, dict.__getitem__(self, k)) for k in self._vis()]

    def values(self):
        return [dict.__getitem__(self, k) for k in self._vis()]

    def __len__(self):
        return len(self._vis())

    def hidden(self):
        return [(k, dict.__getitem__(self, k)) for k in dict.keys(self) if str(k).startswith(HIDDEN_PL)]

    def copy(self):
        return dict(self.items())

class WindowsMediaKeyFilter(QAbstractNativeEventFilter):
    """Global Windows media-key bridge (works even when Neon Player is not focused)."""
    MEDIA_IDS = {
        0xB0: "next",        # VK_MEDIA_NEXT_TRACK
        0xB1: "prev",        # VK_MEDIA_PREV_TRACK
        0xB3: "toggle",      # VK_MEDIA_PLAY_PAUSE
        0xFA: "play",        # VK_MEDIA_PLAY
        0x13: "pause",       # VK_MEDIA_PAUSE
        0xB2: "stop",        # VK_MEDIA_STOP
    }
    HOTKEY_BASE = 0x4E500

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.registered = []

    _MSG = None                                        # структура MSG — создаётся один раз (nativeEventFilter)

    def register(self):
        if sys.platform != "win32":
            return
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = int(self.window.winId())
        # No modifiers: make media keys work regardless of focus.
        for i, vk in enumerate(self.MEDIA_IDS, start=1):
            hot_id = self.HOTKEY_BASE + i
            if user32.RegisterHotKey(hwnd, hot_id, 0, vk):
                self.registered.append((hot_id, self.MEDIA_IDS[vk]))

    def unregister(self):
        if sys.platform != "win32":
            return
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = int(self.window.winId())
        for hot_id, _ in self.registered:
            user32.UnregisterHotKey(hwnd, hot_id)
        self.registered.clear()

    def nativeEventFilter(self, eventType, message):
        if sys.platform != "win32" or eventType not in ("windows_generic_MSG", "windows_dispatcher_MSG"):
            return False, 0
        try:
            MSG = WindowsMediaKeyFilter._MSG
            if MSG is None:
                # один раз: раньше класс создавался на КАЖДОЕ сообщение Windows (движение мыши, отрисовка,
                # таймеры — тысячи в секунду) и каждый раз оставлял циклический мусор сборщику
                import ctypes

                class MSG(ctypes.Structure):
                    _fields_ = [
                        ("hwnd", ctypes.c_void_p), ("message", ctypes.c_uint),
                        ("wParam", ctypes.c_size_t), ("lParam", ctypes.c_ssize_t),
                        ("time", ctypes.c_uint), ("pt_x", ctypes.c_long), ("pt_y", ctypes.c_long),
                    ]
                WindowsMediaKeyFilter._MSG = MSG
            msg = MSG.from_address(int(message))
            if msg.message != 0x0312:  # WM_HOTKEY
                return False, 0
            hot_id = int(msg.wParam)
            action = dict(self.registered).get(hot_id)
            if not action:
                return False, 0
            if action == "next": self.window.next_track()
            elif action == "prev": self.window.prev_track()
            elif action in ("toggle", "play", "pause"):
                if action == "play" and self.window.engine.is_playing():
                    return True, 0
                if action == "pause" and not self.window.engine.is_playing():
                    return True, 0
                self.window.toggle_play()
            elif action == "stop":
                self.window.engine.stop()
                self.window._set_playing_ui(False)
            return True, 0
        except Exception as e:
            print("[media keys]", e)
            return False, 0

# Классические пресеты эквалайзера: 10 полос (31, 62, 125, 250, 500 Гц, 1, 2, 4, 8, 16 кГц — полосы VLC), дБ
EQ_PRESETS = (
    ("Плоский",            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
    ("Рок",                [5, 4, 3, 1, -1, -1, 2, 4, 5, 6]),
    ("Поп",                [-1, 2, 4, 5, 3, 0, -1, -1, -1, -2]),
    ("Джаз",               [4, 3, 1, 2, -2, -2, 0, 1, 3, 4]),
    ("Классика",           [5, 4, 3, 2, -1, -1, 0, 2, 3, 4]),
    ("Акустика",           [4, 3, 2, 1, 2, 2, 3, 3, 3, 2]),
    ("Живой звук",         [-3, 0, 3, 4, 4, 4, 3, 2, 2, 2]),
    ("Лаунж",              [-3, -1, 2, 4, 2, -1, -2, 1, 3, 2]),
    ("Вокал",              [-3, -2, -1, 2, 5, 5, 4, 2, 0, -1]),
    ("Бас",                [8, 7, 5, 3, 1, 0, 0, 0, 0, 0]),
    ("Высокие",            [0, 0, 0, 0, 0, 1, 3, 5, 7, 8]),
    ("Бас + высокие",      [6, 5, 2, 0, -2, -2, 0, 3, 5, 6]),
    ("Танцевальная",       [7, 6, 3, 0, 0, -3, -4, -4, 0, 0]),
    ("Электронная",        [5, 4, 1, 0, -2, 2, 1, 2, 4, 5]),
    ("Техно",              [6, 4, 0, -4, -3, 0, 5, 6, 6, 5]),
    ("Хип-хоп",            [6, 5, 2, 3, -1, -1, 2, -1, 2, 3]),
    ("Регги",              [0, 0, -1, -5, 0, 5, 5, 0, 0, 0]),
    ("Наушники",           [4, 8, 4, -2, -2, 1, 3, 6, 8, 9]),
    ("Тихая громкость",    [6, 4, 0, 0, 0, 0, 0, 1, 3, 5]),
)


# жанровое «семейство» (см. music_intel.GENRE_FAMILIES) -> пресет эквалайзера
EQ_BY_FAMILY = {
    "metalcore": "Рок", "metal": "Рок", "punk": "Рок", "emo": "Рок", "rock": "Рок", "indie": "Живой звук",
    "phonk": "Хип-хоп", "cloudrap": "Хип-хоп", "drill": "Хип-хоп", "trap": "Хип-хоп", "hiphop": "Хип-хоп",
    "dnb": "Электронная", "dubstep": "Бас", "hyperpop": "Танцевальная", "synthwave": "Электронная",
    "electronic": "Электронная", "dance": "Танцевальная", "funk": "Поп", "jpop": "Поп", "pop": "Поп",
    "dreampop": "Лаунж", "lofi": "Лаунж", "ambient": "Классика", "rnb": "Вокал", "jazz": "Джаз",
    "classical": "Классика", "soundtrack": "Классика", "folk": "Акустика", "latin": "Регги",
}


def _apply_app_palette(t: dict):
    """Палитра всего приложения из цветов темы: диалоги, всплывающие списки, поля ввода и всё, чему
    QSS не задал фон, на Windows 10 иначе получали системный белый (а текст темы — тоже белый)."""
    from PyQt6.QtGui import QPalette
    app = QApplication.instance()
    if app is None:
        return
    try:
        bg, panel, text = QColor(t["bg"]), QColor(t.get("panel", t["bg"])), QColor(t["text"])
        accent = QColor(t.get("accent", "#ff3b6b"))
        muted = QColor(t.get("muted", t["text"]))
    except Exception:                                    # noqa: BLE001
        return
    if not (bg.isValid() and text.isValid()):
        return
    if not panel.isValid():
        panel = QColor(bg)
    if not accent.isValid():
        accent = QColor("#ff3b6b")
    if not muted.isValid():
        muted = QColor(text)
    for c in (bg, panel, text, accent, muted):
        c.setAlpha(255)
    key = (bg.rgb(), panel.rgb(), text.rgb(), accent.rgb())
    if getattr(_apply_app_palette, "_key", None) == key:
        return
    _apply_app_palette._key = key
    light = 0.299 * accent.red() + 0.587 * accent.green() + 0.114 * accent.blue() > 150
    pal = QPalette()
    R = QPalette.ColorRole
    for role, col in ((R.Window, bg), (R.WindowText, text), (R.Base, panel), (R.AlternateBase, bg),
                      (R.Text, text), (R.Button, panel), (R.ButtonText, text), (R.ToolTipBase, panel),
                      (R.ToolTipText, text), (R.PlaceholderText, muted), (R.BrightText, text),
                      (R.Highlight, accent), (R.HighlightedText, QColor("#000000") if light else QColor("#ffffff")),
                      (R.Link, accent)):
        pal.setColor(role, col)
    for role in (R.WindowText, R.Text, R.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, muted)
    app.setPalette(pal)


class MainWindow(QMainWindow):
    @property
    def playlists(self):
        return self._playlists

    @playlists.setter
    def playlists(self, value):
        """Любое присваивание (переименование пересобирает словарь) — снова PlaylistStore, служебные очереди
        переезжают в новый словарь, а не теряются."""
        old = self.__dict__.get("_playlists")
        store = PlaylistStore(value.items() if isinstance(value, dict) else value)
        for k in list(dict.keys(store)):
            v = dict.__getitem__(store, k)
            desc = str(v.get("desc", "")) if isinstance(v, dict) else ""
            generated = desc.startswith("auto:") or (
                desc == "auto" and k in {"Онлайн", "Моя волна", "Настроение дня", "Популярные треки", "Альбом"}
            ) or desc == "Найдено в интернете"
            if k != "Мне нравится" and not str(k).startswith(HIDDEN_PL) and generated:
                target = {"Моя волна": "wave", "Настроение дня": "mood", "Альбом": "album"}.get(k, "legacy:" + k)
                dict.__setitem__(store, HIDDEN_PL + target, v)
                dict.__delitem__(store, k)
        if isinstance(old, PlaylistStore):
            for k, v in old.hidden():
                dict.__setitem__(store, k, v)
        self.__dict__["_playlists"] = store

    _lyrics_fetched = pyqtSignal(int, str, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ECHOES")
        _ic = _app_icon()
        if _ic is not None:
            self.setWindowIcon(_ic)
        self.resize(1120, 720)
        self.setMinimumSize(860, 600)

        self.engine = AudioEngine()
        self.engine.duration_changed.connect(self._on_engine_duration)
        self.engine.position_changed.connect(self._on_engine_position)
        self.engine.state_changed.connect(self._on_engine_state)
        self.engine.finished.connect(self._on_engine_finished)
        self.engine.crossfade_started.connect(self._on_crossfade_started)
        self.engine.error_changed.connect(self._on_engine_error)
        self._lyrics_fetched.connect(self._lyrics_ready)
        self.library = load_library(LIB_FILE)
        import library_guard                          # коллекция не затирается вторым ECHOES; пропавшее — вернуть
        self._lib_guard = library_guard.Guard(DATA_DIR, LIB_FILE, load_library, save_json)
        self._lib_guard.loaded(self.library)
        self.tierlist_path = TIER_FILE
        stored_playlists = load_json(PL_FILE, {})
        self.playlists = stored_playlists
        self.playlists.setdefault("Мне нравится", {"tracks": [], "desc": "Треки, которые вам понравились", "cover": ""})
        if set(self.playlists) != set(stored_playlists):
            if PL_FILE.exists():
                backup = PL_FILE.with_name("playlists.before-auto-cleanup.json")
                if not backup.exists():
                    backup.write_bytes(PL_FILE.read_bytes())
            save_json(PL_FILE, self.playlists)
        self.profile = load_json(PROFILE_FILE, {"nickname":"user","status":"vibing","avatar":""})
        self.settings = load_json(SETTINGS_FILE, {
            "theme":"Echoes Music", "language":__import__('i18n').system_language(), "crossfade":False, "crossfade_ms":1200, "gapless":False,
            "auto_theme":True, "auto_cover_theme":False, "genius_token":"", "volume":80, "speed":100,
            "fx_dust": True, "fx_breathe": True, "vinyl_warp": False, "vinyl_pause_fx": True,
            "owm_key": "", "owm_city": "Moscow", "play_history": {},
            "download_dir": str(DATA_DIR / "downloads"), "vk_cookies": "",
            "spotify_client_id": "", "spotify_client_secret": "",
        })
        import settings_store                            # история, дневник, дуэль… — из state/ (settings_store)
        settings_store.load_into(self.settings, SETTINGS_FILE)
        try:                                             # своя настройка темы Echoes Music (цвета, шрифт, кнопки)
            import ya_skin
            ya_skin.apply(self.settings.get("ya_skin"))
            import yamusic_theme as _yt                      # своя картинка вместо ноты (Оформление)
            if self.settings.get("placeholder_img"):
                _yt.set_placeholder(self.settings.get("placeholder_img"))
        except Exception as e:                           # noqa: BLE001
            print("[skin]", e)

        self.engine.crossfade_enabled = bool(self.settings.get("crossfade", False))
        self.engine.crossfade_ms = int(self.settings.get("crossfade_ms", 1200))
        self.engine.gapless_enabled = bool(self.settings.get("gapless", False))
        self.engine.warp_enabled = bool(self.settings.get("vinyl_warp", False))
        self.engine.vinyl_pause_fx = bool(self.settings.get("vinyl_pause_fx", True))
        self.engine.set_boost(float(self.settings.get("vol_boost", 1.0) or 1.0))
        self._crossfade_next_index = None

        # ── Автономка: sleep-таймер, Pomodoro, атмосферный шум ───────────
        self.sleep_timer = SleepTimer(self.engine, self)
        self.sleep_timer.tick.connect(self._on_sleep_tick)
        self.sleep_timer.finished.connect(self._on_sleep_finished)

        self.pomodoro = PomodoroTimer(self.engine, self)
        self.pomodoro.phase_changed.connect(self._on_pomo_phase)
        self.pomodoro.tick.connect(self._on_pomo_tick)
        self.pomodoro.stopped.connect(self._on_pomo_stopped)

        self.noise_gen = NoiseGenerator(self.engine.instance, DATA_DIR / "noise_cache")

        # Диалоги загрузчика и редактора текста создаются лениво (при
        # первом открытии) и переиспользуются — не пересоздаём их каждый раз.
        self._downloader_dialog = None
        self._lyrics_editor = None

        self.current_index = -1
        self.queue_context = "library"
        # Spotify-style страница плейлиста: открыта ли сейчас и какая
        self._playlist_detail_open = False
        self._playlist_detail_name = None
        self.shuffle = False
        self._next_shuffle_idx = None
        # Shuffle queue: при включении шафла строим перемешанный список индексов
        # всех треков и проходим по нему. _shuffle_queue — список индексов треков,
        # _shuffle_pos — текущая позиция в этом списке.
        self._shuffle_queue: list[int] = []
        self._shuffle_pos: int = -1
        # Насколько заранее (в мс до конца трека) триггерить start_gapless()
        # в режиме без фейда (crossfade_ms == 0) — этого времени должно
        # хватить VLC на открытие/буферизацию следующего файла. Сам момент
        # переключения при этом планируется отдельно, точным QTimer внутри
        # engine.start_gapless(), а не завязан на грубость опроса позиции.
        self._GAPLESS_LEAD_MS = 1500     # движок сам точно выбирает момент старта (см. start_gapless)
        self.repeat_mode = 0
        self._track_finished_guard = False
        self._lyrics_request_id = 0
        # Темы из конструктора (~/Echoes/themes) — в общий список тем («✦ Название»)
        self.theme_store = theme_kit.ThemeStore(DATA_DIR)
        self._loom_migrate()                    # темы LOOM → темы конструктора (один раз)
        self._custom_keys = register_custom_themes(self.theme_store, theme_kit.to_theme_data)
        self._map_loom_theme()
        self._crt = None                # ThemeRuntime: фон/слои/частицы темы из конструктора
        self._custom_on = False
        self._cur_cover = None
        self._last_qss = None
        self._studio = None
        self._preview_theme = None      # тема, которую сейчас правят в конструкторе (предпросмотр)
        # Старые сохранённые имена тем → актуальные («Default» теперь «Vinyl glass»)
        _LEGACY_THEMES = {"Default": "Vinyl glass", "Milkdrop": "Winamp", "osu!": "Echoes Music",
                          "esu!": "Echoes Music"}           # тема esu! удалена
        _old_theme = self.settings.get("theme")
        if _old_theme in _LEGACY_THEMES and _LEGACY_THEMES[_old_theme] in THEMES:
            self.settings["theme"] = _LEGACY_THEMES[_old_theme]
        if self.settings.get("theme") not in THEMES:      # тема удалена
            self.settings["theme"] = "Echoes Music" if "Echoes Music" in THEMES else next(iter(THEMES))
        self._manual_theme_name = self.settings["theme"]

        # Дебаунс для поиска в библиотеке: запускаем фильтрацию не сразу
        # при каждом нажатии клавиши, а через 200 мс после последнего —
        # это убирает фризы при быстром вводе в больших библиотеках.
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(200)
        self._search_debounce.timeout.connect(self._do_filter_library)

        # Кеш скруглённых иконок обложек: path → QIcon.
        # Строится один раз при загрузке/обновлении обложки,
        # а не заново при каждом вызове _filter_library.
        self._icon_cache: dict[str, "QIcon"] = {}

        if self.settings.get("custom_titlebar", True):
            # окно без системной рамки + своя панель заголовка (рисуется под тему)
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
            self.titlebar = TitleBar(self)
            self.setMenuWidget(self.titlebar)
            self._edge_resizer = EdgeResizer(self)
        self._build_ui()
        inapp.install(self, self.settings.get("inapp_dialogs", True))      # диалоги — слоем внутри окна
        # экспорт треков с эффектами (Slowed + Reverb, Speed Up, Bass Boost) — меню трека и скрипты слоёв
        self.export_effects = self._export_effects
        try:
            import video_safety                      # видеофон: не падать при разворачивании окна
            video_safety.install()
        except Exception as e:                       # noqa: BLE001
            print("[video_safety]", e)
        try:
            import ui_rounding                       # скругления режима клипа (кнопки, панели, рамка)
            ui_rounding.install()
        except Exception as e:                       # noqa: BLE001
            print("[ui_rounding]", e)
        try:
            import clip_sync                         # режим клипа: плавная синхронизация с песней
            clip_sync.install()
        except Exception as e:                       # noqa: BLE001
            print("[clip_sync]", e)
        try:
            import clip_mixer                        # режим клипа: микшер «музыка / звук клипа»
            clip_mixer.install()
        except Exception as e:                       # noqa: BLE001
            print("[clip_mixer]", e)
        if self.settings.get("custom_titlebar", True):
            try:
                import window_corners                # скруглённые углы безрамочного окна (Windows 11)
                window_corners.install(self)
            except Exception as e:                   # noqa: BLE001
                print("[corners]", e)
            try:
                import window_snap                   # прижал к верху экрана — на весь экран (Aero Snap)
                window_snap.install(self)
            except Exception as e:                   # noqa: BLE001
                print("[snap]", e)
        self._apply_theme(self._manual_theme_name)
        self._bind_shortcuts()
        try:
            import player_prefs                      # свои клавиши и размер окна (Ctrl+,)
            player_prefs.install(self)
            import motion, listening_tools
            motion.install(self)
            listening_tools.install(self)
        except Exception as e:                       # noqa: BLE001
            print("[prefs]", e)
        try:
            import playlist_share                    # плейлисты файлами, темы/плейлисты перетаскиванием и из «Импорт»
            playlist_share.install(self)
        except Exception as e:                       # noqa: BLE001
            print("[share]", e)
        try:
            import wheel_guard                       # колесо мыши только листает страницы, значения не меняет
            wheel_guard.install()
        except Exception as e:                       # noqa: BLE001
            print("[wheel]", e)
        try:
            import paint_cache                       # кнопки со стилями рисуются один раз — прокрутка без потери кадров
            paint_cache.install()
        except Exception as e:                       # noqa: BLE001
            print("[paint_cache]", e)
        try:
            import ui_anim                           # анимации: сворачивание окна, смена вкладок, меню
            ui_anim.install(self)
        except Exception as e:                       # noqa: BLE001
            print("[ui_anim]", e)
        try:
            import mem_trim                          # освобождённая память — обратно системе
            mem_trim.install(self)
            import performance
            performance.install(self)
        except Exception as e:                       # noqa: BLE001
            print("[mem]", e)
        self._really_quit = False
        self._tray = None
        try:
            import tray                              # значок в трее: крестик прячет плеер туда
            self._tray = tray.install(self)
        except Exception as e:                       # noqa: BLE001
            print("[tray]", e)
        QApplication.instance().applicationStateChanged.connect(self._on_app_state)
        self._load_profile()
        self._refresh_missing_covers()
        self._refresh_library_view()
        self._refresh_playlists()

        self.vol.setValue(int(self.settings.get("volume", 80)))
        self.speed.setValue(int(self.settings.get("speed", 100)))

        self.stats = ListenStats(DATA_DIR / "stats.json")
        self.loudness = LoudnessStore(DATA_DIR / "loudness.json", on_ready=self._loud_ready)
        self.engine.gain_provider = self._loud_gain
        QTimer.singleShot(12000, self._loud_scan)    # измерить громкость библиотеки в фоне
        QTimer.singleShot(25000, self._warm_studio)  # студией пользуются — её модули подгрузить заранее
        self.user_queue = []                         # «дальше по очереди» — играет раньше основного порядка
        self._queued_now = False                     # сейчас звучит трек из пользовательской очереди
        self._saved_ctx = None                       # откуда продолжить, когда очередь закончится
        self._qguard = False
        for w in (self.avatar_lbl, self.nick_lbl, self.status_lbl):
            w.setCursor(Qt.CursorShape.PointingHandCursor)
            w.setToolTip("Открыть профиль и статистику")
            w.mousePressEvent = lambda e: self._open_profile()
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._update_progress)
        self.ui_timer.start(100)

        self.media_filter = WindowsMediaKeyFilter(self)
        QApplication.instance().installNativeEventFilter(self.media_filter)
        QTimer.singleShot(0, self.media_filter.register)

        # ── Discord Rich Presence ─────────────────────────────────────
        try:
            from discord_rpc import DiscordPresence, CLIENT_ID as _DISCORD_ID
            saved_client_id = self.settings.get("discord_client_id", "")
            self.discord_rpc = DiscordPresence(
                client_id=saved_client_id or _DISCORD_ID,
                enabled=self.settings.get("discord_rpc", True),
                online_covers=self.settings.get("discord_covers", True),
                show_paused=self.settings.get("discord_paused", True),
            )
            self.discord_rpc.set_features(**{k: self.settings.get("discord_" + k, True)
                                             for k in ("lyrics", "artist", "queue", "link", "stats")})
            self.discord_rpc.start()
            self._discord_lyr = ("", 0.0)
            self._discord_lyr_timer = QTimer(self)
            self._discord_lyr_timer.timeout.connect(self._discord_lyric_tick)
            # строку текста в статусе убрали: Discord пропускает обновление раз в ~15 с, текст сильно отставал

            # перемотка откуда угодно (клавиши, медиавиджет Windows) — поправить полосу прогресса в Discord
            self._discord_sent = None
            self._discord_timer = QTimer(self)
            self._discord_timer.timeout.connect(self._discord_drift)
            self._discord_timer.start(4000)
            self._discord_act_key = None
        except Exception as e:
            print("[discord_rpc] init error:", e)
            self.discord_rpc = None
        QTimer.singleShot(0, self._init_fps)            # частота кадров — когда окно уже на экране
        # медиасессия Windows: трек в плашке громкости, на экране блокировки, медиаклавиши
        self._media_session = None
        if self.settings.get("media_session", True):
            QTimer.singleShot(1500, self._start_media_session)

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)

        # Фоновая lo-fi атмосфера — самый нижний слой, создаётся первым,
        # чтобы обычные виджеты естественным образом легли поверх него.
        self._ambience = BackgroundAmbience(root)
        self._ambience.setGeometry(root.rect())
        self._ambience.lower()
        self._ambience.set_enabled(self.settings.get("fx_breathe", True))

        outer = QHBoxLayout(root)
        self._outer = outer
        outer.setContentsMargins(12,12,12,12)
        outer.setSpacing(10)

        left = QFrame(); left.setObjectName("Panel")
        left.setMinimumWidth(220); left.setMaximumWidth(300)
        lv = QVBoxLayout(left); lv.setContentsMargins(18,20,18,18); lv.setSpacing(10)

        prof = QHBoxLayout()
        self.avatar_lbl = QLabel(""); self.avatar_lbl.setFixedSize(46,46)
        self.avatar_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_lbl.setStyleSheet("border-radius:23px;background:rgba(255,255,255,0.07);font-size:18px;")
        self.nick_lbl = QLabel(self.profile["nickname"]); self.nick_lbl.setObjectName("Big")
        self.status_lbl = QLabel(self.profile["status"]); self.status_lbl.setObjectName("Sub")
        col=QVBoxLayout(); col.addWidget(self.nick_lbl); col.addWidget(self.status_lbl)
        prof.addWidget(self.avatar_lbl); prof.addLayout(col); prof.addStretch()
        lv.addLayout(prof)

        self.btn_edit = QPushButton("Профиль"); self.btn_edit.clicked.connect(self._open_profile)
        lv.addWidget(self.btn_edit)

        sec=QLabel("БИБЛИОТЕКА"); sec.setObjectName("Section"); lv.addWidget(sec)
        self.lib_search=QLineEdit()
        self.lib_search.setPlaceholderText("Поиск трека или исполнителя...")
        # textChanged → дебаунс-таймер (200 мс) → _do_filter_library
        # Без дебаунса каждый символ перестраивает весь список + грузит иконки с диска.
        self.lib_search.textChanged.connect(lambda _: self._search_debounce.start())
        lv.addWidget(self.lib_search)

        self.lib_sort = QComboBox()
        self.lib_sort.addItem("По добавлению", "added")
        self.lib_sort.addItem("По названию (А-Я)", "title")
        self.lib_sort.addItem("По исполнителю (А-Я)", "artist")
        self.lib_sort.addItem("По альбому", "album")
        self.lib_sort.addItem("По длительности", "duration")
        saved_sort = self.settings.get("lib_sort", "added")
        found = self.lib_sort.findData(saved_sort)
        if found >= 0:
            self.lib_sort.setCurrentIndex(found)
        self.lib_sort.currentIndexChanged.connect(self._on_sort_changed)
        lv.addWidget(self.lib_sort)

        self.lib_list=QListWidget(); self.lib_list.setIconSize(QSize(40,40)); self.lib_list.setUniformItemSizes(False)
        self.lib_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.lib_list.itemClicked.connect(self._play_from_library)
        # Удаление выделенных треков из библиотеки — Delete или ПКМ-меню.
        self.lib_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.lib_list.customContextMenuRequested.connect(self._lib_context_menu)
        self._lib_delete_sc = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.lib_list)
        self._lib_delete_sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._lib_delete_sc.activated.connect(self._delete_selected_library_tracks)
        lv.addWidget(self.lib_list, 4)
        # треки можно перетащить мышкой на плейлист
        self.lib_list.setDragEnabled(True)
        self.lib_list.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        lib_hint = QLabel("Клик — играть · Ctrl/Shift + клик — выделить несколько · "
                          "Delete или правая кнопка — удалить, в плейлист, теги")
        lib_hint.setObjectName("Sub"); lib_hint.setWordWrap(True)
        lib_hint.setStyleSheet("font-size:11px;")
        lv.addWidget(lib_hint)
        self._lib_hint = lib_hint

        r=QHBoxLayout()
        b=QPushButton("＋ Файлы"); b.setToolTip("Добавить музыкальные файлы с компьютера"); b.clicked.connect(self._add_files); r.addWidget(b)
        self._btn_files = b
        b=QPushButton("＋ Папка"); b.setToolTip("Добавить все треки из папки"); b.clicked.connect(self._add_folder); r.addWidget(b)
        self._btn_folder = b
        lv.addLayout(r)
        b=QPushButton("Скачать"); b.setObjectName("AccentBtn"); b.setToolTip("Скачать трек/альбом/плейлист по ссылке")
        b.clicked.connect(self._open_downloader)
        lv.addWidget(b)
        self._btn_download = b

        # ── Плейлисты (без вкладки «Редактор» — редактирование живёт
        #    в странице плейлиста через drag&drop и ПКМ-меню) ──
        pl_section = QWidget(); pl_section.setStyleSheet(".QWidget{background:transparent;}")
        pt = QVBoxLayout(pl_section); pt.setContentsMargins(0, 4, 0, 0); pt.setSpacing(6)

        hdr_row = QHBoxLayout(); hdr_row.setContentsMargins(0, 0, 0, 0)
        pl_hdr = QLabel("ПЛЕЙЛИСТЫ"); pl_hdr.setObjectName("Section")
        hdr_row.addWidget(pl_hdr); hdr_row.addStretch(1)
        b_help = QPushButton("?"); b_help.setObjectName("GhostBtn"); b_help.setFixedWidth(30)
        b_help.setToolTip("Как пользоваться плейлистами и коллекцией")
        b_help.clicked.connect(lambda: __import__("track_tools").show_help(self))
        hdr_row.addWidget(b_help)
        pt.addLayout(hdr_row)

        self.pl_list = QListWidget(); self.pl_list.setMinimumHeight(90)
        self.pl_list.setIconSize(QSize(36, 36))
        # Клик — открыть страницу плейлиста (как в Spotify), дабл-клик — сразу играть.
        self.pl_list.itemClicked.connect(self._open_playlist_detail)
        self.pl_list.itemDoubleClicked.connect(self._play_playlist)
        self.pl_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.pl_list.customContextMenuRequested.connect(self._playlist_context_menu)
        pt.addWidget(self.pl_list, 1)
        # приём треков, перетащенных из библиотеки
        self.pl_list.setAcceptDrops(True)
        self.pl_list.viewport().setAcceptDrops(True)
        self.pl_list.viewport().installEventFilter(self)
        pl_hint = QLabel("Клик — открыть · двойной клик — играть · перетащите сюда треки из библиотеки")
        pl_hint.setObjectName("Sub"); pl_hint.setWordWrap(True)
        pl_hint.setStyleSheet("font-size:11px;")
        pt.addWidget(pl_hint)
        self._pl_hint = pl_hint

        b = QPushButton("＋ Новый плейлист"); b.setObjectName("AccentBtn")
        b.setToolTip("Пустой плейлист, из файла друга или из Spotify"); b.clicked.connect(self._new_playlist_menu)
        pt.addWidget(b)
        self._btn_new_pl = b
        r = QHBoxLayout()
        b = QPushButton("＋ Играющий трек")
        b.setToolTip("Добавить трек, который играет сейчас, в плейлист"); b.clicked.connect(self._add_current_to_playlist); r.addWidget(b)
        self._btn_add_cur = b
        b = QPushButton("＋ Выделенные")
        b.setToolTip("Добавить выделенные в библиотеке треки (Ctrl/Shift + клик) в плейлист")
        b.clicked.connect(self._add_selected_to_playlist); r.addWidget(b)
        self._btn_add_sel = b
        pt.addLayout(r)

        # Фиктивные атрибуты редактора — чтобы не ломались методы _load_playlist_editor
        # и _save_playlist_editor_order, которые проверяют hasattr и могут вызываться
        # из других мест (например, при добавлении треков).
        self.pl_editor_combo = QComboBox(); self.pl_editor_combo.hide()
        self.pl_edit_list = QListWidget(); self.pl_edit_list.hide()
        pt.addWidget(self.pl_editor_combo)
        pt.addWidget(self.pl_edit_list)

        lv.addWidget(pl_section, 3)
        self._pl_section = pl_section

        # FluidPanel — тот же CenterStage, но с жидкой текстурой на фоне.
        # Пока активна не тема Fluid, она ничего не рисует.
        center = FluidPanel(); self._stage = center
        center.palette_changed.connect(self._on_fluid_palette)
        cv=QVBoxLayout(center); cv.setContentsMargins(24,20,24,20); cv.setSpacing(6)
        self._cv = cv

        self._lyrics_mode = False

        # Контейнер обычного режима (vinyl + meta + viz)
        self._normal_widget = QWidget(); self._normal_widget.setStyleSheet(".QWidget{background:transparent;}")
        nv = QVBoxLayout(self._normal_widget); nv.setContentsMargins(0,0,0,0); nv.setSpacing(6)
        self._nv = nv

        self.vinyl=VinylWidget(); self.vinyl.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.vinyl.set_engine(self.engine)  # для реактивной подсветки диска/иглы по RMS
        nv.addWidget(self.vinyl, 7, Qt.AlignmentFlag.AlignCenter)

        self.title_lbl=QLabel("— не играет —"); self.title_lbl.setObjectName("Title")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artist_lbl=QLabel(""); self.artist_lbl.setObjectName("Artist")
        self.artist_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nv.addWidget(self.title_lbl); nv.addWidget(self.artist_lbl)

        self.viz=Visualizer(); self.viz.setMinimumHeight(100); self.viz.set_engine(self.engine)
        nv.addWidget(self.viz, 2)

        # Текст трека и кнопка "Текст" должны всегда оставаться НАД
        # визуализатором по z-порядку (особенно в режиме Milkdrop) —
        # поднимаем их на верхний уровень стека виджетов.
        self.title_lbl.raise_()
        self.artist_lbl.raise_()

        # ── Кнопка текста — в самом низу зоны vinyl ──
        lyrics_btn_row = QHBoxLayout()
        lyrics_btn_row.setContentsMargins(0, 2, 0, 0)
        lyrics_btn_row.setSpacing(8)
        self.btn_lyrics_mode = QPushButton("Текст")
        self.btn_lyrics_mode.setObjectName("GhostBtn")
        self.btn_lyrics_mode.setCheckable(True)
        self.btn_lyrics_mode.setToolTip("Показать / скрыть текст песни")
        self.btn_lyrics_mode.setFixedWidth(88)
        self.btn_lyrics_mode.clicked.connect(self._toggle_lyrics_mode)
        self.btn_queue_view = QPushButton("Очередь")
        self.btn_queue_view.setObjectName("GhostBtn")
        self.btn_queue_view.setToolTip("Показать очередь воспроизведения")
        self.btn_queue_view.setFixedWidth(96)
        self.btn_queue_view.clicked.connect(self._show_queue_popup)
        lyrics_btn_row.addStretch()
        lyrics_btn_row.addWidget(self.btn_lyrics_mode)
        lyrics_btn_row.addWidget(self.btn_queue_view)
        lyrics_btn_row.addStretch()
        nv.addLayout(lyrics_btn_row)
        self._lyrics_btn_row = lyrics_btn_row
        # В теме Fluid эти две кнопки становятся крупными пунктами «главного меню»
        self.btn_lyrics_mode.setProperty("fluidMenu", True)
        self.btn_queue_view.setProperty("fluidMenu", True)
        self.btn_lyrics_mode.raise_()
        self.btn_queue_view.raise_()

        cv.addWidget(self._normal_widget, 7)

        # LyricsView создаём без parent — потом прикрепим к root как overlay
        self.lyrics_view = LyricsView()

        # ── Транспортная панель (seek + times + controls + громкость/скорость) ──
        # Отдельный виджет (а не голые layout'ы прямо в cv), чтобы LyricsView
        # мог узнать её точные границы и НИКОГДА её не перекрывать — иначе
        # кнопки под ней (в т.ч. "Текст") становятся некликабельными в
        # режиме показа текста.
        self.transport_bar = QFrame()
        self.transport_bar.setObjectName("DockCard")   # бежевая плашка в теме Fluid
        tv = QVBoxLayout(self.transport_bar)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(6)

        # ── Seek + times — отдельный виджет, прячется в lyrics-режиме ──
        self._seek_row = QWidget(); self._seek_row.setStyleSheet(".QWidget{background:transparent;}")
        sr = QVBoxLayout(self._seek_row); sr.setContentsMargins(0,0,0,0); sr.setSpacing(0)
        self.seek=FancySlider(Qt.Orientation.Horizontal); self.seek.setRange(0,1000)
        self.seek.time_provider = lambda f: self._fmt(f * float(self.engine.duration or 0))
        self.seek.sliderReleased.connect(self._on_seek); sr.addWidget(self.seek)
        times=QHBoxLayout(); times.setContentsMargins(2,0,2,0)
        self.t_cur=QLabel("0:00"); self.t_cur.setObjectName("Time")
        self.t_tot=QLabel("0:00"); self.t_tot.setObjectName("Time")
        times.addWidget(self.t_cur); times.addStretch(); times.addWidget(self.t_tot)
        sr.addLayout(times)
        tv.addWidget(self._seek_row)

        # ── Кнопки управления — отдельный виджет, в lyrics-режиме raise_() над overlay ──
        self._controls_widget = QWidget(); self._controls_widget.setStyleSheet(".QWidget{background:transparent;}")
        controls=QHBoxLayout(self._controls_widget); controls.setSpacing(6); controls.setContentsMargins(0,10,0,10)
        self.btn_shuffle=self._icon("Shuffle","Перемешать"); self.btn_shuffle.setCheckable(True); self.btn_shuffle.clicked.connect(self._toggle_shuffle)
        self.btn_prev=self._icon("Prev","Предыдущий"); self.btn_prev.clicked.connect(self.prev_track)
        self.btn_play=PlayPauseButton(); self.btn_play.setObjectName("PlayBtn"); self.btn_play.setToolTip("Play / Pause"); self.btn_play.clicked.connect(self.toggle_play)
        self.btn_next=self._icon("Next","Следующий"); self.btn_next.clicked.connect(self.next_track)
        self.btn_repeat=self._icon("Repeat","Повтор"); self.btn_repeat.setCheckable(True); self.btn_repeat.clicked.connect(self._cycle_repeat)
        # «Шаффл по исполнителю»: клик — все треки исполнителя текущей песни вперемешку,
        # правый клик — выбрать исполнителя (как «Волна по исполнителю» в Echoes Music)
        self.btn_artist_shuffle = self._icon("Артист", "Шаффл по исполнителю: все его треки вперемешку "
                                                      "(правый клик — выбрать исполнителя, Ctrl+Shift+S)")
        self.btn_artist_shuffle.clicked.connect(lambda: self.artist_shuffle())
        self.btn_artist_shuffle.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.btn_artist_shuffle.customContextMenuRequested.connect(
            lambda p_: self.artist_shuffle_menu(self.btn_artist_shuffle.mapToGlobal(p_)))
        controls.addWidget(self.btn_shuffle); controls.addWidget(self.btn_artist_shuffle); controls.addStretch()
        controls.addWidget(self.btn_prev); controls.addSpacing(8)
        controls.addWidget(self.btn_play)
        controls.addSpacing(8); controls.addWidget(self.btn_next)
        controls.addStretch()
        controls.addWidget(self.btn_repeat)
        self.btn_cover_mode = self._icon("Обложка", "Режим обложки: только обложка и управление")
        self.btn_cover_mode.clicked.connect(self._toggle_cover_mode)
        self.btn_cover_mode.setProperty("fluidBig", True)
        controls.addWidget(self.btn_cover_mode)
        # «Клип»: официальный клип песни поверх любой темы (Ctrl+Shift+K)
        self.btn_clip_mode = self._icon("Клип", "Официальный клип песни: смотреть, скачать, эффекты (Ctrl+Shift+K)")
        self.btn_clip_mode.clicked.connect(self._toggle_clip_mode)
        self.btn_clip_mode.setProperty("fluidBig", True)
        controls.addWidget(self.btn_clip_mode)
        # «Музыка»: интерфейс Echoes Music (онлайн-поиск, исполнители, альбомы,
        # волна) в отдельном окне — доступен из любой темы
        self.btn_hub = self._icon("Музыка", "Музыка: поиск и скачивание, исполнители, альбомы, "
                                            "«Моя волна» — как в Яндекс Музыке (Ctrl+M)")
        self.btn_hub.clicked.connect(self._open_hub)
        self.btn_hub.setProperty("fluidBig", True)
        controls.addWidget(self.btn_hub)
        for _b in (self.btn_shuffle, self.btn_artist_shuffle, self.btn_prev, self.btn_next, self.btn_repeat):
            _b.setProperty("fluidBig", True)     # крупный оранжевый текст в теме Fluid
        tv.addWidget(self._controls_widget)

        # ── Vol/Speed — отдельный виджет, прячется в lyrics-режиме ──
        self._vol_row = QWidget(); self._vol_row.setStyleSheet(".QWidget{background:transparent;}")
        bottom=QHBoxLayout(self._vol_row); bottom.setSpacing(10); bottom.setContentsMargins(4,4,4,4)
        vol_lbl=QLabel("Vol"); vol_lbl.setObjectName("Sub"); bottom.addWidget(vol_lbl)
        self.vol=QSlider(Qt.Orientation.Horizontal); self.vol.setRange(0,100); self.vol.valueChanged.connect(self._volume_changed); bottom.addWidget(self.vol,3)
        spd_lbl=QLabel("Speed"); spd_lbl.setObjectName("Sub"); bottom.addWidget(spd_lbl)
        self.speed=QSlider(Qt.Orientation.Horizontal); self.speed.setRange(25,400); self.speed.valueChanged.connect(self._on_speed_changed); bottom.addWidget(self.speed,2)
        self.speed_lbl=QLabel("1.00×"); self.speed_lbl.setObjectName("Sub"); bottom.addWidget(self.speed_lbl)
        btn_spd_reset=QPushButton("1×"); btn_spd_reset.setObjectName("GhostBtn")
        btn_spd_reset.setFixedWidth(32); btn_spd_reset.setToolTip("Сбросить скорость")
        btn_spd_reset.clicked.connect(lambda: self.speed.setValue(100))
        bottom.addWidget(btn_spd_reset)
        tv.addWidget(self._vol_row)

        cv.addWidget(self.transport_bar)

        # ── Spotify-style страница плейлиста ──
        # Занимает то же место, что и _normal_widget + transport_bar,
        # но показывается только когда открыт конкретный плейлист —
        # пластинка, визуализатор и транспорт в этот момент скрыты.
        self.playlist_detail = PlaylistDetailView()
        self.playlist_detail.hide()
        cv.addWidget(self.playlist_detail, 7)

        self.playlist_detail.back_requested.connect(self._close_playlist_detail)
        self.playlist_detail.play_requested.connect(self._pd_play)
        self.playlist_detail.shuffle_play_requested.connect(self._pd_shuffle_play)
        self.playlist_detail.track_activated.connect(self._pd_track_activated)
        self.playlist_detail.cover_change_requested.connect(self._pd_set_cover)
        self.playlist_detail.rename_requested.connect(self._pd_rename)
        self.playlist_detail.description_edit_requested.connect(self._pd_edit_description)
        self.playlist_detail.delete_requested.connect(self._pd_delete_playlist)
        self.playlist_detail.tracks_reordered.connect(self._pd_save_order)
        self.playlist_detail.track_remove_requested.connect(self._pd_remove_tracks)
        self.playlist_detail.add_tracks_requested.connect(lambda n: self.pick_tracks_for_playlist(n))
        self.playlist_detail.move_requested.connect(self._pd_move)
        self.playlist_detail.reveal_requested.connect(
            lambda name, row: self.reveal_in_explorer(
                (self.playlists.get(name, {}).get("tracks", []) or [None] * (row + 1))[row]
                if 0 <= row < len(self.playlists.get(name, {}).get("tracks", [])) else None))
        self.playlist_detail.tags_requested.connect(
            lambda n, r: self.edit_track_tags(self._ctx_tracks(n)[r] if 0 <= r < len(self._ctx_tracks(n)) else None))
        self.playlist_detail.delete_everywhere_requested.connect(
            lambda n, rows: self.remove_tracks_everywhere(
                [self._ctx_tracks(n)[r] for r in rows if 0 <= r < len(self._ctx_tracks(n))]))

        right=QFrame(); right.setObjectName("Panel")
        right.setMinimumWidth(220); right.setMaximumWidth(310)
        from PyQt6.QtWidgets import QStackedWidget
        right_outer = QVBoxLayout(right); right_outer.setContentsMargins(10, 14, 10, 10); right_outer.setSpacing(6)

        # ── Навигационная строка (‹ Заголовок страницы ›) ──
        _nav_widget = QWidget(); _nav_widget.setStyleSheet(".QWidget{background:transparent;}")
        _nav_row = QHBoxLayout(_nav_widget); _nav_row.setContentsMargins(0, 0, 0, 0); _nav_row.setSpacing(6)

        self._rp_prev_btn = QPushButton("‹")
        self._rp_prev_btn.setFixedSize(32, 28)
        self._rp_prev_btn.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.12);"
            "border-radius:10px;color:#f2f4fa;font-size:16px;font-weight:600;padding:0;}"
            "QPushButton:hover{background:rgba(255,255,255,0.13);}"
            "QPushButton:pressed{background:rgba(255,255,255,0.22);}"
        )

        self._rp_next_btn = QPushButton("›")
        self._rp_next_btn.setFixedSize(32, 28)
        self._rp_next_btn.setStyleSheet(self._rp_prev_btn.styleSheet())

        self._rp_page_lbl = QLabel("")
        self._rp_page_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._rp_page_lbl.setStyleSheet(
            "color:rgba(255,255,255,0.55);font-size:10px;font-weight:600;"
            "letter-spacing:1.4px;text-transform:uppercase;background:transparent;"
        )

        _nav_row.addWidget(self._rp_prev_btn)
        _nav_row.addWidget(self._rp_page_lbl, 1)
        _nav_row.addWidget(self._rp_next_btn)
        right_outer.addWidget(_nav_widget)
        self._rp_nav = _nav_widget

        # ── Стек страниц ──
        self._rp_stack = QStackedWidget(); self._rp_stack.setStyleSheet(".QStackedWidget, .QWidget{background:transparent;}")
        right_outer.addWidget(self._rp_stack, 1)

        def _make_page():
            """Создаёт страницу со scroll area и возвращает (page_widget, rv_layout)."""
            scroll = QScrollArea(); scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setStyleSheet(
                "QScrollArea{border:none;background:transparent;}"
                "QScrollBar:horizontal{background:transparent;height:6px;margin:0;}"
                "QScrollBar::handle:horizontal{background:rgba(128,128,128,0.35);border-radius:3px;min-width:24px;}"
                "QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{width:0;}"
                "QScrollBar:vertical{background:transparent;width:4px;margin:0;}"
                "QScrollBar::handle:vertical{background:rgba(128,128,128,0.35);border-radius:2px;min-height:24px;}"
                "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
            )
            content = QWidget(); content.setStyleSheet(".QWidget{background:transparent;}")
            layout = QVBoxLayout(content); layout.setContentsMargins(18, 12, 18, 18); layout.setSpacing(10)
            scroll.setWidget(content)
            return scroll, layout

        # Страница 0: Оформление + Текст песни
        _p0, rv = _make_page()
        self._rp_stack.addWidget(_p0)

        # Страница 1: Воспроизведение + Эквалайзер
        _p1, rv1 = _make_page()
        self._rp_stack.addWidget(_p1)

        # Страница 2: Lo-Fi + Шум + Автономка
        _p2, rv2 = _make_page()
        self._rp_stack.addWidget(_p2)

        _rp_pages = ["Оформление", "Воспроизведение", "Автономка"]

        def _rp_go(delta):
            idx = self._rp_stack.currentIndex()
            new = (idx + delta) % len(_rp_pages)
            sw = getattr(self, "animate_switch_index", None)   # плавно, со сдвигом в сторону перехода
            sw(self._rp_stack, new, delta) if sw else self._rp_stack.setCurrentIndex(new)
            self._rp_page_lbl.setText(_rp_pages[new])
            self._rp_prev_btn.setEnabled(True)
            self._rp_next_btn.setEnabled(True)

        self._rp_prev_btn.clicked.connect(lambda: _rp_go(-1))
        self._rp_next_btn.clicked.connect(lambda: _rp_go(1))
        self._rp_page_lbl.setText(_rp_pages[0])
        # ══════════════════════════════════════════════════════════════
        #  СТРАНИЦА 0: Оформление + Текст песни
        # ══════════════════════════════════════════════════════════════
        sec=QLabel("Оформление"); sec.setObjectName("Section"); rv.addWidget(sec)
        self.theme_cb=QComboBox(); self._fill_theme_combo(); self.theme_cb.currentTextChanged.connect(self._request_theme); rv.addWidget(self.theme_cb)
        _studio_btn = QPushButton("Конструктор тем")
        _studio_btn.setObjectName("AccentBtn")
        _studio_btn.setToolTip("Своя тема: цвета, шрифты, фон (картинка, GIF, видео, живые обои), "
                               "стикеры и надписи где угодно, частицы, эффекты (Ctrl+Shift+T)")
        _studio_btn.clicked.connect(lambda: self._open_theme_studio())
        rv.addWidget(_studio_btn)
        self._studio_btn = _studio_btn
        self.auto_cover_theme_cb=QCheckBox("Цвета из обложки"); self.auto_cover_theme_cb.setToolTip("Подстраивать цвета интерфейса под обложку трека")
        self.auto_cover_theme_cb.setChecked(self.settings.get("auto_cover_theme",False)); self.auto_cover_theme_cb.stateChanged.connect(self._auto_cover_theme); rv.addWidget(self.auto_cover_theme_cb)
        sec=QLabel("Язык / Language"); sec.setObjectName("Section"); rv.addWidget(sec)
        self.lang_cb = QComboBox()
        self.lang_cb.setToolTip("Язык всего интерфейса во всех темах · Interface language for all themes")
        for _code, _name in (("ru", "Русский"), ("en", "English")):
            self.lang_cb.addItem(_name, _code)
        self.lang_cb.setCurrentIndex(max(0, self.lang_cb.findData(self.settings.get("language", "ru"))))
        self.lang_cb.currentIndexChanged.connect(self._on_language_changed)
        rv.addWidget(self.lang_cb)

        # ── Текст песни: превью + ручной редактор/LRC-таймер ─────────
        sec=QLabel("Текст песни"); sec.setObjectName("Section"); rv.addWidget(sec)
        self.lyrics_box=QTextEdit(); self.lyrics_box.setReadOnly(True)
        self.lyrics_box.setMaximumHeight(110)
        rv.addWidget(self.lyrics_box)
        b=QPushButton("Записать/изменить"); b.clicked.connect(self._open_lyrics_editor)
        self._btn_lyrics_edit = b
        rv.addWidget(b)
        b=QPushButton("Найти текст вручную")
        b.setToolTip("Ввести свой запрос (исполнитель - название) и найти текст в интернете · Ctrl+Shift+L")
        b.clicked.connect(self._manual_lyrics_search)
        self._btn_lyrics_find = b
        rv.addWidget(b)
        rv.addStretch()

        # ══════════════════════════════════════════════════════════════
        #  СТРАНИЦА 1: Воспроизведение + Эквалайзер
        # ══════════════════════════════════════════════════════════════
        sec=QLabel("Воспроизведение"); sec.setObjectName("Section"); rv1.addWidget(sec)

        # ── Пресеты: Slowed+Reverb / Speed Up ────────────────────────
        # Slowed+Reverb: настоящий эффект — ffmpeg декодирует трек,
        # scipy добавляет hall-реверб, VLC воспроизводит с rate=0.80×
        # (темп И питч вместе опускаются — именно так звучат slowed covers).
        # Speed Up: просто rate=1.25× (темп + питч вместе вверх, как на TikTok).
        _preset_lbl = QLabel("Пресеты")
        _preset_lbl.setObjectName("Sub")
        rv1.addWidget(_preset_lbl)

        preset_row = QHBoxLayout(); preset_row.setSpacing(6)

        self._btn_slowed = QPushButton("Slowed+Reverb")
        self._btn_slowed.setObjectName("GhostBtn")
        self._btn_slowed.setCheckable(True)
        self._btn_slowed.setToolTip(
            "Hall-реверб + 0.80× скорость\n"
            "Голос и темп замедляются вместе — как настоящий slowed cover.\n"
            "Обработка ~1–2 сек при первом включении."
        )
        self._btn_slowed.setMinimumHeight(34)

        self._btn_speedup = QPushButton("Speed Up")
        self._btn_speedup.setObjectName("GhostBtn")
        self._btn_speedup.setCheckable(True)
        self._btn_speedup.setToolTip(
            "1.25× скорость\n"
            "Голос и темп ускоряются вместе — как nightcore/speed up на YouTube."
        )
        self._btn_speedup.setMinimumHeight(34)
        self._btn_8d = QPushButton("8D")
        self._btn_8d.setObjectName("GhostBtn")
        self._btn_8d.setCheckable(True)
        self._btn_8d.setToolTip("Умный 8D: ИИ находит темп и сильные доли трека, и звук облетает голову в такт "
                                "(басы — в центре). Лучше всего в наушниках")
        self._btn_8d.setMinimumHeight(34)

        # Метка статуса обработки (показывается во время рендера реверба)
        self._preset_status_lbl = QLabel("")
        self._preset_status_lbl.setObjectName("Sub")
        self._preset_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preset_status_lbl.hide()

        # ── внутреннее состояние пресета ──
        import threading as _threading_mod
        self._preset_thread = None   # фоновый тред обработки реверба
        self._preset_pending_path = None  # path трека для которого делаем реверб

        def _set_speed_ui(rate: float):
            """Синхронизирует слайдер Speed и лейбл без побочных сбросов пресета."""
            self.speed.blockSignals(True)
            self.speed.setValue(int(round(rate * 100)))
            self.speed.blockSignals(False)
            self.speed_lbl.setText(f"{rate:.2f}×")

        # ── Пресеты: файл готовится в фоне честным ресэмплингом (темп и
        #    питч меняются вместе), играет на скорости 1.0 — без артефактов
        #    time-stretch. Позиция в треке сохраняется при включении/выключении.
        self._ui_bridge = _UiBridge(self)
        self._ui_bridge.call.connect(lambda fn: fn())
        QTimer.singleShot(1200, self._lyrics_cache_preload)
        # стриминг: онлайн-треки («stream:…») играют сразу, ссылки на поток готовятся заранее
        import stream_core
        self.streams = stream_core.resolver(lambda fn: self._ui_bridge.call.emit(fn))
        self.engine.url_resolver = self.streams.cached
        self._stream_token = 0
        # фоновое изучение библиотеки (жанры/звук) — через 10 с после старта
        QTimer.singleShot(10000, self._start_music_intel)
        _PRESET_NAMES = {"slowed": "Slowed+Reverb", "speedup": "Speed Up", "8d": "8D"}

        def _current_src():
            t_list = self.library if self.queue_context == "library" \
                else self.playlists.get(self.queue_context, {}).get("tracks", [])
            if 0 <= self.current_index < len(t_list):
                return str(t_list[self.current_index].get("path", ""))
            return ""

        def _preset_on():
            """Играет ли сейчас файл пресета (у 8D темп тот же, поэтому смотрим и на файл)."""
            return self.engine.preset_factor != 1.0 or bool(self.engine._preset_temp_path)

        def _sync_preset_buttons(mode):
            for btn, m in ((self._btn_slowed, "slowed"), (self._btn_speedup, "speedup"), (self._btn_8d, "8d")):
                btn.blockSignals(True)
                btn.setChecked(mode == m)
                btn.setEnabled(True)
                btn.blockSignals(False)

        def _orig_position():
            """Позиция в ОРИГИНАЛЬНОМ треке (файл пресета длиннее/короче)."""
            return self.engine.get_position() * (self.engine.preset_factor or 1.0)

        def _unlink_later(path):
            def _rm():
                try:
                    import os as _os
                    _os.unlink(path)
                except OSError:
                    pass
            QTimer.singleShot(1500, _rm)      # VLC успевает отпустить файл

        def _preset_ready(mode, src, tmp):
            self._preset_status_lbl.hide()
            if self.engine.preset_mode != mode or _current_src() != src:
                _unlink_later(tmp)            # пока считали — всё поменялось
                _sync_preset_buttons(self.engine.preset_mode if _preset_on() else None)
                return
            factor = self.engine.PRESET_FACTORS[mode]
            pos = _orig_position()
            old_tmp = self.engine._preset_temp_path
            self.engine.speed = 1.0
            self.engine.load(tmp, autoplay=True, start_sec=pos / factor)
            self.engine.preset_factor = factor
            self.engine._preset_temp_path = tmp
            if old_tmp and old_tmp != tmp:
                _unlink_later(old_tmp)
            _sync_preset_buttons(mode)
            _set_speed_ui(1.0)
            if mode == "8d" and getattr(self.engine, "last_8d", ""):
                self._toast("8D: " + self.engine.last_8d)

        def _preset_failed(msg):
            self.engine.preset_mode = None if not _preset_on() else self.engine.preset_mode
            self._preset_status_lbl.setText(f"Ошибка: {msg[:60]}")
            self._preset_status_lbl.show()
            _sync_preset_buttons(self.engine.preset_mode if _preset_on() else None)

        def _start_preset(mode):
            src = _current_src()
            if not src:
                _sync_preset_buttons(None)
                return
            if src.startswith("stream:"):                  # онлайн-трек: файла для обработки пока нет
                self._toast("Это работает со скачанными треками — скачайте трек, и всё включится")
                _sync_preset_buttons(None)
                return
            self.engine.preset_mode = mode
            self._btn_slowed.setEnabled(False)
            self._btn_speedup.setEnabled(False)
            self._btn_8d.setEnabled(False)
            self._preset_status_lbl.setText("ИИ слушает трек и строит полёт звука вокруг головы…" if mode == "8d"
                                            else f"Готовлю {_PRESET_NAMES[mode]}…")
            self._preset_status_lbl.show()

            def work():
                try:
                    tmp = self.engine.render_preset(src, mode)
                    self._ui_bridge.call.emit(lambda: _preset_ready(mode, src, tmp))
                except Exception as e:                      # noqa: BLE001
                    msg = str(e)
                    self._ui_bridge.call.emit(lambda: _preset_failed(msg))

            self._preset_thread = _threading_mod.Thread(target=work, daemon=True)
            self._preset_thread.start()

        def _stop_preset():
            src = _current_src()
            if _preset_on() and src:
                pos = _orig_position()
                old_tmp = self.engine._preset_temp_path
                self.engine.deactivate_preset()
                self.engine._preset_temp_path = None
                self.engine.speed = 1.0
                self.engine.load(src, autoplay=True, start_sec=pos)
                if old_tmp:
                    _unlink_later(old_tmp)
            else:
                self.engine.deactivate_preset()
            self._preset_status_lbl.hide()
            _sync_preset_buttons(None)
            _set_speed_ui(1.0)
            self.settings["speed"] = 100
            save_json(SETTINGS_FILE, self.settings)

        def _on_slowed_toggled(checked):
            _start_preset("slowed") if checked else _stop_preset()

        def _on_speedup_toggled(checked):
            _start_preset("speedup") if checked else _stop_preset()

        def _on_8d_toggled(checked):
            self.settings["sound_8d"] = bool(checked)      # 8D остаётся включённым и на следующих треках
            if checked:
                for other in (self._btn_slowed, self._btn_speedup):
                    other.blockSignals(True); other.setChecked(False); other.blockSignals(False)
            _start_preset("8d") if checked else _stop_preset()

        self._btn_slowed.toggled.connect(_on_slowed_toggled)
        self._btn_speedup.toggled.connect(_on_speedup_toggled)
        self._btn_8d.toggled.connect(_on_8d_toggled)

        preset_row.addWidget(self._btn_slowed)
        preset_row.addWidget(self._btn_speedup)
        preset_row.addWidget(self._btn_8d)
        rv1.addLayout(preset_row)
        rv1.addWidget(self._preset_status_lbl)

        _preset_hint = QLabel("Темп + питч меняются вместе")
        _preset_hint.setObjectName("Sub")
        _preset_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rv1.addWidget(_preset_hint)

        self.crossfade_cb=QCheckBox("Кроссфейд")
        self.crossfade_cb.setToolTip(
            "Плавно сводить громкость между текущим и следующим треком.\n"
            "Ползунок на 0 = гэплесс-режим: без фейда вообще, только точное "
            "переключение — для альбомов с уже вшитыми переходами."
        )
        self.crossfade_cb.setChecked(self.settings.get("crossfade", False))
        self.crossfade_cb.stateChanged.connect(self._on_crossfade_toggled)
        rv1.addWidget(self.crossfade_cb)

        cf_row=QHBoxLayout(); cf_row.setSpacing(6)
        cf_lbl=QLabel("Длит."); cf_lbl.setObjectName("Sub")
        self.crossfade_slider=QSlider(Qt.Orientation.Horizontal)
        self.crossfade_slider.setRange(0, 6000); self.crossfade_slider.setSingleStep(100)
        self.crossfade_slider.setValue(int(self.settings.get("crossfade_ms", 1200)))
        self.crossfade_slider.setToolTip(
            "Длительность кроссфейда. 0 = гэплесс (без фейда, только точный "
            "стык — для альбомов вроде DJ-миксов, где переход уже в самом треке)."
        )
        self.crossfade_slider.valueChanged.connect(self._on_crossfade_ms_changed)
        _cf_init = self.settings.get('crossfade_ms', 1200)
        self.crossfade_ms_lbl=QLabel(self._fmt_crossfade_ms(_cf_init)); self.crossfade_ms_lbl.setObjectName("Sub")
        self.crossfade_ms_lbl.setFixedWidth(34)
        cf_row.addWidget(cf_lbl); cf_row.addWidget(self.crossfade_slider,1); cf_row.addWidget(self.crossfade_ms_lbl)
        rv1.addLayout(cf_row)
        self.crossfade_slider.setEnabled(self.crossfade_cb.isChecked())
        self.dj_cb = QCheckBox("Умный, как DJ")
        self.dj_cb.setToolTip("Переход по темпу и под бит: начинается там, где трек реально заканчивается (а не на\n"
                              "тишине в конце), следующий входит с первой доли — доли совпадают.\n"
                              "Длина — 16 долей (5–12 с). Работает с треками из коллекции.")
        self.dj_cb.setChecked(bool(self.settings.get("dj_crossfade", False)))
        self.dj_cb.toggled.connect(lambda on: (self.settings.__setitem__("dj_crossfade", bool(on)),
                                               save_json(SETTINGS_FILE, self.settings)))
        self.dj_cb.setEnabled(self.crossfade_cb.isChecked())
        rv1.addWidget(self.dj_cb)

        self.gapless_cb = QCheckBox("Гэплесс")
        self.gapless_cb.setToolTip(
            "Убирает тишину между треками: следующий трек стартует точно в момент\n"
            "окончания предыдущего, без паузы. Идеально для альбомов SLAYER,\n"
            "концептуальных альбомов и DJ-миксов где переходы вшиты в материал.\n"
            "Совместим с кроссфейдом: если включены оба — сначала гэплесс,\n"
            "потом плавное сведение поверх него."
        )
        self.gapless_cb.setChecked(self.settings.get("gapless", False))
        self.gapless_cb.stateChanged.connect(self._on_gapless_toggled)
        rv1.addWidget(self.gapless_cb)

        self.own_out_cb = QCheckBox("Свой аудиовывод (точный gapless)")
        self.own_out_cb.setToolTip(
            "Звук всех треков идёт одним непрерывным потоком: следующий трек начинается\n"
            "ровно со следующего сэмпла — без пауз, независимо от нагрузки и FPS.\n"
            "Ещё: мгновенная громкость, мягкий лимитер на экстремальной громкости,\n"
            "визуализация точно по звуку. Выключите, если со звуком что-то не так.\n"
            "Применяется после перезапуска плеера.")
        self.own_out_cb.setChecked(bool(self.settings.get("own_audio_output", True)))
        self.own_out_cb.stateChanged.connect(self._on_own_output_toggled)
        rv1.addWidget(self.own_out_cb)
        if self.settings.get("own_audio_output", True) and not self.engine.own_output:
            self.own_out_cb.setToolTip(self.own_out_cb.toolTip() +
                                       "\n\nСейчас недоступен: нет библиотеки sounddevice или аудиоустройства.")

        self.loud_cb = QCheckBox("Выравнивать громкость треков")
        self.loud_cb.setToolTip(
            "Громкие и тихие записи звучат на одном уровне: плеер один раз измеряет\n"
            "громкость каждого трека (в фоне) и подстраивает её при воспроизведении.\n"
            "Сами файлы не меняются. Первое измерение — около секунды на трек.")
        self.loud_cb.setChecked(self.settings.get("loudness_norm", True))
        self.loud_cb.stateChanged.connect(self._on_loud_toggled)
        rv1.addWidget(self.loud_cb)

        self.inapp_cb = QCheckBox("Окна внутри приложения")
        self.inapp_cb.setToolTip(
            "Импорт из Spotify, загрузчик, редактор тегов, выбор треков, вопросы («Название плейлиста», «Удалить?»)\n"
            "открываются поверх плеера, а не отдельными окнами. Выбор файлов и папок остаётся системным.")
        self.inapp_cb.setChecked(self.settings.get("inapp_dialogs", True))
        self.inapp_cb.stateChanged.connect(self._on_inapp_toggled)
        rv1.addWidget(self.inapp_cb)

        self.titlebar_cb = QCheckBox("Собственный заголовок окна")
        self.titlebar_cb.setToolTip(
            "Заголовок окна рисуется под текущую тему (у каждой темы свой вид).\n"
            "Если выключить — будет обычная системная рамка Windows.\n"
            "Применяется после перезапуска плеера.")
        self.titlebar_cb.setChecked(self.settings.get("custom_titlebar", True))
        self.titlebar_cb.stateChanged.connect(self._on_titlebar_toggled)
        rv1.addWidget(self.titlebar_cb)

        # ── Графика: частота кадров, видео, конструктор тем ──
        sec=QLabel("Графика и производительность"); sec.setObjectName("Section"); rv1.addWidget(sec)
        import frameclock
        self.fps_cb = QComboBox()
        for val, text in frameclock.RATE_CHOICES:
            self.fps_cb.addItem(text if val <= 0 else f"{text} к/с", val)
        self.fps_cb.setCurrentIndex(max(0, self.fps_cb.findData(int(self.settings.get("fps_limit", 0)))))
        self.fps_cb.setToolTip(
            "Сколько кадров в секунду рисуют анимации (пластинка, визуализатор, фон и слои тем, текст).\n"
            "«Как у монитора» — частота обновления экрана, на котором окно (60/120/144/165/240 Гц).\n"
            "Все анимации считаются по реальному времени: при 144 к/с они не быстрее, а плавнее.")
        self.fps_cb.currentIndexChanged.connect(self._on_fps_changed)
        fps_row = QHBoxLayout(); fps_row.setSpacing(6)
        lb = QLabel("Частота кадров"); lb.setObjectName("Sub")
        self.fps_lbl = QLabel(""); self.fps_lbl.setObjectName("Sub")
        fps_row.addWidget(lb); fps_row.addWidget(self.fps_cb, 1); fps_row.addWidget(self.fps_lbl)
        rv1.addLayout(fps_row)
        self.ui_anim_cb = QCheckBox("Анимации интерфейса")
        self.ui_anim_cb.setToolTip("Плавное сворачивание окна, смена вкладок и страниц, появление меню.")
        self.ui_anim_cb.setChecked(self.settings.get("ui_animations", True))
        self.ui_anim_cb.stateChanged.connect(self._on_ui_anim_toggled)
        rv1.addWidget(self.ui_anim_cb)
        for attr, key, text, tip, default in (
                ("fps_adapt_cb", "fps_adaptive", "Снижать частоту при нагрузке",
                 "Если кадры не успевают, частота временно снижается ступенями (не ниже 60)\n"
                 "и возвращается, когда запас появится — процессор не уходит в 100 %.", True),
                ("video_hw_cb", "video_hw", "Аппаратное декодирование видео",
                 "Видео-обои и видео-слои декодирует видеокарта (D3D11VA/DXVA2): чёткая картинка\n"
                 "в полном разрешении и частоте ролика без нагрузки на процессор.", True),
                ("bg_smooth_cb", "bg_smooth", "Плавный живой фон (до 60 к/с)",
                 "Живые обои конструктора тем (сияние, плазма, звёзды…) обновляются до 60 раз в секунду\n"
                 "вместо 20–30. Плавнее, но немного тяжелее.", False),
                ("native_fx_cb", "native_fx", "C++-ускорение эффектов",
                 "Жидкость Fluid, MilkDrop, «Моя волна» и размытие считает быстрое\n"
                 "C++-ядро в несколько потоков (echoes_fx.dll) вместо Python/numpy.\n"
                 "Выключайте, только если что-то рисуется неправильно. Полностью применяется\n"
                 "после перезапуска плеера.", True),
                ("studio_dock_cb", "studio_docked", "Конструктор тем — панелью в окне плеера",
                 "Включено — конструктор встроен справа в окно плеера (рабочая панель).\n"
                 "Выключено — отдельное окно.", False)):
            cb = QCheckBox(text)
            cb.setToolTip(tip)
            cb.setChecked(bool(self.settings.get(key, default)))
            cb.toggled.connect(lambda on, k=key: self._on_perf_toggled(k, on))
            setattr(self, attr, cb)
            rv1.addWidget(cb)
        from duel_settings import tr as _performance_text
        performance_button=QPushButton(_performance_text(self,'Производительность — память и эффекты','Performance — memory and effects'))
        def open_performance():
            from performance_ui import open_dialog
            open_dialog(self)
        performance_button.clicked.connect(open_performance);rv1.addWidget(performance_button)
        self._fps_timer = QTimer(self)
        self._fps_timer.timeout.connect(self._update_fps_label)
        self._fps_timer.start(1000)

        # ── Клипы песен (режим «Клип», Ctrl+Shift+K) ──
        sec=QLabel("Клипы"); sec.setObjectName("Section"); rv1.addWidget(sec)
        self.clips_stream_cb = QCheckBox("Клипы онлайн, без скачивания")
        self.clips_stream_cb.setToolTip("Клип играет прямо из YouTube — видео на компьютер не скачивается. Скачать\n"
                                        "конкретный клип: в режиме «Клип» → «Другой клип» → «Сохранить клип на компьютер».")
        self.clips_stream_cb.setChecked(bool(self.settings.get("clips_stream", True)))
        self.clips_stream_cb.toggled.connect(self._on_clips_stream)
        rv1.addWidget(self.clips_stream_cb)
        self.clips_auto_cb = QCheckBox("Находить официальные клипы сами")
        self.clip_auto_tip = ("Для каждого играющего трека плеер в фоне найдёт официальный клип (YouTube) и\n"
                              "подгонит его по звуку, чтобы режим «Клип» открывался сразу. С «клипами онлайн»\n"
                              "ничего не скачивается; без них клип скачивается в ~/Echoes/clips.")
        self.clips_auto_cb.setToolTip(self.clip_auto_tip)
        self.clips_auto_cb.setChecked(bool(self.settings.get("clips_auto", False)))
        self.clips_auto_cb.toggled.connect(self._on_clips_auto)
        rv1.addWidget(self.clips_auto_cb)
        self.clips_q_cb = QComboBox()
        for q in (480, 720, 1080):
            self.clips_q_cb.addItem(f"{q}p", q)
        self.clips_q_cb.setCurrentIndex(max(0, self.clips_q_cb.findData(int(self.settings.get("clips_quality", 720)))))
        self.clips_q_cb.currentIndexChanged.connect(self._on_clips_quality)
        q_row = QHBoxLayout(); q_row.setSpacing(6)
        q_lb = QLabel("Качество клипов"); q_lb.setObjectName("Sub")
        q_row.addWidget(q_lb); q_row.addWidget(self.clips_q_cb, 1)
        b_open_clip = QPushButton("Открыть клип"); b_open_clip.setObjectName("GhostBtn")
        b_open_clip.clicked.connect(self._toggle_clip_mode)
        q_row.addWidget(b_open_clip)
        rv1.addLayout(q_row)
        b_clip_clean = QPushButton("Клипы и кэш: посмотреть и удалить…"); b_clip_clean.setObjectName("GhostBtn")
        b_clip_clean.setToolTip("Скачанные клипы (размер, к какому треку), удаление выбранных или всех; очистка кэша")
        b_clip_clean.clicked.connect(lambda: self.open_cleanup(1))
        rv1.addWidget(b_clip_clean)

        # ── Медиатека: кривые файлы → версии с площадок ──
        sec=QLabel("Медиатека"); sec.setObjectName("Section"); rv1.addWidget(sec)
        b_clean = QPushButton("Очистить кривые файлы…"); b_clean.setObjectName("GhostBtn")
        b_clean.setToolTip("Найти треки с плохими тегами (нет исполнителя, «(1)», «official video», адреса сайтов…) "
                           "и заменить их чистыми версиями с YouTube Music / SoundCloud — с тегами и обложкой. "
                           "Плейлисты и история сохраняются, старые файлы уходят в Корзину.")
        b_clean.clicked.connect(lambda: self.open_cleanup(0))
        rv1.addWidget(b_clean)
        b_tags = QPushButton("Найти теги для всей музыки…"); b_tags.setObjectName("GhostBtn")
        b_tags.clicked.connect(self.tag_all_library)
        rv1.addWidget(b_tags)

        sec=QLabel("Эквалайзер"); sec.setObjectName("Section"); rv1.addWidget(sec)
        self._eq_loading = False
        self._eq_auto_active = False
        self._eq_manual = None
        self._eq_manual_preset = ""
        self.eq_preset_cb = QComboBox()
        self.eq_preset_cb.setToolTip("Готовые настройки эквалайзера. Подвинете ползунок — станет «Вручную».")
        rv1.addWidget(self.eq_preset_cb)
        self.eq_auto_cb = QCheckBox("Автопресет по жанру трека")
        self.eq_auto_cb.setToolTip(
            "Для каждого трека плеер сам включает подходящий пресет (рок, хип-хоп, джаз…) по его жанру.\n"
            "Если жанр неизвестен или функцию выключить — возвращаются ваши ручные настройки.")
        self.eq_auto_cb.setChecked(self.settings.get("eq_auto_genre", False))
        self.eq_auto_cb.stateChanged.connect(self._on_eq_auto_toggled)
        rv1.addWidget(self.eq_auto_cb)
        self.eq_auto_lbl = QLabel(""); self.eq_auto_lbl.setObjectName("Sub"); self.eq_auto_lbl.setWordWrap(True)
        self.eq_auto_lbl.hide()
        rv1.addWidget(self.eq_auto_lbl)
        eq_labels = ["31", "62", "125", "250", "500", "1K", "2K", "4K", "8K", "16K"]   # реальные полосы VLC
        self._eq_sliders = []
        self._eq_labels = []
        eq_row = QHBoxLayout(); eq_row.setSpacing(3)
        for i, lbl in enumerate(eq_labels):
            col = QVBoxLayout(); col.setSpacing(2); col.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            sl = QSlider(Qt.Orientation.Vertical)
            sl.setRange(-20, 20); sl.setValue(0); sl.setFixedHeight(80)
            sl.setToolTip(f"{lbl} Hz")
            sl.valueChanged.connect(lambda v, idx=i: self._on_eq_band(idx, v))
            self._eq_sliders.append(sl)
            val_lbl = QLabel("0"); val_lbl.setObjectName("Sub")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val_lbl.setFixedWidth(28)
            self._eq_labels.append(val_lbl)
            sl.valueChanged.connect(lambda v, lb=val_lbl: lb.setText(str(v)))
            freq_lbl = QLabel(lbl); freq_lbl.setObjectName("Sub")
            freq_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            freq_lbl.setFixedWidth(28)
            col.addWidget(val_lbl); col.addWidget(sl); col.addWidget(freq_lbl)
            eq_row.addLayout(col)
        rv1.addLayout(eq_row)
        eq_btns = QHBoxLayout(); eq_btns.setSpacing(6)
        b = QPushButton("Сохранить как…"); b.setToolTip("Сохранить текущие ползунки как свой пресет")
        b.clicked.connect(self._eq_save_preset); eq_btns.addWidget(b)
        self.eq_del_btn = QPushButton("Удалить"); self.eq_del_btn.setToolTip("Удалить выбранный свой пресет")
        self.eq_del_btn.clicked.connect(self._eq_delete_preset); eq_btns.addWidget(self.eq_del_btn)
        rv1.addLayout(eq_btns)
        b = QPushButton("Сброс EQ"); b.clicked.connect(self._reset_eq); rv1.addWidget(b)

        # ── Экстремальная громкость (тот же блок есть на странице «Оформление»
        #    и в настройках Echoes Music — все копии синхронизированы) ──
        rv1.addWidget(self._make_boost_block())
        rv1.addStretch()
        self._eq_save_timer = QTimer(self); self._eq_save_timer.setSingleShot(True)
        self._eq_save_timer.timeout.connect(lambda: save_json(SETTINGS_FILE, self.settings))
        self._eq_fill_combo()
        self.eq_preset_cb.currentIndexChanged.connect(self._on_eq_preset_picked)
        self._eq_restore()
        self._bass_apply()

        # ══════════════════════════════════════════════════════════════
        #  СТРАНИЦА 2: Lo-Fi + Шум + Автономка + Открытия
        # ══════════════════════════════════════════════════════════════

        # ── Lo-Fi / Vinyl FX ─────────────────────────────────────────
        sec=QLabel("Lo-Fi атмосфера"); sec.setObjectName("Section"); rv2.addWidget(sec)
        self.cb_dust = QCheckBox("Пыль и зерно")
        self.cb_dust.setChecked(self.settings.get("fx_dust", True))
        self.cb_dust.stateChanged.connect(self._on_dust_toggled)
        rv2.addWidget(self.cb_dust)
        self.cb_breathe = QCheckBox("Дыхание фона")
        self.cb_breathe.setChecked(self.settings.get("fx_breathe", True))
        self.cb_breathe.stateChanged.connect(self._on_breathe_toggled)
        rv2.addWidget(self.cb_breathe)
        self.cb_warp = QCheckBox("Vinyl Warp (детонация)")
        self.cb_warp.setToolTip("Лёгкая имитация wow-flutter старого/погнутого винила")
        self.cb_warp.setChecked(self.settings.get("vinyl_warp", False))
        self.cb_warp.stateChanged.connect(self._on_warp_toggled)
        rv2.addWidget(self.cb_warp)
        self.cb_pause_fx = QCheckBox("Остановка пластинки на паузе")
        self.cb_pause_fx.setToolTip("Плавный spin-down/spin-up вместо резкого обрыва звука")
        self.cb_pause_fx.setChecked(self.settings.get("vinyl_pause_fx", True))
        self.cb_pause_fx.stateChanged.connect(self._on_pause_fx_toggled)
        rv2.addWidget(self.cb_pause_fx)

        # ── Атмосферный шум (дождь/уют) ──────────────────────────────
        sec=QLabel("Атмосферный шум"); sec.setObjectName("Section"); rv2.addWidget(sec)
        noise_row = QHBoxLayout()
        self.noise_combo = QComboBox()
        self.noise_combo.addItem("Розовый", "pink")
        self.noise_combo.addItem("Коричневый", "brown")
        self.noise_combo.addItem("Белый", "white")
        self.btn_noise = QPushButton("Пуск"); self.btn_noise.setObjectName("IconBtn")
        self.btn_noise.setCheckable(True); self.btn_noise.setToolTip("Играть / остановить шум")
        self.btn_noise.clicked.connect(self._toggle_noise)
        noise_row.addWidget(self.noise_combo, 1); noise_row.addWidget(self.btn_noise)
        rv2.addLayout(noise_row)
        self.noise_vol = QSlider(Qt.Orientation.Horizontal)
        self.noise_vol.setRange(0, 100); self.noise_vol.setValue(30)
        self.noise_vol.valueChanged.connect(self._on_noise_volume)
        rv2.addWidget(self.noise_vol)

        # ── Настроение дня (время суток + погода) ────────────────────
        sec=QLabel("Настроение дня"); sec.setObjectName("Section"); rv2.addWidget(sec)
        self.mood_lbl = QLabel("—"); self.mood_lbl.setObjectName("Sub"); self.mood_lbl.setWordWrap(True)
        rv2.addWidget(self.mood_lbl)
        mood_row = QHBoxLayout()
        b=QPushButton("Подобрать"); b.setObjectName("AccentBtn"); b.clicked.connect(self._build_smart_playlist)
        mood_row.addWidget(b)
        b=QPushButton("Погода и ключи"); b.clicked.connect(self._set_weather_key)
        mood_row.addWidget(b)
        rv2.addLayout(mood_row)

        # ── ИИ жанров (genre_ai): распознаёт жанр по звуку + точный онлайн-поиск ──
        sec=QLabel("Жанры (ИИ)"); sec.setObjectName("Section"); rv2.addWidget(sec)
        self.genre_ai_lbl = QLabel(""); self.genre_ai_lbl.setObjectName("Sub"); self.genre_ai_lbl.setWordWrap(True)
        rv2.addWidget(self.genre_ai_lbl)
        g_row = QHBoxLayout(); g_row.setSpacing(6)
        b = QPushButton("Распознать"); b.setObjectName("AccentBtn")
        b.setToolTip("Изучить звук всех треков, найти жанры онлайн (Deezer, iTunes, MusicBrainz, Last.fm)\n"
                     "и дообучить ИИ на вашей библиотеке. Идёт в фоне.")
        b.clicked.connect(self._genre_ai_run); g_row.addWidget(b)
        self.genre_ai_refs_btn = QPushButton("Эталоны")
        self.genre_ai_refs_btn.setToolTip(
            "Обучить ИИ на эталонах: скачать 30-секундные превью Deezer из плейлистов каждого жанра\n"
            "(≈12 на жанр, превью удаляются сразу после разбора) — модель станет точнее.")
        self.genre_ai_refs_btn.clicked.connect(self._genre_ai_refs); g_row.addWidget(self.genre_ai_refs_btn)
        rv2.addLayout(g_row)
        b = QPushButton("Жанр текущего трека"); b.clicked.connect(self._genre_ai_track_info); rv2.addWidget(b)
        QTimer.singleShot(0, self._genre_ai_refresh_status)

        # ── Таймер сна ────────────────────────────────────────────────
        sec=QLabel("Таймер сна"); sec.setObjectName("Section"); rv2.addWidget(sec)
        sleep_row = QHBoxLayout()
        self.sleep_spin = QSpinBox(); self.sleep_spin.setRange(1, 240)
        self.sleep_spin.setValue(30); self.sleep_spin.setSuffix(" мин")
        self.btn_sleep = QPushButton("Запустить"); self.btn_sleep.setObjectName("GhostBtn")
        self.btn_sleep.clicked.connect(self._toggle_sleep_timer)
        sleep_row.addWidget(self.sleep_spin, 1); sleep_row.addWidget(self.btn_sleep)
        rv2.addLayout(sleep_row)
        self.sleep_status_lbl = QLabel(""); self.sleep_status_lbl.setObjectName("Sub")
        rv2.addWidget(self.sleep_status_lbl)

        # ── Pomodoro-фокус ────────────────────────────────────────────
        sec=QLabel("Pomodoro фокус"); sec.setObjectName("Section"); rv2.addWidget(sec)
        pomo_row = QHBoxLayout()
        self.pomo_work_spin = QSpinBox(); self.pomo_work_spin.setRange(5, 90)
        self.pomo_work_spin.setValue(25); self.pomo_work_spin.setSuffix(" мин")
        self.pomo_break_spin = QSpinBox(); self.pomo_break_spin.setRange(1, 30)
        self.pomo_break_spin.setValue(5); self.pomo_break_spin.setSuffix(" мин")
        pomo_row.addWidget(self.pomo_work_spin); pomo_row.addWidget(self.pomo_break_spin)
        rv2.addLayout(pomo_row)
        self.btn_pomodoro = QPushButton("Старт фокуса"); self.btn_pomodoro.setObjectName("GhostBtn")
        self.btn_pomodoro.clicked.connect(self._toggle_pomodoro)
        rv2.addWidget(self.btn_pomodoro)
        self.pomo_status_lbl = QLabel(""); self.pomo_status_lbl.setObjectName("Sub")
        rv2.addWidget(self.pomo_status_lbl)

        # ── Открытия / экспорт ────────────────────────────────────────
        sec=QLabel("Открытия"); sec.setObjectName("Section"); rv2.addWidget(sec)
        b=QPushButton("Трек дня"); b.clicked.connect(self._play_track_of_the_day); rv2.addWidget(b)
        # импорт из Spotify / Яндекс / VK — в Настройках → Медиатека (встроенными строками, без окон)
        b=QPushButton("Экспорт GIF пластинки"); b.clicked.connect(self._export_vinyl_gif); rv2.addWidget(b)
        token_row=QHBoxLayout()                                  # токен Genius — прямо полем, без окна
        token_row.addWidget(QLabel("Genius token"))
        self.genius_edit=QLineEdit(self.settings.get("genius_token",""))
        self.genius_edit.setPlaceholderText("Access token для текстов с Genius")
        self.genius_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.genius_edit.editingFinished.connect(
            lambda: (self.settings.__setitem__("genius_token",self.genius_edit.text().strip()),
                     save_json(SETTINGS_FILE,self.settings)))
        token_row.addWidget(self.genius_edit,1)
        rv2.addLayout(token_row)

        # ── Discord Rich Presence ─────────────────────────────────────
        sec=QLabel("Discord Rich Presence"); sec.setObjectName("Section"); rv2.addWidget(sec)
        self.discord_rpc_cb = QCheckBox("Показывать трек в Discord")
        self.discord_rpc_cb.setChecked(self.settings.get("discord_rpc", True))
        self.discord_rpc_cb.stateChanged.connect(self._on_discord_rpc_toggled)
        rv2.addWidget(self.discord_rpc_cb)
        self.discord_covers_cb = QCheckBox("Обложка трека в Discord (ищется на Deezer)")
        self.discord_covers_cb.setToolTip("Discord показывает только картинки из интернета: обложка находится по "
                                          "исполнителю и названию на Deezer и кешируется. Выключено — пластинка ECHOES")
        self.discord_covers_cb.setChecked(self.settings.get("discord_covers", True))
        self.discord_covers_cb.toggled.connect(lambda on: self._discord_opt("discord_covers", on))
        rv2.addWidget(self.discord_covers_cb)
        self.discord_act_cb = QCheckBox("Показывать в Discord ECHOES Studio и конструктор тем")
        self.discord_act_cb.setToolTip("Отдельные активности со своими иконками: «ECHOES Studio» (проект, BPM), "
                                       "«Конструктор тем ECHOES» (тема)")
        self.discord_act_cb.setChecked(self.settings.get("discord_activities", True))
        self.discord_act_cb.toggled.connect(self._discord_act_toggled)
        rv2.addWidget(self.discord_act_cb)
        b = QPushButton("Иконки активностей для Discord…")
        b.setObjectName("GhostBtn")
        b.setToolTip("Открыть папку с иконками и страницу Art Assets вашего приложения Discord")
        b.clicked.connect(self._discord_icons_help)
        rv2.addWidget(b)
        cb = QCheckBox("Останавливать фоны и эффекты конструктора тем вне фокуса")
        cb.setChecked(self.settings.get("pause_unfocused", True))
        cb.toggled.connect(lambda on: (self.settings.__setitem__("pause_unfocused", on), self.save_settings()))
        rv2.addWidget(cb)
        sec=QLabel("Стример тул"); sec.setObjectName("Section"); rv2.addWidget(sec)
        b = QPushButton("Окно «Сейчас играет» (захват окна в OBS / TikTok LIVE Studio)")
        b.setObjectName("AccentBtn")
        b.clicked.connect(self._open_stream_widget)
        rv2.addWidget(b)
        for key, label, tip in (
                ("artist", "Фото исполнителя на обложке", "Маленький кружок с фото исполнителя (Deezer)"),
                ("queue", "Место в очереди «(3 из 12)»", "Номер трека в плейлисте, альбоме или волне"),
                ("link", "Кнопка-ссылка на трек", "Вторая кнопка: трек на Deezer, Apple Music, SoundCloud или YouTube"),
                ("stats", "Статистика в подсказке", "Наведите на фото исполнителя: сколько вы сегодня слушаете "
                                                    "в ECHOES и какой раз играет этот трек")):
            cb = QCheckBox(label)
            cb.setToolTip(tip)
            cb.setChecked(self.settings.get("discord_" + key, True))
            cb.toggled.connect(lambda on, k=key: self._discord_feature(k, on))
            rv2.addWidget(cb)
        self.discord_paused_cb = QCheckBox("Показывать в Discord и на паузе")
        self.discord_paused_cb.setToolTip("Выключено — как у Spotify: на паузе статус пропадает")
        self.discord_paused_cb.setChecked(self.settings.get("discord_paused", True))
        self.discord_paused_cb.toggled.connect(lambda on: self._discord_opt("discord_paused", on))
        rv2.addWidget(self.discord_paused_cb)
        self.media_session_cb = QCheckBox("Показывать трек в Windows (медиа-виджет, медиаклавиши)")
        self.media_session_cb.setToolTip("Что играет — в плашке громкости Windows, на экране блокировки и в Game Bar; "
                                         "кнопки там и медиаклавиши клавиатуры управляют ECHOES.")
        self.media_session_cb.setChecked(self.settings.get("media_session", True))
        self.media_session_cb.toggled.connect(self._on_media_session_toggled)
        rv2.addWidget(self.media_session_cb)
        discord_hint = QLabel("В Discord — «Слушает ECHOES», как у Spotify: сначала исполнитель, потом трек и альбом, "
                              "полоса прогресса и кнопка «Слушать на YouTube Music». Нужен запущенный Discord.")
        discord_hint.setWordWrap(True)
        discord_hint.setObjectName("Sub")
        rv2.addWidget(discord_hint)
        b=QPushButton("Вставить Discord Client ID"); b.setObjectName("GhostBtn"); b.clicked.connect(self._set_discord_client_id); rv2.addWidget(b)
        rv2.addStretch()

        self._left_panel = left
        self._right_panel = right
        outer.addWidget(left,2); outer.addWidget(center,5); outer.addWidget(right,2)

        # LyricsView — overlay поверх root, но НЕ поверх транспортной панели
        self.lyrics_view.setParent(root)
        self.lyrics_view.setGeometry(root.rect())
        self.lyrics_view.hide()

        self.lyrics_view.set_vinyl(self.vinyl)
        self.lyrics_view.set_normal_widget(self._normal_widget)
        self.lyrics_view.set_viz(self.viz)
        self.lyrics_view.set_title_artist(self.title_lbl, self.artist_lbl)
        self.lyrics_view.set_lyrics_btn(self.btn_lyrics_mode)
        self.lyrics_view.set_side_panels(self._left_panel, self._right_panel)
        self.lyrics_view.set_transport_bar(self.transport_bar)
        self.lyrics_view.set_close_callback(self._toggle_lyrics_mode)
        self.lyrics_view.set_leave_finished_callback(self._on_lyrics_left)
        self.lyrics_view.set_fluid_source(self._stage)
        if hasattr(self.lyrics_view, "set_seek_callback"):
            self.lyrics_view.set_seek_callback(self._lyrics_seek)
        self.lyrics_view.set_tags_button(False, self.edit_current_tags)

        # ── Скретч: vinyl → AudioEngine ──────────────────────────────────
        self._scratch_was_playing = False
        self.vinyl.scratch_started.connect(self._on_scratch_start)
        self.vinyl.scratch_moved.connect(self._on_scratch_move)
        self.vinyl.scratch_released.connect(self._on_scratch_release)

        # Пыль/зерно — самый верхний декоративный слой, создаётся последним,
        # чтобы лечь поверх всего интерфейса (включая LyricsView-overlay).
        # WA_TransparentForMouseEvents гарантирует, что клики сквозь него
        # проходят к реальным виджетам без изменений.
        self._dust = DustParticles(root)
        self._dust.setGeometry(root.rect())
        self._dust.raise_()
        self._dust.set_enabled(self.settings.get("fx_dust", True))

    def _on_scratch_start(self):
        """Запоминаем состояние плеера и ставим на паузу во время скретча."""
        self._scratch_was_playing = self.engine.is_playing()
        if self._scratch_was_playing:
            self.engine.pause()
            # Не меняем UI-кнопку — пользователь видит, что трек «зажат»

    def _on_scratch_move(self, delta_sec: float):
        """Двигаем позицию трека пропорционально повороту диска."""
        if not self.engine.current_path:
            return
        dur = float(self.engine.duration or 0.0)
        if dur <= 0:
            return
        cur = self.engine.get_position()
        new_pos = max(0.0, min(dur, cur + delta_sec))
        self.engine.seek(new_pos)

    def _on_scratch_release(self):
        """Возобновляем воспроизведение, если трек играл до скретча."""
        if self._scratch_was_playing:
            self.engine.play()
            self._set_playing_ui(True)

    def _icon(self, text, tip):
        b=QPushButton(text); b.setObjectName("IconBtn"); b.setToolTip(tip); return b

    @staticmethod
    def _round_pixmap(src: QPixmap, size: int) -> QPixmap:
        """Возвращает квадратный pixmap с закруглёнными углами (radius = 30%)."""
        from PyQt6.QtGui import QPainter, QBrush, QPainterPath
        scaled = src.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                            Qt.TransformationMode.SmoothTransformation)
        # crop to square
        x = (scaled.width() - size) // 2
        y = (scaled.height() - size) // 2
        scaled = scaled.copy(x, y, size, size)
        out = QPixmap(size, size)
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = size * 0.30
        path = QPainterPath()
        path.addRoundedRect(0, 0, size, size, radius, radius)
        p.setClipPath(path)
        p.drawPixmap(0, 0, scaled)
        p.end()
        return out

    def _fill_theme_combo(self):
        """Список тем с разделами: «полные» темы отдельно от цветовых схем.
        Заголовки разделов неактивны (выбрать их нельзя)."""
        from PyQt6.QtGui import QFont as _QFont
        cb = self.theme_cb
        cb.blockSignals(True)
        cb.clear()
        model = cb.model()
        for gi, (title, hint, names) in enumerate(theme_groups()):
            if not names:
                continue
            if gi > 0:
                cb.insertSeparator(cb.count())
            cb.addItem(title)
            item = model.item(cb.count() - 1)
            item.setFlags(Qt.ItemFlag.NoItemFlags)          # заголовок: не выбирается
            f = _QFont(item.font()); f.setBold(True)
            item.setFont(f)
            item.setToolTip(hint)
            for n in names:
                cb.addItem(n)
                model.item(cb.count() - 1).setToolTip(hint)
        cb.blockSignals(False)

    def _request_theme(self, name):
        if name not in THEMES:
            return              # заголовок раздела / разделитель
        """Смена темы из комбобокса ОТКЛАДЫВАЕТСЯ до следующего витка цикла
        событий. Темы Winamp/Fluid перестраивают раскладку и переносят панель,
        внутри которой лежит сам комбобокс; делать это прямо в его сигнале
        (пока он ещё закрывает выпадающий список) — прямой путь к нативному
        падению Qt без всякого traceback'а."""
        QTimer.singleShot(0, lambda n=name: self._apply_theme(n))

    def _apply_theme(self,name):
        montage = getattr(self, "_montage", None)
        if montage is not None and name != "ECHOES Montage":
            if not montage.request_close(lambda n=name: self._apply_theme(n)):
                return
        if name not in THEMES: name = "Echoes Music" if "Echoes Music" in THEMES else next(iter(THEMES))
        self._preview_theme = None               # выбрали тему — предпросмотр конструктора закончен
        self._manual_theme_name = name
        self.settings["theme"]=name
        self._apply_theme_data(THEMES[name], selector_name=name)
        save_json(SETTINGS_FILE,self.settings)
        try:
            import mem_trim                          # старая тема разобрана — её память отдать системе
            mem_trim.trim_later(3000)
        except Exception:                            # noqa: BLE001
            pass

    def _apply_theme_data(self, theme_data, selector_name=None):
        montage = getattr(self, "_montage", None)
        if montage is not None and not theme_data.get("montage"):
            if not montage.request_close(lambda d=theme_data, n=selector_name: self._apply_theme_data(d, n)):
                return
            self._leave_montage_layout()
        is_custom = bool(theme_data.get("custom"))
        if is_custom:
            theme_data = self._custom_prepare(theme_data)
        self._clip_restyle(theme_data)                   # режим клипа — в стиле новой темы
        if is_custom:
            if self._custom_on and not getattr(self, "_lyrics_mode", False):
                self._custom_fast(theme_data, selector_name)   # тема из конструктора уже на экране
                return
        bg = theme_data["bg"]
        is_light = QColor(bg).value() > 170
        glow = "#000000" if is_light else theme_data.get("glow", theme_data["accent2"])
        extra = f"""
        QWidget#Root {{
            background: qradialgradient(
                cx:0.15, cy:0.0, radius:0.75,
                fx:0.15, fy:0.0,
                stop:0   {glow}e6,
                stop:0.28 {glow}70,
                stop:0.60 #000000cc,
                stop:1   {bg}
            );
        }}
        """
        is_fluid = bool(theme_data.get("fluid"))
        is_winamp = bool(theme_data.get("winamp"))
        is_ya = bool(theme_data.get("yamusic"))
        is_daw = bool(theme_data.get("daw"))
        is_montage = bool(theme_data.get("montage"))
        if (is_ya or is_daw or is_montage) and getattr(self, "_lyrics_mode", False):
            # обычный режим текста сначала закрываем — он завязан на старую раскладку
            self._toggle_lyrics_mode()
            QTimer.singleShot(950, lambda d=theme_data, n=selector_name: self._apply_theme_data(d, n))
            return
        if is_fluid or is_winamp or is_ya or is_daw or is_montage:
            extra = f"QWidget#Root {{ background: {bg}; }}"     # плоский фон: беж / «рабочий стол»
        if is_custom:
            extra = "QWidget#Root { background: transparent; }"  # фон рисует конструктор (ThemeRuntime)
        else:
            self._custom_clear()
        qss = build_qss(theme_data) + extra
        if qss != self._last_qss:                # пересборка стилей всего окна дорогая — только если изменились
            self._last_qss = qss
            self.setStyleSheet(qss)
        _apply_app_palette(theme_data)
        if getattr(self, "titlebar", None) is not None:
            self.titlebar.set_theme(theme_data)
        if selector_name is not None and hasattr(self, "theme_cb"):
            self.theme_cb.blockSignals(True)
            self.theme_cb.setCurrentText(selector_name)
            self.theme_cb.blockSignals(False)
        self._switch_visualizer(selector_name == "Milkdrop")
        self.viz.set_accent(QColor(theme_data["accent"]), QColor(theme_data["accent2"]))
        if hasattr(self, "seek"):
            self.seek.set_colors(QColor(theme_data["accent"]), QColor(theme_data["accent2"]))
        if hasattr(self, "lyrics_view"):
            self.lyrics_view.set_accent(QColor(theme_data["accent"]), QColor(theme_data["accent2"]))
        if hasattr(self, "vinyl"):
            self.vinyl.set_ambient_override(QColor("#000000") if is_light else None)
        if hasattr(self, "btn_play"):
            btn_bg = QColor(theme_data["text"])
            # Перцептивная яркость (luma) вместо .value() (=max(r,g,b)) —
            # даёт куда более надёжный контраст иконки на разных темах.
            luma = 0.299 * btn_bg.red() + 0.587 * btn_bg.green() + 0.114 * btn_bg.blue()
            icon_col = QColor(theme_data["bg"]) if luma > 140 else QColor("#f5f5f7")
            self.btn_play.set_icon_color(icon_col)
        if hasattr(self, "lyrics_view"):
            self.lyrics_view.set_light_theme(is_light)
        if is_daw and not getattr(self, "_daw_on", False):
            # тяжёлые модули студии (numpy/scipy, движок) грузим ДО разборки прежней темы:
            # сборка мусора посреди импорта, пока удаляется старая оболочка, роняла Qt
            try:
                import gc
                import daw_theme  # noqa: F401
                gc.collect()
            except Exception as e:                       # noqa: BLE001
                print("[studio] import:", e)
        # Порядок важен: сперва снимаем Winamp-раскладку (Fluid ждёт обычную),
        # потом Fluid, и только потом включаем Winamp поверх обычной раскладки.
        if not is_winamp:
            self._apply_winamp_mode(theme_data, False)
        if not is_ya:
            self._leave_ya_layout()
        if not is_daw:
            self._leave_daw_layout()
        self._apply_fluid_mode(theme_data, is_fluid)
        if is_winamp:
            self._apply_winamp_mode(theme_data, True)
        if is_ya or is_daw:
            if is_ya:
                self._enter_ya_layout()
                if theme_data.get('duel'):
                    self._ya.show_page('duel')
            else:
                self._enter_daw_layout()
            if hasattr(self, "_ambience"):
                self._ambience.set_enabled(False)
            if hasattr(self, "_dust"):
                self._dust.set_enabled(False)
        if theme_data.get("montage"):
            self._enter_montage_layout()
        if is_custom:
            self._custom_apply(theme_data)

    # ------------------------------------------------------------------ #
    #  Темы из конструктора                                               #
    # ------------------------------------------------------------------ #

    def _custom_runtime(self):
        if self._crt is None:
            from theme_layers import ThemeRuntime
            self._crt = ThemeRuntime(self, self.engine, self.theme_store, self._custom_panel_rects)
            # выход из программы без закрытия окна (из трея, Ctrl+Q…) — всё равно остановить GIF/видео/таймеры
            QApplication.instance().aboutToQuit.connect(self._custom_shutdown)
        return self._crt

    def _custom_shutdown(self):
        try:
            if self._crt is not None:
                self._crt.clear()
        except Exception:                                 # noqa: BLE001
            pass

    def _custom_panel_rects(self):
        """Видимые боковые панели (и плашка под кнопками, если включена) в координатах окна —
        под ними матовое стекло и тени."""
        out = []
        ws = [getattr(self, "_left_panel", None), getattr(self, "_right_panel", None)]
        t = self._crt.theme if self._crt is not None else None
        if t is not None and t["components"]["panels"].get("dock") and not getattr(self, "_lyrics_mode", False):
            ws.append(getattr(self, "transport_bar", None))
        lyr = self._lyrics_custom_on()
        for w in ws:
            try:
                if lyr and w is not None and not w.property("echoesFree"):
                    continue                              # своё оформление текста: погашенным панелям стекло не нужно
                if w is not None and w.isVisible() and w.window() is self and w.width() > 0:
                    tl = w.mapTo(self, QPoint(0, 0))
                    out.append(QRectF(tl.x(), tl.y(), w.width(), w.height()))
            except RuntimeError:
                pass
        return out

    def _custom_prepare(self, d):
        """Шрифты темы (в т.ч. свои файлы) регистрируются до сборки стилей."""
        ct = d["ct"]
        rt = self._custom_runtime()
        rt.theme = ct
        f = ct["font"]
        body = rt.font_family(f.get("file")) or f.get("family") or ""
        title = rt.font_family(f.get("title_file")) or f.get("title_family") or body
        d = dict(d)
        d["_font_family"], d["_title_family"] = body, title
        d["_play_style"] = ct["components"]["play"].get("style", "text")
        return d

    def _custom_fast(self, d, selector_name=None, styles=True):
        """Смена одной темы из конструктора на другую (или правка в конструкторе): раскладка уже
        классическая — только стили, цвета и элементы, без перестройки режимов Fluid/Winamp/EM."""
        is_light = QColor(d["bg"]).value() > 170
        qss = build_qss(d) + "QWidget#Root { background: transparent; }"
        if styles and qss != self._last_qss:              # пересборка стилей окна ~0.3 с — только когда нужно
            self._last_qss = qss
            self.setStyleSheet(qss)
        _apply_app_palette(d)
        if getattr(self, "titlebar", None) is not None:
            self.titlebar.set_theme(d)
        if selector_name is not None and hasattr(self, "theme_cb"):
            self.theme_cb.blockSignals(True)
            self.theme_cb.setCurrentText(selector_name)
            self.theme_cb.blockSignals(False)
        if hasattr(self, "lyrics_view"):
            self.lyrics_view.set_accent(QColor(d["accent"]), QColor(d["accent2"]))
            self.lyrics_view.set_light_theme(is_light)
        self.vinyl.set_ambient_override(QColor("#000000") if is_light else None)
        self._custom_apply(d)

    def _custom_layout(self, p, margin, spacing):
        """Панели: какие видны, порядок (зеркально), профиль, подсказки, отступы."""
        outer = self._outer
        left, center, right = self._left_panel, self._stage, self._right_panel
        cur = [outer.itemAt(i).widget() for i in range(outer.count())]
        want = [right, center, left] if p.get("swap") else [left, center, right]
        if cur != want and sorted(map(id, cur)) == sorted(map(id, want)):
            for w in want:
                outer.removeWidget(w)
            for w, k in zip(want, (2, 5, 2)):
                outer.addWidget(w, k)
        if cur == [] or sorted(map(id, cur)) == sorted(map(id, want)):
            outer.setContentsMargins(margin, margin, margin, margin)
            outer.setSpacing(spacing)
            for w, on in ((left, p.get("left", True)), (right, p.get("right", True))):
                w.setProperty("echoesHidden", not on)
                w.setVisible(on)
        for w in (self.avatar_lbl, self.nick_lbl, self.status_lbl, self.btn_edit):
            w.setVisible(bool(p.get("profile", True)))
        for w in (getattr(self, "_lib_hint", None), getattr(self, "_pl_hint", None)):
            if w is not None:
                w.setVisible(bool(p.get("hints", True)))
        lay = self.transport_bar.layout() if hasattr(self, "transport_bar") else None
        if lay is not None and not getattr(self, "_fluid_layout_on", False):
            lay.setContentsMargins(*((18, 12, 18, 6) if p.get("dock") else (0, 0, 0, 0)))

    def _custom_elements(self):
        """Видимость пластинки и визуализатора по теме (после режима текста и т.п.)."""
        if not self._custom_on or self._crt is None or self._crt.theme is None:
            return
        c = self._crt.theme["components"]
        if getattr(self, "_lyrics_mode", False) or getattr(self, "_playlist_detail_open", False):
            return
        for w, hide in ((self.vinyl, c["vinyl"]["style"] == "hidden"), (self.viz, c["visualizer"]["style"] == "none")):
            w.setProperty("echoesHidden", hide)
            w.setVisible(not hide)

    def studio_lyrics_mode(self, on: bool):
        """Конструктор переключился на режим текста (или обратно) — плеер показывает то, что правят."""
        if getattr(self, "_wa_on", False) or bool(on) == bool(getattr(self, "_lyrics_mode", False)):
            return
        self._toggle_lyrics_mode()

    def _lyrics_custom_on(self, ct=None) -> bool:
        """У темы из конструктора своё оформление режима текста и он сейчас открыт."""
        ct = ct if ct is not None else self.__dict__.get("_custom_full")
        return bool(self._custom_on and ct is not None and getattr(self, "_lyrics_mode", False)
                    and (ct.get("lyrics") or {}).get("on"))

    def _custom_view(self, ct):
        """Тема так, как её сейчас видно: в режиме текста — его фон, слои, эффекты и раскладка."""
        return theme_kit.lyrics_view(ct) if self._lyrics_custom_on(ct) else ct

    def _lyrics_custom_style(self, ct):
        """Стиль текста и раскладка элементов режима текста — в LyricsView."""
        lv = getattr(self, "lyrics_view", None)
        if lv is None:
            return
        ly = (ct or {}).get("lyrics") or {}
        try:
            if self._custom_on and ly.get("on"):
                tx = ly.get("text") or {}
                fam = self._custom_runtime().font_family(tx.get("file")) or tx.get("family") or ""
                lv.set_custom(tx, ly.get("native") or {}, fam)
            else:
                lv.set_custom(None, None)
        except Exception:                                 # noqa: BLE001
            traceback.print_exc()

    def _custom_mode_switch(self):
        """Режим текста открыли/закрыли: у темы своё оформление текста — переключить фон, слои, раскладку."""
        ct = self.__dict__.get("_custom_full")
        if not self._custom_on or ct is None or not (ct.get("lyrics") or {}).get("on"):
            return
        vt = self._custom_view(ct)
        rt = self._custom_runtime()
        try:
            rt.apply(vt)
            rt.set_cover(self._cur_cover)
            rt.raise_overlay()
        except Exception:                                 # noqa: BLE001
            traceback.print_exc()
        self._native_apply(vt)

    def _custom_apply(self, d):
        ct = d["ct"]
        self._custom_full = ct
        ct = self._custom_view(ct)
        rt = self._custom_runtime()
        c = ct["components"]
        light = theme_kit.is_light(ct["palette"]["bg"])
        self._custom_on = True
        # декоративные слои классической темы не нужны — фон и частицы рисует конструктор
        if hasattr(self, "_ambience"):
            self._ambience.set_enabled(False)
        if hasattr(self, "_dust"):
            self._dust.set_enabled(False)
        self._custom_layout(c["panels"], ct["shape"]["margin"], ct["shape"]["spacing"])
        v = c["visualizer"]
        self.viz.set_style(v["style"] if v["style"] != "none" else "bars", v.get("peaks", True), v.get("curve", True))
        self.viz.set_accent(QColor(v.get("color1") or d["accent"]), QColor(v.get("color2") or d["accent2"]))
        vn = c["vinyl"]
        self.vinyl.set_graphic(vn["style"] == "graphic", not light)
        self.vinyl.set_disc_scale(vn.get("scale", 1.0))
        self.vinyl.set_tonearm(vn.get("tonearm", True))
        self._custom_vinyl_image(vn.get("image") or "", ct)
        self._custom_elements()
        sk = c["seek"]
        if hasattr(self, "seek"):
            self.seek.set_colors(QColor(sk.get("color1") or d["accent"]), QColor(sk.get("color2") or d["accent2"]))
        if hasattr(self, "btn_play"):
            pb = QColor(d["accent"] if c["play"].get("style") == "accent" else d["text"])
            luma = 0.299 * pb.red() + 0.587 * pb.green() + 0.114 * pb.blue()
            self.btn_play.set_icon_color(QColor("#08090d") if luma > 140 else QColor("#f5f5f7"))
        # межбуквенный интервал — шрифтом окна (QSS его не умеет), наследуют все виджеты
        sp = float(ct["font"].get("spacing", 0.0))
        f = self.font()
        if abs(f.letterSpacing() - sp) > 1e-3 or f.letterSpacingType() != QFont.SpacingType.AbsoluteSpacing:
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, sp)
            self.setFont(f)
        rt.apply(ct)
        rt.set_cover(self._cur_cover)
        rt.raise_overlay()
        # оформление режима текста (шрифт, цвета, раскладка) — до раскладки родных элементов
        self._lyrics_custom_style(self._custom_full)
        # родные элементы (пластинка, визуализатор, кнопки, панели…): свои места, размеры, скрытые
        self._native_apply(ct)
        # «Только слои»: обычный интерфейс спрятан — кнопки, перемотка и т.д. теперь слои-виджеты темы
        self._custom_ui_layers(c.get("ui") == "layers" and not getattr(self, "_lyrics_mode", False))

    def _custom_vinyl_image(self, rel, ct):
        """Тема из конструктора может крутить свою картинку (PNG) вместо диска пластинки."""
        try:
            import player_prefs
            path = self.theme_store.asset(ct, rel) if (rel and ct is not None) else ""
            player_prefs.apply_vinyl_image(self, path or "")
        except Exception as e:                            # noqa: BLE001
            print("[theme] vinyl image:", e)

    def _custom_clear(self):
        """Уход с темы из конструктора: всё, что она меняла, — как было."""
        if not self._custom_on:
            return
        self._custom_on = False
        self._custom_full = None
        self._lyrics_custom_style(None)
        self._custom_ui_layers(False)
        self._native_reset()
        if self._crt is not None:
            self._crt.clear()
        self._custom_layout({}, 12, 10)
        for w in (self.vinyl, self.viz):
            w.setProperty("echoesHidden", False)
            if not getattr(self, "_lyrics_mode", False) and not getattr(self, "_playlist_detail_open", False):
                w.show()
        self.viz.set_style("bars", True, True)
        self.vinyl.set_disc_scale(1.0)
        self.vinyl.set_tonearm(True)
        self._custom_vinyl_image("", None)
        f = self.font()
        if abs(f.letterSpacing()) > 1e-3:
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.0)
            self.setFont(f)

    def custom_preview(self, theme: dict | None, layers_only: bool = False, styles: bool = True):
        """Конструктор: применить тему вживую (без сохранения и без смены выбранной темы).
        layers_only — поменялись только слои (быстро, без пересборки фона и стилей).
        None — закончить предпросмотр и вернуть выбранную тему."""
        if theme is None:
            if self._preview_theme is not None:
                self._preview_theme = None
                self._apply_theme(self._manual_theme_name)
            return
        self._preview_theme = theme
        if layers_only and self._custom_on and self._crt is not None and self._crt.active():
            self._custom_full = theme
            self._crt.update_layers(self._custom_view(theme))
            return
        if not styles and self._custom_on:                # тянут ползунок: стили окна — после отпускания
            self._custom_fast(self._custom_prepare(theme_kit.to_theme_data(theme)), styles=False)
            return
        t2 = self._custom_cover_accent(theme, self._cur_cover) if self._cur_cover else None
        self._apply_theme_data(theme_kit.to_theme_data(t2 or theme))

    def custom_themes_changed(self, select_id=None):
        """Конструктор сохранил/удалил тему: обновить список тем; select_id — сделать текущей."""
        cur = self.settings.get("theme", "")
        cur_id = self._custom_keys.get(cur)
        self._custom_keys = register_custom_themes(self.theme_store, theme_kit.to_theme_data)
        self._fill_theme_combo()
        key_of = {v: k for k, v in self._custom_keys.items()}
        if select_id is not None and select_id in key_of:
            self._apply_theme(key_of[select_id])
        elif cur_id is not None:                          # активная тема переименована или удалена
            self._apply_theme(key_of.get(cur_id, "Echoes Music"))
        elif hasattr(self, "theme_cb"):
            self.theme_cb.blockSignals(True)
            self.theme_cb.setCurrentText(cur)
            self.theme_cb.blockSignals(False)

    def current_custom_theme_id(self):
        return self._custom_keys.get(self.settings.get("theme", ""))

    def _open_theme_studio(self, theme_id=None):
        try:
            from theme_studio import ThemeStudio
        except Exception as e:                            # noqa: BLE001
            traceback.print_exc()
            QMessageBox.warning(self, "Конструктор тем", f"Не удалось открыть конструктор:\n{e}")
            return
        st = self._studio
        try:
            alive = st is not None and st.isVisible() is not None
        except RuntimeError:
            alive = False
        if not alive:
            st = self._studio = ThemeStudio(self)
        st.open_theme(theme_id if theme_id is not None else self.current_custom_theme_id())
        self._place_studio(st)

    # ── конструктор тем: встроенная панель или отдельное окно ── #

    def studio_docked(self) -> bool:
        return bool(self.settings.get("studio_docked", False))

    def set_studio_docked(self, on: bool):
        self.settings["studio_docked"] = bool(on)
        save_json(SETTINGS_FILE, self.settings)
        cb = getattr(self, "studio_dock_cb", None)
        if cb is not None and cb.isChecked() != bool(on):
            cb.blockSignals(True)
            cb.setChecked(bool(on))
            cb.blockSignals(False)
        st = self._studio
        try:
            if st is not None and st.isVisible():
                self._place_studio(st)
        except RuntimeError:
            pass

    def _place_studio(self, st):
        """Показать конструктор: панелью справа в окне плеера (QDockWidget) или отдельным окном."""
        from PyQt6.QtWidgets import QDockWidget
        dock = getattr(self, "_studio_dock", None)
        if self.studio_docked():
            if dock is None:
                dock = QDockWidget(self)
                dock.setObjectName("StudioDock")
                dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
                dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
                dock.setTitleBarWidget(QWidget())             # свой заголовок — у самого конструктора
                dock.installEventFilter(self)
                self._studio_dock = dock
                self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
            if dock.widget() is not st:
                st.setWindowFlags(Qt.WindowType.Widget)
                dock.setWidget(st)
            st.setMinimumSize(400, 300)
            dock.setMinimumWidth(400)
            dock.show()
            st.show()
            # панель — около трети окна (не больше 520 px), остальное — плееру с темой
            self.resizeDocks([dock], [max(400, min(520, self.width() // 3))], Qt.Orientation.Horizontal)
        else:
            if dock is not None:
                if dock.widget() is st:
                    st.setParent(None)
                    st.setParent(self, Qt.WindowType.Window)
                dock.hide()
            st.setWindowFlags(Qt.WindowType.Window)
            st.setMinimumSize(520, 560)
            st.show()
            st._place()
            st.raise_()
            st.activateWindow()
        if hasattr(st, "_sync_dock_button"):
            st._sync_dock_button()
        QTimer.singleShot(0, self._studio_area_changed)

    def close_studio(self):
        st = self._studio
        if st is None:
            return
        try:
            if st.close():
                dock = getattr(self, "_studio_dock", None)
                if dock is not None:
                    dock.hide()
        except RuntimeError:
            pass
        QTimer.singleShot(0, self._studio_area_changed)

    def _custom_area(self):
        """Где рисуется тема из конструктора: окно, кроме встроенной панели конструктора."""
        r = self.rect()
        dock = getattr(self, "_studio_dock", None)
        try:
            if dock is not None and dock.isVisible() and not dock.isFloating():
                g = dock.geometry()
                if g.center().x() > r.center().x():
                    r.setRight(g.left() - 1)
                else:
                    r.setLeft(g.right() + 1)
        except RuntimeError:
            pass
        return r

    def _studio_area_changed(self):
        crt = getattr(self, "_crt", None)
        if crt is not None and crt.active():
            crt.resize()
            crt.refresh()
        st = self._studio
        try:
            if st is not None and st.canvas is not None:
                st.canvas._follow()
        except RuntimeError:
            pass

    # ── LOOM → конструктор тем ── #

    def _loom_migrate(self):
        try:
            import layer_fx
            made = layer_fx.migrate_loom_scripts(self.theme_store, self.settings)
        except Exception as e:                            # noqa: BLE001
            print("[loom] перенос:", e)
            return
        if made:
            m = dict(self.settings.get("loom_theme_map") or {})
            m.update(made)
            self.settings["loom_theme_map"] = m
            save_json(SETTINGS_FILE, self.settings)
            print("[loom] перенесено в конструктор тем:", ", ".join(made.values()))

    def _map_loom_theme(self):
        """Выбранная раньше тема LOOM («Loom» или «◈ Скрипт») → её перенесённая копия «✦ …»."""
        old = self.settings.get("theme", "")
        if old != "Loom" and not old.startswith("◈ "):
            return
        name = old[2:] if old.startswith("◈ ") else "Loom"
        new = (self.settings.get("loom_theme_map") or {}).get(name, name)
        key = CUSTOM_PREFIX + new
        if key in THEMES:
            self.settings["theme"] = key

    # ── экспорт с эффектами ── #

    def _export_effects(self, tracks):
        try:
            import dsp_export
            dsp_export.open_dialog(self, tracks)
        except Exception as e:                            # noqa: BLE001
            traceback.print_exc()
            QMessageBox.warning(self, "Экспорт с эффектами", f"Не получилось открыть экспорт:\n{e}")

    # ── частота кадров ── #

    def _init_fps(self):
        self._apply_fps()
        try:
            wh = self.windowHandle()
            if wh is not None:
                wh.screenChanged.connect(lambda _s: self._apply_fps())    # окно переехало на другой монитор
        except Exception:                                 # noqa: BLE001
            pass

    def _apply_fps(self):
        try:
            import frameclock
            frameclock.configure(self.settings, self)
        except Exception as e:                            # noqa: BLE001
            print("[fps]", e)
        self._update_fps_label()

    def _on_fps_changed(self, _i=0):
        self.settings["fps_limit"] = int(self.fps_cb.currentData())
        save_json(SETTINGS_FILE, self.settings)
        self._apply_fps()

    def _update_fps_label(self):
        lbl = getattr(self, "fps_lbl", None)
        if lbl is None or not lbl.isVisible():
            return
        import frameclock
        c = frameclock.clock()
        txt = f"{c.rate:.0f} Гц"
        if c.measured > 1:
            txt = f"сейчас {c.measured:.0f} · {txt}"
        lbl.setText(txt)
        lbl.setToolTip(f"Цель: {c.target:.0f} к/с" + (" (монитор)" if c.vsync else "") +
                       (" · регулятор снизил частоту из-за нагрузки" if c.rate < c.target - 0.5 else ""))

    def _on_perf_toggled(self, key, on):
        self.settings[key] = bool(on)
        save_json(SETTINGS_FILE, self.settings)
        if key == "fps_adaptive":
            self._apply_fps()
        elif key == "studio_docked":
            self.set_studio_docked(bool(on))
        elif key == "video_hw":
            crt = getattr(self, "_crt", None)
            if crt is not None and crt.active() and crt.theme is not None:   # пересоздать видео с новым декодером
                crt._video_path = None
                for src in list(crt._videos.values()):
                    if src is not None:
                        src.stop()
                crt._videos.clear()
                crt.apply(crt.theme)

    # ── «Только слои»: обычный интерфейс спрятан, вместо него — слои-виджеты темы ── #

    def _custom_ui_restore(self):
        """После режима текста / клипа: интерфейс снова как в теме. В «Только слои» обычные панели
        прячутся обратно, спрятанные темой элементы не появляются (раньше выход показывал всё подряд,
        и панели, которых в теме нет, расталкивали остальное)."""
        if not self._custom_on:
            return
        ct = self.__dict__.get("_custom_full")
        if ct is None:
            return
        try:
            vt = self._custom_view(ct)
            if not getattr(self, "_lyrics_mode", False):
                c = vt["components"]
                self._custom_layout(c["panels"], vt["shape"]["margin"], vt["shape"]["spacing"])
                self._custom_elements()
                self._native_apply(vt)
            self._custom_ui_layers(ct["components"].get("ui") == "layers" and not getattr(self, "_lyrics_mode", False))
        except Exception:                                  # noqa: BLE001
            traceback.print_exc()

    def _custom_ui_layers(self, on: bool):
        hidden = self.__dict__.get("_ui_hidden")
        root = self.centralWidget()
        if on and root is not None:
            first = hidden is None
            hidden = hidden if hidden is not None else []
            # и при повторном применении темы: раскладка могла снова показать панели.
            # isHidden, а не isVisible: тема применяется и до показа окна (тогда «видимых» ещё нет)
            for w in root.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
                # вынутые родные элементы (пластинка, кнопки…) остаются: их поставили сами
                if not w.isHidden() and not w.isWindow() and not w.property("echoesEditor") \
                        and not w.property("echoesFree"):
                    w.hide()
                    if w not in hidden:
                        hidden.append(w)
            self._ui_hidden = hidden
            if first and self._crt is not None:
                self._crt.refresh()
            self._place_ui_btn(True)
        elif not on and hidden is not None:
            self._ui_hidden = None
            for w in hidden:
                try:
                    if not w.property("echoesHidden"):
                        w.show()
                except RuntimeError:
                    pass
            if self._crt is not None:
                self._crt.refresh()
            self._place_ui_btn(False)

    # ── родные элементы интерфейса как слои (ui_free) ── #

    def _native_items(self):
        """Все элементы обычного интерфейса, которыми управляет конструктор тем: (ключ, название, группа, виджет)."""
        g = lambda n: getattr(self, n, None)                      # noqa: E731
        C, LP, RP = "Центр", "Левая панель", "Правая панель"
        lv = g("lyrics_view")
        lyr = []
        in_lyr = lv is not None and g("vinyl") is not None and self.vinyl.parentWidget() is lv
        if lv is not None and self._lyrics_custom_on():
            L = "Режим текста"
            lyr = [("lyr_text", "Текст песни", L, lv._text_panel),
                   ("lyr_vinyl", "Пластинка (в режиме текста)", L, self.vinyl),
                   ("lyr_caption", "Подпись: название и прогресс", L, lv._caption),
                   ("lyr_close", "Кнопка «Закрыть»", L, lv._close_btn)]
        main = [
            ("stage", "Центральная область целиком", C, g("_stage")),
            # пластинку на время режима текста забирает его оверлей — ею управляет lyr_vinyl
            ("vinyl", "Пластинка", C, None if in_lyr or lyr else g("vinyl")),
            ("title", "Название трека", C, g("title_lbl")),
            ("artist", "Исполнитель", C, g("artist_lbl")),
            ("viz", "Визуализатор", C, g("viz")),
            ("btn_lyrics", "Кнопка «Текст»", C, g("btn_lyrics_mode")),
            ("btn_queue", "Кнопка «Очередь»", C, g("btn_queue_view")),
            ("transport", "Панель управления целиком", C, g("transport_bar")),
            ("seek", "Перемотка и время", C, g("_seek_row")),
            ("controls", "Ряд кнопок управления", C, g("_controls_widget")),
            ("btn_shuffle", "Кнопка «Перемешать»", C, g("btn_shuffle")),
            ("btn_artist_shuffle", "Кнопка «Шаффл по исполнителю»", C, g("btn_artist_shuffle")),
            ("btn_prev", "Кнопка «Предыдущий»", C, g("btn_prev")),
            ("btn_play", "Кнопка Play / Pause", C, g("btn_play")),
            ("btn_next", "Кнопка «Следующий»", C, g("btn_next")),
            ("btn_repeat", "Кнопка «Повтор»", C, g("btn_repeat")),
            ("btn_cover", "Кнопка «Обложка»", C, g("btn_cover_mode")),
            ("btn_clip", "Кнопка «Клип»", C, g("btn_clip_mode")),
            ("btn_hub", "Кнопка «Музыка»", C, g("btn_hub")),
            ("volume", "Громкость и скорость", C, g("_vol_row")),
            ("left", "Левая панель целиком", LP, g("_left_panel")),
            ("btn_profile", "Кнопка «Профиль»", LP, g("btn_edit")),
            ("lib_search", "Поиск по библиотеке", LP, g("lib_search")),
            ("lib_sort", "Сортировка библиотеки", LP, g("lib_sort")),
            ("lib_list", "Список треков", LP, g("lib_list")),
            ("btn_files", "Кнопка «＋ Файлы»", LP, g("_btn_files")),
            ("btn_folder", "Кнопка «＋ Папка»", LP, g("_btn_folder")),
            ("btn_download", "Кнопка «Скачать»", LP, g("_btn_download")),
            ("playlists", "Плейлисты", LP, g("_pl_section")),
            ("right", "Правая панель целиком", RP, g("_right_panel")),
            ("rp_nav", "Переключатель страниц", RP, g("_rp_nav")),
            ("theme_cb", "Выбор темы", RP, g("theme_cb")),
            ("btn_studio", "Кнопка «Конструктор тем»", RP, g("_studio_btn")),
            ("cover_colors", "«Цвета из обложки»", RP, g("auto_cover_theme_cb")),
            ("lang", "Язык", RP, g("lang_cb")),
            ("lyrics_box", "Текст песни (превью)", RP, g("lyrics_box")),
            ("btn_lyrics_edit", "Кнопка «Записать/изменить»", RP, g("_btn_lyrics_edit")),
            ("btn_lyrics_find", "Кнопка «Найти текст вручную»", RP, g("_btn_lyrics_find")),
        ]
        return lyr + main

    def native_layout(self):
        if self.__dict__.get("_native") is None:
            import ui_free
            self._native = ui_free.NativeLayout(self, self._native_items, self._native_delegate)
            self._native.after_edit = self._lyrics_refade
        return self._native

    def _lyrics_refade(self):
        """Правка раскладки прямо в режиме текста: вынутое поверх текста — видно, возвращённое — гаснет."""
        if not self._lyrics_custom_on():
            return
        lv = self.lyrics_view
        ws = self._lyrics_fade_targets() + lv._decor_widgets() + [self._left_panel, self._right_panel]
        for w in ws:
            try:
                if w is None or w.property("echoesHidden"):
                    continue
                eff = w.graphicsEffect()
                if w.property("echoesFree"):
                    if isinstance(eff, QGraphicsOpacityEffect):
                        w.setGraphicsEffect(None)
                elif not isinstance(eff, QGraphicsOpacityEffect) and w not in lv.__dict__.get("_ghosts", {}):
                    e = QGraphicsOpacityEffect(w)
                    e.setOpacity(0.0)
                    w.setGraphicsEffect(e)
            except RuntimeError:
                pass
        self.native_layout().raise_free()

    def _native_delegate(self, key, spec) -> bool:
        """Элементы режима текста ставит сам оверлей текста (они живут в нём, а не в окне)."""
        if not key.startswith("lyr_"):
            return False
        lv = getattr(self, "lyrics_view", None)
        if lv is not None:
            lv.set_item(key, spec)
        return True

    def _native_apply(self, ct):
        c = ct["components"]
        try:
            self.native_layout().apply(ct.get("native"))
        except Exception:                                 # noqa: BLE001
            traceback.print_exc()
        bg = c["vinyl"].get("bg") or {}
        self.vinyl.set_bg_layout(bg.get("dx", 0.0), bg.get("dy", 0.0), bg.get("scale", 1.0), bg.get("on", True))
        h = int(c["visualizer"].get("height", 0) or 0)
        if not self.native_layout().is_free("viz"):
            if h > 0:
                self.viz.setMinimumHeight(h)
                self.viz.setMaximumHeight(h)
            else:
                self.viz.setMinimumHeight(100)
                self.viz.setMaximumHeight(16777215)

    def _native_reset(self):
        nl = self.__dict__.get("_native")
        if nl is not None:
            nl.reset()
        self.vinyl.set_bg_layout()
        self.viz.setMinimumHeight(100)
        self.viz.setMaximumHeight(16777215)

    def _place_ui_btn(self, show=None):
        """«☰» в режиме «Только слои»: темы, конструктор, обычный интерфейс — пока его не видно."""
        btn = self.__dict__.get("_ui_btn")
        if show is None:                                  # из resizeEvent: только переставить (и до показа окна)
            show = bool(self.__dict__.get("_ui_btn_on"))
        self._ui_btn_on = bool(show)
        if not show:
            if btn is not None:
                btn.hide()
            return
        if btn is None:
            btn = self._ui_btn = QPushButton("☰", self)
            btn.setToolTip("Меню: темы, конструктор тем, обычный интерфейс")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(34, 30)
            btn.setStyleSheet("QPushButton{background:rgba(12,12,18,0.55);color:#f2f2f7;border:1px solid "
                              "rgba(255,255,255,0.14);border-radius:10px;font-size:15px;padding:0;}"
                              "QPushButton:hover{background:rgba(40,40,60,0.85);}")
            btn.clicked.connect(lambda: self._ui_layers_menu(btn.mapToGlobal(btn.rect().bottomLeft())))
        top = self.menuWidget().height() if self.menuWidget() is not None else 0
        a = self._custom_area()
        btn.move(a.left() + 10, max(top, a.top()) + 8)
        btn.show()
        btn.raise_()

    def _ui_layers_menu(self, gpos):
        m = QMenu(self)
        themes = m.addMenu("Темы")
        cur = self.settings.get("theme", "")
        for _title, _hint, names in theme_groups():
            for name in names:
                a = themes.addAction(name)
                a.setCheckable(True)
                a.setChecked(name == cur)
                a.triggered.connect(lambda _=False, n=name: self._request_theme(n))
        m.addAction("Конструктор тем… (Ctrl+Shift+T)", lambda: self._open_theme_studio())
        m.addAction("Показать обычный интерфейс", lambda: self._custom_ui_layers(False))
        m.addSeparator()
        m.addAction("Экспорт трека с эффектами…", lambda: self._export_effects([]))
        m.addAction("Полный экран (F11)", self._toggle_fullscreen)
        m.exec(gpos)

    # ------------------------------------------------------------------ #
    #  Тема «Fluid»                                                        #
    # ------------------------------------------------------------------ #

    def _apply_fluid_mode(self, t, is_fluid):
        """Всё, что нельзя выразить через QSS: включает/выключает режим Fluid."""
        # 1. Inline-стили, зашитые под тёмные темы (белые полупрозрачные
        #    кнопки ‹ ›, подпись страницы, аватар), запоминаем и подменяем.
        widgets = [getattr(self, n, None) for n in ("_rp_prev_btn", "_rp_next_btn", "_rp_page_lbl", "avatar_lbl")]
        widgets = [w for w in widgets if w is not None]
        if not hasattr(self, "_inline_orig"):
            self._inline_orig = {w: w.styleSheet() for w in widgets}
        if is_fluid:
            ink, g2, b2 = t["text"], t["glass2"], t["border2"]
            btn = (f"QPushButton{{background:{g2};border:none;border-radius:14px;color:{ink};"
                   f"font-size:16px;font-weight:600;padding:0;}}"
                   f"QPushButton:hover{{background:{b2};}}")
            for w in widgets:
                if isinstance(w, QPushButton):
                    w.setStyleSheet(btn)
            if hasattr(self, "_rp_page_lbl"):
                self._rp_page_lbl.setStyleSheet(f"color:{t['accent']};font-size:10px;font-weight:700;background:transparent;")
            if hasattr(self, "avatar_lbl"):
                self.avatar_lbl.setStyleSheet(f"border-radius:23px;background:{g2};font-size:18px;")
        else:
            # Обычные темы: цвета кнопок ‹ › / подписи / аватара берём из темы.
            # Раньше тут были зашитые белые полупрозрачные стили — в светлой
            # Snow они становились невидимыми.
            ink, g2, b1, b2, mut = t["text"], t["glass2"], t["border"], t["border2"], t["muted"]
            btn = (f"QPushButton{{background:{g2};border:1px solid {b1};border-radius:10px;color:{ink};"
                   f"font-size:16px;font-weight:600;padding:0;}}"
                   f"QPushButton:hover{{border-color:{b2};}}"
                   f"QPushButton:pressed{{background:{b2};}}")
            for n in ("_rp_prev_btn", "_rp_next_btn"):
                w = getattr(self, n, None)
                if w is not None:
                    w.setStyleSheet(btn)
            if hasattr(self, "_rp_page_lbl"):
                self._rp_page_lbl.setStyleSheet(
                    f"color:{mut};font-size:10px;font-weight:600;letter-spacing:1.4px;background:transparent;")
            if hasattr(self, "avatar_lbl"):
                self.avatar_lbl.setStyleSheet(f"border-radius:23px;background:{g2};font-size:18px;")

        # 2. Размытая обложка-фон (BackgroundAmbience) на бежевом не нужна
        if hasattr(self, "_ambience"):
            self._ambience.set_enabled(bool(self.settings.get("fx_breathe", True)) and not is_fluid)
        # Пыль/зерно — прозрачный слой поверх ВСЕГО окна: каждый его кадр
        # заставляет перерисовываться всё под ним. Плоскому стилю Fluid он не
        # нужен, а FPS съедает заметно — в Fluid выключаем (настройка не меняется).
        if hasattr(self, "_dust"):
            self._dust.set_enabled(bool(self.settings.get("fx_dust", True)) and not is_fluid)

        # 3. Жидкая симуляция: вкл/выкл по тому же флагу, что и «дыхание» фона
        dark = bool(t.get("fluid_dark"))
        if hasattr(self, "_stage"):
            self._stage.set_animated(bool(self.settings.get("fx_breathe", True)))
            self._stage.set_dark(dark)
            self._stage.set_engine(self.engine if is_fluid else None)
            self._stage.set_active(is_fluid)
        if hasattr(self, "vinyl"):
            self.vinyl.set_graphic(is_fluid, dark)
            if getattr(self, "_crate", None) is not None:
                try:
                    self._crate.set_dark(dark)
                except RuntimeError:
                    self._crate = None
        if hasattr(self, "lyrics_view"):
            self.lyrics_view.set_fluid_mode(is_fluid, dark)

        # 4. Транспорт — кремовая «полоса меню» с внутренними отступами
        if hasattr(self, "transport_bar") and self.transport_bar.layout() is not None:
            self.transport_bar.layout().setContentsMargins(*((26, 12, 26, 8) if is_fluid else (0, 0, 0, 0)))

        # 5. Силуэт: колонка с заголовком/меню + высокий постер с жидкостью
        if is_fluid:
            self._enter_fluid_layout()
        else:
            self._leave_fluid_layout()

        # 6. Всё строчными, как на референсе (QSS text-transform не умеет)
        from PyQt6.QtGui import QFont
        cap = QFont.Capitalization.AllLowercase if is_fluid else QFont.Capitalization.MixedCase
        low = list(self.findChildren(QLabel, "Section"))
        low += [getattr(self, n, None) for n in (
            "title_lbl", "artist_lbl", "btn_lyrics_mode", "btn_queue_view",
            "btn_shuffle", "btn_artist_shuffle", "btn_prev", "btn_next", "btn_repeat", "nick_lbl")]
        for w in low:
            if w is None:
                continue
            f = w.font(); f.setCapitalization(cap); w.setFont(f)

        # 7. Цвет прогресс-бара/визуализатора — под доминанту текущей обложки
        if is_fluid and hasattr(self, "_stage"):
            self._on_fluid_palette(self._stage.fluid_palette())
        elif hasattr(self, "seek"):
            self.seek.setStyleSheet("")

    def _enter_fluid_layout(self):
        """
        Перестраивает центр под силуэт главного меню BRC:
            [ заголовок · меню · визуализатор · полоса-транспорт ] [ постер ]
        Виджеты те же самые — просто переезжают в другие layout'ы, поэтому
        все сигналы/ссылки продолжают работать, а _leave_fluid_layout()
        возвращает исходную раскладку один-в-один.
        """
        if getattr(self, "_fluid_layout_on", False) or getattr(self, "_lyrics_mode", False):
            return
        if not hasattr(self, "_nv") or not hasattr(self, "_stage"):
            return
        nv, cv = self._nv, self._cv
        movable = [self.vinyl, self.title_lbl, self.artist_lbl, self.viz,
                   self.btn_lyrics_mode, self.btn_queue_view, self.transport_bar]
        was_hidden = {w: w.isHidden() for w in movable}

        # ── разбираем обычную раскладку ──
        for w in (self.vinyl, self.title_lbl, self.artist_lbl, self.viz):
            nv.removeWidget(w)
        # сам ряд (layout со stretch'ами) остаётся в nv пустым — переезжают кнопки
        self._lyrics_btn_row.removeWidget(self.btn_lyrics_mode)
        self._lyrics_btn_row.removeWidget(self.btn_queue_view)
        cv.removeWidget(self.transport_bar)

        # ── собираем Fluid-раскладку ──
        row = QWidget(); row.setStyleSheet(".QWidget{background:transparent;}")
        hb = QHBoxLayout(row); hb.setContentsMargins(0, 0, 0, 0)
        hb.setSpacing(FluidPanel.STRIPES_GAP)

        info = QWidget(); info.setStyleSheet(".QWidget{background:transparent;}")
        iv = QVBoxLayout(info); iv.setContentsMargins(8, 10, 0, 0); iv.setSpacing(2)
        # «ящик с пластинками»: спереди играющий трек, сзади — очередь
        from cover_crate import CoverCrate
        self._crate = CoverCrate()
        self._crate.setMaximumHeight(380)
        self._crate.set_dark(self._stage.is_dark())
        try:
            from PyQt6.QtGui import QFontInfo
            self._crate.set_font_family(QFontInfo(self.title_lbl.font()).family())
        except Exception:
            pass
        try:
            self._crate.set_dominant(QColor(self._stage.fluid_palette().css("dominant")))
        except Exception:
            pass
        self._crate.play_ahead.connect(self._crate_jump)
        iv.addWidget(self._crate, 3)
        iv.addSpacing(6)
        iv.addWidget(self.title_lbl)
        iv.addWidget(self.artist_lbl)
        iv.addSpacing(22)
        iv.addWidget(self.btn_lyrics_mode, 0, Qt.AlignmentFlag.AlignLeft)
        iv.addWidget(self.btn_queue_view, 0, Qt.AlignmentFlag.AlignLeft)
        iv.addStretch(1)                       # пустая зона — в ней рисуется тег-граффити
        iv.addWidget(self.viz, 0)
        iv.addSpacing(30)                      # место под бледную строку «ТРЕК: 045»
        iv.addWidget(self.transport_bar)

        poster = QWidget(); poster.setStyleSheet(".QWidget{background:transparent;}")
        pv = QVBoxLayout(poster); pv.setContentsMargins(26, 26, 26, 26)
        pv.addWidget(self.vinyl, 1, Qt.AlignmentFlag.AlignCenter)

        hb.addWidget(info, 1)
        hb.addWidget(poster, 0)
        nv.insertWidget(0, row, 1)

        # ── внешний вид виджетов в новой роли ──
        self._fluid_saved = {
            "lyr_text": self.btn_lyrics_mode.text(),
            "queue_text": self.btn_queue_view.text(),
        }
        self.btn_lyrics_mode.setText("текст")
        self.btn_queue_view.setText("очередь")
        for b in (self.btn_lyrics_mode, self.btn_queue_view):
            b.setMinimumWidth(0); b.setMaximumWidth(16777215)
        for lbl in (self.title_lbl, self.artist_lbl):
            lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            lbl.setWordWrap(True)
        self.viz.setFixedHeight(FluidPanel.VIZ_H)
        cv.setContentsMargins(4, 6, 6, 6)

        for w, hid in was_hidden.items():
            w.setHidden(hid)

        self._fluid_row, self._fluid_info, self._fluid_poster = row, info, poster
        self._fluid_layout_on = True
        self._stage.set_hosts(poster, self.transport_bar, self.btn_queue_view)
        self._crate_refresh()
        if not hasattr(self, "_crate_timer"):
            self._crate_timer = QTimer(self)
            self._crate_timer.setInterval(1200)      # очередь могли перемешать/изменить
            self._crate_timer.timeout.connect(self._crate_refresh)
        self._crate_timer.start()

    def _upcoming_tracks(self, n=4):
        """Следующие n треков очереди (без побочных эффектов): (треки, индексы)."""
        tracks = self.library if self.queue_context == "library" else \
            self.playlists.get(self.queue_context, {}).get("tracks", [])
        if not tracks or self.current_index < 0:
            return [], []
        idx = []
        if self.shuffle and len(tracks) > 1 and self._shuffle_queue:
            for k in range(1, n + 1):
                pos = self._shuffle_pos + k
                if pos < len(self._shuffle_queue):
                    idx.append(self._shuffle_queue[pos])
        else:
            cur = self.current_index
            for k in range(1, n + 1):
                i = self._step_index(self.queue_context, cur, 1, len(tracks))
                if i < 0 or (k > 1 and i == self.current_index):
                    break
                idx.append(i)
                cur = i
        idx = [i for i in idx if 0 <= i < len(tracks)]
        return [tracks[i] for i in idx], idx

    def _crate_refresh(self, current=None):
        crate = getattr(self, "_crate", None)
        if crate is None:
            return
        try:
            tracks = self.library if self.queue_context == "library" else \
                self.playlists.get(self.queue_context, {}).get("tracks", [])
            if current is None and 0 <= self.current_index < len(tracks):
                current = tracks[self.current_index]
            up, idx = self._upcoming_tracks(4)
            self._crate_idx = idx
            crate.set_tracks(current, up)
        except RuntimeError:
            self._crate = None                         # виджет уже удалён
        except Exception as e:
            print("[crate]", e)

    def _crate_jump(self, k):
        """Клик по k-й обложке очереди в «ящике»."""
        idx = getattr(self, "_crate_idx", [])
        if not 1 <= k <= len(idx):
            return
        if self.shuffle and self._shuffle_queue:
            self._shuffle_pos = min(len(self._shuffle_queue) - 1, self._shuffle_pos + k)
        self._play_index(idx[k - 1], self.queue_context, rebuild_shuffle=False)

    def _leave_fluid_layout(self):
        """Возвращает обычную раскладку ровно в исходном порядке."""
        if not getattr(self, "_fluid_layout_on", False) or getattr(self, "_lyrics_mode", False):
            return
        nv, cv = self._nv, self._cv
        movable = [self.vinyl, self.title_lbl, self.artist_lbl, self.viz,
                   self.btn_lyrics_mode, self.btn_queue_view, self.transport_bar]
        was_hidden = {w: w.isHidden() for w in movable}
        self._stage.set_hosts(None, None)

        if hasattr(self, "_crate_timer"):
            self._crate_timer.stop()
        self._crate = None                             # удалится вместе с row
        row = self._fluid_row
        nv.removeWidget(row)
        # исходный порядок: vinyl(7,center) · title · artist · viz(2) · ряд кнопок
        nv.insertWidget(0, self.vinyl, 7, Qt.AlignmentFlag.AlignCenter)
        nv.insertWidget(1, self.title_lbl)
        nv.insertWidget(2, self.artist_lbl)
        nv.insertWidget(3, self.viz, 2)
        self._lyrics_btn_row.insertWidget(1, self.btn_lyrics_mode)
        self._lyrics_btn_row.insertWidget(2, self.btn_queue_view)
        cv.insertWidget(cv.indexOf(self._normal_widget) + 1, self.transport_bar)
        row.hide(); row.deleteLater()

        saved = getattr(self, "_fluid_saved", {})
        self.btn_lyrics_mode.setText(saved.get("lyr_text", "Текст"))
        self.btn_queue_view.setText(saved.get("queue_text", "Очередь"))
        self.btn_lyrics_mode.setFixedWidth(88)
        self.btn_queue_view.setFixedWidth(96)
        for lbl in (self.title_lbl, self.artist_lbl):
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(False)
        self.viz.setMinimumHeight(160 if isinstance(self.viz, MilkdropVisualizer) else 100)
        self.viz.setMaximumHeight(16777215)
        cv.setContentsMargins(24, 20, 24, 20)

        for w, hid in was_hidden.items():
            w.setHidden(hid)
        self.title_lbl.raise_(); self.artist_lbl.raise_(); self.btn_lyrics_mode.raise_()
        self._fluid_layout_on = False
        self._fluid_row = self._fluid_info = self._fluid_poster = None

    # ------------------------------------------------------------------ #
    #  Тема «Winamp»                                                       #
    # ------------------------------------------------------------------ #

    def _apply_winamp_mode(self, t, on):
        if on:
            self._enter_winamp_layout()
            self._winamp_styles()
        else:
            self._leave_winamp_layout()

    def _winamp_styles(self):
        """То, что не выражается общим QSS (инлайн-стили, слои, иконки).
        Вызывается при КАЖДОМ применении темы — _apply_fluid_mode(False)
        перед этим возвращает исходные инлайн-стили."""
        bevel = ("QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #e6e6ee,stop:1 #8a8aa0);"
                 "color:#10101a;border-top:1px solid #fff;border-left:1px solid #fff;"
                 "border-bottom:1px solid #2a2a36;border-right:1px solid #2a2a36;border-radius:0;"
                 "font-size:13px;font-weight:bold;padding:0;}"
                 "QPushButton:pressed{background:#8a8aa0;}")
        for n in ("_rp_prev_btn", "_rp_next_btn"):
            w = getattr(self, n, None)
            if w is not None:
                w.setStyleSheet(bevel)
        if hasattr(self, "_rp_page_lbl"):
            self._rp_page_lbl.setStyleSheet("color:#00e000;font-size:10px;font-weight:bold;background:transparent;")
        if hasattr(self, "avatar_lbl"):
            self.avatar_lbl.setStyleSheet("border-radius:0;background:#000;border:1px solid #5e5e7a;font-size:18px;")
        if hasattr(self, "_ambience"):
            self._ambience.set_enabled(False)          # плоский «рабочий стол»
        if hasattr(self, "_dust"):
            self._dust.set_enabled(False)
        if hasattr(self, "btn_play"):
            self.btn_play.set_icon_color(QColor("#10101a"))
        if hasattr(self, "lyrics_view") and hasattr(self.lyrics_view, "set_solid_mode"):
            self.lyrics_view.set_solid_mode("#05050a")

    def _wa_toggle_lyrics(self):
        """Текст в теме Winamp: зелёный ЖК-экран поверх MilkDrop (левые окна
        с транспортом остаются доступными)."""
        wa = getattr(self, "_wa", None)
        if not wa:
            return
        from winamp_theme import WinampLyrics
        panel = wa.get("lyrics")
        if panel is None:
            panel = WinampLyrics(self.lyrics_view, self.engine,
                                 title_fn=lambda: (self.artist_lbl.text().split("  ·  ")[0],
                                                   self.title_lbl.text()),
                                 parent=wa["milk"])
            wa["milk"].set_overlay(panel)
            wa["lyrics"] = panel
        self._wa_lyrics = not getattr(self, "_wa_lyrics", False)
        self.btn_lyrics_mode.setChecked(self._wa_lyrics)
        panel.set_open(self._wa_lyrics)

    def _winamp_theme_menu(self, global_pos):
        """Меню тем (кнопка «ТЕМЫ» или левая мини-кнопка в заголовке WINAMP)."""
        menu = QMenu(self)
        cur = self.settings.get("theme", "")
        for title, hint, names in theme_groups():
            if not names:
                continue
            menu.addSection(title)
            for name in names:
                act = menu.addAction(name)
                act.setCheckable(True)
                act.setChecked(name == cur)
                act.setToolTip(hint)
                act.triggered.connect(lambda _=False, n=name: self._request_theme(n))
        menu.exec(global_pos)

    def _winamp_main_menu(self, global_pos):
        """Кнопка «МЕНЮ» окна WINAMP: всё, что раньше занимало место кнопками."""
        menu = QMenu(self)
        themes = menu.addMenu("Темы")
        cur = self.settings.get("theme", "")
        for _title, _hint, names in theme_groups():
            for name in names:
                a = themes.addAction(name)
                a.setCheckable(True)
                a.setChecked(name == cur)
                a.triggered.connect(lambda _=False, n=name: self._request_theme(n))
        menu.addAction("Конструктор тем…", lambda: self._open_theme_studio())
        menu.addAction("Экстремальная громкость…", lambda: self._boost_menu(global_pos))
        menu.addSeparator()
        menu.addAction("Режим обложки", self._toggle_cover_mode)
        menu.addAction("Клип песни (Ctrl+Shift+K)", self._toggle_clip_mode)
        menu.addAction("Полный экран (F11)", self._toggle_fullscreen)
        menu.addAction("Музыка: поиск и скачивание (Ctrl+M)", self._open_hub)
        menu.addSeparator()
        menu.addAction("Профиль и статистика", self._open_profile)
        menu.exec(global_pos)

    def _wa_refresh_playlist(self, sources=True):
        wa = getattr(self, "_wa", None)
        if not getattr(self, "_wa_on", False) or not wa or "plw" not in wa:
            return
        try:
            wa["plw"].refresh_sources() if sources else wa["plw"].mark_current()
        except RuntimeError:
            pass

    def _winamp_update_display(self, t):
        wa = getattr(self, "_wa", None)
        if not wa:
            return
        title = sanitize_title(t.get("title", "Untitled"))
        artist = t.get("artist") or "Unknown artist"
        dur = float(t.get("duration", 0) or 0)
        idx = self.current_index + 1 if self.current_index >= 0 else 1
        marquee = f"{idx}. {artist} - {title} ({int(dur) // 60}:{int(dur) % 60:02d})"
        kbps, khz, ch = self._audio_info(t.get("path", ""))
        wa["disp"].set_track(marquee, kbps, khz, ch)
        self._wa_refresh_playlist(sources=False)

    def _audio_info(self, path):
        """kbps / kHz / каналы для ЖК Winamp (mutagen, кэш на путь)."""
        cache = self.__dict__.setdefault("_audio_info_cache", {})
        if path in cache:
            return cache[path]
        info = ("", "", 2)
        try:
            if MutaFile is not None and path:
                m = MutaFile(path)
                if m is not None and getattr(m, "info", None) is not None:
                    br = int(getattr(m.info, "bitrate", 0) or 0)
                    sr = int(getattr(m.info, "sample_rate", 0) or 0)
                    chn = int(getattr(m.info, "channels", 2) or 2)
                    info = (str(round(br / 1000)) if br else "",
                            str(round(sr / 1000)) if sr else "", chn)
        except Exception:
            pass
        cache[path] = info
        return info

    def _enter_winamp_layout(self):
        """
        Силуэт Winamp 2 + MilkDrop:
          слева — пристыкованные окна WINAMP (ЖК + транспорт),
                  WINAMP EQUALIZER (правая панель, страница EQ),
                  WINAMP PLAYLIST (левая панель с библиотекой);
          справа — большое окно MILKDROP (визуализация от звука).
        Виджеты те же — только переезжают; _leave_winamp_layout() всё возвращает.
        """
        if getattr(self, "_wa_on", False) or getattr(self, "_lyrics_mode", False):
            return
        from winamp_theme import (WinampFrame, WinampDisplay, MilkdropWidget, MilkToolbar,
                                  WinampPlaylist, WinampEqualizer)
        root = self.centralWidget()
        outer, nv, cv = self._outer, self._nv, self._cv
        left, right, center = self._left_panel, self._right_panel, self._stage
        movable = [self.vinyl, self.title_lbl, self.artist_lbl, self.viz,
                   self.btn_lyrics_mode, self.btn_queue_view, self.transport_bar,
                   left, right, center]
        was_hidden = {w: w.isHidden() for w in movable}

        self._wa_saved = {
            "left_w": (left.minimumWidth(), left.maximumWidth()),
            "right_w": (right.minimumWidth(), right.maximumWidth()),
            "lib_icon": self.lib_list.iconSize(),
            "pl_icon": self.pl_list.iconSize(),
            "prev": self.btn_prev.text(), "next": self.btn_next.text(),
            "lyr": self.btn_lyrics_mode.text(), "queue": self.btn_queue_view.text(),
            "rp_index": self._rp_stack.currentIndex(),
            "rp_label": self._rp_page_lbl.text(),
            "cv_margins": cv.contentsMargins(),
            "outer_spacing": outer.spacing(),
        }

        # ── снимаем три колонки с корневого layout ──
        for w in (left, center, right):
            outer.removeWidget(w)

        # ── «склад» для того, что Winamp не показывает (диск, заголовки, бары) ──
        stash = QWidget(root); stash.hide()
        sl = QVBoxLayout(stash)
        for w in (self.vinyl, self.title_lbl, self.artist_lbl, self.viz):
            nv.removeWidget(w)
        sl.addWidget(self.vinyl, 1, Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(self.title_lbl)
        sl.addWidget(self.artist_lbl)
        sl.addWidget(self.viz)
        sl.addWidget(left)                      # старая левая панель (профиль, подсказки) — не нужна
        self.viz.timer.stop()                   # спрятанный визуализатор не тратит CPU
        self._lyrics_btn_row.removeWidget(self.btn_lyrics_mode)
        self._lyrics_btn_row.removeWidget(self.btn_queue_view)
        cv.removeWidget(self.transport_bar)

        # ── окно WINAMP: ЖК + транспорт + кнопки-переключатели ──
        f_main = WinampFrame("Echoes")
        disp = WinampDisplay(); disp.set_engine(self.engine)
        f_main.body().addWidget(disp)
        f_main.body().addWidget(self.transport_bar)
        tog = QHBoxLayout(); tog.setSpacing(3)
        menu_btn = QPushButton("МЕНЮ")
        menu_btn.setToolTip("Темы, громкость, режим обложки, музыка из интернета, полный экран")
        menu_btn.clicked.connect(lambda: self._winamp_main_menu(menu_btn.mapToGlobal(menu_btn.rect().bottomLeft())))
        tog.addWidget(menu_btn)
        tog.addStretch(1)
        tog.addWidget(self.btn_lyrics_mode)
        tog.addWidget(self.btn_queue_view)
        f_main.body().addLayout(tog)

        f_main.menu_clicked.connect(self._winamp_theme_menu)
        f_eq = WinampFrame("Echoes Equalizer"); f_eq.setObjectName("WaEqFrame")
        f_eq.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)   # не тянуть: место — плейлисту
        eqw = WinampEqualizer(self, right)
        f_eq.body().addWidget(eqw)
        f_pl = WinampFrame("Echoes Playlist")
        plw = WinampPlaylist(self)
        f_pl.body().addWidget(plw)

        col = QWidget(); col.setStyleSheet(".QWidget{background:transparent;}")
        vl = QVBoxLayout(col); vl.setContentsMargins(0, 0, 0, 0); vl.setSpacing(0)
        vl.addWidget(f_main, 0)
        vl.addWidget(f_eq, 0)
        vl.addWidget(f_pl, 1)
        col.setFixedWidth(392)

        # ── окно MILKDROP: центральная сцена + визуализатор вместо диска ──
        f_md = WinampFrame("MilkDrop")
        f_md.body().setContentsMargins(7, WinampFrame.TITLE_H + 5, 7, 7)
        f_md.body().addWidget(center)
        milk = MilkdropWidget(); milk.set_engine(self.engine)
        nv.insertWidget(0, milk, 1)
        milk_bar = MilkToolbar(milk)
        nv.insertWidget(1, milk_bar, 0)
        milk.set_lyrics_source(self.lyrics_view, self._current_track_mood)
        mode = self.settings.get("milk_mode", "auto")
        milk_bar.set_mode(mode)
        if mode == "lock" and self.settings.get("milk_preset"):
            milk.goto_preset(self.settings["milk_preset"])
        milk.set_words_config(self.settings.get("milk_words_cfg", {}))
        milk_bar.set_words(bool(self.settings.get("milk_words", False)))
        milk_bar.settings_requested.connect(self._open_milk_words_settings)

        def _save_milk(**kw):
            self.settings.update(kw)
            save_json(SETTINGS_FILE, self.settings)
        milk_bar.mode_changed.connect(lambda m: _save_milk(milk_mode=m, milk_preset=milk.preset_name()))
        milk_bar.words_toggled.connect(lambda on: _save_milk(milk_words=bool(on)))
        milk.preset_changed.connect(
            lambda name: _save_milk(milk_preset=name) if milk.mode() == "lock" else None)
        milk_bar.fullscreen_toggled.connect(self._wa_milk_fullscreen)
        milk.fullscreen_requested.connect(
            lambda: self._wa_milk_fullscreen(not getattr(self, "_wa_milk_full", False)))
        esc = QShortcut(QKeySequence("Esc"), self)
        esc.setEnabled(False)                 # включается только во «всё окно»
        esc.activated.connect(lambda: self._wa_milk_fullscreen(False))
        cv.setContentsMargins(0, 0, 0, 0)

        outer.addWidget(col, 0)
        outer.addWidget(f_md, 1)
        outer.setSpacing(8)

        # ── виджеты в новых ролях ──
        for pnl in (left, right):
            pnl.setMinimumWidth(0); pnl.setMaximumWidth(16777215)
        self.lib_list.setIconSize(QSize(0, 0))
        self.pl_list.setIconSize(QSize(0, 0))
        self.btn_lyrics_mode.setText("ТЕКСТ"); self.btn_queue_view.setText("ОЧЕРЕДЬ")
        # транспорт как у Winamp: короткие подписи, без лишних кнопок (они — в «МЕНЮ»)
        self._wa_saved["shuf"] = self.btn_shuffle.text()
        self.btn_shuffle.setText("SHUF"); self.btn_prev.setText("◀◀"); self.btn_next.setText("▶▶")
        self.btn_artist_shuffle.setText("ART")
        self._wa_repeat_text()
        self.btn_cover_mode.hide(); self.btn_hub.hide(); self.btn_clip_mode.hide()
        for b in (self.btn_lyrics_mode, self.btn_queue_view):
            b.setMinimumWidth(0); b.setMaximumWidth(16777215)
        for lbl in (self.t_cur, self.t_tot):
            lbl.hide()                          # время показывает ЖК
        self._rp_stack.setCurrentIndex(1)       # окно EQUALIZER открывается на эквалайзере
        self._rp_page_lbl.setText("Воспроизведение")

        for w, hid in was_hidden.items():
            w.setHidden(hid)
        eqw.stack.setCurrentIndex(0)            # видимость выше «включила» спрятанную вкладку настроек
        right.hide()
        self._wa = {"col": col, "main": f_main, "eq": f_eq, "pl": f_pl, "md": f_md, "plw": plw, "eqw": eqw,
                    "disp": disp, "milk": milk, "stash": stash, "milk_bar": milk_bar, "esc": esc}
        self._wa_milk_full = False
        self._wa_on = True
        if 0 <= self.current_index:
            tracks = self.library if self.queue_context == "library" else \
                self.playlists.get(self.queue_context, {}).get("tracks", [])
            if 0 <= self.current_index < len(tracks):
                self._winamp_update_display(tracks[self.current_index])

    def _leave_winamp_layout(self):
        if not getattr(self, "_wa_on", False) or getattr(self, "_lyrics_mode", False):
            return
        wa, sv = self._wa, self._wa_saved
        outer, nv, cv = self._outer, self._nv, self._cv
        left, right, center = self._left_panel, self._right_panel, self._stage
        movable = [self.vinyl, self.title_lbl, self.artist_lbl, self.viz,
                   self.btn_lyrics_mode, self.btn_queue_view, self.transport_bar,
                   left, right, center]
        was_hidden = {w: w.isHidden() for w in movable}

        # флаг снимаем СРАЗУ: даже если ниже что-то упадёт, повторный выход
        # не полезет к уже удалённым виджетам
        self._wa_on = False
        try:
            if getattr(self, "_wa_milk_full", False):
                wa["col"].show()
            self._wa_milk_full = False
            wa["esc"].setEnabled(False); wa["esc"].deleteLater()
            nv.removeWidget(wa["milk_bar"])
            wa["milk_bar"].hide(); wa["milk_bar"].deleteLater()
        except (RuntimeError, KeyError):
            pass
        milk = wa["milk"]
        try:
            milk.shutdown()
            nv.removeWidget(milk)
            milk.hide(); milk.deleteLater()
        except RuntimeError:
            pass                                # C++-объект уже удалён

        outer.removeWidget(wa["col"])
        outer.removeWidget(wa["md"])
        outer.addWidget(left, 2)
        outer.addWidget(center, 5)
        outer.addWidget(right, 2)
        outer.setSpacing(sv["outer_spacing"])

        nv.insertWidget(0, self.vinyl, 7, Qt.AlignmentFlag.AlignCenter)
        nv.insertWidget(1, self.title_lbl)
        nv.insertWidget(2, self.artist_lbl)
        nv.insertWidget(3, self.viz, 2)
        self.viz.timer.start(16)
        self._lyrics_btn_row.insertWidget(1, self.btn_lyrics_mode)
        self._lyrics_btn_row.insertWidget(2, self.btn_queue_view)
        cv.insertWidget(cv.indexOf(self._normal_widget) + 1, self.transport_bar)
        cv.setContentsMargins(sv["cv_margins"])

        left.setMinimumWidth(sv["left_w"][0]); left.setMaximumWidth(sv["left_w"][1])
        right.setMinimumWidth(sv["right_w"][0]); right.setMaximumWidth(sv["right_w"][1])
        self.lib_list.setIconSize(sv["lib_icon"])
        self.pl_list.setIconSize(sv["pl_icon"])
        self.btn_prev.setText(sv["prev"]); self.btn_next.setText(sv["next"])
        self.btn_lyrics_mode.setText(sv["lyr"]); self.btn_queue_view.setText(sv["queue"])
        self.btn_lyrics_mode.setFixedWidth(88)
        self.btn_queue_view.setFixedWidth(96)
        for lbl in (self.t_cur, self.t_tot):
            lbl.show()
        self._rp_stack.setCurrentIndex(sv["rp_index"])
        self._rp_page_lbl.setText(sv["rp_label"])

        for w, hid in was_hidden.items():
            w.setHidden(hid)
        left.show(); right.show()               # в Winamp они жили на «складе» / во вкладке настроек
        self.btn_shuffle.setText(sv.get("shuf", "Shuffle"))
        self.btn_artist_shuffle.setText("Артист")
        self._cycle_repeat_labels()
        self.btn_cover_mode.show(); self.btn_hub.show(); self.btn_clip_mode.show()
        for k in ("col", "md", "stash"):
            try:
                wa[k].hide(); wa[k].deleteLater()
            except RuntimeError:
                pass
        if hasattr(self, "lyrics_view") and hasattr(self.lyrics_view, "set_solid_mode"):
            self.lyrics_view.set_solid_mode(None)
        self.title_lbl.raise_(); self.artist_lbl.raise_(); self.btn_lyrics_mode.raise_()
        self._wa = None
        self._wa_on = False
        self._wa_lyrics = False
        self.btn_lyrics_mode.setChecked(False)

    def _open_milk_words_settings(self):
        """Окно настроек слов в MilkDrop: изменения применяются сразу."""
        from milk_words import WordsSettingsDialog
        dlg = getattr(self, "_milk_words_dlg", None)
        if dlg is not None:
            try:
                dlg.show(); dlg.raise_(); dlg.activateWindow()
                return
            except RuntimeError:
                pass
        dlg = WordsSettingsDialog(self.settings.get("milk_words_cfg", {}), self)

        def apply(cfg):
            self.settings["milk_words_cfg"] = cfg
            wa = getattr(self, "_wa", None)
            if wa and getattr(self, "_wa_on", False):
                try:
                    wa["milk"].set_words_config(cfg)
                    if not wa["milk"].words_on():          # настроили — значит, хотят видеть
                        wa["milk_bar"].set_words(True)
                except RuntimeError:
                    pass
        dlg.changed.connect(apply)
        dlg.finished.connect(lambda _r: save_json(SETTINGS_FILE, self.settings))
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dlg.destroyed.connect(lambda *_: setattr(self, "_milk_words_dlg", None))
        self._milk_words_dlg = dlg
        inapp.present(self, dlg, "Слова в MilkDrop")

    def _wa_milk_fullscreen(self, on: bool):
        """MilkDrop на всё окно плеера: прячем колонку окон Winamp слева."""
        wa = getattr(self, "_wa", None)
        if not getattr(self, "_wa_on", False) or not wa:
            return
        on = bool(on)
        if on == getattr(self, "_wa_milk_full", False):
            return
        self._wa_milk_full = on
        try:
            wa["col"].setVisible(not on)
            self._outer.setSpacing(0 if on else 8)
            wa["milk_bar"].set_fullscreen(on)
            wa["esc"].setEnabled(on)
            wa["md"].set_title("MilkDrop  ·  Esc — выход" if on else "MilkDrop") \
                if hasattr(wa["md"], "set_title") else None
        except RuntimeError:
            pass

    def _build_profiles_async(self, cb=None):
        """Профили настроения всей библиотеки (music_intel) — считаются в фоне
        один раз; cb(profiles) вызывается в GUI-потоке."""
        if cb is not None:
            self.__dict__.setdefault("_prof_cbs", []).append(cb)
        if getattr(self, "_intel_prof_busy", False) or self._intel_store() is None:
            return
        self._intel_prof_busy = True
        lib, store = list(self.library), self._intel
        import threading
        def work():
            try:
                pr = music_intel.build_profiles(lib, store)
            except Exception as e:
                print("[intel] profiles:", e); pr = {}
            def done():
                self._intel_profiles = pr
                self._intel_prof_busy = False
                cbs, self._prof_cbs = getattr(self, "_prof_cbs", []), []
                for f in cbs:
                    try:
                        f(pr)
                    except Exception as e:
                        print("[intel] cb:", e)
            self._ui_bridge.call.emit(done)
        threading.Thread(target=work, daemon=True).start()

    def _ya_profiles(self, cb):
        """Для темы Echoes Music: профили сразу (если готовы) или None + cb позже."""
        if music_intel is None:
            return {}
        prof = getattr(self, "_intel_profiles", None)
        if prof is not None:
            return prof
        self._build_profiles_async(cb)
        return None

    def _ya_save_playlists(self):
        save_json(PL_FILE, self.playlists)
        self._refresh_playlists()

    def _current_track_mood(self):
        """Профиль настроения текущего трека (music_intel) для шрифтов слов в MilkDrop.
        Профили библиотеки считаются один раз в фоне; до этого — None."""
        if music_intel is None:
            return None
        path = ""
        try:
            tracks = self.library if self.queue_context == "library" else \
                self.playlists.get(self.queue_context, {}).get("tracks", [])
            if 0 <= self.current_index < len(tracks):
                path = str(tracks[self.current_index].get("path", ""))   # не файл пресета
        except Exception:
            path = str(getattr(self.engine, "current_path", "") or "")
        prof = getattr(self, "_intel_profiles", None)
        if prof is None:
            self._build_profiles_async()
            return None
        return prof.get(path)

    # ------------------------------------------------------------------ #
    #  Тема «Echoes Music» (в духе Яндекс Музыки)                          #
    # ------------------------------------------------------------------ #

    def _open_hub(self, page=None):
        """Окно «Музыка» (Echoes Music) поверх любой темы."""
        if getattr(self, "_ya_on", False):
            if page and getattr(self, "_ya", None) is not None:
                self._ya.show_page(page)
            return                                   # тема и так Echoes Music
        hub = getattr(self, "_hub", None)
        if hub is None:
            from echoes_hub import EchoesHub
            hub = EchoesHub(self)
            self._hub = hub
        if page:
            hub.open_page(page)
        hub.show()
        hub.raise_()
        hub.activateWindow()

    def _close_hub(self):
        hub = getattr(self, "_hub", None)
        if hub is not None:
            try:
                hub.close()
            except RuntimeError:
                pass
            self._hub = None

    def _enter_ya_layout(self):
        if getattr(self, "_ya_on", False):
            return
        self._close_hub()                            # тема сама станет Echoes Music
        from yamusic_theme import YaShell
        outer = self._outer
        left, center, right = self._left_panel, self._stage, self._right_panel
        self._ya_saved = {
            "right_w": (right.minimumWidth(), right.maximumWidth()),
            "margins": outer.contentsMargins(),
            "spacing": outer.spacing(),
        }
        for w in (left, center, right):
            outer.removeWidget(w)
        left.hide()
        center.hide()
        try:
            self.viz.timer.stop()               # спрятанный визуализатор не тратит CPU
        except Exception:
            pass
        shell = YaShell(self, self.centralWidget())
        right.setMinimumWidth(0)
        right.setMaximumWidth(16777215)
        shell.adopt_settings(right)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(shell, 1)
        shell.show()
        self._ya = shell
        self._ya_on = True

    def _leave_ya_layout(self):
        if not getattr(self, "_ya_on", False):
            return
        self._ya_on = False
        shell, sv, outer = self._ya, self._ya_saved, self._outer
        left, center = self._left_panel, self._stage
        right = shell.release_settings() or self._right_panel
        try:
            shell.shutdown()
            outer.removeWidget(shell)
        except RuntimeError:
            pass
        # сначала забираем панели обратно в корень, и только потом удаляем оболочку
        outer.addWidget(left, 2)
        outer.addWidget(center, 5)
        outer.addWidget(right, 2)
        right.setMinimumWidth(sv["right_w"][0])
        right.setMaximumWidth(sv["right_w"][1])
        outer.setContentsMargins(sv["margins"])
        outer.setSpacing(sv["spacing"])
        for w in (left, center, right):
            w.show()
        try:
            shell.hide()
            shell.deleteLater()
        except RuntimeError:
            pass
        self._ya = None
        try:
            self.viz.timer.start(16)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  Тема «Echoes Studio»: студия — биты, сведение, запись, мэшап-бот     #
    # ------------------------------------------------------------------ #

    def _enter_montage_layout(self):
        if getattr(self, "_montage", None) is not None:
            return
        self._close_hub()
        from montage_theme import MontageShell
        outer = self._outer
        self._montage_saved = (outer.contentsMargins(), outer.spacing())
        for widget in (self._left_panel, self._stage, self._right_panel):
            outer.removeWidget(widget)
            widget.hide()
        self.engine.stop()
        self.viz.timer.stop()
        for name in ("_ambience", "_dust"):
            obj = getattr(self, name, None)
            if obj is not None:
                obj.set_enabled(False)
        shell = MontageShell(self, self.centralWidget())
        self._montage = shell
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(shell, 1)
        shell.show()

    def _leave_montage_layout(self):
        shell = getattr(self, "_montage", None)
        if shell is None:
            return
        shell.shutdown()
        self._outer.removeWidget(shell)
        self._montage = None
        shell.hide()
        shell.deleteLater()
        for widget, stretch in ((self._left_panel, 2), (self._stage, 5), (self._right_panel, 2)):
            self._outer.addWidget(widget, stretch)
            widget.show()
        margins, spacing = self._montage_saved
        self._outer.setContentsMargins(margins)
        self._outer.setSpacing(spacing)
        self.viz.timer.start(16)

    def _enter_daw_layout(self):
        if getattr(self, "_daw_on", False):
            return
        self._close_hub()
        from daw_theme import StudioShell
        outer = self._outer
        left, center, right = self._left_panel, self._stage, self._right_panel
        self._daw_saved = {
            "right_w": (right.minimumWidth(), right.maximumWidth()),
            "margins": outer.contentsMargins(),
            "spacing": outer.spacing(),
        }
        for w in (left, center, right):
            outer.removeWidget(w)
            w.hide()
        try:
            self.viz.timer.stop()
        except Exception:
            pass
        shell = StudioShell(self, self.centralWidget())
        right.setMinimumWidth(0)
        right.setMaximumWidth(16777215)
        shell.adopt_settings(right)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(shell, 1)
        shell.show()
        self._daw = shell
        self._daw_on = True

    def _leave_daw_layout(self):
        if not getattr(self, "_daw_on", False):
            return
        self._daw_on = False
        shell, sv, outer = self._daw, self._daw_saved, self._outer
        left, center = self._left_panel, self._stage
        right = shell.release_settings() or self._right_panel
        try:
            shell.shutdown()
            outer.removeWidget(shell)
        except RuntimeError:
            pass
        outer.addWidget(left, 2)
        outer.addWidget(center, 5)
        outer.addWidget(right, 2)
        right.setMinimumWidth(sv["right_w"][0])
        right.setMaximumWidth(sv["right_w"][1])
        outer.setContentsMargins(sv["margins"])
        outer.setSpacing(sv["spacing"])
        for w in (left, center, right):
            w.show()
        try:
            shell.hide()
            shell.deleteLater()
        except RuntimeError:
            pass
        self._daw = None
        try:
            self.viz.timer.start(16)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  Режим «Обложка» (во всех темах)                                     #
    # ------------------------------------------------------------------ #

    def _cover_state(self):
        t = None
        tracks = self.library if self.queue_context == "library" else \
            self.playlists.get(self.queue_context, {}).get("tracks", [])
        if 0 <= self.current_index < len(tracks):
            t = tracks[self.current_index]
        try:
            pos = float(self.engine.get_position() or 0)
            dur = float(self.engine.duration or 0)
            playing = bool(self.engine.is_playing())
        except Exception:
            pos = dur = 0.0
            playing = False
        cover = (t or {}).get("cover", "") or ""
        return {"cover": cover if cover and Path(cover).exists() else "",
                "title": sanitize_title((t or {}).get("title", "")), "artist": (t or {}).get("artist", ""),
                "pos": pos, "dur": dur, "playing": playing}

    def _toggle_fullscreen(self):
        """F11 — плеер на весь экран и обратно (в любой теме)."""
        import ui_anim
        if self.isFullScreen():
            ui_anim.animate_state(self, "max" if getattr(self, "_was_maximized", False) else "normal")
        else:
            self._was_maximized = self.isMaximized()
            ui_anim.animate_state(self, "full")

    def _toggle_now_playing(self):
        """Ctrl+Shift+N — экран «Сейчас играет» (оболочка Echoes Music); в других темах — режим обложки."""
        ya = getattr(self, "_ya", None)
        if ya is not None and ya.isVisible() and hasattr(ya, "toggle_now_playing"):
            ya.toggle_now_playing()
        else:
            self._toggle_cover_mode()

    def _toggle_cover_mode(self):
        from cover_mode import CoverMode
        cm = getattr(self, "_cover_mode", None)
        if cm is None:
            cm = CoverMode(self.centralWidget(), self._cover_state, self.prev_track, self.toggle_play,
                           self.next_track, lambda sec: self.engine.seek(sec))
            self._cover_mode = cm
        if cm.isVisible() and cm._op > 0.5:
            cm.close_mode()
        else:
            cm.winamp = bool(getattr(self, "_wa_on", False))     # в теме Winamp — окно в стиле Winamp
            cm.open()

    # ------------------------------------------------------------------ #
    #  Режим «Клип» (во всех темах)                                        #
    # ------------------------------------------------------------------ #

    def _toggle_clip_mode(self):
        try:
            import clip_mode
            clip_mode.toggle(self)
        except Exception as e:                            # noqa: BLE001
            traceback.print_exc()
            QMessageBox.warning(self, "Клип", f"Не удалось открыть режим клипа:\n{e}")

    def open_clip_mode(self, on=True):
        """Конструктор: показать (или закрыть) режим клипа, чтобы видеть его оформление."""
        import clip_mode
        cm = clip_mode.mode(self, create=on)
        if cm is None:
            return
        if on and not cm.is_open():
            cm.open()
        elif not on and cm.is_open():
            cm.close_mode()
            QTimer.singleShot(0, self._custom_ui_restore)

    def _clip_restyle(self, theme_data):
        """Тема сменилась (или её правят в конструкторе) — режим клипа в её стиле."""
        self._clip_theme_data = theme_data
        cm = self.__dict__.get("_clip_mode")
        if cm is not None:
            try:
                cm.apply_theme(theme_data)
            except RuntimeError:
                self._clip_mode = None

    def _clip_track_changed(self):
        """Новый трек: открытый режим клипа переключается на его клип; с «качать сами» — скачать в фоне."""
        cm = self.__dict__.get("_clip_mode")
        try:
            if cm is not None and cm.is_open():
                cm.track_changed()                       # сам начнёт скачивание, если включено
                return
        except RuntimeError:
            self._clip_mode = None
        if not self.settings.get("clips_auto", False):
            return
        t = self._current_track()
        if t and (t.get("title") or "").strip():
            try:
                import clip_mode
                clip_mode.service(self).start(t)
            except Exception as e:                        # noqa: BLE001
                print("[clip]", e)

    def _on_clips_stream(self, on):
        self.settings["clips_stream"] = bool(on)
        save_json(SETTINGS_FILE, self.settings)

    def _on_clips_auto(self, on):
        self.settings["clips_auto"] = bool(on)
        save_json(SETTINGS_FILE, self.settings)
        if on:
            self._clip_track_changed()

    def _on_clips_quality(self, _i=0):
        self.settings["clips_quality"] = int(self.clips_q_cb.currentData())
        save_json(SETTINGS_FILE, self.settings)

    def _on_fluid_palette(self, pal):
        """Доминирующий цвет обложки сменился (сигнал FluidPanel.palette_changed)."""
        if not getattr(self, "_stage", None) or not self._stage.active:
            return
        dom = pal.css("dominant")
        if hasattr(self, "seek"):
            # inline-правило объединяется с общим QSS: меняется только заливка пройденной части
            self.seek.setStyleSheet(f"QSlider::sub-page:horizontal{{background:{dom};}}")
        accent, accent2 = QColor("#FF8A00"), QColor(dom)
        if getattr(self, "_crate", None) is not None:
            try:
                self._crate.set_dominant(QColor(dom))
            except RuntimeError:
                self._crate = None
        if hasattr(self, "viz"):
            self.viz.set_accent(accent, accent2)
        if hasattr(self, "lyrics_view"):
            self.lyrics_view.set_accent(accent, accent2)

    def _switch_visualizer(self, milkdrop: bool):
        """Меняет виджет визуализатора между обычным и Milkdrop."""
        is_milk = isinstance(self.viz, MilkdropVisualizer)
        if milkdrop == is_milk:
            return  # уже нужный тип

        # layout, в котором СЕЙЧАС лежит viz: обычный nv или колонка Fluid
        host = self.viz.parentWidget()
        nv = host.layout() if host is not None else None
        if nv is None:
            nv = self._normal_widget.layout()
        if nv is None:
            return

        old_viz = self.viz
        old_viz.set_playing(False)

        # Создаём новый виджет
        if milkdrop:
            new_viz = MilkdropVisualizer()
            new_viz.setMinimumHeight(160)
        else:
            new_viz = Visualizer()
            new_viz.setMinimumHeight(100)

        # Milkdrop гораздо "громче" визуально — сжимаем пластинку, чтобы
        # освободить место под UI и не дать ей вылезать за пределы визуализатора.
        if hasattr(self, "vinyl"):
            self.vinyl.set_compact(milkdrop)

        new_viz.set_engine(self.engine)
        is_playing = self.engine.is_playing() if hasattr(self.engine, "is_playing") else False
        new_viz.set_playing(is_playing)

        # Находим индекс в layout
        idx = None
        for i in range(nv.count()):
            item = nv.itemAt(i)
            if item and item.widget() is old_viz:
                idx = i
                break

        if idx is None:
            return

        # Запоминаем stretch
        stretch = nv.stretch(idx)
        nv.removeWidget(old_viz)
        old_viz.setParent(None)
        old_viz.deleteLater()

        nv.insertWidget(idx, new_viz, stretch)
        self.viz = new_viz

        # Текст и кнопка "Текст" всегда должны быть НАД визуализатором
        # по z-порядку — особенно заметно на Milkdrop с его "громкой" плазмой.
        if hasattr(self, "title_lbl"):
            self.title_lbl.raise_()
        if hasattr(self, "artist_lbl"):
            self.artist_lbl.raise_()
        if hasattr(self, "btn_lyrics_mode"):
            self.btn_lyrics_mode.raise_()

        # Обновляем ссылки в LyricsView, если он есть
        if hasattr(self, "lyrics_view"):
            self.lyrics_view.set_viz(new_viz)

    @staticmethod
    def _hex_rgb(color):
        return "#%02x%02x%02x" % (color.red(), color.green(), color.blue())

    @staticmethod
    def _mix(c1, c2, amount):
        amount = max(0.0, min(1.0, float(amount)))
        return QColor(
            round(c1.red() * (1-amount) + c2.red() * amount),
            round(c1.green() * (1-amount) + c2.green() * amount),
            round(c1.blue() * (1-amount) + c2.blue() * amount),
        )

    def _cover_theme(self, cover_path):
        if not cover_path or not Path(cover_path).exists():
            return None
        image = QImage(str(cover_path)).convertToFormat(QImage.Format.Format_RGB32)
        if image.isNull():
            return None
        # Чуть больший размер для лучшей кластеризации цветов
        image = image.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        bins = {}
        total_px = 0
        low_sat_px = 0
        sum_v = 0
        for y in range(image.height()):
            for x in range(image.width()):
                c = QColor(image.pixel(x, y))
                h, s, v, _ = c.getHsv()
                total_px += 1
                sum_v += v
                if s < 40:
                    low_sat_px += 1
                # Игнорируем почти чёрные/серые/белые пиксели
                if v < 28 or v > 240 or s < 35:
                    continue
                # Квантизируем в HSV-пространстве для лучшей кластеризации по оттенку
                hq = h // 20   # 18 бакетов по тону
                sq = s // 40   # 6 бакетов по насыщенности
                vq = v // 40   # 6 бакетов по яркости
                key = (hq, sq, vq)
                # Взвешиваем больше за насыщенность, чем за яркость
                weight = (s / 255.0) * 1.8 + (v / 255.0) * 0.4
                bins[key] = bins.get(key, 0) + weight
        if total_px == 0:
            return None

        # ── Чёрно-белая (монохромная) обложка — своя чёрно-белая тема ──
        if low_sat_px / total_px > 0.85:
            base = THEMES.get(self._manual_theme_name) or next(iter(THEMES.values()))
            avg_v = sum_v / total_px
            if avg_v > 140:
                # Белого больше — светлая тема, свечение чёрное
                return {
                    "bg":      "#f2f2f4",
                    "panel":   "#ffffff",
                    "panel2":  "#eceef1",
                    "glass":   "rgba(0,0,0,0.045)",
                    "glass2":  "rgba(0,0,0,0.08)",
                    "text":    "#0a0a0c",
                    "muted":   "#6b6f76",
                    "accent":  "#101114",
                    "accent2": "#3a3c42",
                    "glow":    "#000000",
                    "border":  "rgba(0,0,0,0.10)",
                    "border2": "rgba(0,0,0,0.16)",
                    "danger":  base["danger"],
                }
            else:
                # Чёрного больше — тёмная тема, свечение белое
                return {
                    "bg":      "#08080a",
                    "panel":   "#111114",
                    "panel2":  "#18181b",
                    "glass":   "rgba(255,255,255,0.045)",
                    "glass2":  "rgba(255,255,255,0.08)",
                    "text":    "#f5f5f7",
                    "muted":   "#8b8f96",
                    "accent":  "#f2f2f4",
                    "accent2": "#c7c8cc",
                    "glow":    "#ffffff",
                    "border":  "rgba(255,255,255,0.10)",
                    "border2": "rgba(255,255,255,0.16)",
                    "danger":  base["danger"],
                }

        if not bins:
            return None
        top = sorted(bins.items(), key=lambda kv: kv[1], reverse=True)

        def hsv_to_qcolor(key):
            hq, sq, vq = key
            h = hq * 20 + 10
            s = min(255, sq * 40 + 60)
            v = min(255, vq * 40 + 40)
            c = QColor()
            c.setHsv(h % 360, s, v)
            return c

        primary = hsv_to_qcolor(top[0][0])

        # Ищем secondary с достаточным расстоянием по тону (>30°), чтобы не дублировать
        secondary = primary
        for key, _ in top[1:]:
            candidate = hsv_to_qcolor(key)
            h1 = primary.hsvHue()
            h2 = candidate.hsvHue()
            hue_diff = min(abs(h1 - h2), 360 - abs(h1 - h2))
            if hue_diff > 30:
                secondary = candidate
                break

        # Основной (primary) цвет красит всю тему приложения — насыщенный,
        # но не режет глаз в качестве фона/панелей.
        def boost_primary(c: QColor) -> QColor:
            h, s, v, _ = c.getHsv()
            s = max(170, min(245, s + 60))
            v = max(150, min(210, v + 20))
            out = QColor()
            out.setHsv(h if h >= 0 else 0, s, v)
            return out

        # Вторичный (secondary) цвет идёт только в угловое свечение —
        # максимально яркий и сочный, без тусклости.
        def boost_glow(c: QColor) -> QColor:
            h, s, v, _ = c.getHsv()
            s = max(210, min(255, s + 80))
            v = max(210, min(255, v + 60))
            out = QColor()
            out.setHsv(h if h >= 0 else 0, s, v)
            return out

        secondary_glow = boost_glow(secondary)
        primary = boost_primary(primary)
        secondary = boost_primary(secondary)

        base = THEMES.get(self._manual_theme_name) or next(iter(THEMES.values()))

        # Фон — тёмный, но заметно окрашенный насыщенным первичным цветом обложки
        bg = self._mix(QColor(base["bg"]), primary, 0.18)
        panel = self._mix(QColor(base["panel"]), primary, 0.24)
        panel2 = self._mix(QColor(base["panel2"]), secondary, 0.20)
        border_c = self._mix(QColor(60, 60, 70), primary, 0.34)
        border2_c = self._mix(QColor(80, 80, 90), primary, 0.46)

        return {
            "bg":      self._hex_rgb(bg),
            "panel":   self._hex_rgb(panel),
            "panel2":  self._hex_rgb(panel2),
            "glass":   "rgba(255,255,255,0.04)",
            "glass2":  "rgba(255,255,255,0.07)",
            "text":    base["text"],
            "muted":   base["muted"],
            "accent":  self._hex_rgb(primary),
            "accent2": self._hex_rgb(secondary),
            # Яркий вторичный цвет обложки — источник углового свечения
            "glow":    self._hex_rgb(secondary_glow),
            "border":  f"rgba({border_c.red()},{border_c.green()},{border_c.blue()},0.15)",
            "border2": f"rgba({border2_c.red()},{border2_c.green()},{border2_c.blue()},0.22)",
            "danger":  base["danger"],
        }

    def _custom_cover_accent(self, ct, cover_path, force=False):
        """Тема из конструктора с акцентами из обложки (если в теме так задано) или None."""
        if not (force or ct["palette"].get("cover_accent")):
            return None
        data = self._cover_theme(cover_path)
        if not data:
            return None
        t2 = theme_kit.normalize(ct)
        t2["palette"]["accent"], t2["palette"]["accent2"] = data["accent"], data["accent2"]
        t2["palette"]["glow"] = data.get("glow") or data["accent2"]
        return t2

    def _apply_cover_theme(self, cover_path):
        _mt = THEMES.get(self._manual_theme_name, {})
        pv = self._preview_theme
        if pv is not None or _mt.get("custom"):
            # тема из конструктора (или её предпросмотр): от обложки берутся только акценты
            ct = pv if pv is not None else _mt["ct"]
            t2 = self._custom_cover_accent(ct, cover_path,
                                           force=pv is None and self.settings.get("auto_cover_theme", False))
            if t2 is None:
                return pv is not None            # предпросмотр конструктора не перебиваем
            self._apply_theme_data(theme_kit.to_theme_data(t2))
            return True
        if _mt.get("fluid") or _mt.get("winamp") or _mt.get("yamusic") or _mt.get("daw"):
            return False        # темы Fluid сами подстраиваются под обложку (см. FluidPanel)
        if not self.settings.get("auto_cover_theme", False):
            return False
        data = self._cover_theme(cover_path)
        if not data:
            return False
        self._apply_theme_data(data)
        return True

    def _load_profile(self):
        self.nick_lbl.setText(self.profile.get("nickname","user"))
        self.status_lbl.setText(self.profile.get("status","vibing"))
        av=self.profile.get("avatar","")
        if av and Path(av).exists():
            self.avatar_lbl.setPixmap(load_pixmap(av, 168).scaled(42,42,Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation))

    def _edit_profile(self):
        """Одно окно «Изменить профиль» (фото, ник, статус, «о себе», любимые треки) — profile_editor."""
        from profile_editor import ProfileEditor
        if ProfileEditor(self).exec():
            self._load_profile()
            return True
        return False

    def _add_files(self):
        files,_=QFileDialog.getOpenFileNames(self,"Добавить треки","","Audio (*.mp3 *.ogg *.wav *.flac *.m4a *.opus)")
        for f in files: self._register_track(f)
        self._save_library(); self._refresh_library_view()

    def _add_folder(self):
        folder=QFileDialog.getExistingDirectory(self,"Выбрать папку")
        if not folder: return
        existing={t.get("path") for t in self.library}
        for p in Path(folder).rglob("*"):
            if p.is_file() and p.suffix.lower() in AUDIO_EXTS and str(p.resolve()) not in existing:
                self._register_track(str(p)); existing.add(str(p.resolve()))
        self._save_library(); self._refresh_library_view()

    # ------------------------------------------------------------------ #
    #  Downloader Engine: VK Music / Spotify / YouTube Music / SoundCloud #
    # ------------------------------------------------------------------ #

    def _open_downloader(self):
        if self._downloader_dialog is None:
            self._downloader_dialog = DownloaderDialog(
                self,
                download_dir=self.settings.get("download_dir", str(DATA_DIR / "downloads")),
                vk_cookies=self.settings.get("vk_cookies", ""),
                spotify_client_id=self.settings.get("spotify_client_id", ""),
                spotify_client_secret=self.settings.get("spotify_client_secret", ""),
                on_track_ready=self._on_downloaded_track,
            )
            # Диалог сам не пишет в settings.json — синхронизируем при
            # каждом изменении папки/cookies/spotify-ключей, чтобы выбор
            # запоминался.
            self._downloader_dialog.dir_btn.clicked.connect(self._save_downloader_settings)
            self._downloader_dialog.vk_cookies_btn.clicked.connect(self._save_downloader_settings)
            self._downloader_dialog.spotify_client_id_edit.editingFinished.connect(self._save_downloader_settings)
            self._downloader_dialog.spotify_client_secret_edit.editingFinished.connect(self._save_downloader_settings)
        inapp.present(self, self._downloader_dialog, "Загрузчик музыки")

    def _save_downloader_settings(self):
        # Вызывается ПОСЛЕ того, как соответствующий виджет DownloaderDialog
        # уже обновил его внутреннее состояние — читаем актуальные значения.
        dlg = self._downloader_dialog
        if dlg is None:
            return
        self.settings["download_dir"] = dlg._download_dir
        self.settings["vk_cookies"] = dlg._vk_cookies
        self.settings["spotify_client_id"] = dlg._spotify_client_id
        self.settings["spotify_client_secret"] = dlg._spotify_client_secret
        save_json(SETTINGS_FILE, self.settings)

    def _on_downloaded_track(self, path: str):
        """Колбэк из DownloadManager — трек только что дозагружен и уже
        протегирован (yt-dlp/spotdl). Добавляем его в библиотеку сразу,
        без ожидания конца всего альбома/плейлиста."""
        self._register_track(path)
        self._save_library()
        self._refresh_library_view()
        self._save_downloader_settings()

    # ── Скачивание из онлайн-поиска (без ссылок) ──────────────────────
    def _quick_download(self, url, playlist=None, play=False, cb=None, meta=None):
        """Поставить найденный в интернете трек в очередь закачки.
        cb(state, value): queued / progress(pct) / done(path) / error(msg)."""
        if playlist not in self.playlists and playlist != "Мне нравится":
            playlist = None
        from online_dl import OnlineDownloadQueue
        q = getattr(self, "_online_q", None)
        if q is None:
            q = OnlineDownloadQueue(lambda: self.settings.get("download_dir", str(DATA_DIR / "downloads")),
                                    parent=self)
            q.state_changed.connect(self._online_state)
            q.track_ready.connect(self._online_track_ready)
            self._online_q = q
            self._online_cbs = {}
        if cb is not None:
            self._online_cbs.setdefault(url, []).append(cb)
        # уже скачивали этот трек и файл на месте — не качаем повторно
        prev = (self.settings.get("online_downloaded") or {}).get(url)
        if prev and Path(prev).exists() and q.state(url)[0] not in ("queued", "loading", "retry") \
                and not q._is_preview_file(prev, (meta or {}).get("duration") or 0):
            job = {"url": url, "track": {"url": url, **(meta or {})}, "playlist": playlist or "", "play": play}
            QTimer.singleShot(0, lambda: self._online_track_ready(prev, playlist or "", job))
            return
        q.enqueue({"url": url, **(meta or {})}, playlist or "", play)

    def _open_spotify_import(self):
        from spotify_import import SpotifyImportDialog
        dlg = getattr(self, "_spotify_dlg", None)
        if dlg is None:
            dlg = SpotifyImportDialog(self)
            self._spotify_dlg = dlg
        inapp.present(self, dlg, "Импорт плейлиста из Spotify")

    def _open_service_import(self,provider):
        from spotify_import import SpotifyImportDialog
        attribute='_import_'+provider+'_dialog'
        dialog=getattr(self,attribute,None)
        if dialog is None:
            dialog=SpotifyImportDialog(self,provider=provider);setattr(self,attribute,dialog)
        inapp.present(self,dialog,dialog.windowTitle())

    def _online_state(self, url, state, pct):
        cbs = getattr(self, "_online_cbs", {}).get(url, [])
        for cb in list(cbs):
            try:
                if state == "queued":
                    cb("queued", 0)
                elif state == "loading":
                    cb("progress", pct)
                elif state == "retry":
                    cb("retry", pct)
                elif state == "error":
                    q = getattr(self, "_online_q", None)
                    why = (q.errors.get(url) if q is not None else "") or "трек не найден ни в одном источнике"
                    cbs.remove(cb)
                    cb("error", why)
            except RuntimeError:
                cbs.remove(cb)                      # строка результата уже удалена
            except Exception as e:
                print("[online dl]", e)

    def _online_track_ready(self, path, playlist, job):
        url = job.get("url", "")
        self._register_track(path)
        rpath = str(Path(path).resolve())
        meta = job.get("track") or {}
        t = next((x for x in self.library if x.get("path") == rpath), None)
        if t is not None:
            # теги YouTube/SoundCloud бывают пустыми — подставляем то, что показал поиск
            if not t.get("artist") and meta.get("artist"):
                t["artist"] = meta["artist"]
            if meta.get("title") and (not t.get("title") or t["title"] == sanitize_title(Path(rpath).stem)):
                t["title"] = meta["title"]
            if meta.get("album") and not t.get("album"):
                t["album"] = meta["album"]
        self.settings.setdefault("online_downloaded", {})[url] = rpath
        if playlist and t is not None and (playlist in self.playlists or playlist == "Мне нравится"):
            pl = self.playlists.setdefault(playlist, {"tracks": [], "desc": "Найдено в интернете", "cover": ""})
            if not any(x.get("path") == rpath for x in pl["tracks"]):
                pl["tracks"].append(dict(t))
            save_json(PL_FILE, self.playlists)
            self._refresh_playlists()
        self._save_library()
        self._refresh_library_view()
        save_json(SETTINGS_FILE, self.settings)
        for cb in getattr(self, "_online_cbs", {}).pop(url, []):
            try:
                cb("done", rpath)
            except RuntimeError:
                pass
            except Exception as e:
                print("[online dl]", e)
        if job.get("play") and t is not None:
            if playlist and playlist in self.playlists:
                i = next((k for k, x in enumerate(self.playlists[playlist]["tracks"]) if x.get("path") == rpath), -1)
                if i >= 0:
                    self._play_index(i, playlist)
                    return
            i = next((k for k, x in enumerate(self.library) if x.get("path") == rpath), -1)
            if i >= 0:
                self._play_index(i, "library")

    def _register_track(self,path):
        path=str(Path(path).resolve())
        if any(t.get("path")==path for t in self.library): return
        meta={"path":path,"title":sanitize_title(Path(path).stem),"artist":"","album":"","genre":"","duration":0.0,"cover":""}
        if MutaFile:
            try:
                m=MutaFile(path)
                if m:
                    tags=m.tags
                    def tag(*keys):
                        if not tags: return ""
                        for k in keys:
                            try:
                                v=tags.get(k)
                                if v is not None:
                                    if isinstance(v,(list,tuple)): return str(v[0]) if v else ""
                                    return str(v)
                            except Exception: pass
                        return ""
                    meta["title"]=sanitize_title(tag("TIT2","title") or meta["title"])
                    meta["artist"]=tag("TPE1","artist")
                    meta["album"]=tag("TALB","album")
                    meta["genre"]=tag("TCON","genre")
                    if getattr(m,"info",None) and getattr(m.info,"length",None):
                        meta["duration"]=float(m.info.length)
                    # Embedded cover art: MP3 ID3/APIC, FLAC pictures and MP4/M4A covr.
                    cover_data = None
                    cover_ext = ".jpg"
                    if hasattr(tags, "getall"):
                        try:
                            pics = tags.getall("APIC")
                            if pics:
                                cover_data = pics[0].data
                                mime = str(getattr(pics[0], "mime", "") or "").lower()
                                if "png" in mime:
                                    cover_ext = ".png"
                                elif "webp" in mime:
                                    cover_ext = ".webp"
                        except Exception:
                            pass
                    if cover_data is None:
                        try:
                            pictures = getattr(m, "pictures", None)
                            if pictures:
                                cover_data = pictures[0].data
                                mime = str(getattr(pictures[0], "mime", "") or "").lower()
                                if "png" in mime:
                                    cover_ext = ".png"
                                elif "webp" in mime:
                                    cover_ext = ".webp"
                        except Exception:
                            pass
                    if cover_data is None and tags is not None:
                        try:
                            covr = tags.get("covr")
                            if covr:
                                cover_data = bytes(covr[0])
                                if cover_data.startswith(b"\\x89PNG"):
                                    cover_ext = ".png"
                        except Exception:
                            pass
                    if cover_data:
                        cover = COVER_DIR / (
                            hashlib.sha1(path.encode("utf-8")).hexdigest() + cover_ext
                        )
                        if not cover.exists() or cover.stat().st_size != len(cover_data):
                            cover.write_bytes(cover_data)
                        meta["cover"] = str(cover)
            except Exception as e:
                print("[meta]",e)
        self.library.append(meta)

    def _refresh_missing_covers(self):
        """Пересканирует embedded cover для уже сохранённых треков — в фоновом потоке
        (проверка ~650 файлов и чтение тегов не задерживают появление окна)."""
        if not MutaFile:
            return
        tracks = list(self.library)

        def work():
            found = self._scan_missing_covers(tracks)
            if found:
                self._ui_bridge.call.emit(lambda: self._missing_covers_found(found))
        threading.Thread(target=work, daemon=True, name="cover-refresh").start()

    def _missing_covers_found(self, found):
        for t, cover in found:
            t["cover"] = cover
        self._save_library()
        # Обложки обновились — инвалидируем кеш иконок, чтобы списки подхватили новые картинки.
        self._icon_cache.clear()
        self._refresh_library_view()

    @staticmethod
    def _scan_missing_covers(tracks):
        found = []
        for t in tracks:
            path = t.get("path", "")
            if not path or str(path).startswith("stream:") or not Path(path).exists():
                continue
            if t.get("cover") and Path(t["cover"]).exists():
                continue
            try:
                m = MutaFile(path)
                tags = getattr(m, "tags", None)
                data = None
                ext = ".jpg"
                if tags is not None and hasattr(tags, "getall"):
                    pics = tags.getall("APIC")
                    if pics:
                        data = pics[0].data
                        mime = str(getattr(pics[0], "mime", "") or "").lower()
                        ext = ".png" if "png" in mime else (".webp" if "webp" in mime else ".jpg")
                if data is None:
                    pictures = getattr(m, "pictures", None)
                    if pictures:
                        data = pictures[0].data
                        mime = str(getattr(pictures[0], "mime", "") or "").lower()
                        ext = ".png" if "png" in mime else (".webp" if "webp" in mime else ".jpg")
                if data is None and tags is not None:
                    covr = tags.get("covr")
                    if covr:
                        data = bytes(covr[0])
                        ext = ".png" if data.startswith(b"\\x89PNG") else ".jpg"
                if data:
                    cover = COVER_DIR / (hashlib.sha1(path.encode("utf-8")).hexdigest() + ext)
                    cover.write_bytes(data)
                    found.append((t, str(cover)))
            except Exception as e:
                print("[cover refresh]", e)
        return found

    def _refresh_library_view(self):
        QTimer.singleShot(0, self._wa_refresh_playlist)
        return self._refresh_library_view_impl()

    def _refresh_library_view_impl(self):
        self._filter_library(self.lib_search.text() if hasattr(self, "lib_search") else "")

    def _on_sort_changed(self, _index=None):
        self.settings["lib_sort"] = self.lib_sort.currentData()
        save_json(SETTINGS_FILE, self.settings)
        self._refresh_library_view()

    def _sorted_library(self):
        mode = self.lib_sort.currentData() if hasattr(self, "lib_sort") else "added"
        items = list(self.library)
        if mode == "title":
            items.sort(key=lambda t: str(t.get("title", "")).casefold())
        elif mode == "artist":
            items.sort(key=lambda t: (str(t.get("artist", "")).casefold(), str(t.get("title", "")).casefold()))
        elif mode == "album":
            items.sort(key=lambda t: (str(t.get("album", "")).casefold(), str(t.get("title", "")).casefold()))
        elif mode == "duration":
            items.sort(key=lambda t: float(t.get("duration", 0) or 0))
        # "added" — порядок как в библиотеке (по умолчанию, без изменений)
        return items

    def _filter_library(self, text=""):
        """Публичный метод — немедленно применяет фильтр (вызывается при
        сортировке, добавлении треков и т.п.). Для поискового поля
        используйте дебаунс (_search_debounce → _do_filter_library)."""
        self._do_filter_library(text)

    def _do_filter_library(self, text=None):
        """Реальная фильтрация — вызывается или немедленно (_filter_library),
        или через дебаунс-таймер после 200 мс паузы в печати."""
        if text is None:
            text = self.lib_search.text() if hasattr(self, "lib_search") else ""
        query = (text or "").strip().casefold()

        # setUpdatesEnabled(False) блокирует любые промежуточные перерисовки
        # списка пока мы добавляем элементы — экономит десятки flush-ов Qt.
        self.lib_list.setUpdatesEnabled(False)
        self.lib_list.clear()
        try:
            for t in self._sorted_library():
                title = sanitize_title(str(t.get("title", "Untitled")))
                artist = str(t.get("artist", ""))
                album = str(t.get("album", ""))
                if query and not _words_match(query, title, artist, album):
                    continue
                shown_artist = artist or "Unknown artist"
                item = QListWidgetItem(f"{title}  ·  {shown_artist}")

                # Иконка из кеша; нет в кеше — догрузится фоном (_lazy_icons_kick)
                self._set_lazy_icon(item, t.get("cover", ""))

                item.setData(Qt.ItemDataRole.UserRole, t)
                self.lib_list.addItem(item)
        finally:
            self.lib_list.setUpdatesEnabled(True)
        self._lazy_icons_kick(self.lib_list, 160, 40)

    # ── обложки в списках: без чтения файлов в GUI-потоке ── #
    # Раньше все ~650 обложек библиотеки (75 МБ) декодировались прямо в __init__ — даже в темах, где
    # этот список скрыт; на «холодном» диске запуск растягивался на десятки секунд.

    _LAZY_COVER = Qt.ItemDataRole.UserRole + 7

    def _set_lazy_icon(self, item, cover):
        if not cover:
            return
        icon = self._icon_cache.get(cover)
        if icon is not None:
            item.setIcon(icon)
        else:
            item.setData(self._LAZY_COVER, cover)

    def _lazy_icons_kick(self, lw, side, size):
        """Недостающие иконки списка — в фоновом потоке и только когда список на экране."""
        if not lw.isVisible():
            waiting = self.__dict__.setdefault("_lazy_icon_wait", {})
            if lw not in waiting:
                lw.installEventFilter(self)
            waiting[lw] = (side, size)
            return
        busy = self.__dict__.setdefault("_lazy_icon_busy", set())
        todo = []
        for i in range(lw.count()):
            c = lw.item(i).data(self._LAZY_COVER)
            if c and c not in self._icon_cache and c not in busy and c not in todo:
                todo.append(c)
        if not todo:
            return
        busy.update(todo)

        def work():
            batch = []
            for c in todo:
                img = _round_image(c, side, size)
                batch.append((c, img))
                if len(batch) >= 24:
                    self._ui_bridge.call.emit(lambda b=batch: self._lazy_icons_apply(lw, b))
                    batch = []
            self._ui_bridge.call.emit(lambda b=batch: self._lazy_icons_apply(lw, b))
        threading.Thread(target=work, daemon=True, name="list-icons").start()

    def _lazy_icons_apply(self, lw, batch):
        busy = self.__dict__.get("_lazy_icon_busy", set())
        for c, img in batch:
            busy.discard(c)
            if img is not None and not img.isNull():
                self._icon_cache[c] = QIcon(QPixmap.fromImage(img))
        try:
            for i in range(lw.count()):
                it = lw.item(i)
                c = it.data(self._LAZY_COVER)
                if c and c in self._icon_cache:
                    it.setIcon(self._icon_cache[c])
                    it.setData(self._LAZY_COVER, None)
        except RuntimeError:
            pass

    def _save_library(self):
        added = self._lib_guard.save(self.library)
        if added:                                      # файл коллекции изменили со стороны — объединено
            QTimer.singleShot(0, self._refresh_library_view)

    def _forget_tracks(self, paths):
        """Треки убраны из коллекции осознанно: защита их не вернёт, «Найти пропавшие» не предложит."""
        paths = [str(p) for p in paths if p]
        self._lib_guard.forget(paths)
        kept = [p for p in (self.settings.get("lib_removed") or []) if isinstance(p, str)]
        self.settings["lib_removed"] = (kept + [p for p in paths if p not in kept])[-5000:]

    def find_lost_tracks(self):
        """«Найти пропавшие треки»: всё, что ECHOES помнит о треках (плейлисты, история, кэши, копии, загрузки),
        чьи файлы на месте, а в коллекции их нет — показать и вернуть."""
        import threading
        import library_guard
        self._toast("Ищу пропавшие треки…")
        lib = list(self.library)
        removed = set(self.settings.get("lib_removed") or [])
        dl = str(self.settings.get("download_dir") or "")

        def work():
            try:
                found = [p for p in library_guard.find_lost(DATA_DIR, lib, dl) if p not in removed]
            except Exception as e:                     # noqa: BLE001
                found = []
                print("[library] find lost:", e)
            self._ui_bridge.call.emit(lambda: self._lost_found(found))
        threading.Thread(target=work, daemon=True, name="find-lost").start()

    def _lost_found(self, found):
        if not found:
            QMessageBox.information(self, "Пропавшие треки", "Пропавших треков не нашлось: всё, что ECHOES помнит "
                                    "и что есть на диске, уже в коллекции.")
            return
        sample = "\n".join(Path(p).stem for p in found[:12]) + ("\n…" if len(found) > 12 else "")
        r = QMessageBox.question(self, "Пропавшие треки",
                                 f"Нашлось треков, которых нет в коллекции, но файлы на месте: {len(found)}\n\n"
                                 f"{sample}\n\nВернуть их в коллекцию?")
        if r != QMessageBox.StandardButton.Yes:
            return
        for p in found:
            self._register_track(p)
        self._save_library()
        self._refresh_library_view()
        self._toast(f"Вернул в коллекцию: {len(found)}")

    def _play_from_library(self, item):
        track = item.data(Qt.ItemDataRole.UserRole)
        if not track:
            return
        path = str(track.get("path", ""))
        idx = next((i for i, t in enumerate(self.library) if str(t.get("path", "")) == path), -1)
        if idx >= 0:
            self._play_index(idx, "library")

    def _play_index(self,idx,context="library",rebuild_shuffle=True,start_sec=0.0):
        """rebuild_shuffle=True — трек выбран пользователем вручную (клик по
        библиотеке/плейлисту, "трек дня" и т.п.): если включён shuffle, строим
        СОВЕРШЕННО НОВУЮ перемешанную очередь с этим треком в начале — старая
        очередь (и то, что в ней уже "сыграно") отбрасывается.
        rebuild_shuffle=False — переход внутренний/автоматический (следующий/
        предыдущий трек через _advance, либо клик по уже показанной очереди
        воспроизведения, где позиция и так корректно синхронизирована) —
        существующую shuffle-очередь не трогаем."""
        if not self._qguard:                         # трек выбран вручную — это новый контекст
            self._queued_now = False
            self._saved_ctx = None
        tracks=self.library if context=="library" else self.playlists.get(context,{}).get("tracks",[])
        if not 0<=idx<len(tracks): return
        t=tracks[idx]
        if str(t.get("path", "")).startswith("stream:"):
            if not self.streams.cached(t["path"]):          # ссылки на поток ещё нет — достать и включить
                self._stream_wait(idx, context, rebuild_shuffle, t, start_sec=start_sec)
                return
            self._stream_apply_info(t)
        elif not Path(t.get("path","")).exists():
            QMessageBox.warning(self,"Файл не найден",t.get("path","")); return
        self._stream_token += 1                          # ручной выбор другого трека отменяет ожидание потока

        if getattr(self, "_preview", None) is not None:
            self._preview.stop(resume=False)         # превью из поиска не должно играть поверх трека
        ok = self.engine.load(t["path"], autoplay=True, start_sec=start_sec)
        if not ok: return
        # При смене трека сбрасываем пресеты — temp файл реверба уже не актуален
        if self.engine.preset_mode is not None:
            self.engine.preset_mode = None
            self.engine.preset_factor = 1.0
            self.engine._cleanup_preset_temp()
            if hasattr(self, "_btn_slowed"):
                self._btn_slowed.blockSignals(True)
                self._btn_slowed.setChecked(False)
                self._btn_slowed.setEnabled(True)
                self._btn_slowed.blockSignals(False)
            if hasattr(self, "_btn_speedup"):
                self._btn_speedup.blockSignals(True)
                self._btn_speedup.setChecked(False)
                self._btn_speedup.setEnabled(True)
                self._btn_speedup.blockSignals(False)
            if hasattr(self, "_btn_8d"):
                self._btn_8d.blockSignals(True)
                self._btn_8d.setChecked(False)
                self._btn_8d.setEnabled(True)
                self._btn_8d.blockSignals(False)
            if hasattr(self, "_preset_status_lbl"):
                self._preset_status_lbl.hide()
        if self.settings.get("sound_8d") and hasattr(self, "_btn_8d") and not str(t.get("path", "")).startswith("stream:"):
            QTimer.singleShot(200, lambda: self._btn_8d.isChecked() or self._btn_8d.setChecked(True))   # 8D — и дальше
        context_changed = (context != self.queue_context)
        self.current_index=idx; self.queue_context=context; self._track_finished_guard=False
        if self.shuffle:
            if rebuild_shuffle:
                # Пользователь ткнул в конкретный трек/плейлист — это новая
                # "сессия" прослушивания, а не продолжение старой очереди.
                self._build_shuffle_queue()
            elif context_changed or not self._shuffle_queue:
                self._build_shuffle_queue()
            else:
                # Ищем трек в существующей очереди — если есть, встаём на него
                if idx in self._shuffle_queue:
                    self._shuffle_pos = self._shuffle_queue.index(idx)
                else:
                    # Трек добавлен после генерации очереди — вставляем в текущую позицию
                    self._shuffle_queue.insert(self._shuffle_pos + 1, idx)
                    self._shuffle_pos += 1
        try:                                         # обложку декодируем ОДИН раз — дальше её берут из памяти
            import img_load                          # все, кто рисует играющий трек (img_load.warm)
            img_load.warm(t.get("cover", ""))
        except Exception:                            # noqa: BLE001
            pass
        self._update_track_info(t)
        self._set_playing_ui(True)
        self._record_play_history(t.get("path", ""))
        self.stats.record_play(t)
        # Предзагружаем соседние треки сразу же (0 мс, не после паузы) —
        # именно это убирает задержку при переключении туда-обратно.
        QTimer.singleShot(0, self._preload_adjacent)
        QTimer.singleShot(0, self._stream_prefetch)
        QTimer.singleShot(0, self._loud_neighbors)
        # cover theme — единственный автоматический источник темы теперь
        self._apply_cover_theme(t.get("cover", ""))
        self._load_lyrics()
        self._clip_track_changed()
        # Если открыта страница именно этого плейлиста — обновляем подсветку
        # текущего трека (актуально при автопереходе на следующий трек).
        if self._playlist_detail_open and self._playlist_detail_name == context:
            self._render_playlist_detail(context)

    # ── стриминг (stream_core): онлайн-треки без скачивания ── #

    def _stream_wait(self, idx, context, rebuild_shuffle, t, start_sec=0.0):
        """Ссылка на поток ещё не готова: показать «подключаю…», достать в фоне и включить трек."""
        self._stream_token += 1
        token = self._stream_token
        auto = bool(getattr(self, "_advancing", False))  # дошли сюда автопереходом / «следующий»
        name = f"{t.get('artist') or ''} — {sanitize_title(t.get('title', ''))}".strip(" —")
        self._toast(f"Подключаю поток: {name}…")

        def done(ok, data):
            if token != self._stream_token:
                return                                   # пока ждали, выбрали другой трек
            if not ok:
                self._toast(f"Не удалось включить «{name}»: {data}")
                self._stream_fails = getattr(self, "_stream_fails", 0) + 1
                if auto and self._stream_fails <= 5:     # дальше по очереди, как будто трек кончился
                    self.current_index, self.queue_context = idx, context
                    if self.shuffle and idx in self._shuffle_queue:
                        self._shuffle_pos = self._shuffle_queue.index(idx)
                    QTimer.singleShot(200, lambda: self._advance(1))
                return
            self._stream_fails = 0
            if auto:
                self._advancing = True
            try:
                self._play_index(idx, context, rebuild_shuffle, start_sec=start_sec)
            finally:
                self._advancing = False
        self.streams.resolve(t, done, urgent=True)            # включают сейчас — без очереди за заготовками

    def _stream_apply_info(self, t):
        """Что выяснилось при поиске потока: локальная обложка, процент совпадения, альбом."""
        info = self.streams.info(t["path"])
        changed = False
        if info.get("cover") and not (t.get("cover") and Path(t["cover"]).exists()):
            t["cover"] = info["cover"]
            changed = True
        if info.get("match") and t.get("match") != info["match"]:
            t["match"] = info["match"]
            changed = True
        if info.get("page") and not t.get("url"):
            t["url"] = info["page"]
            changed = True
        fnd = info.get("found") or {}
        if fnd.get("album") and not t.get("album"):
            t["album"] = fnd["album"]
            changed = True
        if not t.get("duration") and info.get("duration"):
            t["duration"] = int(info["duration"])
            changed = True
        if changed:
            QTimer.singleShot(1500, lambda: save_json(PL_FILE, self.playlists))

    def _stream_prefetch(self):
        """Следующие 3 трека очереди: ссылки на поток — заранее, первый — сразу в кэш движка."""
        try:
            nxt = self._upcoming_tracks(3)[0]
        except Exception:                                # noqa: BLE001
            return
        for k, t in enumerate(nxt):
            p = str(t.get("path", ""))
            if not p.startswith("stream:"):
                continue
            if self.streams.cached(p):
                if k == 0:
                    self.engine.preload(p)
                continue

            def ready(ok, _d, p=p, first=(k == 0)):
                if ok and first and self._upcoming_tracks(1)[0][:1] and \
                        str(self._upcoming_tracks(1)[0][0].get("path", "")) == p:
                    self.engine.preload(p)
            self.streams.resolve(t, ready)

    def stream_tracks(self, tracks, start=0, playlist=None, album="", start_sec=0.0):
        """Включить треки во временной очереди, не создавая пользовательский плейлист."""
        import stream_core
        items = [x if str(x.get("path", "")).startswith("stream:") or x.get("path") else stream_core.make_track(x, album)
                 for x in tracks]
        items = [x for x in items if x.get("path")]
        if not items:
            return
        name = playlist if str(playlist or "").startswith(HIDDEN_PL) else self.ONLINE_PL
        self.playlists[name] = {"tracks": items, "desc": f"auto: {album or 'онлайн'}", "cover": ""}
        if not str(name).startswith(HIDDEN_PL):
            save_json(PL_FILE, self.playlists)
        self._play_index(max(0, min(start, len(items) - 1)), name, start_sec=start_sec)

    def stream_queue_add(self, t, next_=True):
        """Онлайн-трек в очередь «играть следующим» (потоком)."""
        import stream_core
        item = t if str(t.get("path", "")).startswith("stream:") else stream_core.make_track(t)
        self.streams.prefetch(item)
        cur = self._current_track()
        if cur is None:
            self.stream_tracks([item])
            return
        ctx = self.queue_context
        if ctx == "library":                             # библиотека — не плейлист: очередь переезжает в «Онлайн»
            self.playlists[self.ONLINE_PL] = {"tracks": [cur, item], "desc": "auto: онлайн", "cover": ""}
            self.queue_context, self.current_index = self.ONLINE_PL, 0
            if self.shuffle:
                self._build_shuffle_queue()
        else:
            tr = self._ctx_tracks(ctx)
            tr.insert(self.current_index + 1 if next_ else len(tr), item)
            if self.shuffle and self._shuffle_queue:
                self._shuffle_queue = [i + 1 if i > self.current_index else i for i in self._shuffle_queue]
                self._shuffle_queue.insert(self._shuffle_pos + 1, self.current_index + 1)
        save_json(PL_FILE, self.playlists)
        QTimer.singleShot(0, self._stream_prefetch)
        self._toast(f"В очереди: {item.get('artist') or ''} — {item.get('title') or ''}".strip(" —"))

    ONLINE_PL = HIDDEN_PL + "online"             # скрытая очередь онлайн-треков — не плейлист

    def reveal_in_explorer(self, t):
        """Открыть папку с файлом трека в проводнике и выделить файл (трек или путь)."""
        p = str((t or {}).get("path", "") if isinstance(t, dict) else (t or ""))
        if p.startswith("stream:"):
            self._toast("Онлайн-трек — файла на компьютере нет. Скачать: кнопка у трека или меню волны")
            return
        if not p or not Path(p).exists():
            self._toast(f"Файл не найден: {p}" if p else "Файл не найден")
            return
        import subprocess
        try:
            if sys.platform == "win32":
                subprocess.Popen(f'explorer /select,"{_os.path.normpath(p)}"')
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", p])
            else:
                subprocess.Popen(["xdg-open", str(Path(p).parent)])
        except Exception as e:                           # noqa: BLE001
            self._toast(f"Не удалось открыть проводник: {e}")

    def track_menu_for(self, path):
        """Меню трека по пути (для виджетов конструктора тем): играть, проводник, теги."""
        p = str(path or "")
        idx = next((i for i, x in enumerate(self.library) if str(x.get("path", "")) == p), -1)
        t = self.library[idx] if idx >= 0 else {"path": p}
        m = QMenu(self)
        if idx >= 0:
            m.addAction("Играть", lambda: self._play_index(idx, "library"))
            m.addAction("Играть следующим", lambda: self.queue_add([t], next_=True))
        self.reveal_action(m, t)
        if idx >= 0:
            m.addAction("Теги, обложка и текст…", lambda: self.edit_track_tags(t))
        from PyQt6.QtGui import QCursor
        m.exec(QCursor.pos())

    def reveal_action(self, menu, t):
        """Пункт «Показать в проводнике» для меню трека (неактивен у онлайн-треков)."""
        a = menu.addAction("Показать в проводнике", lambda: self.reveal_in_explorer(t))
        if str((t or {}).get("path", "")).startswith("stream:"):
            a.setEnabled(False)
            a.setText("Показать в проводнике (онлайн-трек)")
            menu.addAction("Скачать трек", lambda: self.stream_download(t))
        return a

    def ctx_title(self, ctx=None) -> str:
        """Название контекста воспроизведения для интерфейса."""
        ctx = self.queue_context if ctx is None else ctx
        if ctx == "library":
            return "Библиотека"
        if ctx == HIDDEN_PL + "wave":
            return "Моя волна"
        if ctx == HIDDEN_PL + "mood":
            return "Подборка"
        if ctx == HIDDEN_PL + "album":
            return "Альбом"
        if str(ctx).startswith(HIDDEN_PL):
            return "Онлайн"
        return str(ctx)

    def stream_download_current(self):
        """Скачать текущий онлайн-трек в коллекцию без создания плейлиста."""
        self.stream_download(self._current_track())

    def stream_download(self, t):
        """Скачать онлайн-трек («stream:…») в коллекцию."""
        if not t or not str(t.get("path", "")).startswith("stream:"):
            self._toast("Этот трек уже в коллекции")
            return
        url = t.get("url") or self.streams.info(t["path"]).get("page")
        if not url:
            self._toast("Трек ещё не найден в сети — подождите, пока он заиграет")
            return
        self._quick_download(url, playlist="", meta={"title": t.get("title"), "artist": t.get("artist"),
                                                     "album": t.get("album") or "", "duration": t.get("duration") or 0,
                                                     "thumb_url": t.get("thumb_url") or ""})
        self._toast(f"Скачиваю: {t.get('artist') or ''} — {t.get('title') or ''}".strip(" —"))

    def _update_track_info(self,t):
        try:
            self._eq_auto_apply(t)
        except Exception as e:                           # noqa: BLE001
            print("[eq auto]", e)
        try:
            _tt = sanitize_title(t.get("title", "") or "")
            _ta = t.get("artist") or ""
            _line = f"{_ta} — {_tt}" if _ta and _tt else (_tt or _ta)
            if getattr(self, "titlebar", None) is not None:
                self.titlebar.set_title(_line)
            self.setWindowTitle(f"{_line} · ECHOES" if _line else "ECHOES")
        except Exception:                                # noqa: BLE001
            pass
        self.title_lbl.setText(sanitize_title(t.get("title","Untitled")))
        artist=t.get("artist") or "Unknown artist"
        album=t.get("album") or "Unknown album"
        self.artist_lbl.setText(f"{artist}  ·  {album}")
        dur=float(self.engine.duration or t.get("duration",0) or 0); self.t_tot.setText(self._fmt(dur)); self.t_cur.setText("00:00"); self.seek.setValue(0)
        cover=t.get("cover","")
        valid_cover = cover if cover and Path(cover).exists() else None
        self.vinyl.set_cover(valid_cover)
        if hasattr(self, "_ambience"):
            self._ambience.set_cover(valid_cover)
        self._cur_cover = valid_cover
        if self._crt is not None and self._crt.active():
            self._crt.set_cover(valid_cover)
        if hasattr(self, "_stage"):
            # Доминирующий цвет считается в фоновом потоке, UI не подвисает.
            self._stage.set_cover(valid_cover, key=str(t.get("path", "")))
            self._stage.set_counter(f"{self.current_index + 1:03d}" if self.current_index >= 0 else "")
            self._stage.set_tag(sanitize_title(t.get("title", "")))
        if getattr(self, "_wa_on", False):
            self._winamp_update_display(t)
        if getattr(self, "_crate", None) is not None:
            self._crate_refresh(t)
        # Плавный fade-in заголовка
        self._fade_in(self.title_lbl)
        self._fade_in(self.artist_lbl)

    def _fade_in(self, widget):
        if getattr(self, "_lyrics_mode", False):
            return          # под overlay текста заголовок погашен — не проявляем
        eff = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", widget)
        anim.setDuration(320)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _set_playing_ui(self,playing):
        self.btn_play.set_playing(playing)
        self.vinyl.set_playing(playing); self.viz.set_playing(playing)
        # Discord Rich Presence: обновляем статус при смене play/pause
        self._update_discord_rpc(playing)

    def _update_discord_rpc(self, playing: bool = None):
        """Отправляет текущий трек в Discord Rich Presence."""
        if not hasattr(self, "discord_rpc") or self.discord_rpc is None:
            return
        if getattr(self, "_discord_act_key", None) is not None:
            return                                         # сейчас в Discord — студия или конструктор
        if self.current_index < 0:
            self.discord_rpc.clear()
            return
        tracks = self.library if self.queue_context == "library" else \
                 self.playlists.get(self.queue_context, {}).get("tracks", [])
        if not (0 <= self.current_index < len(tracks)):
            self.discord_rpc.clear()
            return
        if playing is None:
            playing = self.engine.is_playing()
        t = tracks[self.current_index]
        title = sanitize_title(t.get("title", "Untitled"))
        artist = (t.get("artist") or "").replace(" - Topic", "").strip()
        duration = float(self.engine.duration or t.get("duration", 0) or 0)
        position = self.engine.get_position()
        album = (t.get("album") or "").strip()
        cover_url = ""
        if str(t.get("path", "")).startswith("stream:"):   # онлайн-трек: обложка источника уже есть
            cover_url = str(t.get("thumb_url") or "").replace("-t300x300.", "-t500x500.")
            if not cover_url.startswith("http"):
                cover_url = ""
        extra = {}
        try:
            extra = self._discord_extra(t, tracks, playing)
        except Exception as e:                             # noqa: BLE001
            print("[discord_rpc] extra:", e)
        self.discord_rpc.update_track(title, artist, duration, position, playing, cover_url=cover_url, album=album,
                                      genre=t.get("genre") or "", **extra)
        self._discord_sent = (str(t.get("path", "")), bool(playing), time.time() - float(position or 0))
        try:                                               # обложки следующих треков — заранее, чтобы смена была мгновенной
            for nt in self._upcoming_tracks(2)[0]:
                self.discord_rpc.prefetch((nt.get("artist") or "").replace(" - Topic", "").strip(),
                                          sanitize_title(nt.get("title", "")), float(nt.get("duration") or 0))
        except Exception:                                  # noqa: BLE001
            pass

    # ── крутые штуки статуса: строка текста, место в очереди, статистика, ссылка ── #

    def _discord_lyric_now(self) -> str:
        """Строка синхронизированного текста, которую поют сейчас ("" — нет таймингов / проигрыш)."""
        lv = getattr(self, "lyrics_view", None)
        lines = getattr(lv, "_lines", None) or []
        if not lines or not getattr(lv, "_has_timings", False):
            return ""
        f = float(getattr(self.engine, "preset_factor", 1.0) or 1.0)
        ms = float(self.engine.get_position() or 0) * 1000.0 * f
        cur = ""
        for ln in lines:
            m = int(ln.get("ms", -1))
            if m < 0:
                continue
            if m > ms + 150:                            # строку показываем чуть заранее — Discord обновится не сразу
                break
            cur = (ln.get("text") or "").strip()
        return cur

    def _discord_extra(self, t, tracks, playing) -> dict:
        S = self.settings
        out = {}
        ctx = self.queue_context
        if S.get("discord_queue", True) and ctx != "library" and len(tracks) > 1:
            out["queue"] = (self.current_index + 1, len(tracks), self.ctx_title(ctx))
        if S.get("discord_stats", True):
            st = getattr(self, "stats", None)
            d = getattr(st, "data", {}) or {}
            parts = []
            sec = float((d.get("days") or {}).get(time.strftime("%Y-%m-%d"), 0.0))
            if sec >= 60:
                h, m = int(sec // 3600), int(sec % 3600 // 60)
                parts.append(f"сегодня в ECHOES {h} ч {m} мин" if h else f"сегодня в ECHOES {m} мин")
            plays = int(((d.get("tracks") or {}).get(str(t.get("path", ""))) or {}).get("plays", 0))
            if plays >= 2:
                parts.append(f"этот трек — {plays}-й раз")
            try:
                import i18n
                parts = [i18n.tr(x) for x in parts]
            except Exception:                              # noqa: BLE001
                pass
            out["stats_text"] = " · ".join(parts)
        path = str(t.get("path", ""))
        if path.startswith("stream:http"):
            out["link"] = path[len("stream:"):]
        elif str(t.get("url") or "").startswith("http"):
            out["link"] = str(t["url"])
        return out

    def _discord_lyric_tick(self):
        """Строка текста сменилась — обновить статус (не чаще раза в 4.5 с: у Discord лимит 5 обновлений
        за 20 с, место остаётся и для смены трека)."""
        rpc = getattr(self, "discord_rpc", None)
        if rpc is None or not rpc.is_available() or not self.settings.get("discord_lyrics", True):
            return
        if getattr(self, "_discord_act_key", None) is not None or not self.engine.is_playing():
            return
        line = self._discord_lyric_now()
        last, ts = getattr(self, "_discord_lyr", ("", 0.0))
        if line != last and time.time() - ts >= 4.5:
            self._update_discord_rpc(True)

    # ── что вы делаете: конструктор тем, ECHOES Studio — отдельные активности в Discord ── #

    def _discord_feature(self, key, on):
        self.settings["discord_" + key] = bool(on)
        save_json(SETTINGS_FILE, self.settings)
        if getattr(self, "discord_rpc", None) is not None:
            self.discord_rpc.set_features(**{key: bool(on)})
            self._update_discord_rpc()

    def _discord_activity(self):
        """dict для DiscordPresence.set_activity или None — тогда в Discord музыка («Слушает»)."""
        if not self.settings.get("discord_activities", True):
            return None
        since = self.__dict__.setdefault("_discord_since", {})

        def started(kind):
            return since.setdefault(kind, time.time())
        cur = self._current_track()
        song = ""
        if cur:
            song = f"{(cur.get('artist') or '').replace(' - Topic', '').strip()} — {sanitize_title(cur.get('title', ''))}"
            song = song.strip(" —")
        # конструктор тем: окно открыто и не свёрнуто
        st = getattr(self, "_studio", None)
        try:
            studio_open = st is not None and st.isVisible() and not st.isMinimized()
        except RuntimeError:
            studio_open = False
        if studio_open:
            t = getattr(st, "t", {}) or {}
            nlay = len(t.get("layers") or [])
            code = [d for d in (getattr(st, "_code", {}) or {}).values() if d is not None]
            blocks = False
            for d in code:
                try:
                    blocks = blocks or d._blocks_on()
                except RuntimeError:
                    pass
            what = ("Программирует блоками" if blocks else "Пишет код на EchoScript") if code else "Делает тему"
            since.pop("daw", None)
            return {"name": "Конструктор тем ECHOES", "details": f"{what}: «{t.get('name') or 'Новая тема'}»",
                    "state": f"слоёв: {nlay}" + (f" · играет {song}" if song and self.engine.is_playing() else ""),
                    "image": "theme_studio", "image_text": "Конструктор тем ECHOES", "start": started("theme"),
                    "key": ("theme", t.get("name"), nlay, what)}
        since.pop("theme", None)
        # ECHOES Studio (тема DAW)
        daw = getattr(self, "_daw", None) if getattr(self, "_daw_on", False) else None
        if daw is not None:
            pr = getattr(daw, "p", {}) or {}
            nm = pr.get("name") or "Без названия"
            chans = len(pr.get("channels") or [])
            bpm = float(pr.get("bpm") or 0)
            return {"name": "ECHOES Studio", "details": f"Делает музыку: «{nm}»",
                    "state": f"{bpm:.0f} BPM · каналов: {chans}", "image": "studio", "image_text": "ECHOES Studio",
                    "start": started("daw"), "key": ("daw", nm, chans, round(bpm))}
        since.pop("daw", None)
        return None

    def _discord_drift(self):
        """Раз в 4 с: занятие сменилось (студия, конструктор), трек сменился или позиция уехала —
        обновить статус в Discord."""
        if self.discord_rpc is None or not self.discord_rpc.is_available():
            return
        try:
            act = self._discord_activity()
        except Exception as e:                             # noqa: BLE001
            print("[discord_rpc] activity:", e)
            act = None
        if act is not None:
            key = act.pop("key", None)
            if key != getattr(self, "_discord_act_key", None):
                self._discord_act_key = key
                self.discord_rpc.set_activity(**act)
            return
        if getattr(self, "_discord_act_key", None) is not None:   # вернулись к музыке
            self._discord_act_key = None
            self._update_discord_rpc()
            return
        st = getattr(self, "_discord_sent", None)
        if st is None:
            return
        try:
            playing = bool(self.engine.is_playing())
            cur = self._current_track()
            path = str((cur or {}).get("path", ""))
            pos = float(self.engine.get_position() or 0)
        except Exception:                                  # noqa: BLE001
            return
        if path != st[0] or playing != st[1] or (playing and abs((time.time() - pos) - st[2]) > 3.0):
            self._update_discord_rpc(playing)

    def toggle_play(self):
        pv = getattr(self, "_preview", None)
        if pv is not None and pv.is_active():
            pv.toggle_pause()                        # идёт превью из поиска — пауза относится к нему
            return
        if self.current_index<0:
            tracks=self.library if self.queue_context=="library" else self.playlists.get(self.queue_context,{}).get("tracks",[])
            if tracks: self._play_index(0,self.queue_context)
            return
        if self.engine.is_playing():
            # pause_with_effect() играет короткий spin-down вместо резкого
            # обрыва звука (управляется чекбоксом "Остановка пластинки").
            self.engine.pause_with_effect(); self._set_playing_ui(False)
        else:
            if self.engine.play_with_effect():
                self._set_playing_ui(True)

    def next_track(self): self._advance(1)
    def prev_track(self):
        if self.engine.get_position()>3:
            self.engine.seek(0); return
        self._advance(-1)

    # ── пользовательская очередь («Играть следующим» / «В очередь») ── #

    def queue_add(self, tracks, next_=False):
        ok = [dict(t) for t in tracks if t.get("path") and Path(t["path"]).exists()]
        if not ok:
            return
        if next_:
            self.user_queue[0:0] = ok
        else:
            self.user_queue.extend(ok)
        n = len(ok)
        what = f"«{sanitize_title(ok[0].get('title', ''))}»" if n == 1 else f"{n} треков"
        self._toast(f"{what} — следующим" if next_ else f"{what} добавлено в очередь (всего: {len(self.user_queue)})")

    def queue_add_path(self, path, next_=False):
        t = next((x for x in self.library if str(x.get("path", "")) == str(path)), None)
        if t is not None:
            self.queue_add([t], next_)

    def _play_from_queue(self):
        while self.user_queue:
            t = self.user_queue.pop(0)
            p = str(t.get("path", ""))
            idx = next((i for i, x in enumerate(self.library) if str(x.get("path", "")) == p), -1)
            if idx < 0 or not Path(p).exists():
                continue
            if not self._queued_now:
                self._saved_ctx = (self.queue_context, self.current_index,
                                   list(self._shuffle_queue), self._shuffle_pos)
            self._qguard = True
            try:
                self._play_index(idx, "library", rebuild_shuffle=False)
            finally:
                self._qguard = False
            self._queued_now = True
            return True
        return False

    def _restore_ctx(self):
        """Очередь пользователя кончилась — вернуться в плейлист/библиотеку, откуда её запустили."""
        ctx, self._saved_ctx, self._queued_now = self._saved_ctx, None, False
        if not ctx:
            return
        c, i, sq, sp = ctx
        self.queue_context, self.current_index = c, i
        self._shuffle_queue, self._shuffle_pos = sq, sp

    def _toast(self, text):
        lb = getattr(self, "_toast_lbl", None)
        if lb is None:
            lb = self._toast_lbl = QLabel(self)
            lb.setStyleSheet("background:rgba(34,34,34,240);color:#fff;border-radius:16px;"
                             "padding:9px 18px;font-size:13px;font-weight:600;")
            lb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self._toast_timer = QTimer(self)
            self._toast_timer.setSingleShot(True)
            self._toast_timer.timeout.connect(lb.hide)
        lb.setText(text)
        lb.adjustSize()
        lb.move((self.width() - lb.width()) // 2, self.height() - lb.height() - 120)
        lb.show()
        lb.raise_()
        self._toast_timer.start(2200)

    def _advance(self,step):
        if step > 0 and self.user_queue and self._play_from_queue():
            return
        if self._queued_now:
            self._restore_ctx()
            if step < 0:
                step = 0                              # «назад» из очереди — снова трек, на котором были
        tracks=self.library if self.queue_context=="library" else self.playlists.get(self.queue_context,{}).get("tracks",[])
        if not tracks: return
        if self.shuffle and len(tracks)>1:
            # Используем shuffle queue — трек не может повториться раньше
            # чем завершится весь цикл, а prev_track идёт назад по той же очереди.
            if not self._shuffle_queue or len(self._shuffle_queue) != len(tracks):
                self._build_shuffle_queue()
            new_pos = self._shuffle_pos + step
            if new_pos >= len(self._shuffle_queue):
                if self.repeat_mode == 1:
                    # Пересобираем очередь для следующего круга
                    self._build_shuffle_queue()
                    new_pos = 0
                else:
                    self._set_playing_ui(False); return
            if new_pos < 0:
                new_pos = 0  # назад с первого трека — остаёмся на нём
            self._shuffle_pos = new_pos
            idx = self._shuffle_queue[new_pos]
        else:
            idx=self._step_index(self.queue_context, self.current_index, step, len(tracks), wrap_back=True)
            if idx<0:
                self._set_playing_ui(False); return
        # rebuild_shuffle=False: это автоматический переход внутри уже
        # построенной очереди — она не должна пересобираться на каждый next/prev.
        self._advancing = True
        try:
            self._play_index(idx,self.queue_context,rebuild_shuffle=False)
        finally:
            self._advancing = False

    def _loud_neighbors(self):
        """Заранее измерить громкость соседних треков — к переключению коэффициент уже готов."""
        if not self._loud_enabled():
            return
        tracks = self.library if self.queue_context == "library" else \
            self.playlists.get(self.queue_context, {}).get("tracks", [])
        for k in (1, -1, 2):
            i = self.current_index + k
            if 0 <= i < len(tracks):
                self.loudness.request(str(tracks[i].get("path", "")))

    def _preload_adjacent(self):
        """Сразу после старта трека кидаем в кэш движка соседей —
        и следующий, и предыдущий, чтобы переключение в любую сторону
        было без задержки на открытие/парсинг файла."""
        tracks = self.library if self.queue_context == "library" else \
                 self.playlists.get(self.queue_context, {}).get("tracks", [])
        if not tracks or self.current_index < 0:
            return

        if self.shuffle and len(tracks) > 1:
            # Предзагружаем следующий трек из shuffle queue
            if not self._shuffle_queue or len(self._shuffle_queue) != len(tracks):
                self._build_shuffle_queue()
            next_pos = self._shuffle_pos + 1
            if next_pos < len(self._shuffle_queue):
                idx = self._shuffle_queue[next_pos]
                self._next_shuffle_idx = idx
                self.engine.preload(tracks[idx].get("path", ""))
                self._warm_covers([tracks[idx].get("cover", "")])
            else:
                self._next_shuffle_idx = None
            return

        self._next_shuffle_idx = None
        covers = []

        nxt = self._step_index(self.queue_context, self.current_index, 1, len(tracks))
        if 0 <= nxt < len(tracks):
            p = tracks[nxt].get("path", "")
            if p and Path(p).exists():
                self.engine.preload(p)
            covers.append(tracks[nxt].get("cover", ""))

        prv = self._step_index(self.queue_context, self.current_index, -1, len(tracks))
        if 0 <= prv < len(tracks):
            p = tracks[prv].get("path", "")
            if p and Path(p).exists():
                self.engine.preload(p)
            covers.insert(0, tracks[prv].get("cover", ""))   # следующий — последним: он нужнее предыдущего
        self._warm_covers(covers)

    def _warm_covers(self, covers):
        """Обложки соседних треков — в память заранее, в фоне: переключение не ждёт декодирования."""
        covers = [str(c) for c in covers if c]
        if not covers:
            return

        def work():
            try:
                import img_load
                for c in covers:
                    img_load.warm(c)
            except Exception as e:                       # noqa: BLE001
                print("[cover warm]", e)
        threading.Thread(target=work, daemon=True, name="cover-warm").start()

    def _lyrics_seek(self, ms: int):
        """Клик по строке текста — перемотка к ней (с учётом пресета)."""
        if self.current_index < 0:
            return
        f = float(getattr(self.engine, "preset_factor", 1.0) or 1.0)
        try:
            self.engine.seek(max(0.0, ms / 1000.0 / f))
        except Exception as e:
            print("[lyrics seek]", e)

    def _preview_seek(self, value):
        dur = float(self.engine.duration or 0.0)
        if dur > 0:
            self.t_cur.setText(self._fmt(value / 1000.0 * dur))

    def _on_seek(self):
        if self.current_index < 0:
            return
        dur = float(self.engine.duration or 0.0)
        if dur <= 0:
            tracks = self.library if self.queue_context == "library" else self.playlists.get(self.queue_context, {}).get("tracks", [])
            if 0 <= self.current_index < len(tracks):
                dur = float(tracks[self.current_index].get("duration", 0) or 0)
        if dur > 0:
            self.engine.seek(self.seek.value() / 1000.0 * dur)

    def _on_engine_duration(self, duration):
        if self.current_index < 0:
            return
        self.t_tot.setText(self._fmt(duration))
        tracks = self.library if self.queue_context == "library" else self.playlists.get(self.queue_context, {}).get("tracks", [])
        if 0 <= self.current_index < len(tracks):
            tracks[self.current_index]["duration"] = float(duration)
            if self.queue_context == "library":
                self._save_library()

    def _on_engine_position(self, position):
        if self.current_index < 0:
            return
        self._heard_at = (str(self.engine.current_path), float(position))   # где оборвался поток — оттуда и продолжить
        duration = float(self.engine.duration or 0.0)
        self.t_cur.setText(self._fmt(position))
        if duration > 0 and not self.seek.isSliderDown():
            self.seek.blockSignals(True)
            self.seek.setValue(max(0, min(1000, int(round(position / duration * 1000.0)))))
            self.seek.blockSignals(False)
        # Передаём позицию и хронометраж в lyrics_view (в миллисекундах)
        if self._lyrics_mode:
            # тайминги текста — по оригиналу; файл пресета длиннее/короче
            f = float(getattr(self.engine, "preset_factor", 1.0) or 1.0)
            try:
                position = self.engine.get_position_smooth()   # без «ступенек» VLC
            except Exception:
                pass
            cur_ms = int(position * 1000 * f)
            tot_ms = int(duration * 1000 * f)
            self.lyrics_view.set_position(cur_ms)
            self.lyrics_view.set_time(cur_ms, tot_ms)

        # Гэплесс / кроссфейд: за N мс до конца трека стартуем следующий.
        #
        # Гэплесс (engine.gapless_enabled): убирает тишину между треками —
        # вторая дека прогревается заглушённой за ~150 мс до стыка, а в сам
        # момент Ended старой деки mute снимается мгновенно. Триггерим
        # заранее (GAPLESS_LEAD_MS), чтобы прогрев успел отработать.
        # Совместим с кроссфейдом: если оба включены — гэплесс-прогрев
        # устраняет тишину, а кроссфейд добавляет плавное сведение поверх.
        #
        # Кроссфейд (engine.crossfade_enabled, crossfade_ms > 0):
        # плавно сводит громкости двух треков.
        tools = getattr(self, '_listening_tools', None)
        if (not self.engine.is_crossfading and duration > 0
                and not (tools and tools.blocks_transition())):
            remain = duration - position
            cf_ms = self.engine.crossfade_ms if self.engine.crossfade_enabled else 0
            gapless = self.engine.gapless_enabled

            dj = self._dj_tick(position, duration) if cf_ms > 0 and self.settings.get("dj_crossfade") else None
            if dj == "started":
                pass                                           # умный переход уже пошёл
            elif cf_ms > 0 and dj is None and remain <= cf_ms / 1000.0:
                next_path = self._peek_next_path()
                if next_path:
                    self.engine.start_crossfade(next_path, cf_ms)
            # свой вывод: следующая дека копит звук до стыка — 3 с с запасом влезают в её очередь (5.5 с);
            # с 5 с очередь переполнялась, VLC вставал и потом выбрасывал «опоздавший» звук (скачок трека)
            elif gapless and remain <= (3.0 if self.engine.mixer is not None else self._GAPLESS_LEAD_MS / 1000.0):
                next_path = self._peek_next_path()
                if next_path:
                    self.engine.start_gapless(next_path, remain * 1000.0)

    def _dj_tick(self, position, duration):
        """Умный кроссфейд (dj_mix): «started» — переход запущен; «wait» — план есть, ещё рано;
        None — плана нет (поток, анализ не готов, другой трек) → обычный кроссфейд."""
        import dj_mix
        cur = str(getattr(self.engine, "current_path", "") or "")
        if not cur or not _os.path.isfile(cur):
            return None
        st = self.__dict__.setdefault("_dj", {})
        if st.get("cur") != cur:
            st.clear()
            st["cur"] = cur
            dj_mix.analyze_async(cur, duration)
        if position < duration * 0.35:
            return None
        if "next" not in st:                                   # следующий — один раз за трек (и его анализ)
            nxt = self._peek_next_path()
            st["next"] = str(nxt) if nxt else ""
            if st["next"] and _os.path.isfile(st["next"]):
                dj_mix.analyze_async(st["next"])
        nxt = st.get("next")
        if not nxt or not _os.path.isfile(nxt):
            return None
        a, b = dj_mix._MEM.get(dj_mix._key(cur)), dj_mix._MEM.get(dj_mix._key(nxt))
        if not a or not b:
            return None
        p = st.get("plan") or dj_mix.plan(a, b, self.engine.crossfade_ms / 1000.0)
        st["plan"] = p
        if p is None:
            return None
        if position < p["start"]:
            return "wait"
        if st.get("done"):
            return "started"
        if self._peek_next_path() != nxt:                      # очередь поменялась — обычный переход
            return None
        st["done"] = True
        late = max(0.0, position - p["start"])                 # опоздание тика — сдвинуть и вход: доли совпадут
        self.engine.start_crossfade(nxt, int(p["length"] * 1000), start_sec=p["next_at"] + late)
        return "started"

    def _peek_next_path(self):
        """Путь следующего трека без побочных эффектов — для старта кроссфейда
        и gapless. Запоминает, КАК перейти (_pending_transition), а применяется
        это в _on_crossfade_started — в момент, когда следующий трек реально
        зазвучал. Покрывает и пользовательскую очередь, и возврат из неё, и
        повтор одного трека — раньше в этих случаях gapless не включался и
        между треками была пауза."""
        self._pending_transition = None
        if self.repeat_mode == 2:                     # повтор трека — бесшовно сам в себя
            t = self._current_track()
            p = str((t or {}).get("path", ""))
            if not p or not Path(p).exists():
                return None
            self._crossfade_next_index = self.current_index
            self._pending_transition = ("repeat", p)
            return p
        if self.user_queue:                           # следующий — из очереди «Играть следующим»
            for t in self.user_queue:
                p = str(t.get("path", ""))
                idx = next((i for i, x in enumerate(self.library) if str(x.get("path", "")) == p), -1)
                if idx >= 0 and Path(p).exists():
                    self._crossfade_next_index = idx
                    self._pending_transition = ("queue", p, t, idx)
                    return p
            return None
        if self._queued_now:                          # очередь кончилась — назад в плейлист
            ctx = self._saved_ctx
            if not ctx:
                return None
            c, i, sq, sp = ctx
            tracks = self.library if c == "library" else self.playlists.get(c, {}).get("tracks", [])
            idx = self._next_index_in(tracks, i, sq, sp)
            p = str(tracks[idx].get("path", "")) if 0 <= idx < len(tracks) else ""
            if not p or not Path(p).exists():
                return None
            self._crossfade_next_index = idx
            self._pending_transition = ("restore", p)
            return p
        tracks = self.library if self.queue_context == "library" else \
                 self.playlists.get(self.queue_context, {}).get("tracks", [])
        idx = self._next_index_in(tracks, self.current_index, self._shuffle_queue, self._shuffle_pos)
        if not (0 <= idx < len(tracks)):
            return None
        p = tracks[idx].get("path", "")
        if not p or not Path(p).exists():
            return None
        self._crossfade_next_index = idx
        return p

    def _next_index_in(self, tracks, cur, sq, sp):
        """Следующий индекс для заданного контекста (как в _advance(1)) или -1."""
        if not tracks:
            return -1
        if self.shuffle and len(tracks) > 1:
            next_pos = sp + 1
            if sq and 0 <= next_pos < len(sq):
                return sq[next_pos]
            if self._next_shuffle_idx is not None and self._next_shuffle_idx != cur:
                return self._next_shuffle_idx
            if sq and next_pos >= len(sq) and self.repeat_mode == 1:
                import random as _rnd                 # новый круг перемешивания — любой другой трек
                choices = [k for k in range(len(tracks)) if k != cur]
                if choices:
                    self._next_shuffle_idx = _rnd.choice(choices)
                    return self._next_shuffle_idx
            return -1
        ctx = self._saved_ctx[0] if self._queued_now and self._saved_ctx else self.queue_context
        return self._step_index(ctx, cur, 1, len(tracks))

    def _step_index(self, ctx, cur, step, n, wrap_back=False):
        """Сосед текущего трека в порядке, в котором список показан на экране (сортировка коллекции/плейлиста,
        фильтр, поиск — yamusic_theme._remember_order); без такого порядка — по номеру. -1 — дальше нечего."""
        order = (self.__dict__.get("_view_order") or {}).get(ctx)
        if order and cur in order and all(0 <= i < n for i in order[:1]) and max(order) < n:
            pos = order.index(cur) + step
            if 0 <= pos < len(order):
                return order[pos]
            if self.repeat_mode == 1 or (wrap_back and pos < 0):
                return order[pos % len(order)]
            return -1
        idx = cur + step
        if idx >= n:
            return 0 if self.repeat_mode == 1 else -1
        if idx < 0:
            return (n - 1) if (self.repeat_mode == 1 or wrap_back) else -1
        return idx

    def _on_crossfade_started(self, next_path):
        """Вызывается, когда следующий трек реально стал звучать (фейд завершён)."""
        pend, self._pending_transition = getattr(self, "_pending_transition", None), None
        if pend and str(pend[1]) == str(next_path):
            if pend[0] == "queue":
                _, _p, t, qidx = pend
                while self.user_queue:                # снять из очереди всё до этого трека включительно
                    x = self.user_queue.pop(0)
                    if x is t or str(x.get("path", "")) == str(next_path):
                        break
                if not self._queued_now:
                    self._saved_ctx = (self.queue_context, self.current_index,
                                       list(self._shuffle_queue), self._shuffle_pos)
                self.queue_context = "library"
                self._queued_now = True
                self._crossfade_next_index = qidx
            elif pend[0] == "restore":
                idx_saved = self._crossfade_next_index
                self._restore_ctx()
                self._crossfade_next_index = idx_saved
        tracks = self.library if self.queue_context == "library" else \
                 self.playlists.get(self.queue_context, {}).get("tracks", [])
        idx = self._crossfade_next_index
        if idx is None or not (0 <= idx < len(tracks)) or str(tracks[idx].get("path", "")) != str(next_path):
            idx = next((i for i, t in enumerate(tracks) if str(t.get("path", "")) == str(next_path)), -1)
        if idx < 0:
            return
        self.current_index = idx
        self._crossfade_next_index = None
        self._track_finished_guard = False
        # КРИТИЧНО: без этого _shuffle_pos остаётся на позиции ПРЕДЫДУЩЕГО
        # трека, а current_index уже указывает на новый. Тогда следующий
        # _peek_next_path()/_advance() снова считают "следующий" от старой
        # позиции — и кроссфейд раз за разом переключает в один и тот же
        # трек по кругу (это и был баг с зависанием на одном треке).
        if self.shuffle:
            if idx in self._shuffle_queue:
                self._shuffle_pos = self._shuffle_queue.index(idx)
            else:
                self._shuffle_queue.insert(self._shuffle_pos + 1, idx)
                self._shuffle_pos += 1
        self._update_track_info(tracks[idx])
        QTimer.singleShot(0, lambda: self._update_discord_rpc())   # Discord — сразу, а не через 4 с
        self._apply_cover_theme(tracks[idx].get("cover", ""))
        self._load_lyrics()
        self._clip_track_changed()
        self._record_play_history(tracks[idx].get("path", ""))
        self.stats.record_play(tracks[idx])
        QTimer.singleShot(0, self._preload_adjacent)



    def _on_engine_state(self, playing):
        self._set_playing_ui(bool(playing))

    def _on_engine_error(self, text):
        """VLC не смог играть дальше. Раньше это только печаталось в консоль — трек молча замирал, и помогало
        только «назад» + «вперёд». Онлайн-трек: новая ссылка и продолжение с того же места (до 2 раз);
        иначе — следующий трек."""
        print("[audio]", text)
        if self.current_index < 0:
            return
        t = self._current_track() or {}
        path = str(t.get("path", ""))
        if not path or path != str(self.engine.current_path):
            return
        if self._resume_stream(t, "Поток оборвался — переподключаю…"):
            return
        self._toast(f"Не удалось воспроизвести «{sanitize_title(t.get('title', '')) or Path(path).name}» — следующий трек")
        QTimer.singleShot(300, lambda p=path: self._advance(1) if str(self.engine.current_path) == p else None)

    def _resume_stream(self, t, note) -> bool:
        """Онлайн-трек оборвался: свежая ссылка, продолжить с того места, где оборвалось. False — не поток
        или уже пробовали дважды."""
        path = str(t.get("path", ""))
        if not path.startswith("stream:"):
            return False
        tries = self.__dict__.setdefault("_stream_retries", {})
        if tries.get(path, 0) >= 2:
            tries.pop(path, None)
            return False
        tries[path] = tries.get(path, 0) + 1
        at_path, at = getattr(self, "_heard_at", ("", 0.0))
        at = max(0.0, at - 1.0) if at_path == path else 0.0
        self.streams.forget(path)
        self._toast(note)
        token = self._stream_token

        def done(ok, _data):
            if token != self._stream_token or str(self.engine.current_path) != path:
                return                                   # пока ждали, включили другой трек
            if ok:
                self.engine.load(path, autoplay=True, start_sec=at)
            else:
                tries.pop(path, None)
                self._advance(1)
        self.streams.resolve(t, done, urgent=True)
        return True

    def _on_engine_finished(self):
        if self.current_index < 0 or self._track_finished_guard:
            return
        t = self._current_track() or {}
        at_path, at = getattr(self, "_heard_at", ("", 0.0))
        full = float(self.engine.duration or 0.0) or float(t.get("duration") or 0.0)   # длина потока у VLC точнее каталога
        # мёртвая ссылка (403) у VLC — не ошибка, а мгновенный «конец»: тоже переподключаем
        if (str(t.get("path", "")).startswith("stream:") and at_path == str(t.get("path")) and self.repeat_mode != 2
                and ((full > 30 and at < full - 8) or at < 2.0)):
            # поток кончился раньше трека (обрыв сети / истекла ссылка) — не прыгать на следующий
            if self._resume_stream(t, "Поток прервался — продолжаю с того же места…"):
                return
        else:
            self.__dict__.get("_stream_retries", {}).pop(str(t.get("path", "")), None)
        if getattr(self,'_duel_preview',None) == str((self._current_track() or {}).get('path','')):
            self.engine.stop();self._set_playing_ui(False)
            self._duel_preview=None
            return
        tools = getattr(self, '_listening_tools', None)
        if tools and tools.consume_stop():
            return
        self._track_finished_guard = True
        try:
            if self.repeat_mode == 2:
                self.engine.load(self.engine.current_path, autoplay=True, start_sec=0.0)
            else:
                self._advance(1)
        finally:
            self._track_finished_guard = False

    def _update_progress(self):
        # Fallback refresh in case a backend misses a positionChanged signal.
        if self.current_index < 0:
            return
        try:
            tr = self.library if self.queue_context == "library" else \
                self.playlists.get(self.queue_context, {}).get("tracks", [])
            self.stats.tick(tr[self.current_index] if 0 <= self.current_index < len(tr) else None,
                            bool(self.engine.is_playing()))
        except Exception:                            # noqa: BLE001
            pass
        self._on_engine_position(self.engine.get_position())

    def _open_profile(self):
        """Единый полный профиль: внутри Echoes Music или в окне «Музыка»."""
        for shell in (getattr(self, "_ya", None), getattr(getattr(self, "_hub", None), "shell", None)):
            if shell is not None and shell.isVisible() and "profile" in getattr(shell, "pages", {}):
                shell.show_page("profile")
                return
        self._open_hub("profile")

    def _edit_profile_then_refresh(self):
        if not self._edit_profile():
            return
        for shell in (getattr(self, "_ya", None), getattr(getattr(self, "_hub", None), "shell", None)):
            if shell is not None:
                try:
                    shell.refresh_sidebar()
                    if shell._cur_page == "profile":
                        shell.pages["profile"].refresh()
                    if "net" in shell.pages:
                        shell.pages["net"].on_profile_changed()
                except Exception as e:               # noqa: BLE001
                    print("[profile]", e)

    @staticmethod
    def _fmt(sec):
        sec=max(0,int(sec)); return f"{sec//60:02d}:{sec%60:02d}"

    def _build_shuffle_queue(self):
        """Строит перемешанную очередь из всех треков текущего контекста.
        Текущий трек идёт первым, остальные — рандомно после него.
        Вызывается при включении шафла или смене контекста воспроизведения."""
        tracks = self.library if self.queue_context == "library" else \
                 self.playlists.get(self.queue_context, {}).get("tracks", [])
        n = len(tracks)
        if n == 0:
            self._shuffle_queue = []
            self._shuffle_pos = -1
            return
        indices = list(range(n))
        if self.current_index in indices:
            indices.remove(self.current_index)
            random.shuffle(indices)
            self._shuffle_queue = [self.current_index] + indices
            self._shuffle_pos = 0
        else:
            random.shuffle(indices)
            self._shuffle_queue = indices
            self._shuffle_pos = -1

    def _toggle_shuffle(self,checked):
        self.shuffle=bool(checked)
        self.btn_shuffle.setText("Shuffle")
        self.btn_shuffle.setToolTip("Случайный порядок: включен" if self.shuffle else "Случайный порядок: выключен")
        if self.shuffle:
            self._build_shuffle_queue()
        else:
            self._shuffle_queue = []
            self._shuffle_pos = -1
        self._preload_adjacent()

    # ── Шаффл по исполнителю (как «Волна по исполнителю» в Echoes Music) ── #

    ARTIST_PL = HIDDEN_PL + "wave"   # временная очередь, не пользовательский плейлист

    @staticmethod
    def _artist_names(a) -> list:
        """Все исполнители строки «A, B & C feat. D» — первым основной."""
        from artist_identity import split
        return split(a)

    def _artist_counts(self) -> dict:
        from artist_identity import index_for
        idx = index_for(self.library)                    # разные написания одного исполнителя — вместе
        cnt = {}
        for t in self.library:
            names = self._artist_names(t.get("artist"))
            if names:
                n = idx.display(names[0])
                cnt[n] = cnt.get(n, 0) + 1
        return cnt

    def artist_shuffle(self, artist=None):
        """Все треки исполнителя (и где он на фите) вперемешку. Без имени — исполнитель текущего трека;
        если ничего не играет — меню выбора."""
        cur = self._current_track()
        if not artist:
            names = self._artist_names((cur or {}).get("artist"))
            artist = names[0] if names else ""
        if not artist:
            self.artist_shuffle_menu()
            return
        from artist_identity import index_for, credits
        idx = index_for(self.library)
        key = idx.ident(artist)                          # любое написание имени, и где он на фите
        seen, pool = set(), []
        for t in self.library:
            p = str(t.get("path", ""))
            if p in seen:
                continue
            if any(idx.ident(n) == key for n in credits(t)):
                seen.add(p)
                pool.append(t)
        if not pool:
            self._toast(f"В библиотеке нет треков исполнителя {artist}")
            return
        random.shuffle(pool)
        # без двух одинаковых треков подряд (дубли разных версий) — уже убраны по пути; текущий трек
        # исполнителя не прерываем: он становится первым в подборке и доигрывает
        playing = False
        try:
            playing = bool(self.engine.is_playing())
        except Exception:                                      # noqa: BLE001
            pass
        keep = None
        if cur is not None and str(cur.get("path", "")) in seen and playing:
            keep = next(t for t in pool if str(t.get("path", "")) == str(cur.get("path", "")))
            pool.remove(keep)
            pool.insert(0, keep)
        self.playlists[self.ARTIST_PL] = {"tracks": pool, "desc": f"auto: {artist}", "cover": ""}
        self._ya_save_playlists()
        if keep is not None:
            self._saved_ctx = None
            self._queued_now = False
            self.queue_context, self.current_index = self.ARTIST_PL, 0
            if self.shuffle:
                self._build_shuffle_queue()
            try:
                self._preload_adjacent()
            except Exception:                                  # noqa: BLE001
                pass
        else:
            self._play_index(0, self.ARTIST_PL)
        ya = getattr(self, "_ya", None)
        try:
            if ya is not None and hasattr(ya, "wave"):
                ya._wave_kind = ("artist", artist)
                ya.wave.set_mood(artist, "artist", artist)
        except Exception:                                      # noqa: BLE001
            pass
        self._toast(f"Шаффл по исполнителю: {artist} · {len(pool)}")

    def artist_shuffle_menu(self, pos=None):
        """Выбор исполнителя для шаффла: текущий сверху, дальше — самые большие по числу треков."""
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QCursor
        m = QMenu(self)
        cnt = self._artist_counts()
        cur = self._artist_names((self._current_track() or {}).get("artist"))
        if cur:
            m.addAction(f"Шаффл: {cur[0]}", lambda a=cur[0]: self.artist_shuffle(a))
            m.addSeparator()
        top = sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0].casefold()))
        for a, n in top[:30]:
            m.addAction(f"{a}  ·  {n}", lambda a=a: self.artist_shuffle(a))
        if len(top) > 30:
            sub = m.addMenu("Все исполнители")
            for a, n in sorted(top, key=lambda kv: kv[0].casefold()):
                sub.addAction(f"{a}  ·  {n}", lambda a=a: self.artist_shuffle(a))
        if not top:
            act = m.addAction("Библиотека пуста")
            act.setEnabled(False)
        m.exec(pos or QCursor.pos())

    def _wa_repeat_text(self):
        self.btn_repeat.setText({0: "REP", 1: "REP ∞", 2: "REP 1"}[self.repeat_mode])

    def _cycle_repeat_labels(self):
        if getattr(self, "_wa_on", False):
            self._wa_repeat_text()
        else:
            self.btn_repeat.setText({0: "Repeat", 1: "Repeat All", 2: "Repeat 1"}[self.repeat_mode])

    def _cycle_repeat(self):
        # Three stable states: OFF -> ALL -> ONE -> OFF.
        self.repeat_mode=(self.repeat_mode+1)%3
        labels = {0:"REP", 1:"REP ∞", 2:"REP 1"} if getattr(self, "_wa_on", False) else \
                 {0:"Repeat", 1:"Repeat All", 2:"Repeat 1"}
        tips = {0:"Повтор выключен",1:"Повтор всего плейлиста",2:"Повтор текущего трека"}
        self.btn_repeat.setText(labels[self.repeat_mode])
        self.btn_repeat.setToolTip(tips[self.repeat_mode])
        self.btn_repeat.setChecked(self.repeat_mode != 0) if self.btn_repeat.isCheckable() else None
        self.btn_repeat.setProperty("repeatActive", self.repeat_mode != 0)
        self.btn_repeat.style().unpolish(self.btn_repeat)
        self.btn_repeat.style().polish(self.btn_repeat)

    def _volume_changed(self,v):
        self.engine.set_volume(v/100)
        self.settings["volume"] = v
        self._schedule_settings_save()

    # ── Экстремальная громкость ────────────────────────────────────── #
    BOOST_PRESETS = (100, 200, 500, 1000, 2000, 5000, 10000)

    def _make_boost_block(self, compact=False) -> QWidget:
        """Блок «Экстремальная громкость»: множитель поверх ползунка громкости,
        100 %…10 000 %. Можно создать сколько угодно копий (каждая тема
        показывает свою) — значение у всех общее и синхронизируется."""
        box = QWidget(); box.setObjectName("BoostBlock")
        box.setStyleSheet("QWidget#BoostBlock{background:transparent;}")
        v = QVBoxLayout(box); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(6)
        if not compact:
            sec = QLabel("Мощность звука"); sec.setObjectName("Section"); v.addWidget(sec)
        spin = QSpinBox()
        spin.setRange(100, 10000); spin.setSingleStep(50); spin.setSuffix(" %")
        spin.setAccelerated(True)
        spin.setMinimumWidth(0)
        spin.setToolTip(
            "Экстремальная громкость — множитель поверх ползунка:\n"
            "100 % — обычная громкость, 500 % — в 5 раз громче, 10 000 % — в 100 раз.\n"
            "На больших значениях звук упирается в потолок и начинает перегружаться —\n"
            "это нормально, так и задумано. Береги уши и колонки.")
        spin.valueChanged.connect(lambda val: self._set_boost_percent(val))
        v.addWidget(spin)
        grid = QGridLayout(); grid.setSpacing(4)
        cols = 4 if compact else 2
        btns = {}
        for i, pct in enumerate(self.BOOST_PRESETS):
            b = QPushButton(f"{pct} %"); b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setMinimumWidth(0)
            b.setToolTip("Обычная громкость" if pct == 100 else f"Громкость ×{pct // 100}")
            b.clicked.connect(lambda _=False, p=pct: self._set_boost_percent(p))
            grid.addWidget(b, i // cols, i % cols)
            btns[pct] = b
        v.addLayout(grid)
        lbl = QLabel(""); lbl.setObjectName("Sub"); lbl.setWordWrap(True)
        v.addWidget(lbl)
        self.__dict__.setdefault("_boost_blocks", []).append((spin, btns, lbl))
        self._sync_boost_blocks()
        return box

    def _on_language_changed(self, idx):
        code = self.lang_cb.itemData(idx) or "ru"
        if code == self.settings.get("language", "ru"):
            return
        self.settings["language"] = code
        save_json(SETTINGS_FILE, self.settings)
        import i18n
        i18n.change_language(code,self)

    def _restart_app(self):
        from PyQt6.QtCore import QProcess
        self._really_quit = True                         # не в трей — по-настоящему закрыться
        try:
            self.close()
        finally:
            QProcess.startDetached(sys.executable, sys.argv)
            QApplication.instance().quit()

    def _boost_menu(self, global_pos):
        """Всплывающее меню экстремальной громкости (кнопка «ГРОМК+» в Winamp)."""
        menu = QMenu(self)
        menu.addSection("Экстремальная громкость")
        cur = self._boost_percent()
        for pct in self.BOOST_PRESETS:
            act = menu.addAction("Обычная (100 %)" if pct == 100 else f"{pct} %  (×{pct // 100})")
            act.setCheckable(True)
            act.setChecked(pct == cur)
            act.triggered.connect(lambda _=False, p=pct: self._set_boost_percent(p))
        menu.addSeparator()
        act = menu.addAction("Своё значение…")
        def custom():
            val, ok = QInputDialog.getInt(self, "Экстремальная громкость",
                                          "Громкость в процентах (100–10000):", cur, 100, 10000, 50)
            if ok:
                self._set_boost_percent(val)
        act.triggered.connect(custom)
        menu.exec(global_pos)

    def _boost_percent(self) -> int:
        return int(round(float(self.settings.get("vol_boost", 1.0)) * 100))

    def _set_boost_percent(self, pct):
        pct = max(100, min(10000, int(pct)))
        self.engine.set_boost(pct / 100.0)
        if pct != self._boost_percent():
            self.settings["vol_boost"] = pct / 100.0
            self._schedule_settings_save()
        self._sync_boost_blocks()

    def _sync_boost_blocks(self):
        pct = self._boost_percent()
        if pct >= 5000:
            hint = "Аномальная громкость — перегруз гарантирован"
        elif pct >= 1000:
            hint = "Очень громко: возможен перегруз"
        elif pct > 100:
            hint = f"Громче обычного в {pct / 100:g} раз"
        else:
            hint = "Обычная громкость"
        alive = []
        for spin, btns, lbl in self.__dict__.get("_boost_blocks", []):
            try:
                spin.blockSignals(True); spin.setValue(pct); spin.blockSignals(False)
                for p_, b in btns.items():
                    b.setChecked(p_ == pct)
                lbl.setText(hint)
                alive.append((spin, btns, lbl))
            except RuntimeError:                         # виджет удалён вместе с темой
                pass
        self._boost_blocks = alive

    def set_play_speed(self, rate: float):
        """Скорость трека 0.25×…4× (панель «Звук» → «Экстремальная скорость»): темп и тон вместе."""
        v = int(round(max(0.25, min(4.0, float(rate))) * 100))
        if self.speed.value() == v:
            self._on_speed_changed(v)
        else:
            self.speed.setValue(v)                      # → _on_speed_changed (снимает пресеты, сохраняет)

    def play_speed(self) -> float:
        return float(getattr(self.engine, "speed", 1.0) or 1.0)

    def _on_speed_changed(self, v):
        self.engine.set_speed(v / 100)
        self.speed_lbl.setText(f"{v / 100:.2f}×")
        self.settings["speed"] = v
        self._schedule_settings_save()
        # Ручное движение слайдера снимает активный пресет
        if self.engine.preset_mode is not None:
            prev_mode = self.engine.preset_mode
            self.engine.preset_mode = None
            self.engine.preset_factor = 1.0
            self.engine._cleanup_preset_temp()
            if hasattr(self, "_btn_slowed"):
                self._btn_slowed.blockSignals(True)
                self._btn_slowed.setChecked(False)
                self._btn_slowed.setEnabled(True)
                self._btn_slowed.blockSignals(False)
            if hasattr(self, "_btn_speedup"):
                self._btn_speedup.blockSignals(True)
                self._btn_speedup.setChecked(False)
                self._btn_speedup.setEnabled(True)
                self._btn_speedup.blockSignals(False)
            if hasattr(self, "_btn_8d"):
                self._btn_8d.blockSignals(True)
                self._btn_8d.setChecked(False)
                self._btn_8d.setEnabled(True)
                self._btn_8d.blockSignals(False)
            if hasattr(self, "_preset_status_lbl"):
                self._preset_status_lbl.hide()
            # Если был slowed — temp файл уже удалён, перезагружаем оригинал
            if prev_mode in ("slowed", "8d"):
                t_list = self.library if self.queue_context == "library" \
                    else self.playlists.get(self.queue_context, {}).get("tracks", [])
                if 0 <= self.current_index < len(t_list):
                    orig = str(t_list[self.current_index].get("path", ""))
                    resume = self.engine.get_position()
                    self.engine.load(orig, autoplay=True)
                    if resume > 1.0:
                        QTimer.singleShot(200, lambda p=resume: self.engine.seek(p))
                # Применяем новую скорость после перезагрузки
                QTimer.singleShot(250, lambda: self.engine.set_speed(v / 100))

    def _on_own_output_toggled(self, state):
        self.settings["own_audio_output"] = bool(state)
        save_json(SETTINGS_FILE, self.settings)
        self._toast("Аудиовывод сменится после перезапуска плеера")

    def _on_crossfade_toggled(self, state):
        enabled = bool(state)
        self.engine.crossfade_enabled = enabled
        self.crossfade_slider.setEnabled(enabled)
        if hasattr(self, "dj_cb"):
            self.dj_cb.setEnabled(enabled)
        self.settings["crossfade"] = enabled
        save_json(SETTINGS_FILE, self.settings)

    @staticmethod
    def _fmt_crossfade_ms(ms: int) -> str:
        if ms <= 0:
            return "0"
        s = ms / 1000.0
        return f"{s:.2f}с" if s < 1.0 else f"{s:.1f}с"

    def _on_crossfade_ms_changed(self, v):
        self.engine.crossfade_ms = int(v)
        self.crossfade_ms_lbl.setText(self._fmt_crossfade_ms(v))
        self.settings["crossfade_ms"] = int(v)
        self._schedule_settings_save()

    # ── выравнивание громкости ── #

    def _loud_enabled(self) -> bool:
        return bool(self.settings.get("loudness_norm", True))

    def _loud_gain(self, path) -> float:
        """Коэффициент громкости трека для движка (1.0, пока трек не измерен)."""
        if not self._loud_enabled():
            return 1.0
        path = str(path)
        if self.loudness.get(path) is None:
            if any(str(t.get("path", "")) == path for t in self.library):      # не временные файлы пресетов
                self.loudness.request(path, urgent=True)
            return 1.0
        return self.loudness.linear_gain(path)

    def _loud_ready(self, path):
        """Измерение закончилось (рабочий поток) — подстроить играющий трек."""
        self._ui_bridge.call.emit(lambda: self._loud_apply(path))

    def _loud_apply(self, path):
        if self._loud_enabled() and str(self.engine.current_path or "") == str(path):
            self.engine.set_gain(self._loud_gain(path))

    def _loud_scan(self):
        if self._loud_enabled():
            self.loudness.request_many([str(t.get("path", "")) for t in self.library if t.get("path")])

    def _warm_studio(self):
        """Первый вход в Echoes Studio импортировал scipy.signal на главном потоке — окно висело
        2–3 с. Если студией уже пользовались (есть проекты), модули грузятся заранее в фоне."""
        if "daw_dsp" in sys.modules or getattr(self, "_daw_on", False):
            return
        try:
            proj = data_home.root() / "studio" / "projects"
            if not proj.is_dir() or not any(proj.iterdir()):
                return
        except OSError:
            return
        import threading

        def work():
            try:
                import daw_dsp  # noqa: F401
                import daw_engine  # noqa: F401
                import daw_fx  # noqa: F401
            except Exception as e:                       # noqa: BLE001
                print("[studio] warm:", e)
        threading.Thread(target=work, daemon=True, name="studio-warm").start()

    def save_settings(self):
        timer = self.__dict__.get("_settings_save_timer")
        if timer is not None:
            timer.stop()
        save_json(SETTINGS_FILE, self.settings)

    def _schedule_settings_save(self):
        """Apply controls immediately; persist once after the gesture settles."""
        timer = self.__dict__.get("_settings_save_timer")
        if timer is None:
            timer = self._settings_save_timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(350)
            timer.timeout.connect(self.save_settings)
        timer.start()

    def _on_inapp_toggled(self, state):
        self.settings["inapp_dialogs"] = bool(state)
        save_json(SETTINGS_FILE, self.settings)
        inapp.set_enabled(bool(state))

    def _on_ui_anim_toggled(self, state):
        """Анимации интерфейса вкл/выкл (ui_anim): сохраняется сразу, меню и подсказки — тоже."""
        self.settings["ui_animations"] = bool(state)
        self.save_settings()
        try:
            import ui_anim
            ui_anim.install_effects(self)
        except Exception as e:                       # noqa: BLE001
            print("[ui_anim]", e)

    def _on_titlebar_toggled(self, state):
        self.settings["custom_titlebar"] = bool(state)
        save_json(SETTINGS_FILE, self.settings)
        self._toast("Заголовок окна изменится после перезапуска плеера")

    def _on_loud_toggled(self, state):
        self.settings["loudness_norm"] = bool(state)
        save_json(SETTINGS_FILE, self.settings)
        cur = self.engine.current_path
        if cur:
            self.engine.set_gain(self._loud_gain(cur) if state else 1.0)
        if state:
            self._loud_scan()
        self._toast("Выравнивание громкости включено" if state else "Выравнивание громкости выключено")

    def _on_gapless_toggled(self, state):
        enabled = bool(state)
        self.engine.gapless_enabled = enabled
        self.settings["gapless"] = enabled
        save_json(SETTINGS_FILE, self.settings)

    def _new_playlist(self):
        name,ok=QInputDialog.getText(self,"Новый плейлист","Название:")
        name=name.strip()
        if not ok or not name:return
        if name in self.playlists:
            QMessageBox.information(self,"Плейлист уже существует","Выбери другое название."); return
        self.playlists[name]={"tracks":[],"desc":"","cover":""}; save_json(PL_FILE,self.playlists); self._refresh_playlists()

    def _add_current_to_playlist(self):
        if self.current_index<0:return
        names=list(self.playlists)
        if not names:
            QMessageBox.information(self,"Нет плейлистов","Сначала создай плейлист."); return
        name,ok=QInputDialog.getItem(self,"Добавить в плейлист","Плейлист:",names,0,False)
        if not ok:return
        tracks=self.library if self.queue_context=="library" else self.playlists[self.queue_context]["tracks"]
        self.playlists[name]["tracks"].append(dict(tracks[self.current_index]))
        save_json(PL_FILE,self.playlists); self._refresh_playlists()

    def _add_selected_to_playlist(self):
        selected = self.lib_list.selectedItems()
        if not selected:
            QMessageBox.information(self, "Нет выбранных треков", "Выдели один или несколько треков в библиотеке (Ctrl/Shift для нескольких).")
            return
        names=list(self.playlists)
        if not names:
            QMessageBox.information(self,"Нет плейлистов","Сначала создай плейлист.")
            return
        name,ok=QInputDialog.getItem(self,"Добавить выбранные треки","Плейлист:",names,0,False)
        if not ok:return
        playlist=self.playlists[name]
        existing={str(t.get("path","")) for t in playlist.get("tracks",[])}
        added=0
        for item in selected:
            track=item.data(Qt.ItemDataRole.UserRole)
            if not track: continue
            path=str(track.get("path",""))
            if path and path not in existing:
                playlist.setdefault("tracks",[]).append(dict(track))
                existing.add(path); added += 1
        save_json(PL_FILE,self.playlists)
        self._refresh_playlists()
        self._load_playlist_editor(name)
        QMessageBox.information(self,"Готово",f"Добавлено треков: {added}" + ("\nДубликаты пропущены." if added < len(selected) else ""))

    def _on_playlist_tab_changed(self, index):
        # Вкладка «Редактор» удалена — редактирование живёт внутри
        # страницы плейлиста (PlaylistDetailView) через drag&drop и ПКМ.
        pass

    def _load_playlist_editor(self, name):
        if not hasattr(self, "pl_edit_list"): return
        self.pl_edit_list.blockSignals(True)
        self.pl_edit_list.clear()
        tracks=self.playlists.get(name,{}).get("tracks",[]) if name else []
        for i,t in enumerate(tracks):
            artist=t.get("artist") or "Unknown artist"
            item=QListWidgetItem(f"{i+1:02d}. {t.get('title','Untitled')}  ·  {artist}")
            item.setData(Qt.ItemDataRole.UserRole, t.get("path",""))
            self.pl_edit_list.addItem(item)
        self.pl_edit_list.blockSignals(False)

    def _save_playlist_editor_order(self):
        name=self.pl_editor_combo.currentText()
        if not name or name not in self.playlists: return
        by_path={str(t.get("path","")):t for t in self.playlists[name].get("tracks",[])}
        ordered=[]
        for i in range(self.pl_edit_list.count()):
            path=str(self.pl_edit_list.item(i).data(Qt.ItemDataRole.UserRole) or "")
            if path in by_path:
                ordered.append(by_path[path])
        self.playlists[name]["tracks"]=ordered
        save_json(PL_FILE,self.playlists)
        self._refresh_playlists()
        self._renumber_editor_items()

    def _renumber_editor_items(self):
        for i in range(self.pl_edit_list.count()):
            item=self.pl_edit_list.item(i)
            path=item.data(Qt.ItemDataRole.UserRole)
            track=next((t for t in self.playlists.get(self.pl_editor_combo.currentText(),{}).get("tracks",[]) if str(t.get("path",""))==str(path)), None)
            if track:
                artist=track.get("artist") or "Unknown artist"
                item.setText(f"{i+1:02d}. {track.get('title','Untitled')}  ·  {artist}")

    def _move_editor_track(self, direction):
        row=self.pl_edit_list.currentRow()
        target=row+direction
        if row < 0 or target < 0 or target >= self.pl_edit_list.count(): return
        item=self.pl_edit_list.takeItem(row)
        self.pl_edit_list.insertItem(target,item)
        self.pl_edit_list.setCurrentRow(target)
        self._save_playlist_editor_order()

    def _remove_editor_track(self):
        rows = sorted({idx.row() for idx in self.pl_edit_list.selectedIndexes()}, reverse=True)
        if not rows:
            row = self.pl_edit_list.currentRow()
            if row < 0: return
            rows = [row]
        name=self.pl_editor_combo.currentText()
        tracks=self.playlists.get(name,{}).get("tracks",[])
        for row in rows:
            if 0 <= row < len(tracks):
                del tracks[row]
        save_json(PL_FILE,self.playlists)
        self._refresh_playlists()
        self._load_playlist_editor(name)

    def _refresh_playlists(self):
        QTimer.singleShot(0, self._wa_refresh_playlist)
        self.pl_list.clear()
        if not self.playlists:
            it = QListWidgetItem("Плейлистов пока нет —\nнажмите «＋ Новый плейлист»")
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.pl_list.addItem(it)
        for name,pl in self.playlists.items():
            item=QListWidgetItem(f"{name}  ({len(pl.get('tracks',[]))})")
            item.setData(Qt.ItemDataRole.UserRole,name)
            self._set_lazy_icon(item, pl.get("cover", ""))
            self.pl_list.addItem(item)
        self._lazy_icons_kick(self.pl_list, 144, 36)
        if hasattr(self, "pl_editor_combo"):
            current=self.pl_editor_combo.currentText()
            self.pl_editor_combo.blockSignals(True)
            self.pl_editor_combo.clear()
            self.pl_editor_combo.addItems(list(self.playlists))
            if current in self.playlists:
                self.pl_editor_combo.setCurrentText(current)
            self.pl_editor_combo.blockSignals(False)
            if self.pl_editor_combo.currentText():
                self._load_playlist_editor(self.pl_editor_combo.currentText())
        # Если сейчас открыта страница плейлиста — перерисовать её
        # (обложка/трек-лист/порядок могли поменяться), либо закрыть,
        # если плейлист исчез (переименован/удалён из другого места).
        if self._playlist_detail_open:
            if self._playlist_detail_name in self.playlists:
                self._render_playlist_detail(self._playlist_detail_name)
            else:
                self._close_playlist_detail()

    def _play_playlist(self,item):
        name=item.data(Qt.ItemDataRole.UserRole); pl=self.playlists.get(name,{})
        if pl.get("tracks"): self._play_index(0,name)

    # ------------------------------------------------------------------ #
    #  Spotify-style страница плейлиста                                   #
    # ------------------------------------------------------------------ #

    def _open_playlist_detail(self, item):
        name = item.data(Qt.ItemDataRole.UserRole)
        if not name or name not in self.playlists:
            return
        if self._lyrics_mode:
            self._toggle_lyrics_mode()
        self._playlist_detail_open = True
        self._render_playlist_detail(name)
        self._normal_widget.hide()
        if not getattr(self, "_wa_on", False):    # в Winamp транспорт живёт в главном окне
            self.transport_bar.hide()
        self.playlist_detail.show()

    def _close_playlist_detail(self):
        if not self._playlist_detail_open:
            return
        self._playlist_detail_open = False
        self._playlist_detail_name = None
        self.playlist_detail.hide()
        self._normal_widget.show()
        self.transport_bar.show()

    def _render_playlist_detail(self, name):
        pl = self.playlists.get(name)
        if not pl:
            self._close_playlist_detail()
            return
        self._playlist_detail_name = name
        tracks = pl.get("tracks", [])
        cover_path = pl.get("cover", "")
        cover_path = cover_path if cover_path and Path(cover_path).exists() else ""
        top, bottom = self._pd_header_colors(cover_path)
        pixmap = self._round_pixmap(load_pixmap(cover_path, 480), 120) if cover_path else self._placeholder_cover(120)
        current_path = None
        if self.queue_context == name and 0 <= self.current_index < len(tracks):
            current_path = str(tracks[self.current_index].get("path", ""))
        self.playlist_detail.render(
            name=name,
            tracks=tracks,
            cover_pixmap=pixmap,
            description=pl.get("desc", ""),
            author=self.profile.get("nickname", "user"),
            top_color=top,
            bottom_color=bottom,
            current_path=current_path,
            icon_cache=self._icon_cache,
            placeholder_cover_fn=self._placeholder_cover,
            round_pixmap_fn=self._round_pixmap,
        )

    def _pd_header_colors(self, cover_path):
        """Верхний цвет фейда — из обложки плейлиста (если есть), нижний —
        фон текущей темы. Не трогает глобальную тему приложения — это
        отдельный, локальный для страницы плейлиста, эффект."""
        theme = THEMES.get(self._manual_theme_name) or next(iter(THEMES.values()))
        bottom = QColor(theme["panel"])
        top = QColor(theme["accent"])
        if cover_path:
            data = self._cover_theme(cover_path)
            if data:
                top = QColor(data.get("accent", theme["accent"]))
        return top, bottom

    def _placeholder_cover(self, size):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, size, size, size * 0.30, size * 0.30)
        p.setClipPath(path)
        p.fillRect(0, 0, size, size, QColor(30, 32, 40))
        # вместо символа-ноты — простая «пластинка» из колец
        p.setPen(QColor(110, 114, 128))
        p.setBrush(Qt.BrushStyle.NoBrush)
        c = size / 2.0
        for rr in (0.30, 0.22, 0.14):
            p.drawEllipse(QRectF(c - size * rr, c - size * rr, size * rr * 2, size * rr * 2))
        p.setBrush(QColor(110, 114, 128))
        p.drawEllipse(QRectF(c - size * 0.04, c - size * 0.04, size * 0.08, size * 0.08))
        p.end()
        return pm

    def _pd_play(self, name):
        pl = self.playlists.get(name)
        if pl and pl.get("tracks"):
            self._play_index(0, name)

    def _pd_shuffle_play(self, name):
        pl = self.playlists.get(name)
        if not pl or not pl.get("tracks"):
            return
        if not self.shuffle:
            self.btn_shuffle.setChecked(True)
            self._toggle_shuffle(True)
        self._play_index(0, name)

    def _pd_track_activated(self, name, row):
        tracks = self.playlists.get(name, {}).get("tracks", [])
        if 0 <= row < len(tracks):
            # _play_index сам обновит подсветку текущего трека на странице
            self._play_index(row, name)

    def _pd_set_cover(self, name):
        if not name or name not in self.playlists:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Обложка плейлиста", "", "Изображения (*.png *.jpg *.jpeg *.webp)"
        )
        if not path:
            return
        ext = Path(path).suffix.lower() or ".jpg"
        dest = COVER_DIR / ("playlist_" + hashlib.sha1(name.encode("utf-8")).hexdigest() + ext)
        try:
            dest.write_bytes(Path(path).read_bytes())
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить обложку:\n{e}")
            return
        old_cover = self.playlists[name].get("cover", "")
        if old_cover and old_cover != str(dest):
            self._icon_cache.pop(old_cover, None)
            if Path(old_cover).exists():
                try: Path(old_cover).unlink()
                except Exception: pass
        self._icon_cache.pop(str(dest), None)
        self.playlists[name]["cover"] = str(dest)
        save_json(PL_FILE, self.playlists)
        self._refresh_playlists()

    def _pd_rename(self, name):
        if not name or name not in self.playlists:
            return
        new_name, ok = QInputDialog.getText(self, "Переименовать плейлист", "Название:", text=name)
        new_name = new_name.strip()
        if not ok or not new_name or new_name == name:
            return
        if new_name in self.playlists:
            QMessageBox.information(self, "Плейлист уже существует", "Выбери другое название.")
            return
        # dict сохраняет порядок вставки — пересобираем, чтобы плейлист
        # не "улетел" в конец списка при переименовании.
        self.playlists = {
            (new_name if k == name else k): v for k, v in self.playlists.items()
        }
        save_json(PL_FILE, self.playlists)
        if self.queue_context == name:
            self.queue_context = new_name
        if self._playlist_detail_name == name:
            self._playlist_detail_name = new_name
        for shell in (getattr(self, "_ya", None), getattr(getattr(self, "_hub", None), "shell", None)):
            try:
                if shell is not None and getattr(shell, "_pl_name", None) == name:
                    shell._pl_name = new_name
            except RuntimeError:
                pass
        self._refresh_playlists()
        self._notify_tracks_changed()

    def _pd_edit_description(self, name):
        if not name or name not in self.playlists:
            return
        desc, ok = QInputDialog.getMultiLineText(
            self, "Описание плейлиста", "Описание:", text=self.playlists[name].get("desc", "")
        )
        if not ok:
            return
        self.playlists[name]["desc"] = desc.strip()
        save_json(PL_FILE, self.playlists)
        self._refresh_playlists()

    def _pd_delete_playlist(self, name):
        if not name or name not in self.playlists:
            return
        if QMessageBox.question(
            self, "Удалить плейлист",
            f"Удалить плейлист «{name}»? Треки в библиотеке не удаляются."
        ) != QMessageBox.StandardButton.Yes:
            return
        cur = self._current_track() if self.queue_context == name else None
        del self.playlists[name]
        save_json(PL_FILE, self.playlists)
        if self.queue_context == name:
            self.queue_context = "library"
            if cur is not None:
                self._reindex_current(str(cur.get("path", "")))   # трек доигрывает из коллекции
            else:
                self.current_index = -1
        self._close_playlist_detail()
        self._refresh_playlists()
        self._notify_tracks_changed()

    def _pd_move(self, name, rows, delta):
        rows = sorted(rows)
        if not rows:
            return
        n = len(self._ctx_tracks(name))
        target = max(0, rows[0] + delta) if delta < 0 else min(n - len(rows), rows[0] + delta)
        new_rows = self.playlist_move(name, rows, target)
        if self._playlist_detail_open and self._playlist_detail_name == name:
            self.playlist_detail.select_rows(new_rows)

    def _pd_save_order(self, name):
        if not name or name not in self.playlists:
            return
        cur = self._current_track()
        cur_path = str(cur.get("path", "")) if cur else ""
        order_paths = self.playlist_detail.current_track_paths()
        by_path = {str(t.get("path", "")): t for t in self.playlists[name].get("tracks", [])}
        ordered = [by_path[p] for p in order_paths if p in by_path]
        # На случай гонки (данные поменялись пока страница открыта) —
        # не теряем треки, которых почему-то не было в списке на экране.
        seen = {str(t.get("path", "")) for t in ordered}
        for t in self.playlists[name].get("tracks", []):
            if str(t.get("path", "")) not in seen:
                ordered.append(t)
        self.playlists[name]["tracks"] = ordered
        if self.queue_context == name:
            self._reindex_current(cur_path)
        save_json(PL_FILE, self.playlists)
        self._refresh_playlists()
        self._notify_tracks_changed()

    def _pd_remove_tracks(self, name, rows):
        if not name or name not in self.playlists:
            return
        self.playlist_remove_rows(name, rows)

    def _new_playlist_menu(self):
        """«＋ Новый плейлист»: пустой, из файла (.echoesplaylist / .m3u / .txt) или из Spotify."""
        btn = getattr(self, "_btn_new_pl", None)
        m = QMenu(self)
        m.addAction("Пустой плейлист", self._new_playlist)
        m.addAction("Из файла (от друга)…", lambda: getattr(self, "import_playlist_file", lambda *_: None)())
        m.addAction("Из Spotify…", self._open_spotify_import)
        m.addSeparator()
        m.addAction("Перенести все плейлисты на телефон…",
                    lambda: getattr(self, "export_playlists_for_phone", lambda *_: None)())
        m.addSeparator()
        m.addAction("Куда класть файлы тем и плейлистов?", lambda: getattr(self, "files_help", lambda: None)())
        m.exec(btn.mapToGlobal(btn.rect().bottomLeft()) if btn is not None else self.mapToGlobal(self.rect().center()))

    def _playlist_context_menu(self, pos):
        item = self.pl_list.itemAt(pos)
        if not item:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        if not name:
            return
        menu = QMenu(self)
        act_open = menu.addAction("Открыть")
        act_play = menu.addAction("Играть")
        act_add = menu.addAction("＋  Добавить треки из коллекции…")
        menu.addSeparator()
        act_cover = menu.addAction("Обложка…")
        act_rename = menu.addAction("Переименовать")
        act_desc = menu.addAction("Описание…")
        act_share = menu.addAction("Поделиться файлом…")
        act_share.setToolTip("Маленький файл со списком треков — у друга недостающие скачаются сами")
        menu.addSeparator()
        act_delete = menu.addAction("Удалить плейлист")
        chosen = menu.exec(self.pl_list.mapToGlobal(pos))
        if chosen == act_share:
            getattr(self, "share_playlist", lambda *_: None)(name)
        elif chosen == act_add:
            self.pick_tracks_for_playlist(name)
        elif chosen == act_open:
            self._open_playlist_detail(item)
        elif chosen == act_play:
            self._play_playlist(item)
        elif chosen == act_cover:
            self._pd_set_cover(name)
        elif chosen == act_rename:
            self._pd_rename(name)
        elif chosen == act_desc:
            self._pd_edit_description(name)
        elif chosen == act_delete:
            self._pd_delete_playlist(name)

    def _auto_cover_theme(self,state):
        self.settings["auto_cover_theme"]=bool(state)
        save_json(SETTINGS_FILE,self.settings)
        if self.current_index >= 0:
            tracks = self.library if self.queue_context == "library" else self.playlists.get(self.queue_context,{}).get("tracks",[])
            if 0 <= self.current_index < len(tracks):
                cover = tracks[self.current_index].get("cover","")
                if not self._apply_cover_theme(cover):
                    self._apply_theme_data(THEMES.get(self._manual_theme_name) or next(iter(THEMES.values())), selector_name=self._manual_theme_name)

    def _set_token(self):
        token,ok=QInputDialog.getText(self,"Genius token","Access token:",text=self.settings.get("genius_token",""))
        if ok:self.settings["genius_token"]=token.strip(); save_json(SETTINGS_FILE,self.settings)

    def _set_discord_client_id(self):
        """Сохраняет Discord Application Client ID в настройки и прописывает в discord_rpc.py."""
        from pathlib import Path
        current_id = self.settings.get("discord_client_id", "")
        client_id, ok = QInputDialog.getText(
            self, "Discord Client ID",
            "Вставьте Application ID из Discord Developer Portal\n"
            "(discord.com/developers/applications → ваше приложение → Application ID):",
            text=current_id,
        )
        if not ok:
            return
        client_id = client_id.strip()
        self.settings["discord_client_id"] = client_id
        save_json(SETTINGS_FILE, self.settings)

        # Пробуем записать ID прямо в discord_rpc.py рядом с main.py
        rpc_path = Path(__file__).parent / "discord_rpc.py"
        if rpc_path.exists():
            try:
                text = rpc_path.read_text(encoding="utf-8")
                import re
                new_text = re.sub(
                    r'(CLIENT_ID\s*=\s*")[^"]*(")',
                    rf'\g<1>{client_id}\g<2>',
                    text,
                )
                if new_text != text:
                    rpc_path.write_text(new_text, encoding="utf-8")
            except Exception as e:
                print("[discord_rpc] Не удалось обновить discord_rpc.py:", e)

        # Перезапускаем RPC с новым ID если он уже работал
        if hasattr(self, "discord_rpc"):
            self.discord_rpc.stop()
            self.discord_rpc.client_id = client_id
            self.discord_rpc._enabled = bool(client_id) and client_id.strip("0") != ""
            if self.settings.get("discord_rpc", True):
                self.discord_rpc.start()

        msg = (
            "Client ID сохранён и записан в discord_rpc.py.\n\n"
            "Убедитесь, что Discord запущен — статус появится при следующем треке.\n\n"
            "Если статус не появляется:\n"
            "• В Developer Portal включите Rich Presence для вашего приложения\n"
            "• Загрузите хотя бы один Art Asset с ключом «vinyl» (Rich Presence → Art Assets)"
        ) if client_id else "Client ID очищен — Discord Rich Presence отключён."
        QMessageBox.information(self, "Discord Rich Presence", msg)

    def _discord_act_toggled(self, on):
        self.settings["discord_activities"] = bool(on)
        save_json(SETTINGS_FILE, self.settings)
        self._discord_drift()

    def _on_app_state(self, state):
        """Окно не в фокусе / свёрнуто — живые фоны, эффекты и анимации тем на паузе (звук играет)."""
        import frameclock
        off = state != Qt.ApplicationState.ApplicationActive and self.settings.get("pause_unfocused", True)
        # The shared clock also drives transport, lyrics and built-in themes.
        # Only constructor runtimes are suspended (see ThemeRuntime._tick).
        frameclock.set_paused(False)
        if off:
            try:
                import mem_trim
                mem_trim.trim_later(1500)
            except Exception:                              # noqa: BLE001
                pass

    def _open_stream_widget(self):
        """Отдельное окно «Сейчас играет» (обложка, трек, визуализатор) — для захвата окна в OBS / TikTok Studio."""
        import stream_widget
        w = getattr(self, "_stream_win", None)
        if w is None:
            w = self._stream_win = stream_widget.NowPlayingWindow(self)
        w.show(); w.raise_(); w.activateWindow()

    def _discord_icons_help(self):
        """Иконки студии / конструктора нужно один раз загрузить в Art Assets своего приложения Discord."""
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        folder = Path(__file__).parent / "discord_assets"
        cid = (getattr(self, "discord_rpc", None) and self.discord_rpc.client_id) or ""
        r = QMessageBox.question(
            self, "Иконки для Discord",
            "Discord показывает иконки активностей, только если они загружены в ваше приложение Discord.\n\n"
            "1. Откроется папка с иконками и страница Art Assets приложения.\n"
            "2. Нажмите «Add Image(s)» и загрузите studio.png и theme_studio.png.\n"
            "3. Имена (ключи) оставьте как у файлов: studio, theme_studio. Сохраните.\n\n"
            "Discord обновляет ассеты до 10 минут. Открыть?")
        if r != QMessageBox.StandardButton.Yes:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        QDesktopServices.openUrl(QUrl(f"https://discord.com/developers/applications/{cid}/rich-presence/assets"
                                      if cid else "https://discord.com/developers/applications"))

    def _discord_opt(self, key, on):
        self.settings[key] = bool(on)
        save_json(SETTINGS_FILE, self.settings)
        rpc = getattr(self, "discord_rpc", None)
        if rpc is not None:
            (rpc.set_online_covers if key == "discord_covers" else rpc.set_show_paused)(bool(on))

    def _on_discord_rpc_toggled(self, state):
        enabled = bool(state)
        self.settings["discord_rpc"] = enabled
        save_json(SETTINGS_FILE, self.settings)
        if hasattr(self, "discord_rpc"):
            self.discord_rpc.set_enabled(enabled)

    # ------------------------------------------------------------------ #
    #  Удаление треков из библиотеки / плейлиста                          #
    # ------------------------------------------------------------------ #

    def _lib_context_menu(self, pos):
        items = self.lib_list.selectedItems()
        if not items:
            it = self.lib_list.itemAt(pos)
            if it is None:
                return
            it.setSelected(True)
            items = [it]
        tracks = [it.data(Qt.ItemDataRole.UserRole) for it in items if it.data(Qt.ItemDataRole.UserRole)]
        if not tracks:
            return
        menu = QMenu(self)
        n = len(tracks)
        act_play = menu.addAction("Играть")
        act_tags = menu.addAction("Теги, обложка и текст…")
        self.reveal_action(menu, tracks[0])
        if hasattr(self, "export_effects"):
            menu.addAction("Экспорт с эффектами…" if n == 1 else f"Экспорт с эффектами ({n})…",
                           lambda: self.export_effects(tracks))
        sub = menu.addMenu(f"＋  Добавить в плейлист" + (f" ({n})" if n > 1 else ""))
        for name in self.playlists:
            sub.addAction(name, lambda nm=name: self.playlist_add_tracks(nm, tracks))
        sub.addSeparator()
        sub.addAction("Новый плейлист…", lambda: self._new_playlist_with(tracks))
        menu.addSeparator()
        act_del = menu.addAction(f"Удалить из плеера…" + (f" ({n})" if n > 1 else ""))
        chosen = menu.exec(self.lib_list.mapToGlobal(pos))
        if chosen == act_play:
            self._play_from_library(items[0])
        elif chosen == act_tags:
            self.edit_track_tags(tracks[0])
        elif chosen == act_del:
            self.remove_tracks_everywhere(tracks)

    def _save_playlists(self):
        save_json(PL_FILE, self.playlists)

    def _new_playlist_with(self, tracks):
        name, ok = QInputDialog.getText(self, "Новый плейлист", "Название:")
        name = (name or "").strip()
        if not ok or not name:
            return
        if name not in self.playlists:
            self.playlists[name] = {"tracks": [], "desc": "", "cover": ""}
        self.playlist_add_tracks(name, tracks)
        save_json(PL_FILE, self.playlists)
        self._refresh_playlists()

    def _delete_selected_library_tracks(self):
        items = self.lib_list.selectedItems()
        tracks = [it.data(Qt.ItemDataRole.UserRole) for it in items]
        self.remove_tracks_everywhere([t for t in tracks if t])

    def _pl_edit_context_menu(self, pos):
        if not self.pl_edit_list.selectedItems():
            return
        menu = QMenu(self)
        act = menu.addAction("Удалить из плейлиста")
        act.triggered.connect(self._remove_editor_track)
        menu.exec(self.pl_edit_list.mapToGlobal(pos))

    # ------------------------------------------------------------------ #
    #  Lo-Fi / Vinyl FX toggles                                           #
    # ------------------------------------------------------------------ #

    def _on_dust_toggled(self, state):
        enabled = bool(state)
        self.settings["fx_dust"] = enabled; save_json(SETTINGS_FILE, self.settings)
        if hasattr(self, "_dust"):
            self._dust.set_enabled(enabled)

    def _on_breathe_toggled(self, state):
        enabled = bool(state)
        self.settings["fx_breathe"] = enabled; save_json(SETTINGS_FILE, self.settings)
        if hasattr(self, "_ambience"):
            self._ambience.set_enabled(enabled)

    def _on_warp_toggled(self, state):
        enabled = bool(state)
        self.settings["vinyl_warp"] = enabled; save_json(SETTINGS_FILE, self.settings)
        self.engine.set_warp_enabled(enabled)

    def _on_pause_fx_toggled(self, state):
        enabled = bool(state)
        self.settings["vinyl_pause_fx"] = enabled; save_json(SETTINGS_FILE, self.settings)
        self.engine.vinyl_pause_fx = enabled

    # ------------------------------------------------------------------ #
    #  Атмосферный шум                                                     #
    # ------------------------------------------------------------------ #

    def _toggle_noise(self, checked):
        if checked:
            kind = self.noise_combo.currentData()
            self.noise_gen.play(kind, self.noise_vol.value())
            self.btn_noise.setText("Стоп")
        else:
            self.noise_gen.stop()
            self.btn_noise.setText("Пуск")

    def _on_noise_volume(self, v):
        self.noise_gen.set_volume(v)

    # ------------------------------------------------------------------ #
    #  Настроение дня: время суток + погода → авто-плейлист               #
    # ------------------------------------------------------------------ #

    def _set_weather_key(self):
        key, ok = QInputDialog.getText(
            self, "OpenWeatherMap",
            "API key (можно оставить пустым — тогда погода берётся с open-meteo.com без ключа):",
            text=self.settings.get("owm_key", "")
        )
        if not ok:
            return
        self.settings["owm_key"] = key.strip()
        city, ok = QInputDialog.getText(
            self, "Город", "Город (для погоды):", text=self.settings.get("owm_city", "Moscow")
        )
        if ok:
            self.settings["owm_city"] = city.strip() or "Moscow"
        key2, ok = QInputDialog.getText(
            self, "Last.fm (необязательно)",
            "API key Last.fm — даёт теги настроения (sad, chill, aggressive…)\n"
            "для точного «Настроения дня». Бесплатно: last.fm/api/account/create",
            text=self.settings.get("lastfm_key", ""))
        if ok:
            changed = key2.strip() != self.settings.get("lastfm_key", "")
            self.settings["lastfm_key"] = key2.strip()
            if changed and key2.strip() and self._intel_store() is not None:
                # перепроверить теги с новым ключом
                with self._intel.lock:
                    for m in self._intel.data.get("meta", {}).values():
                        m["ts"] = 0
                self._start_music_intel()
        save_json(SETTINGS_FILE, self.settings)

    # ── Анализ библиотеки (жанры + звук) для «Настроения дня» ─────────
    def _intel_store(self):
        if music_intel is None:
            return None
        if getattr(self, "_intel", None) is None:
            self._intel = music_intel.IntelStore(INTEL_FILE)
        return self._intel

    def _start_music_intel(self, quiet=True):
        store = self._intel_store()
        if store is None or not self.library:
            return
        w = getattr(self, "_intel_worker", None)
        if w is not None and w.is_alive():
            return
        lib = list(self.library)
        def progress(stage, done, total, label):
            if done % 5 and done != total - 1:
                return
            if stage == "train":
                txt = "Обучаем ИИ жанров…"
            else:
                txt = (f"Анализ звучания: {done + 1}/{total}" if stage == "audio"
                       else f"Ищем жанры: {done + 1}/{total}")
            def ui():
                self._intel_status = txt
                if hasattr(self, "genre_ai_lbl") and not getattr(self, "_genre_refs_busy", False):
                    self.genre_ai_lbl.setText(txt)
                if not getattr(self, "_mood_busy", False):
                    self.mood_lbl.setToolTip(txt)
                    if self.mood_lbl.text() in ("—", "") or self.mood_lbl.text().startswith(("Анализ звучания", "Ищем жанры")):
                        self.mood_lbl.setText(txt)
            self._ui_bridge.call.emit(ui)
        def finished(stats):
            def ui():
                self._intel_status = ""
                self._intel_profiles = None              # пересчитать при следующем подборе
                self._genre_ai_refresh_status()
                msg = (f"Библиотека изучена: звук {stats['audio']}/{stats['total']}, "
                       f"жанры {stats['genre']}/{stats['total']}")
                self.mood_lbl.setToolTip(msg)
                if self.mood_lbl.text().startswith(("Анализ звучания", "Ищем жанры")):
                    self.mood_lbl.setText(msg)
            self._ui_bridge.call.emit(ui)
        self._intel_worker = music_intel.IntelWorker(
            lib, store, lastfm_key=self.settings.get("lastfm_key", ""),
            progress=progress, finished=finished, network=self.settings.get("intel_network", True))
        self._intel_worker.start()

    # ── ИИ жанров ──────────────────────────────────────────────────── #
    def _genre_ai(self):
        try:
            import genre_ai
            return genre_ai.get_ai(DATA_DIR)
        except Exception as e:                       # noqa: BLE001
            print("[genre-ai]", e)
            return None

    def _genre_ai_refresh_status(self):
        ai = self._genre_ai()
        if hasattr(self, "genre_ai_lbl") and not getattr(self, "_genre_refs_busy", False):
            self.genre_ai_lbl.setText(ai.status_text() if ai else "ИИ жанров недоступен (нет numpy/scipy).")

    def _genre_ai_run(self):
        if self._genre_ai() is None or self._intel_store() is None:
            return
        w = getattr(self, "_intel_worker", None)
        if w is not None and w.is_alive():
            self.genre_ai_lbl.setText("Анализ уже идёт: " + (getattr(self, "_intel_status", "") or "…"))
            return
        if not self.library:
            self.genre_ai_lbl.setText("Библиотека пуста — добавьте треки.")
            return
        self.genre_ai_lbl.setText("Запускаем анализ…")
        self._start_music_intel(quiet=False)

    def _genre_ai_refs(self):
        ai, store = self._genre_ai(), self._intel_store()
        if ai is None or store is None:
            return
        if getattr(self, "_genre_refs_busy", False):
            self._genre_refs_stop.set()                  # повторное нажатие — отмена
            self.genre_ai_refs_btn.setText("Отмена…")
            return
        ok = QMessageBox.question(
            self, "Эталоны для ИИ жанров",
            "Скачать 30-секундные превью Deezer из плейлистов каждого жанра (≈12 на жанр,\n"
            "≈100–150 МБ трафика, несколько минут) и обучить на них ИИ?\n\n"
            "Превью удаляются сразу после разбора — хранятся только числа-признаки.")
        if ok != QMessageBox.StandardButton.Yes:
            return
        import threading
        self._genre_refs_busy = True
        self._genre_refs_stop = threading.Event()
        self.genre_ai_refs_btn.setText("Стоп")
        lib = list(self.library)

        def progress(i, n, label):
            txt = f"Эталоны: {i + 1}/{n} — {label}"
            self._ui_bridge.call.emit(lambda: self.genre_ai_lbl.setText(txt))

        def work():
            msg = ""
            try:
                added = ai.build_references(progress=progress, stop=self._genre_refs_stop)
                self._ui_bridge.call.emit(lambda: self.genre_ai_lbl.setText("Обучаем ИИ жанров…"))
                ai.train(lib, store)
                msg = f"Добавлено эталонов: {added}. "
            except Exception as e:                   # noqa: BLE001
                msg = f"Ошибка: {str(e)[:80]}. "

            def done():
                self._genre_refs_busy = False
                self.genre_ai_refs_btn.setText("Эталоны")
                self._intel_profiles = None
                self.genre_ai_lbl.setText(msg + ai.status_text())
            self._ui_bridge.call.emit(done)
        threading.Thread(target=work, daemon=True, name="genre-refs").start()

    def _genre_ai_track_info(self):
        ai, store, t = self._genre_ai(), self._intel_store(), self._current_track()
        if ai is None or store is None:
            return
        if not t:
            QMessageBox.information(self, "Жанр трека", "Сейчас ничего не играет.")
            return
        if store.ai_entry(t) is None and t.get("path") and Path(str(t["path"])).exists():
            import threading
            self.genre_ai_lbl.setText("Слушаем трек…")

            def work():
                try:
                    import genre_ai
                    vec, info = genre_ai.analyze_file(str(t["path"]), float(t.get("duration") or 0))
                    store.put_ai(t, vec, info)
                    store.save()
                except Exception as e:               # noqa: BLE001
                    print("[genre-ai]", e)
                self._ui_bridge.call.emit(lambda: (self._genre_ai_refresh_status(), self._genre_ai_show(t)))
            threading.Thread(target=work, daemon=True).start()
            return
        self._genre_ai_show(t)

    def _genre_ai_show(self, t):
        import genre_ai
        try:
            from i18n import tr
        except Exception:                            # noqa: BLE001
            tr = lambda x: x
        ai, store = self._genre_ai(), self._intel_store()
        r = ai.genre_of(store, t) if ai and store else {}
        name = lambda f: tr(str(music_intel.GENRE_RU.get(f, f))).capitalize() if music_intel else f
        title = f"{t.get('artist') or ''} — {t.get('title') or ''}".strip(" —")
        if not r or not r.get("dist"):
            text = tr("Пока ничего не известно. Нажмите «Распознать» в разделе «Жанры (ИИ)».")
        else:
            lines = []
            for f, p in r["dist"].items():
                lines.append(f"{name(f):<22} {'█' * max(1, int(round(p * 20)))} {p * 100:.0f}%")
            verdict = ", ".join(name(f) for f in r.get("families", [])) or tr("не уверен")
            src = ", ".join(tr(genre_ai.SOURCE_RU.get(x, x)) for x in r.get("sources", [])) or "—"
            # собираем из уже переведённых кусков — склеенный текст словарь целиком не узнает
            text = (f"{tr('Жанр')}: {verdict}\n{tr('Уверенность')}: {r['conf'] * 100:.0f}%\n"
                    f"{tr('Источники')}: {src}\n" + (r.get("reason", "") + "\n" if r.get("reason") else "")
                    + "\nСравнение вариантов (не измеренная точность):\n" + "\n".join(lines))
        box = QMessageBox(self)
        box.setWindowTitle("Жанр трека (ИИ)")
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(title or tr("Трек"))
        box.setInformativeText(text)
        correct = box.addButton("Исправить жанр…", QMessageBox.ButtonRole.ActionRole)
        clear = box.addButton("Убрать моё исправление", QMessageBox.ButtonRole.ActionRole) if ai and ai.correction(t) else None
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() is correct:
            self._genre_ai_correct(t)
        elif clear is not None and box.clickedButton() is clear:
            self._genre_ai_correct(t, clear=True)

    def _genre_ai_correct(self, track, clear=False):
        ai = self._genre_ai()
        if ai is None:
            return
        families = []
        if not clear:
            from genre_correction_ui import GenreCorrectionDialog
            dialog = GenreCorrectionDialog(music_intel.GENRE_RU if music_intel else {}, ai.correction(track), self)
            if dialog.exec() != dialog.DialogCode.Accepted:
                return
            families = dialog.families
        try:
            ai.set_correction(track, families)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Жанр не сохранён", str(exc))
            return
        self._intel_profiles = None
        self._notify_tracks_changed()
        self._genre_ai_refresh_status()
        self._toast("Ручной жанр сохранён" if families else "Снова используется автоматическое определение жанра")

    def _build_smart_playlist(self):
        if getattr(self, "_mood_busy", False):
            return
        if not self.library:
            QMessageBox.information(self, "Пусто", "Библиотека пуста — нечего подбирать.")
            return
        self._mood_busy = True
        self.mood_lbl.setText("Смотрим погоду и подбираем…")
        lib = list(self.library)
        store = self._intel_store()
        key = self.settings.get("owm_key", "")
        city = self.settings.get("owm_city", "Moscow")
        history = dict(self.settings.get("play_history", {}))
        import threading
        def work():
            daypart = get_daypart()
            try:
                weather = get_weather(key, city) if music_intel is not None else (
                    fetch_weather(key, city=city) if key else None) or fallback_weather()
            except Exception as e:
                print("[weather]", e); weather = fallback_weather()
            tracks, info = [], None
            try:
                if store is not None:
                    prof = music_intel.build_profiles(lib, store)
                    tracks, info = build_smart_playlist_v2(lib, prof, daypart, weather, 25, history)
                else:
                    tracks = build_smart_playlist(lib, daypart, weather["main"], limit=25)
            except Exception as e:
                import traceback; traceback.print_exc()
                tracks = build_smart_playlist(lib, daypart, weather["main"], limit=25)
            self._ui_bridge.call.emit(lambda: self._smart_playlist_ready(daypart, weather, tracks, info))
        threading.Thread(target=work, daemon=True).start()

    def _smart_playlist_ready(self, daypart, weather, tracks, info):
        self._mood_busy = False
        if not tracks:
            self.mood_lbl.setText("Не получилось подобрать треки.")
            return
        name = HIDDEN_PL + "mood"
        self.playlists[name] = {"tracks": tracks, "desc": "auto", "cover": ""}
        save_json(PL_FILE, self.playlists)
        self._refresh_playlists()
        w_label = WEATHER_RU.get(weather.get("main"), weather.get("main", ""))
        temp = weather.get("temp")
        t_txt = f", {temp:+.0f}°" if isinstance(temp, (int, float)) else ""
        head = f"{DAYPART_RU.get(daypart, daypart)}, {w_label}{t_txt}"
        if info:
            extra = []
            if info.get("reasons"):
                extra.append(", ".join(info["reasons"]))
            fams = [music_intel.GENRE_RU.get(f, f) for f in info.get("families", [])] if music_intel else []
            lines = [head + (f" ({'; '.join(extra)})" if extra else ""),
                     f"Настроение: {info['mood']}"]
            if fams:
                lines.append("Больше всего: " + ", ".join(fams))
            lines.append(f"Подобрано {len(tracks)} треков")
            cov = info.get("coverage", 0.0)
            if cov < 0.9:
                lines.append(f"Изучено {cov * 100:.0f}% библиотеки — подбор будет точнее после анализа")
            self.mood_lbl.setText("\n".join(lines))
            tgt = info["target"]
            self.mood_lbl.setToolTip(
                f"Цель: энергия {tgt['energy'] * 100:.0f}%, позитив {tgt['valence'] * 100:.0f}%\n"
                f"Погода: {weather.get('source', '')} {weather.get('description', '')}")
        else:
            self.mood_lbl.setText(f"{head} ({weather.get('source')}) → подобрано {len(tracks)} треков")
        self._play_index(0, name)
        if music_intel is not None and (not info or info.get("coverage", 1) < 0.98):
            self._start_music_intel()

    # ------------------------------------------------------------------ #
    #  Таймер сна                                                          #
    # ------------------------------------------------------------------ #

    def _toggle_sleep_timer(self):
        if self.sleep_timer.active:
            self.sleep_timer.cancel()
            self.btn_sleep.setText("Запустить")
            self.sleep_status_lbl.setText("Отменено")
            return
        self.sleep_timer.start(self.sleep_spin.value(), fade_seconds=20)
        self.btn_sleep.setText("Отменить")

    def _on_sleep_tick(self, remaining):
        m, s = divmod(int(remaining), 60)
        self.sleep_status_lbl.setText(f"До сна: {m}:{s:02d}")

    def _on_sleep_finished(self):
        self.btn_sleep.setText("Запустить")
        self.sleep_status_lbl.setText("Уснули. Спокойной ночи")
        self._set_playing_ui(False)

    # ------------------------------------------------------------------ #
    #  Pomodoro-фокус                                                      #
    # ------------------------------------------------------------------ #

    def _toggle_pomodoro(self):
        if self.pomodoro.phase != "idle":
            self.pomodoro.stop()
            return
        self.pomodoro.start(self.pomo_work_spin.value(), self.pomo_break_spin.value())
        self.btn_pomodoro.setText("Стоп фокуса")

    def _on_pomo_phase(self, phase, remaining):
        label = "Фокус" if phase == "work" else "Отдых"
        m, s = divmod(int(remaining), 60)
        self.pomo_status_lbl.setText(f"{label}: {m}:{s:02d}")

    def _on_pomo_tick(self, remaining):
        label = "Фокус" if self.pomodoro.phase == "work" else "Отдых"
        m, s = divmod(int(remaining), 60)
        self.pomo_status_lbl.setText(f"{label}: {m}:{s:02d}")

    def _on_pomo_stopped(self):
        self.btn_pomodoro.setText("Старт фокуса")
        self.pomo_status_lbl.setText("Остановлено")

    # ------------------------------------------------------------------ #
    #  Трек дня / история прослушиваний                                   #
    # ------------------------------------------------------------------ #

    def _record_play_history(self, path: str):
        path = str(path or "")
        if not path:
            return
        hist = self.settings.setdefault("play_history", {})
        h = hist.setdefault(path, {"count": 0, "last": "1970-01-01"})
        h["count"] = int(h.get("count", 0)) + 1
        h["last"] = datetime.date.today().isoformat()
        self._schedule_settings_save()               # не в момент смены трека: сериализация — после кадра

    def _play_track_of_the_day(self):
        history = self.settings.get("play_history", {})
        track = pick_track_of_the_day(self.library, history)
        if not track:
            QMessageBox.information(self, "Пусто", "Библиотека пуста.")
            return
        idx = next((i for i, t in enumerate(self.library)
                    if str(t.get("path", "")) == str(track.get("path", ""))), -1)
        if idx >= 0:
            self._play_index(idx, "library")

    # ------------------------------------------------------------------ #
    #  Экспорт GIF пластинки                                               #
    # ------------------------------------------------------------------ #

    def _export_vinyl_gif(self):
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт GIF пластинки", "vinyl.gif", "GIF (*.gif)")
        if not path:
            return
        try:
            from gif_export import export_vinyl_gif
            ok = export_vinyl_gif(self.vinyl, path)
            if ok:
                QMessageBox.information(self, "Готово", f"Сохранено: {path}")
            else:
                QMessageBox.warning(self, "Ошибка", "Не удалось создать GIF.")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"{e}")

    def _lyrics_editor_locked(self) -> bool:
        """Защита ручного текста действует ТОЛЬКО для того трека, где текст
        сохранён: иначе флаг старого диалога блокировал бы поиск на других."""
        ed = self._lyrics_editor
        if ed is None or not getattr(ed, "_user_locked", False):
            return False
        tracks = self.library if self.queue_context == "library" else self.playlists.get(self.queue_context, {}).get("tracks", [])
        if not 0 <= self.current_index < len(tracks):
            return False
        return getattr(ed, "_track_path", "") == tracks[self.current_index].get("path", "")

    # ── Кэш найденных текстов: найденный текст (с таймингами или без) хранится НАВСЕГДА и больше
    #    не ищется; «не найдено» перепроверяется раз в неделю. Заменить — Ctrl+L / «Найти текст вручную»
    #    или редактор текста.
    def _lyrics_cache(self):
        if getattr(self, "_lyr_cache", None) is None:
            self._lyr_cache = load_json(LYRICS_CACHE_FILE, {})
            if not isinstance(self._lyr_cache, dict):
                self._lyr_cache = {}
        return self._lyr_cache

    def _lyrics_cache_preload(self):
        """Кэш текстов (мегабайты JSON) — прочитать в фоне сразу после запуска: первое включение трека
        больше не ждёт диск и разбор файла в потоке интерфейса."""
        if getattr(self, "_lyr_cache", None) is not None:
            return

        def work():
            data = load_json(LYRICS_CACHE_FILE, {})
            if not isinstance(data, dict):
                data = {}

            def done():
                if getattr(self, "_lyr_cache", None) is None:    # не успели прочитать сами — берём готовое
                    self._lyr_cache = data
            try:
                self._ui_bridge.call.emit(done)
            except RuntimeError:
                pass
        threading.Thread(target=work, daemon=True, name="lyrics-cache").start()

    def _lyrics_cache_put(self, path, text, src, synced, hit=None):
        c = self._lyrics_cache()
        old = c.get(str(path)) or {}
        c[str(path)] = {"text": text or "", "src": src or "", "synced": bool(synced),
                        "ts": int(time.time())}
        hit = hit or ((old.get("a", ""), old.get("t", "")) if old.get("t") else None)
        if hit and text:                                   # кто поёт по версии источника текста — для тегов
            c[str(path)].update(a=hit[0] or "", t=hit[1] or "")
        if len(c) > 50000:                              # не раздуваем файл бесконечно
            for k in sorted(c, key=lambda k: (bool(c[k].get("text")), c[k].get("ts", 0)))[:len(c) - 50000]:
                c.pop(k, None)
        save_json(LYRICS_CACHE_FILE, c)

    def ai_sync_lyrics(self):
        """ИИ-синхронизация текста текущего трека (Whisper); повторный вызов во время работы — отмена."""
        import threading
        st = getattr(self, "_ai", None)
        if st and st["running"]:
            st["cancel"].set()
            st["status"] = "Отменяю…"
            return
        if self.current_index < 0:
            return
        tracks = self.library if self.queue_context == "library" else \
            self.playlists.get(self.queue_context, {}).get("tracks", [])
        if not 0 <= self.current_index < len(tracks):
            return
        path = str(tracks[self.current_index].get("path", ""))
        text = self.lyrics_box.toPlainText()
        import lyrics_sync as LS
        if not path or not LS.plain_lines(text):
            self._toast("Нет текста для синхронизации")
            return
        if not LS.whisper_installed():
            if QMessageBox.question(
                self, "ИИ-синхронизация",
                "Для синхронизации нужна нейросеть распознавания речи (faster-whisper).\n\n"
                "Она ставится один раз; при первом запуске скачается модель (около 460 МБ). "
                "Аудио никуда не отправляется — всё работает на вашем компьютере.\n\nУстановить?"
            ) != QMessageBox.StandardButton.Yes:
                return
        st = self._ai = {"running": True, "cancel": threading.Event(), "status": "Подготовка…",
                         "path": path, "err": ""}

        def work():
            lrc, err = None, ""
            try:
                if not LS.whisper_installed():
                    st["status"] = "Устанавливаю faster-whisper (1–3 минуты)…"
                    if not LS.install_whisper(lambda s: st.__setitem__("status", s)):
                        raise RuntimeError("не удалось установить faster-whisper (нет интернета?)")
                lrc = LS.sync_lyrics_isolated(path, text, progress=lambda s: st.__setitem__("status", s),
                                     cancel=st["cancel"], model='base' if self.settings.get('lyrics_sync_fast') else 'small',
                                     use_vocals=not self.settings.get('lyrics_sync_fast',False))
            except LS.SyncCancelled:
                err = "cancel"
            except Exception as e:                       # noqa: BLE001
                print("[lyrics sync]", e)
                err = str(e)
            self._ui_bridge.call.emit(lambda: self._ai_sync_done(st, lrc, err))
        threading.Thread(target=work, daemon=True).start()

    def _ai_sync_done(self, st, lrc, err):
        st["running"] = False
        st["status"] = ""
        if lrc:
            try:
                from lyrics_tags import write_lyrics_lrc
                write_lyrics_lrc(st["path"], lrc)
            except Exception as e:                       # noqa: BLE001
                print("[lyrics sync] save:", e)
            self._lyrics_cache_put(st["path"], lrc, "ИИ-синхронизация", True)
            tracks = self.library if self.queue_context == "library" else \
                self.playlists.get(self.queue_context, {}).get("tracks", [])
            cur = str(tracks[self.current_index].get("path", "")) if 0 <= self.current_index < len(tracks) else ""
            if cur == st["path"]:
                self._set_lyrics_display(lrc, "ИИ-синхронизация")
            self._toast("Текст синхронизирован с треком")
        elif err == "cancel":
            self._toast("Синхронизация отменена")
        else:
            st["err"] = f"Не получилось: {err}"
            self._toast(st["err"][:90])

    def _set_lyrics_display(self, text, src=""):
        try:
            from lyrics import uncensor
            text = uncensor(text)
        except Exception:
            pass
        self.lyrics_box.setPlainText(text)
        self.lyrics_view.set_lyrics(text)
        try:
            self.lyrics_box.setToolTip(f"Источник: {src}" if src else "")
            self.lyrics_view.setToolTip(f"Источник: {src}  ·  Ctrl+L — искать заново" if src else
                                        "Ctrl+L — искать текст заново")
        except Exception:
            pass

    def _load_lyrics(self, force=False):
        QTimer.singleShot(2000, self._autotag_flush)      # трек сменился — отложенные теги в освободившиеся файлы
        # любой новый показ текста (другой трек, даже если текст взят из файла или кэша, без сети)
        # отменяет ещё идущий поиск — иначе его ответ лёг бы на уже другую песню
        self._lyrics_request_id += 1
        self._lyrics_request_path = ""
        if self.current_index<0:return
        tracks=self.library if self.queue_context=="library" else self.playlists.get(self.queue_context,{}).get("tracks",[])
        if not 0<=self.current_index<len(tracks):return
        t=tracks[self.current_index]
        path = str(t.get("path", ""))
        self._tags_btn_update(t)

        # Если редактор открыт и пользователь уже сохранил свой текст —
        # автопоиск (сетевой) не должен его перезаписывать. Локальный .lrc/тег
        # всё равно показываем — это то же самое, что пользователь сохранил.
        editor_locked = self._lyrics_editor_locked()

        # Локальный источник (.lrc рядом с файлом или тег USLT/LYRICS/©lyr)
        # проверяется СРАЗУ и синхронно. Если там обычный текст без таймингов,
        # а в кэше уже есть синхронизированный — показываем синхронизированный.
        local = read_local_lyrics(path)
        cached = self._lyrics_cache().get(path) if path else None
        if local:
            from lyrics import is_synced
            if not is_synced(local) and cached and cached.get("synced") and cached.get("text") and not force:
                self._set_lyrics_display(cached["text"], cached.get("src", ""))
            else:
                self._set_lyrics_display(local, "файл / теги трека")
            if not force:
                return

        # Текст защищён пользователем — не лезем в сеть
        if editor_locked:
            return

        refresh = force
        if cached and not force:
            age = time.time() - cached.get("ts", 0)
            if cached.get("text"):
                self._set_lyrics_display(cached["text"], cached.get("src", ""))
                if cached.get("t"):
                    self._autotag_maybe(t, cached.get("a", ""), cached["t"])
                return                               # найден однажды — сохранён, заново не ищем
            elif age < 7 * 86400:
                self._set_lyrics_display("Текст не найден.\nCtrl+L — попробовать ещё раз.")
                return
        if not (cached and cached.get("text") and not force):
            _msg = "Ищем текст с таймингами…" if not force else "Ищем заново…"
            self.lyrics_box.setPlainText(_msg)
            if not local:
                self.lyrics_view.set_lyrics(_msg)      # чтобы не висели строки прошлого трека
        rid = self._lyrics_request_id
        self._lyrics_request_path = path
        try:
            dur = float(t.get("duration") or 0) or float(getattr(self.engine, "duration", 0) or 0)
        except Exception:
            dur = 0.0
        title, artist, album = t.get("title",""), t.get("artist",""), t.get("album","")
        token = self.settings.get("genius_token","")
        had_text = bool(cached and cached.get("text")) and not force
        keep_on_fail = had_text or bool(local)
        import threading
        def work():
            try:
                r = fetch_lyrics_ex(title, artist, token, dur, path, album)
            except Exception as e:
                print("[lyrics]", e); r = None
            def done():
                if r:
                    src = r["source"] + (" · синхронизированный" if r["synced"] else "")
                    hit = (r.get("artist") or "", r.get("title") or "")
                    if hit[1] and rid == self._lyrics_request_id:
                        self._autotag_maybe(t, hit[0], hit[1])
                    if had_text and not r["synced"]:
                        # уже показан обычный текст — просто продлеваем кэш
                        self._lyrics_cache_put(path, cached.get("text",""), cached.get("src",""), False, hit)
                        return
                    self._lyrics_cache_put(path, r["text"], src, r["synced"], hit)
                    self._lyrics_fetched.emit(rid, r["text"], src)
                elif not keep_on_fail:
                    self._lyrics_cache_put(path, "", "", False)
                    self._lyrics_fetched.emit(rid, "", "")
                elif force and rid == self._lyrics_request_id:
                    self.lyrics_box.setToolTip("Ничего нового не нашлось")
            self._ui_bridge.call.emit(done)
        threading.Thread(target=work,daemon=True).start()

    # ── теги из интернета для треков, у которых в файле одно название ── #

    def _tags_btn_update(self, t):
        """Кнопка «Поменять теги трека» над текстом — у треков, которым теги дополняли автоматически
        или у которых их всё ещё нет (исполнитель / обложка)."""
        path = str((t or {}).get("path", ""))
        self._tags_btn_path = ""
        self._tags_btn_show(False)
        if not path or path.startswith("stream:"):
            return
        if t.get("tags_auto"):
            self._tags_btn_path = path
            self._tags_btn_show(True)
            return
        import threading

        def work():
            try:
                import auto_tags
                miss = auto_tags.needs_tags(path, t)
            except Exception:                              # noqa: BLE001
                miss = {}

            def done():
                cur = self._current_track()
                if miss and cur is not None and str(cur.get("path", "")) == path:
                    self._tags_btn_path = path
                    self._tags_btn_show(True)
            self._ui_bridge.call.emit(done)
        threading.Thread(target=work, daemon=True, name="tags-check").start()

    def _tags_btn_show(self, on: bool):
        for w in (getattr(self, "lyrics_view", None), getattr(self, "_ya", None)):
            try:
                if w is not None and hasattr(w, "set_tags_button"):
                    w.set_tags_button(on)
            except RuntimeError:
                pass

    def edit_current_tags(self):
        cur = self._current_track()
        if cur is not None:
            self.edit_track_tags(cur)

    def _autotag_maybe(self, t, artist, title):
        """Текст нашёлся — если у файла нет исполнителя или обложки, найти их (и альбом) и записать навсегда."""
        path = str((t or {}).get("path", ""))
        if not path or path.startswith("stream:") or not self.settings.get("auto_tags", True):
            return
        # попытки помним между запусками: нашлось — в файле навсегда; не нашлось — снова не раньше чем через месяц
        tried = self.__dict__.get("_autotag_tried")
        if tried is None:
            tried = self._autotag_tried = load_json(DATA_DIR / "auto_tags_tried.json", {})
            if not isinstance(tried, dict):
                tried = self._autotag_tried = {}
        if t.get("tags_auto") or time.time() - float(tried.get(path, 0) or 0) < 30 * 86400:
            return
        tried[path] = int(time.time())
        try:
            save_json(DATA_DIR / "auto_tags_tried.json", tried)
        except Exception:                                  # noqa: BLE001
            pass
        try:
            dur = float(t.get("duration") or 0)
        except Exception:                                  # noqa: BLE001
            dur = 0.0
        import threading

        def work():
            plan = None
            try:
                import auto_tags
                miss = auto_tags.needs_tags(path, t)
                if miss:
                    plan = auto_tags.plan_missing(path, artist, title, dur, miss, trust_artist=True)
            except Exception as e:                         # noqa: BLE001
                print("[auto_tags]", e)
            if plan:
                self._ui_bridge.call.emit(lambda: self._autotag_got(path, plan))
        threading.Thread(target=work, daemon=True, name="auto-tags").start()

    # ── запись найденных тегов: НЕ в файл, который сейчас читает плеер ──
    # VLC читает трек с диска по ходу игры (file-caching=0). Перезапись файла (обложка вставляется в начало,
    # всё аудио сдвигается) посреди воспроизведения давала паузу, и звук уезжал от текста. Поэтому для такого
    # файла найденное сразу показывается (исполнитель, альбом, обложка из кэша), а в файл пишется потом —
    # когда трек доиграет (сменится) или при выходе из плеера.

    def _file_in_use(self, path) -> bool:
        path = str(path or "")
        if not path:
            return False
        eng = self.engine
        cur = self._current_track()
        # играющий файл и тот, что уже вступает (кроссфейд / gapless); предзагруженные соседи только разобраны
        # заранее — их файл плеер не читает, туда писать можно
        busy = {str(getattr(eng, "current_path", "") or ""), str((cur or {}).get("path", "")),
                str(getattr(eng, "_fade_next_path", "") or "")}
        return path in busy

    def _autotag_got(self, path, plan):
        """Теги найдены (в фоне). Файл свободен — записать сейчас; играет — показать и записать позже."""
        if not self._file_in_use(path):
            self._autotag_write(path, plan)
            return
        self.__dict__.setdefault("_autotag_pending", {})[path] = plan
        meta = {"path": path, "cover_changed": False}
        meta.update({k: v for k, v in (plan.get("new") or {}).items() if v})
        if plan.get("cover"):
            try:
                ext = ".png" if plan.get("mime") == "image/png" else ".jpg"
                cov = COVER_DIR / (hashlib.sha1(path.encode("utf-8")).hexdigest() + "_auto" + ext)
                cov.write_bytes(plan["cover"])
                meta["cover_path"] = str(cov)
            except Exception as e:                         # noqa: BLE001
                print("[auto_tags] cover cache:", e)
        self._autotag_done(path, dict(meta, cover_changed=bool(meta.get("cover_path"))), meta)

    def _autotag_write(self, path, plan):
        import threading

        def work():
            res = None
            try:
                import auto_tags
                res = auto_tags.apply_plan(path, plan)
            except Exception as e:                         # noqa: BLE001
                print("[auto_tags] write:", e)
            if res:
                self._ui_bridge.call.emit(lambda: self._autotag_done(path, res))
        threading.Thread(target=work, daemon=True, name="auto-tags-write").start()

    def _autotag_flush(self, all_=False):
        """Отложенные теги — в файлы, которые плеер уже не читает (all_ — при выходе: все и сразу)."""
        pend = self.__dict__.get("_autotag_pending") or {}
        for path in list(pend):
            if all_ or not self._file_in_use(path):
                plan = pend.pop(path)
                if all_:
                    try:
                        import auto_tags
                        auto_tags.apply_plan(path, plan)
                    except Exception as e:                 # noqa: BLE001
                        print("[auto_tags] write:", e)
                else:                                      # уже показано — без второго тоста и пересборки обложки
                    self._autotag_write_quiet(path, plan)

    def _autotag_write_quiet(self, path, plan):
        import threading

        def work():
            try:
                import auto_tags
                auto_tags.apply_plan(path, plan)
            except Exception as e:                         # noqa: BLE001
                print("[auto_tags] write:", e)
        threading.Thread(target=work, daemon=True, name="auto-tags-write").start()

    def _autotag_done(self, path, res, meta=None):
        if meta is None:
            meta = {"path": path, "cover_changed": bool(res.get("cover_changed"))}
            for k in ("title", "artist", "album", "genre"):
                if res.get(k):
                    meta[k] = res[k]
        for t in self._all_track_dicts(path):
            t["tags_auto"] = True
        self._on_track_metadata_changed(meta)
        got = [n for k, n in (("artist", "исполнитель"), ("album", "альбом"), ("genre", "жанр")) if res.get(k)]
        if res.get("cover_changed"):
            got.insert(0, "обложка")
        self._toast("Теги трека дополнены: " + ", ".join(got))
        cur = self._current_track()
        if cur is not None and str(cur.get("path", "")) == path:
            self._tags_btn_path = path
            self._tags_btn_show(True)
            try:
                self._update_discord_rpc()
            except Exception:                              # noqa: BLE001
                pass

    def _manual_lyrics_search(self):
        """Ручной поиск текста: свой запрос «исполнитель - название» → поиск по всем источникам →
        найденный текст сохраняется для текущего трека."""
        cur = self._current_track()
        if cur is None:
            QMessageBox.information(self, "Нет трека", "Сначала запустите воспроизведение трека.")
            return
        a = (cur.get("artist") or "").strip()
        ti = (cur.get("title") or "").strip()
        if a.lower() in ("unknown artist", "неизвестный исполнитель"):
            a = ""
        path = str(cur.get("path", ""))
        try:
            dur = float(cur.get("duration") or 0) or float(getattr(self.engine, "duration", 0) or 0)
        except Exception:                                # noqa: BLE001
            dur = 0.0
        from manual_search import LyricsSearchDialog
        dlg = LyricsSearchDialog(self, f"{a} - {ti}" if a else ti, dur, self.settings.get("genius_token", ""))
        if not dlg.exec() or not dlg.result:
            return
        r = dlg.result
        cur2 = self._current_track()
        if cur2 is None or str(cur2.get("path", "")) != path:
            return                                       # пока выбирали, трек сменился
        self._lyrics_request_id += 1                     # автопоиск, если ещё идёт, не перезапишет выбор
        src = r["source"] + (" · синхронизированный" if r["synced"] else "") + " · ручной поиск"
        self._lyrics_cache_put(path, r["text"], src, r["synced"])
        self._set_lyrics_display(r["text"], src)

    def _lyrics_ready(self,rid,text,src):
        if rid!=self._lyrics_request_id:return
        cur = self._current_track()                       # и на всякий случай — та же ли песня сейчас играет
        if cur is not None and str(cur.get("path", "")) != getattr(self, "_lyrics_request_path", ""):
            return
        # Если пользователь успел сохранить свой текст пока шёл сетевой
        # запрос — не перезаписываем его результатом из сети.
        if self._lyrics_editor_locked():
            return
        display = text or "Текст не найден.\nCtrl+L — попробовать ещё раз."
        self._set_lyrics_display(display, src)

    # ------------------------------------------------------------------ #
    #  Ручной редактор / LRC-таймер текста песни                          #
    # ------------------------------------------------------------------ #

    def _open_lyrics_editor(self):
        cur = self._current_track()
        if cur is None:
            QMessageBox.information(self, "Нет трека", "Сначала запустите воспроизведение трека.")
            return
        self.edit_track_tags(cur)

    def _on_lyrics_edited(self, text: str):
        """Редактор что-то сохранил (.lrc или тег) — обновляем показ текста
        сразу, не дожидаясь следующего _load_lyrics()."""
        self.lyrics_box.setPlainText(text)
        self.lyrics_view.set_lyrics(text)

    def _on_track_metadata_changed(self, meta: dict, refresh: bool = True):
        """Редактор сохранил теги файла — обновляем ВСЕ записи этого файла
        (коллекция + все плейлисты), обложку и заголовок плеера.
        refresh=False — пачкой (теги всей медиатеки): без сохранения и перерисовки списков на каждый трек."""
        path = str(meta.get("path") or "")
        if not path:
            cur = self._current_track()
            path = str(cur.get("path", "")) if cur else ""
        if not path:
            return
        new_cover = ""
        if meta.get("cover_path"):                          # обложка уже в кэше (файл трека пока не трогаем)
            new_cover = str(meta["cover_path"])
        elif meta.get("cover_changed"):
            new_cover = self._embedded_cover_to_cache(path, fresh=True)
        for t in self._all_track_dicts(path):
            if meta.get("title"):
                t["title"] = sanitize_title(meta["title"])
            if "artist" in meta and meta.get("artist") is not None:
                t["artist"] = meta["artist"]
            if "album" in meta and meta.get("album") is not None:
                t["album"] = meta["album"]
            if meta.get("genre"):
                t["genre"] = meta["genre"]
            if new_cover:
                t["cover"] = new_cover
        if refresh:
            self._save_library()
            save_json(PL_FILE, self.playlists)
        cur = self._current_track()
        if cur and str(cur.get("path", "")) == path:
            artist = cur.get("artist", "")
            album = cur.get("album", "")
            self.title_lbl.setText(sanitize_title(cur.get("title", "Untitled")))
            self.artist_lbl.setText(f"{artist}  ·  {album}" if album else artist)
            if new_cover:
                try:
                    self.vinyl.set_cover(new_cover)
                except Exception:
                    pass
        if refresh:
            self._library_changed_refresh()

    def _library_changed_refresh(self):
        self._icon_cache.clear()
        self._refresh_library_view()
        self._refresh_playlists()
        self._notify_tracks_changed()

    def tag_all_library(self):
        """Настройки → «Найти теги для всей музыки»: исполнитель, альбом, жанр и обложка для каждого скачанного трека."""
        import tag_all
        tag_all.open_dialog(self)

    # ------------------------------------------------------------------ #
    #  Управление треками — общее для всех тем                            #
    # ------------------------------------------------------------------ #

    def _ctx_tracks(self, ctx=None):
        ctx = self.queue_context if ctx is None else ctx
        return self.library if ctx == "library" else self.playlists.get(ctx, {}).get("tracks", [])

    def _current_track(self):
        tr = self._ctx_tracks()
        return tr[self.current_index] if 0 <= self.current_index < len(tr) else None

    def _all_track_dicts(self, path):
        path = str(path)
        out = [t for t in self.library if str(t.get("path", "")) == path]
        for pl in self.playlists.values():
            out += [t for t in pl.get("tracks", []) if str(t.get("path", "")) == path]
        return out

    def _embedded_cover_to_cache(self, path, fresh=False) -> str:
        """Вшитая обложка файла → картинка в кэше. fresh=True — новое имя файла,
        чтобы все кэши картинок гарантированно показали новую обложку."""
        if not MutaFile:
            return ""
        try:
            m = MutaFile(path)
            tags = getattr(m, "tags", None)
            data, ext = None, ".jpg"
            if tags is not None and hasattr(tags, "getall"):
                pics = tags.getall("APIC")
                if pics:
                    data = pics[0].data
                    mime = str(getattr(pics[0], "mime", "") or "").lower()
                    ext = ".png" if "png" in mime else ".jpg"
            if data is None and getattr(m, "pictures", None):
                data = m.pictures[0].data
                ext = ".png" if "png" in str(getattr(m.pictures[0], "mime", "")).lower() else ".jpg"
            if data is None and tags is not None:
                try:
                    covr = tags.get("covr")
                    if covr:
                        data = bytes(covr[0])
                        ext = ".png" if data.startswith(b"\x89PNG") else ".jpg"
                except Exception:
                    pass
            if not data:
                return ""
            stem = hashlib.sha1(str(path).encode("utf-8")).hexdigest()
            if fresh:
                stem += "_" + str(int(time.time()))
            cover = COVER_DIR / (stem + ext)
            cover.write_bytes(data)
            return str(cover)
        except Exception as e:
            print("[cover]", e)
            return ""

    def edit_track_tags(self, track):
        """Редактор тегов/обложки/текста для ЛЮБОГО трека (не только играющего)."""
        if not track:
            return
        path = str(track.get("path", ""))
        if not path or not Path(path).exists():
            QMessageBox.warning(self, "Файл не найден", path or "у трека нет файла")
            return
        cur = self._current_track()
        text = self.lyrics_box.toPlainText() if cur and str(cur.get("path", "")) == path else ""
        if self._lyrics_editor is None:
            self._lyrics_editor = LyricsEditorDialog(
                self, self.engine,
                genius_token_getter=lambda: self.settings.get("genius_token", ""),
                track_path=path, title=track.get("title", "Untitled"),
                artist=track.get("artist", ""), initial_text=text)
            self._lyrics_editor.lyrics_changed.connect(self._on_lyrics_edited)
            self._lyrics_editor.metadata_changed.connect(self._on_track_metadata_changed)
        else:
            self._lyrics_editor.set_track(track_path=path, title=track.get("title", "Untitled"),
                                          artist=track.get("artist", ""), initial_text=text)
        inapp.present(self, self._lyrics_editor, "Текст и теги")

    def _reindex_current(self, cur_path):
        """После изменения списков — найти играющий трек заново (индексы сдвинулись)."""
        if not cur_path:
            return
        if self.queue_context != "library" and self.queue_context not in self.playlists:
            self.queue_context = "library"
        tr = self._ctx_tracks()
        idx = next((i for i, t in enumerate(tr) if str(t.get("path", "")) == cur_path), -1)
        if idx < 0 and self.queue_context != "library":
            self.queue_context = "library"
            idx = next((i for i, t in enumerate(self.library) if str(t.get("path", "")) == cur_path), -1)
        self.current_index = idx
        if self.shuffle:
            self._build_shuffle_queue()

    def _notify_tracks_changed(self):
        """Темам/окнам — перерисовать списки (длина могла не измениться)."""
        QTimer.singleShot(1500, self._loud_scan)
        for shell in (getattr(self, "_ya", None), getattr(getattr(self, "_hub", None), "shell", None)):
            if shell is None:
                continue
            try:
                shell.on_tracks_changed()
            except RuntimeError:
                pass
            except Exception as e:
                print("[tracks changed]", e)

    def remove_tracks_everywhere(self, tracks, parent=None) -> bool:
        """Удалить треки из плеера целиком: из коллекции и всех плейлистов
        (по желанию — и файлы с диска в Корзину)."""
        tracks = [t for t in tracks if t]
        if not tracks:
            return False
        from track_tools import confirm_delete, move_to_trash
        ok, del_files = confirm_delete(parent or self, tracks)
        if not ok:
            return False
        paths = {str(t.get("path", "")) for t in tracks}
        cur = self._current_track()
        cur_path = str(cur.get("path", "")) if cur else ""
        if cur_path in paths:
            self.engine.stop()
            self.current_index = -1
            self._set_playing_ui(False)
            self.title_lbl.setText("— не играет —")
            self.artist_lbl.setText("")
            cur_path = ""
        self._forget_tracks(paths)
        self.library = [t for t in self.library if str(t.get("path", "")) not in paths]
        for pl in self.playlists.values():
            pl["tracks"] = [t for t in pl.get("tracks", []) if str(t.get("path", "")) not in paths]
        od = self.settings.get("online_downloaded") or {}
        for u in [u for u, p in od.items() if str(p) in paths]:
            od.pop(u, None)
        failed = []
        if del_files:
            for p in paths:
                if p and Path(p).exists():
                    if not move_to_trash(p):
                        failed.append(p)
                    for ext in (".lrc", ".txt"):
                        side = Path(p).with_suffix(ext)
                        if side.exists():
                            move_to_trash(str(side))
        self._reindex_current(cur_path)
        self._save_library()
        save_json(PL_FILE, self.playlists)
        save_json(SETTINGS_FILE, self.settings)
        self._refresh_library_view()
        self._refresh_playlists()
        self._notify_tracks_changed()
        if failed:
            QMessageBox.warning(parent or self, "Не все файлы удалены",
                                "Эти файлы не удалось отправить в Корзину (заняты или нет доступа):\n"
                                + "\n".join(failed[:8]))
        return True

    def _start_media_session(self):
        try:
            import media_session
            self._media_session = media_session.start(self)
        except Exception as e:                           # noqa: BLE001
            print("[media session]", e)
            self._media_session = None

    def _on_media_session_toggled(self, on):
        self.settings["media_session"] = bool(on)
        save_json(SETTINGS_FILE, self.settings)
        ms = self.__dict__.get("_media_session")
        if on and ms is None:
            self._start_media_session()
        elif not on and ms is not None:
            ms.close()
            self._media_session = None

    def open_cleanup(self, tab=0):
        """Окно «Очистка медиатеки и кэша»: 0 — кривые файлы, 1 — клипы, 2 — кэш."""
        from cleanup import open_cleanup
        open_cleanup(self, tab)

    def replace_track_file(self, old_path, new_path, delete_old=True) -> str:
        """Подменить трек другим файлом (очистка медиатеки: кривой файл → версия с площадок).
        Новый трек встаёт на место старого в коллекции, во всех плейлистах и в очереди; история
        прослушиваний и клип переносятся. Старый файл — в Корзину (если не играет прямо сейчас).
        → "" — готово, иначе текст проблемы."""
        old = str(Path(old_path).resolve()) if old_path else ""
        new = str(Path(new_path).resolve())
        if not old or old == new:
            return "это тот же файл"
        self._register_track(new)
        new_t = next((x for x in self.library if x.get("path") == new), None)
        if new_t is None:
            return "новый файл не прочитался"
        cur = self._current_track()
        cur_path = str(cur.get("path", "")) if cur else ""
        old_i = next((i for i, x in enumerate(self.library) if x.get("path") == old), -1)
        if old_i >= 0:
            self._forget_tracks([old])
            self.library.remove(new_t)
            old_i = next((i for i, x in enumerate(self.library) if x.get("path") == old), -1)
            self.library[old_i] = new_t                    # то же место — номера в очереди не съезжают
        for pl in self.playlists.values():
            trs = pl.get("tracks", [])
            for k, x in enumerate(trs):
                if str(x.get("path", "")) == old:
                    trs[k] = dict(new_t)
            # если новый файл уже был в плейлисте — без дубля
            seen, keep = set(), []
            for x in trs:
                p = str(x.get("path", ""))
                if p in seen:
                    continue
                seen.add(p)
                keep.append(x)
            pl["tracks"] = keep
        uq = getattr(self, "user_queue", None)
        if uq:
            for k, x in enumerate(uq):
                if str(x.get("path", "")) == old:
                    uq[k] = dict(new_t)
        hist = self.settings.get("play_history") or {}
        if old in hist:
            h = hist.pop(old)
            if new in hist and isinstance(h, dict) and isinstance(hist[new], dict):
                hist[new]["count"] = int(hist[new].get("count", 0)) + int(h.get("count", 0))
            else:
                hist[new] = h
        try:                                                # скачанный клип — тоже новому файлу
            import clip_fetch as CF
            e = CF.lookup({"path": old})
            if e and not CF.lookup(new_t):
                CF.update(new_t, **{k: v for k, v in e.items() if k not in ("path", "ts")})
        except Exception:                                   # noqa: BLE001
            pass
        problem = ""
        try:
            from tier_store import TierStore
            page = (getattr(getattr(self, "_ya", None), "pages", {}) or {}).get("tierlist")
            tier_store = page.store if page is not None else TierStore(self.tierlist_path)
            if tier_store.remap_path(old, new) and page is not None:
                page.undo_stack.clear()
                page.redo_stack.clear()
        except (ValueError, OSError) as exc:
            problem = f"не удалось перенести оценку тирлиста: {exc}"
        if delete_old and Path(old).exists():
            if old == cur_path:
                problem = "старый файл сейчас играет — удалите его позже"
            else:
                from track_tools import move_to_trash
                if not move_to_trash(old):
                    problem = "старый файл не удалось отправить в Корзину"
                for ext in (".lrc", ".txt"):
                    side = Path(old).with_suffix(ext)
                    if side.exists():
                        move_to_trash(str(side))
        self._reindex_current(cur_path if cur_path != old else new)
        self._save_library()
        save_json(PL_FILE, self.playlists)
        save_json(SETTINGS_FILE, self.settings)
        self._refresh_library_view()
        self._refresh_playlists()
        self._notify_tracks_changed()
        return problem

    def playlist_add_tracks(self, name, tracks) -> int:
        pl = self.playlists.setdefault(name, {"tracks": [], "desc": "", "cover": ""})
        have = {str(t.get("path", "")) for t in pl["tracks"]}
        n = 0
        for t in tracks:
            p = str(t.get("path", ""))
            if p and p not in have:
                pl["tracks"].append(dict(t))
                have.add(p)
                n += 1
        if n:
            save_json(PL_FILE, self.playlists)
            self._refresh_playlists()
            self._notify_tracks_changed()
            self._collab_changed(name)
        return n

    def _collab_changed(self, name):
        """Совместный плейлист поменяли у себя — разослать участникам (net_collab)."""
        if isinstance((self.playlists.get(name) or {}).get("shared"), dict):
            try:
                import net_collab
                net_collab.local_changed(self, name)
                save_json(PL_FILE, self.playlists)
            except Exception as e:                             # noqa: BLE001
                print("[collab]", e)

    def pick_tracks_for_playlist(self, name, parent=None) -> int:
        from track_tools import TrackPicker
        pl = self.playlists.get(name, {})
        dlg = TrackPicker(parent or self, self.library, f"Добавить треки в «{name}»",
                          exclude_paths=[str(t.get("path", "")) for t in pl.get("tracks", [])])
        if dlg.exec() != dlg.DialogCode.Accepted:
            return 0
        return self.playlist_add_tracks(name, dlg.selected())

    def playlist_remove_rows(self, name, rows):
        pl = self.playlists.get(name)
        if not pl:
            return
        cur = self._current_track()
        cur_path = str(cur.get("path", "")) if cur else ""
        tr = pl.get("tracks", [])
        for r in sorted(set(rows), reverse=True):
            if 0 <= r < len(tr):
                del tr[r]
        if self.queue_context == name:
            self._reindex_current(cur_path)
        save_json(PL_FILE, self.playlists)
        self._refresh_playlists()
        self._notify_tracks_changed()
        self._collab_changed(name)

    def playlist_move(self, name, rows, target):
        """Переместить строки rows так, чтобы первая встала на позицию target."""
        pl = self.playlists.get(name)
        if not pl:
            return []
        tr = pl.get("tracks", [])
        rows = sorted(r for r in set(rows) if 0 <= r < len(tr))
        if not rows:
            return []
        cur = self._current_track()
        cur_path = str(cur.get("path", "")) if cur else ""
        moving = [tr[r] for r in rows]
        rest = [t for i, t in enumerate(tr) if i not in set(rows)]
        target = max(0, min(len(rest), target))
        pl["tracks"] = rest[:target] + moving + rest[target:]
        if self.queue_context == name:
            self._reindex_current(cur_path)
        save_json(PL_FILE, self.playlists)
        self._refresh_playlists()
        self._notify_tracks_changed()
        self._collab_changed(name)
        return list(range(target, target + len(moving)))

    def _lyrics_fade_targets(self):
        """То, что под overlay гаснет (а не прячется — раскладка не меняется)."""
        if getattr(self, "_fluid_layout_on", False):
            return [self.transport_bar, self.btn_queue_view]
        return [self._seek_row, self._vol_row, self._controls_widget, self.btn_queue_view]

    def _fade_to(self, w, target: float, ms: int = 320):
        eff = w.graphicsEffect()
        if not isinstance(eff, QGraphicsOpacityEffect):
            eff = QGraphicsOpacityEffect(w)
            eff.setOpacity(1.0)
            w.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", w)
        anim.setDuration(ms)
        anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        anim.setStartValue(eff.opacity())
        anim.setEndValue(target)
        if target >= 1.0:
            # полностью видим — эффект больше не нужен (он не бесплатен)
            anim.finished.connect(lambda w=w: (w.setGraphicsEffect(None)
                                               if not self._lyrics_mode else None))
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _toggle_lyrics_mode(self):
        if getattr(self, "_wa_on", False):
            self._wa_toggle_lyrics()          # в Winamp — свой режим текста поверх MilkDrop
            return
        if not self._lyrics_mode and getattr(self, "_ya_on", False) and getattr(self, "_ya", None) is not None:
            # в Echoes Music — своя страница «Текст»; общий оверлей поверх оболочки там не предусмотрен
            # (тема при входе сама его закрывает) и перерисовывал под собой весь интерфейс каждый кадр
            self._ya.toggle_lyrics()
            return
        if not self._lyrics_mode and getattr(self, "_daw_on", False):
            return
        self._lyrics_mode = not self._lyrics_mode
        self.btn_lyrics_mode.setChecked(self._lyrics_mode)
        # тема из конструктора со своим оформлением текста: фон, слои, эффекты, раскладка — его
        self._custom_mode_switch()
        if self._lyrics_mode:
            # ВХОД: overlay проявляется, диск летит в колонку, а транспорт под
            # overlay плавно гаснет (не прячется — иначе layout перескакивает).
            self.lyrics_view.enter()
            self._stage.set_covered(True)
            for w in self._lyrics_fade_targets():
                if not w.property("echoesFree"):          # тема поставила его поверх текста
                    self.lyrics_view.fade_external(w, out=True, ms=280)
            if self._lyrics_custom_on():
                self.native_layout().raise_free()
                if self._crt is not None:
                    self._crt.raise_overlay()
        else:
            # ВЫХОД: overlay растворяется одновременно с полётом диска назад,
            # транспорт проявляется в том же ритме.
            self._stage.set_covered(False)
            self.lyrics_view.leave()
            for w in self._lyrics_fade_targets():
                w.show()
                self.lyrics_view.fade_external(w, out=False, ms=620)
        self._custom_ui_restore()
        st = self.__dict__.get("_studio")
        try:
            if st is not None and st.isVisible() and hasattr(st, "player_lyrics_changed"):
                st.player_lyrics_changed(self._lyrics_mode)
        except RuntimeError:
            pass

    def _show_queue_popup(self):
        """Показывает всплывающее окно с текущей очередью воспроизведения."""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton
        tracks = self.library if self.queue_context == "library" else \
                 self.playlists.get(self.queue_context, {}).get("tracks", [])
        if not tracks and not self.user_queue:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Очередь воспроизведения")
        dlg.setMinimumSize(360, 480)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(8)

        if self.user_queue:
            hdr = QLabel("Дальше — ваша очередь (играет раньше остального)")
            hdr.setObjectName("Sub")
            lay.addWidget(hdr)
            ulst = QListWidget()
            ulst.setMaximumHeight(150)
            urow_w = QWidget()

            def fill_u():
                ulst.clear()
                for k, qt in enumerate(self.user_queue):
                    ulst.addItem(f"{k + 1}. {sanitize_title(qt.get('title', ''))}  ·  {qt.get('artist', '')}")
                for w_ in (hdr, ulst, urow_w):
                    w_.setVisible(bool(self.user_queue))

            def u_remove():
                r = ulst.currentRow()
                if 0 <= r < len(self.user_queue):
                    self.user_queue.pop(r)
                    fill_u()

            def u_clear():
                self.user_queue.clear()
                fill_u()

            def u_play(item):
                r = ulst.row(item)
                if 0 <= r < len(self.user_queue):
                    self.user_queue.insert(0, self.user_queue.pop(r))
                    self._play_from_queue()
                    dlg.close()
            urow = QHBoxLayout(urow_w)
            urow.setContentsMargins(0, 0, 0, 0)
            b_rm = QPushButton("Убрать выбранный"); b_rm.clicked.connect(u_remove)
            b_cl = QPushButton("Очистить очередь"); b_cl.clicked.connect(u_clear)
            urow.addWidget(b_rm); urow.addWidget(b_cl)
            ulst.itemDoubleClicked.connect(u_play)
            fill_u()
            lay.addWidget(ulst)
            lay.addWidget(urow_w)

        mode_lbl = QLabel("Случайная очередь" if self.shuffle else "Линейная очередь")
        mode_lbl.setObjectName("Sub")
        lay.addWidget(mode_lbl)

        lst = QListWidget()
        lst.setObjectName("QueueList")

        if self.shuffle and self._shuffle_queue:
            # Показываем shuffle queue с текущей позицией
            for pos, track_idx in enumerate(self._shuffle_queue):
                if not (0 <= track_idx < len(tracks)):
                    continue
                t = tracks[track_idx]
                title = sanitize_title(t.get("title", "Untitled"))
                artist = t.get("artist") or "Unknown artist"
                is_current = (pos == self._shuffle_pos)
                text = f"{pos + 1:02d}. {title}  ·  {artist}"
                item = QListWidgetItem(text)
                if is_current:
                    item.setForeground(QColor("#a78bfa"))
                elif pos < self._shuffle_pos:
                    # Уже сыгравшие — приглушённо
                    item.setForeground(QColor("#6b7280"))
                lst.addItem(item)
            if self._shuffle_pos >= 0:
                lst.scrollToItem(lst.item(self._shuffle_pos), QAbstractItemView.ScrollHint.PositionAtCenter)
        else:
            # Линейная очередь
            for i, t in enumerate(tracks):
                title = sanitize_title(t.get("title", "Untitled"))
                artist = t.get("artist") or "Unknown artist"
                is_current = (i == self.current_index)
                text = f"{i + 1:02d}. {title}  ·  {artist}"
                item = QListWidgetItem(text)
                if is_current:
                    item.setForeground(QColor("#a78bfa"))
                elif i < self.current_index:
                    item.setForeground(QColor("#6b7280"))
                lst.addItem(item)
            if self.current_index >= 0:
                lst.scrollToItem(lst.item(self.current_index), QAbstractItemView.ScrollHint.PositionAtCenter)

        # По двойному клику — перейти к треку
        def _on_item_double_clicked(item):
            row = lst.row(item)
            if self.shuffle and self._shuffle_queue and row < len(self._shuffle_queue):
                track_idx = self._shuffle_queue[row]
                self._shuffle_pos = row
                # Позиция в очереди уже выставлена строкой выше — очередь
                # пересобирать не нужно, просто переходим на выбранный трек.
                self._play_index(track_idx, self.queue_context, rebuild_shuffle=False)
            else:
                self._play_index(row, self.queue_context)
            dlg.close()

        lst.itemDoubleClicked.connect(_on_item_double_clicked)
        lay.addWidget(lst, 1)

        hint = QLabel("Двойной клик — перейти к треку")
        hint.setObjectName("Sub")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(hint)

        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(dlg.close)
        lay.addWidget(close_btn)

        inapp.present(self, dlg, "Очередь воспроизведения")

    def _on_lyrics_left(self):
        """LyricsView: диск вернулся на своё место в раскладке."""
        if self._lyrics_mode:
            return                            # успели снова открыть текст
        for w in self._lyrics_fade_targets():
            w.show()
            if isinstance(w.graphicsEffect(), QGraphicsOpacityEffect) and w.graphicsEffect().opacity() >= 0.99:
                w.setGraphicsEffect(None)
        if not getattr(self, "_playlist_detail_open", False):
            self.transport_bar.show()
            self._normal_widget.show()
        self.btn_lyrics_mode.show()
        layout = self._normal_widget.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()
        self._custom_elements()                  # тема из конструктора могла прятать диск/визуализатор
        nl = self.__dict__.get("_native")
        if self._custom_on and nl is not None:   # пластинка вернулась — её место по теме (могла быть вынута)
            try:
                nl.apply(nl.spec)
            except Exception:                    # noqa: BLE001
                traceback.print_exc()
        st = self.__dict__.get("_studio")
        try:
            if st is not None and st.canvas is not None:
                st.canvas.update()
        except RuntimeError:
            pass

    def _anim_panel(self, widget, hide: bool):
        eff = widget.graphicsEffect()
        if not isinstance(eff, QGraphicsOpacityEffect):
            eff = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", widget)
        anim.setDuration(320)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        if hide:
            anim.setStartValue(1.0)
            anim.setEndValue(0.0)
            anim.finished.connect(lambda: widget.hide())
        else:
            widget.show()
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _bind_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key.Key_Space),self,activated=self.toggle_play)
        QShortcut(QKeySequence(Qt.Key.Key_Right),self,activated=self.next_track)
        QShortcut(QKeySequence(Qt.Key.Key_Left),self,activated=self.prev_track)
        QShortcut(QKeySequence("Ctrl+O"),self,activated=self._add_files)
        QShortcut(QKeySequence("Ctrl+R"),self,activated=self._cycle_repeat)
        QShortcut(QKeySequence("Ctrl+S"),self,activated=lambda:self.btn_shuffle.click())
        QShortcut(QKeySequence("Ctrl+Shift+S"),self,activated=lambda:self.artist_shuffle())
        QShortcut(QKeySequence("Ctrl+L"),self,activated=lambda: self._load_lyrics(force=True))
        QShortcut(QKeySequence("Ctrl+Shift+L"),self,activated=self._manual_lyrics_search)
        QShortcut(QKeySequence("Ctrl+Shift+K"),self,activated=self._toggle_clip_mode)   # Ctrl+K — палитра команд
        QShortcut(QKeySequence("Ctrl+Shift+N"),self,activated=self._toggle_now_playing)   # «Сейчас играет» во всё окно
        QShortcut(QKeySequence(Qt.Key.Key_F11),self,activated=self._toggle_fullscreen)
        QShortcut(QKeySequence("Ctrl+M"),self,activated=self._open_hub)
        QShortcut(QKeySequence("Ctrl+Shift+T"),self,activated=lambda: self._open_theme_studio())

    def keyPressEvent(self, event):
        """Поддержка мультимедийных клавиш и обычных стрелок/пробела."""
        key = event.key()
        if key in (Qt.Key.Key_MediaPlay, Qt.Key.Key_MediaPause, Qt.Key.Key_MediaTogglePlayPause):
            self.toggle_play()
            event.accept()
            return
        if key == Qt.Key.Key_MediaNext:
            self.next_track()
            event.accept()
            return
        if key == Qt.Key.Key_MediaPrevious:
            self.prev_track()
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_eq_band(self, band_index, value):
        self.engine.set_eq_band(band_index, float(value) + self._bass_add()[band_index])
        if not self._eq_loading:                           # двигаем руками — это уже «Вручную»
            self._eq_auto_active = False
            self.eq_auto_lbl.hide()
            self.eq_preset_cb.blockSignals(True)
            self.eq_preset_cb.setCurrentIndex(0)
            self.eq_preset_cb.blockSignals(False)
            self.eq_del_btn.setEnabled(False)
            self._eq_persist("")

    # ── Басс буст (панель «Звук» в плеере): прибавка к низким полосам эквалайзера в движке.
    #    Ползунки EQ, пресеты и автопресет по жанру остаются как есть: звучит «ползунок + буст». ── #

    BASS_CURVE = (12, 10, 6, 2, 0, 0, 0, 0, 0, 0)            # дБ при 100 %: 31, 62, 125, 250 Гц

    def _bass_add(self):
        """Прибавка к полосам эквалайзера: басс буст + поправка под модель наушников (hp_eq)."""
        k = max(0, min(100, int(self.settings.get("bass_boost", 0) or 0))) / 100.0
        import hp_eq
        hp = hp_eq.correction(self.settings.get("hp_profile", ""))
        return [round(g * k + h, 1) for g, h in zip(self.BASS_CURVE, hp)]

    def set_hp_profile(self, name):
        """Наушники для эквалайзера («» — без поправки)."""
        self.settings["hp_profile"] = name or ""
        self._eq_save_timer.start(500)
        self._bass_apply()

    def bass_boost(self) -> int:
        return max(0, min(100, int(self.settings.get("bass_boost", 0) or 0)))

    def set_bass_boost(self, pct):
        pct = max(0, min(100, int(pct)))
        if pct != self.bass_boost():
            self.settings["bass_boost"] = pct
            self._eq_save_timer.start(500)
        self._bass_apply()

    def _bass_apply(self):
        add = self._bass_add()
        k = self.bass_boost() / 100.0
        if self.engine.set_bass(k):                          # свой вывод: умный бас (низы + гармоники, без лимитера)
            import hp_eq
            add = list(hp_eq.correction(self.settings.get("hp_profile", "")))
        sliders = getattr(self, "_eq_sliders", None) or []
        for i in range(10):
            base = sliders[i].value() if i < len(sliders) else 0
            self.engine.set_eq_band(i, float(base) + add[i])

    def eq_effective(self):
        """Что реально звучит по полосам: ползунок эквалайзера + басс буст (для мини-эквалайзера панели)."""
        add = self._bass_add()
        sliders = getattr(self, "_eq_sliders", None) or []
        return [max(-20.0, min(20.0, (sliders[i].value() if i < len(sliders) else 0) + add[i])) for i in range(10)]

    # ── пресеты эквалайзера ── #

    def _eq_user_presets(self) -> dict:
        return self.settings.setdefault("eq_user_presets", {})

    def _eq_fill_combo(self, select: str = ""):
        cb = self.eq_preset_cb
        cb.blockSignals(True)
        cb.clear()
        cb.addItem("Вручную", None)
        for name, gains in EQ_PRESETS:
            cb.addItem(name, list(gains))
        for name, gains in self._eq_user_presets().items():
            cb.addItem("★ " + name, list(gains))
        i = cb.findText(select) if select else 0
        cb.setCurrentIndex(max(0, i))
        cb.blockSignals(False)
        self.eq_del_btn.setEnabled(cb.currentText().startswith("★ "))

    def _eq_set_gains(self, gains):
        self._eq_loading = True
        try:
            for sl, lb, g in zip(self._eq_sliders, self._eq_labels, gains):
                sl.setValue(int(g))                         # valueChanged сам обновит движок и подпись
                lb.setText(str(int(g)))
        finally:
            self._eq_loading = False

    def _eq_persist(self, preset_name):
        self.settings["eq_gains"] = [sl.value() for sl in self._eq_sliders]
        self.settings["eq_preset"] = preset_name
        self._eq_save_timer.start(500)

    def _on_eq_preset_picked(self, idx):
        gains = self.eq_preset_cb.itemData(idx)
        name = self.eq_preset_cb.currentText()
        self.eq_del_btn.setEnabled(name.startswith("★ "))
        if gains is None:
            return
        self._eq_auto_active = False                       # пресет выбран руками — «авто» не вмешивается
        self.eq_auto_lbl.hide()
        self._eq_set_gains(gains)
        self._eq_persist(name)

    # ── автопресет по жанру ── #

    def _eq_track_families(self, t):
        prof = (getattr(self, "_intel_profiles", None) or {}).get(str(t.get("path", "")))
        if prof and prof.get("families"):
            return prof["families"]
        store = self._intel_store()
        if store is None or music_intel is None:
            return []
        m, ar = store.meta(t)
        raw = [t.get("genre", "")] + ((m or {}).get("genres") or []) + ((m or {}).get("tags") or []) \
            + ((ar or {}).get("tags") or [])
        return music_intel.genre_families(raw)

    def _eq_auto_apply(self, t):
        """Трек сменился: подобрать пресет по жанру (если функция включена), иначе вернуть ручные настройки."""
        if not self.settings.get("eq_auto_genre", False) or not hasattr(self, "_eq_sliders") or not t:
            return
        fam = next((f for f in self._eq_track_families(t) if f in EQ_BY_FAMILY), None)
        preset = EQ_BY_FAMILY.get(fam) if fam else None
        gains = dict(EQ_PRESETS).get(preset) if preset else None
        if gains is None:
            self._eq_auto_release()
            return
        if not self._eq_auto_active:
            self._eq_manual = [sl.value() for sl in self._eq_sliders]
            self._eq_manual_preset = self.eq_preset_cb.currentText()
            self._eq_auto_active = True
        self._eq_set_gains(gains)
        self.eq_preset_cb.blockSignals(True)
        self.eq_preset_cb.setCurrentIndex(max(0, self.eq_preset_cb.findText(preset)))
        self.eq_preset_cb.blockSignals(False)
        ru = music_intel.GENRE_RU.get(fam, fam) if music_intel is not None else fam
        self.eq_auto_lbl.setText(f"Авто: жанр «{ru}» → пресет «{preset}»")
        self.eq_auto_lbl.show()

    def _eq_auto_release(self):
        if not self._eq_auto_active:
            return
        self._eq_auto_active = False
        self._eq_set_gains(self._eq_manual or [0] * 10)
        i = self.eq_preset_cb.findText(self._eq_manual_preset) if self._eq_manual_preset else 0
        self.eq_preset_cb.blockSignals(True)
        self.eq_preset_cb.setCurrentIndex(max(0, i))
        self.eq_preset_cb.blockSignals(False)
        self.eq_auto_lbl.hide()

    def _on_eq_auto_toggled(self, state):
        self.settings["eq_auto_genre"] = bool(state)
        save_json(SETTINGS_FILE, self.settings)
        if state:
            tracks = self.library if self.queue_context == "library" else \
                self.playlists.get(self.queue_context, {}).get("tracks", [])
            if 0 <= self.current_index < len(tracks):
                self._eq_auto_apply(tracks[self.current_index])
            self._toast("Автопресет по жанру включён")
        else:
            self._eq_auto_release()
            self._toast("Автопресет по жанру выключен")

    def _eq_restore(self):
        gains = self.settings.get("eq_gains")
        if isinstance(gains, list) and len(gains) == 10:
            self._eq_set_gains(gains)
            name = self.settings.get("eq_preset", "")
            i = self.eq_preset_cb.findText(name) if name else 0
            self.eq_preset_cb.blockSignals(True)
            self.eq_preset_cb.setCurrentIndex(max(0, i))
            self.eq_preset_cb.blockSignals(False)
            self.eq_del_btn.setEnabled(self.eq_preset_cb.currentText().startswith("★ "))

    def _eq_save_preset(self):
        name, ok = QInputDialog.getText(self, "Свой пресет", "Название пресета:")
        name = (name or "").strip()[:30]
        if not ok or not name:
            return
        if name in dict(EQ_PRESETS):
            name += " (мой)"
        self._eq_user_presets()[name] = [sl.value() for sl in self._eq_sliders]
        self._eq_fill_combo("★ " + name)
        self._eq_persist("★ " + name)
        self._toast(f"Пресет «{name}» сохранён")

    def _eq_delete_preset(self):
        cur = self.eq_preset_cb.currentText()
        if not cur.startswith("★ "):
            return
        self._eq_user_presets().pop(cur[2:], None)
        self._eq_fill_combo()
        self._eq_persist("")
        self._toast("Пресет удалён")

    def _reset_eq(self):
        self.engine.reset_eq()
        self._eq_set_gains([0] * 10)
        self.eq_preset_cb.blockSignals(True)
        self.eq_preset_cb.setCurrentIndex(max(0, self.eq_preset_cb.findText("Плоский")))
        self.eq_preset_cb.blockSignals(False)
        self.eq_del_btn.setEnabled(False)
        self._eq_persist("Плоский")
        self._bass_apply()                                 # сброс EQ не выключает басс буст из панели «Звук»

    def resizeEvent(self, event):
        super().resizeEvent(event)
        crt = getattr(self, "_crt", None)
        if crt is not None and crt.active():
            crt.resize()
        self._place_ui_btn()
        if hasattr(self, 'lyrics_view') and self.centralWidget():
            self.lyrics_view.setGeometry(self.centralWidget().rect())
            self.lyrics_view.parentResized()
        root_rect = self.centralWidget().rect() if self.centralWidget() else None
        if root_rect is not None:
            if hasattr(self, "_ambience"):
                self._ambience.setGeometry(root_rect)
            if hasattr(self, "_dust"):
                self._dust.setGeometry(root_rect)
                self._dust.raise_()
            cm = getattr(self, "_cover_mode", None)
            if cm is not None and cm.isVisible():
                cm.setGeometry(root_rect)
                cm.raise_()

    def eventFilter(self, obj, ev):
        """Перетаскивание треков из библиотеки на плейлист в списке плейлистов;
        встроенная панель конструктора тем сдвинулась/изменилась — тема занимает остальное окно;
        список с недогруженными обложками показался — догрузить."""
        if ev.type() == QEvent.Type.Show:
            waiting = self.__dict__.get("_lazy_icon_wait")
            if waiting and obj in waiting:
                side, size = waiting.pop(obj)
                obj.removeEventFilter(self)
                QTimer.singleShot(0, lambda o=obj, s=side, z=size: self._lazy_icons_kick(o, s, z))
                return False
        if obj is self.__dict__.get("_studio_dock") and ev.type() in (
                QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show, QEvent.Type.Hide):
            QTimer.singleShot(0, self._studio_area_changed)
            return False
        pl = getattr(self, "pl_list", None)
        try:
            is_pl = pl is not None and obj is pl.viewport()
        except RuntimeError:
            is_pl = False
        if is_pl:
            et = ev.type()
            if et in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
                if ev.source() is getattr(self, "lib_list", None):
                    it = pl.itemAt(ev.position().toPoint())
                    if it is not None and it.data(Qt.ItemDataRole.UserRole):
                        pl.setCurrentItem(it)
                    ev.acceptProposedAction()
                    return True
            elif et == QEvent.Type.Drop and ev.source() is getattr(self, "lib_list", None):
                it = pl.itemAt(ev.position().toPoint())
                name = it.data(Qt.ItemDataRole.UserRole) if it is not None else None
                if name:
                    tracks = [x.data(Qt.ItemDataRole.UserRole) for x in self.lib_list.selectedItems()]
                    n = self.playlist_add_tracks(name, [t for t in tracks if t])
                    from PyQt6.QtWidgets import QToolTip
                    QToolTip.showText(pl.viewport().mapToGlobal(ev.position().toPoint()),
                                      f"Добавлено в «{name}»: {n}" if n else f"Уже есть в «{name}»", pl)
                ev.acceptProposedAction()
                return True
        return super().eventFilter(obj, ev)

    def closeEvent(self,event):
        tr = getattr(self, "_tray", None)
        if tr is not None and not getattr(self, "_really_quit", False) and self.settings.get("close_to_tray", True):
            event.ignore()                           # крестик — в трей, музыка и Echoes.NET работают дальше
            tr.hide_window()
            return
        montage = getattr(self, "_montage", None)
        if montage is not None:
            if not montage.request_close(self.close):
                event.ignore()
                return
            self._leave_montage_layout()
        # открыт конструктор тем с несохранённой темой — спросить, прежде чем всё закрыть
        st = self._studio
        try:
            if st is not None and st.isVisible() and not st.confirm_app_close():
                event.ignore()
                return
        except RuntimeError:
            pass
        try: self.save_settings()
        except Exception: pass
        try: self.stats.save()
        except Exception: pass
        try:                                     # студия открыта — сохранить проект и остановить её потоки
            if getattr(self, "_daw", None) is not None:
                self._daw.shutdown()
        except Exception: pass
        try:
            self._close_hub()
        except Exception: pass
        try:
            if hasattr(self, "media_filter"):
                self.media_filter.unregister()
                QApplication.instance().removeNativeEventFilter(self.media_filter)
        except Exception: pass
        try:self.noise_gen.stop()
        except Exception:pass
        try:
            w = getattr(self, "_intel_worker", None)
            if w is not None:
                w.stop()
                if self._intel is not None:
                    self._intel.save(force=True)
        except Exception:pass
        try:
            if self._downloader_dialog is not None and self._downloader_dialog.manager.busy:
                self._downloader_dialog.manager.cancel()
        except Exception:pass
        try:self.engine.stop();self.engine.shutdown()
        except Exception:pass
        try:self._autotag_flush(all_=True)               # найденные теги играющего трека — в файл, раз он закрыт
        except Exception:pass
        try:
            # Удаляем временный файл реверба если он остался
            self.engine._cleanup_preset_temp()
        except Exception:pass
        try:
            if hasattr(self, "discord_rpc") and self.discord_rpc:
                self.discord_rpc.stop()
        except Exception:pass
        try:                                     # конструктор тем: таймеры, GIF и видео-обои — остановить до выхода
            if self._studio is not None:
                self._studio.set_canvas(False)
                self._studio.hide()
            if self._crt is not None:
                self._crt.clear()
        except Exception:pass
        try:
            for name in ('_ya',):
                shell=getattr(self,name,None)
                if shell is not None:shell.shutdown()
            import ya_wave,frameclock
            ya_wave.shutdown_workers()
            frameclock.clock().shutdown()
        except Exception:pass
        try:
            if getattr(self, "_tray", None) is not None:
                self._tray.icon.hide()
        except Exception:pass
        event.accept()
        QTimer.singleShot(0, QApplication.instance().quit)   # трей отключил выход по закрытию окна

def _install_crash_logging():
    """Любая ошибка — и Python, и нативный краш Qt — пишется в
    ~/Echoes/crash.log (и в консоль), а не теряется молча."""
    import faulthandler
    log_path = DATA_DIR / "crash.log"
    # лог не растёт бесконечно: от старых запусков остаётся только хвост
    try:
        if log_path.exists() and log_path.stat().st_size > 2_000_000:
            with open(log_path, "rb") as f:
                f.seek(-300_000, 2)
                tail = f.read()
            log_path.write_bytes(tail[tail.find(b"\n") + 1:])
    except Exception:
        pass
    log = open(log_path, "a", encoding="utf-8", buffering=1)
    log.write(f"\n===== запуск {datetime.datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
    # нативные падения (segfault/access violation): стек всех потоков
    faulthandler.enable(file=log, all_threads=True)
    seen = {}

    def once(key):
        """Одинаковая ошибка пишется 3 раза, дальше — только счётчик (каждая 500-я)."""
        n = seen.get(key, 0) + 1
        seen[key] = n
        return n <= 3 or n % 500 == 0, n

    def hook(etype, value, tb):
        text = "".join(traceback.format_exception(etype, value, tb))
        # локальные переменные упавших кадров (QPainter!) отпускаем сразу: иначе
        # рисовальщик остаётся «занятым» и ломает все следующие кадры виджета
        try:
            traceback.clear_frames(tb)
        except Exception:
            pass
        sys.last_traceback = sys.last_value = sys.last_type = None
        ok, n = once(text)
        if not ok:
            return
        if n > 3:
            text = f"[повтор ×{n}] " + text.strip().splitlines()[-1] + "\n"
        try:
            sys.__stderr__.write(text)
        except Exception:
            pass
        log.write(text)
        log.flush()
        # собственный excepthook: PyQt6 больше не закрывает программу на
        # ошибке в обработчике — она просто пишется в лог
    sys.excepthook = hook

    try:
        from PyQt6.QtCore import qInstallMessageHandler

        def qt_msg(mode, ctx, msg):
            ok, n = once(msg)
            if not ok:
                return
            line = f"[Qt {mode.name}] {msg}\n" if n <= 3 else f"[Qt {mode.name}] [повтор ×{n}] {msg}\n"
            try:
                sys.__stderr__.write(line)
            except Exception:
                pass
            log.write(line)
        qInstallMessageHandler(qt_msg)
    except Exception:
        pass
    return log_path


def _resource(name: str) -> Path:
    """Файл рядом с программой — и в .exe (PyInstaller кладёт данные в _MEIPASS)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def _app_icon():
    for n in ("icon.ico", "icon.png"):
        p = _resource(n)
        if p.exists():
            return QIcon(str(p))
    return None


if __name__=="__main__":
    _strace.mark("imports")
    _CRASH_LOG = _install_crash_logging()
    print(f"[neon] лог ошибок: {_CRASH_LOG}")
    if sys.platform.startswith("win"):
        # своя «личность» на панели задач — иначе Windows покажет иконку python.exe
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("echoes.player")
        except Exception:
            pass
    # свой аудиовывод (точный gapless) можно выключить в настройках
    try:
        if not json.loads(Path(SETTINGS_FILE).read_text("utf-8")).get("own_audio_output", True):
            _os.environ["ECHOES_AUDIO_BACKEND"] = "vlc"
    except Exception:                                    # noqa: BLE001
        pass
    # язык интерфейса (Русский / English) — до создания окон
    try:
        import i18n
        i18n.install(i18n.read_language(SETTINGS_FILE))
    except Exception as e:                               # noqa: BLE001
        i18n = None
        print("[i18n]", e)
    # Qt logical scaling covers all themes, custom painting and native controls.
    import ui_scale
    ui_scale.configure_environment(SETTINGS_FILE)
    try:                                               # GPU-слои (туманность и т. п.): без вертикальной синхронизации
        # OpenGL — кадры и так идут в ритме экрана (frameclock); со «swap interval 1» поток интерфейса
        # ждал кадр второй раз и терял половину частоты
        from PyQt6.QtGui import QSurfaceFormat
        _fmt = QSurfaceFormat.defaultFormat()
        _fmt.setSwapInterval(0)
        QSurfaceFormat.setDefaultFormat(_fmt)
    except Exception as _e:                            # noqa: BLE001
        print("[gpu] format:", _e)
    app=QApplication(sys.argv)
    _strace.mark("qapp")
    try:                                               # без случайных «окошек» у кнопок (noflash)
        noflash.install_qt_guard(app)
    except Exception as _e:                            # noqa: BLE001
        print("[noflash] qt:", _e)
    ui_scale.install_font_scale(app, SETTINGS_FILE)
    app.setApplicationName("ECHOES")
    # Windows 10: стандартный стиль «windowsvista» рисует поля, списки и диалоги системной светлой
    # палитрой (белый фон) поверх нашего QSS с белым текстом. Fusion берёт цвета из палитры темы.
    app.setStyle("Fusion")
    try:                                               # колесо мыши нажали — прокрутка как в браузере
        import autoscroll
        autoscroll.install(app)
    except Exception as e:                             # noqa: BLE001
        print("[autoscroll]", e)
    if i18n is not None:
        i18n.start(app)
    _ic = _app_icon()
    if _ic is not None:
        app.setWindowIcon(_ic)
    load_fonts()          # шрифты из ./fonts (рекомендуется Unbounded)
    try:                  # плеер уже открыт (или спрятан в трее) — показать его, второй не запускать
        import single_instance
        _single = single_instance.claim()
        if _single is None:
            sys.exit(0)
    except SystemExit:
        raise
    except Exception as _e:                            # noqa: BLE001
        print("[single]", _e); _single = None
    try:                  # какой это ПК: без видеокарты — без GPU-слоёв, слабый — лёгкий режим (sysprobe.py)
        import sysprobe
        _ps = json.loads(SETTINGS_FILE.read_text("utf-8")) if SETTINGS_FILE.exists() else {}
        _before = json.dumps({k: _ps.get(k) for k in ("sys_probe_sig", "sys_probe", "lite_mode", "motion_profile")})
        sysprobe.apply_startup(_ps)
        if json.dumps({k: _ps.get(k) for k in ("sys_probe_sig", "sys_probe", "lite_mode", "motion_profile")}) != _before                 or not SETTINGS_FILE.exists():
            save_json(SETTINGS_FILE, _ps)
    except Exception as _e:                            # noqa: BLE001
        print("[sys]", _e)
    _native_intro = False
    try:                  # заставка в своём потоке — сразу, пока строится окно (intro_win.cpp)
        import intro_anim
        _st = load_json(SETTINGS_FILE, {})             # с учётом ещё не записанного (запись — в фоне)
        if intro_anim.enabled(_st):
            _native_intro = intro_anim.start_native()
    except Exception as _e:                            # noqa: BLE001
        print("[intro]", _e)
    _strace.mark("before_window")
    win=_strace.build(MainWindow)
    _strace.mark("window_built")
    try:                  # заставка: солнце с вылетающими лучами и надпись ECHOES (Настройки → Оформление)
        import intro_anim
        if intro_anim.enabled(win.settings) and not _native_intro:
            intro_anim.play(win)                       # без DLL — прежняя заставка поверх окна
    except Exception as _e:                            # noqa: BLE001
        print("[intro]", _e)
    try:                                               # окно сразу с GPU-совмещением: иначе первый GPU-слой
        import ya_wave                                 # («Моя волна») пересоздавал окно — оно мигало
        ya_wave.gpu_anchor(win)
    except Exception as _e:                            # noqa: BLE001
        print("[gpu] anchor:", _e)
    win.show()
    _strace.mark("shown")
    _strace.after_show(win)
    try:                  # запуск удался — откат больше не нужен; после отката — сказать почему
        import boot_guard
        QTimer.singleShot(15000, boot_guard.mark_ok)
        import onboarding                              # новичку — три шага: музыка, плейлисты, вид
        QTimer.singleShot(1200, lambda: onboarding.maybe_show(win))
        import crash_report                            # вылеты с прошлого раза — спросить, отправить ли автору
        QTimer.singleShot(9000, lambda: crash_report.check_on_start(win))
        _rb = boot_guard.rolled_back_notice()
        if _rb:
            QTimer.singleShot(4000, lambda: win._toast(_rb))
    except Exception as _e:                            # noqa: BLE001
        print("[boot]", _e)
    if _native_intro:     # за заставкой — загрузить всё заранее, потом она растворится
        try:
            import intro_anim, warmup
            intro_anim.follow(win)
            warmup.preload(win)
        except Exception as _e:                        # noqa: BLE001
            print("[preload]", _e)
        finally:
            intro_anim.ready()
    try:                  # сторож плавности: долго меньше ~15 к/с — сам включит лёгкий режим
        import sysprobe
        sysprobe.install_guard(win)
    except Exception as _e:                            # noqa: BLE001
        print("[sys] guard:", _e)
    try:                  # прогрев: первое открытие разделов — без подлагиваний (warmup.py)
        import warmup
        warmup.start(win)
    except Exception as _e:                            # noqa: BLE001
        print("[warmup]", _e)
    try:                  # новая версия на GitHub — кнопка «Обновить» в шапке (github_update.py)
        import github_update
        github_update.install(win)
    except Exception as _e:                            # noqa: BLE001
        print("[github update]", _e)
    try:
        single_instance.serve(_single, lambda: (win._tray.show_window() if getattr(win, "_tray", None)
                                               else __import__("ui_anim").bring_front(win)))
    except Exception as _e:                            # noqa: BLE001
        print("[single]", _e)
    if sys.platform.startswith("win"):
        # окну — команду запуска, значок и имя: «закрепить на панели задач» даст правильный ярлык
        def _identity():
            try:
                import taskbar_identity
                taskbar_identity.apply(win, Path(__file__).resolve().parent)
            except Exception as e:                       # noqa: BLE001
                print("[taskbar]", e)
        QTimer.singleShot(700, _identity)
    _code = app.exec()
    try:
        import boot_guard
        boot_guard.mark_ok()                           # обычный выход — тоже удачный запуск
    except Exception:                                  # noqa: BLE001
        pass
    try:                                               # настройки и библиотека пишутся в фоне — дописать
        import atomic_json
        atomic_json.flush(8.0)
    except Exception:                                  # noqa: BLE001
        pass
    # closeEvent останавливает аудио и графические потоки до финализации Qt.
    # Не используем os._exit: он обходит очистку Python/Qt и вызывал нативный
    # сбой при выгрузке библиотек после открытия конструктора и смены тем.
    # Недемоническим потокам записи даём закончить сохранение.
    try:
        import threading as _th
        _deadline = __import__("time").monotonic() + 4.0
        for _t in _th.enumerate():
            if _t is not _th.main_thread() and not _t.daemon and _t.is_alive():
                _t.join(max(0.0, _deadline - __import__("time").monotonic()))
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:                                    # noqa: BLE001
        pass
    sys.exit(_code)
