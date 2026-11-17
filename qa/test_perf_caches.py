"""Мелкие ускорения: цвета обложек запоминаются между запусками, шрифты ников подключаются по одному стилю.

python qa/test_perf_caches.py
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["USERPROFILE"] = os.environ["HOME"] = tempfile.mkdtemp(prefix="echoes-perf-test-")   # ~/Echoes — временный
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from PyQt6.QtGui import QColor, QFontDatabase, QImage  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv[:1])
fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


# ── цвета обложек ── #
import img_load  # noqa: E402
import ya_decor  # noqa: E402

tmp = Path(tempfile.mkdtemp())
cover = tmp / "c.png"
img = QImage(200, 200, QImage.Format.Format_RGB32)
img.fill(QColor("#d02030"))
img.save(str(cover))
first = ya_decor.palette(str(cover))
check(len(first[0]) >= 3 and first[0][0].red() > first[0][0].blue(), "цвета красной обложки посчитаны")
ya_decor._pal_save()
saved = json.loads(ya_decor._pal_file().read_text("utf-8"))
check(len(saved) == 1 and next(iter(saved)).startswith(str(cover)), "цвета записаны на диск")

reads = []
real_read = img_load.read_image
img_load.read_image = lambda *a, **k: (reads.append(a), real_read(*a, **k))[1]
ya_decor._PAL.clear()                                          # «новый запуск»: память пуста, диск есть
ya_decor._PAL_DISK = None
again = ya_decor.palette(str(cover))
check(not reads, "при следующем запуске обложка не читается — цвета взяты с диска")
check([c.name() for c in again[0]] == [c.name() for c in first[0]] and abs(again[1] - first[1]) < 1e-3,
      "цвета с диска те же")
time.sleep(0.02)
img.fill(QColor("#2040d0"))
img.save(str(cover))                                           # обложку заменили — запись устарела
os.utime(cover, (time.time() + 5, time.time() + 5))
ya_decor._PAL.clear()
changed = ya_decor.palette(str(cover))
check(reads and changed[0][0].blue() > changed[0][0].red(), "изменённая обложка пересчитана")
n_before = len(ya_decor._pal_disk())
ya_decor._PAL.clear()
missing = ya_decor.palette(str(tmp / "нет.png"))
check(len(missing[0]) >= 3 and len(ya_decor._pal_disk()) == n_before, "запасные цвета (нет файла) на диск не пишутся")
ya_decor._pal_file().write_text("{сломано", "utf-8")
ya_decor._PAL.clear()
ya_decor._PAL_DISK = None
check(len(ya_decor.palette(str(cover))[0]) >= 3, "битый файл цветов не мешает")
img_load.read_image = real_read

# ── шрифты ников ── #
import net_nick  # noqa: E402

total = len(list(net_nick.FONT_DIR.glob("*.ttf")))
net_nick.font_for("gg", 20)
check(net_nick._pending is None and not net_nick._loaded, "обычному нику шрифты не подключаются")
net_nick.font_for("bangers", 20)
fams = set(QFontDatabase.families())
check("Bangers" in fams and "Russo One" in fams and len(net_nick._pending) == total - 2,
      f"нику со стилем — только его два файла из {total}")
bad = []
for key, _label, latin, cyr in net_nick.FONTS[1:]:
    net_nick.font_for(key, 20)
    fams = set(QFontDatabase.families())
    if latin not in fams or cyr not in fams:
        bad.append(key)
check(not bad, f"у каждого стиля находятся оба шрифта (не нашлись: {bad})")
check(net_nick._loaded and not net_nick._pending, "все стили показаны — подключено всё")
net_nick._loaded, net_nick._pending = False, None
net_nick._load_fonts()
check(net_nick._loaded, "окно выбора стиля подключает все шрифты разом")

print("\nИТОГ:", "все проверки пройдены" if not fails else f"{len(fails)} ошибок")
sys.exit(1 if fails else 0)
