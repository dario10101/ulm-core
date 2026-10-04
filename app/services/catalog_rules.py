"""Reglas comunes de los catalogos administrables (tags, categorias, metodos de
pago, fuentes, subcategorias): unicidad del nombre y borrado hibrido."""

from collections.abc import Iterable
from typing import Protocol

from app.schemas.finance import CatalogDeleteResult, CatalogStatus
from app.services.errors import CatalogNameTakenError


class NamedCatalogItem(Protocol):
    id: int
    name: str
    status: str


def ensure_unique_name(
    name: str, siblings: Iterable[NamedCatalogItem], *, exclude_id: int | None = None
) -> None:
    """`siblings` son los items entre los que el nombre debe ser unico
    (incluidos los archivados). Sin distinguir mayusculas: "Mercado" y
    "mercado" partirian el mismo concepto en dos barras de analytics."""
    wanted = name.casefold()
    for item in siblings:
        if item.id != exclude_id and item.name.casefold() == wanted:
            raise CatalogNameTakenError(
                item.name, archived=item.status == CatalogStatus.DISABLED.value
            )


def delete_or_archive(item: NamedCatalogItem, *, usage_count: int, delete) -> CatalogDeleteResult:
    """Sin registros que lo usen se borra (`delete`); con registros se archiva,
    para que el historico y analytics sigan mostrandolo."""
    if usage_count == 0:
        delete(item)
        return CatalogDeleteResult.DELETED
    item.status = CatalogStatus.DISABLED.value
    return CatalogDeleteResult.ARCHIVED
