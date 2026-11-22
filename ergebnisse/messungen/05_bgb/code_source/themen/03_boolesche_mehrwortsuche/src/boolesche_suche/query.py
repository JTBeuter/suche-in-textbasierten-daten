"""Abfragevertrag: Rohbegriffe, Operator und optionales NOT-Wort getrennt, Reihenfolge erhalten."""

from collections.abc import Iterable
from dataclasses import dataclass

from gemeinsam import QueryError, normalize_query


@dataclass(frozen=True, slots=True)
class BooleanQuery:
    terms: tuple[str, ...]
    operator: str
    original_term_count: int
    # Normalisiertes ausgeschlossenes Wort für AND NOT; None ohne Ausschluss.
    exclude: str | None = None

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


def normalize_boolean_query(
    terms: Iterable[str], operator: str, exclude: str | None = None,
) -> BooleanQuery:
    """Validiert reine AND-/OR-Abfragen und zählt rohe/effektive Begriffe.

    exclude ist genau ein auszuschließendes Rohwort (A AND B AND NOT C). Es
    wird wie die Pflichtwörter normalisiert, muss genau ein Token ergeben und
    ist nur mit operator 'AND' zulässig. NOT ohne Pflichtwort ist nicht
    vorgesehen, weil es eine Liste aller Dokumente bräuchte. Gleicht das
    NOT-Wort einem Pflichtwort, ist die Anfrage gültig und das Ergebnis leer.
    """
    if not isinstance(operator, str) or operator not in ("AND", "OR"):
        raise QueryError("operator muss 'AND' oder 'OR' sein (Großschreibung).")
    if exclude is not None and operator != "AND":
        raise QueryError("exclude (AND NOT) ist ausschließlich mit operator='AND' zulässig.")
    normalized, original_count = _normalize_terms(terms)
    if exclude is None:
        return BooleanQuery(normalized, operator, original_count)
    if not isinstance(exclude, str):
        raise QueryError("exclude muss ein einzelnes Wort als Zeichenkette sein.")
    try:
        (excluded,) = normalize_query(exclude, "word")
    except QueryError as error:
        raise QueryError(f"exclude muss genau ein Wort ergeben. {error}") from error
    return BooleanQuery(normalized, operator, original_count, excluded)
