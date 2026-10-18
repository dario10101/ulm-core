"""Interfaz (Protocol) del acceso a datos de la practica de ingles.

Lee el banco compartido (solo palabras APPROVED con contenido de su nivel) y
lee/escribe los datos del usuario, siempre filtrando por `user_id`.
"""

from datetime import datetime
from typing import Protocol

from app.db.models.english import (
    EngPractice,
    EngPracticeFeedback,
    EngUserMemory,
    EngUserSettings,
    EngUserWord,
    EngWord,
    EngWordContent,
    EngWordImage,
)


class EnglishPracticeRepository(Protocol):
    # --- Banco (lectura) ---

    def ready_counts_by_level(self) -> dict[str, int]:
        """Palabras APPROVED con contenido de su nivel, por nivel."""
        ...

    def random_new_word(self, level: str, *, user_id: int, exclude: int | None) -> EngWord | None:
        """Una palabra lista del nivel que el usuario nunca practico."""
        ...

    def oldest_practiced_word(
        self, level: str, *, user_id: int, mastered: bool, exclude: int | None
    ) -> EngWord | None:
        """La palabra lista del nivel, ya practicada, con ese `mastered`, que
        hace mas tiempo no sale."""
        ...

    def get_content(self, content_id: int) -> EngWordContent | None: ...

    def content_for(self, word_id: int, level: str) -> EngWordContent | None: ...

    def selected_image(self, word_id: int) -> EngWordImage | None: ...

    def get_word(self, word_id: int) -> EngWord | None: ...

    # --- Usuario ---

    def get_settings(self, *, user_id: int) -> EngUserSettings | None: ...

    def add_settings(self, settings: EngUserSettings) -> None: ...

    def last_practiced_word_id(self, *, user_id: int) -> int | None: ...

    def get_user_word(self, word_id: int, *, user_id: int) -> EngUserWord | None: ...

    def add_user_word(self, user_word: EngUserWord) -> None: ...

    def count_unmastered_ready(self, level: str, *, user_id: int) -> int:
        """Palabras listas del nivel que el usuario todavia no domina (nuevas o
        practicadas sin marcar)."""
        ...

    def add_practice(self, practice: EngPractice) -> None: ...

    def get_practice(self, practice_id: int, *, user_id: int) -> EngPractice | None: ...

    def recent_practices(
        self, level: str, *, user_id: int, limit: int, after: datetime | None
    ) -> list[EngPractice]:
        """Las ultimas `limit` practicas del nivel (mas nueva primero),
        opcionalmente solo las posteriores a `after`."""
        ...

    def get_feedback(self, practice_id: int) -> EngPracticeFeedback | None:
        """Sin user_id: el que llama ya verifico que la practica es del usuario."""
        ...

    def add_feedback(self, feedback: EngPracticeFeedback) -> None: ...

    def get_memory(self, *, user_id: int) -> EngUserMemory | None: ...

    def add_memory(self, memory: EngUserMemory) -> None: ...

    def flush(self) -> None: ...
