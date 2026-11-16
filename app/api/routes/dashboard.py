"""Rutas del dashboard ("Quick access"). Solo hablan con DashboardService y
DashboardInsightService.

El router no exige un permiso de dominio (ver PRIVATE_ROUTERS en app/main.py):
es la pagina de aterrizaje de cualquier usuario, y cada seccion se filtra por
permiso dentro del service. La interpretacion con IA si exige `ai`.
"""

from datetime import date
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import (
    get_current_permissions,
    get_current_timezone,
    get_current_user_id,
    get_dashboard_insight_service,
    get_dashboard_service,
    require,
)
from app.core.logging import get_logger
from app.integrations.openai_client import TextGenerationError
from app.schemas.dashboard import (
    DashboardPulseRead,
    DashboardTodayRead,
    PulseInterpretationRead,
    PulseInterpretationRequest,
)
from app.services.dashboard_insight_service import DashboardInsightService
from app.services.dashboard_service import DashboardService
from app.services.errors import AiNotConfiguredError, PulseWeekInFutureError
from app.services.permissions import Permission

logger = get_logger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/today", response_model=DashboardTodayRead)
def get_today(
    user_id: int = Depends(get_current_user_id),
    tz: ZoneInfo = Depends(get_current_timezone),
    permissions: frozenset[Permission] = Depends(get_current_permissions),
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardTodayRead:
    """Contexto del dia: eventos de hoy y ultimo registro de peso y English."""
    return service.today(user_id, tz, permissions)


@router.get("/pulse", response_model=DashboardPulseRead)
def get_pulse(
    week_start: date | None = Query(default=None, description="Cualquier dia de la semana"),
    user_id: int = Depends(get_current_user_id),
    tz: ZoneInfo = Depends(get_current_timezone),
    permissions: frozenset[Permission] = Depends(get_current_permissions),
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardPulseRead:
    """Semana sabado-viernes vs la anterior y el promedio de las 4 anteriores."""
    try:
        return service.pulse(user_id, tz, permissions, week_start)
    except PulseWeekInFutureError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post(
    "/pulse/interpretation",
    response_model=PulseInterpretationRead,
    dependencies=[Depends(require(Permission.AI))],
)
def interpret_pulse(
    payload: PulseInterpretationRequest,
    user_id: int = Depends(get_current_user_id),
    tz: ZoneInfo = Depends(get_current_timezone),
    permissions: frozenset[Permission] = Depends(get_current_permissions),
    service: DashboardService = Depends(get_dashboard_service),
    insight: DashboardInsightService = Depends(get_dashboard_insight_service),
) -> PulseInterpretationRead:
    """Una llamada al LLM con el pulso ya calculado. Gasta tokens."""
    try:
        pulse = service.pulse(user_id, tz, permissions, payload.week_start)
        return insight.interpret(user_id=user_id, pulse=pulse)
    except PulseWeekInFutureError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except AiNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except TextGenerationError as exc:
        # El detalle (key invalida, sin saldo, rate limit) va al log, no al cliente.
        logger.warning("Fallo el proveedor de IA: %s", exc)
        raise HTTPException(
            status_code=502, detail="No se pudo obtener respuesta del proveedor de IA"
        )
