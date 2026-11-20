"""Icons sent as a "sprite": only those used by the page are included.

- Material Design icons (mdi:xxx), the same as HA: key "m-xxx", paths read from
  mdi.txt.gz (Pictogrammers @mdi/svg package, Apache 2.0 licence; see dev/build_mdi.py).
- House icons (24x24, 2 px stroke): weather and internal buttons (arrows, stop...).
"""
import gzip
import os

_MDI = None


def _mdi():
    """Name -> path table, loaded once (about 3 MB in memory)."""
    global _MDI
    if _MDI is None:
        table, alias = {}, {}
        try:
            f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mdi.txt.gz")
            with gzip.open(f, "rt", encoding="utf-8") as g:
                for line in g:
                    name, _, d = line.rstrip("\n").partition("\t")
                    if d.startswith("="):
                        alias[name] = d[1:]
                    elif d:
                        table[name] = d
        except OSError:
            pass
        for a, n in alias.items():
            if a not in table and n in table:
                table[a] = table[n]
        _MDI = table
    return _MDI


def mdi_key(name):
    """"mdi:gate" -> "m-gate" if the icon exists, otherwise None."""
    name = str(name or "").strip().lower()
    for p in ("mdi:", "hass:"):
        if name.startswith(p):
            name = name[len(p):]
            break
    else:
        return None
    return ("m-" + name) if name in _mdi() else None

_CLOUD_UP = '<path d="M17.5 15H8a4.5 4.5 0 1 1 1-8.9A5.5 5.5 0 0 1 19.6 8 3.5 3.5 0 0 1 17.5 15z"/>'

