# ph_panels.py
"""
Панели Phantom для раскладки ya_layout = "phantom" (этап 4): Библиотека, Очередь, Настройки.

  * Библиотека — вкладки «Треки | Плейлисты | Папки» (как у Phantom): поиск, «добавить файлы / папку /
    проверить файлы», фильтры «Все файлы · Избранное · Недавно прослушано · Отсутствующие файлы», сортировка
    и её направление, строки треков Phantom. Список — TrackListView Echoes (виртуальный, контекстное меню,
    выделение, Delete, «Играть следующим»…), только строки рисует PhTrackDelegate;
  * Очередь — «Сейчас играет» карточкой и «Далее» строками с номером, «×» убирает трек из вашей очереди,
    корзина — очистить её;
  * Настройки — разделы Phantom: «Оформление» (размытие, фон, анимация фона, прозрачность карточек, масштаб,
    эффекты, обработка обложки, движение, видео-обложка, своё фото фона, яркость), «Текст» (размер, размытие
    неактивных строк, подсветка слов, автопрокрутка), «Виджеты». Все прочие настройки Echoes — вкладкой
    «Echoes» в шапке панели (прежняя страница настроек).

Настройки Phantom хранятся в win.settings["ph"] (PH_DEFAULTS) и применяются сразу (apply_appearance).
"""
from __future__ import annotations

import threading
from pathlib import Path

from PyQt6.QtCore import QObject, QPointF, QRect, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import (QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                             QScrollArea, QSlider, QStackedWidget, QStyle, QStyledItemDelegate, QVBoxLayout,
                             QWidget, QComboBox)

import ph_style as ph
import ph_widgets as pw

PH_DEFAULTS = {
    "blur": 28, "bg_intensity": .6, "bg_animation": True, "card_opacity": .72, "ui_scale": 1.0, "effects": True,
    "cover_treatment": "original", "motion": "system", "cover_video": "off", "cover_video_path": "",
    "bg_image": "", "bg_brightness": 1.0,
    "bg_cover": False, "bg_flow": True,                    # фон — обложка трека; перетекание её цветов
    "cover_style": "info", "cover_rules": [],              # вид карточки обложки; свои обложки (ph_cover)
    "lyrics_scale": 1.0, "lyrics_blur": True, "lyrics_words": True, "lyrics_autoscroll": True,
}


def ph_settings(win) -> dict:
    s = win.settings.get("ph")
    if not isinstance(s, dict):
        s = {}
    out = dict(PH_DEFAULTS)
    out.update({k: v for k, v in s.items() if k in PH_DEFAULTS})
    return out


def set_ph(win, **kw):
    s = win.settings.get("ph")
    if not isinstance(s, dict):
        s = win.settings["ph"] = {}
    s.update(kw)
    try:
        win._schedule_settings_save()
    except Exception:                                          # noqa: BLE001
        pass


def _fmt(sec) -> str:
    sec = max(0, int(float(sec or 0)))
    return f"{sec // 60}:{sec % 60:02d}"


def _scroll(widget: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setObjectName("PhScroll")
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    sa.setWidget(widget)
    sa.viewport().setAutoFillBackground(False)
    return sa


# ══════════════════════════════════════════════════════════════════════════ #
#  Строки треков Phantom
# ══════════════════════════════════════════════════════════════════════════ #

class PhTrackDelegate(QStyledItemDelegate):
    """Строка Phantom 58 px: обложка 40 · название и исполнитель · альбом · длительность · ♥ · ⋯; волосок снизу;
    играющий трек — светлее и с полоской слева."""

    ROW_H = 58

    def __init__(self, shell, parent=None):
        super().__init__(parent)
        self.shell = shell

    def sizeHint(self, opt, idx):
        return QSize(opt.rect.width(), ph.px(self.ROW_H))

    @staticmethod
    def zones(r: QRect) -> dict:
        s = ph.px(28)
        cy = r.top() + (r.height() - s) // 2
        dots = QRect(r.right() - ph.px(6) - s, cy, s, s)
        heart = QRect(dots.left() - ph.px(6) - s, cy, s, s)
        dur = QRect(heart.left() - ph.px(54), r.top(), ph.px(44), r.height())
        cover = QRect(r.left() + ph.px(8), r.top() + (r.height() - ph.px(40)) // 2, ph.px(40), ph.px(40))
        alb_w = ph.px(130) if r.width() > ph.px(520) else 0
        album = QRect(dur.left() - ph.px(10) - alb_w, r.top(), alb_w, r.height())
        return {"dots": dots, "heart": heart, "dur": dur, "cover": cover, "album": album}

    def paint(self, p: QPainter, opt, idx):
        from yamusic_theme import _row, cover_pixmap, sanitize_title
        row = _row(idx)
        if not row:
            return
        t = row["t"]
        r = opt.rect
        sh = self.shell
        hover = bool(opt.state & QStyle.StateFlag.State_MouseOver)
        sel = bool(opt.state & QStyle.StateFlag.State_Selected)
        cur = sh.is_current(t)
        z = self.zones(r)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if cur or hover or sel:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ph.white(.08 if (cur or sel) else .043))
            p.drawRoundedRect(QRectF(r).adjusted(0, 1, 0, -1), ph.px(10), ph.px(10))
            if cur:
                p.setBrush(ph.white(.7))
                p.drawRoundedRect(QRectF(r.left(), r.top() + ph.px(14), 2, r.height() - 2 * ph.px(14)), 1, 1)
        else:
            ph.paint_hairline(p, r.left() + ph.px(8), r.right() - ph.px(6), r.bottom())
        view = getattr(opt, "widget", None)
        pm = cover_pixmap(t.get("cover", ""), ph.px(40), ph.px(8), seed=t.get("path", "") or t.get("title", ""),
                          lazy=view.viewport() if hasattr(view, "viewport") else view)
        p.drawPixmap(z["cover"], pm)
        if hover or cur:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 120))
            p.drawRoundedRect(QRectF(z["cover"]), ph.px(8), ph.px(8))
            name = "pause" if (cur and sh.is_playing()) else "play"
            ic = ph.icon_pixmap(name, 15, ph.TEXT_PRIMARY, fill=ph.TEXT_PRIMARY)
            s = ic.width() / ic.devicePixelRatio()
            p.drawPixmap(QPointF(z["cover"].center().x() - s / 2 + .5, z["cover"].center().y() - s / 2 + .5), ic)
        tx = z["cover"].right() + ph.px(14)
        right = (z["album"].left() if z["album"].width() else z["dur"].left()) - ph.px(10)
        tw = max(20, right - tx)
        title = sanitize_title(t.get("title", "") or "Без названия")
        artist = t.get("artist") or "Неизвестный исполнитель"
        f1 = ph.font(ph.TEXT_MD, 600)
        p.setFont(f1)
        p.setPen(ph.qcolor(ph.TEXT_PRIMARY))
        fm = QFontMetrics(f1)
        p.drawText(QRect(tx, r.top() + ph.px(10), tw, ph.px(20)), Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(title, Qt.TextElideMode.ElideRight, tw))
        f2 = ph.font(ph.TEXT_XS, 500)
        p.setFont(f2)
        p.setPen(ph.qcolor(ph.TEXT_TERTIARY))
        p.drawText(QRect(tx, r.top() + ph.px(30), tw, ph.px(18)), Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(f2).elidedText(artist, Qt.TextElideMode.ElideRight, tw))
        if z["album"].width():
            alb = " ".join(str(t.get("album") or "").split()) or "Неизвестный альбом"
            f3 = ph.font(ph.TEXT_SM, 500)
            p.setFont(f3)
            p.setPen(ph.qcolor(ph.TEXT_TERTIARY))
            p.drawText(z["album"], Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       QFontMetrics(f3).elidedText(alb, Qt.TextElideMode.ElideRight, z["album"].width()))
        p.setFont(ph.font(ph.TEXT_SM, 600, tnum=True))
        p.setPen(ph.qcolor(ph.TEXT_SECONDARY))
        p.drawText(z["dur"], Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                   _fmt(t.get("duration") or 0))
        liked = sh.is_liked(t)
        hc = ph.TEXT_PRIMARY if liked else (ph.TEXT_SECONDARY if hover else ph.TEXT_TERTIARY)
        hp = ph.icon_pixmap("heart", 15, hc, fill=ph.TEXT_PRIMARY if liked else None)
        s = hp.width() / hp.devicePixelRatio()
        p.drawPixmap(QPointF(z["heart"].center().x() - s / 2 + .5, z["heart"].center().y() - s / 2 + .5), hp)
        dp = ph.icon_pixmap("ellipsis", 15, ph.TEXT_SECONDARY if hover else ph.TEXT_TERTIARY)
        p.drawPixmap(QPointF(z["dots"].center().x() - s / 2 + .5, z["dots"].center().y() - s / 2 + .5), dp)
        p.restore()


