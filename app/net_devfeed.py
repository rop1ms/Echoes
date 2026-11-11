# net_devfeed.py
"""
Echoes.NET: лента и друзья для своего второго устройства (телефон Echoes Lite, второй ПК).

Зачем: у привязанного устройства свой ключ, друзья его не знают — посты они шлют только этому ПК.
Этот модуль делает ПК «зеркалом»: он отдаёт своему устройству список друзей и ленту, а действия
устройства (реакция, голос, комментарий, пост) выполняет от своего имени — подпись ставит ПК, поэтому
друзьям ничего обновлять не нужно. Работает, пока ПК в сети.

Сообщения — только между привязанными устройствами (settings["my_devices"], привязка — net_devsync):

    устройство → ПК   {"t":"devfeed_req","before":ts,"lim":n}     страница ленты (before=0 — самая свежая)
    ПК → устройство   {"t":"devfeed","items":[…],"contacts":[…],"me":{…},"more":bool}
                      items — те же «треды», что в post_new (пост + комментарии + голоса + реакции),
                      каждый подписан своим автором: устройство проверяет подписи само, ПК подделать не может
    ПК → устройство   {"t":"devfeed_upd","item":…} / {"t":"devfeed_del","id":…}   живые изменения
    устройство → ПК   {"t":"dev_act","nonce":…,"act":"react|vote|comment|publish|delete",…}
    ПК → устройство   {"t":"dev_act_ok","nonce":…,"ok":bool,"err":…}

Через релеи Nostr лента не передаётся (большие частые события там банят): нужен Tor, LAN или прямой канал.
Модуль без Qt: всё выполняется в сетевом потоке NetNode.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import time

TYPES = ("devfeed_req", "devfeed", "devfeed_upd", "devfeed_del", "dev_act", "dev_act_ok")
PAGE = 20                       # постов на страницу по умолчанию (телефону с 512 МБ больше не нужно)
PAGE_MAX = 40
ITEM_MAX = 256 * 1024           # один тред целиком; больше — не пересылаем (устройство увидит skipped)
BATCH_MAX = 1536 * 1024         # одна страница целиком — заметно меньше предела строки протокола (4 МБ)
ACTS_PER_MIN = 30
PUSH_DELAY = 0.3                # изменения одного поста за это время уходят одним сообщением
PUBLISH_KEYS = ("at", "tracks", "title", "hint", "url", "quote", "week", "theme", "flair")
REACT_KINDS = ("emo", "pick", "solved", "cv")


def devices(nd) -> list:
    return list(nd.settings.get("my_devices") or [])


def is_device(nd, onion) -> bool:
    return onion in devices(nd)


def share_on(nd, onion) -> bool:
    """Передавать ли этому устройству друзей и ленту (переключатель в «Мои устройства»; по умолчанию да)."""
    return is_device(nd, onion) and bool((nd.settings.get("dev_feed") or {}).get(onion, True))


def set_share(nd, onion, on: bool):
    d = dict(nd.settings.get("dev_feed") or {})
    d[onion] = bool(on)
    nd.settings["dev_feed"] = d
    nd.save_settings()
    if not on:
        _st(nd)["subs"].discard(onion)


def _st(nd) -> dict:
    """Состояние модуля на узле: подписчики, отправленные хэши, одноразовые номера, ожидающие ответы."""
    st = nd.__dict__.get("_devfeed")
    if st is None:
        st = nd.__dict__["_devfeed"] = {"subs": set(), "sent": {}, "nonces": {}, "acts": {}, "dirty": set(),
                                        "gone": set(), "timer": None, "quiet": 0, "wait": {}, "last": {},
                                        "pend": {}}
    return st


def _num(v, d=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _size(obj) -> int:
    return len(json.dumps(obj, ensure_ascii=False))


def _digest(item) -> str:
    return hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]


def _heavy(p) -> bool:
    """Соединение, по которому ленту слать нельзя (релеи Nostr)."""
    return getattr(p, "via", "") == "nostr"


# ══════════════════════════════════════════════════════════════════════════ #
#  ПК → устройство: страница ленты и живые изменения
# ══════════════════════════════════════════════════════════════════════════ #

def page(nd, before=0.0, lim=PAGE) -> dict:
    """Страница ленты: свои посты и посты друзей, от свежих к старым, начиная раньше before."""
    lim = max(1, min(PAGE_MAX, int(_num(lim, PAGE) or PAGE)))
    before = _num(before)
    posts = nd.store.posts(None, 300)
    if before > 0:
        posts = [p for p in posts if _num(p.get("ts")) < before]
    items, total, skipped = [], 0, 0
    for p in posts:
        if len(items) >= lim:
            break
        it = nd._thread_item(p)
        n = _size(it)
        if n > ITEM_MAX:
            skipped += 1
            continue
        if total + n > BATCH_MAX:
            break
        items.append(it)
        total += n
    last_ts = _num(items[-1]["post"].get("ts")) if items else 0.0
    more = bool(items) and any(_num(p.get("ts")) < last_ts for p in posts)
    out = {"t": "devfeed", "items": items, "more": more, "skipped": skipped}
    if before <= 0:                                            # первая страница — заодно друзья и «кто я»
        devs = set(devices(nd))
        out["contacts"] = [{"onion": c["onion"], "name": c.get("name") or "", "bio": c.get("bio") or ""}
                           for c in nd.store.contacts("friend") if c["onion"] not in devs][:500]
        out["me"] = {"onion": nd.me.onion, "name": nd._name()}
    return out


async def _on_req(nd, p, o, m):
    if not share_on(nd, o):
        await p.send({"t": "devfeed", "items": [], "off": "disabled"})
        return
    if _heavy(p):
        await p.send({"t": "devfeed", "items": [], "off": "relay"})
        return
    st = _st(nd)
    out = page(nd, m.get("before"), m.get("lim"))
    for it in out["items"]:
        st["sent"][(o, it["post"]["id"])] = _digest(it)
    st["subs"].add(o)
    await p.send(out)


def touch(nd, pid):
    """Пост появился или изменился (вызывает net_core) — отправить подписанным устройствам."""
    st = nd.__dict__.get("_devfeed")
    if not st or not st["subs"] or st["quiet"] or not pid:
        return
    st["dirty"].add(str(pid))
    _schedule(nd, st)


def gone(nd, pid):
    """Пост удалён (вызывает net_core)."""
    st = nd.__dict__.get("_devfeed")
    if not st or not st["subs"] or st["quiet"] or not pid:
        return
    st["gone"].add(str(pid))
    st["dirty"].discard(str(pid))
    _schedule(nd, st)


def _schedule(nd, st, delay=PUSH_DELAY):
    if st["timer"] is None and nd.loop is not None:
        st["timer"] = nd.loop.call_later(delay, lambda: asyncio.ensure_future(_flush(nd)))


async def _flush(nd):
    st = _st(nd)
    st["timer"] = None
    dirty0, dead0 = set(st["dirty"]), set(st["gone"])
    st["dirty"], st["gone"] = set(), set()
    retry = False
    for o in list(st["subs"]):
        if not share_on(nd, o):
            st["subs"].discard(o)
            st["pend"].pop(o, None)
            continue
        pd, pg = st["pend"].pop(o, (set(), set()))            # то, что не ушло, пока устройства не было на связи
        dead = sorted(dead0 | pg)
        dirty = sorted((dirty0 | pd) - set(dead))
        p = nd.peers.get(o)
        if p is None or not p.alive or _heavy(p):
            if len(pd) + len(dirty0) <= 300:                   # копим недолго; дальше устройство само перезапросит
                st["pend"][o] = (set(dirty), set(dead))
                retry = True
            continue
        for pid in dead:
            st["sent"].pop((o, pid), None)
            await p.send({"t": "devfeed_del", "id": pid})
        for pid in dirty:
            post = nd.store.post(pid)
            if not post:
                continue
            it = nd._thread_item(post)
            if _size(it) > ITEM_MAX:
                continue
            h = _digest(it)
            if st["sent"].get((o, pid)) == h:                  # то же самое уже отправляли — не гонять по кругу
                continue
            st["sent"][(o, pid)] = h
            await p.send({"t": "devfeed_upd", "item": it})
    if len(st["sent"]) > 6000:
        st["sent"].clear()
    if retry:
        _schedule(nd, st, 2.0)


# ══════════════════════════════════════════════════════════════════════════ #
#  устройство → ПК: действия от имени ПК
# ══════════════════════════════════════════════════════════════════════════ #

def _rate_ok(st, o) -> bool:
    now = time.time()
    q = [t for t in st["acts"].get(o, []) if now - t < 60]
    if len(q) >= ACTS_PER_MIN:
        st["acts"][o] = q
        return False
    q.append(now)
    st["acts"][o] = q
    return True


async def _do_act(nd, m) -> str:
    """Выполнить действие устройства существующими методами узла. Возвращает '' или текст ошибки."""
    from net_core import clip, clean_track, POST_KINDS
    act = m.get("act")
    pid = clip(m.get("pid"), 64)
    if act in ("react", "vote", "comment", "delete") and not nd.store.post(pid):
        return "нет такого поста"
    if act == "react":
        kind, val = m.get("kind"), clip(m.get("val"), 80)
        if kind not in REACT_KINDS or val.startswith("c:"):   # свои реакции-картинки — только с самого ПК
            return "неизвестная реакция"
        r = {"kind": kind, "val": val}
        if not nd._react_ok(r):
            return "неизвестная реакция"
        await nd.react(pid, kind, val)
    elif act == "vote":
        try:
            val = int(m.get("val"))
        except (TypeError, ValueError):
            return "плохой голос"
        if val not in (-1, 0, 1):
            return "плохой голос"
        await nd.vote(pid, val)
    elif act == "comment":
        text, track = clip(m.get("text")).strip(), clean_track(m.get("track"))
        if not text and not track:
            return "пустой комментарий"
        if nd.mod_check(text):
            return "похоже на запрещённое"
        await nd.comment(pid, text, parent=clip(m.get("parent"), 64), track=track, at=m.get("at"))
    elif act == "publish":
        kind = m.get("kind") if m.get("kind") in POST_KINDS else "post"
        if kind == "mod":
            return "моды публикуются только с ПК"
        extra = {k: m[k] for k in PUBLISH_KEYS if k in m}
        if kind == "repost":
            orig = nd.store.post(clip(m.get("orig"), 64))
            if not orig:
                return "нет такого поста"
            extra["orig"] = orig
        before = len(nd.store.posts(nd.me.onion, 500))
        await nd.publish(clip(m.get("text")), track=m.get("track"), kind=kind, **extra)
        if len(nd.store.posts(nd.me.onion, 500)) == before:
            return "пост не опубликован"
    elif act == "delete":
        post = nd.store.post(pid)
        if post["author"] != nd.me.onion:
            return "удалить можно только свой пост"
        await nd.delete_post(pid)
    else:
        return "неизвестное действие"
    return ""


async def _on_act(nd, p, o, m):
    st = _st(nd)
    nonce = str(m.get("nonce") or "")[:40]
    if not nonce:
        return
    if not share_on(nd, o):
        await p.send({"t": "dev_act_ok", "nonce": nonce, "ok": False, "err": "передача ленты выключена"})
        return
    if nonce in st["nonces"]:                                  # повтор (переотправка) — ответить тем же, не выполнять
        await p.send(dict(st["nonces"][nonce], t="dev_act_ok", nonce=nonce))
        return
    if not _rate_ok(st, o):
        await p.send({"t": "dev_act_ok", "nonce": nonce, "ok": False, "err": "слишком часто"})
        return
    try:
        err = await _do_act(nd, m)
    except Exception as e:                                     # noqa: BLE001
        nd.log(f"[net] dev_act: {type(e).__name__} {e}")
        err = "ошибка на ПК"
    res = {"ok": not err, "err": err}
    st["nonces"][nonce] = res
    if len(st["nonces"]) > 400:
        for k in list(st["nonces"])[:200]:
            st["nonces"].pop(k, None)
    await p.send(dict(res, t="dev_act_ok", nonce=nonce))


# ══════════════════════════════════════════════════════════════════════════ #
#  сторона устройства (второй ПК; телефон делает то же самое на Java)
# ══════════════════════════════════════════════════════════════════════════ #

def pull_on(nd) -> bool:
    """Этот ПК сам берёт ленту с другого своего устройства (по умолчанию нет — у ПК свои друзья)."""
    return bool(nd.settings.get("dev_feed_pull"))


async def request(nd, onion, before=0.0, lim=PAGE) -> bool:
    if not is_device(nd, onion):
        return False
    p = await nd._peer_for(onion)
    if p is None:
        return False
    await p.send({"t": "devfeed_req", "before": _num(before), "lim": int(lim)})
    return True


def _take(nd, items) -> int:
    """Принять треды: подпись каждого поста проверяется его автором, как в обычной ленте."""
    st = _st(nd)
    n = 0
    st["quiet"] += 1                                           # принятое не пересылать обратно своим устройствам
    try:
        for it in items[:PAGE_MAX]:
            post = it.get("post") if isinstance(it, dict) else None
            if not isinstance(post, dict) or _size(it) > ITEM_MAX:
                continue
            author = str(post.get("author") or "")
            if author == nd.me.onion:                          # свои посты приходят только от себя
                continue
            had = nd.store.post(str(post.get("id"))) is not None
            nd._take_posts(author, [it], None)
            if nd.store.post(str(post.get("id"))) is not None:
                n += 1 if not had else 0
                st["last"][str(post["id"])] = time.time()
    finally:
        st["quiet"] -= 1
    return n


def _on_feed(nd, o, m):
    if not pull_on(nd):
        return
    st = _st(nd)
    names = nd.__dict__.setdefault("_names", {})
    for c in (m.get("contacts") or [])[:500]:
        if isinstance(c, dict) and isinstance(c.get("onion"), str) and c.get("name"):
            names.setdefault(c["onion"], str(c["name"])[:40])
    me = m.get("me") if isinstance(m.get("me"), dict) else {}
    if m.get("off"):
        nd.emit("devfeed", {"from": o, "off": str(m.get("off"))[:20]})
        return
    items = m.get("items") if isinstance(m.get("items"), list) else []
    new = _take(nd, items)
    st["wait"].pop(("page", o), None)
    nd.emit("feed")
    nd.emit("devfeed", {"from": o, "new": new, "more": bool(m.get("more")), "me": str(me.get("onion") or "")[:80]})


def _on_upd(nd, o, m):
    if pull_on(nd) and isinstance(m.get("item"), dict):
        _take(nd, [m["item"]])
        nd.emit("feed")


def _on_del(nd, o, m):
    if not pull_on(nd):
        return
    pid = str(m.get("id") or "")[:64]
    post = nd.store.post(pid)
    # удаляем только то, что пришло зеркалом: свои посты и посты своих друзей ведёт обычный протокол
    if post and post["author"] != nd.me.onion and not nd.is_friend(post["author"]):
        st = _st(nd)
        st["quiet"] += 1
        try:
            nd.store.delete_post(pid)
        finally:
            st["quiet"] -= 1
        nd.emit("feed")


async def act(nd, onion, act_name, **args) -> str:
    """Попросить свой ПК выполнить действие. Возвращает nonce; ответ придёт событием devact."""
    if not is_device(nd, onion):
        return ""
    p = await nd._peer_for(onion)
    if p is None:
        return ""
    nonce = secrets.token_hex(8)
    await p.send(dict(args, t="dev_act", nonce=nonce, act=act_name))
    return nonce


# ══════════════════════════════════════════════════════════════════════════ #
#  разбор входящих (net_core._on_message)
# ══════════════════════════════════════════════════════════════════════════ #

async def on_message(nd, p, o, m):
    if not is_device(nd, o):                                   # от чужих — молча ничего
        return
    t = m.get("t")
    if t == "devfeed_req":
        await _on_req(nd, p, o, m)
    elif t == "dev_act":
        await _on_act(nd, p, o, m)
    elif t == "devfeed":
        _on_feed(nd, o, m)
    elif t == "devfeed_upd":
        _on_upd(nd, o, m)
    elif t == "devfeed_del":
        _on_del(nd, o, m)
    elif t == "dev_act_ok":
        nd.emit("devact", {"from": o, "nonce": str(m.get("nonce") or "")[:40], "ok": bool(m.get("ok")),
                           "err": str(m.get("err") or "")[:200]})
