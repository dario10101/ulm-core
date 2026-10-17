"""Lectura publica de blogs (sin sesion).

Reglas de visibilidad, todas con el mismo BlogNotFoundError (404): para el
visitante no hay diferencia entre "no existe" y "existe pero no se puede ver",
y distinguirlos revelaria que hay detras.
- Dueño: tiene username, no esta deshabilitado y tiene el permiso `blog`.
- Blog: su registro BLOG esta habilitado (sin registro, el usuario nunca
  entro al modulo: se trata como habilitado y sin secciones).
- Seccion: habilitada y de un tipo conocido. Elemento: publicado.

Lee solo por los patrones de acceso de PLAN-BLOG.md (7.4): secciones por
prefijo (A2) y de ahi la seccion por slug (A3), elementos y subsecciones por
prefijo (A4, A5), un elemento por indice (A6) y su cuerpo por clave (A7).
"""

import frontmatter

from app.db.models.user import User
from app.repositories import blog_keys as keys
from app.repositories.blog_entity_repository import BlogEntityRepository
from app.repositories.user_repository import UserRepository
from app.schemas.blog import (
    PublicBlogRead,
    PublicCollectionRead,
    PublicGroupRead,
    PublicItemRead,
    PublicItemSummary,
    PublicSectionRead,
    PublicSectionRef,
)
from app.services.blog_documents import BlogDoc, BodyDoc, GroupDoc, ItemDoc
from app.services.blog_reads import LoadedSection, load_sections, sort_items
from app.services.blog_section_types import CollectionContent, read_content
from app.services.errors import BlogNotFoundError
from app.services.permissions import Permission
from app.services.user_admin_service import UserAdminService
from app.services.username import normalize_username


def _not_found() -> BlogNotFoundError:
    return BlogNotFoundError("Blog no encontrado")


def _summary(doc: ItemDoc) -> PublicItemSummary:
    return PublicItemSummary(
        slug=doc.slug,
        title=doc.title,
        date=doc.date,
        excerpt=doc.excerpt,
        tags=doc.tags,
        cover_url=doc.cover_url,
    )


class BlogService:
    def __init__(
        self,
        users: UserRepository,
        user_admin: UserAdminService,
        blog: BlogEntityRepository,
    ) -> None:
        self._users = users
        self._user_admin = user_admin
        self._blog = blog

    def get_public_owner(self, username: str) -> User:
        """El dueño del blog, si es visible: existe, no esta deshabilitado y
        tiene el permiso `blog`."""
        user = self._users.get_by_username(normalize_username(username))
        if (
            user is None
            or user.username is None
            or user.disabled_at is not None
            or Permission.BLOG not in self._user_admin.effective_permissions(user)
        ):
            raise _not_found()
        return user

    def get_public_blog(self, username: str) -> PublicBlogRead:
        owner, blog = self._visible_blog(username)
        assert owner.username is not None  # garantizado por get_public_owner
        return PublicBlogRead(
            username=owner.username,
            display_name=blog.display_name,
            sections=[
                PublicSectionRead(
                    slug=section.doc.slug,
                    label=section.doc.label,
                    type=section.type.key,
                    content=read_content(
                        section.type, section.doc.content, section.doc.schema_version
                    ),
                )
                for section in self._enabled_sections(owner.id)
            ],
        )

    def get_public_collection(self, username: str, section_slug: str) -> PublicCollectionRead:
        owner, _ = self._visible_blog(username)
        section = self._collection(owner.id, section_slug)
        content = CollectionContent.model_validate(
            read_content(section.type, section.doc.content, section.doc.schema_version)
        )

        published = [
            (keys.last_part(entity.sk), doc)
            for entity in self._blog.query(user_id=owner.id, sk_prefix=keys.item_prefix(section.id))
            if (doc := ItemDoc.model_validate(entity.data)).status == "published"
        ]
        ordered = sort_items([doc for _, doc in published], content.sort)

        groups = sorted(
            (
                (keys.last_part(entity.sk), GroupDoc.model_validate(entity.data))
                for entity in self._blog.query(
                    user_id=owner.id, sk_prefix=keys.group_prefix(section.id)
                )
            ),
            key=lambda pair: (pair[1].position, pair[1].label.lower()),
        )
        group_ids = {group_id for group_id, _ in groups}
        return PublicCollectionRead(
            section=PublicSectionRef(slug=section.doc.slug, label=section.doc.label),
            groups=[
                PublicGroupRead(
                    label=group.label,
                    description=group.description,
                    items=[_summary(doc) for doc in ordered if doc.group_id == group_id],
                )
                for group_id, group in groups
            ],
            # Sin subseccion, o con una que ya no existe (no deberia pasar:
            # borrar una subseccion desagrupa sus elementos).
            ungrouped=[_summary(doc) for doc in ordered if doc.group_id not in group_ids],
        )

    def get_public_item(self, username: str, section_slug: str, item_slug: str) -> PublicItemRead:
        owner, _ = self._visible_blog(username)
        section = self._collection(owner.id, section_slug)
        entity = self._blog.get_by_index(
            user_id=owner.id,
            gsi1pk=keys.item_slug_index(owner.id, section.id),
            gsi1sk=item_slug.strip().lower(),
        )
        if entity is None:
            raise _not_found()
        doc = ItemDoc.model_validate(entity.data)
        body = self._blog.get(user_id=owner.id, sk=keys.body(keys.last_part(entity.sk)))
        if doc.status != "published" or body is None:
            raise _not_found()
        text = BodyDoc.model_validate(body.data).content_md
        return PublicItemRead(
            **_summary(doc).model_dump(),
            section=PublicSectionRef(slug=section.doc.slug, label=section.doc.label),
            # El original se guarda con su frontmatter (la descarga lo
            # devuelve igual); al lector solo le llega el cuerpo.
            body_md=frontmatter.loads(text).content,
        )

    # --- Interno ---

    def _visible_blog(self, username: str) -> tuple[User, BlogDoc]:
        owner = self.get_public_owner(username)
        entity = self._blog.get(user_id=owner.id, sk=keys.BLOG)
        blog = BlogDoc.model_validate(entity.data) if entity is not None else BlogDoc()
        if not blog.enabled:
            raise _not_found()
        return owner, blog

    def _enabled_sections(self, user_id: int) -> list[LoadedSection]:
        return [s for s in load_sections(self._blog, user_id) if s.doc.enabled]

    def _collection(self, user_id: int, section_slug: str) -> LoadedSection:
        slug = section_slug.strip().lower()
        for section in self._enabled_sections(user_id):
            if section.doc.slug == slug and section.type.has_items:
                return section
        raise _not_found()
