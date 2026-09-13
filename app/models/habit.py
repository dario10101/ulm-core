"""Modelo dummy de habito, punto de partida para el modulo de gestion de habitos."""

from pydantic import BaseModel


class Habit(BaseModel):
    id: int
    name: str
    streak_days: int = 0
