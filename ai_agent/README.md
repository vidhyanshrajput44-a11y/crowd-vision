# CrowdVision AI Crowd Management Agent

> High-performance, modular, production-ready AI crowd intelligence and decision-support layer for the CrowdVision platform.

---

## 1. System Overview

CrowdVision AI Agent is an independent, real-time intelligence service designed to sit atop computer vision processing pipelines (OpenCV, YOLO, ByteTrack, density estimators). It receives structured analytics and provides:

- **Deterministic Risk Assessment**: Multi-factor risk engine with calibrated zone thresholds and temporal hysteresis to prevent false alarms.
- **Predictive Intelligence Interpretation**: Contextual explanation of multi-horizon forecasts, identifying emerging hotspots before physical saturation occurs.
- **Intelligent Action Recommendations**: Prioritized, role-targeted recommendations for stewards, security, and operations, strictly enforcing human approval.
- **Alert Lifecycle Management**: Automated generation, deduplication, escalation, acknowledgement, and resolution with complete audit logging.
- **Conversational Crowd Analyst**: Natural-language operational assistant powered by Google Gemini and backed by authoritative structured tool calling with deterministic offline fallback.
- **Sub-Millisecond Processing**: Pure async architecture delivering ~0.17 ms per zone analysis, processing 50 concurrent zones in ~8.5 ms.

---

## 2. Architecture

```
                 ┌────────────────────────────────┐
                 │  OpenCV / YOLO / ByteTrack     │
                 │  Density & Forecast Pipeline   │
                 └──────────────┬─────────────────┘
                                │ POST /api/v1/agent/analyze (JSON)
                                ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      CrowdVision AI Agent Service                      │
│                                                                        │
│  ┌───────────────────────┐           ┌──────────────────────────────┐  │
│  │ Ingestion & Dedup     │           │ Event Context Manager        │  │
│  │ (Bounded Queue)       │           │ (Strict Event Isolation)     │  │
│  └───────────┬───────────┘           └──────────────┬───────────────┘  │
│              │                                      │                  │
│              ▼                                      ▼                  │
│  ┌───────────────────────┐           ┌──────────────────────────────┐  │
│  │ Crowd Intelligence    │──────────►│ Risk Assessment Engine       │  │
│  │ Analyzer              │           │ (5 Levels, Hysteresis)       │  │
│  └───────────────────────┘           └──────────────┬───────────────┘  │
│                                                     │                  │
│                                                     ▼                  │
│  ┌───────────────────────┐           ┌──────────────────────────────┐  │
│  │ Prediction            │──────────►│ Recommendation Engine        │  │
│  │ Interpreter           │           │ (Context-Aware Catalog)      │  │
│  └───────────────────────┘           └──────────────┬───────────────┘  │
│                                                     │                  │
│                                                     ▼                  │
│  ┌───────────────────────┐           ┌──────────────────────────────┐  │
│  │ Conversational LLM    │           │ Alert Lifecycle Manager      │  │
│  │ (Gemini + Tools)      │           │ (Escalation & State Machine) │  │
│  └───────────────────────┘           └──────────────┬───────────────┘  │
│                                                     │                  │
│                                                     ▼                  │
│                                      ┌──────────────────────────────┐  │
│                                      │ WebSocket & REST Dispatcher  │  │
│                                      └──────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Performance & Empirical Benchmarks

The system was benchmarked on development hardware under simulated production loads with 60 simultaneous active zones.

| Workload | Mean Latency | Median (p50) | 95th Percentile (p95) | 99th Percentile (p99) | Throughput Rate |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1 Zone** | **0.16 ms** | 0.15 ms | 0.23 ms | 0.27 ms | 6,250 zones/sec |
| **5 Zones** | **1.06 ms** | 1.12 ms | 2.01 ms | 2.13 ms | 4,710 zones/sec |
| **10 Zones** | **1.74 ms** | 1.59 ms | 2.88 ms | 3.19 ms | 5,740 zones/sec |
| **25 Zones** | **3.93 ms** | 3.90 ms | 4.73 ms | 5.43 ms | 6,360 zones/sec |
| **50 Zones** | **8.58 ms** | 8.45 ms | 11.12 ms | 11.81 ms | 5,820 zones/sec |
| **60 Zones** | **12.48 ms** | 12.50 ms | 14.10 ms | 18.66 ms | 4,800 zones/sec |

### Target Verification:
- **API Response Latency**: Target < 50 ms p95 -> **Actual: ~8.5 ms (50 zones)**
- **Risk Assessment Latency**: Target < 10 ms -> **Actual: ~1.2 ms**
- **Alert Generation Latency**: Target < 20 ms -> **Actual: ~1.8 ms**
- **Per-Zone Compute Cost**: Target < 5 ms -> **Actual: ~0.17 ms/zone**

---

## 4. Key Subsystems

### A. Real-Time Crowd Intelligence (`app/intelligence/crowd_analyzer.py`)
- Rolling time-series window tracking per zone.
- Continuous linear regression slope calculation detecting accumulation velocity (`rapid_increase`, `increasing`, `stable`, `decreasing`, `rapid_decrease`).
- Statistical anomaly detection (> 2σ above rolling baseline).
- Physical bottleneck detection (inflow >> outflow at elevated occupancy, or movement speed < 0.30 m/s).
- Counterflow and opposing stream collision detection.
- Continuous dwell / congestion duration tracking.

### B. Advanced Risk Assessment (`app/intelligence/risk_assessment.py`)
- Evaluates 8 simultaneous risk dimensions against zone-calibrated thresholds:
  1. Occupancy ratio
  2. Physical density (people/m²)
  3. Net flow dynamics
  4. Accumulation velocity
  5. Predictive forecasts
  6. Congestion duration
  7. Movement irregularities
  8. Adjacent zone spillover
- **Hysteresis Guarantee**: Escalation requires 3 consecutive cycles; de-escalation requires 5 consecutive cycles. Prevents false alarms from transient sensor noise.

### C. Predictive Intelligence Interpreter (`app/intelligence/prediction_interpreter.py`)
- Interprets single and multi-horizon forecasts (1m, 3m, 5m, etc.).
- Flags **Emerging Hotspots** (zones currently nominal but projected to breach safe thresholds).
- Identifies low-confidence forecasts (< 50%) and conflicting model outputs.
- Never presents probabilistic forecasts as certainties.

### D. Intelligent Recommendation Engine (`app/recommendations/recommendation_engine.py`)
- Scenario-driven action catalog covering high occupancy, rapid surge, entrance bottlenecks, counterflow, sustained dwell, and emerging hotspots.
- Role-targeted: Operations, Security, Management, Medical.
- Strict safety gate: All physical actions require human operational approval (`requires_human_approval=True`).
- Time-based deduplication window suppresses identical recommendations within 5 minutes.

### E. Alert Lifecycle Manager (`app/alerts/alert_manager.py`)
- Full state machine: `NEW` -> `ACKNOWLEDGED` -> `IN_PROGRESS` -> `RESOLVED` / `DISMISSED`.
- Automated priority escalation for unacknowledged alerts after 300 seconds.
- Immutable audit log of all state transitions and human interventions.

### F. Conversational AI Crowd Analyst (`app/llm/provider.py`)
- Natural-language interface powered by Google Gemini (e.g. `gemini-2.5-flash`).
- 10 structured tools querying live state directly without executing arbitrary commands.
- **Resilient Fallback Mode**: If the LLM provider is offline or unconfigured, the system continues serving deterministic natural-language answers derived from authoritative tools without interruption.

---

## 5. Quickstart & Installation

### Option A: Local Python Execution

```bash
# 1. Clone and navigate to service directory
cd "crowd vision/ai_agent"

