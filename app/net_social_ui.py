"""Профили Echoes.NET как в Spotify: «N открытых плейлистов · N подписчиков · N подписок», разделы
«Открытые плейлисты», «Подписчики», «Уже подписаны» (списки — по клику), просмотр чужого открытого плейлиста
и вкладка «Время прослушивания» в чужом профиле.

Что уходит в профиль от себя: my_lt(win) — время прослушивания, my_pls(win) — плейлисты, отмеченные открытыми.
"""
from __future__ import annotations

import data_home
import base64
import os
import hashlib
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QBuffer, QByteArray, QIODevice
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget)

from net_music import TrackChip, safe_track
from yamusic_theme import Card, HRow, Page, YELLOW, section_title, cover_pixmap

_PL_DIR = data_home.root() / "net_cache" / "pl_covers"


def _plural(n, one, few, many):
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


# ── своё: что показываем другим ── #

def my_lt(win) -> dict | None:
    st = getattr(win, "stats", None)
    if st is None or not (win.settings or {}).get("share_listen_time", True):
        return None
    d = st.data
    tracks = sorted(((v.get("title") or "", v.get("artist") or "", int(v.get("plays", 0)), int(v.get("sec", 0)))
                     for v in (d.get("tracks") or {}).values() if v.get("plays") or v.get("sec", 0) > 5),
                    key=lambda x: (x[2], x[3]), reverse=True)[:20]
    r = lambda x: int(x) // 300 * 300                          # с точностью 5 мин — профиль не рассылается ежеминутно
    return {"total": r(d.get("total") or 0), "today": r(st.seconds_since(1)), "week": r(st.seconds_since(7)),
            "plays": sum(int(v.get("plays", 0)) for v in (d.get("tracks") or {}).values()),
            "arts": [[a, r(v.get("sec", 0)), int(v.get("plays", 0))] for a, v in st.top_artists(10)],
            "trs": [[t, a, pl, r(sec)] for t, a, pl, sec in tracks],
            "wtrs": __import__("net_weektop").my_week_tracks(win)}         # топ за 7 дней — для «Топа недели друзей»


_THUMBS: dict = {}


def _thumb_b64(path, side=96) -> str:
    """Миниатюра обложки строкой для профиля. Запоминается по файлу: профиль собирает плейлисты трижды за одно
    открытие, и каждый раз обложка читалась и сжималась заново — это было видно как пауза окна."""
    if not path:
        return ""
    try:
        st = os.stat(path)
        key = (str(path), st.st_mtime_ns, st.st_size, side)
    except OSError:
        return ""
    hit = _THUMBS.get(key)
    if hit is not None:
        return hit
    out = _thumb_make(path, side)
    if len(_THUMBS) > 64:
        _THUMBS.clear()
    _THUMBS[key] = out
    return out


def _thumb_make(path, side) -> str:
    img = QImage(str(path))
    if img.isNull():
        return ""
    s = min(img.width(), img.height())
    img = img.copy((img.width() - s) // 2, (img.height() - s) // 2, s, s).scaled(
        side, side, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "JPG", 72)
    return base64.b64encode(bytes(ba)).decode()


def my_pls(win) -> list:
    from net_page import track_meta
    out = []
    for name, pl in (win.playlists or {}).items():
        if not isinstance(pl, dict) or not pl.get("public"):
            continue
        tr = pl.get("tracks") or []
        cov = pl.get("cover") or (tr[0].get("cover", "") if tr else "")
        metas = [m for m in (track_meta(t) for t in tr[:60]) if m]
        out.append({"name": name, "desc": "" if str(pl.get("desc") or "").startswith("auto") else str(pl.get("desc") or ""),
                    "n": len(tr), "tracks": metas, "cover": _thumb_b64(cov)})
        if len(out) >= 6:
            break
    return out


def pl_cover_path(pl) -> str:
    """Обложка чужого плейлиста (JPEG в профиле) → файл в кэше (для карточек)."""
    b = pl.get("cover") or ""
    if not b:
        return ""
    f = _PL_DIR / (hashlib.sha1(b.encode()).hexdigest()[:20] + ".jpg")
    if not f.exists():
        try:
            _PL_DIR.mkdir(parents=True, exist_ok=True)
            f.write_bytes(base64.b64decode(b))
        except (OSError, ValueError):
            return ""
    return str(f)


