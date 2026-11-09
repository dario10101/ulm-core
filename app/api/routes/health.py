"""Endpoint de salud, util para verificar que el servicio esta arriba."""

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict:
    # Smoke test del despliegue: `version` dice que revision esta respondiendo.
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
        "version": settings.app_version,
    }
