import json
import threading
import urllib.error
import urllib.request
from typing import Optional

import numpy as np

from .base import Action
from ..config import load_config, save_config

TIMEOUT_SECONDS = 5


class WebhookAction(Action):
    """POSTs a small JSON payload to an arbitrary URL for any event --
    lowest-lift, highest-flexibility way to do *something* downstream
    (IFTTT, a phone notification, a smart-home hook, whatever) without this
    app needing to know or care what that something is. See DREAMS.md for
    the original writeup this followed.

    Fire-and-forget: runs on its own thread so a slow/unreachable endpoint
    can't stall the pipeline, logs failures, never retries. Off by default
    until a URL is actually configured.
    """

    name = "webhook"
    enabled = False

    def __init__(self):
        self.url = load_config().get("webhook_url") or None

    def set_url(self, url: Optional[str]):
        self.url = url or None
        save_config(webhook_url=self.url)

    def trigger(self, event, frame: np.ndarray) -> None:
        if not self.url:
            return
        payload = {
            "event": event.type,  # e.g. "motion", "person", "manual" -- the name downstream automations match on
            "id": event.id,
            "type": event.type,
            "timestamp": event.timestamp,
            "meta": event.meta,
        }
        threading.Thread(target=self._post, args=(self.url, payload), daemon=True).start()

    def _post(self, url: str, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS).close()
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"Webhook POST to {url} failed: {e}", flush=True)
