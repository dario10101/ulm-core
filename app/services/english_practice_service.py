"""Practica de ingles del usuario (ENGLISH-TEACHER-PLAN.md, secciones 3 y 6).

La practica vive en el front hasta el cierre (D8): `next_practice` no guarda
nada, solo elige la palabra y devuelve todo lo necesario (incluida la
respuesta, D10). `save_practice` guarda la practica completa al llegar al
cierre (D21) y actualiza la relacion usuario-palabra.

Seleccion de la palabra (seccion 6), sin LLM:
1. Candidatas: palabras listas del nivel del usuario que no domina.
2. ~30% de las veces, una ya practicada sin dominar (la que hace mas tiempo
   no sale); si no, una nueva al azar. Si un grupo esta vacio, el otro.
3. Nunca la misma de la practica anterior (salvo que sea la unica).
4. Si domino todo el nivel, se repiten las dominadas (D19).
"""

import random
from dataclasses import dataclass
from datetime import UTC, datetime

from app.db.models.english import (
    EngPractice,
    EngUserSettings,
    EngUserWord,
    EngWord,
    EngWordContent,
    EngWordImage,
)
from app.repositories.english_practice_repository import EnglishPracticeRepository
from app.schemas.english import EnglishPracticeWrite
from app.services.english_levels import LEVEL_ORDER, EnglishLevel, level_config
from app.services.errors import (
    EnglishBankEmptyError,
    EnglishContentMismatchError,
    EnglishLevelNotSetError,
    EnglishLevelUnavailableError,
    EnglishPracticeNotFoundError,
    EnglishWritingTooShortError,
)

REVIEW_PROBABILITY = 0.3


@dataclass(frozen=True)
class LevelAvailability:
    level: EnglishLevel
    ready_words: int
    available: bool


@dataclass(frozen=True)
class SettingsView:
    level: EnglishLevel | None
    levels: list[LevelAvailability]
    # Ya domina todas las palabras de su nivel (D19): la UI lo avisa.
    level_completed: bool


@dataclass(frozen=True)
class PracticeDraft:
    word: EngWord
    content: EngWordContent
    image: EngWordImage | None
    # Palabra ya dominada que se repite porque no quedan otras (D19).
    mastered_repeat: bool


@dataclass(frozen=True)
class SavedPractice:
    practice: EngPractice
    mastered: bool


def _now() -> datetime:
    return datetime.now(UTC)