ICONS = {
    "bulb": '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.8.8 1 1.5 1 2.5h6c0-1 .2-1.7 1-2.5A6 6 0 0 0 12 3z"/>',
    "plug": '<path d="M9 2v6M15 2v6M6 8h12v3a6 6 0 0 1-12 0zM12 17v5"/>',
    "power": '<path d="M12 2v10M18.4 6.6a9 9 0 1 1-12.8 0"/>',
    "toggle": '<rect x="2" y="7" width="20" height="10" rx="5"/><circle cx="16" cy="12" r="3"/>',
    "fan": '<circle cx="12" cy="12" r="2"/><path d="M12 10c0-4 1-7 4-7s3 4-2 7M14 12c4 0 7 1 7 4s-4 3-7-2'
           'M12 14c0 4-1 7-4 7s-3-4 2-7M10 12c-4 0-7-1-7-4s4-3 7 2"/>',
    "thermo": '<path d="M14 14.8V4a2 2 0 0 0-4 0v10.8a4 4 0 1 0 4 0z"/><path d="M12 9v7"/>',
    "drop": '<path d="M12 2.7l5.7 5.6a8 8 0 1 1-11.4 0z"/>',
    "bolt": '<path d="M13 2L3 14h9l-1 8 10-12h-9z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4'
           'M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "moon": '<path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/>',
    "cloud": '<path d="M17.5 19H8a5 5 0 1 1 1.2-9.9A6 6 0 0 1 20.8 11 4 4 0 0 1 17.5 19z"/>',
    "cloudsun": '<path d="M12 2v2M4.9 4.9l1.4 1.4M2 12h2M19.1 4.9l-1.4 1.4"/><path d="M8.5 9.5a4 4 0 0 1 7-1"/>'
                '<path d="M17 20H9a4 4 0 1 1 .9-7.9A5 5 0 0 1 19.6 14 3 3 0 0 1 17 20z"/>',
    "rain": _CLOUD_UP + '<path d="M8 21l1-2M12 22l1-2M16 21l1-2"/>',
    "pour": _CLOUD_UP + '<path d="M7 22l2-4M11 22l2-4M15 22l2-4"/>',
    "snow": _CLOUD_UP + '<path d="M8 19h.01M12 21h.01M16 19h.01M10 22.5h.01M14 18h.01"/>',
    "storm": _CLOUD_UP + '<path d="M13 15l-3 4h4l-2 4"/>',
    "fog": '<path d="M4 9h16M4 13h16M6 17h12M8 5h8"/>',
    "wind": '<path d="M3 8h11a3 3 0 1 0-3-3M3 12h16a3 3 0 1 1-3 3M3 16h8"/>',
    "home": '<path d="M3 11l9-8 9 8M5 9.5V21h14V9.5M10 21v-6h4v6"/>',
    "door": '<path d="M6 21V3h12v18M4 21h16M14 12h.01"/>',
    "window": '<rect x="4" y="3" width="16" height="18" rx="1"/><path d="M12 3v18M4 12h16"/>',
    "shutter": '<rect x="4" y="3" width="16" height="18" rx="1"/><path d="M4 7.5h16M4 12h16M4 16.5h16"/>',
    "motion": '<circle cx="12" cy="12" r="2"/><path d="M8 8a6 6 0 0 0 0 8M16 8a6 6 0 0 1 0 8'
              'M5 5a10 10 0 0 0 0 14M19 5a10 10 0 0 1 0 14"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "camera": '<path d="M3 7h4l2-3h6l2 3h4v13H3z"/><circle cx="12" cy="13" r="4"/>',
    "gate": '<path d="M3 20V6M21 20V6M3 8h18M3 18h18M8 8v10M13 8v10M17 8v10"/>',
    "garage": '<path d="M3 21V9l9-6 9 6v12M7 21v-9h10v9M7 15h10M7 18h10"/>',
    "vacuum": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="9" r="2"/><path d="M7 16h10"/>',
    "play": '<path d="M7 4l13 8-13 8z"/>',
    "pause": '<path d="M8 5v14M16 5v14"/>',
    "speaker": '<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a9 9 0 0 1 0 12"/>',
    "tv": '<rect x="3" y="5" width="18" height="12" rx="2"/><path d="M8 21h8M12 17v4"/>',
    "gauge": '<path d="M4 18a9 9 0 1 1 16 0"/><path d="M12 14l4-5"/>',
    "battery": '<rect x="3" y="7" width="16" height="10" rx="2"/><path d="M21 11v2M6 10v4M9 10v4"/>',
    "alert": '<path d="M12 3l10 18H2z"/><path d="M12 10v4M12 17h.01"/>',
    "palette": '<path d="M12 3a9 9 0 1 0 0 18c1.5 0 2-1 2-2 0-1.5-1-2-1-3s1-2 2.5-2H18a3 3 0 0 0 3-3 9 9 0 0 0-9-8z"/>'
               '<path d="M7.5 11h.01M10 7.5h.01M14.5 7.5h.01"/>',
    "script": '<circle cx="12" cy="12" r="9"/><path d="M10 8.5l5 3.5-5 3.5z"/>',
    "button": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/>',
    "person": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "leaf": '<path d="M5 21c0-9 5-16 16-16 0 11-7 16-16 16zM5 21l8-8"/>',
    "wifi": '<path d="M2 9a15 15 0 0 1 20 0M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0M12 19.5h.01"/>',
    "server": '<rect x="3" y="4" width="18" height="7" rx="1"/><rect x="3" y="13" width="18" height="7" rx="1"/>'
              '<path d="M7 7.5h.01M7 16.5h.01"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "solar": '<rect x="3" y="11" width="18" height="9" rx="1"/><path d="M3 15.5h18M9 11v9M15 11v9M12 3v3M6 5l1.5 2'
             'M18 5l-1.5 2"/>',
    "dot": '<circle cx="12" cy="12" r="4"/>',
    "up": '<path d="M6 15l6-6 6 6"/>',
    "down": '<path d="M6 9l6 6 6-6"/>',
    "stop": '<rect x="7" y="7" width="10" height="10" rx="1.5"/>',
    "car": '<path d="M4 16V12l2.5-5h11l2.5 5v4z"/><path d="M4 12h16"/><circle cx="7.5" cy="16.5" r="1.8"/>'
           '<circle cx="16.5" cy="16.5" r="1.8"/>',
    "walk": '<circle cx="13" cy="4" r="2"/><path d="M8 21l3-7 3 3v4M10.5 14l1-5 4 2.5 2 3M11.5 9l-3.5 2.5-1 3"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5h.01"/>',
}