def make_track_list(shell):
    """TrackListView Echoes со строками Phantom и своими зонами клика."""
    from yamusic_theme import TrackListView, _row

    class PhTrackList(TrackListView):
        def __init__(self, sh):
            super().__init__(sh)
            self.setObjectName("PhList")
            self.setItemDelegate(PhTrackDelegate(sh, self))
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.setStyleSheet("QListView#PhList{background:transparent;border:0;outline:0;}")
            self.viewport().setAutoFillBackground(False)

        def mousePressEvent(self, e):
            idx = self.indexAt(e.position().toPoint())
            if idx.isValid() and e.button() == Qt.MouseButton.LeftButton:
                z = PhTrackDelegate.zones(self.visualRect(idx))
                pt = e.position().toPoint()
                row = _row(idx)
                if z["dots"].contains(pt):
                    self.setCurrentIndex(idx)
                    self._menu(pt)
                    return
                if z["heart"].contains(pt):
                    self.shell.toggle_like(row["t"])
                    self.viewport().update()
                    return
                if z["cover"].contains(pt):
                    if self.shell.is_current(row["t"]):
                        self.shell.win.toggle_play()
                    else:
                        self.shell.play_row(row)
                    self.viewport().update()
                    return
            from PyQt6.QtWidgets import QListView
            QListView.mousePressEvent(self, e)

    return PhTrackList(shell)


# ══════════════════════════════════════════════════════════════════════════ #
#  Библиотека
# ══════════════════════════════════════════════════════════════════════════ #

class _MissingBus(QObject):
    done = pyqtSignal(int, object)


SORTS = (("added", "Дата добавления"), ("title", "Название"), ("artist", "Исполнитель"), ("album", "Альбом"),
         ("duration", "Длительность"), ("plays", "Часто слушаю"))


