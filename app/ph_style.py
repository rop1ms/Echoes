# ph_style.py
"""
Стиль Phantom Audio для Echoes: токены, шрифт Inter, иконки Lucide, QSS стандартных виджетов и стеклянные
поверхности. Значения взяты из CSS самого Phantom 1.12.2 (`:root` и модули компонентов), см.
docs/PHANTOM_REDESIGN.md и снимки docs/phantom_ref/.

Здесь нет ни одного таймера и ни одной перерисовки сами по себе: только данные и функции рисования.
Живой фон (картинка, «атмосфера», пылинки) — в ph_backdrop.

Как пользоваться:
    import ph_style as ph
    ph.load_fonts()                      # один раз, после создания QApplication
    root.setFont(ph.font(ph.TEXT_BASE))  # шрифт по умолчанию для оболочки (наследуется детьми)
    root.setStyleSheet(ph.qss())         # QSS — только для виджетов с objectName Ph*
    btn.setObjectName("PhSecondary"); btn.setIcon(ph.icon("shuffle", 16))
    ph.paint_surface(painter, rect, "panel")   # стекло в paintEvent; тень — ph.paint_shadow у родителя

Почему стекло без размытия: фон под панелями у Phantom и так размыт (картинка 22–36 px + мягкие пятна
света), а заливка стекла — всего 4–8 % белого. Повторное размытие уже размытого фона на глаз ничего не
меняет, а стоит кадра. Поэтому стекло — это полупрозрачная заливка, блик и рамка; тени — готовые
картинки «девятью кусками» из кэша. Размытие нужно только под выезжающими панелями (там под ними резкий
интерфейс) — ph_backdrop.frozen_blur делает его один раз при открытии, а не на каждом кадре.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QByteArray, QEasingCurve, QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import (QColor, QFont, QFontDatabase, QIcon, QImage, QLinearGradient, QPainter,
                         QPainterPath, QPen, QPixmap)

ASSETS = Path(__file__).resolve().parent / "assets"

# ══════════════════════════════════════════════════════════════════════════ #
#  Токены (как в :root Phantom)
# ══════════════════════════════════════════════════════════════════════════ #

BG_VOID = "#030303"
BG_BASE = "#050505"
BG_RAISED = "#080808"
BG_HIGHEST = "#101010"
WHITE = "#ffffff"

# (r, g, b, a) — a в долях; css()/qcolor() превращают в строку QSS или QColor
TEXT_PRIMARY = (255, 255, 255, .96)
TEXT_SECONDARY = (255, 255, 255, .64)
TEXT_TERTIARY = (255, 255, 255, .42)
TEXT_GHOST = (255, 255, 255, .22)
LINE_1 = (255, 255, 255, .065)
LINE_2 = (255, 255, 255, .11)
LINE_3 = (255, 255, 255, .18)

R_XS, R_SM, R_MD, R_LG, R_XL, R_2XL, R_PILL = 6, 10, 14, 20, 26, 32, 999
S_1, S_2, S_3, S_4, S_5, S_6, S_7, S_8, S_9, S_10, S_11 = 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80

# размеры текста (px при масштабе 1; у Phantom 1rem = 16px)
TEXT_2XS, TEXT_XS, TEXT_SM, TEXT_MD, TEXT_BASE = 10, 11, 12, 13, 14
TEXT_LG, TEXT_XL, TEXT_2XL, TEXT_3XL, TEXT_4XL = 16, 20, 24, 32, 44

TRACKING_TIGHT, TRACKING_SNUG, TRACKING_WIDE = -.03, -.015, .14     # em
KICKER_TRACKING = .2
WORDMARK_TRACKING = .28

DUR_INSTANT, DUR_FAST, DUR_BASE, DUR_SLOW, DUR_SLOWER = 90, 150, 240, 420, 650   # мс

TOPBAR_HEIGHT = 72
LEFT_COLUMN, RIGHT_COLUMN = 41, 59      # доли колонок главного экрана

GLASS_BLUR = 28                         # px — для frozen_blur и настроек; в живом стекле не используется
GLASS_SATURATE = 1.18
SURFACE_ALPHA = .062                    # × прозрачность карточек (cardOpacity, по умолчанию .72)
SURFACE_STRONG_ALPHA = .105
GLASS_HIGHLIGHT = .055

# Настройки внешнего вида — как appearance у Phantom; оболочка меняет их через configure()
_CFG = {"card_opacity": .72, "ui_scale": 1.0, "effects": True, "motion": "system"}


def configure(**kw):
    """card_opacity 0..1, ui_scale 0.8..1.4, effects bool, motion 'system'|'reduce'|'full'."""
    for k, v in kw.items():
        if k in _CFG and v is not None:
            _CFG[k] = v


def setting(name):
    return _CFG[name]


def px(v: float) -> int:
    """Размер с учётом масштаба интерфейса."""
    return max(1, int(round(v * float(_CFG["ui_scale"]))))


def qcolor(c, alpha: float | None = None) -> QColor:
    """Токен (кортеж или '#hex') → QColor; alpha (0..1) — заменить прозрачность."""
    if isinstance(c, QColor):
        q = QColor(c)
    elif isinstance(c, tuple):
        q = QColor(int(c[0]), int(c[1]), int(c[2]), int(round(255 * (c[3] if len(c) > 3 else 1))))
    else:
        q = QColor(c)
    if alpha is not None:
        q.setAlphaF(max(0.0, min(1.0, alpha)))
    return q


def css(c, alpha: float | None = None) -> str:
    """Токен → строка для QSS: rgba(r,g,b,a)."""
    q = qcolor(c, alpha)
    return f"rgba({q.red()},{q.green()},{q.blue()},{q.alphaF():.3f})"


def white(a: float) -> QColor:
    return QColor(255, 255, 255, int(round(255 * max(0.0, min(1.0, a)))))


def surface_alpha(strong: bool = False) -> float:
    return (SURFACE_STRONG_ALPHA if strong else SURFACE_ALPHA) * float(_CFG["card_opacity"])


# Оттенок монохрома — из картинки фона (ph_backdrop считает его при каждой новой картинке): серое в волне,
# тирлисте, дуэли чуть окрашено под фон. Белый — нейтрально.
_TINT = [QColor(255, 255, 255)]


def set_tint(c: QColor):
    if QColor(c) == _TINT[0]:
        return
    _TINT[0] = QColor(c)
    import sys
    wave = sys.modules.get("ya_wave")                          # «Моя волна» на экране — перекрасить сразу
    if wave is not None and hasattr(wave, "retint"):
        wave.retint()


def tint() -> QColor:
    return QColor(_TINT[0])


def tone(level: int, alpha: int = 255, k: float = .22) -> QColor:
    """Серый яркости level (0..255), смешанный с оттенком фона на k (яркость сохраняется)."""
    t = _TINT[0]
    lum_t = max(1.0, .299 * t.red() + .587 * t.green() + .114 * t.blue())
    f = level / lum_t
    r, g, b = (min(255.0, c * f) for c in (t.red(), t.green(), t.blue()))
    mix = (lambda c: int(round(level + (c - level) * k)))
    return QColor(mix(r), mix(g), mix(b), alpha)


def mono_scheme(k: float = .38) -> tuple:
    """4 цвета туманности «Моей волны» в виде Phantom: ядро, середина, край, пятна — оттенок фона."""
    return tuple(tone(v, k=k).name() for v in (255, 190, 112, 220))


def motion_reduced() -> bool:
    return _CFG["motion"] == "reduce" or not _CFG["effects"]


def ease_out() -> QEasingCurve:
    """cubic-bezier(.16, 1, .3, 1) — главная кривая Phantom (быстрый старт, долгое мягкое торможение)."""
    c = QEasingCurve(QEasingCurve.Type.BezierSpline)
    c.addCubicBezierSegment(QPointF(.16, 1.0), QPointF(.3, 1.0), QPointF(1.0, 1.0))
    return c


def ease_out_soft() -> QEasingCurve:
    c = QEasingCurve(QEasingCurve.Type.BezierSpline)
    c.addCubicBezierSegment(QPointF(.22, 1.0), QPointF(.36, 1.0), QPointF(1.0, 1.0))
    return c


def ease_in_out() -> QEasingCurve:
    c = QEasingCurve(QEasingCurve.Type.BezierSpline)
    c.addCubicBezierSegment(QPointF(.65, 0.0), QPointF(.35, 1.0), QPointF(1.0, 1.0))
    return c


def duration(ms: int) -> int:
    """Длительность анимации с учётом «уменьшенного движения» (там — без анимации)."""
    return 0 if motion_reduced() else int(ms)


# ══════════════════════════════════════════════════════════════════════════ #
#  Шрифт: Inter Variable (OFL), разбит по алфавитам — Qt подставляет по символу
# ══════════════════════════════════════════════════════════════════════════ #

FAMILIES = ["Inter PA", "Inter PA Cyr", "Inter PA Ext", "Inter PA CyrExt", "Inter PA Greek",
            "Segoe UI Variable Text", "Segoe UI", "ECHOES Symbols"]
MONO_FAMILIES = ["Cascadia Mono", "Consolas", "Inter PA"]
_FONTS_LOADED: bool | None = None


def load_fonts() -> bool:
    """Подключить Inter (один раз; нужен QGuiApplication). True — если подключился хоть один файл."""
    global _FONTS_LOADED
    if _FONTS_LOADED is not None:
        return _FONTS_LOADED
    ok = False
    for f in sorted((ASSETS / "fonts" / "inter").glob("*.ttf")):
        if QFontDatabase.addApplicationFont(str(f)) >= 0:
            ok = True
    sym = ASSETS / "EchoesSymbols.ttf"
    if sym.exists():
        QFontDatabase.addApplicationFont(str(sym))
    # в Inter нет стрелок и части значков (→ ▾ ✓ ★): без замены Qt рисовал их квадратиками там, где в таблице
    # стилей указан только Inter
    from PyQt6.QtGui import QFont as _QF
    for fam in FAMILIES[:5]:
        _QF.insertSubstitutions(fam, ["Segoe UI", "Segoe UI Symbol", "ECHOES Symbols"])
    _FONTS_LOADED = ok
    return ok


def font(size: float = TEXT_BASE, weight: int = 400, tracking: float = 0.0, tnum: bool = False,
         mono: bool = False, scaled: bool = True) -> QFont:
    """size — px (по умолчанию с учётом масштаба интерфейса), weight 100..900 (Inter — переменный,
    промежуточные 450/550/650 тоже работают), tracking — межбуквенный интервал в em."""
    f = QFont()
    f.setFamilies(MONO_FAMILIES if mono else FAMILIES)
    p = px(size) if scaled else max(1, int(round(size)))
    f.setPixelSize(p)
    f.setWeight(QFont.Weight(max(100, min(900, int(weight)))))
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    if tracking:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, tracking * p)
    if tnum:
        try:
            f.setFeature(QFont.Tag("tnum"), 1)
        except (AttributeError, TypeError):                    # Qt < 6.7
            pass
    return f


def font_css(f: QFont) -> str:
    """Шрифт как свойства QSS. Нужен, потому что таблица стилей Echoes Music задаёт всем виджетам
    `font-family … font-size:13px`, а шрифт из QSS всегда перебивает setFont. Вес в QSS — только сотни
    (450 → 500, 550 → 600, 650 → 700)."""
    fams = ",".join(f'"{x}"' for x in (f.families() or FAMILIES))
    w = max(100, min(900, int(int(f.weight()) / 100.0 + .5) * 100))
    size = f.pixelSize() if f.pixelSize() > 0 else int(round(f.pointSizeF() * 96 / 72))
    css = f"font-family:{fams}; font-size:{size}px; font-weight:{w};"
    if f.letterSpacingType() == QFont.SpacingType.AbsoluteSpacing and abs(f.letterSpacing()) > .01:
        css += f" letter-spacing:{f.letterSpacing():.2f}px;"
    return css


def set_font(widget, f: QFont):
    """setFont + тот же шрифт собственной таблицей стилей виджета (у неё приоритет над общей таблицей).
    Затирает прежнюю таблицу стилей виджета — для наших виджетов её нет."""
    widget.setFont(f)
    widget.setStyleSheet(font_css(f))


def kicker_font() -> QFont:
    """LYRICS · NOW PLAYING · QUEUE: 10–11 px, 600, капс, разрядка .2em (капс делает сам текст)."""
    return font(TEXT_2XS, 600, KICKER_TRACKING)


def wordmark_font() -> QFont:
    return font(TEXT_SM, 600, WORDMARK_TRACKING)


def title_font(size: float = 20) -> QFont:
    """.pa-title: 19–22 px, 600, −.02em."""
    return font(size, 600, -.02)


def display_font(size: float = 36) -> QFont:
    """.pa-display: 28–44 px, 650, −.035em."""
    return font(size, 650, -.035)


# ══════════════════════════════════════════════════════════════════════════ #
#  Иконки: Lucide (как в Phantom), штрих 1.75, скругления
# ══════════════════════════════════════════════════════════════════════════ #

# имена Echoes → имена Lucide (иконки, которых не было в Phantom, дописываем в ph_icons_data.EXTRA)
ALIASES = {
    "close": "x", "more": "ellipsis", "prev": "skip-back", "next": "skip-forward", "like": "heart",
    "volume": "volume-2", "mute": "volume-x", "queue": "list-music", "settings": "settings",
    "library": "library", "global": "earth", "lyrics": "mic-vocal", "expand": "maximize-2",
    "add": "plus", "delete": "trash", "edit": "pencil", "reload": "refresh-cw", "folder": "folder-open",
}
_ICON_CACHE: dict = {}
_ICON_CACHE_MAX = 400


def _icon_body(name: str) -> str:
    import ph_icons_data as data
    name = ALIASES.get(name, name)
    body = data.ICONS.get(name)
    if body is None:
        body = getattr(data, "EXTRA", {}).get(name)
    return body or ""


def has_icon(name: str) -> bool:
    return bool(_icon_body(name))


def icon_pixmap(name: str, size: int = 16, color=TEXT_SECONDARY, stroke: float = 1.75,
                dpr: float = 2.0, fill=None) -> QPixmap:
    """Иконка size×size (логических px) цвета color. Неизвестное имя — пустая картинка."""
    q = qcolor(color)
    fq = qcolor(fill) if fill is not None else None
    key = (name, int(size), q.rgba(), round(stroke, 2), dpr, fq.rgba() if fq else None)
    pm = _ICON_CACHE.get(key)
    if pm is not None:
        return pm
    from PyQt6.QtSvg import QSvgRenderer
    side = max(1, int(round(size * dpr)))
    pm = QPixmap(side, side)
    pm.fill(Qt.GlobalColor.transparent)
    body = _icon_body(name)
    if body:
        col = f"rgb({q.red()},{q.green()},{q.blue()})"
        fill_attr = f"rgb({fq.red()},{fq.green()},{fq.blue()})" if fq else "none"
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
               f'fill="{fill_attr}" stroke="{col}" stroke-width="{stroke}" stroke-opacity="{q.alphaF():.3f}" '
               f'fill-opacity="{(fq.alphaF() if fq else 0):.3f}" stroke-linecap="round" stroke-linejoin="round">'
               f'{body}</svg>')
        r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r.render(p, QRectF(0, 0, side, side))
        p.end()
    pm.setDevicePixelRatio(dpr)
    if len(_ICON_CACHE) >= _ICON_CACHE_MAX:
        _ICON_CACHE.clear()
    _ICON_CACHE[key] = pm
    return pm


def icon(name: str, size: int = 16, color=TEXT_SECONDARY, active=TEXT_PRIMARY, stroke: float = 1.75,
         checked=None, disabled=TEXT_GHOST) -> QIcon:
    """QIcon с состояниями: обычная — color, наведение/нажатие — active, включённая (checkable) — checked
    (по умолчанию как active), выключенная — disabled. Цвета наведения QPushButton берёт из Mode.Active."""
    ic = QIcon()
    ic.addPixmap(icon_pixmap(name, size, color, stroke), QIcon.Mode.Normal, QIcon.State.Off)
    ic.addPixmap(icon_pixmap(name, size, active, stroke), QIcon.Mode.Active, QIcon.State.Off)
    on = checked if checked is not None else active
    ic.addPixmap(icon_pixmap(name, size, on, stroke), QIcon.Mode.Normal, QIcon.State.On)
    ic.addPixmap(icon_pixmap(name, size, on, stroke), QIcon.Mode.Active, QIcon.State.On)
    ic.addPixmap(icon_pixmap(name, size, disabled, stroke), QIcon.Mode.Disabled, QIcon.State.Off)
    return ic


# ══════════════════════════════════════════════════════════════════════════ #
#  QSS — для виджетов с objectName Ph* (ничего чужого не трогает)
# ══════════════════════════════════════════════════════════════════════════ #

def _switch_assets() -> dict:
    """PNG для QCheckBox#PhSwitch: дорожка 40×22, ручка 16 px (как у Phantom). Рисуются один раз в 4×."""
    import data_home
    d = data_home.root() / "ui_cache" / "ph"
    out = {k: d / f"{k}.png" for k in ("sw_off", "sw_on", "sw_off_h", "sw_on_h", "chev")}
    if all(p.exists() for p in out.values()) and (d / "v1").exists():
        return {k: p.as_posix() for k, p in out.items()}
    try:
        d.mkdir(parents=True, exist_ok=True)
        W, H, S = 40, 22, 4
        for key, on, hover in (("sw_off", False, False), ("sw_on", True, False),
                               ("sw_off_h", False, True), ("sw_on_h", True, True)):
            img = QImage(W * S, H * S, QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(Qt.GlobalColor.transparent)
            p = QPainter(img)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            r = QRectF(.5 * S, .5 * S, (W - 1) * S, (H - 1) * S)
            if on:
                p.setPen(QPen(white(1.0 if hover else .9), S))
                p.setBrush(white(1.0 if hover else .9))
            else:
                p.setPen(QPen(qcolor(LINE_3 if hover else LINE_2), S))
                p.setBrush(white(.07))
            p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
            k = 16 * S
            x = (W - 3) * S - k if on else 3 * S
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(BG_RAISED) if on else white(.72))
            p.drawEllipse(QRectF(x, (H * S - k) / 2, k, k))
            p.end()
            img.scaled(W * 2, H * 2, Qt.AspectRatioMode.IgnoreAspectRatio,
                       Qt.TransformationMode.SmoothTransformation).save(str(out[key]))
        icon_pixmap("chevron-down", 12, TEXT_SECONDARY, 2.0, 2.0).save(str(out["chev"]))
        (d / "v1").write_text("1", "utf-8")
    except Exception:                                          # noqa: BLE001 — без картинок QSS просто проще
        pass
    return {k: p.as_posix() for k, p in out.items()}


