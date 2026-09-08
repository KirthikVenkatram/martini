"""Covers agent/config.py's two auth paths (Developer API vs. Vertex AI).

config.py validates at import time, so these tests reload the module
under a controlled environment rather than importing it once.
"""

from __future__ import annotations

import importlib
import os
from contextlib import contextmanager

import pytest

import agent.config as config

_ALL_PATH_VARS = ("GOOGLE_API_KEY", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION")


@contextmanager
def _env(**overrides: str | None):
    """Sets env vars for the block, restoring the prior environment after.

    A value of None simulates "unset" as an empty string rather than
    deleting the key -- config.py calls load_dotenv(), which never
    overrides a key already present in os.environ, but does fill in a
    deleted one from the repo's real .env, defeating the simulation.
    """
    saved = {key: os.environ.get(key) for key in overrides}
    try:
        for key, value in overrides.items():
            os.environ[key] = value if value is not None else ""
        yield
    finally:
        for key, prior in saved.items():
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior
        importlib.reload(config)


def test_vertex_path_missing_project_raises_named_error():
    with _env(
        GOOGLE_GENAI_USE_VERTEXAI="TRUE",
        GOOGLE_CLOUD_PROJECT=None,
        GOOGLE_CLOUD_LOCATION="us-central1",
        GOOGLE_API_KEY=None,
    ):
        with pytest.raises(RuntimeError, match="GOOGLE_CLOUD_PROJECT"):
            importlib.reload(config)


def test_vertex_path_missing_location_raises_named_error():
    with _env(
        GOOGLE_GENAI_USE_VERTEXAI="TRUE",
        GOOGLE_CLOUD_PROJECT="martini-proj-508014-f8",
        GOOGLE_CLOUD_LOCATION=None,
        GOOGLE_API_KEY=None,
    ):
        with pytest.raises(RuntimeError, match="GOOGLE_CLOUD_LOCATION"):
            importlib.reload(config)


def test_vertex_path_does_not_require_api_key():
    with _env(
        GOOGLE_GENAI_USE_VERTEXAI="TRUE",
        GOOGLE_CLOUD_PROJECT="martini-proj-508014-f8",
        GOOGLE_CLOUD_LOCATION="us-central1",
        GOOGLE_API_KEY=None,
    ):
        importlib.reload(config)
        assert config.USE_VERTEXAI is True
        assert config.GOOGLE_CLOUD_PROJECT == "martini-proj-508014-f8"
        assert config.GOOGLE_CLOUD_LOCATION == "us-central1"


def test_developer_api_path_missing_api_key_raises_named_error():
    with _env(
        GOOGLE_GENAI_USE_VERTEXAI="FALSE",
        GOOGLE_API_KEY=None,
        GOOGLE_CLOUD_PROJECT=None,
        GOOGLE_CLOUD_LOCATION=None,
    ):
        with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
            importlib.reload(config)


def test_developer_api_path_does_not_require_cloud_vars():
    with _env(
        GOOGLE_GENAI_USE_VERTEXAI="FALSE",
        GOOGLE_API_KEY="test-fake-key",
        GOOGLE_CLOUD_PROJECT=None,
        GOOGLE_CLOUD_LOCATION=None,
    ):
        importlib.reload(config)
        assert config.USE_VERTEXAI is False
        assert config.GOOGLE_API_KEY == "test-fake-key"
