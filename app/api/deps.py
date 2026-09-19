"""Dependencias compartidas de FastAPI: arman la cadena Session -> Repository -> Service.

Las rutas solo declaran una dependencia del Service; nunca instancian ni
importan un repository directamente.
"""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.category_repository import CategoryRepository
from app.repositories.sqlalchemy_category_repository import SqlAlchemyCategoryRepository
from app.repositories.sqlalchemy_task_repository import SqlAlchemyTaskRepository
from app.repositories.sqlalchemy_template_task_repository import (
    SqlAlchemyTemplateTaskRepository,
)
from app.repositories.sqlalchemy_week_repository import SqlAlchemyWeekRepository
from app.repositories.sqlalchemy_weight_repository import SqlAlchemyWeightRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.template_task_repository import TemplateTaskRepository
from app.repositories.week_repository import WeekRepository
from app.repositories.weight_repository import WeightRepository
from app.services.category_service import CategoryService
from app.services.checklist_task_service import ChecklistTaskService
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


def get_week_service(
    week_repository: WeekRepository = Depends(get_week_repository),
    task_repository: TaskRepository = Depends(get_task_repository),
    template_task_repository: TemplateTaskRepository = Depends(get_template_task_repository),
) -> WeekService:
    return WeekService(week_repository, task_repository, template_task_repository)


def get_checklist_task_service(
    task_repository: TaskRepository = Depends(get_task_repository),
    week_repository: WeekRepository = Depends(get_week_repository),
) -> ChecklistTaskService:
    return ChecklistTaskService(task_repository, week_repository)
