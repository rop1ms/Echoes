"""Personal music tier board, with virtualized track views and the existing ECHOES player."""
from __future__ import annotations

import data_home
import json
import math
from pathlib import Path
import re

from PyQt6.QtCore import QAbstractListModel, QEvent, QMimeData, QModelIndex, QRect, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QDrag, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QListView, QMenu, QMessageBox, QPushButton,
    QScrollArea, QSizePolicy, QSlider, QStyledItemDelegate, QStyle, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView, QInputDialog,
)

from tier_store import TierStore, track_key as _store_key

MIME = "application/x-echoes-tier-tracks"
ROLE = Qt.ItemDataRole.UserRole


def track_key(path):
    try:
        return _store_key(path)
    except (ValueError, TypeError):
        return ""



def _ph() -> bool:
    try:
        import ya_skin
        return bool(ya_skin.PHANTOM_ON)
    except Exception:                                          # noqa: BLE001
        return False


def _tone(color: str) -> str:
    """Вид Phantom — монохром: цвет уровня становится серым той же яркости (уровни различимы, цвета нет)."""
    if not _ph():
        return color
    q = QColor(color)
    v = max(40, min(245, int(.299 * q.red() + .587 * q.green() + .114 * q.blue())))
    import ph_style                                            # серый с оттенком картинки фона
    return ph_style.tone(v).name()

class TierTrackModel(QAbstractListModel):
    def __init__(self, page, tier_id, parent):
        super().__init__(parent)
        self.page, self.tier_id, self.tracks = page, tier_id, []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.tracks)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.tracks):
            return None
        t = self.tracks[index.row()]
        if role == ROLE:
            return t
        if role == Qt.ItemDataRole.DisplayRole:
            return t.get("title") or Path(str(t.get("path", ""))).stem
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{t.get('artist') or 'Без исполнителя'} — {self.data(index)}\nДвойной щелчок — слушать; перетащите в уровень"
        return None

    def flags(self, index):
        return (Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled
                if index.isValid() else Qt.ItemFlag.ItemIsDropEnabled)

    def set_tracks(self, tracks):
        self.beginResetModel()
        self.tracks = tracks
        self.endResetModel()


class TrackTile(QStyledItemDelegate):
    def paint(self, painter, option, index):
        import yamusic_theme as Y
        t = index.data(ROLE) or {}
        page = index.model().page
        r = option.rect.adjusted(3, 3, -3, -3)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        focused = track_key(t.get("path", "")) == page.selected
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.setPen(QPen(QColor(Y.YELLOW), 2) if focused else QPen(QColor(_tone("#c3ad54")), 1) if selected
                       else Qt.PenStyle.NoPen)
        painter.setBrush(QColor(_tone("#302c1b") if focused else _tone("#363020") if selected else "#232323"))
        painter.drawRoundedRect(r, 9, 9)
        cover = QRect(r.left() + 6, r.top() + 5, 30, 30)
        painter.drawPixmap(cover, Y.cover_pixmap(t.get("cover") or "", 30, 6,
                                                seed=str(t.get("path") or ""), lazy=option.widget))
        painter.setFont(Y.ya_font(11, QFont.Weight.DemiBold))
        painter.setPen(QColor("#ffffff"))
        title = t.get("title") or Path(str(t.get("path", ""))).stem
        painter.drawText(QRect(r.left() + 44, r.top() + 3, r.width() - 52, 18),
                         Qt.AlignmentFlag.AlignVCenter, painter.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, r.width() - 52))
        painter.setFont(Y.ya_font(10))
        painter.setPen(QColor("#a2a2a2"))
        painter.drawText(QRect(r.left() + 44, r.top() + 21, r.width() - 52, 16),
                         Qt.AlignmentFlag.AlignVCenter, painter.fontMetrics().elidedText(
                             t.get("artist") or "Без исполнителя", Qt.TextElideMode.ElideRight, r.width() - 52))
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(192, 46)


