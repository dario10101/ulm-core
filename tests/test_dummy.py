"""Pruebas unitarias de lectura/escritura sobre la tabla dummy.

Usa SQLite en memoria en vez de Postgres para no depender del contenedor Docker
local durante las pruebas automatizadas.
"""


from tests.conftest import client


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
