"""Пословная синхронизация текста для «жидкой» заливки (белым по буквам) — сразу, без ИИ и без сети.

1) estimate(lines) — мгновенно, без звука. Синхронизированный текст знает только начало каждой строки.
   Слоги каждого слова (гласные; иероглифы и кана — по слогу) и скорость пения ЭТОЙ песни (по самым плотным
   строкам): строка поётся столько, сколько нужно её слогам, слова — пропорционально слогам.
2) refine(lines, est, envelope(path)) — по звуку трека, за доли секунды:
   * ffmpeg отдаёт стерео 11 кГц ПОТОКОМ — в памяти никогда нет ни всего трека, ни всей спектрограммы
     (раньше — ~235 МБ на трек); остаются два коротких ряда по 10 мс (~0.2 МБ на 4-минутный трек);
   * голос обычно в центре стереокартины: из середины (L+R) вычитается боковая часть (L-R) — бас, гитары и
     реверберация по краям мешают меньше; ВЧ-удары (хэты, тарелки) вычитаются из потока «новых звуков»;
   * «активность голоса» по 10 мс: громкость центра в полосе голоса и её быстрые колебания (речь и пение
     модулированы, ровная подложка — нет);
   * раскладка: слова делят строку по «пропетому времени» — там, где голос звучит, время идёт быстрее,
     в паузах и проигрышах почти стоит; поэтому заливка не ползёт по тишине и не отстаёт после вдоха.
     Длина пения строки — по слогам и скорости песни, а не до следующей метки;
   * начало слова подтягивается к ближайшему всплеску голоса, но не дальше ~половины длины слова.
   Замер против пословной разметки 15 треков (350 строк, 2095 слов): медиана ошибки начала слова 140 мс
   (было 160), средняя 201 мс (было 243), точнее 0.2 с — 66 % слов (было 58 %).

Слова — [(начало_мс, слово, конец_мс)] на строку (None — строка без меток / пустая).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np

_VOW = re.compile(r"[aeiouyæøåäöüéèêáàíìóòúùаеёиоуыэюяіїє]+", re.I)
_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")
SR = 11025
HOP = 110                                                      # 10 мс
FFT = 512
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
        nxt = next((m for m in all_ms if m > ms), None)
        out.append((i, ms, nxt if nxt is not None else ms + 6000))
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

P = dict(side=0.9, hi_sup=0.6, act_e=0.5, act_mod=0.9, floor=0.4, over=1.3, tol=0.45, lead=20, gamma=0.6)
DECODE_LIMIT_S = 60.0


def _ffmpeg():
    p = shutil.which("ffmpeg")
    if p:
        return p
    for d in (Path(__file__).resolve().parent.parent / "ffmpeg", Path(__file__).resolve().parent / "ffmpeg"):
        if (d / "ffmpeg.exe").exists():
            return str(d / "ffmpeg.exe")
    return None


def _features(path: str):
    """Признаки по 10 мс (потоково): громкость центра в полосе голоса, поток новых звуков голоса, поток ВЧ."""
    exe = _ffmpeg()
    if not exe:
        return None
    try:
        pr = subprocess.Popen([exe, "-nostdin", "-v", "error", "-i", path, "-vn", "-ac", "2", "-ar", str(SR),
                               "-f", "s16le", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              creationflags=0x08000000 if os.name == "nt" else 0)
    except Exception:                                          # noqa: BLE001
        return None
    win = np.hanning(FFT).astype(np.float32)
    f = np.fft.rfftfreq(FFT, 1.0 / SR)
    mid = (f > 300) & (f < 3400)
    hi = (f > 3800) & (f < 5400)
    block = HOP * 256                                          # ~2.5 с звука за раз
    tail = np.zeros((0, 2), np.float32)
    e_out, fm_out, fh_out = [], [], []
    prev_m = prev_h = None
    t_end = time.monotonic() + DECODE_LIMIT_S
    try:
        while time.monotonic() < t_end:
            raw = pr.stdout.read(block * 4)
            if not raw:
                break
            x = np.frombuffer(raw[:len(raw) // 4 * 4], dtype=np.int16).astype(np.float32).reshape(-1, 2) / 32768.0
            if len(tail):
                x = np.concatenate([tail, x])
            n = (len(x) - FFT) // HOP + 1
            if n <= 0:
                tail = x
                continue
            idx = np.arange(FFT)[None, :] + HOP * np.arange(n)[:, None]
            m = (x[:, 0] + x[:, 1]) * 0.5
            sd = (x[:, 0] - x[:, 1]) * 0.5
            M = np.abs(np.fft.rfft(m[idx] * win, axis=1))
            S = np.abs(np.fft.rfft(sd[idx] * win, axis=1))
            cm = np.log1p(np.maximum(M[:, mid] - P["side"] * S[:, mid], 0.0) * 40.0)
            hm = np.log1p(M[:, hi] * 40.0)
            pm = np.concatenate([prev_m[None] if prev_m is not None else cm[:1], cm[:-1]])
            ph = np.concatenate([prev_h[None] if prev_h is not None else hm[:1], hm[:-1]])
            e_out.append(cm.mean(axis=1).astype(np.float32))
            fm_out.append(np.maximum(cm - pm, 0).sum(axis=1).astype(np.float32))
            fh_out.append(np.maximum(hm - ph, 0).sum(axis=1).astype(np.float32))
            prev_m, prev_h = cm[-1].copy(), hm[-1].copy()
            tail = x[n * HOP:]
    finally:
        try:
            pr.kill()
        except Exception:                                      # noqa: BLE001
            pass
        try:
            pr.stdout.close()
            pr.wait(timeout=5)
        except Exception:                                      # noqa: BLE001
            pass
    if not e_out or sum(len(a) for a in e_out) < 50:
        return None
    return np.concatenate(e_out), np.concatenate(fm_out), np.concatenate(fh_out)


def _ma(x, n):
    return np.convolve(x, np.ones(n, np.float32) / n, mode="same")


def _derive(feat):
    """(активность голоса 0..1, сила начала звука) по 10 мс."""
    e, fm, fh = feat
    lo, hi = np.percentile(e, 20), np.percentile(e, 92)
    en = np.clip((e - lo) / (hi - lo + 1e-6), 0, 1)
    mod = _ma(np.abs(_ma(e, 5) - _ma(e, 41)), 31)
    mod = np.clip(mod / (np.percentile(mod, 90) + 1e-6), 0, 1.5)
    act = _ma(np.clip(P["act_e"] * en + P["act_mod"] * mod * en, 0, 1) ** P["gamma"], 7)
    on = fm / (np.percentile(fm, 95) + 1e-6) - P["hi_sup"] * fh / (np.percentile(fh, 95) + 1e-6)
    return act.astype(np.float32), _ma(np.maximum(on, 0), 3).astype(np.float32)


def envelope(path: str):
    """Голос трека по 10 мс: (активность, начала звуков) — или None. Кэш на 4 трека (~0.2 МБ каждый)."""
    if not path or not os.path.exists(path):
        return None
    key = (path, os.path.getmtime(path))
    hit = _ENV_CACHE.get(key)
    if hit is not None:
        return hit
    feat = _features(path)
    if feat is None:
        return None
    res = _derive(feat)
    if len(_ENV_CACHE) > 3:
        _ENV_CACHE.pop(next(iter(_ENV_CACHE)))
    _ENV_CACHE[key] = res
    return res


def _weights(words):
    out = []
    for w in words:
        k = syllables(w) + 0.35
        if w.rstrip().endswith((",", ";", ":", "—", "-", "…", ".", "!", "?")):
            k += 0.45                                          # после знака — вдох
        out.append(k)
    return out


def refine(lines, est, env) -> list:
    """Уточнить оценку по звуку: слова — по «пропетому времени» строки, начала — к всплескам голоса."""
    if env is None:
        return est
    act, on = env
    nf = len(act)
    rate = song_rate(lines)
    out = list(est)
    for i, a, b in _spans(lines):
        words = (lines[i].get("text") or "").split(" ")
        if i >= len(est) or est[i] is None or len(words) < 2 or len(est[i]) != len(words):
            continue
        fa, fb = int(a / 10), min(nf - 1, int(b / 10))
        if fb - fa < 8:
            continue
        wts = _weights(words)
        n_syl = sum(syllables(w) for w in words)
        seg = np.maximum(act[fa:fb], P["floor"])
        U = np.concatenate([[0.0], np.cumsum(seg)]) * 10.0      # «пропетые» мс к каждому кадру строки
        need = n_syl / rate * 1000.0 * P["over"] * float(np.clip(seg.mean() * 1.6, 0.35, 1.0))
        u_end = min(U[-1], max(need, U[-1] * 0.25))
        cum = np.concatenate([[0.0], np.cumsum(wts)]) / sum(wts)
        tgt = np.interp(cum * u_end, U, np.arange(len(U))) + fa
        starts, prev = [float(fa)], float(fa)
        for k in range(1, len(words)):
            t = float(tgt[k])
            d = max(6.0, float(tgt[k + 1] - tgt[k]))
            tol = float(np.clip(d * P["tol"], 5, 35))
            lo, hi = int(max(prev + 5, t - tol)), int(min(fb - 3, t + tol))
            if hi > lo:
                idx = np.arange(lo, hi + 1)
                j = int(np.argmax(on[lo:hi + 1] - ((idx - t) / tol) ** 2))
                if on[lo + j] > 0.25:
                    t = float(lo + j) - P["lead"] / 10.0      # чуть раньше всплеска — заливка не опаздывает
            t = max(prev + 5, t)
            starts.append(t)
            prev = t
        end = min(max(starts[-1] + 12, float(tgt[-1])), fb - 3)
        res = []
        for k, w in enumerate(words):
            s0 = starts[k]
            e0 = starts[k + 1] if k + 1 < len(words) else end
            res.append((int(s0 * 10), w, int(max(s0 + 5, e0) * 10)))
        out[i] = res
    return out
