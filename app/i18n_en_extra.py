# i18n_en_extra.py
"""Дополнение словаря английского интерфейса (i18n_en.py): строки, которых там не было —
студия, конструктор тем, клипы, микшер и т. д. Подключается в i18n._load()."""

EXACT = {'отменено': 'cancelled',
 'Картинки (*.png *.jpg *.jpeg *.gif *.webp *.bmp)': 'Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp)',
 'Квадрат': 'Square',
 'Широкая 2:1': 'Wide 2:1',
 'Высокая 1:2': 'Tall 1:2',
 'Полоска 4:1': 'Strip 4:1',
 'Таблетка': 'Pill',
 'Без фона': 'No background',
 'Следующий трек': 'Next track',
 'Предыдущий трек': 'Previous track',
 'Клип песни': 'Song video',
 'Звук вкл / выкл': 'Sound on / off',
 'Полный экран': 'Full screen',
 'Скачать музыку': 'Download music',
 'Меню тем': 'Themes menu',
 'Без действия (украшение)': 'No action (decoration)',
 'Выбрать и двигать (колесо — размер, Del — удалить)': 'Select and move (wheel — size, Del — delete)',
 'Кисть': 'Brush',
 'Ластик': 'Eraser',
 'Надпись: щёлкните на холсте': 'Text: click on the canvas',
 'Картинка из файла': 'Image from file',
 '// кнопка из редактора кнопок (вид — «Изменить вид кнопки…»)': '// button from the button editor (look — “Edit '
                                                                 'button look…”)',
 'Кнопка': 'Button',
 'Редактор кнопки — ECHOES': 'Button editor — ECHOES',
 'Редактор кнопки': 'Button editor',
 'Цвет кисти и надписей (и выбранного элемента)': 'Brush and text color (and the selected item)',
 'Второй цвет градиента (правая кнопка мыши — убрать)': 'Second gradient color (right click — remove)',
 'Обрезать рисунок по форме': 'Clip the drawing to the shape',
 'Наверх': 'Up',
 'Вниз': 'Down',
 'Увеличивается при наведении': 'Grows on hover',
 'Очистить рисунок': 'Clear drawing',
 '✥ — выбрать и двигать, угол рамки или колесо — размер, Del — удалить, стрелки — сдвиг. Цвет: сначала выберите элемент, потом цвет. Правая кнопка по образцу цвета — «нет».': '✥ '
                                                                                                                                                                               '— '
                                                                                                                                                                               'select '
                                                                                                                                                                               'and '
                                                                                                                                                                               'move, '
                                                                                                                                                                               'frame '
                                                                                                                                                                               'corner '
                                                                                                                                                                               'or '
                                                                                                                                                                               'wheel '
                                                                                                                                                                               '— '
                                                                                                                                                                               'size, '
                                                                                                                                                                               'Del '
                                                                                                                                                                               '— '
                                                                                                                                                                               'delete, '
                                                                                                                                                                               'arrows '
                                                                                                                                                                               '— '
                                                                                                                                                                               'nudge. '
                                                                                                                                                                               'Color: '
                                                                                                                                                                               'select '
                                                                                                                                                                               'an '
                                                                                                                                                                               'item '
                                                                                                                                                                               'first, '
                                                                                                                                                                               'then '
                                                                                                                                                                               'a '
                                                                                                                                                                               'color. '
                                                                                                                                                                               'Right '
                                                                                                                                                                               'click '
                                                                                                                                                                               'on '
                                                                                                                                                                               'a '
                                                                                                                                                                               'color '
                                                                                                                                                                               'swatch '
                                                                                                                                                                               '— '
                                                                                                                                                                               '“none”.',
 'Картинка на кнопку': 'Image on the button',
 'Текст на кнопке:': 'Button text:',
 'Показывать редактор вкладкой внутри конструктора или отдельным окном': 'Show the editor as a tab inside the '
                                                                         'constructor or as a separate window',
 'Обновить кнопку': 'Update button',
 'Добавить кнопку в тему': 'Add button to the theme',
 'Кисть и текст': 'Brush and text',
 'Символы': 'Symbols',
 'Добавить символ на кнопку': 'Add a symbol to the button',
 'Выбранный элемент': 'Selected item',
 'Что делает': 'Action',
 'Отдельным окном': 'Separate window',
 'Встроить': 'Embed',
 'Холст': 'Canvas',
 'Форма': 'Shape',
 'Заливка': 'Fill',
 'Толщина кисти': 'Brush size',
 'караоке': 'karaoke',
 'реакция': 'reaction',
 'концерт': 'concert',
 'урок': 'lesson',
 'разбор': 'breakdown',
 'клип': 'music video',
 'Синхронизирую с треком…': 'Syncing with the track…',
 'Ищу официальный клип…': 'Looking for the official video…',
 'Скачиваю клип…': 'Downloading the video…',
 'Собираю видео…': 'Assembling the video…',
 'Официальный клип не найден': 'Official video not found',
 'Калейдоскоп': 'Kaleidoscope',
 'Зеркало ×4': 'Mirror ×4',
 'Волны': 'Waves',
 'Плавление': 'Melt',
 'Бесконечность': 'Infinity',
 'Пульс-зум': 'Pulse zoom',
 'Пиксели': 'Pixels',
 'RGB-сдвиг': 'RGB shift',
 'Двоение': 'Double vision',
 'Радуга': 'Rainbow',
 'Кислота': 'Acid',
 'Тепловизор': 'Thermal camera',
 'Неон-контуры': 'Neon edges',
 'Постер': 'Poster',
 'Соляризация': 'Solarize',
 'Шлейф': 'Trail',
 'Туннель': 'Tunnel',
 'Негатив на бит': 'Negative on beat',
 'Мигающий негатив': 'Flashing negative',
 'Стробоскоп': 'Strobe',
 'Кошмар эпилептика': 'Epileptic nightmare',
 'Кислотный трип': 'Acid trip',
 'Сон наяву': 'Waking dream',
 'Кассета 1989': 'Cassette 1989',
 'Хищник': 'Predator',
 'Аркада': 'Arcade',
 'Бездна': 'Abyss',
 'Цифровой мир': 'Digital world',
 'МИКШЕР': 'MIXER',
 'Звук клипа': 'Video sound',
 'Звук клипа — дорожка самого видео (вступления, сценки).\nВместе с музыкой песня может звучать дважды.': 'Video '
                                                                                                          'sound — '
                                                                                                          'the '
                                                                                                          "video's "
                                                                                                          'own audio '
                                                                                                          'track '
                                                                                                          '(intros, '
                                                                                                          'skits).\n'
                                                                                                          'Together '
                                                                                                          'with the '
                                                                                                          'music the '
                                                                                                          'song may '
                                                                                                          'play '
                                                                                                          'twice.',
 'Микшер: громкость музыки и звука клипа': 'Mixer: music and video sound volume',
 'Скачать клип': 'Download video',
 'Найти и скачать официальный клип этой песни': 'Find and download the official video of this song',
 'Другой ▾': 'Other ▾',
 'Выбрать другой ролик из найденных или удалить этот': 'Pick another of the found videos or delete this one',
 'Психоделические эффекты поверх клипа (E)': 'Psychedelic effects over the video (E)',
 'Закрыть клип (Esc)': 'Close video (Esc)',
 'Играть / пауза (пробел)': 'Play / pause (space)',
 'Сдвиг клипа относительно песни': 'Video offset relative to the song',
 'Подобрать сдвиг заново по звуку': 'Re-detect the offset by sound',
 'ЭФФЕКТЫ': 'EFFECTS',
 'НАБОРЫ': 'PRESETS',
 'Выключить все эффекты': 'Turn off all effects',
 'Скачать официальный клип': 'Download the official video',
 'Найти заново': 'Search again',
 'Слушаю клип и трек…': 'Listening to the video and the track…',
 'Вспышки': 'Flashes',
 'Этот эффект — быстрые мигания и вспышки света.\n\nОни могут вызвать приступ у людей со светочувствительной эпилепсией и неприятны многим. Если вам или кому-то рядом это опасно — не включайте.\n\nВключить вспышки?': 'This '
                                                                                                                                                                                                                         'effect '
                                                                                                                                                                                                                         'has '
                                                                                                                                                                                                                         'fast '
                                                                                                                                                                                                                         'flickering '
                                                                                                                                                                                                                         'and '
                                                                                                                                                                                                                         'flashes '
                                                                                                                                                                                                                         'of '
                                                                                                                                                                                                                         'light.\n'
                                                                                                                                                                                                                         '\n'
                                                                                                                                                                                                                         'They '
                                                                                                                                                                                                                         'can '
                                                                                                                                                                                                                         'trigger '
                                                                                                                                                                                                                         'seizures '
                                                                                                                                                                                                                         'in '
                                                                                                                                                                                                                         'people '
                                                                                                                                                                                                                         'with '
                                                                                                                                                                                                                         'photosensitive '
                                                                                                                                                                                                                         'epilepsy '
                                                                                                                                                                                                                         'and '
                                                                                                                                                                                                                         'are '
                                                                                                                                                                                                                         'unpleasant '
                                                                                                                                                                                                                         'for '
                                                                                                                                                                                                                         'many. '
                                                                                                                                                                                                                         'If '
                                                                                                                                                                                                                         'this '
                                                                                                                                                                                                                         'is '
                                                                                                                                                                                                                         'dangerous '
                                                                                                                                                                                                                         'for '
                                                                                                                                                                                                                         'you '
                                                                                                                                                                                                                         'or '
                                                                                                                                                                                                                         'someone '
                                                                                                                                                                                                                         'nearby '
                                                                                                                                                                                                                         '— '
                                                                                                                                                                                                                         "don't "
                                                                                                                                                                                                                         'turn '
                                                                                                                                                                                                                         'it '
                                                                                                                                                                                                                         'on.\n'
                                                                                                                                                                                                                         '\n'
                                                                                                                                                                                                                         'Turn '
                                                                                                                                                                                                                         'on '
                                                                                                                                                                                                                         'flashes?',
 'ECHOES — КЛИП': 'ECHOES — VIDEO',
 'Искать снова': 'Search again',
 'Удалить скачанный клип': 'Delete the downloaded video',
 'Не получилось открыть видео (нет VLC?)': "Couldn't open the video (no VLC?)",
 'Быстрые вспышки!': 'Fast flashes!',
 'Ничего не играет': 'Nothing is playing',
 'По звуку подобрать не вышло — подвиньте −/+': "Couldn't match by sound — adjust with −/+",
 'Официальный клип не нашёлся — можно выбрать ролик вручную': 'Official video not found — you can pick a video '
                                                              'manually',
 'Клип ещё не скачан': 'Video not downloaded yet',
 'трек, чей голос взять…': 'track to take the vocals from…',
 'Поменять местами': 'Swap',
 'трек, чью музыку взять…': 'track to take the music from…',
 'Схема: сам решит': 'Layout: let the bot decide',
 'По песне вокала': 'Follow the vocal song',
 'По структуре бита': 'Follow the beat structure',
 'Оба целиком': 'Both in full',
 'По песне вокала — голос идёт как в оригинале, под ним меняются части бита.\nПо структуре бита — части бита по порядку, на них вокал той же роли.\nОба целиком — бит и вокал как в оригиналах, без нарезки: бот выбирает только,\nгде вступить голосу, чтобы припев лёг на припев.': 'Follow '
                                                                                                                                                                                                                                                                                      'the '
                                                                                                                                                                                                                                                                                      'vocal '
                                                                                                                                                                                                                                                                                      'song '
                                                                                                                                                                                                                                                                                      '— '
                                                                                                                                                                                                                                                                                      'the '
                                                                                                                                                                                                                                                                                      'vocals '
                                                                                                                                                                                                                                                                                      'go '
                                                                                                                                                                                                                                                                                      'as '
                                                                                                                                                                                                                                                                                      'in '
                                                                                                                                                                                                                                                                                      'the '
                                                                                                                                                                                                                                                                                      'original, '
                                                                                                                                                                                                                                                                                      'beat '
                                                                                                                                                                                                                                                                                      'sections '
                                                                                                                                                                                                                                                                                      'change '
                                                                                                                                                                                                                                                                                      'underneath.\n'
                                                                                                                                                                                                                                                                                      'Follow '
                                                                                                                                                                                                                                                                                      'the '
                                                                                                                                                                                                                                                                                      'beat '
                                                                                                                                                                                                                                                                                      'structure '
                                                                                                                                                                                                                                                                                      '— '
                                                                                                                                                                                                                                                                                      'beat '
                                                                                                                                                                                                                                                                                      'sections '
                                                                                                                                                                                                                                                                                      'in '
                                                                                                                                                                                                                                                                                      'order, '
                                                                                                                                                                                                                                                                                      'vocals '
                                                                                                                                                                                                                                                                                      'of '
                                                                                                                                                                                                                                                                                      'the '
                                                                                                                                                                                                                                                                                      'same '
                                                                                                                                                                                                                                                                                      'role '
                                                                                                                                                                                                                                                                                      'on '
                                                                                                                                                                                                                                                                                      'top.\n'
                                                                                                                                                                                                                                                                                      'Both '
                                                                                                                                                                                                                                                                                      'in '
                                                                                                                                                                                                                                                                                      'full '
                                                                                                                                                                                                                                                                                      '— '
                                                                                                                                                                                                                                                                                      'beat '
                                                                                                                                                                                                                                                                                      'and '
                                                                                                                                                                                                                                                                                      'vocals '
                                                                                                                                                                                                                                                                                      'as '
                                                                                                                                                                                                                                                                                      'in '
                                                                                                                                                                                                                                                                                      'the '
                                                                                                                                                                                                                                                                                      'originals, '
                                                                                                                                                                                                                                                                                      'no '
                                                                                                                                                                                                                                                                                      'cutting: '
                                                                                                                                                                                                                                                                                      'the '
                                                                                                                                                                                                                                                                                      'bot '
                                                                                                                                                                                                                                                                                      'only '
                                                                                                                                                                                                                                                                                      'chooses\n'
                                                                                                                                                                                                                                                                                      'where '
                                                                                                                                                                                                                                                                                      'the '
                                                                                                                                                                                                                                                                                      'vocals '
                                                                                                                                                                                                                                                                                      'come '
                                                                                                                                                                                                                                                                                      'in '
                                                                                                                                                                                                                                                                                      'so '
                                                                                                                                                                                                                                                                                      'the '
                                                                                                                                                                                                                                                                                      'chorus '
                                                                                                                                                                                                                                                                                      'lands '
                                                                                                                                                                                                                                                                                      'on '
                                                                                                                                                                                                                                                                                      'the '
                                                                                                                                                                                                                                                                                      'chorus.',
 'Остановить работу бота': 'Stop the bot',
 'Напиши боту: «смешай Numb и In the End», «ещё вариант», «помощь»…': 'Tell the bot: “mix Numb and In the End”, '
                                                                      '“another version”, “help”…',
 'Отправить': 'Send',
 'Привет! Я делаю мэшапы из твоих треков: беру голос одного и музыку другого, подгоняю темп по долям и тональность, раскладываю по частям песни и свожу. Выбери треки сверху или напиши, что смешать. «помощь» — что я умею.': 'Hi! '
                                                                                                                                                                                                                               'I '
                                                                                                                                                                                                                               'make '
                                                                                                                                                                                                                               'mashups '
                                                                                                                                                                                                                               'from '
                                                                                                                                                                                                                               'your '
                                                                                                                                                                                                                               'tracks: '
                                                                                                                                                                                                                               'I '
                                                                                                                                                                                                                               'take '
                                                                                                                                                                                                                               'the '
                                                                                                                                                                                                                               'vocals '
                                                                                                                                                                                                                               'of '
                                                                                                                                                                                                                               'one '
                                                                                                                                                                                                                               'and '
                                                                                                                                                                                                                               'the '
                                                                                                                                                                                                                               'music '
                                                                                                                                                                                                                               'of '
                                                                                                                                                                                                                               'another, '
                                                                                                                                                                                                                               'match '
                                                                                                                                                                                                                               'the '
                                                                                                                                                                                                                               'tempo '
                                                                                                                                                                                                                               'by '
                                                                                                                                                                                                                               'beats '
                                                                                                                                                                                                                               'and '
                                                                                                                                                                                                                               'the '
                                                                                                                                                                                                                               'key, '
                                                                                                                                                                                                                               'arrange '
                                                                                                                                                                                                                               'them '
                                                                                                                                                                                                                               'by '
                                                                                                                                                                                                                               'song '
                                                                                                                                                                                                                               'sections '
                                                                                                                                                                                                                               'and '
                                                                                                                                                                                                                               'mix. '
                                                                                                                                                                                                                               'Pick '
                                                                                                                                                                                                                               'the '
                                                                                                                                                                                                                               'tracks '
                                                                                                                                                                                                                               'above '
                                                                                                                                                                                                                               'or '
                                                                                                                                                                                                                               'tell '
                                                                                                                                                                                                                               'me '
                                                                                                                                                                                                                               'what '
                                                                                                                                                                                                                               'to '
                                                                                                                                                                                                                               'mix. '
                                                                                                                                                                                                                               '“help” '
                                                                                                                                                                                                                               '— '
                                                                                                                                                                                                                               'what '
                                                                                                                                                                                                                               'I '
                                                                                                                                                                                                                               'can '
                                                                                                                                                                                                                               'do.',
 'Выбери любой в поле «Бит» и нажми «Сделать мэшап».': 'Pick any in the “Beat” field and press “Make mashup”.',
 'Анализ…': 'Analyzing…',
 'Начинаю…': 'Starting…',
 'Бит': 'Beat',
 'Замедлить (как slowed + reverb)': 'Slow down (like slowed + reverb)',
 'Ускорить (как sped up)': 'Speed up (like sped up)',
 'Короче': 'Shorter',
 'Около двух минут': 'About two minutes',
 'Без переходов': 'No transitions',
 'Без райзеров и ударов перед припевами': 'No risers and hits before choruses',
 'Только припевы': 'Choruses only',
 'Оставить только припевы': 'Keep only the choruses',
 'Сделать мэшап': 'Make mashup',
 'Подобрать пару': 'Find a match',
 'Что из библиотеки подойдёт к треку': 'What from the library fits this track',
 'Ещё вариант': 'Another version',
 'В библиотеку': 'To library',
 'Сохранить мэшап в MP3 и добавить в плеер': 'Save the mashup as MP3 and add it to the player',
 'Выбери оба трека: чей голос взять (Вокал) и чью музыку (Бит).': 'Pick both tracks: whose vocals to take (Vocals) '
                                                                  'and whose music (Beat).',
 'Это один и тот же трек — выбери два разных.': "That's the same track — pick two different ones.",
 'Сначала сделаем мэшап — потом смогу предложить другой вариант.': "Let's make a mashup first — then I can suggest "
                                                                   'another version.',
 'Выбери трек в поле «Вокал» — подберу к нему музыку.': "Pick a track in the “Vocals” field — I'll find music for "
                                                        'it.',
 'Для подбора нужен анализ библиотеки (темп и тональность треков) — плеер делает его сам в фоне, когда включены умные рекомендации. Пока могу смешать любые два трека, которые ты выберешь.': 'Matching '
                                                                                                                                                                                              'needs '
                                                                                                                                                                                              'a '
                                                                                                                                                                                              'library '
                                                                                                                                                                                              'analysis '
                                                                                                                                                                                              '(tempo '
                                                                                                                                                                                              'and '
                                                                                                                                                                                              'key '
                                                                                                                                                                                              'of '
                                                                                                                                                                                              'tracks) '
                                                                                                                                                                                              '— '
                                                                                                                                                                                              'the '
                                                                                                                                                                                              'player '
                                                                                                                                                                                              'does '
                                                                                                                                                                                              'it '
                                                                                                                                                                                              'in '
                                                                                                                                                                                              'the '
                                                                                                                                                                                              'background '
                                                                                                                                                                                              'when '
                                                                                                                                                                                              'smart '
                                                                                                                                                                                              'recommendations '
                                                                                                                                                                                              'are '
                                                                                                                                                                                              'on. '
                                                                                                                                                                                              'For '
                                                                                                                                                                                              'now '
                                                                                                                                                                                              'I '
                                                                                                                                                                                              'can '
                                                                                                                                                                                              'mix '
                                                                                                                                                                                              'any '
                                                                                                                                                                                              'two '
                                                                                                                                                                                              'tracks '
                                                                                                                                                                                              'you '
                                                                                                                                                                                              'choose.',
 'Подожди, я ещё занят предыдущим.': "Wait, I'm still busy with the previous one.",
 'Подожди, я ещё собираю предыдущий мэшап (или нажми «Стоп»).': "Wait, I'm still building the previous mashup (or "
                                                                'press “Stop”).',
 'Растягиваю бит и вокал по долям…': 'Stretching the beat and vocals by beats…',
 'Остановил.': 'Stopped.',
 '\nПробел — слушать. Нравится — «В библиотеку».': '\nSpace — listen. Like it — “To library”.',
 'Экспортирую текущий проект.': 'Exporting the current project.',
 'Решаю, чей голос брать…': 'Deciding whose vocals to take…',
 'К какому треку подобрать пару? Напиши название или выбери его в поле «Вокал».': 'Which track should I find a match '
                                                                                  'for? Type the name or pick it in '
                                                                                  'the “Vocals” field.',
 'Поменял местами поля «Вокал» и «Бит».': 'Swapped the “Vocals” and “Beat” fields.',
 'ровный': 'steady',
 'живой': 'live',
 'Не понял. Напиши, например: «смешай Numb и Faint» или «помощь».': "I didn't get that. Try: “mix Numb and Faint” or "
                                                                    '“help”.',
 'Не нашёл таких треков в библиотеке. Выбери их в полях сверху — там поиск по мере набора.': "Couldn't find those "
                                                                                             'tracks in the library. '
                                                                                             'Pick them in the '
                                                                                             'fields above — they '
                                                                                             'search as you type.',
 'Поиск: треки, звуки, эффекты…': 'Search: tracks, sounds, effects…',
 'Текущий проект': 'Current project',
 'Треки плеера: перетащите в плейлист — станет аудиоклипом': 'Player tracks: drag into the playlist — becomes an '
                                                             'audio clip',
 'Звуки (драм-кит)': 'Sounds (drum kit)',
 'Инструменты': 'Instruments',
 'Пресеты голоса': 'Voice presets',
 'Записи': 'Recordings',
 'Проекты': 'Projects',
 'Чистый': 'Clean',
 'Двойной щелчок — цепочка эффектов на выбранную дорожку микшера': 'Double click — effect chain on the selected '
                                                                   'mixer track',
 'Двойной щелчок — выбрать, тащить — в плейлист': 'Double click — select, drag — into the playlist',
 'Двойной щелчок — открыть': 'Double click — open',
 'Щелчок — послушать, двойной — в плейлист, тащить — куда нужно': 'Click — listen, double click — into the playlist, '
                                                                  'drag — anywhere',
 'Щелчок — послушать, двойной — новый канал': 'Click — listen, double click — new channel',
 'Тащить — в плейлист': 'Drag — into the playlist',
 'Двойной щелчок — новый канал с этим звуком': 'Double click — new channel with this sound',
 'Паттерны': 'Patterns',
 'Двойной щелчок — ': 'Double click — ',
 'пусто': 'empty',
 ' Двойной щелчок — на выбранную дорожку микшера': ' Double click — onto the selected mixer track',
 'в плейлист': 'into the playlist',
 'открыть': 'open',
 'Срез низа': 'Low cut',
 'Низы': 'Lows',
 'Низкая середина': 'Low mids',
 'Середина': 'Mids',
 'Верхняя середина': 'High mids',
 'Верха': 'Highs',
 'Срез верха': 'High cut',
 'Параметрический EQ': 'Parametric EQ',
 'Эквалайзеры и фильтры': 'Equalizers and filters',
 '7 полос: срезы, полки и колокола. Точки на графике можно тянуть мышью, колесо — ширина.': '7 bands: cuts, shelves '
                                                                                            'and bells. Drag the '
                                                                                            'points on the graph '
                                                                                            'with the mouse, wheel — '
                                                                                            'width.',
 'Компрессор': 'Compressor',
 'Динамика': 'Dynamics',
 'Выравнивает громкость: всё, что громче порога, сжимается в «соотношение» раз.': 'Evens out the volume: everything '
                                                                                  'louder than the threshold is '
                                                                                  'compressed by the “ratio”.',
 'Лимитер': 'Limiter',
 'Не даёт звуку перейти потолок: громко и без перегруза. Ставят последним на мастер.': 'Keeps the sound under the '
                                                                                       'ceiling: loud without '
                                                                                       'clipping. Usually last on '
                                                                                       'the master.',
 'Гейт': 'Gate',
 'Глушит всё тише порога: убирает шум между фразами и хвосты.': 'Mutes everything below the threshold: removes noise '
                                                                'between phrases and tails.',
 'Де-эссер': 'De-esser',
 'Приглушает резкие «с», «ш», «ц» в голосе.': 'Softens harsh “s”, “sh”, “ts” sounds in the voice.',
 'Сайдчейн-качка': 'Sidechain pump',
 'Громкость «качается» в такт, как будто бочка давит остальное — танцевальный сайдчейн.': 'The volume “pumps” in '
                                                                                          'time, as if the kick '
                                                                                          'ducks everything else — '
                                                                                          'dance sidechain.',
 'Ревербератор': 'Reverb',
 'Пространство': 'Space',
 'Звук в помещении: от маленькой комнаты до собора.': 'Sound in a room: from a small room to a cathedral.',
 'Дилей (эхо)': 'Delay (echo)',
 'Эхо в такт песне. Пинг-понг — повторы прыгают слева направо.': 'Echo in time with the song. Ping-pong — repeats '
                                                                 'bounce left and right.',
 'Хорус / даблер': 'Chorus / doubler',
 'Модуляция': 'Modulation',
 'Несколько слегка расстроенных копий — звук шире и «гуще». Для голоса — эффект дабла.': 'Several slightly detuned '
                                                                                         'copies — a wider, '
                                                                                         '“thicker” sound. For '
                                                                                         'vocals — a double effect.',
 'Флэнджер': 'Flanger',
 '«Самолётный» свист: очень короткая задержка с обратной связью.': '“Jet plane” whoosh: a very short delay with '
                                                                   'feedback.',
 'Фейзер': 'Phaser',
 'Плывущие провалы по частотам — «космический» перелив.': 'Sweeping notches across frequencies — a “spacey” shimmer.',
 'Фильтр': 'Filter',
 'Срезает низ или верх; с качанием в такт — классический «фильтр-свип».': 'Cuts the lows or the highs; with tempo '
                                                                          'sync — the classic “filter sweep”.',
 'Дисторшн / сатуратор': 'Distortion / saturator',
 'Искажения': 'Distortion',
 'От тёплого лампового перегруза до злого фузза.': 'From warm tube overdrive to nasty fuzz.',
 'Биткрашер': 'Bitcrusher',
 'Звук старых приставок: меньше бит и частоты дискретизации.': 'The sound of old consoles: fewer bits and a lower '
                                                               'sample rate.',
 'Лоу-фай (кассета)': 'Lo-fi (cassette)',
 'Плавание плёнки, шипение, треск пластинки и мягкий завал верхов.': 'Tape wobble, hiss, vinyl crackle and soft high '
                                                                     'roll-off.',
 'Стерео-расширитель': 'Stereo widener',
 'Утилиты': 'Utilities',
 'Шире или уже стерео, панорама, моно на басу.': 'Wider or narrower stereo, panning, mono bass.',
 'Утилита (громкость)': 'Utility (volume)',
 'Громкость, панорама, моно, смена фазы.': 'Volume, panning, mono, phase flip.',
 'Анализатор (осциллограф и спектр)': 'Analyzer (oscilloscope and spectrum)',
 'Ничего не меняет — показывает волну и спектр того, что проходит.': 'Changes nothing — shows the waveform and '
                                                                     'spectrum of what passes through.',
 'Питч-шифтер': 'Pitch shifter',
 'Выше или ниже без изменения темпа. «Сохранять тембр» — голос не становится мультяшным.': 'Higher or lower without '
                                                                                           'changing the tempo. '
                                                                                           '“Keep timbre” — the '
                                                                                           "voice doesn't turn "
                                                                                           'cartoonish.',
 'Автотюн': 'Autotune',
 'Подтягивает голос к нотам лада. Скорость 0 — роботизированный эффект, как в хитах 2000-х.': 'Pulls the voice to '
                                                                                              'the notes of the '
                                                                                              'scale. Speed 0 — the '
                                                                                              'robotic effect, like '
                                                                                              '2000s hits.',
 'Робот / вокодер': 'Robot / vocoder',
 'Робот, монотонный вокодер, аккорд-вокодер или шёпот.': 'Robot, monotone vocoder, chord vocoder or whisper.',
 'Мажор': 'Major',
 'Минор': 'Minor',
 'Хроматическая': 'Chromatic',
 'Пентатоника мажор': 'Major pentatonic',
 'Пентатоника минор': 'Minor pentatonic',
 'Гармонический минор': 'Harmonic minor',
 'Блюз': 'Blues',
 'Дорийский': 'Dorian',
 'Вырез под вокал': 'Vocal pocket',
 'Присутствие голоса': 'Vocal presence',
 'Убрать гул': 'Remove rumble',
 'Телефон': 'Telephone',
 'Радио AM': 'AM radio',
 'Больше баса': 'More bass',
 'Яркость': 'Brightness',
 'Рэп — плотно': 'Rap — tight',
 'Бочка': 'Kick',
 'Склейка мастера': 'Master glue',
 'Комната': 'Room',
 'Зал': 'Hall',
 'Пластина (вокал)': 'Plate (vocals)',
 'Собор': 'Cathedral',
 'Стадион': 'Stadium',
 'Восьмые пинг-понг': 'Eighths ping-pong',
 'Четверть точкой': 'Dotted quarter',
 'Слэпбэк': 'Slapback',
 'Бесконечное эхо': 'Endless echo',
 'Жёсткий (роботизированный)': 'Hard (robotic)',
 'Естественно': 'Natural',
 'Мягкая подтяжка': 'Gentle correction',
 'Демон': 'Demon',
 'Бурундук': 'Chipmunk',
 'Октава вниз': 'Octave down',
 'Чуть выше': 'A bit higher',
 'Тёплая лампа': 'Warm tube',
 'Мегафон': 'Megaphone',
 'Злой фузз': 'Nasty fuzz',
 'Свип в такт': 'Tempo sweep',
 'Под водой': 'Underwater',
 'Классика 1/4': 'Classic 1/4',
 'Быстрый 1/8': 'Fast 1/8',
 'Студийный вокал': 'Studio vocals',
 'Рэп — плотный': 'Rap — tight',
 'Автотюн жёсткий': 'Hard autotune',
 'Автотюн естественный': 'Natural autotune',
 'Радио': 'Radio',
 'Робот': 'Robot',
 'Вокодер': 'Vocoder',
 'Шёпот-призрак': 'Ghost whisper',
 'Хор / дабл': 'Choir / double',
 'Лоу-фай': 'Lo-fi',
 'Крутизна срезов': 'Cut slope',
 'Выход': 'Output',
 'Порог': 'Threshold',
 'Соотношение': 'Ratio',
 'Атака': 'Attack',
 'Спад': 'Release',
 'Мягкость колена': 'Knee',
 'Компенсация': 'Makeup',
 'Усиление на входе': 'Input gain',
 'Потолок': 'Ceiling',
 'Удержание': 'Hold',
 'Глубина': 'Depth',
 'Частота': 'Frequency',
 'Шаг': 'Step',
 'Восстановление': 'Recovery',
 'Сдвиг': 'Shift',
 'Глушение верхов': 'High damping',
 'Пред-задержка': 'Pre-delay',
 'Чистый звук': 'Dry',
 'Время': 'Time',
 'Повторы': 'Feedback',
 'Пинг-понг': 'Ping-pong',
 'Тон повторов': 'Repeat tone',
 'Задержка': 'Delay',
 'Голоса': 'Voices',
 'Обратная связь': 'Feedback',
 'Стадии': 'Stages',
 'Тип': 'Type',
 'Частота среза': 'Cutoff',
 'Качание': 'Sweep',
 'Глубина качания': 'Sweep depth',
 'Характер': 'Character',
 'Перегруз': 'Drive',
 'Тон': 'Tone',
 'Разрядность': 'Bit depth',
 'бит': 'bit',
 'Понижение частоты': 'Downsampling',
 'Плавание': 'Wobble',
 'Треск': 'Crackle',
 'Шипение': 'Hiss',
 'Насыщение': 'Saturation',
 'Панорама': 'Pan',
 'Моно ниже': 'Mono below',
 'Моно': 'Mono',
 'Перевернуть фазу': 'Flip phase',
 'Полутоны': 'Semitones',
 'Центы': 'Cents',
 'Сохранять тембр': 'Keep timbre',
 'Сдвиг тембра': 'Formant shift',
 'Тоника': 'Root',
 'Лад': 'Scale',
 'Скорость подтяжки': 'Retune speed',
 'Режим': 'Mode',
 'Нота вокодера': 'Vocoder note',
 'вкл': 'on',
 'выкл': 'off',
 '12 дБ/окт': '12 dB/oct',
 '24 дБ/окт': '24 dB/oct',
 '48 дБ/окт': '48 dB/oct',
 'Низких частот (LP)': 'Low-pass (LP)',
 'Высоких частот (HP)': 'High-pass (HP)',
 'Полосовой (BP)': 'Band-pass (BP)',
 'Режекторный': 'Notch',
 'Мягкий (лампа)': 'Soft (tube)',
 'Жёсткий клиппинг': 'Hard clipping',
 'Фузз': 'Fuzz',
 'Транзистор': 'Transistor',
 'Складка (wavefold)': 'Wavefold',
 'Выпрямитель': 'Rectifier',
 'Вокодер (одна нота)': 'Vocoder (one note)',
 'Вокодер (аккорд)': 'Vocoder (chord)',
 'Шёпот': 'Whisper',
 'Пила': 'Saw',
 'Импульс 25%': 'Pulse 25%',
 'Шум': 'Noise',
 'Синтезатор': 'Synthesizer',
 'Три осциллятора, фильтр с огибающей, унисон и вибрато — бас, лиды, пэды.': 'Three oscillators, filter with '
                                                                             'envelope, unison and vibrato — bass, '
                                                                             'leads, pads.',
 'Супер-пила': 'Supersaw',
 'До 9 расстроенных пил — широкие лиды и пэды транса и EDM.': 'Up to 9 detuned saws — wide trance and EDM leads and '
                                                              'pads.',
 'Рояль': 'Grand piano',
 'Электропиано': 'Electric piano',
 'Орган': 'Organ',
 'Музыкальная шкатулка': 'Music box',
 'Клавесин': 'Harpsichord',
 'Маримба': 'Marimba',
 'Клавишные': 'Keys',
 'Рояль, электропиано, орган, шкатулка, клавесин, маримба.': 'Grand piano, electric piano, organ, music box, '
                                                             'harpsichord, marimba.',
 'Щипковые': 'Plucked',
 'Струна по Карплусу — Стронгу: гитара, арфа, кото, бас-гитара.': 'Karplus–Strong string: guitar, harp, koto, bass '
                                                                  'guitar.',
 'FM-синт': 'FM synth',
 'Частотная модуляция двух операторов: колокола, DX-пиано, металлический бас.': 'Two-operator frequency modulation: '
                                                                                'bells, DX piano, metallic bass.',
 'Гудящий бас трэпа: синус со «щелчком» высоты, долгим хвостом и перегрузом.': 'Booming trap bass: a sine with a '
                                                                               'pitch “click”, long tail and drive.',
 'Сэмплер': 'Sampler',
 'Играет звук из кита или любой файл. Высота меняется нотой.': 'Plays a kit sound or any file. Pitch follows the '
                                                               'note.',
 'Срез': 'Cutoff',
 'Огибающая фильтра': 'Filter envelope',
 'окт': 'oct',
 'Ф: атака': 'F: attack',
 'Ф: спад': 'F: decay',
 'Ф: уровень': 'F: amount',
 'Уровень': 'Level',
 'Отпускание': 'Release',
 'Пила-лид': 'Saw lead',
 'Квадратный лид': 'Square lead',
 'Синт-бас 80-х': '80s synth bass',
 'Мягкий пэд': 'Soft pad',
 'Стринги': 'Strings',
 'Плак': 'Pluck',
 'Чиптюн': 'Chiptune',
 'Колокольчик': 'Bell',
 'Транс-лид': 'Trance lead',
 'Широкий пэд': 'Wide pad',
 'Хардстайл': 'Hardstyle',
 'Аккорды-стабы': 'Chord stabs',
 'Яркий рояль': 'Bright piano',
 'Шкатулка': 'Music box',
 'Гитара': 'Guitar',
 'Арфа': 'Harp',
 'Кото': 'Koto',
 'Бас-гитара': 'Bass guitar',
 'Глухой щипок': 'Muted pluck',
 'Колокол': 'Bell',
 'DX-пиано': 'DX piano',
 'Металл': 'Metal',
 'Мягкий FM-пэд': 'Soft FM pad',
 '808 классика': 'Classic 808',
 '808 долгий': '808 long',
 '808 злой': '808 nasty',
 '808 короткий': '808 short',
 'Дистортед 808': 'Distorted 808',
 'Бочки': 'Kicks',
 'Малые': 'Snares',
 'Хлопки': 'Claps',
 'Хэты и тарелки': 'Hats and cymbals',
 'Томы и перкуссия': 'Toms and percussion',
 'Низких (LP)': 'Low-pass (LP)',
 'Высоких (HP)': 'High-pass (HP)',
 'Полосовой': 'Band-pass',
 'Инструмент': 'Instrument',
 'Звучание': 'Sound',
 'Место щипка': 'Pluck position',
 'Хвост': 'Tail',
 'Удар высотой': 'Pitch punch',
 'Время удара': 'Punch time',
 'Щелчок': 'Click',
 'Подстройка': 'Tuning',
 'Корневая нота': 'Root note',
 'Высота от ноты': 'Pitch follows note',
 'Играть всю длину': 'Play full length',
 'Начало': 'Start',
 'Задом наперёд': 'Reverse',
 'Отношение модулятора': 'Modulator ratio',
 'Глубина модуляции': 'Modulation depth',
 'Спад глубины': 'Depth decay',
 'Бочка Punch': 'Kick Punch',
 'Бочка Deep': 'Kick Deep',
 'Бочка House': 'Kick House',
 'Бочка Trap': 'Kick Trap',
 'Бочка Lo-fi': 'Kick Lo-fi',
 'Бочка Hardstyle': 'Kick Hardstyle',
 'Малый Tight': 'Snare Tight',
 'Малый Fat': 'Snare Fat',
 'Малый Trap': 'Snare Trap',
 'Римшот': 'Rimshot',
 'Хлопок': 'Clap',
 'Хлопок большой': 'Big clap',
 'Щелчок пальцами': 'Finger snap',
 'Хэт закрытый': 'Closed hat',
 'Хэт Trap': 'Trap hat',
 'Хэт открытый': 'Open hat',
 'Шейкер': 'Shaker',
 'Райд': 'Ride',
 'Крэш': 'Crash',
 'Том низкий': 'Low tom',
 'Том средний': 'Mid tom',
 'Том высокий': 'High tom',
 'Ковбелл': 'Cowbell',
 'Конга': 'Conga',
 'Конга низкая': 'Low conga',
 'Райзер': 'Riser',
 'Даунлифтер': 'Downlifter',
 'Импакт': 'Impact',
 'Обратная тарелка': 'Reverse cymbal',
 'Расстройка': 'Detune',
 'Центр / края': 'Center / sides',
 'Унисон (голоса)': 'Unison (voices)',
 'Расстройка унисона': 'Unison detune',
 'Ширина стерео': 'Stereo width',
 'Вибрато': 'Vibrato',
 'Скорость вибрато': 'Vibrato speed',
 'Глиссандо от': 'Glide from',
 'Я делаю мэшапы: вокал одного трека на бите другого — с подгонкой темпа по долям, тональности и сведением.\n\nКак просить:\n  смешай Numb и In the End\n  вокал из Blinding Lights на бит Faint\n  подбери пару к One Step Closer\n  ещё вариант / поменяй местами\n  по структуре бита / по структуре вокала\n  оба целиком — бит и вокал как в оригиналах, без нарезки\n  slowed / sped up / нормальная скорость\n  короче / полная версия / без переходов / только припев\n  вокал выше на 1 / вокал ниже на 2 / громче вокал / тише вокал\n  экспорт — сохранить готовый мэшап в библиотеку\n\nМожно и без слов: выбери треки в полях «Вокал» и «Бит» и нажми «Сделать мэшап».\nПервый раз на каждый трек уходит 1–3 минуты: нейросеть отделяет голос от музыки. Потом — быстро.': 'I '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'make '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'mashups: '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'vocals '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'of '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'one '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'track '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'over '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'beat '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'of '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'another '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '— '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'with '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'tempo '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'matching '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'by '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'beats, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'key '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'matching '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'and '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'mixing.\n'
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '\n'
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'How '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'to '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'ask:\n'
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '  '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'mix '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'Numb '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'and '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'In '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'End\n'
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '  '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'vocals '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'from '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'Blinding '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'Lights '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'over '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'Faint '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'beat\n'
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '  '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'find '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'a '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'match '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'for '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'One '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'Step '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'Closer\n'
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '  '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'another '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'version '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '/ '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'swap\n'
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '  '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'by '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'beat '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'structure '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '/ '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'by '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'vocal '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'structure\n'
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '  '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'both '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'in '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'full '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '— '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'beat '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'and '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'vocals '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'as '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'in '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'originals, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'no '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'cutting\n'
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '  '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'slowed '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '/ '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'sped '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'up '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '/ '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'normal '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'speed\n'
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '  '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'shorter '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '/ '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'full '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'version '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '/ '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'no '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'transitions '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '/ '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'chorus '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'only\n'
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '  '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'vocals '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'up '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '1 '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '/ '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'vocals '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'down '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '2 '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '/ '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'louder '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'vocals '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '/ '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'quieter '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'vocals\n'
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '  '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'export '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '— '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'save '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'finished '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'mashup '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'to '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'library\n'
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '\n'
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'Or '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'without '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'words: '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'pick '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'tracks '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'in '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '“Vocals” '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'and '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '“Beat” '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'fields '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'and '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'press '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '“Make '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'mashup”.\n'
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'The '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'first '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'time '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'each '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'track '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'takes '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '1–3 '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'minutes: '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'a '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'neural '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'network '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'separates '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'voice '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'from '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'music. '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'After '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'that '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        '— '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        'fast.',
 'вступление': 'intro',
 'концовка': 'outro',
 'припев': 'chorus',
 'куплет': 'verse',
 'проигрыш': 'interlude',
 'Уточняю темп по ударам…': 'Refining the tempo by beats…',
 'Определяю тональность…': 'Detecting the key…',
 'Оригинал бита': 'Original beat',
 'Всё лежит в плейлисте: фразы можно двигать, громкость и эффекты — на дорожках «Вокал» и «Бит». «Ещё вариант» — другая раскладка, «поменяй местами» — наоборот.': 'Everything '
                                                                                                                                                                   'is '
                                                                                                                                                                   'in '
                                                                                                                                                                   'the '
                                                                                                                                                                   'playlist: '
                                                                                                                                                                   'phrases '
                                                                                                                                                                   'can '
                                                                                                                                                                   'be '
                                                                                                                                                                   'moved, '
                                                                                                                                                                   'volume '
                                                                                                                                                                   'and '
                                                                                                                                                                   'effects '
                                                                                                                                                                   'are '
                                                                                                                                                                   'on '
                                                                                                                                                                   'the '
                                                                                                                                                                   '“Vocals” '
                                                                                                                                                                   'and '
                                                                                                                                                                   '“Beat” '
                                                                                                                                                                   'tracks. '
                                                                                                                                                                   '“Another '
                                                                                                                                                                   'version” '
                                                                                                                                                                   '— '
                                                                                                                                                                   'a '
                                                                                                                                                                   'different '
                                                                                                                                                                   'arrangement, '
                                                                                                                                                                   '“swap” '
                                                                                                                                                                   '— '
                                                                                                                                                                   'the '
                                                                                                                                                                   'other '
                                                                                                                                                                   'way '
                                                                                                                                                                   'round.',
 'Переходы': 'Transitions',
 'Подъём': 'Rise',
 'Удар': 'Hit',
 'передискретизацией, как у диджея (барабаны чёткие)': 'by resampling, like a DJ (drums stay crisp)',
 'по долям вокодером': 'by beats with a vocoder',
 'Основа — ': 'Base — ',
 ' бита': ' of the beat',
 'Вокал отделён без нейросети (нет onnxruntime или интернета) — качество хуже обычного.': 'Vocals separated without '
                                                                                          'the neural network (no '
                                                                                          'onnxruntime or internet) '
                                                                                          '— quality is worse than '
                                                                                          'usual.',
 'Собираю аранжировку…': 'Building the arrangement…',
 'Паттерн 1': 'Pattern 1',
 'часть': 'part',
 ' вокала': ' of the vocals',
 'бит с голосом оригинала': 'beat with the original vocals',
 'только бит': 'beat only',
 'Слушаю трек: ': 'Listening to the track: ',
 'поднят': 'raised',
 'опущен': 'lowered',
 'структура вокальной песни: куплеты и припевы идут как в оригинале, под ними меняются части бита.': 'vocal song '
                                                                                                     'structure: '
                                                                                                     'verses and '
                                                                                                     'choruses go as '
                                                                                                     'in the '
                                                                                                     'original, beat '
                                                                                                     'sections '
                                                                                                     'change '
                                                                                                     'underneath.',
 'структура бита: его части по порядку, на них — вокал той же роли сплошными кусками.': 'beat structure: its '
                                                                                        'sections in order, with '
                                                                                        'vocals of the same role on '
                                                                                        'top in solid chunks.',
 'оба трека целиком, как в оригиналах: бит от начала до конца, вокал одним куском без нарезки, вступает так, чтобы припев лёг на припев бита.': 'both '
                                                                                                                                                'tracks '
                                                                                                                                                'in '
                                                                                                                                                'full, '
                                                                                                                                                'as '
                                                                                                                                                'in '
                                                                                                                                                'the '
                                                                                                                                                'originals: '
                                                                                                                                                'the '
                                                                                                                                                'beat '
                                                                                                                                                'from '
                                                                                                                                                'start '
                                                                                                                                                'to '
                                                                                                                                                'end, '
                                                                                                                                                'the '
                                                                                                                                                'vocals '
                                                                                                                                                'in '
                                                                                                                                                'one '
                                                                                                                                                'piece '
                                                                                                                                                'without '
                                                                                                                                                'cutting, '
                                                                                                                                                'coming '
                                                                                                                                                'in '
                                                                                                                                                'so '
                                                                                                                                                'the '
                                                                                                                                                'chorus '
                                                                                                                                                'lands '
                                                                                                                                                'on '
                                                                                                                                                'the '
                                                                                                                                                "beat's "
                                                                                                                                                'chorus.',
 'Дорожка включена': 'Track enabled',
 'Эффект включён': 'Effect enabled',
 'Пресет голоса: готовая цепочка эффектов для вокала': 'Voice preset: a ready effect chain for vocals',
 'Убрать все эффекты с дорожки': 'Remove all effects from the track',
 'Дорожка микшера': 'Mixer track',
 'Сбросить громкость и панораму': 'Reset volume and pan',
 'Очистить эффекты': 'Clear effects',
 'Соло': 'Solo',
 'Сброс дорожки': 'Reset track',
 'Пресет эффекта': 'Effect preset',
 'Порядок эффектов': 'Effect order',
 'Панорама дорожки': 'Track pan',
 'Соло: слышна только эта дорожка': 'Solo: only this track is heard',
 'Заглушить дорожку': 'Mute track',
 'Микс эффекта': 'Effect mix',
 'Вкл/выкл эффект': 'Effect on/off',
 'Пустая ячейка: щелчок — выбрать эффект': 'Empty slot: click — choose an effect',
 '— пусто —': '— empty —',
 'Пресет голоса': 'Voice preset',
 'Очистить цепочку': 'Clear chain',
 'Название дорожки': 'Track name',
 'Заменить эффект': 'Replace effect',
 'Открыть окно': 'Open window',
 'Громкость дорожки': 'Track volume',
 ' Правая кнопка — меню': ' Right click — menu',
 'Мастер': 'Master',
 'Каналов на дорожке нет': 'No channels on this track',
 'Пресет': 'Preset',
 'Каналы: ': 'Channels: ',
 'Дорожка ': 'Track ',
 'такт': 'bar',
 'доля': 'beat',
 '1/2 доли': '1/2 beat',
 '1/4 доли': '1/4 beat',
 'без сетки': 'no grid',
 'Поставить клип': 'Place clip',
 'Разрезать клип': 'Split clip',
 'Дорожка': 'Track',
 'Название дорожки:': 'Track name:',
 'Заглушить / включить': 'Mute / unmute',
 'Выделить все клипы дорожки': 'Select all clips of the track',
 'Очистить дорожку': 'Clear track',
 'Что ставит кисть: паттерн или аудиоклип': 'What the brush places: a pattern or an audio clip',
 'аудио': 'audio',
 'Удалить клипы': 'Delete clips',
 'Заглушить клип': 'Mute clip',
 'Двигать клипы': 'Move clips',
 'ПЕСНЯ': 'SONG',
 'ПАТТЕРН (L — песня)': 'PATTERN (L — song)',
 'Кисть: ставить и двигать клипы (щелчок по клипу — выбрать его образцом)': 'Brush: place and move clips (click a '
                                                                            'clip — use it as the sample)',
 'Рисовать серией: тянуть — клипы подряд': 'Paint a series: drag — clips in a row',
 'Нож: разрезать клип': 'Knife: split a clip',
 'Выделение рамкой': 'Box selection',
 'Ставить': 'Place',
 'Длина клипа': 'Clip length',
 'Начало клипа': 'Clip start',
 'Копия клипов': 'Copy clips',
 'Паттерн: ': 'Pattern: ',
 'Вставить клипы': 'Paste clips',
 'готовлю звук…': 'preparing sound…',
 'Аудио: ': 'Audio: ',
 'Повторить клипы': 'Repeat clips',
 'Параметр плагина': 'Plugin parameter',
 'Звук для сэмплера': 'Sound for the sampler',
 'Звук (*.wav *.mp3 *.flac *.ogg *.m4a *.aiff)': 'Audio (*.wav *.mp3 *.flac *.ogg *.m4a *.aiff)',
 'Подавление': 'Reduction',
 'Пресет…': 'Preset…',
 'Звук кита…': 'Kit sound…',
 'Взять звук из файла': 'Take sound from a file',
 'Файл…': 'File…',
 ' — тянуть, колесо — ширина': ' — drag, wheel — width',
 'Голоса нет — включите воспроизведение': 'No voice — start playback',
 'мастер': 'master',
 'слышу ': 'hearing ',
 'дорожка ': 'track ',
 'Проект': 'Project',
 'Хэт': 'Hat',
 'Малый': 'Snare',
 'Громкость канала': 'Channel volume',
 'Панорама канала': 'Channel pan',
 'Шаги': 'Steps',
 'Канал включён (выкл — заглушён)': 'Channel on (off — muted)',
 'Добавить канал: звук кита, инструмент, аудиоканал или файл': 'Add a channel: kit sound, instrument, audio channel '
                                                               'or file',
 'Паттерн, который редактируется и играет в режиме «Паттерн»': 'The pattern edited and played in “Pattern” mode',
 'Новый паттерн': 'New pattern',
 'Копия паттерна': 'Copy of pattern',
 'Длина паттерна': 'Pattern length',
 'Свободная дорожка': 'Free track',
 'Канал': 'Channel',
 'Название канала:': 'Channel name:',
 'Другой…': 'Other…',
 'Клонировать': 'Clone',
 'Удалить канал': 'Delete channel',
 'Цвет канала': 'Channel color',
 'Заполнить шаги': 'Fill steps',
 'Порядок каналов': 'Channel order',
 'Звук кита (сэмплер)': 'Kit sound (sampler)',
 'Сэмплер из файла…': 'Sampler from file…',
 'Аудиоканал (для клипов и записи)': 'Audio channel (for clips and recording)',
 'Шаги: щелчок — включить, тянуть — рисовать, правая кнопка — стереть': 'Steps: click — on, drag — paint, right '
                                                                        'click — erase',
 'В паттерне мелодия — щелчок откроет пианоролл': 'This pattern has a melody — click to open the piano roll',
 'Аудиоканал играет клипы из плейлиста — шагов у него нет': 'An audio channel plays clips from the playlist — it has '
                                                            'no steps',
 'аудиоканал — клипы в плейлисте': 'audio channel — clips in the playlist',
 'Заглушить канал': 'Mute channel',
 'Шагов': 'Steps',
 'Свинг': 'Swing',
 'Переименовать канал': 'Rename channel',
 'Открыть инструмент': 'Open instrument',
 'Пианоролл': 'Piano roll',
 'Заменить инструмент': 'Replace instrument',
 'Очистить ноты в паттерне': 'Clear notes in the pattern',
 'Очистить ноты': 'Clear notes',
 'Звук кита': 'Kit sound',
 'Звук из файла…': 'Sound from file…',
 'Аудио': 'Audio',
 'аудиоканал': 'audio channel',
 '1/1 такта': '1/1 bar',
 '1/4 доли (шаг)': '1/4 beat (step)',
 '1/8 доли': '1/8 beat',
 'триоли': 'triplets',
 'одна нота': 'single note',
 'мажор': 'major',
 'минор': 'minor',
 'септаккорд 7': 'dominant 7',
 'мажорный 7': 'major 7',
 'минорный 7': 'minor 7',
 'уменьшённый': 'diminished',
 'увеличенный': 'augmented',
 'квинта (power)': 'fifth (power)',
 'октава': 'octave',
 'Нота': 'Note',
 'Канал, ноты которого редактируются': 'Channel whose notes are being edited',
 'Штамп: одним щелчком ставится весь аккорд': 'Stamp: one click places the whole chord',
 'Подсветить ноты лада и использовать его в генераторах': 'Highlight the notes of the scale and use it in the '
                                                          'generators',
 'Квантизация: подтянуть начала нот к сетке (Q)': 'Quantize: snap note starts to the grid (Q)',
 'Генераторы: аккорды, бас, арпеджио, мелодия': 'Generators: chords, bass, arpeggio, melody',
 'Показывать ноты других каналов': 'Show notes of other channels',
 'Квантизация': 'Quantize',
 'Аккорды: грустная прогрессия (i–VI–III–VII)': 'Chords: sad progression (i–VI–III–VII)',
 'Аккорды: поп (I–V–vi–IV)': 'Chords: pop (I–V–vi–IV)',
 'Аккорды: трэп (i–iv–VI–v)': 'Chords: trap (i–iv–VI–v)',
 'Аккорды: джаз (ii–V–I–I)': 'Chords: jazz (ii–V–I–I)',
 'Бас по аккордам паттерна': "Bass from the pattern's chords",
 'Арпеджио из выделенных / всех нот': 'Arpeggio from the selected / all notes',
 'Мелодия в ладу (каждый раз новая)': 'Melody in the scale (new every time)',
 '808 по бочке (ноты на ударах бочки)': '808 on the kick (notes on kick hits)',
 'Очистить ноты канала': 'Clear channel notes',
 'Аккорды': 'Chords',
 'Арпеджио': 'Arpeggio',
 'Мелодия': 'Melody',
 '808 по бочке': '808 on the kick',
 'Сила нажатия': 'Velocity',
 'Удалить ноты': 'Delete notes',
 'Двигать ноты': 'Move notes',
 'Выберите канал с инструментом': 'Pick a channel with an instrument',
 'Карандаш: ставить и двигать ноты': 'Pencil: place and move notes',
 'Ластик: удалять ноты': 'Eraser: delete notes',
 'Аккорд': 'Chord',
 'Идеи': 'Ideas',
 'Нет нот для арпеджио — сначала поставьте аккорды': 'No notes for an arpeggio — place some chords first',
 'В паттерне нет бочки — поставьте шаги бочке, и 808 ляжет на них': 'The pattern has no kick — add kick steps and '
                                                                    'the 808 will follow them',
 'Копия нот': 'Copy notes',
 'Длина ноты': 'Note length',
 'Боч': 'Kick',
 'Вставить ноты': 'Paste notes',
 'Повторить ноты': 'Repeat notes',
 'Транспонировать': 'Transpose',
 'Сдвиг нот': 'Shift notes',
 'Читаю трек…': 'Reading the track…',
 'Вокал отделён': 'Vocals separated',
 'Вокал уже отделён раньше': 'Vocals were already separated',
 'Отделяю вокал по стерео-центру (без нейросети)…': 'Separating vocals by the stereo center (no neural network)…',
 'Качаю нейросеть для отделения вокала (67 МБ, один раз)…': 'Downloading the vocal separation network (67 MB, once)…',
 'Нейросеть отделяет вокал от бита…': 'The neural network is separating the vocals from the beat…',
 'Отделяю вокал…': 'Separating vocals…',
 'Что играет: один паттерн по кругу или вся песня из плейлиста (L)': 'What plays: one pattern on loop or the whole '
                                                                     'song from the playlist (L)',
 'Играть / стоп (пробел)': 'Play / stop (space)',
 'Стоп — вернуться к началу': 'Stop — back to the start',
 'Запись с микрофона (R): взвести и нажать «играть»': 'Microphone recording (R): arm and press “play”',
 'Уровень микрофона': 'Microphone level',
 'Темп, BPM: тянуть вверх/вниз (Ctrl — точно), колесо, двойной щелчок — ввести': 'Tempo, BPM: drag up/down (Ctrl — '
                                                                                 'fine), wheel, double click — type',
 'Метроном (Ctrl+M)': 'Metronome (Ctrl+M)',
 'Загрузка звукового потока и память': 'Audio stream load and memory',
 'Мэшап-бот (F10): вокал одного трека на бите другого': 'Mashup bot (F10): the vocals of one track over the beat of '
                                                        'another',
 'Стойка каналов': 'Channel rack',
 'Микшер': 'Mixer',
 'Мэшап-бот': 'Mashup bot',
 'Добро пожаловать в Echoes Studio. Пробел — играть, F10 — мэшап-бот, F1 — справка по клавишам.': 'Welcome to Echoes '
                                                                                                  'Studio. Space — '
                                                                                                  'play, F10 — '
                                                                                                  'mashup bot, F1 — '
                                                                                                  'keyboard help.',
 'Звук готов': 'Sound ready',
 'Канал голоса': 'Voice channel',
 'Запись': 'Recording',
 'Новый канал': 'New channel',
 'Клон канала': 'Clone channel',
 'Пресет инструмента': 'Instrument preset',
 'Звук сэмплера': 'Sampler sound',
 'Паттерн': 'Pattern',
 'Название паттерна:': 'Pattern name:',
 'Удалить паттерн': 'Delete pattern',
 'Аудиоклип': 'Audio clip',
 ' дБ': ' dB',
 'Нарастание в начале': 'Fade in',
 ' дол.': ' beats',
 'Затухание в конце': 'Fade out',
 'Сдвиг тона': 'Pitch shift',
 ' пт': ' st',
 'Подгонять под темп проекта (растяжение без смены тона)': 'Fit to the project tempo (stretch without changing '
                                                           'pitch)',
 'Темп самого звука': 'Tempo of the sound itself',
 'Определить темп звука': "Detect the sound's tempo",
 'Свойства клипа': 'Clip properties',
 'Автосохранение': 'Autosave',
 'Новый проект': 'New project',
 'Импорт звука': 'Import sound',
 'Звук (*.mp3 *.wav *.flac *.ogg *.m4a *.opus *.aiff)': 'Audio (*.mp3 *.wav *.flac *.ogg *.m4a *.opus *.aiff)',
 'WAV 16 бит (без сжатия)': 'WAV 16-bit (uncompressed)',
 'Вся песня (плейлист)': 'Whole song (playlist)',
 'Только текущий паттерн': 'Current pattern only',
 'Добавить в библиотеку плеера': 'Add to the player library',
 'Звук студии': 'Studio audio',
 'Звук студии настроен': 'Studio audio configured',
 'Echoes Studio — клавиши': 'Echoes Studio — keys',
 'Новый проект (Ctrl+N)': 'New project (Ctrl+N)',
 'Новый пустой проект': 'New empty project',
 'Открыть… (Ctrl+O)': 'Open… (Ctrl+O)',
 'Последние': 'Recent',
 'Сохранить (Ctrl+S)': 'Save (Ctrl+S)',
 'Сохранить как… (Ctrl+Shift+S)': 'Save as… (Ctrl+Shift+S)',
 'Экспорт в MP3 / WAV / FLAC… (Ctrl+R)': 'Export to MP3 / WAV / FLAC… (Ctrl+R)',
 'Импорт звука в плейлист…': 'Import sound into the playlist…',
 'Открыть папку студии': 'Open the studio folder',
 'Выйти из студии (тема Echoes Music)': 'Leave the studio (Echoes Music theme)',
 'Переименовать проект…': 'Rename project…',
 'Темп': 'Tempo',
 'Темп проекта, BPM:': 'Project tempo, BPM:',
 'Название проекта:': 'Project name:',
 'Копия текущего': 'Copy of current',
 'Удалить текущий': 'Delete current',
 'Расставить окна заново': 'Rearrange windows',
 'Закрыть все окна плагинов': 'Close all plugin windows',
 'Звук: вывод и микрофон…': 'Audio: output and microphone…',
 'Клавиатура компьютера как пианино': 'Computer keyboard as a piano',
 'Справка по клавишам (F1)': 'Keyboard help (F1)',
 'ФАЙЛ': 'FILE',
 'ПРАВКА': 'EDIT',
 'ДОБАВИТЬ': 'ADD',
 'ПАТТЕРНЫ': 'PATTERNS',
 'ВИД': 'VIEW',
 'ПАРАМЕТРЫ': 'OPTIONS',
 'Позиция (щелчок — такты или минуты)': 'Position (click — bars or minutes)',
 'Громкость мастера': 'Master volume',
 'Плейлист (F5)': 'Playlist (F5)',
 'Стойка каналов (F6)': 'Channel rack (F6)',
 'Пианоролл (F7)': 'Piano roll (F7)',
 'Браузер (F8)': 'Browser (F8)',
 'Микшер (F9)': 'Mixer (F9)',
 'Сохранить проект (Ctrl+S)': 'Save project (Ctrl+S)',
 'Отменять нечего': 'Nothing to undo',
 'Повторять нечего': 'Nothing to redo',
 'Запись взведена: нажмите «играть» (пробел) и пойте, «стоп» — дубль ляжет в плейлист': 'Recording armed: press '
                                                                                        '“play” (space) and sing, '
                                                                                        '“stop” — the take goes into '
                                                                                        'the playlist',
 'Запись выключена': 'Recording off',
 'Прослушивание остановлено': 'Preview stopped',
 ' (щелчок ещё раз — стоп)': ' (click again — stop)',
 'Название паттерна': 'Pattern name',
 'Последний паттерн удалить нельзя': "The last pattern can't be deleted",
 'На дорожке нет свободных ячеек': 'No free slots on the track',
 'Слушаю…': 'Listening…',
 'Сохранить проект': 'Save project',
 'Открыть проект': 'Open project',
 'Проект студии (*.echoproj)': 'Studio project (*.echoproj)',
 'Сохранить в файл': 'Save to file',
 'Мой трек': 'My track',
 'Формат': 'Format',
 'Вывод (колонки / наушники)': 'Output (speakers / headphones)',
 'Микрофон для записи': 'Recording microphone',
 '\n\nСтойка каналов: щелчок по шагу — включить, правая кнопка — стереть, щелчок по имени — окно инструмента.\nПианоролл: щелчок — нота, тянуть край — длина, правая — удалить, Ctrl+рамка — выделить, стрелки — транспонировать.\nПлейлист: кисть ставит выбранный паттерн, двойной щелчок по аудиоклипу — громкость, затухания, тон и темп.\nМикшер: каналы идут на дорожки, на дорожках — до 10 эффектов, пресеты голоса — кнопкой справа.\nЗапись: R, затем пробел; дубль ложится в плейлист на канал «Голос».': '\n'
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     '\n'
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'Channel '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'rack: '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'click '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'a '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'step '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     '— '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'on, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'right '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'click '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     '— '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'erase, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'click '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'name '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     '— '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'instrument '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'window.\n'
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'Piano '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'roll: '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'click '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     '— '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'note, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'drag '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'edge '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     '— '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'length, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'right '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'click '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     '— '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'delete, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'Ctrl+box '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     '— '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'select, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'arrows '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     '— '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'transpose.\n'
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'Playlist: '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'brush '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'places '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'selected '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'pattern, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'double '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'click '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'an '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'audio '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'clip '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     '— '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'volume, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'fades, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'pitch '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'and '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'tempo.\n'
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'Mixer: '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'channels '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'go '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'to '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'tracks, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'each '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'track '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'has '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'up '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'to '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     '10 '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'effects, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'voice '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'presets '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     '— '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'button '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'on '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'right.\n'
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'Recording: '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'R, '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'then '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'space; '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'take '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'goes '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'into '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'playlist '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'on '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'the '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     '“Voice” '
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     'channel.',
 'Мэшап-бот (F10)': 'Mashup bot (F10)',
 'Клавиатура как пианино: Z S X D C V G B H N J M — нижняя октава, Q 2 W 3 E… — верхняя': 'Keyboard as a piano: Z S '
                                                                                          'X D C V G B H N J M — '
                                                                                          'lower octave, Q 2 W 3 E… '
                                                                                          '— upper',
 'Клавиатура как пианино выключена': 'Keyboard piano off',
 'ТАКТ:ДОЛЯ:ТИК': 'BAR:BEAT:TICK',
 'МИН:СЕК:СОТЫЕ': 'MIN:SEC:HUNDREDTHS',
 'ПАТ': 'PAT',
 'Аудиоканал: громкость и эффекты — на его дорожке микшера, клипы — в плейлисте': 'Audio channel: volume and effects '
                                                                                  '— on its mixer track, clips — in '
                                                                                  'the playlist',
 'Играет вся песня из плейлиста': 'Playing the whole song from the playlist',
 'Играет выбранный паттерн по кругу': 'Playing the selected pattern on loop',
 'Слушаю: ': 'Listening: ',
 'По умолчанию системы': 'System default',
 ' — проверьте его в «Параметры → Звук»': ' — check it in “Options → Audio”',
 'мастере': 'master',
 'Клип паттерна': 'Pattern clip',
 'Микрофон не открылся': "The microphone didn't open",
 'дорожке ': 'track ',
 ' — добавлен в библиотеку плеера': ' — added to the player library',
 'Ввести значение…': 'Enter value…',
 'Закрыть окно': 'Close window',
 'Развернуть / вернуть': 'Maximize / restore',
 '−∞ дБ': '−∞ dB',
 'Что это': 'What it is',
 'Без кода': 'No code',
 'События': 'Events',
 'Звук и плеер': 'Sound and player',
 'Рисование': 'Drawing',
 'Математика': 'Math',
 'Примеры': 'Examples',
 'Фон со свечением': 'Glowing background',
 'Залитый фон и два мягких пятна света, дышат от баса': 'Filled background with two soft light spots, breathing with '
                                                        'the bass',
 'Видеофон (без звука, по кругу), светлеет от баса': 'Video background (muted, looped), brightens with the bass',
 'Прямоугольник, круг, кольцо, звезда, многоугольник (sides), шестиугольник, треугольник': 'Rectangle, circle, ring, '
                                                                                           'star, polygon (sides), '
                                                                                           'hexagon, triangle',
 'Векторный контур (SVG)': 'Vector path (SVG)',
 'Любой контур в синтаксисе SVG (свойство d) — иконки, логотипы, свои фигуры': 'Any path in SVG syntax (property d) '
                                                                               '— icons, logos, custom shapes',
 'Живая капля': 'Living blob',
 'Мягкая колышущаяся фигура, дышит от баса и середины': 'A soft wobbling shape, breathing with the bass and mids',
 'Надпись; bind подставляет название, исполнителя, альбом или время': 'Text; bind inserts the title, artist, album '
                                                                      'or time',
 'Название и исполнитель': 'Title and artist',
 'Спектр': 'Spectrum',
 'Круговой спектр': 'Circular spectrum',
 'Искры на бит': 'Sparks on beat',
 'Вспышки частиц на ударах (с гравитацией)': 'Particle bursts on hits (with gravity)',
 'Кнопка управления: play, prev, next, shuffle, repeat (свойство action)': 'Control button: play, prev, next, '
                                                                           'shuffle, repeat (property action)',
 'Прогресс трека': 'Track progress',
 'Картинка с обрезкой по центру; анимированные GIF/WEBP проигрываются': 'Image cropped to the center; animated '
                                                                        'GIF/WEBP play',
 '"Текст"': '"Text"',
 'Две строки: название трека и исполнитель': 'Two lines: track title and artist',
 'Обложка трека (квадрат или вращающийся диск)': 'Track cover (square or spinning disc)',
 'Столбики спектра с плавным спадом': 'Spectrum bars with smooth fall-off',
 'Форма звуковой волны': 'Waveform',
 'Лучи спектра по кругу, вращаются от середины': 'Spectrum rays in a circle, spinning with the mids',
 'Полоса перемотки: клик и перетаскивание': 'Seek bar: click and drag',
 'Ползунок громкости: клик, перетаскивание, колесо': 'Volume slider: click, drag, wheel',
 'Текущий плейлист: колесо — прокрутка, клик — включить': 'Current playlist: wheel — scroll, click — play',
 'Клик': 'Click',
 'Нажатие': 'Press',
 'Колесо мыши': 'Mouse wheel',
 'Удар в музыке': 'Beat in the music',
 'Смена трека': 'Track change',
 'Курсор зашёл': 'Cursor entered',
 'Курсор ушёл': 'Cursor left',
 'Пауза / воспроизведение': 'Pause / play',
 'Перемешивание': 'Shuffle',
 'Режим повтора': 'Repeat mode',
 'Громкость +10%': 'Volume +10%',
 'Громкость −10%': 'Volume −10%',
 'Громкость колесом': 'Volume by wheel',
 'Перемотка колесом': 'Seek by wheel',
 'В начало трека': 'To the start of the track',
 'Записать в журнал': 'Write to the log',
 'Темы ▾': 'Themes ▾',
 'Выбрать тему': 'Choose theme',
 'Изменить тему': 'Edit theme',
 'Конструктор: добавляйте блоки, двигайте и настраивайте их мышью': 'Constructor: add blocks, move and tune them '
                                                                    'with the mouse',
 'Вернуть студию в плеер': 'Return the studio to the player',
 'Отдельное окно': 'Separate window',
 'Перетащите блок из конструктора на сцену  ·  щёлкните виджет, чтобы настроить его  ·  правая кнопка — меню': 'Drag '
                                                                                                               'a '
                                                                                                               'block '
                                                                                                               'from '
                                                                                                               'the '
                                                                                                               'constructor '
                                                                                                               'onto '
                                                                                                               'the '
                                                                                                               'stage  '
                                                                                                               '·  '
                                                                                                               'click '
                                                                                                               'a '
                                                                                                               'widget '
                                                                                                               'to '
                                                                                                               'tune '
                                                                                                               'it  '
                                                                                                               '·  '
                                                                                                               'right '
                                                                                                               'click '
                                                                                                               '— '
                                                                                                               'menu',
 'рисовать можно только в обработчике on draw': 'you can only draw in the on draw handler',
 'restore() без парного save()': 'restore() without a matching save()',
 'lines(): нужен список [x1, y1, x2, y2, …]': 'lines(): needs a list [x1, y1, x2, y2, …]',
 'точки — список [x1, y1, x2, y2, …]': 'points — a list [x1, y1, x2, y2, …]',
 'push(): первый аргумент — список': 'push(): the first argument must be a list',
 '   — создан в цикле, двигается только в коде': '   — created in a loop, moves only in code',
 'Второй цвет': 'Second color',
 'Скругление': 'Corner radius',
 'Контур, толщина': 'Outline, width',
 'Цвет контура': 'Outline color',
 'Стороны / лучи': 'Sides / rays',
 'Подставлять': 'Insert',
 'Жирность': 'Weight',
 'Реакция на звук': 'Sound reaction',
 'Столбиков': 'Bars',
 'Промежуток': 'Gap',
 'От центра': 'From center',
 'Толщина линии': 'Line width',
 'Лучей': 'Rays',
 'Оттенок, °': 'Hue, °',
 'Действие': 'Action',
 'Показывать время': 'Show time',
 'Высота строки': 'Row height',
 'Свечение вокруг': 'Glow around',
 'Свет 1': 'Light 1',
 'Свет 2': 'Light 2',
 'Точек': 'Points',
 'Колыхание': 'Wobble',
 'Контур (SVG)': 'Path (SVG)',
 'Обрезать по рамке': 'Clip to frame',
 'Запоминать картинку': 'Cache the image',
 'Разрешение': 'Resolution',
 'Нитей основы': 'Warp threads',
 'Рядов утка': 'Weft rows',
 'прямоугольник': 'rectangle',
 'круг': 'circle',
 'кольцо': 'ring',
 'звезда': 'star',
 'шестиугольник': 'hexagon',
 'треугольник': 'triangle',
 'многоугольник': 'polygon',
 'влево': 'left',
 'по центру': 'center',
 'вправо': 'right',
 'пауза / воспроизведение': 'pause / play',
 'предыдущий': 'previous',
 'следующий': 'next',
 'перемешать': 'shuffle',
 'повтор': 'repeat',
 'название трека': 'track title',
 'исполнитель': 'artist',
 'альбом': 'album',
 'время': 'time',
 'Акцент 2': 'Accent 2',
 'Акцент 3': 'Accent 3',
 'Приглушённый': 'Muted',
 'Панель': 'Panel',
 'Конструктор темы': 'Theme constructor',
 'Файл ▾': 'File ▾',
 'Двигать': 'Move',
 'Включено — виджеты на сцене выбираются и двигаются мышью (код обновляется сам).\nВыключите, чтобы нажимать кнопки сцены, как в плеере.\nСтрелки — сдвиг, Shift — крупнее и с пропорциями, Alt — без прилипания, Delete — удалить': 'On '
                                                                                                                                                                                                                                     '— '
                                                                                                                                                                                                                                     'widgets '
                                                                                                                                                                                                                                     'on '
                                                                                                                                                                                                                                     'the '
                                                                                                                                                                                                                                     'stage '
                                                                                                                                                                                                                                     'are '
                                                                                                                                                                                                                                     'selected '
                                                                                                                                                                                                                                     'and '
                                                                                                                                                                                                                                     'moved '
                                                                                                                                                                                                                                     'with '
                                                                                                                                                                                                                                     'the '
                                                                                                                                                                                                                                     'mouse '
                                                                                                                                                                                                                                     '(the '
                                                                                                                                                                                                                                     'code '
                                                                                                                                                                                                                                     'updates '
                                                                                                                                                                                                                                     'itself).\n'
                                                                                                                                                                                                                                     'Turn '
                                                                                                                                                                                                                                     'off '
                                                                                                                                                                                                                                     'to '
                                                                                                                                                                                                                                     'press '
                                                                                                                                                                                                                                     'the '
                                                                                                                                                                                                                                     'stage '
                                                                                                                                                                                                                                     'buttons '
                                                                                                                                                                                                                                     'like '
                                                                                                                                                                                                                                     'in '
                                                                                                                                                                                                                                     'the '
                                                                                                                                                                                                                                     'player.\n'
                                                                                                                                                                                                                                     'Arrows '
                                                                                                                                                                                                                                     '— '
                                                                                                                                                                                                                                     'nudge, '
                                                                                                                                                                                                                                     'Shift '
                                                                                                                                                                                                                                     '— '
                                                                                                                                                                                                                                     'bigger '
                                                                                                                                                                                                                                     'and '
                                                                                                                                                                                                                                     'keep '
                                                                                                                                                                                                                                     'proportions, '
                                                                                                                                                                                                                                     'Alt '
                                                                                                                                                                                                                                     '— '
                                                                                                                                                                                                                                     'no '
                                                                                                                                                                                                                                     'snapping, '
                                                                                                                                                                                                                                     'Delete '
                                                                                                                                                                                                                                     '— '
                                                                                                                                                                                                                                     'delete',
 'Отдельное окно / вернуть в плеер': 'Separate window / return to the player',
 'Закрыть конструктор (всё уже сохранено)': 'Close the constructor (everything is already saved)',
 'Журнал: log(...) и print(...) из скрипта, ошибки': 'Log: log(...) and print(...) from the script, errors',
 'Изменения применяются сами через полсекунды · Ctrl+S — сохранить · Ctrl+R — перезапустить сцену': 'Changes apply '
                                                                                                    'by themselves '
                                                                                                    'after half a '
                                                                                                    'second · Ctrl+S '
                                                                                                    '— save · Ctrl+R '
                                                                                                    '— restart the '
                                                                                                    'scene',
 'Конструктор': 'Constructor',
 'Код': 'Code',
 'Скорость сцены: кадров в секунду и время кадра (логика скрипта + рисование)': 'Scene speed: frames per second and '
                                                                                'frame time (script logic + drawing)',
 'Новый': 'New',
 'Готовый набор (обложка, кнопки, спектр, список)': 'Ready set (cover, buttons, spectrum, list)',
 'Из темы плеера': 'From a player theme',
 'Копия…': 'Copy…',
 'Взять цвета из темы': 'Take colors from a theme',
 'Импорт виджетов из скрипта': 'Import widgets from a script',
 'Импорт слоёв и фона из темы конструктора': 'Import layers and background from a constructor theme',
 'Экспорт в файл .echo…': 'Export to an .echo file…',
 'Импорт файла .echo…': 'Import an .echo file…',
 'Открыть папку скриптов': 'Open the scripts folder',
 'Рисовать видеокартой (GPU)': 'Draw with the GPU',
 'Сглаживание и свечение считает видеокарта — в 2–3 раза быстрее': 'Antialiasing and glow are computed by the GPU — '
                                                                   '2–3 times faster',
 'Студия в отдельном окне': 'Studio in a separate window',
 'С их расстановкой на сцене (иначе — только код, добавляйте сами)': 'With their placement on the stage (otherwise — '
                                                                     'code only, add them yourself)',
 'Новый скрипт из темы': 'New script from a theme',
 'видеокарта': 'GPU',
 'процессор': 'CPU',
 'Понятно': 'Got it',
 'ПОЛОЖЕНИЕ И РАЗМЕР, %': 'POSITION AND SIZE, %',
 'ЧТО ДЕЛАТЬ': 'WHAT IT DOES',
 'Дополнительно ▸': 'More ▸',
 'Цвета темы': 'Theme colors',
 'Выбрать свой цвет…': 'Pick a custom color…',
 'ВЫРОВНЯТЬ': 'ALIGN',
 'ГРУППА': 'GROUP',
 'Картинки и видео (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.mp4 *.webm *.mov *.mkv *.avi *.m4v);;Все файлы (*)': 'Images '
                                                                                                                 'and '
                                                                                                                 'videos '
                                                                                                                 '(*.png '
                                                                                                                 '*.jpg '
                                                                                                                 '*.jpeg '
                                                                                                                 '*.gif '
                                                                                                                 '*.webp '
                                                                                                                 '*.bmp '
                                                                                                                 '*.mp4 '
                                                                                                                 '*.webm '
                                                                                                                 '*.mov '
                                                                                                                 '*.mkv '
                                                                                                                 '*.avi '
                                                                                                                 '*.m4v);;All '
                                                                                                                 'files '
                                                                                                                 '(*)',
 'Новый скрипт': 'New script',
 'Копия скрипта': 'Copy of script',
 'Экспорт скрипта': 'Export script',
 'Импорт скрипта': 'Import script',
 'Вернуть встроенную версию? Ваши правки удалятся.': 'Restore the built-in version? Your edits will be deleted.',
 'других скриптов нет': 'no other scripts',
 'Какие виджеты перенести (вместе с нужными им функциями и цветами темы):': 'Which widgets to bring over (with the '
                                                                            'functions and theme colors they need):',
 'тем из конструктора нет': 'no constructor themes',
 ' (скрипт)': ' (script)',
 'Сбросить к встроенной версии': 'Reset to the built-in version',
 "<span style='color:#8cf0b4'>Сохранено</span>": "<span style='color:#8cf0b4'>Saved</span>",
 "<span style='color:#8cf0b4'>работает</span>": "<span style='color:#8cf0b4'>running</span>",
 'Видеокарта недоступна для рисования (нет OpenGL 2.0 или только программный драйвер) — сцена рисуется процессором.': 'The '
                                                                                                                      'GPU '
                                                                                                                      "isn't "
                                                                                                                      'available '
                                                                                                                      'for '
                                                                                                                      'drawing '
                                                                                                                      '(no '
                                                                                                                      'OpenGL '
                                                                                                                      '2.0 '
                                                                                                                      'or '
                                                                                                                      'only '
                                                                                                                      'a '
                                                                                                                      'software '
                                                                                                                      'driver) '
                                                                                                                      '— '
                                                                                                                      'the '
                                                                                                                      'scene '
                                                                                                                      'is '
                                                                                                                      'drawn '
                                                                                                                      'by '
                                                                                                                      'the '
                                                                                                                      'CPU.',
 '<b>Перетащите блок</b> из списка ниже на сцену (или просто щёлкните по нему).': '<b>Drag a block</b> from the list '
                                                                                  'below onto the stage (or just '
                                                                                  'click it).',
 '<b>Двигайте</b> виджет мышью, тяните за углы, чтобы изменить размер.': '<b>Move</b> the widget with the mouse, '
                                                                         'drag the corners to resize.',
 '<b>Настройте</b> его ниже: цвета, текст, файлы, что делать по клику.': '<b>Tune</b> it below: colors, text, files, '
                                                                         'what to do on click.',
 'Разгруппировать': 'Ungroup',
 'На передний план': 'Bring to front',
 'На задний план': 'Send to back',
 'Показать код': 'Show code',
 'Сделать копию рядом': 'Duplicate next to it',
 'Показать код этого виджета': "Show this widget's code",
 'Удалить со сцены (Delete)': 'Remove from the stage (Delete)',
 'Этот виджет создаётся в цикле —\nего свойства меняются в коде.': 'This widget is created in a loop —\n'
                                                                   'its properties are changed in code.',
 '— ничего —': '— nothing —',
 'Свой код…': 'Custom code…',
 'слой: больше — выше': 'layer: higher — on top',
 'общая группа выделяется вместе': 'a shared group is selected together',
 'обрезать рисование по рамке виджета': 'clip drawing to the widget frame',
 'рисовать один раз и запоминать картинку (для статичного)': 'draw once and cache the image (for static content)',
 '0.1…1 — рисовать в меньшем разрешении (только процессором)': '0.1…1 — draw at a lower resolution (CPU only)',
 'Вернуть значение по умолчанию': 'Reset to default',
 'Нет (без второго цвета)': 'None (no second color)',
 'Свой код события': 'Custom event code',
 'Функция EchoScript (параметры как у события: click(x, y), wheel(d), beat(power)…):': 'EchoScript function '
                                                                                       '(parameters as in the event: '
                                                                                       'click(x, y), wheel(d), '
                                                                                       'beat(power)…):',
 'Скрипт с таким названием уже есть.': 'A script with this name already exists.',
 'Встроенный скрипт переименовать нельзя — сделайте копию.': "A built-in script can't be renamed — make a copy.",
 '  · встроенный': '  · built-in',
 'превью': 'preview',
 'СВОЙСТВА\n\nЩёлкните по виджету на сцене,\nчтобы настроить его.\n\nCtrl+клик или рамка мышью —\nвыбрать несколько.': 'PROPERTIES\n'
                                                                                                                       '\n'
                                                                                                                       'Click '
                                                                                                                       'a '
                                                                                                                       'widget '
                                                                                                                       'on '
                                                                                                                       'the '
                                                                                                                       'stage\n'
                                                                                                                       'to '
                                                                                                                       'tune '
                                                                                                                       'it.\n'
                                                                                                                       '\n'
                                                                                                                       'Ctrl+click '
                                                                                                                       'or '
                                                                                                                       'a '
                                                                                                                       'mouse '
                                                                                                                       'box '
                                                                                                                       '—\n'
                                                                                                                       'select '
                                                                                                                       'several.',
 'СВОЙСТВА\n\nВключите «Двигать» вверху,\nчтобы выбирать виджеты на сцене.': 'PROPERTIES\n'
                                                                             '\n'
                                                                             'Turn on “Move” at the top\n'
                                                                             'to select widgets on the stage.',
 'свой код': 'custom code',
 'По левому краю': 'Align left',
 'По центру по горизонтали': 'Center horizontally',
 'По правому краю': 'Align right',
 'По верху': 'Align top',
 'По центру по вертикали': 'Center vertically',
 'По низу': 'Align bottom',
 '↔ поровну': '↔ evenly',
 'Распределить по горизонтали с равными промежутками': 'Distribute horizontally with equal gaps',
 '↕ поровну': '↕ evenly',
 'Распределить по вертикали с равными промежутками': 'Distribute vertically with equal gaps',
 '= ширина': '= width',
 'Ширина как у последнего выбранного': 'Width like the last selected',
 '= высота': '= height',
 'Высота как у последнего выбранного': 'Height like the last selected',
 'Сгруппировать': 'Group',
 'Выбираются и двигаются вместе (свойство group)': 'Selected and moved together (property group)',
 'Убрать свойство group': 'Remove the group property',
 'Удалить выбранные': 'Delete selected',
 'группы: ': 'groups: ',
 '  · изменён': '  · modified',
 '\nПеретащите на сцену или щёлкните, чтобы добавить': '\nDrag onto the stage or click to add',
 '» в коде — это действие выполнится вдобавок': '» in code — this action runs in addition',
 'У виджета уже есть «on ': 'The widget already has «on ',
 'Дополнительно ▾': 'More ▾',
 'по умолчанию': 'default',
 'Значение — выражение EchoScript': 'Value — an EchoScript expression',
 'выражение: ': 'expression: ',
 'Винил': 'Vinyl',
 'Настоящая пластинка плеера: крутится, пока играет музыка; обложка — в центре': "The player's real record: spins "
                                                                                 'while music plays; the cover is in '
                                                                                 'the center',
 'в скрипте нет ни одного widget { … }': 'the script has no widget { … }',
 'Не удалось записать теги для этого формата.\nПопробуйте другой формат или проверьте права на файл.': "Couldn't "
                                                                                                       'write tags '
                                                                                                       'for this '
                                                                                                       'format.\n'
                                                                                                       'Try another '
                                                                                                       'format or '
                                                                                                       'check the '
                                                                                                       'file '
                                                                                                       'permissions.',
 'Ошибка обложки': 'Cover error',
 'Не удалось записать обложку в тег файла.': "Couldn't write the cover into the file tag.",
 'Не удалось записать тег. Попробуйте «Сохранить в .lrc».': "Couldn't write the tag. Try “Save to .lrc”.",
 'Для каждого играющего трека плеер в фоне найдёт и скачает официальный клип\n(YouTube), чтобы режим «Клип» открывался сразу. Выключено — клип скачивается\nкнопкой «Скачать клип» в самом режиме. Клипы лежат в ~/Echoes/clips.': 'For '
                                                                                                                                                                                                                                         'every '
                                                                                                                                                                                                                                         'playing '
                                                                                                                                                                                                                                         'track '
                                                                                                                                                                                                                                         'the '
                                                                                                                                                                                                                                         'player '
                                                                                                                                                                                                                                         'will '
                                                                                                                                                                                                                                         'find '
                                                                                                                                                                                                                                         'and '
                                                                                                                                                                                                                                         'download '
                                                                                                                                                                                                                                         'the '
                                                                                                                                                                                                                                         'official '
                                                                                                                                                                                                                                         'video\n'
                                                                                                                                                                                                                                         '(YouTube) '
                                                                                                                                                                                                                                         'in '
                                                                                                                                                                                                                                         'the '
                                                                                                                                                                                                                                         'background, '
                                                                                                                                                                                                                                         'so '
                                                                                                                                                                                                                                         '“Video” '
                                                                                                                                                                                                                                         'mode '
                                                                                                                                                                                                                                         'opens '
                                                                                                                                                                                                                                         'instantly. '
                                                                                                                                                                                                                                         'Off '
                                                                                                                                                                                                                                         '— '
                                                                                                                                                                                                                                         'the '
                                                                                                                                                                                                                                         'video '
                                                                                                                                                                                                                                         'is '
                                                                                                                                                                                                                                         'downloaded\n'
                                                                                                                                                                                                                                         'with '
                                                                                                                                                                                                                                         'the '
                                                                                                                                                                                                                                         '“Download '
                                                                                                                                                                                                                                         'video” '
                                                                                                                                                                                                                                         'button '
                                                                                                                                                                                                                                         'in '
                                                                                                                                                                                                                                         'the '
                                                                                                                                                                                                                                         'mode '
                                                                                                                                                                                                                                         'itself. '
                                                                                                                                                                                                                                         'Videos '
                                                                                                                                                                                                                                         'are '
                                                                                                                                                                                                                                         'stored '
                                                                                                                                                                                                                                         'in '
                                                                                                                                                                                                                                         '~/Echoes/clips.',
 'Пустой плейлист, из файла друга или из Spotify': "Empty playlist, from a friend's file or from Spotify",
 'Клип': 'Video',
 'Официальный клип песни: смотреть, скачать, эффекты (Ctrl+Shift+K)': "The song's official video: watch, download, effects "
                                                                '(Ctrl+Shift+K)',
 'Язык / Language': 'Language',
 'Язык всего интерфейса во всех темах · Interface language for all themes': 'Interface language for all themes',
 'Клипы': 'Videos',
 'Скачивать официальные клипы сами': 'Download official videos automatically',
 'Качество клипов': 'Video quality',
 'Открыть клип': 'Open video',
 'Клип песни (Ctrl+Shift+K)': 'Song video (Ctrl+Shift+K)',
 'Restart ECHOES now to switch the language?\nПерезапустить ECHOES сейчас, чтобы сменить язык?': 'Restart ECHOES now '
                                                                                                 'to switch the '
                                                                                                 'language?',
 'Пустой плейлист': 'Empty playlist',
 'Из файла (от друга)…': 'From a file (from a friend)…',
 'Из Spotify…': 'From Spotify…',
 'Куда класть файлы тем и плейлистов?': 'Where to put theme and playlist files?',
 'Поделиться файлом…': 'Share as a file…',
 'Маленький файл со списком треков — у друга недостающие скачаются сами': 'A small file with the track list — your '
                                                                          "friend's missing tracks download by "
                                                                          'themselves',
 'Русский': 'Russian',
 'Кнопка «Клип»': '“Video” button',
 'Язык': 'Language',
 'Не получилось подключить этот файл как шрифт.': "Couldn't use this file as a font.",
 'поиск нашёл другой трек (не совпала длительность)': "search found a different track (duration didn't match)",
 'SoundCloud не отдал файл': "SoundCloud didn't return the file",
 ' — на YouTube Music точного совпадения нет': ' — no exact match on YouTube Music',
 'Сложность': 'Difficulty',
 'Попыток': 'Attempts',
 'Пройдено': 'Passed',
 'Провалов': 'Failed',
 'Выходов': 'Quit',
 'Первое прохождение': 'First pass',
 'Лучшая точность': 'Best accuracy',
 'Последняя игра': 'Last played',
 'Попытки по картам': 'Attempts per map',
 'Найти трек или исполнителя…': 'Find a track or artist…',
 'Попытка — каждый запуск карты (без Auto, просмотра повторов и проверки из редактора). Выход и быстрый рестарт тоже считаются попыткой. Двойной щелчок — открыть карту. ': 'An '
                                                                                                                                                                            'attempt '
                                                                                                                                                                            'is '
                                                                                                                                                                            'every '
                                                                                                                                                                            'map '
                                                                                                                                                                            'start '
                                                                                                                                                                            '(excluding '
                                                                                                                                                                            'Auto, '
                                                                                                                                                                            'watching '
                                                                                                                                                                            'replays '
                                                                                                                                                                            'and '
                                                                                                                                                                            'testing '
                                                                                                                                                                            'from '
                                                                                                                                                                            'the '
                                                                                                                                                                            'editor). '
                                                                                                                                                                            'Quitting '
                                                                                                                                                                            'and '
                                                                                                                                                                            'quick '
                                                                                                                                                                            'restart '
                                                                                                                                                                            'also '
                                                                                                                                                                            'count. '
                                                                                                                                                                            'Double '
                                                                                                                                                                            'click '
                                                                                                                                                                            '— '
                                                                                                                                                                            'open '
                                                                                                                                                                            'the '
                                                                                                                                                                            'map. ',
 'Для карт, сыгранных до появления счётчика, известны только прохождения из рекордов.': 'For maps played before the '
                                                                                        'counter existed, only '
                                                                                        'passes from the scores are '
                                                                                        'known.',
 'с 1-й': 'on the 1st',
 'до учёта': 'before tracking',
 'ещё нет': 'not yet',
 'Попытки и рекорды': 'Attempts and scores',
 'Группировать': 'Group',
 'Сортировать': 'Sort',
 'По длине': 'By length',
 'Поиск:': 'Search:',
 'назад': 'back',
 'Упрощение игры': 'Difficulty Reduction',
 'Усложнение игры': 'Difficulty Increase',
 'Особые': 'Special',
 'Что вы хотите сделать с этой картой?': 'What do you want to do with this beatmap?',
 'Поиск: исполнитель или название…': 'Search: artist or title…',
 'карты нет — F4': 'no map — F4',
 'Коллекции': 'Collections',
 'Моя музыка': 'My music',
 'Всё вместе': 'All together',
 'введите название': 'type to search',
 'Рекордов пока нет!': 'No records set!',
 'Тема': 'Theme',
 'Моды': 'Mods',
 'Случайно': 'Random',
 'Карта': 'Beatmap',
 'Моды влияют на процесс игры. Некоторые из них изменяют количество получаемых': 'Mods change gameplay. Some of them '
                                                                                 'change the amount of points you '
                                                                                 'get,',
 'очков, а некоторые придуманы просто так, для развлечения.': 'and some are just for fun.',
 '1. Сбросить все моды': '1. Reset all mods',
 '2. Закрыть': '2. Close',
 'Выбрать трек…': 'Pick a track…',
 'С припева (как превью карты)': 'From the chorus (like the map preview)',
 'Снег из скина в меню (menu-snow)': 'Snow from the skin in the menu (menu-snow)',
 'Режим редактора: Enter или щелчок по сложности откроет редактор карты': 'Editor mode: Enter or clicking a '
                                                                          'difficulty opens the map editor',
 'Сгенерировать заново / выбрать отрывок  F4': 'Generate again / pick a section  F4',
 'игрок': 'player',
 'Только для стиля «классика». Выключите — будет прежний вид выбора песни.': 'Only for the “classic” style. Turn off '
                                                                             '— the previous song select look.',
 'Сортировка': 'Sorting',
 'Как упорядочить песни?': 'How should the songs be ordered?',
 'Группировка': 'Grouping',
 'Какие песни показывать?': 'Which songs to show?',
 'Карты ещё нет — нажмите «Сгенерировать карту» (F4)': 'No map yet — press “Generate map” (F4)',
 'Карта: ECHOES AI': 'Map: ECHOES AI',
 'Открываю карту': 'Opening the map',
 'Модель слушает трек': 'The model is listening to the track',
 'Карта строится…': 'Building the map…',
 'Сгенерировать карту  F4': 'Generate map  F4',
 'У карты есть видео — ': 'The map has a video — ',
 'Клип скачан — ': 'Video downloaded — ',
 'Скачать клип песни для фона карты': "Download the song's video for the map background",
 'что играло': 'what was playing',
 'случайный трек': 'random track',
 'выбранный трек': 'chosen track',
 'трек не выбран': 'no track chosen',
 'не удалось': 'failed',
 'оно будет фоном': 'it will be the background',
 'выключено': 'off',
 'он будет фоном карты': 'it will be the map background',
 'фон: обложка': 'background: cover',
 'не удалось: ': 'failed: ',
 'карты нет — «Сгенерировать карту» (F4)': 'no map — “Generate map” (F4)',
 'Выбор': 'Select',
 'Слайдер': 'Slider',
 'Спиннер': 'Spinner',
 'Правки удалены — вернётся сгенерированная карта': 'Edits removed — the generated map is back',
 'Размер кругов (CS)': 'Circle size (CS)',
 'Скорость появления (AR)': 'Approach rate (AR)',
 'Точность (OD)': 'Accuracy (OD)',
 'Здоровье (HP)': 'Health (HP)',
 'Делитель долей': 'Beat divisor',
 'Возвращено': 'Restored',
 'Пустую карту не сохраняю — поставьте хотя бы один объект': 'Not saving an empty map — place at least one object',
 'На карте нет объектов': 'The map has no objects',
 'Есть несохранённые правки: Ctrl+S — сохранить, Esc ещё раз — выйти без сохранения': 'Unsaved edits: Ctrl+S — save, '
                                                                                      'Esc again — quit without '
                                                                                      'saving',
 'Комбо': 'Combo',
 'Пробел': 'Space',
 'Проверить': 'Test',
 'Вернуть сгенерированную': 'Restore the generated one',
 '1–4 — инструменты': '1–4 — tools',
 'Колесо, стрелки — шаг по долям': 'Wheel, arrows — step by beats',
 '[ ] — делитель долей': '[ ] — beat divisor',
 'Q — новое комбо, W/E/R — звуки': 'Q — new combo, W/E/R — sounds',
 'Слайдер: щелчки, правая кнопка — готово': 'Slider: clicks, right click — done',
 'Пробел — играть, F5 — проверить': 'Space — play, F5 — test',
 'Ctrl+Z / Ctrl+Y — отмена': 'Ctrl+Z / Ctrl+Y — undo',
 'Ctrl+S — сохранить': 'Ctrl+S — save',
 'Слайдеру нужно хотя бы две точки': 'A slider needs at least two points',
 'Следующий объект — с нового комбо': 'Next object — new combo',
 'Новое комбо: выкл': 'New combo: off',
 'Новое комбо': 'New combo',
 'Удалить (Delete)': 'Delete (Delete)',
 '  · правка': '  · edited',
 'Свист': 'Whistle',
 'Финиш': 'Finish',
 'Влево': 'Left',
 'Вправо': 'Right',
 'Вверх': 'Up',
 'Левая кнопка (K1)': 'Left button (K1)',
 'Правая кнопка (K2)': 'Right button (K2)',
 'Пауза / продолжить': 'Pause / resume',
 'Быстрый рестарт': 'Quick restart',
 'Пропустить вступление': 'Skip intro',
 'Скрыть / показать интерфейс игры': 'Hide / show the game interface',
 'Продолжить': 'Continue',
 'Заново': 'Retry',
 'Выйти в меню': 'Back to menu',
 'об/мин': 'rpm',
 'Провал': 'Failed',
 'Наведите курсор и нажмите клавишу': 'Hover and press a key',
 'КРУТИ!': 'SPIN!',
 'ПРОПУСТИТЬ ▸▸': 'SKIP ▸▸',
 'АВТОИГРА': 'AUTOPLAY',
 'ПОВТОР': 'REPLAY',
 'Интерфейс игры: ': 'Game interface: ',
 'показан': 'shown',
 'скрыт': 'hidden',
 'Сгенерировать карту': 'Generate map',
 'Карта строится только по выделенному отрывку. Тяните розовые края, двигайте выделение за середину; щелчок по волне — послушать с этого места.': 'The '
                                                                                                                                                  'map '
                                                                                                                                                  'is '
                                                                                                                                                  'built '
                                                                                                                                                  'only '
                                                                                                                                                  'from '
                                                                                                                                                  'the '
                                                                                                                                                  'selected '
                                                                                                                                                  'section. '
                                                                                                                                                  'Drag '
                                                                                                                                                  'the '
                                                                                                                                                  'pink '
                                                                                                                                                  'edges, '
                                                                                                                                                  'move '
                                                                                                                                                  'the '
                                                                                                                                                  'selection '
                                                                                                                                                  'by '
                                                                                                                                                  'its '
                                                                                                                                                  'middle; '
                                                                                                                                                  'click '
                                                                                                                                                  'the '
                                                                                                                                                  'waveform '
                                                                                                                                                  '— '
                                                                                                                                                  'listen '
                                                                                                                                                  'from '
                                                                                                                                                  'there.',
 'Слушать отрывок': 'Listen to the section',
 'Сгенерировать': 'Generate',
 'Весь трек': 'Whole track',
 'Слушаю: спектр…': 'Listening: spectrum…',
 'Ищу темп и начала ударов…': 'Finding the tempo and beat onsets…',
 'Слушаю удары…': 'Listening to the hits…',
 'Такты и части песни…': 'Bars and song sections…',
 'Слушаю мелодию, голос и ударные…': 'Listening to the melody, voice and drums…',
 'Те же пресеты, что в настройках плеера': 'The same presets as in the player settings',
 'Сбросить эквалайзер': 'Reset equalizer',
 'Это эквалайзер плеера: изменения сразу слышны и сохраняются в его настройках.': "This is the player's equalizer: "
                                                                                  'changes are heard immediately and '
                                                                                  'saved in its settings.',
 'Громкость музыки': 'Music volume',
 'Громкость хитсаундов': 'Hitsound volume',
 'Смещение звука (+ — ноты позже)': 'Audio offset (+ — notes later)',
 'Затемнение фона': 'Background dim',
 'Размыть фон': 'Blur background',
 'Фон пульсирует в припевах': 'Background pulses in choruses',
 'Счёт, здоровье и комбо': 'Score, health and combo',
 'Шкала ошибок попадания': 'Hit error meter',
 'Счётчик нажатий клавиш': 'Key counter',
 'След курсора': 'Cursor trail',
 'Размер курсора': 'Cursor size',
 'Чувствительность': 'Sensitivity',
 'Перенести из игры…': 'Import from a game…',
 'Чувствительность из Roblox, RIVALS, CS2, Valorant, Fortnite и других': 'Sensitivity from Roblox, RIVALS, CS2, '
                                                                         'Valorant, Fortnite and others',
 'Сбросить настройки': 'Reset settings',
 'Хитсаунды, смещение, фон, интерфейс игры, курсор и чувствительность — как по умолчанию (громкость музыки не меняется)': 'Hitsounds, '
                                                                                                                          'offset, '
                                                                                                                          'background, '
                                                                                                                          'game '
                                                                                                                          'interface, '
                                                                                                                          'cursor '
                                                                                                                          'and '
                                                                                                                          'sensitivity '
                                                                                                                          '— '
                                                                                                                          'back '
                                                                                                                          'to '
                                                                                                                          'defaults '
                                                                                                                          '(music '
                                                                                                                          'volume '
                                                                                                                          "doesn't "
                                                                                                                          'change)',
 'Звук': 'Audio',
 'Фон карты': 'Map background',
 'Интерфейс игры': 'Game interface',
 'Ввод': 'Input',
 'Roblox (обычная камера)': 'Roblox (default camera)',
 'Чувствительность камеры': 'Camera sensitivity',
 'Чувствительность в RIVALS': 'Sensitivity in RIVALS',
 'Чувствительность Roblox': 'Roblox sensitivity',
 'Чувствительность X, %': 'Sensitivity X, %',
 'Roblox: Arsenal, BedWars, Da Hood и др. (камера Roblox)': 'Roblox: Arsenal, BedWars, Da Hood, etc. (Roblox camera)',
 'Чувствительность камеры Roblox': 'Roblox camera sensitivity',
 'Quake Champions / Quake Live / старые CoD': 'Quake Champions / Quake Live / old CoD',
 'Чувствительность мыши': 'Mouse sensitivity',
 'Чувствительность (множитель 0.02)': 'Sensitivity (multiplier 0.02)',
 'Чувствительность, % (0–200)': 'Sensitivity, % (0–200)',
 'Любая игра: см на 360°': 'Any game: cm per 360°',
 'Сантиметров на полный оборот': 'Centimeters per full turn',
 'Любая игра: градусов на отсчёт': 'Any game: degrees per count',
 'Градусов на отсчёт (yaw × sens)': 'Degrees per count (yaw × sens)',
 'Перенос чувствительности из игры': 'Import sensitivity from a game',
 'Перенос чувствительности': 'Sensitivity import',
 'Игра': 'Game',
 'Поле зрения (по горизонтали)': 'Field of view (horizontal)',
 'DPI мыши в игре': 'Mouse DPI in the game',
 'Для Roblox: скорость указателя Windows 6/11 и без «повышенной точности».': 'For Roblox: Windows pointer speed 6/11 '
                                                                             'and no “enhanced precision”.',
 'Яркие': 'Bright',
 'Пастель': 'Pastel',
 'Ctrl+Enter в выборе песни — смотреть, как карту проходит Auto': 'Ctrl+Enter in song select — watch Auto play the '
                                                                  'map',
 'F1 — моды, F2 — случайная песня, просто печатайте для поиска': 'F1 — mods, F2 — random song, just type to search',
 '~ (тильда) — мгновенный перезапуск карты': '~ (tilde) — instant map restart',
 'Скачайте клип песни (Ctrl+Shift+K) — и он станет фоном карты': "Download the song's video (Ctrl+Shift+K) — and it becomes the "
                                                           'map background',
 'Колесо мыши в меню — громкость': 'Mouse wheel in the menu — volume',
 'В настройках можно включить raw input и подобрать чувствительность': 'In settings you can turn on raw input and '
                                                                       'match your sensitivity',
 'Понижение сложности': 'Difficulty Reduction',
 'Повышение сложности': 'Difficulty Increase',
 'Попыток на этой сложности пока нет': 'No attempts on this difficulty yet',
 '  ·  ещё не пройдена': '  ·  not passed yet',
 'Редактор': 'Editor',
 'Настройки': 'Settings',
 'Редактор карт': 'Map editor',
 'Свободная игра — выбор песни': 'Free play — song select',
 'Библиотека ECHOES': 'ECHOES library',
 'ничего не играет': 'nothing is playing',
 'Сменить тему ▾': 'Change theme ▾',
 'по названию': 'by title',
 'по исполнителю': 'by artist',
 'по длине': 'by length',
 'по добавлению': 'by date added',
 'Лучшие результаты (на этом компьютере)': 'Top scores (on this computer)',
 'Модификаторы': 'Mods',
 'Попытки по картам…': 'Attempts per map…',
 'Выбрать папку Songs…': 'Choose the Songs folder…',
 'Карта ECHOES AI': 'ECHOES AI map',
 'Макс. комбо': 'Max combo',
 'Точность': 'Accuracy',
 'здоровье по ходу карты': 'health over the map',
 'нажмите клавишу…': 'press a key…',
 'Удалить выбранный скин': 'Delete the selected skin',
 'Фон главного меню из скина (menu-background)': 'Main menu background from the skin (menu-background)',
 'Перенести чувствительность из игры (Roblox, RIVALS, CS2, Valorant…)': 'Import sensitivity from a game (Roblox, '
                                                                        'RIVALS, CS2, Valorant…)',
 'Raw input (без ускорения Windows)': 'Raw input (no Windows acceleration)',
 'Не выпускать курсор из окна во время игры': 'Keep the cursor inside the window while playing',
 'Кнопки мыши тоже нажимают ноты': 'Mouse buttons also hit notes',
 'Клавиши': 'Keys',
 'Нажмите на кнопку, затем нужную клавишу. Esc — отмена, Backspace — убрать клавишу. Клавиши узнаются по месту на клавиатуре, поэтому работают и в русской раскладке. Если клавиша уже занята, действия меняются местами.': 'Click '
                                                                                                                                                                                                                            'a '
                                                                                                                                                                                                                            'button, '
                                                                                                                                                                                                                            'then '
                                                                                                                                                                                                                            'the '
                                                                                                                                                                                                                            'key '
                                                                                                                                                                                                                            'you '
                                                                                                                                                                                                                            'want. '
                                                                                                                                                                                                                            'Esc '
                                                                                                                                                                                                                            '— '
                                                                                                                                                                                                                            'cancel, '
                                                                                                                                                                                                                            'Backspace '
                                                                                                                                                                                                                            '— '
                                                                                                                                                                                                                            'clear '
                                                                                                                                                                                                                            'the '
                                                                                                                                                                                                                            'key. '
                                                                                                                                                                                                                            'Keys '
                                                                                                                                                                                                                            'are '
                                                                                                                                                                                                                            'recognized '
                                                                                                                                                                                                                            'by '
                                                                                                                                                                                                                            'their '
                                                                                                                                                                                                                            'position '
                                                                                                                                                                                                                            'on '
                                                                                                                                                                                                                            'the '
                                                                                                                                                                                                                            'keyboard, '
                                                                                                                                                                                                                            'so '
                                                                                                                                                                                                                            'they '
                                                                                                                                                                                                                            'work '
                                                                                                                                                                                                                            'in '
                                                                                                                                                                                                                            'any '
                                                                                                                                                                                                                            'layout. '
                                                                                                                                                                                                                            'If '
                                                                                                                                                                                                                            'a '
                                                                                                                                                                                                                            'key '
                                                                                                                                                                                                                            'is '
                                                                                                                                                                                                                            'already '
                                                                                                                                                                                                                            'taken, '
                                                                                                                                                                                                                            'the '
                                                                                                                                                                                                                            'actions '
                                                                                                                                                                                                                            'swap.',
 'Сбросить клавиши': 'Reset keys',
 'Отсчёт «3, 2, 1, GO!» перед картой': '“3, 2, 1, GO!” countdown before the map',
 'Таблица рекордов слева во время игры': 'Leaderboard on the left while playing',
 'Замедление музыки при провале': 'Slow the music down on fail',
 'Графика': 'Graphics',
 'Подсветка попаданий': 'Hit lighting',
 'Искры при попаданиях': 'Sparks on hits',
 'Слайдеры выползают «змейкой»': 'Snaking sliders',
 'Дорожки между нотами (follow points)': 'Follow points between notes',
 'Вспышки и фонтаны звёзд в припевах (kiai)': 'Flashes and star fountains in choruses (kiai)',
 'Фон пульсирует в такт в kiai': 'Background pulses to the beat in kiai',
 'Показывать «300»': 'Show “300”',
 'Вспышка счётчика комбо': 'Combo counter flash',
 'Волны от нажатий': 'Ripples on presses',
 'Показывать интерфейс в игре (счёт, HP, комбо)': 'Show the game interface (score, HP, combo)',
 'Параллакс фона в меню': 'Menu background parallax',
 'Цвета нот': 'Note colors',
 'Хитсаунды из папки карты (свои звуки маппера)': "Hitsounds from the map folder (the mapper's own sounds)",
 'Цвета комбо из карты': 'Combo colors from the map',
 'Скин карты (свои картинки нот в папке карты — поверх скина)': 'Beatmap skin (note images in the map folder — over '
                                                                'the skin)',
 'Видео карты как фон (если есть)': 'Map video as the background (if any)',
 'Генератор карт': 'Map generator',
 'Плотность нот': 'Note density',
 'Размах прыжков': 'Jump spacing',
 'Слайдеры': 'Sliders',
 'Сбросить настройки генератора': 'Reset generator settings',
 'Эквалайзер, эффекты, таймеры и остальные настройки плеера:': 'Equalizer, effects, timers and other player '
                                                               'settings:',
 'Сменить тему плеера…': 'Change player theme…',
 'Модель строит другой вариант карт…': 'The model is building another version of the maps…',
 'часа': 'hours',
 'часов': 'hours',
 'минута': 'minute',
 'минуты': 'minutes',
 'минут': 'minutes',
 'Совет: ': 'Tip: ',
 'Карта создана моделью ECHOES (по ударам и частям песни)': 'Map made by the ECHOES model (from the beats and song '
                                                            'sections)',
 'Карты ещё нет — нажмите «Сгенерировать карту» (F4): весь трек или только отрывок': 'No map yet — press “Generate '
                                                                                     'map” (F4): the whole track or '
                                                                                     'just a section',
 'Печатайте для поиска…': 'Type to search…',
 'все карты': 'all maps',
 'Моды  F1': 'Mods  F1',
 'Случайно  F2': 'Random  F2',
 'Карта…  F3': 'Beatmap…  F3',
 'Только моя музыка': 'Only my music',
 'Редактор карты (Ctrl+E)': 'Map editor (Ctrl+E)',
 'Сгенерировать карту / выбрать отрывок…  (F4)': 'Generate map / pick a section…  (F4)',
 'Сгенерировать заново (другой вариант)': 'Generate again (another version)',
 'Открыть папку карт': 'Open the maps folder',
 'Смотреть Auto (Ctrl+Enter)': 'Watch Auto (Ctrl+Enter)',
 'Карта ещё строится — подождите пару секунд': 'The map is still building — wait a couple of seconds',
 ' — первое прохождение!': ' — first pass!',
 'ПРОВАЛ': 'FAILED',
 'Смотреть повтор': 'Watch replay',
 'Подогнать смещение': 'Adjust offset',
 'Скин': 'Skin',
 'Папка скина…': 'Skin folder…',
 'Отдельный вывод звука для хитсаундов недоступен (нет sounddevice или устройства).': 'A separate audio output for '
                                                                                      "hitsounds isn't available (no "
                                                                                      'sounddevice or device).',
 'Папка Songs…': 'Songs folder…',
 'Стримы на сложных картах': 'Streams on hard maps',
 'Спиннеры': 'Spinners',
 'Симметричные паттерны': 'Symmetric patterns',
 'Ищу и качаю официальный клип…': 'Finding and downloading the official video…',
 'Открываю карту…': 'Opening the map…',
 'набор не найден': 'set not found',
 'Открываю карты…': 'Opening the maps…',
 'Модель строит карту': 'The model is building the map',
 'Сначала дождитесь, пока карта построится': 'Wait until the map is built first',
 'Этого трека уже нет в коллекции': 'This track is no longer in the collection',
 'секунда': 'second',
 'секунды': 'seconds',
 'секунд': 'seconds',
 'карта': 'map',
 'карты': 'maps',
 'карт': 'maps',
 'всё': 'all',
 'моя музыка': 'my music',
 'Пока нет — сыграйте первым!': 'None yet — be the first to play!',
 'Открыть папку этой карты': "Open this map's folder",
 'Карта ещё открывается — подождите секунду': 'The map is still opening — wait a second',
 'НОВЫЙ РЕКОРД!': 'NEW RECORD!',
 'Клип песни (если скачан)': 'Song video (if downloaded)',
 'Клип не найден: ': 'Video not found: ',
 ' по всему треку…': ' over the whole track…',
 'Сортировка: ': 'Sort: ',
 'выключено в настройках': 'off in settings',
 'фон: обложка (смените в настройках)': 'background: cover (change in settings)',
 'позже': 'later',
 'раньше': 'earlier',
 'Генератор: настройки по умолчанию': 'Generator: default settings',
 'Повтор этого результата не сохранился': "The replay of this score wasn't saved",
 'название': 'title',
 'длина': 'length',
 'добавлено': 'added',
 'Удар (normal)': 'Hit (normal)',
 'Удар (soft)': 'Hit (soft)',
 'Удар (drum)': 'Hit (drum)',
 'Свисток (whistle)': 'Whistle',
 'Тарелка (finish)': 'Finish',
 'Хлопок (clap)': 'Clap',
 'Тик слайдера': 'Slider tick',
 'Конец слайдера': 'Slider end',
 'Вращение спиннера': 'Spinner spin',
 'Бонус спиннера': 'Spinner bonus',
 'Сброс комбо': 'Combo break',
 'Отсчёт «3»': 'Countdown “3”',
 'Отсчёт «2»': 'Countdown “2”',
 'Отсчёт «1»': 'Countdown “1”',
 'Секция пройдена': 'Section pass',
 'Секция провалена': 'Section fail',
 'Аплодисменты': 'Applause',
 'Меню: выбор': 'Menu: select',
 'Меню: клик': 'Menu: click',
 'Меню: назад': 'Menu: back',
 'Меню: наведение': 'Menu: hover',
 'Вход в меню': 'Menu enter',
 'Комбо-бёрст': 'Combo burst',
 'Мод включён': 'Mod on',
 'Мод выключен': 'Mod off',
 'Выбор: раскрыть набор': 'Select: expand set',
 'Выбор: сложность': 'Select: difficulty',
 'Экран результатов': 'Results screen',
 'Сердцебиение печеньки': 'Cookie heartbeat',
 'Меню: Play': 'Menu: Play',
 'Меню: Edit': 'Menu: Edit',
 'Меню: Options': 'Menu: Options',
 'Меню: Exit': 'Menu: Exit',
 'Меню: Solo': 'Menu: Solo',
 'Моды F1': 'Mods F1',
 'Случайно F2': 'Random F2',
 'Карта F3': 'Beatmap F3',
 'печатайте для поиска…': 'type to search…',
 'Свои хитсаунды': 'Custom hitsounds',
 'Все — встроенные': 'All built-in',
 'Звук (*.wav *.ogg *.mp3 *.flac *.m4a *.opus)': 'Audio (*.wav *.ogg *.mp3 *.flac *.m4a *.opus)',
 'ОФОРМЛЕНИЕ': 'LOOK',
 'Y2K — минимал': 'Y2K — minimal',
 'СВОИ ХИТСАУНДЫ': 'CUSTOM HITSOUNDS',
 'Хитсаунды…': 'Hitsounds…',
 'Послушать': 'Listen',
 'Встроенный звук': 'Built-in sound',
 'Стиль темы': 'Theme style',
 'поиск: ': 'search: ',
 'сорт: ': 'sort: ',
 'вся библиотека': 'whole library',
 'ГЕНЕРАТОР КАРТ': 'MAP GENERATOR',
 'свой: ': 'custom: ',
 'встроенный': 'built-in',
 'из скина: ': 'from skin: ',
 'Свободно': 'Free',
 '16:9 — широкий': '16:9 — widescreen',
 '4:3 — классический': '4:3 — classic',
 '21:9 — ультраширокий': '21:9 — ultrawide',
 '1:1 — квадрат': '1:1 — square',
 '9:16 — вертикальный': '9:16 — vertical',
 'Клавиши и окно': 'Keys and window',
 'Работают везде — даже когда плеер свёрнут или в другом окне': 'Work everywhere — even when the player is minimized '
                                                                'or in another window',
 'Сбросить как было': 'Reset to defaults',
 'Горячие клавиши': 'Hotkeys',
 'Щёлкните по полю и нажмите сочетание. Пусто — без клавиши.': 'Click a field and press a combination. Empty — no '
                                                               'key.',
 'Без клавиши': 'No key',
 'Размер окна': 'Window size',
 'Пропорции держатся, когда тянете край окна. «Развернуть» и F11 — как обычно.': 'Proportions are kept when you drag '
                                                                                 'the window edge. “Maximize” and '
                                                                                 'F11 work as usual.',
 '— выберите пропорции —': '— choose proportions —',
 'Одно сочетание на два действия: ': 'One combination for two actions: ',
 'Заняты другой программой (работают только в окне плеера): ': 'Taken by another program (work only in the player '
                                                               'window): ',
 'Поделиться плейлистом': 'Share playlist',
 'Открыть файл плейлиста': 'Open playlist file',
 'Плейлист из файла': 'Playlist from file',
 'Файлы тем и плейлистов': 'Theme and playlist files',
 'Тема или плейлист': 'Theme or playlist',
 'Из файла плейлиста': 'From a playlist file',
 'Открыть папку «Импорт»': 'Open the “Import” folder',
 'Открыть файл…': 'Open file…',
 'Папка с темами': 'Themes folder',
 '1. Первая тема за 5 минут': '1. Your first theme in 5 minutes',
 '2. Что где в конструкторе': "2. What's where in the constructor",
 '3. Мышь и клавиши на холсте': '3. Mouse and keys on the canvas',
 '4. Слои: картинки, текст, видео, эффекты': '4. Layers: images, text, video, effects',
 '5. Виджеты и кнопки': '5. Widgets and buttons',
 '6. Элементы плеера и «Только слои»': '6. Player elements and “Layers only”',
 '7. Режим текста и режим клипа': '7. Lyrics mode and video mode',
 '8. Частицы и эффекты экрана': '8. Particles and screen effects',
 '9. Скрипты: что это и зачем': '9. Scripts: what and why',
 '10. Скрипты: поведение слоя (примеры)': '10. Scripts: layer behavior (examples)',
 '11. Скрипты: свой виджет (примеры)': '11. Scripts: your own widget (examples)',
 '12. Скрипт фона': '12. Background script',
 '13. Сохранить, поделиться, файлы': '13. Save, share, files',
 '14. Если что-то не так': '14. If something goes wrong',
 'Справочник EchoScript': 'EchoScript reference',
 '← Назад': '← Back',
 'Дальше →': 'Next →',
 'Полный справочник EchoScript…': 'Full EchoScript reference…',
 'Размытая обложка': 'Blurred cover',
 'Цвета клипа (эмбилайт)': 'Video colors (ambilight)',
 'Фон темы (со слоями)': 'Theme background (with layers)',
 'Скруглённая': 'Rounded',
 'Прямые углы': 'Square corners',
 'Без рамки': 'No frame',
 'Старый телевизор': 'Old TV',
 'Неоновая': 'Neon',
 'Полароид': 'Polaroid',
 'Киноплёнка': 'Film strip',
 'Полная панель': 'Full panel',
 'Только кнопки': 'Buttons only',
 'Прятать, пока не нужна': 'Hide until needed',
 'Тащите слой или элемент (оранжевая рамка) · двойной клик — то, что под ним · углы — размер (Shift — свободно, Alt — от центра) · стороны — растянуть в эту сторону · кружок — поворот · колесо — размер, Ctrl — поворот, Alt — 3D · Ctrl+клик — несколько · Enter — изменить · Del — убрать · Esc — готово': 'Drag '
                                                                                                                                                                                                                                                                                                               'a '
                                                                                                                                                                                                                                                                                                               'layer '
                                                                                                                                                                                                                                                                                                               'or '
                                                                                                                                                                                                                                                                                                               'element '
                                                                                                                                                                                                                                                                                                               '(orange '
                                                                                                                                                                                                                                                                                                               'frame) '
                                                                                                                                                                                                                                                                                                               '· '
                                                                                                                                                                                                                                                                                                               'double '
                                                                                                                                                                                                                                                                                                               'click '
                                                                                                                                                                                                                                                                                                               '— '
                                                                                                                                                                                                                                                                                                               "what's "
                                                                                                                                                                                                                                                                                                               'underneath '
                                                                                                                                                                                                                                                                                                               '· '
                                                                                                                                                                                                                                                                                                               'corners '
                                                                                                                                                                                                                                                                                                               '— '
                                                                                                                                                                                                                                                                                                               'size '
                                                                                                                                                                                                                                                                                                               '(Shift '
                                                                                                                                                                                                                                                                                                               '— '
                                                                                                                                                                                                                                                                                                               'free, '
                                                                                                                                                                                                                                                                                                               'Alt '
                                                                                                                                                                                                                                                                                                               '— '
                                                                                                                                                                                                                                                                                                               'from '
                                                                                                                                                                                                                                                                                                               'center) '
                                                                                                                                                                                                                                                                                                               '· '
                                                                                                                                                                                                                                                                                                               'sides '
                                                                                                                                                                                                                                                                                                               '— '
                                                                                                                                                                                                                                                                                                               'stretch '
                                                                                                                                                                                                                                                                                                               'that '
                                                                                                                                                                                                                                                                                                               'way '
                                                                                                                                                                                                                                                                                                               '· '
                                                                                                                                                                                                                                                                                                               'circle '
                                                                                                                                                                                                                                                                                                               '— '
                                                                                                                                                                                                                                                                                                               'rotate '
                                                                                                                                                                                                                                                                                                               '· '
                                                                                                                                                                                                                                                                                                               'wheel '
                                                                                                                                                                                                                                                                                                               '— '
                                                                                                                                                                                                                                                                                                               'size, '
                                                                                                                                                                                                                                                                                                               'Ctrl '
                                                                                                                                                                                                                                                                                                               '— '
                                                                                                                                                                                                                                                                                                               'rotate, '
                                                                                                                                                                                                                                                                                                               'Alt '
                                                                                                                                                                                                                                                                                                               '— '
                                                                                                                                                                                                                                                                                                               '3D '
                                                                                                                                                                                                                                                                                                               '· '
                                                                                                                                                                                                                                                                                                               'Ctrl+click '
                                                                                                                                                                                                                                                                                                               '— '
                                                                                                                                                                                                                                                                                                               'several '
                                                                                                                                                                                                                                                                                                               '· '
                                                                                                                                                                                                                                                                                                               'Enter '
                                                                                                                                                                                                                                                                                                               '— '
                                                                                                                                                                                                                                                                                                               'edit '
                                                                                                                                                                                                                                                                                                               '· '
                                                                                                                                                                                                                                                                                                               'Del '
                                                                                                                                                                                                                                                                                                               '— '
                                                                                                                                                                                                                                                                                                               'remove '
                                                                                                                                                                                                                                                                                                               '· '
                                                                                                                                                                                                                                                                                                               'Esc '
                                                                                                                                                                                                                                                                                                               '— '
                                                                                                                                                                                                                                                                                                               'done',
 'Библиотека целиком (левая панель)': 'Whole library (left panel)',
 'Кнопки управления (ряд)': 'Control buttons (row)',
 '+ Плеер ▾': '+ Player ▾',
 'Настоящие элементы плеера: винил, визуализатор, кнопки, библиотека, плейлисты…': 'Real player elements: vinyl, '
                                                                                   'visualizer, buttons, library, '
                                                                                   'playlists…',
 'Кнопки, перемотка, громкость, обложка, текст песни, спектры…': 'Buttons, seek bar, volume, cover, lyrics, '
                                                                 'spectrums…',
 '+ Кнопка…': '+ Button…',
 'Нарисовать свою кнопку: форма, рисунок, надпись, символ, картинка': 'Draw your own button: shape, drawing, text, '
                                                                      'symbol, image',
 'Свою кнопку…': 'Custom button…',
 'Убрать фон — ECHOES': 'Remove background — ECHOES',
 'Убрать фон': 'Remove background',
 'Вернуть фон': 'Restore background',
 'Показать исходную картинку, как была': 'Show the original image as it was',
 'Сила (смелее срезать фон)': 'Strength (cut the background more boldly)',
 'Мягкость краёв (волосы, мех)': 'Edge softness (hair, fur)',
 'Убирать фон и внутри (просветы между руками, в буквах…)': 'Remove the background inside too (gaps between arms, '
                                                            'inside letters…)',
 'Своя модель: изучает цвета фона по краям кадра и цвета объекта, проверяет, что фон связан с краями, и подгоняет края по самой картинке. Лучше всего — объект на однотонном или спокойном фоне. Работает без интернета.': 'Our '
                                                                                                                                                                                                                           'own '
                                                                                                                                                                                                                           'model: '
                                                                                                                                                                                                                           'learns '
                                                                                                                                                                                                                           'the '
                                                                                                                                                                                                                           'background '
                                                                                                                                                                                                                           'colors '
                                                                                                                                                                                                                           'along '
                                                                                                                                                                                                                           'the '
                                                                                                                                                                                                                           'frame '
                                                                                                                                                                                                                           'edges '
                                                                                                                                                                                                                           'and '
                                                                                                                                                                                                                           'the '
                                                                                                                                                                                                                           'object '
                                                                                                                                                                                                                           'colors, '
                                                                                                                                                                                                                           'checks '
                                                                                                                                                                                                                           'that '
                                                                                                                                                                                                                           'the '
                                                                                                                                                                                                                           'background '
                                                                                                                                                                                                                           'connects '
                                                                                                                                                                                                                           'to '
                                                                                                                                                                                                                           'the '
                                                                                                                                                                                                                           'edges, '
                                                                                                                                                                                                                           'and '
                                                                                                                                                                                                                           'refines '
                                                                                                                                                                                                                           'the '
                                                                                                                                                                                                                           'edges '
                                                                                                                                                                                                                           'from '
                                                                                                                                                                                                                           'the '
                                                                                                                                                                                                                           'image '
                                                                                                                                                                                                                           'itself. '
                                                                                                                                                                                                                           'Works '
                                                                                                                                                                                                                           'best '
                                                                                                                                                                                                                           'with '
                                                                                                                                                                                                                           'an '
                                                                                                                                                                                                                           'object '
                                                                                                                                                                                                                           'on '
                                                                                                                                                                                                                           'a '
                                                                                                                                                                                                                           'plain '
                                                                                                                                                                                                                           'or '
                                                                                                                                                                                                                           'calm '
                                                                                                                                                                                                                           'background. '
                                                                                                                                                                                                                           'Works '
                                                                                                                                                                                                                           'offline.',
 'Режим клипа': 'Video mode',
 '？ Справка': '？ Help',
 'Как пользоваться конструктором и писать скрипты — по шагам, с примерами': 'How to use the constructor and write '
                                                                            'scripts — step by step, with examples',
 'Оформление режима клипа: фон, рамка, свечение, панель, эффекты. Плеер покажет клип, чтобы было видно, что вы правите': 'Video '
                                                                                                                         'mode '
                                                                                                                         'look: '
                                                                                                                         'background, '
                                                                                                                         'frame, '
                                                                                                                         'glow, '
                                                                                                                         'panel, '
                                                                                                                         'effects. '
                                                                                                                         'The '
                                                                                                                         'player '
                                                                                                                         'will '
                                                                                                                         'show '
                                                                                                                         'a '
                                                                                                                         'video '
                                                                                                                         'so '
                                                                                                                         'you '
                                                                                                                         'can '
                                                                                                                         'see '
                                                                                                                         'what '
                                                                                                                         "you're "
                                                                                                                         'editing',
 'Элементы плеера на окне': 'Player elements on the window',
 'Настоящие винил, визуализатор, кнопки, библиотека, плейлисты… — добавляются как виджеты («+ Элемент плеера» или страница «Библиотека»), клик — выбрать, Del на окне — убрать.': 'Real '
                                                                                                                                                                                  'vinyl, '
                                                                                                                                                                                  'visualizer, '
                                                                                                                                                                                  'buttons, '
                                                                                                                                                                                  'library, '
                                                                                                                                                                                  'playlists… '
                                                                                                                                                                                  '— '
                                                                                                                                                                                  'added '
                                                                                                                                                                                  'as '
                                                                                                                                                                                  'widgets '
                                                                                                                                                                                  '(“+ '
                                                                                                                                                                                  'Player '
                                                                                                                                                                                  'element” '
                                                                                                                                                                                  'or '
                                                                                                                                                                                  'the '
                                                                                                                                                                                  '“Library” '
                                                                                                                                                                                  'page), '
                                                                                                                                                                                  'click '
                                                                                                                                                                                  '— '
                                                                                                                                                                                  'select, '
                                                                                                                                                                                  'Del '
                                                                                                                                                                                  'on '
                                                                                                                                                                                  'the '
                                                                                                                                                                                  'window '
                                                                                                                                                                                  '— '
                                                                                                                                                                                  'remove.',
 '+ Элемент плеера ▾': '+ Player element ▾',
 'Все — как было': 'All as they were',
 'Вернуть все элементы плеера на их обычные места': 'Return all player elements to their usual places',
 'Пластинка и звук': 'Record and sound',
 'Управление': 'Controls',
 'Библиотека и плейлисты': 'Library and playlists',
 'Кнопки режимов': 'Mode buttons',
 'Как писать поведение — справка с примерами': 'How to write behavior — help with examples',
 'Элементы плеера': 'Player elements',
 'Настоящие винил, визуализатор, кнопки, перемотка, громкость, библиотека и плейлисты — те же, что в обычном плеере. Ставятся на любой холст, даже на пустой; на окне их можно двигать, растягивать и убирать (Del).': 'Real '
                                                                                                                                                                                                                       'vinyl, '
                                                                                                                                                                                                                       'visualizer, '
                                                                                                                                                                                                                       'buttons, '
                                                                                                                                                                                                                       'seek '
                                                                                                                                                                                                                       'bar, '
                                                                                                                                                                                                                       'volume, '
                                                                                                                                                                                                                       'library '
                                                                                                                                                                                                                       'and '
                                                                                                                                                                                                                       'playlists '
                                                                                                                                                                                                                       '— '
                                                                                                                                                                                                                       'the '
                                                                                                                                                                                                                       'same '
                                                                                                                                                                                                                       'as '
                                                                                                                                                                                                                       'in '
                                                                                                                                                                                                                       'the '
                                                                                                                                                                                                                       'regular '
                                                                                                                                                                                                                       'player. '
                                                                                                                                                                                                                       'They '
                                                                                                                                                                                                                       'go '
                                                                                                                                                                                                                       'on '
                                                                                                                                                                                                                       'any '
                                                                                                                                                                                                                       'canvas, '
                                                                                                                                                                                                                       'even '
                                                                                                                                                                                                                       'an '
                                                                                                                                                                                                                       'empty '
                                                                                                                                                                                                                       'one; '
                                                                                                                                                                                                                       'on '
                                                                                                                                                                                                                       'the '
                                                                                                                                                                                                                       'window '
                                                                                                                                                                                                                       'they '
                                                                                                                                                                                                                       'can '
                                                                                                                                                                                                                       'be '
                                                                                                                                                                                                                       'moved, '
                                                                                                                                                                                                                       'stretched '
                                                                                                                                                                                                                       'and '
                                                                                                                                                                                                                       'removed '
                                                                                                                                                                                                                       '(Del).',
 'Своя кнопка': 'Custom button',
 'Нарисуйте вид кнопки: форма и заливка, кисть, надписи, символы ▶ ❚❚ ▶▶ ♥, картинки. Потом выберите, что она делает по клику.': 'Draw '
                                                                                                                                 'the '
                                                                                                                                 "button's "
                                                                                                                                 'look: '
                                                                                                                                 'shape '
                                                                                                                                 'and '
                                                                                                                                 'fill, '
                                                                                                                                 'brush, '
                                                                                                                                 'text, '
                                                                                                                                 'symbols '
                                                                                                                                 '▶ '
                                                                                                                                 '❚❚ '
                                                                                                                                 '▶▶ '
                                                                                                                                 '♥, '
                                                                                                                                 'images. '
                                                                                                                                 'Then '
                                                                                                                                 'choose '
                                                                                                                                 'what '
                                                                                                                                 'it '
                                                                                                                                 'does '
                                                                                                                                 'on '
                                                                                                                                 'click.',
 'Редактор кнопок…': 'Button editor…',
 'Каждый виджет — отдельный слой: двигайте, тяните, крутите, наклоняйте в 3D, складывайте в группы. Код любого виджета можно открыть и переписать.': 'Each '
                                                                                                                                                     'widget '
                                                                                                                                                     'is '
                                                                                                                                                     'a '
                                                                                                                                                     'separate '
                                                                                                                                                     'layer: '
                                                                                                                                                     'move, '
                                                                                                                                                     'drag, '
                                                                                                                                                     'rotate, '
                                                                                                                                                     'tilt '
                                                                                                                                                     'in '
                                                                                                                                                     '3D, '
                                                                                                                                                     'group. '
                                                                                                                                                     'The '
                                                                                                                                                     'code '
                                                                                                                                                     'of '
                                                                                                                                                     'any '
                                                                                                                                                     'widget '
                                                                                                                                                     'can '
                                                                                                                                                     'be '
                                                                                                                                                     'opened '
                                                                                                                                                     'and '
                                                                                                                                                     'rewritten.',
 'Где эффекты': 'Where effects go',
 'Частицы, сканлайны, зерно и виньетка — поверх всего окна или за интерфейсом: на фоне, под панелями, кнопками и пластинкой.': 'Particles, '
                                                                                                                               'scanlines, '
                                                                                                                               'grain '
                                                                                                                               'and '
                                                                                                                               'vignette '
                                                                                                                               '— '
                                                                                                                               'over '
                                                                                                                               'the '
                                                                                                                               'whole '
                                                                                                                               'window '
                                                                                                                               'or '
                                                                                                                               'behind '
                                                                                                                               'the '
                                                                                                                               'interface: '
                                                                                                                               'on '
                                                                                                                               'the '
                                                                                                                               'background, '
                                                                                                                               'under '
                                                                                                                               'panels, '
                                                                                                                               'buttons '
                                                                                                                               'and '
                                                                                                                               'the '
                                                                                                                               'record.',
 'За интерфейсом (на фоне)': 'Behind the interface (background)',
 'Летают по окну (поверх интерфейса или за ним — см. выше) и ускоряются под музыку.': 'Fly around the window (over '
                                                                                      'the interface or behind it — '
                                                                                      'see above) and speed up with '
                                                                                      'the music.',
 'Выбрать картинку (PNG)…': 'Choose an image (PNG)…',
 'Картинка крутится вместо пластинки — только в этой теме': 'The image spins instead of the record — only in this '
                                                            'theme',
 'Обычная пластинка': 'Regular record',
 'Картинка вместо пластинки': 'Image instead of the record',
 'Картинки (*.png *.webp *.jpg *.jpeg *.bmp *.gif)': 'Images (*.png *.webp *.jpg *.jpeg *.bmp *.gif)',
 'Официальный клип песни (кнопка «Клип» или Ctrl+Shift+K). Здесь — его оформление в этой теме: фон, рамка, свечение, панель управления и эффекты, которые включатся сразу. Выключено — клип оформлен по палитре темы.': 'The '
                                                                                                                                                                                                                  "song's "
                                                                                                                                                                                                                  'official '
                                                                                                                                                                                                                  'video '
                                                                                                                                                                                                                  '(the '
                                                                                                                                                                                                                  '“Video” '
                                                                                                                                                                                                                  'button '
                                                                                                                                                                                                                  'or '
                                                                                                                                                                                                                  'Ctrl+Shift+K). '
                                                                                                                                                                                                                  'Here '
                                                                                                                                                                                                                  '— '
                                                                                                                                                                                                                  'its '
                                                                                                                                                                                                                  'look '
                                                                                                                                                                                                                  'in '
                                                                                                                                                                                                                  'this '
                                                                                                                                                                                                                  'theme: '
                                                                                                                                                                                                                  'background, '
                                                                                                                                                                                                                  'frame, '
                                                                                                                                                                                                                  'glow, '
                                                                                                                                                                                                                  'control '
                                                                                                                                                                                                                  'panel '
                                                                                                                                                                                                                  'and '
                                                                                                                                                                                                                  'effects '
                                                                                                                                                                                                                  'that '
                                                                                                                                                                                                                  'turn '
                                                                                                                                                                                                                  'on '
                                                                                                                                                                                                                  'right '
                                                                                                                                                                                                                  'away. '
                                                                                                                                                                                                                  'Off '
                                                                                                                                                                                                                  '— '
                                                                                                                                                                                                                  'the '
                                                                                                                                                                                                                  'video '
                                                                                                                                                                                                                  'follows '
                                                                                                                                                                                                                  'the '
                                                                                                                                                                                                                  'theme '
                                                                                                                                                                                                                  'palette.',
 'Показать режим клипа на плеере': 'Show video mode on the player',
 'Рамка и свечение': 'Frame and glow',
 'Видео и панель': 'Video and panel',
 'Эффекты сразу при открытии': 'Effects right on open',
 'Психоделические эффекты включатся сами, когда откроют клип в этой теме (их можно выключить в самом клипе). «!» — вспышки: плеер предупредит перед ними.': 'Psychedelic '
                                                                                                                                                            'effects '
                                                                                                                                                            'turn '
                                                                                                                                                            'on '
                                                                                                                                                            'by '
                                                                                                                                                            'themselves '
                                                                                                                                                            'when '
                                                                                                                                                            'a '
                                                                                                                                                            'video '
                                                                                                                                                            'is '
                                                                                                                                                            'opened '
                                                                                                                                                            'in '
                                                                                                                                                            'this '
                                                                                                                                                            'theme '
                                                                                                                                                            '(they '
                                                                                                                                                            'can '
                                                                                                                                                            'be '
                                                                                                                                                            'turned '
                                                                                                                                                            'off '
                                                                                                                                                            'in '
                                                                                                                                                            'the '
                                                                                                                                                            'video '
                                                                                                                                                            'itself). '
                                                                                                                                                            '“!” '
                                                                                                                                                            '— '
                                                                                                                                                            'flashes: '
                                                                                                                                                            'the '
                                                                                                                                                            'player '
                                                                                                                                                            'warns '
                                                                                                                                                            'before '
                                                                                                                                                            'them.',
 'Отдать его место соседям': 'Give its space to neighbors',
 'Выключено — вынутый или убранный элемент оставляет пустое место, остальные элементы не двигаются и не растягиваются': 'Off '
                                                                                                                        '— '
                                                                                                                        'a '
                                                                                                                        'taken-out '
                                                                                                                        'or '
                                                                                                                        'removed '
                                                                                                                        'element '
                                                                                                                        'leaves '
                                                                                                                        'empty '
                                                                                                                        'space, '
                                                                                                                        'other '
                                                                                                                        'elements '
                                                                                                                        "don't "
                                                                                                                        'move '
                                                                                                                        'or '
                                                                                                                        'stretch',
 'Элемент плеера': 'Player element',
 'Было': 'Before',
 'Стало': 'After',
 'Думаю…': 'Thinking…',
 'Фон убран — слой уже показывает новую картинку.': 'Background removed — the layer already shows the new image.',
 'Исходная картинка возвращена.': 'Original image restored.',
 'Своя кнопка (редактор кнопок)…': 'Custom button (button editor)…',
 'Кнопка: ': 'Button: ',
 'Убрать фон…': 'Remove background…',
 'Своя модель вырежет объект из фона (картинки и GIF), края — мягкие': 'Our own model cuts the object out of the '
                                                                       'background (images and GIFs), with soft '
                                                                       'edges',
 'Своя картинка вместо диска': 'Custom image instead of the disc',
 'Сейчас обычная пластинка. PNG с прозрачностью крутится вместе с музыкой.': 'Now a regular record. A PNG with '
                                                                             'transparency spins with the music.',
 'Своё оформление режима клипа': 'Custom video mode look',
 '«Фон темы» — под клипом видны фон и слои этой темы. «Цвета клипа» — фон переливается средним цветом кадра, как подсветка телевизора.': '“Theme '
                                                                                                                                         'background” '
                                                                                                                                         '— '
                                                                                                                                         'the '
                                                                                                                                         "theme's "
                                                                                                                                         'background '
                                                                                                                                         'and '
                                                                                                                                         'layers '
                                                                                                                                         'are '
                                                                                                                                         'visible '
                                                                                                                                         'under '
                                                                                                                                         'the '
                                                                                                                                         'video. '
                                                                                                                                         '“Video '
                                                                                                                                         'colors” '
                                                                                                                                         '— '
                                                                                                                                         'the '
                                                                                                                                         'background '
                                                                                                                                         'shimmers '
                                                                                                                                         'with '
                                                                                                                                         'the '
                                                                                                                                         'average '
                                                                                                                                         'frame '
                                                                                                                                         'color, '
                                                                                                                                         'like '
                                                                                                                                         'a '
                                                                                                                                         'TV '
                                                                                                                                         'backlight.',
 'Цвет рамки / неона': 'Frame / neon color',
 'Толщина рамки': 'Frame width',
 'Свечение вокруг видео': 'Glow around the video',
 'Размер видео': 'Video size',
 'Название трека сверху': 'Track title on top',
 'Акцент (кнопки, полоска)': 'Accent (buttons, bar)',
 'Сила эффектов': 'Effect strength',
 'Изменить вид кнопки…': 'Edit button look…',
 'слой': 'layer',
 'Файл картинки не найден': 'Image file not found',
 'Не получилось сохранить результат': "Couldn't save the result",
 'Окном': 'Window',
 'Встроить в плеер': 'Embed into the player',
 'Элемент стоит на своём месте — отдавать нечего': 'The element is in its place — nothing to give',
 'Элементы ставятся в теме из конструктора — сначала откройте или создайте тему': 'Elements are placed in a '
                                                                                  'constructor theme — open or '
                                                                                  'create a theme first',
 ' — на окне. Двигайте и тяните его в «Расставить на экране»': ' — on the window. Move and drag it in “Arrange on '
                                                               'screen”',
 'Пусто — добавьте элементы из библиотеки': 'Empty — add elements from the library',
 'Элементы плеера (винил, кнопки, библиотека…)': 'Player elements (vinyl, buttons, library…)',
 'Сначала выберите слой-картинку или GIF': 'Select an image or GIF layer first',
 'новая': 'new',
 'Не получилось сохранить картинку кнопки': "Couldn't save the button image",
 'Кнопка добавлена — её можно двигать на окне («Расставить на экране»)': 'Button added — you can move it on the '
                                                                         'window (“Arrange on screen”)',
 'Кнопка обновлена': 'Button updated',
 ' — крутится вместо диска (стиль «Пластинка»)': ' — spins instead of the disc (“Record” style)',
 'Плеер показывает режим клипа — правки видны сразу': 'The player shows video mode — edits are visible right away',
 'Рамка': 'Frame',
 'из клипа': 'from the video',
 'Панель управления': 'Control panel',
 'стекло': 'glass',
 'двойной клик — следующий под ним': 'double click — the next one underneath',
 '. В предпросмотре — первый кадр, «Применить» обработает все.': '. The preview shows the first frame, “Apply” will '
                                                                 'process all of them.',
 'Винил на окне — двигайте и тяните его в «Расставить на экране»': 'Vinyl on the window — move and drag it in '
                                                                   '“Arrange on screen”',
 'Выбрано: ': 'Selected: ',
 'Не получилось открыть: ': "Couldn't open: ",
 'Анимация: кадров ': 'Animation: frames ',
 'Готово. Не нравится — подвиньте «Силу» или «Мягкость».': "Done. Don't like it — adjust “Strength” or “Softness”.",
 'Уже на окне — поставить свободно сюда': 'Already on the window — place it freely here',
 'Поставить на окно': 'Place on the window',
 'Целиком': 'Fit',
 'Заполнить (обрезать края)': 'Fill (crop the edges)',
 'Режим клипа не открылся: ': "Video mode didn't open: ",
 'Ошибка модели: ': 'Model error: ',
 'Сплошной фон эффекта (без него тёмный фон прозрачный)': 'Solid effect background (without it a dark background is '
                                                          'transparent)',
 'Обрабатываю кадры: ': 'Processing frames: ',
 'сингл': 'single',
 'Загружаю альбомы и синглы с YouTube Music…': 'Loading albums and singles from YouTube Music…',
 '  Все треки исполнителя': "  All of the artist's tracks",
 'Синглы и EP': 'Singles and EPs',
 'По популярности': 'By popularity',
 'Как на YouTube Music': 'As on YouTube Music',
 'Все треки исполнителя · YouTube Music': "All of the artist's tracks · YouTube Music",
 'Найти трек исполнителя…': 'Find a track by this artist…',
 'Открыть: треки и прослушивания': 'Open: tracks and plays',
 'Альбомы не нашлись на YouTube Music': 'No albums found on YouTube Music',
 'Все треки — в плейлист с названием альбома': 'All tracks — into a playlist named after the album',
 'Загружаю все треки…': 'Loading all tracks…',
 'Треки не нашлись на YouTube Music': 'No tracks found on YouTube Music',
 '  Скачать все в плейлист': '  Download all into a playlist',
 'Все треки уже в коллекции': 'All tracks are already in the collection',
 'Не удалось загрузить: ': "Couldn't load: ",
 'Альбом не нашёлся на YouTube Music': 'Album not found on YouTube Music',
 '  Настроить': '  Customize',
 'Под занятие': 'For an activity',
 'По характеру': 'By mood',
 'По языку': 'By language',
 'Настроить Мою волну': 'Customize My Wave',
 'Сбросить настройки волны': 'Reset wave settings',
 'Просыпаюсь': 'Waking up',
 'В дороге': 'On the road',
 'Работаю': 'Working',
 'Тренируюсь': 'Working out',
 'Засыпаю': 'Falling asleep',
 'Иностранный': 'Foreign',
 'Без слов': 'Instrumental',
 'Подборка из вашей коллекции': 'A selection from your collection',
 '  Все треки': '  All tracks',
 'Куда класть файлы тем/плейлистов': 'Where to put theme/playlist files',
 'Плейлист': 'Playlist',
 'Инди/альтернатива': 'Indie / alternative',
 'Трэп': 'Trap',
 'Хип-хоп': 'Hip-hop',
 'Анимации интерфейса': 'Interface animations',
 'Плавное сворачивание окна, смена вкладок и страниц, появление меню.': 'Smooth window minimizing, tab and page '
                                                                        'switching, menus appearing.'}

