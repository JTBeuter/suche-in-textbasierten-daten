"""Abfragevertrag: Rohbegriffe und Operator getrennt, Reihenfolge erhalten."""

from collections.abc import Iterable
from dataclasses import dataclass

from gemeinsam import QueryError, normalize_query


@dataclass(frozen=True, slots=True)
class BooleanQuery:
    terms: tuple[str, ...]
    operator: str
    original_term_count: int

    @property
    def effective_term_count(self) -> int:
        return len(self.terms)


def _normalize_terms(terms: Iterable[str]) -> tuple[tuple[str, ...], int]:
    if isinstance(terms, (str, bytes)):
        raise QueryError("Begriffe als Iterable einzelner Wörter übergeben, nicht als Zeichenkette.")
    try:
        iterator = iter(terms)
    except TypeError as error:
        raise QueryError("Begriffe müssen ein Iterable einzelner Wörter sein.") from error
    seen: set[str] = set()
    normalized: list[str] = []
    original_count = 0
    for term in iterator:
        original_count += 1
        (token,) = normalize_query(term, "word")
        if token not in seen:
            seen.add(token)
            normalized.append(token)
    if not normalized:
        raise QueryError("Die boolesche Anfrage muss mindestens einen Begriff enthalten.")
    return tuple(normalized), original_count


def normalize_terms(terms: Iterable[str]) -> tuple[str, ...]:
    """Jeden Rohbegriff zentral normalisieren und Duplikate stabil entfernen.

    Jeder Eintrag muss genau ein Token ergeben. Einträge wie 'Fehler!' sind
    gültig, 'E-Mail' oder 'Fehler Server' ergeben QueryError. Iterable werden
    einmal konsumiert; ihre Iterationsreihenfolge bestimmt die Grundvariante.
    """
    return _normalize_terms(terms)[0]


def normalize_boolean_query(terms: Iterable[str], operator: str) -> BooleanQuery:
    """Validiert reine AND-/OR-Abfragen und zählt rohe/effektive Begriffe."""
    if not isinstance(operator, str) or operator not in ("AND", "OR"):
        raise QueryError("operator muss 'AND' oder 'OR' sein (Großschreibung).")
    normalized, original_count = _normalize_terms(terms)
    return BooleanQuery(normalized, operator, original_count)
