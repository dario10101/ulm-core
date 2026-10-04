"""Configuracion compartida de las pruebas.

Antes, cada tests/test_*.py creaba su propio engine y asignaba
`app.dependency_overrides[get_db]` a nivel de modulo. Como `app` es un
singleton y pytest importa todos los modulos antes de correr, ganaba el
ultimo import: toda la suite terminaba corriendo contra la base de un solo
archivo. Los tests pasaban, pero el aislamiento era ficticio.

Ahora hay un unico engine y una fixture autouse que le da a cada test su
propia transaccion, que se revierte al terminar. Cada test arranca con el
esquema creado y el usuario por defecto sembrado, y nada de lo que escriba
sobrevive al siguiente.

Login: por defecto cada request se hace como el usuario por defecto, sin
cookie (se reemplaza `get_current_user`) y con todos los permisos de dominio
(se reemplaza `get_current_permissions`). `acting_as` cambia de usuario. Los
tests del login usan `real_auth` y los de permisos `real_permissions`, que
quitan cada reemplazo.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_permissions, get_current_user
from app.db.base_class import Base

# Importar los modelos para que sus tablas queden registradas en Base.metadata
from app.db.models import checklist as checklist_model  # noqa: F401
from app.db.models import cld_event as cld_event_model  # noqa: F401
from app.db.models import cld_task as cld_task_model  # noqa: F401
from app.db.models import cld_user_event as cld_user_event_model  # noqa: F401
from app.db.models import finance as finance_model  # noqa: F401
from app.db.models import meal as meal_model  # noqa: F401
from app.db.models import user as user_model  # noqa: F401
from app.db.models import weight as weight_model  # noqa: F401
from app.db.models.user import User
from app.db.session import get_db
from app.main import app
from app.services.permissions import ALL_PERMISSIONS

# SQLite en memoria para no depender de Postgres. StaticPool mantiene una sola
# conexion viva, que es lo que hace que ":memory:" persista entre operaciones.
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


# El driver pysqlite abre transacciones por su cuenta de una forma que rompe
# SAVEPOINT, y sin SAVEPOINT los commit() de la aplicacion se aplicarian de
# verdad y el rollback del final del test no los desharia. El workaround
# documentado por SQLAlchemy es desactivar ese manejo implicito y emitir el
# BEGIN nosotros.
@event.listens_for(test_engine, "connect")
def _disable_pysqlite_implicit_begin(dbapi_connection, connection_record):
    dbapi_connection.isolation_level = None
    # SQLite ignora las FOREIGN KEY salvo que se active por conexion. Sin
    # esto, las FK compuestas que impiden referenciar filas de otro usuario
    # (ver app/db/models/checklist.py) no se probarian nunca fuera de Postgres.
    dbapi_connection.execute("PRAGMA foreign_keys = ON")


@event.listens_for(test_engine, "begin")
def _emit_explicit_begin(conn):
    conn.exec_driver_sql("BEGIN")


Base.metadata.create_all(bind=test_engine)

# El cliente no guarda estado de base: la sesion se la inyecta la fixture de
# abajo en cada test, asi que puede ser uno solo para toda la suite.
client = TestClient(app)

# Usuario "A" de todos los tests. Zona Bogota (UTC-5, sin horario de verano):
# los tests de comidas y calendario hacen cuentas con ese offset.
DEFAULT_USER_ID = 1

# Pila de "quien hace el request": el tope es el usuario actual (ver acting_as).
_acting_user_ids: list[int] = [DEFAULT_USER_ID]


@pytest.fixture(autouse=True)
def db_session():
    """Una transaccion por test, revertida al final.

    `join_transaction_mode="create_savepoint"` hace que los commit() del
    codigo de la aplicacion liberen un savepoint en vez de cerrar la
    transaccion externa, que es lo que permite revertir todo al terminar
    aunque el service haya hecho commit.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    session.add(
        User(id=DEFAULT_USER_ID, name="Ruben", email="ruben@example.com", timezone="America/Bogota")
    )
    session.commit()

    # Se replica la semantica de produccion (una transaccion por request, ver
    # app/db/session.py) en vez de entregar la sesion pelada: asi los tests
    # ejercitan el mismo commit/rollback que la app real. El commit libera un
    # savepoint, y el rollback de abajo deshace todo igual.
    def override_get_db():
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: session.get(User, _acting_user_ids[-1])
    app.dependency_overrides[get_current_permissions] = lambda: ALL_PERMISSIONS
    try:
        yield session
    finally:
        app.dependency_overrides.clear()
        session.close()
        transaction.rollback()
        connection.close()


# --- Aislamiento entre usuarios ---

# DEFAULT_USER_ID es el "A" de los tests de aislamiento; este es el "B",
# dueño de los recursos que A intenta tocar.
OTHER_USER_ID = 2


@pytest.fixture
def other_user(db_session) -> int:
    db_session.add(
        User(id=OTHER_USER_ID, name="Otra persona", email="otra@example.com", timezone="UTC")
    )
    db_session.commit()
    return OTHER_USER_ID


@contextmanager
def acting_as(user_id: int) -> Iterator[None]:
    """Los requests dentro del bloque se hacen como `user_id`. Reemplaza al
    usuario de la sesion, asi que todo lo que cuelga de el (id, zona horaria)
    es el de `user_id`, igual que con un login real."""
    _acting_user_ids.append(user_id)
    try:
        yield
    finally:
        _acting_user_ids.pop()


@pytest.fixture
def real_auth():
    """Quita el reemplazo de get_current_user: los requests necesitan una
    cookie de sesion de verdad. Para los tests del login."""
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def real_permissions():
    """Quita el reemplazo de get_current_permissions: cada usuario tiene solo
    lo que le asigne el test (o todo, si su email esta en ADMIN_EMAILS)."""
    app.dependency_overrides.pop(get_current_permissions, None)
