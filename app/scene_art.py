# scene_art.py
"""
«Сцена»: что стоит на месте обложки — гифка, вырезанный персонаж или сама обложка.

Порядок выбора:
  1. своя картинка или гифка, которую пользователь выбрал для этого трека (правый клик по обложке в «Сцене»);
  2. гифка с названием трека или с образом, который распознал режиссёр. Поиск использует ключ Tenor
     или Giphy из «Сеть → GIF». Результат сохраняется для этой песни и образа;
  3. обложка трека.

Потом — вырезание фона (bg_remove, своя модель без сети): если у картинки ровный однотонный фон, персонаж
остаётся один и стоит прямо на фоне сцены. Для гифок результат кладётся в ~/Echoes/scenes/cut/ (анимированный
WebP) и второй раз не считается. Картинки с уже прозрачным фоном показываются как есть.

Всё здесь — для фонового потока: чтение файлов, сеть и вырезание могут занять секунды.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

import numpy as np
from scene_cards import scene_dir

MAX_GIF_BYTES = 12 * 1024 * 1024
MAX_CUT_FRAMES = 90
MAX_CUT_PIXELS = 36_000_000                                    # кадры × ширина × высота — больше не вырезаем
_LOCK = threading.RLock()
STORE_V = 3


def _dir() -> Path:
    return scene_dir()


def _store_path() -> Path:
    return _dir() / "art.json"


def load_store() -> dict:
    try:
        d = json.loads(_store_path().read_text(encoding="utf-8"))
        if isinstance(d, dict):
            if d.get("v") != STORE_V:                          # прежний поиск брал гифки к исполнителю — забыть их
                d["auto"] = {}
            return {"user": dict(d.get("user") or {}), "auto": dict(d.get("auto") or {}),
                    "nocut": list(d.get("nocut") or []), "nogif": list(d.get("nogif") or []),
                    "cut": list(d.get("cut") or [])}
    except (OSError, ValueError):
        pass
    return {"user": {}, "auto": {}, "nocut": [], "nogif": [], "cut": []}


def save_store(st: dict):
    with _LOCK:
        p = _store_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps({**st, "v": STORE_V}, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)


def set_user_art(key: str, path: str | None):
    """Своя картинка для трека (None — убрать и вернуться к автоматике)."""
    with _LOCK:
        st = load_store()
        if path:
            st["user"][key] = str(path)
        else:
            st["user"].pop(key, None)
        save_store(st)


def set_flag(key: str, flag: str, on: bool):
    """flag: "nocut" — не вырезать фон у своей картинки и гифки, "cut" — вырезать персонажа с обложки,
    "nogif" — не искать гифку для этого трека."""
    with _LOCK:
        st = load_store()
        cur = set(st.get(flag) or [])
        (cur.add if on else cur.discard)(key)
        st[flag] = sorted(cur)
        save_store(st)


def clear_auto(key):
    with _LOCK:
        st = load_store()
        for match in list(st["auto"]):
            if match.startswith(key + ":"):
                del st["auto"][match]
        save_store(st)


def gif_settings(win) -> tuple:
    """(сервис, ключ) поиска гифок из настроек Echoes.NET или ("", "")."""
    node = getattr(win, "_net_node", None)
    s = getattr(node, "settings", None)
    if not isinstance(s, dict):
        return "", ""
    order = [s.get("gif_provider")] + ["tenor", "giphy"]
    for prov in order:
        if prov in ("tenor", "giphy"):
            key = str(s.get(f"gif_key_{prov}") or "").strip()
            if key:
                return prov, key
    return "", ""


def is_animated(path: str) -> bool:
    try:
        from PIL import Image
        with Image.open(path) as im:
            return bool(getattr(im, "is_animated", False)) and getattr(im, "n_frames", 1) > 1
    except Exception:                                          # noqa: BLE001
        return False


def _tokens(text: str) -> list:
    return [w for w in "".join(ch if ch.isalnum() else " " for ch in text.lower().replace("ё", "е")).split()
            if len(w) >= 3]


def gif_matches(desc: str, artist: str, title: str) -> bool:
    """Require the song title as a phrase and disambiguate one-word titles with the artist."""
    terms = _tokens(desc)
    tt, at = _tokens(title), _tokens(artist)
    if not tt or (" " + " ".join(tt) + " ") not in (" " + " ".join(terms) + " "):
        return False
    return len(tt) > 1 or bool(set(at).intersection(terms))


def download_gif(url: str) -> str:
    """Скачать гифку с CDN Tenor/Giphy в кэш гифок → путь или ""."""
    import net_gif
    import requests
    url = net_gif.safe_url(url)
    if not url:
        return ""
    f = net_gif.cache_file(url)
    if f.is_file():
        return str(f)
    try:
        data = b""
        with requests.get(url, timeout=20, stream=True) as r:
            r.raise_for_status()
            for chunk in r.iter_content(64 * 1024):
                data += chunk
                if len(data) > MAX_GIF_BYTES:
                    return ""
        if data[:3] != b"GIF":
            return ""
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
        return str(f)
    except Exception as e:                                     # noqa: BLE001
        print("[scene art] gif download:", type(e).__name__)
        return ""


def find_gif(artist, title, provider, key, motif="") -> str:
    """Prefer an exact song match. Rank topical alternatives with the local model."""
    import net_gif
    from scene_director import MOTIFS, match_score
    query = f"{artist} {title}".strip()
    exact = net_gif.search(provider, key, query, limit=12) if query and _tokens(title) else []
    matches = [g for g in exact if gif_matches(str(g.get("title") or ""), artist, title)]
    if motif in MOTIFS and not matches:
        stock = net_gif.search(provider, key, MOTIFS[motif].query, limit=16)
        scored = [(match_score(str(g.get("title") or ""), motif), g) for g in stock]
        matches = [g for score, g in sorted(scored, key=lambda item: -item[0]) if score >= .15]
    for g in matches[:3]:
        path = download_gif(g.get("url"))
        if path and is_animated(path):
            return path
    return ""


def plain_border(rgba: np.ndarray) -> bool:
    """Ровный ли одноцветный фон хотя бы с трёх сторон кадра (тогда персонажа можно вырезать)."""
    h, w = rgba.shape[:2]
    if h < 24 or w < 24:
        return False
    b = max(2, int(min(h, w) * 0.04))
    rgb = rgba[..., :3].astype(np.float32)
    q = 4                                                      # усреднить по 4×4: зерно гифки и шум сжатия не в счёт
    hq, wq = h // q * q, w // q * q
    rgb = rgb[:hq, :wq].reshape(hq // q, q, wq // q, q, 3).mean(axis=(1, 3))
    h, w = rgb.shape[:2]
    b = max(1, int(min(h, w) * 0.05))
    sides = [rgb[:b].reshape(-1, 3), rgb[-b:].reshape(-1, 3), rgb[:, :b].reshape(-1, 3), rgb[:, -b:].reshape(-1, 3)]
    flat = [sd.mean(axis=0) for sd in sides if float(sd.std(axis=0).mean()) < 16.0]
    if len(flat) < 3:                                          # одна сторона может быть занята: персонаж стоит на краю
        return False
    m = np.array(flat)
    return float((m.max(axis=0) - m.min(axis=0)).max()) < 26.0     # и ровные стороны — одного цвета


def has_alpha(rgba: np.ndarray) -> bool:
    """Фон уже прозрачный (наклейка, PNG персонажа)."""
    return rgba.shape[-1] == 4 and float((rgba[..., 3] < 40).mean()) > 0.08


def _good_cut(a: np.ndarray) -> bool:
    cover = float((a > 128).mean())
    return 0.06 < cover < 0.82


def trim(rgba: np.ndarray) -> np.ndarray:
    """Обрезать пустые поля вокруг персонажа."""
    ys, xs = np.where(rgba[..., 3] > 16)
    if len(ys) == 0:
        return rgba
    return rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def static_cutout(path: str) -> np.ndarray | None:
    """Персонаж без фона из обычной картинки (RGBA) или None, если вырезать нечего."""
    try:
        import bg_remove
        frames, _d, _anim = bg_remove.load_frames(path)
        f = frames[0]
        if max(f.shape[:2]) > 900:                             # для сцены больше не нужно, а считать быстрее
            from PIL import Image
            k = 900 / max(f.shape[:2])
            f = np.array(Image.fromarray(f, "RGBA").resize((max(1, int(f.shape[1] * k)), max(1, int(f.shape[0] * k))),
                                                           Image.LANCZOS))
        if has_alpha(f):
            return trim(f)
        if not plain_border(f):
            return None
        out = bg_remove.fit_model([f]).cutout(f)
        return trim(out) if _good_cut(out[..., 3]) else None
    except Exception as e:                                     # noqa: BLE001
        print("[scene art] cutout:", e)
        return None


def animated_cutout(path: str) -> str:
    """Гифка без фона → путь к анимированному WebP в ~/Echoes/scenes/cut или "" (фон не ровный, слишком большая)."""
    try:
        import bg_remove
        src = Path(path)
        sig = hashlib.sha1(f"{src}|{src.stat().st_size}|{int(src.stat().st_mtime)}".encode("utf-8")).hexdigest()[:20]
        out = _dir() / "cut" / f"{sig}.webp"
        mark = out.with_suffix(".no")
        if out.is_file():
            return str(out)
        if mark.is_file():
            return ""
        from PIL import Image
        with Image.open(src) as source:
            n = getattr(source, "n_frames", 1)
            if not 2 <= n <= MAX_CUT_FRAMES or n * source.width * source.height > MAX_CUT_PIXELS:
                return ""
        frames, durs, anim = bg_remove.load_frames(str(src))
        if not anim or len(frames) > MAX_CUT_FRAMES:
            return ""
        h, w = frames[0].shape[:2]
        out.parent.mkdir(parents=True, exist_ok=True)
        if len(frames) * h * w > MAX_CUT_PIXELS or has_alpha(frames[0]) or not plain_border(frames[0]):
            mark.write_bytes(b"")                              # прозрачная гифка играет как есть; неровный фон — не трогаем
            return ""
        model = bg_remove.fit_model(frames)
        cut = [model.cutout(f) for f in frames]
        if not _good_cut(cut[0][..., 3]):
            mark.write_bytes(b"")
            return ""
        bg_remove.save(cut, durs, True, str(out))
        return str(out) if out.is_file() else ""
    except Exception as e:                                     # noqa: BLE001
        print("[scene art] gif cutout:", e)
        return ""


def resolve(key: str, cover: str, gif: tuple = ("", ""), motif="") -> dict:
    """Resolve the user's override, the current motif's GIF, or the track cover."""
    st = load_store()
    cut_ok = key not in st["nocut"]
    p = st["user"].get(key)
    if p and Path(p).is_file():
        return {"path": p, "source": "user", "animated": is_animated(p), "cut": cut_ok}
    prov, gkey = gif
    if prov and gkey and key not in st["nogif"]:
        known = (st["auto"].get(f"{key}:{prov}:{motif}") or {}).get("path")
        if known and Path(known).is_file():
            return {"path": known, "source": "gif", "animated": True, "cut": cut_ok}
    # обложку сами не режем: у многих обложек ровный фон, а вырезать там нечего — только по просьбе
    return {"path": cover, "source": "cover", "animated": False, "cut": key in st["cut"]}


def fetch_auto(key, artist, title, gif, motif):
    """Look up and cache one GIF per track and motif. Expire empty results after a day."""
    if not (gif[0] and gif[1]):
        return ""
    cache_key = f"{key}:{gif[0]}:{motif}"
    st = load_store()
    if key in st["user"] or key in st["nogif"]:
        return ""
    known = st["auto"].get(cache_key) or {}
    path = known.get("path", "")
    if (path and Path(path).is_file()) or (not path and time.time() - known.get("at", 0) < 86400):
        return ""
    found = find_gif(artist, title, *gif, motif)
    with _LOCK:
        st = load_store()
        if key in st["user"] or key in st["nogif"]:
            return ""
        st["auto"][cache_key] = {"path": found, "at": time.time()}
        if len(st["auto"]) > 2000:
            for k in list(st["auto"])[:500]:
                st["auto"].pop(k, None)
        save_store(st)
    return found
