"""SlimDash - colours taken from the Home Assistant theme.

The HA theme (CSS variables) is reduced to a small palette of opaque colours,
then translated into a few CSS rules specific to each device type:
explicit rules for type 1 (no CSS variables), variables for the others.
Transparencies are computed here: no costly effect on the browser side.
"""
import os
import re

# Home Assistant default dark theme.
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
# Home Assistant default light theme ("light" mode).
LIGHT = dict(DEFAULTS, **{
    "primary-background-color": "#fafafa",
    "ha-card-background": "#ffffff",
    "primary-text-color": "#212121",
    "secondary-text-color": "#727272",
})
# SlimDash colour group -> (possible HA variables, default HA colour; None = "active")
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
    """Simple CSS colour -> (r, g, b, a) or None."""
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
    """fg laid over bg (opaque) with the transparency of fg, or alpha if given."""
    a = fg[3] if alpha is None else alpha
    return tuple(int(round(fg[i] * a + bg[i] * (1 - a))) for i in range(3)) + (1.0,)


def hexc(c):
    return "#%02x%02x%02x" % (c[0], c[1], c[2])


def lum(c):
    """Relative luminance (WCAG) of a colour (r, g, b)."""
    def ch(x):
        x = x / 255.0
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])


def readable(color, card, ratio=3.0):
    """On a light background, darkens a colour that is too light (same hue) until the
    contrast is sufficient; on a dark background, the colour is returned as is."""
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
    """Value of a theme variable, following var(--other)."""
    v = tv.get(key)
    if not isinstance(v, str) or depth > 5:
        return None
    m = re.match(r"^\s*var\(\s*--([\w-]+)\s*(?:,\s*(.+))?\)\s*$", v)
    if m:
        return resolve(tv, m.group(1), depth + 1) or (m.group(2) or "").strip() or None
    return v.strip()


def palette(theme_vars=None, mode="dark"):
    """Variables of an HA theme (or None) -> palette of opaque colours (hex).
    mode: "dark" or "light" (for two-mode themes and the default theme)."""
    light = mode == "light"
    base = LIGHT if light else DEFAULTS
    tv = dict(theme_vars or {})
    modes = tv.get("modes")
    if isinstance(modes, dict):          # two-mode theme: the requested one
        if isinstance(modes.get(mode), dict):
            tv.update(modes[mode])
        elif not light and isinstance(modes.get("light"), dict):
            tv.update(modes["light"])    # theme without a dark mode

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


# CSS values taken as is from a theme: nothing that could escape the rule.
_SAFE = re.compile(r"^[\w\s#(),.%/-]{1,300}$")
_FILTER = re.compile(r"(?:blur|saturate|brightness|contrast)\(\s*[\d.]+(?:px|%)?\s*\)")


def _safe(v):
    v = (v or "").strip().rstrip(";").replace("!important", "").strip()
    return v if v and _SAFE.match(v) else None


def _block(cssx, sel):
    """Content of the first rule "sel { ... }" of a card-mod style sheet."""
    m = re.search(re.escape(sel) + r"\s*\{([^}]*)\}", cssx or "")
    return m.group(1) if m else ""


def _prop(block, name):
    m = re.search(r"(?:^|[;\s])" + re.escape(name) + r"\s*:\s*([^;]+);?", block or "")
    return m.group(1).strip() if m else None


