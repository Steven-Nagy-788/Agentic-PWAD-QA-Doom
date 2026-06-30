"""Tests for ablation study framework."""

from __future__ import annotations

from app.services.ablation_study import (
    AblationComponent,
    AblationConfig,
    AblationResult,
    compute_ablation_summary,
    get_ablation_config,
    get_runtime_overrides,
    list_ablation_configs,
)


def test_ablation_config_guards_disabled():
    config = AblationConfig(
        name="test",
        description="test",
        disabled_components={AblationComponent.GUARDS},
    )
    assert config.guard_enabled is False
    assert config.cross_run_memory_enabled is True


def test_ablation_config_multiple_disabled():
    config = AblationConfig(
        name="test",
        description="test",
        disabled_components={
            AblationComponent.GUARDS,
            AblationComponent.CROSS_RUN_MEMORY,
            AblationComponent.MAP_GRAPH,
        },
    )
    assert config.guard_enabled is False
    assert config.cross_run_memory_enabled is False
    assert config.map_graph_enabled is False
    assert config.deterministic_fallback_enabled is True


def test_list_ablation_configs():
    configs = list_ablation_configs()
    assert "full_system" in configs
    assert "no_guards" in configs
    assert "no_cross_run_memory" in configs


def test_get_ablation_config_valid():
    config = get_ablation_config("full_system")
    assert config is not None
    assert config.name == "full_system"


def test_get_ablation_config_invalid():
    config = get_ablation_config("nonexistent")
    assert config is None


def test_get_runtime_overrides():
    config = AblationConfig(
        name="test",
        description="test",
        disabled_components={AblationComponent.GUARDS},
    )
    overrides = get_runtime_overrides(config)
    assert overrides["guard_enabled"] is False
    assert overrides["cross_run_memory_enabled"] is True


def test_ablation_result_to_dict():
    result = AblationResult(
        config_name="full_system",
        outcome="map_completed",
        coverage_percent=75.0,
        defects_detected=5,
        guard_interventions=10,
        llm_fallback_count=2,
        total_actions=100,
        total_ticks=500,
        execution_time_seconds=120.0,
    )
    d = result.to_dict()
    assert d["config_name"] == "full_system"
    assert d["coverage_percent"] == 75.0
    assert d["defects_detected"] == 5


def test_compute_ablation_summary_baseline():
    results = [
        AblationResult(
            config_name="full_system",
            outcome="map_completed",
            coverage_percent=75.0,
            defects_detected=5,
            guard_interventions=10,
            llm_fallback_count=2,
            total_actions=100,
            total_ticks=500,
            execution_time_seconds=120.0,
        ),
        AblationResult(
            config_name="no_guards",
            outcome="timeout",
            coverage_percent=60.0,
            defects_detected=3,
            guard_interventions=0,
            llm_fallback_count=0,
            total_actions=80,
            total_ticks=400,
            execution_time_seconds=100.0,
        ),
    ]
    summary = compute_ablation_summary(results)
    assert "baseline" in summary
    assert summary["baseline"]["config_name"] == "full_system"
    assert len(summary["deltas"]) == 1
    assert summary["deltas"][0]["coverage_delta"] == -15.0


def test_compute_ablation_summary_no_baseline():
    results = [
        AblationResult(
            config_name="no_guards",
            outcome="timeout",
            coverage_percent=60.0,
            defects_detected=3,
            guard_interventions=0,
            llm_fallback_count=0,
            total_actions=80,
            total_ticks=400,
            execution_time_seconds=100.0,
        ),
    ]
    summary = compute_ablation_summary(results)
    assert "error" in summary
