"""SlimDash - conversion d'une configuration Lovelace en HTML simple.

Le rendu produit du HTML statique + des "slots" : petits morceaux de la page
(texte d'un état, classe on/off d'une tuile...) recalculés côté serveur quand
une entité change, puis envoyés au navigateur sous forme de JSON minuscule.
"""
import hashlib
import html
import logging
import re
from datetime import datetime

import colorsys
import icons
import math
import theme

log = logging.getLogger("slimdash.render")

E = html.escape

# Domaines qu'un clic bascule (on/off) par défaut.
TOGGLE_DOMAINS = {
    "light", "switch", "fan", "input_boolean", "automation", "siren",
    "humidifier", "group", "lock",
}
# Domaines que l'interrupteur d'en-tête d'une carte entities bascule (DOMAINS_TOGGLE de HA).
HEADER_TOGGLE = ("fan", "input_boolean", "light", "switch", "group", "automation", "humidifier", "valve")
# Lignes dont la valeur se modifie dans la carte entities (champ, liste, heure).
EDIT_DOMAINS = ("number", "input_number", "select", "input_select", "time", "input_datetime",
                "text", "input_text", "date")
RUN_DOMAINS = {"scene": "Activer", "script": "Exécuter", "button": "Appuyer",
               "input_button": "Appuyer"}

ON_STATES = {"on", "open", "opening", "unlocked", "playing", "home", "cleaning",
             "heat", "cool", "heat_cool", "auto", "dry", "fan_only", "active",
             "above_horizon", "returning", "buffering"}
OFF_STATES = {"off", "closed", "closing", "locked", "idle", "paused", "standby",
              "not_home", "docked", "below_horizon"}

STATE_FR = {
    "unavailable": "Indisponible", "unknown": "Inconnu",
    "open": "Ouvert", "closed": "Fermé", "opening": "Ouverture",
    "closing": "Fermeture", "locked": "Verrouillé", "unlocked": "Déverrouillé",
    "locking": "Verrouillage", "unlocking": "Déverrouillage", "jammed": "Bloqué",
    "playing": "Lecture", "paused": "Pause", "idle": "Inactif",
    "standby": "Veille", "buffering": "Chargement",
    "home": "Maison", "not_home": "Absent",
    "docked": "À la base", "cleaning": "Nettoyage", "returning": "Retour base",
    "error": "Erreur",
    "heat": "Chauffage", "cool": "Climatisation", "heat_cool": "Auto",
    "auto": "Auto", "dry": "Déshumidif.", "fan_only": "Ventilation",
    "above_horizon": "Jour", "below_horizon": "Nuit",
    "armed_away": "Armée (absent)", "armed_home": "Armée (présent)",
    "armed_night": "Armée (nuit)", "disarmed": "Désarmée",
    "triggered": "Déclenchée", "pending": "En attente", "arming": "Armement",
}

BINARY_FR = {
    "motion": ("Mouvement", "Calme"), "occupancy": ("Détecté", "Libre"),
    "presence": ("Présent", "Absent"), "door": ("Ouverte", "Fermée"),
    "garage_door": ("Ouverte", "Fermée"), "window": ("Ouverte", "Fermée"),
    "opening": ("Ouvert", "Fermé"), "moisture": ("Humide", "Sec"),
    "smoke": ("Fumée !", "OK"), "gas": ("Gaz !", "OK"),
    "problem": ("Problème", "OK"), "safety": ("Danger", "OK"),
    "battery": ("Faible", "Normale"), "connectivity": ("Connecté", "Déconnecté"),
    "plug": ("Branché", "Débranché"), "power": ("Sous tension", "Hors tension"),
    "lock": ("Ouvert", "Verrouillé"), "running": ("En marche", "Arrêté"),
    "light": ("Lumière", "Sombre"), "sound": ("Son", "Calme"),
    "vibration": ("Vibration", "Calme"), "tamper": ("Sabotage", "OK"),
    "update": ("Mise à jour", "À jour"), "heat": ("Chaud", "Normal"),
    "cold": ("Froid", "Normal"),
}

WEATHER_FR = {
    "clear-night": "Nuit claire", "cloudy": "Nuageux", "fog": "Brouillard",
    "hail": "Grêle", "lightning": "Orage", "lightning-rainy": "Orage pluvieux",
    "partlycloudy": "Éclaircies", "pouring": "Averses", "rainy": "Pluie",
    "snowy": "Neige", "snowy-rainy": "Pluie et neige", "sunny": "Soleil",
    "windy": "Venteux", "windy-variant": "Venteux", "exceptional": "Exceptionnel",
}
DAYS_FR = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]

# Libellés d'état de Home Assistant (« domaine.classe.état » -> texte), remplis par le
# serveur à la connexion. Les tables ci-dessus ne servent plus que de secours.
TR = {}


def tr_state(dom, device_class, s):
    """Libellé HA d'un état (ex. switch on -> « Activé »), ou None."""
    if not TR or s is None:
        return None
    t = TR.get("%s.%s.%s" % (dom, device_class or "_", s))
    if t is None and device_class:
        t = TR.get("%s._.%s" % (dom, s))
    return t


def weather_txt(s):
    return tr_state("weather", None, s) or WEATHER_FR.get(s, s or "")


def domain_of(eid):
    return eid.split(".", 1)[0] if isinstance(eid, str) else ""


def num(v):
    """Nombre au format français (virgule), sinon None."""
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
    return group(s.replace(".", ","))


