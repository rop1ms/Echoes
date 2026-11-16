# ph_shell.py
"""
Раскладка Echoes Music в дизайне Phantom Audio (ya_layout = "phantom"), этап 2 — каркас окна.

    ┌ ECHOES 11:47 ─────────── [◉ островок] ──────── LIVE|ТЕКСТ  🌐 ▥ ≡ ⚙   – □ × ┐
    │ ┌ обложка ───────────┐   LYRICS · Синхронизировано · ✦ 🔍 …                  │
    │ │                    │                                                       │
    │ └────────────────────┘   крупный текст (ТЕКСТ) / обложка в кольцах (LIVE)      │
    │ ┌ плеер ─────────────┐                                                       │
    │ └────────────────────┘                                                       │
    │ ┌ виджет ┐ ┌ виджет ┐                                                        │
    └───────────────────────────────────────────────────────────────────────────────┘

  * 🌐 «планета» — стеклянное окно почти во всё окно с меню Echoes сегментами (Моя волна, Для вас, Альбомы,
    Подписки, Тирлист, Дуэль, Echoes.NET, Поиск, Профиль); под ним — страница раздела;
  * ▥ Библиотека (коллекция, плейлисты), ≡ Очередь, ⚙ Настройки — стеклянной панелью справа (как в Phantom);
  * страницы Echoes живут в ОДНОМ стеке (YaShell.stack) — он стоит внутри этой панели; переключение страниц,
    история, «назад», пересборка в простое — прежние, из YaShell;
  * панель текста прежней страницы (l_panel) стоит в правой колонке «ТЕКСТ», её кнопки — значками в шапке;
  * прежние кнопки разделов и нижний плеер создаются как раньше (их состояние ведёт YaShell._tick), но
    спрятаны; новые кнопки зовут те же методы окна. Свой заголовок окна Echoes спрятан — окно двигается
    за верхнюю полосу, кнопки окна — в ней же.

Чтобы не тормозило: фон — ph_backdrop (см. там); стекло — заливка без размытия, тени — картинки из кэша;
панели открываются снимком (frozen_blur один раз + картинка панели едет и проявляется), живые виджеты
появляются, когда анимация закончилась; обновление состояния — из YaShell._tick (10 раз в секунду), и только
то, что изменилось; обложка грузится и уменьшается в фоновом потоке.
"""
from __future__ import annotations

import threading
import time

from frameclock import FrameTimer
from PyQt6.QtCore import (QEasingCurve, QEvent, QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer,
                          QVariantAnimation, pyqtSignal)
from PyQt6.QtGui import QColor, QFontMetrics, QImage, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

import ph_backdrop
import ph_style as ph
import ph_widgets as pw

# меню Echoes в панели «планеты»: ключ страницы YaShell, подпись, значок Lucide
PLANET_MENU = (("wave", "Моя волна", "waves-horizontal"), ("foryou", "Для вас", "sparkles"),
               ("albums", "Альбомы", "disc-3"), ("follows", "Подписки", "user-plus"),
               ("tierlist", "Тирлист", "chart-column"), ("duel", "Дуэль", "flag"),
               ("net", "Echoes.NET", "wifi"), ("search", "Поиск", "search"), ("profile", "Профиль", "user-round"))
PLANET_KEYS = {k for k, _t, _i in PLANET_MENU} | {"artist"}
# панели справа: ключ → (кикер, заголовок)
DRAWERS = {"collection": ("Library", "Библиотека"), "playlist": ("Playlist", "Плейлист"),
           "queue": ("Queue", "Очередь"), "settings": ("Settings", "Настройки")}
PLANET_TITLES = {"wave": "Моя волна", "foryou": "Для вас и тренды", "albums": "Альбомы", "follows": "Подписки",
                 "tierlist": "Тирлист музыки", "duel": "Дуэль треков", "net": "Echoes.NET", "search": "Поиск",
                 "profile": "Профиль", "artist": "Исполнитель"}
# кнопки прежней страницы текста → значки в шапке «ТЕКСТ»: (кнопка оболочки, значок, подсказка)
TEXT_TOOLS = (("l_ai", "sparkles", "Синхронизировать с ИИ: нейросеть послушает трек и расставит таймкоды"),
              ("l_appearance", "sliders-vertical", "Язык и оформление: перевод, шрифт, размер, стекло"),
              ("l_find", "search", "Найти текст вручную"),
              ("l_tags", "pencil", "Теги трека: исполнитель, альбом, обложка"))
WEEKDAYS = ("ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС")
MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря")


def _fmt(sec: float) -> str:
    sec = max(0, int(sec or 0))
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _title(t) -> str:
    from yamusic_theme import sanitize_title
    return sanitize_title((t or {}).get("title", "") or "Без названия")


def _artist(t) -> str:
    return (t or {}).get("artist") or "Неизвестный исполнитель"


def _elide(lbl: QLabel, text: str, width: int):
    fm = QFontMetrics(lbl.font())
    lbl.setText(fm.elidedText(text, Qt.TextElideMode.ElideRight, max(20, width)))
    lbl.setToolTip(text if fm.horizontalAdvance(text) > width else "")


# ══════════════════════════════════════════════════════════════════════════ #
#  Обложка: загрузка и уменьшение в фоновом потоке
# ══════════════════════════════════════════════════════════════════════════ #

class _CoverBus(QObject):
    done = pyqtSignal(int, QImage)


class CoverLoader(QObject):
    """load(path, side) → ready(QImage) в потоке окна; устаревшие ответы отбрасываются."""

    ready = pyqtSignal(QImage)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._token = 0
        self._bus = _CoverBus(self)
        self._bus.done.connect(self._on_done)

    def load(self, path: str, side: int):
        self._token += 1
        tok = self._token
        if not path:
            self.ready.emit(QImage())
            return

        def work():
            img = QImage()
            try:
                from img_load import read_image
                img = read_image(str(path), int(side))
            except Exception:                                  # noqa: BLE001 — нет обложки → заглушка
                img = QImage()
            self._bus.done.emit(tok, img)
        threading.Thread(target=work, name="ph-cover", daemon=True).start()

    def _on_done(self, tok: int, img: QImage):
        if tok == self._token:
            self.ready.emit(img)


# ══════════════════════════════════════════════════════════════════════════ #
#  Верхняя полоса
# ══════════════════════════════════════════════════════════════════════════ #