# ── подписчики / подписки ── #

def _person_av(page, p) -> str:
    nd = page.node
    if p.get("onion"):
        if p["onion"] == nd.me.onion:
            return str(page.win.profile.get("avatar") or "")
        a = nd.avatar_path(p["onion"])
        if a:
            return a
    return ((page._pub()["profiles"].get(p.get("npub")) or {}).get("avatar_file") or "")


def _open_person(page, p):
    if p.get("onion"):
        page.open_profile(p["onion"])
    elif p.get("npub"):
        page.open_public(p["npub"])


def ask(page, onion, npub):
    """Спросить у релеев подписки/подписчиков (не чаще раза в минуту на человека)."""
    nd = page.node
    if nd is None or len(npub or "") != 64:
        return
    asked = page.__dict__.setdefault("_soc_asked", {})
    if time.time() - asked.get(npub, 0) < 60:
        return
    asked[npub] = time.time()
    nd.call(nd.social_query, npub)


def info(page, onion, me) -> dict:
    nd = page.node
    npub = nd._nostr_keys()[1] if me else (getattr(page, "_profile_npub", None) or nd._npk_for(onion))
    ask(page, onion, npub)
    return nd.social_info(onion, npub)


def stats_row(page, onion, me) -> QWidget:
    """«2 открытых плейлиста · 5 подписчиков · 23 подписки» — каждое число кликается."""
    si = info(page, onion, me)
    pls = page.node.public_playlists(onion) if not me else my_pls(page.win)
    w = QWidget()
    w.setObjectName("YaPageInner")
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 10, 0, 0)
    h.setSpacing(6)

    def link(text, fn):
        b = QPushButton(text)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet("QPushButton{background:transparent;border:none;color:#e8e8e8;font-weight:700;"
                        "font-size:13px;padding:2px 0;}QPushButton:hover{color:#ffffff;text-decoration:underline;}")
        b.clicked.connect(fn)
        return b

    def dot():
        d = QLabel("·")
        d.setStyleSheet("color:#8a8a8a;background:transparent;")
        return d
    n_pl, n_fol, n_ing = len(pls), len(si["followers"]), si["n_following"]
    h.addWidget(link(f"{n_pl} {_plural(n_pl, 'открытый плейлист', 'открытых плейлиста', 'открытых плейлистов')}",
                     lambda: PlaylistsDialog(page, pls, onion, me).exec()))
    h.addWidget(dot())
    h.addWidget(link(f"{n_fol} {_plural(n_fol, 'подписчик', 'подписчика', 'подписчиков')}",
                     lambda: PeopleDialog(page, "Подписчики", si["followers"]).exec()))
    h.addWidget(dot())
    h.addWidget(link(f"{n_ing} {_plural(n_ing, 'подписка', 'подписки', 'подписок')}",
                     lambda: PeopleDialog(page, "Подписки", si["following"], hidden=si["following"] is None,
                                          own=me).exec()))
    h.addStretch(1)
    return w


def _people_row(page, people) -> HRow:
    row = HRow()
    for p in people[:14]:
        c = Card(p.get("name") or p.get("npub", "")[:8], "Профиль", _person_av(page, p), 120, circle=True,
                 seed=p.get("npub") or p.get("onion") or "")
        c.clicked.connect(lambda p=p: _open_person(page, p))
        row.add(c)
    return row


def sections(page, bv, onion, me):
    """Разделы как в Spotify: открытые плейлисты, подписчики, на кого подписан."""
    si = info(page, onion, me)
    pls = my_pls(page.win) if me else page.node.public_playlists(onion)
    if pls:
        bv.addWidget(section_title("Открытые плейлисты", lambda: PlaylistsDialog(page, pls, onion, me).exec()))
        row = HRow()
        for pl in pls:
            c = Card(pl["name"], f"{pl.get('n') or len(pl['tracks'])} треков",
                     pl_cover_path(pl) if not me else (page.win.playlists.get(pl["name"], {}).get("cover") or
                                                       pl_cover_path(pl)), 150, seed=pl["name"])
            c.clicked.connect(lambda pl=pl: (page.shell.open_playlist(pl["name"]) if me else
                                             PlaylistDialog(page, pl, onion).exec()))
            row.add(c)
        bv.addWidget(row)
    if si["followers"]:
        bv.addWidget(section_title(f"Подписчики · {len(si['followers'])}",
                                   lambda: PeopleDialog(page, "Подписчики", si["followers"]).exec()))
        bv.addWidget(_people_row(page, si["followers"]))
    if si["following"]:
        bv.addWidget(section_title("Уже подписаны" if not me else f"Подписки на людей · {len(si['following'])}",
                                   lambda: PeopleDialog(page, "Подписки", si["following"], own=me).exec()))
        bv.addWidget(_people_row(page, si["following"]))
    elif si["following"] is None and si["n_following"]:
        bv.addWidget(section_title(f"Подписки · {si['n_following']}"))
        bv.addWidget(_muted("Человек скрыл, на кого подписан."))


