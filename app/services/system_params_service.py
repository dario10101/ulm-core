"""Parametros globales del sistema que solo administra el admin: categorias de
gasto y metodos de pago (catalogos compartidos por todos los usuarios).

Mismo borrado hibrido que FinanceParamsService, pero el uso se cuenta sobre
los gastos de *todos* los usuarios: archivar una categoria que solo usa otra
persona sigue siendo archivar, nunca borrarle el historico.
"""

from collections.abc import Callable, Sequence

from app.db.models.finance import Category, PaymentMethod
from app.repositories.finance_catalog_repository import FinanceCatalogRepository
from app.schemas.finance import (
    CatalogDeleteResult,
    CategoryAdminRead,
    CategoryRead,
    IconCatalogWrite,
    PaymentMethodAdminRead,
    PaymentMethodRead,
)
from app.services.catalog_rules import delete_or_archive, ensure_unique_name
from app.services.errors import CatalogItemNotFoundError

IconCatalogItem = Category | PaymentMethod


class SystemParamsService:
    def __init__(self, repository: FinanceCatalogRepository) -> None:
        self._repository = repository

    # --- Categorias de gasto ---

    def list_categories(self) -> list[CategoryAdminRead]:
        usage = self._repository.category_usage()
        return [
            self._category_read(c, usage.get(c.id, 0))
            for c in self._repository.list_all_categories()
        ]

    def create_category(self, payload: IconCatalogWrite) -> CategoryAdminRead:
        category = self._create(Category, payload, self._repository.list_all_categories())
        return self._category_read(category, 0)

    def update_category(self, category_id: int, payload: IconCatalogWrite) -> CategoryAdminRead:
        category = self._update(
            self._repository.get_category(category_id),
            "Categoria",
            category_id,
            payload,
            self._repository.list_all_categories(),
        )
        return self._category_read(category, self._repository.category_usage().get(category.id, 0))

    def delete_category(self, category_id: int) -> CatalogDeleteResult:
        return self._delete(
            self._repository.get_category(category_id),
            "Categoria",
            category_id,
            self._repository.category_usage,
        )

    @staticmethod
    def _category_read(category: Category, usage_count: int) -> CategoryAdminRead:
        return CategoryAdminRead(
            **CategoryRead.model_validate(category).model_dump(), usage_count=usage_count
        )

    # --- Metodos de pago ---

    def list_payment_methods(self) -> list[PaymentMethodAdminRead]:
        usage = self._repository.payment_method_usage()
        return [
            self._payment_method_read(p, usage.get(p.id, 0))
            for p in self._repository.list_all_payment_methods()
        ]

    def create_payment_method(self, payload: IconCatalogWrite) -> PaymentMethodAdminRead:
        method = self._create(PaymentMethod, payload, self._repository.list_all_payment_methods())
        return self._payment_method_read(method, 0)

    def update_payment_method(
        self, payment_method_id: int, payload: IconCatalogWrite
    ) -> PaymentMethodAdminRead:
        method = self._update(
            self._repository.get_payment_method(payment_method_id),
            "Metodo de pago",
            payment_method_id,
            payload,
            self._repository.list_all_payment_methods(),
        )
        return self._payment_method_read(
            method, self._repository.payment_method_usage().get(method.id, 0)
        )

    def delete_payment_method(self, payment_method_id: int) -> CatalogDeleteResult:
        return self._delete(
            self._repository.get_payment_method(payment_method_id),
            "Metodo de pago",
            payment_method_id,
            self._repository.payment_method_usage,
        )

    @staticmethod
    def _payment_method_read(method: PaymentMethod, usage_count: int) -> PaymentMethodAdminRead:
        return PaymentMethodAdminRead(
            **PaymentMethodRead.model_validate(method).model_dump(), usage_count=usage_count
        )

    # --- Comun: los dos catalogos tienen exactamente los mismos campos ---

    def _create[T: IconCatalogItem](
        self, model: type[T], payload: IconCatalogWrite, siblings: Sequence[IconCatalogItem]
    ) -> T:
        ensure_unique_name(payload.name, siblings)
        item = model(
            name=payload.name,
            icon_key=payload.icon_key,
            color_key=payload.color_key,
            status=payload.status.value,
        )
        self._repository.add(item)
        self._repository.flush()
        return item

    def _update[T: IconCatalogItem](
        self,
        item: T | None,
        label: str,
        item_id: int,
        payload: IconCatalogWrite,
        siblings: Sequence[IconCatalogItem],
    ) -> T:
        if item is None:
            raise CatalogItemNotFoundError(label, item_id)
        ensure_unique_name(payload.name, siblings, exclude_id=item.id)
        item.name = payload.name
        item.icon_key = payload.icon_key
        item.color_key = payload.color_key
        item.status = payload.status.value
        self._repository.flush()
        return item

    def _delete(
        self,
        item: IconCatalogItem | None,
        label: str,
        item_id: int,
        usage: Callable[[], dict[int, int]],
    ) -> CatalogDeleteResult:
        if item is None:
            raise CatalogItemNotFoundError(label, item_id)
        result = delete_or_archive(
            item, usage_count=usage().get(item.id, 0), delete=self._repository.delete
        )
        self._repository.flush()
        return result
