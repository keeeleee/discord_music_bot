import os
import re

from flask import Blueprint, jsonify

from app.container import current_container
from audio.peaks import waveform
from app.validation import is_finite_number, json_body
from config import SEEK_TIMEOUT, STATUS_QUEUE_PREVIEW

bp = Blueprint("playback", __name__, url_prefix="/api")


STORED_SOUND_RE = re.compile(r"^[0-9a-f]{32}\.(mp3|wav|ogg|opus|m4a|flac|webm)$")


@bp.route("/peaks/<name>", methods=["GET"])
def peaks(name):
    c = current_container()
    if not STORED_SOUND_RE.match(name) or not os.path.exists(c.sounds.path(name)):
        return jsonify({"ok": False, "message": "Sound not found"}), 404
    values = waveform(c.sounds.path(name))
    if values is None:
        return jsonify({"ok": False, "message": "Could not read the audio"}), 500
    return jsonify(values)


@bp.route("/status", methods=["GET"])
def status():
    c = current_container()
    pb = c.playback
    vc = pb.voice_client
    connected = vc is not None and vc.is_connected()
    queue = list(pb.queue)
    return jsonify({
        "connected": connected,
        "is_playing": pb.is_playing,
        "is_paused": bool(pb.music and pb.music.paused),
        "sounds": c.player.playing_sound_tags(),
        "current_track": pb.current_track,
        "current_category": pb.current_category,
        "elapsed": pb.elapsed_seconds(),
        "queue": [{"title": t.get("title") or t.get("url") or t.get("file"), "url": t.get("url"), "file": t.get("file")} for t in queue[:STATUS_QUEUE_PREVIEW]],
        "queue_length": len(queue),
        "loop": pb.loop,
        "shuffle": pb.shuffle,
        "guild_id": pb.guild_id,
        "channel_id": pb.channel_id,
        "channel_name": vc.channel.name if connected else None,
    })


@bp.route("/play/category", methods=["POST"])
def play_category():
    c = current_container()
    category = json_body().get("category")
    if not isinstance(category, str) or not category:
        return jsonify({"ok": False, "message": "category required"}), 400
    ok, msg = c.bridge.run_async(c.player.play_category(category))
    return jsonify({"ok": ok, "message": msg})


@bp.route("/play/track", methods=["POST"])
def play_track():
    c = current_container()
    data = json_body()
    category = data.get("category")
    index = data.get("index")
    if not isinstance(category, str) or not isinstance(index, int) or isinstance(index, bool):
        return jsonify({"ok": False, "message": "category and index required"}), 400
    tracks = c.playlists.tracks(category)
    if not 0 <= index < len(tracks):
        return jsonify({"ok": False, "message": "Track not found"}), 404
    ok, msg = c.bridge.run_async(c.player.play_single_track(dict(tracks[index]), category))
    return jsonify({"ok": ok, "message": msg})


@bp.route("/stop", methods=["POST"])
def stop():
    c = current_container()
    return jsonify({"ok": c.bridge.call(c.player.stop_music)})


@bp.route("/pause", methods=["POST"])
def pause():
    c = current_container()
    return jsonify({"ok": c.bridge.call(c.player.pause_music)})


@bp.route("/resume", methods=["POST"])
def resume():
    c = current_container()
    return jsonify({"ok": c.bridge.call(c.player.resume_music)})


@bp.route("/skip", methods=["POST"])
def skip():
    c = current_container()
    return jsonify({"ok": c.bridge.call(c.player.skip_track)})


@bp.route("/seek", methods=["POST"])
def seek():
    # Body: {"position": seconds} to jump to an absolute time, or {"offset": seconds} to move relatively.
    c = current_container()
    data = json_body()
    position = data.get("position")
    offset = data.get("offset")
    if (position is None) == (offset is None):
        return jsonify({"ok": False, "message": "Give exactly one of position or offset"}), 400
    value = position if position is not None else offset
    if not is_finite_number(value):
        return jsonify({"ok": False, "message": "position and offset must be numbers"}), 400
    if position is not None:
        ok = c.bridge.run_async(c.player.seek_music(position=float(position)), timeout=SEEK_TIMEOUT)
    else:
        ok = c.bridge.run_async(c.player.seek_music(offset=float(offset)), timeout=SEEK_TIMEOUT)
    return jsonify({"ok": ok})


@bp.route("/loop", methods=["POST"])
def loop():
    c = current_container()
    enabled = c.player.set_loop(bool(json_body().get("loop", False)))
    return jsonify({"ok": True, "loop": enabled})


@bp.route("/shuffle", methods=["POST"])
def shuffle():
    c = current_container()
    enabled = c.bridge.call(c.player.set_shuffle, bool(json_body().get("shuffle", False)))
    return jsonify({"ok": True, "shuffle": enabled})
