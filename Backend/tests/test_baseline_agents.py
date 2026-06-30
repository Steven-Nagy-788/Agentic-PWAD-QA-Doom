"""Tests for baseline comparison agents."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.baseline_agents import (
    GuardOnlyAgent,
    PureLLMAgent,
    RandomAgent,
    get_baseline_agent,
)


def test_random_agent_selects_valid_tool():
    agent = RandomAgent(seed=42)
    state = {"game_variables": {"HEALTH": 100}}
    lockstep_state = {}
    decision = agent.decide(state, lockstep_state, 0)
    assert "mcp_tool" in decision
    assert "mcp_params" in decision
    assert decision["mcp_tool"] in [
        "explore",
        "move_to",
        "aim_and_shoot",
        "strafe_and_shoot",
        "select_weapon",
        "retreat",
        "finish",
    ]


def test_random_agent_deterministic_with_seed():
    agent1 = RandomAgent(seed=42)
    agent2 = RandomAgent(seed=42)
    state = {"game_variables": {}}
    lockstep_state = {}
    d1 = agent1.decide(state, lockstep_state, 0)
    d2 = agent2.decide(state, lockstep_state, 0)
    assert d1["mcp_tool"] == d2["mcp_tool"]


def test_random_agent_explore_params():
    agent = RandomAgent(seed=1)
    state = {"game_variables": {}}
    lockstep_state = {}
    for _ in range(20):
        decision = agent.decide(state, lockstep_state, 0)
        if decision["mcp_tool"] == "explore":
            assert "max_tics" in decision["mcp_params"]
            assert "stop_on_enemy" in decision["mcp_params"]
            return
    pytest.skip("No explore selected in 20 tries")


@pytest.mark.asyncio
async def test_pure_llm_agent():
    mock_gemini = AsyncMock()
    mock_gemini.decide.return_value = (
        {"mcp_tool": "explore", "reasoning_summary": "test"},
        {"prompt_tokens": 100, "completion_tokens": 50},
    )
    agent = PureLLMAgent(mock_gemini)
    result = await agent.decide("prompt", {"game_variables": {}})
    assert result["decision"]["mcp_tool"] == "explore"
    assert result["guard_modified"] is False
    assert result["decision_source"] == "gemini"


def test_guard_only_agent_default_explore():
    agent = GuardOnlyAgent()
    state = {"game_variables": {}}
    lockstep_state = {}
    decision = agent.decide(state, lockstep_state, 0)
    assert decision["mcp_tool"] == "explore"


def test_guard_only_agent_get_state_spam():
    agent = GuardOnlyAgent()
    state = {"game_variables": {}}
    lockstep_state = {"consecutive_get_state": 3}
    decision = agent.decide(state, lockstep_state, 0)
    assert decision["mcp_tool"] == "explore"
    assert decision["mcp_params"]["turn_before"] == 180.0


def test_guard_only_agent_stuck():
    agent = GuardOnlyAgent()
    state = {"game_variables": {}}
    lockstep_state = {"position_stuck_counter": 3}
    decision = agent.decide(state, lockstep_state, 0)
    assert decision["mcp_tool"] == "explore"
    assert decision["mcp_params"]["turn_before"] == -180.0


def test_guard_only_agent_diversity():
    agent = GuardOnlyAgent()
    state = {"game_variables": {}}
    lockstep_state = {"decision_diversity_counter": 4}
    decision = agent.decide(state, lockstep_state, 0)
    assert decision["mcp_tool"] == "explore"
    assert decision["mcp_params"]["turn_before"] == 90.0


def test_get_baseline_agent_random():
    agent = get_baseline_agent("random", seed=42)
    assert isinstance(agent, RandomAgent)


def test_get_baseline_agent_guard_only():
    agent = get_baseline_agent("guard_only")
    assert isinstance(agent, GuardOnlyAgent)


def test_get_baseline_agent_pure_llm():
    mock_gemini = MagicMock()
    agent = get_baseline_agent("pure_llm", gemini_service=mock_gemini)
    assert isinstance(agent, PureLLMAgent)


def test_get_baseline_agent_invalid():
    with pytest.raises(ValueError, match="Unknown baseline type"):
        get_baseline_agent("invalid")
