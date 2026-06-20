"""Direct tests for app.core.behavior_profiles module."""

from __future__ import annotations

from app.core.behavior_profiles import (
    EXPLOIT_FOCUSED,
    FAST,
    THOROUGH,
    PROFILES,
    BehaviorProfile,
    get_profile,
)


def test_profiles_dict_contains_all_three():
    assert set(PROFILES.keys()) == {"thorough", "fast", "exploit_focused"}


def test_get_profile_returns_thorough():
    profile = get_profile("thorough")
    assert profile is THOROUGH
    assert profile.name == "thorough"


def test_get_profile_returns_fast():
    profile = get_profile("fast")
    assert profile is FAST
    assert profile.name == "fast"


def test_get_profile_returns_exploit_focused():
    profile = get_profile("exploit_focused")
    assert profile is EXPLOIT_FOCUSED
    assert profile.name == "exploit_focused"


def test_get_profile_raises_for_unknown():
    import pytest
    with pytest.raises(KeyError):
        get_profile("nonexistent")


def test_thorough_profile_has_throttle_delays():
    delays = THOROUGH.throttle_delays
    assert "combat" in delays
    assert "low_health" in delays
    assert "stuck" in delays
    assert "default" in delays
    assert all(isinstance(v, float) for v in delays.values())


def test_fast_profile_is_faster_than_thorough():
    assert FAST.throttle_delays["default"] < THOROUGH.throttle_delays["default"]
    assert FAST.throttle_delays["combat"] < THOROUGH.throttle_delays["combat"]


def test_exploit_focused_is_fastest():
    assert EXPLOIT_FOCUSED.throttle_delays["default"] < FAST.throttle_delays["default"]
    assert EXPLOIT_FOCUSED.throttle_delays["stuck"] < FAST.throttle_delays["stuck"]


def test_all_profiles_have_required_attributes():
    for profile in PROFILES.values():
        assert isinstance(profile, BehaviorProfile)
        assert profile.name
        assert profile.description
        assert profile.system_prompt_addendum
        assert len(profile.throttle_delays) == 4


def test_profiles_are_dataclass_instances():
    import dataclasses
    for profile in PROFILES.values():
        assert dataclasses.is_dataclass(profile)
