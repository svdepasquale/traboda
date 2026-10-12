"""Finds the badge among the serial devices, by USB vendor id, never by port name.

The badge is an ESP32-S3: Espressif's vendor id 0x303a, both in the ROM bootloader
(USB-Serial-JTAG, 303a:1001) and under MicroPython (TinyUSB CDC). Anything else on the
bus, a Raspberry Pi Pico running MicroPython for instance (2e8a:0005), is ignored.
"""

import subprocess
import sys

ESPRESSIF_VID = "303a"


def list_badges():
    """[(port, serial, vid:pid, description)] for every Espressif device attached."""
    out = subprocess.run(["mpremote", "devs"], capture_output=True, text=True, check=True).stdout
    found = []
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) >= 3 and parts[2].lower().startswith(ESPRESSIF_VID + ":"):
            found.append((parts[0], parts[1], parts[2], parts[3] if len(parts) > 3 else ""))
    return found


def find_port(explicit=None):
    if explicit:
        return explicit
    badges = list_badges()
    if not badges:
        sys.exit("badge not found: switch it ON (slide switch) and use a data USB-C cable")
    if len(badges) > 1:
        listing = "\n".join("  %s  %s  %s" % (p, s, d) for p, s, _, d in badges)
        sys.exit("more than one Espressif device attached, pick one with --port:\n" + listing)
    return badges[0][0]


if __name__ == "__main__":
    for port, serial, vidpid, desc in list_badges():
        print(port, serial, vidpid, desc)
