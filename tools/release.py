"""Выпуск ECHOES: подписать текущий коммит и отдать его людям (каналы stable / beta).

    py tools/release.py --init-key          один раз: создать ключ автора (и вписать открытый ключ в программу)
    py tools/release.py beta  [--notes ...] друзьям-тестерам
    py tools/release.py stable [--notes ...] всем (beta тоже получит, если у неё версия старее)

Что делает: проверяет, что всё закоммичено и уже на GitHub; берёт файлы app/ и setup/ ровно из этого коммита
(git archive — то же, что скачает обновлятор), считает их SHA-256, подписывает закрытым ключом и кладёт
release/<канал>.json; коммит и push. Пуш в main без этого шага никого не обновляет.

Закрытый ключ: %USERPROFILE%\\.echoes_release\\release_ed25519.key — НЕ в репозитории. Сделайте копию
(флешка / менеджер паролей): без ключа новые выпуски не подписать, а значит, не выпустить.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import release_sign as rs  # noqa: E402

KEY_PATH = Path(os.environ.get("ECHOES_RELEASE_KEY") or (Path.home() / ".echoes_release" / "release_ed25519.key"))


def parse_version(s) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", str(s or ""))[:6])


def git(*args, binary=False):
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True)
    return out.stdout if binary else out.stdout.decode("utf-8", "replace").strip()


def init_key():
    if KEY_PATH.exists():
        sys.exit(f"Ключ уже есть: {KEY_PATH}. Новый не создаю — иначе старые программы перестанут принимать выпуски.")
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    seed = os.urandom(32)
    KEY_PATH.write_text(seed.hex(), "utf-8")
    pub = rs.public_hex(seed)
    src = ROOT / "app" / "release_sign.py"
    s = src.read_text("utf-8")
    s = re.sub(r'PUBLIC_KEY_HEX = "[^"]*"', f'PUBLIC_KEY_HEX = "{pub}"', s, count=1)
    src.write_text(s, "utf-8")
    print(f"Ключ создан: {KEY_PATH}\nОткрытый ключ вписан в app/release_sign.py: {pub}\n"
          "СДЕЛАЙТЕ КОПИЮ файла ключа — без него выпуски не подписать.")


def manifest_for(commit: str, channel: str, notes: str) -> dict:
    # концы строк — как в архиве GitHub (без autocrlf Windows: иначе 95 текстовых файлов не совпали бы)
    tar = git("-c", "core.autocrlf=false", "-c", "core.eol=lf", "archive", "--format=tar", commit, "app", "setup",
              binary=True)
    files = {}
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        for m in t.getmembers():
            if m.isfile() and rs.covered(m.name):
                files[m.name] = rs.sha256(t.extractfile(m).read())
    ver = git("show", f"{commit}:app/version.txt").strip()
    result = {"version": ver, "commit": commit, "channel": channel, "notes": notes[:2000], "ts": int(time.time()),
              "files": files}
    if "setup/launcher.sha256" in files:
        expected = git("show", f"{commit}:setup/launcher.sha256").lower()
        launcher = git("show", f"{commit}:ECHOES Launcher.exe", binary=True)
        if rs.sha256(launcher) != expected:
            raise RuntimeError("Run tools/build_launcher.ps1 and commit the launcher with its checksum.")
        result["launcher_sha256"] = expected
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("channel", nargs="?", choices=rs.CHANNELS)
    ap.add_argument("--init-key", action="store_true")
    ap.add_argument("--notes", default="")
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()
    if a.init_key:
        return init_key()
    if not a.channel:
        ap.error("укажите канал: stable или beta")
    if not KEY_PATH.exists():
        sys.exit(f"Нет ключа автора ({KEY_PATH}). Один раз: py tools/release.py --init-key")
    seed = bytes.fromhex(KEY_PATH.read_text("utf-8").strip())
    if rs.public_hex(seed) != rs.PUBLIC_KEY_HEX:
        sys.exit("Ключ не совпадает с открытым ключом в app/release_sign.py — выпуск не будет принят программами.")
    if git("status", "--porcelain", "--", "app", "setup"):
        sys.exit("В app/ или setup/ есть незакоммиченные изменения — сначала коммит и push.")
    git("fetch", "-q", "origin")
    head = git("rev-parse", "HEAD")
    if not a.no_push and git("rev-parse", "origin/main") != head:
        sys.exit("Текущий коммит ещё не на GitHub (или отстаёт) — сначала git pull --ff-only и git push.")
    notes = a.notes or "\n".join(l for l in git("log", "-1", "--format=%B", head).splitlines()
                                 if l.strip() and not l.startswith("Co-Authored-By"))[:2000]
    rel = ROOT / "release"
    rel.mkdir(exist_ok=True)
    channels = [a.channel]
    if a.channel == "stable":                     # бета не должна отставать от стабильной
        try:
            beta = json.loads((rel / "beta.json").read_text("utf-8"))
            if parse_version(beta.get("version")) <= parse_version(git("show", f"{head}:app/version.txt")):
                channels.append("beta")
        except (OSError, ValueError):
            channels.append("beta")
    for ch in channels:
        m = rs.sign(manifest_for(head, ch, notes), seed)
        assert rs.verify(m), "подпись не проверилась"
        (rel / f"{ch}.json").write_text(json.dumps(m, ensure_ascii=False, indent=1, sort_keys=True), "utf-8")
        print(f"{ch}: {m['version']} ({head[:7]}), файлов {len(m['files'])}")
    git("add", "release")
    git("commit", "-q", "-m", f"release {git('show', f'{head}:app/version.txt')} → {', '.join(channels)}")
    if not a.no_push:
        git("push", "-q")
        print("Опубликовано.")


if __name__ == "__main__":
    main()
