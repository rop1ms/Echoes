"""Своя обложка в карточке Phantom: фото, GIF или видео вместо обложки трека.

Правила хранятся в settings["ph"]["cover_rules"]: [{scope, key, label, path, fill}].
scope: all — все треки; nocover — треки без обложки; artist; album; track.
Если подходит несколько правил, побеждает самое точное: трек → альбом → исполнитель → без обложки → все треки.
Прежняя настройка «Видео вместо обложки» (cover_video) работает как самое слабое правило «все треки».
"""
from __future__ import annotations

import threading
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QFileDialog, QHBoxLayout, QLabel, QMenu, QVBoxLayout, QWidget

import ph_style as ph
import ph_widgets as pw

IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
GIFS = {".gif"}
VIDEOS = {".mp4", ".webm", ".mov", ".mkv", ".m4v", ".avi"}
BUNDLED = "bundled"                         # встроенное видео Phantom (assets/ph/cover-video.mp4)

# (scope, приоритет, значок, подпись в меню)
SCOPES = (
    ("track", 5, "eighth-note", "Для этого трека"),
    ("album", 4, "disc-3", "Для альбома"),
    ("artist", 3, "user-round", "Для исполнителя"),
    ("nocover", 2, "square-dashed", "Для треков без обложки"),
    ("all", 1, "earth", "Для всех треков"),
)
PRIORITY = {s[0]: s[1] for s in SCOPES}
ICON = {s[0]: s[2] for s in SCOPES}
FILTER = ("Фото, GIF или видео (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.mp4 *.webm *.mov *.mkv *.m4v *.avi)")


def media_path(rule: dict) -> str:
    p = str(rule.get("path") or "")
    if p == BUNDLED:
        import ph_backdrop
        return str(ph_backdrop.ASSETS_VIDEO)
    return p


def media_kind(path: str) -> str:
    """image | gif | video | '' (неизвестный файл)."""
    ext = Path(path).suffix.lower()
    return "image" if ext in IMAGES else "gif" if ext in GIFS else "video" if ext in VIDEOS else ""


def _artist_main(t) -> str:
    a = str((t or {}).get("artist") or "")
    try:
        from yamusic_theme import _artist_main as am
        a = am(a) or a
    except Exception:                                          # noqa: BLE001
        pass
    return a.strip()


def keys_for(t) -> dict:
    """Ключи трека для правил: track — путь файла, artist — главный исполнитель, album — исполнитель|альбом."""
    t = t or {}
    art = _artist_main(t).lower()
    alb = str(t.get("album") or "").strip().lower()
    out = {}
    if t.get("path"):
        out["track"] = str(t["path"])
    if art:
        out["artist"] = art
    if alb:
        out["album"] = f"{art}|{alb}"
    return out


def labels_for(t) -> dict:
    """Подписи правил для трека (что увидит человек в списке правил)."""
    t = t or {}
    try:
        from yamusic_theme import sanitize_title
        title = sanitize_title(str(t.get("title") or "")) or "Без названия"
    except Exception:                                          # noqa: BLE001
        title = str(t.get("title") or "Без названия")
    art = _artist_main(t)
    return {"track": f"{title} — {art}" if art else title, "album": str(t.get("album") or "").strip(),
            "artist": art, "nocover": "Треки без обложки", "all": "Все треки"}


def rules(win) -> list:
    import ph_panels
    r = ph_panels.ph_settings(win).get("cover_rules") or []
    return [dict(x) for x in r if isinstance(x, dict) and x.get("scope") in PRIORITY and x.get("path")]


def save_rules(win, items: list):
    import ph_panels
    ph_panels.set_ph(win, cover_rules=items)


def put_rule(win, scope: str, key: str, label: str, path: str):
    """Добавить правило (то же место — заменить файл). Видео и GIF по умолчанию — на всю карточку."""
    items = [r for r in rules(win) if not (r["scope"] == scope and r.get("key", "") == key)]
    kind = media_kind(media_path({"path": path}))
    items.append({"scope": scope, "key": key, "label": label, "path": path, "fill": kind in ("video", "gif")})
    items.sort(key=lambda r: -PRIORITY[r["scope"]])
    save_rules(win, items)


def legacy_rule(win):
    """Прежняя настройка «Видео вместо обложки» — как правило «все треки» (самое слабое)."""
    import ph_panels
    s = ph_panels.ph_settings(win)
    mode = s.get("cover_video")
    if mode == "bundled":
        return {"scope": "all", "key": "", "label": "Все треки", "path": BUNDLED, "fill": True, "legacy": True}
    if mode == "custom" and s.get("cover_video_path"):
        return {"scope": "all", "key": "", "label": "Все треки", "path": s["cover_video_path"], "fill": True,
                "legacy": True}
    return None


