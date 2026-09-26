"""Interfaz (Protocol) del acceso a datos de registros de comida.

La capa de servicio depende solo de esto, nunca de una implementacion concreta
(ver app/repositories/weight_repository.py para el mismo patron).
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from app.db.models.meal import Meal


class MealRepository(Protocol):
    def create(
        self,
        *,
        user_id: int,
        recorded_on: datetime,
        meal_type: str,
        meal_size: int,
        meal_content: str | None,
        drink: str | None,
        note: str | None,
    ) -> Meal: ...

    def list(
        self,
        *,
        user_id: int,
        start_at: datetime | None,
        end_at: datetime | None,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[Meal], int]: ...

    def get(self, meal_id: int) -> Meal | None: ...

    def update(
        self,
        meal_id: int,
        *,
        user_id: int,
        recorded_on: datetime,
        meal_type: str,
        meal_size: int,
        meal_content: str | None,
        drink: str | None,
        note: str | None,
    ) -> Meal | None:
        """Devuelve None si el registro no existe **o no es de ese usuario**:
        quien no es dueño no puede distinguir un caso del otro."""
        ...

    def delete(self, meal_id: int, *, user_id: int) -> bool:
        """False si no existe o no es de ese usuario (misma razon que update)."""
        ...
