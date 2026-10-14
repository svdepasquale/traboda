"""Games hub: the list of games, best scores, and the launch of the chosen one."""

from ... import buttons as B
from ... import icons, settings, ui

TITLE = "Giochi"
ICON = "games"

# (module, title, icon, one-line pitch)
GAMES = (
    ("snake", "Snake", "snake", "Mangia, cresci, non morderti"),
    ("blocks", "Blocchi", "blocks", "Righe complete, punti doppi"),
    ("breakout", "Mattoncini", "breakout", "Paddle, pallina, muro"),
    ("g2048", "2048", "2048", "Somma le tessere fino a 2048"),
    ("flappy", "Vola!", "flappy", "Un tasto, tanti tubi"),
    ("simon", "Memoria", "simon", "Ripeti la sequenza di luci"),
    ("reaction", "Riflessi", "reaction", "Quanto sei veloce?"),
)


async def main(sys):
    import sys as _sys
    sel = 0
    while True:
        items = []
        for mod, title, icon, pitch in GAMES:
            best = settings.score(mod)
            items.append(ui.Item(title, "%d" % best if best else None, icon, tag=mod, detail=pitch))
        it = await ui.menu(sys, TITLE, items, icon=ICON, sel=sel,
                           hints=[("A", "Gioca"), ("B", "Indietro")], accent=ui.YELLOW)
        if it is None:
            return
        sel = [g[0] for g in GAMES].index(it.tag)
        modname = "traboda.apps.games." + it.tag
        try:
            game = __import__(modname, None, None, ("main",))
        except ImportError as e:
            await ui.dialog(sys, it.label, "Non ancora disponibile (%s)" % e)
            continue
        claim = sys.claim_media
        sys.claim_media = getattr(game, "MEDIA_KEYS", True)
        try:
            await game.main(sys)
        except Exception as e:  # noqa: BLE001 - back to the hub, not to the launcher
            _sys.print_exception(e)
            sys.claim_media = False
            await ui.dialog(sys, "Errore in " + it.label, "%s: %s" % (type(e).__name__, e))
        finally:
            sys.claim_media = claim
            if sys.leds:
                sys.leds.progress = None
                sys.leds.set_effect(settings.get("led_effect") if settings.get("leds_on") else "off")
            _sys.modules.pop(modname, None)
