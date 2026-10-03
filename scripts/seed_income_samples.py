"""Datos de prueba de ingresos para visualizar "View records -> Income".

Inserta, para el usuario quemado (id 1):
- Subcategorias extra, exclusivas de una fuente (SEED_SUBCATEGORIES), para
  ver en el formulario que cada fuente ofrece las suyas.
- Ingresos directos de enero a septiembre de 2026: salario quincenal
  (SALARIO BASE), algunos EXTRA y BONO, y ventas ocasionales.
- Intereses mensuales de enero a julio de 2026 para cada fuente INTEREST,
  con saldos encadenados (el final de un mes es el inicial del siguiente).
  Agosto queda libre a proposito: es el periodo por defecto del formulario
  y asi se puede probar "Use July balance" sin chocar con un registro existente.

Todas las filas llevan una nota que empieza con SEED_MARK: el script borra
esas filas antes de insertar (se puede correr varias veces) y con --delete
solo las borra, junto con las subcategorias de SEED_SUBCATEGORIES que ya no
use ningun ingreso.

Uso (desde ulm-core/, con el venv activado y Postgres corriendo, despues de
`alembic upgrade head`, que siembra las fuentes y subcategorias):
    python -m scripts.seed_income_samples
    python -m scripts.seed_income_samples --delete
"""

import random
import sys
from datetime import date
from decimal import Decimal

from sqlalchemy import select

import app.main  # noqa: F401 -- registra todos los modelos (FK a users, tags)
from app.db.models.finance import (
    DirectIncome,
    IncomeSource,
    IncomeSubcategory,
    InterestIncome,
    Tag,
)
from app.db.session import SessionLocal

SEED_MARK = "[seed]"
USER_ID = 1
YEAR = 2026

# fuente -> subcategorias que crea el script (get-or-create).
SEED_SUBCATEGORIES = {
    "Salario": ["BONO"],
    "Venta ocasional": ["ARTICULO USADO"],
}

random.seed(7)


def _by_name(rows) -> dict:
    return {row.name: row for row in rows}


def _delete_seeded(db) -> None:
    for model in (DirectIncome, InterestIncome):
        # delete() masivo no pasa por el ORM: las filas de las tablas de tags
        # se borran a mano con los registros (no hay ON DELETE CASCADE).
        records = (
            db.execute(
                select(model).where(model.user_id == USER_ID, model.note.startswith(SEED_MARK))
            )
            .scalars()
            .all()
        )
        for record in records:
            db.delete(record)
    db.flush()

    sources = _by_name(_user_sources(db))
    for source_name, names in SEED_SUBCATEGORIES.items():
        source = sources.get(source_name)
        if source is None:
            continue
        for subcategory in db.execute(
            select(IncomeSubcategory).where(
                IncomeSubcategory.source_id == source.id, IncomeSubcategory.name.in_(names)
            )
        ).scalars():
            in_use = any(
                db.scalar(select(model.id).where(model.subcategory_id == subcategory.id).limit(1))
                for model in (DirectIncome, InterestIncome)
            )
            if not in_use:
                db.delete(subcategory)
    db.flush()


def _user_sources(db):
    return db.execute(select(IncomeSource).where(IncomeSource.user_id == USER_ID)).scalars()


def _subcategories_by_source(db, sources: dict) -> dict[str, dict[str, IncomeSubcategory]]:
    """{nombre de fuente: {nombre de subcategoria: fila}}, creando las de
    SEED_SUBCATEGORIES que falten."""
    for source_name, names in SEED_SUBCATEGORIES.items():
        source = sources[source_name]
        existing = set(
            db.execute(
                select(IncomeSubcategory.name).where(IncomeSubcategory.source_id == source.id)
            ).scalars()
        )
        for name in names:
            if name not in existing:
                db.add(
                    IncomeSubcategory(
                        user_id=USER_ID, source_id=source.id, type=source.type, name=name
                    )
                )
    db.flush()

    by_source: dict[str, dict[str, IncomeSubcategory]] = {}
    for source_name, source in sources.items():
        by_source[source_name] = _by_name(
            db.execute(
                select(IncomeSubcategory).where(IncomeSubcategory.source_id == source.id)
            ).scalars()
        )
    return by_source


