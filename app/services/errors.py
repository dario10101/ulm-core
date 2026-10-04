"""Errores de dominio compartidos por los services.

Antes cada service definia su propia `CategoryNotFoundError`, lo que obligaba a
importarlas con alias en las rutas (`CategoryNotFoundError as
UnknownCategoryIdsError`) y hacia imposible capturarlas juntas.

Todos heredan de `DomainError`, asi que una ruta puede capturar el caso
concreto o la familia entera. Ninguno conoce codigos HTTP: la traduccion a
respuesta vive en la capa de ruta.
"""


class DomainError(Exception):
    """Raiz de los errores de negocio. No incluye fallos tecnicos."""


class NotFoundError(DomainError):
    """Lo referenciado no existe, o no pertenece al usuario.

    La ambiguedad es deliberada: responder distinto en cada caso le confirmaria
    a un usuario la existencia de recursos ajenos.
    """


class ConflictError(DomainError):
    """La operacion choca con el estado actual (se traduce a 409)."""


class ValidationError(DomainError):
    """La entrada es coherente en forma pero invalida en el dominio (422)."""


# --- Categorias ---


class CategoryNotFoundError(NotFoundError):
    """Una o mas categorias referenciadas no existen (o no son del usuario).

    Lleva el conjunto de ids para que la ruta pueda detallarlos: algunos
    endpoints reciben una sola categoria y otros una lista.
    """

    def __init__(self, category_ids: set[int] | int) -> None:
        self.category_ids = {category_ids} if isinstance(category_ids, int) else category_ids
        super().__init__(f"Categorias inexistentes: {sorted(self.category_ids)}")

    @property
    def category_id(self) -> int:
        """Atajo para los casos de una sola categoria."""
        return next(iter(self.category_ids))


class CategoryInUseError(ConflictError):
    """Se intento eliminar una categoria que todavia tiene tareas de template."""

    def __init__(self, category_names: list[str]) -> None:
        self.category_names = category_names
        super().__init__(f"Categorias en uso: {', '.join(category_names)}")


class DuplicateCategoryNameError(ValidationError):
    """El mismo guardado trae dos categorias con el mismo nombre (sin
    distinguir mayusculas)."""

    def __init__(self, names: list[str]) -> None:
        self.names = names
        super().__init__(f"Nombres repetidos: {', '.join(names)}")


class CategoryNameTakenError(ConflictError):
    """El nombre ya lo usa una categoria DISABLED del usuario (o una que este
    mismo guardado deshabilita). Los nombres son unicos contando las
    deshabilitadas, para que analytics no parta una misma categoria en dos."""

    def __init__(self, names: list[str]) -> None:
        self.names = names
        super().__init__(f"Nombres usados por categorias deshabilitadas: {', '.join(names)}")


# --- Semanas de checklist ---


class WeekNotFoundError(NotFoundError):
    """La semana solicitada no existe (o no es del usuario)."""


class WeekAlreadyOpenError(ConflictError):
    """Ya existe una semana sin cerrar; hay que cerrarla antes de crear otra."""


class WeekAlreadyClosedError(ConflictError):
    """La semana ya fue cerrada, no se puede cerrar de nuevo."""


class WeekClosedError(ConflictError):
    """La semana ya esta cerrada: sus tareas no se pueden modificar."""


class WeekHasPendingTasksError(ConflictError):
    """La semana todavia tiene tareas sin marcar (PENDING); no se puede cerrar."""

    def __init__(self, pending_count: int) -> None:
        self.pending_count = pending_count
        super().__init__(f"Quedan {pending_count} tarea(s) en PENDING")


class InvalidWeekRangeError(ValidationError):
    """El rango elegido cubre menos de 1 o mas de 7 dias."""


class WeekEndInThePastError(ValidationError):
    """last_day no puede ser anterior a hoy."""


class WeekStartTooEarlyError(ValidationError):
    """first_day es anterior al minimo permitido (ver WeekService.get_next_range)."""

    def __init__(self, min_first_day) -> None:  # date, sin importar para no acoplar
        self.min_first_day = min_first_day
        super().__init__(f"El primer dia no puede ser anterior a {min_first_day}")


# --- Tareas ---


class TaskNotFoundError(NotFoundError):
    """La tarea de semana solicitada no existe (o no es del usuario)."""


class TemplateTaskNotFoundError(NotFoundError):
    """La tarea de template (o el dia pedido dentro de ella) no existe."""


class CldTaskNotFoundError(NotFoundError):
    """La tarea de calendario solicitada no existe (o no es del usuario)."""


class InvalidTaskDateError(ValidationError):
    """scheduled_date/repeat_date no corresponde al repeat_mode de la tarea."""


# --- Registros de peso ---


class WeightNotFoundError(NotFoundError):
    """El registro de peso no existe (o no es del usuario)."""


# --- Registros de comida ---


class MealNotFoundError(NotFoundError):
    """El registro de comida no existe (o no es del usuario)."""


# --- Finanzas: gastos ---


class ExpenseNotFoundError(NotFoundError):
    """El registro de gasto no existe (o no es del usuario)."""


class ExpenseCategoryNotFoundError(NotFoundError):
    """La categoria de gasto referenciada no existe (o esta deshabilitada)."""

    def __init__(self, category_id: int) -> None:
        self.category_id = category_id
        super().__init__(f"Categoria de gasto inexistente: {category_id}")


class PaymentMethodNotFoundError(NotFoundError):
    """El metodo de pago referenciado no existe (o esta deshabilitado)."""

    def __init__(self, payment_method_id: int) -> None:
        self.payment_method_id = payment_method_id
        super().__init__(f"Metodo de pago inexistente: {payment_method_id}")


