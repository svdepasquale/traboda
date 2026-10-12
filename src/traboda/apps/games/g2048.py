"""2048: slide the tiles with the D-pad, equal tiles merge into their sum. Make a 2048
tile to win, then keep going if you like. The board is redrawn only after a move, with a
short slide and pop that is skipped when the next key is already waiting."""

import random

from ... import buttons as B
from ... import gfx, settings, ui
from ...display import rgb
from . import common

GAME_ID = "g2048"
TITLE = "2048"
ICON = "2048"
MEDIA_KEYS = True

TILE = 44
GAP = 4
SIZE = 4 * TILE + 5 * GAP
BX = (320 - SIZE) // 2
BY = common.HUD_H + (ui.FOOTER_Y - common.HUD_H - SIZE) // 2
WIN = 11                    # exponent of the 2048 tile
CARD_W = BX - 12
HINTS = [("▲▼◄►", "Sposta"), ("►‖", "Pausa")]

# the four lines of cells for each direction, starting from the edge the tiles slide to
LINES = {
    B.LEFT: tuple(tuple(r * 4 + c for c in range(4)) for r in range(4)),
    B.RIGHT: tuple(tuple(r * 4 + 3 - c for c in range(4)) for r in range(4)),
    B.UP: tuple(tuple(r * 4 + c for r in range(4)) for c in range(4)),
    B.DOWN: tuple(tuple((3 - r) * 4 + c for r in range(4)) for c in range(4)),
}

# by exponent (2, 4, 8...): tile colour, and True when its number is drawn dark
_TILES = (
    ((70, 82, 140), False),
    ((96, 104, 186), False),
    ((45, 150, 215), False),
    ((45, 205, 200), True),
    ((61, 220, 132), True),
    ((175, 228, 60), True),
    ((255, 214, 10), True),
    ((255, 168, 30), True),
    ((255, 120, 40), True),
    ((255, 77, 77), False),
    ((255, 45, 111), False),
    ((190, 70, 255), False),
    ((236, 238, 245), True),
)
_FILL = tuple(rgb(*c) for c, _ in _TILES)
_INK = tuple(ui.BG if dark else ui.WHITE for _, dark in _TILES)
_EMPTY = rgb(34, 40, 68)
_OFF = (0, 0, 0)


def slide(cells, lines, motion=None, merged=None):
    """One move on cells (16 exponents, 0 = empty) with the original rules: tiles slide to
    the edge and each pair of equal neighbours merges once, the pair nearest the edge
    first. Returns (moved, points). motion collects (from, to, exponent) for every tile,
    merged the cells that received a merge."""
    moved = False
    points = 0
    for line in lines:
        n = 0               # cells filled so far along the line
        last = 0            # exponent at line[n - 1] while it can still take a merge
        for i in line:
            e = cells[i]
            if not e:
                continue
            cells[i] = 0
            if e == last:
                to = line[n - 1]
                cells[to] = e + 1
                points += 1 << (e + 1)
                last = 0
                if merged is not None:
                    merged.append(to)
            else:
                to = line[n]
                cells[to] = e
                last = e
                n += 1
            if to != i:
                moved = True
            if motion is not None:
                motion.append((i, to, e))
    return moved, points


def spawn(cells):
    """A 2 (90 %) or a 4 on a random free cell; returns the cell or -1."""
    free = [i for i in range(16) if not cells[i]]
    if not free:
        return -1
    i = free[random.randrange(len(free))]
    cells[i] = 1 if random.random() < 0.9 else 2
    return i


def can_move(cells):
    for i in range(16):
        e = cells[i]
        if not e or (i % 4 < 3 and cells[i + 1] == e) or (i < 12 and cells[i + 4] == e):
            return True
    return False


def new_board():
    cells = [0] * 16
    spawn(cells)
    spawn(cells)
    return cells


def _skip_events(sys):
    """Drops stale key events (common.drain would spin on the HOME of a pending app)."""
    if not sys.pending_app():
        common.drain(sys)


