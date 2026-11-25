import logging
import threading

from app import create_app
from app.container import build_container
from config import DISCORD_TOKEN, FLASK_HOST, FLASK_PORT, LOG_LEVEL, LOOPBACK_HOSTS

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN is not set in .env file")

container = build_container()
app = create_app(container)

if FLASK_HOST in LOOPBACK_HOSTS:
    # Rejects requests with a foreign Host header (DNS rebinding protection).
    app.config["TRUSTED_HOSTS"] = ["localhost", "127.0.0.1", "[::1]"]


def run_flask():
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print(f"Web UI running at http://localhost:{FLASK_PORT}")
    container.client.run(DISCORD_TOKEN, log_level=logging.getLevelName(LOG_LEVEL))