def qss() -> str:
    """Таблица стилей Phantom. Шрифт (семейство) не задаётся — его даёт setFont корня оболочки."""
    a = _switch_assets()
    t1, t2, t3, tg = css(TEXT_PRIMARY), css(TEXT_SECONDARY), css(TEXT_TERTIARY), css(TEXT_GHOST)
    l1, l2, l3 = css(LINE_1), css(LINE_2), css(LINE_3)
    gf, gfs = css(WHITE, surface_alpha()), css(WHITE, surface_alpha(True))
    sm, xs = px(TEXT_SM), px(TEXT_XS)
    rxs, rsm, rmd = px(R_XS), px(R_SM), px(R_MD)

    def bx(n):                      # размер с рамкой 1 px: в QSS min/max — без рамки, у Phantom — с ней
        return px(n) - 2
    return f"""
/* ── текст ── */
/* шрифты подписей и кнопок задаются в коде (ph.font / ph_widgets): QSS не знает весов 450/550/650
   переменного Inter и перебивал бы setFont */
QLabel#PhKicker {{ color:{t3}; }}
QLabel#PhWordmark, QLabel#PhTitle, QLabel#PhDisplay, QLabel#PhHeading, QLabel#PhBody {{ color:{t1}; }}
QLabel#PhSub {{ color:{t2}; }}
QLabel#PhMuted {{ color:{t3}; }}
QLabel#PhGhost {{ color:{tg}; }}
QLabel#PhBadge {{ color:{t2}; padding:0 5px; min-height:18px; max-height:18px;
    border:1px solid {l1}; border-radius:{rxs}px; }}

/* ── кнопки: основная (белая), вторичная (стекло), призрачная ── */
QPushButton#PhPrimary, QPushButton#PhSecondary, QPushButton#PhGhost, QPushButton#PhDanger, QToolButton#PhSecondary {{
    min-height:{bx(34)}px; max-height:{bx(34)}px; padding:0 {px(14)}px; border-radius:{rsm}px; }}
QPushButton#PhPrimary {{ color:#050505; background:rgba(255,255,255,0.92); border:1px solid rgba(255,255,255,0.92); }}
QPushButton#PhPrimary:hover {{ background:#ffffff; border-color:#ffffff; }}
QPushButton#PhPrimary:pressed {{ background:rgba(255,255,255,0.84); }}
QPushButton#PhSecondary, QToolButton#PhSecondary {{ color:{t1}; background:rgba(255,255,255,0.055); border:1px solid {l2}; }}
QPushButton#PhSecondary:hover, QToolButton#PhSecondary:hover {{ border-color:{l3}; }}
QPushButton#PhSecondary:pressed {{ }}
QPushButton#PhSecondary:checked {{ background:rgba(255,255,255,0.12); border-color:{l3}; }}
QPushButton#PhGhost {{ color:{t2}; background:transparent; border:1px solid transparent; }}
QPushButton#PhGhost:hover {{ color:{t1}; }}
QPushButton#PhDanger {{ color:{t1}; background:rgba(255,255,255,0.04); border:1px solid {l2}; }}
QPushButton#PhDanger:hover {{ border-color:{l3}; }}
QPushButton#PhPrimary:disabled, QPushButton#PhSecondary:disabled, QPushButton#PhGhost:disabled {{ color:{tg}; }}
QPushButton#PhPrimary:disabled {{ color:rgba(5,5,5,0.55); background:rgba(255,255,255,0.55); border-color:rgba(255,255,255,0.55); }}
QPushButton#PhSmall {{ min-height:{bx(28)}px; max-height:{bx(28)}px; padding:0 {px(10)}px; border-radius:{px(14)}px;
    color:{t1}; background:rgba(255,255,255,0.045); border:1px solid {l2}; }}
QPushButton#PhSmall:hover {{ border-color:{l3}; }}
QPushButton#PhSmall:disabled {{ color:{tg}; border-color:{l1}; background:transparent; }}

/* ── круглые кнопки-иконки: ghost / surface / solid; размер — свойство phSize sm|md|lg ── */
QPushButton#PhIcon, QPushButton#PhIconSurface, QPushButton#PhIconSolid, QToolButton#PhIcon {{
    min-width:{bx(34)}px; max-width:{bx(34)}px; min-height:{bx(34)}px; max-height:{bx(34)}px; padding:0;
    border-radius:{px(17)}px; border:1px solid transparent; background:transparent; }}
QPushButton#PhIcon[phSize="sm"], QPushButton#PhIconSurface[phSize="sm"], QPushButton#PhIconSolid[phSize="sm"] {{
    min-width:{bx(28)}px; max-width:{bx(28)}px; min-height:{bx(28)}px; max-height:{bx(28)}px; border-radius:{px(14)}px; }}
QPushButton#PhIcon[phSize="top"], QPushButton#PhIconSurface[phSize="top"] {{
    min-width:{bx(30)}px; max-width:{bx(30)}px; min-height:{bx(30)}px; max-height:{bx(30)}px; border-radius:{px(15)}px; }}
QPushButton#PhIcon[phSize="lg"], QPushButton#PhIconSurface[phSize="lg"], QPushButton#PhIconSolid[phSize="lg"] {{
    min-width:{bx(40)}px; max-width:{bx(40)}px; min-height:{bx(40)}px; max-height:{bx(40)}px; border-radius:{px(20)}px; }}
QPushButton#PhIconSolid[phSize="play"] {{
    min-width:{bx(44)}px; max-width:{bx(44)}px; min-height:{bx(44)}px; max-height:{bx(44)}px; border-radius:{px(22)}px; }}
QPushButton#PhIcon:hover, QToolButton#PhIcon:hover {{ }}
QPushButton#PhIcon:checked {{ background:rgba(255,255,255,0.12); border-color:{l2}; }}
QPushButton#PhIconSurface {{ background:{gf}; border-color:{l1}; }}
QPushButton#PhIconSurface:hover {{ border-color:{l2}; }}
QPushButton#PhIconSurface:checked {{ background:rgba(255,255,255,0.12); border-color:{l2}; }}
QPushButton#PhIconSolid {{ background:#ffffff; border-color:#ffffff; }}
QPushButton#PhIconSolid:hover {{ background:rgba(255,255,255,0.92); }}
QPushButton#PhIconSolid:pressed {{ background:rgba(255,255,255,0.86); }}
QPushButton#PhIcon:disabled, QPushButton#PhIconSurface:disabled {{ background:transparent; border-color:transparent; }}

/* кнопки окна (свернуть/развернуть/закрыть): 42×32, прямоугольные */
QPushButton#PhWindow, QPushButton#PhWindowClose {{ min-width:{px(42)}px; max-width:{px(42)}px;
    min-height:{px(32)}px; max-height:{px(32)}px; padding:0; border:0; border-radius:{rxs}px; background:transparent; }}
QPushButton#PhWindow:hover {{ background:rgba(255,255,255,0.07); }}
QPushButton#PhWindowClose:hover {{ background:rgba(232,17,35,0.85); }}

/* ── сегменты (вкладки Треки | Плейлисты | Папки, LIVE | ТЕКСТ, меню Echoes) ── */
QFrame#PhSegments {{ background:{gf}; border:1px solid {l1}; border-radius:{px(17)}px; }}
QFrame#PhSegments[phCompact="true"] {{ border-radius:{px(15)}px; }}
QPushButton#PhSegment {{ min-height:{bx(28)}px; max-height:{bx(28)}px; padding:0 {px(14)}px; border-radius:{px(14)}px;
    color:{t3}; background:transparent; border:1px solid transparent; }}
QPushButton#PhSegment:hover {{ color:{t2}; }}
QPushButton#PhSegment:checked {{ color:{t1}; background:transparent; border-color:transparent; }}  /* плашку рисуют PhSegments — она едет */
QFrame#PhSegments[phCompact="true"] QPushButton#PhSegment {{ min-height:{bx(22)}px; max-height:{bx(22)}px;
    padding:0 {px(8)}px; border-radius:{px(11)}px; }}

/* ── пилюли-фильтры ── */
QPushButton#PhChip {{ min-height:{bx(28)}px; max-height:{bx(28)}px; padding:0 {px(10)}px; border-radius:{px(14)}px;
    color:{t3}; background:rgba(255,255,255,0.03); border:1px solid {l1}; }}
QPushButton#PhChip:hover {{ color:{t2}; }}
QPushButton#PhChip:checked {{ color:{t1}; background:rgba(255,255,255,0.10); border-color:{l3}; }}

/* ── поля ввода ── */
QLineEdit#PhInput, QLineEdit#PhSearch, QPlainTextEdit#PhInput, QTextEdit#PhInput, QSpinBox#PhInput {{
    color:{t1}; background:rgba(255,255,255,0.035); border:1px solid {l1}; border-radius:{rsm}px;
    padding:0 {px(12)}px; min-height:{bx(34)}px; font-size:{sm}px;
    selection-background-color:rgba(255,255,255,0.88); selection-color:#050505; }}
QLineEdit#PhSearch {{ min-height:{bx(40)}px; border-radius:{px(12)}px; padding-left:{px(36)}px; }}
QLineEdit#PhInput:hover, QLineEdit#PhSearch:hover, QPlainTextEdit#PhInput:hover {{ border-color:{l2}; }}
QLineEdit#PhInput:focus, QLineEdit#PhSearch:focus, QPlainTextEdit#PhInput:focus {{
    border-color:rgba(255,255,255,0.42); background:rgba(255,255,255,0.05); }}

/* ── выпадающий список ── */
QComboBox#PhSelect {{ color:{t1}; background:rgba(255,255,255,0.04); border:1px solid {l2}; border-radius:{rsm}px;
    min-height:{bx(30)}px; padding:0 {px(28)}px 0 {px(10)}px; font-size:{xs}px; font-weight:600; }}
QComboBox#PhSelect:hover {{ border-color:{l3}; background:rgba(255,255,255,0.07); }}
QComboBox#PhSelect::drop-down {{ border:0; width:{px(24)}px; }}
QComboBox#PhSelect::down-arrow {{ image:url({a['chev']}); width:12px; height:12px; }}
QComboBox#PhSelect QAbstractItemView {{ background:rgba(13,13,13,0.97); border:1px solid {l2}; border-radius:{rmd}px;
    padding:6px; color:{t2}; outline:0; selection-background-color:rgba(255,255,255,0.07); selection-color:{t1}; }}

/* ── ползунок настроек: дорожка 3 px, белый кружок 12 px ── */
QSlider#PhSlider {{ min-height:{px(20)}px; background:transparent; }}
QSlider#PhSlider::groove:horizontal {{ height:3px; background:rgba(255,255,255,0.12); border-radius:1px; }}
QSlider#PhSlider::sub-page:horizontal {{ height:3px; background:rgba(255,255,255,0.86); border-radius:1px; }}
QSlider#PhSlider::add-page:horizontal {{ height:3px; background:rgba(255,255,255,0.12); border-radius:1px; }}
QSlider#PhSlider::handle:horizontal {{ width:12px; height:12px; margin:-5px 0; border-radius:6px; background:#ffffff; }}
QSlider#PhSlider::handle:horizontal:hover {{ width:14px; height:14px; margin:-6px 0; border-radius:7px; }}
QSlider#PhSlider:disabled {{ background:transparent; }}
QSlider#PhSlider::sub-page:horizontal:disabled {{ background:rgba(255,255,255,0.30); }}

/* ── переключатель ── */
QCheckBox#PhSwitch {{ color:{t1}; spacing:{px(16)}px; min-height:{px(36)}px; }}
QCheckBox#PhSwitch::indicator {{ width:40px; height:22px; }}
QCheckBox#PhSwitch::indicator:unchecked {{ image:url({a['sw_off']}); }}
QCheckBox#PhSwitch::indicator:unchecked:hover {{ image:url({a['sw_off_h']}); }}
QCheckBox#PhSwitch::indicator:checked {{ image:url({a['sw_on']}); }}
QCheckBox#PhSwitch::indicator:checked:hover {{ image:url({a['sw_on_h']}); }}

/* ── прокрутка: тонкая, без дорожки ── */
QScrollArea#PhScroll, QScrollArea#PhScroll > QWidget > QWidget {{ background:transparent; border:0; }}
QAbstractScrollArea#PhScroll, QListView#PhList, QTreeView#PhList {{ background:transparent; border:0; outline:0; }}
QWidget#PhRoot QScrollBar:vertical, QScrollBar#PhScrollBar:vertical {{ width:8px; background:transparent; margin:2px 0; }}
QWidget#PhRoot QScrollBar::handle:vertical, QScrollBar#PhScrollBar::handle:vertical {{
    min-height:32px; border-radius:3px; margin:0 2px; background:rgba(255,255,255,0.12); }}
QWidget#PhRoot QScrollBar::handle:vertical:hover, QScrollBar#PhScrollBar::handle:vertical:hover {{ background:rgba(255,255,255,0.22); }}
QWidget#PhRoot QScrollBar:horizontal {{ height:8px; background:transparent; margin:0 2px; }}
QWidget#PhRoot QScrollBar::handle:horizontal {{ min-width:32px; border-radius:3px; margin:2px 0; background:rgba(255,255,255,0.12); }}
QWidget#PhRoot QScrollBar::add-line, QWidget#PhRoot QScrollBar::sub-line,
QWidget#PhRoot QScrollBar::add-page, QWidget#PhRoot QScrollBar::sub-page,
QScrollBar#PhScrollBar::add-line, QScrollBar#PhScrollBar::sub-line,
QScrollBar#PhScrollBar::add-page, QScrollBar#PhScrollBar::sub-page {{ width:0; height:0; background:transparent; border:0; }}

/* ── меню и подсказки ── */
QWidget#PhRoot QMenu, QMenu#PhMenu {{ background:rgba(13,13,13,0.95); border:1px solid {l2}; border-radius:{rmd}px; padding:6px; }}
QWidget#PhRoot QMenu::item, QMenu#PhMenu::item {{ color:{t2}; min-height:{px(34)}px; padding:0 {px(14)}px 0 {px(10)}px;
    border-radius:{rxs}px; font-size:{sm}px; }}
QWidget#PhRoot QMenu::item:selected, QMenu#PhMenu::item:selected {{ color:{t1}; background:rgba(255,255,255,0.07); }}
QWidget#PhRoot QMenu::item:disabled, QMenu#PhMenu::item:disabled {{ color:{tg}; }}
QWidget#PhRoot QMenu::separator, QMenu#PhMenu::separator {{ height:1px; background:{l1}; margin:4px 6px; }}
QWidget#PhRoot QMenu::icon, QMenu#PhMenu::icon {{ padding-left:4px; }}
QWidget#PhRoot QToolTip, QToolTip#PhTip {{ color:{t1}; background:rgba(13,13,13,0.96); border:1px solid {l2};
    border-radius:8px; padding:5px 8px; font-size:{xs}px; }}

/* ── разделитель-волосок ── */
QFrame#PhHairline {{ background:{l1}; border:0; min-height:1px; max-height:1px; }}
"""


