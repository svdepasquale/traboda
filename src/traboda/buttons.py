"""The badge's nine keys, as press / release / repeat / long-press events.

Eight keys sit on the AW9523B (read over I2C only when its INTN line says something
changed, plus a slow safety poll); the rewind key is GPIO0. The board debounces every key
with an RC filter, so edges are taken as they come.

Events are small ints, kind << 4 | key, so the queue never allocates.
"""

import time
from machine import Pin

from . import board

UP, DOWN, LEFT, RIGHT, A, B, PLAY, PREV, NEXT = range(9)
NAMES = ("up", "down", "left", "right", "A", "B", "play", "prev", "next")
GLYPHS = ("▲", "▼", "◄", "►", "A", "B", "►‖", "◄◄", "►►")

PRESS = 1
RELEASE = 2
REPEAT = 3
LONG = 4
CLICK = 7     # released before LONG fired (synthesized by the core)

REPEAT_DELAY = 380
REPEAT_EVERY = 90
LONG_AFTER = 700
_REPEATS = 1 << UP | 1 << DOWN | 1 << LEFT | 1 << RIGHT

# expander bit -> key
_MAP = (
    (board.EX_UP, UP), (board.EX_DOWN, DOWN), (board.EX_LEFT, LEFT), (board.EX_RIGHT, RIGHT),
    (board.EX_A, A), (board.EX_B, B), (board.EX_PLAY, PLAY), (board.EX_NEXT, NEXT),
)


def kind(ev):
    return ev >> 4


def key(ev):
    return ev & 15


class Buttons:
    def __init__(self, expander):
        self.ex = expander
        self.prev_pin = Pin(board.BUTTON_PREV, Pin.IN, Pin.PULL_UP)
        self.int_pin = Pin(board.EXPANDER_INT, Pin.IN, Pin.PULL_UP)
        self.state = 0              # bitmask of keys held now
        self._ex_keys = 0
        self._since = [0] * 9       # ms when each key went down
        self._next_repeat = [0] * 9
        self._long_sent = 0
        self._last_read = 0
        self.queue = []
        self.last_activity = time.ticks_ms()
        self.read_expander()

    def read_expander(self):
        bits = self.ex.inputs()
        keys = 0
        for bit, k in _MAP:
            if not bits >> bit & 1:      # active low
                keys |= 1 << k
        self._ex_keys = keys
        self._last_read = time.ticks_ms()
        return bits

    def scan(self):
        """Samples the keys and queues events; call every ~10 ms. Returns True on activity."""
        now = time.ticks_ms()
        if not self.int_pin.value() or time.ticks_diff(now, self._last_read) > 250:
            self.read_expander()
        keys = self._ex_keys
        if not self.prev_pin.value():
            keys |= 1 << PREV
        changed = keys ^ self.state
        q = self.queue
        if changed:
            for k in range(9):
                m = 1 << k
                if changed & m:
                    if keys & m:
                        self._since[k] = now
                        self._next_repeat[k] = time.ticks_add(now, REPEAT_DELAY)
                        self._long_sent &= ~m
                        q.append(PRESS << 4 | k)
                    else:
                        q.append(RELEASE << 4 | k)
            self.state = keys
        if keys:
            for k in range(9):
                m = 1 << k
                if keys & m:
                    if m & _REPEATS and time.ticks_diff(now, self._next_repeat[k]) >= 0:
                        self._next_repeat[k] = time.ticks_add(now, REPEAT_EVERY)
                        q.append(REPEAT << 4 | k)
                    if not self._long_sent & m and time.ticks_diff(now, self._since[k]) >= LONG_AFTER:
                        self._long_sent |= m
                        q.append(LONG << 4 | k)
        if len(q) > 32:
            del q[:-32]
        if changed or keys:
            self.last_activity = now
            return True
        return False

    def held(self, k):
        return bool(self.state >> k & 1)

    def get(self):
        """Next queued event, or None."""
        return self.queue.pop(0) if self.queue else None

    def clear(self):
        self.queue.clear()
