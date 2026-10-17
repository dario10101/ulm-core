"""Administracion del blog propio (permiso `blog`): config, secciones,
subsecciones y elementos .md.

La persistencia es una tabla generica llave-valor (blg_entities, ver
app/db/models/blog.py). Por eso este service hace lo que en tablas
relacionales harian las FKs y constraints:

- Cascadas: borrar una seccion borra sus subsecciones, elementos y cuerpos;
  borrar una subseccion saca de ella a sus elementos.
- Pertenencia: una subseccion referenciada por un elemento tiene que ser de la
  misma seccion (se busca por su clave, que incluye la seccion).
- Limites (PLAN-BLOG.md seccion 5): cada cambio que altera cuantas secciones
  hay o cuantas estan habilitadas reescribe el registro BLOG; su `version`
  (bloqueo optimista) hace que de dos requests simultaneos uno falle con 409
  en vez de pasar ambos el tope.

Cada metodo lee solo por los patrones de acceso de PLAN-BLOG.md (7.4): por
clave o por prefijo del sk dentro de la particion del usuario.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from app.core.config import settings
from app.core.ids import new_ulid
from app.core.logging import get_logger
from app.db.models.blog import (
    ENTITY_BLOG,
    ENTITY_BODY,
    ENTITY_GROUP,
    ENTITY_ITEM,
    ENTITY_SECTION,
    BlgEntity,
)
from app.repositories import blog_keys as keys
from app.repositories.blog_entity_repository import BlogEntityRepository
from app.schemas.blog_admin import (
    BlogSettingsRead,
    BlogSettingsWrite,
    GroupCreate,
    GroupRead,
    GroupUpdate,
    ItemRead,
    ItemUpdate,
    SectionCreate,
    SectionRead,
    SectionTypeRead,
    SectionUpdate,
)
from app.services.blog_documents import BlogDoc, BodyDoc, GroupDoc, ItemDoc, SectionDoc
from app.services.blog_markdown import parse_markdown_upload
from app.services.blog_reads import LoadedSection as _Section
from app.services.blog_reads import load_sections, sort_items
from app.services.blog_section_types import (
    SECTION_TYPES,
    get_section_type,
    read_content,
    validate_content,
)
from app.services.blog_slugs import (
    SECTION_SLUG_MAX,
    SECTION_SLUG_MIN,
    slugify,
    validate_section_slug,
)
from app.services.errors import (
    BlogGroupNotFoundError,
    BlogItemNotFoundError,
    BlogLimitError,
    BlogSectionNotFoundError,
    InvalidOrderError,
    SectionWithoutItemsError,
    SingletonSectionExistsError,
    SlugTakenError,
)

logger = get_logger(__name__)

# Slug de una seccion cuyo label no deja ninguno valido (ej. "Ñ" o "日本").
_FALLBACK_SECTION_SLUG = "seccion"


def _now() -> datetime:
    return datetime.now(UTC)


def _save(entity: BlgEntity, document: BaseModel) -> None:
    """Reescribe `data`. Asignar un dict nuevo (y no mutar el viejo) es lo que
    hace que SQLAlchemy detecte el cambio en una columna JSON."""
    entity.data = document.model_dump(mode="json")
    entity.updated_at = _now()


class BlogAdminService:
    def __init__(self, repository: BlogEntityRepository) -> None:
        self._repo = repository

    # --- Config ---

    def get_settings(self, user_id: int) -> BlogSettingsRead:
        entity = self._blog(user_id)
        self._repo.flush()
        return self._settings_read(BlogDoc.model_validate(entity.data))

    def update_settings(self, user_id: int, payload: BlogSettingsWrite) -> BlogSettingsRead:
        entity = self._blog(user_id)
        doc = BlogDoc(enabled=payload.enabled, display_name=payload.display_name or None)
        _save(entity, doc)
        self._repo.flush()
        return self._settings_read(doc)

    # --- Secciones ---

    def list_sections(self, user_id: int) -> list[SectionRead]:
        return [self._section_read(section) for section in self._sections(user_id)]

    def create_section(self, user_id: int, payload: SectionCreate) -> SectionRead:
        section_type = get_section_type(payload.type)
        blog = self._blog(user_id)
        sections = self._sections(user_id, include_unknown=True)
        if len(sections) >= settings.blog_max_sections:
            raise BlogLimitError(f"Puedes tener hasta {settings.blog_max_sections} secciones")
        if section_type.singleton and any(s.doc.type == section_type.key for s in sections):
            raise SingletonSectionExistsError(section_type.key)
        if payload.enabled:
            self._check_enabled_limit(sections)

        label = payload.label or section_type.default_label
        taken = {s.doc.slug for s in sections}
        if payload.slug is not None:
            slug = validate_section_slug(payload.slug)
            if slug in taken:
                raise SlugTakenError(slug)
        else:
            base = section_type.default_slug or slugify(label, SECTION_SLUG_MAX)
            slug = self._free_slug(base, taken)

        section_id = section_type.key if section_type.singleton else new_ulid()
        doc = SectionDoc(
            type=section_type.key,
            label=label,
            slug=slug,
            position=max((s.doc.position for s in sections), default=-1) + 1,
            enabled=payload.enabled,
            schema_version=section_type.schema_version,
            content=validate_content(section_type, {}),
        )
        entity = self._repo.create(
            user_id=user_id,
            sk=keys.section(section_id),
            entity_type=ENTITY_SECTION,
            data=doc.model_dump(mode="json"),
            gsi1pk=keys.section_slug_index(user_id),
            gsi1sk=slug,
        )
        self._touch(blog)
        self._repo.flush()
        return self._section_read(_Section(entity, doc, section_type))

    def update_section(self, user_id: int, section_id: str, payload: SectionUpdate) -> SectionRead:
        section = self._section(user_id, section_id)
        doc = section.doc
        fields = payload.model_fields_set

        if "label" in fields and payload.label is not None:
            doc.label = payload.label
        if "slug" in fields and payload.slug is not None:
            slug = validate_section_slug(payload.slug)
            if slug != doc.slug:
                if self._repo.get_by_index(
                    user_id=user_id, gsi1pk=keys.section_slug_index(user_id), gsi1sk=slug
                ):
                    raise SlugTakenError(slug)
                doc.slug = slug
                section.entity.gsi1sk = slug
        if "enabled" in fields and payload.enabled is not None and payload.enabled != doc.enabled:
            blog = self._blog(user_id)
            if payload.enabled:
                self._check_enabled_limit(self._sections(user_id, include_unknown=True))
            doc.enabled = payload.enabled
            self._touch(blog)

        _save(section.entity, doc)
        self._repo.flush()
        return self._section_read(section)

    def set_section_content(
        self, user_id: int, section_id: str, content: dict[str, Any]
    ) -> SectionRead:
        """Reemplaza el contenido de la plantilla (lo que manda el formulario)."""
        section = self._section(user_id, section_id)
        section.doc.content = validate_content(section.type, content)
        section.doc.schema_version = section.type.schema_version
        _save(section.entity, section.doc)
        self._repo.flush()
        return self._section_read(section)

    def reorder_sections(self, user_id: int, ids: list[str]) -> list[SectionRead]:
        sections = self._sections(user_id, include_unknown=True)
        by_id = {section.id: section for section in sections}
        self._check_order(ids, by_id, "seccion")
        for position, section_id in enumerate(ids):
            section = by_id[section_id]
            if section.doc.position != position:
                section.doc.position = position
                _save(section.entity, section.doc)
        self._repo.flush()
        return self.list_sections(user_id)

    def delete_section(self, user_id: int, section_id: str) -> None:
        """Borra la seccion con sus subsecciones, elementos y cuerpos."""
        section = self._section(user_id, section_id)
        blog = self._blog(user_id)
        for group in self._repo.query(user_id=user_id, sk_prefix=keys.group_prefix(section.id)):
            self._repo.delete(group)
        for item in self._repo.query(user_id=user_id, sk_prefix=keys.item_prefix(section.id)):
            body = self._repo.get(user_id=user_id, sk=keys.body(keys.last_part(item.sk)))
            if body is not None:
                self._repo.delete(body)
            self._repo.delete(item)
        self._repo.delete(section.entity)
        self._touch(blog)
        self._repo.flush()

    # --- Subsecciones ---

    def list_groups(self, user_id: int, section_id: str) -> list[GroupRead]:
        section = self._items_section(user_id, section_id)
        groups = [self._group_read(entity) for entity in self._groups(user_id, section.id)]
        return sorted(groups, key=lambda group: (group.position, group.label.lower()))

    def create_group(self, user_id: int, section_id: str, payload: GroupCreate) -> GroupRead:
        section = self._items_section(user_id, section_id)
        groups = self._groups(user_id, section.id)
        if len(groups) >= settings.blog_max_groups_per_section:
            raise BlogLimitError(
                f"Una seccion puede tener hasta {settings.blog_max_groups_per_section} subsecciones"
            )
        doc = GroupDoc(
            label=payload.label,
            description=payload.description or None,
            position=max((GroupDoc.model_validate(g.data).position for g in groups), default=-1)
            + 1,
        )
        entity = self._repo.create(
            user_id=user_id,
            sk=keys.group(section.id, new_ulid()),
            entity_type=ENTITY_GROUP,
            data=doc.model_dump(mode="json"),
        )
        self._repo.flush()
        return self._group_read(entity)

    def update_group(
        self, user_id: int, section_id: str, group_id: str, payload: GroupUpdate
    ) -> GroupRead:
        section = self._items_section(user_id, section_id)
        entity = self._group(user_id, section.id, group_id)
        doc = GroupDoc.model_validate(entity.data)
        fields = payload.model_fields_set
        if "label" in fields and payload.label is not None:
            doc.label = payload.label
        if "description" in fields:
            doc.description = payload.description or None
        if "position" in fields and payload.position is not None:
            doc.position = payload.position
        _save(entity, doc)
        self._repo.flush()
        return self._group_read(entity)

    def reorder_groups(self, user_id: int, section_id: str, ids: list[str]) -> list[GroupRead]:
        """Todas las subsecciones de la seccion, en el orden nuevo (atomico:
        subir una es mover dos)."""
        section = self._items_section(user_id, section_id)
        by_id = {keys.last_part(e.sk): e for e in self._groups(user_id, section.id)}
        self._check_order(ids, by_id, "subseccion")
        for position, group_id in enumerate(ids):
            entity = by_id[group_id]
            doc = GroupDoc.model_validate(entity.data)
            if doc.position != position:
                doc.position = position
                _save(entity, doc)
        self._repo.flush()
        return self.list_groups(user_id, section.id)

    def delete_group(self, user_id: int, section_id: str, group_id: str) -> None:
        """Borra la subseccion; sus elementos quedan en la seccion, sin subseccion."""
        section = self._items_section(user_id, section_id)
        entity = self._group(user_id, section.id, group_id)
        for item in self._repo.query(user_id=user_id, sk_prefix=keys.item_prefix(section.id)):
            doc = ItemDoc.model_validate(item.data)
            if doc.group_id == group_id:
                doc.group_id = None
                _save(item, doc)
        self._repo.delete(entity)
        self._repo.flush()

    # --- Elementos (.md) ---

    def list_items(self, user_id: int, section_id: str) -> list[ItemRead]:
        """Todos, borradores incluidos, sin el cuerpo del .md."""
        section = self._items_section(user_id, section_id)
        items = [
            self._item_read(section.id, entity)
            for entity in self._repo.query(user_id=user_id, sk_prefix=keys.item_prefix(section.id))
        ]
        # El admin ve siempre el orden manual (posicion, luego fecha): es el
        # que esta editando, aunque la vista publica ordene de otra forma.
        return sort_items(items, "manual")

    def upload_item(
        self,
        user_id: int,
        section_id: str,
        *,
        filename: str | None,
        raw: bytes,
        replace: bool = False,
        group_id: str | None = None,
    ) -> tuple[ItemRead, bool]:
        """Sube un .md. Un slug que ya existe en la seccion es 409, salvo
        `replace` (B5): entonces se reemplazan metadatos y cuerpo, conservando
        id, estado y posicion. Devuelve el elemento y si se creo."""
        section = self._items_section(user_id, section_id)
        parsed = parse_markdown_upload(filename, raw, max_bytes=settings.blog_max_md_bytes)
        if group_id is not None:
            self._group(user_id, section.id, group_id)

        existing = self._repo.get_by_index(
            user_id=user_id,
            gsi1pk=keys.item_slug_index(user_id, section.id),
            gsi1sk=parsed.slug,
        )
        if existing is not None and not replace:
            raise SlugTakenError(parsed.slug)

        if existing is None:
            items = self._repo.query(user_id=user_id, sk_prefix=keys.item_prefix(section.id))
            if len(items) >= settings.blog_max_items_per_section:
                raise BlogLimitError(
                    f"Una seccion puede tener hasta {settings.blog_max_items_per_section} elementos"
                )
            item_id = new_ulid()
            previous = None
        else:
            item_id = keys.last_part(existing.sk)
            previous = ItemDoc.model_validate(existing.data)

        doc = ItemDoc(
            slug=parsed.slug,
            title=parsed.meta.title,
            date=parsed.meta.date,
            excerpt=parsed.meta.excerpt or None,
            tags=parsed.meta.tags,
            cover_url=str(parsed.meta.cover_url) if parsed.meta.cover_url else None,
            group_id=group_id if group_id is not None or previous is None else previous.group_id,
            status=previous.status if previous else "draft",
            position=previous.position if previous else None,
            size_bytes=parsed.size_bytes,
            sha256=parsed.sha256,
            original_filename=parsed.filename,
        )
        body = BodyDoc(content_md=parsed.text)

        if existing is None:
            entity = self._repo.create(
                user_id=user_id,
                sk=keys.item(section.id, item_id),
                entity_type=ENTITY_ITEM,
                data=doc.model_dump(mode="json"),
                gsi1pk=keys.item_slug_index(user_id, section.id),
                gsi1sk=parsed.slug,
            )
            self._repo.create(
                user_id=user_id,
                sk=keys.body(item_id),
                entity_type=ENTITY_BODY,
                data=body.model_dump(mode="json"),
            )
        else:
            entity = existing
            _save(entity, doc)
            body_entity = self._repo.get(user_id=user_id, sk=keys.body(item_id))
            if body_entity is None:  # no deberia pasar: se crean juntos
                self._repo.create(
                    user_id=user_id,
                    sk=keys.body(item_id),
                    entity_type=ENTITY_BODY,
                    data=body.model_dump(mode="json"),
                )
            else:
                _save(body_entity, body)
        self._repo.flush()
        return self._item_read(section.id, entity), existing is None

    def update_item(
        self, user_id: int, section_id: str, item_id: str, payload: ItemUpdate
    ) -> ItemRead:
        section = self._items_section(user_id, section_id)
        entity = self._item(user_id, section.id, item_id)
        doc = ItemDoc.model_validate(entity.data)
        fields = payload.model_fields_set
        if "status" in fields and payload.status is not None:
            doc.status = payload.status
        if "group_id" in fields:
            if payload.group_id is not None:
                self._group(user_id, section.id, payload.group_id)
            doc.group_id = payload.group_id
        if "position" in fields:
            doc.position = payload.position
        _save(entity, doc)
        self._repo.flush()
        return self._item_read(section.id, entity)

    def reorder_items(self, user_id: int, section_id: str, ids: list[str]) -> list[ItemRead]:
        """Todos los elementos de la seccion, en el orden manual nuevo (lo usa
        la vista publica cuando la coleccion ordena `manual`)."""
        section = self._items_section(user_id, section_id)
        by_id = {
            keys.last_part(e.sk): e
            for e in self._repo.query(user_id=user_id, sk_prefix=keys.item_prefix(section.id))
        }
        self._check_order(ids, by_id, "elemento")
        for position, item_id in enumerate(ids):
            entity = by_id[item_id]
            doc = ItemDoc.model_validate(entity.data)
            if doc.position != position:
                doc.position = position
                _save(entity, doc)
        self._repo.flush()
        return self.list_items(user_id, section.id)

    def delete_item(self, user_id: int, section_id: str, item_id: str) -> None:
        section = self._items_section(user_id, section_id)
        entity = self._item(user_id, section.id, item_id)
        body = self._repo.get(user_id=user_id, sk=keys.body(item_id))
        if body is not None:
            self._repo.delete(body)
        self._repo.delete(entity)
        self._repo.flush()

    def download_item(self, user_id: int, section_id: str, item_id: str) -> tuple[str, str]:
        """(nombre de archivo, .md original tal cual se subio)."""
        section = self._items_section(user_id, section_id)
        entity = self._item(user_id, section.id, item_id)
        body = self._repo.get(user_id=user_id, sk=keys.body(item_id))
        if body is None:
            raise BlogItemNotFoundError()
        doc = ItemDoc.model_validate(entity.data)
        return doc.original_filename, BodyDoc.model_validate(body.data).content_md

    # --- Lectura interna ---

    def _blog(self, user_id: int) -> BlgEntity:
        """El registro BLOG del usuario; se crea en el primer acceso (no en
        una migracion ni en el alta del usuario: ver D20)."""
        entity = self._repo.get(user_id=user_id, sk=keys.BLOG)
        if entity is None:
            entity = self._repo.create(
                user_id=user_id,
                sk=keys.BLOG,
                entity_type=ENTITY_BLOG,
                data=BlogDoc().model_dump(mode="json"),
            )
        return entity

    def _touch(self, blog: BlgEntity) -> None:
        """Fuerza un UPDATE del registro BLOG (y con el, el chequeo de su
        `version`). Ver el docstring del modulo."""
        blog.updated_at = _now()

    def _sections(self, user_id: int, *, include_unknown: bool = False) -> list[_Section]:
        return load_sections(self._repo, user_id, include_unknown=include_unknown)

    def _section(self, user_id: int, section_id: str) -> _Section:
        entity = self._repo.get(user_id=user_id, sk=keys.section(section_id))
        if entity is None:
            raise BlogSectionNotFoundError()
        doc = SectionDoc.model_validate(entity.data)
        section_type = SECTION_TYPES.get(doc.type)
        if section_type is None:
            raise BlogSectionNotFoundError()
        return _Section(entity, doc, section_type)

    def _items_section(self, user_id: int, section_id: str) -> _Section:
        section = self._section(user_id, section_id)
        if not section.type.has_items:
            raise SectionWithoutItemsError(section.type.key)
        return section

    def _groups(self, user_id: int, section_id: str) -> list[BlgEntity]:
        return list(self._repo.query(user_id=user_id, sk_prefix=keys.group_prefix(section_id)))

    def _group(self, user_id: int, section_id: str, group_id: str) -> BlgEntity:
        entity = self._repo.get(user_id=user_id, sk=keys.group(section_id, group_id))
        if entity is None:
            raise BlogGroupNotFoundError()
        return entity

    def _item(self, user_id: int, section_id: str, item_id: str) -> BlgEntity:
        entity = self._repo.get(user_id=user_id, sk=keys.item(section_id, item_id))
        if entity is None:
            raise BlogItemNotFoundError()
        return entity

    @staticmethod
    def _check_order(ids: list[str], existing: dict[str, Any], noun: str) -> None:
        if len(ids) != len(set(ids)) or set(ids) != set(existing):
            raise InvalidOrderError(noun)

    @staticmethod
    def _check_enabled_limit(sections: list[_Section]) -> None:
        if sum(s.doc.enabled for s in sections) >= settings.blog_max_enabled_sections:
            raise BlogLimitError(
                f"Puedes tener hasta {settings.blog_max_enabled_sections} secciones "
                "habilitadas a la vez. Deshabilita otra primero."
            )

    @staticmethod
    def _free_slug(base: str, taken: set[str]) -> str:
        """`base` si esta libre; si no, base-2, base-3... Solo para slugs
        automaticos: uno elegido por el usuario que ya existe es 409."""
        if len(base) < SECTION_SLUG_MIN:
            base = _FALLBACK_SECTION_SLUG
        candidate = base
        suffix = 2
        while candidate in taken:
            tail = f"-{suffix}"
            candidate = f"{base[: SECTION_SLUG_MAX - len(tail)].rstrip('-')}{tail}"
            suffix += 1
        return validate_section_slug(candidate)

    # --- Mapeo a schemas ---

    @staticmethod
    def _settings_read(doc: BlogDoc) -> BlogSettingsRead:
        return BlogSettingsRead(
            enabled=doc.enabled,
            display_name=doc.display_name,
            max_enabled_sections=settings.blog_max_enabled_sections,
            max_sections=settings.blog_max_sections,
            section_types=[
                SectionTypeRead(
                    type=t.key,
                    singleton=t.singleton,
                    has_items=t.has_items,
                    default_label=t.default_label,
                    default_slug=t.default_slug,
                )
                for t in SECTION_TYPES.values()
            ],
        )

    @staticmethod
    def _section_read(section: _Section) -> SectionRead:
        return SectionRead(
            id=section.id,
            type=section.doc.type,
            label=section.doc.label,
            slug=section.doc.slug,
            position=section.doc.position,
            enabled=section.doc.enabled,
            content=read_content(section.type, section.doc.content, section.doc.schema_version),
            created_at=section.entity.created_at,
            updated_at=section.entity.updated_at,
        )

    @staticmethod
    def _group_read(entity: BlgEntity) -> GroupRead:
        doc = GroupDoc.model_validate(entity.data)
        return GroupRead(
            id=keys.last_part(entity.sk),
            label=doc.label,
            description=doc.description,
            position=doc.position,
        )

    @staticmethod
    def _item_read(section_id: str, entity: BlgEntity) -> ItemRead:
        doc = ItemDoc.model_validate(entity.data)
        return ItemRead(
            id=keys.last_part(entity.sk),
            section_id=section_id,
            slug=doc.slug,
            title=doc.title,
            date=doc.date,
            excerpt=doc.excerpt,
            tags=doc.tags,
            cover_url=doc.cover_url,
            group_id=doc.group_id,
            status=doc.status,
            position=doc.position,
            size_bytes=doc.size_bytes,
            original_filename=doc.original_filename,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