TEMPLATES = {'Скачиваю: {0}': 'Downloading: {0}',
 'Вокал «{0}» на бит «{1}».': 'Vocals of “{0}” over the beat of “{1}”.',
 'К «{0}» по темпу и тональности лучше всего подходят:': 'By tempo and key the best matches for “{0}” are:',
 'Слушаю «{0}»…': 'Listening to “{0}”…',
 'Мэшап-бот: {0}': 'Mashup bot: {0}',
 '«{0}»: {1} BPM ({2} темп), тональность {3} ({4}), длина {5}:{6}, частей: {7}.': '“{0}”: {1} BPM ({2} tempo), key '
                                                                                  '{3} ({4}), length {5}:{6}, '
                                                                                  'sections: {7}.',
 'Готов звук: {0}': 'Sound ready: {0}',
 'Нашёл «{0}». С каким треком смешать? Напиши второй или выбери в поле.': 'Found “{0}”. What should I mix it with? '
                                                                          'Type the second one or pick it in the '
                                                                          'field.',
 'Библиотека треков ({0})': 'Track library ({0})',
 'Паттерны ({0})': 'Patterns ({0})',
 'Каналы ({0})': 'Channels ({0})',
 'Аудио ({0})': 'Audio ({0})',
 '{0} дБ': '{0} dB',
 '{0} кГц': '{0} kHz',
 '{0} Гц': '{0} Hz',
 '{0} пт': '{0} st',
 '{0}: частота': '{0}: frequency',
 '{0}: усиление': '{0}: gain',
 '{0}: ширина (Q)': '{0}: width (Q)',
 'Осц {0}: волна': 'Osc {0}: wave',
 'Осц {0}: громкость': 'Osc {0}: volume',
 'Осц {0}: полутоны': 'Osc {0}: semitones',
 'Осц {0}: подстройка': 'Osc {0}: fine tune',
 'Мэшап: {0} × {1}': 'Mashup: {0} × {1}',
 'Бит — {0}': 'Beat — {0}',
 'Готово: вокал «{0}» на бите «{1}».': 'Done: vocals of “{0}” over the beat of “{1}”.',
 'Структура ({0}:{1}):': 'Structure ({0}:{1}):',
 'Совместимость: {0} %.': 'Compatibility: {0} %.',
 ', сдвиг {0}': ', shift {0}',
 'Тональность: бит {0} ({1}), вокал {2} ({3}) — вокал {4} на {5} пт. → {6}, тембр голоса сохранён.': 'Key: beat {0} '
                                                                                                     '({1}), vocals '
                                                                                                     '{2} ({3}) — '
                                                                                                     'vocals {4} by '
                                                                                                     '{5} st. → {6}, '
                                                                                                     'voice timbre '
                                                                                                     'kept.',
 'Тональность: бит {0} ({1}), вокал {2} ({3}) — по тону сходятся без сдвига.': 'Key: beat {0} ({1}), vocals {2} '
                                                                               '({3}) — they match in key without a '
                                                                               'shift.',
 'Бит из-за смены скорости звучит на {0} пт. — вокал подстроен туда же, строй совпадает.': 'Because of the speed '
                                                                                           'change the beat sounds '
                                                                                           '{0} st. off — the vocals '
                                                                                           'are tuned the same way, '
                                                                                           'the pitch matches.',
 '  {0}:{1}  {2}, {3} т. — {4} (под ним {5})': '  {0}:{1}  {2}, {3} bars — {4} (under it {5})',
 'Темп {0} BPM — как у бита. Вокал подогнан по долям: {1}': 'Tempo {0} BPM — same as the beat. Vocals fitted by '
                                                            'beats: {1}',
 'Темп {0} BPM: бит {1} → {2} ({3} %, {4}), вокал {5}': 'Tempo {0} BPM: beat {1} → {2} ({3} %, {4}), vocals {5}',
 'Оригинал — {0}': 'Original — {0}',
 ', эффектов: {0}': ', effects: {0}',
 'Дорожка {0}': 'Track {0}',
 '\nЗадержка эффектов {0} мс — компенсируется': '\nEffect latency {0} ms — compensated',
 ' — каналы: {0}': ' — channels: {0}',
 ' — с такта {0}, {1} т. Двойной щелчок — открыть, правая кнопка — удалить': ' — from bar {0}, {1} bars. Double '
                                                                             'click — open, right click — delete',
 'Скопировано клипов: {0}': 'Clips copied: {0}',
 '{0} — {1}, ячейка {2}': '{0} — {1}, slot {2}',
 'Пресет: {0}': 'Preset: {0}',
 '  {0} пт': '  {0} st',
 ', {0} дБ, Q {1}': ', {0} dB, Q {1}',
 '{0} — {1}: щелчок — открыть, правая кнопка — меню': '{0} — {1}: click — open, right click — menu',
 'Дорожка микшера: {0} ({1})': 'Mixer track: {0} ({1})',
 'Каждый {0}-й шаг': 'Every {0}th step',
 'Квантизовано нот: {0}': 'Notes quantized: {0}',
 'Сила нажатия: {0} %': 'Velocity: {0} %',
 '{0}: начало {1}, длина {2} доли, сила {3} %': '{0}: start {1}, length {2} beats, velocity {3} %',
 'Скопировано нот: {0}': 'Notes copied: {0}',
 'Качаю нейросеть… {0}%': 'Downloading the neural network… {0}%',
 'Нейросеть отделяет вокал: {0}%': 'The neural network is separating vocals: {0}%',
 'Запись {0} — {1}': 'Recording {0} — {1}',
 '{0} (копия)': '{0} (copy)',
 'Повторено: {0}': 'Repeated: {0}',
 'Дубль записан: {0} ({1} с) — на дорожке {2}, эффекты — на дорожке микшера «Голос»': 'Take recorded: {0} ({1} s) — '
                                                                                      'on track {2}, effects — on '
                                                                                      'the “Voice” mixer track',
 'Канал «{0}» добавлен на дорожку микшера {1}': 'Channel “{0}” added to mixer track {1}',
 'Паттерн {0}': 'Pattern {0}',
 'Создан {0}': 'Created {0}',
 'Паттерн: {0}': 'Pattern: {0}',
 'Пресет голоса «{0}» на {1}': 'Voice preset “{0}” on {1}',
 '«{0}» — аудиоклип на дорожке {1}': '“{0}” — audio clip on track {1}',
 'Проект сохранён: {0}': 'Project saved: {0}',
 'Открыт проект «{0}»': 'Opened project “{0}”',
 'Темп проекта… ({0})': 'Project tempo… ({0})',
 'Задержка вывода: {0} мс. Запись сдвигается на задержку автоматически.': 'Output latency: {0} ms. Recordings are '
                                                                          'shifted by the latency automatically.',
 'Звук не получился: {0}': 'The sound failed: {0}',
 'Темп: {0} BPM': 'Tempo: {0} BPM',
 'Не открыть: {0}': "Can't open: {0}",
 'Не открыть папку: {0}': "Can't open the folder: {0}",
 'Не прочитать файл: {0}': "Can't read the file: {0}",
 'Не вышло: {0}': "Didn't work: {0}",
 'Свожу… {0}%': 'Mixing down… {0}%',
 'Не удалось подготовить «{0}»: {1}': "Couldn't prepare “{0}”: {1}",
 '\nПапка: {0}': '\nFolder: {0}',
 'строка {0}: {1}': 'line {0}: {1}',
 'непонятный цвет «{0}»': 'unknown color “{0}”',
 'это не цвет: {0}': 'not a color: {0}',
 'неизвестный режим смешивания «{0}» (есть: {1})': 'unknown blend mode “{0}” (available: {1})',
 'нет виджета «{0}» (объявите: widget {1} {{ … }})': 'no widget “{0}” (declare: widget {1} {{ … }})',
 '{0}, событие {1}: {2}': '{0}, event {1}: {2}',
 'Выбрано: {0}  ·  Ctrl+клик — добавить/убрать  ·  стрелки — сдвиг': 'Selected: {0}  ·  Ctrl+click — add/remove  ·  '
                                                                     'arrows — nudge',
 'виджет {0}: неизвестное событие «{1}» (есть: {2})': 'widget {0}: unknown event “{1}” (available: {2})',
 'действие не выполнилось: {0}': 'the action failed: {0}',
 'Виджеты из «{0}»': 'Widgets from “{0}”',
 "<span style='color:#8cf0b4'>Импортировано: {0}</span>": "<span style='color:#8cf0b4'>Imported: {0}</span>",
 "<span style='color:#8cf0b4'>Из «{0}»: цвета, фон и слоёв — {1}</span>": "<span style='color:#8cf0b4'>From “{0}”: "
                                                                          'colors, background and layers — '
                                                                          '{1}</span>',
 "<span style='color:{0}'>{1} к/с</span> · кадр {2} мс (рисование {3}) · {4}": "<span style='color:{0}'>{1} "
                                                                               'fps</span> · frame {2} ms (drawing '
                                                                               '{3}) · {4}',
 "<span style='color:#8cf0b4'>Добавлено: {0}</span>": "<span style='color:#8cf0b4'>Added: {0}</span>",
 "<b style='color:#ffb347'>Выбрано: {0}</b>": "<b style='color:#ffb347'>Selected: {0}</b>",
 "<span style='color:#8cf0b4'>Группа g{0}: {1} виджета(ов)</span>": "<span style='color:#8cf0b4'>Group g{0}: {1} "
                                                                    'widget(s)</span>',
 'Удалить скрипт «{0}»?': 'Delete script “{0}”?',
 'В скрипте «{0}» нет виджетов.': 'Script “{0}” has no widgets.',
 'Сгруппировать ({0})': 'Group ({0})',
 'Удалить ({0})': 'Delete ({0})',
 'свойство «{0}»': 'property “{0}”',
 "<span style='color:#8cf0b4'>Цвета взяты из темы «{0}»</span>": "<span style='color:#8cf0b4'>Colors taken from the "
                                                                 'theme “{0}”</span>',
 "<span style='color:#ff6b7f'>Не удалось сохранить: {0}</span>": "<span style='color:#ff6b7f'>Couldn't save: "
                                                                 '{0}</span>',
 "<span style='color:#ff6b7f'>Не нашёл «add {0}» в строке {1}</span>": "<span style='color:#ff6b7f'>Couldn't find "
                                                                       '“add {0}” on line {1}</span>',
 'Не удалось переименовать: {0}': "Couldn't rename: {0}",
 'Не удалось прочитать: {0}': "Couldn't read: {0}",
 '<b>Треков: {0}</b>': '<b>Tracks: {0}</b>',
 'Обработка {0} из {1}: {2}…': 'Processing {0} of {1}: {2}…',
 '+{0} дБ': '+{0} dB',
 ' · ошибок: {0}': ' · errors: {0}',
 'Не удалось создать папку: {0}': "Couldn't create the folder: {0}",
 'виджет «{0}» не создан': "widget “{0}” wasn't created",
 'Не удалось сохранить .lrc: {0}': "Couldn't save the .lrc: {0}",
 'сейчас {0} · {1}': 'now {0} · {1}',
 'Не получилось открыть экспорт:\n{0}': "Couldn't open the export:\n{0}",
 'Не удалось открыть режим клипа:\n{0}': "Couldn't open video mode:\n{0}",
 'Экспорт с эффектами ({0})…': 'Export with effects ({0})…',
 'Всего попыток: {0}  ·  карт: {1}  ·  пройдено карт: {2}  ·  провалов: {3}': 'Total attempts: {0}  ·  maps: {1}  ·  '
                                                                              'maps passed: {2}  ·  fails: {3}',
 '  ·  в среднем карта проходится с {0}-й попытки': '  ·  on average a map is passed on attempt {0}',
 'с {0}-й': 'on the {0}th',
 'Разбираю карты: {0}': 'Parsing maps: {0}',
 'Распаковываю {0}': 'Unpacking {0}',
 'Карта: {0}': 'Map: {0}',
 'Длина: {0}   BPM: {1}   Объекты: {2}': 'Length: {0}   BPM: {1}   Objects: {2}',
 'Круги: {0}   Слайдеры: {1}   Спиннеры: {2}': 'Circles: {0}   Sliders: {1}   Spinners: {2}',
 'CS:{0}  AR:{1}  OD:{2}  HP:{3}  Звёзды: {4}': 'CS:{0}  AR:{1}  OD:{2}  HP:{3}  Stars: {4}',
 'Множитель очков: {0}x': 'Score Multiplier: {0}x',
 'Очки: {0} ({1}x)': 'Score: {0} ({1}x)',
 '{0} (правка)': '{0} (edit)',
 'Карта сохранена · ★ {0} · объектов {1}': 'Map saved · ★ {0} · objects {1}',
 'круги {0} · слайдеры {1} · спиннеры {2}': 'circles {0} · sliders {1} · spinners {2}',
 'Сетка {0}': 'Grid {0}',
 'x {0} · y {1} · комбо {2}': 'x {0} · y {1} · combo {2}',
 'Не удалось сохранить: {0}': "Couldn't save: {0}",
 'Проходов: {0}': 'Passes: {0}',
 'Длина: {0} доли': 'Length: {0} beats',
 '{0} — заново  ·  Esc — выйти': '{0} — retry  ·  Esc — quit',
 'Esc — продолжить  ·  {0} — заново': 'Esc — continue  ·  {0} — retry',
 'Счёт {0}  ·  точность {1}%  ·  комбо {2}x': 'Score {0}  ·  accuracy {1}%  ·  combo {2}x',
 'Весь трек · {0}': 'Whole track · {0}',
 '{0} – {1}   ·   длина {2}': '{0} – {1}   ·   length {2}',
 'Расставляю ноты: {0}…': 'Placing notes: {0}…',
 'В игре: {0} см на 360°': 'In the game: {0} cm per 360°',
 '(точно было бы {0}% — ограничено 1–500%)': '(exactly it would be {0}% — limited to 1–500%)',
 'Попыток: {0}  ·  пройдено: {1}': 'Attempts: {0}  ·  passed: {1}',
 '  ·  впервые — с {0}-й попытки': '  ·  first passed on attempt {0}',
 'Точность: {0}%  ·  игр: {1}': 'Accuracy: {0}%  ·  plays: {1}',
 'ур. {0}': 'lv. {0}',
 'Ничего не найдено по «{0}» — Esc очистит поиск': 'Nothing found for “{0}” — Esc clears the search',
 'В «{0}» нет треков — выберите другую коллекцию справа': 'No tracks in “{0}” — choose another collection on the '
                                                          'right',
 'Множитель очков: ×{0}': 'Score multiplier: ×{0}',
 '  ·  попытка {0}': '  ·  attempt {0}',
 '{0}pp   ·   UR {1}   ·   в среднем {2} мс {3}   ·   макс. комбо карты {4}x': '{0}pp   ·   UR {1}   ·   on average '
                                                                               '{2} ms {3}   ·   map max combo {4}x',
 'Тема {0} · ECHOES': 'Theme {0} · ECHOES',
 'Попытка {0}': 'Attempt {0}',
 'Длина: {0}   BPM: {1}   Объектов: {2}   Макс. комбо: {3}x': 'Length: {0}   BPM: {1}   Objects: {2}   Max combo: '
                                                              '{3}x',
 'Кругов: {0}   Слайдеров: {1}   Спиннеров: {2}   ·   CS {3}  AR {4}  OD {5}  HP {6}   ★ {7}': 'Circles: {0}   '
                                                                                               'Sliders: {1}   '
                                                                                               'Spinners: {2}   ·   '
                                                                                               'CS {3}  AR {4}  OD '
                                                                                               '{5}  HP {6}   ★ {7}',
 'Игрок {0}  ·  {1}': 'Player {0}  ·  {1}',
 'Чувствительность: {0}%': 'Sensitivity: {0}%',
 'Клип: {0} {1}%': 'Video: {0} {1}%',
 'добро пожаловать в {0}': 'welcome to {0}',
 'Производительность: {0}pp': 'Performance: {0}pp',
 '  ·  отрывок {0}–{1}': '  ·  section {0}–{1}',
 '  ·  впервые пройдена с {0}-й': '  ·  first passed on attempt {0}',
 'Клип: {0}': 'Video: {0}',
 ' по отрывку {0}–{1}…': ' for the section {0}–{1}…',
 'Экспорт не удался: {0}': 'Export failed: {0}',
 'Добавлено наборов: {0}, карт: {1}': 'Sets added: {0}, maps: {1}',
 'Наборов: {0}, карт: {1}': 'Sets: {0}, maps: {1}',
 '  ·  папка: {0}': '  ·  folder: {0}',
 'Скин не импортирован: {0}': 'Skin not imported: {0}',
 'Импорт не удался: {0}': 'Import failed: {0}',
 'Счёт {0}  ({1}x)': 'Score {0}  ({1}x)',
 '{0}pp  ·  {1}%  ·  {2} игр': '{0}pp  ·  {1}%  ·  {2} plays',
 'модель слушает трек: {0}': 'the model is listening to the track: {0}',
 'Не получилось проиграть: {0}': "Couldn't play: {0}",
 'Из скина взято звуков: {0}': 'Sounds taken from the skin: {0}',
 'Плейлист ECHOES (*{0})': 'ECHOES playlist (*{0})',
 'Готово: {0} ({1} КБ, {2} треков). Отправьте файл другу — пусть перетащит его на окно ECHOES': 'Done: {0} ({1} KB, '
                                                                                                '{2} tracks). Send '
                                                                                                'the file to a '
                                                                                                'friend — let them '
                                                                                                'drag it onto the '
                                                                                                'ECHOES window',
 'Плейлисты (*{0} *.m3u *.m3u8 *.txt);;Все файлы (*)': 'Playlists (*{0} *.m3u *.m3u8 *.txt);;All files (*)',
 'Тема «{0}» добавлена в «Мои темы»': 'Theme “{0}” added to “My themes”',
 'Темы и плейлисты (*{0} *{1} *.m3u *.m3u8 *.txt)': 'Themes and playlists (*{0} *{1} *.m3u *.m3u8 *.txt)',
 'Не получилось прочитать файл:\n{0}': "Couldn't read the file:\n{0}",
 'Файл «{0}»: {1} треков. Треки, которые уже есть у вас, сразу попадут в плейлист, остальные будут найдены на YouTube Music / YouTube / SoundCloud и скачаны. Берутся только точные совпадения (исполнитель, название и длительность).': 'File '
                                                                                                                                                                                                                                         '“{0}”: '
                                                                                                                                                                                                                                         '{1} '
                                                                                                                                                                                                                                         'tracks. '
                                                                                                                                                                                                                                         'Tracks '
                                                                                                                                                                                                                                         'you '
                                                                                                                                                                                                                                         'already '
                                                                                                                                                                                                                                         'have '
                                                                                                                                                                                                                                         'go '
                                                                                                                                                                                                                                         'straight '
                                                                                                                                                                                                                                         'into '
                                                                                                                                                                                                                                         'the '
                                                                                                                                                                                                                                         'playlist, '
                                                                                                                                                                                                                                         'the '
                                                                                                                                                                                                                                         'rest '
                                                                                                                                                                                                                                         'will '
                                                                                                                                                                                                                                         'be '
                                                                                                                                                                                                                                         'found '
                                                                                                                                                                                                                                         'on '
                                                                                                                                                                                                                                         'YouTube '
                                                                                                                                                                                                                                         'Music '
                                                                                                                                                                                                                                         '/ '
                                                                                                                                                                                                                                         'YouTube '
                                                                                                                                                                                                                                         '/ '
                                                                                                                                                                                                                                         'SoundCloud '
                                                                                                                                                                                                                                         'and '
                                                                                                                                                                                                                                         'downloaded. '
                                                                                                                                                                                                                                         'Only '
                                                                                                                                                                                                                                         'exact '
                                                                                                                                                                                                                                         'matches '
                                                                                                                                                                                                                                         'are '
                                                                                                                                                                                                                                         'used '
                                                                                                                                                                                                                                         '(artist, '
                                                                                                                                                                                                                                         'title '
                                                                                                                                                                                                                                         'and '
                                                                                                                                                                                                                                         'duration).',
 'Справочник недоступен: {0}': 'Reference unavailable: {0}',
 'Группа G{0}: {1} слоёв — двигаются вместе': 'Group G{0}: {1} layers — move together',
 'Скопировано слоёв из «{0}»: {1}': 'Layers copied from “{0}”: {1}',
 'Добавлено слоёв: {0} — их можно двигать, тянуть и складывать с другими эффектами': 'Layers added: {0} — they can '
                                                                                     'be moved, stretched and '
                                                                                     'stacked with other effects',
 'Виджетов из «{0}»: {1}': 'Widgets from “{0}”: {1}',
 'Не удалось прочитать файл:\n{0}': "Couldn't read the file:\n{0}",
 'Справка недоступна: {0}': 'Help unavailable: {0}',
 '{0} треков  ·  прослушивания подтягиваются из альбомов…': '{0} tracks  ·  plays are loading from the albums…',
 'Скачиваю {0} треков в плейлист «{1}»': 'Downloading {0} tracks into the playlist “{1}”',
 'Плейлист · {0}': 'Playlist · {0}',
 'Доступно {0} карта.': '{0} beatmaps available.',
 'Доступно {0} карты.': '{0} beatmaps available.',
 'Доступно {0} карт.': '{0} beatmaps available.',
 'Текущее время: {0}': 'Current time: {0}',
 '{0} секунда': '{0} second',
 '{0} секунды': '{0} seconds',
 '{0} секунд': '{0} seconds',
 '{0} минута': '{0} minute',
 '{0} минуты': '{0} minutes',
 '{0} минут': '{0} minutes',
 '{0} час': '{0} hour',
 '{0} часа': '{0} hours',
 '{0} часов': '{0} hours',
 '{0} час {1} минута': '{0} hour {1} minute',
 '{0} час {1} минуты': '{0} hour {1} minutes',
 '{0} час {1} минут': '{0} hour {1} minutes',
 '{0} часа {1} минута': '{0} hours {1} minute',
 '{0} часа {1} минуты': '{0} hours {1} minutes',
 '{0} часа {1} минут': '{0} hours {1} minutes',
 '{0} часов {1} минута': '{0} hours {1} minute',
 '{0} часов {1} минуты': '{0} hours {1} minutes',
 '{0} часов {1} минут': '{0} hours {1} minutes'}


