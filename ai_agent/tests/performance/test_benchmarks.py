"""Performance, latency, and scalability benchmarks for CrowdVision AI Agent."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from app.core.event_context import EventContextManager
from app.dependencies import get_event_manager, get_orchestrator
from app.schemas.models import (
    CrowdDataInput,
    VenueConfig,
    ZoneConfig,
)


@pytest.fixture
def fifty_zone_event() -> str:
    """Create a scaled venue topology containing 50 distinct zones."""
    em = get_event_manager()
    event_id = "perf_event_50zones"

    zones = [
        ZoneConfig(
            zone_id=f"zone_{i:02d}",
            zone_name=f"Sector {i:02d}",
            capacity=400 + (i * 10),
            area_sqm=800.0,
            threshold_low=0.5,
            threshold_moderate=0.7,
            threshold_high=0.85,
            threshold_critical=0.95,
        )
        for i in range(50)
    ]
    venue = VenueConfig(
        venue_id="perf_stadium",
        venue_name="Grand Olympic Stadium",
        zones=zones,
        total_capacity=sum(z.capacity for z in zones),
    )
    em.register_event(event_id, "Olympic Finals 2026", venue)
    return event_id


@pytest.mark.asyncio
async def test_benchmark_fifty_concurrent_zones(fifty_zone_event: str):
    """Benchmark end-to-end batch processing of 50 simultaneous zones."""
    orchestrator = get_orchestrator()
    now = datetime.now(timezone.utc)

    # 50 zones analytical updates
    batch = [
        CrowdDataInput(
            event_id=fifty_zone_event,
            venue_id="perf_stadium",
            zone_id=f"zone_{i:02d}",
            timestamp=now,
            people_count=200 + (i * 5),
            current_occupancy=(200 + (i * 5)) / (400 + (i * 10)),
            inflow_rate=12.0,
            outflow_rate=8.0,
            movement_speed=1.1,
            predicted_occupancy=0.75,
            forecast_horizon_seconds=300,
            forecast_confidence=0.82,
        )
        for i in range(50)
    ]

    # Warmup cycle
    await orchestrator.process_batch(batch[:5])

    # Benchmarked run
    start = time.perf_counter()
    result = await orchestrator.process_batch(batch)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    print(f"\n[BENCHMARK] 50 Zones Processed in {elapsed_ms:.2f} ms ({elapsed_ms/50:.3f} ms/zone)")

    assert result.zones_analyzed == 50
    assert len(result.risk_assessments) == 50
    # Must comfortably meet high-performance throughput targets
    assert elapsed_ms < 200.0  # < 200ms total for 50 zones (< 4ms per zone)


@pytest.mark.asyncio
async def test_benchmark_api_analyze_latency(async_client: AsyncClient, fifty_zone_event: str):
    """Benchmark API round-trip latency over HTTP."""
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        "data": [
            {
                "event_id": fifty_zone_event,
                "venue_id": "perf_stadium",
                "zone_id": f"zone_{i:02d}",
                "timestamp": now_iso,
                "people_count": 280,
                "current_occupancy": 0.70,
                "inflow_rate": 10.0,
                "outflow_rate": 8.0,
            }
            for i in range(10)
        ]
    }

    latencies = []
    for _ in range(15):
        t0 = time.perf_counter()
        res = await async_client.post("/api/v1/agent/analyze", json=payload)
        t1 = time.perf_counter()
        assert res.status_code == 200
        latencies.append((t1 - t0) * 1000.0)

    # Sort latencies
    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[int(len(latencies) * 0.95)]

    print(f"\n[BENCHMARK HTTP] 10 Zones API Round-trip: p50={p50:.2f}ms, p95={p95:.2f}ms")
    assert p50 < 60.0  # sub-60ms p50 over HTTP transport
