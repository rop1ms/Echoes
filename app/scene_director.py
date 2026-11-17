"""Local inference and cue planning for Scene, independent of Qt and GIF providers."""
from __future__ import annotations

import bisect
import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

import scene_cards


@dataclass(frozen=True)
class Motif:
    name: str
    en: str
    icon: str
    color: str
    particles: str
    animation: str
    query: str
    examples: str


MOTIFS = {
    "ice": Motif("Лёд", "Ice", "❄️", "#6c92ff", "snow", "crystal", "ice crystal snow loop",
                 "холод мороз замерз ледяной лёд снег снежинки зима иней | icy ice snow frost frozen winter crystal"),
    "glint": Motif("Блики", "Glints", "✨", "#ff8bba", "sparks", "lens", "lens flare sparkle loop",
                   "блики блеск сияние яркий свет слепит ослепляет фоточки фотка вспышка отражение солнце "
                   "| reflection glare sparkle glitter glow photo flash glint shine lens flare"),
    "chrome": Motif("Хром", "Chrome", "⛓️", "#a68bf5", "sparks", "links", "silver chain chrome loop",
                    "цепь цепями цепочка хром серебро металл железо сталь браслет кулон "
                    "| silver chain steel chrome metal bracelet necklace link"),
    "flight": Motif("Полёт", "Flight", "🪽", "#9a8ef2", "dust", "wings", "bird wings flight loop",
                    "орёл орел птица птицы птички крылья летел улетают полёт высота стая "
                    "| bird eagle wings flying flight flock feather soar"),
    "rain": Motif("Дождь", "Rain", "💧", "#6492de", "rain", "ripples", "raindrop window rain loop",
                  "дождь дождик ливень слёзы плачу промок гроза капли раны тучи "
                  "| rain raindrop tears crying downpour wet storm puddle"),
    "heart": Motif("Сердце", "Heart", "💗", "#ef779a", "sparks", "heart", "pink heart pulse loop",
                   "люблю влюблён влюбился любовь сердце нежность поцелуй чувства скучаю "
                   "| love loving heart kiss sweetheart crush affection"),
    "money": Motif("Деньги", "Money", "🪙", "#d9a75f", "dust", "coin", "gold coin spin loop",
                   "деньги монета наличка рубли заплатил ценник цена банк счёт купюра "
                   "| money bank cash dollars coins gold price pay"),
    "chance": Motif("Бросок монеты", "Coin toss", "🪙", "#e3ae6d", "dust", "coin", "coin toss flip loop",
                    "решка ребро подбросил подкинул жребий подкинуть бросок "
                    "| coin toss heads tails flip chance"),
    "fire": Motif("Огонь", "Fire", "🔥", "#f58a5f", "embers", "lens", "ember sparks fire loop",
                  "огонь пламя дым горю сгорел жар пепел искры зажигаю "
                  "| fire flame ashes burning burn smoke ember heat"),
    "night": Motif("Ночное небо", "Night sky", "🌙", "#a88afa", "sparks", "orbit", "moon stars cosmos loop",
                   "ночь звёзды луна темнота космос планета небо вселенная комета "
                   "| night stars moon galaxy dark space planet cosmos comet"),
    "water": Motif("Волны", "Waves", "🌊", "#58b8c4", "bubbles", "ripples", "ocean wave water loop",
                   "волна море океан вода берег прилив тону рябь "
                   "| wave ocean water sea beach shore tide ripples"),
}

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
_CYR = re.compile(r"[а-яё]", re.I)


def words(text):
    return _WORD.findall(text.casefold().replace("ё", "е"))


@lru_cache(maxsize=8192)
def _ngrams(word):
    padded = "^" + word + "$"
    return Counter(padded[i:i + n] for n in (3, 4, 5) for i in range(len(padded) - n + 1))


@lru_cache(maxsize=1)
def _fit_model():
    """Fit TF-IDF nearest centroids on the bilingual labeled examples above."""
    samples = {name: Counter() for name in MOTIFS}
    for name, motif in MOTIFS.items():
        for word in set(words(motif.examples)):
            samples[name].update(_ngrams(word))
    df = Counter(gram for row in samples.values() for gram in row)
    idf = {gram: 1 + math.log((1 + len(samples)) / (1 + n)) for gram, n in df.items()}
    model = {}
    for name, grams in samples.items():
        weighted = {g: (1 + math.log(n)) * idf[g] for g, n in grams.items()}
        length = math.hypot(*weighted.values())
        model[name] = {g: v / length for g, v in weighted.items()}
    return idf, model


