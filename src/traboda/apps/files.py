"""File: the internal memory and the SD card. Folders first with sizes, a text pager (hex
for binary files), details, delete with confirmation, and WAV playback."""

import os
import time

from .. import buttons as B
from .. import gfx, icons, paths, settings, tz, ui
from ..player import title_of

TITLE = "File"
ICON = "files"
MEDIA_KEYS = False

ROWS = 6
LIST_Y = 52
NOTE_Y = 209                  # path and counts, under the list
VIEW_CAP = 48 * 1024          # what the text pager loads
TOP_Y = 42                    # first pager line
LINE_H = 13
PAGE = 13                     # pager lines on screen
COLS = 50                     # pager columns ("small" font, 6 px)
HEX_X = 37
TEXT_EXT = (".txt", ".py", ".json", ".md", ".csv", ".log", ".cfg", ".ini", ".html", ".xml")
CRITICAL = {
    "main.py": "Senza main.py il badge non avvia Traboda OS: si ferma al prompt di MicroPython.",
    "settings.json": "Contiene nickname, reti Wi-Fi, record e preferenze: tornano quelli di fabbrica.",
}
_ERRORS = {2: "non trovato", 5: "errore di I/O", 13: "accesso negato", 28: "spazio esaurito",
           30: "sola lettura"}

icons.register("f_text", (
    "................",
    "..lllllllll.....",
    "..lwwwwwwwll....",
    "..lwddddwwlwl...",
    "..lwwwwwwwllll..",
    "..lwddddddddwl..",
    "..lwwwwwwwwwwl..",
    "..lwddddddddwl..",
    "..lwwwwwwwwwwl..",
    "..lwddddddwwwl..",
    "..lwwwwwwwwwwl..",
    "..lwddddddddwl..",
    "..lwwwwwwwwwwl..",
    "..lwwwwwwwwwwl..",
    "..llllllllllll..",
    "................",
))
icons.register("f_file", (
    "................",
    "..lllllllll.....",
    "..lwwwwwwwll....",
    "..lwwwwwwwlwl...",
    "..lwwwwwwwllll..",
    "..lwwwwwwwwwwl..",
    "..lwwwwwwwwwwl..",
    "..lwwwvvvwwwwl..",
    "..lwwvvvvvwwwl..",
    "..lwwvvvvvwwwl..",
    "..lwwwvvvwwwwl..",
    "..lwwwwwwwwwwl..",
    "..lwwwwwwwwwwl..",
    "..lwwwwwwwwwwl..",
    "..llllllllllll..",
    "................",
))
icons.register("f_up", (
    "................",
    ".......BB.......",
    "......BBBB......",
    ".....BBBBBB.....",
    "....BBBBBBBB....",
    "...BBB.BB.BBB...",
    "..BBB..BB..BBB..",
    ".......BB.......",
    ".......BB.......",
    ".......BB.......",
    ".......BBBBBBB..",
    ".......BBBBBBB..",
    "................",
    "................",
    "................",
    "................",
))
icons.register("f_sd", (
    "................",
    "...BBBBBBBB.....",
    "...ByByByByB....",
    "...ByByByByBB...",
    "...BBBBBBBBBBB..",
    "...BBBBBBBBBBB..",
    "...BBBBBBBBBBB..",
    "...BBwwwwwwwBB..",
    "...BBwwwwwwwBB..",
    "...BBwwwwwwwBB..",
    "...BBBBBBBBBBB..",
    "...BBBBBBBBBBB..",
    "...BBBBBBBBBBB..",
    "...BBBBBBBBBBB..",
    "................",
    "................",
))
icons.register("f_chip", (
    "................",
    "....l.l.l.l.l...",
    "....l.l.l.l.l...",
    "...lllllllllll..",
    "...ldddddddddl..",
    "...ldGdddddddl..",
    "...ldddddddddl..",
    "...ldddddddddl..",
    "...ldddddddddl..",
    "...ldddddddddl..",
    "...ldddddddddl..",
    "...lllllllllll..",
    "....l.l.l.l.l...",
    "....l.l.l.l.l...",
    "................",
    "................",
))
icons.register("f_trash", (
    "................",
    "......rrrr......",
    ".....rr..rr.....",
    "..rrrrrrrrrrrr..",
    "................",
    "...rrrrrrrrrr...",
    "...rr.rr.rr.r...",
    "...rr.rr.rr.r...",
    "...rr.rr.rr.r...",
    "...rr.rr.rr.r...",
    "...rr.rr.rr.r...",
    "...rr.rr.rr.r...",
    "...rrrrrrrrrr...",
    "....rrrrrrrr....",
    "................",
    "................",
))


