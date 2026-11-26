# Changelog

All notable changes to SlimDash. The format follows [Keep a Changelog](https://keepachangelog.com/).
The detailed development log (measurements, decisions) is in `docs/changelog.md` of the repository.

## 0.8.73 - 0.8.87

### Added
- `thermostat` card like Home Assistant: dial with the set point and the current temperature (drag the
  handle to set the temperature), action, - / + buttons, colours of the mode (heat, cool, auto).
  A menu (three dots, top right) changes the mode: off, heat, cool, auto.
- `features` of the thermostat and tile cards: `climate-hvac-modes` (`style: icons` available) and
  `climate-fan-modes`; on the thermostat card they are shown as buttons at the bottom, like in Home Assistant.
- Thermostat card option `show_current_as_primary`: swaps the set point and the current temperature.
- Cover features of the tile card: `cover-position` (position slider), `cover-position-favorite` (favourite
  positions buttons), in the colour of the tile; the stop button is hidden when the cover cannot stop.

### Fixed
- Light theme: a curve colour that is too light (e.g. white), including the colour thresholds, is darkened so
  the graph stays visible.
- Type 0 (e-reader image): in the statistics graph cards, the values are aligned (humidity on the baseline of the
  temperature, pressure above it).
- A request to run an action without a valid action number (missing or negative) no longer runs the last action;
  it is rejected.
- Tile cards: `state_content` is handled, e.g. `last_changed` shows a relative time ("3 hours ago").
- Bubble card: the card `state_content` (e.g. last updated) is shown under the name.
- Temperatures of climate entities (tiles, thermostat) use the temperature unit of Home Assistant
  (Fahrenheit was shown as Celsius).
- A dashboard added in the options can be saved without touching "Tabs at the bottom".
- The climate action ("Heating", "Idle"...) and the fan modes use the language of Home Assistant.

### Changed
- Options: an empty `views` means `0` (first view), an empty `device` means `auto`.

## 0.8.71

### Added
- Language: SlimDash now uses the language of Home Assistant (English by default) for number formats,
  month and day names, "3 minutes ago" texts and dates. Supported: en, fr, de, es, it, pt, nl, ru, pl, hu.
  Other languages fall back to English (state labels still come from Home Assistant).

### Fixed
- The add-on page now links to the GitHub repository.

### Changed
- All the documentation is now in English (README, DOCS, guides, development notes).
- The texts shown by the app (default view names, error messages, diagnostics page) and the log
  messages are in English.
- A single Kindle folder, `kindle-k4/` (guide, extension, Windows install script).

## 0.8.69
### Added
- Beta installation through a custom repository (My Home Assistant button and steps in the README).

## 0.8.65 - 0.8.68
### Added
- Illustrations in the README and in the Info tab.
### Fixed
- Markdown card with `text_only`: no border, background or shadow.

## 0.8.61 - 0.8.64
### Added
- View background image (type 3), with the Home Assistant settings; the image is shrunk to the screen.
- Phone notch / front camera: content kept out of the notch, background up to the screen edge.
### Changed
- No tab bar when a dashboard publishes a single view.

## 0.8.59 - 0.8.60
### Added
- Sections spanning several columns (`column_span`) use the whole available width.
- Full screen at the first touch on the page.

## 0.8.56 - 0.8.58
### Added
- Type 0: the view drawn as a greyscale PNG image (`/<dashboard>.png?view=N`) for e-readers, with an
  extension and a guide for the non-touch Kindle 4.

## 0.8.52 - 0.8.55
### Added
- `picture` card (file, uploaded image or image entity).
- Info / documentation sections: Why, Tip (debloat your device) and Warning (battery, network security).

## 0.8.42 - 0.8.51
### Added
- Cameras through Frigate (address taken from the Frigate integration), live video on type 3.
- `light` card (270 degree brightness dial) and its light theme rendering.
- Trying a type from the address: `?type=1`, `2` or `3`.
### Fixed
- Crashes of the Android 4.4 browser with camera images; lost taps on icons.

## 0.8.30 - 0.8.41
### Added
- Timestamp sensors like Home Assistant (uptime, "... ago").
- Theme effects (translucent background, blur, edge highlight) on modern browsers.
- Energy view: large statistics graph, curves with fill.
- Connection dot fixed at the top right.

## 0.8.17 - 0.8.29
### Added
- `energy-self-sufficiency-gauge` card, Home Assistant Material Design icons (7,447 icons).
- Theme per view, light and dark themes; light colours with a rainbow box and hue bar.
- View tabs like Home Assistant.
- Bubble card sub-buttons in the new format.

## 0.8.5 - 0.8.16
### Added
- Sizes, theme colours and state labels taken from Home Assistant; `color` option of tiles and buttons.
- Lights: real icon colour, favourite colours, brightness and temperature sliders.
- Columns of 500 px at most, two columns in landscape, like the Home Assistant sections views.
### Fixed
- Galaxy Tab 3 browser without `calc()`.
