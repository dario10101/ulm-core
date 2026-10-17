"""Administracion del blog propio (permiso `blog`, ver PRIVATE_ROUTERS en
app/main.py): config, secciones del menu, contenido de las plantillas,
subsecciones y elementos .md de las colecciones.

La lectura publica (sin sesion) vive aparte, en public_blogs.py.
"""

import re
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, Query, Response, UploadFile

from app.api.deps import get_blog_admin_service, get_current_user_id
from app.api.errors import http_error
from app.core.config import settings
from app.schemas.blog_admin import (
    BlogSettingsRead,
    BlogSettingsWrite,
    GroupCreate,
    GroupRead,
    GroupUpdate,
    ItemRead,
    ItemUpdate,
    OrderWrite,
    SectionCreate,
    SectionOrderWrite,
    SectionRead,
    SectionUpdate,
)
from app.services.blog_admin_service import BlogAdminService
from app.services.errors import DomainError

router = APIRouter(prefix="/blog", tags=["blog"])


# --- Config ---


@router.get("/settings", response_model=BlogSettingsRead)
def read_settings(
    user_id: int = Depends(get_current_user_id),
    service: BlogAdminService = Depends(get_blog_admin_service),
) -> BlogSettingsRead:
    """Config del blog, topes y catalogo de tipos de seccion (para el front)."""
    return service.get_settings(user_id)


@router.put("/settings", response_model=BlogSettingsRead)
def update_settings(
    payload: BlogSettingsWrite,
    user_id: int = Depends(get_current_user_id),
    service: BlogAdminService = Depends(get_blog_admin_service),
) -> BlogSettingsRead:
    try:
        return service.update_settings(user_id, payload)
    except DomainError as exc:
        raise http_error(exc) from exc


# --- Secciones ---


@router.get("/sections", response_model=list[SectionRead])
def list_sections(
    user_id: int = Depends(get_current_user_id),
    service: BlogAdminService = Depends(get_blog_admin_service),
) -> list[SectionRead]:
    """Todas (habilitadas o no), en el orden del menu."""
    return service.list_sections(user_id)


@router.post("/sections", response_model=SectionRead, status_code=201)
def create_section(
    payload: SectionCreate,
    user_id: int = Depends(get_current_user_id),
    service: BlogAdminService = Depends(get_blog_admin_service),
) -> SectionRead:
    try:
        return service.create_section(user_id, payload)
    except DomainError as exc:
        raise http_error(exc) from exc


# Antes que /sections/{section_id}: si no, "order" se tomaria como un id.
@router.put("/sections/order", response_model=list[SectionRead])
def reorder_sections(
    payload: SectionOrderWrite,
    user_id: int = Depends(get_current_user_id),
    service: BlogAdminService = Depends(get_blog_admin_service),
) -> list[SectionRead]:
    try:
        return service.reorder_sections(user_id, payload.ids)
    except DomainError as exc:
        raise http_error(exc) from exc


@router.patch("/sections/{section_id}", response_model=SectionRead)
def update_section(
    section_id: str,
    payload: SectionUpdate,
    user_id: int = Depends(get_current_user_id),
    service: BlogAdminService = Depends(get_blog_admin_service),
) -> SectionRead:
    try:
        return service.update_section(user_id, section_id, payload)
    except DomainError as exc:
        raise http_error(exc) from exc


@router.put("/sections/{section_id}/content", response_model=SectionRead)
def set_section_content(
    section_id: str,
    content: dict[str, Any] = Body(),
    user_id: int = Depends(get_current_user_id),
    service: BlogAdminService = Depends(get_blog_admin_service),
) -> SectionRead:
    """Contenido de la plantilla (formulario). Lo valida el modelo del tipo
    de seccion (app/services/blog_section_types.py): 422 con los campos."""
    try:
        return service.set_section_content(user_id, section_id, content)
    except DomainError as exc:
        raise http_error(exc) from exc


@router.delete("/sections/{section_id}", status_code=204)
def delete_section(
    section_id: str,
    user_id: int = Depends(get_current_user_id),
    service: BlogAdminService = Depends(get_blog_admin_service),
) -> None:
    """Borra tambien sus subsecciones y elementos."""
    try:
        service.delete_section(user_id, section_id)
    except DomainError as exc:
        raise http_error(exc) from exc


# --- Subsecciones ---


@router.get("/sections/{section_id}/groups", response_model=list[GroupRead])
def list_groups(
    section_id: str,
    user_id: int = Depends(get_current_user_id),
    service: BlogAdminService = Depends(get_blog_admin_service),
) -> list[GroupRead]:
    try:
        return service.list_groups(user_id, section_id)
    except DomainError as exc:
        raise http_error(exc) from exc


@router.post("/sections/{section_id}/groups", response_model=GroupRead, status_code=201)
def create_group(
    section_id: str,
    payload: GroupCreate,
    user_id: int = Depends(get_current_user_id),
    service: BlogAdminService = Depends(get_blog_admin_service),
) -> GroupRead:
    try:
        return service.create_group(user_id, section_id, payload)
    except DomainError as exc:
        raise http_error(exc) from exc


