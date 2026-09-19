# ULM Core

Backend de ULM (gestion personal: habitos, finanzas, contenido). API REST consumida por `ulm-web`.

**Stack**: Python 3.12, FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2.0 + psycopg2, PostgreSQL (Docker local), Pytest.

**Estructura**: `app/api/routes` (endpoints) + `app/api/deps.py` (inyeccion Session->Repository->Service), `app/core` (config), `app/db` (engine/sesion/modelos ORM/seed), `app/repositories` (acceso a datos, detras de un `Protocol` por dominio), `app/services` (logica de negocio; las rutas nunca llaman a un repository directo), `app/models` (Pydantic sin persistencia), `app/schemas` (Pydantic con persistencia), `tests/`, `doc/` (Postman).

Patron establecido con `weights` (repository + service desacoplados): replicarlo para cada dominio nuevo en vez de que las rutas hablen directo con SQLAlchemy (como sigue haciendo `dummy`, que quedo como esta a proposito por ser el endpoint de prueba original).

Estilo: ver STYLEGUIDE.md (codigo en ingles, comentarios/logs en espanol).
