from __future__ import annotations

import numpy as np

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
