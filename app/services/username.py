"""Reglas del username: formato, normalizacion y nombres reservados.

El username es publico (va en la URL del blog, /blog/<username>) y a futuro
sera el usuario del login con contraseña. Por eso las reglas son estrictas:

- Solo ASCII en minusculas, digitos y guiones: nada de letras de otros
  alfabetos que se ven iguales a una latina (homoglifos, "аdmin" con "а"
  cirilica), que permitirian suplantar a otro usuario en la URL.
- Se normaliza a minusculas antes de validar y guardar: "Ruben" y "ruben" son
  el mismo username (el indice unico uq_users_username es sobre lower()).
- Reservados: rutas propias de la app, o que lo seran, no pueden quedar
  tomadas por un usuario.
"""

import re

from app.services.errors import InvalidUsernameError

MIN_LENGTH = 3
MAX_LENGTH = 30

# Bloques de letras/digitos separados por un guion: sin guion al principio,
# al final ni dos seguidos.
_USERNAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

RESERVED_USERNAMES = frozenset(
    {
        "about",
        "account",
        "admin",
        "administrator",
        "api",
        "app",
        "assets",
        "auth",
        "blog",
        "blogs",
        "dashboard",
        "explore",
        "help",
        "login",
        "logout",
        "me",
        "new",
        "null",
        "projects",
        "public",
        "register",
        "root",
        "search",
        "settings",
        "signup",
        "static",
        "support",
        "system",
        "ulm",
        "undefined",
        "user",
        "users",
        "writing",
        "www",
    }
)


def normalize_username(value: str) -> str:
    """Minusculas y sin espacios alrededor: la forma en que se guarda y busca."""
    return value.strip().lower()


def validate_username(value: str) -> str:
    """El username normalizado, o InvalidUsernameError con el motivo."""
    username = normalize_username(value)
    if not MIN_LENGTH <= len(username) <= MAX_LENGTH:
        raise InvalidUsernameError(
            f"El username debe tener entre {MIN_LENGTH} y {MAX_LENGTH} caracteres"
        )
    if not _USERNAME_RE.match(username):
        raise InvalidUsernameError(
            "Solo letras minusculas, numeros y guiones (sin guion al inicio, "
            "al final ni dos seguidos)"
        )
    if username in RESERVED_USERNAMES:
        raise InvalidUsernameError(f"'{username}' esta reservado")
    return username
