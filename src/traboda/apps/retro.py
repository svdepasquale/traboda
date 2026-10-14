"""Retro-Go: the console firmware kept in the badge's other app partitions. What is
installed, where the ROMs go, its keys on this badge, and the reboot into it."""

from .. import buttons as B
from .. import gfx, icons, settings, ui

TITLE = "Retro-Go"
ICON = "retro"
MEDIA_KEYS = False

# (partition label, name, what it runs)
PARTS = (
    ("launcher", "Launcher", "Il menu: scegli il gioco e l'emulatore"),
    ("retro-core", "Emulatori",
     "NES, SNES, Game Boy/Color, Lynx, PC Engine, Master System, Game Gear, Coleco, Game&Watch"),
    ("prboom-go", "Doom", "PrBoom: Doom e i WAD in /roms/doom"),
)
ROMS = (("nes", "NES"), ("snes", "SNES"), ("gb", "Game Boy"), ("gbc", "GB Color"),
        ("sms", "Master Sys"), ("gg", "Game Gear"), ("col", "Coleco"), ("pce", "PC Engine"),
        ("lnx", "Lynx"), ("gw", "Game&Watch"), ("doom", "Doom (WAD)"))
# Retro-Go's own map on this badge: MENU is the rewind key, SELECT fast-forward, and
# OPTION is MENU held with A.
KEYS = ((B.GLYPHS[B.A], "A"), (B.GLYPHS[B.B], "B"), (B.GLYPHS[B.PLAY], "START"),
        (B.GLYPHS[B.NEXT], "SELECT"), (B.GLYPHS[B.PREV], "MENU"), (B.GLYPHS[B.PREV] + "+A", "Opzioni"))
TABS = ("Emulatori", "ROM", "Tasti")
TAB_Y = 50
BODY_Y = 78


def _installed():
    """Labels of the app partitions holding a firmware image (it starts with 0xE9): the
    partition table lists Retro-Go's three on every badge, flashed or erased."""
    try:
        import esp32
        found = esp32.Partition.find(esp32.Partition.TYPE_APP)
    except (ImportError, OSError):
        return []
    out = []
    head = bytearray(4)
    for p in found:
        try:
            p.readblocks(0, head)
        except AttributeError:              # the simulator's partitions hold no data
            head[0] = 0xE9
        except OSError:
            continue
        if head[0] == 0xE9:
            out.append(p.info()[4])
    return out


def _sd_present(sys):
    try:
        return sys.sd_mounted or sys.power.sd_present()
    except OSError:
        return False


def _frame(sys, parts):
    ui.header(sys, TITLE, ICON)
    missing = [p[0] for p in PARTS if p[0] not in parts]
    if "launcher" in missing:
        gfx.text("✗ non installato", 310, 22, ui.RED, align=-1)
    elif missing:
        gfx.text("incompleto", 310, 22, ui.ORANGE, align=-1)
    else:
        gfx.text("✓ installato", 310, 22, ui.GREEN, align=-1)
    ui.footer([("◄►", "Sezione"), ("A", "Avvia"), ("B", "Indietro")])


def _tabs(tab):
    gfx.fill_rect(0, TAB_Y, 320, ui.FOOTER_Y - TAB_Y, ui.BG)
    for i, name in enumerate(TABS):
        x = 8 + i * 103
        on = i == tab
        gfx.round_rect(x, TAB_Y, 98, 20, 6, ui.ACCENT if on else ui.PANEL)
        gfx.text(name, x + 49, TAB_Y + 2, ui.WHITE if on else ui.DIM, align=1)


def _emulators(parts):
    y = BODY_Y
    for label, name, what in PARTS:
        lines = gfx.wrap(what, 284, "small")
        h = 22 + 12 * len(lines)
        gfx.round_rect(8, y, 304, h, 6, ui.PANEL)
        x = 16 + gfx.text(name, 16, y + 3, ui.TEXT)
        gfx.text(label, x + 8, y + 6, ui.LINE, "small")
        if label in parts:
            gfx.text("✓ presente", 304, y + 3, ui.GREEN, align=-1)
        else:
            gfx.text("✗ manca", 304, y + 3, ui.RED, align=-1)
        for i, line in enumerate(lines):
            gfx.text(line, 16, y + 20 + 12 * i, ui.DIM, "small")
        y += h + 5


