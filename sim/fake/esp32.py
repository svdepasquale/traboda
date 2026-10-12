"""Fake esp32 module: partitions as on the badge, sleep wake sources."""

WAKEUP_ALL_LOW = False
WAKEUP_ANY_HIGH = True
HEAP_DATA = 0
HEAP_EXEC = 1


class Partition:
    BOOT = 0
    RUNNING = 1
    TYPE_APP = 0
    TYPE_DATA = 1
    _table = (
        (0, 0, 0x10000, 0x400000, "factory"), (0, 16, 0x410000, 0x120000, "launcher"),
        (0, 17, 0x530000, 0x120000, "retro-core"), (0, 18, 0x650000, 0xF0000, "prboom-go"),
        (1, 2, 0x9000, 0x6000, "nvs"), (1, 0, 0x740000, 0x2000, "otadata"),
        (1, 129, 0x742000, 0x200000, "data"), (1, 129, 0x942000, 0x6BE000, "vfs"),
    )
    booted = "factory"
    next_boot = None

    def __init__(self, id):
        if id in (0, 1):
            id = Partition.booted
        self._info = [p for p in self._table if p[4] == id][0]

    def info(self):
        return self._info + (False,)

    @classmethod
    def find(cls, type=0, subtype=255, label=None):
        out = []
        for p in cls._table:
            if p[0] == type and (label is None or p[4] == label):
                out.append(cls(p[4]))
        return out

    def set_boot(self):
        Partition.next_boot = self._info[4]

    def get_next_update(self):
        return self


def wake_on_ext0(pin, level):
    pass


def wake_on_ext1(pins, level):
    pass


def gpio_deep_sleep_hold(enable):
    pass


def idf_heap_info(cap):
    return [(8 * 1024 * 1024, 7 * 1024 * 1024, 4 * 1024 * 1024, 6 * 1024 * 1024)]


class NVS:
    def __init__(self, ns):
        self.d = {}

    def get_i32(self, k):
        return self.d[k]

    def set_i32(self, k, v):
        self.d[k] = v

    def commit(self):
        pass
