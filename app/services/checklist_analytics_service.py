"""Agregaciones de checklist para analytics (tendencias semanales/mensuales
de semanas cerradas). Solo lee cl_week + cl_week_category_day_score, nunca
escribe (eso lo hace WeekService.close_week, una unica vez por semana)."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from app.repositories.category_repository import CategoryRepository
from app.repositories.week_category_day_score_repository import WeekCategoryDayScoreRepository
from app.repositories.week_repository import WeekRepository
from app.services.day_utils import resolve_date_for_day

# Por encima de este numero de categorias con datos en el rango consultado,
# las de menor puntaje total se agrupan en un bucket "Others" — el resto se
# muestra por su nombre real. Ver conversacion de diseño: la decision de
# cuantas/cuales se agrupan la toma el backend (ya esta agregando los datos),
# el front solo pinta lo que recibe.
MAX_NAMED_CATEGORIES = 7
OTHERS_LABEL = "Others"


@dataclass
class CategoryPlan:
    """Que categorias se muestran con su propio nombre y cuales se pliegan
    en "Others", mas el orden final de las series del grafico."""

    # (category_id, name) en el orden final de presentacion. category_id=None
    # es el bucket "Others" (solo presente si hubo que agrupar).
    order: list[tuple[int | None, str]] = field(default_factory=list)
    others_ids: set[int] = field(default_factory=set)


class ChecklistAnalyticsService:
    def __init__(
        self,
        week_repository: WeekRepository,
        score_repository: WeekCategoryDayScoreRepository,
        category_repository: CategoryRepository,
    ) -> None:
        self._week_repository = week_repository
        self._score_repository = score_repository
        self._category_repository = category_repository

    def get_weekly(self, user_id: int, year: int) -> tuple[list[tuple[int | None, str]], list[dict]]:
        weeks = self._week_repository.list_closed_by_year(user_id, year)
        rows = self._score_repository.list_by_week_ids([week.id for week in weeks])

        per_week_category: dict[tuple[int, int], int] = defaultdict(int)
        category_totals: dict[int, int] = defaultdict(int)
        for row in rows:
            per_week_category[(row.cl_week_id, row.category_id)] += row.score
            category_totals[row.category_id] += row.score

        plan = self._build_category_plan(user_id, category_totals)

        points = [
            {
                "week_id": week.id,
                "first_day": week.first_day,
                "last_day": week.last_day,
                "total_score": week.score or 0,
                "scores": self._project(plan, {cid: per_week_category.get((week.id, cid), 0) for cid in category_totals}),
            }
            for week in weeks
        ]
        return plan.order, points

    def get_monthly(self, user_id: int, year: int) -> tuple[list[tuple[int | None, str]], list[dict]]:
        weeks = self._week_repository.list_closed_overlapping_year(user_id, year)
        rows = self._score_repository.list_by_week_ids([week.id for week in weeks])
        weeks_by_id = {week.id: week for week in weeks}
        year_start, year_end = date(year, 1, 1), date(year, 12, 31)

        # Una semana que cruza fin de mes (o fin de anio) se desagrega dia a
        # dia: cada dia va al mes/anio calendario que realmente le corresponde.
        per_month_category: dict[tuple[int, int], int] = defaultdict(int)
        month_totals: dict[int, int] = defaultdict(int)
        category_totals: dict[int, int] = defaultdict(int)
        for row in rows:
            week = weeks_by_id[row.cl_week_id]
            actual_date = resolve_date_for_day(week.first_day, row.day_of_week)
            if not (year_start <= actual_date <= year_end):
                continue  # cae en el anio vecino, no corresponde a esta consulta
            month = actual_date.month
            per_month_category[(month, row.category_id)] += row.score
            month_totals[month] += row.score
            category_totals[row.category_id] += row.score

        plan = self._build_category_plan(user_id, category_totals)

        points = [
            {
                "month": month,
                "total_score": month_totals.get(month, 0),
                "scores": self._project(plan, {cid: per_month_category.get((month, cid), 0) for cid in category_totals}),
            }
            for month in range(1, 13)
        ]
        return plan.order, points

    def _build_category_plan(self, user_id: int, category_totals: dict[int, int]) -> CategoryPlan:
        if not category_totals:
            return CategoryPlan()

        categories = {
            category.id: category
            for category in self._category_repository.list_by_ids(user_id, list(category_totals))
        }

        # Ranking solo para decidir quien entra a "Others" — el orden de
        # presentacion final es por prioridad de categoria, no por puntaje,
        # para que el color asignado no cambie segun quien va ganando.
        ranked = sorted(category_totals.items(), key=lambda kv: kv[1], reverse=True)
        if len(ranked) <= MAX_NAMED_CATEGORIES + 1:
            named_ids = {category_id for category_id, _ in ranked}
            others_ids: set[int] = set()
        else:
            named_ids = {category_id for category_id, _ in ranked[:MAX_NAMED_CATEGORIES]}
            others_ids = {category_id for category_id, _ in ranked[MAX_NAMED_CATEGORIES:]}

        def display_name(category_id: int) -> str:
            category = categories.get(category_id)
            return category.name if category is not None else f"Category {category_id}"

        def sort_key(category_id: int) -> tuple[int, int]:
            category = categories.get(category_id)
            priority = category.priority if category is not None else 0
            return (priority, category_id)

        order: list[tuple[int | None, str]] = [
            (category_id, display_name(category_id)) for category_id in sorted(named_ids, key=sort_key)
        ]
        if others_ids:
            order.append((None, OTHERS_LABEL))

        return CategoryPlan(order=order, others_ids=others_ids)

    @staticmethod
    def _project(plan: CategoryPlan, raw_by_category: dict[int, int]) -> list[int]:
        """Reordena/agrupa un dict {category_id: valor} segun el CategoryPlan,
        devolviendo la lista alineada 1:1 con `plan.order`."""
        scores: list[int] = []
        for category_id, _name in plan.order:
            if category_id is None:
                scores.append(sum(raw_by_category.get(cid, 0) for cid in plan.others_ids))
            else:
                scores.append(raw_by_category.get(category_id, 0))
        return scores
