"""Раздел «Подписки»: исполнители, на которых вы подписаны (фото, аудитория, «Отписаться»), и окошко
«Уведомления» — новые релизы подписок (artist_follow)."""
from __future__ import annotations

import threading

from PyQt6.QtCore import Qt, QSize, QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDialog, QListWidget,
                             QListWidgetItem, QFrame)

import artist_follow as AF


class _Pics(QObject):
    done = pyqtSignal(str, str)                                # имя, путь к фото


def _pic_of(name) -> str:
    try:
        import artist_net
        c = artist_net.cached(name) or {}
        return c.get("picture") or artist_net.cached_image(c.get("picture_url") or c.get("wiki_img") or "") or ""
    except Exception:                                          # noqa: BLE001
        return ""


class FollowTile(QWidget):
    """Плитка исполнителя: круглое фото, имя, аудитория, «Отписаться»."""

    def __init__(self, page, name):
        super().__init__()
        from yamusic_theme import Card
        self.page, self.name = page, name
        self.setFixedWidth(170)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        sub = ""
        try:
            import artist_net
            n, what = artist_net.audience(artist_net.cached(name) or {})
            if n:
                sub = f"{artist_net.human(n)} {what}"
        except Exception:                                      # noqa: BLE001
            pass
        self.card = Card(name, sub or "Исполнитель", _pic_of(name), 150, circle=True, seed=name)
        self.card.clicked.connect(lambda: page.shell.open_artist(name))
        v.addWidget(self.card, 0, Qt.AlignmentFlag.AlignHCenter)
        un = QPushButton("Отписаться")
        un.setObjectName("YaChip")
        un.setCursor(Qt.CursorShape.PointingHandCursor)
        un.setStyleSheet("QPushButton{border-radius:14px;padding:5px 14px;}")
        un.clicked.connect(lambda: AF.set_follow(page.shell.win, name, False))
        v.addWidget(un, 0, Qt.AlignmentFlag.AlignHCenter)
        # высота плитки задана жёстко: сетка не может её сжать, и круг не наезжает на имя и кнопку
        self.setFixedHeight(self.card.height() + v.spacing() + max(30, un.sizeHint().height()) + 4)


class FollowsPage(QWidget):
    def __init__(self, shell):
        super().__init__()
        from yamusic_theme import CardGrid, ya_icon
        self.shell = shell
        self.setObjectName("YaPage")
        v = QVBoxLayout(self)
        v.setContentsMargins(32, 22, 32, 16)
        v.setSpacing(12)
        head = QHBoxLayout()
        t = QLabel("Подписки")
        t.setStyleSheet("font-size:30px;font-weight:900;background:transparent;")
        head.addWidget(t)
        self.count = QLabel("")
        self.count.setObjectName("YaSub")
        head.addWidget(self.count, 0, Qt.AlignmentFlag.AlignBottom)
        head.addStretch(1)
        self.b_check = QPushButton("  Проверить релизы")
        self.b_check.setIcon(ya_icon("repeat", 16, "#e6e6e6"))
        self.b_check.setToolTip("Сейчас посмотреть, не вышло ли нового у ваших исполнителей")
        self.b_check.clicked.connect(self._check)
        head.addWidget(self.b_check)
        self.b_notif = QPushButton("  Уведомления")
        self.b_notif.setObjectName("AccentBtn")
        self.b_notif.setIcon(ya_icon("bell", 16, "#000000"))
        self.b_notif.clicked.connect(self.open_notifications)
        head.addWidget(self.b_notif)
        v.addLayout(head)
        self.hint = QLabel("Вы пока ни на кого не подписаны. Нажмите «Подписаться» в карточке «Об исполнителе» "
                           "или на странице исполнителя — его новые релизы будут приходить уведомлениями.")
        self.hint.setObjectName("YaSub")
        self.hint.setWordWrap(True)
        v.addWidget(self.hint)
        self.grid = CardGrid()
        v.addWidget(self.grid, 1)
        self.pics = _Pics(self)
        self.pics.done.connect(self._pic_ready)
        AF.bus().changed.connect(self.refresh)
        self._sig = None

    def refresh(self, force=False):
        win = self.shell.win
        names = list(reversed(AF.followed(win)))               # новые подписки — первыми
        n_new = AF.unread(win)
        self.b_notif.setText(f"  Уведомления · {n_new}" if n_new else "  Уведомления")
        self.count.setText(f"{len(names)}" if names else "")
        self.hint.setVisible(not names)
        sig = tuple(names)
        if sig == self._sig and not force:
            return
        self._sig = sig
        tiles = [FollowTile(self, n) for n in names]
        self.grid.set_cards(tiles)
        missing = [n for n in names if not _pic_of(n)]
        if missing:
            threading.Thread(target=self._load, args=(missing,), daemon=True).start()

    def _load(self, names):
        key = str((self.shell.win.settings or {}).get("lastfm_key", "") or "")
        for n in names:
            try:
                import artist_net
                d = artist_net.fetch_artist(n, key, images=False)
                p = d.get("picture") or artist_net.cached_image(d.get("picture_url") or "")
                if p:
                    self.pics.done.emit(n, p)
            except Exception:                                  # noqa: BLE001
                pass

    def _pic_ready(self, name, path):
        for c in self.grid.cards:
            if getattr(c, "name", None) == name:
                c.card.cover = path
                c.card.update()

    def _check(self):
        self.b_check.setEnabled(False)
        self.b_check.setText("  Проверяю…")
        AF.check_now(self.shell.win)
        QTimer.singleShot(8000, lambda: (self.b_check.setEnabled(True),
                                         self.b_check.setText("  Проверить релизы")))

    def open_notifications(self):
        d = ReleasesDialog(self.shell, self)
        d.exec()
        AF.mark_read(self.shell.win)
        self.refresh()


