import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from .base import Detector

MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "models"

# YOLOv4-tiny (Darknet) run through cv2.dnn -- chosen deliberately over a
# torch/ultralytics stack. It's a single ~24MB weights file OpenCV loads
# natively, so there's no heavy new dependency for someone forking this to
# run a hobby cam, and it does ~100ms/frame on CPU, which is fine on the slow
# detection thread. It's a night-and-day upgrade over the old HOG pedestrian
# detector: far fewer false positives, and it knows 80 object classes instead
# of only "person". Files auto-download to data/models/ on first use.
_MODEL_FILES = {
    "yolov4-tiny.cfg": "https://raw.githubusercontent.com/AlexeyAB/darknet/master/cfg/yolov4-tiny.cfg",
    "yolov4-tiny.weights": "https://github.com/AlexeyAB/darknet/releases/download/darknet_yolo_v4_pre/yolov4-tiny.weights",
    "coco.names": "https://raw.githubusercontent.com/AlexeyAB/darknet/master/data/coco.names",
}

# The "classes" the UI/API exposes, each mapped to the COCO class names the
# model actually predicts. "package" is virtual: COCO has no cardboard-box
# class, so a parcel/delivery is approximated by the carried-luggage classes
# it does know. A true shipping-box detector would need a custom-trained model
# (noted in DREAMS.md) -- but "person carrying a bag/case up to the door" is
# most of the delivery signal anyway, and person+package firing together is a
# decent "someone's dropping something off" heuristic.
CLASS_GROUPS = {
    "person": ["person"],
    "bicycle": ["bicycle"],
    "package": ["backpack", "handbag", "suitcase"],
}
DEFAULT_CLASSES = {"person": True, "bicycle": True, "package": False}

_INPUT_SIZE = 416
_CONF_THRESHOLD = 0.35
_NMS_THRESHOLD = 0.45

# Proximity gate -- the "no manual zones" trick. Instead of hand-painting a
# region of interest per camera, we just require a detection's box to cover at
# least this fraction of the frame, i.e. be big enough (= close enough) to
# matter. That automatically ignores distant street traffic and tiny far-off
# figures without any per-camera setup: object detection is already semantic
# ("that's a person"), so all that's left is "is it close enough to care?".
DEFAULT_MIN_AREA_FRAC = 0.02


def _ensure_model_files() -> bool:
    """Downloads the model files to data/models/ if missing. Returns whether
    all three are present afterward. Best-effort: on failure the detector just
    stays disabled and says so, same spirit as the camera-name fallback."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in _MODEL_FILES.items():
        dest = MODELS_DIR / name
        if dest.exists() and dest.stat().st_size > 0:
            continue
        try:
            print(f"[objects] downloading {name} (first run only)...", flush=True)
            urllib.request.urlretrieve(url, dest)
        except Exception as e:  # network down, URL moved, etc.
            print(f"[objects] could not download {name}: {e}", flush=True)
            return False
    return True


class ObjectDetector(Detector):
    """General object detection (YOLOv4-tiny via cv2.dnn). Replaces the old
    HOG person detector with something that actually works and generalizes:
    one detector, a configurable set of target classes (person, bicycle,
    package). Fires a distinct event *type* per class (so the webhook payload
    and Recording Status naturally read "person" / "bicycle" / "package"),
    with per-class cooldown so a person lingering in frame doesn't spam.

    Runs on the slow detection thread (heavy=True) and self-throttles to
    run_interval on top of that, since inference is ~100ms and doesn't need to
    run every frame."""

    name = "objects"
    heavy = True

    def __init__(
        self,
        get_classes: Callable[[], dict],
        min_area_frac: float = DEFAULT_MIN_AREA_FRAC,
        cooldown_seconds: float = 8.0,
        run_interval: float = 0.75,
    ):
        self.enabled = True
        self._get_classes = get_classes
        self.min_area_frac = min_area_frac
        self.cooldown_seconds = cooldown_seconds
        self.run_interval = run_interval

        self._net = None
        self._names: list[str] = []
        self._out_layers = None
        self._load_failed = False
        self._last_run_at = 0.0
        self._last_event_at: dict[str, float] = {}

    def _ensure_model(self) -> bool:
        if self._net is not None:
            return True
        if self._load_failed:
            return False
        if not _ensure_model_files():
            self._load_failed = True
            return False
        try:
            net = cv2.dnn.readNetFromDarknet(
                str(MODELS_DIR / "yolov4-tiny.cfg"),
                str(MODELS_DIR / "yolov4-tiny.weights"),
            )
            net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            self._names = [
                line.strip()
                for line in (MODELS_DIR / "coco.names").read_text().splitlines()
                if line.strip()
            ]
            self._out_layers = net.getUnconnectedOutLayersNames()
            self._net = net
            print("[objects] model loaded", flush=True)
            return True
        except Exception as e:
            print(f"[objects] model load failed: {e}", flush=True)
            self._load_failed = True
            return False

    def process(self, frame: np.ndarray) -> Optional[dict]:
        if not self.enabled:
            return None

        now = time.time()
        if now - self._last_run_at < self.run_interval:
            return None
        self._last_run_at = now

        # Resolve which COCO names we're currently looking for. Doing this
        # first means a fully-disabled set skips inference entirely.
        wanted: dict[str, str] = {}  # coco name -> group label
        for group, on in self._get_classes().items():
            if not on:
                continue
            for coco in CLASS_GROUPS.get(group, []):
                wanted[coco] = group
        if not wanted:
            return None

        if not self._ensure_model():
            return None

        H, W = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (_INPUT_SIZE, _INPUT_SIZE), swapRB=True, crop=False)
        self._net.setInput(blob)
        outputs = self._net.forward(self._out_layers)

        min_area = self.min_area_frac * W * H
        boxes: list[list[int]] = []
        confs: list[float] = []
        labels: list[str] = []
        for out in outputs:
            for det in out:
                scores = det[5:]
                cid = int(np.argmax(scores))
                conf = float(scores[cid])
                if conf < _CONF_THRESHOLD:
                    continue
                coco = self._names[cid] if cid < len(self._names) else None
                if coco not in wanted:
                    continue
                w, h = det[2] * W, det[3] * H
                if w * h < min_area:  # proximity gate
                    continue
                cx, cy = det[0] * W, det[1] * H
                boxes.append([int(cx - w / 2), int(cy - h / 2), int(w), int(h)])
                confs.append(conf)
                labels.append(wanted[coco])

        if not boxes:
            return None
        idxs = cv2.dnn.NMSBoxes(boxes, confs, _CONF_THRESHOLD, _NMS_THRESHOLD)
        if len(idxs) == 0:
            return None

        # Best surviving detection per label, then fire the single
        # highest-confidence label that isn't still on cooldown. One event per
        # call (the Detector contract) -- other present labels fire on
        # subsequent cycles ~run_interval apart, so a delivery person + their
        # bag still both register within a second or two.
        best: dict[str, tuple] = {}
        for i in idxs.flatten():
            lbl = labels[i]
            if lbl not in best or confs[i] > best[lbl][0]:
                best[lbl] = (confs[i], boxes[i])

        for lbl, (conf, box) in sorted(best.items(), key=lambda kv: -kv[1][0]):
            if now - self._last_event_at.get(lbl, 0.0) < self.cooldown_seconds:
                continue
            self._last_event_at[lbl] = now
            return {
                "type": lbl,
                "meta": {
                    "confidence": round(conf, 2),
                    "box": box,
                    "present": sorted(best.keys()),
                },
            }
        return None

    def reset(self):
        self._last_run_at = 0.0
        self._last_event_at = {}
