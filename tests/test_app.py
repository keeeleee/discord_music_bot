import asyncio
import shlex
import threading
import time
import types

import discord
import pytest

from app import create_app
from app.bridge import LoopBridge
from app.container import build_container
from app.routes import soundboard as soundboard_routes
from audio import youtube
from audio.mixer import SILENCE_FRAME, Channel, Mixer
from audio.sources import build_ffmpeg_before_opts, create_audio_source
from config import (
    FRAME_BYTES, MAX_PLAYLIST_TRACKS, MAX_TITLE_LENGTH, PREFETCH_MAX_AGE, STATUS_QUEUE_PREVIEW,
    VOICE_CONNECT_ATTEMPTS, VOICE_CONNECT_TIMEOUT, VOICE_RETRY_DELAY,
)
from storage.json_store import DEFAULT_DATA


REAL_FETCH_TRACKS = youtube.fetch_tracks
# Deterministic stand-in for the random shuffler: reverses the order instead.
REVERSING_SHUFFLER = types.SimpleNamespace(shuffle=lambda items: items.reverse())


def audio_info(title="Title", duration=120):
    return {"url": "https://audio", "title": title, "acodec": "opus", "headers": {}, "duration": duration}


class FakeVoiceClient:
    def __init__(self, playing=False, paused=False):
        self.playing = playing
        self.paused = paused
        self.connected = True
        self.source = None
        self.after = None
        self.stopped = False
        self.channel = types.SimpleNamespace(id=2, name="sesja", members=[])

    def is_connected(self):
        return self.connected

    def is_playing(self):
        return self.playing

    def is_paused(self):
        return self.paused

    def play(self, source, after=None):
        self.source = source
        self.after = after
        self.playing = True

    def stop(self):
        self.stopped = True
        self.playing = False
        self.paused = False

    def pause(self):
        self.playing = False
        self.paused = True

    def resume(self):
        self.playing = True
        self.paused = False

    async def disconnect(self, force=False):
        self.connected = False


class FakeOpusSource(discord.AudioSource):
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def read(self):
        return b""

    def is_opus(self):
        return True


@pytest.fixture(autouse=True)
def container(tmp_path, monkeypatch):
    built = build_container(data_file=str(tmp_path / "playlists.json"), sounds_dir=str(tmp_path / "sounds"))
    monkeypatch.setattr(built.bridge, "run_async", lambda coro, timeout=None: asyncio.run(coro))
    monkeypatch.setattr(built.bridge, "call", lambda func, *args: func(*args))
    # Never reach YouTube from tests; the title is derived from the URL instead.
    monkeypatch.setattr(youtube, "fetch_tracks", lambda url: [{"url": url, "title": "YT " + url[-4:]}])
    return built


@pytest.fixture
def client(container):
    app = create_app(container)
    app.config["TESTING"] = True
    return app.test_client()


YT_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_index_renders(client):
    assert client.get("/").status_code == 200


def test_default_categories_created(client):
    r = client.get("/api/categories")
    assert set(r.get_json()) == {"combat_music", "ambient_music", "storm_music"}


def test_default_data_not_mutated(client):
    client.post("/api/categories", json={"name": "boss fight"})
    assert "boss_fight" not in DEFAULT_DATA["categories"]


def test_add_category_normalizes_name(client):
    r = client.post("/api/categories", json={"name": "Boss Fight"})
    assert r.get_json()["ok"] is True
    assert "boss_fight" in client.get("/api/categories").get_json()


@pytest.mark.parametrize("name", [
    "<img src=x onerror=alert(1)>",
    "a'); alert(1); //",
    "../etc",
    "x" * 51,
])
def test_add_category_rejects_unsafe_names(client, name):
    r = client.post("/api/categories", json={"name": name})
    assert r.status_code == 400


def test_duplicate_category(client):
    r = client.post("/api/categories", json={"name": "combat_music"})
    assert r.get_json()["ok"] is False


def test_delete_category(client):
    assert client.delete("/api/categories/storm_music", json={}).get_json()["ok"] is True
    assert client.delete("/api/categories/storm_music", json={}).get_json()["ok"] is False


@pytest.mark.parametrize("body", ["not json", [1, 2], {}])
def test_malformed_body_returns_400_not_500(client, body):
    for path in ["/api/categories", "/api/join", "/api/play/category", "/api/play/track",
                 "/api/categories/combat_music/tracks"]:
        if isinstance(body, str):
            r = client.post(path, data=body, content_type="application/json")
        else:
            r = client.post(path, json=body)
        assert r.status_code == 400, path


@pytest.mark.parametrize("method,path", [
    ("post", "/api/stop"),
    ("post", "/api/leave"),
    ("post", "/api/skip"),
    ("post", "/api/pause"),
    ("post", "/api/seek"),
    ("post", "/api/loop"),
    ("post", "/api/categories"),
    ("delete", "/api/categories/combat_music"),
])
@pytest.mark.parametrize("content_type", [None, "text/plain", "application/x-www-form-urlencoded", "multipart/form-data"])
def test_state_changes_require_json_csrf(client, method, path, content_type):
    kwargs = {"data": "name=x"} if content_type else {}
    if content_type:
        kwargs["content_type"] = content_type
    r = getattr(client, method)(path, **kwargs)
    assert r.status_code == 415
    assert "combat_music" in client.get("/api/categories").get_json()


@pytest.mark.parametrize("method", ["put", "patch"])
def test_get_only_routes_reject_other_methods(client, method):
    assert getattr(client, method)("/api/status", json={}).status_code == 405


def test_add_and_remove_track(client):
    r = client.post("/api/categories/combat_music/tracks", json={"url": YT_URL, "title": "Song"})
    assert r.get_json()["ok"] is True
    tracks = client.get("/api/categories").get_json()["combat_music"]
    assert tracks == [{"url": YT_URL, "title": "Song"}]
    assert client.delete("/api/categories/combat_music/tracks/0", json={}).get_json()["ok"] is True
    assert client.delete("/api/categories/combat_music/tracks/0", json={}).get_json()["ok"] is False


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "http://127.0.0.1:8080/admin",
    "http://169.254.169.254/latest/meta-data/",
    "https://youtube.com.evil.example/watch?v=x",
    "javascript:alert(1)",
    "https://www.youtube.com/watch?v=" + "a" * 600,
])
def test_add_track_rejects_non_youtube_urls(client, url):
    r = client.post("/api/categories/combat_music/tracks", json={"url": url})
    assert r.status_code == 400


