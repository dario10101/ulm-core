"""Llenado y curacion del banco compartido de ingles (ENGLISH-TEACHER-PLAN.md, 5.1).

El boton "Fill bank" del admin son dos pasos que el front encadena:
1. `import_next`: agrega hasta 100 palabras nuevas del nivel desde la lista.
2. `process_next`, repetido hasta `remaining == 0`: cada llamada completa ~10
   palabras (imagen + contenido del LLM) y devuelve el progreso.

Procesamiento por lotes dirigido por el cliente: un request de minutos es
fragil y, en Cloud Run, una tarea en segundo plano se queda sin CPU al
responder. Asi cada request dura segundos y el llenado se puede cortar y
retomar.

Idempotente (D25): solo completa lo que falta. Una palabra con imagen no se
vuelve a buscar, una con contenido no se regenera, y las que fallan se
reintentan hasta MAX_FILL_ATTEMPTS veces; despues quedan en REVIEW para el
admin. Volver a llenar un banco lleno no paga nada de nuevo.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import ValidationError as PydanticValidationError

from app.core.logging import get_logger
from app.db.models.english import (
    WORD_APPROVED,
    WORD_DISABLED,
    WORD_PENDING,
    WORD_REVIEW,
    EngWord,
    EngWordContent,
    EngWordImage,
)
from app.integrations.image_search import ImageSearch
from app.integrations.openai_client import TextGenerator
from app.repositories.english_bank_repository import EnglishBankRepository
from app.services.ai_models import AiModel
from app.services.ai_usage_service import AiUsageRecorder
from app.services.english_content import (
    PROMPT_VERSION,
    GeneratedBatch,
    build_instructions,
    build_prompt,
    filter_accepted_answers,
    response_schema,
    validate_item,
)
from app.services.english_levels import LEVEL_ORDER, EnglishLevel, level_config
from app.services.english_wordlist import entries_for_level
from app.services.errors import (
    AiNotConfiguredError,
    EnglishWordNotFoundError,
    EnglishWordNotReadyError,
    NoMoreImageCandidatesError,
)

logger = get_logger(__name__)

IMPORT_BATCH = 100
PROCESS_BATCH = 10
MAX_FILL_ATTEMPTS = 2
IMAGE_CANDIDATES = 5
USAGE_FEATURE = "english.bank"


@dataclass(frozen=True)
class LevelBankStatus:
    level: EnglishLevel
    # Palabras del nivel en la lista (despues de filtrar, D28/D29).
    list_total: int
    imported: int
    approved: int
    review: int
    pending: int
    disabled: int
    # Pendientes o en revision con intentos restantes: las que tocaria un llenado.
    processable: int

    @property
    def full(self) -> bool:
        """Lleno (D26): no quedan palabras de la lista por importar ni por procesar."""
        return self.imported >= self.list_total and self.processable == 0


@dataclass(frozen=True)
class FillProgress:
    processed: int
    approved: int
    sent_to_review: int
    remaining: int


@dataclass(frozen=True)
class WordAdminView:
    word: EngWord
    image: EngWordImage | None
    has_content: bool


def _now() -> datetime:
    return datetime.now(UTC)


class EnglishBankService:
    def __init__(
        self,
        repository: EnglishBankRepository,
        image_search: ImageSearch,
        generator: TextGenerator | None,
        usage: AiUsageRecorder,
        *,
        model: AiModel,
        max_output_tokens: int,
    ) -> None:
        self._repository = repository
        self._images = image_search
        # None: no hay OPENAI_API_KEY (ver deps.get_text_generator).
        self._generator = generator
        self._usage = usage
        self._model = model
        self._max_output_tokens = max_output_tokens

    # --- Estado ---

    def level_statuses(self) -> list[LevelBankStatus]:
        return [self.level_status(level) for level in LEVEL_ORDER]

    def level_status(self, level: EnglishLevel) -> LevelBankStatus:
        counts = self._repository.count_by_status(level.value)
        processable = len(
            self._repository.processable_words(
                level.value, max_attempts=MAX_FILL_ATTEMPTS, limit=10_000
            )
        )
        return LevelBankStatus(
            level=level,
            list_total=len(entries_for_level(level)),
            imported=sum(counts.values()),
            approved=counts.get(WORD_APPROVED, 0),
            review=counts.get(WORD_REVIEW, 0),
            pending=counts.get(WORD_PENDING, 0),
            disabled=counts.get(WORD_DISABLED, 0),
            processable=processable,
        )

    # --- Llenado ---

    def import_next(self, level: EnglishLevel) -> int:
        """Agrega hasta IMPORT_BATCH palabras nuevas; 0 si la lista se agoto."""
        existing = self._repository.existing_lemmas()
        new_entries = [e for e in entries_for_level(level) if e.lemma not in existing]
        for entry in new_entries[:IMPORT_BATCH]:
            self._repository.add_word(
                EngWord(
                    lemma=entry.lemma,
                    pos=entry.pos,
                    cefr_level=level.value,
                    variants=list(entry.variants),
                    accepted_answers=filter_accepted_answers(entry.lemma, list(entry.variants)),
                    source_list=entry.source,
                    status=WORD_PENDING,
                    fill_attempts=0,
                )
            )
        self._repository.flush()
        return min(len(new_entries), IMPORT_BATCH)

    def process_next(self, level: EnglishLevel, *, user_id: int) -> FillProgress:
        """Completa un lote. `user_id` (el admin) queda en ai_usage_events.

        Un fallo del proveedor (TextGenerationError) se propaga: la ruta
        responde 502 y el request se revierte entero, incluidas las imagenes
        del lote, que se vuelven a buscar en el siguiente intento.
        """
        words = self._repository.processable_words(
            level.value, max_attempts=MAX_FILL_ATTEMPTS, limit=PROCESS_BATCH
        )
        if not words:
            return FillProgress(processed=0, approved=0, sent_to_review=0, remaining=0)
        if self._generator is None:
            raise AiNotConfiguredError()

        approved = review = 0
        with_content = self._repository.content_word_ids([w.id for w in words], level.value)
        need_content: list[EngWord] = []
        for word in words:
            if not self._ensure_image(word):
                self._to_review(word, "no_image")
                review += 1
            elif word.id in with_content:
                self._approve(word)
                approved += 1
            else:
                need_content.append(word)

        if need_content:
            ok, failed = self._generate_contents(level, need_content, user_id=user_id)
            approved += ok
            review += failed

        self._repository.flush()
        remaining = len(
            self._repository.processable_words(
                level.value, max_attempts=MAX_FILL_ATTEMPTS, limit=10_000
            )
        )
        return FillProgress(
            processed=len(words), approved=approved, sent_to_review=review, remaining=remaining
        )

    def _ensure_image(self, word: EngWord) -> bool:
        """True si la palabra tiene (o consiguio) una imagen seleccionada."""
        images = self._repository.images_of(word.id)
        if any(image.selected and not image.rejected for image in images):
            return True
        available = [image for image in images if not image.rejected]
        if available:
            available[0].selected = True
            return True
        if images:
            # Todas descartadas por el admin: no se busca de nuevo.
            return False
        candidates = self._images.find(word.lemma, pos=word.pos, limit=IMAGE_CANDIDATES)
        for position, candidate in enumerate(candidates):
            self._repository.add_image(
                EngWordImage(
                    word_id=word.id,
                    position=position,
                    url=candidate.url,
                    source=candidate.source,
                    license=candidate.license,
                    attribution=candidate.attribution,
                    page_url=candidate.page_url,
                    # Aprobacion automatica (D24): la primera queda elegida.
                    selected=position == 0,
                    rejected=False,
                )
            )
        return bool(candidates)

    def _generate_contents(
        self, level: EnglishLevel, words: list[EngWord], *, user_id: int
    ) -> tuple[int, int]:
        assert self._generator is not None
        result = self._generator.generate(
            model=self._model.id,
            instructions=build_instructions(level),
            prompt=build_prompt([(w.lemma, w.pos) for w in words]),
            max_output_tokens=self._max_output_tokens,
            reasoning_effort=self._model.reasoning_effort,
            json_schema=response_schema(),
        )
        # Desde aca la llamada ya se pago: nada debe levantar un error (se
        # perderia el registro con el rollback). Los fallos van a REVIEW.
        self._usage.record_text(user_id=user_id, feature=USAGE_FEATURE, result=result)
        try:
            batch = GeneratedBatch.model_validate_json(result.text)
        except PydanticValidationError as exc:
            logger.warning("Respuesta del banco con formato invalido: %s", exc)
            for word in words:
                self._to_review(word, "invalid_response")
            return 0, len(words)

        by_word = {item.word.strip().lower(): item for item in batch.items}
        config = level_config(level)
        ok = failed = 0
        for word in words:
            item = by_word.get(word.lemma)
            if item is None:
                self._to_review(word, "missing_in_response")
                failed += 1
                continue
            content = validate_item(item, word.lemma, config)
            if isinstance(content, str):
                self._to_review(word, content)
                failed += 1
                continue
            self._repository.add_content(
                EngWordContent(
                    word_id=word.id,
                    level=level.value,
                    listening_sentence=content.listening_sentence,
                    writing_prompt=content.writing_prompt,
                    writing_prompt_es=content.writing_prompt_es,
                    reading_text=content.reading_text,
                    reading_question=content.reading_question,
                    hint=content.hint,
                    model=result.model,
                    prompt_version=PROMPT_VERSION,
                )
            )
            word.accepted_answers = filter_accepted_answers(
                word.lemma, list(word.variants) + item.accepted_answers
            )
            self._approve(word)
            ok += 1
        return ok, failed

    def _approve(self, word: EngWord) -> None:
        word.status = WORD_APPROVED
        word.status_reason = None
        word.updated_at = _now()

    def _to_review(self, word: EngWord, reason: str) -> None:
        word.status = WORD_REVIEW
        word.status_reason = reason
        word.fill_attempts += 1
        word.updated_at = _now()

    # --- Curacion posterior (D24) ---

    def list_words(
        self, level: EnglishLevel, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[WordAdminView], int]:
        words, total = self._repository.list_words(
            level.value, status=status, offset=offset, limit=limit
        )
        ids = [w.id for w in words]
        images = self._repository.selected_images(ids)
        with_content = self._repository.content_word_ids(ids, level.value)
        views = [WordAdminView(w, images.get(w.id), w.id in with_content) for w in words]
        return views, total

    def next_image(self, word_id: int) -> WordAdminView:
        """Descarta la imagen actual y elige la siguiente candidata."""
        word = self._get(word_id)
        images = self._repository.images_of(word_id)
        for image in images:
            if image.selected:
                image.selected = False
                image.rejected = True
        remaining = [image for image in images if not image.rejected]
        if not remaining:
            raise NoMoreImageCandidatesError(word.lemma)
        remaining[0].selected = True
        word.updated_at = _now()
        self._repository.flush()
        return self._view(word)

    def set_enabled(self, word_id: int, enabled: bool) -> WordAdminView:
        word = self._get(word_id)
        if enabled:
            has_image = any(i.selected for i in self._repository.images_of(word_id))
            has_content = self._repository.get_content(word_id, word.cefr_level) is not None
            if not (has_image and has_content):
                raise EnglishWordNotReadyError(word.lemma)
            self._approve(word)
        else:
            word.status = WORD_DISABLED
            word.updated_at = _now()
        self._repository.flush()
        return self._view(word)

    def _get(self, word_id: int) -> EngWord:
        word = self._repository.get_word(word_id)
        if word is None:
            raise EnglishWordNotFoundError(word_id)
        return word

    def _view(self, word: EngWord) -> WordAdminView:
        image = self._repository.selected_images([word.id]).get(word.id)
        has_content = self._repository.get_content(word.id, word.cefr_level) is not None
        return WordAdminView(word, image, has_content)
