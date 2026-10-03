"""Interfaz (Protocol) de las consultas agregadas de ingresos para
"Finance analysis -> Income". Separada de IncomeRepository porque no opera
sobre una tabla sino sobre la union de directos e intereses."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal, NamedTuple, Protocol

IncomeGroupBy = Literal["source", "subcategory", "tag", "month", "year"]
IncomeStack = Literal["source", "subcategory"]
IncomeKindName = Literal["direct", "interest"]


@dataclass(frozen=True)
class IncomeSummaryFilters:
    kind: IncomeKindName | None = None
    start_date: date | None = None
    end_date: date | None = None
    # Multi-seleccion: coincide si el ingreso tiene cualquiera de los ids.
    source_ids: Sequence[int] = field(default_factory=tuple)
    subcategory_ids: Sequence[int] = field(default_factory=tuple)
    tag_ids: Sequence[int] = field(default_factory=tuple)


class IncomeSummaryRow(NamedTuple):
    """Un grupo agregado. Para mes/año con desglose, hay una fila por
    (periodo, segmento) y el service las junta por periodo."""

    key: str
    label: str
    parent_label: str | None
    color_key: str | None
    total: Decimal
    count: int
    segment_key: str | None = None
    segment_label: str | None = None


class IncomeTotals(NamedTuple):
    total: Decimal
    count: int
    direct_total: Decimal
    interest_total: Decimal


class IncomeSummaryRepository(Protocol):
    def summarize(
        self,
        *,
        user_id: int,
        group_by: IncomeGroupBy,
        stack_by: IncomeStack | None,
        filters: IncomeSummaryFilters,
    ) -> tuple[Sequence[IncomeSummaryRow], IncomeTotals]:
        """Grupos + totales globales del filtro. El total global se calcula
        aparte: agrupando por tag, sumar los grupos contaria dos veces un
        ingreso con dos tags."""
        ...
