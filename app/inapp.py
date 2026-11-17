# inapp.py
"""
Окна внутри приложения. Всё, что раньше открывалось отдельными окнами (импорт из Spotify,
загрузчик, редактор тегов и текста, выбор треков, вопросы «Название плейлиста», «Удалить?»,
профиль, очередь…), показывается слоем ПОВЕРХ главного окна: затемнение + карточка по центру.

Как это работает:
  • Layer          — слой-карточка: заголовок, кнопка «×», содержимое (прокручивается, если окно мало);
  • present()      — показать готовый QDialog внутри приложения (без блокировки);
  • QDialog.exec() — подменяется: модальные диалоги главного окна открываются слоем и ждут ответа
                     во вложенном цикле событий, как и раньше (код вызывающих не меняется);
  • QInputDialog.getText и QMessageBox.question/information/warning/critical — тоже слоем;
  • системные окна выбора файлов/папок остаются системными (их встроить нельзя).
Включается/выключается set_enabled() (настройка «Окна внутри приложения»).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QEvent, QEventLoop, QObject, QSize, QRect, QPointF
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor, QPainter, QPixmap, QIcon, QPen
from PyQt6.QtWidgets import (QApplication, QDialog, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel,
                             QLineEdit, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
                             QColorDialog, QFontDialog)

_main = None                  # главное окно
_enabled = False
_orig = {}                    # оригинальные функции Qt
_layers: list = []            # открытые слои (стек)

_SKIP = (QFileDialog, QMessageBox, QColorDialog, QFontDialog)
# Хозяин встраивания: fn(content) → виджет, внутри которого показать окно страницей (вид Phantom: открытые
# настройки), или None — показать как обычно, слоем поверх окна. Ставит ph_shell, снимает при выходе из вида.
EMBED = None


def _win_of(widget):
    if _main is None or widget is None:
        return None
    try:
        return _main if widget.window() is _main else None
    except RuntimeError:
        return None


def _window_icon(restore=False):
    pm = QPixmap(36, 36)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(2)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor("#e0e5ec"), 1.2))
    if restore:
        p.drawRect(6, 3, 9, 9)
        p.fillRect(3, 6, 9, 9, QColor("#0b0d10"))
        p.drawRect(3, 6, 9, 9)
    else:
        p.drawRect(3, 3, 12, 12)
        p.drawLine(3, 6, 15, 6)
    p.end()
    return QIcon(pm)


class _LayerGrip(QWidget):
    """Resize the in-app card, never the application's top-level window."""
    def __init__(self, layer):
        super().__init__(layer.card)
        self.layer = layer
        self.start = None
        self.setFixedSize(22, 22)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setToolTip("Потяните, чтобы изменить размер")

    def paintEvent(self, _):
        p = QPainter(self)
        p.setPen(QPen(QColor(220, 231, 246, 110), 1.2))
        for x in (7, 12, 17):
            p.drawLine(QPointF(x, 18), QPointF(18, x))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.start = (e.globalPosition().toPoint(), QRect(self.layer.card.geometry()))
            e.accept()

    def mouseMoveEvent(self, e):
        if self.start is not None:
            delta = e.globalPosition().toPoint() - self.start[0]
            r = QRect(self.start[1])
            r.setSize(QSize(max(280, r.width() + delta.x()), max(180, r.height() + delta.y())))
            self.layer._set_card_geometry(r)

    def mouseReleaseEvent(self, e):
        self.start = None
        e.accept()


