"""End-to-end integration test covering auth, CRUD, video upload & processing, analytics, alerts, chat, and reports."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database.session import close_db, init_db
from app.main import app
from scripts.generate_test_video import generate_synthetic_crowd_video


@pytest_asyncio.fixture(autouse=True)
async def _setup_db():
    await init_db()
    yield
    await close_db()


@pytest.mark.asyncio
async def test_full_platform_e2e_workflow(tmp_path: Path):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Health check
        h = await client.get("/api/health/")
        assert h.status_code == 200
        assert h.json()["database"] == "healthy"

        # 2. Authentication
        login_res = await client.post(
            "/api/auth/login",
            json={"email": "admin@crowdvision.io", "password": "admin123"},
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 3. User info
        me_res = await client.get("/api/auth/me", headers=headers)
        assert me_res.status_code == 200
        assert me_res.json()["role"] == "ADMIN"

        # 4. List Events
        events_res = await client.get("/api/events/", headers=headers)
        assert events_res.status_code == 200
        events = events_res.json()
        assert len(events) >= 1
        # Target an isolated event that is not the permanent railway demonstration task
        non_demo_events = [e for e in events if e.get("id") != "task_railway_cctv_analysis"]
        target_event = non_demo_events[0] if non_demo_events else events[0]
        event_id = target_event["id"]
        venue_id = target_event["venue_id"]

        # 5. Venue & Zones
        venue_res = await client.get(f"/api/venues/{venue_id}", headers=headers)
        assert venue_res.status_code == 200
        venue = venue_res.json()
        assert len(venue["zones"]) >= 1

        # 6. Generate Synthetic Crowd Video
        video_file = tmp_path / "e2e_crowd.mp4"
        generate_synthetic_crowd_video(output_path=video_file, duration_sec=4.0, fps=8.0)

        # 7. Upload Video
        with open(video_file, "rb") as f:
            up_res = await client.post(
                "/api/videos/upload",
                headers=headers,
                data={
                    "event_id": event_id,
                    "sample_fps": "2.0",
                    "auto_process": "false",
                },
                files={"file": ("e2e_crowd.mp4", f, "video/mp4")},
            )
        assert up_res.status_code == 200
        upload_data = up_res.json()
        video_id = upload_data["video_id"]
        assert upload_data["duration_seconds"] > 0

        # 8. Start Processing
        proc_res = await client.post(
            f"/api/videos/{video_id}/process",
            headers=headers,
            json={"sample_fps": 2.0},
        )
        assert proc_res.status_code in (200, 201)
        assert proc_res.json()["status"] in ("QUEUED", "RUNNING")

        # 9. Wait for Background Video Processing Job
        job_status = "QUEUED"
        job_data = {}
        for _ in range(80):
            await asyncio.sleep(0.25)
            j_res = await client.get(f"/api/videos/jobs/{video_id}", headers=headers)
            assert j_res.status_code == 200
            job_data = j_res.json()
            job_status = job_data["status"]
            if job_status in ("COMPLETED", "FAILED", "STOPPED"):
                break

        assert job_status == "COMPLETED", f"Job ended with status {job_status}: {job_data}"
        assert job_data["frames_processed"] >= 1
        assert job_data["max_people_detected"] >= 0

        # 10. Frame Detections & Heatmap
        det_res = await client.get(f"/api/analytics/detections/{video_id}?ts=2.0", headers=headers)
        assert det_res.status_code == 200
        assert "heatmap_grid" in det_res.json()

        hm_res = await client.get(f"/api/analytics/heatmap/{video_id}?ts=2.0", headers=headers)
        assert hm_res.status_code == 200
        hm_data = hm_res.json()
        assert "60" in hm_data["predicted"]
        assert "180" in hm_data["predicted"]
        assert "300" in hm_data["predicted"]

        # 11. Predictions across horizons
        pred_res = await client.get(
            f"/api/analytics/predictions/{video_id}",
            headers=headers,
        )
        assert pred_res.status_code == 200
        assert len(pred_res.json()) >= 1

        # 12. Zone Telemetry Summary
        summary_res = await client.get(f"/api/analytics/zones/{event_id}/summary", headers=headers)
        assert summary_res.status_code == 200
        summary = summary_res.json()
        assert len(summary["zones"]) >= 1
        assert len(summary["trend_series"]) >= 1

        # 13. AI Agent Chat Query
        chat_res = await client.post(
            "/api/chat/",
            headers=headers,
            json={
                "event_id": event_id,
                "message": "What is the current crowd status and forecast?",
            },
        )
        assert chat_res.status_code == 200
        assert "response" in chat_res.json()

        # 14. Report Generation & CSV Export
        rep_res = await client.post(
            "/api/reports/generate",
            headers=headers,
            json={"event_id": event_id, "job_id": video_id},
        )
        assert rep_res.status_code in (200, 201)
        report_id = rep_res.json()["id"]
        assert "summary_data" in rep_res.json()

        csv_res = await client.get(f"/api/reports/{report_id}/export.csv", headers=headers)
        assert csv_res.status_code == 200
        assert "Zone Name" in csv_res.text
