# SlimDash: project review and change log

## 0.8.4: project review (13 November 2026)

Method: code review, then an automatic survey (position, size, font and colour of every text and icon)
of the original cards in Home Assistant and of the same cards in SlimDash, at 600 px width. Views
compared: `dashboard-slimdash` 0 and 2, `slimdash-demo` 0 to 4. Old class surveyed in detail;
Intermediate and Modern surveyed on 3 views. Not checked: the real rendering on the tablet (surveys
done in a recent browser).

### 1. Lightness: goal met

- One view page: 16 KB, 2.8 KB compressed. CSS 5.1 KB + JS 2.6 KB compressed, cached for 24 h.
- Pure ES5 JavaScript, a single pending request, no library.
- A single connection to Home Assistant, render prepared on the server, per class and on demand.

### 2. Respect of the limits of each class

| Class | Finding | Severity |
|---|---|---|
| Modern | `gap` on flexbox rows (`.hs`): missing in Chrome 80–83 and Safari 13–14.0, which are nevertheless classed Modern. The cards of a row touch each other. | bug |
| Old | Half-width cards at 49 % + 1 %: the right column stops 6 px before the edge of the full-width cards (measured: 588 vs 594). | visible |
| Old / Inter. | The gate card is 134 px in Old and 164 px in Intermediate (148 in Home Assistant). | visible |
| Modern | Gap between sections larger than elsewhere (headings shifted by 12 to 50 px at the bottom of the page). | minor |
| All | Still compliant: no flexbox or CSS variables in Old, SVG sprite, prefixed `calc`. | ok |

### 3. Visual faithfulness: measured differences

#### 3.1 Global differences (affect all cards)

| Subject | Original | SlimDash |
|---|---|---|
| Theme | theme `glass-bottom-nav`: background #2c2c2e + image, cards black 70 %, white text, secondary #d3d3d3 | background #111, cards #1e1e1e, text #e6e6e6, secondary #9a9a9a |
| Width | centred 500 px column | 588 px (full width, earlier choice) |
| Banner | none | 36 px banner (indicator, name, time) |
| Text size | 14 px (name) / 12 px (state) everywhere | 15/13 px in tiles, 18 px in lists |
| « Active » colour | amber for light, switch, detector; sensors #44739e | blue switch, orange detector, sensors #5d9ad1 |
| State labels | French examples: « Activé », « Non détecté », « Nuit dégagée » | « Allumé », « Libre », « Nuit claire » |

#### 3.2 Cards whose layout differs

| Card | Original | SlimDash |
|---|---|---|
| weather-forecast | state in 28 px on the left, place below, temperature on the right with max / min; forecast: day 12 px, icon 40, max then min one under the other | place on top, 44 px temperature stuck to the icon, humidity and wind; max and min on one line, icon 32 |
| sensor / entity | name on the left, icon top right, 28 px value on the left, grey 16 px unit, curve edge to edge at the bottom | icon left of the name, centred value, unit same size, curve inset |
| gauge | arc on top, name **under** the arc | name **above** the arc |
| history-graph | 24 px title, graph, legend at the bottom (coloured dot, name, value) | entity rows on top (18 px, icons), curve below, no legend colour |
| entities | 24 px title, 48 px rows, 14 px names, switch on one line, white section titles | 17 px grey title, 18 px names, switches on two lines (57 px), blue sections; card 530 px vs 593 |
| glance | 190 px card, white names, 14 px states | 128 px card, grey names, 18 px states |
| markdown | 14 px text, 20 px bold title, 16 px margin | 18 px text, 21 px thin title |
| picture-glance / picture-entity | title bottom left, icons or state bottom right | title top left, state text in addition to the icon, no state for picture-entity |
| button | icon ~65×40 at y=26, 16 px name at y=86 | 40 icon at y=16, 15 px name at y=69 |
| tile 2U (cover, curve) | content at y=16, buttons or curve at y=66–77 | content at y=11, buttons or curve at y=54–60 |
| badges | 36 px high, 12 px bold text, icon 18 | 24 px, 14 px text, icon 16 |
| chips | 36 px, 10.8 px bold text | 28 px, 14 px text |
| heading | 16 px text | 18 px |

#### 3.3 Options of your cards that were not taken into account

