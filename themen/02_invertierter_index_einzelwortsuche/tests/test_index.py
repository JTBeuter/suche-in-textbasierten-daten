"""Hand fixtures and a document scan independently verify every posting."""

from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from pathlib import Path
import random

import pytest

from direkte_suche import search_direct_word
from gemeinsam import CorpusError, PreparedDocument, QueryError, RawDocument, load_corpus, prepare_corpus
from invertierter_index import InvertedIndex, build_inverted_index, get_postings, search_index_word


ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "daten" / "beispiele" / "d0_d5"

# These values are transcribed from the plan, not produced by any tokenizer.
HAND_TOKENS = {
    "D0.txt": ("fehler", "bei", "der", "verbindung", "zum", "server"),
    "D1.txt": ("serverfehler", "ohne", "verbindung"),
    "D2.txt": ("verbindung", "zum", "server", "fehler", "fehler"),
    "D3.txt": ("server", "ohne", "verbindung"),
    "D4.txt": (),
    "D5.txt": ("a", "a", "a"),
}
HAND_INDEX = {
    "a": ("D5.txt",),
    "bei": ("D0.txt",),
    "der": ("D0.txt",),
    "fehler": ("D0.txt", "D2.txt"),
    "ohne": ("D1.txt", "D3.txt"),
    "server": ("D0.txt", "D2.txt", "D3.txt"),
    "serverfehler": ("D1.txt",),
    "verbindung": ("D0.txt", "D1.txt", "D2.txt", "D3.txt"),
    "zum": ("D0.txt", "D2.txt"),
}


def prepared(document_id, tokens, raw_text="unchanged source"):
    return PreparedDocument(document_id, document_id, raw_text, tuple(tokens))


def scan_documents(documents, token):
    """Simple test oracle: inspect documents, with no index access or helpers."""
    matches = []
    for document in documents:
        for candidate in document.tokens:
            if candidate == token:
                matches.append(document.document_id)
                break
    return sorted(matches)


@pytest.fixture
def hand_documents():
    return tuple(prepared(identifier, tokens) for identifier, tokens in HAND_TOKENS.items())


def test_handcomputed_complete_index(hand_documents):
    index = build_inverted_index(hand_documents)
    assert isinstance(index, InvertedIndex)
    assert isinstance(index, Mapping)
    assert dict(index.items()) == HAND_INDEX
    assert len(index) == len(HAND_INDEX)
    assert set(index) == set(HAND_INDEX)
    for token, postings in HAND_INDEX.items():
        assert index[token] == postings
        assert get_postings(index, token) == postings
        assert search_index_word(index, token) == list(postings)
    assert search_index_word(index, "Fehler") == ["D0.txt", "D2.txt"]
    assert "D1.txt" not in search_index_word(index, "Fehler")


def test_example_files_preserve_handcomputed_tokens_and_postings():
    documents = prepare_corpus(load_corpus(EXAMPLES))
    assert {document.document_id: document.tokens for document in documents} == HAND_TOKENS
    assert dict(build_inverted_index(documents).items()) == HAND_INDEX


@pytest.mark.parametrize("query", ["fehler", "Fehler", "FEHLER", "Fehler!", "\nFehler\t"])
def test_public_search_uses_shared_word_normalization(hand_documents, query):
    assert search_index_word(build_inverted_index(hand_documents), query) == ["D0.txt", "D2.txt"]


@pytest.mark.parametrize("documents", [(), [], iter(())])
def test_empty_corpus_produces_empty_index(documents):
    index = build_inverted_index(documents)
    assert dict(index.items()) == {}
    assert get_postings(index, "fehler") == ()
    assert search_index_word(index, "Fehler") == []


def test_empty_documents_create_no_keys_and_repetition_creates_one_hit():
    documents = (
        prepared("z.txt", ()),
        prepared("m.txt", ("a", "a", "a")),
        prepared("a.txt", ("a",)),
        prepared("b.txt", ()),
    )
    assert dict(build_inverted_index(documents).items()) == {"a": ("a.txt", "m.txt")}


