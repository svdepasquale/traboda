"""Riflessi: wait for green, then press a key as fast as you can. Five tries; the score is
1000 minus the average in milliseconds, and the best average is kept apart."""

import asyncio
import framebuf
import math
import random
import time

from ... import buttons as B
from ... import gfx, icons, settings, ui
from ...display import rgb
from . import common

GAME_ID = "reaction"
TITLE = "Riflessi"
ICON = "reaction"
MEDIA_KEYS = True

ROUNDS = 5
BEST_KEY = "reaction_best_ms"
PX, PY, PW, PH = 8, 24, 304, 150
CHIP_Y = 182
SLOW_MS = 5000
ANTICIPATION_MS = 100
WAIT_BG = rgb(150, 20, 44)
WAIT_FG = rgb(255, 200, 210)
GO_BG = rgb(34, 204, 100)
GO_FG = rgb(4, 44, 20)
FOUL_BG = rgb(196, 92, 0)
BLACK = (0, 0, 0)
INTRO_LEDS = [(120, 0, 0) if p % 11 < 4 else (120, 90, 0) if p % 11 < 7 else (0, 120, 40) for p in range(22)]
GO_LEDS = [(0, 255, 70)] * 22
FOUL_LEDS = [(255, 40, 0)] * 22
OFF_LEDS = [BLACK] * 22
GOLD_LEDS = [(255, 214, 10)] * 22
INTRO_HINTS = [("A", "Inizia"), ("B", "Esci")]
COUNT_HINTS = [("►‖", "Pausa")]
PLAY_HINTS = [("A", "Premi al verde"), ("►‖", "Pausa")]
NEXT_HINTS = [("A", "Continua"), ("►‖", "Pausa")]
# (under ms, verdict, screen colour, LED colour)
RATINGS = (
    (200, "Fulmine!", ui.CYAN, (45, 226, 230)),
    (250, "Ottimo!", ui.GREEN, (61, 220, 132)),
    (320, "Buono", ui.YELLOW, (255, 214, 10)),
    (420, "Nella media", ui.ORANGE, (255, 150, 40)),
    (1 << 30, "Svegliati!", ui.RED, (255, 60, 60)),
)


def _rating(ms):
    for r in RATINGS:
        if ms < r[0]:
            return r
    return RATINGS[-1]


def _strip(color, cols):
    """Both rows lit in the given columns."""
    frame = [BLACK] * 22
    for c in cols:
        frame[c] = frame[11 + c] = color
    return frame


def _panel(color):
    gfx.fill_rect(PX, PY, PW, PH, ui.BG)
    gfx.round_rect(PX, PY, PW, PH, 12, color)


def _ms(value, y, color):
    """Big digits with a small "ms" after them, centred."""
    digits = str(value)
    w = len(digits) * 32
    x = 160 - (w + 30) // 2
    gfx.text(digits, x, y, color, "huge")
    gfx.text("ms", x + w + 6, y + 38, ui.DIM, "title")