| Card | Ignored option | Effect |
|---|---|---|
| tile | `features_position: inline` | original: 1U full width, curve on the right; SlimDash: half-width 2U, curve below |
| digital-clock | formats and sizes of the two lines | original 122 px (56 px + 35 px thin date) or 78 px (short bold date); SlimDash always 80 px |
| statistics-graph-chart-card | `state_size` per entity, value colour, `align_state`, `hide_name` | « Outside » card: 2.2 °C in 40 px coloured on the left, hPa 20 px and % 30 px on the right; SlimDash: three white 30 px values in a row, 212 px vs 195 |
| statistics-graph-chart-card | names shown | original: « Temperature 2.2 °C ▼ » list; SlimDash: columns |
| bubble-card | sub-buttons without state | original: icons only; SlimDash: adds the values |
| mushroom chip `weather` | — | original: icon only; SlimDash: « Clear night 4.5 °C » |
| chip `last-changed` | — | original « 13 hours ago »; SlimDash « since 18:14 » (earlier choice) |
| light tile | `light-color-favorites`, sliders | empty 1U slot; state « On 1 % » instead of « 1 % » |

#### 3.4 Compliant (difference ≤ 3 px)

Positions of the name and state in 1U tiles, mushroom-template, heights in units (tile 56, button 120,
weather 248/120, gauge 184), barometer card in bars (211 vs 209).

### 4. Code

- `s.css` stacks four generations of rules for the same elements (dot, gauge); `c-inter.css` redefines
  part of them. It works, but every change is risky.
- `docs/rendus.md` still describes Old without icons or graphs.
- `Builder.rich` and `Builder.graphs` are always true: the « text only » branches are dead.
- No automatic regression test of the rendering.

### 5. Proposed fixes, in batches (0.8.x versions)

1. **Visual base**: 14/12 px sizes, colours read from the Home Assistant theme (background, cards,
   texts, « active » colour), state labels taken from the Home Assistant translations, class fixes
   (Modern rows, Old right edge).
2. **Native cards**: weather, sensor/entity, gauge, history-graph, entities, glance, markdown, cameras,
   button, 2U tiles, badges, headings.
3. **Options of custom cards**: inline tile, clock, statistics-graph-chart-card, bubble, chips.
4. **Housekeeping**: style sheet rebuilt per class, documentation, automatic original / SlimDash
   comparison that can be replayed after each version.

To decide: width (500 px centred like the original, or full width), top banner (keep, or reduce to the
indicator only), theme background image (cost on old devices).

## Change log

- 0.8.5: batch 1 done (14/12 px sizes, theme colours through the « theme » option, Home Assistant state
  labels, Modern rows, Old right edge). The « white weather icons » line of the survey was a
  measurement error and was removed: Home Assistant weather icons are coloured.
- 0.8.6: batch 2 done (weather, sensor/entity, gauge, history-graph, entities, glance, markdown,
  cameras, button, 2U tiles, badges, card titles).
- 0.8.7: small weather card fixed on Android 4.4 (negative margins removed).
- 0.8.8: batch 3 done (tile with inline curve, clock formats and sizes, statistics card: sizes,
  colours, alignments, bars + curves, « name value » list; bubble and weather chip as an icon only).
- 0.8.9: batch 4 done. Style sheets rebuilt per component (stacked rules merged, dead rules removed),
  dead rendering code removed, `docs/rendus.md` rewritten, non-regression tool `dev/snapshot.py`
  (18 views measured, no difference before / after the rebuild).
- 0.8.10: top banner (title, time) removed; the connection dot is on the left of the tab row (in a
  corner if there are no tabs). Width and absence of background image validated as they are.
- 0.8.11: statistics cards with several values (names hidden) placed like the original (line height
  1.6 x the size, values set under the title, « centre » value pushed to the right by the styles set
  to the right); tabs shown even for a single view (they carry the indicator); app configuration:
  allowed networks before the log level, dashboard fields translated with a help text per field.
- 0.8.12: lights. The icon of a light that is on takes its real colour (`rgb_color`, theme yellow by
  default). Tile features `light-color-favorites` (Home Assistant favourites, otherwise its 8 default
  colours), `light-brightness` and `light-color-temp`: placed like the original (42 px, 66 px from the
  top), sliders dragged with the finger and sent on release.