class Layer(QWidget):
    """Слой поверх главного окна с карточкой по центру."""

    def __init__(self, win, content: QWidget, title: str = "", modal=False):
        host = None
        if EMBED is not None:
            try:
                host = EMBED(content)
            except Exception as e:                  # noqa: BLE001
                print("[inapp] embed:", e)
        self.host = host                            # страница внутри панели (вид Phantom) или None — слой поверх
        super().__init__(host or win)
        self.win, self.content, self.modal = win, content, modal
        self._orig_parent = content.parentWidget()
        self._orig_flags = content.windowFlags()
        self._closing = False
        self._manual_geometry = None
        self._maximized = False
        self._drag = None
        # страховка: окно внутри закрылось/удалилось, а слой остался — он бы забирал все клики по ECHOES
        self._orphan = QTimer(self)
        self._orphan.setInterval(1000)
        self._orphan.timeout.connect(self._check_orphan)
        self._orphan.start()
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, host is None)
        self._backdrop = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        try:                                        # карточка — «жидкое стекло», как главный экран и плеер
            if host is not None:
                raise RuntimeError("страница внутри панели — без своей карточки")
            from echo_glass import GlassFrame
            self.card = GlassFrame(self, 18)
        except Exception:                           # noqa: BLE001
            self.card = QFrame(self)
        self.card.setObjectName("InAppCard")
        self.card.setStyleSheet("QFrame#InAppCard{background:transparent;border:none;border-radius:18px;}"
                                "QLabel#InAppTitle{background:transparent;color:#ffffff;font-size:15px;font-weight:800;}"
                                "QPushButton#InAppClose{background:transparent;border:none;color:#cfcfcf;"
                                "font-size:22px;border-radius:15px;padding:0;}"
                                "QPushButton#InAppClose:hover{background:rgba(255,255,255,0.12);color:#fff;}")
        v = QVBoxLayout(self.card)
        v.setContentsMargins(16, 12, 16, 16)
        v.setSpacing(10)
        head = QHBoxLayout()
        self.title = QLabel(title or "")
        self.title.setObjectName("InAppTitle")
        self.title.installEventFilter(self)
        self.title.setToolTip("Перетащите окно; двойной щелчок — развернуть")
        head.addWidget(self.title, 1)
        self.btn_maximize = QPushButton()
        self.btn_maximize.setObjectName("InAppClose")
        self.btn_maximize.setIcon(_window_icon())
        self.btn_maximize.setFixedSize(30, 30)
        self.btn_maximize.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_maximize.setToolTip("Развернуть / восстановить окно")
        self.btn_maximize.clicked.connect(self.toggle_maximized)
        head.addWidget(self.btn_maximize)
        self.btn_close = QPushButton("×")
        self.btn_close.setObjectName("InAppClose")
        self.btn_close.setFixedSize(30, 30)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setToolTip("Закрыть")
        self.btn_close.clicked.connect(self.request_close)
        head.addWidget(self.btn_close)
        if host is not None:                        # страница: «‹ Назад» слева, без «развернуть» и «×»
            self.btn_maximize.hide()
            self.btn_close.hide()
            self.btn_back = QPushButton("  Назад")
            self.btn_back.setObjectName("InAppBack")
            self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_back.setToolTip("Вернуться к настройкам")
            try:
                import ph_style
                self.btn_back.setIcon(ph_style.icon("chevron-left", 14, ph_style.TEXT_PRIMARY))
                ph_style.set_font(self.btn_back, ph_style.font(ph_style.TEXT_SM, 550))
                ph_style.set_font(self.title, ph_style.font(ph_style.TEXT_LG, 650, -.015))
            except Exception:                       # noqa: BLE001
                pass
            self.btn_back.clicked.connect(self.request_close)
            head.insertWidget(0, self.btn_back)
            head.insertSpacing(1, 6)
            v.setContentsMargins(0, 0, 0, 0)
        v.addLayout(head)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;}")
        v.addWidget(self.scroll, 1)
        self.grip = _LayerGrip(self)
        self.card.installEventFilter(self)

        content.setWindowFlags(Qt.WindowType.Widget)
        self.scroll.setWidget(content)
        content.show()
        win.installEventFilter(self)
        if host is not None:
            host.installEventFilter(self)
        content.installEventFilter(self)
        _layers.append(self)
        self._relayout()
        # The blocked page behind the dialog need not be composited on every
        # mouse move. Keep its appearance while moving/resizing the glass card.
        self._backdrop = win.grab(self._area()) if host is None else None
        self.show()
        self.raise_()
        QTimer.singleShot(0, lambda: (content.focusWidget() or content).setFocus())

    # ── размеры ── #

    def _area(self):
        if self.host is not None:
            return self.host.rect()
        cw = self.win.centralWidget()
        r = cw.geometry() if cw is not None else self.win.rect()
        return r

    def _relayout(self):
        r = self._area()
        self.setGeometry(r)
        if self.host is not None:                   # страница — во всю панель
            self.card.setGeometry(self.rect())
            self.grip.hide()
            return
        if self._maximized:
            self.card.setGeometry(self.rect().adjusted(6, 6, -6, -6))
            self._place_grip()
            return
        if self._manual_geometry is not None:
            self._set_card_geometry(self._manual_geometry)
            return
        c = self.content
        want = c.sizeHint().expandedTo(c.minimumSizeHint()).expandedTo(c.minimumSize())
        w = min(max(380, want.width() + 40), max(1, int(r.width() * 0.94)))
        h = min(max(200, want.height() + 90), max(1, int(r.height() * 0.94)))
        self.card.setGeometry((r.width() - w) // 2, (r.height() - h) // 2, w, h)
        self._place_grip()

    def _place_grip(self):
        self.grip.move(self.card.width() - 25, self.card.height() - 25)
        self.grip.setVisible(not self._maximized)
        self.grip.raise_()

    def _set_card_geometry(self, rect):
        r = QRect(rect)
        w = min(max(280, r.width()), max(1, self.width() - 12))
        h = min(max(180, r.height()), max(1, self.height() - 12))
        x = max(6, min(r.x(), self.width() - w - 6))
        y = max(6, min(r.y(), self.height() - h - 6))
        self._manual_geometry = QRect(x, y, w, h)
        self.card.setGeometry(self._manual_geometry)
        self._place_grip()

    def toggle_maximized(self):
        self._maximized = not self._maximized
        self.btn_maximize.setIcon(_window_icon(self._maximized))
        self._relayout()

    def eventFilter(self, obj, ev):
        t = ev.type()
        if (obj is self.win or (self.host is not None and obj is self.host)) and                 t in (QEvent.Type.Resize, QEvent.Type.Move):
            self._relayout()
        elif obj is self.card and t == QEvent.Type.Resize:
            self._place_grip()
        elif obj is self.title and self.host is None:
            if t == QEvent.Type.MouseButtonDblClick and ev.button() == Qt.MouseButton.LeftButton:
                self.toggle_maximized()
                return True
            if t == QEvent.Type.MouseButtonPress and ev.button() == Qt.MouseButton.LeftButton and not self._maximized:
                self._drag = (ev.globalPosition().toPoint(), QRect(self.card.geometry()))
                return True
            if t == QEvent.Type.MouseMove and self._drag is not None:
                delta = ev.globalPosition().toPoint() - self._drag[0]
                self._set_card_geometry(self._drag[1].translated(delta))
                return True
            if t == QEvent.Type.MouseButtonRelease:
                self._drag = None
        elif obj is self.content and t == QEvent.Type.Hide and not self._closing:
            # диалог сам закрылся (кнопка «Закрыть», accept, reject…). Не прямо здесь: Qt ещё внутри скрытия
            # окна, а _finish переподвешивает его к другому родителю — так «Конструктор стримера» ронял
            # ECHOES при закрытии (access violation)
            QTimer.singleShot(0, self._finish)
        return False

    # ── ввод/рисование ── #

    def paintEvent(self, _):
        if self.host is not None:                   # страница внутри стеклянной панели — фон у панели
            return
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(12, 13, 16))
        if self._backdrop is not None:
            p.drawPixmap(self.rect(), self._backdrop)
        p.fillRect(self.rect(), QColor(0, 0, 0, 165))
        p.end()

    def mousePressEvent(self, e):
        e.accept()                                  # клики мимо карточки не доходят до окна под слоем

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.request_close()
            e.accept()
        else:
            super().keyPressEvent(e)

    # ── закрытие ── #

    def request_close(self):
        c = self.content
        if isinstance(c, QDialog):
            c.reject() if self.modal else c.hide()
        else:
            c.hide()
        # не прямо здесь: мы внутри reject()/hide() диалога, а _finish переподвешивает его к другому
        # родителю — так ECHOES и падал (access violation в журнале: inapp._finish ← request_close)
        QTimer.singleShot(0, self._finish)

    def _check_orphan(self):
        if self._closing:
            return
        try:
            from PyQt6 import sip
            gone = sip.isdeleted(self.content) or (self.isVisible() and not self.content.isVisible())
        except RuntimeError:
            gone = True
        if gone:
            print("[inapp] слой без окна — убираю")
            self._finish()

    def _finish(self):
        if self._closing:
            return
        self._closing = True
        try:
            self.win.removeEventFilter(self)
            self.content.removeEventFilter(self)
            if self.host is not None:
                self.host.removeEventFilter(self)
        except RuntimeError:
            pass
        try:
            from PyQt6 import sip
            if not sip.isdeleted(self.content):                # диалог мог уже удалить себя (finished → deleteLater)
                self.scroll.takeWidget()
                self.content.hide()
                self.content.setParent(self._orig_parent, self._orig_flags)   # вернуть как было (для повторного показа)
        except RuntimeError:
            pass
        if self in _layers:
            _layers.remove(self)
        try:
            if self.content.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose):
                self.content.deleteLater()
        except RuntimeError:
            pass
        self.hide()
        self.deleteLater()
        self.closed_cb()

    def closed_cb(self):
        pass


