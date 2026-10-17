"""Implementacion del BlogEntityRepository sobre SQLAlchemy/Postgres."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.db.models.blog import BlgEntity
from app.repositories import blog_keys
from app.services.errors import ConcurrentUpdateError


class SqlAlchemyBlogEntityRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, *, user_id: int, sk: str) -> BlgEntity | None:
        return self._db.get(BlgEntity, (blog_keys.partition(user_id), sk))

    def query(self, *, user_id: int, sk_prefix: str) -> Sequence[BlgEntity]:
        # La igualdad sobre pk acota la busqueda a la particion del usuario
        # (unas decenas o cientos de filas), asi que el LIKE del prefijo no
        # necesita indice propio. autoescape: un `_` o `%` en el prefijo es
        # literal, no comodin.
        return (
            self._db.execute(
                select(BlgEntity)
                .where(
                    BlgEntity.pk == blog_keys.partition(user_id),
                    BlgEntity.sk.startswith(sk_prefix, autoescape=True),
                )
                .order_by(BlgEntity.sk)
            )
            .scalars()
            .all()
        )

    def get_by_index(self, *, user_id: int, gsi1pk: str, gsi1sk: str) -> BlgEntity | None:
        return self._db.execute(
            select(BlgEntity).where(
                BlgEntity.pk == blog_keys.partition(user_id),
                BlgEntity.gsi1pk == gsi1pk,
                BlgEntity.gsi1sk == gsi1sk,
            )
        ).scalar_one_or_none()

    def create(
        self,
        *,
        user_id: int,
        sk: str,
        entity_type: str,
        data: dict[str, Any],
        gsi1pk: str | None = None,
        gsi1sk: str | None = None,
    ) -> BlgEntity:
        entity = BlgEntity(
            pk=blog_keys.partition(user_id),
            sk=sk,
            user_id=user_id,
            entity_type=entity_type,
            data=data,
            gsi1pk=gsi1pk,
            gsi1sk=gsi1sk,
        )
        self._db.add(entity)
        return entity

    def delete(self, entity: BlgEntity) -> None:
        self._db.delete(entity)

    def flush(self) -> None:
        try:
            self._db.flush()
        except StaleDataError as exc:
            # Otro request cambio la fila entre que este la leyo y la escribio
            # (version distinta). Ver BlgEntity.version.
            raise ConcurrentUpdateError() from exc
