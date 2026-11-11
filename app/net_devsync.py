# net_devsync.py
"""
Синхронизация между своими ПК / ноутбуком (через Echoes.NET — без облака и аккаунтов).

Привязка: на одном ПК «Показать код для другого ПК» (код живёт 10 минут) → на другом «Привязать этот ПК»
и вставить код. Устройства становятся друзьями с пометкой «моё устройство» (заявка принимается сама).

Что синхронизируется: плейлисты и «Мне нравится» (треки ищутся в своей коллекции, нет — добавляются
как онлайн-треки), ник и статус, оформление профиля (рамка, шапка, витрина). Правило: при первой
синхронизации плейлисты объединяются; дальше побеждает последнее изменение; удаление плейлиста тоже
доходит. Ник/оформление переносятся, когда их меняют (привязка ничего не затирает).
Состояние напоминается раз в минуту, пока устройство в сети, — догонит, если было выключено.
"""
from __future__ import annotations

import data_home
import hashlib
import json
import secrets
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer

MAX_TRACKS = 3000
PAIR_TTL = 600


def devices(nd) -> list:
    return list(nd.settings.get("my_devices") or [])


def is_device(nd, onion) -> bool:
    return onion in devices(nd)


def add_device(nd, onion):
    d = devices(nd)
    if onion not in d:
        nd.settings["my_devices"] = d + [onion]
        nd.save_settings()


def pair_code(nd) -> str:
    tok = secrets.token_hex(4)
    nd.settings["sync_pair"] = {"token": tok, "until": time.time() + PAIR_TTL}
    nd.save_settings()
    return f"ECHOES-SYNC {nd.code} {tok}"


def pair_ok(nd, token) -> bool:
    """Проверить и погасить одноразовый код привязки."""
    sp = nd.settings.get("sync_pair") or {}
    if token and sp.get("token") == token and time.time() < float(sp.get("until") or 0):
        nd.settings.pop("sync_pair", None)
        return True
    return False


def parse(text) -> tuple:
    parts = str(text or "").strip().split()
    if len(parts) == 3 and parts[0].upper() == "ECHOES-SYNC":
        return parts[1], parts[2]
    return "", ""


