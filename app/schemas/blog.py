"""Schemas publicos del blog (sin sesion).

Separados de los privados a proposito: lo que sale por aca lo ve cualquiera,
asi que se declara campo por campo. Nunca id, email, nombre de Google ni
avatar: el usuario no autorizo publicarlos. Tampoco ids internos de
secciones, subsecciones o elementos: el publico navega por slugs, y los
elementos van anidados en su subseccion para no exponer el id de esta.
"""

import datetime as dt
from typing import Any

from pydantic import BaseModel


class PublicSectionRead(BaseModel):
    slug: str
    label: str
    # Tipo del catalogo (home, about, professional, collection): el front
    # elige con esto que plantilla pintar.
    type: str
    content: dict[str, Any]


class PublicBlogRead(BaseModel):
    """Todo lo que el layout necesita en un solo request (sin cascada): el
    menu y el contenido de las plantillas. Solo secciones habilitadas, en
    orden."""

    username: str
    display_name: str | None
    sections: list[PublicSectionRead]


class PublicItemSummary(BaseModel):
    slug: str
    title: str
    date: dt.date | None
    excerpt: str | None
    tags: list[str]
    cover_url: str | None


class PublicGroupRead(BaseModel):
    label: str
    description: str | None
    items: list[PublicItemSummary]


class PublicSectionRef(BaseModel):
    slug: str
    label: str


class PublicCollectionRead(BaseModel):
    """Una coleccion: sus subsecciones (con sus elementos) y los elementos
    sin subseccion. Solo publicados, sin el cuerpo del .md."""

    section: PublicSectionRef
    groups: list[PublicGroupRead]
    ungrouped: list[PublicItemSummary]


class PublicItemRead(PublicItemSummary):
    section: PublicSectionRef
    # El markdown sin el frontmatter. Lo renderiza y sanitiza el front.
    body_md: str
