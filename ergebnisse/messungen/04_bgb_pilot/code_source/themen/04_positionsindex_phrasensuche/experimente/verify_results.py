#!/usr/bin/env python3
"""Audit: volle Ergebnisse, Quelldaten, Integerzeiten, Statistik und Speicher."""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict
import csv
from datetime import datetime
import json
from pathlib import Path
import random
from statistics import median, quantiles
from tempfile import TemporaryDirectory

from gemeinsam.messung import CSV_FIELDS, MeasurementPlan
from invertierter_index import build_inverted_index
from positionsindex import build_positional_index, search_direct_phrase, search_index_phrase

if __package__:
    from .run import (ALGORITHMS, MEMORY_FIELDS, PARAMETERS, ROOT, code_hashes, datasets,
                      describe_dataset, sha, validate_positional)
else:
    from run import (ALGORITHMS, MEMORY_FIELDS, PARAMETERS, ROOT, code_hashes, datasets,
                     describe_dataset, sha, validate_positional)


def verify_data(rows, summary, metadata):
    """Gelieferte Reihe: vier Datensätze, kontrollierte Ergebnisgrößenreihe, Zeitwerte."""
    descriptions = {item["dataset_id"]: item for item in metadata["datasets"]}
    assert len(descriptions) == len(metadata["datasets"]) == 4
    generated = [item for item in descriptions.values() if item["kind"] == "generated"]
    assert len(generated) == 3
    baseline = generated[0]
    for dataset in generated[1:]:
        for field in ("document_count", "text_bytes", "token_count", "vocabulary_size", "posting_count", "unigram_statistics"):
            assert dataset[field] == baseline[field], f"controlled result-size series changes {field}"
    verify_timing_rows(rows, summary, metadata)


def verify_timing_rows(rows, summary, metadata):
    """Allgemeiner Teil für beliebig viele Datensätze (auch den BGB-Lauf).

    Schema, Einheiten, Leerfelder, Treffer, Stichprobenzahl, Statistik aus
    Integer-Blockzeiten und die deterministisch gemischte Reihenfolge.
    """
    plan = metadata["measurement_plan"]
    repeats = plan["repeats"]
    descriptions = {item["dataset_id"]: item for item in metadata["datasets"]}
    assert len(descriptions) == len(metadata["datasets"]) >= 1
    expected_keys = set()
    for identifier, dataset in descriptions.items():
        expected_keys.update((identifier, algorithm, "build", "") for algorithm in ("inverted_index", "positional_index"))
        assert len({q["query_id"] for q in dataset["queries"]}) == len(dataset["queries"])
        expected_keys.update((identifier, algorithm, "query", query["query_id"])
                             for algorithm in ALGORITHMS for query in dataset["queries"])
    assert len(rows) == len(expected_keys) * repeats and len(summary) == len(expected_keys)
    grouped = defaultdict(list)
    for row in rows:
        dataset = descriptions[row["dataset_id"]]
        phase = row["phase"]
        key = row["dataset_id"], row["algorithm"], phase, row["query_id"]
        assert key in expected_keys and row["correct"] == "True"
        assert row["run_id"] == metadata["run_id"] and row["git_commit"] == metadata["git_commit"]
        assert int(row["seed"]) == plan["seed"]
        assert all(int(row[field]) == dataset[field] for field in ("document_count", "text_bytes", "token_count"))
        elapsed, block = int(row["elapsed_ns"]), int(row["block_size"])
        assert elapsed >= 0 and block > 0
        assert float(row[f"{phase}_ms"]) == elapsed / 1_000_000 / block
        assert all(row[f"{other}_ms"] == "" for other in ("load", "preparation", "build", "query") if other != phase)
        assert row["index_bytes"] == row["peak_memory_bytes"] == ""
        if phase == "query":
            query = next(q for q in dataset["queries"] if q["query_id"] == row["query_id"])
            assert block == plan["query_block_size"] and row["query_type"] == "phrase"
            assert row["query_text"] == query["text"]
            assert int(row["hit_count"]) == query["hit_count"] == len(query["expected_positions"])
            assert query["position_count"] == sum(map(len, query["expected_positions"].values()))
        else:
            assert block == 1
            assert all(row[field] == "" for field in ("query_id", "query_type", "query_text", "order_index", "hit_count"))
        grouped[key].append(row)
    assert set(grouped) == expected_keys
    seen = set()
    for item in summary:
        key = item["dataset_id"], item["algorithm"], item["phase"], item["query_id"]
        assert key not in seen and key in grouped
        seen.add(key)
        group = grouped[key]
        assert sorted(int(row["repeat"]) for row in group) == list(range(repeats))
        assert item["sample_count"] == repeats and item["token_count"] == descriptions[key[0]]["token_count"]
        assert item["query_type"] == group[0]["query_type"]
        values = [int(row["elapsed_ns"]) / 1_000_000 / int(row["block_size"]) for row in group]
        q1, _, q3 = quantiles(values, n=4, method="inclusive")
        assert item["median_ms"] == median(values)
        assert item["q1_ms"] == q1 and item["q3_ms"] == q3 and item["iqr_ms"] == q3 - q1
        assert item["minimum_ms"] == min(values) and item["maximum_ms"] == max(values)
    assert seen == expected_keys
    for identifier, dataset in descriptions.items():
        rng = random.Random(plan["seed"])
        tasks = [(algorithm, query["query_id"]) for algorithm in sorted(ALGORITHMS) for query in dataset["queries"]]
        for iteration in range(-plan["warmups"], repeats):
            order = tasks[:]
            rng.shuffle(order)
            if iteration < 0:
                continue
            observed = sorted((row for row in rows if row["dataset_id"] == identifier and row["phase"] == "query"
                               and int(row["repeat"]) == iteration), key=lambda row: int(row["order_index"]))
            assert [int(row["order_index"]) for row in observed] == list(range(len(tasks)))
            assert [(row["algorithm"], row["query_id"]) for row in observed] == order