class EnglishPracticeService:
    def __init__(
        self,
        repository: EnglishPracticeRepository,
        *,
        min_words_per_level: int,
        rng: random.Random | None = None,
    ) -> None:
        self._repository = repository
        self._min_words = min_words_per_level
        # Inyectable para que los tests fijen la mezcla nuevas/repaso.
        self._rng = rng or random.Random()

    # --- Nivel ---

    def get_settings(self, user_id: int) -> SettingsView:
        settings = self._repository.get_settings(user_id=user_id)
        level = EnglishLevel(settings.level) if settings else None
        completed = (
            level is not None
            and self._repository.count_unmastered_ready(level.value, user_id=user_id) == 0
        )
        return SettingsView(level=level, levels=self._availability(), level_completed=completed)

    def set_level(self, user_id: int, level: EnglishLevel) -> SettingsView:
        available = {a.level for a in self._availability() if a.available}
        if level not in available:
            raise EnglishLevelUnavailableError(level.value)
        settings = self._repository.get_settings(user_id=user_id)
        if settings is None:
            self._repository.add_settings(EngUserSettings(user_id=user_id, level=level.value))
        else:
            settings.level = level.value
            # Nivel nuevo: la sugerencia empieza de cero.
            settings.level_suggestion_dismissed_at = None
            settings.updated_at = _now()
        self._repository.flush()
        return self.get_settings(user_id)

    def _availability(self) -> list[LevelAvailability]:
        counts = self._repository.ready_counts_by_level()
        return [
            LevelAvailability(
                level=level,
                ready_words=counts.get(level.value, 0),
                available=counts.get(level.value, 0) >= self._min_words,
            )
            for level in LEVEL_ORDER
        ]

    def current_level(self, user_id: int) -> EnglishLevel:
        settings = self._repository.get_settings(user_id=user_id)
        if settings is None:
            raise EnglishLevelNotSetError()
        return EnglishLevel(settings.level)

    # --- Practica ---

    def next_practice(self, user_id: int) -> PracticeDraft:
        level = self.current_level(user_id)
        last = self._repository.last_practiced_word_id(user_id=user_id)
        word, mastered_repeat = self._pick(level, user_id=user_id, exclude=last)
        if word is None:
            # Sin otra opcion, se permite repetir la anterior.
            word, mastered_repeat = self._pick(level, user_id=user_id, exclude=None)
        if word is None:
            raise EnglishBankEmptyError(level.value)
        content = self._repository.content_for(word.id, level.value)
        assert content is not None  # _pick solo devuelve palabras con contenido
        return PracticeDraft(
            word=word,
            content=content,
            image=self._repository.selected_image(word.id),
            mastered_repeat=mastered_repeat,
        )

    def _pick(
        self, level: EnglishLevel, *, user_id: int, exclude: int | None
    ) -> tuple[EngWord | None, bool]:
        def review() -> EngWord | None:
            return self._repository.oldest_practiced_word(
                level.value, user_id=user_id, mastered=False, exclude=exclude
            )

        def new() -> EngWord | None:
            return self._repository.random_new_word(level.value, user_id=user_id, exclude=exclude)

        first, second = (review, new) if self._rng.random() < REVIEW_PROBABILITY else (new, review)
        word = first() or second()
        if word is not None:
            return word, False
        mastered = self._repository.oldest_practiced_word(
            level.value, user_id=user_id, mastered=True, exclude=exclude
        )
        return mastered, mastered is not None

    def save_practice(self, user_id: int, payload: EnglishPracticeWrite) -> SavedPractice:
        content = self._repository.get_content(payload.content_id)
        if content is None or content.word_id != payload.word_id:
            raise EnglishContentMismatchError()
        minimum = level_config(EnglishLevel(content.level)).writing_min_chars
        if len(payload.writing_text.strip()) < minimum:
            raise EnglishWritingTooShortError(minimum)

        now = _now()
        user_word = self._repository.get_user_word(payload.word_id, user_id=user_id)
        if user_word is None:
            user_word = EngUserWord(
                user_id=user_id, word_id=payload.word_id, mastered=False, times_practiced=0
            )
            self._repository.add_user_word(user_word)
        was_mastered = user_word.mastered

        practice = EngPractice(
            user_id=user_id,
            word_id=payload.word_id,
            content_id=content.id,
            level=content.level,
            vocab_revealed=payload.vocab_revealed,
            vocab_used_synonym=payload.vocab_used_synonym,
            listening_text_shown=payload.listening_text_shown,
            writing_text=payload.writing_text.strip(),
            reading_transcript=payload.reading_transcript,
            reading_match_pct=payload.reading_match_pct,
            free_transcript=payload.free_transcript,
            speaking_skipped=payload.speaking_skipped,
            audio_seconds=payload.audio_seconds,
            was_mastered=was_mastered,
            completed_at=now,
        )
        self._repository.add_practice(practice)
        user_word.times_practiced += 1
        user_word.last_practiced_at = now
        # Una dominada no se desmarca (D20): el check solo aplica a las demas.
        if not was_mastered:
            self._apply_mastered(user_word, payload.mastered, now)
        self._repository.flush()
        return SavedPractice(practice=practice, mastered=user_word.mastered)

    def set_mastered(self, user_id: int, practice_id: int, mastered: bool) -> SavedPractice:
        practice = self._repository.get_practice(practice_id, user_id=user_id)
        if practice is None:
            raise EnglishPracticeNotFoundError(practice_id)
        user_word = self._repository.get_user_word(practice.word_id, user_id=user_id)
        assert user_word is not None  # se crea con la practica
        if not practice.was_mastered:
            self._apply_mastered(user_word, mastered, _now())
            self._repository.flush()
        return SavedPractice(practice=practice, mastered=user_word.mastered)

    @staticmethod
    def _apply_mastered(user_word: EngUserWord, mastered: bool, now: datetime) -> None:
        if mastered and not user_word.mastered:
            user_word.mastered_at = now
        if not mastered:
            user_word.mastered_at = None
        user_word.mastered = mastered