def app_qss() -> str:
    """Phantom для ВСЕГО окна (не только виджетов Ph*): дописывается в конец QSS темы Echoes Music, пока выбран
    вид Phantom (ya_skin, скин «Phantom»). Перекрашивает стандартные кнопки, поля, списки, вкладки, флажки,
    ползунки, меню, подсказки, диалоги и всплывашки, страницы Echoes (#Ya*, #Net*) — монохромом Phantom."""
    t1, t2, t3, tg = css(TEXT_PRIMARY), css(TEXT_SECONDARY), css(TEXT_TERTIARY), css(TEXT_GHOST)
    l1, l2, l3 = css(LINE_1), css(LINE_2), css(LINE_3)
    fams = ",".join(f'"{f}"' for f in FAMILIES)
    sw = _switch_assets()
    return f"""
/* ═══ Phantom: всё окно ═══ */
QWidget {{ font-family:{fams}; color:{t1}; }}
QToolTip {{ color:{t1}; background:rgba(13,13,13,0.96); border:1px solid {l2}; border-radius:8px; padding:5px 8px;
    font-size:11px; }}
QMenu {{ background:rgba(13,13,13,0.97); border:1px solid {l2}; border-radius:14px; padding:6px; }}
QMenu::item {{ color:{t2}; min-height:30px; padding:0 14px 0 10px; border-radius:6px; font-size:12px;
    background:transparent; }}
QMenu::item:selected {{ color:{t1}; background:rgba(255,255,255,0.07); }}
QMenu::item:disabled {{ color:{tg}; }}
QMenu::separator {{ height:1px; background:{l1}; margin:4px 6px; }}
QMenu::section {{ color:{t3}; font-size:10px; font-weight:600; padding:6px 10px; }}

/* кнопки: вторичная — стекло, отмеченная — светлее; акцентные — белые (как «играть» у Phantom) */
QPushButton, QToolButton {{ color:{t1}; background:rgba(255,255,255,0.055); border:1px solid {l2};
    border-radius:10px; }}
QPushButton:hover, QToolButton:hover {{ border-color:{l3}; }}
QPushButton:pressed, QToolButton:pressed {{ }}
QPushButton:checked, QToolButton:checked {{ color:{t1}; background:rgba(255,255,255,0.13); border-color:{l3}; }}
QPushButton:disabled, QToolButton:disabled {{ color:{tg}; background:transparent; border-color:{l1}; }}
QPushButton#AccentBtn, QPushButton#YaYellow,
QPushButton#NetPrimary, QPushButton#PrimaryBtn {{ color:#050505; background:rgba(255,255,255,0.92);
    border:1px solid rgba(255,255,255,0.92); }}
QPushButton#AccentBtn:hover, QPushButton#YaYellow:hover, QPushButton#NetPrimary:hover,
QPushButton#PrimaryBtn:hover {{ background:#ffffff; border-color:#ffffff; }}
QPushButton#YaChip, QPushButton#YaSeg {{ color:{t3}; background:rgba(255,255,255,0.03); border:1px solid {l1};
    border-radius:14px; font-weight:500; }}
QPushButton#YaChip:hover, QPushButton#YaSeg:hover {{ color:{t2}; }}
QPushButton#YaChip:checked, QPushButton#YaSeg:checked {{ border-radius:14px; color:{t1};
    background:rgba(255,255,255,0.13); border:1px solid {l2}; }}   /* выбранная — стеклянная пилюля, как у Phantom */
QFrame#YaSegTrack {{ background:rgba(255,255,255,0.045); border:1px solid {l1}; border-radius:17px; }}
QPushButton#YaNav {{ color:{t2}; background:transparent; border:1px solid transparent; border-radius:10px; }}
QPushButton#YaNav:hover {{ color:{t1}; }}
QPushButton#YaNav:checked {{ color:{t1}; background:rgba(255,255,255,0.12); border-color:{l2}; }}
QPushButton#GhostBtn {{ color:{t2}; background:transparent; border:1px solid transparent; }}
QPushButton#GhostBtn:hover {{ color:{t1}; }}

/* поля ввода и списки выбора */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit, QTimeEdit {{
    color:{t1}; background:rgba(255,255,255,0.035); border:1px solid {l1}; border-radius:10px;
    selection-background-color:rgba(255,255,255,0.88); selection-color:#050505; }}
QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QSpinBox:hover, QComboBox:hover {{ border-color:{l2}; }}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color:rgba(255,255,255,0.42); background:rgba(255,255,255,0.05); }}
QComboBox::drop-down {{ border:0; width:22px; }}
QComboBox::down-arrow {{ image:url({sw['chev']}); width:12px; height:12px; }}
QComboBox QAbstractItemView {{ background:rgba(13,13,13,0.97); border:1px solid {l2}; border-radius:12px; padding:6px;
    color:{t2}; outline:0; selection-background-color:rgba(255,255,255,0.07); selection-color:{t1}; }}

/* флажки — переключатели Phantom, радио — кружки */
QCheckBox {{ color:{t1}; spacing:10px; background:transparent; }}
QCheckBox::indicator {{ width:40px; height:22px; }}
QCheckBox::indicator:unchecked {{ image:url({sw['sw_off']}); }}
QCheckBox::indicator:unchecked:hover {{ image:url({sw['sw_off_h']}); }}
QCheckBox::indicator:checked {{ image:url({sw['sw_on']}); }}
QCheckBox::indicator:checked:hover {{ image:url({sw['sw_on_h']}); }}
QRadioButton {{ color:{t1}; spacing:8px; background:transparent; }}
QRadioButton::indicator {{ width:14px; height:14px; border-radius:7px; border:1px solid {l3}; background:transparent; }}
QRadioButton::indicator:checked {{ background:#ffffff; border:4px solid #1a1a1a; }}

/* ползунки: дорожка 3 px, белая заливка, кружок 12 px */
QSlider::groove:horizontal {{ height:3px; background:rgba(255,255,255,0.12); border-radius:1px; }}
QSlider::sub-page:horizontal {{ height:3px; background:rgba(255,255,255,0.86); border-radius:1px; }}
QSlider::add-page:horizontal {{ height:3px; background:rgba(255,255,255,0.12); border-radius:1px; }}
QSlider::handle:horizontal {{ width:12px; height:12px; margin:-5px 0; border-radius:6px; background:#ffffff;
    border:0; }}
QSlider::groove:vertical {{ width:3px; background:rgba(255,255,255,0.12); border-radius:1px; }}
QSlider::add-page:vertical {{ width:3px; background:rgba(255,255,255,0.86); border-radius:1px; }}
QSlider::sub-page:vertical {{ width:3px; background:rgba(255,255,255,0.12); border-radius:1px; }}
QSlider::handle:vertical {{ width:12px; height:12px; margin:0 -5px; border-radius:6px; background:#ffffff; border:0; }}
QProgressBar {{ background:rgba(255,255,255,0.10); border:0; border-radius:2px; color:transparent; max-height:4px; }}
QProgressBar::chunk {{ background:rgba(255,255,255,0.86); border-radius:2px; }}

/* вкладки — сегменты */
QTabWidget::pane {{ border:1px solid {l1}; border-radius:14px; background:rgba(255,255,255,0.02); top:-1px; }}
QTabBar::tab {{ color:{t3}; background:transparent; border:1px solid transparent; border-radius:12px;
    padding:6px 14px; margin:2px; font-weight:600; }}
QTabBar::tab:hover {{ color:{t2}; }}
QTabBar::tab:selected {{ color:{t1}; background:rgba(255,255,255,0.12); border-color:{l2}; }}

/* списки и таблицы */
QListView, QListWidget, QTreeView, QTreeWidget, QTableView, QTableWidget {{ background:transparent; border:0;
    outline:0; color:{t1}; selection-background-color:rgba(255,255,255,0.08); selection-color:{t1};
    alternate-background-color:rgba(255,255,255,0.02); }}
QListView::item:hover, QListWidget::item:hover, QTreeView::item:hover {{ background:rgba(255,255,255,0.045); }}
QListView::item:selected, QListWidget::item:selected, QTreeView::item:selected {{
    background:rgba(255,255,255,0.09); color:{t1}; }}
QHeaderView::section {{ color:{t3}; background:transparent; border:0; border-bottom:1px solid {l1}; padding:6px 8px;
    font-size:10px; font-weight:600; }}

/* прокрутка — тонкая, без дорожки */
QScrollBar:vertical {{ width:8px; background:transparent; margin:2px 0; border:0; }}
QScrollBar::handle:vertical {{ min-height:32px; border-radius:3px; margin:0 2px; background:rgba(255,255,255,0.12); }}
QScrollBar::handle:vertical:hover {{ background:rgba(255,255,255,0.22); }}
QScrollBar:horizontal {{ height:8px; background:transparent; margin:0 2px; border:0; }}
QScrollBar::handle:horizontal {{ min-width:32px; border-radius:3px; margin:2px 0; background:rgba(255,255,255,0.12); }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ width:0; height:0;
    background:transparent; border:0; }}

/* диалоги, группы, разделители */
QDialog, QMessageBox, QInputDialog, QFileDialog, QColorDialog, QFontDialog {{ background:#0b0b0b; color:{t1}; }}
QMessageBox QLabel {{ color:{t1}; background:transparent; }}
QGroupBox {{ color:{t2}; border:1px solid {l1}; border-radius:14px; margin-top:14px; padding-top:8px;
    background:rgba(255,255,255,0.02); }}
QGroupBox::title {{ subcontrol-origin:margin; left:12px; padding:0 4px; color:{t3}; font-size:10px; font-weight:600; }}
QFrame[frameShape="4"], QFrame[frameShape="5"] {{ color:{l1}; background:{l1}; border:0; max-height:1px; }}

/* подписи страниц Echoes — шрифт и цвета Phantom */
QLabel {{ background:transparent; }}
QLabel#YaH1 {{ color:{t1}; font-size:28px; font-weight:700; }}
QLabel#YaH2 {{ color:{t1}; font-size:20px; font-weight:600; }}
QLabel#YaHero {{ color:{t1}; font-weight:700; }}
QLabel#YaSub, QLabel#Sub {{ color:{t2}; font-size:12px; }}
QLabel#Section, QLabel#YaSideHead {{ color:{t3}; font-size:10px; font-weight:600; letter-spacing:2px; }}
QLabel#Big {{ color:{t1}; font-size:15px; font-weight:600; }}
QLabel#YaBadge {{ color:#050505; background:#ffffff; border-radius:9px; font-size:10px; font-weight:700; }}

/* панели и карточки Echoes — стекло вместо сплошного тёмного */
QFrame#YaContent, QFrame#YaPlayer, QFrame#YaTopBar, QFrame#YaSideNav, QFrame#YaCornerBox {{
    background:rgba(255,255,255,0.03); border:1px solid {l1}; }}
QFrame#NetCard, QFrame#YaWaveCard, QFrame#YaSkinCard, QFrame#YaCard, QFrame#Card {{
    background:rgba(255,255,255,0.045); border:1px solid {l1}; border-radius:20px; }}
"""


