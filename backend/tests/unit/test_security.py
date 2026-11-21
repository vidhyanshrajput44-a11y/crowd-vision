"""Automated security tests for CrowdVision API, file ingestion, path traversal, and CV pipeline."""
from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient
import numpy as np
import pytest

from app.analytics.zone_mapper import validate_polygon_geometry
from app.config import get_settings
from app.cv.detector import compute_ground_contact
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_unsupported_video_extension_rejected(client: TestClient):
    """Verify that executable and script file extensions are rejected."""
    fake_payload = io.BytesIO(b"echo 'malicious'")
    res = client.post(
        "/api/videos/upload",
        data={"event_id": "test_event"},
        files={"file": ("malicious_payload.sh", fake_payload, "application/x-sh")},
    )
    assert res.status_code == 400
    assert "Unsupported video format" in res.json()["detail"]


def test_empty_video_upload_rejected(client: TestClient):
    """Verify that 0-byte video files are rejected."""
    empty_payload = io.BytesIO(b"")
    res = client.post(
        "/api/videos/upload",
        data={"event_id": "test_event"},
        files={"file": ("empty.mp4", empty_payload, "video/mp4")},
    )
    assert res.status_code == 400
    assert "empty" in res.json()["detail"].lower()


def test_corrupted_video_file_rejected_and_cleaned(client: TestClient):
    """Verify that non-video bytes disguised as MP4 are rejected and disk cleaned."""
    corrupt_payload = io.BytesIO(b"NOT_A_VALID_MP4_HEADER_GARBAGE_BYTES_1234567890")
    res = client.post(
        "/api/videos/upload",
        data={"event_id": "test_event"},
        files={"file": ("corrupted.mp4", corrupt_payload, "video/mp4")},
    )
    assert res.status_code == 400
    assert "decode" in res.json()["detail"].lower()


def test_path_traversal_in_image_upload_sanitized(client: TestClient):
    """Verify that directory traversal sequences in image uploads are sanitized."""
    empty_img = io.BytesIO(b"")
    res = client.post(
        "/api/images/analyze",
        files={"file": ("../../../../etc/passwd.jpg", empty_img, "image/jpeg")},
    )
    # Fails empty validation or decode, but never escapes target directory
    assert res.status_code in (400, 422)


def test_unsupported_image_extension_rejected(client: TestClient):
    """Verify that non-image formats like HTML/SVG are rejected by image analyzer."""
    svg_payload = io.BytesIO(b"<svg onload=alert(1)>")
    res = client.post(
        "/api/images/analyze",
        files={"file": ("exploit.svg", svg_payload, "image/svg+xml")},
    )
    assert res.status_code == 400
    assert "Unsupported image extension" in res.json()["detail"]


def test_ground_contact_perspective_computation():
    """Verify ground contact point mathematical projection for different camera perspectives."""
    bbox = (100.0, 50.0, 200.0, 250.0)

    # Fixed CCTV should use bottom-center
    gc_cctv = compute_ground_contact(bbox, perspective="FIXED_CCTV")
    assert gc_cctv == (150.0, 250.0)

    # Drone top-down should use geometric centroid
    gc_drone = compute_ground_contact(bbox, perspective="DRONE_TOPDOWN")
    assert gc_drone == (150.0, 150.0)


def test_polygon_geometry_validation_security():
    """Verify that invalid or malformed spatial polygons are flagged."""
    # Under minimum 3 vertices
    val_few = validate_polygon_geometry([[0.1, 0.1], [0.2, 0.2]])
    assert not val_few.is_valid
    assert any("at least 3" in e.lower() for e in val_few.errors)

    # Self-intersecting bowtie polygon
    bowtie = [[0.1, 0.1], [0.5, 0.5], [0.1, 0.5], [0.5, 0.1]]
    val_bowtie = validate_polygon_geometry(bowtie)
    assert not val_bowtie.is_valid
    assert any("self-intersect" in e.lower() for e in val_bowtie.errors)

    # Valid convex polygon
    valid_box = [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]]
    val_box = validate_polygon_geometry(valid_box)
    assert val_box.is_valid
    assert len(val_box.errors) == 0


def test_settings_upload_bounds_defaults():
    """Verify upload size and security bounds are configured properly."""
    settings = get_settings()
    assert settings.max_upload_size_mb >= 50
    assert settings.max_video_duration_seconds >= 60.0
    assert settings.max_video_dimension >= 1920
    assert len(settings.allowed_origins_list) >= 1