class PhLibraryPanel(QWidget):
    """Библиотека Phantom: Треки · Плейлисты · Папки."""

    def __init__(self, lay, parent=None):
        super().__init__(parent)
        self.lay = lay
        self.shell, self.win = lay.shell, lay.win
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        st = self.win.settings.get("ph_lib") or {}
        self.filter = st.get("filter", "all") if st.get("filter") in ("all", "fav", "recent", "missing") else "all"
        self.sort = st.get("sort", "added") if st.get("sort") in dict(SORTS) else "added"
        self.desc = bool(st.get("desc", True))
        self.folder = None
        self._missing: set | None = None
        self._sig = None
        self._bus = _MissingBus(self)
        self._bus.done.connect(self._on_missing)
        self._tok = 0
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(ph.px(12))
        self.tabs = pw.PhSegments([("tracks", "Треки", "eighth-note"), ("playlists", "Плейлисты", "list-music"),
                                   ("folders", "Папки", "folder-open")])
        self.tabs.changed.connect(self._tab)
        v.addWidget(self.tabs)
        self.stack = QStackedWidget()
        self.stack.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        v.addWidget(self.stack, 1)
        # ── треки ── #
        tw = QWidget()
        tv = QVBoxLayout(tw)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(ph.px(10))
        sr = QHBoxLayout()
        sr.setSpacing(ph.px(8))
        self.search = pw.PhSearch("Поиск по названию, исполнителю или альбому")
        self.search.textChanged.connect(lambda q: self.list.set_filter(q))
        sr.addWidget(self.search, 1)
        for name, tip, fn in (("file-plus-corner", "Добавить файлы", self.win._add_files),
                              ("folder-plus", "Добавить папку", self.win._add_folder),
                              ("refresh-cw", "Проверить файлы (найти пропавшие)", self.recheck)):
            b = pw.icon_button(name, "surface", "lg", 16, tip)
            b.clicked.connect(fn)
            sr.addWidget(b)
        tv.addLayout(sr)
        cr = QHBoxLayout()
        cr.setSpacing(ph.px(6))
        self.chips = {}
        for key, text in (("all", "Все файлы"), ("fav", "Избранное"), ("recent", "Недавно прослушано"),
                          ("missing", "Отсутствующие файлы")):
            c = pw.chip(text, key == self.filter)
            c.clicked.connect(lambda _=False, k=key: self.set_filter(k))
            cr.addWidget(c)
            self.chips[key] = c
        self.folder_chip = pw.chip("", True)
        self.folder_chip.setIcon(ph.icon("x", 12, ph.TEXT_PRIMARY))
        self.folder_chip.clicked.connect(lambda: self.set_folder(None))
        self.folder_chip.hide()
        cr.addWidget(self.folder_chip)
        cr.addStretch(1)
        tv.addLayout(cr)
        so = QHBoxLayout()
        so.setSpacing(ph.px(8))
        so.addWidget(pw.label("Сортировка", "PhMuted", font=ph.font(ph.TEXT_SM, 500)))
        self.sort_box = QComboBox()
        self.sort_box.setObjectName("PhSelect")
        ph.set_font(self.sort_box, ph.font(ph.TEXT_XS, 600))
        for k, t in SORTS:
            self.sort_box.addItem(t, k)
        self.sort_box.setCurrentIndex([k for k, _ in SORTS].index(self.sort))
        self.sort_box.currentIndexChanged.connect(lambda i: self.set_sort(SORTS[i][0]))
        so.addWidget(self.sort_box)
        self.order = pw.icon_button("arrow-down-wide-narrow", "surface", "md", 15, "Порядок сортировки")
        self.order.clicked.connect(self.toggle_order)
        so.addWidget(self.order)
        so.addStretch(1)
        self.count = pw.label("", "PhMuted")
        so.addWidget(self.count)
        tv.addLayout(so)
        self.list = make_track_list(self.shell)
        tv.addWidget(self.list, 1)
        self.empty = pw.label("", "PhSub")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.hide()
        tv.addWidget(self.empty)
        self.stack.addWidget(tw)
        # ── плейлисты ── #
        pwid = QWidget()
        pv = QVBoxLayout(pwid)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(ph.px(10))
        ph_row = QHBoxLayout()
        ph_row.addWidget(pw.label("Ваши плейлисты", "PhHeading"))
        ph_row.addStretch(1)
        nb = pw.text_button("Новый плейлист", "secondary", "plus")
        nb.clicked.connect(lambda: (self.shell.new_playlist(), QTimer.singleShot(300, self.refresh_playlists)))
        ph_row.addWidget(nb)
        pv.addLayout(ph_row)
        self.pl_list = _RowList(self._open_playlist)
        pv.addWidget(self.pl_list, 1)
        self.stack.addWidget(pwid)
        # ── папки ── #
        fwid = QWidget()
        fv = QVBoxLayout(fwid)
        fv.setContentsMargins(0, 0, 0, 0)
        fv.setSpacing(ph.px(10))
        fr = QHBoxLayout()
        fr.addWidget(pw.label("Папки с музыкой", "PhHeading"))
        fr.addStretch(1)
        ab = pw.text_button("Добавить папку", "secondary", "folder-plus")
        ab.clicked.connect(lambda: (self.win._add_folder(), self.refresh_folders()))
        fr.addWidget(ab)
        fv.addLayout(fr)
        self.dir_list = _RowList(self._open_folder)
        fv.addWidget(self.dir_list, 1)
        self.stack.addWidget(fwid)
        self._sync_order_icon()

    # ── данные ── #
    def _save(self):
        self.win.settings["ph_lib"] = {"filter": self.filter, "sort": self.sort, "desc": self.desc}

    def signature(self):
        lib = self.win.library
        return (len(lib), id(lib), self.filter, self.sort, self.desc, self.folder,
                len(self.win.settings.get("play_history") or {}), self._missing is not None)

    def invalidate(self):
        self._sig = None

    def refresh_on_open(self):
        # Playback counts and the favourites list can change without a library edit.
        self.refresh(force=self.filter in ("fav", "recent") or self.sort == "plays")

    def refresh(self, force=False):
        sig = self.signature()
        if not force and sig == self._sig:
            self.list.viewport().update()
            return
        self._sig = sig
        lib = self.win.library
        rows = [{"t": t, "ctx": "library", "i": i} for i, t in enumerate(lib)]
        if self.folder:
            rows = [r for r in rows if str(Path(str(r["t"].get("path", ""))).parent) == self.folder]
        hist = self.win.settings.get("play_history") or {}
        if self.filter == "fav":
            rows = [r for r in rows if self.shell.is_liked(r["t"])]
        elif self.filter == "recent":
            rows = [r for r in rows if str(r["t"].get("path", "")) in hist]
        elif self.filter == "missing":
            if self._missing is None:
                self._scan_missing()
                rows = []
            else:
                rows = [r for r in rows if str(r["t"].get("path", "")) in self._missing]
        key = self.sort
        if self.filter == "recent" and key == "added":
            rows.sort(key=lambda r: (hist.get(str(r["t"].get("path", "")), {}).get("last", ""),
                                     hist.get(str(r["t"].get("path", "")), {}).get("count", 0)), reverse=True)
        elif key == "added":
            if self.desc:
                rows.reverse()
        else:
            from yamusic_theme import sanitize_title
            kf = {"title": lambda r: sanitize_title(r["t"].get("title", "") or "").casefold(),
                  "artist": lambda r: str(r["t"].get("artist") or "").casefold(),
                  "album": lambda r: str(r["t"].get("album") or "").casefold(),
                  "duration": lambda r: float(r["t"].get("duration") or 0),
                  "plays": lambda r: int(hist.get(str(r["t"].get("path", "")), {}).get("count", 0))}[key]
            desc = self.desc if key in ("duration", "plays") else not self.desc
            rows.sort(key=kf, reverse=desc)
        self.list.set_rows(rows)
        n = self.list.model_.rowCount()
        self.count.setText(f"{n} треков" if n != 1 else "1 трек")
        msg = {"fav": "В избранном пока пусто — ♥ у трека добавит его сюда",
               "recent": "Вы ещё ничего не слушали",
               "missing": "Проверяю файлы…" if self._missing is None else "Все файлы на месте"}.get(self.filter,
                                                                                                 "Библиотека пуста")
        self.empty.setText(msg)
        self.empty.setVisible(n == 0 and not self.search.text())
        self.list.setVisible(n > 0 or bool(self.search.text()))

    def _scan_missing(self):
        self._tok += 1
        tok = self._tok
        paths = [str(t.get("path", "")) for t in self.win.library]

        def work():
            miss = set()
            for pth in paths:
                if pth and not pth.startswith(("stream:", "http")) and not Path(pth).exists():
                    miss.add(pth)
            self._bus.done.emit(tok, miss)
        threading.Thread(target=work, name="ph-missing", daemon=True).start()

    def _on_missing(self, tok, miss):
        if tok == self._tok:
            self._missing = miss
            self.refresh(force=True)

    def recheck(self):
        """Проверить файлы заново (переименовали, удалили, вернули диск)."""
        self._missing = None
        self.set_filter("missing")

    def set_filter(self, key: str):
        self.filter = key
        for k, c in self.chips.items():
            c.setChecked(k == key)
        self._save()
        self.refresh(force=True)

    def set_folder(self, folder: str | None):
        self.folder = folder
        self.folder_chip.setVisible(bool(folder))
        if folder:
            self.folder_chip.setText("  " + (Path(folder).name or folder))
        self.refresh(force=True)

    def set_sort(self, key: str):
        self.sort = key
        self._save()
        self.refresh(force=True)

    def toggle_order(self):
        self.desc = not self.desc
        self._sync_order_icon()
        self._save()
        self.refresh(force=True)

    def _sync_order_icon(self):
        self.order.setIcon(ph.icon("arrow-down-wide-narrow" if self.desc else "arrow-up-narrow-wide", 15))

    def _tab(self, key: str):
        self.stack.setCurrentIndex({"tracks": 0, "playlists": 1, "folders": 2}[key])
        if key == "playlists":
            self.refresh_playlists()
        elif key == "folders":
            self.refresh_folders()

    def refresh_playlists(self):
        from yamusic_theme import LIKED, cover_pixmap, liked_cover
        w = self.win
        items = []
        for name in self.shell.playlists_by_usage():
            pl = w.playlists.get(name) or {}
            tr = pl.get("tracks", [])
            cov = pl.get("cover") or (tr[0].get("cover", "") if tr else "")
            pm = liked_cover(40, 8) if name == LIKED and not pl.get("cover") else \
                cover_pixmap(cov, ph.px(40), ph.px(8), seed=name)
            total = sum(float(t.get("duration") or 0) for t in tr)
            items.append((name, name, f"{len(tr)} треков · {int(total // 60)} мин", pm))
        self.pl_list.set_items(items)

    def refresh_folders(self):
        counts: dict = {}
        for t in self.win.library:
            pth = str(t.get("path", ""))
            if not pth or pth.startswith(("stream:", "http")):
                continue
            d = str(Path(pth).parent)
            counts[d] = counts.get(d, 0) + 1
        items = []
        icon = ph.icon_pixmap("folder-open", 18, ph.TEXT_SECONDARY)
        for d, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            items.append((d, Path(d).name or d, f"{n} треков · {d}", icon))
        self.dir_list.set_items(items)

    def _open_playlist(self, name):
        self.shell.open_playlist(name)

    def _open_folder(self, folder):
        self.tabs.set_current("tracks", emit=True)
        if self.filter != "all":
            self.filter = "all"
            for k, c in self.chips.items():
                c.setChecked(k == "all")
        self.set_folder(folder)