class TagNotFoundError(NotFoundError):
    """Uno o mas tags referenciados no existen (o no son del usuario)."""

    def __init__(self, tag_ids: set[int]) -> None:
        self.tag_ids = tag_ids
        super().__init__(f"Tags inexistentes: {sorted(self.tag_ids)}")


# --- Finanzas: ingresos ---


class IncomeNotFoundError(NotFoundError):
    """El registro de ingreso no existe (o no es del usuario)."""


class IncomeSourceNotFoundError(NotFoundError):
    """La fuente referenciada no existe, no es del usuario o no aplica a ese
    tipo de ingreso (para el cliente es lo mismo: no es una opcion valida)."""

    def __init__(self, source_id: int) -> None:
        self.source_id = source_id
        super().__init__(f"Fuente de ingreso inexistente para este tipo: {source_id}")


class IncomeSubcategoryNotFoundError(NotFoundError):
    """La subcategoria no existe, no es del usuario o no pertenece a la fuente
    elegida."""

    def __init__(self, subcategory_id: int) -> None:
        self.subcategory_id = subcategory_id
        super().__init__(f"Subcategoria inexistente para esa fuente: {subcategory_id}")


class InterestPeriodTakenError(ConflictError):
    """Ya hay un registro de intereses para esa fuente en ese mes."""

    def __init__(self) -> None:
        super().__init__("Ya existe un registro de intereses para esa fuente en ese mes")


# --- Administracion de catalogos (tags, categorias, fuentes...) ---


class CatalogItemNotFoundError(NotFoundError):
    """El item de catalogo a editar/borrar no existe (o no es del usuario)."""

    def __init__(self, label: str, item_id: int) -> None:
        self.label = label
        self.item_id = item_id
        super().__init__(f"{label} inexistente: {item_id}")


class CatalogNameTakenError(ConflictError):
    """Ya hay otro item con ese nombre (sin distinguir mayusculas). Cuenta
    tambien los archivados: restaurar el viejo es mejor que tener dos con el
    mismo nombre partiendo el historico en analytics."""

    def __init__(self, name: str, *, archived: bool) -> None:
        self.name = name
        self.archived = archived
        where = " (archivado: restauralo en vez de crear otro)" if archived else ""
        super().__init__(f"Ya existe '{name}'{where}")


class CatalogItemLockedError(ConflictError):
    """El cambio dejaria registros existentes inconsistentes (ej. pasar a
    DIRECT una fuente con ingresos de intereses)."""


# --- Eventos generales de calendario ---


class CldEventNotFoundError(NotFoundError):
    """El evento general (festivo, fecha especial) no existe."""


class CldUserEventNotFoundError(NotFoundError):
    """El evento personal no existe (o no es del usuario)."""


# --- Usuarios y login ---


class UserNotFoundError(NotFoundError):
    """El usuario no existe."""


class EmailTakenError(ConflictError):
    """Ya hay un usuario con ese email (sin distinguir mayusculas)."""

    def __init__(self, email: str) -> None:
        self.email = email
        super().__init__(f"Ya existe un usuario con el email {email}")


class InvalidUsernameError(ValidationError):
    """El username no cumple el formato o esta reservado (ver
    app/services/username.py). El mensaje dice cual regla fallo."""


class UsernameTakenError(ConflictError):
    """Otro usuario ya tiene ese username (sin distinguir mayusculas)."""

    def __init__(self, username: str) -> None:
        self.username = username
        super().__init__(f"El username '{username}' ya esta en uso")


class UsernameAlreadySetError(ConflictError):
    """El usuario ya tiene username y no se cambia: romperia los links a su
    blog y liberaria el nombre para que otro lo tome (suplantacion)."""

    def __init__(self) -> None:
        super().__init__("Ya tienes un username y no se puede cambiar")


# --- Blog ---


class BlogNotFoundError(NotFoundError):
    """No hay blog publico con ese username: no existe, esta deshabilitado o
    su dueño no tiene el permiso `blog`. Para el visitante es lo mismo."""


class LoginError(DomainError):
    """Raiz de los motivos por los que un login no termina en sesion. Cada
    subclase tiene un `code` que la ruta manda al front (/login?error=code)
    para que muestre el mensaje correspondiente."""

    code = "oauth_failed"


class LoginNotConfiguredError(LoginError):
    """Faltan GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / SESSION_SECRET."""

    code = "not_configured"


class LoginFlowError(LoginError):
    """El flujo OAuth no cierra: state que no coincide, cookie del login
    vencida o ausente, o Google rechazo el code / el id_token."""

    code = "oauth_failed"


class EmailNotVerifiedError(LoginError):
    """Google no garantiza que la cuenta sea dueña de ese email: no se puede
    usar para vincular ni para buscar una invitacion."""

    code = "email_not_verified"


class NotInvitedError(LoginError):
    """Modo invite_only y no hay usuario con ese email."""

    code = "not_invited"


class UserDisabledError(LoginError):
    code = "disabled"


# --- Permisos ---


class UnknownPermissionError(ValidationError):
    """El permiso no existe en el catalogo (app/services/permissions.py)."""

    def __init__(self, value: str) -> None:
        self.value = value
        super().__init__(f"Permiso desconocido: {value}")


class MissingBasePermissionError(ValidationError):
    """Se intento dar un permiso avanzado (`<dominio>.ai`) sin el base."""

    def __init__(self, permission: str, base: str) -> None:
        self.permission = permission
        self.base = base
        super().__init__(f"{permission} exige tener antes {base}")


class AdminRoleNotEditableError(ConflictError):
    """El admin sale de ADMIN_EMAILS: no se le asignan ni quitan permisos, ni
    se lo deshabilita, por API o consola."""
