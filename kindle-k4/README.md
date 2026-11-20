# SlimDash on a Kindle 4 (non-touch)

Give a Kindle 4 a second life: it shows one of your Home Assistant dashboard views full screen,
refreshed every minute, with no sleep mode. Its browser is not used.

SlimDash draws the view as a 600 × 800 pixel greyscale PNG image
(`http://<IP>:8099/<dashboard>.png?view=<number>`). A small script on the Kindle downloads the
image and displays it. The image only changes when a displayed value has changed, and the Kindle only
refreshes its screen at that moment.

> The Kindle is only a screen: you cannot tap the buttons of the image.

## What is in this folder

| Item | Purpose |
|---|---|
| `README.md` | This guide: jailbreak, KUAL, installing SlimDash. |
| `copy-to-kindle/extensions/slimdash/` | The SlimDash extension: the scripts and settings to copy to the Kindle. |
| `install-on-kindle.ps1` | Windows script that copies the extension and sets the address (optional: you can also copy by hand). |

The jailbreak and KUAL files are **not** in this folder: they are software by other authors, to
download from their official pages (links in steps 2 and 3).

---

## 0. Before you start

- **Non-touch Kindle 4**: 5 buttons and a directional pad. Firmware **4.1.x**
  (`Menu` › `Settings` › `Menu` › `Device Info`). Check compatibility with the KindleModding
  « Find my Jailbreak » wizard before you begin.
- **The Kindle Wi-Fi already set up**, on the same network as Home Assistant.
- **A USB wall charger** (a phone charger) for everyday use. ⚠️ Not a computer USB port: plugged
  into a PC, the Kindle goes into « USB drive mode » and switches off its display and Wi-Fi.
- A computer and the USB cable, to copy the files.
- SlimDash installed in Home Assistant (a recent 0.8.x version: « type 0 » is required).

### Precautions

- The jailbreak is done **at your own risk**: follow the steps in order. It does not touch your
  books and can be undone (see the end of this guide).
- **Amazon automatic updates.** A firmware update can remove the jailbreak. During the installation,
  put the Kindle in **airplane mode**. Afterwards, as with any old device, **block its access to the
  Internet** on your router: it only needs your local network, and it no longer gets security updates.
- An old Kindle has a worn battery: when it stays plugged in all the time, check now and then that it
  does not swell.

---

## 1. Prepare the view in Home Assistant

1. Create a dedicated view (in a dashboard published by SlimDash), of the **Sections** type, with
   **a single column** (« Maximum number of columns »: 1).
2. Keep it **short**: the screen is 600 × 800. If it is too tall, the image is scaled down (to 60 %
   at most), then cut at the bottom.
3. Cards that are drawn: clock (`digital-clock`), weather, graphs (history, statistics), gauges,
   buttons, tiles, entities, glance, markdown, headings, bubble-card, mushroom, stacks and grids. Other
   cards are shown as a « name: state » list. Cameras are not drawn.
4. Check the image in the browser of your PC:
   `http://<Home Assistant IP>:8099/<dashboard>.png?view=0`
   (`<dashboard>`: the name given in SlimDash; `view`: the view number starting at 0, or its URL
   path).

Image options: `w` and `h` (screen size, 600 × 800 by default), `rotate=90` or `270` (Kindle lying
down), `k=<key>` (access key, if SlimDash has one).

---

## 2. Jailbreak the Kindle

File: **`K4-Jailbreak.zip`**, by NiLuJe, to download from the official KindleModding page (the
download link is at the bottom of its guide).

1. Put the Kindle in **airplane mode** (turn the Wi-Fi off): `Menu` › `Settings`, then `Menu` ›
   « Airplane Mode » or « Turn Wireless Off », depending on the version.
2. Unzip the archive. Plug the Kindle into the PC: it shows up as a USB drive.
3. Copy these three items to the **root** of the Kindle: **`data.tar.gz`**, **`ENABLE_DIAGS`** and
   **`diagnostic_logs`**.
4. Eject the Kindle properly, then unplug it.
5. Restart it: `Menu` › `Settings` › `Menu` › `Restart`.
6. It opens in **diagnostic mode** (a text screen). With the directional pad:
   - choose **D) Exit, Reboot or Disable Diags**;
   - then **R) Reboot System**;
   - then **Q) To continue**.
7. Wait about twenty seconds. A book called **« You are Jailbroken »** appears in the library: it is
   done.

---

## 3. Install KUAL (the extension launcher)

KUAL adds an extension launcher to the library: it is what starts SlimDash.

1. Download **`KUAL-KDK-1.0.azw2`**: this is the version for old Kindles (K4 and earlier).
   **Not the « booklet » version**, which does not work on a Kindle 4.
2. Copy it into the **`documents`** folder of the Kindle. Eject and unplug.
3. Open « Kindle Launcher » (KUAL) in the library. A menu appears: KUAL works.

