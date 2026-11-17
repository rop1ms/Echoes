"""Косметика Echoes.NET в стиле Phantom: рамки аватарок с собственной анимацией у каждой.

Вместо прежней неоновой пестроты — стекло, серебро и мягкий свет: тонкое кольцо, стеклянная полоса, свой узор
и своё движение (бег блика, орбиты, мерцание звёзд, рябь, такт музыки…). Все рамки рисуются кодом — ничего не
скачивается, у всех выглядят одинаково.

Каталог (FRAMES): id рамки → (название, раздел, как получить). Разделы:
  free    — бесплатные, для всех;
  ach     — за ачивки (как и раньше), теперь в новом виде;
  role    — у админа и модераторов;
  season  — сезонные;
  sponsor — для спонсоров ECHOES (net_sponsor).
draw(p, kind, S, t) — рамка размером S×S в момент t (секунды); kind — id без префикса «ach:» (как в net_frames).
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QConicalGradient, QPainter, QPainterPath, QPen, QRadialGradient

# ── каталог ── #
FREE = {"glass": "Стекло", "halo": "Ореол", "orbit": "Орбита", "eq": "Эквалайзер", "wave": "Волна",
        "ripple": "Рябь", "dots": "Пунктир", "aurora": "Сияние", "vinylmini": "Пластинка", "comet": "Комета"}
SPONSOR = {"prism": "Призма", "crown": "Корона спонсора", "nebula": "Туманность", "constellation": "Созвездие",
           "gold": "Золото", "flare": "Вспышка", "heartbeat": "Сердце ECHOES", "echo": "Эхо"}
FREE_ORDER = list(FREE)
SPONSOR_ORDER = list(SPONSOR)
SPONSOR_FLAG = "__sponsor__"                                  # «ачивка»-метка спонсора в списке ачивок (net_frames)


def has(kind: str) -> bool:
    return kind in _DRAW


def anim_speed() -> float:
    try:
        import ph_style as ph
        return 0.0 if ph.duration(100) <= 0 else 1.0                 # «уменьшенное движение» — без анимации
    except Exception:                                          # noqa: BLE001
        return 1.0


def _lvl() -> float:
    try:
        import net_frames
        return net_frames.music_level()
    except Exception:                                          # noqa: BLE001
        return 0.0


# ── примитивы ── #

def _w(a: float) -> QColor:
    c = QColor(255, 255, 255)
    c.setAlphaF(max(0.0, min(1.0, a)))
    return c


def _tint(a: float, warm: float = 0.0, cool: float = 0.0) -> QColor:
    r, g, b = 255, 255, 255
    if warm:
        r, g, b = 255, int(255 - 40 * warm), int(255 - 110 * warm)
    if cool:
        r, g, b = int(255 - 90 * cool), int(255 - 40 * cool), 255
    c = QColor(r, g, b)
    c.setAlphaF(max(0.0, min(1.0, a)))
    return c


def _base(p: QPainter, S: float, band=.075, glass=.07, edge=.9, inner=.28):
    """Основа: стеклянная полоса между тонким ярким краем и волосяной линией внутри."""
    c = QPointF(S / 2, S / 2)
    R = S / 2 - S * .02
    w = S * band
    path = QPainterPath()
    path.addEllipse(c, R, R)
    hole = QPainterPath()
    hole.addEllipse(c, R - w, R - w)
    p.fillPath(path.subtracted(hole), _w(glass))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(_w(edge), max(1.0, S * .012)))
    p.drawEllipse(c, R, R)
    p.setPen(QPen(_w(inner), max(.8, S * .006)))
    p.drawEllipse(c, R - w, R - w)
    return c, R, w


def _arc(p, c, r, start_deg, span_deg, col, width):
    p.setPen(QPen(col, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), int(start_deg * 16), int(span_deg * 16))


def _sweep(p, c, R, w, ang, strength=.85, span=.16):
    """Блик бежит по полосе: конический градиент, прозрачный везде, кроме узкого сектора."""
    g = QConicalGradient(c, -ang)
    g.setColorAt(0, _w(strength))
    g.setColorAt(span * .5, _w(strength * .35))
    g.setColorAt(span, _w(0))
    g.setColorAt(1 - span * .3, _w(0))
    g.setColorAt(1, _w(strength))
    path = QPainterPath()
    path.addEllipse(c, R, R)
    hole = QPainterPath()
    hole.addEllipse(c, R - w, R - w)
    p.fillPath(path.subtracted(hole), g)


def _dot(p, x, y, r, a, glow=True):
    if glow:
        g = QRadialGradient(QPointF(x, y), r * 3)
        g.setColorAt(0, _w(a * .55))
        g.setColorAt(1, _w(0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(x, y), r * 3, r * 3)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_w(a))
    p.drawEllipse(QPointF(x, y), r, r)


def _star(p, x, y, r, a):
    path = QPainterPath()
    for i in range(8):
        rr = r if i % 2 == 0 else r * .32
        ang = i * math.pi / 4 - math.pi / 2
        pt = QPointF(x + math.cos(ang) * rr, y + math.sin(ang) * rr)
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    path.closeSubpath()
    p.setPen(Qt.PenStyle.NoPen)
    p.fillPath(path, _w(a))


def _heart(p, x, y, s, a):
    path = QPainterPath()
    path.moveTo(x, y + s * .35)
    path.cubicTo(x - s * .9, y - s * .25, x - s * .45, y - s * .95, x, y - s * .45)
    path.cubicTo(x + s * .45, y - s * .95, x + s * .9, y - s * .25, x, y + s * .35)
    p.setPen(Qt.PenStyle.NoPen)
    p.fillPath(path, _w(a))


def _note(p, x, y, s, a):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_w(a))
    p.drawEllipse(QPointF(x, y), s * .42, s * .32)
    p.setPen(QPen(_w(a), max(1.0, s * .14)))
    p.drawLine(QPointF(x + s * .38, y), QPointF(x + s * .38, y - s * 1.3))
    p.drawLine(QPointF(x + s * .38, y - s * 1.3), QPointF(x + s * .9, y - s * 1.0))


def _gem(p, x, y, s, a):
    path = QPainterPath()
    path.moveTo(x, y - s)
    path.lineTo(x + s * .7, y)
    path.lineTo(x, y + s)
    path.lineTo(x - s * .7, y)
    path.closeSubpath()
    p.setPen(QPen(_w(a), max(.8, s * .12)))
    p.setBrush(_w(a * .25))
    p.drawPath(path)


def _polar(c, r, ang):
    return QPointF(c.x() + math.cos(ang) * r, c.y() + math.sin(ang) * r)


# ── рамки ── #

def _glass(p, S, t):
    c, R, w = _base(p, S)
    _sweep(p, c, R, w, t * 70)


def _halo(p, S, t):
    k = .5 + .5 * math.sin(t * 2 * math.pi / 3.2)
    c, R, w = _base(p, S, glass=.05 + .05 * k)
    g = QRadialGradient(c, R * 1.0)
    g.setColorAt(.80, _w(0))
    g.setColorAt(.93, _w(.18 + .18 * k))
    g.setColorAt(1.0, _w(0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawEllipse(c, R, R)


def _orbit(p, S, t):
    c, R, w = _base(p, S, glass=.05)
    a = t * 1.6
    _dot(p, *(_polar(c, R - w / 2, a).x(), _polar(c, R - w / 2, a).y()), S * .022, .95)
    for i in range(1, 9):                                         # хвост
        q = _polar(c, R - w / 2, a - i * .09)
        _dot(p, q.x(), q.y(), S * .016 * (1 - i / 10), .5 * (1 - i / 9), glow=False)


def _eq(p, S, t):
    c, R, w = _base(p, S, glass=.04)
    lv = _lvl()
    n = 36
    for i in range(n):
        ang = 2 * math.pi * i / n - math.pi / 2
        k = .25 + .75 * abs(math.sin(i * 1.7 + t * 5.0)) * (.35 + .65 * lv)
        r0 = R - w * .85
        r1 = r0 + w * .7 * k
        p.setPen(QPen(_w(.35 + .55 * k), max(1.0, S * .011), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(_polar(c, r0, ang), _polar(c, r1, ang))


def _wave(p, S, t):
    c, R, w = _base(p, S, glass=.04, inner=.18)
    path = QPainterPath()
    n = 120
    for i in range(n + 1):
        ang = 2 * math.pi * i / n
        r = R - w / 2 + w * .32 * math.sin(ang * 6 + t * 2.4)
        pt = _polar(c, r, ang)
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    p.setPen(QPen(_w(.85), max(1.0, S * .012)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)


def _ripple(p, S, t):
    c, R, w = _base(p, S)
    for k in range(3):
        ph = ((t / 2.4) + k / 3) % 1.0
        r = R - w + w * 1.1 * ph
        p.setPen(QPen(_w(.55 * (1 - ph)), max(.8, S * .008)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, r, r)


def _dots(p, S, t):
    c, R, w = _base(p, S, glass=.03, edge=.55)
    n = 28
    for i in range(n):
        ang = 2 * math.pi * i / n + t * .5
        k = .5 + .5 * math.sin(i * .8 - t * 3)
        q = _polar(c, R - w / 2, ang)
        _dot(p, q.x(), q.y(), S * (.009 + .006 * k), .45 + .5 * k, glow=False)


def _aurora(p, S, t):
    c = QPointF(S / 2, S / 2)
    R = S / 2 - S * .02
    w = S * .085
    g = QConicalGradient(c, t * 30)
    try:
        import ph_style as ph
        base = ph.tint()
    except Exception:                                          # noqa: BLE001
        base = QColor(200, 210, 255)
    for i, a in enumerate((.55, .12, .45, .08, .55)):
        cc = QColor(base)
        cc.setAlphaF(a)
        g.setColorAt(i / 4, cc)
    path = QPainterPath()
    path.addEllipse(c, R, R)
    hole = QPainterPath()
    hole.addEllipse(c, R - w, R - w)
    p.fillPath(path.subtracted(hole), g)
    p.setPen(QPen(_w(.8), max(1.0, S * .01)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(c, R, R)


def _vinylmini(p, S, t):
    c, R, w = _base(p, S, band=.1, glass=.12, edge=.7)
    for k in range(1, 4):
        p.setPen(QPen(_w(.12), max(.6, S * .004)))
        p.drawEllipse(c, R - w * k / 4, R - w * k / 4)
    _arc(p, c, R - w / 2, -t * 120, 38, _w(.55), w * .5)
    _arc(p, c, R - w / 2, -t * 120 + 180, 22, _w(.3), w * .5)


def _comet(p, S, t):
    c, R, w = _base(p, S, glass=.04)
    a = t * 2.2
    for i in range(24):
        q = _polar(c, R - w / 2, a - i * .06)
        _dot(p, q.x(), q.y(), S * .02 * (1 - i / 26), .9 * (1 - i / 24) ** 1.6, glow=(i == 0))


# — за ачивки —

def _first_post(p, S, t):
    c, R, w = _base(p, S, glass=.1)
    g = QConicalGradient(c, t * 40)
    for pos, a in ((0, .6), (.25, .15), (.5, .55), (.75, .12), (1, .6)):
        g.setColorAt(pos, _w(a))
    path = QPainterPath()
    path.addEllipse(c, R, R)
    hole = QPainterPath()
    hole.addEllipse(c, R - w, R - w)
    p.fillPath(path.subtracted(hole), g)
    _star(p, S * .82, S * .18, S * .05 * (1 + .25 * math.sin(t * 3)), .9)


def _author(p, S, t):
    c, R, w = _base(p, S)
    for i in range(12):
        k = max(0.0, math.cos(((t * 1.5) % 12 - i) * .9)) if anim_speed() else .4
        q = _polar(c, R - w / 2, i * math.pi / 6 - math.pi / 2)
        _dot(p, q.x(), q.y(), S * (.012 + .008 * k), .35 + .6 * k, glow=k > .5)


def _social(p, S, t):
    c = QPointF(S / 2, S / 2)
    R = S / 2 - S * .02
    w = S * .08
    g = QConicalGradient(c, t * 25)
    for i, (r, gg, b) in enumerate(((255, 190, 200), (255, 230, 190), (200, 255, 220), (190, 225, 255),
                                    (230, 200, 255), (255, 190, 200))):
        g.setColorAt(i / 5, QColor(r, gg, b, 150))
    path = QPainterPath()
    path.addEllipse(c, R, R)
    hole = QPainterPath()
    hole.addEllipse(c, R - w, R - w)
    p.fillPath(path.subtracted(hole), g)
    p.setPen(QPen(_w(.8), max(1.0, S * .01)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(c, R, R)


def _dj(p, S, t):
    _vinylmini(p, S, t * 1.4)


def _together(p, S, t):
    c, R, w = _base(p, S, glass=.04)
    for sgn, rr in ((1, R - w * .3), (-1, R - w * .75)):
        q = _polar(c, rr, sgn * t * 1.3)
        _dot(p, q.x(), q.y(), S * .02, .9)
        _arc(p, c, rr, -math.degrees(sgn * t * 1.3) - (30 if sgn > 0 else -30) * 0, 0, _w(0), 1)


def _inseparable(p, S, t):
    c, R, w = _base(p, S)
    beat = abs(math.sin(t * math.pi * 1.2)) ** 3
    for i in range(4):
        q = _polar(c, R - w / 2, i * math.pi / 2 - math.pi / 4)
        _heart(p, q.x(), q.y(), S * (.045 + .015 * beat), .55 + .4 * beat)


def _sleuth(p, S, t):
    c, R, w = _base(p, S, glass=.04)
    p.setPen(QPen(_w(.5), max(1.0, S * .01), Qt.PenStyle.DashLine))
    p.drawEllipse(c, R - w / 2, R - w / 2)
    a = t * .9
    q = _polar(c, R - w / 2, a)
    p.setPen(QPen(_w(.95), max(1.2, S * .014)))
    p.setBrush(_w(.15))
    p.drawEllipse(q, S * .045, S * .045)
    p.drawLine(_polar(q, S * .045, a + .8), _polar(q, S * .085, a + .8))


def _hitmaker(p, S, t):
    c, R, w = _base(p, S)
    for i in range(14):                                           # язычки пламени снизу, мерцают
        ang = math.pi * (.15 + .7 * i / 13)
        h = w * (1.0 + .6 * abs(math.sin(t * 6 + i * 1.3)))
        base = _polar(c, R - w * .2, ang)
        tip = _polar(c, R + h * .6, ang + .04 * math.sin(t * 4 + i))
        path = QPainterPath()
        path.moveTo(_polar(c, R - w * .2, ang - .06))
        path.quadTo(tip, _polar(c, R - w * .2, ang + .06))
        path.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.fillPath(path, _w(.35 + .3 * abs(math.sin(t * 5 + i))))
        del base


def _melomane(p, S, t):
    c, R, w = _base(p, S)
    for i in range(6):
        ang = i * math.pi / 3 + t * .35
        bob = math.sin(t * 2 + i) * S * .012
        q = _polar(c, R - w / 2, ang)
        _note(p, q.x(), q.y() + bob, S * .038, .75)


def _collector(p, S, t):
    c, R, w = _base(p, S)
    for i in range(8):
        k = .5 + .5 * math.sin(t * 2.6 + i * 2.1)
        q = _polar(c, R - w / 2, i * math.pi / 4)
        _gem(p, q.x(), q.y(), S * (.03 + .008 * k), .5 + .45 * k)


def _group(p, S, t):
    c, R, w = _base(p, S)
    path = QPainterPath()                                         # корона сверху
    cx, top = c.x(), c.y() - R
    sw = S * .34
    path.moveTo(cx - sw / 2, top + S * .06)
    for i, (dx, dy) in enumerate(((-.5, -.06), (-.25, .02), (0, -.1), (.25, .02), (.5, -.06))):
        path.lineTo(cx + dx * sw, top + dy * S)
    path.lineTo(cx + sw / 2, top + S * .06)
    path.closeSubpath()
    p.setPen(QPen(_w(.9), max(1.0, S * .01)))
    p.setBrush(_w(.18))
    p.drawPath(path)
    gl = (t * .6) % 1.6 - .3
    if 0 <= gl <= 1:
        _star(p, cx - sw / 2 + sw * gl, top - S * .02, S * .03, .9)


def _champion(p, S, t):
    c, R, w = _base(p, S)
    for side in (-1, 1):                                          # лавровые листья по бокам
        for i in range(6):
            ang = math.pi / 2 + side * (math.pi * (.25 + .09 * i))
            q = _polar(c, R - w * .3, ang)
            p.save()
            p.translate(q)
            p.rotate(math.degrees(ang) + 90 + side * 35)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_w(.6))
            p.drawEllipse(QPointF(0, 0), S * .018, S * .04)
            p.restore()
    _sweep(p, c, R, w, t * 55, .6, .1)


def _night_owl(p, S, t):
    c, R, w = _base(p, S, glass=.05)
    m = QPointF(c.x() + R * .62, c.y() - R * .62)                 # месяц
    path = QPainterPath()
    path.addEllipse(m, S * .07, S * .07)
    cut = QPainterPath()
    cut.addEllipse(QPointF(m.x() + S * .03, m.y() - S * .02), S * .06, S * .06)
    p.fillPath(path.subtracted(cut), _w(.9))
    for i in range(9):
        k = .5 + .5 * math.sin(t * 2.2 + i * 1.9)
        q = _polar(c, R - w * (.3 + .4 * (i % 2)), i * .7 + 1.5)
        _star(p, q.x(), q.y(), S * (.012 + .012 * k), .3 + .6 * k)


def _early_bird(p, S, t):
    c, R, w = _base(p, S)
    for i in range(11):                                           # лучи солнца снизу
        ang = math.pi * (.2 + .6 * i / 10)
        ln = w * (.6 + .5 * (.5 + .5 * math.sin(t * 2 + i)))
        p.setPen(QPen(_tint(.7, warm=.4), max(1.0, S * .012), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(_polar(c, R + S * .005, ang), _polar(c, R + ln, ang))


def _streak7(p, S, t):
    c, R, w = _base(p, S)
    lit = int(t * 2) % 8
    for i in range(7):
        q = _polar(c, R - w / 2, -math.pi / 2 + (i - 3) * .32)
        _dot(p, q.x(), q.y(), S * .018, .95 if i < lit else .25, glow=i < lit)


def _explorer(p, S, t):
    c, R, w = _base(p, S)
    for i in range(48):
        ang = 2 * math.pi * i / 48
        ln = w * (.55 if i % 12 == 0 else .3 if i % 4 == 0 else .15)
        p.setPen(QPen(_w(.7 if i % 12 == 0 else .35), max(.8, S * .007)))
        p.drawLine(_polar(c, R - S * .01, ang), _polar(c, R - S * .01 - ln, ang))
    a = math.sin(t * .8) * .6 - math.pi / 2                       # стрелка покачивается
    q = _polar(c, R - w * .5, a)
    path = QPainterPath()
    path.moveTo(_polar(c, R - w * .05, a))
    path.lineTo(_polar(q, S * .02, a + math.pi / 2))
    path.lineTo(_polar(c, R - w * .95, a))
    path.lineTo(_polar(q, S * .02, a - math.pi / 2))
    path.closeSubpath()
    p.setPen(Qt.PenStyle.NoPen)
    p.fillPath(path, _w(.95))


def _loyal(p, S, t):
    c, R, w = _base(p, S)
    beat = abs(math.sin(t * math.pi * 1.25)) ** 4
    _heart(p, c.x(), c.y() + R - w * .2, S * (.08 + .025 * beat), .9)
    for k in range(2):
        ph = ((t * .8) + k / 2) % 1.0
        _arc(p, c, R + S * .01 + ph * S * .03, 240, 60, _w(.4 * (1 - ph)), max(.8, S * .007))


def _marathon(p, S, t):
    c, R, w = _base(p, S, glass=.04)
    for i in range(60):
        ang = 2 * math.pi * i / 60
        ln = w * (.45 if i % 5 == 0 else .2)
        p.setPen(QPen(_w(.5 if i % 5 == 0 else .22), max(.7, S * .006)))
        p.drawLine(_polar(c, R - S * .012, ang), _polar(c, R - S * .012 - ln, ang))
    prog = (t / 6) % 1.0
    _arc(p, c, R - w * .75, 90, -prog * 360, _w(.85), max(1.2, S * .016))


# — роли и сезоны —

def _admin(p, S, t):
    c, R, w = _base(p, S, edge=.95)
    for i in range(16):                                           # тёплые лучи — солнце автора ECHOES
        ang = 2 * math.pi * i / 16 + t * .25
        ln = w * (.7 if i % 2 == 0 else .4)
        p.setPen(QPen(_tint(.75, warm=.7), max(1.0, S * .013), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(_polar(c, R - w * .9, ang), _polar(c, R - w * .9 + ln, ang))
    _sweep(p, c, R, w, t * 50, .5, .12)


def _mod(p, S, t):
    c, R, w = _base(p, S, glass=.08)
    p.setPen(QPen(_tint(.85, cool=.8), max(1.0, S * .014), Qt.PenStyle.DashLine))
    p.save()
    p.translate(c)
    p.rotate(t * 20)
    p.translate(-c)
    p.drawEllipse(c, R - w / 2, R - w / 2)
    p.restore()


def _season(kind):
    def f(p, S, t):
        c, R, w = _base(p, S)
        if kind == "newyear" or kind == "winter":
            for i in range(10):
                ph = ((t * .25) + i / 10) % 1.0
                ang = i * .63
                q = _polar(c, R - w * ph, ang)
                _star(p, q.x(), q.y(), S * .02, .9 * (1 - ph * .6))
        elif kind == "halloween":
            for i in range(3):
                q = _polar(c, R + S * .0 - w * .4, t * (.9 + i * .2) + i * 2.1)
                p.setPen(QPen(_w(.85), max(1.0, S * .012)))
                p.drawLine(QPointF(q.x() - S * .03, q.y()), QPointF(q.x(), q.y() + S * .015))
                p.drawLine(QPointF(q.x(), q.y() + S * .015), QPointF(q.x() + S * .03, q.y()))
        elif kind == "spring":
            for i in range(8):
                q = _polar(c, R - w / 2, i * math.pi / 4 + t * .3)
                p.save()
                p.translate(q)
                p.rotate(t * 40 + i * 45)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(_tint(.7, warm=.15))
                p.drawEllipse(QPointF(0, 0), S * .02, S * .035)
                p.restore()
        else:                                                     # лето — бликует как солнце на воде
            _sweep(p, c, R, w, t * 80, .7, .2)
            _sweep(p, c, R, w, -t * 50 + 120, .4, .1)
    return f


# — для спонсоров —

def _prism(p, S, t):
    c = QPointF(S / 2, S / 2)
    R = S / 2 - S * .02
    w = S * .09
    g = QConicalGradient(c, t * 45)
    cols = ((255, 120, 160), (255, 200, 120), (140, 255, 200), (120, 190, 255), (200, 140, 255), (255, 120, 160))
    for i, (r, gg, b) in enumerate(cols):
        g.setColorAt(i / 5, QColor(r, gg, b, 200))
    path = QPainterPath()
    path.addEllipse(c, R, R)
    hole = QPainterPath()
    hole.addEllipse(c, R - w, R - w)
    p.fillPath(path.subtracted(hole), g)
    p.setPen(QPen(_w(.95), max(1.0, S * .012)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(c, R, R)
    p.setPen(QPen(_w(.4), max(.8, S * .006)))
    p.drawEllipse(c, R - w, R - w)
    _sweep(p, c, R, w, -t * 90, .6, .08)


def _crown_sp(p, S, t):
    _group(p, S, t)
    c = QPointF(S / 2, S / 2)
    R = S / 2 - S * .02
    for i in range(10):                                           # искры поднимаются от короны
        ph = ((t * .5) + i / 10) % 1.0
        x = c.x() + math.sin(i * 2.3) * S * .18
        y = c.y() - R - S * .02 - ph * S * .08
        _dot(p, x, y, S * .008, .8 * (1 - ph), glow=False)


def _nebula(p, S, t):
    c = QPointF(S / 2, S / 2)
    R = S / 2 - S * .02
    w = S * .11
    path = QPainterPath()
    path.addEllipse(c, R, R)
    hole = QPainterPath()
    hole.addEllipse(c, R - w, R - w)
    band = path.subtracted(hole)
    p.save()
    p.setClipPath(band)
    for i in range(5):
        a = t * (.3 + .1 * i) + i * 1.3
        q = _polar(c, R - w / 2, a)
        g = QRadialGradient(q, w * 1.6)
        g.setColorAt(0, QColor(200, 190, 255, 110))
        g.setColorAt(1, QColor(200, 190, 255, 0))
        p.fillRect(QRectF(0, 0, S, S), g)
    p.restore()
    p.setPen(QPen(_w(.85), max(1.0, S * .01)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(c, R, R)
    for i in range(12):
        k = .5 + .5 * math.sin(t * 3 + i * 1.7)
        q = _polar(c, R - w * (.2 + .6 * ((i * 7) % 10) / 10), i * .52)
        _dot(p, q.x(), q.y(), S * .006, .4 + .5 * k, glow=False)


def _constellation(p, S, t):
    c, R, w = _base(p, S, glass=.04)
    pts = [_polar(c, R - w * (.25 + .5 * ((i * 3) % 4) / 3), i * 2 * math.pi / 9 + .2) for i in range(9)]
    p.setPen(QPen(_w(.28), max(.8, S * .006)))
    for i in range(len(pts)):
        p.drawLine(pts[i], pts[(i + 1) % len(pts)])
    for i, q in enumerate(pts):
        k = .5 + .5 * math.sin(t * 2.4 + i * 1.4)
        _star(p, q.x(), q.y(), S * (.016 + .012 * k), .55 + .45 * k)


def _gold(p, S, t):
    c = QPointF(S / 2, S / 2)
    R = S / 2 - S * .02
    w = S * .085
    g = QConicalGradient(c, t * 35)
    for pos, a in ((0, .95), (.2, .45), (.5, .9), (.75, .4), (1, .95)):
        g.setColorAt(pos, _tint(a, warm=.85))
    path = QPainterPath()
    path.addEllipse(c, R, R)
    hole = QPainterPath()
    hole.addEllipse(c, R - w, R - w)
    p.fillPath(path.subtracted(hole), g)
    p.setPen(QPen(_tint(.95, warm=.5), max(1.0, S * .01)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(c, R, R)
    p.drawEllipse(c, R - w, R - w)


def _flare(p, S, t):
    c, R, w = _base(p, S)
    a = t * 1.1
    q = _polar(c, R - w / 2, a)
    g = QRadialGradient(q, S * .16)
    g.setColorAt(0, _w(.85))
    g.setColorAt(.2, _w(.3))
    g.setColorAt(1, _w(0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawEllipse(q, S * .16, S * .16)
    p.setPen(QPen(_w(.6), max(.8, S * .006)))
    p.drawLine(_polar(q, S * .12, a), _polar(q, S * .12, a + math.pi))
    p.drawLine(_polar(q, S * .08, a + math.pi / 2), _polar(q, S * .08, a - math.pi / 2))


def _heartbeat(p, S, t):
    c, R, w = _base(p, S, glass=.05)
    path = QPainterPath()                                         # кардиограмма бежит по кругу
    n = 160
    off = (t * .5) % 1.0
    for i in range(n + 1):
        u = i / n
        ang = 2 * math.pi * u - math.pi / 2
        d = (u - off) % 1.0
        spike = 0.0
        if d < .05:
            spike = math.sin(d / .05 * math.pi) * (1.0 if d < .025 else -.5)
        r = R - w / 2 - spike * w * .9
        pt = _polar(c, r, ang)
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    p.setPen(QPen(_w(.9), max(1.0, S * .012)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    _heart(p, c.x(), c.y() + R - w * .2, S * .055, .9)


def _echo(p, S, t):
    c, R, w = _base(p, S, glass=.04)
    lv = _lvl()
    for k in range(4):                                            # «эхо»: кольца расходятся в такт
        ph = ((t / 1.8) + k / 4) % 1.0
        r = R - w * (1 - ph)
        p.setPen(QPen(_w((.25 + .5 * lv) * (1 - ph)), max(.8, S * .01)))
        p.drawEllipse(c, r, r)
    p.setFont(_font(S * .07))
    p.setPen(_w(.85))
    p.drawText(QRectF(c.x() - S * .2, c.y() + R - w * 1.05, S * .4, w), Qt.AlignmentFlag.AlignCenter, "E")


def _font(px):
    from PyQt6.QtGui import QFont
    f = QFont()
    f.setFamilies(["Inter PA", "Segoe UI"])
    f.setPixelSize(max(6, int(px)))
    f.setWeight(QFont.Weight(700))
    return f


_DRAW = {
    "glass": _glass, "halo": _halo, "orbit": _orbit, "eq": _eq, "wave": _wave, "ripple": _ripple, "dots": _dots,
    "aurora": _aurora, "vinylmini": _vinylmini, "comet": _comet,
    "first_post": _first_post, "author": _author, "social": _social, "dj": _dj, "together": _together,
    "inseparable": _inseparable, "sleuth": _sleuth, "hitmaker": _hitmaker, "melomane": _melomane,
    "collector": _collector, "group": _group, "champion": _champion, "night_owl": _night_owl,
    "early_bird": _early_bird, "streak7": _streak7, "explorer": _explorer, "loyal": _loyal, "marathon": _marathon,
    "admin": _admin, "mod": _mod,
    "season:halloween": _season("halloween"), "season:newyear": _season("newyear"), "season:winter": _season("winter"),
    "season:spring": _season("spring"), "season:summer": _season("summer"),
    "prism": _prism, "crown": _crown_sp, "nebula": _nebula, "constellation": _constellation, "gold": _gold,
    "flare": _flare, "heartbeat": _heartbeat, "echo": _echo,
}


def kind_of(spec: dict) -> str:
    """id рамки (net_frames) → вид для draw: ach:x → x, role → роль, ph:x / sp:x → x, season:x как есть."""
    fid = (spec or {}).get("id", "")
    if fid == "role":
        return spec.get("role", "")
    if fid.startswith(("ach:", "ph:", "sp:")):
        return fid.split(":", 1)[1]
    return fid


def draw(p: QPainter, kind: str, S: float, t: float = 0.0) -> bool:
    fn = _DRAW.get(kind)
    if fn is None:
        return False
    p.save()
    try:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fn(p, S, t * anim_speed())
    finally:
        p.restore()
    return True
