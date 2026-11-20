"""Fake Home Assistant (WebSocket + camera) to test SlimDash on the PC, without a token.

    python dev/mock_ha.py            (listens on port 8124; MOCK_FIXTURE = Lovelace config)
    set HA_URL=http://127.0.0.1:8124 & set HA_TOKEN=x & python slimdash/app/slimdash.py
"""
import asyncio
import json
import math
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone

from aiohttp import web

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.environ.get("MOCK_FIXTURE", os.path.join(HERE, "demo_dashboard.json"))
ICON = os.path.join(HERE, "..", "slimdash", "app", "static", "icon.png")
FIXED = bool(os.environ.get("MOCK_FIXED"))     # données figées (dev/snapshot.py)


def S(state, **attrs):
    return {"s": state, "a": attrs}


STATES = {
    "weather.home": S("partlycloudy", friendly_name="Home", temperature=12.6,
                         temperature_unit="°C", humidity=90, wind_speed=11.2, wind_speed_unit="km/h"),
    "sensor.environnement_pression": S("1018.4", unit_of_measurement="hPa", friendly_name="Pression",
                                       device_class="pressure"),
    "sensor.jardin_th_exterieur_humidite": S("90.0", unit_of_measurement="%", friendly_name="Humidité ext.",
                                             device_class="humidity"),
    "sensor.jardin_th_exterieur_temperature": S("11.7", unit_of_measurement="°C",
                                                friendly_name="Température ext.", device_class="temperature"),
    "sensor.maison_temperature_moyenne": S("22.1", unit_of_measurement="°C", friendly_name="Température maison",
                                           device_class="temperature"),
    "sensor.maison_humidite_moyenne": S("56.1", unit_of_measurement="%", friendly_name="Humidité maison",
                                        device_class="humidity"),
    "sensor.izypower_cloud_maison_32028_puissance_pv": S("0", unit_of_measurement="W", friendly_name="Puissance PV",
                                                         device_class="power"),
    "sensor.portail_portail_etat": dict(S("fermé", friendly_name="Portail État"), lc=time.time() - 1800),
    "sensor.linky_teleinfo_linky_w_instantane": S("742.6", unit_of_measurement="W", friendly_name="Linky",
                                                  device_class="power"),
    "input_boolean.slimdash_demo_lampe": S("off", friendly_name="Démo lampe"),
    "input_boolean.slimdash_demo_prise": S("on", friendly_name="Démo prise"),
    "input_button.slimdash_demo_bouton": S("2026-11-12T10:00:00+00:00", friendly_name="Démo bouton"),
    "binary_sensor.radar_bureau_presence": S("on", friendly_name="Présence bureau", device_class="occupancy"),
    "binary_sensor.radar_salon_presence": S("off", friendly_name="Présence salon", device_class="occupancy"),
    "binary_sensor.radar_cuisine_presence": S("off", friendly_name="Présence cuisine", device_class="occupancy"),
    "camera.portail": S("idle", friendly_name="Portail"),
    "cover.volet_bureau": S("closed", friendly_name="Volet Bureau", device_class="shutter", supported_features=11),
    "button.portail_portail_pieton": S("unknown", friendly_name="Portail Piéton", icon="mdi:walk"),
    "button.portail_portail_voiture": S("unknown", friendly_name="Portail Voiture", icon="mdi:car"),
    "button.portail_portail_portillon": S("unknown", friendly_name="Portillon", icon="mdi:gate"),
    "camera.facade": S("idle", friendly_name="Façade"),
    "camera.jardin": S("idle", friendly_name="Jardin"),
    "camera.sonnette": S("idle", friendly_name="Sonnette"),
    "light.lampe_bureau": S("on", friendly_name="Lampe Bureau", brightness=3),
    "light.lampe_bleue": S("on", friendly_name="Lampe bleue", brightness=200, rgb_color=[0, 80, 255]),
    "light.lampe_simple": S("on", friendly_name="Lampe sans couleur"),
    "light.lampe_salon": S("on", friendly_name="Lampe salon", brightness=180, color_temp_kelvin=3000,
                           min_color_temp_kelvin=2000, max_color_temp_kelvin=6500,
                           supported_color_modes=["color_temp", "hs"], rgb_color=[255, 180, 107]),
    "number.zone_1_duree": S("15.0", friendly_name="Zone 1 Durée manuelle", min=1, max=360, step=1, mode="box", unit_of_measurement="min"),
    "number.grassy_tonte": S("2.5", friendly_name="Grassy Durée de tonte lundi", min=0, max=24, step=0.1, mode="box", unit_of_measurement="h"),
    "input_number.score": S("6.5", friendly_name="Score arrosage", min=0, max=10, step=0.5, mode="slider"),
    "time.grassy_depart": S("09:30:00", friendly_name="Grassy Départ lundi"),
    "select.commandes": S("Sélectionner une action", friendly_name="Commandes machine", options=["Sélectionner une action", "Display On", "Display Off", "Reboot"]),
    "input_text.message": S("Bonjour", friendly_name="Message", max=100, mode="text"),
    "input_datetime.reveil": S("2026-11-14 07:30:00", friendly_name="Réveil", has_date=True, has_time=True),
    "switch.adguard_filtrage": S("on", friendly_name="AdGuard Home Filtrage"),
    "switch.adguard_filtrage_2": S("off", friendly_name="AdGuard Home Filtrage 2"),
    "sensor.dernier_demarrage": S("2026-10-09T04:49:37+00:00", friendly_name="System Monitor Temps de fonctionnement", device_class="uptime"),
    "sensor.derniere_sauvegarde": S("2026-11-13T06:00:00+00:00", friendly_name="Dernière sauvegarde", device_class="timestamp"),
    "light.lampe_eteinte": S("off", friendly_name="Lampe éteinte", supported_color_modes=["color_temp"]),
    "light.lampe_salon": S("on", friendly_name="Lampe Salon", brightness=128, color_mode="color_temp",
                           color_temp_kelvin=3000, rgb_color=[255, 180, 107],
                           min_color_temp_kelvin=2000, max_color_temp_kelvin=6500,
                           supported_color_modes=["color_temp", "hs"]),
}


