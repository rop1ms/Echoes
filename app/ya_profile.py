# ya_profile.py
"""
Единый профиль ECHOES и Echoes.NET: социальные разделы, недавние
исполнители и треки; вкладка «Время прослушивания» — общее время, топ треков
и исполнителей. Данные берутся из listen_stats.ListenStats.
"""
from __future__ import annotations

import data_home
import json
import threading
from pathlib import Path

from PyQt6.QtCore import Qt, QRectF, QPointF, QVariantAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QFontMetrics, QFont
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame

from listen_stats import fmt_dur, _first_artist
from yamusic_theme import (Page, Card, HRow, TrackListView, section_title, cover_pixmap,
                           cover_colors, ya_font, ya_icon, YELLOW)


class SegTabs(QWidget):
    """Современный переключатель вкладок: тёмная «капсула» и скользящая жёлтая плашка."""
    changed = pyqtSignal(str)
    H, PAD, GAP, ICON = 46, 5, 4, 18

    def __init__(self, items, current, parent=None):
        super().__init__(parent)
        self.items = items                         # [(ключ, подпись, иконка)]
        self.cur = current
        self._hover = -1
        self._font = ya_font(13, QFont.Weight.Bold)
        fm = QFontMetrics(self._font)
        self._w = [self.ICON + 10 + fm.horizontalAdvance(t) + 44 for _, t, _ in items]
        self.setFixedSize(sum(self._w) + self.GAP * (len(items) - 1) + self.PAD * 2, self.H)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._x = self._target_x()
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(240)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(lambda v: (setattr(self, "_x", v), self.update()))

    def _index(self):
        return next((i for i, it in enumerate(self.items) if it[0] == self.cur), 0)

    def _seg_x(self, i):
        return self.PAD + sum(self._w[:i]) + self.GAP * i

    def _target_x(self):
        return float(self._seg_x(self._index()))

    def set_current(self, key, animate=True):
        if key == self.cur:
            return
        self.cur = key
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self._x)
            self._anim.setEndValue(self._target_x())
            self._anim.start()
        else:
            self._x = self._target_x()
            self.update()

    def _at(self, pos):
        for i in range(len(self.items)):
            x = self._seg_x(i)
            if x <= pos.x() <= x + self._w[i]:
                return i
        return -1

    def mouseMoveEvent(self, e):
        i = self._at(e.position())
        if i != self._hover:
            self._hover = i
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            i = self._at(e.position())
            if i >= 0 and self.items[i][0] != self.cur:
                key = self.items[i][0]
                self.set_current(key)
                self.changed.emit(key)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        H = self.height()
        track = QPainterPath()
        track.addRoundedRect(QRectF(0, 0, self.width(), H), H / 2, H / 2)
        p.fillPath(track, QColor(255, 255, 255, 18))
        # скользящая плашка
        cw = self._w[self._index()]
        pill = QPainterPath()
        pill.addRoundedRect(QRectF(self._x, self.PAD, cw, H - self.PAD * 2), (H - self.PAD * 2) / 2,
                            (H - self.PAD * 2) / 2)
        g = QLinearGradient(QPointF(self._x, 0), QPointF(self._x + cw, 0))
        g.setColorAt(0.0, QColor(YELLOW))
        g.setColorAt(1.0, QColor(YELLOW).darker(112))
        p.fillPath(pill, g)
        p.setFont(self._font)
        fm = QFontMetrics(self._font)
        for i, (key, text, icon) in enumerate(self.items):
            active = key == self.cur
            x = self._seg_x(i)
            col = "#000000" if active else ("#ffffff" if i == self._hover else "#b5b5b5")
            tw = fm.horizontalAdvance(text)
            gx = x + (self._w[i] - (self.ICON + 10 + tw)) / 2
            ya_icon(icon, self.ICON, col).paint(p, int(gx), int((H - self.ICON) / 2), self.ICON, self.ICON)
            p.setPen(QColor(col))
            p.drawText(QRectF(gx + self.ICON + 10, 0, tw + 4, H), Qt.AlignmentFlag.AlignVCenter, text)
        p.end()


def _phantom() -> bool:
    try:
        import ya_skin
        return bool(ya_skin.PHANTOM_ON)
    except Exception:                                          # noqa: BLE001
        return False


