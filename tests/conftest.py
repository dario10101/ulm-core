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
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base_class import Base

# Importar los modelos para que sus tablas queden registradas en Base.metadata
from app.db.models import checklist as checklist_model  # noqa: F401
from app.db.models import cld_event as cld_event_model  # noqa: F401
from app.db.models import cld_task as cld_task_model  # noqa: F401
from app.db.models import cld_user_event as cld_user_event_model  # noqa: F401
from app.db.models import dummy as dummy_model  # noqa: F401
from app.db.models import user as user_model  # noqa: F401
from app.db.models import weight as weight_model  # noqa: F401
from app.db.seed import ensure_default_user
from app.db.session import get_db
from app.main import app

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


@event.listens_for(test_engine, "begin")
def _emit_explicit_begin(conn):
    conn.exec_driver_sql("BEGIN")


Base.metadata.create_all(bind=test_engine)

# El cliente no guarda estado de base: la sesion se la inyecta la fixture de
# abajo en cada test, asi que puede ser uno solo para toda la suite.
client = TestClient(app)


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
    ensure_default_user(session)

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
    try:
        yield session
    finally:
        app.dependency_overrides.clear()
        session.close()
        transaction.rollback()
        connection.close()
