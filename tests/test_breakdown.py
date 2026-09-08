from __future__ import annotations

from datetime import date

import pytest
from google.genai.errors import ClientError

from agent.tools import breakdown


def _quota_error() -> ClientError:
    return ClientError(429, {"error": {"message": "quota exceeded", "status": "RESOURCE_EXHAUSTED"}}, None)


def test_slugify_character_name_normalizes():
    assert breakdown.slugify_character_name("PRIYA") == "priya"
    assert breakdown.slugify_character_name("  Desmond Ruiz ") == "desmond-ruiz"
    assert breakdown.slugify_character_name("***") == "cast"


def test_parses_a_well_formed_json_array():
    raw = """
    [
      {
        "number": "1",
        "synopsis": "MARCUS and ELENA argue in the kitchen.",
        "int_ext": "int",
        "day_night": "day",
        "location": "Kitchen",
        "page_eighths": "2 3/8",
        "cast_names": ["MARCUS", "ELENA"],
        "estimated_setups": 3
      }
    ]
    """

    scenes = breakdown._parse_breakdown_payload(raw)

    assert len(scenes) == 1
    scene = scenes[0]
    assert scene.number == "1"
    assert scene.int_ext == "INT"
    assert scene.day_night == "DAY"
    assert str(scene.page_eighths) == "2 3/8"
    assert scene.cast_ids == ["marcus", "elena"]
    assert scene.estimated_setups == 3


def test_strips_markdown_code_fences():
    raw = '```json\n[{"number": "1", "synopsis": "A.", "int_ext": "INT", "day_night": "DAY", "location": "Set", "page_eighths": "1", "cast_names": [], "estimated_setups": 1}]\n```'

    scenes = breakdown._parse_breakdown_payload(raw)

    assert len(scenes) == 1


def test_raises_a_named_error_on_invalid_json():
    with pytest.raises(breakdown.BreakdownParseError, match="not valid JSON"):
        breakdown._parse_breakdown_payload("not json at all")


def test_raises_a_named_error_naming_the_bad_scene():
    raw = '[{"number": "1", "synopsis": "A.", "int_ext": "SIDEWAYS", "day_night": "DAY", "location": "Set", "page_eighths": "1", "cast_names": [], "estimated_setups": 1}]'

    with pytest.raises(breakdown.BreakdownParseError, match="scene at index 0"):
        breakdown._parse_breakdown_payload(raw)


def test_breakdown_script_raises_quota_exceeded_when_the_counter_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(breakdown, "_QUOTA_PATH", tmp_path / "quota.json")
    monkeypatch.setattr(breakdown, "_QUOTA_DAILY_LIMIT", 0)

    with pytest.raises(breakdown.BreakdownQuotaExceeded, match="quota"):
        breakdown.breakdown_script(b"%PDF-fake")


def test_breakdown_script_raises_quota_exceeded_on_a_live_429(tmp_path, monkeypatch):
    monkeypatch.setattr(breakdown, "_QUOTA_PATH", tmp_path / "quota.json")

    class _FakeModels:
        def generate_content(self, **kwargs):
            raise _quota_error()

    class _FakeClient:
        def __init__(self, **kwargs):
            self.models = _FakeModels()

    monkeypatch.setattr(breakdown.genai, "Client", _FakeClient)

    with pytest.raises(breakdown.BreakdownQuotaExceeded, match="quota"):
        breakdown.breakdown_script(b"%PDF-fake")


def test_breakdown_script_reraises_non_quota_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(breakdown, "_QUOTA_PATH", tmp_path / "quota.json")

    class _FakeModels:
        def generate_content(self, **kwargs):
            raise ClientError(500, {"error": {"message": "server error"}}, None)

    class _FakeClient:
        def __init__(self, **kwargs):
            self.models = _FakeModels()

    monkeypatch.setattr(breakdown.genai, "Client", _FakeClient)

    with pytest.raises(ClientError):
        breakdown.breakdown_script(b"%PDF-fake")


def test_breakdown_script_parses_a_successful_response(tmp_path, monkeypatch):
    monkeypatch.setattr(breakdown, "_QUOTA_PATH", tmp_path / "quota.json")

    raw = '[{"number": "1", "synopsis": "A.", "int_ext": "INT", "day_night": "DAY", "location": "Set", "page_eighths": "1", "cast_names": [], "estimated_setups": 1}]'

    class _FakeResponse:
        text = raw

    class _FakeModels:
        def generate_content(self, **kwargs):
            return _FakeResponse()

    class _FakeClient:
        def __init__(self, **kwargs):
            self.models = _FakeModels()

    monkeypatch.setattr(breakdown.genai, "Client", _FakeClient)

    scenes = breakdown.breakdown_script(b"%PDF-fake")

    assert len(scenes) == 1
    assert scenes[0].number == "1"
