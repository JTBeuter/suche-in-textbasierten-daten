"""Vertragsprüfung für bereits gemeinsam normalisierte Tokenphrasen."""

from collections.abc import Iterable

from gemeinsam import QueryError, tokenize


def validate_phrase_tokens(phrase_tokens: Iterable[str]) -> tuple[str, ...]:
    """Erhält Reihenfolge und Wiederholungen; normalisiert keine Rohwörter.

    Rohtext wird vorher durch normalize_query(text, query_type='phrase')
    vorbereitet. Jeder Kernbegriff muss schon ein einzelnes normalisiertes
    Token sein. Auch bei unbekannten Wörtern wird die gesamte Anfrage geprüft.
    Einmalig konsumierbare Iterables sind zulässig, Zeichenketten nicht.
    """
    if isinstance(phrase_tokens, (str, bytes)):
        raise QueryError("Die Phrase benötigt ein Iterable bereits normalisierter Tokens.")
    try:
        tokens = tuple(phrase_tokens)
    except TypeError as error:
        raise QueryError("Die Phrase benötigt ein Iterable bereits normalisierter Tokens.") from error
    if not tokens:
        raise QueryError("Die Phrase muss mindestens ein Token enthalten.")
    checked: set[str] = set()
    for token in tokens:
        if not isinstance(token, str):
            raise QueryError("Jedes Phrasenelement muss ein bereits normalisiertes Token sein.")
        if token not in checked:
            if tokenize(token) != (token,):
                raise QueryError(f"Kein normalisiertes einzelnes Phrasentoken: {token!r}")
            checked.add(token)
    return tokens
