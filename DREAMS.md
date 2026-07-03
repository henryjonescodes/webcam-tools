# Dreams

Loosely-formed future ideas for Webcam Tools. Nothing here is scheduled or
committed — it's a parking lot so ideas don't get lost, not a roadmap.

---

## Generic webhook action (event → arbitrary downstream automation)

**The ask:** a way to *do something* with events beyond recording a clip —
lowest lift, highest flexibility. Send a webhook payload somewhere (IFTTT,
another consumer) so anything downstream (a text message, a smart-home
trigger, whatever) can react to "motion happened" without this app needing
to know or care what that downstream thing is.

**Why this fits cleanly:** it's not a new concept, it's the *next instance*
of the `Action` abstraction already built (`backend/app/actions/base.py`).
`RecordClipAction` is "on event, do this." A `WebhookAction` would be "on
event, POST this" — same interface (`trigger(event, frame)`), same
enable/disable toggle already surfaced in the Pipeline tab, same fan-out
model (every enabled action runs for every enabled detector's events). The
hard part (event/action plumbing) is already done; this is mostly a new leaf
class plus a config UI for the URL(s).

**Lowest-lift version I'd actually build first:**
- One `WebhookAction`, POSTs a small JSON body (`type`, `timestamp`, `meta`,
  `camera_name` — no image/video, keep the payload tiny) to a URL stored in
  `config.json`.
- IFTTT's **Maker/Webhooks** service is the natural first target:
  `POST https://maker.ifttt.com/trigger/{event_name}/with/key/{key}` with
  `{value1, value2, value3}`. The key lives in the URL itself, so no
  separate secrets handling needed — fits the existing "just a JSON file"
  config pattern. IFTTT becomes the fan-out point to *anything* (SMS via
  their SMS action, email, smart-home, whatever) without this app touching
  any of those integrations directly.
- Fire-and-forget: log failures, don't retry, don't block the detection
  loop (matches how `RecordClipAction` already keeps heavy work off the hot
  path).
- No per-event-type routing at first — same "every action runs for every
  event" model already in place. Filtering (e.g. "only webhook on motion,
  not on some future person-detected event") is a later refinement if it's
  ever needed.

**Open questions for whenever this gets picked up:**
- Generic arbitrary-URL webhook vs. IFTTT-specific convenience wrapper (or
  both — IFTTT preset is just a URL-shape helper on top of a generic POST).
  Since it's just an Action subclass, having both variant registered
  separately is unbelievably cheap.
- Should the payload optionally include a snapshot (base64 or a URL back to
  `/api/events/{id}/image`)? Adds payload weight/complexity; probably v2.
- Rate limiting beyond what `MotionDetector`'s cooldown already provides —
  likely unnecessary since the cooldown already bounds trigger frequency.
- UI: a simple settings panel (URL field(s) + enable toggle) is enough;
  doesn't need its own tab, could live in the Pipeline tab next to the
  action's existing enable switch.

---

## Real parcel / cardboard-box detection

**The gap:** the `objects` detector's `package` class is an approximation —
COCO (what YOLOv4-tiny was trained on) has no cardboard-box class, so
`package` currently maps to backpack/handbag/suitcase. That catches "delivery
person carrying something," but a bare box left on the step won't reliably
trip it.

**What it'd take:** a small custom-trained model. Options, roughly ascending
effort:
- Fine-tune a YOLO-nano on an open "package/parcel on doorstep" dataset (a
  few exist on Roboflow Universe) and drop the resulting weights into
  `data/models/` — the `ObjectDetector` is already structured so the model
  files are the only thing that'd change.
- Or a lighter heuristic: a "left-behind object" detector — background
  subtraction that flags a *new stationary blob* that appears and persists
  (a box dropped and left), which sidesteps needing a trained class at all
  and composes with the existing motion pipeline.

**Why parked:** the carried-luggage approximation covers most of the actual
"someone's at the door dropping something off" signal, and a custom model is
a real training/hosting commitment for a hobby cam. The `left-behind blob`
heuristic is the more interesting cheap experiment if this gets picked up.
