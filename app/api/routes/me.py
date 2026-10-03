"""Datos del usuario logueado."""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.db.models.user import User
from app.schemas.user import MeRead

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=MeRead)
def read_me(user: User = Depends(get_current_user)) -> User:
    return user
