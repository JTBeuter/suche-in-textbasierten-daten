#!/usr/bin/env python3
"""Rohwerte, Statistik, Randomisierung, Daten und eingefrorene Quellen prüfen."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import random
from statistics import median, quantiles
from tempfile import TemporaryDirectory

from gemeinsam.messung import CSV_FIELDS
from boolean_generator import generate_corpus
from run import ALGORITHMS, ROOT, eligible, make_queries, query_metadata, real_fixture, sha, validate_dataset


def verify_data(rows, summary, metadata):
    """Statistik wird direkt aus den Integer-Blockzeiten neu berechnet."""
    plan = metadata["measurement_plan"]
    repeats = plan["repeats"]
    datasets = {ds["dataset_id"]: ds for ds in metadata["datasets"]}
    assert len(datasets) == 2
    grouped = defaultdict(list)
    expected_keys = set()
    for identifier, dataset in datasets.items():
        expected_keys.update((identifier, algorithm, phase, "") for algorithm, phase in
                             (("corpus_loader", "load"), ("tokenizer", "preparation"), ("inverted_index", "build")))
        for query in dataset["queries"]:
            for algorithm in ALGORITHMS:
                applies = algorithm == "direct_boolean" or (query["operator"] == "AND" and algorithm.startswith("and_")) or (query["operator"] == "OR" and algorithm == "or_input_order")
                if applies:
                    expected_keys.add((identifier, algorithm, "query", query["query_id"]))
    assert len(rows) == len(expected_keys) * repeats
    assert len(summary) == len(expected_keys)
    for row in rows:
        dataset = datasets[row["dataset_id"]]
        phase = row["phase"]
        key = row["dataset_id"], row["algorithm"], phase, row["query_id"]
        assert key in expected_keys
        assert row["correct"] == "True"
        assert row["run_id"] == metadata["run_id"] and row["git_commit"] == metadata["git_commit"]
        assert int(row["seed"]) == plan["seed"]
        for field in ("document_count", "text_bytes", "token_count"):
            assert int(row[field]) == dataset[field]
        elapsed, block = int(row["elapsed_ns"]), int(row["block_size"])
        assert elapsed >= 0 and block >= 1
        assert float(row[f"{phase}_ms"]) == elapsed / 1_000_000 / block
        for other in ("load", "preparation", "build", "query"):
            if other != phase:
                assert row[f"{other}_ms"] == ""
        assert row["index_bytes"] == row["peak_memory_bytes"] == ""
        if phase == "query":
            query = next(q for q in dataset["queries"] if q["query_id"] == row["query_id"])
            assert block == plan["query_block_size"]
            assert row["query_text"] == query["text"] and row["query_type"] == query["operator"].lower()
            assert int(row["hit_count"]) == query["hit_count"] == len(query["expected_ids"])
        else:
            assert block == 1
            assert all(row[field] == "" for field in ("query_id", "query_text", "query_type", "order_index", "hit_count"))
        grouped[key].append(row)
    assert set(grouped) == expected_keys
    seen_summary = set()
    for item in summary:
        key = item["dataset_id"], item["algorithm"], item["phase"], item["query_id"]
        assert key not in seen_summary
        seen_summary.add(key)
        group = grouped[key]
        assert sorted(int(row["repeat"]) for row in group) == list(range(repeats))
        assert item["sample_count"] == repeats and item["token_count"] == datasets[key[0]]["token_count"]
        assert item["query_type"] == group[0]["query_type"]
        values = [int(row["elapsed_ns"]) / 1_000_000 / int(row["block_size"]) for row in group]
        q1, _, q3 = quantiles(values, n=4, method="inclusive")
        assert item["median_ms"] == median(values)
        assert item["q1_ms"] == q1 and item["q3_ms"] == q3 and item["iqr_ms"] == q3 - q1
        assert item["minimum_ms"] == min(values) and item["maximum_ms"] == max(values)
    assert seen_summary == expected_keys
    for identifier, dataset in datasets.items():
        rng = random.Random(plan["seed"])
        # Query order and algorithm order are both fixed before each shuffle.
        tasks = [(algorithm, q["query_id"]) for algorithm in sorted(ALGORITHMS) for q in dataset["queries"]
                 if algorithm == "direct_boolean" or (q["operator"] == "AND" and algorithm.startswith("and_"))
                 or (q["operator"] == "OR" and algorithm == "or_input_order")]
        for iteration in range(-plan["warmups"], repeats):
            order = list(tasks)
            rng.shuffle(order)
            if iteration < 0:
                continue
            observed = sorted((row for row in rows if row["dataset_id"] == identifier and row["phase"] == "query"
                               and int(row["repeat"]) == iteration), key=lambda row: int(row["order_index"]))
            assert [int(row["order_index"]) for row in observed] == list(range(len(tasks)))
            assert [(row["algorithm"], row["query_id"]) for row in observed] == order


def verify_corpora(metadata):
    checked = 0
    with TemporaryDirectory(prefix="textsuche-03-verify-") as temporary:
        for dataset in metadata["datasets"]:
            if dataset["kind"] == "generated":
                parameters = metadata["parameters"]["synthetic"]
                generated = generate_corpus(Path(temporary) / "controlled", document_count=parameters["document_count"],
                    tokens_per_document=parameters["tokens_per_document"], seed=metadata["parameters"]["seed"])
                directory, tokens, membership, source = generated.root, generated.expected_tokens, generated.membership, None
                assert {entry["document_id"]: entry["sha256"] for entry in dataset["files"]} == generated.file_sha256
            else:
                directory, tokens, source = real_fixture()
                membership = None
                assert source == dataset["source_fixture"]
            _, _, _, _, recomputed = validate_dataset(dataset["dataset_id"], directory, tokens, membership, source)
            assert recomputed == dataset, "Datensatz/Anfragen/Diagnose weichen von erneuter unabhängiger Prüfung ab"
            checked += len(dataset["files"])
    return checked


def verify_directory(directory, *, check_active_code=True):
    directory = Path(directory)
    with (directory / "raw.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames) == CSV_FIELDS
        rows = list(reader)
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    for relative, expected in metadata["code_sha256"].items():
        assert not Path(relative).is_absolute() and ".." not in Path(relative).parts
        assert sha(directory / "code_source" / relative) == expected, f"Quelltextarchiv beschädigt: {relative}"
        if check_active_code:
            assert sha(ROOT / relative) == expected, f"aktiver Code geändert: {relative}"
    verify_data(rows, summary, metadata)
    return len(rows), len(summary), verify_corpora(metadata)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--archive-only", action="store_true", help="aktuelle Quelltexte dürfen abweichen; Archiv, Rohwerte und Daten bleiben geprüft")
    args = parser.parse_args()
    directory = ROOT / "ergebnisse/messungen" / ("03_pilot" if args.pilot else "03_boolesche_mehrwortsuche")
    rows, groups, files = verify_directory(directory, check_active_code=not args.archive_only)
    print(f"{rows} Rohwerte, {groups} Statistikgruppen, {files} Datei-Hashes, Query-Diagnosen, Reihenfolge und Quelltextarchive geprüft.")


if __name__ == "__main__":
    main()
