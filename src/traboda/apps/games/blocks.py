"""Blocchi: falling tetrominoes with a 7-bag, SRS rotation states and wall kicks, a ghost
piece and a three-piece preview.

The well is diffed against what is on screen, so a frame repaints only the cells that
changed and pushes only their rows.
"""

import asyncio
import random
import time

from ... import buttons as B
from ... import gfx, settings, ui
from ...display import rgb
from ...leds import hsv
from . import common

GAME_ID = "blocks"
TITLE = "Blocchi"
ICON = "blocks"
MEDIA_KEYS = True

COLS = 10
ROWS = 22                   # the top two are hidden: pieces spawn there
HIDDEN = 2
CELL = 10
WX = 110                    # visible well on screen; WY on a 10-row band boundary
WY = 20
VISIBLE = COLS * (ROWS - HIDDEN)
GREY = 8                    # cell values: 0 empty, 1-7 piece, 8 grey, 9-15 ghost, 16 flash
FLASH = 16

# I J L O S T Z: spawn cells (x, y pairs) and the rotation box size (0: never rotates)
_SPAWN = (
    ((0, 1, 1, 1, 2, 1, 3, 1), 4),
    ((0, 0, 0, 1, 1, 1, 2, 1), 3),
    ((2, 0, 0, 1, 1, 1, 2, 1), 3),
    ((1, 0, 2, 0, 1, 1, 2, 1), 0),
    ((1, 0, 2, 0, 0, 1, 1, 1), 3),
    ((1, 0, 0, 1, 1, 1, 2, 1), 3),
    ((0, 0, 1, 0, 1, 1, 2, 1), 3),
)
_RGB = ((45, 226, 230), (64, 120, 255), (255, 150, 40), (255, 214, 10), (61, 220, 132),
        (178, 102, 255), (255, 77, 77), (104, 110, 138))
KICKS = (0, 0, -1, 0, 1, 0, 0, -1, -2, 0, 2, 0)      # (dx, dy) tried in order on a rotation
GRAVITY = tuple(int(1000 * (0.8 - n * 0.007) ** n) for n in range(15))  # ms per row by level
SOFT_MS = 40
LOCK_MS = 500
LOCK_RESETS = 15
LINE_POINTS = (0, 100, 300, 500, 800)
HUD, STATS, NEXT = 1, 2, 4

WELL = rgb(14, 17, 31)
DOT = rgb(36, 42, 70)
WALL = rgb(52, 60, 96)
OFF = (0, 0, 0)
LINE_LEDS = ((45, 226, 230), (61, 220, 132), (255, 214, 10))
LEVEL_LEDS = tuple(hsv(0.33 - 0.033 * c) for c in range(11))
PROGRESS_LED = (45, 226, 230)
HINTS = (("▲/A", "Ruota"), ("▼", "Giù"), ("►►", "Lancia"), ("►‖", "Pausa"))


def _rotations(cells, n):
    out = [cells]
    for _ in range(3):
        if n:
            cells = tuple(n - 1 - cells[i + 1] if i % 2 == 0 else cells[i - 1] for i in range(8))
        out.append(cells)
    return tuple(out)


def _bounds(cells):
    """(min x, min y, width, height) in cells."""
    xs = [cells[i] for i in range(0, 8, 2)]
    ys = [cells[i] for i in range(1, 8, 2)]
    return min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1


