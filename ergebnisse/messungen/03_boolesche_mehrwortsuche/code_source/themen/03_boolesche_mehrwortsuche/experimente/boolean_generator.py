"""Deterministischer Pflanzplan; Erwartungen entstehen vor der Aufbereitung."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import random


GROUPS = {
    "rare": tuple(f"q{i:03d}" for i in range(0, 5)),
    "frequent": tuple(f"q{i:03d}" for i in range(5, 10)),
    "mixed": tuple(f"q{i:03d}" for i in range(10, 15)),
    "unknown": ("q005", "q999", "q006", "q007", "q008"),
    "disjoint": tuple(f"q{i:03d}" for i in range(15, 20)),
    "high_overlap": tuple(f"q{i:03d}" for i in range(20, 25)),
    "low_overlap": tuple(f"q{i:03d}" for i in range(25, 30)),
}


@dataclass(frozen=True)
class GeneratedCorpus:
    root: Path
    expected_tokens: dict[str, tuple[str, ...]]
    membership: dict[str, tuple[str, ...]]
    file_sha256: dict[str, str]


def membership_plan(document_count: int) -> dict[str, tuple[str, ...]]:
    """Feste relative Häufigkeiten und kontrollierte Überschneidungen.

    Anzahl muss durch 100 teilbar sein, damit alle Häufigkeiten exakt bleiben.
    Kennungen werden aus dem Pflanzplan gebildet, nicht aus einem Suchindex.
    """
    if isinstance(document_count, bool) or not isinstance(document_count, int):
        raise TypeError("document_count muss eine ganze Zahl sein")
    if document_count < 100 or document_count % 100:
        raise ValueError("document_count muss positiv und durch 100 teilbar sein")
    identifiers = tuple(f"d{i:05d}.txt" for i in range(document_count))
    n = document_count
    result = {"q999": ()}
    for i in range(5):
        # Seltene Listen haben gleiche Länge, schmale gemeinsame Bereiche.
        result[GROUPS["rare"][i]] = identifiers[i * n // 500:i * n // 500 + n // 50]
        result[GROUPS["frequent"][i]] = tuple(identifier for j, identifier in enumerate(identifiers)
                                                    if j % 10 != i)
        size = (95, 75, 50, 10, 1)[i] * n // 100
        result[GROUPS["mixed"][i]] = identifiers[:size]
        result[GROUPS["disjoint"][i]] = identifiers[i * n // 10:(i + 1) * n // 10]
        result[GROUPS["high_overlap"][i]] = identifiers[:3 * n // 5]
    result["q025"] = identifiers[:n // 2]
    result["q026"] = identifiers[49 * n // 100:99 * n // 100]
    result["q027"] = identifiers[:n // 4] + identifiers[3 * n // 4:]
    result["q028"] = identifiers[n // 4:3 * n // 4]
    result["q029"] = tuple(identifier for j, identifier in enumerate(identifiers) if j % 2 == 0)
    return result


def generate_corpus(root: Path, *, document_count: int = 1000,
                    tokens_per_document: int = 100, seed: int = 20261006) -> GeneratedCorpus:
    for name, value in (("tokens_per_document", tokens_per_document), ("seed", seed)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} muss eine ganze Zahl sein")
    membership = membership_plan(document_count)
    if tokens_per_document < 40:
        raise ValueError("mindestens 40 Tokens pro Dokument erforderlich")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError("Zielverzeichnis muss leer sein")
    membership_sets = {term: set(ids) for term, ids in membership.items()}
    rng = random.Random(seed)
    tokens_by_id, hashes = {}, {}
    for i in range(document_count):
        identifier = f"d{i:05d}.txt"
        planted = [term for term in sorted(membership) if identifier in membership_sets[term]]
        filler = [f"f{rng.randrange(50):03d}" for _ in range(tokens_per_document - len(planted))]
        tokens = planted + filler
        rng.shuffle(tokens)
        expected = tuple(tokens)
        # Großschreibung + Satztrenner prüfen Aufbereitung gegen den Pflanzplan.
        encoded = (". ".join(token.upper() for token in expected) + ".\n").encode("utf-8")
        (root / identifier).write_bytes(encoded)
        tokens_by_id[identifier] = expected
        hashes[identifier] = hashlib.sha256(encoded).hexdigest()
    return GeneratedCorpus(root, tokens_by_id, membership, hashes)


def expected_hits(membership: dict[str, tuple[str, ...]], terms: tuple[str, ...], operator: str) -> tuple[str, ...]:
    """Unabhängige Mengenoracle direkt auf dem Pflanzplan."""
    lists = [set(membership.get(term, ())) for term in terms]
    if not lists:
        raise ValueError("leere Anfrage")
    if operator == "AND":
        return tuple(sorted(set.intersection(*lists)))
    if operator == "OR":
        return tuple(sorted(set.union(*lists)))
    raise ValueError("unbekannter Operator")
