# ya_foryou.py
"""
«Для вас и тренды» (Echoes Music): настоящие чарты и рекомендации по всей вашей медиатеке.

  taste(win)      — разбор коллекции и прослушиваний: любимые исполнители (за всё время и СЕЙЧАС —
                    последние ~200 прослушиваний с затуханием за 3 дня), жанры с долями;
  fetch_trends()  — «Чарт России» (Apple Music, most-played RU) и «Мировой чарт» (Deezer);
  fetch_recs(t)   — похожие исполнители (Deezer related от ваших главных, без тех, что уже есть),
                    их лучшие треки, «ещё от ваших исполнителей» (чего нет в коллекции), новое в ваших жанрах.

Всё сетевое — в фоне и с кэшем на диске (~/Echoes/foryou_net.json): тренды обновляются раз в 6 часов,
рекомендации — раз в сутки или когда меняются ваши главные исполнители.
"""
from __future__ import annotations

import data_home
import json
import math
import re
import time
from functools import lru_cache
from pathlib import Path

CACHE = data_home.root() / "foryou_net.json"
UA = {"User-Agent": "ECHOES-player/1.0"}
TRENDS_TTL = 6 * 3600
RECS_TTL = 24 * 3600
UNKNOWN = {"", "unknown artist", "неизвестный исполнитель", "unknown", "various artists"}

# жанр из тегов файла → жанр Deezer (id, название)
DEEZER_GENRES = [
    (("rap", "hip hop", "hip-hop", "hiphop", "trap", "drill", "рэп", "хип", "plugg", "rage", "phonk"), 116, "Рэп / хип-хоп"),
    (("metal", "метал", "core"), 464, "Метал"),
    (("rock", "рок", "punk", "панк", "grunge"), 152, "Рок"),
    (("alternative", "indie", "альтерн", "инди", "shoegaze", "emo"), 85, "Альтернатива"),
    (("electro", "edm", "techno", "house", "electronic", "электрон", "dubstep", "drum", "dnb", "hyperpop", "breakcore"), 106, "Электроника"),
    (("dance", "танц", "disco"), 113, "Танцевальная"),
    (("r&b", "rnb", "soul", "соул"), 165, "R&B"),
    (("jazz", "джаз"), 129, "Джаз"),
    (("classical", "класс", "orchestra"), 98, "Классика"),
    (("soundtrack", "ost", "game", "film", "anime", "саундтрек"), 173, "Саундтреки"),
    (("reggae", "регги"), 144, "Регги"),
    (("folk", "фолк"), 466, "Фолк"),
    (("latin", "latino", "reggaeton"), 197, "Латино"),
    (("pop", "поп"), 132, "Поп"),
]


def _main_artist(a: str) -> str:
    a = (a or "").replace(" - Topic", "")
    return re.split(r",| & | x | feat\.? | ft\.? | Feat\.? ", a, maxsplit=1)[0].strip()


def _norm(s: str) -> str:
    return _norm_c(s) if type(s) is str else _norm_c(str(s or ""))


