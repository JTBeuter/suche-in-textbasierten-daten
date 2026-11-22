"""Pflanzplan, getrennte Diagnosen, Blockgrenzen und Rohwert-Audit."""

import copy
import csv
import importlib.util
import json
from pathlib import Path
import shutil
import sys

import pytest

from gemeinsam import load_corpus, prepare_corpus
from gemeinsam.messung import MeasurementPlan


EXPERIMENTS = Path(__file__).resolve().parents[1]
ROOT = EXPERIMENTS.parents[2]


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(EXPERIMENTS))
    result = {}
    for name in ("boolean_generator", "boolean_diagnostics", "run", "verify_results", "analyse"):
        label = f"experiment03_{name}"
        spec = importlib.util.spec_from_file_location(label, EXPERIMENTS / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, label, module)
        spec.loader.exec_module(module)
        result[name] = module
    return result


def test_fixed_corpus_membership_token_oracle_and_order(modules, tmp_path):
    generator = modules["boolean_generator"]
    left = generator.generate_corpus(tmp_path / "left", document_count=1000, seed=17)
    right = generator.generate_corpus(tmp_path / "right", document_count=1000, seed=17)
    assert left.file_sha256 == right.file_sha256 and left.expected_tokens == right.expected_tokens
    prepared = prepare_corpus(load_corpus(left.root))
    assert {doc.document_id: doc.tokens for doc in prepared} == left.expected_tokens
    assert all(len(tokens) == 100 for tokens in left.expected_tokens.values())
    postings = modules["run"].independent_postings(left.expected_tokens)
    assert all(postings.get(word, ()) == ids for word, ids in left.membership.items())
    assert [len(left.membership[word]) for word in generator.GROUPS["mixed"]] == [950, 750, 500, 100, 10]
    assert [len(left.membership[word]) for word in generator.GROUPS["rare"]] == [20] * 5
    assert [len(left.membership[word]) for word in generator.GROUPS["frequent"]] == [900] * 5
    assert [len(left.membership[word]) for word in generator.GROUPS["low_overlap"]] == [500] * 5
    assert len(generator.expected_hits(left.membership, generator.GROUPS["low_overlap"][:2], "AND")) == 10
    assert len(generator.expected_hits(left.membership, generator.GROUPS["high_overlap"], "AND")) == 600
    for group, words in generator.GROUPS.items():
        for count in (2, 3, 5):
            for operator in ("AND", "OR"):
                assert generator.expected_hits(left.membership, words[:count], operator) == generator.expected_hits(left.membership, words[:count][::-1], operator)


@pytest.mark.parametrize("kwargs,error", [({"document_count": 101}, ValueError), ({"document_count": True}, TypeError),
                                         ({"tokens_per_document": 10}, ValueError), ({"seed": False}, TypeError)])
def test_generator_rejects_invalid_parameters(modules, tmp_path, kwargs, error):
    with pytest.raises(error):
        modules["boolean_generator"].generate_corpus(tmp_path, **kwargs)


def test_unknown_sort_tie_and_intermediate_diagnostics(modules):
    diagnose = modules["boolean_diagnostics"].diagnose_postings
    postings = {"a": ("a.txt", "b.txt", "c.txt"), "b": ("b.txt", "c.txt"), "c": ("c.txt",)}
    assert diagnose(postings, ("a", "b", "c"), "AND", "input_order")["intermediate_lengths"] == [3, 2, 1]
    optimized = diagnose(postings, ("a", "b", "c"), "AND", "shortest_first")
    assert optimized["ordered_terms"] == ["c", "b", "a"] and optimized["result_ids"] == ["c.txt"]
    missing = diagnose(postings, ("a", "missing", "c"), "AND", "shortest_first")
    assert missing["intermediate_lengths"] == [0] and missing["id_comparisons"] == 0
    assert diagnose({"a": ("a.txt",), "b": ("b.txt",)}, ("b", "a"), "AND", "shortest_first")["ordered_terms"] == ["b", "a"]
    for operator in ("AND", "OR"):
        got, comparisons, _ = modules["boolean_diagnostics"].merge_diagnostic(("a.txt", "c.txt"), ("b.txt", "c.txt", "d.txt"), operator)
        oracle = sorted({"a.txt", "c.txt"} & {"b.txt", "c.txt", "d.txt"}) if operator == "AND" else ["a.txt", "b.txt", "c.txt", "d.txt"]
        assert got == oracle
        assert comparisons == 5  # == und <, == und <, schließlich ==.


