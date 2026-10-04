"""Logica de negocio de ingresos (directos e intereses) y de sus catalogos.
Las rutas dependen de esto, nunca de los repositories directamente."""

import math
from datetime import date
from decimal import Decimal

from app.db.models.finance import DirectIncome, IncomeSource, IncomeSubcategory, Tag
from app.repositories.finance_catalog_repository import FinanceCatalogRepository
from app.repositories.income_repository import (
    IncomeFilters,
    IncomeRepository,
    InterestIncomeRepository,
)
from app.schemas.finance import (
    CatalogStatus,
    DirectIncomeCreate,
    DirectIncomeRead,
    IncomeKind,
    IncomeOptionsRead,
    IncomeSourceRead,
    IncomeSubcategoryRead,
    InterestEndBalance,
    InterestIncomeCreate,
    InterestIncomeRead,
    TagRead,
)
from app.services.errors import (
    IncomeNotFoundError,
    IncomeSourceNotFoundError,
    IncomeSubcategoryNotFoundError,
    InterestPeriodTakenError,
    TagNotFoundError,
)
from app.services.mappers import direct_income_to_read, interest_income_to_read


def _applies_to(catalog_type: str, kind: IncomeKind) -> bool:
    return catalog_type in (kind.value, IncomeKind.ALL.value)


def _usable(item: IncomeSource | IncomeSubcategory | Tag, allow_archived: bool) -> bool:
    return allow_archived or item.status == CatalogStatus.ENABLED.value


