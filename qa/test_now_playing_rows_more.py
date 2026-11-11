"""Экран «Сейчас играет», живые строки коллекции (альбом, лайк, эквалайзер) и «Ещё» в нижнем плеере.

python qa/test_now_playing_rows_more.py [папка-для-картинок]
"""
import sys
import time
from pathlib import Path

source = Path(__file__).with_name('ui_smoke.py').read_text('utf-8')
exec(compile(source.split('win = None')[0], str(Path(__file__).with_name('ui_smoke.py')), 'exec'))
import main, ui_anim
from PyQt6.QtCore import QPoint, QPointF, QRect, Qt
from PyQt6.QtGui import QColor, QImage, QMouseEvent, QPainter, QShortcut
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QAbstractButton, QStyle, QStyleOptionViewItem

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else None
main.WindowsMediaKeyFilter.register = lambda self: None
fails = []


def check(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg, flush=True)
    if not cond:
        fails.append(msg)


def wait(cond, seconds=4.0):
    until = time.monotonic() + seconds
    while time.monotonic() < until and not cond():
        settle(.05)
    return cond()


win = main.MainWindow()
win.resize(1440, 900)
win.show(); settle(.5)
shell = win._ya
import yamusic_theme as Y
from yamusic_theme import LIKED, TrackDelegate

# обложки — настоящие файлы: фон и карточка экрана строятся из них в фоновом потоке
covers = []
for i, col in enumerate(("#c0392b", "#2e86de", "#27ae60")):
    img = QImage(300, 300, QImage.Format.Format_RGB32)
    img.fill(QColor(col))
    p = audit_home / f"cover{i}.png"
    img.save(str(p))
    covers.append(str(p))
names = [("Zeta", "Bravo", "Bravo LP"), ("Alpha", "Charlie", "Alpha"), ("Mike", "Alpha", ""), ("Lima", "Delta", "Night Drive"),
         ("Kilo", "Delta", "Night Drive"), ("Echo", "Delta", "Unknown Album")]
win.library = [{"path": str(audit_home / f"{i}.wav"), "title": t, "artist": a, "duration": 100 + i, "album": alb,
                "cover": covers[i % 3]} for i, (t, a, alb) in enumerate(names)]
win.playlists = {LIKED: {"tracks": [dict(win.library[3])]}}
shell._liked_cache = None
win.queue_context, win.current_index = "library", 0
shell._dirty.add("collection"); shell.show_page("collection"); ui_anim._finish(shell.stack); settle(.4)
state = {"playing": True}
shell.is_playing = lambda: state["playing"]

# ───────────────────────────── строки коллекции ─────────────────────────────
view = shell.c_list
dele = view.itemDelegate()
rows = {r["t"]["title"]: (k, r) for k, r in enumerate(view.model_.rows)}
wide, narrow = QRect(0, 0, 1000, 56), QRect(0, 0, 600, 56)
check(TrackDelegate.album_zone(wide) is not None, "широкая строка: есть колонка альбома")
check(TrackDelegate.album_zone(narrow) is None, "узкая строка: колонки альбома нет")
check(TrackDelegate.album_of(rows["Zeta"][1]) == "Bravo LP", "альбом берётся из трека")
check(TrackDelegate.album_of(rows["Alpha"][1]) == "", "сингл с названием трека — альбом не дублируется")
check(TrackDelegate.album_of(rows["Mike"][1]) == "" and TrackDelegate.album_of(rows["Echo"][1]) == "",
      "пустой и «неизвестный» альбом не показываются")
check(TrackDelegate.album_hit(wide, rows["Zeta"][1]) is not None and TrackDelegate.album_hit(narrow, rows["Zeta"][1]) is None,
      "надпись альбома кликабельна только когда колонка видна")
z = TrackDelegate.album_zone(wide)
heart_r, cov_r = TrackDelegate.zones(wide)
check(z.right() < TrackDelegate.dots_zone(wide).left() and z.left() > cov_r.right() + 200,
      "колонка альбома — в середине, не налезает на «⋯» и название")


