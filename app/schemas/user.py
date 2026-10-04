"""Schemas de usuario expuestos por la API."""

from pydantic import BaseModel


class MeRead(BaseModel):
    """Lo que el front necesita del usuario logueado. `permissions` son los
    efectivos (todos si es admin): el front muestra u oculta modulos con esto,
    pero quien decide es el backend (require en cada router)."""

    id: int
    name: str
    email: str
    avatar_url: str | None
    timezone: str
    is_admin: bool
    permissions: list[str]
