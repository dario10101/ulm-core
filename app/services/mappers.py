"""Traduccion de entidades ORM a esquemas de salida.

Antes esto vivia en la capa de ruta, que para hacerlo tenia que importar los
modelos ORM (`ChecklistTask`, `CldTask`...). Eso anulaba el beneficio de tener
los repositories detras de un `Protocol`: cambiar de persistencia habria
obligado a tocar tambien las rutas.

Ahora los services devuelven esquemas y la ruta no sabe que existe SQLAlchemy.
"""

from zoneinfo import ZoneInfo

from app.db.models.checklist import (
    ChecklistCategory,
    ChecklistTask,
    ChecklistTemplateTask,
    ChecklistWeek,
)
from app.db.models.cld_task import CldTask
from app.db.models.finance import Expense
from app.db.models.meal import Meal
from app.db.models.weight import WeightRecord
from app.schemas.checklist import (
    POINTS_BY_IMPORTANCE,
    CategoryRead,
    Importance,
    TaskRead,
    TaskStatus,
    TemplateTaskRead,
    WeekRead,
)
from app.schemas.cld_task import CldTaskOccurrenceRead, CldTaskRead, RepeatMode
from app.schemas.finance import CategoryRead as FinanceCategoryRead
from app.schemas.finance import ExpenseRead, PaymentMethodRead, TagRead
from app.schemas.meal import MealRead, MealType
from app.schemas.weight import WeightRead
from app.services.cld_task_sync import Occurrence, to_local
from app.services.day_utils import parse_days


def category_to_read(category: ChecklistCategory) -> CategoryRead:
    return CategoryRead.model_validate(category, from_attributes=True)


def week_to_read(week: ChecklistWeek) -> WeekRead:
    return WeekRead.model_validate(week, from_attributes=True)


def template_task_to_read(task: ChecklistTemplateTask) -> TemplateTaskRead:
    importance = Importance(task.importance)
    return TemplateTaskRead(
        id=task.id,
        name=task.name,
        importance=importance,
        points=POINTS_BY_IMPORTANCE[importance],
        category_id=task.category_id,
        days=sorted(parse_days(task.day_of_week)),
        detail=task.detail,
    )


def checklist_task_to_read(task: ChecklistTask) -> TaskRead:
    importance = Importance(task.importance)
    return TaskRead(
        id=task.id,
        name=task.name,
        importance=importance,
        points=POINTS_BY_IMPORTANCE[importance],
        category_id=task.category_id,
        day_of_week=int(task.day_of_week),
        status=TaskStatus(task.status),
        last_modified_date=task.last_modified_date,
        detail=task.detail,
    )


def cld_task_to_read(task: CldTask, tz: ZoneInfo) -> CldTaskRead:
    """Los anclajes salen en hora de pared del usuario, igual que entran: la
    BD guarda UTC, pero el contrato de la API es simetrico (el formulario de
    edicion del front parte de estos valores)."""
    return CldTaskRead(
        id=task.id,
        name=task.name,
        importance=Importance(task.importance),
        category_id=task.category_id,
        notify=task.notify,
        repeat_mode=RepeatMode(task.repeat_mode) if task.repeat_mode else None,
        scheduled_date=to_local(task.scheduled_date, tz) if task.scheduled_date else None,
        repeat_date=to_local(task.repeat_date, tz) if task.repeat_date else None,
        duration_minutes=task.duration_minutes,
        add_to_checklist=task.add_to_checklist,
        detail=task.detail,
        last_modified_date=task.last_modified_date,
    )


def cld_task_occurrence_to_read(
    task: CldTask, occurrence: Occurrence, tz: ZoneInfo
) -> CldTaskOccurrenceRead:
    return CldTaskOccurrenceRead(
        id=task.id,
        name=task.name,
        importance=Importance(task.importance),
        category_id=task.category_id,
        notify=task.notify,
        repeat_mode=RepeatMode(task.repeat_mode) if task.repeat_mode else None,
        scheduled_date=to_local(task.scheduled_date, tz) if task.scheduled_date else None,
        repeat_date=to_local(task.repeat_date, tz) if task.repeat_date else None,
        duration_minutes=task.duration_minutes,
        add_to_checklist=task.add_to_checklist,
        detail=task.detail,
        occurrence_at=occurrence.at_utc,
        occurrence_local=occurrence.local,
    )


def weight_to_read(record: WeightRecord) -> WeightRead:
    return WeightRead.model_validate(record, from_attributes=True)


def expense_to_read(expense: Expense) -> ExpenseRead:
    """`category`/`payment_method`/`tags` ya vienen resueltos (relationship
    con lazy="joined"/"selectin", ver app/db/models/finance.py), asi que
    "View records" no tiene que cruzar los catalogos por id."""
    return ExpenseRead(
        id=expense.id,
        user_id=expense.user_id,
        name=expense.name,
        amount=float(expense.amount),
        recorded_on=expense.recorded_on,
        note=expense.note,
        category=FinanceCategoryRead.model_validate(expense.category),
        payment_method=PaymentMethodRead.model_validate(expense.payment_method),
        tags=[TagRead.model_validate(tag) for tag in expense.tags],
        created_at=expense.created_at,
        updated_at=expense.updated_at,
    )


def meal_to_read(meal: Meal, tz: ZoneInfo) -> MealRead:
    """`recorded_on` sale en hora de pared del usuario, igual que entra (ver
    cld_task_to_read para el mismo contrato)."""
    return MealRead(
        id=meal.id,
        user_id=meal.user_id,
        recorded_on=to_local(meal.recorded_on, tz),
        meal_type=MealType(meal.meal_type),
        meal_size=meal.meal_size,
        meal_content=meal.meal_content,
        drink=meal.drink,
        note=meal.note,
        created_at=meal.created_at,
        updated_at=meal.updated_at,
    )
