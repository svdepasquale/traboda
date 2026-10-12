import vfs
from flashbdev import bdev

MAIN_PY = """\
# Traboda OS starts here. Hold B while powering on to stay at the REPL instead.
import traboda
traboda.main()
"""


def check_bootsec():
    buf = bytearray(bdev.ioctl(5, 0))  # 5 is SEC_SIZE
    bdev.readblocks(0, buf)
    for b in buf:
        if b != 0xFF:
            fs_corrupted()
    return True


def fs_corrupted():
    import time
    import micropython

    micropython.kbd_intr(3)
    while 1:
        print(
            "The filesystem is corrupted. Reflash with: tools/flash.py --erase-fs\n"
            "(that keeps Retro-Go, erases only Traboda's 'vfs' partition)."
        )
        time.sleep(3)


def setup():
    check_bootsec()
    print("Traboda: formatting the internal filesystem")
    vfs.VfsLfs2.mkfs(bdev)
    fs = vfs.VfsLfs2(bdev)
    vfs.mount(fs, "/")
    with open("main.py", "w") as f:
        f.write(MAIN_PY)
    return fs
