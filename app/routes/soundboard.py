import os

from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename

from app.container import current_container
from app.validation import is_valid_colour, json_body, normalise_group
from audio import youtube
from config import MAX_DECK_TILES, MAX_GROUP_LENGTH, MAX_TITLE_LENGTH, SEEK_TIMEOUT
from services.tracks import (
    TrackError, is_valid_track_url, read_track_edit, resolve_tracks, sound_error, store_upload,
)
from storage.soundboard import UNSET

bp = Blueprint("soundboard", __name__, url_prefix="/api")


@bp.route("/deck", methods=["GET"])
def deck():
    return jsonify(current_container().soundboard.tiles())


@bp.route("/deck/groups", methods=["GET"])
def deck_groups():
    return jsonify(current_container().soundboard.groups())


@bp.route("/deck/groups", methods=["POST"])
def add_deck_group():
    c = current_container()
    name = json_body().get("name", "")
    name = normalise_group(name) if isinstance(name, str) else None
    if not name:
        return jsonify({"ok": False, "message": f"Group name required (up to {MAX_GROUP_LENGTH} characters)"}), 400
    ok = c.soundboard.add_group(name)
    return jsonify({"ok": ok, "message": "Group added" if ok else "Group already exists"}), (200 if ok else 400)


@bp.route("/deck/groups/colors", methods=["GET"])
def deck_group_colors():
    return jsonify(current_container().soundboard.group_colors())


@bp.route("/deck/groups/<path:name>", methods=["PUT"])
def update_deck_group(name):
    """Renames a group ({"name": new}) and/or sets its colour ({"color": "#rrggbb" or null})."""
    c = current_container()
    if not c.soundboard.group_exists(name):
        return jsonify({"ok": False, "message": "Group not found"}), 404
    data = json_body()
    if "name" not in data and "color" not in data:
        return jsonify({"ok": False, "message": "Nothing to change"}), 400
    new_name = None
    if "name" in data:
        new_name = normalise_group(data["name"]) if isinstance(data["name"], str) else None
        if not new_name:
            return jsonify({"ok": False, "message": f"Group name required (up to {MAX_GROUP_LENGTH} characters)"}), 400
    color = data.get("color", UNSET)
    if color is not UNSET and color is not None:
        if not is_valid_colour(color):
            return jsonify({"ok": False, "message": "Colour must look like #7c6cff"}), 400
        color = color.lower()
    result = c.soundboard.update_group(name, new_name, color)
    if result == "taken":
        return jsonify({"ok": False, "message": "Group already exists"}), 400
    return jsonify({"ok": result == "ok"})


@bp.route("/deck/groups/<path:name>", methods=["DELETE"])
def delete_deck_group(name):
    return jsonify({"ok": current_container().soundboard.delete_group(name)})


@bp.route("/deck", methods=["POST"])
def add_deck_tile():
    c = current_container()
    data = json_body()
    url = data.get("url", "")
    label = data.get("label", "")
    if not isinstance(url, str) or not isinstance(label, str):
        return jsonify({"ok": False, "message": "url and label must be strings"}), 400
    url = url.strip()
    label = label.strip()[:MAX_TITLE_LENGTH]
    if not url:
        return jsonify({"ok": False, "message": "url required"}), 400
    if not is_valid_track_url(url):
        return jsonify({"ok": False, "message": "Only YouTube links are allowed"}), 400
    if youtube.is_playlist_url(url):
        return jsonify({"ok": False, "message": "A tile needs a single video link, not a playlist"}), 400
    if len(c.soundboard.tiles()) >= MAX_DECK_TILES:
        return jsonify({"ok": False, "message": f"Deck is full (max {MAX_DECK_TILES} tiles)"}), 400
    try:
        tracks = resolve_tracks(url, label)
    except TrackError as e:
        return jsonify({"ok": False, "message": str(e)}), e.status
    group = normalise_group(data.get("group"))
    if group is None:
        return jsonify({"ok": False, "message": f"Group must be text up to {MAX_GROUP_LENGTH} characters"}), 400
    color = data.get("color")
    if color is not None and not is_valid_colour(color):
        return jsonify({"ok": False, "message": "Colour must look like #7c6cff"}), 400
    c.soundboard.add_tile(tracks[0]["title"][:MAX_TITLE_LENGTH], url=url, group=group, color=color.lower() if color else None)
    return jsonify({"ok": True})


