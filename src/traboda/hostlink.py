"""Commands from the Mac over the USB serial line, while the OS keeps running.

A line starting with "@@TRB " is a command; anything else is ignored. Ctrl-C still stops
the OS and drops to the REPL. tools/badgectl.py speaks this protocol:

  @@TRB ping                  -> @@PONG
  @@TRB snap                  -> @@SNAP <bytes>, base64 lines, @@END   (framebuffer)
  @@TRB key <name> [hold_ms]  inject a key press (names in buttons.NAMES)
  @@TRB time <epoch_utc>      set the RTC
  @@TRB toast <text>          show a notification (with an LED flash)
  @@TRB stats <json>          data for the Companion app (CPU, RAM, battery, track...)
  @@TRB app <name>            open an app
  @@TRB wifi <json>           {"ssid": ..., "password": ...}: save and join a network
  @@TRB info                  -> @@INFO <json> (version, app, errors, battery, heap, uptime)
"""

import binascii
import json
import select
import sys

from . import buttons

PREFIX = b"@@TRB "


class HostLink:
    def __init__(self, system):
        self.sys = system
        self.poll = select.poll()
        self.poll.register(sys.stdin, select.POLLIN)
        self.inp = getattr(sys.stdin, "buffer", sys.stdin)
        self.out = getattr(sys.stdout, "buffer", sys.stdout)
        self.line = bytearray()
        self.stats = None          # last dict pushed by the Mac
        self.stats_at = 0

    def pump(self):
        """Reads whatever arrived; returns the commands completed."""
        done = []
        while self.poll.poll(0):
            ch = self.inp.read(1)
            if not ch:
                break
            if ch in (b"\r", b"\n"):
                if bytes(self.line[:len(PREFIX)]) == PREFIX:
                    try:
                        done.append(bytes(self.line[len(PREFIX):]).decode())
                    except UnicodeError:
                        pass
                self.line = bytearray()
            elif len(self.line) < 4096:
                self.line += ch
        return done

    def handle(self, cmd):
        name, _, arg = cmd.partition(" ")
        s = self.sys
        if name == "ping":
            print("@@PONG")
        elif name == "snap":
            self.snap()
        elif name == "key":
            k, _, hold = arg.partition(" ")
            if k in buttons.NAMES:
                s.inject_key(buttons.NAMES.index(k), int(hold or 0))
        elif name == "time":
            s.set_utc(int(arg))
            print("@@OK")
        elif name == "toast":
            s.notify(arg)
        elif name == "stats":
            try:
                self.stats = json.loads(arg)
                import time
                self.stats_at = time.ticks_ms()
            except ValueError:
                pass
        elif name == "app":
            s.request_app(arg.strip())
        elif name == "info":
            import gc
            import time
            from . import VERSION, net
            info = {"version": VERSION, "app": s.app_name, "errors": s.errors[-10:],
                    "battery": s.battery, "charging": s.charging, "heap": gc.mem_free(),
                    "uptime_s": time.ticks_diff(time.ticks_ms(), s._started) // 1000,
                    "wifi": net.status, "ip": net.ip(), "sd": s.sd_mounted}
            print("@@INFO " + json.dumps(info))
        elif name == "wifi":
            try:
                cfg = json.loads(arg)
                from . import net
                net.remember(cfg["ssid"], cfg.get("password", ""))
                s.kick_wifi()
                print("@@OK")
            except (ValueError, KeyError):
                print("@@ERR")

    def snap(self):
        buf = self.sys.display.buf
        out = self.out
        out.write(("@@SNAP %d\n" % len(buf)).encode())
        mv = memoryview(buf)
        for i in range(0, len(buf), 3072):
            out.write(binascii.b2a_base64(mv[i:i + 3072]))
        out.write(b"@@END\n")
