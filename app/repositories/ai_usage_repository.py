"""Interfaz (Protocol) del registro de consumo de IA (ai_usage_events)."""

from typing import Protocol

from app.db.models.ai_usage import AiUsageEvent


class AiUsageRepository(Protocol):
    def add(self, event: AiUsageEvent) -> None: ...
