from __future__ import annotations

from collections import Counter
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models import StaticAnalysisResult, WadFile
from app.services.analysis_service import AnalysisService


@patch("app.services.analysis_service.asyncio.to_thread")
@patch("app.services.analysis_service.detect_map_names")
@pytest.mark.asyncio
async def test_analyze_wad_returns_list_of_static_analysis_results(
    mock_detect: MagicMock,
    mock_to_thread: AsyncMock,
) -> None:
    mock_detect.return_value = ["E1M1", "E1M2"]
    mock_to_thread.return_value = ["E1M1", "E1M2"]

    db = AsyncMock()
    wad_file = MagicMock(spec=WadFile)
    wad_file.stored_path = "/tmp/test.wad"
    wad_file.id = uuid4()

    repo = AsyncMock()
    result_1 = MagicMock(spec=StaticAnalysisResult)
    result_2 = MagicMock(spec=StaticAnalysisResult)
    repo.upsert.side_effect = [result_1, result_2]
    repo.get_by_wad_and_map.return_value = None

    service = AnalysisService(db)
    service.repo = repo

    with patch.object(service, "analyze_map", new_callable=AsyncMock) as mock_analyze:
        mock_analyze.side_effect = [result_1, result_2]

        results = await service.analyze_wad(wad_file)

    assert len(results) == 2
    assert results == [result_1, result_2]
    assert wad_file.detected_maps == ["E1M1", "E1M2"]


def test_extract_map_features_extracts_expected_fields() -> None:
    editor = MagicMock()

    door = MagicMock()
    door.special = 1
    locked_door = MagicMock()
    locked_door.special = 32
    lift = MagicMock()
    lift.special = 10
    no_special = MagicMock()
    no_special.special = 0
    editor.linedefs = [door, locked_door, lift, no_special]

    thing_counts = Counter({
        13: 1,
        6: 1,
        5: 1,
        39: 1,
        97: 1,
    })

    result = AnalysisService._extract_map_features(editor, thing_counts)

    assert result["door_count"] == 2
    assert result["locked_door_count"] == 1
    assert result["lift_count"] == 1
    assert result["teleporter_count"] == 2
    assert result["key_requirements"] == {"red": True, "yellow": True, "blue": True}


def test_extract_map_features_no_keys() -> None:
    editor = MagicMock()
    editor.linedefs = []
    thing_counts = Counter()

    result = AnalysisService._extract_map_features(editor, thing_counts)

    assert result["door_count"] == 0
    assert result["locked_door_count"] == 0
    assert result["lift_count"] == 0
    assert result["teleporter_count"] == 0
    assert result["key_requirements"] == {"red": False, "yellow": False, "blue": False}


def test_extract_map_features_secret_linedef_ignored_in_counts() -> None:
    editor = MagicMock()
    door = MagicMock()
    door.special = 1
    secret_door = MagicMock()
    secret_door.special = 1
    editor.linedefs = [door, secret_door]

    thing_counts = Counter()

    result = AnalysisService._extract_map_features(editor, thing_counts)

    assert result["door_count"] == 2


def test_map_bounds_from_editor_returns_static_coordinate_space() -> None:
    editor = MagicMock()
    editor.vertexes = [
        MagicMock(x=-128, y=-64),
        MagicMock(x=512, y=384),
    ]

    assert AnalysisService._map_bounds_from_editor(editor) == {
        "min_x": -128,
        "max_x": 512,
        "min_y": -64,
        "max_y": 384,
    }


@patch("app.services.analysis_service.ImageDraw.Draw")
@patch("app.services.analysis_service.Image.new")
def test_render_overview_generates_png(
    mock_image_new: MagicMock,
    mock_draw_cls: MagicMock,
) -> None:
    editor = MagicMock()
    v1 = MagicMock()
    v1.x = 0
    v1.y = 0
    v2 = MagicMock()
    v2.x = 100
    v2.y = 100
    editor.vertexes = [v1, v2]

    linedef = MagicMock()
    linedef.vx_a = 0
    linedef.vx_b = 1
    linedef.secret = False
    editor.linedefs = [linedef]

    mock_img = MagicMock()
    mock_image_new.return_value = mock_img
    mock_draw = MagicMock()
    mock_draw_cls.return_value = mock_draw

    service = AnalysisService.__new__(AnalysisService)
    service.settings = MagicMock()
    service.settings.analysis_storage_dir = Path("/tmp/test_analysis")

    result = service._render_overview(uuid4(), "E1M1", editor)

    mock_image_new.assert_called_once_with("RGB", (1024, 1024), "black")
    mock_img.save.assert_called_once()
    mock_draw.line.assert_called_once()
    assert result.suffix == ".png"


@patch("app.services.analysis_service.ImageDraw.Draw")
@patch("app.services.analysis_service.Image.new")
def test_render_overview_handles_empty_vertices(
    mock_image_new: MagicMock,
    mock_draw_cls: MagicMock,
) -> None:
    editor = MagicMock()
    editor.vertexes = []
    editor.linedefs = []

    mock_img = MagicMock()
    mock_image_new.return_value = mock_img
    mock_draw = MagicMock()
    mock_draw_cls.return_value = mock_draw

    service = AnalysisService.__new__(AnalysisService)
    service.settings = MagicMock()
    service.settings.analysis_storage_dir = Path("/tmp/test_analysis")

    result = service._render_overview(uuid4(), "E1M1", editor)

    mock_image_new.assert_called_once_with("RGB", (1024, 1024), "black")
    mock_img.save.assert_called_once()
    mock_draw.line.assert_not_called()
    assert result.suffix == ".png"
