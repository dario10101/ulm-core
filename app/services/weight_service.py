"""Logica de negocio de registros de peso. Las rutas dependen de esto,
nunca del repository directamente."""

import math
from datetime import date
from decimal import Decimal

from app.repositories.weight_repository import WeightRepository
from app.schemas.weight import WeightRead
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
