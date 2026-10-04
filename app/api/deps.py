"""Dependencias compartidas de FastAPI: arman la cadena Session -> Repository -> Service.

Las rutas solo declaran una dependencia del Service; nunca instancian ni
importan un repository directamente.

Aca viven tambien las dependencias de identidad (quien es el usuario y en que
zona horaria vive): las rutas piden `get_current_user_id` por Depends y no
saben de cookies ni sesiones. Los tests reemplazan `get_current_user` (ver
tests/conftest.py, acting_as).
"""

from functools import lru_cache
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.session_cookie import SESSION_COOKIE, set_session_cookie
from app.core.config import settings
from app.db.models.finance import DirectIncome
from app.db.models.user import User
from app.db.session import get_db
from app.integrations.google_oauth import GoogleOAuthClient, HttpGoogleOAuthClient
from app.repositories.category_repository import CategoryRepository
from app.repositories.cld_event_repository import CldEventRepository
from app.repositories.cld_task_repository import CldTaskRepository
from app.repositories.cld_user_event_repository import CldUserEventRepository
from app.repositories.expense_repository import ExpenseRepository
from app.repositories.finance_catalog_repository import FinanceCatalogRepository
from app.repositories.income_repository import IncomeRepository, InterestIncomeRepository
from app.repositories.income_summary_repository import IncomeSummaryRepository
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
from app.repositories.sqlalchemy_income_repository import (
    SqlAlchemyIncomeRepository,
    SqlAlchemyInterestIncomeRepository,
)
from app.repositories.sqlalchemy_income_summary_repository import (
    SqlAlchemyIncomeSummaryRepository,
)
from app.repositories.sqlalchemy_meal_repository import SqlAlchemyMealRepository
from app.repositories.sqlalchemy_task_repository import SqlAlchemyTaskRepository
from app.repositories.sqlalchemy_template_task_repository import (
    SqlAlchemyTemplateTaskRepository,
)
from app.repositories.sqlalchemy_user_permission_repository import (
    SqlAlchemyUserPermissionRepository,
)
from app.repositories.sqlalchemy_user_repository import SqlAlchemyUserRepository
from app.repositories.sqlalchemy_user_session_repository import SqlAlchemyUserSessionRepository
from app.repositories.sqlalchemy_week_category_day_score_repository import (
    SqlAlchemyWeekCategoryDayScoreRepository,
)
from app.repositories.sqlalchemy_week_repository import SqlAlchemyWeekRepository
from app.repositories.sqlalchemy_weight_repository import SqlAlchemyWeightRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.template_task_repository import TemplateTaskRepository
from app.repositories.user_permission_repository import UserPermissionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.repositories.week_category_day_score_repository import WeekCategoryDayScoreRepository
from app.repositories.week_repository import WeekRepository
from app.repositories.weight_repository import WeightRepository
from app.services.auth_service import AuthService
from app.services.calendar_event_service import CalendarEventService
from app.services.category_service import CategoryService
from app.services.checklist_analytics_service import ChecklistAnalyticsService
from app.services.checklist_task_service import ChecklistTaskService
from app.services.cld_task_service import CldTaskService
from app.services.expense_service import ExpenseService
from app.services.finance_catalog_service import FinanceCatalogService
from app.services.income_service import IncomeService
from app.services.income_summary_service import IncomeSummaryService
from app.services.meal_service import MealService
from app.services.permissions import Permission
from app.services.template_task_service import TemplateTaskService
from app.services.user_admin_service import UserAdminService
from app.services.week_service import WeekService
from app.services.weight_service import WeightService

# --- Identidad ---


def get_user_repository(db: Session = Depends(get_db)) -> UserRepository:
    return SqlAlchemyUserRepository(db)


def get_user_session_repository(db: Session = Depends(get_db)) -> UserSessionRepository:
    return SqlAlchemyUserSessionRepository(db)


