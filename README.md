# Traboda OS

A companion and console firmware, written from scratch, for the **RomHack Camp 2026
badge**: the Walkman-shaped ESP32-S3 handheld handed out at
[RomHack Camp](https://badge.romhack.io) (Cyber Saiyan; the PCB carries the
**Traboda** brand on its back, hence the name).

Traboda OS is MicroPython 1.29 with a custom board definition and an OS in Python on
top: a launcher, a Walkman music player, games, an LED studio, an NFC tool, Wi-Fi and
Bluetooth tools, weather, a name-tag mode, a synth, and a dashboard fed by your Mac.
It keeps the badge's stock **Retro-Go** emulators in their own partitions and boots
into them from its launcher, so the badge stays a retro console too.

![Traboda OS screens: home, Walkman, games, clock, LED studio, NFC, synth, Wi-Fi, quick panel](docs/img/screens.png)

## The badge

| | |
|---|---|
| SoC | ESP32-S3 (2x Xtensa LX7 240 MHz), 16 MB flash, 8 MB octal PSRAM, Wi-Fi 4, BLE 5 |
| Screen | 2.4" 320x240 TFT (ILI9341) |
| Keys | D-pad, A, B, and Walkman transport keys (rewind, play, fast-forward) |
| Audio | ES8156 DAC: 3.5 mm stereo jack + mono speaker |
| Lights | 22 addressable RGB LEDs |
| Extras | 13.56 MHz NFC reader/writer (Ci522, PCB antenna), microSD, Qwiic/STEMMA QT port, LiPo + USB-C charging |

Pinout, quirks and what was measured on a real badge: [docs/hardware.md](docs/hardware.md).

## Features

| App | |
|---|---|
| Walkman | WAV player with a drawn, spinning cassette; library, shuffle/repeat, seek, LED VU meter. The transport keys control it from anywhere |
| Giochi | Snake, Blocchi (falling blocks), Mattoncini (breakout), 2048, Vola! (flappy), Memoria (Simon with the LEDs), Riflessi; best scores kept |
| Retro-Go | boots the stock emulators (NES, Game Boy/Color, Master System/Game Gear, PC Engine, Lynx, SNES, Doom); exiting Retro-Go comes back here |
| Luci | LED studio: effects, colours, brightness, speed, torch |
| Orologio | big clock, timer with the LED strip as progress, stopwatch, pomodoro |
| Badge | conference name tag with your nickname and a matching LED animation |
| Synth | seven-note instrument on the keys plus an 8-step sequencer on the LEDs |
| NFC | reads ISO 14443-A cards and tags (UID, type, NTAG/Ultralight NDEF, MIFARE Classic default keys), saves dumps, writes URL/text to NTAG stickers. Hold cards over the Cyber Saiyan logo, where the antenna coil is |
| Wi-Fi | scan, connect with an on-screen keyboard, saved networks, channel chart, NTP |
| Bluetooth | BLE scanner with vendors, a Geiger-style finder, and "Badge vicini" to spot other Traboda badges |
| Meteo | Open-Meteo forecast for Italian cities, cached offline |
| Companion | your Mac's CPU, RAM, battery and now-playing, pushed over USB by `tools/companion.py` (macOS) |
| File | browse the internal memory and the SD card, view, delete, play |
| Impostazioni | screen, audio, LEDs, time zone and manual clock, key test, system info, standby |

Quick panel (hold play) anywhere: volume, brightness, LEDs, speaker, standby.

### Keys

* **A** (upper right) opens/selects, **B** (lower right) goes back; holding A also goes
  back.