def _layer_for(dlg):
    for L in _layers:
        if L.content is dlg:
            return L
    return None


def present(win, dlg: QDialog, title: str = ""):
    """Показать диалог слоем внутри приложения (не блокируя). Повторный вызов — просто вынести наверх."""
    if not _enabled or _win_of(win) is None:
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        return
    L = _layer_for(dlg)
    if L is not None:
        L.raise_()
        return
    Layer(win, dlg, title or dlg.windowTitle(), modal=False)


def _exec_inapp(self):
    """Подмена QDialog.exec(): модальный диалог главного окна — слоем, с ожиданием ответа."""
    par = self.parentWidget()
    if not _enabled or isinstance(self, _SKIP) or par is None or _win_of(par) is None:
        return _orig["exec"](self)
    win = _main
    loop = QEventLoop()
    L = Layer(win, self, self.windowTitle(), modal=True)
    L.closed_cb = loop.quit
    self.finished.connect(lambda *_: QTimer.singleShot(0, L._finish))     # после выхода из done()
    loop.exec()
    try:
        return QDialog.result(self)                        # метод Qt: у некоторых диалогов поле result — их ответ
    except RuntimeError:                                   # диалог сам удалился по закрытию (finished → deleteLater)
        return 0


# ── вопросы и ввод текста ── #

