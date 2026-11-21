"""Phase 1 Full Stack E2E Operational Verification Script."""
import asyncio
from httpx import AsyncClient, ASGITransport
from app.main import create_app
from app.database.session import init_db, close_db

async def run_verification():
    await init_db()
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Health check
        res_health = await client.get("/api/health/")
        print("Health check status:", res_health.status_code, res_health.json())
        assert res_health.status_code == 200

        # 2. Copilot status
        res_copilot = await client.get("/api/copilot/status")
        print("Copilot status:", res_copilot.status_code, res_copilot.json())
        assert res_copilot.status_code == 200

        # 3. Create a spatial layout with 2 zones
        layout_data = {
            "name": "Championship Grand Arena",
            "description": "Full stadium floorplan with spectator sectors",
            "canvas_width": 1920,
            "canvas_height": 1080,
            "zones_data": [
                {
                    "id": "zone-grandstand-a",
                    "name": "North Grandstand",
                    "zone_type": "SEATING",
                    "capacity": 1200,
                    "color": "#06B6D4",
                    "polygon_points": [[0.05, 0.05], [0.95, 0.05], [0.95, 0.35], [0.05, 0.35]]
                },
                {
                    "id": "zone-field",
                    "name": "Field Floor Level",
                    "zone_type": "STAGE",
                    "capacity": 500,
                    "color": "#10B981",
                    "polygon_points": [[0.15, 0.45], [0.85, 0.45], [0.85, 0.85], [0.15, 0.85]]
                }
            ]
        }
        res_l = await client.post("/api/layouts/", json=layout_data)
        print("Create Layout status:", res_l.status_code)
        assert res_l.status_code == 201
        layout = res_l.json()
        layout_id = layout["id"]

        # 4. Create Task with frozen layout snapshot
        task_data = {
            "name": "Finals Tournament Surveillance",
            "location": "Sector 1A",
            "description": "Real-time crowd monitoring and bottleneck detection",
            "state": "READY",
            "layout_id": layout_id,
            "video_config": {
                "source_type": "CCTV_STREAM",
                "source_uri": "rtsp://192.168.1.100:554/live",
                "camera_perspective": "DRONE_TOPDOWN",
                "sample_fps": 2.0
            },
            "notes": "Monitor field egress corridors during halftime"
        }
        res_t = await client.post("/api/tasks/", json=task_data)
        print("Create Task status:", res_t.status_code)
        assert res_t.status_code == 201
        task = res_t.json()
        task_id = task["id"]
        assert len(task["layout_snapshot"]["zones_data"]) == 2
        print(f"Task created with ID {task_id} and {len(task['layout_snapshot']['zones_data'])} snapshot zones.")

        # 5. Query Copilot with Task context
        res_cop = await client.post("/api/copilot/query", json={
            "task_id": task_id,
            "message": "What zones and capacities are configured for this task?"
        })
        print("Copilot Query response:", res_cop.json()["response"][:120], "...")
        assert "North Grandstand" in res_cop.json()["response"]

        # 6. Lifecycle transition to PAUSED and back
        res_st = await client.post(f"/api/tasks/{task_id}/state", json={
            "state": "PAUSED",
            "reason": "Halftime scheduled pause"
        })
        assert res_st.status_code == 200
        assert res_st.json()["state"] == "PAUSED"
        print("Task state transitioned to PAUSED.")

        # 7. Audit history verification
        res_hist = await client.get(f"/api/tasks/{task_id}/history")
        hist = res_hist.json()
        print(f"Audit trail verified with {len(hist)} events: {[h['event_type'] for h in hist]}")
        assert len(hist) >= 2

        # 8. List tasks
        res_list = await client.get("/api/tasks/")
        assert res_list.status_code == 200
        print(f"Active task catalog has {len(res_list.json())} tasks.")

    await close_db()
    print("ALL PHASE 1 END-TO-END OPERATIONAL CHECKS PASSED PERFECTLY!")

if __name__ == "__main__":
    asyncio.run(run_verification())
