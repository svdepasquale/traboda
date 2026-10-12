"""Name tag: your nickname in big letters, a tagline, a scrolling line and a matching LED
show, in three styles. The screen stays on while the badge is shown."""

import time

from .. import buttons as B
from .. import gfx, icons, settings, ui
from ..display import rgb

TITLE = "Badge"
ICON = "badge"
MEDIA_KEYS = False

STYLES = ("RomHack", "Neon", "Ciao!")
STYLE_LEDS = (("wave", (255, 45, 111)), ("comet", (45, 226, 230)), ("breathe", (255, 45, 111)))
MARQUEE = "Fermami e parliamo di hacking  •  RomHack Camp 2026"
HINTS = [("A", "Modifica"), ("◄►", "Stile"), ("A tieni", "Esci")]
HINT_MS = 4000
SCROLL = 0.035          # marquee speed, px per ms
HOME = "home"
_SIZES = (("large", 3), ("title", 3), ("large", 2), ("title", 2), ("large", 1), ("title", 1),
          ("text", 1))
_INK = rgb(24, 24, 36)
_GRID = rgb(150, 30, 170)
_BANDS = ((ui.ACCENT_DARK, ui.ACCENT, ui.WHITE), (ui.BLACK, ui.ACCENT, ui.CYAN),
          (ui.PANEL, ui.LINE, ui.WHITE))         # marquee: background, top line, text

icons.register("quote", (
    "................",
    "................",
    "..wwwwwwwwwwww..",
    ".wwwwwwwwwwwwww.",
    ".wwddddddddddww.",
    ".wwwwwwwwwwwwww.",
    ".wwddddddddwwww.",
    ".wwwwwwwwwwwwww.",
    "..wwwwwwwwwwww..",
    "....www.........",
    "...ww...........",
    "..w.............",
    "................",
    "................",
    "................",
    "................",
))
icons.register("brush", (
    "................",
    "............dd..",
    "...........dlld.",
    "..........dlld..",
    ".........dlld...",
    "........dlld....",
    ".......dlld.....",
    "......oood......",
    ".....PPoo.......",
    "....PPPP........",
    "...PPPPP........",
    "..PPPPP.........",
    ".PPPP...........",
    ".PP.............",
    "................",
    "................",
))
icons.register("ticker", (
    "................",
    "................",
    "...B............",
    "..BB............",
    ".BBBBBBBBBBBBBB.",
    "..BB............",
    "...B............",
    "................",
    ".wwwww.wwww.www.",
    "................",
    ".www.wwwww.wwww.",
    "................",
    ".wwww.www.wwwww.",
    "................",
    "................",
    "................",
))


def _text(s, x, y, color, f, k):
    if k == 1:
        gfx.text(s, x, y, color, f, align=1)
    else:
        gfx.text_scaled(s, x, y, color, f, k, align=1)


def _name(s, cy, color, maxw, maxh, shadow=None):
    """The nickname centred on (160, cy), as large as fits in maxw x maxh."""
    if len(s) * 8 > maxw:
        s = gfx.ellipsize(s, maxw)
    f, k, h = "text", 1, 16
    for f_, k_ in _SIZES:
        font = gfx.font(f_)
        if len(s) * font.w * k_ <= maxw and font.h * k_ <= maxh:
            f, k, h = f_, k_, font.h * k_
            break
    y = cy - h // 2
    if shadow is not None:
        _text(s, 160 + k, y + k, shadow, f, k)
    _text(s, 160, y, color, f, k)


def _tag_lines(s, maxw=300):
    """The tagline as (font, lines): one "title" line when it fits, else two of "text"."""
    if not s:
        return "title", []
    if len(s) * 12 <= maxw:
        return "title", [s]
    lines = gfx.wrap(s, maxw)
    if len(lines) > 2:
        lines = [lines[0], gfx.ellipsize(" ".join(lines[1:]), maxw)]
    return "text", lines


def _tagline(tag, cy, color):
    f, lines = tag
    h = gfx.font(f).h
    y = cy - h * len(lines) // 2
    for i, line in enumerate(lines):
        gfx.text(line, 160, y + h * i, color, f, align=1)


