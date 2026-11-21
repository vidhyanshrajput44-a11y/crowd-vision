"""Camera motion estimation and homography stabilization for moving and drifting cameras."""
from __future__ import annotations

from typing import Any, Optional

import cv2
import numpy as np


class CameraMotionCompensator:
    """Estimates and accumulates inter-frame camera motion for moving or drifting cameras."""

    def __init__(
        self,
        max_features: int = 200,
        quality_level: float = 0.01,
        min_distance: float = 15.0,
    ):
        self.max_features = max_features
        self.quality_level = quality_level
        self.min_distance = min_distance
        self._prev_gray: Optional[np.ndarray] = None
        self._accumulated_transform: np.ndarray = np.eye(3, dtype=np.float32)

    def reset(self) -> None:
        self._prev_gray = None
        self._accumulated_transform = np.eye(3, dtype=np.float32)

    def update(self, frame_bgr: np.ndarray) -> tuple[np.ndarray, dict[str, float]]:
        if frame_bgr is None or frame_bgr.size == 0:
            return self._accumulated_transform.copy(), {
                "dx": 0.0,
                "dy": 0.0,
                "rotation_deg": 0.0,
                "scale": 1.0,
            }

        curr_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

        if self._prev_gray is None:
            self._prev_gray = curr_gray
            return self._accumulated_transform.copy(), {
                "dx": 0.0,
                "dy": 0.0,
                "rotation_deg": 0.0,
                "scale": 1.0,
            }

        p0 = cv2.goodFeaturesToTrack(
            self._prev_gray,
            maxCorners=self.max_features,
            qualityLevel=self.quality_level,
            minDistance=self.min_distance,
        )

        motion_metrics = {"dx": 0.0, "dy": 0.0, "rotation_deg": 0.0, "scale": 1.0}

        if p0 is not None and len(p0) >= 10:
            p1, st, err = cv2.calcOpticalFlowPyrLK(
                self._prev_gray, curr_gray, p0, None, winSize=(21, 21), maxLevel=3
            )
            good_p0 = p0[st == 1]
            good_p1 = p1[st == 1]

            if len(good_p0) >= 8:
                transform_matrix, inliers = cv2.estimateAffinePartial2D(
                    good_p0, good_p1, method=cv2.RANSAC, ransacReprojThreshold=3.0
                )
                if transform_matrix is not None:
                    dx = float(transform_matrix[0, 2])
                    dy = float(transform_matrix[1, 2])
                    da = float(np.arctan2(transform_matrix[1, 0], transform_matrix[0, 0]))
                    scale = float(
                        np.sqrt(
                            transform_matrix[0, 0] ** 2 + transform_matrix[1, 0] ** 2
                        )
                    )

                    motion_metrics = {
                        "dx": round(dx, 2),
                        "dy": round(dy, 2),
                        "rotation_deg": round(float(np.degrees(da)), 2),
                        "scale": round(scale, 4),
                    }

                    affine_3x3 = np.eye(3, dtype=np.float32)
                    affine_3x3[:2, :] = transform_matrix
                    self._accumulated_transform = (
                        self._accumulated_transform @ affine_3x3
                    )

        self._prev_gray = curr_gray
        return self._accumulated_transform.copy(), motion_metrics

    def stabilize_point(
        self, px: float, py: float, frame_w: int, frame_h: int
    ) -> tuple[float, float]:
        pt = np.array([px, py, 1.0], dtype=np.float32)
        try:
            inv = np.linalg.inv(self._accumulated_transform)
            stab_pt = inv @ pt
            sx = float(np.clip(stab_pt[0] / max(float(frame_w), 1.0), 0.0, 1.0))
            sy = float(np.clip(stab_pt[1] / max(float(frame_h), 1.0), 0.0, 1.0))
            return sx, sy
        except Exception:
            return float(px / max(float(frame_w), 1.0)), float(
                py / max(float(frame_h), 1.0)
            )
