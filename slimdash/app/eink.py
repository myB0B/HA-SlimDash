"""Type 0: the view drawn as a PNG image (greyscale), for e-readers whose
browser cannot be used (Kindle 4...). Address: /<dashboard>.png?view=N

Drawn directly with Pillow, without a browser: same grid as the HA "sections" views
(12 columns, rows of 56 px + 8 px), one drawer per card type; any card not
handled is shown as a "name: state" list. Designed for e-ink: white background,
solid black, 16 grey levels at most.
"""
import asyncio
import hashlib
import io
import logging
import math
import os
import re
import time
from datetime import datetime

from aiohttp import web

import i18n
import icons
import render

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:         # development PC without Pillow: 503 response
    Image = None

log = logging.getLogger("slimdash.eink")
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_FILE = os.path.join(HERE, "fonts", "Roboto.ttf")

SS = 2                  # supersampling (drawn at x2 then reduced: smooth edges)
ROW, GAP = 56, 8        # HA grid row and gap
PAD = 8                 # page margin (top, bottom)
SIDE = 0.09             # left and right margin, as a share of the width (54 px out of 600)
INK, INK2, GREY, LINE = 0, 0x33, 0x99, 0x66   # black, secondary text, medium grey, lines
# Type 3 look (HA): light grey page, white cards, light grey surfaces.
# Values before the final e-ink correction (about 221, 204, 204 on screen).
BG, CARD, FILL, ARC0 = 232, 255, 222, 215

_DATE = re.compile(r"'([^']*)'|cccc|EEEE|ccc|EEE|LLLL|MMMM|LLL|MMM|LL|MM|dd|d|yyyy|yy|HH|H|hh|h|mm|ss|a")


def fmt_date(f, d):
    """Same tokens as the s.js clock (digital-clock card)."""
    def rep(m):
        t = m.group(0)
        h12 = d.hour % 12 or 12
        return {
            "cccc": i18n.day_name(d.weekday()), "EEEE": i18n.day_name(d.weekday()),
            "ccc": i18n.day_name(d.weekday(), True), "EEE": i18n.day_name(d.weekday(), True),
            "LLLL": i18n.month_name(d), "MMMM": i18n.month_name(d),
            "LLL": i18n.month_name(d, True), "MMM": i18n.month_name(d, True),
            "LL": "%02d" % d.month, "MM": "%02d" % d.month, "dd": "%02d" % d.day, "d": str(d.day),
            "yyyy": str(d.year), "yy": str(d.year)[2:], "HH": "%02d" % d.hour, "H": str(d.hour),
            "hh": "%02d" % h12, "h": str(h12), "mm": "%02d" % d.minute, "ss": "%02d" % d.second,
            "a": "AM" if d.hour < 12 else "PM",
        }.get(t, m.group(1) or "")
    return _DATE.sub(rep, f)


# --------------------------------------------------------------------------
# Icons: SVG paths (MDI and house icons) drawn directly
# --------------------------------------------------------------------------
_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


class _Scan:
    def __init__(self, d):
        self.d, self.i = d, 0

    def skip(self):
        while self.i < len(self.d) and self.d[self.i] in " ,\t\r\n":
            self.i += 1

    def more(self):
        self.skip()
        return self.i < len(self.d) and self.d[self.i] in "+-.0123456789"

    def num(self):
        self.skip()
        m = _NUM.match(self.d, self.i)
        if not m:
            raise ValueError("nombre attendu")
        self.i = m.end()
        return float(m.group())

    def flag(self):
        self.skip()
        c = self.d[self.i]
        self.i += 1
        return c == "1"

    def cmd(self):
        self.skip()
        if self.i < len(self.d) and self.d[self.i].isalpha():
            self.i += 1
            return self.d[self.i - 1]
        return None


def _bez(p0, p1, p2, p3, n=8):
    out = []
    for k in range(1, n + 1):
        t = k / float(n)
        u = 1 - t
        out.append((u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
                    u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]))
    return out


