"""Determinismus, Kontrollgrößen, unabhängige Oracles und Audit-Manipulationen."""

from collections import Counter
import copy
import csv
import importlib
import json
from pathlib import Path
import weakref

import pytest

from gemeinsam import load_corpus, prepare_corpus
from gemeinsam.messung import MeasurementPlan, summarize_measurements, write_measurements


PREFIX = "themen.04_positionsindex_phrasensuche.experimente"


@pytest.fixture
def modules():
    return {name: importlib.import_module(f"{PREFIX}.{name}") for name in ("generator", "run", "memory", "verify_results")}


def test_generator_determinism_full_token_oracle_and_unigram_controls(modules, tmp_path):
    generator = modules["generator"]
    corpora = [generator.generate_corpus(tmp_path / f"h{hits}", document_count=10,
                tokens_per_document=100, result_document_count=hits, seed=17) for hits in (0, 2, 10)]
    again = generator.generate_corpus(tmp_path / "again", document_count=10,
                tokens_per_document=100, result_document_count=10, seed=17)
    assert again.expected_tokens == corpora[-1].expected_tokens
    assert again.file_sha256 == corpora[-1].file_sha256
    baseline = {identifier: Counter(tokens) for identifier, tokens in corpora[0].expected_tokens.items()}
    for generated, hits in zip(corpora, (0, 2, 10)):
        assert {doc.document_id: doc.tokens for doc in prepare_corpus(load_corpus(generated.root))} == generated.expected_tokens
        assert {identifier: Counter(tokens) for identifier, tokens in generated.expected_tokens.items()} == baseline
        assert set(map(len, generated.expected_tokens.values())) == {100}
        assert len({token for tokens in generated.expected_tokens.values() for token in tokens}) == 66
        result = generator.synthetic_queries(generated, full=True)
        assert result[0].expected == {f"d{i:05d}.txt": [40] for i in range(hits)}
        queries = {query.query_id: query.expected for query in result}
        assert queries["frequent_k5"]["d00000.txt"] == [0, 50]
        assert queries["rare_k3"] == {"d00000.txt": [30], "d00001.txt": [30]}
        assert queries["repeated_k1"]["d00000.txt"] == [20, 21, 22, 23, 24, 25]
        assert queries["repeated_k5"]["d00000.txt"] == [20, 21]
        assert queries["wrong_order_k2"] == queries["unknown_k1"] == {}


@pytest.mark.parametrize("kwargs,error", [({"document_count": True}, TypeError), ({"seed": False}, TypeError),
    ({"document_count": 1}, ValueError), ({"tokens_per_document": 99}, ValueError),
    ({"result_document_count": -1}, ValueError), ({"result_document_count": 201}, ValueError)])
def test_generator_invalid_parameters(modules, tmp_path, kwargs, error):
    with pytest.raises(error):
        modules["generator"].generate_corpus(tmp_path, **kwargs)


