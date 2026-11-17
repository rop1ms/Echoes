# bgproc.py
"""
Тяжёлая фоновая работа — в отдельном процессе.

Интерфейс ECHOES и вывод звука живут в одном процессе Python, а в нём один GIL: пока фоновый
поток считает на Python (разбор страниц yt-dlp, анализ трека), главный поток получает
процессор урывками по 2 мс — кадры растягиваются до сотен миллисекунд, интерфейс «висит».
Отдельный процесс со своим GIL работает на другом ядре и интерфейсу не мешает; ему ещё и
понижен приоритет, чтобы интерфейс и звук всегда были первыми.

    r = bgproc.call("beat_analysis", "analyze", path, progress=fn, cancel=event)

Функция модуля выполняется в дочернем процессе; аргументы и результат — JSON. Если функция
принимает progress, ребёнок шлёт progress(*args) родителю строками. cancel (threading.Event)
— процесс убивается.

Плюс «передний план» (fg_busy / idle_wait): пока идёт игра, необязательные фоновые потоки
внутри процесса (тексты песен, анализ жанров…) подождут — ни одного лишнего мгновения GIL.
"""
from __future__ import annotations

import data_home
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
_LOG = data_home.root() / "bgproc.log"
_NO_WINDOW = 0x08000000
_BELOW_NORMAL = 0x00004000
_IDLE_CLASS = 0x00000040


def _python() -> str:
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        cand = exe.with_name("python.exe")
        if cand.exists():
            return str(cand)
    return str(exe)


def _log_file():
    try:
        _LOG.parent.mkdir(parents=True, exist_ok=True)
        if _LOG.exists() and _LOG.stat().st_size > 1_000_000:
            _LOG.unlink()
        return open(_LOG, "ab")
    except OSError:
        return subprocess.DEVNULL


class Cancelled(RuntimeError):
    pass


