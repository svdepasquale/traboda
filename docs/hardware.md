# The badge's hardware

The RomHack Camp 2026 badge (Cyber Saiyan; the PCB also carries the **Traboda** brand)
is an ESP32-S3 handheld shaped after a Sony Walkman WM-22. Schematic, BOM and photos:
[cybersaiyanIT/rhc2026-badge](https://github.com/cybersaiyanIT/rhc2026-badge)
(`hardware/`). Everything below was checked on a real badge.

| Part | Detail |
|---|---|
| Module | ESP32-S3-WROOM-1 N16R8: 2x Xtensa LX7 240 MHz, 16 MB QIO flash, 8 MB octal PSRAM (in the chip package), Wi-Fi 4, BLE 5 |
| Display | 2.4" ILI9341 320x240, SPI2 on its IO_MUX pins (SCK 12, MOSI 11, MISO 13), CS 15, DC 9, reset on expander P1.6, backlight PWM on GPIO21 |
| Expander | AW9523B at I2C 0x58 (SDA 17, SCL 16, 400 kHz), INTN on GPIO8 |
| Audio | ES8156 DAC at I2C 0x08, I2S0: MCLK 10, BCLK 43, LRCK 46, DOUT 45. Left/right to the 3.5 mm jack, right also to an FM8002A amplifier and the speaker. Amp shutdown on expander P0.7 (high = off) |
| LEDs | 22 WS2812-type LEDs, data GPIO3 through a 74AHCT1G126 buffer powered by the LED rail (expander P1.7), which hangs off the 5 V boost (expander P1.2) |
| NFC | Ci522 (MFRC522 compatible, VersionReg 0x92) on the display's SPI bus, CS GPIO44, NRSTPD on expander P1.4, IRQ not connected, 27.12 MHz crystal. **The antenna is a PCB coil** (net HF_ANT, about 55 cm of 0.25 mm track on both layers) in the board's upper-left corner seen from the front, around the Cyber Saiyan logo: cards go there, on either face. J4 (U.FL) sits in parallel with the coil for an external antenna; J3's pads tap TX1/TX2 ahead of the EMC filter |
| Storage | microSD, SDMMC 1-bit: CLK 4, CMD 5, D0 7 (D3/CS is GPIO14, held high); card detect on expander P1.3 (low = card in) |
| Battery | LiPo through a TP4056 charger (status LEDs only, not readable); voltage on GPIO6 (ADC1 ch5) via 1.5 M / 470 k |
| Expansion | J1: JST-SH 1.0 mm 4-pin (SM04B-SRSS-TB), the **Qwiic / STEMMA QT** connector, on the internal I2C bus (expander 0x58 and codec 0x08 already on it); J2: debug header (TX, RX/RFID-CS, 3V3, VIN) |

## Keys

| Key | Wired to | Switch |
|---|---|---|
| D-pad up / down / left / right | expander P0.6 / P0.3 / P0.5 / P0.2 | SW10 / SW12 / SW3 / SW11 |
| A (right, upper) | expander P0.0 | SW5 |
| B (right, lower) | expander P1.1 | SW4 |
| play (middle, under the screen) | expander P0.1 | SW7 |
| prev (left, under the screen) | expander P1.0 | SW6 |
| next (right, under the screen) | **GPIO0**, the BOOT strap (also SW1 on the back) | SW8 |

Every key has a 100 k pull-up and a 100 nF capacitor (hardware debounce). **Read the
expander's input ports one register at a time**: on this badge a 2-byte burst read from
0x00 intermittently returned a stale port 1 (0x40), which looked like B and prev never
working, phantom B/prev presses and a phantom SD card, while single-byte reads of 0x00 and
0x01 were always right. All nine keys work.

## LEDs

The chain starts at the bottom-left LED, runs right along the bottom row, then back left
along the top row (`traboda/leds.py` `ORDER`). 22 LEDs at full white would pull more than
the boost can give: Traboda caps them at 60 % and defaults to 25 %.

## Notes for firmware authors

* **UART0 is not a console here**: GPIO43 (U0TXD) is the I2S bit clock and GPIO44
  (U0RXD) is the NFC chip select. Traboda's MicroPython keeps the REPL on the
  USB-Serial-JTAG only.
* **USB**: with TinyUSB (MicroPython's default on the S3) the badge sometimes stalled
  half-way through enumeration after a watchdog reset; the built-in USB-Serial-JTAG never
  did, and lets esptool reach the bootloader without pressing BOOT.
* **Resets through USB**: the USB-Serial-JTAG emulates the auto-reset circuit. DTR low
  with RTS high is reset, so a host must open the port with both lines high (pyserial's
  default on macOS) and lower RTS before DTR. After flashing, use
  `esptool --after watchdog-reset`: a reset through RTS latches the download strap and
  leaves the chip in the ROM bootloader.
* **NFC settings**: talk to the Ci522 at 1 MHz and leave RFCfgReg at its reset value (0x48,
  33 dB receiver gain), as the stock firmware does. With a tag held on the coil for 60 s,
  polls cycling through four settings read its UID 245 times out of 245 that way, 183 of
  244 at 4 MHz, and 10 and 8 of 244 with the gain at 48 dB (0x70) at either rate.
* **MCLK**: the ES8156 is driven with MCLK = 256 fs on GPIO10. MicroPython's
  `machine.I2S` has no MCLK pin on the ESP32 port; `firmware/patches/` adds it.
* **Flash layout** (`firmware/boards/TRABODA/partitions.csv`): the stock firmware's app
  partitions are kept at the same offsets, so Retro-Go (`launcher`, `retro-core`,
  `prboom-go`) survives a Traboda flash. Retro-Go formats a FAT partition labelled `data`
  when there is no SD card, so Traboda's filesystem is labelled `vfs`.
* The AW9523B powers up with every pin an output driving low; a software reset (0x7F)
  returns it to that state, not to "all inputs". Traboda soft-resets it at every boot (it
  keeps its state across ESP32 resets) and reads its inputs with single-byte reads.
* **Deep sleep**: the expander's INTN (GPIO8, open drain, no external pull-up) is the wake
  source (ext0, low). `firmware/patches/0002-esp32-ext0-wake-pull.patch` gives the pad an
  RTC pull-up once it moves to the RTC mux; the pad must not be held. Do not wake on GPIO0:
  it is the BOOT strap, so waking with "next" still down lands in the ROM bootloader. A
  backlight pin held low through deep sleep stays held after the wake until released.
