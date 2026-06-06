"""Shared test fixtures for Backend tests."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest


def _build_minimal_pwad(things_data: bytes) -> bytes:
    """Build a minimal valid PWAD with an E1M1 map containing the given THINGS."""
    lumps: list[tuple[str, bytes]] = [
        ("E1M1", b""),
        ("THINGS", things_data),
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


def _make_thing(x: int, y: int, thing_type: int, flags: int) -> bytes:
    """Pack a single Doom THINGS entry (10 bytes)."""
    return struct.pack("<hhhhh", x, y, 0, thing_type, flags)


@pytest.fixture()
def test_wad_path(tmp_path: Path) -> str:
    """Create a minimal E1M1 WAD with 8 enemies (medium-only skill flags).

    Enemies: 4 ZOMBIEMAN (3004), 2 IMP (3001), 2 SHOTGUN_GUY (9).
    All set with medium=True only (flags=0x0002) so they spawn at skill 3
    but not at skill 5.
    """
    things = bytearray()
    for i in range(4):
        things.extend(_make_thing(i * 64, 0, 3004, 0x0002))
    for i in range(2):
        things.extend(_make_thing(256 + i * 64, 0, 3001, 0x0002))
    for i in range(2):
        things.extend(_make_thing(384 + i * 64, 0, 9, 0x0002))
    wad_path = tmp_path / "test_e1m1.wad"
    wad_path.write_bytes(_build_minimal_pwad(bytes(things)))
    return str(wad_path)
