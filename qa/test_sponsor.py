"""Спонсоры ECHOES (net_sponsor): статус выдаёт только модерация, пост подписан самим спонсором и виден на стене
только после одобрения, ссылки на донаты задаёт только админ; подделки отбрасываются; рамки спонсоров видны
только у спонсоров. Настоящие ключи ed25519, без сети.

python qa/test_sponsor.py
"""
import asyncio
import os
import secrets
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
fails = []
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:                                          # noqa: BLE001
    pass


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


import net_core  # noqa: E402
import net_sponsor  # noqa: E402

admin = net_core.Identity(secrets.token_bytes(32))
user = net_core.Identity(secrets.token_bytes(32))
stranger = net_core.Identity(secrets.token_bytes(32))


class FakeNode:
    def __init__(self, me):
        self.me = me
        self.base = Path(tempfile.mkdtemp(prefix="echoes-sponsor-"))
        self.events = []
        self.published = []

    def role(self, onion):
        return "admin" if onion == admin.onion else ""

    def my_role(self):
        return self.role(self.me.onion)

    def staff_hidden(self, *ids):
        return ""

    def emit(self, kind, data):
        self.events.append(kind)

    async def _staff_publish(self, obj, tag, d):
        self.published.append((tag, obj))
        return 1


A = FakeNode(admin)                       # у админа
U = FakeNode(user)                        # у спонсора
run = asyncio.run

# ── статус ── #
run(net_sponsor.grant(U, user.onion))
check(not net_sponsor.is_sponsor(U), "не модератор не может выдать статус")
d = run(net_sponsor.grant(A, user.onion, True, "patron"))
check(d is not None and net_sponsor.is_sponsor(A, user.onion), "админ выдаёт статус спонсора")
check(net_sponsor.tier(A, user.onion) == "patron", "уровень спонсора сохраняется")
check(net_sponsor.take(U, d) and net_sponsor.is_sponsor(U), "решение доходит до спонсора и проверяется подписью")
forged = stranger.sign_obj({"t": "echoes-sponsor", "by": admin.onion, "target": stranger.onion, "allow": True,
                            "tier": "legend", "ts": d["ts"] + 1, "id": "x"})
check(not net_sponsor.take(A, forged) and not net_sponsor.is_sponsor(A, stranger.onion),
      "подделка от имени админа отбрасывается")

# ── пост ── #
p = run(net_sponsor.submit_post(U, "Лиса", "Спасибо за ECHOES!", "", {"artist": "A", "title": "B"}))
check(p is not None and net_sponsor.my_post(U)["text"] == "Спасибо за ECHOES!", "спонсор публикует пост")
check(net_sponsor.take(A, p), "пост доходит до модерации")
check(net_sponsor.wall(A) == [] and len(net_sponsor.queue(A)) == 1, "до проверки поста нет на стене — он в очереди")
S = FakeNode(stranger)
sp_fake = run(net_sponsor.submit_post(S, "Не спонсор", "реклама", "", None))
check(sp_fake is None, "не спонсор не может опубликовать пост")
o = run(net_sponsor.review(A, p, True))
check(o is not None and len(net_sponsor.wall(A)) == 1 and net_sponsor.queue(A) == [],
      "после одобрения пост на стене")
net_sponsor.take(U, o)
check(net_sponsor.post_state(U, net_sponsor.my_post(U)) == "approved", "автор видит, что пост одобрен")
p2 = run(net_sponsor.submit_post(U, "Лиса", "новый текст", "", None))
net_sponsor.take(A, p2)
check(net_sponsor.wall(A) == [] and len(net_sponsor.queue(A)) == 1,
      "новый пост заменяет прежний и снова ждёт проверки")
long_post = dict(p2, text="x" * 400)
check(not net_sponsor.take(A, long_post), "слишком длинный текст отбрасывается")

# ── снятие статуса ── #
run(net_sponsor.review(A, p2, True))
run(net_sponsor.grant(A, user.onion, False))
check(not net_sponsor.is_sponsor(A, user.onion) and net_sponsor.wall(A) == [],
      "статус снят — пост пропадает со стены")

# ── ссылки на донаты ── #
dn = run(net_sponsor.set_donate(A, [{"name": "Boosty", "url": "https://boosty.to/echoes"},
                                    {"name": "плохая", "url": "javascript:alert(1)"}], "Укажите код"))
check(dn is not None and net_sponsor.donate_links(A) == [{"name": "Boosty", "url": "https://boosty.to/echoes"}],
      "админ задаёт ссылки на донаты; не-https отбрасываются")
check(net_sponsor.take(U, dn) and net_sponsor.donate_links(U)[0]["name"] == "Boosty", "ссылки доходят до всех")
check(run(net_sponsor.set_donate(U, [{"name": "x", "url": "https://evil"}])) is None,
      "не админ не может менять ссылки")

# ── сохранение ── #
A2 = FakeNode(admin)
A2.base = A.base
check(net_sponsor.donate_links(A2) and len(net_sponsor.load(A2)["posts"]) == 1,
      "всё сохраняется в sponsors.json и проверяется при загрузке")

# ── рамки спонсоров ── #
import net_frames  # noqa: E402
check(net_frames.effective({"id": "sp:prism"}, [], "") == {}, "рамка спонсора у не спонсора не видна")
check(net_frames.effective({"id": "sp:prism"}, ["__sponsor__"], "").get("id") == "sp:prism",
      "рамка спонсора видна у спонсора")
check(net_frames.clean_spec({"id": "ph:glass"}) == {"id": "ph:glass"} and net_frames.clean_spec({"id": "ph:zzz"}) == {},
      "бесплатные рамки Phantom проходят проверку, выдуманные — нет")
import net_cosmetics  # noqa: E402
from PyQt6.QtGui import QImage, QPainter  # noqa: E402
img = QImage(120, 120, QImage.Format.Format_ARGB32)
bad = []
for k in net_cosmetics._DRAW:
    img.fill(0)
    q = QPainter(img)
    try:
        net_cosmetics.draw(q, k, 120, 1.7)
    except Exception as e:                                 # noqa: BLE001
        bad.append(f"{k}: {e}")
    q.end()
check(not bad, f"все {len(net_cosmetics._DRAW)} рамок рисуются ({bad[:2]})")

print("\nFAILED:", len(fails)) if fails else print("\nВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
sys.exit(1 if fails else 0)
