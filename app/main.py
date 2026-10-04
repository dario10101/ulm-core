"""Punto de entrada de la API. Ejecutar con: uvicorn app.main:app --reload"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_current_user, require
from app.api.routes import (
    auth,
    calendar_events,
    checklists,
    cld_tasks,
    expenses,
    health,
    incomes,
    me,
    meals,
    weights,
)
from app.core.config import settings
from app.core.csrf import OriginCheckMiddleware
from app.core.logging import configure_logging, get_logger

# Importar los modelos para que sus tablas queden registradas en Base.metadata
from app.db.models import checklist as checklist_model  # noqa: F401
from app.db.models import cld_event as cld_event_model  # noqa: F401
from app.db.models import cld_task as cld_task_model  # noqa: F401
from app.db.models import cld_user_event as cld_user_event_model  # noqa: F401
from app.db.models import finance as finance_model  # noqa: F401
from app.db.models import meal as meal_model  # noqa: F401
from app.db.models import user as user_model  # noqa: F401
from app.db.models import weight as weight_model  # noqa: F401
from app.services.permissions import Permission

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # El esquema ya no se crea aca: lo maneja Alembic (`alembic upgrade head`).
    # create_all() solo creaba tablas faltantes, nunca alteraba las existentes,
    # que era justo el problema. Ver ulm-repository/how-to/alembic.md.
    # Los usuarios tampoco: se invitan con scripts/manage_users.py.
    configure_logging()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    OriginCheckMiddleware, allowed_origins=[*settings.cors_origins, settings.frontend_url]
)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    """La base rechazo una escritura por un constraint (unicidad, FK...).

    Los services validan antes de escribir y devuelven un error con mensaje
    propio; llegar aca significa que algo se les escapo, tipicamente dos
    requests simultaneos que pasaron la validacion a la vez. Es un conflicto
    con el estado actual (409), no un fallo interno (500). El detalle del
    constraint va al log, no al cliente.
    """
    logger.warning("Constraint violado en %s %s: %s", request.method, request.url.path, exc.orig)
    return JSONResponse(
        status_code=409,
        content={"detail": "La operacion choca con datos existentes. Recarga e intenta de nuevo."},
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


# Rutas sin sesion. Cualquier otra exige login: se monta con get_current_user
# a nivel de router, asi un endpoint nuevo queda protegido sin acordarse de
# nada. tests/test_auth.py falla si aparece una ruta privada sin esa dependencia.
PUBLIC_ROUTERS = (health.router, auth.router)

# Router privado -> permiso de dominio que exige (None: solo sesion). Igual
# que con la sesion, se exige a nivel de router: tests/test_permissions.py
# falla si una ruta privada (salvo /me) no pide ningun permiso.
PRIVATE_ROUTERS = (
    (me.router, None),
    (weights.router, Permission.WEIGHT),
    (meals.router, Permission.MEALS),
    (expenses.router, Permission.FINANCES),
    (incomes.router, Permission.FINANCES),
    (checklists.router, Permission.PLANNING),
    (cld_tasks.router, Permission.PLANNING),
    (calendar_events.router, Permission.PLANNING),
)

for router in PUBLIC_ROUTERS:
    app.include_router(router, prefix=settings.api_prefix)
for router, permission in PRIVATE_ROUTERS:
    dependencies = [Depends(get_current_user)]
    if permission is not None:
        dependencies.append(Depends(require(permission)))
    app.include_router(router, prefix=settings.api_prefix, dependencies=dependencies)


@app.get("/")
def root() -> dict:
    # Mensaje de bienvenida, confirma que la app arranco correctamente
    return {"message": f"{settings.app_name} esta corriendo"}
