import threading

import numpy as np

from .base import Action

try:
    import winsound
except ImportError:
    winsound = None  # not on Windows -- action just becomes a no-op


class SoundAlarmAction(Action):
    """Plays a short beep on the host PC for any event -- no external
    services, no setup, the simplest possible "something happened" alert.
    Off by default (an audible alarm on every bit of motion is a lot more
    intrusive than a silent toggle) -- flip it on in the Pipeline tab.
    Runs the beep on its own thread so a ~200ms tone can't stall capture."""

    name = "sound_alarm"
    enabled = False

    def trigger(self, event, frame: np.ndarray) -> None:
        if winsound is None:
            return
        threading.Thread(target=self._beep, daemon=True).start()

    def _beep(self):
        try:
            winsound.Beep(1000, 200)
        except RuntimeError:
            pass  # no audio device -- fine, just skip it
