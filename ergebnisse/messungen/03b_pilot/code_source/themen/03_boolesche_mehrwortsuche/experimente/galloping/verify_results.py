#!/usr/bin/env python3
"""Reihe 03b: Rohwerte, Statistik, Randomisierung, Daten und eingefrorene Quellen prüfen."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import importlib.util
import json
from pathlib import Path
import random
from statistics import median, quantiles
import sys
from tempfile import TemporaryDirectory


def load_sibling(name):
    """Lädt ein Skript dieses Ordners unter eindeutigem Namen (Reihe 03 hat gleichnamige Skripte)."""
    label = f"reihe03b_{name}"
    if label not in sys.modules:
        spec = importlib.util.spec_from_file_location(label, Path(__file__).resolve().with_name(f"{name}.py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[label] = module
        spec.loader.exec_module(module)
    return sys.modules[label]


run = load_sibling("run")

from gemeinsam.messung import CSV_FIELDS  # noqa: E402
from galloping_generator import generate_corpus  # noqa: E402


PHASES = (("corpus_loader", "load"), ("tokenizer", "preparation"), ("inverted_index", "build"))


def verify_data(rows, summary, metadata):
    """Statistik wird direkt aus den ganzzahligen Blockzeiten neu berechnet."""
    plan = metadata["measurement_plan"]
    repeats = plan["repeats"]
    assert len(metadata["datasets"]) == 1
    dataset = metadata["datasets"][0]
    identifier = dataset["dataset_id"]
    expected_keys = {(identifier, algorithm, phase, "") for algorithm, phase in PHASES}
    expected_keys.update((identifier, algorithm, "query", query["query_id"])
                         for algorithm in run.ALGORITHMS for query in dataset["queries"])
    assert len(dataset["queries"]) == len(run.STAGES) * len(run.CASES)
    assert len(rows) == len(expected_keys) * repeats
    assert len(summary) == len(expected_keys)
    grouped = defaultdict(list)
    for row in rows:
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
            assert row["query_text"] == query["text"] and row["query_type"] == "and"
            assert int(row["hit_count"]) == query["hit_count"] == len(query["expected_ids"])
        else:
            assert block == 1
            assert all(row[field] == "" for field in ("query_id", "query_text", "query_type", "order_index", "hit_count"))
        grouped[key].append(row)
    assert set(grouped) == expected_keys
    seen = set()
    for item in summary:
        key = item["dataset_id"], item["algorithm"], item["phase"], item["query_id"]
        assert key not in seen
        seen.add(key)
        group = grouped[key]
        assert sorted(int(row["repeat"]) for row in group) == list(range(repeats))
        assert item["sample_count"] == repeats and item["token_count"] == dataset["token_count"]
        assert item["query_type"] == group[0]["query_type"]
        values = [int(row["elapsed_ns"]) / 1_000_000 / int(row["block_size"]) for row in group]
        q1, _, q3 = quantiles(values, n=4, method="inclusive")
        assert item["median_ms"] == median(values)
        assert item["q1_ms"] == q1 and item["q3_ms"] == q3 and item["iqr_ms"] == q3 - q1
        assert item["minimum_ms"] == min(values) and item["maximum_ms"] == max(values)
    assert seen == expected_keys
    # Reihenfolge: dieselbe Mischung wie run.measure_comparison inklusive Warmups.
    rng = random.Random(plan["seed"])
    tasks = [(algorithm, query["query_id"]) for algorithm in sorted(run.ALGORITHMS) for query in dataset["queries"]]
    for iteration in range(-plan["warmups"], repeats):
        order = list(tasks)
        rng.shuffle(order)
        if iteration < 0:
            continue
        observed = sorted((row for row in rows if row["phase"] == "query" and int(row["repeat"]) == iteration),
                          key=lambda row: int(row["order_index"]))
        assert [int(row["order_index"]) for row in observed] == list(range(len(tasks)))
        assert [(row["algorithm"], row["query_id"]) for row in observed] == order


def recompute_dataset(metadata):
    """Korpus neu erzeugen, Dateihashes vergleichen und alle Prüfungen und Diagnosen wiederholen."""
    dataset = metadata["datasets"][0]
    with TemporaryDirectory(prefix="textsuche-03b-verify-") as temporary:
        generated = generate_corpus(Path(temporary) / "galloping", seed=metadata["parameters"]["seed"])
        assert {entry["document_id"]: entry["sha256"] for entry in dataset["files"]} == generated.file_sha256
        _, _, _, _, recomputed = run.validate_dataset(dataset["dataset_id"], generated.root,
                                                      generated.expected_tokens, generated.membership)
    return recomputed


def verify_corpus(metadata):
    dataset = metadata["datasets"][0]
    recomputed = recompute_dataset(metadata)
    assert recomputed == dataset, "Datensatz/Anfragen/Diagnose weichen von erneuter unabhängiger Prüfung ab"
    return len(dataset["files"])


def verify_directory(directory, *, check_active_code=True):
    directory = Path(directory)
    with (directory / "raw.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames) == CSV_FIELDS
        rows = list(reader)
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["run_id"] in ("03b_pilot", "03b_final")
    for relative, expected in metadata["code_sha256"].items():
        assert not Path(relative).is_absolute() and ".." not in Path(relative).parts
        assert run.sha(directory / "code_source" / relative) == expected, f"Quelltextarchiv beschädigt: {relative}"
    if check_active_code:
        assert run.code_hashes() == metadata["code_sha256"], "aktiver Messcode weicht von der Messfassung ab"
        assert metadata["parameters"] == run.PARAMETERS, "Parameter weichen vom gesperrten Versuchsplan ab"
    if metadata["run_id"] == "03b_pilot":
        decision = json.loads((directory / "pilot_decision.json").read_text(encoding="utf-8"))
        assert decision["pilot_correct"] is True and decision["locked_parameters"] == metadata["parameters"]
        assert decision["method_code_sha256"] == metadata["code_sha256"]
        assert decision["pilot_plan"] == metadata["measurement_plan"]
        assert decision["python_hash_seed"] == metadata["environment"]["python_hash_seed"] == run.REQUIRED_HASH_SEED
    else:
        assert metadata["environment"]["python_hash_seed"] == run.REQUIRED_HASH_SEED
        assert metadata["measurement_plan"] == metadata["parameters"]["final_plan"]
        reference = metadata["pilot_reference"]
        pilot = run.ROOT / reference["pilot_decision_path"]
        if pilot.is_file():
            assert run.sha(pilot) == reference["pilot_decision_sha256"], "Pilotentscheidung seit Finalmessung verändert"
            assert json.loads(pilot.read_text(encoding="utf-8"))["method_code_sha256"] == metadata["code_sha256"]
    verify_data(rows, summary, metadata)
    return len(rows), len(summary), verify_corpus(metadata)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eingabe", metavar="NAME",
                        help=f"Ordner unter ergebnisse/messungen (Standard {run.STANDARD_FINAL}, mit --pilot {run.STANDARD_PILOT})")
    parser.add_argument("--pilot", action="store_true", help=f"Kurzform für --eingabe {run.STANDARD_PILOT}")
    parser.add_argument("--archive-only", action="store_true",
                        help="aktuelle Quelltexte dürfen abweichen; Archiv, Rohwerte und Daten bleiben geprüft")
    args = parser.parse_args(argv)
    directory = run.messlauf03.directory_name(args.eingabe or (run.STANDARD_PILOT if args.pilot else run.STANDARD_FINAL))
    rows, groups, files = verify_directory(directory, check_active_code=not args.archive_only)
    print(f"{rows} Rohwerte, {groups} Statistikgruppen, {files} Datei-Hashes, Query-Diagnosen, "
          "Reihenfolge und Quelltextarchive geprüft.")


if __name__ == "__main__":
    main()