def test_add_track_accepts_youtu_be(client):
    r = client.post("/api/categories/combat_music/tracks", json={"url": "https://youtu.be/dQw4w9WgXcQ"})
    assert r.get_json()["ok"] is True


def test_play_track_requires_connection(client):
    client.post("/api/categories/combat_music/tracks", json={"url": YT_URL})
    r = client.post("/api/play/track", json={"category": "combat_music", "index": 0})
    assert r.get_json() == {"ok": False, "message": "Bot is not in a voice channel"}


def test_play_track_out_of_range(client):
    r = client.post("/api/play/track", json={"category": "combat_music", "index": 5})
    assert r.status_code == 404


def test_play_track_rejects_arbitrary_track_payload(client):
    r = client.post("/api/play/track", json={"track": {"url": "file:///etc/passwd"}})
    assert r.status_code == 400


def test_play_track_starts_playback(client, monkeypatch, container):
    monkeypatch.setattr(youtube, "get_audio_url", lambda url: audio_info())
    monkeypatch.setattr(discord, "FFmpegPCMAudio", FakeOpusSource)
    vc = FakeVoiceClient()
    container.playback.voice_client = vc
    client.post("/api/categories/combat_music/tracks", json={"url": YT_URL})

    r = client.post("/api/play/track", json={"category": "combat_music", "index": 0})

    assert r.get_json()["ok"] is True
    assert isinstance(vc.source, Mixer)
    assert isinstance(container.playback.music.source, FakeOpusSource)
    assert container.playback.current_track["title"] == "Title"
    assert container.playback.is_playing is True


def test_audio_source_is_pcm_for_mixing(monkeypatch):
    monkeypatch.setattr(discord, "FFmpegPCMAudio", FakeOpusSource)
    source = create_audio_source("https://audio", "-ss 5")
    assert source.kwargs["before_options"] == "-ss 5"


def test_stop_works_while_paused(client, monkeypatch, container):
    connected_client_with_tracks(client, monkeypatch, count=2)
    client.post("/api/play/category", json={"category": "combat_music"})
    client.post("/api/pause", json={})
    assert client.post("/api/stop", json={}).get_json()["ok"] is True
    assert container.playback.music is None
    assert container.playback.queue == []


def test_pause_resume_skip(client, monkeypatch, container):
    connected_client_with_tracks(client, monkeypatch, count=2)
    client.post("/api/play/category", json={"category": "combat_music"})
    assert client.post("/api/pause", json={}).get_json()["ok"] is True
    assert client.get("/api/status").get_json()["is_paused"] is True
    assert client.post("/api/resume", json={}).get_json()["ok"] is True
    assert client.get("/api/status").get_json()["is_paused"] is False
    assert client.post("/api/skip", json={}).get_json()["ok"] is True
    assert container.playback.music is None


def test_leave_resets_state(client, container):
    container.playback.voice_client = FakeVoiceClient(playing=True)
    container.playback.queue = [{"url": YT_URL}]
    assert client.post("/api/leave", json={}).get_json()["ok"] is True
    assert container.playback.voice_client is None
    assert container.playback.queue == []
    assert client.post("/api/leave", json={}).get_json()["ok"] is False


def test_status_when_disconnected(client):
    s = client.get("/api/status").get_json()
    assert s["connected"] is False
    assert s["is_paused"] is False


def test_loop_toggle(client):
    assert client.post("/api/loop", json={"loop": True}).get_json()["loop"] is True


@pytest.mark.parametrize("payload", [
    {"guild_id": "abc", "channel_id": "1"},
    {"guild_id": "1"},
    {"guild_id": "1; drop", "channel_id": "2"},
])
def test_join_validates_ids(client, payload):
    assert client.post("/api/join", json=payload).status_code == 400


def test_voice_channels_invalid_guild_id(client):
    r = client.get("/api/guilds/not-a-number/channels")
    assert r.status_code == 200
    assert r.get_json() == []


