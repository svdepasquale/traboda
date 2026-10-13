"""Bluetooth: live BLE scanner with a Geiger-style finder, nearby Traboda badges, radio info.

Raw `bluetooth` module: the irq only copies each advertisement into an inbox, the app loop
parses and draws. The radio is on only while this app runs, and the badge advertises
itself only on the "Badge vicini" screen.
"""

import random
import time

from .. import buttons as B
from .. import gfx, icons, settings, ui
from ..display import W, rgb
from .games.common import leds_frame

TITLE = "Bluetooth"
ICON = "bluetooth"
MEDIA_KEYS = False

_IRQ_SCAN_RESULT = 5
_IRQ_SCAN_DONE = 6
SCAN_MS = 20_000            # one gap_scan; the app loop starts the next one
SCAN_US = 30_000            # scan window; the scanner's interval too: listen all the time
NEAR_US = 60_000            # nearby badges: half duty, leaving air time for our own advert
ADV_US = 100_000
FORGET_MS = 30_000          # scanner: devices silent this long disappear
STALE_MS = 10_000           # scanner: rows silent this long are dimmed
BADGE_KEEP_MS = 600_000     # badges stay listed ("assente, ... fa") for 10 minutes
PRESENT_MS = 5_000          # badges advertise ten times a second: silent this long = gone
LOST_MS = 4_000             # finder: no packet for this long = signal lost
FREEZE_MS = 2_500           # a list keeps its order this long after up/down
INBOX_MAX = 160
DEV_MAX = 150
PREFIX = "TRABODA-"

LIST_Y = 52
SCAN_ROWS = 5
DETAIL_Y = 186
NEAR_Y = 104
NEAR_ROWS = 4
HIST = 48
LIGHT = rgb(200, 204, 222)
# finder bands (identity, RSSI, zone, meter, history), each pushed only when it changes
_BANDS = ((52, 70), (70, 140), (140, 170), (170, 190), (190, 220))

icons.register("bt_scan", (
    "................",
    ".....GGGGGG.....",
    "...GGkkkkkkGG...",
    "..GkkkkkkkkkwG..",
    ".GkkkkggggkwkkG.",
    ".GkkkgkkkkwkkkG.",
    ".GkkgkkkkwkgkkG.",
    ".GkkgkkGGkkgkkG.",
    ".GkkgkkGGkkgkkG.",
    ".GkkgkkkkkkgkkG.",
    ".GkkkgkkkkgkkkG.",
    ".GkkyyggggkkkkG.",
    "..GkyykkkkkkkG..",
    "...GGkkkkkkGG...",
    ".....GGGGGG.....",
    "................",
))

# Bluetooth SIG company identifiers (manufacturer data) and member service UUIDs
_VENDORS = {0x004C: "Apple", 0x0006: "Microsoft", 0x0075: "Samsung", 0x00E0: "Google",
            0x018E: "Google", 0x038F: "Xiaomi", 0x0157: "Huami", 0x027D: "Huawei",
            0x072F: "OnePlus", 0x079A: "Oppo", 0x0CCB: "Nothing", 0x012D: "Sony",
            0x00C4: "LG", 0x0087: "Garmin", 0x009E: "Bose", 0x0057: "Harman",
            0x00CC: "Beats", 0x0494: "Sennheiser", 0x05A7: "Sonos", 0x0171: "Amazon",
            0x01AB: "Meta", 0x058E: "Meta", 0x01DA: "Logitech", 0x067C: "Tile",
            0x0059: "Nordic", 0x02E5: "Espressif", 0x0499: "Ruuvi"}
_UUIDS = {0xFE9F: "Google", 0xFE2C: "Google", 0xFEAA: "Eddystone", 0xFE95: "Xiaomi",
          0xFDAB: "Xiaomi", 0xFD5A: "Samsung", 0xFEED: "Tile", 0xFEEC: "Tile", 0xFD84: "Tile",
          0xFE03: "Amazon", 0xFE07: "Sonos", 0xFEBE: "Bose", 0xFE1F: "Garmin",
          0xFD5F: "Meta", 0xFE59: "Nordic"}
_APPLE = {0x07: "AirPods", 0x09: "AirPlay", 0x0C: "Handoff", 0x10: "Nearby", 0x12: "Find My"}
_ZONES = ((-50, "Vicinissimo"), (-60, "Molto vicino"), (-70, "Vicino"), (-80, "Lontano"))
_ABOUT = {
    "scan": "I dispositivi Bluetooth qui intorno, dal più vicino. A su uno per trovarlo "
            "col contatore Geiger.",
    "near": "Il badge si fa vedere dagli altri badge Traboda e ti mostra chi c'è nei dintorni.",
    "info": "Indirizzo MAC, stato della radio e quando il badge è visibile agli altri.",
}


