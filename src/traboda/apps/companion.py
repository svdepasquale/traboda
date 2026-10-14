"""Companion: the Mac's CPU, memory, battery and music, pushed over USB by
tools/companion.py (see sys.hostlink). While it is open the LEDs fill with the CPU load,
and the screen stays on as long as the Mac keeps sending."""

import time
from array import array

from .. import buttons as B
from .. import gfx, icons, settings, ui
from ..display import rgb
from ..leds import COLS, N, hsv

TITLE = "Companion"
ICON = "home"
MEDIA_KEYS = False

STALE_MS = 10000
SAMPLES = 60
SPARK_X = 114
SPARK_Y = 60
SPARK_W = 190
SPARK_H = 62
SPARK_BG = rgb(16, 19, 34)
GRID = rgb(34, 40, 64)
GRAD = tuple(hsv(0.33 - 0.33 * c / (COLS - 1)) for c in range(COLS))   # LED columns
BOLT = array("h", (6, 0, 1, 7, 4, 7, 3, 12, 8, 5, 5, 5, 7, 0))

icons.register("c_mac", (
    "................",
    "................",
    "..llllllllllll..",
    "..lnnnnnnnnnnl..",
    "..lnBBBBnnnnnl..",
    "..lnnnnnnnnnnl..",
    "..lnnPPPPPnnnl..",
    "..lnnnnnnnnnnl..",
    "..lnGGGnnnnnnl..",
    "..lnnnnnnnnnnl..",
    "..llllllllllll..",
    ".llllllllllllll.",
    "lllllllddlllllll",
    ".dddddddddddddd.",
    "................",
    "................",
))