def _render_go():
    """The green screen, drawn once off-screen so that it appears with a single blit."""
    img = framebuf.FrameBuffer(bytearray(PW * PH * 2), PW, PH, framebuf.RGB565)
    screen = gfx.fb
    gfx.attach(img)
    try:
        gfx.fill_rect(0, 0, PW, PH, ui.BG)
        gfx.round_rect(0, 0, PW, PH, 12, GO_BG)
        gfx.text_scaled("VAI!", PW // 2, 22, GO_FG, "large", 2, align=1)
        gfx.text("premi un tasto!", PW // 2, 100, GO_FG, "title", align=1)
    finally:
        gfx.attach(screen)
    return img


class Reaction:
    def __init__(self, sys):
        self.sys = sys
        self.times = []
        self.fouls = 0
        self.best = settings.get(BEST_KEY, 0)
        self.record = False
        self.round = 1
        self.n = 3
        self.panel = self.p_intro
        self.hints = INTRO_HINTS
        self.go_img = _render_go()

    # -- drawing -----------------------------------------------------------------------

    def draw(self):
        gfx.clear(ui.BG)
        best = "record %d ms" % self.best if self.best else "record --"
        common.hud(TITLE, "%d/%d" % (self.round, ROUNDS), extra=best)
        self.draw_chips()
        ui.footer(self.hints)
        self.panel()

    def draw_chips(self):
        done = len(self.times)
        fastest = self.times.index(min(self.times)) if done == ROUNDS else -1
        for i in range(ROUNDS):
            x = PX + i * 62
            gfx.round_rect(x, CHIP_Y, 56, 32, 6, ui.PANEL)
            if i == fastest:
                gfx.round_rect(x, CHIP_Y, 56, 32, 6, ui.GREEN, False)
            elif i == self.round - 1 and done < ROUNDS:
                gfx.round_rect(x, CHIP_Y, 56, 32, 6, ui.YELLOW, False)
            gfx.text("prova %d" % (i + 1), x + 28, CHIP_Y + 3, ui.DIM, "small", align=1)
            if i < done:
                gfx.text(str(self.times[i]), x + 28, CHIP_Y + 14, _rating(self.times[i])[2], align=1)
            else:
                gfx.text("--", x + 28, CHIP_Y + 14, ui.LINE, align=1)

    def show(self, panel):
        """Switches the big panel and pushes it."""
        self.panel = panel
        panel()
        self.sys.show(PY, PY + PH)

    def show_all(self, panel, hints):
        """Switches the panel and the hints and repaints everything (HUD and chips too)."""
        self.panel = panel
        self.hints = hints
        self.draw()
        self.sys.show()

    def p_intro(self):
        _panel(ui.PANEL)
        icons.draw(gfx.fb, ICON, 160 - 24, PY + 8, 3)
        x = 160 - 10 * 8
        x += gfx.text("Quando diventa ", x, PY + 64, ui.TEXT)
        gfx.text("VERDE", x, PY + 64, ui.GREEN)
        gfx.text("premi un tasto, più veloce che puoi", 160, PY + 84, ui.DIM, align=1)
        gfx.text("%d prove: conta la media" % ROUNDS, 160, PY + 106, ui.DIM, "small", align=1)
        if self.best:
            gfx.text("Miglior media: %d ms" % self.best, 160, PY + 124, ui.CYAN, align=1)
        else:
            gfx.text("Ancora nessun record", 160, PY + 124, ui.DIM, align=1)

    def p_count(self):
        _panel(ui.PANEL2)
        gfx.text(str(self.n), 160, PY + 20, ui.YELLOW, "huge", align=1)
        gfx.text("Pronti...", 160, PY + 100, ui.TEXT, "title", align=1)

    def p_wait(self):
        _panel(WAIT_BG)
        gfx.text("Aspetta il verde...", 160, PY + 50, ui.WHITE, "title", align=1)
        gfx.text("se premi prima è falsa partenza", 160, PY + 88, WAIT_FG, align=1)

    def p_go(self):
        gfx.fb.blit(self.go_img, PX, PY)

    def p_result(self):
        ms = self.times[-1]
        r = _rating(ms)
        _panel(ui.PANEL)
        _ms(ms, PY + 14, r[2])
        gfx.text(r[1], 160, PY + 88, r[2], "title", align=1)
        gfx.text("un tasto per continuare", 160, PY + 126, ui.DIM, "small", align=1)

    def p_foul(self):
        _panel(FOUL_BG)
        gfx.text("Troppo presto!", 160, PY + 46, ui.WHITE, "title", align=1)
        gfx.text("falsa partenza: la prova si ripete", 160, PY + 84, ui.WHITE, align=1)

    def p_slow(self):
        _panel(ui.PANEL2)
        gfx.text("Troppo lento!", 160, PY + 46, ui.ORANGE, "title", align=1)
        gfx.text("la prova si ripete", 160, PY + 84, ui.TEXT, align=1)

    def p_summary(self):
        avg = self.average()
        r = _rating(avg)
        _panel(ui.PANEL)
        gfx.text("Media", 160, PY + 6, ui.DIM, align=1)
        _ms(avg, PY + 24, r[2])
        gfx.text(r[1], 160, PY + 92, r[2], align=1)
        if self.record:
            gfx.text("NUOVO RECORD!", 160, PY + 112, ui.YELLOW, align=1)
        else:
            gfx.text("Miglior media: %d ms" % self.best, 160, PY + 112, ui.CYAN, align=1)
        gfx.text("Punti: %d   falsi: %d" % (self.score(), self.fouls), 160, PY + 133, ui.DIM, "small", align=1)

    # -- game ----------------------------------------------------------------------------

    def average(self):
        return sum(self.times) // len(self.times)

    def score(self):
        return max(0, 1000 - self.average())

    def check(self, ev):
        """HOME -> "quit", play -> "pause", REDRAW repaints; else None."""
        sys = self.sys
        kind = B.kind(ev)
        if kind == sys.HOME:
            return "quit"
        if kind == sys.REDRAW:
            self.draw()
            sys.show()
        elif common.wants_pause(ev):
            return "pause"
        return None

    async def hold(self, ms, skip_after=None):
        """Waits ms; a key press after skip_after ms ends it early. Returns "quit", "pause"
        or None."""
        sys = self.sys
        t0 = time.ticks_ms()
        while True:
            el = time.ticks_diff(time.ticks_ms(), t0)
            if el >= ms:
                return None
            ev = await sys.event(timeout_ms=ms - el)
            if ev is None:
                continue
            r = self.check(ev)
            if r:
                return r
            if B.kind(ev) == B.PRESS and skip_after is not None \
                    and time.ticks_diff(time.ticks_ms(), t0) >= skip_after:
                return None

    async def wait_click(self):
        """Until A is pressed and released here (the release of the key that skipped the
        last result must not skip the summary too): None, "back" on back, "quit" on HOME."""
        sys = self.sys
        pressed = False
        while True:
            ev = await sys.event()
            k, kind = B.key(ev), B.kind(ev)
            if kind == sys.HOME:
                return "quit"
            if kind == sys.REDRAW:
                self.draw()
                sys.show()
            elif sys.is_back(ev):
                return "back"
            elif k == B.A and kind == B.PRESS:
                pressed = True
            elif k == B.A and kind == B.CLICK and pressed:
                return None

    async def countdown(self):
        """3, 2, 1 before the first round and after a pause: "quit", "pause" or None."""
        for n in (3, 2, 1):
            self.n = n
            if n == 3:
                self.show_all(self.p_count, COUNT_HINTS)
            else:
                self.show(self.p_count)
            h = (1, 3, 5)[n - 1]
            common.leds_frame(self.sys, _strip((255, 190, 0), range(5 - h, 6 + h)))
            common.sfx(self.sys, "tick")
            r = await self.hold(550)
            if r:
                return r
        return None

    async def wait_phase(self):
        """Red until a random moment: "go", "foul", "pause" or "quit"."""
        sys = self.sys
        self.show_all(self.p_wait, PLAY_HINTS)
        delay = random.randrange(1500, 5001)
        t0 = time.ticks_ms()
        while True:
            el = time.ticks_diff(time.ticks_ms(), t0)
            if el >= delay:
                return "go"
            k = (1 - math.cos(el * 0.004)) / 2
            common.leds_frame(sys, [(50 + int(205 * k), 0, 6)] * 22)
            ev = await sys.event(timeout_ms=min(40, delay - el))
            if ev is None:
                continue
            r = self.check(ev)
            if r:
                return r
            if B.kind(ev) == B.PRESS:
                return "foul"

    async def go_phase(self):
        """Green: the reaction time in ms, "foul", "slow", "pause" or "quit". REDRAW is
        left alone: repainting here would add its time to the measure, and the next
        screen repaints anyway."""
        sys = self.sys
        self.panel = self.p_go
        self.p_go()
        sys.show(PY, PY + PH)
        t0 = time.ticks_us()
        common.leds_frame(sys, GO_LEDS)
        while True:
            ev = sys.poll_event()
            if ev is None:
                if time.ticks_diff(time.ticks_us(), t0) > SLOW_MS * 1000:
                    return "slow"
                await asyncio.sleep_ms(1)
                continue
            ms = time.ticks_diff(time.ticks_us(), t0) // 1000
            kind = B.kind(ev)
            if kind == sys.HOME:
                return "quit"
            if common.wants_pause(ev):
                return "pause"
            if kind == B.PRESS:
                return ms if ms >= ANTICIPATION_MS else "foul"

    async def play_round(self):
        """One valid time, repeating false starts. Returns ms, "pause" or "quit"."""
        sys = self.sys
        self.round = len(self.times) + 1
        while True:
            r = await self.wait_phase()
            if r == "go":
                r = await self.go_phase()
            if r == "foul":
                self.fouls += 1
                self.show(self.p_foul)
                common.leds_frame(sys, FOUL_LEDS)
                common.sfx(sys, "hit")
                r = await self.hold(1600)
            elif r == "slow":
                self.show(self.p_slow)
                common.leds_frame(sys, OFF_LEDS)
                r = await self.hold(1400)
            if r is not None:
                return r

    async def result(self, ms):
        """The time just made: None after a while (or a key), "pause" or "quit"."""
        sys = self.sys
        r = _rating(ms)
        self.show_all(self.p_result, NEXT_HINTS)
        n = max(1, min(11, (650 - ms) * 11 // 450))
        common.leds_frame(sys, _strip(r[3], range(n)))
        common.sfx(sys, "eat" if ms < 250 else "bounce" if ms < 420 else "hit")
        return await self.hold(2500, skip_after=600)

    async def finish(self):
        sys = self.sys
        avg = self.average()
        self.record = not self.best or avg < self.best
        if self.record:
            self.best = avg
            settings.set(BEST_KEY, avg)
        self.show_all(self.p_summary, [("A", "Continua")])
        if self.record:
            common.leds_frame(sys, GOLD_LEDS)
            if await self.hold(900, skip_after=0) == "quit":
                return "quit"
        common.leds_frame(sys, [_rating(self.times[i // 2])[3] if i % 2 else BLACK
                                for i in range(11)] * 2)
        if await self.wait_click() == "quit":
            return "quit"
        return await common.game_over(sys, GAME_ID, TITLE, self.score())


async def _game(sys, intro):
    """One game of ROUNDS tries; the intro screen only before the first one."""
    g = Reaction(sys)
    if intro:
        g.draw()
        sys.show()
        common.leds_frame(sys, INTRO_LEDS)
        if await g.wait_click():
            return "quit"
    r = await g.countdown()
    while r != "quit":
        if r == "pause":
            choice = await common.pause_menu(sys, TITLE)
            if choice != "resume":
                return choice
            r = None if len(g.times) == ROUNDS else await g.countdown()
            continue
        if len(g.times) == ROUNDS:
            return await g.finish()
        r = await g.play_round()
        if isinstance(r, int):
            g.times.append(r)
            r = await g.result(r)
    return "quit"


async def main(sys):
    intro = True
    while await _game(sys, intro) == "restart":
        intro = False
