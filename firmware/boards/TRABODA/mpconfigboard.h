// RomHack Camp 2026 badge ("Traboda" on the PCB): ESP32-S3-WROOM-1 N16R8.
// Pinout: https://github.com/cybersaiyanIT/rhc2026-badge (hardware/SCHEMATIC.pdf).

#define MICROPY_HW_BOARD_NAME               "Traboda Badge"
#define MICROPY_HW_MCU_NAME                 "ESP32S3"

// GPIO43 (U0TXD) is the codec's I2S BCLK and GPIO44 (U0RXD) is the RFID chip select,
// so there is no UART REPL.
#define MICROPY_HW_ENABLE_UART_REPL         (0)

// The REPL runs on the built-in USB-Serial-JTAG rather than TinyUSB: it survives resets
// without re-enumerating and lets esptool reach the bootloader without pressing BOOT.
#define MICROPY_HW_ENABLE_USBDEV            (0)

// Internal I2C: AW9523B GPIO expander (0x58) and ES8156 DAC (0x08).
#define MICROPY_HW_I2C0_SCL                 (16)
#define MICROPY_HW_I2C0_SDA                 (17)

// SPI2 (FSPI) on its IO_MUX pins, shared by the ILI9341 (CS 15) and the Ci522 (CS 44).
#define MICROPY_HW_SPI1_SCK                 (12)
#define MICROPY_HW_SPI1_MOSI                (11)
#define MICROPY_HW_SPI1_MISO                (13)

// The ES8156 wants a master clock on GPIO10 (patches/0001-esp32-i2s-mck.patch).
#define MICROPY_PY_MACHINE_I2S_MCK          (1)

// The expander's INTN wakes the badge from deep sleep (ext0, active low) and has no
// external pull-up (patches/0002-esp32-ext0-wake-pull.patch).
#define MICROPY_HW_SLEEP_WAKE_PULL          (1)
