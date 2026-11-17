# lyrics_view.py
"""
LyricsView — режим текста.

Подход: LyricsView живёт как overlay поверх centralWidget окна.
При входе он растягивается на весь экран и рисует layout:
  [  vinyl (реальный виджет, reparented сюда)  |  divider  |  текст  ]

Vinyl перемещается через анимацию geometry прямо внутри нас — никакого
setParent(root), никаких глобальных координат.
"""

import re
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QSizePolicy, QGraphicsOpacityEffect, QPushButton
)
from frameclock import FrameTimer, animation_delta
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QRect, QPoint,
    QTimer, QParallelAnimationGroup, QVariantAnimation
)
from PyQt6.QtGui import QColor, QPainter, QLinearGradient, QBrush, QPixmap, QFont, QFontMetrics, QFontMetricsF, QPen
from PyQt6.QtCore import QRectF, QPointF
import math
import time


# ────────────────────────────────────────────────────────────────────────────
#  LRC-парсер
# ────────────────────────────────────────────────────────────────────────────

_LRC_LINE = re.compile(r'^\[(\d{1,3}):(\d{2})(?:[\.:](\d{1,3}))?\](.*)')
_LRC_TAG  = re.compile(r'^\[(?:ti|ar|al|by|offset|length|re|ve):', re.IGNORECASE)
_WORD_TS  = re.compile(r'<(\d{1,3}):(\d{2})\.(\d{2,3})>')


def _ms(m, s, f):
    ms = int((f or '0').ljust(3,'0')[:3])
    return int(m)*60_000 + int(s)*1000 + ms


def parse_lrc(text):
    lines, has = [], False
    offset_match = re.search(r'\[offset:([+-]?\d+)\]', text, re.IGNORECASE)
    offset = int(offset_match.group(1)) if offset_match else 0
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw or _LRC_TAG.match(raw):
            continue
        m = _LRC_LINE.match(raw)
        if m:
            t = _ms(m.group(1), m.group(2), m.group(3))
            body = m.group(4).strip()
            timestamps = [t]
            while (extra := _LRC_LINE.match(body)) is not None:
                timestamps.append(_ms(extra.group(1), extra.group(2), extra.group(3)))
                body = extra.group(4).strip()
            has = True
            words = None
            if _WORD_TS.search(body):
                words, parts, cur = [], _WORD_TS.split(body), t
                i = 0
                while i < len(parts):
                    wt = parts[i].strip()
                    if i+3 < len(parts):
                        wt and words.append((cur, wt))
                        cur = _ms(parts[i+1], parts[i+2], parts[i+3])
                        i += 4
                    else:
                        wt and words.append((cur, wt))
                        i += 1
                body = ' '.join(w for _, w in words)
            for timestamp in timestamps:
                shifted_words = ([(max(0, wt + timestamp - t + offset), word) for wt, word in words]
                                 if words is not None else None)
                lines.append({'ms': max(0, timestamp + offset), 'text': body, 'words': shifted_words})
        else:
            lines.append({'ms': -1, 'text': raw, 'words': None})
    lines.sort(key=lambda l: l['ms'] if l['ms'] >= 0 else 0)
    return lines, has


def split_plain(text):
    out, prev = [], False
    for line in text.splitlines():
        s = line.strip()
        if not s:
            if not prev:
                out.append({'ms': -1, 'text': '', 'words': None})
            prev = True
        else:
            out.append({'ms': -1, 'text': s, 'words': None})
            prev = False
    return out


# ────────────────────────────────────────────────────────────────────────────
#  Одна строка текста
# ────────────────────────────────────────────────────────────────────────────

class LyricLine(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text or '\u200b', parent)
        self._active = False
        self._light = False
        self._timed = True
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._apply()

    def set_active(self, v: bool):
        if self._active == v:
            return
        self._active = v
        self._apply()

    def set_light(self, v: bool):
        if self._light == v:
            return
        self._light = v
        self._apply()

    def set_timed(self, v: bool):
        self._timed = v
        self._apply()

    def _apply(self):
        show_active = self._active or not self._timed
        active_col = "#0a0a0a" if self._light else "#ffffff"
        muted_col  = "rgba(0,0,0,0.30)" if self._light else "rgba(255,255,255,0.22)"
        if show_active:
            size = "28px" if self._timed else "18px"
            self.setStyleSheet(
                f"font-size:{size};font-weight:700;color:{active_col};"
                "letter-spacing:-0.4px;padding:4px 0;"
            )
        else:
            self.setStyleSheet(
                f"font-size:19px;font-weight:600;color:{muted_col};"
                "letter-spacing:-0.2px;padding:3px 0;"
            )


# ────────────────────────────────────────────────────────────────────────────
#  Вертикальный разделитель
# ────────────────────────────────────────────────────────────────────────────

