"""Feste Erwartungswerte plus 300 reproduzierbare kleine Differentialkorpora."""

from dataclasses import FrozenInstanceError
from pathlib import Path
import random

import pytest

from gemeinsam import (
    CorpusError, PreparedDocument, QueryError, RawDocument,
    load_corpus, normalize_query, prepare_corpus,
)
from positionsindex import (
    PositionalIndex, build_positional_index, search_direct_phrase,
    search_index_phrase, validate_phrase_tokens,
)
import positionsindex.search as phrase_search
import positionsindex.index as phrase_index


ROOT = Path(__file__).resolve().parents[3]
HAND_TOKENS = {
    "D0.txt": ("fehler", "bei", "der", "verbindung", "zum", "server"),
    "D1.txt": ("serverfehler", "ohne", "verbindung"),
    "D2.txt": ("verbindung", "zum", "server", "fehler", "fehler"),
    "D3.txt": ("server", "ohne", "verbindung"),
    "D4.txt": (),
    "D5.txt": ("a", "a", "a"),
}
HAND_INDEX = {
    "fehler": {"D0.txt": (0,), "D2.txt": (3, 4)},
    "bei": {"D0.txt": (1,)}, "der": {"D0.txt": (2,)},
    "verbindung": {"D0.txt": (3,), "D1.txt": (2,), "D2.txt": (0,), "D3.txt": (2,)},
    "zum": {"D0.txt": (4,), "D2.txt": (1,)},
    "server": {"D0.txt": (5,), "D2.txt": (2,), "D3.txt": (0,)},
    "serverfehler": {"D1.txt": (0,)},
    "ohne": {"D1.txt": (1,), "D3.txt": (1,)},
    "a": {"D5.txt": (0, 1, 2)},
}


def prepared(identifier, tokens, raw_text=None):
    return PreparedDocument(identifier, identifier, " ".join(tokens) if raw_text is None else raw_text, tuple(tokens))


def snapshot(index):
    return {token: dict(postings) for token, postings in index.items()}


@pytest.fixture
def hand_corpus():
    documents = prepare_corpus(load_corpus(ROOT / "daten/beispiele/d0_d5"))
    # Erwartung wird weder von tokenizer noch einer der Suchfunktionen berechnet.
    assert {document.document_id: document.tokens for document in documents} == HAND_TOKENS
    return documents


def check_both(corpus, phrase, expected):
    assert search_direct_phrase(corpus, phrase) == expected
    assert search_index_phrase(build_positional_index(corpus), phrase) == expected


def test_hand_index_has_all_exact_positions(hand_corpus):
    index = build_positional_index(hand_corpus)
    assert isinstance(index, PositionalIndex)
    assert snapshot(index) == HAND_INDEX
    assert len(index) == 9
    assert repr(index) == "PositionalIndex(vocabulary_size=9)"


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("Verbindung zum Server", {"D0.txt": [3], "D2.txt": [0]}),
        ("a", {"D5.txt": [0, 1, 2]}),
        ("a a", {"D5.txt": [0, 1]}),
        ("a a a", {"D5.txt": [0]}),
        ("a a a a", {}),
        ("Server Fehler", {"D2.txt": [2]}),
        ("Fehler Fehler", {"D2.txt": [3]}),
        ("Server Serverfehler", {}),
        ("Fehler Serverfehler", {}),
        ("Verbindung Server", {}),
        ("Fehler", {"D0.txt": [0], "D2.txt": [3, 4]}),
        ("FEHLER, bei. der", {"D0.txt": [0]}),
        ("zum SERVER!", {"D0.txt": [4], "D2.txt": [1]}),
        ("unbekannt", {}),
        ("a unbekannt", {}),
    ],
)
def test_fixed_d0_d5_phrase_starts(hand_corpus, phrase, expected):
    check_both(hand_corpus, normalize_query(phrase, "phrase"), expected)


@pytest.mark.parametrize(
    ("tokens", "phrase", "expected"),
    [
        (("a", "b", "a", "b"), ("a", "b"), {"a.txt": [0, 2]}),
        (("a", "b", "a", "b"), ("b", "a"), {"a.txt": [1]}),
        (("a", "b", "c"), ("b", "a"), {}),
        (("a", "b", "c"), ("a", "missing"), {}),
        (("a", "b", "c"), ("a", "b", "c"), {"a.txt": [0]}),
        (("a", "b", "c"), ("c",), {"a.txt": [2]}),
        (("a", "b", "c"), ("c", "a"), {}),
        ((), ("a",), {}),
    ],
)
def test_order_overlap_document_ends_and_missing_tokens(tokens, phrase, expected):
    check_both((prepared("a.txt", tokens),), phrase, expected)