def _prompt_dialog(win, title, label_text=None, text=None, edit=None, buttons=()):
    dlg = QDialog(win)
    dlg.setWindowTitle(title)
    dlg.setMinimumWidth(420)
    v = QVBoxLayout(dlg)
    v.setSpacing(12)
    if label_text:
        lb = QLabel(label_text)
        lb.setWordWrap(True)
        lb.setTextFormat(Qt.TextFormat.AutoText)
        v.addWidget(lb)
    if edit is not None:
        v.addWidget(edit)
    row = QHBoxLayout()
    row.addStretch(1)
    clicked = {"v": None}
    default_btn = None
    for name, std, accent, is_default in buttons:
        b = QPushButton(name)
        if accent:
            b.setObjectName("AccentBtn")
        b.setMinimumWidth(92)
        b.clicked.connect(lambda _=False, s=std: (clicked.__setitem__("v", s), dlg.done(1 if s is not None else 0)))
        row.addWidget(b)
        if is_default:
            default_btn = b
    v.addLayout(row)
    if default_btn is not None:
        default_btn.setDefault(True)
        default_btn.setAutoDefault(True)
    return dlg, clicked


def _get_text(parent=None, title="", label="", echo=QLineEdit.EchoMode.Normal, text="", *a, **k):
    win = _win_of(parent)
    if not _enabled or win is None:
        return _orig["getText"](parent, title, label, echo, text, *a, **k)
    edit = QLineEdit(text)
    edit.setEchoMode(echo)
    edit.selectAll()
    dlg, clicked = _prompt_dialog(win, title, label, edit=edit,
                                  buttons=(("Отмена", None, False, False), ("OK", "ok", True, True)))
    edit.returnPressed.connect(lambda: (clicked.__setitem__("v", "ok"), dlg.done(1)))
    edit.setFocus()
    res = dlg.exec()
    return edit.text(), bool(res) and clicked["v"] == "ok"


