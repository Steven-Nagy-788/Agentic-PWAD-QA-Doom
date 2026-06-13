from __future__ import annotations

import asyncio
import json
import types
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import report_service as report_service_mod
from app.services.report_service import ReportService


def test_parse_well_formed_json() -> None:
    text = '{"report_purpose": "test", "nested": {"key": "val"}}'
    result = ReportService._parse_report_response(text)
    assert result == {"report_purpose": "test", "nested": {"key": "val"}}


def test_parse_json_in_code_block() -> None:
    text = '```json\n{"report_purpose": "from block", "count": 3}\n```'
    result = ReportService._parse_report_response(text)
    assert result == {"report_purpose": "from block", "count": 3}


def test_parse_json_in_code_block_without_json_label() -> None:
    text = '```\n{"report_purpose": "no lang tag"}\n```'
    result = ReportService._parse_report_response(text)
    assert result == {"report_purpose": "no lang tag"}


def test_parse_json_with_surrounding_text() -> None:
    text = 'Here is the report:\n{"report_purpose": "extracted"}\nDone.'
    result = ReportService._parse_report_response(text)
    assert result == {"report_purpose": "extracted"}


def test_parse_json_with_prefix_and_suffix() -> None:
    text = 'Some preamble\n{"purpose": "x"}\nAnd trailing text'
    result = ReportService._parse_report_response(text)
    assert result == {"purpose": "x"}


def test_parse_empty_string_returns_empty_dict() -> None:
    result = ReportService._parse_report_response("")
    assert result == {}


def test_parse_whitespace_only_returns_empty_dict() -> None:
    result = ReportService._parse_report_response("   \n  \t  ")
    assert result == {}


def test_parse_broken_json_returns_empty_dict() -> None:
    result = ReportService._parse_report_response("{not valid json!!!")
    assert result == {}


def test_parse_partial_json_returns_empty_dict() -> None:
    result = ReportService._parse_report_response('{"key": "value"')
    assert result == {}


def test_parse_list_json_returns_empty_dict() -> None:
    result = ReportService._parse_report_response('[1, 2, 3]')
    assert result == {}


def test_parse_nested_json_extracted_from_braces() -> None:
    text = 'text before {"a": 1} text after'
    result = ReportService._parse_report_response(text)
    assert result == {"a": 1}


def test_parse_multiple_braces_uses_first_and_last_returns_empty_on_invalid() -> None:
    text = '{"first": 1} noise {"second": 2}'
    result = ReportService._parse_report_response(text)
    assert result == {}


def test_parse_empty_code_block_returns_empty_dict() -> None:
    text = '```\n```'
    result = ReportService._parse_report_response(text)
    assert result == {}


def test_parse_whitespace_around_json() -> None:
    text = '  \n  {"key": "val"}  \n  '
    result = ReportService._parse_report_response(text)
    assert result == {"key": "val"}


def test_parse_large_valid_json() -> None:
    data = {f"key_{i}": i for i in range(100)}
    text = json.dumps(data)
    result = ReportService._parse_report_response(text)
    assert result == data


