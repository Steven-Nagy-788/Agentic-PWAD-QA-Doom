from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.websocket_service import websocket_service

router = APIRouter(tags=["Trace"])


@router.websocket("/ws/runs/{run_id}")
async def run_websocket(run_id: UUID, websocket: WebSocket) -> None:
    await websocket_service.connect(run_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_service.disconnect(run_id, websocket)
