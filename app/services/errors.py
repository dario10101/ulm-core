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
