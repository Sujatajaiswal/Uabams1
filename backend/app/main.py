import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func

from app.config import settings
from app import models
from app.database import Base, SessionLocal, engine
from app.routers import (
    alerts, archive, calibration, config, dashboard, gateways, maintenance,
    route_files, sections, threshold, tms_export, trains,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uabams")

app = FastAPI(
    title="UABAMS Cloud API",
    description=(
        "Unattended Axle Box Acceleration Measurement System - cloud-side "
        "ingestion, processing, alerting and dashboard API for Indian Railways."
    ),
    version="1.0.0",
)

origins = ["*"] if settings.CORS_ORIGINS.strip() == "*" else [
    o.strip() for o in settings.CORS_ORIGINS.split(",")
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(archive.router)
app.include_router(dashboard.router)
app.include_router(threshold.router)
app.include_router(calibration.router)
app.include_router(alerts.router)
app.include_router(config.router)
app.include_router(gateways.router)
app.include_router(tms_export.router)
app.include_router(trains.router)
app.include_router(route_files.router)
app.include_router(sections.router)
app.include_router(maintenance.router)


@app.on_event("startup")
def on_startup():
    # Demo-friendly schema bootstrap. In a real production rollout this
    # would be replaced by Alembic migrations (see README).
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ensured.")

    if settings.SEED_ON_STARTUP:
        try:
            from app.seed import seed_if_empty

            seed_if_empty()
        except Exception as exc:  # pragma: no cover - seeding is best-effort
            logger.warning("Seed step skipped: %s", exc)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "service": "uabams-cloud-api"}


@app.get("/health/db", tags=["health"])
def database_health_check():
    db = SessionLocal()
    try:
        return {
            "status": "ok",
            "database": "postgresql" if settings.DATABASE_URL.startswith("postgresql") else "sqlite",
            "gatewaySessions": db.query(func.count(models.GatewaySession.id)).scalar() or 0,
            "alerts": db.query(func.count(models.Alert.id)).scalar() or 0,
            "gateways": db.query(func.count(models.Gateway.gateway_id)).scalar() or 0,
        }
    finally:
        db.close()


@app.get("/", tags=["health"])
def root():
    return {
        "service": "UABAMS Cloud API",
        "docs": "/docs",
        "health": "/health",
    }
