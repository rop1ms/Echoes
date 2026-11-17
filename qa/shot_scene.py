"""Снимки режима «Сцена» без запуска плеера: заглушка оболочки, настоящий SceneMode, несколько разных треков.

    <python плеера> qa/shot_scene.py [папка для снимков] [гифка или картинка для первого трека]

Пишет scene_<трек>.png и печатает облик каждого трека и время одного кадра. Данные — во временном профиле."""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
_HOME = tempfile.mkdtemp(prefix="echoes-scene-")
os.environ["USERPROFILE"] = os.environ["HOME"] = _HOME          # ~/Echoes — временный: свои настройки не трогаем

from PyQt6.QtGui import QColor, QImage, QPainter, QRadialGradient  # noqa: E402
from PyQt6.QtCore import QPointF  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

TRACKS = [
    {"path": "a.mp3", "title": "untitled", "artist": "semmmyq & shinra", "cols": ("#ffffff", "#e3261c"),
     "prof": {"families": ["hyperpop"], "energy": 0.8, "valence": 0.6},
     "lines": ["Эти блики ослепляют, эти фоточки с цепями", "Тот reflection из Китая, почему всё исчезает?",
               "Эти птицы улетают, твой level недосягаем", "Сильный дождь, он лечит раны, эти деньги пропадают",
               "Кончилась любовь, как сижки, в телефоне пять процентов"]},
    {"path": "b.mp3", "title": "Холодное оружие", "artist": "Sqwore & rizza", "cols": ("#3a35b0", "#b9b6ff"),
     "prof": {"energy": 0.34, "valence": 0.3},
     "lines": ["Жертвуй ради дамы, будто пешка", "Холодное оружие, как снежинки",
               "Кончилась любовь, как сижки, зима в моём сердце", "Снег идёт, и холод лечит раны",
               "Цена её любви как ашкудишка"]},
    {"path": "c.mp3", "title": "Пепел", "artist": "NIGHT DRIVE", "cols": ("#120406", "#c2161f"),
     "prof": {"families": ["phonk"], "energy": 0.9, "valence": 0.2},
     "lines": ["Этот город горит, я лечу сквозь огонь", "Скорость двести, и пламя за моей спиной",
               "Дым в глазах, но я вижу дорогу домой", "Пепел на руках, сердце бьётся в такт",
               "Никогда не вернусь, это мой последний шаг"]},
    {"path": "d.mp3", "title": "Daybreak", "artist": "Lunar Fields", "cols": ("#ffd9a0", "#ff8f6b"),
     "prof": {"energy": 0.3, "valence": 0.72},
     "lines": ["We were dreaming by the ocean all night", "Every wave was a secret you told me",
               "The sun came up and I saw your smile", "Hold my heart like the sea holds the sky",
               "Forever is a word I never knew till now"]},
]


def make_cover(path, cols):
    img = QImage(600, 600, QImage.Format.Format_RGB32)
    img.fill(QColor(cols[0]))
    p = QPainter(img)
    g = QRadialGradient(QPointF(380, 260), 330)
    g.setColorAt(0, QColor(cols[1]))
    g.setColorAt(1, QColor(cols[0]))
    p.fillRect(img.rect(), g)
    p.end()
    img.save(str(path))
    return str(path)


class Engine:
    duration = 187.0
    preset_factor = 1.0
    pos = 0.0

    def get_position(self):
        return self.pos

    def is_playing(self):
        return True


class Lyrics:
    def __init__(self, lines):
        import word_sync
        self._lines = [{"ms": 1000 + 3500 * i, "text": t} for i, t in enumerate(lines)]
        self._has_timings = True
        self._words = [None] * len(self._lines)
        self._est = word_sync.estimate(self._lines)


class Win:
    shuffle = False
    repeat_mode = 0

    def __init__(self):
        self.engine = Engine()
        self.lyrics_view = None
        self._intel_profiles = {}


class Shell(QWidget):
    def __init__(self, cover=""):
        super().__init__()
        self.win = Win()
        self._t = None
        if cover:
            self.set_track({"path": "x.mp3", "title": "untitled", "artist": "semmmyq & shinra", "cover": cover,
                            "lines": TRACKS[0]["lines"], "prof": None})

    def set_track(self, t):
        self._t = t
        self.win.lyrics_view = Lyrics(t["lines"])
        self.win._intel_profiles = {t["path"]: t.get("prof")} if t.get("prof") else {}

    def current_track(self):
        return self._t

    def is_playing(self):
        return True

    def is_liked(self, _t):
        return True

    def _seek_frac(self, _f):
        pass


def wait_assets(app, sc, key, seconds=40):
    t0 = time.time()
    while (sc._key != key or sc._pending is not None) and time.time() - t0 < seconds:
        app.processEvents()
        time.sleep(0.01)
    return time.time() - t0


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "qa" / "results"
    art = sys.argv[2] if len(sys.argv) > 2 else ""
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv[:1])
    import scene_art
    import scene_cards
    from scene_mode import SceneMode
    SceneMode.ART_NET = False
    sh = Shell()
    sh.resize(1280, 720)
    sc = SceneMode(sh)
    sc.setGeometry(sh.rect())
    sc._op = sc._op_to = 1.0
    for n, t in enumerate(TRACKS):
        t = dict(t, cover=make_cover(Path(_HOME) / f"cover{n}.png", t["cols"]))
        if n == 0 and art:
            scene_art.set_user_art(scene_cards.scene_key(t["artist"], t["title"]), art)
        sh.set_track(t)
        sc._sync_track(force=True)
        took = wait_assets(app, sc, t["path"])
        for pos in (5.2, 9.4):
            sh.win.engine.pos = pos
            for _ in range(60):
                sc._tick()
                app.processEvents()
                time.sleep(0.012)
        sc.grab().save(str(out / f"scene_{n}.png"))
        lk = sc._look
        t0 = time.perf_counter()
        for _ in range(40):
            sc.grab()
        ms = (time.perf_counter() - t0) / 40 * 1000
        print(f"{n}: {lk['mood']:7} dark={lk['dark']!s:5} {sc._g['layout']:6} card={lk['card']:7} mark={lk['mark']:9} "
              f"frame={sc._frame:8} pattern={lk['pattern']:6} air={lk['particles']:7} font={sc._family or 'default':18} "
              f"art={sc._art_info.get('source')}{'/gif' if sc._movie else ''} ready={took:.2f}s frame={ms:.1f}ms")


if __name__ == "__main__":
    main()
