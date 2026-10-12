"""NFC: read a card held to the reader, show what it is, dump NDEF / sectors, write
NTAG/Ultralight tags and keep an archive of dumps on the badge.

The reader lives on the display's SPI bus and is held in power-down until the app runs
(power.rfid). The idle screen polls a few times a second, yielding between polls so the
UI stays live and back works, and parks the reader (power.rfid off) while the screen
sleeps so a dark badge neither keeps the RF field up nor reads cards. READER_FACTORY
lets the simulator inject a fake reader.
"""

import asyncio

from .. import buttons as B
from .. import gfx, icons, paths, settings, ui
from ..mfrc522 import AUTH_A

TITLE = "NFC"
ICON = "nfc"
MEDIA_KEYS = False

READER_FACTORY = None          # sim/tests may set this to a callable(sys) -> reader

_KEYS = (b"\xff\xff\xff\xff\xff\xff", b"\xa0\xa1\xa2\xa3\xa4\xa5",
         b"\xd3\xf7\xd3\xf7\xd3\xf7", b"\x00\x00\x00\x00\x00\x00")

# NFC Forum URI identifier codes (index = first payload byte of a URI record)
URI_PREFIXES = (
    "", "http://www.", "https://www.", "http://", "https://", "tel:", "mailto:",
    "ftp://anonymous:anonymous@", "ftp://ftp.", "ftps://", "sftp://", "smb://", "nfs://",
    "ftp://", "dav://", "news:", "telnet://", "imap:", "rtsp://", "urn:", "pop:", "sip:",
    "sips:", "tftp:", "btspp://", "btl2cap://", "btgoep://", "tcpobex://", "irdaobex://",
    "file://", "urn:epc:id:", "urn:epc:tag:", "urn:epc:pat:", "urn:epc:raw:", "urn:epc:",
    "urn:nfc:",
)


# -- reader --------------------------------------------------------------------------------

def _open_reader(sys):
    if READER_FACTORY is not None:
        return READER_FACTORY(sys)
    import sys as _sys
    if _sys.platform != "esp32":
        import os
        kind = os.getenv("TRABODA_NFC_FAKE")
        if kind:
            import nfc_fake
            return nfc_fake.FakeReader(kind)
    from .. import board
    from ..mfrc522 import MFRC522
    reader = MFRC522(board.spi(), board.RFID_CS)
    reader.init()
    return reader


def _poll(reader):
    """One detection cycle. Returns (uid, sak, atqa); uid is None when unreadable, and
    the whole result is None when no card answers."""
    atqa = reader.request()
    if atqa is None:
        return None
    res = reader.select()
    if res is None:
        return (None, 0, atqa)
    return (res[0], res[1], atqa)


def _beep_flash(sys):
    try:
        sys.audio.melody(((1568, 50), (2093, 80)), 0.2)
    except Exception:  # noqa: BLE001 - sound is a nicety
        pass
    if sys.leds:
        sys.leds.flash((45, 226, 230), 500, 120)


# -- NDEF ----------------------------------------------------------------------------------

def _hex(data, sep):
    if not data:
        return ""
    return sep.join("%02X" % x for x in data)


def _spaced(h):
    return " ".join(h[i:i + 2] for i in range(0, len(h), 2))


def _dec(data):
    try:
        return bytes(data).decode("utf-8")
    except Exception:  # noqa: BLE001 - show raw-ish on bad encodings
        return "".join(chr(c) if 32 <= c < 127 else "." for c in data)


def ndef_message(user):
    """The NDEF message bytes inside a TLV area, or b"" when there is none."""
    i = 0
    n = len(user)
    while i < n:
        t = user[i]
        if t == 0x00:
            i += 1
            continue
        if t == 0xFE or i + 1 >= n:
            break
        length = user[i + 1]
        j = i + 2
        if length == 0xFF:
            if i + 3 >= n:
                break
            length = user[i + 2] << 8 | user[i + 3]
            j = i + 4
        if t == 0x03:
            return bytes(user[j:j + length])
        i = j + length
    return b""


