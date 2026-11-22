"""Eigener Positionsindex; beide Mappingebenen und Positionslisten sind immutable."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from gemeinsam import CorpusError, PreparedDocument, tokenize


@dataclass(frozen=True, slots=True, init=False, repr=False, eq=False)
class PositionalIndex(Mapping[str, Mapping[str, tuple[int, ...]]]):
    """Token → sortierte Dokumentkennungen → sortierte Tokenpositionen.

    Erzeugung ausschließlich mit build_positional_index. Dokumentkennungen
    einer inneren Mappingebene iterieren lexikografisch, Positionen aufsteigend
    und eindeutig. Die Reihenfolge der äußeren Tokenkeys ist nicht zugesagt.
    Mappingzugriffe verlangen exakte normalisierte Tokens, unbekannte Keys
    erzeugen KeyError. Es entweicht kein veränderliches Aufbauwörterbuch.
    """

    _postings: Mapping[str, Mapping[str, tuple[int, ...]]]

    def __init__(self) -> None:
        raise TypeError("PositionalIndex mit build_positional_index erzeugen.")

    def __getitem__(self, token: str) -> Mapping[str, tuple[int, ...]]:
        return self._postings[token]

    def __iter__(self) -> Iterator[str]:
        return iter(self._postings)

    def __len__(self) -> int:
        return len(self._postings)

    def __repr__(self) -> str:
        return f"PositionalIndex(vocabulary_size={len(self)})"


def build_positional_index(corpus: Iterable[PreparedDocument]) -> PositionalIndex:
    """Traversiert jedes Dokument und enumeriert dessen Tokens ab null.

    Prüft wie build_inverted_index vorbereitete Typen, eindeutige Kennungen
    und jeden verschiedenen Tokenvertrag einmal. Rohtexte werden nicht neu
    aufbereitet; ihre Tokenkonsistenz ist Vorbedingung von prepare_corpus.
    Alle Prüfungen, abschließende ID-Sortierung und unveränderliche
    Ergebnisbildung gehören zur Aufbauzeit. Unsortierte und einmalige
    Iterables sind zulässig. Leere Dokumente erzeugen keine Postinglisten.
    """
    if isinstance(corpus, (str, bytes)):
        raise CorpusError("Der Korpus muss ein Iterable von PreparedDocument sein.")
    try:
        documents = iter(corpus)
    except TypeError as error:
        raise CorpusError("Der Korpus muss ein Iterable von PreparedDocument sein.") from error
    identifiers: set[str] = set()
    checked_tokens: set[str] = set()
    postings: dict[str, dict[str, list[int]]] = {}
    for document in documents:
        if not isinstance(document, PreparedDocument):
            raise CorpusError("Der Korpus enthält ein Element, das kein PreparedDocument ist.")
        if document.document_id in identifiers:
            raise CorpusError(f"Doppelte Dokumentkennung: {document.document_id}")
        identifiers.add(document.document_id)
        for position, token in enumerate(document.tokens):
            if token not in checked_tokens:
                if tokenize(token) != (token,):
                    raise CorpusError(f"Kein normalisiertes einzelnes Token: {token!r}")
                checked_tokens.add(token)
            token_postings = postings.setdefault(token, {})
            token_postings.setdefault(document.document_id, []).append(position)
    immutable = {
        token: MappingProxyType({
            identifier: tuple(positions)
            for identifier, positions in sorted(token_postings.items())
        })
        for token, token_postings in postings.items()
    }
    index = object.__new__(PositionalIndex)
    object.__setattr__(index, "_postings", MappingProxyType(immutable))
    return index
