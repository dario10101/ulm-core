"""Slugs del blog: el tramo de URL de una seccion (/blog/u/<seccion>) y de un
elemento (/blog/u/<seccion>/<elemento>).

Mismo formato que el username (ASCII en minusculas, digitos y guiones sueltos)
por las mismas razones: URL legible y sin homoglifos. Los de seccion viven
debajo de /blog/<username>, asi que no chocan con rutas de la app; solo se
reservan los que podria usar el propio blog a futuro.
"""

import re
import unicodedata

from app.services.errors import InvalidSlugError

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

SECTION_SLUG_MIN = 2
SECTION_SLUG_MAX = 40
ITEM_SLUG_MIN = 2
ITEM_SLUG_MAX = 80

RESERVED_SECTION_SLUGS = frozenset({"feed", "rss", "sitemap"})


def slugify(text: str, max_length: int) -> str:
    """Texto libre a slug: `Cómo usar PySpark` -> `como-usar-pyspark`. Quita
    tildes (NFKD + solo ASCII), pasa a minusculas y deja guiones entre
    palabras. Puede devolver "" si no hay ni una letra o digito latino."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:max_length].rstrip("-")


def _validate(value: str, *, min_length: int, max_length: int) -> str:
    slug = value.strip().lower()
    if not min_length <= len(slug) <= max_length:
        raise InvalidSlugError(f"El slug debe tener entre {min_length} y {max_length} caracteres")
    if not _SLUG_RE.match(slug):
        raise InvalidSlugError(
            "El slug solo admite letras minusculas, numeros y guiones (sin guion "
            "al inicio, al final ni dos seguidos)"
        )
    return slug


def validate_section_slug(value: str) -> str:
    slug = _validate(value, min_length=SECTION_SLUG_MIN, max_length=SECTION_SLUG_MAX)
    if slug in RESERVED_SECTION_SLUGS:
        raise InvalidSlugError(f"'{slug}' esta reservado")
    return slug


def validate_item_slug(value: str) -> str:
    return _validate(value, min_length=ITEM_SLUG_MIN, max_length=ITEM_SLUG_MAX)
