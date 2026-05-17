from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WadFileOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "9d1bf2ec-7f42-4fcb-a8a9-6b4f4fced001",
                "original_filename": "custom_map.wad",
                "file_size_bytes": 2097152,
                "validation_status": "valid_pwad",
                "detected_maps": ["MAP01"],
                "iwad_required": "freedoom2",
                "uploaded_at": "2026-05-16T10:00:00Z",
            }
        },
    )

    id: UUID
    original_filename: str
    file_size_bytes: int
    sha256_hash: str
    validation_status: str
    validation_error: str | None = None
    detected_maps: list[str] | None = None
    iwad_required: str
    uploaded_at: datetime


class WadMapOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "wad_file_id": "9d1bf2ec-7f42-4fcb-a8a9-6b4f4fced001",
                "map_name": "E1M1",
                "iwad_required": "freedoom1",
                "analyzed": True,
                "map_overview_png_url": "/wads/9d1bf2ec-7f42-4fcb-a8a9-6b4f4fced001/map-png?map_name=E1M1",
            }
        }
    )

    wad_file_id: UUID
    map_name: str
    iwad_required: str
    analyzed: bool
    map_overview_png_url: str | None = None
