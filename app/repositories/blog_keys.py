"""Claves de blg_entities: el unico lugar que conoce su formato.

Particion (`pk`): `USER#<user_id>`, todo el blog de un usuario.

| Entidad    | sk                              | gsi1pk / gsi1sk                                  |
|------------|---------------------------------|--------------------------------------------------|
| Config     | `BLOG`                          | -                                                |
| Seccion    | `SEC#<section_id>`              | `USER#<uid>#SECSLUG` / `<slug>`                  |
| Subseccion | `GRP#<section_id>#<group_id>`   | -                                                |
| Elemento   | `ITM#<section_id>#<item_id>`    | `USER#<uid>#SEC#<section_id>#ITMSLUG` / `<slug>` |
| Cuerpo     | `BODY#<item_id>`                | -                                                |

Las secciones singleton (home, about, professional) usan el tipo como id
(`SEC#home`): la clave primaria garantiza que no haya dos del mismo usuario.
Los demas ids son ULID (app/core/ids.py). Ver PLAN-BLOG.md, seccion 7.
"""

BLOG = "BLOG"
SECTION_PREFIX = "SEC#"


def partition(user_id: int) -> str:
    return f"USER#{user_id}"


def section(section_id: str) -> str:
    return f"{SECTION_PREFIX}{section_id}"


def section_id_of(sk: str) -> str:
    return sk.removeprefix(SECTION_PREFIX)


def group_prefix(section_id: str) -> str:
    return f"GRP#{section_id}#"


def group(section_id: str, group_id: str) -> str:
    return f"{group_prefix(section_id)}{group_id}"


def item_prefix(section_id: str) -> str:
    return f"ITM#{section_id}#"


def item(section_id: str, item_id: str) -> str:
    return f"{item_prefix(section_id)}{item_id}"


def last_part(sk: str) -> str:
    """El id de la entidad: ultimo tramo del sk (subseccion, elemento, cuerpo)."""
    return sk.rsplit("#", 1)[-1]


def body(item_id: str) -> str:
    return f"BODY#{item_id}"


def section_slug_index(user_id: int) -> str:
    return f"USER#{user_id}#SECSLUG"


def item_slug_index(user_id: int, section_id: str) -> str:
    return f"USER#{user_id}#SEC#{section_id}#ITMSLUG"
