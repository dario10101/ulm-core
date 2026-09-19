"""Pruebas unitarias de lectura/escritura sobre la tabla dummy.

Usa SQLite en memoria en vez de Postgres para no depender del contenedor Docker
local durante las pruebas automatizadas.
"""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base_class import Base
from app.db.session import get_db
from app.main import app

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
Base.metadata.create_all(bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


def test_create_and_list_dummy():
    create_response = client.post(
        "/api/v1/dummy/",
        json={"name": "registro de prueba", "description": "creado en test", "value": 12.5},
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["name"] == "registro de prueba"
    assert created["is_active"] is True

    list_response = client.get("/api/v1/dummy/")
    assert list_response.status_code == 200
    body = list_response.json()
    assert any(item["id"] == created["id"] for item in body)
