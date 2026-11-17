"""Exercise the signed Windows player entry point with a disposable runtime."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(sys.platform == "win32", "Windows player entry point")
class PlayerIdentityTests(unittest.TestCase):
    def test_branded_executable_and_python_command_line(self):
        source = Path(__file__).resolve().parents[1] / "setup/Echoes.exe"
        runtime = Path(sys.base_prefix)
        python_dll = f"python{sys.version_info.major}{sys.version_info.minor}.dll"
        with tempfile.TemporaryDirectory(prefix="echoes-identity-") as directory:
            root = Path(directory) / "Echoes аудио"
            app = root / "app"
            python = root / "python"
            app.mkdir(parents=True)
            python.mkdir()
            for file in (runtime / "python3.dll", runtime / python_dll, *runtime.glob("vcruntime*.dll")):
                shutil.copyfile(file, python / file.name)
            stdlib_zip = runtime / Path(python_dll).with_suffix(".zip")
            stdlib = (stdlib_zip,) if stdlib_zip.is_file() else (runtime / "Lib", runtime / "DLLs")
            (python / Path(python_dll).with_suffix("._pth")).write_text(
                "".join(f"{path}\n" for path in stdlib), encoding="utf-8"
            )
            exe = python / "Echoes.exe"
            shutil.copyfile(source, exe)
            script = app / "main.py"
            script.write_text(
                "import sys\nfrom pathlib import Path\n"
                "Path('started.txt').write_text(Path(sys.executable).name, encoding='utf-8')\n",
                encoding="utf-8",
            )

            subprocess.run([exe], cwd=root, timeout=10, check=True)
            self.assertEqual((app / "started.txt").read_text("utf-8"), "Echoes.exe")

            result = subprocess.run(
                [exe, "-X", "utf8", "-c", "print(input()[::-1])"], input="тест\n".encode("utf-8"),
                capture_output=True, timeout=10, check=True,
            )
            self.assertEqual(result.stdout.decode("utf-8").strip(), "тсет")


if __name__ == "__main__":
    unittest.main(verbosity=2)
