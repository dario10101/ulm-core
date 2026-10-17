"""Administracion del blog propio (/blog, permiso `blog`).

Con la tabla generica (blg_entities) las reglas que harian las FKs las hace el
service: estos tests cubren esas reglas (cascadas, singleton, slugs, topes,
pertenencia) y el aislamiento entre usuarios, que sostienen el pk armado
desde la sesion y el CHECK pk/user_id de la base.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.db.models.blog import BlgEntity
from app.repositories.sqlalchemy_blog_entity_repository import SqlAlchemyBlogEntityRepository
from app.services.blog_section_types import SECTION_TYPES
from app.services.errors import ConcurrentUpdateError
from tests.conftest import OTHER_USER_ID, acting_as, client

API = "/api/v1/blog"

MD = """---
title: Notas sobre PySpark
date: 2026-07-18
excerpt: Funciones de ventana.
tags: [Datos, PySpark]
cover_url: https://example.com/cover.png
---
# Notas

![grafico](https://example.com/g.png)
"""


def _create(type_: str, **fields) -> dict:
    response = client.post(f"{API}/sections", json={"type": type_, **fields})
    assert response.status_code == 201, response.text
    return response.json()


def _upload(section_id: str, content: str = MD, name: str = "notas.md", **params):
    return client.post(
        f"{API}/sections/{section_id}/items",
        files={"file": (name, content.encode("utf-8"), "text/markdown")},
        params={k: v for k, v in params.items() if k == "replace"},
        data={k: v for k, v in params.items() if k == "group_id"},
    )


def _rows(db_session, prefix: str = "") -> list[str]:
    return [
        row.sk for row in db_session.query(BlgEntity).filter(BlgEntity.sk.startswith(prefix)).all()
    ]


@pytest.fixture
def limits(monkeypatch):
    """Topes chicos para no crear decenas de filas por test."""

    def set_limits(**values):
        for name, value in values.items():
            monkeypatch.setattr(settings, f"blog_max_{name}", value)

    return set_limits


# --- Config ---


def test_settings_are_created_on_first_access_with_the_catalog():
    body = client.get(f"{API}/settings").json()

    assert body["enabled"] is True
    assert body["max_enabled_sections"] == settings.blog_max_enabled_sections
    assert {t["type"] for t in body["section_types"]} == set(SECTION_TYPES)


def test_update_settings():
    response = client.put(f"{API}/settings", json={"enabled": False, "display_name": "Rubén"})

    assert response.status_code == 200
    assert client.get(f"{API}/settings").json()["display_name"] == "Rubén"


# --- Secciones ---


def test_singleton_section_gets_the_template_defaults():
    section = _create("home")

    assert (section["id"], section["label"], section["slug"]) == ("home", "Inicio", "inicio")
    assert section["enabled"] is False
    assert section["content"]["highlights"] == []


def test_singleton_types_allow_only_one_section():
    _create("about")

    response = client.post(f"{API}/sections", json={"type": "about"})

    assert response.status_code == 409


def test_collections_can_be_many_and_get_free_slugs_from_the_label():
    first = _create("collection", label="Libros")
    second = _create("collection", label="Libros")
    third = _create("collection", label="Cómo hacer")

    assert (first["slug"], second["slug"], third["slug"]) == ("libros", "libros-2", "como-hacer")
    assert first["id"] != second["id"]


def test_an_explicit_slug_that_is_taken_is_a_conflict():
    _create("collection", label="Libros")

    response = client.post(
        f"{API}/sections", json={"type": "collection", "label": "Otra", "slug": "libros"}
    )

    assert response.status_code == 409


@pytest.mark.parametrize("slug", ["a", "Con Espacio", "-x", "x--y", "rss", "ñandu"])
def test_invalid_or_reserved_slugs_are_rejected(slug):
    response = client.post(f"{API}/sections", json={"type": "collection", "slug": slug})

    assert response.status_code == 422


def test_unknown_section_type_is_rejected():
    assert client.post(f"{API}/sections", json={"type": "gallery"}).status_code == 422


def test_renaming_keeps_the_slug_and_slug_changes_check_uniqueness():
    books = _create("collection", label="Libros")
    _create("collection", label="Hobbies")

    renamed = client.patch(f"{API}/sections/{books['id']}", json={"label": "Lecturas"}).json()
    assert (renamed["label"], renamed["slug"]) == ("Lecturas", "libros")

    taken = client.patch(f"{API}/sections/{books['id']}", json={"slug": "hobbies"})
    assert taken.status_code == 409

    moved = client.patch(f"{API}/sections/{books['id']}", json={"slug": "lecturas"}).json()
    assert moved["slug"] == "lecturas"
    # El slug viejo queda libre.
    assert _create("collection", label="X", slug="libros")["slug"] == "libros"


def test_enabled_sections_are_capped(limits):
    limits(enabled_sections=2)
    _create("home", enabled=True)
    _create("about", enabled=True)

    over = client.post(f"{API}/sections", json={"type": "professional", "enabled": True})
    assert over.status_code == 422
    assert "2 secciones" in over.json()["detail"]

    # Se puede crear deshabilitada, pero no habilitarla hasta liberar lugar.
    professional = _create("professional")
    assert client.patch(f"{API}/sections/professional", json={"enabled": True}).status_code == 422
    client.patch(f"{API}/sections/home", json={"enabled": False})
    enabled = client.patch(f"{API}/sections/{professional['id']}", json={"enabled": True})
    assert enabled.json()["enabled"] is True


def test_created_sections_are_capped(limits):
    limits(sections=2)
    _create("collection", label="A1")
    _create("collection", label="A2")

    assert client.post(f"{API}/sections", json={"type": "home"}).status_code == 422


def test_reorder_sections():
    home = _create("home")
    books = _create("collection", label="Libros")

    ordered = client.put(f"{API}/sections/order", json={"ids": [books["id"], home["id"]]})

    assert [s["id"] for s in ordered.json()] == [books["id"], home["id"]]
    assert [s["position"] for s in ordered.json()] == [0, 1]


@pytest.mark.parametrize("ids", [["home"], ["home", "home"], ["home", "otra"]])
def test_reorder_needs_every_section_once(ids):
    _create("home")
    _create("about")

    assert client.put(f"{API}/sections/order", json={"ids": ids}).status_code == 422


# --- Contenido de las plantillas ---


VALID_CONTENT = {
    "home": {
        "headline": "Datos y código",
        "intro": "Hola **mundo**",
        "highlights": [
            {"kind": "product", "title": "ULM", "url": "https://ulm.dev", "image_url": None}
        ],
        "cta": {"label": "Ver proyectos", "url": "https://ulm.dev/proyectos"},
    },
    "about": {
        "photo_url": "https://example.com/yo.jpg",
        "bio": "Data Engineer.",
        "interests": ["Kickboxing"],
        "links": [{"label": "GitHub", "url": "https://github.com/x"}],
    },
    "professional": {
        "headline": "Data Engineer",
        "experience": [{"company": "Acme", "role": "DE", "start": "2022-03"}],
        "skills": ["Python", "SQL"],
        "certifications": [{"name": "AWS SAA", "year": 2026}],
    },
    "collection": {"intro": "Lo que leo.", "layout": "cards", "sort": "manual"},
}


def test_every_section_type_has_a_valid_content_example():
    """Al agregar un tipo al catalogo, este test exige su ejemplo aca."""
    assert set(VALID_CONTENT) == set(SECTION_TYPES)


@pytest.mark.parametrize("type_", sorted(SECTION_TYPES))
def test_each_section_type_saves_and_returns_its_content(type_):
    section = _create(type_, label="Sección")

    response = client.put(f"{API}/sections/{section['id']}/content", json=VALID_CONTENT[type_])

    assert response.status_code == 200, response.text
    listed = next(s for s in client.get(f"{API}/sections").json() if s["id"] == section["id"])
    for key, value in VALID_CONTENT[type_].items():
        if not isinstance(value, (list, dict)):
            assert listed["content"][key] == value


@pytest.mark.parametrize(
    "content",
    [
        {"titular": "campo mal escrito"},
        {"highlights": [{"title": "x", "image_url": "http://inseguro.com/a.png"}]},
        {"highlights": [{"title": ""}]},
        {"headline": "x" * 121},
    ],
)
def test_invalid_template_content_is_a_422_with_the_field(content):
    _create("home")

    response = client.put(f"{API}/sections/home/content", json=content)

    assert response.status_code == 422
    assert response.json()["detail"]


def test_experience_dates_are_year_or_year_month():
    _create("professional")
    bad = {"experience": [{"company": "A", "role": "B", "start": "03/2022"}]}

    assert client.put(f"{API}/sections/professional/content", json=bad).status_code == 422


# --- Subsecciones y elementos ---


@pytest.fixture
def books() -> dict:
    return _create("collection", label="Libros")


def test_templates_have_no_groups_or_items():
    _create("home")

    assert client.post(f"{API}/sections/home/groups", json={"label": "x"}).status_code == 422
    assert _upload("home").status_code == 422


def test_upload_creates_a_draft_with_the_frontmatter(books, db_session):
    response = _upload(books["id"], name="Notas PySpark.md")

    assert response.status_code == 201, response.text
    item = response.json()
    assert item["slug"] == "notas-pyspark"  # del nombre del archivo
    assert item["title"] == "Notas sobre PySpark"
    assert item["date"] == "2026-07-18"
    assert item["tags"] == ["Datos", "PySpark"]
    assert item["status"] == "draft"
    assert item["original_filename"] == "Notas PySpark.md"
    # Metadatos y cuerpo en filas separadas (los listados no leen el cuerpo).
    assert _rows(db_session, f"BODY#{item['id']}") == [f"BODY#{item['id']}"]


def test_download_returns_the_original_file(books):
    item = _upload(books["id"]).json()

    response = client.get(f"{API}/sections/{books['id']}/items/{item['id']}/download")

    assert response.status_code == 200
    assert response.content.decode("utf-8") == MD
    assert response.headers["content-disposition"] == 'attachment; filename="notas.md"'


def test_frontmatter_slug_wins_over_the_filename(books):
    content = MD.replace("title:", "slug: mi-slug\ntitle:", 1)

    assert _upload(books["id"], content).json()["slug"] == "mi-slug"


def test_same_slug_is_a_conflict_unless_replace(books):
    first = _upload(books["id"]).json()
    client.patch(f"{API}/sections/{books['id']}/items/{first['id']}", json={"status": "published"})

    assert _upload(books["id"]).status_code == 409

    changed = MD.replace("Notas sobre PySpark", "Notas v2")
    replaced = _upload(books["id"], changed, replace="true")
    assert replaced.status_code == 200
    # Mismo elemento: conserva id y estado; cambian metadatos y cuerpo.
    assert (replaced.json()["id"], replaced.json()["status"]) == (first["id"], "published")
    assert replaced.json()["title"] == "Notas v2"
    download = client.get(f"{API}/sections/{books['id']}/items/{first['id']}/download")
    assert "Notas v2" in download.text


def test_the_same_slug_can_exist_in_two_sections(books):
    hobbies = _create("collection", label="Hobbies")

    assert _upload(books["id"]).status_code == 201
    assert _upload(hobbies["id"]).status_code == 201


@pytest.mark.parametrize(
    ("name", "content", "reason"),
    [
        ("notas.txt", MD, ".md"),
        ("notas.md", "# Sin frontmatter", "frontmatter"),
        ("notas.md", "---\ntitle: [sin cerrar\n---\n", "YAML"),
        ("notas.md", "---\ndate: 2026-01-01\n---\n", "title"),
        ("notas.md", MD.replace("https://example.com/cover", "http://example.com/cover"), "https"),
        ("ñ.md", "---\ntitle: X\n---\n", "slug"),
    ],
)
def test_invalid_uploads_are_rejected(books, name, content, reason):
    response = _upload(books["id"], content, name=name)

    assert response.status_code == 422
    assert reason in response.json()["detail"]


def test_non_utf8_and_oversized_files_are_rejected(books, limits):
    bad = client.post(
        f"{API}/sections/{books['id']}/items",
        files={"file": ("x.md", "---\ntitle: ñ\n---".encode("latin-1"), "text/markdown")},
    )
    assert bad.status_code == 422
    assert "UTF-8" in bad.json()["detail"]

    limits(md_bytes=50)
    assert _upload(books["id"]).status_code == 422


def test_items_per_section_are_capped(books, limits):
    limits(items_per_section=1)
    _upload(books["id"])

    other = MD.replace("title:", "slug: otro\ntitle:", 1)
    assert _upload(books["id"], other).status_code == 422


def test_groups_crud_and_items_inside(books):
    fiction = client.post(f"{API}/sections/{books['id']}/groups", json={"label": "Ficción"}).json()
    tech = client.post(f"{API}/sections/{books['id']}/groups", json={"label": "Técnicos"}).json()
    assert (fiction["position"], tech["position"]) == (0, 1)

    item = _upload(books["id"], group_id=fiction["id"]).json()
    assert item["group_id"] == fiction["id"]

    moved = client.patch(
        f"{API}/sections/{books['id']}/items/{item['id']}", json={"group_id": tech["id"]}
    )
    assert moved.json()["group_id"] == tech["id"]
    ungrouped = client.patch(
        f"{API}/sections/{books['id']}/items/{item['id']}", json={"group_id": None}
    )
    assert ungrouped.json()["group_id"] is None

    renamed = client.patch(
        f"{API}/sections/{books['id']}/groups/{tech['id']}", json={"label": "Técnica"}
    )
    assert renamed.json()["label"] == "Técnica"


def test_a_group_of_another_section_is_not_valid(books):
    hobbies = _create("collection", label="Hobbies")
    other_group = client.post(
        f"{API}/sections/{hobbies['id']}/groups", json={"label": "Música"}
    ).json()

    assert _upload(books["id"], group_id=other_group["id"]).status_code == 404
    assert _upload(books["id"], group_id="NOEXISTE").status_code == 404


def test_deleting_a_group_keeps_its_items_without_group(books):
    group = client.post(f"{API}/sections/{books['id']}/groups", json={"label": "Ficción"}).json()
    item = _upload(books["id"], group_id=group["id"]).json()

    assert client.delete(f"{API}/sections/{books['id']}/groups/{group['id']}").status_code == 204

    [listed] = client.get(f"{API}/sections/{books['id']}/items").json()
    assert (listed["id"], listed["group_id"]) == (item["id"], None)
    assert client.get(f"{API}/sections/{books['id']}/groups").json() == []


def test_groups_per_section_are_capped(books, limits):
    limits(groups_per_section=1)
    client.post(f"{API}/sections/{books['id']}/groups", json={"label": "A"})

    response = client.post(f"{API}/sections/{books['id']}/groups", json={"label": "B"})

    assert response.status_code == 422


def test_deleting_an_item_deletes_its_body(books, db_session):
    item = _upload(books["id"]).json()

    assert client.delete(f"{API}/sections/{books['id']}/items/{item['id']}").status_code == 204

    assert _rows(db_session, "ITM#") == []
    assert _rows(db_session, "BODY#") == []


def test_deleting_a_section_cascades_to_groups_items_and_bodies(books, db_session):
    hobbies = _create("collection", label="Hobbies")
    client.post(f"{API}/sections/{books['id']}/groups", json={"label": "Ficción"})
    _upload(books["id"])
    kept = _upload(hobbies["id"]).json()

    assert client.delete(f"{API}/sections/{books['id']}").status_code == 204

    assert client.get(f"{API}/sections/{books['id']}/items").status_code == 404
    # Lo de la otra seccion sigue intacto.
    assert sorted(_rows(db_session, "ITM#") + _rows(db_session, "BODY#")) == sorted(
        [f"ITM#{hobbies['id']}#{kept['id']}", f"BODY#{kept['id']}"]
    )
    assert _rows(db_session, "GRP#") == []


def test_item_of_another_section_is_not_found(books):
    hobbies = _create("collection", label="Hobbies")
    item = _upload(books["id"]).json()

    path = f"{API}/sections/{hobbies['id']}/items/{item['id']}"
    assert client.patch(path, json={"status": "published"}).status_code == 404
    assert client.get(f"{path}/download").status_code == 404


# --- Aislamiento entre usuarios ---


def test_another_user_cannot_see_or_touch_my_blog(books, other_user):
    group = client.post(f"{API}/sections/{books['id']}/groups", json={"label": "Ficción"}).json()
    item = _upload(books["id"]).json()
    section = f"{API}/sections/{books['id']}"

    with acting_as(other_user):
        assert client.get(f"{API}/sections").json() == []
        assert client.patch(section, json={"label": "Mio"}).status_code == 404
        assert client.put(f"{section}/content", json={}).status_code == 404
        assert client.get(f"{section}/items").status_code == 404
        assert _upload(books["id"]).status_code == 404
        assert client.get(f"{section}/items/{item['id']}/download").status_code == 404
        assert client.delete(f"{section}/groups/{group['id']}").status_code == 404
        assert client.delete(f"{section}/items/{item['id']}").status_code == 404
        assert client.delete(section).status_code == 404
        # Puede usar los mismos slugs: son unicos por usuario.
        assert _create("collection", label="Libros")["slug"] == "libros"

    assert client.get(f"{section}/items").json()[0]["id"] == item["id"]


def test_the_database_rejects_a_row_in_another_users_partition(db_session, other_user):
    db_session.add(
        BlgEntity(pk=f"USER#{other_user}", sk="BLOG", user_id=1, entity_type="BLOG", data={})
    )

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# --- Concurrencia ---


def test_a_stale_write_is_a_concurrent_update_error(db_session):
    client.get(f"{API}/settings")  # crea el registro BLOG
    repository = SqlAlchemyBlogEntityRepository(db_session)
    blog = repository.get(user_id=1, sk="BLOG")
    # Otro request lo escribio despues de que este lo leyera.
    db_session.execute(text("UPDATE blg_entities SET version = version + 1 WHERE sk = 'BLOG'"))

    blog.data = {"enabled": False}
    with pytest.raises(ConcurrentUpdateError):
        repository.flush()
    db_session.rollback()


# --- Orden de subsecciones y elementos ---


def test_reorder_groups(books):
    a = client.post(f"{API}/sections/{books['id']}/groups", json={"label": "A"}).json()
    b = client.post(f"{API}/sections/{books['id']}/groups", json={"label": "B"}).json()

    ordered = client.put(
        f"{API}/sections/{books['id']}/groups/order", json={"ids": [b["id"], a["id"]]}
    )

    assert [(g["label"], g["position"]) for g in ordered.json()] == [("B", 0), ("A", 1)]


def test_reorder_items_sets_the_manual_order(books):
    first = _upload(books["id"]).json()
    second = _upload(books["id"], MD.replace("title:", "slug: otro\ntitle:", 1)).json()

    ordered = client.put(
        f"{API}/sections/{books['id']}/items/order", json={"ids": [second["id"], first["id"]]}
    )

    assert [(i["id"], i["position"]) for i in ordered.json()] == [
        (second["id"], 0),
        (first["id"], 1),
    ]


@pytest.mark.parametrize("kind", ["groups", "items"])
def test_reorder_needs_every_group_or_item_once(books, kind):
    if kind == "groups":
        ids = [
            client.post(f"{API}/sections/{books['id']}/groups", json={"label": x}).json()["id"]
            for x in ("A", "B")
        ]
    else:
        ids = [
            _upload(books["id"]).json()["id"],
            _upload(books["id"], MD.replace("title:", "slug: otro\ntitle:", 1)).json()["id"],
        ]
    path = f"{API}/sections/{books['id']}/{kind}/order"

    for bad in ([ids[0]], [ids[0], ids[0]], [ids[0], "NOEXISTE"]):
        assert client.put(path, json={"ids": bad}).status_code == 422


def test_reorder_of_another_users_section_is_not_found(books, other_user):
    with acting_as(other_user):
        for kind in ("groups", "items"):
            path = f"{API}/sections/{books['id']}/{kind}/order"
            assert client.put(path, json={"ids": []}).status_code == 404
