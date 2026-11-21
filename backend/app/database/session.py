"""Async SQLAlchemy database engine, session dependency, and initial seed helper."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.core.logging import get_logger
from app.database.models import (
    Base,
    Camera,
    Event,
    User,
    Venue,
    VenueLayout,
    Zone,
    ZoneCapacity,
)

logger = get_logger("database.session")

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


async def init_db() -> None:
    global _engine, _session_factory
    from pathlib import Path
    settings = get_settings()
    url = settings.database_url

    # Normalize Render PostgreSQL connection strings to asyncpg
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    # Route SQLite to persistent data directory if configured
    if "sqlite" in url and settings.data_dir:
        p_dir = Path(settings.data_dir).resolve()
        p_dir.mkdir(parents=True, exist_ok=True)
        db_file = p_dir / "crowdvision_main.db"
        url = f"sqlite+aiosqlite:///{db_file}"

    if "sqlite" in url:
        _engine = create_async_engine(url, echo=False, future=True)
    else:
        _engine = create_async_engine(
            url,
            echo=False,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            future=True,
        )

    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        columns_to_migrate = (
            ("layout_id", "VARCHAR(36)", "processing_jobs"),
            ("camera_perspective", "VARCHAR(32) DEFAULT 'FIXED_CCTV'", "processing_jobs"),
            ("perspective", "VARCHAR(32) DEFAULT 'FIXED_CCTV'", "cameras"),
            ("is_moving_camera", "BOOLEAN DEFAULT 0", "cameras"),
            ("layout_id", "VARCHAR(36)", "cameras"),
            ("calibration_data", "JSON DEFAULT '{}'", "cameras"),
            ("crowd_increase_pct", "FLOAT DEFAULT 0.0", "crowd_metrics"),
            ("capacity_utilization_pct", "FLOAT DEFAULT 0.0", "crowd_metrics"),
            ("predicted_change_pct", "FLOAT DEFAULT 0.0", "predictions"),
            ("scale_factor", "FLOAT", "venue_layouts"),
            ("background_image_url", "VARCHAR(512)", "venue_layouts"),
            ("calibration_homography", "JSON", "venue_layouts"),
        )
        for col, col_type, tbl in columns_to_migrate:
            try:
                await conn.exec_driver_sql(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_type};")
            except Exception:
                pass

    await _seed_initial_data()
    logger.info("Main backend database initialized", url=url.split("@")[-1])


async def close_db() -> None:
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if _session_factory is None:
        await init_db()
    assert _session_factory is not None
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory, _engine
    if _session_factory is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=getattr(settings, "db_echo", False),
            future=True,
            connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
        )
        _session_factory = async_sessionmaker(bind=_engine, expire_on_commit=False, class_=AsyncSession)
    return _session_factory


async def _seed_initial_data() -> None:
    from app.core.security import hash_password

    assert _session_factory is not None
    async with _session_factory() as session:
        existing_user = (await session.execute(select(User).limit(1))).scalar_one_or_none()
        if not existing_user:
            users = [
                User(
                    email="admin@crowdvision.io",
                    full_name="System Administrator",
                    password_hash=hash_password("admin123"),
                    role="ADMIN",
                ),
                User(
                    email="manager@crowdvision.io",
                    full_name="Event Operations Manager",
                    password_hash=hash_password("manager123"),
                    role="EVENT_MANAGER",
                ),
                User(
                    email="security@crowdvision.io",
                    full_name="Security Control Officer",
                    password_hash=hash_password("security123"),
                    role="SECURITY_OPERATOR",
                ),
            ]
            session.add_all(users)

        existing_venue = (await session.execute(select(Venue).limit(1))).scalar_one_or_none()
        if not existing_venue:
            venue = Venue(
                id="venue-central-arena",
                name="Central Park Amphitheatre",
                location="Downtown Convention District",
                total_capacity=1200,
                is_calibrated=False,
            )
            session.add(venue)
            await session.flush()

            default_zones = [
                (
                    "zone-main-stage",
                    "Main Stage",
                    "STAGE",
                    [[0.02, 0.04], [0.52, 0.04], [0.52, 0.54], [0.02, 0.54]],
                    "#0d9488",
                    40,
                    250.0,
                    False,
                    False,
                    False,
                ),
                (
                    "zone-entrance-a",
                    "Entrance A",
                    "ENTRANCE",
                    [[0.54, 0.04], [0.98, 0.04], [0.98, 0.48], [0.54, 0.48]],
                    "#2563eb",
                    25,
                    120.0,
                    True,
                    False,
                    False,
                ),
                (
                    "zone-food-court",
                    "Food Court",
                    "FOOD_COURT",
                    [[0.02, 0.56], [0.52, 0.56], [0.52, 0.96], [0.02, 0.96]],
                    "#d97706",
                    30,
                    180.0,
                    False,
                    False,
                    False,
                ),
                (
                    "zone-exit-corridor",
                    "Emergency Corridor",
                    "CORRIDOR",
                    [[0.54, 0.5], [0.98, 0.5], [0.98, 0.96], [0.54, 0.96]],
                    "#dc2626",
                    20,
                    100.0,
                    False,
                    True,
                    True,
                ),
            ]

            for zid, zname, ztype, poly, color, cap, area, is_in, is_out, is_emg in default_zones:
                z = Zone(
                    id=zid,
                    venue_id=venue.id,
                    name=zname,
                    zone_type=ztype,
                    polygon_points=poly,
                    color=color,
                    adjacent_zone_ids=[dz[0] for dz in default_zones if dz[0] != zid],
                    is_entry=is_in,
                    is_exit=is_out,
                    is_emergency_exit=is_emg,
                )
                session.add(z)
                await session.flush()
                session.add(
                    ZoneCapacity(
                        zone_id=z.id,
                        max_capacity=cap,
                        area_sqm=area,
                        is_physically_calibrated=False,
                        threshold_low=0.45,
                        threshold_moderate=0.65,
                        threshold_high=0.82,
                        threshold_critical=0.95,
                    )
                )

            event = Event(
                id="event-festival-2026",
                venue_id=venue.id,
                name="Metro Music & Tech Festival 2026",
                event_type="MUSIC_FESTIVAL",
                status="ACTIVE",
                expected_attendance=1000,
                settings={"sample_fps": 2.0, "forecast_horizons": [60, 180, 300]},
            )
            session.add(event)
            await session.flush()

            layout = VenueLayout(
                id="layout-amphitheatre-default",
                venue_id=venue.id,
                event_id=event.id,
                name="Standard 4-Zone Festival Grid",
                description="Default venue layout dividing Main Stage, Entrance A, Food Court, and Emergency Corridor.",
                version=1,
                is_active=True,
                scale_pixels_per_meter=18.5,
                canvas_width=1920,
                canvas_height=1080,
                zones_data=[
                    {
                        "id": "zone-main-stage",
                        "name": "Main Stage",
                        "zone_type": "STAGE",
                        "polygon_points": [[0.02, 0.04], [0.52, 0.04], [0.52, 0.54], [0.02, 0.54]],
                        "color": "#0d9488",
                        "capacity": 40,
                        "area_sqm": 250.0,
                        "is_physically_calibrated": False,
                        "threshold_low": 0.45,
                        "threshold_moderate": 0.65,
                        "threshold_high": 0.82,
                        "threshold_critical": 0.95,
                        "monitoring_priority": "HIGH",
                        "description": "Primary performance grounds and front-of-stage crowd gathering area",
                        "is_entry": False,
                        "is_exit": False,
                        "is_emergency_exit": False,
                        "adjacent_zone_ids": ["zone-entrance-a", "zone-food-court", "zone-exit-corridor"],
                    },
                    {
                        "id": "zone-entrance-a",
                        "name": "Entrance A",
                        "zone_type": "ENTRANCE",
                        "polygon_points": [[0.54, 0.04], [0.98, 0.04], [0.98, 0.48], [0.54, 0.48]],
                        "color": "#2563eb",
                        "capacity": 25,
                        "area_sqm": 120.0,
                        "is_physically_calibrated": False,
                        "threshold_low": 0.45,
                        "threshold_moderate": 0.65,
                        "threshold_high": 0.82,
                        "threshold_critical": 0.95,
                        "monitoring_priority": "ELEVATED",
                        "description": "Main visitor security check and ticket validation portal",
                        "is_entry": True,
                        "is_exit": False,
                        "is_emergency_exit": False,
                        "adjacent_zone_ids": ["zone-main-stage", "zone-food-court", "zone-exit-corridor"],
                    },
                    {
                        "id": "zone-food-court",
                        "name": "Food Court",
                        "zone_type": "FOOD_COURT",
                        "polygon_points": [[0.02, 0.56], [0.52, 0.56], [0.52, 0.96], [0.02, 0.96]],
                        "color": "#d97706",
                        "capacity": 30,
                        "area_sqm": 180.0,
                        "is_physically_calibrated": False,
                        "threshold_low": 0.45,
                        "threshold_moderate": 0.65,
                        "threshold_high": 0.82,
                        "threshold_critical": 0.95,
                        "monitoring_priority": "ROUTINE",
                        "description": "Concessions, hydration, and visitor dining area",
                        "is_entry": False,
                        "is_exit": False,
                        "is_emergency_exit": False,
                        "adjacent_zone_ids": ["zone-main-stage", "zone-entrance-a", "zone-exit-corridor"],
                    },
                    {
                        "id": "zone-exit-corridor",
                        "name": "Emergency Corridor",
                        "zone_type": "CORRIDOR",
                        "polygon_points": [[0.54, 0.5], [0.98, 0.5], [0.98, 0.96], [0.54, 0.96]],
                        "color": "#dc2626",
                        "capacity": 20,
                        "area_sqm": 100.0,
                        "is_physically_calibrated": False,
                        "threshold_low": 0.45,
                        "threshold_moderate": 0.65,
                        "threshold_high": 0.82,
                        "threshold_critical": 0.95,
                        "monitoring_priority": "IMMEDIATE",
                        "description": "Dedicated emergency exit corridor that must maintain unobstructed egress",
                        "is_entry": False,
                        "is_exit": True,
                        "is_emergency_exit": True,
                        "adjacent_zone_ids": ["zone-main-stage", "zone-entrance-a", "zone-food-court"],
                    },
                ],
            )
            session.add(layout)
            await session.flush()

            session.add(
                Camera(
                    id="cam-main-overview",
                    event_id=event.id,
                    name="Cam-01 Main Plaza Overhead",
                    location="North Truss Rig",
                    input_type="RECORDED_VIDEO",
                    perspective="ELEVATED_OBLIQUE",
                    is_moving_camera=False,
                    layout_id=layout.id,
                    status="IDLE",
                    associated_zone_ids=["zone-main-stage", "zone-entrance-a", "zone-food-court", "zone-exit-corridor"],
                )
            )

        await session.commit()
