# net_core.py
"""
Echoes.NET — соцсеть внутри ECHOES без серверов: только компьютеры друзей и сеть Tor.

Личность = ключ ed25519 (~/Echoes/net/identity.key). Из него же сделан onion-адрес
(как у Tor: base32(ключ + контрольная сумма + версия)), поэтому «код друга» — это и адрес,
по которому до него достучаться, и открытый ключ, которым проверяются его подписи.
Подделать чужой адрес нельзя, сервер регистрации не нужен.

Протокол — строки JSON поверх TCP через Tor (onion:80 → 127.0.0.1:порт плеера):

    клиент → {"t":"knock","v":1}      (первым всегда говорит клиент — иначе Tor теряет данные сервера)
    сервер → {"t":"hello","v":1,"onion":…,"nonce":…}
    клиент → {"t":"auth","onion":…,"sig":подпись("echoes-net-v1|<onion сервера>|<nonce>")}

После этого стороны равноправны:
    hi        — имя, о себе, что сейчас играет, открыта ли комната (присутствие);
    friend_req / friend_ok — заявка и её принятие (до дружбы больше ничего не принимается);
    msg / ack — личные сообщения (неотправленное ждёт в базе и уходит при следующей встрече);
    sync / posts / post_new / post_upd / post_del — лента: посты хранит и раздаёт автор,
                вместе с тредом (комментарии и голоса — каждый подписан тем, кто его оставил);
    vote / comment / react — отправляются АВТОРУ поста, он хранит тред и рассылает обновление друзьям
                (react: эмодзи, выбор в баттле, «угадал» в «Угадай трек»; типы постов — POST_KINDS, net_music);
    room_* / ping / pong — «Слушать вместе»: хост рассылает трек, позицию и своё время,
                гость синхронизирует часы (ping/pong, минимальная задержка) и догоняет.

Модуль без Qt: NetNode живёт в своём потоке с asyncio, интерфейс получает события через
on_event(kind, data) — из сетевого потока (net_page переводит их в сигнал Qt).

Отладка без Tor: ECHOES_NET_DEV=<папка> — узлы слушают 127.0.0.1 и находят друг друга
через <папка>/registry.json (два плеера с разными USERPROFILE на одном компьютере).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import secrets
import threading
import time
from pathlib import Path

from net_store import Store
from net_tor import TorManager, TorError, socks_connect, LINE_LIMIT

PROTO = 1
MAX_TEXT = 4000
MAX_NAME = 40
KEEPALIVE = 30
DEAD_AFTER = 100
FEED_SHARE = 60                # сколько своих последних постов отдаём другу при синхронизации
MAX_POST_RAW = 96 * 1024       # пост целиком (плейлист до 50 треков, репост) — не больше
POST_KINDS = ("post", "battle", "playlist", "quiz", "quote", "repost", "daily", "mod", "thread", "chal")
THREAD_FLAIRS = ("Обсуждение", "Вопрос", "Музыка", "Подборка", "Новинки", "Мемы", "Помощь")
EMOJI = ("🔥", "🎧", "😭", "💀", "🤯", "❤️")
def npk_ok(npk) -> bool:
    return isinstance(npk, str) and len(npk) == 64 and all(c in "0123456789abcdefABCDEF" for c in npk)


REQ_DAYS = 30                                                  # сколько дней заявка ждёт на релеях


def _req_tag(onion: str) -> str:
    """Метка заявок для кода: по ней адресат находит свои заявки на релеях (сам код не раскрывается)."""
    return "echoes-req-" + hashlib.sha256(("echoes-req|" + onion).encode()).hexdigest()[:24]


MSG_KINDS = ("text", "moment", "capsule", "invite", "lyric", "cpl", "file", "gif", "playlist", "gift")
PLAYLIST_MAX = 100                                             # треков в плейлисте-сообщении
CHUNK = 48 * 1024                # кусок файла в одном сообщении (base64 ~64 КБ)
MAX_AVATAR = 60 * 1024          # аватарка в профиле (base64 JPEG ~160 px)
MAX_GROUP = 10                  # участников в групповом чате
VOICE_MAX = 6000                # один кадр голоса (μ-law 8 кГц, ~0.2 с) в base64
DEV_DIR = os.environ.get("ECHOES_NET_DEV", "")


# ══════════════════════════════════════════════════════════════════════════ #
#  Личность: ed25519 + onion-адрес из того же ключа
# ══════════════════════════════════════════════════════════════════════════ #

def onion_from_pub(pub: bytes) -> str:
    ver = b"\x03"
    chk = hashlib.sha3_256(b".onion checksum" + pub + ver).digest()[:2]
    return base64.b32encode(pub + chk + ver).decode().lower()


def pub_from_onion(onion: str) -> bytes | None:
    onion = normalize_code(onion)
    if not onion:
        return None
    raw = base64.b32decode(onion.upper())
    pub, chk, ver = raw[:32], raw[32:34], raw[34:]
    if ver != b"\x03" or hashlib.sha3_256(b".onion checksum" + pub + ver).digest()[:2] != chk:
        return None
    return pub


def normalize_code(code: str) -> str:
    """«echoes:abc….onion», просто адрес, с пробелами — к 56 символам base32 или ''."""
    s = (code or "").strip().lower()
    for pre in ("echoes:", "echoes.net:", "http://", "https://"):
        if s.startswith(pre):
            s = s[len(pre):]
    s = s.split("/")[0].replace(".onion", "").replace(" ", "").replace("-", "")
    if len(s) != 56 or any(ch not in "abcdefghijklmnopqrstuvwxyz234567" for ch in s):
        return ""
    return s


def canon(obj: dict) -> bytes:
    return json.dumps({k: v for k, v in obj.items() if k != "sig"}, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def verify(onion: str, data: bytes, sig_b64: str) -> bool:
    try:
        from Cryptodome.Signature import eddsa
        pub = pub_from_onion(onion)
        if pub is None:
            return False
        eddsa.new(eddsa.import_public_key(pub), "rfc8032").verify(data, base64.b64decode(sig_b64))
        return True
    except Exception:                                          # noqa: BLE001
        return False


def verify_obj(obj: dict, who_field: str) -> bool:
    return isinstance(obj, dict) and verify(str(obj.get(who_field, "")), canon(obj), str(obj.get("sig", "")))


class Identity:
    def __init__(self, seed: bytes):
        from Cryptodome.PublicKey import ECC
        from Cryptodome.Signature import eddsa
        self.seed = seed
        self._key = ECC.construct(curve="Ed25519", seed=seed)
        self._signer = eddsa.new(self._key, "rfc8032")
        self.pub = self._key.public_key().export_key(format="raw")
        self.onion = onion_from_pub(self.pub)

    @classmethod
    def load_or_create(cls, path: Path) -> "Identity":
        try:
            seed = base64.b64decode(json.loads(path.read_text(encoding="utf-8"))["seed"])
            if len(seed) == 32:
                return cls(seed)
        except (OSError, ValueError, KeyError):
            pass
        seed = secrets.token_bytes(32)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"v": 1, "seed": base64.b64encode(seed).decode()}), encoding="utf-8")
        return cls(seed)

    def sign(self, data: bytes) -> str:
        return base64.b64encode(self._signer.sign(data)).decode()

    def sign_obj(self, obj: dict) -> dict:
        obj = dict(obj)
        obj["sig"] = self.sign(canon(obj))
        return obj

    def tor_key(self) -> str:
        """Ключ для ADD_ONION: «расширенный» ed25519 (SHA-512 от seed, с зажатыми битами)."""
        h = bytearray(hashlib.sha512(self.seed).digest())
        h[0] &= 248
        h[31] &= 127
        h[31] |= 64
        return base64.b64encode(bytes(h)).decode()


def clip(s, n=MAX_TEXT) -> str:
    return str(s or "")[:n]


def clean_track(t) -> dict | None:
    """Трек в сообщении/посте/комнате: только описание — никаких путей к файлам на диске."""
    if not isinstance(t, dict):
        return None
    out = {"artist": clip(t.get("artist"), 200), "title": clip(t.get("title"), 300),
           "album": clip(t.get("album"), 200)}
    try:
        out["duration"] = max(0, min(36000, int(float(t.get("duration") or 0))))
    except (TypeError, ValueError, OverflowError):
        out["duration"] = 0
    from urllib.parse import urlsplit
    url = str(t.get("url") or "")
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme == "https" and any(host == h or host.endswith("." + h)
                                              for h in ("youtube.com", "youtu.be", "soundcloud.com")):
            out["url"] = url[:300]
    except ValueError:
        pass
    th = str(t.get("thumb_url") or t.get("cover_url") or "")
    if th.startswith("https://"):
        out["thumb_url"] = th[:400]
    return out if (out["title"] or out["artist"]) else None


def clean_sec(v, hi=36000.0) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, 1) if 0 <= f <= hi else None


def clean_taste(t) -> dict | None:
    """Вкус друга: веса исполнителей (0..1) и его любимые треки — для совместимости и Blend."""
    if not isinstance(t, dict):
        return None
    arts = {}
    for k, v in list((t.get("artists") or {}).items())[:60]:
        try:
            arts[clip(k, 80)] = max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            pass
    tracks = [x for x in (clean_track(x) for x in (t.get("tracks") or [])[:30]) if x]
    out = {"artists": arts, "tracks": tracks}
    gen = {}
    for k, v in list((t.get("genres") or {}).items())[:30] if isinstance(t.get("genres"), dict) else []:
        try:
            gen[clip(k, 30)] = max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            pass
    if gen:
        out["genres"] = gen
    try:
        if t.get("n") is not None:
            out["n"] = max(0, min(10 ** 6, int(t.get("n"))))
    except (TypeError, ValueError):
        pass
    return out


def clean_extra(e) -> dict:
    """Особые сообщения: момент трека, капсула времени, приглашение в комнату, строчка песни."""
    if not isinstance(e, dict) or e.get("kind") not in MSG_KINDS:
        return {}
    out = {"kind": e["kind"]}
    if clean_sec(e.get("at")) is not None:
        out["at"] = clean_sec(e.get("at"))
    if e["kind"] == "capsule":
        try:
            out["unlock"] = min(float(e.get("unlock")), time.time() + 366 * 86400)
        except (TypeError, ValueError):
            return {}
    if e["kind"] == "invite":
        out["room"] = clip(e.get("room"), 80)
    if e["kind"] == "lyric":
        out["line"] = clip(e.get("line"), 300)
    if e["kind"] == "gif":                                     # GIF: только ссылка на CDN Tenor/Giphy
        from net_gif import clean_gif
        g = clean_gif(e.get("gif"))
        if not g:
            return {}
        out["gif"] = g
    if e["kind"] == "file":                                    # файл: описание + превью (net_files)
        from net_files import clean_meta
        fm = clean_meta(e.get("file"))
        if not fm:
            return {}
        out["file"] = fm
    if e["kind"] == "playlist":                                # плейлист: название + треки (только описания)
        tr = [x for x in (clean_track(x) for x in (e.get("tracks") or [])[:PLAYLIST_MAX]) if x]
        if not tr:
            return {}
        for x in tr:
            x.pop("thumb_url", None)                           # обложки ищутся у себя — сообщение меньше
        out["title"] = clip(e.get("title"), 120).strip() or "Плейлист"   # не name: в группе name — автор
        out["tracks"] = tr
    if e["kind"] == "gift":                                    # подарок: рамка / витрина / трек дня (net_gifts)
        from net_gifts import clean as clean_gift
        g = clean_gift(e.get("gift"))
        if not g:
            return {}
        out["gift"] = g
    if e["kind"] == "cpl":                                     # правка общего плейлиста чата
        if e.get("op") not in ("add", "del"):
            return {}
        out["op"] = e["op"]
        out["ref"] = clip(e.get("ref"), 64)
    return out


def clean_mod(m) -> dict | None:
    """Мод (тема ECHOES) в посте/витрине: версия, иконка (JPEG), файл темы и до 4 скриншотов."""
    from net_files import clean_meta
    if not isinstance(m, dict):
        return None
    if m.get("type") in ("frame", "showcase"):                # рамка / витрина из магазина (net_market)
        from net_market import clean_deco_mod
        return clean_deco_mod(m)
    pkg = clean_meta(m.get("pkg"))
    if not pkg or not pkg["name"].lower().endswith(".echoestheme"):
        return None
    out = {"version": clip(m.get("version"), 20), "pkg": pkg, "theme": clip(m.get("theme"), 80),
           "mid": clip(m.get("mid"), 20),
           "shots": [x for x in (clean_meta(f) for f in (m.get("shots") or [])[:4]) if x and x["kind"] == "image"]}
    ic = m.get("icon")
    if isinstance(ic, str) and len(ic) <= 40000:
        try:
            if base64.b64decode(ic)[:3] == b"\xff\xd8\xff":
                out["icon"] = ic
        except ValueError:
            pass
    return out


def _int(v, hi=10 ** 9) -> int:
    try:
        return max(0, min(hi, int(float(v))))
    except (TypeError, ValueError, OverflowError):
        return 0


def clean_lt(x) -> dict | None:
    """Время прослушивания (как вкладка у себя): всего, сегодня, за 7 дней, запуски, топ исполнителей и треков."""
    if not isinstance(x, dict):
        return None
    arts = [[clip(a[0], 200), _int(a[1]), _int(a[2])] for a in (x.get("arts") or [])[:10]
            if isinstance(a, list) and len(a) >= 3 and isinstance(a[0], str)]
    trs = [[clip(a[0], 300), clip(a[1], 200), _int(a[2]), _int(a[3])] for a in (x.get("trs") or [])[:20]
           if isinstance(a, list) and len(a) >= 4 and isinstance(a[0], str)]
    wtrs = [[clip(a[0], 300), clip(a[1], 200), _int(a[2])] for a in (x.get("wtrs") or [])[:15]
            if isinstance(a, list) and len(a) >= 3 and isinstance(a[0], str)]
    return {"total": _int(x.get("total")), "today": _int(x.get("today")), "week": _int(x.get("week")),
            "plays": _int(x.get("plays")), "arts": arts, "trs": trs, "wtrs": wtrs}


def clean_pls(x) -> list:
    """Открытые плейлисты профиля: название, описание, маленькая обложка (JPEG), до 60 треков."""
    out = []
    for pl in (x if isinstance(x, list) else [])[:6]:
        if not isinstance(pl, dict):
            continue
        name = clip(pl.get("name"), 100).strip()
        if not name:
            continue
        tr = [t for t in (clean_track(t) for t in (pl.get("tracks") or [])[:60]) if t]
        d = {"name": name, "desc": clip(pl.get("desc"), 300), "n": _int(pl.get("n"), 100000) or len(tr),
             "tracks": tr}
        cv = pl.get("cover")
        if isinstance(cv, str) and len(cv) <= 12000:
            try:
                if base64.b64decode(cv)[:3] == b"\xff\xd8\xff":
                    d["cover"] = cv
            except ValueError:
                pass
        out.append(d)
    return out


def _num(v, lo=0.0, hi=1e10) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return f if lo <= f <= hi else 0.0


def clean_spl(m) -> dict:
    """Совместный плейлист: только известные поля и размеры."""
    ents = []
    for e in (m.get("entries") or [])[:400] if isinstance(m.get("entries"), list) else []:
        if not isinstance(e, dict):
            continue
        meta = clean_track(e.get("meta"))
        if not meta or not e.get("id"):
            continue
        ents.append({"id": clip(e.get("id"), 24), "meta": meta, "by": clip(e.get("by"), 80),
                     "pos": _num(e.get("pos"), 0, 1e6), "ts": _num(e.get("ts")), "del": _num(e.get("del"))})
    return {"t": m.get("t"), "pid": clip(m.get("pid"), 24), "name": clip(m.get("name"), 100),
            "owner": clip(m.get("owner"), 80), "inviter": clip(m.get("inviter"), MAX_NAME),
            "members": [clip(x, 80) for x in (m.get("members") or [])[:16] if isinstance(x, str)],
            "entries": ents}


def clean_quiz(m) -> dict:
    """Сообщение игры «Угадай трек вместе»: только известные поля и размеры."""
    out = {"t": m.get("t"), "gid": clip(m.get("gid"), 24), "n": int(clean_sec(m.get("n"), 1000) or 0)}
    for k in ("name", "owner", "who", "text"):
        if m.get(k) is not None:
            out[k] = clip(m.get(k), 120)
    for k in ("total", "secs", "pts", "sec"):
        if m.get(k) is not None:
            out[k] = float(clean_sec(m.get(k), 100000) or 0)
    if m.get("track") is not None:
        out["track"] = clean_track(m.get("track"))
    if isinstance(m.get("pool"), list):
        out["pool"] = [x for x in (clean_track(t) for t in m["pool"][:60]) if x]
    for k in ("players", "scores"):
        if isinstance(m.get(k), dict):
            out[k] = {clip(o, 80): ([clip(v[0], MAX_NAME), float(clean_sec(v[1], 10 ** 6) or 0)]
                                    if isinstance(v, list) and len(v) >= 2 else clip(v, MAX_NAME))
                      for o, v in list(m[k].items())[:12]}
    out["offline"] = bool(m.get("offline"))
    return out


def clean_profile(p) -> dict | None:
    """Профиль друга: статус, «о себе», любимые треки, тирлист, ачивки, аватарка (JPEG base64)."""
    if not isinstance(p, dict):
        return None
    out = {"name": clip(p.get("name"), MAX_NAME), "status": clip(p.get("status"), 120),
           "about": clip(p.get("about"), 1500),
           "fav": [x for x in (clean_track(t) for t in (p.get("fav") or [])[:8]) if x],
           "ach": [clip(a, 40) for a in (p.get("ach") or [])[:40] if isinstance(a, str)],
           "follows": [clip(a, 80) for a in (p.get("follows") or [])[:40] if isinstance(a, str) and a.strip()],
           "stats": {k: int(clean_sec((p.get("stats") or {}).get(k), 10 ** 9) or 0)
                     for k in ("tracks", "listened", "friends", "posts", "quiz_wins", "quiz_best")}}
    tier = p.get("tier") if isinstance(p.get("tier"), dict) else {}
    tiers = []
    for tr in (tier.get("tiers") or [])[:8]:
        if not isinstance(tr, dict):
            continue
        col = str(tr.get("color") or "#888888")
        tiers.append({"name": clip(tr.get("name"), 20),
                      "color": col if len(col) == 7 and col.startswith("#") else "#888888",
                      "items": [x for x in (clean_track(t) for t in (tr.get("items") or [])[:20]) if x]})
    out["tier"] = {"tiers": tiers}
    lt = clean_lt(p.get("lt"))
    if lt:
        out["lt"] = lt
    pls = clean_pls(p.get("pls"))
    if pls:
        out["pls"] = pls
    try:                                                       # рамка, фон шапки, витрина (net_showcase)
        from net_showcase import clean_deco
        deco = clean_deco(p.get("deco"))
    except Exception:                                          # noqa: BLE001
        deco = None
    if deco:
        out["deco"] = deco
    try:                                                       # анимированная аватарка (GIF, ya_avanim)
        import ya_avanim
        if ya_avanim.ok_b64(p.get("avanim")):
            out["avanim"] = p["avanim"]
    except Exception:                                          # noqa: BLE001
        pass
    av = p.get("avatar")
    if isinstance(av, str) and len(av) <= MAX_AVATAR:
        try:
            raw = base64.b64decode(av)
            if raw[:3] == b"\xff\xd8\xff":                     # только JPEG
                out["avatar"] = av
        except ValueError:
            pass
    return out


TASTE_LIB_MIN, TASTE_LIB_MAX = 40, 4000   # коллекция меньше/больше — совместимость всегда маленькая


def _cos(A: dict, B: dict) -> float:
    common = set(A) & set(B)
    if not common:
        return 0.0
    dot = sum(A[k] * B[k] for k in common)
    na = sum(v * v for v in A.values()) ** 0.5
    nb = sum(v * v for v in B.values()) ** 0.5
    return min(1.0, dot / (na * nb)) if na and nb else 0.0


def taste_match(a: dict | None, b: dict | None) -> tuple[int, list[str]]:
    """Совместимость вкусов 0..100 %: в основном по жанрам (70 %), немного по исполнителям (30 %);
    у кого в коллекции совсем мало или слишком много треков — всегда небольшая. + общее (жанры, исполнители)."""
    if not a or not b:
        return 0, []
    A, B = a.get("artists") or {}, b.get("artists") or {}
    GA, GB = a.get("genres") or {}, b.get("genres") or {}
    acos = _cos(A, B)
    if GA and GB:
        score = 0.7 * _cos(GA, GB) + 0.3 * acos
    else:
        score = acos
    pct = int(round(100 * score))
    for lib in (a.get("n"), b.get("n")):
        if isinstance(lib, int) and not TASTE_LIB_MIN <= lib <= TASTE_LIB_MAX:
            pct = min(pct, 6 + int(6 * score))                 # мало/много музыки — вкус не понять
    common_g = sorted(set(GA) & set(GB), key=lambda k: -(GA[k] * GB[k]))[:3]
    common_a = sorted(set(A) & set(B), key=lambda k: -(A[k] * B[k]))[:6]
    if pct <= 0 and not common_g and not common_a:
        return 0, []
    return max(1, pct), common_g + common_a


# ══════════════════════════════════════════════════════════════════════════ #
#  Соединение с одним собеседником
# ══════════════════════════════════════════════════════════════════════════ #

VIA_RANK = {"lan": 3, "direct": 2, "tor": 1, "dev": 1, "nostr": 0}   # каким путём соединение лучше (быстрее)
NOSTR_PART = 30000                 # больше — сообщение режется на части (релеи не любят большие события)
MOD_ACTS = ("hide", "unhide", "ban", "unban")
UPD_PUBLIC_TYPES = ("upd_man?", "upd_man", "upd_get", "upd_blob", "upd_err", "upd_req", "upd_pc")
UPD_SERVE_MAX = 3                  # одновременно отдаём обновление не больше стольким
UPD_STALL = 75                     # обновление: столько секунд без кусков — докачать недостающие
UPD_TRIES = 6
SUB_MAX = 300                      # на скольких авторов можно подписаться
PRESENCE_SKEW = 3 * 3600            # насколько могут расходиться часы у друзей
NOSTR_PEER_IDLE = 210              # нет «сердцебиения» друга 3.5 мин — считаем, что он ушёл
NOSTR_STRANGER_IDLE = 600          # незнакомец (гость/хост публичной комнаты) без сообщений 10 мин
NOSTR_P2P_MAX_AGE = 600            # старые (из истории релея) сообщения связи не исполняем
PRESENCE_EVERY = 60
PRESENCE_FUTURE_TOLERANCE = 60     # tolerate small clock drift, never replay hours of relay history as live
NOSTR_FILE_MAX = 2 * 2 ** 20       # файлы через Nostr — до 2 МБ (фото); больше — только через Tor или напрямую
UDP_TYPES = ("voice", "room_state", "room_chat", "room_say", "room_ka", "ping", "pong", "room_join", "room_leave",
             "vc", "call_state", "upd_req", "upd_err")              # обновления: просьбы о кусках — мимо релеев
QUIZ_TYPES = ("quiz_inv", "quiz_join", "quiz_no", "quiz_start", "quiz_round", "quiz_ans", "quiz_hit",
              "quiz_reveal", "quiz_end", "quiz_leave", "quiz_ready")          # «Угадай трек вместе» (net_quiz_live)
CALL_TYPES = ("call_ring", "call_join", "call_here", "call_leave", "call_decline", "call_state", "vc")
CALL_RING_FOR = 45                 # звонок звонит столько секунд
VOICE_FRAMES_MAX = 6


class Peer:
    def __init__(self, onion, reader, writer, outbound, via="tor"):
        self.onion = onion
        self.via = via
        self.r, self.w = reader, writer
        self.outbound = outbound
        self.last_rx = time.time()
        self._last_rx_mono = time.monotonic()
        self.alive = True

    async def send(self, obj: dict):
        if not self.alive:
            return
        try:
            self.w.write((json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
            await self.w.drain()
        except (OSError, RuntimeError, ConnectionError):
            self.close()

    def close(self):
        self.alive = False
        try:
            self.w.close()
        except Exception:                                      # noqa: BLE001
            pass


class NostrPeer:
    """Связь с собеседником через релеи Nostr — когда Tor и прямые пути не проходят (у многих Tor режут).
    Для остального кода это обычное соединение: те же сообщения (hi, посты, сообщения, группы, комнаты,
    профиль, файлы до 16 МБ), только каждое уходит зашифрованным ключом пары событием Nostr (большие —
    частями). Живое, пока приходит «сердцебиение» друга (раз в минуту) или его сообщения."""

    SKIP = ("ka", "bye", "voice", "vc", "ping", "pong")              # бессмысленно / слишком часто для релеев

    def __init__(self, node, onion, npk):
        self.node, self.onion, self.npk = node, onion, npk
        self.via = "nostr"
        self.outbound = False
        self.last_rx = time.time()
        self._last_rx_mono = time.monotonic()
        self._presence_confirmed = False  # an outbound relay mailbox is not proof the recipient is online
        self.alive = True
        self.r = self.w = None
        self._last = {}                                        # тип → (ключ, время, позиция) последней отправки

    def _throttled(self, obj) -> bool:
        """Релеи банят за частые события: «hi» — только если изменился (или раз в 2 мин), состояние комнаты —
        при смене трека/паузы/перемотке и раз в 30 с (позицию гость досчитывает сам по времени хоста)."""
        t = obj.get("t")
        now = time.time()
        if t == "hi":
            key = json.dumps({k: v for k, v in obj.items() if k != "direct"}, sort_keys=True, ensure_ascii=False)
            last = self._last.get(t)
            if last and last[0] == key and now - last[1] < 120:
                return True
            self._last[t] = (key, now, 0)
        elif t == "room_state":
            st = obj.get("state") or {}
            key = json.dumps([(st.get("track") or {}).get("title"), (st.get("track") or {}).get("artist"),
                              bool(st.get("playing")), st.get("members"),
                              (st.get("radio") or {}).get("revision"), (st.get("radio") or {}).get("current"),
                              'queue' in (st.get('radio') or {})], ensure_ascii=False)
            pos = float(st.get("pos") or 0)
            last = self._last.get(t)
            if last and last[0] == key and now - last[1] < 30:
                expect = last[2] + ((now - last[1]) if st.get("playing") else 0)
                if abs(expect - pos) < 3:
                    return True
            self._last[t] = (key, now, pos)
        return False

    async def send(self, obj: dict):
        if not self.alive or not isinstance(obj, dict):
            return
        t = obj.get("t")
        udp = getattr(self.node, "udp", None)
        if t in UDP_TYPES and udp is not None and udp.alive(self.onion) and udp.send(self.onion, obj):
            return                                             # живое — прямым UDP, мимо релеев
        if t in self.SKIP or self._throttled(obj):
            return
        try:
            await self.node._nostr_p2p(self.onion, self.npk, obj)
        except Exception as e:                                 # noqa: BLE001
            self.node.log(f"[net] nostr send {self.onion[:8]}: {type(e).__name__} {e}")

    def close(self):
        self.alive = False


async def _read_json(r, timeout):
    raw = await asyncio.wait_for(r.readline(), timeout)
    if not raw:
        raise ConnectionError("closed")
    obj = json.loads(raw.decode("utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("bad frame")
    return obj


# ══════════════════════════════════════════════════════════════════════════ #
#  Узел сети
# ══════════════════════════════════════════════════════════════════════════ #

class NetNode:
    def __init__(self, base: Path, on_event=None, log=print):
        self.base = Path(base)
        self.base.mkdir(parents=True, exist_ok=True)
        self.log = log
        self.on_event = on_event or (lambda k, d: None)
        self.settings_path = self.base / "net.json"
        self.settings = self._load_settings()
        self.me = Identity.load_or_create(self.base / "identity.key")
        self.store = Store(self.base / "net.db")
        self.tor = TorManager(self.base, self.settings, log)
        self.loop: asyncio.AbstractEventLoop | None = None
        self.cur_call = None                                       # текущий звонок (call_start / call_accept)
        self.rings = {}                                        # входящие звонки: cid → {from, kind, gid, title, ts}
        self.thread = None
        self.peers: dict[str, Peer] = {}
        self._dialing: set[str] = set()
        self._backoff: dict[str, tuple[float, float]] = {}       # onion → (следующая попытка, пауза)
        self.socks = 0
        self.local_port = 0
        self.state = {"phase": "off", "pct": 0, "text": "Сеть выключена", "online": False}
        self.now_playing = None
        self.game = ""                                         # «сейчас в игре» (net_game)
        self.public = {"posts": {}, "profiles": {}, "rooms": {}, "tastes": {}, "likes": {}, "replies": {}, "mods": {}}
        self.taste = None
        self.profile = None                                    # своя карточка профиля (net_page собирает)
        self.pv = ""                                           # её версия — друзья просят её, если изменилась
        self.avatar_dir = self.base / "avatars"
        self.files_dir = self.base / "files"
        self._incoming: dict[str, dict] = {}                   # fid → {"f": файл .part, "got": байт, …}
        self._streams: dict[str, int] = {}                     # сколько файлов сейчас отдаём каждому другу
        # комната: я хост → room_host = {...}; я гость → room_guest = onion хоста
        self.room_host = None
        self.room_members: set[str] = set()
        self.room_guest = None
        self.room_state = None
        self.room_chat: list[dict] = []
        self._clock: list[tuple[float, float]] = []                # (rtt, offset) — замеры часов хоста
        self._stop = False

    # ── настройки ── #

    def _load_settings(self) -> dict:
        d = {"name": "", "bio": "", "mode": "auto", "bridges": "", "tor_path": "", "autostart": False,
             "share_now": True, "last": ""}
        try:
            d.update(json.loads(self.settings_path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
        return d

    def save_settings(self):
        try:
            self.settings_path.write_text(json.dumps(self.settings, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError as e:
            self.log(f"[net] settings: {e}")

    @property
    def code(self) -> str:
        return "echoes:" + self.me.onion

    def emit(self, kind, data=None):
        try:
            self.on_event(kind, data)
        except Exception as e:                                 # noqa: BLE001
            self.log(f"[net] event {kind}: {e}")

    def _set_state(self, phase, pct=None, text=None, online=None):
        self.state["phase"] = phase
        if pct is not None:
            self.state["pct"] = pct
        if text is not None:
            if text != self.state.get("text") and phase != "tor":
                self.log(f"[net] {phase}: {text}")                 # в net.log — чтобы было видно, что со связью
            self.state["text"] = text
        if online is not None:
            self.state["online"] = online
        self.emit("status", dict(self.state))

    # ── поток и цикл ── #

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self._stop = False
        self._presence_leaving = False
        self.__dict__.pop('_presence_npks', None)
        self.__dict__.pop('_presence_leave_task', None)
        self.thread = threading.Thread(target=self._run, name="echoes-net", daemon=True)
        self.thread.start()

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._main())
        except Exception as e:                                 # noqa: BLE001
            self.log(f"[net] loop: {e}")
        finally:
            self.tor.stop()
            try:
                self.loop.close()
            except Exception:                                  # noqa: BLE001
                pass
            self.loop = None
            if self.state["phase"] not in ("no_tor", "error"):
                self._set_state("off", 0, "Сеть выключена", False)

    def stop(self):
        self._stop = True
        if self.loop:
            self.loop.call_soon_threadsafe(lambda: None)

    def shutdown(self, timeout=0.75):
        """Actual application exit: best-effort offline, with one bounded total deadline."""
        deadline = time.monotonic()+max(0., min(2., float(timeout)))
        loop = self.loop
        self.stop()
        if loop is not None and loop.is_running() and threading.current_thread() is not self.thread:
            try:
                task = asyncio.run_coroutine_threadsafe(self._presence_send(leaving=True), loop)
                task.result(timeout=max(0., deadline-time.monotonic()))
            except Exception:
                pass  # TTL remains authoritative if the relay is unreachable or the process is killed
        thread = self.thread
        if thread is not None and thread is not threading.current_thread() and thread.is_alive():
            thread.join(timeout=max(0., deadline-time.monotonic()))

    def call(self, fn, *args, **kw):
        """Из потока интерфейса: выполнить в сетевом цикле (корутина или обычная функция)."""
        loop = self.loop
        if loop is None:
            return
        if asyncio.iscoroutinefunction(fn):
            asyncio.run_coroutine_threadsafe(fn(*args, **kw), loop)
        else:
            loop.call_soon_threadsafe(lambda: fn(*args, **kw))

    async def _main(self):
        self._t_start = time.time()
        server = await asyncio.start_server(self._on_incoming, "127.0.0.1", 0, limit=LINE_LIMIT)
        self.local_port = server.sockets[0].getsockname()[1]
        self.transports = {"tor": False, "direct": "", "nostr": 0}
        try:
            if self.settings.get("direct", True):
                try:
                    await self._start_direct()
                except Exception as e:                         # noqa: BLE001
                    self.log(f"[net] direct: {e}")
            if self.settings.get("udp", True):
                try:
                    from net_udp import UdpLink
                    self.udp = UdpLink(self)
                    await self.udp.start(int(self.settings.get("udp_port") or 0))
                except Exception as e:                         # noqa: BLE001
                    self.udp = None
                    self.log(f"[net] udp: {type(e).__name__} {e}")
            if self.settings.get("nostr", True) and (not DEV_DIR or self.settings.get("relays")):
                asyncio.ensure_future(self._nostr_start())
            if DEV_DIR:
                self._dev_register()
                self.transports["tor"] = True
                self._set_state("online", 100, "Тестовая сеть (без Tor)", True)
            elif not self.settings.get("use_tor", True) or self.tor.find_tor() is None:
                if not self.transports["direct"] and not self.settings.get("nostr", True):
                    self._set_state("no_tor", 0, "Нужен Tor — скачайте его в разделе «Сеть»", False)
                    return
                self._set_state("online", 100, self._status_text(), True)
            else:
                self._set_state("tor", 0, "Запускаю Tor…", False)
                try:
                    self.socks = await self.tor.start(lambda p, t: self._set_state("tor", p, t, False))
                    self.save_settings()
                    self._set_state("onion", 100, "Публикую ваш адрес в сети Tor…", False)
                    sid = await self.tor.add_onion(self.me.tor_key(), self.local_port)
                    if sid != self.me.onion:
                        self.log(f"[net] onion mismatch {sid} != {self.me.onion}")
                    self.transports["tor"] = True
                except TorError as e:
                    if not self.transports["direct"] and not self.settings.get("nostr", True):
                        self._set_state("error", 0, str(e), False)
                        return
                    self.log(f"[net] tor: {e} — остаются прямые соединения и Nostr")
                self._set_state("online", 100, self._status_text(), True)
            if self.room_host is not None and self.room_host.get('station') is not None:
                task = self.__dict__.get('_radio_task')
                if task is None or task.done():
                    self._radio_task = asyncio.create_task(self._radio_loop())
            while not self._stop:
                await self._maintain()
                for _ in range(10):
                    if self._stop:
                        break
                    await asyncio.sleep(1)
        finally:
            task = self.__dict__.pop('_radio_task', None)
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            for p in list(self.peers.values()):
                await p.send({"t": "bye"})
                p.close()
            self.peers.clear()
            server.close()
            await self._stop_direct()
            if getattr(self, "udp", None) is not None:
                self.udp.close()
                self.udp = None
            nos = getattr(self, "nostr", None)
            if nos is not None:
                try:                                           # друзья сразу увидят «не в сети»
                    if nos.up_count:
                        await asyncio.wait_for(self._presence_send(leaving=True), 3)
                except Exception:                              # noqa: BLE001
                    pass
                await nos.close()

    def _dev_register(self):
        reg = Path(DEV_DIR) / "registry.json"
        reg.parent.mkdir(parents=True, exist_ok=True)
        try:
            d = json.loads(reg.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        d[self.me.onion] = self.local_port
        reg.write_text(json.dumps(d), encoding="utf-8")

    def _direct_cands(self, onion) -> list:
        """Куда стучаться напрямую: маячок в LAN (свежий), адреса из «hi» друга (LAN → IPv6 → внешний IPv4)."""
        out = []
        lan = self.__dict__.get("_lan", {}).get(onion)
        if lan and time.time() - lan[2] < 90:
            out.append((lan[0], lan[1], "lan"))
        if self.settings.get("direct", True):
            try:
                for ip, port in json.loads((self.store.contact(onion) or {}).get("direct") or "[]")[:6]:
                    from net_direct import is_private
                    out.append((str(ip), int(port), "lan" if is_private(ip) else "direct"))
            except (ValueError, TypeError):
                pass
        return out

    async def _open(self, onion, direct_only=False):
        """Соединение с другом: все прямые адреса сразу (кто первый ответит), иначе — через Tor."""
        cands = self._direct_cands(onion)
        if cands:
            async def one(ip, port, via):
                r, w = await asyncio.wait_for(asyncio.open_connection(ip, port, limit=LINE_LIMIT), 4)
                return r, w, via
            tasks = [asyncio.ensure_future(one(*c)) for c in cands]
            try:
                for fut in asyncio.as_completed(tasks):
                    try:
                        res = await fut
                    except (OSError, asyncio.TimeoutError):
                        continue
                    for t in tasks:
                        if not t.done():
                            t.cancel()
                    return res
            finally:
                for t in tasks:
                    if not t.done():
                        t.cancel()
        if direct_only:
            raise ConnectionError("no direct route")
        if DEV_DIR:
            d = json.loads((Path(DEV_DIR) / "registry.json").read_text(encoding="utf-8"))
            if onion not in d:
                raise ConnectionError("not online")
            r, w = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", d[onion], limit=LINE_LIMIT), 5)
            return r, w, "dev"
        if not self.transports.get("tor"):
            raise ConnectionError("Tor выключен, прямого пути нет")
        r, w = await socks_connect(self.socks, onion + ".onion", 80)
        return r, w, "tor"

    # ── прямые соединения (net_direct) ── #

    async def _start_direct(self):
        import random
        from net_direct import lan_ipv4, global_ipv6, upnp_map, start_beacon
        port = int(self.settings.get("direct_port") or random.randint(41000, 59000))
        srv = None
        for attempt in range(6):
            try:
                srv = await asyncio.start_server(lambda r, w: self._on_incoming(r, w, "direct"), "0.0.0.0", port,
                                                 limit=LINE_LIMIT)
                break
            except OSError:
                port = random.randint(41000, 59000)
        if srv is None:
            return
        self._direct_srv = [srv]
        try:
            self._direct_srv.append(await asyncio.start_server(lambda r, w: self._on_incoming(r, w, "direct"),
                                                               "::", port, limit=LINE_LIMIT))
        except OSError:
            pass
        self.settings["direct_port"] = port
        self.save_settings()
        self.direct_port = port
        lan = lan_ipv4()
        cands = [[ip, port] for ip in lan] + [[ip, port] for ip in global_ipv6()]
        kinds = ["LAN"] if lan else []
        if cands[len(lan):]:
            kinds.append("IPv6")
        self.direct_cands = cands
        self.transports["direct"] = " + ".join(kinds) or "LAN"
        if self.settings.get("lan", True):
            try:
                self._beacon = await start_beacon(asyncio.get_running_loop(), self.me.onion, port, self._on_lan_peer)
            except OSError as e:
                self.log(f"[net] lan beacon: {e}")
        if self.settings.get("upnp", True) and lan and not DEV_DIR:
            async def upnp():
                try:
                    res = await asyncio.get_running_loop().run_in_executor(None, upnp_map, port, lan[0])
                except Exception as e:                         # noqa: BLE001
                    res = None
                    self.log(f"[net] upnp: {e}")
                if res:
                    ext, eport, url, svc = res
                    self._upnp = (url, svc, eport)
                    self.direct_cands.append([ext, eport])
                    self.transports["direct"] += " + UPnP"
                    self._set_state("online", 100, self._status_text(), True)
                    await self._broadcast_friends(self._hi())
            asyncio.ensure_future(upnp())

    async def _stop_direct(self):
        for srv in self.__dict__.get("_direct_srv", []):
            srv.close()
        b = self.__dict__.get("_beacon")
        if b is not None and b.transport is not None:
            b.transport.close()
        up = self.__dict__.get("_upnp")
        if up:
            from net_direct import upnp_unmap
            await asyncio.get_running_loop().run_in_executor(None, upnp_unmap, up[0], up[1], up[2])

    def _on_lan_peer(self, onion, ip, port):
        if normalize_code(onion) != onion or not (0 < port < 65536):
            return
        self.__dict__.setdefault("_lan", {})[onion] = (ip, port, time.time())
        p = self.peers.get(onion)
        if (p is None or p.via == "tor") and self.is_friend(onion) and onion not in self._dialing:
            asyncio.ensure_future(self._dial(onion, direct_only=p is not None))

    def _status_text(self) -> str:
        tr = getattr(self, "transports", {})
        parts = []
        if tr.get("tor"):
            parts.append("Tor" if not DEV_DIR else "тест")
        if tr.get("direct"):
            parts.append(f"напрямую ({tr['direct']})")
        if tr.get("nostr"):
            parts.append(f"Nostr ({tr['nostr']})")
        return "В сети · " + " + ".join(parts) if parts else "Нет ни одного пути в сеть"

    # ── поддержание связей ── #

    async def _maintain(self):
        now = time.time()
        b = self.__dict__.get("_beacon")
        if b is not None:
            b.announce()
        for p in list(self.peers.values()):
            elapsed = time.monotonic()-p._last_rx_mono if hasattr(p, '_last_rx_mono') else now-p.last_rx
            if p.via == "nostr":
                idle = NOSTR_PEER_IDLE if self.is_friend(p.onion) else NOSTR_STRANGER_IDLE
                if not p.alive or elapsed >= idle:
                    self._drop(p)
                elif not self.udp_alive(p.onion) and now - getattr(p, "udp_offer_t", 0) > 180:
                    asyncio.ensure_future(self._udp_offer(p))
                continue
            if not p.alive or elapsed >= DEAD_AFTER:
                self._drop(p)
            elif elapsed > KEEPALIVE:
                await p.send({"t": "ka"})
        self._call_tick()
        if now-self.__dict__.get('_bugs_retry_t',0)>60:
            self._bugs_retry_t=now
            from net_bugs import pending_peers, deliver
            for peer in pending_peers(self):
                await deliver(self,peer)
        voice_peers = set(self.cur_call["parts"]) if self.cur_call else set()
        if self.room_host is not None:
            voice_peers |= set(self.room_members)
        if self.room_guest:
            voice_peers.add(self.room_guest)
        for o in voice_peers:                                  # голос: прямой канал важен — пробивать чаще
            p = self.peers.get(o)
            if p is not None and p.via == "nostr" and not self.udp_alive(o) and \
                    now - getattr(p, "udp_offer_t", 0) > 25:
                asyncio.ensure_future(self._udp_offer(p))
        if now - self.__dict__.get("_upd_bridge_t", 0) > 600:   # автор: тихо раздать свою сборку старым версиям
            self._upd_bridge_t = now
            asyncio.ensure_future(self._upd_auto_bridge())
        u = self.upd
        if u and u.get("state") == "downloading" and self.__dict__.get("_upd_dl") is None and \
                now - u.get("t_rx", now) > UPD_STALL:
            await self._upd_resume()
        if now - self.__dict__.get("_room_ka_t", 0) > 120:      # комната через Nostr: «я тут» раз в 2 минуты
            self._room_ka_t = now
            hp = self.peers.get(self.room_guest) if self.room_guest else None
            if hp is not None and hp.via == "nostr":
                await hp.send({"t": "room_ka"})
            if self.room_host is not None:
                for o in list(self.room_members):
                    mp = self.peers.get(o)
                    if mp is not None and mp.via == "nostr":
                        await mp.send({"t": "room_ka"})
        want = [c["onion"] for c in self.store.contacts() if c["status"] in ("friend", "pending_out")]
        want += [o for o, _ in self._pending_dials()]
        for onion in dict.fromkeys(want):
            cur = self.peers.get(onion)
            if (cur is not None and cur.via != "nostr") or onion in self._dialing:
                continue                                       # через Nostr — всё равно пробуем Tor/напрямую
            nxt, _pause = self._backoff.get(onion, (0, 0))
            if now >= nxt:
                asyncio.ensure_future(self._dial(onion))

    def _pending_dials(self):
        from net_bugs import pending_peers
        return list(dict.fromkeys([(r["peer"], 0) for r in self.store.q("SELECT DISTINCT peer FROM outbox")] + [(peer,0) for peer in pending_peers(self)]))

    def poke(self, onion=None):
        """Попробовать соединиться сейчас, не дожидаясь паузы (пользователь что-то отправил)."""
        if onion:
            self._backoff.pop(onion, None)
        else:
            self._backoff.clear()

    async def _dial(self, onion, direct_only=False):
        self._dialing.add(onion)
        try:
            r, w, via = await self._open(onion, direct_only)
            # первым говорит звонящий: байты, которые onion-сервис шлёт ДО первого байта клиента,
            # Tor теряет (проверено на tor 16.0) — поэтому «стук», и только потом hello от сервера
            await self._send_raw(w, {"t": "knock", "v": PROTO})
            hello = await _read_json(r, 60)
            if hello.get("t") != "hello" or hello.get("onion") != onion:
                raise ConnectionError("wrong peer")
            await self._send_raw(w, {"t": "auth", "v": PROTO, "onion": self.me.onion,
                                     "sig": self.me.sign(f"echoes-net-v1|{onion}|{hello.get('nonce', '')}".encode())})
            ok = await _read_json(r, 60)
            if ok.get("t") != "welcome":
                raise ConnectionError(ok.get("why") or "rejected")
            self._backoff.pop(onion, None)
            # соединение живёт своей задачей: _dial возвращается сразу (нужно комнатам и «подключиться сейчас»)
            asyncio.ensure_future(self._serve(Peer(onion, r, w, True, via)))
            await asyncio.sleep(0)
        except Exception as e:                                 # noqa: BLE001
            if direct_only:
                return
            _nxt, pause = self._backoff.get(onion, (0, 0))
            pause = min(90.0, max(15.0, pause * 1.6))         # свежий onion-адрес виден в Tor не сразу — чаще пробуем
            self._backoff[onion] = (time.time() + pause, pause)
            self.log(f"[net] dial {onion[:8]}: {type(e).__name__} {e}")
        finally:
            self._dialing.discard(onion)

    @staticmethod
    async def _send_raw(w, obj):
        w.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        await w.drain()

    async def _on_incoming(self, r, w, via="tor"):
        try:
            knock = await _read_json(r, 60)
            if knock.get("t") != "knock":
                w.close()
                return
            nonce = secrets.token_hex(16)
            await self._send_raw(w, {"t": "hello", "v": PROTO, "onion": self.me.onion, "nonce": nonce})
            auth = await _read_json(r, 60)
            onion = normalize_code(str(auth.get("onion", "")))
            if auth.get("t") != "auth" or not onion or onion == self.me.onion or \
                    not verify(onion, f"echoes-net-v1|{self.me.onion}|{nonce}".encode(), str(auth.get("sig", ""))):
                await self._send_raw(w, {"t": "reject", "why": "auth"})
                w.close()
                return
            c = self.store.contact(onion)
            if c and c["status"] == "blocked":
                await self._send_raw(w, {"t": "reject", "why": "blocked"})
                w.close()
                return
            await self._send_raw(w, {"t": "welcome"})
            await self._serve(Peer(onion, r, w, False, via))
        except Exception as e:                                 # noqa: BLE001
            self.log(f"[net] incoming: {type(e).__name__} {e}")
            try:
                w.close()
            except Exception:                                  # noqa: BLE001
                pass

    def _drop(self, p: Peer):
        p.close()
        if self.peers.get(p.onion) is p:
            del self.peers[p.onion]
            self.emit("presence", p.onion)
            for fid, inc in list(self._incoming.items()):     # обрыв: докачаем, когда владелец вернётся
                if inc["owner"] == p.onion:
                    self._incoming.pop(fid, None)
                    self.store.set_file(fid, state="want")
                    self.emit("file", (fid, "waiting", ""))
            if self.room_host is not None and p.onion in self.room_members:
                self.room_members.discard(p.onion)
                asyncio.ensure_future(self._room_broadcast())
            if self.room_guest == p.onion:
                self.room_guest = None
                self.room_state = None
                self.emit("room", None)

    def is_friend(self, onion) -> bool:
        c = self.store.contact(onion)
        return bool(c and c["status"] == "friend")

    def is_online(self, onion) -> bool:
        """Only an authenticated live connection or unexpired inbound activity proves presence."""
        p = self.peers.get(onion)
        if p is None or not p.alive or (p.via == 'nostr' and not getattr(p, '_presence_confirmed', False)):
            return False
        idle = getattr(p, '_presence_idle', NOSTR_PEER_IDLE) if p.via == 'nostr' else DEAD_AFTER
        elapsed = time.monotonic()-p._last_rx_mono if hasattr(p, '_last_rx_mono') else time.time()-p.last_rx
        return 0 <= elapsed < idle

    def _received(self, p, age=0.):
        """Record inbound evidence, retaining its original age instead of renewing a relay replay."""
        age = max(0., float(age))
        received_at = time.time()-age
        if age > 0 and getattr(p, '_presence_confirmed', False) and received_at <= p.last_rx:
            return
        p.last_rx = received_at
        p._last_rx_mono = time.monotonic()-age
        p._presence_confirmed = True
        if p.via == 'nostr':
            p._presence_idle = NOSTR_PEER_IDLE if self.is_friend(p.onion) else NOSTR_STRANGER_IDLE

    def _dialer(self, p: Peer) -> str:
        return self.me.onion if p.outbound else p.onion

    async def _serve(self, p: Peer):
        old = self.peers.get(p.onion)
        if old is not None and old.alive:
            # прямое соединение лучше Tor; при равных — оставить то, где звонил «меньший» адрес (обе стороны так же)
            ro, rn = VIA_RANK.get(old.via, 1), VIA_RANK.get(p.via, 1)
            keep_old = ro > rn or (ro == rn and self._dialer(old) == min(self.me.onion, p.onion) != self._dialer(p))
            if keep_old:
                p.close()
                return
            old.close()
        self.peers[p.onion] = p
        try:
            await self._greet(p)
            while p.alive and not self._stop:
                try:
                    msg = await _read_json(p.r, DEAD_AFTER)
                except (ValueError, UnicodeDecodeError):
                    continue
                self._received(p)
                try:
                    await self._handle(p, msg)
                except Exception as e:                         # noqa: BLE001
                    self.log(f"[net] handle {msg.get('t')}: {type(e).__name__} {e}")
        except (ConnectionError, asyncio.TimeoutError, OSError, asyncio.IncompleteReadError):
            pass
        finally:
            self._drop(p)

    async def _greet(self, p: Peer):
        from net_bugs import flush
        await flush(self,p)
        c = self.store.contact(p.onion)
        status = c["status"] if c else None
        if status == "pending_out":
            await p.send({"t": "friend_req", "name": self._name(), "note": clip(c.get("note"), 200)})
        if status in ("friend", "pending_out") and self.is_online(p.onion):
            self.store.upsert_contact(p.onion, last_seen=p.last_rx)
        for oid, payload in self.store.outbox(p.onion):       # сначала friend_ok и отложенное — потом остальное
            await p.send(payload)
            self.store.outbox_done(oid)
        if status == "friend":
            for fid in self.store.pending_files(p.onion):      # файлы, которые ждали, пока он появится
                asyncio.ensure_future(self._request_file(fid))
            for env in self.store.relay_take(p.onion):        # конверты, которые мы несли для него
                await p.send({"t": "relay_deliver", "env": env})
            await p.send(self._hi())
            have = await self._upd_have()
            if have:
                await p.send(have)
            from net_radio_auth import load as radio_permits
            if self._staff_load().get("mods") or self._staff_load()["acts"] or radio_permits(self):
                await p.send(self._staff_payload())
            mine = [{"target": r["target"], "reason": r["reason"]} for r in self.my_reports()[:200]]
            if mine:
                await p.send({"t": "report", "items": mine})
            await p.send({"t": "sync"})
            for m in self.store.undelivered(p.onion):
                await p.send({"t": "msg", "id": m["id"], "ts": m["ts"], "text": m["text"], "track": m["track"],
                              "extra": m["extra"]})
        self.emit("presence", p.onion)

    def _name(self) -> str:
        return clip(self.settings.get("name") or "ECHOES", MAX_NAME)

    def _hi(self) -> dict:
        room = None
        if self.room_host is not None:
            room = {"title": clip(self.room_host.get("title"), 80), "n": len(self.room_members) + 1}
            self._radio_summary(room)
        return {"t": "hi", "name": self._name(), "bio": clip(self.settings.get("bio"), 300),
                "now": self.now_playing if self.settings.get("share_now", True) else None, "room": room,
                "taste": self.taste if self.settings.get("share_taste", True) else None, "pv": self.pv,
                "direct": self.__dict__.get("direct_cands", []) if self.settings.get("direct", True) else [],
                "npk": self.__dict__.get("nostr_pub", ""), "vc": self._vcaps(),
                "game": clip(self.__dict__.get("game", ""), 60) if self.settings.get("share_game", True) else ""}

    def _vcaps(self) -> list:
        try:
            import net_voice
            return net_voice.codecs()
        except Exception:                                      # noqa: BLE001
            return ["adpcm"]

    def _peer_caps(self, onion) -> list:
        return (self.__dict__.get("voice_caps") or {}).get(onion) or ["adpcm"]

    async def _broadcast_friends(self, obj):
        for o, p in list(self.peers.items()):
            if self.is_friend(o):
                await p.send(obj)

    # ── входящие сообщения ── #

    async def _handle(self, p: Peer, m: dict):
        t = m.get("t")
        o = p.onion
        if t in ('bug_report','bug_ack','staff_reply','staff_reply_ack'):
            from net_bugs import receive
            await receive(self,p,m)
            return
        if t=='radio_permit':
            from net_radio_auth import accept
            bundle=m.get('proof')
            if isinstance(bundle,dict):
                decision=bundle.get('decision')
                accept(self,decision.get('target','') if isinstance(decision,dict) else '',bundle)
                if self.room_host and self.room_host.get('station') and not self.radio_allowed():
                    await self.room_close()
            return
        if t in ("ka", "bye"):
            if t == "bye":
                self.__dict__.setdefault('_pres_offline_ts', {})[o] = time.time()
                self._drop(p)
            return
        if t == "friend_req":
            c = self.store.contact(o)
            if c and c["status"] == "friend":
                await p.send({"t": "friend_ok", "name": self._name()})
                return
            if c and c["status"] == "pending_out":              # оба добавили друг друга — сразу друзья
                self.store.upsert_contact(o, status="friend", name=clip(m.get("name"), MAX_NAME))
                await p.send({"t": "friend_ok", "name": self._name()})
                await self._greet(p)
                self.emit("contacts")
                return
            if self._devpair(o, m.get("note"), clip(m.get("name"), MAX_NAME)):
                return                                         # своё второе устройство (net_devsync)
            if len(self.store.contacts("pending_in")) >= 50:
                return
            if self._mod_drop(o, m.get("name"), m.get("note")):
                return                                         # скрыт / запрещёнка в заявке — молча отбросить
            self.store.upsert_contact(o, status="pending_in", name=clip(m.get("name"), MAX_NAME),
                                      note=clip(m.get("note"), 200), last_seen=time.time())
            self.emit("contacts")
            self.emit("notify", {"kind": "request", "title": clip(m.get('name'), MAX_NAME) or o[:8],
                                 "text": "хочет добавить вас в друзья", "onion": o, "tab": "friends"})
            return
        if t == "friend_ok":
            c = self.store.contact(o)
            if c and c["status"] in ("pending_out", "friend"):
                self.store.upsert_contact(o, status="friend", name=clip(m.get("name"), MAX_NAME) or c["name"])
                await self._greet(p)
                await p.send({"t": "hi?"})                     # его «hi» пришло, пока мы ещё не дружили
                self.emit("contacts")
                self.emit("notify", {"kind": "request", "title": clip(m.get('name'), MAX_NAME) or o[:8],
                                     "text": "теперь ваш друг", "onion": o})
            return
        if not self.is_friend(o):                              # до дружбы — только заявки и публичная комната
            host_public = self.room_host is not None and self.room_host.get("public")
            ok = (host_public and t == "room_join") or t == "file_get" or t == "room_ka" or t in UPD_PUBLIC_TYPES or \
                (t in CALL_TYPES and self._call_ok(o, m)) or \
                (t == "udp_offer" and (o in self.room_members or o == self.room_guest or
                                       (host_public and self.room_host is not None) or
                                       (self.cur_call is not None and o in self.cur_call["parts"]) or
                                       self._upd_peer_ok(o))) or \
                (t in ("file_chunk", "file_end", "file_err") and any(i["owner"] == o for i in self._incoming.values())) or \
                (o in self.room_members and t in ("room_leave", "room_say", "ping", "track_get", "voice",
                                                  "file_get")) or \
                (o == self.room_guest and t in ("room_state", "room_chat", "pong", "voice", "track_file",
                                                "file_chunk", "file_end", "file_err"))
            if not ok:
                return
        if isinstance(m.get("vc"), list):
            self.__dict__.setdefault("voice_caps", {})[o] = [str(x)[:12] for x in m["vc"][:4]]
        if t == "hi":
            now = clean_track(m.get("now"))
            room = m.get("room") if isinstance(m.get("room"), dict) else None
            if room:
                room = self._clean_room_summary(room)
                if room.get('radio'):
                    from net_radio_auth import accept
                    if not accept(self,o,room['radio'].get('permit')):room=None
            taste = clean_taste(m.get("taste"))
            self.store.upsert_contact(o, name=clip(m.get("name"), MAX_NAME), bio=clip(m.get("bio"), 300),
                                      now=json.dumps(now, ensure_ascii=False) if now else "",
                                      room=json.dumps(room, ensure_ascii=False) if room else "",
                                      game=clip(m.get("game"), 60),
                                      last_seen=p.last_rx if self.is_online(o) else (self.store.contact(o) or {}).get("last_seen", 0))
            if taste is not None:
                self.store.upsert_contact(o, taste=json.dumps(taste, ensure_ascii=False))
            dc = []
            for c in (m.get("direct") or [])[:6] if isinstance(m.get("direct"), list) else []:
                try:
                    ip, port = str(c[0])[:45], int(c[1])
                    import ipaddress
                    ipaddress.ip_address(ip)
                    if 0 < port < 65536:
                        dc.append([ip, port])
                except (ValueError, TypeError, IndexError):
                    pass
            npk = str(m.get("npk") or "")
            self.store.upsert_contact(o, direct=json.dumps(dc), npk=npk if npk_ok(npk) else "")
            if dc and p.via == "tor" and self.settings.get("direct", True) and o not in self._dialing:
                asyncio.ensure_future(self._dial(o, direct_only=True))   # попробовать перейти на прямое
            pv = clip(m.get("pv"), 40)
            if pv and pv != self.contact_profile(o).get("pv"):
                await p.send({"t": "profile?"})                # профиль друга изменился — попросить новый
            self.emit("presence", o)
        elif t == "profile?":
            if self.profile:                                   # без служебных полей (путь к файлу аватарки)
                body = {k: v for k, v in self.profile.items() if not k.startswith("_")}
                if p.via == "nostr" and not self.udp_alive(o):
                    body.pop("avanim", None)                   # живая аватарка — только быстрым путём
                await p.send({"t": "profile", "p": body, "pv": self.pv})
        elif t == "profile":
            prof = clean_profile(m.get("p"))
            if prof:
                self._save_profile(o, prof, clip(m.get("pv"), 40))
                self.emit("profile", o)
        elif t == "relay":
            await self._relay_in(o, m.get("env"))
        elif t == "relay_deliver":
            await self._relay_deliver(m.get("env"))
        elif t == "group":
            g = m.get("group") or {}
            if self._group_ok(g) and g.get("owner") == o:
                old = self.store.group(g["id"])
                if not old or float(g.get("ts") or 0) >= float(old.get("ts") or 0):
                    self.store.put_group(g)
                    if not old:
                        self.emit("notify", {"kind": "message", "title": f"Группа «{g.get('name')}»",
                                             "text": f"{self._contact_name(o)} добавил(а) вас в группу", "onion": o})
                    self.emit("contacts")
        elif t == "gmsg":
            await self._gmsg_in(o, m.get("m"))
        elif t == "voice":
            await self._voice_in(o, m)
        elif t == "report":
            self._reports_in(o, m.get("items"))
        elif t == "track_get":
            await self._track_get(p, m)
        elif t == "track_file":
            await self._track_file(o, m)
        elif t == "file_get":
            await self._file_get(p, m)
        elif t == "file_chunk":
            await self._file_chunk(o, m)
        elif t == "file_end":
            await self._file_end(o, m)
        elif t == "file_err":
            fid = clip(m.get("fid"), 40)
            if fid in self._incoming:
                self._incoming.pop(fid, None)
                self.store.set_file(fid, state="want")
                self.emit("file", (fid, "error", clip(m.get("why"), 120)))
        elif t == "msg":
            mid = clip(m.get("id"), 64)
            if mid:
                ts = min(float(m.get("ts") or time.time()), time.time() + 60)
                self.store.add_message(mid, o, "in", ts, clip(m.get("text")), clean_track(m.get("track")),
                                       delivered=1, extra=clean_extra(m.get("extra")))
                await p.send({"t": "ack", "id": mid})
                self.emit("message", o)
        elif t == "ack":
            self.store.mark_delivered(clip(m.get("id"), 64))
            self.emit("delivered", o)
        elif t == "sync":
            await p.send(self._posts_payload())
        elif t == "posts":
            self._take_posts(o, m.get("items") or [], m.get("ids"))
            self.emit("feed")
        elif t in ("post_new", "post_upd"):
            self._take_posts(o, [m.get("item")], None)
            self.emit("feed")
        elif t == "post_del":
            d = m.get("del") or {}
            if verify_obj(d, "author") and d.get("author") == o:
                self.store.delete_post(str(d.get("id")))
                self._devfeed_gone(str(d.get("id")))
                self.emit("feed")
        elif t == "vote":
            v = m.get("vote") or {}
            post = self.store.post(str(v.get("post", "")))
            if post and post["author"] == self.me.onion and v.get("voter") == o and verify_obj(v, "voter") \
                    and int(v.get("val", 0)) in (-1, 0, 1):
                self.store.put_vote(v)
                await self._push_thread(post["id"])
        elif t == "comment":
            c = m.get("comment") or {}
            post = self.store.post(str(c.get("post", "")))
            if post and post["author"] == self.me.onion and c.get("author") == o and verify_obj(c, "author") \
                    and len(json.dumps(c, ensure_ascii=False)) <= MAX_TEXT * 3:
                self.store.put_comment(c)
                await self._push_thread(post["id"])
                self.emit("notify", {"kind": "comment", "title": self._contact_name(o),
                                     "text": clip(c.get("text"), 160) or "новый комментарий к вашему посту",
                                     "onion": o, "post": post["id"]})
        elif t == "react":
            r = m.get("react") or {}
            post = self.store.post(str(r.get("post", "")))
            if post and post["author"] == self.me.onion and r.get("who") == o and verify_obj(r, "who") \
                    and self._react_ok(r):
                self.store.put_react(r)
                await self._push_thread(post["id"])
                if r.get("kind") == "solved" and r.get("val"):
                    self.emit("notify", {"kind": "comment", "title": self._contact_name(o),
                                         "text": "угадал(а) ваш трек!", "onion": o, "post": post["id"]})
        # ── комната ──
        elif t == "ping":
            await p.send({"t": "pong", "c": m.get("c"), "h": time.time()})
        elif t == "pong":
            try:
                c0 = float(m["c"])
                rtt = time.time() - c0
                off = float(m["h"]) + rtt / 2 - time.time()
                self._clock = sorted(self._clock + [(rtt, off)])[:5]
            except (KeyError, TypeError, ValueError):
                pass
        elif t == "room_join":
            if self.room_host is not None:
                self.__dict__.setdefault("_names", {})[o] = clip(m.get("name"), MAX_NAME)
                self.room_members.add(o)
                self.room_host.get('sent_revisions', {}).pop(o, None)
                getattr(p, '_last', {}).pop('room_state', None)
                await self._room_broadcast()
                await self._room_say(None, f"{self._contact_name(o)} зашёл в комнату")
        elif t == "room_leave":
            if o in self.room_members:
                self.room_members.discard(o)
                if self.room_host:
                    self.room_host.get('sent_revisions', {}).pop(o, None)
                await self._room_broadcast()
                await self._room_say(None, f"{self._contact_name(o)} вышел")
        elif t == "room_say":
            if self.room_host is not None and o in self.room_members and \
                    not (not self.is_friend(o) and self._mod_drop(o, m.get("text"))):
                await self._room_say(o, clip(m.get("text"), 500))
        elif t == "room_state":
            if self.room_guest == o:
                st = m.get("state")
                if not st:
                    self.room_guest = None
                    self.room_state = None
                    self.emit("room", None)
                    self.emit("toast", "Комната закрыта")
                else:
                    st["track"] = clean_track(st.get("track"))
                    if 'radio' in st:
                        from net_radio_auth import accept
                        bundle=(st.get('radio') or {}).get('permit') or ((self.room_state or {}).get('radio') or {}).get('permit')
                        if not accept(self,o,bundle):
                            self.room_guest=None;self.room_state=None;self.emit('room',None)
                            self.emit('toast','Radio host permission is missing or revoked');return
                        from radio_station import clean_wire
                        st['radio'] = clean_wire(st['radio'], (self.room_state or {}).get('radio'))
                    self.room_state = st
                    self.emit("room", self.room_view())
        elif t == "room_chat":
            ln = m.get("line")
            if self.room_guest == o and isinstance(ln, dict):
                line = {"from": clip(ln.get("from"), 64), "name": clip(ln.get("name"), MAX_NAME),
                        "text": clip(ln.get("text"), 500), "ts": time.time(), "sys": bool(ln.get("sys"))}
                self.room_chat = (self.room_chat + [line])[-200:]
                self.emit("room_chat", line)
        elif t == "hi?":
            await p.send(self._hi())
        elif t == "room_ka":
            pass                                               # «я ещё в комнате» (связь через Nostr)
        elif t in CALL_TYPES:
            await self._call_in(p, m)
        elif t in ("spl_inv", "spl_join", "spl_state", "spl_leave"):   # совместные плейлисты (net_collab)
            if self.is_friend(o):
                self.emit("spl", {"from": o, "m": clean_spl(m)})
        elif t == "mreact":                                    # реакция на момент трека (net_moments)
            if self.is_friend(o):
                self.emit("mreact", {"from": o, "m": {"track": clean_track(m.get("track")), "id": clip(m.get("id"), 24),
                                                      "name": clip(m.get("name"), MAX_NAME), "emo": clip(m.get("emo"), 8),
                                                      "sec": float(clean_sec(m.get("sec"), 36000) or 0),
                                                      "ts": _num(m.get("ts"))}})
        elif t in ("devsync", "devpair"):                     # синхронизация своих ПК (net_devsync)
            if self.is_friend(o):
                self.emit("devsync", {"from": o, "m": m})
        elif t in ("devfeed_req", "devfeed", "devfeed_upd", "devfeed_del", "dev_act", "dev_act_ok"):
            if self.is_friend(o):                              # лента для своего устройства (net_devfeed)
                import net_devfeed
                await net_devfeed.on_message(self, p, o, m)
        elif t in ("q_add", "q_res"):                         # «подкинуть трек в очередь» другу
            if self.is_friend(o):
                self.emit("q_add" if t == "q_add" else "q_res",
                          {"from": o, "track": clean_track(m.get("track")), "note": clip(m.get("note"), 200),
                           "id": clip(m.get("id"), 24), "ok": bool(m.get("ok")), "how": clip(m.get("how"), 20)})
        elif t in QUIZ_TYPES:
            if self.is_friend(o):                              # игра — только с друзьями
                self.emit("quiz", {"from": o, "m": clean_quiz(m)})
        elif t == "staff":
            self._staff_in(m)
        elif t == "upd_have":
            await self._upd_have_in(p, m)
        elif t == "upd_ask":
            have = await self._upd_have()
            if have:
                await p.send(have)
        elif t == "upd_man?":
            man = await self._upd_mine()
            if man is not None and clip(m.get("id"), 16) == self._upd_mine_id and                     (self.is_friend(o) or man.get("public")):
                await p.send({"t": "upd_man", "m": man})
        elif t == "upd_man":
            await self._upd_man_in(p, m.get("m"))
        elif t == "upd_get":
            asyncio.ensure_future(self._upd_send(p, m))
        elif t == "upd_req":
            asyncio.ensure_future(self._upd_server().handle_req(p, m))
        elif t == "upd_pc":
            dl = self.__dict__.get("_upd_dl")
            if dl is not None and clip(m.get("id"), 16) == dl.uid:
                try:
                    data = base64.b64decode(str(m.get("d") or ""), validate=True)
                    asyncio.ensure_future(dl.on_piece(p.onion, int(m.get("f")), int(m.get("o")), data))
                except (TypeError, ValueError):
                    pass
        elif t == "upd_blob":
            await self._upd_blob_in(p, m)
        elif t == "upd_err":
            u = self.upd
            dl = self.__dict__.get("_upd_dl")
            if dl is not None and u and u.get("id") == clip(m.get("id"), 16):
                dl.bad_src[p.onion] = time.time() + 600        # у этого не вышло — берём у других
                for k, v in list(dl.inflight.items()):
                    if v[0] == p.onion:
                        dl.inflight.pop(k, None)
                        dl.pending.insert(0, [k[0], k[1], v[2]])
                if not any(o != p.onion and dl.bad_src.get(o, 0) < time.time() for o in u["from"]):
                    self._upd_fail(clip(m.get("why"), 160) or "раздающий не смог отдать обновление")
            elif u and u.get("id") == clip(m.get("id"), 16) and u.get("state") == "downloading":
                if any(o not in u.get("tried", []) for o in u["from"]) and len(u.get("tried", [])) < 8:
                    await self._upd_request()                  # есть другие, у кого оно есть
                else:
                    self._upd_fail(clip(m.get("why"), 160) or "друг не смог отдать обновление")
        elif t == "udp_offer":
            udp = getattr(self, "udp", None)
            if udp is not None:
                udp.add_peer(o, self._env_key(o), m.get("c") if isinstance(m.get("c"), list) else [])
                if not m.get("r"):
                    await self._udp_offer(p, reply=True)

    def _contact_name(self, onion) -> str:
        c = self.store.contact(onion)
        return (c and c["name"]) or self.__dict__.get("_names", {}).get(onion) or onion[:8]

    # ── лента ── #

    def _devfeed_touch(self, pid):
        """Пост появился или изменился — передать своим устройствам, если они берут ленту (net_devfeed)."""
        if "_devfeed" in self.__dict__:
            import net_devfeed
            net_devfeed.touch(self, pid)

    def _devfeed_gone(self, pid):
        if "_devfeed" in self.__dict__:
            import net_devfeed
            net_devfeed.gone(self, pid)

    def _thread_item(self, post: dict) -> dict:
        return {"post": post, "comments": self.store.comments(post["id"]), "votes": self.store.votes(post["id"]),
                "reacts": self.store.reacts(post["id"])}

    @staticmethod
    def _react_ok(r: dict) -> bool:
        kind, val = r.get("kind"), str(r.get("val") or "")
        if kind == "emo":
            if val in EMOJI or val == "":
                return True
            import net_reactions                               # своя реакция-картинка: хэш должен сойтись
            return net_reactions.valid(r)
        if kind == "pick":
            return val in ("", "0", "1")
        if kind in ("solved", "cv"):                           # cv — голос в челлендже недели
            return val in ("", "1")
        return False

    @staticmethod
    def _post_ok(post: dict) -> bool:
        """Подписанный пост: известный тип, разумный размер; репост — с проверенным оригиналом."""
        if post.get("k") != "post" or post.get("kind", "post") not in POST_KINDS:
            return False
        if len(json.dumps(post, ensure_ascii=False)) > MAX_POST_RAW:
            return False
        if post.get("gif") is not None:
            from net_gif import clean_gif
            if not clean_gif(post.get("gif")):
                return False
        if post.get("kind") == "mod" and clean_mod(post.get("mod")) is None:
            return False
        if post.get("files") is not None:
            from net_files import clean_meta
            fl = post.get("files")
            if not isinstance(fl, list) or len(fl) > 6 or any(clean_meta(f) is None for f in fl):
                return False
        if post.get("kind") == "repost":
            orig = post.get("orig")
            if not isinstance(orig, dict) or orig.get("kind") == "repost" or not verify_obj(orig, "author") \
                    or orig.get("k") != "post":
                return False
        return True

    def _posts_payload(self) -> dict:
        mine = self.store.posts(self.me.onion, FEED_SHARE)
        return {"t": "posts", "items": [self._thread_item(p) for p in mine], "ids": [p["id"] for p in mine]}

    def _take_posts(self, author, items, ids):
        oldest = None
        for it in items:
            if not isinstance(it, dict):
                continue
            post = it.get("post") or {}
            # пост храним как есть (подпись должна сходиться и при репосте); чистит его интерфейс при показе
            if post.get("author") != author or not verify_obj(post, "author") or not self._post_ok(post):
                continue
            fresh_post = self.store.post(post["id"]) is None
            self.store.put_post(post)
            if fresh_post:
                self._sub_post(post["id"], post.get("ts"), onion=author, name=self._contact_name(author),
                               text=post.get("title") or post.get("text") or "", kind=post.get("kind", "post"))
            coms = [c for c in it.get("comments") or [] if isinstance(c, dict) and c.get("post") == post["id"]
                    and verify_obj(c, "author")]
            vts = [v for v in it.get("votes") or [] if isinstance(v, dict) and v.get("post") == post["id"]
                   and verify_obj(v, "voter")]
            rts = [r for r in it.get("reacts") or [] if isinstance(r, dict) and r.get("post") == post["id"]
                   and verify_obj(r, "who") and self._react_ok(r)]
            self.store.replace_thread(post["id"], coms, vts, rts)
            self._devfeed_touch(post["id"])
            oldest = post["ts"] if oldest is None else min(oldest, post["ts"])
        if isinstance(ids, list):                              # автор удалил пост — убрать и у нас
            keep = set(map(str, ids))
            for p in self.store.posts(author, 500):
                if p["id"] not in keep and (oldest is None or p["ts"] >= oldest):
                    self.store.delete_post(p["id"])
                    self._devfeed_gone(p["id"])

    async def _push_thread(self, pid):
        post = self.store.post(pid)
        if post:
            await self._broadcast_friends({"t": "post_upd", "item": self._thread_item(post)})
            self._devfeed_touch(pid)
            self.emit("feed")

    # ── действия интерфейса (вызывать через call) ── #

    def add_friend(self, code, note=""):
        onion = normalize_code(code)
        if not onion or pub_from_onion(onion) is None:
            self.emit("toast", "Это не код Echoes.NET")
            return
        if onion == self.me.onion:
            self.emit("toast", "Это ваш собственный код")
            return
        c = self.store.contact(onion)
        if c and c["status"] == "friend":
            self.emit("toast", "Уже в друзьях")
            return
        if c and c["status"] == "pending_in":
            self.accept(onion)
            return
        self.store.upsert_contact(onion, status="pending_out", note=clip(note, 200))
        self.poke(onion)
        self.emit("contacts")
        nos = getattr(self, "nostr", None)
        if self.loop is not None and nos is not None and nos.up_count:
            asyncio.ensure_future(self._nostr_req_send(onion, "friend_req"))
            self.emit("toast", "Заявка отправлена — друг получит её, даже если сейчас не в сети")
        else:
            self.emit("toast", "Заявка отправится, как только появится связь (Tor или Nostr)")

    def _devpair(self, o, note, name="") -> bool:
        """Заявка со своего второго ПК с действующим кодом привязки — принять сразу (net_devsync)."""
        note = str(note or "")
        if not note.startswith("ECHOES-SYNC:"):
            return False
        import net_devsync
        if not net_devsync.pair_ok(self, note.split(":", 1)[1].strip()):
            return False
        net_devsync.add_device(self, o)
        self.store.upsert_contact(o, name=name or "", last_seen=time.time())
        self.accept(o)
        self.emit("notify", {"kind": "request", "title": name or "Ваш ПК", "text": "привязан для синхронизации",
                             "onion": o})
        return True

    def accept(self, onion):
        self.store.upsert_contact(onion, status="friend")
        self.store.outbox_add(onion, {"t": "friend_ok", "name": self._name()})
        p = self.peers.get(onion)
        if p and self.loop:
            asyncio.ensure_future(self._flush_outbox(p))
        if self.loop is not None:                              # «принято» — и через Nostr (друг может быть не в сети)
            asyncio.ensure_future(self._nostr_req_send(onion, "friend_ok"))
        self.poke(onion)
        self.emit("contacts")

    async def _flush_outbox(self, p):
        await self._greet(p)

    def decline(self, onion):
        self.store.remove_contact(onion)
        self.emit("contacts")

    def block(self, onion):
        self.store.upsert_contact(onion, status="blocked")
        p = self.peers.get(onion)
        if p:
            self._drop(p)
        self.emit("contacts")

    def remove_friend(self, onion):
        self.store.remove_contact(onion)
        p = self.peers.get(onion)
        if p:
            self._drop(p)
        self.emit("contacts")

    async def send_message(self, onion, text, track=None, extra=None):
        text = clip(text).strip()
        track = clean_track(track)
        extra = clean_extra(extra)
        if not text and not track and not extra:
            return
        mid = secrets.token_hex(12)
        ts = time.time()
        self.store.add_message(mid, onion, "out", ts, text, track, delivered=0, read=1, extra=extra)
        self.emit("message", onion)
        p = self.peers.get(onion)
        msg = {"t": "msg", "id": mid, "ts": ts, "text": text, "track": track, "extra": extra}
        if p:
            await p.send(msg)
        else:
            self.poke(onion)
            relayed = await self._relay_out(onion, msg)            # через общего друга
            mailed = await self._nostr_mail(onion, msg)            # и/или через релеи Nostr
            if relayed or mailed:
                self.store.x("UPDATE messages SET delivered=2 WHERE id=? AND delivered=0", (mid,))
                self.emit("delivered", onion)

    async def publish(self, text, track=None, kind="post", **extra):
        """Пост любого типа: post (текст + трек, «момент» — at), battle (tracks[2]), playlist (tracks, title),
        quiz (трек скрыт, hint), quote (строчка песни + трек), repost (orig — чужой подписанный пост)."""
        text = clip(text).strip()
        kind = kind if kind in POST_KINDS else "post"
        why = self.mod_check(text, extra.get("quote"), extra.get("title"), extra.get("hint"))
        if why:
            self.emit("toast", f"Не опубликовано: похоже на запрещённое ({why})")
            return
        obj = {"k": "post", "kind": kind, "id": secrets.token_hex(12), "author": self.me.onion, "ts": time.time(),
               "text": text, "track": clean_track(track), "name": self._name()}
        if clean_sec(extra.get("at")) is not None:
            obj["at"] = clean_sec(extra.get("at"))
        if kind in ("battle", "playlist"):
            obj["tracks"] = [x for x in (clean_track(t) for t in (extra.get("tracks") or [])[:50]) if x]
            if kind == "battle" and len(obj["tracks"]) != 2:
                self.emit("toast", "Для баттла нужны два трека")
                return
            obj["title"] = clip(extra.get("title"), 100)
        if kind == "quiz":
            obj["hint"] = clip(extra.get("hint"), 200)
            obj["url"] = clip(extra.get("url"), 300)
        if kind == "quote":
            obj["quote"] = clip(extra.get("quote"), 400)
        if kind == "chal":                                     # заявка на челлендж недели (net_challenge)
            if not obj["track"]:
                self.emit("toast", "Для заявки нужен трек")
                return
            obj["week"] = clip(extra.get("week"), 10)
            obj["theme"] = clip(extra.get("theme"), 120)
        if kind == "thread":                                   # тред (как на Reddit): заголовок обязателен
            obj["title"] = clip(extra.get("title"), 200).strip()
            if not obj["title"]:
                self.emit("toast", "У треда должен быть заголовок")
                return
            if extra.get("flair") in THREAD_FLAIRS:
                obj["flair"] = extra["flair"]
        if extra.get("files"):
            from net_files import clean_meta
            obj["files"] = [m for m in (clean_meta(f) for f in extra["files"][:6]) if m]
        if extra.get("gif"):
            from net_gif import clean_gif
            g = clean_gif(extra["gif"])
            if g:
                obj["gif"] = g
        if kind == "mod":
            obj["mod"] = clean_mod(extra.get("mod"))
            obj["title"] = clip(extra.get("title"), 80)
            if not obj["mod"] or not obj["title"]:
                self.emit("toast", "Мод не опубликован: нет файла темы или названия")
                return
        if kind == "repost":
            orig = extra.get("orig")
            if isinstance(orig, dict) and orig.get("kind") == "repost":
                orig = orig.get("orig")
            if not isinstance(orig, dict) or not verify_obj(orig, "author"):
                return
            obj["orig"] = orig
        if not text and not obj["track"] and kind in ("post", "quote") and not obj.get("quote") \
                and not obj.get("files") and not obj.get("gif"):
            return
        post = self.me.sign_obj(obj)
        if not self._post_ok(post):
            self.emit("toast", "Пост слишком большой")
            return
        self.store.put_post(post)
        self.emit("feed")
        self._devfeed_touch(post["id"])
        await self._broadcast_friends({"t": "post_new", "item": self._thread_item(post)})

    async def react(self, pid, kind, val):
        """Реакция на пост: emo (эмодзи), pick (выбор в баттле: «0»/«1»), solved (угадал трек). val='' — снять."""
        post = self.store.post(pid)
        r = {"k": "react", "post": pid, "who": self.me.onion, "kind": kind, "val": str(val or ""), "ts": time.time()}
        if kind == "emo" and str(val or "").startswith("c:"):
            import net_reactions
            r["img"] = net_reactions.b64(val)                  # картинка едет внутри подписанной реакции
        if not post or not self._react_ok(r):
            return
        r = self.me.sign_obj(r)
        self.store.put_react(r)
        self._devfeed_touch(pid)
        self.emit("feed")
        if post["author"] == self.me.onion:
            await self._push_thread(pid)
        else:
            await self._to_author(post["author"], {"t": "react", "react": r})

    # ── профиль ── #

    def contact_profile(self, onion) -> dict:
        c = self.store.contact(onion)
        try:
            own = json.loads(c["profile"]) if c and c.get("profile") else {}
        except ValueError:
            own = {}
        pub = (getattr(self, "public", None) or {}).get("full", {}).get(onion)
        if pub and (not own or pub.get("_ts", 0) > float((c or {}).get("last_seen") or 0) and not own.get("tier")):
            return dict(pub)
        if not own and npk_ok(self._npk_for(onion)):
            self._want_profile(self._npk_for(onion))
        return own

    def avatar_path(self, onion) -> str:
        """Файл аватарки друга (или свой), если есть."""
        if onion == self.me.onion:
            return (self.profile or {}).get("_avatar_path", "")
        pv = self.contact_profile(onion).get("pv", "")
        f = self.avatar_dir / f"{onion[:16]}_{pv}.jpg"
        if pv and f.exists():
            return str(f)
        pub = self.avatar_dir / f"{onion[:16]}_pub.jpg"
        return str(pub) if pub.exists() else ""

    def avatar_anim_path(self, onion) -> str:
        """Анимированная аватарка друга (GIF), если он её прислал."""
        pv = self.contact_profile(onion).get("pv", "")
        f = self.avatar_dir / f"{onion[:16]}_{pv}.gif"
        return str(f) if pv and f.exists() else ""

    def _save_profile(self, onion, prof, pv):
        an = prof.pop("avanim", None)
        try:
            self.avatar_dir.mkdir(parents=True, exist_ok=True)
            for old in self.avatar_dir.glob(f"{onion[:16]}_*.gif"):
                old.unlink(missing_ok=True)
            if an:
                (self.avatar_dir / f"{onion[:16]}_{pv}.gif").write_bytes(base64.b64decode(an))
        except (OSError, ValueError) as e:
            self.log(f"[net] avanim: {e}")
        av = prof.pop("avatar", None)
        if av:
            try:
                self.avatar_dir.mkdir(parents=True, exist_ok=True)
                for old in self.avatar_dir.glob(f"{onion[:16]}_*.jpg"):
                    old.unlink(missing_ok=True)
                (self.avatar_dir / f"{onion[:16]}_{pv}.jpg").write_bytes(base64.b64decode(av))
            except OSError as e:
                self.log(f"[net] avatar: {e}")
        prof["pv"] = pv
        prof["got"] = time.time()
        self.store.upsert_contact(onion, profile=json.dumps(prof, ensure_ascii=False))

    async def set_profile_card(self, card: dict):
        """Своя карточка профиля (собирает интерфейс): друзья заберут её при следующем «hi»."""
        clean = clean_profile(card) or {}
        self.profile = clean
        self.profile["_avatar_path"] = clip(card.get("_avatar_path"), 500)
        body = {k: v for k, v in clean.items() if not k.startswith("_")}
        self.pv = hashlib.sha1(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
        self.profile = dict(body, _avatar_path=self.profile["_avatar_path"])
        await self._broadcast_friends(self._hi())
        nos = getattr(self, "nostr", None)
        if nos is not None and nos.up_count and self.pv != self.__dict__.get("_pub_pv"):
            self._pub_pv = self.pv                             # профиль изменился — сразу и в публичный
            asyncio.ensure_future(self.publish_public_profile())

    # ── доставка через общего друга ── #

    def _env_key(self, other):
        from net_crypto import pair_key
        return pair_key(self.me.seed, self.me.onion, pub_from_onion(other), other)

    async def _relay_out(self, dest, payload) -> bool:
        """Друг не в сети: зашифровать для него и отдать друзьям, которые сейчас в сети, — кто дружит с ним,
        донесёт. Возвращает True, если конверт хоть кому-то ушёл."""
        from net_crypto import seal
        carriers = [p for o, p in self.peers.items() if o != dest and self.is_friend(o)]
        if not carriers:
            return False
        env = {"to": dest, "from": self.me.onion, "id": clip(payload.get("id") or secrets.token_hex(12), 64),
               "ts": time.time(), "blob": seal(self._env_key(dest), payload)}
        for p in carriers[:6]:
            await p.send({"t": "relay", "env": env})
        return True

    async def _relay_in(self, carrier_from, env):
        if not isinstance(env, dict) or len(str(env.get("blob", ""))) > 64 * 1024:
            return
        dest, src = normalize_code(str(env.get("to", ""))), normalize_code(str(env.get("from", "")))
        if not dest or src != carrier_from or not self.is_friend(dest) or dest == self.me.onion:
            return                                              # несём только своим друзьям и только от отправителя
        env = {"to": dest, "from": src, "id": clip(env.get("id"), 64), "ts": time.time(), "blob": str(env["blob"])}
        p = self.peers.get(dest)
        if p:
            await p.send({"t": "relay_deliver", "env": env})
        else:
            self.store.relay_put(env)

    async def _relay_deliver(self, env):
        from net_crypto import open_
        if not isinstance(env, dict) or env.get("to") != self.me.onion:
            return
        src = normalize_code(str(env.get("from", "")))
        if not src or not self.is_friend(src):
            return
        obj = open_(self._env_key(src), str(env.get("blob", "")))
        if not obj:
            return
        if obj.get("t") == "msg":
            mid = clip(obj.get("id"), 64)
            if mid and not self.store.has_message(mid):
                ts = min(float(obj.get("ts") or time.time()), time.time() + 60)
                self.store.add_message(mid, src, "in", ts, clip(obj.get("text")), clean_track(obj.get("track")),
                                       delivered=1, extra=clean_extra(obj.get("extra")))
                self.emit("message", src)

    # ── групповые чаты ── #

    def _group_ok(self, g) -> bool:
        if not isinstance(g, dict) or g.get("k") != "group" or not verify_obj(g, "owner"):
            return False
        mem = g.get("members")
        return isinstance(mem, list) and 2 <= len(mem) <= MAX_GROUP and self.me.onion in mem \
            and g["owner"] in mem and all(normalize_code(str(x)) == x for x in mem)

    async def create_group(self, name, members):
        mem = [self.me.onion] + [m for m in dict.fromkeys(members) if self.is_friend(m)][:MAX_GROUP - 1]
        if len(mem) < 2:
            self.emit("toast", "Выберите хотя бы одного друга")
            return
        g = self.me.sign_obj({"k": "group", "id": secrets.token_hex(10), "name": clip(name, 60) or "Группа",
                              "owner": self.me.onion, "members": mem, "ts": time.time()})
        self.store.put_group(g)
        for o in mem[1:]:
            await self._to_author(o, {"t": "group", "group": g})
        self.emit("contacts")
        self.emit("group", g["id"])

    def leave_group(self, gid):
        self.store.delete_group(gid)
        self.emit("contacts")

    async def send_group(self, gid, text, track=None, extra=None):
        g = self.store.group(gid)
        text, track, extra = clip(text).strip(), clean_track(track), clean_extra(extra)
        if not g or (not text and not track and not extra):
            return
        m = self.me.sign_obj({"k": "gmsg", "id": secrets.token_hex(12), "g": gid, "author": self.me.onion,
                              "ts": time.time(), "text": text, "track": track, "extra": extra})
        self.store.add_message(m["id"], "g:" + gid, "out", m["ts"], text, track, delivered=1, read=1,
                               extra=dict(extra, **{"from": self.me.onion}))
        self.emit("message", "g:" + gid)
        await self._group_fanout(g, m, skip={self.me.onion})

    async def _group_fanout(self, g, m, skip):
        for o in g["members"]:
            if o in skip or not self.is_friend(o):
                continue
            await self._to_author(o, {"t": "gmsg", "m": m})

    async def _gmsg_in(self, sender, m):
        if not isinstance(m, dict) or m.get("k") != "gmsg" or not verify_obj(m, "author"):
            return
        g = self.store.group(str(m.get("g", "")))
        if not g or m["author"] not in g["members"] or sender not in g["members"]:
            return
        mid = clip(m.get("id"), 64)
        if not mid or self.store.has_message(mid):
            return
        big = isinstance(m.get("extra"), dict) and m["extra"].get("kind") == "playlist"
        if len(json.dumps(m, ensure_ascii=False)) > (MAX_TEXT * 16 if big else MAX_TEXT * 3):   # плейлист до 100 треков
            return
        ex = clean_extra(m.get("extra"))
        ex["from"] = m["author"]
        ex["name"] = self._contact_name(m["author"]) if self.store.contact(m["author"]) else ""
        ts = min(float(m.get("ts") or time.time()), time.time() + 60)
        self.store.add_message(mid, "g:" + g["id"], "in", ts, clip(m.get("text")), clean_track(m.get("track")),
                               delivered=1, extra=ex)
        self.emit("message", "g:" + g["id"])
        # переслать тем участникам, кто дружит с нами, но мог не получить (не дружит с автором)
        await self._group_fanout(g, m, skip={self.me.onion, m["author"], sender})

    # ── голос в комнате ── #

    def room_codec(self) -> str:
        """Кодек голоса комнаты: opus, если он есть у всех; иначе запасной adpcm."""
        import net_voice
        if self.room_host is not None:
            return net_voice.pick_codec([self._vcaps()] + [self._peer_caps(o) for o in self.room_members])
        return str((self.room_state or {}).get("vc") or "adpcm")

    def voice_out(self, seq, frames):
        """Из потока голоса (net_voice): кадры своего голоса → в звонок, а если его нет — в комнату."""
        loop = self.loop
        if loop is None:
            return
        loop.call_soon_threadsafe(lambda: self._voice_batch(int(seq), frames))

    def _voice_batch(self, seq, frames):
        """Копить по 2 кадра (40 мс) и отправлять одним сообщением — вдвое меньше пакетов."""
        buf = self.__dict__.setdefault("_vbuf", {"seq": None, "f": {}})
        if buf["seq"] is None or seq != buf["seq"] + sum(1 for _ in next(iter(buf["f"].values()), [])):
            if buf["f"]:
                self._voice_flush()
            buf["seq"] = seq
        for c, lst in frames.items():
            buf["f"].setdefault(c, []).extend(base64.b64encode(x).decode() for x in lst)
        if len(next(iter(buf["f"].values()), [])) >= 2:
            self._voice_flush()

    def _voice_flush(self):
        buf = self.__dict__.get("_vbuf")
        if not buf or not buf["f"]:
            return
        seq, frames = buf["seq"], buf["f"]
        buf["seq"], buf["f"] = None, {}
        if self.cur_call is not None:
            asyncio.ensure_future(self.call_voice(seq, frames))
        else:
            asyncio.ensure_future(self.voice_send(seq, frames))

    async def voice_send(self, seq, frames):
        """Свой голос в комнате: гость — хосту, хост — всем гостям (кодек комнаты)."""
        c = self.room_codec()
        d = frames.get(c) or next(iter(frames.values()), None)
        if not d:
            return
        c = c if c in frames else next(iter(frames))
        frame = {"t": "voice", "c": c, "s": int(seq), "d": d[:VOICE_FRAMES_MAX], "from": self.me.onion}
        if self.room_host is not None:
            for o in list(self.room_members):
                p = self.peers.get(o)
                if p:
                    await p.send(frame)
        elif self.room_guest and self.room_guest in self.peers:
            await self.peers[self.room_guest].send(frame)

    def _voice_frames(self, m):
        d = m.get("d")
        if not isinstance(d, list) or not d or len(d) > VOICE_FRAMES_MAX or \
                any(not isinstance(x, str) or len(x) > VOICE_MAX for x in d):
            return None
        c = str(m.get("c") or "")
        if c not in ("opus", "adpcm"):
            return None
        try:
            seq = int(m.get("s") or 0)
        except (TypeError, ValueError):
            return None
        return c, seq, d

    async def _voice_in(self, o, m):
        vf = self._voice_frames(m)
        if vf is None:
            return
        c, seq, d = vf
        if self.room_host is not None and o in self.room_members:
            self.emit("voice", (o, c, seq, d))                 # хост слышит гостя и пересылает остальным
            for other in list(self.room_members):
                if other != o and other in self.peers:
                    await self.peers[other].send({"t": "voice", "c": c, "s": seq, "d": d, "from": o})
        elif self.room_guest == o:
            src = normalize_code(str(m.get("from") or o)) or o
            self.emit("voice", (src, c, seq, d))

    # ── звонки: личка и созвоны в группах (как в Discord) ── #
    # Сетка: каждый участник шлёт свой голос каждому (до ~8 человек). Голос — только прямым путём
    # (UDP через пробитый NAT / Tor / напрямую); через релеи Nostr — лишь вызов, ответ и состояние.


    def call_view(self) -> dict | None:
        c = self.cur_call
        if not c:
            return None
        parts = [{"onion": o, "mute": bool(st.get("mute")), "deaf": bool(st.get("deaf")),
                  "link": self.voice_link(o) if o != self.me.onion else "me"}
                 for o, st in c["parts"].items()]
        return {"cid": c["cid"], "kind": c["kind"], "gid": c.get("gid", ""), "peer": c.get("peer", ""),
                "title": c["title"], "t0": c["t0"], "parts": parts, "ringing": sorted(c["ringing"]),
                "codec": self.call_codec()}

    def voice_link(self, onion) -> str:
        """Как идёт голос до него: udp / tor / direct / none (только релеи — голос не пройдёт)."""
        p = self.peers.get(onion)
        if p is None or not p.alive:
            return "none"
        if p.via != "nostr":
            return p.via
        return "udp" if self.udp_alive(onion) else "none"

    def call_codec(self) -> str:
        import net_voice
        c = self.cur_call
        if not c:
            return "adpcm"
        return net_voice.pick_codec([self._vcaps()] + [self._peer_caps(o) for o in c["parts"] if o != self.me.onion])

    def _call_ok(self, o, m=None) -> bool:
        """Звонить можно друзьям и участникам общих групп; в идущем звонке — его участникам."""
        if self.is_friend(o):
            return True
        c = self.cur_call
        if c and o in c["parts"]:
            return True
        cid = clip((m or {}).get("cid"), 24)
        if cid and cid in self.rings:
            return True
        gid = clip((m or {}).get("gid"), 40)
        g = self.store.group(gid) if gid else None
        return bool(g and o in (g.get("members") or []) and self.me.onion in (g.get("members") or []))

    async def _peer_for(self, onion):
        """Связь с ним сейчас: есть — она; нет — через Nostr (если знаем ключ) и параллельно Tor/напрямую."""
        p = self.peers.get(onion)
        if p is not None and p.alive:
            return p
        self.poke(onion)
        npk = self._npk_for(onion)
        if npk:
            return self._nostr_attach(onion, npk)
        return None

    async def quiz_send(self, onion, msg):
        """«Угадай трек вместе»: сообщение другу (ведущий ↔ игрок)."""
        p = await self._peer_for(onion)
        if p is None:
            self.emit("quiz", {"from": onion, "m": {"t": "quiz_leave", "gid": msg.get("gid", ""), "offline": True}})
            return
        await p.send(msg)

    async def call_start(self, target):
        """Позвонить: target — onion (личка) или 'g:<id>' (созвон в группе)."""
        if self.cur_call is not None:
            await self.call_leave()
        cid = secrets.token_hex(8)
        if str(target).startswith("g:"):
            g = self.store.group(target[2:]) or {}
            members = [o for o in (g.get("members") or []) if o != self.me.onion]
            kind, title, gid, peer = "group", g.get("name") or "Группа", g.get("id") or target[2:], ""
        else:
            members, kind, title, gid, peer = [target], "dm", self._contact_name(target), "", target
        self.cur_call = {"cid": cid, "kind": kind, "gid": gid, "peer": peer, "title": title, "t0": time.time(),
                     "parts": {self.me.onion: {"mute": False, "deaf": False}}, "ringing": set(members),
                     "ring_t": time.time()}
        msg = {"t": "call_ring", "cid": cid, "kind": kind, "gid": gid, "title": clip(title, 80),
               "name": self._name(), "vc": self._vcaps()}
        n = 0
        for o in members:
            p = await self._peer_for(o)
            if p is not None:
                await p.send(msg)
                asyncio.ensure_future(self._udp_offer(p))
                n += 1
        self.log(f"[net] звонок {cid} ({kind}): позвал {n} из {len(members)}")
        if not n:
            self.emit("toast", "Никого нет в сети — звонок не дойдёт")
        self.emit("call", self.call_view())

    async def call_invite(self, onion):
        """Позвать друга в текущий звонок (из оверлея); не в звонке — просто позвонить ему."""
        c = self.cur_call
        if c is None:
            await self.call_start(onion)
            return
        if onion in c["parts"]:
            return
        kind = c["kind"] if c["kind"] == "group" and onion in ((self.store.group(c.get("gid", "")) or {}).get("members")
                                                                 or []) else "dm"
        c["ringing"].add(onion)
        p = await self._peer_for(onion)
        if p is None:
            self.emit("toast", "Друг не в сети — звонок не дойдёт")
            return
        await p.send({"t": "call_ring", "cid": c["cid"], "kind": kind, "gid": c.get("gid", "") if kind == "group" else "",
                      "title": clip(c.get("title"), 80), "name": self._name(), "vc": self._vcaps()})
        asyncio.ensure_future(self._udp_offer(p))
        self.emit("call", self.call_view())

    async def call_accept(self, cid):
        r = self.rings.pop(cid, None)
        if not r:
            return
        if self.cur_call is not None:
            await self.call_leave()
        self.cur_call = {"cid": cid, "kind": r["kind"], "gid": r.get("gid", ""),
                     "peer": r["from"] if r["kind"] == "dm" else "", "title": r["title"], "t0": time.time(),
                     "parts": {self.me.onion: {"mute": False, "deaf": False}, r["from"]: {}}, "ringing": set(),
                     "ring_t": 0}
        p = await self._peer_for(r["from"])
        if p is not None:
            await p.send({"t": "call_join", "cid": cid, "gid": r.get("gid", ""), "vc": self._vcaps(),
                          "name": self._name()})
            asyncio.ensure_future(self._udp_offer(p))
        self.emit("ring", None)
        self.emit("call", self.call_view())

    async def call_decline(self, cid):
        r = self.rings.pop(cid, None)
        if r:
            p = self.peers.get(r["from"])
            if p is not None and r["kind"] == "dm":
                await p.send({"t": "call_decline", "cid": cid})
        self.emit("ring", None)

    async def call_join_group(self, gid):
        """Подключиться к идущему созвону группы (его звонок мы пропустили)."""
        for cid, r in list(self.rings.items()):
            if r.get("gid") == gid:
                await self.call_accept(cid)
                return
        await self.call_start("g:" + gid)

    async def call_leave(self):
        c = self.cur_call
        if not c:
            return
        self.cur_call = None
        for o in list(c["parts"]) + list(c["ringing"]):
            if o != self.me.onion and o in self.peers:
                await self.peers[o].send({"t": "call_leave", "cid": c["cid"]})
        self.emit("call", None)

    async def call_set(self, mute=None, deaf=None):
        c = self.cur_call
        if not c:
            return
        me = c["parts"][self.me.onion]
        if mute is not None:
            me["mute"] = bool(mute)
        if deaf is not None:
            me["deaf"] = bool(deaf)
        for o in list(c["parts"]):
            if o != self.me.onion and o in self.peers:
                await self.peers[o].send({"t": "call_state", "cid": c["cid"], "mute": me.get("mute", False),
                                          "deaf": me.get("deaf", False)})
        self.emit("call", self.call_view())

    async def call_voice(self, seq, frames):
        c = self.cur_call
        if not c:
            return
        for o in list(c["parts"]):
            if o == self.me.onion:
                continue
            p = self.peers.get(o)
            if p is None:
                continue
            caps = self._peer_caps(o)
            codec = next((x for x in ("opus", "adpcm") if x in frames and x in caps), None)
            if codec is None:
                continue
            await p.send({"t": "vc", "cid": c["cid"], "c": codec, "s": int(seq), "d": frames[codec][:VOICE_FRAMES_MAX]})

    async def _call_in(self, p, m):
        t, o = m.get("t"), p.onion
        cid = clip(m.get("cid"), 24)
        c = self.cur_call
        if isinstance(m.get("vc"), list):
            self.__dict__.setdefault("voice_caps", {})[o] = [str(x)[:12] for x in m["vc"][:4]]
        if t == "vc":
            if c and cid == c["cid"] and o in c["parts"]:
                vf = self._voice_frames(m)
                if vf is not None:
                    self.emit("vc", (o,) + vf)
            return
        if t == "call_ring":
            if c and c["cid"] == cid:
                return
            kind = "group" if m.get("kind") == "group" else "dm"
            gid = clip(m.get("gid"), 40)
            if kind == "group" and not self._call_ok(o, m):
                return
            title = self._contact_name(o) if kind == "dm" else \
                ((self.store.group(gid) or {}).get("name") or clip(m.get("title"), 80) or "Группа")
            self.rings[cid] = {"from": o, "kind": kind, "gid": gid, "title": title, "ts": time.time(),
                               "name": clip(m.get("name"), MAX_NAME) or self._contact_name(o)}
            self.log(f"[net] входящий звонок {cid} от {o[:8]} ({kind})")
            asyncio.ensure_future(self._udp_offer(p))
            self.emit("ring", dict(self.rings[cid], cid=cid))
            return
        if t == "call_join":
            if c and cid == c["cid"]:
                fresh = o not in c["parts"]
                c["parts"].setdefault(o, {})
                c["ringing"].discard(o)
                await p.send({"t": "call_here", "cid": cid, "gid": c.get("gid", ""), "vc": self._vcaps(),
                              "parts": [[x, self._npk_for(x) or ""] for x in c["parts"] if x != o]})
                if fresh:
                    asyncio.ensure_future(self._udp_offer(p))
                self.emit("call", self.call_view())
            return
        if t == "call_here":
            if c and cid == c["cid"]:
                c["parts"].setdefault(o, {})
                c["ringing"].discard(o)
                for ent in (m.get("parts") or [])[:16]:
                    x, npk = (ent[0], ent[1]) if isinstance(ent, list) and len(ent) == 2 else (ent, "")
                    x = normalize_code(str(x))
                    if x and x != self.me.onion and x not in c["parts"]:
                        c["parts"][x] = {}
                        if isinstance(npk, str) and len(npk) == 64 and not self._npk_for(x):
                            self.__dict__.setdefault("_npk_map", {})[x] = npk
                        q = await self._peer_for(x)            # сетка: подключиться к остальным участникам
                        if q is not None:
                            await q.send({"t": "call_join", "cid": cid, "gid": c.get("gid", ""),
                                          "vc": self._vcaps(), "name": self._name()})
                            asyncio.ensure_future(self._udp_offer(q))
                self.emit("call", self.call_view())
            return
        if t == "call_leave":
            if cid in self.rings and self.rings[cid]["from"] == o:
                self.rings.pop(cid, None)                      # позвонивший передумал
                self.emit("ring", None)
            if c and cid == c["cid"]:
                c["parts"].pop(o, None)
                c["ringing"].discard(o)
                self.emit("vc_gone", o)
                if c["kind"] == "dm" and len(c["parts"]) <= 1:
                    self.cur_call = None
                    self.emit("toast", f"{self._contact_name(o)} завершил(а) звонок")
                    self.emit("call", None)
                    return
                self.emit("call", self.call_view())
            return
        if t == "call_decline":
            if c and cid == c["cid"]:
                c["ringing"].discard(o)
                if c["kind"] == "dm" and len(c["parts"]) <= 1:
                    self.cur_call = None
                    self.emit("toast", f"{self._contact_name(o)} отклонил(а) звонок")
                    self.emit("call", None)
                    return
                self.emit("call", self.call_view())
            return
        if t == "call_state":
            if c and cid == c["cid"] and o in c["parts"]:
                c["parts"][o].update(mute=bool(m.get("mute")), deaf=bool(m.get("deaf")))
                self.emit("call", self.call_view())

    def _call_tick(self):
        now = time.time()
        for cid, r in list(self.rings.items()):
            if now - r["ts"] > CALL_RING_FOR:
                self.rings.pop(cid, None)
                self.emit("ring", None)
                self.emit("notify", {"kind": "message", "title": r.get("name") or "Звонок",
                                     "text": "пропущенный звонок", "onion": r["from"]})
        c = self.cur_call
        if c and c["ringing"] and now - c.get("ring_t", now) > CALL_RING_FOR:
            c["ringing"].clear()
            if c["kind"] == "dm" and len(c["parts"]) <= 1:
                self.cur_call = None
                self.emit("toast", f"{c['title']} не ответил(а)")
                self.emit("call", None)
            else:
                self.emit("call", self.call_view())

    # ── «Взять трек у друга»: свой mp3 по запросу (только друзьям и гостям своей комнаты) ── #

    def set_library_lookup(self, fn):
        """Интерфейс даёт функцию: описание трека → путь к своему файлу или ''. Вызывается из сетевого потока."""
        self._lib_lookup = fn

    async def request_track(self, owner, track):
        """Попросить у друга (или хоста комнаты) его файл трека — придёт как обычный файл (докачка, SHA-256)."""
        track = clean_track(track)
        p = self.peers.get(owner)
        if not track:
            return
        if not p:
            self.poke(owner)
            if owner in self._dialing or not await self._dial_now(owner):
                self.emit("toast", "Друг сейчас не в сети")
                return
            p = self.peers.get(owner)
        await p.send({"t": "track_get", "track": track})

    async def _track_get(self, p, m):
        allowed = self.is_friend(p.onion) or (self.room_host is not None and p.onion in self.room_members)
        track = clean_track(m.get("track"))
        lookup = getattr(self, "_lib_lookup", None)
        if not allowed or not track or lookup is None or not self.settings.get("share_tracks", True):
            await p.send({"t": "track_file", "track": track, "file": None, "why": "друг не раздаёт треки"})
            return
        path = lookup(track)
        if not path:
            await p.send({"t": "track_file", "track": track, "file": None, "why": "у друга этот трек не файлом"})
            return
        cache = self.__dict__.setdefault("_track_shares", {})   # один и тот же файл — без повторного хэширования
        meta = cache.get(path)
        if meta is None or not Path(self.store.file(meta["fid"])["path"] if self.store.file(meta["fid"]) else "").exists():
            meta = await self.share_file(path, ["*"])
            if not meta:
                return
            cache[path] = meta
        r = self.store.file(meta["fid"])
        if r and p.onion not in r["allow"] and "*" not in r["allow"]:
            r["allow"].append(p.onion)
        if r and not self.is_friend(p.onion):                  # гость комнаты, не друг: разрешить именно ему
            self.store.put_file(meta["fid"], self.me.onion, r["meta"], "have", r["path"], r["allow"] + [p.onion])
        await p.send({"t": "track_file", "track": track, "file": meta})

    async def _track_file(self, o, m):
        from net_files import clean_meta
        fm = clean_meta(m.get("file"))
        track = clean_track(m.get("track"))
        if not fm:
            self.emit("track_file", (o, track, None, clip(m.get("why"), 120)))
            return
        self.emit("track_file", (o, track, fm, ""))
        await self.fetch(fm, o)

    async def _dial_now(self, onion) -> bool:
        """Соединиться немедленно (не дожидаясь цикла поддержания связей) — для комнат и запросов незнакомцам."""
        self._backoff.pop(onion, None)
        await self._dial(onion)
        if onion in self.peers:
            return True
        npk = self._npk_for(onion)
        if npk and getattr(self, "nostr", None) is not None and self.nostr.up_count:
            self._nostr_attach(onion, npk)                     # Tor не прошёл — связь через релеи
            return True
        return False

    # ══════════════════════════════════════════════════════════════════ #
    #  Nostr: публичная сеть и запасная почта (net_nostr)
    # ══════════════════════════════════════════════════════════════════ #

    def _nostr_keys(self):
        from net_nostr import seckey_from_seed, pubkey
        if not getattr(self, "nostr_sk", None):
            self.nostr_sk = seckey_from_seed(self.me.seed)
            self.nostr_pub = pubkey(self.nostr_sk)
        return self.nostr_sk, self.nostr_pub

    def _link_sig(self) -> str:
        """Подпись ed25519: «этот ключ Nostr — мой onion». Её проверяет каждый, кто видит профиль или пост."""
        return self.me.sign(f"echoes-nostr-link|{self._nostr_keys()[1]}".encode())

    @staticmethod
    def linked_onion(ev) -> str:
        """onion автора события Nostr, если связь подписана (иначе '')."""
        for t in ev.get("tags") or []:
            if isinstance(t, list) and len(t) >= 3 and t[0] == "echoes-onion":
                onion = normalize_code(str(t[1]))
                if onion and verify(onion, f"echoes-nostr-link|{ev.get('pubkey')}".encode(), str(t[2])):
                    return onion
        return ""

    async def _nostr_start(self):
        from net_nostr import Pool, DEFAULT_RELAYS
        self._nostr_keys()
        for _ in range(180):                                   # подождать Tor (если он будет) — релеи через него
            if self.transports.get("tor") or self.state.get("phase") in ("online", "error", "no_tor", "off"):
                break
            await asyncio.sleep(1)
        socks = self.socks if (self.transports.get("tor") and self.settings.get("nostr_tor", True)
                               and not DEV_DIR) else 0
        urls = [u for u in (self.settings.get("relays") or DEFAULT_RELAYS)
                if str(u).startswith(("wss://", "ws://127.0.0.1", "ws://localhost"))][:10]

        def changed(n):
            self.transports["nostr"] = n
            if self.state.get("online") or n:
                self._set_state("online", 100, self._status_text(), True)
        self.public = {"posts": {}, "profiles": {}, "rooms": {}, "tastes": {}, "likes": {}, "replies": {}, "mods": {}}
        self.nostr = Pool(urls, lambda sid, ev: None, log=self.log, socks=socks, on_change=changed,
                          direct_fallback=self.settings.get("nostr_direct_fallback", True))
        self.nostr.start()
        now = int(time.time())
        await self.nostr.subscribe("dm", [{"kinds": [4], "#p": [self.nostr_pub], "since": now - 7 * 86400}],
                                   self._nostr_dm_sync)
        await self.nostr.subscribe("req", [{"kinds": [4], "#t": [_req_tag(self.me.onion)], "since": now - REQ_DAYS * 86400}],
                                   self._nostr_req_in)
        asyncio.ensure_future(self._nostr_req_flush())
        await self._presence_sub()
        asyncio.ensure_future(self._presence_loop())
        await self.nostr.subscribe("feed", [{"kinds": [1], "#t": ["echoes"], "limit": 200}], self._nostr_note)
        await self.nostr.subscribe("rooms", [{"kinds": [30311], "#t": ["echoes"], "since": now - 3600}],
                                   self._nostr_room)
        await self.nostr.subscribe("taste", [{"kinds": [30078], "#d": ["echoes-taste"], "limit": 300}],
                                   self._nostr_taste)
        await self.nostr.subscribe("react", [{"kinds": [7], "#t": ["echoes"], "limit": 500}], self._nostr_react)
        await self.nostr.subscribe("mods", [{"kinds": [30078], "#t": ["echoes-mod"], "limit": 300}], self._nostr_mod)
        await self.nostr.subscribe("upd", [{"kinds": [30078], "#t": ["echoes-update"], "limit": 20}], self._nostr_update)
        await self.nostr.subscribe("staff", [{"kinds": [30078], "#t": ["echoes-staff"], "limit": 20}], self._nostr_staff)
        await self.nostr.subscribe('radio_permits',[{'kinds':[30078],'#t':['echoes-radio-permit'],'limit':500}],self._nostr_radio_permit)
        await self.nostr.subscribe("modact", [{"kinds": [30078], "#t": ["echoes-modact"], "limit": 3000}],
                                   self._nostr_modact)
        asyncio.ensure_future(self._nostr_announce_loop())

    async def _nostr_sign(self, kind, content, tags, pow_target=0):
        from net_nostr import make_event
        sk, _pub = self._nostr_keys()
        return await asyncio.get_running_loop().run_in_executor(None, make_event, sk, kind, content, tags, pow_target)

    def _ev_ok(self, ev) -> bool:
        from net_nostr import verify_event
        muted = set(self.settings.get("muted") or [])
        return isinstance(ev, dict) and ev.get("pubkey") not in muted and verify_event(ev)

    # ── входящее ── #

    def _nostr_note(self, ev):
        from net_nostr import pow_bits, tag
        if not self._ev_ok(ev) or len(ev.get("content", "")) > MAX_TEXT:
            return
        onion = self.linked_onion(ev)
        friend = bool(onion and self.is_friend(onion)) or onion == self.me.onion
        if onion != self.me.onion and (self.mod_hidden(onion) or self._mod_drop(ev["pubkey"], ev.get("content"))):
            if onion:
                self._strike(onion, "запрещённое в публичном посте") if self.mod_check(ev.get("content")) else None
            return
        reply_to = tag(ev, "e")
        if reply_to:                                           # ответ в треде публичного поста
            if pow_bits(ev["id"]) >= 8 or friend:
                known = ev["id"] in self.public["replies"].get(reply_to, {})
                self.public["replies"].setdefault(reply_to, {})[ev["id"]] = dict(ev, onion=onion)
                self.emit("public", "replies")
                parent = self.public["posts"].get(reply_to) or {}
                if not known and onion != self.me.onion and parent.get("onion") == self.me.onion \
                        and float(ev.get("created_at") or 0) > self.__dict__.get("_t_start", time.time()) - 120:
                    self.emit("notify", {"kind": "comment", "title": self._contact_name(onion) if onion else "Ответ",
                                         "text": clip(ev.get("content"), 160), "onion": onion or "",
                                         "npub": ev["pubkey"], "post": reply_to})
            return
        if pow_bits(ev["id"]) < int(self.settings.get("min_pow", 10)) and not friend:
            return                                             # без «работы» — вероятно спам
        meta = {}
        try:
            meta = json.loads(tag(ev, "echoes") or "{}")
        except ValueError:
            pass
        from net_files import clean_meta
        from net_gif import clean_gif
        files = [x for x in (clean_meta(f) for f in (meta.get("files") or [])[:4]) if x] if onion else []
        if files and self.mod_check(" ".join(f["name"] for f in files)) and not friend:
            self._strike(ev["pubkey"], "запрещённое в названии файла")
            return
        self.public["posts"][ev["id"]] = {"id": ev["id"], "npub": ev["pubkey"], "onion": onion, "ts": ev["created_at"],
                                          "files": files, "gif": clean_gif(meta.get("gif")),
                                          "text": ev["content"], "track": clean_track(meta.get("track")),
                                          "pow": pow_bits(ev["id"]), "friend": friend}
        if len(self.public["posts"]) > 600:
            for k in sorted(self.public["posts"], key=lambda k: self.public["posts"][k]["ts"])[:200]:
                self.public["posts"].pop(k, None)
        self._want_profile(ev["pubkey"])
        self.emit("public", "feed")
        nm = ((self.public.get("profiles") or {}).get(ev["pubkey"]) or {}).get("name") or \
            (self._contact_name(onion) if onion else "")
        self._sub_post(ev["id"], ev["created_at"], onion=onion or "", npub=ev["pubkey"], name=nm,
                       text=ev["content"])

    def _nostr_react(self, ev):
        from net_nostr import tag
        if not self._ev_ok(ev):
            return
        e = tag(ev, "e")
        if e:
            self.public["likes"].setdefault(e, set()).add(ev["pubkey"])
            self.emit("public", "likes")

    def _nostr_room(self, ev):
        from net_nostr import tag
        if not self._ev_ok(ev):
            return
        onion = self.linked_onion(ev)
        exp = tag(ev, "expiration")
        try:
            data = json.loads(tag(ev, "echoes-room") or "{}")
        except ValueError:
            data = {}
        if not isinstance(data,dict):return
        if data.get('radio'):
            from net_radio_auth import accept
            if not isinstance(data['radio'],dict) or not accept(self,onion,data['radio'].get('permit')):return
        key = (ev["pubkey"], tag(ev, "d"))
        if self._mod_drop(ev["pubkey"], tag(ev, "title"), data.get("genre")) or self.mod_hidden(onion):
            self.public["rooms"].pop(key, None)
            return
        if onion:
            self.__dict__.setdefault("_npk_map", {})[onion] = ev["pubkey"]
        live = tag(ev, "status") == "live" and (not exp or int(exp) > time.time()) and onion
        if not live:
            self.public["rooms"].pop(key, None)
        else:
            self.public["rooms"][key] = {"npub": ev["pubkey"], "onion": onion, "title": clip(tag(ev, "title"), 80),
                                         "genre": clip(data.get("genre"), 40), "now": clean_track(data.get("now")),
                                         "radio": self._clean_room_summary(data).get('radio'),
                                         "n": int(clean_sec(data.get("n"), 999) or 1), "exp": int(exp or 0),
                                         "ts": ev["created_at"]}
            self._want_profile(ev["pubkey"])
        self.emit("public", "rooms")

    def _nostr_taste(self, ev):
        if not self._ev_ok(ev):
            return
        onion = self.linked_onion(ev)
        try:
            taste = clean_taste(json.loads(ev.get("content") or "{}"))
        except ValueError:
            taste = None
        if onion and taste and onion != self.me.onion:
            self.public["tastes"][ev["pubkey"]] = {"onion": onion, "taste": taste, "ts": ev["created_at"]}
            self._want_profile(ev["pubkey"])
            self.emit("public", "tastes")

    def _want_profile(self, npub):
        q = self.__dict__.setdefault("_prof_queue", set())
        if npub not in self.public["profiles"] and npub not in self.__dict__.setdefault("_prof_asked", set()):
            q.add(npub)

    def _nostr_profile_full(self, ev):
        """Полный публичный профиль (как у друзей) — для незнакомцев и друзей, с которыми нет прямой связи."""
        if not self._ev_ok(ev):
            return
        onion = self.linked_onion(ev)
        if not onion:
            return
        try:
            raw = json.loads(ev.get("content") or "{}")
        except ValueError:
            return
        prof = clean_profile(raw)
        if not prof or self._mod_drop(ev["pubkey"], prof.get("name"), prof.get("about"), prof.get("status")):
            return
        full = self.public.setdefault("full", {})
        if full.get(onion, {}).get("_ts", 0) >= ev["created_at"]:
            return
        av = raw.get("avatar") if isinstance(raw.get("avatar"), str) else ""
        if av:
            try:
                data = base64.b64decode(av)
                if data[:3] == b"\xff\xd8\xff":
                    self.avatar_dir.mkdir(parents=True, exist_ok=True)
                    (self.avatar_dir / f"{onion[:16]}_pub.jpg").write_bytes(data)
            except (OSError, ValueError):
                pass
        prof["_ts"] = ev["created_at"]
        full[onion] = prof
        self.__dict__.setdefault("_npk_map", {})[onion] = ev["pubkey"]
        self.emit("profile", onion)
        self.emit("public", "profiles")

    def _nostr_pls(self, ev):
        """Открытые плейлисты человека из публичной сети."""
        if not self._ev_ok(ev):
            return
        onion = self.linked_onion(ev)
        if not onion:
            return
        try:
            pls = clean_pls(json.loads(ev.get("content") or "{}").get("pls"))
        except (ValueError, AttributeError):
            return
        store = self.public.setdefault("pls", {})
        if store.get(onion, {}).get("ts", 0) >= ev["created_at"]:
            return
        store[onion] = {"ts": ev["created_at"], "pls": pls}
        self.emit("profile", onion)

    def _nostr_deco(self, ev):
        """Рамка, фон шапки и витрина человека из публичной сети."""
        if not self._ev_ok(ev):
            return
        onion = self.linked_onion(ev)
        if not onion:
            return
        try:
            from net_showcase import clean_deco
            deco = clean_deco(json.loads(ev.get("content") or "{}").get("deco")) or {}
        except (ValueError, AttributeError):
            return
        store = self.public.setdefault("deco", {})
        if store.get(onion, {}).get("ts", 0) >= ev["created_at"]:
            return
        store[onion] = {"ts": ev["created_at"], "deco": deco}
        self.emit("profile", onion)

    def public_deco(self, onion) -> dict:
        """Оформление профиля: своё, из карточки друга или из публичной сети (что новее)."""
        if onion == self.me.onion:
            return dict((self.profile or {}).get("deco") or {})
        prof = self.contact_profile(onion)
        pub = ((self.__dict__.get("public") or {}).get("deco") or {}).get(onion)
        own = prof.get("deco")
        if pub and (own is None or pub.get("ts", 0) > float(prof.get("got") or prof.get("_ts") or 0)):
            return dict(pub.get("deco") or {})
        return dict(own or {})

    def public_playlists(self, onion) -> list:
        """Открытые плейлисты: из профиля друга или из публичной сети (что новее)."""
        if onion == self.me.onion:
            return list((self.profile or {}).get("pls") or [])
        own = self.contact_profile(onion).get("pls")
        if own:
            return own
        return list(((self.public.get("pls") or {}).get(onion) or {}).get("pls") or [])

    # ── подписчики / подписки людей (публично, через Nostr) ──
    # Каждый ECHOES публикует свой список подписок — заменяемое событие с тегами «p» (ключи тех, на кого
    # подписан). Подписки человека — его событие; подписчики — все события, где он отмечен.

    def social(self) -> dict:
        return self.__dict__.setdefault("_social", {"following": {}, "followers": {}})

    async def publish_follows(self):
        nos = getattr(self, "nostr", None)
        if nos is None or not nos.up_count:
            return
        ents = []
        for k, v in self.subs().items():
            npub = k[2:] if k.startswith("n:") else (v.get("npub") or self._npk_for(k))
            if len(npub or "") == 64:
                ents.append({"npub": npub, "onion": "" if k.startswith("n:") else k, "name": v.get("name", "")})
        hidden = bool(self.settings.get("follows_hidden"))
        content = {"hidden": hidden, "list": [] if hidden else ents[:300]}
        tags = [["d", "echoes-follows"], ["t", "echoes-follows"], self._link_tag()] + \
               [["p", e["npub"]] for e in ents[:500]]
        ev = await self._nostr_sign(30078, json.dumps(content, ensure_ascii=False), tags)
        self._nostr_follows(ev)
        await nos.publish(ev)

    def set_follows_hidden(self, on):
        self.settings["follows_hidden"] = bool(on)
        self.save_settings()
        if self.loop is not None:
            self.call(self.publish_follows)

    def _nostr_follows(self, ev):
        from net_nostr import tag
        if not self._ev_ok(ev) or tag(ev, "d") != "echoes-follows":
            return
        a = ev["pubkey"]
        S = self.social()
        old = S["following"].get(a)
        if old and old["ts"] >= ev["created_at"]:
            return
        try:
            c = json.loads(ev.get("content") or "{}")
        except ValueError:
            c = {}
        c = c if isinstance(c, dict) else {}
        ps = list(dict.fromkeys(t[1] for t in ev.get("tags") or []
                                if isinstance(t, list) and len(t) > 1 and t[0] == "p" and len(str(t[1])) == 64))[:500]
        if old:
            for x in old["p"]:
                S["followers"].get(x, {}).pop(a, None)
        onion = self.linked_onion(ev)
        names = {str(x.get("npub")): {"onion": normalize_code(str(x.get("onion") or "")) or "",
                                      "name": clip(x.get("name"), MAX_NAME)}
                 for x in (c.get("list") or [])[:500] if isinstance(x, dict)}
        S["following"][a] = {"ts": ev["created_at"], "p": ps, "hidden": bool(c.get("hidden")), "names": names,
                             "onion": onion}
        if onion:
            self.__dict__.setdefault("_npk_map", {})[onion] = a
        for x in ps:
            S["followers"].setdefault(x, {})[a] = {"onion": onion, "ts": ev["created_at"]}
        self._want_profile(a)
        self.emit("social", a)

    async def social_query(self, npub):
        """Подписки и подписчики человека (ответы приходят событиями «social»)."""
        nos = getattr(self, "nostr", None)
        if nos is None or len(npub or "") != 64:
            return
        flt = [{"kinds": [30078], "#d": ["echoes-follows"], "authors": [npub]},
               {"kinds": [30078], "#t": ["echoes-follows"], "#p": [npub], "limit": 500}]
        known = list((self.social()["followers"].get(npub) or {}))[:200]
        if known:                                              # отписка: у бывшего подписчика новый список без «p»
            flt.append({"kinds": [30078], "#d": ["echoes-follows"], "authors": known})
        await nos.subscribe("soc_" + npub[:12], flt, self._nostr_follows)

    def social_info(self, onion="", npub="") -> dict:
        """{followers: [...], following: [...] | None (скрыты), n_following} — люди: {npub, onion, name}."""
        npub = npub or (self._nostr_keys()[1] if onion == self.me.onion else self._npk_for(onion))
        S = self.social()
        def person(n, onion_=""):
            o = onion_ or next((k for k, v in (self.__dict__.get("_npk_map") or {}).items() if v == n), "")
            prof = (self.public.get("profiles") or {}).get(n) or {}
            name = prof.get("name") or (self._contact_name(o) if o and self.store.contact(o) else "") or \
                ((self.public.get("full") or {}).get(o) or {}).get("name") or ""
            return {"npub": n, "onion": o, "name": name}
        fol = [person(a, v.get("onion", "")) for a, v in sorted((S["followers"].get(npub) or {}).items(),
                                                                key=lambda kv: -kv[1].get("ts", 0))]
        me_ = S["following"].get(npub)
        if onion == self.me.onion or npub == self._nostr_keys()[1]:
            ents = []
            for k, v in self.subs().items():
                n = k[2:] if k.startswith("n:") else (v.get("npub") or self._npk_for(k))
                ents.append({"npub": n or "", "onion": "" if k.startswith("n:") else k,
                             "name": v.get("name") or (self._contact_name(k) if not k.startswith("n:") else "")})
            return {"npub": npub, "followers": fol, "following": ents, "n_following": len(ents),
                    "hidden": bool(self.settings.get("follows_hidden"))}
        if me_ is None:
            return {"npub": npub, "followers": fol, "following": [], "n_following": 0, "hidden": False}
        lst = []
        if not me_["hidden"]:
            for n in me_["p"]:
                x = person(n, (me_["names"].get(n) or {}).get("onion", ""))
                x["name"] = x["name"] or (me_["names"].get(n) or {}).get("name", "")
                lst.append(x)
        return {"npub": npub, "followers": fol, "following": None if me_["hidden"] else lst,
                "n_following": len(me_["p"]), "hidden": me_["hidden"]}

    def _nostr_profile(self, ev):
        if not self._ev_ok(ev):
            return
        try:
            c = json.loads(ev.get("content") or "{}")
        except ValueError:
            return
        e = c.get("echoes") if isinstance(c.get("echoes"), dict) else {}
        onion = normalize_code(str(e.get("onion") or ""))
        if onion and not verify(onion, f"echoes-nostr-link|{ev['pubkey']}".encode(), str(e.get("sig") or "")):
            onion = ""
        if self._mod_drop(ev["pubkey"], c.get("name"), c.get("about"), e.get("status")):
            return
        prof = clean_profile({"name": c.get("name") or c.get("display_name"), "status": e.get("status"),
                              "about": c.get("about"), "fav": e.get("fav"), "avatar": e.get("avatar")}) or {}
        av = prof.pop("avatar", None)
        if av:
            try:
                self.avatar_dir.mkdir(parents=True, exist_ok=True)
                (self.avatar_dir / f"n_{ev['pubkey'][:16]}.jpg").write_bytes(base64.b64decode(av))
                prof["avatar_file"] = str(self.avatar_dir / f"n_{ev['pubkey'][:16]}.jpg")
            except OSError:
                pass
        old = self.public["profiles"].get(ev["pubkey"])
        if old and old.get("ts", 0) >= ev["created_at"]:
            return
        prof.update(onion=onion, npub=ev["pubkey"], ts=ev["created_at"])
        self.public["profiles"][ev["pubkey"]] = prof
        self.emit("public", "profiles")

    def _nostr_dm_sync(self, ev):
        """Конверты через Nostr (зашифрованы ключом пары): сообщения связи «p2p» (см. NostrPeer), большие — частями,
        и запасная почта от друга."""
        from net_crypto import open_
        from net_nostr import tag
        if not self._ev_ok(ev):
            return
        src = normalize_code(str(tag(ev, "echoes") or ""))
        if not src or src == self.me.onion or pub_from_onion(src) is None:
            return
        c0 = self.store.contact(src)
        if c0 and c0["status"] == "blocked":
            return
        content = ev.get("content") or ""
        part = next((t for t in ev.get("tags") or [] if isinstance(t, list) and len(t) >= 4 and t[0] == "part"), None)
        if part is not None:                                   # часть большого сообщения — собрать целиком
            try:
                pid, i, n = str(part[1])[:16], int(part[2]), int(part[3])
            except (TypeError, ValueError):
                return
            if not 0 <= i < n <= 800:
                return
            bufs = self.__dict__.setdefault("_nostr_parts", {})
            key = (src, pid)
            got = bufs.setdefault(key, {"n": n, "t": time.time(), "p": {}})
            got["p"][i] = content
            for k in [k for k, v in bufs.items() if time.time() - v["t"] > 600]:
                bufs.pop(k, None)
            if len(got["p"]) < got["n"]:
                return
            bufs.pop(key, None)
            content = "".join(got["p"][j] for j in range(got["n"]))
        obj = open_(self._env_key(src), content)
        if not isinstance(obj, dict):
            return
        if obj.get("t") == "p2p":
            skew = (self.__dict__.get("_skew") or {}).get(src, 0.0)   # часы друга отстают — поправка
            if time.time() - float(ev.get("created_at") or 0) - skew > NOSTR_P2P_MAX_AGE:
                return                                         # из истории релея — уже не актуально
            m = obj.get("m")
            if not isinstance(m, dict):
                return
            event_ts = float(ev.get("created_at") or 0)
            age = time.time()-event_ts
            offline_ts = self.__dict__.get('_pres_offline_ts', {}).get(src, 0)
            live = -PRESENCE_FUTURE_TOLERANCE <= age < NOSTR_PEER_IDLE and event_ts > offline_ts
            p = self._nostr_attach(src, str(ev.get("pubkey") or ""), received=live, age=max(0., age))
            asyncio.ensure_future(self._handle_safe(p, m))
            return
        if obj.get("t") != "msg" or not self.is_friend(src):
            return
        mid = clip(obj.get("id"), 64)
        if mid and not self.store.has_message(mid):
            ts = min(float(obj.get("ts") or time.time()), time.time() + 60)
            self.store.add_message(mid, src, "in", ts, clip(obj.get("text")), clean_track(obj.get("track")),
                                   delivered=1, extra=clean_extra(obj.get("extra")))
            self.emit("message", src)

    async def _nostr_req_send(self, dest, kind="friend_req") -> bool:
        """Заявка в друзья / «принято» через релеи Nostr: не нужно быть в сети одновременно и не нужен Tor.
        Конверт зашифрован ключом пары (из кодов обоих) — открыть его может только адресат, и он же
        убеждается, что заявка от владельца кода; метка — хэш кода адресата, сам код в событии не виден."""
        from net_crypto import seal
        nos = getattr(self, "nostr", None)
        if nos is None or not nos.up_count:
            return False
        c = self.store.contact(dest) or {}
        payload = {"t": kind, "name": self._name(), "ts": time.time(), "npk": self.__dict__.get("nostr_pub", "")}
        if kind == "friend_req":
            payload["note"] = clip(c.get("note"), 200)
        try:
            ev = await self._nostr_sign(4, seal(self._env_key(dest), payload),
                                        [["t", _req_tag(dest)], ["echoes", self.me.onion]])
            ok = await nos.publish(ev) > 0
        except Exception as e:                                 # noqa: BLE001
            self.log(f"[net] nostr req {dest[:8]}: {type(e).__name__} {e}")
            return False
        if ok:
            self.__dict__.setdefault("_req_sent", {})[dest] = time.time()
        return ok

    async def _nostr_req_flush(self):
        """После подключения к релеям: разослать свои неотвеченные заявки (не чаще раза в 6 часов на друга)."""
        for _ in range(60):
            nos = getattr(self, "nostr", None)
            if nos is not None and nos.up_count:
                break
            await asyncio.sleep(2)
        sent = self.__dict__.setdefault("_req_sent", {})
        for c in self.store.contacts("pending_out"):
            if time.time() - sent.get(c["onion"], 0) > 6 * 3600:
                await self._nostr_req_send(c["onion"], "friend_req")

    def _nostr_req_in(self, ev):
        """Заявка / «принято» из Nostr (см. _nostr_req_send)."""
        from net_crypto import open_
        from net_nostr import tag
        if not self._ev_ok(ev):
            return
        src = normalize_code(str(tag(ev, "echoes") or ""))
        if not src or src == self.me.onion or pub_from_onion(src) is None:
            return
        obj = open_(self._env_key(src), ev.get("content") or "")
        if not isinstance(obj, dict) or obj.get("t") not in ("friend_req", "friend_ok"):
            return
        c = self.store.contact(src)
        if c and c["status"] == "blocked":
            return
        npk = str(ev.get("pubkey") or "")
        name = clip(obj.get("name"), MAX_NAME)
        status = c["status"] if c else None
        if obj["t"] == "friend_ok":
            if status == "pending_out":
                self.store.upsert_contact(src, status="friend", name=name or c["name"], npk=npk)
                self.emit("contacts")
                self.emit("notify", {"kind": "request", "title": name or src[:8], "text": "теперь ваш друг", "onion": src})
                self.poke(src)
            elif status == "friend" and npk and not c.get("npk"):
                self.store.upsert_contact(src, npk=npk)
            return
        # friend_req
        if status == "friend":
            if npk and not c.get("npk"):
                self.store.upsert_contact(src, npk=npk)
            if time.time() - self.__dict__.setdefault("_req_sent", {}).get(src, 0) > 600:
                asyncio.ensure_future(self._nostr_req_send(src, "friend_ok"))   # друг не получил наше «принято»
            return
        if status == "pending_out":                            # оба добавили друг друга — сразу друзья
            self.store.upsert_contact(src, status="friend", name=name, npk=npk)
            self.store.outbox_add(src, {"t": "friend_ok", "name": self._name()})
            asyncio.ensure_future(self._nostr_req_send(src, "friend_ok"))
            self.poke(src)
            self.emit("contacts")
            self.emit("notify", {"kind": "request", "title": name or src[:8], "text": "теперь ваш друг", "onion": src})
            return
        if status == "pending_in":
            if npk:
                self.store.upsert_contact(src, npk=npk)
            return
        if self._devpair(src, obj.get("note"), name):
            return
        if len(self.store.contacts("pending_in")) >= 50:
            return
        if self._mod_drop(src, obj.get("name"), obj.get("note")):
            return
        self.store.upsert_contact(src, status="pending_in", name=name, note=clip(obj.get("note"), 200), npk=npk)
        self.poke(src)
        self.emit("contacts")
        self.emit("notify", {"kind": "request", "title": name or src[:8], "text": "хочет добавить вас в друзья",
                             "onion": src, "tab": "friends"})

    async def _handle_safe(self, p, m):
        try:
            await self._handle(p, m)
        except Exception as e:                                 # noqa: BLE001
            self.log(f"[net] handle {m.get('t')} (nostr): {type(e).__name__} {e}")

    def _npk_for(self, onion) -> str:
        npk = (self.store.contact(onion) or {}).get("npk") or self.__dict__.get("_npk_map", {}).get(onion, "")
        return npk if npk_ok(npk) else ""

    def _nostr_attach(self, onion, npk, received=False, age=0.):
        """Связь через Nostr с этим собеседником (если лучшей нет). Возвращает текущее соединение."""
        p = self.peers.get(onion)
        if p is not None and p.alive:
            if p.via == "nostr":
                if received:self._received(p, age)
                if npk_ok(npk):
                    p.npk = npk
            return p
        npk = npk if npk_ok(npk) else self._npk_for(onion)
        p = NostrPeer(self, onion, npk)
        if received:self._received(p, age)
        self.peers[onion] = p
        if npk and self.store.contact(onion) and (self.store.contact(onion).get("npk") or "") != npk:
            self.store.upsert_contact(onion, npk=npk)
        asyncio.ensure_future(self._greet(p))
        asyncio.ensure_future(self._udp_offer(p))
        self.emit("presence", onion)
        return p

    # ── прямой UDP через пробивание NAT (net_udp) ── #

    async def _udp_offer(self, p, reply=False):
        """Отправить свои UDP-адреса (через текущую связь) — оба начнут пробивать NAT навстречу."""
        udp = getattr(self, "udp", None)
        if udp is None or udp.alive(p.onion):
            return
        for _ in range(20):                                    # дождаться ответа STUN (внешний адрес)
            if udp.public:
                break
            await asyncio.sleep(0.25)
        udp.add_peer(p.onion, self._env_key(p.onion), [])
        p.udp_offer_t = time.time()
        await p.send({"t": "udp_offer", "c": udp.candidates(), "r": 1 if reply else 0})

    def _udp_opened(self, onion, addr):
        self.log(f"[net] udp {onion[:8]}: прямой канал открыт ({addr[0]})")
        self.emit("presence", onion)

    def _udp_message(self, onion, obj):
        p = self.peers.get(onion)
        if p is None:
            npk = self._npk_for(onion)
            if not npk:
                return
            p = self._nostr_attach(onion, npk)
        self._received(p)
        asyncio.ensure_future(self._handle_safe(p, obj))

    def udp_alive(self, onion) -> bool:
        udp = getattr(self, "udp", None)
        return bool(udp is not None and udp.alive(onion))

    def fast_path(self, onion) -> bool:
        """Есть ли с ним быстрый путь (Tor / напрямую / UDP) — файлы и голос идут только так."""
        p = self.peers.get(onion)
        return bool(p and p.alive and (p.via != "nostr" or self.udp_alive(onion)))

    async def _nostr_p2p(self, dest, npk, obj) -> bool:
        """Одно сообщение связи через релеи: зашифровано ключом пары; больше NOSTR_PART — частями."""
        from net_crypto import seal
        nos = getattr(self, "nostr", None)
        if nos is None or not nos.up_count or not npk_ok(npk):
            return False
        content = seal(self._env_key(dest), {"t": "p2p", "m": obj})
        base = [["p", npk], ["echoes", self.me.onion]]
        if len(content) <= NOSTR_PART:
            return await nos.publish(await self._nostr_sign(4, content, base)) > 0
        pid = secrets.token_hex(6)
        parts = [content[i:i + NOSTR_PART] for i in range(0, len(content), NOSTR_PART)]
        ok = True
        for i, chunk in enumerate(parts):
            ev = await self._nostr_sign(4, chunk, base + [["part", pid, str(i), str(len(parts))]])
            ok = (await nos.publish(ev) > 0) and ok
            await asyncio.sleep(0.15)                          # не заваливать релеи — у них лимиты
        return ok

    # ── «сердцебиение»: кто в сети (вместо соединения через Tor) ── #

    async def _presence_sub(self):
        """Подписка на «сердцебиение» друзей (и тех, кому отправлена заявка)."""
        nos = getattr(self, "nostr", None)
        if nos is None:
            return
        npks = sorted({c.get("npk") for c in self.store.contacts() if c["status"] in ("friend", "pending_out", "pending_in")
                       and len(c.get("npk") or "") == 64})
        if npks == self.__dict__.get("_presence_npks"):
            return
        self._presence_npks = npks
        if npks:
            # без узкого «since»: событие заменяемое (у релея по одному на друга), а часы у друга могут отставать
            await nos.subscribe("presence", [{"kinds": [30078], "#d": ["echoes-presence"], "authors": npks,
                                              "since": int(time.time()) - PRESENCE_SKEW}], self._nostr_presence)

    # ── обновления ECHOES через сеть (net_update) ── #

    upd = None                                                 # предложенное обновление (см. _upd_man_in)
    _upd_mine_id = ""

    @property
    def app_dir(self):
        import net_update
        return Path(self.__dict__.get("_app_dir") or net_update.APP_DIR)

    @property
    def upd_home(self):
        return self.base / "update"

    def upd_trusted(self) -> list:
        import net_update
        t = self.settings.get("upd_trust")
        t = [x for x in t if isinstance(x, str)] if isinstance(t, list) else []
        if net_update.DEV_ONION not in t and not self.settings.get("upd_no_dev"):
            t.append(net_update.DEV_ONION)
        return t

    def upd_set_trust(self, onion, on=True):
        import net_update
        t = [x for x in self.upd_trusted() if x != onion]
        if on:
            t.append(onion)
        if onion == net_update.DEV_ONION:
            self.settings["upd_no_dev"] = not on
        self.settings["upd_trust"] = [x for x in t if x != net_update.DEV_ONION]
        self.save_settings()
        if on and self.upd and self.upd.get("pub") == onion and not self.upd.get("trusted"):
            self.upd["trusted"] = True
            self.emit("update", self.upd_view())

    async def _upd_mine(self):
        """Манифест своей установленной сборки — если файлы с ним совпадают (иначе делиться нечем)."""
        import net_update
        man = net_update.current_manifest(self.upd_home)
        if not man:
            return None
        mid = net_update.man_id(man)
        if self.__dict__.get("_upd_checked") != mid:
            loop = asyncio.get_running_loop()
            local = await loop.run_in_executor(None, net_update.scan, self.app_dir, self.upd_home)
            ok = all((local.get(r) or [None])[0] == v[0] for r, v in man["files"].items())
            self._upd_checked, self._upd_ok = mid, ok
        if not self.__dict__.get("_upd_ok"):
            return None
        self._upd_mine_id = mid
        return man

    async def _upd_have(self):
        man = await self._upd_mine()
        if man is None:
            return None
        return {"t": "upd_have", "id": self._upd_mine_id, "ts": man.get("ts"), "ver": clip(man.get("ver"), 40),
                "pub": man.get("pub")}

    def _upd_installed_ts(self) -> float:
        import net_update
        st = net_update.installed(self.app_dir)
        man = net_update.current_manifest(self.upd_home) or {}
        return max(float(st.get("ts") or 0), float(man.get("ts") or 0) if st.get("id") == net_update.man_id(man)
                   else 0.0)

    async def _upd_have_in(self, p, m):
        try:
            ts = float(m.get("ts") or 0)
        except (TypeError, ValueError):
            return
        uid = clip(m.get("id"), 16)
        if not uid or ts <= self._upd_installed_ts() + 1 or uid in (self.settings.get("upd_skip") or []):
            return
        u = self.upd
        if u and u.get("id") == uid:
            if p.onion not in u["from"]:
                u["from"].append(p.onion)                      # ещё один друг, у которого она есть
            if u.get("state") == "error" and u.get("man"):
                u.update(state="offer", why="")
                self.emit("update", self.upd_view())
            return
        if u and float(u.get("ts") or 0) >= ts and u.get("state") in ("downloading", "ready"):
            return
        asked = self.__dict__.setdefault("_upd_asked", {})
        if time.time() - asked.get((p.onion, uid), 0) < 600:
            return
        asked[(p.onion, uid)] = time.time()
        await p.send({"t": "upd_man?", "id": uid})

    async def _upd_man_in(self, p, man):
        import net_update
        if not isinstance(man, dict) or not verify_obj(man, "pub"):
            return
        uid = net_update.man_id(man)
        if (self.__dict__.get("_upd_asked") or {}).get((p.onion, uid)) is None:
            return                                             # не просили
        try:
            ts = float(man.get("ts") or 0)
        except (TypeError, ValueError):
            return
        if ts <= self._upd_installed_ts() + 1:
            return
        await self._upd_offer(man, p.onion)

    async def _upd_offer(self, man, src, npk=""):
        """Пришёл манифест (от друга или из публичного объявления): проверить и предложить."""
        import net_update
        uid = net_update.man_id(man)
        ts = float(man.get("ts") or 0)
        if ts <= self._upd_installed_ts() + 1 or uid in (self.settings.get("upd_skip") or []):
            return
        u = self.upd
        if u and u.get("id") == uid:
            if src not in u["from"]:
                u["from"].append(src)
            if npk:
                u.setdefault("npk", {})[src] = npk
            return
        if u and float(u.get("ts") or 0) >= ts and u.get("state") in ("downloading", "ready", "checking"):
            return
        pub = str(man.get("pub") or "")
        why = net_update.check(man, [pub])                     # устройство и подпись; доверие — отдельно
        if why:
            self.log(f"[net] обновление от {src[:8]} отклонено: {why}")
            return
        loop = asyncio.get_running_loop()
        need = await loop.run_in_executor(None, net_update.needed, man, self.app_dir, self.upd_home)
        if not need:                                           # такие файлы уже стоят (поставили вручную)
            await loop.run_in_executor(None, self._upd_mark_installed, man)
            return
        self.upd = {"id": uid, "man": man, "ts": ts, "ver": clip(man.get("ver"), 40), "pub": pub,
                    "note": clip(man.get("note"), 500), "from": [src], "npk": {src: npk} if npk else {}, "need": need,
                    "public": bool(man.get("public")),
                    "size": net_update.need_size(man, need), "trusted": pub in self.upd_trusted(),
                    "state": "offer", "why": "", "got": {}, "n": 0, "stage": "", "tries": 0}
        self.log(f"[net] доступно обновление {uid} от {pub[:8]}: файлов {len(need)}")
        if man.get("public"):
            asyncio.ensure_future(self._upd_seed_sub(uid))
        self.emit("update", self.upd_view())
        if self.upd["trusted"]:
            self.emit("notify", {"kind": "update", "title": "Обновление ECHOES" + (f" {self.upd['ver']}" if
                                                                                  self.upd["ver"] else ""),
                                 "text": (self.upd["note"] or f"изменилось файлов: {len(need)}") +
                                 f" · от {self._contact_name(pub) if self.store.contact(pub) else pub[:8]}",
                                 "onion": pub if self.store.contact(pub) else "", "tab": "update"})

    def _upd_mark_installed(self, man):
        import net_update
        uid = net_update.man_id(man)
        st = {"id": uid, "ts": man.get("ts"), "ver": man.get("ver"), "pub": man.get("pub"),
              "note": man.get("note", ""), "at": time.time()}
        (self.app_dir / net_update.STATE_NAME).write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        net_update.save_current(man, self.upd_home)
        self._upd_checked = None

    def upd_view(self) -> dict | None:
        u = self.upd
        if not u:
            return None
        got = sum(len(x) for x in u["got"].values())
        return {k: u.get(k) for k in ("id", "ver", "pub", "note", "size", "trusted", "state", "why", "stage", "n",
                                      "done_bytes", "total")} | \
            {"files": len(u["need"]), "from": list(u["from"]), "chunks": len(u["got"]), "bytes": got}

    async def upd_download(self):
        u = self.upd
        if not u or u.get("state") not in ("offer", "error"):
            return
        if not u.get("trusted"):
            self._upd_fail("автор обновления не в доверенных")
            return
        u.update(state="downloading", why="", got={}, n=0, tries=0, t_rx=time.time())
        self.emit("update", self.upd_view())
        from net_upd_xfer import Downloader
        old = self.__dict__.get("_upd_dl")
        if old is not None:
            old.stopped = True
        dl = self._upd_dl = Downloader(self, u)
        try:
            await dl.run()
        except Exception as e:                                 # noqa: BLE001
            self.log(f"[net] обновление: {type(e).__name__} {e}")
            self._upd_fail(f"ошибка загрузки: {e}")
        finally:
            if self.__dict__.get("_upd_dl") is dl:
                self._upd_dl = None

    def _upd_peer_ok(self, o) -> bool:
        """Обновление: тот, у кого качаем, или тот, кто качает у нас, — ему можно открыть прямой UDP-канал."""
        u = self.upd
        if u and o in (u.get("from") or []):
            return True
        srv = self.__dict__.get("_upd_srv")
        return bool(srv is not None and o in srv.queues)

    def _upd_server(self):
        srv = self.__dict__.get("_upd_srv")
        if srv is None:
            from net_upd_xfer import Server
            srv = self._upd_srv = Server(self)
        return srv

    def _udp_data(self, onion, body):
        dl = self.__dict__.get("_upd_dl")
        if dl is not None:
            dl.on_udp(onion, body)

    def _upd_source(self):
        """Откуда качать: уже на связи и быстрый путь — лучше; автор — последним (разгрузить его)."""
        import random
        u = self.upd
        tried = u.setdefault("tried", [])
        live = [self.peers[o] for o in u["from"] if o in self.peers and self.peers[o].alive]
        live.sort(key=lambda p: (p.via == "nostr", p.onion in tried, p.onion == u["pub"], random.random()))
        if live and not (live[0].via == "nostr" and live[0].onion in tried):
            return live[0]
        cand = [o for o in u["from"] if o not in self.peers and (u.get("npk") or {}).get(o)]
        cand.sort(key=lambda o: (o in tried, o == u["pub"], random.random()))
        if cand:
            return self._nostr_attach(cand[0], u["npk"][cand[0]])
        return live[0] if live else None

    async def _upd_request(self, only=None):
        u = self.upd
        p = self._upd_source()
        if p is None:
            self._upd_fail("друга с обновлением нет в сети — попробуйте, когда он появится")
            return
        u["src"] = p.onion
        u.setdefault("tried", []).append(p.onion)
        u["t_rx"] = time.time()
        msg = {"t": "upd_get", "id": u["id"], "files": u["need"]}
        if only:
            msg["only"] = only[:2000]
        await p.send(msg)

    async def _upd_resume(self):
        u = self.upd
        u["tries"] = u.get("tries", 0) + 1
        if u["tries"] > UPD_TRIES:
            self._upd_fail("передача обновления оборвалась — попробуйте ещё раз")
            return
        missing = [i for i in range(u["n"]) if i not in u["got"]] if u["n"] else None
        self.log(f"[net] обновление: докачка, не хватает кусков {len(missing) if missing else 'всех'}")
        await self._upd_request(missing)

    def _upd_fail(self, why):
        u = self.upd
        if u:
            u.update(state="error", why=why)
            self.log(f"[net] обновление: {why}")
            self.emit("update", self.upd_view())

    async def _upd_send(self, p, m):
        import net_update, base64
        uid = clip(m.get("id"), 16)
        man = await self._upd_mine()
        if man is None or uid != self._upd_mine_id:
            await p.send({"t": "upd_err", "id": uid, "why": "у друга уже другая сборка"})
            return
        if not self.is_friend(p.onion) and not man.get("public"):
            await p.send({"t": "upd_err", "id": uid, "why": "эта сборка только для друзей"})
            return
        files = [r for r in (m.get("files") or [])[:net_update.MAX_FILES] if isinstance(r, str) and r in man["files"]]
        if not files:
            return
        serving = self.__dict__.setdefault("_upd_serving", set())
        last = self.__dict__.setdefault("_upd_sent", {})
        if time.time() - last.get((p.onion, bool(m.get("only"))), 0) < 20:
            return                                             # не чаще — защита от лавины запросов
        last[(p.onion, bool(m.get("only")))] = time.time()
        key = (uid, tuple(sorted(files)))
        cache = self.__dict__.setdefault("_upd_blobs", {})
        blob = cache.get(key)
        if blob is None:
            blob = await asyncio.get_running_loop().run_in_executor(None, net_update.pack, man, files, self.app_dir)
            cache.clear()
            cache[key] = blob
        nostr = p.via == "nostr"
        via_udp = nostr and self.udp_alive(p.onion)           # старые версии: прямой UDP-канал вместо релеев
        if len(blob) > net_update.MAX_BLOB_FAST:
            await p.send({"t": "upd_err", "id": uid, "why": "обновление слишком большое для старой версии"})
            return
        step = 800 if via_udp else (net_update.CHUNK_NOSTR if nostr else net_update.CHUNK_FAST)
        if via_udp and (len(blob) + step - 1) // step > 20000:
            via_udp, step = False, net_update.CHUNK_NOSTR
        n = max(1, (len(blob) + step - 1) // step)
        only = m.get("only")
        idx = [int(i) for i in only if isinstance(i, int) and 0 <= i < n] if isinstance(only, list) else range(n)
        self.log(f"[net] обновление {uid} → {p.onion[:8]}: {len(blob)} Б, кусков {len(idx)} ({p.via})")
        serving.add(p.onion)
        try:
            for k, i in enumerate(idx):
                if not p.alive:
                    return
                msg = {"t": "upd_blob", "id": uid, "i": i, "n": n, "size": len(blob),
                       "d": base64.b64encode(blob[i * step:(i + 1) * step]).decode()}
                if via_udp and self.udp_alive(p.onion):
                    self.udp.send(p.onion, msg)
                    if k % 8 == 7:
                        await asyncio.sleep(0.004)             # ~1.5 МБ/с, без переполнения буфера
                    continue
                await p.send(msg)
                if nostr and k >= 5:
                    await asyncio.sleep(1.7)                   # у релеев лимит частоты
                else:
                    await asyncio.sleep(0)
        finally:
            serving.discard(p.onion)

    async def _upd_blob_in(self, p, m):
        import net_update, base64
        u = self.upd
        if not u or u.get("state") != "downloading" or clip(m.get("id"), 16) != u["id"] or p.onion not in u["from"]:
            return
        try:
            i, n, size = int(m.get("i")), int(m.get("n")), int(m.get("size"))
            data = base64.b64decode(str(m.get("d") or ""), validate=True)
        except (TypeError, ValueError):
            return
        if not 0 <= i < n <= 20000 or size > net_update.MAX_BLOB_FAST or (u["n"] and n != u["n"]):
            return
        u["n"] = n
        u["got"][i] = data
        u["t_rx"] = time.time()
        if time.time() - u.get("t_emit", 0) > 0.4 or len(u["got"]) == n:
            u["t_emit"] = time.time()
            self.emit("update", self.upd_view())
        if len(u["got"]) < n:
            return
        blob = b"".join(u["got"][j] for j in range(n))
        if len(blob) != size:
            self._upd_fail("обновление пришло повреждённым")
            return
        u["state"] = "checking"
        self.emit("update", self.upd_view())
        try:
            stage = await asyncio.get_running_loop().run_in_executor(None, net_update.stage, u["man"], blob, u["need"], self.upd_home)
        except Exception as e:                                 # noqa: BLE001
            self._upd_fail(f"проверка не прошла: {e}")
            return
        u.update(state="ready", stage=str(stage), got={})
        self.log(f"[net] обновление {u['id']} скачано и проверено: {stage}")
        self.emit("update", self.upd_view())

    def upd_skip(self):
        u = self.upd
        if u:
            sk = [x for x in (self.settings.get("upd_skip") or []) if isinstance(x, str)][-20:]
            self.settings["upd_skip"] = sk + [u["id"]]
            self.save_settings()
            self.upd = None
            self.emit("update", None)

    async def _upd_auto_bridge(self):
        """Мост для старых версий (до 2026.11.02-28), которые умеют обновляться только через Echoes.NET: у автора
        ECHOES узел сам, без кнопок и уведомлений, раздаёт текущую сборку — раз на каждую новую версию. Получив её,
        старые версии дальше обновляются с GitHub. Раздачи вручную больше нет."""
        import net_update
        if self.me.onion != net_update.DEV_ONION or self.__dict__.get("_upd_bridging"):
            return
        ver = net_update.app_version(self.app_dir)
        if not ver or self.settings.get("upd_auto_ver") == ver:
            return
        self._upd_bridging = True
        try:
            await self.upd_publish("Новая версия ECHOES. Дальше обновления приходят с GitHub — кнопка «Обновить» "
                                   "в шапке окна.", public=True, silent=True)
            self.settings["upd_auto_ver"] = ver
            self.save_settings()
            self.log(f"[net] сборка {ver} тихо разослана старым версиям")
        except Exception as e:                                 # noqa: BLE001
            self.log(f"[net] автораздача: {e}")
        finally:
            self._upd_bridging = False

    async def upd_publish(self, note="", public=False, silent=False):
        """«Разослать обновление»: подписать список файлов своей сборки и сообщить друзьям в сети.
        public — ещё и всем пользователям ECHOES (через релеи Nostr; доверяют по умолчанию только автору ECHOES)."""
        import net_update
        loop = asyncio.get_running_loop()
        try:
            man = await loop.run_in_executor(None, net_update.make_manifest, self.me, note, self.app_dir, self.upd_home,
                                             bool(public))
            await loop.run_in_executor(None, self._upd_mark_installed, man)
        except Exception as e:                                 # noqa: BLE001
            if silent:
                raise
            self.emit("toast", f"Не получилось подготовить обновление: {e}")
            return
        have = await self._upd_have()
        n = 0
        for p in list(self.peers.values()):
            if p.alive and self.is_friend(p.onion) and have:
                await p.send(have)
                n += 1
        pub_n = 0
        if public:
            pub_n = await self._upd_announce(man)
            await self._upd_seed_send(force=True)
            asyncio.ensure_future(self._upd_mirror(man, quiet=silent))
        if not silent:
            self.emit("update_pub", {"id": net_update.man_id(man), "files": len(man["files"]), "sent": n,
                                     "ver": man.get("ver"), "public": bool(public), "relays": pub_n})

    async def _upd_mirror(self, man, quiet=False):
        """Своё публичное обновление — на зеркала Blossom: его скачают, даже когда вы не в сети.
        Файлы адресуются SHA-256, поэтому уже лежащие там (из прошлых версий) второй раз не грузятся."""
        import net_update, net_mirror
        if not man.get("public") or man.get("pub") != self.me.onion or self.__dict__.get("_upd_mirroring"):
            return
        uid = net_update.man_id(man)
        if self.settings.get("upd_mirrored") == uid:
            return
        self._upd_mirroring = True
        loop = asyncio.get_running_loop()
        try:
            local = await loop.run_in_executor(None, net_update.scan, self.app_dir, self.upd_home)
            files = [(self.app_dir / rel, v[0], int(v[1])) for rel, v in man["files"].items()
                     if (local.get(rel) or [None])[0] == v[0]]          # файл с тех пор не меняли
            if not quiet:
                self.emit("toast", f"Выкладываю обновление на зеркала ({len(files)} файлов) — "
                                   "его смогут скачать, даже когда вы не в сети")
            sk, _pk = self._nostr_keys()
            step = max(1, len(files) // 4)

            def prog(d, t):
                if d % step == 0 or d == t:
                    self.log(f"[net] зеркала: {d}/{t}")
            res = await loop.run_in_executor(None, net_mirror.mirror_files, sk, files, prog, lambda: self._stop)
        except Exception as e:                                 # noqa: BLE001
            self.log(f"[net] зеркала: {type(e).__name__} {e}")
            return
        finally:
            self._upd_mirroring = False
        bad = [sha for sha, srv in res.items() if not srv]
        if not bad and len(files) == len(man["files"]):
            self.settings["upd_mirrored"] = uid
            self.save_settings()
            self.emit("toast", "Обновление на зеркалах: качается, даже когда вы не в сети")
        elif not quiet:
            self.emit("toast", f"На зеркала не загрузилось файлов: {len(bad) + len(man['files']) - len(files)} — "
                               "докачаю при следующем запуске сети")
        self.log(f"[net] зеркала: {uid} — не загрузилось {len(bad)}")

    async def _upd_announce(self, man) -> int:
        import zlib, base64
        nos = getattr(self, "nostr", None)
        if nos is None or not nos.up_count:
            self.emit("toast", "Публичная сеть (Nostr) сейчас недоступна — разослано только друзьям")
            return 0
        blob = base64.b64encode(zlib.compress(json.dumps(man, ensure_ascii=False).encode("utf-8"), 9)).decode()
        ev = await self._nostr_sign(30078, blob, [["d", "echoes-update"], ["t", "echoes-update"], self._link_tag()])
        return await nos.publish(ev, urgent=True)

    def _nostr_update(self, ev):
        """Публичное объявление обновления: манифест подписан автором — проверяем его подпись и доверие."""
        import zlib, base64
        import net_update
        if not self._ev_ok(ev) or len(ev.get("content") or "") > 400000:
            return
        try:
            man = json.loads(zlib.decompress(base64.b64decode(ev["content"]), bufsize=1 << 20).decode("utf-8"))
        except Exception:                                      # noqa: BLE001
            return
        if not isinstance(man, dict) or not verify_obj(man, "pub") or not man.get("public") \
                or man.get("pub") not in self.upd_trusted():
            return
        src = self.linked_onion(ev)
        if not src or src == self.me.onion:
            return
        asyncio.ensure_future(self._upd_offer(man, src, ev["pubkey"]))

    async def _upd_seed_send(self, force=False):
        """Установили публичную сборку — сообщить, что её можно взять и у нас (разгрузить автора)."""
        if not force and time.time() - self.__dict__.get("_upd_seed_t", 0) < 6 * 3600:
            return
        nos = getattr(self, "nostr", None)
        man = await self._upd_mine()
        if nos is None or not nos.up_count or man is None or not man.get("public") \
                or not self.settings.get("upd_seed", True):
            return
        self._upd_seed_t = time.time()
        ev = await self._nostr_sign(30078, json.dumps({"id": self._upd_mine_id}),
                                    [["d", "echoes-seed"], ["t", "echoes-seed-" + self._upd_mine_id], self._link_tag()])
        await nos.publish(ev)

    async def _upd_seed_sub(self, uid):
        nos = getattr(self, "nostr", None)
        if nos is None:
            return
        await nos.subscribe("updseed", [{"kinds": [30078], "#t": ["echoes-seed-" + uid],
                                         "since": int(time.time()) - 7 * 86400, "limit": 60}], self._nostr_seed)

    def _nostr_seed(self, ev):
        u = self.upd
        if not u or not self._ev_ok(ev):
            return
        try:
            if json.loads(ev.get("content") or "{}").get("id") != u["id"]:
                return
        except ValueError:
            return
        src = self.linked_onion(ev)
        if src and src != self.me.onion and src not in u["from"] and len(u["from"]) < 200:
            u["from"].append(src)
            u.setdefault("npk", {})[src] = ev["pubkey"]

    async def upd_ask(self):
        for p in list(self.peers.values()):
            if p.alive and self.is_friend(p.onion):
                await p.send({"t": "upd_ask"})

    # ── модерация Echoes.NET: админ (автор ECHOES) и назначенные им модераторы ── #
    # Права проверяются подписью ed25519: список модераторов подписывает админ, действия — сам модератор.
    # Подделать нельзя — ключ админа только у него. Состояние: <net>/staff.json (работает и без сети).

    @property
    def admin_onion(self) -> str:
        import net_update
        return net_update.DEV_ONION

    def _staff_load(self):
        st = self.__dict__.get("_staff")
        if st is None:
            try:
                st = json.loads((self.base / "staff.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                st = {}
            st = st if isinstance(st, dict) else {}
            ml = st.get("mods") if self._modlist_ok(st.get("mods")) else None
            acts = {k: a for k, a in (st.get("acts") or {}).items() if isinstance(a, dict) and verify_obj(a, "by")}
            st = self._staff = {"mods": ml, "acts": acts}
        return st

    def _staff_save(self):
        try:
            (self.base / "staff.json").write_text(json.dumps(self._staff_load(), ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def _modlist_ok(self, ml) -> bool:
        return isinstance(ml, dict) and ml.get("t") == "echoes-mods" and ml.get("pub") == self.admin_onion \
            and isinstance(ml.get("mods"), dict) and verify_obj(ml, "pub")

    def mods(self) -> dict:
        ml = self._staff_load().get("mods") or {}
        return ml.get("mods") or {}

    def role(self, onion) -> str:
        """'admin' / 'mod' / '' — значок у ника и права."""
        if not onion:
            return ""
        if onion == self.admin_onion:
            return "admin"
        return "mod" if onion in self.mods() else ""

    def my_role(self) -> str:
        return self.role(self.me.onion)

    def _take_modlist(self, ml) -> bool:
        if not self._modlist_ok(ml):
            return False
        cur = self._staff_load().get("mods")
        if cur and float(cur.get("ts") or 0) >= float(ml.get("ts") or 0):
            return False
        self._staff["mods"] = ml
        self._staff_save()
        self.emit("staff", None)
        return True

    def _act_ok(self, a) -> bool:
        if not isinstance(a, dict) or a.get("t") != "echoes-modact" or not verify_obj(a, "by"):
            return False
        by, target = a.get("by"), str(a.get("target") or "")
        if a.get("act") not in MOD_ACTS or not target or len(target) > 80:
            return False
        r = self.role(by)
        if not r:
            return False
        if a.get("kind") == "user" and self.role(target) and r != "admin":
            return False                                       # модератор не трогает админа и других модераторов
        if target == self.admin_onion:
            return False
        return True

    def _take_act(self, a) -> bool:
        if not self._act_ok(a):
            return False
        acts = self._staff_load()["acts"]
        cur = acts.get(a["target"])
        if cur and float(cur.get("ts") or 0) >= float(a.get("ts") or 0):
            return False
        acts[a["target"]] = a
        if len(acts) > 5000:
            for k in sorted(acts, key=lambda k: float(acts[k].get("ts") or 0))[:500]:
                acts.pop(k, None)
        self._staff_save()
        self.emit("staff", a["target"])
        self.emit("feed")
        self.emit("public", "feed")
        return True

    def staff_hidden(self, *ids) -> str:
        """Скрыто модерацией ECHOES (пост скрыт / автор заблокирован) → причина или ''."""
        acts = self._staff_load()["acts"]
        for i in ids:
            a = acts.get(i) if i else None
            if a and a.get("act") in ("hide", "ban") and self._act_ok(a):
                who = "администратором" if self.role(a["by"]) == "admin" else "модератором"
                return f"скрыто {who} ECHOES" + (f": {a.get('why')}" if a.get("why") else "")
        return ""

    def banned(self) -> list:
        return [a for a in self._staff_load()["acts"].values() if a.get("act") == "ban" and self._act_ok(a)]

    def hidden_posts(self) -> list:
        return [a for a in self._staff_load()["acts"].values() if a.get("act") == "hide" and self._act_ok(a)]

    async def staff_act(self, act, target, kind, why="", extra=None):
        """Действие модерации (из интерфейса): hide/unhide поста, ban/unban пользователя."""
        if not self.my_role():
            self.emit("toast", "Нет прав модератора")
            return
        a = {"t": "echoes-modact", "act": act, "target": clip(target, 80), "kind": kind, "by": self.me.onion,
             "ts": time.time(), "why": clip(why, 120)}
        if isinstance(extra, dict):
            a["info"] = {k: clip(str(v), 120) for k, v in list(extra.items())[:6]}
        a = self.me.sign_obj(a)
        if not self._take_act(a):
            self.emit("toast", "Это действие недоступно")
            return
        n = await self._staff_publish(a, "echoes-modact", "echoes-modact:" + a["target"][:60])
        await self._broadcast_friends({"t": "staff", "acts": [a]})
        self.emit("toast", {"hide": "Пост скрыт для всех", "unhide": "Пост снова виден",
                            "ban": "Пользователь заблокирован в Echoes.NET", "unban": "Блокировка снята"}[act] +
                  (f" · релеев: {n}" if n else " · публичная сеть недоступна — разошлётся друзьям"))

    async def set_mod(self, onion, name="", on=True):
        """Только админ: выдать или снять модерку."""
        if self.my_role() != "admin":
            self.emit("toast", "Выдавать модерку может только администратор")
            return
        onion = normalize_code(onion)
        if not onion or onion == self.admin_onion:
            self.emit("toast", "Это не код Echoes.NET")
            return
        mods = dict(self.mods())
        if on:
            mods[onion] = {"name": clip(name, MAX_NAME) or self._contact_name(onion), "ts": time.time()}
        else:
            mods.pop(onion, None)
        ml = self.me.sign_obj({"t": "echoes-mods", "pub": self.me.onion, "ts": time.time(), "mods": mods})
        self._take_modlist(ml)
        await self._staff_publish(ml, "echoes-staff", "echoes-staff")
        await self._broadcast_friends({"t": "staff", "mods": ml})
        self.emit("toast", ("Модерка выдана: " if on else "Модерка снята: ") + (mods.get(onion, {}).get("name")
                                                                              or name or onion[:8]))

    async def _staff_publish(self, obj, tag_t, d) -> int:
        nos = getattr(self, "nostr", None)
        if nos is None or not nos.up_count:
            return 0
        ev = await self._nostr_sign(30078, json.dumps(obj, ensure_ascii=False), [["d", d], ["t", tag_t],
                                                                                 self._link_tag()])
        return await nos.publish(ev, urgent=True)

    def _nostr_staff(self, ev):
        if not self._ev_ok(ev):
            return
        try:
            self._take_modlist(json.loads(ev.get("content") or "{}"))
        except ValueError:
            pass

    def _nostr_modact(self, ev):
        if not self._ev_ok(ev) or len(ev.get("content") or "") > 4000:
            return
        try:
            self._take_act(json.loads(ev.get("content") or "{}"))
        except ValueError:
            pass

    def _staff_payload(self):
        st = self._staff_load()
        acts = sorted(st["acts"].values(), key=lambda a: -float(a.get("ts") or 0))[:300]
        from net_radio_auth import load
        permits=sorted(load(self).values(),key=lambda p:-p['ts'])[:300]
        return {"t": "staff", "mods": st.get("mods"), "acts": acts,'radio_permits':permits}

    def _staff_in(self, m):
        if m.get("mods"):
            self._take_modlist(m.get("mods"))
        for a in (m.get("acts") or [])[:300]:
            self._take_act(a)
        from net_radio_auth import take
        for decision in (m.get('radio_permits') or [])[:300]:take(self,decision)

    def _nostr_radio_permit(self,ev):
        if not self._ev_ok(ev) or len(ev.get('content') or '')>3000:return
        from net_radio_auth import take
        try:take(self,json.loads(ev.get('content') or '{}'))
        except (ValueError,TypeError):pass

    # ── подписки на авторов: уведомления о новых постах ── #

    def subs(self) -> dict:
        s = self.settings.get("subs")
        return s if isinstance(s, dict) else {}

    def sub_entry(self, onion="", npub=""):
        s = self.subs()
        if onion and onion in s:
            return onion, s[onion]
        for k, v in s.items():
            if npub and v.get("npub") == npub:
                return k, v
        if npub and ("n:" + npub) in s:
            return "n:" + npub, s["n:" + npub]
        return None, None

    def is_subscribed(self, onion="", npub="") -> bool:
        return self.sub_entry(onion, npub)[0] is not None

    def set_subscribed(self, onion="", npub="", name="", on=True):
        """Подписаться/отписаться (из интерфейса). onion — если автор из ECHOES, npub — его ключ в Nostr."""
        s = dict(self.subs())
        k, _v = self.sub_entry(onion, npub)
        if k is not None:
            s.pop(k, None)
        if on:
            npub = npub if len(npub or "") == 64 else (self._npk_for(onion) if onion else "")
            s[onion or ("n:" + npub)] = {"npub": npub or "", "name": clip(name, MAX_NAME), "t": time.time(),
                                         "last": time.time()}
            while len(s) > SUB_MAX:
                s.pop(min(s, key=lambda x: s[x].get("t", 0)))
        self.settings["subs"] = s
        self.save_settings()
        if self.loop is not None:
            self.call(self._subs_sub)
            self.call(self.publish_follows)

    def _sub_post(self, pid, ts, onion="", npub="", name="", text="", kind="post", npub_post=""):
        """Новый пост автора, на которого подписаны, — уведомить (каждый пост один раз, старые — нет)."""
        if onion == self.me.onion:
            return
        k, v = self.sub_entry(onion, npub)
        if k is None:
            return
        ts = float(ts or 0)
        if ts <= float(v.get("last") or 0) or ts < time.time() - 2 * 86400:
            return
        s = dict(self.subs())
        s[k] = dict(v, last=ts)
        self.settings["subs"] = s
        self.save_settings()
        self.emit("notify", {"kind": "post", "title": name or v.get("name") or "Новый пост",
                             "text": clip(text, 160) or ("Новый тред" if kind == "thread" else "Новый пост"),
                             "onion": onion, "npub": npub or npub_post, "post": pid})

    async def _subs_sub(self):
        """Посты подписок через релеи: и тех, кто не в друзьях (общая лента ограничена 200 последними)."""
        nos = getattr(self, "nostr", None)
        if nos is None:
            return
        npks = sorted({v.get("npub") or self._npk_for(k) for k, v in self.subs().items() if not k.startswith("n:")}
                      | {k[2:] for k in self.subs() if k.startswith("n:")})
        npks = [n for n in npks if len(n or "") == 64]
        if npks == self.__dict__.get("_subs_npks"):
            return
        self._subs_npks = npks
        if npks:
            await nos.subscribe("subs", [{"kinds": [1], "#t": ["echoes"], "authors": npks,
                                          "since": int(time.time()) - 2 * 86400}], self._nostr_note)
        else:
            await nos.unsubscribe("subs")

    async def _presence_loop(self):
        while not self._stop and getattr(self, "nostr", None) is not None and not self.nostr.closed:
            try:
                if self.nostr.up_count:
                    await self._presence_send()
                    await self._presence_sub()
                    await self._subs_sub()
                    await self._upd_seed_send()
                    if not self.__dict__.get("_social_started"):
                        self._social_started = True
                        await self.publish_follows()
                        await self.social_query(self._nostr_keys()[1])
                    if not self.__dict__.get("_upd_mirror_tried"):  # своё публичное обновление ещё не на зеркалах
                        self._upd_mirror_tried = True
                        man = await self._upd_mine()
                        if man is not None:
                            asyncio.ensure_future(self._upd_mirror(man, quiet=True))
                        asyncio.ensure_future(self._mirror_my_mods())
            except Exception as e:                             # noqa: BLE001
                self.log(f"[net] presence: {type(e).__name__} {e}")
            for _ in range(PRESENCE_EVERY):
                if self._stop:
                    return
                await asyncio.sleep(1)

    async def _presence_send(self, leaving=False):
        if not leaving and (self._stop or self.__dict__.get('_presence_leaving')):
            return
        if leaving:
            self._presence_leaving = True
            task = self.__dict__.get('_presence_leave_task')
            if task is None:
                task = asyncio.create_task(self._presence_publish(leaving=True))
                self._presence_leave_task = task
            return await asyncio.shield(task)
        return await self._presence_publish()

    async def _presence_publish(self, leaving=False):
        nos = getattr(self, 'nostr', None)
        if nos is None or not nos.up_count or nos.closed:return
        room = None
        if self.room_host is not None and not leaving:
            room = {"title": clip(self.room_host.get("title"), 80), "n": len(self.room_members) + 1,
                    "public": bool(self.room_host.get("public"))}
            self._radio_summary(room)
        now = self.now_playing if (self.settings.get("share_now", True) and self.settings.get("now_public", True)
                                   and not leaving) else None
        content = {"v": PROTO, "on": not leaving, "room": room, "now": now, "name": self._name()}
        ev = await self._nostr_sign(30078, json.dumps(content, ensure_ascii=False),
                                    [["d", "echoes-presence"], self._link_tag()])
        if not leaving and (self._stop or self.__dict__.get('_presence_leaving')):
            return  # a regular heartbeat signed before exit must not follow the offline announcement
        await self.nostr.publish(ev, urgent=leaving)

    def _nostr_presence(self, ev):
        if not self._ev_ok(ev):
            return
        onion = self.linked_onion(ev)
        if not onion or onion == self.me.onion:
            return
        c = self.store.contact(onion)
        if not c or c["status"] not in ("friend", "pending_out", "pending_in"):
            return
        try:
            data = json.loads(ev.get("content") or "{}")
            ts = float(ev.get("created_at") or 0)
        except (ValueError, TypeError, OverflowError):
            return
        if not isinstance(data, dict) or not isinstance(data.get('on'), bool):
            return
        now = time.time()
        age = now-ts
        # Replayed history is not a heartbeat. Inferring clock skew from an
        # increasing sequence of historical events resurrected offline friends.
        if not -PRESENCE_FUTURE_TOLERANCE <= age <= PRESENCE_SKEW:
            return
        seen_ts = self.__dict__.setdefault("_pres_ts", {})
        seen_on = self.__dict__.setdefault("_pres_on", {})
        previous = seen_ts.get(onion)
        online = data['on']
        if online and ts <= self.__dict__.get('_pres_offline_ts', {}).get(onion, 0):
            return
        if previous is not None and (ts < previous or (ts == previous and (online or not seen_on.get(onion, True)))):
            return
        # Offline wins a timestamp tie (closing immediately after a heartbeat).
        seen_ts[onion] = ts
        seen_on[onion] = online
        self.__dict__.setdefault("_npk_map", {})[onion] = ev["pubkey"]
        upd = {"npk": ev["pubkey"]}
        was = self.is_online(onion)
        fresh = online and age < NOSTR_PEER_IDLE
        if fresh:
            upd['last_seen'] = min(now, ts)
            track = clean_track(data.get("now"))
            upd["now"] = json.dumps(track, ensure_ascii=False) if track else ""
            room = data.get("room") if isinstance(data.get("room"), dict) else None
            if room and room.get('radio'):
                from net_radio_auth import accept
                if not isinstance(room['radio'], dict) or not accept(self,onion,room['radio'].get('permit')):
                    room = None
            upd["room"] = json.dumps(self._clean_room_summary(room), ensure_ascii=False) if room else ""
            self._nostr_attach(onion, ev["pubkey"], received=True, age=max(0., age))
        elif not online:
            self.__dict__.setdefault('_pres_offline_ts', {})[onion] = ts
            peer = self.peers.get(onion)
            # An authenticated direct channel is stronger evidence than relay
            # history; an offline relay announcement closes only that mailbox.
            if peer is not None and peer.via == 'nostr' and (not getattr(peer, '_presence_confirmed', False) or peer.last_rx <= ts):
                self._drop(peer)
            if not self.is_online(onion):
                upd.update(now='', room='')
        self.store.upsert_contact(onion, **upd)
        key = (self.is_online(onion), upd.get("now"), upd.get("room"))
        seen = self.__dict__.setdefault("_pres_seen", {})
        if seen.get(onion) != key or was != self.is_online(onion):
            seen[onion] = key
            self.emit("presence", onion)

    async def _nostr_mail(self, dest, payload) -> bool:
        """Друг недоступен ни через Tor, ни напрямую: зашифрованный конверт — через релеи Nostr."""
        from net_crypto import seal
        nos = getattr(self, "nostr", None)
        npk = (self.store.contact(dest) or {}).get("npk") or ""
        if nos is None or not nos.up_count or len(npk) != 64:
            return False
        ev = await self._nostr_sign(4, seal(self._env_key(dest), payload), [["p", npk], ["echoes", self.me.onion]])
        return await nos.publish(ev) > 0

    # ── своё: профиль, посты, комнаты, вкус ── #

    async def _nostr_announce_loop(self):
        """Раз в 2 минуты: своя публичная комната (если открыта); раз в 30 минут — профиль и вкус; профили авторов."""
        n = 0
        while not self._stop and getattr(self, "nostr", None) is not None and not self.nostr.closed:
            try:
                if self.nostr.up_count:
                    if n % 15 == 0:
                        await self.publish_public_profile()
                    if self.room_host is not None and self.room_host.get("public"):
                        await self._nostr_room_announce()
                    q = self.__dict__.get("_prof_queue")
                    if q:
                        batch = list(q)[:60]
                        q.difference_update(batch)
                        self._prof_asked.update(batch)
                        await self.nostr.subscribe(f"prof{n}", [{"kinds": [0], "authors": batch}], self._nostr_profile)
                        await self.nostr.subscribe(f"pfull{n}", [{"kinds": [30078], "#d": ["echoes-profile"],
                                                                  "authors": batch}], self._nostr_profile_full)
                        await self.nostr.subscribe(f"ppls{n}", [{"kinds": [30078], "#d": ["echoes-playlists"],
                                                                 "authors": batch}], self._nostr_pls)
                        await self.nostr.subscribe(f"pdeco{n}", [{"kinds": [30078], "#d": ["echoes-deco"],
                                                                  "authors": batch}], self._nostr_deco)
                    if self.room_guest is None and n % 3 == 0:
                        await self.nostr.subscribe("rooms", [{"kinds": [30311], "#t": ["echoes"],
                                                              "since": int(time.time()) - 1800}], self._nostr_room)
            except Exception as e:                             # noqa: BLE001
                self.log(f"[nostr] announce: {e}")
            n += 1
            for _ in range(8):
                if self._stop:
                    return
                await asyncio.sleep(15 if n > 1 else 2)

    def _link_tag(self):
        return ["echoes-onion", self.me.onion, self._link_sig()]

    async def publish_public_profile(self):
        nos = getattr(self, "nostr", None)
        if nos is None or not self.settings.get("public_profile", True):
            return
        prof = {k: v for k, v in (self.profile or {}).items() if not k.startswith("_")}
        content = {"name": self._name(), "about": prof.get("about", ""),
                   "echoes": {"onion": self.me.onion, "sig": self._link_sig(), "status": prof.get("status", ""),
                              "fav": prof.get("fav", []),
                              "avatar": prof.get("avatar", "") if len(prof.get("avatar", "")) <= 24000 else ""}}
        await nos.publish(await self._nostr_sign(0, json.dumps(content, ensure_ascii=False), [self._link_tag()]))
        full = clean_profile(dict(prof, name=self._name()))
        if full:                                               # весь профиль, как у друзей: тирлист, ачивки, статистика
            pls = full.pop("pls", None) or []
            await nos.publish(await self._nostr_sign(30078, json.dumps({"pls": pls}, ensure_ascii=False),
                                                     [["d", "echoes-playlists"], self._link_tag()]))
            deco = full.pop("deco", None) or {}                # оформление — своим событием (размер)
            try:                                               # релеи не примут большое — ужатая копия
                from net_showcase import for_public
                deco = for_public(deco)
            except Exception:                                  # noqa: BLE001
                pass
            await nos.publish(await self._nostr_sign(30078, json.dumps({"deco": deco}, ensure_ascii=False),
                                                     [["d", "echoes-deco"], self._link_tag()]))
            if prof.get("avatar") and len(prof["avatar"]) <= 60000:
                full["avatar"] = prof["avatar"]
            await nos.publish(await self._nostr_sign(30078, json.dumps(full, ensure_ascii=False),
                                                     [["d", "echoes-profile"], self._link_tag()]))
        if self.taste and self.settings.get("share_taste", True):
            await nos.publish(await self._nostr_sign(30078, json.dumps(self.taste, ensure_ascii=False),
                                                     [["d", "echoes-taste"], self._link_tag()]))

    async def publish_public(self, text, track=None, paths=(), gif=None):
        """Пост для всех (Nostr): текст + трек, с PoW против спама и подписью-связью с onion."""
        nos = getattr(self, "nostr", None)
        if nos is None or not nos.up_count:
            self.emit("toast", "Публичная сеть (Nostr) сейчас недоступна")
            return
        text = clip(text).strip()
        track = clean_track(track)
        why = self.mod_check(text)
        if why:
            self.emit("toast", f"Не опубликовано: похоже на запрещённое ({why})")
            return
        from net_files import shrink_meta
        metas = []
        for pth in list(paths)[:4]:                            # файлы раздаёт автор всем, кто попросит (через Tor)
            mm = await self.share_file(pth, ["*public*"])
            if mm:
                metas.append(shrink_meta(mm, 9000))
        names = " ".join(mm["name"] for mm in metas)
        if self.mod_check(names):
            self.emit("toast", "Не опубликовано: запрещённое в названии файла")
            return
        from net_gif import clean_gif
        g = clean_gif(gif) if gif else None
        content = text + (f"\n\nТрек: {track['artist']} — {track['title']}" if track else "")
        tags = [["t", "echoes"], ["client", "ECHOES"], self._link_tag(),
                ["echoes", json.dumps({"track": track, "files": metas, "gif": g}, ensure_ascii=False)]]
        ev = await self._nostr_sign(1, content, tags, int(self.settings.get("pow", 14)))
        self._nostr_note(ev)
        n = await nos.publish(ev)
        self.emit("toast", f"Опубликовано для всех · релеев: {n}")

    async def public_like(self, eid, npub):
        nos = getattr(self, "nostr", None)
        if nos is None:
            return
        ev = await self._nostr_sign(7, "+", [["e", eid], ["p", npub], ["t", "echoes"]])
        self._nostr_react(ev)
        await nos.publish(ev)

    async def public_reply(self, eid, npub, text):
        nos = getattr(self, "nostr", None)
        text = clip(text).strip()
        if nos is None or not text:
            return
        if self.mod_check(text):
            self.emit("toast", "Не отправлено: похоже на запрещённое")
            return
        ev = await self._nostr_sign(1, text, [["e", eid, "", "reply"], ["p", npub], ["t", "echoes"],
                                              self._link_tag()], 8)
        self._nostr_note(ev)
        await nos.publish(ev)

    async def _nostr_room_announce(self, ended=False):
        nos = getattr(self, "nostr", None)
        rh = self.room_host
        if nos is None or rh is None:
            return
        st = rh.get("state") or {}
        data = {"genre": rh.get("genre", ""), "now": st.get("track"), "n": len(self.room_members) + 1}
        self._radio_summary(data)
        tags = [["d", rh["id"]], ["title", rh.get("title", "")], ["status", "ended" if ended else "live"],
                ["t", "echoes"], ["expiration", str(int(time.time()) + 300)], self._link_tag(),
                ["echoes-room", json.dumps(data, ensure_ascii=False)]]
        await nos.publish(await self._nostr_sign(30311, "", tags))

    def mute(self, npub):
        m = self.settings.setdefault("muted", [])
        if npub not in m:
            m.append(npub)
        self.save_settings()
        for k in [k for k, v in self.public["posts"].items() if v["npub"] == npub]:
            self.public["posts"].pop(k, None)
        self.emit("public", "feed")

    async def request_stranger(self, onion, note=""):
        """Заявка незнакомцу из публичной сети: обычная заявка в друзья по его onion (у него — в «Заявках»)."""
        self.add_friend(onion, note)
        await self._dial_now(normalize_code(onion))

    # ══════════════════════════════════════════════════════════════════ #
    #  Модерация (net_moderation): фильтр запрещённого, жалобы, общие с друзьями
    # ══════════════════════════════════════════════════════════════════ #

    def mod_check(self, *texts):
        """Запрещённое в тексте → причина (по-русски) или ''. Мат не считается."""
        if not self.settings.get("moderation", True):
            return ""
        from net_moderation import check_many, reason
        r = check_many(*texts)
        return reason(r[0]) if r else ""

    def mod_hidden(self, *ids) -> str:
        """Автор скрыт? (вы пожаловались / пожаловался друг / фильтр поймал его не раз) → причина или ''."""
        st = self.staff_hidden(*ids)
        if st:
            return st
        for i in ids:
            if not i:
                continue
            rows = self.store.q("SELECT reporter, reason FROM reports WHERE target=?", (i,))
            for r in rows:
                if r["reporter"] == self.me.onion:
                    return f"вы пожаловались: {r['reason']}"
                if r["reporter"] == "auto":
                    continue
                if self.settings.get("trust_reports", True) and self.is_friend(r["reporter"]):
                    return f"пожаловался друг {self._contact_name(r['reporter'])}: {r['reason']}"
            auto = [r for r in rows if r["reporter"] == "auto"]
            if len(auto) and int(auto[0]["reason"].split("|")[0] or 0) >= 2:
                return "автор не раз публиковал запрещённое"
        return ""

    def _strike(self, author, why):
        """Фильтр поймал автора: копим «страйки» — после второго он скрыт целиком."""
        if not author or author == self.me.onion or author == getattr(self, "nostr_pub", ""):
            return
        r = self.store.q("SELECT reason FROM reports WHERE target=? AND reporter='auto'", (author,))
        n = int(r[0]["reason"].split("|")[0]) + 1 if r else 1
        self.store.x("INSERT OR REPLACE INTO reports(target, reporter, reason, ts) VALUES(?,?,?,?)",
                     (author, "auto", f"{n}|{why}", time.time()))
        self.mod_count = getattr(self, "mod_count", 0) + 1

    def _mod_drop(self, author, *texts) -> bool:
        """Входящее от незнакомцев: скрыт автор или текст запрещённый → отбросить (и записать страйк)."""
        if self.mod_hidden(author):
            self.mod_count = getattr(self, "mod_count", 0) + 1
            return True
        why = self.mod_check(*texts)
        if why:
            self._strike(author, why)
            return True
        return False

    async def report(self, target, reason="", extra_ids=()):
        """Пожаловаться: скрыть автора у себя и тихо сообщить друзьям (у них он тоже скроется)."""
        reason = clip(reason, 80) or "запрещённый контент"
        for t in [target] + [x for x in extra_ids if x]:
            self.store.x("INSERT OR REPLACE INTO reports(target, reporter, reason, ts) VALUES(?,?,?,?)",
                         (t, self.me.onion, reason, time.time()))
        await self._broadcast_friends({"t": "report", "items": [{"target": t, "reason": reason}
                                                                for t in [target] + list(extra_ids) if t]})
        self.emit("feed")
        self.emit("public", "feed")

    async def unreport(self, target):
        self.store.x("DELETE FROM reports WHERE target=? AND reporter=?", (target, self.me.onion))
        await self._broadcast_friends({"t": "report", "items": [{"target": target, "reason": ""}]})
        self.emit("feed")
        self.emit("public", "feed")

    def my_reports(self):
        return self.store.q("SELECT target, reason, ts FROM reports WHERE reporter=? ORDER BY ts DESC",
                            (self.me.onion,))

    def _reports_in(self, o, items):
        for it in (items or [])[:200]:
            if not isinstance(it, dict):
                continue
            t = clip(it.get("target"), 64)
            if not t or t == self.me.onion or t == getattr(self, "nostr_pub", ""):
                continue
            if it.get("reason"):
                self.store.x("INSERT OR REPLACE INTO reports(target, reporter, reason, ts) VALUES(?,?,?,?)",
                             (t, o, clip(it.get("reason"), 80), time.time()))
            else:
                self.store.x("DELETE FROM reports WHERE target=? AND reporter=?", (t, o))
        self.emit("feed")
        self.emit("public", "feed")

    # ── моды (темы ECHOES): друзьям — постом, всем — витриной в Nostr ── #

    async def publish_mod(self, pkg_path, title, desc, version="", icon_path="", shot_paths=(), public=True,
                          theme=""):
        """Выложить мод: файл темы и скриншоты раздаёт автор (через Tor), описание — друзьям и (если public)
        в общую витрину. Иконка — маленький JPEG прямо в описании."""
        from net_files import preview, shrink_meta
        why = self.mod_check(title, desc)
        if why:
            self.emit("toast", f"Мод не опубликован: похоже на запрещённое ({why})")
            return
        allow = ["*public*"] if public else ["*"]
        pkg = await self.share_file(pkg_path, allow)
        if not pkg:
            return
        if public:
            asyncio.ensure_future(self._mirror_file(pkg))
        shots = []
        for pth in list(shot_paths)[:4]:
            mm = await self.share_file(pth, allow)
            if mm and mm["kind"] == "image":
                shots.append(shrink_meta(mm, 7000))
        icon = ""
        if icon_path:
            try:
                im = await asyncio.get_running_loop().run_in_executor(None, preview, icon_path)
                icon = shrink_meta(im, 14000).get("pv", {}).get("thumb", "")
            except (OSError, ValueError):
                icon = ""
        mid = secrets.token_hex(8)
        mod = {"mid": mid, "version": clip(version, 20), "pkg": shrink_meta(pkg, 7000), "shots": shots,
               "icon": icon, "theme": clip(theme, 80)}
        await self.publish(clip(desc, 3000), None, "mod", title=clip(title, 80), mod=mod)
        nos = getattr(self, "nostr", None)
        if public and nos is not None and nos.up_count:
            content = json.dumps({"title": clip(title, 80), "desc": clip(desc, 3000), "mod": mod}, ensure_ascii=False)
            ev = await self._nostr_sign(30078, content, [["d", f"echoes-mod:{mid}"], ["t", "echoes-mod"],
                                                         self._link_tag()], 10)
            self._nostr_mod(ev)
            n = await nos.publish(ev)
            self.emit("toast", f"Мод «{title}» выложен для всех · релеев: {n}")
        else:
            self.emit("toast", f"Мод «{title}» выложен для друзей")

    def _my_mod(self, mid):
        """Свой мод по mid: (пост для друзей или None, запись витрины или None)."""
        post = next((p for p in self.store.posts(self.me.onion, 500)
                     if p.get("kind") == "mod" and (p.get("mod") or {}).get("mid") == mid), None)
        pub = next((it for it in (self.public.get("mods") or {}).values()
                    if it.get("onion") == self.me.onion and (it.get("mod") or {}).get("mid") == mid), None)
        return post, pub

    async def update_mod(self, mid, title, desc, version="", pkg_path="", icon_path="", shot_paths=None,
                         public=True, theme=""):
        """Изменить свой мод: название, описание, версию; при желании — новый файл темы, иконку, скриншоты.
        У друзей пост заменяется (тот же id, новая подпись), в витрине Nostr — событие с тем же d-тегом."""
        from net_files import preview, shrink_meta
        post, pub = self._my_mod(mid)
        base = clean_mod((post or {}).get("mod") or (pub or {}).get("mod"))
        if not base:
            self.emit("toast", "Мод не найден — возможно, он уже удалён")
            return
        why = self.mod_check(title, desc)
        if why:
            self.emit("toast", f"Мод не изменён: похоже на запрещённое ({why})")
            return
        allow = ["*public*"] if public else ["*"]
        mod = dict(base, mid=mid, version=clip(version, 20))
        if theme:
            mod["theme"] = clip(theme, 80)
        if pkg_path:
            pkg = await self.share_file(pkg_path, allow)
            if not pkg:
                return
            mod["pkg"] = shrink_meta(pkg, 7000)
            if public:
                asyncio.ensure_future(self._mirror_file(pkg))
        if shot_paths is not None:
            shots = []
            for pth in list(shot_paths)[:4]:
                if isinstance(pth, dict):                      # оставленный старый скриншот
                    shots.append(pth)
                    continue
                mm = await self.share_file(pth, allow)
                if mm and mm["kind"] == "image":
                    shots.append(shrink_meta(mm, 7000))
            mod["shots"] = shots
        if icon_path:
            try:
                im = await asyncio.get_running_loop().run_in_executor(None, preview, icon_path)
                mod["icon"] = shrink_meta(im, 14000).get("pv", {}).get("thumb", "")
            except (OSError, ValueError):
                pass
        title, desc = clip(title, 80), clip(desc, 3000)
        if post:
            obj = {k: v for k, v in post.items() if k != "sig"}
            obj.update(text=desc, title=title, mod=clean_mod(mod), edited=time.time())
            new = self.me.sign_obj(obj)
            self.store.put_post(new)
            self.emit("feed")
            await self._broadcast_friends({"t": "post_upd", "item": self._thread_item(new)})
        else:
            await self.publish(desc, None, "mod", title=title, mod=mod)
        nos = getattr(self, "nostr", None)
        if (public or pub) and nos is not None and nos.up_count:
            if pub and pub.get("ts", 0) >= int(time.time()):
                await asyncio.sleep(1.1)                       # заменяемое событие: новое должно быть позже старого
            content = json.dumps({"title": title, "desc": desc, "mod": mod}, ensure_ascii=False)
            ev = await self._nostr_sign(30078, content, [["d", f"echoes-mod:{mid}"], ["t", "echoes-mod"],
                                                         self._link_tag()], 10)
            self._nostr_mod(ev)
            await nos.publish(ev)
        self.emit("toast", f"Мод «{title}» обновлён")
        self.emit("public", "mods")

    async def delete_mod(self, mid):
        """Убрать свой мод: пост у друзей удаляется, в витрине — «пустая» замена с тем же d-тегом
        (у Nostr заменяемые события: новое затирает старое) плюс запрос на удаление (kind 5)."""
        post, pub = self._my_mod(mid)
        if post:
            await self.delete_post(post["id"])
        nos = getattr(self, "nostr", None)
        if pub is not None:
            self.public["mods"].pop(pub["key"], None)
        self.settings.setdefault("mods_deleted", [])
        if mid not in self.settings["mods_deleted"]:
            self.settings["mods_deleted"] = (self.settings["mods_deleted"] + [mid])[-200:]
            self.save_settings()
        if nos is not None and nos.up_count:
            _sk, npub = self._nostr_keys()
            d = f"echoes-mod:{mid}"
            gone = await self._nostr_sign(30078, json.dumps({"deleted": True}), [["d", d], ["t", "echoes-mod"],
                                                                                  self._link_tag()], 10)
            await nos.publish(gone)
            kill = await self._nostr_sign(5, "мод удалён автором", [["a", f"30078:{npub}:{d}"]], 0)
            await nos.publish(kill)
        self.emit("public", "mods")
        self.emit("feed")
        self.emit("toast", "Мод удалён из мастерской")

    def _nostr_mod(self, ev):
        from net_nostr import tag
        if not self._ev_ok(ev):
            return
        onion = self.linked_onion(ev)
        if not onion:
            return                                             # мод без подтверждённого автора — не показываем
        try:
            c = json.loads(ev.get("content") or "{}")
        except ValueError:
            return
        if c.get("deleted"):                                   # автор убрал мод — убрать и из витрины
            key = f"{ev['pubkey']}:{tag(ev, 'd')}"
            old = (self.public.get("mods") or {}).get(key)
            if old and old["ts"] <= ev["created_at"]:
                self.public["mods"].pop(key, None)
                self.emit("public", "mods")
            return
        mod = clean_mod(c.get("mod"))
        title, desc = clip(c.get("title"), 80), clip(c.get("desc"), 3000)
        if not mod or not title:
            return
        if onion == self.me.onion and mod.get("mid") in (self.settings.get("mods_deleted") or []):
            return                                             # свой удалённый мод: реле ещё отдают старую копию
        if onion != self.me.onion and (self.mod_hidden(onion, ev["pubkey"]) or self._mod_drop(ev["pubkey"], title, desc)):
            return
        key = f"{ev['pubkey']}:{tag(ev, 'd')}"
        old = self.public.setdefault("mods", {}).get(key)
        if old and (old["ts"] > ev["created_at"] or old.get("ev") == ev["id"]):
            return
        self.public["mods"][key] = {"key": key, "npub": ev["pubkey"], "onion": onion, "ts": ev["created_at"],
                                    "title": title, "desc": desc, "mod": mod, "ev": ev["id"]}
        self._want_profile(ev["pubkey"])
        self.emit("public", "mods")

    # ── файлы ── #

    async def share_file(self, path, allow) -> dict | None:
        """Свой файл → копия в files/sent, описание с превью (в фоне). allow: список onion или ["*"] — друзья."""
        import shutil
        from net_files import preview
        loop = asyncio.get_running_loop()
        try:
            meta = await loop.run_in_executor(None, preview, str(path))
        except (OSError, ValueError) as e:
            self.emit("toast", f"Файл не отправлен: {e}")
            return None
        fid = secrets.token_hex(12)
        meta["fid"] = fid
        dest = self.files_dir / "sent" / f"{fid}_{meta['name']}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        await loop.run_in_executor(None, shutil.copyfile, str(path), str(dest))
        self.store.put_file(fid, self.me.onion, meta, "have", str(dest), list(allow))
        return meta

    async def send_file(self, peer, path, text=""):
        """Файл в чат (peer — onion или «g:<группа>»): описание с превью уходит сообщением, сам файл — по запросу."""
        if str(peer).startswith("g:"):
            g = self.store.group(peer[2:])
            if not g:
                return
            meta = await self.share_file(path, g["members"])
            if meta:
                await self.send_group(peer[2:], text, None, {"kind": "file", "file": meta})
        else:
            meta = await self.share_file(path, [peer])
            if meta:
                await self.send_message(peer, text, None, {"kind": "file", "file": meta})

    async def publish_files(self, text, paths, track=None, kind="post", **extra):
        metas = []
        for pth in list(paths)[:6]:
            m = await self.share_file(pth, ["*"])
            if m:
                metas.append(m)
        if metas or text or track:
            await self.publish(text, track, kind, files=metas, **extra)

    def file_state(self, fid) -> dict:
        r = self.store.file(fid) or {}
        inc = self._incoming.get(fid)
        return {"state": r.get("state", ""), "path": r.get("path", ""), "got": inc["got"] if inc else 0}

    async def _mirror_file(self, meta):
        """Свой публичный файл (тема-мод) — на зеркала Blossom, чтобы его брали и без автора в сети."""
        import net_mirror
        r = self.store.file(meta["fid"]) or {}
        if not r.get("path") or not meta.get("sha"):
            return
        sk, _pk = self._nostr_keys()
        res = await asyncio.get_running_loop().run_in_executor(
            None, net_mirror.mirror_files, sk, [(r["path"], meta["sha"], int(meta["size"]))])
        self.log(f"[net] зеркала: {meta['name']} → {len(res.get(meta['sha']) or [])} серв.")

    async def _mirror_my_mods(self):
        """Выложенные раньше публичные моды — тоже на зеркала (один раз)."""
        await asyncio.sleep(30)                                # витрина успевает прийти с релеев
        done = set(self.settings.get("mods_mirrored") or [])
        for it in list((self.public.get("mods") or {}).values()):
            pkg = (it.get("mod") or {}).get("pkg") or {}
            if it.get("onion") != self.me.onion or not pkg.get("sha") or pkg["sha"] in done:
                continue
            r = self.store.file(pkg.get("fid", "")) or {}
            if r.get("path") and Path(r["path"]).exists():
                await self._mirror_file(pkg)
                done.add(pkg["sha"])
        self.settings["mods_mirrored"] = sorted(done)[-300:]
        self.save_settings()

    async def fetch(self, meta, owner, mirror=False):
        """Скачать чужой файл у владельца (автор сообщения/поста). Без связи — скачается, когда он появится.
        mirror — публичный файл (мод): сначала с зеркал Blossom по SHA-256, быстро и без автора в сети."""
        from net_files import clean_meta, safe_name
        meta = clean_meta(meta)
        if not meta:
            return
        fid = meta["fid"]
        r = self.store.file(fid)
        if r and r["state"] == "have" and r["path"] and Path(r["path"]).exists():
            self.emit("file", (fid, "done", r["path"]))
            return
        if fid in self._incoming:
            return
        if not r:
            dest = self.files_dir / "in" / f"{fid}_{safe_name(meta['name'])}"
            self.store.put_file(fid, owner, meta, "want", str(dest))
        else:
            self.store.set_file(fid, state="want")
        if mirror and meta.get("sha"):
            import net_mirror
            dest = Path((self.store.file(fid) or {}).get("path") or self.files_dir / "in" / f"{fid}_{safe_name(meta['name'])}")
            part = dest.with_name(dest.name + ".part")
            ok = await asyncio.get_running_loop().run_in_executor(None, net_mirror.fetch, meta["sha"], int(meta["size"]),
                                                                  part)
            if ok:
                os.replace(part, dest)
                from net_files import mark_internet
                mark_internet(dest)                            # «из интернета»: SmartScreen / защищённый просмотр
                self.store.set_file(fid, state="have", path=str(dest))
                self.emit("file", (fid, "done", str(dest)))
                return
            part.unlink(missing_ok=True)
        await self._request_file(fid)

    async def _request_file(self, fid):
        r = self.store.file(fid)
        if not r or r["state"] == "have" or fid in self._incoming:
            return
        p = self.peers.get(r["owner"])
        if not p and not self.is_friend(r["owner"]) and r["owner"] not in self._dialing:
            await self._dial_now(r["owner"])                   # публичный файл незнакомца — соединиться сразу
            p = self.peers.get(r["owner"])
        if not p:
            self.poke(r["owner"])
            self.emit("file", (fid, "waiting", ""))
            return
        part = Path(r["path"] + ".part")
        part.parent.mkdir(parents=True, exist_ok=True)
        off = part.stat().st_size if part.exists() else 0     # докачка с места обрыва
        self._incoming[fid] = {"f": part, "got": off, "size": int(r["meta"].get("size", 0)), "owner": r["owner"],
                               "emit": off}
        self.store.set_file(fid, state="part")
        self.emit("file", (fid, "progress", off))
        await p.send({"t": "file_get", "fid": fid, "off": off})

    async def _file_get(self, p, m):
        fid = clip(m.get("fid"), 40)
        r = self.store.file(fid)
        if p.via == "nostr" and r and Path(r["path"]).exists() and Path(r["path"]).stat().st_size > NOSTR_FILE_MAX:
            await p.send({"t": "file_err", "fid": fid, "why": "файл больше 2 МБ — передаётся только когда есть "
                                                             "связь через Tor или напрямую"})
            return
        ok = bool(r) and r["state"] == "have" and r["owner"] == self.me.onion and Path(r["path"]).exists() and \
            (("*" in r["allow"] and self.is_friend(p.onion)) or p.onion in r["allow"] or "*public*" in r["allow"] or
             ('radio' in r['allow'] and p.onion in self.room_members and self.room_host is not None and
              any(sound.get('fid')==fid for sound in self.room_host.get('sounds',[]))))
        if not ok:
            await p.send({"t": "file_err", "fid": fid, "why": "файла нет или он не для вас"})
            return
        if self._streams.get(p.onion, 0) >= 3:
            await p.send({"t": "file_err", "fid": fid, "why": "занято, повторите позже"})
            return
        try:
            off = max(0, int(m.get("off") or 0))
        except (TypeError, ValueError):
            off = 0
        asyncio.ensure_future(self._stream_file(p, fid, r["path"], off))

    async def _stream_file(self, p, fid, path, off):
        loop = asyncio.get_running_loop()
        self._streams[p.onion] = self._streams.get(p.onion, 0) + 1
        try:
            with open(path, "rb") as f:
                f.seek(off)
                while p.alive:
                    chunk = await loop.run_in_executor(None, f.read, CHUNK)
                    if not chunk:
                        break
                    await p.send({"t": "file_chunk", "fid": fid, "off": off, "d": base64.b64encode(chunk).decode()})
                    off += len(chunk)
                    await asyncio.sleep(0)                     # чат и голос не ждут, пока идёт файл
            if p.alive:
                await p.send({"t": "file_end", "fid": fid, "size": off})
        except OSError as e:
            await p.send({"t": "file_err", "fid": fid, "why": str(e)[:100]})
        finally:
            self._streams[p.onion] = max(0, self._streams.get(p.onion, 1) - 1)

    async def _file_chunk(self, o, m):
        fid = clip(m.get("fid"), 40)
        inc = self._incoming.get(fid)
        if not inc or inc["owner"] != o:
            return
        try:
            off = int(m.get("off"))
            data = base64.b64decode(str(m.get("d") or ""))
        except (TypeError, ValueError):
            return
        if off != inc["got"] or len(data) > CHUNK or inc["got"] + len(data) > inc["size"]:
            return                                             # не по порядку / больше заявленного — отбросить
        with open(inc["f"], "ab") as f:
            f.write(data)
        inc["got"] += len(data)
        if inc["got"] - inc["emit"] >= max(CHUNK * 2, inc["size"] // 50) or inc["got"] >= inc["size"]:
            inc["emit"] = inc["got"]
            self.emit("file", (fid, "progress", inc["got"]))

    async def _file_end(self, o, m):
        from net_files import sha256_file
        fid = clip(m.get("fid"), 40)
        inc = self._incoming.get(fid)
        if not inc or inc["owner"] != o:
            return
        self._incoming.pop(fid, None)
        r = self.store.file(fid)
        part = inc["f"]
        sha = await asyncio.get_running_loop().run_in_executor(None, sha256_file, str(part))
        if sha != r["meta"].get("sha"):
            part.unlink(missing_ok=True)
            self.store.set_file(fid, state="want")
            self.emit("file", (fid, "error", "файл повреждён в пути — попробуйте ещё раз"))
            return
        final = Path(r["path"])
        final.unlink(missing_ok=True)
        part.rename(final)
        from net_files import mark_internet
        mark_internet(final)                                   # «из интернета»: SmartScreen / защищённый просмотр
        self.store.set_file(fid, state="have")
        self.emit("file", (fid, "done", str(final)))

    async def set_taste(self, taste):
        self.taste = clean_taste(taste)
        if self.settings.get("share_taste", True):
            await self._broadcast_friends(self._hi())

    async def delete_post(self, pid):
        post = self.store.post(pid)
        if not post or post["author"] != self.me.onion:
            return
        self.store.delete_post(pid)
        self._devfeed_gone(pid)
        self.emit("feed")
        d = self.me.sign_obj({"k": "del", "id": pid, "author": self.me.onion, "ts": time.time()})
        await self._broadcast_friends({"t": "post_del", "del": d})

    async def vote(self, pid, val):
        post = self.store.post(pid)
        if not post:
            return
        v = self.me.sign_obj({"k": "vote", "post": pid, "voter": self.me.onion, "val": int(val), "ts": time.time()})
        self.store.put_vote(v)
        self._devfeed_touch(pid)
        self.emit("feed")
        if post["author"] == self.me.onion:
            await self._push_thread(pid)
        else:
            await self._to_author(post["author"], {"t": "vote", "vote": v})

    async def comment(self, pid, text, parent="", track=None, at=None):
        """Комментарий; track — ответ треком («эстафета»), at — секунда трека поста («на 1:23»)."""
        post = self.store.post(pid)
        text = clip(text).strip()
        track = clean_track(track)
        if not post or (not text and not track):
            return
        if self.mod_check(text):
            self.emit("toast", "Комментарий не отправлен: похоже на запрещённое")
            return
        obj = {"k": "com", "id": secrets.token_hex(12), "post": pid, "parent": clip(parent, 64),
               "author": self.me.onion, "name": self._name(), "ts": time.time(), "text": text}
        if track:
            obj["track"] = track
        if clean_sec(at) is not None:
            obj["at"] = clean_sec(at)
        c = self.me.sign_obj(obj)
        self.store.put_comment(c)
        self._devfeed_touch(pid)
        self.emit("feed")
        if post["author"] == self.me.onion:
            await self._push_thread(pid)
        else:
            await self._to_author(post["author"], {"t": "comment", "comment": c})

    async def _to_author(self, onion, payload):
        p = self.peers.get(onion)
        if p:
            await p.send(payload)
        else:
            self.store.outbox_add(onion, payload)
            self.poke(onion)

    async def refresh(self):
        self.poke()
        for o, p in list(self.peers.items()):
            if self.is_friend(o):
                await p.send({"t": "sync"})

    async def set_profile(self, name, bio, share_now):
        self.settings.update(name=clip(name, MAX_NAME), bio=clip(bio, 300), share_now=bool(share_now))
        self.save_settings()
        await self._broadcast_friends(self._hi())

    async def set_game(self, name):
        self.game = clip(name, 60)
        await self._broadcast_friends(self._hi())
        self.emit("presence", "")

    async def set_now_playing(self, track):
        self.now_playing = clean_track(track)
        if self.settings.get("share_now", True):
            await self._broadcast_friends(self._hi())

    # ── «Слушать вместе» ── #

    @staticmethod
    def _clean_room_summary(raw):
        from radio_station import summary
        return {'title': clip(raw.get('title'), 80), 'n': int(clean_sec(raw.get('n'), 999) or 1),
                'radio': summary(raw.get('radio')), 'now': clean_track(raw.get('now'))}

    def _radio_summary(self, destination):
        st = (self.room_host or {}).get('state') or {}
        if st.get('radio'):
            from radio_station import summary
            destination.update(radio=summary(st['radio']), now=clean_track(st.get('track')))
            from net_radio_auth import proof
            destination['radio']['permit']=proof(self)

    def radio_allowed(self,onion=None):
        from net_radio_auth import allowed
        return allowed(self,onion)

    def radio_voice_out(self,seq,frames):
        """Dedicated host microphone/soundboard route: never send to an unrelated call."""
        loop=self.loop
        if loop is None:return
        def send():
            if self.room_host is not None and self.room_host.get('station') is not None:
                encoded={codec:[base64.b64encode(frame).decode() for frame in packets] for codec,packets in frames.items()}
                asyncio.create_task(self.voice_send(int(seq),encoded))
        loop.call_soon_threadsafe(send)

    async def radio_add_sound(self,path):
        if not self.room_host or not self.room_host.get('station') or not self.radio_allowed():return
        rh=self.room_host;sounds=rh.setdefault('sounds',[])
        if len(sounds)>=16:self.emit('toast','The station soundboard holds up to 16 clips');return
        try:
            from radio_audio import decode_clip
            audio=await asyncio.get_running_loop().run_in_executor(None,decode_clip,path)
            del audio
            meta=await self.share_file(path,['radio'])
        except Exception as error:
            self.emit('toast',str(error));return
        if self.room_host is not rh or not meta:return
        sounds=rh.setdefault('sounds',[])
        if len(sounds)>=16:return
        small={**meta,'pv':{k:v for k,v in meta.get('pv',{}).items() if k in ('dur','title','artist')}}
        sounds.append(small);self.settings['radio_sounds']=sounds;self.save_settings()
        rh['station'].revision=secrets.token_hex(8);rh['state']=rh['station'].state()
        await self._room_broadcast()

    async def radio_remove_sound(self,fid):
        rh=self.room_host
        if rh is None or not rh.get('station'):return
        rh['sounds']=[s for s in rh.get('sounds',[]) if s.get('fid')!=fid]
        self.settings['radio_sounds']=rh['sounds'];self.save_settings()
        rh['station'].revision=secrets.token_hex(8);rh['state']=rh['station'].state();await self._room_broadcast()

    async def radio_open(self, config):
        if not self.radio_allowed():
            self.emit('toast','Radio hosting requires approval. Open Requests & bugs to apply.');return
        from radio_station import Station
        try:
            station = Station(config)
        except ValueError as error:
            self.emit('toast', str(error)); return
        self.settings['radio_station'] = station.config()
        self.save_settings()
        await self.room_open(station.brand['name'], True, station.genre,
                             bool(self.settings.get('share_tracks', True)), radio=station)

    async def radio_configure(self, config):
        station = (self.room_host or {}).get('station')
        if station is None: return
        try:
            station.configure(config)
        except ValueError as error:
            self.emit('toast', str(error)); return
        self.settings['radio_station'] = station.config()
        self.save_settings()
        self.room_host.update(title=station.brand['name'], genre=station.genre, state=station.state())
        await self._room_broadcast()
        await self._nostr_room_announce()
        if getattr(self, 'nostr', None) is not None:
            await self._presence_send()

    async def radio_control(self, action, qid=None):
        station = (self.room_host or {}).get('station')
        if station is None: return
        station.control(action, qid)
        self.room_host['state'] = station.state()
        await self._room_broadcast()

    async def _radio_loop(self):
        last_key = None; last_send = 0.
        while self.room_host is not None and self.room_host.get('station') is not None:
            rh = self.room_host
            if not self.radio_allowed():
                self.emit('toast','Radio host permission was revoked')
                asyncio.create_task(self.room_close());return
            st = rh['station'].state()
            key = (st['radio']['revision'], st['radio']['current'], st['playing'])
            rh['state'] = st
            if key != last_key or time.monotonic()-last_send >= 5:
                try:
                    await self._room_broadcast()
                    if key != last_key:
                        await self._nostr_room_announce()
                except Exception as error:
                    self.log(f'[radio] broadcast: {type(error).__name__}')
                last_key = key; last_send = time.monotonic()
            await asyncio.sleep(1)

    def room_view(self) -> dict | None:
        if self.room_host is not None:
            return {"role": "host", "title": self.room_host.get("title", ""), "state": self.room_host.get("state"),
                    "members": [self._contact_name(o) for o in self.room_members]}
        if self.room_guest:
            st = dict(self.room_state or {})
            return {"role": "guest", "host": self.room_guest, "host_name": self._contact_name(self.room_guest),
                    "title": st.get("title", ""), "state": st, "members": st.get("members", [])}
        return None

    def host_clock(self) -> float:
        """Время хоста комнаты по нашим часам (медиана лучших замеров ping/pong)."""
        if not self._clock:
            return time.time()
        offs = sorted(o for _r, o in self._clock[:3])
        return time.time() + offs[len(offs) // 2]

    async def room_open(self, title, public=None, genre="", share=True, radio=None):
        """public — комната видна всем в Echoes.NET (объявление в Nostr), зайти могут и незнакомцы.
        share — гостям, у которых трека нет, хост отдаёт свой файл."""
        if radio is not None and not self.radio_allowed():
            self.emit('toast','Radio hosting requires staff approval');return
        if public is None:                                     # по умолчанию комнаты — для всех
            public = bool(self.settings.get("rooms_public", True)) and getattr(self, "nostr", None) is not None
        if self.room_guest:
            await self.room_leave()
        if self.room_host is not None:
            await self.room_close()
        self.room_host = {"title": clip(title, 80) or f"Комната {self._name()}", "state": None,
                          "public": bool(public), "genre": clip(genre, 40), "share": bool(share),
                          "id": secrets.token_hex(6)}
        if radio is not None:
            sounds=[m for m in self.settings.get('radio_sounds',[])[:16] if isinstance(m,dict) and self.store.file(m.get('fid',''))]
            self.room_host.update(station=radio, state=radio.state(), sent_revisions={},sounds=sounds)
            self._radio_task = asyncio.create_task(self._radio_loop())
        self.room_members = set()
        self.room_chat = []
        self.emit("room", self.room_view())
        await self._broadcast_friends(self._hi())
        if public:
            asyncio.ensure_future(self._nostr_room_announce())
        if getattr(self, "nostr", None) is not None and self.nostr.up_count:
            asyncio.ensure_future(self._presence_send())       # друзья увидят комнату сразу

    async def room_close(self):
        if self.room_host is None:
            return
        task = self.__dict__.pop('_radio_task', None)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if self.room_host.get("public"):
            try:
                await self._nostr_room_announce(ended=True)
            except Exception as e:                             # noqa: BLE001
                self.log(f"[nostr] room end: {e}")
        members = list(self.room_members)
        self.room_host = None
        self.room_members = set()
        for o in members:
            p = self.peers.get(o)
            if p:
                await p.send({"t": "room_state", "state": None})
        self.emit("room", None)
        await self._broadcast_friends(self._hi())

    async def room_update(self, state):
        """Хост: трек/позиция/пауза изменились (state: track, pos, playing)."""
        if self.room_host is None or self.room_host.get('station') is not None:
            return
        st = dict(state or {})
        st["track"] = clean_track(st.get("track"))
        st["ts"] = time.time()
        self.room_host["state"] = st
        await self._room_broadcast()

    async def _room_broadcast(self):
        if self.room_host is None:
            return
        st = dict(self.room_host.get("state") or {})
        if st.get('radio'):
            from net_radio_auth import proof
            st['radio']={**st['radio'],'permit':proof(self),'sounds':self.room_host.get('sounds',[])}
            self.room_host['state']={**(self.room_host.get('state') or {}),'radio':st['radio']}
        st["title"] = self.room_host.get("title", "")
        st["share"] = bool(self.room_host.get("share"))
        st["public"] = bool(self.room_host.get("public"))
        st["members"] = [self._name()] + [self._contact_name(o) for o in self.room_members]
        st["vc"] = self.room_codec()
        for o in list(self.room_members):
            p = self.peers.get(o)
            if p:
                packet = st
                if st.get('radio'):
                    revisions = self.room_host.setdefault('sent_revisions', {})
                    radio = st['radio']
                    previous = revisions.get(o)
                    full = not previous or previous[0] != radio['revision'] or time.monotonic()-previous[1] >= 30
                    if not full:
                        packet = {**st, 'radio': {k:v for k,v in radio.items() if k not in ('avatar', 'queue', 'permit', 'sounds')}}
                    await p.send({"t": "room_state", "state": packet})
                    if full: revisions[o] = (radio['revision'], time.monotonic())
                else:
                    await p.send({"t": "room_state", "state": packet})
        self.emit("room", self.room_view())
        hk = (json.dumps((st.get("track") or {}), sort_keys=True, ensure_ascii=False), len(self.room_members),
              (st.get('radio') or {}).get('revision'))
        if self.settings.get("share_now", True) and hk != self.__dict__.get("_room_hi_key"):
            self._room_hi_key = hk                             # трек/состав сменились — друзьям обновить «hi»
            await self._broadcast_friends(self._hi())

    async def _room_say(self, who, text):
        """Хост: строка в чат комнаты (who=None — служебная) — себе и всем гостям."""
        if who is None:
            line = {"from": "", "name": "", "text": text, "ts": time.time(), "sys": True}
        else:
            name = self._name() if who == self.me.onion else self._contact_name(who)
            line = {"from": who, "name": name, "text": text, "ts": time.time()}
        self.room_chat = (self.room_chat + [line])[-200:]
        self.emit("room_chat", line)
        for o in list(self.room_members):
            p = self.peers.get(o)
            if p:
                await p.send({"t": "room_chat", "line": line})

    async def room_join(self, host):
        if self.room_host is not None:
            await self.room_close()
        if self.room_guest and self.room_guest != host:
            await self.room_leave()
        self.room_guest = host                                 # заранее: ответы хоста-незнакомца пропустит фильтр
        p = self.peers.get(host)
        if not p:
            self.emit("toast", "Подключаюсь к комнате…")
            if not await self._dial_now(host):
                self.room_guest = None
                self.emit("toast", "Хост комнаты сейчас не в сети")
                return
            p = self.peers.get(host)
        self.room_state = None
        self.room_chat = []
        self._clock = []
        await p.send({"t": "room_join", "name": self._name(), "vc": self._vcaps()})
        await self._udp_offer(p)
        for _ in range(6):                                     # часы хоста: несколько замеров
            await p.send({"t": "ping", "c": time.time()})
            await asyncio.sleep(0.25)
        self.emit("room", self.room_view())

    async def room_leave(self):
        host = self.room_guest
        self.room_guest = None
        self.room_state = None
        if host and host in self.peers:
            await self.peers[host].send({"t": "room_leave"})
        self.emit("room", None)

    async def room_ping(self):
        if self.room_guest and self.room_guest in self.peers:
            await self.peers[self.room_guest].send({"t": "ping", "c": time.time()})

    async def room_say(self, text):
        text = clip(text, 500).strip()
        if not text:
            return
        if self.room_host is not None:
            await self._room_say(self.me.onion, text)
        elif self.room_guest and self.room_guest in self.peers:
            await self.peers[self.room_guest].send({"t": "room_say", "text": text})

    # ── очистка ── #

    def clear(self, what):
        self.store.clear(what, self.me.onion)
        self.emit("contacts")
        self.emit("feed")
        self.emit("message", None)
