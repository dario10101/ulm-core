"""Blogs publicos: se leen sin sesion (va en PUBLIC_ROUTERS de app/main.py).

Todas las respuestas 200 llevan cache HTTP (app/api/http_cache.py). Las reglas
de visibilidad y el 404 uniforme viven en BlogService.
"""

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import get_blog_service
from app.api.errors import http_error
from app.api.http_cache import cached_json
from app.schemas.blog import PublicBlogRead, PublicCollectionRead, PublicItemRead
from app.services.blog_service import BlogService
from app.services.errors import BlogNotFoundError

router = APIRouter(prefix="/public/blogs", tags=["public-blogs"])


@router.get("/{username}", response_model=PublicBlogRead)
def read_public_blog(
    username: str,
    request: Request,
    service: BlogService = Depends(get_blog_service),
) -> Response:
    """Dueño + secciones habilitadas con su contenido: todo el menu y las
    plantillas en un solo request."""
    try:
        return cached_json(request, service.get_public_blog(username))
    except BlogNotFoundError as exc:
        raise http_error(exc) from exc


@router.get("/{username}/{section}/items", response_model=PublicCollectionRead)
def read_public_collection(
    username: str,
    section: str,
    request: Request,
    service: BlogService = Depends(get_blog_service),
) -> Response:
    """Subsecciones y elementos publicados de una coleccion, sin cuerpos."""
    try:
        return cached_json(request, service.get_public_collection(username, section))
    except BlogNotFoundError as exc:
        raise http_error(exc) from exc


@router.get("/{username}/{section}/items/{item}", response_model=PublicItemRead)
def read_public_item(
    username: str,
    section: str,
    item: str,
    request: Request,
    service: BlogService = Depends(get_blog_service),
) -> Response:
    try:
        return cached_json(request, service.get_public_item(username, section, item))
    except BlogNotFoundError as exc:
        raise http_error(exc) from exc
