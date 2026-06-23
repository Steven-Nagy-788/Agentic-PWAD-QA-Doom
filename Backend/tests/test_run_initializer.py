from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.run_initializer import (
    RunInitContext,
    _build_cross_run_memory_context,
    _build_per_decision_cross_run_context,
    init_gemini,
    init_lockstep_state,
    init_recorder,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hypothesis(tag: str, content: str, confidence: float) -> MagicMock:
    h = MagicMock()
    h.tag = tag
    h.content = content
    h.confidence = confidence
    return h


def _make_spatial(
    cell_x: int, cell_y: int, event_type: str, occurrence_count: int,
) -> MagicMock:
    s = MagicMock()
    s.cell_x = cell_x
    s.cell_y = cell_y
    s.event_type = event_type
    s.occurrence_count = occurrence_count
    return s


def _make_ctx(**overrides) -> RunInitContext:
    defaults = dict(
        run_id=uuid.uuid4(),
        wad_file_id=uuid.uuid4(),
        map_name="E1M1",
        max_ticks=500,
        seed=None,
        iwad_used="doom.wad",
        difficulty_level="medium",
        llm_model="gemini-2.0-flash",
        prompt="test prompt",
        wad_stored_path="/tmp/test.wad",
        recording_fps=24.0,
        gemini_rate_limit=10,
        total_map_cells_estimate=None,
    )
    defaults.update(overrides)
    return RunInitContext(**defaults)


def _mock_db_execute(results_map: dict[str, list]) -> AsyncMock:
    """Return an AsyncMock db whose execute() dispatches by model class name."""
    db = AsyncMock()

    def _execute(stmt):
        model_class_name = stmt.column_descriptions[0]["name"]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = results_map.get(
            model_class_name, []
        )
        return mock_result

    db.execute = AsyncMock(side_effect=_execute)
    return db


# ---------------------------------------------------------------------------
# _build_cross_run_memory_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_cross_run_memory_with_hypotheses_and_spatial():
    hyp1 = _make_hypothesis("ENCOUNTER_HOTSPOT", "Big fight ahead", 0.9)
    hyp2 = _make_hypothesis("KEY_LOCATION", "Red key behind door", 0.7)
    sp1 = _make_spatial(3, 5, "death", 7)
    sp2 = _make_spatial(10, 2, "stuck", 4)

    db = _mock_db_execute({
        "WadHypothesis": [hyp1, hyp2],
        "WadSpatialMemory": [sp1, sp2],
    })

    result = await _build_cross_run_memory_context(
        db, uuid.uuid4(), "E1M1",
    )

    assert "CROSS-RUN HYPOTHESES" in result
    assert "KNOWN DANGER ZONES" in result
    assert "Big fight ahead" in result
    assert "Red key behind door" in result
    assert "Cell (3,5)" in result
    assert "death x7" in result


@pytest.mark.asyncio
async def test_build_cross_run_memory_empty():
    db = _mock_db_execute({})

    result = await _build_cross_run_memory_context(
        db, uuid.uuid4(), "E1M1",
    )

    assert result == ""


@pytest.mark.asyncio
async def test_build_cross_run_memory_only_hypotheses():
    hyp = _make_hypothesis("RESOURCE_CACHE", "Shell box nearby", 0.6)

    db = _mock_db_execute({
        "WadHypothesis": [hyp],
        "WadSpatialMemory": [],
    })

    result = await _build_cross_run_memory_context(
        db, uuid.uuid4(), "E1M1",
    )

    assert "CROSS-RUN HYPOTHESES" in result
    assert "KNOWN DANGER ZONES" not in result
    assert "Shell box nearby" in result


# ---------------------------------------------------------------------------
# _build_per_decision_cross_run_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_per_decision_with_danger_zones():
    player_x, player_y, cell_size = 768.0, 1280.0, 256
    # player cell: round(768/256)=3, round(1280/256)=5

    sp_near = _make_spatial(3, 5, "death", 5)
    sp_far = _make_spatial(50, 50, "stuck", 10)

    db = _mock_db_execute({
        "WadSpatialMemory": [sp_near, sp_far],
        "WadHypothesis": [],
        "TestRun": [],
    })

    result = await _build_per_decision_cross_run_context(
        db, uuid.uuid4(), "E1M1", player_x, player_y, cell_size,
    )

    assert len(result["danger_zones"]) >= 1
    near = next(d for d in result["danger_zones"] if d["cell_x"] == 3)
    assert near["event"] == "death"
    assert near["distance_cells"] == 0


@pytest.mark.asyncio
async def test_build_per_decision_empty():
    db = _mock_db_execute({})

    result = await _build_per_decision_cross_run_context(
        db, uuid.uuid4(), "E1M1", 0.0, 0.0, 256,
    )

    assert result["danger_zones"] == []
    assert result["hypotheses"] == []
    assert result["run_summaries"] == []


@pytest.mark.asyncio
async def test_build_per_decision_cell_size_affects_radius():
    player_x, player_y = 640.0, 640.0

    sp_cell1 = _make_spatial(2, 2, "death", 3)  # round(640/256)=2
    sp_cell5 = _make_spatial(5, 2, "stuck", 3)  # 5 - 2 = 3 cells away

    db_small = _mock_db_execute({
        "WadSpatialMemory": [sp_cell1],
        "WadHypothesis": [],
        "TestRun": [],
    })

    result_small = await _build_per_decision_cross_run_context(
        db_small, uuid.uuid4(), "E1M1", player_x, player_y, cell_size=256,
    )
    assert len(result_small["danger_zones"]) == 1

    db_large = _mock_db_execute({
        "WadSpatialMemory": [sp_cell1, sp_cell5],
        "WadHypothesis": [],
        "TestRun": [],
    })

    result_large = await _build_per_decision_cross_run_context(
        db_large, uuid.uuid4(), "E1M1", player_x, player_y, cell_size=128,
    )
    # cell_size=128 → cx=5, cy=5. sp_cell1 is (2,2) distance=3, sp_cell5 is (5,2) distance=3
    # both within radius 5
    assert len(result_large["danger_zones"]) == 2


# ---------------------------------------------------------------------------
# init_lockstep_state
# ---------------------------------------------------------------------------


def test_init_lockstep_state_with_cells():
    ctx = _make_ctx(total_map_cells_estimate=1024)
    state = init_lockstep_state(ctx)
    assert state["total_map_cells_estimate"] == 1024


def test_init_lockstep_state_without_cells():
    ctx = _make_ctx(total_map_cells_estimate=None)
    state = init_lockstep_state(ctx)
    assert "total_map_cells_estimate" not in state


# ---------------------------------------------------------------------------
# init_recorder
# ---------------------------------------------------------------------------


def test_init_recorder_creates_service():
    run_id = uuid.uuid4()
    ctx = _make_ctx(run_id=run_id, recording_fps=30.0)

    recorder = init_recorder(ctx)

    assert recorder.run_id == str(run_id)
    assert recorder.fps == 30.0


# ---------------------------------------------------------------------------
# init_gemini
# ---------------------------------------------------------------------------


def test_init_gemini_creates_service():
    ctx = _make_ctx(llm_model="gemini-2.5-pro", gemini_rate_limit=5)

    gemini = init_gemini(ctx)

    assert gemini.llm_model == "gemini-2.5-pro"
    assert gemini.rate_limit_calls_per_minute == 5
