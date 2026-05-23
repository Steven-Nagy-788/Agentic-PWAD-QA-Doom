from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models import Defect, TestRun
from app.services.pattern_service import PatternService


@pytest.mark.asyncio
async def test_get_patterns_no_runs_returns_empty() -> None:
    db = AsyncMock()
    wad_id = uuid4()

    runs_result = MagicMock()
    runs_result.scalars.return_value.all.return_value = []
    db.execute.return_value = runs_result

    service = PatternService(db)
    result = await service.get_patterns(wad_id)

    assert result["total_runs"] == 0
    assert result["defect_patterns"] == []
    assert result["wad_id"] == str(wad_id)


@pytest.mark.asyncio
async def test_get_patterns_single_run_no_defects() -> None:
    db = AsyncMock()
    wad_id = uuid4()
    run_id = uuid4()
    run = MagicMock(spec=TestRun)
    run.id = run_id
    run.difficulty_level = 3
    run.outcome = "map_completed"

    runs_result = MagicMock()
    runs_result.scalars.return_value.all.return_value = [run]
    defects_result = MagicMock()
    defects_result.scalars.return_value.all.return_value = []

    db.execute = AsyncMock()
    db.execute.side_effect = [runs_result, defects_result]

    service = PatternService(db)
    result = await service.get_patterns(wad_id)

    assert result["total_runs"] == 1
    assert result["total_defects"] == 0
    assert result["defect_patterns"] == []


@pytest.mark.asyncio
async def test_get_patterns_single_run_with_defects() -> None:
    db = AsyncMock()
    wad_id = uuid4()
    run_id = uuid4()
    run = MagicMock(spec=TestRun)
    run.id = run_id
    run.difficulty_level = 3
    run.outcome = "map_completed"

    defect = MagicMock(spec=Defect)
    defect.run_id = run_id
    defect.fingerprint = "agent_observed_geometry:test_issue"
    defect.defect_type = "agent_observed_geometry"
    defect.title = "Test issue"
    defect.severity = 2
    defect.position_x = 100.0
    defect.position_y = 200.0
    defect.run = run

    runs_result = MagicMock()
    runs_result.scalars.return_value.all.return_value = [run]
    defects_result = MagicMock()
    defects_result.scalars.return_value.all.return_value = [defect]

    db.execute = AsyncMock()
    db.execute.side_effect = [runs_result, defects_result]

    service = PatternService(db)
    result = await service.get_patterns(wad_id)

    assert result["total_runs"] == 1
    assert result["total_defects"] == 1
    assert len(result["defect_patterns"]) == 0


@pytest.mark.asyncio
async def test_get_patterns_multiple_runs_same_fingerprint_groups() -> None:
    db = AsyncMock()
    wad_id = uuid4()
    run_id_1 = uuid4()
    run_id_2 = uuid4()

    run_1 = MagicMock(spec=TestRun)
    run_1.id = run_id_1
    run_1.difficulty_level = 3
    run_1.outcome = "map_completed"

    run_2 = MagicMock(spec=TestRun)
    run_2.id = run_id_2
    run_2.difficulty_level = 4
    run_2.outcome = "stuck"

    fingerprint = "agent_observed_geometry:hall_of_mirrors"
    defect_1 = MagicMock(spec=Defect)
    defect_1.run_id = run_id_1
    defect_1.fingerprint = fingerprint
    defect_1.defect_type = "agent_observed_geometry"
    defect_1.title = "Hall of mirrors"
    defect_1.severity = 2
    defect_1.position_x = 100.0
    defect_1.position_y = 200.0
    defect_1.run = run_1

    defect_2 = MagicMock(spec=Defect)
    defect_2.run_id = run_id_2
    defect_2.fingerprint = fingerprint
    defect_2.defect_type = "agent_observed_geometry"
    defect_2.title = "Hall of mirrors"
    defect_2.severity = 3
    defect_2.position_x = 110.0
    defect_2.position_y = 210.0
    defect_2.run = run_2

    runs_result = MagicMock()
    runs_result.scalars.return_value.all.return_value = [run_1, run_2]
    defects_result = MagicMock()
    defects_result.scalars.return_value.all.return_value = [defect_1, defect_2]

    db.execute = AsyncMock()
    db.execute.side_effect = [runs_result, defects_result]

    service = PatternService(db)
    result = await service.get_patterns(wad_id)

    assert result["total_runs"] == 2
    assert result["total_defects"] == 2
    assert len(result["defect_patterns"]) == 1

    pattern = result["defect_patterns"][0]
    assert pattern["fingerprint"] == fingerprint
    assert pattern["occurrence_count"] == 2
    assert pattern["affected_runs"] == 2
    assert pattern["avg_severity"] == 2.5