def _arc(x1, y1, rx, ry, phi, fa, fs, x2, y2):
    """Arc elliptique SVG -> points (conversion « endpoint -> center », SVG F.6.5)."""
    if rx == 0 or ry == 0:
        return [(x2, y2)]
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(phi)
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2.0, (y1 - y2) / 2.0
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = x1p * x1p / (rx * rx) + y1p * y1p / (ry * ry)
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    co = math.sqrt(max(0.0, (rx * rx * ry * ry - den) / den)) if den else 0.0
    if fa == fs:
        co = -co
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx, cy = cp * cxp - sp * cyp + (x1 + x2) / 2.0, sp * cxp + cp * cyp + (y1 + y2) / 2.0

    def ang(ux, uy, vx, vy):
        return math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
    ux, uy = (x1p - cxp) / rx, (y1p - cyp) / ry
    t1 = ang(1, 0, ux, uy)
    dt = ang(ux, uy, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not fs and dt > 0:
        dt -= 2 * math.pi
    elif fs and dt < 0:
        dt += 2 * math.pi
    n = max(2, int(abs(dt) / (math.pi / 10)) + 1)
    out = []
    for k in range(1, n + 1):
        t = t1 + dt * k / n
        xx, yy = rx * math.cos(t), ry * math.sin(t)
        out.append((cp * xx - sp * yy + cx, sp * xx + cp * yy + cy))
    return out


def path_polys(d):
    """SVG path -> list of polylines [(x, y)...] (flattened curves)."""
    sc = _Scan(d)
    subs, pts = [], None
    x = y = sx = sy = 0.0
    cmd = prev = None
    lc = None           # last control point (S / T)
    while True:
        c = sc.cmd()
        if c is None:
            if cmd is None or not sc.more():
                break
            c = cmd
        rel = c.islower()
        C = c.upper()
        if C == "M":
            nx, ny = sc.num(), sc.num()
            x, y = (x + nx, y + ny) if rel else (nx, ny)
            if pts and len(pts) > 1:
                subs.append(pts)
            pts = [(x, y)]
            sx, sy = x, y
            cmd, prev, lc = ("l" if rel else "L"), C, None
            continue
        if pts is None:
            pts = [(x, y)]
        if C == "Z":
            pts.append((sx, sy))
            subs.append(pts)
            pts = [(sx, sy)]
            x, y = sx, sy
            cmd, prev, lc = None, C, None
            continue
        if C == "L":
            nx, ny = sc.num(), sc.num()
            x, y = (x + nx, y + ny) if rel else (nx, ny)
            pts.append((x, y))
            lc = None
        elif C == "H":
            v = sc.num()
            x = x + v if rel else v
            pts.append((x, y))
            lc = None
        elif C == "V":
            v = sc.num()
            y = y + v if rel else v
            pts.append((x, y))
            lc = None
        elif C in "CS":
            if C == "C":
                a, b = sc.num(), sc.num()
                p1 = (x + a, y + b) if rel else (a, b)
            else:
                p1 = (2 * x - lc[0], 2 * y - lc[1]) if lc and prev in "CS" else (x, y)
            a, b, e, f = sc.num(), sc.num(), sc.num(), sc.num()
            p2 = (x + a, y + b) if rel else (a, b)
            p3 = (x + e, y + f) if rel else (e, f)
            pts.extend(_bez((x, y), p1, p2, p3))
            lc, (x, y) = p2, p3
        elif C in "QT":
            if C == "Q":
                a, b = sc.num(), sc.num()
                q = (x + a, y + b) if rel else (a, b)
            else:
                q = (2 * x - lc[0], 2 * y - lc[1]) if lc and prev in "QT" else (x, y)
            a, b = sc.num(), sc.num()
            p3 = (x + a, y + b) if rel else (a, b)
            p1 = (x + 2 / 3.0 * (q[0] - x), y + 2 / 3.0 * (q[1] - y))
            p2 = (p3[0] + 2 / 3.0 * (q[0] - p3[0]), p3[1] + 2 / 3.0 * (q[1] - p3[1]))
            pts.extend(_bez((x, y), p1, p2, p3))
            lc, (x, y) = q, p3
        elif C == "A":
            rx, ry, rot = sc.num(), sc.num(), sc.num()
            fa, fs = sc.flag(), sc.flag()
            a, b = sc.num(), sc.num()
            nx, ny = (x + a, y + b) if rel else (a, b)
            pts.extend(_arc(x, y, rx, ry, rot, fa, fs, nx, ny))
            x, y, lc = nx, ny, None
        else:
            break
        cmd, prev = c, C
    if pts and len(pts) > 1:
        subs.append(pts)
    return subs


def _fill(polys, size, scale):
    """"nonzero" fill (default SVG rule) -> L mask of size x size."""
    edges = []
    for p in polys:
        for (x0, y0), (x1, y1) in zip(p, p[1:] + p[:1]):
            if y0 == y1:
                continue
            d = 1 if y1 > y0 else -1
            if y0 > y1:
                x0, y0, x1, y1 = x1, y1, x0, y0
            edges.append((y0 * scale, y1 * scale, x0 * scale, (x1 - x0) / (y1 - y0), d))
    buf = bytearray(size * size)
    for row in range(size):
        yc = row + 0.5
        xs = [(xa + (yc - ya) * k, d) for ya, yb, xa, k, d in edges if ya <= yc < yb]
        if not xs:
            continue
        xs.sort()
        w = 0
        for i in range(len(xs) - 1):
            w += xs[i][1]
            if w:
                a = max(0, int(round(xs[i][0])))
                b = min(size, int(round(xs[i + 1][0])))
                if b > a:
                    buf[row * size + a:row * size + b] = b"\xff" * (b - a)
    return Image.frombytes("L", (size, size), bytes(buf))


_ATTR = re.compile(r'(\w[\w-]*)="([^"]*)"')
_EL = re.compile(r"<(path|rect|circle)\s([^>]*)/>")
_icon_cache = {}


def icon_mask(key, px):
    """L mask (px x px) of an icon: key "m-xxx" (MDI, filled) or house icon (stroke)."""
    px = max(4, int(round(px)))
    ck = (key, px)
    m = _icon_cache.get(ck)
    if m is not None:
        return m
    q = 4                       # supersampling specific to the icons
    size = px * q
    scale = size / 24.0
    try:
        if key and key.startswith("m-") and key[2:] in icons._mdi():
            m = _fill(path_polys(icons._mdi()[key[2:]]), size, scale)
        else:
            m = Image.new("L", (size, size), 0)
            dr = ImageDraw.Draw(m)
            w = 2 * scale
            r = w / 2.0
            for tag, attrs in _EL.findall(icons.ICONS.get(key) or icons.ICONS["dot"]):
                a = dict(_ATTR.findall(attrs))
                f = lambda k: float(a.get(k) or 0) * scale    # noqa: E731
                if tag == "path":
                    for p in path_polys(a.get("d", "")):
                        sp = [(u * scale, v * scale) for u, v in p]
                        dr.line(sp, fill=255, width=int(round(w)), joint="curve")
                        for u, v in (sp[0], sp[-1]):
                            dr.ellipse((u - r, v - r, u + r, v + r), fill=255)
                elif tag == "rect":
                    x0, y0 = f("x"), f("y")
                    dr.rounded_rectangle((x0, y0, x0 + f("width"), y0 + f("height")),
                                         radius=f("rx"), outline=255, width=int(round(w)))
                else:
                    cx, cy, rr = f("cx"), f("cy"), f("r")
                    dr.ellipse((cx - rr - r, cy - rr - r, cx + rr + r, cy + rr + r), fill=255)
                    if rr > r:
                        dr.ellipse((cx - rr + r, cy - rr + r, cx + rr - r, cy + rr - r), fill=0)
    except Exception:
        log.exception("Icon %s unreadable", key)
        m = Image.new("L", (size, size), 0)
    m = m.resize((px, px), Image.LANCZOS)
    if len(_icon_cache) > 600:
        _icon_cache.clear()
    _icon_cache[ck] = m
    return m


# --------------------------------------------------------------------------
# Pen: coordinates in page px (1x), supersampled drawing
# --------------------------------------------------------------------------
_fonts = {}


def font(px, weight=400):
    px = max(5, int(round(px * SS)))
    k = (px, weight)
    f = _fonts.get(k)
    if f is None:
        try:
            f = ImageFont.truetype(FONT_FILE, px)
            try:
                f.set_variation_by_axes([weight, 100])
            except Exception:
                pass
        except OSError:
            f = ImageFont.load_default(px)
        _fonts[k] = f
    return f


class Pen:
    def __init__(self, w, h):
        self.img = Image.new("L", (int(round(w * SS)), int(round(h * SS))), BG)
        self.d = ImageDraw.Draw(self.img)

    @staticmethod
    def clean(s):
        """A single line; thin no-break space (thousands) missing from Roboto -> no-break space."""
        return " ".join(str(s).split("\n")).replace(" ", " ")

    @staticmethod
    def tw(s, size, weight=400):
        return font(size, weight).getlength(Pen.clean(s)) / SS

    def fit(self, s, size, weight, maxw):
        s = Pen.clean(s)
        if maxw <= 0:
            return ""
        if self.tw(s, size, weight) <= maxw:
            return s
        while s and self.tw(s + "…", size, weight) > maxw:
            s = s[:-1]
        return (s.rstrip() + "…") if s else ""

    def text(self, x, y, s, size, weight=400, fill=INK, anchor="la", maxw=None):
        s = self.fit(s, size, weight, maxw) if maxw is not None else Pen.clean(s)
        if s:
            self.d.text((x * SS, y * SS), s, font=font(size, weight), fill=fill, anchor=anchor)

    def wrap(self, s, size, weight, maxw):
        lines = []
        for para in str(s).split("\n"):
            cur = ""
            for word in para.split():
                t = (cur + " " + word) if cur else word
                if self.tw(t, size, weight) <= maxw or not cur:
                    cur = t
                else:
                    lines.append(cur)
                    cur = word
            lines.append(cur)
        return lines

    def rect(self, x, y, w, h, r=10, outline=LINE, width=1.5, fill=None):
        self.d.rounded_rectangle((x * SS, y * SS, (x + w) * SS, (y + h) * SS), radius=r * SS,
                                 outline=outline, width=max(1, int(round(width * SS))), fill=fill)

    def line(self, pts, fill=INK, width=2):
        if len(pts) > 1:
            self.d.line([(u * SS, v * SS) for u, v in pts], fill=fill,
                        width=max(1, int(round(width * SS))), joint="curve")

    def arc(self, cx, cy, r, a0, a1, width, fill):
        if a1 <= a0:
            return
        self.d.arc(((cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS), a0, a1,
                   fill=fill, width=max(1, int(round(width * SS))))

    def icon(self, key, x, y, px, fill=INK):
        m = icon_mask(key, px * SS)
        self.img.paste(fill, (int(round(x * SS)), int(round(y * SS))), m)


# --------------------------------------------------------------------------
# Drawing a view
# --------------------------------------------------------------------------
class Scene:
    def __init__(self, dash, now):
        self.dash = dash
        self.hub = dash.hub
        self.b = render.Builder(dash, dash.spec.get("url_path"), "t1")
        self.now = now
        self.pen = None         # None : mesure seulement
        self.in_sic = 0

    # ---- data ----
    def st(self, eid):
        return self.hub.states.get(eid) if eid else None

    def state(self, eid, decimals=None):
        if render.domain_of(eid) in render.STATELESS:    # button, scene, script: no useful state
            return ""
        return render.fmt_state(self.st(eid), eid, self.b.prec(eid) if decimals is None else decimals)

    def name(self, eid, cfg=None):
        try:
            return str(self.b.nm(eid, cfg)) if eid else str(cfg or "")
        except Exception:
            return str(cfg or eid or "")

    def ic(self, eid, cfg_icon=None):
        if eid:
            return icons.pick(eid, cfg_icon, (self.st(eid) or {}).get("a"))
        return icons.from_mdi(cfg_icon) or "dot"

    def tpl(self, s):
        if not render.has_tpl(s):
            return str(s or "")
        v = self.hub.tpl.get(render.tkey(s))
        return "…" if v is None else str(v)

    def hist(self, eid, hours):
        hours = max(1, min(render.MAX_HOURS, int(hours or 24)))
        return self.hub.hist.get("h:%s:%d" % (eid, hours)) or []

    # ---- card types ----
    @staticmethod
    def kind(c):
        return re.sub(r"[^a-z0-9]", "_", str(c.get("type", "")).lower())

    def visible(self, c):
        if not isinstance(c, dict):
            return False
        if self.kind(c) == "conditional":
            return self.cond_ok(c.get("conditions")) and self.visible(c.get("card") or {})
        vis = c.get("visibility")
        if isinstance(vis, list) and not self.cond_ok(vis):
            return False
        if self.kind(c) == "custom_bubble_card" and c.get("card_type") not in ("button", "separator"):
            return False
        return True

    def cond_ok(self, conds):
        for x in conds or []:
            if not isinstance(x, dict):
                continue
            e = x.get("entity")
            if not e:
                continue
            s = (self.st(e) or {}).get("s")
            if x.get("condition", "state") == "numeric_state":
                try:
                    f = float(s)
                    if "above" in x and not f > float(x["above"]):
                        return False
                    if "below" in x and not f < float(x["below"]):
                        return False
                except (TypeError, ValueError):
                    return False
                continue
            want, nwant = x.get("state"), x.get("state_not")
            if want is not None and s not in [str(w) for w in (want if isinstance(want, list) else [want])]:
                return False
            if nwant is not None and s in [str(w) for w in (nwant if isinstance(nwant, list) else [nwant])]:
                return False
        return True

    def size(self, c):
        """(columns out of 12, rows or None = natural height), like render.py."""
        k = self.kind(c)
        if k == "conditional":
            return self.size(c.get("card") or {})
        if k == "custom_weather_forecast" or k == "weather_forecast" or k == "custom_meteofrance_weather_card":
            both = c.get("show_current", True) is not False and c.get("show_forecast", True) is not False
            return self.b.size(c, 12, 4 if both or k == "custom_meteofrance_weather_card" else 2)
        if k == "custom_statistics_graph_chart_card":
            single = len([e for e in c.get("entities") or [] if e]) == 1
            return self.b.size(c, 12, 4 if single and not c.get("height") else None)
        if k in ("history_graph", "statistics_graph"):
            return self.b.size(c, 12, 6)
        if k in ("gauge", "energy_self_sufficiency_gauge"):
            cols, rows = self.b.size(c, 12 if k == "gauge" else 6, None)
            return cols, rows or (3 if cols == 12 else 2)
        if k == "button":
            return self.b.size(c, 6, 2)
        if k in ("entity", "sensor", "sensor_entity"):
            return self.b.size(c, 6, 2)
        if k in ("tile", "custom_mushroom_entity_card", "custom_mushroom_template_card"):
            return self.b.size(c, 6, 1)
        if k == "custom_bubble_card":
            if c.get("card_type") == "separator":
                return 12, None
            return self.b.size(c, 12 if c.get("sub_button") else 6, 1)
        return self.b.size(c, 12, None)

    # ---- mesure / dessin ----
    def measure(self, c, w):
        return self.run(c, 0, 0, w, None)

    def run(self, c, x, y, w, h):
        """h None: returns the natural height without drawing. Otherwise draws in (x, y, w, h)."""
        k = self.kind(c)
        fn = getattr(self, "k_" + k, None)
        if k == "conditional":
            return self.run(c.get("card") or {}, x, y, w, h)
        pen = self.pen
        if h is None:
            self.pen = None
        try:
            return (fn or self.k_fallback)(c, x, y, w, h)
        except Exception:
            log.exception("Type 0: drawing error for card %s", k)
            return 0 if h is None else h
        finally:
            self.pen = pen

    def frame(self, x, y, w, h):
        if self.pen and not self.in_sic:
            self.pen.rect(x, y, w, h, r=12, outline=None, width=0, fill=CARD)

    def T(self, *a, **kw):
        if self.pen:
            self.pen.text(*a, **kw)

    def I(self, key, x, y, px, fill=INK):
        if self.pen and key:
            self.pen.icon(key, x, y, px, fill)

    def tw(self, s, size, weight=400):
        return Pen.tw(s, size, weight)

    def fitw(self, s, size, weight, maxw):
        return Pen.fit(Pen, s, size, weight, maxw)

    # ---- grille de section ----
    def grid(self, cards, x, y, w, draw=True):
        """"Dense" placement on 12 columns (like HA). Returns the height used."""
        cw = (w - 11 * GAP) / 12.0
        occ = []                # rows -> set of columns taken
        placed = []
        for c in cards:
            if not self.visible(c):
                continue
            cols, rows = self.size(c)
            cols = max(1, min(12, cols))
            cwid = cols * cw + (cols - 1) * GAP
            if rows:
                span = rows
            else:
                nat = self.measure(c, cwid)
                if nat <= 0:
                    continue
                span = max(1, int(math.ceil((nat + GAP) / float(ROW + GAP) - 0.05)))
            r = 0
            while True:
                while len(occ) < r + span:
                    occ.append(set())
                col = next((c0 for c0 in range(0, 13 - cols)
                            if all(not (set(range(c0, c0 + cols)) & occ[rr]) for rr in range(r, r + span))),
                           None)
                if col is not None:
                    break
                r += 1
            for rr in range(r, r + span):
                occ[rr].update(range(col, col + cols))
            placed.append((c, col, r, cols, span))
        nrows = max([p[2] + p[4] for p in placed] or [0])
        if draw:
            for c, col, r, cols, span in placed:
                self.run(c, x + col * (cw + GAP), y + r * (ROW + GAP),
                         cols * cw + (cols - 1) * GAP, span * ROW + (span - 1) * GAP)
        return nrows * ROW + max(0, nrows - 1) * GAP

    def view(self, v, W, draw=True, y0=0.0):
        """Total height of the view at width W (and drawing if draw), shifted by y0."""
        y = PAD + y0
        side = max(PAD, round(W * SIDE))     # wider left/right margins: less stretched
        x, w = side, W - 2 * side
        badges = v.get("badges") or []
        if badges:
            y += self.badges(badges, x, y, w, draw) + GAP
        if v.get("type") == "sections":
            for sec in v.get("sections") or []:
                cards = [c for c in sec.get("cards") or [] if isinstance(c, dict)]
                hh = self.grid(cards, x, y, w, draw)
                if hh:
                    y += hh + 2 * GAP
        else:
            cards = v.get("cards") or []
            if v.get("type") == "panel":
                cards = cards[:1]
            for c in cards:
                if not self.visible(c):
                    continue
                cols, rows = self.size(c)
                hh = (rows * ROW + (rows - 1) * GAP) if rows else self.measure(c, w)
                if hh <= 0:
                    continue
                if draw:
                    self.run(c, x, y, w, hh)
                y += hh + GAP
        return y

    def badges(self, badges, x, y, w, draw):
        cx, h = x, 34
        for bd in badges:
            if isinstance(bd, str):
                bd = {"entity": bd}
            eid = bd.get("entity") if isinstance(bd, dict) else None
            if not eid:
                continue
            txt = self.state(eid)
            bw = 12 + 20 + 6 + self.tw(txt, 15, 500) + 12
            if cx + bw > x + w and cx > x:
                break
            if draw and self.pen:
                self.pen.rect(cx, y, bw, h, r=h / 2, outline=None, width=0, fill=CARD)
                self.I(self.ic(eid, bd.get("icon")), cx + 10, y + 7, 20)
                self.T(cx + 38, y + h / 2, txt, 15, 500, anchor="lm")
            cx += bw + 8
        return h

    # ---- cartes ----
    def k_vertical_stack(self, c, x, y, w, h):
        cards = [k for k in c.get("cards") or [] if self.visible(k)]
        title = c.get("title") if isinstance(c.get("title"), str) else ""
        cy = y + (30 if title else 0)
        if title:
            self.T(x + 4, y + 4, title, 18, 500, maxw=w - 8)
        for k in cards:
            nat = self.measure(k, w)
            if nat <= 0:
                continue
            if h is not None:
                self.run(k, x, cy, w, nat)
            cy += nat + GAP
        return max(0, cy - y - GAP)

    def k_horizontal_stack(self, c, x, y, w, h):
        cards = [k for k in c.get("cards") or [] if self.visible(k)]
        if not cards:
            return 0
        n = len(cards)
        cw = (w - (n - 1) * GAP) / float(n)
        hh = max(self.measure(k, cw) for k in cards)
        if h is not None:
            for i, k in enumerate(cards):
                self.run(k, x + i * (cw + GAP), y, cw, hh)
        return hh

    def k_grid(self, c, x, y, w, h):
        cards = [k for k in c.get("cards") or [] if self.visible(k)]
        if not cards:
            return 0
        n = max(1, min(6, int(c.get("columns") or 3)))
        cw = (w - (n - 1) * GAP) / float(n)
        square = c.get("square", True) is not False
        cy = y
        for i in range(0, len(cards), n):
            line = cards[i:i + n]
            hh = cw if square else max(self.measure(k, cw) for k in line)
            if h is not None:
                for j, k in enumerate(line):
                    self.run(k, x + j * (cw + GAP), cy, cw, hh)
            cy += hh + GAP
        return cy - y - GAP

    def k_custom_stack_in_card(self, c, x, y, w, h):
        self.frame(x, y, w, h) if h is not None else None
        self.in_sic += 1
        try:
            if c.get("mode") == "horizontal":
                return self.k_horizontal_stack(c, x, y, w, h)
            return self.k_vertical_stack(c, x, y, w, h)
        finally:
            self.in_sic -= 1

    def k_custom_digital_clock(self, c, x, y, w, h):
        pad = str(c.get("padding") or "8px")
        m = re.match(r"^(\d{1,2})px(?:\s+(\d{1,2})px)?", pad.strip())
        pv, ph = (int(m.group(1)), int(m.group(2) or m.group(1))) if m else (8, 8)
        lines = []
        for fmt, lay, dfmt, dsize in ((c.get("firstLineFormat"), c.get("firstLineLayout"), "HH:mm", 2.8),
                                      (c.get("secondLineFormat"), c.get("secondLineLayout"), "ccc d LLL", 1.6)):
            lay = lay if isinstance(lay, dict) else {}
            fmt = fmt if isinstance(fmt, str) and fmt else dfmt
            fs = max(8.0, min(120.0, render.css_px(lay.get("fontSize"), dsize * 14.0)))
            lh = render.css_px(lay.get("lineHeight", "1em"), fs, base=fs)
            fw = str(lay.get("fontWeight", "bold"))
            fw = {"bold": 700, "bolder": 700, "normal": 400, "lighter": 400}.get(fw) or (
                int(fw) if fw.isdigit() else 700)
            ta = lay.get("textAlign") if lay.get("textAlign") in ("left", "center", "right") else "center"
            lines.append((fmt_date(fmt, self.now), fs, max(lh, fs), max(400, fw), ta))
        tot = 2 * pv + sum(l[2] for l in lines)
        if h is None:
            return tot
        self.frame(x, y, w, h)
        cy = y + max(pv, (h - tot) / 2.0 + pv)
        for txt, fs, lh, fw, ta in lines:
            tx = {"left": x + ph, "right": x + w - ph}.get(ta, x + w / 2.0)
            anc = {"left": "lm", "right": "rm"}.get(ta, "mm")
            self.T(tx, cy + lh / 2.0, txt, fs, fw, anchor=anc, maxw=w - 2 * ph)
            cy += lh
        return h

    def k_weather_forecast(self, c, x, y, w, h):
        eid = c.get("entity")
        if not eid:
            return 0
        show_cur = c.get("show_current", True) is not False
        fcst = c.get("show_forecast", True) is not False
        ftype = c.get("forecast_type") or "daily"
        if h is None:
            return 4 * ROW + 3 * GAP if (show_cur and fcst) else 2 * ROW + GAP
        self.frame(x, y, w, h)
        items = (self.hub.fc.get("fc:%s:%s" % (eid, ftype)) or []) if fcst else []
        cy = y + 12
        if show_cur:
            st = self.st(eid) or {}
            a = st.get("a") or {}
            s = st.get("s")
            unit = a.get("temperature_unit", render.TEMP_UNIT)
            self.I(icons.WEATHER.get(s, "cloud"), x + 12, cy, 52)
            temp = ("%s %s" % (render.num(a.get("temperature")), unit)) if a.get("temperature") is not None else ""
            second = ""
            if items and ftype != "hourly" and items[0].get("templow") is not None:
                second = "%s %s / %s %s" % (render.num(items[0].get("temperature")), unit,
                                            render.num(items[0].get("templow")), unit)
            elif a.get("humidity") is not None:
                second = "%s %% humidity" % render.num(a["humidity"])
            rw = max(self.tw(temp, 34, 400), self.tw(second, 15, 400)) + 12
            self.T(x + w - 12, cy + 2, temp, 34, 400, anchor="ra")
            self.T(x + w - 12, cy + 42, second, 15, 400, fill=INK2, anchor="ra")
            self.T(x + 74, cy + 6, render.weather_txt(s), 20, 500, maxw=w - 86 - rw)
            self.T(x + 74, cy + 34, self.name(eid, c.get("name")), 15, 400, fill=INK2, maxw=w - 86 - rw)
            cy += 64
        if fcst and items:
            items = items[:5]
            n = len(items)
            room = y + h - cy - 8
            cw = (w - 16) / float(max(1, n))
            # Larger forecasts, centred in the remaining space (no gap at the bottom).
            isz = max(20, min(60, room - 72, cw - 8))
            blk = 70 + isz
            fy = cy + max(0, (room - blk) / 2.0)
            for i, f in enumerate(items):
                cx = x + 8 + cw * i + cw / 2.0
                try:
                    d = datetime.fromisoformat(str(f.get("datetime")).replace("Z", "+00:00")).astimezone()
                    lab = i18n.day_name(d.weekday(), True) if ftype != "hourly" else d.strftime("%H:%M")
                except (ValueError, TypeError):
                    lab = ""
                self.T(cx, fy, lab, 16, 500, anchor="ma")
                self.I(icons.WEATHER.get(f.get("condition"), "cloud"), cx - isz / 2.0, fy + 22, isz)
                hi, lo = f.get("temperature"), f.get("templow")
                if hi is not None:
                    self.T(cx, fy + 26 + isz, "%s°" % render.num(hi), 20, 500, anchor="ma")
                if lo is not None:
                    self.T(cx, fy + 50 + isz, "%s°" % render.num(lo), 18, 400, fill=INK2, anchor="ma")
        return h

    k_custom_meteofrance_weather_card = k_weather_forecast

    def chart(self, series, x, y, w, h, frame_bottom=True):
        """series = [(values, thickness, grey)] -> curves in the rectangle."""
        if not self.pen or h < 8:
            return
        if not any(v is not None for vals, _, _ in series for v in vals):
            self.T(x + w / 2.0, y + h / 2.0, "no data", 13, 400, fill=GREY, anchor="mm")
            return
        lines = []
        for vals, width, grey in series:
            n = len(vals)
            known = [v for v in vals if v is not None]
            if n < 2 or not known:
                continue
            # Scale specific to each curve (different units), like the mini graphs.
            lo, hi = min(known), max(known)
            if hi - lo < 1e-9:
                lo, hi = lo - 1, hi + 1
            span = hi - lo
            lo, hi = lo - span * 0.08, hi + span * 0.08
            seg = []
            for i, v in enumerate(vals + [None]):
                if v is None:
                    if len(seg) > 1:
                        lines.append((seg, grey, width))
                    seg = []
                    continue
                seg.append((x + w * i / float(n - 1), y + h - (v - lo) / (hi - lo) * h))
        # Like type 3: greyed area under the curves, then the lines on top.
        for seg, _, _ in lines:
            self.pen.d.polygon([(u * SS, v * SS) for u, v in seg + [(seg[-1][0], y + h), (seg[0][0], y + h)]],
                               fill=FILL)
        for seg, grey, width in lines:
            self.pen.line(seg, grey, width)
        if frame_bottom:
            self.pen.line([(x, y + h), (x + w, y + h)], GREY, 1)

    def order_ents(self, ents):
        """Several values: temperature first, then humidity, then pressure, then the rest."""
        def rank(e):
            a = (self.st(e["entity"]) or {}).get("a") or {}
            dc, u = a.get("device_class"), a.get("unit_of_measurement") or ""
            if dc == "temperature" or u in ("°C", "°F"):
                return 0
            if dc == "humidity":
                return 1
            if dc in ("pressure", "atmospheric_pressure") or u in ("hPa", "mbar", "inHg", "mmHg"):
                return 2
            return 3
        return sorted(ents, key=rank)      # stable sort: otherwise the order of the card is kept

    def big_value(self, x, y, e, size, maxw, anchor="la"):
        """Large value with the smaller unit beside it (like the card). Returns the width."""
        eid = e["entity"]
        txt = self.state(eid, e.get("decimals"))
        unit = ((self.st(eid) or {}).get("a") or {}).get("unit_of_measurement")
        if unit and txt.endswith(" " + unit):
            v = txt[:-len(unit) - 1]
        else:
            v, unit = txt, ""
        us = max(13, size * 0.45)
        while size > 14 and self.tw(v, size, 500) + (self.tw(unit, us, 400) + 4 if unit else 0) > maxw:
            size -= 1
            us = max(13, size * 0.45)
        vw = self.tw(v, size, 500)
        tot = vw + (self.tw(unit, us, 400) + 4 if unit else 0)
        x0 = x - tot if anchor == "ra" else x
        self.T(x0, y, v, size, 500)
        if unit:
            self.T(x0 + vw + 4, y + size * 0.12, unit, us, 400, fill=INK2)
        return tot

    def k_custom_statistics_graph_chart_card(self, c, x, y, w, h):
        ents = [e if isinstance(e, dict) else {"entity": e} for e in c.get("entities") or []]
        ents = self.order_ents([e for e in ents if e.get("entity")][:4])
        title = c.get("card_header") or c.get("title") or ""
        title = title if isinstance(title, str) else ""
        hours = c.get("hours_to_show") or (int(c.get("days_to_show") or 1) * 24)

        def ssize(e, dflt=40):
            try:
                return max(18, min(64, int(str(e.get("state_size") or dflt).replace("px", ""))))
            except ValueError:
                return dflt
        shown = [e for e in ents if e.get("show_state") is not False]
        size = ssize(shown[0]) if shown else 0
        rest = shown[1:]
        rs = 22                                   # following values, on the right
        head = (30 if title else 0)

        def asc(px):
            return font(px, 500).getmetrics()[0] / SS
        # The last value (humidity) shares the baseline of the main value; the one above (pressure) sits on
        # the baseline of the title, or one line higher when there is no title.
        up = 0 if (title or len(rest) < 2) else max(0, (len(rest) - 1) * (rs + 4) - (asc(size) - asc(rs)))
        vals_h = (max(size, (rs + 4) * len(rest)) + 8 + up) if shown else 0
        if h is None:
            return 12 + head + vals_h + 64 + 4
        self.frame(x, y, w, h)
        cy = y + 10
        if title:
            self.T(x + 14, cy, title, 18, 500, fill=INK2, maxw=w - 28)
            cy += head
        if shown:
            cy += up
            base = cy + asc(size)               # baseline of the main value
            tbase = (y + 10 + asc(18)) if title else None
            rw = 0
            for i, e in enumerate(rest):      # humidity on the main baseline, pressure above
                if i == 0:
                    bl = base
                elif i == 1 and tbase is not None:
                    bl = tbase
                else:
                    bl = base - i * (rs + 4)
                rw = max(rw, self.big_value(x + w - 14, bl - asc(rs), e, rs, (w - 28) * 0.45, anchor="ra"))
            self.big_value(x + 14, cy, shown[0], size, w - 28 - (rw + 10 if rest else 0))
            cy += max(size, (rs + 4) * len(rest)) + 8
        widths = [(2.5, INK), (2, LINE), (1.5, INK), (1.5, GREY)]
        series = [(self.hist(e["entity"], hours), widths[i][0], widths[i][1]) for i, e in enumerate(ents)]
        self.chart(series, x + 6, cy + 2, w - 12, y + h - cy - 12)
        return h

    def graph_card(self, c, x, y, w, h, hours):
        ents = [e if isinstance(e, dict) else {"entity": e} for e in c.get("entities") or []]
        ents = self.order_ents([e for e in ents if e.get("entity")][:4])
        title = c.get("title") if isinstance(c.get("title"), str) else ""
        if h is None:
            return 12 + (30 if title else 0) + 80 + 24 * len(ents) + 8
        self.frame(x, y, w, h)
        cy = y + 10
        if title:
            self.T(x + 14, cy, title, 18, 500, maxw=w - 28)
            cy += 30
        leg = 24 * len(ents)
        widths = [(2.5, INK), (2, LINE), (1.5, INK), (1.5, GREY)]
        self.chart([(self.hist(e["entity"], hours), widths[i][0], widths[i][1]) for i, e in enumerate(ents)],
                   x + 10, cy + 2, w - 20, y + h - cy - leg - 16)
        ly = y + h - leg - 8
        for i, e in enumerate(ents):
            v = self.state(e["entity"])
            if self.pen:
                self.pen.line([(x + 14, ly + 10), (x + 34, ly + 10)], widths[i][1], widths[i][0])
            self.T(x + w - 14, ly, v, 15, 500, anchor="ra")
            self.T(x + 42, ly, self.name(e["entity"], e.get("name")), 15, 400, maxw=w - 70 - self.tw(v, 15, 500))
            ly += 24
        return h

    def k_history_graph(self, c, x, y, w, h):
        return self.graph_card(c, x, y, w, h, c.get("hours_to_show") or 24)

    def k_statistics_graph(self, c, x, y, w, h):
        return self.graph_card(c, x, y, w, h, (c.get("days_to_show") or 30) * 24)

    def gauge(self, x, y, w, h, frac, txt, name):
        if h is None:
            return 2 * ROW + GAP
        self.frame(x, y, w, h)
        name_h = 26 if name else 0
        r = min((w - 24) / 2.0, (h - name_h - 16) * 0.95)
        r = max(10, r)
        th = max(6, r * 0.24)
        cx, cy = x + w / 2.0, y + 10 + r + (h - name_h - 16 - r) / 2.0
        if self.pen:
            self.pen.arc(cx, cy, r - th / 2, 180, 360, th, ARC0)
            self.pen.arc(cx, cy, r - th / 2, 180, 180 + 180 * max(0.0, min(1.0, frac)), th, INK)
        # Value placed in the hollow of the arc, without touching it (1200 W, Unavailable...).
        fs = max(12, min(24, (r - th) * 0.55))
        room = 1.5 * (r - th)
        while fs > 12 and self.tw(txt, fs, 500) > room:
            fs -= 1
        self.T(cx, cy - 2, txt, fs, 500, anchor="ms", maxw=room)
        if name:
            self.T(cx, y + h - 10, name, 15, 500, anchor="ms", maxw=w - 16)
        return h

    def k_gauge(self, c, x, y, w, h):
        eid = c.get("entity")
        if not eid:
            return 0
        mn = float(c.get("min", 0) or 0)
        mx = float(c.get("max", 100) or 100)
        st = self.st(eid)
        v = render.num_value(st)
        frac = 0 if v is None or mx == mn else (v - mn) / (mx - mn)
        if c.get("unit") and st and render.num(st.get("s")) is not None:
            txt = "%s %s" % (render.num(st.get("s")), c["unit"])
        else:
            txt = self.state(eid)
        return self.gauge(x, y, w, h, frac, txt, self.name(eid, c.get("name")))

    def k_energy_self_sufficiency_gauge(self, c, x, y, w, h):
        v = self.hub.hist.get("e:ss")
        return self.gauge(x, y, w, h, 0 if v is None else v / 100.0,
                          "—" if v is None else "%d %%" % round(v),
                          str(c.get("title") or "Taux d'autosuffisance"))

    def k_button(self, c, x, y, w, h):
        eid = c.get("entity")
        nm = (self.name(eid, c.get("name")) if eid else str(c.get("name") or "")) if c.get("show_name", True) else ""
        state = self.state(eid) if eid and c.get("show_state", False) else ""
        show_icon = c.get("show_icon", True)
        if h is None:
            return 2 * ROW + GAP
        self.frame(x, y, w, h)
        texth = (24 if nm else 0) + (20 if state else 0)
        isz = max(16, min(48, h - texth - 24)) if show_icon else 0
        top = y + (h - isz - texth - (6 if isz and texth else 0)) / 2.0
        if show_icon:
            self.I(self.ic(eid, c.get("icon")), x + (w - isz) / 2.0, top, isz)
            top += isz + 6
        if nm:
            self.T(x + w / 2.0, top, nm, 17, 500, anchor="ma", maxw=w - 12)
            top += 24
        if state:
            self.T(x + w / 2.0, top, state, 15, 400, fill=INK2, anchor="ma", maxw=w - 12)
        return h

    def tile(self, x, y, w, h, eid, nm, state, cfg_icon=None, side=""):
        if h is None:
            return ROW
        self.frame(x, y, w, h)
        isz = 26
        cy = y + min(h, ROW) / 2.0 if h < 2 * ROW else y + h / 2.0
        if self.pen:
            self.pen.d.ellipse(((x + 8) * SS, (cy - 19) * SS, (x + 46) * SS, (cy + 19) * SS), fill=BG)
        self.I(self.ic(eid, cfg_icon), x + 27 - isz / 2.0, cy - isz / 2.0, isz)
        sw = self.tw(side, 15, 500) + 12 if side else 0
        if side:
            self.T(x + w - 12, cy, side, 15, 500, anchor="rm", maxw=w * 0.5)
            sw = min(sw, w * 0.5 + 12)
        tx, mw = x + 56, w - 64 - sw
        if state:
            self.T(tx, cy - 2, nm, 16, 500, anchor="ls", maxw=mw)
            self.T(tx, cy + 3, state, 15, 400, fill=INK2, anchor="lt", maxw=mw)
        else:
            self.T(tx, cy, nm, 16, 500, anchor="lm", maxw=mw)
        return h

    def k_tile(self, c, x, y, w, h):
        eid = c.get("entity")
        if not eid:
            return 0
        state = self.state(eid) if c.get("show_entity_picture") is not True and c.get("hide_state") is not True else ""
        return self.tile(x, y, w, h, eid, self.name(eid, c.get("name")), state, c.get("icon"))

    def k_custom_mushroom_entity_card(self, c, x, y, w, h):
        eid = c.get("entity")
        if not eid:
            return 0
        state = "" if c.get("primary_info") == "state" or c.get("secondary_info") == "none" else self.state(eid)
        return self.tile(x, y, w, h, eid, self.name(eid, c.get("name")), state, c.get("icon"))

    def k_custom_mushroom_template_card(self, c, x, y, w, h):
        eid = c.get("entity")
        prim = self.tpl(c.get("primary") or "")
        sec = self.tpl(c.get("secondary") or "")
        if not prim and not sec:
            return 0
        icon = c.get("icon") if not render.has_tpl(c.get("icon")) else self.tpl(c.get("icon"))
        return self.tile(x, y, w, h, eid, prim or sec, sec if prim else "", icon or None)

    def k_custom_bubble_card(self, c, x, y, w, h):
        if c.get("card_type") == "separator":
            return self.k_heading({"heading": c.get("name") or ""}, x, y, w, h)
        eid = c.get("entity")
        if not eid:
            return 0
        sub = c.get("sub_button")
        if isinstance(sub, dict):
            sub = (sub.get("main") or []) + (sub.get("bottom") or [])
        vals = []
        for s in (sub or [])[:4]:
            if not (isinstance(s, dict) and s.get("entity")):
                continue
            se = s["entity"]
            # Like render.py: state_content ("state", "last_updated", attribute...) or show_state.
            sc = s.get("state_content")
            sc = [sc] if isinstance(sc, str) else [k for k in (sc or []) if isinstance(k, str)]
            if s.get("show_state") and "state" not in sc:
                sc.insert(0, "state")
            if s.get("show_last_changed") or s.get("show_last_updated"):
                sc.append("last_changed")
            for k in sc[:3]:
                if k == "state":
                    vals.append(render.cap(self.state(se)))
                elif k in ("last_updated", "last_changed", "last-updated", "last-changed"):
                    t = render.ts_epoch((self.st(se) or {}).get("lc"))
                    vals.append(render.cap(render.rel_time(t)) if t is not None else "—")
                elif re.match(r"^\w+$", k):
                    v = ((self.st(se) or {}).get("a") or {}).get(k)
                    vals.append("—" if v is None else str(v))
        state = render.cap(self.state(eid)) if c.get("show_state") else ""
        return self.tile(x, y, w, h, eid, self.name(eid, c.get("name")), state, c.get("icon"),
                         side=" · ".join(vals))

    def k_entity(self, c, x, y, w, h):
        eid = c.get("entity")
        if not eid:
            return 0
        graph = self.kind(c) == "sensor" and c.get("graph") == "line"
        if h is None:
            return 2 * ROW + GAP
        self.frame(x, y, w, h)
        self.I(self.ic(eid, c.get("icon")), x + w - 38, y + 12, 26)
        self.T(x + 14, y + 14, self.name(eid, c.get("name")), 16, 500, fill=INK2, maxw=w - 60)
        st = self.st(eid)
        if c.get("attribute"):
            v = ((st or {}).get("a") or {}).get(c["attribute"])
            txt = "—" if v is None else (render.num(v) or str(v))
            if c.get("unit"):
                txt += " " + c["unit"]
        elif c.get("unit"):
            s = st.get("s") if st else None
            txt = "%s %s" % (render.num(s) or s or "—", c["unit"])
        else:
            txt = self.state(eid)
        self.T(x + 14, y + 42, txt, 28, 500, maxw=w - 28)
        if graph:
            self.chart([(self.hist(eid, c.get("hours_to_show") or 24), 2.5, INK)],
                       x + 6, y + 80, w - 12, y + h - (y + 80) - 8)
        return h

    k_sensor = k_entity
    k_sensor_entity = k_entity

    def title_h(self, c, key="title"):
        t = c.get(key)
        return t if isinstance(t, str) and t and not render.has_tpl(t) else ""

    def k_entities(self, c, x, y, w, h):
        title = self.title_h(c)
        rows = []
        for r in c.get("entities") or []:
            if isinstance(r, str):
                r = {"entity": r}
            if not isinstance(r, dict):
                continue
            t = r.get("type")
            if r.get("entity") and (not t or t in ("attribute", "simple-entity")):
                rows.append(("ent", r))
            elif t == "section":
                rows.append(("sec", r))
            elif t == "divider":
                rows.append(("div", r))
            elif r.get("name"):
                rows.append(("txt", r))
        if not rows and not title:
            return 0
        RH = 40
        tot = 10 + (34 if title else 0) + sum(RH if k != "div" else 12 for k, _ in rows) + 6
        if h is None:
            return tot
        self.frame(x, y, w, h)
        cy = y + 10
        if title:
            self.T(x + 14, cy + 2, title, 19, 500, maxw=w - 28)
            cy += 34
        for k, r in rows:
            if k == "div":
                if self.pen:
                    self.pen.line([(x + 12, cy + 6), (x + w - 12, cy + 6)], GREY, 1)
                cy += 12
                continue
            mid = cy + RH / 2.0
            if k == "ent":
                eid = r["entity"]
                if r.get("type") == "attribute":
                    v = ((self.st(eid) or {}).get("a") or {}).get(r.get("attribute"))
                    v = "—" if v is None else (render.num(v) or str(v))
                    v = "%s%s%s" % (r.get("prefix") or "", v, r.get("suffix") or "")
                else:
                    v = self.state(eid)
                self.I(self.ic(eid, r.get("icon")), x + 12, mid - 12, 24)
                vw = min(self.tw(v, 16, 500), w * 0.45)
                self.T(x + w - 14, mid, v, 16, 500, anchor="rm", maxw=w * 0.45)
                self.T(x + 50, mid, self.name(eid, r.get("name")), 16, 400, anchor="lm",
                       maxw=w - 70 - vw)
            elif k == "sec":
                self.T(x + 14, mid, str(r.get("label") or ""), 16, 500, fill=INK2, anchor="lm", maxw=w - 28)
            else:
                self.T(x + 50, mid, str(r.get("name")), 16, 400, anchor="lm", maxw=w - 64)
            cy += RH
        return h

    def k_glance(self, c, x, y, w, h):
        ents = [e if isinstance(e, dict) else {"entity": e} for e in c.get("entities") or []]
        ents = [e for e in ents if isinstance(e, dict) and e.get("entity")]
        if not ents:
            return 0
        title = self.title_h(c)
        n = int(c.get("columns") or min(5, len(ents)))
        lines = int(math.ceil(len(ents) / float(n)))
        show_n, show_i, show_s = (c.get("show_name", True), c.get("show_icon", True), c.get("show_state", True))
        lh = 8 + (22 if show_n else 0) + (34 if show_i else 0) + (22 if show_s else 0)
        if h is None:
            return 10 + (34 if title else 0) + lines * lh + 6
        self.frame(x, y, w, h)
        cy = y + 10
        if title:
            self.T(x + 14, cy + 2, title, 19, 500, maxw=w - 28)
            cy += 34
        cw = (w - 8) / float(n)
        for i, e in enumerate(ents):
            cx = x + 4 + cw * (i % n) + cw / 2.0
            ty = cy + (i // n) * lh + 4
            eid = e["entity"]
            if show_n and e.get("show_name", True):
                self.T(cx, ty, self.name(eid, e.get("name")), 14, 400, fill=INK2, anchor="ma", maxw=cw - 4)
                ty += 22
            if show_i and e.get("show_icon", True):
                self.I(self.ic(eid, e.get("icon")), cx - 14, ty, 28)
                ty += 34
            if show_s and e.get("show_state", True):
                self.T(cx, ty, self.state(eid), 15, 500, anchor="ma", maxw=cw - 4)
        return h

    _MDCLEAN = [(re.compile(r"<br\s*/?>|</p>|</div>|</li>|</h\d>", re.I), "\n"),
                (re.compile(r"<[^>]+>"), ""), (re.compile(r"^\s{0,3}#{1,6}\s*", re.M), ""),
                (re.compile(r"\*\*|__|(?<!\w)[*_](?!\s)|(?<!\s)[*_](?!\w)"), ""),
                (re.compile(r"^\s*[-*]\s+", re.M), "• "), (re.compile(r"\n{3,}"), "\n\n")]

    def k_markdown(self, c, x, y, w, h):
        txt = self.tpl(str(c.get("content") or ""))
        for rx, rep in self._MDCLEAN:
            txt = rx.sub(rep, txt)
        txt = txt.replace("&nbsp;", " ").replace("&amp;", "&").strip()
        title = self.title_h(c)
        lines = Pen.wrap(Pen, txt, 16, 400, w - 28) if txt else []
        lines = lines[:30]
        if not lines and not title:
            return 0
        tot = 12 + (34 if title else 0) + 22 * len(lines) + 8
        if h is None:
            return tot
        self.frame(x, y, w, h)
        cy = y + 12
        if title:
            self.T(x + 14, cy, title, 19, 500, maxw=w - 28)
            cy += 34
        for ln in lines:
            if cy + 22 > y + h:
                break
            self.T(x + 14, cy, ln, 16, 400, maxw=w - 28)
            cy += 22
        return h

    def k_heading(self, c, x, y, w, h):
        t = str(c.get("heading") or "")
        if not t:
            return 0
        if h is None:
            return 36
        size = 20 if c.get("heading_style") != "subtitle" else 16
        tx = x + 4
        if c.get("icon"):
            self.I(icons.from_mdi(c.get("icon")) or "dot", tx, y + h / 2.0 - 11, 22)
            tx += 28
        self.T(tx, y + h / 2.0, t, size, 500, anchor="lm", maxw=w - (tx - x))
        bx = tx + self.tw(t, size, 500) + 12
        for bd in c.get("badges") or []:
            eid = bd if isinstance(bd, str) else (bd.get("entity") if isinstance(bd, dict) else None)
            if not eid:
                continue
            v = self.state(eid)
            if bx + self.tw(v, 15, 400) + 26 > x + w:
                break
            self.I(self.ic(eid, bd.get("icon") if isinstance(bd, dict) else None), bx, y + h / 2.0 - 9, 18)
            self.T(bx + 22, y + h / 2.0, v, 15, 400, fill=INK2, anchor="lm")
            bx += 22 + self.tw(v, 15, 400) + 14
        return h

    def k_fallback(self, c, x, y, w, h):
        """Card not handled: "name: state" list of the entities it cites."""
        title = (c.get("title") or c.get("name") or c.get("card_header") or c.get("header") or "")
        if not isinstance(title, str) or "[[[" in title or render.has_tpl(title):
            title = ""
        ents = []
        for e in c.get("entities") or []:
            eid = e if isinstance(e, str) else (e.get("entity") if isinstance(e, dict) else None)
            if isinstance(eid, str) and eid not in ents:
                ents.append(eid)
        if c.get("entity") and c["entity"] not in ents:
            ents.insert(0, c["entity"])
        if not ents:
            ents = sorted(render.collect_entities(c))
        ents = [e for e in ents if not e.startswith("camera.")][:8]
        if not ents:
            return 0
        RH = 30
        tot = 10 + (32 if title else 0) + RH * len(ents) + 6
        if h is None:
            return tot
        self.frame(x, y, w, h)
        cy = y + 10
        if title:
            self.T(x + 14, cy, title, 18, 500, maxw=w - 28)
            cy += 32
        for eid in ents:
            if cy + RH > y + h + 2:
                break
            v = self.state(eid)
            vw = min(self.tw(v, 16, 500), w * 0.5)
            self.T(x + w - 14, cy + RH / 2.0, v, 16, 500, anchor="rm", maxw=w * 0.5)
            self.T(x + 14, cy + RH / 2.0, self.name(eid) + " :", 16, 400, anchor="lm", maxw=w - 36 - vw)
            cy += RH
        return h


def draw_png(dash, view_idx, W=600, H=800, rotate=0):
    """PNG image (bytes) of the view. Content too tall: everything is shrunk to fit."""
    views = (dash.config or {}).get("views") or []
    v = views[view_idx] if 0 <= view_idx < len(views) else {}
    sc = Scene(dash, datetime.now())
    s = 1.0
    vw, vh = float(W), float(H)
    for _ in range(3):
        need = sc.view(v, vw, draw=False)
        if need <= vh + 0.5:
            break
        s = max(0.6, s * vh / need)
        vw, vh = W / s, H / s
        if s <= 0.6:
            break
    sc.pen = Pen(vw, vh)
    # Content shorter than the screen: centred top to bottom (same margin at top and bottom).
    need = sc.view(v, vw, draw=False)
    used = need - PAD - (2 * GAP if v.get("type") == "sections" else GAP)
    off = max(0.0, (vh - used) / 2.0 - PAD)
    sc.view(v, vw, draw=True, y0=off)
    if not dash.hub.connected:
        sc.pen.d.rectangle((0, (vh - 30) * SS, vw * SS, vh * SS), fill=INK)
        sc.pen.text(vw / 2.0, vh - 15, "Home Assistant injoignable", 16, 500, fill=255, anchor="mm")
    img = sc.pen.img.resize((W, H), Image.LANCZOS)
    # E-ink: dark greys a little darker (sharper text), then 16 levels.
    lut = [min(255, int(round(((i / 255.0) ** 1.35) * 15)) * 17) for i in range(256)]
    img = img.point(lut)
    if rotate in (90, 180, 270):
        img = img.rotate(rotate, expand=True)
    out = io.BytesIO()
    img.save(out, "PNG", compress_level=6)
    return out.getvalue()


# --------------------------------------------------------------------------
# Serveur
# --------------------------------------------------------------------------
_cache = {}         # (dash, view, size, rotation) -> (content key, png, etag)
_lock = None


async def h_png(req):
    if Image is None:
        raise web.HTTPServiceUnavailable(text="Pillow missing: type 0 unavailable")
    dash = _sd["get_dash"](req)
    ref = req.query.get("view") or _sd["default_ref"](dash)
    view, idx = _sd["pick_view"](dash, ref)
    if view is None or dash.config is None:
        raise web.HTTPServiceUnavailable(text=dash.error or "Connecting to Home Assistant…",
                                         headers={"Retry-After": "10"})
    try:
        W = max(200, min(2000, int(req.query.get("w") or 600)))
        H = max(200, min(2000, int(req.query.get("h") or 800)))
        rot = int(req.query.get("rotate") or 0)
    except ValueError:
        raise web.HTTPBadRequest(text="w, h, rotate : nombres attendus")
    if rot in (90, 270):
        W, H = H, W     # w x h = screen size; drawing is done in the reading direction
    var = dash.variant("t1")      # makes the histories, forecasts and templates load
    if var is None:
        raise web.HTTPServiceUnavailable(text="Rendering in progress", headers={"Retry-After": "5"})
    vidx = view["index"]
    hub = dash.hub
    content = (dash.cv, max(var.slot_ver or [0]), hub.connected, int(time.time() // 60))
    ck = (dash.name, vidx, W, H, rot)
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    async with _lock:
        ent = _cache.get(ck)
        if not ent or ent[0] != content:
            t0 = time.time()
            png = await asyncio.get_running_loop().run_in_executor(None, draw_png, dash, vidx, W, H, rot)
            ms = (time.time() - t0) * 1000
            log.debug("[%s] type 0 view %d: %d bytes in %.0f ms", dash.name, vidx, len(png), ms)
            etag = '"%s"' % hashlib.md5(png).hexdigest()[:16]
            ent = (content, png, etag, ms)
            _cache[ck] = ent
    _, png, etag, ms = ent
    hdr = {"Cache-Control": "no-cache", "ETag": etag, "X-Render-Ms": "%.0f" % ms}
    if req.headers.get("If-None-Match") == etag:
        return web.Response(status=304, headers=hdr)
    return web.Response(body=png, content_type="image/png", headers=hdr)


@web.middleware
async def type0(req, handler):
    """/<name>?type=0 -> /<name>.png (same view)."""
    if req.query.get("type") == "0" and re.match(r"^/[A-Za-z0-9][A-Za-z0-9_-]*/?$", req.path):
        q = {k: v for k, v in req.query.items() if k != "type"}
        raise web.HTTPFound(req.rel_url.with_path("/%s.png" % req.path.strip("/")).with_query(q))
    return await handler(req)


_sd = {}


def setup(app, get_dash, pick_view, default_ref):
    """To call before the /{name} route (otherwise "tab3.png" would be taken for a dashboard)."""
    _sd.update(get_dash=get_dash, pick_view=pick_view, default_ref=default_ref)
    app.middlewares.append(type0)
    app.router.add_get("/{name}.png", h_png)
