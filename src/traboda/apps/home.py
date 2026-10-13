"""Home: clock, date, what is playing, and the app grid (4 x 2 per page)."""

from .. import buttons as B
from .. import gfx, icons, settings, tz, ui
from ..apps import APPS

TITLE = "Home"
ICON = "home"

COLS = 4
ROWS = 2
PER_PAGE = COLS * ROWS
TILE_W = 78
TILE_H = 56
GRID_X = 4
GRID_Y = 100

_sel = 0     # kept across visits


def _draw_clock(sys):
    gfx.fill_rect(0, ui.STATUS_H, 320, GRID_Y - ui.STATUS_H - 2, ui.BG)
    if tz.clock_valid():
        t = tz.now()
        hhmm = "%02d:%02d" % (t[3], t[4])
        date = "%s %d %s" % (tz.DAYS_LONG[t[6]], t[2], tz.MONTHS_LONG[t[1] - 1])
    else:
        hhmm = "--:--"
        date = "ora non impostata"
    gfx.text(hhmm, 12, ui.STATUS_H + 6, ui.TEXT, "large")
    gfx.text(date, 12, ui.STATUS_H + 40, ui.DIM)
    name = settings.get("nickname")
    gfx.text(gfx.ellipsize(name, 140), 308, ui.STATUS_H + 8, ui.ACCENT, "text", align=-1)
    p = sys.player
    if p.loaded:
        from ..player import title_of
        mark = "‖ " if sys.audio.paused else "♪ "
        line = mark + title_of(p.current)
        gfx.round_rect(8, ui.STATUS_H + 60, 304, 18, 5, ui.PANEL)
        gfx.text(gfx.ellipsize(line, 290), 14, ui.STATUS_H + 61, ui.CYAN if not sys.audio.paused else ui.DIM)
    else:
        shown = [e for e in sys.errors if not e.startswith("sd:")]   # no card is not a fault
        if shown:
            gfx.text(gfx.ellipsize("! " + shown[-1], 300), 12, ui.STATUS_H + 62, ui.ORANGE, "small")


def _draw_grid(sel):
    page = sel // PER_PAGE
    gfx.fill_rect(0, GRID_Y - 2, 320, ui.FOOTER_Y - GRID_Y + 2, ui.BG)
    for slot in range(PER_PAGE):
        i = page * PER_PAGE + slot
        if i >= len(APPS):
            break
        _mod, title, icon = APPS[i]
        x = GRID_X + (slot % COLS) * TILE_W
        y = GRID_Y + (slot // COLS) * TILE_H
        if i == sel:
            gfx.round_rect(x + 2, y, TILE_W - 4, TILE_H - 2, 8, ui.PANEL2)
            gfx.round_rect(x + 2, y, TILE_W - 4, TILE_H - 2, 8, ui.ACCENT, False)
        icons.draw(gfx.fb, icon, x + (TILE_W - 32) // 2, y + 4)
        gfx.text(gfx.ellipsize(title, TILE_W - 6, "small"), x + TILE_W // 2, y + 40,
                 ui.TEXT if i == sel else ui.DIM, "small", align=1)
    pages = (len(APPS) + PER_PAGE - 1) // PER_PAGE
    if pages > 1:
        x0 = 160 - (pages * 12) // 2
        for p in range(pages):
            gfx.circle(x0 + p * 12 + 6, GRID_Y + 2 * TILE_H + 6, 3, ui.ACCENT if p == page else ui.LINE, True)


async def main(sys):
    global _sel
    sel = _sel
    full = True
    last_minute = -1
    while True:
        if full:
            gfx.clear(ui.BG)
            ui.statusbar(sys)
            _draw_clock(sys)
            _draw_grid(sel)
            ui.footer([("A", "Apri"), ("►", "Musica"), ("► tieni", "Pannello")])
            sys.show()
            full = False
        ev = await sys.event(timeout_ms=1000)
        if ev is None:
            t = tz.now()
            if t[4] != last_minute:
                last_minute = t[4]
                ui.statusbar(sys)
                _draw_clock(sys)
                sys.show(0, GRID_Y)
            continue
        k, kind = B.key(ev), B.kind(ev)
        if kind == sys.REDRAW:
            full = True
            continue
        if kind == sys.HOME:
            if sys.pending_app():
                return
            continue
        if kind == B.CLICK and k in (B.A, B.PLAY):
            name = APPS[sel][0] if k == B.A else "music"
            _sel = sel
            if settings.get("clicks"):
                sys.audio.click()
            sys.request_app(name)
            return
        if kind not in (B.PRESS, B.REPEAT):
            continue
        old = sel
        if k == B.RIGHT:
            sel = (sel + 1) % len(APPS)
        elif k == B.LEFT:
            sel = (sel - 1) % len(APPS)
        elif k == B.DOWN:
            sel = min(len(APPS) - 1, sel + COLS)
        elif k == B.UP:
            sel = max(0, sel - COLS)
        if sel != old:
            _sel = sel
            if old // PER_PAGE != sel // PER_PAGE:
                _draw_grid(sel)
            else:
                _draw_grid(sel)
            sys.show(GRID_Y - 2, ui.FOOTER_Y)
