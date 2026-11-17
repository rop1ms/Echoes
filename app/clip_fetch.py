# clip_fetch.py
"""
Официальные клипы песен для «Режима клипа».

  * поиск — yt-dlp (YouTube): берётся несколько результатов по «исполнитель — название
    official music video» и каждому ставится оценка: «official video / клип / MV» в
    названии, канал исполнителя или VEVO, длительность близка к треку — плюс;
    lyric video, audio, live, cover, karaoke, slowed, nightcore… — минус;
  * скачивание — видео до 720p/1080p (вместе со звуком: он нужен для синхронизации);
  * синхронизация — у клипа часто есть вступление или сценка до музыки. Звук клипа и
    трека раскладываются на «огибающую атак» (где начинаются удары и ноты), и
    взаимная корреляция находит сдвиг: время клипа = время трека + offset;
  * кэш — ~/Echoes/clips: index.json (какой клип у какого трека, сдвиг, «клипа нет» —
    чтобы не искать заново каждый раз) и скачанные клипы, если их сохраняли;
  * по умолчанию клипы ОНЛАЙН (stream_job): видео не скачивается, VLC играет видеодорожку по
    ссылке, для синхронизации звук клипа берётся во временный файл и сразу удаляется.

Всё сетевое и тяжёлое — в фоновых потоках, интерфейс не ждёт.
"""
from __future__ import annotations

import data_home
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import numpy as np

CLIP_DIR = data_home.root() / "clips"
INDEX = CLIP_DIR / "index.json"
VIDEO_EXT = (".mp4", ".webm", ".mkv", ".mov")

_BAD = ("lyric", "lyrics", "текст", "караоке", "karaoke", "audio only", "official audio", "(audio)", "[audio]",
        "visualizer", "visualiser", "cover by", "cover)", "(cover", "reaction", "реакция", "live at", "live from",
        "(live", "[live", "концерт", "slowed", "sped up", "speed up", "nightcore", "8d audio", "instrumental",
        "минус", "tutorial", "урок", "разбор", "fan made", "fanmade", "amv", "edit audio", "1 hour", "10 hours",
        "remix")
_GOOD = ("official music video", "official video", "music video", "official mv", " mv", "(mv)", "[mv]", "клип",
         "official clip", "videoclip", "video oficial", "(video)", "[video]")

_lock = threading.Lock()


def _ffmpeg() -> str | None:
    p = shutil.which("ffmpeg")
    if p:
        return p
    local = Path(__file__).resolve().parent.parent / "ffmpeg" / "ffmpeg.exe"
    return str(local) if local.exists() else None


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)                  # (feat. …), [Remastered] — мешают сравнению
    s = re.sub(r"\b(feat|ft)\.?\b.*", " ", s)
    return re.sub(r"[^\w]+", " ", s, flags=re.U).strip()


def track_key(t: dict) -> str:
    """Ключ трека в кэше клипов: путь файла, а если его нет — «исполнитель|название»."""
    p = str(t.get("path") or "")
    if p:
        return p
    return f"{_norm(t.get('artist', ''))}|{_norm(t.get('title', ''))}"


# ── индекс ── #

_cache = {"sig": None, "d": {}}


def _load() -> dict:
    """Индекс из памяти, пока файл не менялся: lookup() зовут из отрисовки —
    раньше каждый кадр читался и разбирался весь index.json."""
    try:
        st = INDEX.stat()
        sig = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    if sig != _cache["sig"]:
        try:
            _cache["d"] = json.loads(INDEX.read_text("utf-8"))
        except Exception:                                  # noqa: BLE001
            _cache["d"] = {}
        _cache["sig"] = sig
    return dict(_cache["d"])