# -- helpers -------------------------------------------------------------------------------

def _root(path):
    return path.rstrip("/") or "/"


def _join(folder, name):
    return folder.rstrip("/") + "/" + name


def _parent(path):
    return path.rsplit("/", 1)[0] or "/"


def _size(n):
    if n < 1024:
        return "%d B" % n
    for unit in ("KB", "MB", "GB"):
        n /= 1024
        if n < 1024:
            break
    return ("%.1f %s" % (n, unit)).replace(".", ",") if n < 10 else "%d %s" % (n, unit)


def _grouped(n):
    s = str(n)
    out = ""
    while len(s) > 3:
        out = "." + s[-3:] + out
        s = s[:-3]
    return s + out


def _free(path):
    try:
        s = os.statvfs(path)
    except OSError:
        return None
    return "%s liberi" % _size(s[1] * s[3])


def _audio_error(e):
    """Audio's error text, in Italian for the ones a bad file gives."""
    if e.startswith("not a WAV") or e.startswith("WAV "):
        return "non è un file WAV valido"
    if e.startswith("compressed"):
        return "WAV compresso, serve PCM"
    if e.endswith("(only 16-bit)"):
        return "serve un WAV a 16 bit"
    return "file illeggibile" if e.startswith("[Errno") else e


def _why(e):
    code = e.args[0] if e.args else 0
    return _ERRORS.get(code, "errore %s" % code)


def _tail(s, n):
    return s if len(s) <= n else "«" + s[len(s) - n + 1:]


def _where(vols, path):
    """The path as the user knows it: "/music" in the memory, "SD:/roms" on the card."""
    best = vols[0]
    for v in vols[1:]:
        r = v[1].rstrip("/")
        if path == v[1] or path.startswith(r + "/"):
            best = v
    rel = path[len(best[1].rstrip("/")):] or "/"
    return rel if best is vols[0] else "SD:" + rel


def _icon(name):
    low = name.lower()
    if low.endswith(".wav"):
        return "music"
    return "f_text" if low.endswith(TEXT_EXT) else "f_file"


def _scan(sys, folder):
    """([(name, is_dir, size)] folders first, then by name; how many names were skipped).
    The badge's FAT keeps names in code page 437, so an accented name written by a
    computer is not UTF-8 and cannot become a str. A slow listing (a big folder on the
    card) puts up a notice. Raises OSError."""
    out = []
    bad = 0
    t0 = time.ticks_ms()
    slow = False
    it = os.ilistdir(folder)
    while True:
        try:
            e = next(it)
        except StopIteration:
            break
        except ValueError:                      # UnicodeError; the listing goes on
            bad += 1
            continue
        is_dir = e[1] == 0x4000
        size = e[3] if len(e) > 3 else 0
        if len(e) < 4 and not is_dir:           # the unix port lists no sizes
            try:
                size = os.stat(_join(folder, e[0]))[6]
            except OSError:
                pass
        out.append((e[0], is_dir, size))
        if not slow and time.ticks_diff(time.ticks_ms(), t0) > 150:
            slow = True
            y0, y1 = ui.toast_draw("Caricamento…")
            sys.show(y0, y1)
    out.sort(key=lambda e: (not e[1], e[0].lower()))
    return out, bad