* **play** plays/pauses music from any app, **⏪**/**⏩** skip tracks; **holding play**
  opens the quick panel. Games use play as pause.
* Hold **B** while switching on to skip the OS and stay at the MicroPython REPL.

## Install on your badge

Everything runs from a copy of this repository on your computer (macOS, Linux or
Windows). No ESP-IDF and no GitHub account needed: the firmware comes from the
[latest release](https://github.com/svdepasquale/traboda/releases/latest).

### 1. Tools

[esptool](https://github.com/espressif/esptool) **5 or newer** and
[mpremote](https://docs.micropython.org/en/latest/reference/mpremote.html), as commands:

* **macOS**: `brew install esptool mpremote`
* **Linux**: `pipx install esptool` and `pipx install mpremote` (no pipx yet:
  `sudo apt install pipx && pipx ensurepath`, then open a new terminal). Not your distro's
  esptool package: Debian and Ubuntu ship 4.x, which `tools/flash.py` cannot drive. For the
  serial port, `sudo usermod -aG dialout $USER` (Arch: `uucp`) and log in again.
* **Windows**: `py -m pip install --user pipx`, `py -m pipx ensurepath`, open a new
  terminal, then `pipx install esptool` and `pipx install mpremote`. Type `py` wherever
  this page says `python3`.

`esptool version` must print v5 or later. Then get the repository and run every command
from its folder:

```sh
git clone https://github.com/svdepasquale/traboda
cd traboda
```

(or download the release's source zip and unpack it).

### 2. Back up your badge, once

Switch the badge on (slide switch on the side), plug it in with a **data** USB-C cable,
then:

```sh
python3 tools/flash.py --backup ../stock-badge.bin
```

It reads the whole 16 MB flash, stock firmware and your data, in a few minutes. Keep the
file: it is your way back. `flash.py` never overwrites an existing backup.

### 3. Flash

```sh
python3 tools/flash.py --download
```

This fetches the latest release, checks it against its `SHA256SUMS` and writes it; the
badge restarts into Traboda. On the first install it also erases the stock firmware's
internal storage, where Traboda keeps its own files: Tactility's settings and Wi-Fi, the
preloaded MP3s and Doom WAD, and Retro-Go saves made without a card (your backup has them).
Retro-Go itself stays, and the microSD card is never touched. `tools/flash.py` finds the
badge by its USB vendor id, so other boards plugged in are left alone.

### 4. First steps

* **Wi-Fi**: Wi-Fi app → Cerca reti → pick the network → type the password on the
  on-screen keyboard (D-pad moves, A types, B deletes, ⏩ shows it, ▶ confirms). It stays
  on the badge, and the clock sets itself once connected.
* **NFC**: hold cards over the Cyber Saiyan logo, where the antenna is.
* **Retro-Go**: games go on a FAT32 microSD card, in `roms/nes`, `roms/snes`, `roms/gb`,
  `roms/gbc`, `roms/sms`, `roms/gg`, `roms/col`, `roms/pce`, `roms/lnx` and `roms/gw`.
  For Doom, put the stock firmware's
  [doom1.wad.zip](https://github.com/cybersaiyanIT/rhc2026-badge/raw/HEAD/firmware/tactility/Data/data/roms/doom/doom1.wad.zip)
  in `roms/doom`.
* **Music**: see below.

### Update

```sh
git pull
python3 tools/flash.py --download
```

Settings, Wi-Fi networks and music stay.

### Back to stock

```sh
python3 tools/flash.py --restore ../stock-badge.bin --yes
```

No backup? The official stock image restores the same way: download
[firmware.bin](https://badge.romhack.io/firmware/firmware.bin) (16 MB) and run
`python3 tools/flash.py --restore firmware.bin --yes`, or use the web flasher on
[badge.romhack.io](https://badge.romhack.io). Only your own backup brings back your old
settings.

### If something goes wrong

* `badge not found`: switch it on, wake it from standby with any key, and use a data
  cable (a charge-only one shows no port at all).
* `esptool ... needs 5 or newer` or `esptool not found`: see Tools.
* The download fails (certificate errors are common with python.org's Python on macOS):
  download `bootloader.bin`, `partition-table.bin`, `traboda.bin` and `SHA256SUMS` from the
  [latest release](https://github.com/svdepasquale/traboda/releases/latest) into one
  folder and run `python3 tools/flash.py --dist that-folder`.
* esptool cannot connect: hold BOOT (on the back; ⏩ is the same pin), tap RESET, release
  BOOT and flash again. Do not hold ⏩ while switching on, or the badge waits in the
  bootloader.
* The screen stays dark after `done`: slide the switch off and on. If the badge still
  shows nothing new, flash again with `--erase-fs`, which starts the filesystem over.

## Music, Wi-Fi from the Mac, Mac companion

* **Music**: 16-bit PCM WAV files in a `music` folder on the SD card or in the internal
  memory (about 7 MB, under 3 minutes at the default 22050 Hz mono). If the card's
  `music` folder has any WAV, the Walkman plays only the card. A fresh install has no
  tracks: `python3 tools/chiptune.py demo` renders two original chiptunes into `demo/`;
  copy them into the card's `music` folder, or upload them with
  `python3 tools/music.py demo/*.wav`. `tools/music.py` converts anything ffmpeg reads
  (it needs ffmpeg, WAV included) and copies it over USB; `--sd FOLDER` writes to a card
  mounted on the computer instead.
* **Wi-Fi from the Mac**: `uv run tools/dev.py wifi "Network"` gives the badge a network
  the Mac knows; the password comes from the macOS keychain after a system prompt and is
  stored on the badge only.
* **Companion** (macOS): with the badge on USB, `uv run tools/companion.py` and open the
  Companion app; `--notify "text"` pops a notification on the badge. On Linux only the CPU
  load shows. `tools/companion.py` and `tools/dev.py` need pyserial, which `uv run`
  provides (or `pip install pyserial` in a virtualenv).

## Build from source

ESP-IDF v5.5.2 (`git clone -b v5.5.2 --recursive https://github.com/espressif/esp-idf
~/esp/esp-idf && ~/esp/esp-idf/install.sh esp32s3`), then `./firmware/build.sh`. It fetches
MicroPython 1.29.0, applies `firmware/patches/`, freezes `src/traboda` into the image and
writes `firmware/dist/{bootloader,partition-table,traboda}.bin` and `SHA256SUMS`;
`python3 tools/flash.py` then flashes them. CI does the same in the `espressif/idf:v5.5.2`
container.

## Development

* `docs/DEVELOPING.md`: the app contract and every API.
* `sim/`: the whole OS runs headless on the MicroPython unix port; `sim/run.py` drives
  it with scripted key presses and `sim/topng.py` turns snapshots into PNGs.
* `python3 tests/smoke.py`: compiles every module for the badge and walks every app in
  the simulator (needs `micropython` and `mpy-cross`: `brew install micropython`).
* `tools/dev.py sync` pushes `src/traboda` (as .mpy) onto a running badge, shadowing the
  frozen copy, and `tools/dev.py run` restarts the OS; `tools/dev.py clean` removes the
  copy, do it before flashing a new firmware or the old copy keeps running.
  `tools/dev.py snap shot.png` takes a screenshot of the real screen over USB,
  `tools/dev.py key right` presses a key.
* Releases: bump `VERSION` in `src/traboda/__init__.py`, commit, then
  `git tag vX.Y.Z && git push origin main vX.Y.Z`. CI builds the firmware, runs the smoke
  tests and publishes the release with the three images and `SHA256SUMS`; a tag that does
  not match `VERSION` fails the build.

## Credits

Badge hardware and stock firmware by [Cyber Saiyan](https://www.cybersaiyan.it)
([rhc2026-badge](https://github.com/cybersaiyanIT/rhc2026-badge)). Fonts: Spleen by
Frederic Cambus. Built on MicroPython and ESP-IDF; see [THIRD_PARTY.md](THIRD_PARTY.md).
Traboda OS is MIT licensed.