# Keywords of the Material icons (mdi:xxx) -> house icon. Order matters.
MDI_KEYWORDS = [
    ("weather-fog", "fog"), ("weather-hazy", "fog"), ("weather-night", "moon"),
    ("weather-partly", "cloudsun"), ("weather-pouring", "pour"), ("weather-rain", "rain"),
    ("weather-snow", "snow"), ("weather-lightning", "storm"), ("weather-windy", "wind"),
    ("weather-sunny", "sun"), ("weather", "cloud"),
    ("lightning", "bolt"), ("flash", "bolt"), ("current", "bolt"), ("counter", "bolt"),
    ("transmission-tower", "bolt"), ("meter-electric", "bolt"),
    ("lightbulb", "bulb"), ("lamp", "bulb"), ("ceiling-light", "bulb"), ("led", "bulb"),
    ("light", "bulb"), ("power-plug", "plug"), ("power-socket", "plug"), ("socket", "plug"),
    ("outlet", "plug"), ("power", "power"), ("toggle", "toggle"), ("fan", "fan"),
    ("thermometer", "thermo"), ("thermostat", "thermo"), ("radiator", "thermo"),
    ("heat", "thermo"), ("water-percent", "drop"), ("humidity", "drop"), ("water", "drop"),
    ("faucet", "drop"), ("solar", "solar"), ("sun", "sun"), ("moon", "moon"), ("cloud", "cloud"),
    ("door", "door"), ("window-shutter", "shutter"), ("blinds", "shutter"),
    ("roller-shade", "shutter"), ("curtains", "shutter"), ("window", "window"),
    ("motion", "motion"), ("walk", "walk"), ("run", "walk"), ("radar", "motion"),
    ("car", "car"), ("information", "info"), ("arrow-up", "up"), ("arrow-down", "down"),
    ("account", "person"), ("human", "motion"), ("lock", "lock"), ("cctv", "camera"),
    ("camera", "camera"), ("video", "camera"), ("webcam", "camera"), ("gate", "gate"),
    ("garage", "garage"), ("robot", "vacuum"), ("vacuum", "vacuum"), ("play", "play"),
    ("pause", "pause"), ("speaker", "speaker"), ("music", "speaker"), ("volume", "speaker"),
    ("television", "tv"), ("tv", "tv"), ("monitor", "tv"), ("home", "home"), ("house", "home"),
    ("gauge", "gauge"), ("speedometer", "gauge"), ("battery", "battery"), ("alert", "alert"),
    ("palette", "palette"), ("script", "script"), ("gesture", "button"), ("button", "button"),
    ("calendar", "calendar"), ("clock", "clock"), ("timer", "clock"), ("leaf", "leaf"),
    ("flower", "leaf"), ("sprout", "leaf"), ("tree", "leaf"), ("grass", "leaf"),
    ("mower", "leaf"), ("wifi", "wifi"), ("web", "wifi"), ("router", "wifi"),
    ("server", "server"), ("memory", "server"), ("harddisk", "server"), ("nas", "server"),
    ("database", "server"), ("cpu", "server"), ("air", "wind"), ("wind", "wind"),
]

DEVICE_CLASS = {
    "temperature": "thermo", "humidity": "drop", "moisture": "drop", "power": "bolt",
    "energy": "bolt", "current": "bolt", "voltage": "bolt", "apparent_power": "bolt",
    "battery": "battery", "motion": "motion", "occupancy": "motion", "presence": "motion",
    "door": "door", "garage_door": "garage", "opening": "door", "window": "window",
    "pm25": "wind", "pm10": "wind", "aqi": "wind", "volatile_organic_compounds": "wind",
    "pressure": "gauge", "atmospheric_pressure": "gauge", "illuminance": "sun",
    "connectivity": "wifi", "outlet": "plug", "shutter": "shutter", "blind": "shutter",
    "shade": "shutter", "curtain": "shutter", "gate": "gate", "garage": "garage",
    "timestamp": "clock", "uptime": "clock", "duration": "clock", "plug": "plug", "speaker": "speaker",
    "tv": "tv", "smoke": "alert", "gas": "alert", "problem": "alert", "safety": "alert",
}

DOMAIN = {
    "light": "bulb", "switch": "toggle", "fan": "fan", "cover": "shutter", "lock": "lock",
    "climate": "thermo", "water_heater": "thermo", "camera": "camera", "media_player": "speaker",
    "vacuum": "vacuum", "binary_sensor": "dot", "sensor": "gauge", "weather": "cloudsun",
    "person": "person", "device_tracker": "person", "input_boolean": "toggle",
    "automation": "script", "script": "script", "scene": "palette", "button": "button",
    "input_button": "button", "sun": "sun", "alarm_control_panel": "lock", "todo": "calendar",
    "calendar": "calendar", "number": "gauge", "input_number": "gauge", "select": "gauge",
    "input_select": "gauge", "update": "alert", "lawn_mower": "leaf", "remote": "tv",
    "siren": "alert", "humidifier": "drop", "time": "clock", "input_datetime": "clock",
}

