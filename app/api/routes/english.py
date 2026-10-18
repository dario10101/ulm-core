"""Practica de ingles del usuario (permiso `english`). Ver ENGLISH-TEACHER-PLAN.md.

El banco se administra aparte, en /system/english (solo admin).
"""

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.api.deps import (
    get_current_user_id,
    get_english_feedback_service,
    get_english_practice_service,
    get_english_speech_service,
)
from app.api.errors import http_error
from app.core.logging import get_logger
from app.integrations.openai_client import TextGenerationError
from app.integrations.speech_client import TranscriptionError
from app.schemas.english import (
    EnglishCorrectionRead,
    EnglishDiffOpRead,
    EnglishFeedbackRead,
    EnglishImageRead,
    EnglishLevelAvailabilityRead,
    EnglishLevelConfigRead,
    EnglishLevelSuggestionRead,
    EnglishMasteredWrite,
    EnglishPracticeRead,
    EnglishPracticeSavedRead,
    EnglishPracticeWrite,
    EnglishSettingsRead,
    EnglishSettingsWrite,
    EnglishSpeechRead,
)
from app.services.english_feedback_service import EnglishFeedbackService
from app.services.english_levels import EnglishLevel, level_config
from app.services.english_practice_service import (
    EnglishPracticeService,
    PracticeDraft,
    SavedPractice,
    SettingsView,
)
from app.services.english_speech_service import EnglishSpeechService
from app.services.errors import AiNotConfiguredError, DomainError

logger = get_logger(__name__)

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
        suggestion=(
            EnglishLevelSuggestionRead(
                direction=view.suggestion.direction,
                level=view.suggestion.level,
                reason=view.suggestion.reason,
            )
            if view.suggestion
            else None
        ),
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


@router.post("/settings/level-suggestion/dismiss", response_model=EnglishSettingsRead)
def dismiss_level_suggestion(
    user_id: int = Depends(get_current_user_id),
    service: EnglishPracticeService = Depends(get_english_practice_service),
) -> EnglishSettingsRead:
    """ "No por ahora" en la sugerencia de nivel."""
    try:
        return _settings_read(service.dismiss_suggestion(user_id))
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


@router.post("/speech", response_model=EnglishSpeechRead)
def transcribe_speech(
    audio: UploadFile = File(),
    content_id: int = Form(),
    phase: Literal["reading", "free"] = Form(),
    duration_seconds: float = Form(ge=0),
    user_id: int = Depends(get_current_user_id),
    service: EnglishSpeechService = Depends(get_english_speech_service),
) -> EnglishSpeechRead:
    """Transcribe una grabacion del speaking; en la lectura, la compara con el
    texto esperado. No necesita la practica guardada (D8)."""
    try:
        result = service.transcribe(
            user_id=user_id,
            content_id=content_id,
            phase=phase,
            audio=audio.file.read(),
            content_type=audio.content_type or "",
            client_seconds=duration_seconds,
        )
    except AiNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except TranscriptionError as exc:
        logger.warning("Fallo la transcripcion: %s", exc)
        raise HTTPException(status_code=502, detail="No se pudo transcribir el audio")
    except DomainError as exc:
        raise http_error(exc)
    diff = result.diff
    return EnglishSpeechRead(
        transcript=result.transcript,
        duration_seconds=result.duration_seconds,
        match_pct=diff.match_pct if diff else None,
        diff=(
            [EnglishDiffOpRead(kind=op.kind, expected=op.expected, said=op.said) for op in diff.ops]
            if diff
            else None
        ),
    )


@router.post(
    "/practices/{practice_id}/feedback",
    response_model=EnglishFeedbackRead,
    responses={502: {"description": "El proveedor de IA fallo o respondio mal"}},
)
def practice_feedback(
    practice_id: int,
    user_id: int = Depends(get_current_user_id),
    service: EnglishFeedbackService = Depends(get_english_feedback_service),
):
    """Feedback de la practica (1 llamada al LLM). Si ya existe, devuelve el
    guardado sin volver a pagar."""
    try:
        outcome = service.get_or_create(user_id, practice_id)
    except AiNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except TextGenerationError as exc:
        logger.warning("Fallo el proveedor de IA en el feedback: %s", exc)
        raise HTTPException(
            status_code=502, detail="No se pudo obtener respuesta del proveedor de IA"
        )
    except DomainError as exc:
        raise http_error(exc)
    if outcome.feedback is None:
        # Respuesta pagada pero inutilizable: 502 SIN excepcion, para que el
        # request se commitee y quede registrado el consumo.
        return JSONResponse(
            status_code=502,
            content={"detail": "La IA respondio en un formato invalido; intenta de nuevo"},
        )
    feedback = outcome.feedback
    return EnglishFeedbackRead(
        summary=feedback.summary,
        vocabulary=feedback.vocabulary,
        writing_corrections=[
            EnglishCorrectionRead(**c.model_dump()) for c in feedback.writing_corrections
        ],
        reading_observations=feedback.reading_observations,
        speaking_corrections=[
            EnglishCorrectionRead(**c.model_dump()) for c in feedback.speaking_corrections
        ],
        answered_question=feedback.answered_question,
        tips=feedback.tips,
        model=outcome.model,
    )
