#!/usr/bin/env python3
"""Flashes Traboda onto the badge, leaving Retro-Go's partitions alone.

Writes the bootloader (0x0), the partition table (0x8000) and Traboda (0x10000) from
firmware/dist/ (or --dist DIR, checked against the SHA256SUMS next to the files). With
--download it first fetches them from a GitHub release, the latest or the tag given.

When the badge's partition table is not Traboda's (the first install, over the stock
firmware) it also erases Traboda's filesystem and Retro-Go's FAT fallback, where the stock
firmware kept its own storage; --erase-fs does the same on purpose, to start over. The boot
selector (otadata) is blanked every time, so the badge starts Traboda even when it was left
in Retro-Go. Retro-Go's apps (0x410000-0x740000) are never written.

Usage: tools/flash.py [--download [TAG]] [--dist DIR] [--erase-fs] [--port PORT]
       tools/flash.py --backup FILE        read the whole 16 MB flash into FILE
       tools/flash.py --restore FILE --yes write a full backup back (the stock firmware)
"""

import argparse
import hashlib
import json
import os
import shutil
import re
import struct
import subprocess
import sys
import tempfile
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import badge  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "firmware", "dist")
REPO = "svdepasquale/traboda"
IMAGES = ("bootloader.bin", "partition-table.bin", "traboda.bin")

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


def esptool_cmd():
    """esptool 5 or newer as installed: on the PATH (brew, pipx), else this Python's module
    (pip). This script speaks esptool 5 (write-flash, --after watchdog-reset); 4.x refuses."""
    cmd = None
    for name in ("esptool", "esptool.py"):
        if shutil.which(name):
            cmd = [name]
            break
    cmd = cmd or [sys.executable, "-m", "esptool"]
    try:
        out = subprocess.run(cmd + ["version"], capture_output=True, text=True).stdout
    except OSError:
        out = ""
    m = re.search(r"v?(\d+)\.\d+", out)
    if not m:
        sys.exit("esptool not found: install esptool 5 or newer (see the README, Install)")
    if int(m.group(1)) < 5:
        sys.exit("esptool %s found, this needs 5 or newer (see the README, Install)" % m.group(0))
    return cmd


def check_sums(folder):
    """When a release's SHA256SUMS sits next to the images, they must match it."""
    path = os.path.join(folder, "SHA256SUMS")
    if not os.path.exists(path):
        return
    with open(path) as f:
        sums = dict(reversed(line.split()) for line in f if len(line.split()) == 2)
    for name in IMAGES:
        want = sums.get(name) or sums.get("*" + name)
        with open(os.path.join(folder, name), "rb") as f:
            if want and hashlib.sha256(f.read()).hexdigest() != want.lower():
                sys.exit("%s does not match SHA256SUMS: download it again" % name)


