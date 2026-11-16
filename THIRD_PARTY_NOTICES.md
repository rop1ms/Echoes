# Third-party components

The root [MIT license](LICENSE) covers ECHOES-authored source and documentation. It does not replace the licenses of dependencies, bundled libraries, fonts, codecs, imported skins, or downloaded models/media.

## Distribution of the complete application

The ordinary open-source **PyQt6** distribution is **GPLv3**, with a separate commercial licensing option; it is not LGPL. Qt itself has its own LGPL/GPL/commercial terms. Distributing a combined application with GPL dependencies requires compliance with their GPL terms. An MIT grant for the original ECHOES files does not make an assembled PyQt6 application MIT-only. See [Riverbank's license description](https://riverbankcomputing.com/software/pyqt/intro) and [license FAQ](https://riverbankcomputing.com/commercial/license-faq).

The native runtime carries notices and license texts under [`app/montage_native/licenses/`](app/montage_native/licenses/). Keep that directory with the runtime. Build sources for ECHOES' native editor, audio, and visual effects are included under `tools/`. Qt/MSYS2 components remain separately licensed; corresponding upstream source must be supplied or made available as required when distributing binaries.

## Main dependencies

| Component | Role | Upstream licensing |
| --- | --- | --- |
| [Python](https://www.python.org/) | Private interpreter downloaded by setup | PSF license |
| [PyQt6](https://riverbankcomputing.com/software/pyqt/intro) | Python UI bindings | GPLv3 / commercial |
| [Qt](https://doc.qt.io/qt-6/licensing.html) | UI and native editor runtime | LGPLv3 / GPL / commercial; module-specific terms |
| [VLC / libVLC](https://www.videolan.org/legal.html), python-vlc | Playback, decoding, music videos | Component-specific GPL/LGPL; libVLC LGPLv2.1+ |
| [FFmpeg](https://ffmpeg.org/legal.html) | Conversion, editing, export | LGPL/GPL depending on build and enabled components |
| NumPy / SciPy | Audio analysis and signal processing | BSD-style; bundled library notices also apply |
| mutagen | Tags and cover metadata | GPLv2-or-later |
| requests | HTTP client | Apache-2.0 |
| yt-dlp | Supported-source extraction and downloads | Unlicense for core; dependency and executable-bundle notices apply |
| ytmusicapi / spotDL | Online music and playlist integrations | MIT; dependency notices apply |
| syncedlyrics / lyricsgenius / Beautiful Soup | Lyrics lookup | MIT |
| Pillow | Images, animated images, artwork | MIT-CMU and bundled library notices |
| pypresence / python-sounddevice | Discord integration / audio output | MIT |
| PyCryptodomex | Network cryptography | BSD/public-domain component terms |
| websockets / PyAV | Network and audio/video integration | BSD-style; linked FFmpeg licenses also apply |
| PyWinRT packages | Windows integration | MIT |
| faster-whisper / CTranslate2 | Optional local speech recognition | MIT; each model has its own license |
| psutil / PyInstaller | Launcher build and process management | BSD-3-Clause / GPL with bootloader exception |
| MSYS2 runtime libraries | Native editor dependencies | Individual notices bundled with the native runtime |

Check the license shipped with the exact installed version of each dependency. The installer retrieves third-party binaries separately; this source package does not contain a private Python, VLC, or FFmpeg installation.

## Artwork, symbols, reactions, and user assets

The ECHOES icon, drawn UI symbols, and original demonstration cover artwork are project assets. The screenshots use generated demo data and contain no bundled commercial recordings. The `EchoesSymbols.ttf` UI font is generated from ECHOES' own vector drawings.

The Phantom-style interface (`app/ph_*.py`) bundles:

| Asset | Location | License |
| --- | --- | --- |
| [Inter](https://github.com/rsms/inter) 4.001, split into Latin / Cyrillic / Greek subsets, families renamed `Inter PA*` | `app/assets/fonts/inter/` | SIL Open Font License 1.1 — [`app/assets/licenses/Inter-OFL.txt`](app/assets/licenses/Inter-OFL.txt) |
| [Lucide](https://lucide.dev) icon outlines | `app/ph_icons_data.py` | ISC (some icons MIT, from Feather) — [`app/assets/licenses/lucide-LICENSE.txt`](app/assets/licenses/lucide-LICENSE.txt) |
| Phantom Audio default background | `app/assets/ph/background.jpg` | Phantom Audio, same author as ECHOES |

Emoji used for reactions are independent of the UI symbol font. The reaction asset loader can obtain Noto Emoji / other emoji artwork; retain the relevant upstream notices (for example, [Noto Emoji](https://github.com/googlefonts/noto-emoji)) for any redistributed assets. Downloaded artist artwork, lyrics, music, videos, osu! maps/skins, and user-imported themes are not relicensed by this repository. Only redistribute material you have permission to redistribute.

## Русский

MIT относится к авторским файлам ECHOES. Сторонние компоненты сохраняют свои лицензии. Обычная версия PyQt6 распространяется по GPLv3, а Qt и FFmpeg имеют собственные условия. При распространении собранного приложения нужно соблюдать условия входящих GPL/LGPL-компонентов; MIT в корне репозитория их не заменяет. Лицензии нативной среды находятся в `app/montage_native/licenses/`.
