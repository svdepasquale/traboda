"""Sound through the ES8156 DAC: headphone jack always, speaker amp when enabled.

The codec is configured over I2C with Espressif's ES8156 sequence (the one the badge's own
firmwares use) after the I2S clocks run, MCLK included. Playback streams 16-bit PCM WAV
through machine.I2S with asyncio, so the UI keeps running; the player fills `levels` for
the LED VU meter.
"""

import asyncio
import struct
import time
from machine import I2S, Pin

from . import board, power

_INIT = ((0x02, 0x04), (0x20, 0x2A), (0x21, 0x3C), (0x22, 0x00), (0x24, 0x07), (0x23, 0x00),
         (0x0A, 0x01), (0x0B, 0x01), (0x11, 0x00), (0x14, 0xB3), (0x0D, 0x14), (0x18, 0x00),
         (0x08, 0x3F), (0x00, 0x02), (0x00, 0x03), (0x25, 0x20))
_STOP = ((0x14, 0x00), (0x19, 0x02), (0x21, 0x1F), (0x22, 0x02), (0x25, 0x21), (0x25, 0xA1),
         (0x18, 0x01), (0x09, 0x02), (0x09, 0x01), (0x08, 0x00))
_UI_RATE = 22050


def parse_wav(f):
    """Reads a RIFF/WAVE header. Returns (rate, channels, bits, data_bytes); f is left at
    the first sample."""
    head = f.read(12)
    if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    rate = channels = bits = None
    while True:
        chunk = f.read(8)
        if len(chunk) < 8:
            raise ValueError("WAV without data")
        cid, size = chunk[:4], struct.unpack("<I", chunk[4:])[0]
        if cid == b"fmt ":
            fmt = f.read(size)
            tag, channels, rate = struct.unpack_from("<HHI", fmt)
            bits = struct.unpack_from("<H", fmt, 14)[0]
            if tag not in (1, 0xFFFE):
                raise ValueError("compressed WAV (only PCM)")
        elif cid == b"data":
            if rate is None:
                raise ValueError("WAV data before fmt")
            return rate, channels, bits, size
        else:
            f.seek(size + (size & 1), 1)


