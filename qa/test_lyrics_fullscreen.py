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

shell.toggle_lyrics()
settle(1.0)
np_.activate("tools")                                        # «…» — прежняя страница: поиск, ИИ, язык
settle(1.0)
check(not shell.now_playing_open() and shell._cur_page == "lyrics", "«…» открывает страницу поиска и синхронизации")
shell.show_page("collection")
settle(0.6)

if lv is not None:                                           # текст без таймкодов — показывается целиком
    lv._has_timings = False
try:
    win.lyrics_box.setPlainText("Куплет без таймкодов\nВторая строка\n\nПрипев")
except Exception:                                            # noqa: BLE001
    pass
shell.toggle_lyrics()
settle(1.0)
check(np_._plain_text()[:2] == ["Куплет без таймкодов", "Вторая строка"], "текст без таймкодов берётся целиком")
img = win.grab().toImage()
check(not img.isNull(), "экран с текстом без таймкодов рисуется")
np_.close_mode(instant=True)
settle(0.3)
check(np_._cap is None, "после закрытия заголовок окна снова системного цвета")

print("ALL OK" if not fails else f"{len(fails)} FAILED", flush=True)
os._exit(1 if fails else 0)