def resolve(win, t, has_cover: bool):
    """Правило для трека или None. Чем точнее правило, тем оно главнее."""
    ks = keys_for(t)
    best, bp = None, 0
    for r in rules(win):
        sc = r["scope"]
        ok = sc == "all" or (sc == "nocover" and not has_cover) or (sc in ks and ks[sc] == r.get("key"))
        if not ok or PRIORITY[sc] <= bp:
            continue
        path = media_path(r)
        if not path or not Path(path).exists() or not media_kind(path):
            continue
        best, bp = r, PRIORITY[sc]
    if best is None:
        lg = legacy_rule(win)
        if lg is not None and Path(media_path(lg)).exists():
            best = lg
    return best


# ── сведения о файле для карточки «Сведения»: формат и качество (в фоне, с кэшем) ── #

class _Quality(QObject):
    ready = pyqtSignal(str, str)


QUALITY = None
_QCACHE: dict = {}


def quality(path: str) -> str | None:
    """'44.1 кГц · 16 бит' / '320 кбит/с' или None, пока считается (потом придёт QUALITY.ready)."""
    global QUALITY
    if not path:
        return ""
    if path in _QCACHE:
        return _QCACHE[path]
    if QUALITY is None:
        QUALITY = _Quality()
    _QCACHE[path] = None

    def work():
        txt = ""
        try:
            import mutagen
            f = mutagen.File(path)
            info = getattr(f, "info", None)
            sr = int(getattr(info, "sample_rate", 0) or 0)
            bits = int(getattr(info, "bits_per_sample", 0) or 0)
            br = int(getattr(info, "bitrate", 0) or 0)
            if bits and sr:
                txt = f"{sr / 1000:g} кГц · {bits} бит"
            elif br:
                txt = f"{round(br / 1000)} кбит/с"
            elif sr:
                txt = f"{sr / 1000:g} кГц"
        except Exception:                                      # noqa: BLE001
            txt = ""
        _QCACHE[path] = txt
        try:
            QUALITY.ready.emit(path, txt)
        except RuntimeError:
            pass
    threading.Thread(target=work, daemon=True, name="ph-quality").start()
    return None


# ── меню на карточке и в настройках ── #

def _ask_file(parent, title: str) -> str:
    f, _ = QFileDialog.getOpenFileName(parent, title, "", FILTER)
    return f or ""


def add_for(lay, scope: str, parent=None, path: str | None = None) -> bool:
    """Выбрать файл и поставить правило scope (для трека/альбома/исполнителя — играющего сейчас)."""
    win = lay.win
    t = lay.shell.current_track() if hasattr(lay.shell, "current_track") else None
    ks, lb = keys_for(t), labels_for(t)
    if scope in ("track", "album", "artist") and scope not in ks:
        return False
    if path is None:
        what = {"track": f"трека «{lb['track']}»", "album": f"альбома «{lb['album']}»",
                "artist": f"исполнителя {lb['artist']}", "nocover": "треков без обложки",
                "all": "всех треков"}[scope]
        path = _ask_file(parent, f"Своя обложка для {what}")
    if not path:
        return False
    put_rule(win, scope, ks.get(scope, ""), lb[scope], path)
    lay.refresh_cover_media()
    return True


def remove_rule(lay, rule: dict):
    win = lay.win
    if rule.get("legacy"):
        import ph_panels
        ph_panels.set_ph(win, cover_video="off")
    else:
        save_rules(win, [r for r in rules(win)
                         if not (r["scope"] == rule["scope"] and r.get("key", "") == rule.get("key", ""))])
    lay.refresh_cover_media()


def scope_menu(lay, parent) -> QMenu:
    """Пункты «Для этого трека / альбома / исполнителя / без обложки / всех треков» (с именами играющего)."""
    m = QMenu(parent)
    t = lay.shell.current_track() if hasattr(lay.shell, "current_track") else None
    ks, lb = keys_for(t), labels_for(t)
    for scope, _pri, icon, text in SCOPES:
        name = {"track": lb["track"], "album": lb["album"], "artist": lb["artist"]}.get(scope, "")
        a = m.addAction(ph.icon(icon, 14), f"{text}: {_short(name)}" if name else text)
        a.setEnabled(scope not in ("track", "album", "artist") or scope in ks)
        a.triggered.connect(lambda _=False, s=scope: add_for(lay, s, parent))
    return m


def _short(s: str, n: int = 34) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


STYLES = (("info", "Сведения"), ("blur", "Размытый фон"), ("vinyl", "Винил"), ("crop", "Обрезать"))


def cover_menu(lay, anchor):
    """Кнопка на карточке обложки: своя обложка (по правилам) и вид карточки."""
    m = scope_menu(lay, anchor)
    m.insertSection(m.actions()[0], "Своя обложка — фото, GIF или видео")
    cur = getattr(lay.cover, "_rule", None)
    if cur is not None:
        m.addSeparator()
        a = m.addAction(ph.icon("trash", 14), f"Убрать: {rule_title(cur)}")
        a.triggered.connect(lambda: remove_rule(lay, cur))
    m.addSeparator()
    sub = m.addMenu("Вид карточки")
    import ph_panels
    st = ph_panels.ph_settings(lay.win).get("cover_style", "info")
    for k, text in STYLES:
        a = sub.addAction(text)
        a.setCheckable(True)
        a.setChecked(k == st)
        a.triggered.connect(lambda _=False, key=k: (ph_panels.set_ph(lay.win, cover_style=key),
                                                    lay.apply_appearance(["cover_style"])))
    m.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))


