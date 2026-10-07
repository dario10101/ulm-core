"""Carga puntual de ingresos REALES de 2026 (ene-ago) para ruben.d21pc@gmail.com,
pasados a mano por el usuario el 2026-10-04:

- Salario Alejandria (directos): un registro BASE por mes (SALARIO BASE) y los
  extras separados segun su comentario. Fecha = ultimo dia del mes.
  Abril (bono + reintegro) se parte asumiendo que la 1/2 de bono es igual a
  la de mayo (2.950.894); el resto (72.993) es el reintegro (OTRO).
- Intereses Lulo (DEFAULT): solo el neto; saldo inicial cuando lo hay, sin
  saldo final. Aportes/retiros quedan en 0 (columnas NOT NULL).
- Tyba (MI CARRO): conciliacion completa; se verifica que cuadre.

Decisiones confirmadas por el usuario: un registro por fuente+subcategoria+mes,
salario al ultimo dia del mes, extras clasificados por inferencia, renombrar la
subcategoria "DEAFULT" (errata) a "DEFAULT".

Idempotente: un registro identico (fuente, subcategoria, fecha, monto) no se
vuelve a insertar. Uso (desde ulm-core/, venv activo, `alembic upgrade head`):
    python -m scripts.import_incomes_2026
"""

import calendar
from datetime import date
from decimal import Decimal

from sqlalchemy import select

import app.main  # noqa: F401 -- registra todos los modelos
from app.db.models.finance import (
    DirectIncome,
    IncomeSource,
    IncomeSubcategory,
    InterestIncome,
)
from app.db.models.user import User
from app.db.session import SessionLocal

EMAIL = "ruben.d21pc@gmail.com"
YEAR = 2026

# (mes, base, [(subcategoria, monto, nota)], total esperado)
SALARY = [
    (1, "4950617", [("OTRO", "348594", "Intereses cesantías")], "5299211"),
    (2, "4938095", [], "4938095"),
    (3, "4907113", [], "4907113"),
    (
        4,
        "4907113",
        [("BONO", "2950894", "1/2 de bono"), ("OTRO", "72993", "Reintegro")],
        "7931000",
    ),
    (5, "4907113", [("BONO", "2950894", "1/2 de bono")], "7858007"),
    (6, "4907113", [("PRIMA", "2028517", "Prima")], "6935630"),
    (7, "4907113", [], "4907113"),
    (8, "4907113", [], "4907113"),
]

# (mes, saldo inicial | None, neto, nota)
LULO = [
    (1, None, "102654", None),
    (2, None, "128218", "hay intereses bolsillo Long Term 01"),
    (3, "18703830", "98560", None),
    (4, "15725372", "91074", None),
    (5, "19018275", "126119", None),
    (6, "23090395", "136183", None),
    (7, "20905400", "134640", None),
    (8, "19624000", "129710", "Restar 13.000 de ingresos de Long term 02 al retirar"),
]

# (mes, saldo inicial, aportes, retiros, saldo final, neto)
TYBA = [
    (2, "1252048", "100000", "0", "1360082", "8034"),
    (3, "1360082", "100000", "0", "1469492", "9410"),
    (4, "1469492", "100000", "0", "1580023", "10531"),
    (5, "1580023", "100000", "0", "1691940", "11917"),
    (6, "1691940", "100000", "0", "1804701", "12761"),
    (7, "1804701", "100000", "0", "1918819", "14118"),
    (8, "1918819", "100000", "0", "2032425", "13606"),
]


def _validate() -> None:
    """Los datos vienen de una tabla a mano: que cuadren antes de tocar la base."""
    for month, base, extras, total in SALARY:
        got = Decimal(base) + sum(Decimal(amount) for _, amount, _ in extras)
        assert got == Decimal(total), f"Salario mes {month}: {got} != {total}"
    for month, start, deposits, withdrawals, end, net in TYBA:
        expected = Decimal(start) + Decimal(deposits) - Decimal(withdrawals) + Decimal(net)
        assert expected == Decimal(end), f"Tyba mes {month}: {expected} != {end}"


def _last_day(month: int) -> date:
    return date(YEAR, month, calendar.monthrange(YEAR, month)[1])


def main() -> None:
    _validate()
    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.email == EMAIL)).scalar_one()
        sources = {
            s.name: s
            for s in db.execute(select(IncomeSource).where(IncomeSource.user_id == user.id))
            .scalars()
            .all()
        }
        salary, lulo, tyba = (
            sources["Salario Alejandría"],
            sources["Intereses Lulo"],
            sources["Tyba"],
        )

        def subcategory(source: IncomeSource, name: str) -> IncomeSubcategory:
            return db.execute(
                select(IncomeSubcategory).where(
                    IncomeSubcategory.source_id == source.id, IncomeSubcategory.name == name
                )
            ).scalar_one()

        # Errata del catalogo, confirmada por el usuario.
        typo = db.execute(
            select(IncomeSubcategory).where(
                IncomeSubcategory.source_id == lulo.id, IncomeSubcategory.name == "DEAFULT"
            )
        ).scalar_one_or_none()
        if typo is not None:
            typo.name = "DEFAULT"
            db.flush()

        inserted = {"direct": 0, "interest": 0}

        def add(model, kind: str, **fields) -> None:
            exists = db.scalar(
                select(model.id).where(
                    model.user_id == user.id,
                    model.source_id == fields["source_id"],
                    model.subcategory_id == fields["subcategory_id"],
                    model.recorded_on == fields["recorded_on"],
                    model.amount == fields["amount"],
                )
            )
            if exists is None:
                db.add(model(user_id=user.id, **fields))
                inserted[kind] += 1

        base_sub = subcategory(salary, "SALARIO BASE")
        for month, base, extras, _total in SALARY:
            recorded_on = _last_day(month)
            add(
                DirectIncome,
                "direct",
                source_id=salary.id,
                subcategory_id=base_sub.id,
                amount=Decimal(base),
                recorded_on=recorded_on,
                note=None,
            )
            for name, amount, note in extras:
                add(
                    DirectIncome,
                    "direct",
                    source_id=salary.id,
                    subcategory_id=subcategory(salary, name).id,
                    amount=Decimal(amount),
                    recorded_on=recorded_on,
                    note=note,
                )

        lulo_sub = subcategory(lulo, "DEFAULT")
        for month, start, net, note in LULO:
            add(
                InterestIncome,
                "interest",
                source_id=lulo.id,
                subcategory_id=lulo_sub.id,
                amount=Decimal(net),
                recorded_on=date(YEAR, month, 1),
                start_of_month_amount=Decimal(start) if start else None,
                end_of_month_amount=None,
                deposits_amount=Decimal(0),
                withdrawals_amount=Decimal(0),
                note=note,
            )

        car_sub = subcategory(tyba, "MI CARRO")
        for month, start, deposits, withdrawals, end, net in TYBA:
            add(
                InterestIncome,
                "interest",
                source_id=tyba.id,
                subcategory_id=car_sub.id,
                amount=Decimal(net),
                recorded_on=date(YEAR, month, 1),
                start_of_month_amount=Decimal(start),
                end_of_month_amount=Decimal(end),
                deposits_amount=Decimal(deposits),
                withdrawals_amount=Decimal(withdrawals),
                note=None,
            )

        db.commit()
        print(
            f"Insertados {inserted['direct']} ingresos directos y "
            f"{inserted['interest']} de intereses para {EMAIL}."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
