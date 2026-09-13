"""Pruebas unitarias del modulo dummy de habitos."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_list_habits_returns_seed_data():
    response = client.get("/api/v1/habits/")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["name"] == "Leer 20 minutos"
