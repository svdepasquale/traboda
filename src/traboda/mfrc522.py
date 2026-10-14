"""Ci522 / MFRC522 13.56 MHz reader on the display's SPI bus.

The reader shares SPI2 with the ILI9341, which the display drives at 40 MHz. Every public
call here brackets its transfers with spi.init(1 MHz) ... spi.init(40 MHz) in a finally, so
the bus is never left slow while the caller awaits and the display draws between calls.
Register access keeps the RFID CS (GPIO44) low for one address byte plus the data; reads
issue spi.read(1, 0) after the address. The IRQ pin is not wired, so transfers poll ComIrq
with the chip's own timer (set for a ~15 ms timeout) plus a wall-clock backstop.

A reader held in NRSTPD power-down (power.rfid) reads VersionReg as 0; init() tolerates
that (the simulator returns zeros) and never raises, so the app degrades to "no card".

1 MHz and the receiver gain left at its reset value (RFCfgReg 0x48, 33 dB) are the stock
firmware's settings and the ones that work with the badge's PCB coil. A tag held still for
60 s while the polls cycled through four settings gave its UID 245 times out of 245 at
1 MHz with the reset gain, 183 of 244 at 4 MHz with it, and 10 and 8 of 244 with the gain
at 48 dB (RFCfgReg 0x70) at either rate: at that gain the answers come back too garbled to
select.
"""

import time
from machine import Pin

ticks_ms = time.ticks_ms
ticks_diff = time.ticks_diff

# Registers
_COMMAND = 0x01
_COMIRQ = 0x04
_DIVIRQ = 0x05
_ERROR = 0x06
_STATUS2 = 0x08
_FIFODATA = 0x09
_FIFOLEVEL = 0x0A
_CONTROL = 0x0C
_BITFRAMING = 0x0D
_MODE = 0x11
_TXCONTROL = 0x14
_TXASK = 0x15
_CRCRESULT_H = 0x21
_CRCRESULT_L = 0x22
_TMODE = 0x2A
_TPRESCALER = 0x2B
_TRELOAD_H = 0x2C
_TRELOAD_L = 0x2D
_VERSION = 0x37

# PCD commands
_IDLE = 0x00
_CALCCRC = 0x03
_TRANSCEIVE = 0x0C
_MFAUTHENT = 0x0E
_SOFTRESET = 0x0F

# PICC commands
REQA = 0x26
WUPA = 0x52
_CT = 0x88
_SEL = (0x93, 0x95, 0x97)
_HLTA = 0x50
AUTH_A = 0x60
AUTH_B = 0x61
_READ = 0x30
_UL_WRITE = 0xA2
_GET_VERSION = 0x60


