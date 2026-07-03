import os
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable, Optional

import imageio_ffmpeg
import numpy as np

from .base import Action
from ..events import EventStore

RECORD_SECONDS = 8
PREROLL_SECONDS = 2.0
VIDEO_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "videos"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

# Since run.py now runs headless under pythonw.exe (no console of its own),
# spawning a console app like ffmpeg without this flag makes Windows pop up
# a brand-new console window for it -- once per recording, i.e. every time
# motion fires. CREATE_NO_WINDOW only exists on Windows.
_POPEN_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


class RecordClipAction(Action):
    """Records an ~10s H.264 clip (2s pre-roll + 8s post-trigger) for
    whatever event fires it. Owns its own rolling pre-roll buffer, fed every
    frame via `tick()`, independent of anything else in the pipeline.

    `tick()` always comes from the fast capture loop, but `trigger()` can
    now come from either the fast loop (a light detector like motion) or the
    slow detection loop (a heavy one like person) -- `_lock` keeps those two
    threads from touching `_proc`/`_frames_left`/etc. at the same time."""

    name = "record_clip"

    def __init__(self, events: EventStore, fps_lookup: Callable[[], float]):
        self.enabled = True
        self.events = events
        self._fps_lookup = fps_lookup
        self._lock = threading.Lock()
        self._preroll: deque = deque()  # (timestamp, frame)
        self._proc: Optional[subprocess.Popen] = None
        self._event_id: Optional[str] = None
        self._event_type: Optional[str] = None
        self._frames_left = 0
        self._size = (0, 0)
        self._finalize_thread: Optional[threading.Thread] = None

    @property
    def is_active(self) -> bool:
        return self._proc is not None

    @property
    def current_event_type(self) -> Optional[str]:
        """The type (e.g. "motion", "manual") of the event currently being
        recorded, or None if idle. Lets callers show *why* it's recording,
        not just that it is."""
        return self._event_type if self._proc is not None else None

    def reset(self):
        with self._lock:
            self._preroll.clear()

    def tick(self, frame: np.ndarray) -> None:
        now = time.time()
        with self._lock:
            self._preroll.append((now, frame))
            while self._preroll and now - self._preroll[0][0] > PREROLL_SECONDS:
                self._preroll.popleft()

            if self._proc is not None:
                self._write_frame_locked(frame)

    def trigger(self, event, frame: np.ndarray) -> None:
        with self._lock:
            if self._proc is not None:
                # Already recording -- this event happened during that clip.
                # Point its thumbnail/video at the in-progress recording
                # instead of leaving it with no video it'll ever get (only
                # one recording can run at a time on a single camera stream).
                if self._event_id is not None:
                    self.events.set_video(event.id, f"{self._event_id}.mp4")
                return
            self._event_type = event.type
            self._start_locked(event.id, frame)

    def shutdown(self):
        with self._lock:
            self._finish_locked()
        if self._finalize_thread is not None:
            self._finalize_thread.join(timeout=5)

    def _start_locked(self, event_id: str, frame: np.ndarray):
        height, width = frame.shape[:2]
        width -= width % 2
        height -= height % 2
        fps = self._fps_lookup()
        if not fps or fps <= 1:
            fps = 15.0
        path = VIDEO_DIR / f"{event_id}.mp4"

        cmd = [
            FFMPEG_EXE, "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}", "-r", str(fps),
            "-i", "-",
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(path),
        ]
        try:
            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=_POPEN_FLAGS,
            )
        except OSError:
            return

        self._proc = proc
        self._event_id = event_id
        self._frames_left = int(fps * RECORD_SECONDS)
        self._size = (width, height)

        # dump buffered pre-roll frames (everything before this trigger frame,
        # which tick() already appended) so the clip shows what led up to the
        # event, not just what happened after it fired.
        for _, buffered in list(self._preroll)[:-1]:
            self._write_frame_locked(buffered, count=False)

    def _write_frame_locked(self, frame: np.ndarray, count: bool = True):
        if self._proc is None:
            return
        width, height = self._size
        h, w = frame.shape[:2]
        if (w, h) != (width, height):
            frame = frame[:height, :width]
        try:
            self._proc.stdin.write(frame.tobytes())
        except (BrokenPipeError, OSError):
            self._finish_locked()
            return
        if count:
            self._frames_left -= 1
            if self._frames_left <= 0:
                self._finish_locked()

    def _finish_locked(self):
        """Hands the ffmpeg process off to a background thread to flush/finalize
        (can take ~1s) so the capture loop (and the live stream) never stalls
        waiting on it."""
        if self._proc is None:
            return
        proc, event_id = self._proc, self._event_id
        self._proc = None
        self._event_id = None
        self._frames_left = 0

        def finalize():
            try:
                proc.stdin.close()
                proc.wait(timeout=15)
            except Exception:
                proc.kill()
            self.events.set_video(event_id, f"{event_id}.mp4")

        self._finalize_thread = threading.Thread(target=finalize, daemon=True)
        self._finalize_thread.start()
