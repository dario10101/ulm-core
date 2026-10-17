"""Lectura de las listas de vocabulario por nivel (CEFR-J + Octanove).

Los CSV van sin modificar en app/data/english (ver su README: licencias y
citas). Aca se filtran segun ENGLISH-TEACHER-PLAN.md:
- D28: solo sustantivos, verbos y adjetivos, escritos en minusculas (descarta
  abreviaturas y nombres propios como "TV" o "AM").
- D29: una entrada por palabra; con varias categorias gana sustantivo > verbo
  > adjetivo, y el nivel es el menor en que aparece.

El orden dentro de cada nivel es un hash de la palabra: deterministico (cada
"Fill bank" toma las siguientes, siempre las mismas) pero sin el sesgo
alfabetico de la lista original (si no, el primer banco serian todas palabras
con "a").
"""

import csv
import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.services.english_levels import LEVEL_ORDER, EnglishLevel

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "english"
SOURCES = (
    ("cefrj", "cefrj-vocabulary-profile-1.5.csv"),
    ("octanove", "octanove-vocabulary-profile-c1c2-1.0.csv"),
)

# Prioridad de categoria (D29): la primera es la mas facil de dibujar.
POS_PRIORITY = ("noun", "verb", "adjective")

# Letras minusculas, con espacios o guiones entre partes ("ice cream", "t-shirt").
WORD_PATTERN = re.compile(r"^[a-z]+(?:[ -][a-z]+)*$")
MIN_LENGTH = 3
MAX_LENGTH = 20


@dataclass(frozen=True)
class WordListEntry:
    lemma: str
    pos: str
    level: EnglishLevel
    # Otras formas de la misma entrada en la lista (ej. "grey" en "gray/grey").
    variants: tuple[str, ...]
    source: str


def _valid_form(form: str) -> bool:
    return bool(WORD_PATTERN.match(form)) and MIN_LENGTH <= len(form) <= MAX_LENGTH


def _order_key(lemma: str) -> str:
    return hashlib.sha1(lemma.encode()).hexdigest()


def parse_rows(rows: list[tuple[str, str, str, str]]) -> list[WordListEntry]:
    """Filtra y deduplica filas (headword, pos, nivel, fuente). Puro: los tests
    lo usan sin leer los CSV."""
    candidates: dict[str, list[tuple[str, EnglishLevel, tuple[str, ...], str]]] = {}
    for headword, pos, level, source in rows:
        pos = pos.strip().lower()
        if pos not in POS_PRIORITY:
            continue
        try:
            cefr = EnglishLevel(level.strip().upper())
        except ValueError:
            continue
        forms = [form.strip() for form in headword.split("/")]
        valid = [form for form in forms if _valid_form(form)]
        if not valid:
            continue
        lemma, variants = valid[0], tuple(valid[1:])
        candidates.setdefault(lemma, []).append((pos, cefr, variants, source))

    entries = []
    for lemma, options in candidates.items():
        pos, _, _, source = min(options, key=lambda option: POS_PRIORITY.index(option[0]))
        level = min((option[1] for option in options), key=LEVEL_ORDER.index)
        variants = tuple(sorted({v for option in options for v in option[2]} - {lemma}))
        entries.append(WordListEntry(lemma, pos, level, variants, source))
    entries.sort(key=lambda entry: (LEVEL_ORDER.index(entry.level), _order_key(entry.lemma)))
    return entries


def _read_rows() -> list[tuple[str, str, str, str]]:
    rows = []
    for source, filename in SOURCES:
        with (DATA_DIR / filename).open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                rows.append((row["headword"], row["pos"], row["CEFR"], source))
    return rows


@lru_cache
def load_word_list() -> tuple[WordListEntry, ...]:
    """Una vez por proceso: son ~10 mil filas y no cambian."""
    return tuple(parse_rows(_read_rows()))


def entries_for_level(level: EnglishLevel) -> list[WordListEntry]:
    return [entry for entry in load_word_list() if entry.level == level]
