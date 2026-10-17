"""Interfaz (Protocol) del acceso al banco compartido de ingles.

Sin user_id: el banco es de toda la app (D14) y solo lo escribe el admin.
"""

from collections.abc import Sequence
from typing import Protocol

from app.db.models.english import EngWord, EngWordContent, EngWordImage


class EnglishBankRepository(Protocol):
    def existing_lemmas(self) -> set[str]: ...

    def add_word(self, word: EngWord) -> None: ...

    def count_by_status(self, level: str) -> dict[str, int]:
        """Palabras del nivel por estado (solo los estados con alguna)."""
        ...

    def processable_words(self, level: str, *, max_attempts: int, limit: int) -> list[EngWord]:
        """PENDING, o REVIEW con menos de `max_attempts` intentos, por id."""
        ...

    def get_word(self, word_id: int) -> EngWord | None: ...

    def list_words(
        self, level: str, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[EngWord], int]:
        """Pagina de palabras del nivel (por lemma) y el total del filtro."""
        ...

    def images_of(self, word_id: int) -> list[EngWordImage]:
        """Por `position`."""
        ...

    def selected_images(self, word_ids: Sequence[int]) -> dict[int, EngWordImage]: ...

    def add_image(self, image: EngWordImage) -> None: ...

    def get_content(self, word_id: int, level: str) -> EngWordContent | None: ...

    def content_word_ids(self, word_ids: Sequence[int], level: str) -> set[int]: ...

    def add_content(self, content: EngWordContent) -> None: ...

    def flush(self) -> None: ...