def test_preflight_detects_changed_tokens_before_search(modules, tmp_path):
    generated = modules["boolean_generator"].generate_corpus(tmp_path / "data", document_count=100)
    first = next(iter(generated.expected_tokens))
    (generated.root / first).write_text("manipuliert\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="Tokenfolgen"):
        modules["run"].validate_dataset("test", generated.root, generated.expected_tokens, generated.membership)


def test_real_snapshot_regex_expectations_and_boolean_queries(modules):
    run = modules["run"]
    directory, tokens, source = run.real_fixture()
    _, _, _, queries, data = run.validate_dataset("real", directory, tokens, None, source)
    assert len(tokens) == 1 and sum(map(len, tokens.values())) == 1271
    assert len(queries) == 18
    assert all(query.expected_ids == () for query in queries if query.operator == "AND" and query.group == "real_unknown")
    assert all(query["original_term_count"] == 3 and query["effective_term_count"] == 2 for query in data["queries"] if query["group"] == "duplicates")


def test_measurement_all_blocks_eligible_random_and_checked(modules, monkeypatch):
    run = modules["run"]
    clock = iter(range(0, 1_000_000, 1000))
    monkeypatch.setattr(run, "perf_counter_ns", lambda: next(clock))
    query = run.BooleanQuerySpec
    queries = [query("a", ("a",), "AND", "test", "forward", ("a.txt",)), query("b", ("b",), "OR", "test", "forward", ())]
    calls = []
    def operation(name):
        def search(terms, operator):
            calls.append((name, terms, operator))
            return ["a.txt"] if operator == "AND" else []
        return search
    operations = {name: operation(name) for name in run.ALGORITHMS}
    plan = MeasurementPlan(warmups=1, repeats=3, query_block_size=4, seed=7)
    rows = run.measure_comparison(operations, queries, plan, {})
    assert len(rows) == 15 and len(calls) == 4 * 5 * 4
    assert all(row["elapsed_ns"] == 1000 and row["query_ms"] == .00025 for row in rows)
    assert all(sorted(row["order_index"] for row in rows if row["repeat"] == i) == list(range(5)) for i in range(3))
    repeated = run.measure_comparison(operations, queries, plan, {})
    assert [(r["repeat"], r["algorithm"], r["query_id"], r["order_index"]) for r in rows] == [(r["repeat"], r["algorithm"], r["query_id"], r["order_index"]) for r in repeated]
    state = 0
    def wrong_once(terms, operator):
        nonlocal state
        state += 1
        return ["wrong.txt"] if state == 2 else ["a.txt"]
    with pytest.raises(AssertionError):
        run.measure_comparison({"direct_boolean": wrong_once}, queries[:1], plan, {})


def test_previous_result_destruction_precedes_next_timer(modules, monkeypatch):
    run = modules["run"]
    events = []
    class Observed(list):
        def __del__(self):
            events.append("destroy")
    def clock():
        events.append("clock")
        return len(events) * 1000
    monkeypatch.setattr(run, "perf_counter_ns", clock)
    query = run.BooleanQuerySpec("a", ("a",), "AND", "test", "forward", ("a.txt",))
    run.measure_comparison({"direct_boolean": lambda terms, operator: Observed(["a.txt"])}, [query],
                           MeasurementPlan(warmups=0, repeats=2, query_block_size=1), {})
    assert events == ["clock", "clock", "destroy", "clock", "clock", "destroy"]


def test_final_requires_successful_pilot_and_matching_source(modules, tmp_path, monkeypatch):
    run = modules["run"]
    path = tmp_path / "decision.json"
    with pytest.raises(SystemExit, match="Zuerst"):
        run.require_pilot(path)
    path.write_text(json.dumps({"pilot_correct": False, "locked_parameters": run.PARAMETERS}))
    with pytest.raises(SystemExit, match="Erfolgreicher"):
        run.require_pilot(path)
    path.write_text(json.dumps({"pilot_correct": True, "locked_parameters": run.PARAMETERS, "method_code_sha256": {"x": "y"}}))
    with pytest.raises(SystemExit, match="Messcode"):
        run.require_pilot(path)
    monkeypatch.setattr(run, "code_hashes", lambda: {"x": "y"})
    run.require_pilot(path)


def test_existing_final_artifacts_and_raw_summary_corruption_rejected(modules, tmp_path):
    directory = ROOT / "ergebnisse/messungen/03_boolesche_mehrwortsuche"
    if not (directory / "metadata.json").exists():
        pytest.skip("Finalmessung noch nicht ausgeführt")
    verifier = modules["verify_results"]
    # Seit der Erweiterung um Galloping Search und AND NOT (14.10.2026) weicht der aktive
    # Code bewusst von der Messfassung ab. Geprüft werden deshalb Archiv, Rohwerte und Daten
    # mit dem aktuellen Such-/Generatorverhalten (--archive-only); nichts wird umetikettiert.
    assert verifier.verify_directory(directory, check_active_code=False) == (5320, 266, 1001)
    with pytest.raises(AssertionError, match="aktiver Code geändert"):
        verifier.verify_directory(directory)
    with (directory / "raw.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    rows[0]["elapsed_ns"] = str(int(rows[0]["elapsed_ns"]) + 1)
    with pytest.raises(AssertionError):
        verifier.verify_data(rows, summary, metadata)
    metadata["datasets"][0]["queries"][0]["diagnostics"]["input_order"]["id_comparisons"] += 1
    with pytest.raises(AssertionError):
        verifier.verify_corpora(metadata)
    archived = tmp_path / "corrupt_archive"
    shutil.copytree(directory, archived)
    source = archived / "code_source/themen/03_boolesche_mehrwortsuche/experimente/run.py"
    source.write_text(source.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="Quelltextarchiv"):
        verifier.verify_directory(archived, check_active_code=False)
