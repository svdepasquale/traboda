"""Wi-Fi: joins the strongest saved network, keeps the clock on NTP, small HTTP helpers."""

import asyncio
import time

from . import settings

wlan = None
status = "off"          # off, scanning, connecting, connected, failed
ssid = None
last_sync = 0


def _wlan():
    global wlan
    if wlan is None:
        import network
        network.hostname("traboda")
        wlan = network.WLAN(network.WLAN.IF_STA)
    return wlan


def connected():
    return wlan is not None and wlan.isconnected()


def ip():
    return wlan.ifconfig()[0] if connected() else None


def rssi():
    try:
        return wlan.status("rssi") if connected() else None
    except Exception:  # noqa: BLE001 - not every build reports it
        return None


def scan():
    """[(ssid, rssi, channel, secure), ...] strongest first, hidden networks skipped."""
    w = _wlan()
    w.active(True)
    seen = {}
    for entry in w.scan():
        name = entry[0].decode("utf-8", "replace")
        if not name:
            continue
        rssi_ = entry[3]
        if name not in seen or seen[name][1] < rssi_:
            seen[name] = (name, rssi_, entry[2], entry[4] != 0)
    return sorted(seen.values(), key=lambda e: -e[1])


async def connect(name, password, timeout_ms=15000):
    global status, ssid
    w = _wlan()
    w.active(True)
    if w.isconnected():
        w.disconnect()
    status = "connecting"
    ssid = name
    w.connect(name, password)
    t0 = time.ticks_ms()
    while not w.isconnected():
        if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
            status = "failed"
            w.disconnect()
            return False
        await asyncio.sleep_ms(200)
    status = "connected"
    return True


async def auto_connect():
    """Tries the saved networks, strongest first. Returns True when connected."""
    global status
    saved = {n: p for n, p in settings.get("wifi")}
    if not saved:
        status = "off"
        return False
    status = "scanning"
    try:
        found = scan()
    except OSError:
        status = "failed"
        return False
    for name, _rssi, _ch, _sec in found:
        if name in saved and await connect(name, saved[name]):
            return True
    status = "failed"
    return False


def disable():
    global status
    if wlan:
        wlan.disconnect()
        wlan.active(False)
    status = "off"


def sync_time():
    """Sets the RTC from NTP. Returns True on success."""
    global last_sync
    try:
        import ntptime
        ntptime.host = "pool.ntp.org"
        ntptime.settime()
        last_sync = time.time()
        return True
    except Exception:  # noqa: BLE001 - network errors of every kind
        return False


def remember(name, password):
    nets = [n for n in settings.get("wifi") if n[0] != name]
    nets.insert(0, [name, password])
    settings.set("wifi", nets[:8])


def forget(name):
    settings.set("wifi", [n for n in settings.get("wifi") if n[0] != name])


def get_json(url, timeout=10):
    """GET url and parse JSON (blocking; call from a screen that shows it is loading)."""
    import requests
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "traboda-badge"})
    try:
        if r.status_code != 200:
            raise OSError("HTTP %d" % r.status_code)
        return r.json()
    finally:
        r.close()
