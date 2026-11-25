import asyncio
import ctypes.util

import discord

from config import AUTO_LEAVE_DELAY, VOICE_CONNECT_ATTEMPTS, VOICE_CONNECT_TIMEOUT, VOICE_RETRY_DELAY


def load_opus_library():
    """Mixed audio is PCM, which discord.py encodes with libopus. Finds it where Homebrew puts it on macOS."""
    if discord.opus.is_loaded():
        return
    candidates = [ctypes.util.find_library("opus"), "/opt/homebrew/lib/libopus.dylib", "/usr/local/lib/libopus.dylib"]
    for path in candidates:
        if not path:
            continue
        try:
            discord.opus.load_opus(path)
            return
        except OSError:
            continue
    print("WARNING: libopus not found - install it (macOS: brew install opus). Playback will fail.")


def create_client():
    intents = discord.Intents.default()
    intents.voice_states = True
    return discord.Client(intents=intents)


class VoiceConnection:
    """Joins and leaves the voice channel, and leaves on its own when nobody is listening."""

    def __init__(self, client, playback, auto_leave_delay=AUTO_LEAVE_DELAY):
        self.client = client
        self.playback = playback
        self.auto_leave_delay = auto_leave_delay
        client.event(self.on_voice_state_update)
        client.event(self.on_ready)

    def guilds(self):
        return [{"id": str(g.id), "name": g.name} for g in self.client.guilds]

    def voice_channels(self, guild_id):
        guild = self.client.get_guild(int(guild_id))
        if guild is None:
            return []
        return [
            {"id": str(c.id), "name": c.name}
            for c in guild.channels
            if isinstance(c, discord.VoiceChannel)
        ]

    async def connect_with_retry(self, channel, attempts=VOICE_CONNECT_ATTEMPTS):
        for attempt in range(1, attempts + 1):
            try:
                return await channel.connect(timeout=VOICE_CONNECT_TIMEOUT, reconnect=True, self_deaf=True)
            except Exception as e:
                print(f"Voice connection attempt {attempt}/{attempts} failed: {e!r}")
                if attempt == attempts:
                    raise
                await asyncio.sleep(VOICE_RETRY_DELAY)

    async def join(self, guild_id, channel_id):
        guild = self.client.get_guild(int(guild_id))
        if guild is None:
            return False, "Guild not found"

        channel = guild.get_channel(int(channel_id))
        if channel is None:
            return False, "Channel not found"

        if not isinstance(channel, discord.VoiceChannel):
            return False, "Not a voice channel"

        pb = self.playback
        vc = pb.voice_client
        if vc and vc.is_connected() and vc.channel.id == channel.id:
            return True, "Already in this channel"

        try:
            if vc and vc.is_connected():
                await vc.move_to(channel)
            else:
                pb.voice_client = await self.connect_with_retry(channel)
        except TimeoutError:
            return False, "Timed out connecting to Discord voice server (check firewall/VPN)"
        except Exception as e:
            return False, f"Failed to connect: {e!r}"

        pb.guild_id = guild_id
        pb.channel_id = channel_id
        pb.ensure_mixer(pb.voice_client)
        return True, "Joined channel"

    async def leave(self):
        pb = self.playback
        vc = pb.voice_client
        if vc is None:
            return False
        pb.queue = []
        pb.current_track = None
        pb.is_playing = False
        pb.voice_client = None
        pb.music = None
        pb.mixer = None
        pb.reset_track_clock()
        was_connected = vc.is_connected()
        await vc.disconnect(force=True)
        return was_connected

    @staticmethod
    def has_listeners(channel):
        return any(not member.bot for member in channel.members)

    async def on_voice_state_update(self, member, before, after):
        pb = self.playback
        vc = pb.voice_client
        if member.bot or vc is None or not vc.is_connected():
            return
        if before.channel != vc.channel or self.has_listeners(vc.channel):
            return
        await asyncio.sleep(self.auto_leave_delay)
        if pb.voice_client is vc and vc.is_connected() and not self.has_listeners(vc.channel):
            print("Everyone left the voice channel - leaving.")
            await self.leave()

    async def on_ready(self):
        print(f"Bot logged in as {self.client.user}")
