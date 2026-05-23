from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.websocket_service import websocket_service

router = APIRouter(tags=["Trace"])


@router.websocket("/runs/{run_id}")
async def run_websocket(run_id: UUID, websocket: WebSocket) -> None:
    await websocket_service.connect(run_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "pong":
                    websocket_service.handle_pong(websocket)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        websocket_service.disconnect(run_id, websocket)
