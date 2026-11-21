"""Automated performance and latency benchmark suite for CrowdVision AI Agent."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime, timezone

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.orchestrator import AgentOrchestrator
from app.dependencies import (
    get_event_manager,
    get_orchestrator,
    initialize_services,
    shutdown_services,
)
from app.schemas.models import (
    CrowdDataInput,
    MovementDirection,
    VenueConfig,
    ZoneConfig,
)


async def run_benchmarks() -> dict:
    """Run comprehensive performance tests and return timing statistics."""
    print("=" * 70)
    print("CROWDVISION AI AGENT - PRODUCTION BENCHMARK RUNNER")
    print("=" * 70)

    await initialize_services()
    em = get_event_manager()
    orchestrator = get_orchestrator()

    # 1. Setup multi-zone venue (60 zones)
    event_id = "bench_event_60zones"
    num_zones = 60
    zones = [
        ZoneConfig(
            zone_id=f"zone_{i:02d}",
            zone_name=f"Arena Zone {i:02d}",
            capacity=500,
            area_sqm=1000.0,
            threshold_low=0.5,
            threshold_moderate=0.7,
            threshold_high=0.85,
            threshold_critical=0.95,
        )
        for i in range(num_zones)
    ]
    venue = VenueConfig(
        venue_id="bench_stadium",
        venue_name="Benchmark Stadium",
        zones=zones,
        total_capacity=500 * num_zones,
    )
    em.register_event(event_id, "Grand Final Benchmark", venue)

    # 2. Warmup
    print("Executing warmup cycles...")
    now = datetime.now(timezone.utc)
    for _ in range(5):
        sample_batch = [
            CrowdDataInput(
                event_id=event_id,
                venue_id="bench_stadium",
                zone_id=f"zone_{i:02d}",
                timestamp=now,
                people_count=200,
            )
            for i in range(10)
        ]
        await orchestrator.process_batch(sample_batch)

    # 3. Batch Scaling Latency Benchmarks (10, 25, 50, 60 zones)
    batch_sizes = [1, 5, 10, 25, 50, 60]
    bench_results = {}

    for size in batch_sizes:
        latencies = []
        for iteration in range(25):
            now = datetime.now(timezone.utc)
            batch = [
                CrowdDataInput(
                    event_id=event_id,
                    venue_id="bench_stadium",
                    zone_id=f"zone_{i:02d}",
                    timestamp=now,
                    people_count=150 + (i * 5),
                    current_occupancy=(150 + (i * 5)) / 500.0,
                    inflow_rate=12.0,
                    outflow_rate=8.0,
                    movement_direction=MovementDirection.INWARD,
                    movement_speed=1.1,
                    predicted_occupancy=min(1.0, (150 + (i * 5)) / 500.0 + 0.1),
                    forecast_horizon_seconds=300,
                    forecast_confidence=0.82,
                )
                for i in range(size)
            ]

            t0 = time.perf_counter()
            res = await orchestrator.process_batch(batch)
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000.0)

        latencies.sort()
        n = len(latencies)
        p50 = latencies[n // 2]
        p95 = latencies[int(n * 0.95)]
        p99 = latencies[int(n * 0.99)]
        mean = sum(latencies) / n

        bench_results[f"batch_{size}"] = {
            "batch_size": size,
            "mean_ms": round(mean, 2),
            "p50_ms": round(p50, 2),
            "p95_ms": round(p95, 2),
            "p99_ms": round(p99, 2),
            "per_zone_ms": round(mean / size, 3),
        }

        print(
            f"Batch {size:2d} zones: mean={mean:6.2f}ms | p50={p50:6.2f}ms | "
            f"p95={p95:6.2f}ms | p99={p99:6.2f}ms | {mean/size:6.3f}ms/zone"
        )

    await shutdown_services()
    return bench_results


if __name__ == "__main__":
    asyncio.run(run_benchmarks())