@lru_cache(maxsize=32768)
def _norm_c(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
    return re.sub(r"[^\w]+", " ", s).strip()


def _genre_of(text: str):
    t = (text or "").lower()
    if not t:
        return None
    for keys, gid, name in DEEZER_GENRES:
        if any(k in t for k in keys):
            return gid, name
    return None


# ══════════════════════════════════════════════════════════════════════════ #
#  Вкус
# ══════════════════════════════════════════════════════════════════════════ #

_TASTE = {"key": None, "val": None}


def taste(win) -> dict:
    """{'top': [(artist, score)], 'now': [(artist, score)], 'genres': [(gid, name, share)], 'owned': set,
        'owned_artists': set, 'total': N}
    Запоминается, пока не поменялись библиотека, статистика и последние прослушивания (не дольше 10 мин —
    «сейчас слушаете» затухает по дням): раньше весь проход по библиотеке шёл на каждой смене трека
    в потоке интерфейса — десятки-сотни мс, на быстрой смене волн — рывки."""
    lib = list(getattr(win, "library", []) or [])
    stats = getattr(getattr(win, "stats", None), "data", None) or {}
    now = time.time()
    recent = stats.get("recent") or []
    prof = getattr(getattr(win, "_ya", None), "_profiles", None) or {}
    key = (id(getattr(win, "library", None)), len(lib), len(stats.get("artists") or {}), int(stats.get("total", 0) // 60),
           len(recent), (recent[-1].get("ts") if recent and isinstance(recent[-1], dict) else None),
           len(prof), int(now // 600), int(((getattr(win, "settings", None) or {}).get("foryou_fb") or {}).get("rev", 0)))
    if _TASTE["key"] == key and _TASTE["val"] is not None:
        return _TASTE["val"]
    val = _taste(win, lib, stats, now)
    _TASTE["key"], _TASTE["val"] = key, val
    return val


def _taste(win, lib, stats, now) -> dict:
    from artist_identity import index_for, credits, split
    idx = index_for(lib)                                   # Lil Flash$ = LiL Flash$, «A & B» — двое
    disp = {}

    def who(name):
        if not name or name.strip().lower() in UNKNOWN:
            return ""
        k = idx.ident(name)
        if k not in disp:
            disp[k] = idx.display(name) if k in idx.names else name.strip()
        return k

    score, nowscore, owned, owned_art = {}, {}, set(), set()
    for t in lib:
        owned.add((_norm(_main_artist(t.get("artist", ""))), _norm(t.get("title", ""))))
        names = credits(t)
        for i, n in enumerate(names):
            k = who(n)
            if k:
                score[k] = score.get(k, 0.0) + (1.0 if i == 0 else 0.5)    # гость в треке весит меньше
                owned_art.add(k)
    for a, d in (stats.get("artists") or {}).items():
        k = who((split(a) or [""])[0])
        if k:
            score[k] = score.get(k, 0.0) + 0.35 * float(d.get("plays", 0) or 0)
    for r in stats.get("recent") or []:
        w = math.exp(-max(0.0, now - float(r.get("ts", now) or now)) / (3 * 86400))
        for i, n in enumerate(split(r.get("artist", ""))):
            k = who(n)
            if not k:
                continue
            nowscore[k] = nowscore.get(k, 0.0) + (w if i == 0 else w * 0.5)
            score[k] = score.get(k, 0.0) + 2.0 * w
    # 👍/👎 в «Для вас» (fy_feedback): лайкнутые исполнители — в «ваши» (по ним ищутся похожие),
    # дизлайкнутые — вниз, а с «меньше такого» дважды — вовсе не в затравку рекомендаций
    import fy_feedback as FB
    fb = FB.data(getattr(win, "settings", None) or {})
    fb_art = {}
    for e in fb["artists"].values():
        if not isinstance(e, dict) or not e.get("n"):
            continue
        k = who(e["n"])
        if not k:
            continue
        s_ = float(e.get("s", 0) or 0)
        fb_art[k] = s_
        if s_ > 0:
            score[k] = score.get(k, 0.0) + 3.0 * s_
        elif s_ <= FB.BLOCK:
            score.pop(k, None)
            nowscore.pop(k, None)
        elif k in score:
            score[k] *= 0.15
    # жанры: теги файлов, затем — профили music_intel (если уже посчитаны)
    gcount = {}
    for t in lib:
        g = _genre_of(t.get("genre", ""))
        if g:
            gcount[g] = gcount.get(g, 0) + 1
    try:
        prof = getattr(getattr(win, "_ya", None), "_profiles", None) or {}
        for pr in prof.values():
            for f in (pr.get("families") or [])[:1]:
                g = _genre_of(f)
                if g:
                    gcount[g] = gcount.get(g, 0) + 0.5
    except Exception:                                      # noqa: BLE001
        pass
    gsum = sum(gcount.values()) or 1
    gw = {g[1]: FB.genre_factor(getattr(win, "settings", None) or {}, g[1]) for g in gcount}
    genres = [(g[0], g[1], n / gsum) for g, n in sorted(gcount.items(), key=lambda x: -x[1] * gw[x[0][1]])]
    return {"top": [(disp[k], v) for k, v in sorted(score.items(), key=lambda x: -x[1])],
            "now": [(disp[k], v) for k, v in sorted(nowscore.items(), key=lambda x: -x[1])],
            "genres": genres, "owned": owned, "owned_artists": owned_art, "total": len(lib),
            "fb_art": fb_art, "genre_w": gw, "fb_rev": int(fb.get("rev", 0))}


def now_artists(win, n=4) -> list[str]:
    """Кого вы СЕЙЧАС часто слушаете (последние прослушивания с затуханием); добирается любимыми из коллекции."""
    tt = taste(win)
    out = [a for a, _ in tt["now"]][:n]
    for a, _ in tt["top"]:
        if len(out) >= n:
            break
        if a not in out:
            out.append(a)
    return out


# ══════════════════════════════════════════════════════════════════════════ #
#  Сеть
# ══════════════════════════════════════════════════════════════════════════ #

def _get(url, **params):
    import requests
    r = requests.get(url, params=params or None, headers=UA, timeout=8)
    r.raise_for_status()
    return r.json()


def _dz_track(d, because=""):
    alb = d.get("album") or {}
    return {"title": d.get("title") or "", "artist": (d.get("artist") or {}).get("name") or "",
            "duration": int(d.get("duration") or 0), "album": alb.get("title") or "",
            "cover_url": alb.get("cover_medium") or alb.get("cover_big") or "", "because": because}


def fetch_trends() -> dict:
    out = {"ru": [], "world": []}
    try:
        j = _get("https://rss.applemarketingtools.com/api/v2/ru/music/most-played/40/songs.json")
        for d in (j.get("feed") or {}).get("results") or []:
            art = (d.get("artworkUrl100") or "").replace("100x100", "300x300")
            out["ru"].append({"title": d.get("name") or "", "artist": d.get("artistName") or "", "duration": 0,
                              "album": "", "cover_url": art, "because": ""})
    except Exception as e:                                 # noqa: BLE001
        print("[foryou] apple:", e)
    try:
        j = _get("https://api.deezer.com/chart/0/tracks", limit=40)
        out["world"] = [_dz_track(d) for d in j.get("data") or []]
    except Exception as e:                                 # noqa: BLE001
        print("[foryou] deezer chart:", e)
    return out


def _artist_id(name):
    from track_identity import similarity
    j = _get("https://api.deezer.com/search/artist", q=name, limit=5)
    best, bs = None, 0.0
    for d in j.get("data") or []:
        sc = similarity(name.lower(), (d.get("name") or "").lower())
        if sc > bs:
            best, bs = d, sc
    return (best or {}).get("id") if bs >= 0.8 else None


def fetch_recs(tt: dict, seeds_n=6) -> dict:
    import concurrent.futures as cf
    owned, owned_art = tt["owned"], tt["owned_artists"]
    fb_art = tt.get("fb_art") or {}
    from artist_identity import ident as _ident
    seeds = [a for a, _ in tt["now"][:3]]
    for a, _ in tt["top"]:
        if len(seeds) >= seeds_n:
            break
        if a not in seeds:
            seeds.append(a)

    def seed_work(a):
        aid = _artist_id(a)
        if not aid:
            return a, None, [], []
        rel = (_get(f"https://api.deezer.com/artist/{aid}/related", limit=12).get("data") or [])
        top = (_get(f"https://api.deezer.com/artist/{aid}/top", limit=10).get("data") or [])
        return a, aid, rel, top

    cand, more = {}, []
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for fut in [ex.submit(seed_work, a) for a in seeds]:
            try:
                a, aid, rel, top = fut.result(timeout=25)
            except Exception as e:                         # noqa: BLE001
                print("[foryou] seed:", e)
                continue
            w = 1.0 / (1 + seeds.index(a) * 0.35)
            for rank, d in enumerate(rel):
                nm = d.get("name") or ""
                from artist_identity import ident
                if not nm or ident(nm) in owned_art or fb_art.get(ident(nm), 0) <= -2:
                    continue
                e = cand.setdefault(nm, {"name": nm, "id": d.get("id"), "pic": d.get("picture_medium") or "",
                                         "fans": int(d.get("nb_fan") or 0), "score": 0.0, "because": []})
                e["score"] += w / (1 + rank * 0.15) * (1 + 0.35 * max(0.0, fb_art.get(ident(nm), 0)))
                if a not in e["because"]:
                    e["because"].append(a)
            for d in top:                                  # «ещё от ваших исполнителей»
                tr = _dz_track(d, a)
                if fb_art.get(_ident(_main_artist(tr["artist"])), 0) <= -2:
                    continue
                if (_norm(_main_artist(tr["artist"])), _norm(tr["title"])) not in owned:
                    more.append(tr)
    # по очереди от каждого вашего исполнителя, чтобы один не забивал весь список
    ranked = sorted(cand.values(), key=lambda e: (-e["score"], -e["fans"]))
    by_seed = {}
    for e in ranked:
        by_seed.setdefault(e["because"][0], []).append(e)
    artists = _round_robin([by_seed[a] for a in seeds if a in by_seed])[:14]

    def top_of(e):
        try:
            data = _get(f"https://api.deezer.com/artist/{e['id']}/top", limit=2).get("data") or []
            return [_dz_track(d, "похож на " + e["because"][0]) for d in data]
        except Exception:                                  # noqa: BLE001
            return []
    tracks = []
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for res in ex.map(top_of, artists[:10]):
            tracks += res

    genres = []
    seen = {(_norm(t["artist"]), _norm(t["title"])) for t in tracks + more}
    for gid, gname, share in tt["genres"][:3]:
        if share * (tt.get("genre_w") or {}).get(gname, 1.0) < 0.08:
            continue
        try:
            data = _get(f"https://api.deezer.com/chart/{gid}/tracks", limit=40).get("data") or []
        except Exception:                                  # noqa: BLE001
            continue
        gt = []
        for d in data:
            tr = _dz_track(d, gname)
            k = (_norm(_main_artist(tr["artist"])), _norm(tr["title"]))
            if k in owned or k in seen:
                continue
            seen.add(k)
            gt.append(tr)
        if gt:
            genres.append({"id": gid, "name": gname, "share": share, "tracks": gt[:16]})
    return {"artists": [{"name": e["name"], "pic": e["pic"], "because": e["because"][:2]} for e in artists],
            "tracks": _mix_by_artist(tracks)[:24], "more": _mix_by_artist(more)[:24], "genres": genres, "seeds": seeds}


def _round_robin(groups):
    out, groups = [], [list(g) for g in groups]
    while any(groups):
        for g in groups:
            if g:
                out.append(g.pop(0))
    return out


def _mix_by_artist(tracks):
    """Треки разных исполнителей вперемешку, а не пачками."""
    by = {}
    for t in tracks:
        by.setdefault(_main_artist(t["artist"]).lower(), []).append(t)
    return _round_robin(by.values())


# ══════════════════════════════════════════════════════════════════════════ #
#  Кэш
# ══════════════════════════════════════════════════════════════════════════ #

def load_cache() -> dict:
    try:
        d = json.loads(CACHE.read_text("utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:                                      # noqa: BLE001
        return {}


def save_cache(d: dict):
    try:
        tmp = CACHE.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), "utf-8")
        tmp.replace(CACHE)
    except Exception as e:                                 # noqa: BLE001
        print("[foryou] cache:", e)


def seeds_sig(tt: dict) -> str:
    return "|".join(sorted(a for a, _ in tt["top"][:6])) + f"#{tt.get('fb_rev', 0)}"


def stale(cache: dict, tt: dict) -> tuple[bool, bool]:
    """(тренды устарели, рекомендации устарели)."""
    now = time.time()
    tr = cache.get("trends") or {}
    rc = cache.get("recs") or {}
    return (now - float(tr.get("ts", 0)) > TRENDS_TTL,
            now - float(rc.get("ts", 0)) > RECS_TTL or rc.get("sig") != seeds_sig(tt))


def refresh(tt: dict, want_trends: bool, want_recs: bool) -> dict:
    """Сеть (вызывать в фоне): обновить устаревшее, сохранить, вернуть весь кэш."""
    cache = load_cache()
    if want_trends:
        t = fetch_trends()
        if t["ru"] or t["world"]:
            cache["trends"] = {"ts": int(time.time()), "data": t}
    if want_recs:
        r = fetch_recs(tt)
        if r["artists"] or r["tracks"] or r["more"]:
            cache["recs"] = {"ts": int(time.time()), "sig": seeds_sig(tt), "data": r}
    save_cache(cache)
    return cache
