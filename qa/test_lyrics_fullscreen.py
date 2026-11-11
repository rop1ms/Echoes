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
for name in ("l_appearance", "l_find", "l_panel"):
    w = getattr(shell, name)
    check(w.isVisible() and box.isAncestorOf(w), f"{name} виден на экране «Текст»")
check(not shell.l_collapse.isVisible(), "вторая стрелка «свернуть» спрятана — есть стрелка экрана")
check(shell.l_ai.parentWidget() is shell.l_top and box.isAncestorOf(shell.l_ai), "«Синхронизировать с ИИ» — в той же панели кнопок")
gb = box.geometry()
check(gb.left() > np_.width() * 0.3 and gb.height() > np_.height() * 0.6, f"панель текста — правая колонка во всю высоту ({gb})")
check(shell.l_panel._backdrop is None, "панель текста прозрачная — под ней живой фон экрана")
img = np_.grab().toImage()
c = img.pixelColor(gb.center().x(), gb.center().y())
check(max(c.red(), c.green(), c.blue()) > 24, f"на месте панели текста — фон, а не чёрный прямоугольник ({c.name()})")
img = win.grab().toImage()
fc = shell.l_find.mapTo(win, shell.l_find.rect().center())
c2 = img.pixelColor(fc.x(), fc.y())
check(min(c2.red(), c2.green(), c2.blue()) > 150, f"кнопка «Найти текст вручную» действительно нарисована ({c2.name()})")
check(shell.l_panel.updatesEnabled() and box.updatesEnabled(), "панель и кнопки перерисовываются")
check(not hasattr(np_, "_paint_plain") and "tools" not in np_.TIPS, "кнопки «…» и своего показа текста больше нет")
np_.activate("lyrics")
settle(1.0)
check(np_.mode() == "cover" and not box.isVisible(), "в «Сейчас играет» панель текста уходит")
np_.activate("lyrics")
settle(1.0)
check(box.isVisible(), "и возвращается в «Тексте»")
np_.close_mode(instant=True)
settle(0.3)
check(np_._cap is None and not box.isVisible(), "после закрытия заголовок окна снова системный, панель спрятана")

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
