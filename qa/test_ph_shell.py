"""Раскладка Phantom (этап 2): настоящее окно ECHOES с ya_layout = "phantom" — верхняя полоса вместо заголовка
окна, левая колонка (обложка, плеер, виджеты), правая — ТЕКСТ (панель текста Echoes) и LIVE, панель «планеты» с
меню Echoes и выезжающие справа Библиотека / Очередь / Настройки; Esc и клик мимо закрывают; кнопки плеера
зовут окно; смена вида возвращает заголовок окна.

python qa/test_ph_shell.py [--shot путь.png]
"""
import os
import sys
import time
from pathlib import Path

SHOT = sys.argv[sys.argv.index("--shot") + 1] if "--shot" in sys.argv else ""
source = Path(__file__).with_name("ui_smoke.py").read_text("utf-8")
exec(compile(source.split("win = None")[0], str(Path(__file__).with_name("ui_smoke.py")), "exec"))
import json as _json  # noqa: E402
_st = _json.loads((data / "settings.json").read_text("utf-8"))
_st["custom_titlebar"] = True
_st["ya_layout"] = "phantom"
(data / "settings.json").write_text(_json.dumps(_st), encoding="utf-8")
import main  # noqa: E402
from PyQt6.QtCore import QPoint, Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

main.WindowsMediaKeyFilter.register = lambda self: None
fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


win = main.MainWindow()
win.resize(1440, 900)
win.show()
settle(1.2)
shell = win._ya
lay = shell.__dict__.get("ph")
check(lay is not None, "оболочка собрана в раскладке Phantom")
if lay is None:
    sys.exit(1)
tb = getattr(win, "titlebar", None)
check(tb is None or not tb.isVisible(), "заголовок окна ECHOES спрятан — его место заняла верхняя полоса")
check(lay.top.win_btns and all(b.isVisible() for b in lay.top.win_btns), "кнопки окна — в верхней полосе")
check(not lay.overlay.isVisible(), "открывается главным экраном, без панели")
check(lay.mode in ("text", "live"), f"режим правой колонки: {lay.mode}")

W = shell.width()
c, p_, r = lay.cover.geometry(), lay.player.geometry(), lay.right.geometry()
check(c.right() < r.left() and p_.right() < r.left(), "левая колонка не заходит на правую")
check(abs(c.width() / max(1, c.width() + r.width()) - .41) < .03, f"колонки ~41/59 ({c.width()} / {r.width()})")
check(c.bottom() < p_.top() and all(p_.bottom() < w.geometry().top() for w in lay.widgets),
      "обложка → плеер → виджеты сверху вниз")
check(all(w.geometry().bottom() < shell.height() for w in lay.widgets), "виджеты помещаются в окно")
isl = lay.island.geometry()
check(abs(isl.center().x() - W / 2) <= 2, "островок — по центру окна")

# ── текст в правой колонке ── #
win.library = [{"path": str(audit_home / f"{i}.wav"), "title": f"Трек {i}", "artist": "Артист", "duration": 200,
                "album": "Альбом"} for i in range(5)]
win.current_index = 0
lv = getattr(win, "lyrics_view", None)
if lv is not None:
    lv._lines = [{"ms": 1000 + 4000 * k, "text": f"Строка {k}"} for k in range(8)]
    lv._has_timings = True
lay.set_mode("text")
settle(.4)
panel = getattr(shell, "l_panel", None)
check(panel is not None and panel.parentWidget() is lay.right and panel.isVisible(),
      "панель текста Echoes стоит в правой колонке")
check(lay.right.kick.text() == "LYRICS", "шапка — LYRICS")
check(shell.__dict__.get("_now_playing") is None, "экран «Сейчас играет» во всё окно не создаётся")
check(lay.player.title.text().startswith("Трек 0"), f"карточка плеера показывает трек ({lay.player.title.text()})")
check("Синхронизировано" in lay.right.status.text(), f"статус текста: {lay.right.status.text().strip()}")

shell.toggle_lyrics()                                        # кнопка текста: ТЕКСТ → LIVE
settle(.3)
check(lay.mode == "live" and lay.right.live.isVisible() and not panel.isVisible(), "кнопка текста переключает на LIVE")
check(lay.top.mode.current() == "live", "переключатель LIVE|ТЕКСТ следует за режимом")
shell.open_now_playing(mode="lyrics")
settle(.3)
check(lay.mode == "text", "«Сейчас играет» в режиме текста — ТЕКСТ в правой колонке")
shell.show_page("lyrics")
settle(.2)
check(lay.mode == "text" and not lay.overlay.isVisible(), "страница «Текст» — правая колонка, без панели")

