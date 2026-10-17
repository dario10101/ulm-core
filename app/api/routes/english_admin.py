"""Banco compartido de ingles (Settings -> System -> English bank). Solo el
admin (ver PRIVATE_ROUTERS en app/main.py). Ver ENGLISH-TEACHER-PLAN.md, 5.1."""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user_id, get_english_bank_service
from app.api.errors import http_error
from app.core.logging import get_logger
from app.integrations.openai_client import TextGenerationError
from app.schemas.english import (
    EnglishFillProgressRead,
    EnglishImageRead,
    EnglishImportRead,
    EnglishLevelBankRead,
    EnglishWordAdminRead,
    EnglishWordPageRead,
    EnglishWordStatusWrite,
)
from app.services.english_bank_service import (
    EnglishBankService,
    LevelBankStatus,
    WordAdminView,
)
from app.services.english_levels import EnglishLevel
from app.services.errors import AiNotConfiguredError, DomainError

logger = get_logger(__name__)

router = APIRouter(prefix="/system/english", tags=["english bank"])


def _level_read(status: LevelBankStatus) -> EnglishLevelBankRead:
    return EnglishLevelBankRead(
        level=status.level,
        list_total=status.list_total,
        imported=status.imported,
        approved=status.approved,
        review=status.review,
        pending=status.pending,
        disabled=status.disabled,
        processable=status.processable,
        full=status.full,
    )


def _word_read(view: WordAdminView) -> EnglishWordAdminRead:
    word = view.word
    return EnglishWordAdminRead(
        id=word.id,
        lemma=word.lemma,
        pos=word.pos,
        level=EnglishLevel(word.cefr_level),
        status=word.status,
        status_reason=word.status_reason,
        accepted_answers=list(word.accepted_answers),
        image=EnglishImageRead.model_validate(view.image) if view.image else None,
        has_content=view.has_content,
    )


@router.get("/levels", response_model=list[EnglishLevelBankRead])
def list_levels(
    service: EnglishBankService = Depends(get_english_bank_service),
) -> list[EnglishLevelBankRead]:
    return [_level_read(status) for status in service.level_statuses()]


@router.post("/levels/{level}/import", response_model=EnglishImportRead)
def import_words(
    level: EnglishLevel, service: EnglishBankService = Depends(get_english_bank_service)
) -> EnglishImportRead:
    """Primer paso de "Fill bank": hasta 100 palabras nuevas de la lista."""
    return EnglishImportRead(added=service.import_next(level))


@router.post("/levels/{level}/process", response_model=EnglishFillProgressRead)
def process_words(
    level: EnglishLevel,
    user_id: int = Depends(get_current_user_id),
    service: EnglishBankService = Depends(get_english_bank_service),
) -> EnglishFillProgressRead:
    """Un lote del llenado; el front repite hasta `remaining == 0`."""
    try:
        progress = service.process_next(level, user_id=user_id)
    except AiNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except TextGenerationError as exc:
        logger.warning("Fallo el proveedor de IA al llenar el banco: %s", exc)
        raise HTTPException(
            status_code=502, detail="No se pudo obtener respuesta del proveedor de IA"
        )
    return EnglishFillProgressRead(
        processed=progress.processed,
        approved=progress.approved,
        sent_to_review=progress.sent_to_review,
        remaining=progress.remaining,
    )


@router.get("/words", response_model=EnglishWordPageRead)
def list_words(
    level: EnglishLevel,
    status: str | None = Query(default=None, pattern="^(PENDING|APPROVED|REVIEW|DISABLED)$"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=48, ge=1, le=200),
    service: EnglishBankService = Depends(get_english_bank_service),
) -> EnglishWordPageRead:
    views, total = service.list_words(level, status=status, offset=offset, limit=limit)
    return EnglishWordPageRead(items=[_word_read(view) for view in views], total=total)


@router.post("/words/{word_id}/next-image", response_model=EnglishWordAdminRead)
def next_image(
    word_id: int, service: EnglishBankService = Depends(get_english_bank_service)
) -> EnglishWordAdminRead:
    try:
        return _word_read(service.next_image(word_id))
    except DomainError as exc:
        raise http_error(exc)


@router.patch("/words/{word_id}", response_model=EnglishWordAdminRead)
def set_word_status(
    word_id: int,
    payload: EnglishWordStatusWrite,
    service: EnglishBankService = Depends(get_english_bank_service),
) -> EnglishWordAdminRead:
    try:
        return _word_read(service.set_enabled(word_id, payload.status == "APPROVED"))
    except DomainError as exc:
        raise http_error(exc)
