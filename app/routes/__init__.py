from flask import render_template

from app.routes import playback, playlists, soundboard, voice


def index():
    return render_template("index.html")


def favicon():
    # The page uses an inline icon; this only stops browsers from logging 404s.
    return "", 204


def register_routes(app):
    app.add_url_rule("/", "index", index, methods=["GET"])
    app.add_url_rule("/favicon.ico", "favicon", favicon, methods=["GET"])
    for module in (playback, voice, playlists, soundboard):
        app.register_blueprint(module.bp)
