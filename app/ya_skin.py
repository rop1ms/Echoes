# ya_skin.py
"""
Полная настройка темы Echoes Music: цвета, шрифт, размер текста, скругление и стиль кнопок.

«Скин» хранится в settings["ya_skin"] и применяется поверх темы:
  * apply()        — подменяет цвета темы (YELLOW, BG, PANEL… в yamusic_theme и во всех модулях, которые
                     импортировали их по имени) и шрифт; вызывается при запуске и перед пересборкой темы;
  * overrides_qss()— дописывается в конец QSS темы: скругления, стиль кнопок (стекло / плоские / контур / мягкие),
                     размер текста;
  * SkinEditor     — окно настройки с живым предпросмотром и готовыми пресетами; «Применить» пересобирает
                     интерфейс Echoes Music без перезапуска.
"""
from __future__ import annotations

import data_home
import sys

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (QButtonGroup, QColorDialog, QDialog, QFontComboBox, QFrame, QGridLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget, QCheckBox, QTabWidget)

DEFAULT = {"accent": "#ffdb1a", "on_accent": "#000000", "bg": "#000000", "panel": "#121212", "panel2": "#1a1a1a",
           "card": "#232323", "text": "#ffffff", "muted": "#8a8a8a", "font": "", "size": 13, "radius": 13,
           "buttons": "glass", "bold": True, "title_font": "", "density": "normal", "album_round": 10,
           "artist_round": True, "panel_radius": 22}
TITLE_FONTS = (("", "Как текст"), ("rounded", "Округлый"), ("mono", "Терминал"), ("hand", "Рукописный"))
TITLE_FAMILY = {"rounded": ["Nunito", "Varela Round", "Arial Rounded MT Bold", "Quicksand", "Segoe UI Variable Display",
                            "Segoe UI"],
                "mono": ["JetBrains Mono", "Cascadia Mono", "Cascadia Code", "Consolas", "Courier New"],
                "hand": ["Segoe Print", "Segoe Script", "Comic Sans MS", "Ink Free"]}
DENSITIES = (("spacious", "Просторно", 1.15), ("normal", "Обычно", 1.0), ("compact", "Компактно", 0.86))

PRESETS = {
    "Echoes Classic": {},
    "Midnight": {"accent": "#7c8cff", "on_accent": "#ffffff", "bg": "#03040c", "panel": "#0a0c1c", "panel2": "#0f1226",
                 "card": "#1a1e3a", "muted": "#8b90b8"},
    "Sakura": {"accent": "#ff8fc2", "on_accent": "#2a0716", "bg": "#0c0609", "panel": "#170c12", "panel2": "#1f1018",
               "card": "#2e1824", "muted": "#b392a3"},
    "Mono": {"accent": "#ffffff", "on_accent": "#000000", "bg": "#000000", "panel": "#0e0e0e", "panel2": "#151515",
             "card": "#222222", "muted": "#8c8c8c"},
    "Vapor": {"accent": "#ff3cf0", "on_accent": "#ffffff", "bg": "#07020f", "panel": "#120624", "panel2": "#1a0a33",
              "card": "#2a1050", "text": "#f2ecff", "muted": "#9d8cc8"},
    "Forest": {"accent": "#7ddc6a", "on_accent": "#06140a", "bg": "#030805", "panel": "#0a140d", "panel2": "#0f1c12",
               "card": "#18291c", "muted": "#88a38c"},
    "Зелёный (как Spotify)": {"accent": "#1ed760", "on_accent": "#000000", "panel": "#121212", "panel2": "#181818"},
    "Неон": {"accent": "#b46bff", "on_accent": "#ffffff", "bg": "#07040d", "panel": "#100a1a", "panel2": "#161022",
             "card": "#211830", "muted": "#9a8fb0"},
    "Розовый": {"accent": "#ff4fa3", "on_accent": "#ffffff", "bg": "#0b0609", "panel": "#140c11", "panel2": "#1c1218",
                "card": "#2a1a23"},
    "Океан": {"accent": "#2fc6ff", "on_accent": "#00131c", "bg": "#03080d", "panel": "#0a131b", "panel2": "#0f1b25",
              "card": "#172836", "muted": "#7f97a8"},
    "Красный": {"accent": "#ff3b3b", "on_accent": "#ffffff", "bg": "#080505", "panel": "#120b0b", "panel2": "#1a1010"},
    "Мята": {"accent": "#5ef2c2", "on_accent": "#00140d", "bg": "#040a08", "panel": "#0b1411", "panel2": "#101c18",
             "card": "#182923", "muted": "#86a39a"},
    "Графит": {"accent": "#e8e8e8", "on_accent": "#000000", "bg": "#0c0c0d", "panel": "#161618", "panel2": "#1d1d20",
               "card": "#28282c"},
    "Закат": {"accent": "#ff9a3c", "on_accent": "#1a0b00", "bg": "#0a0604", "panel": "#140d09", "panel2": "#1d130d",
              "card": "#2b1c13"},
}
BUTTON_STYLES = (("glass", "Стекло"), ("flat", "Плоские"), ("outline", "Контур"), ("soft", "Мягкие"))
COLOR_ROWS = (("accent", "Акцент", "кнопки, выделение, активная вкладка"),
              ("on_accent", "Текст на акценте", "надписи на жёлтых (акцентных) кнопках"),
              ("bg", "Фон окна", ""), ("panel", "Панели", "основная область"), ("panel2", "Плеер и меню", ""),
              ("card", "Карточки", ""), ("text", "Текст", ""), ("muted", "Второстепенный текст", "подписи, время"))


