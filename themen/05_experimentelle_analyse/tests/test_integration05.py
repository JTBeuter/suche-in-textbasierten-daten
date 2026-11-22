"""Gemeinsame Unicode-, Treffer- und Kopierverträge aller vorhandenen Pakete."""

from copy import deepcopy
from pathlib import Path
import tomllib

import pytest

from boolesche_suche import search_direct_boolean, search_index_boolean
from direkte_suche import search_direct_word
from gemeinsam import RawDocument, normalize_query, prepare_corpus, tokenize
from invertierter_index import build_inverted_index, search_index_word
from positionsindex import build_positional_index, search_direct_phrase, search_index_phrase


ROOT = Path(__file__).resolve().parents[3]


def integrated_corpus():
    return prepare_corpus([
        RawDocument("z.txt", "z.txt", "Serverfehler. Straße! a a a"),
        RawDocument("a.txt", "a.txt", "FEHLER; Verbindung. zum Server Äpfel"),
        RawDocument("nested/b.txt", "nested/b.txt", "Server ohne Verbindung A\u0308pfel STRASSE"),
        RawDocument("empty.txt", "empty.txt", ""),
    ])


def test_shared_token_contract_keeps_letters_decimal_digits_and_phrase_boundaries():
    # Expected values are literal, rather than another normalizer's output.
    assert tokenize("Straße STRASSE A\u0308pfel x²y foo_bar ١٢٣ Ⅳ") == (
        "strasse", "strasse", "äpfel", "x", "y", "foo", "bar", "١٢٣",
    )
    corpus = integrated_corpus()
    assert {document.document_id: document.tokens for document in corpus} == {
        "a.txt": ("fehler", "verbindung", "zum", "server", "äpfel"),
        "empty.txt": (),
        "nested/b.txt": ("server", "ohne", "verbindung", "äpfel", "strasse"),
        "z.txt": ("serverfehler", "strasse", "a", "a", "a"),
    }


@pytest.mark.parametrize("query,expected", [
    ("Fehler", ["a.txt"]),
    ("STRASSE", ["nested/b.txt", "z.txt"]),
    ("A\u0308pfel", ["a.txt", "nested/b.txt"]),
    ("nievorhanden", []),
])
def test_word_apis_agree_with_independent_known_results(query, expected):
    corpus = integrated_corpus()
    assert search_direct_word(corpus, query) == expected
    assert search_index_word(build_inverted_index(corpus), query) == expected


@pytest.mark.parametrize("operator,terms,expected", [
    ("AND", ["Verbindung", "Server"], ["a.txt", "nested/b.txt"]),
    ("OR", ["Fehler", "Straße"], ["a.txt", "nested/b.txt", "z.txt"]),
    ("AND", ["Straße", "STRASSE!"], ["nested/b.txt", "z.txt"]),
    ("AND", ["Server", "nievorhanden"], []),
])
def test_boolean_apis_keep_results_across_supported_variants(operator, terms, expected):
    corpus = integrated_corpus()
    index = build_inverted_index(corpus)
    assert search_direct_boolean(corpus, terms, operator) == expected
    for variant in (("input_order", "shortest_first") if operator == "AND" else ("input_order",)):
        assert search_index_boolean(index, terms, operator, variant) == expected


@pytest.mark.parametrize("query,expected", [
    ("Verbindung zum Server", {"a.txt": [1]}),
    ("a a", {"z.txt": [2, 3]}),
    ("a a a", {"z.txt": [2]}),
    ("Server Verbindung", {}),
    ("Straße", {"nested/b.txt": [4], "z.txt": [1]}),
])
def test_phrase_apis_preserve_every_start_and_sentence_separator_behavior(query, expected):
    corpus = integrated_corpus()
    tokens = normalize_query(query, "phrase")
    assert search_direct_phrase(corpus, tokens) == expected
    assert search_index_phrase(build_positional_index(corpus), tokens) == expected


def test_materialized_search_results_do_not_mutate_shared_corpus_or_indices():
    corpus = integrated_corpus()
    before = deepcopy(corpus)
    inverted = build_inverted_index(corpus)
    positional = build_positional_index(corpus)
    words = search_index_word(inverted, "Straße")
    words.clear()
    boolean = search_index_boolean(inverted, ["Fehler", "Straße"], "OR")
    boolean.clear()
    phrase = search_index_phrase(positional, ("a", "a"))
    phrase["z.txt"].clear()
    phrase.clear()
    assert corpus == before
    assert search_index_word(inverted, "Straße") == ["nested/b.txt", "z.txt"]
    assert search_index_boolean(inverted, ["Fehler", "Straße"], "OR") == ["a.txt", "nested/b.txt", "z.txt"]
    assert search_index_phrase(positional, ("a", "a")) == {"z.txt": [2, 3]}


def test_packaging_only_adds_theme05_package_mapping_and_testpath():
    current = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    original = tomllib.loads((ROOT / "ergebnisse/messungen/04_positionsindex_phrasensuche/code_source/pyproject.toml")
                             .read_text(encoding="utf-8"))
    # Preserve the measured project configuration rather than a relaxed subset.
    packages = current["tool"]["setuptools"]["packages"]
    assert packages.count("experimentelle_analyse") == 1
    packages.remove("experimentelle_analyse")
    mapping = current["tool"]["setuptools"]["package-dir"]
    assert mapping.pop("experimentelle_analyse") == "themen/05_experimentelle_analyse/src/experimentelle_analyse"
    testpaths = current["tool"]["pytest"]["ini_options"]["testpaths"]
    assert testpaths.count("themen/05_experimentelle_analyse/tests") == 1
    testpaths.remove("themen/05_experimentelle_analyse/tests")
    assert current == original
