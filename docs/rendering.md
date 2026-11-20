# SlimDash: rendering by device class

Goal: show a Home Assistant dashboard on devices too old for the original interface, staying as
faithful as possible to its layout (positions, sizes, heights), with a page of a few kilobytes.

## The three classes

The class is deduced from the browser (`/diag` shows what the device reports) or forced by the
dashboard `device` option. Adding `?type=1` (old), `2` (intermediate) or `3` (modern) to the address
lets you try one; the type is kept when you change tab.

| | **Old** | **Intermediate** | **Modern** |
|---|---|---|---|
| Browsers | Chromium < 50, iOS < 10, Firefox < 52, unknown | Chromium 50–79, iOS 10–12, Firefox 52–74 | Chromium ≥ 80, iOS ≥ 13, Firefox ≥ 75 |
| Style sheets | `s.css` | `s.css` + `c-t2.css` | + `c-t3.css` |
| Layout | inline blocks, floats, tables | flexbox | CSS grid (several sections side by side when the width allows) |
| Theme colours | explicit rules, opaque colours computed by the server | CSS variables | CSS variables |
| Icons | SVG sprite | same | same |
| Graphs | 48 points, line only, redrawn every 30 min | 48 points, filled | 96 points, min/max under the large curves |
| Cameras | 480 px image every 30 s | 640 px every 10 s | 800 px every 3 s |
| Animations | none | none | short transitions |

Rules for the Old class (`s.css`): no flexbox, no CSS variables, `calc` with its `-webkit-` prefix,
and **never a negative margin on a block next to a float** (Android 4.4 draws it over the float).
In the Modern class: no `gap` on flexbox rows (missing in Chrome 80–83 and Safari 13–14.0).

## Faithfulness to the original

- **Layout**: heights in units like the Home Assistant « sections » views (1U = 56 px, +8 px for each
  additional unit), widths on 12 columns (`grid_options`), 8 px between cards. Columns of 500 px at
  most; two columns (32 px apart) from 684 px of width, for example a tablet in landscape, if the view
  has at least two sections; a single column stays centred. A section spanning several columns
  (`column_span` 2 to 4) takes the whole available width, even when alone in the view (several columns
  only from 684 px, as in Home Assistant).
- **View background image** (type 3 only): Home Assistant settings (opacity, size, alignment, repeat,
  fixed / scrolling); the image is shrunk by the server (Pillow) to 960, 1600 or 2048 px depending on
  the screen width, never enlarged, then cached. Types 1 and 2: theme background, no image.
- **Theme**: the one chosen in each view of the dashboard (Edit view > Theme); without a theme, the
  Home Assistant default theme. Dashboard `theme` option: `view` (default), `ha light` or `ha dark`
  (the Home Assistant default theme for all views; the old French values `vue`, `ha clair`,
  `ha sombre` are still accepted). Background, cards, texts, radii and state colours are taken from it
  (`theme.py`). Transparencies are computed on the server; no blur.
- **Language**: the one set in Home Assistant, English by default and when the language is not supported.
  State labels (« On », « Not detected »…) are those of Home Assistant; number format, month and day
  names, « 3 minutes ago » texts and short dates come from `i18n.py` (en, fr, de, es, it, pt, nl, ru,
  pl, hu; the same data is sent to the browser for the clock and the « ago » texts). To add a language,
  add an entry to `LANGS` in `i18n.py`.
- **Texts**: 14 px (name) and 12 px (state), card titles 24 px, like the original.

## Supported cards

Native: `tile` (features: trend curve, at the bottom or inline; cover buttons; lights: favourite
colours, brightness and temperature sliders), `button`, `entity` / `sensor` (with curve), `gauge`,
`energy-self-sufficiency-gauge`, `entities`, `glance`, `markdown` (templates), `heading`, badges,
`weather-forecast`, `thermostat`, `history-graph`, `statistics-graph`, `picture` (file, image uploaded
in Home Assistant at 512 px except type 3, or image entity), `picture-glance`, `picture-entity`
(cameras), `horizontal-stack`, `vertical-stack`, `grid`, `conditional`.

Custom:

| Card | Rendering |
|---|---|
| `button-card` | button (name, state, action); imposed height ≤ 80 px → compact 1U button. The JavaScript templates `[[[ ]]]` are ignored. |
| `bubble-card` | `button` → tile (state under the name if `show_state`); sub-buttons: icon, name, values of `state_content` (state, « 44 minutes ago », attribute) or `show_state`; `separator` → heading; `pop-up` ignored. |
| `mushroom-entity-card`, `mushroom-template-card` | tile; texts and icon colour computed by Home Assistant (Jinja templates). |
| `mushroom-chips-card` | chips; weather chip as an icon only unless `show_conditions` / `show_temperature`. |
| `stack-in-card` | a single card; chips aligned to the right after a tile sit on the tile's line. |
| `statistics-graph-chart-card` | one entity: large value + curve or bars. Several, names hidden: each value at its size (`state_size`), its colour (`state_adaptive_color`, thresholds), its place (`align_state`, offsets of `styles`). Names shown: « name value » list. Bars and curves in the same graph. |
| `digital-clock` | formats (`HH:mm`, `cccc d LLLL yyyy`…), sizes, weights and margins of the two lines. |
| `meteofrance-weather-card` | weather card. |
| `advanced-camera-card`, `webrtc-camera` | camera image. |

Any other card: a readable list of the entities it contains.

## Deliberate limitations

Not supported: `map`, `iframe` cards, media players, calendars, energy, pop-ups, `auto-entities`,
sliders other than the light ones (volume…), live video, trend arrows, `card_mod` styles (except the
background and height of a card), background image on types 1 and 2, and the theme effects on type 1.
Possible actions: toggle, press, call a service, set a light (colour, brightness, temperature),
navigate between the published views. The icon of a light that is on takes its real colour.

## Load

A single WebSocket connection to Home Assistant, limited to the displayed entities. A render per class
is only prepared when a device of that class asks for it. History is only requested if displayed
(every 5 minutes). A view weighs about 3 KB compressed; the style sheets and the script are cached for
24 hours.

## Checking a change

`python dev/snapshot.py check` compares the rendering of all the test views, in the three classes,
with the saved reference (`dev/snapshots/`): position, size, font and colours of every element. After
an intended change: `python dev/snapshot.py save`. To measure an original card, paste
`dev/measure_ha.js` into the browser console, on the Home Assistant view opened at 600 px width. The
November 2026 measurements are in `changelog.md`.
