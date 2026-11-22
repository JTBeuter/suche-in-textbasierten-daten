"""Galloping Search und AND NOT gegen unabhängige Mengenoracles und die direkte Referenz."""

from collections.abc import Sequence
import itertools
import json
import math
from pathlib import Path
import random

import pytest

from gemeinsam import PreparedDocument, QueryError, RawDocument, load_corpus, prepare_corpus
from invertierter_index import build_inverted_index
from boolesche_suche import (
    VARIANTS, difference_sorted, intersect_galloping, intersect_sorted, normalize_boolean_query,
    search_direct_boolean, search_index_boolean,
)
import boolesche_suche.search as boolean_search


ROOT = Path(__file__).resolve().parents[3]
UNIVERSE = tuple(f"d{i:05d}.txt" for i in range(2000))


def oracle_and(left, right):
    return sorted(set(left) & set(right))


def check_pair(left, right, context=""):
    """Alle Schnittverfahren in beiden Richtungen gegen die Mengenoracle."""
    expected = oracle_and(left, right)
    saved = (list(left), list(right))
    assert intersect_galloping(left, right) == expected, context
    assert intersect_galloping(right, left) == expected, context
    assert intersect_sorted(left, right) == expected, context
    assert difference_sorted(left, right) == sorted(set(left) - set(right)), context
    assert difference_sorted(right, left) == sorted(set(right) - set(left)), context
    assert (list(left), list(right)) == saved, context


# --- Listenverfahren ---------------------------------------------------------

EDGE_CASES = [
    ([], []), ([], ["D0.txt"]), (["D0.txt"], []), (["D0.txt"], ["D0.txt"]),
    (["D0.txt", "D2.txt"], ["D0.txt", "D2.txt"]),
    (["D0.txt", "D2.txt"], ["D1.txt", "D3.txt"]),
    (["D0.txt", "D2.txt", "D4.txt"], ["D1.txt", "D2.txt", "D5.txt"]),
    (["D0.txt"], [f"D{i:03d}.txt" for i in range(100)]),
    (["D099.txt"], [f"D{i:03d}.txt" for i in range(100)]),
    (["D100.txt"], [f"D{i:03d}.txt" for i in range(100)]),
    (["A.txt"], [f"D{i:03d}.txt" for i in range(100)]),
    (["D10.txt", "D2.txt"], ["D1.txt", "D10.txt", "D2.txt", "D3.txt"]),
    (["z/a.txt"], ["A.txt", "a/b.txt", "z/a.txt"]),
]


@pytest.mark.parametrize("left,right", EDGE_CASES)
def test_edge_cases_and_input_preservation_lists_and_tuples(left, right):
    check_pair(left, right)
    check_pair(tuple(left), tuple(right))
    assert type(intersect_galloping(tuple(left), tuple(right))) is list
    assert type(difference_sorted(tuple(left), tuple(right))) is list


