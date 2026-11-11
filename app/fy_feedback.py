"""«Больше такого / меньше такого» в «Для вас и тренды».

На каждой карточке трека (тренды, «Треки для вас», «Ещё от ваших исполнителей», жанры) при наведении —
два значка: 👍 и 👎 (и то же самое по правой кнопке мыши). Оценка запоминается в settings["foryou_fb"]:

  tracks  — {«исполнитель|название»: +1 / -1}: дизлайкнутый трек больше не показывается;
  artists — {ключ исполнителя: {"n": имя, "s": счёт}}: 👍 треку = +1 исполнителю, 👎 = −1;
            счёт ≥ 1 — исполнитель становится «вашим» (по нему ищутся похожие и его треки — первыми в лентах),
            счёт ≤ −2 — его треки и похожие на него больше не предлагаются;
  genres  — {жанр: счёт}: оценка трека из жанровой ленты сдвигает долю жанра (больше / меньше жанровых лент);
  rev     — номер правки: по нему ya_foryou понимает, что вкус поменялся, и пересчитывает рекомендации.

Чарты (Россия / мир) не пересортировываются — из них только убирается то, что вы не хотите видеть.
"""
from __future__ import annotations

import math
import re

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, QTimer
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QMenu, QPushButton, QWidget

KEY = "foryou_fb"
BLOCK = -2.0                                               # исполнитель с таким счётом — не предлагать


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w ]+", " ", (s or "").lower())).strip()


def _main(a: str) -> str:
    return re.split(r"\s*(?:,|&|\bfeat\.?|\bft\.?|\bx\b|;|/)\s*", a or "", maxsplit=1, flags=re.I)[0].strip()


def track_key(t: dict) -> str:
    return f"{_norm(_main(t.get('artist', '')))}|{_norm(t.get('title', ''))}"


def artist_key(name: str) -> str:
    try:
        from artist_identity import ident
        return ident(_main(name))
    except Exception:                                      # noqa: BLE001
        return _norm(_main(name))


def data(settings) -> dict:
    d = settings.get(KEY) if isinstance(settings, dict) else None
    if not isinstance(d, dict):
        d = {}
    for k in ("tracks", "artists", "genres"):
        if not isinstance(d.get(k), dict):
            d[k] = {}
    d.setdefault("rev", 0)
    return d


def vote_of(settings, t: dict) -> int:
    return int(data(settings)["tracks"].get(track_key(t), 0) or 0)


def artist_score(settings, name: str) -> float:
    e = data(settings)["artists"].get(artist_key(name))
    return float(e.get("s", 0) if isinstance(e, dict) else 0)


def genre_factor(settings, name: str) -> float:
    s = float(data(settings)["genres"].get(name, 0) or 0)
    return max(0.25, min(3.0, math.exp(0.45 * s)))


def vote(settings, t: dict, v: int, genre: str = "") -> int:
    """Поставить оценку треку (+1, −1, 0 — снять). Возвращает новую оценку."""
    d = data(settings)
    k = track_key(t)
    prev = int(d["tracks"].get(k, 0) or 0)
    v = max(-1, min(1, int(v)))
    if v == prev:
        return v
    if v:
        d["tracks"][k] = v
    else:
        d["tracks"].pop(k, None)
    delta = v - prev
    name = _main(t.get("artist", ""))
    if name:
        ak = artist_key(name)
        e = d["artists"].get(ak) if isinstance(d["artists"].get(ak), dict) else {"n": name, "s": 0.0}
        e["s"] = max(-5.0, min(5.0, float(e.get("s", 0)) + delta))
        e["n"] = e.get("n") or name
        if abs(e["s"]) < 1e-6:
            d["artists"].pop(ak, None)
        else:
            d["artists"][ak] = e
    because = t.get("because") or ""
    if because.startswith("похож на "):                    # трек «похож на X» понравился — X тоже в плюс
        seed = because[len("похож на "):].strip()
        if seed:
            sk = artist_key(seed)
            e = d["artists"].get(sk) if isinstance(d["artists"].get(sk), dict) else {"n": seed, "s": 0.0}
            e["s"] = max(-5.0, min(5.0, float(e.get("s", 0)) + 0.34 * delta))
            if abs(e["s"]) < 1e-6:
                d["artists"].pop(sk, None)
            else:
                d["artists"][sk] = e
    if genre:
        g = max(-4.0, min(4.0, float(d["genres"].get(genre, 0) or 0) + 0.5 * delta))
        if abs(g) < 1e-6:
            d["genres"].pop(genre, None)
        else:
            d["genres"][genre] = g
    if len(d["tracks"]) > 3000:                            # не растём бесконечно: старые оценки — вон
        for old in list(d["tracks"])[:500]:
            d["tracks"].pop(old, None)
    d["rev"] = int(d.get("rev", 0)) + 1
    settings[KEY] = d
    return v


