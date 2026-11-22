"""Unveränderliche Dokumente; Positionen sind Indizes der Tokenfolge."""

from dataclasses import dataclass


class CorpusError(ValueError):
    """Unzulässiger Korpus, Dokumenttyp oder nicht lesbare Quelldaten."""


class QueryError(ValueError):
    """Die Anfrage entspricht nicht der vereinbarten Suchsemantik."""


def _validate_document_fields(document_id: str, source_path: str, raw_text: str) -> None:
    for name, value in (("document_id", document_id), ("source_path", source_path)):
        if not isinstance(value, str) or not value:
            raise CorpusError(f"{name} muss eine nichtleere Zeichenkette sein.")
        if "\x00" in value:
            raise CorpusError(f"{name} darf kein Nullzeichen enthalten.")
    # The ID is deliberately independent of document ordering and corpus size.
    if (
        document_id.startswith("/")
        or any(part in ("", ".", "..") for part in document_id.split("/"))
        or not document_id.endswith(".txt")
    ):
        raise CorpusError("document_id muss ein relativer POSIX-Dateipfad mit Endung .txt sein.")
    if not isinstance(raw_text, str):
        raise CorpusError("raw_text muss eine Zeichenkette sein.")


@dataclass(frozen=True, slots=True)
class RawDocument:
    """UTF-8-Quelldokument; document_id bezeichnet den relativen Dateipfad."""

    document_id: str
    source_path: str
    raw_text: str

    def __post_init__(self) -> None:
        _validate_document_fields(self.document_id, self.source_path, self.raw_text)


@dataclass(frozen=True, slots=True)
class PreparedDocument:
    """Quelldaten plus normalisierte Tokens; tokens[0] hat Position null."""

    document_id: str
    source_path: str
    raw_text: str
    tokens: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_document_fields(self.document_id, self.source_path, self.raw_text)
        if not isinstance(self.tokens, tuple) or any(
            not isinstance(token, str) or not token for token in self.tokens
        ):
            raise CorpusError("tokens muss ein Tupel nichtleerer Zeichenketten sein.")
