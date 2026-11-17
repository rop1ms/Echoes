# net_challenge.py
"""
Музыкальный челлендж недели (Echoes.NET).

Тема недели одна у всех (по номеру недели): «Трек для дождя», «Лучший дроп», «Песня из детства»…
Вверху ленты — карточка челленджа: тема, сколько осталось, «Предложить трек» (играющий или из коллекции) и
лучшие заявки друзей с голосами. Голос — один на человека в неделю (новый голос снимает прежний).
Победитель недели (больше всех голосов, хотя бы один) получает ачивку «Чемпион недели» и рамку «Кубок».

Сеть: заявка — пост вида "chal" (week, theme), голос — подписанная реакция "cv". Старые версии ECHOES
такие посты просто не показывают.
"""
from __future__ import annotations

import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

THEMES = ("Трек для дождя за окном", "Самый мощный дроп", "Песня из детства", "Трек, который никто не знает",
          "Идеально для ночной поездки", "Под это невозможно не двигаться", "Самый грустный трек",
          "Лучший кавер или ремикс", "Трек с лучшим вступлением", "Музыка для учёбы и фокуса",
          "Трек, который вы заслушали до дыр", "Звук лета", "Трек, под который хочется в спортзал",
          "Лучшая коллаборация", "Трек с самым красивым голосом", "Трек, который стоит услышать хотя бы раз",
          "Песня на другом языке", "Саундтрек вашей недели", "Трек для зимнего вечера", "Неожиданный жанр")


def week_id(ts: float | None = None) -> str:
    import datetime
    y, w, _d = datetime.date.fromtimestamp(ts or time.time()).isocalendar()
    return f"{y}-W{w:02d}"


def theme_for(week: str) -> str:
    y, w = week.split("-W")
    return THEMES[(int(y) * 53 + int(w)) % len(THEMES)]


def left_text(ts: float | None = None) -> str:
    import datetime
    now = datetime.datetime.fromtimestamp(ts or time.time())
    end = (now + datetime.timedelta(days=7 - now.isoweekday())).replace(hour=23, minute=59, second=59)
    s = max(0, int((end - now).total_seconds()))
    d, h = s // 86400, s % 86400 // 3600
    import i18n
    if i18n.LANG == 'en':
        return f'{d}d {h}h remaining' if d else f'{h}h {s % 3600 // 60}m remaining'
    return f"ещё {d} д {h} ч" if d else f"ещё {h} ч {s % 3600 // 60} мин"


def prev_week(week: str) -> str:
    import datetime
    y, w = week.split("-W")
    monday = datetime.date.fromisocalendar(int(y), int(w), 1) - datetime.timedelta(days=7)
    yy, ww, _ = monday.isocalendar()
    return f"{yy}-W{ww:02d}"


def entries(net, week: str) -> list:
    """Заявки недели: [(пост, голоса)] — больше голосов выше."""
    st = net.node.store
    out = []
    for p in st.posts(limit=600):
        if p.get("kind") == "chal" and p.get("week") == week and p.get("track"):
            out.append((p, int(st.react_counts(p["id"], "cv").get("1", 0))))
    out.sort(key=lambda x: (-x[1], x[0].get("ts", 0)))
    return out


def winner(net, week: str):
    es = entries(net, week)
    if not es or es[0][1] < 1 or (len(es) > 1 and es[1][1] == es[0][1]):
        return None                                            # ничья или без голосов — без победителя
    return es[0][0]


def is_champion(net) -> bool:
    """Ачивка «Чемпион недели»: хоть раз ваша заявка победила."""
    me = net.node.me.onion
    weeks = {p.get("week") for p in net.node.store.posts(me, 300) if p.get("kind") == "chal"}
    cur = week_id()
    for w in weeks:
        if w and w != cur:
            win = winner(net, w)
            if win and win.get("author") == me:
                return True
    return False


def my_vote(net, week):
    me = net.node.me.onion
    st = net.node.store
    for p, _n in entries(net, week):
        if st.my_react(p["id"], me, "cv") == "1":
            return p["id"]
    return None


def vote(net, pid, week):
    """Один голос в неделю: прежний снимается."""
    if not net.running():
        net.toast("Включите сеть, чтобы голосовать")
        return
    old = my_vote(net, week)
    if old == pid:
        net.node.call(net.node.react, pid, "cv", "")          # повторный клик — снять голос
    else:
        if old:
            net.node.call(net.node.react, old, "cv", "")
        net.node.call(net.node.react, pid, "cv", "1")


def submit(net, meta, text=""):
    week = week_id()
    if not net.running():
        net.toast("Включите сеть, чтобы участвовать")
        return
    mine = [p for p, _n in entries(net, week) if p.get("author") == net.node.me.onion]
    if mine:
        net.toast("Одна заявка в неделю — ваша уже участвует")
        return
    net.node.call(net.node.publish, text or "Моя заявка", meta, "chal", week=week, theme=theme_for(week))
    net.toast("Заявка отправлена — друзья смогут проголосовать")


def _pick_and_submit(net):
    from PyQt6.QtGui import QCursor
    from PyQt6.QtWidgets import QMenu
    from net_page import track_meta
    m = QMenu(net)
    cur = net.shell.current_track()
    if cur:
        m.addAction(f"Играющий: {cur.get('title', '')}", lambda: submit(net, track_meta(cur)))

    def choose():
        from net_playlist_ui import TrackSearch, track_to_meta
        d = TrackSearch(net.win, net, title=f"Заявка: {theme_for(week_id())}")
        d.file_btn.hide()
        d.ok.setText("Отправить")
        if d.exec() and d.result_tracks:
            submit(net, track_to_meta(d.result_tracks[0]))
    m.addAction("Выбрать из коллекции…", choose)
    m.exec(QCursor.pos())


