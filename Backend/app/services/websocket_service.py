from __future__ import annotations

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
        self._connections[str(run_id)].discard(websocket)

    async def broadcast(self, run_id: UUID, payload: dict) -> None:
        dead = []
        for websocket in self._connections.get(str(run_id), set()):
            try:
                await websocket.send_text(json.dumps(payload, default=str))
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(run_id, websocket)


websocket_service = WebSocketService()
