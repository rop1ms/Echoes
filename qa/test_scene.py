"""Режим «Сцена»: движок карточек (ключевые слова, счётчики, свои сцены из файла) и сам экран на заглушке
оболочки — открывается, рисует кадр, идёт по строкам, закрывается и отпускает картинки.

python qa/test_scene.py
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["USERPROFILE"] = os.environ["HOME"] = tempfile.mkdtemp(prefix="echoes-scene-test-")   # ~/Echoes — временный
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "qa"))

import scene_cards as sc  # noqa: E402

fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


TX = ["Эти блики ослепляют, эти фоточки с цепями",
      "Тот reflection из Китая, почему всё исчезает?",
      "Эти птицы улетают, твой level недосягаем",
      "Сильный дождь, он лечит раны, эти деньги пропадают",
      "Рано утром часто бывает день",
      "Кончилась любовь, как сижки, в телефоне пять процентов"]
MS = [i * 3500.0 for i in range(len(TX))]
import scene_director as sd  # noqa: E402


def build(tx, ms):
    """Сцену строит «режиссёр» (scene_director.plan): образы строк, карточки, уведомления, тема."""
    return sd.plan(tx, ms, "Song")[0]


scene, theme = sd.plan(TX, MS, "Song")
check(len(scene) == len(TX), "сцена есть для каждой строки")
check(all(isinstance(e.get("cards"), list) and 1 <= len(e["cards"]) <= 2 for e in scene),
      "у каждой строки одна-две карточки")
check(all(all(c.get("title") for c in e["cards"]) for e in scene), "у карточек есть заголовки")
check(all(all(0 <= k < len(TX[i].split(" ")) for k in e.get("keys", [])) for i, e in enumerate(scene)),
      "ключевые слова — из своей строки")
check(isinstance(theme, str) and theme, f"у песни есть образ-тема ({theme})")
check(scene == build(TX, MS), "сцена одна и та же при каждом расчёте")
st = sd.stat("Темп", "♫", 128, "BPM")
check(st["title"] == "Темп" and st["layout"] == "stat", "карточка-показатель режиссёра")
check(sc.card_value({"kind": "time", "a": 125, "b": 5, "unit": "", "bar": None}, 0.0)[0] == "2:05", "время — мм:сс")
check(sc.card_value({"kind": "money", "a": 12480, "b": 0, "unit": " ₽", "bar": None}, 0.0)[0] == "12 480 ₽",
      "сумма — с разрядами")
v0, f0 = sc.card_value({"kind": "pct", "a": 10, "b": 60, "unit": "", "bar": None}, 0.0)
v1, f1 = sc.card_value({"kind": "pct", "a": 10, "b": 60, "unit": "", "bar": None}, 1.0)
check(v0.endswith("%") and int(v1[:-1]) > int(v0[:-1]), f"счётчик растёт: от {v0} до {v1}")
check(len(build(["la la la", "ooh"], [0.0, 2000.0])) == 2, "строки без слов — без падений")
check(build([], []) == [], "пустой текст")

with tempfile.TemporaryDirectory() as d:                       # своя сцена из файла
    p = sc.export(scene, TX, Path(d) / "s.json")
    data = json.loads(p.read_text("utf-8"))
    data["lines"][TX[1]]["cards"] = [{"emoji": "🪞", "title": "Reflection", "kind": "pct", "a": 99, "b": 1}]
    data["lines"][TX[1]]["keys"] = [1, 99]
    data["lines"][TX[0]]["cards"] = [{"title": "битая"}]
    p.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    over = sc.apply_overrides(build(TX, MS), TX, p)
    check(over[1]["cards"][0]["title"] == "Reflection" and over[1]["keys"] == [1], "строка из файла заменила расчёт")
    check(over[0]["cards"] == scene[0]["cards"], "битая карточка в файле не принята")
    p.write_text("{не json", "utf-8")
    check(sc.apply_overrides(build(TX, MS), TX, p) == scene, "битый файл — сцена как без него")

# ── экран ── #
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv[:1])
import shot_scene  # noqa: E402
import numpy as np  # noqa: E402
from PyQt6.QtGui import QColor  # noqa: E402
import scene_art  # noqa: E402
import scene_look  # noqa: E402
from scene_mode import SceneMode, palette  # noqa: E402

SceneMode.ART_NET = False

# ── облик трека (scene_look: по образу строки, обложке и звуку) ── #
hard = {"families": ["hyperpop"], "energy": 0.9}
calm = {"energy": 0.3}
a = scene_look.make(hard, 0.2, "rain")
check(a == scene_look.make(hard, 0.2, "rain"), "облик трека один и тот же при каждом расчёте")
check(a["dark"] and a["pattern"] == "grid", "яркий жёсткий трек с тёмной обложкой: тёмная сцена, сетка")
c = scene_look.make(calm, 0.8, "")
check(not c["dark"] and c["pattern"] == "blobs" and c["speed"] > a["speed"], "спокойный светлый трек — другой облик")
check(a["particles"] != "dust" and c["particles"] == "dust", "образ песни задаёт, что летает в воздухе")
dk = palette([QColor("#c2161f")], dark=True)
check(dk["base"].lightnessF() < 0.15 and dk["ink"].lightnessF() > 0.85, "тёмная палитра: тёмный фон, светлые буквы")

# ── гифка, персонаж ── #
check(scene_art.gif_matches("Sqwore Холодное оружие edit", "Sqwore & rizza", "Холодное оружие"),
      "гифка с названием трека в описании подходит")
check(not scene_art.gif_matches("sqwore concert funny", "Sqwore & rizza", "Холодное оружие"),
      "гифка только к исполнителю — не подходит")
check(not scene_art.gif_matches("untitled goose dancing", "semmmyq", "untitled")
      and scene_art.gif_matches("semmmyq untitled", "semmmyq", "untitled"),
      "короткое название из одного слова — нужен ещё и исполнитель")
white = np.full((120, 100, 4), 255, np.uint8)
figure = white.copy()
figure[30:104, 30:70, :3] = (220, 30, 30)
feet = figure.copy()
feet[104:120, 44:56, :3] = (220, 30, 30)                       # стоит на нижнем крае
check(scene_art.plain_border(figure) and scene_art.plain_border(feet), "ровный фон с трёх сторон — можно вырезать")
noisy = white.copy()
noisy[..., :3] = np.random.default_rng(1).integers(0, 255, (120, 100, 3))
check(not scene_art.plain_border(noisy), "пёстрый фон — не вырезаем")
half = white.copy()
half[:, :50, :3] = 0
check(not scene_art.plain_border(half), "стороны разного цвета — не вырезаем")
from PIL import Image  # noqa: E402
tmp = Path(tempfile.mkdtemp())
Image.fromarray(figure, "RGBA").convert("RGB").save(tmp / "fig.png")
cut = scene_art.static_cutout(str(tmp / "fig.png"))
check(cut is not None and cut.shape[1] < 70 and cut[..., 3].max() == 255, "персонаж вырезан и обрезан по краям")
r0 = scene_art.resolve("k1", "cover.png")
check(r0["source"] == "cover" and not r0["cut"], "по умолчанию — обложка, целиком")
scene_art.set_flag("k1", "cut", True)
check(scene_art.resolve("k1", "cover.png")["cut"], "обложку режем только по просьбе")
scene_art.set_user_art("k1", str(tmp / "fig.png"))
r1 = scene_art.resolve("k1", "cover.png")
check(r1["source"] == "user" and r1["path"].endswith("fig.png") and not r1["animated"], "своя картинка важнее обложки")
scene_art.set_user_art("k1", None)
check(scene_art.resolve("k1", "cover.png")["source"] == "cover", "убрали свою — снова обложка")
check(scene_art.fetch_auto("k2", "A", "T", ("", ""), "") == "", "в сеть за гифкой — только с ключом")
from PyQt6.QtGui import QColor  # noqa: E402

pal = palette([QColor("#ffffff"), QColor("#e02a1c"), QColor("#202020")])
check(pal["accent"].hslHueF() < 0.05 or pal["accent"].hslHueF() > 0.95, "акцент — красный с красно-белой обложки")
check(pal["base"].lightnessF() > 0.8 and pal["ink"].lightnessF() < 0.2, "фон светлый, чернила тёмные")
check(palette([QColor("#808080")])["accent"].isValid(), "серая обложка — запасная палитра")

sh = shot_scene.Shell(str(ROOT / "app" / "icon.png"))
sh.resize(1280, 720)
sh.show()
s = SceneMode(sh)
s.open()
t0 = time.time()
while s._bg is None and time.time() - t0 < 10:
    app.processEvents()
    time.sleep(0.01)
check(s._bg is not None and s._under is not None and s._art is not None, "картинки готовы в фоне")
check(s.is_open(), "экран открыт")
seen = set()
for pos in (0.5, 2.0, 5.0, 9.0, 12.0, 16.0):
    sh.win.engine.pos = pos
    s._tick()
    seen.add(s._li)
    img = s.grab().toImage()
check(seen == {-1, 0, 1, 2, 3, 4}, f"строки идут за временем: {sorted(seen)}")
check(not img.isNull() and (img.pixelColor(40, 40).lightnessF() > 0.5) == (not s._pal["dark"]),
      "кадр нарисован, фон в тон облика (светлый или тёмный)")
check(any(e.get("note") for e in s._scene), "у сцены есть уведомления (выезжают при обычном проигрывании строки)")
s.resize(700, 420)
s._tick()
check(not s.grab().isNull() and s._g["card1"].right() < s._g["cover"].left(), "узкое окно — карточки не под обложкой")
g_ = s._g
check(g_["queue"].bottom() < s.height() and g_["vol"].top() > g_["play"].bottom(), "громкость и значки помещаются под кнопками")
s.close_mode(instant=True)
check(not s.is_open() and not s._timer.isActive(), "закрыт, таймер кадров остановлен")
s._free_at = time.monotonic() - 1
s._free_assets()
check(s._bg is None and s._art is None and s._movie is None and not s._emoji, "после закрытия картинки отпущены")

# своя гифка на месте обложки: играет, персонаж вырезан, после закрытия отпускается
frames = [Image.new("RGB", (80, 80), (255, 255, 255)) for _ in range(4)]
for i, fr in enumerate(frames):
    for x in range(30, 50):
        for y in range(16 + i * 4, 66):
            fr.putpixel((x, y), (200, 40, 40))
frames[0].save(tmp / "a.gif", save_all=True, append_images=frames[1:], duration=80, loop=0)
scene_art.set_user_art(sc.scene_key(s._artist, s._title), str(tmp / "a.gif"))
s.open()
t0 = time.time()
while (s._movie is None or s._pending is not None) and time.time() - t0 < 20:
    app.processEvents()
    time.sleep(0.01)
check(s._movie is not None and s._art_info.get("source") == "user", "своя гифка играет на месте обложки")
check(s._frame == "free", "у гифки с ровным фоном персонаж вырезан")
s._tick()
check(not s.grab().isNull(), "кадр с гифкой рисуется")
check(s.art_menu().actions()[0].text().startswith("Своя гифка"), "меню картинки открывается")
s.close_mode(instant=True)
s._free_at = time.monotonic() - 1
s._free_assets()
check(s._movie is None, "гифка отпущена после закрытия")

print("\nИТОГ:", "все проверки пройдены" if not fails else f"{len(fails)} ошибок")
sys.exit(1 if fails else 0)
