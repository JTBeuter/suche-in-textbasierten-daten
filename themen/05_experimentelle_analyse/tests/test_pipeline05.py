"""Messgrenzen, Fehlerfortpflanzung und strikte Konfigurations-/CSV-Verträge."""

from copy import deepcopy
import csv
import gc
import json
from pathlib import Path
import random

import pytest

from experimentelle_analyse import pipeline
from experimentelle_analyse.schema import (
    BATCH_FIELDS, FLOW_FIELDS, check_derived, integer, read_csv, validate_config, write_csv,
)


ROOT = Path(__file__).resolve().parents[3]


def valid_config():
    return {
        "schema_version": 1, "seed": 20261006, "warmups": 1, "repeats": 3,
        "block_size": 5, "memory_repeats": 3,
        "datasets": [{"id": "tiny", "kind": "synthetic", "documents": 2,
                      "length": 100, "vocabulary": 32}],
        "q_values": [0, 1, 10],
    }


@pytest.fixture
def restore_gc_state():
    state = gc.isenabled()
    yield
    gc.enable() if state else gc.disable()


@pytest.mark.parametrize("initial_gc", [True, False])
def test_timer_materializes_all_results_then_validates_outside_interval(monkeypatch, restore_gc_state, initial_gc):
    gc.enable() if initial_gc else gc.disable()
    events = []
    expected_objects = [[0], [1], [2]]
    clock_values = iter([100, 160])

    def clock():
        events.append("clock")
        assert not gc.isenabled()
        return next(clock_values)

    def operation():
        assert not gc.isenabled()
        result = expected_objects[sum(event == "operation" for event in events)]
        events.append("operation")
        return result

    observed = []

    def validate(result):
        assert gc.isenabled() is initial_gc
        events.append("validate")
        observed.append(result)

    monkeypatch.setattr(pipeline, "perf_counter_ns", clock)
    assert pipeline.timed(operation, 3, validate) == 60
    assert events == ["clock", "operation", "operation", "operation", "clock",
                      "validate", "validate", "validate"]
    assert all(observed[i] is expected_objects[i] for i in range(3))
    assert gc.isenabled() is initial_gc


@pytest.mark.parametrize("initial_gc", [True, False])
def test_operation_failure_propagates_and_restores_previous_gc(restore_gc_state, initial_gc):
    gc.enable() if initial_gc else gc.disable()
    validations = []

    def fail():
        assert not gc.isenabled()
        raise RuntimeError("operation failed")

    with pytest.raises(RuntimeError, match="operation failed"):
        pipeline.timed(fail, 3, validations.append)
    assert validations == []
    assert gc.isenabled() is initial_gc


@pytest.mark.parametrize("initial_gc", [True, False])
def test_incorrect_result_in_middle_of_block_cannot_be_hidden_by_final_result(restore_gc_state, initial_gc):
    gc.enable() if initial_gc else gc.disable()
    produced = iter([["ok"], ["wrong"], ["ok"]])
    calls = []

    def check(result):
        calls.append(result)
        if result != ["ok"]:
            raise AssertionError("middle result is wrong")

    with pytest.raises(AssertionError, match="middle result is wrong"):
        pipeline.timed(lambda: next(produced), 3, check)
    assert calls == [["ok"], ["wrong"]]
    assert list(produced) == []
    assert gc.isenabled() is initial_gc


def test_clock_failure_also_restores_gc(monkeypatch, restore_gc_state):
    gc.enable()

    def fail_clock():
        raise RuntimeError("timer failed")

    monkeypatch.setattr(pipeline, "perf_counter_ns", fail_clock)
    with pytest.raises(RuntimeError, match="timer failed"):
        pipeline.timed(lambda: [], 1, lambda result: None)
    assert gc.isenabled()


