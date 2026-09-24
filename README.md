# ULM Core (Backend)

Backend de **Unified Life Manager (ULM)**, una aplicacion personal de gestion diaria: habitos, finanzas y publicacion de contenido.

## Funcionalidad

Este repositorio expone la API REST que consume `ulm-web`. Estado actual:

- **Habitos**: endpoint dummy en memoria (pendiente de persistencia real).
- **Peso corporal**: CRUD completo con paginacion y filtro por rango de fechas.
- **Checklist**: modulo completo — categorias (CRUD + reordenar por prioridad), template semanal fijo por dia/categoria, generacion/seguimiento de la semana en curso (tareas con estado pendiente/completada/no lograda, puntaje y cierre de semana), alta de tareas circunstanciales directo en la semana sin modificar el template, y un campo `detail` (descripcion libre opcional) tanto en tareas de template como de semana.
- **Tareas de calendario** (`cld_tasks`): tareas puntuales o recurrentes (semanal/mensual/anual, con ancla de fecha+hora y clamp al ultimo dia del mes cuando aplica) creadas desde "Add record". Tienen una duracion (`duration_minutes`, default 60) que nunca puede cruzar la medianoche del dia de inicio (validado tanto al crear como al editar). Opcionalmente se sincronizan con el checklist semanal (semana actual al crearse, y semanas futuras al crearse cada una) sin modificar nunca el template. Se pueden consultar por dia o por rango de fechas (vistas diaria/semanal del calendario), editar, y borrar una ocurrencia puntual o la serie completa (`excluded_dates`).
- **Eventos de calendario**: `cld_events` (festivos y eventos generales, no ligados a un usuario; por ahora los 19 festivos de Colombia 2026) y `cld_user_events` (rangos personales del usuario, ej. vacaciones/viajes; sin CRUD en el front todavia). Ambas tablas tienen un campo `code` (ej. `HOLIDAY`, `SPECIAL_DATE` en `cld_events`; `TRAVEL`, `VACATION`, `BIRTHDAY` en `cld_user_events`) que la vista anual del front usa para filtrar por tipo de evento. La vista semanal los consulta como marcadores de inicio/fin (o dia unico si `first_day == last_day`, caso de los festivos); las vistas mensual y anual consultan ademas el rango completo (sin recortar), para pintar cada dia que un evento cubre.
- **Vista mensual**: `GET /calendar-tasks` (por rango) ahora devuelve todas las ocurrencias de una tarea recurrente dentro de un mes completo, no solo una (una tarea `WEEKLY` puede caer 4-5 veces en un mes; antes solo se soportaban rangos de hasta 7 dias).

