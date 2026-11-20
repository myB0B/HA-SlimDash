# Type 0 / Kindle: to do

State on 15/11/2026: 0.8.56 published, Kindle 4 NT on `http://192.168.1.10:8099/tab3.png?view=0`,
stop with any key.

## 1. Two columns (landscape)
- Today `eink.py` stacks the sections, each one on the full width.
- Place the sections side by side like Home Assistant, from the view « Maximum number of columns »
  (`max_columns`): at 800 × 600 (`rotate=90`), 2 columns of about 390 px.
- Single-column views do not change.

## 2. Settings from Home Assistant (no more editing `slimdash.conf`)
- The Kindle needs a fixed address (e.g. `http://192.168.1.10:8099/kindle.png`), set only once at
  installation.
- Dashboard chosen by the SlimDash options (dashboard published under the name `kindle`), view = the
  default view of that dashboard.
- Orientation deduced from the view (2 columns or more → landscape), without `rotate` in the address.
- Possibly a KUAL Portrait / Landscape menu (KUAL on K4 NT: menus only, no text input).

## 3. Commands with the Kindle keys
- Read the key code without `od` (missing): extract the bytes with `dd` and compare (`cmp` or `awk`,
  to check on the Kindle). Codes to read from the log.
- The script calls SlimDash (e.g. `/<dashboard>/key?k=…`); SlimDash acts as for the tablet buttons
  (same rights, same access key).
- Pad: a thick frame that moves from one button / tile to the next; centre: activates the framed
  button; page keys: previous / next view; Home: stop.
- Consider a confirmation for sensitive commands (gate).
- Test actions only on the fake Home Assistant.
