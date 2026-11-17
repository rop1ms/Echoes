"""Scene card formatting and support for saved user scenes."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

VERSION = 1
_WORD = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
_VOW = re.compile(r"[аеёиоуыэюяaeiouy]", re.IGNORECASE)

STOP = frozenset("""
и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне было вот от меня
еще нет о из ему теперь когда даже ну вдруг ли если уже или ни быть был него до вас нибудь опять уж вам ведь там
потом себя ничего ей может они тут где есть надо ней для мы тебя их чем была сам чтоб без будто чего раз тоже
себе под будет ж тогда кто этот того потому этого какой совсем ним здесь этом один почти мой тем чтобы нее
сейчас были куда зачем всех никогда можно при наконец два об другой хоть после над больше тот через эти нас про
всего них какая много разве три эту моя впрочем хорошо свою этой перед иногда лучше чуть том нельзя такой им
более всегда конечно всю между это эта мои твой твоя твои свой своя просто очень тебе мной тобой
the a an and or but of to in on at for with from by is are was were be been am i you he she it we they me my your
his her its our their this that these those not no so if then than as do does did have has had will would can
could just all up out about into over oh yeah ya im dont every each some any there here when where what who how
came come told tell hold holds knew know till until were been like got get let too very more than them then
""".split())

def norm(word: str) -> str:
    """Слово без знаков, в нижнем регистре, «ё» как «е»."""
    return "".join(_WORD.findall(word.lower())).replace("ё", "е")


def _syll(text: str) -> int:
    return max(1, len(_VOW.findall(text)))


def fact_cards(i, texts, ms, english) -> list:
    """Карточки из самой песни — темп произнесения и позиция строки."""
    n = len(texts)
    nxt = ms[i + 1] if i + 1 < n else ms[i] + 4000
    dur = max(0.4, min(12.0, (nxt - ms[i]) / 1000.0))
    rate = _syll(texts[i]) / dur
    if english:
        cap = "tongue twister" if rate > 6.5 else "fast" if rate > 4.5 else "easy pace" if rate > 2.5 else "drawn out"
        return [{"emoji": "🎤", "title": "Flow", "kind": "text", "a": f"{rate:.1f}", "b": f"{rate:.1f}", "unit": "",
                 "caption": f"syllables per second — {cap}", "bar": (0.0, min(1.0, rate / 8.0)), "layout": "stat",
                 "chip": ""},
                {"emoji": "📜", "title": "Line", "kind": "text", "a": f"{i + 1} / {n}", "b": f"{i + 1} / {n}",
                 "unit": "", "caption": "of the song", "bar": (i / max(1, n), (i + 1) / max(1, n)), "layout": "stat",
                 "chip": ""}]
    cap = "скороговорка" if rate > 6.5 else "быстро" if rate > 4.5 else "спокойно" if rate > 2.5 else "нараспев"
    val = f"{rate:.1f}".replace(".", ",")
    return [{"emoji": "🎤", "title": "Подача", "kind": "text", "a": val, "b": val, "unit": "",
             "caption": f"слогов в секунду — {cap}", "bar": (0.0, min(1.0, rate / 8.0)), "layout": "stat", "chip": ""},
            {"emoji": "📜", "title": "Строка", "kind": "text", "a": f"{i + 1} / {n}", "b": f"{i + 1} / {n}",
             "unit": "", "caption": "текста песни", "bar": (i / max(1, n), (i + 1) / max(1, n)), "layout": "stat",
             "chip": ""}]


def _fmt_int(v: int) -> str:
    s = f"{abs(int(v)):,}".replace(",", " ")                   # узкий пробел между разрядами
    return ("−" + s) if v < 0 else s


def card_value(card: dict, t: float) -> tuple:
    """Что показывает карточка в момент t (0..1 по строке): (текст значения, доля полоски | None)."""
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    e = 1.0 - (1.0 - t) ** 2.2                                 # быстро в начале, мягко к концу
    kind, a, b, unit = card["kind"], card["a"], card["b"], card.get("unit", "")
    bar = card.get("bar")
    frac = None if bar is None else bar[0] + (bar[1] - bar[0]) * e
    if kind == "text":
        return str(b if t >= 0.5 else a) + unit, frac
    v = int(round(a + (b - a) * e))
    if kind == "pct":
        return _fmt_int(v) + "%", frac
    if kind == "time":
        v = max(0, v)
        return f"{v // 60}:{v % 60:02d}", frac
    return _fmt_int(v) + unit, frac


# ── своя сцена из файла ──────────────────────────────────────────────── #

def scene_key(artist: str, title: str) -> str:
    return hashlib.sha1(f"{norm(artist)}|{norm(title)}".encode("utf-8")).hexdigest()[:20]


def scene_dir() -> Path:
    try:
        from data_home import root
    except ImportError:
        return Path.home() / ".neon_player" / "scenes"
    return root() / "scenes"


def scene_path(artist: str, title: str) -> Path:
    return scene_dir() / f"{scene_key(artist, title)}.json"


def _valid_card(c) -> bool:
    return (isinstance(c, dict) and isinstance(c.get("title"), str) and isinstance(c.get("emoji"), str)
            and c.get("kind") in ("pct", "num", "time", "money", "text") and "a" in c and "b" in c)


def apply_overrides(scene: list, texts: list, path: Path) -> list:
    """Подменить строки сцены теми, что описаны в файле (ключ — текст строки). Битый файл — молча мимо."""
    try:
        if not path.is_file() or path.stat().st_size > 2_000_000:
            return scene
        data = json.loads(path.read_text(encoding="utf-8"))
        lines = data.get("lines") if isinstance(data, dict) else None
        if not isinstance(lines, dict):
            return scene
    except (OSError, ValueError):
        return scene
    by = {" ".join(str(k).split()).lower(): v for k, v in lines.items() if isinstance(v, dict)}
    for i, text in enumerate(texts):
        o = by.get(" ".join(text.split()).lower())
        if not o:
            continue
        n_words = len(text.split(" "))
        ent = dict(scene[i])
        keys = o.get("keys")
        if isinstance(keys, list):
            ent["keys"] = sorted({int(k) for k in keys if isinstance(k, int) and 0 <= k < n_words})[:3]
        cards = o.get("cards")
        if isinstance(cards, list):
            good = []
            for c in cards[:2]:
                if _valid_card(c):
                    c = dict(c)
                    c.setdefault("unit", "")
                    c.setdefault("caption", "")
                    c["layout"] = c.get("layout") if c.get("layout") in ("stat", "goal", "spark", "range") else "stat"
                    c["chip"] = str(c.get("chip") or "")[:24]
                    b = c.get("bar")
                    c["bar"] = tuple(b[:2]) if isinstance(b, (list, tuple)) and len(b) >= 2 else None
                    good.append(c)
            if good:
                ent["cards"] = good
        note = o.get("note")
        if isinstance(note, dict) and isinstance(note.get("title"), str):
            ent["note"] = {"emoji": str(note.get("emoji", "🔔")), "app": str(note.get("app", "")),
                           "title": note["title"], "text": str(note.get("text", ""))}
        scene[i] = ent
    return scene


def export(scene: list, texts: list, path: Path) -> Path:
    """Записать сцену файлом — чтобы править руками или поделиться."""
    lines = {}
    for text, ent in zip(texts, scene):
        lines[text] = {"keys": ent["keys"], "cards": [{**c, "bar": list(c["bar"]) if c.get("bar") else None}
                                                      for c in ent["cards"]], "note": ent["note"]}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"v": VERSION, "lines": lines}, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path
