"""Sugerencia de cambio de nivel (ENGLISH-TEACHER-PLAN.md, seccion 4.1).

Reglas escritas a mano, sin LLM ni modelo entrenado (C7): con pocos usuarios
no hay datos para entrenar, y una regla se puede explicar. Los umbrales son
una suposicion inicial; son justo lo que una regresion podria reemplazar
cuando haya historial suficiente.

Sobre las ultimas WINDOW practicas del nivel actual:
- Subir si se cumplen las tres: acerto la palabra sola >= 80%, entendio el
  listening sin texto >= 80% y leyo con coincidencia promedio >= 90%.
- Bajar si se cumplen dos de tres: <= 30%, <= 30% y <= 60%.
- Tambien subir si ya domina todas las palabras del nivel (D19).

Es una sugerencia: el usuario decide. Despues de un "no por ahora" no se
vuelve a sugerir nada hasta juntar WINDOW practicas nuevas.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.db.models.english import EngPractice
from app.services.english_levels import EnglishLevel, next_level, previous_level

WINDOW = 10

UP_GUESSED_PCT = 80
UP_LISTENING_PCT = 80
UP_READING_PCT = 90
DOWN_GUESSED_PCT = 30
DOWN_LISTENING_PCT = 30
DOWN_READING_PCT = 60


@dataclass(frozen=True)
class LevelSuggestion:
    direction: str  # "up" | "down"
    level: EnglishLevel
    reason: str  # "performance" | "completed"


@dataclass(frozen=True)
class LevelSignals:
    guessed_pct: float
    listening_pct: float
    # Promedio de las practicas con lectura grabada; None si ninguna tiene.
    reading_pct: float | None


def signals(practices: Sequence[EngPractice]) -> LevelSignals:
    total = len(practices)
    guessed = sum(1 for p in practices if not p.vocab_revealed)
    by_ear = sum(1 for p in practices if not p.listening_text_shown)
    readings = [p.reading_match_pct for p in practices if p.reading_match_pct is not None]
    return LevelSignals(
        guessed_pct=100 * guessed / total,
        listening_pct=100 * by_ear / total,
        reading_pct=sum(readings) / len(readings) if readings else None,
    )


def suggest(
    *,
    level: EnglishLevel,
    practices: Sequence[EngPractice],
    level_completed: bool,
    dismissed: bool,
    available: set[EnglishLevel],
) -> LevelSuggestion | None:
    """`practices`: las ultimas del nivel (mas nueva primero), solo las
    posteriores al ultimo "no por ahora" si `dismissed`."""
    up = next_level(level)
    down = previous_level(level)
    can_go_up = up is not None and up in available
    can_go_down = down is not None and down in available

    if len(practices) < WINDOW:
        if level_completed and can_go_up and not dismissed:
            return LevelSuggestion("up", up, "completed")  # type: ignore[arg-type]
        return None

    s = signals(practices[:WINDOW])
    if (
        can_go_up
        and s.guessed_pct >= UP_GUESSED_PCT
        and s.listening_pct >= UP_LISTENING_PCT
        and s.reading_pct is not None
        and s.reading_pct >= UP_READING_PCT
    ):
        return LevelSuggestion("up", up, "performance")  # type: ignore[arg-type]
    struggling = [
        s.guessed_pct <= DOWN_GUESSED_PCT,
        s.listening_pct <= DOWN_LISTENING_PCT,
        s.reading_pct is not None and s.reading_pct <= DOWN_READING_PCT,
    ]
    if can_go_down and sum(struggling) >= 2:
        return LevelSuggestion("down", down, "performance")  # type: ignore[arg-type]
    if level_completed and can_go_up:
        return LevelSuggestion("up", up, "completed")  # type: ignore[arg-type]
    return None
