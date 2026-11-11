"""Где интерфейс «замирает»: настоящий плеер на КОПИИ профиля, сторож ловит каждую паузу потока окна.

python qa/probe_hitches.py [--offscreen] [--synthetic] [--ms 34] [--out файл.json] [сценарий ...]

Поток окна каждые 4 мс ставит отметку. Сторож в другом потоке видит, что отметки нет дольше --ms,
и записывает стек потока окна (каждые 4 мс, пока пауза не кончится) — так у каждой паузы есть виновник.
Профиль: JSON-файлы из ~/Echoes копируются во временную папку (настоящие не меняются), сеть закрыта,
Discord/медиасессия/трей выключены, громкость 0. --synthetic — без настоящего профиля (CI).
"""
import collections
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import threading
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(ROOT / "app"))
ARGS = sys.argv[1:]


def _opt(name, default=None):
    if name in ARGS:
        i = ARGS.index(name)
        val = ARGS[i + 1]
        del ARGS[i:i + 2]
        return val
    return default


LIMIT_MS = float(_opt("--ms", "34"))
OUT = _opt("--out", str(ROOT / "qa" / "results" / "hitches.json"))
OFFSCREEN = "--offscreen" in ARGS
SYNTH = "--synthetic" in ARGS
ONLY = [a for a in ARGS if not a.startswith("--")]

real_home = Path.home()
installed = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "ECHOES"
for directory in (installed / "vlc", installed / "ffmpeg"):
    os.environ["PATH"] = str(directory) + os.pathsep + os.environ["PATH"]
os.environ["PYTHON_VLC_LIB_PATH"] = str(installed / "vlc" / "libvlc.dll")
if OFFSCREEN:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["ECHOES_SPOKEN_OFFLINE"] = "1"
temporary = tempfile.TemporaryDirectory(prefix="echoes-hitch-", ignore_cleanup_errors=True)
home = Path(temporary.name)
data = home / "Echoes"
data.mkdir()
real = real_home / "Echoes"
settings = {}
if not SYNTH and (real / "settings.json").exists():
    for f in real.glob("*.json"):
        if f.stat().st_size < 32 * 2 ** 20 and not f.name.endswith(".bak"):
            shutil.copy2(f, data / f.name)
    for sub in ("ui_cache", "wave_cache", "state", "fonts", "avatar"):
        if (real / sub).is_dir():
            shutil.copytree(real / sub, data / sub, dirs_exist_ok=True)
    settings = json.loads((data / "settings.json").read_text("utf-8-sig"))
else:
    import wave
    tracks = []
    for index in range(700):
        path = home / f"synthetic-{index}.wav"
        with wave.open(str(path), "wb") as output:
            output.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
            output.writeframes(b"\0\0" * 8000 * 20)
        tracks.append(dict(path=str(path), title=f"Song {index}", artist=f"Artist {index % 40}",
                           album=f"Album {index % 60}", duration=20))
    (data / "library.json").write_text(json.dumps(tracks), "utf-8")
    settings = {"theme": "Echoes Music", "ya_page": "collection", "language": "ru", "onboarded": True}
settings.update(discord_rpc=False, media_session=False, close_to_tray=False, intro_enabled=False,
                voice_cmd_always=False, volume=0, keybinds_global=False, onboarded=True, tray_hinted=True)
settings.pop("win_size", None)
(data / "settings.json").write_text(json.dumps(settings), "utf-8")
Path.home = classmethod(lambda cls: home)
for var, val in (("USERPROFILE", home), ("HOME", home), ("APPDATA", home / "roaming"), ("LOCALAPPDATA", home / "local")):
    os.environ[var] = str(val)


def no_network(*a, **k):
    raise OSError("сеть закрыта (probe_hitches)")


socket.socket.connect = no_network
socket.create_connection = no_network
socket.getaddrinfo = no_network

# ── сторож ──────────────────────────────────────────────────────────────────────────────────────
MAIN_ID = threading.get_ident()
beat = [time.perf_counter()]
label = ["import"]
stalls = []
_run = [True]
APP_DIR = str(ROOT / "app")


def _frames(frame):
    out = []
    while frame is not None:
        fn = frame.f_code.co_filename
        if fn.startswith(APP_DIR):
            out.append(f"{os.path.basename(fn)}:{frame.f_lineno} {frame.f_code.co_name}")
        frame = frame.f_back
    return out                                              # от самого глубокого кадра к внешнему


