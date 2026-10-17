"""Ids generados por la app (ULID) para las entidades del blog.

ULID: 48 bits de milisegundos + 80 bits aleatorios, en base32 de Crockford
(26 caracteres). A diferencia de una secuencia de Postgres, se genera sin la
base (DynamoDB no tiene autoincremento) y, como empieza por el tiempo, ordenar
por id es ordenar por creacion. Sin dependencia externa: son pocas lineas.
"""

import os
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    value = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")
    chars = []
    for _ in range(26):
        value, index = divmod(value, 32)
        chars.append(_CROCKFORD[index])
    return "".join(reversed(chars))