@lru_cache
def get_google_oauth_client() -> GoogleOAuthClient:
    """Uno solo por proceso: reutiliza las conexiones HTTP a Google."""
    return HttpGoogleOAuthClient(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        redirect_uri=settings.google_redirect_uri,
    )


def get_user_permission_repository(db: Session = Depends(get_db)) -> UserPermissionRepository:
    return SqlAlchemyUserPermissionRepository(db)


def get_user_admin_service(
    users: UserRepository = Depends(get_user_repository),
    sessions: UserSessionRepository = Depends(get_user_session_repository),
    permissions: UserPermissionRepository = Depends(get_user_permission_repository),
) -> UserAdminService:
    return UserAdminService(users, sessions, permissions)


def get_auth_service(
    users: UserRepository = Depends(get_user_repository),
    sessions: UserSessionRepository = Depends(get_user_session_repository),
    user_admin: UserAdminService = Depends(get_user_admin_service),
    google: GoogleOAuthClient = Depends(get_google_oauth_client),
) -> AuthService:
    return AuthService(users, sessions, user_admin, google)


def get_current_user(
    request: Request,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
) -> User:
    """Usuario de la cookie de sesion, o 401. Si la expiracion deslizante se
    renovo, reenvia la cookie para que el navegador tambien la extienda."""
    token = request.cookies.get(SESSION_COOKIE)
    user, renewed = auth.resolve_session(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Sesion no iniciada o vencida")
    if renewed and token is not None:
        set_session_cookie(response, token)
    return user


def get_current_user_id(user: User = Depends(get_current_user)) -> int:
    return user.id


def get_current_permissions(
    user: User = Depends(get_current_user),
    user_admin: UserAdminService = Depends(get_user_admin_service),
) -> frozenset[Permission]:
    """Permisos efectivos del usuario actual. FastAPI cachea una dependencia
    por request, asi que varios `require` en la misma ruta hacen una sola query."""
    return user_admin.effective_permissions(user)


def require(permission: Permission):
    """Dependencia que exige `permission`; se usa a nivel de router (ver
    PRIVATE_ROUTERS en app/main.py). 403 y no 404: a diferencia de un recurso
    ajeno, que el modulo existe no es un secreto (el menu ya lo muestra)."""

    def _require(permissions: frozenset[Permission] = Depends(get_current_permissions)) -> None:
        if permission not in permissions:
            raise HTTPException(status_code=403, detail=f"Necesitas el permiso {permission.value}")

    # Marca para el test fail-closed (tests/test_permissions.py): asi sabe que
    # permiso exige cada ruta sin depender de nombres de funciones.
    _require.required_permission = permission  # type: ignore[attr-defined]
    return _require


def get_current_timezone(user: User = Depends(get_current_user)) -> ZoneInfo:
    """Zona IANA del usuario. Todo calculo de calendario (dia, dia de semana,
    dia del mes) se hace convirtiendo a esta zona; la BD guarda UTC."""
    return ZoneInfo(user.timezone)


# --- Dominios ---


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


def get_direct_income_repository(
    db: Session = Depends(get_db),
) -> IncomeRepository[DirectIncome]:
    return SqlAlchemyIncomeRepository(db, DirectIncome)


def get_interest_income_repository(db: Session = Depends(get_db)) -> InterestIncomeRepository:
    return SqlAlchemyInterestIncomeRepository(db)


def get_income_service(
    direct_repository: IncomeRepository[DirectIncome] = Depends(get_direct_income_repository),
    interest_repository: InterestIncomeRepository = Depends(get_interest_income_repository),
    catalog_repository: FinanceCatalogRepository = Depends(get_finance_catalog_repository),
) -> IncomeService:
    return IncomeService(direct_repository, interest_repository, catalog_repository)


def get_income_summary_repository(db: Session = Depends(get_db)) -> IncomeSummaryRepository:
    return SqlAlchemyIncomeSummaryRepository(db)


def get_income_summary_service(
    repository: IncomeSummaryRepository = Depends(get_income_summary_repository),
) -> IncomeSummaryService:
    return IncomeSummaryService(repository)


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
