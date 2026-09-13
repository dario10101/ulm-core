# Guia de estilo - ULM Core

## Idioma

- Codigo (variables, funciones, clases, archivos, carpetas): **ingles**.
- Comentarios, docstrings, logs y mensajes de commit: **espanol**.

## Estructura y nombres

- Carpetas en `snake_case` (ej. `api/routes`).
- Archivos Python en `snake_case.py`.
- Clases en `PascalCase`, funciones/variables en `snake_case`.
- Un router por dominio funcional dentro de `app/api/routes/`.

## Convenciones de codigo

- Tipar siempre los parametros y retornos de funciones publicas.
- Usar modelos Pydantic para toda entrada/salida de la API (no dicts sueltos en la firma).
- Configuracion centralizada en `app/core/config.py`, nunca hardcodear valores de entorno.
- Un archivo de test por modulo (`tests/test_<modulo>.py`).

## Comentarios y logs

- Comentar el "por que", no el "que" (el codigo ya dice que hace).
- Logs y mensajes de error orientados al usuario o al desarrollador en espanol.

## Commits

- Mensajes cortos, en espanol, en modo imperativo: `agrega endpoint de habitos`, `corrige validacion de fecha`.

## Pruebas

- Toda funcionalidad nueva debe incluir al menos una prueba unitaria en `tests/`.
- Ejecutar `pytest` antes de cada commit.
