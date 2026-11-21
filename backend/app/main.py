"""CrowdVision Main Backend FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    alerts,
    analytics,
    auth,
    calibration,
    cameras,
    chat,
    copilot,
    events,
    health,
    images,
    layouts,
    recommendations,
    reports,
    tasks,
    venues,
    videos,
)
from app.api.websocket.handler import router as ws_router
from app.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.database.session import close_db, init_db

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    setup_logging(settings.app_log_level)

    # Ensure required upload directories exist
    settings.videos_dir.mkdir(parents=True, exist_ok=True)
    settings.floorplans_dir.mkdir(parents=True, exist_ok=True)
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    settings.images_dir.mkdir(parents=True, exist_ok=True)

    await init_db()

    # Auto-initialize Railway CCTV demonstration if video exists
    try:
        from app.scripts.setup_railway_demo import setup_railway_demo
        await setup_railway_demo()
    except Exception as e:
        logger.warning("Railway demo auto-init skipped", error=str(e))

    logger.info("CrowdVision Main Backend started", title=settings.app_name)

    yield

    await close_db()
    logger.info("CrowdVision Main Backend shutdown completed")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="AI-Powered Predictive Crowd Monitoring and Intelligent Crowd Management Platform",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_origin_regex=r"https://.*\.onrender\.com",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    uploads_root = settings.effective_storage_root / settings.upload_dir
    uploads_root.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(uploads_root)), name="uploads")

    # Mount API routers
    app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
    app.include_router(tasks.router, prefix="/api", tags=["Tasks"])
    app.include_router(copilot.router, prefix="/api", tags=["AI Copilot"])
    app.include_router(events.router, prefix="/api/events", tags=["Events"])
    app.include_router(venues.router, prefix="/api/venues", tags=["Venues & Zones"])
    app.include_router(layouts.router, prefix="/api", tags=["Venue Layouts"])
    app.include_router(calibration.router, prefix="/api", tags=["Camera Calibration"])
    app.include_router(cameras.router, prefix="/api/cameras", tags=["Cameras"])
    app.include_router(videos.router, prefix="/api/videos", tags=["Videos & Processing"])
    app.include_router(images.router, prefix="/api", tags=["Single Image Analysis"])
    app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics & Predictions"])
    app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"])
    app.include_router(recommendations.router, prefix="/api/recommendations", tags=["Recommendations"])
    app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
    app.include_router(chat.router, prefix="/api/chat", tags=["AI Analyst"])
    app.include_router(health.router, prefix="/api/health", tags=["Health"])
    app.include_router(health.router, prefix="/health", tags=["Health"])
    app.include_router(ws_router, tags=["WebSocket"])

    # Mount frontend static distribution if built
    from pathlib import Path
    dist_dir = settings.base_dir.parent / "frontend" / "dist"
    if not dist_dir.exists():
        dist_dir = Path("frontend/dist").resolve()

    if dist_dir.exists():
        assets_dir = dist_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/{full_path:path}", tags=["Frontend"])
        async def serve_spa_and_static(full_path: str):
            target = dist_dir / full_path
            if full_path and target.is_file():
                return FileResponse(target)
            return FileResponse(dist_dir / "index.html")
    else:
        @app.get("/", tags=["Root"])
        async def root():
            return {
                "app": settings.app_name,
                "version": "1.0.0",
                "docs": "/docs",
                "status": "running",
            }

    return app


app = create_app()
