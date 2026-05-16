from __future__ import annotations

import base64
import subprocess
from pathlib import Path

import cv2
import numpy as np

from app.core.config import get_settings


class RecordingService:
    def __init__(self, run_id: str, fps: float = 2.0) -> None:
        self.settings = get_settings()
        self.run_id = run_id
        self.fps = fps
        self.path = self.settings.recording_storage_dir / f"{run_id}.mp4"
        self.source_path = self.settings.recording_storage_dir / f"{run_id}.source.mp4"
        self.writer: cv2.VideoWriter | None = None

    def start_from_frame(self, frame: np.ndarray) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        height, width = frame.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.writer = cv2.VideoWriter(str(self.source_path), fourcc, self.fps, (width, height))

    def write_frame(self, frame: np.ndarray | None) -> None:
        if frame is None:
            return
        if self.writer is None:
            self.start_from_frame(frame)
        assert self.writer is not None
        self.writer.write(self._bgr(frame))

    def save_screenshot(self, frame: np.ndarray, event_id: int) -> Path:
        path = self.settings.screenshot_storage_dir / f"{event_id}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(path), self._bgr(frame))
        return path

    def finalize(self) -> Path | None:
        if self.writer is not None:
            self.writer.release()
            self.writer = None
            return self._transcode_h264()
        return None

    def _transcode_h264(self) -> Path:
        if not self.source_path.exists():
            return self.path if self.path.exists() else self.source_path

        try:
            import ffmpeg

            (
                ffmpeg.input(str(self.source_path))
                .output(
                    str(self.path),
                    vcodec="libx264",
                    pix_fmt="yuv420p",
                    movflags="+faststart",
                    an=None,
                )
                .overwrite_output()
                .run(quiet=True)
            )
        except Exception:
            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(self.source_path),
                        "-c:v",
                        "libx264",
                        "-pix_fmt",
                        "yuv420p",
                        "-movflags",
                        "+faststart",
                        "-an",
                        str(self.path),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                return self.source_path

        if self.path.exists() and self.path.stat().st_size > 0:
            self.source_path.unlink(missing_ok=True)
            return self.path
        return self.source_path

    @staticmethod
    def _bgr(frame: np.ndarray) -> np.ndarray:
        if frame.ndim == 3 and frame.shape[2] == 3:
            return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        return frame


def png_bytes_to_frame(png_bytes: bytes | None) -> np.ndarray | None:
    if not png_bytes:
        return None
    arr = np.frombuffer(png_bytes, dtype=np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if bgr is None:
        return None
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def jpeg_b64(frame: np.ndarray, max_width: int = 480) -> str | None:
    if frame is None:
        return None
    height, width = frame.shape[:2]
    if width > max_width:
        scale = max_width / width
        frame = cv2.resize(frame, (max_width, int(height * scale)))
    bgr = RecordingService._bgr(frame)
    ok, encoded = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
    if not ok:
        return None
    return base64.b64encode(encoded.tobytes()).decode("ascii")