def group(numstr):
    """« 1003,5 » -> « 1 003,5 » (espace fine insécable entre les milliers)."""
    neg = numstr.startswith("-")
    body = numstr[1:] if neg else numstr
    ent, sep, dec = body.partition(",")
    if len(ent) > 3 and ent.isdigit():
        parts = []
        while len(ent) > 3:
            parts.insert(0, ent[-3:])
            ent = ent[:-3]
        parts.insert(0, ent)
        ent = "\u202f".join(parts)
    return ("-" if neg else "") + ent + sep + dec


def round_num(v, decimals):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    s = ("%." + str(int(decimals)) + "f") % f
    return group(s.replace(".", ","))


def fmt_time(iso):
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone()
    except (ValueError, TypeError):
        return str(iso)
    now = datetime.now().astimezone()
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    return dt.strftime("%d/%m %H:%M")


def since(ts):
    """Horodatage du dernier changement -> « depuis 14:32 » / « depuis le 12/11 »."""
    if not ts:
        return "—"
    try:
        dt = datetime.fromtimestamp(float(ts)).astimezone() if not isinstance(ts, str) \
            else datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
    except (TypeError, ValueError, OSError):
        return "—"
    now = datetime.now().astimezone()
    if dt.date() == now.date():
        return "depuis " + dt.strftime("%H:%M")
    return "depuis le " + dt.strftime("%d/%m")


def ts_epoch(ts):
    """Horodatage HA (nombre ou texte ISO) -> secondes depuis 1970, ou None."""
    if not ts:
        return None
    try:
        if not isinstance(ts, str):
            return float(ts)
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError, OSError):
        return None


TOTAL_UNITS = (("seconde", "secondes"), ("minute", "minutes"), ("heure", "heures"),
               ("jour", "jours"), ("semaine", "semaines"), ("mois", "mois"), ("an", "ans"))


def rel_fr(t, now=None, total=False):
    """Temps écoulé, comme HA en français : « Il y a 44 minutes », « Hier »…
    total=True : durée seule, sans « il y a » (« 1 mois »), comme le format « total » de HA.
    Même calcul que relFr() de s.js, qui le tient à jour."""
    if t is None:
        return "—"
    import time as _t
    s = max(0, int((now or _t.time()) - t))
    if total:
        for lim, div, u in ((45, 1, 0), (2700, 60, 1), (79200, 3600, 2), (432000, 86400, 3),
                            (2419200, 604800, 4), (31536000, 2592000, 5), (None, 31536000, 6)):
            if lim is None or s < lim:
                n = max(1, int(round(s / float(div)))) if u else s
                return "%d %s" % (n, TOTAL_UNITS[u][n > 1])
    if s < 45:
        txt = "maintenant" if s < 1 else "il y a %d seconde%s" % (s, "s" if s > 1 else "")
    elif s < 2700:
        m = max(1, int(round(s / 60.0)))
        txt = "il y a %d minute%s" % (m, "s" if m > 1 else "")
    elif s < 79200:
        h = max(1, int(round(s / 3600.0)))
        txt = "il y a %d heure%s" % (h, "s" if h > 1 else "")
    elif s < 432000:
        d = max(1, int(round(s / 86400.0)))
        txt = {1: "hier", 2: "avant-hier"}.get(d, "il y a %d jours" % d)
    elif s < 2419200:
        w = max(1, int(round(s / 604800.0)))
        txt = "la semaine dernière" if w == 1 else "il y a %d semaines" % w
    elif s < 31536000:
        m = max(1, int(round(s / 2592000.0)))
        txt = "le mois dernier" if m == 1 else "il y a %d mois" % m
    else:
        y = max(1, int(round(s / 31536000.0)))
        txt = "l’année dernière" if y == 1 else "il y a %d ans" % y
    return txt[:1].upper() + txt[1:]


def rel_span(ts, total=False):
    """Temps écoulé tenu à jour par s.js (classe ago, horodatage dans data-t ;
    data-m="t" pour une durée sans « il y a »)."""
    t = ts_epoch(ts)
    if t is None:
        return "—"
    return '<span class="ago" data-t="%d"%s>%s</span>' % (
        t, ' data-m="t"' if total else "", E(rel_fr(t, total=total)))


def ts_format(st, fmt=None):
    """Format d'affichage d'un capteur horodaté, comme HA (None si ce n'en est pas un) :
    « relative » pour un horodatage, « total » pour un temps de fonctionnement."""
    if not st or ts_epoch(st.get("s")) is None or not isinstance(st.get("s"), str) or "T" not in st["s"]:
        return None
    dc = (st.get("a") or {}).get("device_class")
    if dc not in ("timestamp", "uptime"):
        return None
    if fmt in ("relative", "total", "date", "time", "datetime"):
        return fmt
    return "total" if dc == "uptime" else "relative"


def ts_html(st, fmt):
    """Valeur HTML d'un capteur horodaté selon son format (voir ts_format)."""
    s = st.get("s")
    if fmt in ("relative", "total"):
        return rel_span(s, fmt == "total")
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone()
    except (ValueError, TypeError):
        return E(s)
    return E(dt.strftime({"date": "%d/%m/%Y", "time": "%H:%M", "datetime": "%d/%m/%Y %H:%M"}[fmt]))


def cap(txt):
    return txt[:1].upper() + txt[1:]


