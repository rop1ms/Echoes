"""Смена трека не должна останавливать интерфейс: обложка декодируется один раз, своя фоновая запись
коллекции не принимается за чужую, цветокоррекция размытия идёт по маленькой копии.

Замер на настоящем окне — qa/probe_hitches.py; здесь — причины, по одной."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from PyQt6.QtGui import QColor, QImage  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])
import atomic_json  # noqa: E402
import blur_fx  # noqa: E402
import img_load  # noqa: E402
import library_guard as LG  # noqa: E402


class HotCover(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.path = str(Path(self.tmp.name) / 'cover.png')
        img = QImage(1000, 800, QImage.Format.Format_RGB32)
        img.fill(QColor('#c04080'))
        img.save(self.path)
        img_load.forget()

    def tearDown(self):
        img_load.forget()
        self.tmp.cleanup()

    def test_one_decode_serves_every_size(self):
        self.assertTrue(img_load.warm(self.path))
        with patch.object(img_load, '_decode', side_effect=AssertionError('decoded again')):
            for side in (64, 208, 240, 256, 1200, 1600):
                got = img_load.read_image(self.path, side)
                self.assertFalse(got.isNull())
                self.assertEqual(max(got.width(), got.height()), min(side, 1000))
            self.assertEqual(img_load.read_image(self.path).width(), 1000)      # целиком — тоже из памяти
            self.assertTrue(img_load.warm(self.path))                           # повторный прогрев ничего не стоит

    def test_same_result_as_plain_decode(self):
        plain = img_load.read_image(self.path, 240)
        img_load.warm(self.path)
        hot = img_load.read_image(self.path, 240)
        self.assertEqual((plain.width(), plain.height()), (hot.width(), hot.height()))
        self.assertEqual(plain.pixelColor(100, 100).name(), hot.pixelColor(100, 100).name())

    def test_replaced_file_is_read_again(self):
        img_load.warm(self.path)
        other = QImage(300, 300, QImage.Format.Format_RGB32)
        other.fill(QColor('#00ff00'))
        other.save(self.path)
        os.utime(self.path, ns=(1, 1))                                          # подпись файла точно другая
        got = img_load.read_image(self.path, 1600)
        self.assertEqual(got.width(), 300)
        self.assertEqual(got.pixelColor(10, 10).name(), '#00ff00')

    def test_only_neighbours_are_kept(self):
        paths = []
        for i in range(img_load.HOT_KEEP + 2):
            p = str(Path(self.tmp.name) / f'c{i}.png')
            QImage(32, 32, QImage.Format.Format_RGB32).save(p)
            img_load.warm(p)
            paths.append(p)
        self.assertEqual(len(img_load._HOT), img_load.HOT_KEEP)
        self.assertNotIn(paths[0], img_load._HOT)
        self.assertFalse(img_load.warm(''))
        self.assertFalse(img_load.warm(str(Path(self.tmp.name) / 'missing.png')))


class OwnBackgroundWrite(unittest.TestCase):
    def test_own_async_save_is_not_reloaded_as_foreign(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            d = Path(tmp)
            f = d / 'library.json'
            lib = [{'path': str(d / f'{i}.mp3'), 'title': str(i)} for i in range(50)]
            atomic_json.save_json(f, lib)
            loads = []

            def load(path):
                loads.append(path)
                return atomic_json.load_json(path, [])
            g = LG.Guard(d, f, load, atomic_json.save_json_async)
            g.loaded(lib)
            for n in range(4):                                  # как длительность трека на каждой смене трека
                lib[n]['duration'] = 100.0 + n
                self.assertEqual(g.save(lib), 0)
                atomic_json.flush()
            self.assertEqual(loads, [], 'own background write was mistaken for another ECHOES')
            # а чужая запись по-прежнему объединяется
            other = atomic_json.load_json(f, []) + [{'path': str(d / 'new.mp3'), 'title': 'new'}]
            f.write_text(__import__('json').dumps(other), 'utf-8')
            self.assertEqual(g.save(lib), 1)
            self.assertEqual(len(loads), 1)
            atomic_json.flush()                                 # фоновая запись — до удаления временной папки


class BlurColorOnWorkCopy(unittest.TestCase):
    def test_saturation_runs_on_small_image(self):
        src = QImage(600, 600, QImage.Format.Format_RGB32)
        src.fill(QColor('#804020'))
        seen = []
        real = blur_fx.saturate

        def spy(img, s):
            seen.append((img.width(), img.height()))
            return real(img, s)
        with patch.object(blur_fx, 'saturate', spy):
            out = blur_fx.blurred_cover(src, 1400, 800, 90.0, sat=1.45)
        self.assertEqual((out.width(), out.height()), (1400, 800))
        self.assertEqual(len(seen), 1)
        self.assertLess(seen[0][0] * seen[0][1], 1400 * 800 / 16, 'colour work must use the small blurred copy')


class ProgressTimes(unittest.TestCase):
    def test_times_reserve_room_and_follow_seconds(self):
        import yamusic_theme as Y
        line = Y.ProgressLine()
        line.resize(900, 20)
        self.assertEqual(line.PAD, Y.ProgressLine.PAD)
        line.show_times(True)
        self.assertEqual(line.PAD, Y.ProgressLine.TIME_PAD)
        line.set_state(0.5, 200.0)
        line.set_state(0.5 + 0.0002, 200.0)                     # меньше полпикселя и та же секунда — без перерисовки
        self.assertEqual(line.frac, 0.5)
        line.set_state(0.5 + 0.0051, 200.0)                     # следующая секунда — подпись обновляется
        self.assertNotEqual(line.frac, 0.5)
        line.grab()                                             # отрисовка с подписями не падает
        line.deleteLater()


if __name__ == '__main__':
    unittest.main()
