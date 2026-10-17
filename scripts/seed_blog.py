"""Datos de prueba del blog (PLAN-BLOG.md, seccion 14).

Carga, para los usuarios de SEEDS (buscados por username), secciones de todos
los tipos, subsecciones y elementos .md. Todo pasa por BlogAdminService, la
misma logica que usa la API: si un dato de aca es invalido (contenido de una
plantilla, slug, frontmatter, topes), el script falla igual que fallaria un
request. tests/test_seed_blog.py lo corre en CI.

Casos que ejercita: el tope de secciones habilitadas (rubendorado tiene 6
habilitadas y "Libros" deshabilitada), una seccion de plantilla deshabilitada
(el "Sobre mí" de rubendorado2), un label renombrado con el slug por defecto
("Bienvenida" -> /inicio), borradores, elementos con y sin subseccion, e
imagenes por URL en el .md y en las plantillas.

No es una migracion (D20): datos de prueba, solo para desarrollo.

Uso (desde ulm-core/, con el venv activado y la base migrada):
    python -m scripts.seed_blog            # carga; si un usuario ya tiene blog, lo salta
    python -m scripts.seed_blog --reset    # borra el blog de esos usuarios y lo carga de nuevo
    python -m scripts.seed_blog --delete   # solo borra el blog de esos usuarios
"""

import sys
from dataclasses import dataclass, field
from typing import Any

import yaml

import app.main  # noqa: F401 -- registra todos los modelos (FK a users)
from app.db.session import SessionLocal
from app.repositories.blog_entity_repository import BlogEntityRepository
from app.repositories.sqlalchemy_blog_entity_repository import SqlAlchemyBlogEntityRepository
from app.repositories.sqlalchemy_user_repository import SqlAlchemyUserRepository
from app.schemas.blog_admin import GroupCreate, ItemUpdate, SectionCreate
from app.services.blog_admin_service import BlogAdminService


def image(seed: str) -> str:
    """Imagen de ejemplo estable (la misma para el mismo `seed`)."""
    return f"https://picsum.photos/seed/ulm-{seed}/800/400"


def markdown(body: str, **meta: Any) -> str:
    """Un .md con frontmatter. yaml.safe_dump se encarga de las comillas."""
    header = yaml.safe_dump(
        {key: value for key, value in meta.items() if value is not None},
        allow_unicode=True,
        sort_keys=False,
    )
    return f"---\n{header}---\n\n{body.strip()}\n"


@dataclass
class ItemSeed:
    filename: str
    text: str
    group: str | None = None
    published: bool = True


@dataclass
class SectionSeed:
    type: str
    label: str | None = None
    enabled: bool = True
    content: dict[str, Any] = field(default_factory=dict)
    # (label, descripcion) de cada subseccion, en orden.
    groups: list[tuple[str, str | None]] = field(default_factory=list)
    items: list[ItemSeed] = field(default_factory=list)


# --- rubendorado: los textos que antes estaban quemados en el front ---

