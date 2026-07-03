from abc import ABC, abstractmethod
from typing import Optional
import numpy as np


class Detector(ABC):
    """Extension point for the frame-processing pipeline.

    To add a new detector (e.g. a YOLO person/vehicle model), subclass this,
    implement `process`, and append an instance to the `detectors` list built
    in `camera.py`. Nothing else in the app needs to change.

    Two independent loops feed detectors: a fast one (capture cadence, the
    pristine frame straight off the sensor) and a slow one (its own timer,
    decoupled from capture so it can never block a frame read). Set
    `heavy = True` to run on the slow loop -- appropriate for anything
    costlier than simple frame diffing (a real model, multi-scale search,
    etc). Leave it False (the default) for anything cheap and
    latency-sensitive, like motion detection, that wants every frame.
    """

    name: str = "detector"
    enabled: bool = True
    heavy: bool = False

    @abstractmethod
    def process(self, frame: np.ndarray) -> Optional[dict]:
        """Inspect a frame. Return an event dict (e.g. {"type": ..., "meta": {...}})
        if something noteworthy happened, otherwise None. Called on every
        captured frame (or a throttled subset), so keep it fast.
        """
        raise NotImplementedError

    def reset(self):
        """Called when the active camera changes. Override to clear any
        state derived from previous frames (e.g. a background/diff model) so
        switching cameras doesn't trigger a spurious event."""
        pass
