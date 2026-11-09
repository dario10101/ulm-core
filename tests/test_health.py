"""Pruebas unitarias del endpoint de salud."""

from tests.conftest import client


def test_health_check_returns_ok():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_check_exposes_version():
    # El deploy compara este valor con el SHA del commit (ver ci.yml, Smoke test).
    response = client.get("/api/v1/health")
    assert response.json()["version"] == "dev"


def test_root_returns_welcome_message():
    response = client.get("/")
    assert response.status_code == 200
    assert "esta corriendo" in response.json()["message"]
