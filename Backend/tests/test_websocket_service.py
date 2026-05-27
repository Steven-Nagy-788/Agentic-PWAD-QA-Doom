from __future__ import annotations

import contextlib
import json
from uuid import uuid4

import pytest

from app.services.websocket_service import WebSocketService


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.messages: list[dict] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, message: str) -> None:
        self.messages.append(json.loads(message))

    async def close(self, code: int = 1000) -> None:
        self.messages.append({"type": "closed", "code": code})


@pytest.mark.asyncio
async def test_websocket_replays_cached_live_messages_on_connect() -> None:
    service = WebSocketService()
    run_id = uuid4()

    await service.broadcast(run_id, {"type": "llm_decision", "sequence_number": 2, "mcp_tool": "explore"})
    await service.broadcast(run_id, {"type": "mcp_call_result", "sequence_number": 2, "mcp_stop_reason": "max_tics"})
    await service.broadcast(run_id, {"type": "state", "tick": 120, "health": 82})
    await service.broadcast(run_id, {"type": "progress", "tick": 120, "run_history": {"decisions": []}})
    await service.broadcast(run_id, {"type": "frame", "tick": 120, "frame_b64": "abc"})
    await service.broadcast(run_id, {"type": "defect", "fingerprint": "softlock:120", "title": "Softlock"})

    websocket = FakeWebSocket()
    await service.connect(run_id, websocket)  # type: ignore[arg-type]

    if service._ping_task is not None:
        service._ping_task.cancel()
        with contextlib.suppress(BaseException):
            await service._ping_task

    assert websocket.accepted is True
    types = [message["type"] for message in websocket.messages]
    assert types[0] == "replay_start"
    assert "llm_decision" in types
    assert "mcp_call_result" in types
    assert "defect" in types
    assert types.index("progress") < types.index("state") < types.index("frame")
    assert types[-1] == "replay_end"
