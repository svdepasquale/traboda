"""The music queue behind the Walkman: lives in the system, so playback goes on while
other apps run and the transport keys work from anywhere."""

import os
import random

from . import settings

EXTS = (".wav",)


def list_tracks(folder):
    """Audio files under folder (one level of sub-folders), sorted by path."""
    out = []
    try:
        entries = sorted(os.listdir(folder))
    except OSError:
        return out
    for name in entries:
        path = folder.rstrip("/") + "/" + name
        try:
            is_dir = os.stat(path)[0] & 0x4000
        except OSError:
            continue
        if is_dir:
            try:
                for sub in sorted(os.listdir(path)):
                    if sub.lower().endswith(EXTS) and not sub.startswith("."):
                        out.append(path + "/" + sub)
            except OSError:
                pass
        elif name.lower().endswith(EXTS) and not name.startswith("."):
            out.append(path)
    return out


def title_of(path):
    name = path.rsplit("/", 1)[-1]
    name = name.rsplit(".", 1)[0]
    return name.replace("_", " ")


class Player:
    def __init__(self, audio):
        self.audio = audio
        self.queue = []
        self.index = -1
        self.shuffle = settings.get("shuffle")
        self.repeat = settings.get("repeat")

    @property
    def loaded(self):
        return 0 <= self.index < len(self.queue)

    @property
    def current(self):
        return self.queue[self.index] if self.loaded else None

    def load(self, tracks, start=0):
        self.queue = list(tracks)
        self.index = start if self.queue else -1
        if self.loaded:
            self.audio.play(self.current)

    def play_pause(self):
        if not self.loaded:
            return
        if self.audio.playing:
            self.audio.toggle()
        else:
            self.audio.play(self.current)

    def next(self, auto=False):
        if not self.queue:
            return
        if self.shuffle and len(self.queue) > 1:
            i = self.index
            while i == self.index:
                i = random.randrange(len(self.queue))
            self.index = i
        elif self.index + 1 < len(self.queue):
            self.index += 1
        elif self.repeat or not auto:
            self.index = 0
        else:
            self.audio.stop()
            return
        self.audio.play(self.current)

    def prev(self):
        if not self.queue:
            return
        if self.audio.playing and self.audio.elapsed > 3:
            self.audio.play(self.current)          # restart the track, like a tape deck
            return
        self.index = (self.index - 1) % len(self.queue)
        self.audio.play(self.current)

    def stop(self):
        self.audio.stop()

    def tick(self):
        """Advances when a track ends by itself; call a few times a second."""
        if self.audio.ended and self.loaded:
            self.audio.ended = False
            self.next(auto=True)
