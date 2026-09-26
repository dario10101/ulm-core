"""Logica de negocio de registros de comida. Las rutas dependen de esto,
nunca del repository directamente.

Zona horaria: `recorded_on` entra y sale de este service en hora de pared del
usuario (naive); la conversion a/desde UTC (lo que guarda la BD) pasa aca
adentro, usando la zona que llega por parametro (ver cld_task_sync)."""

import math
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.repositories.meal_repository import MealRepository
from app.schemas.meal import MealComponentIn, MealRead
from app.services.cld_task_sync import to_utc
from app.services.errors import MealNotFoundError
from app.services.mappers import meal_to_read
from app.services.meal_content import serialize_meal_content


class MealService:
    def __init__(self, repository: MealRepository) -> None:
        self._repository = repository

    def create_meal(
        self,
        *,
        user_id: int,
        tz: ZoneInfo,
        recorded_on: datetime,
        meal_type: str,
        meal_size: int,
        components: list[MealComponentIn],
        drink: str | None,
        note: str | None,
    ) -> MealRead:
        record = self._repository.create(
            user_id=user_id,
            recorded_on=to_utc(recorded_on, tz),
            meal_type=meal_type,
            meal_size=meal_size,
            meal_content=serialize_meal_content([(c.name, c.percent) for c in components]),
            drink=drink.strip().upper() if drink and drink.strip() else None,
            note=note,
        )
        return meal_to_read(record, tz)

    def list_meals(
        self,
        *,
        user_id: int,
        tz: ZoneInfo,
        start_date: date | None,
        end_date: date | None,
        page: int,
        page_size: int,
    ) -> tuple[list[MealRead], int, int]:
        # start_date/end_date son dias civiles del usuario: se convierten al
        # instante UTC de su inicio/fin para que el filtro respete su zona
        # horaria en vez de la del servidor.
        start_at = to_utc(datetime.combine(start_date, time.min), tz) if start_date else None
        end_at = to_utc(datetime.combine(end_date, time.max), tz) if end_date else None

        offset = (page - 1) * page_size
        items, total = self._repository.list(
            user_id=user_id,
            start_at=start_at,
            end_at=end_at,
            offset=offset,
            limit=page_size,
        )
        total_pages = math.ceil(total / page_size) if total else 0
        return [meal_to_read(item, tz) for item in items], total, total_pages

    def update_meal(
        self,
        meal_id: int,
        *,
        user_id: int,
        tz: ZoneInfo,
        recorded_on: datetime,
        meal_type: str,
        meal_size: int,
        components: list[MealComponentIn],
        drink: str | None,
        note: str | None,
    ) -> MealRead:
        record = self._repository.update(
            meal_id,
            user_id=user_id,
            recorded_on=to_utc(recorded_on, tz),
            meal_type=meal_type,
            meal_size=meal_size,
            meal_content=serialize_meal_content([(c.name, c.percent) for c in components]),
            drink=drink.strip().upper() if drink and drink.strip() else None,
            note=note,
        )
        if record is None:
            raise MealNotFoundError(meal_id)
        return meal_to_read(record, tz)

    def delete_meal(self, meal_id: int, *, user_id: int) -> None:
        deleted = self._repository.delete(meal_id, user_id=user_id)
        if not deleted:
            raise MealNotFoundError(meal_id)
