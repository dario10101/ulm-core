"""Interfaz (Protocol) del acceso a datos de los catalogos de finanzas
(categorias, metodos de pago, tags, fuentes y subcategorias de ingreso). La
capa de servicio depende solo de esto, nunca de una implementacion concreta (ver
app/repositories/weight_repository.py para el mismo patron).
"""

from collections.abc import Sequence
from typing import Protocol

from app.db.base_class import Base
from app.db.models.finance import (
    Category,
    DefaultExpenseCategory,
    IncomeSource,
    IncomeSubcategory,
    PaymentMethod,
    Tag,
)


class FinanceCatalogRepository(Protocol):
    def list_enabled_categories(self, user_id: int) -> Sequence[Category]: ...

    def list_enabled_payment_methods(self) -> Sequence[PaymentMethod]: ...

    def list_enabled_tags(self, user_id: int) -> Sequence[Tag]: ...

    def get_category(self, user_id: int, category_id: int) -> Category | None:
        """None si no existe o no es de ese usuario."""
        ...

    def get_payment_method(self, payment_method_id: int) -> PaymentMethod | None: ...

    def list_tags_by_ids(self, user_id: int, tag_ids: Sequence[int]) -> Sequence[Tag]:
        """Solo tags del usuario indicado, sin filtrar por status: un gasto
        viejo puede referenciar un tag ya DISABLED y debe poder seguir
        leyendose."""
        ...

    def list_income_sources(self, user_id: int) -> Sequence[IncomeSource]: ...

    def list_income_subcategories(self, user_id: int) -> Sequence[IncomeSubcategory]: ...

    def get_income_source(self, user_id: int, source_id: int) -> IncomeSource | None:
        """None si no existe o no es de ese usuario."""
        ...

    def get_income_subcategory(
        self, user_id: int, subcategory_id: int
    ) -> IncomeSubcategory | None: ...

    # --- Administracion (Settings y "View records") ---

    def list_categories(self, user_id: int) -> Sequence[Category]:
        """Todas las categorias del usuario, incluidas las archivadas."""
        ...

    def list_default_categories(self) -> Sequence[DefaultExpenseCategory]: ...

    def get_default_category(self, category_id: int) -> DefaultExpenseCategory | None: ...

    def copy_default_categories(self, user_id: int) -> None:
        """Le da al usuario su propia copia de la plantilla (al registrarse)."""
        ...

    def list_all_payment_methods(self) -> Sequence[PaymentMethod]: ...

    def list_tags(self, user_id: int) -> Sequence[Tag]:
        """Todos los tags del usuario, incluidos los archivados."""
        ...

    def get_tag(self, user_id: int, tag_id: int) -> Tag | None: ...

    # Conteos de uso: id -> cantidad de registros que lo referencian. Un id
    # sin registros no aparece en el dict.

    def category_usage(self, user_id: int) -> dict[int, int]: ...

    def payment_method_usage(self) -> dict[int, int]: ...

    def tag_usage(self, user_id: int) -> dict[int, int]:
        """Gastos + ingresos directos + ingresos de intereses."""
        ...

    def source_usage(self, user_id: int) -> dict[int, tuple[int, int]]:
        """id -> (ingresos directos, ingresos de intereses)."""
        ...

    def subcategory_usage(self, user_id: int) -> dict[int, int]: ...

    def add(self, item: Base) -> None: ...

    def delete(self, item: Base) -> None: ...

    def flush(self) -> None: ...
