from flask import Blueprint, jsonify

from app.container import current_container
from app.validation import is_valid_snowflake, json_body
from config import JOIN_TIMEOUT

bp = Blueprint("voice", __name__, url_prefix="/api")


@bp.route("/guilds", methods=["GET"])
def guilds():
    return jsonify(current_container().voice.guilds())


@bp.route("/guilds/<guild_id>/channels", methods=["GET"])
def voice_channels(guild_id):
    if not is_valid_snowflake(guild_id):
        return jsonify([])
    return jsonify(current_container().voice.voice_channels(guild_id))


@bp.route("/join", methods=["POST"])
def join():
    c = current_container()
    data = json_body()
    guild_id = str(data.get("guild_id", ""))
    channel_id = str(data.get("channel_id", ""))
    if not is_valid_snowflake(guild_id) or not is_valid_snowflake(channel_id):
        return jsonify({"ok": False, "message": "guild_id and channel_id required"}), 400
    ok, msg = c.bridge.run_async(c.voice.join(guild_id, channel_id), timeout=JOIN_TIMEOUT)
    return jsonify({"ok": ok, "message": msg})


@bp.route("/leave", methods=["POST"])
def leave():
    c = current_container()
    return jsonify({"ok": c.bridge.run_async(c.voice.leave())})
