from __future__ import annotations

from pathlib import Path

import pytest

from app.core.path_security import resolve_path_within, unlink_if_within


def test_resolve_path_within_rejects_sibling_prefix(tmp_path: Path) -> None:
    allowed = tmp_path / "reports"
    sibling = tmp_path / "reports_evil"
    allowed.mkdir()
    sibling.mkdir()

    with pytest.raises(ValueError):
        resolve_path_within(sibling / "leak.pdf", allowed)


def test_unlink_if_within_only_deletes_allowed_files(tmp_path: Path) -> None:
    allowed = tmp_path / "recordings"
    outside = tmp_path / "recordings_old"
    allowed.mkdir()
    outside.mkdir()
    inside_file = allowed / "run.mp4"
    outside_file = outside / "run.mp4"
    inside_file.write_bytes(b"ok")
    outside_file.write_bytes(b"no")

    assert unlink_if_within(inside_file, allowed) is True
    assert unlink_if_within(outside_file, allowed) is False
    assert not inside_file.exists()
    assert outside_file.exists()
