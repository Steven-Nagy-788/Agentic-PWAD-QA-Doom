"""Ablation study framework for BoJack.

Inspired by TITAN's ablation methodology (Table 5 in the paper).
Systematically removes each component to measure its contribution to
task completion and defect detection.

Components to ablate:
1. Guards (run_guards.py) - 4 hard guards that override LLM decisions
2. Cross-run memory - spatial memory and hypothesis confidence
3. MapGraph - topological sector connectivity analysis
4. Deterministic fallback - rule-based decision tree when LLM fails
5. Execution time monitor - performance anomaly detection

Each configuration runs the same WAD+map and measures:
- Task completion (outcome)
- Coverage percent
- Defects detected
- Guard interventions count
- LLM fallback count
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AblationComponent(str, Enum):
    """Components that can be ablated."""

    GUARDS = "guards"
    CROSS_RUN_MEMORY = "cross_run_memory"
    MAP_GRAPH = "map_graph"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"
    EXECUTION_TIME_MONITOR = "execution_time_monitor"


@dataclass
class AblationConfig:
    """Configuration for a single ablation run."""

    name: str
    description: str
    disabled_components: set[AblationComponent] = field(default_factory=set)
    guard_enabled: bool = True
    cross_run_memory_enabled: bool = True
    map_graph_enabled: bool = True
    deterministic_fallback_enabled: bool = True
    execution_time_monitor_enabled: bool = True

    def __post_init__(self) -> None:
        """Apply component disabling based on disabled_components set."""
        if AblationComponent.GUARDS in self.disabled_components:
            self.guard_enabled = False
        if AblationComponent.CROSS_RUN_MEMORY in self.disabled_components:
            self.cross_run_memory_enabled = False
        if AblationComponent.MAP_GRAPH in self.disabled_components:
            self.map_graph_enabled = False
        if AblationComponent.DETERMINISTIC_FALLBACK in self.disabled_components:
            self.deterministic_fallback_enabled = False
        if AblationComponent.EXECUTION_TIME_MONITOR in self.disabled_components:
            self.execution_time_monitor_enabled = False


@dataclass
class AblationResult:
    """Results from a single ablation run."""

    config_name: str
    outcome: str
    coverage_percent: float
    defects_detected: int
    guard_interventions: int
    llm_fallback_count: int
    total_actions: int
    total_ticks: int
    execution_time_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_name": self.config_name,
            "outcome": self.outcome,
            "coverage_percent": self.coverage_percent,
            "defects_detected": self.defects_detected,
            "guard_interventions": self.guard_interventions,
            "llm_fallback_count": self.llm_fallback_count,
            "total_actions": self.total_actions,
            "total_ticks": self.total_ticks,
            "execution_time_seconds": self.execution_time_seconds,
        }


# Predefined ablation configurations following TITAN's methodology
ABLATION_CONFIGS: dict[str, AblationConfig] = {
    "full_system": AblationConfig(
        name="full_system",
        description="Full BoJack system with all components enabled",
    ),
    "no_guards": AblationConfig(
        name="no_guards",
        description="Without guard overrides - LLM decisions execute directly",
        disabled_components={AblationComponent.GUARDS},
    ),
    "no_cross_run_memory": AblationConfig(
        name="no_cross_run_memory",
        description="Without cross-run spatial memory and hypothesis confidence",
        disabled_components={AblationComponent.CROSS_RUN_MEMORY},
    ),
    "no_map_graph": AblationConfig(
        name="no_map_graph",
        description="Without MapGraph topological analysis",
        disabled_components={AblationComponent.MAP_GRAPH},
    ),
    "no_deterministic_fallback": AblationConfig(
        name="no_deterministic_fallback",
        description="Without deterministic fallback - fails if LLM unavailable",
        disabled_components={AblationComponent.DETERMINISTIC_FALLBACK},
    ),
    "no_execution_time_monitor": AblationConfig(
        name="no_execution_time_monitor",
        description="Without execution time anomaly detection",
        disabled_components={AblationComponent.EXECUTION_TIME_MONITOR},
    ),
    "guards_only": AblationConfig(
        name="guards_only",
        description="Only guards enabled - no memory, no map graph, no fallback",
        disabled_components={
            AblationComponent.CROSS_RUN_MEMORY,
            AblationComponent.MAP_GRAPH,
            AblationComponent.DETERMINISTIC_FALLBACK,
            AblationComponent.EXECUTION_TIME_MONITOR,
        },
    ),
    "memory_only": AblationConfig(
        name="memory_only",
        description="Only cross-run memory enabled - no guards, no map graph",
        disabled_components={
            AblationComponent.GUARDS,
            AblationComponent.MAP_GRAPH,
            AblationComponent.DETERMINISTIC_FALLBACK,
            AblationComponent.EXECUTION_TIME_MONITOR,
        },
    ),
}


def get_ablation_config(name: str) -> AblationConfig | None:
    """Get an ablation configuration by name."""
    return ABLATION_CONFIGS.get(name)


def list_ablation_configs() -> list[str]:
    """List all available ablation configuration names."""
    return list(ABLATION_CONFIGS.keys())


def get_runtime_overrides(config: AblationConfig) -> dict[str, Any]:
    """Convert ablation config to runtime overrides for ConfigRepository."""
    return {
        "guard_enabled": config.guard_enabled,
        "cross_run_memory_enabled": config.cross_run_memory_enabled,
        "deterministic_fallback_enabled": config.deterministic_fallback_enabled,
        "execution_time_monitor_enabled": config.execution_time_monitor_enabled,
    }


async def apply_config(config: AblationConfig) -> None:
    """Write ablation config overrides to the database ConfigRepository."""
    from app.core.database import SessionLocal
    from app.repositories.config_repository import ConfigRepository

    overrides = get_runtime_overrides(config)
    async with SessionLocal() as db:
        await ConfigRepository(db).set_many(overrides)
        await db.commit()


async def reset_config() -> None:
    """Reset all runtime overrides to defaults by removing them from the database."""
    from app.core.database import SessionLocal
    from app.repositories.config_repository import ConfigRepository

    keys = [
        "guard_enabled",
        "cross_run_memory_enabled",
        "deterministic_fallback_enabled",
        "execution_time_monitor_enabled",
    ]
    async with SessionLocal() as db:
        for key in keys:
            await ConfigRepository(db).delete(key)
        await db.commit()


def compute_ablation_summary(results: list[AblationResult]) -> dict[str, Any]:
    """Compute summary statistics across ablation results.

    Returns a dictionary with:
    - per_config: list of result dicts
    - baseline: full_system result
    - deltas: performance delta of each config vs baseline
    - component_contributions: estimated contribution of each component
    """
    baseline = next((r for r in results if r.config_name == "full_system"), None)
    if baseline is None:
        return {"error": "No full_system baseline found in results"}

    per_config = [r.to_dict() for r in results]
    deltas = []

    for result in results:
        if result.config_name == "full_system":
            continue
        delta = {
            "config_name": result.config_name,
            "coverage_delta": result.coverage_percent - baseline.coverage_percent,
            "defects_delta": result.defects_detected - baseline.defects_detected,
            "guard_interventions": result.guard_interventions,
            "llm_fallback_count": result.llm_fallback_count,
        }
        deltas.append(delta)

    component_contributions = {}
    for result in results:
        if result.config_name == "full_system":
            continue
        coverage_loss = baseline.coverage_percent - result.coverage_percent
        defects_loss = baseline.defects_detected - result.defects_detected
        component_contributions[result.config_name] = {
            "coverage_contribution_pct": round(
                coverage_loss / max(baseline.coverage_percent, 1) * 100, 1
            ),
            "defects_contribution": defects_loss,
        }

    return {
        "per_config": per_config,
        "baseline": baseline.to_dict(),
        "deltas": deltas,
        "component_contributions": component_contributions,
    }
