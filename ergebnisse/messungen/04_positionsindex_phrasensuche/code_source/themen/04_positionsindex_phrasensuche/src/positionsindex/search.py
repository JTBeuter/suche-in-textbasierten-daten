"""Unabhängiger Startpositionsscan und verschobene Zwei-Zeiger-Schnittbildung."""

from collections.abc import Iterable, Sequence

from boolesche_suche import intersect_sorted
from gemeinsam import CorpusError, PreparedDocument

from .index import PositionalIndex
from .query import validate_phrase_tokens


PhraseMatches = dict[str, list[int]]


def search_direct_phrase(
    corpus: Iterable[PreparedDocument], phrase_tokens: Iterable[str],
) -> PhraseMatches:
    """Prüft alle zulässigen Starts und unmittelbar nachfolgende Tokens.

    Keine Positionslisten, keine Wortmengen, kein Index. Ein früher
    Tokenunterschied beendet nur die Prüfung des aktuellen Starts;
    überlappende Treffer bleiben erhalten. Der einmalig durch prepare_corpus
    validierte Tokenvertrag ist Vorbedingung wie bei der direkten Wortsuche.
    Queryprüfung, Typ-/ID-Prüfung und sortierte Ergebnisbildung sind Teil der
    öffentlichen Abfrage. Eingabeiterables werden einmal konsumiert.
    """
    phrase = validate_phrase_tokens(phrase_tokens)
    if isinstance(corpus, (str, bytes)):
        raise CorpusError("Die Phrasensuche benötigt ein Iterable von PreparedDocument.")
    try:
        documents = iter(corpus)
    except TypeError as error:
        raise CorpusError("Die Phrasensuche benötigt ein Iterable von PreparedDocument.") from error
    identifiers: set[str] = set()
    matches: PhraseMatches = {}
    phrase_length = len(phrase)
    for document in documents:
        if not isinstance(document, PreparedDocument):
            raise CorpusError("Die Phrasensuche benötigt PreparedDocument aus prepare_corpus.")
        if document.document_id in identifiers:
            raise CorpusError(f"Doppelte Dokumentkennung: {document.document_id}")
        identifiers.add(document.document_id)
        starts: list[int] = []
        for start in range(len(document.tokens) - phrase_length + 1):
            for offset, token in enumerate(phrase):
                if document.tokens[start + offset] != token:
                    break
            else:
                starts.append(start)
        if starts:
            matches[document.document_id] = starts
    return dict(sorted(matches.items()))


def _intersect_shifted(
    starts: Sequence[int], positions: Sequence[int], offset: int,
) -> list[int]:
    """Behält s aus starts genau dann, wenn s+offset in positions liegt.

    Beide Eingaben sind sortiert und eindeutig. Verschiebung erfolgt beim
    Vergleich, ohne Kopie der gesamten Positionsliste. Zwei Zeiger laufen
    monoton; Kosten O(len(starts) + len(positions)). Keine Eingabemutation.
    """
    result: list[int] = []
    i = j = 0
    while i < len(starts) and j < len(positions):
        start = starts[i]
        shifted_position = positions[j] - offset
        if start == shifted_position:
            result.append(start)
            i += 1
            j += 1
        elif start < shifted_position:
            i += 1
        else:
            j += 1
    return result


def search_index_phrase(
    index: PositionalIndex, phrase_tokens: Iterable[str],
) -> PhraseMatches:
    """AND-Kandidaten, dann jedes Phrasenelement mit richtigem Offset prüfen.

    Kandidaten entstehen aus sortierten Dokumentkeys je verschiedenem Wort
    über intersect_sorted aus Thema 03. Pro Kandidat dienen die kürzesten
    Positionslisten als Anker; Gleichstände erhalten die Phrasenreihenfolge.
    Position p des Ankers an Offset j ergibt den Start p-j. Negative Starts
    entfallen. Die anschließende verschobene Schnittbildung prüft jedes
    Element einschließlich Wiederholungen. Keine Positionsliste wird verändert
    oder als mutable Alias ausgegeben. Fehlende Wörter/leere Zwischenergebnisse
    führen zum frühen Abbruch. Der Indexaufbau garantiert sämtliche Invarianten.
    """
    phrase = validate_phrase_tokens(phrase_tokens)
    document_lists: list[tuple[str, ...]] = []
    for token in dict.fromkeys(phrase):
        postings = index.get(token)
        if postings is None:
            return {}
        document_lists.append(tuple(postings))
    document_lists.sort(key=len)
    candidates = list(document_lists[0])
    for document_ids in document_lists[1:]:
        candidates = intersect_sorted(candidates, document_ids)
        if not candidates:
            return {}
    matches: PhraseMatches = {}
    for identifier in candidates:
        # enumerate preserves each repeated token and its original offset.
        occurrences = [(offset, index[token][identifier]) for offset, token in enumerate(phrase)]
        occurrences.sort(key=lambda occurrence: len(occurrence[1]))
        anchor_offset, anchor_positions = occurrences[0]
        starts = [position - anchor_offset for position in anchor_positions if position >= anchor_offset]
        for offset, positions in occurrences[1:]:
            if not starts:
                break
            starts = _intersect_shifted(starts, positions, offset)
        if starts:
            matches[identifier] = starts
    return matches
