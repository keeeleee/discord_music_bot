import itertools
from urllib.parse import urlparse

import yt_dlp

from config import MAX_PLAYLIST_TRACKS

YTDL_OPTIONS = {
    "format": "bestaudio[acodec=opus]/bestaudio[ext=webm]/bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "extract_flat": False,
    "source_address": "0.0.0.0",
}

# Used when adding tracks: reads titles (and playlist entries) without resolving audio streams.
METADATA_OPTIONS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "extract_flat": "in_playlist",
}
UNAVAILABLE_TITLES = {"[Private video]", "[Deleted video]"}


def get_audio_url(youtube_url):
    with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
        if "entries" in info:
            info = info["entries"][0]
        return {
            "url": info["url"],
            "title": info.get("title", youtube_url),
            "acodec": info.get("acodec", ""),
            "headers": info.get("http_headers") or {},
            "duration": info.get("duration"),
        }


def is_playlist_url(url):
    return urlparse(url).path == "/playlist"


def fetch_tracks(url):
    """Returns [{url, title}] for a single video, or for every video of a playlist link."""
    with yt_dlp.YoutubeDL({**METADATA_OPTIONS, "noplaylist": not is_playlist_url(url)}) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = info.get("entries")
    if entries is None:
        return [{"url": url, "title": info.get("title") or url}]
    tracks = []
    for entry in itertools.islice(entries, MAX_PLAYLIST_TRACKS):
        if not entry or not entry.get("id") or entry.get("title") in UNAVAILABLE_TITLES:
            continue
        tracks.append({
            "url": f"https://www.youtube.com/watch?v={entry['id']}",
            "title": entry.get("title") or entry["id"],
        })
    return tracks
