"""Clock: the time in huge digits, a countdown timer with an alarm, a stopwatch with laps
and a 25/5 pomodoro, on tabs switched with left/right.

The timers run only while the app is open, and keep the screen awake while they run. With
a track loaded the core keeps ►► for the music, so every ►► action has a D-pad key too.
"""

import time

from .. import buttons as B
from .. import gfx, icons, settings, tz, ui

TITLE = "Orologio"
ICON = "clock"
MEDIA_KEYS = False

TABS = ("Ora", "Timer", "Cronometro", "Pomodoro")
CLOCK, TIMER = 0, 1     # the first tab, and the one the alarm jumps to
TAB_Y = 21
TAB_H = 20
TAB_X = (320 - sum(len(t) * 8 + 16 for t in TABS) - 4 * (len(TABS) - 1)) // 2
TOP = 44            # content, below the tab bar
BIG_Y = 46          # "huge" cells (32x64): the digits' ink is on rows 12..51
SMALL_Y = BIG_Y + 26    # a "large" cell sharing that baseline
BAR_Y = 106
LINE1_Y = 122
LINE2_Y = 154
NOTE_Y = 204
LAP_Y = 114
LAP_H = 20
LAPS = 5

IDLE, RUN, PAUSE, RING = range(4)
MIN_S = 5
MAX_S = 99 * 60
WORK_S = 25 * 60
BREAK_S = 5 * 60

C_TIMER = (45, 226, 230)
C_ALARM = (255, 214, 10)
C_WORK = (255, 40, 40)
C_BREAK = (40, 220, 90)
C_TURN = (255, 255, 255)    # pomodoro transitions: blinks against the full phase colour

# Short notes: audio.tone() builds every sample in Python and the loop waits for it.
RINGTONE = ((1047, 100, 30), (1319, 100, 30), (1568, 100, 30), (2093, 120, 750))  # Hz, ms, rest
CHIME_BREAK = ((1319, 100), (1568, 100), (2093, 160))
CHIME_WORK = ((2093, 100), (1568, 100), (1319, 160))

NOTE = "i timer contano solo con l'app aperta"

H_CLOCK = (("◄►", "Schede"), ("B", "Esci"))
H_TIMER_IDLE = (("▲▼", "Imposta"), ("A", "Avvia"), ("B", "Esci"))
H_TIMER_RUN = (("A", "Pausa"), ("►►", "Azzera"), ("B", "Esci"))
H_TIMER_RUN_MUSIC = (("A", "Pausa"), ("B", "Esci"))
H_TIMER_PAUSE = (("A", "Riprendi"), ("▲▼", "Azzera"), ("B", "Esci"))
H_TIMER_RING = (("un tasto", "Ferma l'allarme"),)
H_WATCH_IDLE = (("A", "Avvia"), ("B", "Esci"))
H_WATCH_RUN = (("A", "Ferma"), ("▼", "Giro"), ("▲", "Azzera"), ("B", "Esci"))
H_WATCH_STOP = (("A", "Riprendi"), ("▲", "Azzera"), ("B", "Esci"))
H_POMO_IDLE = (("A", "Avvia"), ("B", "Esci"))
H_POMO_RUN = (("A", "Ferma"), ("▼", "Salta"), ("▲", "Azzera"), ("B", "Esci"))
H_POMO_PAUSE = (("A", "Riprendi"), ("▲", "Azzera"), ("B", "Esci"))
H_EXIT = (("B", "di nuovo per uscire"),)

icons.register("tomato", (
    "................",
    ".......g........",
    "......gGg..g....",
    "...rrrgGGgGgr...",
    "..rrrrrgGGgrrr..",
    ".rrwwrrrggrrrrr.",
    ".rwwrrrrrrrrrrr.",
    "rrwrrrrrrrrrrrrr",
    "rrrrrrrrrrrrrrrr",
    "rrrrrrrrrrrrrrrr",
    "rrrrrrrrrrrrrrrp",
    ".rrrrrrrrrrrrrp.",
    ".prrrrrrrrrrrpp.",
    "..pprrrrrrrrpp..",
    "....pppppppp....",
    "................",
))