# EchoScript: вложенные виджеты, новые блоки и «Готовое» для кода виджета
EXACT.update({
 'Показывать трек в Windows (медиа-виджет, медиаклавиши)': 'Show the track in Windows (media widget, media keys)',
 'Что играет — в плашке громкости Windows, на экране блокировки и в Game Bar; кнопки там и медиаклавиши клавиатуры управляют ECHOES.':
   'What is playing — in the Windows volume flyout, on the lock screen and in Game Bar; its buttons and the keyboard media keys control ECHOES.',
 'Очистка медиатеки и кэша': 'Clean up library and cache', 'Кривые файлы': 'Messy files', 'Клипы': 'Videos', 'Кэш': 'Cache',
 'Очистить кривые файлы…': 'Clean up messy files…', 'Клипы и кэш: посмотреть и удалить…': 'Videos and cache: view and delete…',
 'Медиатека': 'Library', 'Заменить отмеченные': 'Replace checked', 'Отметить уверенные': 'Check confident matches',
 'Снять все': 'Uncheck all', 'Старые файлы — в Корзину': 'Old files to Recycle Bin', 'Свой запрос…': 'Custom query…',
 'Показать все треки': 'Show all tracks', 'Удалить отмеченные клипы': 'Delete checked videos', 'Открыть папку': 'Open folder',
 'Отметить все': 'Check all', 'Удалить': 'Delete', 'Очистить': 'Clear',
 'Релизы с SoundCloud — на YouTube Music исполнителя нет': 'Releases from SoundCloud — the artist is not on YouTube Music',
 'Альбомы не нашлись ни на YouTube Music, ни на SoundCloud': 'No albums on YouTube Music or SoundCloud',
 'Поиск текста': 'Lyrics search', 'Поиск клипа': 'Video search',
 'Исполнитель - название (или что угодно). Результаты появляются по мере ответа сайтов.': 'Artist - title (or anything). Results appear as the sites answer.',
 'Что искать на YouTube. Результаты обновляются, пока вы печатаете.': 'What to search on YouTube. Results update as you type.',
 'С таймингами': 'Synced', 'Без таймингов': 'Not synced', 'Инструментал': 'Instrumental',
 'Применить': 'Apply', 'Скачать этот клип': 'Download this video', 'Открыть на YouTube': 'Open on YouTube',
 'длина совпадает с треком': 'length matches the track', 'Введите запрос': 'Type a query',
 'Ничего не нашлось. Попробуйте другой запрос.': 'Nothing found. Try another query.',
 'Живые обои: туманность «Моей волны»': 'Live wallpaper: My Wave nebula',
 'Туманность «Моей волны»': 'My Wave nebula',
 'Туманность': 'Nebula',
 'Многоцветная туманность, как «Моя волна» в Яндекс Музыке: облака перетекают, по ним бегут нити света, на удар — вспышка. Цвета — до четырёх.':
   'A multicolor nebula like My Wave in Yandex Music: clouds flow, threads of light run across them, a flash on every beat. Up to four colors.',
 '15. Виджеты в виджетах, игры и всё остальное': '15. Widgets in widgets, games and everything else',
 'Обложка любой формы': 'Cover of any shape',
 'Обложка играющего трека любой формы: круг, сердце, звезда, капля, шестерёнка, цветок, свой SVG-контур или свои точки; вращение, пульс от баса, контур, свечение': "The playing track's cover in any shape: circle, heart, star, drop, gear, flower, your own SVG outline or points; spin, bass pulse, outline, glow",
 'Медиатека': 'Library',
 'Вся медиатека с обложками и поиском: колесо — прокрутка, клик — включить. Управляется из других виджетов: move_sel, open, set_filter': 'The whole library with covers and search: wheel scrolls, click plays. Other widgets can drive it: move_sel, open, set_filter',
 'Плеер в стиле iPod': 'iPod-style player',
 'iPod: внутри — настоящая медиатека и обложка (вложенные виджеты). Колесо крутится мышью, MENU — экран, центр — включить/пауза, края — перемотка и пауза': 'iPod: the real library and cover live inside (nested widgets). Turn the wheel with the mouse, MENU switches the screen, the center plays/pauses, the edges skip and pause',
 'Вставить кусочек кода в место курсора (внутри widget { … }): вложенные виджеты, таймеры, звуки, клавиши, маски, холсты, сохранения, управление слоями…': 'Insert a piece of code at the cursor (inside widget { … }): nested widgets, timers, sounds, keys, masks, canvases, saves, layer control…',
 'Вернуться к «Моей волне»': 'Back to My Wave',
 'Поиск…': 'Search…',
 'Медиатека пуста': 'The library is empty',
 'Ничего не найдено': 'Nothing found',
 'Поиск в медиатеке': 'Search the library',
 'Название, исполнитель или альбом:': 'Title, artist or album:',
 'Справочник EchoScript': 'EchoScript reference',
 'Вложенный виджет (child)': 'Nested widget (child)',
 'Нарисовать вложенный виджет здесь (в on draw)': 'Draw a nested widget here (in on draw)',
 'Создать виджет кодом (spawn)': 'Create a widget from code (spawn)',
 'Сообщение родителю и ответ': 'Message to the parent and a reply',
 'Сообщение всем слоям (post)': 'Message to all layers (post)',
 'Найти виджет и вызвать его метод': 'Find a widget and call its method',
 'Управлять другим слоем': 'Control another layer',
 'Таймеры': 'Timers',
 'Плавная анимация (tween)': 'Smooth animation (tween)',
 'Клавиши WASD': 'WASD keys',
 'Звук по клику': 'Sound on click',
 'Мелодия': 'Melody',
 'Картинка в форме сердца': 'Picture shaped like a heart',
 'Маска любой формы': 'Mask of any shape',
 'Клик только по форме (hit_shape)': 'Click only inside a shape (hit_shape)',
 'Холст-рисовалка': 'Drawing canvas',
 'Помехи камеры наблюдения': 'Security-camera static',
 'Сохранить рекорд': 'Save a record',
 'Выбор варианта (match)': 'Pick a branch (match)',
 'Защита от ошибки (try)': 'Guard against errors (try)',
 'Строка с подстановкой': 'Template string',
})

