import json
import random
from pathlib import Path

import pytest

from direkte_suche import search_direct_substring, search_direct_word
from gemeinsam import CorpusError, PreparedDocument, QueryError, RawDocument, load_corpus, prepare_corpus


ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "daten" / "beispiele" / "d0_d5"
EXPECTED = json.loads((ROOT / "daten" / "beispiele" / "d0_d5_expected.json").read_text(encoding="utf-8"))


def test_example_tokens_against_handcomputed_fixture():
    prepared = prepare_corpus(load_corpus(EXAMPLES))
    assert {doc.document_id: list(doc.tokens) for doc in prepared} == EXPECTED["tokens"]


@pytest.mark.parametrize(("query", "expected"), EXPECTED["word_matches"].items())
def test_example_word_results_against_handcomputed_fixture(query, expected):
    assert search_direct_word(prepare_corpus(load_corpus(EXAMPLES)), query) == expected


def test_substring_semantics_includes_serverfehler():
    raw = load_corpus(EXAMPLES)
    assert search_direct_substring(raw, "Fehler") == EXPECTED["substring_matches"]["Fehler"]
    assert search_direct_word(prepare_corpus(raw), "Fehler") == ["D0.txt", "D2.txt"]


def test_phrase_fixtures_preserve_positions_sentence_and_document_boundaries():
    # This only verifies the hand fixture against token windows, and does not
    # implement the later project's public phrase-search API.
    prepared = prepare_corpus(load_corpus(EXAMPLES))
    for phrase, expected in EXPECTED["phrase_positions"].items():
        words = tuple(phrase.casefold().split())
        actual = {}
        for document in prepared:
            starts = [
                index
                for index in range(len(document.tokens) - len(words) + 1)
                if document.tokens[index : index + len(words)] == words
            ]
            if starts:
                actual[document.document_id] = starts
        assert actual == expected
    # D0 ends with server and D1 starts with serverfehler. They stay separate.
    assert all("server serverfehler" not in " ".join(doc.tokens) for doc in prepared)


def test_casefold_and_canonical_unicode_have_expected_document_hits():
    raw = (
        RawDocument("a.txt", "a.txt", "Straße Äpfel"),
        RawDocument("b.txt", "b.txt", "STRASSE A\u0308pfel"),
        RawDocument("c.txt", "c.txt", "Strassen Apfel"),
    )
    prepared = prepare_corpus(raw)
    for query in ("Straße", "STRASSE", "strasse"):
        assert search_direct_word(prepared, query) == ["a.txt", "b.txt"]
    for query in ("Äpfel", "A\u0308pfel"):
        assert search_direct_word(prepared, query) == ["a.txt", "b.txt"]
    assert search_direct_word(prepared, "Apfel") == ["c.txt"]


def test_empty_corpus_and_repeated_tokens():
    assert search_direct_word((), "fehler") == []
    raw = [RawDocument("a.txt", "a.txt", "fehler fehler fehler"), RawDocument("b.txt", "b.txt", "")]
    assert search_direct_word(prepare_corpus(raw), "FEHLER") == ["a.txt"]
    assert search_direct_substring((), "fehler") == []


def test_unknown_word_is_valid_and_has_no_hits():
    assert search_direct_word(prepare_corpus(load_corpus(EXAMPLES)), "abwesend") == []


@pytest.mark.parametrize("invalid", ["", "—...", " ", "Fehler Server", None, 42])
def test_invalid_word_queries_raise_even_for_empty_corpus(invalid):
    with pytest.raises(QueryError):
        search_direct_word((), invalid)


@pytest.mark.parametrize("invalid", ["", None, 42])
def test_substring_rejects_empty_or_non_string_query(invalid):
    with pytest.raises(QueryError):
        search_direct_substring((), invalid)


def test_substring_can_search_exact_spaces_and_punctuation():
    raw = (RawDocument("a.txt", "a.txt", "Fehler!\n Straße"),)
    assert search_direct_substring(raw, "!\n ") == ["a.txt"]
    assert search_direct_substring(raw, "STRASSE") == ["a.txt"]
    assert search_direct_substring(raw, "fehler straße") == []


def test_wrong_document_type_is_explained():
    raw = (RawDocument("a.txt", "a.txt", "fehler"),)
    with pytest.raises(CorpusError, match="PreparedDocument"):
        search_direct_word(raw, "fehler")
    with pytest.raises(CorpusError, match="RawDocument"):
        search_direct_substring(prepare_corpus(raw), "fehler")


def test_generated_planted_hits_are_independent_of_normalization_and_search():
    rng = random.Random(20261006)
    tags = ("alpha", "beta", "gamma", "delta")
    expected = {tag: [] for tag in tags}
    expected["absent"] = []
    raw = []
    for index in range(41):
        identifier = f"nested/doc{index:02d}.txt"
        planted = [tag for tag in tags if rng.random() < 0.38]
        for tag in planted:
            expected[tag].append(identifier)
        # Noise never includes a tag. Expectations depend on planting decisions,
        # not on a second tokenizer, regex, substring search or shared code.
        words = ["noise"] * rng.randrange(0, 20)
        for tag in planted:
            words.extend([tag.upper()] * rng.randrange(1, 5))
        rng.shuffle(words)
        raw.append(RawDocument(identifier, identifier, ",\n".join(words)))
    rng.shuffle(raw)
    original = tuple(raw)
    prepared = prepare_corpus(raw)
    for query, hits in expected.items():
        result = search_direct_word(prepared, query)
        assert result == hits
        assert result == sorted(set(result))
        assert search_direct_word(reversed(prepared), query.upper()) == hits
    assert tuple(raw) == original
    assert prepare_corpus(reversed(raw)) == prepared


def test_duplicate_input_documents_still_produce_unique_sorted_results():
    # Normal production input passes prepare_corpus and has unique IDs.
    prepared = prepare_corpus([RawDocument("b.txt", "b.txt", "a"), RawDocument("a.txt", "a.txt", "a")])
    assert search_direct_word((*prepared, prepared[0]), "a") == ["a.txt", "b.txt"]


def test_word_reference_compares_in_sequence_and_stops_at_first_hit():
    comparisons = []

    class ObservedToken(str):
        def __eq__(self, other):
            comparisons.append(str(self))
            if str(self) == "unreachable":
                raise AssertionError("Tokens nach dem ersten Treffer dürfen nicht verglichen werden.")
            return str.__eq__(self, other)
    document = PreparedDocument(
        "a.txt", "a.txt", "before target unreachable",
        tuple(ObservedToken(word) for word in ("before", "target", "unreachable")),
    )
    assert search_direct_word((document,), "target") == ["a.txt"]
    assert comparisons == ["before", "target"]
