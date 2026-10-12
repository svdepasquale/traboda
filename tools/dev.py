#!/usr/bin/env python3
# /// script
# dependencies = ["pyserial"]
# ///
"""Development loop against a badge on USB, without rebuilding the firmware.

  tools/dev.py sync         compile src/traboda to .mpy and copy it to /traboda on the
                            badge, where it shadows the frozen copy
  tools/dev.py clean        remove that overlay (the frozen OS runs again)
  tools/dev.py run          reboot the badge (main.py starts the OS)
  tools/dev.py snap OUT.png screenshot of the running OS
  tools/dev.py key NAME [ms] press a key on the running OS (up down left right A B play prev next)
  tools/dev.py time         set the badge clock from the Mac
  tools/dev.py toast TEXT   show a notification on the badge
  tools/dev.py wifi [SSID]  give the badge a Wi-Fi network: the password comes from the
                            macOS keychain (a system dialog asks you), goes over USB to the
                            running OS and is stored on the badge only

Needs mpremote and mpy-cross (built by firmware/build.sh) on the PATH or in their usual
places, and pyserial for the commands that talk to the running OS.
"""

import base64
import os
import shutil
import struct
import subprocess
import sys
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import badge  # noqa: E402

SRC = os.path.join(ROOT, "src", "traboda")
BUILD = os.path.join(ROOT, "firmware", ".build", "overlay")
MPY_CROSS = os.path.join(ROOT, "firmware", ".build", "micropython", "mpy-cross", "build", "mpy-cross")


def mpremote(port, *args, check=True):
    return subprocess.run(["mpremote", "connect", port] + list(args), check=check)


def compile_overlay():
    cross = MPY_CROSS if os.path.exists(MPY_CROSS) else shutil.which("mpy-cross")
    if not cross:
        sys.exit("mpy-cross not found: run firmware/build.sh once")
    if os.path.exists(BUILD):
        shutil.rmtree(BUILD)
    out_root = os.path.join(BUILD, "traboda")
    for dirpath, _dirs, files in os.walk(SRC):
        rel = os.path.relpath(dirpath, SRC)
        dest = os.path.normpath(os.path.join(out_root, rel))
        os.makedirs(dest, exist_ok=True)
        for name in files:
            if not name.endswith(".py"):
                continue
            src = os.path.join(dirpath, name)
            mod = os.path.join("traboda", rel, name) if rel != "." else os.path.join("traboda", name)
            subprocess.run([cross, "-march=xtensawin", "-s", mod, "-o",
                            os.path.join(dest, name[:-3] + ".mpy"), src], check=True)
    return out_root


def sync(port):
    out = compile_overlay()
    mpremote(port, "exec", "import os\ntry:\n os.stat('/traboda')\nexcept OSError:\n os.mkdir('/traboda')")
    mpremote(port, "cp", "-r", out + "/", ":/")
    print("synced %s -> %s:/traboda" % (out, port))


def clean(port):
    mpremote(port, "exec", """
import os
def rm(p):
    try:
        mode = os.stat(p)[0]
    except OSError:
        return
    if mode & 0x4000:
        for n in os.listdir(p):
            rm(p + '/' + n)
        os.rmdir(p)
    else:
        os.remove(p)
rm('/traboda')
print('overlay removed')
""")


# -- talking to the running OS ---------------------------------------------------------

def open_serial(port):
    """Opens the badge's USB-Serial-JTAG without resetting it.

    The peripheral emulates the classic auto-reset circuit: DTR low with RTS high holds
    the chip in reset. macOS raises both lines on open, so they are left high (pyserial's
    default) and lowered RTS-first on close, as mpremote does.
    """
    import serial
    s = serial.Serial()
    s.port = port
    s.baudrate = 115200
    s.timeout = 0.2
    s.open()
    return s


def close_serial(s):
    s.rts = False
    s.dtr = False
    s.close()


def command(port, line, until=None, timeout=5.0):
    s = open_serial(port)
    try:
        s.reset_input_buffer()
        s.write(("\r\n@@TRB " + line + "\r\n").encode())
        if not until:
            time.sleep(0.2)
            return b""
        buf = b""
        t0 = time.time()
        while until not in buf and time.time() - t0 < timeout:
            buf += s.read(65536)
        return buf
    finally:
        close_serial(s)


def png(path, rgb565_swapped, w=320, h=240):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        row = rgb565_swapped[y * w * 2:(y + 1) * w * 2]
        for x in range(w):
            c = row[2 * x] << 8 | row[2 * x + 1]      # byte-swapped in the framebuffer
            raw += bytes(((c >> 8) & 0xF8 | (c >> 13), (c >> 3) & 0xFC | (c >> 9) & 3,
                          (c << 3) & 0xF8 | (c >> 2) & 7))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
        f.write(chunk(b"IEND", b""))


def snap(port, out):
    buf = command(port, "snap", until=b"@@END", timeout=15)
    start = buf.find(b"@@SNAP ")
    if start < 0:
        sys.exit("no snapshot (is the OS running?)")
    header_end = buf.index(b"\n", start)
    size = int(buf[start + 7:header_end])
    body = buf[header_end + 1:buf.index(b"@@END", header_end)]
    data = base64.b64decode(b"".join(body.split()))
    if len(data) != size:
        sys.exit("short snapshot: %d of %d bytes" % (len(data), size))
    png(out, data)
    print("wrote", out)


def current_ssid():
    out = subprocess.run(["ipconfig", "getsummary", "en0"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("SSID :"):
            ssid = line.split(":", 1)[1].strip()
            return None if ssid.startswith("<") else ssid   # macOS redacts it without location access
    return None


def wifi(port, ssid):
    import json
    ssid = ssid or current_ssid()
    if not ssid:
        sys.exit("no SSID: pass one, e.g. tools/dev.py wifi MyNetwork")
    r = subprocess.run(["security", "find-generic-password", "-D", "AirPort network password",
                        "-a", ssid, "-w"], capture_output=True, text=True)
    if r.returncode:
        sys.exit("no keychain password for %r (or access denied)" % ssid)
    payload = json.dumps({"ssid": ssid, "password": r.stdout.strip()})
    reply = command(port, "wifi " + payload, until=b"@@", timeout=5)
    print("badge: %s for %s" % ("saved, joining" if b"@@OK" in reply else "no answer", ssid))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd, args = sys.argv[1], sys.argv[2:]
    port = badge.find_port(os.environ.get("BADGE_PORT"))
    if cmd == "sync":
        sync(port)
    elif cmd == "clean":
        clean(port)
    elif cmd == "run":
        # A soft reset inside mpremote's raw REPL does not run main.py: reboot instead.
        mpremote(port, "exec", "import machine; machine.reset()", check=False)
    elif cmd == "snap":
        snap(port, args[0] if args else "snap.png")
    elif cmd == "key":
        command(port, "key %s %s" % (args[0], args[1] if len(args) > 1 else "0"))
    elif cmd == "time":
        command(port, "time %d" % int(time.time()))
    elif cmd == "toast":
        command(port, "toast " + " ".join(args))
    elif cmd == "wifi":
        wifi(port, args[0] if args else None)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
