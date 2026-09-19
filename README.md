# ULM Core (Backend)

Backend de **Unified Life Manager (ULM)**, una aplicacion personal de gestion diaria: habitos, finanzas y publicacion de contenido.

## Funcionalidad

Este repositorio expone la API REST que consume `ulm-web`. Estado actual:

- **Habitos**: endpoint dummy en memoria (pendiente de persistencia real).
- **Peso corporal**: CRUD completo con paginacion y filtro por rango de fechas.
- **Checklist**: modulo completo — categorias (CRUD + reordenar por prioridad), template semanal fijo por dia/categoria, y generacion/seguimiento de la semana en curso (tareas con estado pendiente/completada/no lograda, puntaje y cierre de semana).

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
| `/api/v1/checklists/template/tasks` | POST | Crea una tarea de template, pudiendo aplicarla a varios dias a la vez |
| `/api/v1/checklists/template/tasks/{id}` | PUT | Edita una tarea de template para un dia puntual (`day`), sin afectar los demas dias en los que aplica |
| `/api/v1/checklists/template/tasks/{id}` | DELETE | Elimina una tarea de template para un dia puntual (`day`) |
| `/api/v1/checklists/weeks/current` | GET | Devuelve la semana abierta actual (o `null` si no hay ninguna) |
| `/api/v1/checklists/weeks` | POST | Crea una semana (rango de 7 dias) y copia las tareas del template a partir de ella |
| `/api/v1/checklists/weeks/{id}/close` | POST | Cierra la semana y calcula su puntaje final |
| `/api/v1/checklists/weeks/{id}/tasks` | GET | Lista las tareas concretas de una semana |
| `/api/v1/checklists/tasks/{id}` | PATCH | Cambia el estado de una tarea de la semana (`PENDING`, `COMPLETE`, `FAILED`) |

Coleccion de Postman lista para importar: [doc/ulm-core.postman_collection.json](./doc/ulm-core.postman_collection.json).

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
   Las tablas se crean automaticamente al iniciar (`Base.metadata.create_all`); si Postgres no esta corriendo, la app arranca igual pero los endpoints de `dummy` fallaran.
5. Abrir la documentacion interactiva en `http://127.0.0.1:8000/docs`

## Correr pruebas

```
pytest -v
```

## Estilo de desarrollo

Ver [STYLEGUIDE.md](./STYLEGUIDE.md).
