#!/usr/bin/env bash
# Builds the Traboda firmware: MicroPython (pinned) + boards/TRABODA + the frozen OS in src/.
# Needs ESP-IDF v5.5.2 (IDF_PATH, default ~/esp/esp-idf). Artifacts land in firmware/dist/.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
MPY_VERSION="v1.29.0"
MPY_DIR="${MPY_DIR:-$HERE/.build/micropython}"
IDF_PATH="${IDF_PATH:-$HOME/esp/esp-idf}"
BOARD_DIR="$HERE/boards/TRABODA"
BUILD="$MPY_DIR/ports/esp32/build-TRABODA"

if [ ! -d "$MPY_DIR/.git" ]; then
    git clone --depth 1 -b "$MPY_VERSION" https://github.com/micropython/micropython.git "$MPY_DIR"
fi

# Patches are applied once; a patch that is already in reverses cleanly and is skipped.
for patch in "$HERE"/patches/*.patch; do
    if git -C "$MPY_DIR" apply --check "$patch" 2>/dev/null; then
        git -C "$MPY_DIR" apply "$patch"
        echo "applied $(basename "$patch")"
    elif ! git -C "$MPY_DIR" apply --reverse --check "$patch" 2>/dev/null; then
        echo "error: $(basename "$patch") does not apply to MicroPython $MPY_VERSION" >&2
        exit 1
    fi
done

cp "$BOARD_DIR/partitions.csv" "$MPY_DIR/ports/esp32/partitions-traboda.csv"

# export.sh looks for a Python venv named after the current python3; after a Homebrew
# Python upgrade that is not the one install.sh created, so point it at an existing one.
if [ -z "${IDF_PYTHON_ENV_PATH:-}" ]; then
    for env in "$HOME"/.espressif/python_env/idf5.5_py*_env; do
        if [ -x "$env/bin/python" ]; then
            export IDF_PYTHON_ENV_PATH="$env"
        fi
    done
fi
# shellcheck disable=SC1091
source "$IDF_PATH/export.sh" >/dev/null

make -C "$MPY_DIR/mpy-cross" -j"$(getconf _NPROCESSORS_ONLN)"
make -C "$MPY_DIR/ports/esp32" BOARD_DIR="$BOARD_DIR" submodules
make -C "$MPY_DIR/ports/esp32" BOARD_DIR="$BOARD_DIR" -j"$(getconf _NPROCESSORS_ONLN)"

mkdir -p "$HERE/dist"
cp "$BUILD/bootloader/bootloader.bin" "$HERE/dist/bootloader.bin"
cp "$BUILD/partition_table/partition-table.bin" "$HERE/dist/partition-table.bin"
cp "$BUILD/micropython.bin" "$HERE/dist/traboda.bin"
# tools/flash.py checks the images against this file when it is there (a release has one).
(cd "$HERE/dist" && if command -v sha256sum >/dev/null; then sha256sum *.bin; else shasum -a 256 *.bin; fi > SHA256SUMS)
ls -l "$HERE/dist"
