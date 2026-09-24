"""Punto de entrada de la API. Ejecutar con: uvicorn app.main:app --reload"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.routes import (
    calendar_events,
    checklists,
    cld_tasks,
    dummy,
    habits,
    health,
    weights,
)
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

# Importar los modelos para que sus tablas queden registradas en Base.metadata
from app.db.models import checklist as checklist_model  # noqa: F401
from app.db.models import cld_event as cld_event_model  # noqa: F401
from app.db.models import cld_task as cld_task_model  # noqa: F401
from app.db.models import cld_user_event as cld_user_event_model  # noqa: F401
from app.db.models import dummy as dummy_model  # noqa: F401
from app.db.models import user as user_model  # noqa: F401
from app.db.models import weight as weight_model  # noqa: F401
from app.db.seed import ensure_default_user
from app.db.session import SessionLocal

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # El esquema ya no se crea aca: lo maneja Alembic (`alembic upgrade head`).
    # create_all() solo creaba tablas faltantes, nunca alteraba las existentes,
    # que era justo el problema. Ver ulm-repository/how-to/alembic.md.
    configure_logging()
    try:
        db: Session = SessionLocal()
        try:
            ensure_default_user(db)
        finally:
            db.close()
    except OperationalError:
        # Postgres no disponible (ej. sin el contenedor local corriendo);
        # la app sigue arriba, pero los endpoints que usan la base fallaran
        # hasta levantarlo.
        logger.warning("No se pudo conectar a la base de datos al iniciar")
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Ultimo recurso para cualquier error no previsto.

    El traceback completo va al log (con el metodo y la ruta, para poder
    ubicarlo); al cliente solo le llega un mensaje generico, porque el detalle
    de un fallo interno no le sirve y puede filtrar informacion del sistema.
    """
    logger.exception("Error no controlado en %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Error interno del servidor"})


app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(habits.router, prefix=settings.api_prefix)
app.include_router(dummy.router, prefix=settings.api_prefix)
app.include_router(weights.router, prefix=settings.api_prefix)
app.include_router(checklists.router, prefix=settings.api_prefix)
app.include_router(cld_tasks.router, prefix=settings.api_prefix)
app.include_router(calendar_events.router, prefix=settings.api_prefix)


@app.get("/")
def root() -> dict:
    # Mensaje de bienvenida, confirma que la app arranco correctamente
    return {"message": f"{settings.app_name} esta corriendo"}