# ══════════════════════════════════════════════════════════════════════════ #
#  Стекло: заливка, блик, рамка, тень (тень — девятью кусками из кэша)
# ══════════════════════════════════════════════════════════════════════════ #

# вид поверхности → (радиус по умолчанию, тень, сила заливки)
# тени — как в CSS Phantom: (смещение y, размытие, расширение, прозрачность)
SHADOWS = {
    "panel": [(30, 90, -28, .92), (12, 36, -16, .65)],
    "card": [(18, 48, -20, .82)],
    "float": [(16, 44, -12, .72)],
    "soft": [(18, 48, -20, .82)],
}
KINDS = {
    "panel": (R_XL, "panel"),     # большие карточки и выезжающие панели (.pa-surface-panel / .glass)
    "card": (R_LG, "card"),       # карточки-виджеты (.glass-soft)
    "soft": (R_MD, "card"),
    "island": (18, "float"),      # «островок» мини-плеера вверху
    "menu": (R_MD, "float"),
    "row": (R_MD, None),          # строки списков (без тени)
}
_SHADOW_CACHE: dict = {}


def _reach(shadow: str) -> int:
    """Насколько тень выходит за край (3σ размытия − расширение + смещение)."""
    return max(int(b * 1.5 - s + abs(y)) for y, b, s, _a in SHADOWS[shadow]) + 2