PH_BTN = ("QPushButton{color:#f5f5f5;background:rgba(12,12,12,0.55);border:1px solid rgba(255,255,255,0.16);"
          "border-radius:15px;padding:7px 16px;font-weight:600;}"
          "QPushButton:hover{background:rgba(12,12,12,0.68);border-color:rgba(255,255,255,0.24);}")


class ProfileHeader(QWidget):
    H = 230

    def __init__(self, page, parent=None):
        super().__init__(parent)
        self.page = page
        self.setFixedHeight(self.H)
        self._surface = None
        self.deco = None                     # оформление профиля (net_showcase): фон шапки, аура
        self._frame = None
        self._avatar_args = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(40, 30, 40, 18)
        lay.setSpacing(26)
        self.avatar = QLabel()
        self.avatar.setFixedSize(170, 170)
        lay.addWidget(self.avatar)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addStretch(1)
        self.kicker = QLabel("Профиль")
        self.kicker.setStyleSheet("font-size:12px;font-weight:700;background:transparent;")
        self.nick = QLabel("")
        self.nick.setStyleSheet("font-size:54px;font-weight:900;background:transparent;")
        self.sub = QLabel("")
        self.sub.setStyleSheet("font-size:13px;font-weight:600;color:#cfcfcf;background:transparent;")
        col.addWidget(self.kicker)
        col.addWidget(self.nick)
        col.addWidget(self.sub)
        col.addStretch(1)
        lay.addLayout(col, 1)
        self.btn = QPushButton("Изменить профиль")
        self.btn.setObjectName("YaChip")
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        lay.addWidget(self.btn, 0, Qt.AlignmentFlag.AlignBottom)
        if _phantom():                                         # Phantom: Inter 650, кикер капсом, тёмное стекло кнопки
            import ph_style as ph
            self.kicker.setText("PROFILE")
            self.kicker.setStyleSheet("font-size:10px;font-weight:600;letter-spacing:2px;"
                                      "color:rgba(255,255,255,0.62);background:transparent;")
            self.nick.setStyleSheet("font-size:46px;font-weight:700;background:transparent;")
            self.sub.setStyleSheet("font-size:12px;font-weight:500;color:rgba(255,255,255,0.72);"
                                   "background:transparent;")
            self.btn.setObjectName("PhProfileBtn")
            self.btn.setStyleSheet(PH_BTN)
            lay.setContentsMargins(ph.px(36), ph.px(28), ph.px(36), ph.px(22))

    def set_profile(self, nick, status, avatar, sub, anim=""):
        self.anim_path = anim or ""                           # GIF — живая аватарка (ya_avanim)
        self._avatar_args = (avatar, nick)
        self._set_avatar()
        self.nick.setText(nick)
        self.sub.setText(sub if not status else f"{status}  ·  {sub}")
        self.update()

    def _set_avatar(self):
        avatar, nick = self._avatar_args or ("", "")
        pm = cover_pixmap(avatar, 170, 85, seed=nick, circle=True)
        import net_frames
        net_frames.animate_label(self.avatar, pm, self._frame or {}, 170, getattr(self, "anim_path", ""))

    def set_frame(self, spec):
        self._frame = spec or None
        self._set_avatar()

    def paintEvent(self, _):
        from echo_glass import liquid_surface
        from PyQt6.QtCore import QSize, QRectF
        if _phantom():                                         # стеклянная карточка Phantom; оформление — поверх
            import ph_style as ph
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            r = QRectF(12, 12, max(1, self.width() - 24), max(1, self.height() - 12))
            ph.paint_surface(p, r, "card", float(ph.px(22)))
            if self.deco:
                import net_showcase
                p.save()
                p.setClipPath(ph.surface_path(r, float(ph.px(22))))
                net_showcase.header_paint(self, p, r)
                p.restore()
            p.end()
            return
        size = QSize(max(1, self.width() - 24), max(1, self.height() - 12))
        if self._surface is None or self._surface.size() != size:
            self._surface = liquid_surface(size)
        p = QPainter(self)
        p.drawPixmap(12, 12, self._surface)
        if self.deco:
            import net_showcase
            net_showcase.header_paint(self, p, QRectF(12, 12, size.width(), size.height()))
        p.end()