def ndef_records(msg):
    """[(tnf, type_bytes, payload_bytes), ...] parsed from an NDEF message."""
    recs = []
    i = 0
    n = len(msg)
    while i < n:
        hdr = msg[i]
        i += 1
        if i >= n:
            break
        tlen = msg[i]
        i += 1
        if hdr & 0x10:                       # short record
            if i >= n:
                break
            plen = msg[i]
            i += 1
        else:
            if i + 3 >= n:
                break
            plen = msg[i] << 24 | msg[i + 1] << 16 | msg[i + 2] << 8 | msg[i + 3]
            i += 4
        ilen = 0
        if hdr & 0x08:                       # ID present
            if i >= n:
                break
            ilen = msg[i]
            i += 1
        rtype = bytes(msg[i:i + tlen])
        i += tlen + ilen
        payload = bytes(msg[i:i + plen])
        i += plen
        recs.append((hdr & 0x07, rtype, payload))
        if hdr & 0x40:                       # message end
            break
    return recs


def describe_record(rec):
    tnf, rtype, payload = rec
    if tnf == 1 and rtype == b"U" and payload:
        p = payload[0]
        pre = URI_PREFIXES[p] if p < len(URI_PREFIXES) else ""
        return ["URL", pre + _dec(payload[1:])]
    if tnf == 1 and rtype == b"T" and payload:
        st = payload[0]
        llen = st & 0x3F
        lang = _dec(payload[1:1 + llen])
        txt = "(UTF-16)" if st & 0x80 else _dec(payload[1 + llen:])
        return ["Testo", "[" + lang + "] " + txt]
    label = _dec(rtype) if rtype else "?"
    return [label or "?", _dec(payload)]


def _record(rtype, payload):
    return bytes((0xD1, len(rtype), len(payload))) + rtype + payload   # MB|ME|SR, TNF=1


def ndef_uri(url):
    code = 0
    best = 0
    for i in range(1, len(URI_PREFIXES)):
        pre = URI_PREFIXES[i]
        if pre and url.startswith(pre) and len(pre) > best:
            code = i
            best = len(pre)
    return _record(b"U", bytes((code,)) + url[best:].encode("utf-8"))


def ndef_text(text, lang="it"):
    lb = lang.encode("ascii")
    return _record(b"T", bytes((len(lb) & 0x3F,)) + lb + text.encode("utf-8"))


def ndef_tlv(msg):
    if len(msg) < 0xFF:
        tlv = bytes((0x03, len(msg))) + msg + b"\xfe"
    else:
        tlv = bytes((0x03, 0xFF, len(msg) >> 8, len(msg) & 0xFF)) + msg + b"\xfe"
    return tlv + bytes((4 - len(tlv) % 4) % 4)


# -- type + reading ------------------------------------------------------------------------

def guess_type(sak, gv):
    if sak & 0x20:
        return "ISO 14443-4", "carta bancaria o trasporti", "isodep"
    if sak == 0x00:
        if gv and len(gv) >= 7 and gv[2] == 0x04:
            name = {0x0F: "NTAG213", 0x11: "NTAG215", 0x13: "NTAG216"}.get(gv[6], "NTAG")
            return name, "tag NFC riscrivibile", "ntag"
        if gv and len(gv) >= 3 and gv[2] == 0x03:
            return "Ultralight EV1", "tag NFC riscrivibile", "ul"
        return "Ultralight", "tag NFC riscrivibile", "ul"
    if sak == 0x09:
        return "MIFARE Mini", "tessera MIFARE", "classic"
    if sak == 0x08:
        return "MIFARE Classic 1K", "tessera MIFARE", "classic"
    if sak == 0x18:
        return "MIFARE Classic 4K", "tessera MIFARE", "classic"
    if sak in (0x10, 0x11):
        return "MIFARE Plus", "tessera MIFARE", "classic"
    return "Sconosciuta", "tipo non riconosciuto", "unknown"


