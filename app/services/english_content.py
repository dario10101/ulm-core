"""Generacion y validacion del contenido del banco (ENGLISH-TEACHER-PLAN.md, 7.1).

Funciones puras: armar el prompt y el esquema de un lote de palabras, y validar
lo que devuelve el LLM antes de guardarlo. El LLM redacta; lo verificable
(contiene la palabra, empieza con la frase del listening, termina en
pregunta, largos del nivel) lo comprueba el codigo.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.services.english_levels import EnglishLevel, LevelConfig, level_config

# Subirla cuando cambie el prompt: queda guardada con cada contenido.
PROMPT_VERSION = 2  # 2: agrega la pista del vocabulario (hint)

SPANISH_LEVELS = {EnglishLevel.A1, EnglishLevel.A2}

# Pista corta: una frase, no un parrafo.
HINT_MAX_CHARS = 120


class GeneratedItem(BaseModel):
    word: str
    accepted_answers: list[str]
    listening_sentence: str
    writing_prompt: str
    writing_prompt_es: str
    reading_text: str
    hint: str
    # Solo para validar que la pista no regale la traduccion; no se guarda.
    translation_es: str


class GeneratedBatch(BaseModel):
    items: list[GeneratedItem]


@dataclass(frozen=True)
class ValidContent:
    listening_sentence: str
    writing_prompt: str
    writing_prompt_es: str | None
    reading_text: str
    reading_question: str
    hint: str


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
            "hint": {"type": "string"},
            "translation_es": {"type": "string"},
        },
    }
    return {
        "title": "english_bank_batch",
        "type": "object",
        "additionalProperties": False,
        "required": ["items"],
        "properties": {"items": {"type": "array", "items": item}},
    }


def hint_instruction(level: EnglishLevel) -> str:
    """Regla de la pista del vocabulario. En A1-A2 va en español: en ingles,
    la pista usaria palabras mas dificiles que la que hay que adivinar."""
    language = "Spanish" if level in SPANISH_LEVELS else "simple English"
    return (
        f"hint: one short clue in {language} (max {HINT_MAX_CHARS} characters) that helps to "
        "guess the word from its picture: what it is, what it is used for or where it is found. "
        "It must NOT contain the word, any synonym, or its Spanish translation.\n"
        "- translation_es: the most common Spanish translation of the word (only used to "
        "check the hint; never shown to the learner)."
    )


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
        f"- {hint_instruction(level)}\n"
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


def _plain(text: str) -> str:
    """Minusculas y sin tildes: "Cámara" y "camara" cuentan igual."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def contains_translation(hint: str, translation: str) -> bool:
    """La pista contiene alguna palabra (4+ letras) de la traduccion, o su plural.
    Las cortas ("de", "la") quedan fuera: aparecen en cualquier pista."""
    hint_words = set(re.findall(r"[a-z]+", _plain(hint)))
    for word in re.findall(r"[a-z]+", _plain(translation)):
        if len(word) >= 4 and hint_words & {word, word + "s", word + "es"}:
            return True
    return False


def validate_hint(hint: str, lemma: str, synonyms: list[str], translation: str = "") -> str | None:
    """Motivo por el que la pista no sirve, o None: vacia, larga, o que regala
    la palabra (en ingles) o su traduccion al español. La traduccion la da el
    mismo LLM: si se equivoca, la pista mala se cura en la curacion."""
    clean = _normalize(hint)
    if not clean:
        return "empty_hint"
    if len(clean) > HINT_MAX_CHARS:
        return "hint_too_long"
    for word in [lemma, *synonyms]:
        if word.strip() and contains_word(clean, word.strip().lower()):
            return "hint_contains_word"
    if translation.strip() and contains_translation(clean, translation):
        return "hint_contains_translation"
    return None


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
    hint_problem = validate_hint(item.hint, lemma, item.accepted_answers, item.translation_es)
    if hint_problem:
        return hint_problem
    return ValidContent(
        listening_sentence=listening,
        writing_prompt=item.writing_prompt.strip(),
        writing_prompt_es=spanish if config.level in SPANISH_LEVELS else None,
        reading_text=reading,
        reading_question=last_sentence(reading),
        hint=_normalize(item.hint),
    )
