"""Practica de ingles del usuario (permiso `english`). Ver ENGLISH-TEACHER-PLAN.md.

El banco se administra aparte, en /system/english (solo admin).
"""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user_id, get_english_practice_service
from app.api.errors import http_error
from app.schemas.english import (
    EnglishImageRead,
    EnglishLevelAvailabilityRead,
    EnglishLevelConfigRead,
    EnglishMasteredWrite,
    EnglishPracticeRead,
    EnglishPracticeSavedRead,
    EnglishPracticeWrite,
    EnglishSettingsRead,
    EnglishSettingsWrite,
)
from app.services.english_levels import EnglishLevel, level_config
from app.services.english_practice_service import (
    EnglishPracticeService,
    PracticeDraft,
    SavedPractice,
    SettingsView,
)
from app.services.errors import DomainError

router = APIRouter(prefix="/english", tags=["english"])


def _settings_read(view: SettingsView) -> EnglishSettingsRead:
    return EnglishSettingsRead(
        level=view.level,
        levels=[
            EnglishLevelAvailabilityRead(
                level=a.level, ready_words=a.ready_words, available=a.available
            )
            for a in view.levels
        ],
        level_completed=view.level_completed,
    )


def _practice_read(draft: PracticeDraft) -> EnglishPracticeRead:
    level = EnglishLevel(draft.content.level)
    config = level_config(level)
    return EnglishPracticeRead(
        word_id=draft.word.id,
        content_id=draft.content.id,
        level=level,
        lemma=draft.word.lemma,
        accepted_answers=list(draft.word.accepted_answers),
        pos=draft.word.pos,
        image=EnglishImageRead.model_validate(draft.image) if draft.image else None,
        listening_sentence=draft.content.listening_sentence,
        writing_prompt=draft.content.writing_prompt,
        writing_prompt_es=draft.content.writing_prompt_es,
        reading_text=draft.content.reading_text,
        reading_question=draft.content.reading_question,
        mastered_repeat=draft.mastered_repeat,
        config=EnglishLevelConfigRead(
            first_letter_hint=config.first_letter_hint,
            tts_rate=config.tts_rate,
            writing_min_chars=config.writing_min_chars,
            free_speaking_seconds=config.free_speaking_seconds,
            instructions_lang=config.instructions_lang,
        ),
    )


def _saved_read(saved: SavedPractice) -> EnglishPracticeSavedRead:
    return EnglishPracticeSavedRead(
        id=saved.practice.id, mastered=saved.mastered, was_mastered=saved.practice.was_mastered
    )


@router.get("/settings", response_model=EnglishSettingsRead)
def get_settings(
    user_id: int = Depends(get_current_user_id),
    service: EnglishPracticeService = Depends(get_english_practice_service),
) -> EnglishSettingsRead:
    return _settings_read(service.get_settings(user_id))


@router.put("/settings", response_model=EnglishSettingsRead)
def update_settings(
    payload: EnglishSettingsWrite,
    user_id: int = Depends(get_current_user_id),
    service: EnglishPracticeService = Depends(get_english_practice_service),
) -> EnglishSettingsRead:
    try:
        return _settings_read(service.set_level(user_id, payload.level))
    except DomainError as exc:
        raise http_error(exc)


@router.get("/practices/next", response_model=EnglishPracticeRead)
def next_practice(
    user_id: int = Depends(get_current_user_id),
    service: EnglishPracticeService = Depends(get_english_practice_service),
) -> EnglishPracticeRead:
    """Elige la palabra y devuelve la practica entera. No guarda nada (D8)."""
    try:
        return _practice_read(service.next_practice(user_id))
    except DomainError as exc:
        raise http_error(exc)


@router.post("/practices", response_model=EnglishPracticeSavedRead, status_code=201)
def save_practice(
    payload: EnglishPracticeWrite,
    user_id: int = Depends(get_current_user_id),
    service: EnglishPracticeService = Depends(get_english_practice_service),
) -> EnglishPracticeSavedRead:
    """Guarda la practica completa al llegar al cierre (D21)."""
    try:
        return _saved_read(service.save_practice(user_id, payload))
    except DomainError as exc:
        raise http_error(exc)


@router.patch("/practices/{practice_id}", response_model=EnglishPracticeSavedRead)
def set_mastered(
    practice_id: int,
    payload: EnglishMasteredWrite,
    user_id: int = Depends(get_current_user_id),
    service: EnglishPracticeService = Depends(get_english_practice_service),
) -> EnglishPracticeSavedRead:
    """Cambia el check "la domino" desde la pantalla de cierre."""
    try:
        return _saved_read(service.set_mastered(user_id, practice_id, payload.mastered))
    except DomainError as exc:
        raise http_error(exc)
