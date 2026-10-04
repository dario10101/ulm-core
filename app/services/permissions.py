"""Catalogo de permisos y quien es admin.

Dos niveles por dominio: el base (`finances`) habilita registros, analytics y
parametros del dominio; el avanzado (`finances.ai`) habilita el analisis con
IA y exige el base. Un dominio sin implementar puede tener permisos asignados
desde ya: simplemente ningun router los pide todavia.

El admin NO es un permiso guardado en la base: sale de ADMIN_EMAILS (ver
config.py). Asi nadie puede volverse admin desde la API, la UI ni un script con
acceso a la base: hace falta cambiar la configuracion del servidor. El admin
tiene todos los permisos, calculados, asi que un dominio nuevo no requiere
asignarselo.

"Todos los permisos" es acceso a todos los *modulos* para sus propios datos:
no lo deja ver datos de otros usuarios (eso lo siguen impidiendo los
repositories, que filtran por user_id).
"""

from collections.abc import Iterable
from enum import Enum

from app.core.config import settings

AI_SUFFIX = ".ai"


class Permission(str, Enum):
    WEIGHT = "weight"
    WEIGHT_AI = "weight.ai"
    MEALS = "meals"
    MEALS_AI = "meals.ai"
    FINANCES = "finances"
    FINANCES_AI = "finances.ai"
    # Checklist y calendario son un solo dominio: comparten categorias y el
    # calendario sincroniza tareas al checklist.
    PLANNING = "planning"
    PLANNING_AI = "planning.ai"

    @property
    def base(self) -> "Permission | None":
        """El permiso base que exige este, o None si este ya es base."""
        if not self.value.endswith(AI_SUFFIX):
            return None
        return Permission(self.value.removesuffix(AI_SUFFIX))


ALL_PERMISSIONS: frozenset[Permission] = frozenset(Permission)


def admin_emails() -> frozenset[str]:
    """ADMIN_EMAILS (separados por coma), normalizados como users.email."""
    return frozenset(
        email.strip().lower() for email in settings.admin_emails.split(",") if email.strip()
    )


def is_admin_email(email: str) -> bool:
    return email.strip().lower() in admin_emails()


def known_permissions(values: Iterable[str]) -> set[Permission]:
    """Los valores que son permisos del catalogo. Uno guardado que ya no
    existe (un dominio que se quito) se ignora en vez de romper el login."""
    known = {permission.value for permission in Permission}
    return {Permission(value) for value in values if value in known}