def paint_row(title, rect=wide, hover=False):
    k, _row = rows[title]
    opt = QStyleOptionViewItem()
    opt.rect = rect
    opt.widget = view
    opt.state = QStyle.StateFlag.State_Enabled | (QStyle.StateFlag.State_MouseOver if hover else QStyle.StateFlag.State_None)
    img = QImage(rect.width(), rect.height(), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    qp = QPainter(img)
    dele.paint(qp, opt, view.model_.index(k))
    qp.end()
    return img


def ink(img, r):
    """Сколько непрозрачных точек в прямоугольнике."""
    return sum(1 for y in range(max(0, r.top()), min(img.height(), r.bottom() + 1))
               for x in range(max(0, r.left()), min(img.width(), r.right() + 1)) if img.pixelColor(x, y).alpha() > 40)


def accent_px(img, r):
    acc = QColor(Y.YELLOW)
    n = 0
    for y in range(r.top(), r.bottom() + 1):
        for x in range(r.left(), r.right() + 1):
            c = img.pixelColor(x, y)
            if c.alpha() > 200 and abs(c.red() - acc.red()) + abs(c.green() - acc.green()) + abs(c.blue() - acc.blue()) < 40:
                n += 1
    return n


check(ink(paint_row("Lima"), z) > 30, "альбом нарисован в широкой строке")
check(ink(paint_row("Mike"), z) == 0, "без альбома середина строки пустая")
nz = QRect(int(600 * 0.52), 14, 120, 28)
check(ink(paint_row("Lima", narrow), nz) == ink(paint_row("Mike", narrow), nz), "в узкой строке альбом не рисуется")
check(accent_px(paint_row("Lima"), heart_r) > 20, "лайкнутый трек: сердце видно без наведения")
check(ink(paint_row("Kilo"), heart_r) == 0, "не лайкнутый: сердца без наведения нет")
check(ink(paint_row("Kilo", hover=True), heart_r) > 20, "наведение: контур сердца появляется")

win.settings["ui_animations"] = True
lv1 = TrackDelegate.eq_levels(True, now=1.0)
check(len(lv1) == TrackDelegate.EQ_BARS and lv1 != TrackDelegate.eq_levels(True, now=1.31), "эквалайзер живой, пока играет")
check(TrackDelegate.eq_levels(False, now=1.0) == TrackDelegate.eq_levels(False, now=2.0), "на паузе столбики застывшие")
check(all(0.0 < v <= 1.0 for v in lv1), "высоты столбиков в пределах обложки")
view._eq_at = 0.0
cur_img = paint_row("Zeta")                                    # Zeta — текущий трек (current_index = 0)
check(accent_px(cur_img, cov_r) > 25, "играющая строка: эквалайзер на обложке")
check(view._eq_timer is not None and view._eq_timer.isActive() and view._eq_row == rows["Zeta"][0],
      "по кадрам обновляется только играющая строка")
check(accent_px(paint_row("Kilo"), cov_r) == 0, "у остальных строк эквалайзера нет")
hov = paint_row("Zeta", hover=True)
check(accent_px(hov, cov_r) == 0 and hov != cur_img, "наведение на играющую строку: значок вместо эквалайзера")
check(paint_row("Kilo", hover=True) != paint_row("Kilo"), "наведение: значок «играть» поверх обложки")
state["playing"] = False
view._eq_tick()
check(not view._eq_timer.isActive(), "пауза: таймер эквалайзера остановлен")
a, b = paint_row("Zeta"), paint_row("Zeta")
check(accent_px(a, cov_r) > 20 and a == b, "пауза: столбики на месте и не двигаются")
state["playing"] = True
win.settings["ui_animations"] = False
check(TrackDelegate.eq_levels(True, now=1.0) == TrackDelegate.eq_levels(True, now=1.7), "анимации выключены — эквалайзер статичный")
view._eq_timer.stop(); paint_row("Zeta")
check(not view._eq_timer.isActive(), "анимации выключены — таймер не запускается")
win.settings["ui_animations"] = True
opened = []
shell.open_album = lambda key, **k: opened.append(key)
view.resize(1000, 400); settle(.1)
vr = view.visualRect(view.model_.index(rows["Lima"][0]))
hit = TrackDelegate.album_hit(vr, rows["Lima"][1])
if hit is not None:
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=hit.center())
check(opened == ["night drive"], "клик по альбому открывает альбом: " + str(opened))

# ───────────────────────────── «Сейчас играет» ─────────────────────────────
check(not shell.now_playing_open(), "экран закрыт по умолчанию")
ev = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(5, 5), QPointF(5, 5), Qt.MouseButton.LeftButton,
                 Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
shell._p_cover_press(ev); settle(.6)
npw = shell._now_playing
check(shell.now_playing_open() and npw.isVisible(), "клик по обложке в плеере открывает экран")
check(npw.geometry() == shell.rect(), "экран занимает всю оболочку")
check(wait(lambda: npw._cur is not None and npw._cur.card is not None), "обложка и фон готовы (из фонового потока)")
check(npw._cur.title == "Zeta" and npw._cur.artist == "Bravo", "название и исполнитель текущего трека")
check(wait(lambda: npw._op >= 1.0) and npw.testAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent) and npw.prog.isVisible(),
      "открыт полностью: непрозрачный, полоска времени на месте")
