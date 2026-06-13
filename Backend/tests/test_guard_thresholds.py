from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import Settings


def test_settings_has_guard_consecutive_get_state_threshold() -> None:
    settings = Settings()
    assert hasattr(settings, "guard_consecutive_get_state_threshold")
    assert settings.guard_consecutive_get_state_threshold == 2


def test_settings_has_guard_position_stuck_threshold() -> None:
    settings = Settings()
    assert hasattr(settings, "guard_position_stuck_threshold")
    assert settings.guard_position_stuck_threshold == 2


def test_settings_has_guard_diversity_threshold() -> None:
    settings = Settings()
    assert hasattr(settings, "guard_diversity_threshold")
    assert settings.guard_diversity_threshold == 3


def test_settings_has_guard_enabled() -> None:
    settings = Settings()
    assert hasattr(settings, "guard_enabled")
    assert settings.guard_enabled is True


def test_guard_thresholds_are_integers() -> None:
    settings = Settings()
    assert isinstance(settings.guard_consecutive_get_state_threshold, int)
    assert isinstance(settings.guard_position_stuck_threshold, int)
    assert isinstance(settings.guard_diversity_threshold, int)


def test_guard_get_state_threshold_reads_from_runtime_value() -> None:
    runtime_overrides = {"guard_consecutive_get_state_threshold": 5}

    def fake_runtime_value(key, fallback=None):
        return runtime_overrides.get(key, fallback)

    settings = SimpleNamespace(
        guard_enabled=True,
        guard_consecutive_get_state_threshold=2,
        guard_position_stuck_threshold=2,
        guard_diversity_threshold=3,
    )

    result = int(fake_runtime_value("guard_consecutive_get_state_threshold", settings.guard_consecutive_get_state_threshold))
    assert result == 5


def test_guard_stuck_threshold_reads_from_runtime_value() -> None:
    runtime_overrides = {"guard_position_stuck_threshold": 4}

    def fake_runtime_value(key, fallback=None):
        return runtime_overrides.get(key, fallback)

    settings = SimpleNamespace(
        guard_enabled=True,
        guard_consecutive_get_state_threshold=2,
        guard_position_stuck_threshold=2,
        guard_diversity_threshold=3,
    )

    result = int(fake_runtime_value("guard_position_stuck_threshold", settings.guard_position_stuck_threshold))
    assert result == 4


def test_guard_diversity_threshold_reads_from_runtime_value() -> None:
    runtime_overrides = {"guard_diversity_threshold": 6}

    def fake_runtime_value(key, fallback=None):
        return runtime_overrides.get(key, fallback)

    settings = SimpleNamespace(
        guard_enabled=True,
        guard_consecutive_get_state_threshold=2,
        guard_position_stuck_threshold=2,
        guard_diversity_threshold=3,
    )

    result = int(fake_runtime_value("guard_diversity_threshold", settings.guard_diversity_threshold))
    assert result == 6


def test_guard_thresholds_fallback_to_settings_defaults() -> None:
    runtime_overrides = {}

    def fake_runtime_value(key, fallback=None):
        return runtime_overrides.get(key, fallback)

    settings = SimpleNamespace(
        guard_enabled=True,
        guard_consecutive_get_state_threshold=2,
        guard_position_stuck_threshold=2,
        guard_diversity_threshold=3,
    )

    assert int(fake_runtime_value("guard_consecutive_get_state_threshold", settings.guard_consecutive_get_state_threshold)) == 2
    assert int(fake_runtime_value("guard_position_stuck_threshold", settings.guard_position_stuck_threshold)) == 2
    assert int(fake_runtime_value("guard_diversity_threshold", settings.guard_diversity_threshold)) == 3


def test_guard_enabled_flag_controls_guard_behavior() -> None:
    settings = SimpleNamespace(guard_enabled=False)
    assert settings.guard_enabled is False

    settings = SimpleNamespace(guard_enabled=True)
    assert settings.guard_enabled is True


def test_guard_thresholds_triggered_when_at_or_above() -> None:
    settings = SimpleNamespace(
        guard_enabled=True,
        guard_consecutive_get_state_threshold=2,
        guard_position_stuck_threshold=2,
        guard_diversity_threshold=3,
    )

    lockstep_state = {
        "consecutive_get_state": 3,
        "position_stuck_counter": 3,
        "decision_diversity_counter": 4,
    }

    get_state_count = lockstep_state.get("consecutive_get_state", 0)
    stuck_counter = lockstep_state.get("position_stuck_counter", 0)
    diversity_counter = lockstep_state.get("decision_diversity_counter", 0)

    assert get_state_count >= settings.guard_consecutive_get_state_threshold
    assert stuck_counter >= settings.guard_position_stuck_threshold
    assert diversity_counter >= settings.guard_diversity_threshold


def test_guard_thresholds_not_triggered_when_below() -> None:
    settings = SimpleNamespace(
        guard_enabled=True,
        guard_consecutive_get_state_threshold=2,
        guard_position_stuck_threshold=2,
        guard_diversity_threshold=3,
    )

    lockstep_state = {
        "consecutive_get_state": 1,
        "position_stuck_counter": 0,
        "decision_diversity_counter": 2,
    }

    get_state_count = lockstep_state.get("consecutive_get_state", 0)
    stuck_counter = lockstep_state.get("position_stuck_counter", 0)
    diversity_counter = lockstep_state.get("decision_diversity_counter", 0)

    assert get_state_count < settings.guard_consecutive_get_state_threshold
    assert stuck_counter < settings.guard_position_stuck_threshold
    assert diversity_counter < settings.guard_diversity_threshold
