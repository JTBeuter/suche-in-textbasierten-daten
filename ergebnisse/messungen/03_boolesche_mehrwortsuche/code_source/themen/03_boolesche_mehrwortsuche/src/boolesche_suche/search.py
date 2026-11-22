"""Direkte Tokenreferenz und Kombination vorhandener immutable Postinglisten."""

from collections.abc import Iterable

from gemeinsam import CorpusError, PreparedDocument, QueryError
from invertierter_index import InvertedIndex, get_postings

from .lists import intersect_sorted, union_sorted
from .query import normalize_boolean_query


def search_direct_boolean(
    corpus: Iterable[PreparedDocument], terms: Iterable[str], operator: str,
) -> list[str]:
    """Scan ohne Index/Dokumentwortmengen; pro Dokument früh abbrechen.

    Einmal mit prepare_corpus geprüfte Dokumente vorausgesetzt wie in Thema 01.
    Nur Anfragebegriffe, innerhalb des aktuellen Dokuments gefundene Begriffe
    und Ergebniskennungen liegen in kleinen Sets. Tokens werden sequenziell
    betrachtet; kein vorbereiteter Dokument- oder Wortindex wird verwendet.
    """
    query = normalize_boolean_query(terms, operator)
    wanted = set(query.terms)
    if isinstance(corpus, (str, bytes)):
        raise CorpusError("Die boolesche Suche benötigt einen Korpus aus PreparedDocument.")
    try:
        documents = iter(corpus)
    except TypeError as error:
        raise CorpusError("Die boolesche Suche benötigt einen Korpus aus PreparedDocument.") from error
    matches: set[str] = set()
    for document in documents:
        if not isinstance(document, PreparedDocument):
            raise CorpusError("Die boolesche Suche benötigt PreparedDocument aus prepare_corpus.")
        if query.operator == "OR":
            for token in document.tokens:
                if token in wanted:
                    matches.add(document.document_id)
                    break
        else:
            found: set[str] = set()
            for token in document.tokens:
                if token in wanted:
                    found.add(token)
                    if len(found) == query.effective_term_count:
                        matches.add(document.document_id)
                        break
    return sorted(matches)


def search_index_boolean(
    index: InvertedIndex, terms: Iterable[str], operator: str,
    variant: str = "input_order",
) -> list[str]:
    """AND in Eingabereihenfolge oder stabil nach Länge; OR in Eingabereihenfolge.

    Normalisieren, get_postings-Vertragsprüfung, Sammeln, ggf. Sortieren und
    vollständige Ergebnisbildung gehören zur öffentlichen Abfrage. Sortierung
    betrifft nur eine lokale Liste von Tupelreferenzen. Auch bei k=1 wird eine
    neue Ergebnisliste erzeugt; der Index und seine Postinglisten bleiben gleich.
    """
    query = normalize_boolean_query(terms, operator)
    if not isinstance(variant, str) or variant not in ("input_order", "shortest_first"):
        raise QueryError("variant muss 'input_order' oder 'shortest_first' sein.")
    if query.operator == "OR" and variant != "input_order":
        raise QueryError("OR unterstützt ausschließlich variant='input_order'.")
    postings = [get_postings(index, term) for term in query.terms]
    if variant == "shortest_first":
        # Python sort ist stabil: bei gleicher Länge bleibt die Eingabereihenfolge.
        postings.sort(key=len)
    result = list(postings[0])
    for posting in postings[1:]:
        if query.operator == "AND":
            if not result:
                break
            result = intersect_sorted(result, posting)
        else:
            result = union_sorted(result, posting)
    return result
