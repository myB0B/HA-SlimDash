"""SlimDash - couleurs reprises du thème Home Assistant.

Le thème HA (variables CSS) est réduit à une petite palette de couleurs opaques,
puis traduit en quelques règles CSS propres à chaque type d'appareil :
règles explicites pour le type 1 (pas de variables CSS), variables pour les autres.
Les transparences sont calculées ici : aucun effet coûteux côté navigateur.
"""
import os
import re

# Thème sombre par défaut de Home Assistant.
DEFAULTS = {
    "primary-background-color": "#111111",
    "ha-card-background": "#1c1c1c",
    "primary-text-color": "#e1e1e1",
    "secondary-text-color": "#9b9b9b",
    "primary-color": "#03a9f4",
    "accent-color": "#ff9800",
    "ha-card-border-radius": "12px",
    "state-icon-color": "#44739e",
    "state-active-color": "#ffc107",
    "state-inactive-color": "#9e9e9e",
}
# Thème clair par défaut de Home Assistant (mode « clair »).
LIGHT = dict(DEFAULTS, **{
    "primary-background-color": "#fafafa",
    "ha-card-background": "#ffffff",
    "primary-text-color": "#212121",
    "secondary-text-color": "#727272",
})
# groupe de couleur SlimDash -> (variables HA possibles, couleur HA par défaut ; None = « actif »)
GROUPS = {
    "light": (("state-light-active-color", "state-light-on-color"), None),
    "switch": (("state-switch-active-color", "state-switch-on-color"), None),
    "binary": (("state-binary_sensor-active-color", "state-binary_sensor-on-color"), None),
    "fan": (("state-fan-active-color", "state-fan-on-color"), "#00bcd4"),
    "cover": (("state-cover-active-color", "state-cover-open-color"), "#926bc7"),
    "climate": (("state-climate-heat-color",), "#ff5722"),
    "media": (("state-media_player-active-color",), "#03a9f4"),
    "vacuum": (("state-vacuum-active-color",), "#009688"),
    "person": (("state-person-home-color", "state-person-active-color"), "#4caf50"),
}
NAMED = {"white": (255, 255, 255, 1.0), "black": (0, 0, 0, 1.0), "transparent": (0, 0, 0, 0.0)}


def parse(c):
    """Couleur CSS simple -> (r, g, b, a) ou None."""
    if not isinstance(c, str):
        return None
    c = c.strip().lower()
    if c in NAMED:
        return NAMED[c]
    m = re.match(r"^#([0-9a-f]{3,8})$", c)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(x * 2 for x in h)
        if len(h) not in (6, 8):
            return None
        a = int(h[6:8], 16) / 255.0 if len(h) == 8 else 1.0
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)
    m = re.match(r"^rgba?\(([^)]+)\)$", c)
    if m:
        parts = [p for p in re.split(r"[\s,/]+", m.group(1).strip()) if p]
        try:
            rgb = [max(0, min(255, int(round(float(p))))) for p in parts[:3]]
            a = 1.0
            if len(parts) > 3:
                a = float(parts[3][:-1]) / 100 if parts[3].endswith("%") else float(parts[3])
        except ValueError:
            return None
        if len(rgb) == 3:
            return (rgb[0], rgb[1], rgb[2], max(0.0, min(1.0, a)))
    return None


def blend(fg, bg, alpha=None):
    """fg posé sur bg (opaque) avec la transparence de fg, ou alpha si donné."""
    a = fg[3] if alpha is None else alpha
    return tuple(int(round(fg[i] * a + bg[i] * (1 - a))) for i in range(3)) + (1.0,)


def hexc(c):
    return "#%02x%02x%02x" % (c[0], c[1], c[2])


def lum(c):
    """Luminance relative (WCAG) d'une couleur (r, g, b)."""
    def ch(x):
        x = x / 255.0
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])


def readable(color, card, ratio=3.0):
    """Sur un fond clair, assombrit une couleur trop claire (même teinte) jusqu'à un
    contraste suffisant ; sur un fond sombre, la couleur est rendue telle quelle."""
    c, bg = parse(color), parse(card)
    if not c or not bg or lum(bg) < 0.5:
        return color
    lb = lum(bg) + 0.05
    k = 1.0
    while k > 0.2 and lb / (lum(tuple(x * k for x in c[:3])) + 0.05) < ratio:
        k -= 0.04
    if k >= 1.0:
        return color
    return hexc(tuple(int(round(x * k)) for x in c[:3]))


