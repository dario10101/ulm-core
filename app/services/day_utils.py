"""Formato CSV de dias (1-7) compartido por template tasks y generacion de semanas."""

from datetime import date, timedelta


def parse_days(day_of_week: str) -> list[int]:
    return [int(day) for day in day_of_week.split(",") if day]


def serialize_days(days: list[int]) -> str:
    return ",".join(str(day) for day in sorted(days))


def resolve_date_for_day(first_day: date, day_of_week: int) -> date:
    """Fecha calendario real de un day_of_week ISO (1=Lunes...7=Domingo)
    dentro de una semana que empieza en first_day (no siempre un lunes: una
    semana puede arrancar cualquier dia). Usado para el rollup mensual, que
    necesita saber a que mes pertenece cada dia de una semana que puede
    cruzar fin de mes."""
    offset = (day_of_week - first_day.isoweekday()) % 7
    return first_day + timedelta(days=offset)
