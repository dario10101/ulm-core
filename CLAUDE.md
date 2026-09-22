# ULM Core

Backend de ULM (gestion personal: habitos, finanzas, contenido). API REST consumida por `ulm-web`.

**Stack**: Python 3.12, FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2.0 + psycopg2, PostgreSQL (Docker local), Pytest.

**Estructura**: `app/api/routes` (endpoints) + `app/api/deps.py` (inyeccion Session->Repository->Service), `app/core` (config), `app/db` (engine/sesion/modelos ORM/seed), `app/repositories` (acceso a datos, detras de un `Protocol` por dominio), `app/services` (logica de negocio; las rutas nunca llaman a un repository directo), `app/models` (Pydantic sin persistencia), `app/schemas` (Pydantic con persistencia), `tests/`, `doc/` (Postman).

Patron establecido con `weights` (repository + service desacoplados): replicarlo para cada dominio nuevo en vez de que las rutas hablen directo con SQLAlchemy (como sigue haciendo `dummy`, que quedo como esta a proposito por ser el endpoint de prueba original).

**Zona horaria**: la BD guarda siempre UTC; cada usuario tiene su zona IANA en `users.timezone`. La API habla *hora de pared* del usuario en `scheduled_date`/`repeat_date` (string sin `Z` ni offset; una fecha con offset se rechaza con 422) y devuelve las ocurrencias en las dos formas: `occurrence_at` (instante UTC) y `occurrence_local` (hora de pared, que es lo que el front pinta). Toda cuenta de calendario —que dia es, que dia de semana, que dia del mes— se hace **despues** de convertir a la zona del usuario, nunca sobre el instante UTC. Ver `app/services/cld_task_sync.py`.

Estilo: ver STYLEGUIDE.md (codigo en ingles, comentarios/logs en espanol).
