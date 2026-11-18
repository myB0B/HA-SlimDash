"""Non-régression du rendu SlimDash : « photo » des mesures de chaque élément.

    python dev/snapshot.py save     enregistre la référence dans dev/snapshots/
    python dev/snapshot.py check    compare le rendu actuel à la référence

Le script lance le faux Home Assistant (données figées), SlimDash, puis Edge ou Chrome
sans fenêtre (600 x 1024). Pour chaque classe d'appareil et chaque vue de test, il relève
la position, la taille, la police et les couleurs de tous les éléments de la page.
Une ligne par élément : un écart = une ligne différente. Aucune dépendance en plus d'aiohttp.
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile

from aiohttp import ClientSession

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SNAP = os.path.join(HERE, "snapshots")
FIXTURES = ["demo_dashboard.json", "fixture_lot3.json"]
CLASSES = ["t1", "t2", "t3"]
TYPE = {"t1": "1", "t2": "2", "t3": "3"}     # &type= de l'adresse
MOCK_PORT, SD_PORT = 8134, 8136
CDP_PORT = 9300 + os.getpid() % 500     # un port par passage : jamais un navigateur d'un passage précédent
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "/usr/bin/chromium", "/usr/bin/google-chrome"]

# Relevé fait dans la page. Le bandeau du haut (heure) est ignoré.
EXTRACT = r"""
(function () {
  var out = [], R = Math.round;
  var els = document.querySelectorAll('#tabs, #tabs *, #main, #main *');
  for (var i = 0; i < els.length; i++) {
    var e = els[i], t = e.tagName.toLowerCase();
    if (t === 'symbol' || t === 'path' || t === 'use' || t === 'rect' || t === 'polyline' ||
        t === 'polygon' || t === 'g' || t === 'circle' || t === 'b' || t === 'i' && !e.className) { continue; }
    if (e.closest && e.closest('svg') && t !== 'svg') { continue; }
    var r = e.getBoundingClientRect(), cs = getComputedStyle(e);
    if (!r.width && !r.height) { continue; }
    var cl = (e.getAttribute('class') || '').replace(/\s+/g, '.');
    out.push(t + (cl ? '.' + cl : '') + ' ' + R(r.left) + ',' + R(r.top + scrollY) + ' ' + R(r.width) + 'x' + R(r.height) +
      ' f' + parseFloat(cs.fontSize) + '/' + cs.fontWeight + ' ' + cs.color.replace(/ /g, '') +
      ' bg' + cs.backgroundColor.replace(/ /g, '') + ' r' + cs.borderTopLeftRadius);
  }
  return out.join('\n');
})()
"""


async def wait_http(sess, url, tries=60):
    for _ in range(tries):
        try:
            async with sess.get(url) as r:
                await r.read()
                return
        except Exception:
            await asyncio.sleep(0.25)
    raise RuntimeError("pas de réponse de %s" % url)


class Tab:
    def __init__(self, ws):
        self.ws, self.n = ws, 0

    async def cmd(self, method, **params):
        self.n += 1
        mid = self.n
        await self.ws.send_str(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            d = json.loads((await self.ws.receive()).data)
            if d.get("id") == mid:
                if "error" in d:
                    raise RuntimeError(d["error"])
                return d.get("result") or {}


async def measure(views):
    tmp = tempfile.mkdtemp(prefix="slimdash-snap-")
    fixture = os.path.join(tmp, "fixture.json")
    with open(fixture, "w", encoding="utf-8") as f:
        json.dump({"views": views}, f)
    options = os.path.join(tmp, "options.json")
    with open(options, "w", encoding="utf-8") as f:
        json.dump({"dashboards": [{"name": "t", "dashboard": "x",
                                   "views": ",".join(str(i) for i in range(len(views))),
                                   "tabs_bottom": True, "refresh": 0, "device": "auto"}],
                   "allowed_networks": ["127.0.0.0/8"], "log_level": "warning", "theme": "test"}, f)
    browser = next((b for b in BROWSERS if os.path.exists(b)), None)
    if not browser:
        raise SystemExit("Edge ou Chrome introuvable")
    env = dict(os.environ, MOCK_FIXTURE=fixture, MOCK_PORT=str(MOCK_PORT), MOCK_FIXED="1", MOCK_FRIGATE="",
               HA_URL="http://127.0.0.1:%d" % MOCK_PORT, HA_TOKEN="x",
               SLIMDASH_OPTIONS=options, SLIMDASH_PORT=str(SD_PORT))
    quiet = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs = [subprocess.Popen([sys.executable, os.path.join(HERE, "mock_ha.py")], env=env, **quiet)]
    result = {}
    try:
        await asyncio.sleep(1.5)
        procs.append(subprocess.Popen(
            [sys.executable, os.path.join(ROOT, "slimdash", "app", "slimdash.py")], env=env, **quiet))
        procs.append(subprocess.Popen(
            [browser, "--headless=new", "--remote-debugging-port=%d" % CDP_PORT,
             "--user-data-dir=" + os.path.join(tmp, "profil"), "--no-first-run",
             "--hide-scrollbars", "--window-size=600,1024", "about:blank"], **quiet))
        base = "http://127.0.0.1:%d/t" % SD_PORT
        async with ClientSession() as sess:
            await wait_http(sess, "http://127.0.0.1:%d/diag" % SD_PORT)
            await wait_http(sess, "http://127.0.0.1:%d/json/version" % CDP_PORT)
            await asyncio.sleep(2)
            # 1er passage : prépare chaque rendu (historique, prévisions, templates)
            for cls in CLASSES:
                async with sess.get("%s?type=%s&view=0" % (base, TYPE[cls])) as r:
                    await r.read()
            await asyncio.sleep(4)
            async with sess.put("http://127.0.0.1:%d/json/new?about:blank" % CDP_PORT) as r:
                info = await r.json()
            async with sess.ws_connect(info["webSocketDebuggerUrl"], max_msg_size=0) as ws:
                tab = Tab(ws)
                await tab.cmd("Emulation.setDeviceMetricsOverride", width=600, height=1024,
                              deviceScaleFactor=1, mobile=False)
                for cls in CLASSES:
                    for v in range(len(views)):
                        await tab.cmd("Page.navigate", url="%s?type=%s&view=%d" % (base, TYPE[cls], v))
                        # on attend que la page ne bouge plus (images, templates, courbes)
                        prev, text = None, ""
                        for _ in range(12):
                            await asyncio.sleep(1.2)
                            res = await tab.cmd("Runtime.evaluate", expression=EXTRACT, returnByValue=True)
                            text = res["result"].get("value") or ""
                            ok = await tab.cmd("Runtime.evaluate", returnByValue=True, expression=(
                                "[].every.call(document.images,function(i){return i.complete&&i.naturalWidth>0})"))
                            if text and text == prev and ok["result"].get("value"):
                                break
                            prev = text
                        result["%s-%d" % (cls, v)] = text
                await tab.cmd("Page.navigate", url="about:blank")
            # ferme le navigateur et ses processus (sinon ils gardent des connexions ouvertes)
            try:
                async with sess.get("http://127.0.0.1:%d/json/version" % CDP_PORT) as r:
                    bws = (await r.json())["webSocketDebuggerUrl"]
                async with sess.ws_connect(bws) as ws:
                    await ws.send_str(json.dumps({"id": 1, "method": "Browser.close"}))
                    await asyncio.sleep(1)
            except Exception:
                pass
    finally:
        for p in reversed(procs):
            p.terminate()
    return result


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    views = []
    for name in FIXTURES:
        with open(os.path.join(HERE, name), encoding="utf-8") as f:
            cfg = json.load(f)
        views.extend((cfg.get("config") or cfg.get("data", {}).get("config") or cfg).get("views") or [])
    result = asyncio.run(measure(views))
    os.makedirs(SNAP, exist_ok=True)
    bad = 0
    for key, text in sorted(result.items()):
        path = os.path.join(SNAP, key + ".txt")
        if mode == "save":
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text + "\n")
            print("%-18s %4d éléments" % (key, text.count("\n") + 1))
            continue
        try:
            with open(path, encoding="utf-8") as f:
                ref = f.read().rstrip("\n").split("\n")
        except FileNotFoundError:
            print("%-18s pas de référence (lancer « save »)" % key)
            bad += 1
            continue
        cur = text.split("\n")
        diffs = [(i, a, b) for i, (a, b) in enumerate(zip(ref, cur)) if a != b]
        if len(ref) != len(cur):
            diffs.append((min(len(ref), len(cur)), "%d éléments" % len(ref), "%d éléments" % len(cur)))
        if diffs:
            bad += 1
            print("%-18s %d écart(s)" % (key, len(diffs)))
            for i, a, b in diffs[:6]:
                print("    #%d\n      réf : %s\n      act : %s" % (i, a, b))
        else:
            print("%-18s identique (%d éléments)" % (key, len(cur)))
    if mode != "save":
        print("\n%s" % ("Aucun écart." if not bad else "%d vue(s) avec écarts." % bad))
        sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
