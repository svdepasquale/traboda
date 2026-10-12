"""Wi-Fi: connection status, network scan, saved networks, channel congestion chart,
auto-connect and NTP sync. Every radio call goes through traboda.net."""

import asyncio
import time

from .. import buttons as B
from .. import gfx, icons, net, settings, tz, ui
from ..display import W, rgb

TITLE = "Wi-Fi"
ICON = "wifi"
MEDIA_KEYS = False

CARD_Y = 54
CARD_H = 48
LIST_Y = 106
LIST_ROWS = 4
NET_ROWS = 5
DETAIL_Y = 186
LIGHT = rgb(200, 204, 222)

icons.register("wf_scan", (
    "................",
    "....dddddd......",
    "...dBBBBBBd.....",
    "..dBwwBBBBBd....",
    ".dBwBBBBBBBBd...",
    ".dBwBBBBBBBBd...",
    ".dBBBBBBBBBBd...",
    ".dBBBBBBBBBBd...",
    ".dBBBBBBBBBBd...",
    "..dBBBBBBBBd....",
    "...dBBBBBBdoo...",
    "....ddddddoooo..",
    "...........oooo.",
    "............ooo.",
    ".............o..",
    "................",
))
icons.register("wf_saved", (
    "................",
    ".......yy.......",
    ".......yy.......",
    "......yyyy......",
    "......yyyy......",
    ".yyyyyyyyyyyyyo.",
    "..yyyyyyyyyyyo..",
    "...yyyyyyyyyo...",
    "....yyyyyyyo....",
    "....yyyyyyyo....",
    "...yyyyyyyyyo...",
    "...yyyo..yyyo...",
    "..yyo......yyo..",
    "..yo........yo..",
    "................",
    "................",
))
icons.register("wf_chan", (
    "................",
    "................",
    ".............GG.",
    ".............GG.",
    ".........yy..GG.",
    ".........yy..GG.",
    ".........yy..GG.",
    ".....rr..yy..GG.",
    ".....rr..yy..GG.",
    ".....rr..yy..GG.",
    ".BB..rr..yy..GG.",
    ".BB..rr..yy..GG.",
    ".BB..rr..yy..GG.",
    "llllllllllllllll",
    "................",
    "................",
))
icons.register("wf_auto", (
    "................",
    ".....GGGGGG.....",
    "...GGGGGGGGGG.G.",
    "..GGG......GGGG.",
    ".GGG.......GGGG.",
    ".GG.......GGGGG.",
    ".GG.............",
    ".GG.........GG..",
    "..GG........GG..",
    ".............GG.",
    ".GGGGG.......GG.",
    ".GGGG.......GGG.",
    ".GGGG......GGG..",
    ".G.GGGGGGGGGG...",
    ".....GGGGGG.....",
    "................",
))

_scan = []      # last scan: [(ssid, rssi, channel, secure), ...] strongest first


# -- small drawing helpers ---------------------------------------------------------------

def _level(rssi):
    return 4 if rssi >= -60 else 3 if rssi >= -70 else 2 if rssi >= -80 else 1


def _level_color(n):
    return ui.GREEN if n >= 3 else ui.YELLOW if n == 2 else ui.ORANGE


def _quality(rssi):
    return ("debole", "discreto", "buono", "ottimo")[_level(rssi) - 1]


def _bars(x, base, n, bw=3, gap=1, step=3, c=None):
    """Four signal bars standing on y=base, n of them lit."""
    c = c or _level_color(n)
    for i in range(4):
        h = step * (i + 1)
        gfx.fill_rect(x + i * (bw + gap), base - h, bw, h, c if i < n else ui.LINE)


def _lock(x, y, c):
    gfx.rect(x + 1, y, 5, 6, c)
    gfx.fill_rect(x, y + 4, 7, 6, c)


def _current():
    return net.ssid if net.connected() else None


def _saved():
    return {n[0]: n[1] for n in settings.get("wifi")}


def _sync_text():
    if not net.last_sync:
        return None
    t = time.gmtime(net.last_sync + tz.offset_minutes(net.last_sync) * 60)
    return "%02d:%02d" % (t[3], t[4])


# -- root screen -------------------------------------------------------------------------

def _root_items():
    saved = settings.get("wifi")
    items = [
        ui.Item("Cerca reti", None, "wf_scan", tag="scan"),
        ui.Item("Reti salvate", str(len(saved)) if saved else None, "wf_saved", tag="saved"),
        ui.Item("Canali", None, "wf_chan", tag="chan"),
        ui.Item("Connessione automatica", settings.get("wifi_auto"), "wf_auto", "toggle",
                tag="auto"),
        ui.Item("Sincronizza ora", _sync_text(), "clock", tag="sync"),
    ]
    if net.connected():
        items.append(ui.Item("Disconnetti", None, "power", tag="off"))
    return items