def fmt_state(st, eid, decimals=None):
    """Texte (non échappé) de l'état d'une entité, façon Home Assistant FR."""
    if st is None:
        return "—"
    s = st.get("s")
    a = st.get("a") or {}
    dom = domain_of(eid)
    if s in ("unavailable", "unknown"):
        return STATE_FR[s]
    t = tr_state(dom, a.get("device_class"), s)
    if dom == "light" and s == "on" and a.get("brightness") is not None:
        try:        # comme HA : la luminosité remplace « Allumé »
            return "%d %%" % round(int(a["brightness"]) * 100 / 255)
        except (TypeError, ValueError):
            pass
    if t is not None and dom not in ("weather", "climate", "cover"):
        return t
    if dom == "binary_sensor":
        pair = BINARY_FR.get(a.get("device_class"), ("Activé", "Désactivé"))
        return pair[0] if s == "on" else pair[1]
    if dom in ("light", "fan", "input_boolean", "siren", "humidifier"):
        if s == "on" and dom == "light" and a.get("brightness") is not None:
            try:
                return "Allumé %d %%" % round(int(a["brightness"]) * 100 / 255)
            except (TypeError, ValueError):
                pass
        if s == "on" and dom == "fan" and a.get("percentage"):
            return "Marche %s %%" % a.get("percentage")
        return {"on": "Allumé", "off": "Éteint"}.get(s, s)
    if dom in ("switch", "automation", "media_player", "group", "remote"):
        if s in ("on", "off"):
            return {"on": "Marche", "off": "Arrêt"}[s]
    if dom == "weather":
        temp = a.get("temperature")
        txt = weather_txt(s)
        if temp is not None:
            txt += " %s %s" % (num(temp) or temp, a.get("temperature_unit", "°C"))
        return txt
    if dom == "climate":
        cur = a.get("current_temperature")
        txt = t or (STATE_FR.get(s, s) if s != "off" else "Arrêt")
        if cur is not None:
            txt += " · %s °C" % (num(cur) or cur)
        return txt
    if dom == "cover" and a.get("current_position") is not None and s == "open":
        return "%s %s %%" % (t or "Ouvert", a.get("current_position"))
    if t is not None:
        return t
    tf = ts_format(st)
    if tf:
        t = ts_epoch(s)
        return cap(rel_fr(t, total=tf == "total"))
    if dom in ("input_datetime",) and "T" in str(s):
        return fmt_time(s)
    if s in STATE_FR:
        return STATE_FR[s]
    unit = a.get("unit_of_measurement")
    n = round_num(s, decimals) if decimals is not None else num(s)
    if n is not None:
        return n + (" " + unit if unit else "")
    return s + (" " + unit if unit else "")


def kelvin_rgb(k):
    """Couleur d'un blanc de k kelvins (même formule que le frontend de HA)."""
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
    """Toutes les entity_id citées dans une config (récursif)."""
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
    """Markdown très simple -> HTML sûr (titres, gras, italique, listes)."""
    text = re.sub(r"(?i)<br\s*/?>", "\n", str(text or ""))
    text = _TAG.sub("", text)
    out = []
    in_list = False
    for line in text.split("\n"):
        # Entités HTML écrites dans le markdown (&nbsp;, &#9728;…) : rendues comme dans HA.
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
    """Index d'une vue : numéro (0 = première) ou chemin de la vue."""
    ref = str(ref).strip()
    if ref.isdigit() and int(ref) < len(views):
        return int(ref)
    for i, v in enumerate(views):
        if str(v.get("path") or "") == ref:
            return i
    return None


def select_views(config, refs):
    """-> (vues choisies dans l'ordre demandé, vues à rendre).

    Les vues à rendre = vues choisies + celles qu'elles ouvrent (navigate).
    """
    views = config.get("views") or []
    if not views:
        return [], []
    chosen = []
    for r in refs or []:
        i = find_view(views, r)
        if i is None:
            log.warning("Vue introuvable : %s", r)
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
HIST_POINTS = 96          # points calculés par le serveur (sous-échantillonnés ensuite)
MAX_HOURS = 24 * 31       # limite des graphiques
HEX = re.compile(r"^#[0-9a-fA-F]{3,8}$")
SERIES_COLORS = ["#4269d0", "#f4bd4a", "#ff725c", "#6cc5b0"]
# Couleur par défaut d'une courbe selon ce qu'elle mesure (quand la carte n'en donne pas).
TYPE_COLORS = {"temperature": "#43a047", "humidity": "#4fc3f7", "energy": "#c2479a",
               "pressure": "#e53935", "solar": "#fdd835"}
_SOLAR = re.compile(r"solar|solaire|photovolt|\bpv\b|_pv_|_pv$|^pv_|panneau|onduleur|inverter|envoy|enphase", re.I)


MUSHROOM_COLORS = {"red", "pink", "purple", "deep-purple", "indigo", "blue", "light-blue",
                   "cyan", "teal", "green", "light-green", "lime", "yellow", "amber",
                   "orange", "deep-orange", "brown", "grey", "blue-grey", "black", "white",
                   "disabled", "primary", "accent"}
# Entités sans état allumé/éteint : la couleur d'une carte (option color) s'applique toujours.
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
    return s.replace(".", ",")


