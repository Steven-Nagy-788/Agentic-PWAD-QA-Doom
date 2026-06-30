"""Baseline agents for comparison studies.

Inspired by TITAN's evaluation methodology (Section 4.3).
Provides baseline implementations to compare against BoJack's full system:

1. RandomAgent - randomly selects from available MCP tools
2. PureLLMAgent - uses LLM without guard overrides
3. GuardOnlyAgent - uses only guards without LLM (deterministic rules)

These baselines help quantify the contribution of each BoJack component.
"""

from __future__ import annotations

import random
from typing import Any
from uuid import UUID

from app.core.types import LockstepState


AVAILABLE_MCP_TOOLS = [
    "explore",
    "move_to",
    "aim_and_shoot",
    "strafe_and_shoot",
    "select_weapon",
    "retreat",
    "finish",
]


class RandomAgent:
    """Randomly selects actions from available MCP tools.

    Baseline: demonstrates what happens with no intelligence.
    """

    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)

    def decide(
        self,
        state: dict[str, Any],
        lockstep_state: LockstepState,
        tick: int,
    ) -> dict[str, Any]:
        """Select a random action."""
        tool = self.rng.choice(AVAILABLE_MCP_TOOLS)
        params = self._random_params(tool, state)
        return {
            "reasoning_summary": f"Random agent selected {tool}",
            "mcp_tool": tool,
            "mcp_params": params,
        }

    def _random_params(self, tool: str, state: dict[str, Any]) -> dict[str, Any]:
        """Generate random parameters for a tool."""
        if tool == "explore":
            return {
                "max_tics": self.rng.randint(20, 100),
                "stop_on_enemy": self.rng.choice([True, False]),
                "stop_on_item": self.rng.choice([True, False]),
                "turn_before": self.rng.uniform(-180, 180),
            }
        elif tool == "move_to":
            return {
                "target_x": self.rng.uniform(-1000, 1000),
                "target_y": self.rng.uniform(-1000, 1000),
                "max_tics": self.rng.randint(20, 140),
            }
        elif tool in ("aim_and_shoot", "strafe_and_shoot"):
            return {
                "max_tics": self.rng.randint(10, 90),
            }
        elif tool == "select_weapon":
            return {
                "weapon_slot": self.rng.randint(1, 7),
            }
        elif tool == "retreat":
            return {
                "tics": self.rng.randint(8, 70),
            }
        elif tool == "finish":
            return {
                "outcome": "qa_completed",
            }
        return {}


class PureLLMAgent:
    """Uses LLM decisions without guard overrides.

    Baseline: demonstrates what happens with LLM but no safety net.
    """

    def __init__(self, gemini_service: Any) -> None:
        self.gemini = gemini_service

    async def decide(
        self,
        prompt: str,
        llm_input: dict[str, Any],
        screenshot_png: bytes | None = None,
        map_layout_png: bytes | None = None,
    ) -> dict[str, Any]:
        """Get LLM decision without guard processing."""
        decision, token_usage = await self.gemini.decide(
            prompt,
            llm_input,
            screenshot_png=screenshot_png,
            map_layout_png=map_layout_png,
        )
        return {
            "decision": decision,
            "token_usage": token_usage,
            "guard_modified": False,
            "decision_source": "gemini",
        }


class GuardOnlyAgent:
    """Uses only deterministic guard rules without LLM.

    Baseline: demonstrates what happens with rules but no intelligence.
    """

    def decide(
        self,
        state: dict[str, Any],
        lockstep_state: LockstepState,
        tick: int,
    ) -> dict[str, Any]:
        """Apply guard logic directly without LLM input."""
        get_state_count = lockstep_state.get("consecutive_get_state", 0)
        if get_state_count >= 2:
            return {
                "reasoning_summary": "Guard: forcing explore after consecutive get_state",
                "mcp_tool": "explore",
                "mcp_params": {
                    "max_tics": 80,
                    "stop_on_enemy": False,
                    "stop_on_item": True,
                    "turn_before": 180.0,
                },
            }

        stuck_counter = lockstep_state.get("position_stuck_counter", 0)
        if stuck_counter >= 2:
            turn_amount = 180.0 if stuck_counter % 2 == 0 else -180.0
            return {
                "reasoning_summary": f"Guard: forcing explore after stuck ({stuck_counter})",
                "mcp_tool": "explore",
                "mcp_params": {
                    "max_tics": 80,
                    "stop_on_enemy": False,
                    "stop_on_item": True,
                    "turn_before": turn_amount,
                },
            }

        diversity_counter = lockstep_state.get("decision_diversity_counter", 0)
        if diversity_counter >= 3:
            return {
                "reasoning_summary": f"Guard: forcing diverse explore after {diversity_counter} repeated",
                "mcp_tool": "explore",
                "mcp_params": {
                    "max_tics": 80,
                    "stop_on_enemy": False,
                    "stop_on_item": False,
                    "turn_before": 90.0,
                },
            }

        return {
            "reasoning_summary": "Guard: default explore",
            "mcp_tool": "explore",
            "mcp_params": {
                "max_tics": 50,
                "stop_on_enemy": True,
                "stop_on_item": True,
            },
        }


def get_baseline_agent(
    baseline_type: str, **kwargs: Any
) -> RandomAgent | PureLLMAgent | GuardOnlyAgent:
    """Factory function to create baseline agents."""
    if baseline_type == "random":
        return RandomAgent(seed=kwargs.get("seed"))
    elif baseline_type == "pure_llm":
        gemini_service = kwargs.get("gemini_service")
        if gemini_service is None:
            raise ValueError("gemini_service required for pure_llm baseline")
        return PureLLMAgent(gemini_service)
    elif baseline_type == "guard_only":
        return GuardOnlyAgent()
    else:
        raise ValueError(f"Unknown baseline type: {baseline_type}")
