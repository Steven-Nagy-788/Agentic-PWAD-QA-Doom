from __future__ import annotations

import pytest

from app.services.gemini_service import (
    GeminiService,
    estimate_llm_cost_usd,
    _is_rate_limit,
    _retry_delay_seconds,
    _normalize_hypotheses,
)


# ── _extract_json_balanced ───────────────────────────────────────────────────


def test_extract_balanced_simple() -> None:
    text = '{"a": 1}'
    result = GeminiService._extract_json_balanced(text)
    assert result == '{"a": 1}'


def test_extract_balanced_nested_braces() -> None:
    text = '{"a": {"b": "c"}}'
    result = GeminiService._extract_json_balanced(text)
    assert result is not None
    assert '"a"' in result
    assert '"b"' in result


def test_extract_balanced_picks_longest_when_multiple_objects() -> None:
    text = '{"short": 1} some noise {"longer": {"nested": true}}'
    result = GeminiService._extract_json_balanced(text)
    assert result is not None
    assert '"longer"' in result
    assert '"nested"' in result


def test_extract_balanced_markdown_code_fence_stripped() -> None:
    text = "```json\n{\"key\": \"value\"}\n```"
    result = GeminiService._extract_json_balanced(text)
    assert result is not None
    assert '"key"' in result


def test_extract_balanced_no_braces_returns_none() -> None:
    result = GeminiService._extract_json_balanced("no braces here")
    assert result is None


def test_extract_balanced_unmatched_opening_brace_returns_none() -> None:
    result = GeminiService._extract_json_balanced("{unclosed")
    assert result is None


def test_extract_balanced_only_closing_brace_returns_none() -> None:
    result = GeminiService._extract_json_balanced("} only closing")
    assert result is None


# ── parse_decision ───────────────────────────────────────────────────────────


def test_parse_decision_valid_json() -> None:
    result = GeminiService().parse_decision(
        '{"mcp_tool": "move_to", "mcp_params": {"object_id": 5}, "reasoning_summary": "moving"}'
    )
    assert result["mcp_tool"] == "move_to"
    assert result["mcp_params"] == {"object_id": 5}
    assert result["reasoning_summary"] == "moving"


def test_parse_decision_missing_mcp_tool_is_rejected_for_retry() -> None:
    with pytest.raises(ValueError, match="omitted mcp_tool"):
        GeminiService().parse_decision("{}")


def test_parse_decision_invalid_tool_is_preserved_for_structured_rejection() -> None:
    result = GeminiService().parse_decision('{"mcp_tool": "fly_away"}')
    assert result["mcp_tool"] == "fly_away"


def test_parse_decision_missing_reasoning_fills_default() -> None:
    result = GeminiService().parse_decision('{"mcp_tool": "explore"}')
    assert result["reasoning_summary"] == "No reasoning summary returned."


def test_parse_decision_missing_mcp_params_defaults_to_empty_dict() -> None:
    result = GeminiService().parse_decision('{"mcp_tool": "explore"}')
    assert result["mcp_params"] == {}


def test_parse_decision_empty_string_is_rejected_for_retry() -> None:
    with pytest.raises(ValueError, match="Could not parse"):
        GeminiService().parse_decision("")


def test_parse_decision_none_input_is_rejected_for_retry() -> None:
    with pytest.raises(ValueError, match="Could not parse"):
        GeminiService().parse_decision(None)  # type: ignore[arg-type]


def test_parse_decision_json_array_is_rejected_for_retry() -> None:
    with pytest.raises(ValueError, match="Could not parse"):
        GeminiService().parse_decision("[]")


def test_parse_decision_garbage_text_is_rejected_for_retry() -> None:
    with pytest.raises(ValueError, match="Could not parse"):
        GeminiService().parse_decision("this is not json at all")


def test_parse_decision_markdown_fenced_json() -> None:
    text = 'Here is the decision:\n\n```json\n{"mcp_tool": "explore", "reasoning_summary": "thoughtful"}\n```'
    result = GeminiService().parse_decision(text)
    assert result["mcp_tool"] == "explore"
    assert result["reasoning_summary"] == "thoughtful"


def test_parse_decision_observed_issue_as_dict() -> None:
    result = GeminiService().parse_decision(
        '{"mcp_tool": "explore", "observed_issue": {"category": "GEOMETRY", "description": "HOM"}}'
    )
    assert result["observed_issue"] == {"category": "GEOMETRY", "description": "HOM"}