def resolve(tv, key, depth=0):
    """Valeur d'une variable du thème, en suivant les var(--autre)."""
    v = tv.get(key)
    if not isinstance(v, str) or depth > 5:
        return None
    m = re.match(r"^\s*var\(\s*--([\w-]+)\s*(?:,\s*(.+))?\)\s*$", v)
    if m:
        return resolve(tv, m.group(1), depth + 1) or (m.group(2) or "").strip() or None
    return v.strip()


def palette(theme_vars=None, mode="dark"):
    """Variables d'un thème HA (ou None) -> palette de couleurs opaques (hex).
    mode : « dark » ou « light » (pour les thèmes à deux modes et le thème par défaut)."""
    light = mode == "light"
    base = LIGHT if light else DEFAULTS
    tv = dict(theme_vars or {})
    modes = tv.get("modes")
    if isinstance(modes, dict):          # thème à deux modes : celui demandé
        if isinstance(modes.get(mode), dict):
            tv.update(modes[mode])
        elif not light and isinstance(modes.get("light"), dict):
            tv.update(modes["light"])    # thème sans mode sombre

    def col(*keys):
        for k in keys:
            c = parse(resolve(tv, k))
            if c:
                return c
        return parse(base[keys[0]])

    bg = blend(col("primary-background-color"), (250, 250, 250, 1.0) if light else (17, 17, 17, 1.0))
    card = blend(col("ha-card-background", "card-background-color"), bg)
    text = blend(col("primary-text-color"), card)
    sec = blend(col("secondary-text-color"), card)
    prim = blend(col("primary-color"), card)
    acc = blend(col("accent-color"), card)
    icon = blend(col("state-icon-color"), card)
    active = blend(col("state-active-color"), card)
    inact = blend(col("state-inactive-color"), card)
    fx = effects(tv, bg) if not light else {}
    rad = resolve(tv, "ha-card-border-radius") or base["ha-card-border-radius"]
    if not re.match(r"^\d{1,2}px$", rad):
        rad = DEFAULTS["ha-card-border-radius"]
    p = {"bg": hexc(bg), "card": hexc(card), "text": hexc(text), "sec": hexc(sec),
         "prim": hexc(prim), "prim_bg": hexc(blend(prim, card, 0.2)),
         "acc": hexc(acc), "acc_bg": hexc(blend(acc, card, 0.2)), "icon": hexc(icon), "inact": hexc(inact), "rad": rad,
         "line": hexc(blend(text, card, 0.12)), "soft": hexc(blend(text, card, 0.1)),
         "track": hexc(blend(text, card, 0.25)),
         "icon_bg": hexc(blend(icon, card, 0.2)), "inact_bg": hexc(blend(inact, card, 0.2)),
         "groups": {}, "fx": fx, "dark": lum(bg) < 0.5}
    for g, (keys, default) in GROUPS.items():
        c = None
        for k in keys:
            c = parse(resolve(tv, k))
            if c:
                break
        c = blend(c, card) if c else (parse(default) if default else active)
        p["groups"][g] = (hexc(c), hexc(blend(c, card, 0.2)))
    return p


# Valeurs CSS reprises telles quelles d'un thème : rien qui puisse sortir de la règle.
_SAFE = re.compile(r"^[\w\s#(),.%/-]{1,300}$")
_FILTER = re.compile(r"(?:blur|saturate|brightness|contrast)\(\s*[\d.]+(?:px|%)?\s*\)")


def _safe(v):
    v = (v or "").strip().rstrip(";").replace("!important", "").strip()
    return v if v and _SAFE.match(v) else None


def _block(cssx, sel):
    """Contenu de la première règle « sel { ... } » d'une feuille card-mod."""
    m = re.search(re.escape(sel) + r"\s*\{([^}]*)\}", cssx or "")
    return m.group(1) if m else ""


