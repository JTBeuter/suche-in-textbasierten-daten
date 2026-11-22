"""Reproduzierbare UTF-8-Korpora mit unabhängig festgelegten Suchfällen."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import random


@dataclass(frozen=True)
class GeneratedCorpus:
    """Erwartungen entstehen aus dem Pflanzplan, nicht aus dem Suchverfahren."""

    root: Path
    total_tokens: int
    document_count: int
    seed: int
    expected_tokens: dict[str, tuple[str, ...]]
    expected_hits: dict[str, tuple[str, ...]]
    expected_occurrences: dict[str, int]
    file_sha256: dict[str, str]


def generate_corpus(
    root: str | Path,
    total_tokens: int,
    *,
    document_count: int = 20,
    seed: int = 20261006,
) -> GeneratedCorpus:
    """Schreibe gleich lange Dokumente; eine Datei entspricht einem Dokument.

    Wortschatz: wort0000..wort0999, mit Random(seed).randrange(1000).
    Fehler steht an den Positionen 0, 100, 200, ... jedes Dokuments.
    Verbindung steht nur am Ende von doc00.txt; Unauffindbar fehlt.
    Der Generator fordert mindestens zwei Tokens je Dokument und verhindert
    einen Konflikt zwischen beiden gepflanzten Suchwörtern.
    """
    if isinstance(total_tokens, bool) or not isinstance(total_tokens, int):
        raise TypeError("total_tokens muss eine ganze Zahl sein")
    if isinstance(document_count, bool) or not isinstance(document_count, int):
        raise TypeError("document_count muss eine ganze Zahl sein")
    if document_count <= 0 or total_tokens < 2 * document_count:
        raise ValueError("mindestens zwei Tokens je Dokument sind erforderlich")
    if total_tokens % document_count:
        raise ValueError("total_tokens muss durch document_count teilbar sein")
    tokens_per_document = total_tokens // document_count
    if (tokens_per_document - 1) % 100 == 0:
        raise ValueError("letzte Position kollidiert mit dem gepflanzten Fehler")
    target = Path(root)
    target.mkdir(parents=True, exist_ok=True)
    if any(target.iterdir()):
        raise ValueError("Zielverzeichnis muss leer sein")

    rng = random.Random(seed)
    expected_tokens: dict[str, tuple[str, ...]] = {}
    hashes: dict[str, str] = {}
    width = max(2, len(str(document_count - 1)))
    for number in range(document_count):
        name = f"doc{number:0{width}d}.txt"
        words = [f"wort{rng.randrange(1000):04d}" for _ in range(tokens_per_document)]
        for position in range(0, tokens_per_document, 100):
            words[position] = "Fehler"
        if number == 0:
            words[-1] = "Verbindung"
        payload = (" ".join(words) + "\n").encode("utf-8")
        (target / name).write_bytes(payload)
        hashes[name] = hashlib.sha256(payload).hexdigest()
        # Diese Erwartung benutzt keine Aufbereitung des untersuchten Systems.
        expected_tokens[name] = tuple(
            "fehler" if word == "Fehler" else "verbindung" if word == "Verbindung" else word
            for word in words
        )
    identifiers = tuple(expected_tokens)
    return GeneratedCorpus(
        root=target,
        total_tokens=total_tokens,
        document_count=document_count,
        seed=seed,
        expected_tokens=expected_tokens,
        expected_hits={
            "frequent": identifiers,
            "rare": (identifiers[0],),
            "missing": (),
        },
        expected_occurrences={
            "frequent": document_count * ((tokens_per_document - 1) // 100 + 1),
            "rare": 1,
            "missing": 0,
        },
        file_sha256=hashes,
    )