def verify_corpora(metadata):
    assert metadata["parameters"] == PARAMETERS, "parameter contract changed"
    checked, expected_datasets = 0, metadata["datasets"]
    with TemporaryDirectory(prefix="textsuche-04-audit-") as temporary:
        regenerated = list(datasets(temporary))
        assert [item[0] for item in regenerated] == [item["dataset_id"] for item in expected_datasets]
        for (identifier, directory, tokens, queries, extra), saved in zip(regenerated, expected_datasets):
            prepared, postings, positional, description = describe_dataset(identifier, directory, tokens, queries, extra)
            assert description == saved, "dataset/query/positions metadata differs from regenerated independent plan"
            inverted = build_inverted_index(prepared)
            assert dict(inverted) == postings
            del inverted
            index = build_positional_index(prepared)
            validate_positional(index, positional)
            for query in queries:
                assert search_direct_phrase(prepared, query.tokens) == query.expected
                assert search_index_phrase(index, query.tokens) == query.expected
            validate_positional(index, positional)
            del index
            checked += len(saved["files"])
    return checked


def verify_memory(memory, csv_rows, metadata):
    assert memory["schema"] == list(MEMORY_FIELDS)
    assert memory["measurement"] == metadata["memory"]
    assert memory["code_sha256"] == metadata["code_sha256"]
    rows, repeats = memory["rows"], metadata["memory"]["repeats"]
    assert repeats == 3
    descriptions = {ds["dataset_id"]: ds for ds in metadata["datasets"]}
    expected_keys = {(identifier, algorithm) for identifier in descriptions for algorithm in ("inverted_index", "positional_index")}
    assert len(rows) == len(csv_rows) == len(expected_keys) * repeats
    assert len(memory["workers"]) == len(memory["summary"]) == len(expected_keys)
    grouped = defaultdict(list)
    for row, saved in zip(rows, csv_rows):
        assert set(row) == set(MEMORY_FIELDS)
        assert {key: str(row[key]) for key in MEMORY_FIELDS} == saved
        key = row["dataset_id"], row["algorithm"]
        assert key in expected_keys
        dataset = descriptions[key[0]]
        assert row["run_id"] == metadata["run_id"]
        assert all(row[field] == dataset[field] for field in ("document_count", "token_count", "vocabulary_size", "posting_count"))
        retained, peak, transient = (row[field] for field in ("retained_traced_bytes", "peak_traced_bytes", "transient_peak_bytes"))
        assert all(isinstance(value, int) and not isinstance(value, bool) for value in (retained, peak, transient, row["worker_pid"]))
        assert retained > 0 and peak >= retained and transient == peak - retained
        grouped[key].append(row)
    assert set(grouped) == expected_keys
    workers = {}
    previous_end = datetime.fromisoformat(metadata["timing_completed_at_utc"])
    for worker in memory["workers"]:
        key = worker["dataset_id"], worker["algorithm"]
        assert key in expected_keys and key not in workers
        workers[key] = worker
        assert worker["code_sha256"] == metadata["code_sha256"]
        start, end = (datetime.fromisoformat(worker[field]) for field in ("started_at_utc", "completed_at_utc"))
        assert previous_end <= start <= end, "profiling overlaps time run or another worker"
        previous_end = end
        group = grouped[key]
        assert sorted(row["repeat"] for row in group) == list(range(repeats))
        assert all(row["worker_pid"] == worker["worker_pid"] for row in group)
    assert len({worker["worker_pid"] for worker in workers.values()}) == len(expected_keys), "algorithms require separate processes"
    seen = set()
    for item in memory["summary"]:
        key = item["dataset_id"], item["algorithm"]
        assert key not in seen and key in grouped
        seen.add(key)
        for field in ("retained_traced_bytes", "peak_traced_bytes", "transient_peak_bytes"):
            assert item[f"median_{field}"] == median(row[field] for row in grouped[key])
    assert seen == expected_keys