def placements(long_ids, count):
    """Kurze Listen aus der langen Liste: Anfang, Ende, gleichmäßig verteilt, Mitte."""
    size = len(long_ids)
    count = min(count, size)
    if count == 0:
        return {"leer": ()}
    step = size / count
    return {
        "anfang": long_ids[:count],
        "ende": long_ids[size - count:],
        "verteilt": tuple(long_ids[int(i * step)] for i in range(count)),
        "mitte": long_ids[(size - count) // 2:(size - count) // 2 + count],
    }


@pytest.mark.parametrize("long_size", [1, 2, 3, 10, 100, 1000, 2000])
@pytest.mark.parametrize("short_size", [0, 1, 2, 3, 10, 50])
def test_systematic_length_ratios_and_positions(long_size, short_size):
    long_ids = UNIVERSE[:long_size]
    for name, short in placements(long_ids, short_size).items():
        # Teilmenge der langen Liste.
        check_pair(short, long_ids, f"teilmenge/{name}/{short_size}/{long_size}")
        # Gemischt: jede zweite kurze Kennung fehlt in der langen Liste.
        missing = set(short[::2])
        reduced = tuple(identifier for identifier in long_ids if identifier not in missing)
        check_pair(short, reduced, f"teilweise/{name}/{short_size}/{long_size}")
    # Disjunkt: kurze Liste ganz vor, ganz hinter und zwischen den langen Kennungen.
    even = UNIVERSE[:2 * long_size:2]
    odd = UNIVERSE[1:2 * short_size + 1:2]
    check_pair(odd, even, f"verschraenkt/{short_size}/{long_size}")
    check_pair(tuple(f"a{i:05d}.txt" for i in range(short_size)), long_ids, "davor")
    check_pair(tuple(f"z{i:05d}.txt" for i in range(short_size)), long_ids, "dahinter")


def test_identical_and_nested_lists():
    for size in (0, 1, 2, 7, 64, 65, 1000):
        ids = UNIVERSE[:size]
        check_pair(ids, ids, f"identisch/{size}")
        check_pair(ids[: size // 2], ids, f"praefix/{size}")
        check_pair(ids[size // 2:], ids, f"suffix/{size}")


@pytest.mark.parametrize("seed", [0, 17, 193, 20261006])
def test_random_skewed_lists_against_set_oracle(seed):
    rng = random.Random(seed)
    for case in range(300):
        short = sorted(rng.sample(UNIVERSE, rng.randrange(0, 40)))
        long = sorted(rng.sample(UNIVERSE, rng.choice([0, 1, 5, 40, 400, 1999, 2000])))
        check_pair(short, long, f"seed={seed}, case={case}")
        # Kurze Liste als echte Teilmenge mit zufälligen Positionen.
        subset = sorted(rng.sample(long, min(len(long), rng.randrange(0, 40))))
        check_pair(subset, long, f"seed={seed}, case={case}, teilmenge")


class Recorded(Sequence):
    """Protokolliert Zugriffe, um Rollen und Aufwand zu prüfen."""

    def __init__(self, values):
        self.values = tuple(values)
        self.indexed = 0
        self.iterated = 0

    def __len__(self):
        return len(self.values)

    def __getitem__(self, position):
        self.indexed += 1
        return self.values[position]

    def __iter__(self):
        self.iterated += 1
        return iter(self.values)


@pytest.mark.parametrize("swap", [False, True])
def test_keys_come_from_shorter_list_and_longer_list_is_only_probed(swap):
    long_ids = UNIVERSE[:2000]
    short = Recorded(long_ids[::200])
    long = Recorded(long_ids)
    arguments = (long, short) if swap else (short, long)
    assert intersect_galloping(*arguments) == list(long_ids[::200])
    assert short.iterated == 1 and short.indexed == 0
    assert long.iterated == 0
    # a=10, b=2000: je Kennung höchstens etwa 2·log2(b/a)+4 Zugriffe, nicht b.
    a, b = len(short), len(long)
    assert long.indexed <= a * (2 * math.log2(b / a) + 4)
    assert long.indexed < b / 10


def test_equal_lengths_take_keys_from_left():
    left, right = Recorded(UNIVERSE[:50:2]), Recorded(UNIVERSE[1:51:2])
    assert intersect_galloping(left, right) == []
    assert left.iterated == 1 and right.iterated == 0


def test_galloping_probe_count_matches_documented_jumps():
    # Kennung an Stelle 8 hinter Position 0: Proben an 0, 1, 2, 4, 8, danach Binärsuche
    # im letzten Sprungintervall [5, 8) mit zwei Schritten und ein Gleichheitszugriff.
    long = Recorded(UNIVERSE[:100])
    assert intersect_galloping([UNIVERSE[8]], long) == [UNIVERSE[8]]
    assert long.indexed == 5 + 2 + 1


# --- AND mit galloping ---------------------------------------------------------

@pytest.fixture
def fixture_corpus():
    corpus = prepare_corpus(load_corpus(ROOT / "daten/beispiele/d0_d5"))
    known = json.loads((ROOT / "daten/beispiele/d0_d5_expected.json").read_text(encoding="utf-8"))
    assert {doc.document_id: list(doc.tokens) for doc in corpus} == known["tokens"]
    return corpus, known


def test_variants_constant_and_order():
    assert VARIANTS == ("input_order", "shortest_first", "galloping")


@pytest.mark.parametrize("terms", [
    ["Verbindung", "Server"], ["Fehler", "Verbindung", "Server"], ["Verbindung", "unbekannt"],
    ["Fehler", "FEHLER!", "Fehler", "Server"], ["Serverfehler", "Server"], ["a"], ["Verbindung"],
    ["Server", "Verbindung", "zum", "Fehler"],
])
def test_galloping_and_matches_word_oracle_and_direct_reference(fixture_corpus, terms):
    corpus, known = fixture_corpus
    index = build_inverted_index(corpus)
    word = {key.casefold(): set(value) for key, value in known["word_matches"].items()}
    direct = search_direct_boolean(corpus, terms, "AND")
    if all(term.casefold().strip("!") in word for term in terms):
        assert direct == sorted(set.intersection(*(word[term.casefold().strip("!")] for term in terms)))
    for variant in VARIANTS:
        assert search_index_boolean(index, terms, "AND", variant) == direct


def test_galloping_sorts_by_length_and_uses_galloping_intersection(monkeypatch):
    raw = (
        RawDocument("d0.txt", "d0.txt", "long tieleft"),
        RawDocument("d1.txt", "d1.txt", "long tieleft tieright"),
        RawDocument("d2.txt", "d2.txt", "long tieleft tieright short"),
        RawDocument("d3.txt", "d3.txt", "long tieright"),
    )
    index = build_inverted_index(prepare_corpus(raw))
    calls = []
    original = boolean_search.intersect_galloping

    def observed(left, right):
        calls.append((tuple(left), tuple(right)))
        return original(left, right)

    def forbidden(left, right):
        raise AssertionError("galloping darf intersect_sorted nicht verwenden")

    monkeypatch.setattr(boolean_search, "intersect_galloping", observed)
    monkeypatch.setattr(boolean_search, "intersect_sorted", forbidden)
    assert search_index_boolean(index, ("long", "tieleft", "tieright", "short"), "AND", "galloping") == ["d2.txt"]
    # short (1) zuerst, dann Gleichstand tieleft/tieright in Eingabereihenfolge, zuletzt long.
    assert calls == [(("d2.txt",), index[term]) for term in ("tieleft", "tieright", "long")]


def test_galloping_stops_after_empty_intermediate_result(monkeypatch):
    index = build_inverted_index(prepare_corpus([
        RawDocument("a.txt", "a.txt", "x y"), RawDocument("b.txt", "b.txt", "z y"),
        RawDocument("c.txt", "c.txt", "y"),
    ]))
    calls = []
    original = boolean_search.intersect_galloping
    monkeypatch.setattr(boolean_search, "intersect_galloping",
                        lambda left, right: calls.append(1) or original(left, right))
    assert search_index_boolean(index, ["y", "x", "z"], "AND", "galloping") == []
    assert len(calls) == 1  # Sortiert x, z, y: x∩z ist leer, y wird nicht mehr geschnitten.
    calls.clear()
    assert search_index_boolean(index, ["x", "unbekannt", "y"], "AND", "galloping") == []
    assert calls == []


def test_or_and_direct_reject_galloping_with_explanation():
    with pytest.raises(QueryError, match="OR"):
        search_index_boolean(build_inverted_index(()), ["wort"], "OR", "galloping")
    with pytest.raises(QueryError, match="variant"):
        search_index_boolean(build_inverted_index(()), ["wort"], "AND", "Galloping")


# --- AND NOT -------------------------------------------------------------------

def assert_all_exclude(corpus, terms, exclude, expected):
    index = build_inverted_index(corpus)
    assert search_direct_boolean(corpus, terms, "AND", exclude) == expected
    assert search_direct_boolean(corpus, terms, "AND", exclude=exclude) == expected
    for variant in VARIANTS:
        assert search_index_boolean(index, terms, "AND", variant, exclude) == expected
        assert search_index_boolean(index, terms, "AND", variant=variant, exclude=exclude) == expected


@pytest.mark.parametrize("terms,exclude,expected", [
    (["verbindung"], "server", ["D1.txt"]),
    (["Verbindung"], "SERVER!", ["D1.txt"]),
    (["Verbindung"], "Fehler", ["D1.txt", "D3.txt"]),
    (["Verbindung", "zum"], "fehler", []),
    (["Verbindung", "Server"], "Fehler", ["D3.txt"]),
    (["Verbindung"], "Serverfehler", ["D0.txt", "D2.txt", "D3.txt"]),
    (["Verbindung"], "unbekannt", ["D0.txt", "D1.txt", "D2.txt", "D3.txt"]),
    (["unbekannt"], "Verbindung", []),
    (["a"], "Fehler", ["D5.txt"]),
    (["Fehler"], "fehler", []),
    (["Fehler", "Server"], "FEHLER", []),
    (["Server", "Verbindung"], "ohne", ["D0.txt", "D2.txt"]),
])
def test_and_not_known_semantics(fixture_corpus, terms, exclude, expected):
    corpus, known = fixture_corpus
    word = {key.casefold(): set(value) for key, value in known["word_matches"].items()}
    plain = [term.casefold().strip("!") for term in terms]
    excluded = exclude.casefold().strip("!")
    if all(term in word for term in plain) and excluded in word:
        oracle = set.intersection(*(word[term] for term in plain)) - word[excluded]
        assert sorted(oracle) == expected
    assert_all_exclude(corpus, terms, exclude, expected)


def test_and_not_normalizes_exclude_like_terms():
    query = normalize_boolean_query(["Server"], "AND", "Straße!")
    assert query.exclude == "strasse"
    assert normalize_boolean_query(["Server"], "AND").exclude is None
    corpus = prepare_corpus([RawDocument("u.txt", "u.txt", "Server STRASSE"),
                             RawDocument("v.txt", "v.txt", "Server Äpfel"),
                             RawDocument("w.txt", "w.txt", "server")])
    assert_all_exclude(corpus, ["SERVER"], "Straße", ["v.txt", "w.txt"])
    assert_all_exclude(corpus, ["SERVER"], "Äpfel", ["u.txt", "w.txt"])


@pytest.mark.parametrize("exclude", ["", "...", "Fehler Server", "E-Mail", b"fehler", 3, ["fehler"]])
def test_invalid_exclude_is_explained(exclude):
    with pytest.raises(QueryError):
        normalize_boolean_query(["Server"], "AND", exclude)
    with pytest.raises(QueryError):
        search_direct_boolean((), ["Server"], "AND", exclude)
    for variant in VARIANTS:
        with pytest.raises(QueryError):
            search_index_boolean(build_inverted_index(()), ["Server"], "AND", variant, exclude)


def test_exclude_only_with_and():
    with pytest.raises(QueryError, match="AND"):
        normalize_boolean_query(["Server"], "OR", "Fehler")
    with pytest.raises(QueryError, match="AND"):
        search_direct_boolean((), ["Server"], "OR", "Fehler")
    with pytest.raises(QueryError, match="AND"):
        search_index_boolean(build_inverted_index(()), ["Server"], "OR", "input_order", "Fehler")
    # NOT ohne Pflichtwort ist nicht vorgesehen.
    with pytest.raises(QueryError):
        search_index_boolean(build_inverted_index(()), [], "AND", "input_order", "Fehler")


def test_empty_corpus_and_empty_document_with_exclude():
    assert_all_exclude((), ["Server"], "Fehler", [])
    corpus = prepare_corpus([RawDocument("empty.txt", "empty.txt", "")])
    assert_all_exclude(corpus, ["Server"], "Fehler", [])


class GuardedToken(str):
    """Meldet jede Untersuchung eines Tokens über Hash oder Gleichheit."""

    inspected: list[str] = []

    def __hash__(self):
        GuardedToken.inspected.append(str(self))
        return str.__hash__(self)

    def __eq__(self, other):
        GuardedToken.inspected.append(str(self))
        return str.__eq__(self, other)

    __ne__ = str.__ne__


def guarded_document(tokens):
    return PreparedDocument("a.txt", "a.txt", " ".join(tokens), tuple(GuardedToken(token) for token in tokens))


def test_direct_exclude_reads_past_complete_match_and_stops_at_excluded_word():
    GuardedToken.inspected = []
    # Alle Pflichtwörter stehen vorn, das NOT-Wort erst am Ende: kein Treffer.
    late = guarded_document(("alpha", "beta", "fill", "fill", "gamma"))
    assert search_direct_boolean((late,), ["alpha", "beta"], "AND", "gamma") == []
    assert "gamma" in GuardedToken.inspected
    # Nach dem NOT-Wort wird nichts mehr untersucht.
    GuardedToken.inspected = []
    early = guarded_document(("alpha", "gamma", "unreachable"))
    assert search_direct_boolean((early,), ["alpha"], "AND", "gamma") == []
    assert "unreachable" not in GuardedToken.inspected
    # Ohne NOT-Wort im Dokument: Treffer erst nach vollständigem Lesen.
    GuardedToken.inspected = []
    hit = guarded_document(("alpha", "beta", "fill", "last"))
    assert search_direct_boolean((hit,), ["alpha", "beta"], "AND", "gamma") == ["a.txt"]
    assert "last" in GuardedToken.inspected


def test_index_exclude_skips_difference_for_empty_intersection(monkeypatch):
    corpus = prepare_corpus([RawDocument("a.txt", "a.txt", "x"), RawDocument("b.txt", "b.txt", "y z")])
    index = build_inverted_index(corpus)
    calls = []
    original = boolean_search.difference_sorted
    monkeypatch.setattr(boolean_search, "difference_sorted",
                        lambda left, right: calls.append((tuple(left), tuple(right))) or original(left, right))
    for variant in VARIANTS:
        assert search_index_boolean(index, ["x", "y"], "AND", variant, "z") == []
        assert search_index_boolean(index, ["y"], "AND", variant, "z") == []
        assert search_index_boolean(index, ["y"], "AND", variant, "x") == ["b.txt"]
    assert calls == [(("b.txt",), ("b.txt",)), (("b.txt",), ("a.txt",))] * 3


def test_new_variants_and_exclude_do_not_change_index_or_share_results(fixture_corpus):
    corpus, _ = fixture_corpus
    index = build_inverted_index(corpus)
    before = dict(index)
    identities = {word: id(posting) for word, posting in index.items()}
    requests = [(["Verbindung", "Server"], None), (["Verbindung"], "Server"), (["Fehler"], None),
                (["Verbindung", "Fehler"], "unbekannt"), (["Fehler"], "Fehler")]
    for terms, exclude in requests * 2:
        expected = search_direct_boolean(corpus, terms, "AND", exclude)
        for variant in VARIANTS:
            result = search_index_boolean(index, terms, "AND", variant, exclude)
            assert type(result) is list
            result.clear()
            result.append("manipuliert.txt")
            assert search_index_boolean(index, terms, "AND", variant, exclude) == expected
        assert dict(index) == before
        assert {word: id(posting) for word, posting in index.items()} == identities
        assert all(type(posting) is tuple for posting in index.values())


@pytest.mark.parametrize("seed", [1, 23, 91, 193, 1201, 20261006])
def test_generated_corpora_galloping_and_exclude_against_independent_oracle(seed):
    rng = random.Random(seed)
    vocabulary = ("alpha", "beta", "server", "verbindung", "fehler", "strasse", "äpfel", "2026")
    raw_forms = {"alpha": "ALPHA", "beta": "beta", "server": "SERVER", "verbindung": "Verbindung",
                 "fehler": "Fehler!", "strasse": "Straße", "äpfel": "Äpfel", "2026": "2026"}
    planned = {f"doc{i:02d}.txt": tuple(rng.choice(vocabulary) for _ in range(rng.randrange(25)))
               for i in range(30)}
    raw = [RawDocument(identifier, identifier, " - ".join(raw_forms[token] for token in tokens))
           for identifier, tokens in planned.items()]
    rng.shuffle(raw)
    corpus = prepare_corpus(raw)
    assert {doc.document_id: doc.tokens for doc in corpus} == planned
    index = build_inverted_index(reversed(corpus))
    before = dict(index)
    for case in range(40):
        canonical = rng.sample([*vocabulary, "unauffindbar"], rng.choice([1, 2, 3, 5]))
        terms = [raw_forms.get(token, token) for token in canonical]
        excluded = rng.choice([*vocabulary, "unauffindbar", canonical[0]])
        wanted = set(canonical)
        expected_and = sorted(identifier for identifier, tokens in planned.items() if wanted <= set(tokens))
        expected_not = [identifier for identifier in expected_and if excluded not in planned[identifier]]
        context = f"seed={seed}, case={case}, terms={terms}, exclude={excluded}"
        exclude_raw = raw_forms.get(excluded, excluded)
        assert search_direct_boolean(corpus, terms, "AND", exclude_raw) == expected_not, context
        orders = list(itertools.permutations(terms)) if len(terms) <= 3 else [terms, terms[::-1]]
        for order in orders:
            assert search_index_boolean(index, order, "AND", "galloping") == expected_and, context
            for variant in VARIANTS:
                assert search_index_boolean(index, order, "AND", variant, exclude_raw) == expected_not, context
    assert dict(index) == before


def test_real_corpus_exclude_samples():
    corpus = prepare_corpus(load_corpus(ROOT / "daten/real/kafka_verwandlung"))
    for terms, exclude, expected in [
        (["Gregor"], "Unauffindbar", ["01_anfang.txt"]),
        (["Gregor"], "Fenster", []),
        (["Gregor", "Fenster"], "Samsa", []),
    ]:
        assert_all_exclude(corpus, terms, exclude, expected)
    index = build_inverted_index(corpus)
    assert search_index_boolean(index, ["Gregor", "Fenster"], "AND", "galloping") == ["01_anfang.txt"]
