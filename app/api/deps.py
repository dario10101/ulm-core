"""Dependencias compartidas de FastAPI: arman la cadena Session -> Repository -> Service.

Las rutas solo declaran una dependencia del Service; nunca instancian ni
importan un repository directamente.

Aca viven tambien las dependencias de identidad (quien es el usuario y en que
zona horaria vive): las rutas las piden por Depends en vez de leer settings,
asi el dia que exista login solo cambia este archivo.
"""

from zoneinfo import ZoneInfo

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.user import User
from app.db.session import get_db
from app.repositories.category_repository import CategoryRepository
from app.repositories.cld_event_repository import CldEventRepository
from app.repositories.cld_task_repository import CldTaskRepository
from app.repositories.cld_user_event_repository import CldUserEventRepository
from app.repositories.expense_repository import ExpenseRepository
from app.repositories.finance_catalog_repository import FinanceCatalogRepository
from app.repositories.meal_repository import MealRepository
from app.repositories.sqlalchemy_category_repository import SqlAlchemyCategoryRepository
from app.repositories.sqlalchemy_cld_event_repository import SqlAlchemyCldEventRepository
from app.repositories.sqlalchemy_cld_task_repository import SqlAlchemyCldTaskRepository
from app.repositories.sqlalchemy_cld_user_event_repository import (
    SqlAlchemyCldUserEventRepository,
)
from app.repositories.sqlalchemy_expense_repository import SqlAlchemyExpenseRepository
from app.repositories.sqlalchemy_finance_catalog_repository import (
    SqlAlchemyFinanceCatalogRepository,
)
from app.repositories.sqlalchemy_meal_repository import SqlAlchemyMealRepository
from app.repositories.sqlalchemy_task_repository import SqlAlchemyTaskRepository
from app.repositories.sqlalchemy_template_task_repository import (
    SqlAlchemyTemplateTaskRepository,
)
from app.repositories.sqlalchemy_week_category_day_score_repository import (
    SqlAlchemyWeekCategoryDayScoreRepository,
)
from app.repositories.sqlalchemy_week_repository import SqlAlchemyWeekRepository
from app.repositories.sqlalchemy_weight_repository import SqlAlchemyWeightRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.template_task_repository import TemplateTaskRepository
from app.repositories.week_category_day_score_repository import WeekCategoryDayScoreRepository
from app.repositories.week_repository import WeekRepository
from app.repositories.weight_repository import WeightRepository
from app.services.calendar_event_service import CalendarEventService
from app.services.category_service import CategoryService
from app.services.checklist_analytics_service import ChecklistAnalyticsService
from app.services.checklist_task_service import ChecklistTaskService
from app.services.cld_task_service import CldTaskService
from app.services.expense_service import ExpenseService
from app.services.finance_catalog_service import FinanceCatalogService
from app.services.meal_service import MealService
from app.services.template_task_service import TemplateTaskService
from app.services.week_service import WeekService
from app.services.weight_service import WeightService


def get_current_user_id() -> int:
    """Usuario quemado: todavia no hay auth. Cuando exista login, este es el
    unico lugar que cambia."""
    return settings.default_user_id