class ReleasesDialog(QDialog):
    """Окошко «Уведомления»: последние релизы подписок (новые отмечены)."""

    def __init__(self, shell, parent=None):
        super().__init__(parent)
        self.shell = shell
        self.setWindowTitle("Уведомления · новые релизы")
        self.setMinimumSize(520, 520)
        v = QVBoxLayout(self)
        v.setSpacing(10)
        feed = AF.feed(shell.win)
        if not feed:
            e = QLabel("Пока пусто. Когда у исполнителей из «Подписок» выйдет альбом, сингл или EP, "
                       "он появится здесь и придёт уведомлением в углу экрана.")
            e.setObjectName("YaSub")
            e.setWordWrap(True)
            v.addWidget(e)
        self.lst = QListWidget()
        self.lst.setIconSize(QSize(54, 54))
        self.lst.setStyleSheet("QListWidget{background:transparent;border:none;}"
                               "QListWidget::item{padding:6px;border-radius:10px;}"
                               "QListWidget::item:hover{background:rgba(255,255,255,0.06);}")
        self.lst.itemClicked.connect(self._open)
        v.addWidget(self.lst, 1)
        from yamusic_theme import cover_pixmap
        self._items = {}
        for r in feed[:120]:
            path = ""
            try:
                import artist_net
                path = artist_net.cached_image(r.get("cover_url") or "")
            except Exception:                                  # noqa: BLE001
                pass
            mark = "●  " if r.get("new") else ""
            date = r.get("date") or ""
            it = QListWidgetItem(QPixmapIcon(cover_pixmap(path, 54, 8, seed=r.get("title", ""))),
                                 f"{mark}{r.get('title', '')}\n{r.get('artist', '')} · {r.get('type', 'Релиз')}"
                                 + (f" · {date}" if date else ""))
            it.setData(Qt.ItemDataRole.UserRole, r.get("artist", ""))
            if r.get("new"):
                f = QFont(it.font())
                f.setBold(True)
                it.setFont(f)
            self.lst.addItem(it)
            if not path and r.get("cover_url"):
                self._items[r["cover_url"]] = it
        self._pics = _Pics(self)
        self._pics.done.connect(self._cover_ready)
        if self._items:
            threading.Thread(target=self._covers, daemon=True).start()

    def _covers(self):
        for url in list(self._items):
            try:
                import artist_net
                p = artist_net.image(url)
                if p:
                    self._pics.done.emit(url, p)
            except Exception:                                  # noqa: BLE001
                pass

    def _cover_ready(self, url, path):
        it = self._items.get(url)
        if it is not None:
            from yamusic_theme import cover_pixmap
            try:
                it.setIcon(QPixmapIcon(cover_pixmap(path, 54, 8)))
            except RuntimeError:
                pass

    def _open(self, it):
        name = it.data(Qt.ItemDataRole.UserRole)
        self.accept()
        if name:
            self.shell.open_artist(name)


def QPixmapIcon(pm):
    from PyQt6.QtGui import QIcon
    return QIcon(pm)