@pytest.mark.parametrize("fails", [False, True])
def test_gc_restores_disabled_state_even_if_operation_temporarily_enables_it(restore_gc_state, fails):
    gc.disable()

    def operation():
        gc.enable()
        if fails:
            raise RuntimeError("operation changed GC and failed")
        return []

    if fails:
        with pytest.raises(RuntimeError, match="changed GC"):
            pipeline.timed(operation, 1, lambda result: None)
    else:
        pipeline.timed(operation, 1, lambda result: None)
    assert not gc.isenabled()


def test_accepted_config_is_not_rewritten_by_validation():
    config = valid_config()
    before = deepcopy(config)
    assert validate_config(config) == before
    assert config == before


@pytest.mark.parametrize("filename", ["pilot.json", "main.json"])
def test_published_experiment_configs_pass_the_same_strict_validator(filename):
    config = json.loads((ROOT / "themen/05_experimentelle_analyse/experimente" / filename)
                        .read_text(encoding="utf-8"))
    assert validate_config(config) == config


@pytest.mark.parametrize("field", ["schema_version", "seed", "warmups", "repeats", "block_size",
                                   "memory_repeats", "datasets", "q_values"])
def test_each_missing_required_config_field_is_rejected(field):
    config = valid_config()
    del config[field]
    with pytest.raises(ValueError):
        validate_config(config)


@pytest.mark.parametrize("field,value", [
    ("schema_version", True), ("schema_version", 2), ("schema_version", "1"),
    ("seed", -1), ("seed", True), ("seed", "42"),
    ("warmups", -1), ("warmups", 1.0), ("warmups", True),
    ("repeats", 1), ("repeats", True), ("repeats", "3"),
    ("block_size", 0), ("block_size", 2.5), ("block_size", False),
    ("memory_repeats", 1), ("memory_repeats", None),
    ("total_repeats", 1), ("total_repeats", True),
    ("sequence_block_size", 0), ("sequence_block_size", True),
    ("q_values", []), ("q_values", [1, 0]), ("q_values", [0, 1, 1]),
    ("q_values", [-1]), ("q_values", [True]), ("q_values", [1.0]),
    ("datasets", []), ("datasets", {}), ("datasets", [{"id": "a"}]),
])
def test_malformed_configuration_values_are_rejected(field, value):
    config = valid_config()
    config[field] = value
    with pytest.raises(ValueError):
        validate_config(config)


@pytest.mark.parametrize("value", [0, -1, True, "3", 1.5, None])
def test_sequence_cycles_requires_a_positive_integer(value):
    config = valid_config()
    config["sequence_cycles"] = value
    with pytest.raises(ValueError):
        validate_config(config)


@pytest.mark.parametrize("value", [True, {}, [], 42])
def test_pilot_directory_requires_a_path_string(value):
    config = valid_config()
    config["pilot_directory"] = value
    with pytest.raises(ValueError):
        validate_config(config)


@pytest.mark.parametrize("field,value", [("unit", "ms"), ("repeat", 3), ("unexpected", None)])
def test_unknown_config_fields_and_units_do_not_get_silently_ignored(field, value):
    config = valid_config()
    config[field] = value
    with pytest.raises(ValueError):
        validate_config(config)


def test_duplicate_dataset_mapping_is_rejected():
    config = valid_config()
    config["datasets"].append(deepcopy(config["datasets"][0]))
    with pytest.raises(ValueError, match="Doppelte|eindeutig"):
        validate_config(config)


@pytest.mark.parametrize("value", ["", "-1", "1.0", "1e3", "nan", "inf", None, True, False, 1.5])
def test_integer_raw_values_reject_float_boolean_negative_and_missing_values(value):
    with pytest.raises(ValueError):
        integer(value, "elapsed_ns")


@pytest.mark.parametrize("value,expected", [(0, 0), (42, 42), ("0", 0), ("0042", 42), ("12345678901234567890", 12345678901234567890)])
def test_nonnegative_integer_raw_values_remain_exact(value, expected):
    assert integer(value, "elapsed_ns") == expected


