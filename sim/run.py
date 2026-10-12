"""Runs Traboda OS headless on the MicroPython unix port and takes screenshots.

usage: micropython sim/run.py OUTDIR "STEPS"
STEPS, comma separated:
  app:NAME          open an app (as if picked in the launcher)
  wait:MS           let the OS run
  key:NAME          tap a key (up down left right A B play prev next) -> PRESS, RELEASE, CLICK
  hold:NAME         hold a key past the long-press time (A held = back)
  down:NAME/up:NAME press / release a key through the simulated expander (real scan path)
  snap:LABEL        save OUTDIR/LABEL.raw (framebuffer) and LABEL.leds
  battery:VOLTS     set the simulated battery voltage
Then: python3 sim/topng.py OUTDIR  ->  OUTDIR/LABEL.png (2x, with the LED strip)
"""

import sys

ROOT = sys.argv[0].rsplit("/", 2)[0] if "/" in sys.argv[0] else "."
if ROOT.endswith("/sim") or ROOT == "sim":
    ROOT = ROOT[:-3].rstrip("/") or "."
sys.path.insert(0, ROOT + "/src")
sys.path.insert(0, ROOT + "/sim/fake")

import os  # noqa: E402

import simpaths  # noqa: E402
import simstate  # noqa: E402

simpaths.FIXTURES = ROOT + "/sim/fixtures"
OUT = sys.argv[1]
STEPS = sys.argv[2] if len(sys.argv) > 2 else "wait:500,snap:home"


def mkdirs(path):
    parts = path.split("/")
    for i in range(1, len(parts) + 1):
        p = "/".join(parts[:i])
        if p:
            try:
                os.mkdir(p)
            except OSError:
                pass


mkdirs(OUT)
SANDBOX = OUT + "/fs"
mkdirs(SANDBOX + "/sd/music")

from traboda import paths  # noqa: E402

paths.ROOT = SANDBOX
paths.SD = SANDBOX + "/sd"


def make_wav(path, seconds=3, rate=22050):
    import struct
    n = rate * seconds
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + n * 2) + b"WAVEfmt ")
        f.write(struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16))
        f.write(b"data" + struct.pack("<I", n * 2))
        chunk = bytearray(2 * 441)
        for i in range(441):
            struct.pack_into("<h", chunk, 2 * i, 8000 if (i // 25) % 2 else -8000)
        for _ in range(n // 441):
            f.write(chunk)


for name in ("Daft_Punk-Around_the_World.wav", "Ennio_Morricone-Il_Buono.wav", "Chiptune_Demo.wav"):
    p = SANDBOX + "/sd/music/" + name
    try:
        os.stat(p)
    except OSError:
        make_wav(p)

import asyncio  # noqa: E402

from traboda import buttons  # noqa: E402
from traboda.core import System  # noqa: E402


def snap(system, label):
    with open(OUT + "/" + label + ".raw", "wb") as f:
        f.write(system.display.buf)
    with open(OUT + "/" + label + ".leds", "w") as f:
        f.write(repr([tuple(c) for c in simstate.leds]))
    print("snap", label)


async def scenario(system):
    await asyncio.sleep_ms(300)
    for step in STEPS.split(","):
        step = step.strip()
        if not step:
            continue
        cmd, _, arg = step.partition(":")
        if cmd == "wait":
            await asyncio.sleep_ms(int(arg))
        elif cmd == "app":
            system.request_app(arg)
            await asyncio.sleep_ms(400)
        elif cmd == "key":
            system.inject_key(buttons.NAMES.index(arg))
            await asyncio.sleep_ms(120)
        elif cmd == "hold":
            system.inject_key(buttons.NAMES.index(arg), 900)
            await asyncio.sleep_ms(150)
        elif cmd == "down":
            simstate.press(buttons.NAMES.index(arg))
            await asyncio.sleep_ms(30)
        elif cmd == "up":
            simstate.release(buttons.NAMES.index(arg))
            await asyncio.sleep_ms(30)
        elif cmd == "snap":
            await asyncio.sleep_ms(80)
            snap(system, arg)
        elif cmd == "battery":
            simstate.battery_volts = float(arg)
        else:
            print("unknown step", step)
    if system.errors:
        print("errors:", system.errors)


async def main():
    system = System()
    task = asyncio.create_task(system.run())
    await scenario(system)
    task.cancel()


asyncio.run(main())