def _prop(block, name):
    m = re.search(r"(?:^|[;\s])" + re.escape(name) + r"\s*:\s*([^;]+);?", block or "")
    return m.group(1).strip() if m else None


def effects(tv, bg):
    """Effets du thème (variables HA et feuille card-mod des cartes), s'ils existent :
    fond translucide, bordure, ombre, flou d'arrière-plan, liseré et reflet."""
    fx = {}
    cm = resolve(tv, "card-mod-card") or ""
    if not isinstance(cm, str):
        cm = ""
    c = parse(resolve(tv, "ha-card-background") or resolve(tv, "card-background-color"))
    if c and c[3] < 1:
        fx["card_rgba"] = "rgba(%d,%d,%d,%.2f)" % (c[0], c[1], c[2], c[3])
    try:
        bw = int(re.match(r"^\s*(\d+)", resolve(tv, "ha-card-border-width") or "").group(1))
    except (AttributeError, ValueError):
        bw = None
    bc = parse(resolve(tv, "ha-card-border-color") or resolve(tv, "divider-color"))
    if bw:
        fx["border"] = "%dpx solid %s" % (min(bw, 4), "rgba(%d,%d,%d,%.2f)" % bc if bc else "rgba(255,255,255,.12)")
    sh = _safe(resolve(tv, "ha-card-box-shadow"))
    hc = _block(cm, "ha-card")
    sh = sh or _safe(_prop(hc, "box-shadow"))
    if sh and sh != "none":
        fx["shadow"] = sh
    flt = resolve(tv, "ha-card-backdrop-filter") or _prop(hc, "backdrop-filter") or ""
    f = " ".join(_FILTER.findall(flt))
    if f:
        fx["blur"] = f
    edge = _safe(_prop(_block(cm, "ha-card::after"), "background"))
    if edge and "gradient" in edge:
        fx["edge"] = edge
    refl = _safe(_prop(_block(cm, "ha-card::before"), "background"))
    if refl and "gradient" in refl:
        fx["reflect"] = refl
    return fx


def fx_css(p, cls):
    """Effets du thème : tous en type 3 ; bordure, fond et halo en type 2.
    Les cartes empilées dans un stack-in-card n'en ont pas (un seul fond, comme HA)."""
    fx = p.get("fx") or {}
    out = []
    top = ".card"
    # cartes empilées : sans effet propre (sélecteur simple, compris des anciens WebKit)
    reset = (".sic .card{border:0;box-shadow:none;-webkit-backdrop-filter:none;backdrop-filter:none}"
             ".sic .card:before,.sic .card:after{display:none}")
    if cls in ("t2", "t3"):
        # léger halo lumineux sur le fond de la page (calque fixe derrière le contenu), clair ou sombre
        pr = "%d,%d,%d" % tuple(parse(p["prim"])[:3])
        out.append("html{background:%s}body{background:transparent}"
                   "body:before{content:\"\";position:fixed;top:0;left:0;right:0;bottom:0;z-index:-1;pointer-events:none;"
                   "background:radial-gradient(ellipse 75%% 60%% at 10%% 0%%,%s,transparent 70%%),"
                   "radial-gradient(ellipse 65%% 55%% at 100%% 100%%,rgba(%s,%s),transparent 70%%),"
                   "radial-gradient(ellipse 50%% 40%% at 60%% 45%%,rgba(%s,.06),transparent 75%%)}" % (
                       p["bg"],
                       # sombre : lueur claire ; clair : lueur bleutée plus soutenue (sur fond blanc)
                       "rgba(190,210,240,.20)" if p.get("dark") else "rgba(120,160,230,.22)",
                       pr, ".20" if p.get("dark") else ".16", pr))
    # HA trace par défaut un trait de 1 px (couleur des séparateurs) autour des cartes,
    # quand le thème ne donne ni bordure ni liseré
    plain = cls in ("t2", "t3") and not fx.get("border") and not fx.get("edge")
    if plain:
        out.append("%s{border:1px solid %s}" % (top, p["line"]))
    if cls == "t2":
        if fx.get("border"):
            out.append("%s{border:%s}" % (top, fx["border"]))
        elif fx.get("edge"):
            # liseré en dégradé : approché par une bordure claire en haut à gauche
            out.append("%s{border:1px solid rgba(255,255,255,.06);border-top-color:rgba(255,255,255,.28);"
                       "border-left-color:rgba(255,255,255,.18)}" % top)
        return "".join(out) + (reset if fx or plain else "")
    if cls == "t1":
        # type 1 : pas d'effet de thème, seulement le trait fin de HA (clair comme sombre)
        return "%s{border:1px solid %s}" % (top, p["line"]) + reset
    if cls != "t3":
        return ""
    if not fx:
        return "".join(out) + reset
    if fx.get("card_rgba") and fx.get("blur"):
        out.append("%s{background:%s}" % (top, fx["card_rgba"]))
    if fx.get("blur"):
        out.append("%s{-webkit-backdrop-filter:%s;backdrop-filter:%s}" % (top, fx["blur"], fx["blur"]))
    if fx.get("border"):
        out.append("%s{border:%s}" % (top, fx["border"]))
    if fx.get("shadow"):
        out.append("%s{box-shadow:%s}" % (top, fx["shadow"]))
    if fx.get("edge") or fx.get("reflect"):
        out.append("%s{position:relative}" % top)
    if fx.get("edge"):
        out.append("%s:after{content:\"\";position:absolute;top:0;left:0;right:0;bottom:0;border-radius:inherit;"
                   "padding:1px;background:%s;-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);"
                   "-webkit-mask-composite:xor;mask-composite:exclude;pointer-events:none}" % (top, fx["edge"]))
    if fx.get("reflect"):
        out.append("%s:before{content:\"\";position:absolute;top:0;left:0;right:0;bottom:0;border-radius:inherit;"
                   "background:%s;pointer-events:none}" % (top, fx["reflect"]))
    return "".join(out) + reset


