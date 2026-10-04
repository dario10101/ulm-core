"""Schemas publicos del blog (sin sesion).

Separados de los privados a proposito: lo que sale por aca lo ve cualquiera,
asi que se declara campo por campo. Nunca id, email, nombre de Google ni
avatar: el usuario no autorizo publicarlos.
"""

from pydantic import BaseModel


class PublicBlogRead(BaseModel):
    username: str
