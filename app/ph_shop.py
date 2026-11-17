"""Магазин косметики и поддержка ECHOES (кнопка с пакетом в верхней полосе) и стена «Наши спонсоры» в Echoes.NET.

Ничего не продаётся за функции и ничего не урезается: всё в ECHOES бесплатно. Донат — добровольный, по ссылкам,
которые задал автор (net_sponsor.set_donate). Кто поддержал — получает статус спонсора от автора: значок, особые
рамки и один пост на стене спонсоров (после проверки модерацией).
"""
from __future__ import annotations

import time

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QFontMetrics, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (QComboBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPlainTextEdit, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

import ph_style as ph
import ph_widgets as pw


def _net(win):
    sh = getattr(win, "_ya", None)
    return sh.pages.get("net") if sh is not None else None


def _node(win):
    page = _net(win)
    return getattr(page, "node", None) if page is not None else None


def _avatar(win, size):
    page = _net(win)
    try:
        return page._my_avatar_pm(size)
    except Exception:                                          # noqa: BLE001
        return ph.placeholder_cover(size, str((win.profile or {}).get("nickname") or "Я"), "", size / 2)


def _ach(win) -> list:
    page = _net(win)
    out = []
    try:
        out = list(page.achievements()) if page is not None and page.node is not None else []
    except Exception:                                          # noqa: BLE001
        out = []
    nd = _node(win)
    if nd is not None:
        import net_sponsor
        if net_sponsor.is_sponsor(nd):
            out.append("__sponsor__")
    return out


def _wrap(w: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QScrollArea.Shape.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    sa.setStyleSheet("QScrollArea{background:transparent;border:none;}")
    sa.viewport().setAutoFillBackground(False)
    sa.viewport().setObjectName("PhShopView")
    sa.viewport().setStyleSheet("#PhShopView{background:transparent;}")
    w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    if not w.objectName():
        w.setObjectName("PhShopBody")
    w.setStyleSheet(f"#{w.objectName()}{{background:transparent;}}")
    sa.setWidget(w)
    return sa


def _card(parent=None) -> tuple[QWidget, QVBoxLayout]:
    c = pw.PhSurface("card", parent)
    v = QVBoxLayout(c)
    v.setContentsMargins(ph.px(22), ph.px(18), ph.px(22), ph.px(18))
    v.setSpacing(ph.px(8))
    return c, v


def _title(text, size=ph.TEXT_LG + 2):
    return pw.label(text, "PhTitle", font=ph.font(size, 650, -.01))


def _sub(text):
    lb = pw.label(text, "PhSub", font=ph.font(ph.TEXT_SM))
    lb.setWordWrap(True)
    return lb


# ══════════════════════════════════════════════════════════════════════════ #
#  Плитка рамки: живая при наведении (и в большом предпросмотре), статичная в покое
# ══════════════════════════════════════════════════════════════════════════ #

class FrameTile(QWidget):
    picked = pyqtSignal(dict)

    def __init__(self, avatar: QPixmap, spec: dict, name: str, locked: str = "", parent=None):
        super().__init__(parent)
        self.avatar, self.spec, self.name, self.locked = avatar, spec, name, locked
        self.setFixedSize(ph.px(116), ph.px(140))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(locked or name)
        self.selected = False
        self._hover = False
        self._t0 = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self.update)

    def enterEvent(self, e):
        self._hover = True
        self._timer.start()
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self._timer.stop()
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.picked.emit(self.spec)

    def paintEvent(self, e):
        # в покое плитка — одна готовая картинка (прокрутка магазина = копирование), живая — только под мышью
        if not self._hover:
            dpr = self.devicePixelRatioF() or 1.0
            key = (self.selected, bool(self.locked), self.width(), self.height(), dpr, self.name)
            if self.__dict__.get("_ck") != key:
                pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
                pm.setDevicePixelRatio(dpr)
                pm.fill(Qt.GlobalColor.transparent)
                q = QPainter(pm)
                try:
                    self._paint(q)
                finally:
                    q.end()
                self._cpm, self._ck = pm, key
            p = QPainter(self)
            p.drawPixmap(0, 0, self._cpm)
            p.end()
            return
        p = QPainter(self)
        try:
            self._paint(p)
        finally:
            p.end()

    def _paint(self, p: QPainter):
        import net_frames
        if True:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
            p.setPen(ph.qcolor(ph.LINE_3 if self.selected else ph.LINE_1))
            p.setBrush(ph.white(.09 if self.selected else .05 if self._hover else .025))
            p.drawRoundedRect(r, ph.px(16), ph.px(16))
            s = ph.px(84)
            t = time.monotonic() - self._t0 if self._hover else 1.2
            pm = net_frames.framed_anim(self.avatar, self.spec, s, t) if self.spec.get("id") not in ("none", "") \
                else net_frames.framed(self.avatar, {}, s)
            p.setOpacity(.38 if self.locked else 1.0)
            p.drawPixmap(QRectF((self.width() - s) / 2, ph.px(10), s, s), pm, QRectF(pm.rect()))
            p.setOpacity(1.0)
            f = ph.font(ph.TEXT_XS, 600)
            p.setFont(f)
            p.setPen(ph.qcolor(ph.TEXT_TERTIARY if self.locked else ph.TEXT_PRIMARY))
            fm = QFontMetrics(f)
            p.drawText(QRectF(ph.px(6), ph.px(100), self.width() - ph.px(12), ph.px(18)), Qt.AlignmentFlag.AlignCenter,
                       fm.elidedText(self.name, Qt.TextElideMode.ElideRight, self.width() - ph.px(12)))
            if self.locked:
                ic = ph.icon_pixmap("lock", 11, ph.TEXT_TERTIARY)
                p.drawPixmap(QRectF(self.width() / 2 - ph.px(6), ph.px(120), ph.px(12), ph.px(12)), ic,
                             QRectF(ic.rect()))


class _Flow(QWidget):
    """Плитки рядами: сколько влезает по ширине."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.g = QGridLayout(self)
        self.g.setContentsMargins(0, 0, 0, 0)
        self.g.setHorizontalSpacing(ph.px(10))
        self.g.setVerticalSpacing(ph.px(10))
        self.g.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.items = []
        self._cols = 0

    def add(self, w):
        self.items.append(w)
        self._cols = 0
        self._relayout()

    def _relayout(self):
        if not self.items:
            return
        cw = self.items[0].width() + self.g.horizontalSpacing()
        cols = max(1, (max(self.width(), cw) + self.g.horizontalSpacing()) // cw)
        if cols == self._cols:
            return
        self._cols = cols
        for w in self.items:
            self.g.removeWidget(w)
        for i, w in enumerate(self.items):
            self.g.addWidget(w, i // cols, i % cols)
        rows = (len(self.items) + cols - 1) // cols                # высота — по рядам (иначе раскладка сжимала до 0)
        h = max(w.sizeHint().height() if w.sizeHint().height() > 0 else w.height() for w in self.items)
        self.setMinimumHeight(rows * h + (rows - 1) * self.g.verticalSpacing())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        if not self.items:
            return 0
        cw = self.items[0].width() + self.g.horizontalSpacing()
        cols = max(1, (w + self.g.horizontalSpacing()) // cw)
        rows = (len(self.items) + cols - 1) // cols
        return rows * (self.items[0].height() + self.g.verticalSpacing())


# ══════════════════════════════════════════════════════════════════════════ #
#  Магазин
# ══════════════════════════════════════════════════════════════════════════ #

class ShopPage(QWidget):
    """Страница магазина: поддержать ECHOES (донат), статус спонсора, вся косметика с живыми предпросмотрами."""

    def __init__(self, lay, parent=None):
        super().__init__(parent)
        self.lay = lay
        self.win = lay.win
        self.setObjectName("YaPage")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.body = QWidget()
        self.v = QVBoxLayout(self.body)
        self.v.setContentsMargins(ph.px(4), ph.px(4), ph.px(12), ph.px(24))
        self.v.setSpacing(ph.px(14))
        outer.addWidget(_wrap(self.body))
        self._built = False

    def showEvent(self, e):
        super().showEvent(e)
        self.fill()

    def fill(self):
        while self.v.count():
            it = self.v.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        nd = _node(self.win)
        import net_sponsor
        sp = net_sponsor.is_sponsor(nd) if nd is not None else False
        self.v.addWidget(self._support_card(nd, sp))
        self.v.addWidget(self._frames_block(sp))
        self.v.addWidget(self._style_card())
        self.v.addStretch(1)

    # ── поддержать ── #
    def _support_card(self, nd, sp):
        import net_sponsor
        c, v = _card()
        top = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(ph.px(4))
        col.addWidget(pw.kicker("Support"))
        col.addWidget(_title("Поддержать ECHOES", ph.TEXT_2XL))
        col.addWidget(_sub("ECHOES бесплатный и таким останется: ничего не закрыто и не урезано. Если хочется "
                           "помочь развитию — поддержите автора. Спонсоры получают значок, особые рамки и свой пост "
                           "на стене «Наши спонсоры» в Echoes.NET."))
        top.addLayout(col, 1)
        if sp:
            tier = net_sponsor.TIERS.get(net_sponsor.tier(nd), "Спонсор")
            badge = pw.chip(f"  Вы {tier.lower()} ECHOES — спасибо!", checked=True)
            badge.setIcon(ph.icon("heart", 13, ph.TEXT_PRIMARY))
            top.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(top)
        links = net_sponsor.donate_links(nd) if nd is not None else []
        row = QHBoxLayout()
        row.setSpacing(ph.px(8))
        if links:
            for i, ln in enumerate(links):
                b = pw.text_button(ln["name"] or "Поддержать", "primary" if i == 0 else "secondary", icon="heart"
                                   if i == 0 else None)
                b.setToolTip(ln["url"])
                b.clicked.connect(lambda _=False, u=ln["url"]: QDesktopServices.openUrl(QUrl(u)))
                row.addWidget(b)
        else:
            row.addWidget(_sub("Ссылки на донаты появятся здесь, когда автор их добавит." if nd is not None else
                               "Включите Echoes.NET, чтобы увидеть ссылки на донаты и свой статус."))
        row.addStretch(1)
        if nd is not None:
            code = pw.text_button("Скопировать мой код", "ghost", icon="copy")
            code.setToolTip("Укажите код в комментарии к донату — автор выдаст статус спонсора")
            code.clicked.connect(lambda: getattr(_net(self.win), "copy_code", lambda: None)())
            row.addWidget(code)
            if nd.my_role() == "admin":
                cfg = pw.text_button("Ссылки на донаты…", "ghost", icon="settings")
                cfg.clicked.connect(self._edit_links)
                row.addWidget(cfg)
        v.addLayout(row)
        note = net_sponsor.donate_note(nd) if nd is not None else ""
        hint = note or "В комментарии к донату укажите свой код Echoes.NET — так автор узнает, кому выдать статус."
        v.addWidget(_sub(hint))
        wall = pw.text_button("Стена «Наши спонсоры»", "small", icon="chevron-right")
        wall.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        wall.clicked.connect(self._open_wall)
        v.addWidget(wall, 0, Qt.AlignmentFlag.AlignLeft)
        return c

    def _open_wall(self):
        sh = self.win._ya
        sh.show_page("net")
        page = _net(self.win)
        if page is not None:
            page.show_tab("sponsors")

    def _edit_links(self):
        nd = _node(self.win)
        if nd is None:
            return
        import net_sponsor
        d = DonateLinksDialog(net_sponsor.donate_links(nd), net_sponsor.donate_note(nd), self)
        if d.exec():
            nd.call(net_sponsor.set_donate, nd, d.links(), d.note())
            QTimer.singleShot(600, self.fill)

    # ── рамки ── #
    def _frames_block(self, sp):
        import net_cosmetics
        import net_frames
        c, v = _card()
        head = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(ph.px(2))
        col.addWidget(pw.kicker("Frames"))
        col.addWidget(_title("Рамки аватарки"))
        col.addWidget(_sub("У каждой рамки своя анимация — наведите, чтобы увидеть. Видна всем в Echoes.NET: в "
                           "профиле, ленте и чатах."))
        head.addLayout(col, 1)
        self.big = QLabel()
        self.big.setFixedSize(ph.px(120), ph.px(120))
        head.addWidget(self.big)
        bcol = QVBoxLayout()
        self.pick_name = _title("—", ph.TEXT_BASE + 1)
        self.pick_hint = _sub("")
        self.pick_btn = pw.text_button("Надеть", "primary", icon="check")
        self.pick_btn.clicked.connect(self._apply)
        bcol.addStretch(1)
        bcol.addWidget(self.pick_name)
        bcol.addWidget(self.pick_hint)
        bcol.addWidget(self.pick_btn, 0, Qt.AlignmentFlag.AlignLeft)
        bcol.addStretch(1)
        head.addLayout(bcol)
        v.addLayout(head)
        av = _avatar(self.win, 120)
        self._av = av
        ach = set(_ach(self.win))
        page = _net(self.win)
        names = getattr(page, "ACH", {}) or {}
        cur = ((self.win.settings.get("ya_profile_deco") or {}).get("frame") or {}).get("id", "none")
        self._tiles = []

        def section(title, items):
            v.addWidget(pw.label(title.upper(), "PhKicker", font=ph.kicker_font()))
            fl = _Flow()
            for spec, name, lock in items:
                t = FrameTile(av, spec, name, lock)
                t.selected = spec.get("id") == cur
                t.picked.connect(lambda s, tt=t: self._pick(s, tt))
                fl.add(t)
                self._tiles.append(t)
            v.addWidget(fl)

        section("Phantom — бесплатно", [({"id": "none"}, "Без рамки", "")] +
                [({"id": "ph:" + k}, n, "") for k, n in net_cosmetics.FREE.items()])
        lock_sp = "" if sp else "Для спонсоров ECHOES — поддержите проект выше"
        section("Для спонсоров", [({"id": "sp:" + k}, n, lock_sp) for k, n in net_cosmetics.SPONSOR.items()])
        section("За ачивки", [({"id": "ach:" + k}, n, "" if k in ach else
                               "Откроется с ачивкой «" + names.get(k, (k, ""))[0] + "»: " + names.get(k, ("", ""))[1])
                              for k, n in net_frames.ACH_FRAMES.items()])
        section("Сезонные", [({"id": "season:" + k}, n[0], "" if net_frames._season_on(k) else "Доступна: " + n[1])
                             for k, n in net_frames.SEASON_FRAMES.items()])
        cur_spec = {"id": cur}
        tile = next((t for t in self._tiles if t.spec.get("id") == cur), None)
        self._pick(cur_spec, tile, apply_btn=False)
        return c

    def _pick(self, spec, tile, apply_btn=True):
        import net_frames
        for t in self._tiles:
            t.selected = t is tile
            t.update()
        self._spec = dict(spec)
        self.pick_name.setText(tile.name if tile is not None else "—")
        lock = tile.locked if tile is not None else ""
        cur = self._is_current(spec)
        self.pick_hint.setText(lock or ("Сейчас на вас" if cur else "Нажмите «Надеть»"))
        self.pick_btn.setText("Надето" if cur else "Недоступно" if lock else "Надеть")
        self.pick_btn.setEnabled(not lock and not cur)
        eff = {} if spec.get("id") in ("none", "") else dict(spec)
        net_frames.animate_label(self.big, self._av, eff, ph.px(120))

    def _is_current(self, spec) -> bool:
        cur = ((self.win.settings.get("ya_profile_deco") or {}).get("frame") or {}).get("id", "none")
        return (spec.get("id") or "none") == cur

    def _apply(self):
        d = dict(self.win.settings.get("ya_profile_deco") or {})
        d["frame"] = {"id": self._spec.get("id") or "none"}
        self.win.settings["ya_profile_deco"] = d
        try:
            self.win.save_settings()
        except Exception:                                      # noqa: BLE001
            pass
        page = _net(self.win)
        try:
            page._deco_changed()
        except Exception:                                      # noqa: BLE001
            pass
        self.pick_hint.setText("Сейчас на вас")
        self.pick_btn.setText("Надето")
        self.pick_btn.setEnabled(False)

    # ── ник и профиль ── #
    def _style_card(self):
        c, v = _card()
        v.addWidget(pw.kicker("Profile"))
        v.addWidget(_title("Стиль ника и оформление профиля"))
        v.addWidget(_sub("Шрифт и эффект ника, мини-профиль, фон шапки и витрина — всё бесплатно."))
        row = QHBoxLayout()
        page = _net(self.win)
        for text, icon, fn in (("Стиль ника", "pencil", "edit_nick"), ("Мини-профиль", "user-round", "edit_mini"),
                               ("Витрина и фон шапки", "image", "edit_showcase")):
            b = pw.text_button(text, "secondary", icon=icon)
            b.clicked.connect(lambda _=False, f=fn: getattr(page, f, lambda: None)())
            b.setEnabled(page is not None and getattr(page, "node", None) is not None)
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        if page is None or getattr(page, "node", None) is None:
            v.addWidget(_sub("Чтобы менять стиль ника и профиль, включите Echoes.NET."))
        return c


class DonateLinksDialog(QDialog):
    """Админ: ссылки на донаты для всех (Boosty, DonationAlerts, ЮMoney…), до 8 штук, и подсказка донатерам."""
    PRESETS = ("Boosty", "DonationAlerts", "ЮMoney", "Ko-fi", "Patreon", "CloudTips")

    def __init__(self, links, note, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ссылки на донаты")
        self.setMinimumWidth(ph.px(560))
        v = QVBoxLayout(self)
        v.setSpacing(ph.px(8))
        v.addWidget(_title("Ссылки на донаты"))
        v.addWidget(_sub("Увидят все в магазине ECHOES. Вставьте ссылку на свою страницу (например, "
                         "https://boosty.to/…). Первая — главная кнопка."))
        self.rows = []
        for i in range(6):
            ln = links[i] if i < len(links) else {"name": "", "url": ""}
            h = QHBoxLayout()
            name = QComboBox()
            name.setEditable(True)
            name.addItems(("",) + self.PRESETS)
            name.setCurrentText(ln.get("name", ""))
            name.setFixedWidth(ph.px(170))
            url = QLineEdit(ln.get("url", ""))
            url.setPlaceholderText("https://…")
            h.addWidget(name)
            h.addWidget(url, 1)
            v.addLayout(h)
            self.rows.append((name, url))
        self.note_e = QLineEdit(note)
        self.note_e.setPlaceholderText("Подсказка донатерам (необязательно)")
        v.addWidget(self.note_e)
        bt = QHBoxLayout()
        bt.addStretch(1)
        cancel = pw.text_button("Отмена", "ghost")
        cancel.clicked.connect(self.reject)
        ok = pw.text_button("Сохранить для всех", "primary")
        ok.clicked.connect(self.accept)
        bt.addWidget(cancel)
        bt.addWidget(ok)
        v.addLayout(bt)

    def links(self):
        return [{"name": n.currentText().strip(), "url": u.text().strip()} for n, u in self.rows if u.text().strip()]

    def note(self):
        return self.note_e.text().strip()


# ══════════════════════════════════════════════════════════════════════════ #
#  Стена «Наши спонсоры» (вкладка Echoes.NET)
# ══════════════════════════════════════════════════════════════════════════ #

class SponsorCard(QWidget):
    """Пост спонсора: фото квадратом, имя со значком, подпись, трек (щелчок — включить)."""

    def __init__(self, page, post, state="approved", staff=False, parent=None):
        super().__init__(parent)
        import net_sponsor
        self.page, self.post = page, post
        self.setFixedWidth(ph.px(260))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(ph.px(8))
        self.photo = QLabel()
        s = ph.px(260)
        self.photo.setFixedSize(s, s)
        img = QImage()
        img.loadFromData(net_sponsor.photo_bytes(post))
        pm = ph.rounded_pixmap(img, QSize(s, s), ph.px(18)) if not img.isNull() else \
            ph.placeholder_cover(s, post.get("name") or "", "", ph.px(18))
        self.photo.setPixmap(pm)
        v.addWidget(self.photo)
        nm = QHBoxLayout()
        nm.setSpacing(ph.px(6))
        nm.addWidget(pw.label(post.get("name") or "Спонсор", "PhTitle", font=ph.font(ph.TEXT_BASE + 1, 650)))
        nd = page.node
        tier = net_sponsor.TIERS.get(net_sponsor.tier(nd, post.get("by")), "Спонсор") if nd is not None else ""
        if tier:
            b = pw.chip(tier, checked=True)
            b.setIcon(ph.icon("heart", 11, ph.TEXT_PRIMARY))
            b.setEnabled(False)
            nm.addWidget(b)
        nm.addStretch(1)
        v.addLayout(nm)
        if post.get("text"):
            t = _sub(post["text"])
            t.setTextFormat(Qt.TextFormat.PlainText)
            v.addWidget(t)
        tr = post.get("track")
        if tr and (tr.get("title") or tr.get("artist")):
            b = pw.text_button(f"{tr.get('artist', '')} — {tr.get('title', '')}".strip(" —"), "small", icon="play")
            b.setToolTip("Включить трек")
            b.clicked.connect(lambda: page.play_meta(tr))
            v.addWidget(b, 0, Qt.AlignmentFlag.AlignLeft)
        if state != "approved":
            v.addWidget(_sub({"pending": "На проверке у модерации", "rejected": "Отклонён модерацией"}[state]))
        if staff:
            row = QHBoxLayout()
            ok = pw.text_button("Одобрить", "primary", icon="check")
            no = pw.text_button("Отклонить", "secondary", icon="x")
            ok.clicked.connect(lambda: page.node.call(net_sponsor.review, page.node, post, True))
            no.clicked.connect(lambda: page.node.call(net_sponsor.review, page.node, post, False))
            row.addWidget(ok)
            row.addWidget(no)
            row.addStretch(1)
            v.addLayout(row)
        v.addStretch(1)


class SponsorsWall(QWidget):
    """Вкладка «Спонсоры»: стена одобренных постов, свой пост, инструменты модерации."""

    def __init__(self, page, parent=None):
        super().__init__(parent)
        self.page = page
        self.setObjectName("YaPage")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.body = QWidget()
        self.v = QVBoxLayout(self.body)
        self.v.setContentsMargins(0, ph.px(6), ph.px(10), ph.px(24))
        self.v.setSpacing(ph.px(14))
        outer.addWidget(_wrap(self.body))

    def fill(self):
        import net_sponsor
        while self.v.count():
            it = self.v.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
            elif it.layout() is not None:
                _clear(it.layout())
        nd = self.page.node
        head = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(ph.px(4))
        col.addWidget(pw.kicker("Sponsors"))
        col.addWidget(_title("Наши спонсоры", ph.TEXT_2XL))
        col.addWidget(_sub("Люди, благодаря которым ECHOES развивается и остаётся бесплатным для всех."))
        head.addLayout(col, 1)
        sup = pw.text_button("Поддержать ECHOES", "primary", icon="heart")
        sup.clicked.connect(self._open_shop)
        head.addWidget(sup, 0, Qt.AlignmentFlag.AlignTop)
        hw = QWidget()
        hw.setLayout(head)
        self.v.addWidget(hw)
        if nd is None:
            import ph_kit
            self.v.addWidget(ph_kit.Empty("heart", "Echoes.NET выключен", "Включите сеть, чтобы увидеть стену "
                                          "спонсоров.", "Включить сеть", getattr(self.page, "toggle_power", None)))
            self.v.addStretch(1)
            return
        if net_sponsor.is_sponsor(nd):
            self.v.addWidget(self._my_post(nd))
        if nd.my_role() in ("admin", "mod"):
            self.v.addWidget(self._staff(nd))
        posts = net_sponsor.wall(nd)
        if posts:
            fl = _Flow()
            for p_ in posts:
                c = SponsorCard(self.page, p_)
                c.adjustSize()
                fl.add(c)
            self.v.addWidget(fl)
        else:
            import ph_kit
            self.v.addWidget(ph_kit.Empty("heart", "Здесь появятся спонсоры",
                                          "Поддержите ECHOES — и ваш пост будет первым на этой стене."))
        self.v.addStretch(1)

    def _open_shop(self):
        lay = self.page.shell.__dict__.get("ph")
        if lay is not None:
            lay.open_shop()

    def _my_post(self, nd):
        import net_sponsor
        c, v = _card()
        mine = net_sponsor.my_post(nd)
        row = QHBoxLayout()
        col = QVBoxLayout()
        col.addWidget(_title("Ваш пост на стене", ph.TEXT_BASE + 1))
        if mine:
            st = net_sponsor.post_state(nd, mine)
            col.addWidget(_sub({"approved": "Опубликован — его видят все.",
                                "pending": "Ждёт проверки модерацией.",
                                "rejected": "Отклонён модерацией — можно отправить другой."}[st]))
        else:
            col.addWidget(_sub("Вы спонсор ECHOES — можно разместить один пост: фото, имя, подпись и трек."))
        row.addLayout(col, 1)
        b = pw.text_button("Изменить пост" if mine else "Создать пост", "primary" if not mine else "secondary",
                           icon="pencil")
        b.clicked.connect(self._edit)
        row.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        v.addLayout(row)
        return c

    def _edit(self):
        import net_sponsor
        nd = self.page.node
        if nd is None:
            return
        d = SponsorPostDialog(self.page, net_sponsor.my_post(nd), self)
        if d.exec():
            nd.call(net_sponsor.submit_post, nd, d.name(), d.text(), d.photo, d.track)
            QTimer.singleShot(700, self.fill)

    def _staff(self, nd):
        import net_sponsor
        c, v = _card()
        v.addWidget(pw.kicker("Moderation"))
        q = net_sponsor.queue(nd)
        v.addWidget(_title(f"Проверка постов · {len(q)}" if q else "Проверка постов", ph.TEXT_BASE + 1))
        if q:
            fl = _Flow()
            for p_ in q:
                fl.add(SponsorCard(self.page, p_, "pending", staff=True))
            v.addWidget(fl)
        else:
            v.addWidget(_sub("Новых постов нет."))
        v.addWidget(pw.PhHairline())
        v.addWidget(_title("Выдать статус спонсора", ph.TEXT_BASE))
        v.addWidget(_sub("Код человека из комментария к донату (его «Мой код» в Echoes.NET)."))
        row = QHBoxLayout()
        code = QLineEdit()
        code.setPlaceholderText("echoes:… или адрес")
        tier = QComboBox()
        for k, n in net_sponsor.TIERS.items():
            tier.addItem(n, k)
        give = pw.text_button("Выдать", "primary", icon="heart")
        give.clicked.connect(lambda: (nd.call(net_sponsor.grant, nd, code.text(), True, tier.currentData()),
                                      code.clear(), QTimer.singleShot(700, self.fill)))
        row.addWidget(code, 1)
        row.addWidget(tier)
        row.addWidget(give)
        v.addLayout(row)
        sps = net_sponsor.sponsors(nd)
        if sps:
            v.addWidget(_sub(f"Спонсоров: {len(sps)}"))
            for d in sorted(sps, key=lambda x: -x["ts"])[:30]:
                r = QHBoxLayout()
                nm = self.page._name(d["target"]) if hasattr(self.page, "_name") else d["target"][:10]
                r.addWidget(pw.label(f"{nm} · {net_sponsor.TIERS.get(d.get('tier'), 'Спонсор')}", "PhBody"))
                r.addStretch(1)
                rm = pw.text_button("Снять", "ghost")
                rm.clicked.connect(lambda _=False, t=d["target"]: (nd.call(net_sponsor.grant, nd, t, False),
                                                                    QTimer.singleShot(700, self.fill)))
                r.addWidget(rm)
                v.addLayout(r)
        return c


def _clear(lay):
    while lay.count():
        it = lay.takeAt(0)
        if it.widget() is not None:
            it.widget().deleteLater()
        elif it.layout() is not None:
            _clear(it.layout())


class SponsorPostDialog(QDialog):
    """Свой пост на стене спонсоров: фото, имя, подпись (до 280 знаков) и трек."""

    def __init__(self, page, post, parent=None):
        super().__init__(parent)
        import net_sponsor
        self.page = page
        self.setWindowTitle("Пост на стене спонсоров")
        self.setMinimumWidth(ph.px(560))
        post = post or {}
        self.photo = post.get("photo") or ""
        self.track = post.get("track")
        v = QVBoxLayout(self)
        v.setSpacing(ph.px(10))
        v.addWidget(_title("Пост на стене спонсоров"))
        v.addWidget(_sub("Один пост на человека: новый заменит прежний. Его увидят все после проверки модерацией."))
        row = QHBoxLayout()
        self.pic = QLabel()
        self.pic.setFixedSize(ph.px(150), ph.px(150))
        row.addWidget(self.pic)
        col = QVBoxLayout()
        b = pw.text_button("Выбрать фото…", "secondary", icon="image")
        b.clicked.connect(self._pick_photo)
        col.addWidget(b, 0, Qt.AlignmentFlag.AlignLeft)
        self.name_e = QLineEdit(post.get("name") or (page.node._name() if page.node else ""))
        self.name_e.setMaxLength(net_sponsor.NAME_LIMIT)
        self.name_e.setPlaceholderText("Имя")
        col.addWidget(self.name_e)
        self.tr_lbl = _sub("")
        trow = QHBoxLayout()
        tb = pw.text_button("Играющий трек", "small", icon="play")
        tb.clicked.connect(self._take_track)
        tc = pw.text_button("Без трека", "small")
        tc.clicked.connect(lambda: self._set_track(None))
        trow.addWidget(tb)
        trow.addWidget(tc)
        trow.addStretch(1)
        col.addLayout(trow)
        col.addWidget(self.tr_lbl)
        col.addStretch(1)
        row.addLayout(col, 1)
        v.addLayout(row)
        self.text_e = QPlainTextEdit(post.get("text") or "")
        self.text_e.setPlaceholderText("Подпись — пара слов о себе или об ECHOES")
        self.text_e.setFixedHeight(ph.px(90))
        v.addWidget(self.text_e)
        self.count = _sub("")
        self.text_e.textChanged.connect(self._count)
        v.addWidget(self.count)
        bt = QHBoxLayout()
        bt.addStretch(1)
        cancel = pw.text_button("Отмена", "ghost")
        cancel.clicked.connect(self.reject)
        self.ok = pw.text_button("Отправить на проверку", "primary")
        self.ok.clicked.connect(self.accept)
        bt.addWidget(cancel)
        bt.addWidget(self.ok)
        v.addLayout(bt)
        self._show_photo()
        self._set_track(self.track)
        self._count()

    def _count(self):
        import net_sponsor
        n = len(self.text_e.toPlainText())
        self.count.setText(f"{n} / {net_sponsor.TEXT_LIMIT}")
        self.ok.setEnabled(n <= net_sponsor.TEXT_LIMIT and bool(self.name_e.text().strip()))

    def _pick_photo(self):
        import net_sponsor
        f, _ = QFileDialog.getOpenFileName(self, "Фото для поста", "", "Изображения (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not f:
            return
        b = net_sponsor.photo_from_file(f)
        if b:
            self.photo = b
            self._show_photo()

    def _show_photo(self):
        import base64
        s = ph.px(150)
        img = QImage()
        if self.photo:
            img.loadFromData(base64.b64decode(self.photo))
        self.pic.setPixmap(ph.rounded_pixmap(img, QSize(s, s), ph.px(16)) if not img.isNull()
                           else ph.placeholder_cover(s, self.name_e.text() if hasattr(self, "name_e") else "", "",
                                                     ph.px(16)))

    def _take_track(self):
        sh = self.page.shell
        t = sh.current_track() if hasattr(sh, "current_track") else None
        if t:
            self._set_track({"artist": t.get("artist", ""), "title": t.get("title", ""), "album": t.get("album", ""),
                             "duration": t.get("duration", 0)})

    def _set_track(self, t):
        self.track = t
        self.tr_lbl.setText(f"Трек: {t.get('artist', '')} — {t.get('title', '')}" if t else "Без трека")

    def name(self):
        return self.name_e.text().strip()

    def text(self):
        return self.text_e.toPlainText().strip()