WEATHER = {
    "clear-night": "moon", "cloudy": "cloud", "fog": "fog", "hail": "snow",
    "lightning": "storm", "lightning-rainy": "storm", "partlycloudy": "cloudsun",
    "pouring": "pour", "rainy": "rain", "snowy": "snow", "snowy-rainy": "snow",
    "sunny": "sun", "windy": "wind", "windy-variant": "wind", "exceptional": "alert",
}

# Colour group (CSS class "dc-xxx") per domain, like the HA state colours.
COLOR_GROUP = {
    "light": "light", "switch": "switch", "input_boolean": "switch", "automation": "switch",
    "fan": "fan", "cover": "cover", "lock": "lock", "climate": "climate",
    "water_heater": "climate", "media_player": "media", "vacuum": "vacuum",
    "lawn_mower": "vacuum", "binary_sensor": "binary", "camera": "media",
    "person": "person", "device_tracker": "person",
}


# Default icon (no icon chosen in HA): the HA one, in Material Design.
DEFAULT_MDI = {
    "bulb": "lightbulb", "plug": "power-plug", "power": "power", "toggle": "toggle-switch-variant",
    "fan": "fan", "thermo": "thermometer", "drop": "water-percent", "bolt": "flash",
    "home": "home", "door": "door", "window": "window-closed", "shutter": "window-shutter",
    "motion": "motion-sensor", "lock": "lock", "camera": "video", "gate": "gate",
    "garage": "garage", "vacuum": "robot-vacuum", "speaker": "speaker", "tv": "television",
    "gauge": "gauge", "battery": "battery", "alert": "alert", "palette": "palette",
    "script": "script-text", "button": "button-pointer", "person": "account", "leaf": "leaf",
    "wifi": "wifi", "calendar": "calendar", "clock": "clock-outline", "solar": "solar-power",
    "car": "car", "walk": "walk", "info": "information-outline",
}

# Icon -> colour group, for switches (switch, input_boolean...).
ICON_GROUP = {"bulb": "light", "fan": "fan", "shutter": "cover", "lock": "lock",
              "tv": "media", "speaker": "media", "vacuum": "vacuum", "thermo": "climate"}


def house(name):
    """House icon closest to an MDI name (used for the colour groups)."""
    name = str(name or "").lower()
    for p in ("mdi:", "hass:", "m-"):
        if name.startswith(p):
            name = name[len(p):]
            break
    for kw, icon in MDI_KEYWORDS:
        if kw in name:
            return icon
    return None


def from_mdi(name):
    """HA icon name -> icon key: the real MDI icon, otherwise the closest house icon."""
    return mdi_key(name) or house(name)


def default(h):
    """House icon -> HA default MDI icon (if known)."""
    m = DEFAULT_MDI.get(h)
    return ("m-" + m) if m and m in _mdi() else h


def group_icon(key):
    """Icon key -> house icon, for ICON_GROUP."""
    return house(key) if str(key).startswith("m-") else key


def pick(eid, cfg_icon=None, attrs=None):
    """Icon of an entity: the one chosen in HA, otherwise the domain default."""
    attrs = attrs or {}
    for cand in (cfg_icon, attrs.get("icon")):
        if isinstance(cand, str) and "{" not in cand:
            ic = from_mdi(cand)
            if ic:
                return ic
    dc = attrs.get("device_class")
    if dc in DEVICE_CLASS:
        return default(DEVICE_CLASS[dc])
    dom = eid.split(".", 1)[0] if isinstance(eid, str) else ""
    if dom == "sensor" and attrs.get("unit_of_measurement") is None:
        return "dot"
    return default(DOMAIN.get(dom, "dot"))


def sprite(names):
    """Hidden <svg> holding the <symbol>s of the icons used."""
    if not names:
        return ""
    out = []
    for n in sorted(names):
        if n in ICONS:
            out.append('<symbol id="i-%s" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
                       ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">%s</symbol>'
                       % (n, ICONS[n]))
        elif n.startswith("m-") and n[2:] in _mdi():
            out.append('<symbol id="i-%s" viewBox="0 0 24 24" fill="currentColor"><path d="%s"/></symbol>'
                       % (n, _mdi()[n[2:]]))
    return '<svg xmlns="http://www.w3.org/2000/svg" style="display:none">%s</svg>' % "".join(out)