class _RowList(QListWidget):
    """Простой список Phantom (плейлисты, папки): значок 40 · название · подпись; клик — открыть."""

    def __init__(self, on_open):
        super().__init__()
        self.setObjectName("PhList")
        self.on_open = on_open
        self.setItemDelegate(_RowDelegate(self))
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QListWidget#PhList{background:transparent;border:0;outline:0;}")
        self.viewport().setAutoFillBackground(False)
        self.itemClicked.connect(lambda it: self.on_open(it.data(Qt.ItemDataRole.UserRole)))

    def set_items(self, items):
        self.clear()
        for key, title, sub, pm in items:
            it = QListWidgetItem(title)
            it.setData(Qt.ItemDataRole.UserRole, key)
            it.setData(Qt.ItemDataRole.UserRole + 1, sub)
            it.setData(Qt.ItemDataRole.UserRole + 2, pm)
            self.addItem(it)


class _RowDelegate(QStyledItemDelegate):
    def sizeHint(self, opt, idx):
        return QSize(opt.rect.width(), ph.px(58))

    def paint(self, p, opt, idx):
        r = opt.rect
        hover = bool(opt.state & QStyle.StateFlag.State_MouseOver)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ph.white(.043))
            p.drawRoundedRect(QRectF(r).adjusted(0, 1, 0, -1), ph.px(10), ph.px(10))
        else:
            ph.paint_hairline(p, r.left() + ph.px(8), r.right() - ph.px(6), r.bottom())
        pm = idx.data(Qt.ItemDataRole.UserRole + 2)
        box = QRect(r.left() + ph.px(8), r.top() + (r.height() - ph.px(40)) // 2, ph.px(40), ph.px(40))
        if pm is not None and hasattr(pm, "isNull") and not pm.isNull():
            w = pm.width() / pm.devicePixelRatio()
            if w >= ph.px(36):
                p.drawPixmap(box, pm)
            else:
                p.setPen(QPen(ph.qcolor(ph.LINE_2), 1))
                p.setBrush(ph.white(.04))
                p.drawRoundedRect(QRectF(box).adjusted(.5, .5, -.5, -.5), ph.px(8), ph.px(8))
                p.drawPixmap(QPointF(box.center().x() - w / 2 + .5, box.center().y() - w / 2 + .5), pm)
        tx = box.right() + ph.px(14)
        tw = r.right() - tx - ph.px(12)
        f1 = ph.font(ph.TEXT_MD, 600)
        p.setFont(f1)
        p.setPen(ph.qcolor(ph.TEXT_PRIMARY))
        p.drawText(QRect(tx, r.top() + ph.px(10), tw, ph.px(20)), Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(f1).elidedText(str(idx.data(Qt.ItemDataRole.DisplayRole) or ""),
                                               Qt.TextElideMode.ElideRight, tw))
        f2 = ph.font(ph.TEXT_XS, 500)
        p.setFont(f2)
        p.setPen(ph.qcolor(ph.TEXT_TERTIARY))
        p.drawText(QRect(tx, r.top() + ph.px(30), tw, ph.px(18)), Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(f2).elidedText(str(idx.data(Qt.ItemDataRole.UserRole + 1) or ""),
                                               Qt.TextElideMode.ElideMiddle, tw))
        p.restore()


# ══════════════════════════════════════════════════════════════════════════ #
#  Очередь
# ══════════════════════════════════════════════════════════════════════════ #

class _NowCard(pw.PhSurface):
    """«Сейчас играет»: обложка 64 · название · исполнитель · полоса · время · ▶."""

    def __init__(self, lay):
        super().__init__("soft")
        self.lay = lay
        self.setFixedHeight(ph.px(98))
        h = QHBoxLayout(self)
        h.setContentsMargins(ph.px(12), ph.px(12), ph.px(12), ph.px(12))
        h.setSpacing(ph.px(14))
        self.cover = QLabel()
        self.cover.setFixedSize(ph.px(70), ph.px(70))
        h.addWidget(self.cover)
        c = QVBoxLayout()
        c.setSpacing(ph.px(2))
        self.title = pw.label("—", "PhHeading", font=ph.font(ph.TEXT_BASE, 650))
        self.artist = pw.label("", "PhMuted")
        c.addWidget(self.title)
        c.addWidget(self.artist)
        c.addStretch(1)
        self.seek = pw.PhSeek()
        self.seek.released.connect(lay.shell._seek_frac)
        c.addWidget(self.seek)
        tr = QHBoxLayout()
        self.t0 = pw.label("0:00", "PhMuted", font=ph.font(ph.TEXT_XS, 600, tnum=True))
        self.t1 = pw.label("0:00", "PhMuted", font=ph.font(ph.TEXT_XS, 600, tnum=True))
        tr.addWidget(self.t0)
        tr.addStretch(1)
        tr.addWidget(self.t1)
        c.addLayout(tr)
        h.addLayout(c, 1)
        self.play = pw.icon_button("play", "solid", "lg", 16, "Играть / пауза")
        self.play.clicked.connect(lay.win.toggle_play)
        h.addWidget(self.play)
        self._key = None
        self._playing = None

    def sync(self, t, playing: bool, pos: float, dur: float):
        from yamusic_theme import cover_pixmap, sanitize_title
        key = str((t or {}).get("path", ""))
        if key != self._key:
            self._key = key
            title = sanitize_title((t or {}).get("title", "") or "—")
            fm = QFontMetrics(self.title.font())
            self.title.setText(fm.elidedText(title, Qt.TextElideMode.ElideRight, max(60, self.width() - ph.px(170))))
            self.artist.setText((t or {}).get("artist") or "")
            self.cover.setPixmap(cover_pixmap((t or {}).get("cover", ""), ph.px(70), ph.px(10),
                                              seed=key or "x"))
        if playing != self._playing:
            self._playing = playing
            self.play.setIcon(ph.icon("pause" if playing else "play", 16, (5, 5, 5, 1.0), (5, 5, 5, 1.0)))
        self.seek.set_value(pos / dur if dur > 0 else 0)
        self.t0.setText(_fmt(pos))
        self.t1.setText(_fmt(dur))


class PhQueuePanel(QWidget):
    """Очередь Phantom: «Сейчас играет» + «Далее» (ваша очередь, затем порядок списка)."""

    LIMIT = 60

    def __init__(self, lay, parent=None):
        super().__init__(parent)
        self.lay = lay
        self.shell, self.win = lay.shell, lay.win
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(ph.px(12))
        v.addWidget(pw.label("Сейчас играет", "PhHeading", font=ph.font(ph.TEXT_BASE, 650)))
        self.now = _NowCard(lay)
        v.addWidget(self.now)
        hr = QHBoxLayout()
        hr.addWidget(pw.label("Далее", "PhHeading", font=ph.font(ph.TEXT_BASE, 650)))
        hr.addStretch(1)
        self.n_lbl = pw.label("", "PhMuted")
        hr.addWidget(self.n_lbl)
        self.clear_btn = pw.icon_button("trash", "ghost", "sm", 14, "Очистить вашу очередь")
        self.clear_btn.clicked.connect(self._clear)
        hr.addWidget(self.clear_btn)
        v.addLayout(hr)
        self.list = QListWidget()
        self.list.setObjectName("PhList")
        self.list.setItemDelegate(_QueueDelegate(self.list))
        self.list.setMouseTracking(True)
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setStyleSheet("QListWidget#PhList{background:transparent;border:0;outline:0;}")
        self.list.viewport().setAutoFillBackground(False)
        self.list.viewport().installEventFilter(self)
        v.addWidget(self.list, 1)
        self._sig = None

    def _entries(self):
        """[(трек, источник)]: ("q", k) — ваша очередь, ("i", ctx, i) — порядок списка."""
        w, sh = self.win, self.shell
        out = [(t, ("q", k)) for k, t in enumerate(list(getattr(w, "user_queue", []) or []))]
        try:
            qp = sh.pages.get("queue")
            ctx, cur_i, sq, sp = qp._context_view()
            tracks = w.library if ctx == "library" else w.playlists.get(ctx, {}).get("tracks", [])
            for i in qp._upcoming(tracks, cur_i, sq, sp)[:self.LIMIT]:
                out.append((tracks[i], ("i", ctx, i)))
        except Exception as e:                                 # noqa: BLE001
            print("[ph queue]", e)
        return out[:self.LIMIT + len(getattr(w, "user_queue", []) or [])]

    def refresh(self, force=False):
        ent = self._entries()
        sig = tuple((str(t.get("path", "")), src) for t, src in ent)
        sh = self.shell
        try:
            eng = self.win.engine
            pos, dur = float(eng.get_position() or 0), float(eng.duration or 0)
        except Exception:                                      # noqa: BLE001
            pos = dur = 0.0
        self.now.sync(sh.current_track(), sh.is_playing(), pos, dur)
        if not force and sig == self._sig:
            return
        self._sig = sig
        from yamusic_theme import sanitize_title
        self.list.clear()
        for n, (t, src) in enumerate(ent):
            it = QListWidgetItem(sanitize_title(t.get("title", "") or "Без названия"))
            it.setData(Qt.ItemDataRole.UserRole, (n + 1, t.get("artist") or "", float(t.get("duration") or 0),
                                                  src))
            self.list.addItem(it)
        nq = len(getattr(self.win, "user_queue", []) or [])
        total = len(ent)
        self.n_lbl.setText(f"{total} треков" + (f" · ваших {nq}" if nq else ""))
        self.clear_btn.setVisible(nq > 0)
        self.lay.overlay.subline.setText(f"{total} треков".upper() if self.lay.overlay.kind == "drawer" else "")

    def _clear(self):
        self.win.user_queue.clear()
        self.refresh(force=True)

    def eventFilter(self, obj, ev):
        from PyQt6.QtCore import QEvent
        if obj is self.list.viewport() and ev.type() == QEvent.Type.MouseButtonRelease:
            it = self.list.itemAt(ev.position().toPoint())
            if it is not None:
                _n, _a, _d, src = it.data(Qt.ItemDataRole.UserRole)
                r = self.list.visualItemRect(it)
                x_zone = QRect(r.right() - ph.px(34), r.top(), ph.px(34), r.height())
                if src[0] == "q" and x_zone.contains(ev.position().toPoint()):
                    try:
                        self.win.user_queue.pop(src[1])
                    except IndexError:
                        pass
                    self.refresh(force=True)
                    return True
                if src[0] == "i":
                    self.win._play_index(src[2], src[1])
                else:
                    q = self.win.user_queue
                    if 0 <= src[1] < len(q):
                        q.insert(0, q.pop(src[1]))
                        self.win.next_track()
                QTimer.singleShot(150, lambda: self.refresh(force=True))
                return True
        return False


class _QueueDelegate(QStyledItemDelegate):
    def sizeHint(self, opt, idx):
        return QSize(opt.rect.width(), ph.px(54))

    def paint(self, p, opt, idx):
        r = opt.rect
        n, artist, dur, src = idx.data(Qt.ItemDataRole.UserRole)
        hover = bool(opt.state & QStyle.StateFlag.State_MouseOver)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ph.white(.043))
            p.drawRoundedRect(QRectF(r).adjusted(0, 1, 0, -1), ph.px(10), ph.px(10))
        p.setFont(ph.font(ph.TEXT_XS, 600, tnum=True))
        p.setPen(ph.qcolor(ph.TEXT_TERTIARY))
        p.drawText(QRect(r.left() + ph.px(10), r.top(), ph.px(26), r.height()), Qt.AlignmentFlag.AlignVCenter,
                   f"{n:02d}")
        tx = r.left() + ph.px(42)
        tw = r.right() - tx - ph.px(100)
        f1 = ph.font(ph.TEXT_MD, 600)
        p.setFont(f1)
        p.setPen(ph.qcolor(ph.TEXT_PRIMARY))
        p.drawText(QRect(tx, r.top() + ph.px(8), tw, ph.px(20)), Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(f1).elidedText(str(idx.data(Qt.ItemDataRole.DisplayRole) or ""),
                                               Qt.TextElideMode.ElideRight, tw))
        f2 = ph.font(ph.TEXT_XS, 500)
        p.setFont(f2)
        p.setPen(ph.qcolor(ph.TEXT_TERTIARY))
        p.drawText(QRect(tx, r.top() + ph.px(28), tw, ph.px(18)), Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(f2).elidedText(artist, Qt.TextElideMode.ElideRight, tw))
        p.setFont(ph.font(ph.TEXT_SM, 600, tnum=True))
        p.setPen(ph.qcolor(ph.TEXT_SECONDARY))
        p.drawText(QRect(r.right() - ph.px(92), r.top(), ph.px(48), r.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, _fmt(dur))
        if src[0] == "q":
            xp = ph.icon_pixmap("x", 14, ph.TEXT_SECONDARY if hover else ph.TEXT_TERTIARY)
            s = xp.width() / xp.devicePixelRatio()
            p.drawPixmap(QPointF(r.right() - ph.px(22) - s / 2, r.center().y() - s / 2), xp)
        p.restore()


# ══════════════════════════════════════════════════════════════════════════ #
#  Настройки Phantom
# ══════════════════════════════════════════════════════════════════════════ #

class _Slider(QWidget):
    """Подпись и значение в строку, под ними — ползунок Phantom."""

    def __init__(self, title: str, lo: float, hi: float, value: float, fmt, on_change, step: float = 1.0):
        super().__init__()
        self.lo, self.hi, self.step, self.fmt = lo, hi, step, fmt
        v = QVBoxLayout(self)
        v.setContentsMargins(0, ph.px(6), 0, ph.px(6))
        v.setSpacing(ph.px(6))
        h = QHBoxLayout()
        h.addWidget(pw.label(title, "PhBody", font=ph.font(ph.TEXT_BASE, 550)))
        h.addStretch(1)
        self.val = pw.label("", "PhSub", font=ph.font(ph.TEXT_XS, 600, tnum=True))
        h.addWidget(self.val)
        v.addLayout(h)
        self.s = QSlider(Qt.Orientation.Horizontal)
        self.s.setObjectName("PhSlider")
        n = int(round((hi - lo) / step))
        self.s.setRange(0, n)
        self.s.setValue(int(round((value - lo) / step)))
        self.s.valueChanged.connect(self._changed)
        self.on_change = on_change
        v.addWidget(self.s)
        self._show()

    def value(self) -> float:
        return self.lo + self.s.value() * self.step

    def _show(self):
        self.val.setText(self.fmt(self.value()))

    def _changed(self, _):
        self._show()
        self.on_change(self.value())


def _switch(title: str, value: bool, on_change) -> QWidget:
    """Строка-переключатель Phantom: подпись слева, переключатель у правого края (клик по подписи — тоже)."""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, ph.px(6), 0, ph.px(6))
    lb = pw.label(title, "PhBody", font=ph.font(ph.TEXT_BASE, 550))
    h.addWidget(lb, 1)
    c = QCheckBox()
    c.setObjectName("PhSwitch")
    c.setChecked(bool(value))
    c.toggled.connect(on_change)
    h.addWidget(c)
    lb.setCursor(Qt.CursorShape.PointingHandCursor)
    lb.mousePressEvent = lambda e: c.toggle()
    w.box = c
    return w


