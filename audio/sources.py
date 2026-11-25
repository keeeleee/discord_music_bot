import shlex
import shutil
import subprocess

import discord
import static_ffmpeg

static_ffmpeg.add_paths()

FFMPEG_BEFORE_OPTS = (
    "-nostdin "
    "-reconnect 1 "
    "-reconnect_streamed 1 "
    "-reconnect_on_network_error 1 "
    "-reconnect_on_http_error 4xx,5xx "
    "-reconnect_delay_max 5 "
    "-analyzeduration 0 "
    "-probesize 32 "
    "-rw_timeout 15000000"
)
FFMPEG_OPTS = "-vn -bufsize 512k"


def build_ffmpeg_before_opts(headers):
    if not headers:
        return FFMPEG_BEFORE_OPTS
    header_str = "".join(f"{key}: {value}\r\n" for key, value in headers.items())
    return f"{FFMPEG_BEFORE_OPTS} -headers {shlex.quote(header_str)}"


def create_audio_source(audio_url, before_opts):
    # PCM, not Opus: the mixer has to add sounds together before they are encoded.
    return discord.FFmpegPCMAudio(audio_url, before_options=before_opts, options=FFMPEG_OPTS)


def create_local_source(path):
    return discord.FFmpegPCMAudio(path, options=FFMPEG_OPTS)


def probe_duration(path):
    """Length of a local audio file in seconds, or None when ffprobe cannot tell."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return None
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
        return float(out)
    except (subprocess.SubprocessError, OSError, ValueError):
        return None
