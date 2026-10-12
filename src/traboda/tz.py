"""Local time from the UTC RTC: fixed offsets ("UTC+02:00") or Europe/* with the EU
daylight-saving rule (last Sunday of March / October, at 01:00 UTC)."""

import time

_EU = {"Europe/Rome": 60, "Europe/Berlin": 60, "Europe/Paris": 60, "Europe/Madrid": 60,
       "Europe/Amsterdam": 60, "Europe/Vienna": 60, "Europe/Zurich": 60,
       "Europe/London": 0, "Europe/Lisbon": 0, "Europe/Dublin": 0,
       "Europe/Athens": 120, "Europe/Helsinki": 120}

DAYS = ("Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom")
DAYS_LONG = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
MONTHS = ("gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic")
MONTHS_LONG = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
               "agosto", "settembre", "ottobre", "novembre", "dicembre")

zone = "Europe/Rome"


def _last_sunday_utc(year, month):
    """Epoch of 01:00 UTC on the last Sunday of month (March or October: 31 days)."""
    t = time.mktime((year, month, 31, 1, 0, 0, 0, 0))
    weekday = time.gmtime(t)[6]           # Monday = 0
    return t - ((weekday + 1) % 7) * 86400


def offset_minutes(utc=None):
    utc = time.time() if utc is None else utc
    if zone in _EU:
        base = _EU[zone]
        year = time.gmtime(utc)[0]
        if _last_sunday_utc(year, 3) <= utc < _last_sunday_utc(year, 10):
            return base + 60
        return base
    if zone.startswith("UTC") and len(zone) > 3:
        sign = -1 if zone[3] == "-" else 1
        hh, _, mm = zone[4:].partition(":")
        return sign * (int(hh) * 60 + int(mm or 0))
    return 0


def now():
    """Local time tuple: (year, month, mday, hour, minute, second, weekday, yearday)."""
    utc = time.time()
    return time.gmtime(utc + offset_minutes(utc) * 60)


def clock_valid():
    """False until NTP (or the host) has set the RTC."""
    return time.gmtime()[0] >= 2025
