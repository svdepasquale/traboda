"""LED studio: a live preview of the 22 LEDs above the effect, colour, brightness, speed and
torch controls. Every change shows at once and is saved when you leave."""

import time

from .. import buttons as B
from .. import gfx, icons, settings, ui
from ..display import rgb
from ..leds import EFFECTS, hsv

TITLE = "Luci"
ICON = "lights"
MEDIA_KEYS = False

PRESETS = (
    ("Rosa RomHack", (255, 45, 111)), ("Rosso", (255, 0, 0)), ("Arancio", (255, 96, 0)),
    ("Giallo", (255, 200, 0)), ("Lime", (140, 255, 0)), ("Verde", (0, 255, 64)),
    ("Ciano", (0, 220, 255)), ("Blu", (0, 64, 255)), ("Viola", (150, 0, 255)),
    ("Magenta", (255, 0, 200)), ("Bianco", (255, 255, 255)), ("Bianco caldo", (255, 160, 80)),
)
CUSTOM = "Personalizzato"
FX = tuple(e for e in EFFECTS if e != "off")
FX_NAMES = {"solid": "Fisso", "breathe": "Respiro", "rainbow": "Arcobaleno", "wave": "Onda",
            "comet": "Cometa", "scanner": "Scanner", "sparkle": "Scintille", "fire": "Fuoco",
            "police": "Polizia", "vu": "VU meter"}
NO_COLOR = ("rainbow", "scanner", "fire", "police", "vu")      # effects with their own colours
SPEEDS = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0)
ROWS = (("on", "LED accesi", "lights"), ("fx", "Effetto", "fx"), ("color", "Colore", "palette"),
        ("level", "Luminosità", "sun"), ("speed", "Velocità", "speed"), ("torch", "Torcia", "torch"))
HOME = "home"

PREV_Y = 21         # preview card
PREV_H = 40
LIST_Y = 64
ROW_H = 26
TILE_W = 70         # colour palette grid
TILE_H = 36
FIELD_X = 16        # HSV picker: 36 hues x 11 lightness steps
FIELD_Y = 58
CELL_W = 8
CELL_H = 10

_SOFT = rgb(200, 204, 222)
_OFF = rgb(14, 16, 30)
_PANEL = (24, 28, 48)
_INK = rgb(40, 40, 56)

icons.register("fx", (
    "................",
    "....y...........",
    "....y.......P...",
    "...yoy.....PwP..",
    "..yowoy.....P...",
    "yyowwwoyy.......",
    "..yowoy.........",
    "...yoy..........",
    "....y......B....",
    "....y.....BwB...",
    "...........B....",
    ".......P........",
    "......PwP.......",
    ".......P........",
    "................",
    "................",
))
icons.register("palette", (
    "................",
    "....PPPPrrrr....",
    "...PPPPPrrrrr...",
    "..PPPPPPrrrrrr..",
    ".vvvPPPPrrrrooo.",
    ".vvvvPPwwrroooo.",
    ".vvvvvw..wooooo.",
    ".vvvvw....woooo.",
    ".vvvvw....woooo.",
    ".BBBBBw..wyyyyy.",
    ".BBBBBBwwyyyyyy.",
    ".BBBBBGGGGyyyyy.",
    "..BBBBGGGGyyyy..",
    "...BBGGGGGGyy...",
    "....BGGGGGGy....",
    "................",
))
icons.register("sun", (
    "................",
    ".......yy.......",
    "..y....yy....y..",
    "...y........y...",
    "......oooo......",
    ".....oyyyyo.....",
    "....oyyyyyyo....",
    "yy..oyyyyyyo..yy",
    "yy..oyyyyyyo..yy",
    "....oyyyyyyo....",
    ".....oyyyyo.....",
    "......oooo......",
    "...y........y...",
    "..y....yy....y..",
    ".......yy.......",
    "................",
))
icons.register("speed", (
    "................",
    "................",
    "................",
    "..B.....B.......",
    "..BB....BB......",
    "..BwB...BwB.....",
    "..BBwB..BBwB....",
    "..BBBwB.BBBwB...",
    "..BBBBB.BBBBB...",
    "..BBBB..BBBB....",
    "..BBB...BBB.....",
    "..BB....BB......",
    "..B.....B.......",
    "................",
    "................",
    "................",
))
icons.register("torch", (
    "..o....oo....o..",
    "...o...oo...o...",
    "....o..oo..o....",
    "................",
    "...kkkkkkkkkk...",
    "...kyyyyyyyyk...",
    "...kkkkkkkkkk...",
    "....kllllllk....",
    ".....kllllk.....",
    ".....kdrrdk.....",
    ".....kddddk.....",
    ".....kddddk.....",
    ".....kddddk.....",
    ".....kddddk.....",
    ".....kkkkkk.....",
    "................",
))


