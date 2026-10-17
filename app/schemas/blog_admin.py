"""Schemas de la administracion del blog propio (/blog, permiso `blog`).

Separados de los publicos (app/schemas/blog.py): estos ven ids, borradores y
secciones deshabilitadas, que el publico nunca debe recibir.

El formato de slugs y el contenido de cada plantilla los valida el service
(son reglas de dominio que tambien usara la lectura publica); aca solo los
limites de forma.
"""

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Label = Field(min_length=1, max_length=40)


class _Write(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --- Config ---


class SectionTypeRead(BaseModel):
    type: str
    singleton: bool
    has_items: bool
    default_label: str
    default_slug: str | None


class BlogSettingsRead(BaseModel):
    enabled: bool
    display_name: str | None
    max_enabled_sections: int
    max_sections: int
    section_types: list[SectionTypeRead]


class BlogSettingsWrite(_Write):
    enabled: bool
    display_name: str | None = Field(default=None, max_length=80)


# --- Secciones ---


class SectionRead(BaseModel):
    id: str
    type: str
    label: str
    slug: str
    position: int
    enabled: bool
    content: dict[str, Any]
    created_at: dt.datetime
    updated_at: dt.datetime


class SectionCreate(_Write):
    type: str = Field(max_length=40)
    # Sin label: el del tipo ("Inicio"). Sin slug: el del tipo, o derivado
    # del label en las colecciones.
    label: str | None = Field(default=None, min_length=1, max_length=40)
    slug: str | None = Field(default=None, max_length=60)
    enabled: bool = False


class SectionUpdate(_Write):
    """Solo los campos enviados. Renombrar (label) no cambia el slug."""

    label: str | None = Field(default=None, min_length=1, max_length=40)
    slug: str | None = Field(default=None, max_length=60)
    enabled: bool | None = None


class SectionOrderWrite(_Write):
    """Todas las secciones del usuario, en el orden nuevo del menu."""

    ids: list[str] = Field(max_length=100)


class OrderWrite(_Write):
    """Todas las subsecciones (o todos los elementos) de una seccion, en el orden nuevo."""

    ids: list[str] = Field(max_length=500)


# --- Subsecciones ---


class GroupRead(BaseModel):
    id: str
    label: str
    description: str | None
    position: int


class GroupCreate(_Write):
    label: str = Field(min_length=1, max_length=60)
    description: str | None = Field(default=None, max_length=300)


class GroupUpdate(_Write):
    label: str | None = Field(default=None, min_length=1, max_length=60)
    description: str | None = Field(default=None, max_length=300)
    position: int | None = Field(default=None, ge=0)


# --- Elementos (.md) ---


class ItemRead(BaseModel):
    id: str
    section_id: str
    slug: str
    title: str
    date: dt.date | None
    excerpt: str | None
    tags: list[str]
    cover_url: str | None
    group_id: str | None
    status: Literal["draft", "published"]
    position: int | None
    size_bytes: int
    original_filename: str
    created_at: dt.datetime
    updated_at: dt.datetime


class ItemUpdate(_Write):
    """Solo los campos enviados. `group_id: null` saca el elemento de su subseccion."""

    status: Literal["draft", "published"] | None = None
    group_id: str | None = Field(default=None, max_length=40)
    position: int | None = Field(default=None, ge=0)
