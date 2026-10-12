"""Weather: the Open-Meteo forecast (no key) for an Italian city, drawn glyphs and a
three-day row. The last answer is cached on flash and shown, marked as old, offline."""

import json
import time
from array import array

from .. import buttons as B
from .. import gfx, net, paths, settings, tz, ui
from ..display import W, rgb

TITLE = "Meteo"
ICON = "weather"
MEDIA_KEYS = False

URL = ("https://api.open-meteo.com/v1/forecast?latitude=%.2f&longitude=%.2f"
       "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,"
       "wind_speed_10m,is_day&daily=weather_code,temperature_2m_max,temperature_2m_min,"
       "precipitation_probability_max&timezone=auto&forecast_days=4")
STALE_S = 30 * 60
RETRY_MS = 5 * 60 * 1000

CITIES = (
    ("Roma", 41.89, 12.49), ("Milano", 45.46, 9.19), ("Napoli", 40.85, 14.27),
    ("Torino", 45.07, 7.69), ("Palermo", 38.12, 13.36), ("Genova", 44.41, 8.93),
    ("Bologna", 44.49, 11.34), ("Firenze", 43.77, 11.25), ("Bari", 41.12, 16.87),
    ("Venezia", 45.44, 12.33), ("Verona", 45.44, 10.99), ("Cagliari", 39.22, 9.12),
)

# WMO weather codes: the first row whose upper bound holds the code wins
_WMO = ((0, "clear", "Sereno"), (2, "partly", "Poco nuvoloso"), (3, "cloudy", "Nuvoloso"),
        (48, "fog", "Nebbia"), (57, "drizzle", "Pioggerella"), (67, "rain", "Pioggia"),
        (77, "snow", "Neve"), (82, "showers", "Rovesci"), (86, "snow", "Neve"),
        (99, "storm", "Temporale"))

SUN = ui.YELLOW
SUN_CORE = rgb(255, 240, 160)
RAY = rgb(255, 168, 36)
MOON = rgb(240, 234, 200)
CLOUD = rgb(226, 231, 244)
CLOUD_SHADE = rgb(132, 142, 176)
GREY = rgb(160, 168, 196)
GREY_SHADE = rgb(88, 96, 130)
RAIN = rgb(80, 168, 255)
FOG = rgb(150, 158, 188)

_RAYS = ((10, 0), (7, 7), (0, 10), (-7, 7), (-10, 0), (-7, -7), (0, -10), (7, -7))
_BOLT = (17, 14, 22, 14, 18, 21, 22, 21, 13, 31, 16, 23, 12, 23)    # half units of 16


def _wmo(code):
    if code is not None:
        for top, kind, text in _WMO:
            if code <= top:
                return kind, text
    return "cloudy", "--"


def _r(v):
    return int(v + 0.5) if v >= 0 else -int(0.5 - v)


def _fmt(f, v):
    """f with v rounded; "--" for the nulls Open-Meteo sends when a value is missing."""
    return "--" if v is None else f % _r(v)


def _weekday(y, m, d):
    """Monday = 0 (Sakamoto's method)."""
    if m < 3:
        y -= 1
    return (y + y // 4 - y // 100 + y // 400 + (0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4)[m - 1]
            + d + 6) % 7


# -- glyphs: gfx shapes in a box of s x s pixels, s a multiple of 16 --------------------