def _hex(c: str, default: str) -> str:
    q = QColor(str(c or ""))
    return q.name() if q.isValid() else default


def normalize(skin) -> dict:
    s = dict(DEFAULT)
    if isinstance(skin, dict):
        for k, d in DEFAULT.items():
            v = skin.get(k, d)
            if k in ("size", "radius", "album_round", "panel_radius"):
                try:
                    v = int(v)
                except (TypeError, ValueError):
                    v = d
                v = max(10, min(17, v)) if k == "size" else max(0, min(75, v)) if k == "album_round" else \
                    max(0, min(36 if k == "panel_radius" else 20, v))
            elif k == "title_font":
                v = v if v in dict(TITLE_FONTS) else ""
            elif k == "density":
                v = v if v in [x[0] for x in DENSITIES] else "normal"
            elif k == "artist_round":
                v = bool(v)
            elif k == "buttons":
                v = v if v in dict(BUTTON_STYLES) else d
            elif k == "bold":
                v = bool(v)
            elif k == "font":
                v = str(v or "")[:80]
            else:
                v = _hex(v, d)
            s[k] = v
    return s


def rgba(c: str, a: float) -> str:
    q = QColor(c)
    return f"rgba({q.red()},{q.green()},{q.blue()},{a})"


def lighter(c: str, k=125) -> str:
    return QColor(c).lighter(k).name()


def darker(c: str, k=125) -> str:
    return QColor(c).darker(k).name()


_ORIG = {}
_RECOLOR: dict = {}            # константа → (значение по умолчанию, цвет скина) — для модулей, импортированных позже


def _skin_module(name: str) -> bool:
    return (name == "yamusic_theme" or name.startswith(("net_", "ya_", "echo", "music_"))
            or name in ("emoji_pack", "profile_editor", "lyrics_view"))


class _LateImport:
    """apply() перекрашивает только уже загруженные модули. «Моя волна», дуэль и другие страницы грузятся
    позже — у них оставался стандартный жёлтый при другом акценте. Этот поиск модулей перекрашивает их
    константы сразу после загрузки."""

    def find_spec(self, name, path=None, target=None):
        if not _RECOLOR or not _skin_module(name):
            return None
        from importlib.machinery import PathFinder
        spec = PathFinder.find_spec(name, path)
        loader = getattr(spec, "loader", None)
        if loader is None or not hasattr(loader, "exec_module"):
            return spec
        orig = loader.exec_module

        def exec_module(module, _o=orig):
            _o(module)
            for k, (old, new) in list(_RECOLOR.items()):
                try:
                    if getattr(module, k, None) == old:
                        setattr(module, k, new)
                except Exception:                              # noqa: BLE001
                    pass
        loader.exec_module = exec_module
        return spec


_HOOK = []


