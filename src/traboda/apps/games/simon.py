"""Memoria: the classic light-and-sound memory game, on the screen and on the LEDs.

Pads clockwise from the top: up green, right red, down blue, left yellow. Every round
adds a step; repeat the whole sequence with the D-pad before the ring runs out.
"""

import math
import random
import time
from array import array

from ... import buttons as B
from ... import gfx, settings, ui
from ...display import rgb
from . import common

GAME_ID = "simon"
TITLE = "Memoria"
ICON = "simon"
MEDIA_KEYS = True

CX = 160
CY = 120
R_OUT = 94
R_IN = 46
R_DISC = 34
TIMEOUT_MS = 3000
SEGS = 24

KEYS = (B.UP, B.RIGHT, B.DOWN, B.LEFT)
ARROWS = ("▲", "►", "▼", "◄")
TONES = (415, 310, 209, 252)
_DIM = ((18, 96, 54), (124, 28, 40), (26, 52, 130), (122, 98, 14))
_LIT = ((90, 255, 160), (255, 90, 104), (96, 176, 255), (255, 230, 80))
DIM = tuple(rgb(*c) for c in _DIM)
LIT = tuple(rgb(*c) for c in _LIT)
MID = tuple(rgb((d[0] + l[0]) // 2, (d[1] + l[1]) // 2, (d[2] + l[2]) // 2) for d, l in zip(_DIM, _LIT))
LED = ((0, 255, 70), (255, 16, 24), (20, 70, 255), (255, 176, 0))
BLACK = (0, 0, 0)


def _sector(mid_deg, half_deg, r0, r1, gap, seg):
    """Ring sector centred on mid_deg (0 = right, clockwise), pushed out by gap pixels."""
    mid = math.radians(mid_deg)
    half = math.radians(half_deg)
    dx = gap * math.cos(mid)
    dy = gap * math.sin(mid)
    pts = array("h")
    for r, a0, a1 in ((r1, mid - half, mid + half), (r0, mid + half, mid - half)):
        for j in range(seg + 1):
            a = a0 + (a1 - a0) * j / seg
            pts.append(round(CX + dx + r * math.cos(a)))
            pts.append(round(CY + dy + r * math.sin(a)))
    return pts


def _band(pts):
    ys = [pts[i] for i in range(1, len(pts), 2)]
    return min(ys), max(ys) + 1


def _region(pos):
    """The pad an LED belongs to: the strip is split like the D-pad."""
    row, col = divmod(pos, 11)
    if col < 3:
        return 3
    if col > 7:
        return 1
    return 0 if row == 0 else 2


PADS = tuple(_sector(-90 + 90 * i, 45, R_IN, R_OUT, 4, 14) for i in range(4))
BANDS = tuple(_band(p) for p in PADS)
RING = tuple(_sector(-90 + 15 * j + 7.5, 6, 37, 41, 0, 2) for j in range(SEGS))
REGION = tuple(_region(p) for p in range(22))
LIT_FRAMES = tuple([LED[i] if REGION[p] == i else BLACK for p in range(22)] for i in range(4))
IDLE_FRAME = [tuple(v * 14 // 100 for v in LED[REGION[p]]) for p in range(22)]
OFF_FRAME = [BLACK] * 22


def _tone(sys, pad, ms):
    if common.sounds_on():
        try:
            sys.audio.tone(TONES[pad], ms)
        except Exception:  # noqa: BLE001 - never let a beep stop a game
            pass


class Simon:
    def __init__(self, sys):
        self.sys = sys
        self.seq = []
        self.score = 0
        self.best = settings.score(GAME_ID)
        self.lit = -1
        self.rest = OFF_FRAME
        self.label = ("GUARDA", ui.DIM)
        self.segs = 0

    # -- drawing -----------------------------------------------------------------------

    def draw(self):
        gfx.clear(ui.BG)
        common.hud(TITLE, self.score, self.best)
        for i in range(4):
            self.draw_pad(i)
        self.draw_ring()
        self.draw_center()
        ui.footer([("▲▼◄►", "Ripeti"), ("▶", "Pausa")])

    def draw_pad(self, i):
        on = i == self.lit
        c = LIT[i] if on else DIM[i]
        gfx.fb.poly(0, 0, PADS[i], c, True)
        gfx.fb.poly(0, 0, PADS[i], ui.WHITE if on else c, False)
        a = math.radians(-90 + 90 * i)
        gfx.text(ARROWS[i], round(CX + 74 * math.cos(a)), round(CY + 74 * math.sin(a)) - 16,
                 ui.WHITE if on else MID[i], "large", align=1)

    def draw_ring(self):
        color = ui.CYAN if self.segs > SEGS // 2 else ui.YELLOW if self.segs > SEGS // 4 else ui.RED
        for j in range(SEGS):
            gfx.fb.poly(0, 0, RING[j], color if j < self.segs else ui.PANEL2, True)

    def draw_center(self):
        gfx.circle(CX, CY, R_DISC, ui.PANEL, True)
        gfx.circle(CX, CY, R_DISC, ui.LINE)
        gfx.text(str(len(self.seq) or 1), CX, CY - 18, ui.CYAN, "title", align=1)
        gfx.text(self.label[0], CX, CY + 8, self.label[1], "small", align=1)

    def show_center(self):
        self.sys.show(CY - 42, CY + 43)

    def set_label(self, text, color):
        self.label = (text, color)
        self.draw_center()
        self.show_center()

    def set_segs(self, n):
        if n != self.segs:
            self.segs = n
            self.draw_ring()
            self.draw_center()
            self.show_center()

    def light(self, pad, tone_ms=0):
        """Lights one pad (or none with -1), with its LEDs and tone."""
        old, self.lit = self.lit, pad
        for i in (old, pad):
            if i >= 0:
                self.draw_pad(i)
                self.sys.show(BANDS[i][0], BANDS[i][1])
        common.leds_frame(self.sys, LIT_FRAMES[pad] if pad >= 0 else self.rest)
        if pad >= 0 and tone_ms:
            _tone(self.sys, pad, tone_ms)

    # -- timing and events -------------------------------------------------------------

    def check(self, ev):
        """HOME -> "quit", pause or back -> "pause", REDRAW repaints; else None."""
        sys = self.sys
        if B.kind(ev) == sys.HOME:
            return "quit"
        if B.kind(ev) == sys.REDRAW:
            self.draw()
            sys.show()
        elif common.wants_pause(ev) or sys.is_back(ev):
            return "pause"
        return None

    async def hold(self, ms):
        """Waits ms, ignoring the pads. Returns "quit", "pause" or None."""
        until = time.ticks_add(time.ticks_ms(), ms)
        while True:
            left = time.ticks_diff(until, time.ticks_ms())
            if left <= 0:
                return None
            ev = await self.sys.event(timeout_ms=left)
            if ev is not None:
                r = self.check(ev)
                if r:
                    return r

    # -- phases ------------------------------------------------------------------------

    async def show_sequence(self):
        n = len(self.seq)
        on = 420 if n <= 5 else 320 if n <= 13 else 220
        self.rest = OFF_FRAME
        self.set_segs(0)
        self.set_label("GUARDA", ui.DIM)
        common.leds_frame(self.sys, OFF_FRAME)
        r = await self.hold(500)
        for pad in self.seq:
            if r:
                break
            t = time.ticks_ms()
            self.light(pad, on - 80)
            r = await self.hold(on - time.ticks_diff(time.ticks_ms(), t))
            self.light(-1)
            if not r:
                r = await self.hold(on + 90 - time.ticks_diff(time.ticks_ms(), t))
        return r

    async def read_answer(self):
        """Returns "ok", "pause", "quit", or the pad that should have been pressed."""
        sys = self.sys
        self.rest = IDLE_FRAME
        common.leds_frame(sys, IDLE_FRAME)
        self.set_label("TOCCA!", ui.YELLOW)
        i = 0
        deadline = time.ticks_add(time.ticks_ms(), TIMEOUT_MS)
        unlight = None
        while True:
            now = time.ticks_ms()
            if unlight is not None and time.ticks_diff(unlight, now) <= 0:
                unlight = None
                self.light(-1)
                if i == len(self.seq):
                    return "ok"
            left = time.ticks_diff(deadline, now)
            if left <= 0 and i < len(self.seq):
                return self.seq[i]
            segs = max(0, (left * SEGS + TIMEOUT_MS - 1) // TIMEOUT_MS) if i < len(self.seq) else 0
            self.set_segs(segs)
            wait = max(1, left - (segs - 1) * TIMEOUT_MS // SEGS) if segs else 250
            if unlight is not None:
                wait = min(wait, max(1, time.ticks_diff(unlight, now)))
            ev = await sys.event(timeout_ms=wait)
            if ev is None:
                continue
            r = self.check(ev)
            if r:
                return r
            k = B.key(ev)
            if B.kind(ev) != B.PRESS or k not in KEYS or i == len(self.seq):
                continue
            pad = KEYS.index(k)
            self.light(pad, 200)
            if pad != self.seq[i]:
                return self.seq[i]
            i += 1
            unlight = time.ticks_add(time.ticks_ms(), 220)
            deadline = time.ticks_add(time.ticks_ms(), TIMEOUT_MS)

    async def fail(self, expected):
        sys = self.sys
        self.set_segs(0)
        self.set_label("ERRORE", ui.RED)
        common.leds_flash(sys, (255, 30, 30), 500)
        if common.sounds_on():
            try:
                sys.audio.tone(90, 400)
            except Exception:  # noqa: BLE001
                pass
        self.rest = OFF_FRAME
        for _ in range(3):
            self.light(expected)
            if await self.hold(220) == "quit":
                return "quit"
            self.light(-1)
            if await self.hold(140) == "quit":
                return "quit"
        return await common.game_over(sys, GAME_ID, TITLE, self.score)


async def _game(sys):
    g = Simon(sys)
    g.draw()
    sys.show()
    common.leds_frame(sys, OFF_FRAME)
    grow = True
    while True:
        if grow:
            g.seq.append(random.randrange(4))
            grow = False
        r = await g.show_sequence()
        if r is None:
            r = await g.read_answer()
        if r == "ok":
            g.score = len(g.seq)
            common.hud(TITLE, g.score, max(g.best, g.score))
            sys.show(0, common.HUD_H)
            g.set_label("BRAVO!", ui.GREEN)
            common.leds_flash(sys, (61, 220, 132), 240)
            grow = True
            r = await g.hold(600)
        if r == "quit":
            return "quit"
        if r == "pause":
            g.light(-1)
            choice = await common.pause_menu(sys, TITLE)
            if choice != "resume":
                return choice
            g.draw()
            sys.show()
        elif isinstance(r, int):
            return await g.fail(r)


async def main(sys):
    while True:
        if await _game(sys) != "restart":
            return
