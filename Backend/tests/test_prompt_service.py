"""Tests for prompt_service sanitization and rendering."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.prompt_service import _sanitize_prompt_value


def test_sanitize_prompt_value_replaces_open_brace() -> None:
    assert _sanitize_prompt_value("hello {world}") == "hello (world)"


def test_sanitize_prompt_value_replaces_close_brace() -> None:
    assert _sanitize_prompt_value("key: value}") == "key: value)"


def test_sanitize_prompt_value_replaces_multiple_braces() -> None:
    assert _sanitize_prompt_value("{a} and {b}") == "(a) and (b)"


def test_sanitize_prompt_value_passthrough_no_braces() -> None:
    assert _sanitize_prompt_value("no braces here") == "no braces here"


def test_sanitize_prompt_value_handles_non_string() -> None:
    assert _sanitize_prompt_value(42) == "42"
    assert _sanitize_prompt_value(None) == "None"


def test_sanitize_prompt_value_handles_empty_string() -> None:
    assert _sanitize_prompt_value("") == ""


def test_render_agent_prompt_produces_output() -> None:
    from app.services.prompt_service import render_agent_prompt

    wad = MagicMock()
    wad.iwad_required = "freedoom2"

    analysis = MagicMock()
    analysis.map_name = "MAP01"
    analysis.map_display_name = "Test Map"
    analysis.thing_count_enemies = 10
    analysis.enemy_breakdown = {}
    analysis.hitscanner_percent = 50.0
    analysis.health_ratio = 1.5
    analysis.ammo_ratio = 2.0
    analysis.secret_sector_count = 3
    analysis.map_width_units = 512
    analysis.map_height_units = 512
    analysis.total_health_pickup_pts = 200
    analysis.estimated_difficulty = "medium"
    analysis.spawn_summary_by_skill = {}

    run = MagicMock()
    run.difficulty_level = 3

    prompt = render_agent_prompt(wad, analysis, run)
    assert isinstance(prompt, str)
    assert len(prompt) > 100
    assert "MAP01" in prompt