def _shadow_image(shadow: str, w: float, h: float, radius: float) -> tuple[QImage, int]:
    """Тень прямоугольника w×h в МАЛЕНЬКОЙ картинке (масштаб — так, чтобы самое узкое размытие было ~3 px):
    тень всё равно очень мягкая, растяжение при рисовании незаметно. Карточка 600×400 — картинка ~150×120,
    считается за доли миллисекунды и хранится в кэше по размеру."""
    key = (shadow, int(w) // 4, int(h) // 4, round(radius, 1))     # окно тянут — не пересчитывать на каждый px
    hit = _SHADOW_CACHE.get(key)
    if hit is not None:
        return hit
    import blur_fx
    layers = SHADOWS[shadow]
    reach = _reach(shadow)
    k = max(1.0, min(b for _y, b, _s, _a in layers) / 2.0 / 3.0)            # CSS blur = 2σ; σ → 3 px
    W, H = w + 2 * reach, h + 2 * reach
    iw, ih = max(4, int(round(W / k))), max(4, int(round(H / k)))
    acc = QImage(iw, ih, QImage.Format.Format_ARGB32_Premultiplied)
    acc.fill(Qt.GlobalColor.transparent)
    for y, b, s, alpha in layers:
        sil = QImage(iw, ih, QImage.Format.Format_ARGB32_Premultiplied)
        sil.fill(Qt.GlobalColor.transparent)
        p = QPainter(sil)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, int(255 * alpha)))
        r = QRectF((reach - s) / k, (reach - s + y) / k, max(1.0, (w + 2 * s) / k), max(1.0, (h + 2 * s) / k))
        rr = max(0.0, radius + s) / k
        p.drawRoundedRect(r, rr, rr)
        p.end()
        sil = blur_fx.blur_image(sil, b / 2.0 / k)
        p = QPainter(acc)
        p.drawImage(0, 0, sil)
        p.end()
    hit = (acc, reach)
    if len(_SHADOW_CACHE) > 64:
        _SHADOW_CACHE.clear()
    _SHADOW_CACHE[key] = hit
    return hit