If KUAL shows **« Mobileread Kindlet Kit is not installed »**: install MKK first (the
« Mobileread Kindlet Kit (MKK) » thread on MobileRead). Copy its `.bin` file to the root of the
Kindle, then `Menu` › `Settings` › `Menu` › `Update Your Kindle`. Users report errors when an
unregistered Kindle has its Wi-Fi on during this step: do it in airplane mode.

MRPI (a package installer) is **not needed** for SlimDash.

---

## 4. Install SlimDash on the Kindle

### With the Windows script (easiest)

1. Plug the Kindle into the PC (the drive is called « Kindle »).
2. In this folder, right-click `install-on-kindle.ps1` › **Run with PowerShell**, or in a terminal:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\install-on-kindle.ps1 `
     -Url "http://192.168.1.10:8099/kindle.png?view=0" -Ntp "192.168.1.10"
   ```
   (`-Url`: the address tested in step 1; add `&k=<key>` if SlimDash has an access key;
   `-Ntp`: time server, optional; `-Drive E:` if the Kindle is not detected.)
3. Eject the Kindle and unplug it.

Running the script again later updates the extension and **keeps your settings** if you do not give
`-Url` again.

### By hand (Windows, macOS, Linux)

1. Plug the Kindle into the PC.
2. At the root of the Kindle, create the **`extensions`** folder if it does not exist.
3. Copy into it the **`slimdash`** folder from `copy-to-kindle/extensions/`. You must end up with
   `extensions/slimdash/config.xml`, `menu.json`, `slimdash.conf` and `bin/`.
4. Open `extensions/slimdash/slimdash.conf` with a text editor and set:
   ```
   URL="http://192.168.1.10:8099/kindle.png?view=0"
   NTP=""
   INTERVAL=60
   FULL_EVERY=10
   ```
   - `URL`: the image address, tested in step 1;
   - `NTP`: time server of the local network (for example Home Assistant, if it acts as one), to keep
     the Kindle on time; empty: none;
   - `INTERVAL`: seconds between two updates (10 at least), aligned on the clock (60 = exactly every
     minute);
   - `FULL_EVERY`: the screen is fully cleared then redrawn every N images (removes ghosting).
5. Save, eject, unplug.

Then plug the Kindle into the **wall charger**.

---

## 5. Start and stop

- **Start**: « Kindle Launcher » › **SlimDash** › **Start display**. The Kindle interface stops,
  « SlimDash: connecting... » appears, then the image arrives in less than a minute. The Wi-Fi must
  be **on** (no airplane mode).
- **Stop**: the **Home** key (the other keys are ignored, to avoid stopping by mistake). The interface
  comes back after a few seconds. If nothing happens, hold the **power button for 20 seconds**: the
  Kindle restarts normally.
- After a restart of the Kindle, start SlimDash again from KUAL: there is no automatic start.

---

## 6. Troubleshooting

| Symptom | What to do |
|---|---|
| « SlimDash: address missing. » | `URL` is empty in `slimdash.conf`. |
| « SlimDash unreachable - retrying... » at the bottom of the screen | Check the address in the PC browser and the Wi-Fi of the Kindle. The script restarts the Wi-Fi and retries by itself. |
| Black banner « Home Assistant unreachable » on the image | SlimDash is running but can no longer reach Home Assistant. |
| Image too small or cut | The view is too tall: remove cards or reduce their height (rows). |
| Nothing is displayed after « Start » | Plug it into the PC and read `extensions/slimdash/slimdash.log`. |
| The Kindle goes into USB drive mode | It is plugged into a PC: use a wall charger. |
| KUAL does not open, or « not signed by an authorized developer » | Check that the file is `KUAL-KDK-1.0.azw2` (not the « booklet » version) and install an up-to-date MKK. |
| « You are Jailbroken » is gone | An Amazon update removed the jailbreak. Redo step 2 in airplane mode, then block the Kindle's Internet access on the router. |

The log `extensions/slimdash/slimdash.log` records the start, the Wi-Fi state, the keys and the
download failures.

---

## 7. Uninstall

- **SlimDash**: delete the `extensions/slimdash` folder from the Kindle.
- **The jailbreak**: follow the « Unjailbreaking Your Kindle » page of KindleModding.

---

## Sources

- [KindleModding: NiLuJe K4 Jailbreak](https://kindlemodding.org/jailbreaking/Legacy/K4-Jailbreak/)
  (step 2, file `K4-Jailbreak.zip`).
- [KindleModding: Installing KUAL & MRPI](https://kindlemodding.org/jailbreaking/Legacy/post-jailbreak/installing-kual-mrpi/)
  (step 3, file `KUAL-KDK-1.0.azw2`, airplane mode).
- [KindleModding: Disabling OTA Updates](https://kindlemodding.org/jailbreaking/Legacy/post-jailbreak/disable-ota.html)
  (preventing Amazon updates).
- [KindleModding: Unjailbreaking Your Kindle](https://kindlemodding.org/jailbreaking/unjailbreaking.html).
- MobileRead, thread « Mobileread Kindlet Kit (MKK) » (if KUAL asks for it).

Links and file names may change: when in doubt, the KindleModding page is the reference for the
jailbreak and KUAL. SlimDash is not affiliated with Amazon or with these projects.
