"""«Сцена» в настоящей оболочке: пункт в «Ещё» нижнего плеера, открытие, уход при переходе на страницу и при
открытии «Сейчас играет», размер вслед за окном.

python qa/test_scene_shell.py
"""
import sys
from pathlib import Path

source = Path(__file__).with_name('ui_smoke.py').read_text('utf-8')
exec(compile(source.split('win = None')[0], str(Path(__file__).with_name('ui_smoke.py')), 'exec'))
import json as _pj  # noqa: E402  — прежний вид Echoes Music (Phantom теперь по умолчанию)
_ps = _pj.loads((data / 'settings.json').read_text('utf-8')); _ps['ya_layout'] = 'new'
(data / 'settings.json').write_text(_pj.dumps(_ps), encoding='utf-8')
import main

main.WindowsMediaKeyFilter.register = lambda self: None
fails = []


def check(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg, flush=True)
    if not cond:
        fails.append(msg)


win = main.MainWindow()
win.resize(1280, 800)
win.show(); settle(.5)
shell = win._ya
items = {it["key"]: it for it in shell.player_more_items()}
check("scene" in items and items["scene"]["text"] == "Сцена", "в «Ещё» есть пункт «Сцена»")
items["scene"]["fn"](); settle(.6)
sc = shell.__dict__.get("_scene")
check(sc is not None and sc.is_open() and sc.size() == shell.size(), "«Сцена» открыта во всё окно оболочки")
check(not sc.grab().isNull(), "кадр без трека и текста рисуется")
win.resize(1100, 700); settle(.3)
check(sc.size() == shell.size(), "размер идёт за окном")
shell.open_now_playing(); settle(.3)
check(not sc.is_open() and shell.now_playing_open(), "«Сейчас играет» закрывает «Сцену»")
shell.open_scene(); settle(.6)
check(sc.is_open() and not shell.now_playing_open(), "«Сцена» закрывает «Сейчас играет»")
shell.show_page("settings"); settle(.3)
check(not sc.is_open(), "переход на страницу закрывает «Сцену»")
shell.open_scene(); settle(.5)
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
QTest.keyClick(sc, Qt.Key.Key_Escape); settle(.6)
check(not sc.isVisible(), "Esc закрывает")
print("FAILED" if fails else "ALL OK", len(fails), flush=True)
win.close()
sys.exit(1 if fails else 0)
