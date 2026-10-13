"""Fake Wi-Fi: a few networks; connecting to any of them succeeds after a moment."""

import time

STAT_IDLE = 0
STAT_CONNECTING = 1
STAT_GOT_IP = 1010
AUTH_OPEN = 0
AUTH_WPA2_PSK = 3

_NETS = (
    (b"CasaMia", b"\x11\x22\x33\x44\x55\x66", 6, -48, 3, False),
    (b"FRITZ!Box 7590", b"\x11\x22\x33\x44\x55\x67", 1, -61, 3, False),
    (b"RomHackCamp", b"\x11\x22\x33\x44\x55\x68", 11, -70, 0, False),
    (b"Vodafone-WiFi", b"\x11\x22\x33\x44\x55\x69", 6, -79, 3, False),
    (b"iPhone di Marco", b"\x11\x22\x33\x44\x55\x6a", 1, -84, 3, False),
)
_hostname = "esp32"


def hostname(name=None):
    global _hostname
    if name is None:
        return _hostname
    _hostname = name


class WLAN:
    IF_STA = 0
    IF_AP = 1

    def __init__(self, iface=0):
        self._active = False
        self._ssid = None
        self._since = 0

    def active(self, v=None):
        if v is None:
            return self._active
        self._active = v
        if not v:
            self._ssid = None

    def scan(self):
        time.sleep_ms(300)
        return list(_NETS)

    def connect(self, ssid, key=None):
        self._ssid = ssid
        self._since = time.ticks_ms()

    def disconnect(self):
        self._ssid = None

    def isconnected(self):
        return self._ssid is not None and time.ticks_diff(time.ticks_ms(), self._since) > 600

    def status(self, what=None):
        if what == "rssi":
            return -52
        return STAT_GOT_IP if self.isconnected() else STAT_IDLE

    def ifconfig(self, *a):
        return ("192.168.178.42", "255.255.255.0", "192.168.178.1", "192.168.178.1")

    def config(self, *a, **k):
        if a and a[0] == "mac":
            return b"\x14\xc1\x9f\xc4\x3d\x4c"
        if a and a[0] == "essid":
            return self._ssid or ""
        return None