class StatRow(QWidget):
    """Строка топа: место, обложка, название/исполнитель, справа — прослушивания и время."""

    def __init__(self, n, title, sub, cover, right, on_click=None, circle=False, seed="", parent=None):
        super().__init__(parent)
        self.on_click = on_click
        self.setFixedHeight(56)
        if on_click:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 12, 4)
        lay.setSpacing(12)
        num = QLabel(str(n))
        num.setFixedWidth(26)
        num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num.setStyleSheet("color:#8a8a8a;font-weight:700;background:transparent;")
        pic = QLabel()
        pic.setFixedSize(42, 42)
        pic.setPixmap(cover_pixmap(cover, 42, 6, seed=seed or title, circle=circle))
        col = QVBoxLayout()
        col.setSpacing(0)
        t = QLabel(title)
        t.setStyleSheet("font-weight:700;font-size:13px;background:transparent;")
        col.addWidget(t)
        if sub:
            s = QLabel(sub)
            s.setObjectName("YaSub")
            col.addWidget(s)
        r = QLabel(right)
        r.setObjectName("YaSub")
        lay.addWidget(num)
        lay.addWidget(pic)
        lay.addLayout(col, 1)
        lay.addWidget(r)

    def mouseReleaseEvent(self, e):
        if self.on_click and e.button() == Qt.MouseButton.LeftButton:
            self.on_click()


def _tile(caption, value):
    f = QFrame()
    f.setStyleSheet("QFrame{background:rgba(255,255,255,0.045);border:1px solid rgba(255,255,255,0.065);"
                    "border-radius:16px;}" if _phantom() else "QFrame{background:#1b1b1b;border-radius:14px;}")
    v = QVBoxLayout(f)
    v.setContentsMargins(18, 14, 18, 14)
    v.setSpacing(2)
    a = QLabel(value)
    a.setStyleSheet("font-size:24px;font-weight:900;background:transparent;")
    b = QLabel(caption)
    b.setStyleSheet("font-size:12px;color:#9a9a9a;background:transparent;")
    v.addWidget(a)
    v.addWidget(b)
    return f


