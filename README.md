# Webcam Tools

Turns an old webcam into a self-hosted LAN camera app — live view, motion
and person detection, automatic clip recording, an event log, and a
configurable detector→action pipeline (record a clip, beep, hit a webhook,
whatever). A Python (FastAPI + OpenCV) backend serves everything over one
port; a React frontend gives you the live view and controls; an optional
Stream Deck plugin gives you physical buttons for all of it.

This is a personal side project, not a maintained product — built to be
forked, read, and changed, not installed-and-forgotten. Expect some rough
edges; PRs and forks are welcome.

## ⚠️ Security model — read this before running it anywhere but your LAN

**There is no authentication and no login.** Anyone who can reach the
server's port can view the live feed, watch/download recordings, change
camera settings, and fire the webhook. CORS is wide open
(`allow_origins=["*"]` in `backend/app/main.py`) because this is designed to
be reached from a browser on your phone or a Stream Deck on the same
network, not from the internet.

**Do not port-forward this to the public internet.** If you want remote
access, put it behind a [Tailscale](https://tailscale.com/) or
[Cloudflare Tunnel](https://www.cloudflare.com/products/tunnel/) and add
real authentication in front of it first. The webhook feature in particular
sends outbound requests to whatever URL you configure — anyone who can reach
the API can repoint that at an internal address, so treat "who can reach
this server" as "who I trust with that," same as the rest of the app.

## Project structure

A monorepo with three independent pieces — each has its own dependencies
and can be worked on without touching the others:

```
webcam-tools/
├── backend/           FastAPI + OpenCV server (Python) — capture, detection,
│                       recording, the REST API, mDNS advertisement
├── frontend/           React + Vite web app — live view, event log, settings
├── streamdeck-plugin/  Elgato Stream Deck plugin (TypeScript/Node) — optional
├── start.bat           One-command launcher (builds frontend if needed,
│                       runs the backend headless, self-healing)
└── DREAMS.md            Parking lot for future ideas, not a roadmap
```

## Quick start

**Prerequisites:** Windows (the camera-enumeration and headless-launch paths
are Windows-specific — see [Platform notes](#platform-notes)), Python 3.9+,
Node 18+, a webcam.

```
git clone https://github.com/henryjonescodes/webcam-tools.git
cd webcam-tools
python -m venv backend/.venv
backend\.venv\Scripts\pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
start.bat
```

Then open **http://localhost:8000** (or `http://webcam-tools.local:8000` /
`http://<LAN-IP>:8000` from another device on the network). `start.bat` is
safe to re-run any time — it checks whether the server's already up before
doing anything, builds the frontend only if it's missing or stale, then
launches the backend headless (no terminal window to keep open; logs go to
`backend/data/server.log`).

## Layout

The UI is a dockable-panel shell: the live view fills whatever space is
left, with a **right dock** (Camera settings + Pipeline tabs) and a
**bottom dock** (Event log). Either dock collapses to a thin bar (click it
to expand again) so the live view can go effectively full-bleed.
Connection/fps status and the REC indicator are small overlays on the video
itself, not a page header.

## Camera selection

Pick which camera to use from the dropdown in the **Camera** tab of the
right dock (devices are listed by friendly name, e.g. "Logi C525 HD
Webcam") — no restart needed. The choice is persisted to
`backend/data/config.json` and survives restarts.

**Pause camera** (button next to the dropdown) fully releases the OpenCV
capture handle so another app (Zoom, Teams, OBS) can open the same device —
useful since most webcams only allow one exclusive reader at a time.

## Detection: motion and person

Two detectors ship out of the box, both toggleable from the **Pipeline**
tab:

- **Motion** — cheap frame-differencing, runs on every captured frame. Fast
  enough to never compete for camera bandwidth.
- **Person** — OpenCV's built-in HOG pedestrian detector, distinguishes an
  actual person from a passing car or blowing leaves. Meaningfully more
  expensive per-check, so it runs on its **own background thread and
  timer**, independent of the capture loop — see
  [Detectors vs. the image pipeline](#detectors-vs-the-image-pipeline)
  below for why that split exists.

## The pipeline: detectors → actions, wired per-stage

The **Pipeline** tab shows every detector and every action, plus a chip
grid wiring which detector's events fire which action — click a chip to
link/unlink that specific pair (e.g. have Person fire the webhook but not
Motion, or vice versa). Nothing's hardcoded: this reads from a single
`/api/toggles` endpoint that reports every detector, action, and
image-processing toggle that currently exists, so a new one you add shows
up automatically.

**Actions** that ship today:
- **Record clip** — an ~10s H.264 clip (2s pre-roll + 8s post-trigger).
- **Sound alarm** — a short beep on the host PC. Off by default.
- **Webhook** — POSTs a small JSON payload (`event`, `id`, `timestamp`,
  `meta`) to a URL you configure in the Pipeline tab. The lowest-lift way to
  wire this into anything else — [ntfy.sh](https://ntfy.sh) for a free push
  notification, a Discord webhook, [Home Assistant](https://www.home-assistant.io/),
  [n8n](https://n8n.io/), IFTTT's Maker Webhooks, whatever. Off by default
  until you set a URL.

To add your own: **Detectors** decide *when* something happened
(`backend/app/detection/base.py`, `process(frame) -> Optional[dict]`).
**Actions** decide *what to do about it*
(`backend/app/actions/base.py`, `trigger(event, frame)`). Subclass either,
append an instance to `self.detectors` / `self.actions` in
`backend/app/camera.py`, and it's live — wired into the toggle registry,
the Pipeline tab, and (if you want) a Stream Deck button, with no other
code changes.

### Detectors vs. the image pipeline

Two independent loops feed the pipeline:

- **Fast loop** — capture cadence, the pristine frame straight off the
  sensor. Feeds the live stream, recordings, and any `heavy = False`
  detector (Motion). Nothing here may block for long.
- **Slow loop** — its own thread and timer, reading whatever frame is
  freshest instead of taking one off the capture loop. Any `heavy = True`
  detector (Person) runs here, so an expensive check can never stall a
  camera read or drop frames.

Set `heavy = True` on a new `Detector` subclass to put it on the slow loop;
leave it unset for anything cheap and latency-sensitive.

## Image controls

Three layers, applied in order:

1. **Exposure (hardware/preprocessing)** — Auto exposure toggle, Exposure,
   and Brightness sliders set actual camera driver properties
   (`CAP_PROP_EXPOSURE`, `CAP_PROP_AUTO_EXPOSURE`, `CAP_PROP_BRIGHTNESS`)
   before a frame is even read. This is what actually fixes blown-out
   highlights — once a pixel clips to white, no amount of post-processing
   brings the detail back, so correcting exposure at the source is the only
   real fix. Values are saved **per camera** (keyed by device name) under
   `camera_profiles` in `backend/data/config.json`, and reapplied
   automatically whenever that camera is selected.
2. **Rotation** — 0°/90°/180°/270°, for a camera mounted sideways or
   upside-down. Applied immediately after capture, before anything else
   touches the frame, so detection/recording/display all agree on "up."
3. **Post-processing (software)** — Brightness/contrast/saturation sliders,
   plus an **anti-glare** toggle that compresses highlights above a
   threshold instead of letting them clip to pure white (cuts glare from a
   window or windshield without darkening the rest of the frame). All layer
   on top of whatever the hardware already captured, and never affect
   motion detection (which always runs on the raw, pre-adjustment frame).

## Events: flagging and cleanup

Events (video clips) are kept for **24 hours** then garbage-collected
automatically (checked every 30 min). Click the ☆ on any event to flag it —
flagged events (★) are kept indefinitely. Use the ✕ button for
immediate/manual deletion. An event still recording shows a "still
recording" placeholder in the log instead of a broken/empty preview — it
becomes clickable once its clip finishes.

## Stream Deck plugin

A real Stream Deck plugin, not a generic "System: Website" button — see
[`streamdeck-plugin/`](streamdeck-plugin) for the full action list. A few
highlights:

- **Video Cell** — one button that's both a live thumbnail and your entry
  point into a dedicated Sentry-Cam Stream Deck profile.
- **Launch** — the power button: press to start the server, hold once
  running to stop it. Icon swaps between play/stop automatically.
- **Pipeline Toggle** — one configurable action for *any* on/off pipeline
  stage (a detector, an action, or an image toggle like anti-glare) — its
  Property Inspector dropdown is populated live from the server, so
  whatever you add to the pipeline later shows up there too, no plugin
  update required.

## Platform notes

Built and tested on Windows, which is baked into a few pieces:

- Camera enumeration by friendly name uses `pygrabber` (DirectShow).
- `start.bat` launches the backend via `pythonw.exe` for a headless (no
  console window) run.
- Opening the recordings folder and mDNS advertisement (`webcam-tools.local`)
  are Windows-specific paths.

The core FastAPI/OpenCV backend itself has no hard Windows dependency and
would likely run on Linux/macOS with camera enumeration swapped out (PRs
welcome) — it just hasn't been tried.

## Dev mode

Two terminals, if you want hot-reload on the frontend while working on it:

```
cd backend
.venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```
cd frontend
npm run dev
```

Open http://localhost:5173 — Vite proxies `/api` to the backend.

## License

[MIT](LICENSE) — do whatever you want with it.
