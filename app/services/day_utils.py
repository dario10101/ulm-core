"""Formato CSV de dias (1-7) compartido por template tasks y generacion de semanas."""


def parse_days(day_of_week: str) -> list[int]:
    return [int(day) for day in day_of_week.split(",") if day]


def serialize_days(days: list[int]) -> str:
    return ",".join(str(day) for day in sorted(days))