def _mix(c, to, k):
    """k eighths of the way from colour c to colour to."""
    return rgb(c[0] + (to[0] - c[0]) * k // 8, c[1] + (to[1] - c[1]) * k // 8,
               c[2] + (to[2] - c[2]) * k // 8)


SHAPES = tuple(_rotations(cells, n) for cells, n in _SPAWN)
BOUNDS = tuple(_bounds(cells) for cells, _ in _SPAWN)
BASE = tuple(rgb(*c) for c in _RGB)
LIGHT = tuple(_mix(c, (255, 255, 255), 3) for c in _RGB)
DARK = tuple(_mix(c, (0, 0, 0), 4) for c in _RGB)
GHOST = tuple(_mix(c, (14, 17, 31), 4) for c in _RGB)


def _block(x, y, s, t):
    gfx.fill_rect(x, y, s, s, BASE[t])
    gfx.hline(x, y, s, LIGHT[t])
    gfx.vline(x, y, s, LIGHT[t])
    gfx.hline(x + 1, y + s - 1, s - 1, DARK[t])
    gfx.vline(x + s - 1, y + 1, s - 1, DARK[t])


def _cell(i, v):
    x = WX + i % COLS * CELL
    y = WY + i // COLS * CELL
    if v == 0:
        gfx.fill_rect(x, y, CELL, CELL, WELL)
        gfx.fb.pixel(x, y, DOT)
    elif v <= GREY:
        _block(x, y, CELL, v - 1)
    elif v < FLASH:
        gfx.fill_rect(x, y, CELL, CELL, WELL)
        gfx.rect(x + 1, y + 1, CELL - 2, CELL - 2, GHOST[v - 9])
    else:
        gfx.fill_rect(x, y, CELL, CELL, ui.WHITE)


def _preview(t, cx, cy, s):
    """Piece t in spawn orientation, centred on (cx, cy), s-pixel cells."""
    cells = SHAPES[t][0]
    mx, my, w, h = BOUNDS[t]
    x0 = cx - w * s // 2 - mx * s
    y0 = cy - h * s // 2 - my * s
    for i in range(0, 8, 2):
        _block(x0 + cells[i] * s, y0 + cells[i + 1] * s, s, t)


class Blocks:
    def __init__(self, sys):
        self.sys = sys
        self.board = bytearray(COLS * ROWS)
        self.view = memoryview(self.board)[COLS * HIDDEN:]
        self.want = bytearray(VISIBLE)
        self.shown = bytearray(VISIBLE)
        self.led = [OFF] * 22
        self.reset()

    def reset(self):
        self.board[:] = bytes(COLS * ROWS)
        self.queue = []
        self.score = 0
        self.lines = 0
        self.level = 1
        self.best = settings.score(GAME_ID)
        self.flash = ()
        self.bands = 0              # 10-row screen bands to push
        self.dirty = 0              # HUD | STATS | NEXT
        self.spawn()
        self.set_leds()

    # -- pieces ---------------------------------------------------------------------------

    def spawn(self):
        """Takes the next piece from the bag; False when it does not fit (game over)."""
        if len(self.queue) < 4:
            bag = [0, 1, 2, 3, 4, 5, 6]
            for i in range(6, 0, -1):
                j = random.randrange(i + 1)
                bag[i], bag[j] = bag[j], bag[i]
            self.queue.extend(bag)
        self.t = self.queue.pop(0)
        self.r = 0
        self.x = 3
        self.y = HIDDEN - 1
        self.fall = 0
        self.lock = 0
        self.resets = 0
        self.dirty |= NEXT
        if not self.fits(0, 3, self.y):
            return False
        self.find_ghost()
        return True

    def fits(self, r, x, y):
        cells = SHAPES[self.t][r]
        board = self.board
        for i in range(0, 8, 2):
            cx = x + cells[i]
            cy = y + cells[i + 1]
            if cx < 0 or cx >= COLS or cy >= ROWS or (cy >= 0 and board[cy * COLS + cx]):
                return False
        return True

    def find_ghost(self):
        gy = self.y
        while self.fits(self.r, self.x, gy + 1):
            gy += 1
        self.gy = gy

    def moved(self):
        self.find_ghost()
        if self.lock and self.resets < LOCK_RESETS:
            self.lock = 0
            self.resets += 1

    def shift(self, dx):
        if self.fits(self.r, self.x + dx, self.y):
            self.x += dx
            self.moved()

    def rotate(self):
        """Clockwise, trying the kicks in turn. Returns True when it turned."""
        if self.t == 3:
            return False
        r = (self.r + 1) % 4
        for i in range(0, len(KICKS), 2):
            x = self.x + KICKS[i]
            y = self.y + KICKS[i + 1]
            if self.fits(r, x, y):
                self.r, self.x, self.y = r, x, y
                self.moved()
                return True
        return False

    def soft_step(self):
        if self.y < self.gy:
            self.y += 1
            self.fall = 0
            self.lock = 0
            self.score += 1
            self.dirty |= HUD

    def hard_drop(self):
        self.score += 2 * (self.gy - self.y)
        self.y = self.gy
        self.dirty |= HUD

    def update(self, dt, soft):
        """Gravity (faster while down is held) and lock delay. True: time to lock."""
        step = GRAVITY[min(self.level, len(GRAVITY)) - 1]
        soft = soft and SOFT_MS < step
        if soft:
            step = SOFT_MS
        self.fall += dt
        while self.fall >= step and self.y < self.gy:
            self.fall -= step
            self.y += 1
            self.lock = 0
            if soft:
                self.score += 1
                self.dirty |= HUD
        if self.y < self.gy:
            return False
        self.fall = 0
        self.lock += dt
        return self.lock >= LOCK_MS

    async def land(self):
        """Locks the piece and clears full rows. False when the stack reached the top."""
        cells = SHAPES[self.t][self.r]
        board = self.board
        top = ROWS
        rows = []
        for i in range(0, 8, 2):
            y = self.y + cells[i + 1]
            top = min(top, y)
            if y >= 0:
                board[y * COLS + self.x + cells[i]] = self.t + 1
                if y not in rows:
                    rows.append(y)
        self.t = -1
        if top < HIDDEN:
            return False
        full = [y for y in rows if min(board[y * COLS:y * COLS + COLS])]
        if full:
            await self.clear(full)
        return self.spawn()

    async def clear(self, full):
        n = len(full)
        for step in range(6):
            self.flash = full if step % 2 == 0 else ()
            led = self.led
            for i in range(22):
                if n == 4:
                    led[i] = hsv(i % 11 / 11 + step / 6)
                else:
                    led[i] = LINE_LEDS[n - 1] if step % 2 == 0 else OFF
            self.render()
            self.flush()
            common.leds_frame(self.sys, led)
            if step == 0:
                common.sfx(self.sys, "line")
            await asyncio.sleep_ms(70)
        self.flash = ()
        board = self.board
        dst = ROWS - 1
        for y in range(ROWS - 1, -1, -1):
            if y not in full:
                if dst != y:
                    board[dst * COLS:dst * COLS + COLS] = board[y * COLS:y * COLS + COLS]
                dst -= 1
        board[:(dst + 1) * COLS] = bytes((dst + 1) * COLS)
        self.score += LINE_POINTS[n] * self.level
        self.lines += n
        self.level = 1 + self.lines // 10
        self.dirty |= HUD | STATS
        self.set_leds()

    async def top_out(self):
        """A grey curtain falls over the well."""
        self.t = -1
        board = self.board
        for y in range(HIDDEN, ROWS):
            board[y * COLS:y * COLS + COLS] = bytes((GREY,)) * COLS
            self.render()
            self.flush()
            await asyncio.sleep_ms(25)

    def set_leds(self):
        """Top row: the level (up to 11); bottom row: lines towards the next one."""
        led = self.led
        done = self.lines % 10
        for c in range(11):
            led[c] = LEVEL_LEDS[c] if c < self.level else OFF
            led[11 + c] = PROGRESS_LED if c < done else OFF

    # -- drawing --------------------------------------------------------------------------

    def render(self):
        """Repaints the well cells that differ from what is on screen."""
        want = self.want
        want[:] = self.view
        for y in self.flash:
            i = (y - HIDDEN) * COLS
            for j in range(i, i + COLS):
                want[j] = FLASH
        t = self.t
        if t >= 0:
            cells = SHAPES[t][self.r]
            for i in range(0, 8, 2):
                y = self.gy + cells[i + 1] - HIDDEN
                j = y * COLS + self.x + cells[i]
                if y >= 0 and not want[j]:
                    want[j] = 9 + t
            for i in range(0, 8, 2):
                y = self.y + cells[i + 1] - HIDDEN
                if y >= 0:
                    want[y * COLS + self.x + cells[i]] = 1 + t
        shown = self.shown
        if want == shown:
            return
        rows = 0
        for i in range(VISIBLE):
            v = want[i]
            if v != shown[i]:
                shown[i] = v
                _cell(i, v)
                rows |= 1 << (i // COLS)
        self.bands |= rows << (WY // 10)

    def mark(self, y0, y1):
        for b in range(y0 // 10, (y1 + 9) // 10):
            self.bands |= 1 << b

    def draw_stats(self):
        gfx.round_rect(8, 24, 92, 64, 8, ui.PANEL)
        gfx.text("LIVELLO", 54, 30, ui.DIM, "small", align=1)
        gfx.text(str(self.level), 54, 46, ui.CYAN, "large", align=1)
        gfx.round_rect(8, 96, 92, 72, 8, ui.PANEL)
        gfx.text("LINEE", 54, 102, ui.DIM, "small", align=1)
        gfx.text(str(self.lines), 54, 118, ui.TEXT, "title", align=1)
        gfx.bar(20, 152, 68, 6, self.lines % 10 / 10, ui.CYAN, ui.PANEL2, 3)
        self.mark(24, 168)

    def draw_next(self):
        gfx.round_rect(220, 24, 92, 144, 8, ui.PANEL)
        gfx.text("PROSSIMI", 266, 30, ui.DIM, "small", align=1)
        gfx.round_rect(228, 46, 76, 40, 6, ui.PANEL2)
        _preview(self.queue[0], 266, 66, 10)
        _preview(self.queue[1], 266, 110, 8)
        _preview(self.queue[2], 266, 144, 8)
        self.mark(24, 168)

    def draw_all(self):
        gfx.clear(ui.BG)
        common.hud(TITLE, self.score, max(self.best, self.score))
        gfx.fill_rect(WX - 2, WY, 2, 202, WALL)
        gfx.fill_rect(WX + COLS * CELL, WY, 2, 202, WALL)
        gfx.fill_rect(WX, WY + 200, COLS * CELL, 2, WALL)
        shown = self.shown
        for i in range(VISIBLE):
            shown[i] = 255
        self.render()
        self.draw_stats()
        self.draw_next()
        ui.footer(HINTS)
        self.bands = 0
        self.dirty = 0

    def flush(self):
        """Redraws the panels whose values changed, then pushes every touched band."""
        d = self.dirty
        if d & HUD:
            common.hud(TITLE, self.score, max(self.best, self.score))
            self.mark(0, common.HUD_H)
        if d & STATS:
            self.draw_stats()
        if d & NEXT:
            self.draw_next()
        self.dirty = 0
        bands = self.bands
        show = self.sys.show
        b = 0
        while bands:
            if bands & 1:
                start = b
                while bands & 1:
                    bands >>= 1
                    b += 1
                show(start * 10, b * 10)
            bands >>= 1
            b += 1
        self.bands = 0


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
    game = Blocks(sys)
    if not await _start(sys, game):
        return
    tick = common.Ticker(30)
    last = time.ticks_ms()
    while True:
        drop = False
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
                last = time.ticks_ms()
                break
            elif kind == B.PRESS or (kind == B.REPEAT and k in (B.LEFT, B.RIGHT)):
                if k == B.LEFT or k == B.RIGHT:
                    game.shift(-1 if k == B.LEFT else 1)
                elif k == B.UP or k == B.A:
                    if game.rotate():
                        common.sfx(sys, "rotate")
                elif k == B.DOWN:
                    game.soft_step()
                elif k == B.NEXT:
                    game.hard_drop()
                    drop = True
                    break
        now = time.ticks_ms()
        dt = min(100, time.ticks_diff(now, last))
        last = now
        if drop or game.update(dt, sys.buttons.held(B.DOWN)):
            alive = await game.land()
            last = time.ticks_ms()
            if not alive:
                game.flush()
                await game.top_out()
                if await common.game_over(sys, GAME_ID, TITLE, game.score) == "quit":
                    return
                game.reset()
                if not await _start(sys, game):
                    return
                last = time.ticks_ms()
        game.render()
        game.flush()
        common.leds_frame(sys, game.led)
        await tick.wait()
