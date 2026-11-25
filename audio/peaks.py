"""Waveform peaks for a stored sound: a few hundred amplitudes, each 0..1, for drawing the bars."""
import array
import os
import shutil
import subprocess

BARS = 160
SAMPLE_RATE = 2000  # plenty for drawing bars, and fast to decode

_cache = {}


def compute_peaks(path, bars=BARS):
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return None
    try:
        raw = subprocess.run(
            [ffmpeg, "-v", "error", "-i", path, "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-"],
            capture_output=True, timeout=60, check=True,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) // 2 * 2])
    if not samples:
        return None
    step = max(1, len(samples) // bars)
    peaks = [max((abs(x) for x in samples[i * step:(i + 1) * step]), default=0) for i in range(bars)]
    top = max(peaks) or 1
    return [round(p / top, 3) for p in peaks]


def waveform(path):
    """Cached per file and modification time, so a sound is decoded only once."""
    try:
        key = (path, os.path.getmtime(path))
    except OSError:
        return None
    if key not in _cache:
        _cache[key] = compute_peaks(path)
    return _cache[key]