def reset(settings):
    settings.pop(KEY, None)


def counts(settings) -> tuple[int, int]:
    tr = data(settings)["tracks"].values()
    return sum(1 for v in tr if v > 0), sum(1 for v in tr if v < 0)


def shape(settings, tracks: list, rank: bool = True) -> list:
    """Убрать дизлайкнутое и исполнителей «меньше такого»; rank — лайкнутых исполнителей вперёд."""
    d = data(settings)
    if not (d["tracks"] or d["artists"]):
        return list(tracks)
    out = []
    for i, t in enumerate(tracks):
        if d["tracks"].get(track_key(t), 0) < 0:
            continue
        e = d["artists"].get(artist_key(t.get("artist", "")))
        s = float(e.get("s", 0)) if isinstance(e, dict) else 0.0
        if s <= BLOCK:
            continue
        out.append((i, s, t))
    if rank:
        out.sort(key=lambda x: (-(max(0.0, x[1]) + (1.5 if d["tracks"].get(track_key(x[2]), 0) > 0 else 0)), x[0]))
    return [t for _, _, t in out]


# ══════════════════════════════════════════════════════════════════════════ #
#  Интерфейс: значки на карточке
# ══════════════════════════════════════════════════════════════════════════ #

class _Buttons(QWidget):
    """Два круглых значка поверх обложки наведённой карточки."""

    def __init__(self, host: QWidget, on_vote):
        super().__init__(host)
        self.on_vote = on_vote
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.up = self._btn("Больше такого")
        self.down = self._btn("Меньше такого")
        self.up.clicked.connect(lambda: self.on_vote(1))
        self.down.clicked.connect(lambda: self.on_vote(-1))
        self.up.move(0, 0)
        self.down.move(34, 0)
        self.setFixedSize(64, 30)
        self.hide()

    def _btn(self, tip):
        b = QPushButton(self)
        b.setFixedSize(30, 30)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.setIconSize(QSize(17, 17))
        return b

    def paint_state(self, v: int):
        from yamusic_theme import ya_icon
        import ya_decor
        acc = ya_decor.accent().name()
        base = ("QPushButton{background:rgba(10,10,12,0.78);border:1px solid rgba(255,255,255,0.16);"
                "border-radius:15px;} QPushButton:hover{background:rgba(40,40,46,0.92);}")
        on = (f"QPushButton{{background:{acc};border:none;border-radius:15px;}}")
        self.up.setStyleSheet(on if v > 0 else base)
        self.down.setStyleSheet(on if v < 0 else base)
        dark = ya_decor.on_accent(ya_decor.accent()).name()
        self.up.setIcon(ya_icon("thumb_up_fill" if v > 0 else "thumb_up", 17, dark if v > 0 else "#ffffff"))
        self.down.setIcon(ya_icon("thumb_down_fill" if v < 0 else "thumb_down", 17, dark if v < 0 else "#ffffff"))


