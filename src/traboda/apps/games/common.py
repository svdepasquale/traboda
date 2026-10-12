"""What every game shares: frame pacing, event draining, HUD, sounds, LED effects,
pause and game-over screens with best scores."""

import asyncio
import time

from ... import buttons as B
from ... import gfx, settings, ui

HUD_H = 18

_SFX = {
    "move": ((1800, 8),),
    "rotate": ((1300, 12),),
    "eat": ((880, 30), (1320, 40)),
    "line": ((660, 40), (880, 40), (1320, 70)),
    "hit": ((440, 25),),
    "bounce": ((1046, 18),),
    "lose": ((392, 120), (330, 120), (262, 260)),
    "win": ((523, 90), (659, 90), (784, 90), (1047, 220)),
    "start": ((784, 60), (1047, 90)),
    "tick": ((2200, 6),),
}


def sounds_on():
    return settings.get("game_sounds", True)


def sfx(sys, name):
    if sounds_on() and name in _SFX:
        try:
            sys.audio.melody(_SFX[name], 0.25)
        except Exception:  # noqa: BLE001 - never let a beep stop a game
            pass


def drain(sys):
    """Every pending event, already filtered by the core (HOME, REDRAW...)."""
    out = []
    while True:
        ev = sys.poll_event()
        if ev is None:
            return out
        out.append(ev)


class Ticker:
    """Fixed-rate loop: `await tick.wait()` at the end of each frame."""

    def __init__(self, fps):
        self.period = 1000 // fps
        self.last = time.ticks_ms()

    async def wait(self):
        elapsed = time.ticks_diff(time.ticks_ms(), self.last)
        await asyncio.sleep_ms(max(1, self.period - elapsed))
        self.last = time.ticks_ms()


def hud(title, score, best=None, extra=None, color=ui.YELLOW):
    """Slim top bar: title left, score centre, best right. Push rows 0..HUD_H."""
    gfx.fill_rect(0, 0, 320, HUD_H, ui.PANEL)
    gfx.hline(0, HUD_H - 1, 320, ui.LINE)
    gfx.text(title, 6, 1, ui.DIM)
    gfx.text(str(score), 160, 1, color, align=1)
    right = extra if extra is not None else ("record %d" % best if best is not None else "")
    gfx.text(right, 314, 1, ui.DIM, align=-1)


def leds_flash(sys, color, ms=400):
    if sys.leds:
        sys.leds.flash(color, ms, 100)


def leds_frame(sys, frame):
    """Draw a 22-LED frame (positions row-major, top row first)."""
    if sys.leds:
        if sys.leds.effect != "custom":
            sys.leds.set_effect("custom")
        sys.leds.frame = frame


async def countdown(sys, redraw):
    """3, 2, 1 over the game screen; redraw() repaints the field under the digits."""
    for n in (3, 2, 1):
        redraw()
        gfx.round_rect(130, 90, 60, 60, 12, ui.PANEL)
        gfx.text(str(n), 160, 104, ui.YELLOW, "large", align=1)
        sys.show()
        sfx(sys, "tick")
        await asyncio.sleep_ms(450)
    redraw()
    sys.show()


async def pause_menu(sys, title):
    """Returns "resume", "restart" or "quit"."""
    choice = await ui.dialog(sys, title + " - pausa", "▶ riprendi la partita",
                             ("Riprendi", "Ricomincia", "Esci"), accent=ui.YELLOW)
    return ("resume", "restart", "quit")[choice] if choice is not None else "resume"


async def game_over(sys, game_id, title, score, won=False):
    """Records the best score, celebrates a record. Returns "restart" or "quit"."""
    best_before = settings.score(game_id)
    best = settings.score(game_id, score)
    record = score > best_before and score > 0
    if record:
        leds_flash(sys, (255, 214, 10), 1200)
        sfx(sys, "win")
    else:
        leds_flash(sys, (255, 40, 40) if not won else (61, 220, 132), 600)
        sfx(sys, "win" if won else "lose")
    msg = "Punti: %d\nRecord: %d%s" % (score, best, "\nNUOVO RECORD!" if record else "")
    choice = await ui.dialog(sys, ("Hai vinto!" if won else "Game over") + " - " + title, msg,
                             ("Ancora", "Esci"), accent=ui.YELLOW if record else ui.ACCENT)
    return "restart" if choice == 0 else "quit"


def wants_pause(ev):
    """Play pressed: games open the pause menu with it."""
    return B.key(ev) == B.PLAY and B.kind(ev) == B.PRESS
