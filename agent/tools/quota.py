"""A local-dev daily call counter (Module 7).

This is a convenience that warns before a script upload burns the
day's Gemini free-tier quota during local development -- it is NOT a
real guard in production. Cloud Run's filesystem is ephemeral and
resets every cold start, so this file will not reliably persist a
count there. The real defence against quota exhaustion is the 429
handler around the Gemini call itself (agent/tools/breakdown.py),
which must stay clean and never crash its caller regardless of what
this counter says.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path


def check_and_increment(path: Path, limit: int, today: date) -> bool:
    """True (and records the call) if under `limit` calls for `today` so far."""
    state = {"date": today.isoformat(), "count": 0}
    if path.exists():
        try:
            loaded = json.loads(path.read_text())
            if loaded.get("date") == today.isoformat():
                state = loaded
        except (json.JSONDecodeError, OSError):
            pass

    if state["count"] >= limit:
        return False

    state["count"] += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))
    return True
