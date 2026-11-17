"""Обновления безопасны: ставится только подписанный автором выпуск, подменённый файл отклоняется,
версия, которая не запускается, откатывается сама. Без сети (GitHub подменён локальными архивами).

python qa/test_release_safety.py
"""
import io
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import release_sign as rs

fails = []
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:                                          # noqa: BLE001
    pass


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


check(len(rs.PUBLIC_KEY_HEX) == 64 and not rs.PUBLIC_KEY_HEX.startswith("__"), "в программу вписан ключ автора")
seed = os.urandom(32)
pub = rs.public_hex(seed)
tmp = Path(tempfile.mkdtemp())
tree = tmp / "Echoes-abc"
(tree / "app").mkdir(parents=True)
(tree / "setup").mkdir()
(tree / "app" / "main.py").write_text("print('hi')\n", "utf-8")
(tree / "app" / "version.txt").write_text("2099.01.01-1", "utf-8")
(tree / "setup" / "update.ps1").write_text("Write-Host ok\r\n", "utf-8")
files = {f.relative_to(tree).as_posix(): rs.sha256(f.read_bytes()) for f in tree.rglob("*") if f.is_file()}
man = rs.sign({"version": "2099.01.01-1", "commit": "c" * 40, "channel": "stable", "notes": "", "ts": 1,
               "files": files}, seed)
check(rs.verify(man, pub), "подпись автора принимается")
check(not rs.verify(dict(man, version="2099.12.31-9"), pub), "изменённый манифест отклоняется")
check(not rs.verify(man, rs.public_hex(os.urandom(32))), "чужой ключ отклоняется")
check(not rs.verify({k: v for k, v in man.items() if k != "sig"}, pub), "без подписи — отклоняется")
check(rs.check_tree(tree, man) == [], "файлы совпадают с подписью")
(tree / "app" / "main.py").write_text("import os; os.system('evil')\n", "utf-8")
check(any("изменён" in p for p in rs.check_tree(tree, man)), "подменённый файл найден")
(tree / "app" / "main.py").write_text("print('hi')\n", "utf-8")
(tree / "app" / "extra.py").write_text("x=1\n", "utf-8")
check(any("лишний" in p for p in rs.check_tree(tree, man)), "лишний файл найден")
(tree / "app" / "extra.py").unlink()


