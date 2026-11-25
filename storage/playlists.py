UNSET = object()


class PlaylistRepository:
    """Categories (playlists) and their tracks."""

    def __init__(self, store):
        self._store = store

    def categories(self):
        return self._store.read()["categories"]

    def category_colors(self):
        return dict(self._store.read().get("category_colors", {}))

    def category_exists(self, name):
        return name in self._store.read()["categories"]

    def tracks(self, category):
        return self._store.read()["categories"].get(category, [])

    def add_tracks(self, category, tracks):
        entries = [_entry(track) for track in tracks]

        def change(data):
            data["categories"].setdefault(category, []).extend(entries)
            return None, True

        self._store.edit(change)

    def add_category(self, name):
        def change(data):
            if name in data["categories"]:
                return False, False
            data["categories"][name] = []
            return True, True

        return self._store.edit(change)

    def delete_category(self, name):
        def change(data):
            if name not in data["categories"]:
                return False, False
            del data["categories"][name]
            data.get("category_colors", {}).pop(name, None)
            return True, True

        return self._store.edit(change)

    def update_category(self, name, new_name=None, color=UNSET):
        """Renames a playlist (keeping its place in the order) and/or sets its colour (None clears it).

        Returns "ok", "missing" or "taken". A rename to the same name is not a clash."""
        def change(data):
            categories = data["categories"]
            if name not in categories:
                return "missing", False
            target = name
            if new_name is not None and new_name != name:
                if new_name in categories:
                    return "taken", False
                data["categories"] = {
                    (new_name if key == name else key): tracks for key, tracks in categories.items()
                }
                colors = data.get("category_colors", {})
                if name in colors:
                    colors[new_name] = colors.pop(name)
                target = new_name
            if color is not UNSET:
                colors = data.setdefault("category_colors", {})
                if color is None:
                    colors.pop(target, None)
                else:
                    colors[target] = color
            return "ok", True

        return self._store.edit(change)

    def remove_track(self, category, index):
        def change(data):
            tracks = data["categories"].get(category)
            if tracks is None or not 0 <= index < len(tracks):
                return False, False
            tracks.pop(index)
            return True, True

        return self._store.edit(change)

    def rename_track(self, category, index, title):
        def change(data):
            tracks = data["categories"].get(category)
            if tracks is None or not 0 <= index < len(tracks):
                return False, False
            tracks[index]["title"] = title
            return True, True

        return self._store.edit(change)

    def update_track(self, category, index, url, title):
        def change(data):
            tracks = data["categories"].get(category)
            if tracks is None or not 0 <= index < len(tracks):
                return False, False
            tracks[index] = {"url": url, "title": title}
            return True, True

        return self._store.edit(change)


def _entry(track):
    if track.get("file"):
        return {"file": track["file"], "title": track.get("title") or track["file"]}
    return {"url": track["url"], "title": track.get("title") or track["url"]}
