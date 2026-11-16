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


class LinkDoc(_Document):
    """Un link de la lista del usuario (PLAN-BLOG-LINKS.md). `url` ya
    normalizado (https://, mailto: o https://wa.me/)."""

    id: str
    type: str
    url: str
    label: str | None = None


class BlogDoc(_Document):
    """Config del blog (sk `BLOG`). Tambien es el "candado" de los cambios que
    afectan a todas las secciones (cuantas hay habilitadas): se reescribe en
    cada uno para que su `version` serialice dos requests simultaneos.

    `links`: la lista de links del usuario. Va aca y no en su propia fila: son
    pocos (tope por tipo), siempre se leen juntos y la lectura publica ya lee
    este registro; ademas su `version` evita que dos pestañas se pisen."""

    enabled: bool = True
    display_name: str | None = None
    links: list[LinkDoc] = []


class LinkSlot(_Document):
    """Un link de la lista del usuario en una ubicacion de la seccion."""

    id: str
    enabled: bool


class SectionLinksDoc(_Document):
    """Links de la seccion por ubicacion: en medio de la pagina (`inline`) y
    al final de la plantilla (`end`). Fuera de `content`: no depende del tipo."""

    inline: list[LinkSlot] = []
    end: list[LinkSlot] = []


class SectionDoc(_Document):
    type: str
    label: str
    slug: str
    position: int
    enabled: bool
    schema_version: int
    content: dict[str, Any]
    links: SectionLinksDoc = SectionLinksDoc()


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
