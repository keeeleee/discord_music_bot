import asyncio
import secrets
import time

from audio import youtube
from audio.mixer import Channel
from audio.sources import build_ffmpeg_before_opts, create_audio_source, create_local_source, probe_duration
from config import MAX_PARALLEL_SOUNDS, PREFETCH_MAX_AGE


class Player:
    """Playback logic: the queue, the music channel, soundboard tiles and seeking."""

    def __init__(self, playback, playlists, sounds, shuffler=None):
        self.playback = playback
        self.playlists = playlists
        self.sounds = sounds
        self.shuffler = shuffler if shuffler is not None else secrets.SystemRandom()
        # YouTube URL -> (resolved_at, audio info). Only touched from the bot's event loop thread.
        self.prefetched = {}
        # Keeps references to fire-and-forget tasks so they are not garbage collected mid-run.
        self.background_tasks = set()

    # ----- queue and music -----

    async def play_category(self, category):
        tracks = self.playlists.tracks(category)
        if not tracks:
            return False, "No tracks in category"

        pb = self.playback
        vc = pb.voice_client
        if vc is None or not vc.is_connected():
            return False, "Bot is not in a voice channel"

        queue = list(tracks)
        if pb.shuffle:
            self.shuffler.shuffle(queue)
        pb.current_category = category
        pb.queue = queue
        pb.current_track = None
        await self.play_next(pb.guild_id)
        return True, "Playing category"

    async def play_single_track(self, track, category=None):
        pb = self.playback
        vc = pb.voice_client
        if vc is None or not vc.is_connected():
            return False, "Bot is not in a voice channel"

        pb.current_category = category
        pb.queue = [track]
        pb.current_track = None
        await self.play_next(pb.guild_id)
        return True, "Playing track"

    async def play_next(self, guild_id):
        pb = self.playback
        vc = pb.voice_client
        if vc is None:
            return

        queue = pb.queue
        if pb.loop and pb.current_track:
            track = dict(pb.current_track)
        elif queue:
            track = queue.pop(0)
            pb.current_track = track
        else:
            old = pb.music
            if old is not None:
                pb.ensure_mixer(vc).remove(old)
            pb.music = None
            pb.is_playing = False
            pb.current_track = None
            pb.reset_track_clock()
            return

        try:
            info = None if track.get("file") else self.take_prefetched(track["url"])
            if info is None:
                info = await self.resolve_track(track)
            track["title"] = info["title"]
            track["duration"] = info["duration"]
            pb.current_track = track

            self.start_music(pb.ensure_mixer(vc), info)
            self.run_in_background(self.prefetch_next())
        except Exception as e:
            print(f"Error playing track: {e!r}")
            pb.is_playing = False

    def start_music(self, mixer, info, offset=0.0, paused=False):
        """Starts the current track's music channel at `offset` seconds, replacing any music playing now."""
        pb = self.playback
        old = pb.music
        if old is not None:
            mixer.remove(old)

        before_opts = "-nostdin" if info.get("local") else build_ffmpeg_before_opts(info["headers"])
        if offset:
            before_opts = f"{before_opts} -ss {offset:.3f}"
        source = create_audio_source(info["url"], before_opts)
        guild_id = pb.guild_id

        def on_end():
            # Only the channel that is still the current music may move the queue on.
            if pb.music is channel:
                pb.music = None
                self.schedule_play_next(guild_id)

        channel = Channel(source, on_end)
        channel.paused = paused
        pb.music = channel
        mixer.add(channel)

        now = time.monotonic()
        pb.track_started_at = now - offset
        pb.paused_total = 0.0
        pb.paused_at = now if paused else None
        pb.is_playing = not paused

    def pause_music(self):
        pb = self.playback
        music = pb.music
        if music is None or music.paused:
            return False
        music.paused = True
        pb.is_playing = False
        pb.paused_at = time.monotonic()
        return True

    def resume_music(self):
        pb = self.playback
        music = pb.music
        if music is None or not music.paused:
            return False
        music.paused = False
        pb.is_playing = True
        if pb.paused_at is not None:
            pb.paused_total += time.monotonic() - pb.paused_at
            pb.paused_at = None
        return True

    def stop_music(self):
        pb = self.playback
        music = pb.music
        if music is None:
            return False
        pb.queue = []
        pb.current_track = None
        pb.music = None
        pb.ensure_mixer(pb.voice_client).remove(music)
        pb.is_playing = False
        pb.reset_track_clock()
        return True

    def skip_track(self):
        pb = self.playback
        music = pb.music
        if music is None:
            return False
        pb.music = None
        pb.ensure_mixer(pb.voice_client).remove(music)
        self.schedule_play_next(pb.guild_id)
        return True

    async def seek_music(self, position=None, offset=None):
        """Moves the current track to `position` seconds, or by `offset` seconds (negative = back).

        Restarts the stream with ffmpeg's input seek (-ss), so it needs a fresh stream URL.
        Returns False if nothing is playing or the track changed while resolving.
        """
        pb = self.playback
        vc = pb.voice_client
        track = pb.current_track
        music = pb.music
        if vc is None or track is None or music is None:
            return False

        current = pb.elapsed_seconds() or 0.0
        target = max(0.0, (current + offset) if offset is not None else position)
        duration = track.get("duration")
        if duration is not None and target >= duration:
            return self.skip_track()

        try:
            info = await self.resolve_track(track)
        except Exception as e:
            print(f"Seek failed for {track.get('url') or track.get('file')}: {e!r}")
            return False

        # Nothing changed while we were resolving the stream?
        if pb.music is not music or pb.current_track is not track:
            return False

        self.start_music(pb.ensure_mixer(vc), info, offset=target, paused=music.paused)
        return True

    def set_shuffle(self, enabled):
        pb = self.playback
        pb.shuffle = enabled
        if enabled:
            self.shuffler.shuffle(pb.queue)
        return enabled

    def set_loop(self, enabled):
        self.playback.loop = enabled
        return enabled

    # ----- soundboard -----

    @staticmethod
    def tile_key(tile):
        """Identifies a tile by its stored file or link."""
        return tile.get("file") or tile.get("url")

    def playing_sound_tags(self):
        mixer = self.playback.mixer
        return mixer.tags() if mixer is not None else []

    async def play_sound(self, tile):
        """Plays a soundboard tile next to the music and other tiles (it does not touch the queue).

        A tile that is already playing is stopped instead.
        """
        pb = self.playback
        vc = pb.voice_client
        if vc is None or not vc.is_connected():
            return False, "Bot is not in a voice channel"

        mixer = pb.ensure_mixer(vc)
        key = self.tile_key(tile)
        running = mixer.find(key)
        if running is not None:
            mixer.remove(running)
            return True, "Sound stopped"
        if mixer.count() >= MAX_PARALLEL_SOUNDS:
            return False, f"Already {MAX_PARALLEL_SOUNDS} sounds playing"

        if tile.get("file"):
            source = create_local_source(self.sounds.path(tile["file"]))
        else:
            info = await asyncio.get_running_loop().run_in_executor(None, youtube.get_audio_url, tile["url"])
            source = create_audio_source(info["url"], build_ffmpeg_before_opts(info["headers"]))
        mixer.add(Channel(source, tag=key))
        return True, "Playing sound"

    # ----- resolving and prefetching -----

    def run_in_background(self, coro):
        task = asyncio.create_task(coro)
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)

    def schedule_play_next(self, guild_id):
        """Moves the queue on from a callback running on the bot's event loop."""
        coro = self.play_next(guild_id)
        try:
            self.run_in_background(coro)
        except RuntimeError:  # no running loop (only outside the bot, e.g. in tests)
            coro.close()

    def upcoming_track(self):
        pb = self.playback
        if pb.loop and pb.current_track:
            return pb.current_track
        return pb.queue[0] if pb.queue else None

    def take_prefetched(self, url):
        cached = self.prefetched.pop(url, None)
        if cached and time.monotonic() - cached[0] < PREFETCH_MAX_AGE:
            return cached[1]
        return None

    async def resolve_track(self, track):
        """Returns what the player needs for a playlist entry: a stored file, or a YouTube link resolved to a stream."""
        if track.get("file"):
            path = self.sounds.path(track["file"])
            duration = await asyncio.get_running_loop().run_in_executor(None, probe_duration, path)
            return {"url": path, "title": track.get("title") or track["file"],
                    "acodec": "", "headers": {}, "duration": duration, "local": True}
        return await asyncio.get_running_loop().run_in_executor(None, youtube.get_audio_url, track["url"])

    async def prefetch_next(self):
        """Resolves the next track's stream while the current one plays, to shorten the gap."""
        track = self.upcoming_track()
        # Stored files need no preparation, and only YouTube entries have a link to prefetch.
        if track is None or track.get("file") or track["url"] in self.prefetched:
            return
        try:
            info = await asyncio.get_running_loop().run_in_executor(None, youtube.get_audio_url, track["url"])
        except Exception as e:
            print(f"Prefetch failed for {track['url']}: {e!r}")
            return
        self.prefetched.clear()
        self.prefetched[track["url"]] = (time.monotonic(), info)
