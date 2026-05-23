from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models import WadFile
from app.services.wad_service import WadService


@pytest.mark.asyncio
async def test_list_calls_repository_and_returns_results() -> None:
    db = AsyncMock()
    service = WadService(db)
    mock_repo = AsyncMock()
    wads = [MagicMock(spec=WadFile) for _ in range(3)]
    mock_repo.list.return_value = wads
    service.repo = mock_repo

    result = await service.list(limit=10, offset=0)

    assert result == wads
    mock_repo.list.assert_called_once_with(limit=10, offset=0)


@pytest.mark.asyncio
async def test_get_returns_wad() -> None:
    db = AsyncMock()
    service = WadService(db)
    mock_repo = AsyncMock()
    wad = MagicMock(spec=WadFile)
    wad_id = uuid4()
    mock_repo.get_by_id.return_value = wad
    service.repo = mock_repo

    result = await service.get(wad_id)

    assert result == wad
    mock_repo.get_by_id.assert_called_once_with(wad_id)


@pytest.mark.asyncio
async def test_get_raises_404_when_not_found() -> None:
    db = AsyncMock()
    service = WadService(db)
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = None
    service.repo = mock_repo

    with pytest.raises(HTTPException) as exc:
        await service.get(uuid4())

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_removes_wad() -> None:
    db = AsyncMock()
    wad_id = uuid4()
    wad = MagicMock(spec=WadFile)
    wad.id = wad_id
    wad.stored_path = "/tmp/nonexistent.wad"

    run = MagicMock()
    run.id = uuid4()
    run.recording_mp4_path = None

    analysis = MagicMock()
    analysis.map_overview_png_path = None

    service = WadService(db)
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = wad
    service.repo = mock_repo

    with (
        patch("app.services.wad_service.RunRepository") as mock_run_repo_cls,
        patch("app.services.wad_service.AnalysisRepository") as mock_analysis_repo_cls,
    ):
        mock_run_repo = AsyncMock()
        mock_run_repo.has_active_for_wad.return_value = False
        mock_run_repo_cls.return_value = mock_run_repo

        mock_analysis_repo = AsyncMock()
        mock_analysis_repo.list_by_wad.return_value = [analysis]
        mock_analysis_repo_cls.return_value = mock_analysis_repo

        runs_result = MagicMock()
        runs_result.scalars.return_value.all.return_value = [run]
        screenshots_result = MagicMock()
        screenshots_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock()
        db.execute.side_effect = [runs_result, screenshots_result]

        await service.delete(wad_id)

    mock_run_repo.has_active_for_wad.assert_called_once_with(wad_id)
    mock_repo.get_by_id.assert_called_once_with(wad_id)


@pytest.mark.asyncio
async def test_delete_raises_404_when_not_found() -> None:
    db = AsyncMock()
    service = WadService(db)
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = None
    service.repo = mock_repo

    with pytest.raises(HTTPException) as exc:
        await service.delete(uuid4())

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_raises_409_when_run_active() -> None:
    db = AsyncMock()
    wad_id = uuid4()
    wad = MagicMock(spec=WadFile)
    wad.id = wad_id

    service = WadService(db)
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = wad
    service.repo = mock_repo

    with patch("app.services.wad_service.RunRepository") as mock_run_repo_cls:
        mock_run_repo = AsyncMock()
        mock_run_repo.has_active_for_wad.return_value = True
        mock_run_repo_cls.return_value = mock_run_repo

        with pytest.raises(HTTPException) as exc:
            await service.delete(wad_id)

        assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_all_maps_returns_maps() -> None:
    db = AsyncMock()
    wad = MagicMock(spec=WadFile)
    wad.id = uuid4()

    service = WadService(db)
    mock_repo = AsyncMock()
    mock_repo.list.return_value = [wad]
    service.repo = mock_repo

    service._maps_for_wad = AsyncMock()
    service._maps_for_wad.return_value = ["map_out_a", "map_out_b"]

    result = await service.all_maps()

    assert result == ["map_out_a", "map_out_b"]
    mock_repo.list.assert_called_once()