@pytest.mark.asyncio
async def test_get_patterns_single_occurrence_not_grouped() -> None:
    db = AsyncMock()
    wad_id = uuid4()
    run_id = uuid4()

    run = MagicMock(spec=TestRun)
    run.id = run_id
    run.difficulty_level = 3
    run.outcome = "map_completed"

    defect = MagicMock(spec=Defect)
    defect.run_id = run_id
    defect.fingerprint = "unique_fingerprint"
    defect.defect_type = "agent_observed_geometry"
    defect.title = "Unique issue"
    defect.severity = 2
    defect.position_x = 100.0
    defect.position_y = 200.0
    defect.run = run

    runs_result = MagicMock()
    runs_result.scalars.return_value.all.return_value = [run]
    defects_result = MagicMock()
    defects_result.scalars.return_value.all.return_value = [defect]

    db.execute = AsyncMock()
    db.execute.side_effect = [runs_result, defects_result]

    service = PatternService(db)
    result = await service.get_patterns(wad_id)

    assert len(result["defect_patterns"]) == 0


@pytest.mark.asyncio
async def test_get_patterns_difficulty_coverage_tracks_outcomes() -> None:
    db = AsyncMock()
    wad_id = uuid4()
    run_id = uuid4()

    run = MagicMock(spec=TestRun)
    run.id = run_id
    run.difficulty_level = 3
    run.outcome = "map_completed"

    runs_result = MagicMock()
    runs_result.scalars.return_value.all.return_value = [run]
    defects_result = MagicMock()
    defects_result.scalars.return_value.all.return_value = []

    db.execute = AsyncMock()
    db.execute.side_effect = [runs_result, defects_result]

    service = PatternService(db)
    result = await service.get_patterns(wad_id)

    coverage = result["difficulty_coverage"]
    assert 3 in coverage
    assert coverage[3]["runs"] == 1
    assert coverage[3]["completed"] == 1
    assert coverage[3]["failed"] == 0


@pytest.mark.asyncio
async def test_get_patterns_cell_clustering() -> None:
    db = AsyncMock()
    wad_id = uuid4()
    run_id = uuid4()

    run = MagicMock(spec=TestRun)
    run.id = run_id
    run.difficulty_level = 3
    run.outcome = "map_completed"

    defect = MagicMock(spec=Defect)
    defect.run_id = run_id
    defect.fingerprint = "geom:test"
    defect.defect_type = "agent_observed_geometry"
    defect.title = "Test"
    defect.severity = 2
    defect.position_x = 256.0
    defect.position_y = 256.0
    defect.run = run

    runs_result = MagicMock()
    runs_result.scalars.return_value.all.return_value = [run]
    defects_result = MagicMock()
    defects_result.scalars.return_value.all.return_value = [defect]

    db.execute = AsyncMock()
    db.execute.side_effect = [runs_result, defects_result]

    service = PatternService(db)
    result = await service.get_patterns(wad_id)

    # only one defect, no grouped pattern
    assert len(result["defect_patterns"]) == 0

    # but cell cluster should exist
    clusters = result["defect_clusters"]
    assert len(clusters) == 1
    assert clusters[0]["cell"] == {"x": 2, "y": 2}


