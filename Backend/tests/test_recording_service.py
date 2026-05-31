from __future__ import annotations

import numpy as np
import subprocess

from app.services.recording_service import RecordingService


def test_recording_finalize_pads_single_frame_recordings(tmp_path, monkeypatch) -> None:
    recorder = RecordingService("test-run", fps=10)
    recorder.path = tmp_path / "test-run.mp4"
    recorder.source_path = tmp_path / "test-run.source.mp4"
    monkeypatch.setattr(RecordingService, "_transcode_h264", lambda self: self.source_path)

    frame = np.zeros((16, 16, 3), dtype=np.uint8)
    recorder.write_frame(frame)
    path = recorder.finalize()

    assert path == recorder.source_path
    assert recorder.frames_written >= recorder.min_frames


def test_recording_metadata_uses_game_ticks_and_unique_frames(tmp_path, monkeypatch) -> None:
    recorder = RecordingService("metadata-run", fps=15)
    recorder.path = tmp_path / "metadata-run.mp4"
    recorder.source_path = tmp_path / "metadata-run.source.mp4"
    monkeypatch.setattr(RecordingService, "_transcode_h264", lambda self: self.source_path)

    first = np.zeros((480, 640, 3), dtype=np.uint8)
    middle = np.full((480, 640, 3), 127, dtype=np.uint8)
    second = np.full((480, 640, 3), 255, dtype=np.uint8)
    recorder.write_frame(first, game_tick=100)
    recorder.write_frame(middle, game_tick=118)
    recorder.write_frame(second, game_tick=135)
    path = recorder.finalize()

    metadata = recorder.validate(path, outcome="stuck")

    assert metadata["timing_mode"] == "gameplay_time"
    assert metadata["width"] == 640
    assert metadata["height"] == 480
    assert metadata["fps"] == 15
    assert metadata["first_game_tick"] == 100
    assert metadata["last_game_tick"] == 135
    assert metadata["advanced_game_ticks"] == 35
    assert metadata["gameplay_seconds"] == 1.0
    assert metadata["frame_count"] >= recorder.min_frames
    assert metadata["unique_frame_count"] == 3
    assert metadata["quality_status"] == "ok"


def test_recording_samples_telemetry_to_target_gameplay_fps(tmp_path, monkeypatch) -> None:
    recorder = RecordingService("sampled-run", fps=15)
    recorder.path = tmp_path / "sampled-run.mp4"
    recorder.source_path = tmp_path / "sampled-run.source.mp4"
    monkeypatch.setattr(RecordingService, "_transcode_h264", lambda self: self.source_path)

    for tick in range(36):
        frame = np.full((480, 640, 3), tick, dtype=np.uint8)
        recorder.write_frame(frame, game_tick=tick)
    path = recorder.finalize()

    metadata = recorder.validate(path, outcome="stuck")

    assert 14 <= metadata["frame_count"] <= 16
    assert metadata["advanced_game_ticks"] == 35
    assert metadata["quality_status"] == "ok"


def test_crash_recording_metadata_is_expected_missing() -> None:
    recorder = RecordingService("crash-run", fps=15)

    metadata = recorder.validate(None, outcome="pwad_crash")

    assert metadata["quality_status"] == "expected_missing"
    assert metadata["frame_count"] == 0
    assert metadata["path"] is None
    assert "No recording is expected" in metadata["validation_warnings"][0]


def test_ffmpeg_timeout_retains_source_recording(tmp_path, monkeypatch) -> None:
    recorder = RecordingService("timeout-run", fps=15)
    recorder.path = tmp_path / "timeout-run.mp4"
    recorder.source_path = tmp_path / "timeout-run.source.mp4"
    recorder.source_path.write_bytes(b"source")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("ffmpeg", 60)),
    )

    path = recorder._transcode_h264()

    assert path == recorder.source_path
    assert recorder.source_path.exists()
    assert "ffmpeg_transcode_timed_out" in recorder._transcode_errors
