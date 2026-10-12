#!/usr/bin/env python3
"""Converts sim/run.py snapshots (LABEL.raw + LABEL.leds) to 2x PNGs with the LED strip."""

import ast
import glob
import os
import struct
import sys
import zlib

ORDER = tuple(range(21, 10, -1)) + tuple(range(11))   # position -> chain index (leds.py)
W, H, S = 320, 240, 2
STRIP = 36


def convert(raw_path):
    data = open(raw_path, "rb").read()
    leds = [(0, 0, 0)] * 22
    led_path = raw_path[:-4] + ".leds"
    if os.path.exists(led_path):
        leds = ast.literal_eval(open(led_path).read())
    ow, oh = W * S, H * S + STRIP
    img = bytearray(b"\x16\x16\x1c" * ow * oh)

    def put(x, y, c):
        i = (y * ow + x) * 3
        img[i:i + 3] = bytes(c)

    for pos in range(22):
        r, g, b = leds[ORDER[pos]]
        # brighten what the LED engine dims, so the colour reads in a screenshot
        m = max(r, g, b, 1)
        c = (r * 255 // m, g * 255 // m, b * 255 // m) if max(r, g, b) else (40, 40, 48)
        cx = 40 + (pos % 11) * 52
        cy = 8 + (pos // 11) * 14
        for dy in range(8):
            for dx in range(20):
                put(cx + dx, cy + dy, c)
    for y in range(H):
        for x in range(W):
            hi, lo = data[(y * W + x) * 2], data[(y * W + x) * 2 + 1]
            c = hi << 8 | lo
            rgb = ((c >> 8) & 0xF8, (c >> 3) & 0xFC, (c << 3) & 0xF8)
            for dy in range(S):
                for dx in range(S):
                    put(x * S + dx, STRIP + y * S + dy, rgb)
    raw = b"".join(b"\x00" + bytes(img[y * ow * 3:(y + 1) * ow * 3]) for y in range(oh))

    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))

    out = raw_path[:-4] + ".png"
    with open(out, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", ow, oh, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))
    return out


if __name__ == "__main__":
    for path in sorted(glob.glob(os.path.join(sys.argv[1], "*.raw"))):
        print(convert(path))
