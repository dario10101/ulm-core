"""Logica de negocio de categorias de checklist. Las rutas dependen de esto,
nunca del repository directamente."""

from collections.abc import Sequence

from app.db.models.checklist import ChecklistCategory
from app.repositories.category_repository import CategoryRepository
from app.schemas.checklist import CategoryRead, CategoryStatus, CategoryWrite
from app.services.errors import (
    CategoryInUseError,
    CategoryNameTakenError,
    CategoryNotFoundError,
    DuplicateCategoryNameError,
)
from app.services.mappers import category_to_read


class CategoryService:
    def __init__(self, repository: CategoryRepository) -> None:
        self._repository = repository

    def list_categories(
        self, user_id: int, *, include_disabled: bool = False
    ) -> list[CategoryRead]:
        categories = (
            self._repository.list_all_by_user(user_id)
            if include_disabled
            else self._repository.list_by_user(user_id)
        )
        return [category_to_read(c) for c in categories]

    def enable_category(self, user_id: int, category_id: int) -> CategoryRead:
        """Reactiva una categoria DISABLED: vuelve a aparecer en todas las
        listas ENABLED, al final (nueva prioridad = ultima + 1)."""
        category = self._repository.get(category_id)
        if category is None or category.user_id != user_id:
            raise CategoryNotFoundError({category_id})

        enabled = self._repository.list_by_user(user_id)
        next_priority = max((c.priority for c in enabled), default=0) + 1
        self._repository.enable(category, next_priority)
        self._repository.flush()
        return category_to_read(category)

    def replace_categories(self, user_id: int, items: list[CategoryWrite]) -> list[CategoryRead]:
        """Guardado en bloque: crea, renombra, reordena y elimina en una sola
        operacion (botones Guardar/Cancelar de la pantalla de administracion).

        El orden de `items` define la prioridad (indice + 1). Una categoria
        existente que no aparece en `items` se interpreta como eliminada.
        """
        all_categories = self._repository.list_all_by_user(user_id)
        existing = {c.id: c for c in all_categories if c.status == CategoryStatus.ENABLED.value}
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

        self._check_names(items, all_categories, to_delete_ids)

        for category_id in to_delete_ids:
            self._repository.disable(existing[category_id])

        # Renombres en dos pasos. El indice unico de nombre se valida fila por
        # fila, asi que intercambiar dos nombres (A->"B", B->"A") choca en el
        # primer UPDATE contra el nombre que la otra todavia tiene. Pasar
        # primero por un nombre temporal (unico por id) libera todos los
        # nombres viejos antes de asignar los nuevos.
        renamed = [
            existing[item.id]
            for item in items
            if item.id is not None and existing[item.id].name != item.name
        ]
        if renamed:
            for category in renamed:
                category.name = f"__renaming_{category.id}"
            self._repository.flush()

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

        # flush y no commit: el commit lo hace get_db al cerrar el request. Aca
        # hace falta para que las categorias nuevas tengan su id asignado.
        self._repository.flush()

        result.sort(key=lambda c: c.priority)
        return [category_to_read(c) for c in result]

    @staticmethod
    def _check_names(
        items: list[CategoryWrite],
        all_categories: Sequence[ChecklistCategory],
        to_delete_ids: set[int],
    ) -> None:
        """Valida antes de escribir lo mismo que el indice unico de la base
        (usuario + lower(name), contando DISABLED), para responder con un
        error que diga que nombre choca en vez de un IntegrityError."""
        seen: set[str] = set()
        duplicated: list[str] = []
        for item in items:
            key = item.name.lower()
            if key in seen and item.name not in duplicated:
                duplicated.append(item.name)
            seen.add(key)
        if duplicated:
            raise DuplicateCategoryNameError(duplicated)

        # Nombres que quedan ocupados por filas que no estan en el payload: las
        # ya deshabilitadas y las que este mismo guardado deshabilita.
        inactive = {
            c.name.lower(): c.name
            for c in all_categories
            if c.status != CategoryStatus.ENABLED.value or c.id in to_delete_ids
        }
        taken = [item.name for item in items if item.name.lower() in inactive]
        if taken:
            raise CategoryNameTakenError(taken)