# 2. Configure environment
cp .env.example .env

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8100 --reload
```

Interactive documentation is immediately accessible at:
- Swagger UI: `http://localhost:8100/docs`
- ReDoc: `http://localhost:8100/redoc`

---

### Option B: Docker Compose Deployment

```bash
# Build and start PostgreSQL, Redis, and AI Agent
docker-compose up -d --build

# View container logs
docker-compose logs -f agent
```

---

## 6. Running Tests & Benchmarks

```bash
# Run complete test suite (33 tests)
python -m pytest tests -v

# Run performance benchmark suite
python scripts/benchmark.py
```

---

## 7. REST API & WebSocket Reference

### Analytics & Ingestion
- `POST /api/v1/agent/events` — Register event and venue zone topology.
- `POST /api/v1/agent/analyze` — Ingest batch crowd analytics snapshots.
- `GET /api/v1/agent/zones/{zone_id}/analysis?event_id={id}` — Retrieve detailed analytical dossier for a zone.

### Alert Management
- `GET /api/v1/agent/alerts?event_id={id}` — List active or filtered alerts.
- `POST /api/v1/agent/alerts/{alert_id}/acknowledge` — Acknowledge an alert.
- `POST /api/v1/agent/alerts/{alert_id}/resolve` — Mark alert resolved with resolution notes.
- `GET /api/v1/agent/alerts/{alert_id}/history` — View chronological audit history.

### Recommendations & Assistant
- `GET /api/v1/agent/recommendations?event_id={id}` — List active recommendations.
- `POST /api/v1/agent/chat` — Conversational query interface.
- `POST /api/v1/agent/feedback` — Submit operator feedback on agent insights.

### Real-Time Streaming (WebSockets)
- `ws://localhost:8100/ws/{event_id}` — Event-scoped live stream (alerts, risk changes, recommendations).
- `ws://localhost:8100/ws` — Global broadcast channel.

### System Telemetry
- `GET /health` — Diagnostic health check.
- `GET /api/v1/agent/status` — Operational status and backlogs.
- `GET /api/v1/agent/metrics` — Latency percentiles (p50, p95, p99).

---

## 8. License

Proprietary — Developed for CrowdVision Platform.
