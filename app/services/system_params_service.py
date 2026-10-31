"""Parametros globales del sistema que solo administra el admin: las
plantillas que se copian a cada usuario al registrarse (ver
UserAdminService.register): categorias de gasto, metodos de pago, fuentes y
subcategorias de ingreso.

Nada referencia una plantilla despues de la copia, asi que no hay borrado
hibrido: borrar es borrar. Cambiarla no toca lo que ya tienen los usuarios
existentes (cada uno administra lo suyo, ver FinanceParamsService).
"""

from collections.abc import Iterable
from typing import Protocol

from app.db.base_class import Base
from app.db.models.finance import (
    DefaultExpenseCategory,
    DefaultIncomeSource,
    DefaultIncomeSubcategory,
    DefaultPaymentMethod,
)
from app.repositories.finance_catalog_repository import FinanceCatalogRepository
from app.schemas.finance import (
    CatalogDeleteResult,
    DefaultIconCatalogRead,
    DefaultIconCatalogWrite,
    DefaultIncomeSourceRead,
    DefaultIncomeSourceWrite,
    DefaultIncomeSubcategoryRead,
    DefaultIncomeSubcategoryWrite,
)
from app.services.errors import CatalogItemNotFoundError, CatalogNameTakenError


class _Named(Protocol):
    id: int
    name: str


def _ensure_unique_name(
    name: str, siblings: Iterable[_Named], *, exclude_id: int | None = None
) -> None:
    """Como catalog_rules.ensure_unique_name, pero sin archivados: los items
    de una plantilla no tienen status."""
    wanted = name.casefold()
    for item in siblings:
        if item.id != exclude_id and item.name.casefold() == wanted:
            raise CatalogNameTakenError(item.name, archived=False)


IconDefault = DefaultExpenseCategory | DefaultPaymentMethod