def download(tag, folder):
    """Fetches a release's images and SHA256SUMS into folder, checked before writing."""
    url = "https://api.github.com/repos/%s/releases/%s" % (REPO, "tags/" + tag if tag else "latest")
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            release = json.load(r)
        assets = {a["name"]: a["browser_download_url"] for a in release["assets"]}
        blobs = {}
        for name in ("SHA256SUMS",) + IMAGES:
            if name not in assets:
                sys.exit("release %s has no %s" % (release["tag_name"], name))
            with urllib.request.urlopen(assets[name], timeout=60) as r:
                blobs[name] = r.read()
    except OSError as e:            # URLError, HTTPError and SSL errors are all OSErrors
        sys.exit("download failed (%s). Get %s and SHA256SUMS from "
                 "https://github.com/%s/releases into one folder and run with --dist FOLDER"
                 % (e, ", ".join(IMAGES), REPO))
    sums = {}
    for line in blobs["SHA256SUMS"].decode().splitlines():
        parts = line.split()
        if len(parts) == 2:
            sums[parts[1].lstrip("*")] = parts[0]
    for name in IMAGES:
        if hashlib.sha256(blobs[name]).hexdigest() != sums.get(name):
            sys.exit("%s does not match the release's SHA256SUMS: nothing written" % name)
    os.makedirs(folder, exist_ok=True)
    for name in ("SHA256SUMS",) + IMAGES:
        with open(os.path.join(folder, name), "wb") as f:
            f.write(blobs[name])
    print("Traboda %s downloaded into %s" % (release["tag_name"], folder), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", help="serial port (default: the only Espressif device)")
    ap.add_argument("--download", nargs="?", const="", metavar="TAG",
                    help="fetch the firmware from the latest GitHub release (or TAG) first")
    ap.add_argument("--dist", default=DIST, metavar="DIR",
                    help="folder with the three images (default: firmware/dist)")
    ap.add_argument("--erase-fs", action="store_true",
                    help="erase Traboda's filesystem and Retro-Go's FAT fallback (start over)")
    ap.add_argument("--backup", metavar="FILE", help="read the whole flash into FILE")
    ap.add_argument("--restore", metavar="FILE", help="write a full 16 MB image at 0x0")
    ap.add_argument("--yes", action="store_true", help="confirm --restore")
    args = ap.parse_args()

    if args.backup or args.restore:
        port = badge.find_port(args.port)
        esptool = esptool_cmd() + ["--chip", "esp32s3", "--port", port, "--baud", "921600",
                                   "--after", "watchdog-reset"]
        if args.backup:
            if os.path.exists(args.backup):
                sys.exit("%s already exists: keep it, and pick another name" % args.backup)
            subprocess.run(esptool + ["read-flash", "0", "0x1000000", args.backup], check=True)
            return
        if os.path.getsize(args.restore) != 0x1000000:
            sys.exit("%s is not a 16 MB full-flash image" % args.restore)
        if not args.yes:
            sys.exit("this overwrites the whole badge, Traboda included: add --yes")
        subprocess.run(esptool + ["write-flash", "0x0", args.restore], check=True)
        return

    if args.download is not None:
        download(args.download, args.dist)
    files = {name: os.path.join(args.dist, name) for name in IMAGES}
    for path in files.values():
        if not os.path.exists(path):
            sys.exit("missing %s: add --download, or build with firmware/build.sh" % path)
    check_sums(args.dist)

    table = read_table(files["partition-table.bin"])
    for label, where in EXPECTED.items():
        if table.get(label) != where:
            sys.exit("partition table mismatch for %r: %r, expected %r" % (label, table.get(label), where))
    app_size = os.path.getsize(files["traboda.bin"])
    if app_size > EXPECTED["factory"][1]:
        sys.exit("traboda.bin (%d bytes) does not fit the factory partition" % app_size)

    port = badge.find_port(args.port)
    esptool = esptool_cmd() + ["--chip", "esp32s3", "--port", port, "--baud", "921600"]

    erase = []
    with tempfile.TemporaryDirectory() as tmp:
        current = os.path.join(tmp, "table.bin")
        subprocess.run(esptool + ["--after", "no-reset", "read-flash", "0x8000", "0xc00", current],
                       check=True)
        with open(current, "rb") as a, open(files["partition-table.bin"], "rb") as b:
            first = a.read() != b.read()
    if first:
        print("first install on this badge (its partition table is not Traboda's): "
              "erasing the old storage, 0x742000 to the end", flush=True)
    if first or args.erase_fs:
        erase += ["data", "vfs"]
    for label in erase:
        offset, size = EXPECTED[label]
        subprocess.run(esptool + ["--after", "no-reset", "erase-region", hex(offset), hex(size)],
                       check=True)

    subprocess.run(esptool + [
        "--after", "no-reset", "write-flash", "--flash-mode", "keep", "--flash-freq", "keep",
        "--flash-size", "16MB",
        "0x0", files["bootloader.bin"],
        "0x8000", files["partition-table.bin"],
        "0x10000", files["traboda.bin"],
    ], check=True)
    # Retro-Go hands the badge over by pointing otadata at its next app; blank, the
    # bootloader starts the factory app, Traboda. Done after the write, so a failed write
    # leaves the badge booting what it booted before.
    offset, size = EXPECTED["otadata"]
    subprocess.run(esptool + ["--after", "no-reset", "erase-region", hex(offset), hex(size)],
                   check=True)
    # A reset through the USB-Serial-JTAG's RTS line latches the download strap and leaves
    # the chip in the ROM bootloader; the watchdog reboots it clean. The port vanishes under
    # esptool while it does, which it may report as an error: the image is already verified.
    subprocess.run(esptool + ["--before", "no-reset", "--after", "watchdog-reset", "chip-id"],
                   capture_output=True)
    print("done: Traboda flashed on %s (Retro-Go untouched). If the screen stays dark, "
          "slide the switch off and on." % port, flush=True)


if __name__ == "__main__":
    main()
