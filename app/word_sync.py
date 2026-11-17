"""Пословная синхронизация текста для «жидкой» заливки (белым по буквам) — сразу, без долгого ИИ.

1) estimate(lines) — мгновенно, без сети и звука. Синхронизированный текст знает только начало каждой
   строки; раньше заливка растягивалась на весь промежуток до следующей строки (вместе с паузой) и
   отставала от голоса. Теперь: слоги каждого слова (гласные; иероглифы и кана — по слогу) и скорость
   пения ЭТОЙ песни — её узнаём по самым плотным строкам (там строка ≈ время пения). Строка поётся
   столько, сколько нужно её слогам, слова — пропорционально своим слогам, пауза после строки не
   растягивает заливку.
2) refine(...) — через доли секунды, по звуку трека (ffmpeg → 11 кГц моно → огибающая «новых звуков»
   в полосе голоса 250–3500 Гц). Начало каждого слова подтягивается к ближайшему всплеску рядом с
   оценкой (не дальше ±40 % длины слова), конец строки — к месту, где голос стихает. Если в треке
   нет явных всплесков (сплошной звук), остаётся оценка — она тоже ровная.

Слова — [(начало_мс, слово, конец_мс)] на строку (None — строка без меток / пустая).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from bisect import bisect_right
from pathlib import Path

import numpy as np

_VOW = re.compile(r"[aeiouyæøåäöüéèêáàíìóòúùаеёиоуыэюяіїє]+", re.I)
_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")
SR = 11025
HOP = 110                                                      # 10 мс
FFT = 512
FRAMES_PER_BATCH = 2048
_ENV_CACHE: dict = {}


def syllables(word: str) -> int:
    w = word.lower()
    n = len(_VOW.findall(w)) + len(_CJK.findall(w))
    if n == 0 and re.search(r"[a-zа-я0-9]", w):
        n = 1
    return max(1, n) if w.strip() else 0


def _spans(lines):
    """[(i, start, next_start)] для строк с меткой времени."""
    timed = [(i, ln["ms"]) for i, ln in enumerate(lines) if ln.get("ms", -1) >= 0 and (ln.get("text") or "").strip()]
    out = []
    all_ms = sorted(ln["ms"] for ln in lines if ln.get("ms", -1) >= 0)
    for i, ms in timed:
        nxt = bisect_right(all_ms, ms)
        out.append((i, ms, all_ms[nxt] if nxt < len(all_ms) else ms + 6000))
    return out


def song_rate(lines) -> float:
    """Скорость пения песни (слогов в секунду) по плотным строкам."""
    rates = []
    for i, a, b in _spans(lines):
        n = sum(syllables(w) for w in (lines[i].get("text") or "").split())
        dur = (b - a) / 1000.0
        if n >= 3 and 0.6 < dur < 12:
            rates.append(n / dur)
    if not rates:
        return 4.0
    rates.sort()
    r = rates[int(len(rates) * 0.7)] if len(rates) > 2 else max(rates)
    return float(min(9.5, max(2.2, r)))


def estimate(lines) -> list:
    """Тайминги слов по слогам — для каждой строки (или None)."""
    rate = song_rate(lines)
    out = [None] * len(lines)
    for i, a, b in _spans(lines):
        words = (lines[i].get("text") or "").split(" ")
        if not any(w.strip() for w in words):
            continue
        weights = [syllables(w) + 0.35 for w in words]       # + согласные/переходы между словами
        n_syl = sum(syllables(w) for w in words)
        span = max(300.0, b - a - 90.0)
        sing = min(span * 0.96, max(260.0 * len(words) ** 0.5, n_syl / rate * 1000.0 * 1.06))
        tot = sum(weights) or 1.0
        t, res = float(a), []
        for w, k in zip(words, weights):
            d = sing * k / tot
            res.append((int(t), w, int(t + d)))
            t += d
        out[i] = res
    return out


# ── звук ── #

def _ffmpeg():
    p = shutil.which("ffmpeg")
    if p:
        return p
    for d in (Path(__file__).resolve().parent.parent / "ffmpeg", Path(__file__).resolve().parent / "ffmpeg"):
        if (d / "ffmpeg.exe").exists():
            return str(d / "ffmpeg.exe")
    return None


def _analyze_pcm(sound):
    samples = sound.tell() // 2
    if samples < FFT * 4:
        return None
    n = (samples - FFT) // HOP
    flux = np.empty(n)
    loud = np.empty(n)
    win = np.hanning(FFT).astype(np.float32)
    freq = np.fft.rfftfreq(FFT, 1.0 / SR)
    band = (freq > 250) & (freq < 3500)
    previous = None
    for start in range(0, n, FRAMES_PER_BATCH):
        end = min(start + FRAMES_PER_BATCH, n)
        sound.seek(start * HOP * 2)
        pcm = np.fromfile(sound, dtype="<i2", count=(end - start - 1) * HOP + FFT)
        x = pcm.astype(np.float32) / 32768.0
        frames = np.lib.stride_tricks.sliding_window_view(x, FFT)[::HOP]
        mag = np.log1p(np.abs(np.fft.rfft(frames * win, axis=1)[:, band]) * 40.0)
        flux[start:end] = np.maximum(0.0, np.diff(mag, axis=0,
                                                prepend=mag[:1] if previous is None else previous)).sum(axis=1)
        loud[start:end] = mag.mean(axis=1)
        previous = mag[-1:].copy()
    flux = np.convolve(flux, np.ones(3) / 3.0, mode="same")
    loud = np.convolve(loud, np.ones(9) / 9.0, mode="same")
    return flux / (np.percentile(flux, 95) + 1e-9), loud


def envelope(path: str):
    """(поток «новых звуков» голоса, громкость голоса) по 10 мс — или None. Кэш на 4 трека."""
    if not path or not os.path.exists(path):
        return None
    key = (path, os.path.getmtime(path))
    hit = _ENV_CACHE.get(key)
    if hit is not None:
        return hit
    exe = _ffmpeg()
    if not exe:
        return None
    try:
        # Keep decoded audio and FFT matrices off the Python heap for long recordings.
        with tempfile.TemporaryFile() as sound:
            subprocess.run([exe, "-nostdin", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(SR),
                            "-f", "s16le", "-"], stdout=sound, stderr=subprocess.DEVNULL, check=True, timeout=60,
                           creationflags=0x08000000 if os.name == "nt" else 0)
            sound.seek(0, os.SEEK_END)
            res = _analyze_pcm(sound)
    except (OSError, subprocess.SubprocessError):
        return None
    if res is None:
        return None
    if len(_ENV_CACHE) > 3:
        _ENV_CACHE.pop(next(iter(_ENV_CACHE)))
    _ENV_CACHE[key] = res
    return res


def refine(lines, est, env) -> list:
    """Уточнить оценку по звуку: начала слов — к всплескам голоса, конец строки — где голос стихает."""
    if env is None:
        return est
    flux, loud = env
    nf = len(flux)
    fr = lambda ms: int(ms / 10)                               # noqa: E731
    out = list(est)
    spans = {i: (a, b) for i, a, b in _spans(lines)}
    for i, words in enumerate(est):
        if not words or i not in spans:
            continue
        a, b = spans[i]
        new = []
        prev_end = a
        for k, (t0, w, t1) in enumerate(words):
            d = max(60, t1 - t0)
            if k == 0:
                lo, hi = t0 - 120, t0 + min(250, d * 0.5)      # первое слово — около метки строки
            else:
                lo, hi = t0 - d * 0.4, t0 + d * 0.4
            lo, hi = max(prev_end - 20, lo), min(b - 60, hi)
            s = t0
            if hi > lo and fr(hi) < nf:
                seg = flux[fr(lo):fr(hi) + 1]
                if len(seg) and seg.max() > 0.35 and seg.max() > 1.8 * (np.median(seg) + 1e-6):
                    s = lo + int(np.argmax(seg)) * 10 - 20     # чуть раньше пика — заливка не опаздывает
            s = max(prev_end, s)
            new.append([int(s), w, 0])
            prev_end = s + 50
        for k in range(len(new) - 1):
            new[k][2] = max(new[k][0] + 50, new[k + 1][0])
        last_s = new[-1][0]
        est_end = words[-1][2]
        end = est_end
        lo, hi = fr(last_s + 120), fr(min(b - 40, max(est_end + 600, last_s + 400)))
        if 0 <= lo < hi < nf:                                  # голос стих — там и конец строки
            seg = loud[lo:hi]
            ref = loud[fr(a):fr(last_s) + 1].mean() if fr(last_s) > fr(a) else seg.max()
            quiet = np.nonzero(seg < ref * 0.55)[0]
            if len(quiet):
                end = (lo + int(quiet[0])) * 10
        new[-1][2] = int(max(last_s + 120, min(end, b - 40)))
        out[i] = [tuple(x) for x in new]
    return out
