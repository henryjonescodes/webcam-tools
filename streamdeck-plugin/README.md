# Webcam Tools — Stream Deck Plugin

Launch, monitor, and control the [Webcam Tools](..) security camera app from a
Stream Deck. Built with Elgato's official SDK (`@elgato/streamdeck` v2 + the
Node.js plugin runtime), not a browser/website wrapper.

## Actions

| Action | Controller | What it does |
|---|---|---|
| **Video Cell** | Key | The one button worth putting on your *main* profile. Shows a live-updating thumbnail (like Live Feed) — falls back to the plain icon plus an "Offline" title if the snapshot fetch fails, rather than freezing on a stale frame that still reads as live. **Short press** → opens the bundled Webcam Tools profile (dials + status + web app, see below). **Long press** (~450ms) → "smart open": if the server's already up, opens the web app; if it needed a cold start, just starts it (press again once it's up to actually open the browser) — a cold-start tab left open on the live feed is exactly the kind of thing that can hang a later shutdown, see Launch below. |
| **Launch** | Key | The power button. Stopped: press to run `start.bat`. Running: icon flips to a stop glyph — **hold** (~450ms) to shut the server down; a short press on that state is a no-op, so a stray tap can't kill it. The hold *always* attempts a shutdown regardless of what the button last saw (e.g. right after Stream Deck boots, before the first status poll lands, or a stuck process is holding the camera without us knowing) — it's meant as a reliable "make sure it's off," not just a toggle. |
| **Status** | Key | Polls `/api/status` every 5s while visible; title shows `Live · N fps`, `Paused`, `No camera`, or `Offline`. Press to refresh immediately. Purely about connection health — recording state lives on its own cell now, see below. |
| **Recording Status** | Key | Separate cell just for recording state: `Idle`, or `REC` plus what triggered it (`Motion` / `Manual`). Press to refresh immediately. |
| **Open Web App** | Key | Opens the web app in your default browser (via Stream Deck's own `openUrl`). |
| **Open Recordings Folder** | Key | Opens the videos folder in Explorer *on the host machine* (the server does the opening, so this only makes sense from wherever Webcam Tools's Windows PC actually is). |
| **Live Feed** | Key | Standalone version of Video Cell's thumbnail, without the press behaviors. Same offline fallback. |
| **Camera Dial** | Encoder (Stream Deck+) | Bind each dial (via its Property Inspector) to one image control: hardware Exposure, hardware Brightness, or post-processing Brightness/Contrast/Saturation. Rotate to adjust, press to reset. Rotating Exposure also flips auto-exposure off, same convention real cameras use. Shows the current value as an actual progress bar on the touchscreen (a custom layout, `layouts/dial.json`), not just a title. |
| **Reset Camera Settings** | Key | Resets both hardware exposure *and* post-processing back to defaults in one press — the "start fresh" button. |
| **Record Clip** | Key | Manually records a clip right now, independent of motion detection. |
| **Pipeline Toggle** | Key | One configurable on/off button for *any* pipeline stage — a detector (motion, person), an action (record clip, sound alarm, webhook), or an image-processing toggle (anti-glare). Pick which one in the Property Inspector's dropdown, which is populated live from the server rather than hardcoded, so a stage added later just shows up — no plugin update needed. Icon flips solid green when on; title shows the specific name + on/off. Add as many as you want, each bound to a different stage. |

There's no separate Back/Shutdown action anymore — **Back** is just Stream
Deck's own built-in *Switch Profile* action (drag it from the system actions
list, not from Webcam Tools's category — point it at your home profile and it
can return to an exact profile by name, which a plugin-side Back button
[can't do](https://docs.elgato.com/streamdeck/sdk/guides/profiles)), and
**Shutdown** is folded into Launch's hold gesture above.

All actions share one **Server URL** (default `http://webcam-tools.local:8000`),
set once via any action's Property Inspector — it's stored in Stream Deck's
*global* settings, not per-button.

## Install (local use — no Marketplace needed)

Two ways, same result:

1. **Double-click** `com.webcam-tools.streamdeck.streamDeckPlugin` — Stream Deck
   installs it like any downloaded plugin. Rebuild + repack after code
   changes with `npm run pack`.
2. **Dev-link** (better while iterating): `npm run watch` — this rebuilds on
   every save and restarts the plugin in Stream Deck automatically, no
   repackaging needed. Requires the plugin to be linked once via
   `npx streamdeck link com.webcam-tools.streamdeck.sdPlugin`.

After installing, set the **Server URL** (and, on Launch/Video Cell, the
**start.bat path**) in any action's Property Inspector — it's shared, so you
only do this once.

## Building a "one button" profile

No profile ships by default — Elgato doesn't document (or support)
hand-authoring a `.streamDeckProfile` file
([confirmed against their own SDK docs](https://docs.elgato.com/streamdeck/sdk/guides/profiles)):
it has to be built by dragging actions onto the canvas in the Stream Deck app
and exported from there, so there's nothing to commit ahead of time that
would actually work on your layout. The pattern this plugin is built for
(and worth setting up once you've installed it):

1. In the Stream Deck app, drag **Video Cell** onto your everyday/main
   profile, and build a second profile (call it whatever you like) with the
   rest of the actions you want — Status, Camera Dial, Reset, etc. — plus a
   **Switch Profile** key (Stream Deck's own built-in action) to get back to
   your main one.
2. Right-click that second profile in Preferences → Profiles → **Export**.
3. Drop the exported `.streamDeckProfile` file in this folder (or the repo
   root) and run:
   ```
   npm run update-profile
   ```
   This finds it, copies it into place as `profiles/webcam-tools.streamDeckProfile`,
   adds the manifest entry so it ships with the plugin from now on, rebuilds,
   and repacks — one command. (Or pass a path explicitly:
   `npm run update-profile -- "C:\path\to\file.streamDeckProfile"`.)
4. Reinstall `com.webcam-tools.streamdeck.streamDeckPlugin` (or `npx streamdeck
   restart com.webcam-tools.streamdeck` if dev-linked) to pick it up.

From then on, short-pressing **Video Cell** on your main profile jumps
straight into that second profile (dials, status, web app); **Switch
Profile** returns you to wherever you came from.

**Default layout**, if you want a starting point before customizing:
- **Switch Profile** (Stream Deck's built-in action, pointed at your home
  profile) → any key (un-does opening the panel).
- **Launch** → any key (doubles as the power button; hold once running to
  stop the server, see above).
- **Status**, **Recording Status** → any two keys — they're deliberately
  separate now so connection health and recording state don't fight over
  one line of text.
- **Open Web App** → any key.
- **Reset Camera Settings**, **Record Clip** → any keys (both optional, but
  handy on the same panel as the dials).
- **Camera Dial** → all 4 dials, each with its own **Control** set in the
  Property Inspector:
  - Dial 1: `Exposure (hardware)`
  - Dial 2: `Brightness (hardware)`
  - Dial 3: `Brightness (post-processing)`
  - Dial 4: `Contrast (post-processing)`
  (Saturation is available too, if you'd rather swap it in for one of these.)

## Using it from a Mac (view-only)

The plugin declares macOS support and everything except spawning `start.bat`
is plain HTTP + Stream Deck's own `openUrl`, so it works over the LAN with
zero code differences:

- **Video Cell** short-press still opens the panel; long-press opens the web
  app if the server's already up, or shows an alert if it's not (a Mac can't
  start the Windows host — start it there, or hit its own Launch button).
- **Status**, **Recording Status**, **Live Feed**, **Open Web App**, and all
  4 **Camera Dials** work identically to the Windows side, live, over the
  network.
- Just install the same `.streamDeckPlugin` on the Mac and repeat the
  profile setup above (or export/copy the same profile — Stream Deck
  profiles aren't OS-specific).

## Troubleshooting

- **"It was working, then I uninstalled/reinstalled and it wasn't."** A full
  uninstall + reinstall wipes the plugin's global settings (Server URL,
  start.bat path) — that's normal Stream Deck behavior, not a bug. Re-enter
  them once in any action's Property Inspector. (Just *updating* the plugin,
  or dev-linking with `npm run watch`, does **not** wipe settings — only a
  full uninstall does.)
- Node debug mode is off by default (`Nodejs.Debug: "disabled"` in the
  manifest) so a leftover process from a previous install can't block the
  new one from claiming its debug port on relaunch. Flip it back to
  `"enabled"` if you need to attach a debugger.
- If a button just shows "Offline" everywhere: the server itself isn't
  reachable, not a plugin bug — check `start.bat` is running (it's
  self-healing now, safe to re-run any time; see the main
  [Webcam Tools README](../README.md)).

## Build from source

```
npm install
npm run build      # -> com.webcam-tools.streamdeck.sdPlugin/bin/plugin.js
npm run validate    # runs the official streamdeck validator
npm run pack        # -> com.webcam-tools.streamdeck.streamDeckPlugin
```

Icons are from two sources:
- **Video Cell, Live Feed, Camera Dial, Recording Status, and Launch's stop
  glyph** are hand-drawn by `scripts/generate_icons.py` (needs Pillow — the
  webcam-tools backend's venv already has it:
  `../backend/.venv/Scripts/python.exe scripts/generate_icons.py`). Re-run it
  if you tweak a glyph.
- **Launch (play), Status, Reset, Record Clip, and Open Web App** were pulled
  out of a `.streamDeckProfile` export where they'd been manually set as
  custom per-key images in the Stream Deck app — profile exports are just
  ZIPs, and each key's custom image lives under
  `Profiles/*.sdProfile/Profiles/<page-uuid>/Images/`, referenced from that
  page's own `manifest.json`. There's no script for this since it's a
  one-time pull from someone's specific export; to redo it, export a
  profile, unzip it, find the image referenced for the key you want, and
  drop a resized copy into `imgs/actions/<name>/{icon,icon@2x,key,key@2x}.png`.

Either way, nothing else needs to change since the plugin's own
`manifest.json` just references those paths.

## Limitations / honest caveats

- **Live Feed / Video Cell aren't video.** Stream Deck key images aren't
  meant for streaming — this polls a JPEG snapshot at ~1/sec, which reads as
  "live-ish" on a small button, not a real camera feed. Pushing the rate
  much higher risks overloading the Stream Deck app.
- **Launch's play/stop swap uses two manifest States (`setState()`), not a
  runtime image swap (`setImage()`).** The latter is silently ignored on any
  key where you've manually set a custom image in the Stream Deck app — an
  actual issue in an earlier build of this plugin. States sidestep that
  entirely: State 1 (running) just uses its own manifest-declared image, so
  the swap works even on a key you've customized, without needing to
  "Restore to default image" first.
- **Shutdown has a 5s hard-exit watchdog.** Uvicorn's graceful shutdown
  waits for in-flight connections to finish before it actually stops the
  process — and `/api/stream` (the live MJPEG feed) is long-lived by design,
  so a browser tab left open on it can hang that indefinitely, leaving the
  process (and its lock on the camera) stuck. `POST /api/system/shutdown`
  now force-exits 5s later regardless, so Launch's hold-to-stop is reliable
  even with a tab open — any in-flight stream just gets cut off.
- **A profile ships now**, but re-exporting a new one is still a manual
  Stream Deck app step (Elgato doesn't support hand-authoring the format) —
  `npm run update-profile` handles everything after that export.
- **Not tested on physical Stream Deck hardware from this environment** — the
  code builds and passes the official `streamdeck validate` check, and every
  API call it makes was verified directly against the running Webcam Tools
  backend, but the actual on-device feel (dial sensitivity, long-press
  timing, image refresh smoothness) needs a real Stream Deck+ to tune. The
  long-press threshold (450ms) is a reasonable starting guess, not something
  I could tune by feel.
- **Launching only works from Windows** (start.bat, DirectShow, mDNS are all
  Windows-side) — everything else (viewing, dials, status) works from any
  OS Stream Deck supports, including the Mac case above.

## Distributing beyond your own machine

The `.streamDeckPlugin` file works as a one-off install for anyone you send
it to (same double-click flow) — the bundled profile travels with it.
Publishing to the **Elgato Marketplace** is a
separate, heavier process — plugin review, icon/asset requirements, a
public listing — not attempted here since this is a personal-use tool
talking to a camera on your specific LAN.
