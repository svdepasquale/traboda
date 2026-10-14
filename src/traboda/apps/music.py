"""Walkman: the music library, and a cassette deck whose reels follow the tape."""

import asyncio
import math
import os
import time
from array import array

from .. import buttons as B
from .. import gfx, icons, paths, settings, ui
from ..display import W, rgb
from ..player import EXTS, title_of

TITLE = "Walkman"
ICON = "cassette"
MEDIA_KEYS = False

icons.register("shuffle", (
    "................",
    "...........B....",
    "...........BB...",
    "BBBB....BBBBBB..",
    "BBBBBB..BBBBBB..",
    "....BB..BB.BB...",
    ".....BBBB..B....",
    "......BB........",
    "......BB........",
    ".....BBBB..B....",
    "....BB..BB.BB...",
    "BBBBBB..BBBBBB..",
    "BBBB....BBBBBB..",
    "...........BB...",
    "...........B....",
    "................",
))
icons.register("repeat", (
    "................",
    "...........G....",
    "...........GG...",
    "..GGGGGGGGGGGG..",
    ".GGGGGGGGGGGGG..",
    ".GG........GG...",
    ".GG........G....",
    ".GG..........GG.",
    ".GG..........GG.",
    "....G........GG.",
    "...GG........GG.",
    "..GGGGGGGGGGGGG.",
    "..GGGGGGGGGGGG..",
    "...GG...........",
    "....G...........",
    "................",
))
icons.register("vu", (
    "................",
    "................",
    ".............rr.",
    ".............rr.",
    "..........oo.rr.",
    "..........oo.rr.",
    ".......yy.oo.rr.",
    ".......yy.oo.rr.",
    "....GG.yy.oo.rr.",
    "....GG.yy.oo.rr.",
    ".GG.GG.yy.oo.rr.",
    ".GG.GG.yy.oo.rr.",
    ".GG.GG.yy.oo.rr.",
    ".GG.GG.yy.oo.rr.",
    "................",
    "................",
))
icons.register("playing", [row.replace("B", "P") for row in icons.ART["music"]])

SOFT = rgb(200, 204, 222)
SHELL = rgb(46, 48, 64)
SHELL_EDGE = rgb(98, 102, 128)
RAMP = rgb(62, 65, 86)
SCREW = rgb(132, 136, 156)
LABEL = rgb(242, 236, 220)
INK = rgb(32, 36, 96)
INK_SOFT = rgb(104, 106, 136)
WINDOW = rgb(18, 18, 28)
WINDOW_EDGE = rgb(112, 114, 134)
TAPE = rgb(96, 60, 38)
TAPE_EDGE = rgb(136, 88, 58)
TAPE_RING = rgb(76, 46, 30)
HUB = rgb(236, 232, 220)
HOLE = rgb(16, 16, 24)

LIST_Y = 52
ROWS = 6
ROW_H = ui.ROW_H

CX = W // 2
CAS_X, CAS_Y, CAS_W, CAS_H = 36, 22, 248, 128
LAB_X, LAB_Y, LAB_W, LAB_H = 50, 30, 220, 88
WIN_X, WIN_Y, WIN_W, WIN_H = 98, 70, 124, 46
HUB_Y = WIN_Y + WIN_H // 2
HUB_LX = WIN_X + 30
HUB_RX = WIN_X + WIN_W - 31
HUB_R = 10
EMPTY_R = 12
FULL_R = 21
TIME_Y = 156
CTRL_Y = 178
STATE_Y = 200
BAR_X = 62
BAR_W = 196
FRAME_MS = 100
SPIN = 117                    # reel speed: 1/256 steps of 5 degrees per ms, times radius
TURN = 72 * 256
HINTS = [("A", "▶‖"), ("◄►", "Brano"), ("▲▼", "Volume"), ("B", "Lista")]

_SIN = array("h", [int(1024 * math.sin(i * math.pi / 36)) for i in range(72)])
# tape pack radius for 0..100 % of the tape wound on it (the tape area is constant)
_RADII = bytes([int(math.sqrt(EMPTY_R * EMPTY_R + (FULL_R * FULL_R - EMPTY_R * EMPTY_R) * i / 100) + 0.5)
                for i in range(101)])
