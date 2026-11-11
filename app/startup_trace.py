"""Отметки времени запуска: сколько прошло до импорта, создания окна, показа и первого кадра.

Включается переменной ECHOES_STARTUP_TRACE=<файл>: каждая отметка — строка JSON {"m": имя, "t": time.time()}.
ECHOES_STARTUP_EXIT=1 — закрыть плеер сразу после первого кадра (замер в CI: qa/probe_startup_time.py).
Без переменной модуль ничего не делает и ничего не пишет.
"""
from __future__ import annotations

import json
import os
import time

_PATH = os.environ.get("ECHOES_STARTUP_TRACE", "")


def on() -> bool:
    return bool(_PATH)


_PROF = os.environ.get("ECHOES_STARTUP_PROFILE", "")       # профиль сборки окна (только поток окна)


def build(factory):
    """factory() — как есть; с ECHOES_STARTUP_PROFILE — под profile (точный, только этот поток)."""
    if not (_PATH and _PROF):
        return factory()
    import profile
    pr = profile.Profile()
    try:
        return pr.runcall(factory)
    finally:
        pr.dump_stats(_PROF)


def mark(name: str):
    if not _PATH:
        return
    try:
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"m": name, "t": time.time()}) + "\n")
    except OSError:
        pass


def after_show(win):
    """Первый кадр: окно показано и цикл событий его нарисовал."""
    if not _PATH:
        return
    from PyQt6.QtCore import QTimer

    def painted():
        mark("first_frame")
        if os.environ.get("ECHOES_STARTUP_EXIT") == "1":
            QTimer.singleShot(int(float(os.environ.get("ECHOES_STARTUP_LINGER", "0.3")) * 1000), win.close)
            QTimer.singleShot(int(float(os.environ.get("ECHOES_STARTUP_LINGER", "0.3")) * 1000) + 4000,
                              lambda: os._exit(0))
    QTimer.singleShot(0, painted)
