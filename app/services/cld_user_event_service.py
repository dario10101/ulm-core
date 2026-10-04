"""Alta, edicion y borrado de eventos personales del usuario (cld_user_events):
rangos de fechas propios (vacaciones, viajes, cumpleanos...), sin hora.

El tipo (`code`) es texto libre: el usuario elige uno que ya uso o escribe uno
nuevo. Siempre se guarda en mayusculas (lo normaliza el schema y lo exige un
CHECK en la base).

La lectura para pintar el calendario sigue en CalendarEventService, que junta
estos eventos con los generales (festivos).
"""

from app.db.models.cld_user_event import CldUserEvent
from app.repositories.category_repository import CategoryRepository
from app.repositories.cld_user_event_repository import CldUserEventRepository
from app.schemas.calendar_event import CldUserEventRead, CldUserEventWrite
from app.schemas.checklist import CategoryStatus
from app.services.errors import CategoryNotFoundError, CldUserEventNotFoundError


class CldUserEventService:
    def __init__(
        self,
        repository: CldUserEventRepository,
        category_repository: CategoryRepository,
    ) -> None:
        self._repository = repository
        self._category_repository = category_repository

    def list_codes(self, user_id: int) -> list[str]:
        return self._repository.list_codes(user_id=user_id)

    def create(self, user_id: int, payload: CldUserEventWrite) -> CldUserEventRead:
        self._require_enabled_category(user_id, payload.category_id)
        event = CldUserEvent(user_id=user_id, **payload.model_dump(mode="python"))
        self._repository.add(event)
        self._repository.flush()
        return CldUserEventRead.model_validate(event)

    def update(self, user_id: int, event_id: int, payload: CldUserEventWrite) -> CldUserEventRead:
        event = self._get(user_id, event_id)
        self._require_enabled_category(user_id, payload.category_id)
        event.category_id = payload.category_id
        event.code = payload.code
        event.first_day = payload.first_day
        event.last_day = payload.last_day
        event.name = payload.name
        event.detail = payload.detail
        self._repository.flush()
        return CldUserEventRead.model_validate(event)

    def delete(self, user_id: int, event_id: int) -> None:
        # Borrado real: nada referencia a cld_user_events.
        self._repository.delete(self._get(user_id, event_id))
        self._repository.flush()

    def _get(self, user_id: int, event_id: int) -> CldUserEvent:
        event = self._repository.get(event_id, user_id=user_id)
        if event is None:
            raise CldUserEventNotFoundError(f"Evento {event_id} no encontrado")
        return event

    def _require_enabled_category(self, user_id: int, category_id: int) -> None:
        # Una categoria DISABLED no sirve: sus eventos no se muestran en el
        # calendario, asi que el evento quedaria invisible apenas se guarda.
        category = self._category_repository.get(category_id, user_id=user_id)
        if category is None or category.status != CategoryStatus.ENABLED.value:
            raise CategoryNotFoundError(category_id)