def _segment(title: str, items, cur: str, on_change) -> QWidget:
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, ph.px(6), 0, ph.px(6))
    v.setSpacing(ph.px(8))
    v.addWidget(pw.label(title, "PhBody", font=ph.font(ph.TEXT_BASE, 550)))
    seg = pw.PhSegments(items)
    seg.set_current(cur)
    seg.changed.connect(on_change)
    v.addWidget(seg)
    return w


def _file_row(title: str, sub: str, pick_text: str, on_pick, on_reset) -> QWidget:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, ph.px(8), 0, ph.px(8))
    c = QVBoxLayout()
    c.setSpacing(ph.px(2))
    c.addWidget(pw.label(title, "PhBody", font=ph.font(ph.TEXT_BASE, 550)))
    w.sub = pw.label(sub, "PhMuted")
    c.addWidget(w.sub)
    h.addLayout(c, 1)
    b = pw.text_button(pick_text, "small")
    b.clicked.connect(on_pick)
    h.addWidget(b)
    r = pw.text_button("Сбросить", "small")
    r.clicked.connect(on_reset)
    h.addWidget(r)
    return w


class PhSettingsPanel(QScrollArea):
    """Разделы Phantom: Оформление, Текст, Виджеты. Применяются сразу."""

    def __init__(self, lay, parent=None):
        super().__init__(parent)
        self.lay = lay
        self.win = lay.win
        self.setObjectName("PhScroll")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWidget(body)
        self.viewport().setAutoFillBackground(False)
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, ph.px(10), ph.px(20))
        v.setSpacing(ph.px(2))
        s = ph_settings(self.win)

        def sect(title, reset_keys):
            hr = QHBoxLayout()
            hr.setContentsMargins(0, ph.px(14), 0, ph.px(4))
            hr.addWidget(pw.label(title, "PhHeading", font=ph.font(ph.TEXT_MD, 650)))
            hr.addStretch(1)
            rb = pw.text_button("Сбросить раздел", "ghost", "rotate-ccw")
            rb.clicked.connect(lambda: self._reset(reset_keys))
            hr.addWidget(rb)
            v.addLayout(hr)

        A = ("blur", "bg_intensity", "bg_animation", "card_opacity", "ui_scale", "effects", "cover_treatment",
             "motion", "cover_video", "cover_video_path", "bg_image", "bg_brightness")
        sect("Оформление", A)
        v.addWidget(_Slider("Интенсивность размытия", 0, 40, s["blur"], lambda x: f"{int(x)} px",
                            lambda x: self._set(blur=int(x))))
        v.addWidget(_Slider("Интенсивность фона", 0, 100, s["bg_intensity"] * 100, lambda x: f"{int(x)} %",
                            lambda x: self._set(bg_intensity=round(x / 100, 2))))
        v.addWidget(_switch("Фоновая анимация", s["bg_animation"], lambda on: self._set(bg_animation=on)))
        v.addWidget(_Slider("Прозрачность карточек", 30, 100, s["card_opacity"] * 100, lambda x: f"{int(x)} %",
                            lambda x: self._set(card_opacity=round(x / 100, 2))))
        self.scale = _Slider("Масштаб интерфейса", 80, 130, s["ui_scale"] * 100, lambda x: f"{x / 100:.2f}×",
                             lambda x: self._scale_later(round(x / 100, 2)), 5)
        v.addWidget(self.scale)
        v.addWidget(_switch("Визуальные эффекты", s["effects"], lambda on: self._set(effects=on)))
        v.addWidget(_segment("Обработка обложки", [("original", "Оригинал"), ("mono", "Монохром"),
                                                   ("dim", "Затемнение")], s["cover_treatment"],
                             lambda k: self._set(cover_treatment=k)))
        v.addWidget(_segment("Движение", [("system", "Как в системе"), ("reduce", "Уменьшенное"),
                                          ("full", "Полное")], s["motion"], lambda k: self._set(motion=k)))
        v.addWidget(_segment("Видео-обложка", [("off", "Обложка трека"), ("bundled", "Встроенное видео"),
                                               ("custom", "Своё видео")], s["cover_video"], self._video_mode))
        self.video_row = _file_row("Своё видео для обложки", Path(s["cover_video_path"]).name or "Не выбрано",
                                   "Выбрать видео", self._pick_video, lambda: self._video_path(""))
        v.addWidget(self.video_row)
        self.bg_row = _file_row("Фон приложения", Path(s["bg_image"]).name or "Встроенный фон",
                                "Выбрать изображение", self._pick_bg, lambda: self._bg(""))
        v.addWidget(self.bg_row)
        v.addWidget(_Slider("Яркость фона", 20, 160, s["bg_brightness"] * 100, lambda x: f"{int(x)} %",
                            lambda x: self._set(bg_brightness=round(x / 100, 2))))
        L = ("lyrics_scale", "lyrics_blur", "lyrics_words", "lyrics_autoscroll")
        sect("Текст песни", L)
        v.addWidget(_Slider("Размер текста", 70, 150, s["lyrics_scale"] * 100, lambda x: f"{int(x)} %",
                            lambda x: self._set(lyrics_scale=round(x / 100, 2)), 5))
        v.addWidget(_switch("Размывать неактивные строки", s["lyrics_blur"], lambda on: self._set(lyrics_blur=on)))
        v.addWidget(_switch("Подсветка слов", s["lyrics_words"], lambda on: self._set(lyrics_words=on)))
        v.addWidget(_switch("Автопрокрутка", s["lyrics_autoscroll"], lambda on: self._set(lyrics_autoscroll=on)))
        sect("Виджеты", ())
        hint = pw.label("Карточки под плеером листаются стрелками ‹ › — выбранный вид запоминается.", "PhSub")
        hint.setWordWrap(True)
        v.addWidget(hint)
        v.addStretch(1)

    def _set(self, **kw):
        set_ph(self.win, **kw)
        self.lay.apply_appearance(list(kw))

    def _scale_later(self, k: float):
        set_ph(self.win, ui_scale=k)
        t = self.__dict__.get("_scale_t")
        if t is None:
            t = self._scale_t = QTimer(self)
            t.setSingleShot(True)
            t.setInterval(900)
            t.timeout.connect(lambda: self.lay.rebuild())         # масштаб — пересборка раскладки (раз, в конце)
        t.start()

    def _reset(self, keys):
        s = self.win.settings.get("ph") or {}
        for k in keys:
            s.pop(k, None)
        self.win.settings["ph"] = s
        self.lay.rebuild()

    def _video_mode(self, k):
        if k == "custom" and not ph_settings(self.win)["cover_video_path"]:
            self._pick_video()
            if not ph_settings(self.win)["cover_video_path"]:
                return
        self._set(cover_video=k)

    def _pick_video(self):
        f, _ = QFileDialog.getOpenFileName(self, "Видео для обложки", "", "Видео (*.mp4 *.webm *.mov *.mkv *.m4v)")
        if f:
            self._video_path(f)

    def _video_path(self, f):
        set_ph(self.win, cover_video_path=f, cover_video="custom" if f else "off")
        self.video_row.sub.setText(Path(f).name if f else "Не выбрано")
        self.lay.apply_appearance(["cover_video"])

    def _pick_bg(self):
        f, _ = QFileDialog.getOpenFileName(self, "Фон приложения", "", "Изображения (*.jpg *.jpeg *.png *.webp *.bmp)")
        if f:
            self._bg(f)

    def _bg(self, f):
        self._set(bg_image=f)
        self.bg_row.sub.setText(Path(f).name if f else "Встроенный фон")


