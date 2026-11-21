"""Video Source Abstraction Engine for CROWD VISION.

Provides unified interface and concrete implementations for:
- Uploaded recorded video files (MP4, AVI, MOV, MKV, WebM)
- CCTV and Drone recordings
- RTSP, HLS, and HTTP network camera streams
- Local camera devices / USB webcams
- Handles frame extraction, timestamping, stream health, reconnection, and error recovery.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import time
from typing import Any, Optional

import cv2
import numpy as np

from app.core.logging import get_logger

logger = get_logger("cv.video_source")


class VideoSourceType(str, Enum):
    FILE = "FILE"
    CCTV_RECORDING = "CCTV_RECORDING"
    DRONE_RECORDING = "DRONE_RECORDING"
    RTSP_STREAM = "RTSP_STREAM"
    HLS_STREAM = "HLS_STREAM"
    HTTP_STREAM = "HTTP_STREAM"
    WEBCAM = "WEBCAM"
    DEVICE = "DEVICE"


class SourceState(str, Enum):
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    STREAMING = "STREAMING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    DISCONNECTED = "DISCONNECTED"


@dataclass
class SourceMetadata:
    """Metadata describing the characteristics of an ingested video source."""

    source_type: VideoSourceType
    is_live: bool
    width: int
    height: int
    fps: float
    total_frames: Optional[int] = None
    duration_seconds: Optional[float] = None
    source_identifier: str = ""
    codec: str = ""


@dataclass
class VideoFrame:
    """Decoded video frame and associated telemetry."""

    frame_index: int
    timestamp_sec: float
    frame: np.ndarray
    is_live: bool = False
    source_type: str = "FILE"


class BaseVideoSource(ABC):
    """Abstract Base Class for all video source providers."""

    def __init__(self, source_identifier: str, source_type: VideoSourceType):
        self.source_identifier = source_identifier
        self.source_type = source_type
        self.state: SourceState = SourceState.INITIALIZING
        self._metadata: Optional[SourceMetadata] = None
        self._frame_count: int = 0
        self._start_wall_time: float = 0.0
        self._last_frame_time: float = 0.0

    @abstractmethod
    def open(self) -> bool:
        """Initialize and open the video stream or file."""
        raise NotImplementedError

    @abstractmethod
    def read_frame(self) -> Optional[VideoFrame]:
        """Acquire and decode the next frame from the stream."""
        raise NotImplementedError

    @abstractmethod
    def seek(self, timestamp_sec: float) -> bool:
        """Seek to a specific timecode (for recorded media only)."""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Release underlying system resources and descriptors."""
        raise NotImplementedError

    def pause(self) -> None:
        if self.state in (SourceState.STREAMING, SourceState.READY):
            self.state = SourceState.PAUSED
            logger.info("Video source paused", source=self.source_identifier)

    def resume(self) -> None:
        if self.state == SourceState.PAUSED:
            self.state = SourceState.STREAMING
            logger.info("Video source resumed", source=self.source_identifier)

    @property
    def metadata(self) -> Optional[SourceMetadata]:
        return self._metadata

    @property
    def is_live(self) -> bool:
        return self.source_type in (
            VideoSourceType.RTSP_STREAM,
            VideoSourceType.HLS_STREAM,
            VideoSourceType.HTTP_STREAM,
            VideoSourceType.WEBCAM,
            VideoSourceType.DEVICE,
        )

    def get_health_status(self) -> dict[str, Any]:
        return {
            "source_identifier": self.source_identifier,
            "source_type": self.source_type.value,
            "state": self.state.value,
            "is_live": self.is_live,
            "frames_extracted": self._frame_count,
            "last_frame_elapsed_sec": round(time.time() - self._last_frame_time, 2)
            if self._last_frame_time > 0
            else None,
        }


