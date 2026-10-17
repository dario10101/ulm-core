"""Implementacion del EnglishPracticeRepository sobre SQLAlchemy/Postgres."""

from datetime import datetime

from sqlalchemy import and_, exists, func, select
from sqlalchemy.orm import Session

from app.db.models.english import (
    WORD_APPROVED,
    EngPractice,
    EngUserSettings,
    EngUserWord,
    EngWord,
    EngWordContent,
    EngWordImage,
)


def _ready(level: str):
    """Condicion de "lista para practicar": APPROVED, del nivel y con contenido
    de ese nivel (una aprobada a mano sin contenido no deberia existir, pero el
    filtro no depende de eso)."""
    has_content = exists().where(
        EngWordContent.word_id == EngWord.id, EngWordContent.level == level
    )
    return and_(EngWord.status == WORD_APPROVED, EngWord.cefr_level == level, has_content)


class SqlAlchemyEnglishPracticeRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    # --- Banco ---

    def ready_counts_by_level(self) -> dict[str, int]:
        rows = self._db.execute(
            select(EngWord.cefr_level, func.count(EngWord.id))
            .join(
                EngWordContent,
                and_(
                    EngWordContent.word_id == EngWord.id,
                    EngWordContent.level == EngWord.cefr_level,
                ),
            )
            .where(EngWord.status == WORD_APPROVED)
            .group_by(EngWord.cefr_level)
        ).all()
        return {level: count for level, count in rows}

    def random_new_word(self, level: str, *, user_id: int, exclude: int | None) -> EngWord | None:
        practiced = exists().where(
            EngUserWord.word_id == EngWord.id, EngUserWord.user_id == user_id
        )
        query = select(EngWord).where(_ready(level), ~practiced)
        if exclude is not None:
            query = query.where(EngWord.id != exclude)
        # random() existe en Postgres y en SQLite. Con miles de filas un
        # ORDER BY random() es aceptable; con millones habria que muestrear.
        return self._db.execute(query.order_by(func.random()).limit(1)).scalar_one_or_none()

    def oldest_practiced_word(
        self, level: str, *, user_id: int, mastered: bool, exclude: int | None
    ) -> EngWord | None:
        query = (
            select(EngWord)
            .join(EngUserWord, EngUserWord.word_id == EngWord.id)
            .where(_ready(level), EngUserWord.user_id == user_id, EngUserWord.mastered == mastered)
        )
        if exclude is not None:
            query = query.where(EngWord.id != exclude)
        return self._db.execute(
            query.order_by(EngUserWord.last_practiced_at, EngWord.id).limit(1)
        ).scalar_one_or_none()

    def get_content(self, content_id: int) -> EngWordContent | None:
        return self._db.get(EngWordContent, content_id)

    def content_for(self, word_id: int, level: str) -> EngWordContent | None:
        return self._db.execute(
            select(EngWordContent).where(
                EngWordContent.word_id == word_id, EngWordContent.level == level
            )
        ).scalar_one_or_none()

    def selected_image(self, word_id: int) -> EngWordImage | None:
        return self._db.execute(
            select(EngWordImage).where(
                EngWordImage.word_id == word_id, EngWordImage.selected.is_(True)
            )
        ).scalar_one_or_none()

    def get_word(self, word_id: int) -> EngWord | None:
        return self._db.get(EngWord, word_id)

    # --- Usuario ---

    def get_settings(self, *, user_id: int) -> EngUserSettings | None:
        return self._db.get(EngUserSettings, user_id)

    def add_settings(self, settings: EngUserSettings) -> None:
        self._db.add(settings)

    def last_practiced_word_id(self, *, user_id: int) -> int | None:
        return self._db.execute(
            select(EngPractice.word_id)
            .where(EngPractice.user_id == user_id)
            .order_by(EngPractice.completed_at.desc(), EngPractice.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    def get_user_word(self, word_id: int, *, user_id: int) -> EngUserWord | None:
        return self._db.get(EngUserWord, (user_id, word_id))

    def add_user_word(self, user_word: EngUserWord) -> None:
        self._db.add(user_word)

    def count_unmastered_ready(self, level: str, *, user_id: int) -> int:
        mastered = exists().where(
            EngUserWord.word_id == EngWord.id,
            EngUserWord.user_id == user_id,
            EngUserWord.mastered.is_(True),
        )
        return self._db.execute(
            select(func.count(EngWord.id)).where(_ready(level), ~mastered)
        ).scalar_one()

    def add_practice(self, practice: EngPractice) -> None:
        self._db.add(practice)

    def get_practice(self, practice_id: int, *, user_id: int) -> EngPractice | None:
        return self._db.execute(
            select(EngPractice).where(EngPractice.id == practice_id, EngPractice.user_id == user_id)
        ).scalar_one_or_none()

    def recent_practices(
        self, level: str, *, user_id: int, limit: int, after: datetime | None
    ) -> list[EngPractice]:
        query = select(EngPractice).where(
            EngPractice.user_id == user_id, EngPractice.level == level
        )
        if after is not None:
            query = query.where(EngPractice.completed_at > after)
        return list(
            self._db.execute(
                query.order_by(EngPractice.completed_at.desc(), EngPractice.id.desc()).limit(limit)
            )
            .scalars()
            .all()
        )

    def flush(self) -> None:
        self._db.flush()