# ── обновлятор: скачивает именно коммит выпуска и сверяет файлы ──
def zip_of(folder: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for f in folder.rglob("*"):
            z.write(f, f.relative_to(folder.parent).as_posix())
    return buf.getvalue()


class Resp:
    def __init__(self, data):
        self.data, self.headers = data, {"Content-Length": str(len(data))}

    def raise_for_status(self):
        pass

    def iter_content(self, n):
        for i in range(0, len(self.data), n):
            yield self.data[i:i + n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


import requests
import github_update as gu
rs.PUBLIC_KEY_HEX = pub
served = {}
requests.get = lambda url, **k: (served.__setitem__("url", url), Resp(served["zip"]))[1]
served["zip"] = zip_of(tree)
src = gu.download(dict(man))
check(served["url"].endswith("c" * 40), "скачан ровно коммит из подписанного выпуска")
check((src / "app" / "main.py").exists(), "подписанный выпуск распакован")
(tree / "app" / "main.py").write_text("print('bad')\n", "utf-8")
served["zip"] = zip_of(tree)
try:
    gu.download(dict(man))
    check(False, "подменённый архив отклонён")
except RuntimeError as e:
    check("не совпали" in str(e), "подменённый архив отклонён: " + str(e)[:80])

# The fast installer only reuses an EXE matching the signed package, and the
# compact ZIP is still checked against that same signature.
sys.path.insert(0, str(ROOT / "launcher"))
# The launcher bundles psutil; the player's CI only exercises downloads here.
with patch.dict(sys.modules, {"psutil": ModuleType("psutil")}):
    import core as lc

(tree / "app/main.py").write_text("print('hi')\n", "utf-8")
(tree / "setup/install.ps1").write_text("Write-Host ok\n", "utf-8")
launcher = tmp / "launcher.exe"
launcher.write_bytes(b"test launcher")
man["files"]["setup/install.ps1"] = rs.sha256((tree / "setup/install.ps1").read_bytes())
signed = rs.sign(dict(man, launcher_sha256=rs.sha256(launcher.read_bytes())), seed)
check(rs.verify(signed, pub), "SHA-256 лаунчера входит в подпись")
compact_zip = zip_of(tree)


def download_zip(url, destination, progress, cancel):
    served["url"] = url
    destination.write_bytes(compact_zip)


with patch.object(lc, "release", return_value=signed), patch.object(lc, "_download_archive", download_zip):
    src = lc.download_source(launcher=launcher)
    check(served["url"].endswith("/ECHOES.App.zip"), "подходящий EXE позволяет скачать компактный архив")
    check((src / "ECHOES Launcher.exe").read_bytes() == launcher.read_bytes(), "установщику передан проверенный EXE")
    shutil.rmtree(src.parents[1])
    launcher.write_bytes(b"older launcher")
    src = lc.download_source(launcher=launcher)
    check(served["url"].endswith("c" * 40), "старый EXE использует полный архив подписанного коммита")
    shutil.rmtree(src.parents[1])

# ── откат версии, которая дважды не запустилась ──
import importlib
import boot_guard as bg
inst = tmp / "ECHOES"
(inst / "python").mkdir(parents=True)
(inst / "app").mkdir()
(inst / "app.prev").mkdir()
(inst / "app" / "version.txt").write_text("2.0", "utf-8")
(inst / "app" / "main.py").write_text("broken", "utf-8")
(inst / "app.prev" / "version.txt").write_text("1.0", "utf-8")
(inst / "app.prev" / "main.py").write_text("good", "utf-8")
bg.APP, bg.PREV, bg.STATE = inst / "app", inst / "app.prev", inst / "boot_state.json"
relaunched = []
import subprocess
_Popen = subprocess.Popen
bg.subprocess.Popen = lambda *a, **k: relaunched.append(a)
bg.os._exit = lambda code: (_ for _ in ()).throw(SystemExit(code))
dead = 999999                                              # «прошлый процесс» — его уже нет


def boot():
    d = bg.state()
    if d:
        d["pid"] = dead
        bg._save(d)
    try:
        bg.enter()
    except SystemExit:
        pass


boot()                                                     # 1-й запуск 2.0 — «в процессе», не дошёл до ok
check(bg.state().get("pending") and (inst / "app" / "main.py").read_text() == "broken", "первый неудачный — ждём")
boot()                                                     # 2-й тоже не дошёл
check((inst / "app" / "main.py").read_text() == "broken", "один сбой — ещё не откат")
boot()                                                     # третий старт видит два сбоя подряд — откат
check((inst / "app" / "main.py").read_text() == "good" and bg._version(inst / "app") == "1.0",
      "две неудачи подряд — вернулась прошлая версия")
check("2.0" in (bg.state().get("bad") or []) and relaunched, "плохая версия запомнена, ECHOES перезапущен")
check("2.0" in bg.rolled_back_notice(), "человеку объясняют, что случилось")
(inst / "app" / "version.txt").write_text("3.0", "utf-8")
boot()
bg.mark_ok()
check(not bg.state().get("pending") and bg.state().get("fails") == 0, "удачный запуск сбрасывает счётчик")
d = bg.state()
# второй запуск при открытом ECHOES не считается сбоем
p = _Popen([sys.executable, "-c", "import time; time.sleep(5)"])
d.update(pid=p.pid, pending=True, fails=1); bg._save(d)
bg.enter()
check(bg.state().get("fails") == 1, "второй запуск при открытом ECHOES — не сбой")
p.kill()
shutil.rmtree(tmp, ignore_errors=True)
print("FAILED" if fails else "ALL OK", len(fails), flush=True)
sys.exit(1 if fails else 0)
