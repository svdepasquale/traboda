"""Fake BLE: a scan delivers a handful of advertisements, then SCAN_DONE."""

_IRQ_SCAN_RESULT = 5
_IRQ_SCAN_DONE = 6

_ADS = (
    (0, b"\xaa\x01\x02\x03\x04\x05", 0, -45, b"\x02\x01\x06\x0b\x09MacBook Pro\x05\xff\x4c\x00\x10\x05"),
    (1, b"\xbb\x01\x02\x03\x04\x05", 0, -63, b"\x02\x01\x06\x07\x09Pixel 9\x03\x03\x9f\xfe"),
    (1, b"\xcc\x01\x02\x03\x04\x05", 3, -71, b"\x1a\xff\x4c\x00\x02\x15" + bytes(21)),
    (0, b"\xdd\x01\x02\x03\x04\x05", 0, -80, b"\x02\x01\x06\x09\x09Mi Band 8"),
    (0, b"\xee\x01\x02\x03\x04\x05", 0, -58, b"\x02\x01\x06\x0a\x09TRABODA-7\x05\xff\xff\xff\x54\x42"),
)


class UUID:
    def __init__(self, v):
        self.v = v


FLAG_READ = 2
FLAG_WRITE = 8
FLAG_NOTIFY = 16


class BLE:
    def __init__(self):
        self._active = False
        self._irq = None

    def active(self, v=None):
        if v is None:
            return self._active
        self._active = v

    def irq(self, handler):
        self._irq = handler

    def config(self, *a, **k):
        if a and a[0] == "mac":
            return (0, b"\x14\xc1\x9f\xc4\x3d\x4e")
        return None

    def gap_scan(self, duration_ms, interval_us=None, window_us=None, active=False):
        if duration_ms is None or not self._irq:
            return
        for addr_type, addr, adv_type, rssi, adv in _ADS:
            self._irq(_IRQ_SCAN_RESULT, (addr_type, memoryview(addr), adv_type, rssi, memoryview(adv)))
        self._irq(_IRQ_SCAN_DONE, ())

    def gap_advertise(self, interval_us, adv_data=None, **k):
        pass

    def gatts_register_services(self, services):
        return tuple(tuple(range(len(s[1]))) for s in services)

    def gatts_write(self, *a):
        pass

    def gatts_notify(self, *a):
        pass
