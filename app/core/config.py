"""Configuracion central de la aplicacion."""

from typing import Literal

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

    # Origenes permitidos para CORS y para el chequeo de Origin en escrituras
    # (ver app/core/csrf.py). En desarrollo el front habla con la API a traves
    # del proxy de Vite, asi que para el navegador es el mismo origen.
    cors_origins: list[str] = ["http://localhost:5173"]

    # URL publica del frontend: adonde vuelve el usuario despues del login.
    frontend_url: str = "http://localhost:5173"

    # --- Login con Google (OIDC). Ver ulm-core/.env.example ---
    google_client_id: str = ""
    google_client_secret: str = ""
    # Tiene que coincidir exacto con la registrada en Google Cloud Console.
    # Pasa por el proxy de Vite, por eso apunta al puerto del front.
    google_redirect_uri: str = "http://localhost:5173/api/v1/auth/google/callback"

    # Firma la cookie temporal del login (state, nonce, PKCE). No es la sesion.
    session_secret: str = ""
    session_ttl_days: int = 30
    # Secure obliga HTTPS: en produccion siempre True; en local (http) False.
    session_cookie_secure: bool = False

    # invite_only: solo entra quien ya tenga un usuario con su email (lo crea
    # el admin, ver scripts/manage_users.py). open: un login con un email
    # desconocido crea el usuario. Ver AuthService.login_with_google.
    registration_mode: Literal["invite_only", "open"] = "invite_only"

    # Zona horaria si el navegador no manda una valida en el primer login.
    default_timezone: str = "America/Bogota"


settings = Settings()