def _mmss(s):
    return "%02d:%02d" % (s // 60, s % 60)


def _lap(ms):
    s = ms // 1000
    if s >= 3600:
        return "%d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60)
    return "%02d:%02d.%02d" % (s // 60, s % 60, ms // 10 % 100)


def _step(v, fast):
    """Timer setting ladder: 5 s below a minute, 15 s below ten, then minutes."""
    if v < 60:
        return 15 if fast else 5
    if v < 600:
        return 60 if fast else 15
    return 300 if fast else 60


def _zone():
    off = tz.offset_minutes()
    utc = "UTC%s%02d:%02d" % ("-" if off < 0 else "+", abs(off) // 60, abs(off) % 60)
    return utc if tz.zone.startswith("UTC") else tz.zone + " · " + utc


def _union(band, rows):
    return rows if band is None else (min(band[0], rows[0]), max(band[1], rows[1]))


def _clear():
    gfx.fill_rect(0, TOP, 320, ui.FOOTER_Y - TOP, ui.BG)


def _note():
    gfx.text(NOTE, 160, NOTE_Y, ui.DIM, "small", align=1)


def _play(sys, notes):
    try:
        sys.audio.melody(notes, 0.35)
    except Exception:  # noqa: BLE001 - a chime must never stop the clock
        pass


def _flash(sys, color, ms=1300):
    """ms=0 cancels a flash still running."""
    if sys.leds and (settings.get("leds_on") or not ms):
        sys.leds.flash(color, ms, 150)


def _tabbar(sel, dots):
    gfx.fill_rect(0, ui.STATUS_H, 320, TOP - ui.STATUS_H, ui.BG)
    gfx.text("◄", 4, TAB_Y + 2, ui.DIM)
    gfx.text("►", 316, TAB_Y + 2, ui.DIM, align=-1)
    x = TAB_X
    for i in range(len(TABS)):
        w = len(TABS[i]) * 8 + 16
        on = i == sel
        gfx.round_rect(x, TAB_Y, w, TAB_H, 6, ui.ACCENT if on else ui.PANEL)
        gfx.text(TABS[i], x + w // 2, TAB_Y + 2, ui.WHITE if on else ui.DIM, align=1)
        if dots[i] is not None and not on:
            gfx.circle(x + w - 5, TAB_Y + 5, 2, dots[i], True)
        x += w + 4


class _Clock:
    def __init__(self):
        self.drawn = None
        self.minute = -1
        self.sec = -1

    def hints(self, app):
        return H_CLOCK

    def key(self, k, kind, now):
        pass

    def draw(self, app, now, full):
        t, valid = app.t, app.valid
        hour = t[2] * 24 + t[3] if valid else -1     # date and zone lines: hourly (DST)
        band = None
        if full or hour != self.drawn:
            self.drawn = hour
            self.minute = self.sec = -1
            _clear()
            if valid:
                gfx.text(tz.DAYS_LONG[t[6]], 160, LINE1_Y, ui.CYAN, "title", align=1)
                date = "%d %s %d" % (t[2], tz.MONTHS_LONG[t[1] - 1], t[0])
                gfx.text(date, 160, LINE2_Y, ui.TEXT, align=1)
            else:
                gfx.text("--:--", 160, BIG_Y, ui.DIM, "huge", align=1)
                gfx.text("Ora non impostata", 160, LINE1_Y, ui.YELLOW, "title", align=1)
                gfx.text("collega il Wi-Fi: si imposta da sola", 160, LINE2_Y, ui.DIM, align=1)
            gfx.text(_zone(), 160, NOTE_Y, ui.DIM, "small", align=1)
            band = (TOP, ui.FOOTER_Y)
        if not valid:
            return band
        if t[4] != self.minute:
            self.minute = t[4]
            self.sec = -1
            gfx.text("%02d:%02d" % (t[3], t[4]), 160, BIG_Y, ui.TEXT, "huge", bg=ui.BG, align=1)
            band = _union(band, (BIG_Y, BIG_Y + 64))
        if t[5] != self.sec:
            self.sec = s = t[5]
            gfx.text(":", 160, BIG_Y, ui.ACCENT if s % 2 == 0 else ui.BG, "huge", bg=ui.BG, align=1)
            gfx.text("%02d" % s, 244, SMALL_Y, ui.CYAN, "large", bg=ui.BG)
            gfx.bar(84, BAR_Y, 152, 3, s / 59, ui.ACCENT, ui.PANEL2)
            band = _union(band, (BIG_Y, BAR_Y + 3))
        return band


class _Timer:
    def __init__(self):
        self.total = max(MIN_S, min(MAX_S, settings.get("timer_s", 300)))
        self.left = self.total * 1000       # ms, while not running
        self.end = 0
        self.state = IDLE
        self.reps = 0                       # REPEATs of the held key: the ladder speeds up
        self.mute = False                   # the held key reset a paused timer: no setting
        self.note = 0
        self.next_note = 0
        self.next_flash = 0
        self.drawn = None
        self.shown = None

    def remaining(self, now):
        return max(0, time.ticks_diff(self.end, now)) if self.state == RUN else self.left

    def reset(self):
        self.state = IDLE
        self.left = self.total * 1000

    def tick(self, now):
        """True when the countdown just reached zero."""
        if self.state == RUN and time.ticks_diff(self.end, now) <= 0:
            self.state = RING
            self.left = 0
            self.note = 0
            self.next_note = self.next_flash = now
            return True
        return False

    def ring(self, sys, now):
        """One note of the ringtone per call when due, so keys stay responsive."""
        if time.ticks_diff(now, self.next_note) >= 0:
            freq, ms, rest = RINGTONE[self.note]
            self.note = (self.note + 1) % len(RINGTONE)
            self.next_note = time.ticks_add(now, ms + rest)
            _play(sys, ((freq, ms),))
        if time.ticks_diff(now, self.next_flash) >= 0:
            self.next_flash = time.ticks_add(now, 1000)
            _flash(sys, C_ALARM)

    def hints(self, app):
        if self.state == RUN:
            return H_TIMER_RUN_MUSIC if app.sys.player.loaded else H_TIMER_RUN
        return (H_TIMER_IDLE, None, H_TIMER_PAUSE, H_TIMER_RING)[self.state]

    def key(self, k, kind, now):
        st = self.state
        if kind == B.CLICK and k in (B.A, B.PLAY):
            if st == RUN:
                self.left = self.remaining(now)
                self.state = PAUSE
            else:
                if st == IDLE and self.total != settings.get("timer_s", 300):
                    settings.set("timer_s", self.total)
                self.end = time.ticks_add(now, self.left)
                self.state = RUN
        elif kind == B.CLICK and k == B.NEXT:
            self.reset()
        elif k in (B.UP, B.DOWN) and kind in (B.PRESS, B.REPEAT):
            if kind == B.PRESS:
                self.reps = 0
                self.mute = st == PAUSE
                if st == PAUSE:
                    self.reset()
                    return
            else:
                self.reps += 1
            if st == IDLE and not self.mute:
                v = self.total
                fast = self.reps > 8
                if k == B.UP:
                    step = _step(v, fast)
                    v = (v // step + 1) * step
                else:
                    step = _step(v - 1, fast)
                    v = (v - 1) // step * step
                self.total = max(MIN_S, min(MAX_S, v))
                self.left = self.total * 1000

    def draw(self, app, now, full):
        st = self.state
        band = None
        if full or st != self.drawn:
            self.drawn = st
            self.shown = None
            _clear()
            self.draw_text(app, now)
            band = (TOP, ui.FOOTER_Y)
        left = self.remaining(now)
        blink = st == RING and now // 300 % 2 == 1
        shown = ((left + 999) // 1000, self.total, blink)
        if shown != self.shown:
            self.shown = shown
            if st == RING:
                color = ui.ACCENT_DARK if blink else ui.RED
            else:
                color = (ui.TEXT, ui.CYAN, ui.YELLOW)[st]
            gfx.text(_mmss(shown[0]), 160, BIG_Y, color, "huge", bg=ui.BG, align=1)
            gfx.bar(40, BAR_Y, 240, 8, left / (self.total * 1000), ui.CYAN, ui.PANEL2, 4)
            band = _union(band, (BIG_Y, BAR_Y + 8))
        return band

    def draw_text(self, app, now):
        st = self.state
        if st == RING:
            gfx.text("Tempo scaduto!", 160, LINE1_Y, ui.RED, "title", align=1)
            gfx.text("premi un tasto qualsiasi", 160, LINE2_Y, ui.TEXT, align=1)
            return
        label = ("Pronto", "In corso", "In pausa")[st]
        gfx.text(label, 160, LINE1_Y, (ui.TEXT, ui.CYAN, ui.YELLOW)[st], "title", align=1)
        if st == RUN and app.valid:
            t = tz.now()
            s = t[3] * 3600 + t[4] * 60 + t[5] + (self.remaining(now) + 999) // 1000
            info = "suona alle %02d:%02d:%02d" % (s // 3600 % 24, s // 60 % 60, s % 60)
        elif st == IDLE:
            info = "▲▼ cambiano la durata"
        else:
            info = "durata %s" % _mmss(self.total)
        gfx.text(info, 160, LINE2_Y, ui.DIM, align=1)
        _note()


class _Stopwatch:
    def __init__(self):
        self.reset()

    def reset(self):
        self.running = False
        self.acc = 0                # ms counted before the current run
        self.t0 = 0
        self.laps = []              # (number, split ms, total ms), newest first
        self.n = 0
        self.last = 0               # total at the previous lap
        self.drawn = None
        self.big = None
        self.small = None
        self.lap_n = -1

    def elapsed(self, now):
        return self.acc + time.ticks_diff(now, self.t0) if self.running else self.acc

    def state(self):
        return RUN if self.running else PAUSE if self.acc else IDLE

    def hints(self, app):
        return (H_WATCH_IDLE, H_WATCH_RUN, H_WATCH_STOP)[self.state()]

    def key(self, k, kind, now):
        if kind == B.CLICK and k in (B.A, B.PLAY):
            if self.running:
                self.acc = self.elapsed(now)
            else:
                self.t0 = now
            self.running = not self.running
        elif self.running and ((k == B.DOWN and kind == B.PRESS) or (k == B.NEXT and kind == B.CLICK)):
            total = self.elapsed(now)
            self.n += 1
            self.laps.insert(0, (self.n, total - self.last, total))
            del self.laps[LAPS:]
            self.last = total
        elif k == B.UP and kind == B.PRESS and self.state() != IDLE:
            self.reset()

    def draw(self, app, now, full):
        st = self.state()
        band = None
        if full or st != self.drawn:
            self.drawn = st
            self.big = self.small = None
            self.lap_n = -1
            _clear()
            band = (TOP, ui.FOOTER_Y)
        ms = self.elapsed(now)
        s = ms // 1000
        if s < 3600:
            big = "%02d:%02d" % (s // 60, s % 60)
            small = ".%02d" % (ms // 10 % 100)
        else:
            big = "%d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60)
            small = ".%d" % (ms // 100 % 10)
        x = 160 - (len(big) * 32 + len(small) * 16) // 2
        color = (ui.TEXT, ui.CYAN, ui.YELLOW)[st]
        if big != self.big:
            if self.big is not None and len(big) != len(self.big):
                gfx.fill_rect(0, BIG_Y, 320, 64, ui.BG)       # the hour digit moved everything
                self.small = None
            self.big = big
            gfx.text(big, x, BIG_Y, color, "huge", bg=ui.BG)
            band = _union(band, (BIG_Y, BIG_Y + 64))
        if small != self.small:
            self.small = small
            gfx.text(small, x + len(big) * 32, SMALL_Y, color, "large", bg=ui.BG)
            band = _union(band, (SMALL_Y, SMALL_Y + 32))
        if self.n != self.lap_n:
            self.lap_n = self.n
            self.draw_laps(st)
            band = _union(band, (LAP_Y - 2, ui.FOOTER_Y))
        return band

    def draw_laps(self, st):
        gfx.fill_rect(0, LAP_Y - 2, 320, ui.FOOTER_Y - LAP_Y + 2, ui.BG)
        for i in range(len(self.laps)):
            n, split, total = self.laps[i]
            y = LAP_Y + i * LAP_H
            if i == 0:
                gfx.round_rect(12, y - 1, 296, LAP_H - 2, 5, ui.PANEL)
            gfx.text("Giro %d" % n, 22, y, ui.TEXT if i == 0 else ui.DIM)
            gfx.text(_lap(split), 200, y, ui.CYAN if i == 0 else ui.TEXT, align=-1)
            gfx.text(_lap(total), 298, y, ui.DIM, align=-1)
        if not self.laps and st == RUN:
            gfx.text("▼ segna un giro", 160, LAP_Y + LAP_H, ui.DIM, align=1)
        if len(self.laps) < LAPS:
            _note()


class _Pomodoro:
    def __init__(self):
        self.reset()

    def reset(self):
        self.work = True
        self.state = IDLE
        self.left = WORK_S * 1000
        self.end = 0
        self.done = 0               # completed work phases
        self.drawn = None
        self.shown = None

    def phase_ms(self):
        return (WORK_S if self.work else BREAK_S) * 1000

    def remaining(self, now):
        return max(0, time.ticks_diff(self.end, now)) if self.state == RUN else self.left

    def color(self):
        return C_WORK if self.work else C_BREAK

    def tick(self, sys, now):
        if self.state != RUN or time.ticks_diff(self.end, now) > 0:
            return
        while time.ticks_diff(self.end, now) <= 0:
            if self.work:
                self.done += 1
            self.work = not self.work
            self.end = time.ticks_add(self.end, self.phase_ms())
        _flash(sys, C_TURN)
        _play(sys, CHIME_WORK if self.work else CHIME_BREAK)

    def hints(self, app):
        return (H_POMO_IDLE, H_POMO_RUN, H_POMO_PAUSE)[self.state]

    def key(self, k, kind, now):
        if kind == B.CLICK and k in (B.A, B.PLAY):
            if self.state == RUN:
                self.left = self.remaining(now)
                self.state = PAUSE
            else:
                self.end = time.ticks_add(now, self.left)
                self.state = RUN
        elif self.state == IDLE:
            return
        elif (k == B.DOWN and kind == B.PRESS) or (k == B.NEXT and kind == B.CLICK):
            self.work = not self.work
            self.left = self.phase_ms()
            self.end = time.ticks_add(now, self.left)
        elif k == B.UP and kind == B.PRESS:
            self.reset()

    def draw(self, app, now, full):
        static = (self.state, self.work, self.done)
        band = None
        phase = ui.RED if self.work else ui.GREEN
        if full or static != self.drawn:
            self.drawn = static
            self.shown = None
            _clear()
            label = "Lavoro" if self.work else "Pausa"
            more = "sospeso" if self.state == PAUSE else "%d min" % ((WORK_S if self.work else BREAK_S) // 60)
            gfx.text(label + " · " + more, 160, LINE1_Y, phase, "title", align=1)
            gfx.text("Pomodori completati: %d" % self.done, 160, LINE2_Y, ui.TEXT, align=1)
            n = min(self.done, 12)
            x = 160 - (n * 20 - 4) // 2
            for i in range(n):
                icons.draw(gfx.fb, "tomato", x + i * 20, LINE2_Y + 22, 1)
            _note()
            band = (TOP, ui.FOOTER_Y)
        left = self.remaining(now)
        secs = (left + 999) // 1000
        if secs != self.shown:
            self.shown = secs
            color = (ui.TEXT, phase, ui.YELLOW)[self.state]
            gfx.text(_mmss(secs), 160, BIG_Y, color, "huge", bg=ui.BG, align=1)
            gfx.bar(40, BAR_Y, 240, 8, left / self.phase_ms(), phase, ui.PANEL2, 4)
            band = _union(band, (BIG_Y, BAR_Y + 8))
        return band


class _App:
    def __init__(self, sys):
        self.sys = sys
        self.tab = CLOCK
        self.timer = _Timer()
        self.watch = _Stopwatch()
        self.pomo = _Pomodoro()
        self.tabs = (_Clock(), self.timer, self.watch, self.pomo)
        self.color = sys.leds.color if sys.leds else None
        self.secs = -1
        self.t = None
        self.valid = False
        self.minute = -1
        self.dots = None
        self.hints = None
        self.swallow = 0            # keys whose release/click/long are ignored until pressed again
        self.exit_until = None      # a second "back" before this leaves while a timer runs
        self.awake = time.ticks_ms()

    def busy(self):
        return self.timer.state in (RUN, RING) or self.watch.running or self.pomo.state == RUN

    def tick(self, now):
        """Background work for every tab; True when the alarm took over the screen."""
        sys = self.sys
        secs = int(time.time())
        if secs != self.secs:
            self.secs = secs
            self.t = tz.now()
            self.valid = tz.clock_valid()
        rang = self.timer.tick(now)
        if rang:
            self.tab = TIMER
            self.exit_until = None
            if not sys.screen_on:
                sys.wake_screen()
        if self.timer.state == RING:
            self.timer.ring(sys, now)
        self.pomo.tick(sys, now)
        self.leds(now)
        if self.busy() and time.ticks_diff(now, self.awake) >= 1000:
            self.awake = now
            sys.buttons.last_activity = now
        if self.exit_until is not None and time.ticks_diff(now, self.exit_until) >= 0:
            self.exit_until = None
        return rang

    def leds(self, now):
        """Progress on the strip: alarm, then the running timer, then the pomodoro."""
        leds = self.sys.leds
        if not leds:
            return
        t, p = self.timer, self.pomo
        frac = color = None
        if settings.get("leds_on"):
            if t.state == RING:
                frac, color = 0, C_ALARM
            elif t.state == RUN or (t.state == PAUSE and p.state != RUN):
                frac, color = t.remaining(now) / (t.total * 1000), C_TIMER
            elif p.state != IDLE:
                frac, color = p.remaining(now) / p.phase_ms(), p.color()
        if frac is None:
            if leds.progress is not None:
                leds.progress = None
                leds.color = self.color
        else:
            leds.color = color
            leds.progress = frac

    def dots_now(self):
        t, w, p = self.timer, self.watch, self.pomo
        return (None,
                (None, ui.CYAN, ui.YELLOW, ui.RED)[t.state],
                (None, ui.CYAN, ui.YELLOW)[w.state()],
                (None, ui.RED if p.work else ui.GREEN, ui.YELLOW)[p.state])

    def draw(self, now, full):
        sys = self.sys
        tab = self.tabs[self.tab]
        dots = self.dots_now()
        hints = H_EXIT if self.exit_until is not None else tab.hints(self)
        if full:
            gfx.clear(ui.BG)
            ui.statusbar(sys, TITLE)
            self.minute = self.t[4]
            _tabbar(self.tab, dots)
            self.dots = dots
            tab.draw(self, now, True)
            ui.footer(hints)
            self.hints = hints
            sys.show()
            return
        if self.t[4] != self.minute:
            self.minute = self.t[4]
            ui.statusbar(sys, TITLE)
            sys.show(0, ui.STATUS_H)
        if dots != self.dots:
            self.dots = dots
            _tabbar(self.tab, dots)
            sys.show(ui.STATUS_H, TOP)
        band = tab.draw(self, now, False)
        if band:
            sys.show(band[0], band[1])
        if hints is not self.hints:
            self.hints = hints
            ui.footer(hints)
            sys.show(ui.FOOTER_Y, 240)

    def wait(self):
        if self.timer.state == RING:
            return 50
        return 100 if self.tab == CLOCK or self.busy() else 250

    async def run(self):
        sys = self.sys
        full = True
        while True:
            now = time.ticks_ms()
            if self.tick(now):
                full = True
            self.draw(now, full)
            full = False
            ev = await sys.event(timeout_ms=self.wait())
            if ev is None:
                continue
            k, kind = B.key(ev), B.kind(ev)
            if kind == sys.HOME:
                return
            if kind == sys.REDRAW:
                full = True
                continue
            m = 1 << k
            if self.swallow & m:
                if kind != B.PRESS:
                    continue
                self.swallow &= ~m
            if self.timer.state == RING:
                if kind == B.PRESS:
                    self.timer.reset()
                    self.swallow |= m
                    _flash(sys, (0, 0, 0), 0)
                continue
            if sys.is_back(ev):
                if self.exit_until is not None or not self.busy():
                    return
                self.exit_until = time.ticks_add(time.ticks_ms(), 3000)
            elif kind == B.PRESS and k in (B.LEFT, B.RIGHT):
                self.tab = (self.tab + (1 if k == B.RIGHT else -1)) % len(TABS)
                full = True
            else:
                self.tabs[self.tab].key(k, kind, time.ticks_ms())

    def close(self):
        leds = self.sys.leds
        if leds:
            _flash(self.sys, (0, 0, 0), 0)
            leds.progress = None
            leds.color = tuple(settings.get("led_color"))
            leds.set_effect(settings.get("led_effect") if settings.get("leds_on") else "off")


async def main(sys):
    app = _App(sys)
    try:
        await app.run()
    finally:
        app.close()
