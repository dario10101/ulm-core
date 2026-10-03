"""Verifica que los nombres de la base coincidan con los que declaran los modelos.

`alembic check` compara estructura (columnas, tipos, que exista una FK entre
tal y tal columna) pero no nombres: una PK que se llama `pk_cl_categories` en
una tabla que ya se llama `cl_user_categories` pasa sin aviso. Ese drift es
invisible hasta que una migracion intenta borrar el constraint por el nombre
que dice el modelo y en la base no existe.

Compara, por tabla: PK, FK, UNIQUE, indices y la secuencia del `id`.

Uso (con la base ya migrada, `alembic upgrade head`):
    python -m scripts.check_db_names
Sale con codigo 1 si encuentra diferencias. Corre en CI despues del upgrade.
"""

import sys

from sqlalchemy import UniqueConstraint, inspect, text

import app.main  # noqa: F401 -- registra todos los modelos en Base.metadata
from app.db.base_class import Base
from app.db.session import engine


def _expected(table) -> dict[str, set[str]]:
    names = {
        "pk": {table.primary_key.name},
        "fk": {fk.name for fk in table.foreign_key_constraints},
        "uq": {c.name for c in table.constraints if isinstance(c, UniqueConstraint)},
        "ix": {i.name for i in table.indexes},
        "seq": set(),
    }
    id_column = table.columns.get("id")
    if id_column is not None and id_column.primary_key and id_column.autoincrement is not False:
        names["seq"] = {f"{table.name}_id_seq"}
    return names


def _actual(inspector, conn, table_name: str) -> dict[str, set[str]]:
    # Secuencias que pertenecen a la tabla (OWNED BY). No se asume una columna
    # `id`: fn_expenses_tags, por ejemplo, tiene PK compuesta y ninguna.
    sequences = conn.execute(
        text(
            "SELECT s.relname FROM pg_class s "
            "JOIN pg_depend d ON d.objid = s.oid "
            "JOIN pg_class t ON d.refobjid = t.oid "
            "WHERE s.relkind = 'S' AND t.relname = :t"
        ),
        {"t": table_name},
    ).scalars()
    return {
        "pk": {inspector.get_pk_constraint(table_name)["name"]},
        "fk": {fk["name"] for fk in inspector.get_foreign_keys(table_name)},
        "uq": {uq["name"] for uq in inspector.get_unique_constraints(table_name)},
        # Postgres reporta los UNIQUE tambien como indices: se descartan aca
        # porque ya se comparan como "uq".
        "ix": {
            ix["name"]
            for ix in inspector.get_indexes(table_name)
            if not ix.get("duplicates_constraint")
        },
        "seq": set(sequences),
    }


def main() -> int:
    problems: list[str] = []
    with engine.connect() as conn:
        inspector = inspect(conn)
        db_tables = set(inspector.get_table_names()) - {"alembic_version"}
        model_tables = set(Base.metadata.tables)

        for name in sorted(model_tables - db_tables):
            problems.append(f"{name}: tabla declarada en los modelos pero ausente en la base")
        for name in sorted(db_tables - model_tables):
            problems.append(f"{name}: tabla en la base sin modelo")

        for name in sorted(model_tables & db_tables):
            expected = _expected(Base.metadata.tables[name])
            actual = _actual(inspector, conn, name)
            for kind in expected:
                missing = expected[kind] - actual[kind]
                extra = actual[kind] - expected[kind]
                if missing or extra:
                    problems.append(
                        f"{name} [{kind}]: esperado {sorted(missing)}, en la base {sorted(extra)}"
                    )

    if problems:
        print("Nombres fuera de sincronia entre modelos y base:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"OK: {len(model_tables)} tablas con nombres consistentes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
