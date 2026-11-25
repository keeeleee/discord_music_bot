UNSET = object()


class SoundboardRepository:
    """Soundboard tiles and their groups."""

    def __init__(self, store):
        self._store = store

    def tiles(self):
        return list(self._store.read().get("deck", []))

    def groups(self):
        return list(self._store.read().get("deck_groups", []))

    def group_colors(self):
        return dict(self._store.read().get("group_colors", {}))

    def group_exists(self, name):
        data = self._store.read()
        return name in data.get("deck_groups", []) or any(t.get("group") == name for t in data.get("deck", []))

    def update_group(self, name, new_name=None, color=UNSET):
        """Renames a group (in the group list and on every tile) and/or sets its colour (None clears it).

        Returns "ok", "missing" or "taken". A rename to the same name is not a clash."""
        def change(data):
            groups = data.get("deck_groups", [])
            tiles = data.get("deck", [])
            exists = name in groups or any(t.get("group") == name for t in tiles)
            if not exists:
                return "missing", False
            target = name
            if new_name is not None and new_name != name:
                taken = new_name in groups or any(t.get("group") == new_name for t in tiles)
                if taken:
                    return "taken", False
                data["deck_groups"] = [new_name if g == name else g for g in groups]
                for tile in tiles:
                    if tile.get("group") == name:
                        tile["group"] = new_name
                colors = data.get("group_colors", {})
                if name in colors:
                    colors[new_name] = colors.pop(name)
                target = new_name
            if color is not UNSET:
                colors = data.setdefault("group_colors", {})
                if color is None:
                    colors.pop(target, None)
                else:
                    colors[target] = color
            return "ok", True

        return self._store.edit(change)

    def add_tile(self, title, url=None, file=None, group=None, color=None):
        tile = {"title": title}
        if group:
            tile["group"] = group
        if color:
            tile["color"] = color
        if file:
            tile["file"] = file
        else:
            tile["url"] = url

        def change(data):
            data.setdefault("deck", []).append(tile)
            return None, True

        self._store.edit(change)

    def add_group(self, name):
        """Returns False if the group already exists."""
        def change(data):
            groups = data.setdefault("deck_groups", [])
            if name in groups:
                return False, False
            groups.append(name)
            return True, True

        return self._store.edit(change)

    def delete_group(self, name):
        """Removes a group and takes it off every tile that had it. Tiles themselves stay."""
        def change(data):
            groups = data.get("deck_groups", [])
            if name in groups:
                groups.remove(name)
            for tile in data.get("deck", []):
                if tile.get("group") == name:
                    tile.pop("group", None)
            data.get("group_colors", {}).pop(name, None)
            return True, True

        return self._store.edit(change)

    def update_tile(self, index, title, url=None):
        """Changes a tile's title, and its link for YouTube tiles (uploaded files keep their file)."""
        def change(data):
            tiles = data.get("deck", [])
            if not 0 <= index < len(tiles):
                return False, False
            tiles[index]["title"] = title
            if url is not None and "file" not in tiles[index]:
                tiles[index]["url"] = url
            return True, True

        return self._store.edit(change)

    def set_tile_field(self, index, field, value):
        """Sets one optional field of a tile ("color", "group"); an empty value removes it."""
        def change(data):
            tiles = data.get("deck", [])
            if not 0 <= index < len(tiles):
                return False, False
            if value:
                tiles[index][field] = value
            else:
                tiles[index].pop(field, None)
            return True, True

        return self._store.edit(change)

    def delete_tile(self, index):
        """Removes a tile and returns it, or None if the index is out of range."""
        def change(data):
            tiles = data.get("deck", [])
            if not 0 <= index < len(tiles):
                return None, False
            return tiles.pop(index), True

        return self._store.edit(change)
