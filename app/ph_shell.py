# ph_shell.py
"""
Раскладка Echoes Music в дизайне Phantom Audio (ya_layout = "phantom"), этап 2 — каркас окна.

    ┌ ECHOES 11:47 ─────────────────────────────── LIVE|ТЕКСТ  🌐 ▥ ≡ ⚙   – □ × ┐
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

import math
import threading
import time
from pathlib import Path

from frameclock import FrameTimer
from PyQt6.QtCore import (QEasingCurve, QEvent, QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer,
                          QVariantAnimation, pyqtSignal)
from PyQt6.QtGui import (QColor, QCursor, QFontMetrics, QIcon, QImage, QKeySequence, QLinearGradient, QPainter, QPen, QPixmap,
                         QRadialGradient, QShortcut)
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget

import ph_backdrop
import ph_style as ph
import ph_widgets as pw

# меню Echoes в панели «планеты»: ключ страницы YaShell, подпись, значок Lucide
PLANET_MENU = (("wave", "Моя волна", "waves-horizontal"), ("foryou", "Для вас", "sparkles"),
               ("albums", "Альбомы", "disc-3"), ("follows", "Подписки", "user-plus"),
               ("tierlist", "Тирлист", "chart-column"), ("duel", "Дуэль", "flag"),
               ("search", "Поиск", "search"), ("profile", "Профиль", "user-round"))
# Echoes.NET — отдельно от разделов: своя кнопка с землёй в верхней полосе и своя панель
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


def layout_of(widget) -> "PhantomLayout | None":
    """Раскладка Phantom окна, в котором widget (или None — прежний вид)."""
    try:
        sh = getattr(widget.window(), "_ya", None)
        return sh.__dict__.get("ph") if sh is not None else None
    except RuntimeError:
        return None


def paint_backdrop(widget, p: QPainter, rect: QRect | None = None) -> bool:
    """Нарисовать под widget то, что видно за ним внутри открытой панели: кусок размытого снимка под панелью и
    стекло панели. Для непрозрачных ради скорости виджетов (туманность «Моей волны», арена дуэли): выглядят как
    прозрачные, но не заставляют перерисовывать всё под собой. False — не в панели Phantom (рисовать как раньше)."""
    lay = layout_of(widget)
    if lay is None:
        return False
    ov = lay.overlay
    scrim = ov._scrim
    if scrim.isNull() or not ov.isVisible() or not ov.isAncestorOf(widget):
        return False
    off = widget.mapTo(ov, QPoint(0, 0))
    r = QRect(rect) if rect is not None else widget.rect()
    k = scrim.devicePixelRatio()
    p.drawPixmap(QRectF(r), scrim, QRectF((off.x() + r.x()) * k, (off.y() + r.y()) * k, r.width() * k,
                                          r.height() * k))
    p.fillRect(r, ph.white(ph.surface_alpha(True)))
    return True


def backdrop_key(widget):
    """Что меняет картинку paint_backdrop (для кэшей): снимок и положение виджета в панели."""
    lay = layout_of(widget)
    if lay is None or lay.overlay._scrim.isNull():
        return None
    off = widget.mapTo(lay.overlay, QPoint(0, 0))
    return (lay.overlay._scrim.cacheKey(), off.x(), off.y())


def lyrics_style(base: dict | None, phs: dict | None = None) -> dict:
    """Стиль панели текста Echoes в правой колонке Phantom: Inter 700 крупно, по левому краю, текущая строка
    чуть выше середины, неактивные размыты; без подписи времени. phs — настройки Phantom (раздел «Текст»)."""
    phs = phs or {}
    st = dict(base or {})
    for k in ("size", "panel", "liquid_glass", "upper"):          # крупный текст Phantom без подложки
        st.pop(k, None)
    st.update(phantom=True, align="left", time=False, karaoke=False,
              blur_inactive=bool(phs.get("lyrics_blur", True)), words=bool(phs.get("lyrics_words", True)),
              size_scale=float(phs.get("lyrics_scale", 1.0)))
    if not phs.get("lyrics_autoscroll", True):
        st["manual_scroll"] = True
    st.setdefault("anchor", .44)
    st.setdefault("line_gap", .62)
    st.setdefault("fade", .16)
    st.setdefault("weight", 700)
    st.setdefault("active_scale", 1.0)
    return st


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
    """ECHOES · часы и дата · LIVE|ТЕКСТ · значки · кнопки окна.
    Пустое место полосы двигает окно, двойной щелчок — развернуть."""

    def __init__(self, lay: "PhantomLayout", parent=None):
        super().__init__(parent)
        self.lay = lay
        win = lay.win
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(ph.px(16))
        brand = QHBoxLayout()
        brand.setSpacing(ph.px(4))
        mark = QLabel()
        mark.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        size = ph.px(20)
        logo = Path(__file__).resolve().parent / "assets/logo/echoes_mark.png"
        mark.setPixmap(QIcon(str(logo)).pixmap(QSize(size, size), self.devicePixelRatioF()))
        brand.addWidget(mark)
        self.word = pw.label("ECHOES", "PhWordmark", font=ph.font(15, 700, -.01))
        brand.addWidget(self.word)
        h.addLayout(brand)
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
        self.b_net = pw.icon_button("earth", "ghost", "top", 17, "Echoes.NET — друзья, лента, сообщения")
        self.b_shop = pw.icon_button("shopping-bag", "ghost", "top", 17, "Магазин косметики и поддержка ECHOES")
        self.b_planet = pw.icon_button("compass", "ghost", "top", 17, "Разделы Echoes")
        self.b_library = pw.icon_button("library", "ghost", "top", 17, "Библиотека")
        self.b_queue = pw.icon_button("list-music", "ghost", "top", 17, "Очередь")
        self.b_settings = pw.icon_button("settings", "ghost", "top", 17, "Настройки")
        self.b_planet.clicked.connect(lay.open_planet)
        self.b_net.clicked.connect(lambda: lay.toggle_page("net"))
        self.b_shop.clicked.connect(lambda: lay.toggle_page("shop"))
        self.b_library.clicked.connect(lambda: lay.toggle_page("collection"))
        self.b_queue.clicked.connect(lambda: lay.toggle_page("queue"))
        self.b_settings.clicked.connect(lambda: lay.toggle_page("settings"))
        for b in (self.b_net, self.b_shop, self.b_planet, self.b_library, self.b_queue, self.b_settings):
            b.setCheckable(True)
            icons.addWidget(b)
            if b is self.b_shop:                               # сеть и магазин — отдельно от разделов: разделитель
                sep = QWidget()
                sep.setFixedSize(1, ph.px(16))
                sep.setStyleSheet(f"background:{ph.css(ph.LINE_2)};")
                icons.addSpacing(ph.px(2))
                icons.addWidget(sep, 0, Qt.AlignmentFlag.AlignVCenter)
                icons.addSpacing(ph.px(2))
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
        for b, keys in ((self.b_net, {"net"}), (self.b_shop, {"shop"}), (self.b_planet, PLANET_KEYS), (self.b_library, {"collection", "playlist"}),
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


# ══════════════════════════════════════════════════════════════════════════ #
#  Левая колонка
# ══════════════════════════════════════════════════════════════════════════ #

class PhCoverCard(QWidget):
    """Большая карточка обложки над плеером. Обложки квадратные, а карточка широкая, поэтому вид на выбор
    (настройка «Вид карточки»): info — обложка слева и сведения о треке справа; blur — обложка по центру на её же
    размытой копии; vinyl — конверт и выезжающая пластинка (модель из vinyl.py); crop — обложка с обрезкой.
    Своя обложка (ph_cover): фото, GIF или видео — на месте обложки или на всю карточку.
    ⤢ — режим обложки Echoes; кнопка-картинка — своя обложка и вид; клик — LIVE."""

    def __init__(self, lay: "PhantomLayout", parent=None):
        super().__init__(parent)
        self.lay = lay
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._img = QImage()                                   # обложка трека
        self._custom = QImage()                                # своя картинка (правило с фото)
        self._custom_src = ""
        self._raw = None                                       # последний кадр GIF/видео
        self._title = self._artist = ""
        self._track = None
        self._rule = None                                      # действующее правило своей обложки
        self._old = QPixmap()
        self._fade = 1.0
        self._bg, self._bg_k = QPixmap(), None
        self._slot, self._slot_k = QPixmap(), None
        self._playing = False
        self._angle = 0.0
        self._slide = .30                                      # насколько пластинка выехала из конверта
        self._vw, self._vw_k = None, None
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(ph.ease_out())
        self._anim.valueChanged.connect(self._on_fade)
        self._spin = FrameTimer(self)
        self._spin.setInterval(33)
        self._spin.timeout.connect(self._spin_tick)
        self._spin_t = time.monotonic()
        self.expand = pw.icon_button("maximize-2", "surface", "sm", 13, "Режим обложки", parent=self)
        self.expand.clicked.connect(lambda: getattr(lay.win, "_toggle_cover_mode", lambda: None)())
        self.media_btn = pw.icon_button("image", "surface", "sm", 13, "Своя обложка и вид карточки", parent=self)
        self.media_btn.clicked.connect(self._media_menu)
        for b in (self.expand, self.media_btn):                # кнопки — при наведении (как в Phantom): не на тексте
            b.hide()
        import ph_cover
        if ph_cover.QUALITY is None:
            ph_cover.QUALITY = ph_cover._Quality()
        ph_cover.QUALITY.ready.connect(self._on_quality)

    def _media_menu(self):
        import ph_cover
        ph_cover.cover_menu(self.lay, self.media_btn)
        if not self.underMouse():
            self.leaveEvent(None)

    def enterEvent(self, e):
        self.expand.show()
        self.media_btn.show()

    def leaveEvent(self, e):
        if self.media_btn.isDown():
            return
        self.expand.hide()
        self.media_btn.hide()

    def radius(self) -> float:
        return float(ph.px(22))

    # ── данные ── #
    style = "info"
    treatment = "original"                                     # «Обработка обложки»: original | mono | dim

    def set_style(self, style: str):
        if style not in ("info", "blur", "vinyl", "crop"):
            style = "info"
        if style != self.style:
            self._old = self._snapshot()                       # плавно из прежнего вида в новый
            self.style = style
            self._start_fade()
            self._invalidate()
            self._frame_rescale()
            self._sync_spin()

    def set_treatment(self, mode: str):
        if mode != self.treatment:
            self.treatment = mode
            self._invalidate()
            self._vw_k = None

    def set_track(self, t):
        self._track = t

    def set_image(self, img: QImage, title: str, artist: str):
        self._old = self._snapshot()
        self._img, self._title, self._artist = img, title, artist
        self._invalidate()
        self._start_fade()

    def _start_fade(self):
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

    def set_playing(self, playing: bool):
        if playing != self._playing:
            self._playing = playing
            self._sync_spin()

    def _on_quality(self, path, _txt):
        if self._track and str(self._track.get("path") or "") == path and self.style == "info":
            self._invalidate()

    def _invalidate(self):
        self._bg_k = self._slot_k = None
        self.update()

    def _on_fade(self, v):
        self._fade = float(v)
        if self._fade >= 1.0:
            self._old = QPixmap()
        self.update()

    def _snapshot(self) -> QPixmap:
        """Нынешний вид карточки без кнопок — для плавной смены трека."""
        if self.width() < 4 or not self.isVisible():
            return QPixmap()
        dpr = self.devicePixelRatioF() or 1.0
        pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        try:
            self._paint_content(p)
        finally:
            p.end()
        return pm

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._invalidate()
        self._old = QPixmap()
        m = ph.px(14)
        self.expand.move(self.width() - self.expand.width() - m, m)
        self.media_btn.move(self.expand.x() - self.media_btn.width() - ph.px(6), m)
        self._frame_rescale()

    def _treat(self, img: QImage) -> QImage:
        if self.treatment == "mono" and not img.isNull():
            return img.convertToFormat(QImage.Format.Format_Grayscale8).convertToFormat(
                QImage.Format.Format_ARGB32_Premultiplied)
        return img

    def _still(self) -> QImage:
        """Неподвижная картинка для места обложки: своё фото или обложка трека."""
        return self._custom if not self._custom.isNull() else self._img

    # ── раскладка вида ── #
    def _geom(self):
        """(вид, место обложки, место сведений). Узкая карточка — вид попроще, чтобы всё помещалось."""
        W, H = self.width(), self.height()
        r = self._rule
        if self.style == "crop" or (r is not None and r.get("fill")) or H < ph.px(60) or W < H * 1.3:
            # карточка на одну клетку (почти квадрат) — просто обложка 1:1
            return "crop", QRectF(0, 0, W, H), None
        pad = ph.px(14)
        s = H - 2 * pad
        if self.style == "info":
            tx = pad + s + ph.px(18)
            if W - pad - tx >= ph.px(120):
                return "info", QRectF(pad, pad, s, s), QRectF(tx, pad, W - pad - tx, s)
        if self.style == "vinyl" and W >= s * 1.5 + 2 * pad:
            return "vinyl", QRectF(pad + ph.px(6), pad, s, s), None
        return "blur", QRectF((W - s) / 2, pad, s, s), None

    def _slot_radius(self, mode) -> float:
        return self.radius() if mode == "crop" else float(ph.px(12))

    # ── фон: размытая обложка, тень под обложкой, сведения ── #
    def _background(self, mode, slot, text) -> QPixmap:
        W, H = self.width(), self.height()
        dpr = self.devicePixelRatioF() or 1.0
        src = self._treat(self._still())
        info = self._info_lines() if mode == "info" else None
        key = (mode, W, H, dpr, src.cacheKey(), self.treatment, slot, text, info)
        if key == self._bg_k:
            return self._bg
        pm = QPixmap(max(1, int(W * dpr)), max(1, int(H * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        try:
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            q.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            q.setClipPath(ph.surface_path(QRectF(0, 0, W, H), self.radius()))
            if not src.isNull():
                import blur_fx
                bw, bh = max(8, int(W * dpr / 3)), max(8, int(H * dpr / 3))
                q.drawImage(QRectF(0, 0, W, H), blur_fx.blurred_cover(src, bw, bh, 9.0, dim=.42, sat=1.15))
            else:
                g = QLinearGradient(0, 0, W, H)
                g.setColorAt(0, QColor(24, 24, 24))
                g.setColorAt(1, QColor(8, 8, 8))
                q.fillRect(QRectF(0, 0, W, H), g)
            g = QLinearGradient(0, 0, 0, H)                    # стекло Phantom: светлее сверху, темнее снизу
            g.setColorAt(0, ph.white(.06))
            g.setColorAt(.5, QColor(0, 0, 0, 0))
            g.setColorAt(1, QColor(0, 0, 0, 70))
            q.fillRect(QRectF(0, 0, W, H), g)
            ph.paint_shadow(q, slot, "card", self._slot_radius(mode))
            if info is not None:
                self._paint_info(q, text, info)
        finally:
            q.end()
        self._bg, self._bg_k = pm, key
        return pm

    def _info_lines(self):
        t = self._track or {}
        import ph_cover
        path = str(t.get("path") or "")
        ext = Path(path).suffix.lstrip(".").upper() if path and not path.startswith("http") else ""
        qual = ph_cover.quality(path) if ext else ""
        dur = int(t.get("duration") or 0)
        album = str(t.get("album") or "").strip()
        genre = str(t.get("genre") or "").strip()
        chips = tuple(x for x in (ext, qual or "", f"{dur // 60}:{dur % 60:02d}" if dur else "") if x)
        return (self._title or "Ничего не играет", self._artist, " · ".join(x for x in (album, genre) if x), chips,
                bool(self._track))

    def _paint_info(self, q: QPainter, r: QRectF, info):
        title, artist, album, chips, has = info
        x, w = r.x(), r.width()
        y = r.y() + ph.px(2)
        f = ph.kicker_font()
        q.setFont(f)
        q.setPen(ph.qcolor(ph.TEXT_TERTIARY))
        fm = QFontMetrics(f)
        q.drawText(QRectF(x, y, w, fm.height()), Qt.AlignmentFlag.AlignLeft, "СЕЙЧАС ИГРАЕТ" if has else "ECHOES")
        y += fm.height() + ph.px(8)
        big = r.height() >= ph.px(150)
        ft = ph.font(ph.TEXT_XL if big else ph.TEXT_LG, 650, -.02)
        q.setFont(ft)
        q.setPen(ph.qcolor(ph.TEXT_PRIMARY))
        fm = QFontMetrics(ft)
        for ln in _wrap2(title, fm, int(w), 2 if big else 1):
            q.drawText(QRectF(x, y, w, fm.height()), Qt.AlignmentFlag.AlignLeft, ln)
            y += fm.height()
        y += ph.px(4)
        if artist:
            fa = ph.font(ph.TEXT_SM, 500)
            q.setFont(fa)
            q.setPen(ph.qcolor(ph.TEXT_SECONDARY))
            fm = QFontMetrics(fa)
            q.drawText(QRectF(x, y, w, fm.height()), Qt.AlignmentFlag.AlignLeft,
                       fm.elidedText(artist, Qt.TextElideMode.ElideRight, int(w)))
            y += fm.height() + ph.px(2)
        if album:
            fb = ph.font(ph.TEXT_XS)
            q.setFont(fb)
            q.setPen(ph.qcolor(ph.TEXT_TERTIARY))
            fm = QFontMetrics(fb)
            q.drawText(QRectF(x, y, w, fm.height()), Qt.AlignmentFlag.AlignLeft,
                       fm.elidedText(album, Qt.TextElideMode.ElideRight, int(w)))
            y += fm.height()
        if chips:                                              # формат, качество, длительность — пилюли внизу
            fc = ph.font(ph.TEXT_2XS, 600, .04)
            q.setFont(fc)
            fm = QFontMetrics(fc)
            ch = fm.height() + ph.px(8)
            cx, cy = x, r.bottom() - ch
            if cy > y + ph.px(4):
                for c in chips:
                    cw = fm.horizontalAdvance(c) + ph.px(16)
                    if cx + cw > x + w:
                        break
                    rr = QRectF(cx, cy, cw, ch)
                    q.setPen(QPen(ph.qcolor(ph.LINE_2), 1.0))
                    q.setBrush(ph.white(.06))
                    q.drawRoundedRect(rr.adjusted(.5, .5, -.5, -.5), ch / 2, ch / 2)
                    q.setPen(ph.qcolor(ph.TEXT_SECONDARY))
                    q.drawText(rr, Qt.AlignmentFlag.AlignCenter, c)
                    cx += cw + ph.px(6)

    # ── место обложки ── #
    def _slot_pixmap(self, mode, slot) -> QPixmap:
        dpr = self.devicePixelRatioF() or 1.0
        src = self._treat(self._still())
        rad = self._slot_radius(mode)
        key = (src.cacheKey(), slot.size(), rad, dpr, self.treatment, self._title, self._artist)
        if key != self._slot_k:
            size = QSize(max(1, int(slot.width())), max(1, int(slot.height())))
            self._slot = (ph.rounded_pixmap(src, size, rad, dpr) if not src.isNull()
                          else ph.placeholder_cover(size, self._title, self._artist, rad, dpr))
            self._slot_k = key
        return self._slot

    def _paint_slot(self, p: QPainter, mode, slot):
        rad = self._slot_radius(mode)
        if self._frame is not None:                            # GIF / видео — кадр уже под размер места
            p.save()
            p.setClipPath(ph.surface_path(slot, rad))
            fw = self._frame.width() / self._frame.devicePixelRatio()
            fh = self._frame.height() / self._frame.devicePixelRatio()
            p.drawImage(QPointF(slot.center().x() - fw / 2, slot.center().y() - fh / 2), self._frame)
            p.restore()
        else:
            p.drawPixmap(slot.topLeft(), self._slot_pixmap(mode, slot))
        if mode != "crop":
            p.setPen(QPen(ph.qcolor(ph.LINE_2), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(slot.adjusted(.5, .5, -.5, -.5), rad, rad)

    # ── винил: модель из vinyl.py (диск, бороздки, этикетка с обложкой, блик) ── #
    def _vinyl(self):
        if self._vw is None:
            import vinyl
            self._vw = vinyl.VinylWidget(self)
            self._vw.hide()
        src = self._treat(self._still())
        k = (src.cacheKey(), self.treatment)
        if k != self._vw_k:
            self._vw.set_cover(QPixmap.fromImage(src) if not src.isNull() else QPixmap())
            self._vw_k = k
        return self._vw

    def _disc_geom(self, slot):
        r = slot.height() * .47
        return slot.x() + slot.width() * (.5 + self._slide), slot.center().y(), r

    def _paint_disc(self, p: QPainter, slot):
        cx, cy, r = self._disc_geom(slot)
        try:
            static, spin, sheen = self._vinyl()._real_layers(r)
        except Exception as e:                                 # noqa: BLE001
            print("[ph] vinyl:", e)
            return
        g = QRadialGradient(cx + r * .04, cy + r * .08, r * 1.12)
        g.setColorAt(0, QColor(0, 0, 0, 120))
        g.setColorAt(.85, QColor(0, 0, 0, 60))
        g.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(cx + r * .04, cy + r * .08), r * 1.12, r * 1.12)
        S = static.width() / static.devicePixelRatio()
        p.drawPixmap(QPointF(cx - S / 2, cy - S / 2), static)
        p.save()
        p.translate(cx, cy)
        p.rotate(self._angle)
        p.drawPixmap(QPointF(-S / 2, -S / 2), spin)
        p.restore()
        p.drawPixmap(QPointF(cx - S / 2, cy - S / 2), sheen)

    def _sync_spin(self):
        run = (self.style == "vinyl" and self.isVisible() and not (self.window() and self.window().isMinimized())
               and (self._playing or abs(self._slide - .30) > .002))
        if run and not self._spin.isActive():
            self._spin_t = time.monotonic()
            self._spin.start()
        elif not run and self._spin.isActive():
            self._spin.stop()

    def _spin_tick(self):
        now = time.monotonic()
        dt = min(.1, now - self._spin_t)
        self._spin_t = now
        mode, slot, _ = self._geom()
        if mode != "vinyl":
            self._spin.stop()
            return
        target = .46 if self._playing else .30                 # играет — пластинка выезжает и крутится
        self._slide += (target - self._slide) * min(1.0, dt * 4.0)
        if self._playing:
            self._angle = (self._angle + dt * 120.0) % 360.0
        cx, cy, r = self._disc_geom(slot)
        x0 = int(slot.center().x())
        self.update(QRect(x0, int(cy - r * 1.2), int(cx + r * 1.2 - x0 + ph.px(8)), int(2.4 * r)))
        if not self._playing and abs(self._slide - .30) <= .002:
            self._spin.stop()

    # ── своя обложка: фото / GIF / видео ── #
    _player = None
    _sink = None
    _movie = None
    _frame = None
    _video_src = ""

    def set_media(self, rule):
        """rule из ph_cover.resolve (или None — обложка трека)."""
        import ph_cover
        path = ph_cover.media_path(rule) if rule else ""
        kind = ph_cover.media_kind(path) if path else ""
        old_k = ((self._rule or {}).get("path"), (self._rule or {}).get("fill"))
        self._rule = rule if kind else None
        new_k = ((self._rule or {}).get("path"), (self._rule or {}).get("fill"))
        if new_k != old_k:
            self._old = self._snapshot()
        self._play_video(path if kind == "video" else "")
        self._play_gif(path if kind == "gif" else "")
        if kind == "image":
            if self._custom_src != path:
                from PyQt6.QtGui import QImageReader
                rd = QImageReader(path)
                rd.setAutoTransform(True)
                sz = rd.size()
                if sz.isValid() and max(sz.width(), sz.height()) > 1600:
                    rd.setScaledSize(sz.scaled(1600, 1600, Qt.AspectRatioMode.KeepAspectRatio))
                self._custom = rd.read()
                self._custom_src = path
        else:
            self._custom, self._custom_src = QImage(), ""
        self._invalidate()
        self._frame_rescale()
        if new_k != old_k:
            self._start_fade()

    def set_video(self, path: str):
        """Прежний вызов: видео на всю карточку ('' — обложка трека)."""
        self.set_media({"scope": "all", "key": "", "path": path, "fill": True} if path else None)

    def _play_video(self, path: str):
        if path == self._video_src:
            return
        self._video_src = path
        if not path:
            if self._player is not None:
                self._player.stop()
                self._player.deleteLater()
                self._player = self._sink = None
            if self._movie is None:
                self._frame = self._raw = None
            self.update()
            return
        try:
            from PyQt6.QtCore import QUrl
            from PyQt6.QtMultimedia import QMediaPlayer, QVideoSink
        except Exception as e:                                 # noqa: BLE001
            print("[ph] video:", e)
            return
        if self._player is None:
            self._player = QMediaPlayer(self)
            self._sink = QVideoSink(self)
            self._player.setVideoSink(self._sink)
            self._sink.videoFrameChanged.connect(self._on_frame)
            try:
                self._player.setLoops(QMediaPlayer.Loops.Infinite)
            except Exception:                                  # noqa: BLE001
                pass
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._sync_video()

    def _play_gif(self, path: str):
        cur = self._movie.fileName() if self._movie is not None else ""
        if path == cur:
            return
        if self._movie is not None:
            self._movie.stop()
            self._movie.deleteLater()
            self._movie = None
            if self._player is None:
                self._frame = self._raw = None
        if not path:
            return
        from PyQt6.QtGui import QMovie
        self._movie = QMovie(path, parent=self)
        self._movie.setCacheMode(QMovie.CacheMode.CacheAll)
        mv = self._movie
        mv.frameChanged.connect(lambda _i, m=mv: self._on_image_frame(m.currentImage()))
        self._sync_video()

    def _sync_video(self):
        run = self.isVisible() and not (self.window() and self.window().isMinimized())
        if self._player is not None:
            from PyQt6.QtMultimedia import QMediaPlayer
            st = self._player.playbackState()
            if run and st != QMediaPlayer.PlaybackState.PlayingState:
                self._player.play()
            elif not run and st == QMediaPlayer.PlaybackState.PlayingState:
                self._player.pause()
        if self._movie is not None:
            from PyQt6.QtGui import QMovie
            st = self._movie.state()
            if run and st == QMovie.MovieState.NotRunning:
                self._movie.start()
            elif run and st == QMovie.MovieState.Paused:
                self._movie.setPaused(False)
            elif not run and st == QMovie.MovieState.Running:
                self._movie.setPaused(True)

    def showEvent(self, e):
        super().showEvent(e)
        self._sync_video()
        self._sync_spin()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._sync_video()
        self._sync_spin()

    def _on_frame(self, frame):
        if not frame.isValid() or not self.isVisible():
            return
        self._on_image_frame(frame.toImage())

    def _on_image_frame(self, img: QImage):
        if img.isNull() or not self.isVisible():
            return
        self._raw = img
        self._frame_rescale()

    def _frame_rescale(self):
        img = self._raw
        if img is None or (self._player is None and self._movie is None):
            self._frame = None
            return
        _mode, slot, _ = self._geom()
        dpr = self.devicePixelRatioF() or 1.0
        w, h = max(1, int(slot.width() * dpr)), max(1, int(slot.height() * dpr))
        out = img.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                         Qt.TransformationMode.SmoothTransformation if self._movie is not None
                         else Qt.TransformationMode.FastTransformation)
        out = self._treat(out)
        out.setDevicePixelRatio(dpr)
        self._frame = out
        self.update(slot.toAlignedRect().adjusted(-1, -1, 1, 1))

    # ── мышь и отрисовка ── #
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.lay.set_mode("live")
        elif e.button() == Qt.MouseButton.RightButton:
            self.lay.shell._p_cover_press(e)

    def _paint_content(self, p: QPainter):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        mode, slot, text = self._geom()
        if mode != "crop":
            p.drawPixmap(0, 0, self._background(mode, slot, text))
        if mode == "vinyl":
            self._paint_disc(p, slot)
        self._paint_slot(p, mode, slot)

    def paintEvent(self, e):
        p = QPainter(self)
        try:
            if not self._old.isNull() and self._fade < 1.0:
                p.drawPixmap(0, 0, self._old)
                p.setOpacity(self._fade)
            self._paint_content(p)
            p.setOpacity(1.0)
            if self.treatment == "dim":
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 0, 0, 92))
                p.drawPath(ph.surface_path(QRectF(self.rect()), self.radius()))
            p.setPen(QPen(ph.qcolor(ph.LINE_1), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            r = self.radius()
            p.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), r, r)
        finally:
            p.end()


def _wrap2(text: str, fm: QFontMetrics, width: int, lines: int = 2) -> list:
    """Перенос по словам максимум на lines строк, последняя — с многоточием."""
    if lines <= 1 or fm.horizontalAdvance(text) <= width:
        return [fm.elidedText(text, Qt.TextElideMode.ElideRight, width)]
    words, first = text.split(), ""
    for i, wd in enumerate(words):
        cand = (first + " " + wd).strip()
        if fm.horizontalAdvance(cand) > width and first:
            rest = " ".join(words[i:])
            return [first, fm.elidedText(rest, Qt.TextElideMode.ElideRight, width)]
        first = cand
    return [fm.elidedText(text, Qt.TextElideMode.ElideRight, width)]


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
        self.b_extra = pw.icon_button("sliders-vertical", "ghost", "sm", 15,
                                      "Перемешать, повтор, громкость — спрятаны, чтобы плеер стал маленьким")
        self.b_extra.clicked.connect(self._extra_menu)
        self.b_extra.wheelEvent = self._vol_wheel
        self.b_extra.hide()                                    # только у маленького плеера
        for b in (self.b_like, self.b_vol, self.b_extra, self.b_more):
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
        self._v = v
        self._state = {}
        self._pop: PhVolumePopup | None = None
        self.compact = False

    def set_compact(self, on: bool):
        """Плеер на одну клетку: название мельче, «перемешать», «повтор» и громкость прячутся — они в меню
        кнопки ⫶ (громкость ещё и колесом над карточкой), поля уже. ⏮ ▶ ⏭, ♥, «⋯» и полоса остаются."""
        if on == self.compact:
            return
        self.compact = on
        for b in (self.b_shuffle, self.b_repeat, self.b_vol):
            b.setVisible(not on)
        self.b_extra.setVisible(on)                            # они — в меню этой кнопки
        ph.set_font(self.title, ph.font(17 if on else 22, 650, -.02))
        m = ph.px(14 if on else 20)
        self._v.setContentsMargins(m, ph.px(14 if on else 18), m, ph.px(12 if on else 14))

    def wheelEvent(self, e):
        if self.compact:                                       # громкости-кнопки нет — колесо над карточкой
            self._vol_wheel(e)
            return
        super().wheelEvent(e)

    def set_track(self, t):
        reserve = ph.px(100 if self.compact else 150)
        _elide(self.title, _title(t) if t else "—", self.width() - reserve)
        _elide(self.artist, _artist(t) if t else "", self.width() - reserve)
        self._state.pop("like", None)

    def resizeEvent(self, e):
        self.set_compact(self.width() < ph.px(340))
        super().resizeEvent(e)
        t = self.lay.shell.current_track()
        self.set_track(t)

    def _seek_preview(self, f):
        d = self._state.get("dur", 0.0)
        self.t_pos.setText(_fmt(f * d))

    def _extra_menu(self):
        """Меню маленького плеера: то, что спрятано, чтобы он поместился на одну клетку."""
        from PyQt6.QtWidgets import QMenu
        w = self.lay.win
        m = QMenu(self)
        a = m.addAction(ph.icon("shuffle", 14), "Перемешать")
        a.setCheckable(True)
        a.setChecked(bool(w.shuffle))
        a.triggered.connect(lambda: w.btn_shuffle.click())
        rm = int(getattr(w, "repeat_mode", 0))
        a = m.addAction(ph.icon("repeat-1" if rm == 2 else "repeat", 14),
                        ("Повтор: выключен", "Повтор: весь список", "Повтор: один трек")[max(0, min(2, rm))])
        a.triggered.connect(w._cycle_repeat)
        vol = w.vol.value()
        a = m.addAction(ph.icon(("volume-x", "volume-1", "volume-2")[0 if vol == 0 else 1 if vol < 50 else 2], 14),
                        f"Громкость: {vol}%")
        a.triggered.connect(lambda: self._volume(self.b_extra))
        m.exec(self.b_extra.mapToGlobal(QPoint(0, self.b_extra.height() + ph.px(4))))

    def _volume(self, anchor=None):
        if self._pop is None:
            self._pop = PhVolumePopup(self.lay)
        self._pop.sync()
        anchor = anchor if isinstance(anchor, QWidget) else self.b_vol
        g = anchor.mapToGlobal(QPoint(anchor.width() // 2, anchor.height() + ph.px(6)))
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
    """Карточка-виджет слева (как у Phantom): кикер, подпись, ‹ ›, точки. Виды и их отрисовка — ph_cards
    (спектр, круг, уровень, статистика, эквалайзер, часы, очередь, о треке, погода, друзья в NET, ачивки)."""

    def __init__(self, lay: "PhantomLayout", kind: str, parent=None):
        super().__init__("card", parent)
        import ph_cards
        self.KINDS = ph_cards.KINDS
        self.lay = lay
        keys = [k for k, _a, _b in self.KINDS]
        self.idx = keys.index(kind) if kind in keys else 0
        v = QVBoxLayout(self)
        v.setContentsMargins(ph.px(16), ph.px(14), ph.px(12), ph.px(12))
        v.setSpacing(0)
        self._v = v
        self._compact = False
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
        self._arrows = (bl, br)
        self.reset = pw.icon_button("rotate-ccw", "ghost", "sm", 13, "Сбросить эквалайзер (все полосы в ноль)")
        self.reset.clicked.connect(self._eq_reset)
        hr.addWidget(self.reset, 0, Qt.AlignmentFlag.AlignTop)
        hr.addWidget(bl, 0, Qt.AlignmentFlag.AlignTop)
        hr.addWidget(br, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(hr)
        self.body = ph_cards.WidgetBody(self)
        v.addWidget(self.body, 1)
        self.dots = pw.PhDots(len(self.KINDS), self.idx)
        v.addWidget(self.dots, 0, Qt.AlignmentFlag.AlignHCenter)
        self._apply()

    def widget_kind(self) -> str:
        return self.KINDS[self.idx][0]

    def step(self, d: int):
        old = self.body.grab() if self.body.isVisible() else None
        self.idx = (self.idx + d) % len(self.KINDS)
        self._apply()
        if old is not None:
            self.body.slide(old, d)                            # старый вид уезжает, новый въезжает
        self.lay.save_widgets()

    def set_kind(self, kind: str):
        keys = [k for k, _a, _b in self.KINDS]
        if kind in keys:
            self.idx = keys.index(kind)
            self._apply()

    def _apply(self):
        _k, kick, sub = self.KINDS[self.idx]
        self.kick.setText(kick.upper())
        self.sub.setText(sub)
        self.dots.set_current(self.idx)
        self.reset.setVisible(self.widget_kind() == "eq" and not self._compact)
        self.body.kind_changed()

    COMPACT_W = 210                                            # уже (квадрат 1:1) — шапка без подписи; ‹ › остаются

    def resizeEvent(self, e):
        super().resizeEvent(e)
        compact = self.width() < ph.px(self.COMPACT_W)
        if compact == self._compact:
            return
        self._compact = compact                                # виды листаются ‹ › и колёсиком
        self.sub.setVisible(not compact)
        self.reset.setVisible(self.widget_kind() == "eq" and not compact)
        m = ph.px(10) if compact else ph.px(16)
        self._v.setContentsMargins(m, ph.px(10) if compact else ph.px(14), ph.px(8) if compact else ph.px(12),
                                   ph.px(8) if compact else ph.px(12))

    def _eq_reset(self):
        """Все полосы в ноль: пресет «Плоский», если он есть, иначе ползунки по одному."""
        win = self.lay.win
        cb = getattr(win, "eq_preset_cb", None)
        i = cb.findText("Плоский") if cb is not None else -1
        if i >= 0:
            if cb.currentIndex() == i:
                cb.setCurrentIndex(0)
            cb.setCurrentIndex(i)
        for sl in getattr(win, "_eq_sliders", None) or []:
            if sl.value() != 0:
                sl.setValue(0)
        self.body.kind_changed()

    def wheelEvent(self, e):                                   # колесо над карточкой — листать виды
        d = e.angleDelta().y()
        if d:
            self.step(-1 if d > 0 else 1)
            e.accept()

    def tick(self):
        self.body.tick()


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
        panel.liquid = False                                   # буквы не подрастают: текущая строка загорается
                                                               # по словам (LyricsScrollPanel._draw_words_ph)
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
        self.set_tabs = pw.PhSegments([("phantom", "Phantom", "sparkles"), ("echoes", "Echoes — все настройки",
                                                                             "settings")])
        self.set_tabs.changed.connect(self._settings_switch)
        self.set_tabs.hide()
        pv.addWidget(self.set_tabs)
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
        if kind in ("planet", "wide"):
            m = ph.px(20)
            return QRect(m, m, W - 2 * m, H - 2 * m)
        m = ph.px(12)
        k, lo = (.5, ph.px(660)) if kind == "side" else (.44, ph.px(560))
        w = min(max(lo, int(W * k)), W - 2 * m)
        return QRect(W - w - m, m, w, H - 2 * m)

    def settings_tab(self) -> str:
        return self.set_tabs.current() or "phantom"

    def _settings_switch(self, key: str):
        """Настройки: «Phantom» — разделы Phantom, «Echoes» — прежняя страница со всеми настройками Echoes."""
        sh = self.lay.shell
        w = self.lay.page_widget("settings") if key == "phantom" else sh.pages.get("settings")
        if w is not None:
            sh.stack.setCurrentWidget(w)

    def configure(self, kind: str, kick: str, title: str, subline: str = "", menu_key: str | None = None,
                  back: bool = False, settings: bool = False):
        changed = kind != self.kind
        self.kind = kind
        self.kick.setText(kick.upper())
        ph.set_font(self.title, ph.font(30 if kind in ("planet", "wide") else 22, 650, -.03))
        self.title.setText(title)
        self.subline.setText(subline.upper())
        self.subline.setVisible(bool(subline))
        planet = kind == "planet"
        self.set_tabs.setVisible(settings)
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
        """Панель открыта целиком: под ней всё прячется — снимок закрывает окно, а живые фон и текст
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
        dx = (1.0 - k) * (ph.px(36) if self.kind in ("drawer", "side") else 0)
        dy = (1.0 - k) * (ph.px(14) if self.kind in ("planet", "wide") else 0)
        rr = r.translated(dx, dy)
        p.setOpacity(k)
        ph.paint_shadow(p, rr, "panel")
        if not self._snap.isNull():
            p.drawPixmap(rr.topLeft(), self._snap)
        p.end()