def _roms(sys):
    x = 12 + gfx.text("In ", 12, BODY_Y, ui.TEXT)
    x += gfx.text("/roms/<sistema>/", x, BODY_Y, ui.CYAN)
    gfx.text(" sulla scheda SD", x, BODY_Y, ui.TEXT)
    for i, (folder, name) in enumerate(ROMS):
        cx = 8 + (i % 4) * 77
        cy = BODY_Y + 20 + (i // 4) * 34
        gfx.round_rect(cx, cy, 73, 30, 6, ui.PANEL)
        gfx.text(folder, cx + 6, cy + 1, ui.CYAN)
        gfx.text(name, cx + 6, cy + 17, ui.DIM, "small")
    y = BODY_Y + 20 + 3 * 34 + 4
    if _sd_present(sys):
        gfx.text("✓ Scheda SD inserita", 12, y, ui.GREEN, "small")
    else:
        gfx.text("Senza scheda SD c'è solo un piccolo spazio interno", 10, y, ui.ORANGE, "small")


def _keys():
    for i, (glyph, fn) in enumerate(KEYS):
        x = 12 + (i % 2) * 152
        y = BODY_Y + (i // 2) * 28
        kw = max(22, len(glyph) * 8 + 10)
        gfx.round_rect(x, y, kw, 20, 5, ui.PANEL2)
        gfx.text(glyph, x + kw // 2, y + 2, ui.YELLOW, align=1)
        gfx.text("→ " + fn, x + kw + 8, y + 2, ui.TEXT)
    y = BODY_Y + 86
    gfx.round_rect(8, y, 304, 54, 8, ui.PANEL)
    icons.draw(gfx.fb, "home", 18, y + 19, 1)
    gfx.text("Per tornare a Traboda:", 44, y + 3, ui.DIM)
    gfx.text("B nel menu di Retro-Go e conferma", 44, y + 19, ui.TEXT)
    gfx.text("o spegni e riaccendi il badge", 44, y + 35, ui.TEXT)


def _restore_leds(sys):
    if sys.leds:
        sys.leds.set_effect(settings.get("led_effect") if settings.get("leds_on") else "off")


async def _launch(sys, parts):
    """Confirms, then reboots into Retro-Go. Returns True when the app should leave."""
    if "launcher" not in parts:
        await ui.dialog(sys, TITLE, "Retro-Go non è installato su questo badge: la "
                                    "partizione «launcher» è vuota o manca.")
        return sys.leaving()
    msg = ("Il badge si riavvia in Retro-Go. Per tornare a Traboda: B nel suo menu e "
           "conferma, o spegni e riaccendi.")
    if await ui.dialog(sys, "Avvia Retro-Go", msg, ("Annulla", "Avvia")) != 1:
        return sys.leaving()
    import esp32
    import machine
    try:
        sys.audio.stop()
        settings.save()
        sys.audio.close()
        if sys.leds:
            sys.leds.off(now=True)
    except OSError:
        pass                                # the reboot goes ahead all the same
    gfx.clear(ui.BG)
    icons.draw(gfx.fb, ICON, 144, 76, 2)
    gfx.text("Avvio di Retro-Go…", 160, 122, ui.TEXT, "title", align=1)
    sys.show()
    await sys.sleep_ms(400)
    try:
        esp32.Partition("launcher").set_boot()
        machine.reset()
    except SystemExit:                      # what machine.reset() does in the simulator
        pass
    except Exception as e:  # noqa: BLE001 - set_boot refuses an image that does not verify
        _restore_leds(sys)
        await ui.dialog(sys, TITLE, "La partizione «launcher» non contiene un firmware "
                                    "avviabile (%s)." % e)
        return sys.leaving()
    _restore_leds(sys)
    return True


async def main(sys):
    parts = _installed()
    tab = 0
    full = True
    while True:
        if full:
            _frame(sys, parts)
        _tabs(tab)
        if tab == 0:
            _emulators(parts)
        elif tab == 1:
            _roms(sys)
        else:
            _keys()
        if full:
            sys.show()
            full = False
        else:
            sys.show(TAB_Y, ui.FOOTER_Y)
        while True:
            ev = await sys.event()
            if ev is None:
                continue
            k, kind = B.key(ev), B.kind(ev)
            if kind == sys.REDRAW:
                full = True
                break
            if sys.is_back(ev):
                return
            if k == B.A and kind == B.CLICK:
                if await _launch(sys, parts):
                    return
                full = True
                break
            if kind == B.PRESS and k in (B.LEFT, B.RIGHT):
                tab = (tab + (1 if k == B.RIGHT else -1)) % len(TABS)
                break
