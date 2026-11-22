"""Pflanzplan, Messgrenzen, Randomisierung und exklusiver Speichervertrag."""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from gemeinsam import RawDocument, load_corpus, prepare_corpus
from gemeinsam.messung import MeasurementPlan, QuerySpec
from invertierter_index import build_inverted_index


EXPERIMENTS = Path(__file__).resolve().parents[1]
ROOT = EXPERIMENTS.parents[2]


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(EXPERIMENTS))
    result = {}
    for name in ("generator", "memory", "run", "verify_results"):
        label = f"experiment02_{name}"
        spec = importlib.util.spec_from_file_location(label, EXPERIMENTS / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, label, module)
        spec.loader.exec_module(module)
        result[name] = module
    return result


@pytest.mark.parametrize("documents,length,vocabulary", [(1, 20, 7), (2, 20, 7), (7, 200, 30), (10, 1000, 1000)])
def test_generator_independent_expected_tokens_reached_v_and_hashes(modules, tmp_path, documents, length, vocabulary):
    module = modules["generator"]
    left = module.generate_corpus(tmp_path / "left", documents * length, document_count=documents,
                                  base_vocabulary=vocabulary, seed=17)
    right = module.generate_corpus(tmp_path / "right", documents * length, document_count=documents,
                                   base_vocabulary=vocabulary, seed=17)
    assert left.file_sha256 == right.file_sha256
    assert left.expected_tokens == right.expected_tokens
    observed = prepare_corpus(load_corpus(left.root))
    assert {document.document_id: document.tokens for document in observed} == left.expected_tokens
    all_words = set().union(*(set(sequence) for sequence in left.expected_tokens.values()))
    assert all_words == {f"wort{i:05d}" for i in range(vocabulary)} | {"fehler", "verbindung"}
    assert sum(sequence.count("fehler") for sequence in left.expected_tokens.values()) == documents * ((length - 1) // 100 + 1)
    assert sum(sequence.count("verbindung") for sequence in left.expected_tokens.values()) == 1
    assert left.expected_tokens[next(iter(left.expected_tokens))][-1] == "verbindung"
    assert "unauffindbar" not in all_words
    reference = {word: tuple(sorted(identifier for identifier, sequence in left.expected_tokens.items() if word in sequence))
                 for word in all_words}
    assert dict(build_inverted_index(observed)) == reference
    assert modules["run"].linear_expected_postings(left.expected_tokens) == reference


@pytest.mark.parametrize("parameters,error", [
    ({"total_tokens": True, "document_count": 2, "base_vocabulary": 2}, TypeError),
    ({"total_tokens": 40, "document_count": False, "base_vocabulary": 2}, TypeError),
    ({"total_tokens": 40, "document_count": 2, "base_vocabulary": True}, TypeError),
    ({"total_tokens": 40, "document_count": 2, "base_vocabulary": 2, "seed": True}, TypeError),
    ({"total_tokens": 1, "document_count": 1, "base_vocabulary": 2}, ValueError),
    ({"total_tokens": 40, "document_count": 0, "base_vocabulary": 2}, ValueError),
    ({"total_tokens": 41, "document_count": 2, "base_vocabulary": 2}, ValueError),
    ({"total_tokens": 202, "document_count": 2, "base_vocabulary": 2}, ValueError),
    ({"total_tokens": 40, "document_count": 2, "base_vocabulary": 0}, ValueError),
    ({"total_tokens": 40, "document_count": 2, "base_vocabulary": 38}, ValueError),
])
def test_generator_rejects_unreachable_and_invalid_parameters(modules, tmp_path, parameters, error):
    with pytest.raises(error):
        modules["generator"].generate_corpus(tmp_path, **parameters)


def test_generator_rejects_nonempty_directory(modules, tmp_path):
    (tmp_path / "existing.txt").write_text("x")
    with pytest.raises(ValueError, match="leer"):
        modules["generator"].generate_corpus(tmp_path, 40, document_count=2, base_vocabulary=2)


def test_two_algorithms_random_order_and_all_block_results_checked(modules, monkeypatch):
    module = modules["run"]
    clock = iter(range(0, 100_000, 1000))
    monkeypatch.setattr(module, "perf_counter_ns", lambda: next(clock))
    calls = []
    def operation(name):
        def search(text):
            calls.append((name, text))
            return ["a.txt"] if text == "A" else []
        return search
    operations = {"direct_word": operation("direct_word"), "inverted_index": operation("inverted_index")}
    queries = [QuerySpec("a", "A", "word", ("a.txt",)), QuerySpec("b", "B", "word", ())]
    plan = MeasurementPlan(warmups=1, repeats=3, query_block_size=4, seed=7)
    rows = module.measure_comparison(operations, queries, plan, {"dataset_id": "test", "token_count": 1})
    assert len(calls) == (1 + 3) * 2 * 2 * 4
    assert len(rows) == 3 * 2 * 2
    assert all(row["elapsed_ns"] == 1000 and row["query_ms"] == .00025 for row in rows)
    assert all(sorted(row["order_index"] for row in rows if row["repeat"] == repeat) == [0, 1, 2, 3]
               for repeat in range(3))
    order = [(row["repeat"], row["algorithm"], row["query_id"], row["order_index"]) for row in rows]
    repeated = module.measure_comparison(operations, queries, plan, {"dataset_id": "test", "token_count": 1})
    assert order == [(row["repeat"], row["algorithm"], row["query_id"], row["order_index"]) for row in repeated]
    faulty_calls = 0
    def faulty(text):
        nonlocal faulty_calls
        faulty_calls += 1
        return ["wrong.txt"] if faulty_calls == 2 else ["a.txt"]
    with pytest.raises(AssertionError):
        module.measure_comparison({"direct_word": faulty}, queries[:1], plan, {})


def test_exclusive_memory_counts_proxy_backing_dict_and_shared_strings_once(modules):
    prepared = prepare_corpus((RawDocument("a.txt", "a.txt", "eins eins zwei"),
                               RawDocument("b.txt", "b.txt", "eins")))
    index = build_inverted_index(prepared)
    # Alle im Index gespeicherten Keys/IDs stammen aus dem bereits existierenden Korpus.
    shared_strings = {id(doc.document_id) for doc in prepared} | {id(token) for doc in prepared for token in doc.tokens}
    assert all(id(word) in shared_strings and all(id(identifier) in shared_strings for identifier in ids)
               for word, ids in index.items())
    expected = sys.getsizeof(index) + sys.getsizeof(index._postings) + sys.getsizeof(dict(index))
    expected += sum(sys.getsizeof(ids) for ids in index.values())
    assert modules["memory"].exclusive_index_bytes(index, prepared) == expected
    assert modules["memory"].exclusive_index_bytes(index, ()) > expected
    expected_index = {"eins": ("a.txt", "b.txt"), "zwei": ("a.txt",)}
    values = modules["memory"].profile_index(prepared, expected_index)
    assert len(values) == 3
    assert all(row["peak_traced_bytes"] >= row["retained_traced_bytes"] > 0 and row["exclusive_index_bytes"] == expected
               for row in values)


def test_previous_result_destruction_occurs_outside_next_timer(modules, monkeypatch):
    module = modules["run"]
    events = []
    class ObservedResult(list):
        def __del__(self):
            events.append("destroy")
    counter = 0
    def clock():
        nonlocal counter
        events.append("clock")
        counter += 1000
        return counter
    monkeypatch.setattr(module, "perf_counter_ns", clock)
    plan = MeasurementPlan(warmups=0, repeats=2, query_block_size=1)
    rows = module.measure_comparison({"direct_word": lambda query: ObservedResult(["a.txt"])},
                                      [QuerySpec("a", "A", "word", ("a.txt",))], plan, {})
    assert len(rows) == 2
    assert events == ["clock", "clock", "destroy", "clock", "clock", "destroy"]


def test_final_requires_matching_successful_pilot_and_source(modules, tmp_path, monkeypatch):
    module = modules["run"]
    path = tmp_path / "decision.json"
    with pytest.raises(SystemExit, match="Zuerst"):
        module.require_pilot(path)
    path.write_text(json.dumps({"pilot_correct": False, "locked_parameters": module.PARAMETERS}))
    with pytest.raises(SystemExit, match="Erfolgreicher"):
        module.require_pilot(path)
    path.write_text(json.dumps({"pilot_correct": True, "locked_parameters": module.PARAMETERS, "method_code_sha256": {"x": "y"}}))
    with pytest.raises(SystemExit, match="Messcode"):
        module.require_pilot(path)
    monkeypatch.setattr(module, "code_hashes", lambda: {"x": "y"})
    module.require_pilot(path)


def test_saved_final_artifacts_verified_and_corruption_rejected(modules):
    directory = ROOT / "ergebnisse/messungen/02_invertierter_index"
    if not (directory / "metadata.json").is_file():
        pytest.skip("Finalmessung noch nicht ausgeführt")
    verifier = modules["verify_results"]
    assert verifier.verify_directory(directory, check_active_code=False)[0] == 840
    with (directory / "raw.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    memory = json.loads((directory / "memory.json").read_text(encoding="utf-8"))
    with (directory / "memory.csv").open(encoding="utf-8", newline="") as handle:
        memory_rows = list(csv.DictReader(handle))
    rows[0]["elapsed_ns"] = str(int(rows[0]["elapsed_ns"]) + 1)
    with pytest.raises(AssertionError):
        verifier.verify_data(rows, summary, metadata, memory, memory_rows)