def spark_svg(series, h, labels=None, fill=True, pre="", gid="g"):
    """Courbe(s) SVG ; chaque série a sa propre échelle (comme « y_axis: independent »).
    Série = (valeurs, couleur[, seuils]) ; seuils = [(valeur, (r, g, b))] triés : la courbe
    prend un dégradé vertical (couleur selon la hauteur), comme color_thresholds.
    pre = dessin placé derrière les courbes (barres)."""
    W = 300.0
    parts = [pre] if pre else []
    for si, ser in enumerate(series):
        vals, color = ser[0], ser[1]
        stops = ser[2] if len(ser) > 2 else None
        sfill = ser[3] if len(ser) > 3 else None     # remplissage propre à la série (show_fill)
        pts = [v for v in vals if v is not None]
        if len(pts) < 2:
            continue
        lo, hi = min(pts), max(pts)
        rng = (hi - lo) or 1.0
        if stops:
            # offset 0 = bas de la courbe (lo), 1 = haut (hi)
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
    """Histogramme : n barres (moyennes), échelle min-max, barre mini visible."""
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
    """Couleur interpolée entre des seuils [(valeur, (r, g, b))] triés."""
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

# Domaines qui ont la fonctionnalité « toggle » des tuiles HA.
TOGGLE_FEATURE = ("light", "switch", "fan", "input_boolean", "siren", "humidifier",
                  "water_heater", "climate", "media_player", "automation", "remote")

