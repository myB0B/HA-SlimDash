"""SlimDash - dashboards Home Assistant en HTML léger pour vieux navigateurs.

Une seule connexion WebSocket vers Home Assistant (abonnée aux seules entités
des vues publiées), rendu HTML côté serveur mis en cache, et mises à jour
envoyées aux navigateurs par "long polling" (XMLHttpRequest, Android 4).

Chaque dashboard publié a un nom, qui sert d'URL : http://IP:8099/<nom>
"""
import asyncio
import hashlib
import io
import ipaddress
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone

from urllib.parse import quote

from aiohttp import ClientSession, WSMsgType, web

import eink
import icons
import render
import theme

VERSION = "0.8.69"
HERE = os.path.dirname(os.path.abspath(__file__))
log = logging.getLogger("slimdash")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
RESERVED = {"static", "debug", "diag", "u", "a", "cam", "live"}
LONGPOLL = 25  # durée max (s) d'une requête de mise à jour en attente


def _static_tag():
    """Empreinte des fichiers statiques : le navigateur recharge CSS/JS dès qu'ils changent."""
    import hashlib
    h = hashlib.md5()
    folder = os.path.join(HERE, "static")
    for n in sorted(os.listdir(folder)):
        with open(os.path.join(folder, n), "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()[:8]


STATIC_TAG = _static_tag()


# --------------------------------------------------------------------------
# Types d'appareils t1 / t2 / t3 (d'après l'en-tête User-Agent, lu à la 1re requête)
# --------------------------------------------------------------------------
def strip_prefix(name, prefix):
    """Comme HA : « Portail Voiture » sur l'appareil « Portail » -> « Voiture »."""
    if not name or not prefix:
        return name
    low = name.lower()
    for sep in (" ", ": ", " - "):
        p = prefix.lower() + sep
        if low.startswith(p) and len(name) > len(p):
            rest = name[len(p):]
            return rest[0].upper() + rest[1:]
    return name


TYPE_IDS = ("t1", "t2", "t3")
TYPE_LABEL = {"t1": "Type 1", "t2": "Type 2", "t3": "Type 3"}
# Essai d'un type depuis l'adresse : &type=1, 2 ou 3.
TYPES = {"1": "t1", "2": "t2", "3": "t3"}


def classify(ua):
    """-> (moteur, version, type). Inconnu = t1 (le plus sûr)."""
    ua = ua or ""

    def level(v, mid, top):
        return "t1" if v < mid else ("t2" if v < top else "t3")

    m = re.search(r"(?:Chrome|CriOS)/(\d+)", ua)
    if m:
        v = int(m.group(1))
        return "Chromium", v, level(v, 50, 80)
    m = re.search(r"Firefox/(\d+)", ua)
    if m:
        v = int(m.group(1))
        return "Firefox", v, level(v, 52, 75)
    m = re.search(r"(?:iPhone|iPad|iPod).* OS (\d+)_", ua)
    if m:
        v = int(m.group(1))
        return "Safari iOS", v, level(v, 10, 13)
    m = re.search(r"Version/(\d+)[.\d]* .*Safari/", ua)
    if m:
        v = int(m.group(1))
        return "Safari", v, level(v, 10, 13)
    m = re.search(r"AppleWebKit/(\d+)", ua)
    if m:
        return "WebKit", int(m.group(1)), "t1"
    return "inconnu", 0, "t1"


def device_type(dash, req):
    if req.query.get("type") in TYPES:          # essai : ?type=1|2|3
        return TYPES[req.query["type"]]
    if dash is not None and dash.spec["device"] in TYPE_IDS:
        return dash.spec["device"]
    return classify(req.headers.get("User-Agent"))[2]


# --------------------------------------------------------------------------
# Options
# --------------------------------------------------------------------------
def parse_path(path):
    """« lovelace/kindle » -> (url_path HA ou None, vue ou None)."""
    p = str(path or "").strip()
    p = re.sub(r"^[a-z]+://[^/]+", "", p)        # URL complète collée
    p = p.split("?")[0].split("#")[0].strip("/")
    parts = [x for x in p.split("/") if x]
    if not parts:
        return None, None
    dash = parts[0]
    view = parts[1] if len(parts) > 1 else None
    return (None if dash == "lovelace" else dash), view


def load_options():
    opts = {
        "dashboards": [],
        "allowed_networks": ["192.168.0.0/16", "10.0.0.0/8"],
        "access_key": "",
        "frigate_url": "",
        "log_level": "info",
        "theme": "",
        "port": 8099,
    }
    path = os.environ.get("SLIMDASH_OPTIONS", "/data/options.json")
    try:
        with open(path, encoding="utf-8-sig") as f:
            opts.update({k: v for k, v in json.load(f).items() if v is not None})
    except FileNotFoundError:
        pass
    if not opts["dashboards"]:
        opts["dashboards"] = [{"name": "kindle", "dashboard": "lovelace", "views": "kindle"}]
    dashes, seen = [], set()
    for d in opts["dashboards"]:
        name = str(d.get("name") or "").strip().lower()
        if not NAME_RE.match(name) or name in RESERVED or name in seen:
            log.warning("Nom de dashboard invalide ou en double ignoré : %r", d.get("name"))
            continue
        seen.add(name)
        # « dashboard » (0.3) ; « path » = ancien format dashboard/vue (0.2).
        url_path, view_in_url = parse_path(d.get("dashboard") or d.get("path"))
        views = [x.strip() for x in str(d.get("views") or "").split(",") if x.strip()]
        if not views and view_in_url:
            views = [view_in_url]
        # Rafraîchissement : 0 = temps réel ; sinon toutes les N s (5 à 3600).
        try:
            refresh = int(d.get("refresh") or 0)
        except (TypeError, ValueError):
            refresh = 0
        if refresh > 0:
            refresh = max(5, min(3600, refresh))
        # « type 1|2|3 » (anciennes valeurs ancien|intermediaire|moderne encore acceptées)
        device = {"ancien": "1", "intermediaire": "2", "moderne": "3"}.get(
            str(d.get("device") or "auto").strip().lower(), str(d.get("device") or "auto"))
        device = device.strip().lower()
        device = TYPES.get(device.replace("type", "").strip(), device)
        if device not in ("auto",) + TYPE_IDS:
            device = "auto"
        # Thème propre au dashboard ; à défaut l'ancienne option globale (avant 0.8.20).
        # Thème : celui de chaque vue (HA), ou le thème par défaut de HA en clair / en sombre.
        # (valeurs anglaises depuis 0.8.49 ; les françaises ha clair|ha sombre|vue restent acceptées)
        th = {"ha light": "light", "ha dark": "dark", "ha clair": "light", "ha sombre": "dark"}.get(
            str(d.get("theme") or "").strip().lower(), "view")
        dashes.append({"name": name, "url_path": url_path, "views": views, "theme": th,
                       "refresh": max(0, refresh), "device": device,
                       "tabs_bottom": bool(d.get("tabs_bottom")),
                       "label": "%s / %s" % (url_path or "lovelace",
                                             ",".join(views) or "1re vue")})
    opts["_dashes"] = dashes
    if os.environ.get("SUPERVISOR_TOKEN"):
        opts["ws_url"] = "ws://supervisor/core/websocket"
        opts["api_url"] = "http://supervisor/core/api"
        opts["token"] = os.environ["SUPERVISOR_TOKEN"]
    else:  # exécution hors Home Assistant (développement)
        base = os.environ.get("HA_URL", opts.get("ha_url", "http://homeassistant.local:8123"))
        opts["ws_url"] = base.rstrip("/").replace("http", "ws", 1) + "/api/websocket"
        opts["api_url"] = base.rstrip("/") + "/api"
        opts["token"] = os.environ.get("HA_TOKEN", opts.get("ha_token", ""))
    if os.environ.get("SLIMDASH_PORT"):
        opts["port"] = int(os.environ["SLIMDASH_PORT"])
    nets = []
    for n in opts.get("allowed_networks") or []:
        try:
            nets.append(ipaddress.ip_network(str(n).strip(), strict=False))
        except ValueError:
            log.warning("Réseau autorisé invalide ignoré : %s", n)
    opts["_nets"] = nets
    return opts


# --------------------------------------------------------------------------
# État partagé (Hub) et état de chaque dashboard publié (Dash)
# --------------------------------------------------------------------------
class Hub:
    def __init__(self, opts):
        self.opts = opts
        self.states = {}
        self.reg = {}
        self.tpl = {}       # clé de template -> texte rendu par HA
        self.fc = {}        # "fc:entité:type" -> prévisions météo
        self.hist = {}      # "h:entité:heures" -> valeurs (graphiques)
        self.palette = theme.palette(None)     # couleurs du thème par défaut de HA
        self.themes = {}                        # nom de thème -> variables (HA)
        self.default_theme = ""                 # thème par défaut de HA
        self.palettes = {}                      # (thème, clair/sombre) -> couleurs
        self.theme_names = []                   # thèmes déclarés dans HA
        self.frigate = ""                       # URL de Frigate joignable ("" : caméras via HA)
        self.frigate_fps = {}                   # caméra Frigate -> images/s de sa détection
        self.look = ""                          # signature thème + libellés
        self.connected = False
        self.version = 1
        self.boot = "%x" % int(time.time())
        self.need_event = None
        self.dashes = {d["name"]: Dash(self, d) for d in opts["_dashes"]}

    def bump(self):
        self.version += 1
        return self.version

    def palette_for(self, dash, view=None):
        """Couleurs d'une vue : thème HA clair / sombre imposé, sinon thème de la vue
        (à défaut celui par défaut de HA ; mode sombre pour un thème à deux modes)."""
        how = dash.spec.get("theme") if dash else "view"
        if how in ("light", "dark"):
            key = ("", how)
        else:
            name = (view or {}).get("theme") or ""
            key = (name if name in self.themes else self.default_theme, "dark")
        if key not in self.palettes:
            tv = self.themes.get(key[0]) if key[0] else None
            self.palettes[key] = theme.palette(tv if isinstance(tv, dict) else None, key[1])
        return self.palettes[key]

    def theme_style(self, cls, dash=None, view=None):
        p = self.palette_for(dash, view)
        out = theme.css(p, cls)
        bg = (view or {}).get("bg")
        if bg and dash and cls == "t3":      # image de fond de la vue : type 3 seulement
            out += theme.bg_css(p, quote(dash.name), bg)
        return "<style>%s</style>" % out

    def changed(self, keys):
        for d in self.dashes.values():
            d.changed(keys)

    def set_connected(self, c):
        if self.connected != c:
            self.connected = c
            for d in self.dashes.values():
                d.notify()

    def wake(self):
        if self.need_event is not None:
            self.need_event.set()

    def needs(self):
        """Ce que les rendus déjà construits demandent à HA."""
        tpl, fc, hist = {}, set(), {}
        for d in self.dashes.values():
            for v in d.variants.values():
                tpl.update(v.need_tpl)
                fc |= v.need_fc
                hist.update(v.need_hist)
        return tpl, fc, hist


class Variant:
    """Rendu d'un dashboard pour une type d'appareil (construit à la demande)."""

    def __init__(self, dash, cls):
        b = render.Builder(dash, dash.spec["url_path"], cls)
        views = b.build(dash.config or {}, dash.indices)
        self.cls = cls
        self.body = {v["index"]: v["body"] for v in views}
        for v in dash.views:      # icônes des onglets
            if v.get("ic"):
                b.icons.add(v["ic"])
        self.sprite = b.sprite()
        self.slots = b.slots
        self.actions = b.actions
        self.need_tpl, self.need_fc = b.need_tpl, b.need_fc
        self.need_hist, self.cams = b.need_hist, b.cams
        self.imgs = b.imgs
        ver = dash.hub.bump()
        self.slot_val = [fn() for _, fn in self.slots]
        self.slot_ver = [ver] * len(self.slots)
        self.build_version = ver
        self.deps = {}
        for i, (deps, _) in enumerate(self.slots):
            for d in deps:
                self.deps.setdefault(d, []).append(i)
        self.pages = {}
        self.waiters = set()
        self.hub = dash.hub

    def notify(self):
        for f in self.waiters:
            if not f.done():
                f.set_result(None)
        self.waiters.clear()

    def changed(self, keys):
        todo = set()
        for k in keys:
            todo.update(self.deps.get(k, ()))
        newver = None
        for i in todo:
            try:
                v = self.slots[i][1]()
            except Exception:
                log.exception("Erreur de calcul d'un élément")
                continue
            if v != self.slot_val[i]:
                if newver is None:
                    newver = self.hub.bump()
                self.slot_val[i] = v
                self.slot_ver[i] = newver
        if newver is not None:
            self.notify()

    def changes_since(self, v):
        return {"s%d" % i: list(self.slot_val[i])
                for i, ver in enumerate(self.slot_ver) if ver > v}


class Dash:
    def __init__(self, hub, spec):
        self.hub = hub
        self.spec = spec
        self.name = spec["name"]
        self.config = None
        self.config_json = None
        self.indices = None
        self.tab_indices = []
        self.error = None
        self.build_no = 0
        self.views = []         # titres/chemins des vues rendues (sans le HTML)
        self.bgs = {}           # clé -> image de fond d'une vue (relayée par /<nom>/img)
        self.variants = {}      # type d'appareil -> Variant
        self.wanted = set()     # types déjà demandés par un appareil

    # Interface attendue par render.Builder (données partagées par tous les dashboards)
    @property
    def states(self):
        return self.hub.states

    @property
    def reg(self):
        return self.hub.reg

    @property
    def tpl(self):
        return self.hub.tpl

    @property
    def fc(self):
        return self.hub.fc

    @property
    def hist(self):
        return self.hub.hist

    @property
    def palette(self):
        v = self.views[0] if self.views else None   # graphiques, lampes : 1re vue
        return self.hub.palette_for(self, v)

    @property
    def frigate(self):
        return self.hub.frigate

    @property
    def frigate_fps(self):
        return self.hub.frigate_fps

    @property
    def cv(self):
        return "%s.%d" % (self.hub.boot, self.build_no)

    def cams(self):
        out = set()
        for v in self.variants.values():
            out |= v.cams
        return out

    def img(self, key):
        """Image d'une carte picture de ce dashboard (seules celles-ci sont relayées)."""
        if key in self.bgs:
            return self.bgs[key]
        for v in self.variants.values():
            if key in v.imgs:
                return v.imgs[key]
        return None

    def view_bg(self, v):
        """Image de fond d'une vue (« Arrière-plan » de HA) : clé de l'image relayée par
        /<nom>/img et réglages. Utilisée en type 3 seulement."""
        b = v.get("background")
        if not isinstance(b, dict):
            return None
        path = render.img_path(b.get("image"), True)
        if not path:
            return None
        key = hashlib.md5(path.encode("utf-8")).hexdigest()[:10]
        self.bgs[key] = ("url", path)
        try:
            op = max(0.0, min(100.0, float(b.get("opacity", 33))))
        except (TypeError, ValueError):
            op = 33.0
        return {"key": key, "opacity": op, "alignment": b.get("alignment"), "size": b.get("size"),
                "repeat": b.get("repeat"), "attachment": b.get("attachment")}

    def notify(self):
        for v in self.variants.values():
            v.notify()

    def variant(self, cls):
        v = self.variants.get(cls)
        if v is None and self.config is not None:
            v = Variant(self, cls)
            self.variants[cls] = v
            self.wanted.add(cls)
            log.info("[%s] rendu « %s » : %d éléments dynamiques, %d actions, %d icônes",
                     self.name, cls, len(v.slots), len(v.actions), v.sprite.count("<symbol"))
            self.hub.wake()
        return v

    def rebuild(self):
        views = (self.config or {}).get("views") or []
        self.bgs = {}
        self.views = [{"index": i, "path": str(views[i].get("path") or i),
                       "bg": self.view_bg(views[i]),
                       "title": views[i].get("title") or views[i].get("path") or "Vue %d" % (i + 1),
                       "subview": bool(views[i].get("subview")),
                       "theme": views[i].get("theme") if isinstance(views[i].get("theme"), str)
                       else "",
                       # Onglet comme HA : icône seule si la vue a une icône, icône et nom si
                       # « show_icon_and_title » est coché, sinon nom seul.
                       "ic": icons.from_mdi(views[i].get("icon")) if views[i].get("icon") else None,
                       "both": bool(views[i].get("show_icon_and_title") and views[i].get("icon")
                                    and views[i].get("title"))}
                      for i in self.indices or []]
        self.build_no += 1
        old = list(self.variants.values())
        self.variants = {}
        for cls in sorted(self.wanted):
            self.variant(cls)
        for v in old:          # les pages ouvertes vont se recharger (cv a changé)
            v.notify()

    def changed(self, keys):
        for v in self.variants.values():
            v.changed(keys)


def downsample(points, start, end, n):
    """[(horodatage, valeur)] -> n moyennes régulières (valeur reportée si pas de mesure)."""
    pts = []
    for t, v in points:
        try:
            if isinstance(t, str):
                t = datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
            elif t and t > 1e11:
                t = t / 1000.0
            pts.append((float(t), float(v)))
        except (TypeError, ValueError):
            continue
    pts.sort()
    span = (end - start) / float(n)
    out, last, idx = [], None, 0
    for i in range(n):
        b_end = start + (i + 1) * span
        vals = []
        while idx < len(pts) and pts[idx][0] < b_end:
            vals.append(pts[idx][1])
            idx += 1
        if vals:
            last = vals[-1]
            out.append(round(sum(vals) / len(vals), 3))
        else:
            out.append(round(last, 3) if last is not None else None)
    return out


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


# --------------------------------------------------------------------------
# Client WebSocket Home Assistant
# --------------------------------------------------------------------------
TR_KEY = re.compile(r"^component\.([a-z0-9_]+)\.entity_component\.([a-z0-9_]+)\.state\.([\w-]+)$")


class HAClient:
    def __init__(self, hub):
        self.hub = hub
        self.opts = hub.opts
        self.ws = None
        self.msg_id = 0
        self.pending = {}
        self.handlers = {}
        self.reload_task = None
        self.subscribed = set()
        self.hist_due = 0
        self.hist30_at = 0
        self.hist30_seen = set()

    async def send(self, payload):
        self.msg_id += 1
        mid = self.msg_id
        fut = asyncio.get_running_loop().create_future()
        self.pending[mid] = fut
        await self.ws.send_str(json.dumps(dict(payload, id=mid)))
        try:
            return await asyncio.wait_for(fut, 30)
        finally:
            self.pending.pop(mid, None)

    async def subscribe(self, payload, handler):
        self.msg_id += 1
        mid = self.msg_id
        self.handlers[mid] = handler
        fut = asyncio.get_running_loop().create_future()
        self.pending[mid] = fut
        await self.ws.send_str(json.dumps(dict(payload, id=mid)))
        try:
            await asyncio.wait_for(fut, 30)
        except Exception:
            self.handlers.pop(mid, None)
            raise
        finally:
            self.pending.pop(mid, None)
        return mid

    async def call_service(self, domain, service, data=None, target=None):
        if not self.ws or self.ws.closed:
            raise RuntimeError("Home Assistant non connecté")
        msg = {"type": "call_service", "domain": domain, "service": service,
               "service_data": data or {}}
        if target:
            msg["target"] = target
        log.info("Action : %s.%s %s", domain, service, target or data)
        return await self.send(msg)

    async def run(self):
        delay = 2
        while True:
            try:
                async with ClientSession() as sess:
                    async with sess.ws_connect(self.opts["ws_url"], heartbeat=30,
                                               max_msg_size=0) as ws:
                        self.ws = ws
                        await self.session(ws)
                        delay = 2
            except asyncio.CancelledError:
                raise
            except Exception as e:  # coupure réseau, HA qui redémarre...
                log.warning("Connexion Home Assistant perdue : %s", e)
            self.ws = None
            self.hub.set_connected(False)
            for f in self.pending.values():
                if not f.done():
                    f.set_exception(ConnectionError("déconnecté"))
            self.pending.clear()
            self.handlers.clear()
            log.info("Nouvelle tentative dans %d s", delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)

    async def session(self, ws):
        msg = await ws.receive_json(timeout=20)
        if msg.get("type") != "auth_required":
            raise RuntimeError("réponse inattendue : %s" % msg)
        await ws.send_str(json.dumps({"type": "auth", "access_token": self.opts["token"]}))
        msg = await ws.receive_json(timeout=20)
        if msg.get("type") != "auth_ok":
            raise RuntimeError("Authentification refusée par Home Assistant")
        log.info("Connecté à Home Assistant %s", msg.get("ha_version", ""))
        reader = asyncio.create_task(self.reader(ws))
        maint = None
        try:
            await self.setup()
            self.hub.set_connected(True)
            maint = asyncio.create_task(self.maintenance())
            await reader
        finally:
            reader.cancel()
            if maint:
                maint.cancel()

    async def reader(self, ws):
        async for m in ws:
            if m.type != WSMsgType.TEXT:
                if m.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                    break
                continue
            data = json.loads(m.data)
            for d in data if isinstance(data, list) else [data]:
                self.dispatch(d)

    def dispatch(self, d):
        t = d.get("type")
        mid = d.get("id")
        if t == "result":
            fut = self.pending.get(mid)
            if fut and not fut.done():
                if d.get("success"):
                    fut.set_result(d.get("result"))
                else:
                    err = d.get("error") or {}
                    fut.set_exception(RuntimeError(err.get("message") or str(err)))
        elif t == "event":
            h = self.handlers.get(mid)
            if h:
                try:
                    h(d.get("event"))
                except Exception:
                    log.exception("Erreur de traitement d'un événement")

    # -- abonnements ------------------------------------------------------
    async def setup(self):
        hub = self.hub
        configs = {}
        all_entities = set()
        selected_all = []
        for dash in hub.dashes.values():
            up = dash.spec["url_path"]
            if up not in configs:
                try:
                    configs[up] = (await self.send({"type": "lovelace/config", "url_path": up,
                                                    "force": False}), None)
                except Exception as e:
                    configs[up] = ({"views": []}, "Dashboard « %s » introuvable : %s"
                                   % (up or "lovelace", e))
            config, err = configs[up]
            dash.error = err
            if err:
                log.error("[%s] %s", dash.name, err)
            # Seulement la vue publiée (+ celles qu'elle ouvre) : charge minimale sur HA.
            dash._new_tabs, dash._new_indices = render.select_views(config, dash.spec["views"])
            views = config.get("views") or []
            selected = [views[i] for i in dash._new_indices]
            dash._new_config = config
            ents = render.collect_entities(selected)
            all_entities |= ents
            selected_all.extend(selected)
            log.info("[%s] %s : %d vue(s), %d entité(s)", dash.name,
                     dash.spec["label"], len(dash._new_indices), len(ents))
        entities = sorted(all_entities)
        hub.reg = await self.load_registry(entities, selected_all)
        await self.load_frigate()
        await self.load_look()
        reg_json = json.dumps([hub.reg, hub.look], sort_keys=True)

        first = asyncio.get_running_loop().create_future()
        seen = {}

        def on_entities(ev):
            changed = set()
            if "a" in ev:
                for eid, v in ev["a"].items():
                    seen[eid] = {"s": v.get("s"), "a": v.get("a") or {},
                                 "lc": v.get("lc") or v.get("lu")}
                    changed.add(eid)
                hub.states.update(seen)
            if "c" in ev:
                for eid, diff in ev["c"].items():
                    st = hub.states.setdefault(eid, {"s": None, "a": {}})
                    plus = diff.get("+") or {}
                    if "s" in plus:
                        st["s"] = plus["s"]
                    if "lc" in plus or ("s" in plus and "lu" in plus):
                        st["lc"] = plus.get("lc") or plus.get("lu")
                    if "a" in plus:
                        st["a"] = dict(st["a"], **plus["a"])
                    minus = diff.get("-") or {}
                    for k in minus.get("a") or []:
                        st["a"].pop(k, None)
                    changed.add(eid)
            if "r" in ev:
                for eid in ev["r"]:
                    hub.states.pop(eid, None)
                    changed.add(eid)
            if not first.done():
                first.set_result(True)
            else:
                hub.changed(changed)

        if entities:
            await self.subscribe({"type": "subscribe_entities", "entity_ids": entities},
                                 on_entities)
            try:
                await asyncio.wait_for(first, 15)
            except asyncio.TimeoutError:
                log.warning("Pas d'état initial reçu")
        for eid in list(hub.states):
            if eid not in seen:
                hub.states.pop(eid, None)
        log.info("%d entité(s) suivie(s) au total", len(entities))

        for dash in hub.dashes.values():
            new_json = json.dumps([dash._new_config, dash._new_indices, dash._new_tabs, reg_json],
                                  sort_keys=True)
            if new_json != dash.config_json or dash.config is None:
                dash.config = dash._new_config
                dash.indices = dash._new_indices
                dash.tab_indices = dash._new_tabs
                dash.config_json = new_json
                dash.rebuild()
            else:
                dash.changed(set(hub.states))
        # Nouvelle connexion : templates et prévisions sont à ré-abonner.
        self.subscribed = set()
        self.hist_due = 0
        await self.sync_needs()
        try:
            await self.subscribe({"type": "subscribe_events", "event_type": "lovelace_updated"},
                                 self._lovelace_updated)
        except Exception as e:
            log.warning("Suivi des modifications des dashboards impossible : %s", e)
        try:
            await self.subscribe({"type": "subscribe_events", "event_type": "themes_updated"},
                                 self._themes_updated)
        except Exception as e:
            log.warning("Suivi des modifications du thème impossible : %s", e)

    async def load_frigate(self):
        """Adresse de Frigate : option frigate_url, sinon celle de l'intégration Frigate de HA
        (titre de son entrée, ex. « ccab4aaf-frigate:5000 ») ; vérifiée par /api/version."""
        hub = self.hub
        cands = []
        if hub.opts.get("frigate_url"):
            cands.append(str(hub.opts["frigate_url"]).strip())
        else:
            try:
                for e in await self.send({"type": "config_entries/get", "domain": "frigate"}) or []:
                    if e.get("domain") == "frigate" and e.get("state") == "loaded" and e.get("title"):
                        cands.append(e["title"])
            except Exception as e:
                log.debug("Entrées Frigate illisibles : %s", e)
        found = ""
        for u in cands:
            u = u.rstrip("/")
            if not re.match(r"^https?://", u):
                u = "http://" + u
            try:
                async with ClientSession() as sess, sess.get(u + "/api/version", timeout=4) as r:
                    if r.status == 200:
                        found = u
                        log.info("Frigate %s : %s", (await r.text()).strip(), u)
                        break
                    log.warning("Frigate %s : réponse %d (port 5000 attendu)", u, r.status)
            except Exception as e:
                log.warning("Frigate %s injoignable : %s", u, e)
        if not found:
            log.info("Pas de Frigate : caméras via Home Assistant")
        fps = {}
        if found:   # latest.jpg change au rythme de la détection : inutile de demander plus vite
            try:
                async with ClientSession() as sess, sess.get(found + "/api/config", timeout=6) as r:
                    for n, c in ((await r.json()).get("cameras") or {}).items():
                        fps[n] = (c.get("detect") or {}).get("fps") or 5
            except Exception as e:
                log.debug("Configuration Frigate illisible : %s", e)
        hub.frigate = found
        hub.frigate_fps = fps
        n = sum(1 for v in hub.reg.values() if v.get("fc"))
        if found and n:
            log.info("%d caméra(s) servie(s) par Frigate", n)

    async def load_look(self):
        """Couleurs du thème et libellés d'état de Home Assistant."""
        hub = self.hub
        themes, dflt = {}, ""
        try:
            res = await self.send({"type": "frontend/get_themes"}) or {}
            themes = res.get("themes") or {}
            dflt = res.get("default_dark_theme") or res.get("default_theme") or ""
        except Exception as e:
            log.warning("Lecture des thèmes impossible : %s", e)
        hub.theme_names = sorted(n for n, v in themes.items() if isinstance(v, dict))
        hub.themes = {n: v for n, v in themes.items() if isinstance(v, dict)}
        hub.default_theme = dflt if dflt in hub.themes else ""
        hub.palettes = {}
        hub.palette = hub.palette_for(None)
        for d in hub.dashes.values():
            how = d.spec.get("theme")
            if how in ("light", "dark"):
                log.info("Thème du dashboard %s : HA %s", d.name,
                         "clair" if how == "light" else "sombre")
                continue
            for v in d.views:
                name = v.get("theme") or ""
                ok = name in hub.themes
                if name and not ok and name not in ("default", "Backend-selected"):
                    log.warning("Thème « %s » (vue %s de %s) introuvable", name, v["title"], d.name)
                log.info("Thème de la vue %s (%s) : %s", v["title"], d.name,
                         name if ok else "défaut de Home Assistant")
        try:
            cfg = await self.send({"type": "get_config"}) or {}
            res = await self.send({"type": "frontend/get_translations",
                                   "language": cfg.get("language") or "fr",
                                   "category": "entity_component"}) or {}
            tr = {}
            for k, v in (res.get("resources") or {}).items():
                m = TR_KEY.match(k)
                if m and isinstance(v, str):
                    tr["%s.%s.%s" % m.groups()] = v
            if tr:
                render.TR.clear()
                render.TR.update(tr)
                log.info("%d libellés d'état repris de Home Assistant", len(tr))
        except Exception as e:
            log.warning("Lecture des libellés d'état impossible : %s", e)
        hub.look = json.dumps([hub.palette, sorted(hub.palettes.items()), len(render.TR)],
                              sort_keys=True)

    def _themes_updated(self, ev):
        log.info("Thèmes modifiés dans Home Assistant : rechargement")
        if self.reload_task and not self.reload_task.done():
            return
        self.reload_task = asyncio.create_task(self._reload_soon())

    async def maintenance(self):
        """Abonnements à la demande + historique des graphiques (toutes les 5 min)."""
        ev = self.hub.need_event
        while True:
            await self.sync_needs()
            if time.time() >= self.hist_due:
                self.hist_due = time.time() + 300
                try:
                    await self.fetch_history()
                except Exception as e:
                    log.warning("Historique indisponible : %s", e)
            try:
                await asyncio.wait_for(ev.wait(), 30)
            except asyncio.TimeoutError:
                pass
            ev.clear()

    async def sync_needs(self):
        tpls, fcs, hists = self.hub.needs()
        for key, tpl in tpls.items():
            if ("t", key) in self.subscribed:
                continue
            self.subscribed.add(("t", key))
            try:
                await self.subscribe({"type": "render_template", "template": tpl},
                                     self._tpl_handler(key))
            except Exception as e:
                log.warning("Template refusé par HA : %s", e)
        for eid, ftype in fcs:
            if ("f", eid, ftype) in self.subscribed:
                continue
            self.subscribed.add(("f", eid, ftype))
            try:
                await self.subscribe({"type": "weather/subscribe_forecast",
                                      "entity_id": eid, "forecast_type": ftype},
                                     self._fc_handler("fc:%s:%s" % (eid, ftype)))
            except Exception as e:
                log.warning("Prévisions indisponibles pour %s : %s", eid, e)
        if any(k not in self.hub.hist for k in hists):
            self.hist_due = 0

    async def fetch_energy(self):
        """Taux d'autosuffisance du jour, calculé comme la carte énergie de HA :
        (1 - réseau / consommation de la maison) x 100, depuis minuit (fuseau de HA)."""
        prefs = await self.send({"type": "energy/get_prefs"}) or {}
        grid_in, grid_out, solar, bat_in, bat_out = set(), set(), set(), set(), set()
        for s in prefs.get("energy_sources") or []:
            t = s.get("type")
            if t == "grid":
                grid_in.add(s.get("stat_energy_from"))
                grid_out.add(s.get("stat_energy_to"))
                for f in s.get("flow_from") or []:      # ancien format des préférences
                    grid_in.add(f.get("stat_energy_from"))
                for f in s.get("flow_to") or []:
                    grid_out.add(f.get("stat_energy_to"))
            elif t == "solar":
                solar.add(s.get("stat_energy_from"))
            elif t == "battery":
                bat_in.add(s.get("stat_energy_from"))    # décharge : vers la maison
                bat_out.add(s.get("stat_energy_to"))     # charge
        groups = [g - {None, ""} for g in (grid_in, grid_out, solar, bat_in, bat_out)]
        ids = sorted(set().union(*groups))
        if not ids:
            return None
        try:
            from zoneinfo import ZoneInfo
            cfg = await self.send({"type": "get_config"}) or {}
            tz = ZoneInfo(cfg.get("time_zone") or "UTC")
        except Exception:
            tz = None
        now = datetime.now(tz) if tz else datetime.now().astimezone()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        res = await self.send({
            "type": "recorder/statistics_during_period", "start_time": start.isoformat(),
            "end_time": now.isoformat(), "statistic_ids": ids, "period": "hour",
            "types": ["change"], "units": {"energy": "kWh"}}) or {}

        def tot(g):
            return sum(r.get("change") or 0 for e in g for r in res.get(e) or [])
        gi, go, so, bi, bo = (tot(g) for g in groups)
        cons = max(0.0, gi + so + bi - go - bo)
        if cons <= 0:
            return None
        return (1 - min(1.0, gi / cons)) * 100

    async def fetch_history(self):
        _, _, hists = self.hub.needs()
        if not hists:
            return
        changed = set()
        # clés « e:… » : données énergie (pas des courbes)
        if "e:ss" in hists:
            try:
                v = await self.fetch_energy()
            except Exception as e:
                log.warning("Données énergie indisponibles : %s", e)
                v = None
            if self.hub.hist.get("e:ss", -1) != v:
                self.hub.hist["e:ss"] = v
                changed.add("hist:e:ss")
        hists = {k: v for k, v in hists.items() if not k.startswith("e:")}
        by_hours = {}
        for key, (eid, hours) in hists.items():
            by_hours.setdefault(hours, []).append((key, eid))
        now = time.time()
        for hours, items in by_hours.items():
            start = now - hours * 3600
            eids = sorted({e for _, e in items})
            if hours <= 48:     # historique détaillé
                res = await self.send({
                    "type": "history/history_during_period", "start_time": iso(start),
                    "end_time": iso(now), "entity_ids": eids, "minimal_response": True,
                    "no_attributes": True, "significant_changes_only": False}) or {}
                series = {e: [(p.get("lu") or p.get("lc"), p.get("s")) for p in res.get(e) or []]
                          for e in eids}
            else:               # statistiques horaires (beaucoup plus léger sur de longues durées)
                res = await self.send({
                    "type": "recorder/statistics_during_period", "start_time": iso(start),
                    "end_time": iso(now), "statistic_ids": eids, "period": "hour",
                    "types": ["mean", "state"]}) or {}
                series = {e: [(r.get("start"), r.get("mean") if r.get("mean") is not None
                               else r.get("state")) for r in res.get(e) or []] for e in eids}
            for key, eid in items:
                vals = downsample(series.get(eid, []), start, now, render.HIST_POINTS)
                if self.hub.hist.get(key) != vals:
                    self.hub.hist[key] = vals
                    changed.add("hist:" + key)
        # Type 1 : courbes redessinées au plus toutes les 30 min.
        new30 = {"hist30:" + k[5:] for k in changed if k[5:] not in self.hist30_seen}
        if time.time() - self.hist30_at >= 1800:
            self.hist30_at = time.time()
            changed |= {"hist30:" + k for k in hists}
        else:
            changed |= new30
        self.hist30_seen |= {k for k in hists if k in self.hub.hist}
        log.debug("Historique : %d graphique(s) mis à jour", len(changed))
        if changed:
            self.hub.changed(changed)

    async def load_registry(self, entities, selected):
        """Noms d'appareil/pièce et précision d'affichage, lus une fois par connexion."""
        reg = {}
        if not entities:
            return reg
        try:
            entries = await self.send({"type": "config/entity_registry/get_entries",
                                       "entity_ids": entities})
        except Exception as e:
            log.warning("Registre des entités illisible : %s", e)
            return reg
        need_names = any(True for _ in _iter_names(selected))
        devices, areas = {}, {}
        if need_names:
            try:
                for d in await self.send({"type": "config/device_registry/list"}):
                    devices[d["id"]] = d
                for a in await self.send({"type": "config/area_registry/list"}):
                    areas[a["area_id"]] = a.get("name")
            except Exception as e:
                log.warning("Registre des appareils illisible : %s", e)
        for eid, ent in (entries or {}).items():
            if not ent:
                continue
            info = {}
            sopts = (ent.get("options") or {}).get("sensor") or {}
            dp = sopts.get("display_precision")
            if dp is None:
                dp = sopts.get("suggested_display_precision")
            if dp is not None:
                info["dp"] = dp
            # caméra de l'intégration Frigate : unique_id « <entrée>:camera:<nom Frigate> »
            m = re.search(r":camera:([^:]+)$", str(ent.get("unique_id") or ""))
            if ent.get("platform") == "frigate" and m:
                info["fc"] = m.group(1)
            fav = ((ent.get("options") or {}).get("light") or {}).get("favorite_colors")
            if isinstance(fav, list):
                info["fav"] = fav
            if need_names:
                dev = devices.get(ent.get("device_id")) or {}
                info["dn"] = dev.get("name_by_user") or dev.get("name") or ""
                info["en"] = strip_prefix(ent.get("name") or ent.get("original_name") or "",
                                          info["dn"])
                info["an"] = areas.get(ent.get("area_id") or dev.get("area_id")) or ""
            reg[eid] = info
        return reg

    def _tpl_handler(self, key):
        def h(ev):
            if "result" in ev:
                self.hub.tpl[key] = str(ev["result"])
            elif "error" in ev:
                self.hub.tpl[key] = "Erreur de template : %s" % ev["error"]
            self.hub.changed({"tpl:" + key})
        return h

    def _fc_handler(self, key):
        def h(ev):
            self.hub.fc[key] = ev.get("forecast") or []
            self.hub.changed({key})
        return h

    def _lovelace_updated(self, ev):
        data = (ev or {}).get("data") or {}
        if data.get("url_path") not in {d.spec["url_path"] for d in self.hub.dashes.values()}:
            return
        log.info("Dashboard « %s » modifié dans Home Assistant : rechargement",
                 data.get("url_path") or "lovelace")
        if self.reload_task and not self.reload_task.done():
            return
        self.reload_task = asyncio.create_task(self._reload_soon())

    async def _reload_soon(self):
        await asyncio.sleep(2)
        # Le plus simple et le plus sûr : on recrée la connexion.
        if self.ws and not self.ws.closed:
            await self.ws.close()

    async def set_value(self, a, v):
        eid, part = a["entity"], a.get("part") or ""
        dom = render.domain_of(eid)
        at = (self.hub.states.get(eid) or {}).get("a") or {}
        target = {"entity_id": eid}
        v = v.strip() if dom not in ("text", "input_text") else v
        if dom in ("number", "input_number"):
            f = float(v.replace(",", "."))
            if not (float(at.get("min", f)) <= f <= float(at.get("max", f))):
                raise RuntimeError("valeur hors limites")
            return await self.call_service(dom, "set_value", {"value": f}, target)
        if dom in ("select", "input_select"):
            if v not in [str(o) for o in (at.get("options") or [])]:
                raise RuntimeError("option inconnue")
            return await self.call_service(dom, "select_option", {"option": v}, target)
        if dom in ("text", "input_text"):
            return await self.call_service(dom, "set_value", {"value": v}, target)
        if not re.match(r"^(\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}(:\d{2})?)$", v):
            raise RuntimeError("format invalide")
        if ":" in v and len(v) < 8:
            v = ("0" + v if len(v) == 4 else v) + ":00"
        if dom == "time":
            return await self.call_service("time", "set_value", {"time": v}, target)
        if dom == "date":
            return await self.call_service("date", "set_value", {"date": v}, target)
        return await self.call_service("input_datetime", "set_datetime",
                                       {"time" if part == "time" else "date": v}, target)

    async def run_action(self, a, value=None):
        kind = a.get("kind")
        if kind == "light":
            # curseur luminosité (b) ou température (k) ; value = position 0..1000
            eid = a["entity"]
            at = (self.hub.states.get(eid) or {}).get("a") or {}
            f = max(0.0, min(1.0, float(value) / 1000.0))
            if a["what"] == "b":
                data = {"brightness_pct": max(1, int(round(f * 100)))}
            elif a["what"] == "h":      # barre de teintes : couleur pure
                data = {"hs_color": [round(f * 360.0, 1) % 360, 100]}
            else:
                lo = float(at.get("min_color_temp_kelvin") or 2000)
                hi = float(at.get("max_color_temp_kelvin") or 6500)
                data = {"color_temp_kelvin": int(round(lo + (hi - lo) * f))}
            return await self.call_service("light", "turn_on", data, {"entity_id": eid})
        if kind == "service":
            return await self.call_service(a["domain"], a["service"], a.get("data"),
                                           a.get("target"))
        if kind == "set":       # champ modifiable d'une ligne (nombre, liste, heure, texte)
            return await self.set_value(a, "" if value is None else str(value))
        if kind == "all":       # interrupteur d'en-tête : tout éteindre si l'une est allumée
            ents = a.get("entities") or []
            on = any((self.hub.states.get(e) or {}).get("s") == "on" for e in ents)
            res = None
            for e in ents:
                dom = render.domain_of(e)
                dom = "homeassistant" if dom in ("group", "valve") else dom
                res = await self.call_service(dom, "turn_off" if on else "turn_on", None,
                                              {"entity_id": e})
            return res
        eid = a.get("entity")
        st = self.hub.states.get(eid) or {}
        s = st.get("s")
        dom = render.domain_of(eid)
        if kind == "temp":
            cur = (st.get("a") or {}).get("temperature")
            if cur is None:
                raise RuntimeError("pas de consigne")
            return await self.call_service("climate", "set_temperature",
                                           {"temperature": float(cur) + float(a["step"])},
                                           {"entity_id": eid})
        if kind != "toggle":
            raise RuntimeError("action inconnue")
        target = {"entity_id": eid}
        if dom == "lock":
            return await self.call_service("lock", "unlock" if s == "locked" else "lock",
                                           None, target)
        if dom in ("scene", "script"):
            return await self.call_service(dom, "turn_on", None, target)
        if dom in ("button", "input_button"):
            return await self.call_service(dom, "press", None, target)
        if dom == "vacuum":
            return await self.call_service(
                "vacuum", "return_to_base" if s == "cleaning" else "start", None, target)
        if dom in ("light", "switch", "fan", "input_boolean", "automation", "siren",
                   "humidifier", "cover", "media_player", "climate"):
            return await self.call_service(dom, "toggle", None, target)
        return await self.call_service("homeassistant", "toggle", None, target)


def _iter_names(obj):
    """Noms de cartes donnés sous forme d'objet ({type: device}...)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "name" and isinstance(v, (dict, list)):
                yield v
            else:
                yield from _iter_names(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from _iter_names(x)


# --------------------------------------------------------------------------
# Serveur web
# --------------------------------------------------------------------------
def client_ok(req, opts):
    nets = opts["_nets"]
    if nets:
        try:
            ip = ipaddress.ip_address(req.remote or "")
            if ip.version == 6 and ip.ipv4_mapped:
                ip = ip.ipv4_mapped
        except ValueError:
            return False
        if not any(ip in n for n in nets):
            return False
    key = opts.get("access_key") or ""
    if key:
        k = req.query.get("k") or req.cookies.get("sdk")
        if k != key:
            return False
    return True


_denied_logged = set()
_last_actions = {}


@web.middleware
async def guard(req, handler):
    if req.path.startswith("/static/") or req.path in ("/favicon.ico", "/manifest.json"):
        return await handler(req)
    opts = req.app["hub"].opts
    if not client_ok(req, opts):
        if req.remote not in _denied_logged:
            _denied_logged.add(req.remote)
            log.warning("Accès refusé pour %s (réseau non autorisé ou clé absente)", req.remote)
        return web.Response(status=403, text="Accès refusé")
    return await handler(req)


def get_dash(req):
    dash = req.app["hub"].dashes.get(req.match_info["name"].lower())
    if dash is None:
        raise web.HTTPNotFound(text="Dashboard inconnu. Liste : /")
    return dash


def pick_view(dash, ref):
    views = dash.views
    if not views:
        return None, -1
    if ref is not None and ref != "":
        for i, v in enumerate(views):
            if v["path"] == ref:
                return v, i
        for i, v in enumerate(views):
            if str(v.get("index")) == str(ref):
                return v, i
    for i, v in enumerate(views):
        if not v["subview"]:
            return v, i
    return views[0], 0


def page_shell(hub, dash, title, body, tabs, extra_head="", cls="t1", var=None, view=None):
    o = hub.opts
    # Version du rendu HTML (et non la version courante) : le navigateur
    # recevra tout ce qui a changé depuis que le HTML a été produit.
    sd = {"v": var.build_version if var else 0, "cv": dash.cv if (dash and var) else "",
          "cl": cls,
          "base": "/%s/" % dash.name if dash else "/",
          "key": o.get("access_key") or "",
          "tmo": LONGPOLL, "iv": dash.spec["refresh"] if dash else 0,
          "c": 1 if hub.connected else 0}
    # Pas de bandeau : la pastille de connexion est fixe en haut à droite, devant tout.
    tabs = ('<span id="dw"><span id="dot" class="%s"></span></span>'
            % ("ok" if hub.connected else "ha")) + tabs
    return ("<!DOCTYPE html><html lang=\"fr\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, user-scalable=no, viewport-fit=cover\">"
            "<meta name=\"mobile-web-app-capable\" content=\"yes\">"
            "<title>%s</title><link rel=\"stylesheet\" href=\"/static/s.css?%s\">"
            "<link rel=\"icon\" type=\"image/png\" href=\"/static/icon.png\">"
            "<link rel=\"apple-touch-icon\" href=\"/static/icon.png\">"
            "<link rel=\"manifest\" href=\"/manifest.json?s=%s&amp;n=%s\">%s%s</head>"
            "<body class=\"k-%s\">"
            "%s<div id=\"main\"%s>%s</div>"
            "<script>var SD=%s;</script><script src=\"/static/s.js?%s\"></script>"
            "</body></html>") % (
        render.E(title), STATIC_TAG, quote(sd["base"]), quote(title or "SlimDash"),
        class_css(cls) + hub.theme_style(cls, dash, view), extra_head, cls,
        # deux colonnes possibles (paysage) seulement si la vue a au moins deux sections,
        # ou une section sur plusieurs colonnes (column_span)
        tabs, ' class="cols2"' if ('class="sect c1"' in body or 'class="sect sp' in body) else "",
        body, json.dumps(sd), STATIC_TAG)


def class_css(cls):
    """Feuilles de style en plus de s.css selon la type d'appareil."""
    files = {"t1": [], "t2": ["c-t2.css"],
             "t3": ["c-t2.css", "c-t3.css"]}.get(cls, [])
    return "".join('<link rel="stylesheet" href="/static/%s?%s">' % (f, STATIC_TAG) for f in files)


def default_ref(d):
    return str(d.tab_indices[0]) if d.tab_indices else None


def dash_title(d):
    """Titre d'un dashboard publié : titre de sa 1re vue."""
    v, _ = pick_view(d, default_ref(d))
    return str(v["title"]) if v else d.name


async def h_index(req):
    hub = req.app["hub"]
    dashes = list(hub.dashes.values())
    if len(dashes) == 1:
        raise web.HTTPFound("/%s%s" % (dashes[0].name, "?" + req.query_string
                                       if req.query_string else ""))
    k = "?k=" + req.query["k"] if req.query.get("k") else ""
    items = "".join(
        '<a class="card dl" href="/%s%s"><b>%s</b><br><span class="sub">%s</span></a>' % (
            render.E(d.name), render.E(k), render.E(dash_title(d)),
            render.E(d.spec["label"]))
        for d in dashes) or '<div class="card">Aucun dashboard configuré.</div>'
    html_ = page_shell(hub, None, "SlimDash", items, "", cls=device_type(None, req))
    return web.Response(text=html_, content_type="text/html",
                        headers={"Cache-Control": "no-store", "Vary": "User-Agent"})


async def h_diag(req):
    """Ce que l'appareil annonce, et le type que SlimDash en déduit."""
    hub = req.app["hub"]
    ua = req.headers.get("User-Agent", "")
    eng, ver, cls = classify(ua)
    rows = [("Navigateur annoncé (User-Agent)", ua or "—"),
            ("Moteur détecté", "%s %s" % (eng, ver or "")),
            ("Type automatique", TYPE_LABEL[cls]),
            ("Adresse IP", req.remote or "—")]
    for d in hub.dashes.values():
        forced = d.spec["device"]
        eff = forced if forced in TYPE_IDS else cls
        rows.append(("Dashboard /%s" % d.name, "%s (%s)" % (
            TYPE_LABEL[eff], "forcé" if forced in TYPE_IDS else "auto")))
    body = '<div class="card"><h2>Diagnostic de cet appareil</h2>' + "".join(
        '<div class="row"><span class="nm">%s</span><span class="rt diag">%s</span></div>'
        % (render.E(k), render.E(v)) for k, v in rows) + (
        '<div class="row"><span class="nm">Écran</span><span class="rt diag">'
        '<script>document.write(screen.width+" x "+screen.height+" (fenêtre "'
        '+window.innerWidth+" x "+window.innerHeight+", densité "'
        '+(window.devicePixelRatio||1)+")");</script></span></div></div>')
    html_ = page_shell(hub, None, "SlimDash – diagnostic", body, "", cls=cls)
    return web.Response(text=html_, content_type="text/html",
                        headers={"Cache-Control": "no-store", "Vary": "User-Agent"})


async def h_page(req):
    hub = req.app["hub"]
    dash = get_dash(req)
    ref = req.query.get("view") or default_ref(dash)
    view, idx = pick_view(dash, ref)
    resp_headers = {"Cache-Control": "no-store"}
    if view is None:
        msg = dash.error or "Connexion à Home Assistant…"
        html_ = page_shell(hub, dash, "SlimDash",
                           '<div class="card"><p>%s</p></div>' % render.E(msg),
                           "", '<meta http-equiv="refresh" content="5">')
        return web.Response(text=html_, content_type="text/html", headers=resp_headers)
    cls = device_type(dash, req)
    var = dash.variant(cls)
    page = var.pages.get(idx)
    if page is None:
        tabs = ""
        # Pas d'onglets s'il n'y a qu'une seule vue (la pastille de connexion est à part).
        if len(dash.tab_indices) > 1:
            byidx = {v["index"]: v for v in dash.views}
            tabs = '<div id="tabs" class="%s">' % ("bot" if dash.spec["tabs_bottom"] else "top")
            for i in dash.tab_indices:
                v = byidx.get(i)
                if v is None:
                    continue
                name = render.E(str(v["title"]))
                if v.get("ic"):
                    ic = '<svg class="ic"><use xlink:href="#i-%s"></use></svg>' % v["ic"]
                    label = (ic + '<span class="tl">%s</span>' % name) if v.get("both") else ic
                else:
                    label = name
                tabs += '<a class="tab%s%s" href="/%s?view=%d" title="%s">%s</a>' % (
                    " cur" if v is view else "", " ti1" if v.get("ic") and not v.get("both") else "",
                    render.E(dash.name), i, name, label)
            tabs += "</div>"
        title = str(view["title"])
        body = var.sprite + var.body.get(view["index"], "")
        page = page_shell(hub, dash, title, body, tabs, cls=cls, var=var, view=view).encode("utf-8")
        var.pages[idx] = page
    t = req.query.get("type")
    if t in TYPES:      # type forcé : gardé en changeant d'onglet (pas dans la page en cache)
        page = page.replace(('href="/%s?view=' % render.E(dash.name)).encode("utf-8"),
                            ('href="/%s?type=%s&amp;view=' % (render.E(dash.name), t)).encode("utf-8"))
    resp_headers["Vary"] = "User-Agent"
    resp = web.Response(body=page, content_type="text/html", charset="utf-8",
                        headers=resp_headers)
    if hub.opts.get("access_key") and req.query.get("k"):
        resp.set_cookie("sdk", req.query["k"], max_age=10 * 365 * 86400, path="/")
    resp.enable_compression()
    return resp


async def h_updates(req):
    hub = req.app["hub"]
    dash = get_dash(req)
    q = req.query
    nocache = {"Cache-Control": "no-store"}
    try:
        v = int(q.get("v", "0"))
    except ValueError:
        v = 0
    var = dash.variants.get(q.get("cl") or "")
    if q.get("cv") != dash.cv or var is None:
        return web.json_response({"r": 1}, headers=nocache)
    ch = var.changes_since(v)
    # w=0 : rafraîchissement périodique, réponse immédiate (pas d'attente).
    if not ch and q.get("w") != "0" and q.get("c") == ("1" if hub.connected else "0"):
        fut = asyncio.get_running_loop().create_future()
        var.waiters.add(fut)
        try:
            await asyncio.wait_for(fut, LONGPOLL)
        except asyncio.TimeoutError:
            pass
        finally:
            var.waiters.discard(fut)
        if q.get("cv") != dash.cv or dash.variants.get(var.cls) is not var:
            return web.json_response({"r": 1}, headers=nocache)
        ch = var.changes_since(v)
    return web.json_response({"v": hub.version, "c": 1 if hub.connected else 0, "u": ch},
                             headers=nocache)


async def h_action(req):
    dash = get_dash(req)
    ha = req.app["ha"]
    var = dash.variants.get(req.query.get("cl") or "")
    if req.query.get("cv") != dash.cv or var is None:
        return web.json_response({"r": 1})
    form = await req.post()
    try:
        idx = int(form.get("a", "-1"))
        a = var.actions[idx]
    except (ValueError, IndexError):
        return web.json_response({"ok": 0, "e": "action inconnue"}, status=400)
    # Même action du même appareil en moins d'1 s : doublon (toucher + clic fantôme).
    last = _last_actions
    sig = (req.remote, dash.name, var.cls, idx, form.get("v"))
    now = time.time()
    if now - last.get(sig, 0) < 1.0:
        log.info("Action en double ignorée (%s)", req.remote)
        return web.json_response({"ok": 1})
    last[sig] = now
    try:
        await ha.run_action(a, form.get("v"))
    except Exception as e:
        log.warning("Échec de l'action %s : %s", a, e)
        return web.json_response({"ok": 0, "e": str(e)}, status=502)
    return web.json_response({"ok": 1})


async def h_live(req):
    """Vidéo en direct d'une caméra Frigate : relais du websocket MSE de go2rtc
    (Frigate /live/mse/api/ws). Le navigateur ne parle qu'à SlimDash."""
    hub = req.app["hub"]
    dash = get_dash(req)
    eid = req.query.get("e", "")
    fc = (hub.reg.get(eid) or {}).get("fc") if hub.frigate else None
    if not fc or eid not in dash.cams():
        raise web.HTTPNotFound()
    ws = web.WebSocketResponse(heartbeat=30, max_msg_size=0)
    await ws.prepare(req)
    url = re.sub(r"^http", "ws", hub.frigate) + "/live/mse/api/ws?src=" + quote(fc)
    try:
        async with req.app["http"].ws_connect(url, timeout=10, max_msg_size=0) as up:
            async def down():
                async for m in up:
                    if m.type == WSMsgType.BINARY:
                        await ws.send_bytes(m.data)
                    elif m.type == WSMsgType.TEXT:
                        await ws.send_str(m.data)
                    else:
                        break

            async def upw():
                async for m in ws:
                    if m.type == WSMsgType.TEXT:
                        await up.send_str(m.data)
                    else:
                        break
            tasks = [asyncio.ensure_future(down()), asyncio.ensure_future(upw())]
            _, pend = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pend:
                t.cancel()
    except Exception as e:
        log.debug("Live %s interrompu : %s", eid, e)
    await ws.close()
    return ws


async def h_debug(req):
    hub = req.app["hub"]
    return web.json_response({
        "version": VERSION, "connected": hub.connected, "entities": len(hub.states),
        "templates": len(hub.tpl), "graphs": len(hub.hist),
        "frigate": hub.frigate or None,
        "frigate_cameras": {e: "%s (%s i/s)" % (v["fc"], hub.frigate_fps.get(v["fc"], 5))
                            for e, v in hub.reg.items() if v.get("fc")},
        "dashboards": {d.name: {
            "source": d.spec["label"], "error": d.error, "cv": d.cv, "tabs": d.tab_indices,
            "views": [{"path": v["path"], "title": v["title"]} for v in d.views],
            "rendus": {TYPE_LABEL[c].lower(): {"slots": len(v.slots), "actions": len(v.actions),
                           "graphiques": len(v.need_hist), "cameras": sorted(v.cams),
                           "clients_en_attente": len(v.waiters)}
                       for c, v in sorted(d.variants.items())}} for d in hub.dashes.values()},
    }, dumps=lambda o: json.dumps(o, ensure_ascii=False, indent=1))


async def h_cam(req):
    """Image d'une caméra du dashboard en 360 px de haut, via Frigate ou à défaut HA,
    partagée entre les appareils : gardée 0,15 s (Frigate) ou 0,8 s (HA)."""
    hub = req.app["hub"]
    dash = get_dash(req)
    eid = req.query.get("e", "")
    if not eid.startswith("camera.") or eid not in dash.cams():
        raise web.HTTPNotFound()
    cache = req.app["camcache"]
    key = eid
    fc = (hub.reg.get(eid) or {}).get("fc") if hub.frigate else None
    if fc:
        url, hdr, ttl = "%s/api/%s/latest.jpg?h=360" % (hub.frigate, quote(fc)), {}, 0.15
    else:       # HA réduit seulement si largeur ET hauteur sont données (640x360 en 16:9)
        url = "%s/camera_proxy/%s?width=640&height=360" % (hub.opts["api_url"], eid)
        hdr, ttl = {"Authorization": "Bearer " + hub.opts["token"]}, 0.8
    lock = req.app["camlocks"].setdefault(key, asyncio.Lock())
    async with lock:
        ent = cache.get(key)
        if not ent or time.time() - ent[0] > ttl:
            try:
                async with req.app["http"].get(url, headers=hdr, timeout=10) as r:
                    if r.status != 200:
                        raise web.HTTPBadGateway(text="caméra indisponible (%d)" % r.status)
                    ent = (time.time(), await r.read(), r.headers.get("Content-Type", "image/jpeg"))
            except web.HTTPException:
                raise
            except Exception as e:
                raise web.HTTPBadGateway(text="caméra indisponible : %s" % e)
            cache[key] = ent
            for k in [k for k, v in cache.items() if time.time() - v[0] > 120]:
                cache.pop(k, None)
    return web.Response(body=ent[1], headers={"Content-Type": ent[2], "Cache-Control": "no-store"})


async def h_img(req):
    """Image d'une carte picture, relayée depuis HA (avec le jeton : /local, image envoyée,
    image d'entité) ou depuis son adresse http(s). Gardée 10 min, partagée entre appareils."""
    hub = req.app["hub"]
    dash = get_dash(req)
    spec = dash.img(req.query.get("i", ""))
    if not spec:
        raise web.HTTPNotFound()
    kind, val = spec
    if kind == "ent":
        val = ((hub.states.get(val) or {}).get("a") or {}).get("entity_picture")
        if not val:
            raise web.HTTPNotFound()
    base = hub.opts["api_url"][:-len("/api")]
    if val.startswith("/"):
        url, hdr = base + val, {"Authorization": "Bearer " + hub.opts["token"]}
    else:
        url, hdr = val, {}
    cache = req.app["imgcache"]
    lock = req.app["camlocks"].setdefault("img:" + url, asyncio.Lock())
    async with lock:
        ent = cache.get(url)
        if not ent or time.time() - ent[0] > 600:
            try:
                async with req.app["http"].get(url, headers=hdr, timeout=20) as r:
                    if r.status != 200:
                        raise web.HTTPBadGateway(text="image indisponible (%d)" % r.status)
                    ctype = r.headers.get("Content-Type", "image/jpeg")
                    if not ctype.startswith("image/"):
                        raise web.HTTPBadGateway(text="pas une image")
                    body = await r.read()
                    if len(body) > 15 * 1024 * 1024:
                        raise web.HTTPBadGateway(text="image trop lourde")
                    ent = (time.time(), body, ctype)
            except web.HTTPException:
                raise
            except Exception as e:
                raise web.HTTPBadGateway(text="image indisponible : %s" % e)
            cache[url] = ent
            for k in [k for k, v in cache.items() if time.time() - v[0] > 3600]:
                cache.pop(k, None)
        # Image de fond d'une vue : réduite à la taille de l'écran demandée (w), une fois
        # par image, puis gardée.
        w = req.query.get("w", "")
        if w.isdigit() and int(w) in theme.BG_SIZES:
            small = cache.get(url + "#" + w)
            if not small or small[0] != ent[0]:
                body, ctype = await asyncio.get_running_loop().run_in_executor(
                    None, shrink_image, ent[1], ent[2], int(w))
                small = (ent[0], body, ctype)
                cache[url + "#" + w] = small
            return web.Response(body=small[1], headers={"Content-Type": small[2],
                                                        "Cache-Control": "max-age=86400"})
    return web.Response(body=ent[1], headers={"Content-Type": ent[2], "Cache-Control": "max-age=600"})


def shrink_image(body, ctype, side):
    """Réduit l'image pour que son plus grand côté fasse « side » pixels au plus (jamais
    agrandie). Sans Pillow, ou image illisible : l'image d'origine."""
    try:
        from PIL import Image, ImageOps
        im = Image.open(io.BytesIO(body))
        im = ImageOps.exif_transpose(im)
        if max(im.size) <= side:
            return body, ctype
        im.thumbnail((side, side), Image.LANCZOS)
        buf = io.BytesIO()
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            im.convert("RGBA").save(buf, "PNG", optimize=True)
            return buf.getvalue(), "image/png"
        im.convert("RGB").save(buf, "JPEG", quality=72, optimize=True, progressive=True)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        log.exception("réduction d'image impossible")
        return body, ctype


async def h_static(req):
    name = req.match_info["name"]
    types = {"s.css": "text/css", "c-t2.css": "text/css", "c-t3.css": "text/css",
             "s.js": "application/javascript", "icon.png": "image/png"}
    if name not in types:
        raise web.HTTPNotFound()
    ctype = types[name]
    with open(os.path.join(HERE, "static", name), "rb") as f:
        body = f.read()
    resp = web.Response(body=body, content_type=ctype,
                        charset=None if ctype == "image/png" else "utf-8",
                        headers={"Cache-Control": "public, max-age=86400"})
    if ctype != "image/png":
        resp.enable_compression()
    return resp


async def h_favicon(req):
    raise web.HTTPFound("/static/icon.png")


_icon192 = None


async def h_icon192(req):
    """icon.png agrandie à 192 px : taille minimale pour installer la page comme appli."""
    global _icon192
    if _icon192 is None:
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.open(os.path.join(HERE, "static", "icon.png")).convert("RGBA") \
            .resize((192, 192), Image.LANCZOS).save(buf, "PNG")
        _icon192 = buf.getvalue()
    return web.Response(body=_icon192, content_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})