- 0.8.13: columns of 500 px at most, like the Home Assistant « sections » views; two columns (32 px
  apart) from 684 px of width, so a tablet in landscape. Colour favourites in percentages: the tablet
  ignored `calc()` and the red one went off screen.
- 0.8.14: in landscape, a view with a single section keeps its centred 500 px column; the two columns
  only apply to views of at least two sections (class `cols2` on `#main`).
- 0.8.15: Galaxy Tab 3 browser (Android 4.4) without `calc()`: `s.js` detects it and sets in px the
  widths of the w3/w4/w6/w9 cards and horizontal stacks (right edges aligned). The theme background
  covers the whole screen (`html` too). Class `w2` of `#main` renamed `cols2`: it conflicted with the
  weather `.w2` (secondary text).
- 0.8.16: `color` option of the `button` and `tile` cards (named colours, theme `primary` and `accent`).
  The icon takes it when the entity is on, always for a button, a scene or a script. Mock: real icons
  of the gate buttons.
- 0.8.17: `energy-self-sufficiency-gauge` card (self-sufficiency rate). The server reads the energy
  preferences and the statistics of the day (since midnight, Home Assistant time zone, every 5 min):
  (1 - grid / consumption) x 100, Home Assistant colours (green > 75 %, yellow < 50 %).
- 0.8.18: Home Assistant Material Design icons. `mdi.txt.gz` (7,447 icons of @mdi/svg 7.4.47,
  Pictogrammers, Apache 2.0, 850 KB, regenerated by `dev/build_mdi.py`); the page only embeds the icons
  used. Home Assistant default icons for entities without an icon; own icons kept for the weather and
  internal buttons (arrows, stop).
- 0.8.19: Bubble sub-buttons in the new format (`state_content`: state with capital letter,
  `last_updated` / `last_changed` as « 44 minutes ago » kept up to date by s.js, attribute;
  `show_icon: false`). The state under the name only appears with `show_state`, like Bubble.
- 0.8.20: theme and mode (dark / light / auto) per dashboard. At startup, the app wrote the list of
  Home Assistant themes into the schema of its config.yaml (/addons folder mounted) and asked the
  Supervisor to reread the local apps and rebuild it (`hassio_role: manager`): drop-down menu in the
  configuration. Auto = `prefers-color-scheme` (old browsers stay dark). The old global `theme` option
  is still the default value if present.
- 0.8.21: rereading the local apps does not change the schema of an installed app; the app also asks
  for its rebuild (`/addons/self/rebuild`), once per change of the list.
- 0.8.22: the theme comes from each view of the dashboard (Home Assistant view setting), or from the
  Home Assistant default theme in light / dark (`theme` option: view, ha light, ha dark). Removal of
  the Mode field, of the manager role, of the access to the apps folder and of the automatic rebuild
  (0.8.20–0.8.21).
- 0.8.23: a dashboard name accepts capital letters (address in lower case, case insensitive).
- 0.8.24: view tabs like Home Assistant (icon only if the view has an icon, icon + name with
  « show_icon_and_title », otherwise the name). Tiles with several features: the card grows to the
  Home Assistant minimum (1 or 2 + one row per feature), « toggle » feature (half-width slider
  switch), Home Assistant placement (42 px, 12 px gap, centred header).
- 0.8.25: light colours: rainbow box after the favourite colours; it opens a hue bar (full height,
  thin marker) that drives the light live (one send at a time, always the last position); the last box
  takes the hue and confirms. Tapping a slider no longer triggers the card action (turn on/off).
- 0.8.26: rounded corners of the sliders and of the switch on Android 4.4 (`overflow:hidden` does not
  clip children there: each piece has its own radius). Entity name (name type « entity ») without the
  device name in front, like Home Assistant (« Gate Car » -> « Car »).
- 0.8.27: self-sufficiency gauge with « auto » height (outside a stack): it crashed (None >= 3) and
  disappeared; it now takes the height of a normal gauge.
- 0.8.28: light theme: the colours chosen in the cards (coloured values, thresholds, titles) that are
  too light for the background are darkened, same hue, down to a 3:1 contrast (theme.readable); dark
  theme and curves unchanged.