@lru_cache(maxsize=4096)
def infer(word):
    idf, model = _fit_model()
    grams = {g: n * idf.get(g, 2.5) for g, n in _ngrams(word).items()}
    length = math.hypot(*grams.values())
    if not length or len(word) < 3 or word in scene_cards.STOP:
        return "", 0.0
    scores = sorted((sum(v * weights.get(g, 0.0) for g, v in grams.items()) / length, name)
                    for name, weights in model.items())
    score, name = scores[-1]
    if score < 0.128 or score - scores[-2][0] < 0.034:
        return "", 0.0
    return name, score


def cues(text):
    best = {}
    supporting = {}
    for i, token in enumerate(text.split(" ")):
        for word in words(token):
            name, score = infer(word)
            if name:
                supporting.setdefault(name, set()).add(word)
                if name not in best or score > best[name][0]:
                    best[name] = (score, i, word)
    return {name: (score + .036 * min(3, len(supporting[name]) - 1), i, word)
            for name, (score, i, word) in best.items()}


def match_score(description, name):
    evidence = cues(description).get(name)
    return evidence[0] if evidence else 0.0


@dataclass(frozen=True)
class Sound:
    step: float
    energy: tuple
    bass: tuple
    hits: tuple
    changes: tuple
    bpm: int
    profile: dict

    def sample(self, seconds):
        i = max(0, int(seconds / self.step))
        return (self.energy[i], self.bass[i]) if i < len(self.energy) else None

    def hit(self, seconds):
        i = bisect.bisect_right(self.hits, seconds + 0.018) - 1
        return max(0., 1. - max(0., seconds - self.hits[i]) / 0.28) if i >= 0 else 0.

    def waveform(self, duration, points=64):
        stride = max(1., duration / (points * self.step))
        chunks = ((int(i * stride), int((i + 1) * stride)) for i in range(points))
        return [max(self.energy[a:b], default=0.) for a, b in chunks]


@lru_cache(maxsize=4)
def _live_window(length, sample_rate):
    return np.hanning(length), np.fft.rfftfreq(length, 1 / sample_rate) <= 180


def live_level(samples, sample_rate):
    window, low_bins = _live_window(len(samples), sample_rate)
    spec = np.abs(np.fft.rfft(samples * window))
    level = float(np.sqrt(np.mean(samples ** 2))) * 3.1
    bass = float(np.sqrt(np.sum(spec[low_bins] ** 2))) * 10 / len(samples)
    return min(1., level), min(1., bass)


def _scale(values):
    lo, hi = np.percentile(values, (12, 95))
    return np.clip((values - lo) / max(0.035, hi - lo), 0, 1)


def sound_from_samples(samples, sr):
    """A playback-time map of RMS, bass envelope, spectral onsets and section changes."""
    if len(samples) < sr or float(np.max(np.abs(samples))) < .001:
        return None
    hop, win = sr // 40, sr // 20
    step = hop / sr
    window = np.hanning(win)
    bins = np.fft.rfftfreq(win, 1 / sr)
    low = bins <= 155
    frames = np.lib.stride_tricks.sliding_window_view(samples, win)[::hop]
    rms = np.empty(len(frames))
    bass = np.empty(len(frames))
    flux = np.zeros(len(frames))
    last = np.zeros(bins.size)
    for i in range(0, len(frames), 384):
        chunk = frames[i:i + 384]
        spec = np.abs(np.fft.rfft(chunk * window, axis=-1))
        log_spec = np.log1p(spec)
        n = len(chunk)
        flux[i:i+n] = np.maximum(0, np.diff(log_spec, axis=0, prepend=last[None])).mean(axis=1)
        last = log_spec[-1]
        rms[i:i+n] = np.sqrt(np.mean(chunk ** 2, axis=1))
        bass[i:i+n] = np.sqrt(np.sum(spec[:, low] ** 2, axis=1)) / win
    energy = _scale(rms)
    bass = _scale(bass)
    peak = np.maximum(0, np.diff(bass, prepend=bass[0])) * .50 + _scale(flux) * .75
    from scipy.ndimage import median_filter
    from scipy.signal import find_peaks
    floor = median_filter(peak, size=25)
    hits, _ = find_peaks(peak, height=np.maximum(.31, floor + .18), prominence=.14, distance=8)
    # Smooth over two seconds, then detect changes between adjacent two-second phrases.
    width = round(2 / step)
    smooth = np.convolve(energy, np.ones(width) / width, "same") if len(energy) >= width else energy
    changes = np.maximum(0, smooth[width:] - smooth[:-width])
    boundaries, _ = find_peaks(changes, height=.22, prominence=.12, distance=round(5 / step))
    profile, bpm = {}, 0
    if len(samples) >= sr * 5:
        from music_intel import SR, analyze_signal, audio_mood
        if sr == SR:
            # The mood estimator only needs an excerpt. The cue map uses the entire analysis window.
            length = min(len(samples), 28 * sr)
            start = (len(samples) - length) // 3
            f = analyze_signal(samples[start:start + length])
            profile = audio_mood(f)
            bpm = round(f.get("bpm", 0)) if f.get("pulse", 0) >= .13 and len(hits) >= 5 else 0
    return Sound(step * 4, tuple(map(float, energy[::4])), tuple(map(float, bass[::4])),
                 tuple(float((i + .5) * step) for i in hits),
                 tuple(float((i + width / 2) * step) for i in boundaries), bpm, profile)


