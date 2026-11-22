"""Deterministischer Pflanzplan der Reihe 03b; Erwartungen entstehen vor der Aufbereitung."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import random


STAGES = (10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000)
CASES = ("verteilt", "anfang")
SHORT_LENGTH = 10
DOCUMENT_COUNT = 10_000
TOKENS_PER_DOCUMENT = 100
FILLER_WORDS = 50


@dataclass(frozen=True)
class GeneratedCorpus:
    root: Path
    expected_tokens: dict[str, tuple[str, ...]]
    membership: dict[str, tuple[str, ...]]
    file_sha256: dict[str, str]


def long_word(stage: int) -> str:
    """Langes Wort der Stufe; vier ASCII-Zeichen wie alle Anfrage- und Fülltokens."""
    return f"l{stage:03d}"


def short_word(case: str, stage: int) -> str:
    if case not in CASES:
        raise ValueError(f"unbekannter Fall: {case}")
    return f"{'v' if case == 'verteilt' else 'a'}{stage:03d}"


def identifiers(document_count: int) -> tuple[str, ...]:
    """Feste Breite: lexikografische Ordnung entspricht der Nummer."""
    return tuple(f"d{i:05d}.txt" for i in range(document_count))


def membership_plan(document_count: int = DOCUMENT_COUNT, stages: tuple[int, ...] = STAGES,
                    short_length: int = SHORT_LENGTH) -> dict[str, tuple[str, ...]]:
    """Pflanzplan je Stufe: langes Wort, kurzes Wort verteilt, kurzes Wort am Anfang.

    Das lange Wort der Stufe mit df Dokumenten liegt gleichmäßig über alle
    Dokumente verteilt (Dokument i·D/df). Das kurze Wort „verteilt“ besteht aus
    short_length Einträgen der langen Liste an den Stellen (j+1)·df/short_length−1,
    also gleichmäßig verteilt bis zum letzten Eintrag; ein Zwei-Zeiger-Schnitt
    muss deshalb die ganze lange Liste ablaufen. Das kurze Wort „anfang“ besteht
    aus den ersten short_length Einträgen der langen Liste (Gegenprobe).
    """
    for name, value in (("document_count", document_count), ("short_length", short_length)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} muss eine ganze Zahl sein")
    if document_count < 1 or document_count > 100_000:
        raise ValueError("document_count muss zwischen 1 und 100000 liegen")
    if len(stages) > 1000 or list(stages) != sorted(set(stages)):
        raise ValueError("stages müssen eindeutig, aufsteigend und höchstens 1000 sein")
    if any(isinstance(df, bool) or not isinstance(df, int) or not short_length <= df <= document_count
           for df in stages):
        raise ValueError("jede Stufe braucht short_length <= df <= document_count")
    ids = identifiers(document_count)
    result = {}
    for stage, df in enumerate(stages):
        long_ids = tuple(ids[i * document_count // df] for i in range(df))
        result[long_word(stage)] = long_ids
        result[short_word("verteilt", stage)] = tuple(long_ids[(j + 1) * df // short_length - 1]
                                                       for j in range(short_length))
        result[short_word("anfang", stage)] = long_ids[:short_length]
    return result


def generate_corpus(root: Path, *, document_count: int = DOCUMENT_COUNT, stages: tuple[int, ...] = STAGES,
                    short_length: int = SHORT_LENGTH, tokens_per_document: int = TOKENS_PER_DOCUMENT,
                    seed: int = 20261006) -> GeneratedCorpus:
    """Schreibt die Dateien temporär; Erwartungen stammen aus dem Plan, nicht aus einem Index."""
    for name, value in (("tokens_per_document", tokens_per_document), ("seed", seed)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} muss eine ganze Zahl sein")
    membership = membership_plan(document_count, stages, short_length)
    if tokens_per_document < 3 * len(stages):
        raise ValueError("zu wenige Tokens pro Dokument für alle gepflanzten Wörter")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError("Zielverzeichnis muss leer sein")
    planted_by_id: dict[str, list[str]] = {}
    for word in sorted(membership):
        for identifier in membership[word]:
            planted_by_id.setdefault(identifier, []).append(word)
    rng = random.Random(seed)
    tokens_by_id, hashes = {}, {}
    for identifier in identifiers(document_count):
        planted = planted_by_id.get(identifier, [])
        filler = [f"f{rng.randrange(FILLER_WORDS):03d}" for _ in range(tokens_per_document - len(planted))]
        tokens = planted + filler
        rng.shuffle(tokens)
        expected = tuple(tokens)
        # Großschreibung und Satztrenner prüfen die Aufbereitung gegen den Plan.
        encoded = (". ".join(token.upper() for token in expected) + ".\n").encode("utf-8")
        (root / identifier).write_bytes(encoded)
        tokens_by_id[identifier] = expected
        hashes[identifier] = hashlib.sha256(encoded).hexdigest()
    return GeneratedCorpus(root, tokens_by_id, membership, hashes)


def expected_and(membership: dict[str, tuple[str, ...]], terms: tuple[str, ...]) -> tuple[str, ...]:
    """Unabhängige Mengenoracle direkt auf dem Pflanzplan."""
    if not terms:
        raise ValueError("leere Anfrage")
    return tuple(sorted(set.intersection(*(set(membership.get(term, ())) for term in terms))))
