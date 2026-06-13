from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.report_service import ReportService


def test_parse_well_formed_json() -> None:
    text = '{"report_purpose": "test", "nested": {"key": "val"}}'
    result = ReportService._parse_report_json(text)
    assert result == {"report_purpose": "test", "nested": {"key": "val"}}


def test_parse_json_in_code_block() -> None:
    text = '```json\n{"report_purpose": "from block", "count": 3}\n```'
    result = ReportService._parse_report_json(text)
    assert result == {"report_purpose": "from block", "count": 3}


def test_parse_json_in_code_block_without_json_label() -> None:
    text = '```\n{"report_purpose": "no lang tag"}\n```'
    result = ReportService._parse_report_json(text)
    assert result == {"report_purpose": "no lang tag"}


def test_parse_json_with_surrounding_text() -> None:
    text = 'Here is the report:\n{"report_purpose": "extracted"}\nDone.'
    result = ReportService._parse_report_json(text)
    assert result == {"report_purpose": "extracted"}


def test_parse_json_with_prefix_and_suffix() -> None:
    text = 'Some preamble\n{"purpose": "x"}\nAnd trailing text'
    result = ReportService._parse_report_json(text)
    assert result == {"purpose": "x"}


def test_parse_whitespace_around_json() -> None:
    text = '  \n  {"key": "val"}  \n  '
    result = ReportService._parse_report_json(text)
    assert result == {"key": "val"}


def test_parse_large_valid_json() -> None:
    data = {f"key_{i}": i for i in range(100)}
    text = json.dumps(data)
    result = ReportService._parse_report_json(text)
    assert result == data


def test_parse_json_extracted_from_braces() -> None:
    text = 'text before {"a": 1} text after'
    result = ReportService._parse_report_json(text)
    assert result == {"a": 1}


def test_parse_json_raises_on_empty_string() -> None:
    with pytest.raises((json.JSONDecodeError, ValueError)):
        ReportService._parse_report_json("")


def test_parse_json_raises_on_whitespace_only() -> None:
    with pytest.raises((json.JSONDecodeError, ValueError)):
        ReportService._parse_report_json("   \n  \t  ")


def test_parse_json_raises_on_broken_json() -> None:
    with pytest.raises((json.JSONDecodeError, ValueError)):
        ReportService._parse_report_json("{not valid json!!!")


def test_parse_json_raises_on_partial_json() -> None:
    with pytest.raises((json.JSONDecodeError, ValueError)):
        ReportService._parse_report_json('{"key": "value"')


def test_parse_json_raises_on_list() -> None:
    with pytest.raises((json.JSONDecodeError, ValueError)):
        ReportService._parse_report_json('[1, 2, 3]')


def test_parse_json_raises_on_multiple_braces() -> None:
    with pytest.raises((json.JSONDecodeError, ValueError)):
        ReportService._parse_report_json('{"first": 1} noise {"second": 2}')


def test_parse_json_raises_on_empty_code_block() -> None:
    with pytest.raises((json.JSONDecodeError, ValueError)):
        ReportService._parse_report_json('```\n```')


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


class _FakeGeminiResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.usage_metadata = SimpleNamespace(
            prompt_token_count=10,
            candidates_token_count=5,
        )


@pytest.mark.asyncio
async def test_call_gemini_returns_valid_json(monkeypatch) -> None:
    service = object.__new__(ReportService)
    service.settings = SimpleNamespace(
        gemini_api_key="test-key",
        llm_model="gemini-test",
        gemini_rate_limit_calls_per_minute=15,
        gemini_max_concurrency=1,
        report_gemini_timeout_seconds=60,
    )
    payload = _minimal_payload()

    async def fake_generate_content(**kwargs):
        return _FakeGeminiResponse('{"report_purpose": "gemini narrative"}')

    monkeypatch.setattr(
        "app.services.gemini_service._get_gemini_sem",
        lambda: asyncio.Lock(),
    )
    monkeypatch.setattr(
        "app.services.gemini_service._throttle_local_rate",
        lambda _: asyncio.sleep(0),
    )
    monkeypatch.setattr(
        "app.services.gemini_service._record_api_call",
        lambda: None,
    )

    import google.genai as _genai_mod
    monkeypatch.setattr(
        "google.genai.Client",
        lambda api_key: SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=fake_generate_content))),
    )

    result = await service._call_gemini_or_fallback(payload)
    assert result["report_purpose"] == "gemini narrative"
    assert result["_report_model"] == "gemini-test"


