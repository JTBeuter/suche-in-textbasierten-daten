"""Eine gemeinsame Aufbereitung für Dokumente und Suchanfragen."""

import unicodedata

from .models import QueryError


def normalize_text(text: str) -> str:
    """NFC → casefold → NFC; erhält Umlaute und ist idempotent."""
    if not isinstance(text, str):
        raise TypeError("text muss eine Zeichenkette sein.")
    return unicodedata.normalize("NFC", unicodedata.normalize("NFC", text).casefold())


def _is_token_character(character: str) -> bool:
    category = unicodedata.category(character)
    return category.startswith("L") or category == "Nd"


def tokenize(text: str) -> tuple[str, ...]:
    """Maximale Folgen aus Unicode-Buchstaben (L*) und Dezimalziffern (Nd).

    Alle anderen Kategorien trennen Tokens, auch kombinierende Zeichen,
    die nach der NFC-Normalisierung verbleiben. Satzgrenzen werden nicht
    gespeichert. Die Tokenfolge eines Dokuments wird niemals verkettet.
    """
    tokens: list[str] = []
    current: list[str] = []
    for character in normalize_text(text):
        if _is_token_character(character):
            current.append(character)
        elif current:
            tokens.append("".join(current))
            current.clear()
    if current:
        tokens.append("".join(current))
    return tuple(tokens)


def normalize_query(query: str, query_type: str = "word") -> tuple[str, ...]:
    """Validiert ein Wort oder eine später nutzbare nichtleere Tokenphrase."""
    if not isinstance(query, str):
        raise QueryError("Die Suchanfrage muss eine Zeichenkette sein.")
    if query_type not in ("word", "phrase"):
        raise QueryError("query_type muss 'word' oder 'phrase' sein.")
    tokens = tokenize(query)
    if not tokens:
        raise QueryError("Die Suchanfrage muss mindestens ein Token enthalten.")
    if query_type == "word" and len(tokens) != 1:
        raise QueryError("Die Wortsuche verlangt genau ein Token.")
    return tokens