@pytest.mark.parametrize("value", ["nan", "NaN", "inf", "-inf", "milliseconds", None, "1.001", "1000"])
def test_derived_values_reject_nonfinite_wrong_units_or_inconsistent_scale(value):
    with pytest.raises(ValueError):
        check_derived(value, 1.0, "ns_per_query")


def test_derived_values_accept_consistent_ratio():
    check_derived("12.5", 25 / 2, "ns_per_query")


@pytest.mark.parametrize("fields", [BATCH_FIELDS, FLOW_FIELDS])
def test_csv_shape_and_integer_unit_header_are_exact(tmp_path, fields):
    path = tmp_path / "raw.csv"
    row = {field: "value" for field in fields}
    write_csv(path, [row], fields)
    assert read_csv(path, fields) == [row]
    content = path.read_text(encoding="utf-8")
    path.write_text(content.replace("elapsed_ns", "elapsed_ms", 1), encoding="utf-8")
    with pytest.raises(ValueError, match="Felder/Einheiten"):
        read_csv(path, fields)


@pytest.mark.parametrize("damage", ["missing_header", "reordered_header", "extra_cell", "missing_cell"])
def test_corrupt_csv_shape_is_rejected(tmp_path, damage):
    path = tmp_path / "corrupt.csv"
    fields = list(BATCH_FIELDS)
    values = ["value"] * len(fields)
    if damage == "missing_header":
        fields = fields[:-1]
        values = values[:-1]
    elif damage == "reordered_header":
        fields[0], fields[1] = fields[1], fields[0]
    elif damage == "extra_cell":
        values.append("extra")
    else:
        values.pop()
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(fields)
        writer.writerow(values)
    with pytest.raises(ValueError):
        read_csv(path, BATCH_FIELDS)


def test_csv_writer_refuses_unregistered_fields(tmp_path):
    with pytest.raises(ValueError):
        write_csv(tmp_path / "extra.csv", [{"unregistered": 1}], BATCH_FIELDS)


