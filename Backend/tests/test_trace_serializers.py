from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.models import AgentDecision
from app.serializers.game_event_serializers import TraceEntryOut
from app.serializers.agent_decision_serializers import AgentDecisionOut


def test_trace_entry_exposes_top_level_mcp_fields() -> None:
    entry = TraceEntryOut(
        id=1,
        run_id=uuid4(),
        tick_number=12,
        recorded_at=datetime.now(UTC),
        player_x=1.0,
        player_y=2.0,
        player_angle=90,
        health=100,
        armor=0,
        ammo_bullets=50,
        ammo_shells=0,
        ammo_rockets=0,
        ammo_cells=0,
        kill_count=1,
        item_count=0,
        secret_count=0,
        weapon_selected=2,
        event_type="kill",
        action_taken={
            "mcp_tool": "strafe_and_shoot",
            "mcp_executed_tool": "strafe_and_shoot",
            "mcp_params": {"object_id": 7},
            "mcp_output": {"action_summary": {"stop_reason": "target_killed", "kills": 1}},
        },
    )

    dumped = entry.model_dump()

    assert dumped["mcp_tool"] == "strafe_and_shoot"
    assert dumped["mcp_executed_tool"] == "strafe_and_shoot"
    assert dumped["mcp_params"] == {"object_id": 7}
    assert dumped["mcp_action_summary"]["kills"] == 1
    assert dumped["mcp_stop_reason"] == "target_killed"


def test_agent_decision_serializer_exposes_llm_and_mcp_trace() -> None:
    decision = AgentDecisionOut(
        id=uuid4(),
        run_id=uuid4(),
        sequence_number=3,
        tick_before=100,
        tick_after=140,
        game_event_id=7,
        status="complete",
        llm_input_summary={"tick": 100},
        llm_decision={"mcp_tool": "explore"},
        reasoning_summary="No visible enemies; exploring with item stops enabled.",
        mcp_tool="explore",
        mcp_input={"max_tics": 80},
        mcp_output={"action_summary": {"stop_reason": "item_found"}},
        mcp_stop_reason="item_found",
        guard_modified=True,
        decision_source="deterministic_fallback",
        llm_duration_ms=12.5,
        mcp_duration_ms=4.0,
        created_at=datetime.now(UTC),
    )

    dumped = decision.model_dump()

    assert dumped["sequence_number"] == 3
    assert dumped["mcp_tool"] == "explore"
    assert dumped["mcp_stop_reason"] == "item_found"
    assert dumped["llm_input_summary"] == {"tick": 100}
    assert dumped["guard_modified"] is True
    assert dumped["decision_source"] == "deterministic_fallback"


def test_agent_decision_serializer_exposes_validation_rejection() -> None:
    decision = AgentDecision(
        id=uuid4(),
        run_id=uuid4(),
        sequence_number=4,
        status="complete",
        guard_modified=False,
        decision_source="gemini",
        mcp_output={"action_summary": {"stop_reason": "invalid_params", "validation_error": "move_to requires object_id"}},
        created_at=datetime.now(UTC),
    )

    dumped = AgentDecisionOut.model_validate(decision).model_dump()

    assert dumped["validation_rejection"] == "move_to requires object_id"
