"""MP3 → FLAC: сопоставление треков, проверка на «пересжатый из MP3» и замена; фон Phantom из обложки."""
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from PyQt6.QtCore import QObject, pyqtSignal                      # noqa: E402
from PyQt6.QtGui import QColor, QImage                          # noqa: E402
from PyQt6.QtWidgets import QApplication                        # noqa: E402

import flac_upgrade as fu                                       # noqa: E402

APP = QApplication.instance() or QApplication([])
FF = fu._ffmpeg()


def wait_for(cond, sec=60):
    until = time.monotonic() + sec
    while not cond() and time.monotonic() < until:
        APP.processEvents()
        time.sleep(.01)
    return cond()


def make_audio(path, lowpass=None, seconds=40, title="Night Drive"):
    """Шум на всю полосу (как настоящая запись) или «подделка»: тот же шум через MP3 (lowpass — его битрейт
    в кбит/с), упакованный обратно во FLAC."""
    src = ["-f", "lavfi", "-i", "anoisesrc=d=%d:c=pink:r=44100:a=0.3" % seconds]
    if lowpass:
        mp3 = str(path) + ".src.mp3"
        subprocess.run([FF, "-v", "error", "-y", *src, "-ac", "2", "-c:a", "libmp3lame", "-b:a", f"{lowpass}k", mp3],
                       check=True, capture_output=True, timeout=60)
        src = ["-i", mp3]
    subprocess.run([FF, "-v", "error", "-y", *src, "-ac", "2", "-metadata", "artist=Test Artist",
                    "-metadata", f"title={title}", str(path)], check=True, capture_output=True, timeout=60)
    if lowpass:
        os.remove(mp3)


class Matching(unittest.TestCase):
    def test_norm_drops_junk_and_feat(self):
        self.assertEqual(fu.norm("Night Drive (Official Audio) feat. Someone"), "night drive")
        self.assertEqual(fu.norm("Ёлка [HQ]"), "елка")

    def test_match_by_tags_and_duration(self):
        t = {"path": "a.mp3", "artist": "Test Artist", "title": "Night Drive (Official Video)", "duration": 200}
        good = {"path": "x.flac", "artist": "Test Artist", "title": "Night Drive", "duration": 201.5}
        wrong_len = {"path": "y.flac", "artist": "Test Artist", "title": "Night Drive", "duration": 260}
        other = {"path": "z.flac", "artist": "Test Artist", "title": "Day Walk", "duration": 200}
        c, score = fu.match(t, [wrong_len, other, good])
        self.assertIs(c, good)
        self.assertGreater(score, .9)
        self.assertEqual(fu.match(t, [wrong_len, other]), (None, 0.0))

    def test_match_from_filename(self):
        t = {"path": "C:/m/Test Artist - Night Drive.mp3", "artist": "", "title": "", "duration": 0}
        c, _ = fu.match(t, [{"path": "q.flac", "artist": "Test Artist", "title": "Night Drive", "duration": 0}])
        self.assertIsNotNone(c)

    def test_store_links_are_search_pages(self):
        links = dict(fu.store_links({"artist": "A B", "title": "C"}))
        self.assertIn("bandcamp.com/search?q=A+B+C", links["Bandcamp"])


@unittest.skipUnless(FF, "нет ffmpeg")
class Spectrum(unittest.TestCase):
    def test_real_and_fake_flac(self):
        with tempfile.TemporaryDirectory() as d:
            real, fake = Path(d) / "real.flac", Path(d) / "fake.flac"
            make_audio(real)
            make_audio(fake, lowpass=128)
            kr, _ = fu.verdict(fu.read_meta(str(real)), fu.spectrum_cutoff(str(real), 40))
            kf, line = fu.verdict(fu.read_meta(str(fake)), fu.spectrum_cutoff(str(fake), 40))
            self.assertEqual(kr, "real")
            self.assertEqual(kf, "fake", line)


class _Bridge(QObject):
    call = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(lambda fn: fn())