# ══════════════════════════════════════════════════════════════════════════ #
#  Настройки Phantom — карточками внутри общих настроек Echoes (SettingsHub)
# ══════════════════════════════════════════════════════════════════════════ #

HUB_ICONS = {"palette": "image", "eq": "sliders-vertical", "play": "play", "lyrics": "mic-vocal", "album": "disc-3",
             "performance": "chart-column", "settings": "settings", "net": "wifi", "dots": "ellipsis"}

# что настраивается в разделе — строкой под поиском (настройки понятнее с первого взгляда)
HUB_HINTS = {
    "look": "Как выглядит Echoes: вид, фон и стекло, обложка, тема, анимации, заглушки обложек.",
    "sound": "Как звучит музыка: эквалайзер, эффекты (bass boost, slowed, nightcore), громкость, шум.",
    "play": "Воспроизведение: онлайн-прослушивание, клипы, таймер сна, переходы между треками.",
    "lyrics": "Текст песни: вид текста, перевод, синхронизация, подсветка слов.",
    "library": "Медиатека: папки, плейлисты, теги и обложки, фильтр по настроению.",
    "performance": "Скорость и память: частота кадров, анимации, кэш, нагрузка на компьютер.",
    "tools": "Инструменты: горячие клавиши, автоматика, голосовые команды, резервная копия.",
    "apps": "Сеть и интеграции: Echoes.NET, Discord, уведомления.",
    "other": "Всё остальное.",
}