def watchdog():
    cur = None
    while _run[0]:
        time.sleep(0.004)
        now = time.perf_counter()
        gap = (now - beat[0]) * 1000
        if gap > LIMIT_MS:
            if cur is None or cur["beat"] != beat[0]:
                if cur is not None:
                    stalls.append(cur)
                cur = {"beat": beat[0], "label": label[0], "ms": gap, "stacks": collections.Counter(),
                       "others": collections.Counter()}
            cur["ms"] = gap
            frames = sys._current_frames()
            st = _frames(frames.get(MAIN_ID))
            cur["stacks"][" < ".join(st[:7]) or "(Qt/C++ без кода плеера)"] += 1
            me = threading.get_ident()
            for tid, fr in frames.items():                  # чем в это время заняты ДРУГИЕ потоки (кто держит GIL)
                if tid in (MAIN_ID, me):
                    continue
                o = _frames(fr)
                if o and not o[0].startswith(("atomic_json.py", "bgproc.py")):
                    cur["others"][" < ".join(o[:3])] += 1
        elif cur is not None:
            stalls.append(cur)
            cur = None
    if cur is not None:
        stalls.append(cur)


threading.Thread(target=watchdog, daemon=True, name="hitch-watchdog").start()

import gc
gc_log = []                                                 # сборки мусора дольше 4 мс: (поколение, мс, сценарий)
_gc_t = [0.0]


def _gc_cb(phase, info):
    if phase == "start":
        _gc_t[0] = time.perf_counter()
    else:
        ms = (time.perf_counter() - _gc_t[0]) * 1000
        if ms > 4:
            gc_log.append([info.get("generation"), round(ms, 1), label[0]])


gc.callbacks.append(_gc_cb)

from PyQt6.QtCore import QEventLoop, QPoint, QPointF, Qt, QTimer, qInstallMessageHandler
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

errors = []


def exception_hook(kind, value, tb):
    errors.append("".join(traceback.format_exception(kind, value, tb))[-2500:])
    print(errors[-1], flush=True)


sys.excepthook = exception_hook
qInstallMessageHandler(lambda *a: None)
import i18n
i18n.install(settings.get("language", "ru"))
app = QApplication([])
app.setStyle("Fusion")
i18n.start(app)
hb = QTimer()
hb.setTimerType(Qt.TimerType.PreciseTimer)
hb.timeout.connect(lambda: beat.__setitem__(0, time.perf_counter()))
hb.start(4)
timings = {}


def pump(seconds):
    until = time.perf_counter() + seconds
    while time.perf_counter() < until:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 8)
        beat[0] = time.perf_counter()
        time.sleep(0.001)


def scenario(name, fn, settle=1.0):
    if ONLY and not any(name.startswith(o) for o in ONLY) and name != "startup":
        return
    label[0] = name
    beat[0] = time.perf_counter()
    start = time.perf_counter()
    try:
        fn()
    except Exception:                                       # noqa: BLE001
        errors.append(name + ": " + traceback.format_exc()[-2500:])
        print(errors[-1], flush=True)
    timings[name] = round((time.perf_counter() - start) * 1000, 1)
    beat[0] = time.perf_counter()
    pump(settle)
    print(f"· {name}: {timings[name]} мс", flush=True)


import main
main.WindowsMediaKeyFilter.register = lambda self: None
win = None
shell = None


def startup():
    global win, shell
    win = main.MainWindow()
    win.resize(1440, 900)
    win.show()
    shell = win._ya


