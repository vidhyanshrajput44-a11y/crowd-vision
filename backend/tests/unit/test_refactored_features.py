"""Unit and API integration tests for refactored spatial features."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from app.analytics.zone_mapper import ZoneMapper, validate_polygon_geometry
from app.cv.detector import assess_footage_perspective, compute_ground_contact
from app.main import app


def test_polygon_geometry_validation():
    valid_triangle = [[0.1, 0.1], [0.5, 0.8], [0.9, 0.1]]
    is_valid, errors = validate_polygon_geometry(valid_triangle)
    assert is_valid is True
    assert len(errors) == 0

    hourglass = [[0.1, 0.1], [0.8, 0.8], [0.8, 0.1], [0.1, 0.8]]
    is_valid, errors = validate_polygon_geometry(hourglass)
    assert is_valid is False
    assert any("self-intersect" in e.lower() for e in errors)

    too_few = [[0.1, 0.1], [0.2, 0.2]]
    is_valid, errors = validate_polygon_geometry(too_few)
    assert is_valid is False

    dup_pts = [[0.1, 0.1], [0.1, 0.1], [0.5, 0.5], [0.5, 0.1]]
    is_valid, errors = validate_polygon_geometry(dup_pts)
    assert is_valid is False
    assert any("coincident" in e.lower() or "close" in e.lower() for e in errors)


def test_ground_contact_by_perspective():
    bbox = (100.0, 50.0, 160.0, 150.0)
    gc_cctv = compute_ground_contact(bbox, perspective="FIXED_CCTV")
    assert gc_cctv == (130.0, 150.0)

    gc_oblique = compute_ground_contact(bbox, perspective="ELEVATED_OBLIQUE")
    assert gc_oblique == (130.0, 150.0)

    gc_drone = compute_ground_contact(bbox, perspective="DRONE_TOPDOWN")
    assert gc_drone == (130.0, 100.0)


def test_footage_perspective_assessment():
    topdown_frame = np.full((400, 400, 3), 255, dtype=np.uint8)
    for y in range(50, 350, 50):
        cv2.line(topdown_frame, (50, y), (350, y), (0, 0, 0), 2)
    for x in range(50, 350, 50):
        cv2.line(topdown_frame, (x, 50), (x, 350), (0, 0, 0), 2)
    res_td = assess_footage_perspective(topdown_frame)
    assert res_td["perspective"] in ("DRONE_TOPDOWN", "FIXED_CCTV")
    assert "perspective" in res_td
    assert "confidence" in res_td

    oblique_frame = np.full((400, 400, 3), 255, dtype=np.uint8)
    vp = (200, 60)
    for bx in range(20, 380, 40):
        cv2.line(oblique_frame, (bx, 380), vp, (0, 0, 0), 2)
    res_ob = assess_footage_perspective(oblique_frame)
    assert res_ob["perspective"] in ("ELEVATED_OBLIQUE", "FIXED_CCTV")


@pytest.mark.asyncio
async def test_layout_api_and_validation():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        login_res = await client.post(
            "/api/auth/login",
            json={"email": "admin@crowdvision.io", "password": "admin123"},
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        val_res = await client.post(
            "/api/layouts/validate-geometry",
            headers=headers,
            json={"polygon_points": [[0.1, 0.1], [0.6, 0.8], [0.8, 0.2]]},
        )
        assert val_res.status_code == 200
        assert val_res.json()["is_valid"] is True

        bad_res = await client.post(
            "/api/layouts/validate-geometry",
            headers=headers,
            json={"polygon_points": [[0.1, 0.1], [0.2, 0.2]]},
        )
        assert bad_res.status_code == 200
        assert bad_res.json()["is_valid"] is False

        create_res = await client.post(
            "/api/layouts/",
            headers=headers,
            json={
                "name": "Festival Grand Arena Layout",
                "description": "Multi-zone layout for main festival grounds",
                "canvas_width": 1280,
                "canvas_height": 720,
                "scale_factor": 0.05,
                "zones_data": [
                    {
                        "zone_id": "zone-stage-a",
                        "zone_name": "Stage A Arena",
                        "zone_type": "MAIN_STAGE",
                        "polygon_points": [[0.1, 0.1], [0.4, 0.1], [0.4, 0.4], [0.1, 0.4]],
                        "max_capacity": 450,
                        "area_sqm": 250.0,
                        "is_physically_calibrated": True,
                    },
                    {
                        "zone_id": "zone-corridor-1",
                        "zone_name": "North Corridor",
                        "zone_type": "EMERGENCY_CORRIDOR",
                        "polygon_points": [[0.45, 0.1], [0.65, 0.1], [0.65, 0.5], [0.45, 0.5]],
                        "max_capacity": 150,
                        "area_sqm": 80.0,
                        "is_physically_calibrated": True,
                    },
                ],
            },
        )
        assert create_res.status_code == 201
        layout = create_res.json()
        layout_id = layout["id"]
        assert layout["name"] == "Festival Grand Arena Layout"
        assert len(layout["zones_data"]) == 2

        get_res = await client.get(f"/api/layouts/{layout_id}", headers=headers)
        assert get_res.status_code == 200
        assert get_res.json()["id"] != ""
        assert "zones_data" in get_res.json()

        list_res = await client.get("/api/layouts/", headers=headers)
        assert list_res.status_code == 200
        assert len(list_res.json()) >= 1


@pytest.mark.asyncio
async def test_calibration_and_single_image_api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        login_res = await client.post(
            "/api/auth/login",
            json={"email": "admin@crowdvision.io", "password": "admin123"},
        )
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        homo_res = await client.post(
            "/api/calibration/homography",
            headers=headers,
            json={
                "camera_perspective": "FIXED_CCTV",
                "image_points": [[50, 50], [350, 50], [350, 350], [50, 350]],
                "venue_points": [[0, 0], [10, 0], [10, 10], [0, 10]],
                "scale_factor_m_per_px": 0.025,
            },
        )
        assert homo_res.status_code == 200
        homo_data = homo_res.json()
        assert homo_data["success"] is True
        assert len(homo_data["homography_matrix"]) == 3

        test_img = np.full((240, 320, 3), 200, dtype=np.uint8)
        test_img[60:140, 80:110] = (20, 20, 150)
        test_img[70:150, 200:230] = (20, 20, 150)
        ok, buf = cv2.imencode(".jpg", test_img)
        assert ok

        img_res = await client.post(
            "/api/images/analyze",
            headers=headers,
            data={"camera_perspective": "FIXED_CCTV"},
            files={"file": ("test_static_crowd.jpg", io.BytesIO(buf.tobytes()), "image/jpeg")},
        )
        assert img_res.status_code == 200
        img_data = img_res.json()
        assert "id" in img_data
        assert "disclaimer" in img_data
        assert "Single-frame static observation" in img_data["disclaimer"]
        assert "heatmap_grid" in img_data
        assert len(img_data["heatmap_grid"]) > 0
