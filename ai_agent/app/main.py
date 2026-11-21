"""CrowdVision AI Crowd Management Agent - FastAPI Application Entrypoint."""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.alerts import router as alerts_router
from app.api.routes.analyze import router as analyze_router
from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.api.routes.recommendations import router as recommendations_router
from app.api.websocket.handler import router as websocket_router
from app.config import get_settings
from app.dependencies import initialize_services, shutdown_services
from app.monitoring.logger import get_logger, setup_logging

settings = get_settings()
setup_logging(log_level=settings.app_log_level, json_logs=settings.is_production)
logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager handling resource initialization and teardown."""
    logger.info("Starting CrowdVision AI Agent service...", app_env=settings.app_env.value)
    await initialize_services()
    yield
    logger.info("Shutting down CrowdVision AI Agent service...")
    await shutdown_services()


app = FastAPI(
    title="CrowdVision AI Crowd Management Agent",
    description="Intelligent real-time crowd intelligence, risk assessment, and decision support engine.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS Middleware ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request Timing Middleware ────────────────────────────────────
@app.middleware("http")
async def add_process_time_header(request: Request, call_next) -> Response:
    start_time = time.monotonic()
    response = await call_next(request)
    process_time_ms = (time.monotonic() - start_time) * 1000.0
    response.headers["X-Process-Time-Ms"] = f"{process_time_ms:.2f}"
    return response


# ── Global Exception Handler ────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception during request processing", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred while processing crowd intelligence."},
    )


# ── Route Registration ──────────────────────────────────────────
app.include_router(health_router)
app.include_router(analyze_router)
app.include_router(alerts_router)
app.include_router(recommendations_router)
app.include_router(chat_router)
app.include_router(websocket_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )
