"""Lectura publica de blogs (/public/blogs/*, sin sesion).

El blog se arma con BlogAdminService (lo mismo que haria el dueño por la API
privada) y se lee por HTTP como un visitante. Cada regla de visibilidad tiene
que terminar en el mismo 404, y nada privado (ids, email, borradores) puede
salir en una respuesta.
"""

import re
from datetime import UTC, datetime

import pytest

from app.db.models.blog import BlgEntity
from app.db.models.user import User, UserPermission
from app.repositories.sqlalchemy_blog_entity_repository import SqlAlchemyBlogEntityRepository
from app.schemas.blog_admin import BlogSettingsWrite, GroupCreate, ItemUpdate, SectionCreate
from app.services.blog_admin_service import BlogAdminService
from tests.conftest import client

API = "/api/v1/public/blogs"
NOT_FOUND = {"detail": "Blog no encontrado"}
ULID = re.compile(r"[0-9A-HJKMNP-TV-Z]{26}")


def _md(title: str, *, slug: str, date: str | None = None, body: str = "Cuerpo") -> bytes:
    date_line = f"date: {date}\n" if date else ""
    return f"---\ntitle: {title}\nslug: {slug}\n{date_line}---\n{body}\n".encode()


@pytest.fixture
def admin(db_session) -> BlogAdminService:
    return BlogAdminService(SqlAlchemyBlogEntityRepository(db_session))


@pytest.fixture
def blog(db_session, admin):
    """Blog de `ruben` (usuario 1) con permiso `blog`: Inicio y Escritos
    habilitados (en ese orden), Sobre mi deshabilitada; en Escritos una
    subseccion, dos publicados (uno en la subseccion) y un borrador."""
    user = db_session.get(User, 1)
    user.username = "ruben"
    db_session.add(UserPermission(user_id=1, permission="blog"))
    db_session.commit()

    admin.create_section(1, SectionCreate(type="home", enabled=True))
    admin.set_section_content(1, "home", {"headline": "Hola"})
    admin.create_section(1, SectionCreate(type="about"))  # deshabilitada
    writing = admin.create_section(
        1, SectionCreate(type="collection", label="Escritos", enabled=True)
    )
    group = admin.create_group(1, writing.id, GroupCreate(label="Datos"))

    def upload(slug: str, *, publish: bool = True, group_id: str | None = None, **kw):
        item, _ = admin.upload_item(
            1,
            writing.id,
            filename=f"{slug}.md",
            raw=_md(slug.title(), slug=slug, **kw),
            group_id=group_id,
        )
        if publish:
            admin.update_item(1, writing.id, item.id, ItemUpdate(status="published"))

    upload("viejo", date="2026-01-01", group_id=group.id)
    upload("nuevo", date="2026-06-01", body="# Titulo\n\nTexto **publico**")
    upload("borrador", publish=False)
    db_session.commit()
    return writing


def _get(path: str, **headers):
    return client.get(f"{API}/{path}", headers=headers)


# --- Blog y secciones ---


@pytest.mark.usefixtures("blog", "real_auth")
def test_blog_lists_enabled_sections_in_order_with_their_content():
    response = _get("ruben")

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "ruben"
    assert [(s["slug"], s["type"]) for s in body["sections"]] == [
        ("inicio", "home"),
        ("escritos", "collection"),
    ]
    assert body["sections"][0]["content"]["headline"] == "Hola"


@pytest.mark.usefixtures("blog")
def test_collection_groups_published_items_without_bodies():
    body = _get("ruben/escritos/items").json()

    assert body["section"] == {"slug": "escritos", "label": "Escritos"}
    [group] = body["groups"]
    assert (group["label"], [i["slug"] for i in group["items"]]) == ("Datos", ["viejo"])
    # Sin subseccion; el borrador no aparece; mas nuevo primero (date_desc).
    assert [i["slug"] for i in body["ungrouped"]] == ["nuevo"]
    assert "body_md" not in body["ungrouped"][0]


