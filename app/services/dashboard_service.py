"""Dashboard ("Quick access"): vista Today y vista Weekly pulse.

Endpoint de agregacion: no tiene datos propios ni SQL propio, solo combina los
services de cada dominio. Cada seccion se calcula solo si el usuario tiene el
permiso de ese dominio (el router no exige ninguno: ver app/main.py).

El pulso compara una semana sabado-viernes (la del checklist) contra la
anterior y contra el promedio de las 4 anteriores. Ver
ulm-doc/plans/PLAN-DASHBOARD.md.
"""

from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.repositories.income_summary_repository import IncomeSummaryFilters
from app.schemas.calendar_event import MarkerSource
from app.schemas.dashboard import (
    DashboardPulseRead,
    DashboardTodayRead,
    PulseCategoryDeviation,
    PulseComparison,
    PulseEnglishRead,
    PulseFinancesRead,
    PulsePlanningRead,
    PulseWeekRead,
    PulseWeightRead,
    TodayEnglishRead,
    TodayWeightRead,
)
from app.schemas.finance import ExpenseSummaryGroupBy, IncomeSummaryGroupBy
from app.services.calendar_event_service import CalendarEventService
from app.services.checklist_analytics_service import ChecklistAnalyticsService
from app.services.english_practice_service import EnglishPracticeService
from app.services.errors import PulseWeekInFutureError
from app.services.expense_service import ExpenseService
from app.services.income_summary_service import IncomeSummaryService
from app.services.permissions import Permission
from app.services.weight_service import WeightService

WEEK_DAYS = 7
# ISO: 6 = sabado. La semana del checklist va de sabado a viernes.
WEEK_START_ISO_DAY = 6
# Semanas anteriores para el promedio (la primera es la "anterior").
HISTORY_WEEKS = 4


def week_start_for(day: date) -> date:
    """Sabado en o antes de `day`."""
    return day - timedelta(days=(day.isoweekday() - WEEK_START_ISO_DAY) % WEEK_DAYS)