def apply(skin) -> dict:
    """Подменить цвета и шрифт темы Echoes Music (до сборки интерфейса)."""
    s = normalize(skin)
    import yamusic_theme as Y
    try:
        import custom_fonts                                    # свои шрифты из файлов — до сборки интерфейса
        custom_fonts.load_all()
    except Exception as e:                                     # noqa: BLE001
        print("[skin] fonts:", e)
    try:
        # Шрифт темы может быть из встроенного набора (assets/fonts/nick: BioRhyme, Unbounded, Comfortaa…).
        # Тот набор регистрировался только при первом открытии профиля — до этого интерфейс собирался
        # запасным шрифтом, а после часть надписей переключалась на выбранный: на экране два шрифта сразу.
        from PyQt6.QtGui import QFontDatabase
        want = [f for f in [s["font"], *TITLE_FAMILY.get(s["title_font"], [])] if f]
        if want:
            known = set(QFontDatabase.families())
            if any(f not in known for f in want):
                import net_nick
                net_nick._load_fonts()
    except Exception as e:                                     # noqa: BLE001
        print("[skin] bundled fonts:", e)
    if not _ORIG:
        _ORIG.update(YELLOW=Y.YELLOW, BG=Y.BG, PANEL=Y.PANEL, PANEL2=Y.PANEL2, CARD=Y.CARD, TEXT=Y.TEXT,
                     MUTED=Y.MUTED, FAMILIES=list(Y.FAMILIES))
    new = {"YELLOW": s["accent"], "BG": s["bg"], "PANEL": s["panel"], "PANEL2": s["panel2"], "CARD": s["card"],
           "TEXT": s["text"], "MUTED": s["muted"]}
    old = {k: getattr(Y, k) for k in new}
    _RECOLOR.clear()
    _RECOLOR.update({k: (_ORIG[k], v) for k, v in new.items() if _ORIG.get(k) != v})
    if not _HOOK:
        _HOOK.append(_LateImport())
        sys.meta_path.insert(0, _HOOK[0])
    for name, mod in list(sys.modules.items()):              # и в модулях, что сделали «from yamusic_theme import YELLOW»
        if mod is None or not _skin_module(name):
            continue
        for k, v in new.items():
            try:
                if getattr(mod, k, None) == old[k]:
                    setattr(mod, k, v)
            except Exception:                                  # noqa: BLE001
                pass
    Y.FAMILIES[:] = ([s["font"]] if s["font"] else []) + [f for f in _ORIG["FAMILIES"] if f != s["font"]]
    Y.TITLE_FAMILIES[:] = list(TITLE_FAMILY.get(s["title_font"], []))  # заголовки, логотип
    Y.DENSITY = next(k for key, _n, k in DENSITIES if key == s["density"])
    Y.CARD_RADIUS = s["album_round"]
    Y.ARTIST_ROUND = s["artist_round"]
    Y._ICON_CACHE.clear()
    try:                                                       # тумблеры (картинки) — перерисовать в новом акценте
        from pathlib import Path
        d = data_home.root() / "ui_cache"
        stamp = d / "accent.txt"
        if not stamp.exists() or stamp.read_text(encoding="utf-8") != s["accent"]:
            for f in ("sw_on.png", "sw_off.png", "v2"):
                (d / f).unlink(missing_ok=True)
            d.mkdir(parents=True, exist_ok=True)
            stamp.write_text(s["accent"], encoding="utf-8")
    except OSError:
        pass
    globals()["CURRENT"] = s
    return s


CURRENT = dict(DEFAULT)


def interface_radius(base=22):
    return round(base * CURRENT.get("panel_radius", 22) / 22)


def gold(accent: str) -> str:
    """«Золотой» градиент стеклянной акцентной кнопки — из любого акцента."""
    return (f"qlineargradient(x1:0,y1:0,x2:0.8,y2:1,stop:0 {lighter(accent, 150)},stop:0.12 {lighter(accent, 125)},"
            f"stop:0.45 {accent},stop:0.85 {darker(accent, 120)},stop:1 {lighter(accent, 110)})")


