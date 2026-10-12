"""AW9523B 16-bit I2C GPIO expander: the badge's buttons and power switches.

Register map: 0x00/0x01 input, 0x02/0x03 output, 0x04/0x05 direction (1 = input),
0x06/0x07 interrupt mask (1 = masked), 0x10 id (0x23), 0x11 GCR (bit 4: P0 push-pull),
0x12/0x13 LED-mode switch (1 = GPIO), 0x7F soft reset.
"""

from . import board

_INPUTS = (1 << board.EX_A | 1 << board.EX_PLAY | 1 << board.EX_RIGHT | 1 << board.EX_DOWN
           | 1 << board.EX_LEFT | 1 << board.EX_UP | 1 << 4
           | 1 << board.EX_NEXT | 1 << board.EX_B | 1 << board.EX_SD_DETECT | 1 << 13)
_BUTTONS = (1 << board.EX_A | 1 << board.EX_PLAY | 1 << board.EX_RIGHT | 1 << board.EX_DOWN
            | 1 << board.EX_LEFT | 1 << board.EX_UP | 1 << board.EX_NEXT | 1 << board.EX_B)


class AW9523:
    def __init__(self, i2c, addr=board.AW9523_ADDR):
        self.i2c = i2c
        self.addr = addr
        self._b1 = bytearray(1)
        self._b2 = bytearray(2)
        if self._read8(0x10) != 0x23:
            raise OSError("AW9523B not found")
        # Outputs first, directions second, so no switch glitches on when a pin turns output:
        # amplifier shut down, boost, RFID and LEDs off, LCD out of reset.
        self.out = 1 << board.EX_AMP_SHUTDOWN | 1 << board.EX_LCD_RESET
        self._write8(0x11, 0x10)  # P0 push-pull, or P0.7 could never drive the amp off
        self._write8(0x12, 0xFF)
        self._write8(0x13, 0xFF)
        self._write16(0x02, self.out)
        self._write16(0x04, _INPUTS)
        self._write16(0x06, 0xFFFF & ~_BUTTONS)  # INTN fires on button changes only

    def _read8(self, reg):
        self.i2c.readfrom_mem_into(self.addr, reg, self._b1)
        return self._b1[0]

    def _write8(self, reg, value):
        self._b1[0] = value
        self.i2c.writeto_mem(self.addr, reg, self._b1)

    def _write16(self, reg, value):
        self._b2[0] = value & 0xFF
        self._b2[1] = value >> 8
        self.i2c.writeto_mem(self.addr, reg, self._b2)

    def inputs(self):
        """Both input ports as one 16-bit word (reading also clears INTN)."""
        self.i2c.readfrom_mem_into(self.addr, 0x00, self._b2)
        return self._b2[0] | self._b2[1] << 8

    def pin(self, n):
        return self.inputs() >> n & 1

    def set(self, n, on):
        value = self.out | 1 << n if on else self.out & ~(1 << n)
        if value != self.out:
            self.out = value
            port = n >> 3
            self._write8(0x02 + port, value >> (8 * port) & 0xFF)

    def get(self, n):
        return self.out >> n & 1
