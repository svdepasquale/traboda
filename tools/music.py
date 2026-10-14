#!/usr/bin/env python3
"""Music for the badge: converts audio files to 16-bit PCM WAV with ffmpeg, then copies
them to the badge's internal "music" folder, or to an SD card mounted on the Mac.

  tools/music.py song.mp3 album/*.flac       22050 Hz mono WAVs into :/music on the badge
  tools/music.py --hq song.m4a               44100 Hz stereo (four times the space)
  tools/music.py --sd /Volumes/SD *.mp3      into /Volumes/SD/music instead of the badge
  options: --port PORT (default: the badge found by tools/badge.py)

The Walkman reads "Artist - Title.wav" as artist and title, so name the sources that way
(the WAV keeps the source's name; on the SD card without accents, which the badge cannot
list there). With tracks in the card's music folder the Walkman plays those, not the
internal ones. 22050 Hz mono takes about 2.6 MB a minute and the
internal memory holds a few MB: files that do not fit are refused before anything is
copied. The copy goes through mpremote, which stops Traboda OS (it takes over the REPL),
so the badge is reset at the end and the OS starts again. Needs ffmpeg (brew install
ffmpeg) and mpremote; not while tools/companion.py holds the port.
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import badge  # noqa: E402

FOLDER = "music"              # settings "music_dir": /music in flash, /sd/music on a card
RESERVE = 64 * 1024           # left free for settings, scores and the filesystem itself


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" % (n, unit)) if unit == "B" else "%.1f %s" % (n, unit)
        n /= 1024


def wav_name(path, ascii_only=False):
    """The source's name as a WAV, minus the characters FAT does not allow. ascii_only
    for the SD card: the badge reads FAT names in code page 437, so an accented name
    written by the Mac cannot be listed there ("Perché" becomes "Perche")."""
    base = os.path.splitext(os.path.basename(path))[0]
    if ascii_only:
        base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    base = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", base).strip(" .")[:120]
    return (base or "brano") + ".wav"


def convert(src, dst, hq):
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", src,
           "-vn", "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:a", "+bitexact",
           "-ac", "2" if hq else "1", "-ar", "44100" if hq else "22050", "-c:a", "pcm_s16le", dst]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        lines = r.stderr.strip().splitlines()
        raise RuntimeError(lines[-1] if lines else "ffmpeg exited with %d" % r.returncode)


def minutes(size, hq):
    s = size // (44100 * 4 if hq else 22050 * 2)
    return "%d:%02d" % (s // 60, s % 60)


def fit(files, free, cost=lambda size: size):
    """The files that fit in free bytes (keeping RESERVE), in order; reports the others.
    cost(size) is what a file takes on the target filesystem."""
    chosen = []
    for path, name, size in files:
        need = cost(size)
        if need + RESERVE <= free:
            chosen.append((path, name, size))
            free -= need
        else:
            print("  no room for %s (%s, %s free)" % (name, human(size), human(max(0, free - RESERVE))))
    return chosen


def mpremote(port, *args, capture=False):
    cmd = ["mpremote", "connect", port, "resume"] + list(args)
    return subprocess.run(cmd, capture_output=capture, text=True)


def badge_free(port):
    """Makes /music on the badge; returns its filesystem's free bytes and block size."""
    code = ("import os\ntry:\n os.mkdir('/%s')\nexcept OSError:\n pass\n"
            "s = os.statvfs('/')\nprint('@@FREE', s[1] * s[4], s[1])" % FOLDER)
    r = mpremote(port, "exec", code, capture=True)
    m = re.search(r"@@FREE (\d+) (\d+)", r.stdout)
    if r.returncode or not m:
        sys.exit("cannot read the badge's free space:\n" + (r.stderr or r.stdout).strip())
    return int(m.group(1)), int(m.group(2))


def to_badge(port, files):
    """Copies what fits; the badge is reset at the end whatever happens, since mpremote
    stopped the OS."""
    try:
        free, block = badge_free(port)
        print("badge: %s free in flash" % human(free))
        # LittleFS stores a file in whole blocks, each losing ~8 bytes to skip-list pointers
        chosen = fit(files, free, lambda size: -(-size // (block - 8)) * block)
        args = []
        for path, name, _size in chosen:
            args += ["fs", "cp", path, ":/%s/%s" % (FOLDER, name), "+"]
        r = mpremote(port, *args[:-1]) if args else None
        if r is not None and r.returncode:
            sys.exit("mpremote failed (exit %d)" % r.returncode)
        return chosen
    finally:
        mpremote(port, "reset", capture=True)  # restarts the OS; the port drops, so no exit code


def to_sd(folder, files):
    dest = folder if os.path.basename(folder.rstrip("/")).lower() == FOLDER else \
        os.path.join(folder, FOLDER)
    os.makedirs(dest, exist_ok=True)
    chosen = []
    for path, name, size in files:
        if fit([(path, name, size)], shutil.disk_usage(dest).free):
            shutil.copyfile(path, os.path.join(dest, name))
            chosen.append((path, name, size))
    print("written to %s" % dest)
    return chosen


def main():
    ap = argparse.ArgumentParser(description="Converts audio to WAV and copies it to the badge.")
    ap.add_argument("files", nargs="+", help="audio files ffmpeg can read")
    ap.add_argument("--hq", action="store_true", help="44100 Hz stereo instead of 22050 Hz mono")
    ap.add_argument("--sd", metavar="DIR", help="write to this mounted SD card (or its music folder)")
    ap.add_argument("--port", default=os.environ.get("BADGE_PORT"))
    args = ap.parse_args()
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found: brew install ffmpeg")
    if not args.sd and not shutil.which("mpremote"):
        sys.exit("mpremote not found: pip install mpremote")
    if args.sd and not os.path.isdir(args.sd):
        sys.exit("%s is not a folder: is the SD card mounted?" % args.sd)
    port = None if args.sd else badge.find_port(args.port)
    with tempfile.TemporaryDirectory(prefix="traboda-music-") as tmp:
        files = []
        names = set()
        # Windows shells pass wildcards through unexpanded; real names (even "a [b].mp3")
        # are taken as they are.
        for src in [m for a in args.files
                    for m in ([a] if os.path.exists(a) else sorted(glob.glob(a)) or [a])]:
            if not os.path.isfile(src):
                print("  skipped %s: no such file" % src)
                continue
            name = wav_name(src, bool(args.sd))
            if name in names:
                print("  skipped %s: another file is also called %s" % (src, name))
                continue
            out = os.path.join(tmp, name)
            try:
                convert(src, out, args.hq)
            except (OSError, RuntimeError) as e:
                print("  skipped %s: %s" % (src, e))
                continue
            names.add(name)
            size = os.path.getsize(out)
            files.append((out, name, size))
            print("  %s  %s  %s" % (name, human(size), minutes(size, args.hq)))
        if not files:
            sys.exit("nothing to copy")
        if args.sd:
            done = to_sd(args.sd, files)
        else:
            done = to_badge(port, files)
    print("%d of %d copied, %s" % (len(done), len(files), human(sum(f[2] for f in done))))


if __name__ == "__main__":
    main()