def verify_directory(directory, *, check_active_code=True, require_memory=True):
    directory = Path(directory)
    with (directory / "raw.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames) == CSV_FIELDS
        rows = list(reader)
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["parameters"] == PARAMETERS
    expected_plans = {"04_pilot": asdict(MeasurementPlan(warmups=1, repeats=3, query_block_size=5)),
                      "04_final": PARAMETERS["final_plan"]}
    assert metadata["run_id"] in expected_plans
    assert metadata["measurement_plan"] == expected_plans[metadata["run_id"]], "run has wrong locked measurement plan"
    if check_active_code:
        assert metadata["code_sha256"] == code_hashes(), "active measurement code changed"
    assert metadata["code_sha256"]
    for relative, expected in metadata["code_sha256"].items():
        assert not Path(relative).is_absolute() and ".." not in Path(relative).parts
        assert sha(directory / "code_source" / relative) == expected, f"source archive damaged: {relative}"
    verify_data(rows, summary, metadata)
    files = verify_corpora(metadata)
    memory_count = 0
    if require_memory or (directory / "memory.json").exists():
        memory = json.loads((directory / "memory.json").read_text(encoding="utf-8"))
        with (directory / "memory.csv").open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            assert tuple(reader.fieldnames) == MEMORY_FIELDS
            memory_rows = list(reader)
        verify_memory(memory, memory_rows, metadata)
        memory_count = len(memory_rows)
    return len(rows), len(summary), files, memory_count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--timing-only", action="store_true", help="audit timing before separate memory run")
    parser.add_argument("--archive-only", action="store_true", help="allow changed active sources; archive hashes remain checked; semantic rerun uses active code")
    args = parser.parse_args()
    directory = ROOT / "ergebnisse/messungen" / ("04_pilot" if args.pilot else "04_positionsindex_phrasensuche")
    counts = verify_directory(directory, check_active_code=not args.archive_only, require_memory=not args.timing_only)
    print(f"{counts[0]} Rohwerte, {counts[1]} Statistikgruppen, {counts[2]} Dateien und {counts[3]} Speicherwerte geprüft; volle Positionen/Tokenpläne/Randomisierung/Quellarchiv korrekt.")


if __name__ == "__main__":
    main()
