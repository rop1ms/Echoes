"""Close a profile while an external loudness job is in progress."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import loudness


class LoudnessShutdownTests(unittest.TestCase):
    def test_closing_cancels_process_queue_and_callback(self):
        started = threading.Event()
        processes = []
        ready = []
        spawn = subprocess.Popen

        def record_process(*args, **kwargs):
            handle = spawn(*args, **kwargs)
            processes.append(handle)
            started.set()
            return handle

        def measure(path, cancel):
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            loudness._collect_stderr([sys.executable, "-c", "import time; time.sleep(30)"], flags, cancel)
            return -23.0, -6.0

        with tempfile.TemporaryDirectory() as temp, patch.object(loudness.subprocess, "Popen", record_process), \
                patch.object(loudness, "measure", measure):
            cache = Path(temp) / "loudness.json"
            store = loudness.LoudnessStore(cache, on_ready=ready.append)
            self.addCleanup(store.shutdown)
            store.request("running")
            self.assertTrue(started.wait(5))
            store.request("queued")
            worker = store._worker
            store.shutdown()
            store.request("late")
            self.assertFalse(worker.is_alive())
            self.assertIsNotNone(processes[0].poll())
            self.assertEqual(store.pending(), 0)
            self.assertEqual(ready, [])
            self.assertFalse(cache.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