class Job:
    """Один вызов функции в дочернем процессе."""

    def __init__(self, module: str, func: str, args=(), kwargs=None, progress=None, priority="below"):
        self.module, self.func = module, func
        self.args, self.kwargs = list(args), dict(kwargs or {})
        self.progress = progress
        self.priority = priority
        self.proc: subprocess.Popen | None = None
        self.killed = False

    def start(self):
        flags = 0
        if os.name == "nt":
            flags = _NO_WINDOW | (_IDLE_CLASS if self.priority == "idle" else _BELOW_NORMAL)
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["ECHOES_BGPROC"] = "1"
        log = _log_file()
        self.proc = subprocess.Popen([_python(), "-X", "utf8", "-c",
                                      "import sys; sys.path.insert(0, sys.argv[1]); import bgproc; bgproc._child()",
                                      str(APP_DIR)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, cwd=str(APP_DIR),
                                     env=env, creationflags=flags)
        if log is not subprocess.DEVNULL:
            log.close()
        req = {"m": self.module, "f": self.func, "a": self.args, "k": self.kwargs, "p": self.progress is not None}
        try:
            self.proc.stdin.write(json.dumps(req, ensure_ascii=False).encode("utf-8"))
            self.proc.stdin.close()
        except OSError:
            pass
        return self

    def kill(self):
        self.killed = True
        p = self.proc
        if p is not None and p.poll() is None:
            try:
                p.kill()
            except OSError:
                pass

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def wait(self):
        """Читать ответы до результата. Блокирующее чтение трубы отпускает GIL."""
        p = self.proc
        result, err = None, None
        got = False
        for raw in p.stdout:
            try:
                msg = json.loads(raw.decode("utf-8"))
            except ValueError:
                continue
            if "p" in msg:
                if self.progress is not None:
                    try:
                        self.progress(*msg["p"])
                    except Exception:                          # noqa: BLE001
                        pass
            elif "r" in msg:
                result, got = msg["r"], True
            elif "e" in msg:
                err = msg["e"]
        p.wait()
        if self.killed:
            raise Cancelled("отменено")
        if err is not None:
            raise RuntimeError(err)
        if not got:
            raise RuntimeError(f"фоновый процесс завершился без ответа (код {p.returncode})")
        return result


def call(module: str, func: str, *args, progress=None, cancel: threading.Event | None = None, priority="below",
         **kwargs):
    """Выполнить module.func(*args, **kwargs) в отдельном процессе и вернуть результат."""
    job = Job(module, func, args, kwargs, progress, priority).start()
    stop = threading.Event()
    if cancel is not None:
        def watch():
            while not stop.is_set():
                if cancel.wait(0.1):
                    job.kill()
                    return
        threading.Thread(target=watch, daemon=True, name="bgproc-watch").start()
    try:
        return job.wait()
    finally:
        stop.set()


def _child():
    """Точка входа дочернего процесса: запрос — из stdin, ответы — строками JSON в stdout."""
    proto = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr                              # print() модулей не портит протокол
    lock = threading.Lock()

    def send(obj):
        with lock:
            proto.write(json.dumps(obj, ensure_ascii=False) + "\n")
            proto.flush()
    try:
        req = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        import importlib
        mod = importlib.import_module(req["m"])
        fn = getattr(mod, req["f"])
        kw = dict(req.get("k") or {})
        if req.get("p"):
            last = [0.0]

            def prog(*a):
                now = time.perf_counter()
                if now - last[0] >= 0.05 or (a and isinstance(a[0], (int, float)) and a[0] >= 0.999):
                    last[0] = now
                    send({"p": list(a)})
            kw["progress"] = prog
        r = fn(*req.get("a", []), **kw)
        send({"r": r})
    except BaseException as e:                           # noqa: BLE001
        traceback.print_exc()
        send({"e": (str(e) or e.__class__.__name__)[:400]})
    finally:
        try:
            proto.flush()
        except Exception:                                # noqa: BLE001
            pass


def in_child() -> bool:
    return os.environ.get("ECHOES_BGPROC") == "1"


# ------------------------------------------------------------------ #
#  Передний план: пока идёт игра, фоновые потоки в этом процессе ждут  #
# ------------------------------------------------------------------ #

_fg = {}
_fg_lock = threading.Lock()
_fg_free = threading.Event()
_fg_free.set()


def set_fg_busy(name: str, on: bool):
    """Кто-то на переднем плане требует весь процессор (игра, запись…)."""
    with _fg_lock:
        if on:
            _fg[name] = True
        else:
            _fg.pop(name, None)
        if _fg:
            _fg_free.clear()
        else:
            _fg_free.set()


def fg_busy() -> bool:
    return not _fg_free.is_set()


def idle_wait(max_wait: float = 600.0, cancel: threading.Event | None = None):
    """Фоновому потоку: подождать, пока передний план занят (не дольше max_wait секунд).
    В главном потоке ничего не делает."""
    if _fg_free.is_set() or threading.current_thread() is threading.main_thread():
        return
    if cancel is None:
        _fg_free.wait(max_wait)
        return
    deadline = time.monotonic() + max_wait
    while not cancel.is_set():
        remaining = deadline - time.monotonic()
        if remaining <= 0 or _fg_free.wait(min(.1, remaining)):
            return


_tl = threading.local()
_soft: set = set()


def set_soft_busy(name: str, on: bool):
    """Передний план анимирован: фоновые расчёты на Python не останавливаются,
    но берут меньше времени (throttle — короче кусками и реже), чтобы не было рывков кадров."""
    with _fg_lock:
        if on:
            _soft.add(name)
        else:
            _soft.discard(name)


def throttle(duty: float = 0.3, slice_s: float = 0.004):
    """Фоновому потоку с вычислениями на Python: работать не дольше slice_s подряд и не больше
    доли duty времени — остальное время GIL достаётся интерфейсу и звуку (иначе кадры
    растягиваются вдвое-втрое, пока, например, анализ жанров перебирает библиотеку).
    Зовётся в горячих циклах; в главном потоке ничего не делает."""
    if threading.current_thread() is threading.main_thread():
        return
    if _soft:
        duty, slice_s = min(duty, 0.08), min(slice_s, 0.002)
    now = time.perf_counter()
    t0 = getattr(_tl, "t0", None)
    if t0 is None or now - t0 > 1.0:
        _tl.t0 = now
        return
    busy = now - t0
    if busy >= slice_s:
        time.sleep(min(0.05, busy * (1.0 - duty) / duty))
        _tl.t0 = time.perf_counter()
    if not _fg_free.is_set():
        idle_wait()
