"""Кто исполнитель: разбор строки «автор» на отдельных людей и склейка разных написаний одного имени.

split(s)        — «A, B & C feat. D», «A x B», «A/B», «A и B», «(feat. X)» в названии → [A, B, C, D].
                  Не режет устоявшиеся названия: список известных групп, «X & The Y» (Bob Marley & The Wailers,
                  Florence + The Machine, Tyler, The Creator), стилизованные «elctrnc/sed:/», а также всё, что
                  ArtistIndex выучил по вашей медиатеке (строка встречается целиком, а её части отдельно — нигде).
key(s)          — ключ сравнения: регистр, «- Topic», VEVO, похожие кириллические буквы в латинских именах,
                  знаки (☆, $, пробелы) не важны: «Lil Flash$» = «LiL Flash$» = «lil flash».
ArtistIndex     — исполнители медиатеки. Склеивает ещё и опечатки / «хакерские» написания одного имени:
                  цифры вместо букв (0→o, 1→i, 3→e, 4→a, $→s…), удвоенные буквы, 1 отличие у имён от 6 знаков,
                  2 — от 11. Показывается самое частое написание (при равенстве — не КАПСОМ и не строчными).
ident(s)        — общий ключ исполнителя с учётом склеек последнего построенного индекса.
"""
import re
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache

# устоявшиеся названия с «разделителями» внутри — это одна группа, а не совместный трек
PROTECTED = ('AC/DC', 'Tyler, The Creator', 'Earth, Wind & Fire', 'Simon & Garfunkel', 'Years & Years',
             'Mumford & Sons', 'Hall & Oates', 'Chase & Status', 'Above & Beyond', 'Belle & Sebastian',
             'Iron & Wine', 'Crosby, Stills, Nash & Young', 'Crosby, Stills & Nash', 'Kool & the Gang',
             'Sly & the Family Stone', 'Echo & the Bunnymen', 'Florence + the Machine', 'Florence and the Machine',
             'Marina and the Diamonds', 'Of Monsters and Men', 'Coheed and Cambria', 'Hootie & the Blowfish',
             'Huey Lewis & the News', 'Tom Petty and the Heartbreakers', 'Bob Marley & the Wailers',
             'Prince & the Revolution', 'Ike & Tina Turner', 'Peter, Paul and Mary', 'Blood, Sweat & Tears',
             'Emerson, Lake & Palmer', 'Sam & Dave', 'Brooks & Dunn', 'Big & Rich', 'Dan + Shay',
             'Macklemore & Ryan Lewis', 'Daryl Hall & John Oates', 'Lil Nas X',
             'Мумий Тролль', 'Сплин', 'Кино')

_TOPIC = re.compile(r'\s*[-–—]\s*topic\s*$', re.I)
_VEVO = re.compile(r'(?:\s*vevo|\s*\(official\)|\s+official)\s*$', re.I)
_PROD = re.compile(r'[\[(]\s*(?:prod(?:uced)?\.?(?:\s+by)?|произв\.?)\b[^\])]*[\])]', re.I)
_FEAT_IN = re.compile(r'[\[(]\s*(?:feat(?:uring)?\.?|ft\.?|with|при\s+участии|совм\.?\s+с)\s+([^\])]+)[\])]', re.I)
# разделители: запятая/точка с запятой/вертикальная черта, « x », « & », « + », « и », « and », feat/ft/featuring,
# « / » с пробелами; «/» без пробелов — отдельно (_slash_ok)
_STRONG = re.compile(r'(\s*[,;|\n]+\s*|\s*\b(?:feat(?:uring)?|ft)\b\.?\s*|\s+при\s+участии\s+)', re.I)
_WEAK = re.compile(r'(\s*[&+×]\s*|\s+(?:[xх]|and|и|with|vs\.?)\s+(?=\S)|\s+/\s+)', re.I)
_THE = re.compile(r'^(?:the|da)\s+\S', re.I)
_LOOK = str.maketrans('аесорхуіјкмнвтАЕСОРХУІЈКМНВТ', 'aecopxyijkmhbtaecopxyijkmhbt')
_LEET = str.maketrans('013457@$!|8', 'oieastasiib')

_LEARNED_KEEP: set = set()            # ключи целых строк, которые медиатека считает одним исполнителем
_ALIAS: dict = {}                     # ключ → ключ «главного» написания (склейки ArtistIndex)


def key(value):
    return _key(value if type(value) is str else str(value or ''))


