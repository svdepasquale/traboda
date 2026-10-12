"""A stand-in for MicroPython's machine module on the unix port: enough of the badge to
run Traboda OS headless. The AW9523 model takes its key state from sim.state."""

import io
import time

import simstate as state

IN = 1
OUT = 2
OPEN_DRAIN = 3
PULL_UP = 1
PULL_DOWN = 2
IRQ_FALLING = 1
IRQ_RISING = 2


class Pin:
    IN = IN
    OUT = OUT
    OPEN_DRAIN = OPEN_DRAIN
    PULL_UP = PULL_UP
    PULL_DOWN = PULL_DOWN
    IRQ_FALLING = IRQ_FALLING
    IRQ_RISING = IRQ_RISING

    def __init__(self, id, mode=None, pull=None, value=None, hold=None):
        self.id = id
        self._value = 1 if value is None else value

    def value(self, v=None):
        if v is None:
            if self.id == 0:                    # GPIO0: the fast-forward key on the badge
                return 0 if state.keys & state.GPIO0_KEY else 1
            if self.id == 8:                    # AW9523 INTN
                return 0 if state.int_pending else 1
            return self._value
        self._value = v

    __call__ = value

    def irq(self, *a, **k):
        return None

    def init(self, *a, **k):
        pass


class PWM:
    def __init__(self, pin, freq=1000, duty_u16=0):
        self._duty = duty_u16
        self._freq = freq

    def duty_u16(self, v=None):
        if v is None:
            return self._duty
        self._duty = v

    def freq(self, v=None):
        if v is None:
            return self._freq
        self._freq = v

    def deinit(self):
        pass


class _AW9523:
    def __init__(self):
        self.regs = bytearray(256)
        self.regs[0x10] = 0x23
        self.regs[0x04] = 0xFF
        self.regs[0x05] = 0xFF
        self.regs[0x12] = 0xFF
        self.regs[0x13] = 0xFF

    def read(self, reg):
        if reg in (0, 1):
            state.int_pending = False
            pins = 0xFFFF & ~state.expander_low()
            return (pins >> (8 * reg)) & 0xFF
        return self.regs[reg]

    def write(self, reg, value):
        self.regs[reg] = value
        if reg in (2, 3):
            state.expander_out[reg - 2] = value


class _ES8156:
    def __init__(self):
        self.regs = bytearray(256)
        self.regs[0xFD] = 0x81
        self.regs[0xFE] = 0x55

    def read(self, reg):
        return self.regs[reg]

    def write(self, reg, value):
        self.regs[reg] = value


_devices = {0x58: _AW9523(), 0x08: _ES8156()}


class I2C:
    def __init__(self, id=0, scl=None, sda=None, freq=400000):
        pass

    def scan(self):
        return sorted(_devices)

    def readfrom_mem_into(self, addr, reg, buf):
        dev = _devices[addr]
        for i in range(len(buf)):
            buf[i] = dev.read(reg + i)

    def readfrom_mem(self, addr, reg, n):
        buf = bytearray(n)
        self.readfrom_mem_into(addr, reg, buf)
        return bytes(buf)

    def writeto_mem(self, addr, reg, data):
        dev = _devices[addr]
        for i, b in enumerate(data):
            dev.write(reg + i, b)


class SPI:
    def __init__(self, id=1, baudrate=1000000, **kw):
        self.baudrate = baudrate

    def init(self, baudrate=None, **kw):
        if baudrate:
            self.baudrate = baudrate

    def write(self, buf):
        pass

    def read(self, n, write=0):
        return bytes(n)

    def readinto(self, buf, write=0):
        for i in range(len(buf)):
            buf[i] = 0

    def write_readinto(self, out, inp):
        for i in range(len(inp)):
            inp[i] = 0


class ADC:
    ATTN_0DB = 0
    ATTN_2_5DB = 1
    ATTN_6DB = 2
    ATTN_11DB = 3

    def __init__(self, pin, atten=None):
        pass

    def read_uv(self):
        return int(state.battery_volts * 470 / 1970 * 1_000_000)

    def read_u16(self):
        return 30000


class I2S(io.IOBase):
    TX = 0
    RX = 1
    MONO = 0
    STEREO = 1

    def __init__(self, id, sck=None, ws=None, sd=None, mck=None, mode=0, bits=16,
                 format=1, rate=22050, ibuf=20000):
        self.rate = rate
        self.channels = 2 if format == 1 else 1
        state.audio_rate = rate

    def write(self, buf):
        n = len(buf)
        state.audio_bytes += n
        # pace like real hardware would: bytes / byte-rate
        time.sleep_ms(n * 1000 // (self.rate * self.channels * 2) // 4)
        return n

    def ioctl(self, req, arg):
        if req == 3:            # MP_STREAM_POLL: always writable
            return arg & 4
        return 0

    def deinit(self):
        pass


class RTC:
    def datetime(self, t=None):
        if t is None:
            g = time.gmtime()
            return (g[0], g[1], g[2], g[6], g[3], g[4], g[5], 0)
        state.rtc_set = t


class SDCard:
    def __init__(self, *a, **k):
        raise OSError(19)


class _Mem:
    def __getitem__(self, addr):
        state.frame += 1
        return state.frame if state.usb else 0


mem32 = _Mem()
mem16 = _Mem()
mem8 = _Mem()


class Timer:
    def __init__(self, *a, **k):
        pass

    def init(self, *a, **k):
        pass

    def deinit(self):
        pass


def freq(f=None):
    return 240_000_000


def unique_id():
    return b"\x14\xc1\x9f\xc4\x3d\x4c"


def reset():
    raise SystemExit("machine.reset()")


def soft_reset():
    raise SystemExit("machine.soft_reset()")


def deepsleep(ms=0):
    state.deepsleep = True
    raise SystemExit("machine.deepsleep()")


def lightsleep(ms=0):
    time.sleep_ms(ms or 1)


def idle():
    pass