def test_build_accepts_unsorted_single_use_generator_and_sorts_ids_lexicographically():
    documents = [
        prepared("doc2.txt", ("a", "a")),
        prepared("nested/a.txt", ("a",)),
        prepared("doc10.txt", ("a",)),
        prepared("A.txt", ("a",)),
    ]
    expected = ("A.txt", "doc10.txt", "doc2.txt", "nested/a.txt")
    assert get_postings(build_inverted_index(document for document in documents), "a") == expected
    assert get_postings(build_inverted_index(reversed(documents)), "a") == expected


def test_build_does_not_modify_or_retain_mutable_input_container(hand_documents):
    original = tuple(hand_documents)
    documents = list(reversed(hand_documents))
    before = tuple(documents)
    index = build_inverted_index(documents)
    assert tuple(documents) == before
    assert tuple(hand_documents) == original
    assert dict(index.items()) == HAND_INDEX
    documents.clear()
    documents.append(prepared("later.txt", ("later",)))
    assert dict(index.items()) == HAND_INDEX
    with pytest.raises(FrozenInstanceError):
        original[0].tokens = ("changed",)


def test_factory_uses_prepared_tokens_without_retokenizing_raw_source():
    # Prepared input is the agreed boundary; raw_text is retained provenance.
    document = prepared("a.txt", ("a",), raw_text="Fehler Fehler")
    index = build_inverted_index((document,))
    assert dict(index.items()) == {"a": ("a.txt",)}
    assert search_index_word(index, "Fehler") == []


@pytest.mark.parametrize("invalid", [None, 42, True, "a", b"a", object()])
def test_factory_rejects_non_corpus_values(invalid):
    with pytest.raises(CorpusError):
        build_inverted_index(invalid)


@pytest.mark.parametrize("invalid", [None, 42, "a", {}, RawDocument("a.txt", "a.txt", "a")])
def test_factory_rejects_non_prepared_elements(invalid):
    with pytest.raises(CorpusError):
        build_inverted_index((prepared("valid.txt", ("a",)), invalid))


@pytest.mark.parametrize("tokens", [(), ("a",), ("b",)])
def test_duplicate_document_ids_are_rejected_even_for_empty_or_different_docs(tokens):
    documents = (prepared("a.txt", ("a",)), prepared("a.txt", tokens))
    with pytest.raises(CorpusError, match="Doppelte"):
        build_inverted_index(document for document in documents)


@pytest.mark.parametrize(
    "token",
    ["FEHLER", "Straße", "A\u0308pfel", "a b", "a-b", "a_b", "a!", " a ",
     "—", "²", "Ⅲ", "x²y", "q\u0307r", "İx", "\x00"],
)
def test_factory_rejects_non_normalized_or_non_token_prepared_entries(token):
    # The shared model accepts nonempty strings. The builder checks token rules.
    document = prepared("a.txt", ("valid", token))
    with pytest.raises(CorpusError):
        build_inverted_index((document,))


@pytest.mark.parametrize("token", ["fehler", "strasse", "äpfel", "007", "١٢३", "東京", "жук", "σ"])
def test_valid_normalized_unicode_tokens_are_accepted(token):
    index = build_inverted_index((prepared("a.txt", (token, token)),))
    assert index[token] == ("a.txt",)
    assert get_postings(index, token) == ("a.txt",)


@pytest.mark.parametrize("query", ["", " ", "...!", "_—!\n", "Fehler Server", "E-Mail", "İx", None, 42, True, b"a", ["a"]])
def test_public_search_rejects_invalid_queries_even_for_empty_index(query):
    with pytest.raises(QueryError):
        search_index_word(build_inverted_index(()), query)


@pytest.mark.parametrize("token", ["", " ", "Fehler", "FEHLER", "Fehler!", "fehler!", " fehler ", "a b", "a-b", "Straße", "A\u0308pfel", "x²y", None, 42, True, b"a", ["a"]])
def test_posting_reader_rejects_raw_or_invalid_core_queries(token):
    with pytest.raises(QueryError):
        get_postings(build_inverted_index(()), token)


