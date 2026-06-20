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

    # LLM fields are primary — generated values pass through
    assert merged["report_purpose"] == "Gemini generated purpose"
    assert merged["problem_and_escalation"] == "Gemini escalation"
    # Missing generated key is not in merged (LLM-primary)
    assert "test_items_summary" not in merged


def test_merge_measured_fields_llm_primary() -> None:
    defaults = {
        "test_environment_summary": "Measured summary",
        "hardware_spec": {"cpu": "measured"},
        "software_spec": {"vizdoom": "1.3.0"},
        "elapsed_time_seconds": 100,
    }
    generated = {
        "report_purpose": "LLM purpose",
        "test_environment_summary": "LLM environment summary",
        "hardware_spec": {"cpu": "LLM reported"},
        "elapsed_time_seconds": 200,
    }
    merged = ReportService._merge_report_defaults(defaults, generated)

    # LLM fields pass through — deterministic does NOT override
    assert merged["report_purpose"] == "LLM purpose"
    assert merged["test_environment_summary"] == "LLM environment summary"
    assert merged["hardware_spec"] == {"cpu": "LLM reported"}
    assert merged["elapsed_time_seconds"] == 200


def test_merge_pass_fail_summary_gemini_overrides_rationale() -> None:
    defaults = {
        "pass_fail_summary": {"overall_verdict": "PASS", "navigation_rationale": "det rationale"},
    }
    generated = {
        "pass_fail_summary": {"overall_verdict": "FAIL", "navigation_rationale": "LLM rationale"},
    }
    merged = ReportService._merge_report_defaults(defaults, generated)

    # LLM pass_fail_summary is primary
    assert merged["pass_fail_summary"]["overall_verdict"] == "FAIL"
    assert merged["pass_fail_summary"]["navigation_rationale"] == "LLM rationale"


def test_merge_pass_fail_summary_gemini_empty_keeps_default() -> None:
    defaults = {
        "pass_fail_summary": {"overall_verdict": "PASS", "navigation_rationale": "default nav"},
    }
    generated = {
        "pass_fail_summary": {},
    }
    merged = ReportService._merge_report_defaults(defaults, generated)

    # Empty LLM pass_fail falls back to deterministic
    assert merged["pass_fail_summary"]["overall_verdict"] == "PASS"
    assert merged["pass_fail_summary"]["navigation_rationale"] == "default nav"


def test_merge_pass_fail_missing_rationale_stays_empty() -> None:
    defaults = {
        "pass_fail_summary": {"overall_verdict": "PASS", "navigation_rationale": "default nav"},
    }
    generated = {
        "pass_fail_summary": {"overall_verdict": "FAIL", "combat_rationale": "LLM combat"},
    }
    merged = ReportService._merge_report_defaults(defaults, generated)

    # LLM verdict is primary
    assert merged["pass_fail_summary"]["overall_verdict"] == "FAIL"
    # LLM rationale passes through
    assert merged["pass_fail_summary"]["combat_rationale"] == "LLM combat"
    # Missing rationale stays empty — deterministic does NOT fill it
    assert "navigation_rationale" not in merged["pass_fail_summary"]


def test_merge_risk_areas_gemini_list_overrides() -> None:
    defaults = {
        "risk_areas": [{"area": "Default", "risk": "low"}],
    }
    generated = {
        "risk_areas": [{"area": "Gemini", "risk": "high"}],
    }
    merged = ReportService._merge_report_defaults(defaults, generated)

    # LLM fields pass through
    assert merged["risk_areas"] == [{"area": "Gemini", "risk": "high"}]


def test_merge_risk_areas_gemini_empty_stays_empty() -> None:
    defaults = {
        "risk_areas": [{"area": "Default", "risk": "low"}],
    }
    generated = {
        "risk_areas": [],
    }
    merged = ReportService._merge_report_defaults(defaults, generated)

    # LLM-primary: empty generated stays empty
    assert merged["risk_areas"] == []


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


def test_merge_empty_generated_stays_empty() -> None:
    defaults = {
        "test_environment_summary": "Measured",
        "hardware_spec": {"cpu": "x"},
        "elapsed_time_seconds": 100,
    }
    merged = ReportService._merge_report_defaults(defaults, {})

    # LLM-primary: empty generated stays empty, deterministic does NOT fill fields
    assert "test_environment_summary" not in merged
    assert "hardware_spec" not in merged
    assert "elapsed_time_seconds" not in merged


def test_merge_mixed_override_and_keep() -> None:
    defaults = {
        "report_purpose": "Default purpose",
        "test_environment_summary": "Measured env",
        "hardware_spec": {"cpu": "x"},
        "pass_fail_summary": {"overall_verdict": "PASS"},
    }
    generated = {
        "report_purpose": "Gemini purpose",
        "pass_fail_summary": {"overall_verdict": "FAIL", "navigation_rationale": "LLM nav"},
    }
    merged = ReportService._merge_report_defaults(defaults, generated)

    # LLM fields pass through
    assert merged["report_purpose"] == "Gemini purpose"
    assert merged["pass_fail_summary"]["overall_verdict"] == "FAIL"
    assert merged["pass_fail_summary"]["navigation_rationale"] == "LLM nav"
    # Measured fields are NOT filled from defaults (LLM-primary)
    assert "test_environment_summary" not in merged
    assert "hardware_spec" not in merged


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


def test_merge_non_empty_pass_fail_not_replaced() -> None:
    """Non-empty LLM pass_fail_summary is kept even if missing some keys."""
    defaults = {
        "pass_fail_summary": {
            "overall_verdict": "PASS",
            "navigation_rationale": "default nav",
            "combat_rationale": "default combat",
        },
    }
    generated = {
        "pass_fail_summary": {
            "overall_verdict": "FAIL",
            "navigation_rationale": "LLM nav",
        },
    }
    merged = ReportService._merge_report_defaults(defaults, generated)

    assert merged["pass_fail_summary"]["overall_verdict"] == "FAIL"
    assert merged["pass_fail_summary"]["navigation_rationale"] == "LLM nav"
    # combat_rationale is NOT filled from deterministic
    assert "combat_rationale" not in merged["pass_fail_summary"]
