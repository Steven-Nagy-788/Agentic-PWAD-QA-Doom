from __future__ import annotations

from app.services.collector_service import normalize_observed_issue, normalize_variables


def test_string_input_uses_bracket_category() -> None:
    defect_type, title = normalize_observed_issue("[GEOMETRY] Hall of mirrors")
    assert defect_type == "agent_observed_geometry"
    assert "geometry" in title


def test_string_input_no_bracket_defaults_agent_observed() -> None:
    defect_type, title = normalize_observed_issue("some generic issue")
    assert defect_type == "agent_observed_issue"
    assert "issue" in title


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


def test_dict_unknown_category_falls_back_to_slug() -> None:
    defect_type, title = normalize_observed_issue({"category": "graphics_glitch", "description": "weird texture"})
    assert defect_type == "agent_observed_graphics_glitch"
    assert "graphics glitch" in title


def test_dict_missing_category_defaults_to_issue() -> None:
    defect_type, title = normalize_observed_issue({"description": "something happened"})
    assert defect_type == "agent_observed_issue"
    assert "issue" in title


def test_none_input_returns_issue() -> None:
    defect_type, title = normalize_observed_issue(None)
    assert defect_type == "agent_observed_issue"
    assert "issue" in title


def test_list_input_returns_issue() -> None:
    defect_type, title = normalize_observed_issue(["item1", "item2"])
    assert defect_type == "agent_observed_issue"


def test_empty_string_returns_issue() -> None:
    defect_type, title = normalize_observed_issue("")
    assert "issue" in defect_type


def test_dict_empty_category_falls_back() -> None:
    defect_type, title = normalize_observed_issue({"category": "", "description": "desc"})
    assert defect_type == "agent_observed_issue"


def test_title_contains_readable_category_name() -> None:
    _, title = normalize_observed_issue({"category": "progression", "description": "stuck"})
    assert "progression" in title.lower()


def test_normalize_variables_uses_usable_attack_ammo_for_ammo_total() -> None:
    state = {
        "game_variables": {
            "AMMO0": 0,
            "AMMO1": 0,
            "AMMO2": 150,
            "AMMO3": 40,
            "SELECTED_WEAPON": 1,
            "SELECTED_WEAPON_AMMO": 0,
        },
        "weapon_state": {
            "selected_weapon": 1,
            "selected_weapon_ammo": 0,
            "usable_weapons": [1, 2, 3],
            "usable_attack_ammo": 150,
            "best_viable_weapon": 2,
        },
    }

    variables = normalize_variables(state)

    assert variables["ammo_total"] == 150
    assert variables["selected_weapon_ammo"] == 0
    assert variables["usable_weapons"] == [1, 2, 3]
    assert variables["raw_ammo_slots"]["AMMO2"] == 150
