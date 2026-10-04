"""Schemas de usuario expuestos por la API."""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Forma minima (algo@dominio.tld): el control real es Google, que solo deja
# entrar con un email verificado. Esto atrapa errores de tipeo groseros.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class MeRead(BaseModel):
    """Lo que el front necesita del usuario logueado. `permissions` son los
    efectivos (todos si es admin): el front muestra u oculta modulos con esto,
    pero quien decide es el backend (require en cada router)."""

    id: int
    name: str
    email: str
    avatar_url: str | None
    timezone: str
    # Nulo hasta que el usuario lo crea (Settings -> General).
    username: str | None
    is_admin: bool
    permissions: list[str]


class UsernameWrite(BaseModel):
    """El formato se valida en el service (app/services/username.py), no aca:
    es regla de dominio y la reutilizara el login con contraseña. El limite
    solo corta entradas absurdas antes de procesarlas."""

    username: str = Field(max_length=64)


class AccessInfoRead(BaseModel):
    """Como entra la gente a la app (Settings -> Access, solo admin)."""

    registration_mode: str
    # Lista de test users de Google mientras la app OAuth este en modo Testing.
    google_audience_url: str


# --- Administracion de usuarios (solo admin, /admin/users) ---


class UserAdminRead(BaseModel):
    """Un usuario visto por el admin. `permissions` son los efectivos: todos
    si `is_admin` (y entonces no se edita)."""

    id: int
    name: str
    email: str
    avatar_url: str | None
    status: Literal["invited", "active", "disabled"]
    is_admin: bool
    permissions: list[str]
    created_at: datetime
    last_login_at: datetime | None


class UserInvite(BaseModel):
    email: str = Field(max_length=255)
    name: str | None = Field(default=None, max_length=120)

    @field_validator("email")
    @classmethod
    def _looks_like_an_email(cls, value: str) -> str:
        value = value.strip()
        if not _EMAIL_RE.match(value):
            raise ValueError("Email invalido")
        return value

    @field_validator("name")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class UserPermissionsWrite(BaseModel):
    """El conjunto completo: lo que no venga se quita."""

    permissions: list[str]