class TierView(QListView):
    def __init__(self, page, tier_id):
        super().__init__()
        self.page, self.tier_id = page, tier_id
        self.model_ = TierTrackModel(page, tier_id, self)
        self.setModel(self.model_)
        self.setItemDelegate(TrackTile(self))
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setUniformItemSizes(True)
        self.setGridSize(QSize(192, 46))
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QListView{background:transparent;border:none;outline:none;}")
        self.selectionModel().currentChanged.connect(lambda ix, _old: page.select_track(ix.data(ROLE)))
        self.clicked.connect(lambda ix: page.select_track(ix.data(ROLE)))
        self.doubleClicked.connect(lambda ix: page.play_track(ix.data(ROLE)))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.menu)
        self.setAccessibleName("Не оценено" if tier_id is None else "Треки уровня")

    def startDrag(self, actions):
        paths = [ix.data(ROLE).get("path", "") for ix in self.selectedIndexes()]
        if not paths:
            return
        mime = QMimeData()
        mime.setData(MIME, json.dumps(paths, ensure_ascii=False).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME):
            self.setStyleSheet(f"QListView{{background:{_tone('#29251a')};border:2px solid {_tone('#ffdb1a')};"
                               "border-radius:9px;outline:none;}")
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.model_.rowCount():
            painter = QPainter(self.viewport())
            painter.setPen(QColor("#747474"))
            painter.drawText(self.viewport().rect().adjusted(12, 4, -12, -4), Qt.AlignmentFlag.AlignCenter,
                             "Нет треков по запросу" if self.page.search.text().strip() else "Перетащите трек сюда")
            painter.end()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        self.setStyleSheet("QListView{background:transparent;border:none;outline:none;}")
        if not event.mimeData().hasFormat(MIME):
            return
        try:
            paths = json.loads(bytes(event.mimeData().data(MIME)).decode("utf-8"))
            if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
                return
            if self.page.move_paths(paths, self.tier_id):
                event.setDropAction(Qt.DropAction.MoveAction)
                event.accept()
        except (ValueError, UnicodeError):
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet("QListView{background:transparent;border:none;outline:none;}")
        event.accept()

    def menu(self, pos):
        index = self.indexAt(pos)
        if index.isValid() and index not in self.selectedIndexes():
            self.setCurrentIndex(index)
        tracks = [ix.data(ROLE) for ix in self.selectedIndexes()]
        if not tracks:
            return
        m = QMenu(self)
        m.addAction("Слушать", lambda: self.page.play_track(tracks[0]))
        m.addSeparator()
        for tier in self.page.store.tiers:
            m.addAction(tier["name"], lambda _=False, tier=tier: self.page.move_paths([t["path"] for t in tracks], tier["id"]))
        m.addAction("Убрать оценку", lambda: self.page.move_paths([t["path"] for t in tracks], None))
        m.exec(self.viewport().mapToGlobal(pos))


