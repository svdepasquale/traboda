#!/usr/bin/env python3
"""Tiles simulator snapshots (LABEL.raw) into one PNG for the README.

  python3 sim/montage.py OUTDIR label1,label2,... out.png [--cols 3]
"""

import argparse
import os
import struct
import zlib

W, H = 320, 240
GAP = 10
BG = (22, 22, 28)


def load(path):
    data = open(path, "rb").read()
    px = []
    for i in range(0, W * H * 2, 2):
        c = data[i] << 8 | data[i + 1]
        px.append(((c >> 8) & 0xF8, (c >> 3) & 0xFC, (c << 3) & 0xF8))
    return px


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("labels")
    ap.add_argument("out")
    ap.add_argument("--cols", type=int, default=3)
    args = ap.parse_args()
    labels = args.labels.split(",")
    rows = (len(labels) + args.cols - 1) // args.cols
    ow = args.cols * W + (args.cols + 1) * GAP
    oh = rows * H + (rows + 1) * GAP
    img = [list(BG) * ow for _ in range(oh)]
    for n, label in enumerate(labels):
        px = load(os.path.join(args.outdir, label + ".raw"))
        x0 = GAP + (n % args.cols) * (W + GAP)
        y0 = GAP + (n // args.cols) * (H + GAP)
        for y in range(H):
            row = img[y0 + y]
            for x in range(W):
                r, g, b = px[y * W + x]
                k = (x0 + x) * 3
                row[k] = r
                row[k + 1] = g
                row[k + 2] = b
    raw = b"".join(b"\x00" + bytes(r) for r in img)

    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))

    with open(args.out, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", ow, oh, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    print(args.out)


if __name__ == "__main__":
    main()
