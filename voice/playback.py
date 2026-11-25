import asyncio
import time
from dataclasses import dataclass, field

from audio.mixer import Channel, Mixer


@dataclass
class PlaybackState:
    """What the bot is playing right now, shared by the player, the voice connection and the routes."""

    voice_client: object = None
    current_track: dict | None = None
    current_category: str | None = None
    queue: list = field(default_factory=list)
    is_playing: bool = False
    loop: bool = False
    shuffle: bool = False
    track_started_at: float | None = None
    paused_at: float | None = None
    paused_total: float = 0.0
    music: Channel | None = None
    mixer: Mixer | None = None
    guild_id: str | None = None
    channel_id: str | None = None

    def ensure_mixer(self, vc):
        """Gives the voice client its mixer, once. Every sound goes through it."""
        if self.mixer is None:
            self.mixer = Mixer(asyncio.get_running_loop())
            vc.play(self.mixer)
        return self.mixer

    def elapsed_seconds(self):
        if self.track_started_at is None:
            return None
        end = self.paused_at or time.monotonic()
        return max(0.0, end - self.track_started_at - self.paused_total)

    def reset_track_clock(self):
        self.track_started_at = None
        self.paused_at = None
        self.paused_total = 0.0