def _save(d: dict):
    CLIP_DIR.mkdir(parents=True, exist_ok=True)
    tmp = INDEX.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, INDEX)
    # только что записанное и есть индекс: не перечитывать и не разбирать файл заново при следующем lookup()
    # (на каждой смене трека это были ~10 мс в потоке окна)
    try:
        st = INDEX.stat()
        _cache["d"], _cache["sig"] = dict(d), (st.st_mtime_ns, st.st_size)
    except OSError:
        _cache["sig"] = None


def lookup(t: dict) -> dict | None:
    """Запись кэша трека: {"file", "url", "title", "offset", "none"} или None (ещё не искали)."""
    with _lock:
        e = _load().get(track_key(t))
    if not e:
        return None
    if e.get("file"):
        f = CLIP_DIR / e["file"]
        if not f.exists():
            if e.get("url") and not e.get("none"):         # файл удалили — клип остаётся онлайн
                return dict(e, file="", stream=True)
            return None                                    # файл удалили — искать заново
        e = dict(e, path=str(f))
    return e


def update(t: dict, **fields):
    with _lock:
        d = _load()
        e = d.get(track_key(t)) or {}
        e.update(fields)
        e["ts"] = time.time()
        d[track_key(t)] = e
        _save(d)


def forget(t: dict):
    with _lock:
        d = _load()
        e = d.pop(track_key(t), None)
        _save(d)
    if e and e.get("file"):
        try:
            (CLIP_DIR / e["file"]).unlink()
        except OSError:
            pass


# ── поиск ── #

def _score(entry: dict, title: str, artist: str, dur: float) -> float:
    name = (entry.get("title") or "").lower()
    chan = (entry.get("channel") or entry.get("uploader") or "").lower()
    n_name, n_title = _norm(name), _norm(title)
    # исполнитель без пробелов и знаков: «a-ha» → «aha» (иначе от него осталась бы буква «a»)
    first = re.split(r"\s*(?:,|&|feat\.?|ft\.?| x | и )\s*", artist or "", maxsplit=1)[0]
    art = _norm(first).replace(" ", "")
    sq_name, sq_chan = n_name.replace(" ", ""), _norm(chan).replace(" ", "")
    sc = 0.0
    words = [w for w in n_title.split() if len(w) > 1] or n_title.split()
    if words:
        hit = sum(1 for w in words if w in n_name) / len(words)
        sc += 30 * hit - (30 if hit < 0.5 else 0)
    own = bool(art) and len(art) >= 2 and art in sq_chan
    if art and art in sq_name:
        sc += 10
    if own or "vevo" in chan:
        sc += 30                                           # канал самого исполнителя / VEVO — настоящий клип
    elif "official" in chan or "records" in chan or "music" in chan and "of all" not in chan:
        sc += 5
    else:
        sc -= 8                                            # перезалив с чужого канала — только если нет лучше
    if any(g in name for g in _GOOD):
        sc += 30
    if "official" in name:
        sc += 10
    tl = (title or "").lower()
    for b in _BAD:
        if b in name and b not in tl:
            sc -= 45
    d = float(entry.get("duration") or 0)
    if dur > 0 and d > 0:
        if d < dur * 0.7:
            sc -= 40                                       # обрезок/тизер
        elif d > dur * 2.2 + 150:
            sc -= 40                                       # фильм/сборник
        else:
            sc += 10 - min(10.0, abs(d - dur) / 20)
    return sc


def search(title: str, artist: str, dur: float = 0.0, n: int = 8, query: str = "") -> list[dict]:
    """Кандидаты на официальный клип, лучшие первыми: [{"id", "url", "title", "channel", "duration", "score"}].
    query — свой поисковый запрос (ручной поиск): ищется как есть, порядок — как у YouTube."""
    import yt_dlp
    q = query.strip() or (f"{artist} - {title} official music video" if artist else f"{title} official music video")
    opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist", "skip_download": True,
            "noplaylist": True, "socket_timeout": 20}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{n}:{q}", download=False) or {}
    out = []
    for e in info.get("entries") or []:
        if not e or not e.get("id"):
            continue
        out.append({"id": e["id"], "url": e.get("url") or f"https://www.youtube.com/watch?v={e['id']}",
                    "title": e.get("title") or "", "channel": e.get("channel") or e.get("uploader") or "",
                    "duration": float(e.get("duration") or 0), "score": _score(e, title, artist, dur)})
    if not query.strip():
        out.sort(key=lambda x: -x["score"])
    return out