def test_preflight_detects_changed_documents_before_search(modules, tmp_path):
    run, generator = modules["run"], modules["generator"]
    generated = generator.generate_corpus(tmp_path / "source", document_count=2, tokens_per_document=100, result_document_count=1)
    queries = generator.synthetic_queries(generated, full=True)
    (generated.root / "d00000.txt").write_text("manipuliert\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="Tokenfolgen"):
        run.describe_dataset("test", generated.root, generated.expected_tokens, queries, {"kind": "generated"})


def test_real_source_manifest_and_independent_phrase_expectations(modules):
    run = modules["run"]
    directory, tokens, fixture = run.real_fixture()
    queries = run.real_queries(tokens)
    by_id = {query.query_id: query.expected for query in queries}
    assert sum(map(len, tokens.values())) == 1271 and len(tokens) == 1
    assert by_id["real_prefix_k5"] == {"01_anfang.txt": [0]}
    assert by_id["real_repeated_k2"] == {"01_anfang.txt": [1060, 1078]}
    assert by_id["real_repeated_k3"] == by_id["real_wrong_order_k3"] == {}
    prepared, postings, positions, description = run.describe_dataset("real", directory, tokens, queries,
        {"kind": "real", "source_fixture": fixture})
    assert by_id["real_prefix_k1"] == {"01_anfang.txt": [0, 269, 309, 868, 921, 1231, 1255]}
    assert len(prepared) == 1
    assert next(query for query in description["queries"] if query["query_id"] == "real_prefix_k5")["position_count"] == 1
    assert description["unigram_statistics"]["gregor"] == {"cf": 15, "df": 1}


def test_blocks_shuffle_algorithms_check_every_result_and_destroy_outside_timer(modules, monkeypatch):
    run, generator = modules["run"], modules["generator"]
    query = generator.PhraseQuery("known", ("a",), "test", {"d.txt": [0, 2]})
    missing = generator.PhraseQuery("unknown", ("missing",), "test", {})
    clock = iter(range(0, 1_000_000, 1000))
    monkeypatch.setattr(run, "perf_counter_ns", lambda: next(clock))
    calls = []
    def operation(text):
        calls.append(text)
        return {"d.txt": [0, 2]} if text == "A" else {}
    plan = MeasurementPlan(warmups=1, repeats=3, query_block_size=2, seed=7)
    rows = run.measure_comparison({name: operation for name in run.ALGORITHMS}, [query, missing], plan, {})
    assert len(rows) == 12 and len(calls) == 32
    assert all(row["query_ms"] == .0005 and row["elapsed_ns"] == 1000 for row in rows)
    again = run.measure_comparison({name: operation for name in run.ALGORITHMS}, [query, missing], plan, {})
    assert [(r["repeat"], r["algorithm"], r["query_id"], r["order_index"]) for r in rows] == [
        (r["repeat"], r["algorithm"], r["query_id"], r["order_index"]) for r in again]
    events = []
    class Observed(dict):
        def __del__(self):
            events.append("destroy")
    def observed_clock():
        events.append("clock")
        return len(events) * 1000
    monkeypatch.setattr(run, "perf_counter_ns", observed_clock)
    run.measure_comparison({"direct_phrase": lambda text: Observed({"d.txt": [0, 2]})}, [query],
                          MeasurementPlan(warmups=0, repeats=2, query_block_size=1), {})
    assert events == ["clock", "clock", "destroy", "clock", "clock", "destroy"]
    state = 0
    def wrong_once(text):
        nonlocal state
        state += 1
        return {"d.txt": [0]} if state == 2 else query.expected
    with pytest.raises(AssertionError, match="full positions"):
        run.measure_comparison({"direct_phrase": wrong_once}, [query], plan, {})


def test_memory_only_selected_algorithm_and_previous_build_released(modules, monkeypatch):
    memory = modules["memory"]
    refs, calls = [], []
    class Observed(dict):
        pass
    def builder(prepared):
        assert memory.tracemalloc.is_tracing()
        assert all(ref() is None for ref in refs), "previous index still retained"
        index = Observed({"a": ("d.txt",)})
        refs.append(weakref.ref(index))
        calls.append("inverted")
        return index
    def forbidden(prepared):
        raise AssertionError("other production index built in same profile")
    monkeypatch.setattr(memory, "build_inverted_index", builder)
    monkeypatch.setattr(memory, "build_positional_index", forbidden)
    rows = memory.profile_index((), {"a": ("d.txt",)}, algorithm="inverted_index", repeats=3)
    assert len(rows) == 3 and calls == ["inverted"] * 3
    assert all(ref() is None for ref in refs)
    assert not memory.tracemalloc.is_tracing()
    assert all(row["peak_traced_bytes"] >= row["retained_traced_bytes"] > 0 for row in rows)
    assert all(row["transient_peak_bytes"] == row["peak_traced_bytes"] - row["retained_traced_bytes"] for row in rows)


def test_memory_actual_algorithms_full_oracle_and_tracer_cleanup(modules, tmp_path, monkeypatch):
    run, memory, generator = modules["run"], modules["memory"], modules["generator"]
    generated = generator.generate_corpus(tmp_path, document_count=2, tokens_per_document=100, result_document_count=2)
    prepared, postings, positions, _ = run.describe_dataset("small", generated.root, generated.expected_tokens,
        generator.synthetic_queries(generated), {"kind": "generated"})
    for algorithm, expected in (("inverted_index", postings), ("positional_index", positions)):
        rows = memory.profile_index(prepared, expected, algorithm=algorithm, repeats=2)
        assert len(rows) == 2 and not memory.tracemalloc.is_tracing()
    def failing(prepared):
        raise RuntimeError("failed build")
    monkeypatch.setattr(memory, "build_positional_index", failing)
    with pytest.raises(RuntimeError):
        memory.profile_index(prepared, positions, algorithm="positional_index")
    assert not memory.tracemalloc.is_tracing()


def fabricated_audit_fixture(modules, monkeypatch, tmp_path):
    """Test-only timings; never written to production measurement folders."""
    run = modules["run"]
    parameters = copy.deepcopy(run.PARAMETERS)
    parameters["synthetic"] = {"document_count": 3, "tokens_per_document": 100}
    parameters["result_document_counts"] = [0, 1, 3]
    parameters["full_query_result_count"] = 3
    monkeypatch.setattr(run, "PARAMETERS", parameters)
    monkeypatch.setattr(modules["verify_results"], "PARAMETERS", parameters)
    plan = MeasurementPlan(warmups=0, repeats=2, query_block_size=2)
    info = {"run_id": "test_fixture_only", "git_commit": "test_fixture_only", "parameters": parameters,
            "measurement_plan": vars(plan), "datasets": []}
    clock = iter(range(0, 10_000_000, 1000))
    monkeypatch.setattr(run, "perf_counter_ns", lambda: next(clock))
    rows = []
    for identifier, directory, tokens, queries, extra in run.datasets(tmp_path / "sources"):
        _, _, _, description = run.describe_dataset(identifier, directory, tokens, queries, extra)
        info["datasets"].append(description)
        context = {"run_id": info["run_id"], "git_commit": info["git_commit"], "seed": plan.seed,
            **{field: description[field] for field in ("dataset_id", "document_count", "text_bytes", "token_count")}}
        for algorithm in ("inverted_index", "positional_index"):
            for repeat in range(plan.repeats):
                rows.append({**context, "algorithm": algorithm, "phase": "build", "repeat": repeat,
                    "block_size": 1, "elapsed_ns": 1000 + repeat, "build_ms": (1000 + repeat) / 1_000_000, "correct": True})
        expected = {query.text: query.expected for query in queries}
        rows.extend(run.measure_comparison({algorithm: lambda text: expected[text] for algorithm in run.ALGORITHMS}, queries, plan, context))
    path = tmp_path / "test_only.csv"
    write_measurements(path, rows)
    with path.open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    return csv_rows, summarize_measurements(rows), info


def test_audit_detects_timing_hit_count_summary_and_full_position_tampering(modules, monkeypatch, tmp_path):
    verifier = modules["verify_results"]
    rows, summary, info = fabricated_audit_fixture(modules, monkeypatch, tmp_path)
    verifier.verify_data(rows, summary, info)
    assert verifier.verify_corpora(info) == 10
    bad = copy.deepcopy(rows)
    bad[0]["elapsed_ns"] = str(int(bad[0]["elapsed_ns"]) + 1)
    with pytest.raises(AssertionError):
        verifier.verify_data(bad, summary, info)
    bad = copy.deepcopy(rows)
    next(row for row in bad if row["phase"] == "query")["hit_count"] = "987"
    with pytest.raises(AssertionError):
        verifier.verify_data(bad, summary, info)
    bad = copy.deepcopy(summary)
    bad[0]["iqr_ms"] += .01
    with pytest.raises(AssertionError):
        verifier.verify_data(rows, bad, info)
    bad = copy.deepcopy(info)
    bad["datasets"][2]["queries"][0]["expected_positions"]["d00000.txt"] = [41]
    with pytest.raises(AssertionError, match="metadata"):
        verifier.verify_corpora(bad)
    bad = copy.deepcopy(info)
    bad["datasets"][1]["unigram_statistics"]["z000"]["cf"] += 1
    with pytest.raises(AssertionError, match="unigram_statistics"):
        verifier.verify_data(rows, summary, bad)


def test_final_pilot_parameter_source_and_missing_memory_gates(modules, tmp_path, monkeypatch):
    run = modules["run"]
    path = tmp_path / "pilot_decision.json"
    with pytest.raises(SystemExit, match="Zuerst"):
        run.require_pilot(path)
    path.write_text(json.dumps({"pilot_correct": False, "locked_parameters": run.PARAMETERS}), encoding="utf-8")
    with pytest.raises(SystemExit, match="Erfolgreicher"):
        run.require_pilot(path)
    path.write_text(json.dumps({"pilot_correct": True, "locked_parameters": run.PARAMETERS, "method_code_sha256": {"a": "b"}}), encoding="utf-8")
    with pytest.raises(SystemExit, match="Messcode"):
        run.require_pilot(path)
    monkeypatch.setattr(run, "code_hashes", lambda: {"a": "b"})
    with pytest.raises(SystemExit, match="Speicherlauf"):
        run.require_pilot(path)


def test_memory_audit_rejects_overlap_alias_process_and_allocation_corruption(modules):
    """Artificial records stay in this test; they are no measurement evidence."""
    run, verifier = modules["run"], modules["verify_results"]
    datasets = [{"dataset_id": f"test{i}", "document_count": 2, "token_count": 200,
                 "vocabulary_size": 66, "posting_count": 100} for i in range(4)]
    info = {"run_id": "test_fixture_only", "datasets": datasets, "code_sha256": {"test.py": "fixture"},
            "memory": {"repeats": 3}, "timing_completed_at_utc": "2026-10-06T10:00:00+00:00"}
    rows, workers, summary = [], [], []
    for number, (dataset, algorithm) in enumerate((dataset, algorithm) for dataset in datasets
            for algorithm in ("inverted_index", "positional_index")):
        for repeat in range(3):
            rows.append({"run_id": info["run_id"], "dataset_id": dataset["dataset_id"], "algorithm": algorithm,
                **{field: dataset[field] for field in ("document_count", "token_count", "vocabulary_size", "posting_count")},
                "repeat": repeat, "worker_pid": 1000 + number, "retained_traced_bytes": 100 + repeat,
                "peak_traced_bytes": 150 + repeat, "transient_peak_bytes": 50})
        workers.append({"dataset_id": dataset["dataset_id"], "algorithm": algorithm, "worker_pid": 1000 + number,
            "code_sha256": info["code_sha256"], "started_at_utc": f"2026-10-06T10:00:{number * 2 + 1:02d}+00:00",
            "completed_at_utc": f"2026-10-06T10:00:{number * 2 + 2:02d}+00:00"})
        summary.append({"dataset_id": dataset["dataset_id"], "algorithm": algorithm,
            "median_retained_traced_bytes": 101, "median_peak_traced_bytes": 151, "median_transient_peak_bytes": 50})
    memory = {"schema": list(run.MEMORY_FIELDS), "measurement": info["memory"], "code_sha256": info["code_sha256"],
              "workers": workers, "rows": rows, "summary": summary}
    csv_rows = [{key: str(row[key]) for key in run.MEMORY_FIELDS} for row in rows]
    verifier.verify_memory(memory, csv_rows, info)
    changed = copy.deepcopy(memory)
    changed["workers"][1]["started_at_utc"] = changed["workers"][0]["started_at_utc"]
    with pytest.raises(AssertionError, match="overlaps"):
        verifier.verify_memory(changed, csv_rows, info)
    changed = copy.deepcopy(memory)
    changed["rows"][0]["transient_peak_bytes"] += 1
    changed_csv = copy.deepcopy(csv_rows)
    changed_csv[0]["transient_peak_bytes"] = "51"
    with pytest.raises(AssertionError):
        verifier.verify_memory(changed, changed_csv, info)
    changed = copy.deepcopy(memory)
    changed["workers"][1]["worker_pid"] = changed["workers"][0]["worker_pid"]
    changed_csv = copy.deepcopy(csv_rows)
    for number in (3, 4, 5):
        changed["rows"][number]["worker_pid"] = changed["workers"][0]["worker_pid"]
        changed_csv[number]["worker_pid"] = str(changed["workers"][0]["worker_pid"])
    with pytest.raises(AssertionError, match="separate processes"):
        verifier.verify_memory(changed, changed_csv, info)


def test_metadata_without_setuptools_records_missing_version(modules, tmp_path, monkeypatch):
    # Ab Python 3.12 ist setuptools nicht vorinstalliert; die Metadaten dürfen nicht abbrechen.
    run = modules["run"]
    from importlib.metadata import PackageNotFoundError
    installed = run.version

    def without_setuptools(distribution):
        if distribution == "setuptools":
            raise PackageNotFoundError(distribution)
        return installed(distribution)

    monkeypatch.setattr(run, "version", without_setuptools)
    assert run.installed_version("setuptools") is None
    assert run.installed_version("pytest") == installed("pytest")
    metadata = run.make_metadata(MeasurementPlan(warmups=1, repeats=3, query_block_size=5), tmp_path, True)
    assert metadata["environment"]["setuptools"] is None
    assert metadata["environment"]["pytest"] == installed("pytest")