_SB = QMessageBox.StandardButton
_BTN_TEXT = {_SB.Yes: "Да", _SB.No: "Нет", _SB.Ok: "OK", _SB.Cancel: "Отмена", _SB.Close: "Закрыть",
             _SB.Save: "Сохранить", _SB.Discard: "Не сохранять", _SB.Apply: "Применить", _SB.Retry: "Повторить",
             _SB.Ignore: "Пропустить", _SB.Abort: "Прервать", _SB.YesToAll: "Да для всех", _SB.NoToAll: "Нет для всех"}
_ORDER = (_SB.Save, _SB.Yes, _SB.Ok, _SB.Apply, _SB.Retry, _SB.YesToAll, _SB.Discard, _SB.No, _SB.NoToAll,
          _SB.Ignore, _SB.Close, _SB.Abort, _SB.Cancel)
_AFFIRM = (_SB.Yes, _SB.Ok, _SB.Save, _SB.Apply, _SB.Retry, _SB.YesToAll)


def _message(kind, parent, title, text, buttons=None, default=None):
    win = _win_of(parent)
    orig = _orig[kind]
    if buttons is None:
        buttons = _SB.Yes | _SB.No if kind == "question" else _SB.Ok
    if default is None:
        default = _SB.NoButton
    if not _enabled or win is None:
        return orig(parent, title, text, buttons, default)
    btns = [b for b in _ORDER if buttons & b]
    if not btns:
        btns = [_SB.Ok]
    dflt = default if (default != _SB.NoButton and default in btns) else next((b for b in btns if b in _AFFIRM), btns[0])
    spec = tuple((_BTN_TEXT.get(b, "OK"), b, b in _AFFIRM and b == dflt, b == dflt) for b in btns)
    dlg, clicked = _prompt_dialog(win, title, text, buttons=spec)
    dlg.exec()
    if clicked["v"] is not None:
        return clicked["v"]
    for b in (_SB.Cancel, _SB.No, _SB.Close, _SB.Ok):          # закрыли «×» / Esc
        if b in btns:
            return b
    return btns[-1]


def _question(parent, title, text, buttons=None, default=None):
    return _message("question", parent, title, text, buttons, default)


def _information(parent, title, text, buttons=None, default=None):
    return _message("information", parent, title, text, buttons, default)


def _warning(parent, title, text, buttons=None, default=None):
    return _message("warning", parent, title, text, buttons, default)


def _critical(parent, title, text, buttons=None, default=None):
    return _message("critical", parent, title, text, buttons, default)


# ── установка ── #

def install(main_window, enabled: bool = True):
    """Один раз при старте: запоминаем главное окно и подменяем функции Qt."""
    global _main, _enabled
    _main = main_window
    if not _orig:
        _orig["exec"] = QDialog.exec
        _orig["getText"] = QInputDialog.getText
        for k in ("question", "information", "warning", "critical"):
            _orig[k] = getattr(QMessageBox, k)
        QDialog.exec = _exec_inapp
        QInputDialog.getText = staticmethod(_get_text)
        QMessageBox.question = staticmethod(_question)
        QMessageBox.information = staticmethod(_information)
        QMessageBox.warning = staticmethod(_warning)
        QMessageBox.critical = staticmethod(_critical)
    _enabled = bool(enabled)


def set_enabled(on: bool):
    global _enabled
    _enabled = bool(on)