check(len(npw._nexts) >= 2 and npw._nexts[0][0]["title"] == "Alpha", "«Далее» — следующие треки очереди")
shot = npw.grab().toImage()
check(shot.pixelColor(20, shot.height() - 20) != QColor(10, 10, 13), "фон — из цветов обложки, не чёрная заглушка")


def overlaps(g):
    keys = ["cover", "title", "artist", "times", "play", "prev", "next", "shuffle", "repeat"]
    rs = [g[k] for k in keys] + [g["prog"].toRectF() if hasattr(g["prog"], "toRectF") else g["prog"]]
    bad = [(keys[i] if i < len(keys) else "prog", keys[j] if j < len(keys) else "prog")
           for i in range(len(rs)) for j in range(i + 1, len(rs))
           if rs[i].intersects(rs[j]) and {i, j} != {keys.index("title"), keys.index("artist")}]
    return bad


for size in ((1440, 900), (1000, 680)):
    win.resize(*size); settle(.5)
    g = npw._geom()
    inside = all(npw.rect().toRectF().contains(g[k]) for k in ("cover", "title", "artist", "play", "prev", "next",
                                                              "shuffle", "repeat", "like", "back", "lyrics", "queue"))
    check(npw.geometry() == shell.rect() and inside, f"{size[0]}×{size[1]}: всё помещается в окно")
    check(not overlaps(g), f"{size[0]}×{size[1]}: элементы не налезают друг на друга {overlaps(g)}")
    check(g["cover"].width() >= 200 and len(g["next_rows"]) >= 2, f"{size[0]}×{size[1]}: крупная обложка и «Далее» видны")
if OUT:
    OUT.mkdir(parents=True, exist_ok=True)
    npw.grab().save(str(OUT / "now_playing_1000.png"))
win.resize(1440, 900); settle(.4)

# синхронный текст
lyr = win.lyrics_view
lyr._lines = [{"ms": 0, "text": "первая строка"}, {"ms": 4000, "text": "вторая строка"}, {"ms": 9000, "text": "третья"}]
lyr._has_timings = True
check(wait(lambda: len(npw._ly_tx) == 3) and npw._geom()["lyr"] is not None, "синхронный текст: строки показаны")
check(npw._geom()["next_rows"] and npw._geom()["lyr"].bottom() <= npw._geom()["next_rows"][0].top(),
      "текст — над «Далее», не поверх")
lyr._has_timings = False
check(wait(lambda: not npw._ly_tx) and npw._geom()["lyr"] is None, "без таймкодов текст на экране не показывается")

# смена трека — перетекание, а не скачок
seen = {"prev": False}
orig_assets = npw._on_assets


def spy(job, res):
    orig_assets(job, res)
    seen["prev"] = seen["prev"] or (npw._prev is not None and npw._xf < 1.0)


npw._bus.done.disconnect(); npw._bus.done.connect(spy)
win.current_index = 3
check(wait(lambda: npw._cur.key == win.library[3]["path"]), "смена трека: экран показывает новый трек")
check(seen["prev"], "смена трека: старая обложка перетекает в новую")
check(wait(lambda: npw._xf >= 1.0 and npw._prev is None), "перетекание заканчивается, старый слой освобождён")
check(npw._state_sig[0] is True, "лайк текущего трека виден на экране")

# действия
calls = []
win.toggle_play = lambda: calls.append("play")
win.next_track = lambda: calls.append("next")
win.prev_track = lambda: calls.append("prev")
shell.play_row = lambda row: calls.append(("row", row["i"]))
for name in ("play", "next", "prev"):
    c = npw._geom()[name].center().toPoint()
    QTest.mouseClick(npw, Qt.MouseButton.LeftButton, pos=c)
check(calls == ["play", "next", "prev"], "кнопки управления работают: " + str(calls))
npw._nexts_t = 0.0; settle(.2)
QTest.mouseClick(npw, Qt.MouseButton.LeftButton, pos=npw._geom()["next_rows"][0].center().toPoint())
check(calls[-1] == ("row", 4), "клик по треку в «Далее» включает его: " + str(calls[-1]))
npw.activate("like")
check(not shell.is_liked(win.library[3]), "сердце на экране снимает/ставит лайк")
check(set(npw.TIPS) >= {"back", "lyrics", "queue", "like", "shuffle", "prev", "play", "next", "repeat"},
      "у каждой кнопки экрана есть подсказка")

