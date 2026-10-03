"""Login con Google y logout. Son las unicas rutas (junto con health) que no
exigen sesion: ver PUBLIC_ROUTES en app/main.py.

Las dos de Google son navegaciones del navegador, no fetch: terminan en
redirect (a Google, o de vuelta al front). Un error de login nunca responde
JSON: vuelve al front en /login?error=<code> para que muestre el mensaje.
"""

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse

from app.api.deps import get_auth_service
from app.api.session_cookie import (
    LOGIN_FLOW_COOKIE,
    SESSION_COOKIE,
    clear_login_flow_cookie,
    clear_session_cookie,
    set_login_flow_cookie,
    set_session_cookie,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.services.auth_service import LOGIN_FLOW_MAX_AGE_SECONDS, AuthService
from app.services.errors import LoginError, LoginFlowError

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _back_to_login(error_code: str) -> RedirectResponse:
    query = urlencode({"error": error_code})
    response = RedirectResponse(f"{settings.frontend_url}/login?{query}", status_code=302)
    clear_login_flow_cookie(response)
    return response


@router.get("/google/login")
def google_login(
    tz: str | None = Query(default=None, description="Zona IANA del navegador"),
    next_path: str | None = Query(
        default=None, alias="next", description="Pagina del front a la que volver (/admin...)"
    ),
    auth: AuthService = Depends(get_auth_service),
) -> RedirectResponse:
    """Arranca el login: redirige a la pantalla de Google. `tz` se usa solo
    si este termina siendo el primer login del usuario."""
    try:
        url, flow_cookie = auth.start_google_login(tz, next_path)
    except LoginError as exc:
        logger.warning("Login con Google no disponible: %s", exc.code)
        return _back_to_login(exc.code)

    response = RedirectResponse(url, status_code=302)
    set_login_flow_cookie(response, flow_cookie, max_age=LOGIN_FLOW_MAX_AGE_SECONDS)
    return response


@router.get("/google/callback")
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    auth: AuthService = Depends(get_auth_service),
) -> RedirectResponse:
    """Google vuelve aca. `error` llega si el usuario cancelo en Google."""
    if error is not None:
        return _back_to_login("cancelled" if error == "access_denied" else "oauth_failed")

    try:
        result = auth.complete_google_login(
            code=code,
            state=state,
            flow_cookie=request.cookies.get(LOGIN_FLOW_COOKIE),
            user_agent=request.headers.get("user-agent"),
        )
    except LoginFlowError as exc:
        # El detalle (que fallo del flujo) va al log, no al usuario.
        logger.warning("Login con Google fallido: %s", exc)
        return _back_to_login(exc.code)
    except LoginError as exc:
        logger.info("Login con Google rechazado: %s", exc.code)
        return _back_to_login(exc.code)

    logger.info("Login con Google: usuario %s", result.user.id)
    response = RedirectResponse(f"{settings.frontend_url}{result.next_path}", status_code=302)
    set_session_cookie(response, result.session_token)
    clear_login_flow_cookie(response)
    return response


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
) -> None:
    """Idempotente: sin sesion (o con una ya vencida) tambien responde 204."""
    auth.logout(request.cookies.get(SESSION_COOKIE))
    clear_session_cookie(response)
