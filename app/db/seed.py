"""Datos semilla que la app necesita para funcionar (ej. el usuario quemado)."""

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.user import User


def ensure_default_user(db: Session) -> User:
    """Get-or-create idempotente del usuario quemado (sin auth todavia)."""
    user = db.get(User, settings.default_user_id)
    if user is not None:
        return user

    user = User(
        id=settings.default_user_id,
        name=settings.default_user_name,
        email=settings.default_user_email,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
