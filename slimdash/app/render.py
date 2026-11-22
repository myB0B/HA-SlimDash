"""SlimDash - conversion of a Lovelace configuration into simple HTML.

The rendering produces static HTML + "slots": small pieces of the page
(text of a state, on/off class of a tile...) recomputed on the server when
an entity changes, then sent to the browser as tiny JSON.
"""
import hashlib
import html
import logging
import re
from datetime import datetime

import colorsys
import i18n
import icons
import math
import theme

log = logging.getLogger("slimdash.render")

E = html.escape

# Domains toggled (on/off) by a click by default.
TOGGLE_DOMAINS = {
    "light", "switch", "fan", "input_boolean", "automation", "siren",
    "humidifier", "group", "lock",
}
# Domains toggled by the header switch of an entities card (HA DOMAINS_TOGGLE).
HEADER_TOGGLE = ("fan", "input_boolean", "light", "switch", "group", "automation", "humidifier", "valve")
# Rows whose value can be edited in the entities card (field, list, time).
EDIT_DOMAINS = ("number", "input_number", "select", "input_select", "time", "input_datetime",
                "text", "input_text", "date")
# Temperature unit of Home Assistant (unit system), used when an entity gives none (climate...).
TEMP_UNIT = "°C"


def climate_range(a):
    """(min, max, step) of the set point of a climate entity, in its unit."""
    fahr = a.get("temperature_unit", TEMP_UNIT) == "\u00b0F"

    def f(k, d):
        try:
            return float(a.get(k))
        except (TypeError, ValueError):
            return d
    lo, hi = f("min_temp", 45.0 if fahr else 7.0), f("max_temp", 95.0 if fahr else 35.0)
    if hi <= lo:
        hi = lo + 1
    return lo, hi, f("target_temp_step", 1.0 if fahr else 0.5) or 0.5


def set_temp_unit(unit):
    """Unit from get_config: "°C" or "°F" (anything else keeps °C). True if changed."""
    global TEMP_UNIT
    new = unit if unit in ("°C", "°F") else "°C"
    changed = new != TEMP_UNIT
    TEMP_UNIT = new
    return changed


# Climate: colour of each mode (dial arc) and label of the action, English fallbacks.
CLIMATE_COLORS = {"heat": "#ff6f22", "cool": "#2196f3", "heat_cool": "#4caf50", "auto": "#4caf50",
                  "dry": "#ffc107", "fan_only": "#00bcd4"}      # measured on the HA thermostat card
CLIMATE_OFF = "#9e9e9e"
MODE_ICONS = {"off": "mdi:power", "heat": "mdi:fire", "cool": "mdi:snowflake", "auto": "mdi:thermostat-auto",
              "heat_cool": "mdi:sun-snowflake-variant", "dry": "mdi:water-percent", "fan_only": "mdi:fan"}
ACTION_COLORS = {"heating": "heat", "cooling": "cool", "drying": "dry", "fan": "fan_only"}
ACTION_TXT = {"heating": "Heating", "cooling": "Cooling", "idle": "Idle", "off": "Off",
              "drying": "Drying", "fan": "Fan", "preheating": "Preheating",
              "defrosting": "Defrosting"}

RUN_DOMAINS = {"scene": "Activate", "script": "Run", "button": "Press",
               "input_button": "Press"}

ON_STATES = {"on", "open", "opening", "unlocked", "playing", "home", "cleaning",
             "heat", "cool", "heat_cool", "auto", "dry", "fan_only", "active",
             "above_horizon", "returning", "buffering"}
OFF_STATES = {"off", "closed", "closing", "locked", "idle", "paused", "standby",
              "not_home", "docked", "below_horizon"}

# English fallback labels, used only when Home Assistant did not give its own (TR below).
STATE_TXT = {
    "unavailable": "Unavailable", "unknown": "Unknown",
    "open": "Open", "closed": "Closed", "opening": "Opening",
    "closing": "Closing", "locked": "Locked", "unlocked": "Unlocked",
    "locking": "Locking", "unlocking": "Unlocking", "jammed": "Jammed",
    "playing": "Playing", "paused": "Paused", "idle": "Idle",
    "standby": "Standby", "buffering": "Buffering",
    "home": "Home", "not_home": "Away",
    "docked": "Docked", "cleaning": "Cleaning", "returning": "Returning to dock",
    "error": "Error",
    "heat": "Heat", "cool": "Cool", "heat_cool": "Heat/Cool",
    "auto": "Auto", "dry": "Dry", "fan_only": "Fan only",
    "above_horizon": "Day", "below_horizon": "Night",
    "armed_away": "Armed away", "armed_home": "Armed home",
    "armed_night": "Armed night", "disarmed": "Disarmed",
    "triggered": "Triggered", "pending": "Pending", "arming": "Arming",
}

BINARY_TXT = {
    "motion": ("Detected", "Clear"), "occupancy": ("Detected", "Clear"),
    "presence": ("Home", "Away"), "door": ("Open", "Closed"),
    "garage_door": ("Open", "Closed"), "window": ("Open", "Closed"),
    "opening": ("Open", "Closed"), "moisture": ("Wet", "Dry"),
    "smoke": ("Smoke!", "OK"), "gas": ("Gas!", "OK"),
    "problem": ("Problem", "OK"), "safety": ("Unsafe", "Safe"),
    "battery": ("Low", "Normal"), "connectivity": ("Connected", "Disconnected"),
    "plug": ("Plugged in", "Unplugged"), "power": ("Power on", "Power off"),
    "lock": ("Unlocked", "Locked"), "running": ("Running", "Not running"),
    "light": ("Light", "No light"), "sound": ("Sound", "Clear"),
    "vibration": ("Vibration", "Clear"), "tamper": ("Tampering", "OK"),
    "update": ("Update available", "Up to date"), "heat": ("Hot", "Normal"),
    "cold": ("Cold", "Normal"),
}

WEATHER_TXT = {
    "clear-night": "Clear, night", "cloudy": "Cloudy", "fog": "Fog",
    "hail": "Hail", "lightning": "Lightning", "lightning-rainy": "Lightning, rainy",
    "partlycloudy": "Partly cloudy", "pouring": "Pouring", "rainy": "Rainy",
    "snowy": "Snowy", "snowy-rainy": "Snowy, rainy", "sunny": "Sunny",
    "windy": "Windy", "windy-variant": "Windy", "exceptional": "Exceptional",
}

# Home Assistant state labels ("domain.class.state" -> text), filled by the
# server on connection. The tables above are now only a fallback.
TR = {}


def tr_state(dom, device_class, s):
    """HA label of a state (e.g. switch on -> "On"), or None."""
    if not TR or s is None:
        return None
    t = TR.get("%s.%s.%s" % (dom, device_class or "_", s))
    if t is None and device_class:
        t = TR.get("%s._.%s" % (dom, s))
    return t


def tr_attr(name, value):
    """HA label of the value of a climate attribute (hvac_action, fan_mode...), or None."""
    return TR.get("attr.%s.%s" % (name, value)) if value is not None else None


def weather_txt(s):
    return tr_state("weather", None, s) or WEATHER_TXT.get(s, s or "")


def domain_of(eid):
    return eid.split(".", 1)[0] if isinstance(eid, str) else ""