def _h(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def _tk(t):
    return (str(t.get("artist") or "").strip().lower(), str(t.get("title") or "").strip().lower())


class DevSync(QObject):
    def __init__(self, net):
        super().__init__(net)
        self.net = net
        self._sent = {}                                        # onion → когда слали снимок
        self.t = QTimer(self)
        self.t.setInterval(60000)
        self.t.timeout.connect(self.tick)
        self.t.start()

    @property
    def win(self):
        return self.net.win

    def state(self) -> dict:
        return self.win.settings.setdefault("devsync_state", {"pls": {}, "prof": {}, "deco": {}})

    # ── что синхронизируется ── #

    def _syncable(self) -> dict:
        from yamusic_theme import AUTO_PLAYLISTS
        return {n: p for n, p in self.win.playlists.items()
                if n not in AUTO_PLAYLISTS and isinstance(p, dict) and not p.get("shared")}

    def _prof(self) -> dict:
        p = self.win.profile or {}
        return {"nickname": str(p.get("nickname") or ""), "status": str(p.get("status") or "")}

    def _deco(self) -> dict:
        return dict(self.win.settings.get("ya_profile_deco") or {})

    def detect(self) -> bool:
        """Заметить свои изменения (новые метки времени). True — что-то поменялось."""
        st = self.state()
        now = time.time()
        changed = False
        pls = st.setdefault("pls", {})
        cur = self._syncable()
        for n, p in cur.items():
            h = _h([_tk(t) for t in p.get("tracks") or []])
            e = pls.get(n)
            if e is None:
                pls[n] = {"h": h, "ts": now, "init": True}
                changed = True
            elif e.get("del") or e.get("h") != h:
                pls[n] = {"h": h, "ts": now}
                changed = True
        for n, e in list(pls.items()):
            if n not in cur and not e.get("del"):
                pls[n] = {"h": "", "ts": now, "del": True}
                changed = True
        for key, val in (("prof", self._prof()), ("deco", self._deco())):
            e = st.get(key) or {}
            h = _h(val)
            if not e:
                st[key] = {"h": h, "ts": now, "init": True}
            elif e.get("h") != h:
                st[key] = {"h": h, "ts": now}
                changed = True
        return changed

    def snapshot(self) -> dict:
        from net_core import clean_track
        self.detect()
        st = self.state()
        cur = self._syncable()
        pls = {}
        for n, e in st["pls"].items():
            if e.get("del"):
                pls[n] = {"ts": e["ts"], "del": True}
            elif n in cur:
                tr = [x for x in (clean_track(t) for t in (cur[n].get("tracks") or [])[:MAX_TRACKS]) if x]
                for x in tr:
                    x.pop("thumb_url", None)
                pls[n] = {"ts": e["ts"], "init": bool(e.get("init")), "tracks": tr}
        out = {"t": "devsync", "pls": pls}
        if not st["prof"].get("init"):
            out["prof"] = dict(self._prof(), ts=st["prof"]["ts"])
        if not st["deco"].get("init"):
            out["deco"] = {"ts": st["deco"]["ts"], "d": self._deco()}
        return out

    # ── отправка ── #

    def send_all(self, force=False):
        nd = self.net.node
        if nd is None or not self.net.running():
            return
        snap = None
        for o in devices(nd):
            if not self.net._online(o):
                continue
            if not force and time.time() - self._sent.get(o, 0) < 25:
                continue
            snap = snap or self.snapshot()
            self._sent[o] = time.time()
            nd.call(nd.quiz_send, o, snap)

    def tick(self):
        nd = self.net.node
        if nd is None or not devices(nd):
            return
        changed = self.detect()
        self.send_all(force=changed)
        try:
            self.win.save_settings()
        except Exception:                                      # noqa: BLE001
            pass

    def on_presence(self, onion):
        nd = self.net.node
        if nd is not None and is_device(nd, onion):
            QTimer.singleShot(1500, lambda: self.send_all())

    # ── приём ── #

    def _map(self, metas) -> list:
        import net_music
        import stream_core
        out = []
        for m in metas:
            _i, local = net_music.library_match(self.win, m)
            out.append(dict(local) if local is not None else stream_core.make_track(m))
        return out

    def apply(self, m: dict) -> list:
        """Принять снимок с другого своего ПК. Возвращает, что поменялось (для подсказки)."""
        from net_core import clean_track, clip
        self.detect()
        st = self.state()
        pls_state = st["pls"]
        cur = self.win.playlists
        done = []
        rem = m.get("pls") if isinstance(m.get("pls"), dict) else {}
        for name, e in list(rem.items())[:300]:
            if not isinstance(e, dict):
                continue
            name = clip(name, 120).strip()
            try:
                rts = float(e.get("ts") or 0)
            except (TypeError, ValueError):
                continue
            if not name or rts > time.time() + 86400:
                continue
            le = pls_state.get(name) or {}
            from yamusic_theme import AUTO_PLAYLISTS
            if name in AUTO_PLAYLISTS or (cur.get(name) or {}).get("shared"):
                continue
            if e.get("del"):
                if name in cur and rts > float(le.get("ts") or 0) and not le.get("del"):
                    cur.pop(name, None)
                    pls_state[name] = {"h": "", "ts": rts, "del": True}
                    done.append(f"удалён «{name}»")
                continue
            metas = [x for x in (clean_track(t) for t in (e.get("tracks") or [])[:MAX_TRACKS]) if x]
            if name not in cur or le.get("del"):
                if le.get("del") and float(le.get("ts") or 0) >= rts:
                    continue                                   # у нас удалён позже
                cur[name] = {"tracks": self._map(metas), "desc": ""}
                done.append(f"новый «{name}»")
            elif le.get("init") or e.get("init"):              # первая встреча — объединить
                have = {_tk(t) for t in cur[name].get("tracks") or []}
                add = [x for x in metas if _tk(x) not in have]
                if add:
                    cur[name].setdefault("tracks", []).extend(self._map(add))
                    done.append(f"«{name}» +{len(add)}")
                h = _h([_tk(t) for t in cur[name].get("tracks") or []])
                pls_state[name] = {"h": h, "ts": time.time() if add or not e.get("init") else max(rts, float(le.get("ts") or 0))}
                continue
            elif rts > float(le.get("ts") or 0):               # дальше — побеждает последнее изменение
                if [_tk(t) for t in cur[name].get("tracks") or []] != [_tk(x) for x in metas]:
                    cur[name]["tracks"] = self._map(metas)
                    done.append(f"обновлён «{name}»")
            else:
                continue
            pls_state[name] = {"h": _h([_tk(t) for t in cur[name].get("tracks") or []]), "ts": rts}
        if done:
            try:
                self.win._ya_save_playlists() if hasattr(self.win, "_ya_save_playlists") else self.win._save_playlists()
            except Exception:                                  # noqa: BLE001
                pass
        pr = m.get("prof") if isinstance(m.get("prof"), dict) else None
        if pr and float(pr.get("ts") or 0) > float((st.get("prof") or {}).get("ts") or 0):
            nick, status = clip(pr.get("nickname"), 40).strip(), clip(pr.get("status"), 120)
            if nick:
                self.win.profile.update(nickname=nick, status=status)
                try:
                    p = data_home.root() / "profile.json"
                    p.write_text(json.dumps(self.win.profile, ensure_ascii=False, indent=2), encoding="utf-8")
                except OSError:
                    pass
                st["prof"] = {"h": _h(self._prof()), "ts": float(pr["ts"])}
                done.append("ник и статус")
        dc = m.get("deco") if isinstance(m.get("deco"), dict) else None
        if dc and float(dc.get("ts") or 0) > float((st.get("deco") or {}).get("ts") or 0):
            from net_showcase import clean_deco
            d = clean_deco(dc.get("d")) or {}
            d.pop("aura", None)
            self.win.settings["ya_profile_deco"] = d
            st["deco"] = {"h": _h(self._deco()), "ts": float(dc["ts"])}
            done.append("оформление профиля")
            try:
                self.net._deco_changed()
            except Exception:                                  # noqa: BLE001
                pass
        try:
            self.win.save_settings()
        except Exception:                                      # noqa: BLE001
            pass
        if done:
            try:
                sh = self.net.shell
                sh.refresh_sidebar()
            except Exception:                                  # noqa: BLE001
                pass
        return done


def on_message(net, data):
    nd = net.node
    o = data.get("from", "")
    m = data.get("m") or {}
    if nd is None:
        return
    if m.get("t") == "devpair":
        if pair_ok(nd, str(m.get("token") or "")):
            add_device(nd, o)
            net.toast("Устройство привязано — синхронизация пошла")
            QTimer.singleShot(500, lambda: get(net).send_all(force=True))
        return
    if not is_device(nd, o):
        return
    done = get(net).apply(m)
    if done:                                                   # ответить своим состоянием — сойдёмся быстрее
        QTimer.singleShot(300, lambda: get(net).send_all(force=True))
        net.toast("Синхронизация с вашим ПК: " + ", ".join(done[:4]) + ("…" if len(done) > 4 else ""))


def get(net) -> DevSync:
    ds = getattr(net, "_devsync", None)
    if ds is None:
        ds = net._devsync = DevSync(net)
    return ds


def join(net, text) -> str:
    """Привязать этот ПК по коду с другого. Возвращает сообщение для пользователя."""
    from net_core import normalize_code
    nd = net.node
    code, tok = parse(text)
    onion = normalize_code(code) if code else ""
    if not onion or not tok:
        return "Это не код синхронизации (он начинается с «ECHOES-SYNC»)"
    if onion == nd.me.onion:
        return "Это код этого же ПК — введите его на другом"
    add_device(nd, onion)
    c = nd.store.contact(onion)
    if c and c.get("status") == "friend":
        nd.call(nd.quiz_send, onion, {"t": "devpair", "token": tok})
    else:
        nd.call(nd.add_friend, code, "ECHOES-SYNC:" + tok)
    return "Привязка отправлена — как только оба ПК в сети, начнётся синхронизация"


def settings_card(net):
    from PyQt6.QtWidgets import QApplication, QHBoxLayout, QInputDialog, QLineEdit
    from net_page import accent_btn, card, ghost_btn, lbl
    nd = net.node
    f, v = card()
    v.addWidget(lbl("МОИ УСТРОЙСТВА (СИНХРОНИЗАЦИЯ)", "Section"))
    v.addWidget(lbl("Плейлисты, «Мне нравится», ник и оформление профиля — одинаковые на всех ваших ПК. "
                    "Без облака: напрямую через Echoes.NET, когда оба ПК в сети.", "YaSub", wrap=True))
    for o in devices(nd):
        c = nd.store.contact(o) or {}
        on = net._online(o)
        st = "в сети" if on else "не в сети"
        if c.get("status") != "friend":
            st = "ждёт подтверждения"
        h = QHBoxLayout()
        h.addWidget(lbl(f"\U000f1001  {c.get('name') or o[:8]}  ·  {st}", "NetName"), 1)
        import net_devfeed
        fon = net_devfeed.share_on(nd, o)
        fb = ghost_btn("Лента и друзья: вкл" if fon else "Лента и друзья: выкл")
        fb.setToolTip("Передавать этому устройству (например, телефону Echoes Lite) ваших друзей и ленту. "
                      "Реакции и посты с него уходят от имени этого ПК. Работает, пока этот ПК в сети.")

        def toggle_feed(_=False, o=o, on=fon):
            nd.call(net_devfeed.set_share, nd, o, not on)
            net.toast("Лента для устройства " + ("выключена" if on else "включена"))
            QTimer.singleShot(150, net._fill_net)
        fb.clicked.connect(toggle_feed)
        h.addWidget(fb)
        un = ghost_btn("Отвязать")

        def unlink(_=False, o=o):
            nd.settings["my_devices"] = [x for x in devices(nd) if x != o]
            nd.save_settings()
            net._fill_net()
        un.clicked.connect(unlink)
        h.addWidget(un)
        v.addLayout(h)
    h = QHBoxLayout()
    show = accent_btn("Показать код для другого ПК")
    code_lbl = QLineEdit()
    code_lbl.setReadOnly(True)
    code_lbl.hide()

    def do_show():
        code_lbl.setText(pair_code(nd))
        code_lbl.show()
        QApplication.clipboard().setText(code_lbl.text())
        net.toast("Код скопирован — вставьте его на другом ПК в течение 10 минут")
    show.clicked.connect(do_show)
    h.addWidget(show)
    j = ghost_btn("Привязать этот ПК по коду…")

    def do_join():
        text, ok = QInputDialog.getText(net, "Привязать этот ПК", "Код с другого ПК (ECHOES-SYNC …):")
        if ok and text.strip():
            net.toast(join(net, text))
            net._fill_net()
    j.clicked.connect(do_join)
    h.addWidget(j)
    if devices(nd):
        s = ghost_btn("Синхронизировать сейчас")
        s.clicked.connect(lambda: (get(net).detect(), get(net).send_all(force=True), net.toast("Отправлено")))
        h.addWidget(s)
    h.addStretch(1)
    v.addLayout(h)
    v.addWidget(code_lbl)
    return f