def rule_title(r: dict) -> str:
    sc = r["scope"]
    name = r.get("label") or ""
    return {"track": f"трек «{name}»", "album": f"альбом «{name}»", "artist": f"исполнитель {name}",
            "nocover": "треки без обложки", "all": "все треки"}[sc]


# ── редактор правил для настроек ── #

class RulesEditor(QWidget):
    """Список своих обложек: что, на что и кнопки «Добавить» / убрать. Без лишних вложенных окон."""

    def __init__(self, lay, parent=None):
        super().__init__(parent)
        self.lay = lay
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, ph.px(6), 0, 0)
        v.setSpacing(ph.px(6))
        head = QHBoxLayout()
        head.setSpacing(ph.px(8))
        col = QVBoxLayout()
        col.setSpacing(ph.px(2))
        col.addWidget(pw.label("Свои обложки", "PhBody", font=ph.font(ph.TEXT_BASE, 550)))
        hint = pw.label("Фото, GIF или видео. Если подходят несколько, главнее самое точное: "
                        "сначала трек, потом альбом, исполнитель, «без обложки» и в конце «все треки».", "PhSub",
                        font=ph.font(ph.TEXT_XS))
        hint.setWordWrap(True)
        col.addWidget(hint)
        head.addLayout(col, 1)
        self.add = pw.text_button("Добавить", "small", icon="plus")
        self.add.clicked.connect(self._add_menu)
        head.addWidget(self.add, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(head)
        self.list = QVBoxLayout()
        self.list.setSpacing(ph.px(4))
        v.addLayout(self.list)
        self.empty = pw.label("Пока нет — карточка показывает обложку трека.", "PhSub", font=ph.font(ph.TEXT_XS))
        v.addWidget(self.empty)
        self.refresh()

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()                                         # правила могли поменять с карточки обложки

    def _add_menu(self):
        m = scope_menu(self.lay, self)
        for a in m.actions():
            a.triggered.connect(lambda *_: self.refresh())
        m.exec(self.add.mapToGlobal(self.add.rect().bottomLeft()))

    def refresh(self):
        while self.list.count():
            it = self.list.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        items = rules(self.lay.win)
        lg = legacy_rule(self.lay.win)
        if lg is not None:
            items.append(lg)
        for r in items:
            self.list.addWidget(self._row(r))
        self.empty.setVisible(not items)

    def _row(self, r: dict) -> QWidget:
        row = pw.PhSurface("row")
        h = QHBoxLayout(row)
        h.setContentsMargins(ph.px(10), ph.px(6), ph.px(6), ph.px(6))
        h.setSpacing(ph.px(10))
        ic = QLabel()
        ic.setPixmap(ph.icon_pixmap(ICON[r["scope"]], 16, ph.TEXT_SECONDARY))
        h.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(0)
        t = rule_title(r)
        ttl = pw.label(t[:1].upper() + t[1:], "PhBody", font=ph.font(ph.TEXT_SM, 550))
        col.addWidget(ttl)
        path = media_path(r)
        kind = {"image": "фото", "gif": "GIF", "video": "видео"}.get(media_kind(path), "файл")
        name = "встроенное видео" if r.get("path") == BUNDLED else Path(path).name
        miss = "" if Path(path).exists() else " · файл не найден"
        sub = pw.label(f"{kind} · {name}{miss}" + (" · из прежней настройки" if r.get("legacy") else ""),
                       "PhSub", font=ph.font(ph.TEXT_XS))
        col.addWidget(sub)
        h.addLayout(col, 1)
        if not r.get("legacy"):
            fill = QCheckBox("Вся карточка")
            fill.setToolTip("Растянуть на всю карточку (иначе — на месте обложки в выбранном виде карточки)")
            fill.setFont(ph.font(ph.TEXT_XS))
            fill.setChecked(bool(r.get("fill")))
            fill.toggled.connect(lambda on, rr=r: self._set_fill(rr, on))
            h.addWidget(fill)
            ch = pw.icon_button("pencil", "ghost", "sm", 13, "Другой файл")
            ch.clicked.connect(lambda _=False, rr=r: self._change(rr))
            h.addWidget(ch)
        rm = pw.icon_button("trash", "ghost", "sm", 13, "Убрать")
        rm.clicked.connect(lambda _=False, rr=r: (remove_rule(self.lay, rr), self.refresh()))
        h.addWidget(rm)
        return row

    def _set_fill(self, r, on):
        items = rules(self.lay.win)
        for x in items:
            if x["scope"] == r["scope"] and x.get("key", "") == r.get("key", ""):
                x["fill"] = bool(on)
        save_rules(self.lay.win, items)
        self.lay.refresh_cover_media()

    def _change(self, r):
        f = _ask_file(self, "Другой файл для своей обложки")
        if not f:
            return
        put_rule(self.lay.win, r["scope"], r.get("key", ""), r.get("label", ""), f)
        self.lay.refresh_cover_media()
        self.refresh()