def test_unknown_valid_word_and_missing_mapping_key(hand_documents):
    index = build_inverted_index(hand_documents)
    assert get_postings(index, "abwesend") == ()
    assert search_index_word(index, "Abwesend!") == []
    with pytest.raises(KeyError):
        index["abwesend"]


def test_mapping_and_postings_cannot_be_modified(hand_documents):
    index = build_inverted_index(hand_documents)
    before = dict(index.items())
    with pytest.raises(TypeError):
        index["fehler"] = ("other.txt",)
    with pytest.raises(TypeError):
        del index["fehler"]
    postings = get_postings(index, "fehler")
    assert isinstance(postings, tuple)
    with pytest.raises(TypeError):
        postings[0] = "other.txt"
    copy = dict(index.items())
    copy["fehler"] = ("other.txt",)
    assert dict(index.items()) == before


def test_index_constructor_and_storage_are_guarded(hand_documents):
    with pytest.raises(TypeError, match="build_inverted_index"):
        InvertedIndex()
    index = build_inverted_index(hand_documents)
    with pytest.raises(FrozenInstanceError):
        index._postings = {"injected": ("other.txt",)}
    with pytest.raises(TypeError):
        index._postings["injected"] = ("other.txt",)
    assert dict(index.items()) == HAND_INDEX


def test_results_are_independent_materialized_lists_including_unknown_words(hand_documents):
    index = build_inverted_index(hand_documents)
    for query in ("Fehler", "unbekannt"):
        first = search_index_word(index, query)
        second = search_index_word(index, query)
        assert isinstance(first, list)
        assert first == second
        assert first is not second
        first.clear()
        first.append("injected.txt")
        first.reverse()
        assert search_index_word(index, query) == second
    assert dict(index.items()) == HAND_INDEX


def test_reordered_repeated_queries_never_change_index(hand_documents):
    index = build_inverted_index(hand_documents)
    before = tuple(index.items())
    queries = list(HAND_INDEX) + ["abwesend", "Fehler!", "SERVER"]
    for seed in (7, 19, 20261006):
        random.Random(seed).shuffle(queries)
        for query in queries:
            assert search_index_word(index, query) == search_direct_word(hand_documents, query)
        assert tuple(index.items()) == before


@pytest.mark.parametrize(
    ("raw", "tokens", "query", "hits"),
    [
        ("Straße STRASSE großes", ("strasse", "strasse", "grosses"), "STRAẞE!", ["a.txt"]),
        ("Äpfel A\u0308pfel", ("äpfel", "äpfel"), "A\u0308pfel", ["a.txt"]),
        ("Fehler, bei\tder\nVerbindung. Zum Server!", ("fehler", "bei", "der", "verbindung", "zum", "server"), "FEHLER!", ["a.txt"]),
        ("E-Mail Fehler_Code foo—bar", ("e", "mail", "fehler", "code", "foo", "bar"), "Mail", ["a.txt"]),
        ("abc42 007 ١٢३", ("abc42", "007", "١٢३"), "١٢३", ["a.txt"]),
        ("x²y Ⅲ vier", ("x", "y", "vier"), "x", ["a.txt"]),
        ("q\u0307r İx a\u034fb", ("q", "r", "i", "x", "a", "b"), "r", ["a.txt"]),
        ("東京 中文 ЖУК Σ σ ς", ("東京", "中文", "жук", "σ", "σ", "σ"), "ς", ["a.txt"]),
        ("ﬃ", ("ffi",), "FFI", ["a.txt"]),
        ("läuft laufen", ("läuft", "laufen"), "lauf", []),
    ],
)
def test_shared_unicode_punctuation_and_whole_token_semantics_have_fixed_expectations(raw, tokens, query, hits):
    documents = prepare_corpus((RawDocument("a.txt", "a.txt", raw),))
    assert documents[0].tokens == tokens
    index = build_inverted_index(documents)
    assert search_index_word(index, query) == hits
    for token in set(tokens):
        assert get_postings(index, token) == ("a.txt",)


