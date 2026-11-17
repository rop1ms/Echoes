"""Спонсоры ECHOES в Echoes.NET: статус спонсора, стена «Наши спонсоры», ссылки на донаты.

Всё держится на подписях ed25519, как модерка и разрешения на радио (net_radio_auth):
  * статус спонсора — решение админа или модератора {"t": "echoes-sponsor", "by", "target", "allow", "tier"};
  * пост спонсора — один на человека, подписан им самим {"t": "echoes-sponsor-post", "by", "name", "text",
    "photo" (JPEG base64), "track", "id"}; новый пост заменяет прежний;
  * проверка поста — решение модерации {"t": "echoes-sponsor-ok", "by", "post", "author", "ok"}: на стене виден
    только одобренный пост (пока ждёт — его видит автор и модерация);
  * ссылки на донаты — только от админа {"t": "echoes-donate", "by", "links": [{"name", "url"}], "note"}.
Доходит до всех через события Nostr (kind 30078, теги ниже) и вместе с данными модерации при встрече друзей.
Ничего не запрещается и не урезается: спонсор получает только «сверху» — пост на стене, значок и особые рамки.
"""
from __future__ import annotations

import base64
import json
import math
import secrets
import time

TAGS = ("echoes-sponsor", "echoes-sponsor-post", "echoes-sponsor-ok", "echoes-donate")
PHOTO_LIMIT = 40000                    # base64 фото поста (событие Nostr целиком — до ~64 КБ)
TEXT_LIMIT = 280
NAME_LIMIT = 40
TIERS = {"supporter": "Спонсор", "patron": "Меценат", "legend": "Легенда"}
NODE = None                            # NetNode — ставит net_page (для значков и рамок без ссылки на страницу)


def _empty():
    return {"sponsors": {}, "posts": {}, "oks": {}, "donate": None}


def load(node) -> dict:
    st = node.__dict__.get("_sponsors")
    if st is None:
        try:
            raw = json.loads((node.base / "sponsors.json").read_text("utf-8"))
        except (OSError, ValueError):
            raw = {}
        st = _empty()
        if isinstance(raw, dict):
            for k, d in (raw.get("sponsors") or {}).items():
                if _dec_ok(node, d):
                    st["sponsors"][k] = d
            for k, p in (raw.get("posts") or {}).items():
                if _post_ok(node, p, check_sponsor=False):
                    st["posts"][k] = p
            for k, o in (raw.get("oks") or {}).items():
                if _ok_ok(node, o):
                    st["oks"][k] = o
            if _donate_ok(node, raw.get("donate")):
                st["donate"] = raw["donate"]
        node._sponsors = st
    return st


def _save(node):
    try:
        (node.base / "sponsors.json").write_text(json.dumps(load(node), ensure_ascii=False), "utf-8")
    except OSError:
        pass


def _ts_ok(ts) -> bool:
    return isinstance(ts, (float, int)) and not isinstance(ts, bool) and math.isfinite(ts) and 0 < ts <= time.time() + 120


# ── проверки ── #

def _dec_ok(node, d) -> bool:
    from net_core import normalize_code, verify_obj
    if not isinstance(d, dict) or d.get("t") != "echoes-sponsor" or len(json.dumps(d)) > 2000:
        return False
    return (type(d.get("allow")) is bool and _ts_ok(d.get("ts")) and bool(normalize_code(d.get("target")))
            and node.role(d.get("by")) in ("admin", "mod") and verify_obj(d, "by"))


def _post_ok(node, p, check_sponsor=True) -> bool:
    from net_core import normalize_code, verify_obj
    if not isinstance(p, dict) or p.get("t") != "echoes-sponsor-post" or len(json.dumps(p)) > PHOTO_LIMIT + 4000:
        return False
    if not normalize_code(p.get("by")) or not _ts_ok(p.get("ts")) or not isinstance(p.get("id"), str):
        return False
    if len(str(p.get("text") or "")) > TEXT_LIMIT or len(str(p.get("name") or "")) > NAME_LIMIT:
        return False
    ph = p.get("photo") or ""
    if not isinstance(ph, str) or len(ph) > PHOTO_LIMIT:
        return False
    if check_sponsor and not is_sponsor(node, p["by"]):
        return False
    return verify_obj(p, "by")