class IncomeService:
    def __init__(
        self,
        direct_repository: IncomeRepository[DirectIncome],
        interest_repository: InterestIncomeRepository,
        catalog_repository: FinanceCatalogRepository,
    ) -> None:
        self._direct_repository = direct_repository
        self._interest_repository = interest_repository
        self._catalog_repository = catalog_repository

    def get_options(self, *, user_id: int) -> IncomeOptionsRead:
        return IncomeOptionsRead(
            sources=[
                IncomeSourceRead.model_validate(s)
                for s in self._catalog_repository.list_income_sources(user_id)
                if s.status == CatalogStatus.ENABLED.value
            ],
            subcategories=[
                IncomeSubcategoryRead.model_validate(s)
                for s in self._catalog_repository.list_income_subcategories(user_id)
                if s.status == CatalogStatus.ENABLED.value
            ],
            tags=[
                TagRead.model_validate(t)
                for t in self._catalog_repository.list_enabled_tags(user_id)
            ],
            interest_end_balances=[
                InterestEndBalance(
                    source_id=source_id,
                    period=recorded_on.strftime("%Y-%m"),
                    end_of_month_amount=float(amount),
                )
                for source_id, recorded_on, amount in self._interest_repository.list_end_balances(
                    user_id=user_id
                )
            ],
        )

    def _validate_references(
        self,
        *,
        kind: IncomeKind,
        user_id: int,
        source_id: int,
        subcategory_id: int,
        tag_ids: list[int],
        allow_archived: bool,
    ) -> list[Tag]:
        """La fuente debe ser del usuario y aplicar a este tipo de ingreso (una
        fuente INTEREST no sirve para un ingreso directo), y la subcategoria
        debe pertenecer a esa fuente. El `type` de la subcategoria no se mira:
        lo determina su fuente.

        Un item archivado no sirve para un registro nuevo, pero si al editar
        uno viejo: si no, corregir el monto de un ingreso de una fuente
        archivada obligaria a cambiarle la fuente."""
        source = self._catalog_repository.get_income_source(user_id, source_id)
        if (
            source is None
            or not _applies_to(source.type, kind)
            or not _usable(source, allow_archived)
        ):
            raise IncomeSourceNotFoundError(source_id)
        subcategory = self._catalog_repository.get_income_subcategory(user_id, subcategory_id)
        if (
            subcategory is None
            or subcategory.source_id != source_id
            or not _usable(subcategory, allow_archived)
        ):
            raise IncomeSubcategoryNotFoundError(subcategory_id)

        tags = self._catalog_repository.list_tags_by_ids(user_id, tag_ids)
        missing_tag_ids = set(tag_ids) - {tag.id for tag in tags if _usable(tag, allow_archived)}
        if missing_tag_ids:
            raise TagNotFoundError(missing_tag_ids)
        return list(tags)

    @staticmethod
    def _page(total: int, page_size: int) -> int:
        return math.ceil(total / page_size) if total else 0

    # --- Directos ---

    def create_direct(self, *, user_id: int, payload: DirectIncomeCreate) -> DirectIncomeRead:
        tags = self._validate_references(
            kind=IncomeKind.DIRECT,
            user_id=user_id,
            source_id=payload.source_id,
            subcategory_id=payload.subcategory_id,
            tag_ids=payload.tag_ids,
            allow_archived=False,
        )
        record = self._direct_repository.create(
            user_id=user_id, fields=payload.model_dump(exclude={"tag_ids"}), tags=tags
        )
        return direct_income_to_read(record)

    def update_direct(
        self, record_id: int, *, user_id: int, payload: DirectIncomeCreate
    ) -> DirectIncomeRead:
        tags = self._validate_references(
            kind=IncomeKind.DIRECT,
            user_id=user_id,
            source_id=payload.source_id,
            subcategory_id=payload.subcategory_id,
            tag_ids=payload.tag_ids,
            allow_archived=True,
        )
        record = self._direct_repository.update(
            record_id, user_id=user_id, fields=payload.model_dump(exclude={"tag_ids"}), tags=tags
        )
        if record is None:
            raise IncomeNotFoundError(record_id)
        return direct_income_to_read(record)

    def delete_direct(self, record_id: int, *, user_id: int) -> None:
        if not self._direct_repository.delete(record_id, user_id=user_id):
            raise IncomeNotFoundError(record_id)

    def list_direct(
        self, *, user_id: int, filters: IncomeFilters, page: int, page_size: int
    ) -> tuple[list[DirectIncomeRead], int, int]:
        items, total = self._direct_repository.list(
            user_id=user_id, filters=filters, offset=(page - 1) * page_size, limit=page_size
        )
        return [direct_income_to_read(i) for i in items], total, self._page(total, page_size)

    # --- Intereses ---

    def _interest_fields(
        self, *, user_id: int, payload: InterestIncomeCreate, record_id: int | None
    ) -> tuple[dict, list[Tag]]:
        tags = self._validate_references(
            kind=IncomeKind.INTEREST,
            user_id=user_id,
            source_id=payload.source_id,
            subcategory_id=payload.subcategory_id,
            tag_ids=payload.tag_ids,
            allow_archived=record_id is not None,
        )
        # El registro es del mes, no de un dia: se normaliza al dia 1 para que
        # la unicidad (fuente, mes) sea una comparacion de igualdad.
        period_start = payload.recorded_on.replace(day=1)
        existing_id = self._interest_repository.find_period(
            user_id=user_id, source_id=payload.source_id, period_start=period_start
        )
        if existing_id is not None and existing_id != record_id:
            raise InterestPeriodTakenError()

        fields = payload.model_dump(exclude={"tag_ids"})
        fields["recorded_on"] = period_start
        return fields, tags

    def create_interest(self, *, user_id: int, payload: InterestIncomeCreate) -> InterestIncomeRead:
        fields, tags = self._interest_fields(user_id=user_id, payload=payload, record_id=None)
        record = self._interest_repository.create(user_id=user_id, fields=fields, tags=tags)
        return interest_income_to_read(record)

    def update_interest(
        self, record_id: int, *, user_id: int, payload: InterestIncomeCreate
    ) -> InterestIncomeRead:
        fields, tags = self._interest_fields(user_id=user_id, payload=payload, record_id=record_id)
        record = self._interest_repository.update(
            record_id, user_id=user_id, fields=fields, tags=tags
        )
        if record is None:
            raise IncomeNotFoundError(record_id)
        return interest_income_to_read(record)

    def delete_interest(self, record_id: int, *, user_id: int) -> None:
        if not self._interest_repository.delete(record_id, user_id=user_id):
            raise IncomeNotFoundError(record_id)

    def list_interest(
        self, *, user_id: int, filters: IncomeFilters, page: int, page_size: int
    ) -> tuple[list[InterestIncomeRead], int, int]:
        items, total = self._interest_repository.list(
            user_id=user_id, filters=filters, offset=(page - 1) * page_size, limit=page_size
        )
        return [interest_income_to_read(i) for i in items], total, self._page(total, page_size)


def build_filters(
    *,
    start_date: date | None,
    end_date: date | None,
    source_id: int | None,
    subcategory_id: int | None,
    tag_ids: list[int] | None,
    min_amount: float | None,
    max_amount: float | None,
) -> IncomeFilters:
    return IncomeFilters(
        start_date=start_date,
        end_date=end_date,
        source_id=source_id,
        subcategory_id=subcategory_id,
        tag_ids=tuple(tag_ids or ()),
        min_amount=Decimal(str(min_amount)) if min_amount is not None else None,
        max_amount=Decimal(str(max_amount)) if max_amount is not None else None,
    )