def _card_state(sys):
    return (net.connected(), net.ssid, net.rssi(), net.status, sys.clock_text(), sys.battery)


def _draw_card():
    y = CARD_Y
    gfx.fill_rect(0, y, W, CARD_H, ui.BG)
    gfx.round_rect(6, y, W - 12, CARD_H, 8, ui.PANEL)
    if net.connected():
        r = net.rssi()
        n = _level(r) if r is not None else 4
        _bars(18, y + 38, n, 5, 2, 7)
        gfx.text(gfx.ellipsize(net.ssid or "?", 160), 56, y + 6, ui.TEXT)
        gfx.text(net.ip() or "", 56, y + 26, ui.CYAN)
        if r is not None:
            gfx.text("%d dBm" % r, W - 16, y + 8, _level_color(n), "small", align=-1)
            gfx.text(_quality(r), W - 16, y + 28, ui.DIM, "small", align=-1)
        return
    _bars(18, y + 38, 0, 5, 2, 7)
    if net.status == "connecting":
        title, sub, c = "Connessione…", gfx.ellipsize(net.ssid or "", 240), ui.YELLOW
    elif net.status == "scanning":
        title, sub, c = "Ricerca reti salvate…", "connessione automatica", ui.YELLOW
    else:
        title, sub, c = "Non connesso", "Cerca reti per collegarti", ui.ORANGE
    gfx.text(title, 56, y + 6, c)
    gfx.text(sub, 56, y + 26, ui.DIM)


async def main(sys):
    sel = top = 0
    full = True
    note = None
    try:
        while True:
            items = _root_items()
            sel = min(sel, len(items) - 1)
            top = max(0, min(top, sel, len(items) - LIST_ROWS))
            if sel >= top + LIST_ROWS:
                top = sel - LIST_ROWS + 1
            if full:
                ui.header(sys, TITLE, ICON)
                ui.footer([("A", "Ok"), ("A tieni", "Indietro")])
                full = False
            state = _card_state(sys)
            _draw_card()
            ui.draw_list(items, sel, top, LIST_Y, LIST_ROWS)
            sys.show()
            if note:
                await ui.toast(sys, note, 1500)
                note = None
                full = True
                continue
            ev = await sys.event(timeout_ms=2000)
            while ev is None:
                if _card_state(sys) != state:
                    state = _card_state(sys)
                    ui.statusbar(sys)
                    _draw_card()
                    sys.show(0, CARD_Y + CARD_H)
                ev = await sys.event(timeout_ms=2000)
            k, kind = B.key(ev), B.kind(ev)
            if kind == sys.REDRAW:
                full = True
                continue
            if sys.is_back(ev):
                return
            it = items[sel]
            if kind in (B.PRESS, B.REPEAT):
                if k == B.UP:
                    sel = (sel - 1) % len(items)
                elif k == B.DOWN:
                    sel = (sel + 1) % len(items)
                elif k in (B.LEFT, B.RIGHT) and it.tag == "auto":
                    note = await _set_auto(sys, not it.value)
                    full = True
                continue
            if k != B.A or kind != B.CLICK:
                continue
            if it.tag == "auto":
                r = await _set_auto(sys, not it.value)
            elif it.tag == "scan":
                r = await _scan_screen(sys, 0)
            elif it.tag == "chan":
                r = await _scan_screen(sys, 1)
            elif it.tag == "saved":
                r = await _saved_screen(sys)
            elif it.tag == "sync":
                r = await _sync(sys)
            else:
                r = await _disconnect(sys)
            if r == "home":
                return
            note = r
            full = True
    finally:
        if not net.connected() and net.status != "connecting":
            net.disable()


async def _set_auto(sys, on):
    """Toggles auto-connect; switching it on tries the saved networks right away."""
    settings.set("wifi_auto", on)
    if not on or net.connected() or not settings.get("wifi"):
        return None
    ui.toast_draw("Connessione automatica…")
    sys.show()
    if await net.auto_connect():
        net.sync_time()
        sys.notify("Connesso a " + net.ssid)
        return None
    return "Nessuna rete salvata qui intorno"


async def _sync(sys):
    if not net.connected():
        await ui.dialog(sys, "Sincronizza ora", "Serve una connessione Wi-Fi.")
        return None
    ui.toast_draw("Sincronizzazione…")
    sys.show()
    if net.sync_time():
        return "Ora sincronizzata: " + sys.clock_text()
    return "Server dell'ora non raggiungibile"


