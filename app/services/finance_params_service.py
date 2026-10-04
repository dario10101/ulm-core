"""Parametros del dominio de finanzas que administra cada usuario sobre sus
propios datos: tags (compartidos por gastos e ingresos), fuentes y
subcategorias de ingreso. Los abre el permiso `finances`, no el admin.

Borrado hibrido (ver catalog_rules.delete_or_archive): sin registros se borra,
con registros se archiva. Un item archivado deja de ofrecerse en los
formularios pero los registros viejos lo siguen mostrando; se restaura
mandando status=ENABLED en el update.
"""

from app.db.models.finance import IncomeSource, IncomeSubcategory, Tag
from app.repositories.finance_catalog_repository import FinanceCatalogRepository
from app.schemas.finance import (
    CatalogDeleteResult,
    IncomeKind,
    IncomeSourceAdminRead,
    IncomeSourceRead,
    IncomeSourceWrite,
    IncomeSubcategoryAdminRead,
    IncomeSubcategoryRead,
    IncomeSubcategoryWrite,
    TagAdminRead,
    TagRead,
    TagWrite,
)
from app.services.catalog_rules import delete_or_archive, ensure_unique_name
from app.services.errors import CatalogItemLockedError, CatalogItemNotFoundError


def _source_accepts(source_type: IncomeKind, kind: IncomeKind) -> bool:
    return source_type in (kind, IncomeKind.ALL)


