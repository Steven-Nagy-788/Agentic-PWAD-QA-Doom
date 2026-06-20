from __future__ import annotations

import base64
import binascii
import contextlib
import time
from typing import Any
from uuid import UUID

from app.core.config import get_settings
from app.services.collector_service import CollectorService
from app.services.recording_service import (
    RecordingService,
    jpeg_b64,
    png_bytes_to_frame,
)
from app.services.websocket_service import websocket_service

_last_telemetry_frame_at: dict[str, float] = {}


def _pop_telemetry_frames(state: dict[str, Any]) -> list[dict[str, Any]]:
    frames = state.pop("telemetry_frames", None) if isinstance(state, dict) else None
    if not isinstance(frames, list):
        return []
    return [frame for frame in frames if isinstance(frame, dict)]


def _telemetry_sample_tick(sample: dict[str, Any], fallback: int) -> int:
    with contextlib.suppress(TypeError, ValueError):
        raw = sample.get("tic")
        if raw is not None:
            return max(0, int(float(raw)))
    return fallback


async def _record_telemetry_frames(
    run_id: UUID,
    tick: int,
    telemetry_frames: list[dict[str, Any]],
    collector: CollectorService,
    recorder: RecordingService,
) -> None:
    global _last_telemetry_frame_at
    run_key = str(run_id)
    live_fps = max(get_settings().live_frame_fps, 0.1)
    min_interval = 1.0 / live_fps

    for index, sample in enumerate(telemetry_frames):
        sample_tick = _telemetry_sample_tick(sample, fallback=tick + index + 1)
        sample_state = {
            "game_variables": sample.get("game_variables")
            or sample.get("variables")
            or sample,
            "level_completed": sample.get("level_completed"),
            "map_exit": sample.get("map_exit"),
            "next_map": sample.get("next_map"),
        }
        await collector.collect_position(run_id, sample_tick, sample_state)

        png_b64 = sample.get("screenshot_png_b64") or sample.get("screenshot_b64")
        if not isinstance(png_b64, str) or not png_b64:
            continue
        try:
            png_bytes = base64.b64decode(png_b64, validate=True)
        except (binascii.Error, ValueError):
            continue
        frame = png_bytes_to_frame(png_bytes)
        recorder.write_frame(frame, game_tick=sample_tick)

        now = time.monotonic()
        last = _last_telemetry_frame_at.get(run_key)
        if last is None or now - last >= min_interval:
            encoded = jpeg_b64(frame)
            if encoded:
                await websocket_service.broadcast(
                    run_id,
                    {
                        "type": "frame",
                        "tick": sample_tick,
                        "mime_type": "image/jpeg",
                        "frame_b64": encoded,
                    },
                )
            _last_telemetry_frame_at[run_key] = now


async def _broadcast_state(
    run_id: UUID,
    event: Any,
    decision: dict[str, Any],
    screenshot_b64: str | None = None,
    run_status: str = "running",
) -> None:
    await websocket_service.broadcast(
        run_id,
        {
            "type": "state",
            "tick": event.tick_number,
            "status": run_status,
            "health": event.health,
            "armor": event.armor,
            "kills": event.kill_count,
            "secrets": event.secret_count,
            "ammo": {
                "bullets": event.ammo_bullets,
                "shells": event.ammo_shells,
                "rockets": event.ammo_rockets,
                "cells": event.ammo_cells,
            },
            "position": {
                "x": event.player_x,
                "y": event.player_y,
                "angle": event.player_angle,
            },
            "event_type": event.event_type,
            "llm_reasoning": event.llm_reasoning,
            "action": {
                "mcp_tool": decision.get("mcp_tool"),
                "mcp_params": decision.get("mcp_params") or {},
            },
            "screenshot_b64": screenshot_b64,
        },
    )