async def _disconnect(sys):
    if settings.get("wifi_auto"):
        c = await ui.dialog(sys, "Disconnetti", "Spengo anche la connessione automatica, "
                            "altrimenti il badge si ricollega da solo.", ("Ok", "Annulla"))
        if c != 0:
            return None
        settings.set("wifi_auto", False)
    net.disable()
    return "Wi-Fi disconnesso"


# -- scan: network list and channel chart -------------------------------------------------

def _scan_header(sys, tab):
    ui.header(sys, TITLE, ICON)
    for i, (label, x) in enumerate((("Reti", 214), ("Canali", 262))):
        gfx.text(label, x, 24, ui.TEXT if i == tab else ui.DIM)
        if i == tab:
            gfx.fill_rect(x, 44, len(label) * 8, 2, ui.CYAN)


def _scan_footer(tab):
    if tab == 0:
        ui.footer([("A", "Connetti"), ("◄►", "Canali"), ("A tieni", "Indietro")])
    else:
        ui.footer([("A", "Aggiorna"), ("◄►", "Reti"), ("A tieni", "Indietro")])


def _do_scan(sys, tab):
    """Blocking scan behind a "searching" screen. Returns an error string or None."""
    global _scan
    _scan_header(sys, tab)
    icons.draw(gfx.fb, "wifi", W // 2 - 24, 82, 3)
    gfx.text("Ricerca reti…", W // 2, 144, ui.TEXT, align=1)
    gfx.text("ci vogliono un paio di secondi", W // 2, 166, ui.DIM, "small", align=1)
    ui.footer([])
    sys.show()
    try:
        _scan = net.scan()
    except Exception as e:  # noqa: BLE001 - radio faults surface as OSError or RuntimeError
        _scan = []
        _scan_header(sys, tab)
        ui.footer([])
        return "Il Wi-Fi non risponde (%s). Riprova tra poco." % (e.args[-1] if e.args else
                                                                   type(e).__name__)
    return None


def _net_row(n, y, selected, current):
    ssid, rssi, ch, secure = n
    if selected:
        gfx.round_rect(4, y + 1, W - 8, ui.ROW_H - 2, 6, ui.PANEL2)
        gfx.fill_rect(4, y + 5, 3, ui.ROW_H - 10, ui.ACCENT)
    _bars(14, y + 19, _level(rssi))
    color = ui.GREEN if current else ui.TEXT if selected else LIGHT
    gfx.text(gfx.ellipsize(ssid, W - 36 - 84), 36, y + 5, color)
    if current:
        gfx.text("✓", W - 80, y + 5, ui.GREEN)
    if secure:
        _lock(W - 62, y + 8, ui.YELLOW if selected else ui.DIM)
    gfx.text("ch %d" % ch, W - 14, y + 7, ui.CYAN if selected else ui.DIM, "small", align=-1)


def _net_detail(n, current, saved):
    gfx.fill_rect(0, DETAIL_Y - 2, W, ui.FOOTER_Y - DETAIL_Y + 2, ui.BG)
    gfx.round_rect(4, DETAIL_Y, W - 8, 32, 6, ui.PANEL)
    ssid, rssi, ch, secure = n
    gfx.text("%s · canale %d · %d dBm" % ("Protetta" if secure else "Aperta", ch, rssi),
             12, DETAIL_Y + 1, ui.TEXT)
    if current:
        note = "connessa ora"
    elif saved:
        note = "password salvata" if secure else "rete salvata"
    else:
        note = "serve la password" if secure else "senza password"
    gfx.text("segnale %s · %s" % (_quality(rssi), note), 12, DETAIL_Y + 18, ui.DIM, "small")


def _draw_nets(sel, top):
    y0 = 52
    gfx.fill_rect(0, y0, W, DETAIL_Y - y0, ui.BG)
    if not _scan:
        gfx.text("Nessuna rete trovata", W // 2, 96, ui.TEXT, align=1)
        gfx.text("A: cerca di nuovo", W // 2, 118, ui.DIM, align=1)
        gfx.fill_rect(0, DETAIL_Y - 2, W, ui.FOOTER_Y - DETAIL_Y + 2, ui.BG)
        return
    cur = _current()
    saved = _saved()
    for i in range(top, min(len(_scan), top + NET_ROWS)):
        _net_row(_scan[i], y0 + (i - top) * ui.ROW_H, i == sel, _scan[i][0] == cur)
    if len(_scan) > NET_ROWS:
        track = NET_ROWS * ui.ROW_H
        th = max(10, track * NET_ROWS // len(_scan))
        ty = y0 + (track - th) * top // (len(_scan) - NET_ROWS)
        gfx.fill_rect(W - 3, y0, 2, track, ui.PANEL)
        gfx.fill_rect(W - 3, ty, 2, th, ui.ACCENT)
    n = _scan[sel]
    _net_detail(n, n[0] == cur, n[0] in saved)


def _congestion(nets, ch):
    """Interference on channel ch: overlapping networks (within 4 channels), by strength."""
    score = 0
    for _ssid, rssi, c, _sec in nets:
        d = abs(c - ch)
        if d < 5:
            score += max(1, rssi + 100) * (5 - d)
    return score


def _draw_channels():
    y0 = 52
    gfx.fill_rect(0, y0, W, ui.FOOTER_Y - y0, ui.BG)
    counts = [0] * 14
    best = [None] * 14
    for _ssid, rssi, ch, _sec in _scan:
        if 1 <= ch <= 13:
            counts[ch] += 1
            if best[ch] is None or rssi > best[ch]:
                best[ch] = rssi
    gfx.text("reti per canale, sotto il segnale più forte", W // 2, 54, ui.DIM,
             "small", align=1)
    cur = _current()
    cur_ch = None
    for n in _scan:
        if n[0] == cur:
            cur_ch = n[2]
    top = max(1, max(counts))
    base, maxh, x0, cw = 160, 66, 17, 22
    gfx.hline(x0, base, 13 * cw, ui.LINE)
    for ch in range(1, 14):
        cx = x0 + (ch - 1) * cw + cw // 2
        n = counts[ch]
        if n:
            h = max(6, maxh * n // top)
            gfx.round_rect(cx - 7, base - h, 14, h, 3, _level_color(_level(best[ch])))
            gfx.text(str(n), cx, base - h - 16, ui.TEXT, align=1)
            gfx.text(str(max(-99, best[ch])), cx, base + 17, _level_color(_level(best[ch])),
                     "small", align=1)
        gfx.text(str(ch), cx, base + 4, ui.CYAN if ch == cur_ch else ui.DIM, "small", align=1)
        if ch == cur_ch:
            gfx.hline(cx - 6, base + 1, 13, ui.CYAN)
    gfx.round_rect(4, 194, W - 8, 24, 6, ui.PANEL)
    if not _scan:
        gfx.text("Nessuna rete trovata", 12, 198, ui.DIM)
        return
    free = min((1, 6, 11), key=lambda c: _congestion(_scan, c))
    gfx.text("Canale più libero: %d" % free, 12, 198, ui.TEXT)
    gfx.text("%d reti" % len(_scan) if len(_scan) != 1 else "1 rete", W - 12, 198, ui.DIM,
             align=-1)


async def _scan_screen(sys, tab):
    err = _do_scan(sys, tab)
    if err:
        await ui.dialog(sys, "Wi-Fi non disponibile", err)
        return None
    sel = top = 0
    full = True
    while True:
        sel = min(sel, max(0, len(_scan) - 1))
        if sel < top:
            top = sel
        elif sel >= top + NET_ROWS:
            top = sel - NET_ROWS + 1
        if full:
            _scan_header(sys, tab)
            _scan_footer(tab)
            full = False
        if tab == 0:
            _draw_nets(sel, top)
        else:
            _draw_channels()
        sys.show()
        ev = await sys.event()
        k, kind = B.key(ev), B.kind(ev)
        if kind == sys.REDRAW:
            full = True
            continue
        if sys.is_back(ev):
            return "home" if kind == sys.HOME else None
        if kind in (B.PRESS, B.REPEAT):
            if k in (B.LEFT, B.RIGHT):
                tab = 1 - tab
                full = True
            elif tab == 0 and _scan and k == B.UP:
                sel = (sel - 1) % len(_scan)
            elif tab == 0 and _scan and k == B.DOWN:
                sel = (sel + 1) % len(_scan)
            continue
        if k != B.A or kind != B.CLICK:
            continue
        if tab == 1 or not _scan:
            err = _do_scan(sys, tab)
            if err:
                await ui.dialog(sys, "Wi-Fi non disponibile", err)
                return None
            sel = top = 0
            full = True
            continue
        ssid, _rssi, _ch, secure = _scan[sel]
        if ssid == _current():
            await ui.toast(sys, "Sei già connesso a " + ssid)
        elif await _connect(sys, ssid, secure):
            return None
        full = True


# -- connecting --------------------------------------------------------------------------

def _join_screen(sys, ssid):
    ui.header(sys, TITLE, ICON)
    gfx.text("Connessione a", W // 2, 136, ui.DIM, align=1)
    gfx.text(gfx.ellipsize(ssid, 296, "title"), W // 2, 154, ui.TEXT, "title", align=1)
    ui.footer([("A tieni", "Annulla")])


async def _join(sys, ssid, pw):
    """Connects with a progress animation. True, False, or None when cancelled."""
    _join_screen(sys, ssid)
    sys.show()
    task = asyncio.create_task(net.connect(ssid, pw))
    i = 0
    while not task.done():
        gfx.fill_rect(130, 76, 60, 50, ui.BG)
        _bars(W // 2 - 22, 122, i % 5, 8, 4, 10, ui.CYAN)
        sys.show(76, 126)
        i += 1
        ev = await sys.event(timeout_ms=250)
        if ev is None:
            continue
        if B.kind(ev) == sys.REDRAW:
            _join_screen(sys, ssid)
            sys.show()
        elif sys.is_back(ev):
            task.cancel()
            net.disable()
            return None
    try:
        return await task
    except Exception:  # noqa: BLE001 - a radio error is a failed attempt
        return False


def _joined_screen(sys, ssid, synced):
    ui.header(sys, TITLE, ICON)
    gfx.circle(W // 2, 100, 24, ui.GREEN, True)
    for d in range(3):
        gfx.line(W // 2 - 11, 99 + d, W // 2 - 4, 106 + d, ui.BG)
        gfx.line(W // 2 - 4, 106 + d, W // 2 + 11, 91 + d, ui.BG)
    gfx.text("Connesso a", W // 2, 134, ui.DIM, align=1)
    gfx.text(gfx.ellipsize(ssid, 296, "title"), W // 2, 152, ui.TEXT, "title", align=1)
    gfx.text(net.ip() or "", W // 2, 180, ui.CYAN, align=1)
    gfx.text("ora sincronizzata" if synced else "ora non sincronizzata", W // 2, 200,
             ui.DIM if synced else ui.ORANGE, "small", align=1)
    ui.footer([])
    sys.show()


async def _connect(sys, ssid, secure):
    """Saved password, the keyboard, or none for open networks. True once connected."""
    title = gfx.ellipsize("Password " + ssid, 296, "title")
    pw = _saved().get(ssid)
    if pw is None:
        pw = ""
        if secure:
            pw = await ui.keyboard(sys, title, secret=True)
            if pw is None:
                return False
    while True:
        ok = await _join(sys, ssid, pw)
        if ok is None:
            return False
        if ok:
            net.remember(ssid, pw)
            _joined_screen(sys, ssid, False)
            synced = net.sync_time()
            _joined_screen(sys, ssid, synced)
            sys.notify("Connesso a " + ssid)
            await sys.sleep_ms(1500, interruptible=True)
            return True
        msg = "Password errata o rete troppo lontana." if pw else "La rete non risponde."
        if await ui.dialog(sys, "Connessione fallita", msg, ("Riprova", "Annulla")) != 0:
            return False
        if pw:
            pw = await ui.keyboard(sys, title, text=pw, secret=True)
            if pw is None:
                return False


# -- saved networks ----------------------------------------------------------------------

async def _saved_screen(sys):
    sel = 0
    while True:
        nets = settings.get("wifi")
        if not nets:
            await ui.dialog(sys, "Reti salvate", "Nessuna rete salvata. Collegati da Cerca reti: "
                            "la password viene ricordata.")
            return None
        cur = _current()
        items = [ui.Item(n[0], "connessa" if n[0] == cur else None if n[1] else "aperta",
                         "wifi", tag=n[0]) for n in nets]
        it = await ui.menu(sys, "Reti salvate", items, icon="wf_saved", sel=sel,
                           hints=[("A", "Opzioni"), ("A tieni", "Indietro")])
        if it is None:
            return "home" if sys.pending_app() else None
        sel = items.index(it)
        name = gfx.ellipsize(it.tag, 264)
        if it.tag == cur:
            if await ui.dialog(sys, name, "Connessa ora. Dimenticarla? La connessione resta "
                               "attiva.", ("Dimentica", "Annulla")) == 0:
                net.forget(it.tag)
            continue
        c = await ui.dialog(sys, name, "Rete salvata", ("Connetti", "Dimentica"))
        if c == 0 and await _connect(sys, it.tag, True):
            return None
        if c == 1:
            net.forget(it.tag)
