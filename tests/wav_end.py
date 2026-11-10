"""WAV playback stops at the end of the data chunk (MicroPython, run by tests/smoke.py).

  micropython tests/wav_end.py TMPDIR

Plays synthetic WAVs through the simulator's I2S and checks the bytes sent: a chunk after
`data` (LIST/id3 tags) is not played, and a data size that is not a whole frame ends.
"""

import sys

ROOT = sys.argv[0].rsplit("/", 2)[0] if "/" in sys.argv[0] else "."
if ROOT.endswith("/tests") or ROOT == "tests":
    ROOT = ROOT[:-5].rstrip("/") or "."
sys.path.insert(0, ROOT + "/src")
sys.path.insert(0, ROOT + "/sim/fake")

import asyncio  # noqa: E402
import struct  # noqa: E402

import simstate  # noqa: E402

from traboda import audio, board, power  # noqa: E402
from traboda.aw9523 import AW9523  # noqa: E402


def wav(path, data, tail=b"", channels=2, rate=22050):
    fmt = struct.pack("<HHIIHH", 1, channels, rate, rate * channels * 2, channels * 2, 16)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
    body += b"data" + struct.pack("<I", len(data)) + data + b"\0" * (len(data) & 1) + tail
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", len(body)) + body)


async def played(a, path):
    simstate.audio_bytes = 0
    a.play(path)
    for _ in range(500):
        await asyncio.sleep_ms(10)
        if not a.playing:
            break
    assert not a.playing, "still playing: " + path
    assert a.error is None, a.error
    return simstate.audio_bytes


async def main(tmp):
    i2c = board.i2c()
    power.init(AW9523(i2c))
    a = audio.Audio(i2c)
    tag = b"LIST" + struct.pack("<I", 4092) + b"INFO" + b"\x7f" * 4088
    cases = (
        ("tail", bytes(6000), tag, 6000),       # trailing tags: only the 6000 data bytes
        ("odd", bytes(4099), b"", 4096),        # 4099 bytes = 1024 frames + 3 stray bytes
        ("short", bytes(3), tag, 0),            # less than one frame
    )
    for name, data, tail, want in cases:
        path = tmp + "/" + name + ".wav"
        wav(path, data, tail)
        got = await played(a, path)
        assert got == want, "%s: sent %d bytes, want %d" % (name, got, want)
        print("wav %s ok" % name)


asyncio.run(main(sys.argv[1]))