@lru_cache(maxsize=32768)
def _key(value):
    s = unicodedata.normalize('NFKC', value).casefold()
    s = _TOPIC.sub('', s)
    s = _VEVO.sub('', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Cf')
    if re.search('[a-z]', s):                          # кириллица-двойник в латинском имени: «Lil Flаsh»
        s = s.translate(_LOOK)
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    return ''.join(c for c in s if c.isalnum())


def skeleton(k):
    """Ключ без «хакерских» замен и удвоений: l1l fla$h ≈ lil flash, mzzlff ≈ mzlff."""
    s = (k or '').translate(_LEET)
    return re.sub(r'(.)\1+', r'\1', s)


def ident(name):
    k = key(name)
    return _ALIAS.get(k, k)


def _slash_ok(left, right):
    """«A/B» без пробелов — это два исполнителя? Нет для AC/DC-подобных и стилизованных «elctrnc/sed:/»."""
    l, r = left.strip(), right.strip()
    if not l or not r or r.endswith('/') or l.endswith('/'):
        return False
    if re.search(r'[:\\]', l + r):
        return False
    if len(key(l)) < 3 or len(key(r)) < 3:
        return False
    return True


def _rejoin_the(parts, seps):
    """«Bob Marley & The Wailers», «Tyler, The Creator» — часть на «The …» приклеивается обратно."""
    out, out_seps = [parts[0]], []
    for sep, p in zip(seps, parts[1:]):
        if _THE.match(p.strip()) and len(p.split()) <= 4 and out[-1].strip():
            out[-1] = out[-1] + sep + p
        else:
            out.append(p)
            out_seps.append(sep)
    return out, out_seps


@lru_cache(maxsize=16384)
def _split(value):
    s = unicodedata.normalize('NFKC', value)
    s = _PROD.sub(' ', s)
    s = _FEAT_IN.sub(lambda m: ', ' + m.group(1), s)
    s = _TOPIC.sub('', s)
    if key(s) in _LEARNED_KEEP:
        return (' '.join(s.split()),)
    saved = {}
    for i, name in enumerate(PROTECTED):
        if re.search(re.escape(name), s, re.I):
            token = f'PROTECTEDARTIST{i}TOKEN'
            saved[token] = re.search(re.escape(name), s, re.I).group(0)
            s = re.sub(re.escape(name), token, s, flags=re.I)
    pieces = _STRONG.split(s)
    parts, seps = _rejoin_the(pieces[0::2], pieces[1::2])
    weak = []
    for seg in parts:                                  # «A & B» внутри куска — если медиатека не знает его целиком
        if key(seg) in _LEARNED_KEEP:
            weak.append(seg)
            continue
        wp = _WEAK.split(seg)
        weak.extend(_rejoin_the(wp[0::2], wp[1::2])[0])
    parts = weak
    # «/» без пробелов внутри частей
    final = []
    for p in parts:
        bits = p.split('/')
        if len(bits) > 1 and all(_slash_ok(a, b) for a, b in zip(bits, bits[1:])):
            final.extend(bits)
        else:
            final.append(p)
    result, seen = [], set()
    for p in final:
        p = p.strip()
        for token, name in saved.items():
            p = p.replace(token, name)
        p = ' '.join(p.strip('()[] ').split())
        k = key(p)
        if k and k not in seen:
            result.append(p)
            seen.add(k)
    return tuple(result)


def split(value):
    if isinstance(value, (list, tuple)):
        return list(dict.fromkeys(n for item in value for n in split(item)))
    return list(_split(str(value or '')))


def credits(track):
    """Все исполнители трека: из поля «автор» и из «(feat. X)» в названии."""
    structured=track.get('artists')
    if isinstance(structured,(list,tuple)):
        names=[]
        for item in structured:
            name=item.get('name') if isinstance(item,dict) else item
            if isinstance(name,str) and name.strip():names.append(name.strip())
    else:names=[]
    if not names:names = split(track.get('artist'))
    for m in _FEAT_IN.finditer(str(track.get('title') or '')):
        for n in split(m.group(1)):
            if key(n) not in {key(x) for x in names}:
                names.append(n)
    # Explicit trailing credit without brackets: "Song feat. Guest".
    tail=re.search(r'\s+(?:feat(?:uring)?\.?|ft\.?)\s+(.+)$',str(track.get('title') or ''),re.I)
    if tail:
        suffix=re.split(r'\s+[—–-]\s+|\s*\((?:prod|remix|official)\b',tail.group(1),maxsplit=1,flags=re.I)[0]
        names.extend(split(suffix.strip('()[] ')))
    seen=set();result=[]
    for name in names:
        k=key(name)
        if k and k not in seen:seen.add(k);result.append(name)
    return result


def _lev(a, b, cap):
    """Расстояние Дамерау — Левенштейна с ранним выходом (> cap → cap + 1)."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev2, prev = None, list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        best = cur[0]
        for j in range(1, len(b) + 1):
            c = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + c)
            if prev2 is not None and i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
            best = min(best, cur[j])
        if best > cap:
            return cap + 1
        prev2, prev = prev, cur
    return prev[-1]


def same_artist(a, b):
    """Одно ли это имя с поправкой на опечатки (без контекста медиатеки)."""
    ka, kb = key(a), key(b)
    if not ka or not kb:
        return False
    if ka == kb or skeleton(ka) == skeleton(kb):
        return True
    n = min(len(ka), len(kb))
    cap = 2 if n >= 11 else 1 if n >= 6 else 0
    if not cap or ka[0] != kb[0]:
        return False
    if any(ch.isdigit() for ch in ka + kb) and re.sub(r'\D', '', ka) != re.sub(r'\D', '', kb) \
            and skeleton(ka) != skeleton(kb):
        return False                                   # «Artist 2» ≠ «Artist 3»
    return _lev(ka, kb, cap) <= cap


def learn(tracks):
    """Куски строк «автор», которые медиатека считает ОДНИМ исполнителем:
      * тот же исполнитель встречается и слитно: «key vs. locket» ↔ «keyvslocket»;
    Повторяющиеся совместные треки сами по себе не доказывают, что это одна группа."""
    _LEARNED_KEEP.clear()
    _split.cache_clear()
    segs = Counter()
    for t in tracks:
        a = ' '.join(str(t.get('artist') or '').split())
        for seg in _STRONG.split(_PROD.sub(' ', a))[0::2]:
            seg = ' '.join(seg.split())
            if seg:
                segs[seg] += 1
    alone = {key(seg) for seg in segs if len(_WEAK.split(seg)) == 1}   # встречаются как отдельный исполнитель
    keep = set()
    for seg, n in segs.items():
        wp = _WEAK.split(seg)
        if len(wp) == 1:
            continue
        parts = [p for p in wp[0::2] if key(p)]
        if key(seg) in alone:
            keep.add(key(seg))
    _LEARNED_KEEP.update(keep)
    _split.cache_clear()
    return keep


class ArtistIndex:
    def __init__(self, tracks):
        tracks = list(tracks or [])
        learn(tracks)
        names = defaultdict(Counter)
        for t in tracks:
            for name in credits(t):
                names[key(name)][name] += 1
        # склейка ключей: одинаковый «скелет» или опечатка
        parent = {k: k for k in names}

        def find(k):
            while parent[k] != k:
                parent[k] = parent[parent[k]]
                k = parent[k]
            return k
        by_skel = defaultdict(list)
        for k in names:
            by_skel[skeleton(k)].append(k)
        for ks in by_skel.values():
            for k in ks[1:]:
                parent[find(k)] = find(ks[0])
        buckets = defaultdict(list)                    # опечатки: только похожей длины и с той же первой буквой
        for k in names:
            if len(k) >= 6:
                buckets[(k[0], len(k) // 3)].append(k)
        for (c, b), ks in list(buckets.items()):
            near = ks + buckets.get((c, b + 1), [])
            for i, a in enumerate(ks):
                for bk in near[i + 1:] if near is ks else near:
                    if a != bk and find(a) != find(bk) and same_artist(a, bk):
                        parent[find(bk)] = find(a)
        clusters = defaultdict(Counter)
        for k, cnt in names.items():
            clusters[find(k)].update(cnt)
        # «главный» ключ кластера — у самого частого написания
        self.alias = {}
        self.names = {}
        for root, cnt in clusters.items():
            best = self._best(cnt)
            rep = key(best)
            self.names[rep] = cnt
            for k in names:
                if find(k) == root:
                    self.alias[k] = rep
        _ALIAS.clear()
        _ALIAS.update(self.alias)
        self.tracks = defaultdict(list)
        for t in tracks:
            for name in credits(t):
                rep = self.alias.get(key(name), key(name))
                lst = self.tracks[rep]
                if not lst or lst[-1] is not t:
                    if t not in lst:
                        lst.append(t)

    @staticmethod
    def _best(cnt):
        def score(item):
            name, n = item
            letters = [c for c in name if c.isalpha()]
            cased = bool(letters) and not (all(c.isupper() for c in letters) or all(c.islower() for c in letters))
            return (n, cased, -len(name))
        return max(cnt.items(), key=score)[0]

    def ident(self, name):
        k = key(name)
        return self.alias.get(k, k)

    def display(self, name):
        names = self.names.get(self.ident(name))
        return self._best(names) if names else name

    def tracks_for(self, name):
        return self.tracks.get(self.ident(name), [])

    def groups(self):
        return [(self._best(self.names[k]), tracks) for k, tracks in self.tracks.items() if k in self.names]

    def suggestions(self, name):
        from difflib import SequenceMatcher
        k = self.ident(name)
        return [self._best(self.names[n]) for n in self.names
                if n != k and len(k) >= 7 and abs(len(n) - len(k)) <= 2
                and SequenceMatcher(None, k, n).ratio() >= .88]


_CACHE = {}


def index_for(tracks):
    """ArtistIndex с кэшем: пересобирается, только когда меняются авторы в медиатеке."""
    tracks = list(tracks or [])
    sig = tuple((id(t), str(t.get('path') or t.get('url') or ''),
                 str(t.get('artist') or ''), str(t.get('artists') or ''),str(t.get('title') or '')) for t in tracks)
    idx = _CACHE.get(sig)
    if idx is None:
        idx = ArtistIndex(tracks)
        _CACHE.clear()
        _CACHE[sig] = idx
    else:
        _ALIAS.clear()
        _ALIAS.update(idx.alias)
    return idx
