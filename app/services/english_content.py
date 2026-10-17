"""Generacion y validacion del contenido del banco (ENGLISH-TEACHER-PLAN.md, 7.1).

Funciones puras: armar el prompt y el esquema de un lote de palabras, y validar
lo que devuelve el LLM antes de guardarlo. El LLM redacta; lo verificable
(contiene la palabra, empieza con la frase del listening, termina en
pregunta, largos del nivel) lo comprueba el codigo.
"""

import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.services.english_levels import EnglishLevel, LevelConfig, level_config

# Subirla cuando cambie el prompt: queda guardada con cada contenido.
PROMPT_VERSION = 1

SPANISH_LEVELS = {EnglishLevel.A1, EnglishLevel.A2}


class GeneratedItem(BaseModel):
    word: str
    accepted_answers: list[str]
    listening_sentence: str
    writing_prompt: str
    writing_prompt_es: str
    reading_text: str


class GeneratedBatch(BaseModel):
    items: list[GeneratedItem]


@dataclass(frozen=True)
class ValidContent:
    listening_sentence: str
    writing_prompt: str
    writing_prompt_es: str | None
    reading_text: str
    reading_question: str


def response_schema() -> dict[str, Any]:
    """Esquema estricto de salida estructurada: todos los campos requeridos y
    sin propiedades extra (lo exige el modo strict de OpenAI)."""
    item = {
        "type": "object",
        "additionalProperties": False,
        "required": list(GeneratedItem.model_fields),
        "properties": {
            "word": {"type": "string"},
            "accepted_answers": {"type": "array", "items": {"type": "string"}},
            "listening_sentence": {"type": "string"},
            "writing_prompt": {"type": "string"},
            "writing_prompt_es": {"type": "string"},
            "reading_text": {"type": "string"},
        },
    }
    return {
        "title": "english_bank_batch",
        "type": "object",
        "additionalProperties": False,
        "required": ["items"],
        "properties": {"items": {"type": "array", "items": item}},
    }


def build_instructions(level: EnglishLevel) -> str:
    config = level_config(level)
    lo, hi = config.listening_words
    sentences_lo, sentences_hi = config.reading_sentences
    spanish = (
        "writing_prompt_es: the writing_prompt translated to Spanish."
        if level in SPANISH_LEVELS
        else 'writing_prompt_es: always an empty string "".'
    )
    return (
        f"You write English practice content for Spanish-speaking learners at CEFR level "
        f"{level.value}. Use only vocabulary and grammar appropriate for {level.value}. "
        "For each word in the input, return one item with:\n"
        "- word: the input word, unchanged.\n"
        "- accepted_answers: other English words that name the same picture equally well "
        "(close synonyms and British/American spelling variants). May be empty.\n"
        f"- listening_sentence: one natural sentence of {lo}-{hi} words that contains the word "
        "exactly as given (a plural or verb ending is allowed only if needed).\n"
        "- writing_prompt: a short, specific instruction in English asking the learner to answer "
        "or react to the listening_sentence in writing.\n"
        f"- {spanish}\n"
        f"- reading_text: {sentences_lo}-{sentences_hi} sentences in total. It must start with "
        "the listening_sentence copied verbatim, continue the same topic with new sentences, "
        "and end with one question addressed to the reader, ending with '?'.\n"
        "Return the items in the same order as the input words."
    )


def build_prompt(words: list[tuple[str, str]]) -> str:
    """`words`: (palabra, categoria gramatical)."""
    return "Words:\n" + "\n".join(f"- {lemma} ({pos})" for lemma, pos in words)


# --- Validacion ---

_TOKEN = re.compile(r"[a-z]+(?:'[a-z]+)?")
_SENTENCE_END = re.compile(r"[.!?]+(?=\s|$)")


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def inflections(lemma: str) -> set[str]:
    """Formas regulares aceptadas en la frase (plural, -ed, -ing, 3a persona).
    Los irregulares (go -> went) no estan: el prompt pide la forma dada."""
    forms = {lemma, lemma + "s", lemma + "es", lemma + "ed", lemma + "d", lemma + "ing"}
    if lemma.endswith("e"):
        forms.add(lemma[:-1] + "ing")
    if lemma.endswith("y"):
        forms |= {lemma[:-1] + "ies", lemma[:-1] + "ied"}
    forms |= {lemma + lemma[-1] + "ed", lemma + lemma[-1] + "ing"}
    return forms


def contains_word(sentence: str, lemma: str) -> bool:
    if " " in lemma or "-" in lemma:
        return lemma in _normalize(sentence.lower())
    forms = inflections(lemma)
    return any(token in forms for token in _tokens(sentence))


def count_sentences(text: str) -> int:
    return len([part for part in _SENTENCE_END.split(text) if part.strip()])


def last_sentence(text: str) -> str:
    """La pregunta final del texto de lectura."""
    parts = re.split(r"(?<=[.!?])\s+", _normalize(text))
    return parts[-1] if parts else ""


def filter_accepted_answers(lemma: str, candidates: list[str]) -> list[str]:
    """Solo los que se pueden escribir en las casillas de `lemma` (D30): mismo
    largo y espacios/guiones en las mismas posiciones."""
    pattern = [ch if not ch.isalpha() else None for ch in lemma]
    accepted = []
    for raw in candidates:
        candidate = raw.strip().lower()
        if candidate == lemma or candidate in accepted or len(candidate) != len(lemma):
            continue
        shape = [ch if not ch.isalpha() else None for ch in candidate]
        if shape == pattern and all(ch.isalpha() or ch in " -" for ch in candidate):
            accepted.append(candidate)
    return accepted


def validate_item(item: GeneratedItem, lemma: str, config: LevelConfig) -> ValidContent | str:
    """El contenido listo para guardar, o el motivo por el que no sirve."""
    listening = _normalize(item.listening_sentence)
    reading = _normalize(item.reading_text)
    if not contains_word(listening, lemma):
        return "word_missing_in_sentence"
    lo, hi = config.listening_words
    # Tolerancia: el LLM cuenta mal las palabras y un rango estricto mandaria
    # media lista a revision por una palabra de mas.
    if not lo - 2 <= len(listening.split()) <= hi + 3:
        return "listening_length"
    if not reading.lower().startswith(listening.lower()):
        return "reading_does_not_start_with_listening"
    if not reading.endswith("?"):
        return "reading_without_final_question"
    sentences_lo, sentences_hi = config.reading_sentences
    if not sentences_lo - 1 <= count_sentences(reading) <= sentences_hi + 1:
        return "reading_length"
    if not item.writing_prompt.strip():
        return "empty_writing_prompt"
    spanish = item.writing_prompt_es.strip() or None
    if config.level in SPANISH_LEVELS and spanish is None:
        return "missing_spanish_prompt"
    return ValidContent(
        listening_sentence=listening,
        writing_prompt=item.writing_prompt.strip(),
        writing_prompt_es=spanish if config.level in SPANISH_LEVELS else None,
        reading_text=reading,
        reading_question=last_sentence(reading),
    )
