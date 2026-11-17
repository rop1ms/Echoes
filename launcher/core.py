"""ECHOES Launcher core: find the installation, talk to GitHub, run the bundled installer / updater.
Never touches the user's music or the data folder (~/Echoes)."""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import psutil

REPO = "rop1ms/Echoes"
BRANCH = "main"
VERSION_URL = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/app/version.txt"
ZIP_URL = f"https://codeload.github.com/{REPO}/zip/refs/heads/{BRANCH}"
RELEASE_URL = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/release/stable.json"
COMMIT_ZIP_URL = f"https://codeload.github.com/{REPO}/zip/{{commit}}"
APP_ZIP_URL = f"https://github.com/{REPO}/releases/download/v{{tag}}/ECHOES.App.zip"


def _release_sign():
    """Проверка подписи автора (app/release_sign.py; в exe — вшит при сборке)."""
    try:
        import release_sign
    except ImportError:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
        import release_sign
    return release_sign


def release() -> dict:
    """Подписанный стабильный выпуск: версия, коммит и отпечатки файлов. Подпись не сошлась — ошибка."""
    req = urllib.request.Request(RELEASE_URL, headers={"User-Agent": "ECHOES-Launcher"})
    with urllib.request.urlopen(req, timeout=10) as r:
        m = json.loads(r.read().decode("utf-8"))
    if not _release_sign().verify(m):
        raise RuntimeError("подпись выпуска не прошла проверку — установка отменена")
    return m
DEFAULT_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Programs" / "ECHOES"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def data_dir() -> Path:
    new, old = Path.home() / "Echoes", Path.home() / ".neon_player"
    return new if new.exists() or not old.exists() else old


def accent() -> str:
    """Акцент темы пользователя (если ECHOES уже стоит) — лаунчер в тех же цветах."""
    try:
        s = json.loads((data_dir() / "settings.json").read_text("utf-8-sig"))
        a = str((s.get("ya_skin") or {}).get("accent") or "")
        if re.fullmatch(r"#[0-9a-fA-F]{6}", a):
            return a
    except (OSError, ValueError):
        pass
    return "#ffdb1a"


def installation(path):
    try:
        p = Path(path).resolve()
    except (OSError, TypeError, ValueError):
        return False
    return (p / "app/main.py").is_file() and (p / "python/pythonw.exe").is_file()


def discover():
    candidates = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ECHOES") as k:
            candidates.append(Path(winreg.QueryValueEx(k, "InstallLocation")[0]))
    except OSError:
        pass
    candidates.append(DEFAULT_DIR)
    return next((p for p in candidates if installation(p)), None)


def version(folder):
    try:
        return (Path(folder) / "app/version.txt").read_text("utf-8-sig").strip()[:80]
    except (OSError, TypeError):
        return ""


def parse_version(s) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", str(s or ""))[:6])


def remote_version(timeout=8) -> str:
    return str(release().get("version") or "")


def running(root):
    root = Path(root).resolve()
    for p in psutil.process_iter(["exe", "cmdline"]):
        try:
            exe = p.info["exe"]
            if exe and Path(exe).resolve().is_relative_to(root / "python"):
                return True
            if any(Path(a).resolve() == root / "app/main.py" for a in (p.info["cmdline"] or []) if a.endswith("main.py")):
                return True
        except (OSError, ValueError, psutil.Error):
            continue
    return False


def launch(root):
    root = Path(root).resolve()
    if not installation(root):
        raise ValueError("ECHOES не найден в этой папке.")
    if running(root):
        raise ValueError("ECHOES уже запущен — его окно или значок в трее.")
    return subprocess.Popen([str(root / "python/pythonw.exe"), str(root / "app/main.py")], cwd=root / "app")


def _download_archive(url, zpath, progress, cancel):
    req = urllib.request.Request(url, headers={"User-Agent": "ECHOES-Launcher"})
    with urllib.request.urlopen(req, timeout=30) as r, open(zpath, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if cancel():
                raise RuntimeError("отменено")
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            progress(done, total)


def download_source(progress=lambda done, total: None, cancel=lambda: False, launcher=None) -> Path:
    """Download and verify the signed release, reusing the running EXE when its hash matches."""
    manifest = release()
    base = Path(tempfile.mkdtemp(prefix="echoes-launcher-"))
    zpath = base / "package.zip"
    expected = manifest.get("launcher_sha256")
    compact = False
    try:
        if expected and launcher:
            with Path(launcher).open("rb") as f:
                reuse_launcher = hashlib.file_digest(f, "sha256").hexdigest() == expected
            if reuse_launcher:
                tag = urllib.parse.quote(manifest["version"], safe="")
                try:
                    _download_archive(APP_ZIP_URL.format(tag=tag), zpath, progress, cancel)
                    compact = True
                except urllib.error.URLError:
                    # The signed manifest can reach GitHub before the asset finishes publishing.
                    pass
        if not compact:
            _download_archive(COMMIT_ZIP_URL.format(commit=manifest["commit"]), zpath, progress, cancel)

        src = base / "source"
        with zipfile.ZipFile(zpath) as archive:
            roots = set()
            for name in archive.namelist():
                parts = name.rstrip("/").split("/")
                if not all(parts) or ".." in parts or "." in parts or "\\" in name or ":" in name:
                    raise RuntimeError("подозрительный путь в архиве")
                roots.add(parts[0])
            if len(roots) != 1:
                raise RuntimeError("неверная структура архива")
            archive.extractall(src)
            src /= roots.pop()
        zpath.unlink()
        if not (src / "app/main.py").is_file() or not (src / "setup/install.ps1").is_file():
            raise RuntimeError("в архиве нет программы")
        problems = _release_sign().check_tree(src, manifest)
        if problems:
            raise RuntimeError("файлы не совпали с подписью автора: " + "; ".join(problems[:3]))
        if compact:
            shutil.copyfile(launcher, src / "ECHOES Launcher.exe")
        return src
    except BaseException:
        shutil.rmtree(base, ignore_errors=True)
        raise


STEP_RE = re.compile(r"\[(\d+)/(\d+)\]\s*(.*)")


def run_script(script: Path, args, on_line, cancel=lambda: False) -> int:
    """PowerShell-скрипт установки/обновления без окна консоли; каждая строка вывода → on_line(text)."""
    cmd = ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)] + list(args)
    p = subprocess.Popen(cmd, cwd=str(script.parent.parent), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
    for raw in iter(p.stdout.readline, b""):
        if cancel():
            p.kill()
            break
        line = raw.decode("utf-8", "replace").rstrip()
        line = re.sub(r"\x1b\[[0-9;]*m", "", line)
        if line.strip():
            on_line(line)
    return p.wait()


def uninstall(root):
    script = Path(root) / "uninstall.ps1"
    if not script.is_file():
        raise ValueError("Удаление не найдено в папке ECHOES.")
    subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
