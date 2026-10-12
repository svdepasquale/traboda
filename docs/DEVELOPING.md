# Developing for Traboda OS

Traboda OS is MicroPython 1.29 code in `src/traboda/`, frozen into the firmware and
also runnable headless on the MicroPython unix port (`sim/`). This page is the contract
every app is written against.

## Hardware in one paragraph

ESP32-S3 (240 MHz, 8 MB PSRAM: RAM is not scarce), 320x240 ILI9341 (landscape, RGB565),
22 RGB LEDs in two rows of 11 above the screen, ES8156 DAC to a mono speaker and a stereo
3.5 mm jack, Ci522 (MFRC522-compatible) 13.56 MHz NFC reader on the display's SPI bus,
Wi-Fi + BLE, microSD (optional, often absent), LiPo with USB charging.

Keys: a D-pad, **A** (right, upper), **B** (right, lower), and three transport keys under
the screen: **prev ⏪**, **play ▶**, **next ⏩**. On some badges B and prev never register
(their switches do not close): **every app must be fully usable with UP DOWN LEFT RIGHT,
A, play and next only**. B and prev are extras.

## The app contract

An app is a module `src/traboda/apps/<name>.py`:

```python
TITLE = "Orologio"        # shown in headers
ICON = "clock"            # an icons.ART name (or register your own, see below)
MEDIA_KEYS = False        # True: the app receives play/prev/next raw (games do this)

async def main(sys):      # return to go back to the launcher
    ...
```

The launcher registry is `apps/__init__.py` (APPS). Games live in the `apps/games/`
package (the hub is `apps/games/__init__.py`; each game is `apps/games/<game>.py` with
the same contract plus `GAME_ID` used for high scores).

`sys` is the `traboda.core.System` instance. Keep all state in locals or module globals;
the module is unloaded from `sys.modules` when the app returns.

## Keys and events

```python
from traboda import buttons as B
ev = await sys.event(timeout_ms=None)   # int, or None on timeout
k, kind = B.key(ev), B.kind(ev)
```

* keys: `B.UP B.DOWN B.LEFT B.RIGHT B.A B.B B.PLAY B.PREV B.NEXT`
* kinds: `B.PRESS`, `B.RELEASE`, `B.REPEAT` (D-pad only, while held), `B.LONG` (held
  0.7 s, once), `B.CLICK` (released before LONG: use it for "select"), `sys.HOME`
  (leave now), `sys.REDRAW` (something drew over you: redraw everything).
* `sys.is_back(ev)` is True for B pressed, **A held (LONG)**, or HOME. Use it everywhere
  for "back". Because A-held means back, **select/confirm must act on `B.CLICK` of A**,
  not on PRESS. D-pad movement acts on PRESS and REPEAT.
* Games set `MEDIA_KEYS = True` and act on PRESS for responsiveness; their back is a
  pause menu on play (or A held when paused). Never rely on B or prev alone.
* With `MEDIA_KEYS = False`, play/prev/next control music playback whenever a track is
  loaded (you do not see them), and holding play opens the quick panel (you then get
  REDRAW). When no track is loaded you do receive their CLICKs.
* `sys.buttons.held(B.LEFT)` reads the live state (for games).
* `await sys.sleep_ms(ms, interruptible=True)` sleeps, returning True early on a press.

## Drawing

The screen is a 320x240 framebuffer; nothing appears until you push it:

```python
from traboda import gfx, ui, icons
from traboda.display import rgb
y = ui.header(sys, "Titolo", "clock")   # clears, status bar, title band; returns content y
gfx.text("ciao", 10, y, ui.TEXT)        # fonts: "small" 6x12, "text" 8x16 (default),
                                        # "title" 12x24, "large" 16x32, "huge" 32x64 digits
gfx.text("al centro", 160, y, ui.CYAN, "title", align=1)   # align -1 right, 0 left, 1 centre
ui.footer([("A", "Apri"), ("A tieni", "Indietro")])
sys.show()                              # push all; sys.show(y0, y1) pushes rows y0..y1-1
```

* Colours: `ui.BG PANEL PANEL2 LINE ACCENT ACCENT_DARK CYAN YELLOW GREEN ORANGE RED TEXT
  DIM BLACK WHITE`, or `rgb(r, g, b)` (byte-swapped RGB565; never pass raw RGB565).
* Layout: status bar 0-17 (`ui.STATUS_H`), footer from `ui.FOOTER_Y` = 222.
* gfx: `clear fill_rect rect hline vline line circle(x,y,r,c,fill) round_rect(x,y,w,h,r,c,fill)
  gradient_v(x,y,w,h,(r,g,b),(r,g,b)) bar(x,y,w,h,fraction,fg,bg,r) text text_scaled wrap
  ellipsize`, and `gfx.fb` is the raw `framebuf.FrameBuffer` (blit, poly, ellipse...).
* `gfx.text` handles UTF-8 (Italian accents) and the symbols ▲▼◄►▶◀✓✗♪♫←↑→↓ in "text".
* Icons: 16x16 pixel art, `icons.draw(gfx.fb, "name", x, y, scale)` (scale 1 = 16 px,
  2 = 32 px). New icons: `icons.register("name", rows)` at import time, 16 strings of 16
  palette letters (see the icons.py docstring).