class ProfilePage(Page):
    def __init__(self, shell, parent=None):
        super().__init__(parent, margins=(0, 0, 0, 24))
        self.shell = shell
        self.tab = "profile"
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)  # витрина не влезла — прокрутка вбок
        self._req = 0

    def _data_cover(self, path):
        for t in self.shell.win.library:
            if str(t.get("path", "")) == path:
                return t.get("cover", "")
        return ""

    def refresh(self, force=False):
        w = self.shell.win
        st = w.stats
        d0 = st.data
        net = self.shell.pages.get("net")
        node = getattr(net, "node", None)
        social = None
        if node is not None:
            settings = node.settings
            social = ({k: settings.get(k) for k in ("about", "fav", "share_tier", "follows")},
                      node.store.posts(node.me.onion, 30))
        tier_path = Path(getattr(w, "tierlist_path", data_home.root() / "music_tierlist.json"))
        try:
            tier_revision = tier_path.stat().st_mtime_ns
        except OSError:
            tier_revision = None
        # общее время прослушивания — не в подписи: пока играет музыка, оно меняется каждую минуту, и профиль
        # пересобирался целиком (с записью статистики на диск) почти на каждом показе; его меняем на месте
        sig = (len(w.library), len(d0.get("tracks") or {}),
               json.dumps(w.profile, sort_keys=True, ensure_ascii=False, default=str), self.tab,
               hash(json.dumps(w.settings.get("ya_profile_deco") or {}, sort_keys=True, default=str)),
               json.dumps(social, sort_keys=True, ensure_ascii=False, default=str), tier_revision)
        net_ = self.shell.pages.get("net")
        sig = sig + (net_ is not None and net_.__dict__.get("_sc_tools") is not None,)
        if self.tab == "time":                                 # вкладка времени — графики по минутам
            sig = sig + (int(d0.get("total", 0) // 60),)
        if not force and sig == getattr(self, "_sig", None) and self.v.count():
            hdr = getattr(self, "_hdr", None)                  # ничего не поменялось — не пересобирать
            minutes = int(d0.get("total", 0) // 60)
            if hdr is not None and minutes != getattr(self, "_minutes", None):
                self._minutes = minutes
                try:
                    st0 = w.profile.get("status", "")
                    sub = f"{len(w.library)} треков в коллекции  ·  прослушано {fmt_dur(d0['total'])}"
                    hdr.sub.setText(sub if not st0 else f"{st0}  ·  {sub}")
                except RuntimeError:
                    pass
            return
        self._sig = sig
        st.save()
        self._req += 1
        req = self._req
        self.clear()
        d = st.data
        hdr = ProfileHeader(self)
        self._hdr = hdr
        self._minutes = int(d.get("total", 0) // 60)
        n_plays = sum(v.get("plays", 0) for v in d["tracks"].values())
        hdr.set_profile(w.profile.get("nickname", "user"), w.profile.get("status", ""),
                        w.profile.get("avatar", ""),
                        f"{len(w.library)} треков в коллекции  ·  прослушано {fmt_dur(d['total'])}",
                        anim=str(w.profile.get("avatar_anim") or ""))
        hdr.btn.clicked.connect(w._edit_profile_then_refresh)
        self.v.addWidget(hdr)
        if node is not None:                                   # рамка, фон шапки, витрина
            deco = net.decorate_header(hdr, node.me.onion, True)
            scw = net.showcase_block(node.me.onion, True, deco)
            if scw is not None:
                box = QWidget()
                box.setObjectName("YaPageInner")
                bl_ = QHBoxLayout(box)
                bl_.setContentsMargins(32, 14, 32, 0)
                bl_.addWidget(scw)
                self.v.addWidget(box)

        bar = QWidget()
        bar.setObjectName("YaPageInner")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(32, 18, 32, 4)
        self.seg = SegTabs([("profile", "Профиль", "user"), ("time", "Время прослушивания", "clock")], self.tab)
        self.seg.changed.connect(self._switch)
        bl.addWidget(self.seg)
        bl.addStretch(1)
        import time as _t
        wr = QPushButton(f"  Итоги {_t.localtime().tm_year}")      # Echoes Wrapped
        wr.setObjectName("YaChip")
        wr.setIcon(ya_icon("star", 16, "#ffffff"))
        wr.setCursor(Qt.CursorShape.PointingHandCursor)
        wr.setToolTip("Echoes Wrapped — ваш год в музыке сторис-слайдами")
        wr.clicked.connect(lambda: __import__("ya_wrapped").open_wrapped(w))
        bl.addWidget(wr)
        self.v.addWidget(bar)

        self._body = QWidget()
        self._body.setObjectName("YaPageInner")
        self._bv = QVBoxLayout(self._body)
        self._bv.setContentsMargins(32, 0, 32, 0)
        self._bv.setSpacing(4)
        self.v.addWidget(self._body)
        self.v.addStretch(1)
        self._fill_body()

    def _fill_body(self):
        from yamusic_theme import _clear_layout
        _clear_layout(self._bv)
        self._req += 1
        st = self.shell.win.stats
        if self.tab == "profile":
            self._fill_profile(self._bv, st, self._req)
        else:
            n_plays = sum(v.get("plays", 0) for v in st.data["tracks"].values())
            self._fill_time(self._bv, st, n_plays)

    def _switch(self, key):
        """Смена вкладки: шапка и переключатель остаются (плашка плавно переезжает), меняется только содержимое."""
        self.tab = key
        self.seg.set_current(key)
        self._fill_body()

    # ── вкладка «Профиль» ── #

    def _fill_profile(self, bv, st, req):
        from artist_net import cached
        sh = self.shell
        net = sh.pages.get("net")
        if net is not None:
            net._fill_profile(body_layout=bv, own=True)
        recent = st.data["recent"]
        if not recent:
            lbl = QLabel("Пока пусто — включите несколько треков, и здесь появятся недавние исполнители и треки.")
            lbl.setObjectName("YaSub")
            lbl.setWordWrap(True)
            bv.addSpacing(24)
            bv.addWidget(lbl)
            return
        arts, cover_of = [], {}
        for r in recent:
            a = _first_artist(r.get("artist"))
            if a not in cover_of:
                arts.append(a)
                cover_of[a] = self._data_cover(r.get("path", ""))
            if len(arts) >= 14:
                break
        bv.addWidget(section_title("Недавние исполнители"))
        row = HRow()
        cards = {}
        for a in arts:
            pic = ""
            try:
                pic = (cached(a) or {}).get("picture", "") or ""
            except Exception:                        # noqa: BLE001
                pass
            c = Card(a, "Исполнитель", pic or cover_of[a], 130, circle=True)
            c.has_pic = bool(pic)
            c.clicked.connect(lambda a=a: sh.open_artist(a))
            cards[a] = c
            row.add(c)
        bv.addWidget(row)
        self._load_pictures(cards, req)

        bv.addWidget(section_title("Недавние треки"))
        seen, paths = set(), []
        for r in recent:
            p = str(r.get("path", ""))
            if p and p not in seen:
                seen.add(p)
                paths.append(p)
            if len(paths) >= 30:
                break
        by_path = {str(t.get("path", "")): t for t in sh.win.library}
        rows = sh._lib_rows([by_path[p] for p in paths if p in by_path])
        lst = TrackListView(sh)
        lst.set_auto_height(True)
        lst.set_rows(rows)
        bv.addWidget(lst.section_widget())

    def _load_pictures(self, cards, req):
        """Фото исполнителей, которых ещё нет в кэше, докачиваем в фоне."""
        todo = [a for a, c in cards.items() if not getattr(c, "has_pic", False)][:8]
        if not todo:
            return
        win = self.shell.win
        key = win.settings.get("lastfm_key", "")

        def work():
            from artist_net import fetch_artist
            for a in todo:
                try:
                    pic = (fetch_artist(a, key, images=False) or {}).get("picture", "")
                except Exception as e:               # noqa: BLE001
                    print("[profile] pic:", e)
                    continue
                if pic:
                    def apply(a=a, pic=pic):
                        c = cards.get(a)
                        if req == self._req and c is not None:
                            try:
                                c.cover = pic
                                c.update()
                            except RuntimeError:     # карточку уже удалили
                                pass
                    win._ui_bridge.call.emit(apply)
        threading.Thread(target=work, daemon=True).start()

    # ── вкладка «Время прослушивания» ── #

    def _fill_time(self, bv, st, n_plays):
        sh = self.shell
        tiles = QWidget()
        tiles.setObjectName("YaPageInner")
        tl = QHBoxLayout(tiles)
        tl.setContentsMargins(0, 18, 0, 0)
        tl.setSpacing(12)
        for cap, val in (("Всего прослушано", fmt_dur(st.data["total"])),
                         ("Сегодня", fmt_dur(st.seconds_since(1))),
                         ("За 7 дней", fmt_dur(st.seconds_since(7))),
                         ("Запусков треков", str(n_plays))):
            tl.addWidget(_tile(cap, val))
        bv.addWidget(tiles)
        try:                                                   # календарь, день, «в этот день год назад»
            from ya_history import HistoryBlock
            bv.addWidget(HistoryBlock(sh))
        except Exception as e:                                 # noqa: BLE001
            print("[history]", e)

        tops = st.top_artists(10)
        bv.addWidget(section_title("Топ исполнителей"))
        if not tops:
            lbl = QLabel("Статистика начнёт копиться, пока вы слушаете музыку.")
            lbl.setObjectName("YaSub")
            bv.addWidget(lbl)
        else:
            from artist_net import cached
            cover_of = {}
            for r in st.data["recent"]:
                cover_of.setdefault(_first_artist(r.get("artist")), self._data_cover(r.get("path", "")))
            for t in sh.win.library:
                cover_of.setdefault(_first_artist(t.get("artist")), t.get("cover", ""))
            for i, (name, v) in enumerate(tops, 1):
                try:
                    pic = (cached(name) or {}).get("picture", "") or ""
                except Exception:                    # noqa: BLE001
                    pic = ""
                bv.addWidget(StatRow(i, name, f"{v.get('plays', 0)} раз", pic or cover_of.get(name, ""),
                                     fmt_dur(v.get("sec", 0)), lambda n=name: sh.open_artist(n), circle=True))

        bv.addWidget(section_title("Топ треков"))
        tt = st.top_tracks(20)
        by_path = {}
        for t in sh.win.library:
            by_path[str(t.get("path", ""))] = t
        shown = 0
        for path, v in sorted(st.data["tracks"].items(),
                              key=lambda kv: (kv[1].get("plays", 0), kv[1].get("sec", 0)), reverse=True):
            if not (v.get("plays") or v.get("sec", 0) > 5):
                continue
            lib = by_path.get(path)
            shown += 1
            bv.addWidget(StatRow(shown, v.get("title") or "Без названия", v.get("artist", ""),
                                 (lib or {}).get("cover", ""),
                                 f"{v.get('plays', 0)} раз · {fmt_dur(v.get('sec', 0))}",
                                 (lambda p=path: sh.play_path(p)) if lib else None, seed=path))
            if shown >= 20:
                break
        if not tt:
            lbl = QLabel("Пока нет данных.")
            lbl.setObjectName("YaSub")
            bv.addWidget(lbl)
