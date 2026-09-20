"""Logica de negocio de categorias de checklist. Las rutas dependen de esto,
nunca del repository directamente."""

from typing import Sequence

from app.db.models.checklist import ChecklistCategory
from app.repositories.category_repository import CategoryRepository
from app.schemas.checklist import CategoryWrite


class CategoryNotFoundError(Exception):
    """Se referencio un id de categoria que no existe (o no es del usuario)."""

    def __init__(self, category_ids: set[int]) -> None:
        self.category_ids = category_ids


class CategoryInUseError(Exception):
    """Se intento eliminar una categoria que todavia tiene tareas de template."""

    def __init__(self, category_names: list[str]) -> None:
        self.category_names = category_names


class CategoryService:
    def __init__(self, repository: CategoryRepository) -> None:
        self._repository = repository

    def list_categories(self, user_id: int, *, include_disabled: bool = False) -> Sequence[ChecklistCategory]:
        if include_disabled:
            return self._repository.list_all_by_user(user_id)
        return self._repository.list_by_user(user_id)

    def enable_category(self, user_id: int, category_id: int) -> ChecklistCategory:
        """Reactiva una categoria DISABLED: vuelve a aparecer en todas las
        listas ENABLED, al final (nueva prioridad = ultima + 1)."""
        category = self._repository.get(category_id)
        if category is None or category.user_id != user_id:
            raise CategoryNotFoundError({category_id})

        enabled = self._repository.list_by_user(user_id)
        next_priority = max((c.priority for c in enabled), default=0) + 1
        self._repository.enable(category, next_priority)
        self._repository.commit()
        self._repository.refresh(category)
        return category

    def replace_categories(
        self, user_id: int, items: list[CategoryWrite]
    ) -> list[ChecklistCategory]:
        """Guardado en bloque: crea, renombra, reordena y elimina en una sola
        operacion (botones Guardar/Cancelar de la pantalla de administracion).

        El orden de `items` define la prioridad (indice + 1). Una categoria
        existente que no aparece en `items` se interpreta como eliminada.
        """
        existing = {c.id: c for c in self._repository.list_by_user(user_id)}
        payload_ids = {item.id for item in items if item.id is not None}

        unknown_ids = payload_ids - existing.keys()
        if unknown_ids:
            raise CategoryNotFoundError(unknown_ids)

        to_delete_ids = existing.keys() - payload_ids
        in_use = [
            existing[category_id].name
            for category_id in to_delete_ids
            if self._repository.has_template_tasks(category_id)
        ]
        if in_use:
            raise CategoryInUseError(in_use)

        for category_id in to_delete_ids:
            self._repository.disable(existing[category_id])

        result: list[ChecklistCategory] = []
        for index, item in enumerate(items):
            priority = index + 1
            if item.id is None:
                category = ChecklistCategory(user_id=user_id, name=item.name, priority=priority)
                self._repository.add(category)
            else:
                category = existing[item.id]
                category.name = item.name
                category.priority = priority
            result.append(category)

        self._repository.commit()
        for category in result:
            self._repository.refresh(category)

        result.sort(key=lambda c: c.priority)
        return result
