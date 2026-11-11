# net_page.py
"""
Echoes.NET — вкладка соцсети в Echoes Music (сама сеть — net_core, без Qt).

  Лента     — посты друзей и свои: текст + играющий трек, апвоуты, треды с ответами;
  Сообщения — личные чаты (история на этом компьютере, чат можно очистить);
  Вместе    — комнаты «Слушать вместе»: хост играет, у гостей тот же трек с той же секунды
              (трек ищется в своей коллекции, иначе включается потоком — звук по сети не передаётся);
  Друзья    — свой код, добавить по коду, заявки, список с тем, что сейчас играет;
  Сеть      — Tor (скачать / указать tor.exe / мосты), профиль, очистка истории.

Узел один на окно (win._net_node); события из сетевого потока приходят сигналом _Bridge.ev.
"""
from __future__ import annotations

import data_home
import base64
import hashlib
import json
import math
import random
import time
from collections import OrderedDict
from pathlib import Path
from net_perf import batch_updates

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, QObject, pyqtSignal, QSize, QEvent
from PyQt6.QtGui import (QColor, QFont, QPainter, QPainterPath, QPixmap, QImage, QLinearGradient, QRadialGradient, QPen,
                         QFontMetrics, QCursor, QGuiApplication, QIcon)
from PyQt6.QtWidgets import (QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
                             QLineEdit, QPlainTextEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
                             QComboBox, QFileDialog, QProgressBar, QSizePolicy, QButtonGroup, QScrollArea, QDialog,
                             QGridLayout)

from net_music import (TrackChip, TimelineMarks, ReactBar, BattleBar, QuoteBlock, aura_qss, fmt_sec,
                       items_for, library_match, preview_url, guess_ok, taste_from_stats, my_top_tracks,
                       current_lyric, capsule_times, ago_in, safe_track, tkey)
from yamusic_theme import (YELLOW, MUTED, ya_font, ya_icon, icon_button, cover_pixmap, seg_group, Switch, Page,
                           section_title, HRow, _clear_layout, sanitize_title)

DATA_DIR = data_home.root() / "net"
_AVATARS = OrderedDict()

NET_QSS = f"""
QFrame#NetCard {{ background:rgba(255,255,255,0.045); border:1px solid rgba(255,255,255,0.06); border-radius:16px; }}
QFrame#NetCard:hover {{ border-color:rgba(255,255,255,0.10); }}
QFrame#NetHero {{ border-radius:18px; }}
QLabel#NetName {{ font-weight:800; font-size:13px; }}
QLabel#NetText {{ font-size:14px; color:#ececec; }}
QLabel#NetCode {{ font-family:Consolas,"Cascadia Mono",monospace; font-size:13px; color:{YELLOW};
                  background:rgba(255,219,26,0.07); border-radius:10px; padding:10px 12px; }}
QPushButton#NetLink {{ background:transparent; border:none; padding:2px 4px; color:{MUTED}; font-weight:700; }}
QPushButton#NetLink:hover {{ color:#ffffff; }}
QPushButton#NetVote {{ background:transparent; border:none; border-radius:15px; padding:0; }}
QPushButton#NetVote:hover {{ background:rgba(255,255,255,0.08); }}
QProgressBar {{ background:rgba(255,255,255,0.07); border:none; border-radius:4px; height:8px; }}
QProgressBar::chunk {{ background:{YELLOW}; border-radius:4px; }}
QListWidget#NetChats::item {{ padding:0; border-radius:12px; }}
QListWidget#NetChats::item:selected {{ background:rgba(255,255,255,0.08); }}
QListWidget#NetChats::item:hover {{ background:rgba(255,255,255,0.04); }}
QPushButton {{ border-radius:14px; padding:8px 18px; min-height:16px; }}
QPushButton#YaChip {{ border-radius:13px; padding:6px 14px; }}
QPushButton#YaIcon {{ border-radius:15px; padding:0; }}
QPushButton#NetVote {{ border-radius:14px; }}
QLineEdit {{ border-radius:16px; }}
QComboBox {{ border-radius:16px; }}
QPlainTextEdit {{ border-radius:16px; }}
"""


# ══════════════════════════════════════════════════════════════════════════ #
#  Мелочи: время, цвета, аватары, трек
# ══════════════════════════════════════════════════════════════════════════ #

def ago(ts) -> str:
    d = max(0, time.time() - float(ts or 0))
    if d < 60:
        return "только что"
    if d < 3600:
        return f"{int(d // 60)} мин"
    if d < 86400:
        return f"{int(d // 3600)} ч"
    if d < 7 * 86400:
        return f"{int(d // 86400)} дн"
    return time.strftime("%d.%m.%Y", time.localtime(ts))


def hue_of(onion: str) -> float:
    return int(hashlib.sha1((onion or "?").encode()).hexdigest()[:6], 16) / 0xFFFFFF


def avatar_pm(onion: str, name: str, size: int, online=None, photo: str = "") -> QPixmap:
    """Круглая аватарка: фото профиля (своё или присланное другом), иначе буква на градиенте."""
    import net_frames
    frame = net_frames.overlay_for(onion, size) if size >= 24 else None
    try:
        stat = Path(photo).stat() if photo else None
        photo_stamp = (stat.st_mtime_ns, stat.st_size) if stat else None
    except OSError:
        photo_stamp = None
    key = (onion, name, size, online, photo, photo_stamp, frame.cacheKey() if frame is not None else 0)
    hit = _AVATARS.get(key)
    if hit is not None:
        _AVATARS.move_to_end(key)
        return QPixmap(hit)
    dpr = 2
    pm = QPixmap(size * dpr, size * dpr)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    ins = size * net_frames.INSET if frame is not None else 0.0
    box = QRectF(ins, ins, size - 2 * ins, size - 2 * ins)
    if photo:
        from img_load import read_image
        img = read_image(photo, size * dpr)
    else:
        img = QImage()
    if not img.isNull():
        side = min(img.width(), img.height())
        img = img.copy((img.width() - side) // 2, (img.height() - side) // 2, side, side)
        clip = QPainterPath()
        clip.addEllipse(box)
        p.setClipPath(clip)
        p.drawImage(box, img)
        p.setClipping(False)
    else:
        h = hue_of(onion)
        g = QLinearGradient(0, 0, size, size)
        g.setColorAt(0, QColor.fromHsvF(h, 0.75, 1.0))
        g.setColorAt(1, QColor.fromHsvF((h + 0.15) % 1, 0.85, 0.65))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(box)
        p.setPen(QColor(255, 255, 255))
        p.setFont(ya_font(int(box.width() * 0.42), QFont.Weight.Black))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter,
                   ((name or onion or "?").strip()[:1] or "?").upper())
    if frame is not None:
        p.drawPixmap(QRectF(0, 0, size, size), frame, QRectF(frame.rect()))
    if online is not None:
        r = max(5.0, size * 0.16)
        p.setBrush(QColor("#3ddc84") if online else QColor("#555555"))
        p.setPen(QPen(QColor("#121212"), max(1.5, size * 0.05)))
        p.drawEllipse(QPointF(size - r * 0.9, size - r * 0.9), r * 0.75, r * 0.75)
    p.end()
    # Large profile portraits should not evict hundreds of small feed avatars.
    if size <= 160:
        _AVATARS[key] = QPixmap(pm)
        while len(_AVATARS) > 384:
            _AVATARS.popitem(last=False)
    return pm


def _net_log(*a):
    """Журнал сети: в консоль и в ~/Echoes/net/net.log (до 1 МБ, потом начинается заново) —
    по нему видно, почему не доходит заявка или друг «не в сети»."""
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    print(line)
    try:
        f = DATA_DIR / "net.log"
        mode = "w" if f.exists() and f.stat().st_size > 1_000_000 else "a"
        with open(f, mode, encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def track_meta(t) -> dict | None:
    """Трек плеера → описание для сети (без путей к файлам)."""
    if not t:
        return None
    return {"artist": t.get("artist") or "", "title": sanitize_title(t.get("title") or ""), "album": t.get("album") or "",
            "duration": int(t.get("duration") or 0), "url": t.get("url") or "", "thumb_url": t.get("thumb_url") or ""}


def track_key(t) -> tuple:
    if not t:
        return ("", "")
    try:
        from track_identity import norm
    except Exception:                                          # noqa: BLE001
        def norm(s):
            return (s or "").casefold().strip()
    return norm(t.get("artist") or ""), norm(sanitize_title(t.get("title") or ""))


class _PicBus(QObject):
    """Фото исполнителя скачано (фоновый поток) → плитка в интерфейсе."""
    done = pyqtSignal(object, str)


def lbl(text="", obj="", wrap=False, sel=False) -> QLabel:
    w = QLabel(text)
    w.setTextFormat(Qt.TextFormat.PlainText)            # ники, посты, названия — от людей: текст, не HTML-разметка
    if obj:
        w.setObjectName(obj)
    if wrap:
        w.setWordWrap(True)
    if sel:
        w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return w


def card() -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("NetCard")
    v = QVBoxLayout(f)
    v.setContentsMargins(16, 14, 16, 14)
    v.setSpacing(8)
    return f, v


def accent_btn(text) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("AccentBtn")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def ghost_btn(text) -> QPushButton:
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


class _Bridge(QObject):
    ev = pyqtSignal(str, object)


class _VoiceDevices(QObject):
    """One asynchronous native device query per settings view; never owns a combo."""
    done=pyqtSignal(object)

    def __init__(self,owner):
        super().__init__(owner)
        from duel_settings import tr
        self.loading=tr(owner.win,'Загрузка устройств…','Loading devices…')
        self.unavailable=tr(owner.win,'Устройство недоступно','Device unavailable')
        self.cache=None;self.pending=[];self.started=False
        import threading
        self.cancel=threading.Event()
        self.destroyed.connect(lambda *_args,event=self.cancel:event.set())
        self.done.connect(self._ready)

    def bind(self,combo,key,selected):
        from PyQt6.QtWidgets import QSizePolicy
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(18)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        if self.cache is not None:
            self._populate(combo,key,selected);return
        import weakref
        self.pending.append((weakref.ref(combo),key,selected))
        blocked=combo.blockSignals(True)
        try:
            combo.clear();combo.addItem('Как в Windows',-1)
            if selected is not None:
                combo.addItem(self.loading,selected);combo.setCurrentIndex(1)
            combo.setEnabled(False)
        finally:combo.blockSignals(blocked)
        if self.started:return
        self.started=True
        emit=self.done.emit
        cancel=self.cancel
        def query():
            try:
                from voice_devices import isolated_devices
                devices=isolated_devices(cancel=cancel)
            except Exception:devices=([],[])
            try:emit(devices)
            except (RuntimeError,AttributeError):pass  # the page closed while the native query was pending
        import threading
        threading.Thread(target=query,name='echoes-voice-devices',daemon=True).start()

    def _populate(self,combo,key,selected):
        blocked=combo.blockSignals(True)
        try:
            combo.clear();combo.addItem('Как в Windows',-1)
            for device,name in self.cache[0 if key=='voice_in' else 1]:combo.addItem(name,device)
            index=combo.findData(selected if selected is not None else -1)
            if index<0:
                combo.addItem(self.unavailable,selected);index=combo.count()-1
            combo.setCurrentIndex(index);combo.setEnabled(True)
        finally:combo.blockSignals(blocked)

    def _ready(self,devices):
        from PyQt6 import sip
        self.cache=devices
        pending,self.pending=self.pending,[]
        for ref,key,selected in pending:
            combo=ref()
            if combo is not None and not sip.isdeleted(combo):self._populate(combo,key,selected)


# ══════════════════════════════════════════════════════════════════════════ #
#  Рисованные виджеты
# ══════════════════════════════════════════════════════════════════════════ #

class NetTitle(QWidget):
    """«Echoes.NET» жёлтым + живой индикатор сети (пульсирует, пока в сети)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(46)
        self.setMinimumWidth(260)
        self.online = False
        self.text = "Сеть выключена"
        self._ph = 0.0
        self._t = QTimer(self)
        self._t.setInterval(50)
        self._t.timeout.connect(self._step)

    def set_state(self, online, text):
        self.online, self.text = online, text
        if online and self.isVisible():
            self._t.start()
        elif not online:
            self._t.stop()
        self.update()

    def showEvent(self, e):
        if self.online:
            self._t.start()

    def hideEvent(self, e):
        self._t.stop()

    def _step(self):
        self._ph = (self._ph + 0.05) % (2 * math.pi)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = ya_font(30, QFont.Weight.Black)
        p.setFont(f)
        fm = QFontMetrics(f)
        w1 = fm.horizontalAdvance("Echoes")
        w2 = fm.horizontalAdvance(".NET")
        path = QPainterPath()
        path.addText(0, 34, f, "Echoes")
        path.addText(w1, 34, f, ".NET")
        p.fillPath(path, QColor(YELLOW))
        x = w1 + w2 + 18
        dot = QColor("#3ddc84") if self.online else QColor("#7a7a7a")
        if self.online:
            k = 0.5 + 0.5 * math.sin(self._ph)
            halo = QColor(dot); halo.setAlpha(int(90 * (1 - k)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(halo)
            r = 5 + 7 * k
            p.drawEllipse(QPointF(x + 6, 24), r, r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(dot)
        p.drawEllipse(QPointF(x + 6, 24), 5, 5)
        p.setPen(QColor("#cfcfcf"))
        p.setFont(ya_font(12, QFont.Weight.DemiBold))
        p.drawText(QRectF(x + 18, 14, self.width() - x - 18, 20), Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(ya_font(12)).elidedText(self.text, Qt.TextElideMode.ElideRight,
                                                         max(40, self.width() - int(x) - 24)))
        p.end()


class _WrapLabel(QLabel):
    """Подпись с переносом строк, которая сама держит нужную высоту: в раскладке внутри баннера Qt считал
    её однострочной, и вторая строка уходила под кнопку."""

    def resizeEvent(self, e):
        super().resizeEvent(e)
        h = self.heightForWidth(self.width())
        if h > 0 and h != self.minimumHeight():
            self.setMinimumHeight(h)


class Hero(QFrame):
    """Баннер из чёрного стекла — для пустых состояний и «Слушать вместе»."""

    def __init__(self, title, sub, c1="#ffdb1a", c2="#ff4fa3", height=170, parent=None):
        super().__init__(parent)
        self.setObjectName("NetHero")
        self.setMinimumHeight(height)                  # текст и кнопки — в раскладке: баннер растёт, а не обрезает
        self.title, self.sub = title, sub
        self._surface = None
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(26, 18, 26, 20)
        self.lay.setSpacing(6)
        t = QLabel(title)
        t.setStyleSheet("background:transparent;color:#ffffff;font-size:26px;font-weight:900;")
        t.setFont(ya_font(26, QFont.Weight.Black))
        self.lay.addWidget(t)
        s = _WrapLabel(sub)
        s.setWordWrap(True)
        s.setMaximumWidth(640)
        s.setStyleSheet("background:transparent;color:#ebebeb;font-size:13px;")
        self.lay.addWidget(s)
        self.lay.addStretch(1)

    def paintEvent(self, _):
        from echo_glass import liquid_surface
        if self._surface is None or self._surface.size() != self.size():
            self._surface = liquid_surface(self.size(), radius=18)
        p = QPainter(self)
        p.drawPixmap(0, 0, self._surface)
        p.end()


# ══════════════════════════════════════════════════════════════════════════ #
#  Вкладка
# ══════════════════════════════════════════════════════════════════════════ #

class _FeedSlot(QWidget):
    """Место поста в ленте (виртуальная лента NetPage). Настоящая карточка — десятки кнопок — живёт, только пока
    пост рядом с экраном; ушёл далеко — карточка удаляется, а место держит её высоту, чтобы ничего не прыгало.
    Пока карточки нет, рисуется лёгкая заготовка в форме карточки (видна лишь при очень быстрой прокрутке)."""

    def __init__(self, pid, height):
        super().__init__()
        self.pid = pid
        self.card = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.setFixedHeight(max(40, int(height)))

    def put(self, card):
        self.card = card
        self.layout().addWidget(card)
        card.show()
        self.fit()

    def fit(self):
        """Высота места = высота карточки (всегда фиксированная: раскладка ленты не зависит от того, успел ли
        Qt её пересчитать, — по ней считается, что рядом с экраном)."""
        if self.card is None:
            return
        w = self.width()
        if w < 100:
            par = self.parentWidget()
            w = (par.width() - 8) if par is not None and par.width() > 100 else 640
        h = self.card.heightForWidth(w) if self.card.hasHeightForWidth() else -1
        if h <= 0:
            h = self.card.sizeHint().height()
        h = max(40, h)
        if h != self.height() or self.minimumHeight() != h:
            self.setFixedHeight(h)

    def take(self):
        """Убрать карточку и вернуть её. Место остаётся той же высоты."""
        card, self.card = self.card, None
        if card is not None:
            self.layout().removeWidget(card)
        return card

    def event(self, e):
        if e.type() == QEvent.Type.LayoutRequest and self.card is not None:
            self.fit()                                   # карточка выросла (гифка, файлы, раскрыли ответы)
        return super().event(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.card is not None and e.oldSize().width() != e.size().width():
            self.fit()

    def paintEvent(self, e):
        if self.card is not None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 10))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 16, 16)
        p.setBrush(QColor(255, 255, 255, 16))
        p.drawEllipse(QRectF(52, 14, 34, 34))
        p.drawRoundedRect(QRectF(96, 18, 140, 10), 5, 5)
        p.drawRoundedRect(QRectF(96, 34, 80, 8), 4, 4)
        p.end()


class NetPage(QWidget):
    TAB_TIPS = {"feed": "Посты друзей и всех пользователей ECHOES", "chats": "Личные сообщения и группы",
                "friends": "Ваш код, заявки и друзья", "room": "Слушать музыку вместе — синхронно, с голосом",
                "threads": "Обсуждения как на Reddit", "mods": "Темы оформления от других пользователей",
                "net": "Профиль, приватность, уведомления",
                "admin": "Модерация Echoes.NET: модераторы, блокировки, скрытые посты, обновления для всех"}
    TABS = (("feed", "Лента"), ("chats", "Сообщения"), ("friends", "Друзья"), ("room", "Слушать вместе"),
            ("threads", "Треды"), ("mods", "Моды"), ('requests','Запросы и баги'), ("net", "Настройки"), ("admin", "Админка"))

    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.win = shell.win
        self.setObjectName("YaPage")
        from echo_glass import glass_controls_qss
        self.setStyleSheet(NET_QSS + glass_controls_qss())
        self.node = None
        self.bridge = _Bridge()
        self.bridge.ev.connect(self._on_event)
        import net_frames                                      # рамки у аватарок — по профилям людей
        net_frames.RESOLVER = self._frame_of
        import net_collab                                      # совместные плейлисты: напоминать состояние
        net_collab.install(self.win)
        self._mom_timer = QTimer(self)                         # реакции на момент — догнать тех, кто был не в сети
        self._mom_timer.setInterval(600000)
        self._mom_timer.timeout.connect(lambda: self.running() and __import__("net_moments").resend(self))
        self._mom_timer.start()
        import net_capsule                                     # капсулы времени: уведомить, когда откроются
        self._capsule_watch = net_capsule.Watch(self)
        import net_weektop                                     # по воскресеньям — «топ недели друзей готов»
        self._weektop_alert = net_weektop.SundayAlert(self)
        import net_game
        self._game_watch = net_game.Watcher(self)
        net_frames.ENGINE = getattr(self.win, "engine", None)   # рамки и витрины «под музыку»
        __import__("net_devsync").get(self)                    # синхронизация своих ПК
        self._chat_peer = None
        self._feed_sort = "hot"
        self._open_threads: set[str] = set()
        self._drafts: dict[str, str] = {}
        self._reply_to: dict[str, tuple[str, str]] = {}
        self._revealed: set[str] = set()                       # «Угадай трек»: сдались — ответ виден
        self._pending_seek = None
        self._live = None
        self._voice = None                                     # net_voice.Voice — создаётся при первом голосе
        self._voice_muted = False
        self._voice_seq = 0
        self._ducked = False
        self._voice_t = QTimer(self)
        self._voice_t.setInterval(100)
        self._voice_t.timeout.connect(self._voice_tick)
        self._now_key = None
        self._sync = {"sent": None, "follow": None, "follow_t": 0.0, "follow_path": "", "seek_t": 0.0,
                      "toggle_t": 0.0, "ping_t": 0.0}
        self._feed_timer = QTimer(self); self._feed_timer.setSingleShot(True); self._feed_timer.setInterval(16)
        self._feed_timer.timeout.connect(self._fill_feed)
        self._pres_timer = QTimer(self); self._pres_timer.setSingleShot(True); self._pres_timer.setInterval(400)
        self._pres_timer.timeout.connect(self._presence_refresh)
        self._pres_tick = QTimer(self); self._pres_tick.setInterval(20000)
        self._pres_tick.timeout.connect(self._presence_tick)
        self._pres_tick.start()

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 18, 32, 14)
        root.setSpacing(10)
        top = QHBoxLayout()
        self.title = NetTitle()
        top.addWidget(self.title, 1)
        from duel_settings import tr
        self.b_bug=ghost_btn(tr(self.win,'Запросы и баги','Requests and bugs'))
        self.b_bug.setIcon(ya_icon('bug',16));self.b_bug.clicked.connect(self.open_bug_report);top.addWidget(self.b_bug)
        self.b_me = QLabel()
        self.b_me.setFixedSize(40, 40)
        top.addWidget(self.b_me)
        self.b_code = ghost_btn("  Мой код")
        self.b_code.setIcon(ya_icon("copy", 16))
        self.b_code.setToolTip("Скопировать ваш код Echoes.NET — отправьте его другу")
        self.b_code.clicked.connect(self.copy_code)
        top.addWidget(self.b_code)
        self.b_upd = accent_btn("  Обновить ECHOES")
        self.b_upd.setIcon(ya_icon("download", 16, "#000000"))
        self.b_upd.setToolTip("Друг прислал новую версию ECHOES — посмотреть и установить")
        self.b_upd.clicked.connect(self.open_update)
        self.b_upd.hide()
        top.addWidget(self.b_upd)
        self.b_power = accent_btn("Включить сеть")
        self.b_power.clicked.connect(self.toggle_power)
        top.addWidget(self.b_power)
        root.addLayout(top)

        self.tab_btns = {}
        grp = QButtonGroup(self)
        btns = []
        for key, text in self.TABS:
            if key=='requests':text=tr(self.win,'Запросы и баги','Requests and bugs')
            b = QPushButton(text)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.show_tab(k))
            b.setToolTip(self.TAB_TIPS.get(key, ""))
            grp.addButton(b)
            self.tab_btns[key] = b
            btns.append(b)
        segrow = QHBoxLayout()
        segrow.addWidget(seg_group(*btns))
        segrow.addStretch(1)
        root.addLayout(segrow)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.tabs = {"feed": self._build_feed(), "chats": self._build_chats(), "room": self._build_room(),
                     "friends": self._build_friends(), "net": self._build_net(), "profile": self._build_profile(),
                     "mods": self._build_mods(), "threads": self._build_threads(), "admin": self._build_admin(),
                     'requests':self._build_requests()}
        for w in self.tabs.values():
            self.stack.addWidget(w)
        from net_call_ui import CallController
        self.calls = CallController(self)
        self._tab = None
        self.tab_btns["admin"].hide()
        self.show_tab("feed")
        QTimer.singleShot(0, self._staff_ui)

        self._tick_t = QTimer(self)
        self._tick_t.setInterval(1000)
        self._tick_t.timeout.connect(self._tick)
        self._tick_t.start()
        self._ensure_node(start=False)
        self.b_me.setPixmap(self._av(self.node.me.onion, self.node._name(), 40))
        self._clickable(self.b_me, self.node.me.onion)
        self.b_me.setToolTip("Мой профиль в Echoes.NET")
        self._refresh_tab(self._tab)
        if self.node.settings.get("autostart"):
            QTimer.singleShot(3500, self.start_net)
        self._status_ui(self.node.state)
        self._update_badge()

    # ── узел ── #

    def _ensure_node(self, start=True):
        nd = getattr(self.win, "_net_node", None)
        if nd is None:
            from net_core import NetNode
            nd = NetNode(DATA_DIR, log=_net_log)
            self.win._net_node = nd
            from PyQt6.QtWidgets import QApplication
            QApplication.instance().aboutToQuit.connect(nd.shutdown)
        nd.on_event = lambda k, d: self.bridge.ev.emit(k, d)
        nd.set_library_lookup(self._lib_path)
        if not nd.settings.get("name"):                        # имя в сети по умолчанию — ник профиля плеера
            nd.settings["name"] = str(self.win.profile.get("nickname") or "ECHOES")[:40]
        self.node = nd
        if start:
            nd.start()
        return nd

    def running(self) -> bool:
        return bool(self.node and self.node.thread and self.node.thread.is_alive())

    def open_bug_report(self, _=False, inbox=False):
        self.shell.show_page('net');self.show_tab('requests');self._fill_requests()
        panel=self._requests_panel
        panel.tabs.setCurrentIndex(2 if inbox and panel.inbox is not None else 0)
        return panel

    def _build_requests(self):
        self.requests_page=Page(margins=(0,4,8,12));return self.requests_page

    def _fill_requests(self):
        if self.node is None:return
        panel=getattr(self,'_requests_panel',None)
        if panel is None:
            from bug_report_ui import BugReportsDialog
            panel=self._requests_panel=BugReportsDialog(self,embedded=True)
            self.requests_page.v.addWidget(panel,1)
        panel.refresh()

    def start_net(self):
        nd = self._ensure_node(start=False)
        if not nd.settings.get("name"):
            nd.settings["name"] = str(self.win.profile.get("nickname") or "ECHOES")[:40]
        nd.settings["autostart"] = True
        nd.save_settings()
        nd.start()

    def stop_net(self):
        if self.node:
            self._voice_stop()
            self.node.settings["autostart"] = False
            self.node.save_settings()
            self.node.stop()

    def toggle_power(self):
        if self.running():
            self.stop_net()
        else:
            self.start_net()

    def copy_code(self):
        QGuiApplication.clipboard().setText(self.node.code)
        self.toast("Код скопирован — отправьте его другу")

    def toast(self, text):
        try:
            self.win._toast(text)
        except Exception:                                      # noqa: BLE001
            print("[net]", text)
        self.notify(text)

    @property
    def notifier(self):
        n = self.__dict__.get("_notifier")
        if n is None:
            from net_notify import Notifier
            n = self._notifier = Notifier(self.win, lambda: self.node.settings if self.node else {}, self._tray_icon)
        return n

    def alert(self, kind, title, text="", onion="", npub="", post="", tab="", force=False):
        """Уведомление в углу экрана (net_notify): со звуком, по настройкам «Уведомления»."""
        try:
            pix = self._av(onion, title, 92) if onion else None
            if pix is None and npub:
                pf = ((self._pub().get("profiles") or {}).get(npub) or {}).get("avatar_file") or ""
                pix = QPixmap(pf) if pf else None

            def go():
                import ui_anim                                 # как было: развёрнутым — так развёрнутым
                ui_anim.bring_front(self.win)
                if kind == "message" and onion:
                    self.open_chat(onion)
                elif kind in ("online", "room") and onion:
                    self.open_profile(onion) if kind == "online" else self.show_tab("room")
                elif tab == "update":
                    self.shell.show_page("net")
                    self.open_update()
                elif tab.startswith("artist:"):
                    self.shell.open_artist(tab[7:])
                elif tab == "follows":
                    self.shell.show_page("follows")
                elif tab:
                    self.shell.show_page("net")
                    self.show_tab(tab)
                elif kind == "post" and (onion or npub):
                    self.open_profile(onion) if onion and self.node.store.contact(onion) else self.open_public(npub) \
                        if npub else self.open_profile(onion)
                elif kind == "comment" and post:
                    self.shell.show_page("net")
                    self.show_tab("feed")
                elif onion:
                    self.open_profile(onion)
                else:
                    self.shell.show_page("net")
            key = f"{kind}:{onion or npub}" if kind in ("message", "comment", "post") else None
            return self.notifier.show(kind, title, text, pix, go, key=key, force=force)
        except Exception as e:                                 # noqa: BLE001
            print("[net] alert:", e)
            return False

    def _tray_icon(self):
        shared = getattr(getattr(self.win, "_tray", None), "icon", None)
        if shared is not None:
            return shared
        from PyQt6.QtWidgets import QSystemTrayIcon
        if getattr(self, "_tray", None) is None and QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = QSystemTrayIcon(self.win.windowIcon(), self)
            self._tray.setToolTip("ECHOES · Echoes.NET")
            self._tray.messageClicked.connect(lambda: (__import__("ui_anim").bring_front(self.win),
                                                       self.shell.show_page("net")))
            self._tray.show()
        return getattr(self, "_tray", None)

    def notify(self, text, title="Echoes.NET"):
        """Прочие события сети, пока плеер свёрнут, — карточкой в углу (вид «прочие события»)."""
        try:
            from PyQt6.QtWidgets import QApplication
            if QApplication.applicationState() == Qt.ApplicationState.ApplicationActive or not self.node:
                return
            self.alert("info", title, str(text))
            return
        except Exception as e:                                 # noqa: BLE001
            print("[net] notify:", e)

    # ── голос в комнате ── #

    def toggle_mic(self):
        nd = self.node
        if nd.room_host is None and not nd.room_guest:
            self.toast("Голос работает в комнате «Слушать вместе»")
            return
        if nd.cur_call is not None:
            self.toast("Сейчас идёт звонок — микрофон занят им")
            return
        try:
            v = self.calls.ensure_engine()
            if v.mic_active:
                v.mic_off()
            else:
                v.sink = nd.voice_out
                v.want = {nd.room_codec()}
                v.mic_on()
                self._voice_t.start()
                host = nd.room_guest
                warn = host and nd.voice_link(host) == "none"
                self.toast("Микрофон включён — вас слышат в комнате" +
                           (". Прямого канала с хостом пока нет — голос пойдёт, как только он откроется" if warn
                            else ""))
        except Exception as e:                                 # noqa: BLE001
            self.toast(f"Микрофон не включился: {e}")
        self._fill_room()

    def _voice_stop(self):
        radio=getattr(self,'_radio_voice',None)
        if radio is not None:
            radio.close();self._radio_on_air=False
            try:self.win.engine._apply_loudness()
            except Exception:pass
        self._radio_sound_token=self.__dict__.get('_radio_sound_token',0)+1
        if self._voice is not None and (self.node is None or self.node.cur_call is None):
            self._voice.close()
        self._voice_t.stop()
        if self._ducked:
            self._ducked = False
            try:
                self.win.engine._apply_loudness()
            except Exception:                                  # noqa: BLE001
                pass

    def _voice_in(self, src, codec, seq, frames):
        nd = self.node
        if self._voice_muted or (nd.room_host is None and not nd.room_guest):
            return
        try:
            self.calls.ensure_engine().play(src, codec, seq, frames)
            self._voice_t.start()
        except Exception as e:                                 # noqa: BLE001
            print("[net] voice:", e)

    def _voice_tick(self):
        try:
            self._voice_tick_impl()
        except Exception:                                      # noqa: BLE001
            import traceback
            traceback.print_exc()

    def _voice_tick_impl(self):
        """Каждые 0.1 с: отправить свои кадры, приглушить музыку, пока кто-то говорит, подписать «говорят»."""
        v = self._voice
        if v is None:
            self._voice_t.stop()
            return
        nd = self.node
        if nd.room_host is None and not nd.room_guest and nd.cur_call is None:
            self._voice_stop()
            return
        if nd.cur_call is None and v.mic_active:
            v.want = {nd.room_codec()}                         # кодек комнаты мог смениться (новый гость)
        talk = v.speaking()
        if talk and not self._ducked:
            self._ducked = True
        if self._ducked:
            try:
                self.win.engine._apply_loudness(scale=0.3 if talk else 1.0)
            except Exception:                                  # noqa: BLE001
                pass
            if not talk:
                self._ducked = False
        try:
            names = [self._name(s) for s in talk]
            me = v.mic_active and v.talking
            txt = ("Говорят: " + ", ".join((["вы"] if me else []) + names)) if (names or me) else                 ("Микрофон включён · тишина" if v.mic_active else "")
            self.voice_lbl.setText(txt)
        except (AttributeError, RuntimeError):
            pass

    def resizeEvent(self, e):
        super().resizeEvent(e)
        w = self.width()
        side = getattr(self, "feed_side_w", None)
        if side is not None:
            side.setVisible(w >= 1040)                         # узкое окно — лента во всю ширину
        compact = w < 920
        if compact != self.__dict__.get("_compact_tabs"):
            self._compact_tabs = compact
            for b in getattr(self, "tab_btns", {}).values():   # вкладки поуже, чтобы влезали
                b.setStyleSheet("QPushButton{padding:6px 9px;font-size:12px;}" if compact else "")

    def on_show(self):
        """Открыли Echoes.NET: вкладку пересобрать, только если с прошлого раза пришло что-то новое
        (уже показанная — после перехода, см. _refresh_soon)."""
        self._refresh_soon(self._tab)

    def _refresh_soon(self, key):
        """Вкладка уже была заполнена — показать её сразу как есть, а обновить, когда закончится переход.
        Любое событие сети (присутствие друзей, посты, сообщения) помечает устаревшими все вкладки, поэтому
        раньше почти каждый клик сначала пересобирал вкладку (100–250 мс), а уже потом показывал её."""
        if key in ("profile", "chats") or key not in self.__dict__.get("_filled_ver", {}):
            # впервые — сразу (иначе мелькнёт пустая); профиль и чат — другой человек, старое не показывать
            self._refresh_tab(key, force=False)
            return

        def later():
            try:
                if self._tab == key and self.isVisible():
                    self._refresh_tab(key, force=False)
            except RuntimeError:
                pass
        QTimer.singleShot(320, later)

    def show_tab(self, key):
        if key not in self.tabs:
            return
        previous=self._tab
        self._tab = key
        if key in self.tab_btns:
            self.tab_btns[key].setChecked(True)
        else:                                              # профиль — без кнопки в переключателе
            grp = next(iter(self.tab_btns.values())).group()
            grp.setExclusive(False)
            for b in self.tab_btns.values():
                b.setChecked(False)
            grp.setExclusive(True)
        self._refresh_soon(key)
        w = self.tabs[key]
        # The common transition driver coalesces rapid navigation and captures
        # only visible content; cached tabs keep drafts and scroll position.
        import ui_anim
        order=[name for name,_ in self.TABS]+['profile']
        direction=(1 if order.index(key)>order.index(previous) else -1) if previous in order and key in order and previous!=key else 0
        ui_anim.switch(self.stack,w,direction=direction)

    def _roundify(self, root=None):
        """Compatibility hook for extensions. Rounding is inherited from NET_QSS.

        Per-button style mutation caused another full polish/layout pass after
        every click, including widgets already waiting for deferred deletion.
        """

    # какие вкладки показывают данные события сети (остальные не пересобирать); нет в списке — все
    _EVENT_TABS = {
        "presence": ("friends", "chats", "net", "room"),
        "message": ("chats",), "delivered": ("chats",), "group": ("chats",), "file": ("chats",),
        "track_file": ("chats",),
        "feed": ("feed", "profile"), "social": ("feed", "profile"), "public": ("feed", "profile"),
        "mreact": ("feed", "profile"),
        "profile": ("feed", "friends", "chats", "profile", "room", "requests"),
        "contacts": ("friends", "chats", "requests", "profile"),
        "staff": ("mods", "admin", "profile"),
        "room": ("room",), "room_chat": ("room",), "radio_permits": ("room",), "quiz": ("room",),
        "q_add": ("room",), "q_res": ("room",), "spl": ("room",),
        "update_pub": ("net", "admin"), "notify": ("requests", "friends"),
        "ring": (), "call": (), "toast": (), "devsync": (),
    }

    def _refresh_tab(self, key, force=True):
        version = (self.__dict__.get("_data_ver", 0), self.__dict__.get("_tab_ver", {}).get(key, 0))
        filled = self.__dict__.setdefault("_filled_ver", {})
        def stamp():
            context = self.__dict__.get("_chat_peer") if key == "chats" else \
                (self.__dict__.get("_profile_onion"), self.__dict__.get("_profile_npub")) if key == "profile" else None
            return version, context
        if not force and filled.get(key) == stamp():
            return
        if key == "feed":
            self._fill_feed()
        elif key == "threads":
            self.threads.fill()
        elif key == "chats":
            self._fill_chat_list()
            self._fill_chat()
        elif key == "room":
            self._fill_room()
        elif key == "friends":
            self._fill_friends()
        elif key == "net":
            self._fill_net()
        elif key == "mods":
            self._fill_mods()
        elif key == "profile":
            self._fill_profile()
        elif key == "admin":
            self._fill_admin()
        elif key=='requests':self._fill_requests()
        # Record only successful, populated views (startup creates the node later).
        if self.node is not None:
            filled[key] = stamp()

    # ── события сети ── #

    def _on_event(self, kind, data):
        if kind not in ("voice", "vc", "update", "status"):
            tabs = self._EVENT_TABS.get(kind)
            if tabs is None:                                           # незнакомое событие — устарело всё
                self._data_ver = self.__dict__.get("_data_ver", 0) + 1
            else:                                                      # только вкладки с этими данными
                tv = self.__dict__.setdefault("_tab_ver", {})
                for t in tabs:
                    tv[t] = tv.get(t, 0) + 1
        if kind in ("profile", "contacts", "staff", "social"):
            self._chat_render_epoch = self.__dict__.get("_chat_render_epoch", 0) + 1
        try:                                     # исключение в слоте Qt роняет весь плеер — сеть не должна
            self._on_event_impl(kind, data)
        except Exception:                                      # noqa: BLE001
            import traceback
            traceback.print_exc()

    def _on_event_impl(self, kind, data):
        if kind=='radio_permits':
            if self._tab=='room':self._fill_room()
            return
        if kind == "devsync" and isinstance(data, dict):        # синхронизация своих ПК
            import net_devsync
            net_devsync.on_message(self, data)
            return
        if kind == "presence" and isinstance(data, str) and data:
            import net_devsync
            net_devsync.get(self).on_presence(data)
            try:                                               # автоматика: «друг в сети»
                if self.node.is_friend(data) and not __import__("net_devsync").is_device(self.node, data):
                    __import__("ya_auto").get(self.win).friend_presence(data, self._online(data), self._name(data))
            except Exception:                                  # noqa: BLE001
                pass
        if kind == "mreact" and isinstance(data, dict):         # реакции на момент трека
            import net_moments
            net_moments.on_message(self, data.get("from", ""), data.get("m") or {})
            return
        if kind == "spl" and isinstance(data, dict):            # совместные плейлисты
            import net_collab
            net_collab.on_message(self, data.get("from", ""), data.get("m") or {})
            return
        if kind in ("q_add", "q_res") and isinstance(data, dict):   # очередь от друзей
            import net_queue
            (net_queue.on_add if kind == "q_add" else net_queue.on_res)(self, data)
            return
        if kind == "quiz" and isinstance(data, dict):           # «Угадай трек вместе»
            import net_quiz_live
            net_quiz_live.on_message(self, data.get("from", ""), data.get("m") or {})
            return
        if kind == "status":
            self._status_ui(data)
        elif kind == "toast":
            self.toast(str(data))
        elif kind == "update":
            self._upd_ui(data)
        elif kind == "staff":
            self._staff_ui()
            if self._tab == "admin":
                self._fill_admin()
        elif kind == "update_pub":
            d = data or {}
            self.toast(f"Обновление {d.get('ver') or ''} разослано: друзей в сети — {d.get('sent', 0)}. "
                       "Остальные получат его, когда появятся в сети")
            if self._tab == "net":
                self._fill_net()
        elif kind == "notify" and isinstance(data, dict) and data.get("kind") == "update":
            pass                         # раздачи через Echoes.NET больше нет — обновления приходят с GitHub
        elif kind == "notify" and isinstance(data, dict):
            d = data
            shown = self.alert(d.get("kind", "info"), d.get("title", ""), d.get("text", ""), d.get("onion", ""),
                               d.get("npub", ""), d.get("post", ""), d.get("tab", ""))
            try:
                from PyQt6.QtWidgets import QApplication
                if not shown and QApplication.applicationState() == Qt.ApplicationState.ApplicationActive \
                        and d.get("kind") in ("request", "comment"):
                    self.win._toast(f"{d.get('title', '')}: {d.get('text', '')}")   # уведомления выкл. — хотя бы тост
            except Exception:                                  # noqa: BLE001
                pass
            if d.get("kind") == "request":
                self._update_badge()
        elif kind == "contacts":
            self._update_badge()
            if self._tab in ("friends", "chats"):
                self._refresh_tab(self._tab)
        elif kind == "presence":
            self._pres_timer.start()
        elif kind == "social":
            t = self.__dict__.get("_soc_t")
            if t is None:
                t = self._soc_t = QTimer(self)
                t.setSingleShot(True)
                t.setInterval(2000)
                t.timeout.connect(self._social_refresh)
            if not t.isActive():
                t.start()
        elif kind == "profile":                                # друг прислал новый профиль / аватарку
            if self._tab == "profile" and getattr(self, "_profile_onion", None) == data:
                self._fill_profile()
            else:
                self._pres_timer.start()
        elif kind == "voice":
            self._voice_in(*data)
        elif kind == "vc":
            self.calls.on_vc(data)
            self._voice_t.start()
        elif kind == "vc_gone":
            if self._voice is not None:
                self._voice.drop(data)
        elif kind == "ring":
            self.calls.on_ring(data)
        elif kind == "call":
            self.calls.on_call(data)
            if data is not None:
                self._voice_t.start()
        elif kind == "file":
            self._file_event(*data)
            if data[1] == "done":
                self._maybe_play_track_file(data[0], data[2])
                self._mod_file_done(data[0], data[2])
        elif kind == "track_file":
            self._on_track_file(*data)
        elif kind == "public":
            t = self.__dict__.get("_pub_t")
            if t is None:
                t = self._pub_t = QTimer(self)
                t.setSingleShot(True)
                t.setInterval(1200)
                t.timeout.connect(self._public_refresh)
            t.start()
        elif kind == "group":
            self.open_chat("g:" + str(data))
        elif kind in ("message", "delivered"):
            from PyQt6.QtWidgets import QApplication
            looking = data == self._chat_peer and self._tab == "chats" and self.isVisible() and \
                QApplication.applicationState() == Qt.ApplicationState.ApplicationActive
            if kind == "message" and data and not looking and not str(data).startswith("g:"):
                last = self.node.store.last_message(data)
                if last and last["dir"] == "in":
                    fx = (last.get("extra") or {}).get("file") or {}
                    body = ("прислал(а) капсулу времени" if _capsule_locked(last)
                            else f"Файл: {fx.get('name')}" if fx and not last["text"]
                            else "Плейлист: " + str((last.get("extra") or {}).get("title"))
                            if (last.get("extra") or {}).get("kind") == "playlist"
                            else (last["text"][:160] or "трек"))
                    if not self.alert("message", self._name(data), body, onion=data) and \
                            QApplication.applicationState() == Qt.ApplicationState.ApplicationActive:
                        self.win._toast(f"{self._name(data)}: {body[:60]}")
            if self._tab == "chats" and self.isVisible():
                if data == self._chat_peer or data is None:
                    if data:
                        self.node.store.mark_read(data)
                    self._fill_chat()
                self._fill_chat_list()
            self._update_badge()
        elif kind == "feed":
            if self._tab == "mods" and self.isVisible():
                self._fill_mods()
            if self._tab == "feed" and self.isVisible():
                if not self._feed_timer.isActive():
                    self._feed_timer.start()
            if self._tab == "threads" and self.isVisible():
                self.threads._deb.start()
        elif kind == "room":
            if self._tab == "room":
                view = self.node.room_view() or {}
                state = view.get('state') or {}; radio = state.get('radio') or {}
                signature = (view.get('role'), radio.get('revision'), radio.get('current'),
                             state.get('playing'), tuple(view.get('members') or []))
                if not radio or signature != self.__dict__.get('_radio_view_signature'):
                    self._fill_room()
            if data is None:
                self._sync.update(sent=None, follow=None, follow_path="")
                self._voice_stop()
        elif kind == "room_chat":
            if self._tab == "room":
                self._room_chat_add(data)

    def _public_refresh(self):
        if not self.isVisible():
            return
        now = time.time()
        if now - self.__dict__.get("_pub_refresh_t", 0) < 8:          # публичные события сыплются часто —
            self._pub_t.start()                                         # перестраивать вкладку не чаще раза в 8 с
            return
        self._pub_refresh_t = now
        if self._tab == "mods":
            self._fill_mods()
        elif self._tab == "feed" and self._feed_sort == "all":
            self._fill_feed()
        elif self._tab == "room" and self.node.room_view() is None:
            self._fill_room()
        elif self._tab == "friends":
            self._fill_friends()
        elif self._tab == "profile" and getattr(self, "_profile_npub", None):
            self._fill_profile()

    def _presence_tick(self):
        """Раз в 20 с: изменилось, кто в сети, — перерисовать (событие могло потеряться или друг «отвалился»)."""
        if self.node is None or not self.running():
            return
        if not self.__dict__.get("_net_up_t"):
            self._net_up_t = time.time()
        online = {c["onion"] for c in self.node.store.contacts("friend") if self._online(c["onion"])}
        if online != self.__dict__.get("_online_seen"):
            self._presence_refresh()

    def _presence_refresh(self):
        rooms = {}
        for c in self.node.store.contacts("friend"):
            if c["room"] and self._online(c["onion"]):
                try:
                    rooms[c["onion"]] = (json.loads(c["room"]) or {}).get("title", "")
                except ValueError:
                    pass
        seen = getattr(self, "_rooms_seen", None)
        if seen is not None:                                   # друг только что открыл комнату — позвать
            for o, title in rooms.items():
                if o not in seen:
                    if not self.alert("room", self._name(o), f"открыл(а) комнату «{title}» — заходите слушать вместе",
                                      onion=o):
                        self.win._toast(f"{self._name(o)} открыл(а) комнату «{title}»")
        self._rooms_seen = set(rooms)
        online = {c["onion"] for c in self.node.store.contacts("friend") if self._online(c["onion"])}
        was = self.__dict__.get("_online_seen")
        started = self.__dict__.get("_net_up_t") or time.time()
        now = time.time()
        off_since = self.__dict__.setdefault("_off_since", {})
        last_alert = self.__dict__.setdefault("_online_alerted", {})
        if was is None:
            for c in self.node.store.contacts('friend'):
                if c['onion'] not in online:off_since.setdefault(c['onion'], now)
        if was is not None:
            for o in was - online:
                off_since.setdefault(o, now)                   # пропал — запомнить, с какого момента
        if was is not None and now - started > 45:             # сразу после включения — не сыпать «в сети»
            for o in online - was:
                # связь у друга «мигает» (переподключения) — это не «появился в сети»: зовём, только если его
                # не было хотя бы 10 минут подряд, и не чаще раза в полчаса на человека
                gone_since = off_since.get(o)
                gone = now-gone_since if gone_since is not None else 0
                if gone >= ONLINE_GONE_MIN and now - last_alert.get(o, 0) >= ONLINE_ALERT_EVERY:
                    last_alert[o] = now
                    self.alert("online", self._name(o), "теперь в сети", onion=o)
        for o in online:
            off_since.pop(o, None)
        self._online_seen = online
        if self._tab == "chats":
            self._fill_chat_list()
            self._chat_header()
        elif self._tab == "friends":
            self._fill_friends()
        elif self._tab == "room":
            self._fill_room()
        self.shell._dirty.add("foryou")

    def _status_ui(self, st):
        st = st or {}
        if st.get('phase') in ('off','error','no_tor'):
            radio=getattr(self,'_radio_voice',None)
            if radio is not None and (radio.mic_active or radio._clip is not None):self._voice_stop()
        self._staff_ui()
        on = bool(st.get("online"))
        self.title.set_state(on, st.get("text", ""))
        self.b_power.setText("Выключить" if self.running() and st.get("phase") not in ("off", "no_tor", "error")
                             else "Включить сеть")
        self.b_power.setObjectName("" if self.running() and st.get("phase") not in ("off", "no_tor", "error")
                                   else "AccentBtn")
        self.b_power.style().unpolish(self.b_power); self.b_power.style().polish(self.b_power)
        if st.get("phase") == "no_tor" and self._tab != "net":
            self.show_tab("net")
        if self._tab == "net":
            self._net_status_ui(st)

    def _update_badge(self):
        try:
            n = sum(self.node.store.unread().values()) + len(self.node.store.contacts("pending_in"))
        except Exception:                                      # noqa: BLE001
            n = 0
        b = getattr(self.shell, "net_badge", None)
        if b is not None:
            b.setText(str(n) if n < 100 else "99+")
            b.setVisible(n > 0)

    def _name(self, onion) -> str:
        if str(onion or "").startswith("g:"):
            return self._peer_title(onion)
        c = self.node.store.contact(onion) if onion else None
        return (c and c["name"]) or (onion or "")[:8]

    def _online(self, onion) -> bool:
        return bool(self.node and self.node.is_online(onion))

    # ── воспроизведение треков из сети ── #

    def play_meta(self, meta, at=None, live=None) -> str:
        """Трек из поста/сообщения/комнаты: есть в коллекции — оттуда, нет — потоком. Возвращает путь.
        at — включить с этой секунды; live — комментарии [(сек, имя, текст)], всплывут во время трека."""
        meta = safe_track(meta)
        if not meta:
            return ""
        w = self.win
        i, t = library_match(w, meta)
        if t is not None:
            w._play_index(i, "library")
            path = str(t.get("path", ""))
        else:
            try:
                import stream_core
                item = stream_core.make_track(meta)
                w.stream_tracks([item])
                path = item.get("path", "")
            except Exception as e:                             # noqa: BLE001
                self.toast(f"Не получилось включить трек: {e}")
                return ""
        self._pending_seek = (tkey(meta), path, float(at), time.time()) if at else None
        self._live = {"key": tkey(meta), "path": path, "marks": sorted(live or []), "shown": set()} if live else None
        if at:
            self.toast(f"Включаю с {fmt_sec(at)}")
        return path

    def play_many(self, metas, title="", start=0):
        items = items_for(self.win, metas)
        if not items:
            return
        self.win.stream_tracks(items, start=start)
        if title:
            self.toast(f"Играет: {title} · {len(items)} тр.")

    def preview(self, meta, btn=None):
        """30 секунд трека вслепую: отдельный плеер (основной на паузе), название нигде не показывается."""
        try:
            from preview import get_preview
            owner = getattr(self, "_pv_owner", None)
            if owner is None:
                def owner(state, left):
                    if state == "error":
                        self.toast("Превью не нашлось")
                    elif state == "loading":
                        self.toast("Ищу превью…")
                self._pv_owner = owner
            get_preview(self.win).toggle(preview_url(meta), int((safe_track(meta) or {}).get("duration") or 0), owner)
        except Exception as e:                                 # noqa: BLE001
            self.toast(f"Превью недоступно: {e}")

    def _local_tick(self):
        """Без сети: перемотка «момента» после загрузки трека и всплывающие комментарии на таймлайне."""
        cur = self.shell.current_track()
        eng = self.win.engine
        try:
            dur = float(eng.duration or 0)
            pos = float(eng.get_position() or 0)
        except Exception:                                      # noqa: BLE001
            return
        ps = getattr(self, "_pending_seek", None)
        if ps:
            key, path, at, t0 = ps
            same = cur is not None and (tkey(cur) == key or str(cur.get("path", "")) == path)
            if time.time() - t0 > 40:
                self._pending_seek = None
            elif same and dur > 0 and at < dur:
                eng.seek(at)
                self._pending_seek = None
        lv = getattr(self, "_live", None)
        if lv and cur is not None and (tkey(cur) == lv["key"] or str(cur.get("path", "")) == lv["path"]):
            for i, (sec, name, text) in enumerate(lv["marks"]):
                if i not in lv["shown"] and sec <= pos < sec + 2.5:
                    lv["shown"].add(i)
                    self.toast(f"{fmt_sec(sec)} · {name}: {text[:80]}")
        if self._tab == "chats" and getattr(self, "_capsule_until", 0) and time.time() >= self._capsule_until:
            self._capsule_until = 0
            self._fill_chat()

    # ── тик: «сейчас играет», синхронизация комнаты ── #

    def _tick(self):
        try:
            self._tick_impl()
        except Exception:                                      # noqa: BLE001
            import traceback
            traceback.print_exc()

    def _tick_impl(self):
        self._local_tick()
        if not self.running() or not self.node.state.get("online"):
            return
        nd = self.node
        if time.time() - getattr(self, "_taste_t", 0) > 1800:      # свой вкус — друзьям, раз в полчаса
            self._taste_t = time.time()
            nd.call(nd.set_taste, taste_from_stats(self.win))
        if time.time() - getattr(self, "_prof_t", 0) > 600:        # карточка профиля — если изменилась
            self._prof_t = time.time()
            self.push_profile()
        self._note_together()
        cur = self.shell.current_track()
        k = str(cur.get("path", "")) if cur else None
        if k != self._now_key:
            self._now_key = k
            nd.call(nd.set_now_playing, track_meta(cur))
        now = time.time()
        radio_voice=getattr(self,'_radio_voice',None)
        if nd.room_host is not None and nd.room_host.get('station') is not None and radio_voice is not None:
            radio_voice.want={nd.room_codec()}
        if nd.room_host is not None and nd.room_host.get('station') is None:
            playing = self.shell.is_playing()
            try:
                pos = float(self.win.engine.get_position() or 0)
            except Exception:                                  # noqa: BLE001
                pos = 0.0
            st = {"track": track_meta(cur), "pos": pos, "playing": playing}
            sent = self._sync["sent"]
            need = sent is None or sent["key"] != k or sent["playing"] != playing or now - sent["t"] > 5
            if sent and not need:
                expect = sent["pos"] + ((now - sent["t"]) if sent["playing"] else 0)
                need = abs(expect - pos) > 1.5
            if need:
                self._sync["sent"] = {"key": k, "playing": playing, "pos": pos, "t": now}
                nd.call(nd.room_update, st)
        elif nd.room_guest and nd.room_state:
            self._follow(nd.room_state)
            if now - self._sync["ping_t"] > 10:
                self._sync["ping_t"] = now
                nd.call(nd.room_ping)

    def _follow(self, st):
        tr = st.get("track")
        if not tr:
            return
        now = time.time()
        s = self._sync
        key = track_key(tr)
        cur = self.shell.current_track()
        same = cur is not None and (track_key(cur) == key or (s["follow_path"] and
                                                             str(cur.get("path", "")) == s["follow_path"]))
        if not same:
            if s["follow"] != key or now - s["follow_t"] > 25:
                first = s["follow"] != key
                s["follow"], s["follow_t"] = key, now
                s["follow_path"] = self.play_meta(tr)
                if first and st.get("share") and library_match(self.win, tr)[1] is None and                         self.node.settings.get("room_fetch", True) and self.node.fast_path(self.node.room_guest):
                    self.get_track_from(self.node.room_guest, tr, play=False)   # файл хоста — когда докачается
                elif first and library_match(self.win, tr)[1] is None:
                    self.toast(f"Трека «{tr.get('title')}» нет в вашей коллекции — включаю его онлайн")
            return
        playing = bool(st.get("playing"))
        if playing != self.shell.is_playing() and now - s["toggle_t"] > 2:
            s["toggle_t"] = now
            self.win.toggle_play()
            return
        target = float(st.get("pos") or 0)
        if playing:
            target += self.node.host_clock() - float(st.get("ts") or now)
        eng = self.win.engine
        try:
            dur = float(eng.duration or 0)
            pos = float(eng.get_position() or 0)
        except Exception:                                      # noqa: BLE001
            return
        try:
            self.sync_lbl.setText(f"Синхронизировано с хостом · расхождение {abs(pos - target):.1f} с")
        except (AttributeError, RuntimeError):
            pass
        if dur > 0 and abs(pos - target) > 1.2 and 0 <= target < dur - 2 and now - s["seek_t"] > 4:
            s["seek_t"] = now
            eng.seek(target)

    # ══════════════════════════ ЛЕНТА ══════════════════════════ #

    def _build_feed(self) -> QWidget:
        w = QWidget(); w.setObjectName("YaPage")
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(18)
        self.feed_page = Page(margins=(0, 4, 8, 20))
        h.addWidget(self.feed_page, 1)
        side = QWidget(); side.setObjectName("YaPage")
        side.setFixedWidth(270)
        self.feed_side_w = side                                 # в узком окне прячется (resizeEvent)
        self.feed_side = QVBoxLayout(side)
        self.feed_side.setContentsMargins(0, 4, 0, 0)
        self.feed_side.setSpacing(8)
        h.addWidget(side)
        return w

    COMPOSE = (("post", "Пост"), ("daily", "Трек дня"), ("moment", "Момент"), ("battle", "Баттл"), ("playlist", "Плейлист"),
               ("quiz", "Угадай трек"), ("quote", "Цитата"))

    def _start_card(self) -> QWidget:
        """Первые шаги, пока друзей нет: три понятных действия вместо россыпи кнопок."""
        f, v = card()
        t = lbl("Как начать")
        t.setStyleSheet("font-size:20px;font-weight:900;")
        v.addWidget(t)
        on = self.running()
        steps = (("1", "Включите сеть", "ECHOES сам найдёт путь к друзьям — ничего настраивать не нужно.",
                  None if on else ("Включить сеть", self.toggle_power)),
                 ("2", "Отправьте другу свой код", "Скопируйте и пришлите в любом мессенджере.",
                  ("Скопировать мой код", self.copy_code)),
                 ("3", "Добавьте друга по его коду", "Вкладка «Друзья» → вставьте код → «Отправить заявку». "
                  "Друг увидит заявку, даже если сейчас не в сети.", ("Открыть «Друзья»", lambda: self.show_tab("friends"))))
        for num, title, sub, act in steps:
            h = QHBoxLayout(); h.setSpacing(12)
            n = lbl(num)
            n.setFixedSize(30, 30)
            n.setAlignment(Qt.AlignmentFlag.AlignCenter)
            n.setStyleSheet(f"background:{YELLOW if (num != '1' or not on) else '#2e2e2e'};color:#000;border-radius:15px;"
                            "font-weight:900;font-size:14px;")
            h.addWidget(n, 0, Qt.AlignmentFlag.AlignTop)
            c = QVBoxLayout(); c.setSpacing(0)
            c.addWidget(lbl(title + ("  ✓" if num == "1" and on else ""), "NetName"))
            c.addWidget(lbl(sub, "YaSub", wrap=True))
            h.addLayout(c, 1)
            if act:
                b = ghost_btn(act[0])
                b.clicked.connect(lambda _=False, fn=act[1]: fn())
                h.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
            v.addLayout(h)
        return f

    MAIN_MODES = ("post", "daily")                             # остальные виды постов — в «Ещё»

    def _composer(self) -> QWidget:
        f, v = card()
        mode = getattr(self, "_cmode", "post")
        modes = QHBoxLayout(); modes.setSpacing(6)
        grp = QButtonGroup(f)
        for key, text in [c for c in self.COMPOSE if c[0] in self.MAIN_MODES or c[0] == mode]:
            b = QPushButton(text)
            b.setObjectName("YaChip")
            b.setCheckable(True)
            b.setChecked(key == mode)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("QPushButton#YaChip{padding:6px 12px;font-size:12px;border-radius:12px;}")
            b.clicked.connect(lambda _=False, k=key: (setattr(self, "_cmode", k), self._fill_feed()))
            grp.addButton(b)
            modes.addWidget(b)
        more = QPushButton("Ещё ▾")
        more.setObjectName("YaChip")
        more.setCursor(Qt.CursorShape.PointingHandCursor)
        more.setToolTip("Момент трека, баттл, плейлист, «угадай трек», цитата")
        more.setStyleSheet("QPushButton#YaChip{padding:6px 12px;font-size:12px;border-radius:12px;}")

        def more_menu():
            m = QMenu(self)
            tips = {"moment": "с секунды, где «вот тут дроп»", "battle": "какой из двух треков сильнее",
                    "playlist": "поделиться подборкой", "quiz": "друзья угадывают трек вслепую",
                    "quote": "строчка из песни"}
            for k, t in self.COMPOSE:
                if k not in self.MAIN_MODES:
                    m.addAction(f"{t}  —  {tips.get(k, '')}", lambda k=k: (setattr(self, "_cmode", k), self._fill_feed()))
            m.exec(more.mapToGlobal(more.rect().bottomLeft()))
        more.clicked.connect(more_menu)
        modes.addWidget(more)
        modes.addStretch(1)
        v.addLayout(modes)
        top = QHBoxLayout()
        av = QLabel()
        av.setPixmap(self._av(self.node.me.onion, self.node._name(), 38))
        av.setFixedSize(38, 38)
        top.addWidget(av, 0, Qt.AlignmentFlag.AlignTop)
        self.post_edit = QPlainTextEdit()
        self.post_edit.setPlaceholderText({
            "post": "Что слушаете? Поделитесь треком или мыслью…",
            "daily": "Ваш трек дня — почему именно он? (один в день, попадёт в «Треки дня друзей»)",
            "moment": "Что в этом моменте? «Вот тут дроп — слушай с этой секунды»",
            "battle": "Вопрос баттла: «какой трек сильнее?»",
            "playlist": "Пара слов о подборке",
            "quiz": "Подзадорьте друзей: «угадаете за 30 секунд?»",
            "quote": "Почему эта строчка цепляет?"}[mode])
        self.post_edit.setFixedHeight(64)
        self.post_edit.setPlainText(self._drafts.get("__post", ""))
        self.post_edit.textChanged.connect(lambda: self._drafts.__setitem__("__post", self.post_edit.toPlainText()))
        top.addWidget(self.post_edit, 1)
        v.addLayout(top)
        cur = self.shell.current_track()
        meta = track_meta(cur)
        self._c_extra = {}
        pick = self.__dict__.get("_post_pick")                   # трек из коллекции вместо играющего
        if mode == "daily" and pick:
            v.addWidget(TrackChip(pick["meta"], self.play_meta, cover=pick.get("cover", "")))
        elif mode == "quiz":
            qp = self.__dict__.get("_quiz_pick")                # свой трек: из коллекции / случайный / играющий
            qmeta = qp or (meta if cur else None)
            row = QHBoxLayout()
            if qmeta:
                row.addWidget(TrackChip(qmeta, self.play_meta, compact=True, hidden=True), 1)
            else:
                row.addWidget(lbl("Выберите трек — кнопками справа", "YaSub"), 1)
            for ic, tip, fn in (("search", "Выбрать трек из коллекции", self._quiz_choose),
                                ("shuffle", "Случайный трек из коллекции", self._quiz_random),
                                ("play", "Играющий сейчас", self._quiz_playing)):
                b = icon_button(ic, tip, 34, 16, "#cfcfcf")
                b.clicked.connect(fn)
                row.addWidget(b)
            v.addLayout(row)
            self.c_hint = QLineEdit()
            self.c_hint.setPlaceholderText("Подсказка (жанр, год, первая буква…)")
            v.addWidget(self.c_hint)
            src = "свой выбор" if qp else "играющий трек"
            v.addWidget(lbl(f"Трек: {src}. Друзья услышат 30 секунд вслепую и ответят комментарием — "
                            "ответ проверится сам.", "YaSub", wrap=True))
            live = QHBoxLayout()
            lb = accent_btn("  Играть с друзьями онлайн")
            lb.setIcon(ya_icon("users", 14, "#000000"))
            lb.setToolTip("Живая игра: раунды по 30 секунд, треки — из ваших коллекций вперемешку")
            lb.clicked.connect(lambda: self.quiz_live_start())
            live.addWidget(lb)
            live.addStretch(1)
            v.addLayout(live)
        elif mode in ("moment", "quote", "daily") and not cur:
            v.addWidget(lbl("Включите трек — он станет основой поста." + (" Или выберите его из коллекции ниже."
                                                                         if mode == "daily" else ""), "YaSub"))
        elif mode == "daily":
            v.addWidget(TrackChip(meta, self.play_meta, cover=cur.get("cover", "")))
        elif mode == "moment":
            try:
                pos = float(self.win.engine.get_position() or 0)
            except Exception:                                  # noqa: BLE001
                pos = 0.0
            self._c_extra["at"] = pos
            row = QHBoxLayout()
            row.addWidget(TrackChip(meta, self.play_meta, compact=True, cover=cur.get("cover", ""), at=pos), 1)
            rb = icon_button("clock", "Взять текущую секунду", 34, 18, "#cfcfcf")
            rb.clicked.connect(self._fill_feed)
            row.addWidget(rb)
            v.addLayout(row)
        elif mode == "battle":
            # оба трека можно выбрать самому (поиск по коллекции); по умолчанию — играющий против следующего
            a_meta = getattr(self, "_battle_a", None) or (meta if cur else None)
            b_meta = getattr(self, "_battle_b", None)
            if not b_meta or (a_meta and tkey(b_meta) == tkey(a_meta)):
                b_meta = self._battle_pick(a_meta or {})
            self._battle_b = b_meta
            row = QHBoxLayout()

            def side(m, which):
                box = QHBoxLayout()
                box.setSpacing(4)
                if m:
                    box.addWidget(TrackChip(m, self.play_meta, compact=True,
                                            cover=cur.get("cover", "") if cur and m is meta else ""), 1)
                else:
                    box.addWidget(lbl("выберите трек", "YaSub"), 1)
                pb = icon_button("search", "Выбрать трек из коллекции", 34, 16, "#cfcfcf")
                pb.clicked.connect(lambda: self._battle_choose(which))
                box.addWidget(pb)
                return box
            row.addLayout(side(a_meta, "a"), 1)
            vs = lbl("VS")
            vs.setStyleSheet(f"font-size:18px;font-weight:900;color:{YELLOW};padding:0 6px;")
            row.addWidget(vs)
            row.addLayout(side(b_meta, "b"), 1)
            rr = icon_button("shuffle", "Случайный соперник", 34, 18, "#cfcfcf")
            rr.clicked.connect(lambda: (setattr(self, "_battle_b", self._battle_pick(a_meta or {}, rnd=True)),
                                        self._fill_feed()))
            row.addWidget(rr)
            v.addLayout(row)
            self._c_extra["tracks"] = [a_meta, b_meta] if a_meta and b_meta else []
        elif mode == "playlist":
            self.c_pl = QComboBox()
            for n in self.shell.user_playlists():
                cnt = len(self.win.playlists.get(n, {}).get("tracks", []))
                if cnt:
                    self.c_pl.addItem(f"{n} · {cnt}", n)
            v.addWidget(self.c_pl if self.c_pl.count() else lbl("Нет плейлистов с треками", "YaSub"))
        elif mode == "quote":
            self.c_quote = QLineEdit(current_lyric(self.win))
            self.c_quote.setPlaceholderText("Строчка из песни (если у трека есть синхронный текст — подставится сама)")
            v.addWidget(self.c_quote)
            v.addWidget(TrackChip(meta, self.play_meta, compact=True, cover=cur.get("cover", "")))
        row = QHBoxLayout()
        self.post_track = QPushButton("  Играющий трек", self)  # с родителем — иначе setVisible мелькнёт окном
        self.post_track.setObjectName("YaChip")
        self.post_track.setCheckable(True)
        self.post_track.setIcon(ya_icon("note", 16, "#d0d0d0"))
        self.post_track.setChecked(bool(cur))
        self.post_track.setEnabled(bool(cur))
        self.post_track.setVisible(mode == "post")
        if cur:
            self.post_track.setToolTip(f"{meta['artist']} — {meta['title']}")
        if pick and mode == "post":
            self.post_track.setChecked(False)
            self.post_track.setVisible(False)
        row.addWidget(self.post_track)
        if mode in ("post", "daily"):
            pk = QPushButton(f"  {pick['meta']['title'][:20]}" if pick else "  Из коллекции")
            pk.setObjectName("YaChip")
            pk.setCheckable(True)
            pk.setChecked(bool(pick))
            pk.setIcon(ya_icon("search", 15, "#d0d0d0"))
            pk.setStyleSheet("QPushButton#YaChip{border-radius:13px;}")
            pk.setToolTip(f"{pick['meta']['artist']} — {pick['meta']['title']} · нажмите, чтобы выбрать другой"
                          if pick else "Найти трек в своей коллекции — не обязательно тот, что играет")
            pk.clicked.connect(self._post_pick_track)
            row.addWidget(pk)
            if pick:
                clr = icon_button("close", "Убрать трек из коллекции", 30, 14, "#cfcfcf")
                clr.clicked.connect(lambda: (self.__dict__.pop("_post_pick", None), self._fill_feed()))
                row.addWidget(clr)
        if mode == "post":
            self.post_public = QPushButton("Для всех")
            self.post_public.setObjectName("YaChip")
            self.post_public.setCheckable(True)
            self.post_public.setChecked(self._post_public_on())
            self.post_public.setToolTip("Ещё и в публичную ленту всех пользователей ECHOES (Nostr). Файлы "
                                        "(до 4) раздаёте вы сами через Tor — их видят все")
            self.post_public.setStyleSheet("QPushButton#YaChip{border-radius:13px;}")
            self.post_public.toggled.connect(lambda on: self.__dict__.__setitem__("_post_public", on))
            self.post_public.setEnabled(bool(getattr(self.node, "nostr", None)))
            row.addWidget(self.post_public)
        files = getattr(self, "_post_files_sel", [])
        if mode in ("post", "daily", "moment"):
            gb = QPushButton("GIF ✓" if self.__dict__.get("_post_gif") else "GIF")
            gb.setObjectName("YaChip")
            gb.setToolTip("Анимированная GIF (Tenor / Giphy)")
            gb.setStyleSheet("QPushButton#YaChip{border-radius:13px;font-weight:900;}")
            gb.clicked.connect(lambda: (self.__dict__.pop("_post_gif", None), self._fill_feed())
                               if self.__dict__.get("_post_gif") else self._gif_post())
            row.addWidget(gb)
            att = QPushButton(f"  Файлы · {len(files)}" if files else "  Файлы")
            att.setObjectName("YaChip")
            att.setIcon(ya_icon("plus", 14, "#d0d0d0"))
            att.setStyleSheet("QPushButton#YaChip{border-radius:13px;}")
            att.clicked.connect(self._attach_post)
            row.addWidget(att)
            if files:
                clr = icon_button("close", "Убрать вложения", 30, 14, "#cfcfcf")
                clr.clicked.connect(lambda: (setattr(self, "_post_files_sel", []), self._fill_feed()))
                row.addWidget(clr)
        row.addStretch(1)
        pub = accent_btn("Опубликовать")
        pub.clicked.connect(self._publish)
        row.addWidget(pub)
        v.addLayout(row)
        return f

    def _post_pick_track(self):
        from net_playlist_ui import TrackSearch, track_to_meta
        d = TrackSearch(self.win, self, title="Трек для поста")
        d.file_btn.hide()
        d.ok.setText("Выбрать")
        if d.exec() and d.result_tracks:
            t = d.result_tracks[0]
            self._post_pick = {"meta": track_to_meta(t), "cover": t.get("cover", "")}
        self._fill_feed()

    def _post_public_on(self) -> bool:
        v = self.__dict__.get("_post_public")
        return bool(self.node.settings.get("posts_public", True) if v is None else v)

    def _quiz_choose(self):
        """«Угадай трек»: свой трек — поиск по коллекции."""
        from net_playlist_ui import TrackSearch, track_to_meta
        d = TrackSearch(self.win, self, title="Трек для «Угадай трек»")
        d.file_btn.hide()
        d.ok.setText("Выбрать")
        if d.exec() and d.result_tracks:
            self._quiz_pick = track_to_meta(d.result_tracks[0])
        self._fill_feed()

    def _quiz_random(self):
        lib = [t for t in self.win.library if (t.get("title") or "").strip()]
        if lib:
            self._quiz_pick = track_meta(random.choice(lib))
        self._fill_feed()

    def _quiz_playing(self):
        self._quiz_pick = None
        self._fill_feed()

    def _battle_choose(self, which):
        """Баттл: свой трек слева (a) или справа (b) — поиск по коллекции."""
        from net_playlist_ui import TrackSearch, track_to_meta
        d = TrackSearch(self.win, self, title="Трек для баттла")
        d.file_btn.hide()
        d.ok.setText("Выбрать")
        if d.exec() and d.result_tracks:
            setattr(self, "_battle_" + which, track_to_meta(d.result_tracks[0]))
        self._fill_feed()

    def _battle_pick(self, meta, rnd=False):
        """Соперник для баттла: следующий в очереди, иначе случайный трек коллекции."""
        if not rnd:
            try:
                nxt = self.win._upcoming_tracks(1)[0]
                if nxt and tkey(nxt[0]) != tkey(meta):
                    return track_meta(nxt[0])
            except Exception:                                  # noqa: BLE001
                pass
        lib = [t for t in self.win.library if tkey(t) != tkey(meta)]
        return track_meta(random.choice(lib)) if lib else None

    def _publish(self):
        mode = getattr(self, "_cmode", "post")
        text = self.post_edit.toPlainText().strip()
        cur = self.shell.current_track()
        meta = track_meta(cur)
        kw = {}
        kind = mode
        tr = None
        pick = (self.__dict__.get("_post_pick") or {}).get("meta")
        if mode == "post":
            tr = pick or (meta if self.post_track.isChecked() else None)
            if not text and not tr and not getattr(self, "_post_files_sel", []):
                return
        elif mode == "daily":
            if not cur and not pick:
                return
            tr = pick or meta
        elif mode == "moment":
            if not cur:
                return
            kind, tr, kw["at"] = "post", meta, self._c_extra.get("at", 0)
        elif mode == "battle":
            if len(self._c_extra.get("tracks") or []) != 2:
                return
            kw["tracks"] = self._c_extra["tracks"]
        elif mode == "playlist":
            name = self.c_pl.currentData() if getattr(self, "c_pl", None) is not None and self.c_pl.count() else None
            if not name:
                return
            tracks = self.win.playlists.get(name, {}).get("tracks", [])[:50]
            kw["tracks"] = [track_meta(t) for t in tracks]
            kw["title"] = name
        elif mode == "quiz":
            qp = self.__dict__.get("_quiz_pick")
            if not qp and not cur:
                return
            tr = qp or meta
            kw["hint"] = self.c_hint.text().strip()
            self._quiz_pick = None
        elif mode == "quote":
            q = self.c_quote.text().strip()
            if not cur or not q:
                return
            tr, kw["quote"] = meta, q
        g = self.__dict__.pop("_post_gif", None)
        if g and mode in ("post", "daily", "moment"):
            kw["gif"] = g
        if mode == "post" and self._post_public_on() and getattr(self.node, "nostr", None):
            self.node.call(self.node.publish_public, text, tr, list(getattr(self, "_post_files_sel", []))[:4], g)
        self._send_post(text, tr, kind, **kw)
        self._drafts["__post"] = ""
        self._battle_b = None
        self._battle_a = None
        self.__dict__.pop("_post_pick", None)
        self.post_edit.clear()

    def _send_post(self, text, tr, kind="post", **kw):
        files = getattr(self, "_post_files_sel", [])
        if files and kind in ("post", "daily"):
            if not self.running():
                self.toast("Включите сеть, чтобы опубликовать пост с файлами")
                return
            self._post_files_sel = []
            self.toast(f"Готовлю превью файлов: {len(files)}…")
            self.node.call(self.node.publish_files, text, files, tr, kind, **kw)
            return
        if self.running():
            self.node.call(self.node.publish, text, tr, kind, **kw)
        else:
            self.toast("Сеть выключена — пост сохранён, друзья получат его, когда вы будете в сети")
            import asyncio
            asyncio.run(self.node.publish(text, tr, kind, **kw))   # без цикла: в базу, друзья заберут при sync
            self._fill_feed()

    def _sorted_posts(self):
        st = self.node.store
        posts = st.posts(limit=300)
        me = self.node.me.onion
        if self._feed_sort == "mine":
            posts = [p for p in posts if p["author"] == me]
        if self._feed_sort == "hot":
            activity = st.post_activity(p["id"] for p in posts)
            def hot(p):
                score, comments = activity.get(p["id"], (0, 0))
                age_h = max(0.0, (time.time() - p["ts"]) / 3600)
                return (score + 1 + 0.5 * comments) / ((age_h + 2) ** 1.5)
            posts.sort(key=hot, reverse=True)
        return posts

    def _discard_feed_cards(self):
        widgets = {}
        for name in ("_feed_detached", "_feed_cards"):
            for _signature, widget in self.__dict__.pop(name, {}).values():
                widgets[id(widget)] = widget
        for widget in widgets.values():
            try:
                self.feed_page.v.removeWidget(widget)
                widget.hide()
                widget.deleteLater()
            except RuntimeError:
                pass

    @batch_updates("feed_page", "feed_side_w", on_error="_discard_feed_cards")
    def _fill_feed(self):
        if self.node is None:
            return
        page = self.feed_page
        sb = page.verticalScrollBar()
        keep = sb.value()
        previous_cards = self.__dict__.pop("_feed_cards", {})
        self._feed_detached = previous_cards
        self._feed_cards = {}
        # Keep expensive attachment/reaction widgets when only a composer,
        # another post or the number of visible posts changed.
        for _signature, widget in previous_cards.values():
            page.v.removeWidget(widget)
        page.clear()
        if not self.node.store.contacts("friend"):
            page.v.addWidget(self._start_card())
            page.v.addSpacing(10)
        page.v.addWidget(self._composer())
        srow = QHBoxLayout()
        srow.setContentsMargins(0, 10, 0, 2)
        grp = QButtonGroup(page.inner)
        for key, text in (("hot", "Горячее"), ("new", "Новое"), ("mine", "Мои"), ("all", "Все")):
            b = QPushButton(text)
            b.setObjectName("YaChip")
            b.setCheckable(True)
            b.setChecked(self._feed_sort == key)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: (setattr(self, "_feed_sort", k), self._fill_feed()))
            grp.addButton(b)
            srow.addWidget(b)
        srow.addStretch(1)
        rb = icon_button("repeat", "Обновить ленту у друзей", 34, 18, "#cfcfcf")
        rb.clicked.connect(lambda: self.running() and self.node.call(self.node.refresh))
        srow.addWidget(rb)
        grp.setParent(rb)
        page.v.addLayout(srow)
        self._type_row(page)
        if self._feed_sort == "all":
            for _signature, widget in previous_cards.values():
                widget.hide()
                widget.deleteLater()
            self.__dict__.pop("_feed_detached", None)
            self._fill_public(page)
            page.v.addStretch(1)
            QTimer.singleShot(0, lambda: sb.setValue(keep))
            self._fill_feed_side()
            return
        if not self.__dict__.get("_feed_type"):                 # челлендж недели — над лентой
            try:
                import net_challenge
                page.v.addSpacing(6)
                page.v.addWidget(net_challenge.card(self))
            except Exception as e:                             # noqa: BLE001
                print("[challenge]", e)
        posts = [p for p in self._sorted_posts() if self._type_ok(p) and p.get("kind") != "thread"]  # треды — своя вкладка
        if not posts and self.__dict__.get("_feed_type"):
            page.v.addWidget(lbl("Постов такого типа пока нет.", "YaSub"))
        elif not posts:
            hero = Hero("Здесь будет лента", "Добавьте друзей по коду во вкладке «Друзья» — их посты, треки и "
                        "обсуждения появятся здесь. Серверов нет: всё идёт напрямую через Tor.", height=150)
            page.v.addSpacing(8)
            page.v.addWidget(hero)
        # Виртуальная лента: у каждого поста — лёгкое место (_FeedSlot), карточки строятся только рядом с экраном
        # (_feed_window). Раньше лента строила 30 (потом 12) карточек по десятку кнопок сразу, а «показать ещё»
        # перестраивало всё — вкладка открывалась тяжело, прокрутка дёргалась на полсекунды.
        self._feed_posts = {p["id"]: p for p in posts}
        heights = self.__dict__.setdefault("_feed_heights", {})
        self._feed_slots = OrderedDict()
        for p in posts:
            page.v.addSpacing(6)
            slot = _FeedSlot(p["id"], heights.get(p["id"]) or self._feed_estimate(p))
            page.v.addWidget(slot)
            self._feed_slots[p["id"]] = slot
        self._feed_cards = {}
        first = list(self._feed_slots)[:self.FEED_FIRST]                 # первый экран — сразу, без ожидания тика
        for pid in first + [x for x in self.__dict__.get("_feed_was_open", []) if x not in first]:
            self._feed_put(pid, previous_cards)                          # и то, что было на экране до обновления
        for _signature, widget in previous_cards.values():
            widget.hide()
            widget.deleteLater()
        self.__dict__.pop("_feed_detached", None)
        page.v.addStretch(1)
        if not self.__dict__.get("_feed_hooked"):
            self._feed_hooked = True
            sb.valueChanged.connect(lambda _v: self._feed_window_soon())
            self._feed_vp = page.viewport()
            page.viewport().installEventFilter(self)
        QTimer.singleShot(0, lambda: (sb.setValue(keep), self._feed_window()))
        self._fill_feed_side()

    FEED_FIRST = 6                    # столько карточек строится сразу при заполнении ленты

    def _feed_estimate(self, p) -> int:
        """Высота ещё не построенной карточки — до первого показа (потом запоминается настоящая)."""
        kind = p.get("kind", "post")
        h = 150 + 22 * min(8, len(p.get("text") or "") // 70)
        if kind == "battle":
            h += 190
        elif kind == "playlist":
            h += 200
        elif kind == "quiz":
            h += 150
        elif kind == "repost":
            h += 190
        elif p.get("track"):
            h += 80
        if p.get("files") or p.get("gif"):
            h += 220
        return h

    def _feed_signature(self, p):
        pid = p["id"]
        st = self.node.store
        return (json.dumps((p, st.votes(pid), st.reacts(pid), st.comments(pid)), sort_keys=True, ensure_ascii=False),
                pid in self._open_threads, pid in self._revealed, self._reply_to.get(pid),
                pid in self.__dict__.get("_mod_shown", set()), self._mod_post(p),
                self.__dict__.get("_chat_render_epoch", 0), int(time.time() // 60),
                # Nested polls and expanded comments depend on other
                # posts/moderation events; comments also offer the live track.
                self.__dict__.get("_data_ver", 0) if p.get("orig") or pid in self._open_threads else None,
                tkey(self.shell.current_track() or {}) if pid in self._open_threads else None,
                (frozenset(self._revealed), frozenset(self.__dict__.get("_mod_shown", set())))
                if p.get("orig") else None)

    def _feed_put(self, pid, previous=None):
        """Построить (или взять готовую неизменившуюся) карточку поста в его место. Возвращает изменение высоты."""
        slot = self._feed_slots.get(pid)
        p = self._feed_posts.get(pid)
        if slot is None or p is None or slot.card is not None:
            return 0
        signature = self._feed_signature(p)
        old = (previous or {}).pop(pid, None)
        if old and old[0] == signature:
            widget = old[1]
        else:
            if old:
                old[1].hide()
                old[1].deleteLater()
            widget = self._post_card(p)
        before = slot.height()
        slot.put(widget)
        self._feed_cards[pid] = (signature, widget)
        self._feed_heights[pid] = slot.height()
        return slot.height() - before

    def _feed_drop(self, pid):
        slot = self._feed_slots.get(pid)
        if slot is None or slot.card is None:
            return
        self._feed_heights[pid] = slot.height()
        card = slot.take()
        self._feed_cards.pop(pid, None)
        if card is not None:
            card.hide()
            card.deleteLater()

    def _feed_window_soon(self):
        if not self.__dict__.get("_feed_tick"):
            self._feed_tick = True
            QTimer.singleShot(0, self._feed_window)

    def _feed_window(self):
        """Карточки — только рядом с экраном: видимые сразу, соседние по 2 за тик, далёкие удаляются."""
        self._feed_tick = False
        slots = self.__dict__.get("_feed_slots")
        if not slots or self._feed_sort == "all":
            return
        page = self.feed_page
        sb = page.verticalScrollBar()
        vh = page.viewport().height()
        if vh < 50 or not page.isVisible():
            return
        try:
            places = self._feed_places()
        except RuntimeError:
            return
        top, bot = sb.value(), sb.value() + vh
        # видимое — сразу; соседнее (полтора экрана вверх, два с половиной вниз) — заранее, в паузах между
        # кадрами, не дольше 6 мс за тик: к моменту прокрутки карточки уже готовы
        near_lo, near_hi = top - int(vh * 1.5), bot + int(vh * 2.5)
        far_lo, far_hi = top - vh * 5, bot + vh * 5
        deadline = time.perf_counter() + 0.006
        more, shift = False, 0
        for pid, slot, y, h in places:
            if slot.card is None:
                if y + h < near_lo or y > near_hi:
                    continue
                on_screen = y + h >= top and y <= bot
                if not on_screen and time.perf_counter() > deadline:
                    more = True
                    continue
                d = self._feed_put(pid)
                if y + h <= top:
                    shift += d                           # выросло то, что выше экрана, — экран не должен уехать
            elif y + h < far_lo or y > far_hi:
                self._feed_drop(pid)                     # место сохраняет высоту — сдвигать нечего
        self._feed_was_open = [pid for pid, s in slots.items() if s.card is not None]
        if shift:
            self.feed_page.inner.layout().activate()
            sb.setValue(sb.value() + shift)
        if more:
            QTimer.singleShot(8, self._feed_window_soon)          # следующая порция — после кадра

    def _feed_places(self):
        """[(id, место, y, высота)] — посчитано из фиксированных высот, а не из геометрии Qt: пока раскладка
        ленты не пересчитана (только что заполнили, страница была скрыта), Qt отдаёт старые координаты."""
        page = self.feed_page
        lay = page.v
        sp = lay.spacing()
        width = max(100, page.viewport().width() - 8)
        y = lay.contentsMargins().top()
        out = []
        for i in range(lay.count()):
            it = lay.itemAt(i)
            w = it.widget()
            if isinstance(w, _FeedSlot):
                h = w.minimumHeight()
                out.append((w.pid, w, y, h))
            elif w is not None:
                if w.isHidden():
                    continue
                h = w.heightForWidth(width) if w.hasHeightForWidth() else -1
                h = h if h > 0 else w.sizeHint().height()
            elif it.layout() is not None:
                lh = it.layout()
                h = lh.totalHeightForWidth(width) if lh.hasHeightForWidth() else lh.sizeHint().height()
            else:
                h = it.sizeHint().height()                    # отступ; растяжка в конце — 0
            y += h + sp
        return out

    def eventFilter(self, obj, ev):
        if obj is self.__dict__.get("_feed_vp") and ev.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self._feed_window_soon()
        return QWidget.eventFilter(self, obj, ev)

    KIND_LABEL = {"daily": "трек дня", "battle": "баттл", "playlist": "плейлист", "quiz": "угадай трек", "quote": "цитата",
                  "chal": "челлендж недели",
                  "repost": "репост"}

    def _author_name(self, onion, fallback=""):
        if onion == self.node.me.onion:
            return self.node._name()
        c = self.node.store.contact(onion)
        return (c and c["name"]) or fallback or onion[:8]

    def _post_card(self, p, nested=False) -> QWidget:
        why = self._mod_post(p)
        if why and p["id"] not in self.__dict__.setdefault("_mod_shown", set()):
            return self._mod_stub(why, p["id"])
        return self._post_card_real(p, nested)

    def _mod_post(self, p) -> str:
        """Причина скрыть пост (автор скрыт жалобой / в тексте запрещённое) или ''. Свои посты не трогаем."""
        nd = self.node
        if p.get("author") == nd.me.onion:
            return ""
        orig = p.get("orig") if isinstance(p.get("orig"), dict) else {}
        hid = nd.mod_hidden(p.get("author"), orig.get("author"), p.get("id"), orig.get("id"))
        if hid:
            return hid
        files = " ".join(f.get("name", "") for f in p.get("files") or [] if isinstance(f, dict))
        return nd.mod_check(p.get("text"), p.get("quote"), p.get("title"), p.get("hint"), orig.get("text"), files)

    def _mod_stub(self, why, key):
        f, v = card()
        h = QHBoxLayout()
        ic = lbl("\U000f1005")
        ic.setStyleSheet("font-size:18px;")
        h.addWidget(ic)
        h.addWidget(lbl(f"Скрыто модерацией — {why}", "YaSub", wrap=True), 1)
        sh = ghost_btn("Показать")
        sh.setToolTip("Показать один раз — на свой риск")
        sh.clicked.connect(lambda: (self.__dict__.setdefault("_mod_shown", set()).add(key), self._fill_feed()))
        h.addWidget(sh)
        v.addLayout(h)
        return f

    # ── админка и модерация (net_core: role / staff_act / set_mod) ── #

    ROLE_BADGE = {"admin": ("АДМИН", "Администратор Echoes.NET — автор ECHOES"),
                  "mod": ("МОД", "Модератор Echoes.NET")}

    def _badge(self, onion):
        """Значок у ника: «АДМИН» (заливка акцентом) или «МОД» (обводка)."""
        if self.node is None or not onion:
            return None
        r = self.node.role(onion)
        if not r:
            return None
        text, tip = self.ROLE_BADGE[r]
        b = QLabel(("★ " if r == "admin" else "") + text)
        b.setToolTip(tip)
        if r == "admin":
            b.setStyleSheet(f"background:{YELLOW};color:#000;border-radius:7px;padding:1px 7px;"
                            "font-size:10px;font-weight:900;letter-spacing:1px;")
        else:
            b.setStyleSheet(f"background:transparent;color:{YELLOW};border:1px solid {YELLOW};border-radius:7px;"
                            "padding:0px 6px;font-size:10px;font-weight:900;letter-spacing:1px;")
        b.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        return b

    def _staff_ui(self):
        nd = self.node
        on = bool(nd is not None and nd.my_role())
        b = self.tab_btns.get("admin")
        if b is not None and b.isHidden() == on:
            b.setVisible(on)
        if not on and self._tab == "admin":
            self.show_tab("feed")

    def _staff_menu(self, m, author, post_id, name, preview=""):
        """Пункты модерации в меню «⋯» поста — только у админа и модераторов."""
        nd = self.node
        r = nd.my_role() if nd else ""
        if not r:
            return
        m.addSection("Модерация Echoes.NET")
        hidden = nd.staff_hidden(post_id)
        info = {"name": name, "text": preview}
        if hidden:
            m.addAction("Вернуть пост для всех", lambda: nd.call(nd.staff_act, "unhide", post_id, "post", "", info))
        else:
            m.addAction("Скрыть пост для всех…", lambda: self._staff_ask(
                "Скрыть пост для всех", lambda why: nd.call(nd.staff_act, "hide", post_id, "post", why, info)))
        if author and author != nd.me.onion and not (nd.role(author) and r != "admin") and author != nd.admin_onion:
            if nd.staff_hidden(author):
                m.addAction(f"Разблокировать {name}", lambda: nd.call(nd.staff_act, "unban", author, "user", "",
                                                                       {"name": name}))
            else:
                m.addAction(f"Заблокировать {name} в Echoes.NET…", lambda: self._staff_ask(
                    f"Заблокировать {name}", lambda why: nd.call(nd.staff_act, "ban", author, "user", why,
                                                                  {"name": name})))

    def _staff_ask(self, title, fn):
        from PyQt6.QtWidgets import QInputDialog
        why, ok = QInputDialog.getText(self, title, "Причина (увидят все, можно пусто):")
        if ok:
            fn(why.strip()[:120])

    def _profile_staff_btn(self, o, name):
        """Кнопка «Модерация ▾» в профиле человека."""
        nd = self.node
        r = nd.my_role()
        if not r or o == nd.me.onion or o == nd.admin_onion:
            return None
        b = ghost_btn("  Модерация ▾")
        b.setIcon(ya_icon("settings", 14))

        def menu():
            m = QMenu(self)
            from duel_settings import tr
            from net_radio_auth import issue
            on=not nd.radio_allowed(o)
            if not nd.role(o):
                m.addAction(tr(self.win,'Разрешить вести радио','Allow radio hosting') if on else tr(self.win,'Отозвать разрешение на радио','Revoke radio hosting'),
                            lambda:nd.call(issue,nd,o,on))
            if not (nd.role(o) and r != "admin"):
                if nd.staff_hidden(o):
                    m.addAction("Разблокировать в Echoes.NET", lambda: nd.call(nd.staff_act, "unban", o, "user", "",
                                                                               {"name": name}))
                else:
                    m.addAction("Заблокировать в Echoes.NET…", lambda: self._staff_ask(
                        f"Заблокировать {name}", lambda why: nd.call(nd.staff_act, "ban", o, "user", why,
                                                                      {"name": name})))
            if r == "admin":
                if nd.role(o) == "mod":
                    m.addAction("Снять модерку", lambda: nd.call(nd.set_mod, o, name, False))
                else:
                    m.addAction("Выдать модерку", lambda: nd.call(nd.set_mod, o, name, True))
            m.exec(b.mapToGlobal(b.rect().bottomLeft()))
        b.clicked.connect(menu)
        return b

    def _build_admin(self) -> QWidget:
        self.admin_page = Page(margins=(0, 4, 8, 20))
        return self.admin_page

    def _fill_admin(self):
        nd = self.node
        page = self.admin_page
        page.clear()
        if nd is None or not nd.my_role():
            page.v.addWidget(lbl("Админка доступна только администратору и модераторам Echoes.NET.", "YaSub"))
            page.v.addStretch(1)
            return
        r = nd.my_role()
        f, v = card()
        h = QHBoxLayout()
        bd = self._badge(nd.me.onion)
        h.addWidget(lbl("Вы — администратор Echoes.NET" if r == "admin" else "Вы — модератор Echoes.NET", "Big"))
        if bd is not None:
            h.addWidget(bd)
        h.addStretch(1)
        v.addLayout(h)
        v.addWidget(lbl("Права проверяются подписью: модераторов назначает только администратор, а каждое действие "
                        "подписано тем, кто его сделал. Скрытые посты и блокировки применяются у всех пользователей "
                        "ECHOES. Скрыть пост или заблокировать автора — в меню «⋯» у поста или кнопкой «Модерация» "
                        "в профиле.", "YaSub", wrap=True))
        page.v.addWidget(f)
        from duel_settings import tr
        inbox=ghost_btn(tr(self.win,'Баг-репорты пользователей','User bug reports'))
        inbox.setIcon(ya_icon('bug',16));inbox.clicked.connect(lambda:self.open_bug_report(inbox=True));page.v.addWidget(inbox)
        # модераторы
        page.v.addSpacing(10)
        f, v = card()
        v.addWidget(lbl("МОДЕРАТОРЫ", "Section"))
        mods = nd.mods()
        if not mods:
            v.addWidget(lbl("Пока нет.", "YaSub"))
        for o, ent in sorted(mods.items(), key=lambda kv: -float(kv[1].get("ts") or 0)):
            row = QHBoxLayout()
            av = QLabel(); av.setFixedSize(30, 30)
            nm = ent.get("name") or (self._name(o) if nd.store.contact(o) else o[:8])
            av.setPixmap(self._av(o, nm, 30))
            row.addWidget(self._clickable(av, o))
            row.addWidget(lbl(nm, "NetName"))
            b2 = self._badge(o)
            if b2 is not None:
                row.addWidget(b2)
            row.addWidget(lbl(o[:10] + "…", "YaSub"), 1)
            if r == "admin":
                rm = ghost_btn("Снять модерку")
                rm.clicked.connect(lambda _=False, o=o, nm=nm: nd.call(nd.set_mod, o, nm, False))
                row.addWidget(rm)
            v.addLayout(row)
        if r == "admin":
            add = QHBoxLayout()
            code = QLineEdit(); code.setPlaceholderText("Код Echoes.NET человека (echoes:…)")
            nm_e = QLineEdit(); nm_e.setPlaceholderText("Имя"); nm_e.setMaximumWidth(180)
            gb = accent_btn("Выдать модерку")
            gb.clicked.connect(lambda: (nd.call(nd.set_mod, code.text().strip(), nm_e.text().strip(), True),
                                        code.clear(), nm_e.clear()))
            add.addWidget(code, 1)
            add.addWidget(nm_e)
            add.addWidget(gb)
            v.addLayout(add)
            if nd.store.contacts("friend"):
                v.addWidget(lbl("или из друзей:", "YaSub"))
                fr = QHBoxLayout()
                pick = QComboBox()
                for c in nd.store.contacts("friend"):
                    if not nd.role(c["onion"]):
                        pick.addItem(self._name(c["onion"]), c["onion"])
                fr.addWidget(pick, 1)
                fb = ghost_btn("Выдать другу")
                fb.clicked.connect(lambda: pick.currentData() and nd.call(nd.set_mod, pick.currentData(),
                                                                          pick.currentText(), True))
                fr.addWidget(fb)
                v.addLayout(fr)
        page.v.addWidget(f)
        # блокировки
        page.v.addSpacing(10)
        f, v = card()
        bans = sorted(nd.banned(), key=lambda a: -float(a.get("ts") or 0))
        v.addWidget(lbl(f"ЗАБЛОКИРОВАННЫЕ · {len(bans)}", "Section"))
        if not bans:
            v.addWidget(lbl("Никого.", "YaSub"))
        for a in bans[:100]:
            row = QHBoxLayout()
            who = (a.get("info") or {}).get("name") or a["target"][:10]
            by = "админ" if nd.role(a["by"]) == "admin" else (nd.mods().get(a["by"]) or {}).get("name", "модератор")
            row.addWidget(lbl(who, "NetName"))
            row.addWidget(lbl(f"{a.get('why') or 'без причины'} · {by} · {ago(a['ts'])}", "YaSub", wrap=True), 1)
            ub = ghost_btn("Разблокировать")
            ub.clicked.connect(lambda _=False, a=a: nd.call(nd.staff_act, "unban", a["target"], "user", "",
                                                            a.get("info")))
            row.addWidget(ub)
            v.addLayout(row)
        page.v.addWidget(f)
        # скрытые посты
        page.v.addSpacing(10)
        f, v = card()
        hid = sorted(nd.hidden_posts(), key=lambda a: -float(a.get("ts") or 0))
        v.addWidget(lbl(f"СКРЫТЫЕ ПОСТЫ · {len(hid)}", "Section"))
        if not hid:
            v.addWidget(lbl("Нет.", "YaSub"))
        for a in hid[:100]:
            row = QHBoxLayout()
            inf = a.get("info") or {}
            row.addWidget(lbl(f"{inf.get('name') or 'автор'}: «{inf.get('text') or a['target'][:10]}»", "NetName",
                              wrap=True), 1)
            row.addWidget(lbl(f"{a.get('why') or ''} · {ago(a['ts'])}", "YaSub"))
            ub = ghost_btn("Вернуть")
            ub.clicked.connect(lambda _=False, a=a: nd.call(nd.staff_act, "unhide", a["target"], "post", "",
                                                            a.get("info")))
            row.addWidget(ub)
            v.addLayout(row)
        page.v.addWidget(f)
        page.v.addStretch(1)

    def _report_menu(self, m, target, extra=(), name=""):
        """Пункт «Пожаловаться…» с причинами: автор скрывается у вас и у друзей."""
        sub = m.addMenu("Пожаловаться и скрыть…")
        from net_moderation import CATEGORY
        for why in list(CATEGORY.values()) + ["спам", "оскорбления и травля", "другое"]:
            sub.addAction(why.capitalize(), lambda w=why: (self.node.call(self.node.report, target, w, tuple(extra)),
                                                          self.toast(f"Жалоба отправлена — {name or 'автор'} скрыт(а) "
                                                                     "у вас и у друзей")))

    def _post_card_real(self, p, nested=False) -> QWidget:
        st = self.node.store
        me = self.node.me.onion
        pid = p["id"]
        kind = p.get("kind", "post")
        meta = safe_track(p.get("track"))
        coms = st.comments(pid) if not nested else []
        f = QFrame(); f.setObjectName("NetCard")
        aura = meta or (safe_track((p.get("tracks") or [None])[0]) if p.get("tracks") else None) or \
            (safe_track((p.get("orig") or {}).get("track")) if kind == "repost" else None)
        h = QHBoxLayout(f)
        h.setContentsMargins(10 if not nested else 14, 12, 16, 12)
        h.setSpacing(10)
        if not nested:
            up, dn = st.score(pid)
            mine = st.my_vote(pid, me)
            vc = QVBoxLayout(); vc.setSpacing(0)
            bu = QPushButton(); bu.setObjectName("NetVote"); bu.setFixedSize(32, 30)
            bu.setIcon(ya_icon("up", 18, YELLOW if mine > 0 else "#9a9a9a")); bu.setIconSize(QSize(18, 18))
            bu.setCursor(Qt.CursorShape.PointingHandCursor); bu.setToolTip("Апвоут")
            bu.clicked.connect(lambda: self._vote(pid, 0 if mine > 0 else 1))
            sc = lbl(str(up - dn))
            sc.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sc.setStyleSheet(f"font-weight:900;font-size:14px;color:"
                             f"{YELLOW if mine > 0 else '#ff6b6b' if mine < 0 else '#fff'};")
            bd = QPushButton(); bd.setObjectName("NetVote"); bd.setFixedSize(32, 30)
            bd.setIcon(ya_icon("down", 18, "#ff6b6b" if mine < 0 else "#9a9a9a")); bd.setIconSize(QSize(18, 18))
            bd.setCursor(Qt.CursorShape.PointingHandCursor); bd.setToolTip("Даунвоут")
            bd.clicked.connect(lambda: self._vote(pid, 0 if mine < 0 else -1))
            vc.addWidget(bu); vc.addWidget(sc); vc.addWidget(bd); vc.addStretch(1)
            h.addLayout(vc)
        body = QVBoxLayout(); body.setSpacing(8)
        head = QHBoxLayout(); head.setSpacing(10)
        name = self._author_name(p["author"], p.get("name", ""))
        av = QLabel(); av.setFixedSize(34, 34)
        av.setPixmap(self._av(p["author"], name, 34, None if p["author"] == me or nested
                               else self._online(p["author"])))
        head.addWidget(self._clickable(av, p["author"]))
        nm = QVBoxLayout(); nm.setSpacing(0)
        nrow = QHBoxLayout(); nrow.setSpacing(8)
        nrow.addWidget(self.name_widget(p["author"], name))
        if p["author"] == me:
            nrow.addWidget(lbl("· вы", "YaSub"))
        bd = self._badge(p["author"])
        if bd is not None:
            nrow.addWidget(bd)
        tag = self.KIND_LABEL.get(kind) or ("момент" if p.get("at") is not None else "")
        if tag:
            t = lbl(tag.upper())
            t.setStyleSheet(f"background:rgba(255,219,26,0.16);color:{YELLOW};border-radius:8px;padding:1px 7px;"
                            "font-size:10px;font-weight:900;letter-spacing:1px;")
            nrow.addWidget(t)
        nrow.addStretch(1)
        nm.addLayout(nrow)
        nm.addWidget(lbl(ago(p["ts"]), "YaSub"))
        head.addLayout(nm, 1)
        if not nested:
            dl = icon_button("dots", "Ещё", 30, 16, "#9a9a9a")
            dl.clicked.connect(lambda: self._post_menu(p, dl))
            head.addWidget(dl, 0, Qt.AlignmentFlag.AlignTop)
        body.addLayout(head)
        if p.get("text"):
            body.addWidget(lbl(p["text"], "NetText", wrap=True, sel=True))
        if p.get("files"):
            body.addWidget(self._post_files(p))
        if p.get("gif"):
            body.addWidget(self._gif_widget(p["gif"], 420))
        if kind == "mod":
            body.addWidget(self._mod_in_feed(p))
        marks = [(float(c["at"]), self._author_name(c["author"], c.get("name", "")), c.get("text", ""))
                 for c in coms if isinstance(c.get("at"), (int, float))]

        def play(m, at=None, marks=marks):
            self.play_meta(m, at, live=marks if tkey(m) == tkey(meta) else None)

        if kind == "battle":
            body.addWidget(self._battle_block(p, nested))
        elif kind == "playlist":
            body.addWidget(self._playlist_block(p))
        elif kind == "quiz":
            body.addWidget(self._quiz_block(p, meta))
        elif kind == "chal":
            import net_challenge
            body.addWidget(net_challenge.block(self, p))
        elif kind == "repost" and isinstance(p.get("orig"), dict):
            body.addWidget(self._post_card(p["orig"], nested=True))
        else:
            if kind == "quote" and p.get("quote"):
                body.addWidget(QuoteBlock(p["quote"], meta or {}))
            if meta:
                body.addWidget(TrackChip(meta, play, at=p.get("at"), page=self, cover=self._local_cover(meta),
                                         owner=p["author"]))
                if marks:
                    body.addWidget(TimelineMarks(meta.get("duration"), marks, lambda s, m=meta: play(m, s)))
        if not nested:
            counts = st.react_counts(pid, "emo")
            if any(k.startswith("c:") for k in counts):                 # картинки чужих реакций — на диск
                import net_reactions
                net_reactions.keep(st.reacts(pid))
            body.addWidget(ReactBar(counts, st.my_react(pid, me, "emo"),
                                    lambda e: self._react(pid, "emo", e), on_manage=self._reactions_dialog))
            n = len(coms)
            foot = QHBoxLayout(); foot.setSpacing(4)
            cb = QPushButton(f"  {n} " + _plural(n, "комментарий", "комментария", "комментариев"))
            cb.setObjectName("NetLink")
            cb.setIcon(ya_icon("chat", 16, "#9a9a9a"))
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.clicked.connect(lambda: self._toggle_thread(pid))
            foot.addWidget(cb)
            rp = QPushButton("  Репост")
            rp.setObjectName("NetLink")
            rp.setIcon(ya_icon("repeat", 16, "#9a9a9a"))
            rp.setCursor(Qt.CursorShape.PointingHandCursor)
            rp.setToolTip("Поделиться с вашими друзьями (подпись автора сохраняется)")
            rp.clicked.connect(lambda: self._repost(p))
            foot.addWidget(rp)
            relay = [safe_track(c.get("track")) for c in coms if c.get("track")]
            relay = [x for x in relay if x]
            if relay:
                rl = QPushButton(f"  Эстафета · {len(relay) + (1 if meta else 0)}")
                rl.setObjectName("NetLink")
                rl.setIcon(ya_icon("play", 14, YELLOW))
                rl.setCursor(Qt.CursorShape.PointingHandCursor)
                rl.setToolTip("Трек поста и все треки-ответы из комментариев подряд")
                rl.clicked.connect(lambda: self.play_many(([meta] if meta else []) + relay, "эстафета"))
                foot.addWidget(rl)
            foot.addStretch(1)
            body.addLayout(foot)
            if pid in self._open_threads:
                body.addWidget(self._thread_box(p, coms))
        h.addLayout(body, 1)
        if aura:                          # стиль — в конце: иначе каждый добавленный виджет перестилизовался заново
            f.setStyleSheet(aura_qss(aura))
        return f

    def _local_cover(self, meta) -> str:
        _i, t = library_match(self.win, meta)
        return (t or {}).get("cover", "") or ""

    def _battle_block(self, p, nested=False) -> QWidget:
        st = self.node.store
        me = self.node.me.onion
        pid = p["id"]
        tracks = [safe_track(t) for t in (p.get("tracks") or [])[:2]]
        counts = st.react_counts(pid, "pick")
        mine = st.my_react(pid, me, "pick")
        total = sum(counts.values())
        show = bool(mine) or p["author"] == me
        w = QWidget(); w.setObjectName("YaPage")
        hl = QHBoxLayout(w); hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(10)
        for i, t in enumerate(tracks):
            if i == 1:
                vs = lbl("VS")
                vs.setStyleSheet(f"font-size:20px;font-weight:900;color:{YELLOW};")
                hl.addWidget(vs)
            col = QVBoxLayout(); col.setSpacing(6)
            if t:
                col.addWidget(TrackChip(t, self.play_meta, compact=True, page=self, cover=self._local_cover(t)))
            n = counts.get(str(i), 0)
            if show:
                col.addWidget(BattleBar(n / total if total else 0.0, mine == str(i)))
                col.addWidget(lbl(f"{round(100 * n / total) if total else 0}% · {n} "
                                  + _plural(n, "голос", "голоса", "голосов"), "YaSub"))
            if not nested:                                     # в репосте голосуют у автора — тут только смотреть
                pick = ghost_btn("✓ Ваш выбор") if mine == str(i) else accent_btn("Этот лучше")
                pick.clicked.connect(lambda _=False, i=i: self._react(pid, "pick", "" if mine == str(i) else str(i)))
                col.addWidget(pick)
            hl.addLayout(col, 1)
        if not show:
            w.setToolTip("Голосуйте — результат откроется после выбора")
        return w

    def _playlist_block(self, p) -> QWidget:
        tracks = [x for x in (safe_track(t) for t in p.get("tracks") or []) if x]
        f = QFrame(); f.setObjectName("NetTrack")
        f.setStyleSheet("QFrame#NetTrack{background:rgba(0,0,0,0.35);border-radius:12px;}")
        v = QVBoxLayout(f); v.setContentsMargins(12, 10, 12, 10); v.setSpacing(4)
        t = lbl(f"{p.get('title') or 'Плейлист'}  ·  {len(tracks)} " + _plural(len(tracks), "трек", "трека", "треков"))
        t.setStyleSheet("font-size:15px;font-weight:900;")
        v.addWidget(t)
        for x in tracks[:5]:
            r = lbl(QFontMetrics(ya_font(12)).elidedText(f"{x['artist']} — {x['title']}",
                                                         Qt.TextElideMode.ElideRight, 420), "YaSub")
            v.addWidget(r)
        if len(tracks) > 5:
            v.addWidget(lbl(f"и ещё {len(tracks) - 5}…", "YaSub"))
        row = QHBoxLayout()
        pl = accent_btn("  Слушать")
        pl.setIcon(ya_icon("play", 14, "#000000"))
        pl.clicked.connect(lambda: self.play_many(tracks, p.get("title") or "плейлист"))
        sh = ghost_btn("  Вперемешку")
        sh.setIcon(ya_icon("shuffle", 14))
        sh.clicked.connect(lambda: self.play_many(random.sample(tracks, len(tracks)), p.get("title") or "плейлист"))
        sv = ghost_btn("  Сохранить себе")
        sv.setIcon(ya_icon("plus", 14))
        sv.clicked.connect(lambda: self._save_playlist(p, tracks))
        row.addWidget(pl); row.addWidget(sh); row.addWidget(sv); row.addStretch(1)
        v.addLayout(row)
        return f

    def _save_playlist(self, p, tracks):
        base = f"{p.get('title') or 'Плейлист'} · от {self._author_name(p['author'], p.get('name', ''))}"
        name, k = base, 2
        while name in self.win.playlists:
            name, k = f"{base} ({k})", k + 1
        items = items_for(self.win, tracks)
        self.win.playlist_add_tracks(name, items)
        try:
            self.shell.refresh_sidebar()
        except Exception:                                      # noqa: BLE001
            pass
        self.toast(f"Плейлист «{name}» сохранён: {len(items)} тр.")

    def _quiz_solved(self, p) -> bool:
        me = self.node.me.onion
        return p["author"] == me or self.node.store.my_react(p["id"], me, "solved") == "1" or \
            p["id"] in self._revealed

    def _quiz_block(self, p, meta) -> QWidget:
        st = self.node.store
        pid = p["id"]
        solved = st.react_counts(pid, "solved").get("1", 0)
        w = QWidget(); w.setObjectName("YaPage")
        v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(6)
        if not meta:
            return w
        if self._quiz_solved(p):
            v.addWidget(TrackChip(meta, self.play_meta, page=self, cover=self._local_cover(meta)))
            v.addWidget(lbl(f"Угадали: {solved}", "YaSub"))
            return w
        v.addWidget(TrackChip(meta, self.play_meta, hidden=True, page=self))
        if p.get("hint"):
            v.addWidget(lbl(f"Подсказка: {p['hint']}", "YaSub", wrap=True))
        row = QHBoxLayout()
        pv = accent_btn("  30 секунд вслепую")
        pv.setIcon(ya_icon("wave", 14, "#000000"))
        pv.clicked.connect(lambda: self.preview(meta))
        gu = ghost_btn("  Ответить")
        gu.setIcon(ya_icon("chat", 14))
        gu.clicked.connect(lambda: (self._open_threads.add(pid), self._fill_feed()))
        gv = ghost_btn("Сдаться")
        gv.clicked.connect(lambda: (self._revealed.add(pid), self._fill_feed()))
        row.addWidget(pv); row.addWidget(gu); row.addWidget(gv); row.addStretch(1)
        v.addLayout(row)
        v.addWidget(lbl(f"Угадали: {solved} · ответ — комментарием, проверится сам", "YaSub"))
        return w

    def _thread_box(self, p, coms) -> QWidget:
        pid = p["id"]
        meta = safe_track(p.get("track"))
        hide_answers = p.get("kind") == "quiz" and not self._quiz_solved(p)
        w = QWidget(); w.setObjectName("YaPage")
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(6)
        by_parent: dict[str, list] = {}
        ids = {c["id"] for c in coms}
        for c in coms:
            par = c.get("parent") if c.get("parent") in ids else ""
            by_parent.setdefault(par, []).append(c)

        def add(c, depth):
            row = QHBoxLayout()
            row.setContentsMargins(min(depth, 3) * 30, 0, 0, 0)
            row.setSpacing(8)
            nm = self._author_name(c["author"], c.get("name", ""))
            av = QLabel(); av.setFixedSize(24, 24)
            av.setPixmap(self._av(c["author"], nm, 24))
            row.addWidget(self._clickable(av, c["author"]), 0, Qt.AlignmentFlag.AlignTop)
            col = QVBoxLayout(); col.setSpacing(3)
            hl = QHBoxLayout(); hl.setSpacing(8)
            hl.addWidget(lbl(nm, "NetName"))
            hl.addWidget(lbl(ago(c["ts"]), "YaSub"))
            if isinstance(c.get("at"), (int, float)) and meta:
                mb = QPushButton(f"▶ {fmt_sec(c['at'])}")
                mb.setCursor(Qt.CursorShape.PointingHandCursor)
                mb.setToolTip("Включить трек поста с этой секунды")
                mb.setStyleSheet(f"QPushButton{{background:rgba(255,219,26,0.16);color:{YELLOW};border-radius:9px;"
                                 "padding:1px 8px;font-size:11px;font-weight:800;}")
                mb.clicked.connect(lambda _=False, s=c["at"]: self.play_meta(meta, s))
                hl.addWidget(mb)
            rp = QPushButton("Ответить"); rp.setObjectName("NetLink"); rp.setCursor(Qt.CursorShape.PointingHandCursor)
            rp.clicked.connect(lambda _=False, cid=c["id"], n=nm: self._reply(pid, cid, n))
            hl.addWidget(rp)
            hl.addStretch(1)
            col.addLayout(hl)
            text = c.get("text", "")
            cwhy = "" if c["author"] == self.node.me.onion else \
                (self.node.mod_hidden(c["author"], c.get("id")) or self.node.mod_check(text))
            if cwhy:
                t = lbl(f"\U000f1005 комментарий скрыт модерацией — {cwhy}", "YaSub")
                col.addWidget(t)
            elif hide_answers and meta and guess_ok(text, meta):
                t = lbl("✓ угадал(а) — ответ скрыт, пока вы не угадаете", "YaSub")
                t.setStyleSheet("color:#3ddc84;font-weight:700;")
                col.addWidget(t)
            elif text:
                col.addWidget(lbl(text, "NetText", wrap=True, sel=True))
            if c.get("track"):
                col.addWidget(TrackChip(c["track"], self.play_meta, compact=True, page=self))
            row.addLayout(col, 1)
            v.addLayout(row)
            for ch in by_parent.get(c["id"], []):
                add(ch, depth + 1)

        for c in by_parent.get("", []):
            add(c, 0)
        inp = QHBoxLayout()
        cur = self.shell.current_track()
        tb = icon_button("note", "Ответить треком: прикрепить играющий (эстафета)", 34, 16, "#cfcfcf", checkable=True)
        tb.setEnabled(bool(cur) and p.get("kind") != "quiz")
        inp.addWidget(tb)
        at_btn = None
        if meta and cur is not None and tkey(cur) == tkey(meta) and p.get("kind") != "quiz":
            try:
                pos = float(self.win.engine.get_position() or 0)
            except Exception:                                  # noqa: BLE001
                pos = 0.0
            at_btn = QPushButton(f"на {fmt_sec(pos)}")
            at_btn.setCheckable(True)
            at_btn.setChecked(True)
            at_btn.setObjectName("YaChip")
            at_btn.setToolTip("Привязать комментарий к этой секунде трека — он всплывёт у друзей в этот момент")
            at_btn.setStyleSheet("QPushButton#YaChip{padding:6px 10px;font-size:12px;border-radius:12px;}")
            at_btn.pos_ = pos
            inp.addWidget(at_btn)
        e = QLineEdit()
        rt = self._reply_to.get(pid)
        e.setPlaceholderText(f"Ответ для {rt[1]}…" if rt else
                             ("Ваш ответ: название трека…" if p.get("kind") == "quiz" else "Написать комментарий…"))
        e.setText(self._drafts.get(pid, ""))
        e.textChanged.connect(lambda s: self._drafts.__setitem__(pid, s))
        send = (lambda: self._send_comment(p, e, tb.isChecked(),
                                           at_btn.pos_ if at_btn is not None and at_btn.isChecked() else None))
        e.returnPressed.connect(send)
        inp.addWidget(e, 1)
        if rt:
            x = icon_button("close", "Не отвечать", 30, 14, "#9a9a9a")
            x.clicked.connect(lambda: (self._reply_to.pop(pid, None), self._fill_feed()))
            inp.addWidget(x)
        sb = icon_button("send", "Отправить", 36, 18, YELLOW)
        sb.clicked.connect(send)
        inp.addWidget(sb)
        v.addLayout(inp)
        if rt:
            QTimer.singleShot(0, e.setFocus)
        return w

    def _toggle_thread(self, pid):
        self._open_threads.symmetric_difference_update({pid})
        self._fill_feed()

    def _reply(self, pid, cid, name):
        self._reply_to[pid] = (cid, name)
        self._fill_feed()

    def _send_comment(self, p, e, with_track=False, at=None):
        pid = p["id"]
        text = e.text().strip()
        tr = track_meta(self.shell.current_track()) if with_track else None
        if not text and not tr:
            return
        if not self.running():
            self.toast("Включите сеть, чтобы комментировать")
            return
        if p.get("kind") == "quiz" and not self._quiz_solved(p):
            meta = safe_track(p.get("track"))
            if guess_ok(text, meta):
                self.node.call(self.node.react, pid, "solved", "1")
                self.toast("Угадали! Ответ открыт")
            else:
                self.toast("Мимо! Попробуйте ещё — или «Сдаться»")
        parent = self._reply_to.pop(pid, ("", ""))[0]
        self._drafts.pop(pid, None)
        self.node.call(self.node.comment, pid, text, parent, tr, at)

    def _vote(self, pid, val):
        if not self.running():
            self.toast("Включите сеть, чтобы голосовать")
            return
        self.node.call(self.node.vote, pid, val)

    def _react(self, pid, kind, val):
        if not self.running():
            self.toast("Включите сеть, чтобы реагировать")
            return
        self.node.call(self.node.react, pid, kind, val)

    def _repost(self, p):
        if not self.running():
            self.toast("Включите сеть, чтобы делать репосты")
            return
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "Репост", "Пара слов от вас (можно пусто):")
        if ok:
            orig = p.get("orig") if p.get("kind") == "repost" else p
            self.node.call(self.node.publish, text.strip(), None, "repost", orig=orig)
            self.toast("Репост ушёл друзьям")

    def _post_menu(self, p, btn):
        m = QMenu(self)
        if p["author"] != self.node.me.onion:
            self._report_menu(m, p["author"], name=self._author_name(p["author"], p.get("name", "")))
            m.addSeparator()
        self._staff_menu(m, p["author"], p["id"], self._author_name(p["author"], p.get("name", "")),
                         (p.get("title") or p.get("text") or "")[:80])
        meta = safe_track(p.get("track"))
        if meta and p.get("kind") != "quiz":
            m.addAction("Отправить трек другу…", lambda: self._share_to_friend(meta))
        if p.get("text"):
            m.addAction("Скопировать текст", lambda: QGuiApplication.clipboard().setText(p["text"]))
        if p["author"] == self.node.me.onion:
            m.addSeparator()
            m.addAction("Удалить пост (и у друзей)",
                        lambda: self.running() and self.node.call(self.node.delete_post, p["id"]))
        m.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _share_to_friend(self, meta):
        friends = self.node.store.contacts("friend")
        if not friends:
            self.toast("Сначала добавьте друзей")
            return
        m = QMenu(self)
        for c in friends:
            m.addAction(c["name"] or c["onion"][:8],
                        lambda o=c["onion"]: (self.node.call(self.node.send_message, o, "", meta),
                                              self.toast("Трек отправлен")))
        m.exec(QCursor.pos())

    def _fill_feed_side(self):
        _clear_layout(self.feed_side)
        self.feed_side.addWidget(lbl("СЕЙЧАС СЛУШАЮТ", "Section"))
        friends = self.node.store.contacts("friend")
        live = [c for c in friends if self._online(c["onion"]) and (c["now"] or c["room"] or c.get("game"))]
        if not live:
            self.feed_side.addWidget(lbl("Когда друзья в сети что-то слушают, это видно здесь.", "YaSub", wrap=True))
        for c in live[:8]:
            self.feed_side.addWidget(self._friend_now_card(c))
        chart = self.friends_chart()
        if chart:
            self.feed_side.addSpacing(12)
            hr = QHBoxLayout()
            hr.addWidget(lbl("ЧАРТ ДРУЗЕЙ · НЕДЕЛЯ", "Section"), 1)
            pa = icon_button("play", "Слушать чарт целиком", 28, 14, YELLOW)
            pa.clicked.connect(lambda: self.play_many([m for m, _s in chart], "чарт друзей"))
            hr.addWidget(pa)
            self.feed_side.addLayout(hr)
            for i, (m, score) in enumerate(chart[:7], 1):
                txt = QFontMetrics(ya_font(13)).elidedText(f"{i}.  {m['title']}  ·  {m['artist']}",
                                                           Qt.TextElideMode.ElideRight, 240)
                row = QPushButton(txt)
                row.setCursor(Qt.CursorShape.PointingHandCursor)
                row.setToolTip(f"{m['artist']} — {m['title']} · очки: {score:.0f}")
                row.setStyleSheet("QPushButton{background:transparent;text-align:left;padding:5px 6px;"
                                  "font-weight:700;border-radius:8px;} QPushButton:hover{background:"
                                  "rgba(255,255,255,0.06);}")
                row.clicked.connect(lambda _=False, m=m: self.play_meta(m))
                self.feed_side.addWidget(row)
        self.feed_side.addSpacing(12)
        self.feed_side.addWidget(lbl("ДРУЗЬЯ", "Section"))
        on = sum(1 for c in friends if self._online(c["onion"]))
        self.feed_side.addWidget(lbl(f"{len(friends)} в списке · {on} в сети", "YaSub"))
        add = ghost_btn("  Добавить друга")
        add.setIcon(ya_icon("plus", 16))
        add.clicked.connect(lambda: self.show_tab("friends"))
        self.feed_side.addWidget(add)
        self.feed_side.addStretch(1)

    def friends_chart(self) -> list:
        """Чарт недели по ленте: трек в посте — 2 очка + апвоуты и реакции поста, трек-ответ в треде — 1,
        трек в баттле/плейлисте — 0.5. Свои посты тоже считаются."""
        st = self.node.store
        since = time.time() - 7 * 86400
        score: dict[tuple, list] = {}

        def add(meta, pts):
            m = safe_track(meta)
            if not m:
                return
            k = tkey(m)
            if k not in score:
                score[k] = [m, 0.0]
            score[k][1] += pts
        for p in st.posts(limit=400):
            if p["ts"] < since:
                continue
            if p.get("kind") == "repost":
                p = p.get("orig") or {}
            if p.get("kind") == "quiz":
                continue
            up, dn = st.score(p.get("id", ""))
            emo = sum(st.react_counts(p.get("id", ""), "emo").values())
            add(p.get("track"), 2 + max(0, up - dn) + 0.5 * emo)
            for t in (p.get("tracks") or [])[:50]:
                add(t, 0.5)
            for c in st.comments(p.get("id", "")):
                add(c.get("track"), 1)
        return [(m, s) for m, s in sorted(score.values(), key=lambda x: -x[1]) if s >= 1][:20]

    def compat(self, onion):
        """Совместимость вкусов с другом: (процент, общие исполнители) или (None, [])."""
        import json
        from net_core import taste_match
        c = self.node.store.contact(onion) or {}
        try:
            theirs = json.loads(c.get("taste") or "null")
        except ValueError:
            theirs = None
        mine = getattr(self, "_my_taste", None)
        if mine is None:
            mine = self._my_taste = taste_from_stats(self.win)
        if not theirs or not mine:
            return None, []
        return taste_match(mine, theirs)

    def blend(self, onion):
        """Blend: ваши самые заслушанные треки вперемешку с любимыми треками друга."""
        import json
        c = self.node.store.contact(onion) or {}
        try:
            theirs = (json.loads(c.get("taste") or "null") or {}).get("tracks") or []
        except ValueError:
            theirs = []
        mine = my_top_tracks(self.win, 20)
        if not theirs and not mine:
            self.toast("Пока не из чего смешивать — нужна статистика прослушиваний")
            return
        random.shuffle(mine)
        their_items = items_for(self.win, theirs)
        random.shuffle(their_items)
        mix = []
        for i in range(max(len(mine), len(their_items))):
            if i < len(mine):
                mix.append(mine[i])
            if i < len(their_items):
                mix.append(their_items[i])
        self.win.stream_tracks(mix)
        self.toast(f"Blend с {self._name(onion)}: {len(mix)} тр. — ваши и друга вперемешку")

    def _game_badge(self, game, big=False) -> QLabel:
        """Значок «🎮 Играет в …» (net_game)."""
        b = QLabel(f"\U000f1003  Играет в {game}" if big else f"\U000f1003 {game}")
        b.setToolTip("Друг сейчас в игре")
        b.setStyleSheet("QLabel{background:rgba(57,255,140,0.16);color:#7dffb4;border-radius:%dpx;"
                        "padding:%s;font-weight:800;font-size:%dpx;}" % ((12, "5px 12px", 13) if big else
                                                                         (8, "1px 7px", 11)))
        b.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        return b

    def _friend_now_card(self, c) -> QWidget:
        import json
        f, v = card()
        v.setContentsMargins(12, 10, 12, 10)
        h = QHBoxLayout(); h.setSpacing(10)
        av = QLabel(); av.setFixedSize(32, 32)
        av.setPixmap(self._av(c["onion"], c["name"], 32, True))
        h.addWidget(self._clickable(av, c["onion"]))
        col = QVBoxLayout(); col.setSpacing(0)
        col.addWidget(lbl(c["name"] or c["onion"][:8], "NetName"))
        now = json.loads(c["now"]) if c["now"] else None
        room = json.loads(c["room"]) if c["room"] else None
        txt = f"{now['artist']} — {now['title']}" if now else ""
        sub = lbl(QFontMetrics(ya_font(12)).elidedText(txt or "в сети", Qt.TextElideMode.ElideRight, 170), "YaSub")
        col.addWidget(sub)
        if c.get("game"):
            col.addWidget(self._game_badge(c["game"]))
        h.addLayout(col, 1)
        if now:
            from ya_decor import MiniEq                         # живой мини-эквалайзер — «играет прямо сейчас»
            h.addWidget(MiniEq(), 0, Qt.AlignmentFlag.AlignVCenter)
        v.addLayout(h)
        row = QHBoxLayout()
        if room:
            j = accent_btn(f"Слушать вместе · {room.get('n', 1)}")
            j.clicked.connect(lambda: self.join_room(c["onion"]))
            v.addWidget(j)
        elif now:
            pl = ghost_btn("Включить трек")
            pl.setIcon(ya_icon("play", 14))
            pl.clicked.connect(lambda: self.play_meta(now))
            v.addWidget(pl)
        msg = icon_button("chat", "Написать", 34, 16, "#cfcfcf")
        msg.clicked.connect(lambda: self.open_chat(c["onion"]))
        qz = icon_button("note", "Угадай трек вместе — треки из ваших коллекций", 34, 16, "#cfcfcf")
        qz.clicked.connect(lambda: self.quiz_live_start([c["onion"]]))
        qa = icon_button("queue", "Подкинуть трек в очередь", 34, 16, "#cfcfcf")
        qa.clicked.connect(lambda: __import__("net_queue").pick_and_send(self, c["onion"]))
        row.addStretch(1)
        row.addWidget(qa)
        row.addWidget(qz)
        row.addWidget(msg)
        v.addLayout(row)
        return f

    def add_friends_row(self, page):
        """«Для вас»: друзья сейчас слушают / открытые комнаты (или приглашение в Echoes.NET)."""
        if self.node is None:
            return
        import json
        friends = self.node.store.contacts("friend")
        live = [c for c in friends if self._online(c["onion"]) and (c["now"] or c["room"] or c.get("game"))]
        if live:
            page.v.addWidget(section_title("Друзья сейчас слушают", lambda: self.shell.show_page("net")))
            row = HRow()
            for c in live[:12]:
                w = self._friend_now_card(c)
                w.setFixedSize(280, 158)
                row.add(w)
            page.v.addWidget(row)
        elif not friends:
            page.v.addSpacing(14)
            hero = Hero("Echoes.NET", "Соцсеть прямо в плеере: посты, сообщения и «Слушать вместе» с друзьями. "
                        "Без серверов и регистрации — через Tor.", c1="#ffdb1a", c2="#7a2cff", height=140)
            b = accent_btn("Открыть Echoes.NET")
            b.setMinimumWidth(190)
            b.setMinimumHeight(42)
            b.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            b.clicked.connect(lambda: self.shell.show_page("net"))
            hero.lay.addWidget(b, 0, Qt.AlignmentFlag.AlignLeft)
            page.v.addWidget(hero)
        daily = self.daily_tracks()
        if daily:
            page.v.addWidget(section_title("Треки дня друзей",
                                           lambda: self.play_many([t for t, _o, _n in daily], "треки дня друзей")))
            row = HRow()
            for t, o, n in daily[:14]:
                f, v = card()
                f.setStyleSheet(aura_qss(t))
                f.setFixedSize(250, 128)
                hh = QHBoxLayout()
                av = QLabel(); av.setFixedSize(28, 28)
                av.setPixmap(self._av(o, n, 28))
                hh.addWidget(self._clickable(av, o))
                hh.addWidget(lbl(n, "NetName"), 1)
                v.addLayout(hh)
                v.addWidget(TrackChip(t, self.play_meta, compact=True, cover=self._local_cover(t)))
                row.add(f)
            page.v.addWidget(row)
        _ = json

    def daily_tracks(self) -> list:
        """«Трек дня» друзей (и свой) за последние сутки: [(трек, onion, имя)] — по одному на человека."""
        if self.node is None:
            return []
        out, seen = [], set()
        for p in self.node.store.posts(limit=300):
            if p.get("kind") != "daily" or time.time() - p["ts"] > 86400 or p["author"] in seen:
                continue
            t = safe_track(p.get("track"))
            if t:
                seen.add(p["author"])
                out.append((t, p["author"], self._author_name(p["author"], p.get("name", ""))))
        return out

    # ══════════════════════════ СООБЩЕНИЯ ══════════════════════════ #

    def _build_chats(self) -> QWidget:
        w = QWidget(); w.setObjectName("YaPage")
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 4, 0, 0)
        h.setSpacing(14)
        self.chat_list = QListWidget()
        self.chat_list.setObjectName("NetChats")
        self.chat_list.setFixedWidth(270)
        self.chat_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.chat_list.itemClicked.connect(lambda it: self.open_chat(it.data(Qt.ItemDataRole.UserRole)))
        lc = QVBoxLayout(); lc.setSpacing(8)
        ng = ghost_btn("  Новая группа")
        ng.setIcon(ya_icon("users", 16))
        ng.setFixedWidth(270)
        ng.clicked.connect(self._new_group)
        lc.addWidget(ng)
        lc.addWidget(self.chat_list, 1)
        h.addLayout(lc)
        right, rv = card()
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        self.chat_head = QWidget(); self.chat_head.setObjectName("YaPage")
        self.chat_head_l = QHBoxLayout(self.chat_head)
        self.chat_head_l.setContentsMargins(16, 12, 12, 12)
        rv.addWidget(self.chat_head)
        line = QFrame(); line.setFixedHeight(1); line.setStyleSheet("background:rgba(255,255,255,0.06);")
        rv.addWidget(line)
        self.call_slot = QVBoxLayout()                         # панель звонка (net_call_ui.CallPanel)
        self.call_slot.setContentsMargins(12, 10, 12, 0)
        rv.addLayout(self.call_slot)
        self.chat_view = Page(margins=(16, 12, 16, 12))
        self.chat_view.v.setSpacing(6)
        self.chat_view.setAcceptDrops(True)                    # перетащить файлы в чат — отправить
        self.chat_view.dragEnterEvent = lambda e: e.acceptProposedAction() if e.mimeData().hasUrls() else e.ignore()
        self.chat_view.dragMoveEvent = lambda e: e.acceptProposedAction() if e.mimeData().hasUrls() else e.ignore()
        self.chat_view.dropEvent = lambda e: self.send_files([u.toLocalFile() for u in e.mimeData().urls()
                                                              if u.isLocalFile()])
        rv.addWidget(self.chat_view, 1)
        inp = QHBoxLayout()
        inp.setContentsMargins(12, 8, 12, 12)
        # один «+» вместо россыпи кнопок: файлы, GIF, трек из коллекции, плейлист и музыкальные сообщения
        more = icon_button("plus", "Отправить: файл, GIF, трек из коллекции, плейлист, момент, капсулу…", 38, 18,
                           "#cfcfcf")
        more.clicked.connect(lambda: self._chat_plus(more))
        inp.addWidget(more)
        self.chat_track = icon_button("note", "", 38, 18, "#cfcfcf", checkable=True)
        self.chat_track.hide()                                 # «прикрепить играющий» теперь в меню «+»
        self.chat_edit = QLineEdit()
        self.chat_edit.setPlaceholderText("Сообщение…")
        self.chat_edit.returnPressed.connect(self._send_chat)
        from PyQt6.QtGui import QShortcut, QKeySequence
        sc = QShortcut(QKeySequence.StandardKey.Paste, self.chat_edit)          # Ctrl+V с картинкой — отправить её
        sc.setContext(Qt.ShortcutContext.WidgetShortcut)
        sc.activated.connect(self._paste_chat)
        inp.addWidget(self.chat_edit, 1)
        import net_voicemsg                                    # голосовое: зажать и говорить
        self.chat_rec = net_voicemsg.RecButton(DATA_DIR / "files" / "voice")
        self.chat_rec.done.connect(lambda p: self.send_files([p]))
        inp.addWidget(self.chat_rec)
        sb = icon_button("send", "Отправить", 40, 20, YELLOW)
        sb.clicked.connect(self._send_chat)
        inp.addWidget(sb)
        rv.addLayout(inp)
        h.addWidget(right, 1)
        return w

    def open_chat(self, onion):
        self._chat_peer = onion
        QTimer.singleShot(0, self._call_ui_changed)
        if self._tab != "chats":
            self.shell.show_page("net")
            self.show_tab("chats")
        else:
            self._fill_chat_list()
            self._fill_chat()

    def _peer_title(self, peer) -> str:
        if str(peer).startswith("g:"):
            g = self.node.store.group(peer[2:]) or {}
            return g.get("name") or "Группа"
        return self._name(peer)

    @batch_updates("chat_list")
    def _fill_chat_list(self):
        if self.node is None:
            return
        st = self.node.store
        unread = st.unread()
        rows = [(c["onion"], c["name"] or c["onion"][:8], False) for c in st.contacts() if c["status"] == "friend"]
        known = {r[0] for r in rows}
        for r in st.q("SELECT DISTINCT peer FROM messages"):
            if r["peer"] not in known and not r["peer"].startswith("g:") and st.contact(r["peer"]):
                c = st.contact(r["peer"])
                rows.append((c["onion"], c["name"] or c["onion"][:8], False))
        for g in st.groups():
            rows.append(("g:" + g["id"], g.get("name") or "Группа", True))

        def last_ts(r):
            m = st.last_message(r[0])
            return m["ts"] if m else 0
        rows.sort(key=last_ts, reverse=True)
        self.chat_list.clear()
        if self._chat_peer is None and rows:
            self._chat_peer = rows[0][0]
        for peer, title, is_group in rows:
            it = QListWidgetItem()
            it.setData(Qt.ItemDataRole.UserRole, peer)
            it.setSizeHint(QSize(250, 62))
            self.chat_list.addItem(it)
            row = QWidget(); row.setObjectName("YaPage")
            h = QHBoxLayout(row)
            h.setContentsMargins(10, 8, 10, 8)
            h.setSpacing(10)
            av = QLabel(); av.setFixedSize(40, 40)
            av.setPixmap(avatar_pm(peer, title, 40) if is_group else self._av(peer, title, 40, self._online(peer)))
            h.addWidget(av)
            col = QVBoxLayout(); col.setSpacing(1)
            col.addWidget(lbl(("" if is_group else "") + title, "NetName"))
            m = st.last_message(peer)
            if m:
                who = "Вы: " if m["dir"] == "out" else (((m.get("extra") or {}).get("name") or "") + ": "
                                                         if is_group and (m.get("extra") or {}).get("name") else "")
                prev = who + (m["text"] or "♪ трек")
                if _capsule_locked(m):
                    prev = "Капсула времени"
                elif (m.get("extra") or {}).get("kind") == "cpl":
                    prev = "♫ общий плейлист изменён"
                elif (m.get("extra") or {}).get("kind") == "playlist":
                    prev = who + "Плейлист: " + str((m.get("extra") or {}).get("title") or "")
                elif (m.get("extra") or {}).get("kind") == "gif" and not m["text"]:
                    prev = who + "GIF"
                elif (m.get("extra") or {}).get("kind") == "file":
                    f = (m.get("extra") or {}).get("file") or {}
                    prev = who + {"image": "Фото", "video": "Видео", "audio": "Аудио: "}.get(f.get("kind"), "Файл: ") +                         ("" if f.get("kind") in ("image", "video") else f.get("name", "файл"))
            else:
                prev = "Нет сообщений"
            col.addWidget(lbl(QFontMetrics(ya_font(12)).elidedText(prev.replace("\n", " "),
                                                                    Qt.TextElideMode.ElideRight, 150), "YaSub"))
            h.addLayout(col, 1)
            n = unread.get(peer, 0)
            if n:
                b = lbl(str(n), "YaBadge")
                b.setStyleSheet(f"background:{YELLOW};color:#000;border-radius:9px;font-size:11px;font-weight:800;"
                                "padding:0 6px;")
                b.setFixedHeight(18)
                h.addWidget(b)
            self.chat_list.setItemWidget(it, row)
            if peer == self._chat_peer:
                it.setSelected(True)
        if not rows:
            it = QListWidgetItem("Добавьте друзей, чтобы переписываться")
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.chat_list.addItem(it)

    def _call_ui_changed(self):
        """Звонок начался/закончился/сменился состав — панель над нужной перепиской, кнопки в шапке."""
        c = self.calls
        if c.panel is not None:
            here = bool(c.view) and self._chat_peer == c.call_chat()
            if here and self.call_slot.indexOf(c.panel) < 0:
                self.call_slot.addWidget(c.panel)
            c.panel.setVisible(here)
        if self._tab == "chats" and self._chat_peer:
            self._chat_header()

    def _call_buttons(self, o):
        """Кнопки звонка в шапке переписки."""
        nd = self.node
        c = self.calls
        in_this = bool(c.view) and c.call_chat() == o
        if in_this:
            b = QPushButton("  Завершить")
            b.setIcon(QIcon(__import__("net_call_ui").icon_pm("phone", 16, "#ffffff", off=True)))
            b.setStyleSheet("QPushButton{background:#da373c;color:#fff;border-radius:16px;padding:7px 14px;"
                            "font-weight:800;} QPushButton:hover{background:#e5484d;}")
            b.clicked.connect(c.hang_up)
            return b
        ring = next((dict(r, cid=k) for k, r in nd.rings.items() if (r.get("kind") == "group" and o == "g:" + r.get("gid", ""))
                     or (r.get("kind") == "dm" and r.get("from") == o)), None)
        if o.startswith("g:"):
            b = QPushButton("  Присоединиться к созвону" if ring else "  Созвон")
            b.setToolTip("Голосовой созвон со всеми в группе")
        else:
            b = QPushButton("  Позвонить")
            b.setToolTip("Голосовой звонок")
        b.setIcon(QIcon(__import__("net_call_ui").icon_pm("phone", 16, "#ffffff")))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet("QPushButton{background:#23a55a;color:#fff;border-radius:16px;padding:7px 14px;"
                        "font-weight:800;} QPushButton:hover{background:#2dc26b;}")
        if ring:
            b.clicked.connect(lambda: c.accept(ring["cid"]))
        else:
            b.clicked.connect(lambda: c.start(o))
        return b

    def _chat_header(self):
        _clear_layout(self.chat_head_l)
        o = self._chat_peer
        if not o:
            self.chat_head_l.addWidget(lbl("Выберите чат", "NetName"))
            return
        nd = self.node
        if o.startswith("g:"):
            g = nd.store.group(o[2:]) or {"members": [], "name": "Группа"}
            av = QLabel(); av.setFixedSize(40, 40)
            av.setPixmap(avatar_pm(o, g.get("name", ""), 40))
            self.chat_head_l.addWidget(av)
            col = QVBoxLayout(); col.setSpacing(0)
            col.addWidget(lbl("" + (g.get("name") or "Группа"), "NetName"))
            names = ["вы" if m == nd.me.onion else self._name(m) for m in g.get("members", [])]
            col.addWidget(lbl(QFontMetrics(ya_font(12)).elidedText(f"{len(names)} участн.: " + ", ".join(names),
                                                                    Qt.TextElideMode.ElideRight, 330), "YaSub"))
            self.chat_head_l.addLayout(col, 1)
            self.chat_head_l.addWidget(self._call_buttons(o))
        else:
            c = nd.store.contact(o) or {}
            av = QLabel(); av.setFixedSize(40, 40)
            av.setPixmap(self._av(o, c.get("name", ""), 40, self._online(o)))
            self.chat_head_l.addWidget(self._clickable(av, o))
            col = QVBoxLayout(); col.setSpacing(0)
            nm = lbl(c.get("name") or o[:8], "NetName")
            col.addWidget(self._clickable(nm, o))
            now = json.loads(c["now"]) if c.get("now") else None
            if self._online(o):
                s = f"в сети · слушает {now['artist']} — {now['title']}" if now else "в сети"
                if c.get("game"):
                    s = f"в сети · \U000f1003 {c['game']}" + (f" · {now['artist']} — {now['title']}" if now else "")
            else:
                s = f"был(а) в сети {ago(c['last_seen'])} назад" if c.get("last_seen") else "не в сети"
                s = s.replace("только что назад", "только что")
            col.addWidget(lbl(QFontMetrics(ya_font(12)).elidedText(s, Qt.TextElideMode.ElideRight, 230), "YaSub"))
            self.chat_head_l.addLayout(col, 1)
            if nd.is_friend(o):
                bl = QPushButton("  Blend")
                bl.setObjectName("YaChip")
                bl.setIcon(ya_icon("shuffle", 14, "#e6e6e6"))
                bl.setToolTip("Blend — общий микс: ваши самые заслушанные треки вперемешку с любимыми треками друга")
                bl.setCursor(Qt.CursorShape.PointingHandCursor)
                bl.clicked.connect(lambda _=False, o=o: self.blend(o))
                self.chat_head_l.addWidget(bl)
                self.chat_head_l.addWidget(self._call_buttons(o))
            sk = self.together_streak(o)
            if sk >= 2:
                f = lbl(f"Серия: {sk}")
                f.setToolTip(f"{sk} {_plural(sk, 'день', 'дня', 'дней')} подряд слушаете вместе")
                f.setStyleSheet("font-weight:900;font-size:14px;padding:0 6px;")
                self.chat_head_l.addWidget(f)
            pct, common = self.compat(o)
            if pct is not None:
                cb = QPushButton(f"♥ {pct}%")
                cb.setCursor(Qt.CursorShape.PointingHandCursor)
                col_ = QColor.fromHsvF(0.33 * pct / 100, 0.8, 1.0).name()       # красный → зелёный
                cb.setStyleSheet(f"QPushButton{{background:rgba(255,255,255,0.06);color:{col_};border-radius:13px;"
                                 "padding:6px 12px;font-weight:900;}")
                cb.setToolTip("Совместимость вкусов. Клик — Blend: общий микс"
                              + (f"\nОбщие исполнители: {', '.join(common)}" if common else ""))
                cb.clicked.connect(lambda: self.blend(o))
                self.chat_head_l.addWidget(cb)
        shared = self.shared_playlist(o)
        ct = nd.store.chat_tracks(o)
        pl = ghost_btn(f"  Плейлисты · {len(shared)}")
        pl.setIcon(ya_icon("collection", 14))
        pl.setToolTip("Общий плейлист чата (правят все) и все треки, которыми обменялись")

        def pl_menu(btn=pl):
            m = QMenu(self)
            m.addAction(f"Общий плейлист · {len(shared)} — открыть", lambda: self._shared_dialog(o))
            a = m.addAction(f"Все треки из чата · {len(ct)} — слушать", lambda: self.play_many(ct, "треки чата"))
            a.setEnabled(bool(ct))
            m.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
        pl.clicked.connect(pl_menu)
        self.chat_head_l.addWidget(pl)
        if not o.startswith("g:") and (nd.store.contact(o) or {}).get("room") and self._online(o):
            j = accent_btn("Слушать вместе")
            j.clicked.connect(lambda: self.join_room(o))
            self.chat_head_l.addWidget(j)
        mb = icon_button("dots", "Ещё", 34, 18, "#cfcfcf")
        mb.clicked.connect(lambda: self._contact_menu(o, mb))
        self.chat_head_l.addWidget(mb)

    # ── общий плейлист чата: правки — это сообщения «cpl», поэтому без конфликтов и с доставкой как у чата ── #

    def shared_playlist(self, peer) -> list:
        items: dict[str, dict] = {}
        for m in self.node.store.messages(peer, 5000):
            ex = m.get("extra") or {}
            if ex.get("kind") != "cpl":
                continue
            if ex.get("op") == "add" and m.get("track"):
                items.setdefault(ex.get("ref") or m["id"], {"t": m["track"], "ts": m["ts"],
                                                           "by": ex.get("from") or ("me" if m["dir"] == "out" else peer)})
            elif ex.get("op") == "del":
                items.pop(ex.get("ref"), None)
        return [dict(v, ref=k) for k, v in sorted(items.items(), key=lambda kv: kv[1]["ts"])]

    def _cpl(self, peer, op, track=None, ref=""):
        import secrets
        self._chat_peer = peer
        self._send_special("", track, {"kind": "cpl", "op": op, "ref": ref or secrets.token_hex(8)})

    def _shared_dialog(self, peer):
        from PyQt6.QtWidgets import QDialog
        d = QDialog(self)
        d.setWindowTitle("Общий плейлист")
        d.setMinimumSize(520, 460)
        d.setStyleSheet(NET_QSS + "QDialog{background:#161616;}")
        v = QVBoxLayout(d)
        v.setContentsMargins(18, 16, 18, 16)
        t = lbl(f"Общий плейлист · {self._peer_title(peer)}")
        t.setStyleSheet("font-size:20px;font-weight:900;")
        v.addWidget(t)
        v.addWidget(lbl("Добавлять и убирать треки могут все в чате — правки доходят как сообщения, "
                        "поэтому ничего не теряется и не конфликтует.", "YaSub", wrap=True))
        pg = Page(margins=(0, 6, 0, 6))
        v.addWidget(pg, 1)

        def fill():
            pg.clear()
            items = self.shared_playlist(peer)
            if not items:
                pg.v.addWidget(lbl("Пока пусто — добавьте играющий трек.", "YaSub"))
            for it in items:
                r = QHBoxLayout()
                r.addWidget(TrackChip(it["t"], self.play_meta, compact=True, page=self,
                                      cover=self._local_cover(it["t"])), 1)
                by = lbl("вы" if it["by"] in ("me", self.node.me.onion) else self._name(it["by"]), "YaSub")
                r.addWidget(by)
                x = icon_button("close", "Убрать из общего плейлиста", 30, 14, "#cfcfcf")
                x.clicked.connect(lambda _=False, ref=it["ref"]: self._cpl(peer, "del", None, ref))
                r.addWidget(x)
                pg.v.addLayout(r)
            pg.v.addStretch(1)
        fill()
        row = QHBoxLayout()
        add = accent_btn("  Добавить играющий")
        add.setIcon(ya_icon("plus", 14, "#000000"))
        add.setEnabled(self.shell.current_track() is not None)
        add.clicked.connect(lambda: self._cpl(peer, "add", track_meta(self.shell.current_track())))
        play = ghost_btn("  Слушать всё")
        play.setIcon(ya_icon("play", 14))
        play.clicked.connect(lambda: self.play_many([i["t"] for i in self.shared_playlist(peer)], "общий плейлист"))
        save = ghost_btn("  Сохранить себе")
        save.clicked.connect(lambda: self._save_playlist({"title": "Общий", "author": peer, "name": self._peer_title(peer)},
                                                         [i["t"] for i in self.shared_playlist(peer)]))
        row.addWidget(add); row.addWidget(play); row.addWidget(save); row.addStretch(1)
        v.addLayout(row)
        def updated(kind, data):
            if kind == "message" and data == peer:
                fill()
        self.bridge.ev.connect(updated)
        try:
            d.exec()
        finally:
            self.bridge.ev.disconnect(updated)

    def _new_group(self):
        from PyQt6.QtWidgets import QDialog, QCheckBox
        friends = self.node.store.contacts("friend")
        if not friends:
            self.toast("Сначала добавьте друзей")
            return
        d = QDialog(self)
        d.setWindowTitle("Новая группа")
        d.setStyleSheet(NET_QSS + "QDialog{background:#161616;}")
        v = QVBoxLayout(d)
        v.setContentsMargins(18, 16, 18, 16)
        t = lbl("Новый групповой чат")
        t.setStyleSheet("font-size:20px;font-weight:900;")
        v.addWidget(t)
        name = QLineEdit()
        name.setPlaceholderText("Название группы")
        v.addWidget(name)
        v.addWidget(lbl(f"Участники (до {9}):", "YaSub"))
        boxes = []
        for c in friends:
            cb = QCheckBox(c["name"] or c["onion"][:8])
            cb.onion = c["onion"]
            boxes.append(cb)
            v.addWidget(cb)
        v.addWidget(lbl("Сообщения идут каждому напрямую через Tor; кто не дружит с автором — получит "
                        "через общих друзей в группе.", "YaSub", wrap=True))
        ok = accent_btn("Создать")
        ok.clicked.connect(d.accept)
        v.addWidget(ok)
        if d.exec():
            mem = [b.onion for b in boxes if b.isChecked()][:9]
            if not mem:
                return
            if not self.running():
                self.toast("Включите сеть, чтобы создать группу")
                return
            self.node.call(self.node.create_group, name.text().strip() or "Группа", mem)

    def _contact_menu(self, o, btn):
        m = QMenu(self)
        if str(o).startswith("g:"):
            m.addAction("Очистить переписку на этом компьютере", lambda: self._clear_chat(o))
            m.addAction("Выйти из группы", lambda: (self.node.leave_group(o[2:]), setattr(self, "_chat_peer", None),
                                                   self._refresh_tab("chats")))
            m.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
            return
        m.addAction("Открыть профиль", lambda: self.open_profile(o))
        m.addAction("Очистить переписку на этом компьютере", lambda: self._clear_chat(o))
        m.addSeparator()
        m.addAction("Удалить из друзей", lambda: self._remove_friend(o))
        m.addAction("Заблокировать", lambda: self._block(o))
        m.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _clear_chat(self, o):
        if QMessageBox.question(self, "Очистить чат", "Удалить переписку с этим другом на ЭТОМ компьютере?\n"
                                "У друга его копия останется.") == QMessageBox.StandardButton.Yes:
            self.node.store.clear_chat(o)
            self._fill_chat()
            self._fill_chat_list()

    def _remove_friend(self, o):
        if QMessageBox.question(self, "Удалить из друзей", f"Удалить {self._name(o)} из друзей?") == \
                QMessageBox.StandardButton.Yes:
            if self._chat_peer == o:
                self._chat_peer = None
            self.node.call(self.node.remove_friend, o) if self.running() else self.node.remove_friend(o)

    def _block(self, o):
        if self._chat_peer == o:
            self._chat_peer = None
        self.node.call(self.node.block, o) if self.running() else self.node.block(o)

    @batch_updates("chat_view", "chat_head")
    def _fill_chat(self):
        if self.node is None:
            return
        self._chat_header()
        v = self.chat_view
        o = self._chat_peer
        sb = v.verticalScrollBar()
        keep = sb.value()
        same_peer = self.__dict__.get("_rendered_chat_peer") == o
        follow = not same_peer or sb.maximum() - keep <= 40
        old = self.__dict__.get("_chat_rows", {}) if same_peer else {}
        epoch = self.__dict__.get("_chat_render_epoch", 0)
        if o:
            self.node.store.mark_read(o)
        msgs = self.node.store.messages(o) if o else []
        signatures = [(m["id"], json.dumps(m, sort_keys=True, ensure_ascii=False), epoch) for m in msgs]
        now = time.time()
        # Incoming contents and outgoing countdown headers both change at unlock.
        capsule_state = tuple(m["id"] for m in msgs if (m.get("extra") or {}).get("kind") == "capsule"
                              and now < float((m.get("extra") or {}).get("unlock") or 0))
        state = (o, signatures, capsule_state)
        if same_peer and state == self.__dict__.get("_chat_rows_state"):
            return
        rows = {}
        for m, sig in zip(msgs, signatures):
            hit = old.get(m["id"])
            lock = m["id"] in capsule_state
            if hit and hit[0] == (sig, lock):
                rows[m["id"]] = hit
            else:
                rows[m["id"]] = ((sig, lock), self._bubble(m))
        retained = {id(row[1]) for row in rows.values()}
        # Keep unchanged bubbles alive (image/video widgets and playback included).
        while v.v.count():
            item = v.v.takeAt(0)
            widget = item.widget()
            if widget is not None and id(widget) not in retained:
                widget.hide()
                widget.deleteLater()
        self._chat_rows = rows
        self._chat_rows_state = state
        self._rendered_chat_peer = o
        self._capsule_until = 0
        if not o:
            v.v.addStretch(1)
            return
        self._update_badge()
        if not msgs:
            e = lbl("Напишите первое сообщение. История хранится только на ваших компьютерах.", "YaSub", wrap=True)
            e.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.v.addStretch(1)
            v.v.addWidget(e)
        else:
            v.v.addStretch(1)
        last_day = None
        for m in msgs:
            day = time.strftime("%d.%m.%Y", time.localtime(m["ts"]))
            if day != last_day:
                last_day = day
                d = lbl(day, "YaSub")
                d.setAlignment(Qt.AlignmentFlag.AlignCenter)
                v.v.addWidget(d)
            v.v.addWidget(rows[m["id"]][1])
            if m["id"] in capsule_state:
                until = float((m.get("extra") or {}).get("unlock") or 0)
                if until > now:
                    self._capsule_until = min(self._capsule_until or until, until)
        v.v.activate()
        def restore_scroll():
            if self.__dict__.get("_chat_rows_state") is state:
                sb.setValue(sb.maximum() if follow else keep)
        QTimer.singleShot(0, restore_scroll)

    def _bubble(self, m) -> QWidget:
        out = m["dir"] == "out"
        ex0 = m.get("extra") or {}
        row = QWidget(); row.setObjectName("YaPage")
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        if ex0.get("kind") == "cpl":                           # правка общего плейлиста — служебной строкой
            who = "Вы" if out else (ex0.get("name") or self._name(ex0.get("from") or m["peer"]))
            t = (m.get("track") or {}).get("title") or "трек"
            s = lbl(f"♫ {who} " + (f"добавил(а) «{t}» в общий плейлист" if ex0.get("op") == "add"
                                   else "убрал(а) трек из общего плейлиста"), "YaSub")
            s.setCursor(Qt.CursorShape.PointingHandCursor)
            s.mousePressEvent = lambda e, p=m["peer"]: self._shared_dialog(p)
            h.addStretch(1); h.addWidget(s); h.addStretch(1)
            return row
        if not out and str(m.get("peer", "")).startswith("g:"):  # группа: аватар и имя автора
            src = ex0.get("from") or ""
            nm = self._name(src) if self.node.store.contact(src) else (ex0.get("name") or src[:8])
            av = QLabel(); av.setFixedSize(30, 30)
            av.setPixmap(self._av(src, nm, 30))
            h.addWidget(self._clickable(av, src), 0, Qt.AlignmentFlag.AlignBottom)
        b = QFrame()
        b.setObjectName("NetBubble")
        b.setMaximumWidth(460)
        b.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)   # не растягиваться по высоте чата
        b.setStyleSheet("QFrame#NetBubble{background:%s;border-radius:16px;%s}"
                        % ("rgba(255,219,26,0.92)" if out else "#262628",
                           "border-bottom-right-radius:4px;" if out else "border-bottom-left-radius:4px;"))
        bv = QVBoxLayout(b)
        bv.setContentsMargins(12, 8, 12, 6)
        bv.setSpacing(4)
        ex = m.get("extra") or {}
        kind = ex.get("kind", "text")
        ink = "#111" if out else "#f2f2f2"

        def head(text):
            t = lbl(text)
            t.setStyleSheet(f"font-size:10px;font-weight:900;letter-spacing:1px;color:"
                            f"{'rgba(0,0,0,0.6)' if out else YELLOW};")
            bv.addWidget(t)
        if not out and str(m.get("peer", "")).startswith("g:"):
            src = ex.get("from") or ""
            an = lbl(self._name(src) if self.node.store.contact(src) else (ex.get("name") or src[:8]))
            an.setStyleSheet(f"font-size:12px;font-weight:900;color:{QColor.fromHsvF(hue_of(src), 0.6, 1.0).name()};")
            bv.addWidget(an)
        locked = kind == "capsule" and not out and time.time() < float(ex.get("unlock") or 0)
        if kind == "capsule":
            head("КАПСУЛА ВРЕМЕНИ" + ("" if not out or time.time() >= ex.get("unlock", 0) else
                                      f" · откроется у друга через {ago_in(ex['unlock'])}"))
        if locked:
            box = lbl(f"Откроется через {ago_in(ex['unlock'])}\n"
                      f"{time.strftime('%d.%m %H:%M', time.localtime(ex['unlock']))}")
            box.setStyleSheet("font-size:15px;font-weight:800;color:#f2f2f2;padding:10px 4px;")
            bv.addWidget(box)
            nxt = float(ex["unlock"])
            cu = getattr(self, "_capsule_until", 0)
            self._capsule_until = min(cu, nxt) if cu else nxt
        else:
            if kind == "invite":
                head("ЗОВЁТ СЛУШАТЬ ВМЕСТЕ")
                r = lbl(f"Комната «{ex.get('room') or 'без названия'}»")
                r.setStyleSheet(f"font-size:15px;font-weight:900;color:{ink};")
                bv.addWidget(r)
            if kind == "lyric" and ex.get("line"):
                head("СТРОЧКА ИЗ ПЕСНИ")
                q = QuoteBlock(ex["line"], m.get("track") or {})
                if out:
                    q.setStyleSheet("font-size:19px;font-weight:900;font-style:italic;color:#111;")
                bv.addWidget(q)
            if kind == "moment":
                head(f"МОМЕНТ · С {fmt_sec(ex.get('at', 0))}")
            if kind == "gif" and ex.get("gif"):
                bv.addWidget(self._gif_widget(ex["gif"], 300))
            if kind == "playlist" and ex.get("tracks"):
                from net_playlist_ui import PlaylistCard
                bv.addWidget(PlaylistCard(self, ex, out, max_w=420,
                                          author=self.node.me.onion if out else (ex.get("from") or m["peer"]),
                                          author_name="" if out else (ex.get("name") or "")))
            if kind == "gift" and ex.get("gift"):
                from net_gifts import GiftCard
                bv.addWidget(GiftCard(self, ex["gift"], m["text"], m.get("track"), out,
                                      "" if out else self._name(ex.get("from") or m["peer"])))
            if kind == "file" and ex.get("file"):
                from net_files_ui import FileCard
                owner = self.node.me.onion if out else (ex.get("from") or m["peer"])
                bv.addWidget(FileCard(self, ex["file"], owner, mine=out, max_w=400))
            if m["text"] and kind != "gift":                   # у подарка текст — на открытке
                t = lbl(m["text"], wrap=True, sel=True)
                t.setStyleSheet(f"font-size:14px;color:{ink};")
                bv.addWidget(t)
            if m.get("track"):
                bv.addWidget(TrackChip(m["track"], self.play_meta, compact=True, page=self,
                                       at=ex.get("at") if kind in ("moment", "lyric") else None,
                                       cover=self._local_cover(m["track"]),
                                       owner=None if out else (ex.get("from") or m["peer"])))
            if kind == "invite" and not out:
                jb = accent_btn("Присоединиться")
                jb.clicked.connect(lambda _=False, o=(ex.get("from") or m["peer"]): self.join_room(o))
                bv.addWidget(jb)
        tm = time.strftime("%H:%M", time.localtime(m["ts"]))
        if out:
            tm += "  ✓✓" if m["delivered"] else "  · ждёт сети"
        s = lbl(tm)
        s.setStyleSheet(f"font-size:10px;color:{'rgba(0,0,0,0.55)' if out else '#8a8a8a'};")
        s.setAlignment(Qt.AlignmentFlag.AlignRight)
        bv.addWidget(s)
        if out:
            h.addStretch(1)
            h.addWidget(b)
        else:
            h.addWidget(b)
            h.addStretch(1)
        return row

    def _send_chat(self):
        o = self._chat_peer
        text = self.chat_edit.text().strip()
        tr = track_meta(self.shell.current_track()) if self.chat_track.isChecked() else None
        if not o or (not text and not tr):
            return
        if o.startswith("g:"):
            if not self.running():
                self.toast("Включите сеть, чтобы писать в группу")
                return
            self.node.call(self.node.send_group, o[2:], text, tr)
        elif not self.running():
            self.toast("Сеть выключена — сообщение уйдёт, когда вы её включите")
            import asyncio
            asyncio.run(self.node.send_message(o, text, tr))
            self._fill_chat()
        else:
            self.node.call(self.node.send_message, o, text, tr)
        self.chat_edit.clear()
        self.chat_track.setChecked(False)

    def _send_special(self, text, tr, extra):
        o = self._chat_peer
        if not o:
            return
        if o.startswith("g:"):
            if self.running():
                self.node.call(self.node.send_group, o[2:], text, tr, extra)
            else:
                self.toast("Включите сеть, чтобы писать в группу")
        elif self.running():
            self.node.call(self.node.send_message, o, text, tr, extra)
        else:
            import asyncio
            asyncio.run(self.node.send_message(o, text, tr, extra))
            self._fill_chat()
            self.toast("Сеть выключена — уйдёт, когда вы её включите")
        self.chat_edit.clear()

    def _chat_plus(self, btn):
        """«+» в чате: файлы, GIF, трек из коллекции, плейлист и музыкальные сообщения."""
        if not self._chat_peer:
            return
        cur = self.shell.current_track()
        meta = track_meta(cur)
        text = self.chat_edit.text().strip()
        try:
            pos = float(self.win.engine.get_position() or 0)
        except Exception:                                      # noqa: BLE001
            pos = 0.0
        m = QMenu(self)
        m.addAction(ya_icon("plus", 16), "Файлы…", self._attach_chat)
        m.addAction("GIF…", self._gif_chat)
        m.addAction("Трек из коллекции…", self._send_from_collection)
        m.addAction("Плейлист…", self._send_playlist)
        a = m.addAction(f"Играющий трек: {(meta or {}).get('title', '')[:34]}" if cur else "Играющий трек (ничего не играет)",
                        lambda: self._send_special(text, meta, {}))
        a.setEnabled(bool(cur))
        m.addSeparator()
        a = m.addAction(f"Момент трека — с {fmt_sec(pos)}" if cur else "Момент трека (включите трек)",
                        lambda: self._send_special(text, meta, {"kind": "moment", "at": pos}))
        a.setEnabled(bool(cur))
        line = current_lyric(self.win) if cur else ""
        a = m.addAction(f"Строчка из песни: «{line[:40]}»" if line else "Строчка из песни (нет синхронного текста)",
                        lambda: self._send_special(text, meta, {"kind": "lyric", "line": line, "at": pos}))
        a.setEnabled(bool(line))
        cap = m.addMenu("Капсула времени — откроется у друга…")
        import net_capsule
        for title, ts in capsule_times() + net_capsule.more_times():
            cap.addAction(title, lambda ts=ts: (self._send_special(text, meta if cur else None,
                                                                   {"kind": "capsule", "unlock": ts})
                                                if (text or cur) else self.toast("Напишите текст или включите трек")))
        cap.addSeparator()
        cap.addAction("Выбрать дату (например, день рождения)…", lambda: net_capsule.send_dialog(self))
        m.addAction("\U000f1004  Подарок: рамка, витрина, трек дня…", lambda: __import__("net_gifts").send_dialog(self))
        m.addSeparator()
        peer = self._chat_peer
        a = m.addAction("Добавить играющий трек в общий плейлист", lambda: self._cpl(peer, "add", meta))
        a.setEnabled(bool(cur))
        m.addAction("Открыть общий плейлист", lambda: self._shared_dialog(peer))
        m.addSeparator()
        m.addAction("Позвать слушать вместе", self._invite)
        if not peer.startswith("g:"):
            m.addAction("Blend — общий микс с другом", lambda: self.blend(peer))
        m.exec(btn.mapToGlobal(btn.rect().topLeft()))

    def _send_from_collection(self):
        """Трек из своей коллекции (не только играющий): карточкой или файлом."""
        from net_playlist_ui import TrackSearch, track_to_meta
        if not self._chat_peer:
            return
        d = TrackSearch(self.win, self)
        if not d.exec() or not d.result_tracks:
            return
        t = d.result_tracks[0]
        if d.as_file:
            self.send_files([str(t.get("path"))])
        else:
            self._send_special(self.chat_edit.text().strip(), track_to_meta(t), {})

    def _send_playlist(self):
        from net_playlist_ui import PlaylistPicker
        if not self._chat_peer:
            return
        d = PlaylistPicker(self.win, self)
        if not d.exec() or not d.result:
            return
        name, tracks = d.result
        if not tracks:
            return
        self._send_special(self.chat_edit.text().strip(), None, {"kind": "playlist", "title": name, "tracks": tracks})
        self.toast(f"Плейлист «{name}» отправлен · {len(tracks)} тр.")

    def _invite(self):
        """Открыть свою комнату (если ещё нет) и позвать в неё друга из чата."""
        if not self.running() or not self.node.state.get("online"):
            self.toast("Сначала включите сеть")
            return
        nd = self.node
        title = (nd.room_host or {}).get("title") or f"Комната {nd._name()}"
        if nd.room_host is None:
            nd.call(nd.room_open, title)
        self._send_special(self.chat_edit.text().strip(), None, {"kind": "invite", "room": title})

    # ══════════════════════════ ВМЕСТЕ ══════════════════════════ #

    def _build_room(self) -> QWidget:
        self.room_page = Page(margins=(0, 4, 8, 20))
        return self.room_page

    def join_room(self, onion):
        if not self.running():
            self.toast("Сначала включите сеть")
            return
        self.node.call(self.node.room_join, onion)
        self.shell.show_page("net")
        self.show_tab("room")

    @batch_updates("room_page")
    def _fill_room(self):
        if self.node is None:
            return
        import json
        from duel_settings import tr as translate
        t = lambda ru,en: translate(self.win,ru,en)
        page = self.room_page
        page.clear()
        rv = self.node.room_view()
        if rv is None:
            hero = Hero("Слушайте вместе", "Откройте комнату — друзья зайдут и услышат то же, что и вы, с той же "
                        "секунды. Трек у каждого играет из своей коллекции или потоком: звук по сети не идёт, "
                        "поэтому работает даже через Tor.", c1="#00d4ff", c2="#7a2cff", height=200)
            row = QHBoxLayout()
            self.room_name = QLineEdit()
            self.room_name.setPlaceholderText("Название комнаты, например «вечерний вайб»")
            self.room_name.setFixedWidth(330)
            row.addWidget(self.room_name)
            ob = accent_btn("Открыть комнату")
            ob.clicked.connect(self._open_room)
            row.addWidget(ob)
            row.addStretch(1)
            hero.lay.addLayout(row)
            row2 = QHBoxLayout()
            pref = self.__dict__.get("_room_public_pref")
            self.room_public = Switch(bool(self.node.settings.get("rooms_public", True) if pref is None else pref))
            self.room_public.toggled.connect(lambda on: self.__dict__.__setitem__("_room_public_pref", on))
            self.room_public.setEnabled(bool(getattr(self.node, "nostr", None)))
            row2.addWidget(self.room_public)
            pl_ = lbl("Публичная — видна всем в Echoes.NET, могут зайти и незнакомцы")
            pl_.setStyleSheet("color:#ebebeb;")
            row2.addWidget(pl_)
            self.room_genre = QLineEdit()
            self.room_genre.setPlaceholderText("Жанр (для поиска)")
            self.room_genre.setFixedWidth(170)
            row2.addWidget(self.room_genre)
            row2.addStretch(1)
            hero.lay.addLayout(row2)
            row3 = QHBoxLayout()                                   # радиостанция: эфир без конца
            rb = ghost_btn(t("Создать радиостанцию", "Create radio station"))
            rb.setIcon(ya_icon("broadcast_tower", 18))
            rb.setToolTip(t("Свой аватар, название и эфирная очередь, отдельная от личного плеера.",
                            "Your own avatar, name and on-air queue, independent of your personal player."))
            rb.clicked.connect(self._open_radio)
            row3.addWidget(rb)
            row3.addStretch(1)
            hero.lay.addLayout(row3)
            page.v.addWidget(hero)
            page.v.addWidget(section_title("Комнаты друзей"))
            rooms = [c for c in self.node.store.contacts("friend") if c["room"] and self._online(c["onion"])]
            if not rooms:
                page.v.addWidget(lbl("Сейчас никто из друзей не открыл комнату. Откройте свою — им придёт приглашение "
                                     "в «Друзья сейчас слушают».", "YaSub", wrap=True))
            grid = HRow()
            for c in rooms:
                f, v = card()
                f.setFixedSize(280, 150)
                room = json.loads(c["room"])
                now = room.get('now') if room.get('radio') else (json.loads(c["now"]) if c["now"] else None)
                h = QHBoxLayout()
                av = QLabel(); av.setFixedSize(36, 36)
                if room.get('radio'):
                    from radio_ui import avatar_pixmap
                    av.setPixmap(avatar_pixmap(room['radio'].get('avatar',''),36))
                else:
                    av.setPixmap(self._av(c["onion"], c["name"], 36, True))
                h.addWidget(self._clickable(av, c["onion"]))
                col = QVBoxLayout(); col.setSpacing(0)
                col.addWidget(lbl(room.get("title") or "Комната", "NetName"))
                col.addWidget(lbl(f"{c['name']} · слушателей: {room.get('n', 1)}", "YaSub"))
                h.addLayout(col, 1)
                v.addLayout(h)
                if now:
                    v.addWidget(lbl(QFontMetrics(ya_font(12)).elidedText(f"♪ {now['artist']} — {now['title']}",
                                                                         Qt.TextElideMode.ElideRight, 240), "YaSub"))
                j = accent_btn("Присоединиться")
                j.clicked.connect(lambda _=False, o=c["onion"]: self.join_room(o))
                v.addWidget(j)
                grid.add(f)
            if rooms:
                page.v.addWidget(grid)
            self._public_rooms(page)
            page.v.addStretch(1)
            return
        host = rv["role"] == "host"
        st = rv.get("state") or {}
        station = st.get('radio') or {}
        self._radio_view_signature = (rv.get('role'), station.get('revision'), station.get('current'),
                                      st.get('playing'), tuple(rv.get('members') or []))
        tr = st.get("track")
        hero = Hero(rv.get("title") or "Комната",
                    (t("Публичный эфир · своя очередь, отдельная от вашего плеера", "Public broadcast · its own queue, independent of your player") if station and host else
                     t("Вы слушаете эфир радиостанции", "You are listening to the station broadcast") if station else
                     "Вы ведёте комнату — всё, что играет у вас, слышат гости." if host else
                     f"Ведёт {rv.get('host_name')}. Ваш плеер следует за хостом."),
                    c1="#00d4ff", c2="#ff4fa3", height=96)
        page.v.addWidget(hero)
        if station:
            from radio_ui import avatar_pixmap
            branding=QHBoxLayout(); photo=QLabel(); photo.setPixmap(avatar_pixmap(station.get('avatar',''),56))
            branding.addWidget(photo); branding.addWidget(lbl(station.get('name','Echoes Radio'),'NetName'))
            verified=lbl(t('Проверенный ведущий','Verified host'),'YaSub');branding.addWidget(verified);branding.addStretch()
            hero.lay.addLayout(branding)
        page.v.addSpacing(10)
        mid = QHBoxLayout(); mid.setSpacing(14)
        left, lv = card()
        lv.addWidget(lbl(t("В ЭФИРЕ", "ON AIR") if station else "СЕЙЧАС ИГРАЕТ", "Section"))
        if tr:
            cur = self.shell.current_track()
            cov = cur.get("cover", "") if cur and track_key(cur) == track_key(tr) else ""
            lv.addWidget(TrackChip(tr, self.play_meta, cover=cov, page=self,
                                   owner=None if host else rv.get("host")))
        else:
            lv.addWidget(lbl("Хост ещё ничего не включил" if not host else "Включите любой трек — гости услышат его",
                             "YaSub", wrap=True))
        lv.addWidget(lbl("СЛУШАЮТ", "Section"))
        mem = rv.get("members") or []
        if host:
            mem = [self.node._name() + t(" (вы)"," (you)")] + list(mem)
        lv.addWidget(lbl(", ".join(mem) or "пока только вы", wrap=True))
        if not host:
            self.sync_lbl = lbl("Синхронизация по часам хоста…", "YaSub")
            lv.addWidget(self.sync_lbl)
        lv.addStretch(1)
        radio = host and bool(station)
        if radio:
            controls=QHBoxLayout()
            pause=ghost_btn(t('Пауза эфира','Pause broadcast') if st.get('playing') else t('Продолжить эфир','Resume broadcast'))
            pause.clicked.connect(lambda:self.node.call(self.node.radio_control,'pause')); controls.addWidget(pause)
            nxt=ghost_btn(t('Следующий','Next')); nxt.clicked.connect(lambda:self.node.call(self.node.radio_control,'next')); controls.addWidget(nxt)
            lv.addLayout(controls)
            edit=ghost_btn(t('Станция и очередь','Station and queue')); edit.clicked.connect(self._edit_radio); lv.addWidget(edit)
            console=ghost_btn(t('Голос и звуки эфира','Broadcast voice & sounds'));console.setIcon(ya_icon('eq',18))
            console.clicked.connect(lambda:self._open_radio_console(console,True));lv.addWidget(console)
            if tr:
                monitor=ghost_btn(t('Прослушать текущий трек','Preview current track'))
                monitor.clicked.connect(lambda _=False,meta=tr:self.play_meta(meta)); lv.addWidget(monitor)
        if radio:                                              # радиостанция: эфир и «сказать в эфир»
            onair = lbl(t('В ЭФИРЕ','ON AIR') if st.get('playing') else t('ЭФИР НА ПАУЗЕ','BROADCAST PAUSED'))
            onair.setStyleSheet("color:#ff4d4d;font-weight:900;letter-spacing:1px;")
            lv.addWidget(onair)
        lv.addWidget(lbl("ГОЛОС", "Section"))
        vr = QHBoxLayout()
        on = bool(self._voice and self._voice.mic_active)
        if radio:
            mic = accent_btn(t("Удерживайте — сказать в эфир", "Hold to talk on air"))
            mic.setIcon(ya_icon('mic',18))
            mic.setToolTip(t("Пока держите — вас слышат, музыка у слушателей тише.", "Hold to talk. Music is quieter for listeners while you speak."))
            mic.pressed.connect(lambda: self._radio_talk(True))
            mic.released.connect(lambda: self._radio_talk(False))
        else:
            mic = accent_btn("Микрофон включён") if on else ghost_btn("Включить микрофон")
            mic.setToolTip("Говорить в комнате. Лучше в наушниках — иначе микрофон слышит музыку")
            mic.clicked.connect(self.toggle_mic)
        vr.addWidget(mic, 1)
        mute = icon_button("mute" if self._voice_muted else "volume", "Громкость голосов", 38, 18)
        mute.setToolTip("Не слышать голоса в комнате")
        mute.clicked.connect(lambda: (setattr(self, "_voice_muted", not self._voice_muted), self._fill_room()))
        vr.addWidget(mute)
        lv.addLayout(vr)
        self.voice_lbl = lbl("", "YaSub")
        lv.addWidget(self.voice_lbl)
        targets = list(self.node.room_members) if host else ([self.node.room_guest] if self.node.room_guest else [])
        if targets:
            fast = [o for o in targets if self.node.fast_path(o)]
            vs = lbl("Голос: прямой канал есть" if len(fast) == len(targets) else
                     ("Голос: ищу прямой канал (пробиваю NAT)… через релеи голос не передаётся" if not fast else
                      f"Голос: прямой канал с {len(fast)} из {len(targets)}"), "YaSub", wrap=True)
            lv.addWidget(vs)
        bx = ghost_btn("Закрыть комнату" if host else "Выйти из комнаты")
        bx.clicked.connect(lambda: (self._voice_stop(),
                                    self.node.call(self.node.room_close if host else self.node.room_leave)))
        lv.addWidget(bx)
        left.setFixedWidth(330)
        mid.addWidget(left)
        right, rvl = card()
        if station:
            if not host:
                sounds_button=ghost_btn(t('Звуки станции · скачать','Station sounds · download'))
                sounds_button.clicked.connect(lambda:self._open_radio_console(sounds_button,False));rvl.addWidget(sounds_button)
            rvl.addWidget(lbl(t('ЭФИРНАЯ ОЧЕРЕДЬ','ON-AIR QUEUE'),'Section'))
            queue=QListWidget(); queue.setMinimumHeight(130); queue.setMaximumHeight(230)
            for entry in station.get('queue',[]):
                track=entry.get('track') or {}
                current=entry.get('id')==station.get('current')
                item=QListWidgetItem(('›  ' if current else '    ')+f"{track.get('artist','')} — {track.get('title','')}")
                item.setData(Qt.ItemDataRole.UserRole,entry.get('id')); queue.addItem(item)
                if current:item.setForeground(QColor(YELLOW))
            if host:
                queue.setToolTip(t('Двойной щелчок — поставить в эфир','Double-click to play on air'))
                queue.itemDoubleClicked.connect(lambda item:self.node.call(self.node.radio_control,'play',item.data(Qt.ItemDataRole.UserRole)))
            rvl.addWidget(queue)
        rvl.addWidget(lbl("ЧАТ КОМНАТЫ", "Section"))
        self.room_chat_view = Page(margins=(0, 0, 0, 0))
        self.room_chat_view.v.setSpacing(4)
        self.room_chat_view.v.addStretch(1)
        self.room_chat_view.setMinimumHeight(170)
        rvl.addWidget(self.room_chat_view, 1)
        for line in self.node.room_chat:
            self._room_chat_add(line, scroll=False)
        ir = QHBoxLayout()
        e = QLineEdit(); e.setPlaceholderText("Написать в комнату…")
        e.returnPressed.connect(lambda: (self.node.call(self.node.room_say, e.text()), e.clear()))
        ir.addWidget(e, 1)
        sb = icon_button("send", "Отправить", 36, 18, YELLOW)
        sb.clicked.connect(lambda: (self.node.call(self.node.room_say, e.text()), e.clear()))
        ir.addWidget(sb)
        rvl.addLayout(ir)
        mid.addWidget(right, 1)
        page.v.addLayout(mid)
        page.v.addStretch(1)
        sbar = self.room_chat_view.verticalScrollBar()

        def to_end(sb=sbar):
            try:
                sb.setValue(sb.maximum())
            except RuntimeError:                               # комнату успели перерисовать
                pass
        QTimer.singleShot(50, to_end)

    def _room_chat_add(self, line, scroll=True):
        v = getattr(self, "room_chat_view", None)
        if v is None or not isinstance(line, dict):
            return
        try:
            if line.get("sys"):
                w = lbl(line.get("text", ""), "YaSub")
            else:
                me = line.get("from") == self.node.me.onion
                w = lbl(f"<b style='color:{YELLOW if me else '#fff'}'>{_esc(line.get('name', ''))}</b>&nbsp;&nbsp;"
                        f"{_esc(line.get('text', ''))}", wrap=True)
                w.setTextFormat(Qt.TextFormat.RichText)
            v.v.addWidget(w)
            if scroll:
                sb = v.verticalScrollBar()
                QTimer.singleShot(30, lambda: sb.setValue(sb.maximum()))
        except RuntimeError:
            pass

    def _open_radio(self):
        from duel_settings import tr
        if not self.node.radio_allowed():
            panel=self.open_bug_report();panel.category.setCurrentIndex(panel.category.findData('radio'))
            self.toast(tr(self.win,'Чтобы вести радио, отправьте заявку администратору или модератору.','Apply to an administrator or moderator to host a radio station.'));return
        if not self.running() or not self.node.state.get("online"):
            self.toast(tr(self.win,"Сначала включите сеть","Turn on the network first"));return
        from radio_ui import StationDialog
        dialog = StationDialog(self, self.node.settings.get('radio_station'))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.node.call(self.node.radio_open, dialog.result_config)
            self.shell.show_page('net')
            self.show_tab('room')

    def _edit_radio(self):
        from radio_ui import StationDialog
        config = self.node.settings.get('radio_station') or {}
        dialog = StationDialog(self, config)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.node.call(self.node.radio_configure, dialog.result_config)

    def _radio_talk(self, on):
        """«Сказать в эфир»: пока кнопка зажата — микрофон и тише музыка (у себя тоже)."""
        try:
            from radio_console import engine
            if not self.node.room_host or not self.node.room_host.get('station') or not self.node.radio_allowed():return
            v = engine(self)
            nd = self.node
            if on and not v.mic_active:
                v.sink = nd.radio_voice_out
                v.want = {nd.room_codec()}
                v.mic_on()
                self._voice_t.start()
            elif not on and v.mic_active:
                v.mic_off()
            self.win.engine._apply_loudness(scale=0.3 if on else 1.0)
            self._radio_on_air = on
        except Exception as e:                                 # noqa: BLE001
            self.toast(f"Микрофон не включился: {e}")

    def _open_radio_console(self,anchor,host=True):
        from radio_console import RadioConsole
        previous=getattr(self,'_radio_console',None)
        if previous is not None:
            try:previous.close();previous.deleteLater()
            except RuntimeError:pass
        self._radio_console=RadioConsole(self,anchor,host);self._radio_console.show()

    def _open_room(self):
        if not self.running() or not self.node.state.get("online"):
            self.toast("Сначала включите сеть")
            return
        self.node.call(self.node.room_open, self.room_name.text().strip(),
                       bool(getattr(self, "room_public", None) and self.room_public.isChecked()),
                       self.room_genre.text().strip() if getattr(self, "room_genre", None) else "",
                       bool(self.node.settings.get("share_tracks", True)))

    # ══════════════════════════ ДРУЗЬЯ ══════════════════════════ #

    def _build_friends(self) -> QWidget:
        self.friends_page = Page(margins=(0, 4, 8, 20))
        return self.friends_page

    @batch_updates("friends_page")
    def _fill_friends(self):
        if self.node is None:
            return
        import json
        page = self.friends_page
        page.clear()
        st = self.node.store
        top = QHBoxLayout(); top.setSpacing(14)
        f, v = card()
        v.addWidget(lbl("ВАШ КОД", "Section"))
        code = lbl(self.node.code, "NetCode", wrap=True, sel=True)
        v.addWidget(code)
        r = QHBoxLayout()
        cp = accent_btn("  Скопировать код")
        cp.setIcon(ya_icon("copy", 16, "#000000"))
        cp.clicked.connect(self.copy_code)
        r.addWidget(cp)
        tm = ghost_btn("  Карта вкусов")                       # кто к кому ближе по музыке
        tm.setIcon(ya_icon("tastemap", 18))
        tm.clicked.connect(lambda: __import__("net_tastemap").open_map(self))
        r.addWidget(tm)
        r.addStretch(1)
        v.addLayout(r)
        v.addWidget(lbl("Код — это ваш адрес в сети Tor и открытый ключ. Подделать его нельзя, "
                        "регистрироваться не нужно.", "YaSub", wrap=True))
        top.addWidget(f, 1)
        f2, v2 = card()
        v2.addWidget(lbl("ДОБАВИТЬ ДРУГА", "Section"))
        self.add_code = QLineEdit()
        self.add_code.setPlaceholderText("Вставьте код друга: echoes:…")
        v2.addWidget(self.add_code)
        self.add_note = QLineEdit()
        self.add_note.setPlaceholderText("Пара слов к заявке (необязательно)")
        v2.addWidget(self.add_note)
        ab = accent_btn("Отправить заявку")
        ab.clicked.connect(self._add_friend)
        v2.addWidget(ab)
        v2.addStretch(1)
        top.addWidget(f2, 1)
        page.v.addLayout(top)
        try:                                                   # топ недели среди друзей
            import net_weektop
            page.v.addSpacing(12)
            page.v.addWidget(net_weektop.card(self))
        except Exception as e:                                 # noqa: BLE001
            print("[weektop]", e)

        reqs = st.contacts("pending_in")
        if reqs:
            page.v.addWidget(section_title(f"Заявки · {len(reqs)}"))
            for c in reqs:
                f, v = card()
                h = QHBoxLayout()
                av = QLabel(); av.setFixedSize(38, 38)
                av.setPixmap(self._av(c["onion"], c["name"], 38))
                h.addWidget(av)
                col = QVBoxLayout(); col.setSpacing(0)
                col.addWidget(lbl(c["name"] or c["onion"][:8], "NetName"))
                col.addWidget(lbl(c["note"] or c["onion"][:24] + "…", "YaSub"))
                pubn = next((pp for pp in self._pub()["profiles"].values() if pp.get("onion") == c["onion"]), None)
                col.addWidget(lbl("из публичной сети" if pubn else "по вашему коду или от друга", "YaSub"))
                h.addLayout(col, 1)
                bl = ghost_btn("Заблокировать")
                bl.clicked.connect(lambda _=False, o=c["onion"]: self._act(self.node.block, o))
                h.addWidget(bl)
                ok = accent_btn("Принять")
                ok.clicked.connect(lambda _=False, o=c["onion"]: self._act(self.node.accept, o))
                no = ghost_btn("Отклонить")
                no.clicked.connect(lambda _=False, o=c["onion"]: self._act(self.node.decline, o))
                h.addWidget(ok); h.addWidget(no)
                v.addLayout(h)
                page.v.addWidget(f)
        outs = st.contacts("pending_out")
        if outs:
            page.v.addWidget(section_title("Ждут ответа"))
            for c in outs:
                h = QHBoxLayout()
                h.addWidget(lbl(f"{c['onion'][:16]}…  ·  заявка уйдёт, когда друг будет в сети", "YaSub"), 1)
                x = ghost_btn("Отменить")
                x.clicked.connect(lambda _=False, o=c["onion"]: self._act(self.node.decline, o))
                h.addWidget(x)
                page.v.addLayout(h)
        friends = st.contacts("friend")
        friends.sort(key=lambda c: (not self._online(c["onion"]), (c["name"] or "").casefold()))
        page.v.addWidget(section_title(f"Друзья · {len(friends)}"))
        if not friends:
            page.v.addWidget(lbl("Пока пусто. Скопируйте свой код и отправьте другу (в Telegram, Discord — "
                                 "куда угодно), а его код вставьте выше.", "YaSub", wrap=True))
        for c in friends:
            f, v = card()
            v.setContentsMargins(14, 10, 14, 10)
            h = QHBoxLayout(); h.setSpacing(12)
            on = self._online(c["onion"])
            av = QLabel(); av.setFixedSize(42, 42)
            av.setPixmap(self._av(c["onion"], c["name"], 42, on))
            h.addWidget(self._clickable(av, c["onion"]))
            col = QVBoxLayout(); col.setSpacing(1)
            col.addWidget(lbl(c["name"] or c["onion"][:8], "NetName"))
            now = json.loads(c["now"]) if c["now"] else None
            if on:
                s = f"слушает {now['artist']} — {now['title']}" if now else (c["bio"] or "в сети")
            else:
                s = f"был(а) в сети {ago(c['last_seen'])} назад" if c["last_seen"] else "ещё не был(а) в сети"
                s = s.replace("только что назад", "только что")
            col.addWidget(lbl(QFontMetrics(ya_font(12)).elidedText(s, Qt.TextElideMode.ElideRight, 460), "YaSub"))
            h.addLayout(col, 1)
            pct, common = self.compat(c["onion"])
            if pct is not None:
                cp = lbl(f"♥ {pct}%")
                cp.setStyleSheet(f"color:{QColor.fromHsvF(0.33 * pct / 100, 0.8, 1.0).name()};font-weight:900;"
                                 "font-size:14px;padding:0 8px;")
                cp.setToolTip("Совместимость вкусов" + (f" · общие: {', '.join(common)}" if common else ""))
                h.addWidget(cp)
            if c["room"] and on:
                j = accent_btn("Слушать вместе")
                j.clicked.connect(lambda _=False, o=c["onion"]: self.join_room(o))
                h.addWidget(j)
            mb = icon_button("chat", "Написать", 36, 18, "#cfcfcf")
            mb.clicked.connect(lambda _=False, o=c["onion"]: self.open_chat(o))
            h.addWidget(mb)
            more = icon_button("dots", "Ещё", 36, 18, "#cfcfcf")
            more.clicked.connect(lambda _=False, o=c["onion"], b=more: self._contact_menu(o, b))
            h.addWidget(more)
            v.addLayout(h)
            page.v.addWidget(f)
        self._people_by_taste(page)
        page.v.addStretch(1)

    def _act(self, fn, *args):
        if self.running():
            self.node.call(fn, *args)
        else:
            fn(*args)

    def _add_friend(self):
        code = self.add_code.text().strip()
        if not code:
            return
        self._act(self.node.add_friend, code, self.add_note.text().strip())
        if not self.running():
            self.toast("Заявка сохранена — включите сеть, чтобы её отправить")

    # ══════════════════════════ СЕТЬ ══════════════════════════ #

    def _build_net(self) -> QWidget:
        self.net_page = Page(margins=(0, 4, 8, 20))
        return self.net_page

    def _net_status_ui(self, st):
        try:
            self.net_state_lbl.setText(st.get("text", ""))
            self.net_bar.setValue(int(st.get("pct") or 0))
            self.net_bar.setVisible(st.get("phase") in ("tor", "onion"))
        except (AttributeError, RuntimeError):
            pass

    @batch_updates("net_page")
    def _fill_net(self):
        """Настройки Echoes.NET: сверху — то, что нужно всем (сеть, профиль, приватность, уведомления, GIF, реакции);
        Tor, мосты, релеи и прочая техника — в свёрнутом блоке «Для продвинутых»."""
        if self.node is None:
            return
        nd = self.node
        page = self.net_page
        page.clear()
        s = nd.settings
        from ya_profile import SegTabs                        # «Настройки» | «Ачивки»
        sub = self.__dict__.get("_net_sub", "set")
        seg = SegTabs([("set", "Настройки", "settings"), ("ach", "Ачивки", "star")], sub)
        seg.changed.connect(lambda k: (setattr(self, "_net_sub", k), self._fill_net()))
        sr = QWidget(); sr.setObjectName("YaPage")
        srl = QHBoxLayout(sr); srl.setContentsMargins(0, 6, 0, 8); srl.addWidget(seg); srl.addStretch(1)
        page.v.addWidget(sr)
        if sub == "ach":
            import net_ach
            net_ach.fill_page(self, page.v)
            page.v.addStretch(1)
            return
        # ── сеть: одной строкой ──
        f, v = card()
        v.addWidget(lbl("СЕТЬ", "Section"))
        self.net_state_lbl = lbl(nd.state.get("text", ""), "Big", wrap=True)
        v.addWidget(self.net_state_lbl)
        self.net_bar = QProgressBar()
        self.net_bar.setTextVisible(False)
        self.net_bar.setFixedHeight(8)
        v.addWidget(self.net_bar)
        self._net_status_ui(nd.state)
        tor = nd.tor.find_tor()
        r = QHBoxLayout()
        pw = accent_btn("Выключить сеть" if self.running() else "Включить сеть")
        pw.clicked.connect(lambda: (self.toggle_power(), self._fill_net()))
        r.addWidget(pw)
        cp = ghost_btn("  Мой код")
        cp.setIcon(ya_icon("copy", 14))
        cp.setToolTip("Скопировать ваш код — отправьте его другу, он добавит вас во вкладке «Друзья»")
        cp.clicked.connect(self.copy_code)
        r.addWidget(cp)
        fr = ghost_btn("  Добавить друга")
        fr.setIcon(ya_icon("users", 14))
        fr.clicked.connect(lambda: self.show_tab("friends"))
        r.addWidget(fr)
        r.addStretch(1)
        v.addLayout(r)
        sw2 = QHBoxLayout()
        auto = Switch(bool(s.get("autostart")))
        auto.toggled.connect(lambda on: (s.__setitem__("autostart", bool(on)), nd.save_settings()))
        sw2.addWidget(auto)
        sw2.addWidget(lbl("Включать сеть при запуске плеера"), 1)
        v.addLayout(sw2)
        page.v.addWidget(f)
        # ── профиль ──
        f, v = card()
        v.addWidget(lbl("ПРОФИЛЬ", "Section"))
        pr = QHBoxLayout(); pr.setSpacing(14)
        av = QLabel(); av.setFixedSize(64, 64)
        av.setPixmap(self._av(nd.me.onion, nd._name(), 64))
        pr.addWidget(self._clickable(av, nd.me.onion))
        col = QVBoxLayout(); col.setSpacing(2)
        nm = lbl(str(self.win.profile.get("nickname") or nd._name()))
        nm.setStyleSheet("font-size:18px;font-weight:900;")
        col.addWidget(nm)
        stt = str(self.win.profile.get("status") or "")
        info = (f"{stt}  ·  " if stt else "") + f"любимых треков: {len(s.get('fav') or [])}" + \
            ("  ·  есть «о себе»" if s.get("about") else "")
        col.addWidget(lbl(info, "YaSub"))
        pr.addLayout(col, 1)
        ed = accent_btn("  Изменить профиль")
        ed.setIcon(ya_icon("edit", 14, "#000000"))
        ed.clicked.connect(lambda: getattr(self.win, "_edit_profile_then_refresh", lambda: None)())
        pr.addWidget(ed)
        mp = ghost_btn("  Открыть")
        mp.setIcon(ya_icon("user", 14))
        mp.clicked.connect(lambda: self.open_profile(nd.me.onion))
        pr.addWidget(mp)
        v.addLayout(pr)
        page.v.addSpacing(10)
        page.v.addWidget(f)
        # ── кто что видит + уведомления ──
        f, v = card()
        v.addWidget(lbl("КТО ЧТО ВИДИТ", "Section"))
        v.addWidget(lbl("Включено — видят все в ECHOES. Выключено — только ваши друзья.", "YaSub", wrap=True))
        for key, title, sub in (
                ("public_profile", "Мой профиль", "любимые треки, тирлист, статус — незнакомцы смогут добавить вас"),
                ("posts_public", "Мои посты", "новые посты сразу уходят в общую ленту"),
                ("rooms_public", "Мои комнаты «Слушать вместе»", "зайти сможет любой"),
                ("now_public", "Что я сейчас слушаю", "трек, который играет у вас")):
            h = QHBoxLayout()
            sw = Switch(bool(s.get(key, True)))
            sw.toggled.connect(lambda on, k=key: (s.__setitem__(k, bool(on)), nd.save_settings(),
                                                  self.push_profile(force=True) if k == "public_profile" else None,
                                                  self._game_watch.check() if k == "share_game" else None))
            h.addWidget(sw)
            c2 = QVBoxLayout(); c2.setSpacing(0)
            c2.addWidget(lbl(title, "NetName"))
            c2.addWidget(lbl(sub, "YaSub", wrap=True))
            h.addLayout(c2, 1)
            v.addLayout(h)
        page.v.addSpacing(10)
        page.v.addWidget(f)
        page.v.addSpacing(10)
        self._notif_anchor = self._notify_card()
        page.v.addWidget(self._notif_anchor)
        page.v.addSpacing(10)
        self._voice_anchor = self._voice_card()
        page.v.addWidget(self._voice_anchor)
        page.v.addSpacing(10)
        page.v.addWidget(__import__("net_queue").settings_card(self))
        page.v.addWidget(__import__("net_devsync").settings_card(self))
        page.v.addSpacing(10)
        page.v.addWidget(self._subs_card())
        page.v.addSpacing(10)
        self._upd_anchor = self._update_card()
        page.v.addWidget(self._upd_anchor)
        page.v.addSpacing(10)
        page.v.addWidget(self._gif_card())
        page.v.addSpacing(10)
        page.v.addWidget(self._reactions_card())
        page.v.addSpacing(10)
        page.v.addWidget(self._moderation_card())
        # ── история ──
        f, v = card()
        v.addWidget(lbl("ИСТОРИЯ НА ЭТОМ КОМПЬЮТЕРЕ", "Section"))
        v.addWidget(lbl("Серверов нет — переписка и лента хранятся у вас. То, что уже ушло друзьям, остаётся и у них.",
                        "YaSub", wrap=True))
        cr = QHBoxLayout()
        for what, text in (("messages", "Очистить переписку"), ("feed", "Очистить кэш ленты"),
                           ("all", "Стереть всё")):
            b2 = ghost_btn(text)
            if what == "all":
                b2.setStyleSheet("QPushButton{color:#ff6b6b;}")
            b2.clicked.connect(lambda _=False, w=what, t=text: self._clear(w, t))
            cr.addWidget(b2)
        kb = ghost_btn("Кэш фото, видео, GIF…")
        kb.setToolTip("Выбрать, что очистить: фото, видео, аудио, документы, GIF, картинки из интернета…")
        kb.clicked.connect(lambda: self.win.open_cleanup(2))
        cr.addWidget(kb)
        cr.addStretch(1)
        v.addLayout(cr)
        page.v.addSpacing(10)
        page.v.addWidget(f)
        # ── для продвинутых (свёрнуто) ──
        page.v.addSpacing(14)
        open_ = bool(self.__dict__.get("_adv_open"))
        tg = ghost_btn(("▾  " if open_ else "▸  ") + "Для продвинутых: Tor, мосты, релеи, прямые соединения")
        tg.setToolTip("Обычно трогать не нужно — ECHOES сам выбирает самый быстрый путь")
        tg.clicked.connect(lambda: (self.__dict__.__setitem__("_adv_open", not open_), self._fill_net()))
        rowt = QHBoxLayout(); rowt.addWidget(tg); rowt.addStretch(1)
        page.v.addLayout(rowt)
        if open_:
            f, v = card()
            v.addWidget(lbl("TOR", "Section"))
            v.addWidget(lbl(f"tor.exe: {tor}" if tor else "Tor не найден на этом компьютере — без него работают "
                            "прямые соединения и Nostr.", "YaSub", wrap=True))
            r = QHBoxLayout()
            if not tor:
                dl = accent_btn("Скачать Tor (~20 МБ, torproject.org)")
                dl.clicked.connect(self._download_tor)
                r.addWidget(dl)
            pick = ghost_btn("Указать tor.exe…")
            pick.setToolTip("Например, из Tor Browser: Browser\\TorBrowser\\Tor\\tor.exe")
            pick.clicked.connect(self._pick_tor)
            r.addWidget(pick)
            r.addStretch(1)
            v.addLayout(r)
            self.dl_bar = QProgressBar(); self.dl_bar.setTextVisible(False); self.dl_bar.setFixedHeight(8)
            self.dl_bar.hide()
            v.addWidget(self.dl_bar)
            mode = QComboBox()
            modes = (("auto", "Авто: напрямую, если не вышло — через мосты"), ("direct", "Только напрямую"),
                     ("bridges", "Только через мои мосты"))
            for k, t in modes:
                mode.addItem(t, k)
            mode.setCurrentIndex(max(0, [k for k, _ in modes].index(s.get("mode", "auto"))))
            v.addWidget(mode)
            v.addWidget(lbl("Мосты (если Tor заблокирован провайдером). По строке на мост: obfs4 …, webtunnel … — "
                            "взять у @GetBridgesBot в Telegram или на bridges.torproject.org. В режиме «Авто» "
                            "встроенные мосты snowflake/obfs4 пробуются сами.", "YaSub", wrap=True))
            br = QPlainTextEdit(s.get("bridges", ""))
            br.setFixedHeight(80)
            br.setPlaceholderText("obfs4 1.2.3.4:443 FINGERPRINT cert=… iat-mode=0")
            v.addWidget(br)
            save = accent_btn("Сохранить подключение")

            def do_save():
                s["mode"] = mode.currentData()
                s["bridges"] = br.toPlainText().strip()
                nd.save_settings()
                self.toast("Сохранено. Мосты и режим подключения — со следующего включения сети")
            save.clicked.connect(do_save)
            rr = QHBoxLayout(); rr.addWidget(save); rr.addStretch(1)
            v.addLayout(rr)
            page.v.addSpacing(10)
            page.v.addWidget(f)
            page.v.addSpacing(10)
            page.v.addWidget(self._transports_card())
        page.v.addStretch(1)

    # ── обновления ECHOES через сеть (net_update) ── #

    def _upd_ui(self, view):
        show = bool(view and view.get("trusted") and view.get("state") in
                    ("offer", "downloading", "checking", "ready", "error"))
        self.b_upd.setVisible(False)                           # обновление — только маленькая кнопка в шапке окна
        tb = None                    # кнопку «Обновить» в шапке ведёт только обновление с GitHub (github_update)
        if tb is not None and hasattr(tb, "set_update"):
            if view and view.get("state") in ("downloading", "checking") and view.get("total"):
                txt = f"{int(100 * (view.get('done_bytes') or 0) / max(1, view['total']))}%"
            else:
                txt = "Установить" if view and view.get("state") == "ready" else "Обновить"
            tb.set_update(show, lambda: (self.shell.show_page("net"), self.open_update()), txt)
        if view and view.get("state") == "ready":
            self.b_upd.setText("  Установить обновление")
        elif view and view.get("state") in ("downloading", "checking"):
            pct = int(100 * (view.get("done_bytes") or 0) / max(1, view.get("total") or 1)) if view.get("total")                 else (int(100 * view.get("chunks", 0) / max(1, view.get("n") or 1)) if view.get("n") else 0)
            self.b_upd.setText(f"  Скачиваю… {pct}%")
        else:
            self.b_upd.setText("  Обновить ECHOES")
        d = self.__dict__.get("_upd_dlg")
        if d is not None:
            try:
                d.refresh(view)
            except RuntimeError:
                self._upd_dlg = None
        if self._tab == "net" and (not view or view.get("state") in ("offer", "ready", "error")):
            self._fill_settings_later() if hasattr(self, "_fill_settings_later") else self._fill_net()

    def open_update(self):
        if self.node is None:
            return
        d = UpdateDialog(self)
        self._upd_dlg = d
        d.exec()
        self._upd_dlg = None

    def _upd_who(self, onion) -> str:
        import net_update
        if onion == net_update.DEV_ONION and not self.node.store.contact(onion):
            return "автор ECHOES"
        if onion == self.node.me.onion:
            return "вы"
        return self._name(onion) if self.node.store.contact(onion) else onion[:8] + "…"

    def upd_install(self, stage):
        """Запустить установщик и закрыть плеер — он заменит файлы и откроет ECHOES снова."""
        import net_update
        import os
        import sys
        from PyQt6.QtWidgets import QApplication
        argv = [sys.executable] + [os.path.abspath(sys.argv[0])] + sys.argv[1:] if sys.argv and sys.argv[0] \
            else [sys.executable, str(net_update.APP_DIR / "main.py")]
        try:
            net_update.launch_apply(stage, self.node.app_dir, argv, self.node.upd_home)
        except Exception as e:                                 # noqa: BLE001
            self.toast(f"Не получилось запустить установку: {e}")
            return
        self.win._really_quit = True
        try:
            self.win.close()
        finally:
            QApplication.instance().quit()

    def _update_card(self) -> QWidget:
        """«Обновления ECHOES»: новые версии приходят с GitHub (github_update) — кнопка «Обновить» в шапке окна.
        Раздача сборок через Echoes.NET убрана: старые версии, получившие её раньше, ещё докачиваются у тех,
        у кого она есть (протокол в net_core остаётся), но новые раздачи не принимаются и не создаются."""
        import github_update
        f, v = card()
        head = QHBoxLayout()
        head.addWidget(lbl("ОБНОВЛЕНИЯ ECHOES", "Section"), 1)
        ask = ghost_btn("  Проверить сейчас")
        ask.setIcon(ya_icon("search", 14))

        def check():
            gh = github_update.install(self.win)
            gh.check(manual=True)
            self.toast("Проверяю новую версию на GitHub…")
        ask.clicked.connect(check)
        head.addWidget(ask)
        v.addLayout(head)
        v.addWidget(lbl("Новые версии приходят с GitHub: когда выйдет обновление, в шапке окна появится кнопка "
                        "«Обновить». ECHOES скачает его, закроется на минуту и откроется уже обновлённым — "
                        "настройки, плейлисты и библиотека не трогаются.", "YaSub", wrap=True))
        v.addWidget(lbl(f"Установлена версия {github_update.local_version() or '—'}", "NetName", wrap=True))
        return f

    def _notify_card(self) -> QWidget:
        """«Уведомления»: что показывать, звук, где на экране, сколько держать."""
        import net_notify as NN
        nd = self.node
        s = nd.settings
        c = NN.cfg(s)

        def put(key, val, sub=None):
            cur = s.get("notif") if isinstance(s.get("notif"), dict) else {}
            cur = dict(cur)
            if sub is None:
                cur[key] = val
            else:
                k2 = dict(NN.cfg(s)["kinds"])
                k2[sub] = bool(val)
                cur["kinds"] = k2
            s["notif"] = cur
            nd.save_settings()

        f, v = card()
        head = QHBoxLayout()
        head.addWidget(lbl("УВЕДОМЛЕНИЯ", "Section"), 1)
        test = ghost_btn("  Проверить")
        test.setIcon(ya_icon("play", 14))
        test.setToolTip("Показать пример уведомления со звуком")
        test.clicked.connect(lambda: self.alert("message", "Echoes", "Так выглядят уведомления — нажмите, чтобы открыть",
                                                onion=nd.me.onion, force=True))
        head.addWidget(test)
        v.addLayout(head)
        v.addWidget(lbl("Карточки в углу экрана со звуком — даже когда плеер свёрнут.", "YaSub", wrap=True))

        def sw_row(lay, on, title, sub, fn):
            h = QHBoxLayout()
            w = Switch(bool(on))
            w.toggled.connect(fn)
            h.addWidget(w)
            c2 = QVBoxLayout(); c2.setSpacing(0)
            c2.addWidget(lbl(title, "NetName"))
            if sub:
                c2.addWidget(lbl(sub, "YaSub", wrap=True))
            h.addLayout(c2, 1)
            lay.addLayout(h)
            return w

        sw_row(v, c["enabled"], "Показывать уведомления", "", lambda on: put("enabled", bool(on)))
        sw_row(v, c["dnd"], "Не беспокоить", "временно ничего не показывать и не звучать",
               lambda on: put("dnd", bool(on)))
        v.addSpacing(4)
        v.addWidget(lbl("О ЧЁМ СООБЩАТЬ", "YaSub"))
        for k, title, sub in NN.KINDS:
            sw_row(v, c["kinds"].get(k, True), title, sub, lambda on, k=k: put(None, on, sub=k))
        v.addSpacing(4)
        v.addWidget(lbl("ЗВУК", "YaSub"))
        sw_row(v, c["sound"], "Звук уведомления", "", lambda on: put("sound", bool(on)))
        from PyQt6.QtWidgets import QSlider, QFileDialog
        vr = QHBoxLayout()
        vr.addWidget(lbl("Громкость"))
        vol = QSlider(Qt.Orientation.Horizontal)
        vol.setRange(0, 100)
        vol.setValue(c["volume"])
        vol.setMaximumWidth(260)
        vlab = lbl(f"{c['volume']}%", "YaSub")
        vol.valueChanged.connect(lambda x: (vlab.setText(f"{x}%"), put("volume", int(x))))
        vol.sliderReleased.connect(lambda: self.notifier.sound(force=True))
        vr.addWidget(vol)
        vr.addWidget(vlab)
        vr.addStretch(1)
        v.addLayout(vr)
        sr = QHBoxLayout()
        cur_snd = lbl("Свой звук: " + Path(c["sound_file"]).name if c["sound_file"] else "Звук: стандартный ECHOES",
                      "YaSub")
        sr.addWidget(cur_snd, 1)
        pick = ghost_btn("Свой звук…")

        def pick_sound():
            fn, _ = QFileDialog.getOpenFileName(self, "Звук уведомления", "", "Звук (*.mp3 *.wav *.ogg *.m4a *.flac)")
            if fn:
                put("sound_file", fn)
                cur_snd.setText("Свой звук: " + Path(fn).name)
                self.notifier.sound(force=True)
        pick.clicked.connect(pick_sound)
        sr.addWidget(pick)
        rs = ghost_btn("Стандартный")
        rs.clicked.connect(lambda: (put("sound_file", ""), cur_snd.setText("Звук: стандартный ECHOES"),
                                    self.notifier.sound(force=True)))
        sr.addWidget(rs)
        v.addLayout(sr)
        v.addSpacing(4)
        v.addWidget(lbl("ВИД", "YaSub"))
        g = QHBoxLayout()
        g.addWidget(lbl("Где"))
        pos = QComboBox()
        for k, t in NN.POSITIONS:
            pos.addItem(t, k)
        pos.setCurrentIndex(max(0, [k for k, _ in NN.POSITIONS].index(c["pos"]) if c["pos"] in dict(NN.POSITIONS) else 0))
        pos.currentIndexChanged.connect(lambda _i: put("pos", pos.currentData()))
        g.addWidget(pos)
        g.addSpacing(10)
        g.addWidget(lbl("Держать"))
        dur = QComboBox()
        for sec in (3, 5, 6, 8, 10, 15, 30):
            dur.addItem(f"{sec} с", sec)
        dur.setCurrentIndex(max(0, dur.findData(c["duration"])))
        dur.currentIndexChanged.connect(lambda _i: put("duration", int(dur.currentData())))
        g.addWidget(dur)
        g.addSpacing(10)
        g.addWidget(lbl("Стиль"))
        sty = QComboBox()
        sty.addItem("Echoes (в углу экрана)", "echoes")
        sty.addItem("Как в Windows", "windows")
        sty.setCurrentIndex(0 if c["style"] == "echoes" else 1)
        sty.currentIndexChanged.connect(lambda _i: put("style", sty.currentData()))
        g.addWidget(sty)
        g.addStretch(1)
        v.addLayout(g)
        sw_row(v, c["preview"], "Показывать текст сообщения", "выключите — будет просто «Новое сообщение»",
               lambda on: put("preview", bool(on)))
        sw_row(v, c["background_only"], "Только когда плеер свёрнут", "в открытом плеере уведомлений не будет",
               lambda on: put("background_only", bool(on)))
        return f

    def _voice_card(self) -> QWidget:
        """«Голос и звонки»: устройства, шумодав, автоусиление, чувствительность, проверка микрофона."""
        nd = self.node
        s = nd.settings
        f, v = card()
        head = QHBoxLayout()
        head.addWidget(lbl("ГОЛОС И ЗВОНКИ", "Section"), 1)
        v.addLayout(head)
        from duel_settings import tr as ui_text
        v.addWidget(lbl(ui_text(self.win,'Автоматический кодек: Opus 48 кГц или ADPCM 24 кГц.',
                               'Automatic codec: Opus 48 kHz or ADPCM 24 kHz.'), 'YaSub'))
        v.addWidget(lbl("Звонки — в шапке переписки («Позвонить», «Созвон» в группе). "
                        "Голос идёт напрямую (UDP/Tor/LAN); через одни только релеи звонок не пройдёт — "
                        "это видно на плитке участника.", "YaSub", wrap=True))
        if not hasattr(self,'_voice_devices'):self._voice_devices=_VoiceDevices(self)
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        for row, (key, title) in enumerate((("voice_in", "Микрофон"), ("voice_out", "Вывод"))):
            g.addWidget(lbl(title), row, 0)
            cb = QComboBox()
            cur = s.get(key)
            self._voice_devices.bind(cb,key,cur)

            def chg(_i, cb=cb, key=key):
                s[key] = cb.currentData() if cb.currentData() != -1 else None
                nd.save_settings()
                vv = self._voice
                if vv is not None and key == "voice_in" and vv.mic_active:
                    vv.mic_off(); vv.mic_on()                  # переоткрыть с новым микрофоном
                if vv is not None and key == "voice_out" and vv._out is not None:
                    try:
                        vv._out.stop(); vv._out.close()
                    except Exception:                          # noqa: BLE001
                        pass
                    vv._out = None
            cb.currentIndexChanged.connect(chg)
            g.addWidget(cb, row, 1)
        g.setColumnStretch(1, 1)
        v.addLayout(g)
        nr = QHBoxLayout()
        nr.addWidget(lbl("Шумодав"))
        ns = QComboBox()
        for lvl, t in ((0, "Выключен"), (1, "Обычный — убирает шум, голос естественный"),
                       (2, "Сильный — для шумной комнаты, вентилятора, клавиатуры")):
            ns.addItem(t, lvl)
        ns.setCurrentIndex(int(s.get("voice_ns", 1)))

        def set_ns(_i):
            s["voice_ns"] = int(ns.currentData())
            nd.save_settings()
            if self._voice is not None:
                self._voice.set_ns(int(ns.currentData()))
        ns.currentIndexChanged.connect(set_ns)
        nr.addWidget(ns, 1)
        v.addLayout(nr)
        ag = QHBoxLayout()
        sw = Switch(bool(s.get("voice_agc", True)))
        sw.toggled.connect(lambda on: (s.__setitem__("voice_agc", bool(on)), nd.save_settings()))
        ag.addWidget(sw)
        c2 = QVBoxLayout(); c2.setSpacing(0)
        c2.addWidget(lbl("Автоусиление", "NetName"))
        c2.addWidget(lbl("тихий микрофон подтягивается, громкий не хрипит", "YaSub"))
        ag.addLayout(c2, 1)
        v.addLayout(ag)
        from PyQt6.QtWidgets import QSlider
        for key, title, lo, hi, default, fmt in (("voice_out_vol", "Громкость собеседников", 0, 200, 100, "{}%"),
                                                  ("voice_in_vol", "Громкость микрофона", 20, 300, 100, "{}%")):
            r = QHBoxLayout()
            r.addWidget(lbl(title))
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(lo, hi)
            sl.setValue(int(float(s.get(key, default / 100)) * 100))
            sl.setMaximumWidth(260)
            vl = lbl(fmt.format(sl.value()), "YaSub")
            sl.valueChanged.connect(lambda x, key=key, vl=vl, fmt=fmt: (vl.setText(fmt.format(x)),
                                                                       s.__setitem__(key, x / 100.0)))
            sl.sliderReleased.connect(nd.save_settings)
            r.addWidget(sl)
            r.addWidget(vl)
            r.addStretch(1)
            v.addLayout(r)
        # проверка микрофона: уровень + «слышать себя»
        tr = QHBoxLayout()
        meter = QProgressBar()
        meter.setTextVisible(False)
        meter.setFixedHeight(8)
        meter.setRange(0, 100)
        tst = ghost_btn("  Проверить микрофон")
        tst.setCheckable(True)
        tst.setToolTip("Говорите — полоска покажет уровень, а вы услышите себя (с шумодавом). Лучше в наушниках.")
        tmr = QTimer(f)
        tmr.setInterval(60)

        def upd():
            vv = self._voice
            meter.setValue(int((vv.level if vv is not None else 0) * 100))
            meter.setStyleSheet("QProgressBar::chunk{background:%s;border-radius:4px;}" %
                                ("#23a55a" if vv is not None and vv.talking else "#4e5058"))
        tmr.timeout.connect(upd)

        def test(on):
            vv = self.calls.ensure_engine()
            if on:
                try:
                    if not vv.mic_active:
                        vv.sink = None
                        vv.mic_on()
                        vv._test_owned = True
                    vv.loopback = True
                    tmr.start()
                    tst.setText("  Остановить проверку")
                except Exception as e:                         # noqa: BLE001
                    self.toast(f"Микрофон не включился: {e}")
                    tst.setChecked(False)
            else:
                vv.loopback = False
                vv.drop("__me__")
                if getattr(vv, "_test_owned", False) and nd.cur_call is None and \
                        nd.room_host is None and not nd.room_guest:
                    vv.mic_off()
                vv._test_owned = False
                tmr.stop()
                meter.setValue(0)
                tst.setText("  Проверить микрофон")
        tst.toggled.connect(test)
        f.destroyed.connect(lambda *_: test(False) if self._voice is not None and self._voice.loopback else None)
        tr.addWidget(tst)
        tr.addWidget(meter, 1)
        v.addLayout(tr)
        return f

    def _subs_card(self) -> QWidget:
        """Список подписок (кнопка «Подписаться» в профиле)."""
        nd = self.node
        f, v = card()
        v.addWidget(lbl("ПОДПИСКИ", "Section"))
        subs = nd.subs()
        if not subs:
            v.addWidget(lbl("Пока ни на кого. Откройте профиль человека и нажмите «Подписаться» — "
                            "о его новых постах придёт уведомление.", "YaSub", wrap=True))
            return f
        for k, ent in sorted(subs.items(), key=lambda kv: -float(kv[1].get("t") or 0))[:50]:
            onion = "" if k.startswith("n:") else k
            npub = ent.get("npub") or (k[2:] if k.startswith("n:") else "")
            name = (self._name(onion) if onion and nd.store.contact(onion) else "") or ent.get("name") or \
                (onion or npub)[:8]
            h = QHBoxLayout()
            av = QLabel(); av.setFixedSize(30, 30)
            av.setPixmap(self._av(onion or npub, name, 30))
            h.addWidget(av)
            nm = lbl(name, "NetName")
            h.addWidget(nm, 1)
            op = ghost_btn("Профиль")
            op.clicked.connect(lambda _=False, o=onion, n=npub: self.open_profile(o) if o else self.open_public(n))
            h.addWidget(op)
            un = ghost_btn("Отписаться")
            un.clicked.connect(lambda _=False, o=onion, n=npub, nm_=name: (nd.set_subscribed(o, n, nm_, False),
                                                                           self.toast(f"Вы отписались от {nm_}"),
                                                                           self._fill_net()))
            h.addWidget(un)
            v.addLayout(h)
        return f

    def _gif_card(self) -> QWidget:
        nd = self.node
        s = nd.settings
        f, v = card()
        v.addWidget(lbl("GIF", "Section"))
        v.addWidget(lbl("Поиск GIF работает на вашем бесплатном ключе (у Tenor и Giphy ключ личный — общего быть не "
                        "может). «Подключить» откроет страницу ключа, а скопированный ключ ECHOES подхватит сам. "
                        "Сохранённые GIF («Мои GIF») работают и без ключа.", "YaSub", wrap=True))
        cr = QHBoxLayout()
        conn = accent_btn("Подключить Tenor / Giphy")

        def do_connect():
            from net_gif import ConnectDialog
            if ConnectDialog(self, s, nd.save_settings).exec():
                self._fill_settings_later()
        conn.clicked.connect(do_connect)
        cr.addWidget(conn)
        ok = [k for k in ("tenor", "giphy") if s.get(f"gif_key_{k}")]
        cr.addWidget(lbl("Подключено: " + ", ".join(k.title() for k in ok) if ok else "Пока не подключено", "YaSub"))
        cr.addStretch(1)
        v.addLayout(cr)
        keys = {}
        for prov, title in (("tenor", "Ключ Tenor"), ("giphy", "Ключ Giphy")):
            h = QHBoxLayout()
            h.addWidget(lbl(title, "NetName"))
            e = QLineEdit(s.get(f"gif_key_{prov}", ""))
            e.setEchoMode(QLineEdit.EchoMode.Password)
            e.setPlaceholderText("вставьте ключ")
            h.addWidget(e, 1)
            keys[prov] = e
            v.addLayout(h)
        sv = accent_btn("Сохранить ключи")

        def save():
            for prov, e in keys.items():
                s[f"gif_key_{prov}"] = e.text().strip()
            nd.save_settings()
            self.toast("Ключи GIF сохранены")
        sv.clicked.connect(save)
        r = QHBoxLayout(); r.addWidget(sv); r.addStretch(1)
        v.addLayout(r)
        return f

    def _fill_settings_later(self):
        try:
            QTimer.singleShot(0, lambda: self._refresh_tab(self._tab))
        except Exception:                                      # noqa: BLE001
            pass

    def _reactions_card(self) -> QWidget:
        """Свои реакции: маленькие картинки, которыми можно реагировать на посты."""
        import net_reactions as NR
        f, v = card()
        v.addWidget(lbl("СВОИ РЕАКЦИИ", "Section"))
        v.addWidget(lbl("Любая картинка станет реакцией (ужмётся до 64×64). Ставьте её на посты через «+» "
                        "у реакций — друзья увидят именно вашу картинку.", "YaSub", wrap=True))
        from yamusic_theme import FlowLayout
        box = QWidget()
        box.setObjectName("YaPage")
        flow = FlowLayout(box)
        items = NR.mine()
        for it in items:
            b = QPushButton()
            b.setIcon(QIcon(NR.pixmap(it["id"], 34)))
            b.setIconSize(QSize(34, 34))
            b.setFixedSize(48, 48)
            b.setToolTip(f"{it['name']} — нажмите, чтобы переименовать или удалить")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("QPushButton{background:rgba(255,255,255,0.06);border:none;border-radius:12px;}"
                            "QPushButton:hover{background:rgba(255,255,255,0.14);}")
            b.clicked.connect(lambda _=False, it=it, b=b: self._reaction_menu(it, b))
            flow.addWidget(b)
        if items:
            v.addWidget(box)
        r = QHBoxLayout()
        add = accent_btn("  Добавить реакцию…")
        add.setIcon(ya_icon("plus", 14, "#000000"))
        add.clicked.connect(self._reactions_dialog)
        r.addWidget(add)
        r.addWidget(lbl(f"{len(items)} из {NR.MAX_MINE}", "YaSub"))
        r.addStretch(1)
        v.addLayout(r)
        return f

    def _reactions_dialog(self):
        import net_reactions as NR
        fns, _ = QFileDialog.getOpenFileNames(self, "Картинки для реакций", str(Path.home()),
                                              "Картинки (*.png *.jpg *.jpeg *.gif *.webp *.bmp)")
        added, errs = 0, []
        for fn in fns:
            try:
                NR.add(fn)
                added += 1
            except Exception as e:                             # noqa: BLE001
                errs.append(f"{Path(fn).name}: {e}")
        if added:
            self.toast(f"Добавлено реакций: {added}")
            self._fill_settings_later()
            if self._tab == "feed":
                self._fill_feed()
        if errs:
            self.toast("Не получилось: " + "; ".join(errs)[:200])

    def _reaction_menu(self, it, btn):
        import net_reactions as NR
        from PyQt6.QtWidgets import QInputDialog
        m = QMenu(self)

        def ren():
            name, ok = QInputDialog.getText(self, "Название реакции", "Название:", text=it["name"])
            if ok and name.strip():
                NR.rename(it["id"], name.strip())
                self._fill_settings_later()
        m.addAction("Переименовать", ren)
        m.addAction("Удалить", lambda: (NR.remove(it["id"]), self._fill_settings_later()))
        m.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _moderation_card(self) -> QWidget:
        nd = self.node
        s = nd.settings
        f, v = card()
        v.addWidget(lbl("МОДЕРАЦИЯ", "Section"))
        v.addWidget(lbl("Серверов нет — фильтрует ваш ECHOES. Скрывается продажа наркотиков и закладки, "
                        "насилие над детьми, терроризм, продажа оружия, пробив и подделка документов, «группы смерти». "
                        "Мат — можно. Запрещённое нельзя и опубликовать.", "YaSub", wrap=True))
        for key, title, sub in (
                ("moderation", "Фильтр запрещённого", "рекомендуется: ловит и обходы (латиница, цифры, «з а к л а д к и»)"),
                ("trust_reports", "Доверять жалобам друзей", "на кого пожаловался друг — скрыт и у вас"),
                ("blur_media", "Размывать чужие фото и видео", "пока не нажмёте «Показать» — защита от нюда и шок-контента")):
            h = QHBoxLayout()
            sw = Switch(bool(s.get(key, True)))
            sw.toggled.connect(lambda on, k=key: (s.__setitem__(k, bool(on)), nd.save_settings()))
            h.addWidget(sw)
            col = QVBoxLayout(); col.setSpacing(0)
            col.addWidget(lbl(title, "NetName"))
            col.addWidget(lbl(sub, "YaSub", wrap=True))
            h.addLayout(col, 1)
            v.addLayout(h)
        mine = nd.my_reports()
        v.addWidget(lbl(f"ВАШИ ЖАЛОБЫ · {len(mine)}", "Section"))
        if not mine:
            v.addWidget(lbl("Пока нет. «Пожаловаться и скрыть…» — в меню «⋯» у любого поста.", "YaSub"))
        for r in mine[:30]:
            h = QHBoxLayout()
            prof = next((pp for pp in self._pub()["profiles"].values()
                         if r["target"] in (pp.get("onion"), pp.get("npub"))), {})
            who = self._name(r["target"]) if nd.store.contact(r["target"]) else (prof.get("name") or r["target"][:10] + "…")
            h.addWidget(lbl(f"{who} — {r['reason']}", "YaSub"), 1)
            un = ghost_btn("Вернуть")
            un.clicked.connect(lambda _=False, t=r["target"]: (nd.call(nd.unreport, t),
                                                                QTimer.singleShot(400, self._fill_net)))
            h.addWidget(un)
            v.addLayout(h)
        return f

    def _transports_card(self) -> QWidget:
        """Пути в сеть: Tor, прямые соединения (LAN / IPv6 / UPnP), Nostr; публичный профиль; раздача треков."""
        nd = self.node
        s = nd.settings
        tr = getattr(nd, "transports", {}) or {}
        f, v = card()
        v.addWidget(lbl("ПУТИ В СЕТЬ", "Section"))
        v.addWidget(lbl("ECHOES пробует все включённые пути и берёт самый быстрый. Если Tor блокируют — друзья "
                        "всё равно на связи: напрямую или через Nostr.", "YaSub", wrap=True))
        nos = getattr(nd, "nostr", None)
        rows = (
            ("use_tor", True, "Tor", "анонимно, IP скрыт; медленнее" + ("  · работает" if tr.get("tor") else "")),
            ("direct", True, "Прямые соединения", "быстро (голос, файлы); друзья видят ваш IP"
             + (f"  · {tr['direct']}" if tr.get("direct") else "")),
            ("lan", True, "Локальная сеть", "плееры в одном Wi-Fi находят друг друга сами, даже без интернета"),
            ("upnp", True, "Открыть порт на роутере (UPnP)", "чтобы друзья достучались напрямую из интернета"),
            ("nostr", True, "Nostr", "бесплатные открытые релеи: публичная сеть и запасная почта"
             + (f"  · релеев: {nos.up_count}" if nos else "")),
            ("nostr_tor", True, "Nostr через Tor", "релеи не видят ваш IP"),
            ("udp", True, "Прямой канал (пробивание NAT)", "голос и комнаты без задержек, даже за роутером"),
            ("share_tracks", True, "Раздавать свои треки друзьям", "кнопка «\U000f1014 у друга» и хост комнаты"),
            ("share_game", True, "Показывать, во что играю", "друзья видят «\U000f1003 Играет в …», пока игра на весь экран"),
        )
        for key, dflt, title, sub in rows:
            h = QHBoxLayout()
            sw = Switch(bool(s.get(key, dflt)))
            sw.toggled.connect(lambda on, k=key: (s.__setitem__(k, bool(on)), nd.save_settings(),
                                                  self.push_profile(force=True) if k == "public_profile" else None))
            h.addWidget(sw)
            col = QVBoxLayout(); col.setSpacing(0)
            col.addWidget(lbl(title, "NetName"))
            col.addWidget(lbl(sub, "YaSub", wrap=True))
            h.addLayout(col, 1)
            v.addLayout(h)
        v.addWidget(lbl("РЕЛЕИ NOSTR (по строке)", "Section"))
        from net_nostr import DEFAULT_RELAYS
        rel = QPlainTextEdit("\n".join(s.get("relays") or DEFAULT_RELAYS))
        rel.setFixedHeight(96)
        v.addWidget(rel)
        hr = QHBoxLayout()
        sv = accent_btn("Сохранить пути")

        def save():
            s["relays"] = [x.strip() for x in rel.toPlainText().splitlines() if x.strip().startswith("wss://")][:10]
            nd.save_settings()
            self.toast("Сохранено — применится при следующем включении сети")
        sv.clicked.connect(save)
        hr.addWidget(sv)
        rs = ghost_btn("Перезапустить сеть")
        rs.clicked.connect(lambda: (self.stop_net(), QTimer.singleShot(1500, self.start_net)))
        hr.addWidget(rs)
        hr.addStretch(1)
        v.addLayout(hr)
        v.addWidget(lbl("При первом прямом соединении Windows может спросить разрешение для Python в брандмауэре — "
                        "разрешите для частных сетей.", "YaSub", wrap=True))
        return f

    def _clear(self, what, text):
        extra = "\nДрузья, посты и заявки тоже удалятся (ваш код останется прежним)." if what == "all" else ""
        if QMessageBox.question(self, text, f"{text}?{extra}") != QMessageBox.StandardButton.Yes:
            return
        self.node.clear(what)
        self._chat_peer = None
        self.toast("Готово")
        self._update_badge()

    def _pick_tor(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Где tor.exe?", str(Path.home()), "tor.exe (tor.exe)")
        if fn:
            self.node.settings["tor_path"] = fn
            self.node.save_settings()
            self._fill_net()

    def _download_tor(self):
        if getattr(self, "_dl_busy", False):
            return
        if QMessageBox.question(self, "Скачать Tor",
                                "Скачать Tor Expert Bundle (~20 МБ) с официального сайта dist.torproject.org?\n"
                                "Он будет лежать в папке плеера и запускаться только для Echoes.NET.") != \
                QMessageBox.StandardButton.Yes:
            return
        self._dl_busy = True
        self.dl_bar.show()
        self.dl_bar.setValue(0)
        import threading

        def work():
            try:
                self.node.tor.download(lambda k: self.bridge.ev.emit("_dl", k))
                self.bridge.ev.emit("_dl", "ok")
            except Exception as e:                             # noqa: BLE001
                self.bridge.ev.emit("_dl", f"err:{e}")
        self.bridge.ev.connect(self._dl_event)
        threading.Thread(target=work, daemon=True).start()

    def _dl_event(self, kind, data):
        if kind != "_dl":
            return
        if isinstance(data, float):
            try:
                self.dl_bar.setValue(int(data * 100))
            except RuntimeError:
                pass
            return
        self._dl_busy = False
        try:
            self.bridge.ev.disconnect(self._dl_event)
        except TypeError:
            pass
        if data == "ok":
            self.toast("Tor скачан — включаю сеть")
            self.start_net()
        else:
            self.toast(f"Не удалось скачать Tor: {str(data)[4:]}")
        self._fill_net()

    # ══════════════════════════ ПРОФИЛЬ ══════════════════════════ #

    ACH = {                                  # id: (название, как получить)
        "first_post": ("Первый пост", "Опубликовать первый пост"),
        "author": ("Автор", "10 постов в ленте"),
        "social": ("Душа компании", "5 друзей в Echoes.NET"),
        "dj": ("Диджей", "Открыть комнату «Слушать вместе»"),
        "together": ("Вместе", "Слушать в комнате друга"),
        "inseparable": ("Неразлучные", "3 дня подряд слушать вместе с другом"),
        "sleuth": ("Шерлок", "Угадать 3 трека в «Угадай трек»"),
        "hitmaker": ("Хитмейкер", "Ваш трек — №1 в чарте друзей"),
        "melomane": ("Меломан", "100 часов музыки"),
        "collector": ("Коллекционер", "500 треков в коллекции"),
        "group": ("Своя тусовка", "Создать групповой чат"),
        "champion": ("Чемпион недели", "Победить в музыкальном челлендже недели"),
        "night_owl": ("Ночной слушатель", "50 прослушиваний с полуночи до 5 утра"),
        "early_bird": ("Жаворонок", "50 прослушиваний с 5 до 9 утра"),
        "streak7": ("7 дней подряд", "Слушать музыку каждый день неделю подряд (от 10 минут)"),
        "explorer": ("Исследователь", "100 разных исполнителей"),
        "loyal": ("Преданный фанат", "100 прослушиваний одного исполнителя"),
        "marathon": ("Марафон", "5 часов музыки за один день"),
    }

    def _contact_label(self, onion) -> str:
        c = self.node.store.contact(onion) if self.node else None
        return (c or {}).get("name") or (self.node._contact_name(onion) if self.node else "") or onion[:8]

    def quiz_live_start(self, preselect=()):
        """«Угадай трек вместе»: позвать друзей — треки из коллекций всех игроков вперемешку."""
        import net_quiz_live
        if not self.running():
            self.toast("Включите сеть, чтобы играть с друзьями")
            return
        net_quiz_live.start(self, preselect)

    # ── оформление профиля: рамка, фон шапки, витрина ── #

    def my_deco(self) -> dict:
        d = dict(self.win.settings.get("ya_profile_deco") or {})
        aura = []                                              # аура — из обложек любимых треков
        try:
            import ya_decor
            for t in (self.node.settings.get("fav") or [])[:4] if self.node else []:
                cv = self._local_cover(t)
                if cv:
                    aura.append(ya_decor.palette(cv)[0][0].name())
        except Exception:                                      # noqa: BLE001
            pass
        if aura:
            d["aura"] = aura[:4]
        return d

    def deco_of(self, onion) -> dict:
        if self.node is None:
            return {}
        if onion == self.node.me.onion:
            return self.my_deco()
        return self.node.public_deco(onion)

    def _frame_of(self, key):
        """Для net_frames: (рамка, ачивки, роль) человека; кэш на 5 с — аватарок в ленте много."""
        nd = self.node
        if nd is None or not key:
            return None
        import time as _t
        cache = self.__dict__.setdefault("_frame_cache", {})
        hit = cache.get(key)
        if hit and _t.monotonic() - hit[0] < 5:
            return hit[1]
        onion = key
        if len(key) == 64:                                     # npub публичного профиля
            onion = next((o for o, n in (nd.__dict__.get("_npk_map") or {}).items() if n == key), "")
        res = None
        if onion:
            try:
                if onion == nd.me.onion:
                    ach_ = self.__dict__.get("_my_ach")
                    if ach_ is None or _t.monotonic() - ach_[0] > 30:
                        ach_ = self._my_ach = (_t.monotonic(), self.achievements())
                    res = ((self.win.settings.get("ya_profile_deco") or {}).get("frame") or {}, ach_[1],
                           nd.role(onion))
                else:
                    res = ((self.deco_of(onion) or {}).get("frame") or {}, nd.contact_profile(onion).get("ach") or [],
                           nd.role(onion))
            except Exception:                                  # noqa: BLE001
                res = None
        cache[key] = (_t.monotonic(), res)
        return res

    def _deco_changed(self):
        self.__dict__.pop("_frame_cache", None)
        self.__dict__.pop("_my_ach", None)
        import net_frames
        net_frames._CACHE.clear()
        self.on_profile_changed()

    def _my_avatar_pm(self, size) -> QPixmap:
        from yamusic_theme import cover_pixmap
        return cover_pixmap(str(self.win.profile.get("avatar") or ""), size, size // 2,
                            seed=self.node._name() if self.node else "me", circle=True)

    def edit_frame(self):
        import net_frames
        if self.node is None:
            return
        d = dict(self.win.settings.get("ya_profile_deco") or {})
        dlg = net_frames.FramePicker(self._my_avatar_pm(160), d.get("frame") or {}, self.achievements(),
                                     self.node.role(self.node.me.onion), self.ACH, self,
                                     gifts=__import__("net_gifts").gifted_frames(self.win))
        if dlg.exec():
            d["frame"] = dlg.result_spec()
            self.win.settings["ya_profile_deco"] = d
            try:
                self.win.save_settings()
            except Exception:                                  # noqa: BLE001
                pass
            self._deco_changed()

    def edit_nick(self):
        """Стиль ника (шрифт с кириллической парой, эффект, цвета) — как в Discord."""
        import net_nick
        if self.node is None:
            return
        d = dict(self.win.settings.get("ya_profile_deco") or {})
        dlg = net_nick.NickStyleDialog(self.node._name(), d.get("nick"), self)
        if dlg.exec():
            d = dict(self.win.settings.get("ya_profile_deco") or {})
            res = dlg.result()
            if res:
                d["nick"] = res
            else:
                d.pop("nick", None)
            self.win.settings["ya_profile_deco"] = d
            try:
                self.win.save_settings()
            except Exception:                                  # noqa: BLE001
                pass
            self.__dict__.pop("_nick_cache", None)
            self._deco_changed()

    def edit_mini(self):
        """Мини-профиль — карточка при наведении на аватарку в ленте."""
        import net_miniprof
        if self.node is None:
            return
        if net_miniprof.MiniEditor(self).exec():
            self._deco_changed()

    def nick_of(self, onion) -> dict:
        """Стиль ника человека (кэш на 5 с — ников в ленте много)."""
        import time as _t
        cache = self.__dict__.setdefault("_nick_cache", {})
        hit = cache.get(onion)
        if hit and _t.monotonic() - hit[0] < 5:
            return hit[1]
        try:
            spec = (self.deco_of(onion) or {}).get("nick") or {}
        except Exception:                                      # noqa: BLE001
            spec = {}
        cache[onion] = (_t.monotonic(), spec)
        return spec

    def name_widget(self, onion, text, px=13) -> QWidget:
        """Ник в ленте: со стилем, если человек его выбрал; иначе — обычная подпись."""
        spec = self.nick_of(onion) if onion else {}
        if spec:
            import net_nick
            return net_nick.NickLabel(text, spec, px + 2)
        return lbl(text, "NetName")

    def edit_showcase(self):
        import net_showcase
        if self.node is None:
            return
        d = dict(self.win.settings.get("ya_profile_deco") or {})
        tracks = []
        t = self.shell.current_track() if hasattr(self.shell, "current_track") else None
        if t:
            tracks.append(t)
        tracks += [x for x in (safe_track(x) for x in self.node.settings.get("fav") or []) if x]
        old = self.__dict__.get("_sc_tools")
        if old is not None:                                    # уже правим — просто показать окошко
            self._open_own_profile()
            return
        tools = net_showcase.ShowcaseTools(d, self._showcase_ctx(self.node.me.onion, True), tracks, self.win)
        self._sc_tools = tools
        tools.saved.connect(self._showcase_saved)
        tools.cancelled.connect(lambda: self._showcase_done(None))
        tools.delete_all.connect(self.delete_showcase)
        tools.changed.connect(self._showcase_live)
        self._open_own_profile()

    def delete_showcase(self):
        """Убрать витрину из профиля совсем (фон шапки и рамка остаются)."""
        from PyQt6.QtWidgets import QMessageBox
        if QMessageBox.question(self.win, "Удалить витрину",
                                "Убрать витрину из профиля? Она пропадёт у всех.") != QMessageBox.StandardButton.Yes:
            return
        d = dict(self.win.settings.get("ya_profile_deco") or {})
        d.pop("sc", None)
        self.win.settings["ya_profile_deco"] = d
        try:
            self.win.save_settings()
        except Exception:                                      # noqa: BLE001
            pass
        tools = self.__dict__.pop("_sc_tools", None)
        self._sc_hdr = None
        if tools is not None:
            tools.hide()
            tools.deleteLater()
        self._deco_changed()

    def _open_own_profile(self):
        """Редактор витрины — прямо в своём профиле (холст вместо витрины + окошко инструментов)."""
        sh = self.shell
        if getattr(sh, "_cur_page", None) == "profile":
            sh.pages["profile"].refresh(force=True)
        else:
            sh.show_page("profile")
            sh.pages["profile"].refresh(force=True)

    def _showcase_live(self):
        """Правки в окошке — сразу в шапке (фон) и на холсте."""
        hdr = self.__dict__.get("_sc_hdr")
        tools = self.__dict__.get("_sc_tools")
        if hdr is None or tools is None:
            return
        try:
            d = dict(self.my_deco())
            d.update(tools.result())
            if "hdr" not in tools.deco:
                d.pop("hdr", None)
            hdr.deco = d
            hdr.update()
        except RuntimeError:
            self._sc_hdr = None

    def _showcase_saved(self, res):
        d = dict(self.win.settings.get("ya_profile_deco") or {})
        if "frame" in d:
            res["frame"] = d["frame"]
        self.win.settings["ya_profile_deco"] = res
        try:
            self.win.save_settings()
        except Exception:                                      # noqa: BLE001
            pass
        self._showcase_done(res)

    def _showcase_done(self, res):
        tools = self.__dict__.pop("_sc_tools", None)
        self._sc_hdr = None
        if tools is not None:
            tools.hide()
            tools.deleteLater()
        if res is not None:
            self._deco_changed()
        else:
            self._open_own_profile()

    def _showcase_ctx(self, onion, me):
        import net_showcase
        nd = self.node
        if me:
            card_ = self.profile_card()
            st, ach, name = card_.get("stats") or {}, self.achievements(), nd._name()
        else:
            prof = nd.contact_profile(onion)
            st, ach, name = prof.get("stats") or {}, prof.get("ach") or [], prof.get("name") or ""
        try:
            npub = nd._nostr_keys()[1] if me else nd._npk_for(onion)
            fol = len(nd.social_info(onion, npub)["followers"])
        except Exception:                                      # noqa: BLE001
            fol = 0
        return net_showcase.Ctx(name, st, self.ACH, ach, fol, play=self.play_meta,
                                cover_of=lambda t: self._local_cover(t), now=self._now_of(onion, me))

    def _now_of(self, onion, me):
        """Для блока витрины «Сейчас играет»: что играет у хозяина (у друга — из его «в сети»), кэш на 1,5 с."""
        cache = {"t": 0.0, "v": None}

        def get():
            if time.time() - cache["t"] < 1.5:
                return cache["v"]
            v = None
            try:
                if me:
                    cur = self.shell.current_track()
                    v = track_meta(cur) if cur and self.win.engine.is_playing() else None
                elif self._online(onion):
                    c = self.node.store.contact(onion) or {}
                    v = json.loads(c["now"]) if c.get("now") else None
            except Exception:                                  # noqa: BLE001
                v = None
            cache.update(t=time.time(), v=v)
            return v
        return get

    def decorate_header(self, hdr, onion, me):
        """Шапка профиля: свой фон / аура, аватарка с рамкой; у себя — кнопки «Рамка» и «Оформить профиль»."""
        import net_frames
        deco = self.deco_of(onion)
        hdr.deco = deco
        if deco.get("nick"):
            import net_nick
            hdr.nick = net_nick.swap(hdr.nick, hdr.nick.text(), deco["nick"], 54)
        r = self._frame_of(onion)
        eff = net_frames.effective(*r) if r else {}
        if eff:
            hdr.set_frame(eff)
        hdr.update()
        if me:
            from PyQt6.QtWidgets import QMenu
            if self.__dict__.get("_sc_tools") is not None:     # идёт правка — шапка показывает черновик
                self._sc_hdr = hdr
                self._showcase_live()
            b = QPushButton("Оформить профиль")
            b.setObjectName("YaChip")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip("Рамка аватарки, стиль ника, мини-профиль, фон шапки и витрина")

            def menu(_checked=False, b=b):                     # clicked передаёт checked — не путать с кнопкой
                m = QMenu(b)
                m.addAction("Рамка аватарки…", self.edit_frame)
                m.addAction("Стиль ника…", self.edit_nick)
                m.addAction("Мини-профиль (баннер, местоимения, ачивки)…", self.edit_mini)
                has = bool((self.win.settings.get("ya_profile_deco") or {}).get("sc"))
                m.addAction("Изменить витрину и фон шапки" if has else "Создать витрину / фон шапки",
                            self.edit_showcase)
                if has:
                    m.addAction("Удалить витрину из профиля", self.delete_showcase)
                m.exec(b.mapToGlobal(b.rect().bottomLeft()))
            b.clicked.connect(menu)
            hdr.layout().addWidget(b, 0, Qt.AlignmentFlag.AlignBottom)
        return deco

    def showcase_block(self, onion, me, deco=None):
        """Витрина под шапкой (если есть). Своя пустая — подсказка с кнопкой."""
        import net_showcase
        tools = self.__dict__.get("_sc_tools") if me else None
        if tools is not None:                                  # правим — холст на месте витрины
            return tools.make_canvas()
        deco = deco if deco is not None else self.deco_of(onion)
        sc = deco.get("sc") if deco else None
        if not sc or not sc.get("items"):                      # нет витрины — и в профиле её нет
            return None                                        # (создать: «Оформить профиль» → «Создать витрину»)
        view = net_showcase.ShowcaseView(sc, self._showcase_ctx(onion, me))
        if not me:
            return view
        box = QWidget(); box.setObjectName("YaPage")              # своя — с кнопкой «Изменить» в углу
        v = QVBoxLayout(box); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(6)
        row = QHBoxLayout(); row.addStretch(1)
        e = QPushButton("Изменить витрину")
        e.setObjectName("YaChip")
        e.setCursor(Qt.CursorShape.PointingHandCursor)
        e.clicked.connect(lambda: self.edit_showcase())
        row.addWidget(e)
        dl = QPushButton("Удалить витрину")
        dl.setObjectName("YaChip")
        dl.setCursor(Qt.CursorShape.PointingHandCursor)
        dl.clicked.connect(lambda: self.delete_showcase())
        row.addWidget(dl)
        v.addLayout(row)
        v.addWidget(view)
        return box

    def _av(self, onion, name, size, online=None):
        photo = ""
        if self.node is not None:
            photo = str(self.win.profile.get("avatar") or "") if onion == self.node.me.onion \
                else self.node.avatar_path(onion)
        return avatar_pm(onion, name, size, online, photo)

    def _clickable(self, w, onion):
        """Аватар/имя → профиль человека."""
        w.setCursor(Qt.CursorShape.PointingHandCursor)
        w.mousePressEvent = lambda e, o=onion: self.open_profile(o)
        if isinstance(w, QLabel) and w.width() <= 64:          # аватарка: наведи — мини-профиль (net_miniprof)
            return __import__("net_miniprof").hover(self, w, onion)
        w.setToolTip("Открыть профиль")
        return w

    def _stats_data(self) -> dict:
        try:
            return json.loads((data_home.root() / "stats.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _my_tierlist(self) -> dict:
        """Свой тирлист из music_tierlist.json → уровни с треками (без путей к файлам)."""
        try:
            d = json.loads(Path(getattr(self.win, "tierlist_path", data_home.root() / "music_tierlist.json")).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"tiers": []}
        from music_tierlist import track_key
        by_path = {track_key(t.get("path", "")): t for t in self.win.library if track_key(t.get("path", ""))}
        tiers = []
        for tr in (d.get("tiers") or [])[:8]:
            items = [track_meta(by_path[track_key(p)]) for p, tid in (d.get("assignments") or {}).items()
                     if tid == tr.get("id") and track_key(p) in by_path][:20]
            tiers.append({"name": tr.get("name", ""), "color": tr.get("color", "#888888"), "items": items})
        return {"tiers": [t for t in tiers if t["items"]]}

    def _my_tier_of(self) -> dict:
        """Ключ трека → название уровня в своём тирлисте (для сравнения с тирлистом друга)."""
        out = {}
        for tr in self._my_tierlist()["tiers"]:
            for it in tr["items"]:
                out[tkey(it)] = tr["name"]
        return out

    def together_streak(self, onion) -> int:
        """Сколько дней подряд (до сегодня/вчера) вы слушали вместе в комнате."""
        days = set(self.node.settings.get("together", {}).get(onion, []))
        n, d = 0, time.time()
        if time.strftime("%Y-%m-%d", time.localtime(d)) not in days:
            d -= 86400
        while time.strftime("%Y-%m-%d", time.localtime(d)) in days:
            n += 1
            d -= 86400
        return n

    def _note_together(self):
        """Раз в минуту: с кем сейчас слушаем вместе — в календарь серий и счётчики ачивок."""
        nd = self.node
        if time.time() - getattr(self, "_tog_t", 0) < 60:
            return
        self._tog_t = time.time()
        peers = list(nd.room_members) if nd.room_host is not None else ([nd.room_guest] if nd.room_guest else [])
        if not peers:
            return
        today = time.strftime("%Y-%m-%d")
        tog = nd.settings.setdefault("together", {})
        for o in peers:
            days = tog.setdefault(o, [])
            if today not in days:
                days.append(today)
                del days[:-60]
        role = "rooms_hosted" if nd.room_host is not None else "rooms_joined"
        seen = nd.settings.setdefault("_room_days", [])
        if f"{role}:{today}" not in seen:                      # счётчик комнат — раз в день на роль
            seen.append(f"{role}:{today}")
            del seen[:-120]
            nd.settings[role] = int(nd.settings.get(role, 0)) + 1
        nd.save_settings()

    def achievements(self) -> list:
        nd = self.node
        st = nd.store
        me = nd.me.onion
        stats = self._stats_data()
        posts = st.posts(me, 500)
        solved = st.q("SELECT COUNT(*) n FROM reacts WHERE who=? AND kind='solved' AND val='1'", (me,))[0]["n"]
        friends = st.contacts("friend")
        chart = self.friends_chart()
        got = {
            "first_post": len(posts) >= 1,
            "author": len(posts) >= 10,
            "social": len(friends) >= 5,
            "dj": int(nd.settings.get("rooms_hosted", 0)) >= 1,
            "together": int(nd.settings.get("rooms_joined", 0)) >= 1,
            "inseparable": any(self.together_streak(c["onion"]) >= 3 for c in friends),
            "sleuth": solved >= 3,
            "hitmaker": bool(chart) and any(tkey(p.get("track")) == tkey(chart[0][0]) for p in posts if p.get("track")),
            "melomane": float(stats.get("total") or 0) >= 100 * 3600,
            "collector": len(self.win.library) >= 500,
            "group": any(g.get("owner") == me for g in st.groups()),
            "champion": __import__("net_challenge").is_champion(self),
        }
        import net_ach                                         # ачивки по истории прослушиваний
        ex = net_ach.listening_counts(self.win)
        for k in ("night_owl", "early_bird", "streak7", "explorer", "loyal", "marathon"):
            got[k] = ex[k] >= net_ach.NEED[k]
        return [k for k, v in got.items() if v]

    def _avatar_b64(self) -> str:
        path = str(self.win.profile.get("avatar") or "")
        img = QImage(path) if path else QImage()
        if img.isNull():
            return ""
        side = min(img.width(), img.height())
        img = img.copy((img.width() - side) // 2, (img.height() - side) // 2, side, side).scaled(
            160, 160, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
        for q in (85, 70, 55):
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            img.save(buf, "JPG", q)
            raw = bytes(ba)
            b64 = base64.b64encode(raw).decode()
            if len(b64) < 58 * 1024:
                return b64
        return ""

    def profile_card(self) -> dict:
        s = self.node.settings
        stats = self._stats_data()
        return {"name": self.node._name(), "status": str(self.win.profile.get("status") or ""),
                "about": s.get("about", ""), "fav": s.get("fav", []),
                "tier": self._my_tierlist() if s.get("share_tier", True) else {"tiers": []},
                "ach": self.achievements(), "avatar": self._avatar_b64(),
                "follows": [str(a)[:80] for a in (self.win.settings.get("followed_artists") or [])][-40:],
                "lt": __import__("net_social_ui").my_lt(self.win), "pls": __import__("net_social_ui").my_pls(self.win),
                "deco": self.my_deco(),
                "avanim": __import__("ya_avanim").b64_of(self.win.profile.get("avatar_anim") or ""),
                "stats": {"tracks": len(self.win.library), "listened": int(float(stats.get("total") or 0)),
                          "quiz_wins": int((self.win.settings.get("quiz_live") or {}).get("wins", 0)),
                          "quiz_best": int((self.win.settings.get("quiz_live") or {}).get("best", 0)),
                          "friends": len(self.node.store.contacts("friend")),
                          "posts": len(self.node.store.posts(self.node.me.onion, 500))},
                "_avatar_path": str(self.win.profile.get("avatar") or "")}

    def push_profile(self, force=False):
        """Своя карточка профиля → друзьям (только если что-то поменялось)."""
        if not self.running():
            return
        card = self.profile_card()
        sig = hashlib.sha1(json.dumps({k: v for k, v in card.items() if k != "avatar"}, sort_keys=True,
                                      ensure_ascii=False).encode() + card["avatar"][:200].encode()).hexdigest()
        if force or sig != getattr(self, "_card_sig", None):
            self._card_sig = sig
            self.node.call(self.node.set_profile_card, card)

    # ══════════════════════════ ФАЙЛЫ ══════════════════════════ #

    def blur_media(self, fid) -> bool:
        """Размывать чужие фото/видео до клика (настройка «Сети»), если этот файл ещё не открывали."""
        return bool(self.node and self.node.settings.get("blur_media", True)) and             fid not in self.__dict__.setdefault("_revealed_media", set())

    def reveal_media(self, fid, on=True):
        s = self.__dict__.setdefault("_revealed_media", set())
        (s.add if on else s.discard)(fid)

    def register_file_card(self, card):
        import weakref
        self.__dict__.setdefault("_file_cards", {}).setdefault(card.fid, []).append(weakref.ref(card))

    def _file_event(self, fid, state, val):
        cards = self.__dict__.get("_file_cards", {}).get(fid, [])
        alive = []
        for ref in cards:
            c = ref()
            try:
                if c is None or not c.isVisible() and c.parent() is None:
                    continue
                if state == "progress":
                    c.on_progress(val)
                elif state == "waiting":
                    c.on_waiting()
                elif state == "error":
                    c.on_error(val)
                elif state == "done":
                    c.on_done(val)
                    if getattr(c, "_open_when_done", False):
                        c._open_when_done = False
                        QTimer.singleShot(0, c.activate)
                alive.append(ref)
            except RuntimeError:                               # виджет уже удалён вместе с перерисовкой чата
                continue
        self._file_cards[fid] = alive

    def play_local(self, path, meta):
        pv = meta.get("pv") or {}
        self.win.stream_tracks([{"path": path, "title": pv.get("title") or Path(meta["name"]).stem,
                                 "artist": pv.get("artist") or "", "album": "", "duration": int(pv.get("dur") or 0),
                                 "cover": ""}])
        self.toast(f"Играет: {pv.get('title') or meta['name']}")

    def send_files(self, paths):
        paths = [p for p in paths if p and Path(p).is_file()]
        o = self._chat_peer
        if not paths or not o:
            return
        if not self.running():
            self.toast("Включите сеть, чтобы отправлять файлы")
            return
        from net_files import MAX_FILE, human
        text = self.chat_edit.text().strip()
        for i, pth in enumerate(paths[:10]):
            if Path(pth).stat().st_size > MAX_FILE:
                self.toast(f"«{Path(pth).name}» больше {human(MAX_FILE)} — через Tor это слишком долго")
                continue
            self.node.call(self.node.send_file, o, pth, text if i == 0 else "")
        self.chat_edit.clear()
        self.toast(f"Отправляю: {len(paths[:10])} — готовлю превью…")

    def _attach_chat(self):
        if not self._chat_peer:
            return
        fns, _ = QFileDialog.getOpenFileNames(self, "Отправить файлы", str(Path.home()))
        self.send_files(fns)

    def _paste_chat(self):
        """Ctrl+V: картинка из буфера (скриншот) — отправить файлом; файлы из проводника — тоже; иначе текст."""
        cb = QGuiApplication.clipboard()
        md = cb.mimeData()
        if md is not None and md.hasUrls() and any(u.isLocalFile() for u in md.urls()):
            self.send_files([u.toLocalFile() for u in md.urls() if u.isLocalFile()])
            return
        img = cb.image()
        if not img.isNull():
            tmp = DATA_DIR / "files" / "clipboard"
            tmp.mkdir(parents=True, exist_ok=True)
            fn = tmp / time.strftime("скриншот_%Y-%m-%d_%H-%M-%S.png")
            img.save(str(fn), "PNG")
            self.send_files([str(fn)])
            return
        self.chat_edit.paste()

    def _attach_post(self):
        fns, _ = QFileDialog.getOpenFileNames(self, "Файлы к посту (до 6)", str(Path.home()))
        if fns:
            self._post_files_sel = (getattr(self, "_post_files_sel", []) + fns)[:6]
            self._fill_feed()

    def _post_files(self, p) -> QWidget:
        """Вложения поста: фото/видео — сеткой (как альбом в Telegram), остальное — карточками."""
        from net_files_ui import FileCard
        from net_files import clean_meta
        owner = p["author"]
        metas = [m for m in (clean_meta(f) for f in p.get("files") or []) if m]
        w = QWidget(); w.setObjectName("YaPage")
        v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(8)
        media = [m for m in metas if m["kind"] in ("image", "video")]
        other = [m for m in metas if m["kind"] not in ("image", "video")]
        mine = owner == self.node.me.onion
        if media:
            per_row = 1 if len(media) == 1 else 2
            mw = 480 if per_row == 1 else 236
            for i in range(0, len(media), per_row):
                r = QHBoxLayout(); r.setSpacing(8)
                for m in media[i:i + per_row]:
                    r.addWidget(FileCard(self, m, owner, mine=mine, max_w=mw))
                r.addStretch(1)
                v.addLayout(r)
        for m in other:
            v.addWidget(FileCard(self, m, owner, mine=mine, max_w=440))
        if not mine and not self.node.store.contact(owner):
            v.addWidget(lbl("Файлы скачиваются у автора — он не у вас в друзьях.", "YaSub"))
        return w

    # ══════════════════════════ ПУБЛИЧНАЯ СЕТЬ (Nostr) ══════════════════════════ #

    def _pub(self) -> dict:
        return getattr(self.node, "public", None) or {"posts": {}, "profiles": {}, "rooms": {}, "tastes": {},
                                                     "likes": {}, "replies": {}}

    def _pub_name(self, npub, onion="") -> str:
        if onion and self.node.store.contact(onion):
            return self._name(onion)
        prof = self._pub()["profiles"].get(npub) or {}
        return prof.get("name") or f"гость {npub[:6]}"

    def _pub_av(self, npub, name, size, onion=""):
        if onion and (onion == self.node.me.onion or self.node.store.contact(onion)):
            return self._av(onion, name, size)
        photo = (self._pub()["profiles"].get(npub) or {}).get("avatar_file", "")
        return avatar_pm(npub, name, size, None, photo)

    def _fill_public(self, page):
        """Лента «Все»: публичные посты всех пользователей ECHOES (Nostr) — друзья выше, спам отсечён PoW."""
        nd = self.node
        pub = self._pub()
        if not getattr(nd, "nostr", None):
            page.v.addWidget(Hero("Публичная сеть выключена", "Включите Nostr в разделе «Сеть» — появится общая лента "
                                  "всех пользователей ECHOES, публичные комнаты и знакомства по вкусу. Бесплатно: "
                                  "это открытые релеи, своего сервера не нужно.", c1="#7a2cff", c2="#00d4ff",
                                  height=150))
            return
        if not nd.nostr.up_count:
            page.v.addWidget(lbl("Подключаюсь к релеям Nostr…", "YaSub"))
        posts = sorted(pub["posts"].values(), key=lambda p: (-p["ts"]))
        if self.__dict__.get("_pub_only_friends"):
            posts = [p for p in posts if p["friend"]]
        if not posts and nd.nostr.up_count:
            page.v.addWidget(lbl("Пока тихо. Напишите первый публичный пост — включите «Для всех» в поле поста.",
                                 "YaSub", wrap=True))
        n_mod = getattr(nd, "mod_count", 0)
        if n_mod:
            page.v.addWidget(lbl(f"\U000f1005 Модерация скрыла: {n_mod} — запрещённое и авторы, на которых пожаловались",
                                 "YaSub"))
        posts = [p for p in posts if self._type_ok(p)]
        for p in posts[:120]:
            if nd.mod_hidden(p["onion"], p["npub"], p["id"]):           # пожаловались после того, как пост пришёл
                continue
            page.v.addSpacing(6)
            page.v.addWidget(self._public_card(p))

    def _public_card(self, p) -> QWidget:
        nd = self.node
        pub = self._pub()
        f = QFrame(); f.setObjectName("NetCard")
        if p.get("track"):
            f.setStyleSheet(aura_qss(p["track"]))
        v = QVBoxLayout(f); v.setContentsMargins(16, 12, 16, 12); v.setSpacing(8)
        head = QHBoxLayout(); head.setSpacing(10)
        name = self._pub_name(p["npub"], p["onion"])
        av = QLabel(); av.setFixedSize(34, 34)
        av.setPixmap(self._pub_av(p["npub"], name, 34, p["onion"]))
        av.setCursor(Qt.CursorShape.PointingHandCursor)
        av.mousePressEvent = lambda e, n=p["npub"]: self.open_public(n)
        head.addWidget(av)
        col = QVBoxLayout(); col.setSpacing(0)
        nr = QHBoxLayout(); nr.setSpacing(8)
        nr.addWidget(lbl(name + ("  · вы" if p["onion"] == nd.me.onion else ""), "NetName"))
        bd = self._badge(p["onion"])
        if bd is not None:
            nr.addWidget(bd)
        tag_txt = "ДРУГ" if p["friend"] and p["onion"] != nd.me.onion else ("ВСЕ" if p["onion"] else "NOSTR")
        t = lbl(tag_txt)
        t.setStyleSheet("background:rgba(0,212,255,0.14);color:#5ad8ff;border-radius:8px;padding:1px 7px;"
                        "font-size:10px;font-weight:900;letter-spacing:1px;")
        nr.addWidget(t)
        nr.addStretch(1)
        col.addLayout(nr)
        col.addWidget(lbl(ago(p["ts"]), "YaSub"))
        head.addLayout(col, 1)
        mb = icon_button("dots", "Ещё", 30, 16, "#9a9a9a")
        mb.clicked.connect(lambda: self._public_menu(p, mb))
        head.addWidget(mb, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(head)
        text = p["text"]
        if p.get("track"):
            text = text.split("\n\n🎵 ")[0].split("\n\nТрек: ")[0]
        if text.strip():
            v.addWidget(lbl(text, "NetText", wrap=True, sel=True))
        if p.get("track"):
            v.addWidget(TrackChip(p["track"], self.play_meta, page=self, cover=self._local_cover(p["track"])))
        if p.get("gif"):
            v.addWidget(self._gif_widget(p["gif"], 420))
        if p.get("files"):                                     # файлы раздаёт автор (через Tor); превью — сразу
            from net_files_ui import FileCard
            from yamusic_theme import FlowLayout
            fw = QWidget(); fw.setObjectName("YaPage")
            ff = FlowLayout(fw)
            for fm in p["files"]:
                ff.addWidget(FileCard(self, fm, p["onion"], mine=p["onion"] == nd.me.onion,
                                      max_w=236 if len(p["files"]) > 1 else 440))
            v.addWidget(fw)
        likes = pub["likes"].get(p["id"], set())
        mine = getattr(nd, "nostr_pub", "") in likes
        reps = pub["replies"].get(p["id"], {})
        foot = QHBoxLayout(); foot.setSpacing(4)
        lk = QPushButton(f"{'♥' if mine else '♡'} {len(likes) or ''}".strip())
        lk.setObjectName("NetLink")
        lk.setStyleSheet(f"QPushButton#NetLink{{color:{'#ff4fa3' if mine else '#9a9a9a'};font-size:14px;}}")
        lk.setCursor(Qt.CursorShape.PointingHandCursor)
        lk.setEnabled(not mine)
        lk.clicked.connect(lambda: nd.call(nd.public_like, p["id"], p["npub"]))
        foot.addWidget(lk)
        cb = QPushButton(f"  {len(reps)} " + _plural(len(reps), "ответ", "ответа", "ответов"))
        cb.setObjectName("NetLink")
        cb.setIcon(ya_icon("chat", 16, "#9a9a9a"))
        cb.setCursor(Qt.CursorShape.PointingHandCursor)
        key = "pub:" + p["id"]
        cb.clicked.connect(lambda: self._toggle_thread(key))
        foot.addWidget(cb)
        if p["onion"] and p["onion"] != nd.me.onion and not nd.store.contact(p["onion"]):
            add = QPushButton("  Добавить в друзья")
            add.setObjectName("NetLink")
            add.setIcon(ya_icon("plus", 14, "#9a9a9a"))
            add.setCursor(Qt.CursorShape.PointingHandCursor)
            add.clicked.connect(lambda: self._stranger_request(p["onion"], name))
            foot.addWidget(add)
        foot.addStretch(1)
        v.addLayout(foot)
        if key in self._open_threads:
            for r in sorted(reps.values(), key=lambda r: r["created_at"]):
                row = QHBoxLayout(); row.setSpacing(8)
                rn = self._pub_name(r["pubkey"], r.get("onion", ""))
                a2 = QLabel(); a2.setFixedSize(24, 24)
                a2.setPixmap(self._pub_av(r["pubkey"], rn, 24, r.get("onion", "")))
                row.addWidget(a2, 0, Qt.AlignmentFlag.AlignTop)
                c2 = QVBoxLayout(); c2.setSpacing(1)
                h2 = QHBoxLayout(); h2.addWidget(lbl(rn, "NetName")); h2.addWidget(lbl(ago(r["created_at"]), "YaSub"))
                h2.addStretch(1)
                c2.addLayout(h2)
                c2.addWidget(lbl(r["content"][:1000], "NetText", wrap=True, sel=True))
                row.addLayout(c2, 1)
                v.addLayout(row)
            inp = QHBoxLayout()
            e = QLineEdit(); e.setPlaceholderText("Ответить публично…")
            send = (lambda: (nd.call(nd.public_reply, p["id"], p["npub"], e.text()), e.clear()))
            e.returnPressed.connect(send)
            inp.addWidget(e, 1)
            sb = icon_button("send", "Отправить", 36, 18, YELLOW)
            sb.clicked.connect(send)
            inp.addWidget(sb)
            v.addLayout(inp)
        return f

    def _public_menu(self, p, btn):
        m = QMenu(self)
        m.addAction("Открыть профиль", lambda: self.open_public(p["npub"]))
        if p["npub"] != getattr(self.node, "nostr_pub", ""):
            self._report_menu(m, p["onion"] or p["npub"], extra=(p["npub"],) if p["onion"] else (),
                              name=self._pub_name(p["npub"], p["onion"]))
        self._staff_menu(m, p["onion"] or p["npub"], p["id"], self._pub_name(p["npub"], p["onion"]),
                         (p.get("text") or "")[:80])
        if p["onion"] and p["onion"] != self.node.me.onion and not self.node.store.contact(p["onion"]):
            m.addAction("Добавить в друзья", lambda: self._stranger_request(p["onion"],
                                                                            self._pub_name(p["npub"], p["onion"])))
        if p["npub"] != getattr(self.node, "nostr_pub", ""):
            m.addSeparator()
            m.addAction("Скрыть все посты этого автора", lambda: (self.node.call(self.node.mute, p["npub"]),
                                                                  self.toast("Автор скрыт")))
        m.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _stranger_request(self, onion, name):
        from PyQt6.QtWidgets import QInputDialog
        note, ok = QInputDialog.getText(self, "Заявка в друзья", f"Пара слов для {name} (необязательно):")
        if ok:
            self.node.call(self.node.request_stranger, onion, note.strip())
            self.toast(f"Заявка отправлена: {name}. Она попадёт в «Заявки» — человек решит сам")

    def _sub_btn(self, onion="", npub="", name=""):
        """«Подписаться» — уведомления о новых постах этого человека."""
        nd = self.node
        on = nd.is_subscribed(onion, npub)
        b = ghost_btn(("  Вы подписаны" if on else "  Подписаться"))
        b.setIcon(ya_icon("check" if on else "plus", 14, YELLOW if on else "#e8e8e8"))
        b.setToolTip("Отписаться от уведомлений о постах" if on else
                     "Получать уведомление, когда он(а) опубликует новый пост")
        if on:
            b.setStyleSheet(f"QPushButton{{color:{YELLOW};}}")

        def flip():
            now_on = not nd.is_subscribed(onion, npub)
            nd.set_subscribed(onion, npub, name, now_on)
            self.toast(f"Вы подписались на {name} — новые посты придут уведомлением" if now_on
                       else f"Вы отписались от {name}")
            on2 = now_on
            b.setText("  Вы подписаны" if on2 else "  Подписаться")
            b.setIcon(ya_icon("check" if on2 else "plus", 14, YELLOW if on2 else "#e8e8e8"))
            b.setStyleSheet(f"QPushButton{{color:{YELLOW};}}" if on2 else "")
        b.clicked.connect(flip)
        return b

    def open_public(self, npub):
        """Профиль человека из публичной сети (Nostr). Если это друг — обычный профиль."""
        prof = self._pub()["profiles"].get(npub) or {}
        onion = prof.get("onion") or next((p["onion"] for p in self._pub()["posts"].values()
                                           if p["npub"] == npub and p["onion"]), "")
        if onion and (onion == self.node.me.onion or self.node.store.contact(onion)):
            self.open_profile(onion)
            return
        self._profile_onion = None
        self._profile_npub = npub
        self.shell.show_page("net")
        self.show_tab("profile")

    def _fill_public_profile(self, npub):
        from ya_profile import ProfileHeader
        page = self.profile_page
        pub = self._pub()
        prof = pub["profiles"].get(npub) or {}
        onion = prof.get("onion", "")
        if onion and onion != self.node.me.onion and (pub.get("full") or {}).get(onion):
            self._profile_onion = onion                        # полный профиль есть — показать как у друга
            self._fill_profile()
            return
        if onion:
            self.node._want_profile(npub)
        page.clear()
        name = prof.get("name") or f"гость {npub[:6]}"
        hdr = ProfileHeader(page)
        hdr.kicker.setText("Публичный профиль · Echoes.NET")
        posts = [p for p in pub["posts"].values() if p["npub"] == npub]
        hdr.set_profile(name, prof.get("status", ""), prof.get("avatar_file", ""),
                        f"публичных постов: {len(posts)}" + ("  ·  подтверждённый ECHOES" if onion else ""))
        hdr.btn.hide()
        hl = hdr.layout()
        if onion != self.node.me.onion:
            hl.addWidget(self._sub_btn(onion, npub, name), 0, Qt.AlignmentFlag.AlignBottom)
            sb_ = self._profile_staff_btn(onion, name) if onion else None
            if sb_ is not None:
                hl.addWidget(sb_, 0, Qt.AlignmentFlag.AlignBottom)
        if onion and onion != self.node.me.onion and not self.node.store.contact(onion):
            b = accent_btn("Добавить в друзья")
            b.clicked.connect(lambda: self._stranger_request(onion, name))
            hl.addWidget(b, 0, Qt.AlignmentFlag.AlignBottom)
        page.v.addWidget(hdr)
        body = QWidget(); body.setObjectName("YaPage")
        bv = QVBoxLayout(body); bv.setContentsMargins(32, 6, 24, 0); bv.setSpacing(6)
        page.v.addWidget(body)
        t = pub["tastes"].get(npub)
        if t:
            from net_core import taste_match
            mine = getattr(self, "_my_taste", None) or taste_from_stats(self.win)
            pct, common = taste_match(mine, t["taste"])
            f, v = card()
            v.addWidget(lbl("СОВМЕСТИМОСТЬ ВКУСОВ", "Section"))
            big = lbl(f"♥ {pct}%")
            big.setStyleSheet(f"font-size:30px;font-weight:900;color:{QColor.fromHsvF(0.33 * pct / 100, 0.8, 1.0).name()};")
            v.addWidget(big)
            v.addWidget(lbl("Общие: " + (", ".join(common) if common else "пока нет"), "YaSub", wrap=True))
            bv.addSpacing(12)
            bv.addWidget(f)
        if prof.get("about"):
            bv.addWidget(section_title("О себе"))
            bv.addWidget(lbl(prof["about"], "NetText", wrap=True, sel=True))
        fav = [x for x in (safe_track(t) for t in prof.get("fav") or []) if x]
        if fav:
            bv.addWidget(section_title("Любимые треки", lambda: self.play_many(fav, f"любимое {name}")))
            for tr in fav:
                bv.addWidget(TrackChip(tr, self.play_meta, page=self, cover=self._local_cover(tr)))
        if posts:
            bv.addWidget(section_title("Публичные посты"))
            for p in sorted(posts, key=lambda p: -p["ts"])[:30]:
                bv.addWidget(self._public_card(p))
                bv.addSpacing(6)
        bv.addStretch(1)

    def _people_by_taste(self, page):
        """«Люди по вкусу»: публичные профили с самой высокой совместимостью."""
        from net_core import taste_match
        pub = self._pub()
        mine = getattr(self, "_my_taste", None) or taste_from_stats(self.win)
        rows = []
        for npub, t in pub["tastes"].items():
            if t["onion"] == self.node.me.onion or self.node.store.contact(t["onion"]):
                continue
            pct, common = taste_match(mine, t["taste"])
            if pct >= 15:
                rows.append((pct, common, npub, t["onion"]))
        rows.sort(key=lambda r: -r[0])
        page.v.addWidget(section_title("Люди по вкусу"))
        if not getattr(self.node, "nostr", None):
            page.v.addWidget(lbl("Включите Nostr и «Публичный профиль» в разделе «Сеть» — ECHOES подберёт людей "
                                 "с похожей музыкой.", "YaSub", wrap=True))
            return
        if not rows:
            page.v.addWidget(lbl("Пока никого с похожим вкусом — загляните позже.", "YaSub"))
        for pct, common, npub, onion in rows[:12]:
            f, v = card()
            v.setContentsMargins(14, 10, 14, 10)
            h = QHBoxLayout(); h.setSpacing(12)
            nm = self._pub_name(npub, onion)
            av = QLabel(); av.setFixedSize(42, 42)
            av.setPixmap(self._pub_av(npub, nm, 42, onion))
            av.setCursor(Qt.CursorShape.PointingHandCursor)
            av.mousePressEvent = lambda e, n=npub: self.open_public(n)
            h.addWidget(av)
            col = QVBoxLayout(); col.setSpacing(1)
            col.addWidget(lbl(nm, "NetName"))
            col.addWidget(lbl("Общие: " + ", ".join(common[:5]), "YaSub"))
            h.addLayout(col, 1)
            cp = lbl(f"♥ {pct}%")
            cp.setStyleSheet(f"color:{QColor.fromHsvF(0.33 * pct / 100, 0.8, 1.0).name()};font-weight:900;"
                             "font-size:15px;padding:0 8px;")
            h.addWidget(cp)
            ad = accent_btn("Добавить")
            ad.clicked.connect(lambda _=False, o=onion, n=nm: self._stranger_request(o, n))
            h.addWidget(ad)
            v.addLayout(h)
            page.v.addWidget(f)

    def _public_rooms(self, page):
        rooms = [r for r in self._pub()["rooms"].values() if r["onion"] != self.node.me.onion
                 and (not r["exp"] or r["exp"] > time.time()) and (not r.get('radio') or self.node.radio_allowed(r['onion']))]
        page.v.addWidget(section_title("Публичные комнаты"))
        if not getattr(self.node, "nostr", None):
            page.v.addWidget(lbl("Включите Nostr в разделе «Сеть», чтобы видеть открытые комнаты всех пользователей.",
                                 "YaSub", wrap=True))
            return
        if not rooms:
            page.v.addWidget(lbl("Сейчас открытых комнат нет. Откройте свою и отметьте «Публичная».", "YaSub", wrap=True))
            return
        grid = HRow()
        for r in sorted(rooms, key=lambda r: -r["n"])[:20]:
            f, v = card()
            f.setFixedSize(280, 156)
            if r.get("now"):
                f.setStyleSheet(aura_qss(r["now"]))
            h = QHBoxLayout()
            nm = self._pub_name(r["npub"], r["onion"])
            av = QLabel(); av.setFixedSize(36, 36)
            if r.get('radio'):
                from radio_ui import avatar_pixmap
                av.setPixmap(avatar_pixmap(r['radio'].get('avatar',''),36))
            else:
                av.setPixmap(self._pub_av(r["npub"], nm, 36, r["onion"]))
            h.addWidget(av)
            col = QVBoxLayout(); col.setSpacing(0)
            col.addWidget(lbl(r["title"] or "Комната", "NetName"))
            col.addWidget(lbl(f"{nm} · слушателей: {r['n']}" + (f" · {r['genre']}" if r.get("genre") else ""), "YaSub"))
            h.addLayout(col, 1)
            v.addLayout(h)
            if r.get("now"):
                v.addWidget(lbl(QFontMetrics(ya_font(12)).elidedText(f"♪ {r['now']['artist']} — {r['now']['title']}",
                                                                     Qt.TextElideMode.ElideRight, 240), "YaSub"))
            j = accent_btn("Зайти")
            j.clicked.connect(lambda _=False, o=r["onion"]: self.join_room(o))
            v.addWidget(j)
            grid.add(f)
        page.v.addWidget(grid)

    # ── «Взять трек у друга» ── #

    def _lib_path(self, meta) -> str:
        """Для сети (из её потока): свой файл трека, если он есть на диске (потоки — не отдаём)."""
        _i, t = library_match(self.win, meta)
        p = str((t or {}).get("path", ""))
        return p if p and not p.startswith("stream:") and Path(p).is_file() else ""

    def get_track_from(self, owner, meta, play=True):
        if not self.running():
            self.toast("Включите сеть")
            return
        self.__dict__.setdefault("_want_track", {})[tkey(meta)] = play
        self.node.call(self.node.request_track, owner, meta)
        self.toast(f"Прошу файл «{meta.get('title')}» у {self._name(owner)}…")

    def _on_track_file(self, owner, track, fm, why):
        if fm is None:
            self.toast(f"Не получилось взять трек: {why}")
            return
        self.__dict__.setdefault("_track_files", {})[fm["fid"]] = track
        self.toast(f"Качаю «{(track or {}).get('title')}» у {self._name(owner)} · {fm and fm['size'] // 1024} КБ")

    def _maybe_play_track_file(self, fid, path):
        track = self.__dict__.get("_track_files", {}).pop(fid, None)
        if not track:
            return
        play = self.__dict__.get("_want_track", {}).pop(tkey(track), True)
        nd = self.node
        room_tr = (nd.room_state or {}).get("track") if nd.room_guest else None
        if room_tr and tkey(room_tr) == tkey(track):           # гость комнаты: перейти с потока на настоящий файл
            self._sync["follow_path"] = path
            play = True
        if play:
            self.win.stream_tracks([{"path": path, "title": track.get("title", ""), "artist": track.get("artist", ""),
                                     "album": track.get("album", ""), "duration": track.get("duration", 0),
                                     "cover": ""}])
            self.toast(f"Играет файл друга: {track.get('title')}")

    # ══════════════════════════ GIF ══════════════════════════ #

    def _dlg_qss(self) -> str:
        try:
            from echo_glass import glass_controls_qss
            return NET_QSS + glass_controls_qss()
        except Exception:                                      # noqa: BLE001
            return NET_QSS

    def pick_gif(self, on_pick):
        from net_gif import GifPicker
        GifPicker(self, self.node.settings, on_pick, self._dlg_qss(), save_cb=self.node.save_settings).exec()
        self.node.save_settings()

    def _gif_chat(self):
        if not self._chat_peer:
            return
        self.pick_gif(lambda g: self._send_special("", None, {"kind": "gif", "gif": g}))

    def _gif_post(self):
        self.pick_gif(lambda g: (setattr(self, "_post_gif", g), self._fill_feed()))

    def _gif_widget(self, g, max_w=320):
        from net_gif import GifView, clean_gif
        g = clean_gif(g)
        if not g:
            return lbl("GIF недоступна", "YaSub")
        gv = GifView(g, max_w, 260)
        gv.setToolTip("Нажмите — растягиваемое окно; правый клик — в «Мои GIF», сохранить файлом")
        gv.on_menu_change = lambda: self.toast("Мои GIF обновлены")
        return gv

    # ══════════════════════════ ТИПЫ ПОСТОВ ══════════════════════════ #

    POST_TYPES = (("", "Все типы"), ("post", "Посты"), ("daily", "Трек дня"), ("moment", "Моменты"),
                  ("battle", "Баттлы"), ("playlist", "Плейлисты"), ("quiz", "Угадай трек"), ("quote", "Цитаты"),
                  ("repost", "Репосты"), ("mod", "Моды"), ("files", "С файлами"), ("gif", "GIF"))

    def _type_of(self, p) -> set:
        k = p.get("kind", "post") or "post"
        out = {k}
        if k == "post" and p.get("at") is not None:
            out = {"moment"}
        if p.get("files"):
            out.add("files")
        if p.get("gif"):
            out.add("gif")
        return out

    def _type_row(self, page):
        """Вкладки по типам постов: вторая строка фильтров ленты."""
        w = QWidget(); w.setObjectName("YaPage")
        from yamusic_theme import FlowLayout
        fl = FlowLayout(w)
        grp = QButtonGroup(w)
        cur = self.__dict__.get("_feed_type", "")
        for key, text in self.POST_TYPES:
            if self._feed_sort == "all" and key not in ("", "post", "files", "gif"):
                continue                                      # в публичной ленте — только эти типы
            b = QPushButton(text)
            b.setObjectName("YaChip")
            b.setCheckable(True)
            b.setChecked(cur == key)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("QPushButton#YaChip{padding:5px 12px;font-size:12px;border-radius:12px;}")
            b.clicked.connect(lambda _=False, k=key: (self.__dict__.__setitem__("_feed_type", k), self._fill_feed()))
            grp.addButton(b)
            fl.addWidget(b)
        page.v.addWidget(w)

    def _type_ok(self, p) -> bool:
        t = self.__dict__.get("_feed_type", "")
        return not t or t in self._type_of(p)

    # ══════════════════════════ МОДЫ (темы ECHOES) ══════════════════════════ #

    def _build_threads(self) -> QWidget:
        from net_threads import ThreadsView
        self.threads = ThreadsView(self)
        return self.threads

    def _build_mods(self) -> QWidget:
        self.mods_page = Page(margins=(0, 4, 8, 24))
        return self.mods_page

    def _mod_items(self) -> list:
        """Все моды: от друзей (посты) и из общей витрины (Nostr). Свои — тоже."""
        nd = self.node
        items = {}
        for p in nd.store.posts(limit=500):
            if p.get("kind") != "mod":
                continue
            from net_core import clean_mod
            m = clean_mod(p.get("mod"))
            if not m:
                continue
            key = f"p:{m.get('mid') or p['id']}"
            items[m.get("mid") or key] = {"key": key, "title": p.get("title") or "Мод", "desc": p.get("text", ""),
                                          "mod": m, "onion": p["author"], "npub": "", "ts": p["ts"],
                                          "name": self._author_name(p["author"], p.get("name", "")), "src": "friends",
                                          "pid": p["id"]}
        for k, it in (self._pub().get("mods") or {}).items():
            mid = it["mod"].get("mid") or k
            if mid in items:
                items[mid]["src"] = "both"
                continue
            items[mid] = {"key": f"n:{k}", "title": it["title"], "desc": it["desc"], "mod": it["mod"],
                          "onion": it["onion"], "npub": it["npub"], "ts": it["ts"],
                          "name": self._pub_name(it["npub"], it["onion"]), "src": "public"}
        out = [i for i in items.values() if not (i["onion"] != nd.me.onion and nd.mod_hidden(i["onion"], i["npub"], i.get("id")))]
        return sorted(out, key=lambda i: -i["ts"])

    def _installed(self) -> dict:
        return self.node.settings.setdefault("mods_installed", {})

    def _fill_mods(self):
        if self.node is None:
            return
        page = self.mods_page
        page.clear()
        nd = self.node
        top = QHBoxLayout()
        t = lbl("Мастерская модов")
        t.setStyleSheet("font-size:22px;font-weight:900;")
        top.addWidget(t)
        top.addStretch(1)
        self.mod_search = QLineEdit(self.__dict__.get("_mod_q", ""))
        self.mod_search.setPlaceholderText("Найти мод…")
        self.mod_search.setFixedWidth(240)
        self.mod_search.returnPressed.connect(lambda: (self.__dict__.__setitem__("_mod_q", self.mod_search.text()),
                                                       self._fill_mods()))
        top.addWidget(self.mod_search)
        pub = accent_btn("  Выложить")
        pub.setIcon(ya_icon("plus", 14, "#000000"))
        import net_market
        pm_ = QMenu(pub)
        pm_.addAction("Тему ECHOES…", self._publish_mod_dialog)
        pm_.addAction("Свою рамку профиля…", lambda: net_market.publish_dialog(self, "frame"))
        pm_.addAction("Свою витрину…", lambda: net_market.publish_dialog(self, "showcase"))
        pub.clicked.connect(lambda: pm_.exec(pub.mapToGlobal(pub.rect().bottomLeft())))
        top.addWidget(pub)
        page.v.addLayout(top)
        page.v.addWidget(lbl("Темы, рамки и витрины от друзей и всех пользователей. Рамки и витрины ставятся сразу; "
                             "файл темы отдаёт автор напрямую через Tor — скачивание работает, пока он в сети.",
                             "YaSub", wrap=True))
        trow = QHBoxLayout(); trow.setContentsMargins(0, 6, 0, 0)
        tgrp = QButtonGroup(page.inner)
        tcur = self.__dict__.get("_mod_type", "all")
        for key, text in (("all", "Всё"), ("theme", "Темы"), ("frame", "Рамки"), ("showcase", "Витрины")):
            b = QPushButton(text)
            b.setObjectName("YaChip")
            b.setCheckable(True)
            b.setChecked(tcur == key)
            b.clicked.connect(lambda _=False, k=key: (self.__dict__.__setitem__("_mod_type", k), self._fill_mods()))
            tgrp.addButton(b)
            trow.addWidget(b)
        trow.addStretch(1)
        page.v.addLayout(trow)
        prev = self.__dict__.get("_mod_preview")
        if prev:
            f, v = card()
            h = QHBoxLayout()
            h.addWidget(lbl(f"Предпросмотр темы «{prev['title']}» включён", "NetName"), 1)
            keep = accent_btn("Оставить")
            keep.clicked.connect(self._preview_keep)
            back = ghost_btn("Вернуть прежнюю")
            back.clicked.connect(self._preview_revert)
            h.addWidget(keep); h.addWidget(back)
            v.addLayout(h)
            page.v.addWidget(f)
        row = QHBoxLayout(); row.setContentsMargins(0, 8, 0, 4)
        grp = QButtonGroup(page.inner)
        cur = self.__dict__.get("_mod_filter", "all")
        for key, text in (("all", "Все"), ("friends", "От друзей"), ("public", "Витрина"), ("mine", "Мои"),
                          ("installed", "Установленные")):
            b = QPushButton(text)
            b.setObjectName("YaChip")
            b.setCheckable(True)
            b.setChecked(cur == key)
            b.clicked.connect(lambda _=False, k=key: (self.__dict__.__setitem__("_mod_filter", k), self._fill_mods()))
            grp.addButton(b)
            row.addWidget(b)
        row.addStretch(1)
        page.v.addLayout(row)
        items = self._mod_items()
        inst = self._installed()
        q = self.__dict__.get("_mod_q", "").casefold().strip()
        if q:
            items = [i for i in items if q in (i["title"] + " " + i["desc"] + " " + i["name"]).casefold()]
        if tcur != "all":
            items = [i for i in items if net_market.kind_of(i.get("mod")) == tcur]
        if cur == "friends":
            items = [i for i in items if i["src"] in ("friends", "both")]
        elif cur == "public":
            items = [i for i in items if i["src"] in ("public", "both")]
        elif cur == "mine":
            items = [i for i in items if i["onion"] == nd.me.onion]
        elif cur == "installed":
            items = [i for i in items if i["key"] in inst]
            orphans = [k for k in inst if k not in {i["key"] for i in self._mod_items()}]
            for k in orphans:                                  # установлено, но в сети уже не видно
                it = inst[k]
                items.append({"key": k, "title": it.get("title", "Мод"), "desc": "", "mod": {}, "onion": "",
                              "npub": "", "ts": 0, "name": it.get("author", ""), "src": "local"})
        if not items:
            page.v.addSpacing(10)
            page.v.addWidget(Hero("Пока пусто", "Выложите свою тему из конструктора ECHOES — с иконкой и скриншотами. "
                                  "Друзья увидят её сразу, а с публичной сетью — все пользователи.",
                                  c1="#ff4fa3", c2="#7a2cff", height=140))
        from yamusic_theme import FlowLayout
        grid = QWidget(); grid.setObjectName("YaPage")
        fl = FlowLayout(grid)
        for it in items[:120]:
            fl.addWidget(self._mod_card(it, it["key"] in inst))
        page.v.addWidget(grid)
        page.v.addStretch(1)

    def _mod_icon_pm(self, it, size):
        from net_files_ui import _thumb_img
        m = it.get("mod") or {}
        if m.get("type") in ("frame", "showcase"):
            import net_market
            return net_market.preview_pm(self, it, size, size)
        img = QImage()
        if m.get("icon"):
            img.loadFromData(base64.b64decode(m["icon"]))
        elif m.get("shots"):
            img = _thumb_img(m["shots"][0])
        pm = QPixmap(size * 2, size * 2)
        pm.setDevicePixelRatio(2)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
        p.setClipPath(path)
        if not img.isNull():
            s = min(img.width(), img.height())
            p.drawImage(QRectF(0, 0, size, size), img.copy((img.width() - s) // 2, (img.height() - s) // 2, s, s))
        else:
            g = QLinearGradient(0, 0, size, size)
            h = hue_of(it.get("title", ""))
            g.setColorAt(0, QColor.fromHsvF(h, 0.7, 1.0))
            g.setColorAt(1, QColor.fromHsvF((h + 0.2) % 1, 0.8, 0.5))
            p.fillRect(QRectF(0, 0, size, size), g)
            p.setPen(QColor("#ffffff"))
            p.setFont(ya_font(int(size * 0.4), QFont.Weight.Black))
            p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, (it.get("title") or "?")[:1].upper())
        p.end()
        return pm

    def _mod_card(self, it, installed) -> QWidget:
        f, v = card()
        f.setFixedSize(236, 268)
        f.setCursor(Qt.CursorShape.PointingHandCursor)
        f.mouseReleaseEvent = lambda e, it=it: self._mod_dialog(it)
        ic = QLabel(); ic.setFixedSize(204, 120)
        m = it.get("mod") or {}
        if m.get("shots"):                                    # обложка карточки — первый скриншот
            from net_files_ui import _thumb_img
            img = _thumb_img(m["shots"][0])
            pm = QPixmap(204 * 2, 120 * 2); pm.setDevicePixelRatio(2); pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            path = QPainterPath(); path.addRoundedRect(QRectF(0, 0, 204, 120), 12, 12); p.setClipPath(path)
            if not img.isNull():
                k = max(204 / img.width(), 120 / img.height())
                p.drawImage(QRectF((204 - img.width() * k) / 2, (120 - img.height() * k) / 2, img.width() * k,
                                   img.height() * k), img)
            p.end()
            ic.setPixmap(pm)
        else:
            ic.setPixmap(__import__("net_market").preview_pm(self, it, 204, 120) if m.get("type") == "showcase"
                         else self._mod_icon_pm(it, 120))
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(ic)
        h = QHBoxLayout(); h.setSpacing(8)
        small = QLabel(); small.setFixedSize(34, 34)
        small.setPixmap(self._mod_icon_pm(it, 34))
        h.addWidget(small)
        col = QVBoxLayout(); col.setSpacing(0)
        col.addWidget(lbl(QFontMetrics(ya_font(13, QFont.Weight.Bold)).elidedText(it["title"],
                                                                                  Qt.TextElideMode.ElideRight, 160),
                          "NetName"))
        col.addWidget(lbl(QFontMetrics(ya_font(12)).elidedText(
            f"{it['name']}" + (f" · v{m['version']}" if m.get("version") else ""), Qt.TextElideMode.ElideRight, 160),
            "YaSub"))
        h.addLayout(col, 1)
        v.addLayout(h)
        v.addWidget(lbl(QFontMetrics(ya_font(12)).elidedText(it["desc"].replace("\n", " "),
                                                             Qt.TextElideMode.ElideRight, 200), "YaSub"))
        v.addStretch(1)
        if m.get("type") in ("frame", "showcase"):
            import net_market
            worn = net_market.is_worn(self, it)
            b = ghost_btn("★ В профиле") if worn else accent_btn("Надеть" if m["type"] == "frame" else
                                                                 "Поставить в профиль")
            b.clicked.connect(lambda _=False, it=it: net_market.apply(self, it) and self._fill_mods())
            v.addWidget(b)
            return f
        b = ghost_btn("✓ Установлено") if installed else accent_btn("Скачать")
        b.clicked.connect(lambda _=False, it=it: self._mod_dialog(it) if installed else self._mod_get(it, "install"))
        v.addWidget(b)
        return f

    def _mod_dialog(self, it):
        from PyQt6.QtWidgets import QDialog
        d = QDialog(self)
        d.setWindowTitle(it["title"])
        d.setMinimumSize(760, 600)
        d.setStyleSheet(self._dlg_qss() + "QDialog{background:#101113;}")
        outer = QVBoxLayout(d)
        outer.setContentsMargins(0, 0, 0, 0)
        pg = Page(margins=(24, 20, 24, 20))
        outer.addWidget(pg)
        v = pg.v
        v.setSpacing(10)
        h = QHBoxLayout(); h.setSpacing(16)
        ic = QLabel(); ic.setFixedSize(96, 96)
        ic.setPixmap(self._mod_icon_pm(it, 96))
        h.addWidget(ic)
        col = QVBoxLayout(); col.setSpacing(2)
        t = lbl(it["title"])
        t.setStyleSheet("font-size:26px;font-weight:900;")
        col.addWidget(t)
        m = it.get("mod") or {}
        ar = QHBoxLayout(); ar.setSpacing(8)
        if it["onion"]:
            av = QLabel(); av.setFixedSize(26, 26)
            av.setPixmap(self._pub_av(it["npub"], it["name"], 26, it["onion"]) if it["npub"] else
                         self._av(it["onion"], it["name"], 26))
            ar.addWidget(av)
        an = lbl(f"Автор: {it['name']}" + (f"  ·  версия {m['version']}" if m.get("version") else "") +
                 (f"  ·  {ago(it['ts'])}" if it.get("ts") else ""), "YaSub")
        ar.addWidget(an)
        ar.addStretch(1)
        col.addLayout(ar)
        col.addStretch(1)
        h.addLayout(col, 1)
        v.addLayout(h)
        inst = self._installed().get(it["key"])
        br = QHBoxLayout()
        deco_mod = m.get("type") in ("frame", "showcase")
        if deco_mod:
            import net_market
            ap = accent_btn("Надеть рамку" if m["type"] == "frame" else "Поставить в профиль")
            ap.clicked.connect(lambda: net_market.apply(self, it) and (d.accept(), self._fill_mods()))
            br.addWidget(ap)
            big = QLabel()
            big.setPixmap(net_market.preview_pm(self, it, 240 if m["type"] == "frame" else 640, 240))
            v.addWidget(big)
        if m.get("pkg"):
            get = accent_btn("  Скачать и установить" if not inst else "  Переустановить")
            get.setIcon(ya_icon("download", 14, "#000000"))
            get.clicked.connect(lambda: (self._mod_get(it, "install"), d.accept()))
            br.addWidget(get)
            pv = ghost_btn("  Предпросмотр")
            pv.setIcon(ya_icon("palette", 14))
            pv.setToolTip("Включить тему на время — потом «Оставить» или «Вернуть прежнюю»")
            pv.clicked.connect(lambda: (self._mod_get(it, "preview"), d.accept()))
            br.addWidget(pv)
        if inst:
            rm = ghost_btn("Удалить тему")
            rm.clicked.connect(lambda: (self._mod_delete(it["key"]), d.accept()))
            br.addWidget(rm)
        mid = m.get("mid") or ""
        if it["onion"] == self.node.me.onion and mid:          # свой мод: изменить или убрать из мастерской
            ed = ghost_btn("  Изменить")
            ed.setIcon(ya_icon("edit", 14))
            ed.clicked.connect(lambda: (d.accept(), self._publish_mod_dialog(edit=it)))
            if not deco_mod:
                br.addWidget(ed)
            dl = ghost_btn("Удалить мод")
            dl.setStyleSheet("QPushButton{color:#ff6b6b;}")

            def kill():
                if QMessageBox.question(d, "Удалить мод", f"Убрать «{it['title']}» из мастерской у всех?\n"
                                        "У тех, кто уже установил тему, она останется.") \
                        != QMessageBox.StandardButton.Yes:
                    return
                d.accept()
                self.node.call(self.node.delete_mod, mid)
            dl.clicked.connect(kill)
            br.addWidget(dl)
        if it["onion"] and it["onion"] != self.node.me.onion:
            rp = ghost_btn("Пожаловаться")
            rp.clicked.connect(lambda: (self.node.call(self.node.report, it["onion"], "запрещённый мод",
                                                       (it["npub"],) if it["npub"] else ()),
                                        self.toast("Жалоба отправлена — автор скрыт у вас и у друзей"), d.accept(),
                                        self._fill_mods()))
            br.addWidget(rp)
        br.addStretch(1)
        v.addLayout(br)
        if m.get("pkg"):
            v.addWidget(lbl(f"Файл темы: {m['pkg']['name']} · {m['pkg']['size'] // 1024} КБ — скачивается у автора "
                            "через Tor, проверяется SHA-256", "YaSub", wrap=True))
        if m.get("shots"):
            v.addWidget(section_title("Скриншоты"))
            from net_files_ui import FileCard
            from yamusic_theme import FlowLayout
            gw = QWidget(); gw.setObjectName("YaPage")
            gl = FlowLayout(gw)
            for sh in m["shots"]:
                gl.addWidget(FileCard(self, sh, it["onion"], mine=it["onion"] == self.node.me.onion, max_w=330))
            v.addWidget(gw)
        if it["desc"]:
            v.addWidget(section_title("Описание"))
            v.addWidget(lbl(it["desc"], "NetText", wrap=True, sel=True))
        v.addStretch(1)
        d.exec()

    def _mod_get(self, it, mode):
        m = it.get("mod") or {}
        if not m.get("pkg"):
            return
        if not self.running():
            self.toast("Включите сеть, чтобы скачать мод")
            return
        self.__dict__.setdefault("_mod_pending", {})[m["pkg"]["fid"]] = (it, mode)
        st = self.node.file_state(m["pkg"]["fid"])
        if st.get("state") == "have" and st.get("path") and Path(st["path"]).exists():
            self._mod_file_done(m["pkg"]["fid"], st["path"])
            return
        self.toast(f"Скачиваю мод «{it['title']}»…")
        self.node.call(self.node.fetch, m["pkg"], it["onion"], True)     # с зеркал, иначе у автора

    def _mod_file_done(self, fid, path):
        job = self.__dict__.get("_mod_pending", {}).pop(fid, None)
        if not job:
            return
        it, mode = job
        store = getattr(self.win, "theme_store", None)
        if store is None:
            self.toast("Темы недоступны в этом окне")
            return
        prev_theme = self.win.settings.get("theme", "")
        try:
            t = store.import_package(path)
        except Exception as e:                                 # noqa: BLE001
            self.toast(f"Не тема ECHOES или файл повреждён: {e}")
            return
        try:
            self.win.custom_themes_changed()
            from themes import THEMES
            key = next((k for k, dd in THEMES.items() if dd.get("custom") and (dd.get("ct") or {}).get("id") == t["id"]),
                       None)
            if key:
                self.win._apply_theme(key)
        except Exception as e:                                 # noqa: BLE001
            print("[mods] apply:", e)
        if mode == "preview":
            self._mod_preview = {"key": it["key"], "tid": t["id"], "prev": prev_theme, "title": it["title"],
                                 "author": it["name"]}
            self.toast(f"Предпросмотр «{it['title']}» — во вкладке «Моды» можно оставить или вернуть прежнюю")
        else:
            old = self._installed().get(it["key"])
            if old and old.get("tid") and old["tid"] != t["id"]:
                store.delete(old["tid"])
            self._installed()[it["key"]] = {"tid": t["id"], "title": it["title"], "author": it["name"]}
            self.node.save_settings()
            self.toast(f"Тема «{it['title']}» установлена и включена")
        if self._tab == "mods":
            self._fill_mods()

    def _preview_keep(self):
        pr = self.__dict__.pop("_mod_preview", None)
        if pr:
            self._installed()[pr["key"]] = {"tid": pr["tid"], "title": pr["title"], "author": pr["author"]}
            self.node.save_settings()
        self._fill_mods()

    def _preview_revert(self):
        pr = self.__dict__.pop("_mod_preview", None)
        if pr:
            try:
                if pr["prev"]:
                    self.win._apply_theme(pr["prev"])
                if pr["key"] not in self._installed():
                    self.win.theme_store.delete(pr["tid"])
                    self.win.custom_themes_changed()
            except Exception as e:                             # noqa: BLE001
                print("[mods] revert:", e)
        self._fill_mods()

    def _mod_delete(self, key):
        it = self._installed().pop(key, None)
        self.node.save_settings()
        if it and it.get("tid"):
            try:
                cur_id = None
                from themes import THEMES
                cur = THEMES.get(self.win.settings.get("theme", ""), {})
                cur_id = (cur.get("ct") or {}).get("id")
                self.win.theme_store.delete(it["tid"])
                self.win.custom_themes_changed()
                if cur_id == it["tid"]:
                    self.win._apply_theme("Echoes Music")
            except Exception as e:                             # noqa: BLE001
                print("[mods] delete:", e)
        self.toast(f"Тема «{(it or {}).get('title', '')}» удалена")
        self._fill_mods()

    def _publish_mod_dialog(self, edit=None):
        """Выложить мод; edit — свой уже выложенный мод (поля заполнены, файл темы можно не менять)."""
        from PyQt6.QtWidgets import QDialog, QCheckBox
        store = getattr(self.win, "theme_store", None)
        themes = store.list() if store is not None else []
        em = (edit or {}).get("mod") or {}
        if not themes and not edit:
            QMessageBox.information(self, "Выложить мод", "Сначала создайте тему в конструкторе тем ECHOES "
                                    "(Настройки → Темы → Конструктор), потом её можно выложить сюда.")
            return
        d = QDialog(self)
        d.setWindowTitle("Изменить мод" if edit else "Выложить мод")
        d.setMinimumWidth(560)
        d.setStyleSheet(self._dlg_qss() + "QDialog{background:#101113;}")
        v = QVBoxLayout(d)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(8)
        t = lbl("Изменить мод" if edit else "Выложить мод")
        t.setStyleSheet("font-size:22px;font-weight:900;")
        v.addWidget(t)
        v.addWidget(lbl("ТЕМА", "Section"))
        cb = QComboBox()
        if edit:
            cb.addItem("Не менять файл темы", "")
        for th in themes:
            cb.addItem(th.get("name") or th["id"], th["id"])
        v.addWidget(cb)
        v.addWidget(lbl("НАЗВАНИЕ", "Section"))
        name = QLineEdit(edit["title"] if edit else themes[0].get("name", ""))
        name.setMaxLength(80)
        cb.currentIndexChanged.connect(lambda i: cb.itemData(i) and name.setText(cb.itemText(i)))
        v.addWidget(name)
        v.addWidget(lbl("ОПИСАНИЕ", "Section"))
        desc = QPlainTextEdit()
        desc.setPlaceholderText("Что в теме особенного, под какую музыку, что поменять в настройках…")
        desc.setFixedHeight(90)
        if edit:
            desc.setPlainText(edit.get("desc", ""))
        v.addWidget(desc)
        hv = QHBoxLayout()
        ver = QLineEdit(em.get("version") or "1.0")
        ver.setMaxLength(20)
        ver.setFixedWidth(120)
        hv.addWidget(lbl("Версия", "YaSub"))
        hv.addWidget(ver)
        hv.addStretch(1)
        v.addLayout(hv)
        sel = {"icon": "", "shots": list(em.get("shots") or [])}   # старые скриншоты — описания (dict)
        v.addWidget(lbl("ИКОНКА И СКРИНШОТЫ (ДО 4)", "Section"))
        info = lbl("Иконка не выбрана · скриншотов: 0", "YaSub")
        hr = QHBoxLayout()
        bi = ghost_btn("Иконка…")
        bs = ghost_btn("Скриншоты…")
        bg = ghost_btn("Снимок плеера")
        bg.setToolTip("Сфотографировать окно ECHOES с текущей темой")

        def upd():
            ic = Path(sel['icon']).name if sel['icon'] else ("прежняя" if em.get("icon") else "нет")
            info.setText(f"Иконка: {ic} · скриншотов: {len(sel['shots'])}")

        def pick_icon():
            fn, _ = QFileDialog.getOpenFileName(d, "Иконка мода", str(Path.home()), "Картинки (*.png *.jpg *.jpeg *.webp)")
            if fn:
                sel["icon"] = fn
                upd()

        def pick_shots():
            fns, _ = QFileDialog.getOpenFileNames(d, "Скриншоты", str(Path.home()), "Картинки (*.png *.jpg *.jpeg *.webp)")
            sel["shots"] = (sel["shots"] + fns)[:4]
            upd()

        def grab():
            if len(sel["shots"]) >= 4:
                return
            out = DATA_DIR / "files" / "mod_shots"
            out.mkdir(parents=True, exist_ok=True)
            fn = out / time.strftime("echoes_%Y%m%d_%H%M%S.png")
            self.win.grab().save(str(fn), "PNG")
            sel["shots"].append(str(fn))
            upd()
        bi.clicked.connect(pick_icon)
        bs.clicked.connect(pick_shots)
        bg.clicked.connect(grab)
        hr.addWidget(bi); hr.addWidget(bs); hr.addWidget(bg)
        if edit:
            bc = ghost_btn("Убрать скриншоты")
            bc.clicked.connect(lambda: (sel.__setitem__("shots", []), upd()))
            hr.addWidget(bc)
        hr.addStretch(1)
        v.addLayout(hr)
        v.addWidget(info)
        upd()
        pubc = QCheckBox("Для всех — в общую витрину (иначе только друзьям)")
        pubc.setChecked(bool(getattr(self.node, "nostr", None)))
        pubc.setEnabled(bool(getattr(self.node, "nostr", None)))
        v.addWidget(pubc)
        if edit:
            pubc.setChecked(edit.get("src") in ("public", "both") or pubc.isChecked())
        ok = accent_btn("Сохранить изменения" if edit else "Опубликовать")
        ok.clicked.connect(d.accept)
        v.addWidget(ok)
        if not d.exec():
            return
        if not self.running():
            self.toast("Включите сеть, чтобы " + ("изменить" if edit else "выложить") + " мод")
            return
        if edit and not cb.currentData():                     # правка без нового файла темы
            self.node.call(self.node.update_mod, em.get("mid"), name.text().strip() or edit["title"],
                           desc.toPlainText().strip(), ver.text().strip(), "", sel["icon"], list(sel["shots"]),
                           pubc.isChecked(), "")
            return
        th = store.load(cb.currentData())
        out = DATA_DIR / "files" / "mod_pkgs"
        out.mkdir(parents=True, exist_ok=True)
        from net_files import safe_name
        try:
            pkg = store.export(th, str(out / (safe_name(name.text().strip() or th["name"]) + ".echoestheme")))
        except Exception as e:                                 # noqa: BLE001
            self.toast(f"Не удалось упаковать тему: {e}")
            return
        if edit:
            self.toast("Обновляю мод: новый файл темы, иконка, скриншоты…")
            self.node.call(self.node.update_mod, em.get("mid"), name.text().strip() or th["name"],
                           desc.toPlainText().strip(), ver.text().strip(), pkg, sel["icon"], list(sel["shots"]),
                           pubc.isChecked(), th.get("name", ""))
            return
        self.toast("Готовлю мод: упаковка, иконка, скриншоты…")
        self.node.call(self.node.publish_mod, pkg, name.text().strip() or th["name"], desc.toPlainText().strip(),
                       ver.text().strip(), sel["icon"], list(sel["shots"]), pubc.isChecked(), th.get("name", ""))

    def _mod_in_feed(self, p) -> QWidget:
        """Пост-мод в ленте: иконка, название, кнопка — в мастерскую."""
        from net_core import clean_mod
        m = clean_mod(p.get("mod")) or {}
        it = {"key": f"p:{m.get('mid') or p['id']}", "title": p.get("title") or "Мод", "desc": p.get("text", ""),
              "mod": m, "onion": p["author"], "npub": "", "ts": p["ts"],
              "name": self._author_name(p["author"], p.get("name", "")), "src": "friends"}
        f, v = card()
        h = QHBoxLayout(); h.setSpacing(12)
        ic = QLabel(); ic.setFixedSize(56, 56)
        ic.setPixmap(self._mod_icon_pm(it, 56))
        h.addWidget(ic)
        col = QVBoxLayout(); col.setSpacing(1)
        col.addWidget(lbl(it["title"], "NetName"))
        col.addWidget(lbl("Мод · " + __import__("net_market").TYPE_NAMES[__import__("net_market").kind_of(m)].lower()
                          .replace("echoes", "ECHOES") + (f" · v{m['version']}" if m.get("version") else ""), "YaSub"))
        h.addLayout(col, 1)
        ob = accent_btn("Открыть")
        ob.clicked.connect(lambda: self._mod_dialog(it))
        h.addWidget(ob)
        v.addLayout(h)
        return f

    def on_profile_changed(self):
        """Профиль изменили в окне «Изменить профиль»: аватар в шапке, друзьям — новая карточка, перерисовать."""
        if self.node is None:
            return
        if self.node.settings.get("name"):
            self.node.settings["name"] = str(self.win.profile.get("nickname") or self.node.settings["name"])[:40]
        self.b_me.setPixmap(self._av(self.node.me.onion, self.node._name(), 40))
        self.push_profile(force=True)
        if self.running():
            self.node.call(self.node.set_profile, self.node._name(), "", self.node.settings.get("share_now", True))
        self._refresh_tab(self._tab)
        profile = getattr(self.shell, "pages", {}).get("profile")
        if profile is not None:
            profile._sig = None
            if getattr(self.shell, "_cur_page", None) == "profile":
                profile.refresh(force=True)

    def open_profile(self, onion):
        if self.node is not None and onion == self.node.me.onion and "profile" in getattr(self.shell, "pages", {}):
            self.shell.show_page("profile")                    # свой профиль один — страница «Профиль» ECHOES
            return
        self._profile_npub = None
        self._profile_onion = onion
        self.shell.show_page("net")
        self.show_tab("profile")

    def _build_profile(self) -> QWidget:
        self.profile_page = Page(margins=(0, 0, 8, 24))
        self.profile_page.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)  # узко — вбок
        return self.profile_page

    def _fill_profile(self, body_layout=None, own=False):
        if self.node is None:
            return
        if not own and getattr(self, "_profile_npub", None) and not getattr(self, "_profile_onion", None):
            self._fill_public_profile(self._profile_npub)
            return
        from ya_profile import ProfileHeader
        from listen_stats import fmt_dur
        nd = self.node
        o = nd.me.onion if own else (getattr(self, "_profile_onion", None) or nd.me.onion)
        me = o == nd.me.onion
        page = self.profile_page
        if body_layout is None:
            page.clear()
        if me:
            prof = self.profile_card()
            prof.pop("avatar", None)
            name, avatar = nd._name(), str(self.win.profile.get("avatar") or "")
        else:
            prof = nd.contact_profile(o)
            c = nd.store.contact(o) or {}
            name, avatar = prof.get("name") or c.get("name") or o[:8], nd.avatar_path(o)
        st = prof.get("stats") or {}
        bits = []
        if st.get("tracks"):
            bits.append(f"{st['tracks']} треков в коллекции")
        if st.get("listened"):
            bits.append(f"прослушано {fmt_dur(st['listened'])}")
        if st.get("friends"):
            bits.append(f"друзей: {st['friends']}")
        if st.get("quiz_wins") or st.get("quiz_best"):
            bits.append(f"«Угадай трек»: побед {st.get('quiz_wins', 0)}, рекорд {st.get('quiz_best', 0)}")
        if not me:
            bits.insert(0, "в сети" if self._online(o) else "не в сети")
        if body_layout is None:
            hdr = ProfileHeader(page)
            role = nd.role(o)
            hdr.kicker.setText("Профиль" + ("  ·  это вы" if me else "") +
                               ({"admin": "  ·  ★ Администратор Echoes.NET", "mod": "  ·  Модератор Echoes.NET"}
                                .get(role, "")))
            if role:
                hdr.kicker.setStyleSheet(f"color:{YELLOW};")
            hdr.set_profile(name, prof.get("status", ""), avatar, "  ·  ".join(bits),
                            anim=str(self.win.profile.get("avatar_anim") or "") if me else nd.avatar_anim_path(o))
            hdr.btn.hide()
            deco = self.decorate_header(hdr, o, me)
            hl = hdr.layout()
            if me:
                b = QPushButton("Изменить профиль")
                b.setObjectName("YaChip")
                b.clicked.connect(lambda: getattr(self.win, "_edit_profile_then_refresh", lambda: None)())
                hl.addWidget(b, 0, Qt.AlignmentFlag.AlignBottom)
            else:
                hl.addWidget(self._sub_btn(o, getattr(self, "_profile_npub", None) or nd._npk_for(o) or "", name),
                             0, Qt.AlignmentFlag.AlignBottom)
                sb_ = self._profile_staff_btn(o, name)
                if sb_ is not None:
                    hl.addWidget(sb_, 0, Qt.AlignmentFlag.AlignBottom)
            if me:
                pass
            elif not nd.is_friend(o):
                st_ = (nd.store.contact(o) or {}).get("status")
                b = accent_btn("Заявка отправлена" if st_ == "pending_out" else "Добавить в друзья")
                b.setEnabled(st_ != "pending_out")
                b.clicked.connect(lambda: self._stranger_request(o, name))
                hl.addWidget(b, 0, Qt.AlignmentFlag.AlignBottom)
            else:
                for text, fn, acc in (("Написать", lambda: self.open_chat(o), True),
                                      ("Blend", lambda: self.blend(o), False)):
                    b = accent_btn(text) if acc else ghost_btn(text)
                    b.clicked.connect(fn)
                    hl.addWidget(b, 0, Qt.AlignmentFlag.AlignBottom)
                if (nd.store.contact(o) or {}).get("room") and self._online(o):
                    j = accent_btn("Слушать вместе")
                    j.clicked.connect(lambda: self.join_room(o))
                    hl.addWidget(j, 0, Qt.AlignmentFlag.AlignBottom)
            page.v.addWidget(hdr)
            body = QWidget(); body.setObjectName("YaPage")
            bv = QVBoxLayout(body)
            bv.setContentsMargins(32, 6, 24, 0)
            bv.setSpacing(6)
            page.v.addWidget(body)
            scw = self.showcase_block(o, me, deco)              # витрина-конструктор
            if scw is not None:
                bv.addSpacing(8)
                bv.addWidget(scw)
            if not me:                                         # как у себя: «Профиль» и «Время прослушивания»
                from ya_profile import SegTabs
                if self.__dict__.get("_prof_tab_of") != o:
                    self._prof_tab_of, self._prof_tab = o, "profile"
                seg = SegTabs([("profile", "Профиль", "user"), ("time", "Время прослушивания", "clock")],
                              self._prof_tab)
                seg.changed.connect(lambda k: (setattr(self, "_prof_tab", k), self._fill_profile()))
                sr = QHBoxLayout(); sr.setContentsMargins(0, 12, 0, 0)
                sr.addWidget(seg); sr.addStretch(1)
                bv.addLayout(sr)
                if self._prof_tab == "time":
                    import net_social_ui
                    net_social_ui.time_tab(self, bv, prof.get("lt"), name)
                    bv.addStretch(1)
                    return
        else:
            bv = body_layout
        import net_social_ui
        bv.addWidget(net_social_ui.stats_row(self, o, me))
        if not me and not prof:
            bv.addWidget(lbl("Профиль появится, когда друг будет в сети (нужна новая версия ECHOES).", "YaSub",
                             wrap=True))
        # сейчас слушает / совместимость / серия
        row = QHBoxLayout(); row.setSpacing(12)
        if not me:
            c = nd.store.contact(o) or {}
            now = json.loads(c["now"]) if c.get("now") and self._online(o) else None
            if c.get("game") and self._online(o):
                bv.addWidget(self._game_badge(c["game"], big=True))
            if now:
                f, v = card()
                from ya_decor import MiniEq
                hh = QHBoxLayout(); hh.setSpacing(8)
                hh.addWidget(lbl("СЕЙЧАС СЛУШАЕТ", "Section"))
                hh.addWidget(MiniEq())
                hh.addStretch(1)
                v.addLayout(hh)
                v.addWidget(TrackChip(now, self.play_meta, page=self, cover=self._local_cover(now)))
                row.addWidget(f, 2)
            pct, common = self.compat(o)
            if pct is not None:
                f, v = card()
                v.addWidget(lbl("СОВМЕСТИМОСТЬ", "Section"))
                big = lbl(f"♥ {pct}%")
                big.setStyleSheet(f"font-size:30px;font-weight:900;color:"
                                  f"{QColor.fromHsvF(0.33 * pct / 100, 0.8, 1.0).name()};")
                v.addWidget(big)
                v.addWidget(lbl("Общие: " + (", ".join(common) if common else "пока нет"), "YaSub", wrap=True))
                row.addWidget(f, 1)
            sk = self.together_streak(o)
            if sk:
                f, v = card()
                v.addWidget(lbl("СЕРИЯ", "Section"))
                big = lbl(f"Серия: {sk}")
                big.setStyleSheet("font-size:30px;font-weight:900;")
                v.addWidget(big)
                v.addWidget(lbl(_plural(sk, "день", "дня", "дней") + " подряд слушаете вместе", "YaSub"))
                row.addWidget(f, 1)
        if row.count():
            bv.addSpacing(12)
            bv.addLayout(row)
        if prof.get("about"):
            bv.addWidget(section_title("О себе"))
            bv.addWidget(lbl(prof["about"], "NetText", wrap=True, sel=True))
        fav = [x for x in (safe_track(t) for t in prof.get("fav") or []) if x]
        if fav:
            bv.addWidget(section_title("Любимые треки", lambda: self.play_many(fav, f"любимое {name}")))
            for t in fav:
                bv.addWidget(TrackChip(t, self.play_meta, page=self, cover=self._local_cover(t)))
        elif me:
            bv.addWidget(section_title("Любимые треки"))
            bv.addWidget(lbl("Добавьте любимые треки через «Изменить профиль».", "YaSub"))
        self._profile_artists(bv, o, me)
        net_social_ui.sections(self, bv, o, me)
        self._profile_follows(bv, o, me)
        tiers = [t for t in (prof.get("tier") or {}).get("tiers", []) if t.get("items")]
        if tiers:
            bv.addWidget(section_title("Тирлист"))
            mine = {} if me else self._my_tier_of()
            for tr in tiers:
                r = QHBoxLayout(); r.setSpacing(8)
                tag = lbl(tr["name"])
                tag.setFixedSize(54, 44)
                tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
                tag.setStyleSheet(f"background:{tr['color']};color:#111;border-radius:12px;font-weight:900;"
                                  "font-size:16px;")
                r.addWidget(tag, 0, Qt.AlignmentFlag.AlignTop)
                flow = QWidget(); flow.setObjectName("YaPage")
                from yamusic_theme import FlowLayout
                fl = FlowLayout(flow)
                for it in tr["items"]:
                    it = safe_track(it)
                    if not it:
                        continue
                    my = mine.get(tkey(it))
                    b = QPushButton(it["title"] + (f"   · у вас {my}" if my else ""))
                    b.setCursor(Qt.CursorShape.PointingHandCursor)
                    b.setToolTip(f"{it['artist']} — {it['title']}" + (f"\nУ вас в тирлисте: {my}" if my else ""))
                    b.setStyleSheet("QPushButton{background:rgba(255,255,255,0.06);border-radius:14px;padding:6px 12px;"
                                    f"font-weight:700;{'border:1px solid ' + YELLOW + ';' if my else ''}}}"
                                    "QPushButton:hover{background:rgba(255,255,255,0.12);}")
                    b.clicked.connect(lambda _=False, it=it: self.play_meta(it))
                    fl.addWidget(b)
                r.addWidget(flow, 1)
                bv.addLayout(r)
            if not me:
                bv.addWidget(lbl("Жёлтая рамка — трек есть и в вашем тирлисте (видно, куда его поставили вы).",
                                 "YaSub"))
        ach = [a for a in prof.get("ach") or [] if a in self.ACH]
        bv.addWidget(section_title(f"Ачивки · {len(ach)} из {len(self.ACH)}"))
        from yamusic_theme import FlowLayout
        aw = QWidget(); aw.setObjectName("YaPage")
        al = FlowLayout(aw)
        import net_ach
        for k, (title, how) in self.ACH.items():
            on = k in ach
            b = QPushButton("  " + title)                      # свой значок у каждой ачивки (ach_icons)
            b.setIcon(QIcon(__import__("ach_icons").pixmap(k, 18, YELLOW if on else "#5a5a5f")))
            b.setIconSize(QSize(18, 18))
            b.setToolTip(how + "\nНажмите — подробнее")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("QPushButton{padding:7px 14px 7px 10px;border-radius:16px;font-weight:800;border:none;" +
                            (f"background:rgba(255,219,26,0.18);color:{YELLOW};}}" if on else
                             "background:rgba(255,255,255,0.04);color:#666;}") +
                            "QPushButton:hover{background:rgba(255,255,255,0.12);}")
            b.mousePressEvent = (lambda e, k=k, on=on: net_ach.popup(self, k, on, name, me,
                                                                      e.globalPosition().toPoint()))
            al.addWidget(b)
        bv.addWidget(aw)
        posts = nd.store.posts(o, 30)
        if posts:
            bv.addWidget(section_title("Посты"))
            for p in posts:
                bv.addWidget(self._post_card(p))
                bv.addSpacing(6)
        if body_layout is None:
            bv.addStretch(1)

    def _social_refresh(self):
        """Пришли подписки/подписчики — перерисовать открытый профиль, если числа поменялись."""
        sh = self.shell
        if self._tab == "profile" and self.isVisible():
            o = getattr(self, "_profile_onion", None) or self.node.me.onion
            me = o == self.node.me.onion
            key = ("net", o)
        elif getattr(sh, "_cur_page", "") == "profile":
            o, me, key = self.node.me.onion, True, ("own", self.node.me.onion)
        else:
            return
        npub = self.node._nostr_keys()[1] if me else (getattr(self, "_profile_npub", None) or self.node._npk_for(o))
        si = self.node.social_info(o, npub)
        sig = (len(si["followers"]), si["n_following"], len(si["following"] or []))
        if self.__dict__.setdefault("_soc_sig", {}).get(key) == sig:
            return
        self._soc_sig[key] = sig
        if key[0] == "net":
            self._fill_profile()
        else:
            sh.pages["profile"].refresh(force=True)

    def _profile_follows(self, bv, o, me):
        """«Подписки»: на каких исполнителей подписан человек (свой профиль — из настроек)."""
        from yamusic_theme import Card
        if me:
            arts = list(reversed(self.win.settings.get("followed_artists") or []))
        else:
            arts = list(reversed((self.node.contact_profile(o) or {}).get("follows") or []))
        if not arts:
            return
        bv.addWidget(section_title(f"Подписки · {len(arts)}"))
        row = HRow()
        missing = []
        for a in arts[:30]:
            pic = ""
            try:
                from artist_net import cached
                pic = (cached(a) or {}).get("picture", "") or ""
            except Exception:                                  # noqa: BLE001
                pass
            c = Card(a, "Исполнитель", pic, 130, circle=True, seed=a)
            c.clicked.connect(lambda a=a: self.shell.open_artist(a))
            row.add(c)
            if not pic:
                missing.append((a, c))
        bv.addWidget(row)
        if missing:
            self._load_artist_pics(missing)

    def _profile_artists(self, bv, o, me):
        from yamusic_theme import Card
        if me:
            arts = [a for a, _v in sorted((self._stats_data().get("artists") or {}).items(),
                                         key=lambda x: -float(x[1].get("sec") or 0))][:14]
        else:
            try:
                taste = json.loads((self.node.store.contact(o) or {}).get("taste") or "null") or {}
            except ValueError:
                taste = {}
            arts = [a for a, _w in sorted((taste.get("artists") or {}).items(), key=lambda x: -x[1])][:14]
        if not arts:
            return
        bv.addWidget(section_title("Любимые исполнители"))
        row = HRow()
        missing = []
        for a in arts:
            pic = ""
            try:
                from artist_net import cached
                pic = (cached(a) or {}).get("picture", "") or ""
            except Exception:                                  # noqa: BLE001
                pass
            title = a if me else a.title()
            c = Card(title, "Исполнитель", pic, 130, circle=True, seed=a)
            c.clicked.connect(lambda a=title: self.shell.open_artist(a) if hasattr(self.shell, "open_artist") else None)
            row.add(c)
            if not pic:
                missing.append((title, c))
        bv.addWidget(row)
        if missing:
            self._load_artist_pics(missing)

    def _load_artist_pics(self, items):
        """Фото исполнителей профиля — сразу в фоне (по 4 параллельно), каждая плитка обновляется сама."""
        bus = self.__dict__.get("_pic_bus")
        if bus is None:
            bus = self._pic_bus = _PicBus(self)

            def apply(card, path):
                try:
                    card.cover = path
                    card.update()
                except RuntimeError:
                    pass                                   # профиль уже закрыли
            bus.done.connect(apply)
        import threading
        from concurrent.futures import ThreadPoolExecutor
        key = str((self.win.settings or {}).get("lastfm_key", "") or "")

        def one(it):
            name, card = it
            try:
                import artist_net
                d = artist_net.fetch_artist(name, key, images=False)
                path = d.get("picture") or artist_net.cached_image(d.get("picture_url") or d.get("wiki_img") or "")
                if path:
                    bus.done.emit(card, path)
            except Exception:                              # noqa: BLE001
                pass

        def work():
            with ThreadPoolExecutor(max_workers=4) as ex:
                list(ex.map(one, items))
        threading.Thread(target=work, name="echoes-artist-pics", daemon=True).start()

    def _fav_edit(self, v):
        """Редактор любимых треков в разделе «Сеть»."""
        s = self.node.settings
        fav = s.setdefault("fav", [])
        box = QWidget(); box.setObjectName("YaPage")
        bl = QVBoxLayout(box); bl.setContentsMargins(0, 0, 0, 0); bl.setSpacing(6)
        for i, t in enumerate(fav):
            r = QHBoxLayout()
            r.addWidget(TrackChip(t, self.play_meta, compact=True, cover=self._local_cover(t)), 1)
            x = icon_button("close", "Убрать из любимых", 32, 14, "#cfcfcf")
            x.clicked.connect(lambda _=False, i=i: (fav.pop(i), self.node.save_settings(), self.push_profile(),
                                                    self._fill_net()))
            r.addWidget(x)
            bl.addLayout(r)
        add = ghost_btn("  Добавить играющий трек в любимые")
        add.setIcon(ya_icon("plus", 14))
        add.setEnabled(self.shell.current_track() is not None and len(fav) < 8)

        def do_add():
            m = track_meta(self.shell.current_track())
            if m and all(tkey(m) != tkey(x) for x in fav):
                fav.append(m)
                self.node.save_settings()
                self.push_profile()
                self._fill_net()
        add.clicked.connect(do_add)
        bl.addWidget(add)
        v.addWidget(box)


ONLINE_GONE_MIN = 600          # «друг в сети» — только если до этого его не было ≥ 10 мин
ONLINE_ALERT_EVERY = 1800      # и не чаще раза в 30 мин на одного друга


def _capsule_locked(m) -> bool:
    """Входящая капсула времени, которая ещё не открылась: текст и трек нельзя показывать."""
    ex = m.get("extra")
    if isinstance(ex, str):
        try:
            import json
            ex = json.loads(ex) if ex else {}
        except ValueError:
            ex = {}
    ex = ex or {}
    return m.get("dir") == "in" and ex.get("kind") == "capsule" and time.time() < float(ex.get("unlock") or 0)


def _plural(n, one, few, many) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _esc(s) -> str:
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


class UpdateDialog(QDialog):
    """Окно «Обновление ECHOES»: что нового, сколько скачать, прогресс, установка."""

    def __init__(self, page):
        super().__init__(page)
        self.page = page
        nd = page.node
        self.setWindowTitle("Обновление ECHOES")
        self.setMinimumWidth(520)
        self.setStyleSheet(NET_QSS + "QDialog{background:#161616;}")
        v = QVBoxLayout(self)
        v.setContentsMargins(26, 22, 26, 20)
        v.setSpacing(10)
        h = QLabel("Обновление ECHOES")
        h.setStyleSheet("font-size:22px;font-weight:900;color:#fff;")
        v.addWidget(h)
        self.who = lbl("", "YaSub", wrap=True)
        v.addWidget(self.who)
        self.note = lbl("", "", wrap=True)
        self.note.setStyleSheet("font-size:14px;color:#e8e8e8;background:#1e1e1e;border-radius:10px;")
        self.note.setContentsMargins(12, 9, 12, 9)
        v.addWidget(self.note)
        self.info = lbl("", "YaSub", wrap=True)
        v.addWidget(self.info)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        v.addWidget(self.bar)
        self.status = lbl("", "YaSub", wrap=True)
        v.addWidget(self.status)
        r = QHBoxLayout()
        self.skip = ghost_btn("Пропустить эту версию")
        self.skip.clicked.connect(lambda: (nd.upd_skip(), self.accept()))
        r.addWidget(self.skip)
        r.addStretch(1)
        self.later = ghost_btn("Позже")
        self.later.clicked.connect(self.accept)
        r.addWidget(self.later)
        self.go = accent_btn("Скачать и установить")
        self.go.clicked.connect(self._go)
        r.addWidget(self.go)
        v.addLayout(r)
        self.refresh(nd.upd_view())

    def _go(self):
        nd = self.page.node
        u = nd.upd_view()
        if not u:
            return
        if u["state"] == "ready":
            self.page.upd_install(u["stage"])
        elif u["state"] in ("offer", "error"):
            nd.call(nd.upd_download)

    def refresh(self, u):
        if not u:
            self.who.setText("Сейчас обновлений нет. Когда друг разошлёт новую версию, здесь появится кнопка.")
            for w in (self.note, self.info, self.bar, self.status, self.skip, self.go):
                w.hide()
            return
        who = self.page._upd_who(u["pub"])
        self.who.setText(f"Версия {u.get('ver') or '—'} · от: {who}" + ("" if u["trusted"] else
                                                                         "  ·  не в доверенных"))
        self.note.setText(u.get("note") or "Без описания")
        size = u.get("size") or 0
        sz = f"{size / 2 ** 20:.1f} МБ" if size >= 2 ** 20 else f"{max(1, size // 1024)} КБ"
        self.info.setText(f"Скачать: {u.get('files', 0)} файл(ов), {sz} (до сжатия). Настройки, плейлисты и музыка "
                          "не трогаются. После установки ECHOES перезапустится сам.")
        st = u.get("state")
        busy = st in ("downloading", "checking")
        self.bar.setVisible(busy or st == "ready")
        total = int(u.get("total") or 0)
        if total:
            self.bar.setRange(0, 1000)
            self.bar.setValue(1000 if st in ("checking", "ready") else int(1000 * (u.get("done_bytes") or 0) / total))
        else:
            n = u.get("n") or 0
            self.bar.setRange(0, max(1, n))
            self.bar.setValue(n if st in ("checking", "ready") else u.get("chunks", 0))
        self.go.setEnabled(not busy and u["trusted"])
        self.go.setText({"ready": "Перезапустить и установить", "error": "Попробовать снова"}.get(st,
                                                                                               "Скачать и установить"))
        got_kb = (u.get("done_bytes") or u.get("bytes") or 0) // 1024
        tot_kb = (u.get("total") or 0) // 1024
        self.status.setText({"downloading": f"Скачиваю… {got_kb} из {tot_kb} КБ" if tot_kb else f"Скачиваю… {got_kb} КБ",
                             "checking": "Проверяю подпись каждого файла…",
                             "ready": "Скачано и проверено. Плеер закроется, заменит файлы и откроется снова.",
                             "error": "Не получилось: " + (u.get("why") or "")}.get(st, "") if u["trusted"] else
                            "Сначала разрешите обновления от этого человека в настройках Echoes.NET → «Обновления ECHOES».")
        self.status.setVisible(bool(self.status.text()))
