"""Interpretacion con IA del pulso semanal (boton "Interpret" del dashboard).

Primer caso del roadmap "insights IA": los numeros los calcula
DashboardService sin IA y el LLM solo los lee (1 llamada, entrada chica). El
pulso se calcula en el servidor, nunca se acepta del cliente: asi el endpoint
no sirve de chat libre ni recibe texto inyectado.

Sin persistencia (D5 del plan): cada clic es una llamada pagada, registrada en
ai_usage_events. El tope por usuario (F2) todavia no existe.
"""

from app.core.logging import get_logger
from app.integrations.openai_client import TextGenerator
from app.schemas.dashboard import DashboardPulseRead, PulseInterpretationRead
from app.services.ai_models import AiModel
from app.services.ai_usage_service import AiUsageRecorder
from app.services.errors import AiNotConfiguredError

logger = get_logger(__name__)

USAGE_FEATURE = "dashboard.pulse"

INSTRUCTIONS = (
    "Eres el asistente de ULM, una app personal de registros. Recibes en JSON el "
    "resumen de una semana (sabado a viernes) del usuario: cada metrica trae el "
    "valor de la semana (current), el de la semana anterior (previous) y el "
    "promedio de las 4 anteriores (average). Las secciones en null no aplican; "
    "no las menciones. Si week.in_progress es true, la semana va por "
    "week.elapsed_days de 7 dias: no la juzgues como si estuviera completa. "
    "Montos en pesos colombianos; score_pct y savings_rate_pct son porcentajes. "
    "Responde en espanol, en texto plano, con 3 a 5 lineas que empiecen con "
    "'- ': lo que va bien, lo que conviene vigilar y una sugerencia concreta. "
    "No inventes datos que no esten en el JSON."
)


class DashboardInsightService:
    def __init__(
        self, generator: TextGenerator | None, usage: AiUsageRecorder, *, model: AiModel
    ) -> None:
        # None: no hay OPENAI_API_KEY configurada (ver deps.get_text_generator).
        self._generator = generator
        self._usage = usage
        self._model = model

    def interpret(self, *, user_id: int, pulse: DashboardPulseRead) -> PulseInterpretationRead:
        if self._generator is None:
            raise AiNotConfiguredError()
        result = self._generator.generate(
            model=self._model.id,
            instructions=INSTRUCTIONS,
            prompt=pulse.model_dump_json(),
            max_output_tokens=self._model.max_output_tokens,
            reasoning_effort=self._model.reasoning_effort,
        )
        # Desde aca ya se pago: nada debe levantar un error.
        self._usage.record_text(user_id=user_id, feature=USAGE_FEATURE, result=result)
        logger.info(
            "Interpretacion del pulso user_id=%s model=%s tokens_in=%s tokens_out=%s",
            user_id,
            result.model,
            result.input_tokens,
            result.output_tokens,
        )
        return PulseInterpretationRead(text=result.text.strip(), model=result.model)
