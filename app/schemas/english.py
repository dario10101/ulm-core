"""Esquemas Pydantic del modulo English (ENGLISH-TEACHER-PLAN.md, seccion 8)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.english_levels import EnglishLevel

# --- Banco (admin, /system/english) ---


class EnglishLevelBankRead(BaseModel):
    level: EnglishLevel
    list_total: int
    imported: int
    approved: int
    review: int
    pending: int
    disabled: int
    processable: int
    full: bool


class EnglishImportRead(BaseModel):
    added: int


class EnglishFillProgressRead(BaseModel):
    processed: int
    approved: int
    sent_to_review: int
    remaining: int


class EnglishImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    url: str
    source: str
    license: str
    attribution: str
    page_url: str | None


class EnglishWordAdminRead(BaseModel):
    id: int
    lemma: str
    pos: str
    level: EnglishLevel
    status: str
    status_reason: str | None
    accepted_answers: list[str]
    image: EnglishImageRead | None
    has_content: bool


class EnglishWordPageRead(BaseModel):
    items: list[EnglishWordAdminRead]
    total: int


class EnglishWordStatusWrite(BaseModel):
    status: Literal["APPROVED", "DISABLED"]


# --- Practica (/english, permiso `english`) ---


class EnglishLevelAvailabilityRead(BaseModel):
    level: EnglishLevel
    ready_words: int
    # Con banco suficiente para elegirlo (ENGLISH_MIN_WORDS_PER_LEVEL).
    available: bool


class EnglishSettingsRead(BaseModel):
    # Nulo hasta que el usuario elige su nivel.
    level: EnglishLevel | None
    levels: list[EnglishLevelAvailabilityRead]
    # Ya domina todas las palabras de su nivel (D19).
    level_completed: bool


class EnglishSettingsWrite(BaseModel):
    level: EnglishLevel


class EnglishLevelConfigRead(BaseModel):
    first_letter_hint: bool
    tts_rate: float
    writing_min_chars: int
    free_speaking_seconds: int
    # "es" en A1-A2: instrucciones de la pagina en español.
    instructions_lang: str


class EnglishPracticeRead(BaseModel):
    """Todo lo de una practica, incluida la respuesta: la validacion del
    vocabulario es solo del front (D10). No se guarda nada al pedirla (D8)."""

    word_id: int
    content_id: int
    level: EnglishLevel
    lemma: str
    accepted_answers: list[str]
    pos: str
    image: EnglishImageRead | None
    listening_sentence: str
    writing_prompt: str
    writing_prompt_es: str | None
    reading_text: str
    reading_question: str
    # Palabra ya dominada que se repite (D19): el front no muestra el check.
    mastered_repeat: bool
    config: EnglishLevelConfigRead


class EnglishPracticeWrite(BaseModel):
    """La practica completa, enviada al llegar al cierre (D21)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    word_id: int
    content_id: int
    vocab_revealed: bool
    vocab_used_synonym: bool = False
    listening_text_shown: bool
    writing_text: str = Field(max_length=5000)
    reading_transcript: str | None = Field(default=None, max_length=5000)
    reading_match_pct: float | None = Field(default=None, ge=0, le=100)
    free_transcript: str | None = Field(default=None, max_length=10000)
    speaking_skipped: bool = False
    audio_seconds: float = Field(default=0, ge=0)
    # El check "la domino" con su valor por defecto (o el que eligio el usuario).
    mastered: bool


class EnglishPracticeSavedRead(BaseModel):
    id: int
    mastered: bool
    was_mastered: bool


class EnglishMasteredWrite(BaseModel):
    mastered: bool