RUBEN_POSTS = [
    ItemSeed(
        "por-que-un-sistema-operativo-para-mi-vida.md",
        markdown(
            """
Planeo mucho y ejecuto menos de lo que quisiera — un problema conocido para
muchos ingenieros. **Unified Life Manager** nació como respuesta a una pregunta
simple: ¿cómo sería una herramienta construida para hacer que realmente haga las
cosas, no solo que las registre?

![Escritorio de trabajo](https://picsum.photos/seed/ulm-escritorio/800/400)

También es una buena excusa para aprender frontend en serio, ya que la mayor
parte de mi trabajo es backend y pipelines de datos.
""",
            title="Por qué estoy construyendo un sistema operativo para mi vida",
            date="2026-08-02",
            slug="por-que-un-sistema-operativo-para-mi-vida",
            excerpt="Planeo mucho y ejecuto menos de lo que quisiera. Este proyecto es un "
            "intento de arreglar eso con algo que controlo yo mismo.",
            tags=["Proyecto", "Meta"],
            cover_url=image("sistema"),
        ),
    ),
    ItemSeed(
        "notas-funciones-de-ventana-pyspark.md",
        markdown(
            """
Las funciones de ventana son de esas cosas que asustan hasta que dejás de
pensarlas como agregaciones y empezás a pensarlas como *"una fila, más contexto
sobre sus vecinas"*.

```python
from pyspark.sql import Window, functions as F

window = Window.partitionBy("user_id").orderBy("event_at")
df.withColumn("previous", F.lag("amount").over(window))
```

Particionar por la columna equivocada es la forma más común de obtener
resultados incorrectos sin que se note — vale la pena revisarlo siempre.
""",
            title="Notas sobre funciones de ventana en PySpark",
            date="2026-07-18",
            excerpt="Algunos patrones que finalmente hicieron que las funciones de ventana "
            "me cerraran, anotados antes de que se me olviden.",
            tags=["Ingeniería de datos", "PySpark"],
        ),
    ),
    ItemSeed(
        "kickboxing-boton-de-reinicio.md",
        markdown(
            """
La mayor parte de mi día la paso pensando en abstracciones — esquemas,
pipelines, casos borde. El kickboxing obliga a lo contrario: reaccionar a lo que
tenés justo enfrente, ahora.

Se convirtió en una de las formas más confiables que tengo para resetear después
de un mal día de debugging.
""",
            title="El kickboxing como botón de reinicio de un data engineer",
            date="2026-06-30",
            excerpt="Por qué lo que más me ayuda a concentrarme frente al teclado es justo "
            "lo más alejado de uno.",
            tags=["Personal"],
        ),
    ),
]

