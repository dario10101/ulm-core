"""Prompt, esquema y validacion del feedback de una practica (ENGLISH-TEACHER-PLAN.md, 7.2).

Una sola llamada stateless hace el feedback y reescribe la memoria del
usuario (`memory_update`): en vez de historial de chat, el LLM recibe un
resumen acotado de practicas anteriores. Lo calculable (diff de la lectura)
ya va resuelto en el prompt: el LLM opina, no cuenta.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.db.models.english import EngPractice, EngWord, EngWordContent
from app.services.english_levels import EnglishLevel
from app.services.english_reading_diff import compare_reading

SPANISH_LEVELS = {EnglishLevel.A1, EnglishLevel.A2}
MEMORY_MAX_CHARS = 600


class Correction(BaseModel):
    original: str
    corrected: str
    explanation: str


class FeedbackResponse(BaseModel):
    summary: str
    vocabulary: str
    # Default: los feedbacks guardados antes del dictado no lo tienen.
    dictation: str = ""
    writing_corrections: list[Correction]
    reading_observations: list[str]
    speaking_corrections: list[Correction]
    answered_question: bool
    tips: list[str] = Field(max_length=5)
    memory_update: str


def response_schema() -> dict[str, Any]:
    correction = {
        "type": "object",
        "additionalProperties": False,
        "required": ["original", "corrected", "explanation"],
        "properties": {
            "original": {"type": "string"},
            "corrected": {"type": "string"},
            "explanation": {"type": "string"},
        },
    }
    strings = {"type": "array", "items": {"type": "string"}}
    return {
        "title": "english_practice_feedback",
        "type": "object",
        "additionalProperties": False,
        "required": list(FeedbackResponse.model_fields),
        "properties": {
            "summary": {"type": "string"},
            "vocabulary": {"type": "string"},
            "dictation": {"type": "string"},
            "writing_corrections": {"type": "array", "items": correction},
            "reading_observations": strings,
            "speaking_corrections": {"type": "array", "items": correction},
            "answered_question": {"type": "boolean"},
            "tips": strings,
            "memory_update": {"type": "string"},
        },
    }


def build_instructions(level: EnglishLevel) -> str:
    language = "Spanish" if level in SPANISH_LEVELS else "English"
    return (
        f"You are a kind but honest English teacher. The learner is at CEFR level {level.value} "
        "and speaks Spanish. Review one practice session and return JSON per the schema.\n"
        f"Write summary, vocabulary, explanations, observations and tips in {language}; "
        "keep 'original' and 'corrected' in English.\n"
        "- summary: 1-2 sentences on how it went.\n"
        "- vocabulary: one short comment on the vocabulary step.\n"
        "- dictation: one short comment on the dictation (writing the sentence they heard), "
        "based on its word diff: words missed by ear or misspelled. Empty string if none.\n"
        "- writing_corrections: real mistakes in the written answer only (grammar, word choice, "
        "spelling). Empty list if there are none. Do not rewrite correct sentences.\n"
        "- reading_observations: based ONLY on the word diff given (missing or changed words). "
        "The transcript comes from speech recognition: it may hide pronunciation mistakes, so "
        "never claim the pronunciation was right or wrong.\n"
        "- speaking_corrections: mistakes in the free speaking transcript (grammar, word choice). "
        "Ignore filler words like 'umm'.\n"
        "- answered_question: whether the free speaking answers the question.\n"
        "- tips: 1-3 concrete tips, prioritising mistakes that also appear in the memory.\n"
        f"- memory_update: the new learner memory, max {MEMORY_MAX_CHARS} characters, in English: "
        "recurring mistakes and strengths, merging the previous memory with this session. "
        "It is the only thing remembered for future sessions."
    )


def _diff_summary(expected: str, actual: str | None, missing: str) -> str:
    if not actual:
        return missing
    diff = compare_reading(expected, actual)
    problems = [
        f"{op.kind}: expected '{' '.join(op.expected)}' said '{' '.join(op.said)}'"
        for op in diff.ops
        if op.kind != "equal"
    ]
    return f"match {diff.match_pct}%; " + ("; ".join(problems) if problems else "no differences")


def build_prompt(
    practice: EngPractice, word: EngWord, content: EngWordContent, memory: str | None
) -> str:
    vocabulary = (
        "revealed the word (did not know it)"
        if practice.vocab_revealed
        else "guessed a synonym"
        if practice.vocab_used_synonym
        else "wrote it correctly"
    )
    listening = "needed to read the text" if practice.listening_text_shown else "understood by ear"
    speaking = (
        "skipped (no microphone)"
        if practice.speaking_skipped
        else practice.free_transcript or "(nothing said)"
    )
    dictation_diff = _diff_summary(
        content.listening_sentence, practice.dictation_text, "(no dictation)"
    )
    reading_diff = _diff_summary(
        content.reading_text, practice.reading_transcript, "(no reading recording)"
    )
    return (
        f"Previous learner memory: {memory or '(none yet)'}\n\n"
        f"Target word: {word.lemma} ({word.pos}). Vocabulary step: {vocabulary}.\n"
        f"Listening sentence: {content.listening_sentence}\n"
        f"Listening: {listening}.\n"
        f"Dictation (wrote the listening sentence): {practice.dictation_text or '(none)'}\n"
        f"Dictation diff: {dictation_diff}\n"
        f"Writing task: {content.writing_prompt}\n"
        f"Written answer: {practice.writing_text}\n"
        f"Reading text: {content.reading_text}\n"
        f"Reading transcript: {practice.reading_transcript or '(none)'}\n"
        f"Reading diff: {reading_diff}\n"
        f"Question to answer by speaking: {content.reading_question}\n"
        f"Free speaking transcript: {speaking}"
    )