@lru_cache(maxsize=8)
def _analyse_file(path, stamp, duration):
    from music_intel import SR, decode_excerpt
    samples = decode_excerpt(path, seconds=min(480., max(5., duration + .1) if duration else 480.), start=0)
    return sound_from_samples(samples, SR) if samples is not None else None


def analyse_file(path, duration):
    try:
        file = Path(path)
        if not file.is_file():
            return None
        stat = file.stat()
    except OSError:
        return None
    return _analyse_file(path, (stat.st_mtime_ns, stat.st_size), duration)


def stat(title, icon, value, caption, *, bar=None, layout="stat"):
    return {"emoji": icon, "title": title, "kind": "text", "a": str(value), "b": str(value),
            "caption": caption, "bar": bar, "layout": layout}


def _motif_card(name, word, english, repeats):
    m = MOTIFS[name]
    label = m.en if english else m.name
    if repeats > 1:
        caption = "Recurring image" if english else "Образ повторяется"
    else:
        caption = "Image in the lyric" if english else "Образ в этой строке"
    return {**stat(label, m.icon, word[:1].upper() + word[1:], caption), "motif": name}


def plan(texts, timings, title="", sound=None, plain=()):
    """Direct each line using its learned motifs, recurrence, neighboring phrases and audio."""
    found = [cues(text) for text in texts]
    phrase = Counter(text.casefold() for text in texts)
    votes = Counter({name: val[0] * .75 for name, val in cues(title).items()})
    for items in found:
        for name, (score, _, _) in items.items():
            votes[name] += score
    for line in plain:
        for name, (score, _, _) in cues(line).items():
            votes[name] += score
    theme = votes.most_common(1)[0][0] if votes else ""
    result, last_note = [], -math.inf
    for i, (text, ms, hits) in enumerate(zip(texts, timings, found)):
        english = not _CYR.search(text)
        repeats = phrase[text.casefold()]
        prev = found[i - 1] if i else {}
        nxt = found[i + 1] if i + 1 < len(found) else {}
        names = sorted(hits, key=lambda name: hits[name][0] + .045 * (name in prev or name in nxt)
                       + .015 * (name == theme), reverse=True)[:2]
        cards = [_motif_card(name, hits[name][2], english, repeats) for name in names]
        facts = scene_cards.fact_cards(i, texts, timings, english)
        metrics = sound.sample(ms / 1000) if sound else None
        if len(cards) < 2 and metrics:
            card = stat("Dynamics" if english else "Динамика", "〰️", f"{metrics[0]:.0%}",
                        "Relative to this track" if english else "Относительно всего трека",
                        bar=(metrics[0], metrics[0]))
            cards.append({**card, "metric": "energy"})
        cards.extend(facts[:2 - len(cards)])
        note = None
        change = sound and any(abs(ms / 1000 - t) < 1.25 for t in sound.changes)
        if ms - last_note >= 8500 and (change or (names and len(names) > 1)):
            name = names[0] if names else theme
            m = MOTIFS.get(name)
            note = {"emoji": m.icon if m else "〰️", "app": "Scene AI" if english else "Режиссёр ИИ",
                    "title": ("Energy rise" if english else "Подъём энергии") if change else (
                        "Images in the lyric" if english else "Образы в строке"),
                    "text": "  ·  ".join(MOTIFS[n].en if english else MOTIFS[n].name for n in names) or text}
            last_note = ms
        marks = {hits[n][1]: n for n in names}
        result.append({"keys": sorted(marks), "cards": cards, "note": note, "motifs": marks,
                       "motif": marks[min(marks)] if marks else (result[-1]["motif"] if i and prev else theme)})
    return result, theme
