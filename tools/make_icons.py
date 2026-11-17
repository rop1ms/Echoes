"""Собрать иконки ECHOES из знака (app/echoes_mark.py):

    app/icon.png                      512×512 — окно, трей, медиаплеер Windows
    app/icon.ico                      16…256 px (PNG внутри) — exe, ярлыки, панель задач
    app/assets/logo/echoes_icon.svg   иконка вектором (чёрный квадрат + белый знак)
    app/assets/logo/echoes_mark.svg   только знак, белый на прозрачном
    app/assets/logo/echoes_mark.png   только знак, 1024 px

Запуск: <python с PyQt6> tools/make_icons.py
"""
from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from PyQt6.QtCore import QBuffer, QIODevice, QRectF, Qt  # noqa: E402
from PyQt6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402

ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def png_bytes(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def write_ico(path: Path, images: list[QImage]):
    """ICO с PNG внутри (Windows Vista+ понимает любой размер)."""
    blobs = [png_bytes(im) for im in images]
    out = io.BytesIO()
    out.write(struct.pack("<HHH", 0, 1, len(images)))
    offset = 6 + 16 * len(images)
    for im, b in zip(images, blobs):
        w = im.width() if im.width() < 256 else 0
        h = im.height() if im.height() < 256 else 0
        out.write(struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(b), offset))
        offset += len(b)
    for b in blobs:
        out.write(b)
    path.write_bytes(out.getvalue())


def main():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])  # noqa: F841
    import echoes_mark as em
    appdir = ROOT / "app"
    logo = appdir / "assets" / "logo"
    logo.mkdir(parents=True, exist_ok=True)
    em.icon_image(512).save(str(appdir / "icon.png"), "PNG")
    write_ico(appdir / "icon.ico", [em.icon_image(s) for s in ICO_SIZES])
    (logo / "echoes_icon.svg").write_text(em.svg(icon=True), encoding="utf-8")
    (logo / "echoes_mark.svg").write_text(em.svg(icon=False), encoding="utf-8")
    m = QImage(1024, 1024, QImage.Format.Format_ARGB32_Premultiplied)
    m.fill(Qt.GlobalColor.transparent)
    p = QPainter(m)
    em.paint_mark(p, QRectF(0, 0, 1024, 1024), em.FG, 0.92)
    p.end()
    m.save(str(logo / "echoes_mark.png"), "PNG")
    print("icons:", ", ".join(str(x.relative_to(ROOT)) for x in
                              (appdir / "icon.png", appdir / "icon.ico", logo / "echoes_icon.svg",
                               logo / "echoes_mark.svg", logo / "echoes_mark.png")))


if __name__ == "__main__":
    main()