def card(net) -> QFrame:
    """Карточка челленджа вверху ленты."""
    from net_page import TrackChip, lbl
    week = week_id()
    f = QFrame()
    f.setObjectName("ChalCard")
    f.setStyleSheet("QFrame#ChalCard{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(255,157,0,0.28),"
                    "stop:1 rgba(255,59,59,0.10));border-radius:18px;border:1px solid rgba(255,190,80,0.25);}"
                    "QLabel{background:transparent;}")
    try:
        import ya_skin
        phantom = bool(ya_skin.PHANTOM_ON)
    except Exception:                                          # noqa: BLE001
        phantom = False
    if phantom:                                                # вид Phantom — стекло вместо оранжевой плашки
        f.setStyleSheet("QFrame#ChalCard{background:rgba(255,255,255,0.045);border-radius:20px;"
                        "border:1px solid rgba(255,255,255,0.065);}QLabel{background:transparent;}")
    v = QVBoxLayout(f)
    v.setContentsMargins(18, 14, 18, 14)
    v.setSpacing(8)
    top = QHBoxLayout()
    col = QVBoxLayout()
    col.setSpacing(0)
    from i18n import tr
    k = QLabel(tr("ЧЕЛЛЕНДЖ НЕДЕЛИ") + "  ·  " + left_text())
    k.setStyleSheet("color:rgba(255,255,255,0.42);font-size:10px;font-weight:600;letter-spacing:2px;" if phantom else
                    "color:#ffcf70;font-size:11px;font-weight:800;letter-spacing:1px;")
    t = QLabel(theme_for(week))
    t.setStyleSheet("font-size:20px;font-weight:600;" if phantom else "font-size:22px;font-weight:900;")
    t.setWordWrap(True)
    col.addWidget(k)
    col.addWidget(t)
    top.addLayout(col, 1)
    b = QPushButton("Предложить трек")
    b.setObjectName("AccentBtn")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.clicked.connect(lambda: _pick_and_submit(net))
    top.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
    v.addLayout(top)
    es = entries(net, week)
    mine = my_vote(net, week)
    if not es:
        v.addWidget(lbl("Заявок пока нет — будьте первым. Голос — один в неделю, победителю — ачивка и рамка «Кубок».",
                        "YaSub", wrap=True))
    for p, n in es[:5]:
        row = QHBoxLayout()
        row.addWidget(TrackChip(p["track"], net.play_meta, compact=True, cover=net._local_cover(p["track"])), 1)
        who = QLabel(p.get("name") or net._contact_label(p.get("author", "")))
        who.setStyleSheet("color:#bdbdbd;font-weight:700;")
        row.addWidget(who)
        vb = QPushButton(("★ " if mine == p["id"] else "☆ ") + str(n))
        vb.setObjectName("YaChip")
        vb.setCheckable(True)
        vb.setChecked(mine == p["id"])
        vb.setToolTip("Голос — один в неделю (повторный клик — снять)")
        vb.setEnabled(p.get("author") != net.node.me.onion)
        vb.clicked.connect(lambda _=False, pid=p["id"]: (vote(net, pid, week), net._fill_feed()))
        row.addWidget(vb)
        v.addLayout(row)
    pw = winner(net, prev_week(week))
    if pw:
        l = QLabel(f"\U000f1000 Прошлая неделя «{theme_for(prev_week(week))}»: {pw.get('name', '')} — "
                   f"{(pw.get('track') or {}).get('artist', '')} — {(pw.get('track') or {}).get('title', '')}")
        l.setWordWrap(True)
        l.setStyleSheet("color:#ffcf70;font-weight:700;")
        v.addWidget(l)
    return f


def block(net, p) -> QFrame:
    """Заявка в ленте: тема + голос."""
    week = p.get("week") or ""
    st = net.node.store
    n = int(st.react_counts(p["id"], "cv").get("1", 0))
    w = QFrame()
    w.setObjectName("ChalTag")
    w.setStyleSheet("QFrame#ChalTag{background:rgba(255,157,0,0.12);border-radius:12px;} QLabel{background:transparent;}")
    h = QHBoxLayout(w)
    h.setContentsMargins(12, 6, 8, 6)
    import html as _h                                    # тема — из чужого поста: только текст, не разметка
    t = QLabel(f"\U000f1000 Челлендж: <b>{_h.escape(str(p.get('theme') or theme_for(week)))}</b>")
    h.addWidget(t, 1)
    if week == week_id():
        mine = st.my_react(p["id"], net.node.me.onion, "cv") == "1"
        b = QPushButton(("★ " if mine else "☆ Голосовать · ") + str(n))
        b.setObjectName("YaChip")
        b.setEnabled(p.get("author") != net.node.me.onion)
        b.clicked.connect(lambda: (vote(net, p["id"], week), net._fill_feed()))
        h.addWidget(b)
    else:
        win = winner(net, week)
        h.addWidget(QLabel(("победитель недели · " if win and win["id"] == p["id"] else "") + f"голосов: {n}"))
    return w