def _preset(color):
    for name, c in PRESETS:
        if c == color:
            return name
    return None


def _speed_text(s):
    return ("%.2f" % s).rstrip("0").rstrip(".").replace(".", ",") + "×"


def _hl_color(h, l):
    """Hue step 0-35 and lightness step (0 dark, 5 pure, 10 white) to (r, g, b)."""
    if l > 5:
        return hsv(h / 36, (10 - l) / 5, 1.0)
    return hsv(h / 36, 1.0, 0.2 + 0.16 * l)


def _to_hl(c):
    r, g, b = c
    hi, lo = max(c), min(c)
    if hi == 0:
        return 0, 0
    span = hi - lo
    if span == 0:
        h = 0
    elif hi == r:
        h = (g - b) / span % 6
    elif hi == g:
        h = (b - r) / span + 2
    else:
        h = (r - g) / span + 4
    if span / hi < 0.9:
        l = 5 + int((1 - span / hi) * 5 + 0.5)
    else:
        l = int((hi / 255 - 0.2) / 0.16 + 0.5)
    return int(h * 6 + 0.5) % 36, max(0, min(10, l))


def _tile_xy(i):
    if i < len(PRESETS):
        return 8 + i % 4 * (TILE_W + 8), 58 + i // 4 * (TILE_H + 10), TILE_W, TILE_H
    return 8, 196, 304, 22


def _draw_torch():
    gfx.clear(ui.WHITE)
    for i in range(12):
        f = i / 11
        gfx.circle(160, 86, 100 - i * 6, rgb(255, 255 - int(30 * f), 255 - int(120 * f)), True)
    icons.draw(gfx.fb, "torch", 128, 50, 4)
    gfx.text("Torcia accesa", 160, 158, _INK, "large", align=1)
    gfx.text("premi un tasto per spegnere", 160, 202, rgb(110, 112, 130), align=1)