def _dump_rows(raw, start, count):
    rows = []
    for p in range(start, start + count):
        off = p * 4
        if off + 4 > len(raw):
            break
        rows.append("P%02d %s" % (p, _hex(raw[off:off + 4], " ")))
    return rows


async def _read_ntag(sys, reader):
    raw = bytearray()
    head = reader.read_block(0)
    if head is None:
        return raw, 0
    raw += head
    cc = raw[12:16]
    size = cc[2] * 8 if cc[0] == 0xE1 else 48
    limit = min(16 + size, 256)
    page = 4
    while len(raw) < limit:
        block = reader.read_block(page)
        if block is None:
            break
        raw += block
        page += 4
        if raw.find(b"\xfe", 16) >= 0:
            break
        await sys.sleep_ms(2)
    return raw, size


async def _read_classic(sys, reader, uid):
    ui.header(sys, "MIFARE", "nfc")
    gfx.text("Lettura settori", 160, 92, ui.CYAN, "title", align=1)
    ui.footer([("A tieni", "Indietro")])
    sys.show()
    reader.halt()                      # the card is ACTIVE from _poll: halt so WUPA can re-select
    opened = []
    key0 = None
    for sector in range(16):
        trailer = sector * 4 + 3
        found = None
        for key in _KEYS:
            if reader.request() is None or reader.select() is None:
                break
            if reader.auth(AUTH_A, trailer, key, uid):
                found = key
                reader.halt()          # HLTA (encrypted while crypto is on) drops the card to HALT
                break
            reader.halt()
            await asyncio.sleep_ms(0)  # yield: a wrong-key auth waits the chip's ~15 ms timer
        opened.append(found is not None)
        if sector == 0 and found is not None:
            key0 = found
        gfx.bar(40, 140, 240, 14, (sector + 1) / 16.0, ui.ACCENT, ui.PANEL, 4)
        sys.show(140, 154)
        await sys.sleep_ms(1)
    block0 = None
    if key0 is not None and reader.request() and reader.select():
        if reader.auth(AUTH_A, 0, key0, uid):
            block0 = reader.read_block(0)
            reader.halt()
    return opened, block0


async def read_card(sys, reader, uid, sak, atqa):
    gv = reader.get_version() if sak == 0x00 else None
    title, desc, kind = guess_type(sak, gv)
    info = {"uid": _hex(uid, ""), "sak": sak, "atqa": atqa[0] | atqa[1] << 8,
            "title": title, "desc": desc, "kind": kind}
    if gv:
        info["ver"] = _hex(gv, "")
    if kind in ("ntag", "ul"):
        _draw_loading(sys, "Lettura dati")
        reader.halt()                  # GET_VERSION leaves the tag ACTIVE or muted: re-activate
        reader.request()
        reader.select()
        raw, size = await _read_ntag(sys, reader)
        info["size"] = size
        info["records"] = [describe_record(r) for r in ndef_records(ndef_message(raw[16:]))]
        info["dump"] = _dump_rows(raw, 4, 6)
    elif kind == "classic":
        opened, block0 = await _read_classic(sys, reader, uid)
        info["sectors"] = opened
        info["block0"] = _hex(block0, "") if block0 else None
    return info


# -- drawing -------------------------------------------------------------------------------

def _draw_loading(sys, msg):
    ui.header(sys, "NFC", "nfc")
    gfx.text(msg, 160, 110, ui.CYAN, "title", align=1)
    ui.footer([("A tieni", "Indietro")])
    sys.show()


def draw_body(sys, info):
    kind = info.get("kind", "unknown")
    gfx.text(gfx.ellipsize(info.get("desc", ""), 300), 10, 54, ui.DIM)
    gfx.text("UID", 10, 72, ui.DIM)
    gfx.text(gfx.ellipsize(_spaced(info.get("uid", "")), 264), 46, 72, ui.CYAN)
    gfx.text("SAK 0x%02X    ATQA 0x%04X" % (info.get("sak", 0), info.get("atqa", 0)),
             10, 94, ui.DIM, "small")
    gfx.hline(10, 108, 300, ui.LINE)
    if kind in ("ntag", "ul"):
        _draw_ndef(info)
    elif kind == "classic":
        _draw_classic(info)
    else:
        y = 122
        for ln in gfx.wrap("Questo tipo non espone dati leggibili dal badge.", 300)[:4]:
            gfx.text(ln, 10, y, ui.DIM)
            y += 16