def _ok_ok(node, o) -> bool:
    from net_core import verify_obj
    if not isinstance(o, dict) or o.get("t") != "echoes-sponsor-ok" or len(json.dumps(o)) > 1500:
        return False
    return (type(o.get("ok")) is bool and _ts_ok(o.get("ts")) and isinstance(o.get("post"), str)
            and node.role(o.get("by")) in ("admin", "mod") and verify_obj(o, "by"))


def _donate_ok(node, d) -> bool:
    from net_core import verify_obj
    if not isinstance(d, dict) or d.get("t") != "echoes-donate" or len(json.dumps(d)) > 6000:
        return False
    links = d.get("links")
    if not isinstance(links, list) or len(links) > 8:
        return False
    for ln in links:
        if not isinstance(ln, dict) or not str(ln.get("url") or "").startswith(("https://", "http://")):
            return False
    return _ts_ok(d.get("ts")) and node.role(d.get("by")) == "admin" and verify_obj(d, "by")


# ── приём (из Nostr и от друзей) ── #

def take(node, obj) -> bool:
    if not isinstance(obj, dict):
        return False
    t = obj.get("t")
    st = load(node)
    changed = False
    if t == "echoes-sponsor" and _dec_ok(node, obj):
        old = st["sponsors"].get(obj["target"])
        if not old or (old["ts"], old.get("id", "")) < (obj["ts"], obj.get("id", "")):
            st["sponsors"][obj["target"]] = obj
            changed = True
    elif t == "echoes-sponsor-post" and _post_ok(node, obj, check_sponsor=False):
        old = st["posts"].get(obj["by"])
        if not old or old["ts"] < obj["ts"]:
            st["posts"][obj["by"]] = obj
            changed = True
    elif t == "echoes-sponsor-ok" and _ok_ok(node, obj):
        old = st["oks"].get(obj["post"])
        if not old or old["ts"] < obj["ts"]:
            st["oks"][obj["post"]] = obj
            changed = True
    elif t == "echoes-donate" and _donate_ok(node, obj):
        old = st["donate"]
        if not old or old["ts"] < obj["ts"]:
            st["donate"] = obj
            changed = True
    if changed:
        while len(st["posts"]) > 500:
            st["posts"].pop(min(st["posts"], key=lambda k: st["posts"][k]["ts"]))
        _save(node)
        node.emit("sponsors", t)
    return changed


def payload(node) -> list:
    """Всё подписанное — для друга при встрече (вместе с данными модерации)."""
    st = load(node)
    out = list(st["sponsors"].values())[:300] + list(st["oks"].values())[:300]
    out += sorted(st["posts"].values(), key=lambda p: -p["ts"])[:60]
    if st["donate"]:
        out.append(st["donate"])
    return out


def take_many(node, items):
    for it in (items or [])[:700]:
        take(node, it)


# ── вопросы ── #

def is_sponsor(node, onion=None) -> bool:
    if node is None:
        return False
    onion = onion or node.me.onion
    if not onion:
        return False
    d = load(node)["sponsors"].get(onion)
    return bool(d and d.get("allow"))


def tier(node, onion=None) -> str:
    d = load(node)["sponsors"].get(onion or node.me.onion) or {}
    return d.get("tier") if d.get("allow") and d.get("tier") in TIERS else ("supporter" if d.get("allow") else "")


def sponsors(node) -> list:
    return [d for d in load(node)["sponsors"].values() if d.get("allow")]


def post_state(node, post) -> str:
    """approved | rejected | pending."""
    o = load(node)["oks"].get(post.get("id"))
    if o is None or o.get("author") not in ("", None, post.get("by")):
        return "pending"
    return "approved" if o.get("ok") else "rejected"


def wall(node) -> list:
    """Одобренные посты действующих спонсоров, свежие первыми."""
    st = load(node)
    out = [p for p in st["posts"].values() if is_sponsor(node, p["by"]) and post_state(node, p) == "approved"
           and not node.staff_hidden(p["by"])]
    return sorted(out, key=lambda p: -p["ts"])


def queue(node) -> list:
    """Ждут проверки (для модерации)."""
    st = load(node)
    return sorted((p for p in st["posts"].values() if is_sponsor(node, p["by"]) and post_state(node, p) == "pending"),
                  key=lambda p: p["ts"])