def wheel(view, steps, delta=-120, gap=0.016):
    vp = view.viewport()
    pos = QPointF(vp.width() / 2, vp.height() / 2)
    for _ in range(steps):
        ev = QWheelEvent(pos, QPointF(vp.mapToGlobal(pos.toPoint())), QPoint(0, 0), QPoint(0, delta),
                         Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(vp, ev)
        pump(gap)


def scroll_collection():
    shell.show_page("collection")
    pump(0.4)
    wheel(shell.c_list, 70)
    wheel(shell.c_list, 40, delta=120)
    bar = shell.c_list.verticalScrollBar()
    for frac in (1.0, 0.5, 0.0, 0.8, 0.2):
        bar.setValue(int(bar.maximum() * frac))
        pump(0.25)


def type_search():
    shell.show_page("collection")
    pump(0.2)
    shell.c_search.setFocus()
    for ch in "the love":
        QTest.keyClicks(shell.c_search, ch)
        pump(0.09)
    pump(0.5)
    shell.c_search.clear()
    pump(0.4)


def play(i):
    def run():
        win._play_index(i)
    return run


def page_scroll(key):
    def run():
        page = shell.pages[key]
        if hasattr(page, "verticalScrollBar"):
            wheel(page, 40)
            wheel(page, 25, delta=120)
    return run


def resize_drag():
    for i in range(40):
        win.resize(1440 - i * 12, 900 - i * 6)
        pump(0.016)
    for i in range(40):
        win.resize(960 + i * 12, 660 + i * 6)
        pump(0.016)


def idle(seconds):
    def run():
        busy = 0.0
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            t = time.perf_counter()
            app.processEvents()
            busy += time.perf_counter() - t
            beat[0] = time.perf_counter()
            time.sleep(0.002)
        timings["busy%:" + label[0]] = round(busy / seconds * 100, 1)
    return run


try:
    scenario("startup", startup, 4.0)
    keys = [k for k in ("collection", "search", "wave", "foryou", "albums", "follows", "tierlist", "duel", "net",
                        "profile", "queue", "lyrics", "settings", "listening") if k in shell.pages]
    for key in keys:
        scenario("cold:" + key, lambda key=key: shell.show_page(key), 1.3)
    for key in keys:
        scenario("warm:" + key, lambda key=key: shell.show_page(key), 0.7)
    scenario("scroll:collection", scroll_collection, 0.6)
    scenario("search:type", type_search, 0.6)
    for key in ("albums", "foryou", "profile", "wave", "settings"):
        if key in shell.pages:
            scenario("scrollpage:" + key, lambda key=key: (shell.show_page(key), pump(0.6), page_scroll(key)()), 0.5)
    scenario("idle:stopped", idle(4.0), 0.1)
    if win.library:
        scenario("play:first", play(0), 3.0)
        scenario("idle:playing-collection", lambda: (shell.show_page("collection"), pump(0.8), idle(5.0)()), 0.1)
        for n in range(1, 6):
            scenario(f"play:next{n}", win.next_track, 1.6)
        scenario("play:pause", win.toggle_play, 0.6)
        scenario("play:resume", win.toggle_play, 0.8)
        for key in ("lyrics", "wave", "listening", "queue", "profile", "collection"):
            if key in shell.pages:
                scenario("playing:" + key, lambda key=key: shell.show_page(key), 2.0)
        scenario("idle:playing-lyrics", lambda: (shell.show_page("lyrics"), pump(0.8), idle(5.0)()), 0.1)
        scenario("playing:scroll", scroll_collection, 0.6)
    scenario("resize:drag", resize_drag, 0.8)
    hub = getattr(shell, "settings_hub", None)
    if hub is not None:
        shell.show_page("settings")
        pump(0.5)
        for category in list(hub.nav_btns):
            scenario("settings:" + str(category), lambda c=category: hub.select(c), 0.5)
except Exception:                                           # noqa: BLE001
    errors.append(traceback.format_exc())
    print(errors[-1], flush=True)
finally:
    label[0] = "shutdown"
    _run[0] = False
    time.sleep(0.02)
    rows = [{"label": s["label"], "ms": round(s["ms"], 1),
             "stacks": [[n, st] for st, n in s["stacks"].most_common(4)],
             "others": [[n, st] for st, n in s["others"].most_common(6)]} for s in stalls]
    rows.sort(key=lambda r: -r["ms"])
    by = collections.defaultdict(lambda: [0, 0.0, 0.0])
    for r in rows:
        b = by[r["label"]]
        b[0] += 1
        b[1] += r["ms"]
        b[2] = max(b[2], r["ms"])
    summary = {k: {"stalls": v[0], "total_ms": round(v[1]), "worst_ms": round(v[2])}
               for k, v in sorted(by.items(), key=lambda kv: -kv[1][1])}
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    Path(OUT).write_text(json.dumps({"limit_ms": LIMIT_MS, "offscreen": OFFSCREEN, "synthetic": SYNTH,
                                     "timings": timings, "gc": gc_log,
                                     "gc_objects": len(gc.get_objects()), "summary": summary, "stalls": rows, "errors": errors},
                                    ensure_ascii=False, indent=1), "utf-8")
    print(f"\nпауз дольше {LIMIT_MS:.0f} мс: {len(rows)}; сумма {sum(r['ms'] for r in rows):.0f} мс → {OUT}")
    print(f"сборок мусора дольше 4 мс: {len(gc_log)}, всего {sum(g[1] for g in gc_log):.0f} мс, "
          f"худшая {max([g[1] for g in gc_log] or [0]):.0f} мс")
    for k, v in list(summary.items())[:25]:
        print(f"  {k:28s} {v['stalls']:3d} пауз, худшая {v['worst_ms']:5d} мс, всего {v['total_ms']} мс")
    try:
        if win is not None:
            win._really_quit = True
            win.close()
            pump(0.3)
    except Exception:                                       # noqa: BLE001
        pass
    sys.stdout.flush()
    os._exit(0)