def _insert_direct(db, sources: dict, subcategories: dict, tags: dict) -> int:
    salary, sale = sources["Salario"], sources["Venta ocasional"]
    base = subcategories["Salario"]["SALARIO BASE"]
    extra = subcategories["Salario"]["EXTRA"]
    bonus = subcategories["Salario"]["BONO"]
    sale_extra = subcategories["Venta ocasional"]["EXTRA"]
    used_item = subcategories["Venta ocasional"]["ARTICULO USADO"]
    recurring = [tags[name] for name in ("RECURRING", "PLANNED") if name in tags]

    rows = []
    for month in range(1, 10):
        for day in (15, 28):
            rows.append(
                DirectIncome(
                    user_id=USER_ID,
                    source_id=salary.id,
                    subcategory_id=base.id,
                    amount=Decimal("2750000.00"),
                    recorded_on=date(YEAR, month, day),
                    note=f"{SEED_MARK} Quincena",
                    tags=recurring,
                )
            )
        if month in (3, 6, 9):
            rows.append(
                DirectIncome(
                    user_id=USER_ID,
                    source_id=salary.id,
                    subcategory_id=extra.id,
                    amount=Decimal(random.randrange(300_000, 900_000, 50_000)),
                    recorded_on=date(YEAR, month, 28),
                    note=f"{SEED_MARK} Horas extra",
                )
            )
    rows.append(
        DirectIncome(
            user_id=USER_ID,
            source_id=salary.id,
            subcategory_id=bonus.id,
            amount=Decimal("1500000.00"),
            recorded_on=date(YEAR, 6, 30),
            note=f"{SEED_MARK} Prima de mitad de anio",
        )
    )
    sales = [
        (used_item, "450000.50", date(YEAR, 5, 10), "Venta de bicicleta usada"),
        (used_item, "180000.00", date(YEAR, 8, 3), "Venta de monitor viejo"),
        (sale_extra, "95000.00", date(YEAR, 9, 12), "Reventa de boletas"),
    ]
    for subcategory, amount, recorded_on, note in sales:
        rows.append(
            DirectIncome(
                user_id=USER_ID,
                source_id=sale.id,
                subcategory_id=subcategory.id,
                amount=Decimal(amount),
                recorded_on=recorded_on,
                note=f"{SEED_MARK} {note}",
            )
        )
    db.add_all(rows)
    return len(rows)


def _insert_interest(db, sources: dict, subcategories: dict) -> int:
    # (fuente, saldo inicial de enero, tasa mensual aproximada)
    plans = [("Tyba", Decimal("2500000"), 0.009), ("Cuenta de ahorros", Decimal("1000000"), 0.006)]

    count = 0
    for source_name, start, rate in plans:
        source = sources[source_name]
        yield_sub = subcategories[source_name]["RENDIMIENTOS"]
        balance = start
        for month in range(1, 8):
            deposits = Decimal(random.choice([0, 0, 100_000, 200_000]))
            withdrawals = Decimal(random.choice([0, 0, 0, 150_000]))
            # Algun mes negativo en Tyba (fondo de inversion), para ver el color.
            monthly_rate = -0.004 if source_name == "Tyba" and month == 4 else rate
            interest = (balance * Decimal(str(monthly_rate))).quantize(Decimal("0.01"))
            end = balance + deposits - withdrawals + interest
            db.add(
                InterestIncome(
                    user_id=USER_ID,
                    source_id=source.id,
                    subcategory_id=yield_sub.id,
                    amount=interest,
                    recorded_on=date(YEAR, month, 1),
                    start_of_month_amount=balance,
                    end_of_month_amount=end,
                    deposits_amount=deposits,
                    withdrawals_amount=withdrawals,
                    note=f"{SEED_MARK} Rendimientos",
                )
            )
            balance = end
            count += 1
    return count


def main() -> None:
    only_delete = "--delete" in sys.argv[1:]
    db = SessionLocal()
    try:
        _delete_seeded(db)
        if only_delete:
            db.commit()
            print("Registros de prueba de ingresos eliminados.")
            return

        sources = _by_name(_user_sources(db))
        subcategories = _subcategories_by_source(db, sources)
        tags = _by_name(db.execute(select(Tag).where(Tag.user_id == USER_ID)).scalars())

        direct_count = _insert_direct(db, sources, subcategories, tags)
        interest_count = _insert_interest(db, sources, subcategories)
        db.commit()
        print(f"Insertados {direct_count} ingresos directos y {interest_count} de intereses.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
