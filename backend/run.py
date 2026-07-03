import sys
from pathlib import Path

# Launched via pythonw.exe (no console window, see start.bat) so there's
# nowhere for stdout/stderr to go by default -- redirect to a log file
# before anything else (uvicorn, the app) has a chance to bind its own
# logging to the original streams.
LOG_DIR = Path(__file__).resolve().parent / "data"
LOG_DIR.mkdir(parents=True, exist_ok=True)
_log_file = open(LOG_DIR / "server.log", "a", buffering=1, encoding="utf-8")
sys.stdout = _log_file
sys.stderr = _log_file

import os  # noqa: E402

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402

if __name__ == "__main__":
    print("=" * 60, flush=True)
    print("Webcam Tools starting...", flush=True)
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
    server = uvicorn.Server(config)
    # Stashed here so /api/system/shutdown can flip should_exit for a clean
    # ASGI lifespan shutdown -- not available when launched via the
    # `uvicorn app.main:app` CLI form, which owns its own Server instance.
    app.state.server = server
    server.run()
    print("Webcam Tools stopped.", flush=True)