def _mix(a, b, f):
    return (a[0] + int((b[0] - a[0]) * f), a[1] + int((b[1] - a[1]) * f),
            a[2] + int((b[2] - a[2]) * f))


# cold to hot, one colour per LED column: cyan, yellow, pink
_HEAT = tuple(_mix((45, 226, 230), (255, 214, 10), i / 5) if i <= 5 else
              _mix((255, 214, 10), (255, 45, 111), (i - 5) / 5) for i in range(11))
_HEAT565 = tuple(rgb(*c) for c in _HEAT)

_inbox = {}         # addr -> (addr_type, adv_type, rssi, payload) of adverts, filled by the irq
_resp = {}          # the same for scan responses, kept apart so neither hides the other
_done = True        # the running gap_scan has ended (set by the irq)
_devs = {}          # addr -> _Dev, owned by the app loop
_sound = True


def _irq(event, data):
    global _done
    if event == _IRQ_SCAN_RESULT:
        box = _resp if data[2] == 4 else _inbox
        addr = bytes(data[1])
        if addr in box or len(box) < INBOX_MAX:     # a full inbox still takes fresh samples
            box[addr] = (data[0], data[2], data[3], bytes(data[4]))
    elif event == _IRQ_SCAN_DONE:
        _done = True


# -- devices ------------------------------------------------------------------------------

class _Dev:
    def __init__(self, addr, atype):
        self.addr = addr
        self.atype = atype
        self.name = None
        self.vendor = None
        self.extra = None
        self.conn = False
        self.rssi = self.raw = self.best = -127
        self.n = 0
        self.last = 0
        self.ads = self.rsp = None      # last payloads parsed

    def sample(self, rssi, now):
        self.raw = rssi
        self.rssi = (self.rssi * 2 + rssi) // 3 if self.n else rssi
        self.best = max(self.best, rssi)
        self.n += 1
        self.last = now


def _text(raw):
    raw = raw.rstrip(b"\x00")
    try:
        s = raw.decode()
    except UnicodeError:
        s = "".join(chr(c) if 32 <= c < 127 else "?" for c in raw)
    return s.strip() or None


def _parse(adv):
    """(name, vendor, extra) from an advertising payload, None where absent."""
    name = vendor = extra = None
    i, n = 0, len(adv)
    while i + 1 < n:
        ln = adv[i]
        if ln == 0 or i + 1 + ln > n:
            break
        t = adv[i + 1]
        if t == 0x09 or (t == 0x08 and name is None):
            name = _text(adv[i + 2:i + 1 + ln])
        elif t == 0xFF and ln >= 3:
            cid = adv[i + 2] | adv[i + 3] << 8
            sub = adv[i + 4] if ln >= 4 else -1
            if cid == 0x004C and sub == 0x02 and ln >= 5 and adv[i + 5] == 0x15:
                vendor, extra = "iBeacon", None
            else:
                vendor = _VENDORS.get(cid) or "0x%04X" % cid
                extra = _APPLE.get(sub) if cid == 0x004C else None
        elif t in (0x02, 0x03, 0x16) and vendor is None:
            for j in range(i + 2, i + ln, 2):
                vendor = _UUIDS.get(adv[j] | adv[j + 1] << 8)
                if vendor or t == 0x16:
                    break
        i += ln + 1
    return name, vendor, extra


def _drain(now, focus=None):
    """Moves what the irq collected into _devs; with focus, only that device is parsed."""
    global _inbox, _resp
    ads, _inbox = _inbox, {}
    rsp, _resp = _resp, {}
    for box in (ads, rsp):
        for addr in box:
            atype, kind, rssi, adv = box[addr]
            if rssi == 127:             # "not available"
                continue
            d = _devs.get(addr)
            if d is None:
                d = _devs[addr] = _Dev(addr, atype)
            d.sample(rssi, now)
            if focus is not None and addr != focus:
                continue
            if kind == 4:
                if adv == d.rsp:
                    continue
                d.rsp = adv
            else:
                d.conn = kind < 2       # ADV_IND, ADV_DIRECT_IND accept connections
                if adv == d.ads:
                    continue
                d.ads = adv
            name, vendor, extra = _parse(adv)
            # a shortened name (AD 0x08) never replaces the complete one it abbreviates
            if name and not (d.name and len(d.name) > len(name) and d.name.startswith(name)):
                d.name = name
            if vendor:
                d.vendor = vendor
                d.extra = extra


def _expire(now, focus=None):
    old = [a for a, d in _devs.items() if a != focus and
           time.ticks_diff(now, d.last) > (BADGE_KEEP_MS if _is_badge(d) else FORGET_MS)]
    for a in old:
        del _devs[a]
    if len(_devs) > DEV_MAX:
        weak = sorted((d for d in _devs.values() if not _is_badge(d) and d.addr != focus),
                      key=_by_rssi)
        for d in weak[:len(_devs) - DEV_MAX]:
            del _devs[d.addr]