# ── скачивание ── #

def download(cand: dict, quality: int = 720, progress=None, cancel: threading.Event | None = None) -> str:
    """Скачать клип → путь к файлу. progress(доля 0..1, текст)."""
    import yt_dlp
    CLIP_DIR.mkdir(parents=True, exist_ok=True)
    ff = _ffmpeg()
    q = int(quality)
    fmt = (f"bv*[height<={q}][vcodec^=avc1]+ba[ext=m4a]/bv*[height<={q}]+ba/b[height<={q}]/b" if ff
           else f"b[height<={q}][ext=mp4]/b[height<={q}]/b")

    def hook(d):
        if cancel is not None and cancel.is_set():
            raise yt_dlp.utils.DownloadCancelled("cancel")
        if progress is None:
            return
        if d.get("status") == "downloading":
            tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            got = d.get("downloaded_bytes") or 0
            progress(min(0.99, got / tot) if tot else 0.0, "Скачиваю клип…")
        elif d.get("status") == "finished":
            progress(0.99, "Собираю видео…")

    opts = {"format": fmt, "outtmpl": str(CLIP_DIR / f"{cand['id']}.%(ext)s"), "quiet": True, "no_warnings": True,
            "noplaylist": True, "noprogress": True, "progress_hooks": [hook], "retries": 4, "fragment_retries": 4,
            "socket_timeout": 25, "overwrites": False}
    if ff:
        opts["ffmpeg_location"] = str(Path(ff).parent)
        opts["merge_output_format"] = "mp4"
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([cand["url"]])
    for ext in VIDEO_EXT:
        f = CLIP_DIR / f"{cand['id']}{ext}"
        if f.exists():
            return str(f)
    hits = sorted(CLIP_DIR.glob(f"{cand['id']}.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    hits = [h for h in hits if h.suffix.lower() in VIDEO_EXT]
    if not hits:
        raise RuntimeError("видео не скачалось")
    return str(hits[0])


# ── синхронизация по звуку ── #

_RATE = 4000            # Гц: для атак хватает
_HOP = 80               # 50 огибающих в секунду


def _pcm(path: str, seconds: float = 240.0) -> np.ndarray | None:
    ff = _ffmpeg()
    if not ff or not path or not Path(path).exists():
        return None
    flags = 0x08000000 if os.name == "nt" else 0
    try:
        r = subprocess.run([ff, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", path, "-t", str(seconds),
                            "-vn", "-ac", "1", "-ar", str(_RATE), "-f", "s16le", "-"],
                           capture_output=True, timeout=120, creationflags=flags)
    except Exception:                                      # noqa: BLE001
        return None
    if not r.stdout:
        return None
    return np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768.0


def _onsets(x: np.ndarray) -> np.ndarray:
    """Огибающая атак: рост энергии в трёх полосах (низ/середина/верх) кадрами по 20 мс."""
    n = len(x) // _HOP
    if n < 10:
        return np.zeros(1, np.float32)
    fr = x[:n * _HOP].reshape(n, _HOP)
    spec = np.abs(np.fft.rfft(fr * np.hanning(_HOP), axis=1))
    bands = [spec[:, 1:4].sum(1), spec[:, 4:14].sum(1), spec[:, 14:].sum(1)]
    env = np.zeros(n, np.float32)
    for b in bands:
        b = np.log1p(b * 50)
        d = np.maximum(0.0, np.diff(b, prepend=b[:1]))
        env += d / (d.std() + 1e-6)
    env -= env.mean()
    return env / (env.std() + 1e-6)


def align(track_path: str, clip_path: str) -> tuple[float, float]:
    """(offset, уверенность). Время в клипе = время трека + offset. Уверенность < 4 — сдвиг ненадёжен."""
    a = _pcm(track_path, 150.0)
    b = _pcm(clip_path, 300.0)
    if a is None or b is None:
        return 0.0, 0.0
    ea, eb = _onsets(a), _onsets(b)
    if len(ea) < 200 or len(eb) < 200:
        return 0.0, 0.0
    n = 1
    while n < len(ea) + len(eb):
        n *= 2
    corr = np.fft.irfft(np.fft.rfft(eb, n) * np.conj(np.fft.rfft(ea, n)), n)
    fps = _RATE / _HOP
    lo, hi = int(-30 * fps), int(150 * fps)                # клип может начаться раньше трека (−30 с) или позже
    idx = np.arange(lo, hi)
    vals = corr[idx % n]
    k = int(np.argmax(vals))
    peak = vals[k]
    conf = float((peak - np.median(vals)) / (vals.std() + 1e-6))
    return round(float(idx[k] / fps), 2), conf


# ── всё вместе ── #

def fetch_job(track: dict, quality=720, cand: dict | None = None, progress=None) -> dict:
    """Поиск + скачивание + синхронизация одного клипа. Выполняется в отдельном процессе (bgproc):
    yt-dlp разбирает страницы на Python, и в процессе интерфейса это отбирало у него процессор.
    Возвращает поля для записи в index.json (её делает родитель)."""
    t = dict(track)
    prog = progress or (lambda *_: None)
    out = {}
    if cand is None:
        prog(0.0, "Ищу официальный клип…")
        cands = search(t.get("title", ""), t.get("artist", ""), float(t.get("duration") or 0))
        out["cands"] = cands[:6]
        good = [c for c in cands if c["score"] > 5]
        if not good:
            out.update(none=True, file="")
            return out
        cand = good[0]
    prog(0.02, f"Скачиваю: {cand['title'][:60]}")
    path = download(cand, quality, prog, None)
    prog(0.995, "Синхронизирую с треком…")
    off, conf = align(str(t.get("path") or ""), path)
    if conf < 4.0:
        off = 0.0
    out.update(file=Path(path).name, url=cand["url"], title=cand["title"], offset=off, conf=round(conf, 1), none=False)
    return out


class Fetch(threading.Thread):
    """Найти и скачать клип трека в фоне. on_progress(доля, текст), on_done(запись | None, ошибка)
    вызываются из этого потока — UI сам перекидывает их в главный поток. Сама работа идёт в отдельном
    процессе (bgproc), этот поток только ждёт его ответа."""

    def __init__(self, track: dict, quality=720, cand: dict | None = None, on_progress=None, on_done=None):
        super().__init__(daemon=True)
        self.t = dict(track)
        self.quality = quality
        self.cand = cand
        self.on_progress = on_progress or (lambda *_: None)
        self.on_done = on_done or (lambda *_: None)
        self.cancel = threading.Event()

    def run(self):
        t = self.t
        try:
            import bgproc
            bgproc.idle_wait(900)                          # идёт игра — клип подождёт
            if self.cancel.is_set():
                return
            light = {k: t.get(k) for k in ("path", "title", "artist", "duration") if t.get(k) is not None}
            r = bgproc.call("clip_fetch", "fetch_job", light, int(self.quality), self.cand,
                            progress=self.on_progress, cancel=self.cancel)
            if self.cancel.is_set():
                self._clean_parts()
                return
            update(t, **r)
            if r.get("none"):
                self.on_done(None, "Официальный клип не найден")
                return
            self.on_done(lookup(t), "")
        except Exception as e:                             # noqa: BLE001
            if self.cancel.is_set():
                self._clean_parts()
                return
            msg = str(e)
            if "cancel" in msg.lower() or "отменено" in msg.lower():
                return
            self.on_done(None, f"Не получилось: {msg[:140]}")

    @staticmethod
    def _clean_parts():
        """Процесс скачивания убит — недокачанные куски не копятся."""
        try:
            for f in CLIP_DIR.glob("*.part*"):
                if time.time() - f.stat().st_mtime < 3600:
                    f.unlink(missing_ok=True)
        except OSError:
            pass


# ══════════════════════════════════════════════════════════════════════════ #
#  Клипы онлайн — без скачивания видео
# ══════════════════════════════════════════════════════════════════════════ #
#
# Клип в режиме «Клип» идёт без звука, поэтому нужна только видеодорожка: VLC играет её прямо по
# ссылке (перемотка ~0,25 с). Для синхронизации со звуком трека yt-dlp берёт самую лёгкую
# аудиодорожку ролика (1–3 МБ) во временный файл — сдвиг считается, файл сразу удаляется.
# В index.json остаются ссылка на ролик и сдвиг (+ ссылка на поток с её сроком жизни);
# устаревшую ссылку на поток stream_source() достаёт заново.

_SURL: dict = {}                     # страница ролика → (ссылка на видеопоток, истекает)
_SLOCK = threading.Lock()


def _expire(url: str) -> float:
    m = re.search(r"[?&]expire=(\d+)", url or "") or re.search(r"/expire/(\d+)", url or "")
    return float(m.group(1)) if m else time.time() + 3600


def video_stream_url(page: str, quality: int = 720) -> tuple[str, float]:
    """(прямая ссылка на видеодорожку до quality, когда истекает). Сеть, 1–2 с."""
    import yt_dlp
    q = int(quality)
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True, "socket_timeout": 20,
            "format": f"bv*[height<={q}][vcodec^=avc1]/bv*[height<={q}][ext=mp4]/bv*[height<={q}]/b[height<={q}]/b"}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(page, download=False) or {}
    url = info.get("url") or ""
    if not url and info.get("requested_formats"):
        url = info["requested_formats"][0].get("url") or ""
    if not url:
        raise RuntimeError("нет ссылки на видео")
    exp = _expire(url)
    with _SLOCK:
        _SURL[page] = (url, exp)
    return url, exp


def _audio_tmp(page: str) -> str:
    """Самая лёгкая аудиодорожка ролика во временный файл (для синхронизации). Удалить — вызывающему."""
    import tempfile
    import yt_dlp
    d = tempfile.mkdtemp(prefix="echoes_clip_")
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "noprogress": True, "socket_timeout": 20,
            "format": "wa[ext=m4a]/wa[acodec=opus]/wa/ba", "outtmpl": os.path.join(d, "a.%(ext)s"), "retries": 3}
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([page])
    files = [os.path.join(d, f) for f in os.listdir(d) if not f.endswith(".part")]
    if not files:
        shutil.rmtree(d, ignore_errors=True)
        raise RuntimeError("звук клипа не получен")
    return files[0]


