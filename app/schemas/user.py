"""Schemas de usuario expuestos por la API."""

from pydantic import BaseModel


class MeRead(BaseModel):
    """Lo que el front necesita del usuario logueado. Los permisos se agregan
    en la fase de autorizacion por modulos."""

    id: int
    name: str
    email: str
    avatar_url: str | None
    timezone: str
