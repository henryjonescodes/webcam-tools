import os
import threading
import time
from typing import Optional

import cv2
import numpy as np

from .actions.base import Action
from .actions.record_clip import RecordClipAction
from .actions.sound_alarm import SoundAlarmAction
from .actions.webhook import WebhookAction
from .config import load_config, save_config
from .detection.base import Detector
from .detection.motion import MotionDetector
from .detection.objects import DEFAULT_CLASSES, ObjectDetector
from .events import EventStore

JPEG_QUALITY = 80
DETECT_EVERY_N_FRAMES = 5

DEFAULT_ADJUST = {"brightness": 0, "contrast": 1.0, "saturation": 1.0}
DEFAULT_ROTATION = 0

# Generic on/off image-pipeline stages -- unlike brightness/contrast/etc
# (continuous sliders), these are simple toggles, kept in their own small
# registry (get_image_toggles/set_image_toggle) so adding another one later
# doesn't need a new endpoint or a new Stream Deck action, same spirit as
# the detector/action pipeline links.
DEFAULT_IMAGE_TOGGLES = {"anti_glare": False}

_ROTATE_CODES = {
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}

# Compresses highlights above the threshold instead of letting them clip to
# pure white -- cuts glare/reflective blowout (a window, a windshield, a wet
# driveway at night) without darkening the rest of the image. A LUT since
# it's a fixed curve, not user-tunable -- built once at import time.
_ANTI_GLARE_THRESHOLD = 180.0
_ANTI_GLARE_COMPRESSION = 0.35
_ANTI_GLARE_LUT = np.arange(256, dtype=np.float32)
_over = _ANTI_GLARE_LUT > _ANTI_GLARE_THRESHOLD
_ANTI_GLARE_LUT[_over] = _ANTI_GLARE_THRESHOLD + (_ANTI_GLARE_LUT[_over] - _ANTI_GLARE_THRESHOLD) * _ANTI_GLARE_COMPRESSION
_ANTI_GLARE_LUT = np.clip(_ANTI_GLARE_LUT, 0, 255).astype(np.uint8)

# Hardware (pre-capture) controls: applied via cv2.VideoCapture.set() so they
# affect the sensor/ISP before a frame ever reaches software. This is what
# actually recovers blown-out highlights -- once a pixel clips to white in
# post-processing the detail is gone, so fixing exposure at the source is the
# only real fix. auto_exposure=True leaves the driver's own auto-exposure in
# control (the safe, no-op default for a camera we haven't tuned yet).
DEFAULT_HARDWARE = {"auto_exposure": True, "exposure": -6, "brightness": 128}


def resolve_initial_adjustments() -> dict:
    cfg = load_config().get("image_adjust", {})
    return {**DEFAULT_ADJUST, **cfg}


def resolve_initial_camera_index() -> int:
    """A camera picked via the UI (persisted to data/config.json) wins. Falls
    back to the CAMERA_INDEX env var, then 0."""
    cfg = load_config()
    if "camera_index" in cfg:
        return cfg["camera_index"]
    return int(os.environ.get("CAMERA_INDEX", "0"))


def list_available_cameras() -> list[dict]:
    """Enumerate connected cameras with their friendly names (Windows, via
    DirectShow). Falls back to unnamed index probing if pygrabber/pywin32
    isn't available."""
    try:
        import pythoncom
        from pygrabber.dshow_graph import FilterGraph

        pythoncom.CoInitialize()
        try:
            names = FilterGraph().get_input_devices()
        finally:
            pythoncom.CoUninitialize()
        return [{"index": i, "name": name} for i, name in enumerate(names)]
    except Exception:
        devices = []
        backend = cv2.CAP_DSHOW if os.name == "nt" else 0
        for i in range(5):
            cap = cv2.VideoCapture(i, backend)
            if cap.isOpened():
                devices.append({"index": i, "name": f"Camera {i}"})
            cap.release()
        return devices