def _muted(text):
    lb = QLabel(text)
    lb.setObjectName("YaSub")
    lb.setWordWrap(True)
    return lb


def _dlg(page, title):
    d = QDialog(page)
    d.setWindowTitle(title)
    d.setMinimumSize(520, 560)
    d.setStyleSheet(page._dlg_qss() + "QDialog{background:#101113;}")
    outer = QVBoxLayout(d)
    outer.setContentsMargins(0, 0, 0, 0)
    pg = Page(margins=(22, 18, 22, 18))
    outer.addWidget(pg)
    t = QLabel(title)
    t.setStyleSheet("font-size:22px;font-weight:900;background:transparent;")
    pg.v.addWidget(t)
    return d, pg.v


class PeopleDialog:
    """Список людей (подписчики / подписки); свой список подписок можно скрыть."""

    def __init__(self, page, title, people, hidden=False, own=False):
        self.d, v = _dlg(page, title)
        if own and title == "Подписки":
            cb = QCheckBox("Скрывать от других, на кого я подписан (число останется видно)")
            cb.setChecked(bool(page.node.settings.get("follows_hidden")))
            cb.toggled.connect(lambda on: (page.node.set_follows_hidden(on),
                                           page.toast("Список подписок скрыт" if on else "Список подписок открыт")))
            v.addWidget(cb)
        if hidden:
            v.addWidget(_muted("Человек скрыл, на кого подписан."))
        elif not people:
            v.addWidget(_muted("Пока никого."))
        for p in people or []:
            r = QPushButton()
            r.setCursor(Qt.CursorShape.PointingHandCursor)
            r.setStyleSheet("QPushButton{background:rgba(255,255,255,0.05);border-radius:14px;text-align:left;"
                            "padding:8px 12px;font-weight:700;font-size:14px;}"
                            "QPushButton:hover{background:rgba(255,255,255,0.10);}")
            from PyQt6.QtGui import QIcon
            r.setIcon(QIcon(cover_pixmap(_person_av(page, p), 40, 20, seed=p.get("npub") or "", circle=True)))
            from PyQt6.QtCore import QSize
            r.setIconSize(QSize(40, 40))
            r.setText("   " + (p.get("name") or (p.get("npub") or "")[:10] + "…"))
            r.clicked.connect(lambda _=False, p=p: (self.d.accept(), _open_person(page, p)))
            v.addWidget(r)
        v.addStretch(1)

    def exec(self):
        return self.d.exec()


class PlaylistsDialog:
    def __init__(self, page, pls, onion, me):
        self.d, v = _dlg(page, "Открытые плейлисты")
        if me:
            v.addWidget(_muted("Плейлист станет открытым через «⋯» на его странице → «Сделать открытым»."))
        if not pls:
            v.addWidget(_muted("Открытых плейлистов нет."))
        for pl in pls:
            b = QPushButton(f"   {pl['name']}  ·  {pl.get('n') or len(pl['tracks'])} треков")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("QPushButton{background:rgba(255,255,255,0.05);border-radius:14px;text-align:left;"
                            "padding:8px 12px;font-weight:700;font-size:14px;}"
                            "QPushButton:hover{background:rgba(255,255,255,0.10);}")
            from PyQt6.QtGui import QIcon
            from PyQt6.QtCore import QSize
            b.setIcon(QIcon(cover_pixmap(pl_cover_path(pl), 44, 8, seed=pl["name"])))
            b.setIconSize(QSize(44, 44))
            b.clicked.connect(lambda _=False, pl=pl: (self.d.accept(), page.shell.open_playlist(pl["name"]) if me
                                                      else PlaylistDialog(page, pl, onion).exec()))
            v.addWidget(b)
        v.addStretch(1)

    def exec(self):
        return self.d.exec()


