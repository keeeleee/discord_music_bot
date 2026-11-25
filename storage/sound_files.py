import os
import uuid


class SoundFiles:
    """Uploaded audio files, kept under random names in one folder."""

    def __init__(self, directory):
        self.directory = directory

    def path(self, name):
        return os.path.join(self.directory, name)

    def exists(self, name):
        return os.path.exists(self.path(name))

    def save(self, upload, extension):
        stored = uuid.uuid4().hex + extension  # never trust the client's file name on disk
        os.makedirs(self.directory, exist_ok=True)
        upload.save(self.path(stored))
        return stored

    def remove(self, name):
        if name:
            try:
                os.remove(self.path(name))
            except OSError:
                pass
