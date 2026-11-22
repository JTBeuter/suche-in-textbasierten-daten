"""Unabhängige Mengenoracles ausschließlich im Test, feste Tokens und Seeds."""

import itertools
import json
from pathlib import Path
import random

import pytest

from gemeinsam import CorpusError, QueryError, RawDocument, load_corpus, prepare_corpus
from direkte_suche import search_direct_word
from invertierter_index import build_inverted_index, search_index_word
from boolesche_suche import (
    intersect_sorted, union_sorted, normalize_terms, normalize_boolean_query,
    search_direct_boolean, search_index_boolean,
)


ROOT = Path(__file__).resolve().parents[3]
CASES = [
    ([], []), ([], ["D0.txt"]), (["D0.txt"], []),
    (["D0.txt", "D2.txt"], ["D0.txt", "D2.txt"]),
    (["D0.txt", "D2.txt"], ["D1.txt", "D3.txt"]),
    (["D0.txt", "D2.txt", "D4.txt"], ["D1.txt", "D2.txt", "D5.txt"]),
    (["D0.txt"], [f"D{i:03d}.txt" for i in range(100)]),
    (["D0.txt", "D5.txt"], ["D0.txt", "D1.txt", "D2.txt"]),
    (["D0.txt", "D5.txt"], ["D1.txt", "D3.txt", "D5.txt"]),
    (["D0.txt", "D1.txt", "D7.txt"], ["D0.txt", "D1.txt"]),
    (["D0.txt", "D1.txt"], ["D0.txt", "D1.txt", "D7.txt"]),
]


@pytest.mark.parametrize("left,right", CASES)
def test_isolated_operations_and_input_preservation(left, right):
    saved = (left.copy(), right.copy())
    assert intersect_sorted(left, tuple(right)) == sorted(set(left) & set(right))
    assert union_sorted(tuple(left), right) == sorted(set(left) | set(right))
    assert (left, right) == saved


@pytest.mark.parametrize("seed", [0, 17, 193, 20261006])
def test_random_lists_against_set_oracle(seed):
    rng = random.Random(seed)
    universe = [f"pfad/{i:03d}.txt" for i in range(180)]
    for case in range(200):
        left = sorted(rng.sample(universe, rng.randrange(len(universe) + 1)))
        right = sorted(rng.sample(universe, rng.randrange(len(universe) + 1)))
        context = f"seed={seed}, case={case}, left={left}, right={right}"
        assert intersect_sorted(left, right) == sorted(set(left) & set(right)), context
        assert union_sorted(left, right) == sorted(set(left) | set(right)), context


@pytest.fixture
def fixture_corpus():
    corpus = prepare_corpus(load_corpus(ROOT / "daten/beispiele/d0_d5"))
    known = json.loads((ROOT / "daten/beispiele/d0_d5_expected.json").read_text())
    assert {doc.document_id: list(doc.tokens) for doc in corpus} == known["tokens"]
    return corpus


def assert_all(corpus, terms, operator, expected):
    index = build_inverted_index(corpus)
    assert search_direct_boolean(corpus, terms, operator) == expected
    assert search_index_boolean(index, terms, operator, "input_order") == expected
    if operator == "AND":
        assert search_index_boolean(index, terms, operator, "shortest_first") == expected


@pytest.mark.parametrize("terms,operator,expected", [
    (["Verbindung", "Server"], "AND", ["D0.txt", "D2.txt", "D3.txt"]),
    (["Verbindung", "Server"], "OR", ["D0.txt", "D1.txt", "D2.txt", "D3.txt"]),
    (["Fehler", "Verbindung", "Server"], "AND", ["D0.txt", "D2.txt"]),
    (["Verbindung", "unbekannt"], "AND", []),
    (["unbekannt", "Verbindung"], "OR", ["D0.txt", "D1.txt", "D2.txt", "D3.txt"]),
    (["unbekannt", "fehlt"], "OR", []),
    (["Fehler", "FEHLER!", "Fehler", "Server"], "AND", ["D0.txt", "D2.txt"]),
    (["a", "a"], "OR", ["D5.txt"]),
    (["Serverfehler", "Server"], "AND", []),
    (["Serverfehler", "Server"], "OR", ["D0.txt", "D1.txt", "D2.txt", "D3.txt"]),
])
def test_known_document_semantics(fixture_corpus, terms, operator, expected):
    assert_all(fixture_corpus, terms, operator, expected)


