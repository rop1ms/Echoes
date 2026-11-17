"""Offline native UI test: languages, custom packs, geometry and persistent settings."""
import ctypes
import json
import os
from pathlib import Path
import tempfile

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt6 import sip
from PyQt6.QtCore import QSettings, QStandardPaths
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QComboBox, QLabel, QStyle, QStyleOptionButton

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / 'qa/results/launcher_native'
OUT.mkdir(parents=True, exist_ok=True)
app = QApplication([])
app.setStyle('Fusion')
temporary = tempfile.TemporaryDirectory(prefix='echoes-launcher-language-')
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, temporary.name)
dll = ctypes.CDLL(str(HERE / 'echoes_launcher.dll'))
dll.ela_new.argtypes = [ctypes.c_char_p]
dll.ela_new.restype = ctypes.c_void_p
dll.ela_validate_pack.argtypes = [ctypes.c_char_p]
dll.ela_load_pack.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
dll.ela_state.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
dll.ela_english_template.restype = ctypes.c_char_p
encode = lambda obj: json.dumps(obj, ensure_ascii=False).encode('utf-8')
assets = HERE.parents[1] / 'app/assets'
state = {'target': r'C:\Programs\ECHOES', 'version': '2026.11.03-2', 'default': r'C:\Programs\ECHOES',
         'mark': str(assets / 'logo/echoes_mark.png'),
         'display_font': str(assets / 'fonts/nick/UnifrakturMaguntia-Book.ttf'),
         'ui_fonts': [str(assets / f'fonts/inter/Inter-{script}.ttf') for script in ('latin', 'cyrillic')],
         'settings_path': str(Path(temporary.name) / 'launcher.ini')}
pointer = dll.ela_new(encode(state))
window = sip.wrapinstance(pointer, QWidget)
window.resize(980, 650)
window.show()
app.processEvents()
languages = window.findChild(QComboBox)
assert languages.currentData() == 'en'


def verify_geometry():
    for button in window.findChildren(QPushButton):
        if not button.isVisible() or len(button.text()) < 3:
            continue
        option = QStyleOptionButton()
        button.initStyleOption(option)
        rect = button.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, option, button)
        assert button.fontMetrics().horizontalAdvance(button.text()) <= rect.width() + 3, (button.text(), rect.width())


assert any(b.text() == 'Open ECHOES' for b in window.findChildren(QPushButton))
verify_geometry()
window.grab().save(str(OUT / 'launcher_en.png'))
next(b for b in window.findChildren(QPushButton) if b.text() == 'Reinstall…').click()
app.processEvents()
verify_geometry()
window.grab().save(str(OUT / 'launcher_setup_en.png'))
next(b for b in window.findChildren(QPushButton) if b.text() == 'Back').click()
app.processEvents()
languages.setCurrentIndex(languages.findData('ru'))
app.processEvents()
assert any(b.text() == 'Запустить ECHOES' for b in window.findChildren(QPushButton))
verify_geometry()
window.grab().save(str(OUT / 'launcher_ru.png'))
next(b for b in window.findChildren(QPushButton) if b.text() == 'Переустановить…').click()
app.processEvents()
verify_geometry()
window.grab().save(str(OUT / 'launcher_setup_ru.png'))
next(b for b in window.findChildren(QPushButton) if b.text() == 'Назад').click()
app.processEvents()
template = json.loads(dll.ela_english_template())
assert len(template['translations']) >= 50
assert dll.ela_validate_pack(encode(template)) == 1
valid = {'format':1, 'name':'Deutsch', 'translations':{'button.launch':'ECHOES öffnen', 'home.installed':'Installiert · {version}'}}
assert dll.ela_validate_pack(encode(valid)) == 1
for invalid in [b'not json', b'{}', encode({'format':1,'name':'Bad','translations':{'home.installed':'No placeholder'}}),
                encode({'format':1,'name':'Bad','translations':{'button.launch':7}}),
                encode({'format':1,'name':'Bad','translations':{'button.launch':'{version}'}}),
                b'x' * (256 * 1024 + 1)]:
    assert dll.ela_validate_pack(invalid) == 0
assert dll.ela_load_pack(pointer, encode(valid), 1) == 1
app.processEvents()
assert any(b.text() == 'ECHOES öffnen' for b in window.findChildren(QPushButton))
assert any(label.text() == 'Installiert · 2026.11.03-2' for label in window.findChildren(QLabel))
dll.ela_state(pointer, encode({'remote':'2026.11.03-3'}))
assert any(b.isVisible() and b.text() == 'Update to 2026.11.03-3' for b in window.findChildren(QPushButton))
dll.ela_state(pointer, encode({'version':'2026.11.03-3'}))
assert not any(b.isVisible() and b.text() == 'Update to 2026.11.03-3' for b in window.findChildren(QPushButton))
verify_geometry()
window.grab().save(str(OUT / 'launcher_custom.png'))
window.close()
sip.delete(window)
pointer2 = dll.ela_new(encode(state))
window2 = sip.wrapinstance(pointer2, QWidget)
assert window2.findChild(QComboBox).currentData() == 'custom'
assert any(b.text() == 'ECHOES öffnen' for b in window2.findChildren(QPushButton))
sip.delete(window2)
print(json.dumps({'native_ui':'C++/Qt', 'languages':['en','ru','custom'], 'template_entries':len(template['translations']),
                  'invalid_packs_rejected':6, 'custom_persistence':True, 'text_clipping':False}))
