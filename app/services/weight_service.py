"""Logica de negocio de registros de peso. Las rutas dependen de esto,
nunca del repository directamente."""

import math
from datetime import date
from decimal import Decimal

from app.repositories.weight_repository import WeightRepository
from app.schemas.weight import (
    WeightRead,
    WeightSummaryBucket,
    WeightSummaryGroupBy,
    WeightSummaryRead,
)
from app.services.errors import WeightNotFoundError
from app.services.mappers import weight_to_read


class WeightService:
    def __init__(self, repository: WeightRepository) -> None:
        self._repository = repository

    def create_weight(
        self, *, user_id: int, weight_kg: Decimal, recorded_on: date, note: str | None
    ) -> WeightRead:
        return weight_to_read(
            self._repository.create(
                user_id=user_id, weight_kg=weight_kg, recorded_on=recorded_on, note=note
            )
        )

    def list_weights(
        self,
        *,
        user_id: int,
        start_date: date | None,
        end_date: date | None,
        page: int,
        page_size: int,
    ) -> tuple[list[WeightRead], int, int]:
        offset = (page - 1) * page_size
        items, total = self._repository.list(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            offset=offset,
            limit=page_size,
        )
        total_pages = math.ceil(total / page_size) if total else 0
        return [weight_to_read(item) for item in items], total, total_pages

    def summarize_weights(
        self,
        *,
        user_id: int,
        group_by: WeightSummaryGroupBy,
        start_date: date | None,
        end_date: date | None,
    ) -> WeightSummaryRead:
        rows = self._repository.summarize(
            user_id=user_id, group_by=group_by, start_date=start_date, end_date=end_date
        )
        count = sum(row_count for _, _, row_count in rows)
        # Promedio global ponderado por cantidad de registros (= promedio de
        # todos los pesajes del rango), no promedio de los promedios por periodo.
        total = sum((average * row_count for _, average, row_count in rows), Decimal(0))
        return WeightSummaryRead(
            buckets=[
                WeightSummaryBucket(key=key, average_kg=round(float(average), 2), count=row_count)
                for key, average, row_count in rows
            ],
            average_kg=round(float(total / count), 2) if count else None,
            count=count,
            available_years=list(self._repository.list_years(user_id=user_id)),
        )

    def update_weight(
        self,
        weight_id: int,
        *,
        user_id: int,
        weight_kg: Decimal,
        recorded_on: date,
        note: str | None,
    ) -> WeightRead:
        record = self._repository.update(
            weight_id, user_id=user_id, weight_kg=weight_kg, recorded_on=recorded_on, note=note
        )
        if record is None:
            raise WeightNotFoundError(weight_id)
        return weight_to_read(record)

    def delete_weight(self, weight_id: int, *, user_id: int) -> None:
        deleted = self._repository.delete(weight_id, user_id=user_id)
        if not deleted:
            raise WeightNotFoundError(weight_id)
