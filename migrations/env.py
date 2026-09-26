"""Configuracion de Alembic para ULM Core.

La URL de la base se lee de `app.core.config.settings`, no de alembic.ini: una
sola fuente de verdad (y la credencial no queda duplicada en un archivo mas).
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.db.base_class import Base

# Importar TODOS los modelos para que sus tablas queden registradas en
# Base.metadata. Si falta alguno, --autogenerate no lo ve y propone borrar su
# tabla (ver ulm-repository/how-to/alembic.md).
from app.db.models import checklist as checklist_model  # noqa: F401
from app.db.models import cld_event as cld_event_model  # noqa: F401
from app.db.models import cld_task as cld_task_model  # noqa: F401
from app.db.models import cld_user_event as cld_user_event_model  # noqa: F401
from app.db.models import dummy as dummy_model  # noqa: F401
from app.db.models import finance as finance_model  # noqa: F401
from app.db.models import meal as meal_model  # noqa: F401
from app.db.models import user as user_model  # noqa: F401
from app.db.models import weight as weight_model  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Opciones de comparacion de --autogenerate:
# - compare_type: detecta cambios de tipo de columna.
# - compare_server_default: detecta cambios de DEFAULT.
# - render_as_batch: necesario para SQLite (no soporta casi ningun ALTER
#   TABLE); en Postgres se comporta como un ALTER normal.
COMPARE_OPTIONS = {
    "compare_type": True,
    "compare_server_default": True,
    "render_as_batch": True,
}


def run_migrations_offline() -> None:
    """Genera el SQL sin conectarse (alembic upgrade head --sql)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **COMPARE_OPTIONS,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, **COMPARE_OPTIONS)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
