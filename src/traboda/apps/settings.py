"""Impostazioni: badge name, screen, audio, LEDs, time, Wi-Fi, a key test, system info,
restart, standby and factory reset. Changes apply at once and are saved on leaving a page."""

import os
import time

from .. import VERSION, gfx, icons, net, paths, settings, tz, ui
from .. import buttons as B

TITLE = "Impostazioni"
ICON = "settings"
MEDIA_KEYS = False

LIST_Y = 52                         # where ui.menu puts its first row
LIST_END = LIST_Y + 6 * ui.ROW_H

SLEEP = (("30 s", 30), ("1 min", 60), ("2 min", 120), ("5 min", 300), ("mai", 0))
ZONES = (tuple("UTC-%02d:00" % h for h in range(12, 0, -1))
         + ("UTC", "Europe/London", "UTC+01:00", "Europe/Rome", "UTC+02:00", "Europe/Athens")
         + tuple("UTC+%02d:00" % h for h in range(3, 15)))
RETRO_PARTS = ("launcher", "retro-core", "prboom-go")
FX_NAMES = {"solid": "Fisso", "breathe": "Respiro", "rainbow": "Arcobaleno", "wave": "Onda",
            "comet": "Cometa", "scanner": "Scanner", "sparkle": "Scintille", "fire": "Fuoco",
            "police": "Polizia", "vu": "VU meter"}           # as the Lights app names them

icons.register("set_screen", (
    "................",
    "................",
    ".llllllllllllll.",
    ".lnnnnnnnnnnnnl.",
    ".lnBBBBBBBBBBnl.",
    ".lnBwwBBBBBBBnl.",
    ".lnBwBBBBBBBBnl.",
    ".lnBBBBBBBBBBnl.",
    ".lnBBBBBBBBBBnl.",
    ".lnBBBBBBBBBBnl.",
    ".lnnnnnnnnnnnnl.",
    ".llllllllllllll.",
    "......dddd......",
    "....dddddddd....",
    "................",
    "................",
))
icons.register("set_speaker", (
    "................",
    "................",
    "........l....B..",
    ".......ll.....B.",
    "......lll..B..B.",
    "..lllllll...B..B",
    "..ldddlll...B..B",
    "..ldddlll...B..B",
    "..ldddlll...B..B",
    "..lllllll...B..B",
    "......lll..B..B.",
    ".......ll.....B.",
    "........l....B..",
    "................",
    "................",
    "................",
))
icons.register("set_reboot", (
    "........G.......",
    "......GGGG......",
    "....GGGGGGG.....",
    "...GGGG.GG......",
    "..GGG...G.......",
    "..GG............",
    ".GGG..........G.",
    ".GG..........GG.",
    ".GG..........GG.",
    ".GGG........GGG.",
    "..GG........GG..",
    "..GGG......GGG..",
    "...GGGG..GGGG...",
    "....GGGGGGGG....",
    "......GGGG......",
    "................",
))
icons.register("set_warn", (
    "................",
    ".......yy.......",
    "......yyyy......",
    "......yyyy......",
    ".....yykkyy.....",
    ".....yykkyy.....",
    "....yyykkyyy....",
    "....yyykkyyy....",
    "...yyyykkyyyy...",
    "...yyyyyyyyyy...",
    "..yyyyykkyyyyy..",
    "..yyyyyyyyyyyy..",
    ".yyyyyyyyyyyyyy.",
    "................",
    "................",
    "................",
))


class _Nav:
    """The System as the ui widgets see it, noting HOME so that nested pages all leave."""

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


async def _toast(nav, msg, ms=1200):
    """ui.toast, but the key that cuts it short is used up to its release instead of also
    acting on the page underneath."""
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