def effects(tv, bg):
    """Theme effects (HA variables and card-mod style sheet of the cards), if any:
    translucent background, border, shadow, backdrop blur, edge highlight and reflection."""
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
    """Theme effects: all of them on type 3; border, background and glow on type 2.
    Cards stacked in a stack-in-card have none (a single background, like HA)."""
    fx = p.get("fx") or {}
    out = []
    top = ".card"
    # stacked cards: no effect of their own (simple selector, understood by old WebKit)
    reset = (".sic .card{border:0;box-shadow:none;-webkit-backdrop-filter:none;backdrop-filter:none}"
             ".sic .card:before,.sic .card:after{display:none}")
    if cls in ("t2", "t3"):
        # slight glow on the page background (fixed layer behind the content), light or dark
        pr = "%d,%d,%d" % tuple(parse(p["prim"])[:3])
        out.append("html{background:%s}body{background:transparent}"
                   "body:before{content:\"\";position:fixed;top:0;left:0;right:0;bottom:0;z-index:-1;pointer-events:none;"
                   "background:radial-gradient(ellipse 75%% 60%% at 10%% 0%%,%s,transparent 70%%),"
                   "radial-gradient(ellipse 65%% 55%% at 100%% 100%%,rgba(%s,%s),transparent 70%%),"
                   "radial-gradient(ellipse 50%% 40%% at 60%% 45%%,rgba(%s,.06),transparent 75%%)}" % (
                       p["bg"],
                       # dark: light glow; light: stronger bluish glow (on a white background)
                       "rgba(190,210,240,.20)" if p.get("dark") else "rgba(120,160,230,.22)",
                       pr, ".20" if p.get("dark") else ".16", pr))
    # HA draws a 1 px line by default (separator colour) around the cards,
    # when the theme gives neither border nor edge highlight
    plain = cls in ("t2", "t3") and not fx.get("border") and not fx.get("edge")
    if plain:
        out.append("%s{border:1px solid %s}" % (top, p["line"]))
    if cls == "t2":
        if fx.get("border"):
            out.append("%s{border:%s}" % (top, fx["border"]))
        elif fx.get("edge"):
            # gradient edge highlight: approximated by a light border at the top left
            out.append("%s{border:1px solid rgba(255,255,255,.06);border-top-color:rgba(255,255,255,.28);"
                       "border-left-color:rgba(255,255,255,.18)}" % top)
        return "".join(out) + (reset if fx or plain else "")
    if cls == "t1":
        # type 1: no theme effect, only the thin HA line (light as well as dark)
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
    """"mushroom" colours (colour option of the cards), read from s.css."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "s.css"),
                  encoding="utf-8") as f:
            return dict(re.findall(r"\.mc-([a-z-]+) \.ic \{ color: (#[0-9a-fA-F]{6})", f.read()))
    except OSError:
        return {}


MC = _mc_colors()


def light_fix(p):
    """Light theme: backgrounds coded dark in s.css (cards, coloured dots, tabs)."""
    card = parse(p["card"])
    if not card or lum(card) < 0.5:
        return ""
    out = [".tile.rt,.tile.rt.on{background:%(card)s}.tab{color:%(sec)s}.tab.cur{color:%(text)s}"
           ".btn,.btn.cv{color:%(text)s}"
           ".tile .btn.cv,.tile .btn.cm:not(.on){background:rgba(158,158,158,.2)}" % p]      # grey like HA
    for n, c in sorted(MC.items()):
        if n in ("primary", "accent"):
            continue
        out.append(".ti.mc-%s{background:%s!important}" % (n, hexc(blend(parse(c), card, 0.2))))
    return "".join(out)


BG_SIZES = (960, 1600, 2048)       # longest side of the background image, depending on the screen width


def bg_css(p, name, bg):
    """Background image of a view (type 3), like HA: the page background colour is laid over
    the image, with a transparency of (100 - opacity) %. Three image sizes,
    chosen by the screen width (the image is shrunk by the /<name>/img relay)."""
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
    """Palette -> CSS rules (inserted in the page, after the style sheets)."""
    d = dict(p)
    common = (
        ".cam{background:#000}"
        # picture card image: rounded itself (old WebKit does not clip it
        # to the rounded corners of the card)
        ".pic .pi,.pic .pb{border-radius:%(rad)s}"
        ".btn{background:%(soft)s;color:%(text)s}.subs .badge{background:%(soft)s}"
        ".sic .hs>.card{background:%(soft)s}"
        ".hd,.hd .ic,.rt .ts,.btn.cv .ic{color:%(text)s}"
        ".gi.on .gs{color:%(text)s}"
        ".nb .ts{color:%(sec)s}.row .btn.lk{background:none;color:%(prim)s}"
        ".tg{background:%(track)s}.tg.on{background:%(prim)s}"
        # "primary" / "accent" colours of a card (colour option): those of the theme
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
