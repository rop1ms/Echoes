"""Знак ECHOES — «нота-клинок»: высокий штиль-клинок, плавник-флажок с острым концом и вогнутой кромкой,
головка-серп с крючком и косая черта, отрезанная от остального тонким зазором. Белым на чёрном.

Один источник формы для всего: иконки (tools/make_icons.py → app/icon.png, app/icon.ico), логотипа в
интерфейсе (yamusic_theme.Logo) и ресурсов в app/assets/logo/. Лаунчер использует тот же
прозрачный PNG как маску для металлической текстуры.

Координаты — в системе исходного наброска (примерно 0..1000 × 0..800); mark_path(rect) вписывает знак в rect.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPainterPathStroker, QPolygonF

STEM = ((528, 36), (546, 122), (586, 370), (521, 632), (505, 370), (514, 122))
SLASH = ((512, 406), (408.6, 569), (294, 726), (399.4, 562))
GAP = 12.0                                                     # зазор вокруг косой черты

BG = QColor(11, 11, 11)
FG = QColor(242, 242, 242)


def _poly(pts) -> QPainterPath:
    p = QPainterPath()
    p.addPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
    p.closeSubpath()
    return p


def _flag() -> QPainterPath:
    p = QPainterPath(QPointF(533, 66))                         # начало — внутри штиля, без щели
    p.lineTo(716, 488)
    p.quadTo(642, 402, 598, 364)                               # вогнутая нижняя кромка
    p.lineTo(574, 400)
    p.closeSubpath()
    return p


def _head() -> QPainterPath:
    p = QPainterPath(QPointF(166, 640))
    p.quadTo(204, 608, 394, 604)                               # верх — к острому носу справа
    p.quadTo(328, 630, 262, 634)
    p.quadTo(252, 648, 304, 664)                               # крючок
    p.quadTo(226, 680, 166, 640)
    p.closeSubpath()
    return p


_RAW: QPainterPath | None = None


def raw_path() -> QPainterPath:
    """Знак в координатах наброска (кэш)."""
    global _RAW
    if _RAW is None:
        body = _poly(STEM).united(_flag()).united(_head())
        slash = _poly(SLASH)
        st = QPainterPathStroker()
        st.setWidth(GAP)
        st.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        st.setMiterLimit(10)
        halo = st.createStroke(slash).united(slash)
        _RAW = body.subtracted(halo).united(slash).simplified()
    return QPainterPath(_RAW)


def mark_path(rect: QRectF, fill: float = 1.0) -> QPainterPath:
    """Знак, вписанный в rect по центру (fill — доля высоты/ширины rect, которую он занимает)."""
    src = raw_path()
    b = src.boundingRect()
    k = min(rect.width() / b.width(), rect.height() / b.height()) * fill
    out = QPainterPath()
    from PyQt6.QtGui import QTransform
    t = QTransform()
    t.translate(rect.center().x(), rect.center().y())
    t.scale(k, k)
    t.translate(-b.center().x(), -b.center().y())
    out.addPath(t.map(src))
    return out


def paint_mark(p: QPainter, rect: QRectF, color: QColor = FG, fill: float = 1.0):
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawPath(mark_path(rect, fill))
    p.restore()


def icon_image(size: int) -> QImage:
    """Иконка size×size: чёрный скруглённый квадрат, белый знак. Мелким размерам — меньше полей."""
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = size * (0.14 if size <= 32 else 0.18)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(BG)
    p.drawRoundedRect(QRectF(0, 0, size, size), r, r)
    fill = 0.92 if size <= 32 else 0.82
    paint_mark(p, QRectF(0, 0, size, size), FG, fill)
    p.end()
    return img


def svg(icon: bool = True) -> str:
    """SVG знака: icon=True — с чёрным квадратом (иконка), False — только белый знак на прозрачном."""
    def d_of(path: QPainterPath) -> str:
        out = []
        for i in range(path.elementCount()):
            e = path.elementAt(i)
            cmd = "M" if e.isMoveTo() else "L" if e.isLineTo() else "C" if e.isCurveTo() else ""
            out.append(f"{cmd}{e.x:.1f} {e.y:.1f}" if cmd else f" {e.x:.1f} {e.y:.1f}")
        return " ".join(out) + " Z"
    path = mark_path(QRectF(0, 0, 1000, 1000), 0.82 if icon else 1.0)
    body = f'<path fill="#f2f2f2" fill-rule="nonzero" d="{d_of(path)}"/>'
    bg = '<rect width="1000" height="1000" rx="180" fill="#0b0b0b"/>' if icon else ""
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">{bg}{body}</svg>\n'
