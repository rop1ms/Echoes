"""Full-page frosted album art for lyrics: one glass surface, never per line."""
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPixmap, QLinearGradient, QPen, QBrush
from PyQt6.QtWidgets import QFrame


def _dominant_colors(img, n=5):
    """Главные цвета обложки (по уменьшенной копии): яркие и насыщенные — первыми."""
    from PyQt6.QtGui import QImage
    small = img.scaled(24, 24, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    small = small.convertToFormat(QImage.Format.Format_RGB32)
    buckets = {}
    for y in range(small.height()):
        for x in range(small.width()):
            c = small.pixelColor(x, y)
            key = (c.red() // 40, c.green() // 40, c.blue() // 40)
            b = buckets.setdefault(key, [0, 0, 0, 0])
            b[0] += c.red(); b[1] += c.green(); b[2] += c.blue(); b[3] += 1
    cols = []
    for r, g, bl, k in buckets.values():
        c = QColor(r // k, g // k, bl // k)
        score = k * (0.35 + c.hsvSaturationF()) * (0.4 + c.valueF())
        cols.append((score, c))
    cols.sort(key=lambda x: -x[0])
    return [c for _s, c in cols[:n]] or [QColor("#3a4a6a")]


def lyrics_background_ios(size, src):
    """Фон текста как в Apple Music на iPhone: цвета обложки большими мягкими пятнами + сильно
    размытая насыщенная обложка + лёгкое затемнение для читаемости и стеклянный блик сверху."""
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QImage, QRadialGradient
    w, h = max(1, size.width()), max(1, size.height())
    cols = _dominant_colors(src)
    lw, lh = 96, max(24, int(96 * h / max(1, w)))
    base = QImage(lw, lh, QImage.Format.Format_ARGB32_Premultiplied)
    dark = QColor(cols[-1]).darker(260)
    base.fill(dark)
    p = QPainter(base)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    import random
    rnd = random.Random(sum(c.rgb() for c in cols) & 0xFFFFFF)
    for i in range(7):                                         # «капли» цвета, как в живом фоне iOS
        c = QColor(cols[i % len(cols)])
        hh, ss, vv, _a = c.getHsvF()
        c = QColor.fromHsvF(hh if hh >= 0 else 0, min(1.0, ss * 1.35 + 0.08), min(0.78, vv * 1.05 + 0.04))   # светлые обложки не выбеливают фон
        cx, cy = rnd.uniform(-0.1, 1.1) * lw, rnd.uniform(-0.1, 1.1) * lh
        r = rnd.uniform(0.45, 0.85) * max(lw, lh)
        g = QRadialGradient(QPointF(cx, cy), r)
        c0 = QColor(c); c0.setAlpha(235 if i < 3 else 170)
        c1 = QColor(c); c1.setAlpha(0)
        g.setColorAt(0, c0)
        g.setColorAt(1, c1)
        p.fillRect(base.rect(), g)
    p.end()
    pm = QPixmap(w, h)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.drawImage(QRectF(0, 0, w, h), base.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation))
    try:                                                       # сама обложка — очень размыто и сочно
        import blur_fx
        cov = blur_fx.blurred_cover(src, w, h, max(w, h) / 16.0, sat=1.45)
        p.setOpacity(0.5)
        p.drawImage(0, 0, cov)
        p.setOpacity(1.0)
    except Exception as e:                                     # noqa: BLE001
        print("[lyrics bg]", e)
    # затемнение по яркости картинки: тёмная обложка почти не трогается, светлая приглушается сильно
    p.end()
    sm = pm.toImage().scaled(16, 16, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    lum = sum(sm.pixelColor(x, y).lightnessF() for y in range(16) for x in range(16)) / 256.0
    p = QPainter(pm)
    p.fillRect(pm.rect(), QColor(0, 0, 0, int(min(130, 35 + max(0.0, lum - 0.3) * 230))))
    vig = QRadialGradient(QPointF(w * 0.5, h * 0.45), max(w, h) * 0.75)
    vig.setColorAt(0.55, QColor(0, 0, 0, 0))
    vig.setColorAt(1.0, QColor(0, 0, 0, 90))
    p.fillRect(pm.rect(), vig)
    top = QLinearGradient(0, 0, 0, h * 0.22)                   # стеклянный блик по верхнему краю
    top.setColorAt(0, QColor(255, 255, 255, 30))
    top.setColorAt(1, QColor(255, 255, 255, 0))
    p.fillRect(QRectF(0, 0, w, h * 0.22), top)
    p.end()
    return pm


def lyrics_background(size, cover=None, accent=None, glass=True, src=None):
    if src is not None and not src.isNull() and glass:
        try:
            return lyrics_background_ios(size, src)
        except Exception as e:                                 # noqa: BLE001
            print("[lyrics bg ios]", e)
    w, h = max(1, size.width()), max(1, size.height())
    pm = QPixmap(w, h)
    pm.fill(QColor('#111319'))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if cover is not None and not cover.isNull():
        p.drawImage(QRectF(0, 0, w, h), cover)
    else:
        bg = QLinearGradient(0, 0, w, h)
        bg.setColorAt(0, QColor('#263044'))
        bg.setColorAt(1, QColor('#101116'))
        p.fillRect(pm.rect(), bg)

    # Frost and dim the cover once, then draw one continuous refraction layer.
    p.fillRect(pm.rect(), QColor(12, 15, 23, 100))
    if glass:
        tint = QColor(accent or '#c9d8ff')
        sheen = QLinearGradient(0, 0, w * .8, h)
        sheen.setColorAt(0, QColor(225, 239, 255, 24))
        c = QColor(tint); c.setAlpha(20)
        sheen.setColorAt(.48, c)
        sheen.setColorAt(1, QColor(8, 13, 25, 48))
        p.fillRect(pm.rect(), sheen)
        p.save(); p.setClipRect(pm.rect())
        for i in range(3):
            y = h * (.18 + i * .30)
            path = QPainterPath(); path.moveTo(-w * .1, y + h * .12)
            path.cubicTo(w * .2, y - h * .26, w * .65, y + h * .34, w * 1.08, y - h * .14)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(230, 241, 255, 22 - i * 5), max(1.0, h * .002)))
            p.drawPath(path)
            shadow = QPainterPath(); shadow.moveTo(-w * .1, y + h * .14 + 3)
            shadow.cubicTo(w * .2, y - h * .24 + 3, w * .65, y + h * .36 + 3, w * 1.08, y - h * .12 + 3)
            p.setPen(QPen(QColor(6, 9, 17, 28 - i * 6), max(1.0, h * .004)))
            p.drawPath(shadow)
        p.restore()
        edge = QLinearGradient(0, 0, 0, h)
        edge.setColorAt(0, QColor(255, 255, 255, 34))
        edge.setColorAt(.012, QColor(255, 255, 255, 8))
        edge.setColorAt(.5, QColor(255, 255, 255, 0))
        edge.setColorAt(.985, QColor(255, 255, 255, 3))
        edge.setColorAt(1, QColor(255, 255, 255, 23))
        p.fillRect(pm.rect(), edge)
    p.end()
    return pm


_SURF_CACHE: dict = {}                                         # (w, h, radius) → готовое стекло


def liquid_surface(size, radius=22):
    """Стекло нужного размера — из кэша (развернуть/свернуть окно второй раз — мгновенно)."""
    key = (max(1, size.width()), max(1, size.height()), radius)
    pm = _SURF_CACHE.get(key)
    if pm is None:
        pm = _liquid_surface(size, radius)
        if len(_SURF_CACHE) > 48:
            _SURF_CACHE.pop(next(iter(_SURF_CACHE)))
        _SURF_CACHE[key] = pm
    # копия (в Qt — общие данные до первой записи): кто рисует поверх стекла (карточки дуэли, шапки), рисует
    # в свою копию. Раньше рисовали прямо в кэш — следующая карточка того же размера получала чужой текст и
    # обложку («LISA» поверх «MINE»), а страницы — отголоски прошлых
    return QPixmap(pm)


_PENDING: dict = {}                                            # (w, h, radius) → виджеты, ждущие стекло


def surface_ready(size, radius, widget) -> bool:
    """Чёткое стекло этого размера уже готово (или считать придётся здесь же — без C++)? Иначе оно
    заказано в фоновом потоке echoes_ui.dll, а widget перерисуется, когда будет готово; до тех пор
    вызывающий рисует растянутое прежнее."""
    import native_ui
    key = (max(1, size.width()), max(1, size.height()), radius)
    if key in _SURF_CACHE or not native_ui.available():
        return True
    import weakref
    waiting = _PENDING.get(key)
    if waiting is None:
        waiting = _PENDING[key] = weakref.WeakSet()

        def done(pm, key=key):
            if len(_SURF_CACHE) > 48:
                _SURF_CACHE.pop(next(iter(_SURF_CACHE)))
            _SURF_CACHE[key] = pm
            for w in list(_PENDING.pop(key, ())):
                try:
                    w.update()
                except RuntimeError:
                    pass
        native_ui.liquid_surface_later(key[0], key[1], radius, done)
    waiting.add(widget)
    return False


def surface_for(widget, cur, radius=22):
    """Для paintEvent: пока окно меняет размер — растянуть прежнее стекло (быстро), а чёткое
    нарисовать через ~150 мс после остановки (или сразу, если такое уже было в кэше)."""
    from PyQt6.QtCore import QTimer
    size = widget.size()
    key = (max(1, size.width()), max(1, size.height()), radius)
    if cur is not None and cur.size() == size:
        return cur
    hit = _SURF_CACHE.get(key)
    if hit is not None or cur is None:
        return liquid_surface(size, radius)
    t = getattr(widget, "_glass_timer", None)
    if t is None:
        t = widget._glass_timer = QTimer(widget)
        t.setSingleShot(True)
        t.setInterval(150)
        t.timeout.connect(widget.update)
    t.start()
    widget._glass_stretch = True
    return cur.scaled(size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)


def _liquid_surface(size, radius=22):
    """Black optical glass: layered reflections, etched grain and refracted rims."""
    import native_ui
    if native_ui.available():                                  # то же стекло на C++ (echoes_ui.dll)
        return native_ui.liquid_surface(size.width(), size.height(), radius)
    import random
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QRadialGradient
    w, h = max(1, size.width()), max(1, size.height())
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect = QRectF(.5, .5, w - 1, h - 1)
    shape = QPainterPath()
    shape.addRoundedRect(rect, radius, radius)
    p.setClipPath(shape)
    base = QLinearGradient(0, 0, w * .7, h)
    base.setColorAt(0, QColor('#0b0c0e'))
    base.setColorAt(.45, QColor('#040506'))
    base.setColorAt(1, QColor('#08090b'))
    p.fillPath(shape, base)
    for cx, cy, r, alpha in ((.08, -.38, .65, 20), (1.15, .9, .48, 11)):
        glow = QRadialGradient(QPointF(w * cx, h * cy), max(w, h) * r)
        glow.setColorAt(0, QColor(230, 237, 246, alpha))
        glow.setColorAt(1, QColor(230, 237, 246, 0))
        p.fillPath(shape, glow)
    # Narrow reflected light bands, separated by dark glass rather than a grey wash.
    sheen = QLinearGradient(0, 0, w, h * .65)
    for pos, alpha in ((0, 0), (.055, 1), (.095, 14), (.115, 3),
                       (.16, 0), (.76, 0), (.82, 5), (.85, 0), (1, 0)):
        sheen.setColorAt(pos, QColor(238, 244, 255, alpha))
    p.fillPath(shape, sheen)
    # Sparse deterministic microtexture; cached with the surface, never animated.
    rng = random.Random(73)
    p.setPen(QPen(QColor(231, 238, 250, 6), .65))
    for _ in range(min(16000, w * h // 65)):
        p.drawPoint(QPointF(rng.random() * w, rng.random() * h))
    # Refraction stays close to the top and bottom edges, away from reading areas.
    for bottom in (False, True):
        y = h - 9 if bottom else 9
        direction = -1 if bottom else 1
        curve = QPainterPath(QPointF(-w * .03, y + direction * 12))
        curve.cubicTo(w * .18, y - direction * 15,
                      w * .5, y + direction * 14, w * 1.04, y)
        light = QLinearGradient(0, 0, w, 0)
        for pos, alpha in ((0, 0), (.12, 26), (.3, 5), (.66, 2), (.93, 20), (1, 0)):
            light.setColorAt(pos, QColor(229, 240, 255, alpha))
        p.setPen(QPen(QBrush(light), 1.1))
        p.drawPath(curve)
    rim = QLinearGradient(0, 0, w * .35, h)
    for pos, alpha in ((0, 95), (.10, 24), (.3, 9), (.7, 6), (.94, 18), (1, 48)):
        rim.setColorAt(pos, QColor(236, 243, 255, alpha))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QBrush(rim), 1))
    p.drawPath(shape)
    inner = QPainterPath()
    inner.addRoundedRect(rect.adjusted(2, 2, -2, -2), max(0, radius - 2), max(0, radius - 2))
    p.setPen(QPen(QColor(0, 0, 0, 190), 1))
    p.drawPath(inner)
    p.end()
    return pm


def glass_controls_qss():
    """Shared controls for every Echoes Music page, including nested network views."""
    # Reflective bands and asymmetric rim keep small controls legible at any DPI.
    face = "qlineargradient(x1:0,y1:0,x2:0.75,y2:1,stop:0 #25282d,stop:0.07 #15171b,stop:0.18 #0c0e11,stop:0.48 #070809,stop:0.80 #0b0d10,stop:0.94 #11151a,stop:1 #1b2027)"
    hover = "qlineargradient(x1:0,y1:0,x2:0.75,y2:1,stop:0 #353b43,stop:0.1 #1c2026,stop:0.35 #101318,stop:0.8 #151a21,stop:1 #272f3a)"
    try:                                                       # акцент темы (ya_skin) — не всегда жёлтый
        import yamusic_theme as _Y
        acc = QColor(_Y.YELLOW)
    except Exception:                                          # noqa: BLE001
        acc = QColor("#ffdb1a")
    try:
        import ya_skin as _S
        on_acc = _S.CURRENT.get("on_accent") or "#080808"
    except Exception:                                          # noqa: BLE001
        on_acc = "#080808"

    def rgba(a):
        return f"rgba({acc.red()},{acc.green()},{acc.blue()},{a})"
    lt, lt2, dk = acc.lighter(120).name(), acc.lighter(150).name(), acc.darker(125).name()
    gold = (f"qlineargradient(x1:0,y1:0,x2:0.8,y2:1,stop:0 {acc.lighter(150).name()},stop:0.12 {acc.lighter(125).name()},"
            f"stop:0.45 {acc.name()},stop:0.85 {acc.darker(120).name()},stop:1 {acc.lighter(110).name()})")
    common = "QPushButton, QToolButton, QPushButton#YaChip, QPushButton#YaSeg, QPushButton#YaIcon, QPushButton#GhostBtn, QPushButton#NetVote"
    hover_selectors = ", ".join(x.strip()+":hover" for x in common.split(","))
    pressed = ", ".join(x.strip()+":pressed" for x in common.split(","))
    checked = ", ".join(x.strip()+":checked" for x in common.split(","))
    return f"""
    {common} {{ background:{face}; border:1px solid rgba(216,231,250,30);
        border-top-color:rgba(235,244,255,65); border-bottom-color:rgba(160,180,210,24); }}
    {hover_selectors} {{ background:{hover}; border-color:rgba(223,237,255,75); border-top-color:rgba(245,250,255,115); }}
    {pressed} {{ background:#050608; border-color:rgba(230,240,255,30); border-bottom-color:rgba(230,240,255,65); }}
    {checked} {{ background:{face}; color:{lt}; border-color:{rgba(140)}; border-top-color:{lt2}; }}
    QPushButton#YaChip:checked, QPushButton#YaSeg:checked,
    QPushButton#AccentBtn, QPushButton#YaYellow {{ background:{gold}; color:{on_acc}; border:1px solid {lt}; border-top-color:{lt2}; }}
    QPushButton#YaChip:checked:hover, QPushButton#YaSeg:checked:hover,
    QPushButton#AccentBtn:hover, QPushButton#YaYellow:hover {{ background:{gold}; border-color:{lt2}; }}
    QPushButton#AccentBtn:pressed, QPushButton#YaYellow:pressed {{ background:{dk}; border-color:{dk}; }}
    QPushButton:disabled, QPushButton#YaChip:disabled, QPushButton#YaIcon:disabled,
    QToolButton:disabled {{ background:#0b0c0e; color:#65686d; border-color:rgba(220,230,245,14); }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background:{face}; border:1px solid rgba(216,231,250,35);
        border-top-color:rgba(235,244,255,60); border-bottom-color:rgba(160,180,210,22); }}
    QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border-color:rgba(225,238,255,85); }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color:{rgba(180)}; border-top-color:{lt2}; }}
    QFrame#YaSegTrack {{ background:#060709; border:1px solid rgba(220,235,255,25); border-top-color:rgba(235,245,255,45); }}
    QPushButton#YaNav {{ background:transparent; border:1px solid transparent; }}
    QPushButton#YaNav:hover {{ background:{face}; border-color:rgba(216,231,250,35); }}
    QPushButton#YaNav:checked {{ background:{face}; color:{lt}; border-color:{rgba(65)}; }}
    """ + _skin_tail()


def _skin_tail() -> str:
    """Своя настройка темы Echoes Music (ya_skin): цвета акцента, стиль и скругление кнопок — поверх стекла."""
    try:
        import ya_skin
        return "\n" + ya_skin.overrides_qss()
    except Exception:                                          # noqa: BLE001
        return ""



def _phantom_on() -> bool:
    try:
        import ya_skin
        return bool(ya_skin.PHANTOM_ON)
    except Exception:                                          # noqa: BLE001
        return False


class GlassFrame(QFrame):
    """Рамка из «жидкого стекла» (как главный экран и плеер) — для всплывающих окошек и диалогов.
    Поверхность рисуется один раз на размер и кэшируется (без затрат в каждом кадре)."""

    def __init__(self, parent=None, radius=18):
        super().__init__(parent)
        self._radius = radius
        self._surface = None

    def paintEvent(self, e):
        from ya_skin import interface_radius
        radius = interface_radius(self._radius)
        if _phantom_on():                                      # вид Phantom — стекло Phantom
            import ph_style
            w = self.window()
            popup = w is self or w.windowType() in (Qt.WindowType.Popup, Qt.WindowType.ToolTip) or                 w.parentWidget() is not None                   # (Popup включает бит Window — сравнивать тип целиком)
            p = QPainter(self)                                 # всплывашка — плотное стекло меню, карточка
            ph_style.paint_surface(p, QRectF(self.rect()), "menu" if popup else "soft", min(radius, 20))
            p.end()                                            # в настройках — как остальные карточки
            return
        if getattr(self, "_surface_radius", None) != radius:
            self._surface_radius, self._surface = radius, None
        if self._surface is None or self._surface.size() != self.size() or getattr(self, "_glass_stretch", False):
            stretched = self._surface is not None and self._surface.size() != self.size()
            if getattr(self, "_glass_stretch", False) and not (getattr(self, "_glass_timer", None) and
                                                                self._glass_timer.isActive()):
                self._glass_stretch = False
                self._surface = liquid_surface(self.size(), radius)
            elif stretched or self._surface is None:
                self._surface = surface_for(self, self._surface, radius)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.drawPixmap(0, 0, self._surface)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawPath(path)
        p.end()