# справка конструктора тем: страница целиком (CSS + глава) → английская глава
try:
    import studio_help as _sh
    import studio_help_en as _she
    for _k, _t, _body in _sh.CHAPTERS:
        if _k in _she.BODY:
            EXACT[_sh.CSS + _body] = _sh.CSS + _she.BODY[_k]
except Exception:                                          # noqa: BLE001
    pass

# шаффл по исполнителю, блоки как в Scratch, Discord «Слушает»
EXACT.update({'Артист': 'Artist', 'Шаффл по исполнителю: все его треки вперемешку (правый клик — выбрать исполнителя, Ctrl+Shift+S)': 'Shuffle by artist: all their tracks shuffled (right click — pick an artist, Ctrl+Shift+S)', 'Кнопка «Шаффл по исполнителю»': 'Button “Shuffle by artist”', 'Шаффл по исполнителю': 'Shuffle by artist', 'Все исполнители': 'All artists', 'Библиотека пуста': 'Library is empty', 'Исполнитель': 'Artist', '⤮ Исполнитель': '⤮ Artist', '⤮ Артист': '⤮ Artist', 'Код': 'Code', 'Блоки': 'Blocks', 'Код EchoScript текстом': 'EchoScript code as text', 'Программирование блоками как в Scratch: все функции EchoScript — блоки, их тянут из палитры и соединяют мышью. Каждая правка сразу пишет код': 'Scratch-style block programming: every EchoScript function is a block you drag from the palette and snap together. Every change writes the code at once', 'Обложка трека в Discord (ищется на Deezer)': 'Track cover in Discord (looked up on Deezer)', 'Discord показывает только картинки из интернета: обложка находится по исполнителю и названию на Deezer и кешируется. Выключено — пластинка ECHOES': 'Discord only shows images from the internet: the cover is found on Deezer by artist and title and cached. Off — the ECHOES vinyl', 'Показывать в Discord и на паузе': 'Show in Discord while paused too', 'Выключено — как у Spotify: на паузе статус пропадает': 'Off — like Spotify: the status disappears on pause', 'В Discord — «Слушает ECHOES», как у Spotify: сначала исполнитель, потом трек и альбом, полоса прогресса и кнопка «Слушать на YouTube Music». Нужен запущенный Discord.': 'Discord shows “Listening to ECHOES” like Spotify: artist first, then track and album, a progress bar and a “Listen on YouTube Music” button. Discord must be running.', 'Слушать на YouTube Music': 'Listen on YouTube Music', 'Слушает в ECHOES': 'Listening in ECHOES', 'События': 'Events', 'Управление': 'Control', 'Переменные': 'Variables', 'Слой': 'Layer', 'Датчики': 'Sensing', 'Плеер': 'Player', 'Рисование': 'Drawing', 'Формы и картинки': 'Shapes & images', 'Операторы': 'Operators', 'Математика': 'Math', 'Списки и текст': 'Lists & text', 'Виджеты': 'Widgets', 'Время и анимация': 'Time & animation', 'Звуки': 'Sounds', 'Данные и окна': 'Data & windows', 'Мои функции': 'My functions', 'Другое': 'Other', 'запуск': 'start', 'каждый кадр': 'every frame', 'рисование': 'draw', 'клик': 'click', 'нажатие мыши': 'mouse down', 'отпускание мыши': 'mouse up', 'двойной клик': 'double click', 'перетаскивание': 'drag', 'движение мыши': 'mouse move', 'курсор зашёл': 'mouse enter', 'курсор ушёл': 'mouse leave', 'колесо мыши': 'mouse wheel', 'удар в музыке': 'beat', 'смена трека': 'track change', 'нажата клавиша': 'key down', 'клавиша отпущена': 'key up', 'сообщение': 'message', 'смена размера': 'resize', 'удаление': 'destroy', 'когда': 'when', 'функция': 'function', 'данные виджета': 'widget data', 'свойство': 'property', 'переменная виджета': 'widget variable', 'вложенный': 'child', 'пусть': 'let', 'задать': 'set', 'если': 'if', 'иначе если': 'else if', 'то': 'then', 'иначе': 'else', 'пока': 'while', 'для': 'for', 'в': 'in', 'вернуть': 'return', 'прервать цикл': 'break loop', 'к следующему шагу': 'next step', 'блок': 'block', 'попробовать': 'try', 'если ошибка': 'on error', 'выбор по': 'match', 'вариант': 'case', 'добавить': 'add', 'код': 'code', 'тема': 'theme', 'сцена': 'scene', 'список': 'list', 'словарь': 'dict', 'текст': 'text', 'не': 'not', 'не в': 'not in', 'значение': 'value', 'условие': 'condition', 'переменная': 'variable', 'список / 0..10': 'list / 0..10', 'объект': 'object', '№': '#', 'от': 'from', 'до': 'to', 'да': 'yes', 'нет': 'no', 'Найти блок: circle, клик, громкость…': 'Find a block: circle, click, volume…', 'Какой виджет показывать блоками (в коде их несколько)': 'Which widget to show as blocks (the code has several)', 'Упорядочить': 'Tidy up', 'Разложить скрипты аккуратными колонками': 'Lay scripts out in neat columns', 'Мельче (Ctrl + колесо)': 'Smaller (Ctrl + wheel)', 'Обычный масштаб': 'Normal zoom', 'Крупнее (Ctrl + колесо)': 'Larger (Ctrl + wheel)', 'Отпустите здесь,\nчтобы удалить': 'Drop here\nto delete', 'Перетащите сюда блоки из палитры слева:\n«когда рисование» → «fill» → «circle»…': 'Drag blocks here from the palette on the left:\n“when draw” → “fill” → “circle”…', 'Дублировать': 'Duplicate', 'Удалить блок': 'Delete block', 'Удалить вместе с блоками ниже': 'Delete with blocks below', 'Комментарий…': 'Comment…', 'Убрать «иначе»': 'Remove “else”', 'Добавить «иначе»': 'Add “else”', 'Убрать «если ошибка»': 'Remove “on error”', 'Добавить «если ошибка»': 'Add “on error”', 'Без второй переменной': 'Without second variable', 'Две переменные (номер, значение)': 'Two variables (index, value)', 'Заменить кодом…': 'Replace with code…', 'Скопировать код блока': 'Copy block code', 'Вставить код как блоки…': 'Paste code as blocks…', 'Упорядочить блоки': 'Tidy up blocks', 'Масштаб 100%': 'Zoom 100%', 'Комментарий': 'Comment', 'Комментарий к блоку (попадёт в код как // …):': 'Block comment (goes into the code as // …):', 'Код вместо блока:': 'Code instead of the block:', 'Своя строка (или несколько) на EchoScript:': 'Your own EchoScript line (or several):', 'Вставить код как блоки': 'Paste code as blocks', 'Код EchoScript (on draw { … }, fn …, или просто инструкции):': 'EchoScript code (on draw { … }, fn …, or plain statements):', 'Параметры — через запятую: x, y, z = 1': 'Parameters — comma separated: x, y, z = 1', 'Имя — буквы, цифры и _, не с цифры': 'Name — letters, digits and _, not starting with a digit', 'Это не имя переменной': 'That is not a variable name', 'Сюда — только переменная: перетащите её из «Переменных»': 'Only a variable fits here: drag one from “Variables”', 'Цвет': 'Color', 'Свойства (prop) и переменные (state) виджета': 'Widget properties (prop) and variables (state)', 'если условие — выполнить блоки внутри': 'if the condition holds — run the blocks inside', 'если … иначе …': 'if … else …', 'повторять, пока условие верно': 'repeat while the condition holds', 'повторить: i = 0, 1, … 9': 'repeat: i = 0, 1, … 9', 'для каждого элемента списка': 'for each item of a list', 'номер и значение каждого элемента': 'index and value of each item', 'выбор варианта (match)': 'pick a case (match)', 'ошибка внутри не ломает виджет': 'an error inside does not break the widget', 'выйти из обработчика / функции (с значением)': 'leave the handler / function (with a value)', 'выйти из цикла': 'leave the loop', 'сразу к следующему шагу цикла': 'jump to the next loop step', 'условие ? да : нет': 'condition ? yes : no', 'функция-значение: для after, every, prompt, map …': 'function value: for after, every, prompt, map …', 'своя функция внутри обработчика': 'your own function inside a handler', 'любой код EchoScript текстом': 'any EchoScript code as text', 'любое выражение текстом': 'any expression as text', 'переменная виджета — живёт между кадрами': 'widget variable — lives between frames', 'свойство — видно в инспекторе слоя': 'property — shown in the layer inspector', 'вложенный виджет (свой класс или блок каталога)': 'child widget (your class or a catalog block)', 'новая переменная внутри обработчика': 'new variable inside a handler', 'задать значение': 'set a value', 'изменить на …': 'change by …', 'переменная этого виджета': 'variable of this widget', 'поле виджета': 'widget field', 'и': 'and', 'или': 'or', 'есть ли в списке / строке / словаре': 'is it in the list / string / dict', 'минус': 'minus', 'диапазон чисел': 'number range', 'текст с подстановкой `…{x}…`': 'template text `…{x}…`', 'элемент списка по номеру': 'list item by index', 'поле словаря / виджета': 'dict / widget field', 'строка': 'string', 'число': 'number', 'истина / ложь / пусто': 'true / false / nil', 'новая функция виджета': 'new widget function', 'вызвать любую функцию или метод по имени (имя — щелчком)': 'call any function or method by name (click the name)'})
TEMPLATES.update({'Шаффл по исполнителю: {0} · {1}': 'Shuffle by artist: {0} · {1}', 'В библиотеке нет треков исполнителя {0}': 'No tracks by {0} in the library', 'Шаффл: {0}': 'Shuffle: {0}', 'Блоками не открыть, пока в коде ошибка: {0}': 'Blocks cannot open while the code has an error: {0}', 'Блоки недоступны: {0}': 'Blocks unavailable: {0}', 'блоков: {0}  ·  правый клик — меню, Ctrl+колесо — масштаб': 'blocks: {0}  ·  right click — menu, Ctrl+wheel — zoom', 'Виджет: {0}': 'Widget: {0}', 'Не разобрать: {0}': 'Cannot parse: {0}', 'поле слоя {0}': 'layer field {0}', 'своя функция {0}({1})': 'your function {0}({1})'})

