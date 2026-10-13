#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyserial"]
# ///
"""Sends the Mac's CPU, memory, battery and now playing to the badge's Companion app.

  tools/companion.py                  every 2 s until Ctrl-C (open Companion on the badge)
  tools/companion.py --open           also opens the Companion app on the badge
  tools/companion.py --notify TEXT    one notification on the badge, then exit
  tools/companion.py --dry-run        print the lines instead of sending them (no badge, no
                                      pyserial); they also drive the simulator:
                                      tools/companion.py --dry-run --interval 0.5 |
                                      micropython sim/run.py OUT "app:companion,wait:6000,snap:x"
  options: --port PORT, --interval SECONDS

Run it with python3 (pip install pyserial) or `uv run tools/companion.py`. The badge is
found by USB vendor id (tools/badge.py, which asks mpremote: without it, pass --port) and
its port is opened without resetting it (tools/dev.py open_serial); unplugged, in standby
or in Retro-Go, it is waited for. The badge
clock is set from the Mac on every connection. While this runs, mpremote, tools/dev.py and
tools/music.py cannot use the port. Music and Spotify are asked what they play only when
they are already running (macOS asks once to allow it); nothing is ever launched.
"""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import badge  # noqa: E402
import dev  # noqa: E402

PLAYERS = ("Music", "Spotify")
NOW_PLAYING = """tell application "%s"
  if player state is stopped then return ""
  set t to current track
  return (name of t) & tab & (artist of t) & tab & (player state as text)
end tell"""


def _run(*cmd, timeout=5):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _clean(s, n=60):
    """Printable, in the Basic Multilingual Plane (the badge's JSON and fonts), short."""
    return "".join(c for c in s if c >= " " and ord(c) <= 0xFFFF).strip()[:n]


def processes():
    """(CPU load of the whole Mac in %, names of the running programs)."""
    total = 0.0
    names = set()
    for line in _run("ps", "-A", "-o", "%cpu=,comm=").splitlines():
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        try:
            total += float(parts[0].replace(",", "."))
        except ValueError:
            continue
        names.add(os.path.basename(parts[1].strip()))
    return min(100.0, total / (os.cpu_count() or 1)), names


def memory():
    """Memory used in %, counted as Activity Monitor does (app + wired + compressed)."""
    out = _run("vm_stat")
    total = _run("sysctl", "-n", "hw.memsize").strip()
    page = re.search(r"page size of (\d+) bytes", out)
    if not page or not total.isdigit():
        return None

    def pages(label):
        m = re.search(r"^%s:\s+(\d+)" % re.escape(label), out, re.M)
        return int(m.group(1)) if m else 0

    anon = pages("Anonymous pages")
    app = anon - pages("Pages purgeable") if anon else pages("Pages active")
    used = app + pages("Pages wired down") + pages("Pages occupied by compressor")
    return max(0.0, min(100.0, used * int(page.group(1)) * 100 / int(total)))


def battery():
    """(percent or None without a battery, charging, on AC power)."""
    out = _run("pmset", "-g", "batt")
    ac = "'AC Power'" in out
    m = re.search(r"(\d+)%;\s*([^;]+);", out)
    if not m:
        return None, False, ac
    return int(m.group(1)), m.group(2).strip() in ("charging", "finishing charge"), ac


def now_playing(running):
    """Music or Spotify, playing first, then paused; only the ones already running."""
    paused = None
    for app in PLAYERS:
        if app not in running:
            continue
        parts = _run("osascript", "-e", NOW_PLAYING % app, timeout=3).rstrip("\n").split("\t")
        if len(parts) != 3 or not parts[0]:
            continue
        info = {"track": _clean(parts[0]), "artist": _clean(parts[1]), "app": app,
                "playing": parts[2] == "playing"}
        if info["playing"]:
            return info
        paused = paused or info
    return paused


def host_name():
    return _clean(_run("scutil", "--get", "ComputerName")) or socket.gethostname().split(".")[0]


def stats(host):
    cpu, running = processes()
    ram = memory()
    batt, charging, ac = battery()
    out = {"cpu": round(cpu, 1), "ram": None if ram is None else round(ram, 1), "batt": batt,
           "charging": charging, "ac": ac, "host": host, "time": time.strftime("%H:%M")}
    out.update(now_playing(running) or {})
    return out


def payload(host):
    return "stats " + json.dumps(stats(host), separators=(",", ":"))


# -- the badge -----------------------------------------------------------------------------

def write(port, line):
    port.write(("\r\n@@TRB " + line + "\r\n").encode())


def wait_for_badge(explicit):
    if explicit:
        return explicit
    told = False
    while True:
        try:
            found = badge.list_badges()
        except FileNotFoundError:
            sys.exit("mpremote not found (pip install mpremote), or pass --port")
        except subprocess.CalledProcessError:
            found = []
        if len(found) == 1:
            return found[0][0]
        if len(found) > 1:
            sys.exit("more than one Espressif device attached, pick one with --port")
        if not told:
            print("waiting for the badge (switched on, data USB-C cable)...")
            told = True
        time.sleep(2)


def feed(send, args, host):
    """The clock, the app with --open, then the stats every interval, forever."""
    send("time %d" % int(time.time()))
    if args.open:
        send("app companion")
    while True:
        t0 = time.monotonic()
        send(payload(host))
        time.sleep(max(0.1, args.interval - (time.monotonic() - t0)))


def session(port_name, args, host):
    """Sends until the port fails (OSError) or Ctrl-C."""
    port = dev.open_serial(port_name)
    try:
        port.write_timeout = 2            # a badge that stops reading counts as gone
        print("sending to the badge on %s every %g s (Ctrl-C to stop)" % (port_name, args.interval))

        def send(line):
            write(port, line)
            port.reset_input_buffer()     # replies and REPL chatter
        feed(send, args, host)
    finally:
        try:
            dev.close_serial(port)
        except OSError:                   # unplugged: the lines cannot move, the fd must go
            port.close()


def dry_run(args):
    """Prints what a session or --notify would send."""
    def send(line):
        print("@@TRB " + line, flush=True)
    try:
        if args.notify is not None:
            send("toast " + _clean(args.notify, 120))
        else:
            feed(send, args, host_name())
    except BrokenPipeError:               # the reader (the simulator, head) is gone
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


def main():
    ap = argparse.ArgumentParser(description="Mac stats for the badge's Companion app.")
    ap.add_argument("--port", default=os.environ.get("BADGE_PORT"))
    ap.add_argument("--interval", type=float, default=2.0, metavar="SECONDS")
    ap.add_argument("--open", action="store_true", help="open the Companion app on the badge")
    ap.add_argument("--notify", metavar="TEXT", help="send one notification and exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the lines instead of sending them (no badge needed)")
    args = ap.parse_args()
    if args.interval <= 0:
        ap.error("--interval must be more than 0")
    if args.notify is not None and not _clean(args.notify):
        ap.error("--notify needs some text")
    try:
        if args.dry_run:
            dry_run(args)
            return
        try:
            import serial  # noqa: F401
        except ImportError:
            sys.exit("pyserial is missing: pip install pyserial, or uv run tools/companion.py")
        if args.notify is not None:
            port = dev.open_serial(badge.find_port(args.port))
            try:
                write(port, "toast " + _clean(args.notify, 120))
                time.sleep(0.2)
            finally:
                dev.close_serial(port)
            return
        host = host_name()
        while True:
            try:
                session(wait_for_badge(args.port), args, host)
            except OSError as e:          # pyserial's SerialException is an OSError
                print("badge lost (%s), waiting..." % e)
                time.sleep(2)
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
