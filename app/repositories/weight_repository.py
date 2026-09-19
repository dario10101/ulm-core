"""Interfaz (Protocol) del acceso a datos de registros de peso.

La capa de servicio depende solo de esto, nunca de una implementacion concreta.
Cuando se quiera evaluar otro tipo de almacenamiento (llave-valor, documental),
alcanza con escribir una clase nueva que cumpla este Protocol.
"""

from datetime import date
from decimal import Decimal
from typing import Protocol, Sequence

from app.db.models.weight import WeightRecord


class WeightRepository(Protocol):
    def create(
        self, *, user_id: int, weight_kg: Decimal, recorded_on: date, note: str | None
    ) -> WeightRecord: ...

    def list(
        self,
        *,
        user_id: int,
        start_date: date | None,
        end_date: date | None,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[WeightRecord], int]: ...

    def get(self, weight_id: int) -> WeightRecord | None: ...

    def update(
        self, weight_id: int, *, weight_kg: Decimal, recorded_on: date, note: str | None
    ) -> WeightRecord | None: ...

    def delete(self, weight_id: int) -> bool: ...