- 0.8.29: light theme: background of the tiles that are on, coloured dots of the icons (color option)
  and tabs follow the theme (theme.light_fix; mushroom colours read from s.css). Dark theme unchanged.
  Local instance in light theme: dev/options_lum_clair.json (port 8095).
- 0.8.30: time-stamped sensors like Home Assistant (uptime « 1 month », timestamp « … ago », row
  format option, updated by s.js); header switch of the entities cards (show_header_toggle);
  editable number / input_number / select / time / date / input_datetime / text rows (field, list,
  slider; set_value on the server with a check of the bounds); gauges in a stack at natural height
  (fluid arc, value in the arc); « dense » placement of half cards next to a tall card (dcol);
  stack-in-card respects grid_options (columns); statistics-graph: show_state false, no min/max if
  axes and legend are hidden, negative style margins applied in a stack-in-card.
- 0.8.31: markdown cards: HTML entities (&nbsp;, &#9728;…) are rendered like in Home Assistant instead
  of being displayed as they are (fixed text and templates; tags still filtered).
- 0.8.32: connection dot fixed at the top right, in front of everything (no longer in the tabs).
  Graphs without a defined colour: colour according to the measurement (temperature green, humidity
  sky blue, energy/power pink-violet, pressure red, solar yellow); the others keep the palette.
- 0.8.33: Energy view. Large statistics-graph like Home Assistant: header icon, large values with the
  name below (name_position: below), show_graph: false respected (value without curve), gradient
  curves according to color_thresholds (small graphs too). Min / max under the curves removed.
  Icons of the stack-in-card tiles recentred in their bubble. Gauges: severity like Home Assistant
  (highest threshold reached), Home Assistant colours and thickness, fluid arc (no longer goes out of
  the card) with the value in the arc; same for the native self-sufficiency gauge.
- 0.8.34: statistics-graph with several curves: fill under each curve like Home Assistant (except
  show_fill: false). Vertical mushroom cards in a stack: natural height (no more 2 forced rows), the
  row of the EDF card lines up like Home Assistant (108 px, icons on top).
- 0.8.35: trying a class from the address: `?type=1` (old), `2` (intermediate) or `3` (modern)
  replaces `?classe=…`; the type is kept in the tab links.
- 0.8.36: theme effects taken over: in modern, translucent background, blur, edge line and reflection
  (card-mod-card), border, shadow, and a fixed glow on the background (dark theme); in intermediate,
  border and background only.
- 0.8.37: glow of the background also in intermediate and in light theme; `theme` option back to the
  three choices view / ha light / ha dark.
- 0.8.38: connection indicator moved (10 px) to fit in the rounded corner of the card.
- 0.8.39: Home Assistant `light` card: 270° brightness dial (drag on the ring), bulb in the centre
  (turn on / off), percentage and name below.
- 0.8.40: `light` card in light theme: readable dial track (theme inactive grey when off, light colour
  at 45 % when on).
- 0.8.41: `light` card in light theme: almost white light -> theme « light on » colour; colour too pale
  darkened (same hue) to stay visible.
- 0.8.42: cameras through Frigate first. Address taken from the Home Assistant Frigate integration
  (optional `frigate_url` option to replace it), checked with /api/version. Frigate cameras:
  latest.jpg?h=360 image every second (cache 0.8 s) in all types; live MSE video (go2rtc, relayed by
  /<dash>/live) in type 3, `&live=1` / `&live=0` to force / cut it, fallback to images if there is no
  MSE/H.264 or if the stream drops. Other cameras: Home Assistant as before. The loaded image replaces
  the old one (no more double download), pause when the page is hidden, hourly reload of the pages with
  cameras. `&info=1`: mode (live / 1s) after the title. `camera_image` and `camera_entity` now read in
  the entity list. `/debug`: Frigate address and cameras served.
- 0.8.43: `&info=1` on a camera without a title: banner with the camera name and its mode.
- 0.8.44: « old / intermediate / modern class » -> « type 1 / 2 / 3 » everywhere: /diag, /debug, option
  « Device type » (`auto|type 1|type 2|type 3`, old values still accepted), internal names t1 / t2 /
  t3, style sheets c-t2.css / c-t3.css. Rendering identical to 0.8.43 (snapshot, 3 types x 6 views).
  dev/snapshot.py: port 8136 (8097 taken = empty pages), Frigate switched off during the measurement.
- 0.8.45: cameras at 360 px everywhere. Home Assistant fallback: camera_proxy?width=640&height=360
  (Home Assistant ignores height alone), 1 image/s, cache 0.8 s. Frigate: at the pace of its detection
  (detect.fps read from /api/config, usually 5 fps), cache 0.15 s; next image requested once the
  previous one is displayed (a slow device slows itself down). `&info=1`: fps obtained (over 5 s) or
  « live ». No more interval or width per type.
- 0.8.46: ceiling for Frigate cameras: 1 fps in type 1 (Android 4.4 crashes at 5 fps x 4 cameras in 30
  s), 3 fps in type 2 (iPad Air iOS 12 holds 5 but heats up), type 3 live (5 fps before). `&fps=N`:
  trying another ceiling. Replaced image emptied at once (old WebKit memory). Displayed fps rounded to
  an integer.
- 0.8.47: the Android 4.4 browser still crashed after about 850 images (3 min 30 at 1 fps x 4 cameras,
  7 min at 0.5 fps): every image had a unique address, kept in memory (peaks at 290 MB). Each camera now
  alternates 2 fixed addresses (`&t=0` / `&t=1`, always no-store) and loads directly into the displayed
  image (no more preloading): 56 to 70 MB stable, 10 min without crash.
- 0.8.48: 2 columns: 8 px between them (like between the cards) and 16 px on the sides, instead of
  24–32 px between and 6 px on the sides (types 1 and 2: 50 % each, 8 px of padding on the right of
  #main; type 3: column-gap 8 px, 2 columns forced between 684 and 1215 px). Click on a camera: the page
  reloaded (the camera name was in data-n, the « go to view » attribute); renamed data-cn. Types 2 and
  3: 1 px line around the cards (separator colour), like Home Assistant, when the theme gives neither
  border nor edge line.
- 0.8.49: add-on configuration in English (description, port, theme values view | ha light | ha dark;
  vue | ha clair | ha sombre still accepted by the code). en.yaml and fr.yaml: frigate_url was filed
  under network (never translated). README.md (Info tab) and DOCS.md (Documentation tab) of the add-on,
  in English. Connection dot in the 16 px margin in 2 columns (3 px from the edge, 8 px from the top),
  without touching the cards.
- 0.8.50: light card (round gauge). Android 4.4: ring and bulb invisible (heights in % computed on the
  0-height block of .lgp) -> .lgd/.lgb placed by their edges. Bulb always grey (.ic overrode the colour
  of .lgi) -> color:inherit. Light off: mdi:lightbulb-off icon like Home Assistant (unless an icon is
  configured), both icons in the page for the live change.
- 0.8.51: lost taps on icons (Android 4.4): the target of a tap on <use> is an SVGElementInstance
  without getAttribute -> real() goes up to correspondingUseElement (target, slider). Type 1: thin 1 px
  line around the cards (separator colour, light and dark), without the stacked cards. Add-on
  description (Info header, README, DOCS, root README): dedicated dashboards per device, main options
  only for custom cards.
- 0.8.52: picture card (fixed image). Sources: Home Assistant path (/local…), http(s) URL, uploaded
  image (media-source://image_upload/ID -> /api/image/serve/ID/512x512, original in type 3; Home
  Assistant only accepts 256, 512 or original), image_entity (entity_picture, slot). Relay
  /<name>/img?i=key: only the images of the dashboard, Home Assistant token, shared 10 min cache. rows
  -> background image (cover).
- 0.8.53: picture card with rounded corners (border-radius on the image: old WebKit does not clip with
  the card). New logo/icon (images/5.png) and banner (docs/banner.jpg, embedded as a data URI in README
  and DOCS for the Home Assistant Info tab).
- 0.8.54: Info tab, Why section: introduction about the old device forgotten in a drawer (too slow,
  incompatible with the modern web and the companion app) that we want to bring back to life.
- 0.8.55: Info and docs: Tip sections (debloating the device, detailed in the docs) and Warning
  (battery, network security, plain HTTP, sensitive commands, good habits).
- 0.8.56: type 0, the view as a PNG image (`/<dashboard>.png?view=N`) drawn with Pillow (new module
  `eink.py`, Roboto fonts), 600 × 800 in 16 grey levels, type 3 look (light grey background, white
  cards, fill under the curves), for e-readers without a usable browser. KUAL extension and guide for
  the non-touch Kindle 4 (`kindle-k4/` folder). Docker image: +14 MB (py3-pillow).
- 0.8.57: type 0: wider left and right margins (9 %), bubble card with `state_content` (« … ago »
  instead of the repeated state), gauge value set in the arc, larger and centred weather forecast,
  graph values in large, temperature then humidity then pressure. Kindle: stop with any key (direct
  reading of the keys, without waitforkey or od).
- 0.8.58: type 0: view centred from top to bottom (same margin at the top and the bottom). Kindle:
  updates aligned exactly on the minute, clock set by a local NTP server (`NTP=` in `slimdash.conf`,
  for example Home Assistant).
- 0.8.59: section spanning several columns (column_span 2 to 4): the whole available width, even when
  alone in the view (before: stuck at 512 px). Class spN outside the left / right alternation.
- 0.8.60: full screen at the first touch on the page (requestFullscreen, webkit prefix included),
  resumed after leaving full screen (added from another session).
- 0.8.61: view background image (type 3 only): opacity, size, alignment, repeat and fixed / scrolling
  like Home Assistant; image shrunk by the server (Pillow, 960 / 1600 / 2048 px depending on the screen
  width, never enlarged, JPEG quality 72) through /<name>/img?w=…, cached.
- 0.8.62: phone notch / camera: viewport-fit=cover, safe margins (env(safe-area-inset-*)) on the page
  body, the connection dot and the bottom tab bar; the background goes to the edge of the screen. Old
  browsers ignore env().
- 0.8.63: no tab bar when the dashboard only publishes a single view (the connection dot stays
  displayed).
- 0.8.64: notch on one side only (phone in landscape): same margin on the left and on the right (the
  larger of the two, max()), the content stays centred.
- 0.8.65: Markdown card with text_only: text only, without background, border, shadow or theme effects
  (class txo), like Home Assistant.
- 0.8.66: shorter Markdown text_only card: 2 px margin (top, bottom) and 4 px (sides), 28 px # title
  without margin (measured in Home Assistant). Normal Markdown cards unchanged.
- 0.8.67: illustrations in the root README, the Info tab and the docs (data URI for Home Assistant):
  banner, two photos of the devices (camera blurred, city erased), screenshots of the Redmi 9A and the
  Galaxy Tab 3, Kindle 4 screen (type 0 image, city masked).
- 0.8.68: captions of the illustrations without type names (models and versions of the devices);
  frigate_url description: « as before » replaced by « one image per second » (en and fr).
- GitHub repository: GNU AGPL v3 or later license (LICENSE file, License section of the root README);
  copyleft, no warranty or liability (articles 15 and 16).
- 0.8.69: beta installation through a custom repository (root README: My Home Assistant button and
  steps; DOCS.md: Installation (beta) section), reminder that the repository requires Home Assistant OS
  or Supervised.
- 0.8.70: all the documentation in English (`kindle-k4/` folder: README.md guide, extension ready to copy,
  install-on-kindle.ps1; `docs/rendering.md`, `docs/changelog.md`, `docs/kindle-todo.md`; Kindle script
  messages and settings comments); export `.gitattributes`: `.sh` and `.conf` scripts with LF line
  endings.
  App texts and log messages and all code comments in English; single Kindle folder `kindle-k4/`
  (old `kindle/` removed, TODO moved to `docs/kindle-todo.md`); `slimdash/CHANGELOG.md` (user-facing);
  real GitHub URL in config.yaml and repository.yaml.
- 0.8.71: language. New `i18n.py`: language read from Home Assistant (`get_config`), English default and
  fallback; number separators, month / day names, relative times (plural rules en, fr, ru, pl), short
  dates and « since » texts per language (en, fr, de, es, it, pt, nl, ru, pl, hu), same data sent to s.js
  (`SD.L`, verified identical to Python for all languages). Fallback state labels now English (HA
  translations still win). The page `lang` follows the language. Snapshots re-saved: the fake Home
  Assistant only translates a few states, the others use the English fallback.
- 0.8.72: Warning section moved to the top of the docs (DOCS.md, right after the introduction) and of the
  Info tab (README.md, before Why); Hungarian (`hu`) added to the supported languages.
- 0.8.73: `tile` card: `state_content` (state, last_changed, last_updated, attribute; list) is now
  handled, the relative time stays up to date (issue 4). Temperature unit read from the Home Assistant
  unit system (get_config) and used when an entity gives none: climate tiles, thermostat, weather, e-ink
  (issue 5); thermostat step = `target_temp_step`, else 1 in Fahrenheit and 0.5 in Celsius. Schema:
  `tabs_bottom`, `views`, `refresh` and `device` optional, so a dashboard added without touching
  them can be saved (issue 6).
- 0.8.74: empty `views` = `0` (explicit), empty `device` = `auto`; both said in the option descriptions
  (en, fr) and in DOCS.md.
- 0.8.75: `thermostat` card redone like HA (title, 270 degree dial with set point handle, current
  temperature mark and mode-coloured arc, action, set point, current temperature, - / + buttons);
  features `climate-hvac-modes` and `climate-fan-modes` (thermostat and tile; action `cmode` ->
  set_hvac_mode / set_fan_mode). bubble-card: card-level `state_content` shows under the name.
- 0.8.76: thermostat card: dial dragged by finger (action `tset`: position -> temperature rounded to the
  step, between min_temp and max_temp), HVAC mode buttons shown by default, thermometer icon inline,
  centre texts narrower than the ring (they hid the touches).
- 0.8.77: thermostat card: - / + buttons change the set point at once on the page and send it once
  0.6 s after the last tap; modes (Off, Heat, Cool, Auto: 4-position selector, short names per language,
  `i18n.mode_label`) in a menu (three-dot button top right, one mode per line, closes on choice) so the
  card keeps the size of the HA one; the tile feature keeps a one-line row.
- 0.8.78: thermostat dial like HA (measured on the real card: heat = fill min -> set point, cool = set
  point -> max, other modes = whole ring, half opacity; active part current -> set point; handle border and
  action text in the mode colour; off = no fill). hvac_action and fan_mode labels from the HA translations
  (`TR_ATTR`, `render.tr_attr`). `features` of the thermostat card shown as rows at the bottom (like HA),
  `style: icons` for the HVAC modes; the three-dot menu stays the default without features.
- 0.8.79: thermostat card option `show_current_as_primary`: current temperature in the big number, set
  point in the small line (target icon, from memory of the HA card, not measured); the - / + buttons update
  that small line locally (`data-sw` on `.thm`, `.thtv`).
- 0.8.80: thermostat card title centred like HA (measured: centred over the whole card, 16 px).
- 0.8.81: cover tile features (issue #7): `cover-position` = position slider (like the brightness one, action
  `cover` -> `cover.set_cover_position`), `cover-position-favorite` = buttons of favourite positions (HA entity
  option `favorite_positions`, `cfav` in the registry, else 0/25/50/75/100; `positions` in the feature overrides),
  `cover-open-close` hides stop when not supported; covers without SET_POSITION fall back to the buttons.
- 0.8.82: cover tile features layout: the position buttons and the open/stop/close buttons share the whole width
  (flex tile: `width:100%`), equal 12 px gaps between the feature rows (cvb 42 px, buttons `vertical-align:top`),
  light theme: grey translucent buttons (`light_fix`).
- 0.8.83: issue #8: `POST /<dash>/a` without the field `a` (or with a negative index) ran the last action (Python negative
  index); now rejected with 400. Internal error message "unknown action" in English.
- 0.8.84: type 0 (Kindle) statistics graph card: humidity on the baseline of the main value, pressure above it on the
  baseline of the title (values drawn from their baseline, `font.getmetrics()`).
- 0.8.85: light theme: curve colours chosen in the cards (e.g. white) darkened to stay readable (`series_color` and
  statistics graph card use `readable`).
- 0.8.86: light theme: `color_thresholds` colours (gradient of the curve, legend dot) darkened with `readable` too
  (in `chart`, before `spark_svg`, which is a module function without access to the palette).
