"""Lecturas del blog que comparten la administracion (BlogAdminService) y la
lectura publica (BlogService): cargar las secciones de un usuario y ordenar
los elementos de una coleccion.

Solo usan los patrones de acceso de PLAN-BLOG.md (7.4): las secciones salen
de una consulta por prefijo (A2) y de ahi mismo se resuelve una por slug (A3).
"""

import datetime as dt
from collections.abc import Sequence
from typing import Literal, Protocol

from app.core.logging import get_logger
from app.db.models.blog import BlgEntity
from app.repositories import blog_keys as keys
from app.repositories.blog_entity_repository import BlogEntityRepository
from app.services.blog_documents import SectionDoc
from app.services.blog_section_types import SECTION_TYPES, SectionType

logger = get_logger(__name__)


class LoadedSection:
    """Una seccion leida: la fila, su documento y su tipo."""

    def __init__(self, entity: BlgEntity, doc: SectionDoc, section_type: SectionType) -> None:
        self.entity = entity
        self.doc = doc
        self.type = section_type

    @property
    def id(self) -> str:
        return keys.section_id_of(self.entity.sk)


def load_sections(
    repository: BlogEntityRepository, user_id: int, *, include_unknown: bool = False
) -> list[LoadedSection]:
    """Las secciones del usuario, en el orden del menu. Una de un tipo que ya
    no esta en el catalogo se omite (y se registra), salvo con
    `include_unknown`, para contar topes, donde sigue ocupando lugar."""
    sections = []
    for entity in repository.query(user_id=user_id, sk_prefix=keys.SECTION_PREFIX):
        doc = SectionDoc.model_validate(entity.data)
        section_type = SECTION_TYPES.get(doc.type)
        if section_type is None:
            logger.warning("Seccion %s de tipo desconocido %s", entity.sk, doc.type)
            if not include_unknown:
                continue
            section_type = SECTION_TYPES["collection"]  # solo para contar
        sections.append(LoadedSection(entity, doc, section_type))
    return sorted(sections, key=lambda s: (s.doc.position, s.doc.label.lower()))


class _Sortable(Protocol):
    @property
    def position(self) -> int | None: ...

    @property
    def date(self) -> dt.date | None: ...

    @property
    def title(self) -> str: ...


ItemSort = Literal["date_desc", "manual", "title"]


def sort_items[T: _Sortable](items: Sequence[T], sort: ItemSort) -> list[T]:
    """Orden de los elementos de una coleccion (`CollectionContent.sort`).
    En todos, el titulo desempata; sin fecha o sin posicion, al final."""

    def newest_first(item: T) -> int:
        return -(item.date.toordinal() if item.date else 0)

    if sort == "title":
        return sorted(items, key=lambda item: item.title.lower())
    if sort == "manual":
        return sorted(
            items,
            key=lambda item: (
                item.position is None,
                item.position or 0,
                newest_first(item),
                item.title.lower(),
            ),
        )
    return sorted(items, key=lambda item: (newest_first(item), item.title.lower()))