def handcomputed_measurements(*, profile_grid=None):
    """Small complete ledger, constructed without running a timing operation.

    The invented integers are test-fixture values, never published as research
    measurements. Their model is 70000 + Q*2000 < Q*10000, hence Q >= 9.
    """
    from experimentelle_analyse.operations import result_hash
    from gemeinsam.messung import CSV_FIELDS

    config = valid_config()
    config.update(warmups=0, repeats=2, block_size=2, memory_repeats=2,
                  total_repeats=2, sequence_block_size=2, seed=17)
    queries = [
        {"id": "missing", "kind": "word", "text": "X", "terms": ["x"],
         "category": "missing", "length": 1, "expected": []},
        {"id": "frequent", "kind": "word", "text": "F", "terms": ["f"],
         "category": "frequent", "length": 1, "expected": ["d0.txt", "d1.txt"]},
        {"id": "rare", "kind": "word", "text": "S", "terms": ["s"],
         "category": "rare", "length": 1, "expected": ["d0.txt"]},
        {"id": "and3", "kind": "and", "text": "A B C", "terms": ["a", "b", "c"],
         "category": "frequent", "length": 3, "expected": ["d0.txt", "d1.txt"]},
        {"id": "or3", "kind": "or", "text": "A B C", "terms": ["a", "b", "c"],
         "category": "frequent", "length": 3, "expected": ["d0.txt", "d1.txt"]},
        {"id": "phrase3", "kind": "phrase", "text": "A B C", "terms": ["a", "b", "c"],
         "category": "frequent", "length": 3, "expected": {"d0.txt": [2], "d1.txt": [1]}},
    ]
    for query in queries:
        query["hit_count"] = len(query["expected"])
        query["position_count"] = 2 if query["kind"] == "phrase" else None
    profiles = [
        {"id": "word_missing", "query_id": "missing", "algorithm": "index"},
        {"id": "word_frequent", "query_id": "frequent", "algorithm": "index"},
        {"id": "word_rare", "query_id": "rare", "algorithm": "index"},
        {"id": "and_present3", "query_id": "and3", "algorithm": "index_shortest"},
        {"id": "or_present3", "query_id": "or3", "algorithm": "index"},
        {"id": "phrase_present3", "query_id": "phrase3", "algorithm": "index"},
    ]
    for profile in profiles:
        profile["q_values"] = [0, 1, 4, 8, 9, 10, 18] if profile_grid is None else list(profile_grid)
        profile["calibration_model"] = {
            "delta_c_ns": 70000.0, "delta_t_ns": 8000.0, "equality_q": 8.75,
            "first_cheaper_q": 9, "last_cheaper_q": None,
            "has_advantage": True, "later_amortisation": True,
        }
    dataset = {"id": "tiny", "kind": "synthetic", "queries": queries, "profiles": profiles,
               "document_count": 2, "token_count": 9, "text_bytes": 21}
    meta = {"config": config, "status": "complete", "run_id": "test_fixture",
            "environment": {"git_commit": "test_fixture"}, "datasets": [dataset]}
    rows, batches, totals, memory, checks = [], [], [], [], []
    rng = random.Random(config["seed"])
    phases = [("load", "common"), ("preparation", "common"),
              ("build", "inverted_index"), ("build", "positional_index")]

    def algorithms(query):
        return ["direct", "index", "index_shortest"] if query["kind"] == "and" else ["direct", "index"]

    tasks = [(query, algorithm) for query in queries for algorithm in algorithms(query)]
    for repeat in range(2):
        order = list(phases)
        rng.shuffle(order)
        for order_index, (phase, algorithm) in enumerate(order):
            elapsed = 70000 if phase == "build" else (1000 if phase == "load" else 2000)
            row = dict.fromkeys(CSV_FIELDS, "")
            row.update(run_id=meta["run_id"], git_commit="test_fixture", seed="17", dataset_id="tiny",
                       document_count="2", token_count="9", text_bytes="21", algorithm=algorithm,
                       phase=phase, repeat=str(repeat), order_index=str(order_index), block_size="1",
                       elapsed_ns=str(elapsed), correct="True")
            row[phase + "_ms"] = str(elapsed / 1e6)
            rows.append(row)
        order = list(tasks)
        rng.shuffle(order)
        for order_index, (query, algorithm) in enumerate(order):
            elapsed = 20000 if algorithm == "direct" else 4000
            row = dict.fromkeys(CSV_FIELDS, "")
            row.update(run_id=meta["run_id"], git_commit="test_fixture", seed="17", dataset_id="tiny",
                       document_count="2", token_count="9", text_bytes="21", algorithm=algorithm,
                       phase="query", query_id=query["id"], query_text=query["text"], query_type=query["kind"],
                       repeat=str(repeat), order_index=str(order_index), block_size="2",
                       elapsed_ns=str(elapsed), query_ms=str(elapsed / 2 / 1e6),
                       hit_count=str(query["hit_count"]), correct="True")
            rows.append(row)
    query_lookup = {query["id"]: query for query in queries}
    for profile in profiles:
        for repeat in range(2):
            order = ["direct", profile["algorithm"]]
            rng.shuffle(order)
            for order_index, algorithm in enumerate(order):
                elapsed = 20000 if algorithm == "direct" else 4000
                batches.append({"run_id": meta["run_id"], "dataset_id": "tiny", "profile_id": profile["id"],
                                "algorithm": algorithm, "repeat": str(repeat), "order_index": str(order_index),
                                "query_count": "2", "elapsed_ns": str(elapsed), "ns_per_query": str(elapsed / 2),
                                "unit": "ns", "correct": "True"})
    for profile in profiles:
        tasks = [(count, algorithm) for count in profile["q_values"] for algorithm in ("direct", profile["algorithm"])]
        for repeat in range(-1, 2):
            order = list(tasks)
            rng.shuffle(order)
            if repeat < 0:
                continue
            for order_index, (count, algorithm) in enumerate(order):
                elapsed = 2000 + count * 10000 if algorithm == "direct" else 72000 + count * 2000
                totals.append({"run_id": meta["run_id"], "dataset_id": "tiny", "profile_id": profile["id"],
                               "algorithm": algorithm, "repeat": str(repeat), "order_index": str(order_index),
                               "query_count": str(count), "elapsed_ns": str(elapsed), "unit": "ns", "correct": "True",
                               "result_digest": result_hash(query_lookup[profile["query_id"]]["expected"])})
    for algorithm, pid in (("inverted_index", 101), ("positional_index", 102)):
        for repeat in range(2):
            memory.append({"run_id": meta["run_id"], "dataset_id": "tiny", "algorithm": algorithm,
                           "unit": "bytes", "retained_traced_bytes": 100, "peak_traced_bytes": 150,
                           "transient_peak_bytes": 50, "worker_pid": pid, "repeat": repeat})
    for query in queries:
        for algorithm in algorithms(query):
            checks.append({"dataset_id": "tiny", "query_id": query["id"], "algorithm": algorithm,
                           "result_sha256": result_hash(query["expected"]), "hit_count": query["hit_count"],
                           "position_count": query["position_count"], "validated_calls": 5})
    return meta, rows, batches, totals, memory, checks


