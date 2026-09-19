"""Esquemas Pydantic de entrada/salida para la tabla dummy."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DummyCreate(BaseModel):
    name: str
    description: str | None = None
    value: float = 0.0
    is_active: bool = True


class DummyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    value: float
    is_active: bool
    created_at: datetime