def test_parse_decision_observed_issue_as_string() -> None:
    result = GeminiService().parse_decision(
        '{"mcp_tool": "explore", "observed_issue": "stuck on geometry"}'
    )
    assert result["observed_issue"] == "stuck on geometry"


def test_parse_decision_observed_issue_wrong_type_becomes_none() -> None:
    result = GeminiService().parse_decision(
        '{"mcp_tool": "explore", "observed_issue": 42}'
    )
    assert result["observed_issue"] is None


def test_parse_decision_hypotheses_are_structured_list() -> None:
    result = GeminiService().parse_decision(
        '{"mcp_tool": "explore", "hypotheses": [" Starting area blocked  ", "Starting area blocked", 3]}'
    )
    assert result["hypotheses"] == ["Starting area blocked"]


def test_parse_decision_tool_is_mcp_tool_case_sensitive() -> None:
    result = GeminiService().parse_decision(
        '{"mcp_tool": "aim_and_shoot", "mcp_params": {"object_id": 3}, "reasoning_summary": "combat"}'
    )
    assert result["mcp_tool"] == "aim_and_shoot"


def test_parse_decision_allows_select_weapon() -> None:
    result = GeminiService().parse_decision(
        '{"mcp_tool": "select_weapon", "mcp_params": {"weapon_slot": 2}, "reasoning_summary": "switch"}'
    )
    assert result["mcp_tool"] == "select_weapon"


def test_fallback_decision_selects_best_weapon_when_selected_weapon_empty() -> None:
    decision = GeminiService()._fallback_decision(
        {
            "objects": [{"id": 7, "type": "monster", "is_visible": True, "distance": 120}],
            "weapon_state": {
                "selected_weapon": 1,
                "selected_weapon_ammo": 0,
                "usable_weapons": [1, 2],
                "usable_attack_ammo": 50,
                "best_viable_weapon": 2,
            },
            "lockstep_state": {},
        },
        "Fallback.",
    )

    assert decision["mcp_tool"] == "select_weapon"
    assert decision["mcp_params"]["weapon_slot"] == 2
    assert decision["mcp_params"]["max_tics"] == 20


def test_cost_estimate_uses_per_million_rates() -> None:
    assert round(estimate_llm_cost_usd(
        1_000_000,
        500_000,
        input_cost_per_million=0.10,
        output_cost_per_million=0.40,
    ), 6) == 0.30


# ── _fallback_decision branches ──────────────────────────────────────────────


def test_fallback_visible_monster_strafe() -> None:
    decision = GeminiService()._fallback_decision(
        {
            "scene_objects": [
                {"id": 3, "type": "monster", "is_visible": True, "distance": 200, "attack_type": "hitscan"},
            ],
            "weapon_state": {"usable_weapons": [1, 2], "usable_attack_ammo": 30, "selected_weapon_ammo": 10, "best_viable_weapon": 2},
            "lockstep_state": {},
        },
        "Fallback.",
    )
    assert decision["mcp_tool"] == "strafe_and_shoot"
    assert decision["mcp_params"]["object_id"] == 3


def test_fallback_visible_monster_aim() -> None:
    decision = GeminiService()._fallback_decision(
        {
            "scene_objects": [
                {"id": 8, "type": "monster", "is_visible": True, "distance": 400, "attack_type": "projectile"},
            ],
            "weapon_state": {"usable_weapons": [1], "usable_attack_ammo": 20, "selected_weapon_ammo": 10, "best_viable_weapon": 1},
            "lockstep_state": {},
        },
        "Fallback.",
    )
    assert decision["mcp_tool"] == "aim_and_shoot"
    assert decision["mcp_params"]["object_id"] == 8


def test_fallback_visible_pickup() -> None:
    decision = GeminiService()._fallback_decision(
        {
            "scene_objects": [
                {"id": 10, "type": "ammo", "is_visible": True, "distance": 150},
            ],
            "weapon_state": {"usable_weapons": [1], "usable_attack_ammo": 30, "selected_weapon_ammo": 10, "best_viable_weapon": 1},
            "lockstep_state": {},
        },
        "Fallback.",
    )
    assert decision["mcp_tool"] == "move_to"
    assert decision["mcp_params"]["object_id"] == 10
    assert decision["mcp_params"]["stop_on_enemy"] is True


def test_fallback_no_usable_weapons() -> None:
    decision = GeminiService()._fallback_decision(
        {
            "scene_objects": [],
            "weapon_state": {"usable_weapons": [], "usable_attack_ammo": 0, "selected_weapon_ammo": 0, "best_viable_weapon": None},
            "lockstep_state": {},
        },
        "Fallback.",
    )
    assert decision["mcp_tool"] == "retreat"
    assert decision["mcp_params"]["tics"] == 28


