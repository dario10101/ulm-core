"""Modelo ORM del blog: una tabla generica llave-valor (blg_entities).

Diseño de tabla unica estilo DynamoDB (*single-table design*, decision B11 de
PLAN-BLOG.md): todo el blog de un usuario vive en la particion `USER#<id>` y
cada entidad (config, seccion, subseccion, elemento, cuerpo del .md) es una
fila con su `sk`. La forma de `data` la validan modelos Pydantic en el service
(app/services/blog_documents.py), no la base. Las claves se arman en un solo
lugar: app/repositories/blog_keys.py.

Lo que una tabla generica pierde frente a tablas relacionales se compensa asi:
- `user_id` es columna real con FK a users, y el CHECK de abajo obliga a que
  el `pk` sea el de ese usuario: la base rechaza una fila que mezcle dos
  usuarios aunque el codigo se equivoque.
- `version` es bloqueo optimista (version_id_col de SQLAlchemy): todo UPDATE
  lleva `WHERE version = <leida>`, el equivalente de una escritura
  condicional de DynamoDB.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base

# Tipos de entidad. Coinciden con el CHECK de la tabla.
ENTITY_BLOG = "BLOG"
ENTITY_SECTION = "SECTION"
ENTITY_GROUP = "GROUP"
ENTITY_ITEM = "ITEM"
ENTITY_BODY = "BODY"
ENTITY_TYPES = (ENTITY_BLOG, ENTITY_SECTION, ENTITY_GROUP, ENTITY_ITEM, ENTITY_BODY)


def _now() -> datetime:
    return datetime.now(UTC)


class BlgEntity(Base):
    __tablename__ = "blg_entities"
    __table_args__ = (
        # Indice secundario "GSI1": hoy solo sirve para que los slugs sean
        # unicos (de seccion por usuario, de elemento por seccion). NULL no
        # participa, asi que las entidades sin slug no chocan entre si.
        UniqueConstraint("gsi1pk", "gsi1sk", name="uq_blg_entities_gsi1"),
        CheckConstraint("pk = 'USER#' || user_id", name="pk_matches_user"),
        CheckConstraint(
            "entity_type IN ('BLOG', 'SECTION', 'GROUP', 'ITEM', 'BODY')", name="entity_type"
        ),
    )

    pk: Mapped[str] = mapped_column(String(40), primary_key=True)
    sk: Mapped[str] = mapped_column(String(120), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(10), nullable=False)
    gsi1pk: Mapped[str | None] = mapped_column(String(120), nullable=True)
    gsi1sk: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # JSONB en Postgres; JSON en SQLite (tests).
    data: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __mapper_args__ = {"version_id_col": version}
