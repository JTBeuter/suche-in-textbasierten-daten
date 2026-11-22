"""Unabhängige Ablauf- und historische Integrationsnachweise des Reviews."""

import hashlib
import importlib.util
from pathlib import Path

import pytest

from boolesche_suche import search_direct_boolean, search_index_boolean
import boolesche_suche.search as boolean_search
from gemeinsam import PreparedDocument, RawDocument, prepare_corpus
from invertierter_index import build_inverted_index


ROOT = Path(__file__).resolve().parents[3]
CLI = Path("themen/01_textaufbereitung_direkte_suche/src/direkte_suche/__main__.py")
OLD_CLI = Path("doku/pruefberichte/artefakte_03/cli_vorstufe02.py")
OLD_CONFIG = Path("doku/pruefberichte/artefakte_03/pyproject_vorstufe02.toml")
OLD_CLI_SHA = "f735ab06b333e1c95e355c64c0694e83449e6475ce1598dd68a089a5da806826"
OLD_CONFIG_SHA = "fa42176a0f27242fb96fc4de0f75085c251b9d44f3e4a5a780fdb89f43cafa87"


@pytest.mark.parametrize(
    ("operator", "tokens", "terms"),
    [
        ("OR", ("alpha", "unreachable"), ("alpha", "missing")),
        ("AND", ("alpha", "alpha", "beta", "unreachable"), ("alpha", "ALPHA!", "beta")),
        ("AND", ("strasse", "beta", "unreachable"), ("Straße", "STRASSE", "beta")),
    ],
)
def test_direct_boolean_stops_reading_tokens_immediately_after_semantic_success(operator, tokens, terms):
    inspected = []

    class GuardedToken(str):
        def __hash__(self):
            inspected.append(str(self))
            assert self != "unreachable", "Token hinter vollständigem Treffer wurde trotzdem untersucht"
            return str.__hash__(self)

    document = PreparedDocument("a.txt", "a.txt", " ".join(tokens), tuple(GuardedToken(token) for token in tokens))
    assert search_direct_boolean((document,), terms, operator) == ["a.txt"]
    assert "unreachable" not in inspected
    if operator == "AND":
        assert "beta" in inspected  # Wiederholtes alpha darf den AND-Abbruch nicht auslösen.


def test_boolean_results_preserve_lexicographic_path_ids_for_unsorted_single_use_inputs():
    texts = {"D2.txt": "alpha beta", "D10.txt": "alpha", "z/a.txt": "beta alpha", "A.txt": "alpha beta"}
    corpus = prepare_corpus(RawDocument(identifier, identifier, text) for identifier, text in texts.items())
    index = build_inverted_index(reversed(corpus))
    before = dict(index.items())
    for operator, expected in (("AND", ["A.txt", "D2.txt", "z/a.txt"]), ("OR", ["A.txt", "D10.txt", "D2.txt", "z/a.txt"])):
        assert search_direct_boolean((document for document in reversed(corpus)), (word for word in ("beta", "ALPHA!")), operator) == expected
        for variant in (("input_order", "shortest_first") if operator == "AND" else ("input_order",)):
            assert search_index_boolean(index, (word for word in ("beta", "ALPHA!")), operator, variant) == expected
    assert dict(index.items()) == before


@pytest.mark.parametrize("ties", [("tieleft", "tieright"), ("tieright", "tieleft")])
def test_shortest_first_uses_original_order_for_equal_length_postings(monkeypatch, ties):
    raw = (
        RawDocument("d0.txt", "d0.txt", "long tieleft"),
        RawDocument("d1.txt", "d1.txt", "long tieleft tieright"),
        RawDocument("d2.txt", "d2.txt", "long tieleft tieright short"),
        RawDocument("d3.txt", "d3.txt", "long tieright"),
    )
    index = build_inverted_index(prepare_corpus(raw))
    calls = []
    original = boolean_search.intersect_sorted

    def observed_intersection(left, right):
        calls.append((tuple(left), tuple(right)))
        return original(left, right)

    monkeypatch.setattr(boolean_search, "intersect_sorted", observed_intersection)
    assert search_index_boolean(index, ("long", *ties, "short"), "AND", "shortest_first") == ["d2.txt"]
    assert calls == [(("d2.txt",), index[term]) for term in (*ties, "long")]


@pytest.fixture
def historical_verifier(tmp_path, monkeypatch):
    source = ROOT / "themen/01_textaufbereitung_direkte_suche/experimente/verify_results.py"
    spec = importlib.util.spec_from_file_location("review_historical_verifier", source)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    monkeypatch.setattr(verifier, "ROOT", tmp_path)
    for relative in (CLI, OLD_CLI, OLD_CONFIG, Path("pyproject.toml")):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    return verifier


def test_actual_boolean_hook_and_packaging_preserve_complete_stage02_contract(historical_verifier):
    verifier = historical_verifier
    assert hashlib.sha256((ROOT / OLD_CLI).read_bytes()).hexdigest() == OLD_CLI_SHA
    assert hashlib.sha256((ROOT / OLD_CONFIG).read_bytes()).hexdigest() == OLD_CONFIG_SHA
    verifier.verify_cli_boolean_extension(OLD_CLI_SHA)
    verifier.verify_packaging_extension(OLD_CONFIG_SHA, OLD_CONFIG.as_posix())


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ('if "--boolean" in argv:', 'if "--boolean" not in argv:'),
        ('argv = sys.argv[1:]', 'argv = sys.argv[2:]'),
        ('argument != "--boolean"', 'argument == "--boolean"'),
        ('from boolesche_suche.__main__ import main as boolean_main', 'from invertierter_index.__main__ import main as boolean_main'),
        ('matches = search_direct_word(prepare_corpus(raw_corpus), args.query)', 'matches = []'),
        ('matches = search_direct_substring(raw_corpus, args.query)', 'matches = []'),
        ('matches = search_index_word(index, args.query)', 'matches = []'),
        ('default="word"', 'default="substring"'),
    ],
)
def test_boolean_extension_rejects_changed_dispatch_or_existing_word_substring_index_behavior(historical_verifier, before, after):
    verifier = historical_verifier
    current = verifier.ROOT / CLI
    content = current.read_text(encoding="utf-8")
    assert before in content
    current.write_text(content.replace(before, after, 1), encoding="utf-8")
    with pytest.raises(AssertionError, match="bestehende CLI-Semantik"):
        verifier.verify_cli_boolean_extension(OLD_CLI_SHA)


@pytest.mark.parametrize("relative", [OLD_CLI, OLD_CONFIG])
def test_historical_stage02_archive_rejects_byte_tampering_even_with_identical_semantics(historical_verifier, relative):
    verifier = historical_verifier
    archive = verifier.ROOT / relative
    archive.write_bytes(archive.read_bytes() + b"\n# tampered archive\n")
    with pytest.raises(AssertionError, match="gemessene"):
        if relative == OLD_CLI:
            verifier.verify_cli_boolean_extension(OLD_CLI_SHA)
        else:
            verifier.verify_packaging_extension(OLD_CONFIG_SHA, OLD_CONFIG.as_posix())


def test_stage02_packaging_rejects_removing_index_package_despite_valid_stage01_baseline(historical_verifier):
    verifier = historical_verifier
    current = verifier.ROOT / "pyproject.toml"
    content = current.read_text(encoding="utf-8")
    current.write_text(content.replace('"invertierter_index", ', '', 1), encoding="utf-8")
    with pytest.raises(AssertionError):
        verifier.verify_packaging_extension(OLD_CONFIG_SHA, OLD_CONFIG.as_posix())
