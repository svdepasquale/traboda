#!/usr/bin/env python3
"""Flashes Traboda onto the badge, leaving Retro-Go's partitions alone.

Writes the bootloader (0x0), the partition table (0x8000) and Traboda (0x10000) from
firmware/dist/. With --erase-fs it also erases Traboda's filesystem and Retro-Go's FAT
fallback; do that on the first install (the stock firmware left FAT filesystems there)
or to start over. Nothing between 0x410000 and 0x742000 (Retro-Go, otadata) is written.

Usage: tools/flash.py [--port PORT] [--erase-fs]
"""

import argparse
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import badge  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "firmware", "dist")

# What the partition table must say for Retro-Go to keep working (label -> offset, size).
EXPECTED = {
    "factory": (0x010000, 0x400000),
    "launcher": (0x410000, 0x120000),
    "retro-core": (0x530000, 0x120000),
    "prboom-go": (0x650000, 0x0F0000),
    "otadata": (0x740000, 0x002000),
    "data": (0x742000, 0x200000),
    "vfs": (0x942000, 0x6BE000),
}


def read_table(path):
    table = {}
    data = open(path, "rb").read()
    for i in range(0, len(data), 32):
        magic, _type, _sub, offset, size = struct.unpack_from("<HBBII", data, i)
        if magic != 0x50AA:
            break
        label = data[i + 12:i + 28].rstrip(b"\0").decode()
        table[label] = (offset, size)
    return table


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", help="serial port (default: the only Espressif device)")
    ap.add_argument("--erase-fs", action="store_true",
                    help="erase Traboda's filesystem and Retro-Go's FAT fallback")
    args = ap.parse_args()

    files = {name: os.path.join(DIST, name) for name in
             ("bootloader.bin", "partition-table.bin", "traboda.bin")}
    for path in files.values():
        if not os.path.exists(path):
            sys.exit("missing %s: run firmware/build.sh first" % path)

    table = read_table(files["partition-table.bin"])
    for label, where in EXPECTED.items():
        if table.get(label) != where:
            sys.exit("partition table mismatch for %r: %r, expected %r" % (label, table.get(label), where))
    app_size = os.path.getsize(files["traboda.bin"])
    if app_size > EXPECTED["factory"][1]:
        sys.exit("traboda.bin (%d bytes) does not fit the factory partition" % app_size)

    port = badge.find_port(args.port)
    esptool = ["esptool", "--chip", "esp32s3", "--port", port, "--baud", "921600"]

    if args.erase_fs:
        for label in ("data", "vfs"):
            offset, size = EXPECTED[label]
            subprocess.run(esptool + ["--after", "no-reset", "erase-region", hex(offset), hex(size)], check=True)

    # "--after watchdog-reset": a reset through the USB-Serial-JTAG's RTS line latches the
    # download strap and leaves the chip in the ROM bootloader; the watchdog reboots it clean.
    subprocess.run(esptool + [
        "--after", "watchdog-reset", "write-flash", "--flash-mode", "keep", "--flash-freq", "keep", "--flash-size", "16MB",
        "0x0", files["bootloader.bin"],
        "0x8000", files["partition-table.bin"],
        "0x10000", files["traboda.bin"],
    ], check=True)
    print("done: Traboda flashed on %s (Retro-Go untouched)" % port)


if __name__ == "__main__":
    main()