def shadow_margin(kind: str = "panel") -> int:
    """Насколько тень выходит за край поверхности (чтобы родитель знал, сколько места оставить)."""
    shadow = KINDS[kind][1] if kind in KINDS else kind
    if not shadow or shadow not in SHADOWS:
        return 0
    return _reach(shadow)


def paint_shadow(p: QPainter, rect: QRectF, kind: str = "panel", radius: float | None = None):
    """Нарисовать тень поверхности rect (в координатах p). Зовёт РОДИТЕЛЬ в своём paintEvent перед детьми:
    сам виджет за свои края рисовать не может. Внутри карточки тень не рисуется (как box-shadow в CSS):
    карточка полупрозрачная, иначе она бы темнела."""
    if not _CFG["effects"]:
        return
    rad0, shadow = KINDS.get(kind, (R_LG, kind))
    if not shadow or shadow not in SHADOWS:
        return
    radius = px(rad0) if radius is None else radius
    img, reach = _shadow_image(shadow, rect.width(), rect.height(), radius)
    outer = QRectF(rect.x() - reach, rect.y() - reach, rect.width() + 2 * reach, rect.height() + 2 * reach)
    clip = QPainterPath()
    clip.addRect(outer)
    clip = clip.subtracted(surface_path(QRectF(rect).adjusted(.5, .5, -.5, -.5), radius))
    p.save()
    p.setClipPath(clip, Qt.ClipOperation.IntersectClip)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.drawImage(outer, img)
    p.restore()