def _minimal_payload() -> dict:
    run = SimpleNamespace(
        id=uuid4(),
        map_name="MAP01",
        iwad_used="freedoom2",
        difficulty_level=3,
        llm_model="gemini-test",
        outcome="timeout",
        status="completed",
        duration_seconds=10,
        total_kills=0,
        final_hp=100,
        final_armor=0,
        secrets_found=0,
        total_items_collected=0,
        total_actions_taken=2,
        total_llm_calls=2,
        max_ticks=3000,
        wad_file_id=uuid4(),
        static_analysis_id=None,
        recording_mp4_path=None,
        recording_metadata={},
        progress_metrics={},
        agent_quality_flags={},
        error_message=None,
        failure_summary=None,
        failure_category=None,
        environment_metadata={},
        report_pdf_path=None,
        seed=None,
    )
    return {
        "run": run,
        "analysis": None,
        "defects": [],
        "events": [],
        "decisions": [],
        "notable_events": [],
        "first_ticks": [],
        "last_ticks": [],
        "metrics": {
            "event_count": 0,
            "decision_count": 0,
            "position_sample_count": 0,
            "position_cluster_count": 0,
            "movement_distance_units": 0,
            "raw_enemy_count": 0,
            "spawned_enemy_count": 0,
            "hidden_enemy_count": 0,
            "raw_item_count": 0,
            "spawned_item_count": 0,
            "hidden_item_count": 0,
            "selected_skill_summary": {},
            "recording_metadata": {},
            "progress_metrics": {},
            "agent_quality_flags": {},
            "fallback_action_count": 0,
            "validation_rejection_count": 0,
            "coverage_percent": None,
        },
    }


@pytest.mark.asyncio
async def test_call_gemini_returns_valid_json(monkeypatch) -> None:
    service = object.__new__(ReportService)
    service.settings = SimpleNamespace(
        gemini_api_key="test-key",
        llm_model="gemini-test",
    )
    payload = _minimal_payload()

    class FakeGemini:
        async def _call_gemini(self_inner, system_prompt, llm_input):
            return '{"report_purpose": "gemini narrative"}', {"prompt_tokens": 10, "completion_tokens": 5}

    monkeypatch.setattr("app.services.gemini_service.GeminiService", lambda: FakeGemini())

    fake_prompt_path = SimpleNamespace(read_text=lambda: "sys")
    report_service_mod.report_prompt_path = lambda: fake_prompt_path

    result = await service._call_gemini_or_fallback(payload)
    assert result["report_purpose"] == "gemini narrative"
    assert result["_report_model"] == "gemini-test"


@pytest.mark.asyncio
async def test_call_gemini_raises_exception_falls_back(monkeypatch) -> None:
    service = object.__new__(ReportService)
    service.settings = SimpleNamespace(
        gemini_api_key="test-key",
        llm_model="gemini-test",
    )
    payload = _minimal_payload()

    class FakeGemini:
        async def _call_gemini(self_inner, system_prompt, llm_input):
            raise RuntimeError("Gemini timeout")

    monkeypatch.setattr("app.services.gemini_service.GeminiService", lambda: FakeGemini())

    fake_prompt_path = SimpleNamespace(read_text=lambda: "sys")
    report_service_mod.report_prompt_path = lambda: fake_prompt_path

    result = await service._call_gemini_or_fallback(payload)
    assert "deterministic-fallback" in result["_report_model"]
    assert "report_purpose" in result


@pytest.mark.asyncio
async def test_call_no_api_key_uses_deterministic_fallback() -> None:
    service = object.__new__(ReportService)
    service.settings = SimpleNamespace(gemini_api_key="")
    payload = _minimal_payload()

    result = await service._call_gemini_or_fallback(payload)
    assert result["_report_model"] == "deterministic-grounded-template"
    assert "report_purpose" in result


@pytest.mark.asyncio
async def test_call_gemini_returns_non_dict_falls_back(monkeypatch) -> None:
    service = object.__new__(ReportService)
    service.settings = SimpleNamespace(
        gemini_api_key="test-key",
        llm_model="gemini-test",
    )
    payload = _minimal_payload()

    class FakeGemini:
        async def _call_gemini(self_inner, system_prompt, llm_input):
            return '[1, 2, 3]', {"prompt_tokens": 5, "completion_tokens": 2}

    monkeypatch.setattr("app.services.gemini_service.GeminiService", lambda: FakeGemini())

    fake_prompt_path = SimpleNamespace(read_text=lambda: "sys")
    report_service_mod.report_prompt_path = lambda: fake_prompt_path

    result = await service._call_gemini_or_fallback(payload)
    assert "report_purpose" in result
    assert result["_report_model"] == "gemini-test"
