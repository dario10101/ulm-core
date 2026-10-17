"""El seed del blog (scripts/seed_blog.py) se carga sin errores y cubre lo
que promete. Pasa por BlogAdminService, asi que un dato invalido del seed
(contenido, slug, frontmatter, topes) rompe este test y no la base de dev."""

import pytest

from app.core.config import settings
from app.db.models.user import User, UserPermission
from app.repositories.sqlalchemy_blog_entity_repository import SqlAlchemyBlogEntityRepository
from app.schemas.blog_admin import SectionUpdate
from app.services.blog_admin_service import BlogAdminService
from app.services.blog_section_types import SECTION_TYPES
from app.services.errors import BlogLimitError
from scripts.seed_blog import SEEDS, delete_blog, seed_user
from tests.conftest import OTHER_USER_ID, client


@pytest.fixture
def seeded(db_session, other_user):
    for user_id, username in ((1, "rubendorado"), (OTHER_USER_ID, "rubendorado2")):
        db_session.get(User, user_id).username = username
        db_session.add(UserPermission(user_id=user_id, permission="blog"))
    db_session.commit()

    repository = SqlAlchemyBlogEntityRepository(db_session)
    service = BlogAdminService(repository)
    seed_user(service, 1, SEEDS["rubendorado"])
    seed_user(service, OTHER_USER_ID, SEEDS["rubendorado2"])
    db_session.commit()
    return service, repository


def test_the_seed_covers_every_section_type(seeded):
    service, _ = seeded
    types = {s.type for uid in (1, OTHER_USER_ID) for s in service.list_sections(uid)}

    assert types == set(SECTION_TYPES)


def test_the_first_user_sits_at_the_enabled_limit(seeded):
    service, _ = seeded
    sections = service.list_sections(1)
    books = next(s for s in sections if s.label == "Libros")

    assert sum(s.enabled for s in sections) == settings.blog_max_enabled_sections
    assert books.enabled is False
    with pytest.raises(BlogLimitError):
        service.update_section(1, books.id, SectionUpdate(enabled=True))


def test_the_public_blogs_show_what_the_seed_promises(seeded):
    first = client.get("/api/v1/public/blogs/rubendorado").json()
    home = first["sections"][0]
    assert (home["label"], home["slug"]) == ("Bienvenida", "inicio")
    assert "libros" not in [s["slug"] for s in first["sections"]]

    second = client.get("/api/v1/public/blogs/rubendorado2").json()
    assert "about" not in [s["type"] for s in second["sections"]]

    books = client.get("/api/v1/public/blogs/rubendorado2/libros/items").json()
    fiction = next(g for g in books["groups"] if g["label"] == "Ficción")
    # El borrador ("El nombre del viento") no se publica.
    assert [i["title"] for i in fiction["items"]] == ["Dune"]


def test_the_seed_can_be_deleted_and_loaded_again(seeded):
    service, repository = seeded

    assert delete_blog(repository, 1) > 0
    assert service.list_sections(1) == []
    seed_user(service, 1, SEEDS["rubendorado"])
    assert len(service.list_sections(1)) == len(SEEDS["rubendorado"])
