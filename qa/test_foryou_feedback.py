"""👍/👎 в «Для вас и тренды»: значки на карточке, оценка запоминается, дизлайкнутое пропадает из лент,
лайкнутый исполнитель становится затравкой рекомендаций, «меньше такого» дважды — исполнитель не предлагается.

python qa/test_foryou_feedback.py [папка-для-картинок]
"""
import sys
from pathlib import Path

source = Path(__file__).with_name('ui_smoke.py').read_text('utf-8')
exec(compile(source.split('win = None')[0], str(Path(__file__).with_name('ui_smoke.py')), 'exec'))
import main
import fy_feedback as FB
import ya_foryou as F

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else None
main.WindowsMediaKeyFilter.register = lambda self: None
fails = []


def check(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg, flush=True)
    if not cond:
        fails.append(msg)


def tr(a, t, because=""):
    return {"title": t, "artist": a, "duration": 180, "album": "", "cover_url": "", "because": because}


CACHE = {
    "trends": {"ts": 9e12, "data": {"ru": [tr("Alpha", "One"), tr("Beta", "Two"), tr("Gamma", "Three")],
                                     "world": [tr("Delta", "Four"), tr("Alpha", "Five")]}},
    "recs": {"ts": 9e12, "sig": "", "data": {
        "artists": [], "tracks": [tr("Echo", "Six", "похож на Alpha"), tr("Zeta", "Seven", "похож на Alpha"),
                                  tr("Eta", "Eight", "похож на Alpha")],
        "more": [], "genres": [{"id": 116, "name": "Рэп", "share": 0.3, "tracks": [tr("Theta", "Nine", "Рэп")]}]}},
}
F.load_cache = lambda: CACHE
F.stale = lambda cache, tt: (False, False)

# ── логика без окна ──
s = {}
check(FB.vote(s, tr("Beta", "Two"), -1) == -1 and FB.vote_of(s, tr("Beta", "Two")) == -1, "дизлайк запомнен")
check([t["title"] for t in FB.shape(s, CACHE["trends"]["data"]["ru"], rank=False)] == ["One", "Three"],
      "дизлайкнутый трек убран из ленты")
FB.vote(s, tr("Zeta", "Seven", "похож на Alpha"), 1)
order = [t["title"] for t in FB.shape(s, CACHE["recs"]["data"]["tracks"])]
check(order[0] == "Seven", f"лайкнутый исполнитель — первым в рекомендациях: {order}")
check(FB.artist_score(s, "Alpha") > 0, "лайк «похожего на Alpha» — плюс и самой Alpha")
FB.vote(s, tr("Gamma", "Three"), -1)
FB.vote(s, tr("Gamma", "Other"), -1)
check(not [t for t in FB.shape(s, [tr("Gamma", "New one")]) if t], "исполнитель с двумя 👎 — не предлагается вовсе")
FB.vote(s, tr("Theta", "Nine", "Рэп"), -1, genre="Рэп")
check(FB.genre_factor(s, "Рэп") < 1, "👎 в жанровой ленте — жанра меньше")
FB.vote(s, tr("Beta", "Two"), 0)
check(FB.vote_of(s, tr("Beta", "Two")) == 0, "оценку можно снять")

# ── окно ──
win = main.MainWindow()
win.resize(1400, 900)
win.show(); settle(.5)
win.settings.pop(FB.KEY, None)
win.library = [{"path": "a.mp3", "title": "Song", "artist": "Omega"}]
shell = win._ya
shell.show_page("foryou"); settle(.6)
shell._rebuild("foryou"); settle(.6)
page = shell.pages["foryou"]
def rows():
    return [o for o in page.findChildren(FB.RowFeedback) if o.host.isVisible()]


fbs = rows()
check(len(fbs) == 4, f"значки 👍/👎 у лент: {len(fbs)}")
ru = fbs[0]
check([t["title"] for _, t in ru.cards] == ["One", "Two", "Three"], "чарт не пересортирован")
ru._show(1); settle(.1)
check(ru.btns.isVisible(), "наведение — значки на карточке видны")
if OUT:
    OUT.mkdir(parents=True, exist_ok=True)
    win.grab().save(str(OUT / "foryou_fb.png"))
ru._vote_cur(-1); settle(.1)
check(FB.vote_of(win.settings, tr("Beta", "Two")) == -1, "клик 👎 — оценка в настройках")
check("меньше" in ru.cards[1][0].subtitle, "карточка помечена «меньше такого»")
recs = fbs[2]
recs._show(0); recs._vote_cur(1); settle(.1)
check(FB.vote_of(win.settings, tr("Echo", "Six")) == 1, "клик 👍 — оценка в настройках")
tt = F.taste(win)
check("Echo" in [a for a, _ in tt["top"][:6]], "лайкнутый исполнитель — в затравке рекомендаций")
check(F.seeds_sig(tt) != CACHE["recs"]["sig"], "после оценки рекомендации пересчитаются")
shell._rebuild("foryou"); settle(.6)
ru2 = rows()[0]
check("Two" not in [t["title"] for _, t in ru2.cards], "после пересборки дизлайкнутого трека нет")
print("FAILED" if fails else "ALL OK", len(fails), flush=True)
win.close()
sys.exit(1 if fails else 0)
