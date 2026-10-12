"""Shared state of the simulated badge (keys, LEDs, radios, battery)."""

# keys held now, as a bitmask over traboda.buttons indexes
keys = 0
GPIO0_KEY = 1 << 8          # buttons.NEXT: the fast-forward key is GPIO0 on the badge
int_pending = False
expander_out = bytearray(2)
leds = [(0, 0, 0)] * 22     # chain order, as written
battery_volts = 4.05
usb = True
frame = 0
audio_rate = 0
audio_bytes = 0
rtc_set = None
deepsleep = False

# buttons index -> AW9523 bit (see traboda/board.py)
_EX_BITS = {0: 6, 1: 3, 2: 5, 3: 2, 4: 0, 5: 9, 6: 1, 7: 8}


def expander_low():
    """AW9523 pins pulled low by held keys."""
    low = 0
    for k, bit in _EX_BITS.items():
        if keys & (1 << k):
            low |= 1 << bit
    return low


def press(k):
    global keys, int_pending
    keys |= 1 << k
    int_pending = True


def release(k):
    global keys, int_pending
    keys &= ~(1 << k)
    int_pending = True