class FileVideoSource(BaseVideoSource):
    """Video source for local recorded files (CCTV, drone, uploaded media)."""

    def __init__(
        self,
        file_path: str | Path,
        source_type: VideoSourceType = VideoSourceType.FILE,
    ):
        super().__init__(str(file_path), source_type)
        self.file_path = Path(file_path)
        self._cap: Optional[cv2.VideoCapture] = None

    def open(self) -> bool:
        if not self.file_path.exists():
            self.state = SourceState.FAILED
            logger.error("Video file does not exist", path=str(self.file_path))
            return False

        self._cap = cv2.VideoCapture(str(self.file_path))
        if not self._cap.isOpened():
            self.state = SourceState.FAILED
            logger.error("OpenCV failed to open video file", path=str(self.file_path))
            return False

        fps = float(self._cap.get(cv2.CAP_PROP_FPS) or 25.0)
        total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        duration = float(total_frames) / fps if fps > 0 else 0.0

        fourcc_int = int(self._cap.get(cv2.CAP_PROP_FOURCC) or 0)
        codec = "".join([chr((fourcc_int >> 8 * i) & 0xFF) for i in range(4)])

        self._metadata = SourceMetadata(
            source_type=self.source_type,
            is_live=False,
            width=width,
            height=height,
            fps=fps,
            total_frames=total_frames,
            duration_seconds=round(duration, 3),
            source_identifier=str(self.file_path.name),
            codec=codec,
        )
        self.state = SourceState.READY
        self._start_wall_time = time.time()
        logger.info(
            "File video source opened successfully",
            path=str(self.file_path),
            width=width,
            height=height,
            fps=fps,
            total_frames=total_frames,
            duration_s=round(duration, 2),
        )
        return True

    def read_frame(self) -> Optional[VideoFrame]:
        if self._cap is None or not self._cap.isOpened():
            return None
        if self.state == SourceState.PAUSED:
            return None

        ret, frame = self._cap.read()
        if not ret or frame is None:
            self.state = SourceState.STOPPED
            return None

        self.state = SourceState.STREAMING
        fps = self._metadata.fps if self._metadata and self._metadata.fps > 0 else 25.0
        v_ts = float(self._frame_count) / fps

        vf = VideoFrame(
            frame_index=self._frame_count,
            timestamp_sec=round(v_ts, 3),
            frame=frame,
            is_live=False,
            source_type=self.source_type.value,
        )
        self._frame_count += 1
        self._last_frame_time = time.time()
        return vf

    def seek(self, timestamp_sec: float) -> bool:
        if self._cap is None or not self._cap.isOpened():
            return False
        fps = self._metadata.fps if self._metadata else 25.0
        target_frame = max(0, int(round(timestamp_sec * fps)))
        res = self._cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        if res:
            self._frame_count = target_frame
        return bool(res)

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self.state = SourceState.STOPPED
        logger.info("File video source closed", file=str(self.file_path))


class NetworkStreamVideoSource(BaseVideoSource):
    """Video source for live RTSP / HLS / HTTP camera streams."""

    def __init__(
        self,
        stream_url: str,
        source_type: VideoSourceType = VideoSourceType.RTSP_STREAM,
        reconnect_attempts: int = 5,
        reconnect_delay_sec: float = 2.0,
    ):
        super().__init__(stream_url, source_type)
        self.stream_url = stream_url
        self.reconnect_attempts = reconnect_attempts
        self.reconnect_delay_sec = reconnect_delay_sec
        self._cap: Optional[cv2.VideoCapture] = None
        self._reconnect_count: int = 0
        self._first_frame_wall_time: Optional[float] = None

    def open(self) -> bool:
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|timeout;5000000"
        self._cap = cv2.VideoCapture(self.stream_url, cv2.CAP_FFMPEG)
        if not self._cap.isOpened():
            self.state = SourceState.DISCONNECTED
            logger.warning("Could not establish connection to stream", url=self.stream_url)
            return False

        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920)
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1080)
        fps = float(self._cap.get(cv2.CAP_PROP_FPS) or 25.0)
        if fps <= 0 or fps > 120:
            fps = 25.0

        self._metadata = SourceMetadata(
            source_type=self.source_type,
            is_live=True,
            width=width,
            height=height,
            fps=fps,
            total_frames=None,
            duration_seconds=None,
            source_identifier=self.stream_url,
        )
        self.state = SourceState.READY
        self._first_frame_wall_time = None
        logger.info("Network stream opened successfully", url=self.stream_url, resolution=f"{width}x{height}")
        return True

    def read_frame(self) -> Optional[VideoFrame]:
        if self._cap is None or not self._cap.isOpened():
            if not self._attempt_reconnect():
                return None

        if self.state == SourceState.PAUSED:
            return None

        ret, frame = self._cap.read()
        if not ret or frame is None:
            logger.warning("Failed to read frame from stream, attempting reconnect", url=self.stream_url)
            self.state = SourceState.DISCONNECTED
            if self._attempt_reconnect():
                ret, frame = self._cap.read()
                if not ret or frame is None:
                    return None
            else:
                return None

        now = time.time()
        if self._first_frame_wall_time is None:
            self._first_frame_wall_time = now

        timestamp_sec = round(now - self._first_frame_wall_time, 3)
        self.state = SourceState.STREAMING

        vf = VideoFrame(
            frame_index=self._frame_count,
            timestamp_sec=timestamp_sec,
            frame=frame,
            is_live=True,
            source_type=self.source_type.value,
        )
        self._frame_count += 1
        self._last_frame_time = now
        self._reconnect_count = 0
        return vf

    def _attempt_reconnect(self) -> bool:
        self.state = SourceState.DISCONNECTED
        while self._reconnect_count < self.reconnect_attempts:
            self._reconnect_count += 1
            logger.info("Reconnecting to stream", attempt=self._reconnect_count, max_attempts=self.reconnect_attempts)
            if self._cap is not None:
                self._cap.release()
            time.sleep(self.reconnect_delay_sec)
            self._cap = cv2.VideoCapture(self.stream_url, cv2.CAP_FFMPEG)
            if self._cap.isOpened():
                self.state = SourceState.STREAMING
                logger.info("Stream reconnection successful", url=self.stream_url)
                return True

        self.state = SourceState.FAILED
        logger.error("Stream reconnection failed after max attempts", url=self.stream_url)
        return False

    def seek(self, timestamp_sec: float) -> bool:
        # Seeking is not supported on live streams
        return False

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self.state = SourceState.STOPPED
        logger.info("Network stream closed", url=self.stream_url)


