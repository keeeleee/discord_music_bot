import sys
import threading
from array import array

import discord

from config import FRAME_BYTES

SILENCE_FRAME = bytes(FRAME_BYTES)


class Channel:
    """One sound inside the mixer: the music track or a soundboard tile."""

    def __init__(self, source, on_end=None, tag=None):
        self.source = source
        self.on_end = on_end  # runs on the bot's event loop when the sound ends by itself
        self.paused = False
        self.tag = tag  # identifies a soundboard tile, so it can be stopped again


def _add_samples(a, b):
    return array("h", [max(-32768, min(32767, x + y)) for x, y in zip(a, b)])


class Mixer(discord.AudioSource):
    """The one audio source given to the voice client: sums all active channels into one stream."""

    def __init__(self, loop):
        self._loop = loop  # where on_end callbacks run: the bot's event loop
        self._lock = threading.Lock()
        self._channels = []

    def add(self, channel):
        with self._lock:
            self._channels.append(channel)

    def remove(self, channel):
        """Stops a channel without calling its on_end."""
        with self._lock:
            if channel in self._channels:
                self._channels.remove(channel)
        channel.source.cleanup()

    def count(self):
        with self._lock:
            return len(self._channels)

    def find(self, tag):
        with self._lock:
            return next((c for c in self._channels if c.tag is not None and c.tag == tag), None)

    def tags(self):
        with self._lock:
            return [c.tag for c in self._channels if c.tag is not None]

    def read(self):
        with self._lock:
            channels = list(self._channels)
        mixed = None
        ended = []
        for channel in channels:
            if channel.paused:
                continue
            data = channel.source.read()
            if len(data) < FRAME_BYTES:
                ended.append(channel)
                continue
            if mixed is None and len(channels) == 1:
                return data  # single sound: pass through untouched
            samples = array("h", data)
            if sys.byteorder == "big":
                samples.byteswap()
            mixed = samples if mixed is None else _add_samples(mixed, samples)
        for channel in ended:
            self._finish(channel)
        if mixed is None:
            return SILENCE_FRAME
        if sys.byteorder == "big":
            mixed.byteswap()
        return mixed.tobytes()

    def _finish(self, channel):
        with self._lock:
            if channel in self._channels:
                self._channels.remove(channel)
        channel.source.cleanup()
        if channel.on_end is not None:
            self._loop.call_soon_threadsafe(channel.on_end)

    def cleanup(self):
        with self._lock:
            channels = list(self._channels)
            self._channels.clear()
        for channel in channels:
            channel.source.cleanup()