@pytest.mark.asyncio
async def test_get_patterns_no_fingerprint_fallback_to_type_title() -> None:
    db = AsyncMock()
    wad_id = uuid4()
    run_id = uuid4()

    run = MagicMock(spec=TestRun)
    run.id = run_id
    run.difficulty_level = 3
    run.outcome = "map_completed"

    defect_1 = MagicMock(spec=Defect)
    defect_1.run_id = run_id
    defect_1.fingerprint = None
    defect_1.defect_type = "agent_observed_geometry"
    defect_1.title = "Hall of mirrors"
    defect_1.severity = 2
    defect_1.position_x = 100.0
    defect_1.position_y = 200.0
    defect_1.run = run

    defect_2 = MagicMock(spec=Defect)
    defect_2.run_id = run_id
    defect_2.fingerprint = None
    defect_2.defect_type = "agent_observed_geometry"
    defect_2.title = "Hall of mirrors"
    defect_2.severity = 3
    defect_2.position_x = 110.0
    defect_2.position_y = 210.0
    defect_2.run = run

    runs_result = MagicMock()
    runs_result.scalars.return_value.all.return_value = [run]
    defects_result = MagicMock()
    defects_result.scalars.return_value.all.return_value = [defect_1, defect_2]

    db.execute = AsyncMock()
    db.execute.side_effect = [runs_result, defects_result]

    service = PatternService(db)
    result = await service.get_patterns(wad_id)

    assert len(result["defect_patterns"]) == 1
    pattern = result["defect_patterns"][0]
    assert pattern["fingerprint"] == "agent_observed_geometry:Hall of mirrors"
    assert pattern["occurrence_count"] == 2
    assert pattern["avg_severity"] == 2.5


@pytest.mark.asyncio
async def test_get_patterns_defects_without_position_skip_grid_clusters() -> None:
    db = AsyncMock()
    wad_id = uuid4()
    run_id = uuid4()

    run = MagicMock(spec=TestRun)
    run.id = run_id
    run.difficulty_level = 3
    run.outcome = "map_completed"

    defect_with_pos = MagicMock(spec=Defect)
    defect_with_pos.run_id = run_id
    defect_with_pos.fingerprint = "fp:with_pos"
    defect_with_pos.defect_type = "agent_observed"
    defect_with_pos.title = "With position"
    defect_with_pos.severity = 2
    defect_with_pos.position_x = 100.0
    defect_with_pos.position_y = 200.0
    defect_with_pos.run = run

    defect_no_pos = MagicMock(spec=Defect)
    defect_no_pos.run_id = run_id
    defect_no_pos.fingerprint = "fp:no_pos"
    defect_no_pos.defect_type = "agent_observed"
    defect_no_pos.title = "No position"
    defect_no_pos.severity = 2
    defect_no_pos.position_x = None
    defect_no_pos.position_y = None
    defect_no_pos.run = run

    runs_result = MagicMock()
    runs_result.scalars.return_value.all.return_value = [run]
    defects_result = MagicMock()
    defects_result.scalars.return_value.all.return_value = [defect_with_pos, defect_no_pos]

    db.execute = AsyncMock()
    db.execute.side_effect = [runs_result, defects_result]

    service = PatternService(db)
    result = await service.get_patterns(wad_id)

    clusters = result["defect_clusters"]
    assert len(clusters) == 1
    assert clusters[0]["cell"] == {"x": 1, "y": 2}


@pytest.mark.asyncio
async def test_get_patterns_multiple_fingerprint_groups_sorted() -> None:
    db = AsyncMock()
    wad_id = uuid4()
    run_id = uuid4()

    run = MagicMock(spec=TestRun)
    run.id = run_id
    run.difficulty_level = 3
    run.outcome = "map_completed"

    defects = []
    for i, (fp, count) in enumerate([("fp:common", 3), ("fp:rare", 2), ("fp:unique", 2)]):
        for j in range(count):
            d = MagicMock(spec=Defect)
            d.run_id = run_id
            d.fingerprint = fp
            d.defect_type = "agent_observed"
            d.title = f"Pattern {i}"
            d.severity = 2
            d.position_x = 100.0
            d.position_y = 200.0
            d.run = run
            defects.append(d)

    runs_result = MagicMock()
    runs_result.scalars.return_value.all.return_value = [run]
    defects_result = MagicMock()
    defects_result.scalars.return_value.all.return_value = defects

    db.execute = AsyncMock()
    db.execute.side_effect = [runs_result, defects_result]

    service = PatternService(db)
    result = await service.get_patterns(wad_id)

    assert len(result["defect_patterns"]) == 3
    assert result["defect_patterns"][0]["fingerprint"] == "fp:common"
    assert result["defect_patterns"][0]["occurrence_count"] == 3
    assert result["defect_patterns"][1]["occurrence_count"] == 2
    assert result["defect_patterns"][2]["occurrence_count"] == 2