@pytest.mark.usefixtures("blog")
def test_item_returns_the_body_without_frontmatter():
    body = _get("ruben/escritos/items/nuevo").json()

    assert body["title"] == "Nuevo"
    assert body["section"] == {"slug": "escritos", "label": "Escritos"}
    assert body["body_md"].strip() == "# Titulo\n\nTexto **publico**"
    assert "title:" not in body["body_md"]


@pytest.mark.usefixtures("blog")
def test_slugs_in_the_url_ignore_case():
    assert _get("Ruben/Escritos/items/Nuevo").status_code == 200


@pytest.mark.usefixtures("blog")
def test_public_payloads_have_no_private_data():
    for path in ("ruben", "ruben/escritos/items", "ruben/escritos/items/nuevo"):
        text = _get(path).text
        assert not ULID.search(text), path
        for private in ("ruben@example.com", '"id"', "user_id", "draft", "group_id"):
            assert private not in text, (path, private)


# --- Visibilidad: siempre el mismo 404 ---


@pytest.mark.usefixtures("blog")
@pytest.mark.parametrize(
    "path",
    [
        "nadie",
        "ruben/sobre-mi/items",  # seccion deshabilitada
        "ruben/inicio/items",  # plantilla: no tiene elementos
        "ruben/no-existe/items",
        "ruben/escritos/items/borrador",
        "ruben/escritos/items/no-existe",
    ],
)
def test_hidden_or_missing_things_are_the_same_404(path):
    response = _get(path)

    assert (response.status_code, response.json()) == (404, NOT_FOUND)


@pytest.mark.usefixtures("blog")
def test_a_disabled_blog_is_a_404(admin, db_session):
    admin.update_settings(1, BlogSettingsWrite(enabled=False))
    db_session.commit()

    for path in ("ruben", "ruben/escritos/items", "ruben/escritos/items/nuevo"):
        assert _get(path).json() == NOT_FOUND


@pytest.mark.usefixtures("blog")
def test_without_the_blog_permission_everything_is_a_404(db_session):
    db_session.query(UserPermission).filter_by(user_id=1, permission="blog").delete()
    db_session.commit()

    assert _get("ruben/escritos/items/nuevo").json() == NOT_FOUND


@pytest.mark.usefixtures("blog")
def test_a_disabled_user_is_a_404(db_session):
    db_session.get(User, 1).disabled_at = datetime.now(UTC)
    db_session.commit()

    assert _get("ruben").json() == NOT_FOUND


@pytest.mark.usefixtures("blog")
def test_a_section_of_an_unknown_type_is_skipped(db_session):
    """Un tipo que se retiro del catalogo no rompe el blog."""
    entity = db_session.query(BlgEntity).filter_by(sk="SEC#home").one()
    entity.data = {**entity.data, "type": "retirado"}
    db_session.commit()

    assert [s["slug"] for s in _get("ruben").json()["sections"]] == ["escritos"]


# --- Cache HTTP ---


@pytest.mark.usefixtures("blog")
@pytest.mark.parametrize("path", ["ruben", "ruben/escritos/items", "ruben/escritos/items/nuevo"])
def test_responses_are_cacheable_and_revalidate_with_etag(path):
    first = _get(path)

    assert first.headers["cache-control"] == "public, max-age=60, stale-while-revalidate=86400"
    etag = first.headers["etag"]

    again = _get(path, **{"If-None-Match": etag})
    assert (again.status_code, again.content) == (304, b"")
    assert _get(path, **{"If-None-Match": '"otra"'}).status_code == 200


@pytest.mark.usefixtures("blog")
def test_the_etag_changes_when_the_content_changes(admin, db_session):
    etag = _get("ruben").headers["etag"]

    admin.set_section_content(1, "home", {"headline": "Otro"})
    db_session.commit()

    assert _get("ruben").headers["etag"] != etag


def test_a_404_is_not_cached():
    response = _get("nadie")

    assert response.status_code == 404
    assert "cache-control" not in response.headers