def _by_rssi(d):
    return d.rssi


def _is_badge(d):
    return d.name is not None and d.name.startswith(PREFIX)


def _mac(addr):
    return ":".join("%02X" % b for b in addr)


def _label(d):
    return d.name or _mac(d.addr)


def _kind(d):
    if _is_badge(d):
        return "Badge Traboda"
    if not d.vendor:
        return "Produttore sconosciuto"
    if d.vendor.startswith("0x"):
        return "Produttore " + d.vendor
    return d.vendor + " · " + d.extra if d.extra else d.vendor


def _advert():
    """(payload, name): flags + our local name, cut to fit the 31-byte advert."""
    name = (PREFIX + str(settings.get("nickname"))).encode()
    kind = 0x09
    if len(name) > 26:
        n = 26
        while n and (name[n] & 0xC0) == 0x80:
            n -= 1
        name = name[:n]
        kind = 0x08                     # shortened local name
    return b"\x02\x01\x06" + bytes((len(name) + 1, kind)) + name, name.decode()


class _Radio:
    """The BLE object plus the scan we want running; the loop calls keep() to restart it."""

    def __init__(self, ble):
        self.ble = ble
        self.mode = None                # None: no scan wanted; else the active-scan flag
        self.interval = SCAN_US
        self.t0 = 0
        self.paused = False
        self.failed = False

    def scan(self, active, interval_us):
        self.mode = active
        self.interval = interval_us
        self.paused = False
        self._start()

    def _start(self):
        global _done
        self._halt()
        _done = False
        self.t0 = time.ticks_ms()
        try:
            self.ble.gap_scan(SCAN_MS, self.interval, SCAN_US, self.mode)
            self.failed = False
        except OSError:
            _done = True
            self.failed = True

    def keep(self, now, pause=False):
        """Restarts the wanted scan when it ended; pause stops it until a later keep()."""
        if self.mode is None:
            return
        if pause:
            if not self.paused:
                self.paused = True
                self._halt()
        elif self.paused or _done or time.ticks_diff(now, self.t0) > SCAN_MS + 3000:
            self.paused = False
            self._start()

    def _halt(self):
        try:
            self.ble.gap_scan(None)
        except OSError:
            pass

    def stop(self):
        self.mode = None
        self._halt()

    def advertise(self, payload):
        """Starts our advert; False when the stack refuses it (the caller retries)."""
        try:
            self.ble.gap_advertise(ADV_US, adv_data=payload, connectable=False)
            return True
        except OSError:
            return False

    def quiet(self):
        try:
            self.ble.gap_advertise(None)
        except OSError:
            pass

    def close(self):
        for step in (self.stop, self.quiet, lambda: self.ble.irq(None),
                     lambda: self.ble.active(False)):
            try:
                step()
            except Exception:  # noqa: BLE001 - shut down whatever state the stack is in
                pass


def _refresh(radio, now, focus=None, pause=False):
    radio.keep(now, pause)
    _drain(now, focus)
    _expire(now, focus)


class _Picker:
    """Selection over a live list: it follows the selected device, and the order stays
    put while the user is moving through it."""

    def __init__(self, rows):
        self.rows = rows
        self.items = []
        self.sel = self.top = 0
        self.addr = None
        self.moved = time.ticks_add(time.ticks_ms(), -FREEZE_MS)

    def update(self, fresh, now):
        if time.ticks_diff(now, self.moved) < FREEZE_MS:
            cur = {d.addr: d for d in fresh}
            kept = [cur.pop(d.addr) for d in self.items if d.addr in cur]
            fresh = kept + [d for d in fresh if d.addr in cur]
        self.items = fresh
        self._follow()

    def move(self, delta, now):
        if self.items:
            self.sel = (self.sel + delta) % len(self.items)
            self.addr = self.items[self.sel].addr
            self.moved = now
            self._follow()

    def current(self):
        return self.items[self.sel] if self.items else None

    def _follow(self):
        for i, d in enumerate(self.items):
            if d.addr == self.addr:
                self.sel = i
                break
        self.sel = max(0, min(self.sel, len(self.items) - 1))
        self.addr = self.items[self.sel].addr if self.items else None
        if self.sel < self.top:
            self.top = self.sel
        elif self.sel >= self.top + self.rows:
            self.top = self.sel - self.rows + 1
        self.top = max(0, min(self.top, len(self.items) - self.rows))


# -- drawing helpers ----------------------------------------------------------------------

def _level(rssi):
    return 4 if rssi >= -60 else 3 if rssi >= -70 else 2 if rssi >= -80 else 1


