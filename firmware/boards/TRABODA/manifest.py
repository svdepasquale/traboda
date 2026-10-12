# The port's own modules, minus the two this board replaces (_boot.py, inisetup.py).
for name in ("apa106.py", "espnow.py", "flashbdev.py", "machine.py"):
    module(name, base_path="$(PORT_DIR)/modules")
freeze("$(BOARD_DIR)/modules")

include("$(MPY_DIR)/extmod/asyncio")
require("bundle-networking")
require("aioble")
require("neopixel")

# Traboda OS itself: frozen so a fresh flash boots straight into it. A copy of any
# module placed in the filesystem root shadows the frozen one ("" precedes ".frozen").
package("traboda", base_path="$(BOARD_DIR)/../../../src")