def _mc_colors():
    """Couleurs « mushroom » (option color des cartes), lues dans s.css."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "s.css"),
                  encoding="utf-8") as f:
            return dict(re.findall(r"\.mc-([a-z-]+) \.ic \{ color: (#[0-9a-fA-F]{6})", f.read()))
    except OSError:
        return {}


MC = _mc_colors()


def light_fix(p):
    """Thème clair : fonds codés en sombre dans s.css (cartes, pastilles colorées, onglets)."""
    card = parse(p["card"])
    if not card or lum(card) < 0.5:
        return ""
    out = [".tile.rt,.tile.rt.on{background:%(card)s}.tab{color:%(sec)s}.tab.cur{color:%(text)s}"
           ".btn,.btn.cv{color:%(text)s}" % p]
    for n, c in sorted(MC.items()):
        if n in ("primary", "accent"):
            continue
        out.append(".ti.mc-%s{background:%s!important}" % (n, hexc(blend(parse(c), card, 0.2))))
    return "".join(out)


BG_SIZES = (960, 1600, 2048)       # côté le plus long de l'image de fond, selon la largeur d'écran


def bg_css(p, name, bg):
    """Image de fond d'une vue (type 3), comme HA : la couleur de fond de la page est posée par
    dessus l'image, avec une transparence de (100 - opacité) %. Trois tailles d'image,
    choisies par la largeur de l'écran (l'image est réduite par le relais /<nom>/img)."""
    r, g, b = parse(p["bg"])[:3]
    a = round(1 - bg["opacity"] / 100.0, 2)
    veil = "linear-gradient(rgba(%d,%d,%d,%s),rgba(%d,%d,%d,%s))" % (r, g, b, a, r, g, b, a)
    pos = bg.get("alignment")
    pos = pos if pos in ("top left", "top center", "top right", "center left", "center",
                         "center right", "bottom left", "bottom center", "bottom right") else "center"
    size = bg.get("size") if bg.get("size") in ("cover", "contain", "auto") else "cover"
    rep = "repeat" if bg.get("repeat") == "repeat" else "no-repeat"
    att = "fixed" if bg.get("attachment") == "fixed" else "scroll"

    def layers(w):
        return "background-image:%s,url(/%s/img?i=%s&w=%d)" % (veil, name, bg["key"], w)

    return ("html{background-color:%s;%s;background-size:auto,%s;background-position:0 0,%s;"
            "background-repeat:repeat,%s;background-attachment:%s,%s}"
            "@media (min-width:901px){html{%s}}@media (min-width:1401px){html{%s}}"
            % (p["bg"], layers(BG_SIZES[0]), size, pos, rep, att, att,
               layers(BG_SIZES[1]), layers(BG_SIZES[2])))


def css(p, cls):
    """Palette -> règles CSS (insérées dans la page, après les feuilles de style)."""
    d = dict(p)
    common = (
        ".cam{background:#000}"
        # image de carte picture : arrondie elle-même (le vieux WebKit ne la découpe pas
        # selon les coins arrondis de la carte)
        ".pic .pi,.pic .pb{border-radius:%(rad)s}"
        ".btn{background:%(soft)s;color:%(text)s}.subs .badge{background:%(soft)s}"
        ".sic .hs>.card{background:%(soft)s}"
        ".hd,.hd .ic,.rt .ts,.btn.cv .ic{color:%(text)s}"
        ".gi.on .gs{color:%(text)s}"
        ".nb .ts{color:%(sec)s}.row .btn.lk{background:none;color:%(prim)s}"
        ".tg{background:%(track)s}.tg.on{background:%(prim)s}"
        # couleurs « primary » / « accent » d'une carte (option color) : celles du thème
        ".mc-primary .ic{color:%(prim)s!important}.ti.mc-primary{background:%(prim_bg)s!important}"
        ".mc-accent .ic{color:%(acc)s!important}.ti.mc-accent{background:%(acc_bg)s!important}"
    ) % d
    if cls == "t1":
        out = [(
            "html,body{background:%(bg)s}body{color:%(text)s}"
            ".card{background:%(card)s;border-radius:%(rad)s}"
            ".badge{background:%(card)s}"
            ".card h2,.sub,.big .tn,.cd,.bn,.tab,.sp.nodata,.mm,"
            ".w2,.wl,.fn,.fl,.lv,.big .u,.sl .sx{color:%(sec)s}"
            ".rt .tn,.rt.on .tn,.tile .tn,.tab.cur,.card .ch,.gn,.gauge .tn,.sec{color:%(text)s}"
            ".sec{border-top-color:%(line)s}"
            ".row{border-bottom-color:%(line)s}hr{border-top-color:%(line)s}"
            ".fcs{border-top-color:%(line)s}"
            "#tabs.bot{background:%(card)s;border-top-color:%(line)s}"
            ".tab.cur{border-bottom-color:%(prim)s}#tabs.bot .tab.cur{border-top-color:%(prim)s}"
            ".ga .gb{stroke:%(track)s}.ga .gv{stroke:%(prim)s}.bar{background:%(track)s}"
            ".bar i{background:%(prim)s}"
            ".ic{color:%(inact)s}.rt .ti{background:%(inact_bg)s}"
            ".dc-def .ic{color:%(icon)s}.dc-def .ti,.dc-def.on .ti{background:%(icon_bg)s}"
            ".badge.dc-def .ic{color:%(prim)s}"
        ) % d]
        for g, (c, cbg) in sorted(p["groups"].items()):
            out.append(".dc-%s.on .ic{color:%s}.dc-%s.on .ti{background:%s}" % (g, c, g, cbg))
        return "".join(out) + common + light_fix(p) + fx_css(p, cls)
    out = [(
        ":root{--bg:%(bg)s;--card:%(card)s;--line:%(line)s;--text:%(text)s;"
        "--muted:%(sec)s;--accent:%(prim)s;--radius:%(rad)s}"
        ".dc-def{--c:%(icon)s}"
        ".rt .ti{color:%(inact)s}.rt .ti:before{background:%(inact)s;opacity:.2}"
        ".rt.dc-def .ti,.rt.dc-def .ti .ic{color:%(icon)s}"
        ".rt.dc-def .ti:before{background:%(icon)s;opacity:.2}"
        ".dc-def .ri,.dc-def .gic,.ri.dc-def,.gi.dc-def .gic{color:%(icon)s}"
        ".badge.dc-def .ic{color:%(prim)s}"
    ) % d]
    for g, (c, _) in sorted(p["groups"].items()):
        out.append(".dc-%s{--c:%s}" % (g, c))
    return "".join(out) + common + light_fix(p) + fx_css(p, cls)