def _level_color(n):
    return ui.GREEN if n >= 3 else ui.YELLOW if n == 2 else ui.ORANGE


def _bars(x, base, n):
    c = _level_color(n)
    for i in range(4):
        h = 3 * (i + 1)
        gfx.fill_rect(x + i * 4, base - h, 3, h, c if i < n else ui.LINE)


def _ago(ms):
    s = ms // 1000
    if s < 2:
        return "ora"
    return "%d s fa" % s if s < 60 else "%d min fa" % (s // 60)


def _prox(rssi):
    p = (rssi + 95) / 55
    return 0.0 if p < 0 else 1.0 if p > 1 else p


def _zone(rssi):
    for lo, label in _ZONES:
        if rssi >= lo:
            return label
    return "Molto lontano"


def _head_count(text, live):
    gfx.fill_rect(176, 20, W - 176, 24, ui.BG)
    w = gfx.text(text, W - 12, 26, ui.DIM, align=-1)
    gfx.circle(W - 20 - w, 33, 3, ui.CYAN if live else ui.LINE, True)


def _highlight(y):
    gfx.round_rect(4, y + 1, W - 8, ui.ROW_H - 2, 6, ui.PANEL2)
    gfx.fill_rect(4, y + 5, 3, ui.ROW_H - 10, ui.ACCENT)


def _scrollbar(y0, view):
    n = len(view.items)
    if n > view.rows:
        track = view.rows * ui.ROW_H
        th = max(10, track * view.rows // n)
        gfx.fill_rect(W - 3, y0, 2, track, ui.PANEL)
        gfx.fill_rect(W - 3, y0 + (track - th) * view.top // (n - view.rows), 2, th, ui.ACCENT)


def _empty(y, title, note, failed):
    if failed:
        title, note = "Scansione non riuscita", "nuovo tentativo ogni secondo"
    gfx.text(title, W // 2, y, ui.ORANGE if failed else ui.TEXT, align=1)
    gfx.text(note, W // 2, y + 22, ui.DIM, "small", align=1)


def _bar_key(sys):
    a = sys.audio
    return sys.clock_text(), sys.battery, sys.charging, sys.wifi_connected(), a.playing, a.paused


def _hints(has_items):
    return [("A", "Trova"), ("A tieni", "Indietro")] if has_items else [("A tieni", "Indietro")]


def _push(sys, full, shown, has_items):
    """Pushes a live list: the whole screen on a full redraw, else the content band plus
    the status bar or the footer when they changed. shown: [status, footer] as drawn."""
    if full:
        shown[0] = _bar_key(sys)
    if full or shown[1] != has_items:
        shown[1] = has_items
        ui.footer(_hints(has_items))
        if not full:
            sys.show(ui.FOOTER_Y, 240)
    if full:
        sys.show()
        return
    y0 = 20
    key = _bar_key(sys)
    if key != shown[0]:
        shown[0] = key
        ui.statusbar(sys)
        y0 = 0
    sys.show(y0, ui.FOOTER_Y)


def _heat_leds(sys, lit, tick):
    if not sys.leds:
        return
    frame = []
    for pos in range(22):
        col = pos % 11
        frame.append((255, 255, 255) if tick and col == lit - 1 else
                     _HEAT[col] if col < lit else (0, 0, 0))
    leds_frame(sys, frame)


def _restore_leds(sys):
    if sys.leds:
        sys.leds.set_effect(settings.get("led_effect") if settings.get("leds_on") else "off")


# -- scanner ------------------------------------------------------------------------------

def _scan_row(d, y, selected, now):
    fresh = time.ticks_diff(now, d.last) < STALE_MS
    if selected:
        _highlight(y)
    n = _level(d.rssi)
    _bars(14, y + 19, n if fresh else 0)
    gfx.text("%d dBm" % d.rssi, W - 14, y + 7, _level_color(n) if fresh else ui.DIM, "small",
             align=-1)
    tag = "badge" if _is_badge(d) else d.vendor
    right = 252
    if tag:
        right -= gfx.text(tag, 252, y + 7, ui.ACCENT if tag == "badge" else
                          ui.CYAN if selected else ui.DIM, "small", align=-1) + 8
    if d.name and fresh:
        color = ui.TEXT if selected else LIGHT
    else:
        color = LIGHT if selected else ui.DIM
    gfx.text(gfx.ellipsize(_label(d), right - 36), 36, y + 5, color)


def _scan_detail(d, now):
    gfx.fill_rect(0, DETAIL_Y - 2, W, ui.FOOTER_Y - DETAIL_Y + 2, ui.BG)
    if d is None:
        return
    gfx.round_rect(4, DETAIL_Y, W - 8, 32, 6, ui.PANEL)
    known = d.vendor or _is_badge(d)
    gfx.text(gfx.ellipsize(_kind(d), 204), 12, DETAIL_Y + 1, ui.TEXT if known else ui.DIM)
    gfx.text("visto " + _ago(time.ticks_diff(now, d.last)), W - 12, DETAIL_Y + 3, ui.DIM,
             "small", align=-1)
    gfx.text("%s · %s · %s" % (_mac(d.addr), "casuale" if d.atype else "pubblico",
                                "connettibile" if d.conn else "solo annunci"),
             12, DETAIL_Y + 18, ui.DIM, "small")


def _ranked(now):
    """Scanner rows: strongest first, the ones gone quiet (dimmed) below the live ones."""
    live, quiet = [], []
    for d in _devs.values():
        age = time.ticks_diff(now, d.last)
        if age < STALE_MS:
            live.append(d)
        elif age <= FORGET_MS:
            quiet.append(d)
    live.sort(key=_by_rssi, reverse=True)
    quiet.sort(key=_by_rssi, reverse=True)
    return live + quiet


def _scan_list(view, now, failed):
    gfx.fill_rect(0, LIST_Y, W, SCAN_ROWS * ui.ROW_H, ui.BG)
    if not view.items:
        icons.draw(gfx.fb, "bt_scan", W // 2 - 16, 70, 2)
        _empty(114, "Ricerca in corso…", "i dispositivi compaiono qui man mano", failed)
    for i in range(view.top, min(len(view.items), view.top + view.rows)):
        _scan_row(view.items[i], LIST_Y + (i - view.top) * ui.ROW_H, i == view.sel, now)
    _scrollbar(LIST_Y, view)
    _scan_detail(view.current(), now)


async def _scanner(sys, radio):
    view = _Picker(SCAN_ROWS)
    radio.scan(True, SCAN_US)
    due = time.ticks_ms()
    live = False
    full = True
    shown = [None, None]
    try:
        while True:
            now = time.ticks_ms()
            dirty = False
            if time.ticks_diff(now, due) >= 0:
                # nobody reads a dark screen: the radio rests until a key wakes it
                _refresh(radio, now, pause=not sys.screen_on)
                view.update(_ranked(now), now)
                live = not live
                due = time.ticks_add(now, 1000)
                dirty = True
            if full:
                ui.header(sys, "Scanner", "bt_scan")
            if full or dirty:
                n = len(view.items)
                _head_count("1 dispositivo" if n == 1 else "%d dispositivi" % n, live)
                _scan_list(view, now, radio.failed)
                _push(sys, full, shown, n > 0)
                full = False
            ev = await sys.event(timeout_ms=max(10, time.ticks_diff(due, time.ticks_ms())))
            if ev is None:
                continue
            k, kind = B.key(ev), B.kind(ev)
            if kind == sys.REDRAW:
                full = True
            elif sys.is_back(ev):
                return "home" if kind == sys.HOME else None
            elif kind in (B.PRESS, B.REPEAT) and k in (B.UP, B.DOWN):
                view.move(-1 if k == B.UP else 1, time.ticks_ms())
                _scan_list(view, time.ticks_ms(), radio.failed)
                sys.show(LIST_Y, ui.FOOTER_Y)
            elif k == B.A and kind == B.CLICK and view.items:
                if await _find(sys, radio, view.addr) == "home":
                    return "home"
                full = True
    finally:
        radio.stop()


# -- finder -------------------------------------------------------------------------------

def _find_head(sys, d, addr):
    """Header and footer; returns the title drawn, so a name learned later redraws it."""
    title = _label(d) if d else _mac(addr)
    ui.header(sys, gfx.ellipsize(title, W - 44, "title"), "bt_scan")
    ui.footer([("A", "Muto" if _sound else "Suono"), ("A tieni", "Indietro")])
    return title


def _find_body(d, addr, r, lost, hist, now, note, shown):
    """Repaints the finder bands whose content changed (every band when shown is all None)
    and the history; returns the indexes in _BANDS to push."""
    p = 0.0 if lost else _prox(r)
    heat = ui.DIM if lost else _HEAT565[int(p * 10 + 0.5)]
    lit = 0 if lost else max(1, int(p * 11 + 0.5))
    ago = _ago(time.ticks_diff(now, d.last)) if d else "--"
    zone = "Segnale perso" if lost else _zone(r)
    kind = _kind(d) if d else None
    keys = ((note, kind), (lost, r, d.best if d else None, ago), (zone, heat), lit)
    out = [i for i in range(4) if keys[i] != shown[i]]
    out.append(4)
    for i in out:
        if i < 4:
            shown[i] = keys[i]
        gfx.fill_rect(0, _BANDS[i][0], W, _BANDS[i][1] - _BANDS[i][0], ui.BG)
    if 0 in out:
        w = gfx.text(note, W - 12, 52, ui.CYAN if note == "♪" else ui.DIM, align=-1)
        info = _mac(addr) if d is None else kind + " · " + _mac(addr)
        gfx.text(gfx.ellipsize(info, W - 32 - w, "small"), 12, 55, ui.DIM, "small")
    if 1 in out:
        gfx.text("--" if lost else str(r), 172, 70, heat, "huge", align=-1)
        gfx.text("dBm", 178, 106, heat, "title")
        gfx.text("picco", W - 12, 74, ui.DIM, "small", align=-1)
        gfx.text("%d dBm" % d.best if d else "--", W - 12, 88, ui.CYAN, align=-1)
        gfx.text("ultimo", W - 12, 108, ui.DIM, "small", align=-1)
        gfx.text(ago, W - 12, 122, ui.ORANGE if lost else ui.TEXT, align=-1)
    if 2 in out:
        gfx.text(zone, W // 2, 142, heat, "title", align=1)
    if 3 in out:
        for i in range(11):
            gfx.round_rect(19 + i * 26, 172, 22, 14, 3, _HEAT565[i] if i < lit else ui.PANEL2)
    gfx.round_rect(10, 192, W - 20, 26, 6, ui.PANEL)
    for i, v in enumerate(hist):
        x = 17 + i * 6
        if v is None:
            gfx.fill_rect(x, 211, 4, 2, ui.LINE)
        else:
            h = 2 + int(v * 16)
            gfx.fill_rect(x, 213 - h, 4, h, _HEAT565[int(v * 10 + 0.5)])
    return out


async def _find(sys, radio, addr):
    """Big RSSI, proximity bar and LEDs, Geiger ticks faster as the signal grows."""
    global _sound
    d = _devs.get(addr)
    ema = float(d.raw if d else -100)
    stamp = d.last if d else 0
    hist = [None] * HIST
    poll = draw = beep = flash = time.ticks_ms()
    leds = bar = title = None
    shown = [None] * 4
    full = True
    try:
        while True:
            now = time.ticks_ms()
            if time.ticks_diff(now, poll) >= 0:
                _refresh(radio, now, addr)
                d = _devs.get(addr) or d
                if d and d.last != stamp:
                    stamp = d.last
                    ema += (d.raw - ema) * 0.35
                if d and _label(d) != title:
                    full = True
                poll = time.ticks_add(now, 200)
            lost = d is None or time.ticks_diff(now, d.last) > LOST_MS
            r = round(ema)
            p = 0.0 if lost else _prox(r)
            lit = 0 if lost else max(1, int(p * 11 + 0.5))
            if not lost:
                sys.buttons.last_activity = now     # a finder in use is watched: screen on
                if time.ticks_diff(now, beep) >= 0:
                    if _sound:
                        try:
                            # one pitch per meter step, so audio keeps each tick's PCM cached
                            sys.audio.tone(460 + 140 * lit, 14, 0.3)
                        except Exception:  # noqa: BLE001 - a beep never stops the finder
                            pass
                    flash = time.ticks_add(now, 60)
                    gap = 60 + int(1000 * (1 - p) * (1 - p))
                    beep = time.ticks_add(now, int(gap * (0.6 + 0.8 * random.random())))
            state = (lit, time.ticks_diff(flash, now) > 0)
            if state != leds:
                leds = state
                _heat_leds(sys, state[0], state[1])
            tick = time.ticks_diff(now, draw) >= 0
            if tick:
                hist.pop(0)
                hist.append(None if lost else p)
                draw = time.ticks_add(now, 250)
            if full or tick:
                if full:
                    title = _find_head(sys, d, addr)
                    bar = _bar_key(sys)
                    shown = [None] * 4
                # a playing track skips tone() (there is no mixer): say why it is silent
                music = sys.audio.playing and not sys.audio.paused
                note = "muto" if not _sound else "musica" if music else "♪"
                bands = _find_body(d, addr, r, lost, hist, now, note, shown)
                if full:
                    sys.show()
                else:
                    key = _bar_key(sys)
                    if key != bar:
                        bar = key
                        ui.statusbar(sys)
                        sys.show(0, ui.STATUS_H)
                    for i in bands:
                        sys.show(_BANDS[i][0], _BANDS[i][1])
                full = False
            wait = min(time.ticks_diff(poll, now), time.ticks_diff(draw, now))
            if not lost:
                wait = min(wait, time.ticks_diff(beep, now))
            if leds[1]:
                wait = min(wait, time.ticks_diff(flash, now))
            ev = await sys.event(timeout_ms=max(5, wait))
            if ev is None:
                continue
            k, kind = B.key(ev), B.kind(ev)
            if kind == sys.REDRAW:
                full = True
                leds = None                 # the quick panel may have changed the LED effect
            elif sys.is_back(ev):
                return "home" if kind == sys.HOME else None
            elif k == B.A and kind == B.CLICK:
                _sound = not _sound
                full = True
    finally:
        _restore_leds(sys)


# -- nearby badges ------------------------------------------------------------------------

def _badges(now):
    here, gone = [], []
    for d in _devs.values():
        if _is_badge(d):
            (here if time.ticks_diff(now, d.last) < PRESENT_MS else gone).append(d)
    here.sort(key=_by_rssi, reverse=True)
    gone.sort(key=lambda d: time.ticks_diff(now, d.last))
    return here + gone, len(here)


def _near_card(name, ok, phase):
    gfx.fill_rect(0, LIST_Y, W, NEAR_Y - LIST_Y - 2, ui.BG)
    gfx.round_rect(6, LIST_Y, W - 12, 46, 8, ui.PANEL)
    for i, r in enumerate((8, 13, 18)):
        gfx.circle(30, LIST_Y + 23, r, ui.ACCENT if ok and phase % 3 == i else ui.LINE)
    gfx.circle(30, LIST_Y + 23, 3, ui.ACCENT if ok else ui.DIM, True)
    if ok:
        gfx.text("Sei visibile come", 58, LIST_Y + 6, ui.DIM, "small")
        gfx.text(gfx.ellipsize(name, W - 72), 58, LIST_Y + 22, ui.CYAN)
    else:
        gfx.text("Annuncio non riuscito", 58, LIST_Y + 5, ui.ORANGE)
        gfx.text("gli altri badge non ti vedono, ma tu sì", 58, LIST_Y + 26, ui.DIM, "small")


def _near_row(d, y, selected, now):
    age = time.ticks_diff(now, d.last)
    here = age < PRESENT_MS
    if selected:
        _highlight(y)
    n = _level(d.rssi)
    _bars(14, y + 19, n if here else 0)
    color = (ui.TEXT if selected else LIGHT) if here else ui.DIM
    gfx.text(gfx.ellipsize(d.name[len(PREFIX):] or "?", 156), 36, y + 5, color)
    if here:
        gfx.text("%d dBm" % d.rssi, 244, y + 7, _level_color(n), "small", align=-1)
    else:
        gfx.text("assente", 244, y + 7, ui.DIM, "small", align=-1)
    gfx.text(_ago(age), W - 14, y + 7, ui.CYAN if here else ui.DIM, "small", align=-1)


def _near_list(view, now, failed):
    gfx.fill_rect(0, NEAR_Y, W, NEAR_ROWS * ui.ROW_H, ui.BG)
    if not view.items:
        _empty(NEAR_Y + 30, "Nessun badge qui intorno", "chi apre Badge vicini compare qui",
               failed)
    for i in range(view.top, min(len(view.items), view.top + view.rows)):
        _near_row(view.items[i], NEAR_Y + (i - view.top) * ui.ROW_H, i == view.sel, now)
    _scrollbar(NEAR_Y, view)


async def _nearby(sys, radio):
    payload, name = _advert()
    ok = radio.advertise(payload)
    radio.scan(False, NEAR_US)
    view = _Picker(NEAR_ROWS)
    due = time.ticks_ms()
    here = phase = 0
    full = True
    shown = [None, None]
    try:
        while True:
            now = time.ticks_ms()
            dirty = False
            if time.ticks_diff(now, due) >= 0:
                ok = ok or radio.advertise(payload)
                _refresh(radio, now)
                fresh, here = _badges(now)
                view.update(fresh, now)
                phase += 1
                due = time.ticks_add(now, 1000)
                dirty = True
            if full:
                ui.header(sys, "Badge vicini", "badge")
            if full or dirty:
                _head_count("%d vicin%s" % (here, "o" if here == 1 else "i"), phase % 2)
                _near_card(name, ok, phase)
                _near_list(view, now, radio.failed)
                _push(sys, full, shown, bool(view.items))
                full = False
            ev = await sys.event(timeout_ms=max(10, time.ticks_diff(due, time.ticks_ms())))
            if ev is None:
                continue
            k, kind = B.key(ev), B.kind(ev)
            if kind == sys.REDRAW:
                full = True
            elif sys.is_back(ev):
                return "home" if kind == sys.HOME else None
            elif kind in (B.PRESS, B.REPEAT) and k in (B.UP, B.DOWN):
                view.move(-1 if k == B.UP else 1, time.ticks_ms())
                _near_list(view, time.ticks_ms(), radio.failed)
                sys.show(NEAR_Y, ui.FOOTER_Y)
            elif k == B.A and kind == B.CLICK and view.items:
                if await _find(sys, radio, view.addr) == "home":
                    return "home"
                full = True
    finally:
        radio.quiet()
        radio.stop()


# -- info and root ------------------------------------------------------------------------

def _draw_info(sys, ble, mac):
    y = ui.header(sys, "Info", "info")
    ui.footer([("A tieni", "Indietro")])
    on = ble.active()
    rows = (
        ("MAC", _mac(mac[1]) if mac else "non disponibile", ui.CYAN),
        ("Indirizzo", ("casuale" if mac[0] else "pubblico") if mac else "-", LIGHT),
        ("Radio", "accesa" if on else "spenta", ui.GREEN if on else ui.RED),
        ("Visibile", "solo in Badge vicini", ui.YELLOW),
        ("Nome", _advert()[1], LIGHT),
    )
    gfx.round_rect(6, y, W - 12, 8 + 20 * len(rows), 8, ui.PANEL)
    for i, (label, value, color) in enumerate(rows):
        gfx.text(label, 16, y + 5 + 20 * i, ui.DIM)
        gfx.text(gfx.ellipsize(value, W - 116), 104, y + 5 + 20 * i, color)
    note = ("Il Bluetooth è acceso solo mentre questa app è aperta, anche a schermo "
            "spento. In standby la radio è spenta e il badge non si vede.")
    for i, line in enumerate(gfx.wrap(note, W - 24, "small")[:3]):
        gfx.text(line, 12, y + 118 + 14 * i, ui.DIM, "small")


async def _info(sys, ble, mac):
    full = True
    while True:
        if full:
            _draw_info(sys, ble, mac)
            sys.show()
            full = False
        ev = await sys.event()
        if ev is None:
            continue
        kind = B.kind(ev)
        if kind == sys.REDRAW:
            full = True
        elif sys.is_back(ev):
            return "home" if kind == sys.HOME else None


def _root_detail(it, mac):
    y = LIST_Y + 3 * ui.ROW_H + 8
    gfx.round_rect(6, y, W - 12, 80, 8, ui.PANEL)
    for i, line in enumerate(gfx.wrap(it.detail, W - 36)[:3]):
        gfx.text(line, 18, y + 6 + 17 * i, LIGHT)
    now = time.ticks_ms()
    if it.tag == "scan":
        n = sum(1 for d in _devs.values() if time.ticks_diff(now, d.last) <= FORGET_MS)
        note = "visti di recente: %d" % n if n else ""
    elif it.tag == "near":
        n = sum(1 for d in _devs.values() if _is_badge(d))
        note = "badge incontrati: %d" % n if n else ""
    else:
        note = "MAC " + _mac(mac[1]) if mac else ""
    gfx.text(note, 18, y + 62, ui.CYAN, "small")


def _starting(sys):
    ui.header(sys, TITLE, ICON)
    icons.draw(gfx.fb, ICON, W // 2 - 24, 82, 3)
    gfx.text("Accensione Bluetooth…", W // 2, 144, ui.TEXT, align=1)
    ui.footer([])
    sys.show()


async def main(sys):
    _starting(sys)
    ble = None
    try:
        import bluetooth
        ble = bluetooth.BLE()
        ble.active(True)
        ble.irq(_irq)
    except Exception as e:  # noqa: BLE001 - missing module, OSError or RuntimeError from the stack
        if ble:
            try:
                ble.active(False)
            except Exception:  # noqa: BLE001
                pass
        why = "%s %s" % (type(e).__name__, e.args[0]) if e.args else type(e).__name__
        await ui.dialog(sys, "Bluetooth non disponibile",
                        "La radio non si è accesa (%s). Riprova tra poco; se succede ancora, "
                        "riavvia il badge." % why)
        return
    radio = _Radio(ble)
    try:
        mac = ble.config("mac")
    except Exception:  # noqa: BLE001 - not every stack reports it
        mac = None
    sel = 0
    try:
        while True:
            items = [ui.Item("Scanner", None, "bt_scan", tag="scan", detail=_ABOUT["scan"]),
                     ui.Item("Badge vicini", None, "badge", tag="near", detail=_ABOUT["near"]),
                     ui.Item("Info", None, "info", tag="info", detail=_ABOUT["info"])]
            it = await ui.menu(sys, TITLE, items, icon=ICON, sel=sel,
                               hints=[("A", "Apri"), ("A tieni", "Indietro")],
                               on_draw=lambda it: _root_detail(it, mac))
            if it is None:
                return
            sel = items.index(it)
            if it.tag == "scan":
                r = await _scanner(sys, radio)
            elif it.tag == "near":
                r = await _nearby(sys, radio)
            else:
                r = await _info(sys, ble, mac)
            if r == "home":
                return
    finally:
        radio.close()
        _restore_leds(sys)
