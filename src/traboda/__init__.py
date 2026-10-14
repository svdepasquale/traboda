"""Traboda OS: a companion and console for the RomHack Camp 2026 badge.

main.py calls traboda.main(). Hold B while powering on (or resetting) to skip the OS and
stay at the MicroPython REPL; Ctrl-C over USB stops a running OS the same way.
"""

VERSION = "0.1.0"


def _splash(system):
    import time
    from . import gfx, icons, settings, ui
    gfx.clear(ui.BG)
    gfx.gradient_v(0, 0, 320, 240, (30, 8, 28), (10, 12, 24))
    icons.draw(gfx.fb, "cassette", 160 - 32, 50, 4)
    gfx.text("TRABODA", 160, 128, ui.ACCENT, "large", align=1)
    gfx.text("RomHack Camp 2026 badge", 160, 166, ui.DIM, align=1)
    gfx.text("v" + VERSION, 160, 214, ui.LINE, "small", align=1)
    system.show()
    system.display.set_brightness(settings.get("brightness"))
    leds = system.leds
    if leds:
        for i in range(12):
            from .leds import hsv
            leds.frame = [hsv(i / 12 + p / 22) if p % 11 <= i else (0, 0, 0) for p in range(22)]
            leds._write()
            time.sleep_ms(35)


def main():
    import asyncio
    import sys
    from . import buttons
    from .core import System

    system = System()
    system.buttons.scan()           # held() reads the state a scan leaves; none has run yet
    if system.buttons.held(buttons.B):
        from . import gfx, ui
        gfx.clear(ui.BG)
        gfx.text("Modalità sicura", 160, 90, ui.YELLOW, "title", align=1)
        gfx.text("Traboda OS non avviato: REPL via USB", 160, 126, ui.DIM, align=1)
        system.show()
        system.display.set_brightness(60)
        print("Traboda: safe mode, OS not started")
        return
    _splash(system)
    try:
        asyncio.run(system.run())
    except KeyboardInterrupt:
        print("Traboda: stopped, back to the REPL")
    finally:
        try:
            if system.leds:
                system.leds.off(now=True)
            system.audio.close()
        except Exception as e:  # noqa: BLE001
            sys.print_exception(e)
        asyncio.new_event_loop()
