"""Comparacion de la lectura en voz alta contra el texto esperado (fase 1 del speaking).

Codigo puro, sin LLM (ENGLISH-TEACHER-PLAN.md, seccion 1): diff por palabras
con difflib despues de normalizar lo que no es un error de lectura
(mayusculas, puntuacion, numeros escritos con digitos por el transcriptor).

Limite conocido (C1): el diff ve palabras omitidas, agregadas o cambiadas,
no la pronunciacion. Una palabra mal pronunciada que el transcriptor
"corrigio" cuenta como bien leida.
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")

_ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen"
).split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def _number_words(number: int) -> list[str]:
    """0-999 en palabras: Whisper escribe "20" donde el texto dice "twenty"."""
    if number < 20:
        return [_ONES[number]]
    if number < 100:
        tens, ones = divmod(number, 10)
        return [_TENS[tens]] + ([_ONES[ones]] if ones else [])
    hundreds, rest = divmod(number, 100)
    return [_ONES[hundreds], "hundred"] + (_number_words(rest) if rest else [])


def tokens(text: str) -> list[str]:
    words: list[str] = []
    for token in _TOKEN.findall(text.lower().replace("’", "'")):
        if token.isdigit() and int(token) < 1000:
            words.extend(_number_words(int(token)))
        else:
            words.append(token)
    return words


@dataclass(frozen=True)
class DiffOp:
    # equal: leida bien; missing: no la dijo; extra: dijo de mas; changed: dijo otra.
    kind: str
    expected: list[str]
    said: list[str]


@dataclass(frozen=True)
class ReadingDiff:
    # Palabras del texto esperado leidas bien, en porcentaje (0-100).
    match_pct: float
    ops: list[DiffOp]


_KIND = {"equal": "equal", "delete": "missing", "insert": "extra", "replace": "changed"}


def compare_reading(expected: str, said: str) -> ReadingDiff:
    expected_words = tokens(expected)
    said_words = tokens(said)
    matcher = SequenceMatcher(a=expected_words, b=said_words, autojunk=False)
    ops = [
        DiffOp(kind=_KIND[tag], expected=expected_words[i1:i2], said=said_words[j1:j2])
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
    ]
    matched = sum(len(op.expected) for op in ops if op.kind == "equal")
    match_pct = round(100 * matched / len(expected_words), 1) if expected_words else 0.0
    return ReadingDiff(match_pct=match_pct, ops=ops)