class Studio:
    def __init__(self, sys):
        self.sys = sys
        self.leds = sys.leds
        self.custom = None
        self.dirty = False
        self.sel = 0
        self.sigs = [None] * len(ROWS)
        self.hints = None
        self.frame = None
        self.next_frame = 0
        self.load()

    def load(self):
        """State from settings and the live engine (read again after the quick panel)."""
        self.on = bool(settings.get("leds_on"))
        fx = settings.get("led_effect")
        self.fx = fx if fx in FX else "rainbow"
        self.color = tuple(settings.get("led_color"))
        self.level = max(5, min(100, settings.get("led_brightness")))
        speed = self.leds.speed if self.leds else settings.get("led_speed", 1.0)
        self.speed = min(range(len(SPEEDS)), key=lambda i: abs(SPEEDS[i] - speed))
        if _preset(self.color) is None:
            self.custom = self.color

    def apply(self, fx=None, color=None):
        leds = self.leds
        if leds:
            leds.level = self.level / 100
            leds.speed = SPEEDS[self.speed]
            leds.set_effect(fx or (self.fx if self.on else "off"), color or self.color)

    def store(self):
        settings.set("leds_on", self.on, False)
        settings.set("led_effect", self.fx, False)
        settings.set("led_color", list(self.color), False)
        settings.set("led_brightness", self.level, False)
        settings.set("led_speed", SPEEDS[self.speed], False)
        self.dirty = True

    def close(self):
        self.apply()
        if self.dirty:
            settings.save()

    def preview_fx(self):
        return self.fx if self.on and self.fx not in NO_COLOR else "solid"

    def set_color(self, c):
        """A colour choice also lights the LEDs, with an effect that shows it."""
        self.color = c
        if _preset(c) is None:
            self.custom = c
        self.on = True
        if self.fx in NO_COLOR:
            self.fx = "solid"

    def change(self, key, d):
        if key == "on":
            self.on = not self.on
        elif key == "fx":
            i = FX.index(self.fx) if self.fx in FX else 0
            self.fx = FX[(i + d) % len(FX)]
            self.on = True
        elif key == "color":
            colors = [c for _, c in PRESETS]
            if self.custom:
                colors.append(self.custom)
            i = colors.index(self.color) if self.color in colors else 0
            self.set_color(colors[(i + d) % len(colors)])
        elif key == "level":
            v = max(5, min(100, self.level + 5 * d))
            if v == self.level:
                return
            self.level = v
        elif key == "speed":
            v = max(0, min(len(SPEEDS) - 1, self.speed + d))
            if v == self.speed:
                return
            self.speed = v
        else:
            return
        self.apply()
        self.store()

    # -- main screen -----------------------------------------------------------------------

    def value(self, key):
        if key == "on":
            return "ON" if self.on else "OFF"
        if key == "fx":
            return FX_NAMES.get(self.fx, self.fx)
        if key == "color":
            return _preset(self.color) or CUSTOM
        if key == "level":
            return "%d%%" % self.level
        if key == "speed":
            return _speed_text(SPEEDS[self.speed])
        return ""

    def draw_row(self, i):
        """Draws row i if what it shows changed; returns True when it did."""
        key, label, icon = ROWS[i]
        selected = i == self.sel
        value = self.value(key)
        sig = (selected, value, self.color if key == "color" else None)
        if sig == self.sigs[i]:
            return False
        self.sigs[i] = sig
        y = LIST_Y + i * ROW_H
        ty = y + 5
        gfx.fill_rect(0, y, 320, ROW_H, ui.BG)
        if selected:
            gfx.round_rect(4, y + 1, 312, ROW_H - 2, 6, ui.PANEL2)
            gfx.fill_rect(4, y + 5, 3, ROW_H - 10, ui.ACCENT)
        icons.draw(gfx.fb, icon, 14, ty, 1)
        gfx.text(label, 36, ty, ui.TEXT if selected else _SOFT)
        x = 306
        if key == "on":
            gfx.text(value, x, ty, ui.GREEN if self.on else ui.DIM, align=-1)
        elif key == "torch":
            if selected:
                x -= gfx.text("accendi", x, ty, ui.CYAN, align=-1) + 18
                gfx.round_rect(x, y + 7, 14, 13, 3, ui.PANEL)
                gfx.text("A", x + 7, ty, ui.YELLOW, align=1)
        else:
            color = ui.CYAN if selected else ui.DIM
            if selected:
                x -= gfx.text("►", x, ty, color, align=-1) + 4
            x -= gfx.text(value, x, ty, color, align=-1)
            if key == "color":
                x -= 20
                gfx.round_rect(x, y + 6, 14, 14, 3, rgb(*self.color))
                gfx.round_rect(x, y + 6, 14, 14, 3, ui.LINE, False)
            elif key in ("level", "speed"):
                frac = (self.level - 5) / 95 if key == "level" else self.speed / (len(SPEEDS) - 1)
                x -= 54
                gfx.bar(x, y + 10, 46, 6, frac, ui.ACCENT if selected else ui.DIM, ui.PANEL, 3)
            if selected:
                gfx.text("◄", x - 4, ty, color, align=-1)
        return True

    def draw_preview(self):
        gfx.round_rect(4, PREV_Y, 312, PREV_H, 8, ui.PANEL)
        frame = self.frame
        if frame is None:
            gfx.text("LED non disponibili", 160, PREV_Y + 12, ui.DIM, align=1)
            return
        k = 0.65 + 0.35 * self.level / 100
        pr, pg, pb = _PANEL
        for core in (False, True):
            for pos in range(22):
                r, g, b = frame[pos]
                x = 25 + pos % 11 * 27
                y = PREV_Y + 12 + pos // 11 * 17
                lit = r or g or b
                if not core:
                    if lit:
                        gfx.circle(x, y, 10, rgb(max(0, int(pr + (r * k - pr) * 0.3)),
                                                 max(0, int(pg + (g * k - pg) * 0.3)),
                                                 max(0, int(pb + (b * k - pb) * 0.3))), True)
                    continue
                gfx.circle(x, y, 8, ui.BG, True)
                if lit:
                    r, g, b = int(r * k), int(g * k), int(b * k)
                    gfx.circle(x, y, 7, rgb(r, g, b), True)
                    gfx.fill_rect(x - 4, y - 4, 2, 2, rgb(128 + r // 2, 128 + g // 2, 128 + b // 2))
                else:
                    gfx.circle(x, y, 7, _OFF, True)

    def tick(self, force=False):
        """Mirrors the engine's frame at ~10 fps; True when the preview was redrawn."""
        now = time.ticks_ms()
        if not force and time.ticks_diff(now, self.next_frame) < 0:
            return False
        self.next_frame = time.ticks_add(now, 100)
        frame = list(self.leds.frame) if self.leds else None
        if not force and frame == self.frame:
            return False
        self.frame = frame
        self.draw_preview()
        return True

    def footer(self):
        key = ROWS[self.sel][0]
        if key == "on":
            hints = [("A", "Spegni" if self.on else "Accendi")]
        elif key == "color":
            hints = [("◄►", "Cambia"), ("A", "Tavolozza")]
        elif key == "torch":
            hints = [("A", "Accendi")]
        else:
            hints = [("◄►", "Regola")]
        hints.append(("A tieni", "Esci"))
        if hints == self.hints:
            return False
        self.hints = hints
        ui.footer(hints)
        return True

    def draw(self):
        gfx.clear(ui.BG)
        ui.statusbar(self.sys, TITLE)
        self.sigs = [None] * len(ROWS)
        self.hints = None
        self.tick(True)
        for i in range(len(ROWS)):
            self.draw_row(i)
        self.footer()
        self.sys.show()

    def refresh(self):
        y0, y1 = 240, 0
        for i in range(len(ROWS)):
            if self.draw_row(i):
                y0 = min(y0, LIST_Y + i * ROW_H)
                y1 = max(y1, LIST_Y + (i + 1) * ROW_H)
        if y1 > y0:
            self.sys.show(y0, y1)
        if self.footer():
            self.sys.show(ui.FOOTER_Y, 240)

    async def run(self):
        sys = self.sys
        self.draw()
        while True:
            ev = await sys.event(timeout_ms=50)
            if self.tick():
                sys.show(PREV_Y, PREV_Y + PREV_H)
            if ev is None:
                continue
            k, kind = B.key(ev), B.kind(ev)
            if kind == sys.REDRAW:
                self.load()
                self.draw()
                continue
            if sys.is_back(ev):
                return
            key = ROWS[self.sel][0]
            if k == B.A and kind == B.CLICK:
                if key == "on":
                    self.change("on", 1)
                elif key in ("color", "torch"):
                    if await (self.palette() if key == "color" else self.torch()) == HOME:
                        return
                    self.draw()
                    continue
            elif kind in (B.PRESS, B.REPEAT) and k in (B.UP, B.DOWN):
                self.sel = (self.sel + (1 if k == B.DOWN else -1)) % len(ROWS)
            elif kind in (B.PRESS, B.REPEAT) and k in (B.LEFT, B.RIGHT):
                self.change(key, 1 if k == B.RIGHT else -1)
            else:
                continue
            self.refresh()

    # -- colour palette --------------------------------------------------------------------

    def draw_tile(self, i, selected, grad=None):
        x, y, w, h = _tile_xy(i)
        gfx.fill_rect(x - 4, y - 4, w + 8, h + 8, ui.BG)
        if selected:
            gfx.round_rect(x - 3, y - 3, w + 6, h + 6, 9, ui.WHITE)
        if i < len(PRESETS):
            c = PRESETS[i][1]
            gfx.round_rect(x, y, w, h, 7, rgb(*c))
            if c == self.color:
                ink = ui.BLACK if c[0] * 3 + c[1] * 6 + c[2] > 1200 else ui.WHITE
                gfx.text("✓", x + w - 12, y + 2, ink)
            return
        for j in range(w):
            gfx.vline(x + j, y, h, grad[j])
        corner = ui.WHITE if selected else ui.BG
        for d, run in enumerate((3, 2, 1, 1)):
            gfx.hline(x, y + d, run, corner)
            gfx.hline(x + w - run, y + d, run, corner)
            gfx.hline(x, y + h - 1 - d, run, corner)
            gfx.hline(x + w - run, y + h - 1 - d, run, corner)
        gfx.round_rect(92, y + 3, 136, 16, 6, ui.BG)
        gfx.text(CUSTOM + "…", 160, y + 3, ui.TEXT, align=1)
        if self.custom:
            gfx.round_rect(x + 8, y + 4, 14, 14, 3, ui.WHITE)
            gfx.round_rect(x + 10, y + 6, 10, 10, 2, rgb(*self.custom))

    async def palette(self):
        sys = self.sys
        colors = [c for _, c in PRESETS]
        sel = colors.index(self.color) if self.color in colors else len(PRESETS)
        col = sel % 4
        grad = [rgb(*hsv(j / 304)) for j in range(304)]
        full = True
        old = sel
        while True:
            self.apply(self.preview_fx(), colors[sel] if sel < len(PRESETS) else self.custom or self.color)
            if full:
                ui.header(sys, "Colore", "palette")
                for i in range(len(PRESETS) + 1):
                    self.draw_tile(i, i == sel, grad)
                ui.footer([("A", "Scegli"), ("A tieni", "Annulla")])
                full = False
            elif old != sel:
                self.draw_tile(old, False, grad)
                self.draw_tile(sel, True, grad)
            gfx.fill_rect(120, 22, 196, 20, ui.BG)
            gfx.text(PRESETS[sel][0] if sel < len(PRESETS) else CUSTOM, 310, 24, ui.CYAN, align=-1)
            sys.show()
            old = sel
            ev = await sys.event()
            if ev is None:
                continue
            k, kind = B.key(ev), B.kind(ev)
            if kind == sys.REDRAW:
                full = True
                continue
            if kind == sys.HOME:
                return HOME
            if sys.is_back(ev):
                self.apply()
                return None
            if k == B.A and kind == B.CLICK:
                if sel < len(PRESETS):
                    self.set_color(colors[sel])
                    self.apply()
                    self.store()
                    return None
                chosen = await self.picker()
                if chosen:
                    return chosen
                full = True
                continue
            if kind not in (B.PRESS, B.REPEAT):
                continue
            n = len(PRESETS)
            if k == B.LEFT:
                sel = (sel - 1) % (n + 1)
            elif k == B.RIGHT:
                sel = (sel + 1) % (n + 1)
            elif k == B.UP:
                sel = n - 4 + col if sel == n else n if sel < 4 else sel - 4
            elif k == B.DOWN:
                sel = col if sel == n else n if sel >= n - 4 else sel + 4
            if sel < n:
                col = sel % 4

    # -- custom colour picker --------------------------------------------------------------

    async def picker(self):
        """Hue x lightness field. Returns True when a colour was chosen, HOME, or None."""
        sys = self.sys
        h, l = _to_hl(self.custom or self.color)
        cells = [rgb(*_hl_color(i % 36, 10 - i // 36)) for i in range(36 * 11)]
        full = True
        while True:
            c = _hl_color(h, l)
            self.apply(self.preview_fx(), c)
            if full:
                ui.header(sys, CUSTOM, "palette")
                ui.footer([("A", "Scegli"), ("A tieni", "Annulla")])
            gfx.fill_rect(FIELD_X - 2, FIELD_Y - 2, 36 * CELL_W + 4, 11 * CELL_H + 4, ui.BG)
            for i in range(36 * 11):
                gfx.fill_rect(FIELD_X + i % 36 * CELL_W, FIELD_Y + i // 36 * CELL_H, CELL_W, CELL_H, cells[i])
            x = FIELD_X + h * CELL_W
            y = FIELD_Y + (10 - l) * CELL_H
            gfx.rect(x - 2, y - 2, CELL_W + 4, CELL_H + 4, ui.BLACK)
            gfx.rect(x - 1, y - 1, CELL_W + 2, CELL_H + 2, ui.WHITE)
            gfx.fill_rect(0, 174, 320, 48, ui.BG)
            gfx.round_rect(16, 176, 64, 40, 8, rgb(*c))
            gfx.round_rect(16, 176, 64, 40, 8, ui.LINE, False)
            gfx.text("#%02X%02X%02X" % c, 92, 176, ui.TEXT, "title")
            gfx.text("◄►", 92, 201, ui.YELLOW)
            gfx.text("tinta %d°" % (h * 10), 112, 201, ui.DIM)
            gfx.text("▲▼", 206, 201, ui.YELLOW)
            gfx.text("luce %d%%" % (l * 10), 226, 201, ui.DIM)
            if full:
                sys.show()
                full = False
            else:
                sys.show(FIELD_Y - 2, ui.FOOTER_Y)
            ev = await sys.event()
            if ev is None:
                continue
            k, kind = B.key(ev), B.kind(ev)
            if kind == sys.REDRAW:
                full = True
                continue
            if kind == sys.HOME:
                return HOME
            if sys.is_back(ev):
                return None
            if k == B.A and kind == B.CLICK:
                self.set_color(c)
                self.apply()
                self.store()
                return True
            if kind not in (B.PRESS, B.REPEAT):
                continue
            if k in (B.LEFT, B.RIGHT):
                h = (h + (1 if k == B.RIGHT else -1)) % 36
            elif k in (B.UP, B.DOWN):
                l = max(0, min(10, l + (1 if k == B.UP else -1)))

    # -- torch -----------------------------------------------------------------------------

    async def torch(self):
        """Every LED white at the highest allowed level, the screen white too, until a key."""
        sys = self.sys
        bright = sys.display.brightness
        if self.leds:
            self.leds.level = 1.0
            self.leds.set_effect("solid", (255, 255, 255))
        sys.display.set_brightness(100)
        try:
            full = True
            while True:
                if full:
                    _draw_torch()
                    sys.show()
                    full = False
                sys.buttons.last_activity = time.ticks_ms()
                ev = await sys.event(timeout_ms=1000)
                if ev is None:
                    continue
                kind = B.kind(ev)
                if kind == sys.REDRAW:
                    full = True
                elif kind == sys.HOME:
                    return HOME
                elif kind in (B.CLICK, B.LONG):
                    return None
        finally:
            sys.display.set_brightness(bright)
            self.apply()


async def main(sys):
    studio = Studio(sys)
    try:
        await studio.run()
    finally:
        studio.close()