def my_post(node):
    return load(node)["posts"].get(node.me.onion)


def donate_links(node) -> list:
    d = load(node)["donate"] or {}
    return [{"name": str(x.get("name") or "")[:30], "url": str(x.get("url") or "")} for x in d.get("links") or []]


def donate_note(node) -> str:
    return str((load(node)["donate"] or {}).get("note") or "")[:300]


def photo_bytes(post) -> bytes:
    try:
        return base64.b64decode(post.get("photo") or "")
    except ValueError:
        return b""


# ── действия (в сетевом цикле: node.call(fn, node, …)) ── #

async def _publish(node, obj, tag, d):
    try:
        await node._staff_publish(obj, tag, d)
    except Exception as e:                                     # noqa: BLE001
        print("[sponsor] publish:", e)


async def grant(node, target, allow=True, tier_="supporter"):
    from net_core import normalize_code
    target = normalize_code(target)
    if node.my_role() not in ("admin", "mod") or not target:
        return None
    d = node.me.sign_obj({"t": "echoes-sponsor", "by": node.me.onion, "target": target, "allow": bool(allow),
                          "tier": tier_ if tier_ in TIERS else "supporter", "ts": time.time(),
                          "id": secrets.token_hex(10)})
    if take(node, d):
        await _publish(node, d, "echoes-sponsor", "sponsor:" + target)
        node.emit("toast", ("Статус спонсора выдан" if allow else "Статус спонсора снят"))
    return d


async def submit_post(node, name, text, photo_b64, track):
    from net_core import clean_track, clip
    if not is_sponsor(node):
        node.emit("toast", "Пост на стене спонсоров — для тех, кто поддержал ECHOES")
        return None
    p = node.me.sign_obj({"t": "echoes-sponsor-post", "by": node.me.onion, "name": clip(name, NAME_LIMIT),
                          "text": clip(text, TEXT_LIMIT), "photo": photo_b64 if len(photo_b64 or "") <= PHOTO_LIMIT
                          else "", "track": clean_track(track) if track else None, "ts": time.time(),
                          "id": secrets.token_hex(12)})
    if take(node, p):
        await _publish(node, p, "echoes-sponsor-post", "sponsor-post:" + node.me.onion)
        node.emit("toast", "Пост отправлен на проверку — появится на стене после одобрения")
    return p


async def review(node, post, ok: bool):
    if node.my_role() not in ("admin", "mod") or not isinstance(post, dict):
        return None
    o = node.me.sign_obj({"t": "echoes-sponsor-ok", "by": node.me.onion, "post": post.get("id"),
                          "author": post.get("by"), "ok": bool(ok), "ts": time.time()})
    if take(node, o):
        await _publish(node, o, "echoes-sponsor-ok", "sponsor-ok:" + str(post.get("id")))
        node.emit("toast", "Пост одобрен" if ok else "Пост отклонён")
    return o


async def set_donate(node, links, note=""):
    if node.my_role() != "admin":
        return None
    clean = [{"name": str(x.get("name") or "")[:30], "url": str(x.get("url") or "").strip()[:300]}
             for x in links if str(x.get("url") or "").strip().startswith(("https://", "http://"))][:8]
    d = node.me.sign_obj({"t": "echoes-donate", "by": node.me.onion, "links": clean, "note": str(note)[:300],
                          "ts": time.time()})
    if take(node, d):
        await _publish(node, d, "echoes-donate", "donate")
        node.emit("toast", "Ссылки на донаты обновлены у всех")
    return d


def photo_from_file(path: str) -> str:
    """Фото для поста: обрезка в квадрат, 420 px, JPEG — ужимается, пока не влезет в лимит."""
    from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PyQt6.QtGui import QImage, QImageReader
    rd = QImageReader(path)
    rd.setAutoTransform(True)
    img = rd.read()
    if img.isNull():
        return ""
    s = min(img.width(), img.height())
    img = img.copy((img.width() - s) // 2, (img.height() - s) // 2, s, s)
    for side, q in ((420, 78), (380, 70), (340, 62), (300, 55), (260, 50)):
        im = img.scaled(side, side, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        im.save(buf, "JPEG", q)
        b = base64.b64encode(bytes(ba)).decode()
        if len(b) <= PHOTO_LIMIT:
            return b
    return ""
