"""A fake MFRC522 for the simulator: one card always on the reader, chosen by kind.

nfc.py picks this up when TRABODA_NFC_FAKE is set (ntag215 | mclassic), so the result,
NDEF, sector-dump and write screens can be exercised without hardware (real SPI reads
zero in the sim, i.e. no card). The page store persists writes so verify-after-write
passes.
"""


def _ntag215_pages():
    uri = b"\x91\x01\x0f\x55\x04" + b"romhackcamp.it"          # URI record, https:// prefix
    text = b"\x51\x01\x0c\x54\x02it" + b"Ciao RHC!"            # Text record, lang "it"
    msg = uri + text
    tlv = b"\x03" + bytes((len(msg),)) + msg + b"\xfe"
    tlv += bytes((4 - len(tlv) % 4) % 4)
    pages = {
        0: b"\x04\x51\x7a\xd1",                                # uid0-2 + BCC0
        1: b"\x2a\x6c\x3d\x80",                                # uid3-6
        2: b"\x48\x00\x00\x00",                                # internal + lock bytes
        3: b"\xe1\x10\x3e\x00",                                # CC: NTAG215, NDEF-capable
    }
    for i in range(0, len(tlv), 4):
        pages[4 + i // 4] = tlv[i:i + 4]
    return pages


def _classic_block0():
    uid = b"\xde\xad\xbe\xef"
    bcc = uid[0] ^ uid[1] ^ uid[2] ^ uid[3]
    return uid + bytes((bcc, 0x08, 0x04, 0x00)) + b"TRABODA!"


class FakeReader:
    def __init__(self, kind="ntag215"):
        self.kind = kind
        self._sector = None
        if kind == "mclassic":
            self.uid = b"\xde\xad\xbe\xef"
            self.sak = 0x08
            self.atqa = b"\x04\x00"
            self.block0 = _classic_block0()
        else:
            self.uid = b"\x04\x51\x7a\x2a\x6c\x3d\x80"
            self.sak = 0x00
            self.atqa = b"\x44\x00"
            self.pages = _ntag215_pages()

    def init(self):
        return 0x92

    def version(self):
        return 0x92

    def request(self, cmd=0x52):
        return bytearray(self.atqa)

    def select(self):
        return bytes(self.uid), self.sak

    def halt(self):
        self._sector = None

    def get_version(self):
        if self.kind == "mclassic":
            return None
        return b"\x00\x04\x04\x02\x01\x00\x11\x03"

    def auth(self, mode, block, key, uid):
        sector = block // 4
        ok = (key == b"\xff\xff\xff\xff\xff\xff" and sector < 8) or \
             (key == b"\xa0\xa1\xa2\xa3\xa4\xa5" and 8 <= sector < 12)
        self._sector = sector if ok else None
        return ok

    def stop_crypto(self):
        self._sector = None

    def read_block(self, block):
        if self.kind == "mclassic":
            if self._sector is None or block // 4 != self._sector:
                return None
            return self.block0 if block == 0 else bytes(16)
        out = bytearray()
        for p in range(block, block + 4):
            out += self.pages.get(p, b"\x00\x00\x00\x00")
        return bytes(out)

    def ul_write(self, page, data):
        if self.kind == "mclassic":
            return False
        self.pages[page] = bytes(data[:4])
        return True
