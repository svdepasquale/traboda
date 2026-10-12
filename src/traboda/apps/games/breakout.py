"""Mattoncini: break the wall with the paddle and the ball. Three lives; every wall
cleared brings a new one and a faster ball. Only the ball, the paddle and the hit
bricks are redrawn each frame, and only their rows are pushed."""

import math

from ... import buttons as B
from ... import gfx, settings, ui
from ...display import rgb
from . import common

GAME_ID = "breakout"
TITLE = "Mattoncini"
ICON = "breakout"
MEDIA_KEYS = True

TOP = common.HUD_H              # the field: rows TOP..BOTTOM-1, the whole width
BOTTOM = ui.FOOTER_Y
COLS = 10
ROWS = 6
BRICK_W = 30                    # on a 32 x 12 pitch
BRICK_H = 10
WALL_Y = TOP + 22
PAD_Y = 204
PAD_H = 6
PAD_W = 48
PAD_SLOW = 5                    # px per frame when a direction is pressed...
PAD_FAST = 10                   # ...accelerating while it is held
NUDGE = 10                      # px per injected tap (no live key state)
BALL = 6
LIVES = 3
MSG_Y = 132
MAX_X = (320 - BALL) << 8       # ball maths in 1/256 px
MIN_Y = TOP << 8
SERVE, PLAY = 0, 1
HINTS = [("◄►", "Muovi"), ("A", "Lancia"), ("►‖", "Pausa")]

# one wall per level, then again with a faster ball; "#" is a brick
WALLS = (
    ("##########", "##########", "##########", "##########", "##########", "##########"),
    ("##.####.##", "##.####.##", "##########", "##########", ".########.", "..######.."),
    ("....##....", "...####...", "..######..", ".########.", "##########", "##########"),
    ("#.#.#.#.#.", ".#.#.#.#.#", "#.#.#.#.#.", ".#.#.#.#.#", "##########", "##########"),
)
ROW_RGB = ((255, 77, 77), (255, 150, 40), (255, 214, 10), (61, 220, 132), (45, 226, 230),
           (170, 110, 255))


