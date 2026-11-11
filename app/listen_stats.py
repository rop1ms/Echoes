# listen_stats.py
"""
Статистика прослушивания: общее время, топ треков и исполнителей, недавно
игравшее. Данные — в ~/Echoes/stats.json. Окно профиля открывается по
клику на аватар.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QListWidget,
                             QWidget, QPushButton)

RECENT_MAX = 200
SAVE_EVERY = 15.0          # сек между сохранениями на диск


def fmt_dur(sec) -> str:
    sec = int(max(0, sec))
    h, m = sec // 3600, sec % 3600 // 60
    if h >= 24:
        return f"{h // 24} д {h % 24} ч {m} мин"
    if h:
        return f"{h} ч {m} мин"
    return f"{m} мин {sec % 60} с" if m else f"{sec} с"


def _first_artist(a: str) -> str:
    return (a or "").split(",")[0].strip() or "Неизвестный исполнитель"


class ListenStats:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data = {"total": 0.0, "tracks": {}, "artists": {}, "recent": [], "days": {}}
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                self.data.update(d)
        except Exception:                            # noqa: BLE001
            pass
        self._last = None                            # monotonic последнего тика
        self._dirty = False
        self._saved = time.monotonic()
        # журнал прослушиваний по годам (history/2026.jsonl): календарь, «в этот день год назад», итоги года
        self.hist_dir = self.path.parent / "history"
        self._hist_cache = {}
        try:
            if not self.hist_dir.exists() and self.data.get("recent"):
                self.hist_dir.mkdir(parents=True, exist_ok=True)   # первый запуск — перенести «недавние»
                for r in reversed(self.data["recent"]):
                    self._hist_write(r)
        except OSError:
            pass

    # ── запись ── #

    def tick(self, track, playing: bool):
        """Вызывать часто (≈10 раз/с): копит время, пока трек реально играет."""
        now = time.monotonic()
        last, self._last = self._last, now
        if not playing or not track or last is None:
            return
        dt = now - last
        if not 0 < dt < 2:                           # пауза/подвисание не считаем
            return
        key = str(track.get("path", ""))
        if not key:
            return
        d = self.data
        d["total"] += dt
        day = time.strftime("%Y-%m-%d")
        d["days"][day] = d["days"].get(day, 0.0) + dt
        t = d["tracks"].setdefault(key, {"title": "", "artist": "", "sec": 0.0, "plays": 0})
        t["title"], t["artist"] = track.get("title", ""), track.get("artist", "")
        t["sec"] += dt
        a = d["artists"].setdefault(_first_artist(track.get("artist")), {"sec": 0.0, "plays": 0})
        a["sec"] += dt
        self._dirty = True
        if now - self._saved > SAVE_EVERY:
            self.save()

    def record_play(self, track):
        """Трек начал играть: +1 прослушивание и запись в «недавние»."""
        key = str((track or {}).get("path", ""))
        if not key:
            return
        d = self.data
        t = d["tracks"].setdefault(key, {"title": "", "artist": "", "sec": 0.0, "plays": 0})
        t["title"], t["artist"] = track.get("title", ""), track.get("artist", "")
        t["plays"] += 1
        d["artists"].setdefault(_first_artist(track.get("artist")), {"sec": 0.0, "plays": 0})["plays"] += 1
        rec = d["recent"]
        item = {"path": key, "title": track.get("title", ""), "artist": track.get("artist", ""),
                "ts": int(time.time())}
        if track.get("cover"):
            item["cover"] = str(track.get("cover"))
        rec.insert(0, item)
        self._hist_write(item)
        del rec[RECENT_MAX:]
        self._dirty = True
        self.save()

    def save(self):
        if not self._dirty:
            return
        try:
            payload = json.dumps(self.data, ensure_ascii=False).encode("utf-8")
            try:                                     # диск — в фоновом потоке (на смене трека это были 5–20 мс)
                import atomic_json
                atomic_json.save_bytes_async(self.path, payload)
            except ImportError:
                tmp = self.path.with_suffix(".tmp")
                tmp.write_bytes(payload)
                tmp.replace(self.path)
            self._dirty = False
            self._saved = time.monotonic()
        except Exception as e:                       # noqa: BLE001
            print("[stats] save:", e)

    def _hist_write(self, item):
        try:
            ts = int(item.get("ts") or time.time())
            f = self.hist_dir / f"{time.localtime(ts).tm_year}.jsonl"
            self.hist_dir.mkdir(parents=True, exist_ok=True)
            with open(f, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({k: item.get(k) for k in ("ts", "path", "title", "artist", "cover") if item.get(k)},
                                    ensure_ascii=False) + "\n")
            self._hist_cache.pop(time.localtime(ts).tm_year, None)
        except (OSError, ValueError, TypeError):
            pass

    def history(self, year: int) -> list:
        """Все прослушивания за год: [{ts, path, title, artist, cover?}] по времени."""
        hit = self._hist_cache.get(year)
        if hit is not None:
            return hit
        out = []
        try:
            with open(self.hist_dir / f"{year}.jsonl", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        r = json.loads(line)
                        if isinstance(r, dict) and r.get("ts"):
                            out.append(r)
                    except ValueError:
                        pass
        except OSError:
            pass
        out.sort(key=lambda r: r["ts"])
        self._hist_cache[year] = out
        return out

    def plays_on(self, date: str) -> list:
        """Прослушивания за день «ГГГГ-ММ-ДД»."""
        y = int(date[:4])
        return [r for r in self.history(y) if time.strftime("%Y-%m-%d", time.localtime(r["ts"])) == date]

    # ── чтение ── #

    def seconds_since(self, days: int) -> float:
        """Сколько секунд слушали за последние days дней (1 — только сегодня)."""
        cut = time.strftime("%Y-%m-%d", time.localtime(time.time() - (days - 1) * 86400))
        return sum(v for k, v in self.data["days"].items() if k >= cut)

    def top_tracks(self, n=20):
        items = [v for v in self.data["tracks"].values() if v.get("plays") or v.get("sec", 0) > 5]
        return sorted(items, key=lambda v: (v.get("plays", 0), v.get("sec", 0)), reverse=True)[:n]

    def top_artists(self, n=20):
        items = [(k, v) for k, v in self.data["artists"].items() if v.get("plays") or v.get("sec", 0) > 5]
        return sorted(items, key=lambda kv: (kv[1].get("sec", 0), kv[1].get("plays", 0)), reverse=True)[:n]

    def recent_artists(self, n=12):
        seen, out = set(), []
        for r in self.data["recent"]:
            a = _first_artist(r.get("artist"))
            if a not in seen:
                seen.add(a)
                out.append(a)
            if len(out) >= n:
                break
        return out


class ProfileDialog(QDialog):
    def __init__(self, win, stats: ListenStats, on_edit=None):
        super().__init__(win)
        self.stats = stats
        self.setWindowTitle("Профиль")
        self.setMinimumSize(520, 560)
        lay = QVBoxLayout(self)
        head = QHBoxLayout()
        self.head = QLabel("")
        self.head.setObjectName("Big")
        head.addWidget(self.head, 1)
        if on_edit:
            b = QPushButton("Изменить профиль")
            b.clicked.connect(lambda: (on_edit(), self.refresh(win.profile)))
            head.addWidget(b)
        lay.addLayout(head)
        self.total = QLabel("")
        self.total.setObjectName("Sub")
        lay.addWidget(self.total)
        self.tabs = QTabWidget()
        self.l_recent_art, self.l_recent, self.l_top, self.l_art = (QListWidget() for _ in range(4))
        recent = QWidget()
        rv = QVBoxLayout(recent)
        rv.addWidget(QLabel("Недавние исполнители"))
        self.l_recent_art.setMaximumHeight(170)
        rv.addWidget(self.l_recent_art)
        rv.addWidget(QLabel("Недавние треки"))
        rv.addWidget(self.l_recent, 1)
        self.tabs.addTab(recent, "Недавнее")
        self.tabs.addTab(self.l_top, "Топ треков")
        self.tabs.addTab(self.l_art, "Топ исполнителей")
        lay.addWidget(self.tabs, 1)
        self.refresh(win.profile)

    def refresh(self, profile=None):
        s, d = self.stats, self.stats.data
        s.save()
        p = profile or {}
        self.head.setText(f"{p.get('nickname', 'user')} — {p.get('status', '')}")
        n_plays = sum(v.get("plays", 0) for v in d["tracks"].values())
        self.total.setText(f"Всего прослушано: {fmt_dur(d['total'])}   ·   запусков треков: {n_plays}")
        self.l_recent_art.clear()
        self.l_recent_art.addItems(s.recent_artists())
        self.l_recent.clear()
        for r in d["recent"][:50]:
            ts = time.strftime("%d.%m %H:%M", time.localtime(r.get("ts", 0)))
            self.l_recent.addItem(f"{r.get('artist', '')} — {r.get('title', '')}      {ts}")
        self.l_top.clear()
        for i, v in enumerate(s.top_tracks(), 1):
            self.l_top.addItem(f"{i:>2}. {v.get('artist', '')} — {v.get('title', '')}      "
                               f"{v.get('plays', 0)} раз · {fmt_dur(v.get('sec', 0))}")
        self.l_art.clear()
        for i, (name, v) in enumerate(s.top_artists(), 1):
            self.l_art.addItem(f"{i:>2}. {name}      {fmt_dur(v.get('sec', 0))} · {v.get('plays', 0)} раз")