RUBEN = [
    SectionSeed(
        "home",
        label="Bienvenida",  # renombrado: el slug sigue siendo el base, /inicio
        content={
            "headline": "Data Engineer, siempre construyendo algo por mi cuenta.",
            "intro": "Escribo sobre lo que voy aprendiendo — sobre todo **datos**, "
            "arquitectura de software y lo que construyo para *Unified Life Manager*.",
            "highlights": [
                {
                    "kind": "project",
                    "title": "Unified Life Manager",
                    "description": "Sistema personal para hábitos, finanzas, planeación y salud.",
                    "image_url": image("ulm"),
                },
                {
                    "kind": "product",
                    "title": "Plantillas de checklist semanal",
                    "description": "Rutinas listas para importar en ULM (próximamente).",
                    "image_url": image("plantillas"),
                },
                {
                    "kind": "link",
                    "title": "Notas de PySpark",
                    "description": "Patrones que uso a diario.",
                    "url": "https://example.com/pyspark",
                },
            ],
            "cta": {"label": "Escríbeme", "url": "https://example.com/contacto"},
        },
    ),
    SectionSeed(
        "about",
        content={
            "photo_url": image("perfil"),
            "bio": "Soy Data Engineer, tengo 28 años, trabajo full-time y dedico buena parte "
            "de mi tiempo libre a aprender cosas relacionadas con mi trabajo — y otras que "
            "no, como desarrollo frontend.\n\nFuera del código: gimnasio, kickboxing y "
            "lectura. Prefiero construir cosas chicas y útiles antes que terminar cosas "
            "grandes y pulidas — este sitio incluido.",
            "interests": ["Ingeniería de datos", "Frontend", "Kickboxing", "Fuerza"],
            "links": [{"label": "Sitio de ejemplo", "url": "https://example.com"}],
        },
    ),
    SectionSeed(
        "professional",
        content={
            "headline": "Data Engineer · Python, Spark y AWS",
            "summary": "Diseño y mantengo **pipelines de datos** y servicios backend. "
            "Me interesa la arquitectura de software y los sistemas que se pueden operar "
            "sin sustos.",
            "experience": [
                {
                    "company": "Empresa de ejemplo",
                    "role": "Data Engineer",
                    "start": "2022-03",
                    "description": "Pipelines batch y streaming en **PySpark** sobre AWS.",
                },
                {
                    "company": "Consultora de ejemplo",
                    "role": "Desarrollador backend",
                    "start": "2020-01",
                    "end": "2022-02",
                },
            ],
            "education": [{"institution": "Universidad de ejemplo", "degree": "Ingeniería"}],
            "skills": ["Python", "SQL", "Apache Spark / PySpark", "AWS", "Vue / TypeScript"],
            "certifications": [{"name": "AWS Solutions Architect (en curso)", "issuer": "AWS"}],
            "links": [{"label": "Perfil de ejemplo", "url": "https://example.com/perfil"}],
        },
    ),
    SectionSeed(
        "collection",
        label="Proyectos",
        content={
            "intro": "Cosas que construí o estoy construyendo.",
            "layout": "cards",
            "sort": "manual",
        },
        groups=[("En progreso", None), ("Planeados", "Ideas que todavía no arrancan.")],
        items=[
            ItemSeed(
                "unified-life-manager.md",
                markdown(
                    """
Un sistema personal para llevar hábitos, finanzas, aprendizaje y salud, y un
espacio para experimentar con frontend y desarrollo asistido por IA.

- **Stack:** Vue, TypeScript, FastAPI, Postgres.
- **Estado:** en progreso. Este blog es parte de él.
""",
                    title="Unified Life Manager",
                    excerpt="Hábitos, finanzas, aprendizaje y salud en un solo lugar.",
                    tags=["Vue", "TypeScript", "FastAPI"],
                    cover_url=image("ulm"),
                ),
                group="En progreso",
            ),
            ItemSeed(
                "mas-proximamente.md",
                markdown(
                    "Otros experimentos y proyectos personales van a aparecer acá a medida "
                    "que tomen forma.",
                    title="Más próximamente",
                    tags=["Planeado"],
                ),
                group="Planeados",
            ),
        ],
    ),
    SectionSeed(
        "collection",
        label="Escritos",
        content={"intro": "Notas sobre datos, código, y lo que vaya surgiendo."},
        items=RUBEN_POSTS,
    ),
    SectionSeed(
        "collection",
        label="How-to",
        content={"intro": "Guías cortas para no volver a buscarlo.", "sort": "title"},
        groups=[("Datos", None)],
        items=[
            ItemSeed(
                "postgres-local-con-docker.md",
                markdown(
                    "Levantar Postgres con `docker run` y un volumen con nombre, para que "
                    "los datos sobrevivan al contenedor.",
                    title="Postgres local con Docker",
                    date="2026-09-10",
                    tags=["Postgres", "Docker"],
                ),
                group="Datos",
            ),
            ItemSeed(
                "zonas-horarias-sin-sustos.md",
                markdown(
                    "Guardar en UTC y convertir a la zona del usuario **antes** de "
                    "preguntar qué día es.",
                    title="Zonas horarias sin sustos",
                    date="2026-09-20",
                ),
            ),
            ItemSeed(
                "migraciones-con-alembic.md",
                markdown(
                    "Borrador: autogenerate, revisar y nunca confiar a ciegas.",
                    title="Migraciones con Alembic",
                ),
                published=False,
            ),
        ],
    ),
    # 7ª seccion, deshabilitada: con 6 habilitadas, habilitarla supera el tope.
    SectionSeed(
        "collection",
        label="Libros",
        enabled=False,
        items=[
            ItemSeed(
                "pragmatic-programmer.md",
                markdown("Releído en 2026. Sigue vigente.", title="The Pragmatic Programmer"),
            )
        ],
    ),
]

# --- rubendorado2 ---

