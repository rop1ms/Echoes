"""Beat-reactive artwork drawn directly into the Scene canvas."""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainterPath, QPen, QPolygonF

from scene_director import MOTIFS


def tint(color, alpha):
    color = QColor(color)
    color.setAlpha(alpha)
    return color


def _star(p, x, y, r):
    shape = QPainterPath(QPointF(x, y - r))
    shape.quadTo(x, y, x + r * .73, y)
    shape.quadTo(x, y, x, y + r)
    shape.quadTo(x, y, x - r * .73, y)
    shape.quadTo(x, y, x, y - r)
    p.drawPath(shape)


def halo(p, box, name, accent, t, drive, opacity):
    """Arcs stay behind the media. Bright points move along the track's current phrase."""
    if opacity <= .01:
        return
    color = QColor(MOTIFS[name].color) if name in MOTIFS else accent
    side = box.width()
    p.save()
    p.translate(box.center())
    p.scale(side, side)
    p.setOpacity(opacity)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for i in range(3):
        d = 1.11 + i * .13 + drive * .045
        r = QRectF(-d / 2, -d / 2, d, d)
        p.setPen(QPen(tint(color, round(92 - 22 * i + 27 * drive)), .004 if i == 0 else .002))
        p.drawArc(r, int((t * (23 - 4 * i) + i * 43) % 360 * 16), (198 - 20 * i) * 16)
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(7):
        a = t * (.18 if i % 2 else -.26) + i * math.tau / 7
        r = .57 + (i % 3) * .070
        p.setBrush(tint(color if i % 2 else QColor("white"), 175 + 55 * int(drive > .45)))
        _star(p, math.cos(a) * r, math.sin(a) * r, .018 + .013 * (i % 3 == 0) + drive * .009)
    p.restore()


def sticker(p, center, side, name, t, drive, opacity):
    motif = MOTIFS.get(name)
    if motif is None or opacity <= .01:
        return
    color = QColor(motif.color)
    a = math.sin(t * 2.3)
    side *= 1. + .08 * drive
    p.save()
    p.setOpacity(opacity)
    p.translate(center + QPointF(0, side * .045 * a))
    p.rotate(-9 + a * 7)
    p.scale(side, side)
    pane = QRectF(-.48, -.48, .96, .96)
    glass = QLinearGradient(pane.topLeft(), pane.bottomRight())
    glass.setColorAt(0, tint(QColor("white"), 245))
    glass.setColorAt(.62, tint(color.lighter(151), 245))
    glass.setColorAt(1, tint(color, 240))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(tint(color.darker(194), 57))
    p.drawRoundedRect(pane.translated(.035, .064), .22, .22)
    p.setPen(QPen(tint(QColor("white"), 220), .014))
    p.setBrush(glass)
    p.drawRoundedRect(pane, .22, .22)
    p.setPen(QPen(color.darker(152), .039, Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if motif.animation == "crystal":
        p.rotate(t * 35 % 360)
        for _ in range(6):
            p.rotate(60)
            p.drawLine(QPointF(0, 0), QPointF(0, -.32))
            p.drawPolyline(QPolygonF([QPointF(-.085, -.24), QPointF(0, -.15), QPointF(.085, -.24)]))
    elif motif.animation == "links":
        p.rotate(-35 + 12 * a)
        for x in (-.12, .12):
            p.drawRoundedRect(QRectF(x - .18, -.105, .36, .21), .095, .095)
    elif motif.animation in ("ripples", "orbit", "coin"):
        for i in range(3):
            d = .13 + i * .16
            width = d * (1.0 if motif.animation != "coin" else .24 + .76 * abs(math.cos(t * 2)))
            if motif.animation == "ripples":
                p.drawEllipse(QRectF(-width / 2, .02 - d / 4, width, d / 2))
            else:
                p.drawEllipse(QRectF(-width / 2, -d / 2, width, d))
    elif motif.animation == "wings":
        f = .08 * math.sin(t * 6.0)
        path = QPainterPath(QPointF(-.32, -.12 + f))
        path.cubicTo(-.14, -.24, -.10, -.06, 0, .13)
        path.cubicTo(.10, -.06, .14, -.24, .32, -.12 + f)
        p.drawPath(path)
    elif motif.animation == "heart":
        path = QPainterPath(QPointF(0, .26))
        path.cubicTo(-.52, -.055, -.22, -.42, 0, -.16)
        path.cubicTo(.22, -.42, .52, -.055, 0, .26)
        p.setBrush(tint(color, 94))
        p.drawPath(path)
    else:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color.darker(142))
        _star(p, -.035, .03, .27 + .025 * a)
        _star(p, .213, -.22, .10)
    p.restore()