def _sun(cx, cy, r):
    a = r + max(2, r // 3)
    b = a + max(3, r * 2 // 3)
    for dx, dy in _RAYS:
        x0, y0 = cx + int(dx * a / 10), cy + int(dy * a / 10)
        x1, y1 = cx + int(dx * b / 10), cy + int(dy * b / 10)
        gfx.line(x0, y0, x1, y1, RAY)
        gfx.line(x0 + 1, y0, x1 + 1, y1, RAY)
        gfx.line(x0, y0 + 1, x1, y1 + 1, RAY)
    gfx.circle(cx, cy, r, SUN, True)
    gfx.circle(cx - r // 4, cy - r // 4, r // 2, SUN_CORE, True)


def _star(x, y, k):
    gfx.hline(x - k, y, 2 * k + 1, MOON)
    gfx.vline(x, y - k, 2 * k + 1, MOON)


def _moon(cx, cy, r, bg):
    gfx.circle(cx, cy, r, MOON, True)
    gfx.circle(cx + r * 45 // 100, cy - r * 35 // 100, r * 78 // 100, bg, True)


def _blob(x, y, w, h, c):
    bh = h * 55 // 100
    gfx.round_rect(x, y + h - bh, w, bh, bh // 2, c)
    gfx.circle(x + w * 30 // 100, y + h * 56 // 100, h * 30 // 100, c, True)
    gfx.circle(x + w * 57 // 100, y + h * 42 // 100, h * 42 // 100, c, True)
    gfx.circle(x + w * 80 // 100, y + h * 62 // 100, h * 26 // 100, c, True)


def _cloud(x, y, w, h, c, shade):
    d = max(1, h // 12)
    _blob(x + d, y + d, w, h, shade)
    _blob(x, y, w, h, c)


def _drops(x, y, u, short):
    for i in range(3):
        dx = x + (4 + 4 * i) * u
        if short:
            for j in (0, 2):
                yy = y + j * u + (u if i == 1 else 0)
                gfx.fill_rect(dx - j * u // 2, yy, max(2, u // 2 + 1), u, RAIN)
        else:
            gfx.line(dx + u, y, dx - u, y + 3 * u, RAIN)
            gfx.line(dx + u + 1, y, dx - u + 1, y + 3 * u, RAIN)


def _flakes(x, y, u):
    k = max(2, u + u // 2)
    for i in range(3):
        cx = x + (4 + 4 * i) * u
        cy = y + (u if i == 1 else 0)
        gfx.hline(cx - k, cy, 2 * k + 1, ui.WHITE)
        gfx.line(cx - k // 2, cy - k, cx + k // 2, cy + k, ui.WHITE)
        gfx.line(cx + k // 2, cy - k, cx - k // 2, cy + k, ui.WHITE)


def _glyph(kind, night, x, y, s, bg):
    u = s // 16
    if kind == "clear":
        if night:
            _moon(x + 7 * u, y + 8 * u, 6 * u, bg)
            _star(x + 13 * u, y + 3 * u, max(1, u // 2 + 1))
            _star(x + 11 * u, y + 9 * u, max(1, u // 2))
        else:
            _sun(x + 8 * u, y + 8 * u, 4 * u)
        return
    if kind == "fog":
        for i, (fx, fw) in enumerate(((2, 12), (1, 11), (3, 12), (2, 10))):
            h = max(2, u * 3 // 2)
            gfx.round_rect(x + fx * u, y + (3 + 3 * i) * u, fw * u, h, h // 2, FOG)
        return
    if kind in ("partly", "showers"):
        if night:
            _moon(x + 6 * u, y + 5 * u, 4 * u, bg)
        else:
            _sun(x + 6 * u, y + 5 * u, 3 * u)
    if kind == "partly":
        _cloud(x + 4 * u, y + 7 * u, 11 * u, 7 * u, CLOUD, CLOUD_SHADE)
        return
    if kind == "cloudy":
        _cloud(x + u, y + 2 * u, 10 * u, 6 * u, GREY, GREY_SHADE)
        _cloud(x + 4 * u, y + 6 * u, 11 * u, 7 * u, CLOUD, CLOUD_SHADE)
        return
    if kind == "showers":
        _cloud(x + 3 * u, y + 4 * u, 12 * u, 7 * u, GREY, GREY_SHADE)
        _drops(x, y + 12 * u, u, False)
        return
    if kind == "snow":
        _cloud(x + u, y + u, 14 * u, 8 * u, CLOUD, CLOUD_SHADE)
        _flakes(x, y + 12 * u, u)
        return
    _cloud(x + u, y + u, 14 * u, 8 * u, GREY if kind != "storm" else GREY_SHADE,
           GREY_SHADE if kind != "storm" else rgb(54, 60, 88))
    if kind == "storm":
        gfx.fb.poly(x, y, array("h", [v * u // 2 for v in _BOLT]), SUN, True)
    else:
        _drops(x, y + 11 * u, u, kind == "drizzle")


def _drop(x, y):
    gfx.line(x + 2, y, x, y + 4, RAIN)
    gfx.line(x + 2, y, x + 4, y + 4, RAIN)
    gfx.circle(x + 2, y + 6, 2, RAIN, True)


# -- data ----------------------------------------------------------------------------------

def _valid(data):
    try:
        cur, day = data["current"], data["daily"]
        for k in ("temperature_2m", "apparent_temperature", "relative_humidity_2m",
                  "weather_code", "wind_speed_10m"):
            cur[k]
        if len(cur["time"]) < 16:
            return False
        for k in ("time", "weather_code", "temperature_2m_max", "temperature_2m_min",
                  "precipitation_probability_max"):
            if len(day[k]) < 4:
                return False
        for d in day["time"][:4]:
            _weekday(int(d[:4]), int(d[5:7]), int(d[8:10]))
        return True
    except (KeyError, TypeError, ValueError, IndexError):
        return False


def _place():
    """The saved city, or the default one if the setting is not a usable place."""
    p = settings.get("weather")
    try:
        if p["name"] and -90 <= p["lat"] <= 90 and -180 <= p["lon"] <= 180:
            return p
    except (KeyError, TypeError):
        pass
    return dict(settings.DEFAULTS["weather"])


def _load(place):
    try:
        with open(paths.data("weather.json")) as f:
            c = json.load(f)
        if c["name"] == place["name"] and isinstance(c["ts"], (int, float)) \
                and _valid(c["data"]):
            return c
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def _age(cache):
    """Seconds since the answer was fetched, or None when the clock cannot tell."""
    if not tz.clock_valid():
        return None
    a = time.time() - cache["ts"]
    return a if 0 <= a < 400 * 86400 else None


def _ago(s):
    if s < 3600:
        return "%d min fa" % max(1, s // 60)
    if s < 7200:
        return "1 ora fa"
    if s < 2 * 86400:
        return "%d ore fa" % (s // 3600)
    return "%d giorni fa" % (s // 86400)


def _fetch(place):
    """Blocking GET; returns (cache, None) or (None, error text)."""
    try:
        d = net.get_json(URL % (place["lat"], place["lon"]))
        data = {"current": d["current"], "daily": d["daily"]}
    except Exception as e:  # noqa: BLE001 - HTTP, DNS, TLS and JSON errors alike
        return None, "Server meteo non raggiungibile (%s)." % (e.args[0] if e.args else
                                                              type(e).__name__)
    if not _valid(data):
        return None, "Risposta del server meteo non valida."
    c = {"ts": time.time(), "name": place["name"], "data": data}
    try:
        with open(paths.data("weather.json"), "w") as f:
            json.dump(c, f)
    except OSError:
        pass
    return c, None


# -- screens -------------------------------------------------------------------------------

def _header(sys, place, cache):
    ui.header(sys, place["name"], ICON)
    if not cache:
        return
    age = _age(cache)
    hm = cache["data"]["current"]["time"][11:16]
    if net.connected() and age is not None and age <= STALE_S:
        gfx.text("agg. " + hm, W - 10, 24, ui.DIM, align=-1)
    else:
        when = _ago(age) if age is not None else "delle " + hm
        gfx.text(("offline · " if not net.connected() else "vecchi · ") + when, W - 10, 24,
                 ui.ORANGE, align=-1)


def _day_card(x, y, day, i):
    gfx.round_rect(x, y, 100, 66, 8, ui.PANEL)
    date = day["time"][i]
    dd = int(date[8:10])
    wd = _weekday(int(date[:4]), int(date[5:7]), dd)
    gfx.text("%s %d" % (tz.DAYS[wd], dd), x + 50, y + 4, ui.TEXT, align=1)
    _glyph(_wmo(day["weather_code"][i])[0], False, x + 6, y + 26, 32, ui.PANEL)
    hi = _fmt("%d°", day["temperature_2m_max"][i])
    lo = _fmt("%d°", day["temperature_2m_min"][i])
    f = "text" if len(hi) + len(lo) <= 6 else "small"
    gfx.text(hi, x + 44, y + 24, ui.TEXT, f)
    gfx.text(lo, x + 96, y + 24, ui.DIM, f, align=-1)
    _drop(x + 45, y + 44)
    gfx.text(_fmt("%d%%", day["precipitation_probability_max"][i]), x + 54, y + 45, RAIN,
             "small")


def _draw_data(cache):
    cur, day = cache["data"]["current"], cache["data"]["daily"]
    kind, text = _wmo(cur["weather_code"])
    _glyph(kind, cur.get("is_day") == 0, 10, 56, 64, ui.BG)
    t = _fmt("%d°", cur["temperature_2m"])
    if len(t) <= 3:
        gfx.text(t, 84, 54, ui.TEXT, "huge")
    else:
        gfx.text(t, 84, 70, ui.TEXT, "large")
    gfx.text(text, 86, 124, ui.CYAN)
    gfx.text("↑%s ↓%s" % (_fmt("%d°", day["temperature_2m_max"][0]),
                          _fmt("%d°", day["temperature_2m_min"][0])), 42, 124, ui.DIM, align=1)
    gfx.vline(198, 60, 84, ui.LINE)
    rows = (("Percepita", _fmt("%d°", cur["apparent_temperature"])),
            ("Umidità", _fmt("%d%%", cur["relative_humidity_2m"])),
            ("Vento", _fmt("%d km/h", cur["wind_speed_10m"])))
    for i, (label, value) in enumerate(rows):
        gfx.text(label, 210, 56 + 30 * i, ui.DIM, "small")
        gfx.text(value, 210, 68 + 30 * i, ui.TEXT)
    for i in range(3):
        _day_card(6 + 104 * i, 150, day, i + 1)


def _draw_message(icon_kind, title, lines, color):
    if icon_kind in ("wifi", "nowifi"):
        gfx.circle(W // 2, 92, 26, ui.PANEL, True)
        for i, h in enumerate((6, 11, 16, 21)):
            gfx.fill_rect(W // 2 - 15 + 8 * i, 104 - h, 6, h,
                          ui.CYAN if icon_kind == "wifi" else ui.LINE)
        if icon_kind == "nowifi":
            for d in range(3):
                gfx.line(W // 2 - 18 + d, 74, W // 2 + 16 + d, 110, ui.RED)
    else:
        _glyph(icon_kind, False, W // 2 - 32, 60, 64, ui.BG)
    gfx.text(title, W // 2, 132, color, "title", align=1)
    for i, line in enumerate(lines[:3]):
        gfx.text(line, W // 2, 162 + 17 * i, ui.DIM, align=1)


def _draw(sys, place, cache, err):
    _header(sys, place, cache)
    if cache:
        _draw_data(cache)
        ui.footer([("A", "Aggiorna" if net.connected() else "Wi-Fi"), ("▼", "Città"),
                   ("A tieni", "Indietro")])
    elif net.connected() and not err:
        _draw_message("partly", "Scarico le previsioni…", [place["name"]], ui.TEXT)
        ui.footer([])
    elif net.connected():
        _draw_message("cloudy", "Meteo non disponibile", gfx.wrap(err, 296), ui.ORANGE)
        ui.footer([("A", "Riprova"), ("▼", "Città"), ("A tieni", "Indietro")])
    elif net.status in ("scanning", "connecting"):
        _draw_message("wifi", "Connessione Wi-Fi…",
                      [gfx.ellipsize((net.ssid or "") if net.status == "connecting" else
                                     "ricerca delle reti salvate", 296)], ui.TEXT)
        ui.footer([("A", "Wi-Fi"), ("▼", "Città"), ("A tieni", "Indietro")])
    else:
        _draw_message("nowifi", "Serve il Wi-Fi",
                      gfx.wrap("Collegati a una rete per scaricare le previsioni di %s."
                               % place["name"], 296), ui.TEXT)
        ui.footer([("A", "Apri Wi-Fi"), ("▼", "Città"), ("A tieni", "Indietro")])


class _Nav:
    """The System as the ui widgets see it, noting HOME so that nested screens all leave."""

    def __init__(self, sys):
        self.sys = sys
        self.home = False

    def __getattr__(self, name):
        return getattr(self.sys, name)

    async def event(self, timeout_ms=None):
        ev = await self.sys.event(timeout_ms)
        if ev is not None and B.kind(ev) == self.sys.HOME:
            self.home = True
        return ev


async def _toast(nav, msg, ms):
    """ui.toast, but the key that cuts it short is used up to its release instead of also
    acting on the screen underneath."""
    ui.toast_draw(msg)
    nav.show()
    if not await nav.sleep_ms(ms, interruptible=True):
        return
    k = None
    held = False
    while True:
        ev = await nav.event(timeout_ms=1000)
        if ev is None or B.kind(ev) == nav.HOME:
            return
        kind = B.kind(ev)
        if kind == nav.REDRAW:
            continue
        if k is None:
            if kind == B.PRESS:
                k = B.key(ev)
        elif B.key(ev) == k:
            if kind == B.LONG:
                held = True
            elif kind == B.CLICK or (kind == B.RELEASE and held):
                return


async def _pick_city(nav, place):
    names = [c[0] for c in CITIES]
    items = [ui.Item(n, "✓" if n == place["name"] else None, tag=i) for i, n in enumerate(names)]
    it = await ui.menu(nav, "Città", items, icon=ICON,
                       sel=names.index(place["name"]) if place["name"] in names else 0,
                       hints=[("A", "Scegli"), ("A tieni", "Indietro")])
    if it is None:
        return None
    name, lat, lon = CITIES[it.tag]
    return {"name": name, "lat": lat, "lon": lon}


def _state(sys):
    """What the screen shows besides the forecast: redraw when it changes."""
    return net.connected(), net.status, sys.clock_text()


async def main(sys):
    nav = _Nav(sys)
    place = _place()
    cache = _load(place)
    err = None
    tried = None            # ticks of the last fetch attempt, to pace retries
    full = True
    force = False           # A pressed: fetch now, whatever the age
    note = None
    seen = None
    while True:
        age = _age(cache) if cache else None
        due = force or age is None or age > STALE_S
        if net.connected() and due and (force or tried is None or
                                        time.ticks_diff(time.ticks_ms(), tried) > RETRY_MS):
            force = False
            _draw(nav, place, cache, None)
            if cache:
                ui.toast_draw("Aggiornamento…")
            nav.show()
            fresh, err = _fetch(place)
            tried = time.ticks_ms()
            if fresh:
                cache = fresh
            elif cache:
                note = "Aggiornamento non riuscito: restano i dati vecchi"
            full = True
        if full:
            _draw(nav, place, cache, err)
            nav.show()
            full = False
            seen = _state(nav)
        if note:
            await _toast(nav, note, 1800)
            note = None
            full = True
            if nav.home:
                return
            continue
        ev = await nav.event(timeout_ms=1000)
        if ev is None:
            if _state(nav) != seen:
                full = True
            continue
        k, kind = B.key(ev), B.kind(ev)
        if kind == nav.REDRAW:
            full = True
            continue
        if nav.is_back(ev):
            return
        if kind == B.PRESS and k in (B.DOWN, B.RIGHT):
            new = await _pick_city(nav, place)
            if nav.home:
                return
            if new and new["name"] != place["name"]:
                place = new
                settings.set("weather", place)
                cache = _load(place)
                err = tried = None
            full = True
        elif k == B.A and kind == B.CLICK:
            if net.connected():
                force = True
                continue
            nav.request_app("wifi")
            return
