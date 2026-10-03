"""Interfaz (Protocol) del acceso a datos de los catalogos de finanzas
(categorias, metodos de pago, tags). La capa de servicio depende solo de
esto, nunca de una implementacion concreta (ver
app/repositories/weight_repository.py para el mismo patron).
"""

from collections.abc import Sequence
from typing import Protocol

from app.db.models.finance import Category, IncomeSource, IncomeSubcategory, PaymentMethod, Tag


class FinanceCatalogRepository(Protocol):
    def list_enabled_categories(self) -> Sequence[Category]: ...

    def list_enabled_payment_methods(self) -> Sequence[PaymentMethod]: ...

    def list_enabled_tags(self, user_id: int) -> Sequence[Tag]: ...

    def get_category(self, category_id: int) -> Category | None: ...

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
