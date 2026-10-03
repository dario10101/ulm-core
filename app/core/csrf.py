"""Chequeo de Origin en escrituras: segunda linea contra CSRF.

CSRF: otro sitio hace que el navegador de la victima mande un POST a esta API,
y el navegador adjunta la cookie de sesion solo. La primera linea es la cookie
SameSite=Lax (no viaja en POST cruzados); esta es la segunda, por si un
navegador viejo no respeta SameSite.

Los navegadores mandan `Origin` en todo POST/PUT/PATCH/DELETE. Si viene y no
es uno de los nuestros, se rechaza. Si no viene, no es un navegador (curl, un
script, los tests): ahi CSRF no aplica, porque el atacante necesitaria la
cookie, y si la tiene ya no necesita CSRF.
"""

from collections.abc import Iterable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class OriginCheckMiddleware:
    def __init__(self, app: ASGIApp, allowed_origins: Iterable[str]) -> None:
        self._app = app
        self._allowed = {origin.rstrip("/") for origin in allowed_origins}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] in UNSAFE_METHODS:
            origin = dict(scope["headers"]).get(b"origin")
            if origin is not None and origin.decode("latin-1") not in self._allowed:
                response = JSONResponse(status_code=403, content={"detail": "Origen no permitido"})
                await response(scope, receive, send)
                return
        await self._app(scope, receive, send)
