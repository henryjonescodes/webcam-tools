import time
from typing import Optional

import cv2
import numpy as np

from .base import Detector

DOWNSCALE_WIDTH = 320


class PersonDetector(Detector):
    """OpenCV's built-in HOG pedestrian detector -- the original ask that
    kicked this whole project off ("detect when a delivery driver is here"),
    distinguishing an actual person from a car passing or leaves blowing
    (which MotionDetector can't tell apart). Heavier than motion diffing, so
    it self-throttles to run_interval regardless of how often process() gets
    called, on top of the normal DETECT_EVERY_N_FRAMES throttle in camera.py.
    """

    name = "person"
    heavy = True  # runs on the slow detection loop, not the fast capture loop

    def __init__(self, cooldown_seconds: float = 8.0, run_interval: float = 1.0):
        self.enabled = True
        self.cooldown_seconds = cooldown_seconds
        self.run_interval = run_interval
        self._hog = cv2.HOGDescriptor()
        self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        self._last_run_at = 0.0
        self._last_event_at = 0.0

    def process(self, frame: np.ndarray) -> Optional[dict]:
        if not self.enabled:
            return None

        now = time.time()
        if now - self._last_run_at < self.run_interval:
            return None
        self._last_run_at = now

        height, width = frame.shape[:2]
        if width > DOWNSCALE_WIDTH:
            scale = DOWNSCALE_WIDTH / width
            frame = cv2.resize(frame, (DOWNSCALE_WIDTH, int(height * scale)), interpolation=cv2.INTER_AREA)

        boxes, _weights = self._hog.detectMultiScale(frame, winStride=(8, 8), padding=(8, 8), scale=1.05)
        if len(boxes) == 0:
            return None

        if now - self._last_event_at < self.cooldown_seconds:
            return None
        self._last_event_at = now

        return {"type": "person", "meta": {"count": int(len(boxes))}}

    def reset(self):
        self._last_run_at = 0.0
        self._last_event_at = 0.0
