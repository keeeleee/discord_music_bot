import copy
import json
import os
import threading

DEFAULT_DATA = {
    "categories": {
        "combat_music": [],
        "ambient_music": [],
        "storm_music": []
    }
}


class JsonStore:
    """One JSON file shared by the web panel and the bot. Every access holds the lock."""

    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()

    def read(self):
        with self._lock:
            return self._load()

    def edit(self, change):
        """Calls change(data) under the lock. It returns (result, changed); the file is written only if changed."""
        with self._lock:
            data = self._load()
            result, changed = change(data)
            if changed:
                self._save(data)
            return result

    def _load(self):
        if not os.path.exists(self.path):
            data = copy.deepcopy(DEFAULT_DATA)
            self._save(data)
            return data
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data):
        # Write to a temp file first, so a crash never leaves a half-written playlists.json.
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, self.path)