def test_sentence_punctuation_and_document_boundaries_are_fixed_semantics():
    corpus = prepare_corpus((
        RawDocument("A.txt", "A.txt", "a"),
        RawDocument("B.txt", "B.txt", "b"),
        RawDocument("C.txt", "C.txt", "a. b a—b a_b"),
    ))
    assert [document.tokens for document in corpus] == [("a",), ("b",), ("a", "b", "a", "b", "a", "b")]
    check_both(corpus, ("a", "b"), {"C.txt": [0, 2, 4]})
    check_both(corpus[:2], ("a", "b"), {})


@pytest.mark.parametrize(
    ("raw", "expected_tokens", "query", "expected"),
    [
        ("Straße STRASSE Straße", ("strasse", "strasse", "strasse"), "STRAẞE strasse", {"a.txt": [0, 1]}),
        ("Äpfel A\u0308pfel Äpfel", ("äpfel", "äpfel", "äpfel"), "A\u0308PFEL äpfel", {"a.txt": [0, 1]}),
        ("Österreich O\u0308sterreich", ("österreich", "österreich"), "österreich O\u0308STERREICH", {"a.txt": [0]}),
        ("der und zum läuft laufen", ("der", "und", "zum", "läuft", "laufen"), "UND zum", {"a.txt": [1]}),
        ("läuft laufen", ("läuft", "laufen"), "lauf", {}),
        ("E-Mail Fehler_Code foo—bar", ("e", "mail", "fehler", "code", "foo", "bar"), "MAIL FEHLER", {"a.txt": [1]}),
        ("abc42 007 ١٢३", ("abc42", "007", "١٢३"), "007 ١٢३", {"a.txt": [1]}),
        ("x²y Ⅲ vier", ("x", "y", "vier"), "x y", {"a.txt": [0]}),
        ("q\u0307r İx a\u034fb", ("q", "r", "i", "x", "a", "b"), "r i x", {"a.txt": [1]}),
        ("東京 中文 ЖУК Σ σ ς", ("東京", "中文", "жук", "σ", "σ", "σ"), "σ ς", {"a.txt": [3, 4]}),
        ("ﬃ ffi", ("ffi", "ffi"), "FFI ﬃ", {"a.txt": [0]}),
        ("Serverfehler Fehler", ("serverfehler", "fehler"), "Fehler", {"a.txt": [1]}),
    ],
)
def test_unicode_and_shared_token_rule_have_independent_expected_tokens(raw, expected_tokens, query, expected):
    corpus = prepare_corpus((RawDocument("a.txt", "a.txt", raw),))
    assert corpus[0].tokens == expected_tokens
    check_both(corpus, normalize_query(query, "phrase"), expected)


def test_empty_corpus_and_empty_documents_are_valid():
    for corpus in ((), (prepared("a.txt", ()), prepared("b.txt", ()))):
        index = build_positional_index(corpus)
        assert len(index) == 0
        assert snapshot(index) == {}
        assert search_direct_phrase(corpus, ("a",)) == {}
        assert search_index_phrase(index, ("a",)) == {}


def test_unsorted_one_shot_corpus_and_query_generators_preserve_lexicographic_ids():
    identifiers = ("doc2.txt", "nested/a.txt", "doc10.txt", "A.txt")
    corpus = [prepared(identifier, ("a", "b", "a", "b")) for identifier in identifiers]
    expected_ids = ["A.txt", "doc10.txt", "doc2.txt", "nested/a.txt"]
    expected = {identifier: [0, 2] for identifier in expected_ids}
    index = build_positional_index(document for document in corpus)
    assert list(index["a"]) == expected_ids
    direct = search_direct_phrase((document for document in reversed(corpus)), (token for token in ("a", "b")))
    indexed = search_index_phrase(index, (token for token in ("a", "b")))
    assert direct == indexed == expected
    assert list(direct) == list(indexed) == expected_ids
    assert [document.document_id for document in corpus] == list(identifiers)


def test_builder_uses_prepared_tokens_without_retokenizing_raw_text():
    corpus = (prepared("a.txt", ("a", "b"), raw_text="Fehler Fehler"),)
    index = build_positional_index(corpus)
    assert snapshot(index) == {"a": {"a.txt": (0,)}, "b": {"a.txt": (1,)}}
    assert search_direct_phrase(corpus, ("a", "b")) == {"a.txt": [0]}
    assert search_index_phrase(index, ("fehler",)) == {}