def _rm_tmp(path: str | None):
    if path:
        shutil.rmtree(os.path.dirname(path), ignore_errors=True)


def stream_job(track: dict, quality=720, cand: dict | None = None, progress=None) -> dict:
    """Поиск + ссылка на поток + синхронизация по звуку — без скачивания видео (процесс bgproc).
    track: path (файл трека) или src_page (страница онлайн-трека, если он сам играет потоком)."""
    t = dict(track)
    prog = progress or (lambda *_: None)
    out = {}
    if cand is None:
        prog(0.0, "Ищу официальный клип…")
        cands = search(t.get("title", ""), t.get("artist", ""), float(t.get("duration") or 0))
        out["cands"] = cands[:6]
        good = [c for c in cands if c["score"] > 5]
        if not good:
            out.update(none=True, file="", stream=False)
            return out
        cand = good[0]
    prog(0.3, f"Клип: {cand['title'][:60]}")
    vurl, exp = video_stream_url(cand["url"], quality)
    prog(0.55, "Синхронизирую с треком…")
    off, conf = 0.0, 0.0
    clip_a = track_a = None
    try:
        clip_a = _audio_tmp(cand["url"])
        src = str(t.get("path") or "")
        if src.startswith("stream:") or not os.path.exists(src):
            page = t.get("src_page") or ""
            if page:
                track_a = _audio_tmp(page)
                src = track_a
        off, conf = align(src, clip_a)
    except Exception as e:                                 # noqa: BLE001
        print("[clip stream] sync:", e)
    finally:
        _rm_tmp(clip_a)
        _rm_tmp(track_a)
    if conf < 4.0:
        off = 0.0
    out.update(file="", url=cand["url"], title=cand["title"], offset=off, conf=round(conf, 1), none=False,
               stream=True, vurl=vurl, vexp=exp, quality=int(quality))
    return out


