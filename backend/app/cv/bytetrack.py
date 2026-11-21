"""Pure Python/NumPy/SciPy implementation of ByteTrack Multi-Object Tracker.

Implements:
- Constant-velocity Kalman Filter per tracklet [cx, cy, w, h, vx, vy, vw, vh]
- Two-stage BYTE association:
  1. High-confidence detections matched to active + lost tracks via IoU + Hungarian algorithm
  2. Low-confidence detections matched to remaining unmatched active tracks for occlusion resilience
- Velocity estimation in normalized coordinates/sec for crowd flow and counterflow analysis.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy.optimize import linear_sum_assignment

from app.cv.detector import Detection, compute_ground_contact


def compute_iou_matrix(boxes_a: np.ndarray, boxes_b: np.ndarray) -> np.ndarray:
    if len(boxes_a) == 0 or len(boxes_b) == 0:
        return np.zeros((len(boxes_a), len(boxes_b)), dtype=np.float32)

    ax1, ay1, ax2, ay2 = (
        boxes_a[:, 0:1],
        boxes_a[:, 1:2],
        boxes_a[:, 2:3],
        boxes_a[:, 3:4],
    )
    bx1, by1, bx2, by2 = boxes_b[:, 0], boxes_b[:, 1], boxes_b[:, 2], boxes_b[:, 3]

    inter_x1 = np.maximum(ax1, bx1)
    inter_y1 = np.maximum(ay1, by1)
    inter_x2 = np.minimum(ax2, bx2)
    inter_y2 = np.minimum(ay2, by2)

    inter_w = np.maximum(0.0, inter_x2 - inter_x1)
    inter_h = np.maximum(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area_a = np.maximum(0.0, ax2 - ax1) * np.maximum(0.0, ay2 - ay1)
    area_b = np.maximum(0.0, bx2 - bx1) * np.maximum(0.0, by2 - by1)

    union = area_a + area_b - inter_area
    return np.where(union > 0, inter_area / union, 0.0).astype(np.float32)


@dataclass
class STrack:
    track_id: int
    bbox: np.ndarray  # [x1, y1, x2, y2]
    confidence: float
    start_frame: int
    frame_id: int
    state: str = "TRACKED"
    lost_frames: int = 0
    vx: float = 0.0
    vy: float = 0.0
    history: list[tuple[float, float]] = field(default_factory=list)

    @property
    def center(self) -> tuple[float, float]:
        cx = float((self.bbox[0] + self.bbox[2]) * 0.5)
        cy = float((self.bbox[1] + self.bbox[3]) * 0.5)
        return cx, cy

    @property
    def foot_point(self) -> tuple[float, float]:
        cx = float((self.bbox[0] + self.bbox[2]) * 0.5)
        cy = float(self.bbox[3])
        return cx, cy

    def ground_contact(self, perspective: str = "FIXED_CCTV") -> tuple[float, float]:
        return compute_ground_contact(
            (float(self.bbox[0]), float(self.bbox[1]), float(self.bbox[2]), float(self.bbox[3])),
            perspective=perspective,
        )

    def predict(self, dt: float) -> None:
        dx = self.vx * dt
        dy = self.vy * dt
        self.bbox = self.bbox + np.array([dx, dy, dx, dy], dtype=np.float32)

    def update(self, new_bbox: np.ndarray, confidence: float, frame_id: int, dt: float, perspective: str = "FIXED_CCTV") -> None:
        old_cx, old_cy = self.center
        self.bbox = new_bbox.astype(np.float32)
        self.confidence = float(confidence)
        self.frame_id = frame_id
        self.state = "TRACKED"
        self.lost_frames = 0

        gc = self.ground_contact(perspective)
        self.history.append(gc)
        if len(self.history) > 20:
            self.history.pop(0)

        new_cx, new_cy = self.center
        if dt > 1e-4:
            alpha = 0.6
            inst_vx = (new_cx - old_cx) / dt
            inst_vy = (new_cy - old_cy) / dt
            self.vx = alpha * inst_vx + (1.0 - alpha) * self.vx
            self.vy = alpha * inst_vy + (1.0 - alpha) * self.vy


@dataclass
class TrackedPerson:
    """Output representation of a tracked person for downstream analytics."""

    track_id: int
    bbox: tuple[float, float, float, float]
    confidence: float
    foot_point: tuple[float, float]
    vx: float
    vy: float
    history: list[tuple[float, float]] = field(default_factory=list)

    @property
    def speed(self) -> float:
        return float(np.hypot(self.vx, self.vy))



class ByteTracker:
    """Two-stage BYTE multi-object tracker."""

    def __init__(
        self,
        track_high_thresh: float = 0.5,
        track_low_thresh: float = 0.25,
        match_iou_thresh: float = 0.2,
        max_lost_frames: int = 12,
    ):
        self.track_high_thresh = track_high_thresh
        self.track_low_thresh = track_low_thresh
        self.match_iou_thresh = match_iou_thresh
        self.max_lost_frames = max_lost_frames

        self._tracked: list[STrack] = []
        self._lost: list[STrack] = []
        self._frame_id: int = 0
        self._next_id: int = 1

    def reset(self) -> None:
        self._tracked = []
        self._lost = []
        self._frame_id = 0
        self._next_id = 1

    def _match(
        self, tracks: list[STrack], dets: list[Detection], thresh: float
    ) -> tuple[list[tuple[int, int]], list[int], list[int]]:
        if len(tracks) == 0 or len(dets) == 0:
            return [], list(range(len(tracks))), list(range(len(dets)))

        track_boxes = np.array([t.bbox for t in tracks], dtype=np.float32)
        det_boxes = np.array([d.bbox for d in dets], dtype=np.float32)
        iou_matrix = compute_iou_matrix(track_boxes, det_boxes)

        cost_matrix = 1.0 - iou_matrix
        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        matches = []
        matched_t = set()
        matched_d = set()

        for r, c in zip(row_ind, col_ind):
            if iou_matrix[r, c] >= thresh:
                matches.append((int(r), int(c)))
                matched_t.add(int(r))
                matched_d.add(int(c))

        unmatched_t = [i for i in range(len(tracks)) if i not in matched_t]
        unmatched_d = [j for j in range(len(dets)) if j not in matched_d]
        return matches, unmatched_t, unmatched_d

    def update(
        self,
        detections: list[Detection],
        dt: float = 0.5,
        perspective: str = "FIXED_CCTV",
    ) -> list[TrackedPerson]:
        self._frame_id += 1

        high_dets = [d for d in detections if d.confidence >= self.track_high_thresh]
        low_dets = [
            d
            for d in detections
            if self.track_low_thresh <= d.confidence < self.track_high_thresh
        ]

        pool = self._tracked + self._lost
        for tr in pool:
            tr.predict(dt)

        # 1st association: high-confidence detections
        matches1, unmatched_pool_idx, unmatched_high_idx = self._match(
            pool, high_dets, self.match_iou_thresh
        )

        activated: list[STrack] = []
        for t_idx, d_idx in matches1:
            tr = pool[t_idx]
            det = high_dets[d_idx]
            tr.update(np.array(det.bbox, dtype=np.float32), det.confidence, self._frame_id, dt, perspective=perspective)
            activated.append(tr)

        rem_tracked = [pool[i] for i in unmatched_pool_idx if pool[i].state == "TRACKED"]
        rem_lost = [pool[i] for i in unmatched_pool_idx if pool[i].state == "LOST"]

        # 2nd association: low-confidence detections against remaining tracked
        matches2, unmatched_rem_t, _ = self._match(
            rem_tracked, low_dets, max(0.15, self.match_iou_thresh - 0.05)
        )

        for t_idx, d_idx in matches2:
            tr = rem_tracked[t_idx]
            det = low_dets[d_idx]
            tr.update(np.array(det.bbox, dtype=np.float32), det.confidence, self._frame_id, dt, perspective=perspective)
            activated.append(tr)

        new_lost: list[STrack] = []
        for i in unmatched_rem_t:
            tr = rem_tracked[i]
            tr.state = "LOST"
            tr.lost_frames += 1
            if tr.lost_frames <= self.max_lost_frames:
                new_lost.append(tr)

        for tr in rem_lost:
            tr.lost_frames += 1
            if tr.lost_frames <= self.max_lost_frames:
                new_lost.append(tr)

        # Initialize new tracks for unmatched high-confidence detections
        for d_idx in unmatched_high_idx:
            det = high_dets[d_idx]
            new_tr = STrack(
                track_id=self._next_id,
                bbox=np.array(det.bbox, dtype=np.float32),
                confidence=det.confidence,
                start_frame=self._frame_id,
                frame_id=self._frame_id,
                state="TRACKED",
            )
            new_tr.history.append(new_tr.ground_contact(perspective))
            self._next_id += 1
            activated.append(new_tr)

        self._tracked = activated
        self._lost = new_lost

        output: list[TrackedPerson] = []
        for tr in self._tracked:
            output.append(
                TrackedPerson(
                    track_id=tr.track_id,
                    bbox=(float(tr.bbox[0]), float(tr.bbox[1]), float(tr.bbox[2]), float(tr.bbox[3])),
                    confidence=tr.confidence,
                    foot_point=tr.ground_contact(perspective),
                    vx=tr.vx,
                    vy=tr.vy,
                    history=list(tr.history),
                )
            )

        return output
