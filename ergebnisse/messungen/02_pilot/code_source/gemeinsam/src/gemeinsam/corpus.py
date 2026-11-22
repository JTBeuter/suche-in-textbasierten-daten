"""Dateizugriff und einmalige Aufbereitung außerhalb der Suchmessung."""

import os
from collections.abc import Iterable
from pathlib import Path

from .models import CorpusError, PreparedDocument, RawDocument
from .text import tokenize


def load_corpus(root: str | Path) -> tuple[RawDocument, ...]:
    """Lädt rekursiv ausschließlich .txt-Dateien als striktes UTF-8.

    Kennung und source_path sind sortierte, relative POSIX-Pfade. Leere
    Verzeichnisse und Dateien sind gültig. Symbolische Links im durchlaufenen
    Baum (auch auf Verzeichnisse) werden abgewiesen, statt ausgelassen oder
    verfolgt zu werden. Auch Dateisystemfehler führen zum Abbruch.
    """
    if not isinstance(root, (str, Path)):
        raise CorpusError("Der Korpuspfad muss str oder pathlib.Path sein.")
    if isinstance(root, str) and (not root or "\x00" in root):
        raise CorpusError("Der Korpuspfad darf weder leer sein noch Nullzeichen enthalten.")
    root_path = Path(root)
    try:
        if root_path.is_symlink():
            raise CorpusError(f"Symbolischer Link als Korpuswurzel ist unzulässig: {root_path}")
        if not root_path.exists():
            raise CorpusError(f"Der Korpuspfad existiert nicht: {root_path}")
        if not root_path.is_dir():
            raise CorpusError(f"Der Korpuspfad ist kein Verzeichnis: {root_path}")

        def walk_error(error: OSError) -> None:
            raise error

        paths: list[Path] = []
        for directory, dirnames, filenames in os.walk(root_path, onerror=walk_error):
            dirnames.sort()
            filenames.sort()
            for name in (*dirnames, *filenames):
                entry = Path(directory) / name
                if entry.is_symlink():
                    raise CorpusError(f"Symbolischer Link im Korpus ist unzulässig: {entry}")
            for name in filenames:
                entry = Path(directory) / name
                if entry.suffix == ".txt":
                    if not entry.is_file():
                        raise CorpusError(f"Keine reguläre Textdatei: {entry}")
                    paths.append(entry)

        documents: list[RawDocument] = []
        for path in sorted(paths, key=lambda item: item.relative_to(root_path).as_posix()):
            relative_path = path.relative_to(root_path).as_posix()
            try:
                # read_bytes avoids the implicit CRLF-to-LF conversion of text I/O.
                raw_text = path.read_bytes().decode("utf-8", errors="strict")
            except UnicodeDecodeError as error:
                raise CorpusError(f"Datei ist kein gültiges UTF-8: {relative_path}") from error
            documents.append(RawDocument(relative_path, relative_path, raw_text))
        return tuple(documents)
    except OSError as error:
        raise CorpusError(f"Korpus konnte nicht vollständig gelesen werden: {error}") from error


def prepare_corpus(raw_documents: Iterable[RawDocument]) -> tuple[PreparedDocument, ...]:
    """Validiert Kennungen, sortiert Dokumente und erhält alle Quelldaten."""
    if isinstance(raw_documents, (str, bytes)):
        raise CorpusError("Der Korpus muss ein Iterable von RawDocument sein.")
    try:
        iterator = iter(raw_documents)
    except TypeError as error:
        raise CorpusError("Der Korpus muss ein Iterable von RawDocument sein.") from error
    documents: list[RawDocument] = []
    identifiers: set[str] = set()
    for document in iterator:
        if not isinstance(document, RawDocument):
            raise CorpusError("Der Korpus enthält ein Element, das kein RawDocument ist.")
        if document.document_id in identifiers:
            raise CorpusError(f"Doppelte Dokumentkennung: {document.document_id}")
        identifiers.add(document.document_id)
        documents.append(document)
    return tuple(
        PreparedDocument(
            document.document_id,
            document.source_path,
            document.raw_text,
            tokenize(document.raw_text),
        )
        for document in sorted(documents, key=lambda item: item.document_id)
    )