| Endpoint | Metodo | Descripcion |
|---|---|---|
| `/` | GET | Mensaje de bienvenida / smoke test |
| `/api/v1/health` | GET | Estado del servicio |
| `/api/v1/habits/` | GET | Lista dummy de habitos (datos en memoria) |
| `/api/v1/dummy/` | POST | Crea un registro en la tabla `dummy` (Postgres) |
| `/api/v1/dummy/` | GET | Lista los registros de la tabla `dummy` (Postgres) |
| `/api/v1/weights/` | POST | Crea un registro de peso |
| `/api/v1/weights/` | GET | Lista registros de peso, paginado y con filtro opcional de rango de fechas (`start_date`, `end_date`) |
| `/api/v1/weights/{id}` | PUT | Reemplaza un registro de peso |
| `/api/v1/weights/{id}` | DELETE | Elimina un registro de peso |
| `/api/v1/checklists/categories` | GET | Lista las categorias del checklist, ordenadas por prioridad |
| `/api/v1/checklists/categories` | PUT | Guardado en bloque: crea, renombra, reordena y elimina categorias en una sola operacion |
| `/api/v1/checklists/template/tasks` | GET | Lista las tareas del template semanal (con los dias a los que aplica cada una) |
| `/api/v1/checklists/template/tasks` | POST | Crea una tarea de template, pudiendo aplicarla a varios dias a la vez (incluye `detail` opcional) |
| `/api/v1/checklists/template/tasks/{id}` | PUT | Edita una tarea de template para un dia puntual (`day`), sin afectar los demas dias en los que aplica |
| `/api/v1/checklists/template/tasks/{id}` | DELETE | Elimina una tarea de template para un dia puntual (`day`) |
| `/api/v1/checklists/weeks/current` | GET | Devuelve la semana abierta actual (o `null` si no hay ninguna) |
| `/api/v1/checklists/weeks/next-range` | GET | Limites minimos para la proxima semana: `min_first_day` (dia siguiente al cierre de la ultima semana, o hasta 7 dias atras de hoy si es la primera) y `min_last_day` (hoy) |
| `/api/v1/checklists/weeks` | POST | Crea una semana (1 a 7 dias, sin solaparse con la anterior ni terminar en el pasado) y copia las tareas del template y de `cld_tasks` (`add_to_checklist=true`) que apliquen |
| `/api/v1/checklists/weeks/{id}/close` | POST | Cierra la semana y calcula su puntaje final (falla con 409 si quedan tareas en `PENDING`) |
| `/api/v1/checklists/weeks/{id}/tasks` | GET | Lista las tareas concretas de una semana |
| `/api/v1/checklists/weeks/{id}/tasks` | POST | Agrega una tarea circunstancial directo a la semana (sin pasar por el template) |
| `/api/v1/checklists/tasks/{id}` | PATCH | Cambia el estado de una tarea de la semana (`PENDING`, `COMPLETE`, `FAILED`) |
| `/api/v1/checklists/tasks/{id}` | PUT | Edita nombre/importancia/categoria/detalle de una tarea de semana (no cambia dia ni semana) |
| `/api/v1/checklists/tasks/{id}` | DELETE | Elimina una tarea de semana, sin confirmacion |
| `/api/v1/calendar-tasks` | POST | Crea una tarea de calendario (puntual o recurrente); si `add_to_checklist` es `true`, la agrega de una a la semana actual cuando la fecha cae en su rango |
| `/api/v1/calendar-tasks?date=` | GET | Ocurrencias concretas de todas las tareas de calendario para un dia puntual (dia local del usuario, vista diaria) |
| `/api/v1/calendar-tasks?first_day=&last_day=` | GET | Igual que el anterior, pero para un rango de fechas (vista semanal) |
| `/api/v1/calendar-tasks/{id}` | PUT | Edita una tarea de calendario (nombre, categoria, importancia, notify, detalle, fecha/hora); no permite tocar `repeat_mode` ni `add_to_checklist` |
| `/api/v1/calendar-tasks/{id}?occurrence_date=` | DELETE | Elimina la tarea; si se pasa `occurrence_date` y la tarea repite, borra solo esa ocurrencia (queda en `excluded_dates`) en vez de toda la serie |
| `/api/v1/calendar-tasks/{id}/checklist?occurrence_date=` | POST | Marca `add_to_checklist=true` y agrega esa ocurrencia a la semana actual si la cubre (si no, queda pendiente para la proxima semana que la cubra) |
| `/api/v1/calendar-events?first_day=&last_day=` | GET | Marcadores de festivos/eventos generales (`cld_events`) y personales (`cld_user_events`) que se solapan con el rango: inicio, fin, o dia unico si `first_day == last_day` |
| `/api/v1/calendar-events/ranges?first_day=&last_day=` | GET | Igual que el anterior, pero sin recortar a inicio/fin: devuelve el rango completo (`first_day`/`last_day` originales) de cada evento que se solapa, para pintar cada dia que cubre (vista mensual) |

Coleccion de Postman lista para importar: [doc/ulm-core.postman_collection.json](./doc/ulm-core.postman_collection.json).

## Migraciones de base de datos

El esquema lo maneja **Alembic**, no `create_all()` (que solo creaba tablas faltantes y nunca alteraba las existentes). La app ya no toca el esquema al arrancar.

```bash
alembic current                                   # en que revision esta la BD
alembic upgrade head                              # aplicar lo pendiente
alembic revision --autogenerate -m "descripcion"  # crear una migracion...
alembic check                                     # ...o verificar que no hay drift
```