# Discord: активности ECHOES Studio, конструктор тем
EXACT.update({
    'Конструктор тем ECHOES': 'ECHOES theme builder',
    'Показывать в Discord ECHOES Studio и конструктор тем': 'Show ECHOES Studio and the theme builder in Discord',
    'Отдельные активности со своими иконками: «ECHOES Studio» (проект, BPM), «Конструктор тем ECHOES» (тема)':
        'Separate activities with their own icons: “ECHOES Studio” (project, BPM), “ECHOES theme builder” (theme)',
    'Discord показывает иконки активностей, только если они загружены в ваше приложение Discord.\n\n'
    '1. Откроется папка с иконками и страница Art Assets приложения.\n'
    '2. Нажмите «Add Image(s)» и загрузите studio.png и theme_studio.png.\n'
    '3. Имена (ключи) оставьте как у файлов: studio, theme_studio. Сохраните.\n\n'
    'Discord обновляет ассеты до 10 минут. Открыть?':
        'Discord only shows activity icons if they are uploaded to your Discord app.\n\n'
        '1. The icon folder and the Art Assets page of the app will open.\n'
        '2. Click “Add Image(s)” and upload studio.png and theme_studio.png.\n'
        '3. Keep the names (keys) as the file names: studio, theme_studio. Save.\n\n'
        'Discord updates assets within 10 minutes. Open?',
    'Иконки активностей для Discord…': 'Activity icons for Discord…',
    'Открыть папку с иконками и страницу Art Assets вашего приложения Discord': 'Open the icon folder and the Art Assets page of your Discord app',
    'Иконки для Discord': 'Icons for Discord',
})
TEMPLATES.update({
    'Делает тему: «{0}»': 'Making a theme: “{0}”', 'Программирует блоками: «{0}»': 'Coding with blocks: “{0}”',
    'Пишет код на EchoScript: «{0}»': 'Writing EchoScript: “{0}”', 'Делает музыку: «{0}»': 'Making music: “{0}”',
    'слоёв: {0}': 'layers: {0}',
})

