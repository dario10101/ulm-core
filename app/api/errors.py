"""Traduccion generica de errores de dominio a HTTP, por familia.

Las rutas viejas capturan cada error concreto; las de administracion de
parametros tienen muchos y todos siguen la regla de su familia (ver
app/services/errors.py), asi que se traducen de una sola forma.
"""

from fastapi import HTTPException

from app.services.errors import ConflictError, DomainError, NotFoundError, ValidationError


def http_error(exc: DomainError) -> HTTPException:
    if isinstance(exc, NotFoundError):
        status = 404
    elif isinstance(exc, ConflictError):
        status = 409
    elif isinstance(exc, ValidationError):
        status = 422
    else:
        status = 400
    return HTTPException(status_code=status, detail=str(exc))