def test_normalization_counts_order_and_unicode():
    query = normalize_boolean_query(["SERVER", "Straße", "STRASSE!", "Äpfel", "A\u0308pfel", "server"], "AND")
    assert query.terms == ("server", "strasse", "äpfel")
    assert query.original_term_count == 6
    assert query.effective_term_count == 3
    assert normalize_terms(iter(["beta", "ALPHA", "beta", "alpha"])) == ("beta", "alpha")
    corpus = prepare_corpus([RawDocument("u.txt", "u.txt", "Straße STRASSE Äpfel A\u0308pfel")])
    assert corpus[0].tokens == ("strasse", "strasse", "äpfel", "äpfel")
    assert_all(corpus, ["STRASSE", "Straße", "A\u0308pfel"], "AND", ["u.txt"])


@pytest.mark.parametrize("operator", ["AND", "OR"])
def test_empty_corpus_and_empty_document(operator):
    assert_all((), ["Server"], operator, [])
    corpus = prepare_corpus([RawDocument("empty.txt", "empty.txt", "")])
    assert corpus[0].tokens == ()
    assert_all(corpus, ["Server", "Fehler"], operator, [])


@pytest.mark.parametrize("word", ["Fehler!", "Server", "a", "abwesend"])
@pytest.mark.parametrize("operator", ["AND", "OR"])
def test_one_term_equals_word_search(fixture_corpus, word, operator):
    index = build_inverted_index(fixture_corpus)
    expected = search_direct_word(fixture_corpus, word)
    assert search_index_word(index, word) == expected
    assert_all(fixture_corpus, [word], operator, expected)


@pytest.mark.parametrize("terms", [[], iter(()), "Fehler", b"fehler", None, 3,
                                      [""], ["..."], ["Fehler Server"], ["E-Mail"], [1], [None]])
def test_invalid_terms_are_explained(terms):
    # Separate iterables because valid generators are consumed once by contract.
    with pytest.raises(QueryError):
        normalize_boolean_query(terms, "AND")


@pytest.mark.parametrize("operator", ["AND", "OR"])
@pytest.mark.parametrize("terms", [[], [""], ["Fehler Server"]])
def test_public_searches_reject_empty_or_invalid_requests(operator, terms):
    with pytest.raises(QueryError):
        search_direct_boolean((), terms, operator)
    with pytest.raises(QueryError):
        search_index_boolean(build_inverted_index(()), terms, operator)


@pytest.mark.parametrize("operator", ["", "and", "NOT", "XOR", "AND OR", None, 1])
def test_invalid_operator_rejected_even_for_empty_corpus(operator):
    with pytest.raises(QueryError):
        search_direct_boolean((), ["wort"], operator)
    with pytest.raises(QueryError):
        search_index_boolean(build_inverted_index(()), ["wort"], operator)


@pytest.mark.parametrize("variant", ["", "bad", None, 1])
def test_invalid_variant_rejected(variant):
    with pytest.raises(QueryError):
        search_index_boolean(build_inverted_index(()), ["wort"], "AND", variant)


def test_or_shortest_first_is_an_explained_error():
    with pytest.raises(QueryError, match="OR"):
        search_index_boolean(build_inverted_index(()), ["wort"], "OR", "shortest_first")


@pytest.mark.parametrize("corpus", [None, "corpus", b"corpus", ["doc"], [RawDocument("a.txt", "a.txt", "a")]])
def test_invalid_direct_corpus_has_corpus_error(corpus):
    with pytest.raises(CorpusError):
        search_direct_boolean(corpus, ["a"], "OR")


def test_output_mutation_and_query_sequences_do_not_change_index(fixture_corpus):
    index = build_inverted_index(fixture_corpus)
    before = dict(index)
    identities = {word: id(posting) for word, posting in index.items()}
    queries = [(["Verbindung", "Server"], "AND"), (["a"], "OR"),
               (["Fehler", "unbekannt"], "OR"), (["unbekannt", "Server"], "AND")]
    for terms, operator in queries * 3:
        expected = search_direct_boolean(fixture_corpus, terms, operator)
        changed_direct_result = search_direct_boolean(fixture_corpus, terms, operator)
        changed_direct_result.clear()
        changed_direct_result.append("manipuliert.txt")
        assert search_direct_boolean(fixture_corpus, terms, operator) == expected
        variants = ("input_order", "shortest_first") if operator == "AND" else ("input_order",)
        for variant in variants:
            result = search_index_boolean(index, terms, operator, variant)
            assert type(result) is list
            result.clear()
            result.append("manipuliert.txt")
            assert search_index_boolean(index, terms, operator, variant) == expected
        assert dict(index) == before
        assert {word: id(posting) for word, posting in index.items()} == identities


