"""Endpoint de salud, util para verificar que el servicio esta arriba."""

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict:
    # Respuesta dummy, sirve como smoke test del despliegue
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}