class CameraStream:
    """Owns the webcam. Runs a background thread that continuously grabs
    frames, keeps the latest one (as jpeg bytes, ready to stream), feeds
    frames through an ordered list of Detectors, and dispatches whatever
    events those detectors fire to an ordered list of Actions.

    Detectors decide *when* something noteworthy happened; Actions decide
    *what to do about it* (recording a clip is just the first one). Add a
    new Detector or Action class and append an instance to `self.detectors`
    / `self.actions` to extend either side of the pipeline without touching
    capture, streaming, or event storage.
    """

    def __init__(self, events: EventStore, camera_index: Optional[int] = None):
        self.events = events
        self.camera_index = camera_index if camera_index is not None else resolve_initial_camera_index()
        self._requested_index = self.camera_index
        # Object detection watches a configurable set of classes; the detector
        # reads self._object_classes lazily at inference time, so it's fine
        # that it's populated a few lines below.
        self._object_classes: dict = {**DEFAULT_CLASSES, **load_config().get("object_classes", {})}
        self.detectors: list[Detector] = [
            MotionDetector(),
            ObjectDetector(lambda: self._object_classes),
        ]
        self.actions: list[Action] = [RecordClipAction(events, lambda: self._fps), SoundAlarmAction(), WebhookAction()]

        self._cap: Optional[cv2.VideoCapture] = None
        self._latest_jpeg: Optional[bytes] = None
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_raw_frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._connected = False
        self._paused = False
        self._frame_count = 0
        self._fps = 0.0
        self._stop = threading.Event()
        # Two independent loops: _run is the fast one (capture cadence,
        # feeds preview/recording/light detectors like motion -- nothing may
        # block it for long). _run_heavy_detection is its own thread on its
        # own timer, reading whatever frame is freshest instead of taking
        # frames off the capture loop directly, so a slow detector (person)
        # can never stall a camera read.
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._heavy_thread = threading.Thread(target=self._run_heavy_detection, daemon=True)

        self._pipeline_links: dict = load_config().get("pipeline_links", {})

        adjust = resolve_initial_adjustments()
        self._brightness = adjust["brightness"]
        self._contrast = adjust["contrast"]
        self._saturation = adjust["saturation"]
        self._rotation = load_config().get("rotation", DEFAULT_ROTATION)
        self._image_toggles: dict = {**DEFAULT_IMAGE_TOGGLES, **load_config().get("image_toggles", {})}

        # Per-camera hardware profile: resolved (by camera name) and applied
        # each time a capture is opened -- see _open_capture / _camera_name.
        self._active_camera_name: Optional[str] = None
        self._hardware: dict = dict(DEFAULT_HARDWARE)

    def start(self):
        self._thread.start()
        self._heavy_thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=2)
        self._heavy_thread.join(timeout=2)
        if self._cap is not None:
            self._cap.release()
        for action in self.actions:
            action.shutdown()

    def link_enabled(self, detector_name: str, action_name: str) -> bool:
        """Whether a given detector's events fire a given action -- defaults
        to on (every action runs for every detector) unless explicitly wired
        off, so existing setups keep working without any configuration."""
        return self._pipeline_links.get(detector_name, {}).get(action_name, True)

    def set_pipeline_link(self, detector_name: str, action_name: str, enabled: bool):
        if self.get_detector(detector_name) is None:
            raise ValueError(f"no detector named {detector_name}")
        if self.get_action(action_name) is None:
            raise ValueError(f"no action named {action_name}")
        self._pipeline_links.setdefault(detector_name, {})[action_name] = enabled
        save_config(pipeline_links=self._pipeline_links)

    def switch(self, camera_index: int):
        """Request a switch to a different camera index. Picked up by the
        capture loop on its next iteration; persisted so it survives restarts."""
        self._requested_index = camera_index
        save_config(camera_index=camera_index)

    def pause(self):
        """Fully releases the camera device so other apps (Zoom, etc.) can use it."""
        self._paused = True

    def resume(self):
        self._paused = False

    def get_adjustments(self) -> dict:
        return {"brightness": self._brightness, "contrast": self._contrast, "saturation": self._saturation}

    def set_adjustments(self, brightness=None, contrast=None, saturation=None):
        if brightness is not None:
            self._brightness = brightness
        if contrast is not None:
            self._contrast = contrast
        if saturation is not None:
            self._saturation = saturation
        save_config(image_adjust=self.get_adjustments())

    def get_rotation(self) -> int:
        return self._rotation

    def set_rotation(self, degrees: int):
        if degrees not in (0, 90, 180, 270):
            raise ValueError("rotation must be one of 0, 90, 180, 270")
        self._rotation = degrees
        save_config(rotation=degrees)
        # A 90/270 rotation changes frame dimensions -- the motion detector
        # caches a previous-frame buffer at the old size and would crash
        # diffing it against the new one, so it needs the same reset a
        # camera switch gets.
        self._reset_pipeline()

    def get_image_toggles(self) -> dict:
        return dict(self._image_toggles)

    def set_image_toggle(self, name: str, enabled: bool):
        if name not in self._image_toggles:
            raise ValueError(f"no image toggle named {name}")
        self._image_toggles[name] = enabled
        save_config(image_toggles=self._image_toggles)

    def get_object_classes(self) -> dict:
        """Which object-detection classes (person/bicycle/package) are armed.
        Individually toggleable so the same generic Pipeline Toggle button
        (web + Stream Deck) can arm 'watch for bikes' vs 'watch for people'."""
        return dict(self._object_classes)

    def set_object_class(self, name: str, enabled: bool):
        if name not in self._object_classes:
            raise ValueError(f"no object class named {name}")
        self._object_classes[name] = enabled
        save_config(object_classes=self._object_classes)

    def reset_all_adjustments(self) -> dict:
        """Resets both layers (hardware + post-processing) to their defaults
        in one shot -- the "start fresh" button."""
        self._brightness = DEFAULT_ADJUST["brightness"]
        self._contrast = DEFAULT_ADJUST["contrast"]
        self._saturation = DEFAULT_ADJUST["saturation"]
        save_config(image_adjust=self.get_adjustments())

        self.set_hardware(
            auto_exposure=DEFAULT_HARDWARE["auto_exposure"],
            exposure=DEFAULT_HARDWARE["exposure"],
            brightness=DEFAULT_HARDWARE["brightness"],
        )
        return {"adjustments": self.get_adjustments(), "hardware": self.get_hardware()}

    def get_hardware(self) -> dict:
        return {**self._hardware, "camera_name": self._active_camera_name}

    def set_hardware(self, auto_exposure=None, exposure=None, brightness=None):
        if auto_exposure is not None:
            self._hardware["auto_exposure"] = auto_exposure
        if exposure is not None:
            self._hardware["exposure"] = exposure
        if brightness is not None:
            self._hardware["brightness"] = brightness
        self._apply_hardware_profile()

        if self._active_camera_name:
            profiles = load_config().get("camera_profiles", {})
            profiles[self._active_camera_name] = self._hardware
            save_config(camera_profiles=profiles)

    def _camera_name(self) -> Optional[str]:
        return next((d["name"] for d in list_available_cameras() if d["index"] == self.camera_index), None)

    def _load_hardware_profile(self, camera_name: Optional[str]) -> dict:
        profiles = load_config().get("camera_profiles", {})
        profile = profiles.get(camera_name, {}) if camera_name else {}
        return {**DEFAULT_HARDWARE, **profile}

    def _apply_hardware_profile(self):
        if self._cap is None:
            return
        h = self._hardware
        # DirectShow convention: 0.75 = auto, 0.25 = manual. Driver-dependent,
        # but this is the standard OpenCV+DSHOW quirk.
        self._cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75 if h["auto_exposure"] else 0.25)
        if not h["auto_exposure"]:
            self._cap.set(cv2.CAP_PROP_EXPOSURE, h["exposure"])
        self._cap.set(cv2.CAP_PROP_BRIGHTNESS, h["brightness"])

    def _apply_rotation(self, frame):
        code = _ROTATE_CODES.get(self._rotation)
        return cv2.rotate(frame, code) if code is not None else frame

    def _apply_adjustments(self, frame):
        if self._image_toggles.get("anti_glare"):
            frame = cv2.LUT(frame, _ANTI_GLARE_LUT)
        if self._contrast != 1.0 or self._brightness != 0:
            frame = cv2.convertScaleAbs(frame, alpha=self._contrast, beta=self._brightness)
        if self._saturation != 1.0:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[..., 1] = np.clip(hsv[..., 1] * self._saturation, 0, 255)
            frame = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
        return frame

    def get_jpeg(self) -> Optional[bytes]:
        with self._lock:
            return self._latest_jpeg

    def get_detector(self, name: str) -> Optional[Detector]:
        return next((d for d in self.detectors if d.name == name), None)

    def get_action(self, name: str) -> Optional[Action]:
        return next((a for a in self.actions if a.name == name), None)

    @property
    def status(self) -> dict:
        record_action = self.get_action("record_clip")
        return {
            "connected": self._connected,
            "paused": self._paused,
            "recording": any(a.is_active for a in self.actions),
            "recording_event_type": getattr(record_action, "current_event_type", None),
            "camera_index": self.camera_index,
            "camera_name": self._active_camera_name,
            "fps": round(self._fps, 1),
            "detectors": [
                {
                    "name": d.name,
                    "enabled": d.enabled,
                    "heavy": d.heavy,
                    "links": {a.name: self.link_enabled(d.name, a.name) for a in self.actions},
                }
                for d in self.detectors
            ],
            "actions": [{"name": a.name, "enabled": a.enabled} for a in self.actions],
        }

    def _open_capture(self):
        backend = cv2.CAP_DSHOW if os.name == "nt" else 0
        cap = cv2.VideoCapture(self.camera_index, backend)
        if cap.isOpened():
            self._cap = cap
            self._connected = True
            self._active_camera_name = self._camera_name()
            self._hardware = self._load_hardware_profile(self._active_camera_name)
            self._apply_hardware_profile()
        else:
            self._connected = False

    def _reset_pipeline(self):
        for detector in self.detectors:
            detector.reset()
        for action in self.actions:
            action.reset()

    def _run(self):
        last_fps_check = time.time()
        frames_since_check = 0
        consecutive_read_failures = 0
        MAX_READ_FAILURES = 5  # ~2.5s of failed reads before forcing a reconnect

        while not self._stop.is_set():
            if self._paused:
                if self._cap is not None:
                    self._cap.release()
                    self._cap = None
                self._connected = False
                self._reset_pipeline()
                with self._lock:
                    self._latest_jpeg = None
                time.sleep(0.5)
                continue

            if self._requested_index != self.camera_index:
                if self._cap is not None:
                    self._cap.release()
                self.camera_index = self._requested_index
                self._open_capture()
                self._reset_pipeline()
                continue

            if self._cap is None or not self._cap.isOpened():
                self._connected = False
                time.sleep(1.0)
                self._open_capture()
                continue

            ok, raw_frame = self._cap.read()
            if not ok:
                self._connected = False
                consecutive_read_failures += 1
                # A dropped USB device often doesn't flip isOpened() to
                # False on its own -- the loop's top-of-iteration check
                # would keep passing and we'd retry reads on the same dead
                # handle forever. Force a real release + reopen instead of
                # waiting for a signal that may never come.
                if consecutive_read_failures >= MAX_READ_FAILURES:
                    self._cap.release()
                    self._cap = None
                    consecutive_read_failures = 0
                time.sleep(0.5)
                continue

            consecutive_read_failures = 0
            self._connected = True
            self._frame_count += 1
            frames_since_check += 1

            # Mount orientation is a property of the physical setup, not a
            # viewing preference -- apply it before anything else touches the
            # frame so detection, display, and recordings all agree on "up".
            raw_frame = self._apply_rotation(raw_frame)

            # detection runs on the raw frame so brightness/contrast/saturation
            # tweaks (for viewing) don't shift motion sensitivity; everything
            # the user sees or saves (stream, pre-roll, recording) uses the
            # adjusted frame.
            frame = self._apply_adjustments(raw_frame)

            ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if ok:
                jpeg_bytes = jpeg.tobytes()
                with self._lock:
                    self._latest_jpeg = jpeg_bytes
                    self._latest_frame = frame
                    self._latest_raw_frame = raw_frame

            try:
                # Only the light (non-heavy) detectors run here, at capture
                # cadence, on the pristine frame -- e.g. motion, which wants
                # every frame and is cheap enough not to compete for it.
                # Heavy detectors run on their own thread/timer entirely
                # (see _run_heavy_detection) so they can never delay a read.
                if self._frame_count % DETECT_EVERY_N_FRAMES == 0:
                    self._run_detectors(raw_frame, frame, heavy=False)

                for action in self.actions:
                    action.tick(frame)
            except Exception as e:
                # A bug in a detector/action (e.g. cached state that doesn't
                # match the current frame size after a rotation/camera
                # change) must not be able to kill this whole thread --
                # that would silently freeze the feed while /api/status
                # kept reporting connected=True, since only capture failures
                # were ever treated as a disconnect.
                print(f"Detector/action error (frame skipped): {e}", flush=True)

            now = time.time()
            if now - last_fps_check >= 2.0:
                self._fps = frames_since_check / (now - last_fps_check)
                frames_since_check = 0
                last_fps_check = now

    def _run_heavy_detection(self):
        """Independent loop for `heavy = True` detectors -- reads whatever
        frame is currently freshest rather than taking one off the capture
        loop, so a slow detector runs on its own schedule and can never
        block a camera read. The poll interval here is just a check-in
        cadence; each heavy detector self-throttles its actual (expensive)
        work internally (see ObjectDetector's run_interval)."""
        POLL_INTERVAL = 0.2

        while not self._stop.is_set():
            if self._paused or not self._connected:
                time.sleep(0.5)
                continue

            with self._lock:
                raw_frame = self._latest_raw_frame
                display_frame = self._latest_frame

            if raw_frame is None or display_frame is None:
                time.sleep(0.5)
                continue

            try:
                self._run_detectors(raw_frame, display_frame, heavy=True)
            except Exception as e:
                print(f"Heavy detector error (skipped): {e}", flush=True)

            time.sleep(POLL_INTERVAL)

    def _run_detectors(self, raw_frame, display_frame, heavy: bool):
        for detector in self.detectors:
            if detector.heavy != heavy or not detector.enabled:
                continue
            result = detector.process(raw_frame)
            if result:
                event = self.events.add(result["type"], meta=result.get("meta", {}))
                for action in self.actions:
                    if action.enabled and self.link_enabled(detector.name, action.name):
                        action.trigger(event, display_frame)

    def manual_trigger(self, event_type: str = "manual") -> Optional[dict]:
        """Fires every enabled action (e.g. records a clip) on demand, same
        as a detector firing, but from an explicit request (a Stream Deck
        button, say) instead of something the pipeline noticed itself."""
        with self._lock:
            frame = self._latest_frame
        if frame is None:
            return None

        event = self.events.add(event_type, meta={"source": "manual"})
        for action in self.actions:
            if action.enabled:
                action.trigger(event, frame)
        return event.to_dict()
