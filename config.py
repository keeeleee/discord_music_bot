import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "playlists.json")
SOUNDS_DIR = os.path.join(BASE_DIR, "sounds")
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.getenv("FLASK_PORT", 5000))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

# Uploads
MAX_SOUND_BYTES = 15 * 1024 * 1024
ALLOWED_SOUND_EXTENSIONS = {".mp3", ".wav", ".ogg", ".opus", ".m4a", ".flac", ".webm"}

# Limits for names, links and lists
MAX_TITLE_LENGTH = 200
MAX_URL_LENGTH = 500
MAX_GROUP_LENGTH = 30
MAX_DECK_TILES = 24
MAX_PLAYLIST_TRACKS = 200
STATUS_QUEUE_PREVIEW = 20

# Discord reads 20 ms of 48 kHz stereo signed 16-bit PCM per frame.
FRAME_BYTES = 3840
# How many sounds (music + soundboard tiles) may play at the same time.
MAX_PARALLEL_SOUNDS = 8

VOICE_CONNECT_TIMEOUT = 20.0
VOICE_CONNECT_ATTEMPTS = 2
VOICE_RETRY_DELAY = 2
# Upper bound for joining, so the web panel waits long enough for all attempts.
JOIN_TIMEOUT = VOICE_CONNECT_ATTEMPTS * (VOICE_CONNECT_TIMEOUT + VOICE_RETRY_DELAY) + 5
AUTO_LEAVE_DELAY = 60

# Web panel waits for the bot's event loop: normal calls, and calls that may re-resolve a stream.
BOT_TIMEOUT = 15
SEEK_TIMEOUT = 30

# Stream URLs from YouTube stay valid for hours; refresh prefetched ones after 30 minutes anyway.
PREFETCH_MAX_AGE = 30 * 60
