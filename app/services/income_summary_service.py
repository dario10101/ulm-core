"""Logica del analisis de ingresos ("Finance analysis -> Income"). Las rutas
dependen de esto, nunca del repository directamente."""

from app.repositories.income_summary_repository import (
    IncomeSummaryFilters,
    IncomeSummaryRepository,
)
from app.schemas.finance import (
    IncomeStackBy,
    IncomeSummaryBucket,
    IncomeSummaryGroupBy,
    IncomeSummaryRead,
    IncomeSummarySegment,
)

_PERIOD_GROUPS = (IncomeSummaryGroupBy.MONTH, IncomeSummaryGroupBy.YEAR)


class IncomeSummaryService:
    def __init__(self, repository: IncomeSummaryRepository) -> None:
        self._repository = repository

    def summarize(
        self,
        *,
        user_id: int,
        group_by: IncomeSummaryGroupBy,
        stack_by: IncomeStackBy | None,
        filters: IncomeSummaryFilters,
    ) -> IncomeSummaryRead:
        # El desglose solo tiene sentido en series de tiempo: en las demas
        # vistas cada bucket ya es una fuente/subcategoria/tag.
        effective_stack = stack_by if group_by in _PERIOD_GROUPS else None
        rows, totals = self._repository.summarize(
            user_id=user_id,
            group_by=group_by.value,
            stack_by=effective_stack.value if effective_stack else None,
            filters=filters,
        )

        buckets: dict[str, IncomeSummaryBucket] = {}
        for row in rows:
            bucket = buckets.get(row.key)
            if bucket is None:
                bucket = IncomeSummaryBucket(
                    key=row.key,
                    label=row.label,
                    parent_label=row.parent_label,
                    color_key=row.color_key,
                    total=0,
                    count=0,
                )
                buckets[row.key] = bucket
            bucket.total += float(row.total)
            bucket.count += row.count
            if row.segment_key is not None:
                bucket.segments.append(
                    IncomeSummarySegment(
                        key=row.segment_key, label=row.segment_label or "", total=float(row.total)
                    )
                )

        return IncomeSummaryRead(
            group_by=group_by,
            stack_by=effective_stack,
            total=float(totals.total),
            count=totals.count,
            direct_total=float(totals.direct_total),
            interest_total=float(totals.interest_total),
            buckets=list(buckets.values()),
        )
