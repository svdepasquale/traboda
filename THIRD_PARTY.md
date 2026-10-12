# Third-party components

| Component | Where | License |
|---|---|---|
| [MicroPython](https://github.com/micropython/micropython) 1.29.0 | fetched by `firmware/build.sh`, built into the firmware; `firmware/patches/` modifies `ports/esp32/machine_i2s.c` | MIT |
| [ESP-IDF](https://github.com/espressif/esp-idf) 5.5.2 | build toolchain, linked into the firmware | Apache-2.0 |
| [Spleen](https://github.com/fcambus/spleen) 2.2.0 by Frederic Cambus | `assets/fonts/*.bdf`, converted into `src/traboda/fonts/` | BSD-2-Clause (`assets/fonts/LICENSE-spleen`) |
| ES8156 register sequence | `src/traboda/audio.py`, from Espressif's esp_codec_dev | Apache-2.0 |
| ILI9341 panel init values | `src/traboda/display.py`, from the badge's Retro-Go port | GPL-2.0 project; the values are hardware parameters |

Retro-Go (GPL-2.0) is not part of this repository: it stays on the badge from the stock
firmware, in its own partitions, and Traboda only switches to it.
