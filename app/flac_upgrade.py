# flac_upgrade.py
"""
«MP3 → FLAC»: заменить MP3 выбранных треков на настоящие FLAC-версии тех же песен.

Как это работает:
  * вы отмечаете треки (в Настройках → Медиатека или правым кликом по выделенным трекам → «Заменить на FLAC…»);
  * ECHOES ищет FLAC тех же песен в ваших папках (купленные альбомы с Bandcamp / Qobuz / 7digital, рипы своих
    CD, загрузки) и среди FLAC, что уже есть в коллекции: по исполнителю и названию из тегов или имени файла,
    с проверкой длительности;
  * каждый найденный FLAC проверяется на «подделку»: FLAC, пересжатый из MP3, звучит ровно как MP3, а весит
    втрое больше. У таких файлов спектр обрывается на 16–19 кГц (там, где его срезал кодер MP3) — это видно
    по нескольким кусочкам трека (ffmpeg + numpy, в фоне);
  * «Заменить» ставит FLAC на место MP3 в коллекции, во всех плейлистах и в очереди, переносит историю
    прослушиваний (main.replace_track_file); старый MP3 уходит в Корзину — его можно вернуть.

Чего здесь нет и не будет: «конвертации» MP3 во FLAC. Потерянное при сжатии не вернуть — файл станет больше,
звук не изменится. Для песен без FLAC есть кнопка «Купить в lossless» (поиск на Bandcamp и Qobuz).
"""
from __future__ import annotations

import difflib
import os
import re
import subprocess
import threading
from pathlib import Path

LOSSLESS_EXTS = {".flac"}
MAX_FILES = 40000                    # на случай, если в папки попал целый диск
DUR_TOLERANCE = 4.0                  # с — расхождение длительности у одной и той же записи

_JUNK = re.compile(r"[\(\[\{][^\)\]\}]*(official|audio|video|lyric|visuali[sz]er|clip|hq|hd|320|kbps|explicit|"
                   r"clean|remaster|music video|mv|премьера|клип)[^\)\]\}]*[\)\]\}]", re.I)
_FEAT = re.compile(r"\s(feat\.?|ft\.?|featuring|при уч\.?)\s.*$", re.I)
_NON = re.compile(r"[^0-9a-zа-я]+")


def norm(s: str) -> str:
    """Название / исполнитель для сравнения: без «(Official Audio)», «feat. …», регистра и знаков."""
    s = str(s or "").lower().replace("ё", "е")
    s = _JUNK.sub(" ", s)
    s = _FEAT.sub("", s)
    s = s.replace("&", " and ")
    return " ".join(_NON.sub(" ", s).split())


def _main_artist(a: str) -> str:
    a = norm(a)
    for sep in (" and ", " x ", " vs ", " with "):
        if sep in f" {a} ":
            a = a.split(sep.strip())[0]
    return a.strip()


def _from_filename(path: str) -> tuple[str, str]:
    """«Исполнитель - Название.flac» / «01. Название.flac» → (исполнитель, название)."""
    stem = re.sub(r"\s*\[[^\]]*\]\s*$", "", Path(path).stem)
    stem = re.sub(r"^\s*\d{1,3}\s*[-._)]\s*", "", stem)
    for sep in (" - ", " – ", " — "):
        if sep in stem:
            a, t = stem.split(sep, 1)
            return a.strip(), t.strip()
    return "", stem.strip()


def read_meta(path: str) -> dict | None:
    """Теги и формат lossless-файла: {path, artist, title, duration, rate, bits}."""
    artist = title = ""
    dur = 0.0
    rate = bits = 0
    try:
        from mutagen import File as MutaFile
        m = MutaFile(path, easy=True)
        if m is not None:
            tags = m.tags or {}
            artist = str((tags.get("artist") or tags.get("albumartist") or [""])[0])
            title = str((tags.get("title") or [""])[0])
            info = getattr(m, "info", None)
            dur = float(getattr(info, "length", 0) or 0)
            rate = int(getattr(info, "sample_rate", 0) or 0)
            bits = int(getattr(info, "bits_per_sample", 0) or 0)
    except Exception:                                          # noqa: BLE001 — битый файл: имя файла
        pass
    fa, ft = _from_filename(path)
    return {"path": str(path), "artist": artist or fa, "title": title or ft, "duration": dur,
            "rate": rate, "bits": bits}