* A full-screen push takes ~33 ms (a band of N rows ~N x 0.14 ms). When animating,
  push only what changed: `sys.show(y0, y1)` for a full-width band, or
  `sys.show_rect(x, y, w, h)` for a rectangle (best for sprites, narrow columns, or two
  changes far apart: push two small rects, not one tall band).

## Widgets (`traboda.ui`)

* `await ui.menu(sys, title, items, icon=..., on_change=fn, accent=...)` -> chosen
  `ui.Item` or None. `ui.Item(label, value=None, icon=None, kind=None|"toggle"|"slider"|
  "choice", choices=[...], step=10, lo=0, hi=100, tag=..., detail=...)`. Sliders,
  toggles and choices change with left/right; on_change(item) fires after each change.
* `await ui.dialog(sys, title, message, options=("OK",))` -> index or None.
* `await ui.keyboard(sys, title, text="", secret=False)` -> str or None.
* `await ui.toast(sys, msg, ms=1200)`; `ui.toast_draw(msg)` draws without waiting.
* `ui.draw_list(items, sel, top, y0, rows)` if you build your own list screen.

## Services on `sys`

* `sys.audio`: `tone(freq_hz, ms, level=0.3)`, `melody([(freq, ms), ...])`, `click()`,
  `set_volume(0..100)`, `.volume`, `play(path)` (16-bit PCM WAV), `toggle()`, `stop()`,
  `.playing .paused .elapsed .duration .levels (l, r) .error`.
* `sys.player`: the music queue: `load(paths, start)`, `play_pause()`, `next()`,
  `prev()`, `.queue .index .current .loaded .shuffle .repeat`.
* `sys.leds` (may be None if the LEDs failed): `set_effect(name, color=None)` with names
  in `leds.EFFECTS`, `.color`, `.level` (0..1), `.speed`, `flash(color, ms)`,
  `.progress` (0..1 fills the strip; set None to release). To draw the LEDs yourself:
  `sys.leds.set_effect("custom")`, then assign `sys.leds.frame` = a list of 22 (r, g, b)
  by position (row 0 = top, left to right; index = row * 11 + col); the engine shows it
  on its next tick (30 Hz) with the user's brightness. Restore the user's effect when you
  leave: `sys.leds.set_effect(settings.get("led_effect") if settings.get("leds_on") else
  "off")`.
* `sys.notify(text)`: toast + LED flash + chime.
* `sys.battery` (percent or None), `sys.charging`, `sys.wifi_connected()`,
  `sys.clock_text()`, `sys.power` (module: `battery_volts()`, `sd_present()`,
  `standby()`), `await sys.standby()`.
* `traboda.settings`: `get(key, default)`, `set(key, value, save_now=True)`,
  `score(game_id, value=None)` (best score; records a new best).
* `traboda.net`: `connected() ip() rssi() scan()` (blocking ~2.5 s: draw "searching"
  first), `await connect(ssid, pw)`, `remember(ssid, pw)`, `forget(ssid)`,
  `sync_time()`, `get_json(url)` (blocking HTTP GET).
* `traboda.tz`: `now()` local time tuple (y, m, d, hh, mm, ss, weekday, yearday),
  `clock_valid()`, `DAYS MONTHS DAYS_LONG MONTHS_LONG` (Italian).
* `traboda.paths`: `ROOT` (internal flash), `SD` (card), `data(name)`, `sd(name)`. Never
  hard-code "/" paths: the simulator sandboxes them.

## MicroPython rules

* No `@micropython.native`/`viper` (the unix port on the Mac has no native emitter).
* No `(a, *b)` / `[*x]` unpacking displays, no dataclasses, typing, `match`, `re`
  beyond basics. f-strings work but keep them simple; `%` formatting is safe.
* Avoid allocating in per-frame loops (reuse lists/bytearrays). Integer maths where it
  matters. `random.randrange/random()`, `math`, `struct`, `json`, `asyncio` exist.
* Long blocking work (HTTP, Wi-Fi scan) freezes the UI: draw a "loading" state, push
  it, then do the work.
* UI text is Italian; code, comments and docstrings are English. Match the existing
  style: short module docstring, few comments, no dead code.

## Simulator

```sh
micropython sim/run.py OUT "app:clock,wait:800,snap:clock,key:right,key:A,wait:300,snap:timer,hold:A,wait:400,snap:back"
python3 sim/topng.py OUT        # OUT/*.png at 2x, LED strip on top: look at them
```

Steps: `app:NAME`, `wait:MS`, `key:NAME` (tap: PRESS, RELEASE, CLICK), `hold:NAME`
(LONG), `down:NAME`/`up:NAME` (through the simulated expander), `snap:LABEL`,
`battery:VOLTS`. Fakes live in `sim/fake/` (Wi-Fi with five networks, BLE with five
advertisers, HTTP answered from `sim/fixtures/`, SD card with three short WAVs). A
Python exception in your app shows as an "Errore in ..." dialog in the snapshot and in
the console. A new fake for your own hardware goes in a new file under `sim/fake/`.

On the badge: `tools/dev.py sync` (then `tools/dev.py run`), `tools/dev.py snap x.png`,
`tools/dev.py key right`.
