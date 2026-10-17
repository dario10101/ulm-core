"""Rutas de las funcionalidades con IA. Solo hablan con AiChatService."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_ai_chat_service, get_current_user_id
from app.core.logging import get_logger
from app.integrations.openai_client import TextGenerationError
from app.schemas.ai import AiAskRequest, AiAskResponse, AiModelRead, AiModelsRead
from app.services.ai_chat_service import AiChatService
from app.services.errors import AiNotConfiguredError, UnknownAiModelError

logger = get_logger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/models", response_model=AiModelsRead)
def list_models(service: AiChatService = Depends(get_ai_chat_service)) -> AiModelsRead:
    """Modelos elegibles: el catalogo cruzado con los que la key tiene habilitados."""
    try:
        models, default = service.list_models()
    except AiNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return AiModelsRead(
        models=[AiModelRead.model_validate(model) for model in models], default=default
    )


@router.post("/ask", response_model=AiAskResponse)
def ask(
    payload: AiAskRequest,
    user_id: int = Depends(get_current_user_id),
    service: AiChatService = Depends(get_ai_chat_service),
) -> AiAskResponse:
    """Pregunta suelta, sin contexto: cada request es independiente."""
    try:
        result = service.ask(user_id=user_id, question=payload.question, model_id=payload.model)
    except UnknownAiModelError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except AiNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except TextGenerationError as exc:
        # El detalle (key invalida, sin saldo, rate limit) va al log, no al cliente.
        logger.warning("Fallo el proveedor de IA: %s", exc)
        raise HTTPException(
            status_code=502, detail="No se pudo obtener respuesta del proveedor de IA"
        )
    return AiAskResponse(answer=result.text, model=result.model)
