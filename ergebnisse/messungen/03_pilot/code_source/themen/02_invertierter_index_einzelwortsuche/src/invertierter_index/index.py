"""Dokumentindex: eigene Wörterbuchkonstruktion, unveränderliche Postinglisten."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from gemeinsam import CorpusError, PreparedDocument, QueryError, normalize_query, tokenize


@dataclass(frozen=True, slots=True, init=False, repr=False, eq=False)
class InvertedIndex(Mapping[str, tuple[str, ...]]):
    """Nur-Lese-Abbildung normalisierter Tokens auf sortierte Dokumentkennungen.

    Erzeugung ausschließlich durch build_inverted_index. Das intern erzeugte
    Wörterbuch entweicht nicht; seine Lesesicht und alle Werte sind unveränderlich.
    Mappingzugriff verlangt bereits normalisierte Schlüssel. Für Rohtextanfragen
    ist search_index_word zuständig, für validierte Kernanfragen get_postings.
    """

    _postings: Mapping[str, tuple[str, ...]]

    def __init__(self) -> None:
        raise TypeError("InvertedIndex mit build_inverted_index erzeugen.")

    def __getitem__(self, token: str) -> tuple[str, ...]:
        return self._postings[token]

    def __iter__(self) -> Iterator[str]:
        return iter(self._postings)

    def __len__(self) -> int:
        return len(self._postings)

    def __repr__(self) -> str:
        return f"InvertedIndex(vocabulary_size={len(self)})"


def build_inverted_index(corpus: Iterable[PreparedDocument]) -> InvertedIndex:
    """Baut Token → sortierte, eindeutige IDs ohne Positionen.

    Prüft vorbereitete Dokumenttypen, ID-Eindeutigkeit und normalisierte Tokens.
    Der Rohtext wird nicht erneut aufbereitet: die Konsistenz seiner Tokens ist
    Vorbedingung von prepare_corpus. Ein lokales Set vermeidet Wiederholungen
    innerhalb eines Dokuments; ein abschließender Sortierschritt erlaubt beliebige
    Eingabereihenfolge. Der Korpus kann ein einmalig konsumierbarer Iterator sein.
    Alle zusätzlichen Aufbauprüfungen gehören zur gemessenen Aufbauzeit.
    """
    if isinstance(corpus, (str, bytes)):
        raise CorpusError("Der Korpus muss ein Iterable von PreparedDocument sein.")
    try:
        documents = iter(corpus)
    except TypeError as error:
        raise CorpusError("Der Korpus muss ein Iterable von PreparedDocument sein.") from error
    identifiers: set[str] = set()
    checked_tokens: set[str] = set()
    postings: dict[str, list[str]] = {}
    for document in documents:
        if not isinstance(document, PreparedDocument):
            raise CorpusError("Der Korpus enthält ein Element, das kein PreparedDocument ist.")
        if document.document_id in identifiers:
            raise CorpusError(f"Doppelte Dokumentkennung: {document.document_id}")
        identifiers.add(document.document_id)
        for token in set(document.tokens):
            # Keine zweite Textregel: die zentrale Tokenisierung prüft nur den
            # vorbereiteten Tokenvertrag, einmal je verschiedenem Token/Aufbau.
            if token not in checked_tokens:
                if tokenize(token) != (token,):
                    raise CorpusError(f"Kein normalisiertes einzelnes Token: {token!r}")
                checked_tokens.add(token)
            postings.setdefault(token, []).append(document.document_id)
    immutable = {token: tuple(sorted(ids)) for token, ids in postings.items()}
    index = object.__new__(InvertedIndex)
    object.__setattr__(index, "_postings", MappingProxyType(immutable))
    return index


def get_postings(index: InvertedIndex, token: str) -> tuple[str, ...]:
    """Liest eine Postingliste ohne Kopie und ohne Korpusdurchlauf (Thema 03).

    Nur ein bereits normalisiertes einzelnes Token ist zulässig. Rohtexte wie
    'Fehler!' werden hier mit QueryError zurückgewiesen; search_index_word
    akzeptiert sie nach gemeinsamer Normalisierung. Unbekannte Tokens liefern ().
    Die Vertragsprüfung kostet Zeichenverarbeitung; der Dictionaryzugriff hat
    durchschnittlich konstante Kosten unter üblichen Hashannahmen.
    """
    if not isinstance(token, str) or tokenize(token) != (token,):
        raise QueryError("Postingzugriff verlangt genau ein bereits normalisiertes Token.")
    return index.get(token, ())


def search_index_word(index: InvertedIndex, query: str) -> list[str]:
    """Normalisiert eine Rohtext-Wortanfrage und kopiert die vollständigen Treffer.

    Kein Aufbau, Korpusdurchlauf oder Cache in der Abfrage. QueryError bei null
    oder mehreren Tokens; unbekanntes gültiges Wort ergibt eine neue leere Liste.
    Die neue Liste teilt keine veränderliche Struktur mit den gespeicherten Tupeln.
    """
    (token,) = normalize_query(query, "word")
    return list(index.get(token, ()))