def _text(data):
    """data decoded when it looks like text, else None."""
    if b"\x00" in data:
        return None
    head = data[:1024]
    ctrl = 0
    for b in head:
        if b < 32 and b not in (9, 10, 12, 13):
            ctrl += 1
    if ctrl * 20 > len(head):
        return None
    try:
        s = data.decode("utf-8", "replace")
    except UnicodeError:
        return None
    return None if s.count("\ufffd") * 20 > len(s) else s


def _wrap(text, cols):
    """Pager lines: tabs expanded, long lines broken at a space when one is near."""
    out = []
    for line in text.split("\n"):
        line = line.rstrip("\r").replace("\t", "    ")
        i, n = 0, len(line)
        while n - i > cols:
            cut = line.rfind(" ", i, i + cols + 1)
            if cut <= i + cols // 2:
                out.append(line[i:i + cols])
                i += cols
            else:
                out.append(line[i:cut])
                i = cut + 1
        out.append(line[i:])
    return out


# -- listing -------------------------------------------------------------------------------

def _items(entries, up):
    items = [ui.Item("..", None, "f_up", tag=("up",))] if up else []
    for name, is_dir, size in entries:
        if is_dir:
            items.append(ui.Item(name, None, "files", tag=("dir", name)))
        else:
            items.append(ui.Item(name, _size(size), _icon(name), tag=("file", name, size)))
    return items


async def _listing(sys, vols, folder, focus, at, up):
    """One folder. Returns (tag, row) for the row picked (or ("up",) for back), or None."""
    note = None
    bad = 0
    try:
        entries, bad = _scan(sys, folder)
    except OSError as e:
        entries = []
        note = "Cartella non leggibile: %s" % _why(e)
    if len(vols) > 1:                       # the card's mount point has its own row
        entries = [e for e in entries if _join(folder, e[0]) != vols[1][1]]
    items = _items(entries, up)
    if not entries and note is None:
        note = "Nomi illeggibili: togli gli accenti" if bad else "Cartella vuota"
    sel = max(0, min(at, len(items) - 1)) if at else 1 if up and entries else 0
    for i, it in enumerate(items):
        if focus is not None and it.tag[0] != "up" and it.tag[1] == focus:
            sel = i
    free = _free(folder)
    dirs = sum(1 for e in entries if e[1])
    counts = []
    if entries:
        counts.append("%d %s · %d file" % (dirs, "cartella" if dirs == 1 else "cartelle",
                                           len(entries) - dirs))
    if bad:
        counts.append("%d %s" % (bad, "illeggibile" if bad == 1 else "illeggibili"))
    summary = " · ".join(counts)
    hints = [("A", "Apri"), ("◄", "Su"), ("B", "Indietro")] if up else \
        [("A", "Apri"), ("B", "Esci")]
    top = 0
    full = True
    while True:
        if sel < top:
            top = sel
        elif sel >= top + ROWS:
            top = sel - ROWS + 1
        if full:
            ui.header(sys, TITLE, ICON)
            if free:
                gfx.text(free, 310, 22, ui.DIM, align=-1)
            gfx.text(summary, 310, NOTE_Y, ui.DIM, "small", align=-1)
            room = (300 - len(summary) * 6 - 12) // 6
            gfx.text(_tail(_where(vols, folder), room), 10, NOTE_Y, ui.DIM, "small")
            ui.footer(hints)
        ui.draw_list(items, sel, top, LIST_Y, ROWS)
        if note:
            for i, line in enumerate(gfx.wrap(note, 296)[:2]):
                gfx.text(line, 160, LIST_Y + ui.ROW_H * len(items) + 6 + 18 * i, ui.DIM, align=1)
        if full:
            sys.show()
            full = False
        else:
            sys.show(LIST_Y, LIST_Y + ROWS * ui.ROW_H)
        ev = await sys.event()
        if ev is None:
            continue
        k, kind = B.key(ev), B.kind(ev)
        if kind == sys.REDRAW:
            full = True
            continue
        if sys.leaving():
            return None
        if sys.is_back(ev):
            return (("up",), sel) if up else None
        if not items:
            continue
        if k == B.A and kind == B.CLICK:
            return items[sel].tag, sel
        if kind not in (B.PRESS, B.REPEAT):
            continue
        if k == B.UP:
            sel = (sel - 1) % len(items)
        elif k == B.DOWN:
            sel = (sel + 1) % len(items)
        elif k == B.LEFT and up and kind == B.PRESS:
            return ("up",), sel
        elif k == B.RIGHT and kind == B.PRESS and items[sel].tag[0] == "dir":
            return items[sel].tag, sel