@bp.route("/deck/upload", methods=["POST"])
def upload_deck_tile():
    c = current_container()
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify({"ok": False, "message": "file required"}), 400
    error = sound_error(upload.filename)
    if error:
        return jsonify({"ok": False, "message": error}), 400
    if len(c.soundboard.tiles()) >= MAX_DECK_TILES:
        return jsonify({"ok": False, "message": f"Deck is full (max {MAX_DECK_TILES} tiles)"}), 400
    label = request.form.get("label", "").strip()[:MAX_TITLE_LENGTH]
    title = label or os.path.splitext(secure_filename(upload.filename))[0] or "Sound"
    stored = store_upload(upload, c.sounds)
    group = normalise_group(request.form.get("group"))
    if group is None:
        c.sounds.remove(stored)
        return jsonify({"ok": False, "message": f"Group must be text up to {MAX_GROUP_LENGTH} characters"}), 400
    color = request.form.get("color") or None
    if color is not None and not is_valid_colour(color):
        c.sounds.remove(stored)
        return jsonify({"ok": False, "message": "Colour must look like #7c6cff"}), 400
    c.soundboard.add_tile(title[:MAX_TITLE_LENGTH], file=stored, group=group, color=color.lower() if color else None)
    return jsonify({"ok": True})


@bp.route("/deck/<int:index>", methods=["PUT"])
def update_deck_tile(index):
    c = current_container()
    tiles = c.soundboard.tiles()
    if not 0 <= index < len(tiles):
        return jsonify({"ok": False, "message": "Tile not found"}), 404
    current = tiles[index]
    data = json_body()
    if "color" in data:
        color = data["color"]
        if color is not None and not is_valid_colour(color):
            return jsonify({"ok": False, "message": "Colour must look like #7c6cff"}), 400
        c.soundboard.set_tile_field(index, "color", color.lower() if color else None)
    if "group" in data:
        group = normalise_group(data["group"])
        if group is None:
            return jsonify({"ok": False, "message": f"Group must be text up to {MAX_GROUP_LENGTH} characters"}), 400
        c.soundboard.set_tile_field(index, "group", group)
    if ("color" in data or "group" in data) and not any(key in data for key in ("title", "url")):
        return jsonify({"ok": True})
    title = data.get("title", "")
    if not isinstance(title, str):
        return jsonify({"ok": False, "message": "title must be a string"}), 400
    title = title.strip()[:MAX_TITLE_LENGTH]
    if "file" in current:
        # Uploaded sounds keep their file; only the name can change.
        ok = c.soundboard.update_tile(index, title or current["title"])
        return jsonify({"ok": ok})
    try:
        url, _ = read_track_edit(data, current)
        if url != current["url"] and not title:
            title = resolve_tracks(url, "")[0]["title"]
    except TrackError as e:
        return jsonify({"ok": False, "message": str(e)}), e.status
    ok = c.soundboard.update_tile(index, (title or current["title"])[:MAX_TITLE_LENGTH], url)
    return jsonify({"ok": ok})


@bp.route("/deck/<int:index>", methods=["DELETE"])
def delete_deck_tile(index):
    c = current_container()
    tile = c.soundboard.delete_tile(index)
    if tile is not None:
        c.sounds.remove(tile.get("file"))
    return jsonify({"ok": tile is not None})


@bp.route("/deck/<int:index>/play", methods=["POST"])
def play_deck_tile(index):
    c = current_container()
    tiles = c.soundboard.tiles()
    if not 0 <= index < len(tiles):
        return jsonify({"ok": False, "message": "Tile not found"}), 404
    tile = dict(tiles[index])
    ok, msg = c.bridge.run_async(c.player.play_sound(tile), timeout=SEEK_TIMEOUT)
    return jsonify({"ok": ok, "message": msg, "playing": c.player.tile_key(tile) in c.player.playing_sound_tags()})