@pytest.mark.parametrize("invalid", [None, 42, True, "a", b"a", object()])
def test_builder_and_direct_reject_non_corpus_inputs(invalid):
    with pytest.raises(CorpusError):
        build_positional_index(invalid)
    with pytest.raises(CorpusError):
        search_direct_phrase(invalid, ("a",))


@pytest.mark.parametrize("invalid", [None, 42, "a", {}, RawDocument("a.txt", "a.txt", "a")])
def test_builder_and_direct_reject_non_prepared_elements(invalid):
    corpus = (prepared("valid.txt", ("a",)), invalid)
    with pytest.raises(CorpusError):
        build_positional_index(corpus)
    with pytest.raises(CorpusError):
        search_direct_phrase(corpus, ("a",))


@pytest.mark.parametrize("tokens", [(), ("a",), ("b",)])
def test_duplicate_ids_are_errors_including_empty_documents(tokens):
    corpus = (prepared("a.txt", ("a",)), prepared("a.txt", tokens))
    with pytest.raises(CorpusError, match="Doppelte"):
        build_positional_index(corpus)
    with pytest.raises(CorpusError, match="Doppelte"):
        search_direct_phrase(corpus, ("a",))


@pytest.mark.parametrize(
    "token",
    ["FEHLER", "Straße", "A\u0308pfel", "a b", "a-b", "a_b", "a!", " a ",
     "—", "²", "Ⅲ", "x²y", "q\u0307r", "İx", "\x00"],
)
def test_builder_rejects_non_normalized_or_invalid_prepared_tokens(token):
    with pytest.raises(CorpusError):
        build_positional_index((prepared("a.txt", ("valid", token)),))


@pytest.mark.parametrize("token", ["fehler", "strasse", "äpfel", "007", "١٢३", "東京", "жук", "σ"])
def test_builder_accepts_central_normalized_unicode_tokens(token):
    index = build_positional_index((prepared("a.txt", (token, token)),))
    assert index[token]["a.txt"] == (0, 1)
    assert search_index_phrase(index, (token, token)) == {"a.txt": [0]}


@pytest.mark.parametrize(
    "phrase",
    [None, 42, True, object(), "a", b"a", (), [], ("",), (" ",), ("...",),
     ("Fehler",), ("FEHLER",), ("a!",), ("a b",), ("a_b",), ("Straße",),
     ("A\u0308pfel",), ("x²y",), ("İx",), (None,), (42,), (b"a",), (["a"],),
     ("unknown", "Fehler")],
)
def test_invalid_core_queries_raise_query_error_even_with_empty_corpus_or_unknown_first_word(phrase):
    with pytest.raises(QueryError):
        validate_phrase_tokens(phrase)
    with pytest.raises(QueryError):
        search_direct_phrase((), phrase)
    with pytest.raises(QueryError):
        search_index_phrase(build_positional_index(()), phrase)


def test_query_validation_preserves_repetition_and_order_without_mutation():
    phrase = ["a", "b", "a", "a"]
    before = tuple(phrase)
    assert validate_phrase_tokens(phrase) == before
    assert tuple(phrase) == before
    assert validate_phrase_tokens(token for token in phrase) == before


def test_index_mutability_guards_cover_both_mapping_levels_and_position_tuples(hand_corpus):
    index = build_positional_index(hand_corpus)
    before = snapshot(index)
    with pytest.raises(TypeError, match="build_positional_index"):
        PositionalIndex()
    with pytest.raises(FrozenInstanceError):
        index._postings = {}
    with pytest.raises(TypeError):
        index["fehler"] = {}
    with pytest.raises(TypeError):
        del index["fehler"]
    with pytest.raises(TypeError):
        index._postings["injected"] = {}
    with pytest.raises(TypeError):
        index["fehler"]["D0.txt"] = (99,)
    with pytest.raises(TypeError):
        del index["fehler"]["D0.txt"]
    with pytest.raises(TypeError):
        index["fehler"]["D0.txt"][0] = 99
    copy = dict(index["fehler"])
    copy["D0.txt"] = (99,)
    assert snapshot(index) == before == HAND_INDEX
    with pytest.raises(KeyError):
        index["abwesend"]


def test_input_containers_and_every_result_list_remain_independent(hand_corpus):
    corpus = list(reversed(hand_corpus))
    corpus_before = tuple(corpus)
    phrase = ["fehler"]
    index = build_positional_index(corpus)
    for query, expected in ((phrase, {"D0.txt": [0], "D2.txt": [3, 4]}), (["unknown"], {})):
        for search in (lambda tokens: search_direct_phrase(corpus, tokens), lambda tokens: search_index_phrase(index, tokens)):
            first = search(query)
            second = search(query)
            assert first == second == expected
            assert first is not second
            for identifier in first:
                assert first[identifier] is not second[identifier]
                assert isinstance(first[identifier], list)
                first[identifier].clear()
                first[identifier].append(999)
            first["injected.txt"] = [1]
            assert search(query) == expected
    assert tuple(corpus) == corpus_before
    assert phrase == ["fehler"]
    assert snapshot(index) == HAND_INDEX
    corpus.clear()
    corpus.append(prepared("later.txt", ("later",)))
    assert snapshot(index) == HAND_INDEX


