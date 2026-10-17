"""Datos de prueba del modulo English, compartidos por sus archivos de test.

Siembran el banco directo con el ORM (palabras APPROVED con imagen y
contenido): los tests de la practica no dependen del llenado.
"""

from sqlalchemy.orm import Session

from app.db.models.english import EngWord, EngWordContent, EngWordImage

LISTENING = "I see the {word} in the park."
READING = "I see the {word} in the park. It is very nice today. Do you like the park?"


def seed_bank(db: Session, *, level: str = "A1", words: list[str] | None = None) -> list[EngWord]:
    lemmas = words or [f"word{chr(97 + i)}" for i in range(6)]
    created = []
    for lemma in lemmas:
        word = EngWord(
            lemma=lemma,
            pos="noun",
            cefr_level=level,
            accepted_answers=[],
            variants=[],
            source_list="cefrj",
            status="APPROVED",
            fill_attempts=0,
        )
        db.add(word)
        db.flush()
        db.add(
            EngWordImage(
                word_id=word.id,
                position=0,
                url=f"https://img.example/{lemma}.png",
                source="arasaac",
                license="CC BY-NC-SA 4.0",
                attribution="ARASAAC",
                page_url=None,
                selected=True,
                rejected=False,
            )
        )
        db.add(
            EngWordContent(
                word_id=word.id,
                level=level,
                listening_sentence=LISTENING.format(word=lemma),
                writing_prompt=f"Write about a {lemma}.",
                writing_prompt_es=f"Escribe sobre {lemma}." if level in ("A1", "A2") else None,
                reading_text=READING.format(word=lemma),
                reading_question="Do you like the park?",
                model="gpt-6-luna",
                prompt_version=1,
            )
        )
        created.append(word)
    db.commit()
    return created


def practice_payload(practice: dict, **overrides) -> dict:
    """Lo que manda el front al llegar al cierre, a partir de GET /practices/next."""
    payload = {
        "word_id": practice["word_id"],
        "content_id": practice["content_id"],
        "vocab_revealed": False,
        "listening_text_shown": False,
        "writing_text": "x" * practice["config"]["writing_min_chars"],
        "reading_transcript": "I see the word in the park.",
        "reading_match_pct": 90.0,
        "free_transcript": "I like the park because it is green.",
        "audio_seconds": 42.0,
        "mastered": True,
    }
    payload.update(overrides)
    return payload