class PhTopBar(QWidget):
    """ECHOES · часы и дата · (островок — отдельно, по центру окна) · LIVE|ТЕКСТ · значки · кнопки окна.
    Пустое место полосы двигает окно, двойной щелчок — развернуть."""

    def __init__(self, lay: "PhantomLayout", parent=None):
        super().__init__(parent)
        self.lay = lay
        win = lay.win
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(ph.px(16))
        self.word = pw.label("ECHOES", "PhWordmark", font=ph.font(15, 700, -.01))
        h.addWidget(self.word)
        col = QVBoxLayout()
        col.setSpacing(1)
        col.addStretch(1)
        self.clock = pw.label("", "PhBody", font=ph.font(ph.TEXT_MD, 600, .01, tnum=True))
        col.addWidget(self.clock)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.date = pw.label("", "PhMuted")
        self.wday = pw.label("", "PhBadge")
        row.addWidget(self.date)
        row.addWidget(self.wday)
        row.addStretch(1)
        col.addLayout(row)
        col.addStretch(1)
        h.addLayout(col)
        self.upd = pw.text_button("Обновить", "small", "download")     # новая версия (как в заголовке окна)
        self.upd.hide()
        self.upd.clicked.connect(self._update_clicked)
        h.addWidget(self.upd)
        h.addStretch(1)
        self.mode = pw.PhSegments([("live", "LIVE"), ("text", "ТЕКСТ")], compact=True, stretch=False)
        self.mode.changed.connect(lambda k: lay.set_mode(k))
        h.addWidget(self.mode)
        icons = QHBoxLayout()
        icons.setSpacing(ph.px(6))
        self.b_planet = pw.icon_button("earth", "ghost", "top", 17, "Echoes — разделы")
        self.b_library = pw.icon_button("library", "ghost", "top", 17, "Библиотека")
        self.b_queue = pw.icon_button("list-music", "ghost", "top", 17, "Очередь")
        self.b_settings = pw.icon_button("settings", "ghost", "top", 17, "Настройки")
        self.b_planet.clicked.connect(lay.open_planet)
        self.b_library.clicked.connect(lambda: lay.toggle_page("collection"))
        self.b_queue.clicked.connect(lambda: lay.toggle_page("queue"))
        self.b_settings.clicked.connect(lambda: lay.toggle_page("settings"))
        for b in (self.b_planet, self.b_library, self.b_queue, self.b_settings):
            b.setCheckable(True)
            icons.addWidget(b)
        h.addLayout(icons)
        self.win_btns = []
        tb = getattr(win, "titlebar", None)
        if tb is not None:                                     # окно без системной рамки — кнопки окна здесь
            h.addSpacing(ph.px(8))
            wb = QHBoxLayout()
            wb.setSpacing(0)
            for name, tip, fn, size in (("minus", "Свернуть", lambda: getattr(win, "animated_minimize",
                                                                               win.showMinimized)(), 15),
                                        ("square", "Развернуть", tb.toggle_maximize, 12),
                                        ("x", "Закрыть", win.close, 15)):
                b = pw.icon_button(name, "ghost", "md", size, tip)
                b.setObjectName("PhWindowClose" if name == "x" else "PhWindow")
                b.clicked.connect(fn)
                wb.addWidget(b)
                self.win_btns.append(b)
            h.addLayout(wb)
        self._clock_timer = QTimer(self)
        self._clock_timer.setSingleShot(True)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._tick_clock()

    def _tick_clock(self):
        t = time.localtime()
        self.clock.setText(time.strftime("%H:%M", t))
        self.date.setText(f"{t.tm_mday} {MONTHS[t.tm_mon - 1]}")
        self.wday.setText(WEEKDAYS[t.tm_wday])
        self._clock_timer.start(int((60 - t.tm_sec) * 1000) + 50)    # следующий раз — ровно в начале минуты

    def sync_update(self):
        """Кнопка «Обновить» спрятанного заголовка окна (github_update / net_page зовут его set_update)."""
        tb = getattr(self.lay.win, "titlebar", None)
        src = getattr(tb, "upd_btn", None)
        on = src is not None and not src.isHidden()
        if on and self.upd.text() != src.text():
            self.upd.setText(src.text())
            self.upd.setToolTip(src.toolTip())
        if self.upd.isVisible() != on:
            self.upd.setVisible(on)

    def _update_clicked(self):
        src = getattr(getattr(self.lay.win, "titlebar", None), "upd_btn", None)
        if src is not None:
            src.click()

    def sync_checked(self, page: str | None):
        """Значки «включены», пока открыта их панель."""
        for b, keys in ((self.b_planet, PLANET_KEYS), (self.b_library, {"collection", "playlist"}),
                        (self.b_queue, {"queue"}), (self.b_settings, {"settings", "listening"})):
            on = page in keys
            if b.isChecked() != on:
                b.setChecked(on)

    # двигать окно за пустое место полосы
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and getattr(self.lay.win, "titlebar", None) is not None:
            h = self.lay.win.windowHandle()
            if h is not None:
                h.startSystemMove()
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        tb = getattr(self.lay.win, "titlebar", None)
        if e.button() == Qt.MouseButton.LeftButton and tb is not None:
            tb.toggle_maximize()
            e.accept()
            return
        super().mouseDoubleClickEvent(e)


