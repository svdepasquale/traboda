"""Persistent settings in /settings.json; secrets (Wi-Fi passwords) live there too, on the
badge only, never in the repository."""

import json

from . import paths

PATH = None         # resolved from paths.ROOT on first load

DEFAULTS = {
    "nickname": "Traboda",
    "tagline": "RomHack Camp 2026",
    "brightness": 70,
    "volume": 60,
    "speaker": True,
    "clicks": True,
    "led_brightness": 25,
    "led_effect": "rainbow",
    "led_color": [255, 45, 111],
    "leds_on": True,
    "sleep_after": 60,           # seconds of inactivity before the screen turns off, 0 = never
    "tz": "Europe/Rome",         # "Europe/Rome" (EU DST rule) or "UTC+HH:MM"
    "wifi": [],                  # [[ssid, password], ...]
    "wifi_auto": True,
    "weather": {"name": "Roma", "lat": 41.89, "lon": 12.49},
    "music_dir": "music",          # relative: under /sd if a card is in, else flash
    "shuffle": False,
    "repeat": True,
    "scores": {},
}

_data = None
errors = []        # save failures, shown by the system info screen


def _path():
    return PATH or paths.data("settings.json")


def load():
    global _data
    data = json.loads(json.dumps(DEFAULTS))     # deep copy: scores etc. are mutated in place
    try:
        with open(_path()) as f:
            data.update(json.load(f))
    except (OSError, ValueError):
        pass
    _data = data
    return data


def get(key, default=None):
    if _data is None:
        load()
    return _data.get(key, DEFAULTS.get(key, default))


def set(key, value, save_now=True):
    if _data is None:
        load()
    _data[key] = value
    if save_now:
        save()


def save():
    if _data is None:
        return
    import os
    path = _path()
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(_data, f)
        try:
            os.remove(path)
        except OSError:
            pass
        os.rename(tmp, path)
    except OSError as e:          # full or failing flash: keep running on the RAM copy
        errors.append("settings: %s" % e)


def score(game, value=None):
    """Best score for game; records value when it beats it. Returns the best."""
    scores = get("scores")
    best = scores.get(game, 0)
    if value is not None and value > best:
        scores[game] = best = value
        set("scores", scores)
    return best