def scan_lossless(folders, extra_paths=(), cancel: threading.Event | None = None, progress=None) -> list[dict]:
    """Все FLAC в папках (и extra_paths — FLAC из коллекции) с тегами. progress(n) — сколько найдено."""
    seen, out = set(), []

    def add(p: str):
        key = os.path.normcase(os.path.abspath(p))
        if key in seen:
            return
        seen.add(key)
        meta = read_meta(p)
        if meta:
            out.append(meta)
            if progress and len(out) % 25 == 0:
                progress(len(out))
    for p in extra_paths:
        if cancel is not None and cancel.is_set():
            return out
        if Path(p).suffix.lower() in LOSSLESS_EXTS and Path(p).exists():
            add(str(p))
    files = 0
    for folder in folders:
        if not folder or not Path(folder).is_dir():
            continue
        for root, dirs, names in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in ("$recycle.bin", "node_modules")]
            for name in names:
                if cancel is not None and cancel.is_set():
                    return out
                if os.path.splitext(name)[1].lower() in LOSSLESS_EXTS:
                    add(os.path.join(root, name))
                    files += 1
                    if files >= MAX_FILES:
                        return out
    return out


def _sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def match(track: dict, candidates: list[dict]) -> tuple[dict | None, float]:
    """Лучший FLAC для трека: (кандидат, уверенность 0..1) или (None, 0)."""
    ta, tt = _main_artist(track.get("artist", "")), norm(track.get("title", ""))
    if not tt:
        fa, ft = _from_filename(track.get("path", ""))
        ta, tt = ta or _main_artist(fa), norm(ft)
    if not tt:
        return None, 0.0
    td = float(track.get("duration") or 0)
    best, best_score = None, 0.0
    for c in candidates:
        ct = norm(c.get("title", ""))
        st = _sim(tt, ct)
        if st < .84:
            continue
        ca = _main_artist(c.get("artist", ""))
        if ta and ca:
            sa = max(_sim(ta, ca), 1.0 if (ta in ca or ca in ta) else 0.0)
            if sa < .7:
                continue
        else:
            sa = .75                                           # исполнителя нет у одного из двух — осторожнее
        cd = float(c.get("duration") or 0)
        if td > 0 and cd > 0:
            diff = abs(td - cd)
            if diff > DUR_TOLERANCE:
                continue
            sd = 1.0 - diff / (DUR_TOLERANCE * 2)
        else:
            sd = .8
        score = st * .5 + sa * .3 + sd * .2
        if score > best_score:
            best, best_score = c, score
    return (best, round(best_score, 3)) if best_score >= .8 else (None, 0.0)


# ── проверка на «пересжатый из MP3» ── #

def _ffmpeg() -> str | None:
    try:
        import daw_dsp
        return daw_dsp.ffmpeg_exe()
    except Exception:                                          # noqa: BLE001
        import shutil
        return shutil.which("ffmpeg")


