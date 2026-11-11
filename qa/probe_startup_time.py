"""Сколько ECHOES запускается: настоящий процесс main.py в чистом профиле (без сети), отметки startup_trace.

  python qa/probe_startup_time.py                 — 3 запуска, лучший и медиана по каждому этапу
  python qa/probe_startup_time.py --runs 5 --tracks 2000
  python qa/probe_startup_time.py --budget 2.0    — код возврата 1, если окно появилось позже бюджета
                                                   (по лучшему из запусков: CI-машины шумные)

Этапы: python (интерпретатор поднялся) → imports (модули загружены) → qapp → window_built → shown →
first_frame (окно нарисовано). Бюджет проверяется по first_frame — «окно за N секунд».
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGES = ["python", "imports", "qapp", "before_window", "window_built", "shown", "first_frame"]


def make_home(tracks: int) -> Path:
    home = Path(tempfile.mkdtemp(prefix="echoes-startup-"))
    data = home / "Echoes"
    data.mkdir()
    (data / "settings.json").write_text(json.dumps({
        "theme": "Echoes Music", "language": "ru", "intro_enabled": False, "onboarded": True,
        "discord_rpc": False, "media_session": False, "close_to_tray": False, "voice_cmd_always": False,
        "auto_tags": False, "github_updates": False, "crash_auto": False}), "utf-8")
    lib = [{"path": str(home / f"music/track-{i}.mp3"), "title": f"Track {i}", "artist": f"Artist {i % 97}",
            "album": f"Album {i % 211}", "duration": 180 + i % 60} for i in range(tracks)]
    (data / "library.json").write_text(json.dumps(lib, ensure_ascii=False), "utf-8")
    return home


def run_once(home: Path, timeout: float) -> dict:
    trace = home / f"trace-{time.time_ns()}.jsonl"
    env = dict(os.environ)
    env.update({
        "USERPROFILE": str(home), "HOME": str(home), "ECHOES_STARTUP_TRACE": str(trace),
        "ECHOES_STARTUP_EXIT": "1", "ECHOES_NO_BOOT_GUARD": "1", "QT_QPA_PLATFORM": env.get("QT_QPA_PLATFORM",
                                                                                          "offscreen"),
        "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": "",
        "ECHOES_AUDIO_BACKEND": "vlc", "PYTHONIOENCODING": "utf-8",
    })
    t0 = time.time()
    p = subprocess.Popen([sys.executable, str(ROOT / "app" / "main.py")], cwd=str(ROOT / "app"), env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        out, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        out, _ = p.communicate()
    marks = {}
    if trace.exists():
        for line in trace.read_text("utf-8").splitlines():
            try:
                d = json.loads(line)
                marks.setdefault(d["m"], d["t"] - t0)
            except Exception:                              # noqa: BLE001
                pass
    marks["_log"] = out.decode("utf-8", "replace")[-3000:]
    return marks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--tracks", type=int, default=500)
    ap.add_argument("--budget", type=float, default=0.0, help="секунды до первого кадра (0 — не проверять)")
    ap.add_argument("--timeout", type=float, default=90)
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                      # noqa: BLE001
        pass
    home = make_home(a.tracks)
    runs = []
    for i in range(a.runs):
        r = run_once(home, a.timeout)
        runs.append(r)
        ok = "first_frame" in r
        print(f"запуск {i + 1}: " + ("  ".join(f"{s}={r[s]:.2f}" for s in STAGES if s in r) if ok
                                     else "окно не появилось"), flush=True)
        if not ok:
            print(r["_log"])
    good = [r for r in runs if "first_frame" in r]
    if not good:
        print("::error::ECHOES не показал окно ни в одном запуске")
        return 1
    print("\nэтап              лучший  медиана")
    prev_b = prev_m = 0.0
    for s in STAGES:
        vals = [r[s] for r in good if s in r]
        if not vals:
            continue
        b, m = min(vals), statistics.median(vals)
        print(f"{s:16} {b:7.2f}  {m:7.2f}   (+{b - prev_b:.2f} / +{m - prev_m:.2f})")
        prev_b, prev_m = b, m
    best = min(r["first_frame"] for r in good)
    if a.budget:
        if best > a.budget:
            print(f"::error::окно появилось за {best:.2f} с — дольше бюджета {a.budget:.1f} с")
            return 1
        print(f"окно за {best:.2f} с — в бюджете {a.budget:.1f} с")
    return 0


if __name__ == "__main__":
    sys.exit(main())
