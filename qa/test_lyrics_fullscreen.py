"""Текст песни на весь экран — тем же экраном, что у обложки (now_playing): кнопка текста в нижнем плеере
открывает его сразу в режиме «Текст», при открытом «Сейчас играет» — перестраивает экран, повторно — закрывает;
раскладка между режимами перетекает; кнопка «…» ведёт на прежнюю страницу с поиском и синхронизацией.

python qa/test_lyrics_fullscreen.py
"""
import os
import sys
from pathlib import Path

source = Path(__file__).with_name("ui_smoke.py").read_text("utf-8")
exec(compile(source.split("win = None")[0], str(Path(__file__).with_name("ui_smoke.py")), "exec"))
import json as _json  # noqa: E402
_st = _json.loads((data / "settings.json").read_text("utf-8"))   # свой заголовок окна — как у пользователя
_st["custom_titlebar"] = True
(data / "settings.json").write_text(_json.dumps(_st), encoding="utf-8")
import main  # noqa: E402

main.WindowsMediaKeyFilter.register = lambda self: None
fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


win = main.MainWindow()
win.resize(1500, 900)
win.show()
settle(1.0)
shell = win._ya
win.library = [{"path": str(audit_home / f"{i}.wav"), "title": f"Трек {i}", "artist": "Артист", "duration": 200}
               for i in range(5)]
win.current_index = 0
lv = getattr(win, "lyrics_view", None)
if lv is not None:
    lv._lines = [{"ms": 1000 + 4000 * k, "text": f"Строка {k}"} for k in range(8)]
    lv._has_timings = True

shell.toggle_lyrics()
settle(1.2)
np_ = shell.__dict__.get("_now_playing")
check(np_ is not None and shell.now_playing_open(), "кнопка текста открыла экран на всё окно")
check(np_ is not None and np_.mode() == "lyrics", "экран открыт сразу в режиме «Текст»")
check(shell.btn_lyrics.isChecked(), "кнопка текста в нижнем плеере подсвечена")
g = np_._geom()
check(g.get("lm") == 1.0 and g["lyr"] is not None and not g["next_rows"], "вся правая колонка — текст, «Далее» убран")
check(g["lyr"].height() > np_.height() * 0.6, f"текст занимает почти всю высоту ({g['lyr'].height():.0f} из {np_.height()})")
check(np_.geometry() == shell.rect(), "экран закрывает всю оболочку")

np_.activate("lyrics")                                       # кнопка вверху экрана — назад к «Сейчас играет»
settle(0.15)
mid = np_._geom().get("lm", 0)
check(0.0 < mid < 1.0, f"раскладка перетекает, а не прыгает (на середине: {mid:.2f})")
settle(1.0)
check(np_.mode() == "cover" and np_._geom().get("lm") == 0.0, "вернулись к «Сейчас играет»")
check(not shell.btn_lyrics.isChecked(), "кнопка текста погасла")

shell.toggle_lyrics()                                        # из «Сейчас играет» — снова текст
settle(1.0)
check(np_.mode() == "lyrics", "кнопка текста при открытом «Сейчас играет» включает «Текст»")
shell.toggle_lyrics()                                        # повторно — закрыть
settle(1.0)
check(not shell.now_playing_open() and not shell.btn_lyrics.isChecked(), "повторное нажатие закрывает экран")

