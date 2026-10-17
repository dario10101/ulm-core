"""Interfaz (Protocol) del almacen llave-valor del blog (blg_entities).

Es deliberadamente generico: las mismas cinco operaciones que ofrece DynamoDB
(GetItem, Query por prefijo del sort key, Query sobre un indice, PutItem,
DeleteItem). Migrar a Dynamo es escribir otra implementacion de esto; el
service, que conoce las claves y los documentos, no cambia.

La particion siempre sale de `user_id` (el usuario de la sesion): ningun
metodo recibe un `pk` del cliente, asi que no hay forma de leer o escribir el
blog de otro usuario.
"""

from collections.abc import Sequence
from typing import Any, Protocol

from app.db.models.blog import BlgEntity


class BlogEntityRepository(Protocol):
    def get(self, *, user_id: int, sk: str) -> BlgEntity | None: ...

    def query(self, *, user_id: int, sk_prefix: str) -> Sequence[BlgEntity]:
        """Las entidades de la particion cuyo sk empieza con `sk_prefix`, ordenadas por sk."""
        ...

    def get_by_index(self, *, user_id: int, gsi1pk: str, gsi1sk: str) -> BlgEntity | None: ...

    def create(
        self,
        *,
        user_id: int,
        sk: str,
        entity_type: str,
        data: dict[str, Any],
        gsi1pk: str | None = None,
        gsi1sk: str | None = None,
    ) -> BlgEntity: ...

    def delete(self, entity: BlgEntity) -> None: ...

    def flush(self) -> None:
        """Manda los cambios pendientes. Un UPDATE sobre una version que otro
        request ya cambio lanza ConcurrentUpdateError."""
        ...
