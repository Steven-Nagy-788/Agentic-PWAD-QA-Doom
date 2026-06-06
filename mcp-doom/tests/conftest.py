"""Shared test fixtures for mcp-doom tests."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest


def _build_minimal_pwad(lumps: list[tuple[str, bytes]]) -> bytes:
    """Build a minimal valid PWAD from a list of (name, data) pairs."""
    payload = bytearray()
    dir_entries: list[tuple[int, int, str]] = []
    for name, data in lumps:
        offset = 12 + len(payload)
        payload.extend(data)
        dir_entries.append((offset, len(data), name))
    directory_offset = 12 + len(payload)
    result = bytearray(struct.pack("<4sii", b"PWAD", len(dir_entries), directory_offset))
    result.extend(payload)
    for offset, size, name in dir_entries:
        result.extend(struct.pack("<ii8s", offset, size, name.encode("ascii")[:8].ljust(8, b"\0")))
    return bytes(result)


@pytest.fixture()
def test_wad_path(tmp_path: Path) -> str:
    """Create a minimal E1M1 WAD suitable for list_wad_maps tests."""
    things = struct.pack("<hhhhh", 0, 0, 0, 1, 0x0002)  # single player start
    lumps: list[tuple[str, bytes]] = [
        ("E1M1", b""),
        ("THINGS", things),
        ("LINEDEFS", b"\x00" * 14),
        ("SIDEDEFS", b"\x00" * 26),
        ("VERTEXES", b"\x00" * 8),
        ("SEGS", b"\x00" * 12),
        ("SSECTORS", b"\x00" * 4),
        ("NODES", b"\x00" * 28),
        ("SECTORS", b"\x00" * 26),
        ("REJECT", b"\x00"),
        ("BLOCKMAP", b"\x00" * 8),
    ]
    wad_path = tmp_path / "test_e1m1.wad"
    wad_path.write_bytes(_build_minimal_pwad(lumps))
    return str(wad_path)
