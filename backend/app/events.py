import json
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from collections import deque
from threading import Lock
from typing import Optional

import cv2

# Every event ID this app generates matches this exactly (see EventStore.add
# below). event_id arrives at video_path/thumbnail_path straight from a URL
# path parameter with no other validation -- without this check, a crafted
# id (e.g. containing "../") sent to the video/image/delete endpoints could
# escape VIDEO_DIR/THUMBNAIL_DIR and touch files elsewhere on disk.
_EVENT_ID_RE = re.compile(r"^[0-9a-f]{12}$")


def _require_valid_event_id(event_id: str) -> str:
    if not _EVENT_ID_RE.match(event_id):
        raise ValueError(f"invalid event id: {event_id!r}")
    return event_id

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
VIDEO_DIR = DATA_DIR / "videos"
THUMBNAIL_DIR = DATA_DIR / "thumbnails"
LOG_FILE = DATA_DIR / "events.jsonl"
FLAGS_FILE = DATA_DIR / "flags.json"

VIDEO_DIR.mkdir(parents=True, exist_ok=True)
THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)

MAX_EVENTS = 2000


@dataclass
class Event:
    id: str
    type: str
    timestamp: float
    meta: dict = field(default_factory=dict)
    video: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class EventStore:
    """Durable event log (data/events.jsonl) mirrored into an in-memory ring
    buffer for fast API reads. Video clips live on disk under data/videos;
    there's no separate snapshot capture — thumbnails are extracted lazily
    from each clip's first frame and cached under data/thumbnails. Flags
    (which events to keep past the GC TTL) are tracked separately in
    data/flags.json so "what to keep" stays a tiny, easy-to-inspect file
    independent of the event log."""

    def __init__(self, max_events: int = MAX_EVENTS):
        self._events: deque[Event] = deque(maxlen=max_events)
        self._lock = Lock()
        self._flags: dict[str, bool] = self._load_flags()
        self._load_existing()

    def _load_existing(self):
        if not LOG_FILE.exists():
            return
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    self._events.appendleft(Event(**data))
                except (json.JSONDecodeError, TypeError):
                    continue

    def _load_flags(self) -> dict:
        if FLAGS_FILE.exists():
            try:
                return json.loads(FLAGS_FILE.read_text())
            except json.JSONDecodeError:
                return {}
        return {}

    def _save_flags(self):
        FLAGS_FILE.write_text(json.dumps(self._flags))

    def add(self, event_type: str, meta: Optional[dict] = None) -> Event:
        event = Event(id=uuid.uuid4().hex[:12], type=event_type, timestamp=time.time(), meta=meta or {})

        with self._lock:
            self._events.appendleft(event)

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict()) + "\n")

        return event

    def set_video(self, event_id: str, filename: str):
        with self._lock:
            for e in self._events:
                if e.id == event_id:
                    e.video = filename
                    break
        self._rewrite_log()

    def set_flag(self, event_id: str, flagged: bool):
        if flagged:
            self._flags[event_id] = True
        else:
            self._flags.pop(event_id, None)
        self._save_flags()

    def delete(self, event_id: str) -> bool:
        with self._lock:
            found = next((e for e in self._events if e.id == event_id), None)
            if found is None:
                return False
            self._events.remove(found)

        self.video_path(event_id).unlink(missing_ok=True)
        self.thumbnail_path(event_id).unlink(missing_ok=True)
        self._flags.pop(event_id, None)
        self._save_flags()
        self._rewrite_log()
        return True

    def list(self, limit: int = 50) -> list[dict]:
        with self._lock:
            events = list(self._events)[:limit]
        return [{**e.to_dict(), "flagged": e.id in self._flags} for e in events]

    def video_path(self, event_id: str) -> Path:
        return VIDEO_DIR / f"{_require_valid_event_id(event_id)}.mp4"

    def thumbnail_path(self, event_id: str) -> Path:
        return THUMBNAIL_DIR / f"{_require_valid_event_id(event_id)}.jpg"

    def get_thumbnail(self, event_id: str) -> Optional[bytes]:
        """Lazily extracts and caches the first frame of the event's video as
        a JPEG thumbnail. Returns None if there's no video yet (e.g. still
        recording) or no video at all."""
        cached = self.thumbnail_path(event_id)
        if cached.exists():
            return cached.read_bytes()

        video = self.video_path(event_id)
        if not video.exists():
            return None

        cap = cv2.VideoCapture(str(video))
        ok, frame = cap.read()
        cap.release()
        if not ok:
            return None

        ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            return None

        jpeg_bytes = jpeg.tobytes()
        cached.write_bytes(jpeg_bytes)
        return jpeg_bytes

    def _rewrite_log(self):
        with self._lock:
            events = list(self._events)
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            for e in reversed(events):
                f.write(json.dumps(e.to_dict()) + "\n")

    def run_gc(self, ttl_seconds: int = 24 * 60 * 60):
        """Deletes events (and their video/thumbnail files) older than
        ttl_seconds, unless flagged. Safe to call repeatedly; runs on a timer
        from main.py."""
        cutoff = time.time() - ttl_seconds
        with self._lock:
            kept, removed = [], []
            for e in self._events:
                if e.timestamp < cutoff and e.id not in self._flags:
                    removed.append(e)
                else:
                    kept.append(e)
            self._events = deque(kept, maxlen=self._events.maxlen)

        for e in removed:
            self.video_path(e.id).unlink(missing_ok=True)
            self.thumbnail_path(e.id).unlink(missing_ok=True)

        if removed:
            self._rewrite_log()
