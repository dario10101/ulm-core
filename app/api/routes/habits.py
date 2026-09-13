"""Rutas dummy del modulo de habitos, pendiente de conectar a base de datos."""

from fastapi import APIRouter

from app.models.habit import Habit

router = APIRouter(prefix="/habits", tags=["habits"])

# Datos en memoria solo para demostrar el esqueleto funcional
_fake_habits = [
    Habit(id=1, name="Leer 20 minutos", streak_days=3),
    Habit(id=2, name="Ejercicio", streak_days=1),
]


@router.get("/", response_model=list[Habit])
def list_habits() -> list[Habit]:
    # Lista dummy, en el futuro vendra de PostgreSQL
    return _fake_habits