class PhEditLayer(QWidget):
    """Режим правки левой колонки (как на iPhone): зажали колёсико мыши над колонкой — блоки (обложка, плеер,
    виджеты) чуть уменьшаются и покачиваются; × — убрать, ‹↑› ‹↓› — на уровень выше/ниже, ⤡ — размер по кругу:
    половина (две в ряд) → квадрат 1:1 (три в ряд) → вся ширина; когда все виджеты 1:1, колонка сужается;
    кнопка слева внизу — «один в ряду» (рядом пусто) или снова рядом с соседом; ↕ — высота виджета: «авто»
    (растянуть до низа колонки), ровно 1 или 2 клетки (ниже или рядом остаётся пустое место); внизу «Добавить» и «Готово». Пока правка открыта, настоящие блоки спрятаны, слой рисует
    их снимки (кадр — только повороты картинок). Всё движется плавно: перестановки едут, убранный блок
    сжимается и гаснет, новый вырастает, кнопки пружинят."""

    def __init__(self, lay: "PhantomLayout", parent=None):
        super().__init__(parent)
        self.lay = lay
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.hide()
        self._snaps: dict = {}                                 # id(блока) → снимок
        self._cur: dict = {}                                   # id(блока) → QRectF сейчас (едет к цели)
        self._dying: list = []                                 # [(снимок, QRectF, t0)] — убранные, гаснут
        self._t0 = time.monotonic()
        self._last = self._t0
        self._k = 0.0                                          # 0 — обычный вид, 1 — правка (уменьшены)
        self._k_to = 0.0
        self._press = None                                     # (действие, блок, t0) — пружинка кнопки
        self._hover = None
        self._timer = FrameTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._frame)
        self._hits: list = []                                  # [(QRectF, действие, блок)]

    # ── вход / выход ── #
    def open(self):
        lay = self.lay
        self.setGeometry(lay.host.geometry())
        self._snaps.clear()
        self._cur.clear()
        self._dying.clear()
        for it in lay.left_items:
            w = lay.block_widget(it)
            self._snaps[id(it)] = w.grab()
            self._cur[id(it)] = QRectF(w.geometry())
            w.hide()
        self._t0 = self._last = time.monotonic()
        self._k, self._k_to = 0.0, 1.0
        self.show()
        self.raise_()
        self.setFocus()
        self._timer.start()

    def close_edit(self):
        """Блоки возвращаются к обычному размеру, потом на их место встают настоящие."""
        if not self.isVisible() or self._k_to == 0.0:
            return
        self._k_to = 0.0
        if ph.duration(200) <= 0:
            self._finish_close()

    def _finish_close(self):
        self._timer.stop()
        self.hide()
        lay = self.lay
        for it in lay.left_items:
            lay.block_widget(it).show()
        lay.relayout()
        lay.save_left()

    def refresh(self):
        """После перестановки/удаления/добавления/смены размера: новые цели; блоку нового размера — снимок."""
        lay = self.lay
        lay.relayout(editing=True)
        alive = {id(it) for it in lay.left_items}
        for k in list(self._snaps):
            if k not in alive:
                self._snaps.pop(k, None)
                self._cur.pop(k, None)
        for it in lay.left_items:
            w = lay.block_widget(it)
            tgt = lay.left_rects.get(id(it))
            if tgt is None:
                continue
            snap = self._snaps.get(id(it))
            want = tgt.size() * w.devicePixelRatioF()
            if snap is None or abs(snap.width() - want.width()) > 2 or abs(snap.height() - want.height()) > 2:
                w.setGeometry(tgt)                              # снимок в новом размере
                lay_ = w.layout()
                if lay_ is not None:
                    lay_.activate()
                if hasattr(w, "_invalidate"):
                    w._invalidate()
                self._snaps[id(it)] = w.grab()
                w.hide()
            if id(it) not in self._cur:                        # новый — вырастает из середины
                r = QRectF(tgt)
                self._cur[id(it)] = r.adjusted(r.width() * .2, r.height() * .2, -r.width() * .2, -r.height() * .2)

    def _frame(self):
        now = time.monotonic()
        dt = min(.05, now - self._last)
        self._last = now
        a = 1.0 - math.exp(-dt / .07)
        self._k += (self._k_to - self._k) * (1.0 - math.exp(-dt / .06))
        if self._k_to == 0.0 and self._k < .02:
            self._finish_close()
            return
        for it in self.lay.left_items:
            tgt = self.lay.left_rects.get(id(it))
            cur = self._cur.get(id(it))
            if tgt is None or cur is None:
                continue
            t = QRectF(tgt)
            self._cur[id(it)] = QRectF(cur.x() + (t.x() - cur.x()) * a, cur.y() + (t.y() - cur.y()) * a,
                                       cur.width() + (t.width() - cur.width()) * a,
                                       cur.height() + (t.height() - cur.height()) * a)
        self._dying = [d for d in self._dying if now - d[2] < .26]
        self.update(self.lay.left_area().adjusted(-ph.px(24), -ph.px(24), ph.px(24), ph.px(48)))

    def _spring(self, act, it) -> float:
        """Масштаб нажатой кнопки: быстро вниз, пружиной обратно."""
        pr = self._press
        if pr is None or pr[0] != act or pr[1] is not it:
            return 1.0
        el = time.monotonic() - pr[2]
        if el > .35:
            return 1.0
        return 1.0 - .22 * math.exp(-el / .07) * math.cos(el * 18)

    # ── отрисовка ── #
    def paintEvent(self, e):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            self._hits = []
            now = time.monotonic()
            t = now - self._t0
            k = max(0.0, min(1.0, self._k))
            for pm, r, t0 in self._dying:                      # убранные: сжимаются и гаснут
                el = (now - t0) / .26
                s = 1.0 - .35 * el
                p.save()
                p.setOpacity(max(0.0, 1.0 - el))
                c = r.center()
                p.translate(c)
                p.scale(s, s)
                p.translate(-c)
                p.drawPixmap(r, pm, QRectF(pm.rect()))
                p.restore()
            items = self.lay.left_items
            for i, it in enumerate(items):
                r = self._cur.get(id(it))
                pm = self._snaps.get(id(it))
                if r is None or pm is None:
                    continue
                ph_ = (i * 1.7) % 6.28
                ang = math.sin(t * 2 * math.pi * 2.1 + ph_) * 0.9 * k    # чуть-чуть, как иконки на iPhone
                dy = math.sin(t * 2 * math.pi * 1.7 + ph_ * 1.3) * .6 * k
                sc = 1.0 - .035 * k
                p.save()
                c = r.center()
                p.translate(c.x(), c.y() + dy)
                p.rotate(ang)
                p.scale(sc, sc)
                p.translate(-c.x(), -c.y())
                ph.paint_shadow(p, r, "card", float(ph.px(18)))
                p.drawPixmap(r, pm, QRectF(pm.rect()))
                p.setOpacity(k)
                xr = QRectF(r.left() - ph.px(7), r.top() - ph.px(7), ph.px(24), ph.px(24))
                self._button(p, xr, "x", True, self._spring("remove", it))
                bs = ph.px(26)
                ur = QRectF(r.right() - 2 * bs - ph.px(14), r.top() + ph.px(10), bs, bs)
                dr = QRectF(r.right() - bs - ph.px(10), r.top() + ph.px(10), bs, bs)
                up_ok, dn_ok = i > 0, i < len(items) - 1
                self._button(p, ur, "chevron-up", up_ok, self._spring("up", it))
                self._button(p, dr, "chevron-down", dn_ok, self._spring("down", it))
                grow = self.lay.next_size(it) == "full"           # следующий размер: крупнее или мельче
                sr = QRectF(r.right() - bs - ph.px(10), r.bottom() - bs - ph.px(10), bs, bs)
                self._button(p, sr, "maximize-2" if grow else "minimize-2", True, self._spring("size", it))
                hr_ = None                                        # высота: авто → 1 клетка → 2 клетки
                if self.lay.has_height(it):
                    hr_ = QRectF(r.right() - bs * 2.6 - ph.px(16), r.bottom() - bs - ph.px(10), bs * 1.6, bs)
                    self._hbutton(p, hr_, self.lay.block_height(it), self._spring("height", it))
                lr = None                                         # один в ряду ↔ рядом с соседом
                if self.lay.block_size(it) != "full":
                    lr = QRectF(r.left() + ph.px(10), r.bottom() - bs - ph.px(10), bs, bs)
                    self._button(p, lr, "panel-left", True, self._spring("solo", it), self.lay.is_solo(it))
                p.restore()
                if k > .5:
                    self._hits.append((xr, "remove", it))
                    if up_ok:
                        self._hits.append((ur, "up", it))
                    if dn_ok:
                        self._hits.append((dr, "down", it))
                    if sr is not None:
                        self._hits.append((sr, "size", it))
                    if lr is not None:
                        self._hits.append((lr, "solo", it))
                    if hr_ is not None:
                        self._hits.append((hr_, "height", it))
            area = self.lay.left_area()                           # внизу: «Добавить» и «Готово»
            f = ph.font(ph.TEXT_XS, 600)
            p.setFont(f)
            fm = QFontMetrics(f)
            h = ph.px(30)
            y = self.height() - ph.px(34) + (ph.px(34) - h) / 2 - ph.px(2) + (1.0 - k) * ph.px(16)
            labels = (("+  Добавить", "add"), ("Готово", "done"))
            ws = [fm.horizontalAdvance(t_) + ph.px(28) for t_, _a in labels]
            x = area.center().x() - (sum(ws) + ph.px(10)) / 2
            p.setOpacity(k)
            for (text, act), w in zip(labels, ws):
                rr = QRectF(x, y, w, h)
                s = self._spring(act, None)
                hov = self._hover == act
                p.save()
                c = rr.center()
                p.translate(c)
                p.scale(s, s)
                p.translate(-c)
                primary = act == "done"
                p.setPen(QPen(ph.qcolor(ph.LINE_2 if not hov else ph.LINE_3), 1.0) if not primary else Qt.PenStyle.NoPen)
                p.setBrush(ph.white(1.0 if hov else .92) if primary else QColor(30, 30, 30, 230) if hov
                           else QColor(20, 20, 20, 200))
                p.drawRoundedRect(rr, h / 2, h / 2)
                p.setPen(QColor(10, 10, 10) if primary else ph.qcolor(ph.TEXT_PRIMARY))
                p.drawText(rr, Qt.AlignmentFlag.AlignCenter, text)
                p.restore()
                if k > .5:
                    self._hits.append((rr, act, None))
                x += w + ph.px(10)
        finally:
            p.end()

    def _hbutton(self, p: QPainter, r: QRectF, h: str, scale: float = 1.0):
        """Кнопка высоты: ↕ и «1» / «2» (белая — высота задана) или «авто» (тёмная — растянуть до низа)."""
        p.save()
        c = r.center()
        p.translate(c)
        p.scale(scale, scale)
        p.translate(-c)
        on = h != "auto"
        p.setPen(QPen(ph.white(.18), 1.0))
        p.setBrush(ph.white(.92) if on else QColor(28, 28, 28, 235))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        col = QColor(12, 12, 12) if on else ph.qcolor(ph.TEXT_PRIMARY)
        s = int(r.height() * .5)
        pm = ph.icon_pixmap("move-vertical", s, col, 2.2)
        p.drawPixmap(QRectF(r.left() + r.height() * .3, c.y() - s / 2, s, s), pm, QRectF(pm.rect()))
        p.setPen(col)
        p.setFont(ph.font(ph.TEXT_2XS if on else 8, 700))
        p.drawText(QRectF(r.left() + r.height() * .3 + s, r.top(), r.width() - r.height() * .3 - s - ph.px(4),
                          r.height()), Qt.AlignmentFlag.AlignCenter, h if on else "авто")
        p.restore()

    def _button(self, p: QPainter, r: QRectF, icon: str, enabled: bool = True, scale: float = 1.0,
                active: bool = False):
        """Круглая кнопка правки; active — включённый переключатель (белая)."""
        p.save()
        c = r.center()
        p.translate(c)
        p.scale(scale, scale)
        p.translate(-c)
        p.setPen(QPen(ph.white(.18), 1.0))
        p.setBrush(ph.white(.92) if active else QColor(28, 28, 28, 235) if enabled else QColor(28, 28, 28, 120))
        p.drawEllipse(r)
        s = int(r.width() * .56)
        pm = ph.icon_pixmap(icon, s, QColor(12, 12, 12) if active else ph.TEXT_PRIMARY if enabled else ph.TEXT_GHOST,
                            2.2)
        p.drawPixmap(QRectF(r.center().x() - s / 2, r.center().y() - s / 2, s, s), pm, QRectF(pm.rect()))
        p.restore()

    # ── мышь и клавиши ── #
    def _hit(self, pos):
        for r, act, it in reversed(self._hits):
            if r.adjusted(-3, -3, 3, 3).contains(pos):
                return act, it
        return None, None

    def mouseMoveEvent(self, e):
        act, _it = self._hit(e.position())
        self._hover = act if act in ("add", "done") else None
        self.setCursor(Qt.CursorShape.PointingHandCursor if act else Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, e):
        act, it = self._hit(e.position())
        if act is not None:
            self._press = (act, it, time.monotonic())
            self._act(act, it)
            return
        for it in self.lay.left_items:                         # по блоку — ничего; мимо — выйти из правки
            r = self._cur.get(id(it))
            if r is not None and r.contains(e.position()):
                return
        self.close_edit()

    def _act(self, act, it):
        lay = self.lay
        if act == "done":
            self.close_edit()
        elif act == "add":
            QTimer.singleShot(90, self._add_menu)              # сначала пружинка кнопки
        elif act in ("up", "down"):
            lay.move_block(it, -1 if act == "up" else 1)
            self.refresh()
        elif act == "size":
            lay.set_block_size(it, lay.next_size(it))
            self.refresh()
        elif act == "solo":
            lay.set_solo(it, not lay.is_solo(it))
            self.refresh()
        elif act == "height":
            lay.set_block_height(it, lay.next_height(it))
            self.refresh()
        elif act == "remove":
            r, pm = self._cur.get(id(it)), self._snaps.get(id(it))
            if r is not None and pm is not None:
                self._dying.append((pm, QRectF(r), time.monotonic()))
            lay.remove_block(it)
            self.refresh()

    def _add_menu(self):
        from PyQt6.QtWidgets import QMenu
        import ph_cards
        lay = self.lay
        m = QMenu(self)
        if "cover" not in lay.left_items:
            m.addAction(ph.icon("image", 14), "Обложка").triggered.connect(lambda: self._add("cover"))
        if "player" not in lay.left_items:
            m.addAction(ph.icon("play", 14), "Плеер").triggered.connect(lambda: self._add("player"))
        if len(lay.widgets) < 6:
            sub = m.addMenu("Виджет")
            for k, _kick, sub_t in ph_cards.KINDS:
                sub.addAction(f"{sub_t}").triggered.connect(lambda _=False, kk=k: self._add(kk))
        if m.isEmpty():
            m.addAction("Больше добавить нечего").setEnabled(False)
        m.exec(QCursor.pos())

    def _add(self, what):
        self.lay.add_block(what)
        self.refresh()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.close_edit()
            return
        super().keyPressEvent(e)


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
        import ph_panels
        self.phs = ph_panels.ph_settings(win)
        ph.configure(card_opacity=self.phs["card_opacity"], ui_scale=self.phs["ui_scale"],
                     effects=self.phs["effects"], motion=self.phs["motion"])
        self.ready = False
        self._panels: dict = {}
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
        self.cover = PhCoverCard(self, self.host)
        self.player = PhPlayerCard(self, self.host)
        self.left_items: list = []                             # левая колонка сверху вниз: "cover", "player", карточки
        self.left_rects: dict = {}
        self.widgets: list = []
        self._build_left()
        self.right = PhRightColumn(self, self.host)
        self.edit = PhEditLayer(self, self.root)               # правка колонки (зажать колёсико мыши)
        self._hold = QTimer(self)
        self._hold.setSingleShot(True)
        self._hold.setInterval(450)
        self._hold.timeout.connect(self.toggle_edit)
        QApplication.instance().installEventFilter(self)
        import ph_motion                                       # подсветка и «волна» нажатия у всех кнопок
        ph_motion.install(win)
        self.overlay = PhOverlay(self, self.root)
        self.overlay.set_content(shell.stack)
        self.overlay.closed.connect(self._overlay_closed)
        shell._badge_on(self.top.b_net)                        # непрочитанное Echoes.NET — на кнопке сети
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
        self.apply_appearance(None)
        self.root.show()
        import inapp                                           # окна из настроек — страницей внутри панели
        inapp.EMBED = self._embed_host

    # ── настройки Phantom (ph_panels) ── #
    def apply_appearance(self, keys):
        """Применить настройки Phantom (keys — что поменялось; None — всё)."""
        import ph_panels
        s = self.phs = ph_panels.ph_settings(self.win)
        every = keys is None
        keys = set(keys or ())
        if every or keys & {"card_opacity", "effects", "motion"}:
            ph.configure(card_opacity=s["card_opacity"], effects=s["effects"], motion=s["motion"])
            if not every:
                self.root.setStyleSheet(ph.qss())
                self.host.update()
        if every or keys & {"bg_intensity", "bg_animation", "bg_brightness", "bg_image", "effects", "motion"}:
            img = s["bg_image"] if s["bg_image"] and Path(s["bg_image"]).exists() else                 (str(ph_backdrop.DEFAULT_IMAGE) if ph_backdrop.DEFAULT_IMAGE.exists() else None)
            self.bg.configure(intensity=s["bg_intensity"], brightness=s["bg_brightness"],
                              animated=s["bg_animation"], image=img if (every or "bg_image" in keys) else ...)
            if "effects" in keys:
                self.bg._rebuild_static()
        if every or "cover_treatment" in keys:
            self.cover.set_treatment(s["cover_treatment"])
        if every or "cover_style" in keys:
            self.cover.set_style(s.get("cover_style", "info"))
        if every or keys & {"cover_video", "cover_video_path", "cover_rules"}:
            self.refresh_cover_media()          # своя обложка по правилам (и прежнее «видео вместо обложки»)
        if not every and keys & {"lyrics_scale", "lyrics_blur", "lyrics_words", "lyrics_autoscroll"}:
            self.shell._lyr_src = None
            try:
                self.shell._lyrics_tick(None, None)
            except Exception as e:                             # noqa: BLE001
                print("[ph] lyrics:", e)

    def rebuild(self):
        """Пересобрать оболочку (масштаб интерфейса, сброс раздела) — музыка не прерывается."""
        import ya_skin
        QTimer.singleShot(0, lambda: ya_skin.reskin(self.win))

    def page_widget(self, key: str):
        """Панель Phantom вместо страницы Echoes (Библиотека, Очередь, Настройки) или None."""
        import ph_panels
        cls = {"collection": ph_panels.PhLibraryPanel, "queue": ph_panels.PhQueuePanel}.get(key)
        # настройки — одна страница Echoes (SettingsHub) с разделами Phantom внутри, отдельной панели нет
        if cls is None or not self.ready:
            return None
        if key == "settings" and self.overlay.settings_tab() == "echoes":
            return None
        w = self._panels.get(key)
        if w is None:
            w = self._panels[key] = cls(self, self.shell.stack)   # сразу внутри оболочки — QSS Phantom
            self.shell.stack.addWidget(w)                          # с самого начала (иначе подписи кнопок
                                                                   # считались по чужому стилю и обрезались)
        if key == "collection":
            w.refresh_on_open()
        else:
            w.refresh(force=True)
        return w

    def refresh_library(self):
        panel = self._panels.get("collection")
        if panel is None:
            return
        panel.invalidate()
        if self.overlay_open() and self.shell.stack.currentWidget() is panel:
            import ui_anim
            ui_anim._finish(self.shell.stack)
            panel.refresh()

    # ── геометрия ── #
    def relayout(self, editing: bool = False):
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
        inner = W - 2 * g - gap
        lw = int(inner * ph.LEFT_COLUMN / (ph.LEFT_COLUMN + ph.RIGHT_COLUMN))
        if self.all_square():                                  # все виджеты 1:1 — колонка уже, текст сдвигается влево
            lw = max(ph.px(300), int(lw * self.NARROW))
        x0, y0 = g, top_h
        bottom = ph.px(36)
        avail = H - y0 - bottom
        self._left_area = QRect(x0, y0, lw, avail)
        self.left_rects = self._left_rects(x0, y0, lw, avail)
        if not editing:
            for it in self.left_items:
                r = self.left_rects.get(id(it))
                if r is not None:
                    self.block_widget(it).setGeometry(r)
        if self.edit.isVisible():
            self.edit.setGeometry(self.host.geometry())
        used = self.left_used_width(x0, lw)                   # справа в колонке пусто — текст занимает это место
        rx = x0 + used + gap
        self.right.setGeometry(rx, top_h - ph.px(2), W - rx - g, H - top_h + ph.px(2))
        # пылинки — только там, где нет стекла
        self._occlude()
        self.host.update()

    def _occlude(self):
        """Пылинки — только там, где нет стекла и текста (под ними их не видно, а каждая будила бы перерисовку
        панели текста)."""
        rects = [self.block_widget(it).geometry() for it in self.left_items]
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

    def open_shop(self):
        self._ensure_shop()
        self.shell.show_page("shop")

    def _ensure_shop(self):
        """Магазин и поддержка (ph_shop) — страница создаётся при первом открытии."""
        sh = self.shell
        if "shop" not in sh.pages:
            import ph_shop
            page = ph_shop.ShopPage(self)
            sh.pages["shop"] = page
            sh.stack.addWidget(page)

    def toggle_page(self, key: str):
        if key == "shop":
            self._ensure_shop()
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
            wide = key in ("settings", "listening")            # настройки — панелью сбоку, пошире
            self.overlay.configure("side" if wide else "drawer", kick, title, back=key == "playlist")
        elif key == "net":                                     # Echoes.NET — своя панель, без вкладок разделов
            title = "Echoes.NET"
            self.overlay.configure("wide", "Network", title)
        elif key == "shop":                                    # магазин косметики и поддержка ECHOES
            title = "Магазин"
            self.overlay.configure("wide", "Store", title)
        else:
            title = PLANET_TITLES.get(key, "Echoes")
            sub = ""
            if key == "artist":
                title = str(getattr(sh.pages.get("artist"), "name", "") or title)
            if key in {k for k, _t, _i in PLANET_MENU}:
                self.win.settings["ph_planet"] = key
            self.overlay.configure("planet", "Echoes", title, sub, menu_key=key, back=key not in PLANET_KEYS - {"artist"})
        self._hide_page_title(sh.pages.get(key), {title, PLANET_TITLES.get(key, ""), DRAWERS.get(key, ("", ""))[1],
                                                  sh.NAV_TEXT.get(key, "")})
        self.overlay.open()
        self.top.sync_checked(key)

    @staticmethod
    def _hide_page_title(page, titles: set):
        """Заголовок страницы уже в шапке панели — свой крупный заголовок страницы (тот же текст) прячется."""
        if page is None:
            return
        titles = {t.strip().lower() for t in titles if t}
        import re as _re
        for lb in page.findChildren(QLabel):
            text = _re.sub(r"<[^>]+>", "", lb.text()).strip().lower()
            big = lb.objectName() in ("YaH1", "YaHero", "YaPageTitle") or lb.font().pixelSize() >= 18
            if big and text in titles:
                if not lb.isHidden():
                    lb.hide()
                break

    def _embed_host(self, content):
        """Окно, открытое из настроек, — страницей внутри панели настроек (с «‹ Назад»), а не всплывашкой.
        Маленькие вопросы («Удалить?», «Название плейлиста») остаются всплывающими."""
        ov = self.overlay
        if not ov.is_open() or self.shell._cur_page not in ("settings", "listening"):
            return None
        hint = content.sizeHint()
        if hint.height() < 220 and hint.width() < 520:
            return None
        return ov.body

    def close_overlay(self, instant: bool = False):
        try:                                                   # страницы-окна внутри панели закрываются с ней
            import inapp
            for L in list(inapp._layers):
                if getattr(L, "host", None) is self.overlay.body:
                    L.request_close()
        except Exception as e:                                 # noqa: BLE001
            print("[ph] embedded:", e)
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
        path = str((t or {}).get("cover", "") or "")
        side = int(max(self.cover.width(), self.cover.height()) * max(1.0, self.cover.devicePixelRatioF()))
        self._cover_for = t
        self._loader.load(path, max(256, side))
        self.right.live.set_track(t, QImage())
        self.right.live.set_next((self.upcoming(1) or [None])[0])

    def refresh_cover_media(self):
        """Своя обложка для играющего трека: самое точное подходящее правило (ph_cover.resolve)."""
        import ph_cover
        t = self.__dict__.get("_cover_for")
        try:
            rule = ph_cover.resolve(self.win, t, not self.cover._img.isNull())
        except Exception as e:                                 # noqa: BLE001
            print("[ph] cover rules:", e)
            rule = None
        self.cover.set_media(rule)

    def _on_cover(self, img: QImage):
        t = self._cover_for
        self.cover.set_track(t)
        self.cover.set_image(img, _title(t) if t else "", _artist(t) if t else "")
        self.refresh_cover_media()
        self.right.live.set_track(t, img)

    def tick(self, playing: bool, pos: float, dur: float):
        self.player.tick(playing, pos, dur)
        self.cover.set_playing(playing)
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
            if self.overlay.is_open():                           # открытая панель Phantom — свежие данные
                cur = self.shell.stack.currentWidget()
                for key in ("queue", "collection"):
                    w = self._panels.get(key)
                    if w is not None and w is cur:
                        w.refresh()

    def save_widgets(self):
        self.win.settings["ph_widgets"] = [wc.widget_kind() for wc in self.widgets]

    # ── левая колонка: состав и порядок блоков (правка — PhEditLayer) ── #
    def _build_left(self):
        s = self.win.settings
        order = s.get("ph_left") or ["cover", "player", "w", "w"]
        kinds = list(s.get("ph_widgets") or ["visualizer", "clock"])
        items, sizes, solo, heights = [], {}, set(), {}
        for raw in order:
            parts = str(raw).split(":")
            name, size = parts[0], (parts[1] if len(parts) > 1 else "")
            if name in ("cover", "player"):
                if name in items:
                    continue
                it = "cover" if name == "cover" else "player"     # те же строки, что в коде (не копии из настроек)
            elif name == "w":
                it = PhWidgetCard(self, kinds.pop(0) if kinds else "clock", self.host)
            else:
                continue
            items.append(it)
            sizes[self._skey(it)] = size if size in self.SIZES else self._default_size(it)
            if "solo" in parts[2:]:
                solo.add(self._skey(it))
            for fl in parts[2:]:
                if fl in ("h1", "h2"):
                    heights[self._skey(it)] = fl[1]
        self.left_items = items
        self.left_sizes = sizes
        self.left_solo = solo
        self.left_heights = heights
        self.widgets = [x for x in items if not isinstance(x, str)]
        self.cover.setVisible("cover" in items)
        self.player.setVisible("player" in items)

    SIZES = ("full", "half", "third")                         # на всю ширину · две в ряд · квадрат 1:1, три в ряд
    NARROW = .8                                                # ширина колонки, когда все виджеты 1:1

    @staticmethod
    def _default_size(it) -> str:
        return "full" if isinstance(it, str) else "half"

    def sizes_for(self, it) -> tuple:
        """Размеры, которые можно выбрать блоку: плееру квадрат не нужен (кнопки не помещаются)."""
        return ("full", "half") if it == "player" else self.SIZES

    def next_size(self, it) -> str:
        """Кнопка размера в правке: половина → 1:1 → вся ширина → половина (плеер: половина ↔ вся ширина)."""
        order = {"half": "third", "third": "full", "full": "half"}
        nxt = order.get(self.block_size(it), "half")
        return nxt if nxt in self.sizes_for(it) else order[nxt]

    def is_solo(self, it) -> bool:
        """Блок стоит в ряду один (рядом пусто), даже если соседний — того же размера."""
        return self._skey(it) in self.__dict__.setdefault("left_solo", set())

    def set_solo(self, it, on: bool):
        solo = self.__dict__.setdefault("left_solo", set())
        (solo.add if on else solo.discard)(self._skey(it))
        self.save_left()

    def has_height(self, it) -> bool:
        """Высоту в клетках выбирают только виджетам «половина» и «вся ширина» (квадрат 1:1 — всегда квадрат)."""
        return not isinstance(it, str) and self.block_size(it) in ("half", "full")

    def block_height(self, it) -> str:
        """auto — растянуть и заполнить колонку (как раньше); "1" / "2" — ровно одна / две клетки, рядом пусто."""
        if not self.has_height(it):
            return "auto"
        return self.__dict__.setdefault("left_heights", {}).get(self._skey(it), "auto")

    def next_height(self, it) -> str:
        return {"auto": "1", "1": "2", "2": "auto"}[self.block_height(it)]

    def set_block_height(self, it, h: str):
        hs = self.__dict__.setdefault("left_heights", {})
        if h in ("1", "2"):
            hs[self._skey(it)] = h
        else:
            hs.pop(self._skey(it), None)
        self.save_left()

    def left_used_width(self, x0: int, lw: int) -> int:
        """Сколько ширины колонки занято блоками: если ни один ряд не доходит до правого края (все блоки —
        половины или квадраты поодиночке), текст справа сдвигается к самому широкому ряду."""
        rights = [r.right() for r in self.left_rects.values()]
        if not rights:
            return lw
        return max(ph.px(120), min(lw, max(rights) - x0 + 1))

    def all_square(self) -> bool:
        """Все виджеты слева — квадраты 1:1 (тогда колонка уже, а текст справа шире)."""
        ws = [x for x in self.left_items if not isinstance(x, str)]
        return bool(ws) and all(self.block_size(x) == "third" for x in ws)

    @staticmethod
    def _skey(it):
        return it if isinstance(it, str) else id(it)

    def block_size(self, it) -> str:
        return self.__dict__.setdefault("left_sizes", {}).get(self._skey(it)) or self._default_size(it)

    def set_block_size(self, it, size: str):
        self.left_sizes[self._skey(it)] = size if size in self.sizes_for(it) else "full"
        self.save_left()

    def save_left(self):
        out = []
        for x in self.left_items:
            name = x if isinstance(x, str) else "w"
            size = self.block_size(x)
            flags = []
            if self.is_solo(x) and size != "full":
                flags.append("solo")
            if self.block_height(x) != "auto":
                flags.append("h" + self.block_height(x))
            if flags:
                out.append(":".join([name, size] + flags))
            else:
                out.append(name if size == self._default_size(x) else f"{name}:{size}")
        self.win.settings["ph_left"] = out
        self.save_widgets()

    def block_widget(self, it) -> QWidget:
        return self.cover if it == "cover" else self.player if it == "player" else it

    def left_area(self) -> QRect:
        return QRect(self.__dict__.get("_left_area") or QRect())

    def _left_rows(self):
        """Блоки по рядам: «на всю ширину» — по ряду; «половина» подряд — по два в ряд; 1:1 подряд — по три;
        блок «один в ряду» ни к кому не подсаживается и к себе не пускает."""
        rows = []
        per = {"half": 2, "third": 3}
        for it in self.left_items:
            sz = self.block_size(it)
            if sz != "full" and rows and self.block_size(rows[-1][0]) == sz and len(rows[-1]) < per[sz] \
                    and not self.is_solo(it) and not self.is_solo(rows[-1][0]):
                rows[-1].append(it)
            else:
                rows.append([it])
        return rows

    def _left_rects(self, x0, y0, lw, avail) -> dict:
        rows = self._left_rows()
        if not rows:
            return {}
        cgap = ph.px(18)
        card_h = ph.px(186)
        half_w = (lw - cgap) // 2
        third_w = (lw - 2 * cgap) // 3

        def kind(row):
            if self.block_size(row[0]) == "third":
                return "third"                                 # квадраты 1:1 — высота ряда = ширина клетки
            if "player" in row:
                return "player"
            if "cover" in row:
                return "cover" if self.block_size("cover") == "full" else "square"
            return "w"
        kinds = [kind(r) for r in rows]
        cell = max(ph.px(130), min(ph.px(210), int(avail * .27)))   # одна клетка виджета по высоте

        def fixed_cells(row) -> int:
            """Ряд виджетов с заданной высотой: сколько клеток (0 — растягивается, как раньше)."""
            hs = [self.block_height(it) for it in row]
            return max((int(h) for h in hs if h != "auto"), default=0)
        cells = [fixed_cells(r) if k == "w" else 0 for r, k in zip(rows, kinds)]

        nw = sum(1 for k, c in zip(kinds, cells) if k == "w" and not c)
        if any(cells):                                         # заданные высоты не помещаются — клетки меньше
            budget = avail - card_h * kinds.count("player") - half_w * kinds.count("square") -                 third_w * kinds.count("third") - cgap * (len(rows) - 1) - sum(cgap * (c - 1) for c in cells if c) -                 (ph.px(120) if "cover" in kinds else 0) - ph.px(96) * nw
            cell = max(ph.px(70), min(cell, budget // sum(cells)))

        def cells_h(n: int) -> int:
            return cell * n + cgap * (n - 1)
        wid_h = cell
        fixed = card_h * kinds.count("player") + half_w * kinds.count("square") + \
            third_w * kinds.count("third") + sum(cells_h(c) for c in cells if c) + cgap * (len(rows) - 1)
        cov_h = 0
        if "cover" in kinds:
            cov_h = max(ph.px(120), min(int(lw * .72), avail - fixed - wid_h * nw))
        rest = avail - fixed - cov_h - wid_h * nw
        if nw:
            if rest > 0:
                wid_h = min(ph.px(260), wid_h + rest // nw)
            else:
                wid_h = max(ph.px(96), wid_h + rest // nw)
        last_auto = max((i for i, (k, c) in enumerate(zip(kinds, cells)) if k == "w" and not c), default=-1)
        out, y = {}, y0
        for i, (row, k) in enumerate(zip(rows, kinds)):
            h = {"cover": cov_h, "player": card_h, "square": half_w, "third": third_w}.get(k, wid_h)
            if cells[i]:
                h = cells_h(cells[i])
            elif i == last_auto and i == len(rows) - 1:         # последний ряд виджетов — до низа колонки
                h = max(h, y0 + avail - y)

            def own_h(it, h=h):                                # виджет в одну клетку в ряду из двух — сверху,
                bh = self.block_height(it)                     # под ним пусто
                return cells_h(int(bh)) if bh != "auto" and cells[i] else h
            sz = self.block_size(row[0])
            if sz == "full":
                out[id(row[0])] = QRect(x0, y, lw, own_h(row[0]))
            else:
                n = 2 if sz == "half" else 3
                cw = half_w if n == 2 else third_w
                for j, it in enumerate(row):                   # последняя клетка полного ряда — до края колонки
                    w = lw - j * (cw + cgap) if j == n - 1 else cw
                    out[id(it)] = QRect(x0 + j * (cw + cgap), y, w, own_h(it))
            y += h + cgap
        return out

    def move_block(self, it, d: int):
        i = self.left_items.index(it)
        j = i + d
        if 0 <= j < len(self.left_items):
            self.left_items[i], self.left_items[j] = self.left_items[j], self.left_items[i]
            self.widgets = [x for x in self.left_items if not isinstance(x, str)]
            self.save_left()

    def remove_block(self, it):
        if it not in self.left_items:
            return
        self.left_items.remove(it)
        self.__dict__.setdefault("left_solo", set()).discard(self._skey(it))
        self.__dict__.setdefault("left_heights", {}).pop(self._skey(it), None)
        w = self.block_widget(it)
        w.hide()
        if not isinstance(it, str):
            self.widgets = [x for x in self.left_items if not isinstance(x, str)]
            w.deleteLater()
        self.save_left()

    def add_block(self, what: str):
        """what: "cover" | "player" | вид виджета. Обложка — наверх, плеер — под ней, виджет — вниз."""
        if what in ("cover", "player"):
            if what in self.left_items:
                return what
            it = what
            pos = 0 if what == "cover" else (1 if "cover" in self.left_items[:1] else 0)
            self.left_items.insert(pos, it)
            self.left_sizes[self._skey(it)] = "full"
        else:
            it = PhWidgetCard(self, what, self.host)
            self.left_items.append(it)
            self.left_sizes[self._skey(it)] = "half"
            self.widgets = [x for x in self.left_items if not isinstance(x, str)]
        if not self.edit.isVisible():
            self.block_widget(it).show()
            self.relayout()
        self.save_left()
        return it

    def toggle_edit(self):
        if self.edit.isVisible():
            self.edit.close_edit()
        elif not self.overlay.isVisible():
            self.relayout()
            self.edit.open()

    def eventFilter(self, obj, ev):
        """Зажатое колёсико мыши над левой колонкой — режим правки (или выход из него)."""
        t = ev.type()
        if t == QEvent.Type.MouseButtonPress and ev.button() == Qt.MouseButton.MiddleButton:
            if isinstance(obj, QWidget) and obj.window() is self.win and not self.overlay.isVisible():
                lp = self.host.mapFromGlobal(ev.globalPosition().toPoint())
                m = ph.px(10)
                if self.left_area().adjusted(-m, -m, m, m).contains(lp):
                    self._hold.start()
        elif t == QEvent.Type.MouseButtonRelease and ev.button() == Qt.MouseButton.MiddleButton:
            self._hold.stop()
        return False

    def shutdown(self):
        import inapp
        if getattr(inapp, "EMBED", None) == self._embed_host:
            inapp.EMBED = None
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
