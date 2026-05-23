from __future__ import annotations

from app.services.collector_service import normalize_observed_issue


def test_string_input_uses_bracket_category() -> None:
    defect_type, title = normalize_observed_issue("[GEOMETRY] Hall of mirrors")
    assert defect_type == "agent_observed_geometry"
    assert "geometry" in title


def test_string_input_no_bracket_defaults_agent_observed() -> None:
    defect_type, title = normalize_observed_issue("some generic issue")
    assert defect_type == "agent_observed_agent_observed"
    assert "agent observed" in title


def test_dict_known_category_returns_normalized() -> None:
    defect_type, title = normalize_observed_issue({"category": "GEOMETRY", "description": "HOM"})
    assert defect_type == "agent_observed_geometry"
    assert "geometry" in title


def test_dict_known_category_lowercase() -> None:
    defect_type, title = normalize_observed_issue({"category": "geometry", "description": "HOM"})
    assert defect_type == "agent_observed_geometry"


def test_dict_known_resource_balance() -> None:
    defect_type, title = normalize_observed_issue({"category": "resource_balance", "description": "no ammo"})
    assert defect_type == "agent_observed_resource_balance"


def test_dict_known_progression() -> None:
    defect_type, title = normalize_observed_issue({"category": "progression", "description": "stuck"})
    assert defect_type == "agent_observed_progression"


def test_dict_known_encounter_design() -> None:
    defect_type, title = normalize_observed_issue({"category": "encounter_design", "description": "too many"})
    assert defect_type == "agent_observed_encounter_design"


def test_dict_known_pwad_crash() -> None:
    defect_type, title = normalize_observed_issue({"category": "pwad_crash", "description": "segfault"})
    assert defect_type == "agent_observed_pwad_crash"


def test_dict_unknown_category_falls_back_to_agent_observed() -> None:
    defect_type, title = normalize_observed_issue({"category": "graphics_glitch", "description": "weird texture"})
    assert defect_type == "agent_observed_agent_observed"


def test_dict_missing_category_defaults_to_agent_observed() -> None:
    defect_type, title = normalize_observed_issue({"description": "something happened"})
    assert defect_type == "agent_observed_agent_observed"


def test_none_input_returns_agent_observed() -> None:
    defect_type, title = normalize_observed_issue(None)
    assert defect_type == "agent_observed_agent_observed"
    assert "agent observed" in title


def test_list_input_returns_agent_observed() -> None:
    defect_type, title = normalize_observed_issue(["item1", "item2"])
    assert defect_type == "agent_observed_agent_observed"


def test_empty_string_returns_agent_observed() -> None:
    defect_type, title = normalize_observed_issue("")
    assert "agent_observed" in defect_type


def test_dict_empty_category_falls_back() -> None:
    defect_type, title = normalize_observed_issue({"category": "", "description": "desc"})
    assert defect_type == "agent_observed_agent_observed"


def test_title_contains_readable_category_name() -> None:
    _, title = normalize_observed_issue({"category": "progression", "description": "stuck"})
    assert "progression" in title.lower()