def _mix(c, to, k):
    return rgb(c[0] + (to[0] - c[0]) * k // 8, c[1] + (to[1] - c[1]) * k // 8,
               c[2] + (to[2] - c[2]) * k // 8)


_BRICKS = tuple((rgb(*c), _mix(c, (255, 255, 255), 4), _mix(c, (0, 0, 0), 4)) for c in ROW_RGB)
_GLOW = tuple(tuple((r * k // 4, g * k // 4, b * k // 4) for k in range(5)) for r, g, b in ROW_RGB)
_PAD_LIGHT = rgb(255, 150, 190)
_OFF = (0, 0, 0)


def _skip_events(sys):
    """Drops stale key events (common.drain would spin on the HOME of a pending app)."""
    if not sys.pending_app():
        common.drain(sys)


def _ball(x, y):
    gfx.fill_rect(x + 1, y, BALL - 2, BALL, ui.WHITE)
    gfx.fill_rect(x, y + 1, BALL, BALL - 2, ui.WHITE)


class Game:
    def __init__(self, sys):
        self.sys = sys
        self.bricks = bytearray(ROWS * COLS)
        self.spans = [0] * 16           # row bands to push this frame: y0, y1, ...
        self.nspans = 0
        self.heat_row = bytearray(11)   # LED column glow, by brick hits
        self.leds = [_OFF] * 22
        self.reset()

    def reset(self):
        self.score = 0
        self.lives = LIVES
        self.level = 1
        self.serves = 0
        self.pad_x = (320 - PAD_W) // 2
        self.pad_v = 0
        self.pad_dir = 0
        self.heat = bytearray(11)
        self.glowing = True
        self.wall()
        self.serve("Livello 1", ui.YELLOW)

    def wall(self):
        rows = WALLS[(self.level - 1) % len(WALLS)]
        self.left = 0
        for r in range(ROWS):
            for c in range(COLS):
                on = 1 if rows[r][c] == "#" else 0
                self.bricks[r * COLS + c] = on
                self.left += on
        speed = min(7.5, 4.5 + 0.5 * (self.level - 1))
        self.sub = 2 if speed <= 6 else 3          # substeps keep each move under 3 px
        self.step = int(speed * 256) // self.sub

    def serve(self, message, color):
        self.state = SERVE
        self.message = message
        self.message_color = color
        self.bx = (self.pad_x + (PAD_W - BALL) // 2) << 8
        self.by = (PAD_Y - BALL) << 8
        self.vx = self.vy = 0

    # -- drawing ---------------------------------------------------------------------------

    def draw_hud(self):
        common.hud(TITLE, self.score, extra="")
        x = 314 - LIVES * 9
        for i in range(LIVES):
            gfx.text("♥", x + i * 9, 1, ui.ACCENT if i < self.lives else ui.LINE)
        gfx.text("liv %d" % self.level, x - 6, 1, ui.DIM, align=-1)

    def draw_brick(self, r, c):
        x = c * 32 + 1
        y = WALL_Y + r * 12
        base, light, dark = _BRICKS[r]
        gfx.fill_rect(x, y, BRICK_W, BRICK_H, base)
        gfx.hline(x, y, BRICK_W, light)
        gfx.vline(x, y, BRICK_H, light)
        gfx.hline(x + 1, y + BRICK_H - 1, BRICK_W - 1, dark)
        gfx.vline(x + BRICK_W - 1, y + 1, BRICK_H - 1, dark)

    def draw_paddle(self):
        gfx.round_rect(self.pad_x, PAD_Y, PAD_W, PAD_H, 3, ui.ACCENT)
        gfx.hline(self.pad_x + 3, PAD_Y + 1, PAD_W - 6, _PAD_LIGHT)

    def draw_message(self):
        gfx.text(self.message, 160, MSG_Y, self.message_color, "title", align=1)
        gfx.text("A o ▲ per lanciare", 160, MSG_Y + 30, ui.DIM, align=1)

    def draw_all(self):
        gfx.clear(ui.BG)
        self.draw_hud()
        for r in range(ROWS):
            for c in range(COLS):
                if self.bricks[r * COLS + c]:
                    self.draw_brick(r, c)
        self.draw_paddle()
        _ball(self.bx >> 8, self.by >> 8)
        if self.state == SERVE:
            self.draw_message()
        ui.footer(HINTS)

    def paint(self):
        self.draw_all()
        self.sys.show()

    def dirty(self, y0, y1):
        if self.nspans < len(self.spans):
            self.spans[self.nspans] = y0
            self.spans[self.nspans + 1] = y1
            self.nspans += 2

    def flush(self):
        """Pushes the dirty bands, merging the ones that touch."""
        s = self.spans
        n = self.nspans
        i = 0
        while i < n:
            j = i + 2
            while j < n:
                if s[j] <= s[i + 1] + 4 and s[j + 1] >= s[i] - 4:
                    s[i] = min(s[i], s[j])
                    s[i + 1] = max(s[i + 1], s[j + 1])
                    n -= 2
                    s[j] = s[n]
                    s[j + 1] = s[n + 1]
                    j = i + 2
                else:
                    j += 2
            self.sys.show(max(0, s[i]), min(BOTTOM, s[i + 1]))
            i += 2
        self.nspans = 0

    def tick_leds(self):
        """Fades the hit columns; the frame is handed over every time because a flash
        replaces the engine's frame list."""
        if self.glowing:
            self.glowing = False
            for c in range(11):
                h = self.heat[c]
                self.leds[c] = self.leds[11 + c] = _GLOW[self.heat_row[c]][(h + 1) // 2]
                if h:
                    self.heat[c] = h - 1
                    self.glowing = True
        common.leds_frame(self.sys, self.leds)

    # -- physics ---------------------------------------------------------------------------

    def aim(self, angle):
        """Ball direction: angle in radians from straight up, positive to the right."""
        self.vx = int(self.step * math.sin(angle))
        self.vy = -int(self.step * math.cos(angle))

    def launch(self, d):
        self.state = PLAY
        self.serves += 1
        gfx.fill_rect(0, MSG_Y - 2, 320, 50, ui.BG)
        self.dirty(MSG_Y - 2, MSG_Y + 48)
        self.aim(0.45 * d if d else (0.35 if self.serves % 2 else -0.35))

    def smash(self, r, c):
        self.bricks[r * COLS + c] = 0
        self.left -= 1
        self.score += (ROWS - r) * 10
        x = c * 32 + 1
        y = WALL_Y + r * 12
        gfx.fill_rect(x, y, BRICK_W, BRICK_H, ui.BG)
        self.dirty(y, y + BRICK_H)
        col = (x + BRICK_W // 2) * 11 // 320
        self.heat[col] = 8
        self.heat_row[col] = r
        self.glowing = True

    def collide(self, x, y):
        """Smashes every brick the ball would overlap at (x, y); True if any."""
        px = x >> 8
        py = y >> 8
        r0 = (py - WALL_Y) // 12
        r1 = (py + BALL - 1 - WALL_Y) // 12
        if r1 < 0 or r0 >= ROWS:
            return False
        hit = False
        for r in range(max(0, r0), min(ROWS - 1, r1) + 1):
            top = WALL_Y + r * 12
            if py >= top + BRICK_H or py + BALL <= top:
                continue
            for c in range(max(0, (px - 1) // 32), min(COLS - 1, (px + BALL - 2) // 32) + 1):
                if self.bricks[r * COLS + c]:
                    left = c * 32 + 1
                    if px < left + BRICK_W and px + BALL > left:
                        self.smash(r, c)
                        hit = True
        return hit

    def on_paddle(self, bx, by, ny):
        x = bx >> 8
        if x + BALL <= self.pad_x or x >= self.pad_x + PAD_W:
            return False
        return (by >> 8) + BALL <= PAD_Y + 2 and (ny >> 8) + BALL > PAD_Y

    def deflect(self, bx):
        """The further from the paddle centre, the wider the angle; paddle motion adds spin."""
        off = ((bx >> 8) + BALL // 2 - self.pad_x - PAD_W // 2) / (PAD_W // 2 + BALL // 2)
        self.aim(max(-1.1, min(1.1, off * 1.05 + 0.2 * self.pad_dir)))

    def advance(self):
        """Moves the ball one frame. Returns (sound, lost)."""
        bx = self.bx
        by = self.by
        sound = None
        for _ in range(self.sub):
            nx = bx + self.vx
            if nx < 0 or nx > MAX_X:
                nx = -nx if nx < 0 else 2 * MAX_X - nx
                self.vx = -self.vx
                sound = sound or "bounce"
            elif self.collide(nx, by):
                nx = bx
                self.vx = -self.vx
                sound = "hit"
            bx = nx
            ny = by + self.vy
            if ny < MIN_Y:
                ny = 2 * MIN_Y - ny
                self.vy = -self.vy
                sound = sound or "bounce"
            elif self.vy > 0 and self.on_paddle(bx, by, ny):
                ny = (PAD_Y - BALL) << 8
                self.deflect(bx)
                sound = sound or "bounce"
            elif self.collide(bx, ny):
                ny = by
                self.vy = -self.vy
                sound = "hit"
            by = ny
            if (by >> 8) + BALL > BOTTOM:
                break
        self.bx = bx
        self.by = by
        return sound, (by >> 8) + BALL > BOTTOM

    # -- play ------------------------------------------------------------------------------

    def leave(self, choice):
        settings.score(GAME_ID, self.score)
        return choice

    async def banner(self, text, color):
        gfx.round_rect(50, 124, 220, 44, 10, ui.PANEL)
        gfx.round_rect(50, 124, 220, 44, 10, color, False)
        gfx.text(text, 160, 134, color, "title", align=1)
        self.sys.show(124, 168)
        await self.sys.sleep_ms(1000)

    async def lost_ball(self):
        """Returns the game-over choice when that was the last ball, else None."""
        sys = self.sys
        self.lives -= 1
        self.draw_hud()
        sys.show(0, TOP)
        common.leds_flash(sys, (255, 0, 0), 500)
        if not self.lives:
            await sys.sleep_ms(500)
            return await common.game_over(sys, GAME_ID, TITLE, self.score)
        common.sfx(sys, "lose")
        self.serve("Palla persa!", ui.ORANGE)
        self.paint()
        _skip_events(sys)
        return None

    async def cleared(self):
        sys = self.sys
        common.sfx(sys, "win")
        common.leds_flash(sys, (61, 220, 132), 900)
        await self.banner("Muro abbattuto!", ui.GREEN)
        self.level += 1
        self.wall()
        self.serve("Livello %d" % self.level, ui.YELLOW)
        self.paint()
        _skip_events(sys)

    async def run(self):
        sys = self.sys
        self.paint()
        self.tick_leds()
        tick = common.Ticker(30)
        while True:
            launch = False
            nudge = 0
            if sys.pending_app():
                return self.leave("quit")
            for ev in common.drain(sys):
                k, kind = B.key(ev), B.kind(ev)
                if kind == sys.REDRAW:
                    self.paint()
                elif kind == sys.HOME:
                    return self.leave("quit")
                elif common.wants_pause(ev) or sys.is_back(ev):
                    choice = await common.pause_menu(sys, TITLE)
                    if choice != "resume" or sys.pending_app():
                        return self.leave("quit" if sys.pending_app() else choice)
                    if self.state == PLAY:
                        await common.countdown(sys, self.draw_all)
                    else:
                        self.paint()
                    _skip_events(sys)
                    break
                elif kind == B.PRESS and k in (B.A, B.UP):
                    launch = True
                elif kind in (B.PRESS, B.REPEAT) and k in (B.LEFT, B.RIGHT):
                    nudge = NUDGE if k == B.RIGHT else -NUDGE

            d = sys.buttons.held(B.RIGHT) - sys.buttons.held(B.LEFT)
            if d:
                self.pad_v = min(PAD_FAST, self.pad_v + 1) if d == self.pad_dir else PAD_SLOW
                dx = d * self.pad_v
            else:
                dx = nudge
                d = (nudge > 0) - (nudge < 0)
            self.pad_dir = d
            old_pad = self.pad_x
            self.pad_x = max(0, min(320 - PAD_W, self.pad_x + dx))
            ox = self.bx >> 8
            oy = self.by >> 8
            sound = None
            lost = False
            if self.state == SERVE:
                self.bx = (self.pad_x + (PAD_W - BALL) // 2) << 8
                if launch:
                    self.launch(d)
            else:
                sound, lost = self.advance()

            if old_pad != self.pad_x:
                gfx.fill_rect(old_pad, PAD_Y, PAD_W, PAD_H, ui.BG)
            gfx.fill_rect(ox, oy, BALL, BALL, ui.BG)
            self.draw_paddle()
            nx = self.bx >> 8
            ny = self.by >> 8
            if not lost:
                _ball(nx, ny)
            self.dirty(PAD_Y, PAD_Y + PAD_H)
            self.dirty(min(oy, ny), max(oy, ny) + BALL)
            if sound == "hit":
                self.draw_hud()
                self.dirty(0, TOP)
            self.flush()
            self.tick_leds()
            if sound:
                common.sfx(sys, sound)
            if lost:
                choice = await self.lost_ball()
                if choice:
                    return choice
            elif not self.left:
                await self.cleared()
            await tick.wait()


async def main(sys):
    game = Game(sys)
    while await game.run() == "restart":
        game.reset()
