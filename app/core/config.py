"""Configuracion central de la aplicacion."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # Nombre del proyecto, expuesto en el endpoint de salud
    app_name: str = "ULM Core"
    environment: str = "development"
    api_prefix: str = "/api/v1"


settings = Settings()
