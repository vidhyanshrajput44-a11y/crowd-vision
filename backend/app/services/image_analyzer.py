"""Service for single image person detection, perspective assessment, zone mapping, and spatial heatmap generation."""
from __future__ import annotations

import time
from typing import Any, Optional
import uuid

import cv2
import numpy as np
from sqlalchemy import select

from app.analytics.zone_mapper import ZoneDefinition, ZoneMapper
from app.config import get_settings
from app.core.logging import get_logger
from app.cv.detector import PersonDetector, assess_footage_perspective, compute_ground_contact
from app.database.models import SingleImageAnalysis, VenueLayout, Zone
from app.database.session import get_session_factory

logger = get_logger("services.image_analyzer")


STATIC_ANALYSIS_DISCLAIMER = (
    "Single-frame static observation. Temporal movement trends, inflow/outflow rates, "
    "and future crowd forecasts are not available for static images."
)


class SingleImageAnalyzer:
    """Analyzes a single uploaded still image for crowd detection and zone occupancy."""

    def __init__(self, detector: Optional[PersonDetector] = None):
        self.detector = detector or PersonDetector()

    @classmethod
    async def analyze_image(
        cls_or_self,
        image_bytes: bytes,
        filename: str,
        event_id: Optional[str] = None,
        venue_id: Optional[str] = None,
        layout_id: Optional[str] = None,
        camera_perspective: Optional[str] = None,
        detector: Optional[PersonDetector] = None,
    ) -> dict[str, Any]:
        detector = cls_or_self.detector if isinstance(cls_or_self, SingleImageAnalyzer) else (detector or PersonDetector())
        settings = get_settings()
        session_factory = get_session_factory()
        t0 = time.perf_counter()

        np_arr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None or frame.size == 0:
            raise ValueError("Failed to decode uploaded image file. Unsupported or corrupted format.")

        img_h, img_w = frame.shape[:2]

        storage_dir = settings.images_dir
        storage_dir.mkdir(parents=True, exist_ok=True)
        stored_filename = f"{uuid.uuid4()}_{filename}"
        stored_path = storage_dir / stored_filename

        with open(stored_path, "wb") as f:
            f.write(image_bytes)

        zone_defs: list[ZoneDefinition] = []
        homography = None

        async with session_factory() as session:
            if layout_id:
                layout = await session.get(VenueLayout, layout_id)
                if layout and layout.zones_data:
                    for z in layout.zones_data:
                        if isinstance(z, dict):
                            zid = str(z.get("zone_id") or z.get("id") or uuid.uuid4())
                            zname = str(z.get("zone_name") or z.get("name") or zid)
                            pts = z.get("polygon_points") or z.get("boundary_coordinates") or []
                            cap = int(z.get("max_capacity") or z.get("capacity") or 50)
                            color = str(z.get("color") or "#0d9488")
                            zone_defs.append(
                                ZoneDefinition(
                                    zone_id=zid,
                                    name=zname,
                                    polygon_points=pts,
                                    capacity=cap,
                                    color=color,
                                )
                            )
                    homography = layout.calibration_homography
            elif venue_id:
                zones = (
                    await session.execute(select(Zone).where(Zone.venue_id == venue_id))
                ).scalars().all()
                for z in zones:
                    zone_defs.append(
                        ZoneDefinition(
                            zone_id=z.id,
                            name=z.name,
                            polygon_points=z.polygon_points or [],
                            capacity=z.capacity.max_capacity if z.capacity else 50,
                            color=z.color or "#0d9488",
                        )
                    )

        perspective_info = assess_footage_perspective(frame)
        perspective = camera_perspective or perspective_info["recommended_perspective"]

        detections, inference_ms = detector.detect(frame, perspective=perspective)
        total_people = len(detections)

        mapper = ZoneMapper(zones=zone_defs, calibration_homography=homography)

        norm_points: list[tuple[float, float]] = []
        zone_counts: dict[str, int] = {z.zone_id: 0 for z in zone_defs}
        serialized_dets: list[dict[str, Any]] = []

        for d in detections:
            foot_x, foot_y = compute_ground_contact(d.bbox, perspective=perspective)
            nx, ny = mapper.project_point(foot_x, foot_y, img_w, img_h)
            norm_points.append((nx, ny))

            assigned_zone = mapper.find_zone(nx, ny)
            assigned_zid = assigned_zone.zone_id if assigned_zone else None
            if assigned_zid and assigned_zid in zone_counts:
                zone_counts[assigned_zid] += 1

            serialized_dets.append(
                {
                    "bbox": list(d.bbox),
                    "confidence": round(float(d.confidence), 2),
                    "foot_point": [round(float(foot_x), 1), round(float(foot_y), 1)],
                    "norm_point": [round(float(nx), 4), round(float(ny), 4)],
                    "zone_id": assigned_zid,
                    "zone_name": assigned_zone.name if assigned_zone else "UNASSIGNED",
                }
            )

        heatmap_grid = mapper.generate_heatmap_grid(norm_points)

        zone_occupancies = []
        for z in zone_defs:
            count = zone_counts.get(z.zone_id, 0)
            ratio = count / max(1, z.capacity)
            zone_occupancies.append(
                {
                    "zone_id": z.zone_id,
                    "zone_name": z.name,
                    "people_count": count,
                    "capacity": z.capacity,
                    "occupancy_ratio": round(ratio, 4),
                    "density_pct": round(min(100.0, ratio * 100.0), 1),
                }
            )

        analysis_id = str(uuid.uuid4())
        image_url = f"/uploads/images/{stored_filename}"

        analysis_record = SingleImageAnalysis(
            id=analysis_id,
            event_id=event_id,
            venue_id=venue_id,
            layout_id=layout_id,
            original_filename=filename,
            stored_path=str(stored_path),
            image_url=image_url,
            width=img_w,
            height=img_h,
            total_people=total_people,
            inference_ms=inference_ms,
            detector_backend=detector.backend_name,
            camera_perspective=perspective,
            detections=serialized_dets,
            heatmap_grid=heatmap_grid,
            zone_occupancies=zone_occupancies,
            analysis_note=f"Analyzed {total_people} persons across {len(zone_defs)} zones with {perspective} perspective.",
            disclaimer=STATIC_ANALYSIS_DISCLAIMER,
        )

        async with session_factory() as session:
            session.add(analysis_record)
            await session.commit()

        logger.info(
            "Single image analysis completed",
            id=analysis_id,
            people=total_people,
            inference_ms=inference_ms,
        )

        return {
            "id": analysis_id,
            "event_id": event_id,
            "venue_id": venue_id,
            "layout_id": layout_id,
            "original_filename": filename,
            "image_url": image_url,
            "width": img_w,
            "height": img_h,
            "total_people": total_people,
            "inference_ms": inference_ms,
            "detector_backend": detector.backend_name,
            "camera_perspective": perspective,
            "detections": serialized_dets,
            "heatmap_grid": heatmap_grid,
            "zone_occupancies": zone_occupancies,
            "analysis_note": analysis_record.analysis_note,
            "disclaimer": analysis_record.disclaimer,
            "created_at": analysis_record.created_at,
        }