@router.put("/sections/{section_id}/groups/order", response_model=list[GroupRead])
def reorder_groups(
    section_id: str,
    payload: OrderWrite,
    user_id: int = Depends(get_current_user_id),
    service: BlogAdminService = Depends(get_blog_admin_service),
) -> list[GroupRead]:
    """Todas las subsecciones de la seccion, exactamente una vez (si no, 422)."""
    try:
        return service.reorder_groups(user_id, section_id, payload.ids)
    except DomainError as exc:
        raise http_error(exc) from exc


@router.patch("/sections/{section_id}/groups/{group_id}", response_model=GroupRead)
def update_group(
    section_id: str,
    group_id: str,
    payload: GroupUpdate,
    user_id: int = Depends(get_current_user_id),
    service: BlogAdminService = Depends(get_blog_admin_service),
) -> GroupRead:
    try:
        return service.update_group(user_id, section_id, group_id, payload)
    except DomainError as exc:
        raise http_error(exc) from exc


@router.delete("/sections/{section_id}/groups/{group_id}", status_code=204)
def delete_group(
    section_id: str,
    group_id: str,
    user_id: int = Depends(get_current_user_id),
    service: BlogAdminService = Depends(get_blog_admin_service),
) -> None:
    """Sus elementos quedan en la seccion, sin subseccion."""
    try:
        service.delete_group(user_id, section_id, group_id)
    except DomainError as exc:
        raise http_error(exc) from exc


# --- Elementos (.md) ---


@router.get("/sections/{section_id}/items", response_model=list[ItemRead])
def list_items(
    section_id: str,
    user_id: int = Depends(get_current_user_id),
    service: BlogAdminService = Depends(get_blog_admin_service),
) -> list[ItemRead]:
    try:
        return service.list_items(user_id, section_id)
    except DomainError as exc:
        raise http_error(exc) from exc


@router.post("/sections/{section_id}/items", response_model=ItemRead, status_code=201)
def upload_item(
    section_id: str,
    response: Response,
    file: UploadFile = File(),
    group_id: str | None = Form(default=None, max_length=40),
    replace: bool = Query(default=False),
    user_id: int = Depends(get_current_user_id),
    service: BlogAdminService = Depends(get_blog_admin_service),
) -> ItemRead:
    """Sube un .md (multipart). Nuevo: 201. Slug existente: 409, salvo
    `?replace=true`, que lo reemplaza y responde 200. Queda en borrador."""
    # Un byte de mas alcanza para saber que se paso del tope sin leer todo.
    raw = file.file.read(settings.blog_max_md_bytes + 1)
    try:
        item, created = service.upload_item(
            user_id,
            section_id,
            filename=file.filename,
            raw=raw,
            replace=replace,
            group_id=group_id or None,
        )
    except DomainError as exc:
        raise http_error(exc) from exc
    if not created:
        response.status_code = 200
    return item


@router.put("/sections/{section_id}/items/order", response_model=list[ItemRead])
def reorder_items(
    section_id: str,
    payload: OrderWrite,
    user_id: int = Depends(get_current_user_id),
    service: BlogAdminService = Depends(get_blog_admin_service),
) -> list[ItemRead]:
    """Orden manual de los elementos: todos, exactamente una vez (si no, 422)."""
    try:
        return service.reorder_items(user_id, section_id, payload.ids)
    except DomainError as exc:
        raise http_error(exc) from exc


@router.patch("/sections/{section_id}/items/{item_id}", response_model=ItemRead)
def update_item(
    section_id: str,
    item_id: str,
    payload: ItemUpdate,
    user_id: int = Depends(get_current_user_id),
    service: BlogAdminService = Depends(get_blog_admin_service),
) -> ItemRead:
    try:
        return service.update_item(user_id, section_id, item_id, payload)
    except DomainError as exc:
        raise http_error(exc) from exc


@router.delete("/sections/{section_id}/items/{item_id}", status_code=204)
def delete_item(
    section_id: str,
    item_id: str,
    user_id: int = Depends(get_current_user_id),
    service: BlogAdminService = Depends(get_blog_admin_service),
) -> None:
    try:
        service.delete_item(user_id, section_id, item_id)
    except DomainError as exc:
        raise http_error(exc) from exc


@router.get("/sections/{section_id}/items/{item_id}/download")
def download_item(
    section_id: str,
    item_id: str,
    user_id: int = Depends(get_current_user_id),
    service: BlogAdminService = Depends(get_blog_admin_service),
) -> Response:
    """El .md original, tal cual se subio."""
    try:
        filename, content = service.download_item(user_id, section_id, item_id)
    except DomainError as exc:
        raise http_error(exc) from exc
    # El nombre va en una cabecera: solo caracteres seguros (sin comillas ni
    # saltos de linea que permitan inyectar otra cabecera).
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename) or "documento.md"
    return Response(
        content=content.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )
