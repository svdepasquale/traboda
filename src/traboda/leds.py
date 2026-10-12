"""The 22 RGB LEDs across the top of the badge, with an effect engine.

Two rows of 11. The strip sits behind a buffer powered from its own rail, so the rail is
switched off whenever every LED is dark. Brightness is capped: 22 LEDs at full white would
pull more than the 5 V boost can give.
"""

import math
import random
import time
from machine import Pin

from . import board, power

N = board.LED_COUNT
COLS = 11
# Chain index of each position, row by row, left to right (row 0 = top). Checked on the
# badge: the chain starts bottom-left, runs along the bottom row, then back along the top.
ORDER = tuple(range(21, 10, -1)) + tuple(range(11))
MAX_LEVEL = 0.6

EFFECTS = ("off", "solid", "breathe", "rainbow", "wave", "comet", "scanner", "sparkle",
           "fire", "police", "vu")
EFFECT_NAMES = {"off": "Spento", "solid": "Fisso", "breathe": "Respiro", "rainbow": "Arcobaleno",
                "wave": "Onda", "comet": "Cometa", "scanner": "Scanner", "sparkle": "Scintille",
                "fire": "Fuoco", "police": "Polizia", "vu": "VU musica"}


def hsv(h, s=1.0, v=1.0):
    """h in [0, 1). Returns (r, g, b) 0-255."""
    h = (h % 1.0) * 6
    i = int(h)
    f = h - i
    p = v * (1 - s)
    q = v * (1 - s * f)
    t = v * (1 - s * (1 - f))
    r, g, b = ((v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q))[i % 6]
    return int(r * 255), int(g * 255), int(b * 255)


