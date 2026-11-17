"""Онлайн-поиск: строки «Альбомы» и «Публичные плейлисты», треклист плейлиста с «Сохранить как плейлист»;
перенос плейлистов: площадка по ссылке; выбор языка перевода вместо кода. Без сети (данные подставные).

python qa/test_search_releases.py [папка-для-картинок]
"""
import sys
from pathlib import Path
from unittest.mock import patch

source = Path(__file__).with_name('ui_smoke.py').read_text('utf-8')
exec(compile(source.split('win = None')[0], str(Path(__file__).with_name('ui_smoke.py')), 'exec'))
import main, ui_anim
from PyQt6.QtWidgets import QComboBox, QLabel, QPushButton

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else None
main.WindowsMediaKeyFilter.register = lambda self: None
fails = []


def check(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg, flush=True)
    if not cond:
        fails.append(msg)


import platform_import as pi
for url, want in [('https://soundcloud.com/forss/sets/soulhack', 'soundcloud'),
                  ('https://on.soundcloud.com/abc', 'soundcloud'),
                  ('https://music.youtube.com/playlist?list=PL1', 'ytmusic'),
                  ('https://www.youtube.com/playlist?list=PL1', 'youtube'),
                  ('https://www.deezer.com/ru/playlist/3155776842', 'deezer'),
                  ('https://deezer.page.link/xyz', 'deezer'),
                  ('https://music.apple.com/us/playlist/x/pl.1', 'apple'),
                  ('https://open.spotify.com/playlist/37i9', 'spotify'),
                  ('https://music.yandex.ru/users/a/playlists/3', 'yandex'),
                  ('https://vk.com/music/playlist/1_2', 'vk'),
                  ('https://example.com/x', '')]:
    check(pi.detect(url) == want, f'площадка по ссылке: {url} → {want or "нет"}')
check(pi._clean('Song (Official Music Video)') == 'Song', 'хвост «Official Video» убирается')

win = main.MainWindow()
win.resize(1500, 950)
win.show(); settle(.6)
shell = win._ya
from ya_online import OnlineResults
shell.show_page('search'); ui_anim._finish(shell.stack); settle(.3)
res = OnlineResults(shell)
albums = [{'title': f'Альбом {i}', 'artist': 'Daft Punk', 'year': '2013', 'type': 'Album', 'browseId': f'MPREb_{i}',
           'src': 'ytm', 'thumb_url': ''} for i in range(5)]
playlists = [{'title': f'Плейлист {i}', 'artist': 'user', 'type': 'Плейлист', 'src': 'ytm' if i % 2 else 'sc',
              'ytm_pl': f'PL{i}' if i % 2 else None, 'sc_id': None if i % 2 else 100 + i, 'count': '20',
              'thumb_url': ''} for i in range(6)]
tracks = [{'title': f'Трек {i}', 'artist': 'Daft Punk', 'url': f'https://music.youtube.com/watch?v={i}',
           'thumb_url': '', 'source': 'ytm', 'duration': 200} for i in range(3)]
win.settings["stream_default"] = True
with patch.object(win.streams, "prefetch") as prefetch:
    res._show('daft punk', {'tracks': tracks, 'artists': [], 'albums': albums, 'playlists': playlists, 'errors': []})
check(prefetch.call_count == 3, 'для первых трёх треков запланирована подготовка потока')
heads = [l.text() for l in res.findChildren(QLabel)]
check(any('Альбомы' in h for h in heads), 'строка «Альбомы» есть')
check(any('Публичные плейлисты' in h for h in heads), 'строка «Публичные плейлисты» есть')
check('5 альбомов, 6 плейлистов' in res.status.text(), 'счётчик в статусе: ' + res.status.text())
if OUT:
    OUT.mkdir(parents=True, exist_ok=True)
    res.resize(1100, 900); res.show(); settle(.4)
    res.grab().save(str(OUT / 'search_rows.png'))
    res.hide()

from ya_online import ReleasePage
page = ReleasePage(shell)
page.rel = {'title': 'Плейлист 1', 'type': 'Плейлист'}
page.artist = 'user'
page._render_album({'title': 'Плейлист 1', 'type': 'Плейлист', 'tracks': tracks}, loading=False)
btns = [b.text().strip() for b in page.findChildren(QPushButton)]
check('Сохранить как плейлист' in btns, 'у плейлиста — «Сохранить как плейлист»')
page._render_album({'title': 'Альбом', 'type': 'Album', 'tracks': tracks}, loading=False)
btns = [b.text().strip() for b in page.findChildren(QPushButton) if b.isVisibleTo(page)]
check('Скачать альбом' in btns, 'у альбома — «Скачать альбом»')

box = win._lyrics_options.build()
combo = box.findChildren(QComboBox)
langs = [c for c in combo if c.findData('en') >= 0 and c.findData('ja') >= 0]
check(bool(langs), 'язык перевода выбирается из списка')
if langs:
    check(langs[0].currentText() == 'Русский', 'по умолчанию — Русский: ' + langs[0].currentText())

from spotify_import import SpotifyImportDialog
dlg = SpotifyImportDialog(win, provider='auto')
chips = [b.text() for b in dlg.findChildren(QPushButton) if b.objectName() == 'YaChip']
check({'SoundCloud', 'YouTube Music', 'Deezer', 'Apple Music', 'Spotify'} <= set(chips), 'площадки в окне переноса: ' + ', '.join(chips))
print('FAILED' if fails else 'ALL OK', len(fails))
win.close()
sys.exit(1 if fails else 0)