class PhIsland(pw.PhSurface):
    """«Островок» по центру полосы: обложка (или инициалы), название, столбики звука (идут, пока играет)."""

    BARS = 4

    def __init__(self, lay: "PhantomLayout", parent=None):
        super().__init__("island", parent)
        self.lay = lay
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Сейчас играет — LIVE")
        self._thumb = QPixmap()
        self._title = ""
        self._playing = False
        self._t0 = time.perf_counter()
        self._bars = FrameTimer(self)
        self._bars.setInterval(66)                             # 15 кадров в секунду — столбики маленькие
        self._bars.timeout.connect(self._bar_tick)
        self.setFixedHeight(ph.px(36))

    def set_track(self, t, thumb: QPixmap | None):
        self._title = _title(t) if t else "ECHOES"
        side = ph.px(22)
        if thumb is not None and not thumb.isNull():
            self._thumb = ph.rounded_pixmap(thumb, QSize(side, side), 6)
        else:
            self._thumb = ph.placeholder_cover(side, self._title, _artist(t) if t else "", 6)
        fm = QFontMetrics(ph.font(12, 600))
        w = ph.px(8) + side + ph.px(10) + min(ph.px(190), fm.horizontalAdvance(self._title)) + ph.px(10) + \
            ph.px(16) + ph.px(14)
        self.setFixedWidth(max(ph.px(150), min(ph.px(360), w)))
        self.update()

    def set_playing(self, on: bool):
        if on == self._playing:
            return
        self._playing = on
        self._sync()
        self.update()

    def _sync(self):
        run = self._playing and self.isVisible() and not ph.motion_reduced()
        if run and not self._bars.isActive():
            self._bars.start()
        elif not run and self._bars.isActive():
            self._bars.stop()

    def showEvent(self, e):
        super().showEvent(e)
        self._sync()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._sync()

    def _bars_rect(self) -> QRect:
        s = ph.px(14)
        return QRect(self.width() - ph.px(12) - s, (self.height() - s) // 2, s, s)

    def _bar_tick(self):
        self.update(self._bars_rect())

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.lay.set_mode("live")
            self.lay.close_overlay()
        elif e.button() == Qt.MouseButton.RightButton:
            self.lay.shell._p_cover_press(e)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = ph.px(22)
        y = (self.height() - side) / 2
        p.drawPixmap(QPointF(ph.px(8), y), self._thumb)
        x = ph.px(8) + side + ph.px(10)
        br = self._bars_rect()
        p.setFont(ph.font(12, 600))
        p.setPen(ph.qcolor(ph.TEXT_PRIMARY))
        fm = p.fontMetrics()
        p.drawText(QRectF(x, 0, br.left() - x - ph.px(8), self.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   fm.elidedText(self._title, Qt.TextElideMode.ElideRight, int(br.left() - x - ph.px(8))))
        # столбики: 4 полоски, на паузе — низкие и тусклые
        t = time.perf_counter() - self._t0
        import math
        bw = br.width() / (self.BARS * 2 - 1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ph.white(.86 if self._playing else .42))
        for i in range(self.BARS):
            if self._playing and self._bars.isActive():
                k = .35 + .65 * abs(math.sin(t * (2.1 + i * .7) + i * 1.3))
            else:
                k = (.35, .6, .45, .3)[i % 4]
            hh = br.height() * k
            p.drawRoundedRect(QRectF(br.left() + i * 2 * bw, br.bottom() - hh, bw, hh), bw / 2, bw / 2)
        p.end()


# ══════════════════════════════════════════════════════════════════════════ #
#  Левая колонка
# ══════════════════════════════════════════════════════════════════════════ #

class PhCoverCard(QWidget):
    """Большая обложка со скруглением и тонкой рамкой; ⤢ — режим обложки Echoes; клик — LIVE."""

    def __init__(self, lay: "PhantomLayout", parent=None):
        super().__init__(parent)
        self.lay = lay
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._img = QImage()
        self._title = self._artist = ""
        self._pm = QPixmap()
        self._old = QPixmap()
        self._fade = 1.0
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(ph.ease_out())
        self._anim.valueChanged.connect(self._on_fade)
        self.expand = pw.icon_button("maximize-2", "surface", "sm", 13, "Режим обложки", parent=self)
        self.expand.clicked.connect(lambda: getattr(lay.win, "_toggle_cover_mode", lambda: None)())

    def radius(self) -> float:
        return float(ph.px(22))

    def set_image(self, img: QImage, title: str, artist: str):
        self._old = self._pm
        self._img, self._title, self._artist = img, title, artist
        self._pm = QPixmap()
        d = ph.duration(ph.DUR_SLOW)
        if d and not self._old.isNull():
            self._anim.stop()
            self._anim.setDuration(d)
            self._fade = 0.0
            self._anim.start()
        else:
            self._fade = 1.0
            self._old = QPixmap()
        self.update()

    def _on_fade(self, v):
        self._fade = float(v)
        if self._fade >= 1.0:
            self._old = QPixmap()
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._pm = QPixmap()
        self._old = QPixmap()
        m = ph.px(14)
        self.expand.move(self.width() - self.expand.width() - m, m)

    def _pixmap(self) -> QPixmap:
        if self._pm.isNull() and self.width() > 4:
            dpr = self.devicePixelRatioF() or 1.0
            if self._img.isNull():
                self._pm = ph.placeholder_cover(self.size(), self._title, self._artist, self.radius(), dpr)
            else:
                self._pm = ph.rounded_pixmap(self._img, self.size(), self.radius(), dpr)
        return self._pm

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.lay.set_mode("live")
        elif e.button() == Qt.MouseButton.RightButton:
            self.lay.shell._p_cover_press(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pm = self._pixmap()
        if not self._old.isNull() and self._fade < 1.0:
            p.drawPixmap(0, 0, self._old)
            p.setOpacity(self._fade)
        p.drawPixmap(0, 0, pm)
        p.setOpacity(1.0)
        p.setPen(QPen(ph.qcolor(ph.LINE_1), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        r = self.radius()
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), r, r)
        p.end()


class PhVolumePopup(QWidget):
    """Всплывающая громкость под кнопкой: ползунок Phantom и проценты; колесо — ±5."""

    def __init__(self, lay: "PhantomLayout"):
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.NoDropShadowWindowHint)
        self.lay = lay
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFont(ph.font(ph.TEXT_SM))
        h = QHBoxLayout(self)
        h.setContentsMargins(ph.px(14), ph.px(10), ph.px(14), ph.px(10))
        h.setSpacing(ph.px(10))
        self.mute = pw.icon_button("volume-2", "ghost", "sm", 14, "Выключить звук")
        self.mute.clicked.connect(self._mute)
        h.addWidget(self.mute)
        self.seek = pw.PhSeek(always_thumb=True)
        self.seek.setFixedWidth(ph.px(150))
        self.seek.moved.connect(self._set)
        self.seek.released.connect(self._set)
        h.addWidget(self.seek)
        self.val = pw.label("", "PhSub", font=ph.font(ph.TEXT_XS, 600, tnum=True))
        self.val.setFixedWidth(ph.px(34))
        h.addWidget(self.val)
        self.resize(ph.px(250), ph.px(46))

    def sync(self):
        v = self.lay.win.vol.value()
        self.seek.set_value(v / 100.0)
        self.val.setText(f"{v}%")
        self.mute.setIcon(ph.icon("volume-x" if v == 0 else "volume-1" if v < 50 else "volume-2", 14))

    def _set(self, f: float):
        self.lay.win.vol.setValue(int(round(f * 100)))
        self.sync()

    def _mute(self):
        self.lay.shell._toggle_mute()
        self.sync()

    def wheelEvent(self, e):
        d = 5 if e.angleDelta().y() > 0 else -5
        w = self.lay.win
        w.vol.setValue(max(0, min(100, w.vol.value() + d)))
        self.sync()

    def paintEvent(self, e):
        p = QPainter(self)
        ph.paint_surface(p, QRectF(self.rect()), "menu")
        p.end()


class PhPlayerCard(pw.PhSurface):
    """Карточка плеера: название, исполнитель, ♥, громкость, «⋯»; shuffle ⏮ ▶ ⏭ repeat; полоса и время."""

    def __init__(self, lay: "PhantomLayout", parent=None):
        super().__init__("panel", parent)
        self.lay = lay
        sh, win = lay.shell, lay.win
        v = QVBoxLayout(self)
        v.setContentsMargins(ph.px(20), ph.px(18), ph.px(20), ph.px(14))
        v.setSpacing(0)
        top = QHBoxLayout()
        top.setSpacing(ph.px(4))
        tc = QVBoxLayout()
        tc.setSpacing(ph.px(1))
        self.title = pw.label("—", "PhTitle", font=ph.font(22, 650, -.025))
        self.artist = pw.label("", "PhSub", font=ph.font(ph.TEXT_SM, 550))
        self.artist.setCursor(Qt.CursorShape.PointingHandCursor)
        self.artist.mousePressEvent = lambda e: sh._open_current_artist()
        tc.addWidget(self.title)
        tc.addWidget(self.artist)
        top.addLayout(tc, 1)
        self.b_like = pw.icon_button("heart", "ghost", "sm", 15, "Мне нравится")
        self.b_like.clicked.connect(lambda: sh.current_track() and sh.toggle_like(sh.current_track()))
        self.b_vol = pw.icon_button("volume-1", "ghost", "sm", 15, "Громкость (колесо — тише/громче)")
        self.b_vol.clicked.connect(self._volume)
        self.b_vol.wheelEvent = self._vol_wheel
        self.b_more = pw.icon_button("ellipsis", "ghost", "sm", 15,
                                     "Ещё: клип, сцена, реакция, звук, тема, настройки")
        self.b_more.clicked.connect(sh.toggle_player_more)
        for b in (self.b_like, self.b_vol, self.b_more):
            top.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(top)
        v.addStretch(1)
        ctr = QHBoxLayout()
        ctr.setSpacing(ph.px(10))
        ctr.addStretch(1)
        self.b_shuffle = pw.icon_button("shuffle", "surface", "sm", 14, "Перемешать", checkable=True)
        self.b_shuffle.clicked.connect(lambda: win.btn_shuffle.click())
        self.b_prev = pw.icon_button("skip-back", "surface", "sm", 14, "Предыдущий")
        self.b_prev.clicked.connect(win.prev_track)
        self.b_play = pw.icon_button("play", "solid", "play", 18, "Играть / пауза")
        self.b_play.clicked.connect(win.toggle_play)
        self.b_next = pw.icon_button("skip-forward", "surface", "sm", 14, "Следующий")
        self.b_next.clicked.connect(win.next_track)
        self.b_repeat = pw.icon_button("repeat", "surface", "sm", 14, "Повтор", checkable=True)
        self.b_repeat.clicked.connect(win._cycle_repeat)
        for b in (self.b_shuffle, self.b_prev, self.b_play, self.b_next, self.b_repeat):
            ctr.addWidget(b)
        ctr.addStretch(1)
        v.addLayout(ctr)
        v.addStretch(1)
        self.seek = pw.PhSeek()
        self.seek.released.connect(sh._seek_frac)
        self.seek.moved.connect(self._seek_preview)
        v.addWidget(self.seek)
        times = QHBoxLayout()
        self.t_pos = pw.label("0:00", "PhBody", font=ph.font(ph.TEXT_XS, 600, tnum=True))
        self.t_dur = pw.label("0:00", "PhBody", font=ph.font(ph.TEXT_XS, 600, tnum=True))
        times.addWidget(self.t_pos)
        times.addStretch(1)
        times.addWidget(self.t_dur)
        v.addLayout(times)
        self._state = {}
        self._pop: PhVolumePopup | None = None

    def set_track(self, t):
        _elide(self.title, _title(t) if t else "—", self.width() - ph.px(150))
        _elide(self.artist, _artist(t) if t else "", self.width() - ph.px(150))
        self._state.pop("like", None)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        t = self.lay.shell.current_track()
        self.set_track(t)

    def _seek_preview(self, f):
        d = self._state.get("dur", 0.0)
        self.t_pos.setText(_fmt(f * d))

    def _volume(self):
        if self._pop is None:
            self._pop = PhVolumePopup(self.lay)
        self._pop.sync()
        g = self.b_vol.mapToGlobal(QPoint(self.b_vol.width() // 2, self.b_vol.height() + ph.px(6)))
        self._pop.move(g.x() - self._pop.width() + ph.px(40), g.y())
        self._pop.show()

    def _vol_wheel(self, e):
        w = self.lay.win
        w.vol.setValue(max(0, min(100, w.vol.value() + (5 if e.angleDelta().y() > 0 else -5))))
        e.accept()

    def tick(self, playing: bool, pos: float, dur: float):
        """Из YaShell._tick: меняется только то, что изменилось."""
        sh, w, st = self.lay.shell, self.lay.win, self._state
        if st.get("play") != playing:
            st["play"] = playing
            self.b_play.setIcon(ph.icon("pause" if playing else "play", 18, (5, 5, 5, 1.0), (5, 5, 5, 1.0)))
        st["dur"] = dur
        self.seek.set_value(pos / dur if dur > 0 else 0.0)
        sec = (int(pos), int(dur))
        if st.get("sec") != sec and not self.seek._drag:
            st["sec"] = sec
            self.t_pos.setText(_fmt(pos))
            self.t_dur.setText(_fmt(dur))
        shuf = bool(w.shuffle)
        if st.get("shuf") != shuf:
            st["shuf"] = shuf
            self.b_shuffle.setChecked(shuf)
        rm = int(getattr(w, "repeat_mode", 0))
        if st.get("rm") != rm:
            st["rm"] = rm
            self.b_repeat.setChecked(rm != 0)
            self.b_repeat.setIcon(ph.icon("repeat-1" if rm == 2 else "repeat", 14, ph.TEXT_SECONDARY,
                                          ph.TEXT_PRIMARY))
        t = sh.current_track()
        liked = bool(t and sh.is_liked(t))
        if st.get("like") != liked:
            st["like"] = liked
            self.b_like.setIcon(_heart_icon(15) if liked else ph.icon("heart", 15))
        vol = w.vol.value()
        vk = 0 if vol == 0 else 1 if vol < 50 else 2
        if st.get("vol") != vk:
            st["vol"] = vk
            self.b_vol.setIcon(ph.icon(("volume-x", "volume-1", "volume-2")[vk], 15))


def _heart_icon(size: int):
    """Залитое сердце — трек в «Мне нравится»."""
    from PyQt6.QtGui import QIcon
    return QIcon(ph.icon_pixmap("heart", size, ph.TEXT_PRIMARY, 1.75, fill=ph.TEXT_PRIMARY))


class PhWidgetCard(pw.PhSurface):
    """Карточка-виджет слева (как у Phantom): кикер, подпись, ‹ ›, точки. Виды этапа 2: часы, визуализатор
    (покой — линия), о треке, далее в очереди; остальные виды Phantom и наши — этап 6."""

    KINDS = (("visualizer", "Audio visualizer", "Живой спектр аудиосигнала"),
             ("clock", "Clock", "Минималистичные часы"),
             ("info", "Music information", "Формат и файл трека"),
             ("queue", "Queue", "Далее в очереди"))

    def __init__(self, lay: "PhantomLayout", kind: str, parent=None):
        super().__init__("card", parent)
        self.lay = lay
        keys = [k for k, _a, _b in self.KINDS]
        self.idx = keys.index(kind) if kind in keys else 0
        v = QVBoxLayout(self)
        v.setContentsMargins(ph.px(16), ph.px(14), ph.px(12), ph.px(12))
        v.setSpacing(0)
        hr = QHBoxLayout()
        hc = QVBoxLayout()
        hc.setSpacing(ph.px(2))
        self.kick = pw.kicker("")
        self.sub = pw.label("", "PhMuted", font=ph.font(ph.TEXT_2XS, 500))
        hc.addWidget(self.kick)
        hc.addWidget(self.sub)
        hr.addLayout(hc, 1)
        bl = pw.icon_button("chevron-left", "ghost", "sm", 13, "Предыдущий виджет")
        br = pw.icon_button("chevron-right", "ghost", "sm", 13, "Следующий виджет")
        bl.clicked.connect(lambda: self.step(-1))
        br.clicked.connect(lambda: self.step(1))
        hr.addWidget(bl, 0, Qt.AlignmentFlag.AlignTop)
        hr.addWidget(br, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(hr)
        self.body = _WidgetBody(self)
        v.addWidget(self.body, 1)
        self.dots = pw.PhDots(len(self.KINDS), self.idx)
        v.addWidget(self.dots, 0, Qt.AlignmentFlag.AlignHCenter)
        self._apply()

    def widget_kind(self) -> str:
        return self.KINDS[self.idx][0]

    def step(self, d: int):
        self.idx = (self.idx + d) % len(self.KINDS)
        self._apply()
        self.lay.save_widgets()

    def _apply(self):
        _k, kick, sub = self.KINDS[self.idx]
        self.kick.setText(kick.upper())
        self.sub.setText(sub)
        self.dots.set_current(self.idx)
        self.body.update()

    def tick(self):
        if self.widget_kind() in ("clock", "queue", "info"):
            self.body.tick()


class _WidgetBody(QWidget):
    def __init__(self, card: PhWidgetCard):
        super().__init__(card)
        self.card = card
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._sig = None

    def tick(self):
        sig = self._signature()
        if sig != self._sig:
            self._sig = sig
            self.update()

    def _signature(self):
        k = self.card.widget_kind()
        if k == "clock":
            return ("clock", time.strftime("%H:%M"))
        lay = self.card.lay
        if k == "queue":
            return ("queue", tuple(str(t.get("path", "")) for t in lay.upcoming(3)))
        t = lay.shell.current_track()
        return ("info", str((t or {}).get("path", "")))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        k = self.card.widget_kind()
        r = QRectF(self.rect())
        lay = self.card.lay
        if k == "visualizer":
            y = r.bottom() - ph.px(14)
            ph.paint_hairline(p, r.left(), r.right() - ph.px(4), y, ph.LINE_2)
        elif k == "clock":
            tm = time.localtime()
            cx, cy = r.left() + ph.px(28), r.center().y() + ph.px(2)
            rad = ph.px(24)
            p.setPen(QPen(ph.white(.12), 1.5))
            p.drawEllipse(QPointF(cx, cy), rad, rad)
            frac = (tm.tm_hour % 12 * 60 + tm.tm_min) / 720.0
            p.setPen(QPen(ph.white(.86), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(QRectF(cx - rad, cy - rad, 2 * rad, 2 * rad), 90 * 16, int(-frac * 360 * 16))
            x = cx + rad + ph.px(16)
            p.setFont(ph.font(17, 650, -.01, tnum=True))
            p.setPen(ph.qcolor(ph.TEXT_PRIMARY))
            p.drawText(QPointF(x, cy + ph.px(1)), time.strftime("%H:%M", tm))
            p.setFont(ph.font(ph.TEXT_2XS, 500))
            p.setPen(ph.qcolor(ph.TEXT_TERTIARY))
            p.drawText(QPointF(x, cy + ph.px(17)),
                       f"{WEEKDAYS[tm.tm_wday]} · {tm.tm_mday} {MONTHS[tm.tm_mon - 1]} {tm.tm_year}")
        elif k == "info":
            t = lay.shell.current_track() or {}
            path = str(t.get("path", ""))
            ext = path.rsplit(".", 1)[-1].upper() if "." in path[-6:] else ("ONLINE" if path else "—")
            rows = (("Формат", ext), ("Исполнитель", _artist(t) if t else "—"),
                    ("Альбом", t.get("album") or "—"))
            self._rows(p, r, rows)
        elif k == "queue":
            nx = lay.upcoming(3)
            rows = [(f"{i + 1:02d}", f"{_title(t)} — {_artist(t)}") for i, t in enumerate(nx)] or [("", "Очередь пуста")]
            self._rows(p, r, rows)
        p.end()

    @staticmethod
    def _rows(p: QPainter, r: QRectF, rows):
        y = r.top() + ph.px(16)
        step = ph.px(22)
        for a, b in rows:
            p.setFont(ph.font(ph.TEXT_2XS, 600, .08))
            p.setPen(ph.qcolor(ph.TEXT_TERTIARY))
            p.drawText(QPointF(r.left(), y + ph.px(12)), a.upper() if not a[:1].isdigit() else a)
            p.setFont(ph.font(ph.TEXT_XS, 550))
            p.setPen(ph.qcolor(ph.TEXT_PRIMARY))
            x = r.left() + ph.px(78 if not a[:1].isdigit() else 24)
            p.drawText(QRectF(x, y, r.right() - x - ph.px(4), step), Qt.AlignmentFlag.AlignVCenter,
                       p.fontMetrics().elidedText(b, Qt.TextElideMode.ElideRight, int(r.right() - x - ph.px(4))))
            y += step


# ══════════════════════════════════════════════════════════════════════════ #
#  Правая колонка: ТЕКСТ (панель текста Echoes) и LIVE (обложка в кольцах)
# ══════════════════════════════════════════════════════════════════════════ #

class PhLive(QWidget):
    """LIVE: обложка в концентрических кольцах, название крупно, исполнитель, альбом, «Далее»."""

    def __init__(self, lay: "PhantomLayout", parent=None):
        super().__init__(parent)
        self.lay = lay
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._img = QImage()
        self._t = None
        self._next = None
        self._cache: QPixmap | None = None

    def set_track(self, t, img: QImage):
        self._t, self._img = t, img
        self._cache = None
        self.update()

    def set_next(self, t):
        if (t or {}).get("path") != (self._next or {}).get("path"):
            self._next = t
            self._cache = None
            self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._cache = None

    def paintEvent(self, e):
        if self._cache is None or self._cache.size() != self.size() * self.devicePixelRatioF():
            self._cache = self._render()
        p = QPainter(self)
        p.drawPixmap(0, 0, self._cache)
        p.end()

    def _render(self) -> QPixmap:
        dpr = self.devicePixelRatioF() or 1.0
        pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        side = max(ph.px(120), min(ph.px(232), int(min(w, h) * .3)))
        cx, cy = w / 2, h * .40
        # кольца
        for i, k in enumerate((1.25, 1.55, 1.85)):
            p.setPen(QPen(ph.white(.09 - i * .02), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), side * k / 2 + ph.px(36), side * k / 2 + ph.px(36))
        r = QRectF(cx - side / 2, cy - side / 2, side, side)
        ph.paint_shadow(p, r, "card", ph.px(18))
        t = self._t or {}
        if self._img.isNull():
            p.drawPixmap(r.topLeft(), ph.placeholder_cover(QSize(side, side), _title(t), _artist(t), ph.px(18), dpr))
        else:
            p.drawPixmap(r.topLeft(), ph.rounded_pixmap(self._img, QSize(side, side), ph.px(18), dpr))
        p.setPen(QPen(ph.qcolor(ph.LINE_1), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), ph.px(18), ph.px(18))
        y = r.bottom() + ph.px(64)
        maxw = int(w * .8)

        def line(text, f, color, dy):
            nonlocal y
            p.setFont(f)
            p.setPen(ph.qcolor(color))
            fm = p.fontMetrics()
            s = fm.elidedText(text, Qt.TextElideMode.ElideRight, maxw)
            p.drawText(QPointF(cx - fm.horizontalAdvance(s) / 2, y + fm.ascent()), s)
            y += fm.height() + dy
        if self._t:
            line(_title(t), ph.display_font(36), ph.TEXT_PRIMARY, ph.px(2))
            line(_artist(t), ph.font(ph.TEXT_LG, 600), ph.TEXT_SECONDARY, ph.px(4))
            if t.get("album"):
                line(t["album"], ph.font(ph.TEXT_XS, 500), ph.TEXT_TERTIARY, 0)
            if self._next:
                y += ph.px(10)
                ph.paint_hairline(p, cx - ph.px(90), cx + ph.px(90), y, ph.LINE_2)
                y += ph.px(10)
                line("Далее", ph.font(ph.TEXT_2XS, 500), ph.TEXT_TERTIARY, ph.px(2))
                line(_title(self._next), ph.font(ph.TEXT_MD, 600), ph.TEXT_PRIMARY, 0)
                line(_artist(self._next), ph.font(ph.TEXT_2XS, 500), ph.TEXT_TERTIARY, 0)
        else:
            line("Ничего не играет", ph.title_font(20), ph.TEXT_SECONDARY, 0)
        p.end()
        return pm


class PhRightColumn(QWidget):
    """Шапка (кикер + значки) и содержимое: панель текста Echoes или LIVE."""

    def __init__(self, lay: "PhantomLayout", parent=None):
        super().__init__(parent)
        self.lay = lay
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.head = QWidget(self)
        hl = QHBoxLayout(self.head)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(ph.px(10))
        self.kick = pw.kicker("Lyrics")
        hl.addWidget(self.kick)
        self.status = pw.text_button("", "small")
        self.status.setCursor(Qt.CursorShape.ArrowCursor)       # просто подпись в виде пилюли, как у Phantom
        self.status.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        hl.addWidget(self.status)
        hl.addStretch(1)
        self.tools = {}
        for attr, icon, tip in TEXT_TOOLS:
            b = pw.icon_button(icon, "surface", "sm", 13, tip)
            b.clicked.connect(lambda _=False, a=attr: self._tool(a))
            b.hide()
            hl.addWidget(b)
            self.tools[attr] = b
        self.live = PhLive(lay, self)
        self.live.hide()
        self.panel = None                                      # панель текста Echoes (забирается при первом показе)
        self.mode = "text"

    def adopt_panel(self):
        sh = self.lay.shell
        if self.panel is not None:
            return self.panel
        panel = getattr(sh, "l_panel", None)
        if panel is None:
            return None
        top = getattr(sh, "l_top", None)
        if top is not None:
            top.hide()                                         # её кнопки — значками в шапке
        col = getattr(sh, "l_collapse", None)
        if col is not None:
            col.hide()
        panel.setParent(self)
        panel.set_backdrop(None)                               # прозрачная: под ней живой фон Phantom
        self.panel = panel
        self._place()
        return panel

    def _tool(self, attr: str):
        b = getattr(self.lay.shell, attr, None)
        if b is not None:
            b.click()

    def set_mode(self, mode: str):
        self.mode = mode
        text = mode == "text"
        self.kick.setText("LYRICS" if text else "NOW PLAYING")
        if text:
            self.adopt_panel()
        if self.panel is not None:
            self.panel.setVisible(text)
        self.live.setVisible(not text)
        self.status.setVisible(text)
        self.sync_tools()
        self._place()

    def sync_tools(self):
        """Значки — только у кнопок, которые прежняя страница сейчас показала бы (ИИ и теги — не всегда)."""
        text = self.mode == "text"
        sh = self.lay.shell
        for attr, b in self.tools.items():
            src = getattr(sh, attr, None)
            on = text and src is not None and not src.isHidden()
            if b.isVisible() != on:
                b.setVisible(on)
        if text:
            lv = getattr(self.lay.win, "lyrics_view", None)
            lines = getattr(lv, "_lines", None) if lv is not None else None
            timed = bool(getattr(lv, "_has_timings", False)) if lv is not None else False
            st = ("Синхронизировано" if timed else "Без таймингов") if lines else "Текст не найден"
            if self.status.text().strip() != st:
                self.status.setText("  " + st)
                self.status.setIcon(ph.icon("circle-check" if timed and lines else "info", 12,
                                            ph.TEXT_PRIMARY if timed and lines else ph.TEXT_TERTIARY))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place()

    def _place(self):
        hh = ph.px(32)
        self.head.setGeometry(0, 0, self.width(), hh)
        body = QRect(0, hh + ph.px(8), self.width(), max(10, self.height() - hh - ph.px(8)))
        self.live.setGeometry(body)
        if self.panel is not None:
            self.panel.setGeometry(body)


# ══════════════════════════════════════════════════════════════════════════ #
#  Панель поверх: «планета» (почти во всё окно) и выезжающая справа
# ══════════════════════════════════════════════════════════════════════════ #

class PhOverlay(QWidget):
    """Слой поверх раскладки: размытый снимок под панелью (скрим) + стеклянная панель со страницей Echoes.
    Открытие и закрытие — снимком панели (едет и проявляется), живая панель — только в покое."""

    closed = pyqtSignal()

    def __init__(self, lay: "PhantomLayout", parent=None):
        super().__init__(parent)
        self.lay = lay
        self.kind = None                                       # "planet" | "drawer"
        self._scrim = QPixmap()
        self._snap = QPixmap()
        self._t = 0.0                                          # 0 — закрыта, 1 — открыта
        self._dir = 1
        self._anim = QVariantAnimation(self)
        self._anim.valueChanged.connect(self._on_anim)
        self._anim.finished.connect(self._on_anim_done)
        self._rescrim = QTimer(self)
        self._rescrim.setSingleShot(True)
        self._rescrim.setInterval(220)
        self._rescrim.timeout.connect(self._redo_scrim)
        self.panel = pw.PhSurface("panel", self)
        self.panel.setFont(ph.font(ph.TEXT_BASE))
        pv = QVBoxLayout(self.panel)
        pv.setContentsMargins(ph.px(28), ph.px(26), ph.px(28), ph.px(16))
        pv.setSpacing(ph.px(14))
        head = QHBoxLayout()
        head.setSpacing(ph.px(8))
        tcol = QVBoxLayout()
        tcol.setSpacing(ph.px(2))
        self.kick = pw.kicker("Echoes")
        self.title = pw.label("", "PhDisplay", font=ph.font(30, 650, -.03))
        self.subline = pw.label("", "PhMuted", font=ph.font(ph.TEXT_2XS, 600, ph.TRACKING_WIDE))
        tcol.addWidget(self.kick)
        tcol.addWidget(self.title)
        tcol.addWidget(self.subline)
        self.back = pw.icon_button("chevron-left", "surface", "md", 16, "Назад")
        self.back.clicked.connect(lambda: lay.shell.go_back())
        head.addWidget(self.back, 0, Qt.AlignmentFlag.AlignTop)
        head.addLayout(tcol, 1)
        self.b_profile = pw.text_button("", "secondary")
        self.b_profile.clicked.connect(lambda: lay.shell.show_page("profile"))
        head.addWidget(self.b_profile, 0, Qt.AlignmentFlag.AlignTop)
        self.b_close = pw.icon_button("x", "ghost", "md", 16, "Закрыть (Esc)")
        self.b_close.clicked.connect(lambda: lay.close_overlay())
        head.addWidget(self.b_close, 0, Qt.AlignmentFlag.AlignTop)
        pv.addLayout(head)
        self.menu = pw.PhSegments([(k, t, i) for k, t, i in PLANET_MENU])
        self.menu.changed.connect(lambda k: lay.shell.show_page(k))
        pv.addWidget(self.menu)
        pv.addWidget(pw.PhHairline())
        self.body = QWidget()
        self.body.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._body_lay = QVBoxLayout(self.body)
        self._body_lay.setContentsMargins(0, 0, 0, 0)
        pv.addWidget(self.body, 1)
        self.hide()
        self._esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._esc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._esc.activated.connect(lambda: lay.close_overlay())

    def set_content(self, w: QWidget):
        if w.parentWidget() is not self.body:
            self._body_lay.addWidget(w)

    def is_open(self) -> bool:
        return self.isVisible() and self._dir > 0

    def panel_rect(self, kind: str | None = None) -> QRect:
        kind = kind or self.kind or "planet"
        W, H = self.width(), self.height()
        if kind == "planet":
            m = ph.px(20)
            return QRect(m, m, W - 2 * m, H - 2 * m)
        m = ph.px(12)
        w = min(max(ph.px(560), int(W * .44)), W - 2 * m)
        return QRect(W - w - m, m, w, H - 2 * m)

    def configure(self, kind: str, kick: str, title: str, subline: str = "", menu_key: str | None = None,
                  back: bool = False):
        changed = kind != self.kind
        self.kind = kind
        self.kick.setText(kick.upper())
        ph.set_font(self.title, ph.font(30 if kind == "planet" else 22, 650, -.03))
        self.title.setText(title)
        self.subline.setText(subline.upper())
        self.subline.setVisible(bool(subline))
        planet = kind == "planet"
        self.menu.setVisible(planet)
        self.b_profile.setVisible(planet)
        self.back.setVisible(back)
        if planet:
            sh = self.lay.shell
            self.b_profile.setText("  " + (sh.nick.text() or "Профиль"))
            av = sh.avatar.pixmap()
            if av is not None and not av.isNull():
                from PyQt6.QtGui import QIcon
                self.b_profile.setIcon(QIcon(av))
                self.b_profile.setIconSize(QSize(ph.px(20), ph.px(20)))
            if menu_key is not None and menu_key in self.menu.buttons:
                self.menu.set_current(menu_key)
            elif self.menu.group.checkedButton() is not None:
                self.menu.group.setExclusive(False)
                self.menu.group.checkedButton().setChecked(False)
                self.menu.group.setExclusive(True)
        if changed or not self.isVisible():
            self.panel.setGeometry(self.panel_rect())

    # ── открыть / закрыть ── #
    def open(self):
        lay = self.lay
        self.setGeometry(lay.shell.rect())
        self.panel.setGeometry(self.panel_rect())
        if self.isVisible() and self._dir > 0:
            self.raise_()
            return
        lay.set_under_visible(True)
        self._scrim = self._make_scrim()
        self._dir = 1
        self.show()
        self.raise_()
        self._start(ph.duration(ph.DUR_BASE + 40))

    def close(self, instant: bool = False):
        if not self.isVisible():
            return
        self._dir = -1
        self.lay.set_under_visible(True)                      # под гаснущим снимком — снова живая раскладка
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        d = 0 if instant else ph.duration(ph.DUR_BASE)
        self._start(d)

    def _make_scrim(self) -> QPixmap:
        """Размытый снимок фона и раскладки (без самой панели)."""
        lay = self.lay
        if lay.root.width() < 8:
            return QPixmap()
        return ph_backdrop.frozen_blur(lay.root, blur=6.0, dim=.55, layers=[lay.bg, lay.host])

    def _settle_under(self):
        """Панель открыта целиком: под ней всё прячется — снимок закрывает окно, а живые фон, текст, островок
        иначе заставляли бы перерисовывать панель со страницей на каждом своём кадре."""
        if self.isVisible() and self._dir > 0 and not self._scrim.isNull():
            self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
            self.lay.set_under_visible(False)

    def _start(self, ms: int):
        self._anim.stop()
        lay = self.panel.layout()
        if lay is not None:
            lay.activate()
        self._snap = self.panel.grab() if ms else QPixmap()
        if ms <= 0:
            self._t = 1.0 if self._dir > 0 else 0.0
            self._on_anim_done()
            return
        self.panel.hide()
        self._anim.setDuration(ms)
        self._anim.setEasingCurve(ph.ease_out() if self._dir > 0 else QEasingCurve(QEasingCurve.Type.InCubic))
        self._anim.setStartValue(self._t)
        self._anim.setEndValue(1.0 if self._dir > 0 else 0.0)
        self._anim.start()

    def _on_anim(self, v):
        self._t = float(v)
        self.update()

    def _on_anim_done(self):
        self._snap = QPixmap()
        if self._dir > 0:
            self._t = 1.0
            self.panel.show()
            self.panel.setFocus()
            self._settle_under()
            self.update()
        else:
            self._t = 0.0
            self.hide()
            self._scrim = QPixmap()
            self.closed.emit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.panel.setGeometry(self.panel_rect())
        if not self.isVisible():
            return
        if not self._scrim.isNull() and self._scrim.size() != self.size() * self._scrim.devicePixelRatio():
            self._scrim = QPixmap()                            # снимок старого размера не годится:
            self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
            self.lay.set_under_visible(True)                   # пока тянут — живая раскладка под тёмной вуалью,
        if self._scrim.isNull() and self._dir > 0:
            self._rescrim.start()                              # а новый снимок — когда перестанут тянуть
                                                               # (каждый шаг перезапускает ожидание)

    def _redo_scrim(self):
        if self.isVisible() and self._dir > 0:
            self._scrim = self._make_scrim()
            self._settle_under()
            self.update()

    def mousePressEvent(self, e):
        if not self.panel.geometry().contains(e.position().toPoint()):
            self.lay.close_overlay()
            e.accept()

    def paintEvent(self, e):
        p = QPainter(self)
        k = self._t
        if not self._scrim.isNull():
            p.setOpacity(k)
            p.drawPixmap(0, 0, self._scrim)
            p.setOpacity(1.0)
        else:
            p.fillRect(self.rect(), QColor(0, 0, 0, int(140 * k)))
        r = QRectF(self.panel_rect())
        dx = (1.0 - k) * (ph.px(36) if self.kind == "drawer" else 0)
        dy = (1.0 - k) * (ph.px(14) if self.kind == "planet" else 0)
        rr = r.translated(dx, dy)
        p.setOpacity(k)
        ph.paint_shadow(p, rr, "panel")
        if not self._snap.isNull():
            p.drawPixmap(rr.topLeft(), self._snap)
        p.end()


# ══════════════════════════════════════════════════════════════════════════ #
#  Раскладка целиком
# ══════════════════════════════════════════════════════════════════════════ #

class PhantomLayout(QObject):
    """Строит раскладку Phantom внутри YaShell и ведёт её. YaShell зовёт: page_shown(key) из _show_page,
    tick() из _tick, track_changed(t) из _on_track_changed, relayout() из resizeEvent, shutdown()."""

    def __init__(self, shell, win):
        super().__init__(shell)
        self.shell, self.win = shell, win
        ph.load_fonts()
        ph.configure(**self._appearance())
        self.ready = False
        # ── прежние кнопки и плеер: живут, но не видны ── #
        self.holder = QWidget(shell)
        self.holder.hide()
        hv = QVBoxLayout(self.holder)
        for b in shell._nav_btns.values():
            hv.addWidget(b)
        for w in (shell.pl_side, shell.avatar, shell.nick, shell.status):
            hv.addWidget(w)
        from PyQt6.QtWidgets import QStackedWidget
        shell.stack = QStackedWidget()
        shell.content = shell.stack
        hv.addWidget(shell._build_player())
        # ── видимые слои ── #
        self.root = QWidget(shell)
        self.root.setObjectName("PhRoot")
        self.root.setFont(ph.font(ph.TEXT_BASE))
        self.root.setStyleSheet(ph.qss())
        self.bg = ph_backdrop.PhBackground(self.root)
        self.host = pw.ShadowHost(self.root)
        self.top = PhTopBar(self, self.host)
        self.island = PhIsland(self, self.host)
        self.cover = PhCoverCard(self, self.host)
        self.player = PhPlayerCard(self, self.host)
        kinds = (win.settings.get("ph_widgets") or ["visualizer", "clock"])[:2]
        while len(kinds) < 2:
            kinds.append("clock")
        self.widgets = [PhWidgetCard(self, k, self.host) for k in kinds]
        self.right = PhRightColumn(self, self.host)
        self.overlay = PhOverlay(self, self.root)
        self.overlay.set_content(shell.stack)
        self.overlay.closed.connect(self._overlay_closed)
        shell._badge_on(self.top.b_planet)                     # непрочитанное Echoes.NET — на «планете»
        # «Ещё», «Звук» и реакция всплывают у «⋯» карточки плеера
        shell.b_pmore = shell.b_sound = shell.b_moment = self.player.b_more
        self._loader = CoverLoader(self)
        self._loader.ready.connect(self._on_cover)
        self._cover_for = None
        self._tb_hidden = False
        tb = getattr(win, "titlebar", None)
        if tb is not None and not tb.isHidden():               # окно может быть ещё не показано — isVisible() ложь
            tb.hide()
            self._tb_hidden = True
        self.mode = win.settings.get("ph_mode", "text")
        self.top.mode.set_current(self.mode)
        self.right.set_mode(self.mode)
        self.relayout()
        self.root.show()

    @staticmethod
    def _appearance() -> dict:
        return {}

    # ── геометрия ── #
    def relayout(self):
        sh = self.shell
        W, H = sh.width(), sh.height()
        self.root.setGeometry(0, 0, W, H)
        self.bg.setGeometry(0, 0, W, H)
        self.host.setGeometry(0, 0, W, H)
        if self.overlay.isVisible():
            self.overlay.setGeometry(0, 0, W, H)
        g = max(ph.px(20), min(ph.px(40), int(W * .024)))
        gap = max(ph.px(18), min(ph.px(38), int(W * .022)))
        top_h = ph.px(ph.TOPBAR_HEIGHT)
        self.top.setGeometry(g, 0, W - 2 * g + ph.px(12), top_h)
        self.island.move((W - self.island.width()) // 2, ph.px(18))
        inner = W - 2 * g - gap
        lw = int(inner * ph.LEFT_COLUMN / (ph.LEFT_COLUMN + ph.RIGHT_COLUMN))
        x0, y0 = g, top_h
        bottom = ph.px(36)
        avail = H - y0 - bottom
        card_h = ph.px(186)
        wid_h = max(ph.px(130), min(ph.px(210), int(avail * .27)))
        cgap = ph.px(18)
        cov_h = max(ph.px(120), avail - card_h - wid_h - 2 * cgap)
        if cov_h > lw * .72:                                   # высокое окно — обложка не выше 72 % ширины
            extra = cov_h - int(lw * .72)
            cov_h -= extra
            wid_h = min(wid_h + extra, ph.px(260))
        self.cover.setGeometry(x0, y0, lw, cov_h)
        y = y0 + cov_h + cgap
        self.player.setGeometry(x0, y, lw, card_h)
        y += card_h + cgap
        ww = (lw - cgap) // 2
        for i, wc in enumerate(self.widgets):
            wc.setGeometry(x0 + i * (ww + cgap), y, ww if i == 0 else lw - ww - cgap, max(ph.px(110), H - y - bottom))
        rx = x0 + lw + gap
        self.right.setGeometry(rx, top_h - ph.px(2), W - rx - g, H - top_h + ph.px(2))
        # пылинки — только там, где нет стекла
        self._occlude()
        self.host.update()

    def _occlude(self):
        """Пылинки — только там, где нет стекла и текста (под ними их не видно, а каждая будила бы перерисовку
        панели текста)."""
        rects = [w.geometry() for w in (self.cover, self.player, *self.widgets)]
        if self.mode == "text":
            rects.append(self.right.geometry())
        self.bg.set_occluders(rects)

    def set_under_visible(self, on: bool):
        """Фон и раскладка под панелью: прячутся, пока панель открыта целиком (их закрывает снимок)."""
        for w in (self.bg, self.host):
            if w.isVisible() != on:
                w.setVisible(on)

    # ── режимы правой колонки ── #
    def set_mode(self, mode: str):
        mode = "live" if mode == "live" else "text"
        if mode != self.mode:
            self.mode = mode
            self.win.settings["ph_mode"] = mode
        self.top.mode.set_current(mode)
        self.right.set_mode(mode)
        self._occlude()
        if mode == "text":
            sh = self.shell
            sh._lyr_src = None
            try:
                sh._lyrics_tick(None, None)
            except Exception as e:                             # noqa: BLE001
                print("[ph] lyrics:", e)

    def text_visible(self) -> bool:
        return self.mode == "text" and self.host.isVisible() and not self.overlay.is_open()

    # ── панели ── #
    def open_planet(self):
        sh = self.shell
        if self.overlay.is_open() and self.overlay.kind == "planet":
            self.close_overlay()
            return
        key = self.win.settings.get("ph_planet", "foryou")
        if key not in PLANET_KEYS:
            key = "foryou"
        sh.show_page(key)

    def toggle_page(self, key: str):
        ov = self.overlay
        cur = self.shell._cur_page
        if ov.is_open() and (cur == key or (key == "collection" and cur == "playlist")):
            self.close_overlay()
        else:
            self.shell.show_page(key)

    def page_shown(self, key: str):
        """YaShell показал страницу key (в стеке) — открыть нужную панель с нужной шапкой."""
        if not self.ready:
            return
        sh = self.shell
        if key in DRAWERS or key == "listening":
            kick, title = DRAWERS.get(key if key != "listening" else "settings")
            if key == "playlist":
                title = str(sh.__dict__.get("_pl_name", "") or title)
                if sh.__dict__.get("_pl_kind") == "album":
                    kick = "Album"
            self.overlay.configure("drawer", kick, title, back=key == "playlist")
        else:
            title = PLANET_TITLES.get(key, "Echoes")
            sub = ""
            if key == "artist":
                title = str(getattr(sh.pages.get("artist"), "name", "") or title)
            if key in {k for k, _t, _i in PLANET_MENU}:
                self.win.settings["ph_planet"] = key
            self.overlay.configure("planet", "Echoes", title, sub, menu_key=key, back=key not in PLANET_KEYS - {"artist"})
        self.overlay.open()
        self.top.sync_checked(key)

    def close_overlay(self, instant: bool = False):
        self.overlay.close(instant)
        self.top.sync_checked(None)

    def _overlay_closed(self):
        self.top.sync_checked(None)
        if self.mode == "text":
            self.shell._lyr_src = None

    def overlay_open(self) -> bool:
        return self.overlay.is_open()

    # ── данные ── #
    def upcoming(self, n: int = 3) -> list:
        w, sh = self.win, self.shell
        out = []
        try:
            out.extend(list(getattr(w, "user_queue", []) or [])[:n])
            qp = sh.pages.get("queue")
            if len(out) < n and qp is not None:
                ctx, cur_i, sq, sp = qp._context_view()
                tracks = w.library if ctx == "library" else w.playlists.get(ctx, {}).get("tracks", [])
                for i in qp._upcoming(tracks, cur_i, sq, sp)[:n - len(out)]:
                    out.append(tracks[i])
        except Exception as e:                                 # noqa: BLE001
            print("[ph] upcoming:", e)
        return out[:n]

    def track_changed(self, t):
        self.player.set_track(t)
        self.island.set_track(t, None)
        path = str((t or {}).get("cover", "") or "")
        side = int(max(self.cover.width(), self.cover.height()) * max(1.0, self.cover.devicePixelRatioF()))
        self._cover_for = t
        self._loader.load(path, max(256, side))
        self.right.live.set_track(t, QImage())
        self.right.live.set_next((self.upcoming(1) or [None])[0])

    def _on_cover(self, img: QImage):
        t = self._cover_for
        self.cover.set_image(img, _title(t) if t else "", _artist(t) if t else "")
        self.island.set_track(t, QPixmap.fromImage(img) if not img.isNull() else None)
        self.right.live.set_track(t, img)

    def tick(self, playing: bool, pos: float, dur: float):
        self.player.tick(playing, pos, dur)
        self.island.set_playing(playing)
        now = time.monotonic()
        if now - self.__dict__.get("_slow_t", 0.0) >= 1.0:   # раз в секунду: виджеты, «Далее», значки текста
            self._slow_t = now
            for wc in self.widgets:
                wc.tick()
            self.top.sync_update()
            if self.mode == "live":
                self.right.live.set_next((self.upcoming(1) or [None])[0])
            else:
                self.right.sync_tools()

    def save_widgets(self):
        self.win.settings["ph_widgets"] = [wc.widget_kind() for wc in self.widgets]

    def shutdown(self):
        tb = getattr(self.win, "titlebar", None)
        if tb is not None and self._tb_hidden:
            tb.show()
        self.bg.release()


def install_event_hooks(shell):
    """Esc в раскладке Phantom: открыта панель — закрыть её."""

    class _F(QObject):
        def eventFilter(self, obj, ev):
            if ev.type() == QEvent.Type.KeyPress and ev.key() == Qt.Key.Key_Escape:
                lay = shell.__dict__.get("ph")
                if lay is not None and lay.overlay.is_open():
                    lay.close_overlay()
                    return True
            return False
    f = _F(shell)
    shell.installEventFilter(f)
    return f
