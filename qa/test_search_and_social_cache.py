"""Regression checks for collection search and HiDPI raster cache limits."""
import base64
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PROFILE = tempfile.TemporaryDirectory(prefix="echoes-cache-test-")
os.environ["USERPROFILE"] = os.environ["HOME"] = PROFILE.name
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication

import emoji_pack
import net_frames
import net_reactions
import search_util
from net_page import _AVATARS, avatar_pm

APP = QApplication.instance() or QApplication([])


def frame_png(rgb):
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))

    pixels = (b"\0" * 49) * 8 + (b"\0" + bytes(rgb) * 16) * 8
    image = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 2, 0, 0, 0)) +
             chunk(b"IDAT", zlib.compress(pixels, 0)) + chunk(b"IEND", b""))
    return base64.b64encode(image).decode("ascii")


class SearchAndSocialCache(unittest.TestCase):
    def setUp(self):
        for cache in (_AVATARS, emoji_pack._pm_cache, net_reactions._pm_cache, net_frames._CACHE):
            cache.clear()
            self.addCleanup(cache.clear)

    def test_search_keeps_layout_transliteration_and_live_metadata(self):
        track = {"title": "Запись 13", "artist": "Серёга + Linkin Park", "album": "Live"}
        for q in ("serega live", "дштлшт 13", "live — серёга", "Запись; Linkin", ["park live"], "---"):
            with self.subTest(query=q):
                self.assertTrue(search_util.track_matches(q, track))
        track["artist"] = "Бумбокс"
        self.assertFalse(search_util.track_matches("сере live", track))
        self.assertTrue(search_util.track_matches("bumboks", track))

    def test_distinct_custom_frames_with_same_png_prefix_and_length(self):
        red, blue = frame_png((255, 0, 0)), frame_png((0, 0, 255))
        self.assertEqual((red[:64], len(red)), (blue[:64], len(blue)))
        a = net_frames.frame_pixmap({"id": "custom", "png": red}, 24)
        b = net_frames.frame_pixmap({"id": "custom", "png": blue}, 24)
        self.assertEqual(a.toImage().pixelColor(24, 40), QColor("#ff0000"))
        self.assertEqual(b.toImage().pixelColor(24, 40), QColor("#0000ff"))

    def test_cache_bytes_use_physical_hidpi_dimensions(self):
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / "image.png"
            image = QImage(64, 64, QImage.Format.Format_RGB32)
            image.fill(QColor("#ee7733"))
            self.assertTrue(image.save(str(path)))
            with patch.object(emoji_pack, "_file", return_value=path), patch.object(net_reactions, "_file", return_value=path):
                for number in range(320):
                    emoji_pack.pixmap(chr(0x4000 + number), 48)
                    net_reactions.pixmap(f"c:{number:016x}", 48)
                    avatar_pm(f"profile-{number}", "Name", 144)
                    png = frame_png((number % 256, number // 256, 128))
                    net_frames.frame_pixmap({"id": "custom", "png": png}, 144)
            for cache in (_AVATARS, emoji_pack._pm_cache, net_reactions._pm_cache, net_frames._CACHE):
                self.assertLessEqual(cache.bytes, cache.limit)
                self.assertLess(len(cache.items), 320)
            retained = avatar_pm("profile-319", "Name", 144)
            self.assertEqual((retained.width(), retained.devicePixelRatio()), (288, 2.0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
