"""Atomic profile JSON with one last-good copy; reads never modify forensic data.

This protects against interrupted application writes, not a guarantee against
filesystem or device failure. It deliberately avoids synchronous fsync on each
UI settings change; closing the temporary file flushes Python's buffers.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import threading
import time

_IO_LOCK=threading.RLock()


def backup_path(path):
    path=Path(path)
    return path.with_name(path.name+'.bak')


def _read(path,default,validator=None):
    value=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    # A wrong-shaped profile container is not a usable library/settings file.
    # Scalars retain the original generic helper behavior.
    expected=list if isinstance(default,list) else dict if isinstance(default,dict) else None
    if expected is not None and not isinstance(value,expected):
        raise ValueError('unexpected JSON container')
    if validator is not None and not validator(value):
        raise ValueError('unusable JSON records')
    return value


def load_json(path,default,validator=None):
    try:path=Path(path)
    except (TypeError,ValueError):return default
    # Windows readers opened through normal Python IO do not share DELETE.
    # Avoid replacing a file while another local profile reader holds it open.
    queued=pending(path)                                  # сохранено, но ещё пишется в фоне
    if queued is not None:
        try:
            value=json.loads(queued.decode('utf-8'))
            expected=list if isinstance(default,list) else dict if isinstance(default,dict) else None
            if expected is None or isinstance(value,expected):return value
        except ValueError:pass
    with _IO_LOCK:
        try:return _read(path,default,validator)
        except (OSError,ValueError,UnicodeError):pass
        try:
            value=_read(backup_path(path),default,validator)
            print('[data] recovered',path.name,'from last-good copy')
            return value
        except (OSError,ValueError,UnicodeError):return default


_OWN={}                                                   # путь → ((mtime_ns, size), номер записи)
_IDS={}                                                   # путь → номер последней ЗАПРОШЕННОЙ записи
_SEQ=[0]
_ID_LOCK=threading.Lock()


def _next_id(path):
    with _ID_LOCK:
        _SEQ[0]+=1;_IDS[str(path)]=_SEQ[0]
        return _SEQ[0]


def last_write_id(path):
    """Номер последней записи этого файла, запрошенной в этом процессе (в очереди или уже на диске)."""
    return _IDS.get(str(Path(path)))


def written(path):
    """(подпись файла, номер записи) сразу после последней записи из этого процесса; None — не писали.
    По номеру library_guard отличает СВОЮ фоновую запись от чужой и не перечитывает всю коллекцию с диска
    на каждой смене трека."""
    return _OWN.get(str(Path(path)))


def _replace(path,payload,wid=None):
    temporary=None
    try:
        fd,name=tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.tmp',dir=path.parent)
        temporary=Path(name)
        with os.fdopen(fd,'wb') as stream:stream.write(payload)
        # Windows: файл на миг держит антивирус или чтение (ежедневная копия) - замена падала с WinError 5,
        # и сохранение молча терялось. Несколько коротких повторов (всего до 0,3 с).
        for attempt in range(6):
            try:
                os.replace(temporary,path);break
            except PermissionError:
                if attempt==5:raise
                time.sleep(0.02*(attempt+1))
        temporary=None
        try:
            st=path.stat();_OWN[str(path)]=((st.st_mtime_ns,st.st_size),wid)
        except OSError:_OWN.pop(str(path),None)
    finally:
        if temporary is not None:
            try:temporary.unlink()
            except FileNotFoundError:pass


def save_json(path,obj):
    path=Path(path)
    # Serialize and encode before touching either existing file. In particular,
    # an invalid object or unicode value must not truncate a healthy library.
    payload=json.dumps(obj,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    with _IO_LOCK:
        _replace(path,payload,_next_id(path))
        # Refresh the backup from the newly committed, known-valid payload, never
        # by copying a potentially corrupt preexisting target over the good copy.
        try:_replace(backup_path(path),payload)
        except OSError as error:print('[data] last-good copy could not be updated:',path.name,str(error))


# ── запись в фоне: поток интерфейса только сериализует (мс), диск — отдельный поток ──
# На медленном диске и с антивирусом, который проверяет каждый новый файл, синхронная запись настроек
# (0,5 МБ + копия) останавливала интерфейс на десятки и сотни мс — на каждом клике, ползунке, треке.
_PENDING={}
_COND=threading.Condition()
_WRITER=[None]
_BUSY=[0]


def _writer():
    while True:
        with _COND:
            while not _PENDING:
                _COND.wait()
            items=[(key,payload,_IDS.get(key)) for key,payload in _PENDING.items()];_PENDING.clear();_BUSY[0]+=1
        try:
            for key,payload,wid in items:
                path=Path(key)
                try:
                    with _IO_LOCK:
                        _replace(path,payload,wid)
                        try:_replace(backup_path(path),payload)
                        except OSError as error:print('[data] last-good copy could not be updated:',path.name,str(error))
                except OSError as error:
                    print('[data] write failed:',path.name,str(error))
        finally:
            with _COND:
                _BUSY[0]-=1;_COND.notify_all()


def save_json_async(path,obj):
    """Как save_json, но запись — в фоне; одна и та же запись подряд склеивается (пишется последняя)."""
    payload=json.dumps(obj,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    with _COND:
        _PENDING[str(Path(path))]=payload;_next_id(Path(path))
        if _WRITER[0] is None or not _WRITER[0].is_alive():
            _WRITER[0]=threading.Thread(target=_writer,daemon=True,name='json-writer');_WRITER[0].start()
        _COND.notify_all()


def pending(path):
    """Ещё не записанное содержимое файла (чтобы чтение сразу после сохранения видело новое)."""
    with _COND:
        return _PENDING.get(str(Path(path)))


def flush(timeout=10.0):
    """Дождаться записи всего, что в очереди (при выходе)."""
    import time
    end=time.monotonic()+timeout
    with _COND:
        while (_PENDING or _BUSY[0]) and time.monotonic()<end:
            _COND.wait(0.05)


import atexit as _atexit
_atexit.register(flush)


def save_bytes_async(path, payload: bytes):
    """Готовое содержимое JSON (уже сериализованное) — в очередь фоновой записи."""
    with _COND:
        _PENDING[str(Path(path))]=bytes(payload);_next_id(Path(path))
        if _WRITER[0] is None or not _WRITER[0].is_alive():
            _WRITER[0]=threading.Thread(target=_writer,daemon=True,name='json-writer');_WRITER[0].start()
        _COND.notify_all()
