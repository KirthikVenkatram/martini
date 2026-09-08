"""Loads and validates MARTINI agent configuration from the environment.

Validated at import time, not at first use -- a missing variable is
caught before the agent tries to reach Gemini or Grafana and fails with
a confusing downstream error instead.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

if not os.environ.get("GOOGLE_GENAI_USE_VERTEXAI"):
    raise RuntimeError(
        "Missing required environment variable: GOOGLE_GENAI_USE_VERTEXAI. "
        "Set it in .env or the environment before running the MARTINI agent."
    )

GOOGLE_GENAI_USE_VERTEXAI = os.environ["GOOGLE_GENAI_USE_VERTEXAI"]
USE_VERTEXAI = GOOGLE_GENAI_USE_VERTEXAI.strip().upper() == "TRUE"

# Vertex AI authenticates via Application Default Credentials (a service
# account in deployment) and needs a project + region to bill against.
# The Developer API authenticates via a bare API key. Selecting one path
# must never require the other path's variables.
_PATH_REQUIRED_VARS = ["GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"] if USE_VERTEXAI else ["GOOGLE_API_KEY"]
_COMMON_REQUIRED_VARS = ["GRAFANA_URL", "GRAFANA_SERVICE_ACCOUNT_TOKEN"]

_missing = [name for name in _PATH_REQUIRED_VARS + _COMMON_REQUIRED_VARS if not os.environ.get(name)]
if _missing:
    _path_label = "Vertex AI" if USE_VERTEXAI else "Developer API"
    raise RuntimeError(
        f"Missing required environment variable(s) for the {_path_label} auth path: "
        f"{', '.join(_missing)}. Set them in .env or the environment "
        "before running the MARTINI agent."
    )

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
GOOGLE_CLOUD_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "")
GRAFANA_URL = os.environ["GRAFANA_URL"]
GRAFANA_SERVICE_ACCOUNT_TOKEN = os.environ["GRAFANA_SERVICE_ACCOUNT_TOKEN"]

# Has a sensible default, so unlike the vars above it never fails loudly
# when unset -- only the Gemini model name changes, nothing critical.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
