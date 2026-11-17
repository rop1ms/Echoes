# search_util.py
"""
Поиск по коллекции «по словам»: запрос разбивается на слова, и каждое должно
встретиться где угодно в «исполнитель + название + альбом». Поэтому находится
и «gladiator», и «kai angel», и «kai angel gladiator», и «gladiator - kai angel»
(порядок слов не важен, регистр и «ё/е» — тоже).

Слово можно напечатать и не в той раскладке («дштлшт» = «linkin»), и кириллицей
вместо латиницы («линкин» = «linkin»), и наоборот («serega» = «Серега»).
"""
from __future__ import annotations

import re
from functools import lru_cache

_SPLIT = re.compile(r"[\s\-–—·,;:|/&+]+")
_RU = "йцукенгшщзхъфывапролджэячсмитьбю"
_EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,."
_SWAP = str.maketrans(_RU + _EN, _EN + _RU)
_TR = str.maketrans({"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z", "и": "i", "й": "y",
       "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
       "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e",
       "ю": "yu", "я": "ya", "і": "i", "ї": "yi", "є": "ye", "ґ": "g"})
_CYR = re.compile("[а-яёіїєґ]")


def norm(s) -> str:
    return str(s or "").casefold().replace("ё", "е")


def translit(s: str) -> str:
    return s.translate(_TR)


def tokens(query: str) -> list[str]:
    return [w for w in _SPLIT.split(norm(query)) if w]


def variants(word: str) -> tuple[str, ...]:
    """Слово как напечатано + в другой раскладке + латиницей (для слов от 3 букв —
    короткие дали бы случайные совпадения)."""
    if len(word) < 3:
        return (word,)
    out = [word]
    sw = word.translate(_SWAP)
    if sw != word:
        out.append(sw)
    if _CYR.search(word):
        out.append(translit(word))
    return tuple(dict.fromkeys(out))


def hay_of(*fields) -> str:
    """Склейка полей для поиска; кириллица — ещё и латиницей («Серега» находится по «serega»)."""
    h = " ".join(norm(f) for f in fields if f)
    return h + " " + translit(h) if _CYR.search(h) else h


@lru_cache(maxsize=64)
def _query_variants(query: str) -> tuple[tuple[str, ...], ...]:
    # One search compares the same query with thousands of tracks.
    return tuple(variants(word) for word in tokens(query))


def matches(query, *fields) -> bool:
    """Все слова запроса есть в склейке полей (title, artist, album...)."""
    if isinstance(query, str):
        plan = (_query_variants(query) if len(query) <= 512 else
                tuple(variants(word) for word in tokens(query)))
    else:
        plan = tuple(variants(word) for word in query)
    if not plan:
        return True
    hay = hay_of(*fields)
    for alternatives in plan:
        for value in alternatives:
            if value in hay:
                break
        else:
            return False
    return True


def track_matches(query, t: dict) -> bool:
    return matches(query, t.get("title"), t.get("artist"), t.get("album"))