def test_small_complete_handcomputed_ledger_passes_without_running_a_timer():
    from experimentelle_analyse.verify import verify_rows
    verify_rows(*handcomputed_measurements())


@pytest.mark.parametrize("damage", [
    "missing_raw", "duplicate_raw", "bad_repeat", "wrong_dataset", "wrong_run", "wrong_seed",
    "wrong_unit_scale", "elapsed_float", "wrong_query_text", "wrong_hit_count", "incorrect_result",
    "missing_batch", "batch_wrong_unit", "batch_wrong_derived", "missing_total", "total_wrong_unit",
    "total_wrong_digest", "memory_wrong_unit", "memory_wrong_peak", "memory_missing_algorithm",
    "ledger_missing", "ledger_wrong_digest", "ledger_wrong_call_count",
    "ledger_wrong_hit_count", "ledger_wrong_position_count", "config_dataset_mapping", "order_indices_shifted",
])
def test_corrupted_measurement_evidence_is_rejected(damage):
    from experimentelle_analyse.verify import verify_rows
    evidence = handcomputed_measurements()
    meta, rows, batches, totals, memory, checks = evidence
    query_row = next(row for row in rows if row["phase"] == "query")
    if damage == "missing_raw":
        rows.pop()
    elif damage == "duplicate_raw":
        rows.append(deepcopy(rows[0]))
    elif damage == "bad_repeat":
        rows[0]["repeat"] = "-1"
    elif damage == "wrong_dataset":
        rows[0]["dataset_id"] = "unrecorded"
    elif damage == "wrong_run":
        rows[0]["run_id"] = "another_run"
    elif damage == "wrong_seed":
        rows[0]["seed"] = "18"
    elif damage == "wrong_unit_scale":
        rows[0][rows[0]["phase"] + "_ms"] = "1000"
    elif damage == "elapsed_float":
        rows[0]["elapsed_ns"] = "1000.0"
    elif damage == "wrong_query_text":
        query_row["query_text"] = "wrong text"
    elif damage == "wrong_hit_count":
        query_row["hit_count"] = "999"
    elif damage == "incorrect_result":
        rows[0]["correct"] = "False"
    elif damage == "missing_batch":
        batches.pop()
    elif damage == "batch_wrong_unit":
        batches[0]["unit"] = "ms"
    elif damage == "batch_wrong_derived":
        batches[0]["ns_per_query"] = "1"
    elif damage == "missing_total":
        totals.pop()
    elif damage == "total_wrong_unit":
        totals[0]["unit"] = "ms"
    elif damage == "total_wrong_digest":
        totals[0]["result_digest"] = "0" * 64
    elif damage == "memory_wrong_unit":
        memory[0]["unit"] = "KB"
    elif damage == "memory_wrong_peak":
        memory[0]["peak_traced_bytes"] = 99
    elif damage == "memory_missing_algorithm":
        memory[:] = [row for row in memory if row["algorithm"] != "positional_index"]
    elif damage == "ledger_missing":
        checks.pop()
    elif damage == "ledger_wrong_digest":
        checks[0]["result_sha256"] = "0" * 64
    elif damage == "ledger_wrong_call_count":
        checks[0]["validated_calls"] = 4
    elif damage == "ledger_wrong_hit_count":
        checks[0]["hit_count"] = 999
    elif damage == "ledger_wrong_position_count":
        next(check for check in checks if check["position_count"] is not None)["position_count"] = 999
    elif damage == "config_dataset_mapping":
        meta["config"]["datasets"][0]["id"] = "unrecorded"
    else:
        for row in rows:
            row["order_index"] = str(int(row["order_index"]) + 100)
    with pytest.raises(ValueError):
        verify_rows(*evidence)


