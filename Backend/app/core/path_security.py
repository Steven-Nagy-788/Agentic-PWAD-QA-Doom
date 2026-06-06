from __future__ import annotations

from pathlib import Path


def resolve_path_within(path: str | Path, allowed_directory: str | Path) -> Path:
    """Resolve a path and require it to live inside an allowed directory."""
    resolved = Path(path).resolve()
    allowed = Path(allowed_directory).resolve()
    try:
        resolved.relative_to(allowed)
    except ValueError as exc:
        raise ValueError(f"Path is outside allowed directory: {resolved}") from exc
    return resolved


def unlink_if_within(path: str | Path | None, allowed_directory: str | Path) -> bool:
    if not path:
        return False
    try:
        resolved = resolve_path_within(path, allowed_directory)
    except ValueError:
        return False
    if not resolved.exists() or not resolved.is_file():
        return False
    resolved.unlink()
    return True
