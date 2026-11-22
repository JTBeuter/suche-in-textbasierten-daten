"""Suchkosten schließen Anfrageaufbereitung und Ergebnisbildung ein."""

from collections.abc import Iterable

from gemeinsam import (
    CorpusError,
    PreparedDocument,
    QueryError,
    RawDocument,
    normalize_query,
    normalize_text,
)


def search_direct_word(corpus: Iterable[PreparedDocument], query: str) -> list[str]:
    """Vergleicht Tokens sequenziell und bricht beim ersten Treffer pro Datei ab.

    Der Korpus wird vorher einmal mit prepare_corpus validiert und aufbereitet.
    Es werden keine Wortmengen oder Token-zu-Dokument-Listen vorbereitet.
    Die eindeutige Ergebnismenge enthält nur gefundene Dokumentkennungen.
    """
    (word,) = normalize_query(query, "word")
    matches: set[str] = set()
    for document in corpus:
        if not isinstance(document, PreparedDocument):
            raise CorpusError("Die Wortsuche benötigt PreparedDocument aus prepare_corpus.")
        for token in document.tokens:
            if token == word:
                matches.add(document.document_id)
                break
    return sorted(matches)


def search_direct_substring(corpus: Iterable[RawDocument], query: str) -> list[str]:
    """Demonstriert normalisierte Teilzeichensuche im Rohtext (keine Wortbaseline)."""
    if not isinstance(query, str) or not query:
        raise QueryError("Die Teilzeichenanfrage muss eine nichtleere Zeichenkette sein.")
    substring = normalize_text(query)
    matches: set[str] = set()
    for document in corpus:
        if not isinstance(document, RawDocument):
            raise CorpusError("Die Teilzeichensuche benötigt RawDocument aus load_corpus.")
        if substring in normalize_text(document.raw_text):
            matches.add(document.document_id)
    return sorted(matches)