def num(v):
    """Number in the language of Home Assistant (decimal and thousands separators), else None."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    if f == int(f) and abs(f) < 1e15 and "." not in str(v):
        s = str(int(f))
    else:
        s = str(v) if isinstance(v, str) else ("%g" % f)
    return group(s)


def group(numstr):
    """"1003.5" -> "1,003.5" / "1 003,5"... (see i18n.group_digits)."""
    return i18n.group_digits(numstr)


def round_num(v, decimals):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return group(("%." + str(int(decimals)) + "f") % f)


def fmt_time(iso):
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone()
    except (ValueError, TypeError):
        return str(iso)
    now = datetime.now().astimezone()
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    return i18n.date_short(dt) + " " + dt.strftime("%H:%M")


def since(ts):
    """Timestamp of the last change -> "since 14:32" / "since 11/12"."""
    if not ts:
        return "—"
    try:
        dt = datetime.fromtimestamp(float(ts)).astimezone() if not isinstance(ts, str) \
            else datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
    except (TypeError, ValueError, OSError):
        return "—"
    now = datetime.now().astimezone()
    if dt.date() == now.date():
        return i18n.D["st"] % dt.strftime("%H:%M")
    return i18n.D["sd"] % i18n.date_short(dt)


def ts_epoch(ts):
    """HA timestamp (number or ISO text) -> seconds since 1970, or None."""
    if not ts:
        return None
    try:
        if not isinstance(ts, str):
            return float(ts)
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError, OSError):
        return None


def rel_time(t, now=None, total=False):
    """Elapsed time (see i18n.rel_time); relTime() in s.js keeps it up to date."""
    return i18n.rel_time(t, now, total)


def rel_span(ts, total=False):
    """Elapsed time kept up to date by s.js (class ago, timestamp in data-t;
    data-m="t" for a duration without "il y a")."""
    t = ts_epoch(ts)
    if t is None:
        return "—"
    return '<span class="ago" data-t="%d"%s>%s</span>' % (
        t, ' data-m="t"' if total else "", E(rel_time(t, total=total)))


def ts_format(st, fmt=None):
    """Display format of a timestamp sensor, like HA (None if it is not one):
    "relative" for a timestamp, "total" for an operating time."""
    if not st or ts_epoch(st.get("s")) is None or not isinstance(st.get("s"), str) or "T" not in st["s"]:
        return None
    dc = (st.get("a") or {}).get("device_class")
    if dc not in ("timestamp", "uptime"):
        return None
    if fmt in ("relative", "total", "date", "time", "datetime"):
        return fmt
    return "total" if dc == "uptime" else "relative"


def ts_html(st, fmt):
    """HTML value of a timestamp sensor according to its format (see ts_format)."""
    s = st.get("s")
    if fmt in ("relative", "total"):
        return rel_span(s, fmt == "total")
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone()
    except (ValueError, TypeError):
        return E(s)
    return E({"date": i18n.date_full(dt), "time": dt.strftime("%H:%M"),
              "datetime": i18n.date_full(dt) + " " + dt.strftime("%H:%M")}[fmt])


def cap(txt):
    return txt[:1].upper() + txt[1:]


def fmt_state(st, eid, decimals=None):
    """Text (not escaped) of the state of an entity, Home Assistant style."""
    if st is None:
        return "—"
    s = st.get("s")
    a = st.get("a") or {}
    dom = domain_of(eid)
    if s in ("unavailable", "unknown"):
        return STATE_TXT[s]
    t = tr_state(dom, a.get("device_class"), s)
    if dom == "light" and s == "on" and a.get("brightness") is not None:
        try:        # like HA: the brightness replaces "On"
            return "%d %%" % round(int(a["brightness"]) * 100 / 255)
        except (TypeError, ValueError):
            pass
    if t is not None and dom not in ("weather", "climate", "cover"):
        return t
    if dom == "binary_sensor":
        pair = BINARY_TXT.get(a.get("device_class"), ("On", "Off"))
        return pair[0] if s == "on" else pair[1]
    if dom in ("light", "fan", "input_boolean", "siren", "humidifier"):
        if s == "on" and dom == "light" and a.get("brightness") is not None:
            try:
                return "On %d %%" % round(int(a["brightness"]) * 100 / 255)
            except (TypeError, ValueError):
                pass
        if s == "on" and dom == "fan" and a.get("percentage"):
            return "On %s %%" % a.get("percentage")
        return {"on": "On", "off": "Off"}.get(s, s)
    if dom in ("switch", "automation", "media_player", "group", "remote"):
        if s in ("on", "off"):
            return {"on": "On", "off": "Off"}[s]
    if dom == "weather":
        temp = a.get("temperature")
        txt = weather_txt(s)
        if temp is not None:
            txt += " %s %s" % (num(temp) or temp, a.get("temperature_unit", TEMP_UNIT))
        return txt
    if dom == "climate":
        cur = a.get("current_temperature")
        txt = t or (STATE_TXT.get(s, s) if s != "off" else "Off")
        if cur is not None:
            txt += " · %s %s" % (num(cur) or cur, a.get("temperature_unit", TEMP_UNIT))
        return txt
    if dom == "cover" and a.get("current_position") is not None and s == "open":
        return "%s %s %%" % (t or "Open", a.get("current_position"))
    if t is not None:
        return t
    tf = ts_format(st)
    if tf:
        t = ts_epoch(s)
        return cap(rel_time(t, total=tf == "total"))
    if dom in ("input_datetime",) and "T" in str(s):
        return fmt_time(s)
    if s in STATE_TXT:
        return STATE_TXT[s]
    unit = a.get("unit_of_measurement")
    n = round_num(s, decimals) if decimals is not None else num(s)
    if n is not None:
        return n + (" " + unit if unit else "")
    return s + (" " + unit if unit else "")


def kelvin_rgb(k):
    """Colour of a white of k kelvins (same formula as the HA frontend)."""
    t = k / 100.0
    if t <= 66:
        r = 255.0
        g = 99.4708025861 * math.log(t) - 161.1195681661
    else:
        r = 329.698727446 * ((t - 60) ** -0.1332047592)
        g = 288.1221695283 * ((t - 60) ** -0.0755148492)
    if t >= 66:
        b = 255.0
    elif t <= 19:
        b = 0.0
    else:
        b = 138.5177312231 * math.log(t - 10) - 305.0447927307
    return tuple(int(round(max(0.0, min(255.0, x)))) for x in (r, g, b))


def state_class(st):
    if st is None:
        return "na"
    s = st.get("s")
    if s in ("unavailable", "unknown"):
        return "na"
    if s in ON_STATES:
        return "on"
    if s in OFF_STATES:
        return "off"
    return ""


def entity_name(st, eid, cfg_name=None):
    if isinstance(cfg_name, str) and cfg_name:
        return cfg_name
    if st is not None:
        fn = (st.get("a") or {}).get("friendly_name")
        if fn:
            return fn
    return eid.split(".", 1)[-1].replace("_", " ") if isinstance(eid, str) else ""


def collect_entities(obj, out=None):
    """All the entity_ids cited in a config (recursive)."""
    if out is None:
        out = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("entity", "entity_id", "camera_image", "camera_entity", "image_entity") and isinstance(v, str) and "." in v:
                out.add(v)
            elif k in ("entity_id",) and isinstance(v, list):
                out.update(x for x in v if isinstance(x, str) and "." in x)
            elif k == "entities" and isinstance(v, list):
                for e in v:
                    if isinstance(e, str) and "." in e:
                        out.add(e)
                    else:
                        collect_entities(e, out)
            elif k in ("card_mod", "styles", "style"):
                continue
            else:
                collect_entities(v, out)
    elif isinstance(obj, list):
        for x in obj:
            collect_entities(x, out)
    return out


_TAG = re.compile(r"<[^>]+>")


_ENT = re.compile(r"&amp;(#\d{1,7}|#[xX][0-9a-fA-F]{1,6}|[a-zA-Z][a-zA-Z0-9]{1,31});")


def mini_markdown(text):
    """Very simple Markdown -> safe HTML (headings, bold, italic, lists)."""
    text = re.sub(r"(?i)<br\s*/?>", "\n", str(text or ""))
    text = _TAG.sub("", text)
    out = []
    in_list = False
    for line in text.split("\n"):
        # HTML entities written in the markdown (&nbsp;, &#9728;...): rendered like in HA.
        ln = _ENT.sub(r"&\1;", E(line.strip()))
        m = re.match(r"^(#{1,6})\s*(.*)$", ln)
        li = re.match(r"^[-*+]\s+(.*)$", ln)
        if li and not m:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append("<li>%s</li>" % _inline(li.group(1)))
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if m:
            lvl = min(len(m.group(1)) + 1, 4)
            out.append("<h%d>%s</h%d>" % (lvl, _inline(m.group(2)), lvl))
        elif ln:
            out.append("<p>%s</p>" % _inline(ln))
    if in_list:
        out.append("</ul>")
    return "".join(out)


def _inline(s):
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)\*", r"<i>\1</i>", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    return s


def nav_paths(obj, out=None):
    if out is None:
        out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "navigation_path" and isinstance(v, str):
                out.append(v)
            else:
                nav_paths(v, out)
    elif isinstance(obj, list):
        for x in obj:
            nav_paths(x, out)
    return out


def find_view(views, ref):
    """Index of a view: number (0 = first) or path of the view."""
    ref = str(ref).strip()
    if ref.isdigit() and int(ref) < len(views):
        return int(ref)
    for i, v in enumerate(views):
        if str(v.get("path") or "") == ref:
            return i
    return None


def select_views(config, refs):
    """-> (views chosen in the requested order, views to render).

    Views to render = chosen views + those they open (navigate).
    """
    views = config.get("views") or []
    if not views:
        return [], []
    chosen = []
    for r in refs or []:
        i = find_view(views, r)
        if i is None:
            log.warning("View not found: %s", r)
        elif i not in chosen:
            chosen.append(i)
    if not chosen:
        chosen = [next((i for i, v in enumerate(views) if not v.get("subview")), 0)]
    sel, todo = list(chosen), list(chosen)
    while todo:
        for p in nav_paths(views[todo.pop()]):
            j = find_view(views, p.rstrip("/").split("/")[-1].split("?")[0])
            if j is not None and j not in sel:
                sel.append(j)
                todo.append(j)
    return chosen, sorted(sel)


POINTS = {"t1": 48, "t2": 48, "t3": 96}
HIST_POINTS = 96          # points computed by the server (subsampled afterwards)
MAX_HOURS = 24 * 31       # limit of the graphs
HEX = re.compile(r"^#[0-9a-fA-F]{3,8}$")
SERIES_COLORS = ["#4269d0", "#f4bd4a", "#ff725c", "#6cc5b0"]
# Default colour of a curve depending on what it measures (when the card gives none).
TYPE_COLORS = {"temperature": "#43a047", "humidity": "#4fc3f7", "energy": "#c2479a",
               "pressure": "#e53935", "solar": "#fdd835"}
_SOLAR = re.compile(r"solar|solaire|photovolt|\bpv\b|_pv_|_pv$|^pv_|panneau|onduleur|inverter|envoy|enphase", re.I)


MUSHROOM_COLORS = {"red", "pink", "purple", "deep-purple", "indigo", "blue", "light-blue",
                   "cyan", "teal", "green", "light-green", "lime", "yellow", "amber",
                   "orange", "deep-orange", "brown", "grey", "blue-grey", "black", "white",
                   "disabled", "primary", "accent"}
# Entities without an on/off state: the colour of a card (colour option) always applies.
STATELESS = {"button", "input_button", "scene", "script", "event"}
SAFE_COLOR = re.compile(r"^(#[0-9a-fA-F]{3,8}|rgba?\([0-9\s.,%]+\)|[a-zA-Z]{3,20})$")


def mc_class(color):
    c = str(color or "").strip().lower()
    return ("mc-" + c) if c in MUSHROOM_COLORS else ""


def tkey(template):
    return "t" + hashlib.sha1(template.encode("utf-8")).hexdigest()[:12]


def has_tpl(s):
    return isinstance(s, str) and ("{{" in s or "{%" in s)


def num_value(st):
    try:
        return float(st.get("s")) if st else None
    except (TypeError, ValueError):
        return None


def fmt_num(v):
    if v is None:
        return "—"
    s = ("%.1f" % v) if abs(v) < 100 else ("%.0f" % v)
    if s.endswith(".0"):
        s = s[:-2]
    return s.replace(".", i18n.D["dec"])


def spark_svg(series, h, labels=None, fill=True, pre="", gid="g"):
    """SVG curve(s); each series has its own scale (like "y_axis: independent").
    Series = (values, colour[, thresholds]); thresholds = [(value, (r, g, b))] sorted: the curve
    gets a vertical gradient (colour depending on the height), like color_thresholds.
    pre = drawing placed behind the curves (bars)."""
    W = 300.0
    parts = [pre] if pre else []
    for si, ser in enumerate(series):
        vals, color = ser[0], ser[1]
        stops = ser[2] if len(ser) > 2 else None
        sfill = ser[3] if len(ser) > 3 else None     # fill specific to the series (show_fill)
        pts = [v for v in vals if v is not None]
        if len(pts) < 2:
            continue
        lo, hi = min(pts), max(pts)
        rng = (hi - lo) or 1.0
        if stops:
            # offset 0 = bottom of the curve (lo), 1 = top (hi)
            gs, prev = [], None
            for v, rgb in stops:
                off = (v - lo) / rng
                if off < 0:
                    prev = (off, rgb)
                    continue
                if prev is not None and not gs:
                    gs.append((0.0, mix_color([(prev[0], prev[1]), (off, rgb)], 0.0)))
                if off > 1:
                    last = gs[-1] if gs else (0.0, "#%02x%02x%02x" % rgb)
                    gs.append((1.0, mix_color([(last[0], hex_rgb(last[1])), (off, rgb)], 1.0)))
                    break
                gs.append((off, "#%02x%02x%02x" % rgb))
            if not gs:
                gs = [(0.0, "#%02x%02x%02x" % stops[-1][1])]
            gname = "%s_%d" % (gid, si)
            parts.append('<defs><linearGradient id="%s" gradientUnits="userSpaceOnUse" x1="0" y1="%d" x2="0" y2="3">%s</linearGradient></defs>'
                         % (gname, h - 3, "".join('<stop offset="%.3f" stop-color="%s"/>' % (o, c) for o, c in gs)))
            color = "url(#%s)" % gname
        n = len(vals)
        segs, cur = [], []
        for i, v in enumerate(vals):
            if v is None:
                if cur:
                    segs.append(cur)
                    cur = []
                continue
            cur.append((W * i / (n - 1), (h - 3) - (v - lo) / rng * (h - 6)))
        if cur:
            segs.append(cur)
        for s in segs:
            if len(s) < 2:
                continue
            p = " ".join("%.1f,%.1f" % xy for xy in s)
            if fill and (sfill if sfill is not None else len(series) == 1):
                parts.append('<polygon points="%.1f,%d %s %.1f,%d" style="fill:%s"/>'
                             % (s[0][0], h, p, s[-1][0], h, color))
            parts.append('<polyline points="%s" style="stroke:%s"/>' % (p, color))
    if not parts:
        return '<div class="sp nodata">Pas encore d\'historique</div>'
    svg = ('<svg class="sp" viewBox="0 0 300 %d" preserveAspectRatio="none" style="height:%dpx">%s</svg>'
           % (h, h, "".join(parts)))
    if labels:
        svg += '<div class="mm"><span>%s</span><span>%s</span></div>' % labels
    return svg


def bars_svg(vals, h, color, n):
    """Histogram: n bars (averages), min-max scale, minimum bar visible."""
    rects = bar_rects(vals, h, n)
    if not rects:
        return '<div class="sp nodata">Pas encore d\'historique</div>'
    return ('<svg class="sp bars" viewBox="0 0 300 %d" preserveAspectRatio="none" '
            'style="height:%dpx;fill:%s">%s</svg>' % (h, h, color, rects))


def bar_rects(vals, h, n):
    pts = [v for v in vals if v is not None]
    if len(pts) < 2:
        return ''
    step = len(vals) / float(n)
    groups = []
    for i in range(n):
        chunk = [v for v in vals[int(i * step):int((i + 1) * step)] if v is not None]
        groups.append(sum(chunk) / len(chunk) if chunk else None)
    g = [v for v in groups if v is not None]
    lo, hi = min(g), max(g)
    rng = (hi - lo) or 1.0
    W = 300.0
    bw = W / n
    gap = min(4.0, bw * 0.15)
    rects = []
    for i, v in enumerate(groups):
        if v is None:
            continue
        bh = 4 + (v - lo) / rng * (h - 8)
        rects.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f"/>' % (
            i * bw + gap / 2, h - bh, bw - gap, bh))
    return "".join(rects)


def mix_color(stops, v):
    """Colour interpolated between sorted thresholds [(value, (r, g, b))]."""
    if v <= stops[0][0]:
        c = stops[0][1]
    elif v >= stops[-1][0]:
        c = stops[-1][1]
    else:
        c = stops[-1][1]
        for (v0, c0), (v1, c1) in zip(stops, stops[1:]):
            if v0 <= v <= v1:
                f = (v - v0) / float((v1 - v0) or 1)
                c = tuple(c0[i] + (c1[i] - c0[i]) * f for i in range(3))
                break
    return "#%02x%02x%02x" % tuple(int(round(x)) for x in c)


def hex_rgb(c):
    c = str(c or "").strip().lstrip("#")
    if len(c) == 3:
        c = "".join(x * 2 for x in c)
    if not re.match(r"^[0-9a-fA-F]{6}$", c):
        return None
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


def css_px(v, default, base=14.0):
    """« 4em », « 20px », 30 -> pixels."""
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(px|em|rem)?\s*$", str(v if v is not None else ""))
    if not m:
        return default
    n = float(m.group(1))
    return n * base if m.group(2) in ("em", "rem") else n


RAINBOW = "#f00 0%, #ff0 16.7%, #0f0 33.3%, #0ff 50%, #00f 66.7%, #f0f 83.3%, #f00 100%"

# Domains that have the HA tiles "toggle" feature.
TOGGLE_FEATURE = ("light", "switch", "fan", "input_boolean", "siren", "humidifier",
                  "water_heater", "climate", "media_player", "automation", "remote")

def img_path(image, modern):
    """image (picture card, view background) -> HA path (/local/..., /api/image/serve/...) or http(s) URL.
    Image uploaded in HA (media-source://image_upload/ID): 512 px except on type 3, original otherwise."""
    if isinstance(image, dict):
        image = image.get("media_content_id")
    if not isinstance(image, str) or not image.strip() or "{" in image:
        return None
    image = image.strip()
    m = re.match(r"media-source://image_upload/([0-9a-f]+)$", image)
    if m:
        return "/api/image/serve/%s/%s" % (m.group(1), "original" if modern else "512x512")
    if image.startswith("/") and not image.startswith("//"):
        return image
    if re.match(r"https?://", image):
        return image
    return None


class Builder:
    """Builds the HTML views of a device type and records slots + actions."""

    def __init__(self, store, dashboard_path, cls="t1"):
        self.store = store
        self.dash = dashboard_path
        self.cls = cls
        self.modern = cls == "t3"
        self.slots = []        # (deps, fn)
        self.actions = []      # dicts
        self.view_refs = {}    # path -> index
        self.icons = set()     # icons used (sprite)
        self.need_tpl = {}     # key -> Jinja template (rendered by HA)
        self.need_fc = set()   # (weather entity, forecast type)
        self.need_hist = {}    # key -> (entity, hours)
        self.cams = set()      # cameras allowed for this rendering
        self.imgs = {}         # key -> picture card image (HA path, URL or entity)
        self.pending_side = ""  # dots to place to the right of the next tile
        self.in_sic = 0         # > 0 while rendering a stack-in-card
        self.in_stack = 0       # > 0 inside a stack or a grid (free heights)

    # ---- slots / actions -------------------------------------------------
    def slot(self, deps, fn):
        self.slots.append((tuple(deps), fn))
        return "s%d" % (len(self.slots) - 1)

    def st(self, eid):
        return self.store.states.get(eid)

    def kind_color(self, eid):
        """Default colour depending on the kind of measurement, or None (keep the palette)."""
        st = self.st(eid) or {}
        a = st.get("a") or {}
        dc = str(a.get("device_class") or "")
        u = str(a.get("unit_of_measurement") or "")
        if dc in ("energy", "power", "apparent_power", "reactive_power") or u in (
                "W", "kW", "MW", "Wh", "kWh", "MWh", "VA", "kVA"):
            name = "%s %s" % (eid, a.get("friendly_name") or "")
            return TYPE_COLORS["solar" if _SOLAR.search(name) else "energy"]
        if dc == "irradiance" or u == "W/m²":
            return TYPE_COLORS["solar"]
        if dc == "temperature" or u in ("°C", "°F", "K"):
            return TYPE_COLORS["temperature"]
        if dc in ("humidity", "moisture"):
            return TYPE_COLORS["humidity"]
        if dc in ("pressure", "atmospheric_pressure") or u in ("hPa", "mbar", "bar", "Pa", "kPa", "inHg", "mmHg", "psi"):
            return TYPE_COLORS["pressure"]
        return None

    def series_color(self, eid, color, i, fallback=None):
        """Colour of a curve: that of the card, otherwise that of the type, otherwise the palette."""
        if color and HEX.match(str(color)):
            return color
        return self.kind_color(eid) or fallback or SERIES_COLORS[i % len(SERIES_COLORS)]

    def prec(self, eid):
        """Display precision set in HA (entity registry)."""
        return (self.store.reg.get(eid) or {}).get("dp")

    def nm(self, eid, cfg_name=None):
        """Name to display: text, or object/list {type: device|entity|area|text}."""
        if isinstance(cfg_name, (dict, list)):
            parts = []
            reg = self.store.reg.get(eid) or {}
            for p in (cfg_name if isinstance(cfg_name, list) else [cfg_name]):
                if isinstance(p, str):
                    parts.append(p)
                    continue
                if not isinstance(p, dict):
                    continue
                t = p.get("type")
                if t == "text":
                    parts.append(str(p.get("text") or ""))
                elif t == "device":
                    parts.append(reg.get("dn") or "")
                elif t == "area":
                    parts.append(reg.get("an") or "")
                elif t == "entity":
                    parts.append(reg.get("en") or "")
            txt = " ".join(x for x in parts if x).strip()
            if txt:
                return txt
            cfg_name = None
        if isinstance(cfg_name, str) and ("[[[" in cfg_name or has_tpl(cfg_name)):
            cfg_name = None
        return entity_name(self.st(eid), eid, cfg_name)

    def text_slot(self, eid, fn=None, tag="span", cls="", fmt=None):
        if fn is None:
            def fn(e=eid):
                st = self.st(e)
                tf = ts_format(st, fmt)
                if tf:      # timestamp: "1 mois", "Il y a 3 heures"... like HA
                    return (ts_html(st, tf), None)
                return (E(fmt_state(st, e, self.prec(e))), None)
        sid = self.slot([eid], fn)
        val = fn()[0]
        c = ' class="%s"' % cls if cls else ""
        return '<%s id="%s"%s>%s</%s>' % (tag, sid, c, val, tag)

    def content_slots(self, eid, content):
        """Tile `state_content` (text or list: "state", "last_changed", "last_updated", attribute
        name) -> HTML joined with " · ", or None when the option is absent (plain state)."""
        sc = [content] if isinstance(content, str) else \
            [x for x in (content or []) if isinstance(x, str)] if isinstance(content, list) else []
        if not sc:
            return None
        parts = []
        for k in sc[:4]:
            if k == "state":
                parts.append(self.text_slot(eid))
            elif k in ("last_changed", "last_updated", "last-changed", "last-updated"):
                def fn(e=eid):      # relative time, like HA ("3 hours ago")
                    st = self.st(e)
                    return (rel_span(st.get("lc") if st else None), None)
                parts.append(self.text_slot(eid, fn))
            elif re.match(r"^\w+$", k):
                def fn(e=eid, k=k):
                    v = ((self.st(e) or {}).get("a") or {}).get(k)
                    return (E("—" if v is None else (num(v) or str(v))), None)
                parts.append(self.text_slot(eid, fn))
        return " · ".join(parts) if parts else None

    def value_fn(self, eid, decimals=None):
        """State of an entity, the unit apart (displayed smaller)."""
        def fn(x=eid, d=decimals):
            st = self.st(x)
            txt = fmt_state(st, x, self.prec(x) if d is None else d)
            unit = ((st or {}).get("a") or {}).get("unit_of_measurement")
            if unit and txt.endswith(" " + unit):
                return ('%s<span class="u">%s</span>' % (E(txt[:-len(unit) - 1]), E(unit)), None)
            return (E(txt), None)
        return fn

    def tpl_slot(self, template, tag="span", cls="", markdown=False):
        """Text computed by a Home Assistant Jinja template (or fixed text)."""
        c = ' class="%s"' % cls if cls else ""
        if not has_tpl(template):
            txt = mini_markdown(template) if markdown else E(str(template or ""))
            return '<%s%s>%s</%s>' % (tag, c, txt, tag)
        key = tkey(template)
        self.need_tpl[key] = template

        def fn(k=key):
            v = self.store.tpl.get(k)
            if v is None:
                return ("…", None)
            return (mini_markdown(v) if markdown else E(v.strip()), None)
        sid = self.slot(["tpl:" + key], fn)
        return '<%s id="%s"%s>%s</%s>' % (tag, sid, c, fn()[0], tag)

    def light_color(self, eid):
        """Real colour of a lit lamp (rgb_color): "#icon|#dot background";
        "" without information (the theme yellow applies)."""
        st = self.st(eid) or {}
        rgb = (st.get("a") or {}).get("rgb_color")
        if st.get("s") != "on" or not isinstance(rgb, (list, tuple)) or len(rgb) != 3:
            return ""
        try:
            c = tuple(max(0, min(255, int(x))) for x in rgb) + (1.0,)
        except (TypeError, ValueError):
            return ""
        card = theme.parse((getattr(self.store, "palette", None) or {}).get("card") or "#1c1c1c")             or (28, 28, 28, 1.0)
        return theme.hexc(c) + "|" + theme.hexc(theme.blend(c, card, 0.2))

    def box_open(self, base, eid=None, action=None, tag="div", optimistic=False, style=""):
        """Opens a container whose class follows the state (on/off/na); for a lamp,
        the icon also takes its real colour (3rd value of the slot, applied by s.js)."""
        attrs = ""
        cls = base
        if eid:
            if "dc-light" in base.split() and domain_of(eid) == "light":
                def fn(e=eid):
                    return (None, state_class(self.st(e)), self.light_color(e))
            else:
                def fn(e=eid):
                    return (None, state_class(self.st(e)))
            sid = self.slot([eid], fn)
            v = fn()
            cls = base + " " + v[1]
            attrs += ' id="%s" data-b="%s"' % (sid, base)
            if len(v) > 2 and v[2]:
                attrs += ' data-c="%s"' % v[2]
            if optimistic:
                attrs += ' data-o="1"'
        attrs += self.action_attrs(action)
        if style:
            attrs += ' style="%s"' % style
        return '<%s class="%s"%s>' % (tag, cls.strip(), attrs)

    def action_attrs(self, action):
        if not action:
            return ""
        if action.get("kind") == "nav":
            return ' data-n="%s"' % E(str(action["view"]))
        self.actions.append(action)
        return ' data-a="%d"' % (len(self.actions) - 1)

    def resolve_action(self, cfg, eid, default):
        """Lovelace tap_action -> SlimDash action (or None)."""
        cfg = cfg if isinstance(cfg, dict) else {}
        act = cfg.get("action") or default
        if act == "toggle":
            if eid:
                return {"kind": "toggle", "entity": eid}
            return None
        if act in ("call-service", "perform-action"):
            srv = cfg.get("perform_action") or cfg.get("service") or ""
            if "." not in srv:
                return None
            d, s = srv.split(".", 1)
            return {"kind": "service", "domain": d, "service": s,
                    "data": cfg.get("data") or cfg.get("service_data") or {},
                    "target": cfg.get("target")}
        if act == "navigate":
            path = str(cfg.get("navigation_path") or "")
            ref = path.rstrip("/").split("/")[-1]
            if ref and not ref.startswith("#"):
                return {"kind": "nav", "view": ref}
        return None

    def default_tap(self, eid):
        dom = domain_of(eid)
        if dom in TOGGLE_DOMAINS or dom in RUN_DOMAINS or dom == "cover":
            return "toggle"
        return "none"

    # ---- icons, colours, graphs, cameras ---------------------------
    def icon(self, name, cls="ic"):
        if not name:
            return ""
        self.icons.add(name)
        return '<svg class="%s"><use xlink:href="#i-%s"></use></svg>' % (cls, name)

    def ent_icon(self, eid, cfg_icon=None):
        st = self.st(eid) if eid else None
        return self.icon(icons.pick(eid, cfg_icon, (st or {}).get("a")) if eid
                         else (icons.from_mdi(cfg_icon) or "dot"))

    def dc(self, eid, cfg_icon=None):
        """Colour group. For a switch, the chosen icon decides
        (bulb -> yellow like a lamp, fan -> cyan, etc.)."""
        dom = domain_of(eid)
        group = icons.COLOR_GROUP.get(dom, "def")
        if group == "switch" or dom == "group":
            st = self.st(eid) if eid else None
            group = icons.ICON_GROUP.get(
                icons.group_icon(icons.pick(eid, cfg_icon, (st or {}).get("a"))), group)
        return "dc-" + group

    def sprite(self):
        return icons.sprite(self.icons)

    def hist_key(self, eid, hours):
        hours = max(1, min(MAX_HOURS, int(hours or 24)))
        key = "h:%s:%d" % (eid, hours)
        self.need_hist[key] = (eid, hours)
        return key

    def chart(self, entities, hours, height=None, bars=0, cls="chart", barmap=None):
        """entities = [(entity_id, colour or None[, thresholds])] -> HTML of a graph (slot).
        bars = number of bars (histogram only); 0 = curve.
        barmap = {entity rank: number of bars}: bars behind the other curves."""
        barmap = barmap or {}
        npts = POINTS[self.cls]
        h = max(24, min(320, int(height or (80 if self.modern else 56))))
        light = self.cls == "t1"
        keys = []
        for i, ent in enumerate(entities):
            eid, color = ent[0], ent[1]
            stops = tuple(ent[2]) if len(ent) > 2 and ent[2] else None
            sfill = ent[3] if len(ent) > 3 else None
            if stops:
                color = "#%02x%02x%02x" % stops[0][1]
            color = self.series_color(eid, color, i)
            keys.append((self.hist_key(eid, hours), color, eid, stops, sfill))
        gid = "lg%d" % len(self.slots)

        def fn(ks=tuple(keys), n=npts, hh=h):
            if bars:
                k, color = ks[0][0], ks[0][1]
                return (bars_svg(self.store.hist.get(k) or [], hh, color, bars), None)
            series = []
            pre = ""
            for idx, (k, color, eid, stops, sfill) in enumerate(ks):
                vals = self.store.hist.get(k) or []
                if idx in barmap:
                    r = bar_rects(vals, hh, barmap[idx])
                    if r:
                        pre += '<g style="fill:%s;opacity:.85">%s</g>' % (color, r)
                    continue
                if vals and n < len(vals):
                    step = len(vals) / float(n)
                    vals = [vals[int(j * step)] for j in range(n)]
                series.append((vals, color, stops, sfill))
            return (spark_svg(series, hh, None, fill=not light and not barmap, pre=pre, gid=gid), None)
        # Type 1: the curve is only redrawn every 30 min (the value itself is live).
        dep = "hist30:" if light else "hist:"
        sid = self.slot([dep + k[0] for k in keys], fn)
        return '<div id="%s" class="%s">%s</div>' % (sid, cls, fn()[0])

    def camera(self, eid, title="", overlay=""):
        # 360 px high image. data-iv: target interval in ms. Frigate: at the pace of its
        # detection (5 fps usually); the device slows down by itself if it cannot keep up (s.js).
        # HA: 1 image/s. Live video for the Frigate cameras if the browser can.
        self.cams.add(eid)
        src = "/%s/cam?e=%s" % (E(self.store.name), E(eid))
        iv, live = 1000, ""
        fc = (self.store.reg.get(eid) or {}).get("fc") if self.store.frigate else None
        if fc:
            iv = max(100, int(1000 / max(1, self.store.frigate_fps.get(fc) or 5)))
            live = ' data-live="%s"' % E(eid)
        foot = ""
        if title or overlay:
            foot = '<div class="cf"><span class="ct">%s</span>%s</div>' % (E(title or ""), overlay)
        return ('<div class="card cam" data-cn="%s"><img class="ci" src="%s" data-iv="%d"%s alt="">%s</div>'
                % (E(entity_name(self.st(eid), eid)), src, iv, live, foot))

    # ---- vues ------------------------------------------------------------
    def build(self, config, indices=None):
        views = config.get("views") or []
        for i, v in enumerate(views):
            if v.get("path"):
                self.view_refs[str(v["path"])] = i
        result = []
        if indices is None:
            indices = range(len(views))
        for i in indices:
            v = views[i]
            try:
                body = self.view(v)
            except Exception:  # a broken view must not block everything
                log.exception("Error rendering view %s", i)
                body = '<div class="card"><p>Error rendering this view.</p></div>'
            result.append({"index": i, "path": str(v.get("path") or i),
                           "title": v.get("title") or v.get("path") or "View %d" % (i + 1),
                           "subview": bool(v.get("subview")), "body": body})
        return result

    def view(self, v):
        out = []
        if v.get("strategy"):
            return '<div class="card"><p>Automatically generated view (strategy): not supported.</p></div>'
        badges = v.get("badges") or []
        if badges:
            out.append(self.badges(badges))
        if v.get("type") == "sections":
            # c0 / c1: left / right column when the screen allows two (landscape)
            # A section spanning several columns (column_span) takes the whole width
            # available: class spN, outside the left / right alternation.
            n = 0
            for sec in v.get("sections") or []:
                inner = self.sect_cards(sec.get("cards") or [])
                if not inner:
                    continue
                try:
                    span = int(sec.get("column_span") or 1)
                except (TypeError, ValueError):
                    span = 1
                if span > 1:
                    out.append('<div class="sect sp%d">%s</div>' % (min(span, 4), inner))
                else:
                    out.append('<div class="sect c%d">%s</div>' % (n % 2, inner))
                    n += 1
        else:
            cards = v.get("cards") or []
            if v.get("type") == "panel":
                cards = cards[:1]
            for c in cards:
                out.append(self.card(c))
        return "".join(out)

    def badge(self, eid, name=None, icon=None, content=None, color=None, info=None):
        ic = self.ent_icon(eid, icon)
        if content is not None:
            txt = self.tpl_slot(content)
        elif info in ("last-changed", "last-updated"):
            def fn(e=eid):
                st = self.st(e)
                return (E(since(st.get("lc") if st else None)), None)
            txt = self.text_slot(eid, fn)
        else:
            txt = self.text_slot(eid)
        nm = ('<span class="bn">%s</span> ' % E(name)) if name else ""
        mc = mc_class(color)
        if eid and not mc:
            return self.box_open("badge " + self.dc(eid, icon), eid, None, tag="span") + ic + nm + txt + "</span>"
        return '<span class="badge %s">%s%s%s</span>' % (mc, ic, nm, txt)

    def badges(self, badges):
        out = ['<div class="badges">']
        for b in badges:
            if isinstance(b, str):
                b = {"entity": b}
            eid = b.get("entity") if isinstance(b, dict) else None
            if not eid:
                continue
            show_name = b.get("show_name") is True     # HA: name hidden by default
            out.append(self.badge(eid, self.nm(eid, b.get("name")) if show_name else None,
                                  b.get("icon")))
        out.append("</div>")
        return "".join(out)

    # ---- cartes ----------------------------------------------------------
    @staticmethod
    def grid_cr(c):
        """(columns, rows) given explicitly in grid_options, otherwise None."""
        go = c.get("grid_options") if isinstance(c, dict) and isinstance(c.get("grid_options"), dict) else {}
        try:
            return int(go.get("columns")), int(go.get("rows"))
        except (TypeError, ValueError):
            return None, None

    def sect_cards(self, cards):
        """Cards of a section. Like the HA grid ("dense" placement): after a half-width card
        of N rows, the following half cards whose rows fit within those N
        stack in the next column instead of wrapping to the next line."""
        out, i = [], 0
        while i < len(cards):
            c = cards[i]
            cols, rows = self.grid_cr(c)
            j, tot = i + 1, 0
            if cols == 6 and rows and rows >= 2:
                while j < len(cards):
                    c2, r2 = self.grid_cr(cards[j])
                    if c2 != 6 or not r2 or tot + r2 > rows:
                        break
                    tot += r2
                    j += 1
            if j - i >= 3:
                out.append(self.card(c))
                out.append('<div class="w6 dcol">%s</div>' % "".join(self.card(x) for x in cards[i + 1:j]))
                i = j
                continue
            out.append(self.card(c))
            i += 1
        return "".join(out)

    def card(self, c):
        if not isinstance(c, dict):
            return ""
        t = str(c.get("type", ""))
        name = "c_" + re.sub(r"[^a-z0-9]", "_", t.lower())
        fn = getattr(self, name, None)
        try:
            if fn:
                return fn(c)
            return self.c_fallback(c)
        except Exception:
            log.exception("Error rendering card %s", t)
            return self.c_fallback(c)

    def title(self, c, key="title"):
        t = c.get(key)
        return '<h2 class="ch">%s</h2>' % E(str(t)) if isinstance(t, str) and t else ""

    def size(self, c, cols, rows):
        """Size of the card like in the HA "sections" views:
        columns out of 12 (3 = quarter, 6 = half, 12 = full width), rows of 56 px."""
        go = c.get("grid_options") if isinstance(c.get("grid_options"), dict) else {}
        lo = c.get("layout_options") if isinstance(c.get("layout_options"), dict) else {}
        col, row = go.get("columns"), go.get("rows")
        if col is None and lo.get("grid_columns") is not None:     # old format, out of 4
            try:
                col = int(lo["grid_columns"]) * 3
            except (TypeError, ValueError):
                col = None
        if row is None:
            row = lo.get("grid_rows")
        if col == "full":
            col = 12
        try:
            col = int(col) if col is not None else cols
        except (TypeError, ValueError):
            col = cols
        col = 3 if col <= 3 else 4 if col <= 4 else 6 if col <= 6 else 9 if col <= 9 else 12
        try:
            row = int(row) if row is not None else rows
        except (TypeError, ValueError):
            row = None          # "auto"
        return col, row

    def height(self, rows):
        """Exact height of the card: N units of 56 px separated by 8 px (like HA).
        In a stack-in-card, a simple minimum height (rendering of these cards unchanged)."""
        if not rows:
            return ""
        px = rows * 56 + (rows - 1) * 8
        if self.in_sic:
            return "min-height:%dpx" % px
        return "height:%dpx;overflow:hidden" % px

    def tile_html(self, eid, name_html, state_html, action, cfg_icon=None, extra="",
                  cols=6, rows=None, vertical=False, optimistic=True, base_extra="", side="",
                  icon_color=None, card=None, color=None, style_extra=""):
        """color = colour option of a tile or a button: the icon takes it when the entity
        is active (always for a button, a scene, a script)."""
        base = "card tile w%d%s%s" % (cols, " vt" if vertical else "", base_extra)
        if color and not icon_color and mc_class(color) and (
                not eid or domain_of(eid) in STATELESS):
            icon_color, color = color, None
        if self.pending_side:
            side, self.pending_side = side + self.pending_side, ""
        cs = self.card_style(card) if card else {}
        if " bc" in base_extra:
            cs.pop("h", None)       # compact button: one unit of height (56 px)
        style = ";".join(x for x in (
            ("min-height:%dpx" % cs["h"]) if cs.get("h") else self.height(rows),
            ("background:%s" % cs["bg"]) if cs.get("bg") else "", style_extra) if x)
        base += " rt " + (("dc-none" if icon_color else self.dc(eid, cfg_icon)) if eid else "dc-def")
        ic = self.ent_icon(eid, cfg_icon) if (eid or cfg_icon) else ""
        return (self.box_open(base, eid, action, optimistic=optimistic and bool(action), style=style)
                + (self.icon_box(ic, icon_color, eid if mc_class(color) else None, color)
                   if ic else "") + side
                + '<span class="tx%s"><span class="tn">%s</span>%s</span>%s</div>' % (
                    "" if state_html else " one",  # name only: centred in height (s.css)
                    name_html, ('<span class="ts">%s</span>' % state_html) if state_html else "",
                    extra))

    def icon_box(self, ic, icon_color, eid=None, color=None):
        """Icon dot; icon_color = fixed mushroom colour or Jinja template;
        color (with eid) = colour applied only when the entity is on."""
        if eid and color and not icon_color:
            def fnc(e=eid, mc=mc_class(color)):
                return (None, mc if state_class(self.st(e)) == "on" else "")
            sid = self.slot([eid], fnc)
            return '<span id="%s" class="ti %s" data-b="ti">%s</span>' % (sid, fnc()[1], ic)
        if not icon_color:
            return '<span class="ti">%s</span>' % ic
        if not has_tpl(icon_color):
            return '<span class="ti %s">%s</span>' % (mc_class(icon_color), ic)
        key = tkey(icon_color)
        self.need_tpl[key] = icon_color

        def fn(k=key):
            return (None, mc_class(self.store.tpl.get(k)))
        sid = self.slot(["tpl:" + key], fn)
        return '<span id="%s" class="ti %s" data-b="ti">%s</span>' % (sid, fn()[1], ic)

    def card_style(self, c):
        """Background and height imposed by card_mod / uix / button-card styles (nothing else)."""
        css = ""
        for k in ("uix", "card_mod"):
            v = c.get(k)
            if isinstance(v, dict) and isinstance(v.get("style"), str):
                css += v["style"]
        bg = h = None
        st = c.get("styles")
        if isinstance(st, dict) and isinstance(st.get("card"), list):
            for d in st["card"]:
                if isinstance(d, dict):
                    bg = d.get("background-color") or d.get("background") or bg
                    h = d.get("height") or h
        m = re.search(r"ha-card\s*\{([^}]*)\}", css)
        if m:
            body = m.group(1)
            mb = re.search(r"background(?:-color)?\s*:\s*([^;!]+)", body)
            mh = re.search(r"(?:^|[;\s])height\s*:\s*(\d+)px", body)
            bg = mb.group(1).strip() if mb else bg
            h = mh.group(1) if mh else h
        out = {}
        if bg and SAFE_COLOR.match(str(bg).strip()) and "[[[" not in str(bg):
            out["bg"] = str(bg).strip()
        try:
            out["h"] = int(str(h).replace("px", "")) if h else None
        except ValueError:
            pass
        return out

    def c_entities(self, c):
        out = ['<div class="card">', self.title(c)]
        # Header switch, like HA: title present, show_header_toggle not false,
        # at least 2 toggleable entities; on if one is, all off / all on.
        ents = []
        for r in c.get("entities") or []:
            e = r if isinstance(r, str) else (r.get("entity") if isinstance(r, dict) and not r.get("type") else None)
            if isinstance(e, str) and domain_of(e) in HEADER_TOGGLE and e not in ents:
                ents.append(e)
        if out[1] and c.get("show_header_toggle") is not False and len(ents) > 1:
            def fn(es=tuple(ents)):
                return (None, "on" if any((self.st(e) or {}).get("s") == "on" for e in es) else "off")
            sid = self.slot(ents, fn)
            out[1] = out[1].replace('<h2 class="ch">', '<h2 class="ch"><span class="tg hdt %s" id="%s" data-b="tg hdt" data-o="1"%s><i></i></span>' % (
                fn()[1], sid, self.action_attrs({"kind": "all", "entities": ents})), 1)
        for r in c.get("entities") or []:
            out.append(self.row(r))
        out.append("</div>")
        return "".join(out)

    def row_icon(self, eid, cfg_icon=None):
        return (self.box_open("ri " + self.dc(eid, cfg_icon), eid, None, tag="span")
                + self.ent_icon(eid, cfg_icon) + "</span>")

    def row(self, r):
        if isinstance(r, str):
            r = {"entity": r}
        if not isinstance(r, dict):
            return ""
        t = r.get("type")
        if t == "section":
            lab = r.get("label")
            return '<div class="sec">%s</div>' % E(lab) if lab else "<hr>"
        if t == "divider":
            return "<hr>"
        if t in ("button", "call-service", "perform-action"):
            if t != "button":
                r = dict(r, tap_action={"action": "perform-action",
                                        "perform_action": r.get("perform_action") or r.get("service"),
                                        "data": r.get("data") or r.get("service_data")})
            eid = r.get("entity")
            act = self.resolve_action(r.get("tap_action"), eid, "toggle" if eid else "none")
            nm = self.nm(eid, r.get("name")) if eid else (r.get("name") or "")
            return '<div class="row">%s<span class="nm">%s</span><span class="rt"><span class="btn lk"%s>%s</span></span></div>' % (
                self.row_icon(eid, r.get("icon")) if eid else "", E(str(nm)),
                self.action_attrs(act), E(str(r.get("action_name") or "Run")))
        if t == "buttons":
            parts = []
            for b in r.get("entities") or []:
                if isinstance(b, str):
                    b = {"entity": b}
                eid = b.get("entity")
                act = self.resolve_action(b.get("tap_action"), eid, self.default_tap(eid))
                parts.append(self.box_open("btn", eid, act, tag="span", optimistic=True)
                             + E(self.nm(eid, b.get("name"))) + "</span>")
            return '<div class="row btns">%s</div>' % "".join(parts)
        if t == "attribute":
            eid, attr = r.get("entity"), r.get("attribute")

            def fn(e=eid, at=attr, pre=r.get("prefix", ""), suf=r.get("suffix", "")):
                st = self.st(e)
                v = (st.get("a") or {}).get(at) if st else None
                v = "—" if v is None else (num(v) or str(v))
                return (E("%s%s%s" % (pre, v, suf)), None)
            return '<div class="row">%s<span class="nm">%s</span><span class="rt">%s</span></div>' % (
                self.row_icon(eid, r.get("icon")), E(self.nm(eid, r.get("name"))),
                self.text_slot(eid, fn))
        if t == "conditional":
            return self.cond_wrap(r.get("conditions"), self.row(r.get("row") or {}))
        if t in ("weblink", "cast", "text"):
            return '<div class="row"><span class="nm">%s</span><span class="rt">%s</span></div>' % (
                E(str(r.get("name") or "")), E(str(r.get("text") or "")))
        eid = r.get("entity")
        if not eid:
            return ""
        return self.entity_row(eid, r)

    def entity_row(self, eid, r):
        dom = domain_of(eid)
        nm = E(self.nm(eid, r.get("name")))
        tap = r.get("tap_action")
        ic = self.row_icon(eid, r.get("icon"))
        if dom == "cover":
            right = self.cover_buttons(eid)
            return '<div class="row">%s<span class="nm">%s</span><span class="rt">%s</span></div>' % (
                ic, nm, right)
        if dom in RUN_DOMAINS:
            act = self.resolve_action(tap, eid, "toggle")
            return '<div class="row">%s<span class="nm">%s</span><span class="rt"><span class="btn lk"%s>%s</span></span></div>' % (
                ic, nm, self.action_attrs(act), RUN_DOMAINS[dom])
        if dom == "climate":
            return '<div class="row">%s<span class="nm">%s<br>%s</span><span class="rt">%s</span></div>' % (
                ic, nm, self.text_slot(eid, cls="sub"), self.climate_ctrl(eid))
        if dom in TOGGLE_DOMAINS and not tap:
            act = {"kind": "toggle", "entity": eid}
            return (self.box_open("row", None, act) + ic
                    + '<span class="nm">%s</span><span class="rt">' % nm
                    + self.box_open("tg", eid, None, tag="span", optimistic=True)
                    + "<i></i></span></span></div>")
        if dom in EDIT_DOMAINS:
            return '<div class="row">%s<span class="nm">%s</span><span class="rt">%s</span></div>' % (
                ic, nm, self.edit_ctrl(eid))
        act = self.resolve_action(tap, eid, "none")
        return (self.box_open("row", None, act) + ic
                + '<span class="nm">%s</span><span class="rt">%s</span></div>' % (
                    nm, self.text_slot(eid, fmt=r.get("format"))))

    def edit_ctrl(self, eid):
        """Editable value of a row (number, list, time, date, text), like HA.
        The field sends its value on change (data-e = action); s.js does not replace it
        while it is being edited."""
        acts = {}
        for part in ("", "date", "time"):
            acts[part] = self.action_attrs({"kind": "set", "entity": eid, "part": part}).replace(
                "data-a", "data-e")

        def fn(e=eid):
            return (self.edit_html(e, acts), None)
        sid = self.slot([eid], fn)
        return '<span class="ed" id="%s">%s</span>' % (sid, fn()[0])

    def edit_html(self, eid, acts):
        st = self.st(eid)
        if not st or st.get("s") == "unavailable":
            return E(fmt_state(st, eid))
        dom, s, a = domain_of(eid), str(st.get("s")), st.get("a") or {}
        val = "" if s == "unknown" else s
        if dom in ("number", "input_number"):
            try:
                mn, mx = float(a.get("min", 0)), float(a.get("max", 100))
                step = float(a.get("step") or 1)
            except (TypeError, ValueError):
                mn, mx, step = 0.0, 100.0, 1.0

            def raw(v):
                try:
                    f = float(v)
                except (TypeError, ValueError):
                    return ""
                return str(int(f)) if f == int(f) and abs(f) < 1e15 else repr(round(f, 6))
            unit = a.get("unit_of_measurement")
            mode = a.get("mode") or "auto"
            rng = ' min="%s" max="%s" step="%s" value="%s"%s' % (
                raw(mn), raw(mx), raw(step), raw(val), acts[""])
            if mode == "slider" or (mode == "auto" and step > 0 and (mx - mn) / step <= 256):
                return '<input type="range" class="erg"%s><span class="ev">%s</span>' % (
                    rng, E(fmt_state(st, eid, self.prec(eid))))
            return '<input type="number" class="ein enb"%s>%s' % (
                rng, '<span class="eu">%s</span>' % E(unit) if unit else "")
        if dom in ("select", "input_select"):
            opts = [str(o) for o in (a.get("options") or [])]
            if val and val not in opts:
                opts.insert(0, val)
            return '<select class="esl"%s>%s</select>' % (acts[""], "".join(
                '<option value="%s"%s>%s</option>' % (E(o), " selected" if o == val else "", E(o))
                for o in opts))
        if dom in ("text", "input_text"):
            pw = a.get("mode") == "password"
            mx = a.get("max")
            return '<input type="%s" class="ein etx" value="%s"%s%s>' % (
                "password" if pw else "text", E(val),
                ' maxlength="%d"' % int(mx) if isinstance(mx, (int, float)) else "", acts[""])

        def time_in(v, act):
            v = (v or "")[:8]
            short = v[5:8] in ("", ":00")
            return '<input type="time" class="ein etm" step="%d" value="%s"%s>' % (
                60 if short else 1, E(v[:5] if short else v), act)

        def date_in(v, act):
            return '<input type="date" class="ein edt" value="%s"%s>' % (E((v or "")[:10]), act)
        if dom == "time":
            return time_in(val, acts[""])
        if dom == "date":
            return date_in(val, acts[""])
        # input_datetime: date and/or time ("2026-11-13 07:30:00", "07:30:00", "2026-11-13")
        out = []
        if a.get("has_date"):
            out.append(date_in(val[:10] if "-" in val[:10] else "", acts["date"]))
        if a.get("has_time"):
            out.append(time_in(val[-8:] if ":" in val else "", acts["time"]))
        return " ".join(out) or E(fmt_state(st, eid))

    # ---- lamps: favourite colours, brightness / temperature sliders ----
    def pal(self):
        return getattr(self.store, "palette", None) or theme.palette(None)

    def light_slider(self, eid, what):
        """Slider like ha-control-slider: bar (brightness) or marker on a gradient
        of whites (temperature). Dragged by finger by s.js, sent on release."""
        attr = self.action_attrs({"kind": "light", "entity": eid, "what": what}).replace("data-a", "data-s")
        at = (self.st(eid) or {}).get("a") or {}
        lo = float(at.get("min_color_temp_kelvin") or 2000)
        hi = float(at.get("max_color_temp_kelvin") or 6500)
        if what == "k":
            stops = ", ".join("%s %d%%" % (theme.hexc(kelvin_rgb(lo + (hi - lo) * i / 10.0)), i * 10)
                              for i in range(11))
            style = (' style="background:-webkit-linear-gradient(left, %s);'
                     'background:linear-gradient(to right, %s)"' % (stops, stops))

            def fn(e=eid):
                st = self.st(e) or {}
                a = st.get("a") or {}
                k = a.get("color_temp_kelvin")
                l = float(a.get("min_color_temp_kelvin") or lo)
                h = float(a.get("max_color_temp_kelvin") or hi)
                if st.get("s") != "on" or not isinstance(k, (int, float)) or h <= l:
                    return ('<span class="lc" style="display:none"></span>', None)
                return ('<span class="lc" style="left:%.1f%%"></span>' % (
                    max(0.0, min(100.0, (k - l) * 100.0 / (h - l)))), None)
            sid = self.slot([eid], fn)
            return '<div class="lsl lk" id="%s"%s%s>%s</div>' % (sid, attr, style, fn()[0])

        def fn(e=eid):
            st = self.st(e) or {}
            p = self.pal()
            on = st.get("s") == "on"
            b = (st.get("a") or {}).get("brightness")
            pct = int(round(float(b) * 100 / 255)) if on and isinstance(b, (int, float)) else 0
            if on:
                col = self.light_color(e).split("|")[0] or p["groups"].get("light", ("#ffc107",))[0]
            else:
                col = p["inact"]
            return ('<span class="lt" style="background:%s"></span><span class="lb" style="width:%d%%;'
                    'background:%s"><i></i></span>' % (col, pct, col), None)
        sid = self.slot([eid], fn)
        return '<div class="lsl" id="%s"%s>%s</div>' % (sid, attr, fn()[0])

    def toggle_switch(self, eid):
        """"toggle" feature like ha-control-switch: grey background, half-width knob
        on the left (off, grey) or on the right (on, entity colour)."""
        light = domain_of(eid) == "light"
        ic_on, ic_off = ("m-lightbulb", "m-lightbulb-off") if light else ("m-power", "m-power-off")
        self.icons.add(ic_on)
        self.icons.add(ic_off)

        def fn(e=eid):
            st = self.st(e) or {}
            p = self.pal()
            on = st.get("s") == "on"
            if on:
                col = (self.light_color(e).split("|")[0] if light else "") or p["groups"].get(
                    "light" if light else "switch", ("#ffc107",))[0]
            else:
                col = p["inact"]
            return ('<span class="lt"></span><span class="fk" style="left:%s;background:%s">'
                    '<svg class="ic"><use xlink:href="#i-%s"></use></svg></span>' % (
                        "50%" if on else "0", col, ic_on if on else ic_off), None)
        sid = self.slot([eid], fn)
        return '<div class="ftg" id="%s"%s>%s</div>' % (
            sid, self.action_attrs({"kind": "toggle", "entity": eid}), fn()[0])

    def light_favorites(self, eid):
        """Favourite colours of the lamp (set in HA), otherwise those HA offers
        by default: 4 whites from warmest to coolest, then 4 colours."""
        favs = (self.store.reg.get(eid) or {}).get("fav")
        at = (self.st(eid) or {}).get("a") or {}
        if not favs:
            modes = at.get("supported_color_modes") or []
            favs = []
            if "color_temp" in modes:
                lo = float(at.get("min_color_temp_kelvin") or 2000)
                hi = float(at.get("max_color_temp_kelvin") or 6500)
                favs += [{"color_temp_kelvin": int(round(lo + (hi - lo) * i / 3.0))} for i in range(4)]
            if any(m in modes for m in ("hs", "xy", "rgb", "rgbw", "rgbww")):
                favs += [{"rgb_color": c} for c in ([127, 172, 255], [215, 150, 255],
                                                    [255, 158, 243], [255, 110, 84])]
        items = []
        for f in favs:
            if not isinstance(f, dict):
                continue
            rgb = data = None
            if f.get("color_temp_kelvin"):
                rgb = kelvin_rgb(float(f["color_temp_kelvin"]))
                data = {"color_temp_kelvin": int(f["color_temp_kelvin"])}
            elif isinstance(f.get("hs_color"), (list, tuple)) and len(f["hs_color"]) == 2:
                r, g, b = colorsys.hsv_to_rgb(float(f["hs_color"][0]) / 360.0,
                                              float(f["hs_color"][1]) / 100.0, 1.0)
                rgb = (r * 255, g * 255, b * 255)
                data = {"hs_color": list(f["hs_color"])}
            else:
                for k in ("rgb_color", "rgbw_color", "rgbww_color"):
                    if isinstance(f.get(k), (list, tuple)) and len(f[k]) >= 3:
                        rgb, data = f[k][:3], {k: list(f[k])}
                        break
            if rgb is not None:
                items.append((rgb, data))
        modes = at.get("supported_color_modes") or []
        hue = any(m in modes for m in ("hs", "xy", "rgb", "rgbw", "rgbww"))
        n = len(items) + (1 if hue else 0)
        if not n:
            return ""
        # Percentages only (calc() is ignored by some Android 4.4 browsers):
        # gap of 1.43 % = 8 px on a 560 px card, like the original.
        gap = 1.43
        wv = (100.0 - gap * (n - 1)) / n
        w = "width:%.3f%%" % wv
        out = []
        for i, (rgb, data) in enumerate(items):
            out.append('<span class="lfb"%s style="%s;background:%s"></span>' % (
                self.action_attrs({"kind": "service", "domain": "light", "service": "turn_on",
                                   "data": data, "target": {"entity_id": eid}}),
                w + (";margin-left:%.2f%%" % gap if i else ""), theme.hexc(tuple(int(round(max(0, min(255, float(x))))) for x in rgb))))
        if not hue:
            return '<div class="lfv">%s</div>' % "".join(out)
        # Rainbow box: opens the hue bar (all the boxes except the last);
        # the last box takes the dragged hue (the lamp follows live) and validates.
        grad = "background:-webkit-linear-gradient(left, %s);background:linear-gradient(to right, %s)" % (
            RAINBOW, RAINBOW)
        out.append('<span class="lfb lfm" data-p="m" style="%s;%s"></span>' % (
            w + (";margin-left:%.2f%%" % gap if len(items) else ""), grad))
        hs = at.get("hs_color") if (self.st(eid) or {}).get("s") == "on" else None
        h = float(hs[0]) if isinstance(hs, (list, tuple)) and len(hs) == 2 else 0.0
        r, g, b = colorsys.hsv_to_rgb(h / 360.0, 1.0, 1.0)
        cur = theme.hexc((int(r * 255), int(g * 255), int(b * 255)))
        attr = self.action_attrs({"kind": "light", "entity": eid, "what": "h"}).replace("data-a", "data-s")
        pick = ('<span class="lhp" style="display:none"><span class="lhb" data-h="1"%s style="width:%.3f%%">'
                '<span class="lht" style="%s"></span><span class="lhi"><span class="lc" style="left:%.1f%%"></span></span></span>'
                '<span class="lfb lhc" data-p="v" style="%s;margin-left:%.2f%%;background:%s"></span></span>') % (
            attr, 100.0 - wv - gap, grad, h * 100.0 / 360.0, w, gap, cur)
        return '<div class="lfv"><span class="lfr">%s</span>%s</div>' % ("".join(out), pick)

    def cover_buttons(self, eid):
        """Monter / stop / descendre."""
        out = []
        for srv, ic in (("open_cover", "up"), ("stop_cover", "stop"), ("close_cover", "down")):
            out.append('<span class="btn cv"%s>%s</span>' % (self.action_attrs(
                {"kind": "service", "domain": "cover", "service": srv, "data": {},
                 "target": {"entity_id": eid}}), self.icon(ic)))
        return "".join(out)

    def climate_ctrl(self, eid):
        def tgt(e=eid):
            st = self.st(e)
            v = (st.get("a") or {}).get("temperature") if st else None
            u = (st.get("a") or {}).get("temperature_unit", TEMP_UNIT) if st else TEMP_UNIT
            return (E("%s %s" % (num(v), u)) if v is not None and num(v) else "—", None)
        a0 = (self.st(eid) or {}).get("a") or {}
        try:    # step of the entity, else 1 degree in Fahrenheit and 0.5 in Celsius
            stp = float(a0.get("target_temp_step") or 0) or (1.0 if TEMP_UNIT == "°F" else 0.5)
        except (TypeError, ValueError):
            stp = 0.5
        minus = self.action_attrs({"kind": "temp", "entity": eid, "step": -stp})
        plus = self.action_attrs({"kind": "temp", "entity": eid, "step": stp})
        return '<span class="btn sm"%s>&minus;</span> %s <span class="btn sm"%s>+</span>' % (
            minus, self.text_slot(eid, tgt, cls="tgt"), plus)

    def c_glance(self, c):
        ents = c.get("entities") or []
        cols = c.get("columns") or min(5, max(1, len(ents)))
        w = 100.0 / cols
        out = ['<div class="card">', self.title(c), '<div class="gl">']
        for e in ents:
            if isinstance(e, str):
                e = {"entity": e}
            eid = e.get("entity")
            if not eid:
                continue
            act = self.resolve_action(e.get("tap_action") or c.get("tap_action"), eid, "none")
            out.append(self.box_open("gi " + self.dc(eid, e.get("icon")), eid, act, style="width:%.3f%%" % w))
            if c.get("show_name", True) and e.get("show_name", True):
                out.append('<div class="gn">%s</div>' % E(self.nm(eid, e.get("name"))))
            if c.get("show_icon", True) and e.get("show_icon", True):
                out.append('<div class="gic">%s</div>' % self.ent_icon(eid, e.get("icon")))
            if c.get("show_state", True) and e.get("show_state", True):
                out.append(self.text_slot(eid, tag="div", cls="gs"))
            out.append("</div>")
        out.append("</div></div>")
        return "".join(out)

    def c_button(self, c):
        eid = c.get("entity")
        act = self.resolve_action(c.get("tap_action"), eid,
                                  self.default_tap(eid) if eid else "none")
        nm = ""
        if c.get("show_name", True):
            nm = E(self.nm(eid, c.get("name")) if eid else str(c.get("name") or ""))
        state = self.text_slot(eid) if eid and c.get("show_state", False) else ""
        icon = c.get("icon") if c.get("show_icon", True) else None
        if not eid and not nm and not icon:
            return ""
        cols, rows = self.size(c, 6, 2)
        return self.tile_html(eid, nm, state, act, cfg_icon=icon, base_extra=" bt nb",
                              cols=cols, rows=rows, vertical=True, color=c.get("color"))

    def c_tile(self, c):
        eid = c.get("entity")
        if not eid:
            return ""
        act = self.resolve_action(c.get("tap_action"), eid, self.default_tap(eid))
        extra = ""
        side = ""
        nfeat = 0
        inline = c.get("features_position") == "inline"
        for f in c.get("features") or []:
            if not isinstance(f, dict):
                continue
            if f.get("type") == "trend-graph" and inline and not side:
                side = self.chart([(eid, None)], f.get("hours_to_show") or 24, 36, cls="chart fi")
            elif f.get("type") == "trend-graph":
                extra += self.chart([(eid, None)], f.get("hours_to_show") or 24, 42)
                nfeat += 1
            elif f.get("type") == "toggle" and domain_of(eid) in TOGGLE_FEATURE:
                extra += self.toggle_switch(eid)
                nfeat += 1
            elif f.get("type") == "light-brightness" and domain_of(eid) == "light":
                extra += self.light_slider(eid, "b")
                nfeat += 1
            elif f.get("type") == "light-color-temp" and domain_of(eid) == "light":
                extra += self.light_slider(eid, "k")
                nfeat += 1
            elif f.get("type") == "light-color-favorites" and domain_of(eid) == "light":
                extra += self.light_favorites(eid)
                nfeat += 1
            elif f.get("type") in ("climate-hvac-modes", "climate-fan-modes") and domain_of(eid) == "climate":
                m = self.climate_modes(eid, f)
                if m:
                    extra += m
                    nfeat += 1
            elif f.get("type") in ("cover-open-close", "cover-position") and domain_of(eid) == "cover":
                extra += '<div class="cvb">%s</div>' % self.cover_buttons(eid)
                nfeat += 1
        vertical = bool(c.get("vertical")) or c.get("layout") == "vertical"
        mini = (2 if vertical else 1) + nfeat
        cols, rows = self.size(c, 12 if side else 6, mini)
        if rows is not None and rows < mini:
            rows = mini         # HA enlarges the card to fit all the features
        if (vertical and self.in_stack and str(c.get("type", "")).startswith("custom:mushroom")
                and not c.get("grid_options") and not c.get("layout_options")):
            rows = None         # vertical mushroom in a stack: natural height, like HA
        pad, tfx = "", ""
        if extra and rows and not vertical and not self.in_sic:
            # HA placement: 42 px features spaced 12 px apart, the last one
            # 12 px from the bottom; the header (36 px) centred in the space left above.
            h = rows * 56 + (rows - 1) * 8
            top = h - nfeat * 54
            pt = max(6, top // 2 - 18)
            pad = "padding-top:%dpx" % pt
            extra = '<div class="fsp" style="height:%dpx"></div>' % max(0, top - pt - 36 - 12) + extra
            tfx = " tfx"
        state = self.content_slots(eid, c.get("state_content")) or self.text_slot(eid)
        return self.tile_html(eid, E(self.nm(eid, c.get("name"))), state, act,
                              cfg_icon=c.get("icon"), extra=extra, cols=cols, rows=rows, side=side,
                              vertical=vertical, color=c.get("color"), style_extra=pad,
                              base_extra=(" tf" if extra else "") + tfx + (" tfi" if side else ""))

    def c_light(self, c):
        """HA "light" card: brightness dial over 270 degrees (ha-control-circular-slider,
        24/320 stroke), big bulb in the centre (on / off), brightness and name below."""
        eid = c.get("entity")
        if not eid:
            return ""
        arc = "M 145 0 A 145 145 0 1 1 0 -145"          # 270 degrees, rotated by 135 degrees (bottom left)
        full = 683.3

        def col(e):
            st = self.st(e) or {}
            p = self.pal()
            if st.get("s") != "on":
                return None
            c1 = self.light_color(e).split("|")[0] or p["groups"].get("light", ("#ffc107",))[0]
            if p.get("dark", True):
                return c1
            # light theme: a white lamp would stay invisible on the white card;
            # almost white colour -> theme "lamp on" colour
            rgb = theme.parse(c1) or (255, 193, 7, 1.0)
            if max(rgb[:3]) - min(rgb[:3]) < 40:
                c1 = p["groups"].get("light", ("#ffc107",))[0]
            return theme.readable(c1, p["card"], 2.0)

        def pct(e):
            st = self.st(e) or {}
            b = (st.get("a") or {}).get("brightness")
            if st.get("s") != "on" or not isinstance(b, (int, float)):
                return None
            return int(round(float(b) * 100 / 255))

        def dial(e=eid):
            c1, v = col(e), pct(e)
            dim = (self.st(e) or {}).get("s") != "on" or v is None
            p = self.pal()
            # off: grey measured on HA (dark); in light, inactive grey of the theme (readable on white)
            off = "#c2c2c2" if p.get("dark", True) else p["inact"]
            return ('<svg viewBox="0 0 320 320"><g transform="translate(160 160) rotate(135)">'
                    '<path class="lgt" d="%s" style="stroke:%s;stroke-opacity:%s"/>'
                    '<path class="la" d="%s" style="stroke:%s" stroke-dasharray="%.1f 1000"/></g></svg>' % (
                        arc, c1 or off, (".3" if p.get("dark", True) else ".45") if c1 else "1",
                        arc, c1 or off, 0 if dim else max(0.1, full * (v or 0) / 100.0)), None)

        def center(e=eid):
            c1 = col(e)
            st = self.st(e) or {}
            if (domain_of(e) == "light" and st.get("s") != "on" and not c.get("icon")
                    and not (st.get("a") or {}).get("icon")):
                ic = self.icon(icons.from_mdi("mdi:lightbulb-off"))   # HA state icon: crossed-out bulb
            else:
                ic = self.ent_icon(e, c.get("icon"))
            return ('<span class="lgi" style="color:%s">%s</span>' % (
                c1 or self.pal()["icon"], ic), None)

        def info(e=eid):
            v = pct(e)
            return ("&nbsp;" if v is None else "%d %%" % v, None)

        slider = self.action_attrs({"kind": "light", "entity": eid, "what": "b"}).replace("data-a", "data-s")
        if domain_of(eid) == "light":   # the two icons are in the page: the state changes live
            self.icons.add(icons.from_mdi("mdi:lightbulb-off"))
            self.ent_icon(eid, c.get("icon"))
        did = self.slot([eid], dial)
        cid = self.slot([eid], center)
        iid = self.slot([eid], info)
        cols, rows = self.size(c, 12, None)
        return ('<div class="card w%d lgc">' % cols
                + '<div class="lgw"><div class="lgp">'
                + '<div class="lgd" id="%s" data-r="1" data-f="%.1f"%s>%s</div>' % (
                    did, full, slider, dial()[0])
                + '<span class="lgb" id="%s"%s>%s</span>' % (
                    cid, self.action_attrs({"kind": "toggle", "entity": eid}), center()[0])
                + '</div></div><div class="lgn"><div class="lgv" id="%s">%s</div>%s</div></div>' % (
                    iid, info()[0], E(self.nm(eid, c.get("name")))))

    def c_entity(self, c):
        eid = c.get("entity")
        if not eid:
            return ""
        attr = c.get("attribute")
        fn = None
        if attr:
            def fn(e=eid, at=attr, unit=c.get("unit", "")):
                st = self.st(e)
                v = (st.get("a") or {}).get(at) if st else None
                v = "—" if v is None else (num(v) or str(v))
                return (E(v) + ('<span class="u">%s</span>' % E(unit) if unit else ""), None)
        elif c.get("unit"):
            def fn(e=eid, unit=c["unit"]):
                st = self.st(e)
                s = st.get("s") if st else None
                return (E(num(s) or s or "—") + '<span class="u">%s</span>' % E(unit), None)
        else:
            fn = self.value_fn(eid)
        act = self.resolve_action(c.get("tap_action"), eid, "none")
        graph = ""
        cols, rows = self.size(c, 6, 2)
        if c.get("type") == "sensor" and c.get("graph") == "line":
            # the curve takes the bottom of the card, under the value (71 px)
            gh = (rows * 56 + (rows - 1) * 8 - 71) if rows else None
            graph = self.chart([(eid, None)], c.get("hours_to_show") or 24, gh)
        head = '%s<div class="tn">%s</div>' % (
            '<span class="hi">%s</span>' % self.ent_icon(eid, c.get("icon")),
            E(self.nm(eid, c.get("name"))))
        return (self.box_open("card w%d big %s" % (cols, self.dc(eid)), None, act,
                              style=self.height(rows)) + head
                + self.text_slot(eid, fn, tag="div", cls="bv") + graph + "</div>")

    def c_sensor(self, c):
        return self.c_entity(c)

    def c_sensor_entity(self, c):
        return self.c_entity(c)

    def c_gauge(self, c):
        eid = c.get("entity")
        if not eid:
            return ""
        mn = float(c.get("min", 0) or 0)
        mx = float(c.get("max", 100) or 100)
        sev = c.get("severity") if isinstance(c.get("severity"), dict) else None

        def val(e=eid):
            return num_value(self.st(e))

        def level(v):
            if v is None:
                return "na"
            if sev:
                # Like HA: the colour of the highest threshold reached, whatever the order.
                best = None
                for k, cl in (("green", "grn"), ("yellow", "yel"), ("red", "red")):
                    try:
                        t = float(sev[k])
                    except (KeyError, TypeError, ValueError):
                        continue
                    if v >= t and (best is None or t > best[0]):
                        best = (t, cl)
                if best:
                    return best[1]
            return ""

        def frac(v):
            return 0 if v is None or mx == mn else max(0.0, min(1.0, (v - mn) / (mx - mn)))

        def txt(e=eid, unit=c.get("unit")):
            st = self.st(e)
            if unit and st and num(st.get("s")) is not None:
                return (E("%s %s" % (num(st.get("s")), unit)), None)
            return (E(fmt_state(st, e, self.prec(e))), None)

        act = self.resolve_action(c.get("tap_action"), eid, "none")
        name = '<div class="tn">%s</div>' % E(self.nm(eid, c.get("name")))
        if self.in_stack and not c.get("grid_options") and not c.get("layout_options"):
            # In a stack, like HA: natural height, the arc follows the width of the card
            # and the value is in the arc (SVG text, which grows with it).
            def farc(e=eid):
                v = val(e)
                return ('<svg class="ga" viewBox="0 0 100 56"><path class="gb" d="M10 50A40 40 0 0 1 90 50"/>'
                        '<path class="gv %s" d="M10 50A40 40 0 0 1 90 50" stroke-dasharray="%.1f 126"/>'
                        '<text class="gtx" x="50" y="49" text-anchor="middle">%s</text></svg>'
                        % (level(v), frac(v) * 125.7, txt(e)[0]), None)
            sid = self.slot([eid], farc)
            return (self.box_open("card gauge gfl", None, act)
                    + '<div class="gw"><div id="%s" class="gin">%s</div></div>' % (sid, farc()[0])
                    + name + "</div>")
        gcols, grows = self.size(c, 12, None)
        if grows is None:
            grows = 3 if gcols == 12 else 2
        gbase = "card w%d gauge gfx%s" % (gcols, " g3" if grows and grows >= 3 else "")
        # Half-circle gauge (SVG arc, length pi*40 = 125.7), value in the arc like HA:
        # the arc follows the width of the card (max size set in CSS) and the text with it.
        def arc(e=eid):
            v = val(e)
            return ('<svg class="ga" viewBox="0 0 100 56"><path class="gb" d="M10 50A40 40 0 0 1 90 50"/>'
                    '<path class="gv %s" d="M10 50A40 40 0 0 1 90 50" stroke-dasharray="%.1f 126"/>'
                    '<text class="gtx" x="50" y="49" text-anchor="middle">%s</text></svg>'
                    % (level(v), frac(v) * 125.7, txt(e)[0]), None)
        sid = self.slot([eid], arc)
        return (self.box_open(gbase, None, act, style=self.height(grows))
                + '<div class="gw"><div class="gp"><div id="%s" class="gin">%s</div></div></div>' % (sid, arc()[0])
                + name + "</div>")

    def c_energy_self_sufficiency_gauge(self, c):
        """Self-sufficiency gauge (native energy card): value computed by the server."""
        self.need_hist["e:ss"] = ("energy", 0)

        def val():
            return self.store.hist.get("e:ss")

        def arc():
            v = val()
            lv = "na" if v is None else ("grn" if v > 75 else ("yel" if v < 50 else ""))
            f = 0 if v is None else max(0.0, min(1.0, v / 100.0))
            return ('<svg class="ga" viewBox="0 0 100 56"><path class="gb" d="M10 50A40 40 0 0 1 90 50"/>'
                    '<path class="gv %s" d="M10 50A40 40 0 0 1 90 50" stroke-dasharray="%.1f 126"/>'
                    '<text class="gtx" x="50" y="49" text-anchor="middle">%s</text></svg>'
                    % (lv, f * 125.7, "—" if v is None else "%d %%" % round(v)), None)

        gcols, grows = self.size(c, 6, 2)
        if grows is None:       # "auto": same height as the classic gauge
            grows = 3 if gcols == 12 else 2
        gbase = "card w%d gauge gfx%s" % (gcols, " g3" if grows >= 3 else "")
        sid = self.slot(["hist:e:ss"], arc)
        return (self.box_open(gbase, None, None, style=self.height(grows))
                + '<div class="gw"><div class="gp"><div id="%s" class="gin">%s</div></div></div>' % (sid, arc()[0])
                + '<div class="tn">%s</div></div>' % E(str(c.get("title") or "Taux d'autosuffisance")))

    def c_markdown(self, c):
        # text_only: text alone, no background, border or shadow (like HA)
        return ('<div class="card md%s">' % (" txo" if c.get("text_only") else "") + self.title(c)
                + self.tpl_slot(str(c.get("content") or ""), tag="div", markdown=True) + "</div>")

    def c_heading(self, c):
        h = c.get("heading") or ""
        out = ['<div class="hd">%s%s' % (self.icon(icons.from_mdi(c.get("icon")), "ic hi")
                                         if c.get("icon") else "", E(str(h)))]
        for b in c.get("badges") or []:
            if isinstance(b, str):
                b = {"entity": b}
            eid = b.get("entity") if isinstance(b, dict) else None
            if eid:
                out.append(" " + self.badge(eid, None, b.get("icon")))
        out.append("</div>")
        return "".join(out)

    def weather_icon(self, cond, cls="wsym"):
        return '<span class="%s">%s</span>' % (cls, self.icon(icons.WEATHER.get(cond, "cloud")))

    def c_weather_forecast(self, c):
        """Like HA: icon, state and place on the left, temperature and max / min on the right;
        forecast in columns (day, icon, max, min)."""
        eid = c.get("entity")
        if not eid:
            return ""
        show_cur = c.get("show_current", True) is not False
        fcst = c.get("show_forecast", True) is not False
        ftype = c.get("forecast_type") or "daily"
        key = "fc:%s:%s" % (eid, ftype)
        if fcst:
            self.need_fc.add((eid, ftype))
        self.icons.update(set(icons.WEATHER.values()))    # the weather changes: all its icons
        drop = self.icon("drop")
        place = E(str(self.nm(eid, c.get("name"))))

        def cur(e=eid, k=key):
            st = self.st(e)
            if not st:
                return ("—", None)
            a = st.get("a") or {}
            s = st.get("s")
            t = a.get("temperature")
            unit = a.get("temperature_unit", TEMP_UNIT)
            second = ""
            items = (self.store.fc.get(k) or []) if fcst else []
            if items and ftype != "hourly" and items[0].get("templow") is not None:
                second = E("%s %s / %s %s" % (num(items[0].get("temperature")), unit,
                                              num(items[0].get("templow")), unit))
            elif a.get("humidity") is not None:
                second = drop + E("%s %%" % num(a["humidity"]))
            return ('%s<span class="wr"><span class="wt">%s</span><span class="w2">%s</span></span>'
                    '<span class="wc"><span class="wn">%s</span><span class="wl">%s</span></span>' % (
                        self.weather_icon(s),
                        E("%s\u00a0%s" % (num(t), unit)) if t is not None else "",
                        second, E(weather_txt(s)), place), None)

        # Like HA: 4U with forecast, 2U for the current weather alone.
        cols, rows = self.size(c, 12, 4 if fcst and show_cur else 2)
        out = ['<div class="card wx w%d%s" style="%s">' % (cols, " wf" if fcst else "", self.height(rows))]
        if show_cur:
            sid = self.slot([eid, key], cur)
            out.append('<div id="%s" class="wcur">%s</div>' % (sid, cur()[0]))
        if fcst:
            def fc(k=key, ft=ftype):
                cells = []
                for f in (self.store.fc.get(k) or [])[:5]:
                    try:
                        d = datetime.fromisoformat(str(f.get("datetime")).replace("Z", "+00:00")).astimezone()
                        lab = i18n.day_name(d.weekday(), True) if ft != "hourly" else d.strftime("%H:%M")
                    except (ValueError, TypeError):
                        lab = ""
                    hi, lo = f.get("temperature"), f.get("templow")
                    cells.append('<div class="fd"><div class="fn">%s</div>%s<div class="fh">%s</div>%s</div>' % (
                        lab, self.weather_icon(f.get("condition")),
                        (E(num(hi) or "") + "°") if hi is not None else "",
                        ('<div class="fl">%s°</div>' % E(num(lo) or "")) if lo is not None else ""))
                return ("".join(cells), None)
            sid = self.slot([key], fc)
            out.append('<div id="%s" class="fcs">%s</div>' % (sid, fc()[0]))
        out.append("</div>")
        return "".join(out)

    def c_custom_meteofrance_weather_card(self, c):
        return self.c_weather_forecast(dict(c, show_current=True, show_forecast=True))

    def climate_range(self, a):
        return climate_range(a)

    def c_thermostat(self, c):
        """HA "thermostat" card: title, 270 degree dial (set point handle, current temperature
        mark, arc between them in the colour of the mode), action, set point, current
        temperature and - / + buttons; optional mode features."""
        eid = c.get("entity")
        if not eid:
            return ""
        arc = "M 145 0 A 145 145 0 1 1 0 -145"
        full = 683.3
        dark = self.pal().get("dark", True)

        def seg(a0, a1, width, color, cap="round", op=1):
            return ('<path d="%s" style="stroke:%s;stroke-width:%d;stroke-linecap:%s;opacity:%s" '
                    'stroke-dasharray="%.1f 1000" stroke-dashoffset="%.1f"/>' % (
                        arc, color, width, cap, op, max(0.1, (a1 - a0) * full), -a0 * full))

        def dial(e=eid):
            st = self.st(e) or {}
            a = st.get("a") or {}
            lo, hi, _ = self.climate_range(a)

            def fr(v):
                try:
                    return max(0.0, min(1.0, (float(v) - lo) / (hi - lo)))
                except (TypeError, ValueError):
                    return None
            ft, fc = fr(a.get("temperature")), fr(a.get("current_temperature"))
            mode = st.get("s")
            col = CLIMATE_COLORS.get(mode)
            body = seg(0, 1, 24, "#bdbdbd" if dark else self.pal()["inact"], op=".3" if dark else ".45")
            if col:
                if mode == "heat" and ft is not None:        # fill: min -> set point
                    body += seg(0, ft, 24, col, op=".5")
                elif mode == "cool" and ft is not None:      # fill: set point -> max
                    body += seg(ft, 1, 24, col, op=".5")
                elif mode not in ("heat", "cool"):           # auto, heat_cool...: whole ring
                    body += seg(0, 1, 24, col, op=".5")
                if ft is not None and fc is not None:        # still to do: current -> set point
                    if mode == "heat" and fc < ft:
                        body += seg(fc, ft, 24, col)
                    elif mode == "cool" and fc > ft:
                        body += seg(ft, fc, 24, col)
            if fc is not None:
                body += seg(fc, fc, 8, "#ffffff" if dark else "#555555", op=".5")
            if ft is not None:
                body += seg(ft, ft, 24, col or CLIMATE_OFF) + seg(ft, ft, 18, "#ffffff")
            return ('<svg viewBox="0 0 320 320"><g transform="translate(160 160) rotate(135)">%s</g></svg>' % body, None)

        def acol(e):
            """Colour of the action (heating, cooling...) while it is running, else None."""
            st = self.st(e) or {}
            k = ACTION_COLORS.get((st.get("a") or {}).get("hvac_action"))
            return CLIMATE_COLORS.get(k) if k and st.get("s") != "off" else None

        def label(e=eid):
            st = self.st(e) or {}
            act = (st.get("a") or {}).get("hvac_action")
            if st.get("s") != "off" and act:
                txt = E(tr_attr("hvac_action", act) or ACTION_TXT.get(act, str(act)))
                c1 = acol(e)
                return ('<span style="color:%s">%s</span>' % (c1, txt) if c1 else txt, None)
            m = st.get("s")
            return (E(tr_state("climate", None, m) or STATE_TXT.get(m) or ("Off" if m == "off" else str(m).replace("_", " ").capitalize())), None)

        swap = bool(c.get("show_current_as_primary"))   # HA option: current temperature in big, set point small

        def tfmt(f, nd):
            return ("%.*f" % (nd, f)).replace(".", i18n.D["dec"])

        def target(e=eid):
            a = (self.st(e) or {}).get("a") or {}
            u = a.get("temperature_unit", TEMP_UNIT)
            tv = a.get("temperature")
            lo, hi, stp = self.climate_range(a)
            nd = 1 if stp % 1 else 0
            if not swap and tv is None and a.get("target_temp_low") is not None \
                    and a.get("target_temp_high") is not None:
                return ('<span class="thn">%s \u2013 %s</span>' % (
                    E(num(a["target_temp_low"]) or ""), E(num(a["target_temp_high"]) or "")), None)
            try:
                f = float((a.get("current_temperature") if swap else tv))
            except (TypeError, ValueError):
                return ('<span class="thn">\u2014</span>', None)
            if nd:
                ip, dp = ("%.1f" % f).split(".")
                addon = '<span class="thu">%s</span><span class="thdc">%s%s</span>' % (E(u), i18n.D["dec"], dp)
            else:
                ip, addon = "%d" % round(f), '<span class="thu">%s</span>' % E(u)
            data = ""
            try:
                data = ('<span class="thm" style="display:none" data-v="%s" data-lo="%s" data-hi="%s" '
                        'data-nd="%d" data-dec="%s" data-u="%s"%s></span>' % (
                            float(tv), lo, hi, nd, E(i18n.D["dec"]), E(u), ' data-sw="1"' if swap else ""))
            except (TypeError, ValueError):
                pass
            return (data + '<span class="thn">%s</span><span class="thx">%s</span>' % (E(group(ip)), addon), None)

        def current(e=eid):
            a = (self.st(e) or {}).get("a") or {}
            u = a.get("temperature_unit", TEMP_UNIT)
            lo, hi, stp = self.climate_range(a)
            v = a.get("temperature") if swap else a.get("current_temperature")
            if v is None:
                return ("&nbsp;", None)
            try:
                txt = tfmt(float(v), 1 if stp % 1 else 0) if swap else (num(v) or str(v))
            except (TypeError, ValueError):
                txt = str(v)
            html = (self.icon(icons.from_mdi("mdi:target" if swap else "mdi:thermometer")) + " "
                    + '<span class="thtv">%s %s</span>' % (E(txt), E(u)))
            c1 = acol(e)
            return ('<span style="color:%s">%s</span>' % (c1, html) if c1 else html, None)

        stp = self.climate_range((self.st(eid) or {}).get("a") or {})[2]
        minus = ' data-tp="%s"' % -stp      # s.js: immediate local change, one send (dial action)
        plus = ' data-tp="%s"' % stp

        def slot(fn, cls, attrs=""):
            return '<div class="%s" id="%s"%s>%s</div>' % (cls, self.slot([eid], fn), attrs, fn()[0])
        # the dial is dragged by s.js (data-s, ring only: data-r) and sent on release
        dial_attrs = ' data-r="1" data-t="1" data-f="%.1f"%s' % (
            full, self.action_attrs({"kind": "tset", "entity": eid}).replace("data-a", "data-s"))
        feats_cfg = [f for f in c.get("features") or []
                     if isinstance(f, dict) and f.get("type") in ("climate-hvac-modes", "climate-fan-modes")]
        if feats_cfg:       # features of the card: rows of buttons at the bottom, like HA
            menu = "".join(self.climate_modes(eid, f) for f in feats_cfg)
        else:               # none: the modes in a menu (three dots), the card keeps its size
            feats = self.climate_modes(eid, {"type": "climate-hvac-modes"}, menu=True)
            menu = ('<span class="thmb" data-tm="1">%s</span><div class="card thmn" style="display:none">%s</div>' % (
                self.icon(icons.from_mdi("mdi:dots-vertical")), feats)) if feats else ""
        return ('<div class="card thc"><div class="thti">%s</div><div class="thw">%s%s%s%s'
                '<div class="thbs"><span class="thb"%s>%s</span><span class="thb"%s>%s</span></div></div>%s</div>' % (
                    E(self.nm(eid, c.get("name"))), slot(dial, "thd", dial_attrs), slot(label, "thl"),
                    slot(target, "thv"), slot(current, "ths"),
                    minus, self.icon(icons.from_mdi("mdi:minus")),
                    plus, self.icon(icons.from_mdi("mdi:plus")), menu))

    def climate_modes(self, eid, f, menu=False):
        """Features climate-hvac-modes / climate-fan-modes: one button per mode, the active
        one highlighted (kept up to date by a slot)."""
        t = f.get("type")
        if t not in ("climate-hvac-modes", "climate-fan-modes"):
            return ""
        fan = t == "climate-fan-modes"
        have = ((self.st(eid) or {}).get("a") or {}).get("fan_modes" if fan else "hvac_modes") or []
        want = f.get("fan_modes" if fan else "hvac_modes")
        if isinstance(want, list):
            modes = [m for m in want if isinstance(m, str)]
        elif fan:
            modes = list(have)
        else:       # default: on/off, heat, cool, auto (4 buttons on one line)
            modes = ["off", "heat", "cool", "auto" if "auto" in have or "heat_cool" not in have else "heat_cool"]
        modes = [m for m in modes if not have or m in have][:6]
        if not modes:
            return ""
        w = 100.0 / len(modes) - 2
        acts = []
        for m in modes:
            what = "fan" if fan else "hvac"
            acts.append((m, self.action_attrs({"kind": "cmode", "entity": eid, "what": what, "value": m})))

        def label(m):
            if fan:
                return tr_attr("fan_mode", m) or m.replace("_", " ").capitalize()
            return (i18n.mode_label(m) or tr_state("climate", None, m) or STATE_TXT.get(m)
                    or m.replace("_", " ").capitalize())

        as_icons = f.get("style") == "icons" and not fan and not menu     # HA "icons" style

        def row(e=eid):
            st = self.st(e) or {}
            cur = (st.get("a") or {}).get("fan_mode") if fan else st.get("s")
            return ("".join('<span class="btn cm%s"%s%s title="%s">%s</span>' % (
                " on" if m == cur else "", at,
                "" if menu else ' style="width:%.1f%%"' % w, E(label(m)),
                self.icon(icons.from_mdi(MODE_ICONS.get(m, "mdi:thermostat"))) if as_icons else E(label(m)))
                for m, at in acts), None)
        return '<div class="cmb%s" id="%s">%s</div>' % (" cmv" if menu else "", self.slot([eid], row), row()[0])

    def graph_rows(self, c, entities, hours, title):
        """Like HA: title, graph, then legend (colour dot, name, value)."""
        cols, rows = self.size(c, 12, 6)
        out = ['<div class="card hg w%d" style="%s">' % (cols, self.height(rows)),
               ('<h2 class="ch">%s</h2>' % E(title)) if title else ""]
        series, legend = [], []
        for e in entities:
            if isinstance(e, str):
                e = {"entity": e}
            eid = e.get("entity") if isinstance(e, dict) else None
            if not eid or len(series) >= 4:
                continue
            color = self.series_color(eid, e.get("color"), len(series))
            series.append((eid, color))
            legend.append('<span class="lg"><i style="background:%s"></i>%s %s</span>' % (
                color, E(self.nm(eid, e.get("name"))), self.text_slot(eid, cls="lv")))
        if series:
            gh = None
            if rows:   # height of the card - title - legend
                gh = rows * 56 + (rows - 1) * 8 - (62 if title else 16) - 56
            out.append(self.chart(series, hours, gh))
            out.append('<div class="lgs">%s</div>' % "".join(legend))
        out.append("</div>")
        return "".join(out)

    def c_history_graph(self, c):
        return self.graph_rows(c, c.get("entities") or [], c.get("hours_to_show") or 24,
                               c.get("title"))

    def c_statistics_graph(self, c):
        return self.graph_rows(c, c.get("entities") or [], (c.get("days_to_show") or 30) * 24,
                               c.get("title"))

    def c_custom_statistics_graph_chart_card(self, c):
        """"statistics-graph-chart-card" card: header, value(s), curves or bars."""
        ents = [e if isinstance(e, dict) else {"entity": e} for e in c.get("entities") or []]
        ents = [e for e in ents if e.get("entity")][:4]
        title = c.get("card_header") or c.get("title") or ""
        has_title = isinstance(title, str) and bool(title)
        try:
            gh = int(c.get("height")) if c.get("height") else None
        except (TypeError, ValueError):
            gh = None
        single = len(ents) == 1
        cols, rows = self.size(c, 12, None if (gh or not single) else 4)
        if rows and not gh:     # height of the card - margins, title, values
            gh = rows * 56 + (rows - 1) * 8 - 24 - (30 if has_title else 0) - 62
        hc = c.get("card_header_color")
        # In a stack-in-card, the negative margins of "styles" (ha-card margin-top,
        # .sgc-plot-wrap margin) pull the graph up under the card above, like HA.
        lift = ""
        sty = str(c.get("styles") or "")
        if self.in_sic and not has_title:
            m1 = re.search(r"ha-card\s*\{[^}]*margin-top\s*:\s*(-?\d+)px", sty)
            m2 = re.search(r"\.sgc-plot-wrap\s*\{[^}]*margin\s*:\s*(-?\d+)px", sty)
            up = (int(m1.group(1)) if m1 else 0) + (int(m2.group(1)) if m2 else 0)
            if up < 0:
                lift = "margin-top:%dpx;" % (up + 12)
        out = ['<div class="card fb w%d%s" style="%s%s">' % (cols, " sg1" if single else "", lift, self.height(rows)),
               ('<h2%s>%s</h2>' % (' style="color:%s"' % E(self.readable(hc)) if hc and SAFE_COLOR.match(str(hc)) else "",
                                   E(title))) if has_title else ""]
        if not ents:
            out.append("</div>")
            return "".join(out)
        hours = c.get("hours_to_show") or (int(c.get("days_to_show") or 1) * 24)

        def value_fn(x, d):
            def fn():
                st = self.st(x)
                txt = fmt_state(st, x, self.prec(x) if d is None else d)
                unit = ((st or {}).get("a") or {}).get("unit_of_measurement")
                if unit and txt.endswith(" " + unit):     # large value, smaller unit
                    return ('%s<span class="u">%s</span>' % (E(txt[:-len(unit) - 1]), E(unit)), None)
                return (E(txt), None)
            return fn

        if not single:
            return self.stat_multi(c, ents, title if has_title else "", hc, hours, gh, cols, rows)
        e = ents[0]
        try:
            size = max(18, min(64, int(str(e.get("state_size") or "40").replace("px", ""))))
        except ValueError:
            size = 40
        if e.get("show_state") is not False:
            out.append('<div class="sv" style="font-size:%dpx;line-height:%dpx">%s</div>' % (
                size, size, self.text_slot(e["entity"], value_fn(e["entity"], e.get("decimals")))))
        if ents[0].get("graph_type") == "bar":
            try:
                pph = float(ents[0].get("points_per_hour") or c.get("points_per_hour") or 1)
            except (TypeError, ValueError):
                pph = 1
            nbars = max(4, min(48, int(round(hours * pph))))
            color = ents[0].get("color")
            color = self.series_color(ents[0]["entity"], color, 0, "#db3a4b")
            out.append(self.chart([(ents[0]["entity"], color)], hours, gh,
                                  bars=nbars, cls="chart bleed"))
        else:
            out.append(self.chart([(e["entity"], e.get("color"), self.thresholds(e)) for e in ents],
                                  hours, gh, cls="chart bleed"))
        out.append("</div>")
        return "".join(out)

    @staticmethod
    def thresholds(e):
        """Active color_thresholds of an entity -> [(value, (r, g, b))] sorted, or None."""
        th = e.get("color_thresholds") if isinstance(e, dict) else None
        if not isinstance(th, dict) or not th.get("enabled"):
            return None
        out = []
        for x in th.get("values") or []:
            try:
                rgb = hex_rgb(x.get("color"))
                if rgb:
                    out.append((float(x.get("value")), rgb))
            except (TypeError, ValueError, AttributeError):
                pass
        out.sort()
        return tuple(out) or None

    def stat_value_fn(self, e):
        """Value + unit; coloured if "state_adaptive_color" (fixed colour or thresholds)."""
        eid, d = e["entity"], e.get("decimals")
        fixed = e.get("color") if e.get("state_adaptive_color") and hex_rgb(e.get("color")) else None
        stops = []
        th = e.get("color_thresholds")
        if e.get("state_adaptive_color") and isinstance(th, dict) and th.get("enabled"):
            for x in th.get("values") or []:
                try:
                    rgb = hex_rgb(x.get("color"))
                    if rgb:
                        stops.append((float(x.get("value")), rgb))
                except (TypeError, ValueError, AttributeError):
                    pass
            stops.sort()

        def fn():
            st = self.st(eid)
            txt = fmt_state(st, eid, self.prec(eid) if d is None else d)
            unit = ((st or {}).get("a") or {}).get("unit_of_measurement")
            if unit and txt.endswith(" " + unit):
                html_ = '%s<span class="u">%s</span>' % (E(txt[:-len(unit) - 1]), E(unit))
            else:
                html_ = E(txt)
            color = fixed
            v = num_value(st)
            if stops and v is not None:
                color = mix_color(stops, v)
            if color:
                html_ = '<span style="color:%s">%s</span>' % (self.readable(color), html_)
            return (html_, None)
        return fn

    def readable(self, color):
        """Colour chosen in a card, readable on the theme background (light theme)."""
        return theme.readable(color, self.pal().get("card") or "#1c1c1c")

    def stat_multi(self, c, ents, title, hc, hours, gh, cols, rows):
        """Several entities. Names shown: "name value" list. Names hidden: values
        placed left / centre / right (align_state), each at its own size."""
        # Names under the values (name_position: below): large values presentation,
        # like the original card; otherwise "dot name value" list.
        below = any(not e.get("hide_name") and e.get("name_position") == "below" for e in ents)
        listed = any(not e.get("hide_name") for e in ents) and not below
        if not gh and rows:
            gh = rows * 56 + (rows - 1) * 8 - (42 if title else 12) - (32 * len(ents) if listed else 52) - 16
        gh = gh or 150
        ic = c.get("card_icon")
        icc = c.get("card_icon_color")
        icon = ""
        if ic and title:
            icon = '<span class="hic"%s>%s</span>' % (
                ' style="color:%s"' % E(icc) if icc and SAFE_COLOR.match(str(icc)) else "",
                self.icon(icons.from_mdi(ic) or "dot"))
        out = ['<div class="card fb w%d %s" style="%s">' % (cols, "sgl" if listed else "sgz", self.height(rows)),
               ('<h2%s>%s%s</h2>' % (' style="color:%s"' % E(self.readable(hc)) if hc and SAFE_COLOR.match(str(hc)) else "",
                                     icon, E(title))) if title else ""]
        series, colors, barmap = [], [], []
        barmap = {}
        for i, e in enumerate(ents):
            color = e.get("color") if hex_rgb(e.get("color")) else self.series_color(e["entity"], None, i)
            stops = self.thresholds(e)
            if stops:
                color = "#%02x%02x%02x" % stops[0][1]
            colors.append(color)
            if e.get("show_graph") is False:        # value alone, no curve (like HA)
                continue
            if e.get("graph_type") == "bar":
                try:
                    pph = float(e.get("points_per_hour") or c.get("points_per_hour") or 1)
                except (TypeError, ValueError):
                    pph = 1
                barmap[len(series)] = max(4, min(48, int(round(hours * pph))))
            series.append((e["entity"], color, stops, e.get("show_fill") is not False))
        if listed:
            for color, e in zip(colors, ents):
                eid = e["entity"]
                out.append('<div class="sl"><i style="background:%s"></i><span class="sn">%s</span>%s</div>' % (
                    color, E(self.nm(eid, e.get("name"))),
                    self.text_slot(eid, self.stat_value_fn(e), cls="sx")))
            out.append(self.chart(series, hours, gh, barmap=barmap))
        else:
            # offsets requested by the "styles" of the card (margins of the alignment classes)
            shift, push_right = {}, False
            for m in re.finditer(r"\.sgc-state-align-(left|center|right)\s*\{([^}]*)\}", str(c.get("styles") or "")):
                dx = dy = 0.0
                mm = re.search(r"margin\s*:\s*(-?[\d.]+)px\s+(-?[\d.]+)(?:px)?\s+(-?[\d.]+)(?:px)?\s+(-?[\d.]+)(?:px)?", m.group(2))
                if mm:
                    top, right, _, left = [float(x) for x in mm.groups()]
                    dy = top
                    dx = {"left": left, "right": -right, "center": (left - right) / 2}[m.group(1)]
                    if m.group(1) == "center" and right < 0 and right < left:
                        # centre pushed to the right (negative right margin): aligned right
                        push_right, dx = True, 0.0
                mt = re.search(r"margin-top\s*:\s*(-?[\d.]+)px", m.group(2))
                if mt:
                    dy = float(mt.group(1))
                shift[m.group(1)] = (dx, dy)
            # Like the original card: line height 1.6 x the size, 5 px above and
            # below each value, areas aligned at the top under the title; the height
            # of the strip takes the vertical offsets of the styles into account.
            zones = {"left": [], "center": [], "right": []}
            hmax = 0
            for e in ents:
                al = e.get("align_state") if e.get("align_state") in zones else "left"
                size = int(max(12, min(64, css_px(e.get("state_size"), 30))))
                lh = int(round(size * 1.6))
                dx, dy = shift.get(al, (0, 0))
                nm = ""
                if below and not e.get("hide_name"):
                    lh = size + 4
                    nm = '<span class="svn">%s</span>' % E(self.nm(e["entity"], e.get("name")))
                hmax = max(hmax, lh + 10 + int(round(dy)) + (16 if nm else 0))
                zones[al].append('<span class="sv" style="font-size:%dpx;line-height:%dpx;top:%dpx%s">%s%s</span>' % (
                    size, lh, round(dy) + 5,
                    (";left:%dpx" % round(dx)) if dx else "",
                    self.text_slot(e["entity"], self.stat_value_fn(e)), nm))
            out.append('<div class="sz" style="height:%dpx">%s</div>' % (hmax, "".join(
                '<span class="z%s">%s</span>' % ("r" if k == "center" and push_right else k[0], "".join(v))
                for k, v in zones.items() if v)))
            out.append(self.chart(series, hours, gh, cls="chart bleed", barmap=barmap))
        out.append("</div>")
        return "".join(out)

    def stack(self, c, cls):
        self.in_stack += 1
        inner = "".join(self.card(x) for x in c.get("cards") or [])
        self.in_stack -= 1
        if not inner:
            return ""
        return '<div class="%s">%s%s</div>' % (cls, self.title(c), inner)

    def c_vertical_stack(self, c):
        return self.stack(c, "vs")

    def c_horizontal_stack(self, c):
        return self.stack(c, "hs")

    def c_custom_stack_in_card(self, c):
        """A single card (a single background) containing the stacked cards, like stack-in-card."""
        cards = [x for x in c.get("cards") or [] if isinstance(x, dict)]
        parts, skip = [], set()
        self.in_sic += 1
        for i, x in enumerate(cards):
            if i in skip:
                continue
            nxt = cards[i + 1] if i + 1 < len(cards) else {}
            # Dots aligned to the right just after a tile: on the line of the tile
            # (replaces the card_mod negative-margin offset).
            if (nxt.get("type") == "custom:mushroom-chips-card" and nxt.get("alignment") == "end"
                    and x.get("type") in ("custom:mushroom-template-card", "custom:mushroom-entity-card",
                                          "tile")):
                chips = self.chips_inner(nxt)
                if chips:
                    self.pending_side = '<span class="subs">%s</span>' % chips
                    skip.add(i + 1)
            parts.append(self.card(x))
            self.pending_side = ""
        self.in_sic -= 1
        inner = "".join(parts)
        if not inner:
            return ""
        mode = " sh" if c.get("mode") == "horizontal" else ""
        # Width in the section (grid_options): half card, third... like the other cards.
        cols, _ = self.size(c, 12, None)
        if cols in (3, 4, 6, 9) and not self.in_stack:
            mode += " w%d" % cols
        return '<div class="card sic%s">%s%s</div>' % (mode, self.title(c), inner)

    def c_grid(self, c):
        cols = int(c.get("columns") or 3)
        self.in_stack += 1
        inner = "".join(self.card(x) for x in c.get("cards") or [])
        self.in_stack -= 1
        if not inner:
            return ""
        return '<div class="grid g%d">%s%s</div>' % (min(cols, 4), self.title(c), inner)

    def c_conditional(self, c):
        return self.cond_wrap(c.get("conditions"), self.card(c.get("card") or {}))

    def cond_wrap(self, conds, inner):
        conds = [x for x in (conds or []) if isinstance(x, dict)]
        deps = [x.get("entity") for x in conds if x.get("entity")]
        if not deps or not inner:
            return inner

        def ok():
            for x in conds:
                e = x.get("entity")
                if not e:
                    continue
                st = self.st(e)
                s = st.get("s") if st else None
                kind = x.get("condition", "state")
                if kind == "numeric_state":
                    try:
                        f = float(s)
                    except (TypeError, ValueError):
                        return False
                    if "above" in x and not f > float(x["above"]):
                        return False
                    if "below" in x and not f < float(x["below"]):
                        return False
                    continue
                want, nwant = x.get("state"), x.get("state_not")
                if want is not None:
                    want = want if isinstance(want, list) else [want]
                    if s not in [str(w) for w in want]:
                        return False
                if nwant is not None:
                    nwant = nwant if isinstance(nwant, list) else [nwant]
                    if s in [str(w) for w in nwant]:
                        return False
            return True

        def fn():
            return (None, "" if ok() else "hid")
        sid = self.slot(deps, fn)
        return '<div id="%s" class="cond %s" data-b="cond">%s</div>' % (sid, fn()[1], inner)

    # ---- cameras ---------------------------------------------------------
    def overlay(self, ents):
        parts = []
        for e in ents or []:
            if isinstance(e, str):
                e = {"entity": e}
            eid = e.get("entity") if isinstance(e, dict) else None
            if eid:     # icon only, coloured according to the state (like picture-glance)
                parts.append(self.box_open("oi " + self.dc(eid, e.get("icon")), eid, None, tag="span")
                             + self.ent_icon(eid, e.get("icon")) + "</span>")
        return '<span class="co">%s</span>' % "".join(parts) if parts else ""

    def c_picture_glance(self, c):
        cam = c.get("camera_image") or (c.get("entity") if domain_of(c.get("entity")) == "camera" else None)
        if not cam:
            return self.c_fallback(c)
        title = c.get("title") if isinstance(c.get("title"), str) else ""
        return self.camera(cam, title, self.overlay(c.get("entities")))

    def c_picture_entity(self, c):
        eid = c.get("entity")
        cam = c.get("camera_image") or (eid if domain_of(eid) == "camera" else None)
        if not cam:
            return self.c_fallback(c)
        title = self.nm(eid, c.get("name")) if c.get("show_name", True) else ""
        state = ""
        if eid and c.get("show_state", True):
            state = '<span class="co">%s</span>' % self.text_slot(eid)
        return self.camera(cam, title, state)

    # ---- picture card (fixed image) ---------------------------------------
    def img_source(self, image):
        """image of a picture card -> HA path (/local/..., /api/image/serve/...) or http(s) URL.
        Image uploaded in HA (media-source://image_upload/ID): 512 px for types 1 and 2
        (old devices), original size on type 3."""
        return img_path(image, self.modern)

    def img_key(self, spec):
        key = hashlib.md5(repr(spec).encode("utf-8")).hexdigest()[:10]
        self.imgs[key] = spec
        return key

    def c_picture(self, c):
        """Picture card: the image over the whole width of the card, without margin (like HA).
        With an imposed height (rows), the image covers the card (background, understood by Android 4)."""
        name = E(self.store.name)
        ent = c.get("image_entity")
        if isinstance(ent, str) and domain_of(ent) in ("image", "person"):
            key = self.img_key(("ent", ent))

            def src(e=ent, k=key):     # entity_picture change (jeton, nouvelle image) : nouvelle adresse
                pic = ((self.st(e) or {}).get("a") or {}).get("entity_picture") or ""
                return "/%s/img?i=%s&v=%s" % (name, k, hashlib.md5(pic.encode("utf-8")).hexdigest()[:8])
        else:
            path = self.img_source(c.get("image"))
            if not path:
                return self.c_fallback(c)
            key = self.img_key(("url", path))

            def src(k=key):
                return "/%s/img?i=%s" % (name, k)
        cols, rows = self.size(c, 12, None)
        act = self.resolve_action(c.get("tap_action"), c.get("entity"), "none")
        alt = E(c.get("alt_text") or "") if isinstance(c.get("alt_text"), str) else ""
        if rows and not self.in_stack:
            h = rows * 56 + (rows - 1) * 8

            def html(s=src):
                return ('<span class="pb" style="background-image:url(%s)"></span>' % s(), None)
            body, style = html()[0], "height:%dpx" % h
        else:
            def html(s=src):
                return ('<img class="pi" src="%s" alt="%s">' % (s(), alt), None)
            body, style = html()[0], ""
        if ent and isinstance(ent, str) and domain_of(ent) in ("image", "person"):
            sid = self.slot([ent], html)
            body = '<span id="%s">%s</span>' % (sid, body)
        attrs = self.action_attrs(act)
        return '<div class="card w%d pic"%s%s>%s</div>' % (
            cols, attrs, ' style="%s"' % style if style else "", body)

    def first_camera(self, c):
        cams = sorted(e for e in collect_entities(c) if domain_of(e) == "camera")
        if not cams:
            for v in (c.get("cameras") or []):
                if isinstance(v, dict) and domain_of(v.get("camera_entity")) == "camera":
                    return v["camera_entity"]
        return cams[0] if cams else None

    def c_custom_advanced_camera_card(self, c):
        cam = self.first_camera(c)
        return self.camera(cam) if cam else ""

    def c_custom_webrtc_camera(self, c):
        cam = self.first_camera(c)
        return self.camera(cam) if cam else ""

    # ---- translated custom cards ---------------------------------------
    def c_custom_button_card(self, c):
        eid = c.get("entity")
        name = c.get("name") if isinstance(c.get("name"), str) and "[[[" not in c.get("name") else None
        if not eid and not name:
            return ""  # spacer or 100 % JavaScript card
        act = self.resolve_action(c.get("tap_action"), eid,
                                  self.default_tap(eid) if eid else "none")
        nm = E(self.nm(eid, name) if eid else name) if c.get("show_name", True) else ""
        state = self.text_slot(eid) if eid and c.get("show_state", False) else ""
        icon = c.get("icon") if isinstance(c.get("icon"), str) and "[[[" not in c.get("icon") else None
        layout = str(c.get("layout") or "vertical")
        h = self.card_style(c).get("h")
        if h and h <= 80:
            # Low imposed height (e.g. 60 px): compact button on one unit,
            # icon to the left of the name, all centred.
            cols, rows = self.size(c, 3, 1)
            return self.tile_html(eid, nm, state, act, cfg_icon=icon, base_extra=" bt bc",
                                  cols=cols, rows=1, card=c)
        if layout == "vertical":
            cols, rows = self.size(c, 12, None if self.in_stack else 5)
        else:
            cols, rows = self.size(c, 12, 1)
        return self.tile_html(eid, nm, state, act, cfg_icon=icon, base_extra=" bt" + (" big5" if rows and rows >= 4 else ""),
                              cols=cols, rows=rows, vertical=(layout == "vertical"), card=c)

    def c_custom_mushroom_entity_card(self, c):
        return self.c_tile(c)

    def c_custom_mushroom_template_card(self, c):
        eid = c.get("entity")
        primary = c.get("primary") or ""
        secondary = c.get("secondary") or ""
        if not primary and not secondary and not eid:
            return ""
        act = self.resolve_action(c.get("tap_action"), eid, "none")
        icon = c.get("icon") if not has_tpl(c.get("icon")) else None
        vertical = c.get("layout") == "vertical"
        cols, rows = self.size(c, 6, 2 if vertical else 1)
        if vertical and self.in_stack and not c.get("grid_options") and not c.get("layout_options"):
            rows = None         # in a stack: natural height, like HA
        return self.tile_html(eid, self.tpl_slot(primary), self.tpl_slot(secondary) if secondary else "",
                              act, cfg_icon=icon or "mdi:dot", optimistic=False,
                              cols=cols, rows=rows, vertical=vertical,
                              icon_color=c.get("icon_color"), card=c)

    def c_custom_mushroom_chips_card(self, c):
        al = {"end": " ar", "center": " ac", "justify": " ac"}.get(c.get("alignment"), "")
        inner = self.chips_inner(c)
        return '<div class="badges chips%s">%s</div>' % (al, inner) if inner else ""

    def chips_inner(self, c):
        out = []
        for ch in c.get("chips") or []:
            if not isinstance(ch, dict):
                continue
            t = ch.get("type")
            eid = ch.get("entity")
            if t == "template" and ch.get("content"):
                icon = ch.get("icon") if not has_tpl(ch.get("icon")) else None
                col = ch.get("icon_color") if not has_tpl(ch.get("icon_color")) else None
                out.append('<span class="badge %s">%s%s</span>' % (
                    mc_class(col), self.icon(icons.from_mdi(icon) or "dot") if icon else "",
                    self.tpl_slot(ch["content"])))
            elif eid and t == "weather":
                self.icons.update(set(icons.WEATHER.values()))

                def wfn(e=eid, sc=ch.get("show_conditions"), stp=ch.get("show_temperature")):
                    st = self.st(e) or {}
                    a = st.get("a") or {}
                    txt = []
                    if sc:
                        txt.append(weather_txt(st.get("s")))
                    if stp and a.get("temperature") is not None:
                        txt.append("%s %s" % (num(a["temperature"]), a.get("temperature_unit", TEMP_UNIT)))
                    return (self.icon(icons.WEATHER.get(st.get("s"), "cloud")) + E(" ".join(txt)), None)
                sid = self.slot([eid], wfn)
                out.append('<span id="%s" class="badge wchip%s">%s</span>' % (
                    sid, "" if (ch.get("show_conditions") or ch.get("show_temperature")) else " io", wfn()[0]))
            elif eid and t in ("entity", "light", "alarm-control-panel", None):
                out.append(self.badge(eid, None, ch.get("icon"), color=ch.get("icon_color"),
                                      info=ch.get("content_info")))
        return "".join(out)

    def c_custom_bubble_card(self, c):
        ct = c.get("card_type")
        if ct == "separator":
            return '<div class="hd">%s</div>' % E(str(c.get("name") or "")) if c.get("name") else ""
        if ct != "button":
            return ""  # pop-up, piles de boutons horizontales… : non pris en charge
        eid = c.get("entity")
        if not eid:
            return ""
        act = self.resolve_action((c.get("button_action") or {}).get("tap_action")
                                  or c.get("tap_action"), eid, self.default_tap(eid))
        sub = c.get("sub_button")
        if isinstance(sub, dict):
            sub = (sub.get("main") or []) + (sub.get("bottom") or [])
        chips = []
        for s in (sub or [])[:4]:
            if isinstance(s, dict) and s.get("entity"):
                se = s["entity"]
                txt = (E(self.nm(se, s.get("name"))) + " ") if s.get("show_name") else ""
                # Values: show_state (old format) or state_content (new: "state",
                # "last_updated", "last_changed", attribute name; text or list).
                sc = s.get("state_content")
                sc = [sc] if isinstance(sc, str) else [x for x in (sc or []) if isinstance(x, str)]
                if s.get("show_state") and "state" not in sc:
                    sc.insert(0, "state")
                if s.get("show_last_changed") or s.get("show_last_updated"):
                    sc.append("last_changed")
                vals = []
                for k in sc[:3]:
                    if k == "state":
                        def fn(e=se):  # Bubble capitalises the state
                            return (E(cap(fmt_state(self.st(e), e, self.prec(e)))), None)
                        vals.append(self.text_slot(se, fn))
                    elif k in ("last_updated", "last_changed", "last-updated", "last-changed"):
                        def fn(e=se):  # "Il y a 44 minutes", like Bubble
                            st = self.st(e)
                            return (rel_span(st.get("lc") if st else None), None)
                        vals.append(self.text_slot(se, fn))
                    elif re.match(r"^\w+$", k):
                        def fn(e=se, k=k):
                            v = ((self.st(e) or {}).get("a") or {}).get(k)
                            return (E("—" if v is None else str(v)), None)
                        vals.append(self.text_slot(se, fn))
                txt += " · ".join(vals)
                ic = self.ent_icon(se, s.get("icon")) if s.get("show_icon", True) is not False else ""
                if not txt and not ic:
                    continue
                chips.append(self.box_open("badge %s%s" % ("" if txt else "io ", self.dc(se, s.get("icon"))),
                                           se, None, tag="span")
                             + ic + txt + "</span>")
        # Values on the right, on the same line as the name (like bubble-card).
        side = '<span class="subs">%s</span>' % "".join(chips) if chips else ""
        # Bubble only shows the state under the name if show_state is on.
        # New format: state_content (text or list) replaces show_state.
        state = self.content_slots(eid, c.get("state_content"))             or (self.text_slot(eid) if c.get("show_state") else "")
        cols, rows = self.size(c, 12 if chips else 6, 1)
        return self.tile_html(eid, E(self.nm(eid, c.get("name"))), state, act,
                              cfg_icon=c.get("icon"), side=side, cols=cols, rows=rows,
                              base_extra=" tb" if chips else "")

    # Custom card "custom:digital-clock": local clock (JS).
    def c_custom_digital_clock(self, c):
        def line(fmt, lay, dfmt, dsize):
            lay = lay if isinstance(lay, dict) else {}
            fmt = fmt if isinstance(fmt, str) and fmt else dfmt
            fs = max(8.0, min(120.0, css_px(lay.get("fontSize"), dsize * 14.0)))
            lh = css_px(lay.get("lineHeight", "1em"), fs, base=fs)
            fw = str(lay.get("fontWeight", "bold"))
            if not re.match(r"^(\d00|normal|bold|lighter|bolder)$", fw):
                fw = "bold"
            ta = lay.get("textAlign") if lay.get("textAlign") in ("left", "center", "right") else "center"
            return ('<div class="cl" data-f="%s" style="font-size:%dpx;line-height:%dpx;'
                    'font-weight:%s;text-align:%s">&nbsp;</div>' % (E(fmt), round(fs), round(lh), fw, ta))
        pad = str(c.get("padding") or "8px")
        if not re.match(r"^(\d{1,2}px\s*){1,4}$", pad):
            pad = "8px"
        return ('<div class="card clock" style="padding:%s">%s%s</div>' % (
            pad.strip(), line(c.get("firstLineFormat"), c.get("firstLineLayout"), "HH:mm", 2.8),
            line(c.get("secondLineFormat"), c.get("secondLineLayout"), "ccc d LLL", 1.6)))

    def c_fallback(self, c):
        """Unknown/custom card: readable list of the entities found."""
        cam = self.first_camera(c)
        if cam:
            return self.camera(cam)
        title = (c.get("title") or c.get("name") or c.get("card_header")
                 or c.get("header") or "")
        if not isinstance(title, str) or "[[[" in title or has_tpl(title):
            title = ""
        ents = []
        for e in c.get("entities") or []:
            if isinstance(e, str):
                ents.append((e, {}))
            elif isinstance(e, dict) and e.get("entity"):
                ents.append((e["entity"], e))
        if c.get("entity") and not ents:
            ents.append((c["entity"], c))
        if not ents:
            nested = sorted(collect_entities(c))
            ents = [(e, {}) for e in nested[:8]]
        if not ents:
            return ""
        out = ['<div class="card fb">']
        if title:
            out.append("<h2>%s</h2>" % E(title))
        for eid, o in ents:
            out.append(self.entity_row(eid, {"name": o.get("name") if isinstance(o, dict) else None}))
        out.append("</div>")
        return "".join(out)