class CameraDeviceVideoSource(BaseVideoSource):
    """Video source for local hardware camera devices (USB webcam, onboard camera)."""

    def __init__(
        self,
        device_index: int = 0,
        source_type: VideoSourceType = VideoSourceType.WEBCAM,
    ):
        super().__init__(f"camera_device_{device_index}", source_type)
        self.device_index = device_index
        self._cap: Optional[cv2.VideoCapture] = None
        self._first_frame_wall_time: Optional[float] = None

    def open(self) -> bool:
        self._cap = cv2.VideoCapture(self.device_index)
        if not self._cap.isOpened():
            self.state = SourceState.FAILED
            logger.error("Could not open camera device", device_index=self.device_index)
            return False

        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)
        fps = float(self._cap.get(cv2.CAP_PROP_FPS) or 30.0)
        if fps <= 0 or fps > 120:
            fps = 30.0

        self._metadata = SourceMetadata(
            source_type=self.source_type,
            is_live=True,
            width=width,
            height=height,
            fps=fps,
            total_frames=None,
            duration_seconds=None,
            source_identifier=f"Device #{self.device_index}",
        )
        self.state = SourceState.READY
        self._first_frame_wall_time = None
        logger.info("Camera device opened successfully", device_index=self.device_index, res=f"{width}x{height}")
        return True

    def read_frame(self) -> Optional[VideoFrame]:
        if self._cap is None or not self._cap.isOpened():
            return None
        if self.state == SourceState.PAUSED:
            return None

        ret, frame = self._cap.read()
        if not ret or frame is None:
            self.state = SourceState.FAILED
            return None

        now = time.time()
        if self._first_frame_wall_time is None:
            self._first_frame_wall_time = now

        timestamp_sec = round(now - self._first_frame_wall_time, 3)
        self.state = SourceState.STREAMING

        vf = VideoFrame(
            frame_index=self._frame_count,
            timestamp_sec=timestamp_sec,
            frame=frame,
            is_live=True,
            source_type=self.source_type.value,
        )
        self._frame_count += 1
        self._last_frame_time = now
        return vf

    def seek(self, timestamp_sec: float) -> bool:
        return False

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self.state = SourceState.STOPPED
        logger.info("Camera device closed", device_index=self.device_index)


def create_video_source(
    config: dict[str, Any] | str,
    base_dir: Optional[Path] = None,
) -> BaseVideoSource:
    """Factory function to instantiate the appropriate BaseVideoSource based on configuration."""
    if isinstance(config, str):
        path_or_url = config.strip()
        if path_or_url.startswith(("rtsp://", "rtsps://")):
            return NetworkStreamVideoSource(path_or_url, VideoSourceType.RTSP_STREAM)
        elif path_or_url.startswith(("http://", "https://")) and (
            path_or_url.endswith(".m3u8") or "hls" in path_or_url.lower()
        ):
            return NetworkStreamVideoSource(path_or_url, VideoSourceType.HLS_STREAM)
        elif path_or_url.startswith(("http://", "https://")):
            return NetworkStreamVideoSource(path_or_url, VideoSourceType.HTTP_STREAM)
        elif path_or_url.isdigit():
            return CameraDeviceVideoSource(int(path_or_url), VideoSourceType.WEBCAM)
        else:
            p = Path(path_or_url)
            if not p.is_absolute() and base_dir:
                p = base_dir / p
            return FileVideoSource(p, VideoSourceType.FILE)

    source_type_raw = str(config.get("source_type", "FILE")).upper()
    uri = str(config.get("source_uri") or config.get("uri") or config.get("stored_path") or config.get("filename") or "")

    if source_type_raw in ("RTSP_STREAM", "RTSP") or uri.startswith(("rtsp://", "rtsps://")):
        return NetworkStreamVideoSource(uri, VideoSourceType.RTSP_STREAM)
    elif source_type_raw in ("HLS_STREAM", "HLS") or uri.endswith(".m3u8"):
        return NetworkStreamVideoSource(uri, VideoSourceType.HLS_STREAM)
    elif source_type_raw in ("HTTP_STREAM", "HTTP"):
        return NetworkStreamVideoSource(uri, VideoSourceType.HTTP_STREAM)
    elif source_type_raw in ("WEBCAM", "USB_CAMERA", "DEVICE"):
        dev_idx = int(config.get("device_index", 0))
        return CameraDeviceVideoSource(dev_idx, VideoSourceType.WEBCAM)
    elif source_type_raw == "DRONE_RECORDING":
        p = Path(uri)
        if not p.is_absolute() and base_dir:
            p = base_dir / p
        return FileVideoSource(p, VideoSourceType.DRONE_RECORDING)
    elif source_type_raw == "CCTV_RECORDING":
        p = Path(uri)
        if not p.is_absolute() and base_dir:
            p = base_dir / p
        return FileVideoSource(p, VideoSourceType.CCTV_RECORDING)
    else:
        p = Path(uri)
        if not p.is_absolute() and base_dir:
            p = base_dir / p
        return FileVideoSource(p, VideoSourceType.FILE)
