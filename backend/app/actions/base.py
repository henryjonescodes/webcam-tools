from abc import ABC, abstractmethod

import numpy as np


class Action(ABC):
    """Extension point for event-triggered behavior. Detectors decide *when*
    something noteworthy happened; Actions decide *what to do about it*.
    Motion -> record-a-clip is just the first wiring of this pipeline - to
    make any event also (say) hit a webhook or flash a light, add a new
    Action subclass and append it to `self.actions` in camera.py. Nothing
    about detection or capture needs to change.
    """

    name: str = "action"
    enabled: bool = True

    @abstractmethod
    def trigger(self, event, frame: np.ndarray) -> None:
        """Called once when a detector fires an event. `frame` is the display
        (post-processed) frame at the moment of the trigger."""
        raise NotImplementedError

    def tick(self, frame: np.ndarray) -> None:
        """Called on every captured frame, regardless of whether an event
        just fired. Override for actions with ongoing state (e.g. an active
        recording that needs more frames after the trigger)."""
        pass

    @property
    def is_active(self) -> bool:
        """Whether this action currently has work in progress (e.g. mid-recording)."""
        return False

    def reset(self):
        """Called when the camera switches/pauses, mirroring Detector.reset()."""
        pass

    def shutdown(self):
        """Called once on app shutdown to flush/finalize any in-progress work."""
        pass
