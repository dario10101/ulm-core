"""Configuracion de logging de la aplicacion.

Un solo lugar que define formato y nivel, en vez de `print()` sueltos: un
print no tiene nivel, no lleva timestamp, no dice de que modulo salio y no se
puede silenciar ni redirigir sin tocar el codigo.
"""

import logging
import sys

from app.core.config import settings

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"


def configure_logging() -> None:
    """Se llama una sola vez, al arrancar la app."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format=_FORMAT,
        stream=sys.stdout,
        force=True,  # gana sobre la config que uvicorn deja puesta
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