# -- file actions --------------------------------------------------------------------------

async def _actions(sys, vols, folder, name, size):
    """The menu of one file, until back or the file is deleted."""
    path = _join(folder, name)
    items = []
    if name.lower().endswith(".wav"):
        items.append(ui.Item("Riproduci", None, "music", tag="play"))
    items += [ui.Item("Visualizza", None, "f_text", tag="view"),
              ui.Item("Info", None, "info", tag="info"),
              ui.Item("Elimina", None, "f_trash", tag="delete")]
    label = _size(size)
    title = gfx.ellipsize(name, 268 - len(label) * 8, "title")
    sel = 0
    while not sys.leaving():
        it = await ui.menu(sys, title, items, icon=_icon(name), sel=sel,
                           on_draw=lambda _: gfx.text(label, 310, 22, ui.DIM, align=-1))
        if it is None:
            return
        sel = items.index(it)
        if it.tag == "play":
            await _play(sys, path)
        elif it.tag == "view":
            await _view(sys, path, name, size)
        elif it.tag == "info":
            await _info(sys, vols, path, name, size)
        elif await _delete(sys, path, name):
            return


async def _play(sys, path):
    sys.player.load([path], 0)
    await sys.sleep_ms(250)                 # a bad file fails at once
    if sys.audio.error:
        err = sys.audio.error
        sys.player.load([])
        await ui.dialog(sys, "Riproduci", "Impossibile riprodurre: %s." % _audio_error(err))
    else:
        await ui.toast(sys, "♪ " + title_of(path), 900)


async def _delete(sys, path, name):
    """Asks (twice for the files the OS needs), then deletes. True when the file is gone."""
    if await ui.dialog(sys, "Elimina", "Eliminare «%s»?" % name, ("Annulla", "Elimina")) != 1:
        return False
    critical = name in CRITICAL and path == paths.data(name)
    if critical and await ui.dialog(sys, "Elimini " + name + "?", CRITICAL[name],
                                    ("Annulla", "Elimina"), accent=ui.RED) != 1:
        return False
    p = sys.player
    cur = p.current
    if cur == path:
        p.stop()
        await sys.sleep_ms(50)              # the cancelled playback task closes the file
    try:
        os.remove(path)
    except OSError as e:
        await ui.dialog(sys, "Elimina", "Impossibile eliminare: %s." % _why(e))
        return False
    if path in p.queue:                     # or the queue stops at the missing track
        p.queue = [t for t in p.queue if t != path]
        p.index = p.queue.index(cur) if cur in p.queue else -1
    if critical and name == "settings.json":
        settings.load()                     # or the next save writes the old values back
    return True


# -- viewer --------------------------------------------------------------------------------

def _frame(sys, hints):
    gfx.clear(ui.BG)
    ui.statusbar(sys)
    gfx.hline(8, TOP_Y - 3, 304, ui.LINE)
    ui.footer(hints)


def _title(name, info):
    gfx.fill_rect(0, ui.STATUS_H, 320, TOP_Y - 3 - ui.STATUS_H, ui.BG)
    gfx.text(info, 310, 21, ui.CYAN, align=-1)
    gfx.text(gfx.ellipsize(name, 300 - len(info) * 8 - 12), 10, 21, ui.TEXT)