@pytest.mark.parametrize(
    ("seed", "document_count", "max_length", "vocabulary_size", "max_repeat"),
    [
        (0, 0, 0, 1, 1),
        (1, 1, 1, 1, 1),
        (73, 13, 12, 3, 6),
        (20261006, 41, 37, 17, 5),
        (731, 29, 80, 61, 1),
        (1740, 19, 0, 11, 4),
    ],
)
def test_every_random_corpus_word_matches_independent_document_scan(seed, document_count, max_length, vocabulary_size, max_repeat):
    rng = random.Random(seed)
    vocabulary = tuple(f"wort{number}" for number in range(vocabulary_size))
    documents = []
    for number in range(document_count):
        target_length = rng.randint(0, max_length)
        tokens = []
        while len(tokens) < target_length:
            tokens.extend([rng.choice(vocabulary)] * rng.randint(1, max_repeat))
        documents.append(prepared(f"nested/doc{number}.txt", tokens[:target_length]))
    rng.shuffle(documents)
    original = tuple(documents)
    index = build_inverted_index(document for document in reversed(documents))
    words = {token for document in documents for token in document.tokens}
    assert set(index) == words
    queries = sorted(words) + ["abwesend", "nichtimkorpus99"]
    rng.shuffle(queries)
    before = dict(index.items())
    for token in queries:
        expected = scan_documents(documents, token)
        assert search_index_word(index, token) == expected
        assert search_direct_word(documents, token) == expected
        postings = get_postings(index, token)
        assert postings == tuple(expected)
        assert postings == tuple(sorted(set(postings)))
        for document in documents:
            assert (document.document_id in postings) == any(candidate == token for candidate in document.tokens)
    assert tuple(documents) == original
    assert dict(index.items()) == before


@pytest.mark.parametrize("seed", [31, 20261006, 9001])
def test_generated_raw_documents_have_independent_token_and_hit_expectations(seed):
    rng = random.Random(seed)
    vocabulary = ("alpha", "beta", "gamma", "delta", "wort42")
    raw_documents = []
    expected_tokens = {}
    for number in range(23):
        identifier = f"doc{number}.txt"
        # The expectation is generated first. Case and punctuation alter only
        # the raw representation; no tokenizer computes expected values.
        tokens = tuple(rng.choice(vocabulary) for _ in range(rng.randrange(0, 28)))
        expected_tokens[identifier] = tokens
        words = [token.upper() if rng.randrange(2) else token for token in tokens]
        raw_documents.append(RawDocument(identifier, identifier, ",\n".join(words)))
    rng.shuffle(raw_documents)
    documents = prepare_corpus(raw_documents)
    assert {document.document_id: document.tokens for document in documents} == expected_tokens
    index = build_inverted_index(reversed(documents))
    for token in (*vocabulary, "abwesend"):
        expected = sorted(identifier for identifier, tokens in expected_tokens.items() if token in tokens)
        assert search_index_word(index, token.upper() + "!") == expected
        assert get_postings(index, token) == tuple(expected)
        assert scan_documents(documents, token) == expected


def test_pinned_real_corpus_index_matches_every_word_and_fixed_known_queries():
    documents = prepare_corpus(load_corpus(ROOT / "daten" / "real" / "kafka_verwandlung"))
    assert len(documents) == 1
    assert documents[0].document_id == "01_anfang.txt"
    assert documents[0].tokens[:5] == ("als", "gregor", "samsa", "eines", "morgens")
    index = build_inverted_index(documents)
    assert search_index_word(index, "Gregor") == ["01_anfang.txt"]
    assert search_index_word(index, "Fenster") == ["01_anfang.txt"]
    assert search_index_word(index, "Unauffindbar") == []
    words = {token for document in documents for token in document.tokens}
    assert set(index) == words
    for token in sorted(words) + ["unauffindbar"]:
        expected = scan_documents(documents, token)
        assert search_index_word(index, token) == expected
        assert search_direct_word(documents, token) == expected
        assert get_postings(index, token) == tuple(expected)
