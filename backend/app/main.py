import os
import subprocess
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import mdns
from .camera import CameraStream, list_available_cameras
from .config import load_config, save_config
from .events import VIDEO_DIR, EventStore

events = EventStore()
camera = CameraStream(events)

_detector_config = load_config().get("detectors", {})
for _detector in camera.detectors:
    if _detector.name in _detector_config:
        _detector.enabled = _detector_config[_detector.name]

_action_config = load_config().get("actions", {})
for _action in camera.actions:
    if _action.name in _action_config:
        _action.enabled = _action_config[_action.name]

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

GC_INTERVAL_SECONDS = 30 * 60
_gc_stop = threading.Event()


def _gc_loop():
    events.run_gc()
    while not _gc_stop.wait(GC_INTERVAL_SECONDS):
        events.run_gc()


@asynccontextmanager
async def lifespan(app: FastAPI):
    camera.start()
    gc_thread = threading.Thread(target=_gc_loop, daemon=True)
    gc_thread.start()
    zc = mdns.start(int(os.environ.get("PORT", 8000)))
    yield
    camera.stop()
    _gc_stop.set()
    mdns.stop(zc)


app = FastAPI(lifespan=lifespan)

# LAN-only tool for now; loosen/tighten this if it's ever exposed beyond the LAN.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_cache_index_html(request, call_next):
    """Vite content-hashes every asset filename (index-XXXX.js), so a stale
    cached index.html pointing at a filename from a previous build 404s on
    reload -- the whole app fails silently. Assets themselves are safe to
    cache hard since their name changes whenever their content does; only
    index.html (and directory-index "/") needs to always revalidate."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.endswith(".html"):
        response.headers["Cache-Control"] = "no-cache"
    return response


def mjpeg_frames():
    while True:
        frame = camera.get_jpeg()
        if frame is None:
            time.sleep(0.05)
            continue
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        )
        time.sleep(0.03)


@app.get("/api/stream")
def stream():
    return StreamingResponse(mjpeg_frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/snapshot")
def snapshot():
    frame = camera.get_jpeg()
    if frame is None:
        raise HTTPException(503, "camera not ready")
    return Response(content=frame, media_type="image/jpeg")


_shutting_down = False


@app.get("/api/status")
def status():
    return {**camera.status, "shutting_down": _shutting_down}


@app.get("/api/cameras")
def cameras():
    return {"devices": list_available_cameras(), "current": camera.camera_index}


class CameraSelect(BaseModel):
    index: int


@app.post("/api/camera/select")
def select_camera(body: CameraSelect):
    camera.switch(body.index)
    return {"index": body.index}


class CameraPause(BaseModel):
    paused: bool


@app.post("/api/camera/pause")
def pause_camera(body: CameraPause):
    if body.paused:
        camera.pause()
    else:
        camera.resume()
    return {"paused": body.paused}


@app.get("/api/camera/adjustments")
def get_adjustments():
    return camera.get_adjustments()


class AdjustmentUpdate(BaseModel):
    brightness: Optional[float] = None
    contrast: Optional[float] = None
    saturation: Optional[float] = None


@app.post("/api/camera/adjustments")
def set_adjustments(body: AdjustmentUpdate):
    camera.set_adjustments(brightness=body.brightness, contrast=body.contrast, saturation=body.saturation)
    return camera.get_adjustments()


@app.get("/api/camera/rotation")
def get_rotation():
    return {"rotation": camera.get_rotation()}


class RotationUpdate(BaseModel):
    rotation: int


@app.post("/api/camera/rotation")
def set_rotation(body: RotationUpdate):
    try:
        camera.set_rotation(body.rotation)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"rotation": camera.get_rotation()}


@app.get("/api/camera/hardware")
def get_hardware():
    return camera.get_hardware()


class HardwareUpdate(BaseModel):
    auto_exposure: Optional[bool] = None
    exposure: Optional[float] = None
    brightness: Optional[float] = None


@app.post("/api/camera/hardware")
def set_hardware(body: HardwareUpdate):
    camera.set_hardware(auto_exposure=body.auto_exposure, exposure=body.exposure, brightness=body.brightness)
    return camera.get_hardware()


@app.post("/api/camera/reset")
def reset_camera():
    return camera.reset_all_adjustments()


@app.get("/api/events")
def list_events(limit: int = 50):
    return events.list(limit=limit)


@app.post("/api/events/record")
def record_now():
    """Manually fires every enabled action (records a clip, etc.) right now,
    independent of any detector -- e.g. a "record clip" button."""
    event = camera.manual_trigger("manual")
    if event is None:
        raise HTTPException(503, "camera not ready")
    return event


@app.get("/api/events/{event_id}/image")
def event_image(event_id: str):
    try:
        thumbnail = events.get_thumbnail(event_id)
    except ValueError:
        raise HTTPException(404, "no such event")
    if thumbnail is None:
        raise HTTPException(404, "no thumbnail yet for that event")
    return Response(content=thumbnail, media_type="image/jpeg")


@app.get("/api/events/{event_id}/video")
def event_video(event_id: str):
    try:
        path = events.video_path(event_id)
    except ValueError:
        raise HTTPException(404, "no such event")
    if path is None or not path.exists():
        raise HTTPException(404, "no video for that event")
    return FileResponse(path, media_type="video/mp4")


class FlagUpdate(BaseModel):
    flagged: bool


@app.post("/api/events/{event_id}/flag")
def flag_event(event_id: str, body: FlagUpdate):
    events.set_flag(event_id, body.flagged)
    return {"id": event_id, "flagged": body.flagged}


class DetectorToggle(BaseModel):
    enabled: bool


@app.post("/api/detectors/{name}/toggle")
def toggle_detector(name: str, body: DetectorToggle):
    detector = camera.get_detector(name)
    if detector is None:
        raise HTTPException(404, f"no detector named {name}")
    detector.enabled = body.enabled
    detector_config = load_config().get("detectors", {})
    detector_config[name] = body.enabled
    save_config(detectors=detector_config)
    return {"name": name, "enabled": detector.enabled}


@app.post("/api/actions/{name}/toggle")
def toggle_action(name: str, body: DetectorToggle):
    action = camera.get_action(name)
    if action is None:
        raise HTTPException(404, f"no action named {name}")
    action.enabled = body.enabled
    action_config = load_config().get("actions", {})
    action_config[name] = body.enabled
    save_config(actions=action_config)
    return {"name": name, "enabled": action.enabled}


@app.get("/api/toggles")
def get_toggles():
    """Every on/off pipeline stage in one place, uncategorized detail
    included -- lets one generic Stream Deck button work for detectors,
    actions, or image-processing stages alike without knowing in advance
    which one it'll be pointed at (see the plugin's Pipeline Toggle action)."""
    status = camera.status
    objects_enabled = next((d["enabled"] for d in status["detectors"] if d["name"] == "objects"), True)
    return {
        "detectors": [{"name": d["name"], "enabled": d["enabled"]} for d in status["detectors"]],
        "actions": status["actions"],
        "image": [{"name": name, "enabled": enabled} for name, enabled in camera.get_image_toggles().items()],
        "classes": [
            {"name": name, "enabled": enabled and objects_enabled}
            for name, enabled in camera.get_object_classes().items()
        ],
    }


@app.post("/api/toggles/{category}/{name}/toggle")
def toggle_generic(category: str, name: str, body: DetectorToggle):
    if category == "detectors":
        return toggle_detector(name, body)
    if category == "actions":
        return toggle_action(name, body)
    if category == "image":
        try:
            camera.set_image_toggle(name, body.enabled)
        except ValueError as e:
            raise HTTPException(404, str(e))
        return {"name": name, "enabled": body.enabled}
    if category == "classes":
        try:
            camera.set_object_class(name, body.enabled)
        except ValueError as e:
            raise HTTPException(404, str(e))
        return {"name": name, "enabled": body.enabled}
    raise HTTPException(404, f"no such toggle category {category!r} (expected detectors, actions, image, or classes)")


@app.get("/api/webhook")
def get_webhook():
    action = camera.get_action("webhook")
    return {"url": getattr(action, "url", None)}


class WebhookUrlUpdate(BaseModel):
    url: Optional[str] = None


@app.post("/api/webhook")
def set_webhook(body: WebhookUrlUpdate):
    action = camera.get_action("webhook")
    if action is None:
        raise HTTPException(404, "no webhook action registered")
    action.set_url(body.url)
    return {"url": action.url}


@app.post("/api/pipeline/{detector_name}/{action_name}/toggle")
def toggle_pipeline_link(detector_name: str, action_name: str, body: DetectorToggle):
    """Wires (or unwires) one detector's events from one action -- e.g. have
    motion record clips but not fire the webhook, while person does both."""
    try:
        camera.set_pipeline_link(detector_name, action_name, body.enabled)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"detector": detector_name, "action": action_name, "enabled": body.enabled}


@app.delete("/api/events/{event_id}")
def delete_event(event_id: str):
    try:
        deleted = events.delete(event_id)
    except ValueError:
        deleted = False
    if not deleted:
        raise HTTPException(404, "no such event")
    return {"id": event_id, "deleted": True}


@app.post("/api/events/clear-unsaved")
def clear_unsaved_events():
    return {"deleted": events.delete_unsaved()}


@app.post("/api/system/open-recordings-folder")
def open_recordings_folder():
    """Opens the videos folder in Explorer on the machine running the
    server. Only makes sense on that specific machine -- there's nowhere
    else for a folder window to open to."""
    if os.name != "nt":
        raise HTTPException(501, "opening a folder is only supported on the Windows host")
    subprocess.Popen(["explorer", str(VIDEO_DIR)])
    return {"opened": str(VIDEO_DIR)}


@app.post("/api/system/shutdown")
def shutdown_server():
    """Gracefully stops the server (camera released, gc thread stopped, mdns
    unregistered via the normal lifespan shutdown) -- only works when
    launched via run.py, which is what start.bat does.

    Uvicorn's graceful shutdown waits for in-flight connections to finish
    before it ever reaches that lifespan teardown -- and /api/stream is a
    long-lived MJPEG connection that never finishes on its own, so a browser
    tab left open on the live feed can hang the shutdown indefinitely,
    leaving the process (and its lock on the camera) stuck. The watchdog
    below forces the process to exit a few seconds later regardless, so this
    button is reliable even with a tab open -- any in-flight stream just
    gets cut off, which is an acceptable tradeoff for an explicit shutdown."""
    server = getattr(app.state, "server", None)
    if server is None:
        raise HTTPException(501, "graceful shutdown isn't available for this launch method")

    global _shutting_down
    _shutting_down = True  # anyone polling /api/status during the grace window below sees this
    server.should_exit = True

    def _force_exit():
        time.sleep(5)
        os._exit(0)

    threading.Thread(target=_force_exit, daemon=True).start()
    return {"shutting_down": True}


if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
