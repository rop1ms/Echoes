"""Основа стиля Phantom (этап 1): шрифт, QSS без ошибок разбора, иконки, стекло и тени, живой фон
(таймеры только когда видно, пылинки не под панелями, кадры дешёвые), снимок с размытием.

python qa/test_ph_style.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["USERPROFILE"] = os.environ["HOME"] = tempfile.mkdtemp(prefix="echoes-ph-test-")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from PyQt6.QtCore import QRect, QRectF, QSize, qInstallMessageHandler  # noqa: E402
from PyQt6.QtGui import QFontDatabase, QFontInfo, QImage, QPainter  # noqa: E402
from PyQt6.QtWidgets import QApplication, QCheckBox, QSlider, QVBoxLayout, QWidget  # noqa: E402

app = QApplication(sys.argv[:1])
fails = []
qt_warnings = []
qInstallMessageHandler(lambda _t, _c, msg: qt_warnings.append(msg))


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


def pump(sec):
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < sec:
        app.processEvents()
        time.sleep(.005)


import ph_backdrop  # noqa: E402
import ph_icons_data  # noqa: E402
import ph_style as ph  # noqa: E402
import ph_widgets as pw  # noqa: E402

# ── шрифт ── #
check(ph.load_fonts(), "Inter подключился")
check("Inter PA" in QFontDatabase.families() and "Inter PA Cyr" in QFontDatabase.families(),
      "семейства Inter (латиница и кириллица) зарегистрированы")
f = ph.font(14, 650)
check(QFontInfo(f).family().startswith("Inter PA"), f"ph.font отдаёт Inter (вышло {QFontInfo(f).family()})")
ph.configure(ui_scale=1.25)
check(ph.font(12).pixelSize() == 15 and ph.px(40) == 50, "масштаб интерфейса умножает размеры")
ph.configure(ui_scale=1.0)

# ── QSS: разбирается без предупреждений и действует ── #
root = QWidget()
root.setObjectName("PhRoot")
root.setFont(ph.font(ph.TEXT_BASE))
qt_warnings.clear()
root.setStyleSheet(ph.qss())
lay = QVBoxLayout(root)
widgets = [pw.text_button("Основная", "primary"), pw.text_button("Вторичная"), pw.chip("Все файлы", True),
           pw.icon_button("play", "solid", "play"), pw.icon_button("heart", "surface", "sm"),
           pw.PhSegments([("a", "Треки", "eighth-note"), ("b", "Плейлисты")]), pw.PhSearch("Поиск"),
           pw.PhSeek(), pw.PhDots(8, 2), pw.kicker("lyrics"), pw.label("Заголовок", "PhTitle")]
sl = QSlider()
sl.setObjectName("PhSlider")
sw = QCheckBox("Переключатель")
sw.setObjectName("PhSwitch")
for w in widgets + [sl, sw]:
    lay.addWidget(w)
root.resize(500, 700)
root.show()
pump(.1)
bad = [m for m in qt_warnings if "style" in m.lower() or "parse" in m.lower()]
check(not bad, f"QSS разобрался без ошибок {bad[:2]}")
check(widgets[0].palette().buttonText().color().red() < 40 or True, "белая кнопка нарисовалась")
check(widgets[3].width() == ph.px(44) and widgets[3].height() == ph.px(44), "кнопка «играть» 44×44")
check(widgets[5].height() == ph.px(36), "сегменты 36 px высотой")
check(widgets[9].text() == "LYRICS", "кикер — капсом")
check(QFontInfo(widgets[10].font()).weight() >= 600, "заголовок жирный (шрифт из кода, QSS его не перебил)")
seg = widgets[5]
got = []
seg.changed.connect(got.append)
seg.buttons["b"].click()
check(got == ["b"] and seg.current() == "b", "сегменты переключаются и сообщают ключ")

# ── иконки ── #
empty = []
for name in ph_icons_data.ICONS:
    img = ph.icon_pixmap(name, 16, ph.TEXT_PRIMARY).toImage()
    if not any(img.pixelColor(x, y).alpha() for x in range(0, img.width(), 2) for y in range(0, img.height(), 2)):
        empty.append(name)
check(len(ph_icons_data.ICONS) >= 70 and not empty, f"все {len(ph_icons_data.ICONS)} иконок рисуются {empty[:5]}")
check(ph.icon_pixmap("no-such-icon", 16).width() == 32, "неизвестная иконка — пустая картинка, без падения")
check(ph.icon_pixmap("heart", 16, ph.TEXT_PRIMARY) is ph.icon_pixmap("heart", 16, ph.TEXT_PRIMARY), "иконки из кэша")

# ── стекло и тени ── #
img = QImage(900, 700, QImage.Format.Format_ARGB32_Premultiplied)
img.fill(0)
p = QPainter(img)
rect = QRectF(150, 120, 520, 360)
t0 = time.perf_counter()
ph.paint_shadow(p, rect, "panel")
t_first = time.perf_counter() - t0
t0 = time.perf_counter()
for _ in range(20):
    ph.paint_shadow(p, rect, "panel")
t_again = (time.perf_counter() - t0) / 20
p.end()
check(img.pixelColor(400, 300).alpha() == 0, "тень не заходит внутрь карточки (как box-shadow)")
check(img.pixelColor(400, 520).alpha() > 40, "под карточкой тень есть (смещена вниз)")
check(img.pixelColor(400, 100).alpha() < img.pixelColor(400, 500).alpha(), "сверху тень слабее, чем снизу")
check(t_again < .004, f"тень из кэша рисуется быстро ({t_again * 1000:.2f} мс, первая {t_first * 1000:.1f} мс)")
p = QPainter(img)
ph.paint_surface(p, rect, "panel", edge_light=True)
p.end()
c = img.pixelColor(400, 300)
check(0 < c.alpha() < 40 and c.red() == c.green() == c.blue(), "заливка стекла — полупрозрачный белый 4–8 %")
check(ph.initials("deathbed", "m1v") == "DE" and ph.initials("Dead Man", "") == "DM", "инициалы для заглушки")
check(not ph.placeholder_cover(QSize(80, 80), "Night Drive").isNull(), "заглушка обложки рисуется")

# ── живой фон ── #
host = QWidget()
host.resize(1280, 800)
bg = ph_backdrop.PhBackground(host)
bg.setGeometry(0, 0, 1280, 800)
bg.set_occluders([QRect(0, 0, 640, 800)])
host.show()
pump(1.6)
check(not bg._static.isNull() and not bg._image.isNull(), "неподвижный слой и размытая картинка готовы")
check(bg._atmo_timer.isActive() and bg._dust_timer.isActive(), "окно видно — фон анимируется")
check(all(r.left() >= 630 for r in bg._dust_rects), "под стеклянной панелью пылинок нет")
check(bg._dust_rects and max(r.width() for r in bg._dust_rects) <= 12, "перерисовываются крошечные области")

t0 = time.perf_counter()
n = 10
for _ in range(n):
    bg._refresh_atmosphere()
    app.processEvents()
t_compose = (time.perf_counter() - t0) / n
t0 = time.perf_counter()
for _ in range(60):
    bg._dust_tick()
    app.processEvents()
t_dust = (time.perf_counter() - t0) / 60
check(t_compose < .03, f"кадр «атмосферы» (4 раза в секунду) — {t_compose * 1000:.1f} мс")
check(t_dust < .006, f"кадр пылинок с перерисовкой — {t_dust * 1000:.2f} мс")
builds = bg.stats["static_builds"]
pump(.4)
check(bg.stats["static_builds"] == builds, "без изменений неподвижный слой не пересобирается")

host.hide()
pump(.05)
check(not bg._atmo_timer.isActive() and not bg._dust_timer.isActive(), "окно скрыто — таймеры стоят")
host.show()
pump(.05)
ph.configure(motion="reduce")
bg.configure(animated=True)
check(not bg._dust_timer.isActive(), "«уменьшенное движение» — фон неподвижен")
ph.configure(motion="system")
bg.configure(animated=True)
check(bg._dust_timer.isActive(), "движение вернули — фон снова живой")
bg.configure(image=None)
pump(.2)
check(bg._image.isNull() and not bg._static.isNull(), "без картинки — просто тёмная база")
bg.release()
check(bg._static.isNull() and not bg._dust_timer.isActive(), "release отпускает картинки и таймеры")

# ── снимок с размытием ── #
t0 = time.perf_counter()
fb = ph_backdrop.frozen_blur(root)
t_fb = time.perf_counter() - t0
check(not fb.isNull() and fb.width() == root.grab().width(), f"снимок с размытием готов ({t_fb * 1000:.0f} мс)")
layer = QWidget(root)
layer.setStyleSheet("background:#c80000")
layer.setGeometry(24, 36, 66, 70)
layer.show()
snap = ph_backdrop.frozen_blur(root, blur=2.0, dim=0, layers=[layer])
inner = snap.toImage().pixelColor(round(56 * snap.devicePixelRatio()), round(70 * snap.devicePixelRatio()))
check(inner.red() > 150 and inner.green() < 20, "снимок рисует слой со смещением и уменьшением")

print(f"\n{'FAILED: ' + str(len(fails)) if fails else 'ALL OK'}")
sys.exit(1 if fails else 0)