@pytest.mark.asyncio
async def test_call_gemini_raises_exception_falls_back(monkeypatch) -> None:
    service = object.__new__(ReportService)
    service.settings = SimpleNamespace(
        gemini_api_key="test-key",
        llm_model="gemini-test",
        gemini_rate_limit_calls_per_minute=15,
        gemini_max_concurrency=1,
        report_gemini_timeout_seconds=60,
    )
    payload = _minimal_payload()

    async def fake_generate_content(**kwargs):
        raise RuntimeError("Gemini timeout")

    monkeypatch.setattr(
        "app.services.gemini_service._get_gemini_sem",
        lambda: asyncio.Lock(),
    )
    monkeypatch.setattr(
        "app.services.gemini_service._throttle_local_rate",
        lambda _: asyncio.sleep(0),
    )
    monkeypatch.setattr(
        "app.services.gemini_service._record_api_call",
        lambda: None,
    )

    import google.genai as _genai_mod
    monkeypatch.setattr(
        "google.genai.Client",
        lambda api_key: SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=fake_generate_content))),
    )

    result = await service._call_gemini_or_fallback(payload)
    assert result["_report_model"] == "deterministic-grounded-template"
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
        gemini_rate_limit_calls_per_minute=15,
        gemini_max_concurrency=1,
        report_gemini_timeout_seconds=60,
    )
    payload = _minimal_payload()

    async def fake_generate_content(**kwargs):
        return _FakeGeminiResponse('[1, 2, 3]')

    monkeypatch.setattr(
        "app.services.gemini_service._get_gemini_sem",
        lambda: asyncio.Lock(),
    )
    monkeypatch.setattr(
        "app.services.gemini_service._throttle_local_rate",
        lambda _: asyncio.sleep(0),
    )
    monkeypatch.setattr(
        "app.services.gemini_service._record_api_call",
        lambda: None,
    )

    import google.genai as _genai_mod
    monkeypatch.setattr(
        "google.genai.Client",
        lambda api_key: SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=fake_generate_content))),
    )

    result = await service._call_gemini_or_fallback(payload)
    assert "report_purpose" in result
    assert result["_report_model"] == "deterministic-grounded-template"


def test_merge_preserves_deterministic_fields() -> None:
    defaults = {
        "report_purpose": "deterministic purpose",
        "executive_summary": "deterministic summary",
        "pass_fail_summary": {
            "overall_verdict": "PASS",
            "navigation_rationale": "det nav rationale",
        },
        "elapsed_time_seconds": 100,
    }
    generated = {
        "report_purpose": "rich LLM narrative about the run",
        "executive_summary": "detailed executive summary from LLM",
        "pass_fail_summary": {
            "overall_verdict": "FAIL",
            "navigation_rationale": "LLM nav rationale",
        },
        "elapsed_time_seconds": 999,
    }
    result = ReportService._merge_report_defaults(defaults, generated)
    assert result["report_purpose"] == "rich LLM narrative about the run"
    assert result["executive_summary"] == "detailed executive summary from LLM"
    assert result["pass_fail_summary"]["overall_verdict"] == "PASS"
    assert result["pass_fail_summary"]["navigation_rationale"] == "LLM nav rationale"
    assert result["elapsed_time_seconds"] == 100


def test_merge_ignores_empty_llm_fields() -> None:
    defaults = {"report_purpose": "deterministic purpose"}
    generated = {"report_purpose": "   "}
    result = ReportService._merge_report_defaults(defaults, generated)
    assert result["report_purpose"] == "deterministic purpose"


def test_merge_ignores_non_string_llm_fields() -> None:
    defaults = {"report_purpose": "deterministic purpose"}
    generated = {"report_purpose": 123}
    result = ReportService._merge_report_defaults(defaults, generated)
    assert result["report_purpose"] == "deterministic purpose"


def test_merge_includes_llm_risk_areas() -> None:
    defaults = {"risk_areas": [{"area": "old", "risk": "old risk"}]}
    generated = {"risk_areas": [{"area": "new", "risk": "new risk"}]}
    result = ReportService._merge_report_defaults(defaults, generated)
    assert result["risk_areas"] == [{"area": "new", "risk": "new risk"}]


def test_merge_keeps_deterministic_risk_when_llm_empty() -> None:
    defaults = {"risk_areas": [{"area": "old", "risk": "old risk"}]}
    generated = {"risk_areas": []}
    result = ReportService._merge_report_defaults(defaults, generated)
    assert result["risk_areas"] == [{"area": "old", "risk": "old risk"}]
