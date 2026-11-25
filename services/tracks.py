import os
import re
from urllib.parse import urlparse

from audio import youtube
from config import ALLOWED_SOUND_EXTENSIONS, MAX_TITLE_LENGTH, MAX_URL_LENGTH

ALLOWED_TRACK_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}
STORED_SOUND_RE = re.compile(r"^[0-9a-f]{32}\.(mp3|wav|ogg|opus|m4a|flac|webm)$")


class TrackError(Exception):
    """A user-facing problem with a track or link, with the HTTP status to answer with."""

    def __init__(self, message, status):
        super().__init__(message)
        self.status = status


def is_valid_track_url(url):
    if len(url) > MAX_URL_LENGTH:
        return False
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and parsed.hostname in ALLOWED_TRACK_HOSTS


def sound_error(filename):
    """Returns the message for a file name that is not an allowed sound, or None."""
    if os.path.splitext(filename or "")[1].lower() in ALLOWED_SOUND_EXTENSIONS:
        return None
    return "Unsupported file type: " + ", ".join(sorted(ALLOWED_SOUND_EXTENSIONS))


def store_upload(upload, sounds):
    """Saves an allowed upload under a random name and returns the stored name."""
    ext = os.path.splitext(upload.filename or "")[1].lower()
    return sounds.save(upload, ext)


def is_stored_sound(name):
    return bool(STORED_SOUND_RE.match(name))


def resolve_tracks(url, title):
    """Returns the tracks to add for a link: the given title, or titles read from YouTube."""
    playlist = youtube.is_playlist_url(url)
    if title and not playlist:
        return [{"url": url, "title": title}]
    try:
        tracks = youtube.fetch_tracks(url)
    except Exception as e:
        print(f"Could not read {url} from YouTube: {e!r}")
        if playlist:
            raise TrackError("Could not read this playlist from YouTube", 502) from e
        return [{"url": url, "title": url}]
    if not tracks:
        raise TrackError("No playable videos found", 400)
    return tracks


def read_track_edit(data, current):
    """Validates an edit of a link track. Returns (url, title); raises TrackError on a bad value."""
    url = data.get("url", current["url"])
    title = data.get("title", "")
    if not isinstance(url, str) or not isinstance(title, str):
        raise TrackError("url and title must be strings", 400)
    url = url.strip()
    title = title.strip()[:MAX_TITLE_LENGTH]
    if not url or not is_valid_track_url(url):
        raise TrackError("Only YouTube links are allowed", 400)
    if youtube.is_playlist_url(url):
        raise TrackError("Use a single video link, not a playlist", 400)
    return url, title
