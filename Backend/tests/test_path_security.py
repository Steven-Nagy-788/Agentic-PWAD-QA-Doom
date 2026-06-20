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


def test_resolve_path_within_accepts_valid_path(tmp_path: Path) -> None:
    allowed = tmp_path / "reports"
    allowed.mkdir()
    valid = allowed / "report.pdf"
    valid.write_bytes(b"ok")

    result = resolve_path_within(valid, allowed)
    assert result == valid.resolve()


def test_resolve_path_within_accepts_nested_path(tmp_path: Path) -> None:
    allowed = tmp_path / "reports"
    nested = allowed / "2026" / "06"
    nested.mkdir(parents=True)
    valid = nested / "report.pdf"

    result = resolve_path_within(valid, allowed)
    assert result == valid.resolve()


def test_resolve_path_within_rejects_dot_dot_traversal(tmp_path: Path) -> None:
    allowed = tmp_path / "reports"
    allowed.mkdir()
    outside = tmp_path / "other"
    outside.mkdir()

    with pytest.raises(ValueError):
        resolve_path_within(allowed / ".." / "other" / "secret.txt", allowed)


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


def test_unlink_if_within_returns_false_for_none_path(tmp_path: Path) -> None:
    allowed = tmp_path / "reports"
    allowed.mkdir()
    assert unlink_if_within(None, allowed) is False


def test_unlink_if_within_returns_false_for_nonexistent_file(tmp_path: Path) -> None:
    allowed = tmp_path / "reports"
    allowed.mkdir()
    assert unlink_if_within(allowed / "missing.pdf", allowed) is False


def test_unlink_if_within_returns_false_for_directory(tmp_path: Path) -> None:
    allowed = tmp_path / "reports"
    allowed.mkdir()
    subdir = allowed / "subdir"
    subdir.mkdir()
    assert unlink_if_within(subdir, allowed) is False