def surface_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def paint_surface(p: QPainter, rect: QRectF, kind: str = "panel", radius: float | None = None,
                  hover: bool = False, edge_light: bool = False, strength: float = 1.0):
    """Стеклянная поверхность Phantom: блик 155°, заливка сверху вниз (сильнее → слабее), рамка 1 px,
    внутренний блик по верхней кромке. kind: panel | card | soft | island | menu | row."""
    rad0, _shadow = KINDS.get(kind, (R_LG, None))
    radius = px(rad0) if radius is None else radius
    r = QRectF(rect).adjusted(.5, .5, -.5, -.5)
    path = surface_path(r, radius)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if kind == "island":
        p.fillPath(path, QColor(0, 0, 0, 189))                 # #000000bd
    elif kind == "menu":
        p.fillPath(path, QColor(13, 13, 13, 242))
    elif kind == "row":
        p.fillPath(path, white(.043 if hover else .024))
    else:
        top = surface_alpha(True) * strength
        bot = surface_alpha() * strength
        if kind in ("card", "soft"):                           # .glass-soft: заливка → почти прозрачно
            top, bot = surface_alpha() * strength, .012 * strength
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, white(top + (.012 if hover else 0)))
        g.setColorAt(1, white(bot + (.008 if hover else 0)))
        p.fillPath(path, g)
        # блик 155°: от левого верхнего угла, гаснет к 42 %
        import math
        ang = math.radians(155 - 90)
        d = (r.width() * abs(math.sin(ang)) + r.height() * abs(math.cos(ang))) / 2
        c = r.center()
        dx, dy = math.sin(ang) * d, -math.cos(ang) * d
        hl = QLinearGradient(QPointF(c.x() - dx, c.y() - dy), QPointF(c.x() + dx, c.y() + dy))
        hl.setColorAt(0, white(.02))
        hl.setColorAt(.42, white(0))
        p.fillPath(path, hl)
    # рамка
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(qcolor(LINE_2 if (hover and kind != "island") else LINE_1), 1.0))
    p.drawPath(path)
    # внутренний блик сверху (inset 0 1px 0 rgba(255,255,255,.045))
    if kind not in ("row",):
        p.setClipPath(path)
        p.setPen(QPen(white(.05 if kind == "island" else .045), 1.0))
        p.drawLine(QPointF(r.left() + radius * .6, r.top() + 1), QPointF(r.right() - radius * .6, r.top() + 1))
        p.setClipping(False)
    if edge_light:
        paint_edge_light(p, r)
    p.restore()


