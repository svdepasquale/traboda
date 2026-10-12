"""Snake: steer with the D-pad, eat to grow and speed up; the walls and your own body kill.

Each step repaints only the cells that changed (new head, old head, tail, food) and
pushes only their rows.
"""

import asyncio
import random
import time

from ... import buttons as B
from ... import gfx, settings, ui
from ...display import rgb
from . import common

GAME_ID = "snake"
TITLE = "Snake"
ICON = "snake"
MEDIA_KEYS = True

CELL = 10
GW = 30                     # cells across
GH = 19                     # cells down
X0 = 10                     # field origin, inside the wall
Y0 = 25
SIZE = GW * GH
DX = (0, 0, -1, 1)          # by direction, which is the D-pad key code: up down left right
DY = (-1, 1, 0, 0)
EYES = ((2, 2, 6, 2), (2, 6, 6, 6), (2, 2, 2, 6), (6, 2, 6, 6))
SNOUT = ((1, 1, 8, 1), (1, 8, 8, 8), (1, 1, 1, 8), (8, 1, 8, 8))   # head corners rounded off

START_MS = 150              # step time with nothing eaten
MIN_MS = 60
FASTER_MS = 3               # less per food eaten
PER_LEVEL = 11              # foods per LED level: each lights one column

FIELD = (rgb(15, 18, 33), rgb(20, 24, 42))
WALL = rgb(52, 60, 96)
BODY = (0, rgb(61, 220, 132), rgb(36, 176, 102))     # by grid value
HEAD = rgb(150, 255, 196)
DEAD = rgb(255, 77, 77)
LEAF = rgb(61, 220, 132)
OFF = (0, 0, 0)
EAT_FLASH = (61, 220, 132)
LEVEL_COLORS = ((61, 220, 132), (45, 226, 230), (255, 214, 10), (255, 150, 40),
                (255, 45, 111), (170, 110, 255))
HINTS = (("◄▲▼►", "Sterza"), ("►‖", "Pausa"))


def _xy(c):
    return X0 + c % GW * CELL, Y0 + c // GW * CELL


