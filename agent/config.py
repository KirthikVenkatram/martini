"""Loads and validates MARTINI agent configuration from the environment.

Validated at import time, not at first use -- a missing variable is
caught before the agent tries to reach Gemini or Grafana and fails with
a confusing downstream error instead.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

_REQUIRED_VARS = [
    "GOOGLE_API_KEY",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GRAFANA_URL",
    "GRAFANA_SERVICE_ACCOUNT_TOKEN",
]

_missing = [name for name in _REQUIRED_VARS if not os.environ.get(name)]
if _missing:
    raise RuntimeError(
        "Missing required environment variable(s): "
        f"{', '.join(_missing)}. Set them in .env or the environment "
        "before running the MARTINI agent."
    )

GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]
GOOGLE_GENAI_USE_VERTEXAI = os.environ["GOOGLE_GENAI_USE_VERTEXAI"]
GRAFANA_URL = os.environ["GRAFANA_URL"]
GRAFANA_SERVICE_ACCOUNT_TOKEN = os.environ["GRAFANA_SERVICE_ACCOUNT_TOKEN"]

# Has a sensible default, so unlike the vars above it never fails loudly
# when unset -- only the Gemini model name changes, nothing critical.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
