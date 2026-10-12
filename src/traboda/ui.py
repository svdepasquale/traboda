"""Theme and widgets: status bar, header, footer hints, menus, dialogs, keyboard, toasts.

Widgets draw into the framebuffer and push it; the async ones take the System object to
read keys. Layout: status bar 0-17, content 18-221, footer 222-239.
"""

from . import buttons as B
from . import gfx, icons
from .display import H, W, rgb

BG = rgb(10, 12, 24)
PANEL = rgb(24, 28, 48)
PANEL2 = rgb(38, 44, 74)
LINE = rgb(52, 60, 96)
ACCENT = rgb(255, 45, 111)       # RomHack pink
ACCENT_DARK = rgb(120, 18, 58)
CYAN = rgb(45, 226, 230)
YELLOW = rgb(255, 214, 10)
GREEN = rgb(61, 220, 132)
ORANGE = rgb(255, 150, 40)
RED = rgb(255, 77, 77)
TEXT = rgb(236, 238, 245)
DIM = rgb(132, 140, 172)
BLACK = rgb(0, 0, 0)
WHITE = rgb(255, 255, 255)

STATUS_H = 18
FOOTER_Y = 222
CONTENT_Y = STATUS_H
CONTENT_H = FOOTER_Y - STATUS_H


def statusbar(sys, title=None):
    gfx.fill_rect(0, 0, W, STATUS_H, PANEL)
    gfx.hline(0, STATUS_H - 1, W, LINE)
    gfx.text(sys.clock_text(), 6, 1, TEXT)
    if title:
        gfx.text(gfx.ellipsize(title, 150), W // 2, 1, DIM, align=1)
    x = W - 4
    pct = sys.battery
    if pct is not None:
        label = "%d%%" % pct
        x -= gfx.text(label, x, 1, GREEN if pct > 30 else YELLOW if pct > 12 else RED, align=-1)
        x -= 4
        _battery_glyph(x - 18, 4, pct, sys.charging)
        x -= 22
    if sys.wifi_connected():
        _wifi_glyph(x - 14, 3)
        x -= 18
    if sys.audio.playing:
        gfx.text("♪", x, 1, ACCENT if not sys.audio.paused else DIM, align=-1)
        x -= 12


def _battery_glyph(x, y, pct, charging):
    gfx.rect(x, y, 16, 9, DIM)
    gfx.fill_rect(x + 16, y + 3, 2, 3, DIM)
    fill = max(1, 14 * pct // 100)
    gfx.fill_rect(x + 1, y + 1, fill, 7, GREEN if pct > 30 else YELLOW if pct > 12 else RED)
    if charging:
        gfx.line(x + 9, y + 1, x + 6, y + 5, YELLOW)
        gfx.line(x + 6, y + 5, x + 10, y + 4, YELLOW)
        gfx.line(x + 10, y + 4, x + 7, y + 8, YELLOW)


def _wifi_glyph(x, y):
    for i, h in enumerate((3, 6, 9, 12)):
        gfx.fill_rect(x + i * 4, y + 12 - h, 3, h, CYAN)


def header(sys, title, icon=None, color=ACCENT):
    """Status bar plus a title band; returns the y where content starts."""
    gfx.clear(BG)
    statusbar(sys)
    y = STATUS_H + 4
    x = 10
    if icon:
        icons.draw(gfx.fb, icon, x, y, 1)
        x += 22
    gfx.text(title, x, y - 4, TEXT, "title")
    gfx.fill_rect(10, y + 22, 40, 2, color)
    return y + 30


def footer(hints, y=FOOTER_Y):
    """hints: [(key, label), ...] like [("A", "Apri"), ("B", "Indietro")]."""
    gfx.fill_rect(0, y, W, H - y, PANEL)
    gfx.hline(0, y, W, LINE)
    x = 6
    for k, label in hints:
        kw = max(14, len(k) * 8 + 6)
        gfx.round_rect(x, y + 3, kw, 13, 3, PANEL2)
        gfx.text(k, x + kw // 2, y + 1, YELLOW, align=1)
        x += kw + 4
        x += gfx.text(label, x, y + 1, DIM) + 10


def toast_draw(msg, color=PANEL2):
    lines = gfx.wrap(msg, 260)[:3]
    h = 16 * len(lines) + 16
    y = (H - h) // 2
    gfx.round_rect(24, y, W - 48, h, 8, color)
    gfx.round_rect(24, y, W - 48, h, 8, ACCENT, False)
    for i, line in enumerate(lines):
        gfx.text(line, W // 2, y + 8 + 16 * i, TEXT, align=1)


async def toast(sys, msg, ms=1200, color=PANEL2):
    toast_draw(msg, color)
    sys.show()
    await sys.sleep_ms(ms, interruptible=True)


# -- menu --------------------------------------------------------------------------------

class Item:
    """A menu row. value: shown on the right; kind: None, "toggle", "slider", "choice"."""

    def __init__(self, label, value=None, icon=None, kind=None, choices=None, step=10,
                 lo=0, hi=100, tag=None, detail=None):
        self.label = label
        self.value = value
        self.icon = icon
        self.kind = kind
        self.choices = choices
        self.step = step
        self.lo = lo
        self.hi = hi
        self.tag = tag if tag is not None else label
        self.detail = detail

    def right_text(self):
        if self.kind == "toggle":
            return "ON" if self.value else "OFF"
        if self.kind == "slider":
            return "%d%%" % self.value if self.hi == 100 else str(self.value)
        if self.value is None:
            return ""
        return str(self.value)

    def adjust(self, delta):
        if self.kind == "toggle":
            self.value = not self.value
            return True
        if self.kind == "slider":
            v = max(self.lo, min(self.hi, self.value + delta * self.step))
            if v != self.value:
                self.value = v
                return True
        if self.kind == "choice" and self.choices:
            i = self.choices.index(self.value) if self.value in self.choices else 0
            self.value = self.choices[(i + delta) % len(self.choices)]
            return True
        return False


ROW_H = 26


def draw_list(items, sel, top, y0, rows, accent=ACCENT):
    gfx.fill_rect(0, y0, W, rows * ROW_H, BG)
    for i in range(top, min(len(items), top + rows)):
        it = items[i]
        y = y0 + (i - top) * ROW_H
        selected = i == sel
        if selected:
            gfx.round_rect(4, y + 1, W - 8, ROW_H - 2, 6, PANEL2)
            gfx.fill_rect(4, y + 5, 3, ROW_H - 10, accent)
        x = 14
        if it.icon:
            icons.draw(gfx.fb, it.icon, x, y + 5, 1)
            x += 22
        right = it.right_text()
        avail = W - x - 14 - (len(right) * 8 + 8 if right else 0)
        gfx.text(gfx.ellipsize(it.label, avail), x, y + 5, TEXT if selected else rgb(200, 204, 222))
        if right:
            color = (GREEN if it.value else DIM) if it.kind == "toggle" else CYAN if selected else DIM
            if it.kind in ("slider", "choice") and selected:
                right = "◄ " + right + " ►"
            gfx.text(right, W - 14, y + 5, color, align=-1)
    if len(items) > rows:
        track = rows * ROW_H
        th = max(10, track * rows // len(items))
        ty = y0 + (track - th) * top // max(1, len(items) - rows)
        gfx.fill_rect(W - 3, y0, 2, track, PANEL)
        gfx.fill_rect(W - 3, ty, 2, th, accent)


async def menu(sys, title, items, icon=None, sel=0, hints=None, on_change=None, on_draw=None,
               accent=ACCENT):
    """Scrolling list. Returns the chosen Item (A) or None (B / home).

    Sliders, toggles and choices change with left/right (and toggles with A too);
    on_change(item) is called after each change.
    """
    rows = 6
    top = 0
    sel = max(0, min(sel, len(items) - 1))
    hints = hints or [("A", "Ok"), ("A tieni", "Indietro")]
    redraw_all = True
    while True:
        if sel < top:
            top = sel
        elif sel >= top + rows:
            top = sel - rows + 1
        if redraw_all:
            y0 = header(sys, title, icon, accent)
            footer(hints)
            redraw_all = False
        draw_list(items, sel, top, y0, rows, accent)
        if on_draw:
            on_draw(items[sel] if items else None)
        sys.show()
        ev = await sys.event()
        if ev is None:
            continue
        k, kind = B.key(ev), B.kind(ev)
        if kind == sys.REDRAW:
            redraw_all = True
            continue
        if sys.is_back(ev):
            return None
        if not items:
            continue
        it = items[sel]
        if k == B.A and kind == B.CLICK:
            if it.kind == "toggle":
                it.adjust(1)
                if on_change:
                    on_change(it)
            elif it.kind not in ("slider", "choice"):
                return it
            continue
        if kind not in (B.PRESS, B.REPEAT):
            continue
        if k == B.UP:
            sel = (sel - 1) % len(items)
        elif k == B.DOWN:
            sel = (sel + 1) % len(items)
        elif k in (B.LEFT, B.RIGHT) and it.kind in ("slider", "choice", "toggle"):
            if it.adjust(-1 if k == B.LEFT else 1) and on_change:
                on_change(it)


async def dialog(sys, title, message, options=("OK",), accent=ACCENT):
    """Modal box; returns the chosen option index, or None on B."""
    sel = 0
    lines = gfx.wrap(message, 256)[:5]
    h = 70 + 16 * len(lines)
    y = (H - h) // 2
    while True:
        gfx.round_rect(20, y, W - 40, h, 10, PANEL)
        gfx.round_rect(20, y, W - 40, h, 10, accent, False)
        gfx.text(title, W // 2, y + 10, TEXT, align=1)
        gfx.hline(40, y + 30, W - 80, LINE)
        for i, line in enumerate(lines):
            gfx.text(line, W // 2, y + 38 + 16 * i, rgb(200, 204, 222), align=1)
        bw = 84
        total = len(options) * bw + (len(options) - 1) * 10
        bx = (W - total) // 2
        by = y + h - 30
        for i, opt in enumerate(options):
            x = bx + i * (bw + 10)
            gfx.round_rect(x, by, bw, 22, 6, accent if i == sel else PANEL2)
            gfx.text(gfx.ellipsize(opt, bw - 8), x + bw // 2, by + 3, WHITE if i == sel else DIM, align=1)
        sys.show()
        ev = await sys.event()
        if ev is None:
            continue
        k, kind = B.key(ev), B.kind(ev)
        if sys.is_back(ev):
            return None
        if k == B.A and kind == B.CLICK:
            return sel
        if kind not in (B.PRESS, B.REPEAT):
            continue
        if k in (B.LEFT, B.UP):
            sel = (sel - 1) % len(options)
        elif k in (B.RIGHT, B.DOWN):
            sel = (sel + 1) % len(options)


# -- on-screen keyboard ------------------------------------------------------------------

_PAGES = (
    ("1234567890", "qwertyuiop", "asdfghjkl'", "zxcvbnm,.-"),
    ("1234567890", "QWERTYUIOP", "ASDFGHJKL\"", "ZXCVBNM;:_"),
    ("!@#$%^&*()", "[]{}<>/\\|~", "+=?`'\"€£°§", "àèéìòù¿¡·…"),
)
_SPECIAL = ("aA", "#!", "spazio", "canc", "OK")


async def keyboard(sys, title, text="", secret=False, max_len=64):
    """Text entry with the D-pad. Returns the string, or None when cancelled.
    A types, B deletes (or cancels when empty), play = OK."""
    page = 0
    row, col = 1, 0
    show_secret = False
    while True:
        gfx.clear(BG)
        statusbar(sys)
        gfx.text(title, 10, 22, TEXT, "title")
        gfx.round_rect(8, 52, W - 16, 26, 6, PANEL)
        shown = ("•" * len(text) if secret and not show_secret else text)[-34:]
        gfx.text(shown + "_", 14, 57, CYAN)
        keys = _PAGES[page]
        ky = 86
        for r in range(5):
            if r < 4:
                for c, ch in enumerate(keys[r]):
                    x = 6 + c * 31
                    y = ky + r * 26
                    on = (r, c) == (row, col)
                    gfx.round_rect(x, y, 28, 23, 5, ACCENT if on else PANEL2)
                    gfx.text(ch, x + 14, y + 4, WHITE if on else TEXT, align=1)
            else:
                x = 6
                for c, label in enumerate(_SPECIAL):
                    bw = 92 if label == "spazio" else 52
                    on = (r, c) == (row, col)
                    gfx.round_rect(x, ky + 4 * 26, bw, 23, 5, ACCENT if on else PANEL)
                    gfx.text(label, x + bw // 2, ky + 4 * 26 + 4, WHITE if on else DIM, align=1)
                    x += bw + 4
        footer([("A", "Scrivi"), ("A tieni", "Canc"), ("►", "OK")])
        sys.show()
        ev = await sys.event()
        if ev is None:
            continue
        k, kind = B.key(ev), B.kind(ev)
        if kind == sys.HOME:
            return None
        if (k == B.A and kind == B.LONG) or (k == B.B and kind in (B.PRESS, B.REPEAT)):
            if text:
                text = text[:-1]
                continue
            return None
        if k == B.A and kind == B.CLICK:
            kind = B.PRESS          # typing happens on the click below
        elif k == B.A or kind not in (B.PRESS, B.REPEAT):
            continue
        ncols = len(_SPECIAL) if row == 4 else 10
        if k == B.UP:
            row = (row - 1) % 5
            col = min(col, (len(_SPECIAL) if row == 4 else 10) - 1)
        elif k == B.DOWN:
            row = (row + 1) % 5
            col = min(col, (len(_SPECIAL) if row == 4 else 10) - 1)
        elif k == B.LEFT:
            col = (col - 1) % ncols
        elif k == B.RIGHT:
            col = (col + 1) % ncols
        elif k == B.PLAY:
            return text
        elif k == B.NEXT and secret:
            show_secret = not show_secret
        elif k == B.A:
            if row < 4:
                if len(text) < max_len:
                    text += keys[row][col]
            else:
                label = _SPECIAL[col]
                if label == "aA":
                    page = 1 if page == 0 else 0
                elif label == "#!":
                    page = 2 if page != 2 else 0
                elif label == "spazio" and len(text) < max_len:
                    text += " "
                elif label == "canc":
                    text = text[:-1]
                elif label == "OK":
                    return text
