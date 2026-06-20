"""Tests for MCP client state normalization and tool validation."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.mcp_client_service import normalize_mcp_state
from app.services.run_loop import _validate_tool_request


TOOL_PARAM_ALLOWLIST = {
    "explore": {"max_tics", "stop_on_enemy", "stop_on_item", "ignore_object_ids", "turn_before"},
    "aim_and_shoot": {"object_id", "shots", "max_tics"},
    "strafe_and_shoot": {"object_id", "direction", "shots", "max_tics"},
    "move_to": {"object_id", "max_tics", "use", "stop_on_enemy"},
    "select_weapon": {"weapon_slot", "max_tics"},
    "retreat": {"tics", "backpedal"},
}

OBJECT_ID_TOOLS = {"aim_and_shoot", "strafe_and_shoot", "move_to"}


def test_normalize_state_plain_dict() -> None:
    state, screenshot = normalize_mcp_state({"game_variables": {"x": 1}})
    assert state == {"game_variables": {"x": 1}}
    assert screenshot is None


def test_normalize_state_list_of_dicts() -> None:
    items = [{"game_variables": {"x": 1}}, {"game_variables": {"y": 2}}]
    state, screenshot = normalize_mcp_state(items)
    assert state == {"game_variables": {"y": 2}}


def test_normalize_state_image_object() -> None:
    img = MagicMock()
    img.data = b"\x89PNG_DATA"
    img.mime_type = "image/png"
    img.content = None
    img.text = None
    img.structured_content = None
    state, screenshot = normalize_mcp_state([img])
    assert screenshot == b"\x89PNG_DATA"


def test_normalize_state_base64_image() -> None:
    import base64

    img = MagicMock()
    img.data = base64.b64encode(b"\x89PNG_DATA").decode()
    img.mime_type = "image/png"
    img.content = None
    img.text = None
    img.structured_content = None
    state, screenshot = normalize_mcp_state([img])
    assert screenshot == b"\x89PNG_DATA"


def test_normalize_state_nested_content() -> None:
    inner = MagicMock()
    inner.content = None
    inner.data = None
    inner.mime_type = ""
    inner.text = None
    inner.structured_content = {"game_variables": {"x": 5}}

    outer = MagicMock()
    outer.content = [inner]
    outer.data = None
    outer.mime_type = ""
    outer.text = None
    outer.structured_content = None

    state, screenshot = normalize_mcp_state([outer])
    assert state == {"game_variables": {"x": 5}}


def test_normalize_state_json_text() -> None:
    import json

    item = MagicMock()
    item.content = None
    item.data = None
    item.mime_type = ""
    item.text = json.dumps({"game_variables": {"x": 99}})
    item.structured_content = None
    del item.data

    state, screenshot = normalize_mcp_state([item])
    assert state == {"game_variables": {"x": 99}}


def test_normalize_state_empty_list() -> None:
    state, screenshot = normalize_mcp_state([])
    assert state == {}
    assert screenshot is None


def test_validate_tool_request_rejects_unsupported() -> None:
    error = _validate_tool_request("fly_to_moon", {}, {}, TOOL_PARAM_ALLOWLIST, OBJECT_ID_TOOLS)
    assert error is not None
    assert "Unsupported" in error


def test_validate_tool_request_rejects_empty_tool() -> None:
    error = _validate_tool_request("", {}, {}, TOOL_PARAM_ALLOWLIST, OBJECT_ID_TOOLS)
    assert error is not None
    assert "Unsupported" in error


def test_validate_tool_request_requires_object_id() -> None:
    error = _validate_tool_request("aim_and_shoot", {"shots": 3}, {"shots": 3}, TOOL_PARAM_ALLOWLIST, OBJECT_ID_TOOLS)
    assert error is not None
    assert "object_id" in error


def test_validate_tool_request_requires_weapon_slot() -> None:
    error = _validate_tool_request("select_weapon", {}, {}, TOOL_PARAM_ALLOWLIST, OBJECT_ID_TOOLS)
    assert error is not None
    assert "weapon_slot" in error


def test_validate_tool_request_accepts_valid_params() -> None:
    error = _validate_tool_request(
        "aim_and_shoot",
        {"object_id": 5, "shots": 3},
        {"object_id": 5, "shots": 3},
        TOOL_PARAM_ALLOWLIST,
        OBJECT_ID_TOOLS,
    )
    assert error is None


def test_validate_tool_request_accepts_take_action() -> None:
    error = _validate_tool_request(
        "take_action",
        {"actions": {"MOVE_FORWARD": 1}},
        {"actions": {"MOVE_FORWARD": 1}},
        TOOL_PARAM_ALLOWLIST,
        OBJECT_ID_TOOLS,
    )
    assert error is None


def test_validate_tool_request_rejects_empty_take_action() -> None:
    error = _validate_tool_request("take_action", {"actions": {}}, {"actions": {}}, TOOL_PARAM_ALLOWLIST, OBJECT_ID_TOOLS)
    assert error is not None
    assert "take_action" in error