def test_profile_q_grid_cannot_be_changed_even_if_corresponding_totals_are_rewritten():
    from experimentelle_analyse.verify import verify_rows
    with pytest.raises(ValueError):
        verify_rows(*handcomputed_measurements(profile_grid=[0, 1, 10]))


def test_profile_calibration_model_must_match_the_recorded_build_and_query_costs():
    from experimentelle_analyse.verify import verify_rows
    evidence = handcomputed_measurements()
    evidence[0]["datasets"][0]["profiles"][0]["calibration_model"]["first_cheaper_q"] = 1
    with pytest.raises(ValueError):
        verify_rows(*evidence)


def test_analysis_quartiles_and_scatter_match_independently_calculated_values():
    from experimentelle_analyse.analysis import stats
    assert stats([1, 2, 4, 7]) == {
        "samples": 4, "median": 3.0, "q1": 1.75, "q3": 4.75,
        "iqr": 3.0, "min": 1.0, "max": 7.0,
    }
    assert stats([7, 4, 2, 1]) == stats([1, 2, 4, 7])
    with pytest.raises(ValueError):
        stats([1])


def test_analysis_keeps_predicted_costs_and_measured_transition_separate():
    from experimentelle_analyse.analysis import calculate_models
    meta, rows, batches, totals, _memory, _checks = handcomputed_measurements()
    models = calculate_models(meta, rows, batches, totals)
    assert len(models) == 6
    for model in models:
        assert model["preparation_direct_ns"] == model["preparation_index_ns"] == 2000
        assert model["build_direct_ns"] == 0
        assert model["build_index_ns"] == 70000
        assert model["query_direct_ns"] == 10000
        assert model["query_index_ns"] == 2000
        assert model["equality_q"] == 8.75
        assert model["first_cheaper_q"] == 9
        assert model["observed_first_median_advantage_q"] == 9
        assert model["observed_first_positive_iqr_q"] == 9
        assert model["observed_transition_bracket"] == [8, 9]
        assert model["observed_median_advantage_qs"] == [9, 10, 18]
        assert model["observed_all_repeats_advantage_qs"] == [9, 10, 18]
        observations = {value["query_count"]: value for value in model["observations"]}
        assert observations[0]["direct_ns"]["median"] == 2000
        assert observations[0]["index_ns"]["median"] == 72000
        assert observations[8]["predicted_saving_ns"] == -6000
        assert observations[9]["predicted_saving_ns"] == 2000
        assert observations[8]["index_cheaper_repeats"] == 0
        assert observations[9]["index_cheaper_repeats"] == 2
        assert observations[9]["paired_saving_ns"]["median"] == 2000
        assert observations[9]["paired_saving_ns"]["iqr"] == 0