async def main(sys):
    nav = _Nav(sys)
    sel = 0
    while True:
        items = _main_items(sys)
        it = await ui.menu(nav, TITLE, items, icon=ICON, sel=sel,
                           hints=[("A", "Apri"), ("A tieni", "Indietro")])
        if it is None or nav.home:
            return
        sel = items.index(it)
        if it.tag == "wifi":
            sys.request_app("wifi")
            return
        await PAGES[it.tag](nav)
        if nav.home or sys.pending_app():
            return


def _main_items(sys):
    fx = settings.get("led_effect")
    leds = FX_NAMES.get(fx, fx) if settings.get("leds_on") else "spenti"
    wifi = net.ssid if net.connected() else "non connesso"
    return [
        ui.Item("Badge", gfx.ellipsize(settings.get("nickname"), 128), "badge", tag="badge"),
        ui.Item("Schermo", "%d%%" % sys.display.brightness, "set_screen", tag="screen"),
        ui.Item("Audio", "%d%%" % sys.audio.volume, "set_speaker", tag="audio"),
        ui.Item("LED", leds, "lights", tag="leds"),
        ui.Item("Ora", sys.clock_text(), "clock", tag="time"),
        ui.Item("Wi-Fi", gfx.ellipsize(wifi or "", 128), "wifi", tag="wifi"),
        ui.Item("Test tasti", None, "games", tag="keys"),
        ui.Item("Info sistema", "v" + VERSION, "info", tag="info"),
        ui.Item("Riavvia", None, "set_reboot", tag="reboot"),
        ui.Item("Standby", None, "power", tag="standby"),
        ui.Item("Ripristina impostazioni", None, "set_warn", tag="reset"),
    ]


# -- pages built on ui.menu ---------------------------------------------------------------

async def _page(nav, title, icon, items, changed=None, notes=None, card=None, sel=0, hints=None):
    """ui.menu with a note (or a card) under the rows; saves the settings on leaving."""
    dirty = [False]

    def on_change(it):
        dirty[0] = True
        changed(it)

    def on_draw(it):
        y = LIST_Y + len(items) * ui.ROW_H + 6
        if card:
            card(y)
        elif notes and it and it.tag in notes:
            _note(notes[it.tag], y)

    if hints is None:
        hints = [("A tieni", "Indietro")]
        if any(i.kind not in ("slider", "choice") for i in items):
            hints.insert(0, ("A", "Ok"))
        if any(i.kind in ("slider", "choice") for i in items):
            hints.insert(0, ("◄►", "Cambia"))
    try:
        return await ui.menu(nav, title, items, icon=icon, sel=sel, hints=hints,
                             on_change=on_change if changed else None, on_draw=on_draw)
    finally:
        if dirty[0]:
            settings.save()


