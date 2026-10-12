#!/usr/bin/env python3
"""Renders Traboda's two demo tunes to 16-bit mono WAV (original compositions, CC0).

  tools/chiptune.py OUTDIR [--rate 22050]

Square-wave lead and arpeggio, triangle bass, noise drums: a tiny tracker in plain
Python, so the Walkman has something to play on a badge without an SD card.
"""

import argparse
import math
import os
import random
import struct

NOTES = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8,
         "A": 9, "A#": 10, "B": 11}


def freq(name):
    """'A4' -> 440.0; None/'-' -> rest."""
    if not name or name == "-":
        return 0.0
    pitch, octave = name[:-1], int(name[-1])
    return 440.0 * 2 ** ((NOTES[pitch] + 12 * (octave - 4) - 9) / 12)


class Song:
    def __init__(self, bpm, bars, rate):
        self.rate = rate
        self.step = 60.0 / bpm / 4               # one 16th note, seconds
        self.n = int(bars * 16 * self.step * rate)
        self.buf = [0.0] * self.n

    def _span(self, step, length):
        a = int(step * self.step * self.rate)
        b = min(self.n, int((step + length) * self.step * self.rate))
        return a, b

    def square(self, step, length, note, vol, duty=0.5, decay=6.0):
        f = freq(note)
        if not f:
            return
        a, b = self._span(step, length)
        period = self.rate / f
        for i in range(a, b):
            t = (i - a) / self.rate
            env = math.exp(-decay * t) * 0.8 + 0.2 if decay else 1.0
            phase = ((i - a) % period) / period
            self.buf[i] += (vol if phase < duty else -vol) * env

    def triangle(self, step, length, note, vol):
        f = freq(note)
        if not f:
            return
        a, b = self._span(step, length)
        period = self.rate / f
        for i in range(a, b):
            phase = ((i - a) % period) / period
            v = 4 * phase - 1 if phase < 0.5 else 3 - 4 * phase
            fade = min(1.0, (b - i) / (0.01 * self.rate))
            self.buf[i] += v * vol * fade

    def noise(self, step, length, vol, decay):
        a, b = self._span(step, length)
        rnd = random.Random(step)
        for i in range(a, b):
            t = (i - a) / self.rate
            self.buf[i] += (rnd.random() * 2 - 1) * vol * math.exp(-decay * t)

    def kick(self, step, vol=0.9):
        a, b = self._span(step, 2)
        for i in range(a, b):
            t = (i - a) / self.rate
            f = 120 * math.exp(-18 * t) + 45
            self.buf[i] += math.sin(2 * math.pi * f * t) * vol * math.exp(-9 * t)

    def save(self, path):
        peak = max(1e-6, max(abs(v) for v in self.buf))
        gain = 0.85 / peak
        data = bytearray()
        for v in self.buf:
            data += struct.pack("<h", int(max(-1.0, min(1.0, v * gain)) * 32767))
        with open(path, "wb") as f:
            f.write(b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt ")
            f.write(struct.pack("<IHHIIHH", 16, 1, 1, self.rate, self.rate * 2, 2, 16))
            f.write(b"data" + struct.pack("<I", len(data)))
            f.write(data)


CHORDS = {"C": ("C", "E", "G"), "G": ("G", "B", "D"), "Am": ("A", "C", "E"),
          "F": ("F", "A", "C"), "Em": ("E", "G", "B"), "Dm": ("D", "F", "A")}


def drums(song, bars, fill_every=4):
    for bar in range(bars):
        s = bar * 16
        song.kick(s)
        song.kick(s + 8)
        if bar % fill_every == fill_every - 1:
            song.kick(s + 14, 0.7)
        song.noise(s + 4, 3, 0.35, 22)
        song.noise(s + 12, 3, 0.35, 22)
        for h in range(0, 16, 2):
            song.noise(s + h, 1, 0.08, 90)


def traboda_theme(rate):
    """'Traboda', 140 bpm, I-V-vi-IV in C."""
    prog = ("C", "G", "Am", "F") * 4
    song = Song(140, len(prog), rate)
    lead = ("E5 - G5 - C6 - B5 A5 G5 - E5 - D5 - C5 -",
            "D5 - G5 - B5 - A5 G5 D5 - B4 - D5 - G5 -",
            "C5 - E5 - A5 - G5 E5 C5 - A4 - C5 - E5 -",
            "F5 - A5 - C6 - A5 G5 F5 - E5 - D5 - C5 -")
    for bar, chord in enumerate(prog):
        s = bar * 16
        root = CHORDS[chord][0]
        for e in range(8):
            song.triangle(s + e * 2, 2, root + ("2" if e % 2 == 0 else "3"), 0.45)
        tones = CHORDS[chord]
        for k in range(16):
            song.square(s + k, 1, tones[k % 3] + "4", 0.10, duty=0.125, decay=14)
        if bar >= 4:
            notes = lead[bar % 4].split()
            for k, note in enumerate(notes):
                if note != "-":
                    song.square(s + k, 2, note, 0.16, duty=0.5, decay=3)
    drums(song, len(prog))
    return song


def notte_a_roma(rate):
    """'Notte a Roma', 100 bpm, vi-IV-I-V in C with a slow echoing arpeggio."""
    prog = ("Am", "F", "C", "G") * 3
    song = Song(100, len(prog), rate)
    melody = ("A5 - - - C6 - B5 - A5 - G5 - E5 - - -",
              "F5 - - - A5 - G5 - F5 - E5 - C5 - - -",
              "E5 - - - G5 - A5 - G5 - E5 - D5 - - -",
              "D5 - - - G5 - F5 - E5 - D5 - B4 - - -")
    for bar, chord in enumerate(prog):
        s = bar * 16
        tones = CHORDS[chord]
        song.triangle(s, 8, tones[0] + "2", 0.5)
        song.triangle(s + 8, 8, tones[0] + "2", 0.5)
        for k in range(8):
            note = tones[k % 3] + ("4" if k < 4 else "5")
            song.square(s + k * 2, 2, note, 0.09, duty=0.25, decay=8)
            song.square(s + k * 2 + 3, 2, note, 0.035, duty=0.25, decay=8)
        if bar >= 4:
            for k, note in enumerate(melody[bar % 4].split()):
                if note != "-":
                    song.square(s + k, 4, note, 0.13, duty=0.5, decay=1.5)
    for bar in range(4, len(prog)):
        s = bar * 16
        song.kick(s, 0.7)
        song.kick(s + 10, 0.6)
        song.noise(s + 8, 4, 0.25, 12)
    return song


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--rate", type=int, default=22050)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    for name, make in (("Traboda - Theme.wav", traboda_theme), ("Traboda - Notte a Roma.wav", notte_a_roma)):
        path = os.path.join(args.outdir, name)
        make(args.rate).save(path)
        print(path, os.path.getsize(path) // 1024, "KB")


if __name__ == "__main__":
    main()
