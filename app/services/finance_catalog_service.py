"""Logica de negocio de los catalogos de finanzas (categorias, metodos de
pago, tags). Las rutas dependen de esto, nunca del repository directamente.
"""

from app.repositories.finance_catalog_repository import FinanceCatalogRepository
from app.schemas.finance import CategoryRead, ExpenseOptionsRead, PaymentMethodRead, TagRead


class FinanceCatalogService:
    def __init__(self, repository: FinanceCatalogRepository) -> None:
        self._repository = repository

    def get_options(self, *, user_id: int) -> ExpenseOptionsRead:
        return ExpenseOptionsRead(
            categories=[
                CategoryRead.model_validate(c) for c in self._repository.list_enabled_categories()
            ],
            payment_methods=[
                PaymentMethodRead.model_validate(p)
                for p in self._repository.list_enabled_payment_methods()
            ],
            tags=[TagRead.model_validate(t) for t in self._repository.list_enabled_tags(user_id)],
        )
