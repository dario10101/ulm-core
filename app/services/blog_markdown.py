"""Validacion de un .md subido a una coleccion del blog.

El archivo se guarda tal cual (la descarga devuelve lo mismo); de aca solo sale
lo que hace falta para listarlo: los metadatos del frontmatter.

```markdown
---
title: Notas sobre funciones de ventana en PySpark   # obligatorio
date: 2026-07-18
slug: notas-pyspark          # opcional: si falta, sale del nombre del archivo
excerpt: Resumen corto para el listado.
tags: [Datos, PySpark]
cover_url: https://...       # solo https
---
```

El frontmatter se lee con `python-frontmatter`, que usa `yaml.safe_load`: no
construye objetos de Python a partir de etiquetas YAML. No cambiarlo.
"""

import datetime as dt
import hashlib
from dataclasses import dataclass
from pathlib import PurePath
from typing import Annotated

import frontmatter
import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from app.services.blog_section_types import HttpsUrl
from app.services.blog_slugs import ITEM_SLUG_MAX, slugify, validate_item_slug
from app.services.errors import InvalidMarkdownError


class ItemFrontmatter(BaseModel):
    # Otros campos del frontmatter se ignoran (quedan en el original).
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    title: Annotated[str, Field(min_length=1, max_length=200)]
    # dt.date: un campo llamado `date` sombrearia al tipo dentro de la clase.
    date: dt.date | None = None
    slug: str | None = None
    excerpt: Annotated[str, Field(max_length=500)] | None = None
    tags: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=40)]], Field(max_length=20)
    ] = []
    cover_url: HttpsUrl | None = None


@dataclass(frozen=True)
class ParsedMarkdown:
    meta: ItemFrontmatter
    slug: str
    text: str
    size_bytes: int
    sha256: str
    filename: str


def _clean_filename(filename: str | None) -> str:
    # Solo el nombre (un navegador viejo puede mandar la ruta completa).
    name = PurePath((filename or "").replace("\\", "/")).name.strip()
    if not name.lower().endswith(".md"):
        raise InvalidMarkdownError("El archivo debe ser .md")
    return name[-120:]


def parse_markdown_upload(filename: str | None, raw: bytes, *, max_bytes: int) -> ParsedMarkdown:
    name = _clean_filename(filename)
    if len(raw) > max_bytes:
        raise InvalidMarkdownError(f"El archivo supera el maximo de {max_bytes // 1000} KB")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise InvalidMarkdownError("El archivo no esta en UTF-8") from None

    try:
        post = frontmatter.loads(text)
    except yaml.YAMLError as exc:
        raise InvalidMarkdownError(f"El frontmatter no es YAML valido: {exc}") from None
    if not post.metadata:
        raise InvalidMarkdownError("El archivo necesita un frontmatter con al menos `title`")
    try:
        meta = ItemFrontmatter.model_validate(post.metadata)
    except PydanticValidationError as exc:
        fields = "; ".join(
            f"{'.'.join(str(p) for p in error['loc'])}: {error['msg']}" for error in exc.errors()
        )
        raise InvalidMarkdownError(f"Frontmatter invalido: {fields}") from None

    slug = meta.slug or slugify(name[:-3], ITEM_SLUG_MAX)
    return ParsedMarkdown(
        meta=meta,
        slug=validate_item_slug(slug),
        text=text,
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        filename=name,
    )