class Snake:
    def __init__(self, sys):
        self.sys = sys
        self.body = [0] * SIZE          # ring buffer of cells; self.head is the newest
        self.led = [OFF] * 22
        self.reset()

    def reset(self):
        self.grid = bytearray(SIZE)     # 0 free, 1/2 body (the two greens alternate)
        y = GH // 2
        for i in range(4):
            c = y * GW + 4 + i
            self.body[i] = c
            self.grid[c] = 1 + (i & 1)
        self.head = 3
        self.n = 4
        self.born = 4                   # segments ever made, for the stripes
        self.dir = B.RIGHT
        self.turns = []
        self.eaten = 0
        self.score = 0
        self.best = settings.score(GAME_ID)
        self.ms = START_MS
        self.won = False
        self.rows = 0                   # bitmask of cell rows to push
        self.hud_dirty = False
        self.place_food()
        self.set_leds()

    def place_food(self):
        if self.n >= SIZE:
            self.food = -1
            self.won = True
            return
        c = random.randrange(SIZE)
        while self.grid[c]:
            c = (c + 1) % SIZE
        self.food = c

    def set_leds(self):
        lit = self.eaten % PER_LEVEL
        color = LEVEL_COLORS[self.eaten // PER_LEVEL % len(LEVEL_COLORS)]
        led = self.led
        for c in range(11):
            led[c] = led[c + 11] = color if c < lit else OFF

    def turn(self, d):
        """Queues up to two turns; a reversal onto the neck is ignored."""
        last = self.turns[-1] if self.turns else self.dir
        if len(self.turns) < 2 and d != last and d != last ^ 1:
            self.turns.append(d)

    # -- drawing --------------------------------------------------------------------------

    def mark(self, c):
        self.rows |= 1 << (c // GW)

    def erase(self, c):
        x, y = _xy(c)
        gfx.fill_rect(x, y, CELL, CELL, FIELD[(c % GW + c // GW) & 1])
        self.mark(c)

    def segment(self, c, toward, color):
        """A body cell plus the bridge that joins it to the next cell headwards."""
        x, y = _xy(c)
        gfx.fill_rect(x + 1, y + 1, 8, 8, color)
        if toward // GW == c // GW:
            x, y = _xy(min(c, toward))
            gfx.fill_rect(x + 9, y + 1, 2, 8, color)
        else:
            x, y = _xy(min(c, toward))
            gfx.fill_rect(x + 1, y + 9, 8, 2, color)
        self.mark(c)
        self.mark(toward)

    def tail(self, c, toward, color):
        """The last cell, thinner, reaching into its neighbour."""
        self.erase(c)
        x, y = _xy(c)
        if toward == c + 1:
            gfx.fill_rect(x + 3, y + 2, 8, 6, color)
        elif toward == c - 1:
            gfx.fill_rect(x - 1, y + 2, 8, 6, color)
        elif toward > c:
            gfx.fill_rect(x + 2, y + 3, 6, 8, color)
        else:
            gfx.fill_rect(x + 2, y - 1, 6, 8, color)
        self.mark(toward)

    def draw_head(self, color=HEAD):
        c = self.body[self.head]
        x, y = _xy(c)
        gfx.fill_rect(x + 1, y + 1, 8, 8, color)
        e = EYES[self.dir]
        gfx.fill_rect(x + e[0], y + e[1], 2, 2, ui.BG)
        gfx.fill_rect(x + e[2], y + e[3], 2, 2, ui.BG)
        e = SNOUT[self.dir]
        bg = FIELD[(c % GW + c // GW) & 1]
        gfx.fb.pixel(x + e[0], y + e[1], bg)
        gfx.fb.pixel(x + e[2], y + e[3], bg)
        self.mark(c)

    def draw_food(self):
        c = self.food
        if c < 0:
            return
        x, y = _xy(c)
        gfx.circle(x + 5, y + 5, 3, ui.RED, True)
        gfx.fill_rect(x + 3, y + 4, 1, 2, ui.WHITE)
        gfx.fill_rect(x + 5, y + 1, 3, 1, LEAF)
        gfx.fill_rect(x + 5, y + 2, 1, 1, LEAF)
        self.mark(c)

    def draw_snake(self, dead=False):
        body, grid, h, n = self.body, self.grid, self.head, self.n
        c = body[(h - n + 1) % SIZE]
        self.tail(c, body[(h - n + 2) % SIZE], DEAD if dead else BODY[grid[c]])
        for i in range(n - 2, 0, -1):
            c = body[(h - i) % SIZE]
            self.segment(c, body[(h - i + 1) % SIZE], DEAD if dead else BODY[grid[c]])
        self.draw_head(DEAD if dead else HEAD)

    def draw_all(self):
        gfx.clear(ui.BG)
        common.hud(TITLE, self.score, max(self.best, self.score))
        gfx.round_rect(X0 - 3, Y0 - 3, GW * CELL + 6, GH * CELL + 6, 4, WALL)
        gfx.fill_rect(X0, Y0, GW * CELL, GH * CELL, FIELD[0])
        for cy in range(GH):
            for cx in range((cy + 1) & 1, GW, 2):
                gfx.fill_rect(X0 + cx * CELL, Y0 + cy * CELL, CELL, CELL, FIELD[1])
        self.draw_snake()
        self.draw_food()
        ui.footer(HINTS)
        self.rows = 0
        self.hud_dirty = False

    def flush(self):
        """Pushes the HUD if the score changed and every run of touched cell rows."""
        show = self.sys.show
        if self.hud_dirty:
            common.hud(TITLE, self.score, max(self.best, self.score))
            show(0, common.HUD_H)
            self.hud_dirty = False
        rows = self.rows
        r = 0
        while rows:
            if rows & 1:
                start = r
                while rows & 1:
                    rows >>= 1
                    r += 1
                show(Y0 + start * CELL, Y0 + r * CELL)
            rows >>= 1
            r += 1
        self.rows = 0

    # -- game -----------------------------------------------------------------------------

    def step(self):
        """Moves one cell; False on a crash."""
        if self.turns:
            self.dir = self.turns.pop(0)
        body, grid = self.body, self.grid
        old = body[self.head]
        x = old % GW + DX[self.dir]
        y = old // GW + DY[self.dir]
        if x < 0 or x >= GW or y < 0 or y >= GH:
            return False
        new = y * GW + x
        grow = new == self.food
        tail = body[(self.head - self.n + 1) % SIZE]
        kept = grid[tail]
        if not grow:
            grid[tail] = 0              # the tail moves away first: chasing it is fine
        if grid[new]:
            grid[tail] = kept
            return False
        grid[new] = 1 + (self.born & 1)
        self.born += 1
        self.head = (self.head + 1) % SIZE
        body[self.head] = new
        if grow:
            self.n += 1
        else:
            self.erase(tail)
            c = body[(self.head - self.n + 1) % SIZE]
            self.tail(c, body[(self.head - self.n + 2) % SIZE], BODY[grid[c]])
        self.segment(old, new, BODY[grid[old]])
        self.draw_head()
        if grow:
            self.eaten += 1
            self.score = self.eaten * 10
            self.ms = max(MIN_MS, START_MS - FASTER_MS * self.eaten)
            self.hud_dirty = True
            self.place_food()
            self.draw_food()
            self.set_leds()
            self.flush()
            common.leds_flash(self.sys, EAT_FLASH, 250)
            common.sfx(self.sys, "eat")
        return True

    async def crash(self):
        common.leds_flash(self.sys, (255, 40, 40), 500)
        common.sfx(self.sys, "hit")
        for i in range(5):
            self.draw_snake(i % 2 == 0)
            self.rows = 0
            self.sys.show(Y0, Y0 + GH * CELL)
            await asyncio.sleep_ms(110)


def _pause_key(ev):
    """Play, A held, or a tap on B (B held is HOME and leaves the game)."""
    k, kind = B.key(ev), B.kind(ev)
    return common.wants_pause(ev) or (k == B.A and kind == B.LONG) or (k == B.B and kind == B.CLICK)


def _discard(sys):
    """Drops the events queued meanwhile; False if one of them was HOME."""
    for ev in common.drain(sys):
        if B.kind(ev) == sys.HOME:
            return False
    return True


async def _start(sys, game):
    """Countdown over a fresh frame; False if HOME arrived meanwhile."""
    common.leds_frame(sys, game.led)
    await common.countdown(sys, game.draw_all)
    return _discard(sys)


async def _settle(sys):
    """Waits (up to 1 s) for the keys still held from play, which would otherwise answer
    the game-over dialog, then drops them; False on HOME."""
    for _ in range(50):
        if not sys.buttons.state:
            break
        await asyncio.sleep_ms(20)
    return _discard(sys)


async def main(sys):
    game = Snake(sys)
    if not await _start(sys, game):
        return
    tick = common.Ticker(100)
    due = time.ticks_add(time.ticks_ms(), game.ms)
    while True:
        for ev in common.drain(sys):
            k, kind = B.key(ev), B.kind(ev)
            if kind == sys.HOME:
                return
            if kind == sys.REDRAW:
                game.draw_all()
                sys.show()
            elif _pause_key(ev):
                choice = await common.pause_menu(sys, TITLE)
                if choice == "quit":
                    return
                if choice == "restart":
                    game.reset()
                if not await _start(sys, game):
                    return
                due = time.ticks_add(time.ticks_ms(), game.ms)
                break
            elif kind == B.PRESS and k <= B.RIGHT:
                game.turn(k)
        now = time.ticks_ms()
        if time.ticks_diff(now, due) >= 0:
            due = time.ticks_add(due, game.ms)
            if time.ticks_diff(now, due) >= 0:
                due = time.ticks_add(now, game.ms)
            if not game.step() or game.won:
                if not game.won:
                    await game.crash()
                if await common.game_over(sys, GAME_ID, TITLE, game.score, game.won) == "quit":
                    return
                game.reset()
                if not await _start(sys, game):
                    return
                due = time.ticks_add(time.ticks_ms(), game.ms)
        game.flush()
        common.leds_frame(sys, game.led)
        await tick.wait()
