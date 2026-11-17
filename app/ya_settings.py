# ya_settings.py
"""
Настройки Echoes Music по разделам + умный поиск.

Слева — разделы (Оформление, Звук, Воспроизведение, Тексты, Медиатека, Инструменты, Сеть и интеграции),
справа — только настройки выбранного раздела. Сверху — поиск: показывает подходящие блоки из всех разделов.
Поиск понимает:
  * опечатки («эквалайзр», «громкасть»);
  * неправильную раскладку («ntvf» → «тема», «ызщешан» → «spotify»);
  * синонимы и смысл («басы» → эквалайзер, «место на диске» → очистка кэша, «цвет» → оформление и тема);
  * начало слова («экв», «discord»).

Блоки — это готовые карточки и секции правой панели плеера (эквалайзер, Lo-Fi, таймер сна…): раздел
не перестраивает их, а прячет/показывает, поэтому всё продолжает работать как раньше.
"""
from __future__ import annotations

import difflib
import re

from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget,
                             QAbstractButton, QButtonGroup, QComboBox)

CATEGORIES = (("look", "Оформление", "palette"), ("sound", "Звук", "eq"), ("play", "Воспроизведение", "play"),
              ("lyrics", "Тексты песен", "lyrics"), ("library", "Медиатека", "album"),
              ("performance", "Производительность", "performance"), ("tools", "Инструменты", "settings"), ("apps", "Сеть и интеграции", "net"), ("other", "Другое", "dots"))

SECTION_CAT = {"оформление": "look", "язык": "look", "графика": "performance", "производительность":"performance", "текст песни": "lyrics",
               "воспроизведение": "play", "клипы": "play", "таймер сна": "play", "медиатека": "library",
               "настроение дня": "library", "жанры": "library", "эквалайзер": "sound", "lo-fi": "sound",
               "атмосферный шум": "sound", "мощность звука": "sound", "pomodoro": "tools", "открытия": "tools",
               "стример": "tools", "discord": "apps", "библиотека": "library", "плейлисты": "library"}

SYNONYMS = {
    "тема": "оформление цвет цвета дизайн скин вид внешний стиль акцент шрифт кнопки echoes music",
    "цвет": "тема оформление акцент цвета палитра",
    "шрифт": "тема оформление текст буквы font размер",
    "кнопки": "тема оформление скругление стиль",
    "громкость": "звук громче тише мощность boost усиление экстремальная",
    "звук": "эквалайзер громкость басы lo-fi шум",
    "басы": "эквалайзер бас низкие частоты eq",
    "эквалайзер": "eq басы частоты пресеты",
    "eq": "эквалайзер",
    "текст": "тексты песни караоке перевод lyrics слова",
    "слова": "тексты песни",
    "перевод": "тексты перевод язык",
    "язык": "language english русский перевод интерфейс",
    "сон": "таймер сна выключить",
    "таймер": "сна pomodoro",
    "кэш": "очистка место диск память удалить",
    "место": "очистка кэш диск",
    "удалить": "очистка кэш",
    "память": "очистка кэш производительность",
    "лаги": "графика производительность кадры fps анимации",
    "фпс": "графика производительность кадры fps",
    "fps": "графика производительность кадры",
    "анимации": "графика производительность инструменты слушателя",
    "spotify": "импорт плейлисты спотифай",
    "спотифай": "spotify импорт",
    "плейлист": "плейлисты импорт телефон файл",
    "телефон": "плейлисты экспорт",
    "теги": "найти теги обложки медиатека",
    "обложка": "режим обложки обложки теги",
    "discord": "дискорд статус rich presence активность",
    "дискорд": "discord",
    "друзья": "echoes.net сеть друзья",
    "сеть": "echoes.net интеграции друзья",
    "стрим": "стример obs конструктор стримера",
    "obs": "стример",
    "онлайн": "слушать онлайн поток стриминг youtube soundcloud",
    "скачивать": "слушать онлайн поток",
    "клип": "клипы видео",
    "шум": "атмосферный шум дождь lo-fi",
    "дождь": "атмосферный шум",
    "настроение": "фильтр по настроению настроение дня",
    "горячие": "клавиши масштаб окно",
    "клавиши": "масштаб клавиши окно горячие",
    "масштаб": "масштаб клавиши окно размер интерфейса",
    "профиль": "профиль ник аватар",
    "фокус": "pomodoro",
}

EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,.`"
RU = "йцукенгшщзхъфывапролджэячсмитьбюё"
_EN2RU = {e: r for e, r in zip(EN, RU)}
_RU2EN = {r: e for e, r in zip(EN, RU)}


def norm(s: str) -> str:
    s = str(s or "").casefold().replace("ё", "е")
    return re.sub(r"[^\w\-\.\s]+", " ", s)


STOP = {"на", "и", "в", "во", "для", "по", "с", "со", "к", "ко", "от", "из", "у", "о", "об", "а", "но", "не", "ни",
        "или", "это", "как", "что", "мне", "мой", "моя", "мои", "свой", "все", "всё", "the", "of", "to", "and", "a"}


def words(s: str) -> list:
    return [w for w in re.split(r"[\s/·,:;()«»\"']+", norm(s)) if (len(w) > 1 or w.isdigit()) and w not in STOP]


def layout_variants(q: str) -> list:
    """Тот же запрос, набранный в другой раскладке («ntvf» → «тема», «ызщешан» → «spotify»)."""
    out = [q]
    if any(c in _EN2RU for c in q) and not re.search("[а-я]", q):
        out.append("".join(_EN2RU.get(c, c) for c in q))
    if re.search("[а-я]", q):
        alt = "".join(_RU2EN.get(c, c) for c in q)
        if alt != q:
            out.append(alt)
    return out


class Block:
    __slots__ = ("cat", "title", "widgets", "anchor", "hay", "title_words", "key_words", "hidden_by_me", "always")

    def __init__(self, cat, title, widgets, text="", anchor=None, always=False, keys=""):
        self.cat, self.title = cat, title
        self.widgets = [w for w in widgets if w is not None]
        self.anchor = anchor or (self.widgets[0] if self.widgets else None)
        self.title_words = words(title)
        self.key_words = set(words(keys))                     # слова, подобранные вручную, — почти как заголовок
        self.hay = set(words(title + " " + keys + " " + text))
        self.hidden_by_me: set = set()
        self.always = always


def _texts(w) -> str:
    """Все надписи внутри виджета: подписи, кнопки, галочки, подсказки, пункты списков — для поиска."""
    bits = []
    try:
        for x in [w] + w.findChildren(QWidget):
            if isinstance(x, QLabel):
                bits.append(x.text())
            elif isinstance(x, QAbstractButton):
                bits.append(x.text())
            elif isinstance(x, QComboBox):
                bits += [x.itemText(i) for i in range(min(x.count(), 40))]
            tip = x.toolTip()
            if tip:
                bits.append(tip)
    except RuntimeError:
        pass
    return " ".join(re.sub(r"<[^>]+>", " ", b) for b in bits if b)


def _layout_widgets(lay) -> list:
    out = []
    for i in range(lay.count()):
        it = lay.itemAt(i)
        if it.widget() is not None:
            out.append(it.widget())
        elif it.layout() is not None:
            out += _layout_widgets(it.layout())
    return out


def section_cat(title: str) -> str:
    t = norm(title)
    for k, c in SECTION_CAT.items():
        if t.startswith(k) or k in t:
            return c
    return "other"


class _Flow(QLayout):
    """Раскладка «в строку с переносом» (пилюли разделов в узкой панели настроек)."""

    def __init__(self, parent=None, gap=6):
        super().__init__(parent)
        self._items = []
        self._gap = gap

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._place(w, apply=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._place(rect.width(), apply=True, x0=rect.x(), y0=rect.y())

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        from PyQt6.QtCore import QSize as _S
        w = max((it.sizeHint().width() for it in self._items), default=0)
        return _S(w, self._place(max(w, 1), apply=False))

    def _place(self, width, apply, x0=0, y0=0):
        from PyQt6.QtCore import QRect as _R
        x, y, row_h = 0, 0, 0
        for it in self._items:
            if it.widget() is not None and it.widget().isHidden():
                continue
            sz = it.sizeHint()
            if x and x + sz.width() > width:
                x, y, row_h = 0, y + row_h + self._gap, 0
            if apply:
                it.setGeometry(_R(x0 + x, y0 + y, sz.width(), sz.height()))
            x += sz.width() + self._gap
            row_h = max(row_h, sz.height())
        return y + row_h


class SettingsHub(QWidget):
    """Страница настроек: разделы слева, поиск сверху. compact — для узкой панели (вид Phantom): поиск сверху,
    под ним разделы пилюлями в несколько строк (chip_factory(текст, значок) делает пилюлю)."""

    def __init__(self, page_cls, icon_fn, accent="#ffdb1a", compact=False, chip_factory=None):
        super().__init__()
        if compact:
            self._init_compact(page_cls, icon_fn, accent, chip_factory)
            return
        self.setObjectName("YaPage")
        self.blocks: list[Block] = []
        self.containers: list = []                             # страницы правой панели: пустые — прятать целиком
        self.cat = "look"
        self.accent = accent
        self.hints: dict = {}                                  # раздел → что в нём настраивается (строка под поиском)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        # ── разделы ──
        nav = QWidget()
        nav.setObjectName("YaPage")
        nav.setFixedWidth(252)                                # «Производительность» целиком, без обрезки
        nv = QVBoxLayout(nav)
        nv.setContentsMargins(28, 24, 10, 20)
        nv.setSpacing(4)
        h = QLabel("Настройки")
        h.setObjectName("YaH1")
        nv.addWidget(h)
        nv.addSpacing(10)
        self.nav_btns = {}
        grp = self._grp = QButtonGroup(self)
        for key, title, ic in CATEGORIES:
            b = QPushButton("  " + title)
            b.setObjectName("YaNav")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            try:
                b.setIcon(icon_fn(ic, 18, "#d0d0d0"))
                b.setIconSize(QSize(18, 18))
            except Exception:                                  # noqa: BLE001
                pass
            b.clicked.connect(lambda _=False, k=key: self.select(k))
            grp.addButton(b)
            nv.addWidget(b)
            self.nav_btns[key] = b
        nv.addStretch(1)
        root.addWidget(nav)
        # ── содержимое ──
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        top = QHBoxLayout()
        top.setContentsMargins(12, 26, 32, 6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Найти настройку: «эквалайзер», «тема», «басы», «место на диске»…")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumHeight(40)
        self.search.setMaximumWidth(620)
        self.search.textChanged.connect(lambda _t: self._deb.start())
        top.addWidget(self.search, 1)
        top.addStretch(0)
        right.addLayout(top)
        self.info = QLabel("")
        self.info.setObjectName("YaSub")
        self.info.setContentsMargins(14, 0, 0, 4)
        right.addWidget(self.info)
        self.page = page_cls(margins=(12, 8, 32, 24))
        right.addWidget(self.page, 1)
        root.addLayout(right, 1)
        self.v = self.page.v
        self._deb = QTimer(self)
        self._deb.setSingleShot(True)
        self._deb.setInterval(160)
        self._deb.timeout.connect(self._do_search)
        self.nav_btns["look"].setChecked(True)

    def _init_compact(self, page_cls, icon_fn, accent, chip_factory):
        self.setObjectName("YaPage")
        self.blocks: list[Block] = []
        self.containers: list = []
        self.cat = "look"
        self.accent = accent
        self.hints: dict = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        self.search = QLineEdit()
        self.search.setObjectName("PhSearch")
        self.search.setPlaceholderText("Найти настройку: «эквалайзер», «фон», «басы», «место на диске»…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _t: self._deb.start())
        root.addWidget(self.search)
        nav = QWidget()
        flow = _Flow(nav, 6)
        self.nav_btns = {}
        grp = self._grp = QButtonGroup(self)
        for key, title, ic in CATEGORIES:
            b = chip_factory(title, icon_fn(ic, 16, "")) if chip_factory else QPushButton(title)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=key: self.select(k))
            grp.addButton(b)
            flow.addWidget(b)
            self.nav_btns[key] = b
        root.addWidget(nav)
        self.info = QLabel("")
        self.info.setObjectName("YaSub")
        self.info.setWordWrap(True)
        root.addWidget(self.info)
        self.page = page_cls(margins=(0, 4, 8, 24))
        root.addWidget(self.page, 1)
        self.v = self.page.v
        self._deb = QTimer(self)
        self._deb.setSingleShot(True)
        self._deb.setInterval(160)
        self._deb.timeout.connect(self._do_search)
        self.nav_btns["look"].setChecked(True)

    # ── совместимость со страницей (Page) ──
    def ensureWidgetVisible(self, w, *a):
        b = next((b for b in self.blocks if w in b.widgets or any(_is_ancestor(x, w) for x in b.widgets)), None)
        if b is not None and b.cat != self.cat and not self.search.text():
            self.select(b.cat)
        QTimer.singleShot(0, lambda: self.page.ensureWidgetVisible(w, *a))

    # ── блоки ──
    def add(self, cat, title, widget_or_list, text="", always=False) -> Block:
        ws = widget_or_list if isinstance(widget_or_list, list) else [widget_or_list]
        b = Block(cat, title, ws, " ".join(_texts(w) for w in ws), always=always, keys=text)
        self.blocks.append(b)
        return b

    def _sync_containers(self):
        for c in self.containers:
            try:
                inside = [b for b in self.blocks if any(_is_ancestor(c, w) for w in b.widgets[:1])]
                c.setVisible(any(not w.isHidden() for b in inside for w in b.widgets))
            except RuntimeError:
                pass

    def index_layout(self, lay, default_cat="other", container=None):
        if container is not None and container not in self.containers:
            self.containers.append(container)
        """Секции правой панели плеера (QLabel#Section + всё до следующего заголовка) — в блоки по разделам."""
        cur, title, ws = None, "", []

        def flush():
            if ws:
                b = Block(cur or default_cat, title, list(ws), " ".join(_texts(w) for w in ws))
                self.blocks.append(b)
        for i in range(lay.count()):
            it = lay.itemAt(i)
            items = [it.widget()] if it.widget() is not None else (_layout_widgets(it.layout()) if it.layout() else [])
            head = next((w for w in items if isinstance(w, QLabel) and w.objectName() == "Section"), None)
            if head is not None:
                flush()
                cur, title, ws = section_cat(head.text()), head.text(), []
            ws += items
        flush()

    def remove_widgets(self, widgets):
        ws = set(widgets)
        self.show_all()
        self.blocks = [b for b in self.blocks if not (set(b.widgets) & ws)]
        self.containers = [c for c in self.containers if c not in ws]

    def _show(self, b: Block, on: bool):
        for w in b.widgets:
            try:
                if on:
                    if w in b.hidden_by_me:
                        w.show()
                elif not w.isHidden():
                    w.hide()
                    b.hidden_by_me.add(w)
            except RuntimeError:
                pass
        if on:
            b.hidden_by_me.clear()

    def show_all(self):
        for b in self.blocks:
            self._show(b, True)
        for c in self.containers:
            try:
                c.setVisible(True)
            except RuntimeError:
                pass

    def select(self, cat):
        """Раздел настроек — с переходом (ui_anim.morph): вниз по списку — вперёд, вверх — назад."""
        prev = getattr(self, "cat", None)
        keys = list(self.nav_btns)
        if prev != cat and prev in keys and cat in keys and self.page.isVisible():
            try:
                import ui_anim
                ui_anim.morph(self.page, lambda: self._select(cat), 1 if keys.index(cat) > keys.index(prev) else -1)
                return
            except Exception:                                  # noqa: BLE001
                pass
        self._select(cat)

    def _select(self, cat):
        self.cat = cat
        if self.search.text():
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
        for k, btn in self.nav_btns.items():
            btn.setChecked(k == cat)
        shown = 0
        for b in self.blocks:
            on = b.always or b.cat == cat
            self._show(b, on)
            shown += on and not b.always
        self.info.setText(self.hints.get(cat, ""))
        self.nav_btns["other"].setVisible(any(b.cat == "other" for b in self.blocks))
        self._sync_containers()
        self.page.verticalScrollBar().setValue(0)

    def refresh(self):
        self.nav_btns["other"].setVisible(any(b.cat == "other" for b in self.blocks))
        if self.search.text():
            self._do_search()
        else:
            self.select(self.cat)

    # ── умный поиск ──
    def score(self, q: str, b: Block) -> float:
        best = 0.0
        for variant in layout_variants(norm(q).strip()):
            qws = words(variant)
            if not qws:
                continue
            total, hit = 0.0, 0
            for w in qws:
                cands = [w] + words(SYNONYMS.get(w, ""))
                for k, syn in SYNONYMS.items():                 # «громкаст» → «громкость» → её синонимы
                    if len(w) >= 4 and (k.startswith(w) or difflib.SequenceMatcher(None, w, k).ratio() > 0.8):
                        cands += [k] + words(syn)
                s = 0.0
                for c in dict.fromkeys(cands):
                    weight = 1.0 if c == w else 0.55
                    for hw in b.hay:
                        if hw == c:
                            m = 1.0
                        elif hw.startswith(c) and len(c) >= 2:
                            m = 0.85
                        elif len(c) >= 4 and c in hw:
                            m = 0.6
                        elif len(c) >= 4 and abs(len(hw) - len(c)) <= 3 and \
                                difflib.SequenceMatcher(None, c, hw).ratio() >= 0.78:
                            m = 0.55                            # опечатка
                        else:
                            continue
                        if hw in b.title_words:
                            m *= 1.6                            # совпало в заголовке — выше
                        elif hw in b.key_words:
                            m *= 1.35
                        s = max(s, m * weight)
                if s > 0:
                    hit += 1
                total += s
            if hit:
                best = max(best, total * (hit / len(qws)) ** 2)
        return best

    def _do_search(self):
        q = self.search.text().strip()
        if not q:
            self.select(self.cat)
            return
        self._grp.setExclusive(False)                          # во время поиска раздел не выбран
        for btn in self.nav_btns.values():
            btn.setChecked(False)
        self._grp.setExclusive(True)
        scored = sorted(((self.score(q, b), i, b) for i, b in enumerate(self.blocks) if not b.always),
                        key=lambda x: (-x[0], x[1]))
        top = scored[0][0] if scored else 0
        found = [b for s, _i, b in scored if s > 0 and s >= top * 0.35]
        keep = set(map(id, found))
        for b in self.blocks:
            self._show(b, id(b) in keep)
        self._sync_containers()
        # порядок показа — по релевантности: переставить нельзя (блоки внутри своих панелей), поэтому
        # прокручиваем к самому подходящему
        names = {k: t for k, t, _ in CATEGORIES}
        if found:
            cats = list(dict.fromkeys(names[b.cat] for b in found))
            self.info.setText(f"Найдено: {len(found)}  ·  " + ", ".join(cats[:4]) +
                              ("" if found[0].title.lower() in q.lower() else f"  ·  лучшее: «{found[0].title}»"))
            a = found[0].anchor
            QTimer.singleShot(30, lambda: a is not None and self.page.ensureWidgetVisible(a, 0, 40))
        else:
            self.info.setText("Ничего не нашлось — попробуйте другое слово")


def _is_ancestor(a, w) -> bool:
    try:
        p = w
        while p is not None:
            if p is a:
                return True
            p = p.parentWidget()
    except RuntimeError:
        pass
    return False
