from __future__ import annotations

import pytest

from app.services.report_service import ReportService


def test_merge_gemini_text_fields_override_defaults() -> None:
    defaults = {
        "report_purpose": "Default purpose",
        "problem_and_escalation": "Default escalation",
        "test_items_summary": "Default items",
    }
    generated = {
        "report_purpose": "Gemini generated purpose",
        "problem_and_escalation": "Gemini escalation",
    }
    merged = ReportService._merge_report_defaults(defaults, generated)

    assert merged["report_purpose"] == "Gemini generated purpose"
    assert merged["problem_and_escalation"] == "Gemini escalation"
    assert merged["test_items_summary"] == "Default items"


def test_merge_gemini_none_values_do_not_override() -> None:
    defaults = {
        "report_purpose": "Default purpose",
        "test_items_summary": "Default items",
    }
    generated = {
        "report_purpose": None,
        "test_items_summary": "",
    }
    merged = ReportService._merge_report_defaults(defaults, generated)

    assert merged["report_purpose"] == "Default purpose"
    assert merged["test_items_summary"] == "Default items"


def test_merge_metrics_not_overwritten_by_gemini() -> None:
    defaults = {
        "metrics": {"event_count": 10, "position_sample_count": 5},
    }
    generated = {
        "metrics": {"event_count": 999},
    }
    merged = ReportService._merge_report_defaults(defaults, generated)

    assert merged["metrics"]["event_count"] == 10
    assert merged["metrics"]["position_sample_count"] == 5


def test_merge_underscore_keys_ignored() -> None:
    defaults = {
        "report_purpose": "Default",
    }
    generated = {
        "_report_model": "gemini-2.5-flash",
        "_report_token_usage": {"prompt_tokens": 100},
        "report_purpose": "Override",
    }
    merged = ReportService._merge_report_defaults(defaults, generated)

    assert "_report_model" not in merged
    assert "_report_token_usage" not in merged
    assert merged["report_purpose"] == "Override"


def test_merge_pass_fail_summary_gemini_overrides_rationale() -> None:
    defaults = {
        "pass_fail_summary": {"overall_verdict": "PASS", "navigation_rationale": "det rationale"},
    }
    generated = {
        "pass_fail_summary": {"overall_verdict": "FAIL", "navigation_rationale": "LLM rationale"},
    }
    merged = ReportService._merge_report_defaults(defaults, generated)

    assert merged["pass_fail_summary"]["overall_verdict"] == "PASS"
    assert merged["pass_fail_summary"]["navigation_rationale"] == "LLM rationale"


def test_merge_pass_fail_summary_gemini_empty_keeps_default() -> None:
    defaults = {
        "pass_fail_summary": {"overall_verdict": "PASS"},
    }
    generated = {
        "pass_fail_summary": {},
    }
    merged = ReportService._merge_report_defaults(defaults, generated)

    assert merged["pass_fail_summary"] == {"overall_verdict": "PASS"}


def test_merge_risk_areas_gemini_list_overrides() -> None:
    defaults = {
        "risk_areas": [{"area": "Default", "risk": "low"}],
    }
    generated = {
        "risk_areas": [{"area": "Gemini", "risk": "high"}],
    }
    merged = ReportService._merge_report_defaults(defaults, generated)

    assert merged["risk_areas"] == [{"area": "Gemini", "risk": "high"}]


def test_merge_risk_areas_gemini_empty_keeps_default() -> None:
    defaults = {
        "risk_areas": [{"area": "Default", "risk": "low"}],
    }
    generated = {
        "risk_areas": [],
    }
    merged = ReportService._merge_report_defaults(defaults, generated)

    assert merged["risk_areas"] == [{"area": "Default", "risk": "low"}]


def test_merge_objectives_planned_gemini_overrides() -> None:
    defaults = {
        "objectives_planned": [{"objective": "Default 1", "status": "planned"}],
    }
    generated = {
        "objectives_planned": [
            {"objective": "Gemini 1", "status": "planned"},
            {"objective": "Gemini 2", "status": "planned"},
        ],
    }
    merged = ReportService._merge_report_defaults(defaults, generated)

    assert len(merged["objectives_planned"]) == 2
    assert merged["objectives_planned"][0]["objective"] == "Gemini 1"


def test_merge_good_quality_areas_gemini_overrides() -> None:
    defaults = {
        "good_quality_areas": [{"area": "Runtime", "evidence": "completed"}],
    }
    generated = {
        "good_quality_areas": [{"area": "Telemetry", "evidence": "rich data"}],
    }
    merged = ReportService._merge_report_defaults(defaults, generated)

    assert merged["good_quality_areas"] == [{"area": "Telemetry", "evidence": "rich data"}]


def test_merge_whitespace_only_strings_do_not_override() -> None:
    defaults = {
        "defect_summary_narrative": "Default narrative",
    }
    generated = {
        "defect_summary_narrative": "   ",
    }
    merged = ReportService._merge_report_defaults(defaults, generated)

    assert merged["defect_summary_narrative"] == "Default narrative"


def test_merge_empty_generated_returns_all_defaults() -> None:
    defaults = {
        "report_purpose": "Default",
        "test_items_summary": "Items",
        "pass_fail_summary": {"overall_verdict": "PASS"},
    }
    merged = ReportService._merge_report_defaults(defaults, {})

    assert merged == defaults


def test_merge_mixed_override_and_keep() -> None:
    defaults = {
        "report_purpose": "Default purpose",
        "problem_and_escalation": "Default escalation",
        "pass_fail_summary": {"overall_verdict": "PASS"},
        "metrics": {"event_count": 5},
    }
    generated = {
        "report_purpose": "Gemini purpose",
        "pass_fail_summary": {"overall_verdict": "FAIL", "navigation_rationale": "LLM nav"},
    }
    merged = ReportService._merge_report_defaults(defaults, generated)

    assert merged["report_purpose"] == "Gemini purpose"
    assert merged["problem_and_escalation"] == "Default escalation"
    assert merged["pass_fail_summary"]["overall_verdict"] == "PASS"
    assert merged["pass_fail_summary"]["navigation_rationale"] == "LLM nav"
    assert merged["metrics"] == {"event_count": 5}


def test_merge_objectives_covered_gemini_overrides() -> None:
    defaults = {
        "objectives_covered": [{"objective": "Default covered"}],
    }
    generated = {
        "objectives_covered": [{"objective": "Gemini covered"}],
    }
    merged = ReportService._merge_report_defaults(defaults, generated)

    assert merged["objectives_covered"] == [{"objective": "Gemini covered"}]


def test_merge_objectives_omitted_gemini_overrides() -> None:
    defaults = {
        "objectives_omitted": [{"objective": "Default omitted", "reason": "no data"}],
    }
    generated = {
        "objectives_omitted": [{"objective": "Gemini omitted", "reason": "timeout"}],
    }
    merged = ReportService._merge_report_defaults(defaults, generated)

    assert merged["objectives_omitted"] == [{"objective": "Gemini omitted", "reason": "timeout"}]
