# library_guard.py
"""
Защита коллекции от «тихой» потери треков и возврат пропавших.

Как треки могли пропасть: два ECHOES одновременно (двойной запуск, автозапуск + ярлык, перезапуск после
обновления) — у каждого своя коллекция в памяти, и тот, где треков меньше, сохранял последним и затирал файл.
Защита:
  * save(): если файл коллекции на диске с прошлой записи изменил кто-то другой — объединяем, а не затираем
    (треки, удалённые вами явно, не возвращаются);
  * резкое уменьшение коллекции без явного удаления — снимок library.shrink-<время>.json (и строка в журнале);
  * раз в день — копия коллекции и плейлистов в backups/ (хранятся 10 последних).
Возврат: find_lost() собирает пути треков из всего, что ECHOES о них помнит (плейлисты, история, статистика,
кэш текстов, анализ треков, снимки и копии, папка загрузок) — те, чьи файлы есть на диске, а в коллекции нет.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

AUDIO_EXTS = {".mp3", ".ogg", ".wav", ".flac", ".m4a", ".opus"}
KEEP_DAILY = 10


def _stat(path: Path):
    try:
        st = path.stat()
        return st.st_mtime_ns, st.st_size
    except OSError:
        return None


def _log(data_dir: Path, msg: str):
    try:
        with open(data_dir / "library_changes.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


class Guard:
    def __init__(self, data_dir: Path, lib_file: Path, load, save):
        self.dir, self.file, self._load, self._save = Path(data_dir), Path(lib_file), load, save
        self.sig = _stat(self.file)
        self.saved_n = None
        self._wid = None                                  # номер нашей последней записи (atomic_json)
        self.removed: set = set()                         # пути, удалённые вами явно (не возвращать)

    def loaded(self, library):
        self.sig = _stat(self.file)
        self.saved_n = len(library)

    def forget(self, paths):
        """Треки удалены осознанно (удаление, замена файла, очистка) — объединение их не вернёт."""
        self.removed.update(str(p) for p in paths if p)

    def save(self, library: list) -> int:
        """Записать коллекцию. Возвращает, сколько треков пришлось вернуть из чужой записи."""
        added = 0
        now_sig = _stat(self.file)
        if now_sig is not None and now_sig != self.sig:
            # запись идёт в фоне (atomic_json): подпись, снятая сразу после save(), была ещё от старого файла,
            # и следующая запись принимала СВОЙ же файл за чужой — вся коллекция читалась с диска в потоке
            # интерфейса на каждой смене трека (десятки мс)
            # Своя — только запись с НАШИМ номером: второй ECHOES (и второй Guard) получает другой.
            try:
                import atomic_json
                done = atomic_json.written(self.file)
                if done is not None and self._wid is not None and done == (now_sig, self._wid):
                    self.sig = now_sig
            except Exception:                                 # noqa: BLE001
                pass
        if self.sig is not None and now_sig is not None and now_sig != self.sig:
            other = self._load(self.file)
            have = {str(t.get("path", "")) for t in library}
            extra = [t for t in other if isinstance(t, dict) and str(t.get("path", "")) not in have
                     and str(t.get("path", "")) not in self.removed]
            if extra:
                library.extend(extra)
                added = len(extra)
                _log(self.dir, f"файл коллекции изменили со стороны (второй ECHOES?) — объединено, "
                               f"возвращено треков: {added}")
        n = len(library)
        if self.saved_n is not None and n < self.saved_n - 20 and n < self.saved_n * 0.9:
            explained = len(self.removed)
            if self.saved_n - n > explained:
                try:
                    snap = self.dir / f"library.shrink-{time.strftime('%Y%m%d-%H%M%S')}.json"
                    if self.file.exists():
                        snap.write_bytes(self.file.read_bytes())
                    _log(self.dir, f"коллекция уменьшилась {self.saved_n} → {n} без явного удаления; снимок {snap.name}")
                except OSError:
                    pass
        self._save(self.file, library)
        try:
            import atomic_json
            self._wid = atomic_json.last_write_id(self.file)  # номер нашей записи (она может быть ещё в очереди)
        except Exception:                                     # noqa: BLE001
            self._wid = None
        self.sig = _stat(self.file)
        self.saved_n = n
        self._daily()
        return added

    def _daily(self):
        try:
            d = self.dir / "backups"
            day = time.strftime("%Y%m%d")
            dst = d / f"library-{day}.json"
            if dst.exists():
                return
            d.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(self.file.read_bytes())
            pl = self.dir / "playlists.json"
            if pl.exists():
                (d / f"playlists-{day}.json").write_bytes(pl.read_bytes())
            for pat in ("library-*.json", "playlists-*.json"):
                old = sorted(d.glob(pat))[:-KEEP_DAILY]
                for f in old:
                    f.unlink(missing_ok=True)
        except OSError:
            pass


# ── возврат пропавших треков ── #

def _paths_in(obj, out: set, depth=0):
    if depth > 6:
        return
    if isinstance(obj, dict):
        p = obj.get("path")
        if isinstance(p, str):
            out.add(p)
        for k, v in obj.items():
            if isinstance(k, str) and len(k) > 4 and k[1:3] == ":\\" and Path(k).suffix.lower() in AUDIO_EXTS:
                out.add(k)                                    # словари «путь → данные» (кэш текстов, анализ)
            if isinstance(v, (dict, list)):
                _paths_in(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            if isinstance(v, (dict, list)):
                _paths_in(v, out, depth + 1)
            elif isinstance(v, str) and Path(v).suffix.lower() in AUDIO_EXTS:
                out.add(v)


def _json(path: Path):
    try:
        return json.loads(path.read_text("utf-8-sig"))
    except (OSError, ValueError, UnicodeError):
        return None


def find_lost(data_dir: Path, library: list, download_dir: str = "") -> list:
    """Пути треков, которые ECHOES помнит, файлы на месте, а в коллекции их нет."""
    data_dir = Path(data_dir)
    known: set = set()
    names = ["playlists.json", "playlists.before-auto-cleanup.json", "stats.json", "lyrics_cache.json",
             "track_intel.json", "loudness.json", "settings.json", "library.json.bak", "music_tierlist.json"]
    files = [data_dir / n for n in names]
    files += sorted(data_dir.glob("library.shrink-*.json")) + sorted((data_dir / "backups").glob("*.json"))
    files += sorted((data_dir / "state").glob("*.json"))    # тяжёлые разделы настроек (settings_store)
    for f in files:
        obj = _json(f)
        if obj is not None:
            _paths_in(obj, known)
    for d in [download_dir, str(data_dir / "downloads")]:
        if d and os.path.isdir(d):
            for root, _dirs, fs in os.walk(d):
                for n in fs:
                    if Path(n).suffix.lower() in AUDIO_EXTS:
                        known.add(os.path.join(root, n))
    have = {os.path.normcase(str(t.get("path", ""))) for t in library}
    out = []
    seen = set()
    for p in known:
        if p.startswith("stream:"):
            continue
        try:
            rp = str(Path(p).resolve())
        except (OSError, ValueError):
            continue
        key = os.path.normcase(rp)
        if key in have or key in seen:
            continue
        if Path(rp).suffix.lower() in AUDIO_EXTS and os.path.isfile(rp):
            seen.add(key)
            out.append(rp)
    return sorted(out)