class RowFeedback(QObject):
    """Значки 👍/👎 для одной ленты карточек (NativeCardRow на C++ или HRow с Card-виджетами)."""

    def __init__(self, shell, row, genre: str = ""):
        host = row.widget_
        super().__init__(host)
        self.shell, self.row, self.genre = shell, row, genre
        self.host = host
        self.cards: list = []                              # [(карточка, трек)]
        self.cur = -1
        self.btns = _Buttons(host, self._vote_cur)
        self.timer = QTimer(self)
        self.timer.setInterval(160)
        self.timer.timeout.connect(self._check)
        host.installEventFilter(self)
        for w in host.findChildren(QWidget):
            if w is not self.btns and not self.btns.isAncestorOf(w):
                w.installEventFilter(self)

    @property
    def settings(self):
        return self.shell.win.settings

    def add(self, card, track):
        i = len(self.cards)
        self.cards.append((card, track))
        hov = getattr(card, "hovered", None)
        if hov is not None:
            hov.connect(lambda i=i: self._show(i))
        elif isinstance(card, QWidget):
            card.installEventFilter(self)
        if vote_of(self.settings, track) > 0:
            self._mark(i, 1)

    # геометрия карточки в координатах ленты
    def _rect(self, i) -> QRect:
        card, _ = self.cards[i]
        if isinstance(card, QWidget):
            p = card.mapTo(self.host, QPoint(0, 0))
            return QRect(p.x(), p.y(), card.width(), card.width())
        x, y = self.row.strip.card_pos(card.index)
        return QRect(x, y, card.size_, card.size_)

    def _index_at(self, pos: QPoint) -> int:
        for i in range(len(self.cards)):
            r = self._rect(i)
            if QRect(r.x(), r.y(), r.width(), r.height() + 46).contains(pos):
                return i
        return -1

    def _show(self, i):
        if i < 0 or i >= len(self.cards):
            return
        try:
            r = self._rect(i)
        except RuntimeError:
            return
        if r.width() < 90:
            return
        self.cur = i
        self.btns.paint_state(vote_of(self.settings, self.cards[i][1]))
        self.btns.move(r.right() - self.btns.width() - 6, r.top() + 6)
        self.btns.show()
        self.btns.raise_()
        self.timer.start()

    def _check(self):
        try:
            if self.cur < 0 or not self.host.isVisible():
                raise RuntimeError
            pos = self.host.mapFromGlobal(QCursor.pos())
            r = self._rect(self.cur)
            if not (r.adjusted(-4, -4, 4, 50).contains(pos) or self.btns.geometry().adjusted(-4, -4, 4, 4).contains(pos)):
                raise RuntimeError
        except RuntimeError:
            self.timer.stop()
            self.cur = -1
            try:
                self.btns.hide()
            except RuntimeError:
                pass

    def eventFilter(self, obj, e):
        t = e.type()
        if t == QEvent.Type.Enter and isinstance(obj, QWidget) and obj not in (self.host, self.btns):
            for i, (c, _) in enumerate(self.cards):
                if c is obj:
                    self._show(i)
                    break
        elif t == QEvent.Type.ContextMenu:
            try:
                gp = e.globalPos()
                i = self._index_at(self.host.mapFromGlobal(gp))
            except Exception:                              # noqa: BLE001
                i = -1
            if i >= 0:
                self._menu(i, gp)
                return True
        return False

    def _menu(self, i, gp):
        t = self.cards[i][1]
        v = vote_of(self.settings, t)
        m = QMenu(self.host)
        a_up = m.addAction(("✓ " if v > 0 else "") + "👍  Больше такого")
        a_dn = m.addAction(("✓ " if v < 0 else "") + "👎  Меньше такого")
        a_rm = m.addAction("Снять оценку") if v else None
        art = _main(t.get("artist", ""))
        a_art = m.addAction(f"Не предлагать исполнителя «{art}»") if art else None
        got = m.exec(gp)
        if got is None:
            return
        if got is a_up:
            self._apply(i, 0 if v > 0 else 1)
        elif got is a_dn:
            self._apply(i, 0 if v < 0 else -1)
        elif got is a_rm:
            self._apply(i, 0)
        elif got is a_art:
            d = data(self.settings)
            ak = artist_key(art)
            d["artists"][ak] = {"n": art, "s": min(BLOCK, float((d["artists"].get(ak) or {}).get("s", 0)))}
            d["rev"] = int(d.get("rev", 0)) + 1
            self.settings[KEY] = d
            self._apply(i, -1)

    def _vote_cur(self, v):
        if self.cur < 0:
            return
        old = vote_of(self.settings, self.cards[self.cur][1])
        self._apply(self.cur, 0 if old == v else v)

    def _apply(self, i, v):
        t = self.cards[i][1]
        v = vote(self.settings, t, v, self.genre)
        self._mark(i, v)
        if self.cur == i:
            self.btns.paint_state(v)
        try:
            self.shell.win.save_settings()
        except Exception:                                  # noqa: BLE001
            pass
        self.shell._dirty.add("foryou")                    # при следующем открытии — уже с учётом оценки
        msg = {1: f"Понял: будет больше похожего на «{_main(t.get('artist', ''))}»",
               -1: "Понял: такого будет меньше — трек убран из ленты",
               0: "Оценка снята"}[v]
        toast = getattr(self.shell.win, "_toast", None)
        if toast:
            try:
                toast(msg)
            except Exception:                              # noqa: BLE001
                pass

    def _mark(self, i, v):
        """Подпись карточки: 👍 — понравилось, 👎 — приглушена (уберётся при следующем открытии)."""
        card, t = self.cards[i]
        base = card.__dict__.setdefault("_fb_sub", card.subtitle)
        sub = ("👍 " + base) if v > 0 else ("👎 меньше такого" if v < 0 else base)
        card.subtitle = sub
        try:
            if hasattr(self.row, "strip"):
                from yamusic_theme import i18n_tr
                self.row.strip.text(card.index, i18n_tr(card.title), i18n_tr(sub))
            else:
                card.__dict__.pop("_c_real", None)
                card.update()
        except RuntimeError:
            pass


def bind(shell, row, pairs, genre: str = "") -> RowFeedback | None:
    try:
        fb = RowFeedback(shell, row, genre)
        for card, t in pairs:
            fb.add(card, t)
        row._fb = fb
        return fb
    except Exception as e:                                 # noqa: BLE001
        print("[foryou] feedback:", e)
        return None