# стриминг онлайн-треков и волна
EXACT.update({
    'Слушать онлайн без скачивания': 'Listen online without downloading',
    'Треки из поиска, альбомов и исполнителей играют сразу — потоком с YouTube Music / SoundCloud. Скачать в коллекцию — кнопкой у трека. В «Моей волне» новые похожие треки всегда идут потоком.':
        'Tracks from search, albums and artists play instantly — streamed from YouTube Music / SoundCloud. Download to your collection with the button on a track. In “My Wave” new similar tracks are always streamed.',
    'Слушать сейчас (онлайн, без скачивания)': 'Listen now (online, no download)',
    'Слушать сейчас': 'Listen now', 'Играть следующим': 'Play next', 'Слушать': 'Listen',
    'Все треки исполнителя онлайн, сразу — без скачивания': 'All of the artist’s tracks online, right away — no download',
    'сейчас играет · онлайн': 'now playing · online',
    'Скачать этот трек в коллекцию': 'Download this track to the collection',
    'Этот трек уже в коллекции': 'This track is already in the collection',
    'Трек ещё не найден в сети — подождите, пока он заиграет': 'The track is not found online yet — wait until it starts',
    'Онлайн': 'Online',
    'Новое для вас · онлайн, похоже на то, что вы слушаете': 'New for you · online, similar to what you listen to',
})
TEMPLATES.update({
    'Подключаю поток: {0}…': 'Connecting stream: {0}…',
    'Не удалось включить «{0}»: {1}': 'Could not play “{0}”: {1}',
    'В очереди: {0}': 'Queued: {0}',
    'Скачиваю: {0} — {1}': 'Downloading: {0} — {1}',
    'Новое для вас · онлайн, похоже на то, что вы слушаете · совпадение {0}%{1}': 'New for you · online, similar to what you listen to · match {0}%{1}',
})

