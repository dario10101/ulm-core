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


class AccessInfoRead(BaseModel):
    """Como entra la gente a la app (Settings -> Access, solo admin)."""

    registration_mode: str
    # Lista de test users de Google mientras la app OAuth este en modo Testing.
    google_audience_url: str
