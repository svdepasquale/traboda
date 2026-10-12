"""Vola!: one key to flap between the pipes. The field is never scrolled as a whole: the
night sky is drawn once into a background buffer, each frame blits back only the strip
a pipe just left and the bird's column, redraws the pipes as rectangles and the bird as a
sprite, then pushes the field band."""

import framebuf
import random

from ... import buttons as B
from ... import gfx, settings, ui
from ...display import rgb
from . import common

GAME_ID = "flappy"
TITLE = "Vola!"
ICON = "flappy"
MEDIA_KEYS = True

TOP = common.HUD_H
GROUND = 196                    # first ground row: scrolling grass, then still earth
STRIPE = 8
FIELD_H = GROUND - TOP
BIRD_X = 64
BIRD_W = 26
BIRD_H = 20
PIPE_W = 40                     # the cap; the body is 3 px narrower on each side
CAP_H = 12
PIPES = 3
SPACING = 150
GAP_MAX = 72                    # gap height, shrinking with the score
GAP_MIN = 56
SPEED = 614                     # pipe speed in 1/256 px per frame...
SPEED_MAX = 921                 # ...up to 3.6 px (the erase strip is 4 px wide)
GRAVITY = 104
FLAP = -1310
MAX_FALL = 2048
PERIOD = 16                     # of the grass stripes
READY, PLAY, DEAD = 0, 1, 2
HINTS = [("A", "Vola"), ("►‖", "Pausa")]

_KEY = rgb(255, 0, 255)         # transparent in the bird sprites
_INK = rgb(48, 26, 20)
_PIPE = (rgb(64, 192, 92), rgb(150, 240, 160), rgb(32, 124, 64), rgb(12, 52, 30))
_GRASS = (rgb(96, 206, 84), rgb(64, 160, 62), rgb(170, 240, 130))
_EARTH = (rgb(112, 78, 58), rgb(84, 56, 44))
_BOB = (0, 1, 2, 3, 3, 3, 2, 1, 0, -1, -2, -3, -3, -3, -2, -1)
_SWEEP = ((45, 226, 230), (18, 100, 104), (5, 34, 36))
_GREEN = (61, 220, 132)
_GOLD = (255, 214, 10)
_OFF = (0, 0, 0)


def _skip_events(sys):
    """Drops stale key events (common.drain would spin on the HOME of a pending app)."""
    if not sys.pending_app():
        common.drain(sys)


