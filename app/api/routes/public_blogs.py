"""Blogs publicos: se leen sin sesion (va en PUBLIC_ROUTERS de app/main.py)."""

from fastapi import APIRouter, Depends

from app.api.deps import get_blog_service
from app.api.errors import http_error
from app.schemas.blog import PublicBlogRead
from app.services.blog_service import BlogService
from app.services.errors import BlogNotFoundError

router = APIRouter(prefix="/public/blogs", tags=["public-blogs"])


@router.get("/{username}", response_model=PublicBlogRead)
def read_public_blog(
    username: str,
    service: BlogService = Depends(get_blog_service),
) -> PublicBlogRead:
    try:
        owner = service.get_public_owner(username)
    except BlogNotFoundError as exc:
        raise http_error(exc) from exc
    # get_public_owner solo devuelve usuarios con username.
    assert owner.username is not None
    return PublicBlogRead(username=owner.username)