async def h_manifest(req):
    """Manifest PWA : plein écran quand la page est installée sur l'écran d'accueil."""
    start = req.query.get("s") or "/"
    if not start.startswith("/") or start.startswith("//"):
        start = "/"
    name = (req.query.get("n") or "SlimDash")[:60]
    body = {"name": name, "short_name": name[:12], "start_url": start, "scope": "/",
            "display": "fullscreen", "background_color": "#000000", "theme_color": "#000000",
            "icons": [{"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
                      {"src": "/static/icon.png", "sizes": "128x128", "type": "image/png"}]}
    return web.Response(text=json.dumps(body), content_type="application/manifest+json",
                        headers={"Cache-Control": "no-cache"})


async def on_startup(app):
    app["hub"].need_event = asyncio.Event()
    app["http"] = ClientSession()
    app["camcache"], app["camlocks"], app["imgcache"] = {}, {}, {}
    app["ha_task"] = asyncio.create_task(app["ha"].run())


async def on_cleanup(app):
    app["ha_task"].cancel()
    await app["http"].close()


def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    opts = load_options()
    logging.getLogger().setLevel(
        getattr(logging, str(opts.get("log_level", "info")).upper(), logging.INFO))
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
    log.info("SlimDash %s, port %s", VERSION, opts["port"])
    for d in opts["_dashes"]:
        log.info("  /%s  <-  %s", d["name"], d["label"])
    if not opts["token"]:
        log.error("Aucun jeton : lancez SlimDash comme add-on, ou définissez HA_TOKEN.")
    hub = Hub(opts)
    app = web.Application(middlewares=[guard])
    app["hub"] = hub
    app["ha"] = HAClient(hub)
    app.router.add_get("/", h_index)
    app.router.add_get("/debug", h_debug)
    app.router.add_get("/diag", h_diag)
    app.router.add_get("/favicon.ico", h_favicon)
    app.router.add_get("/manifest.json", h_manifest)
    app.router.add_get("/static/icon-192.png", h_icon192)
    app.router.add_get("/static/{name}", h_static)
    eink.setup(app, get_dash, pick_view, default_ref)     # type 0 : /<nom>.png
    app.router.add_get("/{name}", h_page)
    app.router.add_get("/{name}/", h_page)
    app.router.add_get("/{name}/u", h_updates)
    app.router.add_get("/{name}/cam", h_cam)
    app.router.add_get("/{name}/img", h_img)
    app.router.add_get("/{name}/live", h_live)
    app.router.add_post("/{name}/a", h_action)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    web.run_app(app, port=int(opts["port"]), access_log=None, print=None)


if __name__ == "__main__":
    main()
