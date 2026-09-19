"""Logica de negocio de registros de peso. Las rutas dependen de esto,
nunca del repository directamente."""

import math
from datetime import date
from decimal import Decimal
from typing import Sequence

from app.db.models.weight import WeightRecord
from app.repositories.weight_repository import WeightRepository


class WeightNotFoundError(Exception):
    """El registro de peso solicitado no existe."""


class WeightService:
    def __init__(self, repository: WeightRepository) -> None:
        self._repository = repository

    def create_weight(
        self, *, user_id: int, weight_kg: Decimal, recorded_on: date, note: str | None
    ) -> WeightRecord:
        return self._repository.create(
            user_id=user_id, weight_kg=weight_kg, recorded_on=recorded_on, note=note
        )

    def list_weights(
        self,
        *,
        user_id: int,
        start_date: date | None,
        end_date: date | None,
        page: int,
        page_size: int,
    ) -> tuple[Sequence[WeightRecord], int, int]:
        offset = (page - 1) * page_size
        items, total = self._repository.list(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            offset=offset,
            limit=page_size,
        )
        total_pages = math.ceil(total / page_size) if total else 0
        return items, total, total_pages

    def update_weight(
        self, weight_id: int, *, weight_kg: Decimal, recorded_on: date, note: str | None
    ) -> WeightRecord:
        record = self._repository.update(
            weight_id, weight_kg=weight_kg, recorded_on=recorded_on, note=note
        )
        if record is None:
            raise WeightNotFoundError(weight_id)
        return record

    def delete_weight(self, weight_id: int) -> None:
        deleted = self._repository.delete(weight_id)
        if not deleted:
            raise WeightNotFoundError(weight_id)
