"""Finds the badge among the serial devices, by USB vendor id, never by port name.

The badge is an ESP32-S3: Espressif's vendor id 0x303a, both in the ROM bootloader
(USB-Serial-JTAG, 303a:1001) and under MicroPython (TinyUSB CDC). Anything else on the
bus, a Raspberry Pi Pico running MicroPython for instance (2e8a:0005), is ignored.
"""

import subprocess
import sys

ESPRESSIF_VID = "303a"


def _devices():
    """[(port, serial, vid:pid, description)] for every USB serial device: through pyserial
    when this Python has it (pip's esptool and mpremote both bring it), else 'mpremote devs'."""
    try:
        from serial.tools import list_ports
    except ImportError:
        list_ports = None
    if list_ports is not None:
        return [(p.device, p.serial_number or "-", "%04x:%04x" % (p.vid, p.pid), p.description or "")
                for p in list_ports.comports() if p.vid is not None]
    try:
        out = subprocess.run(["mpremote", "devs"], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        sys.exit("cannot list serial ports: install mpremote (see the README, Install) or "
                 "pass --port")
    found = []
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) >= 3:
            found.append((parts[0], parts[1], parts[2], parts[3] if len(parts) > 3 else ""))
    return found


def list_badges():
    """[(port, serial, vid:pid, description)] for every Espressif device attached."""
    return [d for d in _devices() if d[2].lower().startswith(ESPRESSIF_VID + ":")]


def find_port(explicit=None):
    if explicit:
        return explicit
    badges = list_badges()
    if not badges:
        sys.exit("badge not found: switch it on (slide switch), wake it from standby with a "
                 "key, and use a data USB-C cable")
    if len(badges) > 1:
        listing = "\n".join("  %s  %s  %s" % (p, s, d) for p, s, _, d in badges)
        sys.exit("more than one Espressif device attached, pick one with --port:\n" + listing)
    return badges[0][0]


if __name__ == "__main__":
    for port, serial, vidpid, desc in list_badges():
        print(port, serial, vidpid, desc)
