"""Deterministischer Pflanzplan; benutzt keine untersuchte Tokenisierung/Suche."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import random


@dataclass(frozen=True)
class GeneratedCorpus:
    root: Path
    total_tokens: int
    document_count: int
    base_vocabulary: int
    seed: int
    expected_tokens: dict[str, tuple[str, ...]]
    expected_hits: dict[str, tuple[str, ...]]
    expected_occurrences: dict[str, int]
    file_sha256: dict[str, str]


def generate_corpus(root: str | Path, total_tokens: int, *, document_count: int,
                    base_vocabulary: int, seed: int = 20261006) -> GeneratedCorpus:
    """Feste Länge; Fehler alle 100 Tokens, Verbindung am Ende der ersten Datei.

    Alle V Basiswörter werden zusätzlich einmal auf zufällig gewählten freien
    Positionen garantiert. Übrige Positionen stammen aus randrange(V). Diese
    Garantie verhindert einen nur nominell, aber nicht erreicht variierten V.
    Erwartete Tokens entstehen direkt aus ASCII-Wörtern und zwei Pflanzwörtern.
    """
    for name, value in (("total_tokens", total_tokens), ("document_count", document_count),
                        ("base_vocabulary", base_vocabulary), ("seed", seed)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} muss eine ganze Zahl sein")
    if document_count <= 0 or total_tokens < 2 * document_count or total_tokens % document_count:
        raise ValueError("positive Dokumentzahl und mindestens zwei gleich verteilte Tokens erforderlich")
    length = total_tokens // document_count
    if (length - 1) % 100 == 0:
        raise ValueError("letzte Position kollidiert mit dem gepflanzten Fehler")
    free_positions = [p for p in range(total_tokens)
                      if p % length % 100 != 0 and p != length - 1]
    if base_vocabulary <= 0 or base_vocabulary > len(free_positions):
        raise ValueError("Basiswortschatz muss positiv und auf freien Positionen erreichbar sein")
    target = Path(root)
    target.mkdir(parents=True, exist_ok=True)
    if any(target.iterdir()):
        raise ValueError("Zielverzeichnis muss leer sein")
    rng = random.Random(seed)
    words = [f"wort{rng.randrange(base_vocabulary):05d}" for _ in range(total_tokens)]
    for word, position in enumerate(rng.sample(free_positions, base_vocabulary)):
        words[position] = f"wort{word:05d}"
    expected_tokens, hashes = {}, {}
    width = max(2, len(str(document_count - 1)))
    for number in range(document_count):
        name = f"doc{number:0{width}d}.txt"
        part = words[number * length:(number + 1) * length]
        for position in range(0, length, 100):
            part[position] = "Fehler"
        if number == 0:
            part[-1] = "Verbindung"
        payload = (" ".join(part) + "\n").encode("utf-8")
        (target / name).write_bytes(payload)
        hashes[name] = hashlib.sha256(payload).hexdigest()
        expected_tokens[name] = tuple(
            "fehler" if word == "Fehler" else "verbindung" if word == "Verbindung" else word
            for word in part
        )
    identifiers = tuple(expected_tokens)
    return GeneratedCorpus(target, total_tokens, document_count, base_vocabulary, seed,
                           expected_tokens,
                           {"frequent": identifiers, "rare": (identifiers[0],), "missing": ()},
                           {"frequent": document_count * ((length - 1) // 100 + 1),
                            "rare": 1, "missing": 0}, hashes)
