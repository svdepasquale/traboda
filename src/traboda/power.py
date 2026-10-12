"""Power: the switched rails on the expander, the battery gauge, USB presence, standby.

The 5 V boost feeds both the speaker amplifier and the LED strip, so it is reference
counted: it stays on while either user holds it.
"""

import time
from machine import ADC, Pin, mem32

from . import board

_ex = None
_boost_users = set()
_adc = None
# LiPo open-circuit voltage -> charge %, coarse but monotonic
_CURVE = ((4.20, 100), (4.10, 90), (4.00, 79), (3.90, 66), (3.80, 52), (3.75, 42),
          (3.70, 31), (3.65, 21), (3.60, 13), (3.50, 6), (3.40, 2), (3.30, 0))
_DIVIDER = (1500 + 470) / 470
_USJ_FRAME = 0x60038024     # USB_SERIAL_JTAG_FRAM_NUM_REG: SOF frame index, bits 10:0


def init(expander):
    global _ex, _adc
    _ex = expander
    _adc = ADC(Pin(board.BATTERY_ADC), atten=ADC.ATTN_2_5DB)


def boost(user, on):
    if on:
        _boost_users.add(user)
    else:
        _boost_users.discard(user)
    want = bool(_boost_users)
    if want != bool(_ex.get(board.EX_BOOST)):
        _ex.set(board.EX_BOOST, want)
        if want:
            time.sleep_ms(3)


def led_rail(on):
    if on:
        boost("leds", True)
        _ex.set(board.EX_LED_POWER, 1)
    else:
        _ex.set(board.EX_LED_POWER, 0)
        boost("leds", False)


def speaker(on):
    """Speaker amplifier (the headphone jack is driven by the codec and always live)."""
    if on:
        boost("amp", True)
        _ex.set(board.EX_AMP_SHUTDOWN, 0)
    else:
        _ex.set(board.EX_AMP_SHUTDOWN, 1)
        boost("amp", False)


def rfid(on):
    """Ci522 NRSTPD: low holds the reader in hard power-down."""
    if on:
        _ex.set(board.EX_RFID_RESET, 0)
        time.sleep_ms(10)
        _ex.set(board.EX_RFID_RESET, 1)
        time.sleep_ms(50)
    else:
        _ex.set(board.EX_RFID_RESET, 0)


def battery_volts(samples=8):
    total = 0
    for _ in range(samples):
        total += _adc.read_uv()
    return total / samples * _DIVIDER / 1_000_000


def battery_percent(volts=None):
    v = battery_volts() if volts is None else volts
    if v >= _CURVE[0][0]:
        return 100
    for (v1, p1), (v0, p0) in zip(_CURVE, _CURVE[1:]):
        if v >= v0:
            return int(p0 + (p1 - p0) * (v - v0) / (v1 - v0))
    return 0


def usb_connected():
    """True while a USB host is sending start-of-frame packets (and so charging us)."""
    a = mem32[_USJ_FRAME] & 0x7FF
    time.sleep_ms(2)
    return (mem32[_USJ_FRAME] & 0x7FF) != a


def sd_present():
    return not _ex.pin(board.EX_SD_DETECT)


def standby(display=None, leds=None, audio=None):
    """Everything off, then deep sleep until any key is pressed (wakes as a fresh boot).

    The slide switch is the only true off: this leaves the ESP32 in deep sleep (~10 uA)
    with the expander watching the keys.
    """
    import esp32
    import machine

    if audio:
        audio.stop()
    if leds:
        leds.off(now=True)
    speaker(False)
    led_rail(False)
    rfid(False)
    if display:
        display.sleep()
    Pin(board.LCD_BACKLIGHT, Pin.OUT, value=0, hold=True)
    # Wait for every key to be released, then clear INTN so only a new press wakes us.
    while _ex.inputs() & 0x036F != 0x036F or not Pin(board.BUTTON_PREV).value():
        time.sleep_ms(20)
    _ex.inputs()
    Pin(board.EXPANDER_INT, Pin.IN, Pin.PULL_UP, hold=True)
    esp32.wake_on_ext0(Pin(board.EXPANDER_INT), esp32.WAKEUP_ALL_LOW)
    esp32.wake_on_ext1((Pin(board.BUTTON_PREV),), esp32.WAKEUP_ALL_LOW)
    machine.deepsleep()