class TierRow(QFrame):
    def __init__(self, page, tier):
        super().__init__()
        self.setObjectName("TierRow")
        self.setAcceptDrops(True)
        self.setStyleSheet("QFrame#TierRow{background:#191919;border-radius:12px;}")
        self.page = page
        self.tier_id = tier["id"] if tier else None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 6, 0)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setFixedWidth(78)
        self.label.setAcceptDrops(True)
        self.label.installEventFilter(self)
        layout.addWidget(self.label)
        right = QVBoxLayout()
        right.setContentsMargins(4, 4, 0, 4)
        self.count = QLabel()
        self.count.setStyleSheet("color:#888;font-size:11px;background:transparent;")
        right.addWidget(self.count)
        self.count.setVisible(tier is None)
        self.view = TierView(page, self.tier_id)
        right.addWidget(self.view)
        layout.addLayout(right, 1)
        self.configure(tier)

    def configure(self, tier):
        name, color = (tier["name"], tier["color"]) if tier else ("Не оценено", "#3b3b3b")
        color = _tone(color)
        q = QColor(color)
        light = .299*q.red() + .587*q.green() + .114*q.blue() > 150
        self.label.setText(name)
        self.label.setToolTip(name + ("\nДвойной щелчок — переименовать уровень" if tier else ""))
        self.label.setStyleSheet(f"background:{color};color:{'#101010' if light else '#fff'};font-size:14px;font-weight:800;border-radius:10px;padding:7px;")
        self.view.setAccessibleName(name)

    def set_tracks(self, tracks, total):
        import yamusic_theme as Y
        self.view.model_.set_tracks(tracks)
        self.count.setText(f"{total} {Y._plural(total, 'трек', 'трека', 'треков')}" + (f" · найдено {len(tracks)}" if len(tracks) != total else ""))
        self.resize_tiles()

    def resize_tiles(self):
        columns = max(1, self.view.viewport().width() // 192)
        lines = max(1, math.ceil(self.view.model_.rowCount() / columns))
        self.view.setFixedHeight(min(2 if self.tier_id is None else 1, lines) * 46 + 4)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resize_tiles()

    def dragEnterEvent(self, event):
        self.view.dragEnterEvent(event)

    def dragMoveEvent(self, event):
        self.view.dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self.view.dragLeaveEvent(event)

    def dropEvent(self, event):
        self.view.dropEvent(event)

    def eventFilter(self, obj, event):
        if obj is self.label:
            if event.type() == QEvent.Type.MouseButtonDblClick and self.tier_id is not None:
                self.page.rename_tier(self.tier_id)
                return True
            handler = {QEvent.Type.DragEnter: self.dragEnterEvent, QEvent.Type.DragMove: self.dragMoveEvent,
                       QEvent.Type.DragLeave: self.dragLeaveEvent, QEvent.Type.Drop: self.dropEvent}.get(event.type())
            if handler:
                handler(event)
                return True
        return super().eventFilter(obj, event)


class TierEditor(QDialog):
    def __init__(self, tiers, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Уровни тирлиста")
        self.resize(520, 440)
        layout = QVBoxLayout(self)
        note = QLabel("Задайте названия, цвета и порядок уровней. При удалении уровня его треки вернутся в «Не оценено».")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Название уровня", "Цвет"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        for tier in tiers:
            self.add_row(tier)
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        for name, fn in (("+ Уровень", lambda: self.add_row()), ("Удалить", self.remove_row),
                         ("↑", lambda: self.move(-1)), ("↓", lambda: self.move(1)), ("Выбрать цвет", self.choose_color)):
            b = QPushButton(name)
            b.clicked.connect(fn)
            actions.addWidget(b)
        layout.addLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.result_tiers = []

    def add_row(self, tier=None):
        if self.table.rowCount() >= 64:
            return
        row = self.table.rowCount()
        self.table.insertRow(row)
        name = QTableWidgetItem(tier["name"] if tier else "Новый уровень")
        name.setData(ROLE, tier.get("id") if tier else None)
        self.table.setItem(row, 0, name)
        self.table.setItem(row, 1, QTableWidgetItem(tier["color"] if tier else "#b6a0e8"))
        self.table.selectRow(row)

    def remove_row(self):
        row = self.table.currentRow()
        if row >= 0 and self.table.rowCount() > 1:
            self.table.removeRow(row)

    def move(self, delta):
        row, other = self.table.currentRow(), self.table.currentRow() + delta
        if row < 0 or not 0 <= other < self.table.rowCount():
            return
        items = [self.table.takeItem(row, c) for c in range(2)]
        others = [self.table.takeItem(other, c) for c in range(2)]
        for c in range(2):
            self.table.setItem(row, c, others[c])
            self.table.setItem(other, c, items[c])
        self.table.selectRow(other)

    def choose_color(self):
        row = self.table.currentRow()
        if row < 0:
            return
        color = QColorDialog.getColor(QColor(self.table.item(row, 1).text()), self, "Цвет уровня")
        if color.isValid():
            self.table.item(row, 1).setText(color.name())

    def accept(self):
        tiers = []
        for row in range(self.table.rowCount()):
            name, color = self.table.item(row, 0).text().strip(), self.table.item(row, 1).text().strip()
            if not name or len(name) > 100 or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                QMessageBox.warning(self, "Проверьте уровень", "Укажите название (1–100 символов) и цвет в формате #RRGGBB.")
                return
            tier = {"name": name, "color": color}
            if self.table.item(row, 0).data(ROLE):
                tier["id"] = self.table.item(row, 0).data(ROLE)
            tiers.append(tier)
        self.result_tiers = tiers
        super().accept()


class MusicTierPage(QWidget):
    def __init__(self, shell):
        super().__init__()
        import yamusic_theme as Y
        self.shell, self.win = shell, shell.win
        self.setObjectName("YaPage")
        self.store = TierStore(getattr(self.win, "tierlist_path", data_home.root() / "music_tierlist.json"))
        self.selected = ""
        self.tracks, self.by_key = [], {}
        self.undo_stack, self.redo_stack = [], []
        self.rows = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 12)
        layout.setSpacing(12)
        header = QHBoxLayout()
        title = QLabel("Тирлист музыки")
        title.setObjectName("YaH1")
        header.addWidget(title)
        header.addStretch()
        add = QPushButton("+ Новый уровень")
        add.clicked.connect(self.add_tier)
        header.addWidget(add)
        edit = QPushButton("Настроить уровни")
        edit.setObjectName("YaYellow")
        edit.clicked.connect(self.edit_tiers)
        header.addWidget(edit)
        layout.addLayout(header)
        self.summary = QLabel()
        self.summary.setObjectName("YaSub")
        layout.addWidget(self.summary)
        tip = QLabel("Выберите трек и послушайте его перед оценкой. Перетащите в уровень или нажмите уровень в закреплённой панели. Название уровня можно изменить двойным щелчком.")
        tip.setObjectName("YaSub")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по названию или исполнителю")
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(150)
        self.search_timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda _: self.search_timer.start())
        controls.addWidget(self.search, 1)
        self.only_unrated = QCheckBox("Только без оценки")
        self.only_unrated.toggled.connect(lambda _: self.refresh())
        controls.addWidget(self.only_unrated)
        self.undo_button = QPushButton("↶")
        self.undo_button.setToolTip("Отменить последнюю оценку или изменение уровней")
        self.undo_button.clicked.connect(self.undo)
        controls.addWidget(self.undo_button)
        self.redo_button = QPushButton("↷")
        self.redo_button.setToolTip("Повторить")
        self.redo_button.clicked.connect(self.redo)
        controls.addWidget(self.redo_button)
        layout.addLayout(controls)
        self.quick_rating = QComboBox()
        self.quick_rating.setMinimumWidth(150)
        self.quick_rating.setMaximumWidth(240)
        self.quick_rating.setToolTip("Оценить выбранный трек без прокрутки тирлиста")
        self.quick_rating.activated.connect(lambda i: self.rate_selected(self.quick_rating.itemData(i)))
        controls.addWidget(self.quick_rating)
        player = QFrame()
        player.setStyleSheet("QFrame{background:#1b1b1b;border-radius:12px;}")
        pv = QVBoxLayout(player)
        playbar = QHBoxLayout()
        self.cover = Y.RoundCover(52, 8)
        playbar.addWidget(self.cover)
        names = QVBoxLayout()
        self.track_title = QLabel("Выберите трек на тирлисте")
        self.track_title.setWordWrap(True)
        self.track_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.track_title.setMaximumHeight(60)
        self.track_title.setStyleSheet("font-size:15px;font-weight:700;")
        self.track_artist = QLabel("Оценки сохраняются автоматически")
        self.track_artist.setWordWrap(True)
        self.track_artist.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.track_artist.setMaximumHeight(44)
        self.track_artist.setObjectName("YaSub")
        names.addWidget(self.track_title)
        names.addWidget(self.track_artist)
        playbar.addLayout(names, 1)
        self.play_button = QPushButton("▶ Слушать")
        self.play_button.clicked.connect(lambda: self.play_track(self.by_key.get(self.selected)))
        playbar.addWidget(self.play_button)
        nxt = QPushButton("Следующий без оценки →")
        nxt.clicked.connect(self.next_unrated)
        playbar.addWidget(nxt)
        pv.addLayout(playbar)
        seekbar = QHBoxLayout()
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 1000)
        self.seek.sliderReleased.connect(self.seek_track)
        seekbar.addWidget(self.seek, 1)
        self.time = QLabel("0:00 / 0:00")
        seekbar.addWidget(self.time)
        pv.addLayout(seekbar)
        rating_widget = QWidget()
        rating_widget.setStyleSheet("background:transparent;")
        self.rating_bar = QHBoxLayout(rating_widget)
        self.rating_bar.setContentsMargins(0, 0, 0, 0)
        rating_scroll = QScrollArea()
        rating_scroll.setFrameShape(QFrame.Shape.NoFrame)
        rating_scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        rating_scroll.setWidgetResizable(True)
        rating_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rating_scroll.setFixedHeight(56)
        rating_scroll.setWidget(rating_widget)
        pv.addWidget(rating_scroll)
        layout.addWidget(player)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.inner = QWidget()
        self.board = QVBoxLayout(self.inner)
        self.board.setContentsMargins(0, 0, 0, 0)
        self.board.setSpacing(5)
        self.scroll.setWidget(self.inner)
        layout.addWidget(self.scroll, 1)
        self.status = QLabel(self.store.load_error or "Все оценки сохраняются автоматически")
        self.status.setObjectName("YaSub")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self._build_rows()
        self.refresh()
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def _build_rows(self):
        while self.board.count():
            item = self.board.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.rows = {}
        for tier in self.store.tiers + [None]:
            row = TierRow(self, tier)
            self.rows[row.tier_id] = row
            self.board.addWidget(row)
        self.board.addStretch(1)
        while self.rating_bar.count():
            item = self.rating_bar.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.quick_rating.clear()
        self.quick_rating.addItem("Убрать оценку", None)
        for tier in self.store.tiers:
            self.quick_rating.addItem(tier["name"], tier["id"])
            button = QPushButton(tier["name"])
            button.setToolTip("Оценить выбранный трек: " + tier["name"])
            color = QColor(_tone(tier["color"]))
            ink = "#101010" if color.lightness() > 150 else "#ffffff"
            button.setStyleSheet(f"QPushButton{{background:{color.name()};color:{ink};border-radius:9px;padding:7px 12px;font-weight:700;}}")
            button.clicked.connect(lambda _=False, tid=tier["id"]: self.rate_selected(tid))
            self.rating_bar.addWidget(button)
        unrate = QPushButton("Убрать оценку")
        unrate.clicked.connect(lambda: self.rate_selected(None))
        self.rating_bar.addWidget(unrate)
        self.rating_bar.addStretch()

    def refresh(self):
        # открыли вкладку, а ничего не менялось — не пересобирать ~650 треков (было ~150 мс на каждый заход)
        try:
            sig = (len(self.win.library), hash(frozenset(self.store.assignments.items())),
                   self.search.text(), self.only_unrated.isChecked(), str(self.store.tiers),
                   self.selected)
        except Exception:                                      # noqa: BLE001
            sig = None
        if sig is not None and sig == self.__dict__.get("_refresh_sig"):
            return
        self._refresh_sig = sig
        self.tracks, self.by_key = [], {}
        for t in self.win.library:
            if not t.get("path"):
                continue
            key = track_key(t["path"])
            if not key:
                continue
            if key in self.by_key:
                continue
            self.tracks.append(t)
            self.by_key[key] = t
        if self.selected not in self.by_key:
            self.selected = ""
        assignments = self.store.assignments
        query = self.search.text().strip().casefold()
        groups = {key: [] for key in self.rows}
        totals = {key: 0 for key in self.rows}
        rated = 0
        for t in self.tracks:
            tid = assignments.get(track_key(t["path"]))
            if tid not in groups:
                tid = None
            rated += tid is not None
            totals[tid] += 1
            if query and not all(word in f"{t.get('title', '')} {t.get('artist', '')}".casefold() for word in query.split()):
                continue
            groups[tid].append(t)
        for tid, row in self.rows.items():
            row.setVisible(not (self.only_unrated.isChecked() and tid is not None))
            row.set_tracks(groups[tid], totals[tid])
        self.summary.setText(f"Оценено {rated} из {len(self.tracks)} · без оценки {len(self.tracks) - rated}")
        self.undo_button.setEnabled(bool(self.undo_stack))
        self.redo_button.setEnabled(bool(self.redo_stack))
        self.show_selected()

    def show_selected(self):
        t = self.by_key.get(self.selected)
        if t is None:
            self.track_title.setText("Выберите трек на тирлисте" if self.tracks else "В коллекции пока нет музыки")
            self.track_artist.setText("Добавьте музыку в коллекцию, чтобы составить тирлист" if not self.tracks else "Перетаскивайте треки или оценивайте кнопками уровней")
            self.cover.set_cover("", "empty")
        else:
            self.track_title.setText(t.get("title") or Path(t["path"]).stem)
            tid = self.store.tier_for(t["path"])
            name = next((tier["name"] for tier in self.store.tiers if tier["id"] == tid), "Не оценено")
            self.track_artist.setText(f"{t.get('artist') or 'Без исполнителя'} · {name}")
            self.cover.set_cover(t.get("cover") or "", t["path"])
        self.quick_rating.setEnabled(t is not None)
        self.quick_rating.setCurrentIndex(max(0, self.quick_rating.findData(self.store.tier_for(t["path"]) if t else None)))
        self.play_button.setEnabled(t is not None)
        for view in self.findChildren(TierView):
            view.viewport().update()
        self.tick()

    def select_track(self, track):
        if track:
            key = track_key(track["path"])
            if key == self.selected:
                return
            self.selected = key
            self.show_selected()

    def play_track(self, track):
        if not track:
            return
        self.select_track(track)
        current = self.win._current_track()
        if current and track_key(current.get("path", "")) == self.selected:
            self.win.toggle_play()
        else:
            index = next((i for i, t in enumerate(self.win.library) if track_key(t.get("path", "")) == self.selected), -1)
            if index >= 0:
                self.win._play_index(index, "library")
        self.tick()

    def next_unrated(self):
        candidates = self.rows[None].view.model_.tracks
        if not candidates:
            self.status.setText("Нет неоценённых треков по этому запросу." if self.search.text().strip() else
                                "Все треки оценены. Можно добавить музыку или изменить любую оценку.")
            return
        keys = [track_key(t["path"]) for t in candidates]
        next_index = (keys.index(self.selected) + 1) % len(candidates) if self.selected in keys else 0
        self.select_track(candidates[next_index])
        row = self.rows[None]
        self.scroll.ensureWidgetVisible(row)
        match = next((i for i, t in enumerate(row.view.model_.tracks) if track_key(t["path"]) == self.selected), -1)
        if match >= 0:
            index = row.view.model_.index(match)
            row.view.setCurrentIndex(index)
            row.view.scrollTo(index)

    def _commit(self, fn, rebuild=False):
        before = self.store.snapshot()
        try:
            fn()
        except (ValueError, OSError) as exc:
            self.status.setText(f"Не удалось сохранить тирлист: {exc}")
            return False
        if self.store.snapshot() != before:
            self.undo_stack.append(before)
            self.undo_stack = self.undo_stack[-60:]
            self.redo_stack.clear()
        if rebuild:
            self._build_rows()
        self.refresh()
        self.status.setText("Сохранено")
        return True

    def move_paths(self, paths, tier_id):
        valid = {path: tier_id for path in paths if track_key(path) in self.by_key}
        if not valid:
            return False
        return self._commit(lambda: self.store.bulk_assign(valid))

    def rate_selected(self, tier_id):
        t = self.by_key.get(self.selected)
        if t:
            self.move_paths([t["path"]], tier_id)
        else:
            self.status.setText("Сначала выберите трек")

    def add_tier(self):
        if len(self.store.tiers) >= 64:
            self.status.setText("Можно создать до 64 уровней")
            return
        name, ok = QInputDialog.getText(self, "Новый уровень", "Название уровня:")
        if ok and name.strip():
            tiers = self.store.tiers + [{"name": name.strip(), "color": "#b6a0e8"}]
            self._commit(lambda: self.store.update_tiers(tiers), rebuild=True)

    def rename_tier(self, tier_id):
        tiers = self.store.tiers
        tier = next((t for t in tiers if t["id"] == tier_id), None)
        if tier is None:
            return
        name, ok = QInputDialog.getText(self, "Переименовать уровень", "Название уровня:", text=tier["name"])
        if ok and name.strip():
            tier["name"] = name.strip()
            self._commit(lambda: self.store.update_tiers(tiers), rebuild=True)

    def edit_tiers(self):
        dialog = TierEditor(self.store.tiers, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._commit(lambda: self.store.update_tiers(dialog.result_tiers), rebuild=True)

    def _history(self, source, target):
        if not source:
            return
        before, state = self.store.snapshot(), source[-1]
        try:
            self.store.restore(state)
        except (ValueError, OSError) as exc:
            self.status.setText(f"Не удалось сохранить тирлист: {exc}")
            return
        source.pop()
        target.append(before)
        self._build_rows()
        self.refresh()
        self.status.setText("Сохранено")

    def undo(self):
        self._history(self.undo_stack, self.redo_stack)

    def redo(self):
        self._history(self.redo_stack, self.undo_stack)

    def tick(self):
        if not self.isVisible():
            return
        current = self.win._current_track()
        mine = current and self.selected and track_key(current.get("path", "")) == self.selected
        engine = self.win.engine
        duration = float((engine.duration if mine else (self.by_key.get(self.selected) or {}).get("duration", 0)) or 0)
        position = max(0., float(engine.get_position() or 0)) if mine else 0.
        self.seek.setEnabled(bool(mine and duration > 0))
        if not self.seek.isSliderDown():
            self.seek.setValue(int(min(1., position/duration)*1000) if duration > 0 else 0)
        fmt = lambda s: f"{int(s)//60}:{int(s)%60:02d}"
        self.time.setText(f"{fmt(position)} / {fmt(duration)}")
        self.play_button.setText("Ⅱ Пауза" if mine and engine.is_playing() else "▶ Слушать")

    def seek_track(self):
        current = self.win._current_track()
        if current and self.selected and track_key(current.get("path", "")) == self.selected:
            self.win.engine.seek(float(self.win.engine.duration or 0) * self.seek.value() / 1000)

    def shutdown(self):
        self.timer.stop()
        self.search_timer.stop()