def img_path(image, modern):
    """image (carte picture, fond de vue) -> chemin HA (/local/…, /api/image/serve/…) ou URL http(s).
    Image envoyée dans HA (media-source://image_upload/ID) : 512 px hors type 3, d'origine sinon."""
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
    """Construit les vues HTML d'une type d'appareil et enregistre slots + actions."""

    def __init__(self, store, dashboard_path, cls="t1"):
        self.store = store
        self.dash = dashboard_path
        self.cls = cls
        self.modern = cls == "t3"
        self.slots = []        # (deps, fn)
        self.actions = []      # dicts
        self.view_refs = {}    # path -> index
        self.icons = set()     # icônes utilisées (sprite)
        self.need_tpl = {}     # clé -> template Jinja (rendu par HA)
        self.need_fc = set()   # (entité météo, type de prévision)
        self.need_hist = {}    # clé -> (entité, heures)
        self.cams = set()      # caméras autorisées pour ce rendu
        self.imgs = {}         # clé -> image de carte picture (chemin HA, URL ou entité)
        self.pending_side = ""  # pastilles à poser à droite de la prochaine tuile
        self.in_sic = 0         # > 0 pendant le rendu d'un stack-in-card
        self.in_stack = 0       # > 0 dans une pile ou une grille (hauteurs libres)

    # ---- slots / actions -------------------------------------------------
    def slot(self, deps, fn):
        self.slots.append((tuple(deps), fn))
        return "s%d" % (len(self.slots) - 1)

    def st(self, eid):
        return self.store.states.get(eid)

    def kind_color(self, eid):
        """Couleur par défaut selon le type de mesure, ou None (garder la palette)."""
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
        """Couleur d'une courbe : celle de la carte, sinon celle du type, sinon la palette."""
        if color and HEX.match(str(color)):
            return color
        return self.kind_color(eid) or fallback or SERIES_COLORS[i % len(SERIES_COLORS)]

    def prec(self, eid):
        """Précision d'affichage réglée dans HA (registre des entités)."""
        return (self.store.reg.get(eid) or {}).get("dp")

    def nm(self, eid, cfg_name=None):
        """Nom à afficher : texte, ou objet/liste {type: device|entity|area|text}."""
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
                if tf:      # horodatage : « 1 mois », « Il y a 3 heures »… comme HA
                    return (ts_html(st, tf), None)
                return (E(fmt_state(st, e, self.prec(e))), None)
        sid = self.slot([eid], fn)
        val = fn()[0]
        c = ' class="%s"' % cls if cls else ""
        return '<%s id="%s"%s>%s</%s>' % (tag, sid, c, val, tag)

    def value_fn(self, eid, decimals=None):
        """État d'une entité, l'unité à part (affichée plus petite)."""
        def fn(x=eid, d=decimals):
            st = self.st(x)
            txt = fmt_state(st, x, self.prec(x) if d is None else d)
            unit = ((st or {}).get("a") or {}).get("unit_of_measurement")
            if unit and txt.endswith(" " + unit):
                return ('%s<span class="u">%s</span>' % (E(txt[:-len(unit) - 1]), E(unit)), None)
            return (E(txt), None)
        return fn

    def tpl_slot(self, template, tag="span", cls="", markdown=False):
        """Texte calculé par un template Jinja de Home Assistant (ou texte fixe)."""
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
        """Couleur réelle d'une lampe allumée (rgb_color) : « #icône|#fond de pastille » ;
        "" sans information (le jaune du thème s'applique)."""
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
        """Ouvre un conteneur dont la classe suit l'état (on/off/na) ; pour une lampe,
        l'icône prend aussi sa couleur réelle (3e valeur du slot, appliquée par s.js)."""
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
        """tap_action Lovelace -> action SlimDash (ou None)."""
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

    # ---- icônes, couleurs, graphiques, caméras ---------------------------
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
        """Groupe de couleur. Pour un interrupteur, l'icône choisie décide
        (ampoule -> jaune comme une lampe, ventilateur -> cyan, etc.)."""
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
        """entities = [(entity_id, couleur ou None[, seuils])] -> HTML d'un graphique (slot).
        bars = nombre de barres (histogramme seul) ; 0 = courbe.
        barmap = {rang de l'entité: nombre de barres} : barres derrière les autres courbes."""
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
        # Type 1 : la courbe n'est redessinée que toutes les 30 min (la valeur, elle, est en direct).
        dep = "hist30:" if light else "hist:"
        sid = self.slot([dep + k[0] for k in keys], fn)
        return '<div id="%s" class="%s">%s</div>' % (sid, cls, fn()[0])

    def camera(self, eid, title="", overlay=""):
        # Image de 360 px de haut. data-iv : intervalle visé en ms. Frigate : au rythme de sa
        # détection (5 i/s en général) ; l'appareil ralentit de lui-même s'il ne suit pas (s.js).
        # HA : 1 image/s. Vidéo en direct pour les caméras Frigate si le navigateur sait.
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
            except Exception:  # une vue cassée ne doit pas tout bloquer
                log.exception("Erreur de rendu de la vue %s", i)
                body = '<div class="card"><p>Erreur de rendu de cette vue.</p></div>'
            result.append({"index": i, "path": str(v.get("path") or i),
                           "title": v.get("title") or v.get("path") or "Vue %d" % (i + 1),
                           "subview": bool(v.get("subview")), "body": body})
        return result

    def view(self, v):
        out = []
        if v.get("strategy"):
            return '<div class="card"><p>Vue générée automatiquement (strategy) : non prise en charge.</p></div>'
        badges = v.get("badges") or []
        if badges:
            out.append(self.badges(badges))
        if v.get("type") == "sections":
            # c0 / c1 : colonne gauche / droite quand l'écran en permet deux (paysage)
            # Une section sur plusieurs colonnes (column_span) occupe toute la largeur
            # disponible : classe spN, hors de l'alternance gauche / droite.
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
            show_name = b.get("show_name") is True     # HA : nom masqué par défaut
            out.append(self.badge(eid, self.nm(eid, b.get("name")) if show_name else None,
                                  b.get("icon")))
        out.append("</div>")
        return "".join(out)

    # ---- cartes ----------------------------------------------------------
    @staticmethod
    def grid_cr(c):
        """(colonnes, rangées) données explicitement dans grid_options, sinon None."""
        go = c.get("grid_options") if isinstance(c, dict) and isinstance(c.get("grid_options"), dict) else {}
        try:
            return int(go.get("columns")), int(go.get("rows"))
        except (TypeError, ValueError):
            return None, None

    def sect_cards(self, cards):
        """Cartes d'une section. Comme la grille de HA (placement « dense ») : après une carte
        d'une demi-largeur et de N rangées, les demi-cartes suivantes dont les rangées tiennent
        dans ces N s'empilent dans la colonne d'à côté au lieu de passer à la ligne."""
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
            log.exception("Erreur de rendu de la carte %s", t)
            return self.c_fallback(c)

    def title(self, c, key="title"):
        t = c.get(key)
        return '<h2 class="ch">%s</h2>' % E(str(t)) if isinstance(t, str) and t else ""

    def size(self, c, cols, rows):
        """Taille de la carte comme dans les vues « sections » de HA :
        colonnes sur 12 (3 = quart, 6 = moitié, 12 = pleine largeur), lignes de 56 px."""
        go = c.get("grid_options") if isinstance(c.get("grid_options"), dict) else {}
        lo = c.get("layout_options") if isinstance(c.get("layout_options"), dict) else {}
        col, row = go.get("columns"), go.get("rows")
        if col is None and lo.get("grid_columns") is not None:     # ancien format, sur 4
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
            row = None          # « auto »
        return col, row

    def height(self, rows):
        """Hauteur exacte de la carte : N unités de 56 px séparées de 8 px (comme HA).
        Dans un stack-in-card, simple hauteur minimale (rendu inchangé de ces cartes)."""
        if not rows:
            return ""
        px = rows * 56 + (rows - 1) * 8
        if self.in_sic:
            return "min-height:%dpx" % px
        return "height:%dpx;overflow:hidden" % px

    def tile_html(self, eid, name_html, state_html, action, cfg_icon=None, extra="",
                  cols=6, rows=None, vertical=False, optimistic=True, base_extra="", side="",
                  icon_color=None, card=None, color=None, style_extra=""):
        """color = option color d'une tuile ou d'un bouton : l'icône la prend quand l'entité
        est active (toujours pour un bouton, une scène, un script)."""
        base = "card tile w%d%s%s" % (cols, " vt" if vertical else "", base_extra)
        if color and not icon_color and mc_class(color) and (
                not eid or domain_of(eid) in STATELESS):
            icon_color, color = color, None
        if self.pending_side:
            side, self.pending_side = side + self.pending_side, ""
        cs = self.card_style(card) if card else {}
        if " bc" in base_extra:
            cs.pop("h", None)       # bouton compact : une unité de hauteur (56 px)
        style = ";".join(x for x in (
            ("min-height:%dpx" % cs["h"]) if cs.get("h") else self.height(rows),
            ("background:%s" % cs["bg"]) if cs.get("bg") else "", style_extra) if x)
        base += " rt " + (("dc-none" if icon_color else self.dc(eid, cfg_icon)) if eid else "dc-def")
        ic = self.ent_icon(eid, cfg_icon) if (eid or cfg_icon) else ""
        return (self.box_open(base, eid, action, optimistic=optimistic and bool(action), style=style)
                + (self.icon_box(ic, icon_color, eid if mc_class(color) else None, color)
                   if ic else "") + side
                + '<span class="tx%s"><span class="tn">%s</span>%s</span>%s</div>' % (
                    "" if state_html else " one",  # nom seul : centré en hauteur (s.css)
                    name_html, ('<span class="ts">%s</span>' % state_html) if state_html else "",
                    extra))

    def icon_box(self, ic, icon_color, eid=None, color=None):
        """Pastille d'icône ; icon_color = couleur mushroom fixe ou template Jinja ;
        color (avec eid) = couleur appliquée seulement quand l'entité est allumée."""
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
        """Fond et hauteur imposés par card_mod / uix / styles de button-card (rien d'autre)."""
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
        # Interrupteur d'en-tête, comme HA : titre présent, show_header_toggle pas à false,
        # au moins 2 entités basculables ; allumé si l'une l'est, tout éteint / tout allumé.
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
                self.action_attrs(act), E(str(r.get("action_name") or "Exécuter")))
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
        """Valeur modifiable d'une ligne (nombre, liste, heure, date, texte), comme HA.
        Le champ envoie sa valeur au changement (data-e = action) ; s.js ne le remplace pas
        pendant qu'on le modifie."""
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
        # input_datetime : date et/ou heure (« 2026-11-13 07:30:00 », « 07:30:00 », « 2026-11-13 »)
        out = []
        if a.get("has_date"):
            out.append(date_in(val[:10] if "-" in val[:10] else "", acts["date"]))
        if a.get("has_time"):
            out.append(time_in(val[-8:] if ":" in val else "", acts["time"]))
        return " ".join(out) or E(fmt_state(st, eid))

    # ---- lampes : couleurs favorites, curseurs luminosité / température ----
    def pal(self):
        return getattr(self.store, "palette", None) or theme.palette(None)

    def light_slider(self, eid, what):
        """Curseur comme ha-control-slider : barre (luminosité) ou repère sur un dégradé
        de blancs (température). Glissé au doigt par s.js, envoyé au relâcher."""
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
        """Fonctionnalité « toggle » comme ha-control-switch : fond gris, curseur d'une
        demi-largeur à gauche (éteint, gris) ou à droite (allumé, couleur de l'entité)."""
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
        """Couleurs favorites de la lampe (réglées dans HA), sinon celles que HA propose
        par défaut : 4 blancs du plus chaud au plus froid, puis 4 couleurs."""
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
        # Pourcentages seulement (calc() est ignoré par certains navigateurs Android 4.4) :
        # écart de 1,43 % = 8 px sur une carte de 560 px, comme l'original.
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
        # Case arc-en-ciel : ouvre la barre de teintes (toutes les cases sauf la dernière) ;
        # la dernière case prend la teinte glissée (la lampe suit en direct) et valide.
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
            return (E(num(v) + " °C") if v is not None and num(v) else "—", None)
        minus = self.action_attrs({"kind": "temp", "entity": eid, "step": -0.5})
        plus = self.action_attrs({"kind": "temp", "entity": eid, "step": 0.5})
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
            elif f.get("type") in ("cover-open-close", "cover-position") and domain_of(eid) == "cover":
                extra += '<div class="cvb">%s</div>' % self.cover_buttons(eid)
                nfeat += 1
        vertical = bool(c.get("vertical")) or c.get("layout") == "vertical"
        mini = (2 if vertical else 1) + nfeat
        cols, rows = self.size(c, 12 if side else 6, mini)
        if rows is not None and rows < mini:
            rows = mini         # HA agrandit la carte pour loger toutes les fonctionnalités
        if (vertical and self.in_stack and str(c.get("type", "")).startswith("custom:mushroom")
                and not c.get("grid_options") and not c.get("layout_options")):
            rows = None         # mushroom vertical dans une pile : hauteur naturelle, comme HA
        pad, tfx = "", ""
        if extra and rows and not vertical and not self.in_sic:
            # Placement de HA : fonctionnalités de 42 px espacées de 12 px, la dernière à
            # 12 px du bas ; l'en-tête (36 px) centré dans la place restante au-dessus.
            h = rows * 56 + (rows - 1) * 8
            top = h - nfeat * 54
            pt = max(6, top // 2 - 18)
            pad = "padding-top:%dpx" % pt
            extra = '<div class="fsp" style="height:%dpx"></div>' % max(0, top - pt - 36 - 12) + extra
            tfx = " tfx"
        return self.tile_html(eid, E(self.nm(eid, c.get("name"))), self.text_slot(eid), act,
                              cfg_icon=c.get("icon"), extra=extra, cols=cols, rows=rows, side=side,
                              vertical=vertical, color=c.get("color"), style_extra=pad,
                              base_extra=(" tf" if extra else "") + tfx + (" tfi" if side else ""))

    def c_light(self, c):
        """Carte « light » de HA : cadran de luminosité sur 270° (ha-control-circular-slider,
        trait 24/320), grosse ampoule au centre (allume / éteint), luminosité et nom dessous."""
        eid = c.get("entity")
        if not eid:
            return ""
        arc = "M 145 0 A 145 145 0 1 1 0 -145"          # 270°, tourné de 135° (bas gauche)
        full = 683.3

        def col(e):
            st = self.st(e) or {}
            p = self.pal()
            if st.get("s") != "on":
                return None
            c1 = self.light_color(e).split("|")[0] or p["groups"].get("light", ("#ffc107",))[0]
            if p.get("dark", True):
                return c1
            # thème clair : une lampe blanche resterait invisible sur la carte blanche ;
            # couleur presque blanche -> couleur « lampe allumée » du thème
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
            # éteinte : gris mesuré sur HA (sombre) ; en clair, gris inactif du thème (lisible sur blanc)
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
                ic = self.icon(icons.from_mdi("mdi:lightbulb-off"))   # icône d'état HA : ampoule barrée
            else:
                ic = self.ent_icon(e, c.get("icon"))
            return ('<span class="lgi" style="color:%s">%s</span>' % (
                c1 or self.pal()["icon"], ic), None)

        def info(e=eid):
            v = pct(e)
            return ("&nbsp;" if v is None else "%d %%" % v, None)

        slider = self.action_attrs({"kind": "light", "entity": eid, "what": "b"}).replace("data-a", "data-s")
        if domain_of(eid) == "light":   # les deux icônes dans la page : l'état change en direct
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
            # la courbe occupe le bas de la carte, sous la valeur (71 px)
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
                # Comme HA : la couleur du plus haut seuil atteint, quel que soit l'ordre.
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
            # Dans une pile, comme HA : hauteur naturelle, l'arc suit la largeur de la carte
            # et la valeur est dans l'arc (texte SVG, qui grandit avec lui).
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
        # Jauge en demi-cercle (arc SVG, longueur π·40 ≈ 125,7), valeur dans l'arc comme HA :
        # l'arc suit la largeur de la carte (taille maxi fixée en CSS) et le texte avec lui.
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
        """Jauge d'autosuffisance (carte énergie native) : valeur calculée par le serveur."""
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
        if grows is None:       # « auto » : même hauteur que la jauge classique
            grows = 3 if gcols == 12 else 2
        gbase = "card w%d gauge gfx%s" % (gcols, " g3" if grows >= 3 else "")
        sid = self.slot(["hist:e:ss"], arc)
        return (self.box_open(gbase, None, None, style=self.height(grows))
                + '<div class="gw"><div class="gp"><div id="%s" class="gin">%s</div></div></div>' % (sid, arc()[0])
                + '<div class="tn">%s</div></div>' % E(str(c.get("title") or "Taux d'autosuffisance")))

    def c_markdown(self, c):
        # text_only : texte seul, sans fond, bordure ni ombre (comme HA)
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
        """Comme HA : icône, état et lieu à gauche, température et max / min à droite ;
        prévisions en colonnes (jour, icône, max, min)."""
        eid = c.get("entity")
        if not eid:
            return ""
        show_cur = c.get("show_current", True) is not False
        fcst = c.get("show_forecast", True) is not False
        ftype = c.get("forecast_type") or "daily"
        key = "fc:%s:%s" % (eid, ftype)
        if fcst:
            self.need_fc.add((eid, ftype))
        self.icons.update(set(icons.WEATHER.values()))    # la météo change : toutes ses icônes
        drop = self.icon("drop")
        place = E(str(self.nm(eid, c.get("name"))))

        def cur(e=eid, k=key):
            st = self.st(e)
            if not st:
                return ("—", None)
            a = st.get("a") or {}
            s = st.get("s")
            t = a.get("temperature")
            unit = a.get("temperature_unit", "°C")
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

        # Comme HA : 4U avec prévisions, 2U pour la météo actuelle seule.
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
                        lab = DAYS_FR[d.weekday()] if ft != "hourly" else d.strftime("%H:%M")
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

    def c_thermostat(self, c):
        eid = c.get("entity")
        if not eid:
            return ""
        return ('<div class="card"><div class="row">%s<span class="nm">%s<br>%s</span>'
                '<span class="rt">%s</span></div></div>' % (
                    self.row_icon(eid), E(self.nm(eid, c.get("name"))),
                    self.text_slot(eid, cls="sub"), self.climate_ctrl(eid)))

    def graph_rows(self, c, entities, hours, title):
        """Comme HA : titre, graphique, puis légende (pastille de couleur, nom, valeur)."""
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
            if rows:   # hauteur de la carte - titre - légende
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
        """Carte « statistics-graph-chart-card » : en-tête, valeur(s), courbes ou barres."""
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
        if rows and not gh:     # hauteur de la carte - marges, titre, valeurs
            gh = rows * 56 + (rows - 1) * 8 - 24 - (30 if has_title else 0) - 62
        hc = c.get("card_header_color")
        # Dans un stack-in-card, les marges négatives de « styles » (ha-card margin-top,
        # .sgc-plot-wrap margin) font remonter le graphique sous la carte du dessus, comme HA.
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
                if unit and txt.endswith(" " + unit):     # valeur grande, unité plus petite
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
        """color_thresholds actifs d'une entité -> [(valeur, (r, g, b))] triés, ou None."""
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
        """Valeur + unité ; colorée si « state_adaptive_color » (couleur fixe ou seuils)."""
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
        """Couleur choisie dans une carte, lisible sur le fond du thème (thème clair)."""
        return theme.readable(color, self.pal().get("card") or "#1c1c1c")

    def stat_multi(self, c, ents, title, hc, hours, gh, cols, rows):
        """Plusieurs entités. Noms affichés : liste « nom valeur ». Noms masqués : valeurs
        placées à gauche / au centre / à droite (align_state), chacune à sa taille."""
        # Noms sous les valeurs (name_position: below) : présentation en grandes valeurs,
        # comme la carte d'origine ; sinon liste « pastille nom valeur ».
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
            if e.get("show_graph") is False:        # valeur seule, pas de courbe (comme HA)
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
            # décalages demandés par les « styles » de la carte (marges des classes d'alignement)
            shift, push_right = {}, False
            for m in re.finditer(r"\.sgc-state-align-(left|center|right)\s*\{([^}]*)\}", str(c.get("styles") or "")):
                dx = dy = 0.0
                mm = re.search(r"margin\s*:\s*(-?[\d.]+)px\s+(-?[\d.]+)(?:px)?\s+(-?[\d.]+)(?:px)?\s+(-?[\d.]+)(?:px)?", m.group(2))
                if mm:
                    top, right, _, left = [float(x) for x in mm.groups()]
                    dy = top
                    dx = {"left": left, "right": -right, "center": (left - right) / 2}[m.group(1)]
                    if m.group(1) == "center" and right < 0 and right < left:
                        # centre poussé vers la droite (marge droite négative) : calé à droite
                        push_right, dx = True, 0.0
                mt = re.search(r"margin-top\s*:\s*(-?[\d.]+)px", m.group(2))
                if mt:
                    dy = float(mt.group(1))
                shift[m.group(1)] = (dx, dy)
            # Comme la carte d'origine : interligne 1,6 x la taille, 5 px au-dessus et
            # au-dessous de chaque valeur, zones calées en haut sous le titre ; la hauteur
            # de la bande tient compte des décalages verticaux des styles.
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
        """Une seule carte (un seul fond) contenant les cartes empilées, comme stack-in-card."""
        cards = [x for x in c.get("cards") or [] if isinstance(x, dict)]
        parts, skip = [], set()
        self.in_sic += 1
        for i, x in enumerate(cards):
            if i in skip:
                continue
            nxt = cards[i + 1] if i + 1 < len(cards) else {}
            # Pastilles alignées à droite juste après une tuile : sur la ligne de la tuile
            # (remplace le décalage par marges négatives des card_mod).
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
        # Largeur dans la section (grid_options) : demi-carte, tiers… comme les autres cartes.
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

    # ---- caméras ---------------------------------------------------------
    def overlay(self, ents):
        parts = []
        for e in ents or []:
            if isinstance(e, str):
                e = {"entity": e}
            eid = e.get("entity") if isinstance(e, dict) else None
            if eid:     # icône seule, colorée selon l'état (comme picture-glance)
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

    # ---- carte picture (image fixe) ---------------------------------------
    def img_source(self, image):
        """image d'une carte picture -> chemin HA (/local/…, /api/image/serve/…) ou URL http(s).
        Image envoyée dans HA (media-source://image_upload/ID) : 512 px pour les types 1 et 2
        (vieux appareils), taille d'origine en type 3."""
        return img_path(image, self.modern)

    def img_key(self, spec):
        key = hashlib.md5(repr(spec).encode("utf-8")).hexdigest()[:10]
        self.imgs[key] = spec
        return key

    def c_picture(self, c):
        """Carte picture : l'image sur toute la largeur de la carte, sans marge (comme HA).
        Avec une hauteur imposée (rows), l'image couvre la carte (fond, compris d'Android 4)."""
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

    # ---- cartes personnalisées traduites ---------------------------------
    def c_custom_button_card(self, c):
        eid = c.get("entity")
        name = c.get("name") if isinstance(c.get("name"), str) and "[[[" not in c.get("name") else None
        if not eid and not name:
            return ""  # espaceur ou carte 100 % JavaScript
        act = self.resolve_action(c.get("tap_action"), eid,
                                  self.default_tap(eid) if eid else "none")
        nm = E(self.nm(eid, name) if eid else name) if c.get("show_name", True) else ""
        state = self.text_slot(eid) if eid and c.get("show_state", False) else ""
        icon = c.get("icon") if isinstance(c.get("icon"), str) and "[[[" not in c.get("icon") else None
        layout = str(c.get("layout") or "vertical")
        h = self.card_style(c).get("h")
        if h and h <= 80:
            # Hauteur imposée faible (ex. 60 px) : bouton compact sur une unité,
            # icône à gauche du nom, le tout centré.
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
            rows = None         # dans une pile : hauteur naturelle, comme HA
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
                        txt.append("%s %s" % (num(a["temperature"]), a.get("temperature_unit", "°C")))
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
                # Valeurs : show_state (ancien format) ou state_content (nouveau : « state »,
                # « last_updated », « last_changed », nom d'attribut ; texte ou liste).
                sc = s.get("state_content")
                sc = [sc] if isinstance(sc, str) else [x for x in (sc or []) if isinstance(x, str)]
                if s.get("show_state") and "state" not in sc:
                    sc.insert(0, "state")
                if s.get("show_last_changed") or s.get("show_last_updated"):
                    sc.append("last_changed")
                vals = []
                for k in sc[:3]:
                    if k == "state":
                        def fn(e=se):  # Bubble met une majuscule à l'état
                            return (E(cap(fmt_state(self.st(e), e, self.prec(e)))), None)
                        vals.append(self.text_slot(se, fn))
                    elif k in ("last_updated", "last_changed", "last-updated", "last-changed"):
                        def fn(e=se):  # « Il y a 44 minutes », comme Bubble
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
        # Valeurs à droite, sur la même ligne que le nom (comme bubble-card).
        side = '<span class="subs">%s</span>' % "".join(chips) if chips else ""
        # Bubble n'affiche l'état sous le nom que si show_state est activé.
        state = self.text_slot(eid) if c.get("show_state") else ""
        cols, rows = self.size(c, 12 if chips else 6, 1)
        return self.tile_html(eid, E(self.nm(eid, c.get("name"))), state, act,
                              cfg_icon=c.get("icon"), side=side, cols=cols, rows=rows,
                              base_extra=" tb" if chips else "")

    # Carte personnalisée "custom:digital-clock" : horloge locale (JS).
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
        """Carte inconnue/personnalisée : liste lisible des entités trouvées."""
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
