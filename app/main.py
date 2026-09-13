"""Punto de entrada de la API. Ejecutar con: uvicorn app.main:app --reload"""

from fastapi import FastAPI

from app.api.routes import habits, health
from app.core.config import settings

app = FastAPI(title=settings.app_name)

app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(habits.router, prefix=settings.api_prefix)


@app.get("/")
def root() -> dict:
    # Mensaje de bienvenida, confirma que la app arranco correctamente
    return {"message": f"{settings.app_name} esta corriendo"}
