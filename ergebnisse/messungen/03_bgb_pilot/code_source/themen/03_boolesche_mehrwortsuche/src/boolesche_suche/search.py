"""Direkte Tokenreferenz und Kombination vorhandener immutable Postinglisten."""

from collections.abc import Iterable

from gemeinsam import CorpusError, PreparedDocument, QueryError
from invertierter_index import InvertedIndex, get_postings

from .lists import difference_sorted, intersect_galloping, intersect_sorted, union_sorted
from .query import normalize_boolean_query


VARIANTS = ("input_order", "shortest_first", "galloping")


def search_direct_boolean(
    corpus: Iterable[PreparedDocument], terms: Iterable[str], operator: str,
    exclude: str | None = None,
) -> list[str]:
    """Scan ohne Index/Dokumentwortmengen; pro Dokument früh abbrechen.

    Einmal mit prepare_corpus geprüfte Dokumente vorausgesetzt wie in Thema 01.
    Nur Anfragebegriffe, innerhalb des aktuellen Dokuments gefundene Begriffe
    und Ergebniskennungen liegen in kleinen Sets. Tokens werden sequenziell
    betrachtet; kein vorbereiteter Dokument- oder Wortindex wird verwendet.

    Mit exclude (nur AND) ist ein Dokument ein Treffer, wenn alle Pflichtwörter
    vorkommen und das ausgeschlossene Wort nicht. Früher Abbruch ist dann nur
    beim ausgeschlossenen Wort korrekt; sind alle Pflichtwörter gefunden, muss
    der Rest des Dokuments trotzdem gelesen werden.
    """
    query = normalize_boolean_query(terms, operator, exclude)
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
        elif query.exclude is None:
            found: set[str] = set()
            for token in document.tokens:
                if token in wanted:
                    found.add(token)
                    if len(found) == query.effective_term_count:
                        matches.add(document.document_id)
                        break
        else:
            found = set()
            excluded = False
            for token in document.tokens:
                if token == query.exclude:
                    # Ausschlusswort gefunden: Dokument kann kein Treffer mehr sein.
                    excluded = True
                    break
                if token in wanted:
                    found.add(token)
            if not excluded and len(found) == query.effective_term_count:
                matches.add(document.document_id)
    return sorted(matches)


def search_index_boolean(
    index: InvertedIndex, terms: Iterable[str], operator: str,
    variant: str = "input_order", exclude: str | None = None,
) -> list[str]:
    """AND in Eingabereihenfolge, stabil nach Länge oder galoppierend; OR in Eingabereihenfolge.

    Normalisieren, get_postings-Vertragsprüfung, Sammeln, ggf. Sortieren und
    vollständige Ergebnisbildung gehören zur öffentlichen Abfrage. Sortierung
    betrifft nur eine lokale Liste von Tupelreferenzen. Auch bei k=1 wird eine
    neue Ergebnisliste erzeugt; der Index und seine Postinglisten bleiben gleich.

    galloping sortiert wie shortest_first stabil aufsteigend nach Länge und
    schneidet dann schrittweise mit intersect_galloping. exclude (nur AND)
    zieht nach dem Schnitt die Postingliste des NOT-Worts mit
    difference_sorted ab; bei leerem Schnitt entfällt dieser Schritt.
    """
    query = normalize_boolean_query(terms, operator, exclude)
    if not isinstance(variant, str) or variant not in VARIANTS:
        raise QueryError("variant muss 'input_order', 'shortest_first' oder 'galloping' sein.")
    if query.operator == "OR" and variant != "input_order":
        raise QueryError("OR unterstützt ausschließlich variant='input_order'.")
    postings = [get_postings(index, term) for term in query.terms]
    if variant != "input_order":
        # Python sort ist stabil: bei gleicher Länge bleibt die Eingabereihenfolge.
        postings.sort(key=len)
    result = list(postings[0])
    for posting in postings[1:]:
        if query.operator == "AND":
            if not result:
                break
            if variant == "galloping":
                result = intersect_galloping(result, posting)
            else:
                result = intersect_sorted(result, posting)
        else:
            result = union_sorted(result, posting)
    if query.exclude is not None and result:
        result = difference_sorted(result, get_postings(index, query.exclude))
    return result