def _xy(i):
    return BX + GAP + (i % 4) * (TILE + GAP), BY + GAP + (i // 4) * (TILE + GAP)


def _font(digits, size):
    for name in ("large", "title", "text", "small"):
        f = gfx.font(name)
        if digits * f.w <= size - 4 and f.h <= size - 8:
            break
    return f


def _tile(x, y, e, size=TILE):
    """The tile of exponent e in the cell whose corner is (x, y), size px wide, centred."""
    c = min(e, len(_TILES)) - 1
    o = (TILE - size) // 2
    gfx.round_rect(x + o, y + o, size, size, 6 if size > 30 else 4, _FILL[c])
    label = str(1 << e)
    f = _font(len(label), size)
    gfx.text(label, x + TILE // 2, y + (TILE - f.h) // 2 + 1, _INK[c], f, align=1)


class Game:
    def __init__(self, sys):
        self.sys = sys
        self.leds = [_OFF] * 22
        self.reset()

    def reset(self):
        self.cells = new_board()
        self.score = 0
        self.moves = 0
        self.won = False
        self.best = settings.score(GAME_ID)

    # -- drawing ---------------------------------------------------------------------------

    def draw_hud(self):
        common.hud(TITLE, self.score, max(self.best, self.score))

    def draw_cards(self):
        """Moves on the left, the highest tile as a small tile on the right."""
        right = 320 - 6 - CARD_W
        for x, label in ((6, "mosse"), (right, "max")):
            gfx.round_rect(x, BY, CARD_W, 52, 6, ui.PANEL)
            gfx.text(label, x + CARD_W // 2, BY + 6, ui.DIM, "small", align=1)
        gfx.text(str(self.moves), 6 + CARD_W // 2, BY + 26, ui.TEXT, align=1)
        top = max(self.cells)
        c = min(top, len(_TILES)) - 1
        label = str(1 << top)
        gfx.round_rect(right + 4, BY + 22, CARD_W - 8, 24, 4, _FILL[c])
        big = len(label) * 8 <= CARD_W - 10
        gfx.text(label, right + CARD_W // 2, BY + (26 if big else 28), _INK[c],
                 "text" if big else "small", align=1)

    def draw_grid(self):
        gfx.round_rect(BX, BY, SIZE, SIZE, 8, ui.PANEL)
        for i in range(16):
            x, y = _xy(i)
            gfx.round_rect(x, y, TILE, TILE, 6, _EMPTY)

    def draw_board(self, grow=(), new=-1):
        self.draw_grid()
        for i in range(16):
            e = self.cells[i]
            if e:
                x, y = _xy(i)
                _tile(x, y, e, TILE + 6 if i in grow else 24 if i == new else TILE)

    def paint(self):
        gfx.clear(ui.BG)
        self.draw_hud()
        self.draw_cards()
        self.draw_board()
        ui.footer(HINTS)
        self.sys.show()

    def push_board(self):
        self.sys.show(BY, BY + SIZE)

    def show_leds(self):
        top = max(self.cells)
        for c in range(11):
            self.leds[c] = self.leds[11 + c] = _TILES[c][0] if c < top else _OFF
        common.leds_frame(self.sys, self.leds)

    # -- play ------------------------------------------------------------------------------

    async def animate(self, motion, merged, new):
        """Slides the tiles in two steps, pops the merged ones and grows the new one."""
        tick = common.Ticker(40)
        for step in (1, 2):
            self.draw_grid()
            for src, dst, e in motion:
                sx, sy = _xy(src)
                dx, dy = _xy(dst)
                _tile(sx + (dx - sx) * step // 3, sy + (dy - sy) * step // 3, e)
            self.push_board()
            await tick.wait()
        self.draw_board(merged, new)
        self.push_board()
        await tick.wait()

    async def move(self, k):
        sys = self.sys
        motion = []
        merged = []
        moved, points = slide(self.cells, LINES[k], motion, merged)
        if not moved:
            return
        self.moves += 1
        self.score += points
        new = spawn(self.cells)
        if not any(B.kind(e) == B.PRESS for e in sys.buttons.queue):
            await self.animate(motion, merged, new)
        self.draw_cards()
        self.draw_board()
        self.push_board()
        if points:
            self.draw_hud()
            sys.show(0, common.HUD_H)
        self.show_leds()
        common.sfx(sys, "eat" if merged else "move")

    async def run(self):
        sys = self.sys
        self.paint()
        self.show_leds()
        while True:
            ev = await sys.event()
            if ev is None:
                continue
            k, kind = B.key(ev), B.kind(ev)
            if kind == sys.REDRAW:
                self.paint()
                continue
            if kind == sys.HOME:
                settings.score(GAME_ID, self.score)
                return "quit"
            if common.wants_pause(ev) or sys.is_back(ev):
                choice = await common.pause_menu(sys, TITLE)
                if choice != "resume" or sys.pending_app():
                    settings.score(GAME_ID, self.score)
                    return "quit" if sys.pending_app() else choice
                self.paint()
                _skip_events(sys)
                continue
            if kind != B.PRESS or k not in LINES:
                continue
            await self.move(k)
            if not self.won and max(self.cells) >= WIN:
                self.won = True
                common.sfx(sys, "win")
                common.leds_flash(sys, (255, 214, 10), 1200)
                choice = await ui.dialog(sys, "2048!", "Punti: %d\nContinui per un record?" % self.score,
                                         ("Continua", "Basta"), accent=ui.YELLOW)
                if choice == 1:
                    return await common.game_over(sys, GAME_ID, TITLE, self.score, won=True)
                self.paint()
                _skip_events(sys)
            if not can_move(self.cells):
                await sys.sleep_ms(700)
                return await common.game_over(sys, GAME_ID, TITLE, self.score, won=self.won)


async def main(sys):
    game = Game(sys)
    while await game.run() == "restart":
        game.reset()
