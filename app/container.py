from dataclasses import dataclass

from flask import current_app

import config
from app.bridge import LoopBridge
from storage.json_store import JsonStore
from storage.playlists import PlaylistRepository
from storage.sound_files import SoundFiles
from storage.soundboard import SoundboardRepository
from voice.connection import VoiceConnection, create_client, load_opus_library
from voice.playback import PlaybackState
from voice.player import Player


@dataclass
class Container:
    """Every long-lived object the web panel and the bot share."""

    client: object
    bridge: LoopBridge
    playback: PlaybackState
    voice: VoiceConnection
    player: Player
    playlists: PlaylistRepository
    soundboard: SoundboardRepository
    sounds: SoundFiles


def build_container(data_file=config.DATA_FILE, sounds_dir=config.SOUNDS_DIR):
    load_opus_library()
    client = create_client()
    store = JsonStore(data_file)
    playlists = PlaylistRepository(store)
    soundboard = SoundboardRepository(store)
    sounds = SoundFiles(sounds_dir)
    playback = PlaybackState()
    return Container(
        client=client,
        bridge=LoopBridge(client),
        playback=playback,
        voice=VoiceConnection(client, playback),
        player=Player(playback, playlists, sounds),
        playlists=playlists,
        soundboard=soundboard,
        sounds=sounds,
    )


def current_container():
    return current_app.extensions["container"]
