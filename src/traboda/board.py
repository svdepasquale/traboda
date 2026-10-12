"""Pin map of the RomHack Camp 2026 badge (the PCB carries the Traboda brand).

Source: hardware/SCHEMATIC.pdf in github.com/cybersaiyanIT/rhc2026-badge, cross-checked
with the pin tables of its Tactility and Retro-Go ports.
"""

from machine import I2C, SPI, Pin

# ESP32-S3 GPIOs
I2C_SDA = 17
I2C_SCL = 16
SPI_SCK = 12            # SPI2/FSPI IO_MUX pins: the bus can run at 80 MHz
SPI_MOSI = 11
SPI_MISO = 13
LCD_CS = 15
LCD_DC = 9
LCD_BACKLIGHT = 21      # NPN low-side switch, PWM dimmable
RFID_CS = 44            # U0RXD on the module, hence no UART REPL
SD_CLK = 4              # SDMMC slot 1, 1-bit
SD_CMD = 5
SD_D0 = 7
SD_D3 = 14              # held high so the card stays in SD (not SPI) mode
I2S_MCK = 10
I2S_BCK = 43            # U0TXD on the module
I2S_WS = 46
I2S_DOUT = 45
LED_DATA = 3            # through a 74AHCT1G126 buffer powered by the LED rail
LED_COUNT = 22
BATTERY_ADC = 6         # ADC1 channel 5, 1.5 M / 470 k divider
EXPANDER_INT = 8        # AW9523B INTN, open drain, low on any input change
BUTTON_PREV = 0         # GPIO0: the rewind key, also the BOOT strap

# AW9523B pins, flat numbering: P0.x = x, P1.x = 8 + x
EX_A = 0
EX_PLAY = 1
EX_RIGHT = 2
EX_DOWN = 3
EX_LEFT = 5
EX_UP = 6
EX_AMP_SHUTDOWN = 7     # FM8002A shutdown: high = off, low = speaker on
EX_NEXT = 8             # P1.0, the fast-forward key
EX_B = 9                # P1.1
EX_BOOST = 10           # P1.2, 5 V boost for the speaker amp and the LEDs
EX_SD_DETECT = 11       # P1.3, low while a card is inserted
EX_RFID_RESET = 12      # P1.4, Ci522 NRSTPD: low = powered down
EX_LCD_RESET = 14       # P1.6
EX_LED_POWER = 15       # P1.7, LED rail switch

AW9523_ADDR = 0x58
ES8156_ADDR = 0x08

_i2c = None
_spi = None


def i2c():
    global _i2c
    if _i2c is None:
        _i2c = I2C(0, scl=Pin(I2C_SCL), sda=Pin(I2C_SDA), freq=400_000)
    return _i2c


def spi(baudrate=40_000_000):
    """The shared SPI bus (display and RFID). Re-init with another baudrate as needed."""
    global _spi
    if _spi is None:
        _spi = SPI(1, baudrate=baudrate, sck=Pin(SPI_SCK), mosi=Pin(SPI_MOSI), miso=Pin(SPI_MISO))
    return _spi
