"""Small backend bridge for the C++ launcher; no UI construction or translation here."""
from __future__ import annotations

import ctypes
import json
import os
import sys
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QLockFile, QStandardPaths, qVersion
from PyQt6.QtWidgets import QApplication, QWidget

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(ROOT / 'launcher'))
import core


class Check(QThread):
    result = pyqtSignal(str)

    def run(self):
        try:
            self.result.emit(core.remote_version())
        except Exception:
            self.result.emit('')


class Job(QThread):
    progress = pyqtSignal(int, object)
    result = pyqtSignal(bool, str)

    def __init__(self, request):
        super().__init__()
        self.request = request

    def run(self):
        request = self.request
        mode = request['action']
        share = 25 if mode == 'install' else 40
        try:
            def downloaded(done, total):
                self.progress.emit(int(share * done / total) if total else -1, {'stage': 'progress.download'})

            executable = sys.executable if getattr(sys, 'frozen', False) else None
            source = core.download_source(downloaded, launcher=executable)
            self.progress.emit(share, {'stage': 'progress.unpack'})
            if mode == 'install':
                args = ['-Auto', '-InstallDir', request['target'], '-NoLaunch']
                for key, flag in (('desktop', '-NoDesktop'), ('menu', '-NoStartMenu'), ('spotify', '-NoSpotify')):
                    if not request.get(key, True):
                        args.append(flag)
                if request.get('autostart'):
                    args.append('-Autostart')
                script = source / 'setup/install.ps1'
            else:
                args = ['-Auto']
                if (source / 'setup/launcher.sha256').is_file():
                    args += ['-NoLaunch', '-InstallDir', request['target']]
                script = source / 'setup/update.ps1'
            stage = 'progress.installing' if mode == 'install' else 'progress.updating'

            def line(text):
                match = core.STEP_RE.search(text)
                pct = None
                if match:
                    step, total = map(int, match.groups()[:2])
                    pct = share + int((100 - share) * (step - 1) / max(1, total))
                self.progress.emit(pct if pct is not None else -2, {'stage': stage, 'line': text.strip()})

            code = core.run_script(script, args, line)
            if code:
                self.result.emit(False, 'error.backend')
            else:
                self.result.emit(True, '')
        except Exception as error:
            self.progress.emit(0, {'line': str(error)})
            self.result.emit(False, 'error.backend')


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    app.setApplicationName('ECHOES Launcher')
    app.setOrganizationName('ECHOES')
    lock = QLockFile(str(Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation)) / 'echoes-native-launcher.lock'))
    if not lock.tryLock(100):
        return 0
    native = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
    assets = native if getattr(sys, 'frozen', False) else ROOT / 'app/assets'
    dll = ctypes.CDLL(str(native / 'echoes_launcher.dll'))
    dll.ela_qt_version.restype = ctypes.c_char_p
    if dll.ela_qt_version().decode() != qVersion():
        raise RuntimeError('The launcher Qt runtime does not match its native UI.')
    callback_type = ctypes.CFUNCTYPE(None, ctypes.c_char_p)
    dll.ela_callback.argtypes = [callback_type]
    dll.ela_new.argtypes = [ctypes.c_char_p]
    dll.ela_new.restype = ctypes.c_void_p
    dll.ela_state.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    dll.ela_progress.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p]
    dll.ela_done.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p]
    target = core.discover()
    payload = {'target': str(target or ''), 'default': str(core.DEFAULT_DIR), 'version': core.version(target),
               'data': str(core.data_dir()),
               'icon': str((native if getattr(sys, 'frozen', False) else ROOT / 'app') / 'icon.ico'),
               'mark': str(assets / 'logo/echoes_mark.png'),
               'display_font': str(assets / 'fonts/nick/UnifrakturMaguntia-Book.ttf'),
               'ui_fonts': [str(assets / f'fonts/inter/Inter-{script}.ttf') for script in ('latin', 'cyrillic')]}
    encode = lambda value: json.dumps(value, ensure_ascii=False).encode('utf-8')
    pointer = dll.ela_new(encode(payload))
    window = sip.wrapinstance(pointer, QWidget)
    jobs = []

    def refresh():
        nonlocal target
        target = target if core.installation(target) else core.discover()
        dll.ela_state(pointer, encode({'target': str(target or ''), 'version': core.version(target)}))

    def action(raw):
        nonlocal target
        try:
            request = json.loads(raw)
            kind = request['action']
            if kind == 'refresh':
                refresh()
            elif kind == 'launch':
                core.launch(request['target'])
                dll.ela_state(pointer, encode({'status': 'home.launching'}))
                QTimer.singleShot(1000, window.close)
            elif kind == 'uninstall':
                core.uninstall(request['target'])
            elif kind in ('install', 'update'):
                job = Job(request)
                jobs.append(job)
                job.progress.connect(lambda pct, event: dll.ela_progress(pointer, pct, encode(event)))

                def done(ok, error):
                    nonlocal target
                    if ok:
                        target = Path(request['target'])
                        refresh()
                    dll.ela_done(pointer, int(ok), error.encode())
                    if ok and kind == 'install' and request.get('launch', True):
                        try:
                            core.launch(target)
                        except Exception:
                            pass
                job.result.connect(done)
                job.finished.connect(lambda: (jobs.remove(job), job.deleteLater()))
                job.start()
        except Exception as error:
            key = 'error.running' if 'уже запущен' in str(error) else 'error.missing' if 'не найден' in str(error).lower() else 'error.backend'
            dll.ela_state(pointer, encode({'status': key}))

    callback = callback_type(action)
    dll.ela_callback(callback)
    check = Check()
    check.result.connect(lambda version: dll.ela_state(pointer, encode({'remote': version,
        'newer': core.parse_version(version) > core.parse_version(core.version(target))})))
    window.show()
    check.start()
    if '--smoke-test' in sys.argv:
        output = Path(sys.argv[sys.argv.index('--smoke-test') + 1])

        def capture():
            output.parent.mkdir(parents=True, exist_ok=True)
            window.grab().save(str(output))
            window.close()

        QTimer.singleShot(1200, capture)
    result = app.exec()
    check.wait(10000)
    return result


if __name__ == '__main__':
    raise SystemExit(main())