def paint_edge_light(p: QPainter, rect: QRectF):
    """.edge-light: волосок света по верхней кромке, 12 %…88 % ширины."""
    x0, x1 = rect.left() + rect.width() * .12, rect.right() - rect.width() * .12
    g = QLinearGradient(QPointF(x0, 0), QPointF(x1, 0))
    g.setColorAt(0, white(0))
    g.setColorAt(.5, white(.14))
    g.setColorAt(1, white(0))
    p.save()
    p.setPen(QPen(g, 1.0))
    p.drawLine(QPointF(x0, rect.top() + .5), QPointF(x1, rect.top() + .5))
    p.restore()


def paint_hairline(p: QPainter, x0: float, x1: float, y: float, color=LINE_1):
    p.save()
    p.setPen(QPen(qcolor(color), 1.0))
    p.drawLine(QPointF(x0, y + .5), QPointF(x1, y + .5))
    p.restore()


def paint_kicker(p: QPainter, x: float, baseline: float, text: str, color=TEXT_TERTIARY) -> float:
    """Кикер капсом с разрядкой; возвращает ширину."""
    from PyQt6.QtGui import QFontMetricsF
    f = kicker_font()
    p.save()
    p.setFont(f)
    p.setPen(qcolor(color))
    t = text.upper()
    p.drawText(QPointF(x, baseline), t)
    p.restore()
    return QFontMetricsF(f).horizontalAdvance(t)


# ══════════════════════════════════════════════════════════════════════════ #
#  Обложки: скругление, заглушка с инициалами (как «DM» у Phantom)
# ══════════════════════════════════════════════════════════════════════════ #

def initials(title: str, artist: str = "") -> str:
    """Две буквы для заглушки: первые буквы двух первых слов названия (или названия и исполнителя)."""
    import re
    words = [w for w in re.split(r"[\s\-_/·.,:;()\[\]]+", title or "") if w]
    if len(words) >= 2:
        s = words[0][0] + words[1][0]
    elif words:
        w = words[0]
        s = w[:2] if len(w) > 1 and not w[1].isspace() else w[0] + ((artist or " ")[0])
    else:
        s = (artist or "?")[:2]
    return s.strip().upper() or "?"


def placeholder_cover(size: QSize | int, title: str = "", artist: str = "", radius: float = 10,
                      dpr: float = 2.0) -> QPixmap:
    """Тёмная карточка с инициалами и концентрическими кругами — заглушка Phantom для трека без обложки."""
    if isinstance(size, int):
        size = QSize(size, size)
    w, h = size.width(), size.height()
    pm = QPixmap(int(w * dpr), int(h * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = QRectF(0, 0, w, h)
    path = surface_path(r.adjusted(.5, .5, -.5, -.5), radius)
    g = QLinearGradient(r.topLeft(), r.bottomRight())
    g.setColorAt(0, QColor(22, 22, 22))
    g.setColorAt(1, QColor(8, 8, 8))
    p.fillPath(path, g)
    p.setClipPath(path)
    p.setPen(QPen(white(.07), 1.0))
    m = min(w, h)
    for i, k in enumerate((.18, .3, .44, .6)):
        off = (i % 2) * m * .06
        p.drawEllipse(QPointF(w * .44 + off, h * .42 + off * .6), m * k, m * k)
    p.setClipping(False)
    p.setPen(QPen(qcolor(LINE_1), 1.0))
    p.drawPath(path)
    f = font(max(9, m * .2), 650, -.02, scaled=False)
    p.setFont(f)
    p.setPen(white(.86))
    p.drawText(r, Qt.AlignmentFlag.AlignCenter, initials(title, artist))
    p.end()
    return pm


def rounded_pixmap(src: QPixmap | QImage, size: QSize, radius: float, dpr: float = 2.0) -> QPixmap:
    """Картинка «с обрезкой» под size и скруглением (для обложек в строках и карточках)."""
    img = src.toImage() if isinstance(src, QPixmap) else src
    w, h = size.width(), size.height()
    out = QPixmap(int(w * dpr), int(h * dpr))
    out.setDevicePixelRatio(dpr)
    out.fill(Qt.GlobalColor.transparent)
    if img.isNull():
        return out
    k = max(w * dpr / img.width(), h * dpr / img.height())
    sw, sh = w * dpr / k, h * dpr / k
    crop = QRectF((img.width() - sw) / 2, (img.height() - sh) / 2, sw, sh)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.setClipPath(surface_path(QRectF(0, 0, w, h), radius))
    p.drawImage(QRectF(0, 0, w, h), img, crop)
    p.end()
    return out


def clear_caches():
    """Отпустить кэши (иконки, тени) — при смене масштаба интерфейса или нехватке памяти."""
    _ICON_CACHE.clear()
    _SHADOW_CACHE.clear()
