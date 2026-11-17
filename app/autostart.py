# autostart.py
import os
import sys
import platform
import subprocess
from pathlib import Path

APP_NAME = "NeonPlayer"
ROOT = Path(__file__).resolve().parent
MAIN = ROOT / "main.py"


def _python_exe() -> str:
    if platform.system() == "Windows":
        player = ROOT.parent / "python" / "Echoes.exe"
        if player.is_file():
            return str(player)
        pw = Path(sys.executable).with_name("pythonw.exe")
        if pw.exists():
            return str(pw)
    return sys.executable


def _win_startup_dir() -> Path:
    return Path(os.getenv("APPDATA")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def install_windows():
    target_dir = _win_startup_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    vbs = target_dir / f"{APP_NAME}.vbs"
    py = _python_exe()
    vbs.write_text(
        'Set sh = CreateObject("WScript.Shell")\n'
        f'sh.Run """{py}"" ""{MAIN}""", 0, False\n',
        encoding="utf-16",
    )
    print(f"[+] Автозапуск добавлен: {vbs}")


def uninstall_windows():
    vbs = _win_startup_dir() / f"{APP_NAME}.vbs"
    if vbs.exists():
        vbs.unlink()
        print(f"[-] Удалено: {vbs}")
    else:
        print("[i] Не найдено.")


def _linux_desktop_path() -> Path:
    return Path.home() / ".config" / "autostart" / f"{APP_NAME.lower()}.desktop"


def install_linux():
    p = _linux_desktop_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        f'Exec="{sys.executable}" "{MAIN}"\n'
        "X-GNOME-Autostart-enabled=true\n"
        "Terminal=false\n",
        encoding="utf-8",
    )
    p.chmod(0o755)
    print(f"[+] Автозапуск добавлен: {p}")


def uninstall_linux():
    p = _linux_desktop_path()
    if p.exists():
        p.unlink()
        print(f"[-] Удалено: {p}")
    else:
        print("[i] Не найдено.")


def _mac_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"com.{APP_NAME.lower()}.plist"


def install_mac():
    p = _mac_plist_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.{APP_NAME.lower()}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{sys.executable}</string>
    <string>{MAIN}</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
</dict>
</plist>
""", encoding="utf-8")
    subprocess.run(["launchctl", "load", str(p)], check=False)
    print(f"[+] Автозапуск добавлен: {p}")


def uninstall_mac():
    p = _mac_plist_path()
    if p.exists():
        subprocess.run(["launchctl", "unload", str(p)], check=False)
        p.unlink()
        print(f"[-] Удалено: {p}")
    else:
        print("[i] Не найдено.")


def install():
    s = platform.system()
    if s == "Windows":
        install_windows()
    elif s == "Linux":
        install_linux()
    elif s == "Darwin":
        install_mac()
    else:
        print(f"[!] Неизвестная ОС: {s}")


def uninstall():
    s = platform.system()
    if s == "Windows":
        uninstall_windows()
    elif s == "Linux":
        uninstall_linux()
    elif s == "Darwin":
        uninstall_mac()
    else:
        print(f"[!] Неизвестная ОС: {s}")


def status():
    s = platform.system()
    if s == "Windows":
        p = _win_startup_dir() / f"{APP_NAME}.vbs"
    elif s == "Linux":
        p = _linux_desktop_path()
    elif s == "Darwin":
        p = _mac_plist_path()
    else:
        print("Неизвестная ОС")
        return
    print(f"Файл автозапуска: {p}")
    print("Статус:", "УСТАНОВЛЕН" if p.exists() else "не установлен")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "install"
    if cmd == "install":
        install()
    elif cmd == "uninstall":
        uninstall()
    elif cmd == "status":
        status()
    else:
        print("Команды: install | uninstall | status")