def _draw_ndef(info):
    gfx.text("NDEF", 10, 114, ui.ACCENT, "small")
    if info.get("size"):
        gfx.text("%d byte" % info["size"], 310, 114, ui.DIM, "small", align=-1)
    recs = info.get("records") or []
    if not recs:
        gfx.text("Nessun record NDEF", 10, 130, ui.DIM)
        y = 150
        for row in info.get("dump", [])[:4]:
            gfx.text(row, 10, y, ui.DIM, "small")
            y += 12
        return
    y = 128
    for idx in range(len(recs)):
        if y > 196:
            gfx.text("...", 10, y, ui.DIM, "small")
            break
        label, value = recs[idx][0], recs[idx][1]
        gfx.text(label, 10, y, ui.YELLOW, "small")
        yy = y + 12
        for ln in gfx.wrap(value, 300)[:2 if idx == 0 else 1]:
            gfx.text(ln, 10, yy, ui.TEXT)
            yy += 16
        y = yy + 4


def _draw_classic(info):
    opened = info.get("sectors") or []
    n_open = 0
    for o in opened:
        if o:
            n_open += 1
    gfx.text("Settori aperti %d/%d" % (n_open, len(opened)), 10, 114, ui.ACCENT, "small")
    cw = 36
    for i in range(len(opened)):
        cx = 12 + (i % 8) * cw
        cy = 128 + (i // 8) * 24
        gfx.round_rect(cx, cy, cw - 4, 20, 4, ui.GREEN if opened[i] else ui.PANEL2)
        gfx.text("%d" % i, cx + (cw - 4) // 2, cy + 3, ui.BLACK if opened[i] else ui.DIM,
                 "small", align=1)
    block0 = info.get("block0")
    if block0:
        gfx.text("Blocco 0 (produttore)", 10, 182, ui.DIM, "small")
        gfx.text(_spaced(block0), 10, 196, ui.TEXT, "small")
    else:
        gfx.text("Blocco 0 non leggibile", 10, 182, ui.DIM, "small")


# -- idle screen ---------------------------------------------------------------------------

def _draw_idle_static(sys, reader):
    ui.header(sys, "NFC", "nfc")
    gfx.text("Avvicina una tessera", 160, 162, ui.TEXT, "title", align=1)
    sub = "lettore sul retro del badge"
    if reader is None:
        sub = "lettore non disponibile"
    gfx.text(sub, 160, 192, ui.DIM, align=1)
    ui.footer([("A", "Archivio"), ("A tieni", "Indietro")])


def _draw_ring(sys, frame):
    gfx.fill_rect(0, 46, 320, 110, ui.BG)   # leaves the header accent bar (y 44-45) intact
    cx, cy = 160, 100
    for i in range(3):
        r = 22 + ((frame * 2 + i * 10) % 30)
        gfx.circle(cx, cy, r, ui.CYAN if r < 40 else ui.LINE)
    icons.draw(gfx.fb, "nfc", cx - 24, cy - 24, 3)
    sys.show(46, 156)


async def _idle_loop(sys, reader):
    last_uid = None
    empty = 0
    frame = 0
    full = True
    powered = reader is not None
    while True:
        if not sys.screen_on:               # screen asleep: drop the RF field, stop polling
            if powered:
                try:
                    sys.power.rfid(False)
                except Exception:  # noqa: BLE001
                    pass
                powered = False
            ev = await sys.event(timeout_ms=500)
            if ev is not None and sys.is_back(ev):
                return
            full = True                     # redraw once the screen comes back
            continue
        if reader is not None and not powered:   # woke up: bring the reader back
            try:
                sys.power.rfid(True)
                reader.init()
                powered = True
            except Exception:  # noqa: BLE001
                powered = False
            last_uid = None
            empty = 0
        if full:
            _draw_idle_static(sys, reader)
            sys.show()
            full = False
        _draw_ring(sys, frame)
        frame += 1
        if reader is not None and powered:
            card = _poll(reader)
            if card is None:
                empty += 1
                if empty >= 3:
                    last_uid = None
            elif card[0] is not None:
                uid, sak, atqa = card
                empty = 0
                if uid == last_uid:
                    reader.halt()
                else:
                    _beep_flash(sys)
                    info = await read_card(sys, reader, uid, sak, atqa)
                    reader.halt()
                    if await result_screen(sys, reader, info):
                        return
                    last_uid = uid
                    full = True
                    continue
        ev = await sys.event(timeout_ms=130)
        if ev is None:
            continue
        k, knd = B.key(ev), B.kind(ev)
        if knd == sys.REDRAW:
            full = True
        elif sys.is_back(ev):
            return
        elif k == B.A and knd == B.CLICK:
            if await archive(sys):
                return
            full = True


# -- result + actions ----------------------------------------------------------------------

async def result_screen(sys, reader, info):
    """Returns True when HOME asked to leave the app, else None (one level back)."""
    writable = info["kind"] in ("ntag", "ul")
    while True:
        ui.header(sys, info["title"], "nfc")
        draw_body(sys, info)
        ui.footer([("A", "Azioni"), ("A tieni", "Indietro")])
        sys.show()
        ev = await sys.event()
        if ev is None:
            continue
        k, knd = B.key(ev), B.kind(ev)
        if knd == sys.REDRAW:
            continue
        if sys.is_back(ev):
            return knd == sys.HOME
        if k == B.A and knd == B.CLICK:
            if await _actions(sys, reader, info, writable):
                return True


async def _actions(sys, reader, info, writable):
    items = [ui.Item("Salva su badge", None, "files", tag="save")]
    if writable:
        items.append(ui.Item("Scrivi URL", None, "nfc", tag="url"))
        items.append(ui.Item("Scrivi testo", None, "nfc", tag="text"))
    items.append(ui.Item("Apri archivio", None, "files", tag="arch"))
    it = await ui.menu(sys, "Azioni", items, icon="settings",
                       hints=[("A", "Scegli"), ("A tieni", "Indietro")], accent=ui.CYAN)
    if it is None:
        return
    if it.tag == "save":
        try:
            save_dump(info)
            await ui.toast(sys, "Salvato in archivio", 1200, ui.GREEN)
        except Exception as e:  # noqa: BLE001 - surface a write failure
            await ui.dialog(sys, "Errore", "Salvataggio fallito: " + str(e))
    elif it.tag == "url":
        await write_flow(sys, reader, info, ndef_uri, "URL", "https://")
    elif it.tag == "text":
        await write_flow(sys, reader, info, ndef_text, "Testo", "")
    elif it.tag == "arch":
        return await archive(sys)


# -- write ---------------------------------------------------------------------------------

async def write_flow(sys, reader, info, make_record, prompt, default):
    if info["kind"] not in ("ntag", "ul"):          # never write Classic or unknown tags
        await ui.dialog(sys, "Errore", "Questa tessera non è scrivibile.")
        return
    text = await ui.keyboard(sys, prompt, default)
    if not text:
        return
    if await ui.dialog(sys, "Conferma", "Sovrascrivo la tessera con:\n" + text,
                       ("Scrivi", "Annulla")) != 0:
        return
    _draw_loading(sys, "Scrittura")
    if reader.request() is None:
        await ui.dialog(sys, "Errore", "Tessera rimossa dal lettore.")
        return
    res = reader.select()
    if res is None or res[1] != 0x00:
        await ui.dialog(sys, "Errore", "Tessera non più scrivibile.")
        return
    data = ndef_tlv(make_record(text))
    head = reader.read_block(0)
    cc = head[12:16] if head else bytes(4)
    ok = True
    page = 4
    for off in range(0, len(data), 4):
        chunk = data[off:off + 4]
        if len(chunk) < 4:
            chunk = chunk + bytes(4 - len(chunk))
        if not reader.ul_write(page, chunk):
            ok = False
            break
        page += 1
        await sys.sleep_ms(3)
    if ok and cc[0] == 0x00:                         # blank tag: make it NDEF-capable
        reader.ul_write(3, b"\xe1\x10\x12\x00")
    recs = await _verify(sys, reader, text) if ok else None
    reader.halt()
    if recs is not None:
        info["records"] = [describe_record(r) for r in recs]
        await ui.toast(sys, "Scritto e verificato ✓", 1300, ui.GREEN)
    else:
        await ui.dialog(sys, "Errore", "Scrittura non riuscita o non verificata.")


async def _verify(sys, reader, text):
    """Re-read the tag and return the records when the first one contains text, else None."""
    reader.halt()                       # the tag is ACTIVE after the writes: halt so WUPA re-selects
    if reader.request() is None or reader.select() is None:
        return None
    raw = bytearray()
    page = 4
    while len(raw) < 240:
        block = reader.read_block(page)
        if block is None:
            break
        raw += block
        page += 4
        if raw.find(b"\xfe") >= 0:
            break
        await sys.sleep_ms(2)
    recs = ndef_records(ndef_message(raw))
    if recs and text in describe_record(recs[0])[1]:
        return recs
    return None


# -- archive -------------------------------------------------------------------------------

def save_dump(info):
    import json
    import os
    folder = paths.data("nfc")
    try:
        os.mkdir(folder)
    except OSError:
        pass
    path = paths.data("nfc/" + info["uid"] + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(info, f)
    try:
        os.remove(path)
    except OSError:
        pass
    os.rename(tmp, path)
    return path


async def archive(sys):
    import json
    import os
    folder = paths.data("nfc")
    while True:
        try:
            names = [n for n in sorted(os.listdir(folder)) if n.endswith(".json")]
        except OSError:
            names = []
        if not names:
            await ui.dialog(sys, "Archivio", "Nessun dump salvato.")
            return
        items = [ui.Item(_spaced(n[:-5]), None, "nfc", tag=n) for n in names]
        it = await ui.menu(sys, "Archivio NFC", items, icon="nfc",
                           hints=[("A", "Apri"), ("A tieni", "Indietro")])
        if it is None:
            return None
        try:
            with open(folder + "/" + it.tag) as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        r = await _view_saved(sys, data)
        if r == "home":
            return True
        if r == "delete":
            if await ui.dialog(sys, "Elimina", "Eliminare questo dump?",
                               ("Elimina", "Annulla")) == 0:
                try:
                    os.remove(folder + "/" + it.tag)
                except OSError:
                    pass


async def _view_saved(sys, info):
    """Returns "home", "delete" (A), or None (one level back)."""
    while True:
        ui.header(sys, info.get("title", "Tessera"), "nfc")
        draw_body(sys, info)
        ui.footer([("A", "Elimina"), ("A tieni", "Indietro")])
        sys.show()
        ev = await sys.event()
        if ev is None:
            continue
        k, knd = B.key(ev), B.kind(ev)
        if knd == sys.REDRAW:
            continue
        if sys.is_back(ev):
            return "home" if knd == sys.HOME else None
        if k == B.A and knd == B.CLICK:
            return "delete"


# -- entry ---------------------------------------------------------------------------------

async def main(sys):
    reader = None
    try:
        try:
            sys.power.rfid(True)
        except Exception:  # noqa: BLE001 - powering the reader is best effort
            pass
        try:
            reader = _open_reader(sys)
        except Exception:  # noqa: BLE001 - app still offers the archive without a reader
            reader = None
        await _idle_loop(sys, reader)
    finally:
        try:
            sys.power.rfid(False)
        except Exception:  # noqa: BLE001
            pass
        if sys.leds:
            sys.leds.set_effect(settings.get("led_effect") if settings.get("leds_on") else "off")