class FinanceParamsService:
    def __init__(self, repository: FinanceCatalogRepository) -> None:
        self._repository = repository

    # --- Tags ---

    def list_tags(self, *, user_id: int) -> list[TagAdminRead]:
        usage = self._repository.tag_usage(user_id)
        return [self._tag_read(t, usage.get(t.id, 0)) for t in self._repository.list_tags(user_id)]

    def create_tag(self, *, user_id: int, payload: TagWrite) -> TagAdminRead:
        ensure_unique_name(payload.name, self._repository.list_tags(user_id))
        tag = Tag(
            user_id=user_id,
            name=payload.name,
            color_key=payload.color_key,
            status=payload.status.value,
        )
        self._repository.add(tag)
        self._repository.flush()
        return self._tag_read(tag, 0)

    def update_tag(self, tag_id: int, *, user_id: int, payload: TagWrite) -> TagAdminRead:
        tag = self._get_tag(user_id, tag_id)
        ensure_unique_name(payload.name, self._repository.list_tags(user_id), exclude_id=tag.id)
        tag.name = payload.name
        tag.color_key = payload.color_key
        tag.status = payload.status.value
        self._repository.flush()
        return self._tag_read(tag, self._repository.tag_usage(user_id).get(tag.id, 0))

    def delete_tag(self, tag_id: int, *, user_id: int) -> CatalogDeleteResult:
        tag = self._get_tag(user_id, tag_id)
        result = delete_or_archive(
            tag,
            usage_count=self._repository.tag_usage(user_id).get(tag.id, 0),
            delete=self._repository.delete,
        )
        self._repository.flush()
        return result

    def _get_tag(self, user_id: int, tag_id: int) -> Tag:
        tag = self._repository.get_tag(user_id, tag_id)
        if tag is None:
            raise CatalogItemNotFoundError("Tag", tag_id)
        return tag

    @staticmethod
    def _tag_read(tag: Tag, usage_count: int) -> TagAdminRead:
        return TagAdminRead(**TagRead.model_validate(tag).model_dump(), usage_count=usage_count)

    # --- Fuentes ---

    def list_sources(self, *, user_id: int) -> list[IncomeSourceAdminRead]:
        usage = self._repository.source_usage(user_id)
        subcategories = self._repository.list_income_subcategories(user_id)
        return [
            self._source_read(
                source,
                sum(usage.get(source.id, (0, 0))),
                sum(1 for s in subcategories if s.source_id == source.id),
            )
            for source in self._repository.list_income_sources(user_id)
        ]

    def create_source(self, *, user_id: int, payload: IncomeSourceWrite) -> IncomeSourceAdminRead:
        ensure_unique_name(payload.name, self._repository.list_income_sources(user_id))
        source = IncomeSource(
            user_id=user_id,
            name=payload.name,
            type=payload.type.value,
            status=payload.status.value,
        )
        self._repository.add(source)
        self._repository.flush()
        return self._source_read(source, 0, 0)

    def update_source(
        self, source_id: int, *, user_id: int, payload: IncomeSourceWrite
    ) -> IncomeSourceAdminRead:
        source = self._get_source(user_id, source_id)
        ensure_unique_name(
            payload.name, self._repository.list_income_sources(user_id), exclude_id=source.id
        )
        direct, interest = self._repository.source_usage(user_id).get(source.id, (0, 0))
        # El tipo decide que formulario ofrece la fuente: no puede dejar fuera
        # a ingresos que ya la usan (ej. pasar a DIRECT con meses de intereses).
        if (direct and not _source_accepts(payload.type, IncomeKind.DIRECT)) or (
            interest and not _source_accepts(payload.type, IncomeKind.INTEREST)
        ):
            raise CatalogItemLockedError(
                f"'{source.name}' tiene ingresos de un tipo que {payload.type.value} no admite"
            )
        source.name = payload.name
        source.type = payload.type.value
        source.status = payload.status.value
        self._repository.flush()
        return self._source_read(source, direct + interest, len(self._siblings(user_id, source.id)))

    def delete_source(self, source_id: int, *, user_id: int) -> CatalogDeleteResult:
        source = self._get_source(user_id, source_id)
        usage_count = sum(self._repository.source_usage(user_id).get(source.id, (0, 0)))
        if usage_count == 0:
            # Sin ingresos tampoco los tiene ninguna de sus subcategorias (un
            # ingreso siempre lleva la fuente de su subcategoria): se van con ella.
            for subcategory in self._repository.list_income_subcategories(user_id):
                if subcategory.source_id == source.id:
                    self._repository.delete(subcategory)
            # Sin relationship entre los modelos, el unit of work no sabe que
            # las subcategorias van antes que la fuente: se fuerza el orden.
            self._repository.flush()
        result = delete_or_archive(source, usage_count=usage_count, delete=self._repository.delete)
        self._repository.flush()
        return result

    def _get_source(self, user_id: int, source_id: int) -> IncomeSource:
        source = self._repository.get_income_source(user_id, source_id)
        if source is None:
            raise CatalogItemNotFoundError("Fuente", source_id)
        return source

    @staticmethod
    def _source_read(
        source: IncomeSource, usage_count: int, subcategory_count: int
    ) -> IncomeSourceAdminRead:
        return IncomeSourceAdminRead(
            **IncomeSourceRead.model_validate(source).model_dump(),
            usage_count=usage_count,
            subcategory_count=subcategory_count,
        )

    # --- Subcategorias ---

    def list_subcategories(self, *, user_id: int) -> list[IncomeSubcategoryAdminRead]:
        usage = self._repository.subcategory_usage(user_id)
        return [
            self._subcategory_read(s, usage.get(s.id, 0))
            for s in self._repository.list_income_subcategories(user_id)
        ]

    def create_subcategory(
        self, *, user_id: int, payload: IncomeSubcategoryWrite
    ) -> IncomeSubcategoryAdminRead:
        source = self._get_source(user_id, payload.source_id)
        ensure_unique_name(payload.name, self._siblings(user_id, source.id))
        subcategory = IncomeSubcategory(
            user_id=user_id,
            source_id=source.id,
            # Columna redundante (el tipo lo da la fuente), pero NOT NULL.
            type=source.type,
            name=payload.name,
            status=payload.status.value,
        )
        self._repository.add(subcategory)
        self._repository.flush()
        return self._subcategory_read(subcategory, 0)

    def update_subcategory(
        self, subcategory_id: int, *, user_id: int, payload: IncomeSubcategoryWrite
    ) -> IncomeSubcategoryAdminRead:
        subcategory = self._get_subcategory(user_id, subcategory_id)
        source = self._get_source(user_id, payload.source_id)
        usage_count = self._repository.subcategory_usage(user_id).get(subcategory.id, 0)
        # Cada ingreso guarda fuente y subcategoria: mover una subcategoria
        # usada dejaria esos ingresos con una pareja que no calza.
        if source.id != subcategory.source_id and usage_count:
            raise CatalogItemLockedError(
                f"'{subcategory.name}' tiene ingresos: no se puede mover a otra fuente"
            )
        ensure_unique_name(
            payload.name, self._siblings(user_id, source.id), exclude_id=subcategory.id
        )
        subcategory.source_id = source.id
        subcategory.type = source.type
        subcategory.name = payload.name
        subcategory.status = payload.status.value
        self._repository.flush()
        return self._subcategory_read(subcategory, usage_count)

    def delete_subcategory(self, subcategory_id: int, *, user_id: int) -> CatalogDeleteResult:
        subcategory = self._get_subcategory(user_id, subcategory_id)
        result = delete_or_archive(
            subcategory,
            usage_count=self._repository.subcategory_usage(user_id).get(subcategory.id, 0),
            delete=self._repository.delete,
        )
        self._repository.flush()
        return result

    def _siblings(self, user_id: int, source_id: int) -> list[IncomeSubcategory]:
        """El nombre de una subcategoria es unico dentro de su fuente."""
        return [
            s
            for s in self._repository.list_income_subcategories(user_id)
            if s.source_id == source_id
        ]

    def _get_subcategory(self, user_id: int, subcategory_id: int) -> IncomeSubcategory:
        subcategory = self._repository.get_income_subcategory(user_id, subcategory_id)
        if subcategory is None:
            raise CatalogItemNotFoundError("Subcategoria", subcategory_id)
        return subcategory

    @staticmethod
    def _subcategory_read(
        subcategory: IncomeSubcategory, usage_count: int
    ) -> IncomeSubcategoryAdminRead:
        return IncomeSubcategoryAdminRead(
            **IncomeSubcategoryRead.model_validate(subcategory).model_dump(),
            usage_count=usage_count,
        )