class Leds:
    def __init__(self):
        import neopixel
        self.np = neopixel.NeoPixel(Pin(board.LED_DATA), N)
        self.frame = [(0, 0, 0)] * N         # by position (ORDER applied on write)
        self.effect = "off"
        self.color = (255, 45, 111)
        self.speed = 1.0
        self.level = 0.25                    # 0..1 of MAX_LEVEL
        self.vu = (0.0, 0.0)                 # audio levels fed by the player
        self.progress = None                 # 0..1 overrides the effect (timers)
        self._flash = None                   # (color, until_ms, period)
        self._rail = False
        self._t0 = time.ticks_ms()
        self._sparks = [0.0] * N
        self._heat = [0] * N

    # -- public ----------------------------------------------------------------------------

    def set_effect(self, name, color=None):
        """name: one of EFFECTS, or "custom" (the engine leaves `frame` to the caller)."""
        self.effect = name if name in EFFECTS or name == "custom" else "off"
        if color is not None:
            self.color = tuple(color)

    def flash(self, color=(255, 255, 255), ms=600, period=150):
        """Blinks every LED for ms, on top of the running effect."""
        self._flash = (tuple(color), time.ticks_add(time.ticks_ms(), ms), period)

    def off(self, now=False):
        self.effect = "off"
        self.progress = None
        self._flash = None
        if now:
            self.frame = [(0, 0, 0)] * N
            self._write()

    def fill(self, color):
        self.frame = [tuple(color)] * N

    # -- engine ----------------------------------------------------------------------------

    def tick(self):
        """Renders one frame; call at ~30 Hz."""
        t = time.ticks_diff(time.ticks_ms(), self._t0) / 1000 * self.speed
        if self.progress is not None:
            self._progress(self.progress)
        else:
            getattr(self, "_fx_" + self.effect, self._fx_off)(t)
        frame = self.frame
        if self._flash:
            color, until, period = self._flash
            now = time.ticks_ms()
            if time.ticks_diff(until, now) <= 0:
                self._flash = None
            elif (now // period) % 2 == 0:
                frame = [color] * N       # shown on top; the effect's own frame survives
        self._write(frame)

    def _write(self, frame=None):
        frame = self.frame if frame is None else frame
        scale = self.level * MAX_LEVEL
        lit = False
        np = self.np
        for pos in range(N):
            r, g, b = frame[pos]
            r = int(r * scale)
            g = int(g * scale)
            b = int(b * scale)
            if r or g or b:
                lit = True
            np[ORDER[pos]] = (r, g, b)
        if lit:
            if not self._rail:
                power.led_rail(True)
                self._rail = True
            np.write()
        elif self._rail:
            np.write()               # latch black before the buffer loses power
            power.led_rail(False)
            self._rail = False

    def _progress(self, fraction):
        """Fills the top row, then the bottom one, left to right."""
        lit = fraction * N
        c = self.color
        frame = []
        for pos in range(N):
            if pos < int(lit):
                frame.append(c)
            elif pos < lit:
                f = lit - int(lit)
                frame.append((int(c[0] * f), int(c[1] * f), int(c[2] * f)))
            else:
                frame.append((0, 0, 0))
        self.frame = frame

    # -- effects (t in seconds) ------------------------------------------------------------

    def _fx_off(self, t):
        self.frame = [(0, 0, 0)] * N

    def _fx_custom(self, t):
        pass

    def _fx_solid(self, t):
        self.frame = [self.color] * N

    def _fx_breathe(self, t):
        k = (1 - math.cos(t * 2.4)) / 2
        k = 0.08 + 0.92 * k * k
        r, g, b = self.color
        self.frame = [(int(r * k), int(g * k), int(b * k))] * N

    def _fx_rainbow(self, t):
        self.frame = [hsv(t * 0.15 + (pos % COLS) / COLS) for pos in range(N)]

    def _fx_wave(self, t):
        r, g, b = self.color
        frame = []
        for pos in range(N):
            col = pos % COLS
            row = pos // COLS
            k = (1 + math.sin(t * 4 - col * 0.7 + row * 1.6)) / 2
            frame.append((int(r * k), int(g * k), int(b * k)))
        self.frame = frame

    def _fx_comet(self, t):
        head = (t * 9) % (2 * COLS - 2)
        if head >= COLS:
            head = 2 * COLS - 2 - head
        r, g, b = self.color
        frame = []
        for pos in range(N):
            d = abs(pos % COLS - head)
            k = max(0.0, 1 - d / 3.5)
            frame.append((int(r * k), int(g * k), int(b * k)))
        self.frame = frame

    def _fx_scanner(self, t):
        head = (math.sin(t * 3) + 1) / 2 * (COLS - 1)
        frame = []
        for pos in range(N):
            k = max(0.0, 1 - abs(pos % COLS - head) / 2.2)
            frame.append((int(255 * k), 0, 0))
        self.frame = frame

    def _fx_sparkle(self, t):
        sparks = self._sparks
        for i in range(N):
            sparks[i] *= 0.82
        if random.random() < 0.6:
            sparks[random.randrange(N)] = 1.0
        r, g, b = self.color
        self.frame = [(int(r * s + 20 * s), int(g * s + 20 * s), int(b * s + 20 * s)) for s in sparks]

    def _fx_fire(self, t):
        heat = self._heat
        frame = []
        for i in range(N):
            heat[i] = max(0, min(255, heat[i] - random.randrange(0, 40) + random.randrange(0, 46)))
            h = heat[i]
            frame.append((255 if h > 60 else h * 4, max(0, h - 90), max(0, h - 200) // 2))
        self.frame = frame

    def _fx_police(self, t):
        phase = int(t * 6) % 4
        left = (255, 0, 0) if phase in (0, 2) else (0, 0, 0)
        right = (0, 0, 255) if phase in (1, 3) else (0, 0, 0)
        self.frame = [left if pos % COLS < COLS // 2 else right for pos in range(N)]

    def _fx_vu(self, t):
        frame = []
        for pos in range(N):
            level = self.vu[pos // COLS]
            col = pos % COLS
            if col < level * COLS:
                frame.append(hsv(0.33 - 0.33 * col / (COLS - 1)))
            else:
                frame.append((0, 0, 0))
        self.frame = frame