def _scrollbar(top, total):
    track = PAGE * LINE_H
    gfx.fill_rect(314, TOP_Y, 2, track, ui.PANEL)
    if total > PAGE:
        th = max(10, track * PAGE // total)
        gfx.fill_rect(314, TOP_Y + (track - th) * top // (total - PAGE), 2, th, ui.ACCENT)


def _step(k, top, last):
    d = {B.UP: -1, B.DOWN: 1, B.LEFT: -PAGE, B.RIGHT: PAGE}.get(k, 0)
    return max(0, min(last, top + d))


async def _view(sys, path, name, size):
    if size > 16 * 1024:
        y0, y1 = ui.toast_draw("Caricamento…")
        sys.show(y0, y1)
    try:
        with open(path, "rb") as f:
            data = f.read(VIEW_CAP)
    except OSError as e:
        await ui.dialog(sys, name, "Impossibile leggere il file: %s." % _why(e))
        return
    cut = size > VIEW_CAP and data.rfind(b"\n") + 1
    if cut:
        data = data[:cut]                   # whole lines: the cap never splits a character
    text = _text(data)
    if text is None:
        await _hex(sys, path, name, size)
        return
    lines = _wrap(text[:-1] if text.endswith("\n") else text, COLS)
    if size > VIEW_CAP:
        lines += ["", "[ mostrati i primi %d KB di %s ]" % (VIEW_CAP // 1024, _size(size))]
    elif not data:
        lines = ["(file vuoto)"]
    await _pager(sys, name, lines)


async def _scroll(sys, name, total, draw):
    """The pager loop over total lines: draw(top) paints them and returns the header info."""
    last = max(0, total - PAGE)
    top = 0
    full = dirty = True
    while True:
        if full:
            _frame(sys, [("▲▼", "Scorri"), ("◄►", "Pagina"), ("B", "Indietro")])
        if dirty:
            gfx.fill_rect(0, TOP_Y, 312, PAGE * LINE_H, ui.BG)
            _title(name, draw(top))
            _scrollbar(top, total)
            if full:
                sys.show()
            else:
                sys.show(ui.STATUS_H, TOP_Y + PAGE * LINE_H)
            full = dirty = False
        ev = await sys.event()
        if ev is None:
            continue
        k, kind = B.key(ev), B.kind(ev)
        if kind == sys.REDRAW:
            full = dirty = True
        elif sys.is_back(ev):
            return
        elif kind in (B.PRESS, B.REPEAT):
            new = _step(k, top, last)
            if new != top:
                top = new
                dirty = True


async def _pager(sys, name, lines):
    total = len(lines)

    def draw(top):
        for i in range(min(PAGE, total - top)):
            gfx.text(lines[top + i], 8, TOP_Y + i * LINE_H, ui.TEXT, "small")
        return "%d-%d/%d" % (top + 1, min(top + PAGE, total), total)

    await _scroll(sys, name, total, draw)


async def _hex(sys, path, name, size):
    try:
        f = open(path, "rb")
    except OSError as e:
        await ui.dialog(sys, name, "Impossibile aprire il file: %s." % _why(e))
        return
    buf = bytearray(PAGE * 8)

    def draw(top):
        try:
            f.seek(top * 8)
            n = f.readinto(buf) or 0
        except OSError:
            n = 0
        if not size:
            gfx.text("(file vuoto)", 8, TOP_Y, ui.DIM, "small")
        for r in range(PAGE):
            i = r * 8
            if i >= n:
                break
            chunk = buf[i:min(i + 8, n)]
            y = TOP_Y + r * LINE_H
            gfx.text("%06X" % (top * 8 + i), HEX_X, y, ui.DIM, "small")
            gfx.text(" ".join("%02X" % b for b in chunk), HEX_X + 48, y, ui.TEXT, "small")
            gfx.text("".join(chr(b) if 32 <= b < 127 else "." for b in chunk),
                     HEX_X + 198, y, ui.CYAN, "small")
        return "hex %d%%" % ((top * 8 + n) * 100 // size if size else 100)

    try:
        await _scroll(sys, name, (size + 7) // 8, draw)
    finally:
        f.close()


# -- details -------------------------------------------------------------------------------

def _modified(path):
    try:
        mtime = os.stat(path)[8]
        t = time.gmtime(mtime + tz.offset_minutes(mtime) * 60)
    except (OSError, OverflowError, ValueError):    # a FAT date before the 2000 epoch
        return None
    if not 2025 <= t[0] < 2100:             # written before the clock was set
        return None
    return "%d %s %d, %02d:%02d" % (t[2], tz.MONTHS[t[1] - 1], t[0], t[3], t[4])


def _kind(path, name):
    """(type, format or None)."""
    try:
        with open(path, "rb") as f:
            if name.lower().endswith(".wav"):
                from ..audio import parse_wav
                rate, channels, bits, n = parse_wav(f)
                secs = n // max(1, rate * channels * bits // 8)
                return ("Audio WAV, %d:%02d" % (secs // 60, secs % 60),
                        "%d Hz · %s · %d bit" % (rate, "stereo" if channels == 2 else "mono", bits))
            head = f.read(1024)
    except (ValueError, MemoryError):       # MemoryError: a broken chunk size
        return "WAV non valido", None
    except OSError as e:
        return "Non leggibile (%s)" % _why(e), None
    return ("Testo" if _text(head) is not None else "Binario"), None


async def _info(sys, vols, path, name, size):
    title = gfx.ellipsize(name, 276, "title")
    rows = [("Nome", name)] if title != name else []
    rows.append(("Cartella", _where(vols, _parent(path))))
    rows.append(("Dimensione", "%s (%s byte)" % (_size(size), _grouped(size)) if size >= 1024
                 else "%d byte" % size))
    when = _modified(path)
    if when:
        rows.append(("Modificato", when))
    ftype, fmt = _kind(path, name)
    rows.append(("Tipo", ftype))
    if fmt:
        rows.append(("Formato", fmt))
    full = True
    while True:
        if full:
            ui.header(sys, title, _icon(name))
            y = 54
            for label, value in rows:
                lines = gfx.wrap(value, 208)
                if len(lines) > 2:
                    lines = [lines[0], gfx.ellipsize(lines[1] + "…", 208)]
                if y + 16 * len(lines) > ui.FOOTER_Y - 2:
                    break
                gfx.text(label, 12, y, ui.DIM)
                for line in lines:
                    gfx.text(line, 104, y, ui.TEXT)
                    y += 16
                y += 3
            ui.footer([("B", "Indietro")])
            sys.show()
            full = False
        ev = await sys.event()
        if ev is None:
            continue
        k, kind = B.key(ev), B.kind(ev)
        if kind == sys.REDRAW:
            full = True
        elif sys.is_back(ev) or (k == B.A and kind == B.CLICK):
            return


# -- entry ---------------------------------------------------------------------------------

async def main(sys):
    try:
        sys.mount_sd()
    except OSError:
        pass
    vols = [("Memoria interna", _root(paths.ROOT), "f_chip")]
    if sys.sd_mounted:
        vols.append(("Scheda SD", _root(paths.SD), "f_sd"))
    roots = [v[1] for v in vols]
    folder = roots[0] if len(vols) == 1 else None
    focus, at, vsel = None, 0, 0
    while not sys.leaving():
        if folder is None:
            items = [ui.Item(label, _free(root), icon, tag=root) for label, root, icon in vols]
            it = await ui.menu(sys, TITLE, items, icon=ICON, sel=vsel,
                               hints=[("A", "Apri"), ("B", "Esci")])
            if it is None:
                return
            vsel = items.index(it)
            folder, focus, at = it.tag, None, 0
            continue
        r = await _listing(sys, vols, folder, focus, at, folder != roots[0] or len(vols) > 1)
        if r is None:
            return
        tag, at = r
        if tag[0] == "up":
            if folder in roots:
                folder = None
            else:
                folder, focus, at = _parent(folder), folder.rsplit("/", 1)[1], 0
        elif tag[0] == "dir":
            folder, focus, at = _join(folder, tag[1]), None, 0
        else:
            await _actions(sys, vols, folder, tag[1], tag[2])
            focus = tag[1]