def overrides_qss(s=None) -> str:
    """Дописывается в конец QSS темы: стиль кнопок, скругление, текст."""
    s = normalize(s or CURRENT)
    a, on, r = s["accent"], s["on_accent"], s["radius"]
    rs = min(r, 13)                                            # у низких кнопок радиус > половины высоты = квадрат
    fam = f'font-family:"{s["font"]}","YS Text","Inter","Segoe UI","ECHOES Symbols";' if s["font"] else ""
    weight = "" if s["bold"] else "font-weight:500;"
    out = [f"QWidget {{ {fam} font-size:{s['size']}px; }}",
           f"QLabel#YaBadge {{ background:{a}; color:{on}; }}",
           f"QPushButton#YaNav:checked {{ color:{s['text']}; background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
           f"stop:0 {rgba(a, 0.18)},stop:0.55 {rgba(a, 0.05)},stop:1 rgba(255,255,255,0.02)); }}",
           f"QLineEdit, QTextEdit, QPlainTextEdit {{ selection-background-color:{a}; selection-color:{on}; }}",
           f"QSlider::add-page:vertical {{ background:{a}; }}"]
    btn = "QPushButton, QToolButton, QPushButton#GhostBtn, QPushButton#NetVote"
    chip = "QPushButton#YaChip, QPushButton#YaSeg"
    acc = "QPushButton#AccentBtn, QPushButton#YaYellow, QPushButton#YaChip:checked, QPushButton#YaSeg:checked"
    if s["buttons"] == "flat":
        out += [f"{btn}, {chip} {{ background:{lighter(s['card'], 110)}; border:none; color:{s['text']}; {weight} }}",
                f"QPushButton:hover, QToolButton:hover, QPushButton#YaChip:hover {{ background:{lighter(s['card'], 135)}; "
                f"border:none; }}",
                f"QPushButton:checked, QToolButton:checked {{ background:{lighter(s['card'], 150)}; color:{a}; border:none; }}",
                f"{acc} {{ background:{a}; color:{on}; border:none; }}",
                f"QPushButton#AccentBtn:hover, QPushButton#YaYellow:hover {{ background:{lighter(a, 112)}; border:none; }}",
                f"QLineEdit, QComboBox, QSpinBox {{ background:{lighter(s['card'], 105)}; border:none; }}"]
    elif s["buttons"] == "outline":
        out += [f"{btn}, {chip} {{ background:transparent; border:1px solid {rgba(s['text'], 0.28)}; color:{s['text']}; {weight} }}",
                f"QPushButton:hover, QToolButton:hover, QPushButton#YaChip:hover {{ background:{rgba(s['text'], 0.06)}; "
                f"border-color:{rgba(s['text'], 0.6)}; }}",
                f"QPushButton:checked, QToolButton:checked {{ background:transparent; color:{a}; border-color:{a}; }}",
                f"{acc} {{ background:transparent; color:{a}; border:2px solid {a}; }}",
                f"QPushButton#AccentBtn:hover, QPushButton#YaYellow:hover {{ background:{rgba(a, 0.12)}; }}",
                f"QLineEdit, QComboBox, QSpinBox {{ background:transparent; border:1px solid {rgba(s['text'], 0.25)}; }}"]
    elif s["buttons"] == "soft":
        out += [f"{btn}, {chip} {{ background:{rgba(a, 0.10)}; border:none; color:{s['text']}; {weight} }}",
                f"QPushButton:hover, QToolButton:hover, QPushButton#YaChip:hover {{ background:{rgba(a, 0.20)}; border:none; }}",
                f"QPushButton:checked, QToolButton:checked {{ background:{rgba(a, 0.28)}; color:{s['text']}; border:none; }}",
                f"{acc} {{ background:{rgba(a, 0.85)}; color:{on}; border:none; }}",
                f"QLineEdit, QComboBox, QSpinBox {{ background:{rgba(a, 0.07)}; border:none; }}"]
    else:                                                      # стекло: акцентные — градиент из акцента
        out += [f"{acc} {{ background:{gold(a)}; color:{on}; border:1px solid {lighter(a, 125)}; "
                f"border-top-color:{lighter(a, 160)}; }}",
                f"QPushButton#AccentBtn:hover, QPushButton#YaYellow:hover {{ background:{gold(lighter(a, 108))}; }}",
                f"QPushButton:checked, QToolButton:checked {{ color:{lighter(a, 120)}; border-color:{rgba(a, 0.55)}; }}",
                f"QLineEdit:focus, QComboBox:focus {{ border-color:{rgba(a, 0.7)}; }}"]
    out += [f"QPushButton, QToolButton {{ border-radius:{rs}px; }}",
            f"QPushButton#YaChip {{ border-radius:{min(r + 3, 16)}px; }}",
            f"QLineEdit, QComboBox {{ border-radius:{min(r + 4, 17)}px; }}",
            f"QFrame#YaContent {{ border-radius:{s['panel_radius']}px; }}",
            f"QFrame#YaPlayer, QFrame#YaTopBar, QFrame#YaSideNav, QFrame#YaCornerBox {{ border-radius:{round(s['panel_radius']*18/22)}px; }}",
            f"QFrame#NetCard, QFrame#YaWaveCard, QFrame#YaSkinCard {{ border-radius:{round(s['panel_radius']*16/22)}px; }}"]
    if not s["bold"]:
        out.append("QPushButton, QPushButton#YaChip, QPushButton#YaSeg, QPushButton#YaNav { font-weight:500; }")
    if s["title_font"]:
        fams = ",".join(f'"{f}"' for f in TITLE_FAMILY[s["title_font"]])
        out.append(f"QLabel#YaH1, QLabel#YaH2, QLabel#YaHero {{ font-family:{fams}; }}")
    return "\n".join(out)


def preview_qss(s) -> str:
    """QSS окна предпросмотра — как будет выглядеть плеер."""
    s = normalize(s)
    import yamusic_theme as Y
    base = (f"QFrame#PvRoot {{ background:{s['bg']}; border-radius:16px; }}"
            f"QFrame#PvPanel {{ background:{s['panel']}; border-radius:{s['panel_radius']}px; }}"
            f"QFrame#PvPlayer {{ background:{s['panel2']}; border-radius:{round(s['panel_radius']*18/22)}px; }}"
            f"QFrame#PvCard {{ background:{s['card']}; border-radius:{round(s['panel_radius']*12/22)}px; }}"
            f"QLabel {{ color:{s['text']}; background:transparent; }} QLabel#PvSub {{ color:{s['muted']}; font-size:11px; }}"
            f"QLabel#PvH {{ font-size:20px; font-weight:800; }}"
            f"QPushButton#PvNav {{ background:transparent; text-align:left; padding:7px 10px; border:none;"
            f" border-radius:8px; color:{s['muted']}; font-weight:600; }}"
            f"QPushButton#PvNavOn {{ text-align:left; padding:7px 10px; border:none; border-radius:8px; color:{s['text']};"
            f" font-weight:800; background:{rgba(s['accent'], 0.16)}; }}"
            f"QPushButton {{ padding:7px 14px; }}")
    try:
        from echo_glass import glass_controls_qss
        glass = glass_controls_qss() if s["buttons"] == "glass" else ""
    except Exception:                                          # noqa: BLE001
        glass = ""
    return base + glass + overrides_qss(s).replace("QWidget {", "QFrame#PvRoot QWidget {", 1)


