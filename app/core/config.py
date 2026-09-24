"""Configuracion central de la aplicacion."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # Nombre del proyecto, expuesto en el endpoint de salud
    app_name: str = "ULM Core"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    # DEBUG, INFO, WARNING, ERROR. Ver app/core/logging.py.
    log_level: str = "INFO"

    # Postgres local via Docker, ver ulm-repository/postgres-local-setup.md
    database_url: str = "postgresql+psycopg2://ulm_user:ulm_password@localhost:5432/ulm_db"

    # Origenes permitidos para CORS (frontend Vite en desarrollo)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Usuario "quemado": todavia no hay auth, todo registro se asocia a este usuario
    default_user_id: int = 1
    default_user_name: str = "Ruben"
    default_user_email: str = "ruben@example.com"
    # Zona horaria IANA del usuario quemado. Se guarda el nombre de la zona
    # (no un offset fijo como -5): el offset correcto depende de la fecha en
    # zonas con horario de verano, y una zona IANA lo resuelve por fecha.
    default_user_timezone: str = "America/Bogota"


settings = Settings()