# показать в проводнике, найти в коллекции
EXACT.update({
    'Показать в проводнике': 'Show in Explorer',
    'Показать в проводнике (онлайн-трек)': 'Show in Explorer (online track)',
    'Онлайн-трек — файла на компьютере нет. Скачать: кнопка у трека или меню волны':
        'Online track — there is no file on this computer. Download: the track button or the wave menu',
    'Файл не найден': 'File not found',
    'Найти в коллекции': 'Find in collection',
    'Скачать трек': 'Download track',
    'Свой запрос «исполнитель - название» — поиск текста по всем источникам':
        'Your own “artist - title” query — search lyrics in all sources',
    'Найти трек в коллекции (правый клик — ещё: показать в проводнике, текст)':
        'Find the track in the collection (right click — more: show in Explorer, lyrics)',
    'Трек играет онлайн — в коллекции его нет. Скачать: меню волны или кнопка у трека':
        'The track is playing online — it is not in the collection. Download: the wave menu or the track button',
    'Этого трека нет в коллекции': 'This track is not in the collection',
    'Выбрать': 'Select',
})
TEMPLATES.update({
    'Файл не найден: {0}': 'File not found: {0}',
    'Не удалось открыть проводник: {0}': 'Could not open Explorer: {0}',
})

# клипы онлайн
EXACT.update({'Клипы онлайн, без скачивания': 'Clips online, without downloading', 'Находить официальные клипы сами': 'Find official clips automatically', 'Найти клип': 'Find clip', 'Клип ещё не найден': 'Clip not found yet', 'Сохранить клип на компьютер': 'Save clip to this computer', 'Подключаю клип…': 'Connecting clip…', 'Клип сейчас недоступен — попробуйте «Другой клип»': 'The clip is unavailable now — try “Other clip”', 'Клип играет прямо из YouTube — видео на компьютер не скачивается. Скачать\nконкретный клип: в режиме «Клип» → «Другой клип» → «Сохранить клип на компьютер».': 'The clip plays straight from YouTube — the video is not downloaded. To download\na clip: Clip mode → “Other clip” → “Save clip to this computer”.', 'Для каждого играющего трека плеер в фоне найдёт официальный клип (YouTube) и\nподгонит его по звуку, чтобы режим «Клип» открывался сразу. С «клипами онлайн»\nничего не скачивается; без них клип скачивается в ~/Echoes/clips.': 'For every playing track the player finds the official clip (YouTube) in the background and\nsyncs it by sound so Clip mode opens instantly. With “clips online” nothing is downloaded;\nwithout it the clip is downloaded to ~/Echoes/clips.', 'Скачиваю клип…': 'Downloading clip…'})
TEMPLATES.update({'{0}  ·  онлайн': '{0}  ·  online', 'Клип: {0}': 'Clip: {0}'})

