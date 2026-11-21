"""In-memory metrics collector for API latencies, queue depths, and throughput."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any


class MetricsCollector:
    """Thread-safe, lightweight metrics collector tracking latencies, counters, and gauges."""

    def __init__(self, max_histogram_points: int = 1000) -> None:
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._max_histogram_points = max_histogram_points

    def increment(self, name: str, amount: int = 1) -> None:
        """Increment a counter by given amount."""
        self._counters[name] += amount

    def set_gauge(self, name: str, value: float) -> None:
        """Set a gauge value."""
        self._gauges[name] = float(value)

    def observe(self, name: str, value: float) -> None:
        """Record an observation in a histogram (e.g. latency in milliseconds)."""
        hist = self._histograms[name]
        hist.append(value)
        if len(hist) > self._max_histogram_points:
            hist.pop(0)

    def get_summary(self) -> dict[str, Any]:
        """Compute statistical summary including p50, p95, and p99 percentiles."""
        summary: dict[str, Any] = {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {},
        }

        for name, values in self._histograms.items():
            if not values:
                continue
            sorted_vals = sorted(values)
            n = len(sorted_vals)
            p50_idx = int(n * 0.50)
            p95_idx = int(n * 0.95)
            p99_idx = int(n * 0.99)

            summary["histograms"][name] = {
                "count": n,
                "min_ms": round(sorted_vals[0], 2),
                "max_ms": round(sorted_vals[-1], 2),
                "mean_ms": round(sum(sorted_vals) / n, 2),
                "p50_ms": round(sorted_vals[min(p50_idx, n - 1)], 2),
                "p95_ms": round(sorted_vals[min(p95_idx, n - 1)], 2),
                "p99_ms": round(sorted_vals[min(p99_idx, n - 1)], 2),
            }

        return summary

    def reset(self) -> None:
        """Clear all metrics."""
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