class PlaylistDialog:
    """Чужой открытый плейлист: обложка, описание, треки (слушать, превью), «Слушать всё»."""

    def __init__(self, page, pl, onion):
        self.d, v = _dlg(page, pl["name"])
        self.d.setMinimumSize(640, 640)
        h = QHBoxLayout()
        ic = QLabel()
        ic.setFixedSize(120, 120)
        ic.setPixmap(cover_pixmap(pl_cover_path(pl), 120, 12, seed=pl["name"]))
        h.addWidget(ic)
        col = QVBoxLayout()
        n = pl.get("n") or len(pl["tracks"])
        col.addWidget(_muted(f"Открытый плейлист · {n} {_plural(n, 'трек', 'трека', 'треков')}"
                             + (f" · {page._name(onion)}" if onion else "")))
        if pl.get("desc"):
            col.addWidget(_muted(pl["desc"]))
        tracks = [t for t in (safe_track(x) for x in pl["tracks"]) if t]
        b = QPushButton("  Слушать всё")
        b.setStyleSheet(f"QPushButton{{background:{YELLOW};color:#000;border-radius:16px;padding:8px 16px;"
                        "font-weight:800;}")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda: (page.play_many(tracks, pl["name"]), self.d.accept()))
        col.addWidget(b, 0, Qt.AlignmentFlag.AlignLeft)
        col.addStretch(1)
        h.addLayout(col, 1)
        v.addLayout(h)
        for t in tracks:
            v.addWidget(TrackChip(t, page.play_meta, compact=True, page=page, cover=page._local_cover(t)))
        if n > len(tracks):
            v.addWidget(_muted(f"Показаны первые {len(tracks)} из {n}."))
        v.addStretch(1)

    def exec(self):
        return self.d.exec()


# ── «Время прослушивания» в чужом профиле ── #

def time_tab(page, bv, lt, name):
    from listen_stats import fmt_dur
    from ya_profile import StatRow, _tile
    if not lt:
        bv.addSpacing(18)
        bv.addWidget(_muted(f"{name} пока не делится временем прослушивания (нужна новая версия ECHOES)."))
        return
    tiles = QWidget()
    tiles.setObjectName("YaPageInner")
    tl = QHBoxLayout(tiles)
    tl.setContentsMargins(0, 18, 0, 0)
    tl.setSpacing(12)
    for cap, val in (("Всего прослушано", fmt_dur(lt["total"])), ("Сегодня", fmt_dur(lt["today"])),
                     ("За 7 дней", fmt_dur(lt["week"])), ("Запусков треков", str(lt["plays"]))):
        tl.addWidget(_tile(cap, val))
    bv.addWidget(tiles)
    bv.addWidget(section_title("Топ исполнителей"))
    if not lt["arts"]:
        bv.addWidget(_muted("Пока нет данных."))
    for i, (a, sec, plays) in enumerate(lt["arts"], 1):
        try:
            from artist_net import cached
            pic = (cached(a) or {}).get("picture", "") or ""
        except Exception:                                      # noqa: BLE001
            pic = ""
        bv.addWidget(StatRow(i, a, f"{plays} раз", pic, fmt_dur(sec), lambda a=a: page.shell.open_artist(a),
                             circle=True))
    bv.addWidget(section_title("Топ треков"))
    if not lt["trs"]:
        bv.addWidget(_muted("Пока нет данных."))
    for i, (title, artist, plays, sec) in enumerate(lt["trs"], 1):
        meta = {"title": title, "artist": artist}
        row = StatRow(i, title or "Без названия", artist, page._local_cover(meta), f"{plays} раз · {fmt_dur(sec)}",
                      lambda m=meta: page.play_meta(m), seed=f"{artist}{title}")
        bv.addWidget(row)
        if not page._local_cover(meta):
            import cover_lookup
            pic = row.findChildren(QLabel)[1]
            cover_lookup.want(meta, lambda p, pic=pic: pic.setPixmap(cover_pixmap(p, 42, 6)))