def test_direct_reference_uses_no_posting_access(fixture_corpus, monkeypatch):
    import boolesche_suche.search as module

    def fail(*args):
        raise AssertionError("Direkte Referenz darf keine Postingliste lesen")

    monkeypatch.setattr(module, "get_postings", fail)
    assert search_direct_boolean(fixture_corpus, ["Server", "Verbindung"], "AND") == ["D0.txt", "D2.txt", "D3.txt"]


@pytest.mark.parametrize("seed", [1, 23, 91, 193, 1201, 20261006])
def test_generated_corpora_independent_oracle_and_invariants(seed):
    rng = random.Random(seed)
    vocabulary = ("alpha", "beta", "server", "verbindung", "fehler", "strasse", "äpfel", "2026")
    raw_forms = {"alpha": "ALPHA", "beta": "beta", "server": "SERVER", "verbindung": "Verbindung",
                 "fehler": "Fehler!", "strasse": "Straße", "äpfel": "A\u0308pfel", "2026": "2026"}
    planned = {f"doc{i:02d}.txt": tuple(rng.choice(vocabulary) for _ in range(rng.randrange(25)))
               for i in range(20)}
    raw = [RawDocument(identifier, identifier, " - ".join(raw_forms[token] for token in tokens))
           for identifier, tokens in planned.items()]
    rng.shuffle(raw)
    corpus = prepare_corpus(raw)
    assert {doc.document_id: doc.tokens for doc in corpus} == planned, f"Tokenplan seed={seed}"
    index = build_inverted_index(reversed(corpus))
    before = dict(index)
    for case in range(30):
        canonical = rng.sample([*vocabulary, "unauffindbar"], rng.choice([1, 2, 3, 5]))
        terms = [raw_forms.get(token, token) for token in canonical]
        terms += [terms[0], terms[-1]]
        wanted = set(canonical)
        single = [{identifier for identifier, tokens in planned.items() if word in tokens} for word in canonical]
        for operator in ("AND", "OR"):
            expected = sorted(identifier for identifier, tokens in planned.items()
                              if (wanted <= set(tokens) if operator == "AND" else bool(wanted & set(tokens))))
            context = f"seed={seed}, case={case}, operator={operator}, terms={terms}, corpus={planned}"
            assert search_direct_boolean(reversed(corpus), iter(terms), operator) == expected, context
            variants = ("input_order", "shortest_first") if operator == "AND" else ("input_order",)
            orders = list(itertools.permutations(canonical)) if len(canonical) <= 3 else [canonical, list(reversed(canonical))]
            for variant in variants:
                assert search_index_boolean(index, iter(terms), operator, variant) == expected, context
                for order in orders:
                    assert search_index_boolean(index, order, operator, variant) == expected, context
                assert search_index_boolean(index, canonical * 2, operator, variant) == expected, context
            for ids in single:
                assert (set(expected) <= ids if operator == "AND" else ids <= set(expected)), context
        assert dict(index) == before


def test_real_corpus_boolean_samples_have_independent_oracle():
    corpus = prepare_corpus(load_corpus(ROOT / "daten/real/kafka_verwandlung"))
    manifest = json.loads((ROOT / "daten/real/kafka_verwandlung/manifest.json").read_text())
    assert corpus[0].tokens[:20] == tuple(manifest["expected_prefix_tokens"])
    for terms, operator, expected in [
        (["Gregor", "Fenster"], "AND", ["01_anfang.txt"]),
        (["Gregor", "Unauffindbar"], "AND", []),
        (["Unauffindbar", "Fenster"], "OR", ["01_anfang.txt"]),
        (["Unauffindbar", "Nichtvorhanden"], "OR", []),
    ]:
        assert_all(corpus, terms, operator, expected)
