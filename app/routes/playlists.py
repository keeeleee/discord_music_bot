import os
import re

from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename

from app.container import current_container
from app.validation import is_valid_colour, json_body
from config import MAX_TITLE_LENGTH
from services.tracks import (
    TrackError, is_stored_sound, is_valid_track_url, read_track_edit, resolve_tracks, sound_error, store_upload,
)
from storage.playlists import UNSET

bp = Blueprint("playlists", __name__, url_prefix="/api")

CATEGORY_NAME_RE = re.compile(r"^[a-z0-9_-]{1,50}$")


def normalise_category_name(value):
    """Returns the playlist name as it is stored (stripped, spaces to underscores, lower case), or None if invalid."""
    if not isinstance(value, str):
        return None
    name = value.strip().replace(" ", "_").lower()
    return name if CATEGORY_NAME_RE.match(name) else None


@bp.route("/categories", methods=["GET"])
def categories():
    return jsonify(current_container().playlists.categories())


@bp.route("/categories/colors", methods=["GET"])
def category_colors():
    return jsonify(current_container().playlists.category_colors())


@bp.route("/categories", methods=["POST"])
def add_category():
    c = current_container()
    name = json_body().get("name", "")
    if not isinstance(name, str):
        name = ""
    name = name.strip().replace(" ", "_").lower()
    if not name:
        return jsonify({"ok": False, "message": "name required"}), 400
    if not CATEGORY_NAME_RE.match(name):
        return jsonify({"ok": False, "message": "Use only letters, digits, spaces, - and _ (max 50)"}), 400
    ok = c.playlists.add_category(name)
    return jsonify({"ok": ok, "message": "Category added" if ok else "Already exists"})


@bp.route("/categories/<name>", methods=["PUT"])
def update_category(name):
    """Renames a playlist ({"name": new}) and/or sets its colour ({"color": "#rrggbb" or null})."""
    c = current_container()
    if not c.playlists.category_exists(name):
        return jsonify({"ok": False, "message": "Playlist not found"}), 404
    data = json_body()
    if "name" not in data and "color" not in data:
        return jsonify({"ok": False, "message": "Nothing to change"}), 400
    new_name = None
    if "name" in data:
        new_name = normalise_category_name(data["name"])
        if new_name is None:
            return jsonify({"ok": False, "message": "Use only letters, digits, spaces, - and _ (max 50)"}), 400
    color = data.get("color", UNSET)
    if color is not UNSET and color is not None:
        if not is_valid_colour(color):
            return jsonify({"ok": False, "message": "Colour must look like #7c6cff"}), 400
        color = color.lower()
    result = c.playlists.update_category(name, new_name, color)
    if result == "taken":
        return jsonify({"ok": False, "message": "Already exists"}), 400
    return jsonify({"ok": result == "ok"})


@bp.route("/categories/<name>", methods=["DELETE"])
def delete_category(name):
    return jsonify({"ok": current_container().playlists.delete_category(name)})


@bp.route("/categories/<category>/upload", methods=["POST"])
def upload_track(category):
    c = current_container()
    if not CATEGORY_NAME_RE.match(category) or category not in c.playlists.categories():
        return jsonify({"ok": False, "message": "Playlist not found"}), 404
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify({"ok": False, "message": "file required"}), 400
    title = request.form.get("title", "").strip()[:MAX_TITLE_LENGTH]
    error = sound_error(upload.filename)
    if error:
        return jsonify({"ok": False, "message": error}), 400
    stored = store_upload(upload, c.sounds)
    title = title or os.path.splitext(secure_filename(upload.filename))[0] or "Track"
    c.playlists.add_tracks(category, [{"file": stored, "title": title[:MAX_TITLE_LENGTH]}])
    return jsonify({"ok": True, "added": 1})


@bp.route("/categories/<category>/tracks", methods=["POST"])
def add_track(category):
    c = current_container()
    if not CATEGORY_NAME_RE.match(category):
        return jsonify({"ok": False, "message": "Invalid category"}), 400
    data = json_body()
    stored = data.get("file")
    if stored is not None:
        # Copying a track that is already a stored file (for example into another playlist).
        if not isinstance(stored, str) or not is_stored_sound(stored) or not c.sounds.exists(stored):
            return jsonify({"ok": False, "message": "Stored file not found"}), 400
        title = data.get("title", "") if isinstance(data.get("title", ""), str) else ""
        c.playlists.add_tracks(category, [{"file": stored, "title": title.strip()[:MAX_TITLE_LENGTH] or stored}])
        return jsonify({"ok": True, "added": 1})
    url = data.get("url", "")
    title = data.get("title", "")
    if not isinstance(url, str) or not isinstance(title, str):
        return jsonify({"ok": False, "message": "url and title must be strings"}), 400
    url = url.strip()
    title = title.strip()[:MAX_TITLE_LENGTH]
    if not url:
        return jsonify({"ok": False, "message": "url required"}), 400
    if not is_valid_track_url(url):
        return jsonify({"ok": False, "message": "Only YouTube links are allowed"}), 400
    try:
        tracks = resolve_tracks(url, title)
    except TrackError as e:
        return jsonify({"ok": False, "message": str(e)}), e.status
    for track in tracks:
        track["title"] = track["title"][:MAX_TITLE_LENGTH]
    c.playlists.add_tracks(category, tracks)
    return jsonify({"ok": True, "added": len(tracks)})


@bp.route("/categories/<category>/tracks/<int:index>", methods=["PUT"])
def update_track(category, index):
    c = current_container()
    if not CATEGORY_NAME_RE.match(category):
        return jsonify({"ok": False, "message": "Invalid category"}), 400
    tracks = c.playlists.tracks(category)
    if not 0 <= index < len(tracks):
        return jsonify({"ok": False, "message": "Track not found"}), 404
    data = json_body()
    if tracks[index].get("file"):
        # Stored files keep their file; only the name can change.
        title = data.get("title", "")
        if not isinstance(title, str):
            return jsonify({"ok": False, "message": "title must be a string"}), 400
        ok = c.playlists.rename_track(category, index, title.strip()[:MAX_TITLE_LENGTH] or tracks[index]["title"])
        return jsonify({"ok": ok})
    try:
        url, title = read_track_edit(data, tracks[index])
        if url != tracks[index]["url"] and not title:
            title = resolve_tracks(url, "")[0]["title"]
    except TrackError as e:
        return jsonify({"ok": False, "message": str(e)}), e.status
    ok = c.playlists.update_track(category, index, url, (title or tracks[index]["title"])[:MAX_TITLE_LENGTH])
    return jsonify({"ok": ok})


@bp.route("/categories/<category>/tracks/<int:index>", methods=["DELETE"])
def remove_track(category, index):
    return jsonify({"ok": current_container().playlists.remove_track(category, index)})
