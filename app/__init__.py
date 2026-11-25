import re
from concurrent.futures import TimeoutError as FutureTimeoutError

from flask import Flask, current_app, jsonify, request
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

import config
from app.container import build_container
from app.routes import register_routes

UPLOAD_HEADER = "X-Requested-With"
UPLOAD_HEADER_VALUE = "panel"
UPLOAD_PATH_RE = re.compile(r"/api/(deck|categories/[^/]+)/upload")
STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def create_app(container=None):
    if container is None:
        container = build_container()
    app = Flask(__name__, static_folder=config.STATIC_DIR, template_folder=config.TEMPLATES_DIR)
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_SOUND_BYTES + 64 * 1024  # plus multipart overhead
    app.extensions["container"] = container
    app.before_request(require_json_for_state_changes)
    app.register_error_handler(Exception, handle_unexpected)
    app.register_error_handler(RequestEntityTooLarge, handle_too_large)
    app.register_error_handler(FutureTimeoutError, handle_timeout)
    register_routes(app)
    return app


def require_json_for_state_changes():
    # CSRF protection: HTML forms cannot send application/json, and a cross-site
    # fetch with this content type needs a CORS preflight, which this app never allows.
    if request.method in STATE_CHANGING_METHODS and not request.is_json:
        # The only exception is the sound upload: a cross-site form cannot send this custom header,
        # and a cross-site fetch that tries it needs a CORS preflight, which this app never allows.
        is_upload = (UPLOAD_PATH_RE.fullmatch(request.path) and request.mimetype == "multipart/form-data"
                     and request.headers.get(UPLOAD_HEADER) == UPLOAD_HEADER_VALUE)
        if not is_upload:
            return jsonify({"ok": False, "message": "Content-Type must be application/json"}), 415
    return None


def handle_unexpected(error):
    # Keep the panel's JSON contract: it shows the message instead of a generic network error.
    if isinstance(error, HTTPException):
        return error
    current_app.logger.exception("Unexpected error")
    return jsonify({"ok": False, "message": f"Server error: {error}"}), 500


def handle_too_large(_error):
    return jsonify({"ok": False, "message": f"File is too large (max {config.MAX_SOUND_BYTES // (1024 * 1024)} MB)"}), 413


def handle_timeout(_error):
    return jsonify({"ok": False, "message": "Bot did not respond in time"}), 504