_TOOTH = array("h", [0] * 6)
_CONE = array("h", [4, 4, 9, 0, 9, 13, 4, 9])
_RAMP = array("h", [CAS_X + 46, 124, CAS_X + CAS_W - 46, 124, CAS_X + CAS_W - 34, 149, CAS_X + 34, 149])


def _split(path):
    """(title, artist) from "Artist - Title" or "Artist-Title", without a leading track
    number ("01 - ..."); the artist may be ""."""
    name = title_of(path).strip()
    for sep in (" - ", "-"):
        num, found, rest = name.partition(sep)
        if found and num.strip().isdigit() and rest.strip():
            name = rest.strip()
            break
    for sep in (" - ", "-"):
        artist, found, title = name.partition(sep)
        if found and artist.strip() and title.strip():
            return title.strip(), artist.strip()
    return name, ""


def _mmss(s):
    s = int(s)
    return "%d:%02d" % (s // 60, s % 60)


def _fit(s, px, f="text"):
    """Ellipsizes for any font ("small" has no ellipsis glyph)."""
    n = px // gfx.font(f).w
    if len(s) <= n:
        return s
    return s[:max(0, n - 1)] + ("." if f == "small" else "…")


def _error(e):
    """Audio's error text, in Italian for the ones a bad file gives."""
    if e.startswith("not a WAV") or e.startswith("WAV "):
        return "file WAV non valido"
    if e.startswith("compressed"):
        return "serve un WAV PCM"
    if e.endswith("(only 16-bit)"):
        return "serve un WAV a 16 bit"
    if e.startswith("[Errno"):
        return "file illeggibile"
    return e


def _leds(sys, here=True):
    """The LEDs are a VU meter while the tape rolls here (if LED VU is on), otherwise
    the user's effect. Cheap: the loops call it every round, with here=False on leaving."""
    leds = sys.leds
    if not leds:
        return
    a = sys.audio
    on = settings.get("leds_on")
    rolling = a.playing and not a.paused or a.ended         # ended: the next track is due
    vu = here and on and rolling and settings.get("music_vu", True)
    want = "vu" if vu else settings.get("led_effect") if on else "off"
    if leds.effect != want and "vu" in (want, leds.effect):
        leds.set_effect(want)


async def _unwind(sys):
    """Stops the stream and lets its task end before another starts: Audio.play() over a
    live stream lets the old task clear the new one's handle, leaving two streams."""
    if sys.audio.playing:
        sys.audio.stop()
        await asyncio.sleep_ms(1)


async def _play(sys, tracks, i):
    await _unwind(sys)
    sys.player.load(tracks, i)


async def _advance(sys):
    """A track that ended goes on to the next one now (gapless), not at the core's next
    half-second tick; the new stream gets a moment to start."""
    if sys.audio.ended:
        sys.player.tick()
        await asyncio.sleep_ms(1)


# -- library -----------------------------------------------------------------------------

def _audio(name):
    return name.lower().endswith(EXTS) and not name.startswith(".")


async def _scan(folder):
    """Audio files under folder and its sub-folders (one level), sorted. One directory
    read per folder (no stat per file), yielding between folders so the music goes on."""
    root = folder.rstrip("/")
    out = []
    try:
        entries = sorted(os.ilistdir(root))
    except OSError:
        return out
    for e in entries:
        name, path = e[0], root + "/" + e[0]
        if e[1] == 0x4000 and not name.startswith("."):
            try:
                subs = sorted(f[0] for f in os.ilistdir(path) if f[1] != 0x4000)
            except OSError:
                continue
            out.extend(path + "/" + f for f in subs if _audio(f))
            await asyncio.sleep_ms(0)
        elif e[1] != 0x4000 and _audio(name):
            out.append(path)
    return out


class _Library:
    def __init__(self):
        self.tracks = None
        self.names = []
        self.summary = ""
        self.tag = None             # tag of the selected row, kept across visits

    async def scan(self, sys):
        """The SD card's music folder if it has tracks, else the internal one."""
        try:
            sys.mount_sd()
        except OSError:
            pass
        name = settings.get("music_dir")
        self.tracks, where = await _scan(paths.sd(name)), "SD"
        if not self.tracks:
            self.tracks, where = await _scan(paths.data(name)), "memoria"
        self.names = [_split(t) for t in self.tracks]
        n = len(self.tracks)
        self.summary = "%d %s · %s" % (n, "brano" if n == 1 else "brani", where)


def _items(sys, lib):
    p = sys.player
    items = []
    if p.loaded:
        items.append(ui.Item("In riproduzione", None, ICON, tag="now"))
    items.append(ui.Item("Shuffle", p.shuffle, "shuffle", "toggle", tag="shuffle"))
    items.append(ui.Item("Ripeti", p.repeat, "repeat", "toggle", tag="repeat"))
    items.append(ui.Item("LED VU", settings.get("music_vu", True), "vu", "toggle", tag="vu"))
    for i, (title, artist) in enumerate(lib.names):
        room = max(96, W - 66 - 8 * len(title))     # what the title leaves in a list row
        items.append(ui.Item(title, _fit(artist, room) or None, "music", tag=i))
    _mark(sys, lib, items)
    return items


def _mark(sys, lib, items):
    """Now-playing text, and the pink note on the current track."""
    a = sys.audio
    cur = sys.player.current
    for it in items:
        if it.tag == "now" and cur:
            mark = "▶ " if a.playing and not a.paused else "‖ " if a.playing else "■ "
            it.value = _fit(mark + _split(cur)[0], 136)
        elif isinstance(it.tag, int):
            it.icon = "playing" if lib.tracks[it.tag] == cur else "music"


def _select(sys, lib, items):
    tag = lib.tag
    cur = sys.player.current
    if (tag is None or isinstance(tag, int)) and cur in lib.tracks:
        tag = lib.tracks.index(cur)
    elif tag is None:
        tag = 0
    for i, it in enumerate(items):
        if it.tag == tag:
            return i
    return 0


def _toggle(sys, it):
    it.adjust(1)
    v = it.value
    if it.tag == "shuffle":
        sys.player.shuffle = v
        settings.set("shuffle", v)
    elif it.tag == "repeat":
        sys.player.repeat = v
        settings.set("repeat", v)
    else:
        settings.set("music_vu", v)
        _leds(sys)


def _hints(it):
    if it.tag == "now":
        return [("A", "Apri"), ("B", "Esci")]
    if it.kind == "toggle":
        return [("A", "Cambia"), ("B", "Esci")]
    return [("A", "Play"), ("◄►", "Pagina"), ("B", "Esci")]


def _loading(sys):
    ui.header(sys, TITLE, ICON)
    gfx.text("Cerco i brani…", CX, 120, ui.DIM, align=1)
    sys.show()


async def _empty(sys):
    """No tracks: where they go. Returns "scan" or "deck" (A), None to leave."""
    loaded = sys.player.loaded
    msg = "Copia file WAV (PCM, 16 bit) nella cartella \"%s\" della scheda SD o della " \
          "memoria interna." % settings.get("music_dir")
    draw = True
    while True:
        if draw:
            y = ui.header(sys, TITLE, ICON)
            gfx.round_rect(10, y + 4, W - 20, 160, 10, ui.PANEL)
            gfx.round_rect(10, y + 4, W - 20, 160, 10, ui.LINE, False)
            icons.draw(gfx.fb, ICON, 26, y + 16, 2)
            gfx.text("Nessun brano", 70, y + 20, ui.TEXT, "title")
            lines = gfx.wrap(msg, W - 52)[:4]
            for i, line in enumerate(lines):
                gfx.text(line, 26, y + 60 + 16 * i, SOFT)
            gfx.text("Da MP3: ffmpeg -i a.mp3 a.wav", 26, y + 68 + 16 * len(lines), ui.CYAN)
            ui.footer([("A", "Riproduzione" if loaded else "Aggiorna"), ("B", "Esci")])
            sys.show()
            draw = False
        ev = await sys.event()
        k, kind = B.key(ev), B.kind(ev)
        if kind == sys.REDRAW:
            draw = True
        elif sys.is_back(ev):
            return None
        elif k == B.A and kind == B.CLICK:
            return "deck" if loaded else "scan"


async def _library(sys, lib):
    """The track list. Returns True to open the deck, False to leave the app."""
    while True:
        if lib.tracks is None:
            _loading(sys)
            await lib.scan(sys)
        if lib.tracks:
            break
        choice = await _empty(sys)
        if choice is None:
            return False
        lib.tracks = None
        if choice == "deck":
            return True
    p, a = sys.player, sys.audio
    items = _items(sys, lib)
    first = len(items) - len(lib.tracks)
    sel = _select(sys, lib, items)
    top = max(0, sel - ROWS + 1)
    full = True
    seen = (p.index, a.playing, a.paused)
    hints = None
    minute = -1
    _leds(sys)
    while True:
        n = len(items)
        if sel < top:
            top = sel
        elif sel >= top + ROWS:
            top = sel - ROWS + 1
        it = items[sel]
        if full:
            ui.header(sys, TITLE, ICON)
            minute = time.time() // 60
            gfx.text(lib.summary, W - 10, 26, ui.DIM, align=-1)
            hints = None
        ui.draw_list(items, sel, top, LIST_Y, ROWS)
        if hints != _hints(it):
            hints = _hints(it)
            ui.footer(hints)
            if not full:
                sys.show(ui.FOOTER_Y, 240)
        if full:
            sys.show()
            full = False
        else:
            sys.show(LIST_Y, LIST_Y + ROWS * ROW_H)
        while True:
            ev = await sys.event(timeout_ms=500)
            await _advance(sys)
            _leds(sys)
            now = (p.index, a.playing, a.paused)
            if now != seen or (ev is None and time.time() // 60 != minute):
                minute = time.time() // 60
                ui.statusbar(sys)
                sys.show(0, ui.STATUS_H)
                if now != seen:
                    seen = now
                    _mark(sys, lib, items)
                    break
            if ev is not None:
                break
        if ev is None:
            continue
        k, kind = B.key(ev), B.kind(ev)
        if kind == sys.REDRAW:
            full = True
            continue
        if sys.is_back(ev):
            lib.tag = it.tag
            return False
        if kind == B.CLICK and k == B.A:
            lib.tag = it.tag
            if it.tag == "now":
                return True
            if it.kind == "toggle":
                _toggle(sys, it)
                continue
            if p.queue != lib.tracks or p.current != lib.tracks[it.tag] or not a.playing:
                await _play(sys, lib.tracks, it.tag)
            return True
        if kind == B.CLICK and k == B.PLAY and not p.loaded:
            lib.tag = it.tag if isinstance(it.tag, int) else 0
            await _play(sys, lib.tracks, lib.tag)
            return True
        if kind not in (B.PRESS, B.REPEAT):
            continue
        if k == B.UP:
            sel = (sel - 1) % n
        elif k == B.DOWN:
            sel = (sel + 1) % n
        elif k in (B.LEFT, B.RIGHT):
            if it.kind == "toggle":
                if kind == B.PRESS:
                    _toggle(sys, it)
            elif sel >= first:
                step = ROWS if k == B.RIGHT else -ROWS
                sel = max(first, min(n - 1, sel + step))


# -- deck --------------------------------------------------------------------------------

def _screw(x, y):
    gfx.circle(x, y, 3, SCREW, True)
    gfx.hline(x - 2, y, 5, SHELL)
    gfx.vline(x, y - 2, 5, SHELL)


def _cassette(title, artist, pos):
    """The static parts: shell, label with title and artist, head area."""
    gfx.round_rect(CAS_X, CAS_Y, CAS_W, CAS_H, 10, SHELL)
    gfx.fb.poly(0, 0, _RAMP, RAMP, True)
    gfx.round_rect(CAS_X, CAS_Y, CAS_W, CAS_H, 10, SHELL_EDGE, False)
    bottom = CAS_Y + CAS_H
    for x in (CX - 40, CX + 40):
        gfx.circle(x, bottom - 14, 4, HOLE, True)
    gfx.fill_rect(CX - 12, bottom - 10, 24, 7, HOLE)
    gfx.fill_rect(CX - 58, bottom - 8, 10, 5, HOLE)
    gfx.fill_rect(CX + 48, bottom - 8, 10, 5, HOLE)
    for x, y in ((CAS_X + 7, CAS_Y + 7), (CAS_X + CAS_W - 8, CAS_Y + 7), (CAS_X + 7, bottom - 9),
                 (CAS_X + CAS_W - 8, bottom - 9), (CX, bottom - 19)):
        _screw(x, y)
    gfx.round_rect(LAB_X, LAB_Y, LAB_W, LAB_H, 6, LABEL)
    right = WIN_X + WIN_W + 3
    for y, c in ((HUB_Y - 6, ui.ACCENT), (HUB_Y + 2, ui.CYAN)):
        gfx.fill_rect(LAB_X, y, WIN_X - 3 - LAB_X, 4, c)
        gfx.fill_rect(right, y, LAB_X + LAB_W - right, 4, c)
    gfx.text(gfx.ellipsize(title, LAB_W - 20), CX, LAB_Y + (3 if artist else 11), INK, align=1)
    if artist:
        gfx.text(_fit(artist, LAB_W - 20, "small"), CX, LAB_Y + 22, INK_SOFT, "small", align=1)
    gfx.circle(LAB_X + 24, HUB_Y, 9, INK, True)
    gfx.text("A", LAB_X + 24, HUB_Y - 8, LABEL, align=1)
    gfx.text(pos, (right + LAB_X + LAB_W) // 2, WIN_Y + 2, INK, "small", align=1)


def _pack(cx, r):
    gfx.circle(cx, HUB_Y, r, TAPE_EDGE, True)
    gfx.circle(cx, HUB_Y, r - 1, TAPE, True)
    if r > EMPTY_R + 3:
        gfx.circle(cx, HUB_Y, r - 4, TAPE_RING)


def _hub(cx, step):
    gfx.circle(cx, HUB_Y, HUB_R, HUB, True)
    gfx.circle(cx, HUB_Y, 7, HOLE, True)
    t = _TOOTH
    for k in range(0, 72, 12):
        s = _SIN[(step + k) % 72]
        c = _SIN[(step + k + 18) % 72]
        t[0] = 9 * c >> 11
        t[1] = 9 * s >> 11
        t[2] = (16 * c - 3 * s) >> 11
        t[3] = (16 * s + 3 * c) >> 11
        t[4] = (16 * c + 3 * s) >> 11
        t[5] = (16 * s - 3 * c) >> 11
        gfx.fb.poly(cx, HUB_Y, t, HUB, True)


def _speaker(x, y, c):
    gfx.fill_rect(x, y + 4, 4, 6, c)
    gfx.fb.poly(x, y, _CONE, c, True)
    gfx.fb.ellipse(x + 10, y + 7, 3, 3, c, False, 9)
    gfx.fb.ellipse(x + 10, y + 7, 6, 6, c, False, 9)


class _Deck:
    def __init__(self, sys):
        self.sys = sys
        self.spin_l = 0
        self.spin_r = 0
        self.t = time.ticks_ms()
        self.sec = -1
        self.minute = -1
        self.sig = None
        self.seek_to = None         # target of the seek in progress (s)
        self.seek_t = 0
        self.seeked = 0             # LEFT/RIGHT bits that repeated: their CLICK is not a skip
        self.volume_changed = False

    def state(self):
        a, p = self.sys.audio, self.sys.player
        return (p.index, a.track, a.playing, a.paused, a.error, p.shuffle, p.repeat)

    def elapsed(self):
        return self.seek_to if self.seek_to is not None else self.sys.audio.elapsed

    def pct(self):
        a = self.sys.audio
        d = a.duration
        if a.error or not d:
            return 0
        return max(0, min(100, int(self.elapsed() * 100 / d)))

    # drawing

    def draw(self):
        sys = self.sys
        p = sys.player
        gfx.clear(ui.BG)
        ui.statusbar(sys, TITLE)
        title, artist = _split(p.current) if p.current else ("", "")
        _cassette(title, artist, "%d/%d" % (p.index + 1, len(p.queue)))
        self.draw_window()
        self.draw_time()
        self.draw_controls()
        self.draw_state()
        ui.footer(HINTS)
        self.sig = self.state()
        self.minute = time.time() // 60
        sys.show()

    def draw_window(self):
        pct = self.pct()
        rl, rr = _RADII[100 - pct], _RADII[pct]
        gfx.round_rect(WIN_X, WIN_Y, WIN_W, WIN_H, 6, WINDOW)
        bottom = WIN_Y + WIN_H - 2
        gfx.line(HUB_LX - rl + 1, HUB_Y, WIN_X + 4, bottom, TAPE_EDGE)
        gfx.line(HUB_RX + rr - 1, HUB_Y, WIN_X + WIN_W - 5, bottom, TAPE_EDGE)
        _pack(HUB_LX, rl)
        _pack(HUB_RX, rr)
        _hub(HUB_LX, self.spin_l >> 8)
        _hub(HUB_RX, self.spin_r >> 8)
        gfx.round_rect(WIN_X, WIN_Y, WIN_W, WIN_H, 6, WINDOW_EDGE, False)

    def draw_time(self):
        a = self.sys.audio
        y = TIME_Y
        gfx.fill_rect(0, y, W, 18, ui.BG)
        d = 0 if a.error else a.duration
        e = min(self.elapsed(), d)
        self.sec = int(e)
        gfx.text(_mmss(e) if d else "-:--", 12, y + 1, ui.YELLOW if self.seek_to is not None else ui.CYAN)
        gfx.text(_mmss(d) if d else "-:--", W - 12, y + 1, ui.DIM, align=-1)
        f = e / d if d else 0
        gfx.bar(BAR_X, y + 7, BAR_W, 5, f, ui.ACCENT, ui.PANEL2, 2)
        gfx.circle(BAR_X + int(BAR_W * f), y + 9, 4, ui.TEXT, True)

    def draw_controls(self):
        sys = self.sys
        y = CTRL_Y
        gfx.fill_rect(0, y, W, 20, ui.BG)
        vol = sys.audio.volume
        _speaker(12, y + 3, ui.DIM)
        lit = (vol + 4) // 5
        for i in range(20):
            h = 4 + i * 11 // 19
            c = ui.PANEL2 if i >= lit else ui.ACCENT if i >= 15 else ui.CYAN
            gfx.fill_rect(34 + i * 5, y + 17 - h, 4, h, c)
        gfx.text("%d%%" % vol, 138, y + 2, ui.TEXT)
        x = W - 10
        for label, on in (("RIPETI", sys.player.repeat), ("SHUFFLE", sys.player.shuffle)):
            w = len(label) * 6 + 12
            x -= w
            c = ui.YELLOW if on else ui.DIM
            gfx.round_rect(x, y + 2, w, 15, 4, ui.PANEL2 if on else ui.BG)
            gfx.round_rect(x, y + 2, w, 15, 4, c if on else ui.LINE, False)
            gfx.text(label, x + w // 2, y + 4, c, "small", align=1)
            x -= 6

    def draw_state(self):
        a = self.sys.audio
        y = STATE_Y
        gfx.fill_rect(0, y, W, 20, ui.BG)
        if a.error:
            gfx.text(gfx.ellipsize("! " + _error(a.error), 200), 12, y + 2, ui.RED)
        else:
            gfx.text("tieni ◄ ► per cercare", 12, y + 5, ui.DIM, "small")
        if a.playing and not a.paused:
            label, c = "▶ PLAY", ui.GREEN
        elif a.playing:
            label, c = "‖ PAUSA", ui.YELLOW
        else:
            label, c = "■ FERMO", ui.DIM
        x = W - 94
        gfx.round_rect(x, y + 1, 84, 18, 5, ui.PANEL)
        gfx.round_rect(x, y + 1, 84, 18, 5, c, False)
        gfx.text(label, x + 42, y + 2, c, align=1)

    # input

    def seek(self, delta):
        sys = self.sys
        a = sys.audio
        if not a.playing or a.error:
            return
        t = max(0, self.elapsed() + delta)
        if a.duration > 1:
            t = min(t, a.duration - 1)
        a.seek(t)
        self.seek_to = t
        self.seek_t = time.ticks_ms()
        self.draw_window()
        self.draw_time()
        sys.show(WIN_Y, WIN_Y + WIN_H)
        sys.show(TIME_Y, TIME_Y + 18)

    async def skip(self, back):
        a, p = self.sys.audio, self.sys.player
        restart = back and a.playing and a.elapsed > 3      # like a tape deck, as Player.prev
        await _unwind(self.sys)
        if restart:
            a.play(p.current)
        else:
            (p.prev if back else p.next)()

    async def key(self, k, kind):
        sys = self.sys
        a, p = sys.audio, sys.player
        if k == B.A and kind == B.CLICK:
            p.play_pause()
            self.seek_t = time.ticks_ms()
        elif k in (B.LEFT, B.RIGHT):
            bit = 1 << k
            if kind == B.PRESS:
                self.seeked &= ~bit
            elif kind == B.REPEAT:
                self.seeked |= bit
                self.seek(-3 if k == B.LEFT else 3)
            elif kind == B.CLICK:
                if self.seeked & bit:
                    self.seeked &= ~bit
                else:
                    await self.skip(k == B.LEFT)
        elif k in (B.UP, B.DOWN) and kind in (B.PRESS, B.REPEAT):
            v = max(0, min(100, a.volume + (5 if k == B.UP else -5)))
            if v != a.volume:
                a.set_volume(v)
                settings.set("volume", v, False)
                self.volume_changed = True
                self.draw_controls()
                sys.show(CTRL_Y, CTRL_Y + 20)

    def tick(self):
        """Reels at FRAME_MS while the tape runs, the clock once a second."""
        sys = self.sys
        a = sys.audio
        now = time.ticks_ms()
        if self.seek_to is not None and not a.paused and time.ticks_diff(now, self.seek_t) > 400:
            self.seek_to = None
            self.sec = -1
        dt = time.ticks_diff(now, self.t)
        if a.playing and not a.paused:
            if dt >= FRAME_MS:
                self.t = now
                dt = min(dt, 250)
                pct = self.pct()
                self.spin_l = (self.spin_l - SPIN * dt // _RADII[100 - pct]) % TURN
                self.spin_r = (self.spin_r - SPIN * dt // _RADII[pct]) % TURN
                self.draw_window()
                sys.show(WIN_Y, WIN_Y + WIN_H)
        else:
            self.t = now
        if int(self.elapsed()) != self.sec:
            self.draw_time()
            sys.show(TIME_Y, TIME_Y + 18)
        minute = time.time() // 60
        if minute != self.minute:
            self.minute = minute
            ui.statusbar(sys, TITLE)
            sys.show(0, ui.STATUS_H)

    async def run(self):
        """Returns True to go back to the library, False on HOME."""
        sys = self.sys
        try:
            self.draw()
            while True:
                await _advance(sys)
                _leds(sys)
                a = sys.audio
                wait = FRAME_MS             # a stream that starts or stops shows up quickly
                if a.playing and not a.paused:
                    wait = max(1, FRAME_MS - time.ticks_diff(time.ticks_ms(), self.t))
                ev = await sys.event(timeout_ms=wait)
                if ev is not None:
                    k, kind = B.key(ev), B.kind(ev)
                    if kind == sys.HOME:
                        return False
                    if sys.is_back(ev):
                        return True
                    if kind == sys.REDRAW:
                        self.sig = None
                    else:
                        await self.key(k, kind)
                if self.state() != self.sig:
                    if self.sig and self.sig[:2] != self.state()[:2]:
                        self.seek_to = None
                    self.draw()
                else:
                    self.tick()
        finally:
            if self.volume_changed:
                settings.save()


async def main(sys):
    lib = _Library()
    try:
        if sys.player.loaded and not await _Deck(sys).run():
            return
        while await _library(sys, lib):
            if not await _Deck(sys).run():
                return
    finally:
        _leds(sys, False)
