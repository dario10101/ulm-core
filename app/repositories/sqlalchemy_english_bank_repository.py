"""Implementacion del EnglishBankRepository sobre SQLAlchemy/Postgres."""

from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models.english import (
    WORD_PENDING,
    WORD_REVIEW,
    EngWord,
    EngWordContent,
    EngWordImage,
)


class SqlAlchemyEnglishBankRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def existing_lemmas(self) -> set[str]:
        return set(self._db.execute(select(EngWord.lemma)).scalars().all())

    def add_word(self, word: EngWord) -> None:
        self._db.add(word)

    def count_by_status(self, level: str) -> dict[str, int]:
        rows = self._db.execute(
            select(EngWord.status, func.count())
            .where(EngWord.cefr_level == level)
            .group_by(EngWord.status)
        ).all()
        return {status: count for status, count in rows}

    def processable_words(self, level: str, *, max_attempts: int, limit: int) -> list[EngWord]:
        return list(
            self._db.execute(
                select(EngWord)
                .where(
                    EngWord.cefr_level == level,
                    or_(
                        EngWord.status == WORD_PENDING,
                        (EngWord.status == WORD_REVIEW) & (EngWord.fill_attempts < max_attempts),
                    ),
                )
                .order_by(EngWord.id)
                .limit(limit)
            )
            .scalars()
            .all()
        )

    def get_word(self, word_id: int) -> EngWord | None:
        return self._db.get(EngWord, word_id)

    def list_words(
        self, level: str, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[EngWord], int]:
        query = select(EngWord).where(EngWord.cefr_level == level)
        if status is not None:
            query = query.where(EngWord.status == status)
        total = self._db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
        words = (
            self._db.execute(query.order_by(EngWord.lemma).offset(offset).limit(limit))
            .scalars()
            .all()
        )
        return list(words), total

    def images_of(self, word_id: int) -> list[EngWordImage]:
        return list(
            self._db.execute(
                select(EngWordImage)
                .where(EngWordImage.word_id == word_id)
                .order_by(EngWordImage.position)
            )
            .scalars()
            .all()
        )

    def selected_images(self, word_ids: Sequence[int]) -> dict[int, EngWordImage]:
        if not word_ids:
            return {}
        images = self._db.execute(
            select(EngWordImage).where(
                EngWordImage.word_id.in_(word_ids), EngWordImage.selected.is_(True)
            )
        ).scalars()
        return {image.word_id: image for image in images}

    def add_image(self, image: EngWordImage) -> None:
        self._db.add(image)

    def get_content(self, word_id: int, level: str) -> EngWordContent | None:
        return self._db.execute(
            select(EngWordContent).where(
                EngWordContent.word_id == word_id, EngWordContent.level == level
            )
        ).scalar_one_or_none()

    def content_word_ids(self, word_ids: Sequence[int], level: str) -> set[int]:
        if not word_ids:
            return set()
        return set(
            self._db.execute(
                select(EngWordContent.word_id).where(
                    EngWordContent.word_id.in_(word_ids), EngWordContent.level == level
                )
            )
            .scalars()
            .all()
        )

    def add_content(self, content: EngWordContent) -> None:
        self._db.add(content)

    def flush(self) -> None:
        self._db.flush()
