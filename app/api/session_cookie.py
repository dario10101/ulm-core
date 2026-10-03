"""Cookies del login. Viven aca y no en las rutas porque las usan tanto las
rutas de auth como la dependencia get_current_user (que renueva la sesion)."""

from fastapi import Response

from app.core.config import settings

SESSION_COOKIE = "ulm_session"
# Cookie de corta vida con state/nonce/PKCE, solo entre /login y /callback.
LOGIN_FLOW_COOKIE = "ulm_login_flow"
LOGIN_FLOW_PATH = f"{settings.api_prefix}/auth/google"


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_days * 24 * 3600,
        # httponly: JavaScript no la puede leer, asi que un XSS no se la lleva.
        httponly=True,
        # lax: viaja en navegacion normal (incluida la vuelta desde Google)
        # pero no en POST/fetch originados en otro sitio. Primera linea contra
        # CSRF; la segunda es el chequeo de Origin (app/core/csrf.py).
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def set_login_flow_cookie(response: Response, value: str, max_age: int) -> None:
    response.set_cookie(
        LOGIN_FLOW_COOKIE,
        value,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path=LOGIN_FLOW_PATH,
    )


def clear_login_flow_cookie(response: Response) -> None:
    response.delete_cookie(LOGIN_FLOW_COOKIE, path=LOGIN_FLOW_PATH)
