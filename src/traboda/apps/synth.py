"""Synth: seven keys play a scale on a piano, plus an 8-step sequencer.

LEFT UP RIGHT DOWN A PLAY NEXT are the seven notes of the scale (major, minor, major
pentatonic or blues). NEXT held opens a small menu: mode, scale, octave, tempo and the
pattern tools. In the sequencer the D-pad picks a step and its note, A switches the step
on and off, NEXT (or PLAY) starts and stops the loop.
"""

import random
import time

from .. import buttons as B
from .. import gfx, settings, ui
from ..display import rgb
from .games.common import leds_frame

TITLE = "Synth"
ICON = "synth"
MEDIA_KEYS = True

NOTE_KEYS = (B.LEFT, B.UP, B.RIGHT, B.DOWN, B.A, B.PLAY, B.NEXT)
NAMES = ("Do", "Do#", "Re", "Mib", "Mi", "Fa", "Fa#", "Sol", "Lab", "La", "Sib", "Si")
SCALES = (
    ("Maggiore", (0, 2, 4, 5, 7, 9, 11)),
    ("Minore", (0, 2, 3, 5, 7, 8, 10)),
    ("Pentatonica", (0, 2, 4, 7, 9, 12, 14)),
    ("Blues", (0, 3, 5, 6, 7, 10, 12)),
)
MODES = ("Tastiera", "Sequencer")
MENU = ("Modalità", "Scala", "Ottava", "Tempo", "Sequenza casuale", "Svuota sequenza")
# one colour per scale degree, boomwhacker style
COLOURS = ((255, 64, 64), (255, 150, 40), (255, 222, 40), (90, 220, 90), (40, 200, 230),
           (80, 120, 255), (200, 90, 255))
