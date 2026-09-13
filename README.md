# ULM Core (Backend)

Backend de **Unified Life Manager (ULM)**, una aplicacion personal de gestion diaria: habitos, finanzas y publicacion de contenido.

## Funcionalidad

Este repositorio expone la API REST que consume `ulm-web`. Estado actual: esqueleto funcional con endpoints dummy.

| Endpoint | Metodo | Descripcion |
|---|---|---|
| `/` | GET | Mensaje de bienvenida / smoke test |
| `/api/v1/health` | GET | Estado del servicio |
| `/api/v1/habits/` | GET | Lista dummy de habitos (datos en memoria) |

## Stack tecnico

- **Lenguaje**: Python 3.12
- **Framework**: FastAPI
- **Servidor ASGI**: Uvicorn
- **Validacion/config**: Pydantic v2 + pydantic-settings
- **Testing**: Pytest + FastAPI TestClient
- **Base de datos objetivo**: PostgreSQL (aun no integrada)

## Estructura

```
app/
  api/routes/   # Endpoints agrupados por dominio
  core/         # Configuracion y utilidades transversales
  models/       # Modelos Pydantic
  main.py       # Punto de entrada de la app FastAPI
tests/          # Pruebas unitarias (pytest)
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
3. Levantar el servidor de desarrollo:
   ```
   uvicorn app.main:app --reload
   ```
4. Abrir la documentacion interactiva en `http://127.0.0.1:8000/docs`

## Correr pruebas

```
pytest -v
```

## Estilo de desarrollo

Ver [STYLEGUIDE.md](./STYLEGUIDE.md).
