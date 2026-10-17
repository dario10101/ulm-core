"""Forma del campo `data` de cada entidad de blg_entities.

Con una tabla generica la base no valida columnas tipadas: lo hacen estos
modelos, al escribir y tambien al leer (una fila escrita a mano o por una
version vieja del codigo se detecta al leerla, no en la vista publica).
`extra="ignore"` al leer: un campo que se dejo de usar no rompe documentos
viejos. Los ids no van en `data`: salen del `sk` (ver blog_keys).
"""

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class _Document(BaseModel):
    model_config = ConfigDict(extra="ignore")


class BlogDoc(_Document):
    """Config del blog (sk `BLOG`). Tambien es el "candado" de los cambios que
    afectan a todas las secciones (cuantas hay habilitadas): se reescribe en
    cada uno para que su `version` serialice dos requests simultaneos."""

    enabled: bool = True
    display_name: str | None = None


class SectionDoc(_Document):
    type: str
    label: str
    slug: str
    position: int
    enabled: bool
    schema_version: int
    content: dict[str, Any]


class GroupDoc(_Document):
    label: str
    description: str | None = None
    position: int


ItemStatus = Literal["draft", "published"]


class ItemDoc(_Document):
    slug: str
    title: str
    # dt.date: un campo llamado `date` sombrearia al tipo dentro de la clase.
    date: dt.date | None = None
    excerpt: str | None = None
    tags: list[str] = []
    cover_url: str | None = None
    group_id: str | None = None
    status: ItemStatus = "draft"
    position: int | None = None
    size_bytes: int
    sha256: str
    original_filename: str


class BodyDoc(_Document):
    """El .md tal cual se subio (con su frontmatter): la descarga devuelve
    exactamente esto. Va en su propia fila para que los listados no lo lean."""

    content_md: str