shell.show_page("lyrics")                                    # старая страница текста — теперь тоже этот экран
settle(1.2)
check(shell.lyrics_full_open() and shell._cur_page != "lyrics", "переход на «Текст» открывает экран на всё окно, а не старую страницу")
box = np_._lyr_box
check(box is not None and box.isVisible() and box.parentWidget() is np_, "кнопки и панель текста перенесены на экран")
check(shell.l_panel.isVisible() and box.isAncestorOf(shell.l_panel), "панель текста видна на экране «Текст»")
check(not shell.l_top.isVisible(), "кнопки с подписями спрятаны — вместо них значки в шапке")
tools = np_._tools(np_._geom())
names = [t[0] for t in tools]
check("t_style" in names and "t_find" in names, f"значки «Язык и оформление» и «Найти текст» в шапке ({names})")
check(all(r.right() <= np_._geom()["lyrics"].left() for _n, r, _i, _a in tools), "значки — слева от кнопок «текст» и «очередь»")
check(("t_ai" in names) == (not shell.l_ai.isHidden()), "значок ИИ — только когда кнопка ИИ нужна")
img = np_.grab().toImage()                                   # координаты значков — в координатах экрана
for n_, r_, _i, _a in tools:
    cc = r_.center().toPoint()
    br = max(img.pixelColor(cc.x() + dx, cc.y() + dy).lightness() for dx in range(-8, 9) for dy in range(-8, 9))
    check(br > 170, f"значок {n_} нарисован (светлее фона: {br})")
hits = []
shell.l_find.clicked.connect(lambda *_: hits.append("find"))
shell.l_find.clicked.disconnect(win._manual_lyrics_search)   # без настоящего окна поиска
r_find = next(r for n, r, _i, _a in tools if n == "t_find")
check(np_._hit(r_find.center()) == "t_find", "значок «Найти текст» нажимается")
np_.activate("t_find")
check(hits == ["find"], "значок делает то же, что кнопка «Найти текст вручную»")
check(np_._tool_tip("t_style").startswith("Язык и оформление"), "у значка подсказка с назначением")
gb = box.geometry()
check(gb.left() > np_.width() * 0.3 and gb.height() > np_.height() * 0.6, f"панель текста — правая колонка во всю высоту ({gb})")
check(shell.l_panel._backdrop is None, "панель текста прозрачная — под ней живой фон экрана")
img = np_.grab().toImage()
c = img.pixelColor(gb.center().x(), gb.center().y())
check(max(c.red(), c.green(), c.blue()) > 24, f"на месте панели текста — фон, а не чёрный прямоугольник ({c.name()})")
check(shell.l_panel.updatesEnabled() and box.updatesEnabled(), "панель перерисовывается")
tb = win.titlebar
check(tb._now_playing_bg() is not None, "заголовок окна рисует под собой фон экрана")
ti = tb.grab().toImage()
x_empty = tb.btn_min.geometry().left() - 30                  # участок без надписей, перед кнопками окна
ct = ti.pixelColor(x_empty, tb.height() // 2)
cn = np_.grab().toImage().pixelColor(x_empty, 2)
check(max(ct.red(), ct.green(), ct.blue()) > 24, f"заголовок окна не чёрный, а в цвет фона ({ct.name()})")
check(max(abs(ct.red() - cn.red()), abs(ct.green() - cn.green()), abs(ct.blue() - cn.blue())) < 28,
      f"на стыке заголовок и экран одного цвета ({ct.name()} и {cn.name()})")
check(not hasattr(np_, "_paint_plain") and "tools" not in np_.TIPS, "кнопки «…» и своего показа текста больше нет")
np_.activate("lyrics")
settle(1.0)
check(np_.mode() == "cover" and not box.isVisible(), "в «Сейчас играет» панель текста уходит")
check(np_._hit(r_find.center()) != "t_find", "в «Сейчас играет» значков-кнопок текста нет")
np_.activate("lyrics")
settle(1.0)
check(box.isVisible(), "и возвращается в «Тексте»")
np_.close_mode(instant=True)
settle(0.3)
check(not box.isVisible(), "после закрытия панель текста спрятана")

shell.toggle_lyrics()                                        # открыть «Текст» и закрыть…
settle(1.0)
np_.close_mode(instant=True)
settle(0.2)
shell.open_now_playing()                                     # …клик по обложке — всегда «Сейчас играет»
settle(1.0)
check(np_.mode() == "cover", "клик по обложке открывает «Сейчас играет», а не последний режим")
np_.close_mode(instant=True)

print("ALL OK" if not fails else f"{len(fails)} FAILED", flush=True)
os._exit(1 if fails else 0)
