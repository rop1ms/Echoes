"""Лента и друзья для своего второго устройства (net_devfeed): ПК отдаёт привязанному устройству ленту друзей,
выполняет его действия от своего имени и ничего не отдаёт чужим.

Четыре узла в тестовой сети без Tor: друг, ПК, устройство (как телефон Echoes Lite) и посторонний друг ПК.

python qa/test_net_devfeed.py
"""
import copy
import os
import sys
import tempfile
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="echoes_devfeed_"))
os.environ["ECHOES_NET_DEV"] = str(TMP / "dev")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:                                          # noqa: BLE001
    pass

import net_core                                             # noqa: E402
import net_devfeed                                          # noqa: E402

fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


def wait(fn, timeout=25.0, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:                                  # noqa: BLE001
            pass
        time.sleep(step)
    return False


class Node:
    def __init__(self, name):
        self.events = []
        self.nd = net_core.NetNode(TMP / name, on_event=lambda k, d: self.events.append((k, d)), log=lambda *a: None)
        self.nd.settings.update({"name": name, "udp": False, "direct": False, "nostr": False, "upnp": False,
                                 "use_tor": False, "moderation": False})
        self.onion = self.nd.me.onion

    def seen(self, kind):
        return [d for k, d in self.events if k == kind]


def friends(a, b):
    a.nd.store.upsert_contact(b.onion, status="friend", name=b.nd.settings["name"])
    b.nd.store.upsert_contact(a.onion, status="friend", name=a.nd.settings["name"])


F, P, D, E = Node("friend"), Node("pc"), Node("device"), Node("stranger")
friends(F, P)
friends(P, D)
friends(P, E)
P.nd.settings["my_devices"] = [D.onion]
D.nd.settings["my_devices"] = [P.onion]
D.nd.settings["dev_feed_pull"] = True
E.nd.settings["dev_feed_pull"] = True                       # посторонний «хочет» ленту — но он не устройство
E.nd.settings["my_devices"] = [P.onion]                     # и даже считает ПК своим: решает сторона ПК
for n in (F, P, D, E):
    n.nd.start()


def registered():
    import json
    return len(json.loads((TMP / "dev" / "registry.json").read_text(encoding="utf-8"))) == 4


# Узлы одновременно дописывают себя в общий registry.json тестовой сети, и при гонке запись теряется
# (в реестре остаётся один узел из четырёх). Поэтому дорегистрировать всех по очереди из одного потока.
wait(lambda: all(getattr(n.nd, "local_port", None) for n in (F, P, D, E)), 20)
for n in (F, P, D, E):
    n.nd._dev_register()
check(registered(), "все четыре узла записаны в реестр тестовой сети")
for n in (F, P, D, E):                                      # первые попытки ушли до регистрации — не ждать пауз
    n.nd.call(n.nd.poke)


_last_poke = [time.time()]


def linked():
    ok = all(b.onion in a.nd.peers and a.nd.peers[b.onion].alive for a, b in ((P, F), (P, D), (P, E), (F, P), (D, P)))
    if not ok and time.time() - _last_poke[0] > 4:          # под нагрузкой попытки отваливаются и паузы растут —
        _last_poke[0] = time.time()                         # не ждать минутами, пробовать снова
        for n in (F, P, D, E):
            n.nd.call(n.nd.poke)
    return ok


check(wait(linked, 120), "все узлы соединились в тестовой сети")
check(F.onion not in D.nd.peers and not D.nd.is_friend(F.onion), "устройство и друг ПК друг друга не знают")

# ── страница ленты ─────────────────────────────────────────────────────────
F.nd.call(F.nd.publish, "Первый пост друга")
check(wait(lambda: len(P.nd.store.posts(F.onion)) == 1), "ПК получил пост друга обычным путём")
pid1 = P.nd.store.posts(F.onion)[0]["id"]
D.nd.call(net_devfeed.request, D.nd, P.onion)
check(wait(lambda: D.nd.store.post(pid1) is not None), "устройство получило пост друга через ПК")
check(D.nd._contact_name(F.onion) == "friend", "устройство узнало имя друга из списка контактов ПК")
check(wait(lambda: any(d.get("new") == 1 for d in D.seen("devfeed")), 5),
      "устройству пришло событие devfeed с числом новых постов")

# ── живые изменения ────────────────────────────────────────────────────────
F.nd.call(F.nd.publish, "Второй пост, уже после запроса")
check(wait(lambda: len(D.nd.store.posts(F.onion)) == 2), "новый пост друга доходит до устройства без повторного запроса")
pid2 = [p["id"] for p in D.nd.store.posts(F.onion) if p["id"] != pid1][0]

# ── действия от имени ПК ───────────────────────────────────────────────────
D.nd.call(net_devfeed.act, D.nd, P.onion, "react", pid=pid1, kind="emo", val="🔥")
check(wait(lambda: any(r["who"] == P.onion and r["val"] == "🔥" for r in F.nd.store.reacts(pid1))),
      "реакция с устройства дошла до автора с подписью ПК")
check(all(net_core.verify_obj(r, "who") for r in F.nd.store.reacts(pid1)), "подпись реакции сходится")
check(wait(lambda: any(r["who"] == P.onion for r in D.nd.store.reacts(pid1))), "устройство увидело свою реакцию в ленте")
check(wait(lambda: any(d["ok"] for d in D.seen("devact"))), "устройство получило подтверждение dev_act_ok")

D.nd.call(net_devfeed.act, D.nd, P.onion, "vote", pid=pid2, val=1)
check(wait(lambda: F.nd.store.score(pid2) == (1, 0)), "голос с устройства засчитан у автора")
D.nd.call(net_devfeed.act, D.nd, P.onion, "comment", pid=pid2, text="Комментарий с телефона")
check(wait(lambda: any(c["author"] == P.onion and c["text"] == "Комментарий с телефона" for c in F.nd.store.comments(pid2))),
      "комментарий с устройства дошёл до автора от имени ПК")

D.nd.call(net_devfeed.act, D.nd, P.onion, "publish", text="Пост, написанный на телефоне")
check(wait(lambda: any(p["text"] == "Пост, написанный на телефоне" for p in F.nd.store.posts(P.onion))),
      "пост с устройства опубликован от имени ПК и виден другу")
mine = [p for p in P.nd.store.posts(P.onion) if p["text"] == "Пост, написанный на телефоне"]
check(len(mine) == 1 and net_core.verify_obj(mine[0], "author"), "пост подписан ключом ПК")
D.nd.call(net_devfeed.act, D.nd, P.onion, "delete", pid=mine[0]["id"] if mine else "")
check(wait(lambda: not any(p["text"] == "Пост, написанный на телефоне" for p in F.nd.store.posts(P.onion))),
      "удаление своего поста с устройства доходит до друзей")

n_err = len([d for d in D.seen("devact") if not d["ok"]])
D.nd.call(net_devfeed.act, D.nd, P.onion, "delete", pid=pid1)
check(wait(lambda: len([d for d in D.seen("devact") if not d["ok"]]) == n_err + 1) and F.nd.store.post(pid1) is not None,
      "чужой пост с устройства удалить нельзя")
D.nd.call(net_devfeed.act, D.nd, P.onion, "publish", kind="mod", text="x", title="Мод")
check(wait(lambda: len([d for d in D.seen("devact") if not d["ok"]]) == n_err + 2), "моды с устройства не публикуются")


# ── повтор и подделка ──────────────────────────────────────────────────────
async def twice():
    p = await D.nd._peer_for(P.onion)
    m = {"t": "dev_act", "nonce": "same-nonce-1", "act": "comment", "pid": pid1, "text": "только один раз"}
    await p.send(m)
    await p.send(dict(m))
D.nd.call(twice)
check(wait(lambda: any(c["text"] == "только один раз" for c in F.nd.store.comments(pid1))), "комментарий по dev_act выполнен")
time.sleep(1.0)
check(len([c for c in F.nd.store.comments(pid1) if c["text"] == "только один раз"]) == 1,
      "повтор того же nonce не выполняется второй раз")

fake = {"post": copy.deepcopy(P.nd.store.post(pid1)), "comments": [], "votes": [], "reacts": []}
fake["post"]["id"] = "f" * 24
fake["post"]["text"] = "Подделанный текст"
got = []
D.nd.call(lambda: got.append(net_devfeed._take(D.nd, [fake])))
check(wait(lambda: got) and D.nd.store.post("f" * 24) is None, "пост с несходящейся подписью устройство не принимает")

# ── посторонние ────────────────────────────────────────────────────────────
E.nd.call(net_devfeed.request, E.nd, P.onion)


async def evil_act():
    p = await E.nd._peer_for(P.onion)
    await p.send({"t": "dev_act", "nonce": "evil-1", "act": "comment", "pid": pid1, "text": "от постороннего"})
    await p.send({"t": "devfeed_upd", "item": fake})
E.nd.call(evil_act)
time.sleep(2.5)
check(not E.seen("devfeed") and not E.seen("devact") and E.nd.store.post(pid1) is None,
      "обычный друг (не устройство) ленту не получает и ответа не видит")
check(not any(c["text"] == "от постороннего" for c in F.nd.store.comments(pid1)), "dev_act от не-устройства не выполняется")
check(E.onion not in net_devfeed._st(P.nd)["subs"], "посторонний не попал в подписчики ленты")

# ── удаление у автора и выключатель ────────────────────────────────────────
F.nd.call(F.nd.delete_post, pid2)
check(wait(lambda: P.nd.store.post(pid2) is None), "ПК убрал пост, удалённый автором")
check(wait(lambda: D.nd.store.post(pid2) is None), "устройство тоже убрало удалённый пост")

P.nd.call(net_devfeed.set_share, P.nd, D.onion, False)
check(wait(lambda: not net_devfeed.share_on(P.nd, D.onion)), "передача ленты устройству выключена")
F.nd.call(F.nd.publish, "Пост после выключения передачи")
check(wait(lambda: len(P.nd.store.posts(F.onion)) == 2), "ПК получил новый пост")
pid3 = [p["id"] for p in P.nd.store.posts(F.onion) if p["id"] != pid1][0]
D.nd.call(net_devfeed.request, D.nd, P.onion)
check(wait(lambda: any(d.get("off") == "disabled" for d in D.seen("devfeed"))), "устройству отвечают: передача выключена")
time.sleep(1.0)
check(D.nd.store.post(pid3) is None, "после выключения новые посты на устройство не идут")

big = net_devfeed.page(P.nd, 0, 9999)
check(len(big["items"]) <= net_devfeed.PAGE_MAX and net_devfeed._size(big) < net_core.LINE_LIMIT,
      "страница ограничена по числу постов и укладывается в предел строки протокола")

for n in (F, P, D, E):
    n.nd.stop()
time.sleep(0.5)
print("\n" + ("ALL OK" if not fails else f"{len(fails)} FAILED"), flush=True)
os._exit(1 if fails else 0)
