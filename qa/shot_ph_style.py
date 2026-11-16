"""Снимок основы стиля Phantom (этап 1): фон, стекло, тени, шрифт, иконки и стандартные виджеты, собранные
в раскладку главного экрана Phantom — для сравнения с docs/phantom_ref/01_lyrics.png.

python qa/shot_ph_style.py [--out docs/phantom_ref/echoes_stage1.png] [--cover путь] [--size 1440x900]
Без окна (offscreen). Это не оболочка (она — этап 2), а витрина деталей.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["USERPROFILE"] = os.environ["HOME"] = tempfile.mkdtemp(prefix="echoes-ph-shot-")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from PyQt6.QtCore import QRectF, QSize, Qt  # noqa: E402
from PyQt6.QtGui import QImage, QPainter  # noqa: E402
from PyQt6.QtWidgets import (QApplication, QCheckBox, QHBoxLayout, QLabel, QSlider, QVBoxLayout,  # noqa: E402
                             QWidget)

import ph_backdrop  # noqa: E402
import ph_style as ph  # noqa: E402
import ph_widgets as pw  # noqa: E402

LYRICS = ["Holding on to the afterglow", "Every light that we used to know", "Running late but the night is slow",
          "Tell me where do the echoes go", "Under neon we drift alone"]


class Cover(QWidget):
    def __init__(self, src: str | None, parent=None):
        super().__init__(parent)
        self.src = src
        self._pm = None

    def paintEvent(self, e):
        p = QPainter(self)
        r = QRectF(self.rect())
        rad = ph.px(22)
        if self._pm is None or self._pm.size() != (self.size() * 2):
            img = QImage(self.src) if self.src else QImage()
            if img.isNull():
                self._pm = ph.placeholder_cover(self.size(), "Afterglow", "ECHOES Sessions", rad)
            else:
                self._pm = ph.rounded_pixmap(img, self.size(), rad)
        p.drawPixmap(0, 0, self._pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(ph.qcolor(ph.LINE_1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), rad, rad)
        p.end()


class Lyrics(QWidget):
    """Крупные строки: текущая — белая и резкая, остальные — тусклее и размытые (размытие — один раз)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cache = None

    def paintEvent(self, e):
        if self._cache is None or self._cache.size() != self.size():
            import blur_fx
            img = QImage(self.size(), QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(Qt.GlobalColor.transparent)
            f = ph.font(52, 700, -.035)
            y = self.height() * .52
            step = 96
            for i, line in enumerate(LYRICS):
                layer = QImage(self.size(), QImage.Format.Format_ARGB32_Premultiplied)
                layer.fill(Qt.GlobalColor.transparent)
                p = QPainter(layer)
                p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
                p.setFont(f)
                p.setPen(ph.white(.62 if i == 0 else .36))
                p.drawText(0, int(y + i * step), line)
                p.end()
                if i:
                    layer = blur_fx.blur_image(layer, 2.2 + i * 1.6)
                p = QPainter(img)
                p.drawImage(0, 0, layer)
                p.end()
            self._cache = img
        p = QPainter(self)
        p.drawImage(0, 0, self._cache)
        p.end()


def build(cover: str | None, w: int, h: int) -> QWidget:
    root = QWidget()
    root.setObjectName("PhRoot")
    root.resize(w, h)
    root.setFont(ph.font(ph.TEXT_BASE))
    root.setStyleSheet(ph.qss())
    bg = ph_backdrop.PhBackground(root)
    bg.setGeometry(0, 0, w, h)

    host = pw.ShadowHost(root)
    host.setGeometry(0, 0, w, h)
    g = 36                                                   # поле страницы

    # ── верхняя полоса ── #
    top = QWidget(host)
    top.setGeometry(0, 0, w, ph.TOPBAR_HEIGHT)
    tl = QHBoxLayout(top)
    tl.setContentsMargins(g - 2, 0, g - 16, 0)
    tl.setSpacing(16)
    word = pw.label("ECHOES", "PhWordmark", font=ph.font(15, 650, -.01))
    tl.addWidget(word)
    clock = QVBoxLayout()
    clock.setSpacing(1)
    clock.addStretch(1)
    clock.addWidget(pw.label("11:47", "PhBody", font=ph.font(13, 600, .01, tnum=True)))
    dr = QHBoxLayout()
    dr.setSpacing(6)
    dr.addWidget(pw.label("16 ноября", "PhMuted"))
    badge = pw.label("ПН", "PhBadge", font=ph.font(10, 600, .14))
    dr.addWidget(badge)
    dr.addStretch(1)
    clock.addLayout(dr)
    clock.addStretch(1)
    tl.addLayout(clock)
    tl.addStretch(1)
    mode = pw.PhSegments([("live", "LIVE"), ("text", "ТЕКСТ")], compact=True, stretch=False)
    mode.set_current("text")
    tl.addWidget(mode)
    for name, tip in (("earth", "Echoes"), ("library", "Библиотека"), ("list-music", "Очередь"),
                      ("settings", "Настройки")):
        tl.addWidget(pw.icon_button(name, "ghost", "top", 18, tip))
    tl.addSpacing(10)
    for name in ("minus", "square", "x"):
        b = pw.icon_button(name, "ghost", "md", 14 if name != "square" else 12)
        b.setObjectName("PhWindow")
        tl.addWidget(b)

    island = pw.PhSurface("island", host)
    island.setGeometry(int(w * .42), 18, 230, 36)
    il = QHBoxLayout(island)
    il.setContentsMargins(8, 0, 12, 0)
    il.setSpacing(10)
    av = QLabel()
    av.setPixmap(ph.placeholder_cover(QSize(22, 22), "Afterglow", "", 6))
    il.addWidget(av)
    il.addWidget(pw.label("Afterglow", "PhBody", font=ph.font(12, 600)))
    il.addStretch(1)
    bars = QLabel()
    bars.setPixmap(ph.icon_pixmap("chart-column", 13, ph.TEXT_SECONDARY))
    il.addWidget(bars)

    # ── левая колонка ── #
    lw = int((w - 2 * g - 32) * .41)
    x0, y0 = g, 72
    cov_h = int(lw * .66)
    cov = Cover(cover, host)
    cov.setGeometry(x0, y0, lw, cov_h)
    exp = pw.icon_button("maximize-2", "surface", "sm", 13, "Открыть обложку", parent=cov)
    exp.move(lw - 42, 14)

    card = pw.PhSurface("panel", host)
    cy = y0 + cov_h + 18
    card.setGeometry(x0, cy, lw, 186)
    cl = QVBoxLayout(card)
    cl.setContentsMargins(20, 18, 20, 16)
    cl.setSpacing(4)
    row = QHBoxLayout()
    tcol = QVBoxLayout()
    tcol.setSpacing(1)
    tcol.addWidget(pw.label("Afterglow", "PhTitle", font=ph.font(22, 650, -.025)))
    tcol.addWidget(pw.label("ECHOES Sessions", "PhSub", font=ph.font(12, 550)))
    row.addLayout(tcol)
    row.addStretch(1)
    row.addWidget(pw.icon_button("heart", "ghost", "sm", 15, "В избранное"))
    row.addWidget(pw.icon_button("volume-1", "ghost", "sm", 15, "Громкость"))
    cl.addLayout(row)
    ctr = QHBoxLayout()
    ctr.setSpacing(10)
    ctr.addStretch(1)
    ctr.addWidget(pw.icon_button("shuffle", "surface", "sm", 14, "Случайный порядок"))
    ctr.addWidget(pw.icon_button("skip-back", "surface", "sm", 14, "Предыдущий"))
    ctr.addWidget(pw.icon_button("play", "solid", "play", 18, "Играть"))
    ctr.addWidget(pw.icon_button("skip-forward", "surface", "sm", 14, "Следующий"))
    ctr.addWidget(pw.icon_button("repeat", "surface", "sm", 14, "Повтор"))
    ctr.addStretch(1)
    cl.addSpacing(6)
    cl.addLayout(ctr)
    cl.addSpacing(10)
    seek = pw.PhSeek()
    seek.set_value(.34)
    cl.addWidget(seek)
    tr = QHBoxLayout()
    tr.addWidget(pw.label("1:12", "PhBody", font=ph.font(11, 600, tnum=True)))
    tr.addStretch(1)
    tr.addWidget(pw.label("3:00", "PhBody", font=ph.font(11, 600, tnum=True)))
    cl.addLayout(tr)

    wy = cy + 186 + 18
    wh = h - wy - 36
    ww = (lw - 18) // 2
    for i, (k, sub, cur) in enumerate((("Audio visualizer", "Живой спектр аудиосигнала", 0),
                                       ("Clock", "Минималистичные часы", 5))):
        wc = pw.PhSurface("card", host)
        wc.setGeometry(x0 + i * (ww + 18), wy, ww, wh)
        v = QVBoxLayout(wc)
        v.setContentsMargins(16, 14, 12, 12)
        v.setSpacing(0)
        hr = QHBoxLayout()
        hc = QVBoxLayout()
        hc.setSpacing(2)
        hc.addWidget(pw.kicker(k))
        hc.addWidget(pw.label(sub, "PhMuted", font=ph.font(10, 500)))
        hr.addLayout(hc)
        hr.addStretch(1)
        hr.addWidget(pw.icon_button("chevron-left", "ghost", "sm", 13))
        hr.addWidget(pw.icon_button("chevron-right", "ghost", "sm", 13))
        v.addLayout(hr)
        v.addStretch(1)
        if i == 1:
            v.addWidget(pw.label("11:47", "PhTitle", font=ph.font(18, 650, tnum=True)),
                        0, Qt.AlignmentFlag.AlignCenter)
            v.addWidget(pw.label("ПН · 16 ноября 2026", "PhMuted"), 0, Qt.AlignmentFlag.AlignCenter)
            v.addStretch(1)
        v.addWidget(pw.PhDots(8, cur), 0, Qt.AlignmentFlag.AlignHCenter)

    # ── правая колонка: текст ── #
    rx = x0 + lw + 32
    rw = w - rx - g
    head = QWidget(host)
    head.setGeometry(rx, 70, rw, 32)
    hl = QHBoxLayout(head)
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(10)
    hl.addWidget(pw.kicker("Lyrics"))
    chip = pw.text_button("  Синхронизировано", "small")
    chip.setIcon(ph.icon("circle-check", 12, ph.TEXT_PRIMARY))
    hl.addWidget(chip)
    src = pw.text_button("LRCLIB · 100%", "small", "file-text")
    hl.addWidget(src)
    hl.addStretch(1)
    hl.addWidget(pw.icon_button("sparkles", "surface", "sm", 13, "Эффекты слов", checkable=True))
    hl.addWidget(pw.text_button("0 мс", "small", "timer"))
    ly = Lyrics(host)
    ly.setGeometry(rx, 110, rw, h - 110)

    # ── витрина стандартных виджетов (справа вверху, поверх текста) ── #
    demo = pw.PhSurface("panel", host)
    demo.setGeometry(rx + rw - 460, 130, 460, 300)
    dl = QVBoxLayout(demo)
    dl.setContentsMargins(20, 18, 20, 18)
    dl.setSpacing(10)
    dl.addWidget(pw.kicker("Library"))
    dl.addWidget(pw.label("Библиотека", "PhTitle", font=ph.title_font(20)))
    seg = pw.PhSegments([("tracks", "Треки", "eighth-note"), ("pl", "Плейлисты", "list-music"),
                         ("dir", "Папки", "folder-open")])
    dl.addWidget(seg)
    sr = QHBoxLayout()
    sr.setSpacing(8)
    sr.addWidget(pw.PhSearch("Поиск по названию, исполнителю или альбому"), 1)
    for name in ("file-plus-corner", "folder-plus", "refresh-cw"):
        sr.addWidget(pw.icon_button(name, "surface", "lg", 16))
    dl.addLayout(sr)
    chips = QHBoxLayout()
    chips.setSpacing(6)
    for i, t in enumerate(("Все файлы", "Избранное", "Недавно прослушано")):
        chips.addWidget(pw.chip(t, i == 0))
    chips.addStretch(1)
    dl.addLayout(chips)
    sl = QSlider(Qt.Orientation.Horizontal)
    sl.setObjectName("PhSlider")
    sl.setRange(0, 100)
    sl.setValue(72)
    dl.addWidget(sl)
    sw = QCheckBox("Фоновая анимация")
    sw.setObjectName("PhSwitch")
    sw.setFont(ph.font(ph.TEXT_BASE, 500))
    sw.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    sw.setChecked(True)
    dl.addWidget(sw)
    return root


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "phantom_ref" / "echoes_stage1.png"))
    ap.add_argument("--cover", default="")
    ap.add_argument("--size", default="1440x900")
    a = ap.parse_args()
    w, h = (int(v) for v in a.size.lower().split("x"))
    app = QApplication(sys.argv[:1])
    ph.load_fonts()
    root = build(a.cover or None, w, h)
    root.show()
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 1.5:                    # фон картинки считается в потоке
        app.processEvents()
        time.sleep(.02)
    root.grab().save(a.out)
    print("saved", a.out)


if __name__ == "__main__":
    main()
