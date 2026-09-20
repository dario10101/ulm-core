"""Seed puntual (correr una sola vez) para poblar historia de checklists y
poder validar el grafico de analytics end-to-end:

1. Backfill de cl_week_category_day_score para la semana ya cerrada que
   exista hoy, calculado desde sus cl_tasks reales (no es data inventada).
2. Semanas sintéticas cerradas desde el 1 de enero del anio de esa semana
   hasta el dia justo antes de que empiece (encadenadas, sin overlap).
   Incluye:
   - Un hueco real (una semana sin fila en cl_week: "no se le hizo tracking").
   - La categoria "Hobbies" solo tiene datos en las primeras semanas del
     anio y despues se deja de usar; al final del script se deshabilita
     (status=DISABLED) para validar que su historia sigue apareciendo en
     el grafico aunque la categoria ya no exista para nuevo trabajo.

Uso: python -m scripts.seed_checklist_history (desde ulm-core/, con el venv
activado y Postgres corriendo). No es idempotente: correrlo dos veces choca
con la unique constraint de cl_week_category_day_score y con fechas de semana
superpuestas.
"""

import random
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from app.db.models.checklist import ChecklistCategory, ChecklistTask, ChecklistWeek, ChecklistWeekCategoryDayScore
from app.db.models import user as user_model  # noqa: F401 -- registra 'users' para resolver el FK de cl_week
from app.db.session import SessionLocal
from app.schemas.checklist import POINTS_BY_IMPORTANCE, Importance, TaskStatus

random.seed(42)

# category_id -> (min, max) puntaje semanal target para esa categoria.
CATEGORY_WEEKLY_RANGES = {
    4: (32, 55),  # Health: tiene template grande, score alto todas las semanas (ver semana real)
    5: (0, 5),  # Work: un solo template task, score bajo
    6: (4, 16),  # Personal: sin template, tareas puntuales agregadas a mano
    7: (4, 16),  # Study: idem
    8: (5, 18),  # Hobbies: idem, pero solo primeras semanas (ver HOBBIES_WEEK_LIMIT)
}
HOBBIES_CATEGORY_ID = 8
HOBBIES_WEEK_LIMIT = 8  # cuantas semanas desde el 1/1 tienen datos de Hobbies
GAP_WEEK_INDEX = 15  # semana (0-indexed) que se salta por completo: "no se trackeo"


def distribute(total: int, parts: int) -> list[int]:
    """Reparte `total` en `parts` enteros no negativos (que suman `total`),
    al azar (particion tipo "stars and bars")."""
    if parts <= 0:
        return []
    if parts == 1:
        return [total]
    cuts = sorted(random.randint(0, total) for _ in range(parts - 1))
    boundaries = [0, *cuts, total]
    return [boundaries[i + 1] - boundaries[i] for i in range(parts)]


def day_of_week_for_offset(first_day: date, offset: int) -> int:
    """ISO weekday (1=Lunes...7=Domingo) del dia `offset` (0-indexed) despues
    de first_day, dentro de esa semana."""
    return ((first_day.isoweekday() - 1 + offset) % 7) + 1


def build_synthetic_week_rows(first_day: date, last_day: date, active_categories: list[int]) -> tuple[int, list[ChecklistWeekCategoryDayScore]]:
    span_days = (last_day - first_day).days + 1
    rows: list[ChecklistWeekCategoryDayScore] = []
    week_total = 0
    for category_id in active_categories:
        lo, hi = CATEGORY_WEEKLY_RANGES[category_id]
        weekly_target = random.randint(lo, hi)
        per_day = distribute(weekly_target, span_days)
        for offset, day_score in enumerate(per_day):
            if day_score == 0 and random.random() < 0.5:
                continue  # sparsity: no todos los dias tienen fila para toda categoria
            points_possible = day_score + random.randint(0, 3)
            rows.append(
                ChecklistWeekCategoryDayScore(
                    category_id=category_id,
                    day_of_week=day_of_week_for_offset(first_day, offset),
                    score=day_score,
                    points_possible=points_possible,
                )
            )
            week_total += day_score
    return week_total, rows


def backfill_existing_closed_week(session, week: ChecklistWeek) -> None:
    """Calcula cl_week_category_day_score para una semana YA cerrada antes de
    que existiera esta tabla, desde sus cl_tasks reales."""
    tasks = session.execute(
        select(ChecklistTask).where(ChecklistTask.cl_week_id == week.id)
    ).scalars().all()

    totals: dict[tuple[int, int], dict[str, int]] = defaultdict(lambda: {"score": 0, "points_possible": 0})
    for task in tasks:
        points = POINTS_BY_IMPORTANCE[Importance(task.importance)]
        key = (task.category_id, int(task.day_of_week))
        totals[key]["points_possible"] += points
        if task.status == TaskStatus.COMPLETE.value:
            totals[key]["score"] += points

    for (category_id, day_of_week), totals_for_key in totals.items():
        session.add(
            ChecklistWeekCategoryDayScore(
                cl_week_id=week.id,
                category_id=category_id,
                day_of_week=day_of_week,
                score=totals_for_key["score"],
                points_possible=totals_for_key["points_possible"],
            )
        )
    print(f"Backfill semana real {week.id} ({week.first_day} - {week.last_day}): {len(totals)} filas")


def main() -> None:
    session = SessionLocal()
    try:
        user_id = 1
        earliest_closed = session.execute(
            select(ChecklistWeek)
            .where(ChecklistWeek.user_id == user_id, ChecklistWeek.closed.is_(True))
            .order_by(ChecklistWeek.first_day)
            .limit(1)
        ).scalar_one_or_none()
        if earliest_closed is None:
            raise SystemExit("No hay ninguna semana cerrada todavia; nada que anclar al backfill.")

        backfill_existing_closed_week(session, earliest_closed)

        year_start = date(earliest_closed.first_day.year, 1, 1)
        boundary = earliest_closed.first_day  # las semanas sinteticas terminan justo antes de esto

        # Encadena semanas de 7 dias (la ultima se recorta para no pisar `boundary`).
        week_ranges: list[tuple[date, date]] = []
        cursor = year_start
        while cursor < boundary:
            last_day = min(cursor + timedelta(days=6), boundary - timedelta(days=1))
            week_ranges.append((cursor, last_day))
            cursor = last_day + timedelta(days=1)

        created = 0
        for index, (first_day, last_day) in enumerate(week_ranges):
            if index == GAP_WEEK_INDEX:
                print(f"Semana {index} ({first_day} - {last_day}): sin tracking, no se crea fila")
                continue

            active_categories = [4, 5, 6, 7]
            if index < HOBBIES_WEEK_LIMIT:
                active_categories.append(HOBBIES_CATEGORY_ID)

            week_total, score_rows = build_synthetic_week_rows(first_day, last_day, active_categories)

            week = ChecklistWeek(
                user_id=user_id,
                first_day=first_day,
                last_day=last_day,
                closed=True,
                closed_date=None,
                score=week_total,
            )
            session.add(week)
            session.flush()  # necesito week.id para las filas de score

            for row in score_rows:
                row.cl_week_id = week.id
                session.add(row)
            created += 1

        session.commit()
        print(f"Semanas sinteticas creadas: {created} (de {len(week_ranges)} generadas, 1 hueco)")

        hobbies = session.get(ChecklistCategory, HOBBIES_CATEGORY_ID)
        if hobbies is not None:
            hobbies.status = "DISABLED"
            session.commit()
            print(f"Categoria '{hobbies.name}' (id={hobbies.id}) marcada DISABLED")
    finally:
        session.close()


if __name__ == "__main__":
    main()
