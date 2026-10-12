"""Traboda OS core: brings the hardware up, runs the background services and the apps.

One System object is handed to every app. Apps are modules in traboda.apps with
TITLE, ICON and `async def main(sys)`; they read keys with `await sys.event()` and push
frames with sys.show(). Global keys, handled here so every app gets them for free:
  B held          -> home (apps see a HOME event and return)
  play held       -> quick panel (volume, brightness, LEDs, standby), then REDRAW
  play/prev/next  -> music transport whenever a track is loaded, unless the app sets
                     MEDIA_KEYS = True to use them itself (games)
"""

import asyncio
import gc
import sys
import time

from . import board, settings, tz, ui
from . import buttons as B
from . import gfx

HOME = 5
REDRAW = 6


class System:
    PRESS = B.PRESS
    RELEASE = B.RELEASE
    REPEAT = B.REPEAT
    LONG = B.LONG
    CLICK = B.CLICK
    HOME = HOME
    REDRAW = REDRAW

    def __init__(self):
        self.errors = []
        settings.load()
        tz.zone = settings.get("tz")
        self.i2c = board.i2c()
        from .aw9523 import AW9523
        from . import power
        from .display import Display
        self.ex = AW9523(self.i2c)
        power.init(self.ex)
        self.power = power
        self.display = Display(board.spi(), self.ex)
        gfx.attach(self.display.fb)
        self.buttons = B.Buttons(self.ex)
        self.leds = self._service("LED", self._make_leds)
        from .audio import Audio
        from .player import Player
        self.audio = Audio(self.i2c)
        self.audio.volume = settings.get("volume")
        self.audio.speaker_enabled = settings.get("speaker")
        self.player = Player(self.audio)
        self.battery = None
        self.charging = False
        try:
            self.battery = power.battery_percent()
            self.charging = power.usb_connected()
        except Exception as e:  # noqa: BLE001
            self.errors.append("battery: %s" % e)
        self.screen_on = True
        self.claim_media = False
        self.app_name = None
        self._requested_app = None
        self._held_long = 0          # keys whose LONG fired, so their RELEASE is not a tap
        self._swallow = 0            # keys pressed to wake the screen
        self._redraw = False
        self._quick = False
        self._toast = None
        self._last_status = 0
        self._started = time.ticks_ms()
        from .hostlink import HostLink
        self.hostlink = HostLink(self)
        self.sd_mounted = False

    def _service(self, name, make):
        try:
            return make()
        except Exception as e:  # noqa: BLE001 - one broken part must not stop the OS
            self.errors.append("%s: %s" % (name, e))
            sys.print_exception(e)
            return None

    def _make_leds(self):
        from .leds import Leds
        leds = Leds()
        leds.level = settings.get("led_brightness") / 100
        leds.color = tuple(settings.get("led_color"))
        if settings.get("leds_on"):
            leds.set_effect(settings.get("led_effect"))
        return leds

    # -- small helpers for apps -------------------------------------------------------------

    def show(self, y0=0, y1=240):
        self.display.show(y0, y1)

    def clock_text(self):
        if not tz.clock_valid():
            return "--:--"
        t = tz.now()
        return "%02d:%02d" % (t[3], t[4])

    def wifi_connected(self):
        from . import net
        return net.connected()

    def is_back(self, ev):
        """B pressed, A held, or HOME. A-held keeps every badge usable: on some units the
        B and rewind switches never close (see docs/hardware.md)."""
        k, kind = B.key(ev), B.kind(ev)
        return kind == HOME or (k == B.B and kind == B.PRESS) or (k == B.A and kind == B.LONG)

    def set_utc(self, epoch):
        """epoch: Unix seconds (1970). MicroPython on the ESP32 counts from 2000."""
        import machine
        if time.gmtime(0)[0] == 2000:
            epoch -= 946684800
        t = time.gmtime(epoch)
        machine.RTC().datetime((t[0], t[1], t[2], t[6] + 1, t[3], t[4], t[5], 0))

    def notify(self, text, color=(45, 226, 230)):
        self._toast = (text, time.ticks_add(time.ticks_ms(), 2500))
        if self.leds:
            self.leds.flash(color, 900)
        if settings.get("clicks"):
            try:
                self.audio.melody(((1568, 60), (2093, 90)), 0.2)
            except Exception:  # noqa: BLE001 - sound is a nicety
                pass
        self._redraw = True

    def request_app(self, name):
        self._requested_app = name

    def pending_app(self):
        return self._requested_app

    def inject_key(self, k, hold_ms=0):
        q = self.buttons.queue
        q.append(B.PRESS << 4 | k)
        if hold_ms >= B.LONG_AFTER:
            q.append(B.LONG << 4 | k)
        q.append(B.RELEASE << 4 | k)
        self.buttons.last_activity = time.ticks_ms()

    async def sleep_ms(self, ms, interruptible=False):
        """Sleeps; with interruptible, returns early (True) on a key press."""
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < ms:
            if interruptible and any(B.kind(e) == B.PRESS for e in self.buttons.queue):
                return True
            await asyncio.sleep_ms(15)
        return False

    # -- events -----------------------------------------------------------------------------

    async def event(self, timeout_ms=None):
        """Next key event (int, see buttons), HOME/REDRAW, or None after timeout_ms."""
        t0 = time.ticks_ms()
        while True:
            if self._quick:
                self._quick = False
                await self.quick_panel()
                return REDRAW << 4
            if self._redraw:
                self._redraw = False
                return REDRAW << 4
            ev = self._next_event()
            if ev is not None:
                return ev
            if self._requested_app:
                return HOME << 4 | B.B
            if timeout_ms is not None and time.ticks_diff(time.ticks_ms(), t0) >= timeout_ms:
                return None
            await asyncio.sleep_ms(10)

    def _next_event(self):
        q = self.buttons.queue
        while q:
            ev = q.pop(0)
            k, kind = B.key(ev), B.kind(ev)
            m = 1 << k
            if self._swallow & m:
                if kind == B.RELEASE:
                    self._swallow &= ~m
                continue
            if kind == B.LONG:
                self._held_long |= m
                if k == B.B:
                    return HOME << 4 | B.B
                if k == B.PLAY and not self.claim_media:
                    self._quick = True
                    return None
            if kind == B.RELEASE:
                was_long = self._held_long & m
                self._held_long &= ~m
                if not self.claim_media and k in (B.PLAY, B.PREV, B.NEXT) and not was_long:
                    if self._media_tap(k):
                        continue
                if not was_long:
                    q.insert(0, B.CLICK << 4 | k)
            if not self.claim_media and k in (B.PLAY, B.PREV, B.NEXT) and self.player.loaded \
                    and kind in (B.PRESS, B.REPEAT, B.LONG):
                continue        # the RELEASE above acts on it
            return ev
        return None

    def _media_tap(self, k):
        if not self.player.loaded:
            return False
        if k == B.PLAY:
            self.player.play_pause()
        elif k == B.NEXT:
            self.player.next()
        else:
            self.player.prev()
        self._redraw = True
        return True

    # -- services -------------------------------------------------------------------------

    async def _input_task(self):
        sleep_after = settings.get("sleep_after")
        while True:
            try:
                active = self.buttons.scan()
                if not self.screen_on and active:
                    self._swallow |= self.buttons.state
                    self.buttons.queue.clear()
                    self.wake_screen()
                elif self.screen_on and sleep_after:
                    idle = time.ticks_diff(time.ticks_ms(), self.buttons.last_activity)
                    if idle > sleep_after * 1000:
                        self.screen_off()
                for cmd in self.hostlink.pump():
                    self.hostlink.handle(cmd)
            except OSError as e:
                self.errors.append("input: %s" % e)
            await asyncio.sleep_ms(10)

    def screen_off(self):
        self.display.sleep()
        self.screen_on = False

    def wake_screen(self):
        self.screen_on = True
        self.display.wake()
        self.buttons.last_activity = time.ticks_ms()

    async def _led_task(self):
        while True:
            leds = self.leds
            if leds:
                if leds.effect == "vu":
                    leds.vu = self.audio.levels
                try:
                    leds.tick()
                except Exception as e:  # noqa: BLE001
                    self.errors.append("leds: %s" % e)
            await asyncio.sleep_ms(33)

    async def _status_task(self):
        n = 0
        while True:
            try:
                self.player.tick()
                if n % 60 == 0:
                    self.battery = self.power.battery_percent()
                if n % 10 == 0:
                    self.charging = self.power.usb_connected()
                if self._toast and time.ticks_diff(self._toast[1], time.ticks_ms()) <= 0:
                    self._toast = None
                    self._redraw = True
            except Exception as e:  # noqa: BLE001
                self.errors.append("status: %s" % e)
            n += 1
            await asyncio.sleep_ms(500)

    async def _wifi_task(self):
        from . import net
        if not settings.get("wifi_auto") or not settings.get("wifi"):
            return
        while True:
            if not net.connected():
                if await net.auto_connect():
                    net.sync_time()
                    self._redraw = True
            elif time.time() - net.last_sync > 6 * 3600:
                net.sync_time()
            await asyncio.sleep(60)

    def mount_sd(self):
        if self.sd_mounted:
            return True
        if not self.power.sd_present():
            return False
        try:
            import machine
            import os
            from machine import Pin
            Pin(board.SD_D3, Pin.OUT, value=1)
            card = machine.SDCard(slot=1, width=1, sck=board.SD_CLK, cmd=board.SD_CMD,
                                  data=(board.SD_D0,))
            from . import paths
            os.mount(card, paths.SD)
            self.sd_mounted = True
        except Exception as e:  # noqa: BLE001 - no card, or not FAT
            self.errors.append("sd: %s" % e)
        return self.sd_mounted

    # -- quick panel ----------------------------------------------------------------------

    async def quick_panel(self):
        from .leds import EFFECTS
        items = [
            ui.Item("Volume", self.audio.volume, "music", "slider", step=5),
            ui.Item("Luminosità", self.display.brightness, "lights", "slider", step=10, lo=5),
            ui.Item("LED", settings.get("leds_on"), "lights", "toggle"),
            ui.Item("Effetto LED", settings.get("led_effect"), "lights", "choice",
                    choices=list(EFFECTS[1:])),
            ui.Item("Altoparlante", self.audio.speaker_enabled, "music", "toggle"),
            ui.Item("Standby", None, "power", tag="standby"),
        ]

        def changed(it):
            if it.label == "Volume":
                self.audio.set_volume(it.value)
                settings.set("volume", it.value, False)
            elif it.label == "Luminosità":
                self.display.set_brightness(it.value)
                settings.set("brightness", it.value, False)
            elif it.label == "LED" and self.leds:
                settings.set("leds_on", it.value, False)
                self.leds.set_effect(settings.get("led_effect") if it.value else "off")
            elif it.label == "Effetto LED" and self.leds:
                settings.set("led_effect", it.value, False)
                settings.set("leds_on", True, False)
                self.leds.set_effect(it.value)
            elif it.label == "Altoparlante":
                self.audio.set_speaker(it.value)
                settings.set("speaker", it.value, False)

        claim, self.claim_media = self.claim_media, False
        try:
            choice = await ui.menu(self, "Pannello rapido", items, icon="settings",
                                   on_change=changed, accent=ui.CYAN)
        finally:
            self.claim_media = claim
            settings.save()
        if choice and choice.tag == "standby":
            await self.standby()

    async def standby(self):
        gfx.clear(ui.BG)
        gfx.text("A dopo!", 160, 100, ui.TEXT, "title", align=1)
        gfx.text("premi un tasto per riaccendere", 160, 132, ui.DIM, align=1)
        self.show()
        await asyncio.sleep_ms(900)
        settings.save()
        self.power.standby(self.display, self.leds, self.audio)

    # -- apps -------------------------------------------------------------------------------

    async def run_app(self, name):
        modname = "traboda.apps." + name
        self.app_name = name
        mod = None
        try:
            mod = __import__(modname, None, None, ("main",))
            self.claim_media = getattr(mod, "MEDIA_KEYS", False)
            self.buttons.clear()
            await mod.main(self)
        except Exception as e:  # noqa: BLE001 - report, then back to the launcher
            sys.print_exception(e)
            self.claim_media = False
            await ui.dialog(self, "Errore in %s" % name, "%s: %s" % (type(e).__name__, e))
        finally:
            self.claim_media = False
            self.app_name = None
            if self.leds:
                self.leds.progress = None
            if name != "home" and modname in sys.modules:
                del sys.modules[modname]
            gc.collect()

    async def run(self):
        self.display.set_brightness(settings.get("brightness"))
        asyncio.create_task(self._input_task())
        asyncio.create_task(self._led_task())
        asyncio.create_task(self._status_task())
        asyncio.create_task(self._wifi_task())
        self.mount_sd()
        while True:
            name = self._requested_app or "home"
            self._requested_app = None
            await self.run_app(name)