class _Win:
    def __init__(self, lib):
        self.library = lib
        self.settings = {}
        self._ui_bridge = _Bridge()
        self.replaced = []

    def replace_track_file(self, old, new, delete_old=True):
        self.replaced.append((old, new, delete_old))
        i = next(i for i, x in enumerate(self.library) if x["path"] == old)
        self.library[i] = {"path": str(Path(new).resolve()), "title": "Night Drive", "artist": "Test Artist",
                           "cover": "", "genre": ""}
        return ""

    def _save_library(self):
        pass

    def _schedule_settings_save(self):
        pass

    def _toast(self, _text):
        pass


@unittest.skipUnless(FF, "нет ffmpeg")
class Tool(unittest.TestCase):
    def test_search_marks_fake_and_replaces_only_real(self):
        with tempfile.TemporaryDirectory() as d:
            mp3a, mp3b = Path(d) / "a.mp3", Path(d) / "b.mp3"
            mp3a.write_bytes(b"\0" * 10)
            mp3b.write_bytes(b"\0" * 10)
            fl = Path(d) / "flac"
            fl.mkdir()
            make_audio(fl / "Test Artist - Night Drive.flac")
            make_audio(fl / "Test Artist - Day Walk.flac", lowpass=128, title="Day Walk")
            lib = [{"path": str(mp3a), "artist": "Test Artist", "title": "Night Drive", "duration": 40,
                    "cover": "c.jpg", "genre": "synthwave"},
                   {"path": str(mp3b), "artist": "Test Artist", "title": "Day Walk", "duration": 40, "cover": ""}]
            win = _Win(lib)
            win.settings["flac_dirs"] = [str(fl)]
            tool = fu.FlacUpgrade(win, [lib[0], lib[1]])
            tool.search()
            self.assertTrue(wait_for(lambda: not tool._busy, 90), tool.status.text())
            kinds = {Path(p).name: f[1] for p, f in tool.found.items()}
            self.assertEqual(kinds, {"a.mp3": "real", "b.mp3": "fake"})
            self.assertEqual(len(tool._ready()), 1)
            tool.apply()
            self.assertEqual([Path(n).name for _o, n, _d in win.replaced], ["Test Artist - Night Drive.flac"])
            self.assertEqual(win.library[0]["cover"], "c.jpg")       # обложка и жанр — от прежнего трека
            self.assertEqual(win.library[0]["genre"], "synthwave")
            tool.deleteLater()


class CoverBackdrop(unittest.TestCase):
    def test_palette_follows_cover_colors(self):
        img = QImage(40, 40, QImage.Format.Format_RGB32)
        img.fill(QColor(220, 30, 40))
        for y in range(20, 40):
            for x in range(40):
                img.setPixelColor(x, y, QColor(30, 60, 220))
        import ph_backdrop
        pal = ph_backdrop.cover_palette(img)
        hues = sorted(round(c.hsvHueF() * 360) for c in pal[:2])
        self.assertTrue(any(h < 20 or h > 340 for h in hues), hues)   # красный
        self.assertTrue(any(200 < h < 250 for h in hues), hues)       # синий
        grey = QImage(10, 10, QImage.Format.Format_RGB32)
        grey.fill(QColor(120, 120, 120))
        self.assertEqual(len(ph_backdrop.cover_palette(grey)), 3)

    def test_cover_background_flows_and_fades(self):
        import ph_backdrop
        import ph_style as ph
        ph.configure(effects=True, motion="full")
        bg = ph_backdrop.PhBackground()
        bg.resize(320, 200)
        bg.show()
        self.assertTrue(wait_for(lambda: not bg._static.isNull(), 5))
        bg.set_flow(True)
        cover = QImage(64, 64, QImage.Format.Format_RGB32)
        cover.fill(QColor(240, 120, 20))
        bg.set_cover(cover, None)
        self.assertTrue(bg._flow_active())
        self.assertEqual(bg._atmo_timer.interval(), ph_backdrop.FLOW_MS)
        self.assertTrue(wait_for(lambda: bg.__dict__.get("_shown_serial") == bg._image_serial, 10))
        self.assertFalse(bg._fade_from.isNull())                        # прежняя картинка тает
        bg.set_cover(None, None)                                        # без обложки — пятна гаснут
        self.assertEqual(bg._pal_to, [])
        bg.set_flow(False)
        self.assertEqual(bg._atmo_timer.interval(), ph_backdrop.ATMO_MS)
        bg.close()


if __name__ == "__main__":
    unittest.main()