def render_tpl(t):
    if '{% if' in t and 'green' in t:   # couleur d'icône mushroom (simplifié)
        return 'green'
    t = re.sub(r"\{\{\s*states\('([^']+)'\)[^}]*\}\}",
               lambda m: str((STATES.get(m.group(1)) or {}).get("s", "?")), t)
    return re.sub(r"\{[{%].*?[}%]\}", "", t)


def fake_series(eid, start, end, n=200):
    base = float((STATES.get(eid) or {}).get("s") or 0) if re.match(r"^-?[\d.]+$", str((STATES.get(eid) or {}).get("s"))) else 0
    out = []
    for i in range(n):
        t = start + (end - start) * i / (n - 1)
        out.append((t, base * (1 + 0.15 * math.sin(i / 12.0)) + (0 if FIXED else random.uniform(-0.5, 0.5))))
    return out


async def ws_handler(request):
    ws = web.WebSocketResponse(max_msg_size=0)
    await ws.prepare(request)
    await ws.send_json({"type": "auth_required", "ha_version": "mock"})
    await ws.receive_json()
    await ws.send_json({"type": "auth_ok", "ha_version": "mock"})
    subs = {}

    async def push(eid):
        for sid, ids in subs.items():
            if eid in ids:
                await ws.send_json({"id": sid, "type": "event",
                                    "event": {"c": {eid: {"+": {"s": STATES[eid]["s"], "a": STATES[eid]["a"]}}}}})

    async def ticker():
        while True:
            await asyncio.sleep(3)
            eid = "sensor.linky_teleinfo_linky_w_instantane"
            STATES[eid]["s"] = str(random.randint(300, 4000))
            await push(eid)

    tick = asyncio.create_task(asyncio.sleep(0) if FIXED else ticker())
    ok = lambda mid, res=None: ws.send_json({"id": mid, "type": "result", "success": True, "result": res})
    try:
        async for m in ws:
            d = json.loads(m.data)
            t, mid = d.get("type"), d.get("id")
            if t == "lovelace/config":
                with open(FIXTURE, encoding="utf-8") as f:
                    await ok(mid, json.load(f))
            elif t == "subscribe_entities":
                ids = d.get("entity_ids") or list(STATES)
                subs[mid] = set(ids)
                await ok(mid)
                await ws.send_json({"id": mid, "type": "event", "event": {"a": {
                    e: STATES.get(e, {"s": "unavailable", "a": {}}) for e in ids}}})
            elif t == "weather/subscribe_forecast":
                await ok(mid)
                now = datetime.now(timezone.utc)
                conds = ["rainy", "cloudy", "partlycloudy", "sunny", "pouring"]
                await ws.send_json({"id": mid, "type": "event", "event": {"type": "daily", "forecast": [
                    {"datetime": (now + timedelta(days=i)).isoformat(), "condition": conds[i],
                     "temperature": 14 + i, "templow": 5 + i} for i in range(5)]}})
            elif t == "render_template":
                await ok(mid)
                await ws.send_json({"id": mid, "type": "event", "event": {"result": render_tpl(d["template"])}})
            elif t == "history/history_during_period":
                st = datetime.fromisoformat(d["start_time"]).timestamp()
                en = datetime.fromisoformat(d["end_time"]).timestamp()
                await ok(mid, {e: [{"s": "%.2f" % v, "lu": ts} for ts, v in fake_series(e, st, en)]
                               for e in d["entity_ids"]})
            elif t == "energy/get_prefs":
                await ok(mid, {"energy_sources": [
                    {"type": "solar", "stat_energy_from": "sensor.prod_kwh"},
                    {"type": "grid", "stat_energy_from": "sensor.linky_hp_wh", "stat_energy_to": None},
                    {"type": "grid", "stat_energy_from": "sensor.linky_hc_wh", "stat_energy_to": None}]})
            elif t == "recorder/statistics_during_period" and "change" in (d.get("types") or []):
                # énergie du jour : 6 kWh solaires, 2 + 1,5 kWh réseau -> 63 %
                per = {"sensor.prod_kwh": 6.0, "sensor.linky_hp_wh": 2.0, "sensor.linky_hc_wh": 1.5}
                await ok(mid, {e: [{"start": 0, "change": per.get(e, 0) / 2}] * 2 for e in d["statistic_ids"]})
            elif t == "recorder/statistics_during_period":
                st = datetime.fromisoformat(d["start_time"]).timestamp()
                en = datetime.fromisoformat(d["end_time"]).timestamp()
                await ok(mid, {e: [{"start": int(ts * 1000), "mean": v} for ts, v in fake_series(e, st, en, 168)]
                               for e in d["statistic_ids"]})
            elif t == "config/entity_registry/get_entries":
                await ok(mid, {e: dict({"device_id": None, "area_id": None, "name": None, "original_name": None,
                                        "options": {"sensor": {"suggested_display_precision": 0}} if "linky" in e else {}},
                                       **FRIGATE_REG.get(e, {}))
                               for e in d["entity_ids"]})
            elif t == "config_entries/get":
                # intégration Frigate : le titre de l'entrée donne host:port (MOCK_FRIGATE, vide = absente)
                fr = os.environ.get("MOCK_FRIGATE", "192.168.1.10:5000")
                await ok(mid, [{"domain": "frigate", "state": "loaded", "title": fr}] if fr else [])
            elif t in ("config/device_registry/list", "config/area_registry/list"):
                await ok(mid, [])
            elif t == "frontend/get_themes":
                await ok(mid, {"default_theme": "default", "themes": {"test": {
                    "primary-background-color": "#2c2c2e", "ha-card-background": "rgba(0, 0, 0, 0.7)",
                    "card-background-color": "var(--secondary-background-color)",
                    "primary-text-color": "#FFF", "secondary-text-color": "#d3d3d3",
                    "primary-color": "#009ac7", "ha-card-border-radius": "8px", "ha-card-border-width": "0",
                    "card-mod-card": "ha-card {\n  position: relative;\n  overflow: hidden;\n  backdrop-filter: var(--fc-card-blur, blur(4px) saturate(110%));\n}\nha-card::after {\n  content: '';\n  position: absolute;\n  inset: 0;\n  padding: 1px;\n  background: linear-gradient(150deg, white, 1%, transparent);\n  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);\n  -webkit-mask-composite: xor;\n  mask-composite: exclude;\n}\nha-card::before {\n  content: '';\n  position: absolute;\n  inset: 0;\n  background: radial-gradient(120% 90% at 0% 0%, rgba(190, 210, 240, 0.20) 0%, transparent 95%);\n}\n"},
                    "clair": {"primary-background-color": "#f0f0f0", "card-background-color": "#ffffff",
                              "primary-text-color": "#212121", "secondary-text-color": "#727272",
                              "primary-color": "#03a9f4"},
                    "duo": {"primary-color": "#e91e63", "modes": {
                        "light": {"primary-background-color": "#fce4ec", "card-background-color": "#ffffff",
                                  "primary-text-color": "#3e2723"},
                        "dark": {"primary-background-color": "#1a0d12", "card-background-color": "#2b1a20",
                                 "primary-text-color": "#f8bbd0"}}}}})
            elif t == "get_config":
                await ok(mid, {"language": "fr"})
            elif t == "frontend/get_translations":
                await ok(mid, {"resources": {
                    "component.switch.entity_component._.state.on": "Activé",
                    "component.input_boolean.entity_component._.state.on": "Activé",
                    "component.input_boolean.entity_component._.state.off": "Désactivé",
                    "component.binary_sensor.entity_component.occupancy.state.on": "Détecté",
                    "component.binary_sensor.entity_component.occupancy.state.off": "Non détecté",
                    "component.cover.entity_component._.state.closed": "Fermé",
                    "component.weather.entity_component._.state.partlycloudy": "Éclaircies",
                    "component.climate.entity_component._.state_attributes.fan_mode.state.auto": "X"}})
            elif t == "call_service":
                print("call_service", d, flush=True)
                eid = (d.get("target") or {}).get("entity_id")
                if eid in STATES and d["service"] == "toggle":
                    STATES[eid]["s"] = "off" if STATES[eid]["s"] == "on" else "on"
                    await push(eid)
                elif eid in STATES and d["service"] in ("set_value", "select_option", "set_datetime"):
                    sd = d.get("service_data") or {}
                    v = sd.get("value", sd.get("option", sd.get("time", sd.get("date"))))
                    if d["domain"] == "input_datetime" and STATES[eid]["a"].get("has_date") and "time" in sd:
                        v = STATES[eid]["s"][:10] + " " + sd["time"]
                    elif d["domain"] == "input_datetime" and STATES[eid]["a"].get("has_time") and "date" in sd:
                        v = sd["date"] + " " + STATES[eid]["s"][-8:]
                    STATES[eid]["s"] = str(v)
                    await push(eid)
                elif eid in STATES and d["service"] in ("turn_on", "turn_off") and d["domain"] != "light":
                    STATES[eid]["s"] = d["service"][5:]
                    await push(eid)
                elif eid in STATES and d["domain"] == "light" and d["service"] == "turn_on":
                    # lampe simulée : luminosité, blanc (kelvin) ou couleur
                    at, sd = STATES[eid]["a"], d.get("service_data") or {}
                    STATES[eid]["s"] = "on"
                    if "brightness_pct" in sd:
                        at["brightness"] = int(round(sd["brightness_pct"] * 2.55))
                    if "color_temp_kelvin" in sd:
                        k = sd["color_temp_kelvin"] / 100.0
                        at.update(color_mode="color_temp", color_temp_kelvin=sd["color_temp_kelvin"],
                                  rgb_color=[255, int(max(0, min(255, 99.47 * math.log(k) - 161.12))),
                                             int(max(0, min(255, 138.52 * math.log(max(k - 10, 1)) - 305.04)))])
                    if "rgb_color" in sd:
                        at.update(color_mode="hs", color_temp_kelvin=None, rgb_color=sd["rgb_color"])
                    elif "hs_color" in sd:
                        import colorsys
                        h, s_ = sd["hs_color"]
                        rgb = [int(round(x * 255)) for x in colorsys.hsv_to_rgb(h / 360.0, s_ / 100.0, 1.0)]
                        at.update(color_mode="hs", color_temp_kelvin=None, hs_color=sd["hs_color"],
                                  rgb_color=rgb)
                    await push(eid)
                await ok(mid, {})
            else:
                await ok(mid)
    finally:
        tick.cancel()
    return ws


FRIGATE_REG = {"camera.%s" % k: {"platform": "frigate", "unique_id": "01MOCK:camera:" + v}
               for k, v in (("portail", "Portail"), ("facade", "Facade"), ("jardin", "Jardin"))}


async def camera(request):
    with open(ICON, "rb") as f:
        return web.Response(body=f.read(), content_type="image/png")


app = web.Application()
app.router.add_get("/api/websocket", ws_handler)
app.router.add_get("/api/camera_proxy/{eid}", camera)
web.run_app(app, port=int(os.environ.get("MOCK_PORT", "8124")))
