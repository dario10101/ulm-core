"""Interfaz (Protocol) del acceso a datos de cl_week_category_day_score."""

from collections.abc import Sequence
from typing import Protocol

from app.db.models.checklist import ChecklistWeekCategoryDayScore


class WeekCategoryDayScoreRepository(Protocol):
    def add(self, row: ChecklistWeekCategoryDayScore) -> None: ...

    def list_by_week_ids(
        self, week_ids: Sequence[int]
    ) -> Sequence[ChecklistWeekCategoryDayScore]: ...
