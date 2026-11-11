"""Снимки режимов «Сейчас играет» и «Текст песни» на весь экран (для проверки вида и шапки окна).

python qa/shot_fullscreen_modes.py <папка-для-картинок>
"""
import sys
from pathlib import Path

source = Path(__file__).with_name("ui_smoke.py").read_text("utf-8")
exec(compile(source.split("win = None")[0], str(Path(__file__).with_name("ui_smoke.py")), "exec"))
import main  # noqa: E402
from PyQt6.QtGui import QColor, QImage, QPainter, QLinearGradient  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
OUT.mkdir(parents=True, exist_ok=True)
main.WindowsMediaKeyFilter.register = lambda self: None

cov = audit_home / "cover.png"                              # обложка с яркими цветами — чтобы фон было видно
img = QImage(400, 400, QImage.Format.Format_RGB32)
p = QPainter(img)
g = QLinearGradient(0, 0, 400, 400)
g.setColorAt(0, QColor("#ff4fa3"))
g.setColorAt(1, QColor("#3b6bff"))
p.fillRect(img.rect(), g)
p.end()
img.save(str(cov))
lrc = "[00:01.00]Первая строка песни\n[00:05.00]Вторая строка, она длиннее первой\n[00:09.00]Третья строка\n[00:13.00]Четвёртая\n[00:17.00]Пятая строка текста"

win = main.MainWindow()
win.resize(1500, 900)
win.show()
settle(1.0)
shell = win._ya
win.library = [{"path": str(audit_home / f"{i}.wav"), "title": f"Ночной город {i}", "artist": "Lunar Fields",
                "album": "Echoes Sessions", "duration": 200, "cover": str(cov), "lyrics": lrc} for i in range(6)]
try:
    win.queue_context = "library"
except Exception:                                           # noqa: BLE001
    pass
win.current_index = 0
try:
    win._update_now_playing_ui() if hasattr(win, "_update_now_playing_ui") else None
except Exception as e:                                      # noqa: BLE001
    print("np ui", e)
try:
    shell.on_track_changed() if hasattr(shell, "on_track_changed") else None
except Exception as e:                                      # noqa: BLE001
    print("track changed", e)
try:
    win.lyrics_box.setPlainText(lrc)
except Exception:                                           # noqa: BLE001
    pass
settle(0.8)
win.grab().save(str(OUT / "0_normal.png"))
shell.show_page("lyrics")
settle(1.2)
win.grab().save(str(OUT / "1_lyrics.png"))
shell.show_page("collection")
settle(0.8)
lv = getattr(win, "lyrics_view", None)
if lv is not None:                                          # синхронный текст, как после загрузки трека
    lv._lines = [{"ms": 1000 + 4000 * k, "text": t} for k, t in enumerate(
        ["Первая строка песни", "Вторая строка, она длиннее первой и переносится", "Третья строка",
         "Четвёртая", "Пятая строка текста", "Шестая", "Седьмая строка", "Восьмая"])]
    lv._has_timings = True
shell.open_now_playing()
settle(1.2)
win.grab().save(str(OUT / "2_now.png"))
shell.toggle_lyrics()                                       # кнопка текста при открытом «Сейчас играет»
settle(0.25)
win.grab().save(str(OUT / "3_morph.png"))
settle(1.2)
win.grab().save(str(OUT / "4_lyrics_full.png"))
print("mode", shell._now_playing.mode(), "btn", shell.btn_lyrics.isChecked(), flush=True)
shell.toggle_lyrics()                                       # повторное нажатие — закрыть
settle(1.0)
print("closed", not shell.now_playing_open(), "btn", shell.btn_lyrics.isChecked(), flush=True)
if lv is not None:
    lv._has_timings = False
shell.toggle_lyrics()                                       # из закрытого — сразу текст (без таймкодов)
settle(1.4)
win.grab().save(str(OUT / "5_plain.png"))
print("mode2", shell._now_playing.mode(), flush=True)
print("shots ok", OUT)
import os  # noqa: E402
os._exit(0)
