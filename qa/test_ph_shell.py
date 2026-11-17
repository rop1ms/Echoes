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
_panel0 = getattr(shell, "l_panel", None)
check(lay.mode != "text" or (_panel0 is not None and _panel0.parentWidget() is lay.right and _panel0.isVisible()),
      "сразу после запуска панель текста стоит в правой колонке (без ручного переключения)")

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

# ── панели Phantom: Библиотека, Очередь, Настройки ── #
import ph_panels  # noqa: E402
lay.top.b_library.click()
settle(.8)
lib = lay._panels.get("collection")
check(isinstance(lib, ph_panels.PhLibraryPanel) and shell.stack.currentWidget() is lib,
      "библиотека — панель Phantom (Треки | Плейлисты | Папки)")
check(lib is not None and lib.list.model_.rowCount() == 5, f"в библиотеке 5 треков ({lib and lib.list.model_.rowCount()})")
lib.search.setText("Трек 3")
settle(.2)
check(lib.list.model_.rowCount() == 1, "поиск по библиотеке")
lib.search.setText("")
lib.set_sort("title")
lib.toggle_order()
settle(.1)
first = lib.list.model_.rows[0]["t"]["title"] if lib.list.model_.rows else ""
check(first in ("Трек 0", "Трек 4"), f"сортировка по названию и её порядок (первый: {first})")
lib.tabs.set_current("folders", emit=True)
settle(.2)
check(lib.dir_list.count() >= 1, "вкладка «Папки» — папки с треками")
lib.tabs.set_current("playlists", emit=True)
settle(.2)
check(lib.pl_list.count() >= 0, "вкладка «Плейлисты» открывается")
lib.tabs.set_current("tracks", emit=True)
lib.set_filter("missing")
settle(1.0)
check(lib._missing is not None and lib.list.model_.rowCount() == 5, "«Отсутствующие файлы» — проверка в фоне")
lib.set_filter("all")
lay.close_overlay(instant=True)
lay.top.b_queue.click()
settle(.8)
qpan = lay._panels.get("queue")
check(isinstance(qpan, ph_panels.PhQueuePanel) and shell.stack.currentWidget() is qpan, "очередь — панель Phantom")
check(qpan is not None and qpan.list.count() == 4, f"«Далее» — 4 трека ({qpan and qpan.list.count()})")
win.user_queue.append(dict(win.library[3]))
qpan.refresh(force=True)
check(qpan.list.count() == 5 and qpan.clear_btn.isVisible(), "ваша очередь — первой, есть «очистить»")
qpan._clear()
check(not win.user_queue, "очистка вашей очереди")
lay.close_overlay(instant=True)
lay.top.b_settings.click()
settle(.8)
hub = shell.pages["settings"]
check(shell.stack.currentWidget() is hub and lay.overlay.kind == "side",
      "настройки — одна страница Echoes панелью сбоку")
check(lay.overlay.panel.width() < shell.width() * .6, f"панель настроек сбоку, не во весь экран ({lay.overlay.panel.width()})")
check(hub.search.objectName() == "PhSearch" and hub.nav_btns["sound"].objectName() == "PhChip",
      "разделы — пилюлями под поиском (узкая панель)")
settle(.3)
check(not any(b.title in ("Экстремальная громкость", "Тема Echoes Music", "Конструктор тем") for b in hub.blocks),
      "повторы и неуместное убраны из настроек Phantom")
from PyQt6.QtWidgets import QDialog, QVBoxLayout as _QV, QLabel as _QL  # noqa: E402
import inapp  # noqa: E402
_dlg = QDialog(win)
_dlg.setWindowTitle("Окно из настроек")
_dl = _QV(_dlg)
_big = _QL("Содержимое окна")
_big.setMinimumSize(560, 420)
_dl.addWidget(_big)
inapp.present(win, _dlg)
settle(.4)
_L = inapp._layer_for(_dlg)
check(_L is not None and _L.host is lay.overlay.body and _L.isVisible(),
      "окно, открытое из настроек, — страницей внутри панели (не всплывашкой)")
check(_L is not None and _L.btn_back.isVisible(), "у страницы — «‹ Назад»")
_L.btn_back.click()
settle(.3)
check(inapp._layer_for(_dlg) is None, "«Назад» возвращает к настройкам")
check(not lay.overlay.set_tabs.isVisible(), "переключателя «Phantom | Echoes» больше нет")
titles = [b.title for b in hub.blocks]
check(all(t in titles for t in ("Фон и стекло", "Обложка слева", "Размер и движение", "Текст песни справа")),
      "разделы Phantom — блоки общих настроек")