class SystemParamsService:
    def __init__(self, repository: FinanceCatalogRepository) -> None:
        self._repository = repository

    # --- Categorias de gasto ---

    def list_default_categories(self) -> list[DefaultIconCatalogRead]:
        return [
            DefaultIconCatalogRead.model_validate(c)
            for c in self._repository.list_default_categories()
        ]

    def create_default_category(self, payload: DefaultIconCatalogWrite) -> DefaultIconCatalogRead:
        _ensure_unique_name(payload.name, self._repository.list_default_categories())
        return self._add_icon_default(DefaultExpenseCategory, payload)

    def update_default_category(
        self, category_id: int, payload: DefaultIconCatalogWrite
    ) -> DefaultIconCatalogRead:
        category = self._found(
            self._repository.get_default_category(category_id), "Categoria", category_id
        )
        _ensure_unique_name(
            payload.name, self._repository.list_default_categories(), exclude_id=category.id
        )
        return self._update_icon_default(category, payload)

    def delete_default_category(self, category_id: int) -> CatalogDeleteResult:
        return self._delete(
            self._found(
                self._repository.get_default_category(category_id), "Categoria", category_id
            )
        )

    # --- Metodos de pago ---

    def list_default_payment_methods(self) -> list[DefaultIconCatalogRead]:
        return [
            DefaultIconCatalogRead.model_validate(p)
            for p in self._repository.list_default_payment_methods()
        ]

    def create_default_payment_method(
        self, payload: DefaultIconCatalogWrite
    ) -> DefaultIconCatalogRead:
        _ensure_unique_name(payload.name, self._repository.list_default_payment_methods())
        return self._add_icon_default(DefaultPaymentMethod, payload)

    def update_default_payment_method(
        self, payment_method_id: int, payload: DefaultIconCatalogWrite
    ) -> DefaultIconCatalogRead:
        method = self._found(
            self._repository.get_default_payment_method(payment_method_id),
            "Metodo de pago",
            payment_method_id,
        )
        _ensure_unique_name(
            payload.name, self._repository.list_default_payment_methods(), exclude_id=method.id
        )
        return self._update_icon_default(method, payload)

    def delete_default_payment_method(self, payment_method_id: int) -> CatalogDeleteResult:
        return self._delete(
            self._found(
                self._repository.get_default_payment_method(payment_method_id),
                "Metodo de pago",
                payment_method_id,
            )
        )

    # --- Fuentes de ingreso ---

    def list_default_sources(self) -> list[DefaultIncomeSourceRead]:
        subcategories = self._repository.list_default_subcategories()
        return [
            self._source_read(source, sum(1 for s in subcategories if s.source_id == source.id))
            for source in self._repository.list_default_sources()
        ]

    def create_default_source(self, payload: DefaultIncomeSourceWrite) -> DefaultIncomeSourceRead:
        _ensure_unique_name(payload.name, self._repository.list_default_sources())
        source = DefaultIncomeSource(name=payload.name, type=payload.type.value)
        self._repository.add(source)
        self._repository.flush()
        return self._source_read(source, 0)

    def update_default_source(
        self, source_id: int, payload: DefaultIncomeSourceWrite
    ) -> DefaultIncomeSourceRead:
        source = self._found(self._repository.get_default_source(source_id), "Fuente", source_id)
        _ensure_unique_name(
            payload.name, self._repository.list_default_sources(), exclude_id=source.id
        )
        source.name = payload.name
        source.type = payload.type.value
        self._repository.flush()
        return self._source_read(source, len(self._siblings(source.id)))

    def delete_default_source(self, source_id: int) -> CatalogDeleteResult:
        source = self._found(self._repository.get_default_source(source_id), "Fuente", source_id)
        # Sus subcategorias se van con ella. Sin relationship entre los
        # modelos, el unit of work no conoce el orden: se fuerza con un flush.
        for subcategory in self._siblings(source.id):
            self._repository.delete(subcategory)
        self._repository.flush()
        return self._delete(source)

    @staticmethod
    def _source_read(
        source: DefaultIncomeSource, subcategory_count: int
    ) -> DefaultIncomeSourceRead:
        return DefaultIncomeSourceRead(
            id=source.id,
            name=source.name,
            type=source.type,
            subcategory_count=subcategory_count,
        )

    # --- Subcategorias de ingreso ---

    def list_default_subcategories(self) -> list[DefaultIncomeSubcategoryRead]:
        return [
            DefaultIncomeSubcategoryRead.model_validate(s)
            for s in self._repository.list_default_subcategories()
        ]

    def create_default_subcategory(
        self, payload: DefaultIncomeSubcategoryWrite
    ) -> DefaultIncomeSubcategoryRead:
        source = self._found(
            self._repository.get_default_source(payload.source_id), "Fuente", payload.source_id
        )
        _ensure_unique_name(payload.name, self._siblings(source.id))
        subcategory = DefaultIncomeSubcategory(source_id=source.id, name=payload.name)
        self._repository.add(subcategory)
        self._repository.flush()
        return DefaultIncomeSubcategoryRead.model_validate(subcategory)

    def update_default_subcategory(
        self, subcategory_id: int, payload: DefaultIncomeSubcategoryWrite
    ) -> DefaultIncomeSubcategoryRead:
        subcategory = self._found(
            self._repository.get_default_subcategory(subcategory_id),
            "Subcategoria",
            subcategory_id,
        )
        # Sin ingresos que la usen, puede cambiar de fuente libremente.
        source = self._found(
            self._repository.get_default_source(payload.source_id), "Fuente", payload.source_id
        )
        _ensure_unique_name(payload.name, self._siblings(source.id), exclude_id=subcategory.id)
        subcategory.source_id = source.id
        subcategory.name = payload.name
        self._repository.flush()
        return DefaultIncomeSubcategoryRead.model_validate(subcategory)

    def delete_default_subcategory(self, subcategory_id: int) -> CatalogDeleteResult:
        return self._delete(
            self._found(
                self._repository.get_default_subcategory(subcategory_id),
                "Subcategoria",
                subcategory_id,
            )
        )

    def _siblings(self, source_id: int) -> list[DefaultIncomeSubcategory]:
        """El nombre de una subcategoria es unico dentro de su fuente."""
        return [
            s for s in self._repository.list_default_subcategories() if s.source_id == source_id
        ]

    # --- Comun ---

    @staticmethod
    def _found[T](item: T | None, label: str, item_id: int) -> T:
        if item is None:
            raise CatalogItemNotFoundError(label, item_id)
        return item

    def _add_icon_default(
        self, model: type[IconDefault], payload: DefaultIconCatalogWrite
    ) -> DefaultIconCatalogRead:
        item = model(name=payload.name, icon_key=payload.icon_key, color_key=payload.color_key)
        self._repository.add(item)
        self._repository.flush()
        return DefaultIconCatalogRead.model_validate(item)

    def _update_icon_default(
        self, item: IconDefault, payload: DefaultIconCatalogWrite
    ) -> DefaultIconCatalogRead:
        item.name = payload.name
        item.icon_key = payload.icon_key
        item.color_key = payload.color_key
        self._repository.flush()
        return DefaultIconCatalogRead.model_validate(item)

    def _delete(self, item: Base) -> CatalogDeleteResult:
        self._repository.delete(item)
        self._repository.flush()
        return CatalogDeleteResult.DELETED