def stream_source(entry: dict | None) -> str | None:
    """Что открыть в VLC: скачанный файл или живая ссылка на поток (None — ссылку надо обновить)."""
    if not entry:
        return None
    if entry.get("path"):
        return entry["path"]
    if not entry.get("stream") or not entry.get("url"):
        return None
    with _SLOCK:
        s = _SURL.get(entry["url"])
    if s and s[1] - 120 > time.time():
        return s[0]
    if entry.get("vurl") and float(entry.get("vexp") or 0) - 120 > time.time():
        with _SLOCK:
            _SURL[entry["url"]] = (entry["vurl"], float(entry["vexp"]))
        return entry["vurl"]
    return None


def refresh_stream_async(track: dict, entry: dict, quality: int, cb):
    """Ссылка на поток устарела — достать новую в фоне; cb(url | None) из фонового потока."""
    page = (entry or {}).get("url")
    if not page:
        cb(None)
        return

    def work():
        try:
            url, exp = video_stream_url(page, quality)
            update(track, vurl=url, vexp=exp)
            cb(url)
        except Exception as e:                             # noqa: BLE001
            print("[clip stream] refresh:", e)
            cb(None)
    threading.Thread(target=work, daemon=True).start()


def realign_stream(track: dict, entry: dict) -> tuple[float, float]:
    """Подобрать сдвиг заново для онлайн-клипа (звук — временно, сразу удаляется)."""
    clip_a = track_a = None
    try:
        clip_a = _audio_tmp(entry["url"])
        src = str(track.get("path") or "")
        if src.startswith("stream:") or not os.path.exists(src):
            if track.get("src_page"):
                track_a = _audio_tmp(track["src_page"])
                src = track_a
        return align(src, clip_a)
    finally:
        _rm_tmp(clip_a)
        _rm_tmp(track_a)


class StreamFetch(Fetch):
    """Как Fetch, но клип не скачивается: поиск, ссылка на поток и синхронизация (в процессе bgproc)."""

    def run(self):
        t = self.t
        try:
            import bgproc
            bgproc.idle_wait(900)
            if self.cancel.is_set():
                return
            light = {k: t.get(k) for k in ("path", "title", "artist", "duration", "src_page") if t.get(k) is not None}
            r = bgproc.call("clip_fetch", "stream_job", light, int(self.quality), self.cand,
                            progress=self.on_progress, cancel=self.cancel)
            if self.cancel.is_set():
                return
            if r.get("vurl"):
                with _SLOCK:
                    _SURL[r["url"]] = (r["vurl"], float(r.get("vexp") or 0))
            update(t, **r)
            if r.get("none"):
                self.on_done(None, "Официальный клип не найден")
                return
            self.on_done(lookup(t), "")
        except Exception as e:                             # noqa: BLE001
            if self.cancel.is_set():
                return
            msg = str(e)
            if "cancel" in msg.lower() or "отменено" in msg.lower():
                return
            self.on_done(None, f"Не получилось: {msg[:140]}")
