from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from uuid import UUID

from fastapi import WebSocket


class WebSocketService:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._last_pong: dict[WebSocket, float] = {}
        self._ws_to_run: dict[WebSocket, str] = {}
        self._ping_task: asyncio.Task | None = None

    async def connect(self, run_id: UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        key = str(run_id)
        self._connections[key].add(websocket)
        self._last_pong[websocket] = time.monotonic()
        self._ws_to_run[websocket] = key
        self._ensure_ping_task()

    def disconnect(self, run_id: UUID, websocket: WebSocket) -> None:
        key = str(run_id)
        self._connections[key].discard(websocket)
        self._last_pong.pop(websocket, None)
        self._ws_to_run.pop(websocket, None)
        if not self._connections[key]:
            self._connections.pop(key, None)

    def handle_pong(self, websocket: WebSocket) -> None:
        self._last_pong[websocket] = time.monotonic()

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
            self._last_pong.pop(websocket, None)
            self._ws_to_run.pop(websocket, None)
            try:
                await asyncio.wait_for(websocket.close(code=1000), timeout=2.0)
            except Exception:
                pass

    def _ensure_ping_task(self) -> None:
        if self._ping_task is None or self._ping_task.done():
            self._ping_task = asyncio.create_task(self._ping_loop())

    async def _ping_loop(self) -> None:
        while True:
            await asyncio.sleep(30)
            now = time.monotonic()
            stale: list[WebSocket] = []
            for websocket, last_pong in list(self._last_pong.items()):
                try:
                    await asyncio.wait_for(
                        websocket.send_text(json.dumps({"type": "ping"})),
                        timeout=2.0,
                    )
                except Exception:
                    stale.append(websocket)
                    continue
                if now - last_pong > 60:
                    stale.append(websocket)
            for websocket in stale:
                run_id_str = self._ws_to_run.pop(websocket, None)
                self._last_pong.pop(websocket, None)
                if run_id_str:
                    self._connections[run_id_str].discard(websocket)
                    if not self._connections[run_id_str]:
                        self._connections.pop(run_id_str, None)
                try:
                    await asyncio.wait_for(websocket.close(code=1001), timeout=2.0)
                except Exception:
                    pass


websocket_service = WebSocketService()
