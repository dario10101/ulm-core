"""Clase base declarativa compartida por todos los modelos ORM."""

from sqlalchemy import MetaData
from sqlalchemy.orm import declarative_base

# Convencion de nombres de constraints e indices.
#
# Sin esto, un constraint que no se nombra explicitamente recibe el nombre que
# le invente el motor (Postgres usa `tabla_columna_fkey`, `tabla_pkey`). Eso
# funciona hasta que una migracion necesita borrarlo o alterarlo: Alembic no
# sabe como se llama y genera `drop_constraint(None, ...)`, que falla. Con la
# convencion, el nombre es predecible desde el modelo.
#
# Un `name=` explicito en el modelo sigue teniendo prioridad sobre esto.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Base = declarative_base(metadata=MetaData(naming_convention=NAMING_CONVENTION))
