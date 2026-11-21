"""Person detector wrapping YOLO / ONNX / OpenCV fallback with ground contact point and perspective assessment."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import time
from typing import Any, Optional

import cv2
import numpy as np

from app.core.logging import get_logger

logger = get_logger("cv.detector")


@dataclass
class Detection:
    """Single person detection in pixel coordinates [x1, y1, x2, y2]."""

    bbox: tuple[float, float, float, float]
    confidence: float
    class_id: int = 0


def compute_ground_contact(
    bbox: tuple[float, float, float, float], perspective: str = "FIXED_CCTV"
) -> tuple[float, float]:
    """Computes the ground contact point for a person bounding box.

    For DRONE_TOPDOWN: uses the geometric center of the bbox.
    For FIXED_CCTV / ELEVATED_OBLIQUE: uses the bottom-center ground contact point.
    """
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) * 0.5
    if perspective.upper() == "DRONE_TOPDOWN":
        cy = (y1 + y2) * 0.5
    else:
        cy = float(y2)
    return float(cx), float(cy)


def assess_footage_perspective(frame: np.ndarray) -> dict[str, Any]:
    """Analyzes vanishing points and line orientations to determine camera perspective."""
    if frame is None or frame.size == 0:
        return {
            "perspective": "FIXED_CCTV",
            "confidence": 0.5,
            "vanishing_points_found": 0,
            "recommended_perspective": "FIXED_CCTV",
            "explanation": "Empty or invalid frame; defaulting to FIXED_CCTV",
        }

    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=80, minLineLength=40, maxLineGap=10
    )

    if lines is None or len(lines) < 6:
        return {
            "perspective": "FIXED_CCTV",
            "confidence": 0.65,
            "vanishing_points_found": 0,
            "recommended_perspective": "FIXED_CCTV",
            "explanation": "Sparse edge features; default fixed camera perspective selected",
        }

    slanted_lines = []
    horizontal_lines = []
    vertical_lines = []

    for line in lines:
        pts = line.reshape(-1)
        if len(pts) < 4:
            continue
        x1, y1, x2, y2 = int(pts[0]), int(pts[1]), int(pts[2]), int(pts[3])
        dx = x2 - x1
        dy = y2 - y1
        angle = np.degrees(np.arctan2(dy, dx)) % 180
        if 15 <= angle <= 75 or 105 <= angle <= 165:
            slanted_lines.append((x1, y1, x2, y2))
        elif angle < 15 or angle > 165:
            horizontal_lines.append((x1, y1, x2, y2))
        else:
            vertical_lines.append((x1, y1, x2, y2))

    total_lines = len(lines)
    slanted_ratio = len(slanted_lines) / max(total_lines, 1)

    # Vanishing points estimation
    intersections = []
    sample_count = min(len(slanted_lines), 30)
    for i in range(sample_count):
        x1, y1, x2, y2 = slanted_lines[i]
        line1 = np.cross([x1, y1, 1], [x2, y2, 1])
        for j in range(i + 1, min(sample_count, i + 10)):
            x3, y3, x4, y4 = slanted_lines[j]
            line2 = np.cross([x3, y3, 1], [x4, y4, 1])
            pt = np.cross(line1, line2)
            if abs(pt[2]) > 1e-5:
                ix = pt[0] / pt[2]
                iy = pt[1] / pt[2]
                if -2 * w <= ix <= 3 * w and -2 * h <= iy <= 3 * h:
                    intersections.append((ix, iy))

    vp_clusters = 0
    if len(intersections) >= 6:
        pts = np.array(intersections, dtype=np.float32)
        hist, _, _ = np.histogram2d(pts[:, 0], pts[:, 1], bins=(6, 6))
        if hist.max() >= 3:
            vp_clusters = int((hist >= 3).sum())

    if slanted_ratio < 0.2 and vp_clusters == 0:
        perspective = "DRONE_TOPDOWN"
        conf = 0.82
        explanation = (
            "Predominance of orthogonal lines with absence of converging vanishing points indicates overhead top-down view"
        )
    elif vp_clusters >= 1 and slanted_ratio >= 0.35:
        perspective = "ELEVATED_OBLIQUE"
        conf = 0.86
        explanation = f"Detected {vp_clusters} perspective convergence cluster(s) and strong slanted ground planes indicating elevated oblique view"
    else:
        perspective = "FIXED_CCTV"
        conf = 0.75
        explanation = "Moderate perspective distortion and horizontal ground plane typical of fixed surveillance camera"

    return {
        "perspective": perspective,
        "confidence": conf,
        "vanishing_points_found": vp_clusters,
        "recommended_perspective": perspective,
        "explanation": explanation,
    }


def _nms_boxes(
    detections: list[Detection], iou_threshold: float = 0.45
) -> list[Detection]:
    if not detections:
        return []

    boxes = np.array([d.bbox for d in detections], dtype=np.float32)
    scores = np.array([d.confidence for d in detections], dtype=np.float32)

    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    order = scores.argsort()[::-1]

    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)

        inds = np.where(iou <= iou_threshold)[0]
        order = order[inds + 1]

    return [detections[idx] for idx in keep]


class PersonDetector:
    """Unified person detector with automatic backend resolution and model reuse."""

    def __init__(
        self,
        model_path: str = "models/yolov8n.onnx",
        confidence_threshold: float = 0.35,
        input_size: int = 640,
    ):
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.input_size = input_size

        self.backend_name = "opencv_hog_motion_fallback"
        self._ultralytics_model = None
        self._onnx_net = None
        self._hog = None
        self._bg_subtractor = None

        self._load_model()

    def _load_model(self) -> None:
        # Try ultralytics first
        try:
            from ultralytics import YOLO

            weights = "yolov8n.pt"
            if os.path.exists(self.model_path) and self.model_path.endswith(".pt"):
                weights = self.model_path
            self._ultralytics_model = YOLO(weights)
            self.backend_name = "ultralytics_yolo"
            logger.info("YOLO detector initialized via Ultralytics", backend=self.backend_name)
            return
        except Exception:
            pass

        # Try ONNX via OpenCV dnn
        if os.path.exists(self.model_path) and self.model_path.endswith(".onnx"):
            try:
                self._onnx_net = cv2.dnn.readNetFromONNX(self.model_path)
                self.backend_name = "opencv_dnn_onnx"
                logger.info("ONNX detector initialized via OpenCV DNN", backend=self.backend_name)
                return
            except Exception:
                pass

        # Robust OpenCV fallback (HOG + background subtraction)
        self.backend_name = "opencv_hog_motion_fallback"
        self._hog = cv2.HOGDescriptor()
        self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        self._bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=300, varThreshold=25, detectShadows=True
        )
        logger.info("Using robust OpenCV fallback person detector", backend=self.backend_name)

    def reset_temporal_state(self) -> None:
        if self._bg_subtractor is not None:
            self._bg_subtractor = cv2.createBackgroundSubtractorMOG2(
                history=300, varThreshold=25, detectShadows=True
            )

    def detect(
        self, frame: np.ndarray, perspective: str = "FIXED_CCTV"
    ) -> tuple[list[Detection], float]:
        if frame is None or frame.size == 0:
            return [], 0.0

        t0 = time.perf_counter()
        raw_dets: list[Detection] = []
        try:
            if self.backend_name == "ultralytics_yolo" and self._ultralytics_model:
                raw_dets = self._detect_ultralytics(frame)
            elif self.backend_name == "opencv_dnn_onnx" and self._onnx_net:
                raw_dets = self._detect_onnx(frame)
            else:
                raw_dets = self._detect_opencv_fallback(frame, perspective)
        except Exception as exc:
            logger.error("Inference error on frame", backend=self.backend_name, error=str(exc))
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return [], round(elapsed_ms, 2)

        h, w = frame.shape[:2]
        mapped: list[Detection] = []
        for det in raw_dets:
            x1, y1, x2, y2 = det.bbox
            x1 = max(0.0, min(float(w - 1), x1))
            y1 = max(0.0, min(float(h - 1), y1))
            x2 = max(0.0, min(float(w - 1), x2))
            y2 = max(0.0, min(float(h - 1), y2))
            bw = x2 - x1
            bh = y2 - y1

            if bw < 4 or bh < 4:
                continue

            # Aspect ratio sanity check based on perspective
            if perspective.upper() == "DRONE_TOPDOWN":
                aspect = bh / max(bw, 1.0)
                if not (0.3 <= aspect <= 3.0):
                    continue
            else:
                aspect = bh / max(bw, 1.0)
                if not (0.55 <= aspect <= 5.0):
                    continue

            mapped.append(Detection(bbox=(x1, y1, x2, y2), confidence=det.confidence, class_id=0))

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return mapped, round(elapsed_ms, 2)

    def _detect_ultralytics(self, frame: np.ndarray) -> list[Detection]:
        results = self._ultralytics_model.predict(
            frame, classes=[0], conf=self.confidence_threshold, verbose=False
        )
        dets: list[Detection] = []
        for r in results:
            if r.boxes is not None:
                for box in r.boxes:
                    xyxy = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0].cpu().numpy())
                    dets.append(
                        Detection(
                            bbox=(float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])),
                            confidence=conf,
                        )
                    )
        return dets

    def _detect_onnx(self, frame: np.ndarray) -> list[Detection]:
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(
            frame, 1 / 255.0, (self.input_size, self.input_size), swapRB=True, crop=False
        )
        self._onnx_net.setInput(blob)
        preds = self._onnx_net.forward()

        # Output shape: (1, 84, 8400) or similar YOLOv8 output
        if len(preds.shape) == 3 and preds.shape[1] < preds.shape[2]:
            preds = np.transpose(preds[0], (1, 0))
        elif len(preds.shape) == 3:
            preds = preds[0]

        boxes = []
        scores = []
        x_scale = w / float(self.input_size)
        y_scale = h / float(self.input_size)

        for row in preds:
            cls_conf = float(row[4]) if len(row) > 4 else 0.0
            if cls_conf < self.confidence_threshold:
                continue
            cx, cy, bw, bh = row[0], row[1], row[2], row[3]
            x1 = (cx - bw * 0.5) * x_scale
            y1 = (cy - bh * 0.5) * y_scale
            boxes.append([int(x1), int(y1), int(bw * x_scale), int(bh * y_scale)])
            scores.append(cls_conf)

        indices = cv2.dnn.NMSBoxes(boxes, scores, self.confidence_threshold, 0.45)
        dets: list[Detection] = []
        for idx in indices:
            b = boxes[idx]
            dets.append(
                Detection(
                    bbox=(float(b[0]), float(b[1]), float(b[0] + b[2]), float(b[1] + b[3])),
                    confidence=float(scores[idx]),
                )
            )
        return dets

    def _detect_opencv_fallback(
        self, frame: np.ndarray, perspective: str = "FIXED_CCTV"
    ) -> list[Detection]:
        h, w = frame.shape[:2]
        dets: list[Detection] = []

        # 1. HOG detector
        rects, weights = self._hog.detectMultiScale(
            frame, winStride=(8, 8), padding=(8, 8), scale=1.05
        )
        for (rx, ry, rw, rh), weight in zip(rects, weights):
            conf = min(0.95, max(0.40, float(weight) * 0.4 + 0.5))
            if conf >= self.confidence_threshold:
                dets.append(
                    Detection(
                        bbox=(float(rx), float(ry), float(rx + rw), float(ry + rh)),
                        confidence=conf,
                    )
                )

        # 2. Motion / Background subtraction blobs
        fg_mask = self._bg_subtractor.apply(frame)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        fg_clean = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(fg_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for c in contours:
            area = cv2.contourArea(c)
            if area < 100:
                continue
            bx, by, bw, bh = cv2.boundingRect(c)
            aspect = bh / max(bw, 1.0)
            conf = min(0.85, 0.45 + (area / float(w * h)) * 10.0)

            # Cluster splitting for multiple people in a blob
            est_single_area = max(400.0, (w * h) * 0.003)
            if area > est_single_area * 1.8 and bw > bh:
                n_people = min(5, max(2, int(round(area / est_single_area))))
                sub_w = bw / float(n_people)
                for k in range(n_people):
                    sub_x1 = bx + k * sub_w
                    dets.append(
                        Detection(
                            bbox=(float(sub_x1), float(by), float(sub_x1 + sub_w), float(by + bh)),
                            confidence=max(0.42, conf - 0.08),
                        )
                    )
            else:
                dets.append(
                    Detection(
                        bbox=(float(bx), float(by), float(bx + bw), float(by + bh)),
                        confidence=conf,
                    )
                )

        return _nms_boxes(dets, iou_threshold=0.40)
