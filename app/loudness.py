# loudness.py
"""
Выравнивание громкости треков (как ReplayGain / «Нормализация громкости» в
стримингах). Каждый трек один раз измеряется через ffmpeg (EBU R128: интегральная
громкость в LUFS и пик), результат кэшируется в ~/Echoes/loudness.json.
При воспроизведении движок умножает громкость на коэффициент трека, так что
громкие и тихие записи звучат на одном уровне. Сам файл не изменяется.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from collections import OrderedDict
from pathlib import Path

TARGET_LUFS = -14.0        # куда подтягиваем (стандарт стримингов)
MAX_BOOST_DB = 12.0        # сильнее не усиливаем — вылезает шум
MAX_CUT_DB = 20.0
PEAK_CEIL_DB = -1.0        # после усиления пик не выше −1 dBFS (без клиппинга)

_I = re.compile(r"^\s*I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", re.M)
_PEAK = re.compile(r"Peak:\s*(-?\d+(?:\.\d+)?|-inf)\s*dBFS", re.M)


def _ffmpeg() -> str | None:
    p = shutil.which("ffmpeg")
    if p:
        return p
    local = Path(__file__).resolve().parent.parent / "ffmpeg" / "ffmpeg.exe"
    return str(local) if local.exists() else None


def _collect_stderr(command, flags, cancel):
    deadline = time.monotonic() + 180
    with subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                          creationflags=flags) as process:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or (cancel is not None and cancel.is_set()):
                process.kill()
                process.communicate()
                return None
            try:
                return process.communicate(timeout=min(.2, remaining) if cancel else remaining)[1]
            except subprocess.TimeoutExpired:
                continue


def measure(path: str, cancel: threading.Event | None = None):
    """(LUFS, пик dBFS) трека или None, если не вышло."""
    exe = _ffmpeg()
    if not exe or not Path(path).exists() or (cancel is not None and cancel.is_set()):
        return None
    flags = 0x08000000 if os.name == "nt" else 0
    try:
        stderr = _collect_stderr([exe, "-nostdin", "-hide_banner", "-nostats", "-i", path, "-vn",
                                  "-af", "ebur128=peak=true", "-f", "null", "-"], flags, cancel)
    except Exception as e:                           # noqa: BLE001
        print("[loudness]", e)
        return None
    if stderr is None:
        return None
    out = stderr.decode("utf-8", "replace")
    # итог — последний блок «Summary» (в нём I: и Peak:)
    tail = out[out.rfind("Summary:"):] if "Summary:" in out else out
    mi = _I.findall(tail)
    if not mi:
        return None
    mp = _PEAK.findall(tail)
    peak = -99.0 if not mp or mp[-1] == "-inf" else float(mp[-1])
    return float(mi[-1]), peak


def gain_db(lufs: float, peak: float, target: float = TARGET_LUFS) -> float:
    g = target - lufs
    if g > 0:                                         # усиление ограничено запасом до клиппинга
        g = min(g, PEAK_CEIL_DB - peak, MAX_BOOST_DB)
        g = max(g, 0.0)
    else:
        g = max(g, -MAX_CUT_DB)
    return g


class LoudnessStore:
    def __init__(self, path: Path, on_ready=None):
        self.path = Path(path)
        self.on_ready = on_ready                       # cb(track_path) — вызывается из рабочего потока
        self.data: dict = {}
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:                            # noqa: BLE001
            self.data = {}
        self._lock = threading.RLock()
        self._closed = threading.Event()
        self._todo: OrderedDict[str, None] = OrderedDict()
        self._worker = None
        self._dirty = 0

    def _key(self, path):
        try:
            st = os.stat(path)
            return str(path), int(st.st_mtime), st.st_size
        except OSError:
            return str(path), 0, 0

    def get(self, path):
        """(LUFS, пик) из кэша или None (кэш устарел, если файл менялся)."""
        e = self.data.get(str(path))
        if not e:
            return None
        _, mt, sz = self._key(path)
        if e.get("mt") != mt or e.get("sz") != sz:
            return None
        return e["lufs"], e["peak"]

    def linear_gain(self, path, target: float = TARGET_LUFS) -> float:
        m = self.get(path)
        if m is None:
            return 1.0
        return 10 ** (gain_db(m[0], m[1], target) / 20.0)

    def request(self, path, urgent=False):
        """Поставить трек в очередь на измерение (срочный — в начало)."""
        path = str(path)
        if not path or self._closed.is_set() or self.get(path) is not None:
            return
        with self._lock:
            if self._closed.is_set():
                return
            self._todo[path] = None
            if urgent:
                self._todo.move_to_end(path, last=False)
            if self._worker is None:
                self._worker = threading.Thread(target=self._run, daemon=True, name="echoes-loudness")
                self._worker.start()

    def request_many(self, paths):
        for p in paths:
            self.request(p)

    def _run(self):
        while True:
            with self._lock:
                path = self._todo.popitem(last=False)[0] if self._todo and not self._closed.is_set() else None
            if path is None:
                self.save()
                with self._lock:
                    # A request can arrive while the previous queue is being saved.
                    if self._todo and not self._closed.is_set():
                        continue
                    self._worker = None
                    return
            if self.get(path) is not None:
                continue
            try:
                import bgproc
                bgproc.idle_wait(cancel=self._closed)
            except Exception:                        # noqa: BLE001
                pass
            m = measure(path, self._closed)
            if self._closed.is_set():
                continue
            _, mt, sz = self._key(path)
            self.data[path] = {"lufs": m[0], "peak": m[1], "mt": mt, "sz": sz} if m else \
                {"lufs": TARGET_LUFS, "peak": -99.0, "mt": mt, "sz": sz}      # не измерился — не трогаем
            self._dirty += 1
            if self._dirty >= 10:
                self.save()
            with self._lock:
                if not self._closed.is_set() and self.on_ready:
                    try:
                        self.on_ready(path)
                    except Exception as e:           # noqa: BLE001
                        print("[loudness] cb:", e)
            self._closed.wait(0.05)

    def shutdown(self):
        self._closed.set()
        with self._lock:
            self._todo.clear()
            self.on_ready = None
            worker = self._worker
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=2)

    def save(self):
        if not self._dirty:
            return
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data), encoding="utf-8")
            tmp.replace(self.path)
            self._dirty = 0
        except Exception as e:                       # noqa: BLE001
            print("[loudness] save:", e)

    def pending(self) -> int:
        with self._lock:
            return len(self._todo)