def test_shortest_middle_anchor_converts_offsets_and_removes_negative_starts(monkeypatch):
    # b has only 2 occurrences vs a's 5. At phrase offset 1 b position 0
    # would give -1; only position 3 can anchor a valid a b a at start 2.
    corpus = (prepared("a.txt", ("b", "a", "a", "b", "a", "a", "a")),)
    index = build_positional_index(corpus)
    calls = []
    original = phrase_search._intersect_shifted

    def observed(starts, positions, offset):
        calls.append((tuple(starts), tuple(positions), offset))
        return original(starts, positions, offset)

    monkeypatch.setattr(phrase_search, "_intersect_shifted", observed)
    assert search_index_phrase(index, ("a", "b", "a")) == {"a.txt": [2]}
    assert calls == [((2,), (1, 2, 4, 5, 6), 0), ((2,), (1, 2, 4, 5, 6), 2)]
    assert search_direct_phrase(corpus, ("a", "b", "a")) == {"a.txt": [2]}


def test_shortest_last_anchor_never_admits_starts_beyond_document_end():
    # c is shortest and lies at phrase offset 2; its position 0 is invalid.
    # The final a b cannot be completed past the document end.
    corpus = (prepared("a.txt", ("c", "a", "b", "c", "a", "b", "a", "b")),)
    check_both(corpus, ("a", "b", "c"), {"a.txt": [1]})
    check_both(corpus, ("c", "a", "b", "c", "a", "b", "c"), {})


def test_candidates_use_boolean_merge_in_shortest_document_list_order(monkeypatch):
    corpus = tuple(prepared(f"d{number}.txt", tokens) for number, tokens in enumerate((
        ("long",), ("long", "medium"), ("long", "medium", "short"), ("long", "medium"),
    )))
    index = build_positional_index(corpus)
    calls = []
    original = phrase_search.intersect_sorted

    def observed(left, right):
        calls.append((tuple(left), tuple(right)))
        return original(left, right)

    monkeypatch.setattr(phrase_search, "intersect_sorted", observed)
    assert search_index_phrase(index, ("long", "medium", "short")) == {"d2.txt": [0]}
    assert calls == [(("d2.txt",), ("d1.txt", "d2.txt", "d3.txt")), (("d2.txt",), ("d0.txt", "d1.txt", "d2.txt", "d3.txt"))]


def test_direct_reference_has_no_index_or_positions_intersection_dependency(monkeypatch):
    def forbidden(*arguments, **keywords):
        raise AssertionError("Direkte Referenz hat Index-/Listenoperation aufgerufen")

    monkeypatch.setattr(phrase_search, "intersect_sorted", forbidden)
    monkeypatch.setattr(phrase_search, "_intersect_shifted", forbidden)
    corpus = (prepared("a.txt", ("a", "a", "a")),)
    assert search_direct_phrase(corpus, ("a", "a")) == {"a.txt": [0, 1]}


def test_builder_checks_each_distinct_prepared_token_once_without_raw_retokenization(monkeypatch):
    original = phrase_index.tokenize
    checked = []

    def observed(token):
        checked.append(token)
        return original(token)

    monkeypatch.setattr(phrase_index, "tokenize", observed)
    corpus = (prepared("a.txt", ("a", "a", "b"), raw_text="OTHER RAW WORDS"), prepared("b.txt", ("b", "a", "c")))
    index = build_positional_index(corpus)
    assert checked == ["a", "b", "c"]
    assert index["a"]["a.txt"] == (0, 1)


def test_missing_words_and_disjoint_documents_abort_before_position_work(monkeypatch):
    def forbidden(*arguments):
        raise AssertionError("Positionsprüfung trotz fehlender Kandidaten")

    monkeypatch.setattr(phrase_search, "_intersect_shifted", forbidden)
    corpus = (prepared("a.txt", ("a",)), prepared("b.txt", ("b",)))
    index = build_positional_index(corpus)
    assert search_index_phrase(index, ("a", "unknown", "b")) == {}
    assert search_index_phrase(index, ("a", "b")) == {}


