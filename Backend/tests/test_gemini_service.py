from __future__ import annotations

from app.services.gemini_service import GeminiService, estimate_llm_cost_usd


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


def test_parse_decision_missing_mcp_tool_defaults_to_explore() -> None:
    result = GeminiService().parse_decision("{}")
    assert result["mcp_tool"] == "explore"


def test_parse_decision_invalid_tool_falls_back_to_explore() -> None:
    result = GeminiService().parse_decision('{"mcp_tool": "fly_away"}')
    assert result["mcp_tool"] == "explore"


def test_parse_decision_missing_reasoning_fills_default() -> None:
    result = GeminiService().parse_decision('{"mcp_tool": "explore"}')
    assert result["reasoning_summary"] == "No reasoning summary returned."


def test_parse_decision_missing_mcp_params_defaults_to_empty_dict() -> None:
    result = GeminiService().parse_decision('{"mcp_tool": "explore"}')
    assert result["mcp_params"] == {}


def test_parse_decision_empty_string_returns_defaults() -> None:
    result = GeminiService().parse_decision("")
    assert result["mcp_tool"] == "explore"
    assert result["mcp_params"] == {}


def test_parse_decision_none_input_returns_defaults() -> None:
    result = GeminiService().parse_decision("")  # type: ignore[arg-type]
    assert result["mcp_tool"] == "explore"


def test_parse_decision_garbage_text_returns_defaults() -> None:
    result = GeminiService().parse_decision("this is not json at all")
    assert result["mcp_tool"] == "explore"


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


def test_cost_estimate_uses_per_million_rates() -> None:
    assert round(estimate_llm_cost_usd(
        1_000_000,
        500_000,
        input_cost_per_million=0.10,
        output_cost_per_million=0.40,
    ), 6) == 0.30
