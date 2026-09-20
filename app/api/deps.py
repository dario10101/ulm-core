"""Dependencias compartidas de FastAPI: arman la cadena Session -> Repository -> Service.

Las rutas solo declaran una dependencia del Service; nunca instancian ni
importan un repository directamente.
"""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.category_repository import CategoryRepository
from app.repositories.cld_event_repository import CldEventRepository
from app.repositories.cld_task_repository import CldTaskRepository
from app.repositories.cld_user_event_repository import CldUserEventRepository
from app.repositories.sqlalchemy_category_repository import SqlAlchemyCategoryRepository
from app.repositories.sqlalchemy_cld_event_repository import SqlAlchemyCldEventRepository
from app.repositories.sqlalchemy_cld_task_repository import SqlAlchemyCldTaskRepository
from app.repositories.sqlalchemy_cld_user_event_repository import (
    SqlAlchemyCldUserEventRepository,
)
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
from app.services.template_task_service import TemplateTaskService
from app.services.week_service import WeekService
from app.services.weight_service import WeightService


def get_weight_repository(db: Session = Depends(get_db)) -> WeightRepository:
    return SqlAlchemyWeightRepository(db)


def get_weight_service(
    repository: WeightRepository = Depends(get_weight_repository),
) -> WeightService:
    return WeightService(repository)


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
    score_repository: WeekCategoryDayScoreRepository = Depends(get_week_category_day_score_repository),
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
    score_repository: WeekCategoryDayScoreRepository = Depends(get_week_category_day_score_repository),
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
    return CldTaskService(cld_task_repository, category_repository, week_repository, task_repository)


def get_cld_event_repository(db: Session = Depends(get_db)) -> CldEventRepository:
    return SqlAlchemyCldEventRepository(db)


def get_cld_user_event_repository(db: Session = Depends(get_db)) -> CldUserEventRepository:
    return SqlAlchemyCldUserEventRepository(db)


def get_calendar_event_service(
    cld_event_repository: CldEventRepository = Depends(get_cld_event_repository),
    cld_user_event_repository: CldUserEventRepository = Depends(get_cld_user_event_repository),
) -> CalendarEventService:
    return CalendarEventService(cld_event_repository, cld_user_event_repository)