def _excerpt(ff: str, path: str, start: float, dur: float, sr: int):
    import numpy as np
    cmd = [ff, "-v", "error", "-nostdin", "-ss", f"{start:.2f}", "-i", str(path), "-t", f"{dur:.2f}",
           "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    flags = 0x08000000 if os.name == "nt" else 0               # без окна консоли
    r = subprocess.run(cmd, capture_output=True, creationflags=flags, timeout=60)
    return np.frombuffer(r.stdout, np.float32)


def spectrum_cutoff(path: str, duration: float = 0.0) -> float | None:
    """Частота (Гц), выше которой в записи почти ничего нет, по трём кусочкам по 6 с. None — не прочитать."""
    import numpy as np
    ff = _ffmpeg()
    if not ff:
        return None
    sr, n = 44100, 4096
    dur = duration if duration > 30 else 180.0
    spec = np.zeros(n // 2 + 1)
    frames = 0
    win = np.hanning(n).astype(np.float32)
    for at in (.22, .5, .74):
        try:
            x = _excerpt(ff, path, max(0.0, dur * at - 3), 6.0, sr)
        except Exception:                                      # noqa: BLE001
            continue
        if x.size < n * 4:
            continue
        k = (x.size - n) // (n // 2)
        idx = np.arange(n)[None, :] + (np.arange(k) * (n // 2))[:, None]
        fr = x[idx] * win
        loud = np.sqrt((fr ** 2).mean(axis=1)) > 1e-3          # тишину не считаем
        if not loud.any():
            continue
        spec += (np.abs(np.fft.rfft(fr[loud], axis=1)) ** 2).sum(axis=0)
        frames += int(loud.sum())
    if not frames:
        return None
    db = 10 * np.log10(spec / frames + 1e-20)
    hz = np.fft.rfftfreq(n, 1 / sr)
    band = max(1, int(200 / (sr / n)))                         # сглаживание по 200 Гц
    sm = np.convolve(db, np.ones(band) / band, mode="same")
    # Кодер MP3 срезает верх «стеной»: на ~1 кГц спектр падает на 20+ дБ и дальше не поднимается.
    # У настоящей записи верх затухает плавно — там обрыва нет (тихий верх — не повод для подозрений).
    step = sr / n
    w = max(2, int(500 / step))
    top = min(len(sm) - 1, int(21800 / step))
    ref = float(np.median(sm[(hz > 1000) & (hz < 4000)]))
    for i in range(int(21000 / step), int(11000 / step), -1):
        before = sm[i - w]
        after = sm[i + w:top]
        if after.size and before > ref - 75 and before - float(after.mean()) > 20 and \
                float(after.max()) < before - 12:
            return float(hz[i])
    return sr / 2


def verdict(meta: dict, cutoff: float | None) -> tuple[str, str]:
    """('real' | 'suspect' | 'fake' | 'unknown', подпись)."""
    fmt = "FLAC"
    if meta.get("bits") and meta.get("rate"):
        fmt += f" {meta['bits']}/{meta['rate'] / 1000:g}"
    if cutoff is None:
        return "unknown", f"{fmt} · проверить качество не удалось"
    khz = cutoff / 1000
    if cutoff < 19000:
        return "fake", f"{fmt} · подделка: звук обрезан на {khz:.1f} кГц — пересжат из MP3"
    if cutoff < 21000:                                         # LAME 192–320k режет на 19,5–20,8 кГц
        return "suspect", f"{fmt} · сомнительно: срез на {khz:.1f} кГц (может быть из MP3 192–320)"
    return "real", f"{fmt} · настоящий lossless (до {khz:.1f} кГц)"


def default_folders(win) -> list[str]:
    s = win.settings
    dirs = [d for d in (s.get("flac_dirs") or []) if isinstance(d, str)]
    if dirs:
        return dirs
    out = []
    for d in (Path.home() / "Music", Path.home() / "Музыка", Path(str(s.get("download_dir") or ""))):
        if str(d) not in ("", ".") and d.is_dir() and str(d) not in out:
            out.append(str(d))
    return out


def mp3_tracks(win) -> list[dict]:
    return [t for t in win.library if str(t.get("path", "")).lower().endswith(".mp3") and Path(t["path"]).exists()]


def store_links(t: dict) -> list[tuple[str, str]]:
    from urllib.parse import quote_plus
    q = quote_plus(f"{t.get('artist') or ''} {t.get('title') or Path(t.get('path', '')).stem}".strip())
    return [("Bandcamp", f"https://bandcamp.com/search?q={q}&item_type=t"),
            ("Qobuz", f"https://www.qobuz.com/search?q={q}")]


def replace(win, track: dict, flac: str, trash_old: bool = True) -> str:
    """FLAC — на место MP3 везде. Пустые у FLAC обложку и жанр берёт у прежнего трека. → "" или проблема."""
    old = dict(track)
    problem = win.replace_track_file(old.get("path", ""), flac, delete_old=trash_old)
    new = str(Path(flac).resolve())
    nt = next((x for x in win.library if x.get("path") == new), None)
    if nt is not None:
        changed = False
        for k in ("cover", "genre", "album", "artist"):
            if not nt.get(k) and old.get(k):
                nt[k] = old[k]
                changed = True
        if changed:
            try:
                win._save_library()
            except Exception as e:                             # noqa: BLE001
                print("[flac] save:", e)
    return problem


# ══════════════════════════════════════════════════════════════════════════ #
#  Интерфейс (в стиле Phantom): карточка Настроек и окно из меню трека
# ══════════════════════════════════════════════════════════════════════════ #

from PyQt6.QtCore import Qt, QUrl                               # noqa: E402
from PyQt6.QtGui import QDesktopServices                       # noqa: E402
from PyQt6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget,  # noqa: E402
                             QListWidgetItem, QMenu, QProgressBar, QPushButton, QVBoxLayout, QWidget)

_ROLE = Qt.ItemDataRole.UserRole


def _ph():
    try:
        import ph_style
        import ph_widgets
        return ph_style, ph_widgets
    except Exception:                                          # noqa: BLE001
        return None, None


def _btn(text: str, kind: str = "secondary") -> QPushButton:
    ph, pw = _ph()
    if pw is not None:
        return pw.text_button(text, kind)
    b = QPushButton(text)
    b.setObjectName("InlineAct")
    return b


def _lab(text: str, role: str = "PhSub") -> QLabel:
    ph, pw = _ph()
    lb = pw.label(text, role) if pw is not None else QLabel(text)
    lb.setWordWrap(True)
    return lb


class FlacUpgrade(QWidget):
    """Список MP3 с галочками → поиск FLAC → проверка → «Заменить». tracks — отмеченные заранее."""

    def __init__(self, win, tracks=None, parent=None):
        super().__init__(parent)
        self.win = win
        self._cancel = threading.Event()
        self._busy = False
        self.found: dict[str, tuple[dict, str, str]] = {}      # путь mp3 → (FLAC, вид, подпись)
        pre = {str(t.get("path", "")) for t in (tracks or [])}
        self.tracks = mp3_tracks(win)
        if pre:                                                 # отмеченные — сверху
            self.tracks.sort(key=lambda t: str(t.get("path", "")) not in pre)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        v.addWidget(_lab("Отметьте треки — ECHOES найдёт их FLAC в ваших папках (купленные альбомы, рипы CD, "
                         "загрузки) и среди FLAC в коллекции, проверит, что это настоящий lossless, а не пересжатый "
                         "MP3, и поставит FLAC на место MP3 во всех плейлистах. Из MP3 FLAC не сделать: потерянное "
                         "при сжатии не вернуть — поэтому здесь замена, а не конвертация."))
        fr = QHBoxLayout()
        self.dirs_lab = _lab("", "PhMuted")
        fr.addWidget(self.dirs_lab, 1)
        add = _btn("Папка с FLAC…", "small")
        add.clicked.connect(self._add_dir)
        fr.addWidget(add)
        clr = _btn("Сбросить", "small")
        clr.clicked.connect(self._reset_dirs)
        fr.addWidget(clr)
        v.addLayout(fr)
        sel = QHBoxLayout()
        self.count = _lab("", "PhMuted")
        sel.addWidget(self.count, 1)
        for text, on in (("Отметить все", True), ("Снять", False)):
            b = _btn(text, "small")
            b.clicked.connect(lambda _=False, o=on: self._check_all(o))
            sel.addWidget(b)
        v.addLayout(sel)
        self.list = QListWidget()
        self.list.setObjectName("PhList")
        self.list.setMinimumHeight(260)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.itemChanged.connect(lambda _it: self._sync_buttons())
        v.addWidget(self.list, 1)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 0)
        self.bar.hide()
        v.addWidget(self.bar)
        self.status = _lab("", "PhMuted")
        v.addWidget(self.status)
        row = QHBoxLayout()
        self.go = _btn("Найти FLAC", "primary")
        self.go.clicked.connect(self.search)
        row.addWidget(self.go)
        self.apply_btn = _btn("Заменить", "secondary")
        self.apply_btn.clicked.connect(self.apply)
        row.addWidget(self.apply_btn)
        self.buy = _btn("Купить в lossless…", "ghost")
        self.buy.clicked.connect(self._buy_current)
        row.addWidget(self.buy)
        row.addStretch(1)
        self.trash = QCheckBox("Старые MP3 — в Корзину")
        self.trash.setChecked(bool(win.settings.get("flac_trash_old", True)))
        self.trash.toggled.connect(self._trash_toggled)
        row.addWidget(self.trash)
        v.addLayout(row)
        self._fill(pre)
        self._show_dirs()
        self.destroyed.connect(lambda *_: self._cancel.set())

    # ── список ── #
    def _fill(self, pre=()):
        self.list.blockSignals(True)
        self.list.clear()
        for t in self.tracks:
            p = str(t.get("path", ""))
            it = QListWidgetItem()
            it.setData(_ROLE, p)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if p in pre else Qt.CheckState.Unchecked)
            self._label(it, t)
            self.list.addItem(it)
        self.list.blockSignals(False)
        if not self.tracks:
            self.status.setText("В коллекции нет MP3 — менять нечего.")
        self._sync_buttons()

    def _label(self, it, t):
        p = str(t.get("path", ""))
        name = f"{t.get('artist') or ''} — {t.get('title') or Path(p).stem}".strip(" —")
        f = self.found.get(p)
        if f is None:
            line = "MP3" if p not in self.__dict__.get("_missing", set()) else "FLAC не найден"
        else:
            line = f[2]
        mark = {"real": "✓ ", "suspect": "≈ ", "fake": "✕ ", "unknown": "? "}.get(f[1], "") if f else ""
        it.setText(f"{name}\n{mark}{line}")
        it.setToolTip(p if f is None else f"{p}\n→ {f[0]['path']}")

    def _track(self, p):
        return next((t for t in self.tracks if str(t.get("path", "")) == p), None)

    def _checked(self) -> list[dict]:
        out = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                t = self._track(it.data(_ROLE))
                if t is not None:
                    out.append(t)
        return out

    def _check_all(self, on):
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
        self.list.blockSignals(False)
        self._sync_buttons()

    def _ready(self) -> list[tuple[dict, dict]]:
        """Отмеченные треки с найденным FLAC, который не подделка."""
        out = []
        for t in self._checked():
            f = self.found.get(str(t.get("path", "")))
            if f is not None and f[1] != "fake":
                out.append((t, f[0]))
        return out

    def _sync_buttons(self):
        n = len(self._checked())
        self.count.setText(f"MP3 в коллекции: {len(self.tracks)} · отмечено: {n}")
        ready = len(self._ready())
        self.go.setEnabled(n > 0 and not self._busy)
        self.apply_btn.setEnabled(ready > 0 and not self._busy)
        self.apply_btn.setText(f"Заменить ({ready})" if ready else "Заменить")

    # ── папки ── #
    def _show_dirs(self):
        d = default_folders(self.win)
        self.dirs_lab.setText("Где искать: " + (" · ".join(Path(x).name or x for x in d) if d else
                                                 "только FLAC в коллекции — добавьте папку с вашими FLAC"))
        self.dirs_lab.setToolTip("\n".join(d))

    def _add_dir(self):
        f = QFileDialog.getExistingDirectory(self, "Папка с FLAC")
        if not f:
            return
        dirs = list(self.win.settings.get("flac_dirs") or default_folders(self.win))
        if f not in dirs:
            dirs.append(f)
        self.win.settings["flac_dirs"] = dirs
        self._save()
        self._show_dirs()

    def _reset_dirs(self):
        self.win.settings.pop("flac_dirs", None)
        self._save()
        self._show_dirs()

    def _trash_toggled(self, on):
        self.win.settings["flac_trash_old"] = bool(on)
        self._save()

    def _save(self):
        try:
            self.win._schedule_settings_save()
        except Exception:                                      # noqa: BLE001
            pass

    # ── поиск ── #
    def search(self):
        todo = self._checked()
        if not todo or self._busy:
            return
        self._busy = True
        self._sync_buttons()
        self.bar.show()
        self.status.setText("Собираю FLAC из папок…")
        folders = default_folders(self.win)
        in_lib = [str(t.get("path", "")) for t in self.win.library]
        cancel = self._cancel
        bridge = self.win._ui_bridge.call

        def say(text):
            bridge.emit(lambda: self._say(text))

        def work():
            found, missing = {}, set()
            try:
                cands = scan_lossless(folders, in_lib, cancel, lambda n: say(f"Собираю FLAC из папок… {n}"))
                for i, t in enumerate(todo):
                    if cancel.is_set():
                        return
                    say(f"Сверяю и проверяю качество: {i + 1} из {len(todo)} (FLAC в папках: {len(cands)})")
                    c, _score = match(t, cands)
                    if c is None:
                        missing.add(str(t.get("path", "")))
                        continue
                    kind, line = verdict(c, spectrum_cutoff(c["path"], c.get("duration") or 0))
                    found[str(t.get("path", ""))] = (c, kind, line)
            except Exception as e:                             # noqa: BLE001
                print("[flac] search:", e)
                say(f"Поиск прервался: {e}")
            if not cancel.is_set():
                bridge.emit(lambda: self._searched(found, missing))
        threading.Thread(target=work, daemon=True, name="flac-upgrade").start()

    def _say(self, text):
        try:
            self.status.setText(text)
        except RuntimeError:
            pass

    def _searched(self, found, missing):
        try:
            self.bar.hide()
        except RuntimeError:
            return
        self._busy = False
        self.found.update(found)
        for p in found:
            self.__dict__.setdefault("_missing", set()).discard(p)
        self.__dict__.setdefault("_missing", set()).update(missing)
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            it = self.list.item(i)
            t = self._track(it.data(_ROLE))
            if t is not None:
                self._label(it, t)
        self.list.blockSignals(False)
        kinds = [f[1] for f in found.values()]
        fake = kinds.count("fake")
        parts = [f"Нашёл FLAC: {len(found)} из {len(found) + len(missing)}"]
        if fake:
            parts.append(f"подделок (пересжатых MP3): {fake} — их не ставлю")
        if missing:
            parts.append(f"не найдено: {len(missing)} — правый клик → «Купить в lossless»")
        self.status.setText(". ".join(parts) + ".")
        self._sync_buttons()

    # ── замена ── #
    def apply(self):
        ready = self._ready()
        if not ready or self._busy:
            return
        problems, done = [], 0
        trash = self.trash.isChecked()
        for t, c in ready:
            msg = replace(self.win, t, c["path"], trash)
            if msg:
                problems.append(f"{t.get('title') or Path(t['path']).stem}: {msg}")
            if not msg or any(w in msg for w in ("Корзину", "играет", "тирлиста")):   # заменён, мелочь не вышла
                done += 1
                self.found.pop(str(t.get("path", "")), None)
        self.tracks = mp3_tracks(self.win)
        self._fill()
        text = f"Заменено на FLAC: {done}."
        if problems:
            text += " " + "; ".join(problems[:3]) + (" …" if len(problems) > 3 else "")
        self.status.setText(text)
        try:
            self.win._toast(f"FLAC вместо MP3: {done}")
        except Exception:                                      # noqa: BLE001
            pass

    # ── купить ── #
    def _menu(self, pos):
        it = self.list.itemAt(pos)
        if it is None:
            return
        t = self._track(it.data(_ROLE))
        if t is None:
            return
        m = QMenu(self)
        for name, url in store_links(t):
            m.addAction(f"Купить в lossless: {name}", lambda u=url: QDesktopServices.openUrl(QUrl(u)))
        f = self.found.get(str(t.get("path", "")))
        if f is not None:
            m.addAction("Показать найденный FLAC", lambda: self.win.reveal_in_explorer(f[0]["path"]))
        m.exec(self.list.viewport().mapToGlobal(pos))

    def _buy_current(self):
        it = self.list.currentItem()
        t = self._track(it.data(_ROLE)) if it is not None else None
        if t is None:
            self.status.setText("Выберите трек в списке — откроется его поиск на Bandcamp.")
            return
        QDesktopServices.openUrl(QUrl(store_links(t)[0][1]))


class FlacUpgradeDialog(QDialog):
    """То же окном — из меню выделенных треков."""

    def __init__(self, win, tracks=None):
        super().__init__(win)
        self.setWindowTitle("MP3 → FLAC")
        self.resize(720, 620)
        ph, pw = _ph()
        if ph is not None and win.settings.get("ya_layout", "phantom") == "phantom":
            try:
                self.setStyleSheet(ph.app_qss() + ph.qss() + f"QDialog{{background:{ph.BG_RAISED};}}")
            except Exception:                                  # noqa: BLE001
                pass
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 20, 22, 18)
        v.setSpacing(10)
        v.addWidget(_lab("MP3 → FLAC", "PhHeading"))
        self.tool = FlacUpgrade(win, tracks, self)
        v.addWidget(self.tool, 1)
        close = _btn("Закрыть", "ghost")
        close.clicked.connect(self.accept)
        h = QHBoxLayout()
        h.addStretch(1)
        h.addWidget(close)
        v.addLayout(h)


def open_for(win, tracks):
    """Окно «MP3 → FLAC» с отмеченными заранее треками (только MP3 из них)."""
    mp3 = [t for t in tracks or [] if str(t.get("path", "")).lower().endswith(".mp3")]
    dlg = FlacUpgradeDialog(win, mp3)
    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dlg.show()
    if mp3:
        dlg.tool.search()
    return dlg