page_before = shell._cur_page
QTest.keyClick(npw, Qt.Key.Key_Escape)
check(wait(lambda: not npw.isVisible()) and not shell.now_playing_open(), "Esc закрывает экран")
check(shell._cur_page == page_before and shell.stack.currentWidget() is shell.pages[page_before],
      "после закрытия — та же страница, что была")
check(not npw._timer.isActive(), "закрытый экран не тратит кадры")
win._toggle_now_playing(); settle(.2)
check(shell.now_playing_open(), "Ctrl+Shift+N (обработчик) открывает экран")
check(any(sc.key().toString() == "Ctrl+Shift+N" for sc in win.findChildren(QShortcut)), "сочетание Ctrl+Shift+N зарегистрировано")
wait(lambda: npw._op >= 1.0)
QTest.mouseClick(npw, Qt.MouseButton.LeftButton, pos=npw._geom()["back"].center().toPoint())
check(wait(lambda: not npw.isVisible()), "кнопка «свернуть» закрывает экран")
win.settings["ui_animations"] = False
shell.open_now_playing()
check(npw._op == 1.0, "анимации выключены — экран открывается сразу")
shell.close_now_playing()
check(not npw.isVisible(), "анимации выключены — закрывается сразу")
win.settings["ui_animations"] = True
shell.open_now_playing(); settle(.3)
npw.activate("queue"); settle(.4); ui_anim._finish(shell.stack)
check(not npw.isVisible() and shell._cur_page == "queue", "«Очередь» на экране ведёт на страницу очереди")
shell.show_page("collection"); ui_anim._finish(shell.stack); settle(.2)

# ───────────────────────────── «Ещё» в плеере ─────────────────────────────
bar = shell._player_bar
for b in (shell.btn_lyrics, shell.btn_queue, shell.b_vol, shell.b_pmore):
    check(b.isVisible() and bool(b.toolTip()), "справа в плеере видна кнопка с подсказкой: " + b.toolTip()[:24])
no_tip = [b for b in bar.findChildren(QAbstractButton) if b.isVisible() and not b.text().strip() and not b.toolTip()]
check(not no_tip, f"у всех значков плеера есть подсказки (без подсказки: {len(no_tip)})")
icon_only = [b for b in bar.findChildren(QAbstractButton) if b.isVisible() and not b.text().strip()]
check(len(icon_only) <= 10, f"значков в плеере стало меньше: {len(icon_only)}")
items = shell.player_more_items()
keys = [it["key"] for it in items]
check(keys == ["now", "moment", "clip", "cover", "sound", "theme", "settings"], "в «Ещё» — все убранные действия: " + ", ".join(keys))
check(all(it["text"].strip() and it["icon"] and callable(it["fn"]) for it in items), "у каждого пункта значок, подпись и действие")
shell.b_pmore.click(); settle(.3)
pop = shell._more_pop
check(pop is not None and pop.isVisible() and set(pop.buttons) == set(keys), "кнопка «Ещё» открывает окошко с пунктами")
check(all(not b.icon().isNull() and b.text().strip() for b in pop.buttons.values()), "пункты — значок + текст")
if OUT:
    pop.grab().save(str(OUT / "player_more.png"))
done = []
win._toggle_cover_mode = lambda: done.append("cover")
win._toggle_clip_mode = lambda: done.append("clip")
win._winamp_theme_menu = lambda pos: done.append("theme")
shell.toggle_sound_panel = lambda: done.append("sound")
shell.open_now_playing = lambda: done.append("now")
import net_moments
net_moments.show_picker = lambda sh, anchor: done.append("moment")
for key in ("cover", "clip", "theme", "sound", "now", "moment"):
    pop = shell.open_player_more(); settle(.1)
    pop.buttons[key].click(); settle(.2)
    check(done and done[-1] == key and shell._more_pop is None, f"«Ещё» → {key}: действие выполнено, окошко закрыто")
pop = shell.open_player_more(); settle(.1)
pop.buttons["settings"].click(); settle(.4); ui_anim._finish(shell.stack)
check(shell._cur_page == "settings", "«Ещё» → Настройки открывает настройки")
win.resize(1000, 680); settle(.4)
check(shell.btn_lyrics.isVisible() and shell.btn_queue.isVisible() and shell.b_vol.isVisible() and shell.b_pmore.isVisible(),
      "1000×680: текст, очередь, громкость и «Ещё» на месте")

check(not errors, "без исключений: " + (errors[0][-300:] if errors else ""))
print("FAILED" if fails else "ALL OK", len(fails), flush=True)
win._really_quit = True
win.close()
sys.exit(1 if fails else 0)
