import time
from typing import Optional

import cv2
import numpy as np

from .base import Detector

DOWNSCALE_WIDTH = 320


class MotionDetector(Detector):
    """Simple background-subtraction motion detector. Diffs a downscaled copy
    of the frame (cheap enough to not compete with whatever else is using the
    CPU/camera) and emits at most one event per cooldown window so a moving
    branch outside doesn't spam the event feed.
    """

    name = "motion"

    def __init__(self, min_area: int = 600, cooldown_seconds: float = 4.0):
        self.enabled = True
        self.min_area = min_area
        self.cooldown_seconds = cooldown_seconds
        self._prev_gray: Optional[np.ndarray] = None
        self._last_event_at = 0.0

    def process(self, frame: np.ndarray) -> Optional[dict]:
        if not self.enabled:
            return None

        height, width = frame.shape[:2]
        if width > DOWNSCALE_WIDTH:
            scale = DOWNSCALE_WIDTH / width
            frame = cv2.resize(frame, (DOWNSCALE_WIDTH, int(height * scale)), interpolation=cv2.INTER_AREA)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (11, 11), 0)

        if self._prev_gray is None:
            self._prev_gray = gray
            return None

        diff = cv2.absdiff(self._prev_gray, gray)
        self._prev_gray = gray

        thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        largest_area = max((cv2.contourArea(c) for c in contours), default=0)
        if largest_area < self.min_area:
            return None

        now = time.time()
        if now - self._last_event_at < self.cooldown_seconds:
            return None

        self._last_event_at = now
        return {"type": "motion", "meta": {"area": int(largest_area)}}

    def reset(self):
        self._prev_gray = None
