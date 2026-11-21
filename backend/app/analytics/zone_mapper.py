"""Venue zone polygon mapping, optional homography calibration, and real spatial heatmap generator."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import NamedTuple, Optional

import cv2
import numpy as np


class PolygonValidationResult(NamedTuple):
    is_valid: bool
    errors: list[str]


def _ccw(p1: list[float] | tuple[float, float], p2: list[float] | tuple[float, float], p3: list[float] | tuple[float, float]) -> float:
    return (p2[0] - p1[0]) * (p3[1] - p1[1]) - (p2[1] - p1[1]) * (p3[0] - p1[0])


def _segments_intersect_strictly(
    p1: list[float] | tuple[float, float],
    p2: list[float] | tuple[float, float],
    p3: list[float] | tuple[float, float],
    p4: list[float] | tuple[float, float],
) -> bool:
    d1 = _ccw(p3, p4, p1)
    d2 = _ccw(p3, p4, p2)
    d3 = _ccw(p1, p2, p3)
    d4 = _ccw(p1, p2, p4)

    return bool(
        ((d1 > 1e-6 and d2 < -1e-6) or (d1 < -1e-6 and d2 > 1e-6))
        and ((d3 > 1e-6 and d4 < -1e-6) or (d3 < -1e-6 and d4 > 1e-6))
    )


def validate_polygon_geometry(points: list[list[float]]) -> PolygonValidationResult:
    errors: list[str] = []
    if not points or len(points) < 3:
        errors.append("A polygon zone requires at least 3 distinct boundary vertices.")
        return PolygonValidationResult(False, errors)

    n = len(points)
    for idx, pt in enumerate(points):
        if len(pt) < 2 or not np.isfinite(pt[0]) or not np.isfinite(pt[1]):
            errors.append(f"Vertex {idx} contains non-finite or invalid coordinates.")
            return PolygonValidationResult(False, errors)

    for i in range(n):
        p_curr = points[i]
        p_next = points[(i + 1) % n]
        if np.hypot(p_next[0] - p_curr[0], p_next[1] - p_curr[1]) < 1e-5:
            errors.append(f"Vertices at index {i} and {(i + 1) % n} are coincident or too close.")
            return PolygonValidationResult(False, errors)

    for i in range(n):
        p1 = points[i]
        p2 = points[(i + 1) % n]
        for j in range(i + 2, n):
            if (i == 0 and j == n - 1):
                continue
            p3 = points[j]
            p4 = points[(j + 1) % n]
            if _segments_intersect_strictly(p1, p2, p3, p4):
                errors.append(f"Polygon boundary self-intersects between edges ({i}-{(i+1)%n}) and ({j}-{(j+1)%n}).")
                return PolygonValidationResult(False, errors)

    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += points[i][0] * points[j][1] - points[j][0] * points[i][1]
    area = 0.5 * abs(area)
    if area < 1e-5:
        errors.append("Degenerate polygon with near-zero area.")
        return PolygonValidationResult(False, errors)

    return PolygonValidationResult(True, [])


@dataclass
class ZoneDefinition:
    """In-memory zone geometry and capacity definition."""
    zone_id: str
    zone_name: str = ""
    zone_type: str = "GENERAL"
    polygon_points: list[list[float]] = field(default_factory=list)
    max_capacity: int = 50
    area_sqm: Optional[float] = None
    is_physically_calibrated: bool = False
    adjacent_zone_ids: Optional[list[str]] = None
    is_entry: bool = False
    is_exit: bool = False
    threshold_low: float = 0.45
    threshold_moderate: float = 0.65
    threshold_high: float = 0.82
    threshold_critical: float = 0.95
    density_moderate: Optional[float] = None
    density_high: Optional[float] = None
    density_critical: Optional[float] = None
    is_emergency_exit: bool = False
    color: str = "#0d9488"
    monitoring_priority: str = "ROUTINE"
    name: Optional[str] = None
    capacity: Optional[int] = None

    def __post_init__(self):
        if self.adjacent_zone_ids is None:
            self.adjacent_zone_ids = []
        if self.name and not self.zone_name:
            self.zone_name = self.name
        elif self.zone_name and not self.name:
            self.name = self.zone_name
        if self.capacity is not None:
            self.max_capacity = self.capacity
        else:
            self.capacity = self.max_capacity


class ZoneMapper:
    """Maps image-space coordinates to venue zones and constructs Gaussian density heatmaps."""

    def __init__(
        self,
        zones: list[ZoneDefinition],
        calibration_homography: Optional[list[list[float]] | np.ndarray] = None,
    ):
        self.zones = zones
        self._homography: Optional[np.ndarray] = None
        if calibration_homography is not None:
            self._homography = np.array(calibration_homography, dtype=np.float32)

        self._contours: dict[str, np.ndarray] = {}
        for z in zones:
            pts_data = z.polygon_points
            if pts_data and len(pts_data) >= 3:
                try:
                    pts = np.ascontiguousarray(np.array(pts_data, dtype=np.float32))
                    if pts.ndim == 2 and pts.shape[0] >= 3 and pts.shape[1] == 2:
                        self._contours[z.zone_id] = pts
                except Exception:
                    pass

        # Heatmap density states for temporal smoothing & accumulation
        self._current_density_grid: Optional[np.ndarray] = None
        self._accumulated_density_grid: Optional[np.ndarray] = None

    def reset_heatmap_state(self) -> None:
        self._current_density_grid = None
        self._accumulated_density_grid = None

    @staticmethod
    def compute_homography(
        image_points: list[list[float]], venue_points: list[list[float]]
    ) -> list[list[float]]:
        if len(image_points) < 4 or len(venue_points) < 4:
            raise ValueError("At least 4 reference point pairs are required for homography calibration")

        src = np.array(image_points, dtype=np.float32)
        dst = np.array(venue_points, dtype=np.float32)
        matrix, _ = cv2.findHomography(src, dst, cv2.RANSAC)
        if matrix is None:
            raise ValueError("Could not compute valid homography matrix from supplied points")
        return matrix.tolist()

    def project_point(
        self, px: float, py: float, frame_w: int, frame_h: int
    ) -> tuple[float, float]:
        nx = max(0.0, min(1.0, float(px) / max(float(frame_w), 1.0)))
        ny = max(0.0, min(1.0, float(py) / max(float(frame_h), 1.0)))

        if self._homography is None:
            return nx, ny

        pt = np.array([[[float(px), float(py)]]], dtype=np.float32)
        projected = cv2.perspectiveTransform(pt, self._homography)
        mapped_x = float(projected[0, 0, 0])
        mapped_y = float(projected[0, 0, 1])
        return max(0.0, min(1.0, mapped_x)), max(0.0, min(1.0, mapped_y))

    def find_zone(
        self,
        norm_x: float,
        norm_y: float,
        px: Optional[float] = None,
        py: Optional[float] = None,
    ) -> Optional[ZoneDefinition]:
        for z in self.zones:
            contour = self._contours.get(z.zone_id)
            if contour is None or len(contour) < 3:
                continue
            try:
                # 1. Test normalized coordinates (when contour is in 0..1 normalized space)
                if cv2.pointPolygonTest(contour, (float(norm_x), float(norm_y)), False) >= 0:
                    return z

                # 2. Test raw pixel coordinates (when contour is in pixel space)
                if px is not None and py is not None:
                    if cv2.pointPolygonTest(contour, (float(px), float(py)), False) >= 0:
                        return z

                # 3. Test standard coordinate projections (1280x720, 1920x1080, 1000x1000 SVG)
                for w, h in [(1280.0, 720.0), (1000.0, 1000.0), (1920.0, 1080.0), (640.0, 480.0)]:
                    if cv2.pointPolygonTest(contour, (float(norm_x * w), float(norm_y * h)), False) >= 0:
                        return z
            except Exception:
                continue
        return None

    def generate_heatmap_grid(
        self,
        normalized_points: list[tuple[float, float]],
        grid_rows: int = 20,
        grid_cols: int = 12,
        sigma: float = 2.0,
        perspective: str = "FIXED_CCTV",
        decay: float = 0.85,
        alpha: float = 0.65,
        **kwargs: Any,
    ) -> list[list[float]]:
        """Constructs an accurate spatial crowd density heatmap from person ground footpoints.

        Uses Gaussian Kernel Density Estimation (KDE), perspective compensation,
        and temporal exponential smoothing.
        """
        instant_grid = np.zeros((grid_rows, grid_cols), dtype=np.float32)
        if not normalized_points:
            # Decay existing grid smoothly towards zero
            if self._current_density_grid is not None and self._current_density_grid.shape == (grid_rows, grid_cols):
                self._current_density_grid *= float(decay)
                if float(np.max(self._current_density_grid)) > 0.02:
                    return np.round(np.clip(self._current_density_grid, 0.0, 1.0), 3).tolist()
                else:
                    self._current_density_grid = None
            return instant_grid.tolist()

        is_drone = perspective.upper() == "DRONE_TOPDOWN"

        # Continuous spatial density mapping
        for nx, ny in normalized_points:
            c = min(grid_cols - 1, max(0, int(nx * grid_cols)))
            r = min(grid_rows - 1, max(0, int(ny * grid_rows)))
            # Weight contribution: perspective compensation
            if is_drone:
                weight = 1.0
            else:
                weight = 1.0 + 0.3 * (1.0 - float(ny))
            instant_grid[r, c] += weight

        # Gaussian kernel smoothing
        eff_sigma = max(0.8, float(sigma))
        ksize = int(round(eff_sigma * 3.0)) | 1
        if ksize < 3:
            ksize = 3
        smooth_grid = cv2.GaussianBlur(instant_grid, (ksize, ksize), sigmaX=eff_sigma, sigmaY=eff_sigma)

        # Temporal smoothing: exponential moving average
        if self._current_density_grid is None or self._current_density_grid.shape != (grid_rows, grid_cols):
            self._current_density_grid = smooth_grid.copy()
        else:
            self._current_density_grid = (
                alpha * smooth_grid + (1.0 - alpha) * (self._current_density_grid * float(decay))
            )

        # Accumulated density grid (historical dwell & spatial flow)
        if self._accumulated_density_grid is None or self._accumulated_density_grid.shape != (grid_rows, grid_cols):
            self._accumulated_density_grid = smooth_grid.copy()
        else:
            self._accumulated_density_grid = (
                0.08 * smooth_grid + 0.92 * self._accumulated_density_grid
            )

        max_val = float(np.max(self._current_density_grid))
        if max_val > 1e-6:
            norm_grid = self._current_density_grid / max_val
        else:
            norm_grid = self._current_density_grid

        return np.round(np.clip(norm_grid, 0.0, 1.0), 3).tolist()

    def get_accumulated_heatmap_grid(self, grid_rows: int = 36, grid_cols: int = 64) -> list[list[float]]:
        """Returns the normalized accumulated spatial traffic / dwell heatmap."""
        if self._accumulated_density_grid is None or self._accumulated_density_grid.shape != (grid_rows, grid_cols):
            return np.zeros((grid_rows, grid_cols), dtype=np.float32).tolist()
        peak = float(np.max(self._accumulated_density_grid))
        if peak > 1e-6:
            norm = self._accumulated_density_grid / peak
        else:
            norm = self._accumulated_density_grid
        return np.round(np.clip(norm, 0.0, 1.0), 3).tolist()

    def generate_predicted_heatmap_grid(
        self,
        base_grid: list[list[float]],
        predicted_growth_by_zone: Optional[dict[str, float]] = None,
        zone_velocity_by_zone: Optional[dict[str, tuple[float, float]]] = None,
        horizon_sec: int = 60,
        zone_scale_factors: Optional[dict[str, float]] = None,
        zone_velocities: Optional[dict[str, tuple[float, float]]] = None,
        **kwargs: Any,
    ) -> list[list[float]]:
        if not base_grid:
            return []

        rows = len(base_grid)
        cols = len(base_grid[0]) if rows > 0 else 0
        arr = np.array(base_grid, dtype=np.float32)
        if rows == 0 or cols == 0:
            return arr.tolist()

        growth_map = zone_scale_factors if zone_scale_factors is not None else (predicted_growth_by_zone or {})
        vel_map = zone_velocities if zone_velocities is not None else (zone_velocity_by_zone or {})

        time_norm = min(3.0, float(horizon_sec) / 60.0)

        # Scale by zone growth
        scaled = arr.copy()
        for z in self.zones:
            rate = growth_map.get(z.zone_id, 0.0)
            if rate > 0.5:
                mult = max(0.2, min(3.0, rate))
            else:
                mult = max(0.2, min(3.0, 1.0 + (rate * time_norm)))
            contour = self._contours.get(z.zone_id)
            if contour is None or len(contour) < 3:
                continue
            for r in range(rows):
                for c in range(cols):
                    nx = (c + 0.5) / cols
                    ny = (r + 0.5) / rows
                    try:
                        if cv2.pointPolygonTest(contour, (float(nx), float(ny)), False) >= 0:
                            scaled[r, c] *= mult
                    except Exception:
                        continue

        # Advection
        advected = np.zeros_like(scaled)
        for r in range(rows):
            for c in range(cols):
                val = scaled[r, c]
                if val <= 0.001:
                    continue
                nx = (c + 0.5) / cols
                ny = (r + 0.5) / rows
                z = self.find_zone(nx, ny)
                vx, vy = vel_map.get(z.zone_id, (0.0, 0.0)) if z else (0.0, 0.0)
                target_c = c + int(round(vx * cols * time_norm * 0.4))
                target_r = r + int(round(vy * rows * time_norm * 0.4))
                tc = max(0, min(cols - 1, target_c))
                tr = max(0, min(rows - 1, target_r))
                advected[tr, tc] += val

        blended = 0.45 * scaled + 0.55 * advected
        ksize = 3 if horizon_sec <= 60 else 5
        sigma = 0.8 + 0.3 * (float(horizon_sec) / 60.0)
        smoothed = cv2.GaussianBlur(blended, (ksize, ksize), sigmaX=sigma, sigmaY=sigma)

        return np.round(np.clip(smoothed, 0.0, 1.0), 3).tolist()
