"""Interfaz (Protocol) del acceso a datos de categorias de checklist."""

from collections.abc import Sequence
from typing import Protocol

from app.db.models.checklist import ChecklistCategory


class CategoryRepository(Protocol):
    def list_by_user(self, user_id: int) -> Sequence[ChecklistCategory]:
        """Solo categorias con status ENABLED (ver CategoryStatus)."""
        ...

    def list_by_ids(self, user_id: int, category_ids: Sequence[int]) -> Sequence[ChecklistCategory]:
        """Sin filtrar por status: usado por analytics, que debe poder
        mostrar el nombre de una categoria historica aunque hoy este
        DISABLED."""
        ...

    def list_all_by_user(self, user_id: int) -> Sequence[ChecklistCategory]:
        """Todas (ENABLED y DISABLED), en ese orden: primero las habilitadas
        por prioridad, despues las deshabilitadas. Uso exclusivo de la
        pantalla de administracion de categorias."""
        ...

    def get(self, category_id: int) -> ChecklistCategory | None: ...

    def flush(self) -> None:
        """Manda los INSERT/UPDATE pendientes a la base sin cerrar la
        transaccion. Sirve para obtener los ids autogenerados; el commit lo
        hace `get_db` al final del request."""
        ...

    def add(self, category: ChecklistCategory) -> None: ...

    def disable(self, category: ChecklistCategory) -> None:
        """Soft-delete: marca la categoria como DISABLED, nunca la borra."""
        ...

    def enable(self, category: ChecklistCategory, priority: int) -> None:
        """Reactiva una categoria DISABLED, al final de las habilitadas."""
        ...

    def has_template_tasks(self, category_id: int) -> bool: ...