Despues de cambiar un modelo: generar la migracion, **abrir el archivo y revisarlo** (autogenerate no detecta renombres: los genera como drop + add, con perdida de datos), y aplicarla. Fundamentos y trampas: [../ulm-repository/how-to/alembic.md](../ulm-repository/how-to/alembic.md).

## Zona horaria

La base guarda **siempre UTC** (`timestamptz`); la zona de cada usuario vive en `users.timezone` como nombre IANA (ej. `America/Bogota`, no un offset `-5`: en zonas con horario de verano el offset correcto depende de la fecha).

Contrato de la API para tareas de calendario:

| Campo | Formato | Ejemplo |
|---|---|---|
| `scheduled_date` / `repeat_date` (entrada y salida) | hora de pared del usuario, **sin** zona | `2026-09-15T19:30:00` |
| `occurrence_at` (salida) | instante exacto, UTC | `2026-09-16T00:30:00Z` |
| `occurrence_local` (salida) | la misma ocurrencia en hora de pared | `2026-09-15T19:30:00` |

Una fecha de entrada con offset (`...Z` o `+02:00`) se rechaza con **422**: significaria que el cliente ya convirtio por su cuenta, probablemente con la zona del navegador, que no tiene por que ser la del usuario.

Todo calculo de calendario (que dia es, que dia de la semana, que dia del mes) se hace convirtiendo primero a la zona del usuario. Calcularlo sobre el instante UTC corre las tareas de la noche al dia siguiente. Ver `app/services/cld_task_sync.py`.

> Nota de despliegue: `zoneinfo` necesita la base de datos IANA del sistema, que Windows y las imagenes Docker `slim` no traen. Por eso `tzdata` esta en `requirements.txt`.

## Stack tecnico

- **Lenguaje**: Python 3.12
- **Framework**: FastAPI
- **Servidor ASGI**: Uvicorn
- **Validacion/config**: Pydantic v2 + pydantic-settings
- **ORM**: SQLAlchemy 2.0 + psycopg2 (driver de Postgres)
- **Testing**: Pytest + FastAPI TestClient (SQLite en memoria, no requieren Docker/Postgres)
- **Base de datos**: PostgreSQL, corriendo local en Docker (ver [guia de setup](../ulm-repository/postgres-local-setup.md))

## Estructura

```
app/
  api/routes/   # Endpoints agrupados por dominio
  core/         # Configuracion y utilidades transversales
  db/           # Motor de conexion, sesion y modelos ORM (SQLAlchemy)
  models/       # Modelos Pydantic (dominio sin persistencia, ej. habits)
  schemas/      # Esquemas Pydantic de entrada/salida para modelos con persistencia
  main.py       # Punto de entrada de la app FastAPI
tests/          # Pruebas unitarias (pytest)
doc/            # Coleccion de Postman
```

## Guia de instalacion

1. Crear/activar entorno virtual (ya incluido en `venv/`, o crear uno nuevo):
   ```
   python -m venv venv
   venv\Scripts\activate      # Windows
   source venv/bin/activate   # Linux/Mac
   ```
2. Instalar dependencias:
   ```
   pip install -r requirements.txt
   ```
3. Levantar Postgres local en Docker: ver [ulm-repository/postgres-local-setup.md](../ulm-repository/postgres-local-setup.md).
4. Levantar el servidor de desarrollo:
   ```
   uvicorn app.main:app --reload
   ```
   Las tablas se crean automaticamente al iniciar (`Base.metadata.create_all`); si Postgres no esta corriendo, la app arranca igual pero los endpoints de `dummy` fallaran. **Ojo**: `create_all` solo crea tablas que no existen, no agrega columnas nuevas a una tabla ya creada (no hay Alembic en este proyecto). Si se agrega un campo a un modelo existente, hay que correr el `ALTER TABLE` a mano contra la base local.
5. Abrir la documentacion interactiva en `http://127.0.0.1:8000/docs`

## Correr pruebas

```
pytest -v
```

## Estilo de desarrollo

Ver [STYLEGUIDE.md](./STYLEGUIDE.md).