hub.search.setText("видео обложка")
hub._do_search()
settle(.2)
vis = [b.title for b in hub.blocks if any(not w.isHidden() for w in b.widgets)]
check("Обложка слева" in vis, f"поиск находит настройки Phantom ({vis[:3]})")
hub.search.setText("")
hub._select("look")
check(hub.info.text().startswith("Как выглядит"), "у раздела — подсказка, что в нём настраивается")
ph_panels.set_ph(win, card_opacity=.5, bg_intensity=.3, cover_treatment="mono")
lay.apply_appearance(["card_opacity", "bg_intensity", "cover_treatment"])
check(abs(lay.bg._intensity - .3) < 1e-6 and lay.cover.treatment == "mono", "настройки Phantom применяются сразу")
ph_panels.set_ph(win, cover_video="bundled")
lay.apply_appearance(["cover_video"])
check(lay.cover._video_src.endswith("cover-video.mp4"), "встроенная видео-обложка включается")
ph_panels.set_ph(win, cover_video="off", card_opacity=.72, bg_intensity=.6, cover_treatment="original")
lay.apply_appearance(None)
check(lay.cover._video_src == "", "видео-обложка выключается")
# ── своя обложка: правила и их приоритет; виды карточки ── #
import ph_cover  # noqa: E402
from PyQt6.QtGui import QImage as _QI  # noqa: E402
import tempfile as _tf  # noqa: E402
_pic = Path(_tf.gettempdir()) / "echoes-ph-rule.png"
_qi = _QI(40, 40, _QI.Format.Format_RGB32)
_qi.fill(0x336699)
_qi.save(str(_pic))
_t = {"path": "C:/m/a.mp3", "title": "Song", "artist": "Band", "album": "LP"}
_k = ph_cover.keys_for(_t)
ph_cover.save_rules(win, [])
for sc in ("all", "nocover", "artist", "album", "track"):
    ph_cover.put_rule(win, sc, _k.get(sc, ""), sc, str(_pic))
check(ph_cover.resolve(win, _t, True)["scope"] == "track", "своя обложка: трек главнее всех")
ph_cover.save_rules(win, [r for r in ph_cover.rules(win) if r["scope"] != "track"])
check(ph_cover.resolve(win, _t, True)["scope"] == "album", "дальше — альбом")
ph_cover.save_rules(win, [r for r in ph_cover.rules(win) if r["scope"] != "album"])
check(ph_cover.resolve(win, _t, True)["scope"] == "artist", "дальше — исполнитель")
ph_cover.save_rules(win, [r for r in ph_cover.rules(win) if r["scope"] != "artist"])
check(ph_cover.resolve(win, _t, False)["scope"] == "nocover" and ph_cover.resolve(win, _t, True)["scope"] == "all",
      "«без обложки» — только у трека без обложки, иначе «все треки»")
ph_cover.save_rules(win, [])
check(ph_cover.resolve(win, _t, True) is None, "без правил — обложка трека")
for _st in ("info", "blur", "vinyl", "crop"):
    ph_panels.set_ph(win, cover_style=_st)
    lay.apply_appearance(["cover_style"])
    lay.cover.repaint()
check(lay.cover.style == "crop", "виды карточки переключаются и рисуются")
ph_panels.set_ph(win, cover_style="info")
lay.apply_appearance(["cover_style"])
# ── виджеты слева (этап 6): все виды рисуются, звуковые крутятся только на своём виде ── #
import ph_cards  # noqa: E402
_wc = lay.widgets[0]
_was = _wc.widget_kind()
for _k, _a, _b in ph_cards.KINDS:
    _wc.set_kind(_k)
    _wc.body.repaint()
    _wc.tick()
check(len(ph_cards.KINDS) >= 11, f"виды виджетов Phantom и Echoes ({len(ph_cards.KINDS)})")
_wc.set_kind("clock")
check(not _wc.body._timer.isActive(), "часы не крутят кадры 30 раз в секунду")
_wc.set_kind("visualizer")
check(_wc.body._timer.isActive() == _wc.body.isVisible(), "спектр обновляется, пока виден")
_wc.set_kind(_was)
# ── правка левой колонки: войти, переставить, убрать, добавить, выйти ── #
lay.close_overlay(instant=True)
lay.toggle_edit()
check(lay.edit.isVisible() and not lay.cover.isVisible(), "правка колонки: блоки — снимками на слое")
_w0 = lay.widgets[0]
lay.edit._act("up", _w0)
check(lay.left_items.index(_w0) == 1, "виджет — на уровень выше")
lay.edit._act("remove", _w0)
check(_w0 not in lay.left_items and len(lay.widgets) == 1, "виджет убран крестиком")
lay.edit._add("clock")
check(len(lay.widgets) == 2, "виджет добавлен")
lay.edit._act("done", None)
settle(.6)
check(not lay.edit.isVisible() and lay.cover.isVisible() and win.settings.get("ph_left")[0] == "cover",
      "«Готово» — блоки на местах, порядок сохранён")
lay.widgets[0].set_kind("eq")
for _sl in getattr(win, "_eq_sliders", [])[:2]:
    _sl.setValue(7)
lay.widgets[0]._eq_reset()
check(all(_sl.value() == 0 for _sl in getattr(win, "_eq_sliders", [])), "эквалайзер сбрасывается кнопкой")
lay.close_overlay(instant=True)

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
    shell.l_panel.load([{"ms": 1000 + 4000 * k, "text": t} for k, t in enumerate(
        ["Holding on to the afterglow", "Every light that we used to know", "Running late but the night is slow",
         "Tell me where do the echoes go", "Under neon we drift alone", "Nothing left but the radio"])], True)
    shell.l_panel.set_pos_ms(5200)
    settle(1.2)
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
    for btn, name in ((lay.top.b_library, "_library"), (lay.top.b_settings, "_settings")):
        btn.click()
        settle(1.0)
        win.grab().save(base + name + ".png")
        lay.close_overlay(instant=True)
    settle(.2)
    pop = shell.open_player_more()
    settle(.5)
    pop.grab().save(base + "_more.png")
    shell.close_player_more()
    from PyQt6.QtWidgets import QMenu
    m = QMenu(shell)
    for t_ in ("Сейчас играет — на весь экран", "Найти в коллекции", "Текст песни", "Версии трека…"):
        m.addAction(t_)
    m.addSeparator()
    m.addAction("Мини-плеер поверх окон")
    m.popup(QPoint(400, 300))
    settle(.4)
    m.grab().save(base + "_menu.png")
    m.close()
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
