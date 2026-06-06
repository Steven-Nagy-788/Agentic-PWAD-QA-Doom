from __future__ import annotations

import re
import struct
import sys
from pathlib import Path


MAP_MARKER_RE = re.compile(r"^(MAP\d\d|E\dM\d)$")


def _resolve_wad(value: str) -> Path:
    if value.lower() in {"freedoom1", "freedoom2"}:
        import vizdoom as vzd

        return Path(vzd.__file__).with_name(f"{value.lower()}.wad")
    return Path(value).expanduser().resolve()


def _read_directory(data: bytes) -> list[tuple[str, int, int]]:
    magic, lump_count, directory_offset = struct.unpack_from("<4sii", data, 0)
    if magic not in {b"IWAD", b"PWAD"}:
        raise ValueError("Input is not a Doom WAD")
    directory: list[tuple[str, int, int]] = []
    for index in range(lump_count):
        offset, size, raw_name = struct.unpack_from("<ii8s", data, directory_offset + index * 16)
        name = raw_name.rstrip(b"\0").decode("ascii", errors="ignore").upper()
        directory.append((name, offset, size))
    return directory


def extract_map(base_wad: Path, map_name: str, output: Path) -> None:
    data = base_wad.read_bytes()
    directory = _read_directory(data)
    target = map_name.upper()
    start_index = next((idx for idx, (name, _, _) in enumerate(directory) if name == target), None)
    if start_index is None:
        raise ValueError(f"Map {target} was not found in {base_wad}")
    end_index = len(directory)
    for idx in range(start_index + 1, len(directory)):
        if MAP_MARKER_RE.match(directory[idx][0]):
            end_index = idx
            break
    map_entries = directory[start_index:end_index]
    lumps: list[tuple[str, bytes]] = []
    for name, offset, size in map_entries:
        lumps.append((name, data[offset : offset + size]))

    payload = bytearray()
    out_directory: list[tuple[int, int, str]] = []
    for name, lump_data in lumps:
        offset = 12 + len(payload)
        payload.extend(lump_data)
        out_directory.append((offset, len(lump_data), name))

    directory_offset = 12 + len(payload)
    result = bytearray()
    result.extend(struct.pack("<4sii", b"PWAD", len(out_directory), directory_offset))
    result.extend(payload)
    for offset, size, name in out_directory:
        result.extend(struct.pack("<ii8s", offset, size, name.encode("ascii")[:8].ljust(8, b"\0")))

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result)


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print("usage: extract_iwad_map.py <freedoom1|freedoom2|base.wad> <MAP01|E1M1> <output.wad>", file=sys.stderr)
        return 2
    extract_map(_resolve_wad(argv[1]), argv[2], Path(argv[3]).expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
