"""Feste Pflanzpläne und unabhängige Erwartungen für Phrasenversuche."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import random


FREQUENT = tuple(f"f{i:03d}" for i in range(5))
RARE = tuple(f"s{i:03d}" for i in range(5))
REPEATED = ("r000",) * 5
RESULT_SIZE = tuple(f"z{i:03d}" for i in range(5))
LENGTHS = (1, 2, 3, 5)


@dataclass(frozen=True)
class PhraseQuery:
    query_id: str
    tokens: tuple[str, ...]
    group: str
    expected: dict[str, list[int]]

    @property
    def text(self) -> str:
        # Uppercase deliberately includes central query normalization in timings.
        return " ".join(self.tokens).upper()


@dataclass(frozen=True)
class GeneratedCorpus:
    root: Path
    expected_tokens: dict[str, tuple[str, ...]]
    file_sha256: dict[str, str]
    planted_positions: dict[str, dict[str, list[int]]]
    recipe: dict


def expected_positions(tokens_by_id, phrase):
    """Oracle by tuple slices of the independent token plan, not production search."""
    width = len(phrase)
    if width == 0:
        raise ValueError("empty phrase")
    result = {}
    for identifier, tokens in sorted(tokens_by_id.items()):
        starts = [i for i in range(len(tokens) - width + 1) if tokens[i:i + width] == tuple(phrase)]
        if starts:
            result[identifier] = starts
    return result


def generate_corpus(root, *, document_count=200, tokens_per_document=500,
                    result_document_count=200, seed=20261006):
    """N/D/V and every unigram count stay constant across result size variants.

    f000..f004 occur together every 50 positions. r000 has a run of length six
    at20. s000..s004 occur only in the first two documents at30. z000..z004
    appear once in every document at40; order is forward in H documents and
    reverse elsewhere. Filler b000..b049 is seeded and guaranteed globally.
    All tokens have four ASCII characters. Uppercase and periods change no
    expected token or token position under the existing shared contract.
    """
    for name, value in (("document_count", document_count), ("tokens_per_document", tokens_per_document),
                        ("result_document_count", result_document_count), ("seed", seed)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be int")
    if document_count < 2 or tokens_per_document < 100 or tokens_per_document % 50:
        raise ValueError("at least2 documents and document length >=100 divisible by50 required")
    if not 0 <= result_document_count <= document_count:
        raise ValueError("result_document_count outside document range")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError("target must be empty")
    rng = random.Random(seed)
    expected, hashes, planted = {}, {}, {}
    guaranteed = 0
    for number in range(document_count):
        identifier = f"d{number:05d}.txt"
        tokens = [f"b{rng.randrange(50):03d}" for _ in range(tokens_per_document)]
        occupied = set()
        positions = {}
        for start in range(0, tokens_per_document, 50):
            tokens[start:start + 5] = FREQUENT
            occupied.update(range(start, start + 5))
        positions["frequent"] = list(range(0, tokens_per_document, 50))
        tokens[20:26] = ("r000",) * 6
        occupied.update(range(20, 26))
        positions["repeated"] = [20]
        if number < 2:
            tokens[30:35] = RARE
            occupied.update(range(30, 35))
            positions["rare"] = [30]
        order = RESULT_SIZE if number < result_document_count else RESULT_SIZE[::-1]
        tokens[40:45] = order
        occupied.update(range(40, 45))
        positions["result_size"] = [40] if number < result_document_count else []
        for position in range(tokens_per_document):
            if guaranteed < 50 and position not in occupied:
                tokens[position] = f"b{guaranteed:03d}"
                guaranteed += 1
        expected[identifier] = tuple(tokens)
        planted[identifier] = positions
        payload = (". ".join(token.upper() for token in tokens) + ".\n").encode("utf-8")
        (root / identifier).write_bytes(payload)
        hashes[identifier] = hashlib.sha256(payload).hexdigest()
    assert guaranteed == 50
    return GeneratedCorpus(root, expected, hashes, planted, {
        "document_count": document_count, "tokens_per_document": tokens_per_document,
        "result_document_count": result_document_count, "seed": seed,
    })


def synthetic_queries(generated, *, full=False):
    tokens = generated.expected_tokens
    queries = [PhraseQuery("result_size_k5", RESULT_SIZE, "result_size", {
        identifier: positions["result_size"][:] for identifier, positions in generated.planted_positions.items()
        if positions["result_size"]
    })]
    if full:
        for group, words in (("frequent", FREQUENT), ("rare", RARE), ("repeated", REPEATED),
                             ("unknown", ("x999",) * 5)):
            for length in LENGTHS:
                phrase = words[:length]
                # These structural expectations do not run a search algorithm.
                if group == "frequent":
                    expected = {identifier: plan["frequent"][:] for identifier, plan in generated.planted_positions.items()}
                elif group == "rare":
                    expected = {identifier: [30] for identifier, plan in generated.planted_positions.items() if "rare" in plan}
                elif group == "repeated":
                    expected = {identifier: list(range(20, 27 - length)) for identifier in tokens}
                else:
                    expected = {}
                assert expected_positions(tokens, phrase) == expected, "plant oracle inconsistent"
                queries.append(PhraseQuery(f"{group}_k{length}", phrase, group, expected))
        for length in (2, 3, 5):
            phrase = FREQUENT[:length][::-1]
            assert expected_positions(tokens, phrase) == {}
            queries.append(PhraseQuery(f"wrong_order_k{length}", phrase, "wrong_order", {}))
    assert expected_positions(tokens, RESULT_SIZE) == queries[0].expected
    return queries
