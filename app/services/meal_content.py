"""Serializacion del campo `meals.meal_content`.

Se guarda deliberadamente como texto plano en vez de normalizar a una tabla
aparte (ver requerimiento): "NOMBRE:PORCENTAJE;NOMBRE:PORCENTAJE". Este
modulo es el unico lugar que arma ese string, para que el formato (mayusculas,
sin tildes, sin caracteres especiales, espacios colapsados, orden alfabetico)
quede en un solo sitio en vez de repetirse en cada caller.
"""

import re
import unicodedata


def normalize_component_name(raw: str) -> str:
    """Mayusculas, sin tildes/diacriticos, solo letras/numeros/espacios, y
    espacios multiples colapsados a uno solo (incluye trim de bordes)."""
    without_accents = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    upper = without_accents.upper()
    only_word_chars = re.sub(r"[^A-Z0-9 ]", " ", upper)
    return re.sub(r"\s+", " ", only_word_chars).strip()


def serialize_meal_content(components: list[tuple[str, int]]) -> str | None:
    """Arma "NOMBRE:PCT;NOMBRE:PCT", ordenado alfabeticamente por nombre ya
    normalizado. Ignora componentes cuyo nombre quede vacio tras normalizar
    (ej. si el usuario solo escribio caracteres especiales); devuelve None si
    no queda ninguno."""
    normalized = [
        (name, percent)
        for name, percent in (
            (normalize_component_name(raw_name), percent) for raw_name, percent in components
        )
        if name
    ]
    if not normalized:
        return None

    normalized.sort(key=lambda item: item[0])
    return ";".join(f"{name}:{percent}" for name, percent in normalized)
