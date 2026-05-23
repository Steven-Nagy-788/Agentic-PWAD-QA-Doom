from __future__ import annotations

import base64
import hashlib
import subprocess
from pathlib import Path
from typing import Any

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
        self.frames_written = 0
        self.min_frames = max(int(round(self.fps * 2)), int(round(self.fps)))
        self._last_frame: np.ndarray | None = None
        self.width: int | None = None
        self.height: int | None = None
        self._unique_frame_hashes: set[str] = set()
        self._first_game_tick: int | None = None
        self._last_game_tick: int | None = None
        self._next_frame_game_tick: float | None = None
        self._needs_transcode = False
        self._transcode_errors: list[str] = []

    def start_from_frame(self, frame: np.ndarray) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        height, width = frame.shape[:2]
        self.width = int(width)
        self.height = int(height)
        fourcc = cv2.VideoWriter_fourcc(*"avc1")
        self.writer = cv2.VideoWriter(str(self.path), fourcc, self.fps, (width, height))
        self._needs_transcode = False
        if self.writer.isOpened():
            return
        self.writer.release()
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.writer = cv2.VideoWriter(str(self.source_path), fourcc, self.fps, (width, height))
        self._needs_transcode = True
        if not self.writer.isOpened():
            self._transcode_errors.append("opencv_video_writer_failed_to_open")
            self.writer = None

    def write_frame(self, frame: np.ndarray | None, game_tick: int | None = None) -> None:
        if frame is None:
            return
        tick = self.record_game_tick(game_tick)
        if tick is not None and self._skip_frame_for_game_tick(tick):
            return
        if self.writer is None:
            self.start_from_frame(frame)
        if self.writer is None:
            return
        self._last_frame = frame
        self._unique_frame_hashes.add(self._frame_hash(frame))
        self.writer.write(self._bgr(frame))
        self.frames_written += 1

    def record_game_tick(self, game_tick: int | None) -> int | None:
        if game_tick is None:
            return None
        try:
            tick = int(game_tick)
        except (TypeError, ValueError):
            return None
        if tick < 0:
            return None
        if self._first_game_tick is None:
            self._first_game_tick = tick
        self._last_game_tick = max(tick, self._last_game_tick if self._last_game_tick is not None else tick)
        return tick

    def save_screenshot(self, frame: np.ndarray, event_id: int) -> Path:
        path = self.settings.screenshot_storage_dir / f"{event_id}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(path), self._bgr(frame))
        return path

    def finalize(self) -> Path | None:
        if self.writer is not None:
            if self._should_pad_minimum_recording():
                for _ in range(self.min_frames - self.frames_written):
                    self.writer.write(self._bgr(self._last_frame))
                    self.frames_written += 1
            self.writer.release()
            self.writer = None
            if self._needs_transcode:
                return self._transcode_h264()
            if self._video_has_frames(self.path):
                return self.path
            self._transcode_errors.append("direct_avc1_output_has_no_decodable_frames")
            return self.path if self.path.exists() else None
        return None

    def metadata(self, path: Path | None = None, outcome: str | None = None) -> dict[str, Any]:
        output_path = path
        if output_path is None:
            if self.path.exists():
                output_path = self.path
            elif self.source_path.exists():
                output_path = self.source_path
        advanced_ticks = None
        if self._first_game_tick is not None and self._last_game_tick is not None:
            advanced_ticks = max(0, self._last_game_tick - self._first_game_tick)
        return {
            "timing_mode": "gameplay_time",
            "path": str(output_path) if output_path else None,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "frame_count": self.frames_written,
            "unique_frame_count": len(self._unique_frame_hashes),
            "duration_seconds": round(self.frames_written / self.fps, 3) if self.fps else 0,
            "first_game_tick": self._first_game_tick,
            "last_game_tick": self._last_game_tick,
            "advanced_game_ticks": advanced_ticks,
            "gameplay_seconds": round(advanced_ticks / 35, 3) if advanced_ticks is not None else None,
            "quality_status": "unknown",
            "validation_warnings": [],
            "outcome": outcome,
        }

    def validate(self, path: Path | None = None, outcome: str | None = None) -> dict[str, Any]:
        metadata = self.metadata(path=path, outcome=outcome)
        warnings: list[str] = []
        advanced_ticks = int(metadata.get("advanced_game_ticks") or 0)
        expected_frames = int((advanced_ticks / 35) * self.fps) if advanced_ticks > 0 else 0
        if outcome == "pwad_crash" and self.frames_written == 0:
            metadata["quality_status"] = "expected_missing"
            metadata["validation_warnings"] = ["No recording is expected because gameplay did not initialize."]
            return metadata
        if self.frames_written == 0:
            warnings.append("recording_has_no_frames")
        if self.width is not None and self.height is not None and (self.width < 640 or self.height < 480):
            warnings.append("recording_resolution_below_640x480")
        if advanced_ticks >= 35 and self.frames_written < max(10, int(expected_frames * 0.5)):
            warnings.append("recording_frame_count_low_for_game_ticks")
        if advanced_ticks >= 35 and self.frames_written > max(self.min_frames, int(expected_frames * 1.5) + 5):
            warnings.append("recording_frame_count_high_for_game_ticks")
        if self.frames_written >= 10 and len(self._unique_frame_hashes) < max(3, int(self.frames_written * 0.05)):
            warnings.append("recording_has_too_few_unique_frames")
        if (
            self.frames_written < self.min_frames
            and outcome not in {"pwad_crash", "cancelled"}
            and self._should_warn_short_recording(expected_frames)
        ):
            warnings.append("recording_shorter_than_minimum_frame_count")
        if path is not None and not self._video_has_frames(path):
            warnings.append("recording_file_has_no_decodable_frames")
        warnings.extend(self._transcode_errors)
        metadata["quality_status"] = "warning" if warnings else "ok"
        metadata["validation_warnings"] = warnings
        return metadata

    def _transcode_h264(self) -> Path:
        if not self.source_path.exists():
            return self.path if self.path.exists() else self.source_path

        try:
            completed = subprocess.run(
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
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                self._transcode_errors.append(_trim_ffmpeg_error(completed.stderr))
        except Exception:
            self._transcode_errors.append("ffmpeg_transcode_failed")
            return self.source_path

        if self.path.exists() and self.path.stat().st_size > 0 and self._video_has_frames(self.path):
            self.source_path.unlink(missing_ok=True)
            return self.path
        self._transcode_errors.append("ffmpeg_output_missing_or_invalid")
        return self.source_path

    @staticmethod
    def _bgr(frame: np.ndarray) -> np.ndarray:
        if frame.ndim == 3 and frame.shape[2] == 3:
            return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        return frame

    def _skip_frame_for_game_tick(self, tick: int) -> bool:
        if self.fps <= 0 or self.fps >= 35:
            return False
        interval = 35.0 / self.fps
        if self._next_frame_game_tick is None:
            self._next_frame_game_tick = tick + interval
            return False
        if tick + 1e-9 < self._next_frame_game_tick:
            return True
        while self._next_frame_game_tick <= tick + 1e-9:
            self._next_frame_game_tick += interval
        return False

    def _should_pad_minimum_recording(self) -> bool:
        if self._last_frame is None or self.frames_written <= 0 or self.frames_written >= self.min_frames:
            return False
        if self._first_game_tick is None or self._last_game_tick is None:
            return True
        advanced_ticks = max(0, self._last_game_tick - self._first_game_tick)
        expected_frames = int((advanced_ticks / 35) * self.fps) if advanced_ticks > 0 else 0
        return self.frames_written < max(10, int(expected_frames * 0.5))

    def _should_warn_short_recording(self, expected_frames: int) -> bool:
        if self._first_game_tick is None or self._last_game_tick is None:
            return True
        return self.frames_written < max(10, int(expected_frames * 0.5))

    @staticmethod
    def _frame_hash(frame: np.ndarray) -> str:
        if frame.size == 0:
            return "empty"
        small = cv2.resize(frame, (64, 48), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY) if small.ndim == 3 else small
        return hashlib.blake2b(gray.tobytes(), digest_size=12).hexdigest()

    @staticmethod
    def _video_has_frames(path: Path) -> bool:
        if not path.exists() or path.stat().st_size <= 0:
            return False
        capture = cv2.VideoCapture(str(path))
        try:
            if not capture.isOpened():
                return False
            ok, frame = capture.read()
            return bool(ok and frame is not None)
        finally:
            capture.release()


def _trim_ffmpeg_error(stderr: str | None) -> str:
    text = (stderr or "").strip()
    if not text:
        return "ffmpeg_transcode_failed_without_stderr"
    return "ffmpeg_transcode_failed: " + text[-1000:]


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