class DashboardService:
    def __init__(
        self,
        *,
        calendar_events: CalendarEventService,
        checklist_analytics: ChecklistAnalyticsService,
        expenses: ExpenseService,
        incomes: IncomeSummaryService,
        weights: WeightService,
        english: EnglishPracticeService,
        clock: Callable[[], datetime],
    ) -> None:
        self._calendar_events = calendar_events
        self._checklist_analytics = checklist_analytics
        self._expenses = expenses
        self._incomes = incomes
        self._weights = weights
        self._english = english
        # "Ahora" en UTC (deps.get_clock): los tests fijan el dia.
        self._clock = clock

    def today_for(self, tz: ZoneInfo) -> date:
        return self._clock().astimezone(tz).date()

    # --- Today ---

    def today(
        self, user_id: int, tz: ZoneInfo, permissions: frozenset[Permission]
    ) -> DashboardTodayRead:
        today = self.today_for(tz)

        # Festivos y fechas especiales son globales: se muestran a todos. Los
        # eventos personales son del dominio planning.
        events = [
            event
            for event in self._calendar_events.list_ranges(user_id, today, today)
            if event.source == MarkerSource.EVENT or Permission.PLANNING in permissions
        ]

        weight = None
        if Permission.WEIGHT in permissions:
            latest, _, _ = self._weights.list_weights(
                user_id=user_id, start_date=None, end_date=None, page=1, page_size=1
            )
            weight = TodayWeightRead(
                last_recorded_on=latest[0].recorded_on if latest else None,
                last_kg=float(latest[0].weight_kg) if latest else None,
            )

        english = None
        if Permission.ENGLISH in permissions:
            english = TodayEnglishRead(last_practice_at=self._english.last_practice_at(user_id))

        return DashboardTodayRead(date=today, events=events, weight=weight, english=english)

    # --- Weekly pulse ---

    def pulse(
        self,
        user_id: int,
        tz: ZoneInfo,
        permissions: frozenset[Permission],
        week_start: date | None = None,
    ) -> DashboardPulseRead:
        today = self.today_for(tz)
        current_start = week_start_for(today)
        first_day = week_start_for(week_start) if week_start is not None else current_start
        if first_day > current_start:
            raise PulseWeekInFutureError()

        # Indice 0 = la semana pedida; 1..HISTORY_WEEKS = las anteriores.
        weeks = [
            (start, start + timedelta(days=WEEK_DAYS - 1))
            for start in (first_day - timedelta(weeks=i) for i in range(HISTORY_WEEKS + 1))
        ]
        in_progress = first_day == current_start
        week = PulseWeekRead(
            first_day=first_day,
            last_day=weeks[0][1],
            in_progress=in_progress,
            elapsed_days=(today - first_day).days + 1 if in_progress else WEEK_DAYS,
            total_days=WEEK_DAYS,
        )

        return DashboardPulseRead(
            week=week,
            planning=(
                self._pulse_planning(user_id, weeks) if Permission.PLANNING in permissions else None
            ),
            finances=(
                self._pulse_finances(user_id, weeks, today)
                if Permission.FINANCES in permissions
                else None
            ),
            weight=self._pulse_weight(user_id, weeks) if Permission.WEIGHT in permissions else None,
            english=(
                self._pulse_english(user_id, weeks, tz)
                if Permission.ENGLISH in permissions
                else None
            ),
        )

    def _pulse_planning(self, user_id: int, weeks: list[tuple[date, date]]) -> PulsePlanningRead:
        by_day = self._checklist_analytics.points_by_day(user_id, weeks[-1][0], weeks[0][1])

        def pct(start: date, end: date) -> float | None:
            days = [points for day, points in by_day.items() if start <= day <= end]
            possible = sum(p for _, p in days)
            if not possible:
                return None
            return round(100 * sum(s for s, _ in days) / possible, 1)

        return PulsePlanningRead(score_pct=_compare([pct(*w) for w in weeks]))

    def _pulse_finances(
        self, user_id: int, weeks: list[tuple[date, date]], today: date
    ) -> PulseFinancesRead:
        per_week = [
            self._expenses.summarize_expenses(
                user_id=user_id,
                group_by=ExpenseSummaryGroupBy.CATEGORY,
                start_date=start,
                end_date=end,
            )
            for start, end in weeks
        ]

        # Categoria que mas subio: gasto de la semana menos su promedio en las
        # 4 anteriores (una semana sin gasto en la categoria cuenta como 0).
        history: dict[str, float] = defaultdict(float)
        for summary in per_week[1:]:
            for bucket in summary.buckets:
                history[bucket.key] += bucket.total
        deviations = [
            PulseCategoryDeviation(
                label=bucket.label,
                current=bucket.total,
                average=round(history[bucket.key] / HISTORY_WEEKS, 2),
            )
            for bucket in per_week[0].buckets
        ]
        rising = [d for d in deviations if d.current > d.average]
        top = max(rising, key=lambda d: d.current - d.average, default=None)

        month_last = min(weeks[0][1], today)
        month_first = month_last.replace(day=1)
        income = self._incomes.summarize(
            user_id=user_id,
            group_by=IncomeSummaryGroupBy.MONTH,
            stack_by=None,
            filters=IncomeSummaryFilters(start_date=month_first, end_date=month_last),
        ).total
        expenses = self._expenses.summarize_expenses(
            user_id=user_id,
            group_by=ExpenseSummaryGroupBy.MONTH,
            start_date=month_first,
            end_date=month_last,
        ).total

        return PulseFinancesRead(
            spent=_compare([summary.total for summary in per_week]),
            top_deviation=top,
            month_first_day=month_first,
            month_last_day=month_last,
            month_income=income,
            month_expenses=expenses,
            savings_rate_pct=round(100 * (income - expenses) / income, 1) if income > 0 else None,
        )

    def _pulse_weight(self, user_id: int, weeks: list[tuple[date, date]]) -> PulseWeightRead:
        buckets = self._weights.summarize_weights(
            user_id=user_id, group_by="day", start_date=weeks[-1][0], end_date=weeks[0][1]
        ).buckets

        def average(start: date, end: date) -> float | None:
            days = [b for b in buckets if start <= date.fromisoformat(b.key) <= end]
            count = sum(b.count for b in days)
            if not count:
                return None
            return round(sum(b.average_kg * b.count for b in days) / count, 2)

        return PulseWeightRead(average_kg=_compare([average(*w) for w in weeks]))

    def _pulse_english(
        self, user_id: int, weeks: list[tuple[date, date]], tz: ZoneInfo
    ) -> PulseEnglishRead:
        # Los limites de cada semana son medianoche en la zona del usuario.
        start = datetime.combine(weeks[-1][0], time.min, tz)
        end = datetime.combine(weeks[0][1] + timedelta(days=1), time.min, tz)
        local_days = [
            moment.astimezone(tz).date()
            for moment in self._english.practice_times(user_id, start, end)
        ]
        counts = [float(sum(1 for d in local_days if s <= d <= e)) for s, e in weeks]
        return PulseEnglishRead(sessions=_compare(counts))


def _compare(values: list[float | None]) -> PulseComparison:
    """values[0] = semana pedida, values[1:] = las anteriores (mas reciente primero).

    El promedio ignora las semanas sin datos (None). En gasto y sesiones de
    English no hay None: cero es un dato real (no gaste, no practique)."""
    history = [v for v in values[1:] if v is not None]
    average = round(sum(history) / len(history), 2) if history else None
    return PulseComparison(current=values[0], previous=values[1], average=average)