def hub_icon(name: str, size: int = 18, color: str = "#d0d0d0"):
    """Значки разделов настроек — Lucide (как у Phantom)."""
    return ph.icon(HUB_ICONS.get(name, name), 16, ph.TEXT_SECONDARY, ph.TEXT_PRIMARY, checked=ph.TEXT_PRIMARY)


class _Card(pw.PhSurface):
    """Карточка настроек Phantom: заголовок, пояснение, строки."""

    def __init__(self, title: str, hint: str):
        super().__init__("soft")
        self.setMaximumWidth(760)
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(ph.px(20), ph.px(16), ph.px(20), ph.px(14))
        self.v.setSpacing(ph.px(2))
        self.v.addWidget(pw.label(title, "PhHeading", font=ph.font(ph.TEXT_LG, 650, -.015)))
        h = pw.label(hint, "PhSub")
        h.setWordWrap(True)
        self.v.addWidget(h)
        self.v.addSpacing(ph.px(6))


def settings_cards(lay) -> list:
    """[(раздел, заголовок, виджет, слова для поиска)] — настройки вида Phantom в общих настройках."""
    win = lay.win
    s = ph_settings(win)

    def put(**kw):
        set_ph(win, **kw)
        lay.apply_appearance(list(kw))

    out = []
    c = _Card("Фон и стекло", "Картинка и живая «атмосфера» за интерфейсом, прозрачность карточек и эффекты.")
    c.v.addWidget(_Slider("Интенсивность фона", 0, 100, s["bg_intensity"] * 100, lambda x: f"{int(x)} %",
                          lambda x: put(bg_intensity=round(x / 100, 2))))
    c.v.addWidget(_Slider("Яркость фона", 20, 160, s["bg_brightness"] * 100, lambda x: f"{int(x)} %",
                          lambda x: put(bg_brightness=round(x / 100, 2))))
    c.v.addWidget(_switch("Фоновая анимация (свет, дым, пылинки)", s["bg_animation"],
                          lambda on: put(bg_animation=on)))
    flow_row = _switch("Перетекание цветов обложки", s["bg_flow"], lambda on: put(bg_flow=on))

    def cover_bg(on):
        put(bg_cover=on)
        flow_row.setEnabled(on)
    c.v.addWidget(_switch("Фон — обложка играющего трека", s["bg_cover"], cover_bg))
    flow_hint = pw.label("Размытая обложка за интерфейсом, при смене трека плавно растворяется в новой, а её цвета "
                         "медленно плывут и перетекают друг в друга.", "PhMuted")
    flow_hint.setWordWrap(True)
    c.v.addWidget(flow_hint)
    flow_row.setEnabled(s["bg_cover"])
    c.v.addWidget(flow_row)
    c.v.addWidget(_Slider("Прозрачность карточек", 30, 100, s["card_opacity"] * 100, lambda x: f"{int(x)} %",
                          lambda x: put(card_opacity=round(x / 100, 2))))
    c.v.addWidget(_Slider("Размытие под панелями", 0, 40, s["blur"], lambda x: f"{int(x)} px",
                          lambda x: put(blur=int(x))))
    c.v.addWidget(_switch("Визуальные эффекты (тени, зерно)", s["effects"], lambda on: put(effects=on)))

    def pick_bg():
        f, _ = QFileDialog.getOpenFileName(c, "Фон приложения", "", "Изображения (*.jpg *.jpeg *.png *.webp *.bmp)")
        if f:
            put(bg_image=f)
            bg_row.sub.setText(Path(f).name)

    def reset_bg():
        put(bg_image="")
        bg_row.sub.setText("Встроенный фон")
    bg_row = _file_row("Своя картинка фона", Path(s["bg_image"]).name or "Встроенный фон", "Выбрать изображение",
                       pick_bg, reset_bg)
    c.v.addWidget(bg_row)
    out.append(("look", "Фон и стекло", c, "фон картинка обои яркость анимация пылинки дым свет прозрачность "
                                           "карточек стекло размытие blur эффекты тени зерно phantom обложка "
                                           "фон из обложки цвета перетекание градиент переливы как обложка"))

    c2 = _Card("Обложка слева", "Как большая карточка над плеером показывает квадратную обложку, "
                                "и своя картинка, GIF или видео вместо неё.")
    c2.v.addWidget(_segment("Вид карточки", [("info", "Сведения"), ("blur", "Размытый фон"), ("vinyl", "Винил"),
                                             ("crop", "Обрезать")], s["cover_style"],
                            lambda k: put(cover_style=k)))
    c2.v.addWidget(_segment("Обработка обложки", [("original", "Оригинал"), ("mono", "Монохром"),
                                                  ("dim", "Затемнение")], s["cover_treatment"],
                            lambda k: put(cover_treatment=k)))
    # «Видео вместо обложки» (cover_video) теперь — правило «все треки» в списке своих обложек
    import ph_cover
    c2.v.addWidget(ph_cover.RulesEditor(lay))
    out.append(("look", "Обложка слева", c2, "обложка вид карточки сведения размытый фон винил пластинка обрезать "
                                             "своя обложка картинка фото гифка gif видео видеообложка анимированная "
                                             "трек альбом исполнитель без обложки все треки монохром чёрно-белая "
                                             "затемнение phantom"))

    c3 = _Card("Размер и движение", "Масштаб всего интерфейса и сколько в нём анимаций.")

    def scale_later(k):
        set_ph(win, ui_scale=k)
        t = c3.__dict__.get("_t")
        if t is None:
            t = c3._t = QTimer(c3)
            t.setSingleShot(True)
            t.setInterval(900)
            t.timeout.connect(lay.rebuild)
        t.start()
    c3.v.addWidget(_Slider("Масштаб интерфейса", 80, 130, s["ui_scale"] * 100, lambda x: f"{x / 100:.2f}×",
                           scale_later, 5))
    c3.v.addWidget(_segment("Движение", [("system", "Как в системе"), ("reduce", "Уменьшенное"), ("full", "Полное")],
                            s["motion"], lambda k: put(motion=k)))
    out.append(("look", "Размер и движение", c3, "масштаб размер интерфейса крупнее мельче анимации движение "
                                                 "уменьшенное плавность"))

    c4 = _Card("Текст песни справа", "Вид текста в правой колонке.")
    c4.v.addWidget(_Slider("Размер текста", 70, 150, s["lyrics_scale"] * 100, lambda x: f"{int(x)} %",
                           lambda x: put(lyrics_scale=round(x / 100, 2)), 5))
    c4.v.addWidget(_switch("Подсветка слов по ходу песни", s["lyrics_words"], lambda on: put(lyrics_words=on)))
    c4.v.addWidget(_switch("Размывать соседние строки", s["lyrics_blur"], lambda on: put(lyrics_blur=on)))
    c4.v.addWidget(_switch("Автопрокрутка за песней", s["lyrics_autoscroll"],
                           lambda on: put(lyrics_autoscroll=on)))
    out.append(("lyrics", "Текст песни справа", c4, "текст размер шрифт крупнее подсветка слов караоке размытие "
                                                    "прокрутка автопрокрутка"))
    return out