def _sky():
    """The still background of the field: gradient, stars, moon, skyline."""
    buf = bytearray(320 * FIELD_H * 2)
    f = framebuf.FrameBuffer(buf, 320, FIELD_H, framebuf.RGB565)
    for y in range(FIELD_H):
        f.hline(0, y, 320, rgb(14 + 70 * y // FIELD_H, 16 + 22 * y // FIELD_H,
                                44 + 54 * y // FIELD_H))
    for _ in range(70):
        f.pixel(random.randrange(320), random.randrange(FIELD_H * 3 // 5),
                rgb(120, 124, 170) if random.random() < 0.7 else rgb(236, 238, 245))
    f.ellipse(262, 30, 13, 13, rgb(250, 238, 196), True)
    f.ellipse(257, 26, 3, 3, rgb(222, 208, 170), True)
    f.ellipse(267, 35, 4, 3, rgb(222, 208, 170), True)
    for color, lo, hi, base in ((rgb(46, 30, 86), 30, 70, 0), (rgb(26, 18, 54), 14, 42, 1)):
        x = -random.randrange(20)
        while x < 320:
            w = random.randrange(16, 34)
            h = random.randrange(lo, hi)
            f.fill_rect(x, FIELD_H - h, w - base, h, color)
            if base:
                for wy in range(FIELD_H - h + 4, FIELD_H - 4, 6):
                    for wx in range(x + 3, x + w - 5, 5):
                        if random.random() < 0.25:
                            f.fill_rect(wx, wy, 2, 2, rgb(255, 214, 120))
            x += w
    return buf, f


def _stripes():
    """The grass band, PERIOD px wider than the screen so it scrolls by blitting views."""
    w = 320 + PERIOD
    buf = bytearray(w * STRIPE * 2)
    f = framebuf.FrameBuffer(buf, w, STRIPE, framebuf.RGB565)
    f.fill(_GRASS[0])
    for x in range(-STRIPE, w, PERIOD):
        for y in range(1, STRIPE):
            f.hline(x + y, y, PERIOD // 2, _GRASS[1])
    f.hline(0, 0, w, _GRASS[2])
    mv = memoryview(buf)
    return [framebuf.FrameBuffer(mv[o * 2:], 320, STRIPE, framebuf.RGB565, w) for o in range(PERIOD)]


def _bird(wing):
    buf = bytearray(BIRD_W * BIRD_H * 2)
    f = framebuf.FrameBuffer(buf, BIRD_W, BIRD_H, framebuf.RGB565)
    f.fill(_KEY)
    f.ellipse(12, 11, 11, 8, _INK, True)
    f.ellipse(12, 11, 10, 7, rgb(255, 206, 20), True)
    f.ellipse(11, 15, 7, 3, rgb(255, 236, 140), True)
    f.ellipse(17, 7, 4, 4, _INK, True)
    f.ellipse(17, 7, 3, 3, ui.WHITE, True)
    f.fill_rect(18, 6, 2, 3, _INK)
    f.fill_rect(19, 10, 7, 5, _INK)
    f.fill_rect(20, 11, 5, 1, rgb(255, 120, 40))
    f.fill_rect(20, 13, 4, 1, rgb(235, 90, 30))
    f.ellipse(6, 11 + wing, 6, 4, _INK, True)
    f.ellipse(6, 11 + wing, 5, 3, rgb(255, 250, 232), True)
    return f


def _body(x, y0, y1):
    h = y1 - y0
    if h > 0:
        mid, light, dark, edge = _PIPE
        x += 3
        w = PIPE_W - 6
        gfx.fill_rect(x, y0, w, h, mid)
        gfx.fill_rect(x + 4, y0, 6, h, light)
        gfx.vline(x + 12, y0, h, light)
        gfx.fill_rect(x + w - 8, y0, 6, h, dark)
        gfx.vline(x, y0, h, edge)
        gfx.vline(x + w - 1, y0, h, edge)


def _cap(x, y):
    mid, light, dark, edge = _PIPE
    gfx.fill_rect(x, y, PIPE_W, CAP_H, mid)
    gfx.fill_rect(x + 4, y + 1, 7, CAP_H - 2, light)
    gfx.fill_rect(x + PIPE_W - 9, y + 1, 7, CAP_H - 2, dark)
    gfx.rect(x, y, PIPE_W, CAP_H, edge)


class Game:
    def __init__(self, sys):
        self.sys = sys
        buf, self.sky = _sky()
        mv = memoryview(buf)
        # background columns: 4 px wide ones to erase behind each pipe, and the bird's
        self.cols = [framebuf.FrameBuffer(mv[x * 2:], 4, FIELD_H, framebuf.RGB565, 320)
                     for x in range(317)]
        self.bird_col = framebuf.FrameBuffer(mv[BIRD_X * 2:], BIRD_W, FIELD_H, framebuf.RGB565, 320)
        self.stripes = _stripes()
        self.sprites = (_bird(-3), _bird(0), _bird(3))
        self.px = [0] * PIPES           # pipe x, 1/256 px
        self.gap = [0] * PIPES          # gap top row
        self.gap_h = [0] * PIPES
        self.scored = bytearray(PIPES)
        self.leds = [_OFF] * 22
        self.reset()

    def reset(self):
        self.score = 0
        self.best = settings.score(GAME_ID)
        self.state = READY
        self.by = (TOP + 70) << 8
        self.vy = 0
        self.hover = self.by
        self.speed = SPEED
        self.ground = 0
        self.frame = 0
        self.last_gap = (TOP + GROUND - GAP_MAX) // 2
        for i in range(PIPES):
            self.px[i] = (440 + i * SPACING) << 8
            self.new_gap(i)
        self.sweep = -9
        self.progress_leds()

    def new_gap(self, i):
        h = max(GAP_MIN, GAP_MAX - self.score)
        lo = TOP + 24
        hi = GROUND - 24 - h
        g = random.randrange(lo, hi + 1)
        g = max(self.last_gap - 64, min(self.last_gap + 64, g))     # reachable from the last
        g = max(lo, min(hi, g))
        self.gap[i] = self.last_gap = g
        self.gap_h[i] = h
        self.scored[i] = 0

    # -- drawing ---------------------------------------------------------------------------

    def draw_hud(self):
        common.hud(TITLE, self.score, max(self.best, self.score))

    def draw_pipes(self):
        for i in range(PIPES):
            x = self.px[i] >> 8
            if x < 320 and x + PIPE_W > 0:
                top = self.gap[i]
                bottom = top + self.gap_h[i]
                _body(x, TOP, top - CAP_H)
                _cap(x, top - CAP_H)
                _cap(x, bottom)
                _body(x, bottom + CAP_H, GROUND)

    def draw_bird(self):
        if self.state == DEAD:
            wing = 1
        elif self.state == READY or self.vy < 0:
            wing = self.frame // 3 % 3
        else:
            wing = 1
        gfx.fb.blit(self.sprites[wing], BIRD_X, self.by >> 8, _KEY)

    def draw_panel(self):
        gfx.round_rect(124, 66, 172, 60, 10, ui.PANEL)
        gfx.round_rect(124, 66, 172, 60, 10, ui.ACCENT, False)
        gfx.text("Pronto?", 210, 74, ui.YELLOW, "title", align=1)
        gfx.text("A, ▲ o ►► per volare", 210, 102, ui.DIM, align=1)

    def draw_field(self):
        """Pipes, bird, panel and grass over a background already restored."""
        self.draw_pipes()
        self.draw_bird()
        if self.state == READY:
            self.draw_panel()
        gfx.fb.blit(self.stripes[self.ground >> 8], 0, GROUND)

    def draw_all(self):
        self.draw_hud()
        gfx.fb.blit(self.sky, 0, TOP)
        self.draw_field()
        y = GROUND + STRIPE
        gfx.fill_rect(0, y, 320, ui.FOOTER_Y - y, _EARTH[0])
        gfx.hline(0, y, 320, _EARTH[1])
        for x in range(0, 320, 24):
            gfx.fill_rect(x + (x // 24 % 3) * 5, y + 5 + (x // 24 % 2) * 6, 6, 2, _EARTH[1])
        ui.footer(HINTS)

    def paint(self):
        self.draw_all()
        self.sys.show()

    def render(self):
        gfx.fb.blit(self.bird_col, BIRD_X, TOP)
        self.draw_field()
        self.sys.show(TOP, GROUND + STRIPE)

    def progress_leds(self):
        """Bottom row: how close the score is to the record, gold once it is beaten."""
        best = self.best
        n = min(11, self.score * 11 // best if best else self.score)
        color = _GOLD if best and self.score > best else _GREEN
        for c in range(11):
            self.leds[11 + c] = color if c < n else _OFF

    def show_leds(self):
        """Top row: a sweep for every pipe passed. Handed over every frame because a
        flash replaces the engine's frame list."""
        s = self.sweep
        for c in range(11):
            d = c - s if c > s else s - c
            self.leds[c] = _SWEEP[d] if d < 3 else _OFF
        if -3 < s < 14:
            self.sweep = s + 1
        common.leds_frame(self.sys, self.leds)

    # -- physics ---------------------------------------------------------------------------

    def scroll(self):
        """Moves the pipes and the grass, erasing the strip each pipe leaves behind."""
        fb = gfx.fb
        for i in range(PIPES):
            self.px[i] -= self.speed
            x = self.px[i] >> 8
            right = x + PIPE_W
            if right < 320:
                c = max(0, min(316, right))
                fb.blit(self.cols[c], c, TOP)
            if right <= 0:
                self.px[i] = max(self.px) + (SPACING << 8)
                self.new_gap(i)
        self.ground = (self.ground + self.speed) % (PERIOD << 8)

    def hits(self):
        y = self.by >> 8
        y0 = y + 3
        y1 = y + BIRD_H - 3
        x0 = BIRD_X + 3
        x1 = BIRD_X + BIRD_W - 3
        for i in range(PIPES):
            x = self.px[i] >> 8
            if x1 <= x or x0 >= x + PIPE_W:
                continue
            top = self.gap[i]
            bottom = top + self.gap_h[i]
            if y0 >= top and y1 <= bottom:
                continue
            if x1 > x + 3 and x0 < x + PIPE_W - 3:
                return True             # the body runs the whole height
            if (y0 < top and y1 > top - CAP_H) or (y1 > bottom and y0 < bottom + CAP_H):
                return True             # the wider cap
        return False

    def passed(self):
        """Scores the pipes whose middle went past the bird's."""
        for i in range(PIPES):
            if not self.scored[i] and (self.px[i] >> 8) + PIPE_W // 2 < BIRD_X + BIRD_W // 2:
                self.scored[i] = 1
                self.score += 1
                self.speed = min(SPEED_MAX, SPEED + 26 * (self.score // 5))
                self.sweep = -2
                self.progress_leds()
                self.draw_hud()
                self.sys.show(0, TOP)

    def fall(self):
        self.vy = min(MAX_FALL, self.vy + GRAVITY)
        self.by += self.vy
        if self.by < TOP << 8:
            self.by = TOP << 8
            self.vy = 0
        if (self.by >> 8) + BIRD_H >= GROUND:
            self.by = (GROUND - BIRD_H) << 8
            return True
        return False

    # -- play ------------------------------------------------------------------------------

    def leave(self, choice):
        settings.score(GAME_ID, self.score)
        return choice

    async def run(self):
        sys = self.sys
        self.paint()
        tick = common.Ticker(30)
        while True:
            flap = False
            if sys.pending_app():
                return self.leave("quit")
            for ev in common.drain(sys):
                k, kind = B.key(ev), B.kind(ev)
                if kind == sys.REDRAW:
                    self.paint()
                elif kind == sys.HOME:
                    return self.leave("quit")
                elif self.state != DEAD and (common.wants_pause(ev) or sys.is_back(ev)):
                    choice = await common.pause_menu(sys, TITLE)
                    if choice != "resume" or sys.pending_app():
                        return self.leave("quit" if sys.pending_app() else choice)
                    if self.state == PLAY:
                        self.state = READY      # hover until the next flap
                        self.hover = self.by
                    self.paint()
                    _skip_events(sys)
                    break
                elif kind == B.PRESS and k in (B.A, B.UP, B.NEXT):
                    flap = True

            self.frame += 1
            if self.state == READY:
                self.by = self.hover + (_BOB[self.frame // 2 % 16] << 8)
                self.ground = (self.ground + self.speed) % (PERIOD << 8)
                if flap:
                    self.state = PLAY
                    self.paint()
            if self.state == PLAY:
                if flap:
                    self.vy = FLAP
                    common.sfx(sys, "bounce")
                self.scroll()
                landed = self.fall()
                self.passed()
                if landed or self.hits():
                    self.state = DEAD
                    common.sfx(sys, "hit")
                    common.leds_flash(sys, (255, 0, 0), 500)
            elif self.state == DEAD and self.fall():
                self.render()
                self.show_leds()
                await sys.sleep_ms(500)
                _skip_events(sys)
                return await common.game_over(sys, GAME_ID, TITLE, self.score)
            self.render()
            self.show_leds()
            await tick.wait()


async def main(sys):
    game = Game(sys)
    while await game.run() == "restart":
        game.reset()