def test_no_cors_headers(client):
    r = client.get("/api/status", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in r.headers


def test_trusted_hosts_blocks_foreign_host(client, monkeypatch):
    monkeypatch.setitem(client.application.config, "TRUSTED_HOSTS", ["localhost", "127.0.0.1"])
    assert client.get("/api/status", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/api/status", headers={"Host": "localhost:5000"}).status_code == 200


def test_message_content_intent_disabled(container):
    assert container.client.intents.message_content is False
    assert container.client.intents.voice_states is True


def test_ffmpeg_headers_are_quoted():
    opts = build_ffmpeg_before_opts({"User-Agent": "x'; rm -rf / #"})
    parts = shlex.split(opts)
    assert parts[-2] == "-headers"
    assert parts[-1] == "User-Agent: x'; rm -rf / #\r\n"


def test_join_already_in_channel(client, monkeypatch, container):
    channel = discord.VoiceChannel.__new__(discord.VoiceChannel)
    channel.id = 2
    guild = type("Guild", (), {"get_channel": lambda self, cid: channel})()
    monkeypatch.setattr(container.client, "get_guild", lambda gid: guild)
    vc = FakeVoiceClient()
    vc.channel = channel
    container.playback.voice_client = vc
    r = client.post("/api/join", json={"guild_id": "1", "channel_id": "2"})
    assert r.get_json() == {"ok": True, "message": "Already in this channel"}


def test_connect_with_retry_retries_then_raises(monkeypatch, container):
    calls = []

    class FailingChannel:
        async def connect(self, **kwargs):
            calls.append(kwargs)
            raise RuntimeError("boom")

    async def no_sleep(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    coro = container.voice.connect_with_retry(FailingChannel())
    with pytest.raises(RuntimeError):
        asyncio.run(coro)
    assert len(calls) == VOICE_CONNECT_ATTEMPTS


def test_join_timeout_covers_all_connection_attempts(client, monkeypatch, container):
    seen = {}

    def fake_run_async(coro, timeout=None):
        coro.close()
        seen["timeout"] = timeout
        return True, "Joined channel"

    monkeypatch.setattr(container.bridge, "run_async", fake_run_async)
    client.post("/api/join", json={"guild_id": "1", "channel_id": "2"})
    worst_case = VOICE_CONNECT_ATTEMPTS * (
        VOICE_CONNECT_TIMEOUT + VOICE_RETRY_DELAY
    )
    assert seen["timeout"] > worst_case


def test_call_in_loop_runs_on_bot_loop(container, monkeypatch):
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(container.client, "loop", loop)
    bridge = LoopBridge(container.client)
    try:
        assert bridge.call(lambda x: (x, threading.current_thread() is thread), 5) == (5, True)
        with pytest.raises(ValueError):
            bridge.call(int, "abc")
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join()
        loop.close()


def test_join_timeout_returns_readable_message(client, monkeypatch, container):
    channel = discord.VoiceChannel.__new__(discord.VoiceChannel)
    channel.id = 2
    guild = type("Guild", (), {"get_channel": lambda self, cid: channel})()
    monkeypatch.setattr(container.client, "get_guild", lambda gid: guild)

    async def timeout(_channel):
        raise TimeoutError

    monkeypatch.setattr(container.voice, "connect_with_retry", timeout)
    r = client.post("/api/join", json={"guild_id": "1", "channel_id": "2"})
    assert r.get_json()["ok"] is False
    assert "Timed out" in r.get_json()["message"]


@pytest.fixture
def sample_audio(tmp_path):
    import shutil
    import subprocess
    import static_ffmpeg
    static_ffmpeg.add_paths()
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("ffmpeg not available")
    path = tmp_path / "tone.webm"
    subprocess.run(
        [ffmpeg, "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-c:a", "libopus", str(path)],
        check=True,
    )
    return str(path)


def test_audio_source_produces_pcm_frames_with_real_ffmpeg(sample_audio):
    source = create_audio_source(sample_audio, "-nostdin")
    try:
        frames = [source.read() for _ in range(5)]
        assert not source.is_opus()
        assert all(len(frame) == FRAME_BYTES for frame in frames)
    finally:
        source.cleanup()


# ---------- Adding tracks: titles and playlists ----------

PLAYLIST_URL = "https://www.youtube.com/playlist?list=PL123"


def test_add_track_without_title_uses_youtube_title(client):
    client.post("/api/categories/combat_music/tracks", json={"url": YT_URL})
    tracks = client.get("/api/categories").get_json()["combat_music"]
    assert tracks == [{"url": YT_URL, "title": "YT " + YT_URL[-4:]}]


def test_add_track_with_title_skips_youtube_lookup(client, monkeypatch):
    def fail(url):
        raise AssertionError("should not query YouTube")

    monkeypatch.setattr(youtube, "fetch_tracks", fail)
    r = client.post("/api/categories/combat_music/tracks", json={"url": YT_URL, "title": "Mine"})
    assert r.get_json() == {"ok": True, "added": 1}


def test_add_playlist_adds_all_videos(client, monkeypatch):
    videos = [{"url": f"https://www.youtube.com/watch?v=v{i}", "title": f"Song {i}"} for i in range(3)]
    monkeypatch.setattr(youtube, "fetch_tracks", lambda url: [dict(v) for v in videos])
    r = client.post("/api/categories/ambient_music/tracks", json={"url": PLAYLIST_URL, "title": "ignored"})
    assert r.get_json() == {"ok": True, "added": 3}
    assert client.get("/api/categories").get_json()["ambient_music"] == videos


def test_youtube_failure_falls_back_to_url_for_single_video(client, monkeypatch):
    def offline(url):
        raise RuntimeError("offline")

    monkeypatch.setattr(youtube, "fetch_tracks", offline)
    assert client.post("/api/categories/combat_music/tracks", json={"url": YT_URL}).get_json()["ok"] is True
    assert client.get("/api/categories").get_json()["combat_music"][0]["title"] == YT_URL


def test_youtube_failure_for_playlist_is_reported(client, monkeypatch):
    def offline(url):
        raise RuntimeError("offline")

    monkeypatch.setattr(youtube, "fetch_tracks", offline)
    r = client.post("/api/categories/combat_music/tracks", json={"url": PLAYLIST_URL})
    assert r.status_code == 502
    assert client.get("/api/categories").get_json()["combat_music"] == []


def test_empty_playlist_is_rejected(client, monkeypatch):
    monkeypatch.setattr(youtube, "fetch_tracks", lambda url: [])
    assert client.post("/api/categories/combat_music/tracks", json={"url": PLAYLIST_URL}).status_code == 400


def test_fetched_titles_are_truncated(client, monkeypatch):
    monkeypatch.setattr(youtube, "fetch_tracks", lambda url: [{"url": url, "title": "x" * 500}])
    client.post("/api/categories/combat_music/tracks", json={"url": YT_URL})
    title = client.get("/api/categories").get_json()["combat_music"][0]["title"]
    assert len(title) == MAX_TITLE_LENGTH


def install_fake_youtube_dl(monkeypatch, info):
    """Replaces yt_dlp.YoutubeDL for one test; returns the options it was created with."""
    used_options = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            used_options.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download):
            return info

    monkeypatch.setattr(youtube.yt_dlp, "YoutubeDL", FakeYoutubeDL)
    return used_options


def test_fetch_tracks_reads_playlist_entries(monkeypatch):
    options = install_fake_youtube_dl(monkeypatch, {"entries": iter([
        {"id": "a1", "title": "First"},
        {"id": "b2", "title": "[Private video]"},
        None,
        {"id": "c3", "title": None},
    ])})
    tracks = REAL_FETCH_TRACKS(PLAYLIST_URL)
    assert tracks == [
        {"url": "https://www.youtube.com/watch?v=a1", "title": "First"},
        {"url": "https://www.youtube.com/watch?v=c3", "title": "c3"},
    ]
    assert options["noplaylist"] is False


def test_fetch_tracks_limits_playlist_size(monkeypatch):
    install_fake_youtube_dl(monkeypatch, {"entries": ({"id": f"v{i}", "title": str(i)} for i in range(1000))})
    assert len(REAL_FETCH_TRACKS(PLAYLIST_URL)) == MAX_PLAYLIST_TRACKS


def test_fetch_tracks_single_video_ignores_playlist_param(monkeypatch):
    options = install_fake_youtube_dl(monkeypatch, {"title": "One video"})
    url = YT_URL + "&list=PL123"
    assert REAL_FETCH_TRACKS(url) == [{"url": url, "title": "One video"}]
    assert options["noplaylist"] is True


# ---------- Shuffle, queue and status ----------

def connected_client_with_tracks(client, monkeypatch, count=5):
    container = client.application.extensions["container"]
    monkeypatch.setattr(youtube, "get_audio_url", lambda url: audio_info(title=url[-2:]))
    monkeypatch.setattr(discord, "FFmpegPCMAudio", FakeOpusSource)
    for i in range(count):
        client.post("/api/categories/combat_music/tracks", json={"url": f"{YT_URL[:-2]}{i:02d}", "title": f"T{i}"})
    vc = FakeVoiceClient()
    container.playback.voice_client = vc
    return vc


def test_status_shows_queue_and_channel(client, monkeypatch):
    connected_client_with_tracks(client, monkeypatch, count=3)
    client.post("/api/play/category", json={"category": "combat_music"})
    s = client.get("/api/status").get_json()
    assert s["channel_name"] == "sesja"
    assert s["current_track"]["duration"] == 120
    assert s["current_category"] == "combat_music"
    assert [t["title"] for t in s["queue"]] == ["T1", "T2"]
    assert s["queue_length"] == 2
    assert s["shuffle"] is False


def test_status_queue_preview_is_limited(client, container):
    container.playback.queue = [{"url": f"{YT_URL}{i}"} for i in range(50)]
    s = client.get("/api/status").get_json()
    assert len(s["queue"]) == STATUS_QUEUE_PREVIEW
    assert s["queue_length"] == 50


def test_play_category_with_shuffle_randomizes_order(client, monkeypatch, container):
    connected_client_with_tracks(client, monkeypatch, count=8)
    monkeypatch.setattr(container.player, "shuffler", REVERSING_SHUFFLER)
    client.post("/api/shuffle", json={"shuffle": True})
    client.post("/api/play/category", json={"category": "combat_music"})
    played = [container.playback.current_track["url"]] + [t["url"] for t in container.playback.queue]
    original = [t["url"] for t in client.get("/api/categories").get_json()["combat_music"]]
    assert sorted(played) == sorted(original)
    assert played != original


def test_enabling_shuffle_reshuffles_remaining_queue(client, monkeypatch, container):
    queue = [{"url": f"{YT_URL}{i}"} for i in range(10)]
    container.playback.queue = list(queue)
    monkeypatch.setattr(container.player, "shuffler", REVERSING_SHUFFLER)
    r = client.post("/api/shuffle", json={"shuffle": True})
    assert r.get_json() == {"ok": True, "shuffle": True}
    assert container.playback.queue != queue
    assert sorted(t["url"] for t in container.playback.queue) == sorted(t["url"] for t in queue)


def test_play_single_track_marks_category(client, monkeypatch, container):
    connected_client_with_tracks(client, monkeypatch, count=2)
    client.post("/api/play/track", json={"category": "combat_music", "index": 1})
    assert container.playback.current_category == "combat_music"
    assert container.playback.current_track["url"].endswith("01")


def test_elapsed_time_excludes_pauses(client, monkeypatch, container):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    connected_client_with_tracks(client, monkeypatch, count=1)
    client.post("/api/play/category", json={"category": "combat_music"})
    now[0] += 30
    client.post("/api/pause", json={})
    now[0] += 100
    assert client.get("/api/status").get_json()["elapsed"] == 30
    client.post("/api/resume", json={})
    now[0] += 5
    assert client.get("/api/status").get_json()["elapsed"] == 35
    client.post("/api/stop", json={})
    assert container.playback.music is None
    assert client.get("/api/status").get_json()["elapsed"] is None


# ---------- Prefetching the next track ----------

def test_next_track_is_prefetched_and_reused(client, monkeypatch, container):
    calls = []

    def resolve(url):
        calls.append(url)
        return audio_info(title="Resolved " + url[-2:])

    connected_client_with_tracks(client, monkeypatch, count=2)
    monkeypatch.setattr(youtube, "get_audio_url", resolve)

    async def scenario():
        await container.player.play_category("combat_music")
        await asyncio.gather(*container.player.background_tasks)
        assert calls == [f"{YT_URL[:-2]}00", f"{YT_URL[:-2]}01"]
        await container.player.play_next(None)
        assert len(calls) == 2, "the prefetched result should be used instead of resolving again"
        assert container.playback.current_track["title"] == "Resolved 01"

    asyncio.run(scenario())


def test_stale_prefetch_is_ignored(monkeypatch, container):
    now = [5000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    monkeypatch.setitem(container.player.prefetched, "u", (now[0], audio_info()))
    now[0] += PREFETCH_MAX_AGE + 1
    assert container.player.take_prefetched("u") is None


def test_failed_prefetch_does_not_break_playback(monkeypatch, container):
    def broken(url):
        raise RuntimeError("yt error")

    container.playback.queue = [{"url": YT_URL}]
    monkeypatch.setattr(youtube, "get_audio_url", broken)
    asyncio.run(container.player.prefetch_next())
    assert container.player.prefetched == {}


# ---------- Auto-leave ----------

def member(is_bot=False):
    return types.SimpleNamespace(bot=is_bot)


@pytest.mark.parametrize("remaining,should_leave", [([], True), ([member(is_bot=True)], True), ([member()], False)])
def test_auto_leave_when_channel_empties(monkeypatch, remaining, should_leave, container):
    monkeypatch.setattr(container.voice, "auto_leave_delay", 0)
    vc = FakeVoiceClient(playing=True)
    vc.channel.members = remaining
    container.playback.voice_client = vc
    before = types.SimpleNamespace(channel=vc.channel)
    after = types.SimpleNamespace(channel=None)
    asyncio.run(container.voice.on_voice_state_update(member(), before, after))
    assert (container.playback.voice_client is None) is should_leave


def test_auto_leave_ignores_other_channels(monkeypatch, container):
    monkeypatch.setattr(container.voice, "auto_leave_delay", 0)
    vc = FakeVoiceClient()
    container.playback.voice_client = vc
    other = types.SimpleNamespace(channel=types.SimpleNamespace(id=99, members=[]))
    asyncio.run(container.voice.on_voice_state_update(member(), other, types.SimpleNamespace(channel=None)))
    assert container.playback.voice_client is vc


def test_auto_leave_cancelled_when_someone_returns(monkeypatch, container):
    vc = FakeVoiceClient()
    container.playback.voice_client = vc
    before = types.SimpleNamespace(channel=vc.channel)

    async def someone_returns(_delay):
        vc.channel.members = [member()]

    monkeypatch.setattr(asyncio, "sleep", someone_returns)
    asyncio.run(container.voice.on_voice_state_update(member(), before, types.SimpleNamespace(channel=None)))
    assert container.playback.voice_client is vc


@pytest.mark.parametrize("body", [{}, {"position": 5, "offset": 5}, {"position": "5"}, {"offset": True}, {"offset": None}])
def test_seek_rejects_invalid_body(client, body):
    r = client.post("/api/seek", json=body)
    assert r.status_code == 400


def test_seek_without_playback_returns_false(client, monkeypatch):
    connected_client_with_tracks(client, monkeypatch, count=1)
    assert client.post("/api/seek", json={"position": 5}).get_json() == {"ok": False}


def test_seek_restarts_stream_at_position(client, monkeypatch, container):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    connected_client_with_tracks(client, monkeypatch, count=2)
    client.post("/api/play/category", json={"category": "combat_music"})
    now[0] += 10
    assert client.post("/api/seek", json={"position": 42.5}).get_json() == {"ok": True}
    assert "-ss 42.500" in container.playback.music.source.kwargs["before_options"]
    assert client.get("/api/status").get_json()["elapsed"] == 42.5
    now[0] += 3
    assert client.get("/api/status").get_json()["elapsed"] == 45.5
    assert client.get("/api/status").get_json()["queue_length"] == 1


def test_seek_offset_is_relative_and_clamped_to_start(client, monkeypatch, container):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    connected_client_with_tracks(client, monkeypatch, count=1)
    client.post("/api/play/category", json={"category": "combat_music"})
    now[0] += 20
    client.post("/api/seek", json={"offset": 10})
    assert client.get("/api/status").get_json()["elapsed"] == 30
    assert "-ss 30.000" in container.playback.music.source.kwargs["before_options"]
    client.post("/api/seek", json={"offset": -100})
    assert client.get("/api/status").get_json()["elapsed"] == 0
    assert "-ss" not in container.playback.music.source.kwargs["before_options"]  # start needs no seek


def test_seek_past_end_skips_track(client, monkeypatch, container):
    connected_client_with_tracks(client, monkeypatch, count=1)
    client.post("/api/play/category", json={"category": "combat_music"})
    assert client.post("/api/seek", json={"position": 500}).get_json() == {"ok": True}
    assert container.playback.music is None


def test_seek_keeps_pause_state(client, monkeypatch, container):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    connected_client_with_tracks(client, monkeypatch, count=1)
    client.post("/api/play/category", json={"category": "combat_music"})
    client.post("/api/pause", json={})
    client.post("/api/seek", json={"position": 15})
    assert container.playback.music.paused
    now[0] += 100
    assert client.get("/api/status").get_json()["elapsed"] == 15
    client.post("/api/resume", json={})
    now[0] += 5
    assert client.get("/api/status").get_json()["elapsed"] == 20


def test_old_source_ending_after_seek_does_not_advance_queue(client, monkeypatch, container):
    connected_client_with_tracks(client, monkeypatch, count=3)
    client.post("/api/play/category", json={"category": "combat_music"})
    old_music = container.playback.music
    client.post("/api/seek", json={"position": 5})
    before = list(container.playback.queue)
    old_music.on_end()  # the replaced channel reports its end
    assert container.playback.queue == before
    assert container.playback.music is not old_music



def test_deck_add_list_delete(client):
    assert client.get("/api/deck").get_json() == []
    r = client.post("/api/deck", json={"url": YT_URL, "label": "  Gong  "})
    assert r.get_json() == {"ok": True}
    assert client.get("/api/deck").get_json() == [{"url": YT_URL, "title": "Gong"}]
    assert client.delete("/api/deck/0", json={}).get_json() == {"ok": True}
    assert client.delete("/api/deck/0", json={}).get_json() == {"ok": False}
    assert client.get("/api/deck").get_json() == []


def test_deck_title_comes_from_youtube_without_label(client):
    client.post("/api/deck", json={"url": YT_URL})
    assert client.get("/api/deck").get_json()[0]["title"] == "YT " + YT_URL[-4:]


@pytest.mark.parametrize("body,message", [
    ({"url": ""}, "url required"),
    ({"url": "https://example.com/x.mp3"}, "Only YouTube links are allowed"),
    ({"url": "https://www.youtube.com/playlist?list=PL1"}, "A tile needs a single video link, not a playlist"),
    ({"url": 5}, "url and label must be strings"),
])
def test_deck_rejects_bad_input(client, body, message):
    r = client.post("/api/deck", json=body)
    assert r.status_code == 400
    assert r.get_json()["message"] == message
    assert client.get("/api/deck").get_json() == []


def test_deck_full_is_rejected(client, monkeypatch):
    monkeypatch.setattr(soundboard_routes, "MAX_DECK_TILES", 2)
    for _ in range(2):
        client.post("/api/deck", json={"url": YT_URL, "label": "x"})
    r = client.post("/api/deck", json={"url": YT_URL, "label": "x"})
    assert r.status_code == 400
    assert len(client.get("/api/deck").get_json()) == 2


def test_deck_tile_plays_next_to_music(client, monkeypatch, container):
    vc = connected_client_with_tracks(client, monkeypatch, count=2)
    client.post("/api/play/category", json={"category": "combat_music"})
    queue_before = list(container.playback.queue)
    client.post("/api/deck", json={"url": YT_URL, "label": "Gong"})
    r = client.post("/api/deck/0/play", json={})
    assert r.get_json()["ok"] is True
    assert vc.source.count() == 2  # music + the tile
    assert container.playback.music is not None
    assert container.playback.queue == queue_before


def test_deck_play_unknown_tile_is_404(client, monkeypatch):
    connected_client_with_tracks(client, monkeypatch, count=1)
    assert client.post("/api/deck/3/play", json={}).status_code == 404


def test_deck_requires_json(client):
    r = client.post("/api/deck", data="url=x", content_type="application/x-www-form-urlencoded")
    assert r.status_code == 415


# ---------- Mixer and uploaded sounds ----------

class FramesSource:
    """Yields the given 20 ms frames of PCM, then ends (empty read)."""

    def __init__(self, frames):
        self.frames = list(frames)
        self.cleaned = False

    def read(self):
        return self.frames.pop(0) if self.frames else b""

    def cleanup(self):
        self.cleaned = True


def pcm(value, count=1920):
    import array
    return array.array("h", [value] * count).tobytes()


def samples(data):
    import array
    return array.array("h", data).tolist()


def test_mixer_sums_channels_and_clips():
    loop = asyncio.new_event_loop()
    try:
        mixer = Mixer(loop)
        mixer.add(Channel(FramesSource([pcm(20000)])))
        mixer.add(Channel(FramesSource([pcm(20000)])))
        assert set(samples(mixer.read())) == {32767}  # 40000 clipped to the 16-bit maximum
    finally:
        loop.close()


def test_mixer_single_channel_passes_through_and_idle_is_silence():
    loop = asyncio.new_event_loop()
    try:
        mixer = Mixer(loop)
        frame = pcm(1234)
        mixer.add(Channel(FramesSource([frame])))
        assert mixer.read() == frame
        assert mixer.read() == SILENCE_FRAME  # the only channel ended
        assert mixer.count() == 0
    finally:
        loop.close()


def test_mixer_skips_paused_channel_and_calls_on_end_when_source_ends():
    loop = asyncio.new_event_loop()
    try:
        mixer = Mixer(loop)
        ended = []
        paused_source = FramesSource([pcm(5)])
        quiet = Channel(paused_source)
        quiet.paused = True
        short = Channel(FramesSource([]), on_end=lambda: ended.append("done"))
        mixer.add(quiet)
        mixer.add(short)
        assert mixer.read() == SILENCE_FRAME
        assert paused_source.frames  # the paused channel was not read
        loop.run_until_complete(asyncio.sleep(0))  # let call_soon_threadsafe run
        assert ended == ["done"]
        assert mixer.count() == 1
    finally:
        loop.close()


def test_upload_saves_sound_and_plays_it_with_file_source(client, monkeypatch, tmp_path, container):
    import io
    monkeypatch.setattr(container.sounds, "directory", str(tmp_path))
    monkeypatch.setattr(discord, "FFmpegPCMAudio", FakeOpusSource)
    vc = connected_client_with_tracks(client, monkeypatch, count=1)
    data = {"file": (io.BytesIO(b"fake audio"), "Dzwon Bitewny.MP3"), "label": "Gong"}
    r = client.post("/api/deck/upload", data=data, content_type="multipart/form-data",
                    headers={"X-Requested-With": "panel"})
    assert r.get_json() == {"ok": True}
    tile = client.get("/api/deck").get_json()[0]
    assert tile["title"] == "Gong" and "url" not in tile
    assert tile["file"].endswith(".mp3") and "/" not in tile["file"]  # stored under a random name
    assert (tmp_path / tile["file"]).read_bytes() == b"fake audio"

    assert client.post("/api/deck/0/play", json={}).get_json()["ok"] is True
    assert vc.source.count() == 1
    assert vc.source is not None

    assert client.delete("/api/deck/0", json={}).get_json() == {"ok": True}
    assert not (tmp_path / tile["file"]).exists()


def test_upload_needs_panel_header_and_allowed_type(client, monkeypatch, tmp_path, container):
    import io
    monkeypatch.setattr(container.sounds, "directory", str(tmp_path))
    no_header = client.post("/api/deck/upload", data={"file": (io.BytesIO(b"x"), "a.mp3")},
                            content_type="multipart/form-data")
    assert no_header.status_code == 415
    bad_type = client.post("/api/deck/upload", data={"file": (io.BytesIO(b"x"), "a.exe")},
                           content_type="multipart/form-data", headers={"X-Requested-With": "panel"})
    assert bad_type.status_code == 400
    assert client.get("/api/deck").get_json() == []
    assert not any(path.suffix in {".mp3", ".exe"} for path in tmp_path.iterdir())


def test_upload_too_large_is_rejected(client, monkeypatch, tmp_path, container):
    import io
    monkeypatch.setattr(container.sounds, "directory", str(tmp_path))
    monkeypatch.setitem(client.application.config, "MAX_CONTENT_LENGTH", 1024)
    r = client.post("/api/deck/upload", data={"file": (io.BytesIO(b"x" * 4096), "a.mp3")},
                    content_type="multipart/form-data", headers={"X-Requested-With": "panel"})
    assert r.status_code == 413


def test_clicking_playing_tile_again_stops_it(client, monkeypatch):
    vc = connected_client_with_tracks(client, monkeypatch, count=1)
    client.post("/api/deck", json={"url": YT_URL, "label": "Gong"})
    first = client.post("/api/deck/0/play", json={}).get_json()
    assert first["playing"] is True
    assert client.get("/api/status").get_json()["sounds"] == [YT_URL]
    second = client.post("/api/deck/0/play", json={}).get_json()
    assert second == {"ok": True, "message": "Sound stopped", "playing": False}
    assert vc.source.count() == 0
    assert client.get("/api/status").get_json()["sounds"] == []


def test_stopping_one_tile_leaves_others_playing(client, monkeypatch):
    vc = connected_client_with_tracks(client, monkeypatch, count=1)
    client.post("/api/deck", json={"url": YT_URL, "label": "A"})
    client.post("/api/deck", json={"url": YT_URL[:-1] + "x", "label": "B"})
    client.post("/api/deck/0/play", json={})
    client.post("/api/deck/1/play", json={})
    client.post("/api/deck/0/play", json={})  # stop A only
    assert vc.source.count() == 1
    assert client.get("/api/status").get_json()["sounds"] == [YT_URL[:-1] + "x"]


# ---------- Editing tracks and tiles ----------

def test_edit_track_title_and_url(client, monkeypatch):
    connected_client_with_tracks(client, monkeypatch, count=0)
    client.post("/api/categories/combat_music/tracks", json={"url": YT_URL, "title": "Old"})
    r = client.put("/api/categories/combat_music/tracks/0", json={"title": "New", "url": YT_URL[:-1] + "x"})
    assert r.get_json() == {"ok": True}
    assert client.get("/api/categories").get_json()["combat_music"] == [{"url": YT_URL[:-1] + "x", "title": "New"}]


def test_edit_track_blank_title_keeps_old_title(client):
    client.post("/api/categories/combat_music/tracks", json={"url": YT_URL, "title": "Old"})
    client.put("/api/categories/combat_music/tracks/0", json={"title": "  "})
    assert client.get("/api/categories").get_json()["combat_music"][0]["title"] == "Old"


def test_edit_track_rejects_bad_input(client):
    client.post("/api/categories/combat_music/tracks", json={"url": YT_URL, "title": "Old"})
    assert client.put("/api/categories/combat_music/tracks/0", json={"url": "https://example.com/x"}).status_code == 400
    assert client.put("/api/categories/combat_music/tracks/0", json={"url": "https://www.youtube.com/playlist?list=PL1"}).status_code == 400
    assert client.put("/api/categories/combat_music/tracks/5", json={"title": "x"}).status_code == 404


def test_edit_deck_tile_title_and_link(client):
    client.post("/api/deck", json={"url": YT_URL, "label": "Gong"})
    assert client.put("/api/deck/0", json={"title": "Bell"}).get_json() == {"ok": True}
    assert client.put("/api/deck/0", json={"url": YT_URL[:-1] + "y", "title": "Bell"}).get_json() == {"ok": True}
    tile = client.get("/api/deck").get_json()[0]
    assert tile == {"url": YT_URL[:-1] + "y", "title": "Bell"}
    assert client.put("/api/deck/9", json={"title": "x"}).status_code == 404


def test_edit_uploaded_tile_renames_but_keeps_file(client, monkeypatch, tmp_path, container):
    import io
    monkeypatch.setattr(container.sounds, "directory", str(tmp_path))
    client.post("/api/deck/upload", data={"file": (io.BytesIO(b"x"), "a.mp3")},
                content_type="multipart/form-data", headers={"X-Requested-With": "panel"})
    stored = client.get("/api/deck").get_json()[0]["file"]
    client.put("/api/deck/0", json={"title": "Renamed", "url": YT_URL})
    tile = client.get("/api/deck").get_json()[0]
    assert tile == {"file": stored, "title": "Renamed"}


def test_tile_colour_set_validate_and_clear(client):
    client.post("/api/deck", json={"url": YT_URL, "label": "Gong"})
    assert client.put("/api/deck/0", json={"color": "#FF5D8F"}).get_json() == {"ok": True}
    tile = client.get("/api/deck").get_json()[0]
    assert tile["color"] == "#ff5d8f" and tile["title"] == "Gong"
    assert client.put("/api/deck/0", json={"color": "red"}).status_code == 400
    assert client.put("/api/deck/0", json={"color": "#12345"}).status_code == 400
    assert client.put("/api/deck/0", json={"color": None}).get_json() == {"ok": True}
    assert "color" not in client.get("/api/deck").get_json()[0]


def test_tile_group_set_create_and_clear(client, monkeypatch, tmp_path, container):
    import io
    monkeypatch.setattr(container.sounds, "directory", str(tmp_path))
    client.post("/api/deck", json={"url": YT_URL, "label": "Gong", "group": " Walka "})
    assert client.get("/api/deck").get_json()[0]["group"] == "Walka"
    assert client.put("/api/deck/0", json={"group": "Tawerna"}).get_json() == {"ok": True}
    assert client.get("/api/deck").get_json()[0]["group"] == "Tawerna"
    assert client.put("/api/deck/0", json={"group": "x" * 31}).status_code == 400
    assert client.put("/api/deck/0", json={"group": ""}).get_json() == {"ok": True}
    assert "group" not in client.get("/api/deck").get_json()[0]
    r = client.post("/api/deck/upload", data={"file": (io.BytesIO(b"x"), "a.mp3"), "group": "Pogoda"},
                    content_type="multipart/form-data", headers={"X-Requested-With": "panel"})
    assert r.get_json() == {"ok": True}
    assert client.get("/api/deck").get_json()[1]["group"] == "Pogoda"


# ---------- Playlist tracks from files ----------

def test_upload_track_to_playlist_and_copy_it(client, monkeypatch, tmp_path, container):
    import io
    monkeypatch.setattr(container.sounds, "directory", str(tmp_path))
    r = client.post("/api/categories/combat_music/upload", data={"file": (io.BytesIO(b"x"), "Bitwa.mp3"), "title": "Bitwa"},
                    content_type="multipart/form-data", headers={"X-Requested-With": "panel"})
    assert r.get_json() == {"ok": True, "added": 1}
    track = client.get("/api/categories").get_json()["combat_music"][0]
    assert track["title"] == "Bitwa" and "url" not in track and track["file"].endswith(".mp3")
    assert (tmp_path / track["file"]).exists()

    # Copying a stored file into another playlist reuses the same file.
    r = client.post("/api/categories/ambient_music/tracks", json={"file": track["file"], "title": "Bitwa"})
    assert r.get_json() == {"ok": True, "added": 1}
    assert client.get("/api/categories").get_json()["ambient_music"] == [{"file": track["file"], "title": "Bitwa"}]
    assert client.post("/api/categories/ambient_music/tracks", json={"file": "../../etc/passwd"}).status_code == 400

    # A file track can be renamed, and its file stays.
    assert client.put("/api/categories/combat_music/tracks/0", json={"title": "Nowa nazwa"}).get_json() == {"ok": True}
    assert client.get("/api/categories").get_json()["combat_music"][0] == {"file": track["file"], "title": "Nowa nazwa"}


def test_upload_track_to_missing_playlist_is_404(client, monkeypatch, tmp_path, container):
    import io
    monkeypatch.setattr(container.sounds, "directory", str(tmp_path))
    r = client.post("/api/categories/nope/upload", data={"file": (io.BytesIO(b"x"), "a.mp3")},
                    content_type="multipart/form-data", headers={"X-Requested-With": "panel"})
    assert r.status_code == 404


def test_deck_groups_add_list_delete(client):
    assert client.get("/api/deck/groups").get_json() == []
    assert client.post("/api/deck/groups", json={"name": "Tawerna"}).get_json()["ok"] is True
    assert client.post("/api/deck/groups", json={"name": "Tawerna"}).status_code == 400
    assert client.post("/api/deck/groups", json={"name": "   "}).status_code == 400
    client.post("/api/deck", json={"url": YT_URL, "label": "Gong", "group": "Tawerna"})
    assert client.get("/api/deck/groups").get_json() == ["Tawerna"]
    assert client.delete("/api/deck/groups/Tawerna", json={}).get_json() == {"ok": True}
    assert client.get("/api/deck/groups").get_json() == []
    assert "group" not in client.get("/api/deck").get_json()[0]  # the tile stays, just ungrouped


# ---------- Manage playlists and groups (rename, colour, delete) ----------

def test_rename_playlist_keeps_tracks_colour_and_order(client, container):
    client.post("/api/categories", json={"name": "tavern"})
    client.post("/api/categories", json={"name": "boss fight"})
    client.put("/api/categories/combat_music", json={"color": "#FF5D8F"})
    tracks = client.get("/api/categories").get_json()["ambient_music"]
    assert client.put("/api/categories/combat_music", json={"name": " Battle Music "}).get_json() == {"ok": True}
    # Responses are sorted by Flask, so the stored order is checked on the repository.
    assert list(container.playlists.categories()) == ["battle_music", "ambient_music", "storm_music", "tavern", "boss_fight"]
    assert client.get("/api/categories").get_json()["ambient_music"] == tracks
    assert client.get("/api/categories/colors").get_json() == {"battle_music": "#ff5d8f"}


def test_rename_playlist_moves_its_tracks(client, monkeypatch):
    client.post("/api/categories/storm_music/tracks", json={"url": YT_URL, "title": "Burza"})
    client.put("/api/categories/storm_music", json={"name": "storm_sounds"})
    assert client.get("/api/categories").get_json()["storm_sounds"] == [{"url": YT_URL, "title": "Burza"}]
    assert "storm_music" not in client.get("/api/categories").get_json()


@pytest.mark.parametrize("name", ["", "   ", "<b>x</b>", "../etc", "x" * 51])
def test_rename_playlist_rejects_invalid_names(client, name):
    r = client.put("/api/categories/combat_music", json={"name": name})
    assert r.status_code == 400
    assert "combat_music" in client.get("/api/categories").get_json()


def test_rename_playlist_rejects_duplicate_and_missing(client):
    r = client.put("/api/categories/combat_music", json={"name": "Storm Music"})
    assert r.status_code == 400 and r.get_json()["message"] == "Already exists"
    assert client.put("/api/categories/nope", json={"name": "fresh"}).status_code == 404
    assert client.put("/api/categories/combat_music", json={}).status_code == 400


def test_playlist_colour_set_validate_and_clear(client):
    assert client.put("/api/categories/combat_music", json={"color": "#3DDC97"}).get_json() == {"ok": True}
    assert client.get("/api/categories/colors").get_json() == {"combat_music": "#3ddc97"}
    assert client.put("/api/categories/combat_music", json={"color": "green"}).status_code == 400
    assert client.put("/api/categories/combat_music", json={"color": "#12345"}).status_code == 400
    assert client.put("/api/categories/nope", json={"color": "#3ddc97"}).status_code == 404
    assert client.put("/api/categories/combat_music", json={"color": None}).get_json() == {"ok": True}
    assert client.get("/api/categories/colors").get_json() == {}
    # The category shape itself never changes.
    assert set(client.get("/api/categories").get_json()) == {"combat_music", "ambient_music", "storm_music"}


def test_delete_playlist_removes_its_colour(client):
    client.put("/api/categories/storm_music", json={"color": "#4cc9f0"})
    assert client.delete("/api/categories/storm_music", json={}).get_json()["ok"] is True
    assert client.get("/api/categories/colors").get_json() == {}


def test_rename_group_updates_tiles_and_list(client):
    client.post("/api/deck/groups", json={"name": "Tawerna"})
    client.post("/api/deck", json={"url": YT_URL, "label": "Gong", "group": "Tawerna"})
    client.post("/api/deck", json={"url": YT_URL, "label": "Brzęk"})
    assert client.put("/api/deck/groups/Tawerna", json={"name": " Karczma "}).get_json() == {"ok": True}
    assert client.get("/api/deck/groups").get_json() == ["Karczma"]
    tiles = client.get("/api/deck").get_json()
    assert tiles[0]["group"] == "Karczma" and "group" not in tiles[1]


def test_rename_group_rejects_bad_duplicate_and_missing(client):
    client.post("/api/deck/groups", json={"name": "Tawerna"})
    client.post("/api/deck/groups", json={"name": "Walka"})
    assert client.put("/api/deck/groups/Tawerna", json={"name": "   "}).status_code == 400
    assert client.put("/api/deck/groups/Tawerna", json={"name": "x" * 31}).status_code == 400
    assert client.put("/api/deck/groups/Tawerna", json={"name": "Walka"}).status_code == 400
    assert client.put("/api/deck/groups/Nope", json={"name": "Fresh"}).status_code == 404
    assert client.get("/api/deck/groups").get_json() == ["Tawerna", "Walka"]


def test_group_colour_set_validate_clear_and_rename_moves_it(client):
    client.post("/api/deck/groups", json={"name": "Tawerna"})
    assert client.put("/api/deck/groups/Tawerna", json={"color": "#FF6B6B"}).get_json() == {"ok": True}
    assert client.get("/api/deck/groups/colors").get_json() == {"Tawerna": "#ff6b6b"}
    assert client.put("/api/deck/groups/Tawerna", json={"color": "red"}).status_code == 400
    assert client.put("/api/deck/groups/Tawerna", json={"color": "#12345"}).status_code == 400
    assert client.put("/api/deck/groups/Tawerna", json={"name": "Karczma"}).get_json() == {"ok": True}
    assert client.get("/api/deck/groups/colors").get_json() == {"Karczma": "#ff6b6b"}
    assert client.put("/api/deck/groups/Karczma", json={"color": None}).get_json() == {"ok": True}
    assert client.get("/api/deck/groups/colors").get_json() == {}


def test_delete_group_removes_its_colour(client):
    client.post("/api/deck/groups", json={"name": "Tawerna"})
    client.put("/api/deck/groups/Tawerna", json={"color": "#06d6a0"})
    assert client.delete("/api/deck/groups/Tawerna", json={}).get_json() == {"ok": True}
    assert client.get("/api/deck/groups/colors").get_json() == {}


def test_manage_routes_require_json_csrf(client):
    r = client.put("/api/categories/combat_music", data="name=x", content_type="text/plain")
    assert r.status_code == 415
    r = client.put("/api/deck/groups/Tawerna", data="name=x", content_type="text/plain")
    assert r.status_code == 415


def test_new_sound_can_carry_a_colour(client, container, monkeypatch, tmp_path):
    import io
    monkeypatch.setattr(container.sounds, "directory", str(tmp_path))
    client.post("/api/deck", json={"url": YT_URL, "label": "Gong", "color": "#FF5D8F"})
    assert client.get("/api/deck").get_json()[0]["color"] == "#ff5d8f"
    assert client.post("/api/deck", json={"url": YT_URL, "label": "X", "color": "red"}).status_code == 400
    r = client.post("/api/deck/upload", data={"file": (io.BytesIO(b"x"), "a.mp3"), "color": "#118ab2"},
                    content_type="multipart/form-data", headers={"X-Requested-With": "panel"})
    assert r.get_json() == {"ok": True}
    assert client.get("/api/deck").get_json()[1]["color"] == "#118ab2"
    r = client.post("/api/deck/upload", data={"file": (io.BytesIO(b"x"), "b.mp3"), "color": "blue"},
                    content_type="multipart/form-data", headers={"X-Requested-With": "panel"})
    assert r.status_code == 400
