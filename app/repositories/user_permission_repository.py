"""Interfaz (Protocol) del acceso a datos de permisos de dominio."""

from typing import Protocol


class UserPermissionRepository(Protocol):
    def list_for_user(self, user_id: int) -> set[str]:
        """Los valores guardados, tal cual (pueden incluir uno que ya no exista
        en el catalogo: ver permissions.known_permissions)."""
        ...

    def add(self, user_id: int, permission: str, *, granted_by: int | None) -> None:
        """Idempotente: si ya lo tiene, no hace nada."""
        ...

    def remove(self, user_id: int, permission: str) -> None: ...