# Скачать альбом, теги трека из интернета
EXACT.update({'Скачать альбом': 'Download album', 'Скачать недостающие треки альбома в коллекцию': "Download the album's missing tracks to the collection", 'Скачать альбом в коллекцию': 'Download album to collection', 'Поменять теги трека (Обложка, автор и тд)': 'Change track tags (cover, artist, etc.)', 'Исполнитель, альбом, обложка и название файла — теги для этого трека дополнялись из интернета или их не хватает': "Artist, album, cover and title of the file — this track's tags were filled in from the internet or are missing", 'Расположение интерфейса': 'Interface layout', 'Готово': 'Done', 'Сбросить всё': 'Reset all', 'Как в скине': 'As in skin', 'скрыто': 'hidden', 'скин': 'skin', 'Перетаскивайте мышью · колесо — размер · правая кнопка — спрятать · двойной клик — на место': 'Drag with the mouse · wheel — size · right click — hide · double click — reset', 'Здоровье': 'Health', 'Счёт': 'Score', 'Точность и прогресс': 'Accuracy and progress', 'Комбо': 'Combo', 'Клавиши': 'Keys', 'Шкала ошибок': 'Hit error meter', 'Моды': 'Mods', 'Таблица рекордов': 'Leaderboard', 'Played by': 'Played by', 'on': 'on', 'мс': 'ms', 'позже': 'late', 'раньше': 'early', 'ПРОВАЛ': 'FAILED', 'НОВЫЙ РЕКОРД!': 'NEW RECORD!', 'Смотреть повтор': 'Watch replay', 'Подогнать смещение': 'Adjust offset', 'Заново': 'Retry'})
TEMPLATES.update({'  Скачать альбом ({0})': '  Download album ({0})', '  Скачивается {0} из {1}': '  Downloading {0} of {1}', 'Альбом скачивается в коллекцию: {0}': 'Album is downloading to the collection: {0}', 'Теги трека дополнены: {0}': 'Track tags filled in: {0}'})

# Discord: строка текста, фото исполнителя, очередь, ссылка, статистика; вокал в генераторе
EXACT.update({'Живая строка текста в статусе': 'Live lyrics line in the status', 'Третья строка статуса — то, что поют прямо сейчас (если у трека синхронизированный текст)': 'The third status line shows what is being sung right now (if the track has synced lyrics)', 'Фото исполнителя на обложке': 'Artist photo on the cover', 'Маленький кружок с фото исполнителя (Deezer)': 'A small circle with the artist photo (Deezer)', 'Место в очереди «(3 из 12)»': 'Queue position “(3 of 12)”', 'Номер трека в плейлисте, альбоме или волне': 'Track number in the playlist, album or wave', 'Кнопка-ссылка на трек': 'Track link button', 'Вторая кнопка: трек на Deezer, Apple Music, SoundCloud или YouTube': 'Second button: the track on Deezer, Apple Music, SoundCloud or YouTube', 'Статистика в подсказке': 'Stats in the tooltip', 'Наведите на фото исполнителя: сколько вы сегодня слушаете в ECHOES и какой раз играет этот трек': 'Hover the artist photo: how long you listened in ECHOES today and how many times this track has played', 'Открыть на Deezer': 'Open on Deezer', 'Открыть в Apple Music': 'Open in Apple Music', 'Открыть на SoundCloud': 'Open on SoundCloud', 'Открыть на YouTube': 'Open on YouTube', 'Открыть в Spotify': 'Open in Spotify', 'Открыть трек': 'Open track', 'Слушать вокал (нейросеть): ноты по слогам и флоу голоса': 'Listen to vocals (neural net): notes follow syllables and vocal flow'})
TEMPLATES.update({'сегодня в ECHOES {0} ч {1} мин': 'today in ECHOES {0} h {1} min', 'сегодня в ECHOES {0} мин': 'today in ECHOES {0} min', 'этот трек — {0}-й раз': 'this track — play #{0}'})

# Дискография: анрелизы с SoundCloud
EXACT.update({'Релизы': 'Releases', 'Треки с SoundCloud исполнителя, которых нет на YouTube Music: сниппеты, демки, слитое, фриты': "The artist's SoundCloud tracks that aren't on YouTube Music: snippets, demos, leaks, freestyles"})
TEMPLATES.update({'Анрелизы · {0}': 'Unreleased · {0}'})

# Network controls and original monochrome UI drawings. Emoji spellings here
# are catalogue keys only; ui_symbols restores the drawings after translation.
EXACT.update({
    'РАЗДЕЛЫ': 'SECTIONS',
    'Подписки': 'Following',
    'Тирлист музыки': 'Music tier list',
    'Дуэль треков': 'Track duel',
    'Сеть выключена': 'Network is off',
    'Мой код': 'My code',
    'Включить сеть': 'Enable network',
    'Новая группа': 'New group',
    'Лента': 'Feed',
    'Сообщения': 'Messages',
    'Друзья': 'Friends',
    'Слушать вместе': 'Listen together',
    'Треды': 'Threads',
    'Моды': 'Mods',
    'не в сети': 'offline',
    'в сети': 'online',
    'Позвонить': 'Call',
    'Плейлисты': 'Playlists',
    'Сообщение…': 'Message…',
    'Нажмите — растягиваемое окно; правый клик — в «Мои GIF», сохранить файлом':
        'Click for a resizable window; right-click to save to My GIFs or as a file',
    '🎁  Подарок другу': '🎁  Gift to a friend',
    'Подарок отправлен 🎁': 'Gift sent 🎁',
    '🎁  Подарок: рамка, витрина, трек дня…': '🎁  Gift: frame, showcase, track of the day…',
    '📻  Запустить радиостанцию': '📻  Start a radio station',
    '🎙  Удерживайте — сказать в эфир': '🎙  Hold to speak on air',
    '🔒  Сделать закрытым (убрать из профиля)': '🔒  Make private (remove from profile)',
    '🌐  Сделать открытым (виден в профиле всем)': '🌐  Make public (visible on your profile)',
    '👥  Позвать ещё друзей…': '👥  Invite more friends…',
    '👥  Сделать совместным (правят друзья)…': '👥  Make collaborative (friends can edit)…',
    'друзья видят «🎮 Играет в …», пока игра на весь экран':
        'friends see “🎮 Playing …” while a game is full screen',
    '🔇 Микрофон выключен': '🔇 Microphone muted',
    '🎙 Микрофон включён': '🎙 Microphone unmuted',
    '🎧 Звук собеседников выключен': '🎧 Voice audio muted',
    '🎧 Звук включён': '🎧 Voice audio unmuted',
    '📌 Виджеты закреплены': '📌 Widgets pinned',
    '📌 Все виджеты закреплены': '📌 All widgets pinned',
    'ВИДЖЕТЫ (📌 — видны поверх игры всегда)': 'WIDGETS (📌 — always visible over the game)',
    '⏸ Пауза': '⏸ Paused',
    '⏭ Следующий трек': '⏭ Next track',
    'кнопка «⬇ у друга» и хост комнаты': 'the “⬇ from a friend” button and the room host',
    '◀ ⏯ ▶ при наведении на значок': '◀ ⏯ ▶ when hovering over the icon',
})
TEMPLATES.update({
    'Показать ещё · {0}': 'Show more · {0}',
    '🏆 Прошлая неделя «{0}»: {1} — {2}': '🏆 Last week “{0}”: {1} — {2}',
    '🏆 Челлендж: <b>{0}</b>': '🏆 Challenge: <b>{0}</b>',
    '🎮 Играет в {0}': '🎮 Playing {0}',
    '🎮  Играет в {0}': '🎮  Playing {0}',
    'в сети · 🎮 {0}': 'online · 🎮 {0}',
    '🎁  Вам подарок — {0}': '🎁  A gift for you — {0}',
    '🎁  Вы подарили {0}': '🎁  You gave {0}',
    '🎁  Вам подарили {0}': '🎁  You received {0}',
    '🛡 скрыто модерацией — {0}': '🛡 hidden by moderation — {0}',
    '🛡 комментарий скрыт модерацией — {0}': '🛡 comment hidden by moderation — {0}',
    '🛡 Модерация скрыла: {0} — запрещённое и авторы, на которых пожаловались':
        '🛡 Hidden by moderation: {0} — blocked content and reported authors',
    '📞 Зовём {0}…': '📞 Calling {0}…',
    '✉ Отправлено: {0}': '✉ Sent: {0}',
})

EXACT.update({
    'Тема и скругление': 'Theme and corners',
    'СКРУГЛЕНИЕ ИНТЕРФЕЙСА': 'INTERFACE CORNERS',
    'Включить трек': 'Play track',
    'Цвета, шрифты, отдельное скругление кнопок и интерфейса, стекло, фон и живые эффекты — в одном окне с предпросмотром.':
        'Colors, fonts, separate button and panel corners, glass, backgrounds and live effects in one editor with a preview.',
})
TEMPLATES.update({'Панели и карточки: {0} px': 'Panels and cards: {0} px',
                  'Скругление кнопок: {0} px': 'Button corners: {0} px'})

EXACT.update({                                   # v30: ник, мини-профиль, коллекция, режим геймера
    '  Перемешать': '  Shuffle',
    'Найти пропавшие треки': 'Find missing tracks',
    'Сменить тему': 'Change theme',
    'Стиль ника…': 'Name style…',
    'Мини-профиль (баннер, местоимения, ачивки)…': 'Mini profile (banner, pronouns, achievements)…',
    'Стиль ника': 'Name style',
    'Выбор шрифта': 'Font',
    'Выбор эффекта': 'Effect',
    'Выбор цвета': 'Color',
    'Минималистичный': 'Minimal', 'Градиент': 'Gradient', 'Неон': 'Neon', 'Мультфильм': 'Toon',
    'Выделение': 'Pop', 'Гамми': 'Gummy', 'Призма': 'Prism',
    'Основной': 'Main', 'Второй': 'Second', 'Сбросить': 'Reset', 'Сохранить': 'Save', 'Отмена': 'Cancel',
    'Мини-профиль': 'Mini profile', 'Баннер': 'Banner', 'Местоимения': 'Pronouns', 'О себе': 'About me',
    'Ачивки на карточке': 'Achievements on the card', 'Как увидят другие': 'How others see it',
    'Выбрать файл…': 'Choose file…', 'Убрать картинку': 'Remove picture', 'Цвет 1': 'Color 1', 'Цвет 2': 'Color 2',
    'Изменить стиль ника…': 'Change name style…', 'Открыть профиль': 'Open profile', 'АЧИВКИ': 'ACHIEVEMENTS',
    '  Включить режим геймера': '  Turn gamer mode on',
    '  Режим геймера включён — выключить': '  Gamer mode is on — turn off',
})

EXACT.update({                                   # v31: настройки без окон, конструктор стримера
    'Темы оформления': 'Themes', 'Все темы плеера — выберите, и плеер переоденется': 'All player themes — pick one to switch',
    'Конструктор тем': 'Theme studio', 'Открыть': 'Open', 'Включить': 'Turn on', 'Режим обложки': 'Cover mode',
    'Масштаб и окно': 'Scale and window', 'Размер и пропорции окна, масштаб интерфейса': 'Window size, aspect and UI scale',
    'Перевод и прокрутка текста': 'Lyrics translation and scrolling', 'Редактор текста': 'Lyrics editor',
    'Открыть для трека': 'Open for track', 'Импорт из Spotify': 'Import from Spotify',
    'Плейлист из файла': 'Playlist from file', 'Выбрать файл…': 'Choose file…', 'Плейлисты на телефон': 'Playlists to phone',
    'Сохранить файл…': 'Save file…', 'Куда класть файлы тем и плейлистов': 'Where to put theme and playlist files',
    'Найти теги для всей музыки': 'Find tags for all music', 'Очистка медиатеки и кэша': 'Library and cache cleanup',
    'Палитра команд': 'Command palette', 'Конструктор окна стримера': 'Streamer window designer',
    'Профиль': 'Profile', 'Страница профиля': 'Profile page', 'Проверить': 'Check', 'Проверить ещё раз': 'Check again',
    'ШАБЛОНЫ': 'TEMPLATES', 'СЛОИ': 'LAYERS', 'ОКНО': 'WINDOW', 'Компакт': 'Compact', 'Широкая полоса': 'Wide bar',
    'Карточка': 'Card', 'Минимал': 'Minimal', '  Окно стримера': '  Streamer window', 'Цвет': 'Color',
    'Прозрачность': 'Opacity', 'Скругление': 'Corners', 'Шрифт': 'Font', 'Размер': 'Size', 'Текст': 'Text',
    'Фон': 'Background', 'Свой': 'Custom', 'Слева': 'Left', 'По центру': 'Center', 'Справа': 'Right',
    'Без рамки (для прозрачного фона)': 'Frameless (for a transparent background)',
    'Выберите слой на холсте или в списке': 'Pick a layer on the canvas or in the list',
    'Выбрать картинку / GIF…': 'Choose picture / GIF…', 'Файл не выбран': 'No file chosen',
})

EXACT.update({                                   # v32: альбомы/плейлисты в поиске, перенос с площадок, язык перевода
    'Альбомы': 'Albums', 'Публичные плейлисты': 'Public playlists', 'Язык перевода': 'Translation language',
    '  Сохранить как плейлист': '  Save as playlist', 'Перенести плейлист с площадки': 'Transfer a playlist',
    'Русский': 'Russian', 'Английский': 'English', 'Украинский': 'Ukrainian', 'Немецкий': 'German',
    'Французский': 'French', 'Испанский': 'Spanish', 'Итальянский': 'Italian', 'Японский': 'Japanese',
    'Корейский': 'Korean', 'Китайский': 'Chinese', 'Турецкий': 'Turkish', 'Польский': 'Polish',
    'Португальский': 'Portuguese', 'Казахский': 'Kazakh', 'Белорусский': 'Belarusian',
})

EXACT.update({                                   # v35: сортировка, экстремальная скорость
    '  Сортировка': '  Sort', 'Как добавлены': 'Date added', 'В обратном порядке': 'Reversed',
    'Сначала новые': 'Newest first', 'Сначала старые': 'Oldest first', 'По названию': 'Title',
    'По исполнителю': 'Artist', 'По альбому': 'Album', 'По длительности': 'Duration', 'Часто слушаю': 'Most played',
    '  Сначала новые': '  Newest first', '  Сначала старые': '  Oldest first', '  По названию': '  Title',
    '  По исполнителю': '  Artist', '  По альбому': '  Album', '  По длительности': '  Duration',
    '  Часто слушаю': '  Most played', '  Как добавлены': '  Date added', '  В обратном порядке': '  Reversed',
    'Экстремальная скорость': 'Extreme speed', 'Обычная скорость': 'Normal speed',
    'Жёстко медленно — низко и тягуче': 'Ultra slow — low and heavy', 'Медленнее и ниже': 'Slower and lower',
    'Быстрее и выше': 'Faster and higher', 'Жёстко быстро — как бурундук': 'Ultra fast — chipmunk mode',
})

# «Сейчас играет» во всё окно, колонка альбома, «Ещё» в плеере
EXACT.update({
    'Сейчас играет — на весь экран (Ctrl+Shift+N). Правый клик — найти в коллекции, текст, ещё':
        'Now playing — full window (Ctrl+Shift+N). Right click — find in collection, lyrics, more',
    'Сейчас играет — на весь экран  (Ctrl+Shift+N)': 'Now playing — full window  (Ctrl+Shift+N)',
    'Обложка, текст и очередь — на всё окно': 'Cover, lyrics and queue — across the whole window',
    'Свернуть (Esc)': 'Close (Esc)',
    'Далее': 'Up next',
    'Громкость: нажмите — выключить звук': 'Volume: click to mute',
    'Ещё: сейчас играет, клип, реакция, звук, тема, настройки':
        'More: now playing, video, reaction, sound, theme, settings',
    'Реакция на этот момент': 'React to this moment',
    'Звук и эффекты': 'Sound and effects',
})