def _draw(style, nick, tagline):
    if style == 0:
        tag = _tag_lines(tagline, 288)
        gfx.gradient_v(0, 18, 320, 204, (46, 8, 38), (10, 12, 24))
        gfx.round_rect(6, 24, 308, 192, 10, ui.ACCENT, False)
        gfx.round_rect(9, 27, 302, 186, 8, ui.ACCENT_DARK, False)
        gfx.text("ciao, sono", 160, 38, ui.ACCENT, align=1)
        _name(nick, 104, ui.WHITE, 288, 96, ui.ACCENT)
        if tag[1]:
            gfx.fill_rect(130, 160, 60, 3, ui.ACCENT)
            _tagline(tag, 186, ui.CYAN)
    elif style == 1:
        tag = _tag_lines(tagline)
        gfx.gradient_v(0, 18, 320, 140, (0, 0, 0), (64, 0, 84))
        gfx.fill_rect(0, 158, 320, 64, ui.BLACK)
        for i in range(1, 8):
            gfx.hline(0, 158 + 63 * i * i // 49, 320, _GRID)
        for i in range(-8, 9):
            gfx.line(160 + i * 14, 158, 160 + i * 64, 221, _GRID)
        gfx.hline(0, 158, 320, ui.ACCENT)
        _name(nick, 70, ui.CYAN, 300, 96, ui.ACCENT)
        _tagline(tag, 137, ui.YELLOW)
    else:
        tag = _tag_lines(tagline)
        band = 178 if len(tag[1]) > 1 else 190
        gfx.fill_rect(0, 18, 320, 66, ui.ACCENT)
        gfx.text("CIAO!", 160, 22, ui.WHITE, "large", align=1)
        gfx.text("mi chiamo", 160, 60, ui.WHITE, align=1)
        gfx.fill_rect(0, 84, 320, band - 84, ui.WHITE)
        _name(nick, (84 + band) // 2, _INK, 300, band - 92)
        gfx.fill_rect(0, band, 320, ui.FOOTER_Y - band, ui.ACCENT)
        _tagline(tag, (band + ui.FOOTER_Y) // 2, ui.WHITE)


def _leds(sys, style):
    leds = sys.leds
    if leds:
        if settings.get("badge_leds", True):
            leds.set_effect(STYLE_LEDS[style][0], STYLE_LEDS[style][1])
        else:
            leds.set_effect("off")


def _restore_leds(sys):
    leds = sys.leds
    if leds:
        leds.color = tuple(settings.get("led_color"))
        leds.set_effect(settings.get("led_effect") if settings.get("leds_on") else "off")


async def _show(sys):
    full = True
    hints = True
    last = time.ticks_ms()
    hints_until = time.ticks_add(last, HINT_MS)
    style = 0
    off = 0.0
    loop = ""
    width = 0
    clock = None
    clock_due = last
    while True:
        now = time.ticks_ms()
        sys.buttons.last_activity = now         # a name tag never dims
        if full:
            style = settings.get("badge_style", 0) % len(STYLES)
            text = settings.get("badge_marquee", MARQUEE)
            text = text + "   •   " if text else ""
            width = len(text) * 8
            loop = text * (42 // max(1, len(text)) + 2)
            _leds(sys, style)
            _draw(style, settings.get("nickname"), settings.get("tagline"))
            ui.statusbar(sys)
            clock = sys.clock_text()
            clock_due = time.ticks_add(now, 1000)
        expired = hints and time.ticks_diff(now, hints_until) >= 0
        if expired:
            hints = False
        if full or expired or not hints and width:
            if hints:
                ui.footer(HINTS)
            else:
                bg, line, fg = _BANDS[style]
                gfx.fill_rect(0, ui.FOOTER_Y, 320, 240 - ui.FOOTER_Y, bg)
                gfx.hline(0, ui.FOOTER_Y, 320, line)
                if width:
                    off = (off + time.ticks_diff(now, last) * SCROLL) % width
                    px = int(off)
                    gfx.text(loop[px // 8:px // 8 + 42], -(px % 8), ui.FOOTER_Y + 1, fg)
            if full:
                sys.show()
            else:
                sys.show(ui.FOOTER_Y, 240)
        full = False
        if time.ticks_diff(now, clock_due) >= 0:
            clock_due = time.ticks_add(now, 1000)
            if sys.clock_text() != clock:
                clock = sys.clock_text()
                ui.statusbar(sys)
                sys.show(0, ui.STATUS_H)
        last = now
        ev = await sys.event(timeout_ms=40)
        if ev is None:
            continue
        k, kind = B.key(ev), B.kind(ev)
        if kind == sys.REDRAW:
            full = True
            continue
        if sys.is_back(ev):
            return
        if k == B.A and kind == B.CLICK:
            if await _edit(sys) == HOME:
                return
            full = True
        elif kind != B.PRESS:
            continue
        if k in (B.LEFT, B.RIGHT):
            style = (style + (1 if k == B.RIGHT else -1)) % len(STYLES)
            settings.set("badge_style", style, False)       # saved on the way out
            full = True
        hints = True
        hints_until = time.ticks_add(time.ticks_ms(), HINT_MS)
        if not full:
            ui.footer(HINTS)
            sys.show(ui.FOOTER_Y, 240)


# -- edit menu -------------------------------------------------------------------------------

def _items():
    marquee = settings.get("badge_marquee", MARQUEE)
    return [
        ui.Item("Nome", gfx.ellipsize(settings.get("nickname"), 150), "badge", tag="nick"),
        ui.Item("Motto", gfx.ellipsize(settings.get("tagline") or "nessuno", 150), "quote", tag="tag"),
        ui.Item("Stile", STYLES[settings.get("badge_style", 0) % len(STYLES)], "brush", "choice",
                choices=list(STYLES), tag="style"),
        ui.Item("Scritta", gfx.ellipsize(marquee or "spenta", 150), "ticker", tag="marquee"),
        ui.Item("LED animati", settings.get("badge_leds", True), "lights", "toggle", tag="leds"),
    ]


def _adjust(sys, it, d):
    if it.tag == "style":
        style = (settings.get("badge_style", 0) + d) % len(STYLES)
        settings.set("badge_style", style, False)
    else:
        style = settings.get("badge_style", 0) % len(STYLES)
        settings.set("badge_leds", not it.value, False)
    _leds(sys, style)


async def _type(sys, tag):
    if tag == "nick":
        s = await ui.keyboard(sys, "Il tuo nome", settings.get("nickname"), max_len=24)
        if s is not None and s.strip():
            settings.set("nickname", s.strip())
    elif tag == "tag":
        s = await ui.keyboard(sys, "Motto", settings.get("tagline"), max_len=48)
        if s is not None:
            settings.set("tagline", s.strip())
    else:
        s = await ui.keyboard(sys, "Scritta scorrevole", settings.get("badge_marquee", MARQUEE))
        if s is not None:
            settings.set("badge_marquee", s.strip())


async def _edit(sys):
    sel = 0
    full = True
    changed = True
    y0 = 0
    try:
        while True:
            items = _items()
            if full:
                y0 = ui.header(sys, "Modifica badge", ICON)
                ui.footer([("A", "Modifica"), ("◄►", "Cambia"), ("A tieni", "Fine")])
            if full or changed:
                ui.draw_list(items, sel, 0, y0, len(items))
                if full:
                    sys.show()
                else:
                    sys.show(y0, y0 + len(items) * ui.ROW_H)
                full = changed = False
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
            it = items[sel]
            if k == B.A and kind == B.CLICK:
                if it.kind:
                    _adjust(sys, it, 1)
                    changed = True
                else:
                    await _type(sys, it.tag)
                    full = True
            elif kind in (B.PRESS, B.REPEAT):
                if k in (B.UP, B.DOWN):
                    sel = (sel + (1 if k == B.DOWN else -1)) % len(items)
                    changed = True
                elif k in (B.LEFT, B.RIGHT) and it.kind:
                    _adjust(sys, it, 1 if k == B.RIGHT else -1)
                    changed = True
    finally:
        settings.save()


async def main(sys):
    style = settings.get("badge_style", 0)
    try:
        await _show(sys)
    finally:
        _restore_leds(sys)
        if settings.get("badge_style", 0) != style:
            settings.save()
