# ULM Core

Backend de ULM (gestion personal: habitos, finanzas, contenido). API REST consumida por `ulm-web`.

**Stack**: Python 3.12, FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2.0 + psycopg2, PostgreSQL (Docker local), Pytest.

**Estructura**: `app/api/routes` (endpoints) + `app/api/deps.py` (inyeccion Session->Repository->Service), `app/core` (config, CSRF), `app/db` (engine/sesion/modelos ORM), `app/repositories` (acceso a datos, detras de un `Protocol` por dominio), `app/services` (logica de negocio; las rutas nunca llaman a un repository directo), `app/integrations` (clientes externos, ej. Google, detras de un `Protocol`), `app/schemas` (Pydantic), `scripts/` (`manage_users`: invitar/administrar usuarios), `tests/`, `doc/` (Postman).

Patron establecido con `weights` (repository + service desacoplados): replicarlo para cada dominio nuevo en vez de que las rutas hablen directo con SQLAlchemy.

**Auth**: login con Google (OIDC + PKCE), sesion en cookie httpOnly con el token hasheado en `user_sessions`. Solo entran usuarios invitados (`REGISTRATION_MODE`). Todo router va en `PRIVATE_ROUTERS` de `app/main.py` salvo `health`/`auth`/`public_blogs` (`PUBLIC_ROUTERS`; lo publico usa schemas propios y 404 uniforme); `tests/test_auth.py` falla si una ruta queda sin sesion. Cada repository recibe `*, user_id`; tests de aislamiento en `tests/test_ownership.py`.

**Permisos**: catalogo en `app/services/permissions.py` (`weight`, `meals`, `finances`, `planning` + `.ai`; `blog` sin `.ai`). Cada router de `PRIVATE_ROUTERS` declara su permiso (`require`, 403); `tests/test_permissions.py` falla si una ruta privada (salvo `/me`) no pide ninguno. El admin sale de `ADMIN_EMAILS` (config, no base): todos los permisos, entra sin invitacion, no se edita por API ni consola. Parametros globales (`/system/*`: categorias de gasto, metodos de pago, festivos) y la administracion de usuarios (`/admin/users`: listar, invitar, `PUT` del conjunto completo de permisos, deshabilitar/habilitar; mismo `UserAdminService` que `scripts/manage_users.py`) van con `ADMIN_ONLY` en `PRIVATE_ROUTERS` (`require_admin`); los del dominio (`/finances/*`: tags, fuentes, subcategorias) con su permiso. Catalogos: borrado hibrido (sin registros se borra, con registros se archiva `DISABLED`; ver `services/catalog_rules.py`).

**Zona horaria**: la BD guarda siempre UTC; cada usuario tiene su zona IANA en `users.timezone`. La API habla *hora de pared* del usuario en `scheduled_date`/`repeat_date` (string sin `Z` ni offset; una fecha con offset se rechaza con 422) y devuelve las ocurrencias en las dos formas: `occurrence_at` (instante UTC) y `occurrence_local` (hora de pared, que es lo que el front pinta). Toda cuenta de calendario —que dia es, que dia de semana, que dia del mes— se hace **despues** de convertir a la zona del usuario, nunca sobre el instante UTC. Ver `app/services/cld_task_sync.py`.

Estilo: ver STYLEGUIDE.md (codigo en ingles, comentarios/logs en espanol).
