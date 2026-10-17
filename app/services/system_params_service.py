"""Parametros globales del sistema que solo administra el admin: la plantilla
de categorias de gasto para usuarios nuevos y los metodos de pago.

- Plantilla: se copia a cada usuario al registrarse (ver
  UserAdminService.register) y nada la referencia despues, asi que borrar es
  borrar. Cambiarla no toca las categorias de los usuarios que ya existen.
- Metodos de pago: catalogo compartido por todos. Mismo borrado hibrido que
  FinanceParamsService, pero el uso se cuenta sobre los gastos de *todos* los
  usuarios: archivar un metodo que solo usa otra persona sigue siendo
  archivar, nunca borrarle el historico.
"""

from app.db.models.finance import DefaultExpenseCategory, PaymentMethod
from app.repositories.finance_catalog_repository import FinanceCatalogRepository
from app.schemas.finance import (
    CatalogDeleteResult,
    DefaultCategoryRead,
    DefaultCategoryWrite,
    IconCatalogWrite,
    PaymentMethodAdminRead,
    PaymentMethodRead,
)
from app.services.catalog_rules import delete_or_archive, ensure_unique_name
from app.services.errors import CatalogItemNotFoundError, CatalogNameTakenError


class SystemParamsService:
    def __init__(self, repository: FinanceCatalogRepository) -> None:
        self._repository = repository

    # --- Plantilla de categorias de gasto ---

    def list_default_categories(self) -> list[DefaultCategoryRead]:
        return [
            DefaultCategoryRead.model_validate(c)
            for c in self._repository.list_default_categories()
        ]

    def create_default_category(self, payload: DefaultCategoryWrite) -> DefaultCategoryRead:
        # Los items de la plantilla no tienen status: para la regla de nombre
        # unico cuentan como activos.
        self._ensure_unique_default_name(payload.name)
        category = DefaultExpenseCategory(
            name=payload.name, icon_key=payload.icon_key, color_key=payload.color_key
        )
        self._repository.add(category)
        self._repository.flush()
        return DefaultCategoryRead.model_validate(category)

    def update_default_category(
        self, category_id: int, payload: DefaultCategoryWrite
    ) -> DefaultCategoryRead:
        category = self._get_default_category(category_id)
        self._ensure_unique_default_name(payload.name, exclude_id=category.id)
        category.name = payload.name
        category.icon_key = payload.icon_key
        category.color_key = payload.color_key
        self._repository.flush()
        return DefaultCategoryRead.model_validate(category)

    def delete_default_category(self, category_id: int) -> CatalogDeleteResult:
        self._repository.delete(self._get_default_category(category_id))
        self._repository.flush()
        return CatalogDeleteResult.DELETED

    def _get_default_category(self, category_id: int) -> DefaultExpenseCategory:
        category = self._repository.get_default_category(category_id)
        if category is None:
            raise CatalogItemNotFoundError("Categoria", category_id)
        return category

    def _ensure_unique_default_name(self, name: str, *, exclude_id: int | None = None) -> None:
        wanted = name.casefold()
        for item in self._repository.list_default_categories():
            if item.id != exclude_id and item.name.casefold() == wanted:
                raise CatalogNameTakenError(item.name, archived=False)

    # --- Metodos de pago ---

    def list_payment_methods(self) -> list[PaymentMethodAdminRead]:
        usage = self._repository.payment_method_usage()
        return [
            self._payment_method_read(p, usage.get(p.id, 0))
            for p in self._repository.list_all_payment_methods()
        ]

    def create_payment_method(self, payload: IconCatalogWrite) -> PaymentMethodAdminRead:
        ensure_unique_name(payload.name, self._repository.list_all_payment_methods())
        method = PaymentMethod(
            name=payload.name,
            icon_key=payload.icon_key,
            color_key=payload.color_key,
            status=payload.status.value,
        )
        self._repository.add(method)
        self._repository.flush()
        return self._payment_method_read(method, 0)

    def update_payment_method(
        self, payment_method_id: int, payload: IconCatalogWrite
    ) -> PaymentMethodAdminRead:
        method = self._get_payment_method(payment_method_id)
        ensure_unique_name(
            payload.name, self._repository.list_all_payment_methods(), exclude_id=method.id
        )
        method.name = payload.name
        method.icon_key = payload.icon_key
        method.color_key = payload.color_key
        method.status = payload.status.value
        self._repository.flush()
        return self._payment_method_read(
            method, self._repository.payment_method_usage().get(method.id, 0)
        )

    def delete_payment_method(self, payment_method_id: int) -> CatalogDeleteResult:
        method = self._get_payment_method(payment_method_id)
        result = delete_or_archive(
            method,
            usage_count=self._repository.payment_method_usage().get(method.id, 0),
            delete=self._repository.delete,
        )
        self._repository.flush()
        return result

    def _get_payment_method(self, payment_method_id: int) -> PaymentMethod:
        method = self._repository.get_payment_method(payment_method_id)
        if method is None:
            raise CatalogItemNotFoundError("Metodo de pago", payment_method_id)
        return method

    @staticmethod
    def _payment_method_read(method: PaymentMethod, usage_count: int) -> PaymentMethodAdminRead:
        return PaymentMethodAdminRead(
            **PaymentMethodRead.model_validate(method).model_dump(), usage_count=usage_count
        )