SCREEN = tuple(rgb(*c) for c in COLOURS)
BLACK = (0, 0, 0)
LED_COL = (0, 2, 3, 5, 7, 8, 10)        # strip column of each scale degree
SEQ_COL = (1, 2, 3, 4, 6, 7, 8, 9)      # strip column of each sequencer step
IDLE = tuple(tuple(v // 10 for v in COLOURS[LED_COL.index(c)]) if c in LED_COL else BLACK
             for c in range(11))
DEFAULTS = {"mode": 0, "scale": 0, "octave": 4, "bpm": 120,
            "notes": [0, 2, 4, 6, 5, 4, 2, 1], "on": [1] * 8}

NOTE_MS = 180
DECAY_MS = 420
OCT_LO, OCT_HI = 2, 5
BPM_LO, BPM_HI = 60, 200

# keyboard: a scope panel over a 9-white-key piano (Do to the Re an octave up)
SCOPE_Y, SCOPE_H = 56, 56
WAVE_X, WAVE_W = 104, 200
KEY_X, KEY_Y, KEY_W, KEY_H = 7, 120, 34, 98
BLACK_W, BLACK_H = 20, 58
WHITES = (0, 2, 4, 5, 7, 9, 11, 12, 14)
BLACKS = (1, 3, 6, 8, 10, 13)
WHITE_KEY = rgb(226, 230, 240)
BLACK_KEY = rgb(16, 18, 28)
BLACK_TOP = rgb(46, 50, 74)
KEY_TEXT = rgb(112, 118, 142)
# sequencer: step numbers, then 8 columns x 7 rows
NUM_Y = 55
GRID_X, GRID_Y = 44, 69
COL_W, ROW_H = 33, 18
INFO_Y = 200
# menu overlay
MENU_X, MENU_Y, MENU_W = 44, 58, 232
MENU_H = 32 + 20 * len(MENU) + 6


def _freq(semi, octave):
    return int(440 * 2 ** ((12 * (octave + 1) + semi - 69) / 12) + 0.5)


def _name(semi, octave):
    return NAMES[semi % 12] + str(octave + semi // 12)


def _scaled(c, k):
    return (int(c[0] * k), int(c[1] * k), int(c[2] * k))


def _col_x(step):
    return GRID_X + step * COL_W + (6 if step >= 4 else 0)


def _row_y(degree):
    return GRID_Y + (6 - degree) * ROW_H


def _tone(sys, freq, ms):
    try:
        sys.audio.tone(freq, ms)
    except Exception:  # noqa: BLE001 - a failed beep must not stop the instrument
        pass


class Synth:
    def __init__(self, sys):
        self.sys = sys
        cfg = dict(DEFAULTS)
        saved = settings.get("synth")
        if isinstance(saved, dict):
            cfg.update(saved)
        if len(cfg["notes"]) != 8 or len(cfg["on"]) != 8:
            cfg["notes"], cfg["on"] = DEFAULTS["notes"], DEFAULTS["on"]
        self.mode = cfg["mode"] % 2
        self.scale = cfg["scale"] % len(SCALES)
        self.octave = min(OCT_HI, max(OCT_LO, cfg["octave"]))
        self.bpm = min(BPM_HI, max(BPM_LO, cfg["bpm"]))
        self.notes = [min(6, max(0, n)) for n in cfg["notes"]]
        self.on = [bool(x) for x in cfg["on"]]
        self.cursor = 0
        self.step = -1              # step being played
        self.playing = False
        self.next_at = 0
        self.held = 0               # note keys held, as a bitmask of degrees
        self.last = -1              # degree played last
        self.hit = None             # ticks_ms of that note while its echo fades
        self.menu = -1              # selected menu row, -1 while closed
        self.menu_sel = 0
        self.frame = [BLACK] * 22

    # -- music -------------------------------------------------------------------------

    def freq(self, d):
        return _freq(SCALES[self.scale][1][d], self.octave)

    def name(self, d):
        return _name(SCALES[self.scale][1][d], self.octave)

    def step_ms(self):
        return 30000 // self.bpm            # eighth notes

    def env(self):
        if self.hit is None:
            return 0
        return max(0, 1 - time.ticks_diff(time.ticks_ms(), self.hit) / DECAY_MS)

    # -- drawing -----------------------------------------------------------------------

    def draw(self):
        ui.header(self.sys, TITLE, ICON)
        self.draw_info()
        if self.mode == 0:
            self.draw_scope()
            self.draw_keys()
        else:
            self.draw_grid()
            self.draw_step()
        self.draw_footer()
        if self.menu >= 0:
            self.draw_menu()
        self.sys.show()

    def draw_info(self):
        gfx.fill_rect(150, 19, 170, 32, ui.BG)
        gfx.text("%s · ottava %d" % (SCALES[self.scale][0], self.octave), 312, 22, ui.CYAN,
                 "small", align=-1)
        sub = MODES[0] if self.mode == 0 else "%s · %d BPM" % (MODES[1], self.bpm)
        gfx.text(sub, 312, 36, ui.DIM, "small", align=-1)

    def draw_footer(self):
        if self.menu >= 0:
            hints = [("▲▼", "Scegli"), ("◄►", "Cambia"), ("A", "Ok")]
        elif self.mode == 0:
            hints = [("A tieni", "Esci"), ("►► tieni", "Menu")]
        else:
            hints = [("◄►", "Passo"), ("▲▼", "Nota"), ("A", "On/Off"),
                     ("►►", "Stop" if self.playing else "Avvia")]
        ui.footer(hints)

    def draw_scope(self):
        y0 = SCOPE_Y
        gfx.round_rect(6, y0, 308, SCOPE_H, 8, ui.PANEL)
        yc = y0 + SCOPE_H // 2
        for gx in range(WAVE_X, WAVE_X + WAVE_W + 1, 25):
            gfx.vline(gx, y0 + 6, SCOPE_H - 12, ui.PANEL2)
        gfx.hline(WAVE_X, yc, WAVE_W, ui.LINE)
        d = self.last
        if d < 0:
            gfx.text("--", 20, y0 + 8, ui.DIM, "title")
            gfx.text("pronto", 20, y0 + 36, ui.DIM, "small")
            gfx.text("premi un tasto per suonare", WAVE_X + WAVE_W // 2, yc - 18, ui.DIM, "small",
                     align=1)
            return
        c = SCREEN[d]
        f = self.freq(d)
        gfx.text(self.name(d), 20, y0 + 8, c, "title")
        gfx.text("%d Hz" % f, 20, y0 + 36, ui.DIM, "small")
        amp = int(20 * self.env())
        if amp < 2:
            return
        half = max(3, 12500 // f)           # an 8 ms window across the wave area
        x = WAVE_X
        end = WAVE_X + WAVE_W
        high = True
        while x < end:
            x2 = min(end, x + half)
            gfx.fill_rect(x, yc - amp if high else yc + amp - 2, x2 - x, 2, c)
            if x2 < end:
                gfx.fill_rect(x2 - 1, yc - amp, 2, 2 * amp, c)
            x = x2
            high = not high

    def badge(self, d, cx, y, w, on):
        """The key that plays degree d, on its piano key."""
        gfx.round_rect(cx - w // 2, y, w, 18, 5, ui.WHITE if on else SCREEN[d])
        gfx.text(B.GLYPHS[NOTE_KEYS[d]], cx, y + 1, SCREEN[d] if on else ui.BG, align=1)

    def draw_keys(self):
        semis = SCALES[self.scale][1]
        gfx.fill_rect(0, KEY_Y - 4, 320, KEY_H + 4, ui.BG)
        gfx.fill_rect(KEY_X + 1, KEY_Y - 4, 9 * KEY_W - 2, 3, ui.ACCENT_DARK)
        for w, s in enumerate(WHITES):
            x = KEY_X + w * KEY_W
            d = semis.index(s) if s in semis else -1
            on = d >= 0 and self.held >> d & 1
            gfx.round_rect(x + 1, KEY_Y, KEY_W - 2, KEY_H, 4, SCREEN[d] if on else WHITE_KEY)
            gfx.text(NAMES[s % 12], x + KEY_W // 2, KEY_Y + KEY_H - 16, ui.BG if on else KEY_TEXT,
                     "small", align=1)
            if d >= 0:
                self.badge(d, x + KEY_W // 2, KEY_Y + KEY_H - 38, 24, on)
        for s in BLACKS:
            cx = KEY_X + (WHITES.index(s - 1) + 1) * KEY_W
            x = cx - BLACK_W // 2
            d = semis.index(s) if s in semis else -1
            on = d >= 0 and self.held >> d & 1
            gfx.round_rect(x, KEY_Y, BLACK_W, BLACK_H, 3, SCREEN[d] if on else BLACK_KEY)
            if not on:
                gfx.fill_rect(x + 3, KEY_Y + 1, BLACK_W - 6, BLACK_H - 10, BLACK_TOP)
            if d >= 0:
                self.badge(d, cx, KEY_Y + BLACK_H - 22, 18, on)

    def draw_grid(self):
        semis = SCALES[self.scale][1]
        gfx.fill_rect(0, NUM_Y, 320, GRID_Y + 7 * ROW_H - NUM_Y, ui.BG)
        for d in range(7):
            gfx.text(_name(semis[d], self.octave), 8, _row_y(d) + 3, SCREEN[d], "small")
        for s in range(8):
            x = _col_x(s)
            now = self.playing and s == self.step
            gfx.text(str(s + 1), x + 15, NUM_Y, ui.ACCENT if s == self.cursor else ui.DIM,
                     "small", align=1)
            gfx.round_rect(x, GRID_Y, COL_W - 3, 7 * ROW_H, 5,
                           ui.LINE if now else ui.PANEL2 if s == self.cursor else ui.PANEL)
            if s == self.cursor:
                gfx.round_rect(x, GRID_Y, COL_W - 3, 7 * ROW_H, 5, ui.ACCENT, False)
            d = self.notes[s]
            for r in range(7):
                if r != d:
                    gfx.fill_rect(x + 13, _row_y(r) + 8, 4, 2, ui.PANEL if now else ui.LINE)
            if self.on[s]:
                gfx.round_rect(x + 3, _row_y(d) + 2, COL_W - 9, ROW_H - 4, 4, SCREEN[d])
            else:
                gfx.round_rect(x + 3, _row_y(d) + 2, COL_W - 9, ROW_H - 4, 4, SCREEN[d], False)

    def draw_step(self):
        gfx.fill_rect(0, INFO_Y - 2, 320, ui.FOOTER_Y - INFO_Y + 2, ui.BG)
        s = self.cursor
        x = 8 + gfx.text("Passo %d: " % (s + 1), 8, INFO_Y, ui.TEXT)
        if self.on[s]:
            gfx.text(self.name(self.notes[s]), x, INFO_Y, SCREEN[self.notes[s]])
        else:
            gfx.text("pausa", x, INFO_Y, ui.DIM)
        gfx.text("►► tieni: menu", 312, INFO_Y + 2, ui.DIM, "small", align=-1)

    def menu_value(self, i):
        if i == 0:
            return MODES[self.mode]
        if i == 1:
            return SCALES[self.scale][0]
        if i == 2:
            return str(self.octave)
        if i == 3:
            return "%d BPM" % self.bpm
        return None

    def draw_menu(self):
        x, y, w = MENU_X, MENU_Y, MENU_W
        gfx.round_rect(x, y, w, MENU_H, 10, ui.PANEL)
        gfx.round_rect(x, y, w, MENU_H, 10, ui.ACCENT, False)
        gfx.text("Menu Synth", x + w // 2, y + 6, ui.TEXT, align=1)
        gfx.hline(x + 16, y + 26, w - 32, ui.LINE)
        for i, label in enumerate(MENU):
            ry = y + 32 + i * 20
            sel = i == self.menu
            if sel:
                gfx.round_rect(x + 6, ry, w - 12, 19, 5, ui.PANEL2)
                gfx.fill_rect(x + 6, ry + 4, 3, 11, ui.ACCENT)
            gfx.text(label, x + 16, ry + 2, ui.TEXT if sel else ui.DIM)
            v = self.menu_value(i)
            if v:
                gfx.text("◄ %s ►" % v if sel else v, x + w - 12, ry + 2, ui.CYAN if sel else ui.DIM,
                         align=-1)

    # -- LEDs --------------------------------------------------------------------------

    def leds(self):
        frame = self.frame
        if self.mode == 0:
            # the seven note colours dimly on their columns; the last note glows over them
            env = self.env()
            centre = LED_COL[self.last] if self.last >= 0 else 0
            for col in range(11):
                k = env * max(0, 1 - abs(col - centre) / 3)
                frame[col] = frame[col + 11] = _scaled(COLOURS[self.last], k) if k > 0.1 else IDLE[col]
        else:
            for i in range(22):
                frame[i] = BLACK
            for s in range(8):
                c = COLOURS[self.notes[s]]
                if self.playing and s == self.step:
                    top = bottom = c if self.on[s] else (90, 90, 90)
                elif self.on[s]:
                    top, bottom = _scaled(c, 0.3), _scaled(c, 0.1)
                else:
                    top = bottom = BLACK
                if not self.playing and s == self.cursor:
                    bottom = (170, 170, 170)
                frame[SEQ_COL[s]] = top
                frame[SEQ_COL[s] + 11] = bottom
        leds_frame(self.sys, frame)

    # -- actions -----------------------------------------------------------------------

    def set_playing(self, on):
        self.playing = on
        self.step = -1
        self.next_at = time.ticks_ms()
        if self.mode == 1 and self.menu < 0:
            self.draw_grid()
            self.draw_footer()
            self.sys.show(NUM_Y, 240)
        self.leds()

    def advance(self, now):
        sys = self.sys
        period = self.step_ms()
        self.step = (self.step + 1) % 8
        self.next_at = time.ticks_add(self.next_at, period)
        if time.ticks_diff(self.next_at, now) <= 0:
            self.next_at = time.ticks_add(now, period)
        if self.menu < 0:
            self.draw_grid()
            sys.show(NUM_Y, GRID_Y + 7 * ROW_H)
        self.leds()
        if self.on[self.step]:
            _tone(sys, self.freq(self.notes[self.step]), min(NOTE_MS, period * 7 // 10))

    def tick(self):
        """Sequencer steps and the fading echo of the last note."""
        now = time.ticks_ms()
        if self.playing and time.ticks_diff(now, self.next_at) >= 0:
            self.advance(now)
        if self.hit is not None:
            if time.ticks_diff(now, self.hit) >= DECAY_MS:
                self.hit = None
            if self.menu < 0 and self.mode == 0:
                self.draw_scope()
                self.sys.show(SCOPE_Y, SCOPE_Y + SCOPE_H)
            self.leds()

    def timeout(self):
        t = None
        if self.playing:
            t = max(1, time.ticks_diff(self.next_at, time.ticks_ms()))
        if self.hit is not None:
            t = 30 if t is None else min(t, 30)
        return t

    def open_menu(self):
        self.menu = self.menu_sel
        self.held = 0
        self.hit = None
        self.leds()
        self.draw_menu()
        self.draw_footer()
        self.sys.show(MENU_Y, 240)

    def close_menu(self):
        self.menu_sel = self.menu
        self.menu = -1
        self.draw()
        self.leds()

    def menu_event(self, ev, k, kind):
        if self.sys.is_back(ev):
            self.close_menu()
            return
        i = self.menu
        if kind == B.CLICK and k in (B.A, B.NEXT):
            if i == 4:
                self.notes = [random.randrange(7) for _ in range(8)]
                self.on = [s == 0 or random.randrange(4) > 0 for s in range(8)]
            elif i == 5:
                self.on = [False] * 8
            if i >= 4 and self.mode == 0:
                self.mode = 1
            self.close_menu()
            return
        if kind not in (B.PRESS, B.REPEAT):
            return
        if k in (B.UP, B.DOWN):
            self.menu = (i + (1 if k == B.DOWN else -1)) % len(MENU)
        elif k in (B.LEFT, B.RIGHT):
            delta = 1 if k == B.RIGHT else -1
            if i == 0:
                self.mode = 1 - self.mode
                if self.playing:
                    self.set_playing(False)
                self.leds()
            elif i == 1:
                self.scale = (self.scale + delta) % len(SCALES)
            elif i == 2:
                self.octave = min(OCT_HI, max(OCT_LO, self.octave + delta))
            elif i == 3:
                self.bpm = min(BPM_HI, max(BPM_LO, self.bpm + 10 * delta))
            self.draw_info()
            if self.mode == 0 and self.last >= 0 and i in (1, 2):
                _tone(self.sys, self.freq(self.last), 120)
        else:
            return
        self.draw_menu()
        self.sys.show(19, MENU_Y + MENU_H)

    def keys_event(self, k, kind):
        if k not in NOTE_KEYS or kind not in (B.PRESS, B.RELEASE):
            return
        d = NOTE_KEYS.index(k)
        if kind == B.RELEASE:
            self.held &= ~(1 << d)
            self.draw_keys()
            self.sys.show(KEY_Y - 4, KEY_Y + KEY_H)
            return
        self.held |= 1 << d
        self.last = d
        self.hit = time.ticks_ms()
        self.draw_scope()
        self.draw_keys()
        self.sys.show(SCOPE_Y, KEY_Y + KEY_H)
        self.leds()
        _tone(self.sys, self.freq(d), NOTE_MS)

    def seq_event(self, k, kind):
        c = self.cursor
        preview = False
        if kind in (B.PRESS, B.REPEAT) and k in (B.LEFT, B.RIGHT):
            self.cursor = (c + (1 if k == B.RIGHT else -1)) % 8
        elif kind in (B.PRESS, B.REPEAT) and k in (B.UP, B.DOWN):
            self.notes[c] = min(6, max(0, self.notes[c] + (1 if k == B.UP else -1)))
            self.on[c] = preview = True
        elif kind == B.CLICK and k == B.A:
            self.on[c] = preview = not self.on[c]
        elif (kind == B.CLICK and k == B.NEXT) or (kind == B.PRESS and k == B.PLAY):
            self.set_playing(not self.playing)
            return
        else:
            return
        self.draw_grid()
        self.draw_step()
        self.sys.show(NUM_Y, ui.FOOTER_Y)
        self.leds()
        if preview and not self.playing:
            _tone(self.sys, self.freq(self.notes[c]), 140)

    def save(self):
        cfg = {"mode": self.mode, "scale": self.scale, "octave": self.octave, "bpm": self.bpm,
               "notes": list(self.notes), "on": [1 if x else 0 for x in self.on]}
        if cfg != settings.get("synth"):
            settings.set("synth", cfg)

    async def run(self, music_paused):
        sys = self.sys
        self.draw()
        self.leds()
        if music_paused:
            await ui.toast(sys, "Musica in pausa", 1200)
            self.draw()
        while True:
            ev = await sys.event(timeout_ms=self.timeout())
            self.tick()
            if ev is None:
                continue
            k, kind = B.key(ev), B.kind(ev)
            if kind == sys.HOME:
                return
            if kind == sys.REDRAW:
                self.draw()
            elif self.menu >= 0:
                self.menu_event(ev, k, kind)
            elif k == B.NEXT and kind == B.LONG:
                self.open_menu()
            elif sys.is_back(ev):
                return
            elif self.mode == 0:
                self.keys_event(k, kind)
            else:
                self.seq_event(k, kind)


async def main(sys):
    music_paused = sys.audio.playing and not sys.audio.paused
    if music_paused:
        sys.player.play_pause()
    synth = Synth(sys)
    try:
        await synth.run(music_paused)
    finally:
        synth.save()
        if sys.leds:
            sys.leds.set_effect(settings.get("led_effect") if settings.get("leds_on") else "off")
