"""Online tracks start fast (stream_core.StreamResolver), network stubbed out.

- a track found by "artist — title" remembers its page: after a restart (new resolver, same cache file)
  the stream link is served from disk, and once the link expires only yt-dlp runs again — no search;
- a remembered page that disappeared is searched again;
- clicks (urgent) never wait behind prefetches; hover hints keep only the latest track."""
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import stream_core as S  # noqa: E402


class Fake:
    def __init__(self):
        self.finds, self.directs, self.dead = 0, 0, set()

    def find(self, artist, title, duration, prefer=("ytm", "sc")):
        self.finds += 1
        return {"url": f"https://music.youtube.com/watch?v={title}", "score": 0.95, "title": title, "artist": artist}

    def direct(self, page):
        self.directs += 1
        if page in self.dead:
            raise RuntimeError("video unavailable")
        return f"https://cdn.example/{page[-6:]}?expire={int(time.time()) + 3600}", {"duration": 200}


def wait(r, track, urgent=False, hint=False):
    ev, out = threading.Event(), {}
    if hint:
        r.hint(track)
        time.sleep(0.6)
    r.resolve(track, lambda ok, d: (out.update(ok=ok, d=d), ev.set()), urgent=urgent)
    ev.wait(10)
    return out


class StreamCache(unittest.TestCase):
    def setUp(self):
        self.fake = Fake()
        self.file = Path(tempfile.mkdtemp()) / 'stream_cache.json'
        p1 = patch.object(S, 'CACHE_FILE', self.file)
        p2 = patch.object(S.StreamResolver, '_find', staticmethod(self.fake.find))
        p3 = patch.object(S.StreamResolver, '_direct', staticmethod(self.fake.direct))
        for p in (p1, p2, p3):
            p.start()
            self.addCleanup(p.stop)
        self.track = S.make_track({'artist': 'Artist', 'title': 'Song01', 'duration': 200})

    def resolver(self):
        resolver = S.StreamResolver()
        self.addCleanup(resolver.pool.shutdown, cancel_futures=True)
        self.addCleanup(resolver.urgent.shutdown, cancel_futures=True)
        return resolver

    def test_remembered_page_and_link_survive_restart(self):
        r = self.resolver()
        self.assertTrue(wait(r, self.track, urgent=True)['ok'])
        self.assertEqual((self.fake.finds, self.fake.directs), (1, 1))
        r._save(force=True)
        r2 = self.resolver()
        self.assertTrue(r2.cached(self.track['path']), 'link served after restart')
        self.assertTrue(wait(r2, self.track)['ok'])
        self.assertEqual((self.fake.finds, self.fake.directs), (1, 1))
        r3 = self.resolver()
        r3.cache.clear()                                        # link expired
        self.assertTrue(wait(r3, self.track)['ok'])
        self.assertEqual((self.fake.finds, self.fake.directs), (1, 2), 'page remembered: no second search')

    def test_dead_page_is_searched_again(self):
        r = self.resolver()
        wait(r, self.track)
        page = r.pages[self.track['path']]['page']
        self.fake.dead.add(page)
        r.cache.clear()
        orig = self.fake.find
        self.fake.find = lambda a, t, d, prefer=("ytm", "sc"): dict(orig(a, t + 'x', d), url=page + 'new')
        with patch.object(S.StreamResolver, '_find', staticmethod(self.fake.find)):
            out = wait(r, self.track)
        self.assertTrue(out['ok'])
        self.assertEqual(r.pages[self.track['path']]['page'], page + 'new')

    def test_hint_resolves_latest_only(self):
        r = self.resolver()
        a = S.make_track({'artist': 'A', 'title': 'Hover1', 'duration': 100})
        b = S.make_track({'artist': 'A', 'title': 'Hover2', 'duration': 100})
        r.hint(a)
        r.hint(b)                                               # moved on before the delay passed
        end = time.perf_counter() + 2.0
        while not r.cached(b['path']) and time.perf_counter() < end:
            time.sleep(0.05)
        self.assertTrue(r.cached(b['path']))
        self.assertFalse(r.cached(a['path']))

    def test_click_does_not_wait_for_prefetch(self):
        slow = threading.Event()

        def busy(page):
            if 'Slow' in page:
                slow.wait(5)
            return self.fake.direct(page)
        with patch.object(S.StreamResolver, '_direct', staticmethod(busy)):
            r = self.resolver()
            try:
                for i in range(4):                              # prefetch pool (3 workers) fully busy
                    r.resolve(S.make_track({'artist': 'A', 'title': f'Slow{i}', 'duration': 100}))
                t0 = time.perf_counter()
                out = wait(r, self.track, urgent=True)
                took = time.perf_counter() - t0
            finally:
                slow.set()
                # Keep _direct patched until all prefetch workers leave.
                r.pool.shutdown(cancel_futures=True)
        self.assertTrue(out['ok'])
        self.assertLess(took, 2.0)


if __name__ == '__main__':
    unittest.main()