class _FadeGhost(QWidget):
    """«Снимок» виджета, который плавно гаснет/проявляется вместо самого
    виджета. QGraphicsOpacityEffect каждый кадр перерисовывает виджет во
    внеэкранный буфер (для списков/панелей это дорого) — а снимок делается
    один раз, и анимация лишь блитит готовую картинку с прозрачностью."""

    def __init__(self, pm: QPixmap, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._pm = pm
        self.op = 0.0

    def set_op(self, v):
        self.op = float(v)
        self.update()

    def paintEvent(self, _):
        if self.op <= 0.003:
            return
        p = QPainter(self)
        p.setOpacity(min(1.0, self.op))
        p.drawPixmap(0, 0, self._pm)
        p.end()


class Divider(QWidget):
    def __init__(self, accent=QColor('#a78bfa'), parent=None):
        super().__init__(parent)
        self._accent = accent
        self.setFixedWidth(2)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

    def set_accent(self, c): self._accent = c; self.update()

    def paintEvent(self, _):
        p = QPainter(self); a = self._accent
        g = QLinearGradient(0, 0, 0, self.height())
        def col(alpha): return QColor(a.red(), a.green(), a.blue(), alpha)
        g.setColorAt(0.00, col(0))
        g.setColorAt(0.15, col(160))
        g.setColorAt(0.50, col(255))
        g.setColorAt(0.85, col(160))
        g.setColorAt(1.00, col(0))
        p.fillRect(self.rect(), QBrush(g))


# ────────────────────────────────────────────────────────────────────────────
#  Панель текста с прокруткой
# ────────────────────────────────────────────────────────────────────────────

class LyricsScrollPanel(QWidget):
    """Текст в стиле Яндекс Музыки: строки по центру крупным жирным шрифтом,
    текущая — ярко-белая, следующие — приглушённые и тают книзу, прошедшие —
    ещё тусклее сверху. Плавная прокрутка, клик по строке — перемотка к ней,
    колесо — ручной просмотр (через 3 с снова следит за песней). В проигрышах
    (вступление, длинные паузы между строками) — «точки ожидания», которые
    заполняются к началу следующей строки.

    Всё рисуется вручную (без QLabel на строку) — дёшево и плавно."""

    FAMILIES = ["YS Text", "Inter", "Segoe UI Variable Display", "Segoe UI", "Helvetica Neue", "Arial"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LyricsScroll")
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

        self._time_lbl = QLabel("0:00 / 0:00", self)
        self._time_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._light = False
        self._apply_time_style()

        self._texts: list[str] = []
        self._ms: list[int] = []
        self._timed = True
        self._active_idx = -1
        self._fade_rgb = None
        self._layout = []           # [(y_top, h)] при текущей ширине
        self._layout_w = -1
        self._font = QFont()
        self._alpha: list[float] = []
        self._scroll = 0.0          # смещение содержимого (px)
        self._target = 0.0
        self._manual_until = 0.0
        self._hover = -1
        self._pos = (0, 0.0)        # (ms, monotonic) — последняя позиция от плеера
        self._dots = None           # (y_center, progress) или None
        self._dots_a = 0.0
        self.seek_cb = None
        self._st = {}               # стиль из темы конструктора (theme_kit.LYRICS_TEXT); {} — как было
        self._st_family = ""        # семейство шрифта стиля (зарегистрированное из файла темы)
        self._last_t = time.monotonic()
        self._timer = FrameTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._backdrop = None       # fn() → (QPixmap, QPoint): подложка под панелью (панель непрозрачна)
        self.liquid = False         # «жидкий» текст: строка заливается белым по буквам, буквы подрастают
        self._words: list = []      # тайминги слов (LRC <mm:ss.xx>), если есть
        self._lq_cache = {}         # раскладка текущей строки по буквам

    def set_backdrop(self, fn):
        """Панель лежит на непрозрачном фоне (страница «Текст» Echoes Music): fn отдаёт картинку фона
        и смещение панели в ней. Тогда панель рисует свой кусок фона сама и помечается непрозрачной —
        её кадры не перерисовывают всё окно под ней."""
        self._backdrop = fn
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, fn is not None)
        self.update()

    # ── стиль из темы ── #

    def set_style(self, st: dict | None, family: str = ""):
        """Шрифт, размеры, цвета, выравнивание и т.д. (None — стандартный вид)."""
        st = dict(st or {})
        if st == self._st and family == self._st_family:
            return
        keep_manual = bool(st.get('manual_scroll') and self._manual_until
                           and time.monotonic() < self._manual_until)
        previous_height = max(1, getattr(self, '_content_h', 1))
        previous_scroll, previous_target = self._scroll, self._target
        self._st, self._st_family = st, family
        self._manual_until = float("inf") if st.get("manual_scroll") else 0.0
        self._time_lbl.setVisible(bool(st.get("time", True)))
        self._apply_time_style()
        self._layout_w = -1
        self._relayout()
        if keep_manual:
            ratio = self._content_h / previous_height
            self._scroll, self._target = previous_scroll * ratio, previous_target * ratio
        else:
            self._target = self._target_scroll()
            self._scroll = self._target
        self.update()

    def _align(self):
        a = self._st.get("align", "center")
        return {"left": Qt.AlignmentFlag.AlignLeft, "right": Qt.AlignmentFlag.AlignRight}.get(
            a, Qt.AlignmentFlag.AlignHCenter)

    def _col(self, key, fallback: QColor) -> QColor:
        c = self._st.get(key) or ""
        return QColor(c) if c else QColor(fallback)

    # ── совместимость со старым API ── #

    def set_fade_rgb(self, r: int, g: int, b: int):
        self._fade_rgb = (int(r), int(g), int(b))
        self.update()

    def reset_fade(self):
        self._fade_rgb = None
        self.update()

    def _apply_time_style(self):
        col = "rgba(0,0,0,0.35)" if self._light else "rgba(255,255,255,0.35)"
        c = (getattr(self, "_st", None) or {}).get("color")
        if c:
            q = QColor(c)
            col = f"rgba({q.red()},{q.green()},{q.blue()},0.45)"
        self._time_lbl.setStyleSheet(f"color:{col};font-size:11px;font-weight:500;"
                                     "background:transparent;padding:0;")

    def set_light(self, v: bool):
        self._light = bool(v)
        self._apply_time_style()
        self.update()

    def set_time(self, cur_ms: int, total_ms: int):
        def fmt(ms):
            s = max(0, ms) // 1000
            return f"{s // 60}:{s % 60:02d}"
        self._time_lbl.setText(f"{fmt(cur_ms)} / {fmt(total_ms)}")
        self._time_lbl.adjustSize()
        self._reposition_time_lbl()

    def _reposition_time_lbl(self):
        self._time_lbl.move(self.width() - self._time_lbl.width() - 30, 16)

    def set_timed(self, v: bool):
        self._timed = bool(v)
        self._kick()

    def load(self, lines, timed: bool = True):
        self._texts = [(ln.get('text') or '').strip() for ln in lines]
        self._ms = [int(ln.get('ms', -1)) for ln in lines]
        self._words = [ln.get('words') or None for ln in lines]
        self._est = [None] * len(lines)                        # тайминги слов: оценка → уточнение по звуку
        if timed and not all(self._words):
            try:
                import word_sync
                self._est = word_sync.estimate(lines)
            except Exception as e:                             # noqa: BLE001
                print("[words]", e)
        self._src_lines = lines
        self._lq_cache = {}
        self._timed = bool(timed)
        self._active_idx = -1
        self._layout_w = -1
        self._alpha = [self._base_alpha(i) for i in range(len(self._texts))]
        self._scroll = self._target = 0.0
        self._manual_until = float("inf") if self._st.get("manual_scroll") else 0.0
        self._dots = None
        self._dots_a = 0.0
        self._relayout()
        self._target = self._target_scroll()
        self._scroll = self._target
        self._kick()

    def set_active(self, idx: int):
        """Совместимость: активная строка теперь считается по позиции (set_pos_ms)."""
        if not self._ms or self._pos[0] <= 0:
            self._set_idx(idx)

    def set_pos_ms(self, ms: int):
        self._pos = (int(ms), time.monotonic())
        self._kick()

    # ── раскладка ── #

    def _font_px(self) -> int:
        size = int(self._st.get("size") or 0)
        if size > 0:
            return size if self._timed else max(8, int(size * 0.75))
        w = max(200, self.width())
        if self._st.get("phantom"):                  # Phantom: крупно, как его LYRICS (≈52 px при колонке 790)
            k = max(0.5, min(2.0, float(self._st.get("size_scale", 1.0))))
            return int(max(26, min(60, w * 0.066)) * k) if self._timed else int(max(18, min(34, w * 0.04)) * k)
        return int(max(20, min(36, w * 0.042))) if self._timed else int(max(17, min(26, w * 0.032)))

    def _shown(self, t: str) -> str:
        return t.upper() if self._st.get("upper") else t

    def _relayout(self):
        w = self.width()
        px = self._font_px()
        f = QFont()
        f.setFamilies(([self._st_family] if self._st_family else []) + self.FAMILIES)
        f.setPixelSize(px)
        self._ph_cache = {}
        if self._st.get("phantom"):                  # Phantom: Inter 700, плотная разрядка −.035em
            import ph_style
            f.setFamilies(ph_style.FAMILIES)
            f.setWeight(QFont.Weight(int(self._st.get("weight", 700))))
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, -0.035 * px)
        elif self._st:
            f.setWeight(QFont.Weight(int(self._st.get("weight", 700))))
            f.setItalic(bool(self._st.get("italic")))
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, float(self._st.get("letter", 0.0)))
        else:
            f.setWeight(QFont.Weight.Bold if self._timed else QFont.Weight.DemiBold)
            f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 98)
        self._font = f
        fm = QFontMetrics(f)
        inner = max(100, w - 2 * self._margin())
        # текущая строка может быть крупнее — место под неё
        grow = max(1.0, self._grow()) if self._timed else 1.0
        gap = int(px * (1.05 if self._timed else 0.75) * float(self._st.get("line_gap", 1.0)))
        y = 0
        lay = []
        for t in self._texts:
            if not t:
                h = int(px * 0.6)                    # пустая строка — небольшой отступ
            else:
                h = self._text_height(self._shown(t), int(inner / grow), fm)
            lay.append((y, h))
            y += h + gap
        self._layout = lay
        self._layout_w = w
        self._content_h = y

    def _text_height(self, text, width, metrics):
        flags = self._align().value | Qt.TextFlag.TextWordWrap.value
        if getattr(self, '_translation_below', False) and '\n' in text:
            original, translated = text.split('\n', 1)
            scale = max(0.4, min(1.5, float(self._st.get('translation_scale', 0.75))))
            primary = metrics.boundingRect(QRect(0, 0, width, 10000), flags, original).height()
            secondary = metrics.boundingRect(QRect(0, 0, max(1, int(width / scale)), 10000), flags, translated).height()
            return primary + 6 + math.ceil(secondary * scale)
        return metrics.boundingRect(QRect(0, 0, width, 10000), flags, text).height()

    def _grow(self) -> float:
        """Насколько текущая строка крупнее остальных («жидкий» текст — заметно крупнее, как в Apple Music)."""
        return float(self._st.get("active_scale", 1.24 if self.liquid else 1.0))

    def _margin(self) -> int:
        if self._st.get("phantom"):                  # Phantom: текст от края колонки
            return 4
        if self._st.get("panel"):
            return max(20, int(self.width() * 0.06))
        return max(24, int(self.width() * 0.07))

    def _anchor(self) -> float:
        return self.height() * float(self._st.get("anchor", 0.40))

    def _target_scroll(self) -> float:
        if not self._layout:
            return 0.0
        if not self._timed:
            return self._scroll if self._manual_until else -self.height() * 0.12
        if self._dots is not None:
            return self._dots[0] - self._anchor()
        i = self._active_idx
        if i < 0:
            first = next((k for k, m in enumerate(self._ms) if m >= 0), 0)
            y, h = self._layout[first]
            return y + h / 2 - self._anchor() + self._font_px() * 2.2
        y, h = self._layout[i]
        return y + h / 2 - self._anchor()

    # ── позиция / активная строка / точки ── #

    def _now_ms(self) -> int:
        ms, t0 = self._pos
        dt = time.monotonic() - t0
        return int(ms + min(dt, 0.45) * 1000)        # дольше 0.45 с без новостей — пауза

    def _set_idx(self, idx):
        if idx != self._active_idx:
            self._active_idx = idx
            if time.monotonic() > self._manual_until:
                self._target = self._target_scroll()
            self._kick()

    def _line_end(self, i) -> int:
        """Оценка, когда строка допета: по числу слогов, но не дальше следующей."""
        t = self._texts[i]
        syl = max(1, len(re.findall(r"[aeiouyаеёиоуыэюя]+", t, re.I)))
        est = self._ms[i] + 650 + syl * 230
        nxt = next((m for m in self._ms[i + 1:] if m >= 0), None)
        return min(est, nxt - 300) if nxt is not None else est

    def _update_state(self):
        if not self._timed or not self._ms:
            self._dots = None
            return
        now = self._now_ms()
        idx = -1
        for i, m in enumerate(self._ms):
            if 0 <= m <= now:
                idx = i
            elif m > now:
                break
        # пустые строки LRC — это и есть проигрыш: активной остаётся предыдущая
        while idx >= 0 and not self._texts[idx]:
            idx -= 1
            if idx < 0 or self._ms[idx] >= 0:
                break
        dots = None
        nxt_i = next((k for k in range(idx + 1, len(self._ms)) if self._ms[k] >= 0 and self._texts[k]), None)
        if nxt_i is not None:
            nxt = self._ms[nxt_i]
            if idx < 0:
                start = 0
            else:
                start = self._line_end(idx)
            if nxt - start >= 3500 and now >= start:
                prog = (now - start) / max(1, nxt - start)
                ny, nh = self._layout[nxt_i]
                if idx >= 0:
                    py, ph = self._layout[idx]
                    yc = (py + ph + ny) / 2
                else:
                    yc = ny - self._font_px() * 1.2
                dots = (yc, max(0.0, min(1.0, prog)), nxt_i)
        changed = (dots is None) != (self._dots is None)
        self._dots = dots
        if changed and time.monotonic() > self._manual_until:
            self._target = self._target_scroll()
        self._set_idx(idx)

    # ── анимация ── #

    def _base_alpha(self, i) -> float:
        if not self._timed:
            return 0.86
        a = self._active_idx
        if self._dots is not None and i == self._dots[2]:
            return 0.42                              # следующая строка после проигрыша
        if i == a:
            return 0.45 if self._dots is not None else 1.0   # проигрыш — строка допета
        if a < 0:
            d = i - next((k for k, m in enumerate(self._ms) if m >= 0), 0)
            return max(0.10, 0.40 - 0.07 * max(0, d))
        if i < a:
            return max(0.08, 0.26 - 0.05 * (a - i - 1))
        return max(0.10, 0.40 - 0.07 * (i - a - 1))

    def _kick(self):
        if not self._timer.isActive() and self.isVisible():
            self._last_t = time.monotonic()
            self._timer.start()

    def showEvent(self, e):
        super().showEvent(e)
        self._kick()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()

    def _tick(self):
        now = time.monotonic()
        dt = animation_delta(now - self._last_t, .05)
        self._last_t = now
        if self._layout_w != self.width():
            self._relayout()
            self._target = self._target_scroll()
        self._update_state()
        if now > self._manual_until and self._manual_until:
            self._manual_until = 0.0
            self._target = self._target_scroll()
        busy = False
        k = 1 - math.exp(-dt * max(1, min(20, float(self._st.get("scroll_speed", 7)))))
        if abs(self._target - self._scroll) > 0.3:
            self._scroll += (self._target - self._scroll) * k
            busy = True
        else:
            self._scroll = self._target
        ka = 1 - math.exp(-dt * 9.0)
        for i in range(len(self._alpha)):
            tgt = self._base_alpha(i)
            if i == self._hover and self._timed and i != self._active_idx:
                tgt = min(1.0, tgt + 0.25)
            d = tgt - self._alpha[i]
            if abs(d) > 0.004:
                self._alpha[i] += d * ka
                busy = True
        want = 1.0 if self._dots is not None else 0.0
        if abs(want - self._dots_a) > 0.01:
            self._dots_a += (want - self._dots_a) * ka
            busy = True
        # перерисовка — только когда что-то движется (раньше — каждый кадр, пока играет музыка, хотя
        # строки меняются раз в несколько секунд; панель на весь экран стоила десятки % процессора)
        if busy or ((self._st.get("karaoke") or self.liquid) and self._active_idx >= 0):
            self.update()
        elif self._st.get("phantom") and self._st.get("words", True) and 0 <= self._active_idx < len(self._layout) \
                and self._timed:
            # Phantom: слова текущей строки заливаются каждый кадр — перерисовать только её полосу
            y, h = self._layout[self._active_idx]
            top = int(y - self._scroll)
            self.update(QRect(0, top - 6, self.width(), h + 16))
        elif self._dots is not None:                 # дышат только точки — перерисовать их полосу
            px = self._font_px()
            yc = int(self._dots[0] - self._scroll)
            self.update(QRect(0, yc - int(px * 0.6) - 2, self.width(), int(px * 1.2) + 4))
            busy = True
        playing = (time.monotonic() - self._pos[1]) < 0.6
        if not busy and not playing:
            self._timer.stop()

    # ── ввод ── #

    def wheelEvent(self, e):
        if not self._layout:
            return
        self._target = max(-self.height() * 0.3,
                           min(self._content_h - self.height() * 0.3,
                               self._target - e.angleDelta().y() * 0.9))
        self._manual_until = (float("inf") if self._st.get("manual_scroll") else
                              time.monotonic() + (3.0 if self._timed else 1e9))
        self._kick()
        e.accept()

    def _line_at(self, y) -> int:
        yy = y + self._scroll
        for i, (ly, lh) in enumerate(self._layout):
            if ly - 6 <= yy <= ly + lh + 6 and self._texts[i]:
                return i
        return -1

    def mouseMoveEvent(self, e):
        i = self._line_at(e.position().y()) if self._timed else -1
        if i != self._hover:
            self._hover = i
            self.setCursor(Qt.CursorShape.PointingHandCursor if i >= 0 and self._ms[i] >= 0
                           else Qt.CursorShape.ArrowCursor)
            self._kick()

    def leaveEvent(self, e):
        self._hover = -1
        self._kick()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._timed and self.seek_cb:
            i = self._line_at(e.position().y())
            if i >= 0 and self._ms[i] >= 0:
                self._manual_until = float("inf") if self._st.get("manual_scroll") else 0.0
                self.seek_cb(self._ms[i])
                self._pos = (self._ms[i], time.monotonic())
                self._kick()
                e.accept()
                return
        super().mousePressEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._reposition_time_lbl()
        self._relayout()
        self._target = self._target_scroll()
        self._scroll = self._target

    # ── рисование ── #

    def paintEvent(self, _):
        W, H = self.width(), self.height()
        bg, off = None, None
        if self._backdrop is not None:
            try:
                bg, off = self._backdrop()
            except Exception:                        # noqa: BLE001
                bg = None
        if self._layout_w != W:
            self._relayout()
        # Пока строки стоят на месте, фон и все неактивные строки — одна готовая картинка (слой), в кадре
        # рисуется только текущая строка и точки. Слой собирается, когда два кадра подряд одинаковы
        # (во время прокрутки к новой строке — рисуем всё напрямую, как раньше).
        key = self._layer_key(bg, off)
        if key is not None and key == self.__dict__.get("_layer_k") and self.__dict__.get("_layer") is not None:
            p = QPainter(self)
            p.drawPixmap(0, 0, self._layer)
            self._paint_content(p, W, H, "active")
            p.end()
            self._prev_k = key
            return
        if key is not None and key == self.__dict__.get("_prev_k"):
            dpr = self.devicePixelRatioF()
            layer = QPixmap(max(1, int(W * dpr)), max(1, int(H * dpr)))
            layer.setDevicePixelRatio(dpr)
            lp = QPainter(layer)
            self._paint_backdrop(lp, W, H, bg, off)
            self._paint_content(lp, W, H, "base")
            lp.end()
            self._layer, self._layer_k = layer, key
            p = QPainter(self)
            p.drawPixmap(0, 0, layer)
            self._paint_content(p, W, H, "active")
            p.end()
            return
        self._layer = None
        self._prev_k = key
        p = QPainter(self)
        self._paint_backdrop(p, W, H, bg, off)
        self._paint_content(p, W, H, "all")
        p.end()

    def _layer_key(self, bg, off):
        """Всё, от чего зависит слой «фон + неактивные строки», или None (слой не нужен: нет непрозрачного
        фона, «точки» дышат, наведена строка, нет активной строки)."""
        if bg is None or bg.isNull() or not self._timed or self._active_idx < 0 or not self._texts:
            return None
        a = list(self._alpha)
        if 0 <= self._active_idx < len(a):
            a[self._active_idx] = None
        return (self.width(), self.height(), self.devicePixelRatioF(), bg.cacheKey(), off.x(), off.y(),
                self._scroll, self._active_idx, tuple(a), id(self._layout), id(self._st), self._light,
                self.liquid, self._font.key(), self._dots is not None)

    def _paint_backdrop(self, p, W, H, bg, off):
        if self._backdrop is not None:
            if bg is not None and not bg.isNull():
                p.drawPixmap(0, 0, bg, off.x(), off.y(), W, H)
            else:
                p.fillRect(QRect(0, 0, W, H), QColor(30, 30, 32))

    def _paint_content(self, p, W, H, part):
        """part: "all" — всё по порядку; "base" — всё, кроме текущей строки и точек; "active" — только они."""
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        st = self._st
        base = QColor(10, 10, 10) if self._light else QColor(255, 255, 255)
        act_col = self._col("color", base)
        dim_col = self._col("dim_color", act_col)
        dim_k = float(st.get("dim", 1.0))
        if part != "active" and st.get("panel") and not st.get('liquid_glass', False):  # Glass: one full-page surface.
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(st["panel"]))
            r = float(st.get("panel_radius", 18))
            p.drawRoundedRect(QRectF(0, 0, W, H), r, r)
        m = self._margin()
        inner = W - 2 * m
        align = self._align()
        iw = int(inner / max(1.0, self._grow()) if self._timed else inner)
        if iw < inner:                               # строки уже панели: крупная текущая не вылезет за край
            m = {Qt.AlignmentFlag.AlignLeft: m, Qt.AlignmentFlag.AlignRight: W - m - iw}.get(
                align, m + (inner - iw) // 2)
            inner = iw
        p.setFont(self._font)
        flags = (align.value | Qt.AlignmentFlag.AlignTop.value | Qt.TextFlag.TextWordWrap.value)
        off = self._scroll
        fade = float(st.get("fade", 0.22))
        grow = self._grow() if (st or self.liquid) else 1.0
        glow = float(st.get("glow", 0.0))
        shadow = float(st.get("shadow", 0.0))
        for i, (y, h) in enumerate(self._layout):
            top = y - off
            if top > H or top + h < 0 or not self._texts[i]:
                continue
            a = self._alpha[i] if i < len(self._alpha) else 0.5
            active = i == self._active_idx and self._timed
            if (part == "base" and active) or (part == "active" and not active):
                continue
            if not active:
                a *= dim_k
            # мягкое затухание к краям панели
            yc = top + h / 2
            if fade > 0.001:
                edge = min(yc, H - yc) / (H * fade)
                a *= max(0.0, min(1.0, edge))
            if a <= 0.01:
                continue
            c = QColor(act_col if active else dim_col)
            c.setAlphaF(min(1.0, a))
            text = self._shown(self._texts[i])
            if active:
                # текущая строка чуть крупнее — масштаб от точки выравнивания строки
                p.save()
                k = min(1.0, (a - 0.4) / 0.6) if a > 0.4 else 0.0
                sc = 1.0 if st.get("phantom") else 1.0 + (0.035 + (grow - 1.0)) * k   # Phantom — без роста
                ax = {Qt.AlignmentFlag.AlignLeft: m, Qt.AlignmentFlag.AlignRight: m + inner}.get(
                    align, m + inner / 2)
                p.translate(ax, top + h / 2)
                p.scale(sc, sc)
                p.translate(-ax, -(top + h / 2))
                rect = QRect(m, int(top), inner, h + 4)
                plain = not (getattr(self, '_translation_below', False) and '\n' in text)
                if st.get("phantom") and st.get("words", True) and self._ms[i] >= 0 and plain:
                    self._draw_words_ph(p, rect, text, c, dim_col, i, a)
                elif self.liquid and self._ms[i] >= 0 and plain:
                    self._draw_liquid(p, rect, text, c, dim_col, i, a)
                else:
                    self._draw_line(p, rect, flags, text, c, glow * k, shadow, i)
                p.restore()
            elif st.get("phantom") and st.get("blur_inactive", True) and self._timed and \
                    not (getattr(self, '_translation_below', False) and '\n' in text):
                # Phantom: неактивные строки размыты — тем сильнее, чем дальше от текущей. Размытая строка —
                # готовая картинка из кэша: в кадре только drawImage с прозрачностью
                d = abs(i - self._active_idx) if self._active_idx >= 0 else 3
                img, pad = self._ph_line(text, inner, h + 4, flags, c, min(7.0, 1.2 + 1.3 * d))
                p.save()
                p.setOpacity(c.alphaF())
                p.drawImage(QPointF(m - pad, top - pad), img)
                p.restore()
            else:
                self._draw_line(p, QRect(m, int(top), inner, h + 4), flags, text, c, 0.0, shadow, -1)

        # точки ожидания (проигрыш)
        if part != "base" and self._dots_a > 0.01 and self._dots is not None:
            base = act_col
            yc = self._dots[0] - off
            prog = self._dots[1]
            n = 4
            px = self._font_px()
            sizes = [px * s for s in (0.20, 0.25, 0.30, 0.36)]
            gap = px * 0.16
            total = sum(sizes) * 2 + gap * (n - 1)
            x = {Qt.AlignmentFlag.AlignLeft: m, Qt.AlignmentFlag.AlignRight: m + inner - total}.get(
                align, m + inner / 2 - total / 2)
            t = time.monotonic()
            p.setPen(Qt.PenStyle.NoPen)
            for k in range(n):
                r = sizes[k]
                lit = max(0.0, min(1.0, prog * n - k))   # заполняются по очереди
                breathe = 1.0 + 0.10 * math.sin(t * 3.2 + k * 0.7) * (1 - lit * 0.6)
                c = QColor(base)
                c.setAlphaF(self._dots_a * (0.22 + 0.78 * lit))
                p.setBrush(c)
                rr = r * breathe
                p.drawEllipse(QRectF(x + r - rr, yc - rr, rr * 2, rr * 2))
                x += r * 2 + gap

    # ── «жидкий» текст ── #

    def set_word_timings(self, lines, words):
        """Уточнённые по звуку тайминги слов (word_sync.refine) — для того же текста."""
        if lines is not getattr(self, "_src_lines", None):
            return
        self._est = words
        self._lq_cache = {}
        self.update()

    def _liquid_span(self, i) -> tuple[int, int]:
        """Строка звучит от своей метки до следующей; длинный проигрыш после — не тянуть заливку бесконечно."""
        start = self._ms[i]
        nxt = next((m for m in self._ms[i + 1:] if m > start), None)
        est = self._line_end(i)
        end = (nxt - 120) if nxt is not None else est + 1500
        if end - start > 9000:                                  # дальше идёт проигрыш (там «точки»)
            end = max(est + 600, start + 1200)
        return start, max(start + 400, end)

    def _liquid_layout(self, i, text, width):
        """Буквы строки с переносами по словам: [(символ, x, y_базовой_линии, ширина, t0, t1)] и размеры."""
        key = (i, text, width, self._font.pixelSize(), self._font.family(), self._align())
        lay = self._lq_cache.get(key)
        if lay is not None:
            return lay
        fm = QFontMetricsF(self._font)
        words = text.split(" ")
        space = fm.horizontalAdvance(" ")
        rows, row, row_w = [], [], 0.0
        for w in words:
            ww = fm.horizontalAdvance(w)
            if row and row_w + space + ww > width:
                rows.append((row, row_w))
                row, row_w = [], 0.0
            row_w += (space if row else 0.0) + ww
            row.append(w)
        rows.append((row, row_w))
        line_h = fm.lineSpacing()
        align = self._align()
        chars = []
        wi = 0
        for r, (row, rw) in enumerate(rows):
            x0 = {Qt.AlignmentFlag.AlignLeft: 0.0, Qt.AlignmentFlag.AlignRight: width - rw}.get(align, (width - rw) / 2)
            base = r * line_h + fm.ascent()
            x = x0
            for k, w in enumerate(row):
                if k:
                    x += space
                for j, ch in enumerate(w):                      # позиции с учётом кернинга
                    cx = x + fm.horizontalAdvance(w[:j])
                    cw = fm.horizontalAdvance(w[:j + 1]) - fm.horizontalAdvance(w[:j])
                    chars.append([ch, cx, base, cw, wi, 0.0, 0.0])
                x += fm.horizontalAdvance(w)
                wi += 1
        # время каждой буквы: по таймингам слов (если есть), иначе равномерно по длительности строки
        start, end = self._liquid_span(i)
        wt = self._words[i] if i < len(self._words) else None
        if not wt:                                              # нет пословных меток — оценка/звук (word_sync)
            est = getattr(self, "_est", None)
            wt = est[i] if est and i < len(est) else None
        n_words = wi
        if wt and len(wt) == n_words:
            spans = []
            for k, ent in enumerate(wt):
                wms = ent[0]
                if len(ent) > 2:                                # известен и конец слова
                    spans.append((wms, max(wms + 60, ent[2])))
                    continue
                nx = wt[k + 1][0] if k + 1 < len(wt) else end
                spans.append((wms, max(wms + 80, nx)))
            for w_idx in range(n_words):
                cs = [c for c in chars if c[4] == w_idx]
                a, b = spans[w_idx]
                for j, c in enumerate(cs):
                    c[5] = a + (b - a) * j / len(cs)
                    c[6] = a + (b - a) * (j + 1) / len(cs)
        else:
            tot = sum(c[3] for c in chars) or 1.0
            acc = 0.0
            for c in chars:                                     # широкие буквы заливаются чуть дольше
                c[5] = start + (end - start) * acc / tot
                acc += c[3]
                c[6] = start + (end - start) * acc / tot
        lay = (chars, len(rows) * line_h, line_h)
        if len(self._lq_cache) > 40:
            self._lq_cache.clear()
        self._lq_cache[key] = lay
        return lay

    def _ph_line(self, text, w, h, flags, color, sigma):
        """Строка, размытая на sigma (Phantom blurInactive), — QImage с полями pad; кэш до смены раскладки."""
        sig = round(sigma * 2) / 2
        key = (text, w, h, flags, color.rgb(), sig)
        cache = self.__dict__.setdefault("_ph_cache", {})
        hit = cache.get(key)
        if hit is not None:
            return hit
        import blur_fx
        from PyQt6.QtGui import QImage
        pad = int(sig * 3) + 2
        dpr = self.devicePixelRatioF() or 1.0
        img = QImage(int((w + 2 * pad) * dpr), int((h + 2 * pad) * dpr), QImage.Format.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(Qt.GlobalColor.transparent)
        q = QPainter(img)
        q.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        q.setFont(self._font)
        col = QColor(color)
        col.setAlphaF(1.0)
        q.setPen(col)
        q.drawText(QRect(pad, pad, w, h), flags, text)
        q.end()
        out = blur_fx.blur_image(img, sig * dpr) if sig > .3 else img
        out.setDevicePixelRatio(dpr)
        if len(cache) > 96:
            cache.clear()
        cache[key] = (out, pad)
        return out, pad

    def _native_text(self):
        """Кэш раскладок и глифов на C++ (echoes_ui.dll) или None — тогда drawText, как раньше."""
        tc = self.__dict__.get("_ntext", False)
        if tc is False:
            import native_ui
            tc = self._ntext = native_ui.TextCache() if native_ui.available() else None
        return tc

    def _text(self, p, rect, flags, text):
        """p.drawText(rect, flags, text) — без повторной раскладки строки в каждом кадре."""
        tc = self._native_text()
        if tc is None:
            p.drawText(rect, flags, text)
            return
        import i18n
        tc.draw_wrapped(p, rect, flags, i18n.tr(text))

    def _draw_words_ph(self, p, rect, text, col, dim_col, i, alpha):
        """Phantom: текущая строка загорается ПО СЛОВАМ. Время слов — тот же расчёт, что у «жидкого» текста
        (_liquid_layout: пословные метки LRC, иначе оценка word_sync, уточнённая по звуку трека); раскладка —
        с переносами, поэтому у строки в два ряда сначала загорается первый ряд, потом второй. Слово
        заливается слева направо за своё время, граница — мягкая; буквы не подрастают."""
        chars, _h, _line_h = self._liquid_layout(i, text, rect.width())
        now = self._now_ms()
        words: dict = {}                                       # № слова → [x0, x1, база, t0, t1, текст]
        for ch, cx, base, cw, wi, t0, t1 in chars:
            w = words.get(wi)
            if w is None:
                words[wi] = [cx, cx + cw, base, t0, t1, ch]
            else:
                w[1], w[4] = cx + cw, t1
                w[5] += ch
        lit = QColor(col)
        lit.setAlphaF(min(1.0, alpha))
        dim = QColor(dim_col)
        dim.setAlphaF(min(1.0, alpha) * 0.34)
        p.setFont(self._font)
        ox, oy = rect.x(), rect.y()
        for x0, x1, base, t0, t1, word in words.values():
            f = 0.0 if now <= t0 else 1.0 if now >= t1 else (now - t0) / max(1.0, t1 - t0)
            pos = QPointF(ox + x0, oy + base)
            if f <= 0.0 or f >= 1.0:
                p.setPen(lit if f >= 1.0 else dim)
                p.drawText(pos, word)
                continue
            ww = max(1.0, x1 - x0)
            soft = max(3.0, ww * 0.18)
            cut = ox + x0 + ww * f
            grad = QLinearGradient(cut - soft, 0, cut + soft, 0)
            grad.setColorAt(0.0, lit)
            grad.setColorAt(1.0, dim)
            p.setPen(QPen(QBrush(grad), 1))
            p.drawText(pos, word)

    def _draw_liquid(self, p, rect, text, col, dim_col, i, alpha):
        """Текущая строка: серый текст заливается белым слева направо ровно за время строки; буква,
        которую заливает, подрастает и приподнимается, залитые светятся мягким ореолом."""
        lay = self._liquid_layout(i, text, rect.width())
        chars, _h, line_h = lay
        now = self._now_ms()
        p.setFont(self._font)
        tc = self._native_text()
        if tc is not None:                                      # тот же рисунок на C++ (готовые глифы)
            import i18n
            import native_ui
            if self.__dict__.get("_lq_arr", (None,))[0] is not lay:
                self._lq_arr = (lay, native_ui.liquid_arrays(chars, i18n.tr))
            tc.draw_liquid(p, rect.x(), rect.y(), self._lq_arr[1], now, self._font.pixelSize(), col, dim_col,
                           alpha)
            return
        lit = QColor(col)
        lit.setAlphaF(min(1.0, alpha))
        dim = QColor(dim_col)
        dim.setAlphaF(min(1.0, alpha) * 0.32)
        glow = QColor(col)
        px = self._font.pixelSize()
        ox, oy = rect.x(), rect.y()
        for ch, cx, base, cw, _wi, t0, t1 in chars:
            if ch == " ":
                continue
            f = 0.0 if now <= t0 else 1.0 if now >= t1 else (now - t0) / max(1.0, t1 - t0)
            # волна: буквы вокруг заливаемой плавно подрастают и приподнимаются, потом оседают
            tc = (t0 + t1) / 2
            d = (now - tc) / max(170.0, (t1 - t0) * 1.6)
            bump = math.exp(-d * d) if -2.5 < d < 2.5 else 0.0
            settled = 0.03 * min(1.0, f)
            sc = 1.0 + 0.085 * bump + settled                    # рост умеренный — соседние буквы не налезают
            lift = -px * (0.15 * bump + 0.02 * min(1.0, f))
            x = ox + cx
            y = oy + base
            pivot_x = x + cw / 2
            p.save()
            p.translate(pivot_x, y + lift)
            p.scale(sc, sc)
            p.translate(-pivot_x, -y)
            if 0.0 < f < 1.0:                                   # граница заливки — мягкий градиент внутри буквы
                soft = max(2.0, cw * 0.45)
                cut = x + cw * f
                grad = QLinearGradient(cut - soft, 0, cut + soft, 0)
                grad.setColorAt(0.0, lit)
                grad.setColorAt(1.0, dim)
                p.setPen(QPen(QBrush(grad), 1))
                p.drawText(QPointF(x, y), ch)
            else:
                if f >= 1.0 or bump > 0.05:                     # мягкий ореол у залитых букв
                    g = QColor(glow)
                    g.setAlphaF(min(1.0, alpha) * (0.10 + 0.22 * bump) * (1.0 if f >= 1.0 else 0.0))
                    if g.alphaF() > 0.01:
                        p.setPen(g)
                        r = max(1.0, px * 0.05)
                        for dx, dy in ((r, 0), (-r, 0), (0, r), (0, -r)):
                            p.drawText(QPointF(x + dx, y + dy), ch)
                p.setPen(lit if f >= 1.0 else dim)
                p.drawText(QPointF(x, y), ch)
            p.restore()

    def _draw_line(self, p, rect, flags, text, c, glow, shadow, idx):
        """Строка: тень, свечение, сам текст; у текущей — заливка «караоке»."""
        if getattr(self, '_translation_below', False) and '\n' in text:
            original, translated = text.split('\n', 1)
            primary_h = p.fontMetrics().boundingRect(rect, flags, original).height()
            self._draw_line(p, rect, flags, original, c, glow, shadow, idx)
            scale = max(0.4, min(1.5, float(self._st.get('translation_scale', 0.75))))
            color = self._col('translation_color', c)
            color.setAlphaF(c.alphaF() * (color.alphaF() if self._st.get('translation_color') else 1.0))
            p.save()
            p.translate(rect.x(), rect.y() + primary_h + 6)
            p.scale(scale, scale)
            p.setPen(color)
            p.drawText(QRect(0, 0, max(1, int(rect.width() / scale)),
                             max(1, int(rect.height() / scale))), flags, translated)
            p.restore()
            return
        if shadow > 0.01:
            sc = QColor(0, 0, 0)
            sc.setAlphaF(min(1.0, c.alphaF() * shadow * 0.8))
            p.setPen(sc)
            d = max(1, int(self._font.pixelSize() * 0.06))
            self._text(p, rect.translated(d, d), flags, text)
        if glow > 0.01:
            gc = self._col("glow_color", c)
            r = max(1.0, self._font.pixelSize() * 0.10)
            for k in range(8):
                ang = k * math.pi / 4
                gc2 = QColor(gc)
                gc2.setAlphaF(min(1.0, c.alphaF() * glow * 0.22))
                p.setPen(gc2)
                self._text(p, rect.translated(int(round(math.cos(ang) * r)), int(round(math.sin(ang) * r))),
                           flags, text)
        if idx >= 0 and self._st.get("karaoke") and 0 <= idx < len(self._ms) and self._ms[idx] >= 0:
            start = self._ms[idx]
            end = max(start + 300, self._line_end(idx))
            prog = max(0.0, min(1.0, (self._now_ms() - start) / (end - start)))
            br = p.boundingRect(rect, flags, text)
            cut = br.left() + br.width() * prog
            dim = QColor(self._col("dim_color", c))
            dim.setAlphaF(min(1.0, c.alphaF() * 0.45))
            p.save()
            p.setClipRect(QRectF(cut, rect.top() - 50, rect.right() + 100 - cut, rect.height() + 100))
            p.setPen(dim)
            self._text(p, rect, flags, text)
            p.restore()
            p.save()
            p.setClipRect(QRectF(rect.left() - 100, rect.top() - 50, cut - rect.left() + 100, rect.height() + 100))
            p.setPen(c)
            self._text(p, rect, flags, text)
            p.restore()
            return
        p.setPen(c)
        self._text(p, rect, flags, text)


class _NowCaption(QWidget):
    """Подпись под обложкой/диском в режиме текста: название, исполнитель и
    тонкая полоска прогресса — как в Яндекс Музыке."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.title = ""
        self.artist = ""
        self.frac = 0.0
        self.light = False
        self.st = {}                 # стиль из темы: cap_size, cap_progress, color, family

    def set_info(self, title, artist):
        if (title, artist) != (self.title, self.artist):
            self.title, self.artist = title, artist
            self.update()

    def set_frac(self, f):
        f = max(0.0, min(1.0, float(f)))
        if abs(f - self.frac) > 0.0005:
            self.frac = f
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W = self.width()
        st = self.st
        base = QColor(10, 10, 10) if self.light else QColor(255, 255, 255)
        if st.get("color"):
            base = QColor(st["color"])
        ts = int(st.get("cap_size", 14))
        k = ts / 14.0
        f = QFont()
        f.setFamilies(([st["family"]] if st.get("family") else []) + LyricsScrollPanel.FAMILIES)
        f.setPixelSize(ts)
        f.setWeight(QFont.Weight.Bold)
        p.setFont(f)
        c = QColor(base); c.setAlphaF(0.92); p.setPen(c)
        fm = p.fontMetrics()
        h1, h2 = int(20 * k), int(18 * k)
        p.drawText(QRect(0, 0, W, h1), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(self.title, Qt.TextElideMode.ElideRight, W))
        f.setPixelSize(max(7, int(12 * k)))
        f.setWeight(QFont.Weight.Normal)
        p.setFont(f)
        c = QColor(base); c.setAlphaF(0.5); p.setPen(c)
        fm = p.fontMetrics()
        p.drawText(QRect(0, h1, W, h2), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(self.artist, Qt.TextElideMode.ElideRight, W))
        if st.get("cap_progress", True):
            y = h1 + h2 + int(8 * k)
            c = QColor(base); c.setAlphaF(0.16)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(c)
            p.drawRoundedRect(QRectF(0, y, W, 3), 1.5, 1.5)
            c = QColor(base); c.setAlphaF(0.85); p.setBrush(c)
            p.drawRoundedRect(QRectF(0, y, max(3.0, W * self.frac), 3), 1.5, 1.5)
        p.end()


# ────────────────────────────────────────────────────────────────────────────
#  LyricsView — overlay поверх centralWidget
# ────────────────────────────────────────────────────────────────────────────

class LyricsView(QWidget):
    """
    Создаётся с parent=centralWidget (Root).
    В нормальном состоянии: hide().
    При enter(): show(), занимает весь Root, vinyl reparent'ится сюда,
    анимируется в левую колонку. При leave() — обратно.

    API:
        lv = LyricsView(root_widget)
        lv.set_vinyl(vinyl_widget)
        lv.set_decor(title_lbl, artist_lbl, viz_widget, normal_widget)
        lv.set_side_panels(left, right)   # для fade-out
        lv.set_lyrics(text)
        lv.set_position(ms)
        lv.set_accent(c1, c2)
        lv.enter() / lv.leave()
    """

    # ширина левой (vinyl) колонки в режиме текста, px
    VINYL_COL_W = 300

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hide()
        self.setObjectName("LyricsOverlay")
        self.setStyleSheet("#LyricsOverlay, .QWidget{background:transparent;}")
        # Растягиваемся на весь parent автоматически через resizeEvent
        if parent:
            self.setGeometry(parent.rect())

        self._active = False
        self._accent = QColor('#a78bfa')

        # Внешние ссылки
        self._vinyl       = None
        self._normal_w    = None   # весь normal_widget (vinyl+labels+viz)
        self._title_lbl   = None
        self._artist_lbl  = None
        self._viz         = None
        self._lyrics_btn  = None
        self._left_panel  = None
        self._right_panel = None
        self._transport_bar = None  # панель seek/controls/volume — overlay её не перекрывает

        # Сохранённые оригинальные данные vinyl
        self._vinyl_orig_parent = None
        self._vinyl_orig_geom   = QRect()

        # Данные текста
        self._lines = []
        self._has_timings = False

        # ── Внутренний layout: [vinyl_slot | gap | divider | text] ──
        # vinyl_slot — просто место, vinyl сам летит туда анимацией
        self._hbox = QHBoxLayout(self)
        self._hbox.setContentsMargins(0, 0, 0, 0)
        self._hbox.setSpacing(0)

        # Левая колонка-слот (для правильного размещения текста)
        self._left_col = QWidget()
        self._left_col.setStyleSheet(".QWidget{background:transparent;}")
        self._left_col.setFixedWidth(self.VINYL_COL_W)
        self._hbox.addWidget(self._left_col)

        self._divider = Divider(self._accent)
        self._hbox.addWidget(self._divider)
        self._divider.hide()                 # в стиле Яндекс Музыки разделителя нет

        # Правая колонка — текст
        self._text_panel = LyricsScrollPanel()
        self._hbox.addWidget(self._text_panel, 1)

        # подпись под диском: название, исполнитель, прогресс
        self._caption = _NowCaption(self)
        self._caption.hide()
        self._cap_h = 54

        # Кнопка закрытия — в левой колонке, снизу по центру
        self._close_btn = QPushButton("Закрыть", self)
        self._close_btn_light = False
        self._apply_close_btn_style()
        self._close_btn.hide()
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # сигнал подключается снаружи через set_close_callback
        self._close_cb = None
        self._close_btn.clicked.connect(self._on_close_clicked)

        # «Поменять теги трека» — над текстом, у треков без исполнителя / обложки или с дополненными тегами
        self._tags_on = False
        self._tags_cb = None
        self._tags_btn = QPushButton("Поменять теги трека (Обложка, автор и тд)", self)
        self._tags_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tags_btn.clicked.connect(lambda: self._tags_cb and self._tags_cb())
        self._tags_btn.hide()

        # ── Fluid-режим: левая половина экрана — живая жидкость с винилом,
        #    правая — чистая контрастная подложка под текст ──
        self._fluid_mode = False
        self._fluid_dark = False

        self._backdrop = QWidget(self)
        self._backdrop.setObjectName("LyricsBackdrop")
        self._backdrop.setStyleSheet("background: rgb(236,231,200);")
        self._backdrop.hide()
        self._backdrop.lower()

        # Левая половина в Fluid — постер с живой жидкостью (кадры даёт сцена)
        self._fluid_left = None
        self._fluid_stage = None

        # «Сплошной» режим (тема Winamp): overlay целиком закрыт одним цветом
        self._solid = None

        # Анимации (держим ссылки чтобы GC не убил)
        self._anims = []

        # Вызывается ровно тогда, когда winyl реально вернулся в
        # _normal_widget (а не по таймеру "на глазок") — чтобы
        # MainWindow мог безопасно снять заморозку размеров.
        self._leave_finished_cb = None

        # Своя раскладка из темы конструктора: lyr_text / lyr_vinyl / lyr_caption / lyr_close →
        # {"free", "x", "y", "w", "h" (доли overlay), "hidden"}. Пусто — стандартная колонка.
        self._items = {}
        self._text_free = False

    # ── оформление из темы конструктора ──────────────────────────────────────

    def set_custom(self, style: dict | None, items: dict | None = None, family: str = ""):
        """Стиль текста и раскладка элементов режима текста (None — стандартный вид)."""
        self._text_panel.set_style(style, family)
        cs = dict(style or {})
        cs["family"] = family
        self._caption.st = cs if style else {}
        self._cap_h = int(54 * (int(cs.get("cap_size", 14)) / 14.0)) if style else 54
        if not cs.get("cap_progress", True) and style:
            self._cap_h = int(self._cap_h * 0.75)
        self._caption.update()
        items = {k: dict(v) for k, v in (items or {}).items() if k.startswith("lyr_") and isinstance(v, dict)}
        for k in ("lyr_text", "lyr_vinyl", "lyr_caption", "lyr_close"):
            self.set_item(k, items.get(k) or {})

    def item_hidden(self, key) -> bool:
        return bool((self._items.get(key) or {}).get("hidden"))

    def set_item(self, key, s: dict):
        """Один элемент: свободное место/размер или «убран». Можно на лету (в режиме текста)."""
        s = dict(s or {})
        old = self._items.get(key) or {}
        if s == old:
            return
        self._items[key] = s
        hidden, was_hidden = bool(s.get("hidden")), bool(old.get("hidden"))
        if key == "lyr_text":
            self._set_text_free(bool(s.get("free")))
            if self._active:
                self._text_panel.setVisible(not hidden)
        elif key == "lyr_caption" and self._active and not self._solid:
            self._caption.setVisible(not hidden)
            self._caption.raise_()
        elif key == "lyr_close" and self._active:
            self._close_btn.setVisible(not hidden)
            self._close_btn.raise_()
        elif key == "lyr_vinyl" and self._active and self._vinyl is not None and hidden != was_hidden:
            if hidden:
                self._stop_anims()
                self._return_vinyl()
                self._fade_widget(self._vinyl, out=True, ms=200)
            else:
                start = self._take_vinyl()
                self._fly_vinyl(start, self._vinyl_rect(), 360, 1.0)
        if self._active:
            if key == "lyr_vinyl" and self._vinyl is not None and self._vinyl.parent() is self:
                a = getattr(self, "_vinyl_anim", None)
                if a is None or a.state() != a.State.Running:
                    self._vinyl.setGeometry(self._vinyl_rect())
            self._apply_geometry()

    def _set_text_free(self, free: bool):
        if free == self._text_free:
            return
        self._text_free = free
        if free:
            self._hbox.removeWidget(self._text_panel)
        else:
            self._hbox.addWidget(self._text_panel, 1)
        self._text_panel.show() if self._active and not self.item_hidden("lyr_text") else None

    def _free_rect(self, key) -> QRect | None:
        s = self._items.get(key) or {}
        if not s.get("free"):
            return None
        W, H = max(1, self.width()), max(1, self.height())
        return QRect(int(round(float(s.get("x", 0.1)) * W)), int(round(float(s.get("y", 0.1)) * H)),
                     max(4, int(round(float(s.get("w", 0.2)) * W))), max(4, int(round(float(s.get("h", 0.2)) * H))))

    # ── публичный API ────────────────────────────────────────────────────────

    def set_vinyl(self, v):        self._vinyl = v
    def set_normal_widget(self, w): self._normal_w = w
    def set_viz(self, v):          self._viz = v
    def set_title_artist(self, title, artist):
        self._title_lbl  = title
        self._artist_lbl = artist
    def set_lyrics_btn(self, btn):
        self._lyrics_btn = btn
    def set_decor(self, title, artist, viz, normal):
        self._title_lbl  = title
        self._artist_lbl = artist
        self._viz        = viz
        self._normal_w   = normal
    def set_side_panels(self, left, right):
        self._left_panel  = left
        self._right_panel = right
    def set_transport_bar(self, bar):
        """Панель с seek/play-controls/громкостью — overlay должен
        останавливаться прямо над ней, чтобы её кнопки (в т.ч. "Текст")
        всегда оставались кликабельными."""
        self._transport_bar = bar

    def set_solid_mode(self, color):
        """color — CSS-цвет сплошной подложки на весь overlay (тема Winamp),
        None — выключить. Во Fluid игнорируется (там своя подложка)."""
        self._solid = color or None
        if self._solid and not self._fluid_mode:
            self._backdrop.setStyleSheet(f"background: {self._solid};")
            c = QColor(self._solid)
            self._text_panel.set_fade_rgb(c.red(), c.green(), c.blue())
        elif not self._fluid_mode:
            self._text_panel.reset_fade()
        if self._active and not self._fluid_mode:
            self._apply_geometry()
            self._backdrop.setVisible(bool(self._solid))
            self._backdrop.lower()

    def set_fluid_source(self, stage):
        """FluidPanel — источник кадров жидкости для постера в режиме текста."""
        self._fluid_stage = stage
        if self._fluid_left is None:
            try:
                from fluid_theme import FluidPosterBackdrop
            except Exception as e:          # noqa: BLE001
                print("[lyrics] fluid backdrop недоступен:", e)
                return
            self._fluid_left = FluidPosterBackdrop(self)
            self._fluid_left.hide()
        self._fluid_left.set_stage(stage)

    def set_close_callback(self, cb):
        self._close_cb = cb

    def set_leave_finished_callback(self, cb):
        """cb вызывается сразу после того, как vinyl реально вернулся
        в исходный layout (в конце leave()) — используется MainWindow,
        чтобы снять заморозку размеров без гонки с длительностью анимации."""
        self._leave_finished_cb = cb

    def _on_close_clicked(self):
        if self._close_cb:
            self._close_cb()

    def _col_width(self) -> int:
        """Ширина левой (vinyl) колонки: в fluid-режиме — половина экрана,
        иначе узкая колонка как в остальных темах."""
        if self._fluid_mode:
            return max(260, self.width() // 2)
        return self.VINYL_COL_W

    def _vinyl_rect(self) -> QRect:
        r = self._free_rect("lyr_vinyl")
        if r is not None:
            return r
        col = self._col_width()
        cap = self._cap_h + 18
        if self._fluid_mode:
            sz = max(180, min(col - 150, self.height() - 200 - cap, 620))
        else:
            sz = max(120, min(col - 40, self.height() - 90 - cap))
        tx = (col - sz) // 2
        ty = (self.height() - sz - cap) // 2
        return QRect(tx, ty, sz, sz)

    def _caption_rect(self) -> QRect:
        r = self._free_rect("lyr_caption")
        if r is not None:
            return r
        v = self._vinyl_rect()
        w = max(160, min(self._col_width() - 40, int(v.width() * 1.05)))
        return QRect((self._col_width() - w) // 2, v.bottom() + 16, w, self._cap_h)

    def _apply_geometry(self):
        col = self._col_width()
        self._left_col.setFixedWidth(col)
        if self._solid and not self._fluid_mode:
            self._backdrop.setGeometry(self.rect())
        else:
            self._backdrop.setGeometry(col, 0, max(0, self.width() - col), self.height())
        if self._fluid_left is not None:
            self._fluid_left.setGeometry(0, 0, col, self.height())
        if self._active and self._vinyl is not None and self._vinyl.parent() is self:
            self._vinyl.setGeometry(self._vinyl_rect())
        self._caption.setGeometry(self._caption_rect())
        self._caption.light = self._text_panel._light
        if self._text_free:
            self._text_panel.setGeometry(self._free_rect("lyr_text") or self._text_panel.geometry())
        self._reposition_close_btn()

    def set_tags_button(self, on: bool, cb=None):
        if cb is not None:
            self._tags_cb = cb
        self._tags_on = bool(on)
        self._reposition_tags_btn()

    def _reposition_tags_btn(self):
        b = self._tags_btn
        vis = self._tags_on and self._active and self._tags_cb is not None and not self.item_hidden("lyr_text")
        if not vis:
            b.hide()
            return
        b.setStyleSheet(self._close_btn.styleSheet())
        b.adjustSize()
        tp = self._text_panel.geometry()
        x = tp.x() + 24 if tp.width() > 0 else self._col_width() + 24
        b.setGeometry(x, max(10, tp.y() + 10), b.sizeHint().width(), b.sizeHint().height())
        b.show()
        b.raise_()

    def _reposition_close_btn(self):
        self._reposition_tags_btn()
        btn = self._close_btn
        r = self._free_rect("lyr_close")
        if r is not None:
            btn.setGeometry(r)
            return
        btn.adjustSize()
        bw = max(btn.sizeHint().width(), 110)
        bh = btn.sizeHint().height()
        x = (self._col_width() - bw) // 2
        y = self.height() - bh - 22
        btn.setGeometry(x, y, bw, bh)

    def set_accent(self, c1: QColor, c2: QColor):
        self._accent = c1
        self._divider.set_accent(c1)

    def _apply_close_btn_style(self):
        if self._close_btn_light:
            self._close_btn.setStyleSheet(
                "QPushButton {"
                "  background: rgba(0,0,0,0.07);"
                "  color: rgba(0,0,0,0.40);"
                "  border: 1px solid rgba(0,0,0,0.12);"
                "  border-radius: 14px;"
                "  font-size: 12px; font-weight: 500; padding: 7px 20px;"
                "}"
                "QPushButton:hover {"
                "  background: rgba(0,0,0,0.13);"
                "  color: rgba(0,0,0,0.75);"
                "  border-color: rgba(0,0,0,0.22);"
                "}"
            )
        else:
            self._close_btn.setStyleSheet(
                "QPushButton {"
                "  background: rgba(255,255,255,0.08);"
                "  color: rgba(255,255,255,0.50);"
                "  border: 1px solid rgba(255,255,255,0.12);"
                "  border-radius: 14px;"
                "  font-size: 12px; font-weight: 500; padding: 7px 20px;"
                "}"
                "QPushButton:hover {"
                "  background: rgba(255,255,255,0.14);"
                "  color: rgba(255,255,255,0.85);"
                "  border-color: rgba(255,255,255,0.22);"
                "}"
            )

    def set_light_theme(self, is_light: bool):
        self._text_panel.set_light(is_light)
        self._close_btn_light = is_light
        self._apply_close_btn_style()

    def set_fluid_mode(self, on: bool, dark: bool = False):
        """Fluid-тема: колонка винила = половина экрана, правая половина —
        чистая подложка (без жидкости), текст контрастный и читаемый."""
        on = bool(on)
        dark = bool(dark)
        changed = (on != self._fluid_mode) or (dark != self._fluid_dark)
        self._fluid_mode, self._fluid_dark = on, dark
        if on:
            col = (13, 13, 16) if dark else (236, 231, 200)
            self._backdrop.setStyleSheet(f"background: rgb({col[0]},{col[1]},{col[2]});")
            self._text_panel.set_fade_rgb(*col)
        else:
            self._text_panel.reset_fade()
        if self._fluid_left is not None:
            self._fluid_left.set_dark(dark)
        if changed and self._active:
            self._apply_geometry()
            self._backdrop.setVisible(on)
            if self._fluid_left is not None:
                self._fluid_left.setVisible(on)
            if on:
                self._backdrop.lower()
                if self._fluid_left is not None:
                    self._fluid_left.lower()

    def set_lyrics(self, text: str):
        if not text or text.strip() in ('', 'Текст не найден.', 'Загрузка…'):
            self._lines = [{'ms': -1, 'text': text or 'Нет текста', 'words': None}]
            self._has_timings = False
        else:
            self._lines, self._has_timings = parse_lrc(text)
            if not self._has_timings:
                self._lines = split_plain(text)
        self._text_panel.load(self._lines, timed=self._has_timings)

    def set_position(self, ms: int):
        if not self._has_timings or not self._lines:
            return
        self._text_panel.set_pos_ms(ms)

    def set_seek_callback(self, cb):
        """cb(ms) — перемотка по клику на строку текста."""
        self._text_panel.seek_cb = cb

    def set_time(self, cur_ms: int, total_ms: int):
        """Передать текущее время в шапку панели текста."""
        self._text_panel.set_time(cur_ms, total_ms)
        self._caption.set_frac(cur_ms / total_ms if total_ms > 0 else 0.0)
        t = self._title_lbl.text() if self._title_lbl is not None else ""
        a = self._artist_lbl.text() if self._artist_lbl is not None else ""
        self._caption.set_info(t, a)

    # ── геометрия ────────────────────────────────────────────────────────────

    def _overlay_rect(self) -> QRect:
        """Overlay занимает весь parent. Кнопки управления поднимаются
        над overlay через raise_() в MainWindow._toggle_lyrics_mode."""
        parent = self.parent()
        if not parent:
            return self.geometry()
        return QRect(parent.rect())

    # ── вход / выход ─────────────────────────────────────────────────────────

    # Длительности/кривые переходов — в одном месте
    ENTER_MS = 820
    LEAVE_MS = 720
    FADE_IN_MS = 460
    FADE_OUT_MS = 380

    def _overlay_parts(self):
        """Всё, что принадлежит overlay (кроме диска) — плавно проявляется/гаснет."""
        parts = [w for w, k in ((self._text_panel, "lyr_text"), (self._close_btn, "lyr_close"))
                 if not self.item_hidden(k)]
        if self._caption.isVisible():
            parts.append(self._caption)
        if self._backdrop.isVisible():
            parts.append(self._backdrop)
        if self._fluid_left is not None and self._fluid_left.isVisible():
            parts.append(self._fluid_left)
        return parts

    def _decor_widgets(self, entering=False):
        # echoesHidden — виджет скрыт темой из конструктора: его не показываем и не «гасим»;
        # echoesFree на входе — тема поставила элемент поверх режима текста, он остаётся виден
        ws = [self._viz, self._title_lbl, self._artist_lbl, self._lyrics_btn]
        if self._vinyl is not None and self.item_hidden("lyr_vinyl") and self._vinyl.parent() is not self:
            ws.append(self._vinyl)                    # пластинку в режиме текста убрали — гаснет на месте
        return [w for w in ws if w is not None and not w.property("echoesHidden")
                and not (entering and w.property("echoesFree"))]

    @staticmethod
    def _pop_rect(a: QRect, b: QRect, scale: float) -> QRect:
        """Середина пути между a и b, чуть увеличенная — «подъём» в полёте."""
        cx = (a.center().x() + b.center().x()) / 2.0
        cy = (a.center().y() + b.center().y()) / 2.0
        w = (a.width() + b.width()) / 2.0 * scale
        h = (a.height() + b.height()) / 2.0 * scale
        return QRect(int(cx - w / 2), int(cy - h / 2), int(w), int(h))

    def _fly_vinyl(self, start: QRect, end: QRect, ms: int, pop: float, on_done=None):
        vinyl = self._vinyl
        if hasattr(vinyl, "set_fast_mode"):
            vinyl.set_fast_mode(True)          # в полёте — без перестройки кэшей диска

        def _landed():
            if hasattr(vinyl, "set_fast_mode"):
                vinyl.set_fast_mode(False)
            if on_done:
                on_done()
        anim = QPropertyAnimation(vinyl, b"geometry")
        anim.setDuration(ms)
        anim.setStartValue(start)
        anim.setKeyValueAt(0.5, self._pop_rect(start, end, pop))
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim.finished.connect(_landed)
        anim.start()
        self._anims.append(anim)
        self._vinyl_anim = anim

    def _stop_anims(self):
        for a in getattr(self, "_anims", []):
            try:
                a.stop()
            except RuntimeError:
                pass
        self._anims = []

    def enter(self):
        if self._active:
            return
        self._active = True
        self._stop_anims()

        if self.parent():
            self.setGeometry(self._overlay_rect())
        self.show()
        self.raise_()
        self._apply_geometry()
        if self._solid and not self._fluid_mode:
            self._backdrop.show()
            self._backdrop.lower()
        if self._fluid_mode:
            self._backdrop.show()
            self._backdrop.lower()
            if self._fluid_left is not None:
                self._fluid_left.show()
                self._fluid_left.lower()

        # overlay проявляется, а то, что под ним, гаснет. Ничего не прячем —
        # раскладка под overlay не меняется, и диску есть куда вернуться.
        self._reposition_close_btn()
        self._close_btn.setVisible(not self.item_hidden("lyr_close"))
        self._text_panel.setVisible(not self.item_hidden("lyr_text"))
        if not self._solid and not self.item_hidden("lyr_caption"):
            self._caption.setGeometry(self._caption_rect())
            self._caption.light = self._text_panel._light
            if self._title_lbl is not None:
                self._caption.set_info(self._title_lbl.text(),
                                       self._artist_lbl.text() if self._artist_lbl is not None else "")
            self._caption.show()
            self._caption.raise_()
        for w in self._overlay_parts():
            self._fade_widget(w, out=False, ms=self.FADE_IN_MS)
        for w in self._decor_widgets(entering=True):
            self._fade_widget(w, out=True, ms=260)
        for panel in (self._left_panel, self._right_panel):
            # панель скрыта темой — не трогаем; поставлена поверх режима текста — остаётся
            if panel and not panel.property("echoesHidden") and not panel.property("echoesFree"):
                self._fade_widget(panel, out=True, ms=320)

        vinyl = self._vinyl
        if vinyl is None or self.item_hidden("lyr_vinyl"):
            return
        start_rect = self._take_vinyl()
        vinyl.raise_()
        self._close_btn.raise_()
        self._fly_vinyl(start_rect, self._vinyl_rect(), self.ENTER_MS, 1.06)

    def _take_vinyl(self) -> QRect:
        """Диск — из раскладки плеера к себе (на его место — невидимая заглушка). → откуда лететь."""
        vinyl = self._vinyl
        if getattr(self, "_placeholder", None) is not None and vinyl.parent() is self:
            # повторный вход, пока диск ещё летел назад — подхватываем с места
            start_rect = vinyl.geometry()
        else:
            self._vinyl_orig_parent = vinyl.parent()
            self._vinyl_orig_layout = None
            self._placeholder = None
            glob = vinyl.mapToGlobal(QPoint(0, 0))
            local = self.mapFromGlobal(glob)
            start_rect = QRect(local.x(), local.y(), vinyl.width(), vinyl.height())
            if (local.x() == 0 and local.y() == 0) or vinyl.width() < 10 or not vinyl.isVisible():
                start_rect = self._vinyl_rect()
            lay = self._vinyl_orig_parent.layout() if self._vinyl_orig_parent is not None else None
            if lay is not None:
                idx = lay.indexOf(vinyl)
                if idx != -1:
                    item = lay.itemAt(idx)
                    self._vinyl_orig_layout = lay
                    self._vinyl_orig_stretch = lay.stretch(idx) if hasattr(lay, "stretch") else 0
                    self._vinyl_orig_alignment = item.alignment()
                    # Невидимая заглушка занимает место диска: соседи не
                    # «съезжают», а на выходе известно, куда лететь.
                    ph = QWidget()
                    ph.setSizePolicy(vinyl.sizePolicy())
                    ph.setMinimumSize(vinyl.minimumSize())
                    ph.setMaximumSize(vinyl.maximumSize())
                    ph.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                    lay.removeWidget(vinyl)
                    lay.insertWidget(idx, ph, self._vinyl_orig_stretch, self._vinyl_orig_alignment)
                    self._placeholder = ph
            vinyl.setParent(self)
            vinyl.setGeometry(start_rect)
            vinyl.setGraphicsEffect(None)
            vinyl.show()
        return start_rect

    def _return_vinyl(self):
        """Диск — сразу обратно в раскладку плеера (на место заглушки)."""
        vinyl = self._vinyl
        ph = getattr(self, "_placeholder", None)
        lay = getattr(self, "_vinyl_orig_layout", None)
        if vinyl is not None and vinyl.parent() is self:
            orig = self._vinyl_orig_parent
            vinyl.setParent(orig)
            if lay is not None and ph is not None:
                idx = lay.indexOf(ph)
                lay.removeWidget(ph)
                lay.insertWidget(max(0, idx), vinyl, self._vinyl_orig_stretch,
                                 self._vinyl_orig_alignment)
                lay.invalidate()
                lay.activate()
            vinyl.show()
        if ph is not None:
            ph.hide()
            ph.deleteLater()
        self._placeholder = None

    def _home_rect(self) -> QRect:
        """Куда вернуть диск: текущая геометрия заглушки в наших координатах."""
        ph = getattr(self, "_placeholder", None)
        if ph is not None:
            try:
                tl = self.mapFromGlobal(ph.mapToGlobal(QPoint(0, 0)))
                if ph.width() > 10:
                    return QRect(tl, ph.size())
            except RuntimeError:
                pass
        return self._vinyl.geometry() if self._vinyl is not None else QRect()

    def leave(self):
        if not self._active:
            return
        self._active = False
        self._stop_anims()
        self._tags_btn.hide()

        # overlay растворяется, интерфейс под ним проявляется — одновременно
        # с полётом диска на своё место
        for w in self._overlay_parts():
            self._fade_widget(w, out=True, ms=self.FADE_OUT_MS)
        for panel in (self._left_panel, self._right_panel):
            if panel and not panel.property("echoesHidden"):
                panel.show()
                self.fade_external(panel, out=False, ms=self.LEAVE_MS - 120)
        for w in self._decor_widgets():
            w.show()
            self.fade_external(w, out=False, ms=self.LEAVE_MS)

        vinyl = self._vinyl
        if vinyl is None or vinyl.parent() is not self:
            self._finish_leave()
            return
        self._fly_vinyl(vinyl.geometry(), self._home_rect(), self.LEAVE_MS, 1.04,
                        on_done=self._finish_leave)

    def _finish_leave(self):
        if self._active:
            return                      # пока летели — пользователь снова открыл текст
        self._return_vinyl()
        self._tags_btn.hide()

        self._flush_ghosts()
        self._caption.hide()
        self.hide()
        self._backdrop.hide()
        if self._fluid_left is not None:
            self._fluid_left.hide()
        # эффекты прозрачности больше не нужны — снимаем (они не бесплатны)
        for w in self._overlay_parts() + [self._backdrop] + \
                ([self._fluid_left] if self._fluid_left is not None else []):
            w.setGraphicsEffect(None)
        for w in self._decor_widgets() + ([self._vinyl] if self._vinyl is not None else []):
            w.setGraphicsEffect(None)
            w.show()
        for panel in (self._left_panel, self._right_panel):
            if panel:
                panel.setGraphicsEffect(None)
        if self._leave_finished_cb:
            self._leave_finished_cb()

    # ── helpers ──────────────────────────────────────────────────────────────

    def _fade_widget(self, w, out: bool, on_done=None, ms: int = 320):
        """Плавное исчезание/появление через «снимок» (см. _FadeGhost):
        сам виджет на время анимации скрыт дешёвым эффектом с прозрачностью 0,
        а гаснет/проявляется его картинка. Прерывается с текущего значения."""
        ghosts = self.__dict__.setdefault("_ghosts", {})
        start = None
        prev = ghosts.pop(w, None)
        if prev is not None:
            g_old, a_old, _ = prev
            try:
                a_old.stop()
                start = g_old.op
                g_old.hide()
                g_old.deleteLater()
            except RuntimeError:
                pass
        if start is None:
            eff = w.graphicsEffect()
            if isinstance(eff, QGraphicsOpacityEffect):
                start = eff.opacity()
            else:
                start = 0.0 if not out else 1.0
        end = 0.0 if out else 1.0

        # снимок виджета в полностью видимом состоянии
        w.setGraphicsEffect(None)
        if not w.isVisible():
            w.show()
        own = (w.parentWidget() is self)
        host = self if own else self.parentWidget()
        if host is None or w.width() < 1 or w.height() < 1:
            if out:
                eff = QGraphicsOpacityEffect(w); eff.setOpacity(0.0); w.setGraphicsEffect(eff)
            if on_done:
                on_done()
            return
        pm = w.grab()
        eff = QGraphicsOpacityEffect(w)
        eff.setOpacity(0.0)                   # opacity 0 Qt не рисует вовсе — это бесплатно
        w.setGraphicsEffect(eff)

        ghost = _FadeGhost(pm, host)
        tl = host.mapFromGlobal(w.mapToGlobal(QPoint(0, 0)))
        ghost.setGeometry(QRect(tl, w.size()))
        ghost.set_op(start)
        ghost.show()
        if own:
            ghost.raise_()
            if self._vinyl is not None and self._vinyl.parentWidget() is self:
                self._vinyl.raise_()
        else:
            ghost.stackUnder(self)            # под overlay текста

        a = QVariantAnimation(self)
        a.setDuration(ms)
        a.setEasingCurve(QEasingCurve.Type.InOutSine if out else QEasingCurve.Type.OutCubic)
        a.setStartValue(float(start))
        a.setEndValue(float(end))
        a.valueChanged.connect(ghost.set_op)

        def _done(w=w, ghost=ghost, out=out):
            if ghosts.get(w, (None,))[0] is ghost:
                ghosts.pop(w, None)
            ghost.hide()
            ghost.deleteLater()
            if not out:
                w.setGraphicsEffect(None)      # виджет снова настоящий
            if on_done:
                on_done()
        a.finished.connect(_done)
        ghosts[w] = (ghost, a, out)
        a.start()
        self._anims.append(a)

    def fade_external(self, w, out: bool, ms: int = 320):
        """Для MainWindow: то же плавное исчезание для виджетов под overlay.
        Проявлять то, что и так видно (не гасло — его тема ставила поверх текста), не нужно."""
        if not out and w not in self.__dict__.get("_ghosts", {}) and w.isVisible() \
                and not isinstance(w.graphicsEffect(), QGraphicsOpacityEffect):
            return
        self._fade_widget(w, out=out, ms=ms)

    def _flush_ghosts(self):
        """Мгновенно завершить все незаконченные исчезания/появления."""
        ghosts = self.__dict__.get("_ghosts", {})
        for w, (g, a, out) in list(ghosts.items()):
            try:
                a.stop()
                g.hide()
                g.deleteLater()
                if not out:
                    w.setGraphicsEffect(None)   # недопроявленный виджет — сразу видим
            except RuntimeError:
                pass
        ghosts.clear()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply_geometry()

    def parentResized(self):
        """Вызывать из MainWindow.resizeEvent когда меняется размер окна."""
        if self.parent():
            self.setGeometry(self._overlay_rect())
        self._apply_geometry()