def hub_chip(text: str, icon=None):
    """Пилюля раздела настроек (вкладка в узкой панели)."""
    b = pw.chip(text)
    b.setFont(ph.font(ph.TEXT_SM, 550))
    ph.set_font(b, ph.font(ph.TEXT_SM, 550))
    b.setMinimumHeight(ph.px(30))
    if icon is not None:
        b.setIcon(icon)
        b.setIconSize(QSize(ph.px(14), ph.px(14)))
    return b


# Что в виде Phantom из общих настроек не показывается (код и сами настройки остаются — в прежнем виде всё как было):
#  * повторы: то же самое уже есть другим блоком;
#  * не к месту: цвета/скин и конструктор тем не действуют в монохромном Phantom; кнопки-переходы на страницы,
#    которые и так в меню «планеты»; действия, а не настройки.
TIDY_HIDE = {
    "Экстремальная громкость": "повтор — «Мощность звука» в разделе «Эквалайзер»",
    "Медиатека": "повтор — «Найти теги для всей музыки» и «Очистка медиатеки и кэша» отдельными блоками",
    "Оформление": "конструктор тем и цвета из обложки — не для монохромного Phantom",
    "Текст песни": "старый блок правой панели с полем текста — для этого есть строка «Редактор текста»",
    "Тема Echoes Music": "цвета скина не действуют в Phantom (у него свой монохромный скин)",
    "Конструктор тем": "отдельное приложение тем — не для Phantom",
    "Режим обложки": "действие, а не настройка (есть в «⋯» плеера)",
    "Страница профиля": "есть в меню «планеты» → Профиль",
    "Echoes.NET": "есть в меню «планеты» → Echoes.NET",
    "Палитра команд": "действие, а не настройка (Ctrl+K)",
}
TIDY_MOVE = {"Игровой оверлей": "tools"}


_SOFT_CHECKED = ("{background:rgba(255,255,255,0.13);color:#f5f5f5;border:1px solid rgba(255,255,255,0.11);}")


def _harmonize(w):
    """Карточка Echoes в общих настройках — в манере Phantom: крупные заголовки (25–28 px) — обычным
    заголовком карточки, выбранные кнопки-пилюли — мягкой подсветкой вместо белой заливки."""
    if isinstance(w, _Card):
        return
    labels = ([w] if isinstance(w, QLabel) else []) + w.findChildren(QLabel)
    for lb in labels:
        if lb.font().pixelSize() >= 19 and "color" not in lb.styleSheet():
            ph.set_font(lb, ph.font(ph.TEXT_LG + 1, 650, -.015))
    for x in [w] + w.findChildren(QWidget):                   # панель звука ставит свой QSS на свой кадр
        ss = x.styleSheet()
        if "#SndChip" in ss or "#SndBig" in ss:
            x.setStyleSheet(ss + "\nQPushButton#SndChip:checked" + _SOFT_CHECKED +
                            "\nQPushButton#SndBig:checked" + _SOFT_CHECKED)


def tidy_hub(hub):
    """Убрать из общих настроек повторы и неуместное (только в виде Phantom) и разложить по разделам."""
    gone = [w for b in hub.blocks if b.title in TIDY_HIDE for w in b.widgets]
    if gone:
        hub.remove_widgets(gone)
        for w in gone:
            try:
                w.hide()
            except RuntimeError:
                pass
    for b in hub.blocks:
        if b.title in TIDY_MOVE:
            b.cat = TIDY_MOVE[b.title]
    for b in hub.blocks:                                       # одна манера у всех карточек
        for w in b.widgets:
            try:
                _harmonize(w)
            except RuntimeError:
                pass
    try:                                                       # лупа в поле поиска, как у Phantom
        from PyQt6.QtWidgets import QLineEdit
        if not hub.search.actions():
            hub.search.addAction(ph.icon("search", 15, ph.TEXT_TERTIARY), QLineEdit.ActionPosition.LeadingPosition)
        hub.search.setStyleSheet(ph.font_css(ph.font(ph.TEXT_SM, 450)) + " padding-left:6px;")
    except Exception as e:                                     # noqa: BLE001
        print("[ph] search icon:", e)
    QTimer.singleShot(0, hub.refresh)