@pytest.mark.asyncio
async def test_all_maps_with_wad_file_id_delegates_to_maps() -> None:
    db = AsyncMock()
    wad_id = uuid4()

    service = WadService(db)
    service.maps = AsyncMock()
    service.maps.return_value = ["map_out"]

    result = await service.all_maps(wad_file_id=wad_id)

    assert result == ["map_out"]
    service.maps.assert_called_once_with(wad_id)


@pytest.mark.asyncio
async def test_maps_returns_maps_for_wad() -> None:
    db = AsyncMock()
    wad_id = uuid4()
    wad = MagicMock(spec=WadFile)
    wad.id = wad_id

    service = WadService(db)
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = wad
    service.repo = mock_repo

    service._maps_for_wad = AsyncMock()
    service._maps_for_wad.return_value = ["map_out"]

    result = await service.maps(wad_id)

    assert result == ["map_out"]


@pytest.mark.asyncio
async def test_schedule_reanalysis_returns_wad() -> None:
    db = AsyncMock()
    wad_id = uuid4()
    wad = MagicMock(spec=WadFile)
    wad.id = wad_id

    service = WadService(db)
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = wad
    service.repo = mock_repo

    with patch("asyncio.create_task") as mock_create_task:
        result = await service.schedule_reanalysis(wad_id)

    assert result == wad
    mock_create_task.assert_called_once()


@pytest.mark.asyncio
async def test_map_png_path_returns_path() -> None:
    db = AsyncMock()
    wad_id = uuid4()
    wad = MagicMock(spec=WadFile)
    wad.id = wad_id
    wad.detected_maps = ["E1M1"]

    service = WadService(db)
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = wad
    service.repo = mock_repo

    analysis = MagicMock()
    analysis.map_overview_png_path = "/tmp/overview.png"

    with patch("app.services.wad_service.AnalysisService") as mock_cls:
        mock_analysis = AsyncMock()
        mock_analysis.analyze_map.return_value = analysis
        mock_cls.return_value = mock_analysis

        result = await service.map_png_path(wad_id, "E1M1")

    assert result == Path("/tmp/overview.png")


@pytest.mark.asyncio
async def test_map_png_path_uses_first_map_when_name_is_none() -> None:
    db = AsyncMock()
    wad_id = uuid4()
    wad = MagicMock(spec=WadFile)
    wad.id = wad_id
    wad.detected_maps = ["MAP01", "MAP02"]

    service = WadService(db)
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = wad
    service.repo = mock_repo

    analysis = MagicMock()
    analysis.map_overview_png_path = "/tmp/overview.png"

    with patch("app.services.wad_service.AnalysisService") as mock_cls:
        mock_analysis = AsyncMock()
        mock_analysis.analyze_map.return_value = analysis
        mock_cls.return_value = mock_analysis

        result = await service.map_png_path(wad_id, None)

    assert result == Path("/tmp/overview.png")
    mock_analysis.analyze_map.assert_called_once_with(wad, "MAP01")


@pytest.mark.asyncio
async def test_map_png_path_raises_404_when_no_png() -> None:
    db = AsyncMock()
    wad_id = uuid4()
    wad = MagicMock(spec=WadFile)
    wad.id = wad_id
    wad.detected_maps = ["E1M1"]

    service = WadService(db)
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = wad
    service.repo = mock_repo

    analysis = MagicMock()
    analysis.map_overview_png_path = None

    with patch("app.services.wad_service.AnalysisService") as mock_cls:
        mock_analysis = AsyncMock()
        mock_analysis.analyze_map.return_value = analysis
        mock_cls.return_value = mock_analysis

        with pytest.raises(HTTPException) as exc:
            await service.map_png_path(wad_id, "E1M1")

        assert exc.value.status_code == 404
