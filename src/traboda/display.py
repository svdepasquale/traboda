"""ILI9341 320x240 panel over SPI, drawn through a full-screen RGB565 framebuffer.

The framebuffer lives in PSRAM and holds byte-swapped RGB565 (big-endian on the wire), so
every colour handed to framebuf must come from rgb(). show() pushes whole rows: a
full-width band is contiguous in memory and goes out as a single DMA write.
"""

import framebuf
import time
from machine import PWM, Pin

from . import board

W = 320
H = 240

# Panel setup from the badge's Retro-Go port (power, VCOM, frame rate, gamma).
_INIT = (
    (0xCF, b"\x00\xc3\x30"),
    (0xED, b"\x64\x03\x12\x81"),
    (0xE8, b"\x85\x00\x78"),
    (0xCB, b"\x39\x2c\x00\x34\x02"),
    (0xF7, b"\x20"),
    (0xEA, b"\x00\x00"),
    (0xC0, b"\x1b"),
    (0xC1, b"\x12"),
    (0xC5, b"\x32\x3c"),
    (0xC7, b"\x91"),
    (0xB1, b"\x00\x10"),
    (0xB6, b"\x0a\xa2"),
    (0xF6, b"\x01\x30"),
    (0xF2, b"\x00"),
    (0x26, b"\x01"),
    (0xE0, b"\xd0\x00\x02\x07\x0a\x28\x32\x44\x42\x06\x0e\x12\x14\x17"),
    (0xE1, b"\xd0\x00\x02\x07\x0a\x28\x31\x54\x47\x0e\x1c\x17\x1b\x1e"),
)
# MV|MY with BGR order: landscape, the orientation Retro-Go settled on this hardware.
_MADCTL = 0xA8


def rgb(r, g, b):
    """24-bit colour to the byte-swapped RGB565 the framebuffer holds."""
    c = (r & 0xF8) << 8 | (g & 0xFC) << 3 | b >> 3
    return (c & 0xFF) << 8 | c >> 8


def unswap(c):
    """Byte-swapped RGB565 back to (r, g, b)."""
    c = (c & 0xFF) << 8 | c >> 8
    return (c >> 8 & 0xF8, c >> 3 & 0xFC, c << 3 & 0xF8)


class Display:
    def __init__(self, spi, expander):
        self.spi = spi
        self.cs = Pin(board.LCD_CS, Pin.OUT, value=1)
        self.dc = Pin(board.LCD_DC, Pin.OUT, value=1)
        self.buf = bytearray(W * H * 2)
        self.mv = memoryview(self.buf)
        self.fb = framebuf.FrameBuffer(self.buf, W, H, framebuf.RGB565)
        self._backlight = PWM(Pin(board.LCD_BACKLIGHT), freq=25_000, duty_u16=0)
        self.brightness = 0
        self._cmdbuf = bytearray(1)
        self._win = bytearray(4)
        self._scratch = bytearray(W * H * 2)    # show_rect gathers rows here
        self._smv = memoryview(self._scratch)
        self.asleep = False
        expander.set(board.EX_LCD_RESET, 0)
        time.sleep_ms(20)
        expander.set(board.EX_LCD_RESET, 1)
        time.sleep_ms(10)
        self.init()

    def _cmd(self, c, data=None):
        # The bus runs at the display's rate; the RFID driver lowers it only for its own
        # transfers and puts it back before returning.
        self._cmdbuf[0] = c
        self.cs(0)
        self.dc(0)
        self.spi.write(self._cmdbuf)
        if data:
            self.dc(1)
            self.spi.write(data)
        self.cs(1)

    def init(self):
        self._cmd(0x01)
        time.sleep_ms(120)
        self._cmd(0x3A, b"\x55")
        self._cmd(0x36, bytes((_MADCTL,)))
        for c, d in _INIT:
            self._cmd(c, d)
        self._cmd(0x11)
        time.sleep_ms(120)
        self._cmd(0x29)
        self.asleep = False

    def show(self, y0=0, y1=H):
        """Push rows y0..y1-1 to the panel."""
        if self.asleep or y1 <= y0:
            return
        y0 = max(0, y0)
        y1 = min(H, y1)
        self._window(0, y0, W - 1, y1 - 1)
        self._cmdbuf[0] = 0x2C
        self.cs(0)
        self.dc(0)
        self.spi.write(self._cmdbuf)
        self.dc(1)
        self.spi.write(self.mv[y0 * W * 2:y1 * W * 2])
        self.cs(1)

    def _window(self, x0, y0, x1, y1):
        w = self._win
        w[0] = x0 >> 8
        w[1] = x0 & 0xFF
        w[2] = x1 >> 8
        w[3] = x1 & 0xFF
        self._cmd(0x2A, w)
        w[0] = y0 >> 8
        w[1] = y0 & 0xFF
        w[2] = y1 >> 8
        w[3] = y1 & 0xFF
        self._cmd(0x2B, w)

    def show_rect(self, x, y, w, h):
        """Push one rectangle: cheaper than a band when the change is narrow (a sprite, a
        pipe edge, two snake cells far apart)."""
        if self.asleep:
            return
        if x < 0:
            w += x
            x = 0
        if y < 0:
            h += y
            y = 0
        w = min(w, W - x)
        h = min(h, H - y)
        if w <= 0 or h <= 0:
            return
        if w == W:
            self.show(y, y + h)
            return
        # framebuf clips a blit to its destination, so blitting the whole screen at
        # (-x, -y) into a w x h buffer gathers the rectangle in C (~1.5 ms for 40x140;
        # a per-row memoryview copy loop took ~9 ms per row on this port).
        framebuf.FrameBuffer(self._scratch, w, h, framebuf.RGB565).blit(self.fb, -x, -y)
        self._window(x, y, x + w - 1, y + h - 1)
        self._cmdbuf[0] = 0x2C
        self.cs(0)
        self.dc(0)
        self.spi.write(self._cmdbuf)
        self.dc(1)
        self.spi.write(self._smv[:w * h * 2])
        self.cs(1)

    def set_brightness(self, percent):
        """Backlight 0-100 %; a gamma-ish curve keeps the low end usable."""
        percent = max(0, min(100, percent))
        self.brightness = percent
        self._backlight.duty_u16((percent * percent * 65535) // 10000)

    def sleep(self):
        self._backlight.duty_u16(0)
        self._cmd(0x28)
        self._cmd(0x10)
        self.asleep = True

    def wake(self):
        self._cmd(0x11)
        time.sleep_ms(120)
        self._cmd(0x29)
        self.asleep = False
        self.show()
        self.set_brightness(self.brightness)
