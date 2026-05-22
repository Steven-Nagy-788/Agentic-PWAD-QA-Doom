from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from uuid import UUID

from fastapi import WebSocket


class WebSocketService:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, run_id: UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[str(run_id)].add(websocket)

    def disconnect(self, run_id: UUID, websocket: WebSocket) -> None:
        key = str(run_id)
        self._connections[key].discard(websocket)
        if not self._connections[key]:
            self._connections.pop(key, None)

    async def broadcast(self, run_id: UUID, payload: dict) -> None:
        key = str(run_id)
        connections = tuple(self._connections.get(key, set()))
        if not connections:
            self._connections.pop(key, None)
            return
        message = json.dumps(payload, default=str)
        dead = []
        for websocket in connections:
            try:
                await asyncio.wait_for(websocket.send_text(message), timeout=2.0)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(run_id, websocket)

    async def cleanup_run(self, run_id: UUID) -> None:
        connections = tuple(self._connections.pop(str(run_id), set()))
        for websocket in connections:
            try:
                await asyncio.wait_for(websocket.close(code=1000), timeout=2.0)
            except Exception:
                pass


websocket_service = WebSocketService()