def test_fallback_unexplored_direction() -> None:
    decision = GeminiService()._fallback_decision(
        {
            "scene_objects": [],
            "weapon_state": {"usable_weapons": [1], "usable_attack_ammo": 10, "selected_weapon_ammo": 10, "best_viable_weapon": 1},
            "navigation": {"unexplored_direction": "north"},
            "lockstep_state": {},
        },
        "Fallback.",
    )
    assert decision["mcp_tool"] == "explore"
    assert decision["mcp_params"]["max_tics"] == 80
    assert decision["mcp_params"]["stop_on_enemy"] is True
    assert decision["mcp_params"]["stop_on_item"] is True


def test_fallback_default_explore() -> None:
    decision = GeminiService()._fallback_decision(
        {
            "scene_objects": [],
            "weapon_state": {"usable_weapons": [1], "usable_attack_ammo": 10, "selected_weapon_ammo": 10, "best_viable_weapon": 1},
            "lockstep_state": {},
        },
        "Fallback.",
    )
    assert decision["mcp_tool"] == "explore"
    assert decision["mcp_params"]["max_tics"] == 80
    assert decision["mcp_params"]["stop_on_enemy"] is True
    assert decision["mcp_params"]["stop_on_item"] is True


def test_fallback_weapon_switch() -> None:
    decision = GeminiService()._fallback_decision(
        {
            "scene_objects": [],
            "weapon_state": {
                "usable_weapons": [1, 3],
                "usable_attack_ammo": 50,
                "selected_weapon_ammo": 0,
                "best_viable_weapon": 3,
            },
            "lockstep_state": {},
        },
        "Fallback.",
    )
    assert decision["mcp_tool"] == "select_weapon"
    assert decision["mcp_params"]["weapon_slot"] == 3
    assert decision["mcp_params"]["max_tics"] == 20


def test_fallback_completed_object_skipped() -> None:
    decision = GeminiService()._fallback_decision(
        {
            "scene_objects": [
                {"id": 5, "type": "ammo", "is_visible": True, "distance": 100},
            ],
            "same_run_memory": {
                "older_milestones": {"completed_targets": {"5": "done"}},
            },
            "weapon_state": {"usable_weapons": [1], "usable_attack_ammo": 10, "selected_weapon_ammo": 10, "best_viable_weapon": 1},
            "lockstep_state": {},
        },
        "Fallback.",
    )
    assert decision["mcp_tool"] != "move_to"
    assert decision["mcp_tool"] == "explore"


def test_fallback_failed_object_skipped() -> None:
    decision = GeminiService()._fallback_decision(
        {
            "scene_objects": [
                {"id": 7, "type": "weapon", "is_visible": True, "distance": 200},
            ],
            "same_run_memory": {
                "older_milestones": {"failed_targets": {"7": "unreachable"}},
            },
            "weapon_state": {"usable_weapons": [1], "usable_attack_ammo": 10, "selected_weapon_ammo": 10, "best_viable_weapon": 1},
            "lockstep_state": {},
        },
        "Fallback.",
    )
    assert decision["mcp_tool"] != "move_to"
    assert decision["mcp_tool"] == "explore"


# ── _is_rate_limit ───────────────────────────────────────────────────────────


def test_is_rate_limit_429() -> None:
    assert _is_rate_limit(Exception("HTTP 429 Too Many Requests")) is True


def test_is_rate_limit_exhausted() -> None:
    assert _is_rate_limit(Exception("RESOURCE_EXHAUSTED quota exceeded")) is True


def test_is_rate_limit_negative() -> None:
    assert _is_rate_limit(Exception("Connection timeout")) is False


# ── _retry_delay_seconds ─────────────────────────────────────────────────────


def test_retry_delay_seconds_with_retry_delay() -> None:
    exc = Exception("retryDelay : 7s")
    delay = _retry_delay_seconds(exc)
    assert 8.0 <= delay <= 17.0


def test_retry_delay_seconds_without_retry_delay() -> None:
    exc = Exception("some random error")
    delay = _retry_delay_seconds(exc)
    assert 16.0 <= delay <= 25.0


# ── _normalize_hypotheses ────────────────────────────────────────────────────


def test_normalize_hypotheses_string() -> None:
    result = _normalize_hypotheses("single hypothesis")
    assert result == ["single hypothesis"]


def test_normalize_hypotheses_dedup() -> None:
    result = _normalize_hypotheses(["foo", "FOO", "bar", "foo"])
    assert result == ["foo", "bar"]