class Audio:
    def __init__(self, i2c):
        self.i2c = i2c
        self.i2s = None
        self.rate = 0
        self.channels = 0
        self.volume = 60
        self.speaker_enabled = True
        self.levels = (0.0, 0.0)
        # player state
        self.track = None          # path being played
        self.playing = False
        self.paused = False
        self.position = 0          # bytes of PCM sent
        self.length = 0            # bytes of PCM in the track
        self.byte_rate = 1
        self.error = None
        self.ended = False         # set when a track ran to its end by itself
        self._task = None
        self._stop = False
        self._seek_to = None
        self._b1 = bytearray(1)

    # -- codec -----------------------------------------------------------------------------

    def _reg(self, reg, value):
        self._b1[0] = value
        self.i2c.writeto_mem(board.ES8156_ADDR, reg, self._b1)

    def _open(self, rate, channels):
        if self.i2s and rate == self.rate and channels == self.channels:
            return
        if self.i2s:
            self.i2s.deinit()
        self.i2s = I2S(0, sck=Pin(board.I2S_BCK), ws=Pin(board.I2S_WS), sd=Pin(board.I2S_DOUT),
                       mck=Pin(board.I2S_MCK), mode=I2S.TX, bits=16,
                       format=I2S.STEREO if channels == 2 else I2S.MONO,
                       rate=rate, ibuf=24_000)
        self.rate = rate
        self.channels = channels
        time.sleep_ms(2)
        for reg, value in _INIT:
            self._reg(reg, value)
        self.set_volume(self.volume)
        power.speaker(self.speaker_enabled)

    def close(self):
        if self.i2s:
            for reg, value in _STOP:
                self._reg(reg, value)
            power.speaker(False)
            self.i2s.deinit()
            self.i2s = None
            self.rate = 0

    def set_volume(self, percent):
        """0-100 %: -45 dB .. +3 dB on the codec's 0.5 dB volume register, 0 mutes."""
        self.volume = max(0, min(100, percent))
        if self.i2s:
            reg = 0 if self.volume == 0 else 0xBF + int((-45 + 48 * self.volume / 100) * 2)
            self._reg(0x14, max(0, min(255, reg)))

    def set_speaker(self, on):
        self.speaker_enabled = on
        if self.i2s:
            power.speaker(on)

    # -- effects ---------------------------------------------------------------------------

    def tone(self, freq, ms, level=0.3):
        """A short square-ish tone (blocking for its duration at most)."""
        if self.playing and not self.paused:
            return
        self._open(_UI_RATE, 1)
        n = _UI_RATE * ms // 1000
        period = max(2, _UI_RATE // max(1, freq))
        amp = int(32767 * level)
        buf = bytearray(n * 2)
        half = period // 2
        fade = min(n, _UI_RATE // 200)
        for i in range(n):
            v = amp if (i % period) < half else -amp
            if i < fade:
                v = v * i // fade
            elif i > n - fade:
                v = v * (n - i) // fade
            struct.pack_into("<h", buf, i * 2, v)
        self.i2s.write(buf)

    def click(self):
        self.tone(2400, 6, 0.12)

    def melody(self, notes, level=0.3):
        """notes: [(freq_hz or 0 for a rest, ms), ...]"""
        for freq, ms in notes:
            if freq:
                self.tone(freq, ms, level)
            else:
                time.sleep_ms(ms)

    # -- player ----------------------------------------------------------------------------

    def play(self, path):
        self.stop()
        self.track = path
        self.error = None
        self.ended = False
        self._stop = False
        self._task = asyncio.create_task(self._run(path))

    def toggle(self):
        if self.playing:
            self.paused = not self.paused

    def stop(self):
        if self._task:
            self._stop = True
            self._task.cancel()
            self._task = None
        self.playing = False
        self.paused = False
        self.levels = (0.0, 0.0)

    @property
    def elapsed(self):
        return self.position / self.byte_rate

    @property
    def duration(self):
        return self.length / self.byte_rate

    def seek(self, seconds):
        self._seek_to = max(0, int(seconds * self.byte_rate)) & ~3

    async def _run(self, path):
        f = None
        try:
            f = open(path, "rb")
            rate, channels, bits, size = parse_wav(f)
            if bits != 16:
                raise ValueError("%d-bit WAV (only 16-bit)" % bits)
            data_start = f.tell()
            self._open(rate, channels)
            self.byte_rate = rate * channels * 2
            self.length = size
            self.position = 0
            self.playing = True
            self._seek_to = None
            out = asyncio.StreamWriter(self.i2s)
            buf = bytearray(4096)
            mv = memoryview(buf)
            frame = channels * 2
            while not self._stop:
                if self.paused:
                    self.levels = (0.0, 0.0)
                    await asyncio.sleep_ms(40)
                    continue
                if self._seek_to is not None:
                    f.seek(data_start + min(self._seek_to, size))
                    self.position = min(self._seek_to, size)
                    self._seek_to = None
                n = f.readinto(buf)
                if n <= 0 or self.position >= size:
                    self.ended = True
                    break
                n -= n % frame
                self.position += n
                self.levels = _peaks(buf, n, channels)
                out.out_buf = mv[:n]
                await out.drain()
        except asyncio.CancelledError:
            pass
        except Exception as e:  # noqa: BLE001 - surfaced in the player UI
            self.error = str(e)
        finally:
            if f:
                f.close()
            self.playing = False
            self.levels = (0.0, 0.0)
            self._task = None


def _peaks(buf, n, channels):
    """Rough per-channel peak (0..1) from 24 samples spread over the block."""
    step = max(4, (n // 24) & ~3)
    left = right = 0
    unpack = struct.unpack_from
    for i in range(0, n - 3, step):
        if channels == 2:
            l, r = unpack("<hh", buf, i)
        else:
            l = r = unpack("<h", buf, i)[0]
        if l < 0:
            l = -l
        if r < 0:
            r = -r
        if l > left:
            left = l
        if r > right:
            right = r
    return left / 32768, right / 32768
