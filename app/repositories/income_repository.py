"""Interfaz (Protocol) del acceso a datos de registros de ingreso (directos e
intereses). La capa de servicio depende solo de esto, nunca de una
implementacion concreta (ver app/repositories/weight_repository.py).

A diferencia de ExpenseRepository, los campos del registro viajan como un
dict (`fields`): son dos tablas con columnas distintas pero exactamente las
mismas operaciones, y una sola implementacion generica evita duplicar todo
el CRUD. El tipado fuerte de esos campos lo garantiza el schema Pydantic de
entrada, antes de llegar aca.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Protocol, TypeVar

from app.db.models.finance import DirectIncome, InterestIncome, Tag

IncomeRecord = TypeVar("IncomeRecord", DirectIncome, InterestIncome)


@dataclass(frozen=True)
class IncomeFilters:
    start_date: date | None = None
    end_date: date | None = None
    source_id: int | None = None
    subcategory_id: int | None = None
    tag_ids: Sequence[int] = field(default_factory=tuple)
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None


class IncomeRepository(Protocol[IncomeRecord]):
    def create(
        self, *, user_id: int, fields: Mapping[str, Any], tags: Sequence[Tag]
    ) -> IncomeRecord: ...

    def list(
        self, *, user_id: int, filters: IncomeFilters, offset: int, limit: int
    ) -> tuple[Sequence[IncomeRecord], int]: ...

    def update(
        self, record_id: int, *, user_id: int, fields: Mapping[str, Any], tags: Sequence[Tag]
    ) -> IncomeRecord | None:
        """None si no existe **o no es de ese usuario** (indistinguibles a proposito)."""
        ...

    def delete(self, record_id: int, *, user_id: int) -> bool: ...


class InterestIncomeRepository(IncomeRepository[InterestIncome], Protocol):
    def find_period(
        self, *, user_id: int, source_id: int, subcategory_id: int, period_start: date
    ) -> int | None:
        """Id del registro de esa fuente y subcategoria en ese mes, si existe."""
        ...

    def list_end_balances(self, *, user_id: int) -> Sequence[tuple[int, int, date, Decimal]]:
        """(source_id, subcategory_id, recorded_on, end_of_month_amount) de los
        meses con saldo final."""
        ...
