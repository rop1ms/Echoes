"""Check that batched audio analysis preserves word timing inputs at the boundaries."""

import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import word_sync as ws


def reference(pcm):
    n = (len(pcm) - ws.FFT) // ws.HOP
    x = pcm.astype(np.float32) / 32768.0
    indices = np.arange(ws.FFT)[None, :] + ws.HOP * np.arange(n)[:, None]
    window = np.hanning(ws.FFT).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(x[indices] * window, axis=1))
    freq = np.fft.rfftfreq(ws.FFT, 1.0 / ws.SR)
    mag = np.log1p(spectrum[:, (freq > 250) & (freq < 3500)] * 40.0)
    flux = np.maximum(0.0, np.diff(mag, axis=0, prepend=mag[:1])).sum(axis=1)
    flux = np.convolve(flux, np.ones(3) / 3.0, mode="same")
    loud = np.convolve(mag.mean(axis=1), np.ones(9) / 9.0, mode="same")
    return flux / (np.percentile(flux, 95) + 1e-9), loud


with tempfile.TemporaryFile() as audio:
    assert ws._analyze_pcm(audio) is None
    size = (2 * ws.FRAMES_PER_BATCH + 7) * ws.HOP + ws.FFT
    pcm = np.random.default_rng(15).integers(-32768, 32767, size, dtype="<i2")
    pcm.tofile(audio)
    for actual, expected in zip(ws._analyze_pcm(audio), reference(pcm), strict=True):
        np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-8)

print("Word timing matches the reference across two FFT batch boundaries.")
