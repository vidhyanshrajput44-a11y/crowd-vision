"""Crowd analytics engine computing zone counts, calibrated/relative density, flow, speed, and anomalies."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Optional

import numpy as np

from app.analytics.zone_mapper import ZoneDefinition, ZoneMapper
from app.cv.bytetrack import TrackedPerson


@dataclass
class ZoneAnalyticsSnapshot:
    """Computed metrics for a single zone at a specific video timestamp."""

    zone_id: str
    zone_name: str
    video_timestamp_sec: float
    people_count: int
    capacity: int
    occupancy_ratio: float
    density_value: float
    density_unit: str
    inflow_rate: float
    outflow_rate: float
    net_flow: float
    avg_speed: float
    movement_direction: str
    is_bottleneck: bool
    is_counterflow: bool
    crowd_increase_pct: float = 0.0
    capacity_utilization_pct: float = 0.0


class CrowdAnalyticsEngine:
    """Tracks per-zone occupancy, inflow/outflow transitions, velocity, and anomalies."""

    def __init__(self, mapper: ZoneMapper):
        self.mapper = mapper
        self._prev_track_zone: dict[int, Optional[str]] = {}
        self._ema_inflow: dict[str, float] = {z.zone_id: 0.0 for z in mapper.zones}
        self._ema_outflow: dict[str, float] = {z.zone_id: 0.0 for z in mapper.zones}
        self._prev_zone_counts: dict[str, int] = {}

    def reset(self) -> None:
        self._prev_track_zone.clear()
        self._ema_inflow = {z.zone_id: 0.0 for z in self.mapper.zones}
        self._ema_outflow = {z.zone_id: 0.0 for z in self.mapper.zones}
        self._prev_zone_counts.clear()

    def compute_frame_analytics(
        self,
        tracked_people: list[TrackedPerson],
        frame_w: int,
        frame_h: int,
        video_timestamp_sec: float,
        dt_sec: float = 0.5,
    ) -> tuple[list[ZoneAnalyticsSnapshot], list[dict[str, Any]], list[list[float]]]:
        dt_min = max(dt_sec, 0.1) / 60.0

        zone_members: dict[str, list[TrackedPerson]] = {z.zone_id: [] for z in self.mapper.zones}
        zone_entries: dict[str, int] = {z.zone_id: 0 for z in self.mapper.zones}
        zone_exits: dict[str, int] = {z.zone_id: 0 for z in self.mapper.zones}

        current_track_zones: dict[int, Optional[str]] = {}
        norm_points: list[tuple[float, float]] = []
        serialized_detections: list[dict[str, Any]] = []

        for person in tracked_people:
            fx, fy = person.foot_point
            nx, ny = self.mapper.project_point(fx, fy, frame_w, frame_h)
            norm_points.append((nx, ny))

            assigned_zone = self.mapper.find_zone(nx, ny, px=fx, py=fy)
            assigned_zid = assigned_zone.zone_id if assigned_zone else None
            current_track_zones[person.track_id] = assigned_zid

            if assigned_zid and assigned_zid in zone_members:
                zone_members[assigned_zid].append(person)

            prev_zid = self._prev_track_zone.get(person.track_id)
            if prev_zid != assigned_zid:
                if assigned_zid and assigned_zid in zone_entries:
                    zone_entries[assigned_zid] += 1
                if prev_zid and prev_zid in zone_exits:
                    zone_exits[prev_zid] += 1

            serialized_detections.append(
                {
                    "track_id": person.track_id,
                    "bbox": [round(float(c), 1) for c in person.bbox],
                    "norm_bbox": [
                        round(max(0.0, min(1.0, float(person.bbox[0]) / max(float(frame_w), 1.0))), 4),
                        round(max(0.0, min(1.0, float(person.bbox[1]) / max(float(frame_h), 1.0))), 4),
                        round(max(0.0, min(1.0, float(person.bbox[2]) / max(float(frame_w), 1.0))), 4),
                        round(max(0.0, min(1.0, float(person.bbox[3]) / max(float(frame_h), 1.0))), 4),
                    ],
                    "confidence": round(float(person.confidence), 2),
                    "foot_point": [round(float(fx), 1), round(float(fy), 1)],
                    "norm_point": [round(float(nx), 4), round(float(ny), 4)],
                    "zone_id": assigned_zid,
                    "zone_name": assigned_zone.name if assigned_zone else "UNASSIGNED",
                    "vx": round(float(person.vx), 3),
                    "vy": round(float(person.vy), 3),
                    "speed": round(float(person.speed), 3),
                    "trajectory": [[round(pt[0], 1), round(pt[1], 1)] for pt in getattr(person, "history", [])],
                }
            )

        self._prev_track_zone = current_track_zones

        snapshots: list[ZoneAnalyticsSnapshot] = []
        alpha = 0.35

        for z in self.mapper.zones:
            zid = z.zone_id
            members = zone_members.get(zid, [])
            count = len(members)

            # Inflow and outflow rates (people / minute)
            inst_inflow = float(zone_entries.get(zid, 0)) / dt_min
            inst_outflow = float(zone_exits.get(zid, 0)) / dt_min

            self._ema_inflow[zid] = alpha * inst_inflow + (1.0 - alpha) * self._ema_inflow.get(zid, 0.0)
            self._ema_outflow[zid] = alpha * inst_outflow + (1.0 - alpha) * self._ema_outflow.get(zid, 0.0)

            inflow = self._ema_inflow[zid]
            outflow = self._ema_outflow[zid]
            net_flow = inflow - outflow

            # Occupancy & density
            cap = max(1, z.capacity)
            occupancy_ratio = float(count) / float(cap)
            capacity_utilization_pct = min(100.0, occupancy_ratio * 100.0)

            prev_count = self._prev_zone_counts.get(zid, count)
            if prev_count > 0:
                crowd_increase_pct = float(count - prev_count) / float(prev_count) * 100.0
            else:
                crowd_increase_pct = 100.0 if count > 0 else 0.0
            self._prev_zone_counts[zid] = count

            if z.is_physically_calibrated and z.area_sqm and z.area_sqm > 0:
                density_val = float(count) / float(z.area_sqm)
                density_unit = "people_per_sqm"
            else:
                density_val = occupancy_ratio
                density_unit = "relative_estimate"

            avg_speed, direction, is_counterflow = self._analyze_movement(members, frame_w, frame_h)

            # Bottleneck condition
            is_bottleneck = (inflow > outflow * 1.8) and (occupancy_ratio >= 0.70)

            snapshots.append(
                ZoneAnalyticsSnapshot(
                    zone_id=zid,
                    zone_name=z.name,
                    video_timestamp_sec=video_timestamp_sec,
                    people_count=count,
                    capacity=z.capacity,
                    occupancy_ratio=round(occupancy_ratio, 4),
                    density_value=round(density_val, 4),
                    density_unit=density_unit,
                    inflow_rate=round(inflow, 2),
                    outflow_rate=round(outflow, 2),
                    net_flow=round(net_flow, 2),
                    avg_speed=round(avg_speed, 4),
                    movement_direction=direction,
                    is_bottleneck=is_bottleneck,
                    is_counterflow=is_counterflow,
                    crowd_increase_pct=round(crowd_increase_pct, 1),
                    capacity_utilization_pct=round(capacity_utilization_pct, 1),
                )
            )

        perspective = getattr(self, "perspective", "FIXED_CCTV")
        heatmap_grid = self.mapper.generate_heatmap_grid(norm_points, perspective=perspective)
        return snapshots, serialized_detections, heatmap_grid

    def get_accumulated_heatmap_grid(self) -> list[list[float]]:
        return self.mapper.get_accumulated_heatmap_grid()

    def _analyze_movement(
        self, members: list[TrackedPerson], frame_w: int, frame_h: int
    ) -> tuple[float, str, bool]:
        if not members:
            return 0.0, "STATIONARY", False

        vx_list = [p.vx for p in members]
        vy_list = [p.vy for p in members]
        speeds = [math.hypot(vx, vy) for vx, vy in zip(vx_list, vy_list)]
        avg_speed = float(np.mean(speeds)) if speeds else 0.0

        if avg_speed < 1.5:
            return avg_speed, "STATIONARY", False

        # Check opposing movement vectors for counterflow
        moving_vecs = [(p.vx, p.vy) for p in members if math.hypot(p.vx, p.vy) >= 1.5]
        opposing_pairs = 0
        for i in range(len(moving_vecs)):
            for j in range(i + 1, len(moving_vecs)):
                v1 = moving_vecs[i]
                v2 = moving_vecs[j]
                dot = v1[0] * v2[0] + v1[1] * v2[1]
                norm1 = math.hypot(*v1)
                norm2 = math.hypot(*v2)
                if norm1 > 0 and norm2 > 0:
                    cos_theta = dot / (norm1 * norm2)
                    if cos_theta < -0.65:
                        opposing_pairs += 1

        is_counterflow = (
            opposing_pairs >= max(1, len(moving_vecs) // 3) and len(moving_vecs) >= 3
        )
        if is_counterflow:
            return avg_speed, "MIXED", True

        mean_vx = float(np.mean(vx_list))
        mean_vy = float(np.mean(vy_list))

        if abs(mean_vy) >= abs(mean_vx):
            direction = "INWARD" if mean_vy > 0 else "OUTWARD"
        else:
            direction = "LATERAL"

        return avg_speed, direction, False
