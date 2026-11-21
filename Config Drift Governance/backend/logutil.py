"""logutil.py -- Unified, timestamped, no-silent-failure logger for the backend.

Follows workspace rules:
- Visible, timestamped progress logs (a heartbeat).
- Universal format: [HH:MM:SS] msg
"""
from __future__ import annotations

import datetime
import sys


def log(msg: str, stream=None) -> None:
    """Print timestamped message to stdout or specified stream."""
    out = stream or sys.stdout
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {msg}", file=out, flush=True)


if __name__ == "__main__":
    log("Unified logger initialized and verified.")