class MFRC522:
    def __init__(self, spi, cs_pin, lo=1_000_000, hi=None):
        self.spi = spi
        self.cs = Pin(cs_pin, Pin.OUT, value=1)
        self._lo = lo
        if hi is None:
            from . import board
            hi = board.DISPLAY_BAUD
        self._hi = hi
        self._a1 = bytearray(1)
        self._a2 = bytearray(2)
        self.ver = 0

    # -- bus / registers -------------------------------------------------------------------

    def _lock(self):
        self.spi.init(baudrate=self._lo)

    def _unlock(self):
        self.spi.init(baudrate=self._hi)

    def _wreg(self, reg, val):
        self._a2[0] = (reg << 1) & 0x7E
        self._a2[1] = val & 0xFF
        self.cs(0)
        self.spi.write(self._a2)
        self.cs(1)

    def _rreg(self, reg):
        self._a1[0] = ((reg << 1) & 0x7E) | 0x80
        self.cs(0)
        self.spi.write(self._a1)
        b = self.spi.read(1, 0)
        self.cs(1)
        return b[0]

    def _set_bits(self, reg, mask):
        self._wreg(reg, self._rreg(reg) | mask)

    def _clear_bits(self, reg, mask):
        self._wreg(reg, self._rreg(reg) & ~mask)

    def _write_fifo(self, data):
        self._a1[0] = (_FIFODATA << 1) & 0x7E
        self.cs(0)
        self.spi.write(self._a1)
        self.spi.write(bytes(data))
        self.cs(1)

    def _read_fifo(self, n):
        out = bytearray(n)
        for i in range(n):
            out[i] = self._rreg(_FIFODATA)
        return out

    # -- setup -----------------------------------------------------------------------------

    def init(self):
        """Soft reset, timer, 100% ASK, antenna on. Returns VersionReg."""
        self._lock()
        try:
            self._wreg(_COMMAND, _SOFTRESET)
            t0 = ticks_ms()
            while self._rreg(_COMMAND) & 0x10:
                if ticks_diff(ticks_ms(), t0) > 50:
                    break
                time.sleep_ms(1)
            self._wreg(_TMODE, 0x80)          # TAuto: timer starts after transmit
            self._wreg(_TPRESCALER, 0xA9)     # ~40 kHz timer tick
            self._wreg(_TRELOAD_H, 0x02)      # reload 600 -> ~15 ms auto-timeout
            self._wreg(_TRELOAD_L, 0x58)
            self._wreg(_TXASK, 0x40)          # force 100% ASK modulation
            self._wreg(_MODE, 0x3D)           # CRC preset 0x6363
            v = self._rreg(_TXCONTROL)
            if (v & 0x03) != 0x03:
                self._wreg(_TXCONTROL, v | 0x03)   # antenna drivers on
            self.ver = self._rreg(_VERSION)
        finally:
            self._unlock()
        return self.ver

    def version(self):
        self._lock()
        try:
            self.ver = self._rreg(_VERSION)
        finally:
            self._unlock()
        return self.ver

    # -- transceive ------------------------------------------------------------------------

    def _transceive(self, send, tx_last_bits=0, timeout_ms=40):
        """Send then receive through the FIFO. Returns (bytes, rx_last_bits) or (None, 0)."""
        self._wreg(_COMMAND, _IDLE)
        self._wreg(_COMIRQ, 0x7F)             # clear all IRQ bits
        self._wreg(_FIFOLEVEL, 0x80)          # flush FIFO
        self._write_fifo(send)
        self._wreg(_BITFRAMING, tx_last_bits)
        self._wreg(_COMMAND, _TRANSCEIVE)
        self._wreg(_BITFRAMING, 0x80 | tx_last_bits)   # StartSend
        t0 = ticks_ms()
        while True:
            irq = self._rreg(_COMIRQ)
            if irq & 0x30:                    # RxIRq or IdleIRq: a reply arrived
                break
            if irq & 0x01:                    # TimerIRq: no reply
                return None, 0
            if ticks_diff(ticks_ms(), t0) > timeout_ms:
                return None, 0
        self._wreg(_BITFRAMING, tx_last_bits)
        if self._rreg(_ERROR) & 0x1B:         # BufferOvfl | CollErr | ParityErr | ProtocolErr
            return None, 0
        n = self._rreg(_FIFOLEVEL)
        last = self._rreg(_CONTROL) & 0x07
        return self._read_fifo(n), last

    def _crc(self, data):
        """CRC_A over data, computed by the chip. Returns 2 bytes (little endian)."""
        self._wreg(_COMMAND, _IDLE)
        self._wreg(_DIVIRQ, 0x04)             # clear CRCIRq
        self._wreg(_FIFOLEVEL, 0x80)
        self._write_fifo(data)
        self._wreg(_COMMAND, _CALCCRC)
        t0 = ticks_ms()
        while not self._rreg(_DIVIRQ) & 0x04:
            if ticks_diff(ticks_ms(), t0) > 20:
                break
        self._wreg(_COMMAND, _IDLE)
        return bytes((self._rreg(_CRCRESULT_L), self._rreg(_CRCRESULT_H)))

    # -- activation (public: each locks the bus once) --------------------------------------

    def request(self, cmd=WUPA):
        """REQA/WUPA short frame. Returns the 2-byte ATQA, or None when no card answers."""
        self._lock()
        try:
            resp, _ = self._transceive(bytes((cmd,)), 7, 20)
        finally:
            self._unlock()
        return resp if resp and len(resp) == 2 else None

    def select(self):
        """Anticollision + SELECT through up to three cascade levels. Returns (uid, sak)."""
        self._lock()
        try:
            return self._select()
        finally:
            self._unlock()

    def _select(self):
        uid = bytearray()
        sak = 0
        for level in range(3):
            sel = _SEL[level]
            resp, _ = self._transceive(bytes((sel, 0x20)))     # anticollision, NVB=0x20
            if resp is None or len(resp) != 5:
                return None
            if resp[0] ^ resp[1] ^ resp[2] ^ resp[3] != resp[4]:
                return None                                    # BCC mismatch
            frame = bytearray((sel, 0x70, resp[0], resp[1], resp[2], resp[3], resp[4]))
            frame += self._crc(frame)
            ack, _ = self._transceive(bytes(frame))            # SELECT, NVB=0x70
            if ack is None or len(ack) < 1:
                return None
            sak = ack[0]
            if resp[0] == _CT:
                uid += resp[1:4]
            else:
                uid += resp[0:4]
            if not sak & 0x04:                                 # cascade complete
                break
        return bytes(uid), sak

    def halt(self):
        """HLTA: the card answers nothing by design, so a timeout here is success."""
        self._lock()
        try:
            frame = bytearray((_HLTA, 0x00))
            frame += self._crc(frame)
            self._transceive(bytes(frame), 0, 10)
            self._clear_bits(_STATUS2, 0x08)
        finally:
            self._unlock()

    # -- MIFARE Classic --------------------------------------------------------------------

    def auth(self, mode, block, key, uid):
        """MIFARE authenticate (mode AUTH_A/AUTH_B) for a block. Returns True on success."""
        self._lock()
        try:
            buf = bytearray(12)
            buf[0] = mode
            buf[1] = block
            buf[2:8] = bytes(key)
            buf[8:12] = bytes(uid[:4])
            self._wreg(_COMMAND, _IDLE)
            self._wreg(_COMIRQ, 0x7F)
            self._wreg(_FIFOLEVEL, 0x80)
            self._write_fifo(buf)
            self._wreg(_COMMAND, _MFAUTHENT)
            t0 = ticks_ms()
            while True:
                irq = self._rreg(_COMIRQ)
                if irq & 0x11:                # IdleIRq done, or TimerIRq
                    break
                if ticks_diff(ticks_ms(), t0) > 30:
                    break
            return bool(self._rreg(_STATUS2) & 0x08)
        finally:
            self._unlock()

    def stop_crypto(self):
        self._lock()
        try:
            self._clear_bits(_STATUS2, 0x08)
        finally:
            self._unlock()

    # -- read / write ----------------------------------------------------------------------

    def read_block(self, block):
        """READ (0x30): 16 bytes. For Classic this needs a prior auth of the block's sector;
        for Ultralight/NTAG it returns four pages starting at `block`."""
        self._lock()
        try:
            frame = bytearray((_READ, block))
            frame += self._crc(frame)
            resp, _ = self._transceive(bytes(frame), 0, 40)
        finally:
            self._unlock()
        return resp[:16] if resp and len(resp) >= 16 else None

    def ul_write(self, page, data):
        """Ultralight/NTAG WRITE (0xA2): one 4-byte page. Returns True on the 4-bit ACK."""
        self._lock()
        try:
            frame = bytearray((_UL_WRITE, page))
            frame += bytes(data[:4])
            frame += self._crc(frame)
            resp, _ = self._transceive(bytes(frame), 0, 40)
        finally:
            self._unlock()
        return resp is not None and len(resp) >= 1 and (resp[0] & 0x0F) == 0x0A

    def get_version(self):
        """NTAG/Ultralight-EV1 GET_VERSION (0x60): 8 bytes, or None when unsupported."""
        self._lock()
        try:
            frame = bytearray((_GET_VERSION,))
            frame += self._crc(frame)
            resp, _ = self._transceive(bytes(frame), 0, 40)
        finally:
            self._unlock()
        return resp[:8] if resp and len(resp) >= 8 else None