def _note(text, y):
    lines = gfx.wrap(text, 272)
    n = min(len(lines), (LIST_END - 12 - y) // 16)
    if n <= 0:
        return
    h = 10 + 16 * n
    gfx.round_rect(12, y, 296, h, 8, ui.PANEL)
    gfx.fill_rect(12, y + 7, 3, h - 14, ui.CYAN)
    for i in range(n):
        gfx.text(lines[i], 24, y + 5 + 16 * i, ui.DIM)


async def _badge(nav):
    sel = 0
    while True:
        items = [ui.Item("Nickname", gfx.ellipsize(settings.get("nickname"), 150), "badge", tag="nickname"),
                 ui.Item("Tagline", gfx.ellipsize(settings.get("tagline"), 150), "info", tag="tagline")]
        it = await _page(nav, "Badge", "badge", items, card=_name_card, sel=sel,
                         hints=[("A", "Modifica"), ("A tieni", "Indietro")])
        if it is None or nav.home:
            return
        sel = items.index(it)
        text = await ui.keyboard(nav, it.label, settings.get(it.tag), max_len=16 if sel == 0 else 32)
        if nav.home:
            return
        if text is not None:
            text = text.strip()
            if not text and it.tag == "nickname":
                text = settings.DEFAULTS["nickname"]
            settings.set(it.tag, text)


def _name_card(y):
    h = LIST_END - 4 - y
    gfx.round_rect(12, y, 296, h, 10, ui.PANEL)
    gfx.round_rect(12, y, 296, h, 10, ui.ACCENT, False)
    gfx.text("ANTEPRIMA", 24, y + 8, ui.DIM, "small")
    gfx.text(gfx.ellipsize(settings.get("nickname"), 272, "large"), 160, y + 24, ui.ACCENT, "large", align=1)
    gfx.text(gfx.ellipsize(settings.get("tagline"), 272), 160, y + 62, ui.TEXT, align=1)


async def _screen(nav):
    display = nav.sys.display
    names = [s[0] for s in SLEEP]
    secs = [s[1] for s in SLEEP]
    cur = settings.get("sleep_after")
    if cur not in secs:
        names.append("%d s" % cur)
        secs.append(cur)
    items = [ui.Item("Luminosità", display.brightness, "set_screen", "slider", step=10, lo=5, tag="brightness"),
             ui.Item("Spegnimento automatico", names[secs.index(cur)], "power", "choice", choices=names,
                     tag="sleep_after")]

    def changed(it):
        if it.tag == "brightness":
            display.set_brightness(it.value)
            settings.set("brightness", it.value, False)
        else:
            settings.set("sleep_after", secs[names.index(it.value)], False)

    await _page(nav, "Schermo", "set_screen", items, changed, {
        "brightness": "Si regola anche dal pannello rapido: tieni premuto ►.",
        "sleep_after": "Senza tasti premuti per questo tempo lo schermo si spegne; un tasto lo "
                       "riaccende. La modifica vale dal prossimo riavvio.",
    })


async def _audio(nav):
    audio = nav.sys.audio
    items = [ui.Item("Volume", audio.volume, "set_speaker", "slider", step=5, tag="volume"),
             ui.Item("Altoparlante", audio.speaker_enabled, "set_speaker", "toggle", tag="speaker"),
             ui.Item("Suoni interfaccia", settings.get("clicks"), "music", "toggle", tag="clicks"),
             ui.Item("Suoni giochi", settings.get("game_sounds", True), "games", "toggle", tag="game_sounds")]

    def changed(it):
        settings.set(it.tag, it.value, False)
        if it.tag == "volume":
            audio.set_volume(it.value)
        elif it.tag == "speaker":
            audio.set_speaker(it.value)
        if it.value and not audio.playing:
            audio.tone(1320, 30, 0.2)

    await _page(nav, "Audio", "set_speaker", items, changed, {
        "volume": "Vale per l'altoparlante e per le cuffie.",
        "speaker": "Spento, l'audio esce solo dal jack delle cuffie.",
        "clicks": "Click dei tasti e suono delle notifiche.",
        "game_sounds": "Effetti sonori dei giochi.",
    })


async def _leds(nav):
    leds = nav.sys.leds
    if leds is None:
        await ui.dialog(nav, "LED", "I LED non rispondono su questo badge.")
        return
    from ..leds import EFFECTS
    fx = [e for e in EFFECTS if e != "off"]
    names = [FX_NAMES.get(e, e) for e in fx]
    cur = settings.get("led_effect")
    items = [ui.Item("LED", settings.get("leds_on"), "lights", "toggle", tag="leds_on"),
             ui.Item("Effetto", FX_NAMES.get(cur, cur), "lights", "choice", choices=names,
                     tag="led_effect"),
             ui.Item("Luminosità", settings.get("led_brightness"), "lights", "slider", step=5, lo=5,
                     tag="led_brightness"),
             ui.Item("Colori e animazioni", None, "lights", tag="app")]

    def changed(it):
        if it.tag == "led_effect":
            effect = fx[names.index(it.value)]
            settings.set("led_effect", effect, False)
            settings.set("leds_on", True, False)
            items[0].value = True
            leds.set_effect(effect)
            return
        settings.set(it.tag, it.value, False)
        if it.tag == "leds_on":
            leds.set_effect(settings.get("led_effect") if it.value else "off")
        else:
            leds.level = it.value / 100

    it = await _page(nav, "LED", "lights", items, changed, {
        "leds_on": "Accende o spegne i 22 LED sopra lo schermo.",
        "led_effect": "Anche dal pannello rapido: tieni premuto ►.",
        "led_brightness": "Più luce, più consumo di batteria.",
        "app": "Colori e altre regolazioni nell'app Luci.",
    })
    if it is not None and not nav.home:
        nav.sys.request_app("lights")


# -- time ---------------------------------------------------------------------------------

async def _time(nav):
    sel = 0
    while True:
        zones = list(ZONES)
        if tz.zone not in zones:
            zones.insert(zones.index("Europe/Rome"), tz.zone)
        items = [ui.Item("Fuso orario", tz.zone, "clock", "choice", choices=zones, tag="tz"),
                 ui.Item("Imposta data e ora", None, "settings", tag="set")]
        if net.connected():
            items.append(ui.Item("Sincronizza da Internet", None, "wifi", tag="ntp"))

        def changed(it):
            tz.zone = it.value
            settings.set("tz", it.value, False)

        def card(y):
            ui.statusbar(nav)
            _clock_card(y)

        it = await _page(nav, "Ora", "clock", items, changed, card=card, sel=sel)
        if it is None or nav.home:
            return
        sel = items.index(it)
        if it.tag == "set":
            await _set_clock(nav)
        else:
            ui.toast_draw("Sincronizzazione…")
            nav.show()
            ok = net.sync_time()
            await _toast(nav, "Ora sincronizzata" if ok else "Server dell'ora non raggiungibile")
        if nav.home:
            return


def _clock_card(y):
    h = LIST_END - 4 - y
    gfx.round_rect(12, y, 296, h, 10, ui.PANEL)
    off = tz.offset_minutes()
    zone = "UTC%s%02d:%02d" % ("-" if off < 0 else "+", abs(off) // 60, abs(off) % 60)
    if tz.clock_valid():
        t = tz.now()
        gfx.text("%02d:%02d" % (t[3], t[4]), 28, y + 10, ui.TEXT, "large")
        gfx.text("%s %d %s" % (tz.DAYS_LONG[t[6]], t[2], tz.MONTHS_LONG[t[1] - 1]), 124, y + 10, ui.TEXT)
        gfx.text("%d · %s" % (t[0], zone), 124, y + 28, ui.DIM)
    else:
        gfx.text("--:--", 28, y + 10, ui.DIM, "large")
        gfx.text("ora non impostata", 124, y + 10, ui.ORANGE)
        gfx.text(zone, 124, y + 28, ui.DIM)
    hint = "Wi-Fi attivo: l'ora si sincronizza da sola." if net.connected() \
        else "Senza Wi-Fi impostala a mano qui sopra."
    gfx.text(hint, 28, y + h - 20, ui.DIM, "small")


# hours, minutes, day, month, year: (x, y, digits, font, lowest, highest)
_FIELDS = ((80, 62, 2, "huge", 0, 23), (176, 62, 2, "huge", 0, 59), (80, 150, 2, "large", 1, 31),
           (128, 150, 2, "large", 1, 12), (176, 150, 4, "large", 2025, 2099))


async def _set_clock(nav):
    if tz.clock_valid():
        t = tz.now()
        v = [t[3], t[4], t[2], t[1], t[0]]
    else:
        v = [12, 0, 1, 1, 2026]
    field = 0
    full = True
    while True:
        if full:
            ui.header(nav, "Data e ora", "clock")
            gfx.text(tz.zone, 310, 26, ui.DIM, "small", align=-1)
            ui.footer([("▲▼◄►", "Modifica"), ("A", "Salva"), ("A tieni", "Annulla")])
        _draw_fields(v, field)
        if full:
            nav.show()
            full = False
        else:
            nav.show(LIST_Y, ui.FOOTER_Y)
        ev = await nav.event()
        if ev is None:
            continue
        k, kind = B.key(ev), B.kind(ev)
        if kind == nav.REDRAW:
            full = True
        elif nav.is_back(ev):
            return
        elif k == B.A and kind == B.CLICK:
            _apply_clock(nav.sys, v)
            await _toast(nav, "Ora impostata", 900)
            return
        elif kind in (B.PRESS, B.REPEAT):
            if k in (B.LEFT, B.RIGHT):
                field = (field + (1 if k == B.RIGHT else -1)) % len(_FIELDS)
            elif k in (B.UP, B.DOWN):
                lo, hi = _FIELDS[field][4], _FIELDS[field][5]
                if field == 2:
                    hi = _month_days(v[4], v[3])
                v[field] = lo + (v[field] - lo + (1 if k == B.UP else -1)) % (hi - lo + 1)
                v[2] = min(v[2], _month_days(v[4], v[3]))


def _draw_fields(v, field):
    gfx.fill_rect(0, LIST_Y, 320, ui.FOOTER_Y - LIST_Y, ui.BG)
    for i, (x, y, n, f, _lo, _hi) in enumerate(_FIELDS):
        w, h = (32 * n, 64) if f == "huge" else (16 * n, 32)
        if i == field:
            gfx.round_rect(x - 6, y - 4, w + 12, h + 8, 8, ui.PANEL2)
            gfx.fill_rect(x, y + h + 1, w, 3, ui.ACCENT)
        gfx.text(("%02d" if n == 2 else "%04d") % v[i], x, y, ui.WHITE if i == field else ui.TEXT, f)
    gfx.text(":", 144, 62, ui.DIM, "huge")
    gfx.text("/", 112, 150, ui.DIM, "large")
    gfx.text("/", 160, 150, ui.DIM, "large")
    day = (_days(v[4], v[3], v[2]) + 3) % 7         # 1970-01-01 was a Thursday
    gfx.text("%s %d %s %d" % (tz.DAYS_LONG[day], v[2], tz.MONTHS_LONG[v[3] - 1], v[4]),
             160, 196, ui.CYAN, align=1)


def _month_days(year, month):
    if month == 2:
        return 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28
    return 30 if month in (4, 6, 9, 11) else 31


def _days(year, month, day):
    """Days from 1970-01-01 (time.mktime is UTC on the badge but local on the unix port)."""
    year -= month <= 2
    era = year // 400
    yoe = year - era * 400
    doy = (153 * (month + (9 if month <= 2 else -3)) + 2) // 5 + day - 1
    return era * 146097 + yoe * 365 + yoe // 4 - yoe // 100 + doy - 719468


def _apply_clock(sys, v):
    hh, mm, day, month, year = v
    local = _days(year, month, day) * 86400 + hh * 3600 + mm * 60
    shift = 946684800 if time.gmtime(0)[0] == 2000 else 0      # tz works in the port's epoch
    off = tz.offset_minutes(local - shift)
    off = tz.offset_minutes(local - shift - off * 60)
    sys.set_utc(local - off * 60)


# -- key test -----------------------------------------------------------------------------

_KEY_NAMES = ("SU", "GIÙ", "SINISTRA", "DESTRA", "A", "B", "PLAY", "PREV", "NEXT")
_KINDS = {B.PRESS: "premuto", B.RELEASE: "rilasciato", B.REPEAT: "ripetuto", B.LONG: "tenuto",
          B.CLICK: "click"}
# where each key sits on the badge: (x, y, w, h), or (cx, cy, 0, r) for the round A and B
_PAD = ((39, 70, 26, 26), (39, 128, 26, 26), (10, 99, 26, 26), (68, 99, 26, 26),
        (284, 96, 0, 17), (250, 132, 0, 17),
        (142, 166, 36, 20), (100, 166, 36, 20), (184, 166, 36, 20))
_EXIT_MS = 2000


async def _keys(nav):
    sys = nav.sys
    claim, sys.claim_media = sys.claim_media, True      # play/prev/next raw, no quick panel
    seen = 0
    last = None
    drawn = None
    bar = None
    a_since = None
    full = True
    try:
        while True:
            state = sys.buttons.state
            fraction = None
            if state & (1 << B.A):
                now = time.ticks_ms()
                if a_since is None:
                    a_since = now
                held = time.ticks_diff(now, a_since)
                if held >= _EXIT_MS:
                    return
                fraction = held / _EXIT_MS
            else:
                a_since = None
            if full or drawn != (state, last):
                drawn = (state, last)
                if full:
                    ui.header(nav, "Test tasti", "games")
                    ui.footer([("A tieni 2 s", "Esci")])
                _draw_pad(state, seen, last)
                _draw_exit(fraction)
                if full:
                    sys.show()
                    full = False
                else:
                    sys.show(58, 216)
            elif fraction is not None or bar is not None:
                _draw_exit(fraction)
                sys.show(190, 212)
            bar = fraction
            ev = await nav.event(timeout_ms=40)
            if ev is None:
                continue
            k, kind = B.key(ev), B.kind(ev)
            if kind == sys.HOME:
                return
            if kind == sys.REDRAW:
                full = True
                continue
            if kind == B.PRESS:
                seen |= 1 << k
            last = (k, kind)
    finally:
        sys.claim_media = claim


def _draw_pad(state, seen, last):
    gfx.round_rect(4, 58, 312, 158, 14, ui.PANEL)
    gfx.round_rect(100, 64, 120, 92, 6, ui.BG)
    gfx.round_rect(100, 64, 120, 92, 6, ui.LINE, False)
    for k in range(9):
        x, y, w, h = _PAD[k]
        held = state >> k & 1
        fill = ui.ACCENT if held else ui.PANEL2
        ring = ui.GREEN if seen >> k & 1 else ui.LINE
        if w:
            gfx.round_rect(x - 2, y - 2, w + 4, h + 4, 7, ring)
            gfx.round_rect(x, y, w, h, 5, fill)
            x += w // 2
            y += h // 2
        else:
            gfx.circle(x, y, h + 2, ring, True)
            gfx.circle(x, y, h, fill, True)
        gfx.text(B.GLYPHS[k], x, y - 8, ui.WHITE if held else ui.TEXT, align=1)
    if last is None:
        gfx.text("Premi", 160, 86, ui.TEXT, align=1)
        gfx.text("ogni tasto", 160, 104, ui.TEXT, align=1)
    else:
        gfx.text(_KEY_NAMES[last[0]], 160, 78, ui.YELLOW, "title", align=1)
        gfx.text(_KINDS.get(last[1], ""), 160, 106, ui.CYAN, align=1)
    n = bin(seen).count("1")
    gfx.text("provati %d su 9" % n, 160, 136, ui.GREEN if n == 9 else ui.DIM, "small", align=1)


def _draw_exit(fraction):
    gfx.fill_rect(20, 190, 280, 22, ui.PANEL)
    if fraction is None:
        gfx.text("Tieni premuto A per 2 s per uscire", 160, 195, ui.DIM, "small", align=1)
    else:
        gfx.bar(80, 196, 160, 8, fraction, ui.ACCENT, ui.PANEL2, 4)


# -- system info --------------------------------------------------------------------------

_INFO_Y = 54
_INFO_H = 20
_INFO_ROWS = 8


async def _info(nav):
    import gc
    gc.collect()
    sys = nav.sys
    fixed = _info_fixed(sys)
    top = 0
    full = True
    while True:
        rows = _info_rows(sys, fixed)
        if full:
            ui.header(nav, "Info sistema", "info")
            ui.footer([("▲▼", "Scorri"), ("A tieni", "Indietro")])
        else:
            ui.statusbar(nav)
        _draw_info(rows, top)
        nav.show(0, 240 if full else ui.FOOTER_Y)
        full = False
        ev = await nav.event(timeout_ms=1000)
        if ev is None:
            continue
        k, kind = B.key(ev), B.kind(ev)
        if kind == nav.REDRAW:
            full = True
        elif nav.is_back(ev):
            return
        elif kind in (B.PRESS, B.REPEAT):
            step = {B.UP: -1, B.DOWN: 1, B.LEFT: -_INFO_ROWS, B.RIGHT: _INFO_ROWS}.get(k, 0)
            top = max(0, min(top + step, len(rows) - _INFO_ROWS))


def _info_fixed(sys):
    """What does not change while the page is open."""
    import machine
    import sys as _sys
    try:
        u = os.uname()
        mp = "v" + u.release
        chip = u.machine.rsplit(" ", 1)[-1]
    except AttributeError:          # the unix port has no os.uname()
        mp = "v%d.%d.%d" % _sys.implementation.version[:3]
        chip = _sys.platform
    try:
        import esp32
        labels = [p.info()[4] for p in esp32.Partition.find(esp32.Partition.TYPE_APP)]
    except (ImportError, OSError):
        labels = []
    missing = [p for p in RETRO_PARTS if p not in labels]
    if not missing:
        retro = "3 partizioni su 3"
    elif len(missing) == len(RETRO_PARTS):
        retro = "non installato"
    else:
        retro = "manca " + ", ".join(missing)
    if sys.sd_mounted:
        sd = _usage_row("Scheda SD", paths.SD)
    elif sys.power.sd_present():
        sd = ("Scheda SD", "inserita, non letta", None, ui.ORANGE)
    else:
        sd = ("Scheda SD", "assente", None, ui.DIM)
    return {
        "mp": mp,
        "cpu": "%s · %d MHz" % (chip, machine.freq() // 1000000),
        "mac": ":".join("%02X" % b for b in machine.unique_id()),
        "retro": (retro, ui.GREEN if not missing else ui.ORANGE),
        "flash": _usage_row("Flash usata", paths.ROOT),
        "sd": sd,
    }


def _usage_row(label, path):
    try:
        s = os.statvfs(path)
    except OSError:
        return (label, "non leggibile", None, ui.ORANGE)
    total = s[1] * s[2]
    used = total - s[1] * s[3]
    return (label, _pair(used, total), used / max(1, total), ui.CYAN)


def _info_rows(sys, fixed):
    """(label, value, fraction or None, colour): the colour is the bar's, or the value's."""
    import gc
    free, used = gc.mem_free(), gc.mem_alloc()
    volts = sys.power.battery_volts()
    pct = sys.power.battery_percent(volts)
    level = ui.GREEN if pct > 30 else ui.YELLOW if pct > 12 else ui.RED
    if net.connected():
        rssi = net.rssi()
        wifi = (net.ssid or "connesso") + (" (%d dBm)" % rssi if rssi is not None else "")
    else:
        wifi = "non connesso"
    return (
        ("Traboda", "v" + VERSION, None, ui.TEXT),
        ("MicroPython", fixed["mp"], None, ui.TEXT),
        ("Processore", fixed["cpu"], None, ui.TEXT),
        ("RAM usata", _pair(used, free + used), used / (free + used), ui.CYAN),
        fixed["flash"],
        fixed["sd"],
        ("Batteria", ("%.2f V · %d%%" % (volts, pct)).replace(".", ","), pct / 100, level),
        ("Ricarica", "sì (USB)" if sys.charging else "no", None, ui.GREEN if sys.charging else ui.TEXT),
        ("Acceso da", _uptime(time.ticks_diff(time.ticks_ms(), sys._started) // 1000), None, ui.TEXT),
        ("Wi-Fi", wifi, None, ui.TEXT if net.connected() else ui.DIM),
        ("IP", net.ip() or "-", None, ui.TEXT if net.connected() else ui.DIM),
        ("MAC", fixed["mac"], None, ui.TEXT),
        ("Retro-Go", fixed["retro"][0], None, fixed["retro"][1]),
    )


def _draw_info(rows, top):
    gfx.fill_rect(0, _INFO_Y, 320, _INFO_ROWS * _INFO_H, ui.BG)
    for i in range(min(_INFO_ROWS, len(rows) - top)):
        label, value, fraction, color = rows[top + i]
        y = _INFO_Y + i * _INFO_H
        if (top + i) % 2:
            gfx.fill_rect(4, y, 308, _INFO_H, ui.PANEL)
        gfx.text(label, 12, y + 2, ui.DIM)
        if fraction is None:
            gfx.text(gfx.ellipsize(value, 184), 124, y + 2, color)
        else:
            gfx.text(gfx.ellipsize(value, 128), 124, y + 2, ui.TEXT)
            gfx.bar(258, y + 6, 48, 8, fraction, color, ui.PANEL2, 4)
    if len(rows) > _INFO_ROWS:
        track = _INFO_ROWS * _INFO_H
        th = track * _INFO_ROWS // len(rows)
        ty = _INFO_Y + (track - th) * top // (len(rows) - _INFO_ROWS)
        gfx.fill_rect(316, _INFO_Y, 2, track, ui.PANEL)
        gfx.fill_rect(316, ty, 2, th, ui.ACCENT)


def _scaled(n):
    """(number text, unit) with three significant digits at most: "1,8", "MB"."""
    unit = "B"
    for u in ("KB", "MB", "GB"):
        if n < 1024:
            break
        n /= 1024
        unit = u
    return ("%.1f" % n).replace(".", ",") if n < 10 and unit != "B" else "%d" % n, unit


def _pair(used, total):
    a, ua = _scaled(used)
    b, ub = _scaled(total)
    return "%s / %s %s" % (a, b, ub) if ua == ub else "%s %s / %s %s" % (a, ua, b, ub)


def _uptime(s):
    d, s = divmod(max(0, s), 86400)
    h, s = divmod(s, 3600)
    if d:
        return "%d g %d h" % (d, h)
    if h:
        return "%d h %02d min" % (h, s // 60)
    return "%d min %02d s" % (s // 60, s % 60)


# -- power --------------------------------------------------------------------------------

def _shutdown(sys, title):
    """Sound and LEDs off and a last frame, before the badge resets."""
    sys.audio.stop()
    sys.audio.close()
    if sys.leds:
        sys.leds.off(now=True)
    gfx.clear(ui.BG)
    icons.draw(gfx.fb, "set_reboot", 144, 76, 2)
    gfx.text(title, 160, 122, ui.TEXT, "title", align=1)
    sys.show()


def _reset():
    import machine
    try:
        machine.reset()
    except SystemExit:              # what machine.reset() does in the simulator
        pass


async def _reboot(nav):
    if await ui.dialog(nav, "Riavvia", "Riavviare il badge adesso?", ("Annulla", "Riavvia")) == 1:
        settings.save()
        _shutdown(nav.sys, "Riavvio…")
        _reset()


async def _standby(nav):
    try:
        await nav.sys.standby()
    except SystemExit:              # deep sleep in the simulator
        nav.sys.wake_screen()


async def _factory(nav):
    msg = "Cancella nickname, reti Wi-Fi salvate, record dei giochi e preferenze, poi riavvia il badge."
    if await ui.dialog(nav, "Ripristinare tutto?", msg, ("Annulla", "Azzera")) != 1:
        return
    try:
        os.remove(paths.data("settings.json"))
    except OSError:
        pass
    settings.load()
    _shutdown(nav.sys, "Ripristino…")
    _reset()


PAGES = {"badge": _badge, "screen": _screen, "audio": _audio, "leds": _leds, "time": _time,
         "keys": _keys, "info": _info, "reboot": _reboot, "standby": _standby, "reset": _factory}