def get_current_timezone(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ZoneInfo:
    """Zona IANA del usuario. Todo calculo de calendario (dia, dia de semana,
    dia del mes) se hace convirtiendo a esta zona; la BD guarda UTC."""
    user = db.get(User, user_id)
    return ZoneInfo(user.timezone if user is not None else settings.default_user_timezone)


def get_weight_repository(db: Session = Depends(get_db)) -> WeightRepository:
    return SqlAlchemyWeightRepository(db)


def get_weight_service(
    repository: WeightRepository = Depends(get_weight_repository),
) -> WeightService:
    return WeightService(repository)


def get_meal_repository(db: Session = Depends(get_db)) -> MealRepository:
    return SqlAlchemyMealRepository(db)


def get_meal_service(
    repository: MealRepository = Depends(get_meal_repository),
) -> MealService:
    return MealService(repository)


def get_finance_catalog_repository(db: Session = Depends(get_db)) -> FinanceCatalogRepository:
    return SqlAlchemyFinanceCatalogRepository(db)


def get_finance_catalog_service(
    repository: FinanceCatalogRepository = Depends(get_finance_catalog_repository),
) -> FinanceCatalogService:
    return FinanceCatalogService(repository)


def get_expense_repository(db: Session = Depends(get_db)) -> ExpenseRepository:
    return SqlAlchemyExpenseRepository(db)


def get_expense_service(
    expense_repository: ExpenseRepository = Depends(get_expense_repository),
    catalog_repository: FinanceCatalogRepository = Depends(get_finance_catalog_repository),
) -> ExpenseService:
    return ExpenseService(expense_repository, catalog_repository)


def get_category_repository(db: Session = Depends(get_db)) -> CategoryRepository:
    return SqlAlchemyCategoryRepository(db)


def get_category_service(
    repository: CategoryRepository = Depends(get_category_repository),
) -> CategoryService:
    return CategoryService(repository)


def get_template_task_repository(db: Session = Depends(get_db)) -> TemplateTaskRepository:
    return SqlAlchemyTemplateTaskRepository(db)


def get_template_task_service(
    repository: TemplateTaskRepository = Depends(get_template_task_repository),
) -> TemplateTaskService:
    return TemplateTaskService(repository)


def get_week_repository(db: Session = Depends(get_db)) -> WeekRepository:
    return SqlAlchemyWeekRepository(db)


def get_task_repository(db: Session = Depends(get_db)) -> TaskRepository:
    return SqlAlchemyTaskRepository(db)


def get_cld_task_repository(db: Session = Depends(get_db)) -> CldTaskRepository:
    return SqlAlchemyCldTaskRepository(db)


def get_week_category_day_score_repository(
    db: Session = Depends(get_db),
) -> WeekCategoryDayScoreRepository:
    return SqlAlchemyWeekCategoryDayScoreRepository(db)


def get_week_service(
    week_repository: WeekRepository = Depends(get_week_repository),
    task_repository: TaskRepository = Depends(get_task_repository),
    template_task_repository: TemplateTaskRepository = Depends(get_template_task_repository),
    cld_task_repository: CldTaskRepository = Depends(get_cld_task_repository),
    score_repository: WeekCategoryDayScoreRepository = Depends(
        get_week_category_day_score_repository
    ),
    category_repository: CategoryRepository = Depends(get_category_repository),
) -> WeekService:
    return WeekService(
        week_repository,
        task_repository,
        template_task_repository,
        cld_task_repository,
        score_repository,
        category_repository,
    )


def get_checklist_analytics_service(
    week_repository: WeekRepository = Depends(get_week_repository),
    score_repository: WeekCategoryDayScoreRepository = Depends(
        get_week_category_day_score_repository
    ),
    category_repository: CategoryRepository = Depends(get_category_repository),
) -> ChecklistAnalyticsService:
    return ChecklistAnalyticsService(week_repository, score_repository, category_repository)


def get_checklist_task_service(
    task_repository: TaskRepository = Depends(get_task_repository),
    week_repository: WeekRepository = Depends(get_week_repository),
    category_repository: CategoryRepository = Depends(get_category_repository),
) -> ChecklistTaskService:
    return ChecklistTaskService(task_repository, week_repository, category_repository)


def get_cld_task_service(
    cld_task_repository: CldTaskRepository = Depends(get_cld_task_repository),
    category_repository: CategoryRepository = Depends(get_category_repository),
    week_repository: WeekRepository = Depends(get_week_repository),
    task_repository: TaskRepository = Depends(get_task_repository),
) -> CldTaskService:
    return CldTaskService(
        cld_task_repository, category_repository, week_repository, task_repository
    )


def get_cld_event_repository(db: Session = Depends(get_db)) -> CldEventRepository:
    return SqlAlchemyCldEventRepository(db)


def get_cld_user_event_repository(db: Session = Depends(get_db)) -> CldUserEventRepository:
    return SqlAlchemyCldUserEventRepository(db)


def get_calendar_event_service(
    cld_event_repository: CldEventRepository = Depends(get_cld_event_repository),
    cld_user_event_repository: CldUserEventRepository = Depends(get_cld_user_event_repository),
) -> CalendarEventService:
    return CalendarEventService(cld_event_repository, cld_user_event_repository)