RUBEN2 = [
    SectionSeed(
        "home",
        content={
            "headline": "Lecturas y hobbies",
            "intro": "Un rincón para anotar lo que leo y lo que hago los fines de semana.",
        },
    ),
    SectionSeed(
        "about",
        enabled=False,  # plantilla deshabilitada: no sale en el menu ni en la API publica
        content={"bio": "Todavía no escribí esto."},
    ),
    SectionSeed(
        "professional",
        content={
            "headline": "Analista",
            "skills": ["Excel", "SQL"],
            "experience": [{"company": "Empresa de ejemplo", "role": "Analista", "start": "2024"}],
        },
    ),
    SectionSeed(
        "collection",
        label="Libros",
        content={"intro": "Lo que leo, por género.", "layout": "list"},
        groups=[("Ficción", None), ("Técnicos", "Para el trabajo.")],
        items=[
            ItemSeed(
                "dune.md",
                markdown(
                    "Arrakis, especia y política. ![Desierto](https://picsum.photos/seed/ulm-dune/800/400)",
                    title="Dune",
                    date="2026-05-01",
                    tags=["Ciencia ficción"],
                    cover_url=image("dune"),
                ),
                group="Ficción",
            ),
            ItemSeed(
                "designing-data-intensive-applications.md",
                markdown(
                    "Replicación, particionamiento y consistencia, explicados sin humo.",
                    title="Designing Data-Intensive Applications",
                    date="2026-03-15",
                    tags=["Datos"],
                ),
                group="Técnicos",
            ),
            ItemSeed(
                "el-nombre-del-viento.md",
                markdown("Notas a medio escribir.", title="El nombre del viento"),
                group="Ficción",
                published=False,
            ),
        ],
    ),
    SectionSeed(
        "collection",
        label="Hobbies",
        content={"intro": "Fines de semana.", "layout": "cards"},
        items=[
            ItemSeed(
                "fotografia.md",
                markdown(
                    "Salidas cortas con una cámara vieja.",
                    title="Fotografía",
                    cover_url=image("foto"),
                ),
            ),
            ItemSeed(
                "ciclismo.md",
                markdown("Rutas de 40 km los domingos.", title="Ciclismo", cover_url=image("bici")),
            ),
        ],
    ),
]

SEEDS: dict[str, list[SectionSeed]] = {"rubendorado": RUBEN, "rubendorado2": RUBEN2}


def delete_blog(repository: BlogEntityRepository, user_id: int) -> int:
    """Borra toda la particion del usuario (su blog completo)."""
    rows = list(repository.query(user_id=user_id, sk_prefix=""))
    for row in rows:
        repository.delete(row)
    repository.flush()
    return len(rows)


def seed_user(service: BlogAdminService, user_id: int, sections: list[SectionSeed]) -> None:
    for spec in sections:
        section = service.create_section(
            user_id, SectionCreate(type=spec.type, label=spec.label, enabled=spec.enabled)
        )
        if spec.content:
            service.set_section_content(user_id, section.id, spec.content)
        group_ids = {
            label: service.create_group(
                user_id, section.id, GroupCreate(label=label, description=description)
            ).id
            for label, description in spec.groups
        }
        for item in spec.items:
            created, _ = service.upload_item(
                user_id,
                section.id,
                filename=item.filename,
                raw=item.text.encode("utf-8"),
                group_id=group_ids[item.group] if item.group else None,
            )
            if item.published:
                service.update_item(user_id, section.id, created.id, ItemUpdate(status="published"))


def main(argv: list[str]) -> int:
    reset = "--reset" in argv
    delete_only = "--delete" in argv
    db = SessionLocal()
    exit_code = 0
    try:
        users = SqlAlchemyUserRepository(db)
        repository = SqlAlchemyBlogEntityRepository(db)
        service = BlogAdminService(repository)
        for username, sections in SEEDS.items():
            user = users.get_by_username(username)
            if user is None:
                print(f"- {username}: no existe ningun usuario con ese username, se omite")
                continue
            existing = repository.query(user_id=user.id, sk_prefix="")
            if delete_only or (existing and reset):
                print(f"- {username}: borradas {delete_blog(repository, user.id)} filas")
            elif existing:
                print(f"- {username}: ya tiene blog ({len(existing)} filas); usa --reset")
                exit_code = 1
                continue
            if not delete_only:
                seed_user(service, user.id, sections)
                print(f"- {username}: {len(sections)} secciones cargadas")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
