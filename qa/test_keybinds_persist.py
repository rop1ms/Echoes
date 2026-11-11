"""Свои горячие клавиши переживают перезапуск: меняем сочетание в карточке «Горячие клавиши», закрываем
плеер, открываем заново на тех же данных — сочетание то же, и действует.

python qa/test_keybinds_persist.py            (сам запускает два раза: «изменить» и «проверить»)
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
if len(sys.argv) < 3:                                       # ведущий процесс: два запуска плеера на одной папке данных
    home = tempfile.mkdtemp(prefix="echoes-keys-")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    rc = 0
    for phase in ("set", "check"):
        p = subprocess.run([sys.executable, str(HERE), phase, home], env=env, capture_output=True, timeout=600)
        out = p.stdout.decode("utf-8", "replace")
        print(out.strip())
        if p.returncode:
            print(p.stderr.decode("utf-8", "replace")[-3000:])
            rc = 1
            break
    sys.exit(rc)

PHASE, HOME = sys.argv[1], sys.argv[2]
source = HERE.with_name("ui_smoke.py").read_text("utf-8")
exec(compile(source.split("win = None")[0], str(HERE.with_name("ui_smoke.py")), "exec"))
import shutil                                               # noqa: E402
SHARED = Path(HOME) / "data"                                # ui_smoke даёт каждому запуску свою папку данных —
if PHASE == "set" and os.environ.get("ECHOES_QA_SETTINGS"):   # проверить на копии настоящих настроек
    shutil.copy2(os.environ["ECHOES_QA_SETTINGS"], data / "settings.json")
if PHASE == "check":                                        # второй запуск получает данные первого
    for f in SHARED.rglob("*"):
        if f.is_file():
            dst = data / f.relative_to(SHARED)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)
import main                                                 # noqa: E402
import player_prefs                                         # noqa: E402
from PyQt6.QtGui import QKeySequence                        # noqa: E402
from PyQt6.QtWidgets import QApplication, QKeySequenceEdit  # noqa: E402

main.WindowsMediaKeyFilter.register = lambda self: None
fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + f"[{PHASE}] " + msg, flush=True)
    if not cond:
        fails.append(msg)


win = main.MainWindow()
win.resize(1400, 900)
win.show()
settle(1.0)
LOCAL = ("next", "Ctrl+Alt+Right")
GLOBAL = ("like", "Ctrl+Shift+F9")
QUIET = ("mute", "Ctrl+Alt+F8")

if PHASE == "set":
    shell = getattr(win, "_ya", None)
    if shell is not None:
        shell.show_page("settings")
        settle(0.5)
    card = getattr(shell, "_keybinds_card", None) or player_prefs.keybinds_card(win)   # та самая карточка из настроек
    check(getattr(shell, "_keybinds_card", None) is not None, "карточка «Горячие клавиши» есть в настройках")
    edits = card.findChildren(QKeySequenceEdit)
    keys = [k for k, _t, _d in player_prefs.ACTIONS]
    # порядок полей: для каждого действия — «в ECHOES», затем «везде» (кроме LOCAL_ONLY)
    order = []
    for k in keys:
        order.append(("local", k))
        if k not in player_prefs.LOCAL_ONLY:
            order.append(("global", k))
    by = dict(zip(order, edits))
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    M = Qt.KeyboardModifier

    def press(ed, key, mods):                               # как человек: щёлкнуть в поле и нажать сочетание
        ed.setFocus()
        QTest.mouseClick(ed, Qt.MouseButton.LeftButton)
        settle(0.1)
        QTest.keyClick(ed, key, mods)
        settle(1.4)                                         # запись сочетания кончается сама (около 1 с)
    press(by[("local", LOCAL[0])], Qt.Key.Key_Right, M.ControlModifier | M.AltModifier)
    press(by[("global", GLOBAL[0])], Qt.Key.Key_F9, M.ControlModifier | M.ShiftModifier)
    by[("local", QUIET[0])].setKeySequence(QKeySequence(QUIET[1]))   # без «редактирование закончено»
    settle(0.8)
    check(player_prefs.binds(win)[QUIET[0]] == QUIET[1], "сочетание сохранено и без сигнала «редактирование закончено»")
    check(player_prefs.binds(win)[LOCAL[0]] == LOCAL[1], "сочетание в окне изменилось в памяти")
    check(player_prefs.global_binds(win).get(GLOBAL[0]) == GLOBAL[1], "глобальное сочетание изменилось в памяти")
    settle(1.5)                                             # дать отработать всему, что пишет настройки в первые секунды
    win.close()
    settle(0.5)
    import atomic_json
    atomic_json.flush()
    shutil.copytree(data, SHARED, dirs_exist_ok=True)
    QApplication.instance().quit()
else:
    b, gb = player_prefs.binds(win), player_prefs.global_binds(win)
    check(b.get(LOCAL[0]) == LOCAL[1], f"после перезапуска «{LOCAL[0]}» = {LOCAL[1]} (сейчас {b.get(LOCAL[0])!r})")
    check(gb.get(GLOBAL[0]) == GLOBAL[1], f"после перезапуска глобальное «{GLOBAL[0]}» = {GLOBAL[1]} (сейчас {gb.get(GLOBAL[0])!r})")
    check(b.get(QUIET[0]) == QUIET[1], f"после перезапуска «{QUIET[0]}» = {QUIET[1]} (сейчас {b.get(QUIET[0])!r})")
    check("keybinds_global" not in win.settings, "старый флаг «работают везде» убран из настроек")
    keys = win.__dict__.get("_prefs", {}).get("keys") if isinstance(win.__dict__.get("_prefs"), dict) else None
    if keys is not None:
        seqs = {sc.key().toString() for sc in keys.shortcuts if sc.isEnabled()}
        check(LOCAL[1] in seqs, "сочетание после перезапуска действует в окне")
    win.close()

import atomic_json                                          # noqa: E402
atomic_json.flush()
print("ALL OK" if not fails else f"{len(fails)} FAILED", flush=True)
os._exit(1 if fails else 0)
