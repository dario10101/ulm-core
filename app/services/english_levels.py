"""Niveles CEFR y como ajustan la dificultad de cada paso de la practica.

Tabla de configuracion en codigo, no en el prompt (ENGLISH-TEACHER-PLAN.md,
seccion 4): el backend la usa para pedir y validar el contenido del banco, y
la manda al front con cada practica (velocidad del audio, minimo del writing,
tope del speaking, idioma de las instrucciones).
"""

from dataclasses import dataclass
from enum import Enum


class EnglishLevel(str, Enum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


@dataclass(frozen=True)
class LevelConfig:
    level: EnglishLevel
    # Pista de la primera letra en el paso de vocabulario.
    first_letter_hint: bool
    # Velocidad de speechSynthesis (1.0 = normal).
    tts_rate: float
    # Palabras de la frase del listening (min, max).
    listening_words: tuple[int, int]
    writing_min_chars: int
    # Frases del texto de lectura, contando la del listening y la pregunta final.
    reading_sentences: tuple[int, int]
    # Tope de la grabacion libre (segundos).
    free_speaking_seconds: int
    # Idioma de las instrucciones de la pagina ("es" en los niveles basicos).
    instructions_lang: str


LEVELS: dict[EnglishLevel, LevelConfig] = {
    config.level: config
    for config in (
        LevelConfig(EnglishLevel.A1, True, 0.8, (4, 7), 30, (3, 3), 30, "es"),
        LevelConfig(EnglishLevel.A2, True, 0.9, (6, 10), 60, (3, 4), 45, "es"),
        LevelConfig(EnglishLevel.B1, False, 1.0, (8, 14), 120, (4, 4), 60, "en"),
        LevelConfig(EnglishLevel.B2, False, 1.0, (10, 18), 200, (4, 5), 90, "en"),
        LevelConfig(EnglishLevel.C1, False, 1.1, (12, 22), 300, (5, 5), 120, "en"),
        LevelConfig(EnglishLevel.C2, False, 1.1, (12, 30), 400, (5, 6), 120, "en"),
    )
}

LEVEL_ORDER: tuple[EnglishLevel, ...] = tuple(EnglishLevel)


def level_config(level: EnglishLevel) -> LevelConfig:
    return LEVELS[level]


def next_level(level: EnglishLevel) -> EnglishLevel | None:
    index = LEVEL_ORDER.index(level)
    return LEVEL_ORDER[index + 1] if index + 1 < len(LEVEL_ORDER) else None


def previous_level(level: EnglishLevel) -> EnglishLevel | None:
    index = LEVEL_ORDER.index(level)
    return LEVEL_ORDER[index - 1] if index > 0 else None