# ── «планета»: меню Echoes ── #
lay.top.b_planet.click()
settle(.8)
ov = lay.overlay
check(ov.isVisible() and ov.kind == "planet", "значок планеты открыл панель разделов")
check(ov.menu.isVisible() and ov.menu.current() == shell._cur_page, f"в меню отмечен раздел ({ov.menu.current()})")
check(shell.stack.parentWidget() is ov.body and shell.stack.isVisible(), "страницы Echoes — внутри панели")
pr = ov.panel.geometry()
check(pr.width() > W * .9, "панель разделов — почти во всё окно")
check(ov.panel.isVisible() and ov._snap.isNull(), "после анимации — живая панель, снимок отпущен")
check(lay.top.b_planet.isChecked(), "значок планеты подсвечен, пока панель открыта")
ov.menu.buttons["albums"].click()
settle(.6)
check(shell._cur_page == "albums" and ov.title.text() == "Альбомы", "меню переключает разделы и заголовок")
check(not lay.text_visible(), "под панелью разделов текст не тикает")

QTest.keyClick(ov.panel, Qt.Key.Key_Escape)
settle(.6)
check(not ov.isVisible(), "Esc закрывает панель")
check(not lay.top.b_planet.isChecked(), "значок погас")

# ── панели справа ── #
lay.top.b_queue.click()
settle(.7)
check(ov.isVisible() and ov.kind == "drawer" and shell._cur_page == "queue", "очередь — панелью справа")
dr = ov.panel.geometry()
check(dr.right() > W - 30 and dr.width() < W * .6, f"панель справа ({dr.x()}..{dr.right()})")
check(not ov.menu.isVisible() and ov.kick.text() == "QUEUE", "у панели — свой кикер, без меню разделов")
lay.top.b_settings.click()
settle(.6)
check(shell._cur_page == "settings" and ov.title.text() == "Настройки", "настройки — та же панель")
lay.top.b_settings.click()
settle(.6)
check(not ov.isVisible(), "повторный клик по значку закрывает панель")
lay.top.b_library.click()
settle(.7)
check(shell._cur_page == "collection" and ov.kind == "drawer", "библиотека — панелью справа")
QTest.mouseClick(ov, Qt.MouseButton.LeftButton, pos=QPoint(40, 400))
settle(.6)
check(not ov.isVisible(), "клик мимо панели закрывает её")

# ── плеер ── #
calls = []
real_toggle, real_next = win.toggle_play, win.next_track
win.toggle_play = lambda *a: calls.append("play")
win.next_track = lambda *a: calls.append("next")
pl = lay.player
try:
    pl.b_play.clicked.disconnect()
    pl.b_next.clicked.disconnect()
except TypeError:
    pass
pl.b_play.clicked.connect(win.toggle_play)
pl.b_next.clicked.connect(win.next_track)
pl.b_play.click()
pl.b_next.click()
check(calls == ["play", "next"], "кнопки карточки плеера зовут окно")
win.toggle_play, win.next_track = real_toggle, real_next
pl.tick(True, 30.0, 200.0)
check(pl.t_pos.text() == "0:30" and pl.t_dur.text() == "3:20", "время на карточке")
check(abs(pl.seek.value() - .15) < .01, "полоса перемотки")
t0 = time.perf_counter()
for i in range(200):
    lay.tick(True, 30.0 + i * .1, 200.0)
dt = (time.perf_counter() - t0) / 200
check(dt < .002, f"тик раскладки дешёвый ({dt * 1000:.2f} мс)")

if SHOT:
    lay.set_mode("text")
    settle(.8)
    win.grab().save(SHOT)
    base = SHOT[:-4] if SHOT.lower().endswith(".png") else SHOT
    lay.set_mode("live")
    settle(.4)
    win.grab().save(base + "_live.png")
    lay.top.b_planet.click()
    settle(1.0)
    win.grab().save(base + "_planet.png")
    lay.close_overlay(instant=True)
    lay.top.b_queue.click()
    settle(1.0)
    win.grab().save(base + "_queue.png")
    lay.close_overlay(instant=True)
    settle(.2)
    print("shot", SHOT, flush=True)

# ── смена вида возвращает заголовок окна ── #
win.settings["ya_layout"] = "new"
win._leave_ya_layout()
settle(.3)
check(tb is None or tb.isVisible(), "вне раскладки Phantom заголовок окна снова на месте")
win._enter_ya_layout()
settle(.6)
check(win._ya.__dict__.get("ph") is None, "вид «Новый» собирается как раньше")

print(f"\n{'FAILED: ' + str(len(fails)) if fails else 'ALL OK'}", flush=True)
os._exit(1 if fails else 0)