@pytest.mark.asyncio
async def test_get_patterns_multiple_defects_same_cell() -> None:
    db = AsyncMock()
    wad_id = uuid4()
    run_id = uuid4()

    run = MagicMock(spec=TestRun)
    run.id = run_id
    run.difficulty_level = 3
    run.outcome = "map_completed"

    defects = []
    for i in range(3):
        d = MagicMock(spec=Defect)
        d.run_id = run_id
        d.fingerprint = f"fp:same_cell_{i}"
        d.defect_type = "agent_observed"
        d.title = f"Same cell {i}"
        d.severity = 2
        d.position_x = 256.0
        d.position_y = 256.0
        d.run = run
        defects.append(d)

    runs_result = MagicMock()
    runs_result.scalars.return_value.all.return_value = [run]
    defects_result = MagicMock()
    defects_result.scalars.return_value.all.return_value = defects

    db.execute = AsyncMock()
    db.execute.side_effect = [runs_result, defects_result]

    service = PatternService(db)
    result = await service.get_patterns(wad_id)

    clusters = result["defect_clusters"]
    assert len(clusters) == 1
    assert clusters[0]["cell"] == {"x": 2, "y": 2}
    assert clusters[0]["count"] == 3


@pytest.mark.asyncio
async def test_get_patterns_unknown_difficulty() -> None:
    db = AsyncMock()
    wad_id = uuid4()
    run_id = uuid4()

    run = MagicMock(spec=TestRun)
    run.id = run_id
    run.difficulty_level = None
    run.outcome = "map_completed"

    runs_result = MagicMock()
    runs_result.scalars.return_value.all.return_value = [run]
    defects_result = MagicMock()
    defects_result.scalars.return_value.all.return_value = []

    db.execute = AsyncMock()
    db.execute.side_effect = [runs_result, defects_result]

    service = PatternService(db)
    result = await service.get_patterns(wad_id)

    coverage = result["difficulty_coverage"]
    assert "unknown" in coverage
    assert coverage["unknown"]["runs"] == 1
    assert coverage["unknown"]["completed"] == 1


@pytest.mark.asyncio
async def test_get_patterns_failed_outcomes_tracked() -> None:
    db = AsyncMock()
    wad_id = uuid4()
    run_id_1 = uuid4()
    run_id_2 = uuid4()
    run_id_3 = uuid4()

    run_1 = MagicMock(spec=TestRun)
    run_1.id = run_id_1
    run_1.difficulty_level = 3
    run_1.outcome = "stuck"

    run_2 = MagicMock(spec=TestRun)
    run_2.id = run_id_2
    run_2.difficulty_level = 3
    run_2.outcome = "error"

    run_3 = MagicMock(spec=TestRun)
    run_3.id = run_id_3
    run_3.difficulty_level = 3
    run_3.outcome = "pwad_crash"

    runs_result = MagicMock()
    runs_result.scalars.return_value.all.return_value = [run_1, run_2, run_3]
    defects_result = MagicMock()
    defects_result.scalars.return_value.all.return_value = []

    db.execute = AsyncMock()
    db.execute.side_effect = [runs_result, defects_result]

    service = PatternService(db)
    result = await service.get_patterns(wad_id)

    coverage = result["difficulty_coverage"]
    assert coverage[3]["runs"] == 3
    assert coverage[3]["completed"] == 0
    assert coverage[3]["failed"] == 3