def _pct(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return max(0, min(100, int(v + 0.5)))


def _str(v):
    return v[:80] if isinstance(v, str) else ""


def _load_color(pct):
    return ui.GREEN if pct < 50 else ui.YELLOW if pct < 80 else ui.RED


# -- LEDs ----------------------------------------------------------------------------------

def _leds_cpu(sys, cpu):
    """Both rows fill left to right with the load, green to red, unless the user turned
    the LEDs off."""
    leds = sys.leds
    if not leds or not settings.get("leds_on"):
        return
    if leds.effect != "custom":
        leds.set_effect("custom")
    lit = cpu * COLS / 100
    full = int(lit)
    frame = []
    for pos in range(N):
        c = pos % COLS
        if c < full:
            frame.append(GRAD[c])
        elif c == full and lit > full:
            f = lit - full
            g = GRAD[c]
            frame.append((int(g[0] * f), int(g[1] * f), int(g[2] * f)))
        else:
            frame.append((0, 0, 0))
    leds.frame = frame


def _leds_restore(sys):
    if sys.leds:
        sys.leds.set_effect(settings.get("led_effect") if settings.get("leds_on") else "off")


# -- dashboard -----------------------------------------------------------------------------

def _frame(sys):
    ui.header(sys, TITLE, ICON)
    gfx.round_rect(8, 54, 304, 74, 8, ui.PANEL)
    gfx.text("CPU", 18, 58, ui.DIM)
    gfx.round_rect(8, 134, 148, 40, 8, ui.PANEL)
    gfx.text("RAM", 18, 137, ui.DIM)
    gfx.round_rect(164, 134, 148, 40, 8, ui.PANEL)
    gfx.text("Batteria", 174, 137, ui.DIM)
    gfx.round_rect(8, 180, 304, 38, 8, ui.PANEL)
    icons.draw(gfx.fb, "music", 16, 191, 1)
    ui.footer([("B", "Indietro")])


def _draw_head(host, clock):
    gfx.fill_rect(146, ui.STATUS_H + 1, 166, 26, ui.BG)
    x = 310
    if clock:
        x -= gfx.text(clock, x, 22, ui.CYAN, align=-1) + 8
    if host:
        gfx.text(gfx.ellipsize(host, x - 150, "small"), x, 25, ui.DIM, "small", align=-1)


def _draw_cpu(cpu, hist, count):
    gfx.fill_rect(14, 76, 96, 48, ui.PANEL)
    if cpu is None:
        gfx.text("--", 18, 78, ui.DIM, "large")
    else:
        gfx.text("%d%%" % cpu, 18, 78, _load_color(cpu), "large")
        gfx.bar(18, 114, 88, 8, cpu / 100, _load_color(cpu), ui.PANEL2, 4)
    gfx.round_rect(SPARK_X, SPARK_Y, SPARK_W, SPARK_H, 4, SPARK_BG)
    base = SPARK_Y + SPARK_H - 4
    span = SPARK_H - 8
    gfx.hline(SPARK_X + 4, base - span // 2, SPARK_W - 8, GRID)
    x = SPARK_X + 5 + (SAMPLES - count) * 3
    for i in range(SAMPLES - count, SAMPLES):
        v = hist[i]
        h = max(1, v * span // 100)
        gfx.fill_rect(x, base - h + 1, 2, h, _load_color(v))
        x += 3


def _draw_ram(ram):
    gfx.fill_rect(60, 136, 92, 16, ui.PANEL)
    gfx.fill_rect(18, 156, 128, 10, ui.PANEL)
    if ram is None:
        gfx.text("--", 146, 137, ui.DIM, align=-1)
        return
    gfx.text("%d%%" % ram, 146, 137, ui.TEXT, align=-1)
    gfx.bar(18, 157, 128, 8, ram / 100, _load_color(ram), ui.PANEL2, 4)


def _draw_batt(batt, charging, ac):
    gfx.fill_rect(240, 136, 66, 16, ui.PANEL)
    gfx.fill_rect(174, 156, 128, 10, ui.PANEL)
    if batt is None:
        gfx.text("rete" if ac else "--", 302, 137, ui.DIM, align=-1)
        return
    color = ui.GREEN if batt > 30 else ui.YELLOW if batt > 12 else ui.RED
    w = gfx.text("%d%%" % batt, 302, 137, ui.TEXT, align=-1)
    if charging:
        gfx.fb.poly(302 - w - 14, 138, BOLT, ui.YELLOW, True)
    gfx.bar(174, 157, 128, 8, batt / 100, color, ui.PANEL2, 4)


def _draw_music(track, artist, app, playing):
    gfx.fill_rect(36, 182, 272, 34, ui.PANEL)
    if not track:
        gfx.text("Niente in riproduzione", 38, 191, ui.DIM)
        return
    line = track + (" - " + artist if artist else "")
    gfx.text(gfx.ellipsize(line, 266), 38, 183, ui.TEXT)
    state = (app + " · " if app else "") + ("in riproduzione" if playing else "in pausa")
    gfx.text(gfx.ellipsize(state, 266, "small"), 38, 202, ui.DIM, "small")


def _update(s, hist, count, seq, shown):
    """Redraws the values that changed; returns the bands to push."""
    bands = []
    parts = (
        ("head", (_str(s.get("host")), _str(s.get("time"))[:5]), _draw_head, (18, 46)),
        ("cpu", (_pct(s.get("cpu")), seq), None, (54, 128)),
        ("ram", (_pct(s.get("ram")),), _draw_ram, (134, 174)),
        ("batt", (_pct(s.get("batt")), bool(s.get("charging")), bool(s.get("ac"))), _draw_batt,
         (134, 174)),
        ("music", (_str(s.get("track")), _str(s.get("artist")), _str(s.get("app")),
                   bool(s.get("playing"))), _draw_music, (180, 218)),
    )
    for name, key, draw, band in parts:
        if shown.get(name) == key:
            continue
        shown[name] = key
        if draw:
            draw(*key)
        else:
            _draw_cpu(key[0], hist, count)
        if band not in bands:
            bands.append(band)
    return bands


# -- waiting -------------------------------------------------------------------------------

def _wait_frame(sys):
    ui.header(sys, TITLE, ICON)
    icons.draw(gfx.fb, "c_mac", 136, 54, 3)
    gfx.text("In attesa del Mac", 160, 104, ui.TEXT, "title", align=1)
    gfx.text("Collega il badge al Mac via USB e", 160, 136, ui.DIM, align=1)
    gfx.text("dalla cartella traboda avvia:", 160, 154, ui.DIM, align=1)
    gfx.round_rect(36, 176, 248, 22, 6, ui.PANEL2)
    gfx.text("python3 tools/companion.py", 160, 179, ui.CYAN, align=1)
    ui.footer([("B", "Indietro")])


def _draw_age(age_s):
    gfx.fill_rect(0, 202, 320, 14, ui.BG)
    if age_s is not None:
        text = "ultimo dato %d s fa" % age_s if age_s < 120 else "ultimo dato %d min fa" % (age_s // 60)
        gfx.text(text, 160, 203, ui.DIM, "small", align=1)


# -- entry ---------------------------------------------------------------------------------

async def main(sys):
    link = sys.hostlink
    hist = bytearray(SAMPLES)       # CPU %, oldest first
    count = seq = 0
    seen = None                     # stats_at of the last sample taken
    mode = None
    shown = {}
    try:
        while True:
            s = link.stats
            age = time.ticks_diff(time.ticks_ms(), link.stats_at)
            fresh = isinstance(s, dict) and 0 <= age < STALE_MS
            if fresh and link.stats_at != seen:
                seen = link.stats_at
                cpu = _pct(s.get("cpu")) or 0
                hist[:-1] = hist[1:]
                hist[-1] = cpu
                count = min(SAMPLES, count + 1)
                seq += 1
                _leds_cpu(sys, cpu)
                if mode != "data" and not sys.screen_on:
                    sys.wake_screen()               # the Mac has just connected
                sys.buttons.last_activity = time.ticks_ms()     # a live dashboard stays lit
            full = mode != ("data" if fresh else "wait")
            if full:
                mode = "data" if fresh else "wait"
                shown = {}
                if fresh:
                    _frame(sys)
                else:
                    _leds_restore(sys)
                    _wait_frame(sys)
            if fresh:
                bands = _update(s, hist, count, seq, shown)
            else:
                age_s = max(0, age) // 1000 if isinstance(s, dict) else None
                bands = [] if shown.get("age") == age_s else [(202, 216)]
                shown["age"] = age_s
                if bands or full:
                    _draw_age(age_s)
            status = (sys.clock_text(), sys.battery, sys.charging, sys.wifi_connected(),
                      sys.audio.playing, sys.audio.paused)
            if status != shown.get("status"):
                shown["status"] = status
                if not full:
                    ui.statusbar(sys)
                    bands.append((0, ui.STATUS_H))
            if full:
                sys.show()
            else:
                for y0, y1 in bands:
                    sys.show(y0, y1)
            ev = await sys.event(timeout_ms=500)
            if ev is None:
                continue
            if B.kind(ev) == sys.REDRAW:
                mode = None
            elif sys.is_back(ev):
                return
    finally:
        _leds_restore(sys)