def test_empty_intermediate_position_result_stops_remaining_phrase_work(monkeypatch):
    original = phrase_search._intersect_shifted
    offsets = []

    def observed(starts, positions, offset):
        offsets.append(offset)
        return original(starts, positions, offset)

    monkeypatch.setattr(phrase_search, "_intersect_shifted", observed)
    index = build_positional_index((prepared("a.txt", ("a", "b", "d", "c")),))
    assert search_index_phrase(index, ("a", "b", "c", "d")) == {}
    assert offsets == [1, 2]


def assert_index_invariants(index, expected_tokens):
    expected_vocabulary = {token for tokens in expected_tokens.values() for token in tokens}
    assert set(index) == expected_vocabulary
    for token, postings in index.items():
        assert list(postings) == sorted(postings)
        assert all(postings.values())
        for identifier, positions in postings.items():
            assert isinstance(positions, tuple)
            assert positions == tuple(sorted(set(positions)))
            assert positions == tuple(number for number, value in enumerate(expected_tokens[identifier]) if value == token)
    for identifier, tokens in expected_tokens.items():
        reconstructed = {position: token for token, postings in index.items() for position in postings.get(identifier, ())}
        assert reconstructed == dict(enumerate(tokens))
        assert sum(len(postings.get(identifier, ())) for postings in index.values()) == len(tokens)


@pytest.mark.parametrize("seed", [31, 20261006, 9001])
def test_300_generated_raw_corpora_match_independent_tokens_oracle_and_direct_reference(seed):
    rng = random.Random(seed)
    vocabulary = ("a", "b", "c", "strasse", "äpfel", "東京", "σ", "007")
    for trial in range(100):
        expected_tokens = {}
        raw_documents = []
        for number in range(rng.randrange(8)):
            identifier = f"nested/doc{number}.txt"
            # Solltokens entstehen vor der Rohrepräsentation und sind unabhängig
            # von der Produktionstokenisierung; häufige a/b erzeugen Wiederholung.
            tokens = tuple(rng.choice((*vocabulary, "a", "a", "b")) for _ in range(rng.randrange(31)))
            expected_tokens[identifier] = tokens
            words = [token.upper() if rng.randrange(2) else token for token in tokens]
            raw_documents.append(RawDocument(identifier, identifier, ".\n".join(words)))
        rng.shuffle(raw_documents)
        corpus = prepare_corpus(raw_documents)
        assert {document.document_id: document.tokens for document in corpus} == expected_tokens, (seed, trial)
        index = build_positional_index(document for document in reversed(corpus))
        assert_index_invariants(index, expected_tokens)
        before = snapshot(index)
        phrases = [("a",), ("a", "a"), ("a", "a", "a"), ("missing",), ("a", "missing")]
        phrases.extend(tuple(rng.choice(vocabulary) for _ in range(rng.randint(1, 7))) for _ in range(15))
        for tokens in expected_tokens.values():
            if tokens:
                start = rng.randrange(len(tokens))
                phrases.append(tokens[start:start + rng.randint(1, 5)])
        for phrase in phrases:
            # Separat geschriebene Fensteroracle: kein Positionsindex und keine
            # Kernfunktion berechnet den Erwartungswert. Vollständige Startlisten.
            expected = {}
            for identifier in sorted(expected_tokens):
                tokens = expected_tokens[identifier]
                starts = [start for start in range(len(tokens) - len(phrase) + 1) if tokens[start:start + len(phrase)] == phrase]
                if starts:
                    expected[identifier] = starts
            direct = search_direct_phrase(corpus, phrase)
            indexed = search_index_phrase(index, phrase)
            assert direct == indexed == expected, (seed, trial, expected_tokens, phrase, direct, indexed, expected)
            assert list(indexed) == sorted(indexed)
            assert all(starts == sorted(set(starts)) for starts in indexed.values())
        assert snapshot(index) == before, (seed, trial)


def test_pinned_real_corpus_has_known_prefix_phrase_start_and_all_windows_agree():
    corpus = prepare_corpus(load_corpus(ROOT / "daten/real/kafka_verwandlung"))
    assert len(corpus) == 1
    assert corpus[0].tokens[:5] == ("als", "gregor", "samsa", "eines", "morgens")
    index = build_positional_index(corpus)
    assert search_direct_phrase(corpus, ("als", "gregor", "samsa")) == {"01_anfang.txt": [0]}
    assert search_index_phrase(index, ("als", "gregor", "samsa")) == {"01_anfang.txt": [0]}
    for length in (1, 2, 3, 5):
        for start in range(len(corpus[0].tokens) - length + 1):
            phrase = corpus[0].tokens[start:start + length]
            assert search_index_phrase(index, phrase) == search_direct_phrase(corpus, phrase)
