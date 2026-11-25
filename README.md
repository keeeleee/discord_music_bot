# Discord Play Music

A Discord bot that plays music from YouTube in a voice channel. You control it from a simple web panel that runs locally, so all players in the channel hear the same music, for example during an RPG session.

## Features

- Join and leave a chosen voice channel from the panel.
- Music categories (`combat_music`, `ambient_music` and `storm_music` by default), plus your own categories that you can add and delete.
- Add YouTube links to categories. Titles are read from YouTube automatically, and a playlist link adds all of its videos at once.
- Play a whole category (optionally shuffled) or a single track.
- Pause, resume, skip and stop tracks, and repeat the current track.
- Seek within the current track: jump 10 seconds back or forward, or to any position.
- Soundboard: up to 24 tiles, each a YouTube video or a file from your computer, with your own label. Click a tile to play it right away. Tiles play next to the music and next to each other (up to 8 sounds at once).
- See what is playing now, its progress, and the next tracks in the queue.
- The next track is prepared in the background, so there is barely any silence between tracks.
- The bot leaves the voice channel automatically a minute after everyone else leaves.
- The panel remembers your server, channel and category, and also works on a phone or tablet.

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (recommended) or `pip`
- A Discord bot account with a token

You don't need to install FFmpeg manually. The `static-ffmpeg` package downloads it automatically on first run.

## Discord bot setup

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and create a new application.
2. In the **Bot** tab, generate a token (**Reset Token**) and copy it.
3. The bot doesn't need any *Privileged Gateway Intents*, so you can leave them disabled.
4. In the **OAuth2 → URL Generator** tab:
   - under *Scopes*, select `bot`,
   - under *Bot Permissions*, select `View Channels`, `Connect` and `Speak`.
5. Open the generated link and invite the bot to your server.

## Installation

```bash
git clone https://github.com/keeeleee/discord_music_bot.git
cd discord_music_bot
uv sync
```

If you use `pip` instead of `uv`:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

Copy the example file and add your token:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `DISCORD_TOKEN` | none (required) | Bot token from the Developer Portal |
| `FLASK_HOST` | `127.0.0.1` | Address the web panel listens on |
| `FLASK_PORT` | `5000` | Web panel port |

> ⚠️ Never commit the `.env` file, because it contains your bot token. The file is already listed in `.gitignore`. If your token leaks, reset it right away in the Developer Portal.

## Running

```bash
uv run main.py
```

Or, if you use `pip` with the virtual environment activated:

```bash
python main.py
```

Then open `http://localhost:5000` (or the port you set in `FLASK_PORT`).

## Usage

1. Select a server and a voice channel, then click **Join**.
2. Select a category or add a new one.
3. Add YouTube links to the category. Leave the title empty to use the one from YouTube. A playlist link (`youtube.com/playlist?list=…`) adds all its videos (up to 200).
4. Click **▶ Play category** to play the whole category, or **▶** next to a single track. Turn on **🔀 Shuffle** to play the category in random order.
5. Control playback with the Pause, ⏪ 10s / 10s ⏩, Skip, Stop and Repeat buttons. Each listener can set the bot's volume in Discord (right-click the bot → User Volume).

Soundboard files you upload are stored in the `sounds/` folder (not committed to the repository). Playlists are saved to `playlists.json` in the project directory. The file is created automatically on first run and is not committed to the repository.

### Controlling playback from a pad or script

The panel's HTTP API can be called from anything that sends HTTP requests, such as a Stream Deck (HTTP request plugin), a MIDI/macro pad script, or a shell. Requests must send `Content-Type: application/json` (the body may be `{}`):

| Action | Request |
|---|---|
| Pause / resume | `POST /api/pause`, `POST /api/resume` |
| Skip / stop | `POST /api/skip`, `POST /api/stop` |
| Seek back 10 s | `POST /api/seek` with `{"offset": -10}` |
| Seek forward 10 s | `POST /api/seek` with `{"offset": 10}` |
| Jump to a time | `POST /api/seek` with `{"position": 90}` (seconds) |

Example: `curl -X POST -H 'Content-Type: application/json' -d '{"offset": -10}' http://127.0.0.1:5000/api/seek`

Seeking restarts the track's stream at the new position, so it takes a moment on long tracks.

## Security

- The web panel **has no login**. By default it listens only on `127.0.0.1`, so you can open it only from your own computer.
- Set `FLASK_HOST=0.0.0.0` only if you trust everyone on your network, because then anyone who knows the address can control the bot. Don't expose the panel to the internet.
- Only YouTube links (`youtube.com`, `youtu.be`, `music.youtube.com`) can be added to playlists.

## Tests

```bash
uv run pytest
```

## Project structure

```
main.py               # entry point: loads .env, starts the Flask panel and the bot
config.py             # settings, paths and limits
app/                  # Flask app factory, REST routes under /api, request validation
services/tracks.py    # track and link rules, reading titles from YouTube, sound uploads
storage/              # playlists.json and soundboard persistence (JsonStore + repositories)
voice/                # Discord client, voice connection, playback state and player
audio/                # PCM mixer, FFmpeg sources, yt-dlp helpers
templates/index.html  # web panel UI
tests/                # tests (pytest)
```

## Troubleshooting

- **`DISCORD_TOKEN is not set`**: the `.env` file is missing or has no token in it.
- **The bot's server isn't in the list**: make sure the bot is invited to the server and is online (the console should show `Bot logged in as ...`).
- **The bot joins the channel but the panel says it timed out**: a firewall or VPN is probably blocking Discord voice servers (non-standard ports and UDP). Try another network or run the bot on a different machine.
- **A track doesn't play**: YouTube changes often, so update yt-dlp with `uv lock --upgrade-package yt-dlp && uv sync`.
