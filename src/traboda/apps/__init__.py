"""The app registry: (module, title, icon). The launcher shows them in this order."""

APPS = (
    ("music", "Walkman", "cassette"),
    ("games", "Giochi", "games"),
    ("retro", "Retro-Go", "retro"),
    ("lights", "Luci", "lights"),
    ("clock", "Orologio", "clock"),
    ("badge", "Badge", "badge"),
    ("synth", "Synth", "synth"),
    ("nfc", "NFC", "nfc"),
    ("wifi", "Wi-Fi", "wifi"),
    ("ble", "Bluetooth", "bluetooth"),
    ("weather", "Meteo", "weather"),
    ("companion", "Companion", "home"),
    ("files", "File", "files"),
    ("settings", "Impostazioni", "settings"),
)


def available():
    """The registry minus apps whose module is missing from this build."""
    out = []
    for mod, title, icon in APPS:
        try:
            __import__("traboda.apps." + mod + "_meta")
        except ImportError:
            pass
        out.append((mod, title, icon))
    return out
