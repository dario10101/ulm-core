"""Esquemas Pydantic del modulo English (ENGLISH-TEACHER-PLAN.md, seccion 8)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.services.english_levels import EnglishLevel

# --- Banco (admin, /system/english) ---


class EnglishLevelBankRead(BaseModel):
    level: EnglishLevel
    list_total: int
    imported: int
    approved: int
    review: int
    pending: int
    disabled: int
    processable: int
    full: bool


class EnglishImportRead(BaseModel):
    added: int


class EnglishFillProgressRead(BaseModel):
    processed: int
    approved: int
    sent_to_review: int
    remaining: int


class EnglishImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    url: str
    source: str
    license: str
    attribution: str
    page_url: str | None


class EnglishWordAdminRead(BaseModel):
    id: int
    lemma: str
    pos: str
    level: EnglishLevel
    status: str
    status_reason: str | None
    accepted_answers: list[str]
    image: EnglishImageRead | None
    has_content: bool


class EnglishWordPageRead(BaseModel):
    items: list[EnglishWordAdminRead]
    total: int


class EnglishWordStatusWrite(BaseModel):
    status: Literal["APPROVED", "DISABLED"]