class _Swatch(QPushButton):
    def __init__(self, color, on_pick):
        super().__init__()
        self.color = color
        self.on_pick = on_pick
        self.setFixedSize(46, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._pick)
        self.set(color)

    def set(self, color):
        self.color = color
        self.setStyleSheet(f"QPushButton{{background:{color};border:2px solid rgba(255,255,255,0.25);border-radius:8px;}}"
                           f"QPushButton:hover{{border-color:#ffffff;}}")

    def _pick(self):
        c = QColorDialog.getColor(QColor(self.color), self.window(), "Цвет")
        if c.isValid():
            self.set(c.name())
            self.on_pick(c.name())


class SkinEditor(QDialog):
    """Окно «Настроить Echoes Music»: пресеты, цвета, шрифт, кнопки — с живым предпросмотром."""

    def __init__(self, win, parent=None):
        super().__init__(parent or win)
        self.win = win
        self.skin = normalize(win.settings.get("ya_skin"))
        self.setWindowTitle("Настроить тему Echoes Music")
        self.resize(1080, 700)
        self.setStyleSheet("QDialog{background:#111113;} QLabel{color:#f0f0f0;background:transparent;}"
                           "QLabel#Sec{color:#8a8a8a;font-size:11px;font-weight:800;letter-spacing:1px;padding-top:10px;}"
                           "QLabel#Sub{color:#8a8a8a;font-size:11px;}"
                           "QPushButton{background:#232326;color:#f0f0f0;border:none;border-radius:12px;padding:7px 14px;"
                           "font-weight:700;} QPushButton:hover{background:#2e2e32;}"
                           "QPushButton:checked{background:#f0f0f0;color:#000;}"
                           "QPushButton#Accent{background:#ffdb1a;color:#000;} QPushButton#Accent:hover{background:#ffe55c;}"
                           "QSlider::groove:horizontal{height:4px;background:#3a3a3a;border-radius:2px;}"
                           "QSlider::sub-page:horizontal{background:#ffffff;border-radius:2px;}"
                           "QSlider::handle:horizontal{background:#fff;width:14px;height:14px;margin:-5px 0;border-radius:7px;}"
                           "QFontComboBox, QLineEdit{background:#1d1d20;color:#f0f0f0;border:1px solid #2c2c30;"
                           "border-radius:10px;padding:5px 10px;}"
                           "QScrollArea{background:transparent;border:none;}")
        outer = QVBoxLayout(self)
        from echo_glass import GlassFrame, glass_controls_qss
        surface = GlassFrame(radius=20)
        outer.addWidget(surface)
        content_layout = QVBoxLayout(surface)
        self.tabs = QTabWidget()
        content_layout.addWidget(self.tabs)
        self.setStyleSheet(self.styleSheet() + glass_controls_qss() +
                          'QTabWidget::pane{background:transparent;border:none;}'
                          'QTabBar::tab{background:rgba(255,255,255,0.05);color:#c6ccd6;'
                          'border:1px solid rgba(255,255,255,0.1);border-radius:10px;padding:8px 18px;margin:3px;}'
                          'QTabBar::tab:selected{background:rgba(255,255,255,0.13);color:white;}')
        theme = QWidget()
        self.tabs.addTab(theme, "Тема и скругление")
        root = QHBoxLayout(theme)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(18)
        # ── слева: настройки ──
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFixedWidth(420)
        inner = QWidget()
        inner.setStyleSheet("background:transparent;")
        v = QVBoxLayout(inner)
        v.setContentsMargins(0, 0, 8, 0)
        v.setSpacing(6)
        t = QLabel("Тема Echoes Music")
        t.setStyleSheet("font-size:22px;font-weight:900;")
        v.addWidget(t)
        sub = QLabel("Цвета, шрифт и кнопки — справа сразу видно, как будет. «Применить» перестроит плеер.")
        sub.setObjectName("Sub")
        sub.setWordWrap(True)
        v.addWidget(sub)
        v.addWidget(self._sec("ГОТОВЫЕ СТИЛИ"))
        pg = QGridLayout()
        pg.setSpacing(6)
        for i, (name, p) in enumerate(PRESETS.items()):
            b = QPushButton(name)
            col = normalize(dict(DEFAULT, **p))["accent"]
            b.setStyleSheet(f"QPushButton{{text-align:left;padding:7px 10px;border-left:4px solid {col};}}")
            b.clicked.connect(lambda _=False, p=p: self._preset(p))
            pg.addWidget(b, i // 2, i % 2)
        v.addLayout(pg)
        v.addWidget(self._sec("ЦВЕТА"))
        self.sw = {}
        for key, title, hint in COLOR_ROWS:
            r = QHBoxLayout()
            sw = _Swatch(self.skin[key], lambda c, k=key: self._set(k, c))
            self.sw[key] = sw
            r.addWidget(sw)
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(QLabel(title))
            if hint:
                h = QLabel(hint)
                h.setObjectName("Sub")
                col.addWidget(h)
            r.addLayout(col, 1)
            v.addLayout(r)
        v.addWidget(self._sec("ШРИФТ"))
        self.font = QFontComboBox()
        self.font.setCurrentFont(QFont(self.skin["font"] or "Segoe UI"))
        self.font.currentFontChanged.connect(lambda f: self._set("font", f.family()))
        fr = QHBoxLayout()
        fr.addWidget(self.font, 1)
        dflt = QPushButton("Как в теме")
        dflt.clicked.connect(lambda: (self._set("font", ""), self.font.blockSignals(True),
                                      self.font.setCurrentFont(QFont("Segoe UI")), self.font.blockSignals(False)))
        fr.addWidget(dflt)
        v.addLayout(fr)
        ffile = QPushButton("Свой шрифт из файла…")
        ffile.setToolTip("TTF, OTF, TTC, WOFF — шрифт сохранится в ECHOES, устанавливать в Windows не нужно")
        ffile.clicked.connect(self._font_file)
        v.addWidget(ffile)
        self.size_lbl = QLabel()
        v.addWidget(self.size_lbl)
        self.size = QSlider(Qt.Orientation.Horizontal)
        self.size.setRange(10, 17)
        self.size.setValue(self.skin["size"])
        self.size.valueChanged.connect(lambda x: self._set("size", x))
        v.addWidget(self.size)
        self.bold = QCheckBox("Жирные надписи на кнопках")
        self.bold.setChecked(self.skin["bold"])
        self.bold.setStyleSheet("color:#f0f0f0;")
        self.bold.toggled.connect(lambda on: self._set("bold", on))
        v.addWidget(self.bold)
        v.addWidget(self._sec("КНОПКИ"))
        br = QHBoxLayout()
        grp = QButtonGroup(self)
        self.btn_style = {}
        for k, name in BUTTON_STYLES:
            b = QPushButton(name)
            b.setCheckable(True)
            b.setChecked(self.skin["buttons"] == k)
            b.clicked.connect(lambda _=False, k=k: self._set("buttons", k))
            grp.addButton(b)
            self.btn_style[k] = b
            br.addWidget(b)
        v.addLayout(br)
        self.rad_lbl = QLabel()
        v.addWidget(self.rad_lbl)
        self.rad = QSlider(Qt.Orientation.Horizontal)
        self.rad.setRange(0, 20)
        self.rad.setValue(self.skin["radius"])
        self.rad.valueChanged.connect(lambda x: self._set("radius", x))
        v.addWidget(self.rad)
        v.addWidget(self._sec("СКРУГЛЕНИЕ ИНТЕРФЕЙСА"))
        self.panel_rad_lbl = QLabel()
        v.addWidget(self.panel_rad_lbl)
        self.panel_rad = QSlider(Qt.Orientation.Horizontal)
        self.panel_rad.setRange(0, 36)
        self.panel_rad.setValue(self.skin["panel_radius"])
        self.panel_rad.valueChanged.connect(lambda x: self._set("panel_radius", x))
        v.addWidget(self.panel_rad)
        v.addWidget(self._sec("ШРИФТ ЗАГОЛОВКОВ И ЛОГОТИПА"))
        self.tf_btn = self._choice(v, TITLE_FONTS, "title_font")
        v.addWidget(self._sec("ПЛОТНОСТЬ — РАЗМЕР КАРТОЧЕК"))
        self.den_btn = self._choice(v, [(k, n) for k, n, _ in DENSITIES], "density")
        v.addWidget(self._sec("ФОРМА КАРТОЧЕК"))
        self.alb_lbl = QLabel()
        v.addWidget(self.alb_lbl)
        self.alb = QSlider(Qt.Orientation.Horizontal)
        self.alb.setRange(0, 75)
        self.alb.setValue(self.skin["album_round"])
        self.alb.valueChanged.connect(lambda x: self._set("album_round", x))
        v.addWidget(self.alb)
        self.art_round = QCheckBox("Исполнители — круглые")
        self.art_round.setChecked(self.skin["artist_round"])
        self.art_round.setStyleSheet("color:#f0f0f0;")
        self.art_round.toggled.connect(lambda on: self._set("artist_round", on))
        v.addWidget(self.art_round)
        v.addStretch(1)
        sc.setWidget(inner)
        root.addWidget(sc)
        # ── справа: предпросмотр ──
        right = QVBoxLayout()
        pt = QLabel("ПРЕДПРОСМОТР")
        pt.setObjectName("Sec")
        right.addWidget(pt)
        self.preview = self._build_preview()
        right.addWidget(self.preview, 1)
        bot = QHBoxLayout()
        reset = QPushButton("Сбросить к стандартной")
        reset.clicked.connect(lambda: self._preset({}))
        bot.addWidget(reset)
        bot.addStretch(1)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        bot.addWidget(cancel)
        ok = QPushButton("Применить")
        ok.setObjectName("Accent")
        ok.clicked.connect(self._apply)
        bot.addWidget(ok)
        right.addLayout(bot)
        root.addLayout(right, 1)
        shell = getattr(win, "_ya", None)
        if shell is not None:
            from ya_decor_ui import DecorDialog
            decor = DecorDialog(shell, embedded=True)
            decor.setWindowFlags(Qt.WindowType.Widget)
            self.tabs.addTab(decor, "Живое оформление")
        self._refresh()

    def _font_file(self):
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        import custom_fonts
        fn, _ = QFileDialog.getOpenFileName(self, "Шрифт", "", custom_fonts.FILTER)
        if not fn:
            return
        try:
            fam = custom_fonts.import_font(fn)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Шрифт", f"Не удалось подключить шрифт: {e}")
            return
        self.font.blockSignals(True)
        self.font.setCurrentFont(QFont(fam))
        self.font.blockSignals(False)
        self._set("font", fam)

    def _sec(self, text):
        l = QLabel(text)
        l.setObjectName("Sec")
        return l

    def _choice(self, v, items, key) -> dict:
        row = QHBoxLayout()
        grp = QButtonGroup(self)
        out = {}
        for k, name in items:
            b = QPushButton(name)
            b.setCheckable(True)
            b.setChecked(self.skin[key] == k)
            b.clicked.connect(lambda _=False, k=k: self._set(key, k))
            grp.addButton(b)
            out[k] = b
            row.addWidget(b)
        v.addLayout(row)
        return out

    def _build_preview(self) -> QFrame:
        r = QFrame()
        r.setObjectName("PvRoot")
        h = QHBoxLayout(r)
        h.setContentsMargins(12, 12, 12, 12)
        h.setSpacing(10)
        side = QVBoxLayout()
        side.setSpacing(2)
        logo = QLabel("ECHOES")
        logo.setStyleSheet("font-size:16px;font-weight:900;padding:4px 10px 10px 10px;")
        self.pv_logo = logo
        side.addWidget(logo)
        for i, n in enumerate(("Моя волна", "Для вас", "Коллекция", "Echoes.NET", "Настройки")):
            b = QPushButton(n)
            b.setObjectName("PvNavOn" if i == 1 else "PvNav")
            side.addWidget(b)
        side.addStretch(1)
        sw = QWidget()
        sw.setFixedWidth(170)
        sw.setLayout(side)
        h.addWidget(sw)
        col = QVBoxLayout()
        col.setSpacing(10)
        panel = QFrame()
        panel.setObjectName("PvPanel")
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(18, 16, 18, 16)
        pv.setSpacing(10)
        hh = QLabel("Для вас")
        hh.setObjectName("PvH")
        pv.addWidget(hh)
        chips = QHBoxLayout()
        for i, n in enumerate(("Всё", "Новое", "Похожее", "Под настроение")):
            c = QPushButton(n)
            c.setObjectName("YaChip")
            c.setCheckable(True)
            c.setChecked(i == 0)
            chips.addWidget(c)
        chips.addStretch(1)
        pv.addLayout(chips)
        row = QHBoxLayout()
        a = QPushButton("Слушать")
        a.setObjectName("AccentBtn")
        row.addWidget(a)
        g = QPushButton("В коллекцию")
        row.addWidget(g)
        e = QLineEdit()
        e.setPlaceholderText("Поиск треков…")
        row.addWidget(e, 1)
        pv.addLayout(row)
        for t, s in (("cry", "lieu · 2:41"), ("under the tree", "m1v · 3:12"), ("blind", "Korn · 4:18")):
            cf = QFrame()
            cf.setObjectName("PvCard")
            cl = QHBoxLayout(cf)
            cl.setContentsMargins(10, 8, 10, 8)
            cv = QVBoxLayout()
            cv.setSpacing(0)
            cv.addWidget(QLabel(t))
            sl = QLabel(s)
            sl.setObjectName("PvSub")
            cv.addWidget(sl)
            cl.addLayout(cv, 1)
            lk = QPushButton("♥")
            lk.setCheckable(True)
            lk.setChecked(t == "cry")
            cl.addWidget(lk)
            pv.addWidget(cf)
        pv.addStretch(1)
        col.addWidget(panel, 1)
        pl = QFrame()
        pl.setObjectName("PvPlayer")
        plh = QHBoxLayout(pl)
        plh.setContentsMargins(14, 10, 14, 10)
        info = QVBoxLayout()
        info.setSpacing(0)
        info.addWidget(QLabel("cry"))
        il = QLabel("lieu")
        il.setObjectName("PvSub")
        info.addWidget(il)
        plh.addLayout(info)
        plh.addStretch(1)
        play = QPushButton("▶")
        play.setObjectName("AccentBtn")
        play.setFixedSize(40, 40)
        self.pv_play = play
        plh.addWidget(play)
        plh.addStretch(1)
        self.pv_bar = QSlider(Qt.Orientation.Horizontal)
        self.pv_bar.setValue(35)
        self.pv_bar.setFixedWidth(180)
        plh.addWidget(self.pv_bar)
        col.addWidget(pl)
        h.addLayout(col, 1)
        return r

    def _set(self, key, val):
        self.skin[key] = val
        self._refresh()

    def _preset(self, p):
        keep = {k: self.skin[k] for k in ("font", "size", "radius", "buttons", "bold", "title_font", "density",
                                          "album_round", "artist_round", "panel_radius")} if p else {}
        self.skin = normalize(dict(DEFAULT, **keep, **p))
        for k, sw in self.sw.items():
            sw.set(self.skin[k])
        for k, b in self.btn_style.items():
            b.setChecked(self.skin["buttons"] == k)
        self.size.setValue(self.skin["size"])
        self.rad.setValue(self.skin["radius"])
        self.panel_rad.setValue(self.skin["panel_radius"])
        self.bold.setChecked(self.skin["bold"])
        self.alb.setValue(self.skin["album_round"])
        self.art_round.setChecked(self.skin["artist_round"])
        for k, b in self.tf_btn.items():
            b.setChecked(self.skin["title_font"] == k)
        for k, b in self.den_btn.items():
            b.setChecked(self.skin["density"] == k)
        self._refresh()

    def _refresh(self):
        s = self.skin = normalize(self.skin)
        self.size_lbl.setText(f"Размер текста: {s['size']} px")
        self.rad_lbl.setText(f"Скругление кнопок: {s['radius']} px" + ("  (квадратные)" if s["radius"] == 0 else ""))
        self.panel_rad_lbl.setText(f"Панели и карточки: {s['panel_radius']} px")
        self.alb_lbl.setText("Обложки альбомов: " + ("квадрат" if s["album_round"] == 0 else
                                                     "круг" if s["album_round"] >= 75 else f"скругление {s['album_round']} px"))
        tf = TITLE_FAMILY.get(s["title_font"])
        f = QFont()
        if tf:
            f.setFamilies(tf)
        f.setPixelSize(16)
        f.setWeight(QFont.Weight.Black)
        self.pv_logo.setFont(f)
        self.preview.setStyleSheet(preview_qss(s))
        self.pv_logo.setStyleSheet(f"font-size:16px;font-weight:900;padding:4px 10px 10px 10px;color:{s['accent']};")
        self.pv_play.setStyleSheet(f"QPushButton{{border-radius:20px;padding:0;background:{s['accent']};color:{s['on_accent']};}}")
        self.pv_bar.setStyleSheet(f"QSlider::sub-page:horizontal{{background:{s['accent']};border-radius:2px;}}"
                                  "QSlider::groove:horizontal{height:4px;background:rgba(255,255,255,0.18);border-radius:2px;}"
                                  "QSlider::handle:horizontal{background:#fff;width:12px;height:12px;margin:-4px 0;border-radius:6px;}")

    def _apply(self):
        self.win.settings["ya_skin"] = dict(self.skin)
        try:
            self.win.save_settings()
        except Exception:                                      # noqa: BLE001
            pass
        self.accept()
        QTimer.singleShot(0, lambda: reskin(self.win))


def reskin(win):
    """Применить скин к открытому плееру: пересобрать интерфейс Echoes Music (сеть и музыка не прерываются)."""
    apply(win.settings.get("ya_skin"))
    if not getattr(win, "_ya_on", False):
        return
    page = getattr(getattr(win, "_ya", None), "_cur_page", None)
    try:
        win._leave_ya_layout()
        win._apply_theme(win.settings.get("theme") or "Echoes Music")
        if not getattr(win, "_ya_on", False):
            win._enter_ya_layout()
        if page and getattr(win, "_ya", None) is not None:
            win._ya.show_page(page)
    except Exception as e:                                     # noqa: BLE001
        print("[skin]", e)
